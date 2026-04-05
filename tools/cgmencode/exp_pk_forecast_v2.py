#!/usr/bin/env python3
"""EXP-356 through EXP-359: Horizon-Aware & Functional PK Forecasting

Building on EXP-352-355 findings:
- EXP-352: Treatment channels (sparse or PK) nearly irrelevant — glucose
  autocorrelation dominates at all horizons with a standard CNN.
- EXP-354: Individual PK channels don't help; adding them hurts slightly.
- EXP-355: **Future PK projection helps dramatically at h120 (-6.7 mg/dL)**
  but hurts at h30 (+3.7). The model trades short-term for long-term accuracy.

Key insight: PK information encodes FUTURE metabolic trajectory, not past.
The CNN can already learn glucose trend from history — what it can't see is
how insulin/carb absorption will change glucose direction in the future.

EXP-356 — Extended horizons with future PK projection
  Add 3h (180min) and 4h (240min) horizons where insulin dynamics dominate.
  Hypothesis: PK advantage grows with horizon length.

EXP-357 — Horizon-aware dual-head architecture
  Separate heads for short-term (glucose-only) and long-term (glucose+PK).
  Hypothesis: Avoid the h30 regression while keeping h120 gains.

EXP-358 — PK residual features
  residual = glucose_roc - PK_predicted_roc. This "model mismatch" tells the
  forecaster where the parametric PK model is wrong.
  Hypothesis: Residual features outperform raw PK channels.

EXP-359 — Functional inner product coupling
  ⟨insulin_activity(t), glucose_roc(t)⟩ as a scalar coupling feature.
  Captures the RELATIONSHIP between PK curves and glucose response.
  Hypothesis: Relational features help more than raw PK channels.

Usage:
    python tools/cgmencode/exp_pk_forecast_v2.py --experiment 356 --device cuda --quick
    python tools/cgmencode/exp_pk_forecast_v2.py --experiment all --device cuda
"""

import numpy as np
import torch
import torch.nn as nn
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

# Extended horizons: 30min through 4h
HORIZONS_EXTENDED = {
    'h30': 6,     # 30 min
    'h60': 12,    # 60 min
    'h120': 24,   # 120 min
    'h180': 36,   # 180 min (3h)
    'h240': 48,   # 240 min (4h)
}
HORIZONS_STANDARD = {
    'h30': 6, 'h60': 12, 'h120': 24,
}

QUICK_PATIENTS = 4
QUICK_EPOCHS = 30
QUICK_PATIENCE = 8

# PK channel indices in continuous_pk output (8 channels)
PK_IDX = {
    'insulin_total': 0, 'insulin_net': 1, 'basal_ratio': 2,
    'carb_rate': 3, 'carb_accel': 4, 'hepatic_production': 5,
    'net_balance': 6, 'isf_curve': 7,
}
PK_NORMS = [0.05, 0.05, 2.0, 0.5, 0.05, 3.0, 20.0, 200.0]


# ─── Data Loading (reuses exp_pk_forecast infrastructure) ───

def find_patient_dirs(patients_dir):
    """Find all patient directories with training data."""
    base = Path(patients_dir)
    dirs = sorted([d for d in base.iterdir() if d.is_dir()
                   and (d / 'training').exists()])
    return dirs


def load_extended_forecast_data(patients_dir, history_steps=72,
                                max_horizon=48, max_patients=None):
    """Load base + PK features with extended future window.

    Returns:
        base_train, base_val: (N, T_total, 8)
        pk_train, pk_val: (N, T_total, 8) PK channels
        T_total = history_steps + max_horizon
    """
    patient_dirs = find_patient_dirs(patients_dir)
    if max_patients:
        patient_dirs = patient_dirs[:max_patients]
    print(f"Loading {len(patient_dirs)} patients "
          f"(history={history_steps}, horizon={max_horizon})")

    all_base_train, all_base_val = [], []
    all_pk_train, all_pk_val = [], []
    window_size = history_steps + max_horizon
    stride = history_steps // 2

    for pdir in patient_dirs:
        train_dir = str(pdir / 'training')
        df, base_grid = build_nightscout_grid(train_dir)  # df + (T, 8)
        pk_grid = build_continuous_pk_features(df)  # (T, 8)

        n_pts = min(len(base_grid), len(pk_grid))
        base_grid = base_grid[:n_pts].astype(np.float32)
        pk_grid = pk_grid[:n_pts].astype(np.float32)
        np.nan_to_num(base_grid, copy=False)
        np.nan_to_num(pk_grid, copy=False)

        # Create windows
        windows_b, windows_p = [], []
        for start in range(0, n_pts - window_size + 1, stride):
            w_b = base_grid[start:start + window_size]
            w_p = pk_grid[start:start + window_size]
            # Skip if glucose history has too many gaps
            glucose_hist = w_b[:history_steps, 0]
            if np.isnan(glucose_hist).mean() > 0.2:
                continue
            # Skip if glucose targets have NaN
            glucose_future = w_b[history_steps:, 0]
            if np.isnan(glucose_future).any():
                continue
            windows_b.append(w_b)
            windows_p.append(w_p)

        if not windows_b:
            continue

        windows_b = np.array(windows_b)
        windows_p = np.array(windows_p)

        # Per-patient chronological split
        n = len(windows_b)
        split = int(0.8 * n)
        all_base_train.append(windows_b[:split])
        all_base_val.append(windows_b[split:])
        all_pk_train.append(windows_p[:split])
        all_pk_val.append(windows_p[split:])
        print(f"  {pdir.name}: {n} windows ({split} train, {n-split} val)")

    bt = np.concatenate(all_base_train)
    bv = np.concatenate(all_base_val)
    pt = np.concatenate(all_pk_train)
    pv = np.concatenate(all_pk_val)
    print(f"Total: {len(bt)} train, {len(bv)} val")
    return bt, bv, pt, pv


def extract_targets(base_windows, history_steps, horizons):
    """Extract glucose targets at specified horizons.

    Args:
        base_windows: (N, T_total, 8)
        history_steps: int
        horizons: dict {name: step_offset}

    Returns:
        (N, n_horizons) normalized glucose targets
    """
    targets = []
    for name, offset in horizons.items():
        idx = history_steps + offset - 1  # -1 because offset=6 means 6th step
        targets.append(base_windows[:, idx, 0])  # glucose is channel 0
    return np.stack(targets, axis=1)


def persistence_baseline(base_val, history_steps, horizons):
    """Persistence baseline: predict last glucose value."""
    last_glucose = base_val[:, history_steps - 1, 0]  # normalized
    targets = extract_targets(base_val, history_steps, horizons)
    per_horizon = {}
    for i, (name, _) in enumerate(horizons.items()):
        mae = float(np.mean(np.abs(last_glucose - targets[:, i])) * GLUCOSE_SCALE)
        per_horizon[name] = mae
    return {
        'mae_overall': float(np.mean(list(per_horizon.values()))),
        'mae_per_horizon': per_horizon,
    }


# ─── Models ───

class ForecastCNN(nn.Module):
    """Standard 1D-CNN forecaster."""
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
    """CNN with separate history + future PK branches."""
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
            nn.AdaptiveAvgPool1d(1),
        )
        self.head = nn.Sequential(
            nn.Linear(64 + 16, 32), nn.ReLU(), nn.Dropout(0.2),
            nn.Linear(32, n_horizons),
        )

    def forward(self, hist, future_pk):
        h = hist.permute(0, 2, 1)
        f = future_pk.permute(0, 2, 1)
        h_feat = self.hist_conv(h).squeeze(-1)
        f_feat = self.future_conv(f).squeeze(-1)
        return self.head(torch.cat([h_feat, f_feat], dim=1))


class HorizonAwareCNN(nn.Module):
    """EXP-357: Separate heads per horizon group.

    Short-term (h30, h60): glucose-only encoder
    Long-term (h120+): glucose + PK encoder with future projection

    This avoids the trade-off seen in EXP-355 where the single model
    sacrificed short-term accuracy to improve long-term.
    """
    def __init__(self, glucose_channels, pk_channels, future_pk_channels,
                 n_short=2, n_long=3):
        super().__init__()
        # Short-term encoder: glucose trend only
        self.short_conv = nn.Sequential(
            nn.Conv1d(glucose_channels, 32, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(32),
            nn.Conv1d(32, 64, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(64),
            nn.AdaptiveAvgPool1d(1),
        )
        self.short_head = nn.Sequential(
            nn.Linear(64, 32), nn.ReLU(), nn.Dropout(0.2),
            nn.Linear(32, n_short),
        )

        # Long-term encoder: glucose + PK history + future PK
        total_hist = glucose_channels + pk_channels
        self.long_hist_conv = nn.Sequential(
            nn.Conv1d(total_hist, 32, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(32),
            nn.Conv1d(32, 64, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(64),
            nn.AdaptiveAvgPool1d(1),
        )
        self.long_future_conv = nn.Sequential(
            nn.Conv1d(future_pk_channels, 16, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(16),
            nn.AdaptiveAvgPool1d(1),
        )
        self.long_head = nn.Sequential(
            nn.Linear(64 + 16, 32), nn.ReLU(), nn.Dropout(0.2),
            nn.Linear(32, n_long),
        )

    def forward(self, glucose_hist, pk_hist, future_pk):
        # Short-term: glucose only
        g = glucose_hist.permute(0, 2, 1)
        s_feat = self.short_conv(g).squeeze(-1)
        short_pred = self.short_head(s_feat)

        # Long-term: glucose + PK + future
        combined = torch.cat([glucose_hist, pk_hist], dim=2)
        c = combined.permute(0, 2, 1)
        l_feat = self.long_hist_conv(c).squeeze(-1)
        f = future_pk.permute(0, 2, 1)
        f_feat = self.long_future_conv(f).squeeze(-1)
        long_pred = self.long_head(torch.cat([l_feat, f_feat], dim=1))

        return torch.cat([short_pred, long_pred], dim=1)


# ─── Feature Engineering ───

def compute_glucose_roc(base_windows, history_steps):
    """Compute rate of change of glucose (finite difference).

    Returns (N, T_hist) array of glucose derivatives (normalized).
    """
    glucose = base_windows[:, :history_steps, 0]  # (N, T_hist)
    roc = np.zeros_like(glucose)
    roc[:, 1:] = glucose[:, 1:] - glucose[:, :-1]
    return roc


def compute_pk_roc(pk_windows, history_steps):
    """Compute rate of change of key PK channels.

    Returns dict of channel_name: (N, T_hist) arrays.
    """
    result = {}
    for name, idx in [('insulin_net', 1), ('carb_rate', 3), ('net_balance', 6)]:
        ch = pk_windows[:, :history_steps, idx]
        roc = np.zeros_like(ch)
        roc[:, 1:] = ch[:, 1:] - ch[:, :-1]
        result[name] = roc
    return result


def compute_pk_residuals(base_windows, pk_windows, history_steps):
    """EXP-358: Compute residual = glucose_roc - PK_predicted_roc.

    The PK model predicts that net_balance ≈ dBG/dt. The residual captures
    where this model is wrong — exactly what the forecaster needs.

    Returns (N, T_hist, 1) residual feature.
    """
    glucose_roc = compute_glucose_roc(base_windows, history_steps)
    # net_balance is PK's prediction of glucose rate of change
    # Normalize to same scale as glucose_roc
    net_balance = pk_windows[:, :history_steps, PK_IDX['net_balance']]
    # net_balance is normalized by 20.0, glucose_roc by ~400 per step
    # Scale net_balance to glucose units: net_balance * 20 / 400 = net_balance * 0.05
    pk_predicted_roc = net_balance * 0.05
    residual = glucose_roc - pk_predicted_roc
    return residual[:, :, np.newaxis]  # (N, T_hist, 1)


def compute_functional_inner_products(base_windows, pk_windows, history_steps):
    """EXP-359: Compute functional inner products between PK and glucose.

    ⟨f, g⟩ = Σ f(t) * g(t) / T  (discrete L² inner product)

    Captures the COUPLING between insulin activity and glucose response.
    High inner product = PK model matches observed glucose dynamics.

    Returns (N, n_features) scalar coupling features.
    """
    glucose_roc = compute_glucose_roc(base_windows, history_steps)  # (N, T)
    T = glucose_roc.shape[1]

    features = []
    feature_names = []

    for pk_name, pk_idx in [('insulin_net', 1), ('carb_rate', 3),
                             ('net_balance', 6)]:
        pk_ch = pk_windows[:, :history_steps, pk_idx]  # (N, T)

        # Inner product with glucose rate of change
        ip = np.sum(pk_ch * glucose_roc, axis=1) / T  # (N,)
        features.append(ip)
        feature_names.append(f'ip_{pk_name}_glucose_roc')

        # Inner product with glucose level (captures correlation)
        glucose = base_windows[:, :history_steps, 0]
        ip_level = np.sum(pk_ch * glucose, axis=1) / T
        features.append(ip_level)
        feature_names.append(f'ip_{pk_name}_glucose')

    # Cross PK inner products
    insulin = pk_windows[:, :history_steps, PK_IDX['insulin_net']]
    carbs = pk_windows[:, :history_steps, PK_IDX['carb_rate']]
    ip_cross = np.sum(insulin * carbs, axis=1) / T
    features.append(ip_cross)
    feature_names.append('ip_insulin_carb')

    result = np.stack(features, axis=1)  # (N, 7)
    return result, feature_names


# ─── Training ───

def train_forecast(train_x, train_y, val_x, val_y, device,
                   epochs=80, batch_size=256, patience=15, lr=1e-3):
    """Train standard ForecastCNN."""
    in_ch = train_x.shape[2]
    n_horizons = train_y.shape[1]
    model = ForecastCNN(in_ch, n_horizons).to(device)
    return _train_loop(model, train_x, train_y, val_x, val_y, device,
                       epochs, batch_size, patience, lr)


def train_with_future(train_hist, train_fpk, train_y,
                      val_hist, val_fpk, val_y, device,
                      epochs=80, batch_size=256, patience=15, lr=1e-3):
    """Train ForecastCNNWithFuture."""
    hist_ch = train_hist.shape[2]
    pk_ch = train_fpk.shape[2]
    n_horizons = train_y.shape[1]
    model = ForecastCNNWithFuture(hist_ch, pk_ch, n_horizons).to(device)

    train_xt = torch.from_numpy(train_hist).float()
    train_ft = torch.from_numpy(train_fpk).float()
    train_yt = torch.from_numpy(train_y).float()
    val_xt = torch.from_numpy(val_hist).float().to(device)
    val_ft = torch.from_numpy(val_fpk).float().to(device)
    val_yt = torch.from_numpy(val_y).float().to(device)

    ds = TensorDataset(train_xt, train_ft, train_yt)
    dl = DataLoader(ds, batch_size=batch_size, shuffle=True,
                    pin_memory=(device.type == 'cuda'))

    criterion = nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-5)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, patience=5, factor=0.5)

    best_mae = float('inf')
    best_metrics = None
    wait = 0

    for epoch in range(epochs):
        model.train()
        for xb, fb, yb in dl:
            xb, fb, yb = xb.to(device), fb.to(device), yb.to(device)
            pred = model(xb, fb)
            loss = criterion(pred, yb)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

        model.eval()
        with torch.no_grad():
            val_pred = model(val_xt, val_ft)
            val_loss = criterion(val_pred, val_yt).item()
            mae_per_h = (val_pred - val_yt).abs().mean(dim=0) * GLUCOSE_SCALE
            overall_mae = mae_per_h.mean().item()

        scheduler.step(val_loss)
        if overall_mae < best_mae:
            best_mae = overall_mae
            best_metrics = _make_metrics(overall_mae, mae_per_h, val_loss,
                                         list(HORIZONS_EXTENDED.keys())[:train_y.shape[1]])
            wait = 0
        else:
            wait += 1
            if wait >= patience:
                break

    return best_metrics


def train_horizon_aware(train_glucose, train_pk_hist, train_fpk, train_y,
                        val_glucose, val_pk_hist, val_fpk, val_y,
                        device, n_short=2, n_long=3,
                        epochs=80, batch_size=256, patience=15, lr=1e-3):
    """Train HorizonAwareCNN (EXP-357)."""
    g_ch = train_glucose.shape[2]
    pk_ch = train_pk_hist.shape[2]
    fpk_ch = train_fpk.shape[2]
    model = HorizonAwareCNN(g_ch, pk_ch, fpk_ch, n_short, n_long).to(device)

    train_gt = torch.from_numpy(train_glucose).float()
    train_pt = torch.from_numpy(train_pk_hist).float()
    train_ft = torch.from_numpy(train_fpk).float()
    train_yt = torch.from_numpy(train_y).float()
    val_gt = torch.from_numpy(val_glucose).float().to(device)
    val_pt = torch.from_numpy(val_pk_hist).float().to(device)
    val_ft = torch.from_numpy(val_fpk).float().to(device)
    val_yt = torch.from_numpy(val_y).float().to(device)

    ds = TensorDataset(train_gt, train_pt, train_ft, train_yt)
    dl = DataLoader(ds, batch_size=batch_size, shuffle=True,
                    pin_memory=(device.type == 'cuda'))

    criterion = nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-5)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, patience=5, factor=0.5)

    best_mae = float('inf')
    best_metrics = None
    wait = 0

    horizon_names = list(HORIZONS_EXTENDED.keys())[:train_y.shape[1]]

    for epoch in range(epochs):
        model.train()
        for gb, pb, fb, yb in dl:
            gb = gb.to(device)
            pb = pb.to(device)
            fb = fb.to(device)
            yb = yb.to(device)
            pred = model(gb, pb, fb)
            loss = criterion(pred, yb)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

        model.eval()
        with torch.no_grad():
            val_pred = model(val_gt, val_pt, val_ft)
            val_loss = criterion(val_pred, val_yt).item()
            mae_per_h = (val_pred - val_yt).abs().mean(dim=0) * GLUCOSE_SCALE
            overall_mae = mae_per_h.mean().item()

        scheduler.step(val_loss)
        if overall_mae < best_mae:
            best_mae = overall_mae
            best_metrics = _make_metrics(overall_mae, mae_per_h, val_loss,
                                         horizon_names)
            wait = 0
        else:
            wait += 1
            if wait >= patience:
                break

    return best_metrics


def _train_loop(model, train_x, train_y, val_x, val_y, device,
                epochs, batch_size, patience, lr):
    """Shared training loop for simple CNN models."""
    n_horizons = train_y.shape[1]
    criterion = nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-5)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, patience=5, factor=0.5)

    train_xt = torch.from_numpy(train_x).float()
    train_yt = torch.from_numpy(train_y).float()
    val_xt = torch.from_numpy(val_x).float().to(device)
    val_yt = torch.from_numpy(val_y).float().to(device)

    ds = TensorDataset(train_xt, train_yt)
    dl = DataLoader(ds, batch_size=batch_size, shuffle=True,
                    pin_memory=(device.type == 'cuda'))

    best_mae = float('inf')
    best_metrics = None
    wait = 0

    horizon_names = list(HORIZONS_EXTENDED.keys())[:n_horizons]

    for epoch in range(epochs):
        model.train()
        for xb, yb in dl:
            xb, yb = xb.to(device), yb.to(device)
            pred = model(xb)
            loss = criterion(pred, yb)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

        model.eval()
        with torch.no_grad():
            val_pred = model(val_xt)
            val_loss = criterion(val_pred, val_yt).item()
            mae_per_h = (val_pred - val_yt).abs().mean(dim=0) * GLUCOSE_SCALE
            overall_mae = mae_per_h.mean().item()

        scheduler.step(val_loss)
        if overall_mae < best_mae:
            best_mae = overall_mae
            best_metrics = _make_metrics(overall_mae, mae_per_h, val_loss,
                                         horizon_names)
            wait = 0
        else:
            wait += 1
            if wait >= patience:
                break

    return best_metrics


def _make_metrics(overall_mae, mae_per_h, val_loss, horizon_names):
    """Build metrics dict from training results."""
    return {
        'mae_overall': float(overall_mae),
        'mae_per_horizon': {name: float(mae_per_h[i])
                            for i, name in enumerate(horizon_names)},
        'mse': float(val_loss),
        'rmse': float(np.sqrt(val_loss) * GLUCOSE_SCALE),
    }


def aggregate_seed_results(seed_results):
    """Aggregate metrics across multi-seed runs."""
    overall_maes = [r['mae_overall'] for r in seed_results]
    agg = {
        'mae_overall_mean': float(np.mean(overall_maes)),
        'mae_overall_std': float(np.std(overall_maes)),
        'per_seed': seed_results,
    }
    all_horizons = set()
    for r in seed_results:
        all_horizons.update(r['mae_per_horizon'].keys())
    for hname in sorted(all_horizons):
        vals = [r['mae_per_horizon'].get(hname, float('nan'))
                for r in seed_results]
        agg[f'mae_{hname}_mean'] = float(np.mean(vals))
        agg[f'mae_{hname}_std'] = float(np.std(vals))
    return agg


# ─── EXP-356: Extended Horizons with Future PK ───

def run_exp_356(base_train, base_val, pk_train, pk_val,
                history_steps, device, output_dir, seeds=SEEDS, train_kw=None):
    """Test PK benefit at extended horizons (3h, 4h) where insulin dynamics dominate."""
    if train_kw is None:
        train_kw = {}
    print("\n" + "=" * 60)
    print("EXP-356: Extended Horizons with Future PK Projection")
    print("=" * 60)

    horizons = HORIZONS_EXTENDED
    max_horizon = max(horizons.values())
    targets_train = extract_targets(base_train, history_steps, horizons)
    targets_val = extract_targets(base_val, history_steps, horizons)
    persist = persistence_baseline(base_val, history_steps, horizons)

    # Future PK channels
    future_pk_idx = [PK_IDX['insulin_net'], PK_IDX['basal_ratio'],
                     PK_IDX['carb_rate'], PK_IDX['net_balance']]
    fpk_train = pk_train[:, history_steps:history_steps + max_horizon, :][:, :, future_pk_idx]
    fpk_val = pk_val[:, history_steps:history_steps + max_horizon, :][:, :, future_pk_idx]

    results = {
        'experiment': 'EXP-356',
        'title': 'Extended Horizons with Future PK Projection',
        'hypothesis': 'PK advantage grows with horizon: 30min=0, 120min=moderate, 240min=large',
        'history_steps': history_steps,
        'horizons': {k: v * 5 for k, v in horizons.items()},
        'seeds': seeds,
        'persistence_baseline': persist,
        'variants': {},
    }

    # Variant 1: glucose_only
    print("\n─── glucose_only (5 horizons) ───")
    glucose_train = base_train[:, :history_steps, :1].copy()
    glucose_val = base_val[:, :history_steps, :1].copy()
    sr = []
    for seed in seeds:
        torch.manual_seed(seed); np.random.seed(seed)
        m = train_forecast(glucose_train, targets_train, glucose_val, targets_val,
                           device, **train_kw)
        sr.append(m)
        _print_horizon_mae(seed, m, horizons)
    results['variants']['glucose_only'] = aggregate_seed_results(sr)

    # Variant 2: glucose + future PK (ForecastCNNWithFuture)
    print("\n─── glucose + future_pk ───")
    sr = []
    for seed in seeds:
        torch.manual_seed(seed); np.random.seed(seed)
        m = train_with_future(glucose_train, fpk_train, targets_train,
                              glucose_val, fpk_val, targets_val,
                              device, **train_kw)
        sr.append(m)
        _print_horizon_mae(seed, m, horizons)
    results['variants']['glucose+future_pk'] = aggregate_seed_results(sr)

    # Variant 3: baseline_8ch (no future)
    print("\n─── baseline_8ch (no future) ───")
    base_hist_train = base_train[:, :history_steps].copy()
    base_hist_val = base_val[:, :history_steps].copy()
    sr = []
    for seed in seeds:
        torch.manual_seed(seed); np.random.seed(seed)
        m = train_forecast(base_hist_train, targets_train,
                           base_hist_val, targets_val, device, **train_kw)
        sr.append(m)
        _print_horizon_mae(seed, m, horizons)
    results['variants']['baseline_8ch'] = aggregate_seed_results(sr)

    # Variant 4: baseline_8ch + future PK
    print("\n─── baseline_8ch + future_pk ───")
    sr = []
    for seed in seeds:
        torch.manual_seed(seed); np.random.seed(seed)
        m = train_with_future(base_hist_train, fpk_train, targets_train,
                              base_hist_val, fpk_val, targets_val,
                              device, **train_kw)
        sr.append(m)
        _print_horizon_mae(seed, m, horizons)
    results['variants']['baseline_8ch+future_pk'] = aggregate_seed_results(sr)

    # Compute per-horizon delta (future_pk vs glucose_only)
    results['horizon_analysis'] = _horizon_delta_analysis(results['variants'],
                                                          'glucose_only',
                                                          'glucose+future_pk',
                                                          horizons)
    return results


# ─── EXP-357: Horizon-Aware Dual-Head ───

def run_exp_357(base_train, base_val, pk_train, pk_val,
                history_steps, device, output_dir, seeds=SEEDS, train_kw=None):
    """Test horizon-aware architecture with separate short/long-term heads."""
    if train_kw is None:
        train_kw = {}
    print("\n" + "=" * 60)
    print("EXP-357: Horizon-Aware Dual-Head Architecture")
    print("=" * 60)

    horizons = HORIZONS_EXTENDED
    max_horizon = max(horizons.values())
    targets_train = extract_targets(base_train, history_steps, horizons)
    targets_val = extract_targets(base_val, history_steps, horizons)

    # Prepare inputs
    glucose_train = base_train[:, :history_steps, :1].copy()
    glucose_val = base_val[:, :history_steps, :1].copy()

    pk_hist_idx = [PK_IDX['insulin_net'], PK_IDX['carb_rate'],
                   PK_IDX['net_balance']]
    pk_hist_train = pk_train[:, :history_steps, :][:, :, pk_hist_idx].copy()
    pk_hist_val = pk_val[:, :history_steps, :][:, :, pk_hist_idx].copy()

    future_pk_idx = [PK_IDX['insulin_net'], PK_IDX['basal_ratio'],
                     PK_IDX['carb_rate'], PK_IDX['net_balance']]
    fpk_train = pk_train[:, history_steps:history_steps + max_horizon, :][:, :, future_pk_idx]
    fpk_val = pk_val[:, history_steps:history_steps + max_horizon, :][:, :, future_pk_idx]

    results = {
        'experiment': 'EXP-357',
        'title': 'Horizon-Aware Dual-Head Architecture',
        'hypothesis': ('Separate glucose-only short head + PK long head '
                       'avoids h30 regression while keeping h120+ gains'),
        'history_steps': history_steps,
        'horizons': {k: v * 5 for k, v in horizons.items()},
        'seeds': seeds,
        'variants': {},
    }

    # Control: single-head glucose_only
    print("\n─── control: glucose_only single-head ───")
    sr = []
    for seed in seeds:
        torch.manual_seed(seed); np.random.seed(seed)
        m = train_forecast(glucose_train, targets_train, glucose_val,
                           targets_val, device, **train_kw)
        sr.append(m)
        _print_horizon_mae(seed, m, horizons)
    results['variants']['glucose_only_single'] = aggregate_seed_results(sr)

    # Control: future PK single-head (baseline from EXP-356)
    print("\n─── control: glucose+future_pk single-head ───")
    sr = []
    for seed in seeds:
        torch.manual_seed(seed); np.random.seed(seed)
        m = train_with_future(glucose_train, fpk_train, targets_train,
                              glucose_val, fpk_val, targets_val,
                              device, **train_kw)
        sr.append(m)
        _print_horizon_mae(seed, m, horizons)
    results['variants']['glucose+future_pk_single'] = aggregate_seed_results(sr)

    # Test: Horizon-aware dual-head
    # Short: h30, h60 (2 horizons) — glucose only
    # Long: h120, h180, h240 (3 horizons) — glucose + PK + future PK
    print("\n─── horizon_aware dual-head ───")
    sr = []
    for seed in seeds:
        torch.manual_seed(seed); np.random.seed(seed)
        m = train_horizon_aware(
            glucose_train, pk_hist_train, fpk_train, targets_train,
            glucose_val, pk_hist_val, fpk_val, targets_val,
            device, n_short=2, n_long=3, **train_kw)
        sr.append(m)
        _print_horizon_mae(seed, m, horizons)
    results['variants']['horizon_aware'] = aggregate_seed_results(sr)

    return results


# ─── EXP-358: PK Residual Features ───

def run_exp_358(base_train, base_val, pk_train, pk_val,
                history_steps, device, output_dir, seeds=SEEDS, train_kw=None):
    """Test residual = glucose_roc - PK_predicted_roc as a feature."""
    if train_kw is None:
        train_kw = {}
    print("\n" + "=" * 60)
    print("EXP-358: PK Residual Features")
    print("=" * 60)

    horizons = HORIZONS_STANDARD
    targets_train = extract_targets(base_train, history_steps, horizons)
    targets_val = extract_targets(base_val, history_steps, horizons)

    results = {
        'experiment': 'EXP-358',
        'title': 'PK Residual Features for Forecasting',
        'hypothesis': ('residual = glucose_roc - PK_roc captures model mismatch; '
                       'should outperform raw PK channels'),
        'history_steps': history_steps,
        'seeds': seeds,
        'variants': {},
    }

    # Compute residual features
    residual_train = compute_pk_residuals(base_train, pk_train, history_steps)
    residual_val = compute_pk_residuals(base_val, pk_val, history_steps)

    # Compute glucose ROC as a feature too
    glucose_roc_train = compute_glucose_roc(base_train, history_steps)[:, :, np.newaxis]
    glucose_roc_val = compute_glucose_roc(base_val, history_steps)[:, :, np.newaxis]

    glucose_train = base_train[:, :history_steps, :1].copy()
    glucose_val = base_val[:, :history_steps, :1].copy()

    variants = {
        'glucose_only': glucose_train,
        'glucose+roc': np.concatenate([glucose_train, glucose_roc_train], axis=2),
        'glucose+residual': np.concatenate([glucose_train, residual_train], axis=2),
        'glucose+roc+residual': np.concatenate([glucose_train, glucose_roc_train,
                                                 residual_train], axis=2),
    }
    variants_val = {
        'glucose_only': glucose_val,
        'glucose+roc': np.concatenate([glucose_val, glucose_roc_val], axis=2),
        'glucose+residual': np.concatenate([glucose_val, residual_val], axis=2),
        'glucose+roc+residual': np.concatenate([glucose_val, glucose_roc_val,
                                                 residual_val], axis=2),
    }

    for vname in variants:
        print(f"\n─── {vname} ({variants[vname].shape[2]} ch) ───")
        sr = []
        for seed in seeds:
            torch.manual_seed(seed); np.random.seed(seed)
            m = train_forecast(variants[vname], targets_train,
                               variants_val[vname], targets_val, device, **train_kw)
            sr.append(m)
            print(f"  seed={seed}: MAE={m['mae_overall']:.1f}")
        results['variants'][vname] = aggregate_seed_results(sr)
        a = results['variants'][vname]
        print(f"  MEAN: MAE={a['mae_overall_mean']:.1f} ± {a['mae_overall_std']:.1f}")

    # Delta analysis
    if 'glucose_only' in results['variants']:
        base = results['variants']['glucose_only']['mae_overall_mean']
        for v, d in results['variants'].items():
            d['delta_vs_glucose_only'] = d['mae_overall_mean'] - base

    return results


# ─── EXP-359: Functional Inner Product Coupling ───

def run_exp_359(base_train, base_val, pk_train, pk_val,
                history_steps, device, output_dir, seeds=SEEDS, train_kw=None):
    """Test functional inner product features (PK-glucose coupling)."""
    if train_kw is None:
        train_kw = {}
    print("\n" + "=" * 60)
    print("EXP-359: Functional Inner Product Coupling Features")
    print("=" * 60)

    horizons = HORIZONS_STANDARD
    targets_train = extract_targets(base_train, history_steps, horizons)
    targets_val = extract_targets(base_val, history_steps, horizons)

    results = {
        'experiment': 'EXP-359',
        'title': 'Functional Inner Product Coupling Features',
        'hypothesis': ('⟨PK, glucose⟩ inner products capture relationship '
                       'between metabolic state and glucose response'),
        'history_steps': history_steps,
        'seeds': seeds,
        'variants': {},
    }

    # Compute inner product features (scalar per window)
    ip_train, ip_names = compute_functional_inner_products(
        base_train, pk_train, history_steps)
    ip_val, _ = compute_functional_inner_products(
        base_val, pk_val, history_steps)
    results['inner_product_features'] = ip_names
    print(f"  Inner product features: {ip_names}")
    print(f"  Shape: train={ip_train.shape}, val={ip_val.shape}")

    glucose_train = base_train[:, :history_steps, :1].copy()
    glucose_val = base_val[:, :history_steps, :1].copy()

    # Broadcast scalar features across time (head injection via tiling)
    ip_train_tiled = np.tile(ip_train[:, np.newaxis, :],
                              (1, history_steps, 1))  # (N, T, 7)
    ip_val_tiled = np.tile(ip_val[:, np.newaxis, :],
                            (1, history_steps, 1))

    variants = {
        'glucose_only': glucose_train,
        'glucose+ip_all': np.concatenate([glucose_train, ip_train_tiled], axis=2),
    }
    variants_val = {
        'glucose_only': glucose_val,
        'glucose+ip_all': np.concatenate([glucose_val, ip_val_tiled], axis=2),
    }

    # Also test individual inner products
    for i, name in enumerate(ip_names):
        feat_t = ip_train_tiled[:, :, i:i+1]
        feat_v = ip_val_tiled[:, :, i:i+1]
        variants[f'glucose+{name}'] = np.concatenate([glucose_train, feat_t], axis=2)
        variants_val[f'glucose+{name}'] = np.concatenate([glucose_val, feat_v], axis=2)

    for vname in variants:
        print(f"\n─── {vname} ({variants[vname].shape[2]} ch) ───")
        sr = []
        for seed in seeds:
            torch.manual_seed(seed); np.random.seed(seed)
            m = train_forecast(variants[vname], targets_train,
                               variants_val[vname], targets_val, device, **train_kw)
            sr.append(m)
            print(f"  seed={seed}: MAE={m['mae_overall']:.1f}")
        results['variants'][vname] = aggregate_seed_results(sr)
        a = results['variants'][vname]
        print(f"  MEAN: MAE={a['mae_overall_mean']:.1f} ± {a['mae_overall_std']:.1f}")

    if 'glucose_only' in results['variants']:
        base = results['variants']['glucose_only']['mae_overall_mean']
        for v, d in results['variants'].items():
            d['delta_vs_glucose_only'] = d['mae_overall_mean'] - base

    return results


# ─── Utilities ───

def _print_horizon_mae(seed, metrics, horizons):
    """Print per-horizon MAE for a single seed run."""
    parts = [f"{h}={metrics['mae_per_horizon'].get(h, 0):.1f}"
             for h in horizons.keys()]
    print(f"  seed={seed}: MAE={metrics['mae_overall']:.1f} [{', '.join(parts)}]")


def _horizon_delta_analysis(variants, control_name, test_name, horizons):
    """Compute per-horizon delta between two variants."""
    if control_name not in variants or test_name not in variants:
        return {}
    ctrl = variants[control_name]
    test = variants[test_name]
    analysis = {}
    for hname in horizons:
        c = ctrl.get(f'mae_{hname}_mean', float('nan'))
        t = test.get(f'mae_{hname}_mean', float('nan'))
        analysis[hname] = {
            'control_mae': c, 'test_mae': t,
            'delta': t - c, 'pct_change': (t - c) / c * 100 if c else 0,
        }
    return analysis


# ─── Main ───

def main():
    parser = argparse.ArgumentParser(description='EXP-356-359: Horizon-Aware PK Forecasting')
    parser.add_argument('--patients-dir', type=str,
                        default='externals/ns-data/patients',
                        help='Path to patient directories')
    parser.add_argument('--output-dir', type=str,
                        default='externals/experiments',
                        help='Directory for result JSON files')
    parser.add_argument('--device', type=str, default='cpu',
                        help='Device: cpu or cuda')
    parser.add_argument('--experiment', type=str, default='all',
                        help='Which experiment: 356, 357, 358, 359, or all')
    parser.add_argument('--history-steps', type=int, default=72,
                        help='History window in 5-min steps (default: 72 = 6h)')
    parser.add_argument('--quick', action='store_true',
                        help='Quick mode: 1 seed, 4 patients, 30 epochs')
    args = parser.parse_args()

    seeds = SEEDS_QUICK if args.quick else SEEDS
    max_patients = QUICK_PATIENTS if args.quick else None
    train_kw = dict(epochs=QUICK_EPOCHS, patience=QUICK_PATIENCE) if args.quick else {}

    device = torch.device(args.device)
    print(f"Device: {device}")
    os.makedirs(args.output_dir, exist_ok=True)

    exps = args.experiment.lower()
    run_356 = exps in ('356', 'all')
    run_357 = exps in ('357', 'all')
    run_358 = exps in ('358', 'all')
    run_359 = exps in ('359', 'all')

    # Extended horizons need larger future window
    max_horizon_needed = max(HORIZONS_EXTENDED.values()) if (run_356 or run_357) else max(HORIZONS_STANDARD.values())

    bt, bv, pt, pv = load_extended_forecast_data(
        args.patients_dir, history_steps=args.history_steps,
        max_horizon=max_horizon_needed, max_patients=max_patients)

    all_results = {}
    t0 = time.time()

    if run_356:
        t1 = time.time()
        r = run_exp_356(bt, bv, pt, pv, args.history_steps, device,
                        args.output_dir, seeds=seeds, train_kw=train_kw)
        r['elapsed_seconds'] = time.time() - t1
        all_results['EXP-356'] = r
        _save_results(r, args.output_dir, 'exp356_extended_horizons.json')

    if run_357:
        t1 = time.time()
        r = run_exp_357(bt, bv, pt, pv, args.history_steps, device,
                        args.output_dir, seeds=seeds, train_kw=train_kw)
        r['elapsed_seconds'] = time.time() - t1
        all_results['EXP-357'] = r
        _save_results(r, args.output_dir, 'exp357_horizon_aware.json')

    if run_358:
        t1 = time.time()
        r = run_exp_358(bt, bv, pt, pv, args.history_steps, device,
                        args.output_dir, seeds=seeds, train_kw=train_kw)
        r['elapsed_seconds'] = time.time() - t1
        all_results['EXP-358'] = r
        _save_results(r, args.output_dir, 'exp358_pk_residual.json')

    if run_359:
        t1 = time.time()
        r = run_exp_359(bt, bv, pt, pv, args.history_steps, device,
                        args.output_dir, seeds=seeds, train_kw=train_kw)
        r['elapsed_seconds'] = time.time() - t1
        all_results['EXP-359'] = r
        _save_results(r, args.output_dir, 'exp359_functional_ip.json')

    total = time.time() - t0
    print(f"\nTotal elapsed: {total:.0f}s")
    _print_summary(all_results)


def _save_results(results, output_dir, filename):
    outfile = os.path.join(output_dir, filename)
    with open(outfile, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nSaved: {outfile}")


def _print_summary(all_results):
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for eid, r in all_results.items():
        print(f"\n{eid}: {r.get('title', '')}")
        if 'variants' in r:
            best_v = None
            best_m = float('inf')
            for vname, vdata in r['variants'].items():
                m = vdata['mae_overall_mean']
                if m < best_m:
                    best_m = m
                    best_v = vname
            print(f"  Best: {best_v} (MAE={best_m:.1f})")
        if 'horizon_analysis' in r:
            print("  Per-horizon Δ (future_pk vs glucose_only):")
            for hname, hdata in r['horizon_analysis'].items():
                print(f"    {hname}: {hdata['delta']:+.1f} mg/dL "
                      f"({hdata['control_mae']:.1f} → {hdata['test_mae']:.1f})")


if __name__ == '__main__':
    main()
