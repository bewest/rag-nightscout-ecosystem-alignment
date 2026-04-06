#!/usr/bin/env python3
"""EXP-369 through EXP-372: Combined Best & Scaling Experiments

Building on EXP-368 validation (ResNet ISF MAE=35.8±0.1, new champion):

EXP-369 — Dilated ResNet
  Combine ResNet's residual connections (depth, skip connections) with
  dilated convolutions (multi-scale temporal receptive field).
  ResNet gave -1.9 vs baseline, TCN gave -6.4 in quick mode.
  Hypothesis: Complementary improvements stack for further gains.

EXP-370 — ResNet with Horizon-Conditioned FiLM
  ResNet backbone + per-horizon FiLM modulation + separate heads.
  FiLM resolved ISF short/long trade-off in EXP-367 (h30=19.4).
  Hypothesis: ResNet depth + FiLM horizon-adaptation = best of both.

EXP-371 — Per-Patient Fine-Tuning
  Train global ResNet model on all patients, then fine-tune last layers
  per-patient. DIA/absorption speed varies widely across patients.
  Hypothesis: Patient-specific adaptation reduces MAE by 2-4 mg/dL.

EXP-372 — History Window Scaling with ResNet
  EXP-353 showed PK crossover at 4h history. ResNet with 240K params
  has capacity for longer sequences. Test 6h, 9h, 12h history.
  Hypothesis: ResNet exploits longer windows better than small CNN.

Usage:
    python tools/cgmencode/exp_pk_forecast_v5.py --experiment 369 --device cuda --quick
    python tools/cgmencode/exp_pk_forecast_v5.py --experiment all --device cuda
"""

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, TensorDataset
import json, os, sys, time, argparse, copy
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cgmencode.real_data_adapter import build_nightscout_grid
from cgmencode.continuous_pk import build_continuous_pk_features

# ─── Constants ───

SEEDS = [42, 123, 456]
SEEDS_QUICK = [42]
GLUCOSE_SCALE = 400.0
QUICK_PATIENTS = 4
QUICK_EPOCHS = 30
QUICK_PATIENCE = 8

HORIZONS_EXTENDED = {
    'h30': 6, 'h60': 12, 'h120': 24, 'h180': 36,
    'h240': 48, 'h360': 72, 'h480': 96, 'h720': 144,
}
HORIZONS_STANDARD = {'h30': 6, 'h60': 12, 'h120': 24}

PK_NORMS = [0.05, 0.05, 2.0, 0.5, 0.05, 3.0, 20.0, 200.0]
FUTURE_PK_INDICES = [1, 2, 3, 6]


# ─── Data Loading (shared with v4) ───

def find_patient_dirs(patients_dir):
    base = Path(patients_dir)
    return sorted([d for d in base.iterdir()
                   if d.is_dir() and (d / 'training').exists()])


def load_patient_profile_isf(train_dir):
    profile_path = os.path.join(train_dir, 'profile.json')
    if not os.path.exists(profile_path):
        return None
    try:
        with open(profile_path) as f:
            profile = json.load(f)
        store = profile.get('store', {})
        default_profile = store.get('Default', store.get(next(iter(store), ''), {}))
        sens = default_profile.get('sens', [])
        if sens:
            isf_values = [s.get('value', 0) for s in sens]
            mean_isf = np.mean([v for v in isf_values if v > 0])
            if mean_isf < 15:
                mean_isf *= 18.0182
            return float(mean_isf) if mean_isf > 0 else None
        return None
    except Exception:
        return None


def load_forecast_data(patients_dir, history_steps=72, max_horizon=144,
                       max_patients=None, load_isf=False):
    """Load base + PK features with extended future window.

    Returns per-patient data for fine-tuning experiments.
    """
    patient_dirs = find_patient_dirs(patients_dir)
    if max_patients:
        patient_dirs = patient_dirs[:max_patients]
    print(f"Loading {len(patient_dirs)} patients "
          f"(history={history_steps}, horizon={max_horizon})")

    all_base_train, all_base_val = [], []
    all_pk_train, all_pk_val = [], []
    all_isf_train, all_isf_val = [], []
    per_patient = []  # For fine-tuning: track per-patient boundaries
    window_size = history_steps + max_horizon
    stride = history_steps // 2

    for pdir in patient_dirs:
        train_dir = str(pdir / 'training')
        df, base_grid = build_nightscout_grid(train_dir)
        pk_grid = build_continuous_pk_features(df)

        n_pts = min(len(base_grid), len(pk_grid))
        base_grid = base_grid[:n_pts].astype(np.float32)
        pk_grid = pk_grid[:n_pts].astype(np.float32)
        np.nan_to_num(base_grid, copy=False)
        np.nan_to_num(pk_grid, copy=False)

        isf = load_patient_profile_isf(train_dir) if load_isf else None

        windows_b, windows_p = [], []
        for start in range(0, n_pts - window_size + 1, stride):
            w_b = base_grid[start:start + window_size]
            w_p = pk_grid[start:start + window_size]
            if np.any(w_b[:history_steps, 0] > 0):
                windows_b.append(w_b)
                windows_p.append(w_p)

        if not windows_b:
            continue

        windows_b = np.array(windows_b, dtype=np.float32)
        windows_p = np.array(windows_p, dtype=np.float32)
        n = len(windows_b)
        split = int(n * 0.8)

        bt, bv = windows_b[:split], windows_b[split:]
        pt, pv = windows_p[:split], windows_p[split:]

        patient_info = {
            'name': pdir.name,
            'isf': isf,
            'train_start': len(all_base_train),
            'train_count': len(bt),
            'val_start': len(all_base_val),
            'val_count': len(bv),
        }

        all_base_train.extend(bt)
        all_base_val.extend(bv)
        all_pk_train.extend(pt)
        all_pk_val.extend(pv)

        if isf is not None:
            all_isf_train.extend([isf] * len(bt))
            all_isf_val.extend([isf] * len(bv))

        name = pdir.name
        print(f"  {name}: {n} windows ({len(bt)} train, {len(bv)} val)")
        per_patient.append(patient_info)

    base_t = np.array(all_base_train, dtype=np.float32)
    base_v = np.array(all_base_val, dtype=np.float32)
    pk_t = np.array(all_pk_train, dtype=np.float32)
    pk_v = np.array(all_pk_val, dtype=np.float32)
    print(f"Total: {len(base_t)} train, {len(base_v)} val")

    if load_isf and all_isf_train:
        isf_t = np.array(all_isf_train, dtype=np.float32)
        isf_v = np.array(all_isf_val, dtype=np.float32)
        return base_t, base_v, pk_t, pk_v, isf_t, isf_v, per_patient
    return base_t, base_v, pk_t, pk_v, None, None, per_patient


def extract_targets(base_windows, history_steps, horizons):
    indices = list(horizons.values())
    return base_windows[:, [history_steps + idx - 1 for idx in indices], 0]


# ─── Models ───

class ResBlock1d(nn.Module):
    """1D Residual block with optional channel change."""
    def __init__(self, in_ch, out_ch, kernel_size=3, dropout=0.1):
        super().__init__()
        padding = kernel_size // 2
        self.conv1 = nn.Conv1d(in_ch, out_ch, kernel_size, padding=padding)
        self.bn1 = nn.BatchNorm1d(out_ch)
        self.conv2 = nn.Conv1d(out_ch, out_ch, kernel_size, padding=padding)
        self.bn2 = nn.BatchNorm1d(out_ch)
        self.dropout = nn.Dropout(dropout)
        self.shortcut = (nn.Conv1d(in_ch, out_ch, 1) if in_ch != out_ch
                         else nn.Identity())

    def forward(self, x):
        residual = self.shortcut(x)
        out = F.relu(self.bn1(self.conv1(x)))
        out = self.dropout(out)
        out = self.bn2(self.conv2(out))
        return F.relu(out + residual)


class DilatedResBlock(nn.Module):
    """Residual block with dilated convolution for multi-scale features."""
    def __init__(self, channels, dilation, kernel_size=3, dropout=0.1):
        super().__init__()
        padding = (kernel_size - 1) * dilation // 2
        self.conv1 = nn.Conv1d(channels, channels, kernel_size,
                               dilation=dilation, padding=padding)
        self.conv2 = nn.Conv1d(channels, channels, 1)
        self.bn1 = nn.BatchNorm1d(channels)
        self.bn2 = nn.BatchNorm1d(channels)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x):
        residual = x
        out = F.relu(self.bn1(self.conv1(x)))
        out = self.dropout(out)
        out = self.bn2(self.conv2(out))
        return F.relu(out + residual)


class DilatedResNet(nn.Module):
    """Combines ResNet depth with dilated convolutions for multi-scale.

    Stage 1: ResNet stem (in→64) + ResBlock 64→128
    Stage 2: Dilated blocks at 128ch with dilations (1,2,4,8,16)
    Stage 3: ResBlock 128→64 + pool + head

    This gets both the depth/skip-connection benefits of ResNet
    and the multi-scale receptive field of dilated convolutions.
    """
    def __init__(self, in_channels, n_horizons=8, hidden=128,
                 dilations=(1, 2, 4, 8, 16), dropout=0.1):
        super().__init__()
        # Stage 1: ResNet stem
        self.stem = nn.Sequential(
            nn.Conv1d(in_channels, 64, kernel_size=5, padding=2),
            nn.ReLU(), nn.BatchNorm1d(64),
        )
        self.res_up = ResBlock1d(64, hidden, dropout=dropout)

        # Stage 2: Dilated blocks at hidden channels
        self.dilated_blocks = nn.ModuleList([
            DilatedResBlock(hidden, d, dropout=dropout) for d in dilations
        ])
        self.skip_proj = nn.Conv1d(hidden * len(dilations), hidden, 1)

        # Stage 3: Downsample + pool
        self.res_down = ResBlock1d(hidden, 64, dropout=dropout)
        self.pool = nn.AdaptiveAvgPool1d(1)
        self.head = nn.Sequential(
            nn.Linear(64, 64), nn.ReLU(), nn.Dropout(dropout),
            nn.Linear(64, n_horizons),
        )

    def forward(self, x):
        x = x.permute(0, 2, 1)
        x = self.stem(x)
        x = self.res_up(x)
        # Multi-scale dilated processing with skip aggregation
        skips = []
        for block in self.dilated_blocks:
            x = block(x)
            skips.append(x)
        combined = torch.cat(skips, dim=1)
        x = F.relu(self.skip_proj(combined))
        x = self.res_down(x)
        feat = self.pool(x).squeeze(-1)
        return self.head(feat)


class DilatedResNetWithFuture(nn.Module):
    """Dilated ResNet + future PK branch."""
    def __init__(self, hist_channels, pk_channels, n_horizons=8, hidden=128,
                 dilations=(1, 2, 4, 8, 16), dropout=0.1):
        super().__init__()
        self.stem = nn.Sequential(
            nn.Conv1d(hist_channels, 64, kernel_size=5, padding=2),
            nn.ReLU(), nn.BatchNorm1d(64),
        )
        self.res_up = ResBlock1d(64, hidden, dropout=dropout)
        self.dilated_blocks = nn.ModuleList([
            DilatedResBlock(hidden, d, dropout=dropout) for d in dilations
        ])
        self.skip_proj = nn.Conv1d(hidden * len(dilations), hidden, 1)
        self.res_down = ResBlock1d(hidden, 64, dropout=dropout)
        self.hist_pool = nn.AdaptiveAvgPool1d(1)

        self.future_conv = nn.Sequential(
            nn.Conv1d(pk_channels, 32, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(32),
            nn.Conv1d(32, 32, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(32),
            nn.AdaptiveAvgPool1d(1),
        )
        self.head = nn.Sequential(
            nn.Linear(64 + 32, 64), nn.ReLU(), nn.Dropout(dropout),
            nn.Linear(64, n_horizons),
        )

    def forward(self, x_hist, x_future):
        h = x_hist.permute(0, 2, 1)
        h = self.stem(h)
        h = self.res_up(h)
        skips = []
        for block in self.dilated_blocks:
            h = block(h)
            skips.append(h)
        combined = torch.cat(skips, dim=1)
        h = F.relu(self.skip_proj(combined))
        h = self.res_down(h)
        h_feat = self.hist_pool(h).squeeze(-1)

        f = x_future.permute(0, 2, 1)
        f_feat = self.future_conv(f).squeeze(-1)

        return self.head(torch.cat([h_feat, f_feat], dim=1))


class ResNetFiLM(nn.Module):
    """ResNet backbone + per-horizon FiLM modulation.

    Deep ResNet extracts features, then each horizon gets its own
    affine transformation (gamma, beta) of the feature vector,
    followed by a separate prediction head.
    """
    def __init__(self, in_channels, n_horizons=8, dropout=0.1):
        super().__init__()
        self.n_horizons = n_horizons
        self.stem = nn.Sequential(
            nn.Conv1d(in_channels, 64, kernel_size=5, padding=2),
            nn.ReLU(), nn.BatchNorm1d(64),
        )
        self.blocks = nn.Sequential(
            ResBlock1d(64, 128, dropout=dropout),
            ResBlock1d(128, 128, dropout=dropout),
            ResBlock1d(128, 64, dropout=dropout),
        )
        self.pool = nn.AdaptiveAvgPool1d(1)
        # Per-horizon FiLM parameters
        self.film_gamma = nn.Parameter(torch.ones(n_horizons, 64))
        self.film_beta = nn.Parameter(torch.zeros(n_horizons, 64))
        self.heads = nn.ModuleList([
            nn.Sequential(nn.Linear(64, 32), nn.ReLU(), nn.Linear(32, 1))
            for _ in range(n_horizons)
        ])

    def forward(self, x):
        x = x.permute(0, 2, 1)
        x = self.stem(x)
        x = self.blocks(x)
        feat = self.pool(x).squeeze(-1)
        outputs = []
        for i in range(self.n_horizons):
            modulated = feat * self.film_gamma[i] + self.film_beta[i]
            outputs.append(self.heads[i](modulated))
        return torch.cat(outputs, dim=1)


class ResNetFiLMWithFuture(nn.Module):
    """ResNet + FiLM + future PK branch."""
    def __init__(self, hist_channels, pk_channels, n_horizons=8, dropout=0.1):
        super().__init__()
        self.n_horizons = n_horizons
        self.stem = nn.Sequential(
            nn.Conv1d(hist_channels, 64, kernel_size=5, padding=2),
            nn.ReLU(), nn.BatchNorm1d(64),
        )
        self.blocks = nn.Sequential(
            ResBlock1d(64, 128, dropout=dropout),
            ResBlock1d(128, 128, dropout=dropout),
            ResBlock1d(128, 64, dropout=dropout),
        )
        self.hist_pool = nn.AdaptiveAvgPool1d(1)

        self.future_conv = nn.Sequential(
            nn.Conv1d(pk_channels, 32, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(32),
            nn.Conv1d(32, 32, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(32),
            nn.AdaptiveAvgPool1d(1),
        )
        combined_dim = 64 + 32
        self.film_gamma = nn.Parameter(torch.ones(n_horizons, combined_dim))
        self.film_beta = nn.Parameter(torch.zeros(n_horizons, combined_dim))
        self.heads = nn.ModuleList([
            nn.Sequential(nn.Linear(combined_dim, 32), nn.ReLU(),
                          nn.Linear(32, 1))
            for _ in range(n_horizons)
        ])

    def forward(self, x_hist, x_future):
        h = x_hist.permute(0, 2, 1)
        h = self.stem(h)
        h = self.blocks(h)
        h_feat = self.hist_pool(h).squeeze(-1)

        f = x_future.permute(0, 2, 1)
        f_feat = self.future_conv(f).squeeze(-1)

        feat = torch.cat([h_feat, f_feat], dim=1)
        outputs = []
        for i in range(self.n_horizons):
            modulated = feat * self.film_gamma[i] + self.film_beta[i]
            outputs.append(self.heads[i](modulated))
        return torch.cat(outputs, dim=1)


class ResNetCNNWithFuture(nn.Module):
    """Standard ResNet + future PK (from v4, for baseline/fine-tuning)."""
    def __init__(self, hist_channels, pk_channels, n_horizons=8, dropout=0.1):
        super().__init__()
        self.hist_stem = nn.Sequential(
            nn.Conv1d(hist_channels, 64, kernel_size=5, padding=2),
            nn.ReLU(), nn.BatchNorm1d(64),
        )
        self.hist_blocks = nn.Sequential(
            ResBlock1d(64, 128, dropout=dropout),
            ResBlock1d(128, 128, dropout=dropout),
            ResBlock1d(128, 64, dropout=dropout),
        )
        self.hist_pool = nn.AdaptiveAvgPool1d(1)

        self.future_conv = nn.Sequential(
            nn.Conv1d(pk_channels, 32, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(32),
            nn.Conv1d(32, 32, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(32),
            nn.AdaptiveAvgPool1d(1),
        )
        self.head = nn.Sequential(
            nn.Linear(64 + 32, 64), nn.ReLU(), nn.Dropout(dropout),
            nn.Linear(64, n_horizons),
        )

    def forward(self, x_hist, x_future):
        h = x_hist.permute(0, 2, 1)
        h = self.hist_stem(h)
        h = self.hist_blocks(h)
        h_feat = self.hist_pool(h).squeeze(-1)

        f = x_future.permute(0, 2, 1)
        f_feat = self.future_conv(f).squeeze(-1)

        return self.head(torch.cat([h_feat, f_feat], dim=1))


# ─── Training ───

def train_model(model, train_loader, val_loader, device, epochs=60,
                patience=15, lr=1e-3):
    model.to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, patience=5, factor=0.5)

    best_val_loss = float('inf')
    best_state = None
    wait = 0

    for epoch in range(epochs):
        model.train()
        train_losses = []
        for batch in train_loader:
            inputs = [b.to(device) for b in batch[:-1]]
            targets = batch[-1].to(device)
            optimizer.zero_grad()
            preds = model(*inputs)
            loss = F.mse_loss(preds, targets)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            train_losses.append(loss.item())

        model.eval()
        val_losses = []
        with torch.no_grad():
            for batch in val_loader:
                inputs = [b.to(device) for b in batch[:-1]]
                targets = batch[-1].to(device)
                preds = model(*inputs)
                val_losses.append(F.mse_loss(preds, targets).item())

        val_loss = np.mean(val_losses)
        scheduler.step(val_loss)

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_state = {k: v.cpu().clone()
                          for k, v in model.state_dict().items()}
            wait = 0
        else:
            wait += 1
            if wait >= patience:
                break

    if best_state:
        model.load_state_dict(best_state)
    return model


def evaluate_model(model, val_loader, device, horizons, scale=GLUCOSE_SCALE):
    model.eval()
    all_preds, all_targets = [], []
    with torch.no_grad():
        for batch in val_loader:
            inputs = [b.to(device) for b in batch[:-1]]
            targets = batch[-1].to(device)
            preds = model(*inputs)
            all_preds.append(preds.cpu().numpy())
            all_targets.append(targets.cpu().numpy())

    preds = np.concatenate(all_preds)
    targets = np.concatenate(all_targets)

    per_horizon = {}
    for i, name in enumerate(horizons.keys()):
        mae = float(np.mean(np.abs(preds[:, i] - targets[:, i])) * scale)
        per_horizon[name] = mae

    return {
        'mae_overall': float(np.mean(list(per_horizon.values()))),
        'mae_per_horizon': per_horizon,
    }, preds, targets


# ─── Feature Preparation ───

def prepare_features(base_train, base_val, pk_train, pk_val,
                     history_steps, horizons, use_8ch=True, use_future_pk=True,
                     use_isf=False, isf_train=None, isf_val=None):
    n_horizons = len(horizons)
    max_horizon = max(horizons.values())

    # Targets — glucose already 0-1 from build_nightscout_grid
    targets_train = extract_targets(base_train, history_steps, horizons)
    targets_val = extract_targets(base_val, history_steps, horizons)

    glucose_t = base_train[:, :history_steps, 0:1].copy()
    glucose_v = base_val[:, :history_steps, 0:1].copy()

    if use_isf and isf_train is not None:
        isf_factor_t = (GLUCOSE_SCALE / isf_train).reshape(-1, 1, 1)
        isf_factor_v = (GLUCOSE_SCALE / isf_val).reshape(-1, 1, 1)
        glucose_t = glucose_t * isf_factor_t
        glucose_v = glucose_v * isf_factor_v
        targets_train = targets_train * (GLUCOSE_SCALE / isf_train).reshape(-1, 1)
        targets_val = targets_val * (GLUCOSE_SCALE / isf_val).reshape(-1, 1)
        np.clip(glucose_t, 0, 10, out=glucose_t)
        np.clip(glucose_v, 0, 10, out=glucose_v)

    if use_8ch:
        hist_t = base_train[:, :history_steps].copy()
        hist_v = base_val[:, :history_steps].copy()
        hist_t[:, :, 0:1] = glucose_t
        hist_v[:, :, 0:1] = glucose_v
    else:
        hist_t = glucose_t
        hist_v = glucose_v

    has_future = use_future_pk
    if use_future_pk:
        future_t = np.stack([
            pk_train[:, history_steps:history_steps + max_horizon, idx] / PK_NORMS[idx]
            for idx in FUTURE_PK_INDICES
        ], axis=2)
        future_v = np.stack([
            pk_val[:, history_steps:history_steps + max_horizon, idx] / PK_NORMS[idx]
            for idx in FUTURE_PK_INDICES
        ], axis=2)
    else:
        future_t, future_v = None, None

    return (hist_t, hist_v, future_t, future_v,
            targets_train, targets_val, has_future)


def to_tensors(hist_t, hist_v, future_t, future_v, targets_t, targets_v,
               has_future):
    if has_future:
        train_ds = TensorDataset(
            torch.from_numpy(hist_t.astype(np.float32)),
            torch.from_numpy(future_t.astype(np.float32)),
            torch.from_numpy(targets_t.astype(np.float32)))
        val_ds = TensorDataset(
            torch.from_numpy(hist_v.astype(np.float32)),
            torch.from_numpy(future_v.astype(np.float32)),
            torch.from_numpy(targets_v.astype(np.float32)))
    else:
        train_ds = TensorDataset(
            torch.from_numpy(hist_t.astype(np.float32)),
            torch.from_numpy(targets_t.astype(np.float32)))
        val_ds = TensorDataset(
            torch.from_numpy(hist_v.astype(np.float32)),
            torch.from_numpy(targets_v.astype(np.float32)))
    return train_ds, val_ds


# ─── Experiment Runners ───

def _run_variant(name, model, train_loader, val_loader, device, horizons,
                 train_kw, scale=GLUCOSE_SCALE):
    """Run a single variant: train + evaluate, print results."""
    t0 = time.time()
    n_params = sum(p.numel() for p in model.parameters())
    model = train_model(model, train_loader, val_loader, device, **train_kw)
    res, preds, targets = evaluate_model(model, val_loader, device, horizons,
                                         scale=scale)
    elapsed = time.time() - t0
    h_str = ', '.join(f"{k}={v:.1f}"
                      for k, v in res['mae_per_horizon'].items())
    print(f"    {name}... MAE={res['mae_overall']:.1f} [{h_str}]"
          f"  ({n_params:,} params, {elapsed:.0f}s)")
    res['n_params'] = n_params
    return res, model


def run_exp_369(args, seeds=None, train_kw=None, max_patients=None):
    """EXP-369: Dilated ResNet — combining ResNet depth + dilated multi-scale.

    Variants:
    1. resnet_baseline — standard ResNet (EXP-368 champion) for reference
    2. dilated_resnet — ResNet stem + dilated blocks + ResNet tail
    3. dilated_resnet_isf — same with ISF normalization
    4. dilated_resnet_deep — wider hidden (192) + more dilations (1..32)
    """
    device = torch.device(args.device)
    seeds = seeds or SEEDS
    train_kw = train_kw or {}
    quick = max_patients is not None
    horizons = HORIZONS_STANDARD if quick else HORIZONS_EXTENDED
    n_horizons = len(horizons)
    max_horizon = max(horizons.values())
    history_steps = 72

    data = load_forecast_data(args.patients_dir, history_steps, max_horizon,
                              max_patients, load_isf=True)
    base_t, base_v, pk_t, pk_v, isf_t, isf_v, per_patient = data

    results = {
        'experiment': 'EXP-369',
        'description': 'Dilated ResNet: ResNet depth + dilated multi-scale',
        'horizons': list(horizons.keys()),
        'variants': {},
    }

    for seed in seeds:
        print(f"\n  seed={seed}:")
        torch.manual_seed(seed)
        np.random.seed(seed)

        # Non-ISF features
        feat = prepare_features(base_t, base_v, pk_t, pk_v, history_steps,
                                horizons, use_8ch=True, use_future_pk=True)
        hist_t, hist_v, fut_t, fut_v, tgt_t, tgt_v, has_fut = feat
        train_ds, val_ds = to_tensors(hist_t, hist_v, fut_t, fut_v,
                                      tgt_t, tgt_v, has_fut)
        tl = DataLoader(train_ds, batch_size=256, shuffle=True)
        vl = DataLoader(val_ds, batch_size=256)

        # ISF features
        feat_isf = prepare_features(base_t, base_v, pk_t, pk_v, history_steps,
                                    horizons, use_8ch=True, use_future_pk=True,
                                    use_isf=True, isf_train=isf_t, isf_val=isf_v)
        hist_ti, hist_vi, fut_ti, fut_vi, tgt_ti, tgt_vi, _ = feat_isf
        train_ds_i, val_ds_i = to_tensors(hist_ti, hist_vi, fut_ti, fut_vi,
                                          tgt_ti, tgt_vi, True)
        tl_i = DataLoader(train_ds_i, batch_size=256, shuffle=True)
        vl_i = DataLoader(val_ds_i, batch_size=256)

        in_ch = hist_t.shape[2]

        # 1. ResNet baseline (reference)
        torch.manual_seed(seed)
        model = ResNetCNNWithFuture(in_ch, 4, n_horizons)
        res, _ = _run_variant('resnet_baseline', model, tl, vl, device,
                              horizons, train_kw)
        results['variants'][f'resnet_baseline_s{seed}'] = res

        # 2. Dilated ResNet (standard: hidden=128, dilations=1,2,4,8,16)
        torch.manual_seed(seed)
        model = DilatedResNetWithFuture(in_ch, 4, n_horizons, hidden=128,
                                        dilations=(1, 2, 4, 8, 16))
        res, _ = _run_variant('dilated_resnet', model, tl, vl, device,
                              horizons, train_kw)
        results['variants'][f'dilated_resnet_s{seed}'] = res

        # 3. Dilated ResNet + ISF
        torch.manual_seed(seed)
        model = DilatedResNetWithFuture(in_ch, 4, n_horizons, hidden=128,
                                        dilations=(1, 2, 4, 8, 16))
        res, _ = _run_variant('dilated_resnet_isf', model, tl_i, vl_i,
                              device, horizons, train_kw)
        results['variants'][f'dilated_resnet_isf_s{seed}'] = res

        # 4. Dilated ResNet Deep (hidden=192, dilations=1..32)
        torch.manual_seed(seed)
        model = DilatedResNetWithFuture(in_ch, 4, n_horizons, hidden=192,
                                        dilations=(1, 2, 4, 8, 16, 32))
        res, _ = _run_variant('dilated_resnet_deep', model, tl, vl, device,
                              horizons, train_kw)
        results['variants'][f'dilated_resnet_deep_s{seed}'] = res

    results['summary'] = _aggregate_results(results['variants'], seeds,
                                            horizons)
    return results


def run_exp_370(args, seeds=None, train_kw=None, max_patients=None):
    """EXP-370: ResNet + Horizon-Conditioned FiLM.

    Variants:
    1. resnet_shared_head — standard ResNet (shared head across horizons)
    2. resnet_film — ResNet + per-horizon FiLM modulation
    3. resnet_film_isf — same with ISF normalization
    4. resnet_film_future — ResNet + FiLM + future PK
    """
    device = torch.device(args.device)
    seeds = seeds or SEEDS
    train_kw = train_kw or {}
    quick = max_patients is not None
    horizons = HORIZONS_STANDARD if quick else HORIZONS_EXTENDED
    n_horizons = len(horizons)
    max_horizon = max(horizons.values())
    history_steps = 72

    data = load_forecast_data(args.patients_dir, history_steps, max_horizon,
                              max_patients, load_isf=True)
    base_t, base_v, pk_t, pk_v, isf_t, isf_v, per_patient = data

    results = {
        'experiment': 'EXP-370',
        'description': 'ResNet + horizon-conditioned FiLM modulation',
        'horizons': list(horizons.keys()),
        'variants': {},
    }

    for seed in seeds:
        print(f"\n  seed={seed}:")
        torch.manual_seed(seed)
        np.random.seed(seed)

        # Non-ISF with future
        feat = prepare_features(base_t, base_v, pk_t, pk_v, history_steps,
                                horizons, use_8ch=True, use_future_pk=True)
        hist_t, hist_v, fut_t, fut_v, tgt_t, tgt_v, has_fut = feat
        train_ds, val_ds = to_tensors(hist_t, hist_v, fut_t, fut_v,
                                      tgt_t, tgt_v, has_fut)
        tl = DataLoader(train_ds, batch_size=256, shuffle=True)
        vl = DataLoader(val_ds, batch_size=256)

        # Non-ISF without future (for history-only FiLM)
        feat_nf = prepare_features(base_t, base_v, pk_t, pk_v, history_steps,
                                   horizons, use_8ch=True, use_future_pk=False)
        hist_t_nf, hist_v_nf, _, _, tgt_t_nf, tgt_v_nf, _ = feat_nf
        train_ds_nf, val_ds_nf = to_tensors(hist_t_nf, hist_v_nf, None, None,
                                            tgt_t_nf, tgt_v_nf, False)
        tl_nf = DataLoader(train_ds_nf, batch_size=256, shuffle=True)
        vl_nf = DataLoader(val_ds_nf, batch_size=256)

        # ISF with future
        feat_isf = prepare_features(base_t, base_v, pk_t, pk_v, history_steps,
                                    horizons, use_8ch=True, use_future_pk=True,
                                    use_isf=True, isf_train=isf_t, isf_val=isf_v)
        hist_ti, hist_vi, fut_ti, fut_vi, tgt_ti, tgt_vi, _ = feat_isf
        train_ds_i, val_ds_i = to_tensors(hist_ti, hist_vi, fut_ti, fut_vi,
                                          tgt_ti, tgt_vi, True)
        tl_i = DataLoader(train_ds_i, batch_size=256, shuffle=True)
        vl_i = DataLoader(val_ds_i, batch_size=256)

        in_ch = hist_t.shape[2]

        # 1. ResNet shared head (reference)
        torch.manual_seed(seed)
        model = ResNetCNNWithFuture(in_ch, 4, n_horizons)
        res, _ = _run_variant('resnet_shared', model, tl, vl, device,
                              horizons, train_kw)
        results['variants'][f'resnet_shared_s{seed}'] = res

        # 2. ResNet FiLM (history-only — tests FiLM without future PK)
        torch.manual_seed(seed)
        model = ResNetFiLM(in_ch, n_horizons)
        res, _ = _run_variant('resnet_film_hist', model, tl_nf, vl_nf,
                              device, horizons, train_kw)
        results['variants'][f'resnet_film_hist_s{seed}'] = res

        # 3. ResNet FiLM + future PK
        torch.manual_seed(seed)
        model = ResNetFiLMWithFuture(in_ch, 4, n_horizons)
        res, _ = _run_variant('resnet_film_future', model, tl, vl, device,
                              horizons, train_kw)
        results['variants'][f'resnet_film_future_s{seed}'] = res

        # 4. ResNet FiLM + ISF + future PK
        torch.manual_seed(seed)
        model = ResNetFiLMWithFuture(in_ch, 4, n_horizons)
        res, _ = _run_variant('resnet_film_isf_ft', model, tl_i, vl_i,
                              device, horizons, train_kw)
        results['variants'][f'resnet_film_isf_ft_s{seed}'] = res

    results['summary'] = _aggregate_results(results['variants'], seeds,
                                            horizons)
    return results


def run_exp_371(args, seeds=None, train_kw=None, max_patients=None):
    """EXP-371: Per-Patient Fine-Tuning.

    Train a global ResNet model on all patients, then fine-tune the
    last 2 layers (head) per-patient for 10 epochs with low learning rate.

    Variants:
    1. global_only — trained on all patients (baseline)
    2. finetune_head — global model + fine-tune head per patient
    3. finetune_last_block — global model + fine-tune last ResBlock + head
    """
    device = torch.device(args.device)
    seeds = seeds or SEEDS
    train_kw = train_kw or {}
    quick = max_patients is not None
    horizons = HORIZONS_STANDARD if quick else HORIZONS_EXTENDED
    n_horizons = len(horizons)
    max_horizon = max(horizons.values())
    history_steps = 72
    ft_epochs = 10 if not quick else 5
    ft_lr = 1e-4

    data = load_forecast_data(args.patients_dir, history_steps, max_horizon,
                              max_patients, load_isf=True)
    base_t, base_v, pk_t, pk_v, isf_t, isf_v, per_patient = data

    results = {
        'experiment': 'EXP-371',
        'description': 'Per-patient fine-tuning of global ResNet model',
        'horizons': list(horizons.keys()),
        'variants': {},
    }

    feat = prepare_features(base_t, base_v, pk_t, pk_v, history_steps,
                            horizons, use_8ch=True, use_future_pk=True)
    hist_t, hist_v, fut_t, fut_v, tgt_t, tgt_v, has_fut = feat

    for seed in seeds:
        print(f"\n  seed={seed}:")
        torch.manual_seed(seed)
        np.random.seed(seed)

        # Full dataset loaders
        train_ds, val_ds = to_tensors(hist_t, hist_v, fut_t, fut_v,
                                      tgt_t, tgt_v, has_fut)
        tl = DataLoader(train_ds, batch_size=256, shuffle=True)
        vl = DataLoader(val_ds, batch_size=256)

        in_ch = hist_t.shape[2]

        # 1. Train global model
        torch.manual_seed(seed)
        global_model = ResNetCNNWithFuture(in_ch, 4, n_horizons)
        res_global, global_model = _run_variant(
            'global_only', global_model, tl, vl, device, horizons, train_kw)
        results['variants'][f'global_only_s{seed}'] = res_global

        # Save global state for fine-tuning
        global_state = {k: v.cpu().clone()
                        for k, v in global_model.state_dict().items()}

        # 2 & 3. Per-patient fine-tuning
        for ft_name, freeze_pattern in [
            ('finetune_head', 'head'),
            ('finetune_last_block', 'head+last_block'),
        ]:
            all_preds_ft = []
            all_tgts_ft = []

            for pi in per_patient:
                vs = pi['val_start']
                vc = pi['val_count']
                ts = pi['train_start']
                tc = pi['train_count']

                if vc == 0 or tc == 0:
                    continue

                # Get this patient's data
                p_hist_t = hist_t[ts:ts + tc]
                p_fut_t = fut_t[ts:ts + tc]
                p_tgt_t = tgt_t[ts:ts + tc]
                p_hist_v = hist_v[vs:vs + vc]
                p_fut_v = fut_v[vs:vs + vc]
                p_tgt_v = tgt_v[vs:vs + vc]

                p_train_ds, p_val_ds = to_tensors(
                    p_hist_t, p_hist_v, p_fut_t, p_fut_v,
                    p_tgt_t, p_tgt_v, True)
                p_tl = DataLoader(p_train_ds, batch_size=64, shuffle=True)
                p_vl = DataLoader(p_val_ds, batch_size=64)

                # Load global weights
                ft_model = ResNetCNNWithFuture(in_ch, 4, n_horizons)
                ft_model.load_state_dict(global_state)
                ft_model.to(device)

                # Freeze appropriate layers
                for name, param in ft_model.named_parameters():
                    if freeze_pattern == 'head':
                        param.requires_grad = 'head' in name
                    elif freeze_pattern == 'head+last_block':
                        param.requires_grad = ('head' in name or
                                               'hist_blocks.2' in name)

                optimizer = torch.optim.Adam(
                    filter(lambda p: p.requires_grad, ft_model.parameters()),
                    lr=ft_lr)

                # Fine-tune
                for ep in range(ft_epochs):
                    ft_model.train()
                    for batch in p_tl:
                        inputs = [b.to(device) for b in batch[:-1]]
                        targets = batch[-1].to(device)
                        optimizer.zero_grad()
                        preds = ft_model(*inputs)
                        loss = F.mse_loss(preds, targets)
                        loss.backward()
                        optimizer.step()

                # Evaluate this patient
                ft_model.eval()
                with torch.no_grad():
                    for batch in p_vl:
                        inputs = [b.to(device) for b in batch[:-1]]
                        targets = batch[-1]
                        preds = ft_model(*inputs).cpu()
                        all_preds_ft.append(preds.numpy())
                        all_tgts_ft.append(targets.numpy())

            # Aggregate across patients
            all_preds_ft = np.concatenate(all_preds_ft)
            all_tgts_ft = np.concatenate(all_tgts_ft)

            per_horizon = {}
            for i, name in enumerate(horizons.keys()):
                mae = float(np.mean(np.abs(
                    all_preds_ft[:, i] - all_tgts_ft[:, i])) * GLUCOSE_SCALE)
                per_horizon[name] = mae

            res_ft = {
                'mae_overall': float(np.mean(list(per_horizon.values()))),
                'mae_per_horizon': per_horizon,
                'n_params': sum(p.numel() for p in global_model.parameters()),
            }

            h_str = ', '.join(f"{k}={v:.1f}"
                              for k, v in per_horizon.items())
            print(f"    {ft_name}... MAE={res_ft['mae_overall']:.1f} "
                  f"[{h_str}]  (ft_epochs={ft_epochs})")
            results['variants'][f'{ft_name}_s{seed}'] = res_ft

    results['summary'] = _aggregate_results(results['variants'], seeds,
                                            horizons)
    return results


def run_exp_372(args, seeds=None, train_kw=None, max_patients=None):
    """EXP-372: History Window Scaling with ResNet.

    Test whether ResNet's larger capacity exploits longer history windows.
    EXP-353 showed PK crossover at 4h (48 steps). ResNet (240K params)
    may extract more from 9h or 12h windows.

    Variants (all use 8ch + future PK):
    1. history_6h (72 steps) — baseline, matches EXP-368
    2. history_9h (108 steps) — 50% more history
    3. history_12h (144 steps) — 2× history, full DIA visible
    """
    device = torch.device(args.device)
    seeds = seeds or SEEDS
    train_kw = train_kw or {}
    quick = max_patients is not None
    horizons = HORIZONS_STANDARD if quick else HORIZONS_EXTENDED
    n_horizons = len(horizons)
    max_horizon = max(horizons.values())

    history_configs = [
        ('history_6h', 72),
        ('history_9h', 108),
        ('history_12h', 144),
    ]

    results = {
        'experiment': 'EXP-372',
        'description': 'History window scaling with ResNet architecture',
        'horizons': list(horizons.keys()),
        'variants': {},
    }

    for h_name, history_steps in history_configs:
        print(f"\n  --- {h_name} ({history_steps} steps) ---")
        # Need larger window for longer history
        total_window = history_steps + max_horizon
        data = load_forecast_data(args.patients_dir, history_steps,
                                  max_horizon, max_patients)
        base_t, base_v, pk_t, pk_v, _, _, per_patient = data

        feat = prepare_features(base_t, base_v, pk_t, pk_v, history_steps,
                                horizons, use_8ch=True, use_future_pk=True)
        hist_t, hist_v, fut_t, fut_v, tgt_t, tgt_v, has_fut = feat
        in_ch = hist_t.shape[2]

        for seed in seeds:
            print(f"\n  seed={seed}:")
            torch.manual_seed(seed)
            np.random.seed(seed)

            train_ds, val_ds = to_tensors(hist_t, hist_v, fut_t, fut_v,
                                          tgt_t, tgt_v, has_fut)
            tl = DataLoader(train_ds, batch_size=256, shuffle=True)
            vl = DataLoader(val_ds, batch_size=256)

            model = ResNetCNNWithFuture(in_ch, 4, n_horizons)
            res, _ = _run_variant(h_name, model, tl, vl, device,
                                  horizons, train_kw)
            results['variants'][f'{h_name}_s{seed}'] = res

    results['summary'] = _aggregate_results(results['variants'], seeds,
                                            horizons)
    return results


# ─── Aggregation ───

def _aggregate_results(variants, seeds, horizons):
    grouped = defaultdict(list)
    for key, res in variants.items():
        parts = key.rsplit('_s', 1)
        variant = parts[0]
        grouped[variant].append(res)

    summary = {}
    for variant, runs in grouped.items():
        overall_maes = [r['mae_overall'] for r in runs]
        per_h = {}
        for hname in horizons:
            vals = [r['mae_per_horizon'].get(hname, float('nan'))
                    for r in runs]
            per_h[hname] = {
                'mean': float(np.mean(vals)),
                'std': float(np.std(vals)),
            }
        summary[variant] = {
            'mae_overall_mean': float(np.mean(overall_maes)),
            'mae_overall_std': float(np.std(overall_maes)),
            'mae_per_horizon': per_h,
            'n_seeds': len(runs),
        }
    return summary


# ─── CLI ───

def save_results(results, experiment_id):
    out_dir = Path('externals/experiments')
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{experiment_id}.json"
    with open(path, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nSaved: {path}")
    return path


def main():
    parser = argparse.ArgumentParser(
        description='EXP-369-372: Combined best & scaling experiments')
    parser.add_argument('--experiment', type=str, default='369',
                        help='Experiment: 369, 370, 371, 372, or all')
    parser.add_argument('--device', type=str, default='cpu')
    parser.add_argument('--quick', action='store_true',
                        help='Quick mode: 1 seed, 4 patients, 30 epochs')
    parser.add_argument('--patients-dir', type=str,
                        default='externals/ns-data/patients')
    args = parser.parse_args()

    experiments = {
        '369': ('exp369_dilated_resnet', run_exp_369),
        '370': ('exp370_resnet_film', run_exp_370),
        '371': ('exp371_finetune', run_exp_371),
        '372': ('exp372_history_scale', run_exp_372),
    }

    if args.quick:
        seeds = SEEDS_QUICK
        train_kw = {'epochs': QUICK_EPOCHS, 'patience': QUICK_PATIENCE}
        max_patients = QUICK_PATIENTS
    else:
        seeds = SEEDS
        train_kw = {'epochs': 60, 'patience': 15}
        max_patients = None

    to_run = (list(experiments.keys()) if args.experiment == 'all'
              else [args.experiment])

    for exp_id in to_run:
        if exp_id not in experiments:
            print(f"Unknown experiment: {exp_id}")
            continue
        name, runner = experiments[exp_id]
        print(f"\n{'='*60}")
        print(f"{name}")
        print(f"{'='*60}")
        results = runner(args, seeds=seeds, train_kw=train_kw,
                         max_patients=max_patients)
        save_results(results, name)

        if 'summary' in results:
            print(f"\n─── Summary ───")
            for variant, stats in results['summary'].items():
                h_str = ', '.join(
                    f"{k}={v['mean']:.1f}±{v['std']:.1f}"
                    for k, v in stats['mae_per_horizon'].items())
                print(f"  {variant}: MAE={stats['mae_overall_mean']:.1f}"
                      f"±{stats['mae_overall_std']:.1f} [{h_str}]")


if __name__ == '__main__':
    main()
