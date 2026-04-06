#!/usr/bin/env python3
"""EXP-378 through EXP-381: Dual Encoder Combinations & Refinements

Building on EXP-374 full validation results:
  - Dual encoder: MAE=36.0±0.0 (173K params), h30=19.9±0.2 (best ever!)
  - vs shared ResNet: 36.2±0.3, h30=21.5±0.6
  - Dual encoder has lower variance, better h30, same-ish overall
  - The ISF champion (EXP-368): 35.8±0.1 — dual encoder doesn't include ISF yet

Key insight: ISF normalization is a NATURAL fit for the dual encoder because:
  1. ISF scales glucose only — dual encoder already separates glucose from PK
  2. Shared ResNet mixes ISF-scaled glucose with unscaled PK in same feature space
  3. Dual encoder gives each signal its own encoder at its natural scale

EXP-378 — Dual Encoder + ISF Normalization
  Apply ISF to glucose branch only, targets scaled accordingly.
  Hypothesis: ISF's equalization + dual encoder's signal separation = new champion.

EXP-379 — Dual Encoder + Heteroscedastic Loss
  Predict mean + log_variance. Train with Gaussian NLL.
  Quick-mode showed -0.6 for shared ResNet (EXP-377).
  Loss function changes translate to full scale (not architecture).
  Hypothesis: Uncertainty-aware training focuses capacity on predictable cases.

EXP-380 — Full Stack: Dual Encoder + ISF + Heteroscedastic
  Combine all three orthogonal improvements.
  If they stack: 36.0 - 0.1 (ISF) - 0.6 (hetero) ≈ 35.3 = new champion.

EXP-381 — Dual Encoder + Per-Patient Fine-Tuning
  Train global dual encoder, then fine-tune head per patient.
  Prior: EXP-371 fine-tuning gave -1.2 in quick mode (shared ResNet).
  Hypothesis: Per-patient head adapts to individual glucose/PK dynamics.

Usage:
    python tools/cgmencode/exp_pk_forecast_v7.py --experiment 378 --device cuda --quick
    python tools/cgmencode/exp_pk_forecast_v7.py --experiment all --device cuda
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

# ─── Data Loading (reused from v6) ───

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
        out = F.relu(self.bn1(self.conv1(x)))
        out = self.drop(out)
        out = self.bn2(self.conv2(out))
        return F.relu(out + residual)


class ResNetCNNWithFuture(nn.Module):
    """Standard ResNet + future PK (baseline reference)."""
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
    Glucose encoder: deep ResNet on glucose channel only
    Treatment encoder: ResNet on PK history channels
    Future encoder: CNN on projected PK channels
    Late fusion: concatenate all embeddings → head
    """
    def __init__(self, pk_hist_channels, pk_future_channels,
                 n_horizons=8, dropout=0.1):
        super().__init__()
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

        self.pk_stem = nn.Sequential(
            nn.Conv1d(pk_hist_channels, 32, kernel_size=5, padding=2),
            nn.ReLU(), nn.BatchNorm1d(32),
        )
        self.pk_blocks = nn.Sequential(
            ResBlock1d(32, 64, dropout=dropout),
            ResBlock1d(64, 32, dropout=dropout),
        )
        self.pk_pool = nn.AdaptiveAvgPool1d(1)

        self.future_conv = nn.Sequential(
            nn.Conv1d(pk_future_channels, 32, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(32),
            nn.Conv1d(32, 32, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(32),
            nn.AdaptiveAvgPool1d(1),
        )

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


class DualEncoderHeteroscedastic(nn.Module):
    """Dual encoder that predicts mean + log_variance for uncertainty."""
    def __init__(self, pk_hist_channels, pk_future_channels,
                 n_horizons=8, dropout=0.1):
        super().__init__()
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

        self.pk_stem = nn.Sequential(
            nn.Conv1d(pk_hist_channels, 32, kernel_size=5, padding=2),
            nn.ReLU(), nn.BatchNorm1d(32),
        )
        self.pk_blocks = nn.Sequential(
            ResBlock1d(32, 64, dropout=dropout),
            ResBlock1d(64, 32, dropout=dropout),
        )
        self.pk_pool = nn.AdaptiveAvgPool1d(1)

        self.future_conv = nn.Sequential(
            nn.Conv1d(pk_future_channels, 32, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(32),
            nn.Conv1d(32, 32, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(32),
            nn.AdaptiveAvgPool1d(1),
        )

        self.shared = nn.Sequential(
            nn.Linear(48 + 32 + 32, 64), nn.ReLU(), nn.Dropout(dropout),
        )
        self.mean_head = nn.Linear(64, n_horizons)
        self.logvar_head = nn.Linear(64, n_horizons)

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

        shared = self.shared(torch.cat([g_feat, p_feat, f_feat], dim=1))
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

def prepare_dual_encoder_features(base_train, base_val, pk_train, pk_val,
                                  history_steps, horizons,
                                  isf_train=None, isf_val=None):
    """Prepare separate glucose, PK-history, and future-PK tensors.

    If ISF arrays provided, glucose and targets are ISF-normalized.
    """
    max_horizon = max(horizons.values())
    targets_train = extract_targets(base_train, history_steps, horizons)
    targets_val = extract_targets(base_val, history_steps, horizons)

    glucose_t = base_train[:, :history_steps, 0:1].copy().astype(np.float32)
    glucose_v = base_val[:, :history_steps, 0:1].copy().astype(np.float32)

    isf_scale = GLUCOSE_SCALE
    if isf_train is not None and isf_val is not None:
        isf_factor_t = (GLUCOSE_SCALE / isf_train).reshape(-1, 1, 1)
        isf_factor_v = (GLUCOSE_SCALE / isf_val).reshape(-1, 1, 1)
        glucose_t = glucose_t * isf_factor_t
        glucose_v = glucose_v * isf_factor_v
        targets_train = targets_train * (GLUCOSE_SCALE / isf_train).reshape(-1, 1)
        targets_val = targets_val * (GLUCOSE_SCALE / isf_val).reshape(-1, 1)
        np.clip(glucose_t, 0, 10, out=glucose_t)
        np.clip(glucose_v, 0, 10, out=glucose_v)

    pk_hist_t = np.stack([
        pk_train[:, :history_steps, idx] / PK_NORMS[idx]
        for idx in FUTURE_PK_INDICES
    ], axis=2).astype(np.float32)
    pk_hist_v = np.stack([
        pk_val[:, :history_steps, idx] / PK_NORMS[idx]
        for idx in FUTURE_PK_INDICES
    ], axis=2).astype(np.float32)

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


def prepare_shared_features(base_train, base_val, pk_train, pk_val,
                            history_steps, horizons,
                            isf_train=None, isf_val=None):
    """Prepare 8ch + future PK features for shared ResNet reference."""
    max_horizon = max(horizons.values())
    targets_train = extract_targets(base_train, history_steps, horizons)
    targets_val = extract_targets(base_val, history_steps, horizons)

    hist_t = base_train[:, :history_steps].copy()
    hist_v = base_val[:, :history_steps].copy()

    isf_scale = GLUCOSE_SCALE
    if isf_train is not None and isf_val is not None:
        isf_factor_t = (GLUCOSE_SCALE / isf_train).reshape(-1, 1, 1)
        isf_factor_v = (GLUCOSE_SCALE / isf_val).reshape(-1, 1, 1)
        hist_t[:, :, 0:1] = hist_t[:, :, 0:1] * isf_factor_t
        hist_v[:, :, 0:1] = hist_v[:, :, 0:1] * isf_factor_v
        targets_train = targets_train * (GLUCOSE_SCALE / isf_train).reshape(-1, 1)
        targets_val = targets_val * (GLUCOSE_SCALE / isf_val).reshape(-1, 1)
        np.clip(hist_t[:, :, 0:1], 0, 10, out=hist_t[:, :, 0:1])
        np.clip(hist_v[:, :, 0:1], 0, 10, out=hist_v[:, :, 0:1])

    future_t = np.stack([
        pk_train[:, history_steps:history_steps + max_horizon, idx] / PK_NORMS[idx]
        for idx in FUTURE_PK_INDICES
    ], axis=2).astype(np.float32)
    future_v = np.stack([
        pk_val[:, history_steps:history_steps + max_horizon, idx] / PK_NORMS[idx]
        for idx in FUTURE_PK_INDICES
    ], axis=2).astype(np.float32)

    return (hist_t.astype(np.float32), hist_v.astype(np.float32),
            future_t, future_v, targets_train, targets_val)


# ─── Helpers ───

def _make_dual_loaders(g_t, g_v, pk_h_t, pk_h_v, f_t, f_v, t_t, t_v):
    train_ds = TensorDataset(
        torch.from_numpy(g_t), torch.from_numpy(pk_h_t),
        torch.from_numpy(f_t), torch.from_numpy(t_t))
    val_ds = TensorDataset(
        torch.from_numpy(g_v), torch.from_numpy(pk_h_v),
        torch.from_numpy(f_v), torch.from_numpy(t_v))
    return (DataLoader(train_ds, batch_size=128, shuffle=True),
            DataLoader(val_ds, batch_size=256))


def _make_shared_loaders(h_t, h_v, f_t, f_v, t_t, t_v):
    train_ds = TensorDataset(
        torch.from_numpy(h_t), torch.from_numpy(f_t),
        torch.from_numpy(t_t.astype(np.float32)))
    val_ds = TensorDataset(
        torch.from_numpy(h_v), torch.from_numpy(f_v),
        torch.from_numpy(t_v.astype(np.float32)))
    return (DataLoader(train_ds, batch_size=128, shuffle=True),
            DataLoader(val_ds, batch_size=256))


def _run_variant(name, model, train_loader, val_loader, device, horizons,
                 train_kw, scale=GLUCOSE_SCALE, is_hetero=False):
    t0 = time.time()
    n_params = sum(p.numel() for p in model.parameters())
    loss_fn = 'gaussian_nll' if is_hetero else 'mse'
    model = train_model(model, train_loader, val_loader, device,
                        **train_kw, loss_fn=loss_fn)
    res, preds, targets = evaluate_model(model, val_loader, device, horizons,
                                         scale=scale, is_hetero=is_hetero)
    elapsed = time.time() - t0
    h_str = ', '.join(f"{k}={v:.1f}" for k, v in res['mae_per_horizon'].items())
    unc_str = ''
    if 'mean_uncertainty' in res:
        unc_str = f"  unc=[" + ', '.join(
            f"{k}={v:.1f}" for k, v in res.get('uncertainty_per_horizon', {}).items()
        ) + "]"
    print(f"    {name}... MAE={res['mae_overall']:.1f} [{h_str}]"
          f"  ({n_params:,} params, {elapsed:.0f}s){unc_str}")
    res['n_params'] = n_params
    return res, model


def _save_results(exp_name, description, results, horizons, filepath):
    summary = {}
    variant_groups = defaultdict(list)
    for key, val in results.items():
        parts = key.rsplit('_', 1)
        base_name = parts[0] if len(parts) > 1 and parts[-1].startswith('s') else key
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


# ─── EXP-378: Dual Encoder + ISF Normalization ───

def run_exp_378(args, seeds=None, train_kw=None, max_patients=None):
    """Dual encoder with ISF-normalized glucose — natural fit."""
    print("\n" + "=" * 60)
    print("exp378_dual_isf")
    print("=" * 60)

    is_quick = args.quick
    horizons = HORIZONS_STANDARD if is_quick else HORIZONS_EXTENDED
    seeds = seeds or (SEEDS_QUICK if is_quick else SEEDS)
    max_patients = max_patients or (QUICK_PATIENTS if is_quick else None)
    train_kw = train_kw or {
        'epochs': QUICK_EPOCHS if is_quick else 60,
        'patience': QUICK_PATIENCE if is_quick else 15,
    }

    base_t, base_v, pk_t, pk_v, isf_t, isf_v, _ = load_forecast_data(
        args.patients_dir, history_steps=72, max_horizon=max(horizons.values()),
        max_patients=max_patients, load_isf=True)

    results = {}
    for seed in seeds:
        print(f"\n  seed={seed}:")
        torch.manual_seed(seed)
        np.random.seed(seed)
        n_h = len(horizons)
        device = args.device

        # Reference: Dual encoder without ISF (reproduces EXP-374)
        (g_t, g_v, pk_h_t, pk_h_v,
         f_t, f_v, t_t, t_v) = prepare_dual_encoder_features(
            base_t, base_v, pk_t, pk_v, 72, horizons)
        dual_tl, dual_vl = _make_dual_loaders(
            g_t, g_v, pk_h_t, pk_h_v, f_t, f_v, t_t, t_v)

        model = DualEncoderWithFuture(
            pk_hist_channels=pk_h_t.shape[2],
            pk_future_channels=f_t.shape[2], n_horizons=n_h)
        res, _ = _run_variant("dual_no_isf", model, dual_tl, dual_vl,
                              device, horizons, train_kw)
        results[f"dual_no_isf_s{seed}"] = res

        # Dual encoder + ISF (glucose branch only ISF-normalized)
        (g_isf_t, g_isf_v, pk_h_t2, pk_h_v2,
         f_t2, f_v2, t_isf_t, t_isf_v) = prepare_dual_encoder_features(
            base_t, base_v, pk_t, pk_v, 72, horizons,
            isf_train=isf_t, isf_val=isf_v)
        dual_isf_tl, dual_isf_vl = _make_dual_loaders(
            g_isf_t, g_isf_v, pk_h_t2, pk_h_v2,
            f_t2, f_v2, t_isf_t, t_isf_v)

        model_isf = DualEncoderWithFuture(
            pk_hist_channels=pk_h_t2.shape[2],
            pk_future_channels=f_t2.shape[2], n_horizons=n_h)
        res_isf, _ = _run_variant("dual_isf", model_isf, dual_isf_tl, dual_isf_vl,
                                  device, horizons, train_kw, scale=GLUCOSE_SCALE)
        results[f"dual_isf_s{seed}"] = res_isf

        # Shared ResNet + ISF (EXP-368 reproduction for comparison)
        (sh_t, sh_v, sf_t, sf_v,
         st_t, st_v) = prepare_shared_features(
            base_t, base_v, pk_t, pk_v, 72, horizons,
            isf_train=isf_t, isf_val=isf_v)
        shared_isf_tl, shared_isf_vl = _make_shared_loaders(
            sh_t, sh_v, sf_t, sf_v, st_t, st_v)

        model_shared = ResNetCNNWithFuture(sh_t.shape[2], sf_t.shape[2], n_h)
        res_shared, _ = _run_variant("shared_isf", model_shared,
                                     shared_isf_tl, shared_isf_vl,
                                     device, horizons, train_kw, scale=GLUCOSE_SCALE)
        results[f"shared_isf_s{seed}"] = res_shared

    _save_results('exp378_dual_isf',
                  'Dual encoder + ISF normalization on glucose branch',
                  results, horizons,
                  'externals/experiments/exp378_dual_isf.json')


# ─── EXP-379: Dual Encoder + Heteroscedastic Loss ───

def run_exp_379(args, seeds=None, train_kw=None, max_patients=None):
    """Dual encoder with Gaussian NLL loss for uncertainty."""
    print("\n" + "=" * 60)
    print("exp379_dual_hetero")
    print("=" * 60)

    is_quick = args.quick
    horizons = HORIZONS_STANDARD if is_quick else HORIZONS_EXTENDED
    seeds = seeds or (SEEDS_QUICK if is_quick else SEEDS)
    max_patients = max_patients or (QUICK_PATIENTS if is_quick else None)
    train_kw_mse = train_kw or {
        'epochs': QUICK_EPOCHS if is_quick else 60,
        'patience': QUICK_PATIENCE if is_quick else 15,
    }
    train_kw_hetero = dict(train_kw_mse)

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

        (g_t, g_v, pk_h_t, pk_h_v,
         f_t, f_v, t_t, t_v) = prepare_dual_encoder_features(
            base_t, base_v, pk_t, pk_v, 72, horizons)
        dual_tl, dual_vl = _make_dual_loaders(
            g_t, g_v, pk_h_t, pk_h_v, f_t, f_v, t_t, t_v)

        # Reference: dual encoder MSE
        model_mse = DualEncoderWithFuture(
            pk_hist_channels=pk_h_t.shape[2],
            pk_future_channels=f_t.shape[2], n_horizons=n_h)
        res_mse, _ = _run_variant("dual_mse", model_mse, dual_tl, dual_vl,
                                  device, horizons, train_kw_mse)
        results[f"dual_mse_s{seed}"] = res_mse

        # Dual encoder + heteroscedastic
        model_het = DualEncoderHeteroscedastic(
            pk_hist_channels=pk_h_t.shape[2],
            pk_future_channels=f_t.shape[2], n_horizons=n_h)
        res_het, _ = _run_variant("dual_hetero", model_het, dual_tl, dual_vl,
                                  device, horizons, train_kw_hetero,
                                  is_hetero=True)
        results[f"dual_hetero_s{seed}"] = res_het

    _save_results('exp379_dual_hetero',
                  'Dual encoder with heteroscedastic uncertainty estimation',
                  results, horizons,
                  'externals/experiments/exp379_dual_hetero.json')


# ─── EXP-380: Full Stack: Dual Encoder + ISF + Heteroscedastic ───

def run_exp_380(args, seeds=None, train_kw=None, max_patients=None):
    """Combine all three orthogonal improvements."""
    print("\n" + "=" * 60)
    print("exp380_dual_isf_hetero")
    print("=" * 60)

    is_quick = args.quick
    horizons = HORIZONS_STANDARD if is_quick else HORIZONS_EXTENDED
    seeds = seeds or (SEEDS_QUICK if is_quick else SEEDS)
    max_patients = max_patients or (QUICK_PATIENTS if is_quick else None)
    train_kw = train_kw or {
        'epochs': QUICK_EPOCHS if is_quick else 60,
        'patience': QUICK_PATIENCE if is_quick else 15,
    }

    base_t, base_v, pk_t, pk_v, isf_t, isf_v, _ = load_forecast_data(
        args.patients_dir, history_steps=72, max_horizon=max(horizons.values()),
        max_patients=max_patients, load_isf=True)

    results = {}
    for seed in seeds:
        print(f"\n  seed={seed}:")
        torch.manual_seed(seed)
        np.random.seed(seed)
        n_h = len(horizons)
        device = args.device

        # Full stack: dual encoder + ISF + heteroscedastic
        (g_isf_t, g_isf_v, pk_h_t, pk_h_v,
         f_t, f_v, t_isf_t, t_isf_v) = prepare_dual_encoder_features(
            base_t, base_v, pk_t, pk_v, 72, horizons,
            isf_train=isf_t, isf_val=isf_v)
        dual_tl, dual_vl = _make_dual_loaders(
            g_isf_t, g_isf_v, pk_h_t, pk_h_v,
            f_t, f_v, t_isf_t, t_isf_v)

        model = DualEncoderHeteroscedastic(
            pk_hist_channels=pk_h_t.shape[2],
            pk_future_channels=f_t.shape[2], n_horizons=n_h)
        res, _ = _run_variant("dual_isf_hetero", model, dual_tl, dual_vl,
                              device, horizons, train_kw,
                              scale=GLUCOSE_SCALE, is_hetero=True)
        results[f"dual_isf_hetero_s{seed}"] = res

        # Comparison: dual encoder + ISF (MSE only)
        model_isf_mse = DualEncoderWithFuture(
            pk_hist_channels=pk_h_t.shape[2],
            pk_future_channels=f_t.shape[2], n_horizons=n_h)
        res_mse, _ = _run_variant("dual_isf_mse", model_isf_mse, dual_tl, dual_vl,
                                  device, horizons, train_kw,
                                  scale=GLUCOSE_SCALE)
        results[f"dual_isf_mse_s{seed}"] = res_mse

    _save_results('exp380_dual_isf_hetero',
                  'Full stack: dual encoder + ISF + heteroscedastic loss',
                  results, horizons,
                  'externals/experiments/exp380_dual_isf_hetero.json')


# ─── EXP-381: Dual Encoder + Per-Patient Fine-Tuning ───

def run_exp_381(args, seeds=None, train_kw=None, max_patients=None):
    """Train global dual encoder, fine-tune head per patient."""
    print("\n" + "=" * 60)
    print("exp381_dual_finetune")
    print("=" * 60)

    is_quick = args.quick
    horizons = HORIZONS_STANDARD if is_quick else HORIZONS_EXTENDED
    seeds = seeds or (SEEDS_QUICK if is_quick else SEEDS)
    max_patients = max_patients or (QUICK_PATIENTS if is_quick else None)
    train_kw = train_kw or {
        'epochs': QUICK_EPOCHS if is_quick else 60,
        'patience': QUICK_PATIENCE if is_quick else 15,
    }

    base_t, base_v, pk_t, pk_v, _, _, per_patient = load_forecast_data(
        args.patients_dir, history_steps=72, max_horizon=max(horizons.values()),
        max_patients=max_patients)

    results = {}
    for seed in seeds:
        print(f"\n  seed={seed}:")
        torch.manual_seed(seed)
        np.random.seed(seed)
        n_h = len(horizons)
        device = args.device

        (g_t, g_v, pk_h_t, pk_h_v,
         f_t, f_v, t_t, t_v) = prepare_dual_encoder_features(
            base_t, base_v, pk_t, pk_v, 72, horizons)
        dual_tl, dual_vl = _make_dual_loaders(
            g_t, g_v, pk_h_t, pk_h_v, f_t, f_v, t_t, t_v)

        # Step 1: Train global dual encoder
        model = DualEncoderWithFuture(
            pk_hist_channels=pk_h_t.shape[2],
            pk_future_channels=f_t.shape[2], n_horizons=n_h)
        res_global, trained_model = _run_variant(
            "dual_global", model, dual_tl, dual_vl,
            device, horizons, train_kw)
        results[f"dual_global_s{seed}"] = res_global

        # Step 2: Per-patient fine-tuning (head only)
        ft_epochs = 5
        ft_lr = 1e-4
        all_ft_preds = []
        all_ft_targets = []

        for pinfo in per_patient:
            vs, vc = pinfo['val_start'], pinfo['val_count']
            ts, tc = pinfo['train_start'], pinfo['train_count']
            if vc == 0 or tc == 0:
                continue

            # Per-patient data
            pt_g = g_t[ts:ts+tc]
            pt_pk = pk_h_t[ts:ts+tc]
            pt_f = f_t[ts:ts+tc]
            pt_tgt = t_t[ts:ts+tc]
            pv_g = g_v[vs:vs+vc]
            pv_pk = pk_h_v[vs:vs+vc]
            pv_f = f_v[vs:vs+vc]
            pv_tgt = t_v[vs:vs+vc]

            pt_ds = TensorDataset(
                torch.from_numpy(pt_g), torch.from_numpy(pt_pk),
                torch.from_numpy(pt_f), torch.from_numpy(pt_tgt))
            pt_loader = DataLoader(pt_ds, batch_size=64, shuffle=True)

            # Clone model, freeze encoders, only fine-tune head
            ft_model = copy.deepcopy(trained_model).to(device)
            for param in ft_model.parameters():
                param.requires_grad = False
            for param in ft_model.head.parameters():
                param.requires_grad = True

            optimizer = torch.optim.Adam(
                filter(lambda p: p.requires_grad, ft_model.parameters()),
                lr=ft_lr)

            for epoch in range(ft_epochs):
                ft_model.train()
                for batch in pt_loader:
                    inputs = [b.to(device) for b in batch[:-1]]
                    targets = batch[-1].to(device)
                    optimizer.zero_grad()
                    preds = ft_model(*inputs)
                    loss = F.mse_loss(preds, targets)
                    loss.backward()
                    optimizer.step()

            # Evaluate on patient val
            ft_model.eval()
            with torch.no_grad():
                pv_inputs = [
                    torch.from_numpy(pv_g).to(device),
                    torch.from_numpy(pv_pk).to(device),
                    torch.from_numpy(pv_f).to(device),
                ]
                pv_pred = ft_model(*pv_inputs).cpu().numpy()
                all_ft_preds.append(pv_pred)
                all_ft_targets.append(pv_tgt)

        # Aggregate fine-tuned results
        ft_preds = np.concatenate(all_ft_preds)
        ft_targets = np.concatenate(all_ft_targets)
        ft_per_h = {}
        for i, h in enumerate(horizons.keys()):
            ft_per_h[h] = float(np.mean(np.abs(
                ft_preds[:, i] - ft_targets[:, i])) * GLUCOSE_SCALE)

        ft_result = {
            'mae_overall': float(np.mean(list(ft_per_h.values()))),
            'mae_per_horizon': ft_per_h,
            'n_params': sum(p.numel() for p in model.parameters()),
        }
        h_str = ', '.join(f"{k}={v:.1f}" for k, v in ft_per_h.items())
        print(f"    dual_finetune... MAE={ft_result['mae_overall']:.1f} [{h_str}]"
              f"  (ft_epochs={ft_epochs})")
        results[f"dual_finetune_s{seed}"] = ft_result

    _save_results('exp381_dual_finetune',
                  'Dual encoder with per-patient head fine-tuning',
                  results, horizons,
                  'externals/experiments/exp381_dual_finetune.json')


# ─── CLI ───

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='EXP-378 to EXP-381: Dual encoder combinations')
    parser.add_argument('--experiment', type=str, default='378',
                        help='Experiment number (378-381) or "all"')
    parser.add_argument('--device', type=str, default='cpu')
    parser.add_argument('--quick', action='store_true',
                        help='Quick mode: 4 patients, 1 seed, 30 epochs')
    parser.add_argument('--patients-dir', type=str,
                        default='externals/ns-data/patients')
    args = parser.parse_args()

    experiments = {
        '378': run_exp_378,
        '379': run_exp_379,
        '380': run_exp_380,
        '381': run_exp_381,
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
