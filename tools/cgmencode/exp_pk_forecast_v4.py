#!/usr/bin/env python3
"""EXP-365 through EXP-368: Horizon-Adaptive & Architecture Experiments

Key insight from EXP-364: ISF normalization wins h30-h120 but loses h240-h720.
This demands horizon-adaptive processing — different features/architectures
for different prediction horizons.

EXP-365 — Horizon-Selective Ensemble
  Combine ISF-normalized and raw-glucose models at inference.
  Use ISF model for short horizons, raw for long horizons, average for mid.
  Hypothesis: Gets best of both worlds (MAE≈36.8 vs 37.4 champion).

EXP-366 — Dilated Temporal CNN (WaveNet-style)
  Replace standard CNN with dilated causal convolutions (1,2,4,8,16,32).
  Skip connections aggregate features at all temporal scales.
  Hypothesis: Multi-scale receptive field improves long-horizon forecasting.

EXP-367 — Horizon-Conditioned ForecastCNN
  Shared backbone extracts features; per-horizon FiLM modulation adapts
  feature representation for each target horizon.
  Hypothesis: Single model learns horizon-specific feature weighting,
  resolving the ISF short/long trade-off without ensembling.

EXP-368 — Residual CNN with wider layers
  Current model (32→64→64 ≈27K params) may be underfitting with 11K windows.
  Deeper ResNet-style blocks (64→128→128→64) with skip connections.
  Hypothesis: More capacity captures complex insulin:glucose dynamics.

Usage:
    python tools/cgmencode/exp_pk_forecast_v4.py --experiment 365 --device cuda --quick
    python tools/cgmencode/exp_pk_forecast_v4.py --experiment all --device cuda
"""

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, TensorDataset
import json, os, sys, time, argparse
from pathlib import Path

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


# ─── Data Loading (reused from v3) ───

def find_patient_dirs(patients_dir):
    base = Path(patients_dir)
    return sorted([d for d in base.iterdir()
                   if d.is_dir() and (d / 'training').exists()])


def load_patient_profile_isf(train_dir):
    """Load ISF from patient profile for normalization."""
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
    """Load base + PK features with extended future window."""
    patient_dirs = find_patient_dirs(patients_dir)
    if max_patients:
        patient_dirs = patient_dirs[:max_patients]
    print(f"Loading {len(patient_dirs)} patients "
          f"(history={history_steps}, horizon={max_horizon})")

    all_base_train, all_base_val = [], []
    all_pk_train, all_pk_val = [], []
    all_isf_train, all_isf_val = [], []
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
            glucose_hist = w_b[:history_steps, 0]
            if np.isnan(glucose_hist).mean() > 0.2:
                continue
            glucose_future = w_b[history_steps:, 0]
            if np.isnan(glucose_future).any():
                continue
            windows_b.append(w_b)
            windows_p.append(w_p)

        if not windows_b:
            continue

        windows_b = np.array(windows_b)
        windows_p = np.array(windows_p)
        n = len(windows_b)
        split = int(0.8 * n)

        all_base_train.append(windows_b[:split])
        all_base_val.append(windows_b[split:])
        all_pk_train.append(windows_p[:split])
        all_pk_val.append(windows_p[split:])

        if load_isf and isf is not None:
            all_isf_train.append(np.full(split, isf, dtype=np.float32))
            all_isf_val.append(np.full(n - split, isf, dtype=np.float32))
        elif load_isf:
            all_isf_train.append(np.full(split, 50.0, dtype=np.float32))
            all_isf_val.append(np.full(n - split, 50.0, dtype=np.float32))

        print(f"  {pdir.name}: {n} windows ({split} train, {n-split} val)"
              f"{f', ISF={isf:.1f}' if isf else ''}")

    bt = np.concatenate(all_base_train)
    bv = np.concatenate(all_base_val)
    pt = np.concatenate(all_pk_train)
    pv = np.concatenate(all_pk_val)
    print(f"Total: {len(bt)} train, {len(bv)} val")

    if load_isf:
        it = np.concatenate(all_isf_train)
        iv = np.concatenate(all_isf_val)
        return bt, bv, pt, pv, it, iv
    return bt, bv, pt, pv


def extract_targets(base_windows, history_steps, horizons):
    targets = []
    for name, offset in horizons.items():
        idx = history_steps + offset - 1
        targets.append(base_windows[:, idx, 0])
    return np.stack(targets, axis=1)


# ─── Baseline Models (from v3) ───

class ForecastCNN(nn.Module):
    """Standard 1D-CNN forecaster (baseline)."""
    def __init__(self, in_channels, n_horizons=3):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv1d(in_channels, 32, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(32),
            nn.Conv1d(32, 64, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(64),
            nn.Conv1d(64, 64, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(64),
            nn.AdaptiveAvgPool1d(1),
        )
        self.head = nn.Sequential(
            nn.Linear(64, 32), nn.ReLU(), nn.Dropout(0.2),
            nn.Linear(32, n_horizons),
        )

    def forward(self, x):
        x = x.permute(0, 2, 1)
        feat = self.conv(x).squeeze(-1)
        return self.head(feat)


class ForecastCNNWithFuture(nn.Module):
    """CNN with separate history + future PK branches (EXP-356 winner)."""
    def __init__(self, hist_channels, pk_channels, n_horizons=3):
        super().__init__()
        self.hist_conv = nn.Sequential(
            nn.Conv1d(hist_channels, 32, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(32),
            nn.Conv1d(32, 64, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(64),
            nn.Conv1d(64, 64, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(64),
            nn.AdaptiveAvgPool1d(1),
        )
        self.future_conv = nn.Sequential(
            nn.Conv1d(pk_channels, 16, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(16),
            nn.Conv1d(16, 16, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(16),
            nn.AdaptiveAvgPool1d(1),
        )
        self.head = nn.Sequential(
            nn.Linear(64 + 16, 32), nn.ReLU(), nn.Dropout(0.2),
            nn.Linear(32, n_horizons),
        )

    def forward(self, x_hist, x_future):
        x_h = x_hist.permute(0, 2, 1)
        x_f = x_future.permute(0, 2, 1)
        h_feat = self.hist_conv(x_h).squeeze(-1)
        f_feat = self.future_conv(x_f).squeeze(-1)
        return self.head(torch.cat([h_feat, f_feat], dim=1))


# ─── New Models ───

class DilatedResBlock(nn.Module):
    """Residual block with dilated convolution."""
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


class DilatedTCN(nn.Module):
    """WaveNet-style Dilated Temporal CNN for forecasting.

    Uses exponentially increasing dilations (1,2,4,8,16,32) to cover
    large receptive fields efficiently. Skip connections at each layer
    aggregate multi-scale temporal features.
    """
    def __init__(self, in_channels, n_horizons=8, hidden=64,
                 dilations=(1, 2, 4, 8, 16, 32), dropout=0.1):
        super().__init__()
        self.input_proj = nn.Sequential(
            nn.Conv1d(in_channels, hidden, 1),
            nn.ReLU(), nn.BatchNorm1d(hidden),
        )
        self.blocks = nn.ModuleList([
            DilatedResBlock(hidden, d, dropout=dropout) for d in dilations
        ])
        self.skip_proj = nn.Conv1d(hidden * len(dilations), hidden, 1)
        self.pool = nn.AdaptiveAvgPool1d(1)
        self.head = nn.Sequential(
            nn.Linear(hidden, 64), nn.ReLU(), nn.Dropout(dropout),
            nn.Linear(64, n_horizons),
        )

    def forward(self, x):
        x = x.permute(0, 2, 1)
        x = self.input_proj(x)
        skips = []
        for block in self.blocks:
            x = block(x)
            skips.append(x)
        # Aggregate skip connections
        combined = torch.cat(skips, dim=1)
        feat = self.pool(F.relu(self.skip_proj(combined))).squeeze(-1)
        return self.head(feat)


class DilatedTCNWithFuture(nn.Module):
    """Dilated TCN with separate future PK branch."""
    def __init__(self, hist_channels, pk_channels, n_horizons=8,
                 hidden=64, dilations=(1, 2, 4, 8, 16, 32)):
        super().__init__()
        self.hist_tcn = DilatedTCN(hist_channels, hidden, hidden, dilations)
        # Override hist_tcn head — we'll use our own
        self.hist_tcn.head = nn.Identity()
        self.hist_tcn.pool = nn.AdaptiveAvgPool1d(1)
        # Rebuild hist_tcn to just produce features
        self.hist_input = nn.Sequential(
            nn.Conv1d(hist_channels, hidden, 1),
            nn.ReLU(), nn.BatchNorm1d(hidden),
        )
        self.hist_blocks = nn.ModuleList([
            DilatedResBlock(hidden, d) for d in dilations
        ])
        self.hist_skip = nn.Conv1d(hidden * len(dilations), hidden, 1)
        self.hist_pool = nn.AdaptiveAvgPool1d(1)

        self.future_conv = nn.Sequential(
            nn.Conv1d(pk_channels, 32, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(32),
            nn.Conv1d(32, 32, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(32),
            nn.AdaptiveAvgPool1d(1),
        )
        self.head = nn.Sequential(
            nn.Linear(hidden + 32, 64), nn.ReLU(), nn.Dropout(0.1),
            nn.Linear(64, n_horizons),
        )

    def forward(self, x_hist, x_future):
        # History through dilated TCN
        h = x_hist.permute(0, 2, 1)
        h = self.hist_input(h)
        skips = []
        for block in self.hist_blocks:
            h = block(h)
            skips.append(h)
        combined = torch.cat(skips, dim=1)
        h_feat = self.hist_pool(F.relu(self.hist_skip(combined))).squeeze(-1)

        # Future PK
        f = x_future.permute(0, 2, 1)
        f_feat = self.future_conv(f).squeeze(-1)

        return self.head(torch.cat([h_feat, f_feat], dim=1))


class HorizonConditionedCNN(nn.Module):
    """CNN with per-horizon FiLM modulation.

    Shared backbone extracts features. Each horizon gets a learned
    affine transformation (gamma, beta) that adapts the feature
    representation. This lets the model learn "for h30, emphasize
    glucose trend" vs "for h720, emphasize PK decay".
    """
    def __init__(self, in_channels, n_horizons=8, hidden=64):
        super().__init__()
        self.n_horizons = n_horizons
        self.conv = nn.Sequential(
            nn.Conv1d(in_channels, 32, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(32),
            nn.Conv1d(32, hidden, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(hidden),
            nn.Conv1d(hidden, hidden, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(hidden),
            nn.AdaptiveAvgPool1d(1),
        )
        # Per-horizon FiLM: gamma and beta for each horizon
        self.film_gamma = nn.Parameter(torch.ones(n_horizons, hidden))
        self.film_beta = nn.Parameter(torch.zeros(n_horizons, hidden))
        # Per-horizon output heads (small but separate)
        self.heads = nn.ModuleList([
            nn.Sequential(nn.Linear(hidden, 32), nn.ReLU(), nn.Linear(32, 1))
            for _ in range(n_horizons)
        ])

    def forward(self, x):
        x = x.permute(0, 2, 1)
        feat = self.conv(x).squeeze(-1)  # (B, hidden)
        outputs = []
        for i in range(self.n_horizons):
            modulated = feat * self.film_gamma[i] + self.film_beta[i]
            outputs.append(self.heads[i](modulated))
        return torch.cat(outputs, dim=1)  # (B, n_horizons)


class HorizonConditionedCNNWithFuture(nn.Module):
    """Horizon-conditioned CNN + separate future PK branch."""
    def __init__(self, hist_channels, pk_channels, n_horizons=8, hidden=64):
        super().__init__()
        self.n_horizons = n_horizons
        self.hist_conv = nn.Sequential(
            nn.Conv1d(hist_channels, 32, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(32),
            nn.Conv1d(32, hidden, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(hidden),
            nn.Conv1d(hidden, hidden, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(hidden),
            nn.AdaptiveAvgPool1d(1),
        )
        self.future_conv = nn.Sequential(
            nn.Conv1d(pk_channels, 32, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(32),
            nn.Conv1d(32, 32, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(32),
            nn.AdaptiveAvgPool1d(1),
        )
        combined_dim = hidden + 32
        self.film_gamma = nn.Parameter(torch.ones(n_horizons, combined_dim))
        self.film_beta = nn.Parameter(torch.zeros(n_horizons, combined_dim))
        self.heads = nn.ModuleList([
            nn.Sequential(nn.Linear(combined_dim, 32), nn.ReLU(), nn.Linear(32, 1))
            for _ in range(n_horizons)
        ])

    def forward(self, x_hist, x_future):
        h = x_hist.permute(0, 2, 1)
        f = x_future.permute(0, 2, 1)
        h_feat = self.hist_conv(h).squeeze(-1)
        f_feat = self.future_conv(f).squeeze(-1)
        feat = torch.cat([h_feat, f_feat], dim=1)
        outputs = []
        for i in range(self.n_horizons):
            modulated = feat * self.film_gamma[i] + self.film_beta[i]
            outputs.append(self.heads[i](modulated))
        return torch.cat(outputs, dim=1)


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
        self.shortcut = nn.Conv1d(in_ch, out_ch, 1) if in_ch != out_ch else nn.Identity()

    def forward(self, x):
        residual = self.shortcut(x)
        out = F.relu(self.bn1(self.conv1(x)))
        out = self.dropout(out)
        out = self.bn2(self.conv2(out))
        return F.relu(out + residual)


class ResNetCNN(nn.Module):
    """Deeper ResNet-style CNN forecaster.

    Architecture: 64→128→128→64 with residual connections.
    ~4× more parameters than baseline (32→64→64).
    """
    def __init__(self, in_channels, n_horizons=8, dropout=0.1):
        super().__init__()
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
        self.head = nn.Sequential(
            nn.Linear(64, 64), nn.ReLU(), nn.Dropout(dropout),
            nn.Linear(64, n_horizons),
        )

    def forward(self, x):
        x = x.permute(0, 2, 1)
        x = self.stem(x)
        x = self.blocks(x)
        feat = self.pool(x).squeeze(-1)
        return self.head(feat)


class ResNetCNNWithFuture(nn.Module):
    """ResNet CNN + future PK branch."""
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
    """Train with MSE loss and early stopping."""
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
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            wait = 0
        else:
            wait += 1
            if wait >= patience:
                break

    if best_state:
        model.load_state_dict(best_state)
    return model


def evaluate_model(model, val_loader, device, horizons):
    """Evaluate forecast MAE per horizon."""
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
        mae = float(np.mean(np.abs(preds[:, i] - targets[:, i])) * GLUCOSE_SCALE)
        per_horizon[name] = mae

    return {
        'mae_overall': float(np.mean(list(per_horizon.values()))),
        'mae_per_horizon': per_horizon,
    }, preds, targets


# ─── Feature Preparation ───

def prepare_features(base_train, base_val, pk_train, pk_val,
                     history_steps, horizons, use_8ch=True, use_future_pk=True,
                     use_isf=False, isf_train=None, isf_val=None):
    """Build input tensors and targets for training.

    Returns: (hist_train, hist_val, future_train, future_val,
              targets_train, targets_val, has_future)
    """
    n_horizons = len(horizons)
    max_horizon = max(horizons.values())

    # Targets — base_grid glucose is already 0-1 (glucose_raw/400)
    targets_train = extract_targets(base_train, history_steps, horizons)
    targets_val = extract_targets(base_val, history_steps, horizons)

    # History features — glucose already in 0-1 from build_nightscout_grid
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
        # All 8 channels already normalized by build_nightscout_grid
        hist_t = base_train[:, :history_steps].copy()
        hist_v = base_val[:, :history_steps].copy()
        # Replace glucose channel with ISF-normalized version if applicable
        hist_t[:, :, 0:1] = glucose_t
        hist_v[:, :, 0:1] = glucose_v
    else:
        hist_t = glucose_t
        hist_v = glucose_v

    # Future PK features
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
    """Convert numpy arrays to TensorDatasets."""
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

def run_exp_365(args, seeds=None, train_kw=None, max_patients=None):
    """EXP-365: Horizon-Selective Ensemble.

    Train ISF and non-ISF models separately, then combine predictions.
    Strategies:
    1. simple_average — average all horizon predictions
    2. horizon_selective — ISF for h≤120, non-ISF for h≥240, avg for h180
    3. learned_blend — train per-horizon blend weights on validation set
    """
    device = torch.device(args.device)
    seeds = seeds or SEEDS
    train_kw = train_kw or {}
    quick = max_patients is not None
    horizons = HORIZONS_STANDARD if quick else HORIZONS_EXTENDED
    n_horizons = len(horizons)
    max_horizon = max(horizons.values())
    history_steps = 72

    # Load data with ISF
    data = load_forecast_data(args.patients_dir, history_steps, max_horizon,
                              max_patients, load_isf=True)
    base_t, base_v, pk_t, pk_v, isf_t, isf_v = data

    results = {
        'experiment': 'EXP-365',
        'description': 'Horizon-selective ensemble of ISF and non-ISF models',
        'horizons': list(horizons.keys()),
        'variants': {},
    }

    for seed in seeds:
        print(f"\n  seed={seed}:")
        torch.manual_seed(seed)
        np.random.seed(seed)

        # --- Train non-ISF model (8ch + future PK) ---
        feat = prepare_features(base_t, base_v, pk_t, pk_v, history_steps,
                                horizons, use_8ch=True, use_future_pk=True,
                                use_isf=False)
        hist_t, hist_v, fut_t, fut_v, tgt_t, tgt_v, has_fut = feat
        train_ds, val_ds = to_tensors(hist_t, hist_v, fut_t, fut_v,
                                      tgt_t, tgt_v, has_fut)
        train_loader = DataLoader(train_ds, batch_size=256, shuffle=True)
        val_loader = DataLoader(val_ds, batch_size=256)

        t0 = time.time()
        model_raw = ForecastCNNWithFuture(hist_t.shape[2], 4, n_horizons)
        model_raw = train_model(model_raw, train_loader, val_loader, device,
                                **train_kw)
        res_raw, preds_raw, tgts_raw = evaluate_model(model_raw, val_loader,
                                                       device, horizons)
        tgts_mg_raw = tgts_raw * GLUCOSE_SCALE
        preds_mg_raw = preds_raw * GLUCOSE_SCALE

        h_str = ', '.join(f"{k}={v:.1f}" for k, v in res_raw['mae_per_horizon'].items())
        print(f"    8ch_future_pk... MAE={res_raw['mae_overall']:.1f} [{h_str}]  ({time.time()-t0:.0f}s)")
        results['variants'][f"8ch_future_pk_s{seed}"] = res_raw

        # --- Train ISF model (ISF + 8ch + future PK) ---
        torch.manual_seed(seed)
        np.random.seed(seed)
        feat_isf = prepare_features(base_t, base_v, pk_t, pk_v, history_steps,
                                    horizons, use_8ch=True, use_future_pk=True,
                                    use_isf=True, isf_train=isf_t, isf_val=isf_v)
        hist_ti, hist_vi, fut_ti, fut_vi, tgt_ti, tgt_vi, has_fi = feat_isf
        train_ds_i, val_ds_i = to_tensors(hist_ti, hist_vi, fut_ti, fut_vi,
                                          tgt_ti, tgt_vi, has_fi)
        train_loader_i = DataLoader(train_ds_i, batch_size=256, shuffle=True)
        val_loader_i = DataLoader(val_ds_i, batch_size=256)

        t0 = time.time()
        model_isf = ForecastCNNWithFuture(hist_ti.shape[2], 4, n_horizons)
        model_isf = train_model(model_isf, train_loader_i, val_loader_i, device,
                                **train_kw)

        # Get ISF predictions in mg/dL
        model_isf.eval()
        all_preds_isf, all_tgts_isf = [], []
        with torch.no_grad():
            for batch in val_loader_i:
                inputs = [b.to(device) for b in batch[:-1]]
                p = model_isf(*inputs).cpu().numpy()
                t = batch[-1].numpy()
                all_preds_isf.append(p)
                all_tgts_isf.append(t)
        preds_isf_scaled = np.concatenate(all_preds_isf)
        tgts_isf_scaled = np.concatenate(all_tgts_isf)

        # Convert ISF-scaled back to mg/dL
        inv_scale = (isf_v / GLUCOSE_SCALE).reshape(-1, 1)
        preds_mg_isf = preds_isf_scaled * inv_scale * GLUCOSE_SCALE
        tgts_mg_isf = tgts_isf_scaled * inv_scale * GLUCOSE_SCALE

        res_isf = {}
        for i, name in enumerate(horizons.keys()):
            res_isf[name] = float(np.mean(np.abs(preds_mg_isf[:, i] - tgts_mg_isf[:, i])))
        res_isf_full = {
            'mae_overall': float(np.mean(list(res_isf.values()))),
            'mae_per_horizon': res_isf,
        }
        h_str = ', '.join(f"{k}={v:.1f}" for k, v in res_isf.items())
        print(f"    isf_8ch_future_pk... MAE={res_isf_full['mae_overall']:.1f} [{h_str}]  ({time.time()-t0:.0f}s)")
        results['variants'][f"isf_8ch_future_pk_s{seed}"] = res_isf_full

        # --- Strategy 1: Simple average ---
        preds_avg = (preds_mg_raw + preds_mg_isf) / 2
        per_h_avg = {}
        for i, name in enumerate(horizons.keys()):
            per_h_avg[name] = float(np.mean(np.abs(preds_avg[:, i] - tgts_mg_raw[:, i])))
        res_avg = {
            'mae_overall': float(np.mean(list(per_h_avg.values()))),
            'mae_per_horizon': per_h_avg,
        }
        h_str = ', '.join(f"{k}={v:.1f}" for k, v in per_h_avg.items())
        print(f"    ensemble_average... MAE={res_avg['mae_overall']:.1f} [{h_str}]")
        results['variants'][f"ensemble_average_s{seed}"] = res_avg

        # --- Strategy 2: Horizon-selective ---
        horizon_names = list(horizons.keys())
        preds_selective = np.zeros_like(preds_mg_raw)
        for i, name in enumerate(horizon_names):
            h_mins = int(name.replace('h', ''))
            if h_mins <= 120:
                preds_selective[:, i] = preds_mg_isf[:, i]  # ISF for short
            elif h_mins >= 240:
                preds_selective[:, i] = preds_mg_raw[:, i]  # Raw for long
            else:
                preds_selective[:, i] = (preds_mg_isf[:, i] + preds_mg_raw[:, i]) / 2

        per_h_sel = {}
        for i, name in enumerate(horizon_names):
            per_h_sel[name] = float(np.mean(np.abs(preds_selective[:, i] - tgts_mg_raw[:, i])))
        res_sel = {
            'mae_overall': float(np.mean(list(per_h_sel.values()))),
            'mae_per_horizon': per_h_sel,
        }
        h_str = ', '.join(f"{k}={v:.1f}" for k, v in per_h_sel.items())
        print(f"    ensemble_selective... MAE={res_sel['mae_overall']:.1f} [{h_str}]")
        results['variants'][f"ensemble_selective_s{seed}"] = res_sel

        # --- Strategy 3: Learned per-horizon blend weights ---
        # Optimize alpha_h to minimize val MAE for each horizon independently
        preds_learned = np.zeros_like(preds_mg_raw)
        blend_weights = {}
        for i, name in enumerate(horizon_names):
            best_alpha, best_mae = 0, float('inf')
            for alpha in np.arange(0, 1.01, 0.05):
                blended = alpha * preds_mg_isf[:, i] + (1 - alpha) * preds_mg_raw[:, i]
                mae = np.mean(np.abs(blended - tgts_mg_raw[:, i]))
                if mae < best_mae:
                    best_mae = mae
                    best_alpha = alpha
            preds_learned[:, i] = best_alpha * preds_mg_isf[:, i] + (1 - best_alpha) * preds_mg_raw[:, i]
            blend_weights[name] = float(best_alpha)

        per_h_learned = {}
        for i, name in enumerate(horizon_names):
            per_h_learned[name] = float(np.mean(np.abs(preds_learned[:, i] - tgts_mg_raw[:, i])))
        res_learned = {
            'mae_overall': float(np.mean(list(per_h_learned.values()))),
            'mae_per_horizon': per_h_learned,
            'blend_weights': blend_weights,
        }
        h_str = ', '.join(f"{k}={v:.1f}" for k, v in per_h_learned.items())
        w_str = ', '.join(f"{k}={v:.2f}" for k, v in blend_weights.items())
        print(f"    ensemble_learned... MAE={res_learned['mae_overall']:.1f} [{h_str}]")
        print(f"      weights (ISF fraction): {w_str}")
        results['variants'][f"ensemble_learned_s{seed}"] = res_learned

    results['summary'] = _aggregate_results(results['variants'], seeds, horizons)
    return results


def run_exp_366(args, seeds=None, train_kw=None, max_patients=None):
    """EXP-366: Dilated Temporal CNN (WaveNet-style).

    Compare:
    1. baseline_cnn — standard 3-layer CNN + future PK (EXP-364 champion)
    2. dilated_tcn — WaveNet-style dilated CNN (dilation 1,2,4,8,16,32)
    3. dilated_tcn_future — dilated TCN + future PK branch
    4. dilated_tcn_deep — deeper dilated TCN (hidden=128, double dilations)
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
                              max_patients)
    base_t, base_v, pk_t, pk_v = data

    feat = prepare_features(base_t, base_v, pk_t, pk_v, history_steps,
                            horizons, use_8ch=True, use_future_pk=True)
    hist_t, hist_v, fut_t, fut_v, tgt_t, tgt_v, _ = feat

    results = {
        'experiment': 'EXP-366',
        'description': 'Dilated TCN vs standard CNN',
        'horizons': list(horizons.keys()),
        'variants': {},
    }

    variant_configs = [
        ('baseline_cnn', 'future'),
        ('dilated_tcn', 'history_only'),
        ('dilated_tcn_future', 'future'),
        ('dilated_tcn_deep', 'future_deep'),
    ]

    for seed in seeds:
        print(f"\n  seed={seed}:")

        for variant_name, config in variant_configs:
            torch.manual_seed(seed)
            np.random.seed(seed)
            t0 = time.time()
            print(f"    {variant_name}...", end=' ', flush=True)

            hist_channels = hist_t.shape[2]

            if config == 'history_only':
                # TCN on history only (all 8ch)
                model = DilatedTCN(hist_channels, n_horizons, hidden=64)
                train_ds, val_ds = to_tensors(hist_t, hist_v, None, None,
                                              tgt_t, tgt_v, False)
            elif config == 'future':
                if variant_name == 'baseline_cnn':
                    model = ForecastCNNWithFuture(hist_channels, 4, n_horizons)
                else:
                    model = DilatedTCNWithFuture(hist_channels, 4, n_horizons,
                                                hidden=64)
                train_ds, val_ds = to_tensors(hist_t, hist_v, fut_t, fut_v,
                                              tgt_t, tgt_v, True)
            elif config == 'future_deep':
                model = DilatedTCNWithFuture(hist_channels, 4, n_horizons,
                                            hidden=128,
                                            dilations=(1, 2, 4, 8, 16, 32, 64))
                train_ds, val_ds = to_tensors(hist_t, hist_v, fut_t, fut_v,
                                              tgt_t, tgt_v, True)

            train_loader = DataLoader(train_ds, batch_size=256, shuffle=True)
            val_loader = DataLoader(val_ds, batch_size=256)

            model = train_model(model, train_loader, val_loader, device,
                                **train_kw)
            res, _, _ = evaluate_model(model, val_loader, device, horizons)

            h_str = ', '.join(f"{k}={v:.1f}" for k, v in res['mae_per_horizon'].items())
            print(f"MAE={res['mae_overall']:.1f} [{h_str}]  ({time.time()-t0:.0f}s)")
            results['variants'][f"{variant_name}_s{seed}"] = res

    results['summary'] = _aggregate_results(results['variants'], seeds, horizons)
    return results


def run_exp_367(args, seeds=None, train_kw=None, max_patients=None):
    """EXP-367: Horizon-Conditioned ForecastCNN.

    Compare:
    1. baseline_cnn — standard shared-head CNN + future PK
    2. horizon_cond — per-horizon FiLM + separate heads
    3. horizon_cond_future — horizon-conditioned + future PK
    4. horizon_cond_isf — horizon-conditioned + ISF + future PK
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
    base_t, base_v, pk_t, pk_v, isf_t, isf_v = data

    results = {
        'experiment': 'EXP-367',
        'description': 'Horizon-conditioned FiLM forecaster',
        'horizons': list(horizons.keys()),
        'variants': {},
    }

    variant_configs = [
        ('baseline_cnn_future', False, True, False),
        ('horizon_cond_history', False, False, False),
        ('horizon_cond_future', False, True, False),
        ('horizon_cond_isf_future', True, True, True),
    ]
    # (name, use_isf, use_future_pk, is_isf_variant)

    for seed in seeds:
        print(f"\n  seed={seed}:")

        for variant_name, use_isf, use_future, _ in variant_configs:
            torch.manual_seed(seed)
            np.random.seed(seed)
            t0 = time.time()
            print(f"    {variant_name}...", end=' ', flush=True)

            feat = prepare_features(
                base_t, base_v, pk_t, pk_v, history_steps, horizons,
                use_8ch=True, use_future_pk=use_future, use_isf=use_isf,
                isf_train=isf_t if use_isf else None,
                isf_val=isf_v if use_isf else None)
            ht, hv, ft, fv, tt, tv, has_f = feat
            hist_channels = ht.shape[2]

            if use_future:
                if 'horizon_cond' in variant_name:
                    model = HorizonConditionedCNNWithFuture(
                        hist_channels, 4, n_horizons)
                else:
                    model = ForecastCNNWithFuture(hist_channels, 4, n_horizons)
            else:
                model = HorizonConditionedCNN(hist_channels, n_horizons)

            train_ds, val_ds = to_tensors(ht, hv, ft, fv, tt, tv, has_f)
            train_loader = DataLoader(train_ds, batch_size=256, shuffle=True)
            val_loader = DataLoader(val_ds, batch_size=256)

            model = train_model(model, train_loader, val_loader, device,
                                **train_kw)

            if use_isf:
                # Evaluate with ISF inverse scaling
                model.eval()
                all_p, all_t = [], []
                with torch.no_grad():
                    for batch in val_loader:
                        inputs = [b.to(device) for b in batch[:-1]]
                        p = model(*inputs).cpu().numpy()
                        all_p.append(p)
                        all_t.append(batch[-1].numpy())
                preds = np.concatenate(all_p)
                tgts = np.concatenate(all_t)
                inv_scale = (isf_v / GLUCOSE_SCALE).reshape(-1, 1)
                preds_mg = preds * inv_scale * GLUCOSE_SCALE
                tgts_mg = tgts * inv_scale * GLUCOSE_SCALE
                per_h = {}
                for i, name in enumerate(horizons.keys()):
                    per_h[name] = float(np.mean(np.abs(preds_mg[:, i] - tgts_mg[:, i])))
                res = {
                    'mae_overall': float(np.mean(list(per_h.values()))),
                    'mae_per_horizon': per_h,
                }
            else:
                res, _, _ = evaluate_model(model, val_loader, device, horizons)

            h_str = ', '.join(f"{k}={v:.1f}" for k, v in res['mae_per_horizon'].items())
            print(f"MAE={res['mae_overall']:.1f} [{h_str}]  ({time.time()-t0:.0f}s)")
            results['variants'][f"{variant_name}_s{seed}"] = res

    results['summary'] = _aggregate_results(results['variants'], seeds, horizons)
    return results


def run_exp_368(args, seeds=None, train_kw=None, max_patients=None):
    """EXP-368: Residual CNN with wider layers.

    Compare:
    1. baseline_cnn — standard 32→64→64 CNN + future PK (~27K params)
    2. resnet_cnn — ResNet 64→128→128→64 + future PK (~100K params)
    3. resnet_cnn_isf — ResNet + ISF normalization + future PK
    4. wide_cnn — standard CNN but 64→128→128 (wider, no residual)
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
    base_t, base_v, pk_t, pk_v, isf_t, isf_v = data

    results = {
        'experiment': 'EXP-368',
        'description': 'ResNet architecture vs baseline CNN',
        'horizons': list(horizons.keys()),
        'variants': {},
    }

    variant_configs = [
        ('baseline_cnn', False),
        ('resnet_cnn', False),
        ('resnet_cnn_isf', True),
        ('wide_cnn', False),
    ]

    for seed in seeds:
        print(f"\n  seed={seed}:")

        for variant_name, use_isf in variant_configs:
            torch.manual_seed(seed)
            np.random.seed(seed)
            t0 = time.time()
            print(f"    {variant_name}...", end=' ', flush=True)

            feat = prepare_features(
                base_t, base_v, pk_t, pk_v, history_steps, horizons,
                use_8ch=True, use_future_pk=True, use_isf=use_isf,
                isf_train=isf_t if use_isf else None,
                isf_val=isf_v if use_isf else None)
            ht, hv, ft, fv, tt, tv, has_f = feat
            hist_channels = ht.shape[2]

            if 'resnet' in variant_name:
                model = ResNetCNNWithFuture(hist_channels, 4, n_horizons)
            elif variant_name == 'wide_cnn':
                # Wider baseline: 64→128→128 (no residual connections)
                model = ForecastCNNWithFuture(hist_channels, 4, n_horizons)
                # Override hist_conv with wider layers
                model.hist_conv = nn.Sequential(
                    nn.Conv1d(hist_channels, 64, kernel_size=3, padding=1),
                    nn.ReLU(), nn.BatchNorm1d(64),
                    nn.Conv1d(64, 128, kernel_size=3, padding=1),
                    nn.ReLU(), nn.BatchNorm1d(128),
                    nn.Conv1d(128, 128, kernel_size=3, padding=1),
                    nn.ReLU(), nn.BatchNorm1d(128),
                    nn.AdaptiveAvgPool1d(1),
                )
                model.head = nn.Sequential(
                    nn.Linear(128 + 16, 64), nn.ReLU(), nn.Dropout(0.2),
                    nn.Linear(64, n_horizons),
                )
            else:
                model = ForecastCNNWithFuture(hist_channels, 4, n_horizons)

            n_params = sum(p.numel() for p in model.parameters())

            train_ds, val_ds = to_tensors(ht, hv, ft, fv, tt, tv, has_f)
            train_loader = DataLoader(train_ds, batch_size=256, shuffle=True)
            val_loader = DataLoader(val_ds, batch_size=256)

            model = train_model(model, train_loader, val_loader, device,
                                **train_kw)

            if use_isf:
                model.eval()
                all_p, all_t = [], []
                with torch.no_grad():
                    for batch in val_loader:
                        inputs = [b.to(device) for b in batch[:-1]]
                        p = model(*inputs).cpu().numpy()
                        all_p.append(p)
                        all_t.append(batch[-1].numpy())
                preds = np.concatenate(all_p)
                tgts = np.concatenate(all_t)
                inv_scale = (isf_v / GLUCOSE_SCALE).reshape(-1, 1)
                preds_mg = preds * inv_scale * GLUCOSE_SCALE
                tgts_mg = tgts * inv_scale * GLUCOSE_SCALE
                per_h = {}
                for i, name in enumerate(horizons.keys()):
                    per_h[name] = float(np.mean(np.abs(preds_mg[:, i] - tgts_mg[:, i])))
                res = {
                    'mae_overall': float(np.mean(list(per_h.values()))),
                    'mae_per_horizon': per_h,
                    'n_params': n_params,
                }
            else:
                res, _, _ = evaluate_model(model, val_loader, device, horizons)
                res['n_params'] = n_params

            h_str = ', '.join(f"{k}={v:.1f}" for k, v in res['mae_per_horizon'].items())
            print(f"MAE={res['mae_overall']:.1f} [{h_str}]  ({n_params:,} params, {time.time()-t0:.0f}s)")
            results['variants'][f"{variant_name}_s{seed}"] = res

    results['summary'] = _aggregate_results(results['variants'], seeds, horizons)
    return results


# ─── Aggregation ───

def _aggregate_results(variants, seeds, horizons):
    """Aggregate per-seed results into mean ± std."""
    from collections import defaultdict
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
            vals = [r['mae_per_horizon'].get(hname, float('nan')) for r in runs]
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
        description='EXP-365-368: Horizon-adaptive & architecture experiments')
    parser.add_argument('--experiment', type=str, default='365',
                        help='Experiment: 365, 366, 367, 368, or all')
    parser.add_argument('--device', type=str, default='cpu')
    parser.add_argument('--quick', action='store_true',
                        help='Quick mode: 1 seed, 4 patients, 30 epochs')
    parser.add_argument('--patients-dir', type=str,
                        default='externals/ns-data/patients')
    args = parser.parse_args()

    experiments = {
        '365': ('exp365_ensemble', run_exp_365),
        '366': ('exp366_dilated_tcn', run_exp_366),
        '367': ('exp367_horizon_cond', run_exp_367),
        '368': ('exp368_resnet', run_exp_368),
    }

    if args.quick:
        seeds = SEEDS_QUICK
        train_kw = {'epochs': QUICK_EPOCHS, 'patience': QUICK_PATIENCE}
        max_patients = QUICK_PATIENTS
    else:
        seeds = SEEDS
        train_kw = {'epochs': 60, 'patience': 15}
        max_patients = None

    to_run = list(experiments.keys()) if args.experiment == 'all' else [args.experiment]

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
