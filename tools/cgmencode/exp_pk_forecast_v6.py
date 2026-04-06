#!/usr/bin/env python3
"""EXP-373 through EXP-377: Combination & Novel Architecture Experiments

Building on validated results:
  - EXP-368 ResNet ISF: 35.8±0.1 (full-scale champion, 11pt/3seed)
  - EXP-369 Dilated ResNet: 27.1 quick (-1.8 vs ResNet baseline)
  - EXP-371 Fine-tuning: 27.2 quick (-1.2 vs global_only)
  - EXP-370 FiLM: 27.5 quick (-1.4 vs shared head)
  - Future PK: foundational breakthrough (-6.4 overall at full scale)

  CLINICAL METRICS NOTE (2026-04-06):
  evaluate_model() now automatically reports MARD, Clarke zones, ISO 15197,
  bias, trend accuracy, and range-stratified MARD (hypo/euglycemic/hyper)
  via compute_clinical_forecast_metrics() from metrics.py. All new experiments
  will have clinical scoring in their result JSONs. See rescore_forecasts.py
  to re-score existing results.

  ⚡ ERA 2 → ERA 3 PERFORMANCE GAP (from evidence synthesis report §1.5):
  ERA 2 forecasters (EXP-043–171) achieve MARD≈8% at 1hr = CGM-grade accuracy.
  ERA 3 (EXP-352+) gets MARD≈17% at the same 1hr horizon — a 2.2× regression.
  Data leakage ruled out (EXP-046: random vs temporal = 0.2 mg/dL difference).
  Root causes: (1) no per-patient fine-tuning, (2) CNN vs Transformer,
  (3) multi-horizon objective dilutes short-horizon accuracy.

  Your EXP-371 (fine-tuning) and EXP-373 (stacked best) directly address
  causes (1) and partially (3). Key suggestion: after EXP-373, try adding a
  1hr-only evaluation alongside multi-horizon to track whether the gap closes.
  Also consider: ERA 2 used 4-layer GroupedEncoder (transformer) — the
  EXP-375 attention experiment may recapture that architecture's advantage.

  The classification thread is handling ISF-norm, functional depth, and
  glucodensity experiments (EXP-369, 371, 372 from normalization runner).
  No overlap with your forecasting focus.

EXP-373 — Stacked Best Techniques
  Combine dilated ResNet + ISF normalization + per-patient fine-tuning.
  These won independently in quick mode — do they stack?
  Hypothesis: Combined should beat any individual technique.

EXP-374 — Dual-Encoder Architecture (GluPredKit-inspired)
  Separate CNN encoders for glucose history vs PK/treatment features,
  fused late via concatenation. Prevents cross-signal interference.
  Hypothesis: Dedicated encoders > shared encoder for heterogeneous signals.

EXP-375 — Temporal Self-Attention over ResNet Features
  ResNet backbone → multi-head self-attention → horizon projection.
  Attention learns which temporal positions matter per horizon.
  Hypothesis: Attention helps long horizons (h360+) where distant context matters.

EXP-376 — Overlapping Windows for Longer History
  Fix EXP-372 data scarcity: use fixed stride=36 instead of history//2.
  With adequate training data, test if longer history (9h, 12h) helps.
  Hypothesis: Data scarcity, not history length, caused EXP-372 failure.

EXP-377 — Heteroscedastic Uncertainty Estimation
  Predict mean + log_variance per horizon. Aleatoric uncertainty.
  Gaussian NLL loss trains both. No extra inference cost.
  Hypothesis: Knowing WHEN predictions are uncertain has clinical value.

Usage:
    python tools/cgmencode/exp_pk_forecast_v6.py --experiment 373 --device cuda --quick
    python tools/cgmencode/exp_pk_forecast_v6.py --experiment all --device cuda
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
from cgmencode.metrics import compute_clinical_forecast_metrics

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
FUTURE_PK_INDICES = [1, 2, 3, 6]  # insulin_net, carb_rate, net_balance, net_effect

# ─── Data Loading ───

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
                       max_patients=None, load_isf=False, stride=None):
    """Load base + PK features with configurable stride for window extraction."""
    patient_dirs = find_patient_dirs(patients_dir)
    if max_patients:
        patient_dirs = patient_dirs[:max_patients]
    print(f"Loading {len(patient_dirs)} patients "
          f"(history={history_steps}, horizon={max_horizon})")

    all_base_train, all_base_val = [], []
    all_pk_train, all_pk_val = [], []
    all_isf_train, all_isf_val = [], []
    per_patient = []
    window_size = history_steps + max_horizon

    if stride is None:
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
        print(f"  {name}: {n} windows ({len(bt)} train, {len(bv)} val)"
              f"  [stride={stride}]")
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


# ─── Model Building Blocks ───

class ResBlock1d(nn.Module):
    def __init__(self, in_ch, out_ch, dropout=0.1):
        super().__init__()
        self.conv1 = nn.Conv1d(in_ch, out_ch, 3, padding=1)
        self.bn1 = nn.BatchNorm1d(out_ch)
        self.conv2 = nn.Conv1d(out_ch, out_ch, 3, padding=1)
        self.bn2 = nn.BatchNorm1d(out_ch)
        self.skip = nn.Conv1d(in_ch, out_ch, 1) if in_ch != out_ch else nn.Identity()
        self.drop = nn.Dropout(dropout)

    def forward(self, x):
        residual = self.skip(x)
        h = F.relu(self.bn1(self.conv1(x)))
        h = self.drop(h)
        h = self.bn2(self.conv2(h))
        return F.relu(h + residual)


class DilatedResBlock(nn.Module):
    """ResBlock with dilated convolutions for multi-scale temporal coverage."""
    def __init__(self, in_ch, out_ch, dilation=1, dropout=0.1):
        super().__init__()
        self.conv1 = nn.Conv1d(in_ch, out_ch, 3, padding=dilation, dilation=dilation)
        self.bn1 = nn.BatchNorm1d(out_ch)
        self.conv2 = nn.Conv1d(out_ch, out_ch, 3, padding=dilation, dilation=dilation)
        self.bn2 = nn.BatchNorm1d(out_ch)
        self.skip = nn.Conv1d(in_ch, out_ch, 1) if in_ch != out_ch else nn.Identity()
        self.drop = nn.Dropout(dropout)

    def forward(self, x):
        residual = self.skip(x)
        h = F.relu(self.bn1(self.conv1(x)))
        h = self.drop(h)
        h = self.bn2(self.conv2(h))
        return F.relu(h + residual)


# ─── Models ───

class DilatedResNetWithFuture(nn.Module):
    """Dilated ResNet with future PK branch (from v5, EXP-369 champion)."""
    def __init__(self, hist_channels, pk_channels, n_horizons=8, dropout=0.1):
        super().__init__()
        self.hist_stem = nn.Sequential(
            nn.Conv1d(hist_channels, 64, kernel_size=5, padding=2),
            nn.ReLU(), nn.BatchNorm1d(64),
        )
        self.hist_blocks = nn.Sequential(
            DilatedResBlock(64, 128, dilation=1, dropout=dropout),
            DilatedResBlock(128, 128, dilation=2, dropout=dropout),
            DilatedResBlock(128, 128, dilation=4, dropout=dropout),
            DilatedResBlock(128, 64, dilation=8, dropout=dropout),
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


class ResNetCNNWithFuture(nn.Module):
    """Standard ResNet + future PK (from v4, baseline reference)."""
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


class DualEncoderWithFuture(nn.Module):
    """Separate encoders for glucose vs PK/treatment features.

    Inspired by GluPredKit's dual-LSTM approach, but using CNNs.
    Glucose encoder: deep ResNet on glucose channel only
    Treatment encoder: ResNet on PK history channels
    Future encoder: CNN on projected PK channels
    Late fusion: concatenate all embeddings → head
    """
    def __init__(self, pk_hist_channels, pk_future_channels,
                 n_horizons=8, dropout=0.1):
        super().__init__()
        # Glucose-only encoder (deep, dedicated)
        self.glucose_stem = nn.Sequential(
            nn.Conv1d(1, 48, kernel_size=7, padding=3),
            nn.ReLU(), nn.BatchNorm1d(48),
        )
        self.glucose_blocks = nn.Sequential(
            ResBlock1d(48, 96, dropout=dropout),
            ResBlock1d(96, 96, dropout=dropout),
            ResBlock1d(96, 48, dropout=dropout),
        )
        self.glucose_pool = nn.AdaptiveAvgPool1d(1)

        # PK/treatment history encoder
        self.pk_stem = nn.Sequential(
            nn.Conv1d(pk_hist_channels, 32, kernel_size=5, padding=2),
            nn.ReLU(), nn.BatchNorm1d(32),
        )
        self.pk_blocks = nn.Sequential(
            ResBlock1d(32, 64, dropout=dropout),
            ResBlock1d(64, 32, dropout=dropout),
        )
        self.pk_pool = nn.AdaptiveAvgPool1d(1)

        # Future PK encoder
        self.future_conv = nn.Sequential(
            nn.Conv1d(pk_future_channels, 32, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(32),
            nn.Conv1d(32, 32, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(32),
            nn.AdaptiveAvgPool1d(1),
        )

        # Late fusion head
        self.head = nn.Sequential(
            nn.Linear(48 + 32 + 32, 64), nn.ReLU(), nn.Dropout(dropout),
            nn.Linear(64, n_horizons),
        )

    def forward(self, x_glucose, x_pk_hist, x_future):
        g = x_glucose.permute(0, 2, 1)
        g = self.glucose_stem(g)
        g = self.glucose_blocks(g)
        g_feat = self.glucose_pool(g).squeeze(-1)

        p = x_pk_hist.permute(0, 2, 1)
        p = self.pk_stem(p)
        p = self.pk_blocks(p)
        p_feat = self.pk_pool(p).squeeze(-1)

        f = x_future.permute(0, 2, 1)
        f_feat = self.future_conv(f).squeeze(-1)

        return self.head(torch.cat([g_feat, p_feat, f_feat], dim=1))


class ResNetWithAttention(nn.Module):
    """ResNet backbone → temporal self-attention → horizon projection.

    Multi-head self-attention over the temporal feature map from ResNet.
    Attention learns which time positions matter for each prediction.
    """
    def __init__(self, hist_channels, pk_channels, n_horizons=8,
                 n_heads=4, dropout=0.1):
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
        # Self-attention over temporal dim (64-d features at each position)
        self.attn = nn.MultiheadAttention(64, n_heads, dropout=dropout,
                                          batch_first=True)
        self.attn_norm = nn.LayerNorm(64)
        self.attn_pool = nn.AdaptiveAvgPool1d(1)

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
        h = x_hist.permute(0, 2, 1)  # (B, C, T)
        h = self.hist_stem(h)
        h = self.hist_blocks(h)  # (B, 64, T)

        # Self-attention: (B, T, 64)
        h_t = h.permute(0, 2, 1)
        h_attn, _ = self.attn(h_t, h_t, h_t)
        h_t = self.attn_norm(h_t + h_attn)  # residual connection
        h = h_t.permute(0, 2, 1)  # back to (B, 64, T)
        h_feat = self.attn_pool(h).squeeze(-1)

        f = x_future.permute(0, 2, 1)
        f_feat = self.future_conv(f).squeeze(-1)
        return self.head(torch.cat([h_feat, f_feat], dim=1))


class HeteroscedasticResNet(nn.Module):
    """ResNet that predicts mean + log_variance for uncertainty estimation.

    Trained with Gaussian NLL loss. Predicts aleatoric uncertainty.
    """
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
        self.shared = nn.Sequential(
            nn.Linear(64 + 32, 64), nn.ReLU(), nn.Dropout(dropout),
        )
        self.mean_head = nn.Linear(64, n_horizons)
        self.logvar_head = nn.Linear(64, n_horizons)

    def forward(self, x_hist, x_future):
        h = x_hist.permute(0, 2, 1)
        h = self.hist_stem(h)
        h = self.hist_blocks(h)
        h_feat = self.hist_pool(h).squeeze(-1)
        f = x_future.permute(0, 2, 1)
        f_feat = self.future_conv(f).squeeze(-1)
        shared = self.shared(torch.cat([h_feat, f_feat], dim=1))
        return self.mean_head(shared), self.logvar_head(shared)


# ─── Training ───

def train_model(model, train_loader, val_loader, device, epochs=60,
                patience=15, lr=1e-3, loss_fn='mse'):
    model.to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, patience=5, factor=0.5)

    is_hetero = (loss_fn == 'gaussian_nll')
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

            if is_hetero:
                mean, logvar = model(*inputs)
                # Gaussian NLL: 0.5 * (logvar + (target - mean)^2 / exp(logvar))
                logvar = torch.clamp(logvar, -6, 6)
                loss = 0.5 * torch.mean(logvar + (targets - mean) ** 2 / torch.exp(logvar))
            else:
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
                if is_hetero:
                    mean, logvar = model(*inputs)
                    logvar = torch.clamp(logvar, -6, 6)
                    vl = 0.5 * torch.mean(logvar + (targets - mean) ** 2 / torch.exp(logvar))
                else:
                    preds = model(*inputs)
                    vl = F.mse_loss(preds, targets)
                val_losses.append(vl.item())

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


def evaluate_model(model, val_loader, device, horizons, scale=GLUCOSE_SCALE,
                   is_hetero=False):
    model.eval()
    all_preds, all_targets = [], []
    all_logvars = []
    with torch.no_grad():
        for batch in val_loader:
            inputs = [b.to(device) for b in batch[:-1]]
            targets = batch[-1].to(device)
            if is_hetero:
                mean, logvar = model(*inputs)
                all_preds.append(mean.cpu().numpy())
                all_logvars.append(logvar.cpu().numpy())
            else:
                preds = model(*inputs)
                all_preds.append(preds.cpu().numpy())
            all_targets.append(targets.cpu().numpy())

    preds = np.concatenate(all_preds)
    targets = np.concatenate(all_targets)

    per_horizon = {}
    for i, name in enumerate(horizons.keys()):
        mae = float(np.mean(np.abs(preds[:, i] - targets[:, i])) * scale)
        per_horizon[name] = mae

    result = {
        'mae_overall': float(np.mean(list(per_horizon.values()))),
        'mae_per_horizon': per_horizon,
    }

    if all_logvars:
        logvars = np.concatenate(all_logvars)
        # Convert log-variance to std in mg/dL
        per_horizon_std = {}
        for i, name in enumerate(horizons.keys()):
            std = float(np.mean(np.sqrt(np.exp(logvars[:, i]))) * scale)
            per_horizon_std[name] = std
        result['uncertainty_per_horizon'] = per_horizon_std
        result['mean_uncertainty'] = float(np.mean(list(per_horizon_std.values())))

    try:
        clinical = compute_clinical_forecast_metrics(
            targets, preds, glucose_scale=scale)
        result['clinical'] = clinical
    except Exception:
        pass

    return result, preds, targets


# ─── Feature Preparation ───

def prepare_features(base_train, base_val, pk_train, pk_val,
                     history_steps, horizons, use_8ch=True, use_future_pk=True,
                     use_isf=False, isf_train=None, isf_val=None):
    max_horizon = max(horizons.values())

    targets_train = extract_targets(base_train, history_steps, horizons)
    targets_val = extract_targets(base_val, history_steps, horizons)

    glucose_t = base_train[:, :history_steps, 0:1].copy()
    glucose_v = base_val[:, :history_steps, 0:1].copy()

    isf_factor_t, isf_factor_v = None, None
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
            targets_train, targets_val, use_future_pk)


def prepare_dual_encoder_features(base_train, base_val, pk_train, pk_val,
                                  history_steps, horizons):
    """Prepare separate glucose, PK-history, and future-PK tensors."""
    max_horizon = max(horizons.values())
    targets_train = extract_targets(base_train, history_steps, horizons)
    targets_val = extract_targets(base_val, history_steps, horizons)

    # Glucose only (channel 0)
    glucose_t = base_train[:, :history_steps, 0:1].astype(np.float32)
    glucose_v = base_val[:, :history_steps, 0:1].astype(np.float32)

    # PK history channels (normalized)
    pk_hist_t = np.stack([
        pk_train[:, :history_steps, idx] / PK_NORMS[idx]
        for idx in FUTURE_PK_INDICES
    ], axis=2).astype(np.float32)
    pk_hist_v = np.stack([
        pk_val[:, :history_steps, idx] / PK_NORMS[idx]
        for idx in FUTURE_PK_INDICES
    ], axis=2).astype(np.float32)

    # Future PK
    future_t = np.stack([
        pk_train[:, history_steps:history_steps + max_horizon, idx] / PK_NORMS[idx]
        for idx in FUTURE_PK_INDICES
    ], axis=2).astype(np.float32)
    future_v = np.stack([
        pk_val[:, history_steps:history_steps + max_horizon, idx] / PK_NORMS[idx]
        for idx in FUTURE_PK_INDICES
    ], axis=2).astype(np.float32)

    return (glucose_t, glucose_v, pk_hist_t, pk_hist_v,
            future_t, future_v, targets_train, targets_val)


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


# ─── Helpers ───

def _run_variant(name, model, train_loader, val_loader, device, horizons,
                 train_kw, scale=GLUCOSE_SCALE, extra_info=''):
    t0 = time.time()
    n_params = sum(p.numel() for p in model.parameters())
    model = train_model(model, train_loader, val_loader, device, **train_kw)
    res, preds, targets = evaluate_model(model, val_loader, device, horizons,
                                         scale=scale)
    elapsed = time.time() - t0
    h_str = ', '.join(f"{k}={v:.1f}" for k, v in res['mae_per_horizon'].items())
    info = f"  ({n_params:,} params, {elapsed:.0f}s)"
    if extra_info:
        info = f"  ({extra_info})"
    print(f"    {name}... MAE={res['mae_overall']:.1f} [{h_str}]{info}")
    res['n_params'] = n_params
    return res, model


def _save_results(exp_name, description, results, horizons, filepath):
    summary = {}
    variant_groups = defaultdict(list)
    for key, val in results.items():
        base_name = '_'.join(key.rsplit('_', 1)[:-1]) if key.rsplit('_', 1)[-1].startswith('s') else key
        variant_groups[base_name].append(val)

    for vname, runs in variant_groups.items():
        maes = [r['mae_overall'] for r in runs]
        horizon_means = {}
        for h in horizons:
            vals = [r['mae_per_horizon'].get(h, 0) for r in runs]
            horizon_means[h] = {'mean': float(np.mean(vals)), 'std': float(np.std(vals))}
        summary[vname] = {
            'mae_overall_mean': float(np.mean(maes)),
            'mae_overall_std': float(np.std(maes)),
            'mae_per_horizon': horizon_means,
            'n_seeds': len(runs),
        }
        # Include uncertainty if present
        if 'uncertainty_per_horizon' in runs[0]:
            unc_means = {}
            for h in horizons:
                vals = [r['uncertainty_per_horizon'].get(h, 0) for r in runs]
                unc_means[h] = float(np.mean(vals))
            summary[vname]['mean_uncertainty'] = float(np.mean(list(unc_means.values())))
            summary[vname]['uncertainty_per_horizon'] = unc_means

    data = {
        'experiment': exp_name,
        'description': description,
        'horizons': list(horizons.keys()),
        'variants': results,
        'summary': summary,
    }
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2, default=str)
    print(f"\nSaved: {filepath}")

    print("\n─── Summary ───")
    for vname, s in summary.items():
        h_str = ', '.join(
            f"{h}={s['mae_per_horizon'][h]['mean']:.1f}±{s['mae_per_horizon'][h]['std']:.1f}"
            for h in horizons)
        extra = ''
        if 'mean_uncertainty' in s:
            extra = f"  (unc={s['mean_uncertainty']:.1f})"
        print(f"  {vname}: MAE={s['mae_overall_mean']:.1f}±{s['mae_overall_std']:.1f}"
              f" [{h_str}]{extra}")


# ─── EXP-373: Stacked Best Techniques ───

def run_exp_373(args, seeds=None, train_kw=None, max_patients=None):
    """Dilated ResNet + ISF + per-patient fine-tuning — stacking best techniques."""
    print("=" * 60)
    print("exp373_stacked_best")
    print("=" * 60)

    is_quick = args.quick
    horizons = HORIZONS_STANDARD if is_quick else HORIZONS_EXTENDED
    seeds = seeds or (SEEDS_QUICK if is_quick else SEEDS)
    max_patients = max_patients or (QUICK_PATIENTS if is_quick else None)
    train_kw = train_kw or {
        'epochs': QUICK_EPOCHS if is_quick else 60,
        'patience': QUICK_PATIENCE if is_quick else 15,
    }

    base_t, base_v, pk_t, pk_v, isf_t, isf_v, per_patient = load_forecast_data(
        args.patients_dir, history_steps=72, max_horizon=max(horizons.values()),
        max_patients=max_patients, load_isf=True)

    results = {}
    for seed in seeds:
        print(f"\n  seed={seed}:")
        torch.manual_seed(seed)
        np.random.seed(seed)
        n_h = len(horizons)
        device = args.device

        # Variant 1: Dilated ResNet baseline (no ISF, no fine-tuning)
        feats = prepare_features(base_t, base_v, pk_t, pk_v, 72, horizons,
                                 use_8ch=True, use_future_pk=True)
        hist_t, hist_v, fut_t, fut_v, tgt_t, tgt_v, has_future = feats
        train_ds, val_ds = to_tensors(hist_t, hist_v, fut_t, fut_v, tgt_t, tgt_v, True)
        train_loader = DataLoader(train_ds, batch_size=128, shuffle=True)
        val_loader = DataLoader(val_ds, batch_size=256)

        model = DilatedResNetWithFuture(hist_t.shape[2], fut_t.shape[2], n_h)
        res, _ = _run_variant(f"dilated_resnet", model, train_loader, val_loader,
                              device, horizons, train_kw)
        results[f"dilated_resnet_s{seed}"] = res

        # Variant 2: Dilated ResNet + ISF
        feats_isf = prepare_features(base_t, base_v, pk_t, pk_v, 72, horizons,
                                     use_8ch=True, use_future_pk=True,
                                     use_isf=True, isf_train=isf_t, isf_val=isf_v)
        h_t, h_v, f_t, f_v, t_t, t_v, _ = feats_isf
        isf_scale = GLUCOSE_SCALE  # ISF-normalized targets need ISF-aware unscaling
        # For fair comparison, evaluate in original scale
        train_ds2, val_ds2 = to_tensors(h_t, h_v, f_t, f_v, t_t, t_v, True)
        train_l2 = DataLoader(train_ds2, batch_size=128, shuffle=True)
        val_l2 = DataLoader(val_ds2, batch_size=256)

        model2 = DilatedResNetWithFuture(h_t.shape[2], f_t.shape[2], n_h)
        res2, _ = _run_variant(f"dilated_resnet_isf", model2, train_l2, val_l2,
                               device, horizons, train_kw, scale=isf_scale)
        results[f"dilated_resnet_isf_s{seed}"] = res2

        # Variant 3: Dilated ResNet + fine-tuning (global → per-patient head)
        model3 = DilatedResNetWithFuture(hist_t.shape[2], fut_t.shape[2], n_h)
        res3_global, trained_model3 = _run_variant(
            f"global_dilated", model3, train_loader, val_loader,
            device, horizons, train_kw)

        # Fine-tune per patient
        ft_epochs = 5
        ft_preds_all = []
        ft_targets_all = []
        for pinfo in per_patient:
            vs, vc = pinfo['val_start'], pinfo['val_count']
            if vc == 0:
                continue
            ts, tc = pinfo['train_start'], pinfo['train_count']

            # Per-patient train/val loaders
            pt_hist = hist_t[ts:ts+tc]
            pt_fut = fut_t[ts:ts+tc]
            pt_tgt = tgt_t[ts:ts+tc]
            pv_hist = hist_v[vs:vs+vc]
            pv_fut = fut_v[vs:vs+vc]
            pv_tgt = tgt_v[vs:vs+vc]

            pt_ds = TensorDataset(
                torch.from_numpy(pt_hist), torch.from_numpy(pt_fut),
                torch.from_numpy(pt_tgt))
            pv_ds = TensorDataset(
                torch.from_numpy(pv_hist), torch.from_numpy(pv_fut),
                torch.from_numpy(pv_tgt))
            pt_loader = DataLoader(pt_ds, batch_size=64, shuffle=True)
            pv_loader = DataLoader(pv_ds, batch_size=256)

            ft_model = copy.deepcopy(trained_model3)
            # Freeze everything except last block + head
            for name, param in ft_model.named_parameters():
                if 'head' not in name and 'hist_blocks.3' not in name:
                    param.requires_grad = False
            ft_model = train_model(ft_model, pt_loader, pv_loader, device,
                                   epochs=ft_epochs, patience=ft_epochs, lr=1e-4)

            # Evaluate
            ft_model.eval()
            with torch.no_grad():
                for batch in pv_loader:
                    inputs = [b.to(device) for b in batch[:-1]]
                    preds = ft_model(*inputs)
                    ft_preds_all.append(preds.cpu().numpy())
                    ft_targets_all.append(batch[-1].numpy())

        if ft_preds_all:
            ft_preds = np.concatenate(ft_preds_all)
            ft_targets = np.concatenate(ft_targets_all)
            ft_per_h = {}
            for i, h in enumerate(horizons):
                ft_per_h[h] = float(np.mean(np.abs(ft_preds[:, i] - ft_targets[:, i])) * GLUCOSE_SCALE)
            ft_mae = float(np.mean(list(ft_per_h.values())))
            h_str = ', '.join(f"{k}={v:.1f}" for k, v in ft_per_h.items())
            print(f"    dilated_resnet_ft... MAE={ft_mae:.1f} [{h_str}]  (ft_epochs={ft_epochs})")
            results[f"dilated_resnet_ft_s{seed}"] = {
                'mae_overall': ft_mae,
                'mae_per_horizon': ft_per_h,
                'n_params': sum(p.numel() for p in trained_model3.parameters()),
            }

        # Variant 4: Dilated ResNet + ISF + fine-tuning (the full stack)
        model4 = DilatedResNetWithFuture(h_t.shape[2], f_t.shape[2], n_h)
        res4_global, trained_model4 = _run_variant(
            f"global_dilated_isf", model4, train_l2, val_l2,
            device, horizons, train_kw, scale=isf_scale)

        ft_preds4_all, ft_tgt4_all = [], []
        for pinfo in per_patient:
            vs, vc = pinfo['val_start'], pinfo['val_count']
            if vc == 0:
                continue
            ts, tc = pinfo['train_start'], pinfo['train_count']

            pt_ds = TensorDataset(
                torch.from_numpy(h_t[ts:ts+tc]),
                torch.from_numpy(f_t[ts:ts+tc]),
                torch.from_numpy(t_t[ts:ts+tc]))
            pv_ds = TensorDataset(
                torch.from_numpy(h_v[vs:vs+vc]),
                torch.from_numpy(f_v[vs:vs+vc]),
                torch.from_numpy(t_v[vs:vs+vc]))
            pt_loader = DataLoader(pt_ds, batch_size=64, shuffle=True)
            pv_loader = DataLoader(pv_ds, batch_size=256)

            ft_model = copy.deepcopy(trained_model4)
            for name, param in ft_model.named_parameters():
                if 'head' not in name and 'hist_blocks.3' not in name:
                    param.requires_grad = False
            ft_model = train_model(ft_model, pt_loader, pv_loader, device,
                                   epochs=ft_epochs, patience=ft_epochs, lr=1e-4)

            ft_model.eval()
            with torch.no_grad():
                for batch in pv_loader:
                    inputs = [b.to(device) for b in batch[:-1]]
                    preds = ft_model(*inputs)
                    ft_preds4_all.append(preds.cpu().numpy())
                    ft_tgt4_all.append(batch[-1].numpy())

        if ft_preds4_all:
            ft_preds4 = np.concatenate(ft_preds4_all)
            ft_tgt4 = np.concatenate(ft_tgt4_all)
            ft4_per_h = {}
            for i, h in enumerate(horizons):
                ft4_per_h[h] = float(np.mean(np.abs(ft_preds4[:, i] - ft_tgt4[:, i])) * isf_scale)
            ft4_mae = float(np.mean(list(ft4_per_h.values())))
            h_str = ', '.join(f"{k}={v:.1f}" for k, v in ft4_per_h.items())
            print(f"    dilated_isf_ft... MAE={ft4_mae:.1f} [{h_str}]  (FULL STACK)")
            results[f"dilated_isf_ft_s{seed}"] = {
                'mae_overall': ft4_mae,
                'mae_per_horizon': ft4_per_h,
                'n_params': sum(p.numel() for p in trained_model4.parameters()),
            }

    _save_results('exp373_stacked_best',
                  'Dilated ResNet + ISF + fine-tuning stacking',
                  results, horizons,
                  'externals/experiments/exp373_stacked_best.json')


# ─── EXP-374: Dual-Encoder Architecture ───

def run_exp_374(args, seeds=None, train_kw=None, max_patients=None):
    """Dual-encoder: separate glucose vs PK processing, late fusion."""
    print("\n" + "=" * 60)
    print("exp374_dual_encoder")
    print("=" * 60)

    is_quick = args.quick
    horizons = HORIZONS_STANDARD if is_quick else HORIZONS_EXTENDED
    seeds = seeds or (SEEDS_QUICK if is_quick else SEEDS)
    max_patients = max_patients or (QUICK_PATIENTS if is_quick else None)
    train_kw = train_kw or {
        'epochs': QUICK_EPOCHS if is_quick else 60,
        'patience': QUICK_PATIENCE if is_quick else 15,
    }

    base_t, base_v, pk_t, pk_v, _, _, _ = load_forecast_data(
        args.patients_dir, history_steps=72, max_horizon=max(horizons.values()),
        max_patients=max_patients)

    results = {}
    for seed in seeds:
        print(f"\n  seed={seed}:")
        torch.manual_seed(seed)
        np.random.seed(seed)
        n_h = len(horizons)
        device = args.device

        # Reference: ResNet shared encoder
        feats = prepare_features(base_t, base_v, pk_t, pk_v, 72, horizons,
                                 use_8ch=True, use_future_pk=True)
        hist_t, hist_v, fut_t, fut_v, tgt_t, tgt_v, _ = feats
        train_ds, val_ds = to_tensors(hist_t, hist_v, fut_t, fut_v, tgt_t, tgt_v, True)
        train_loader = DataLoader(train_ds, batch_size=128, shuffle=True)
        val_loader = DataLoader(val_ds, batch_size=256)

        model_ref = ResNetCNNWithFuture(hist_t.shape[2], fut_t.shape[2], n_h)
        res_ref, _ = _run_variant("resnet_shared", model_ref, train_loader,
                                  val_loader, device, horizons, train_kw)
        results[f"resnet_shared_s{seed}"] = res_ref

        # Dual encoder
        (g_t, g_v, pk_h_t, pk_h_v,
         f_t, f_v, t_t, t_v) = prepare_dual_encoder_features(
            base_t, base_v, pk_t, pk_v, 72, horizons)

        dual_train = TensorDataset(
            torch.from_numpy(g_t), torch.from_numpy(pk_h_t),
            torch.from_numpy(f_t), torch.from_numpy(t_t))
        dual_val = TensorDataset(
            torch.from_numpy(g_v), torch.from_numpy(pk_h_v),
            torch.from_numpy(f_v), torch.from_numpy(t_v))
        dual_tl = DataLoader(dual_train, batch_size=128, shuffle=True)
        dual_vl = DataLoader(dual_val, batch_size=256)

        model_dual = DualEncoderWithFuture(
            pk_hist_channels=pk_h_t.shape[2],
            pk_future_channels=f_t.shape[2],
            n_horizons=n_h)
        res_dual, _ = _run_variant("dual_encoder", model_dual, dual_tl,
                                   dual_vl, device, horizons, train_kw)
        results[f"dual_encoder_s{seed}"] = res_dual

        # Dual encoder with dilated glucose branch
        model_dual_d = DualEncoderWithFuture(
            pk_hist_channels=pk_h_t.shape[2],
            pk_future_channels=f_t.shape[2],
            n_horizons=n_h)
        # Replace glucose blocks with dilated version
        model_dual_d.glucose_blocks = nn.Sequential(
            DilatedResBlock(48, 96, dilation=1),
            DilatedResBlock(96, 96, dilation=2),
            DilatedResBlock(96, 48, dilation=4),
        )
        res_dual_d, _ = _run_variant("dual_dilated", model_dual_d, dual_tl,
                                     dual_vl, device, horizons, train_kw)
        results[f"dual_dilated_s{seed}"] = res_dual_d

    _save_results('exp374_dual_encoder',
                  'Dual-encoder: separate glucose vs PK encoders with late fusion',
                  results, horizons,
                  'externals/experiments/exp374_dual_encoder.json')


# ─── EXP-375: Self-Attention over ResNet ───

def run_exp_375(args, seeds=None, train_kw=None, max_patients=None):
    """ResNet + temporal self-attention for long-horizon improvement."""
    print("\n" + "=" * 60)
    print("exp375_attention")
    print("=" * 60)

    is_quick = args.quick
    horizons = HORIZONS_STANDARD if is_quick else HORIZONS_EXTENDED
    seeds = seeds or (SEEDS_QUICK if is_quick else SEEDS)
    max_patients = max_patients or (QUICK_PATIENTS if is_quick else None)
    train_kw = train_kw or {
        'epochs': QUICK_EPOCHS if is_quick else 60,
        'patience': QUICK_PATIENCE if is_quick else 15,
    }

    base_t, base_v, pk_t, pk_v, _, _, _ = load_forecast_data(
        args.patients_dir, history_steps=72, max_horizon=max(horizons.values()),
        max_patients=max_patients)

    results = {}
    for seed in seeds:
        print(f"\n  seed={seed}:")
        torch.manual_seed(seed)
        np.random.seed(seed)
        n_h = len(horizons)
        device = args.device

        feats = prepare_features(base_t, base_v, pk_t, pk_v, 72, horizons,
                                 use_8ch=True, use_future_pk=True)
        hist_t, hist_v, fut_t, fut_v, tgt_t, tgt_v, _ = feats
        train_ds, val_ds = to_tensors(hist_t, hist_v, fut_t, fut_v, tgt_t, tgt_v, True)
        train_loader = DataLoader(train_ds, batch_size=128, shuffle=True)
        val_loader = DataLoader(val_ds, batch_size=256)

        # ResNet baseline
        model_base = ResNetCNNWithFuture(hist_t.shape[2], fut_t.shape[2], n_h)
        res_base, _ = _run_variant("resnet_baseline", model_base, train_loader,
                                   val_loader, device, horizons, train_kw)
        results[f"resnet_baseline_s{seed}"] = res_base

        # ResNet + attention (4 heads)
        model_attn = ResNetWithAttention(hist_t.shape[2], fut_t.shape[2], n_h,
                                         n_heads=4)
        res_attn, _ = _run_variant("resnet_attn_4h", model_attn, train_loader,
                                   val_loader, device, horizons, train_kw)
        results[f"resnet_attn_4h_s{seed}"] = res_attn

        # ResNet + attention (8 heads)
        model_attn8 = ResNetWithAttention(hist_t.shape[2], fut_t.shape[2], n_h,
                                          n_heads=8)
        res_attn8, _ = _run_variant("resnet_attn_8h", model_attn8, train_loader,
                                    val_loader, device, horizons, train_kw)
        results[f"resnet_attn_8h_s{seed}"] = res_attn8

        # Dilated ResNet + attention (combine best)
        model_dilated_attn = ResNetWithAttention(hist_t.shape[2], fut_t.shape[2],
                                                 n_h, n_heads=4)
        # Replace ResBlocks with DilatedResBlocks
        model_dilated_attn.hist_blocks = nn.Sequential(
            DilatedResBlock(64, 128, dilation=1),
            DilatedResBlock(128, 128, dilation=2),
            DilatedResBlock(128, 64, dilation=4),
        )
        res_da, _ = _run_variant("dilated_attn", model_dilated_attn,
                                 train_loader, val_loader, device, horizons, train_kw)
        results[f"dilated_attn_s{seed}"] = res_da

    _save_results('exp375_attention',
                  'ResNet + temporal self-attention',
                  results, horizons,
                  'externals/experiments/exp375_attention.json')


# ─── EXP-376: Overlapping Windows for Longer History ───

def run_exp_376(args, seeds=None, train_kw=None, max_patients=None):
    """Fix EXP-372: use fixed stride=36 for all history lengths."""
    print("\n" + "=" * 60)
    print("exp376_history_overlap")
    print("=" * 60)

    is_quick = args.quick
    horizons = HORIZONS_STANDARD if is_quick else HORIZONS_EXTENDED
    seeds = seeds or (SEEDS_QUICK if is_quick else SEEDS)
    max_patients = max_patients or (QUICK_PATIENTS if is_quick else None)
    train_kw = train_kw or {
        'epochs': QUICK_EPOCHS if is_quick else 60,
        'patience': QUICK_PATIENCE if is_quick else 15,
    }

    device = args.device
    n_h = len(horizons)
    max_horizon = max(horizons.values())
    fixed_stride = 36  # 3h stride regardless of history length

    results = {}
    for hist_hours, hist_steps in [('6h', 72), ('9h', 108), ('12h', 144)]:
        print(f"\n  --- history_{hist_hours} ({hist_steps} steps, stride={fixed_stride}) ---")

        base_t, base_v, pk_t, pk_v, _, _, _ = load_forecast_data(
            args.patients_dir, history_steps=hist_steps,
            max_horizon=max_horizon, max_patients=max_patients,
            stride=fixed_stride)

        feats = prepare_features(base_t, base_v, pk_t, pk_v, hist_steps,
                                 horizons, use_8ch=True, use_future_pk=True)
        hist_t, hist_v, fut_t, fut_v, tgt_t, tgt_v, _ = feats
        train_ds, val_ds = to_tensors(hist_t, hist_v, fut_t, fut_v,
                                      tgt_t, tgt_v, True)
        train_loader = DataLoader(train_ds, batch_size=128, shuffle=True)
        val_loader = DataLoader(val_ds, batch_size=256)

        for seed in seeds:
            print(f"\n  seed={seed}:")
            torch.manual_seed(seed)
            np.random.seed(seed)

            model = ResNetCNNWithFuture(hist_t.shape[2], fut_t.shape[2], n_h)
            res, _ = _run_variant(f"history_{hist_hours}", model, train_loader,
                                  val_loader, device, horizons, train_kw)
            results[f"history_{hist_hours}_s{seed}"] = res

    _save_results('exp376_history_overlap',
                  'History window scaling with fixed stride=36 (overlapping windows)',
                  results, horizons,
                  'externals/experiments/exp376_history_overlap.json')


# ─── EXP-377: Heteroscedastic Uncertainty ───

def run_exp_377(args, seeds=None, train_kw=None, max_patients=None):
    """Predict mean + variance for uncertainty estimation."""
    print("\n" + "=" * 60)
    print("exp377_uncertainty")
    print("=" * 60)

    is_quick = args.quick
    horizons = HORIZONS_STANDARD if is_quick else HORIZONS_EXTENDED
    seeds = seeds or (SEEDS_QUICK if is_quick else SEEDS)
    max_patients = max_patients or (QUICK_PATIENTS if is_quick else None)
    train_kw_mse = train_kw or {
        'epochs': QUICK_EPOCHS if is_quick else 60,
        'patience': QUICK_PATIENCE if is_quick else 15,
    }
    train_kw_nll = dict(train_kw_mse)
    train_kw_nll['loss_fn'] = 'gaussian_nll'

    base_t, base_v, pk_t, pk_v, _, _, _ = load_forecast_data(
        args.patients_dir, history_steps=72, max_horizon=max(horizons.values()),
        max_patients=max_patients)

    results = {}
    for seed in seeds:
        print(f"\n  seed={seed}:")
        torch.manual_seed(seed)
        np.random.seed(seed)
        n_h = len(horizons)
        device = args.device

        feats = prepare_features(base_t, base_v, pk_t, pk_v, 72, horizons,
                                 use_8ch=True, use_future_pk=True)
        hist_t, hist_v, fut_t, fut_v, tgt_t, tgt_v, _ = feats
        train_ds, val_ds = to_tensors(hist_t, hist_v, fut_t, fut_v, tgt_t, tgt_v, True)
        train_loader = DataLoader(train_ds, batch_size=128, shuffle=True)
        val_loader = DataLoader(val_ds, batch_size=256)

        # MSE baseline (standard ResNet)
        model_mse = ResNetCNNWithFuture(hist_t.shape[2], fut_t.shape[2], n_h)
        res_mse, _ = _run_variant("resnet_mse", model_mse, train_loader,
                                  val_loader, device, horizons, train_kw_mse)
        results[f"resnet_mse_s{seed}"] = res_mse

        # Heteroscedastic ResNet (Gaussian NLL)
        model_hetero = HeteroscedasticResNet(hist_t.shape[2], fut_t.shape[2], n_h)
        t0 = time.time()
        n_params = sum(p.numel() for p in model_hetero.parameters())
        model_hetero = train_model(model_hetero, train_loader, val_loader, device,
                                   **train_kw_nll)
        res_hetero, preds_h, targets_h = evaluate_model(
            model_hetero, val_loader, device, horizons, is_hetero=True)
        elapsed = time.time() - t0
        h_str = ', '.join(f"{k}={v:.1f}" for k, v in res_hetero['mae_per_horizon'].items())
        unc_str = ', '.join(f"{k}={v:.1f}" for k, v in res_hetero.get('uncertainty_per_horizon', {}).items())
        print(f"    resnet_hetero... MAE={res_hetero['mae_overall']:.1f} [{h_str}]"
              f"  unc=[{unc_str}]  ({n_params:,} params, {elapsed:.0f}s)")
        res_hetero['n_params'] = n_params
        results[f"resnet_hetero_s{seed}"] = res_hetero

    _save_results('exp377_uncertainty',
                  'Heteroscedastic uncertainty estimation (Gaussian NLL)',
                  results, horizons,
                  'externals/experiments/exp377_uncertainty.json')


# ─── Main ───

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='EXP-373 to EXP-377: Combination & novel architecture experiments')
    parser.add_argument('--experiment', type=str, default='373',
                        help='Experiment number (373-377) or "all"')
    parser.add_argument('--device', type=str, default='cpu')
    parser.add_argument('--quick', action='store_true',
                        help='Quick mode: 4 patients, 1 seed, 30 epochs')
    parser.add_argument('--patients-dir', type=str,
                        default='externals/ns-data/patients')
    args = parser.parse_args()

    experiments = {
        '373': run_exp_373,
        '374': run_exp_374,
        '375': run_exp_375,
        '376': run_exp_376,
        '377': run_exp_377,
    }

    if args.experiment == 'all':
        for name, fn in experiments.items():
            fn(args)
    elif args.experiment in experiments:
        experiments[args.experiment](args)
    else:
        print(f"Unknown experiment: {args.experiment}")
        print(f"Available: {', '.join(experiments.keys())} or 'all'")
        sys.exit(1)
