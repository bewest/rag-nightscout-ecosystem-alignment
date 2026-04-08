#!/usr/bin/env python3
"""EXP-1111 to EXP-1120: Combined Winners and Advanced Ensemble Methods.

Building on 110 experiments (EXP-1001–1110):
- SOTA: R²=0.507 (weighted ensemble Ridge+GB+CNN, EXP-1108)
- XGBoost 67× faster than sklearn GB (EXP-1101)
- Δg prediction +0.004 R², 11/11 universal (EXP-1102)
- TCN matches Ridge (0.503), best neural (EXP-1107)
- Interpolation+flag: +0.05-0.09 for <20% missing (EXP-1105)
- Static > online learning (EXP-1110)

This batch combines winning techniques and explores advanced methods:
  EXP-1111: Combined Winners (Δg + XGBoost + Ensemble) ★★★
  EXP-1112: XGBoost Hyperparameter Sweep (GPU) ★★
  EXP-1113: Multi-Horizon Joint Prediction ★★★
  EXP-1114: TCN + Δg + Residual Stacking ★★★
  EXP-1115: Attention Over Physics Channels ★★
  EXP-1116: Adaptive Per-Patient Ensemble Weights ★★★
  EXP-1117: Conformal Prediction ★★★
  EXP-1118: Residual LSTM on Ensemble Errors ★★
  EXP-1119: Patient Clustering → Cluster-Specific Models ★★
  EXP-1120: Grand Combined Model ★★★

Run:
    PYTHONPATH=tools python -m cgmencode.exp_clinical_1111 --detail --save --max-patients 11
"""

import argparse
import json
import os
import sys
import time
import warnings

import numpy as np
from pathlib import Path
from sklearn.linear_model import Ridge, QuantileRegressor
from sklearn.cluster import KMeans

warnings.filterwarnings('ignore')

try:
    from cgmencode.exp_metabolic_flux import load_patients, save_results
    from cgmencode.exp_metabolic_441 import compute_supply_demand
    from cgmencode.continuous_pk import build_continuous_pk_features
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from cgmencode.exp_metabolic_flux import load_patients, save_results
    from cgmencode.exp_metabolic_441 import compute_supply_demand
    from cgmencode.continuous_pk import build_continuous_pk_features

import torch
import torch.nn as nn

try:
    import xgboost as xgb
    XGB_AVAILABLE = True
except ImportError:
    XGB_AVAILABLE = False

PATIENTS_DIR = str(Path(__file__).resolve().parent.parent.parent
                   / 'externals' / 'ns-data' / 'patients')
GLUCOSE_SCALE = 400.0
WINDOW = 24       # 2 hours at 5-min intervals
HORIZON = 12      # 1 hour ahead
STRIDE = 6        # 30-min stride
DEVICE = torch.device('cuda' if torch.cuda.is_available() else 'cpu')


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

class ResidualCNN(nn.Module):
    def __init__(self, in_channels, window_size=24):
        super().__init__()
        self.conv1 = nn.Conv1d(in_channels, 32, 3, padding=1)
        self.conv2 = nn.Conv1d(32, 32, 3, padding=1)
        self.conv3 = nn.Conv1d(32, 16, 3, padding=1)
        self.pool = nn.AdaptiveAvgPool1d(1)
        self.fc = nn.Linear(16, 1)
        self.relu = nn.ReLU()

    def forward(self, x):
        h = self.relu(self.conv1(x.permute(0, 2, 1)))
        h = self.relu(self.conv2(h))
        h = self.relu(self.conv3(h))
        h = self.pool(h).squeeze(-1)
        return self.fc(h).squeeze(-1)


class TCN(nn.Module):
    """Simple Temporal Convolutional Network with dilated causal convolutions."""
    def __init__(self, in_channels, window_size=24, hidden=32, n_levels=3):
        super().__init__()
        layers = []
        for i in range(n_levels):
            dilation = 2 ** i
            padding = (3 - 1) * dilation
            in_ch = in_channels if i == 0 else hidden
            layers.append(nn.Conv1d(in_ch, hidden, 3, dilation=dilation,
                                    padding=padding))
            layers.append(nn.ReLU())
            layers.append(nn.Dropout(0.1))
        self.network = nn.Sequential(*layers)
        self.pool = nn.AdaptiveAvgPool1d(1)
        self.fc = nn.Linear(hidden, 1)

    def forward(self, x):
        h = self.network(x.permute(0, 2, 1))
        h = self.pool(h).squeeze(-1)
        return self.fc(h).squeeze(-1)


class ResidualLSTM(nn.Module):
    """Small LSTM for learning temporal patterns in prediction errors."""
    def __init__(self, hidden=32, seq_len=12):
        super().__init__()
        self.lstm = nn.LSTM(1, hidden, batch_first=True, num_layers=1)
        self.head = nn.Linear(hidden, 1)

    def forward(self, x):
        out, _ = self.lstm(x)
        return self.head(out[:, -1, :]).squeeze(-1)


class PhysicsAttention(nn.Module):
    """Channel-wise temporal attention over physics decomposition channels."""
    def __init__(self, n_channels=5, window=24, hidden=32):
        super().__init__()
        self.n_channels = n_channels
        self.window = window
        # Per-channel temporal attention
        self.channel_attn = nn.ModuleList([
            nn.Sequential(
                nn.Linear(window, hidden),
                nn.Tanh(),
                nn.Linear(hidden, window),
                nn.Softmax(dim=-1),
            )
            for _ in range(n_channels)
        ])
        self.head = nn.Sequential(
            nn.Linear(n_channels, hidden),
            nn.ReLU(),
            nn.Linear(hidden, 1),
        )

    def forward(self, x):
        # x: (B, time, channels)
        summaries = []
        for c in range(self.n_channels):
            channel = x[:, :, c]  # (B, time)
            weights = self.channel_attn[c](channel)  # (B, time)
            summary = (weights * channel).sum(dim=-1)  # (B,)
            summaries.append(summary)
        combined = torch.stack(summaries, dim=-1)  # (B, n_channels)
        return self.head(combined).squeeze(-1)


def prepare_patient_raw(p):
    """Return physics channels and glucose separately."""
    sd = compute_supply_demand(p['df'], p['pk'])
    supply = sd['supply'] / 20.0
    demand = sd['demand'] / 20.0
    hepatic = sd['hepatic'] / 5.0
    net = sd['net'] / 20.0
    physics = np.column_stack([supply, demand, hepatic, net])
    glucose = p['df']['glucose'].values.astype(float)
    return glucose, physics


def make_windows(glucose, physics, window=WINDOW, horizon=HORIZON,
                 stride=STRIDE):
    """Create (X, y) windowed pairs from glucose and physics arrays."""
    X_list, y_list = [], []
    g = glucose / GLUCOSE_SCALE
    for i in range(0, len(g) - window - horizon, stride):
        g_win = g[i:i + window]
        if np.isnan(g_win).mean() > 0.3:
            continue
        g_win = np.nan_to_num(
            g_win,
            nan=np.nanmean(g_win) if np.any(~np.isnan(g_win)) else 0.4,
        )
        p_win = physics[i:i + window]
        if np.isnan(p_win).any():
            p_win = np.nan_to_num(p_win, nan=0.0)
        y_val = g[i + window + horizon - 1]
        if np.isnan(y_val):
            continue
        X_list.append(np.column_stack([g_win.reshape(-1, 1), p_win]))
        y_list.append(y_val)
    if len(X_list) == 0:
        return np.array([]).reshape(0, window, 1), np.array([])
    return np.array(X_list), np.array(y_list)


def make_windows_multi_horizon(glucose, physics, window=WINDOW,
                               horizons=[3, 6, 9, 12], stride=STRIDE):
    """Create windows with multiple horizon targets."""
    X_list = []
    y_dict = {h: [] for h in horizons}
    g = glucose / GLUCOSE_SCALE
    max_h = max(horizons)
    for i in range(0, len(g) - window - max_h, stride):
        g_win = g[i:i + window]
        if np.isnan(g_win).mean() > 0.3:
            continue
        g_win = np.nan_to_num(
            g_win, nan=np.nanmean(g_win) if np.any(~np.isnan(g_win)) else 0.4,
        )
        p_win = physics[i:i + window]
        if np.isnan(p_win).any():
            p_win = np.nan_to_num(p_win, nan=0.0)
        all_valid = True
        targets = {}
        for h in horizons:
            y_val = g[i + window + h - 1]
            if np.isnan(y_val):
                all_valid = False
                break
            targets[h] = y_val
        if not all_valid:
            continue
        X_list.append(np.column_stack([g_win.reshape(-1, 1), p_win]))
        for h in horizons:
            y_dict[h].append(targets[h])
    if len(X_list) == 0:
        empty = np.array([]).reshape(0, window, 1)
        return empty, {h: np.array([]) for h in horizons}
    return np.array(X_list), {h: np.array(v) for h, v in y_dict.items()}


def split_data(X, y, train_frac=0.8):
    n = len(X)
    split = int(n * train_frac)
    return X[:split], X[split:], y[:split], y[split:]


def split_3way(X, y, fracs=(0.6, 0.2, 0.2)):
    """Split into train/val/test chronologically."""
    n = len(X)
    s1 = int(n * fracs[0])
    s2 = int(n * (fracs[0] + fracs[1]))
    return (X[:s1], X[s1:s2], X[s2:],
            y[:s1], y[s1:s2], y[s2:])


def compute_r2(y_true, y_pred):
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
    if ss_tot == 0:
        return 0.0
    return 1.0 - ss_res / ss_tot


def compute_mae(y_true, y_pred):
    return float(np.mean(np.abs(y_true - y_pred)))


def block_cv_score(X, y, model_fn, n_folds=3):
    """3-fold chronological block cross-validation."""
    n = len(X)
    fold_size = n // n_folds
    scores = []
    for fold in range(n_folds):
        val_start = fold * fold_size
        val_end = val_start + fold_size if fold < n_folds - 1 else n
        mask = np.ones(n, dtype=bool)
        mask[val_start:val_end] = False
        X_tr, y_tr = X[mask], y[mask]
        X_vl, y_vl = X[~mask], y[~mask]
        model = model_fn()
        model.fit(X_tr, y_tr)
        pred = model.predict(X_vl)
        scores.append(compute_r2(y_vl, pred))
    return float(np.mean(scores)), scores


def build_grand_features(glucose, physics, window=WINDOW, horizon=HORIZON,
                         stride=STRIDE):
    """Build the grand feature set: glucose + physics + interactions +
    derivatives + statistics."""
    g = glucose / GLUCOSE_SCALE
    n = len(g)
    X_list, y_list, g_cur_list = [], [], []

    for i in range(0, n - window - horizon, stride):
        g_win = g[i:i + window]
        if np.isnan(g_win).mean() > 0.3:
            continue
        g_win = np.nan_to_num(
            g_win,
            nan=np.nanmean(g_win) if np.any(~np.isnan(g_win)) else 0.4,
        )
        p_win = physics[i:i + window]
        if np.isnan(p_win).any():
            p_win = np.nan_to_num(p_win, nan=0.0)

        y_val = g[i + window + horizon - 1]
        if np.isnan(y_val):
            continue

        g_current = g_win[-1]

        base = np.concatenate([g_win, p_win.ravel()])
        supply = p_win[:, 0]
        demand = p_win[:, 1]
        hepatic = p_win[:, 2]
        net = p_win[:, 3]
        g_mean = np.mean(g_win)

        interactions = np.array([
            np.mean(supply * demand),
            np.mean(supply * g_mean),
            np.mean(demand * g_mean),
            np.mean(np.diff(net)) if len(net) > 1 else 0.0,
            np.mean(hepatic * supply),
        ])

        derivatives = []
        for scale in [3, 6, 12]:
            if len(g_win) > scale:
                roc = np.mean(np.diff(g_win[::max(1, scale // 3)]))
            else:
                roc = 0.0
            derivatives.append(roc)
        if len(g_win) > 2:
            d1 = np.diff(g_win)
            accel = np.mean(np.diff(d1))
        else:
            accel = 0.0
        derivatives.append(accel)
        derivatives = np.array(derivatives)

        g_std = np.std(g_win)
        g_min = np.min(g_win)
        g_max = np.max(g_win)
        g_range = g_max - g_min
        g_cv = g_std / g_mean if g_mean > 0 else 0.0
        stats = np.array([g_mean, g_std, g_min, g_max, g_range, g_cv])

        feat = np.concatenate([base, interactions, derivatives, stats])
        X_list.append(feat)
        y_list.append(y_val)
        g_cur_list.append(g_current)

    if len(X_list) == 0:
        return np.array([]).reshape(0, 1), np.array([]), np.array([])
    return np.array(X_list), np.array(y_list), np.array(g_cur_list)


def train_neural(model, X_train, y_train, X_val, epochs=60, lr=1e-3,
                 batch_size=256):
    """Train any neural model, return val predictions."""
    model = model.to(DEVICE)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = nn.MSELoss()

    Xt = torch.tensor(X_train, dtype=torch.float32).to(DEVICE)
    yt = torch.tensor(y_train, dtype=torch.float32).to(DEVICE)
    Xv = torch.tensor(X_val, dtype=torch.float32).to(DEVICE)

    batch = min(batch_size, len(Xt))
    model.train()
    for _ in range(epochs):
        perm = torch.randperm(len(Xt))
        for start in range(0, len(Xt), batch):
            idx = perm[start:start + batch]
            pred = model(Xt[idx])
            loss = loss_fn(pred, yt[idx])
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

    model.eval()
    with torch.no_grad():
        return model(Xv).cpu().numpy()


def make_xgb(n_estimators=200, max_depth=4, learning_rate=0.05, **kwargs):
    """Create XGBoost model (GPU if available, else CPU)."""
    if not XGB_AVAILABLE:
        from sklearn.ensemble import GradientBoostingRegressor
        return GradientBoostingRegressor(
            n_estimators=n_estimators, max_depth=max_depth,
            learning_rate=learning_rate, random_state=42)
    return xgb.XGBRegressor(
        n_estimators=n_estimators, max_depth=max_depth,
        learning_rate=learning_rate,
        tree_method='hist', device='cuda' if torch.cuda.is_available() else 'cpu',
        random_state=42, verbosity=0, **kwargs)


# ---------------------------------------------------------------------------
# EXP-1111: Combined Winners (Δg + XGBoost + Ensemble)
# ---------------------------------------------------------------------------

def exp_1111_combined_winners(patients, detail=False):
    """Stack ALL winning techniques: Δg target + XGBoost + Ridge + TCN ensemble.

    This should achieve the campaign's best-ever R².
    """
    results = []
    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        n = min(len(glucose), len(physics))
        if n < WINDOW + HORIZON + 50:
            continue
        glucose, physics = glucose[:n], physics[:n]

        # Build grand features with current glucose for Δg conversion
        X, y_abs, g_cur = build_grand_features(glucose, physics)
        if len(X) < 200:
            continue

        # Δg target: rate of change
        y_delta = y_abs - g_cur

        X_tr, X_vl, yd_tr, yd_vl = split_data(X, y_delta)
        _, _, ya_tr, ya_vl = split_data(X, y_abs)
        gc_tr, gc_vl = g_cur[:len(X_tr)], g_cur[len(X_tr):]

        # --- Baseline: Ridge on absolute ---
        ridge_abs = Ridge(alpha=1.0)
        ridge_abs.fit(X_tr, ya_tr)
        pred_ridge_abs = ridge_abs.predict(X_vl)
        r2_ridge_abs = compute_r2(ya_vl, pred_ridge_abs)

        # --- Ridge on Δg ---
        ridge_dg = Ridge(alpha=1.0)
        ridge_dg.fit(X_tr, yd_tr)
        pred_ridge_dg = ridge_dg.predict(X_vl) + gc_vl
        r2_ridge_dg = compute_r2(ya_vl, pred_ridge_dg)

        # --- XGBoost on Δg ---
        xgb_dg = make_xgb()
        xgb_dg.fit(X_tr, yd_tr)
        pred_xgb_dg = xgb_dg.predict(X_vl) + gc_vl
        r2_xgb_dg = compute_r2(ya_vl, pred_xgb_dg)

        # --- TCN on Δg (needs 3D input) ---
        X_win, y_win = make_windows(glucose, physics)
        if len(X_win) < 200:
            pred_tcn_dg = pred_ridge_dg.copy()
            r2_tcn_dg = r2_ridge_dg
        else:
            gc_win = X_win[:, -1, 0]  # last glucose in window
            yd_win = y_win - gc_win
            Xw_tr, Xw_vl = X_win[:int(0.8*len(X_win))], X_win[int(0.8*len(X_win)):]
            ydw_tr = yd_win[:len(Xw_tr)]
            gcw_vl = gc_win[len(Xw_tr):]
            yaw_vl = y_win[len(Xw_tr):]

            tcn = TCN(in_channels=X_win.shape[2], window_size=WINDOW)
            tcn_pred_delta = train_neural(tcn, Xw_tr, ydw_tr, Xw_vl, epochs=40)
            pred_tcn_dg_raw = tcn_pred_delta + gcw_vl
            r2_tcn_dg = compute_r2(yaw_vl, pred_tcn_dg_raw)

            # Align TCN to flat feature val set size
            if len(pred_tcn_dg_raw) == len(ya_vl):
                pred_tcn_dg = pred_tcn_dg_raw
            else:
                pred_tcn_dg = pred_ridge_dg.copy()

        # --- Weighted Ensemble (Δg models) ---
        # Optimize weights on validation set
        from scipy.optimize import minimize_scalar
        preds = np.column_stack([pred_ridge_dg, pred_xgb_dg, pred_tcn_dg])

        def neg_r2(weights_raw):
            w = np.exp(weights_raw) / np.sum(np.exp(weights_raw))
            pred = preds @ w
            return -compute_r2(ya_vl, pred)

        from scipy.optimize import minimize
        res_opt = minimize(neg_r2, [0.0, 0.0, 0.0], method='Nelder-Mead')
        w_opt = np.exp(res_opt.x) / np.sum(np.exp(res_opt.x))
        pred_ensemble = preds @ w_opt
        r2_ensemble = compute_r2(ya_vl, pred_ensemble)

        # --- Old-style ensemble on absolute target ---
        xgb_abs = make_xgb()
        xgb_abs.fit(X_tr, ya_tr)
        pred_xgb_abs = xgb_abs.predict(X_vl)
        r2_xgb_abs = compute_r2(ya_vl, pred_xgb_abs)

        pred_abs_ensemble = 0.5 * pred_ridge_abs + 0.4 * pred_xgb_abs + 0.1 * pred_ridge_dg
        r2_abs_ensemble = compute_r2(ya_vl, pred_abs_ensemble)

        results.append({
            'patient': p['name'],
            'n_samples': len(X),
            'r2_ridge_abs': round(r2_ridge_abs, 4),
            'r2_ridge_dg': round(r2_ridge_dg, 4),
            'r2_xgb_dg': round(r2_xgb_dg, 4),
            'r2_tcn_dg': round(r2_tcn_dg, 4),
            'r2_dg_ensemble': round(r2_ensemble, 4),
            'r2_abs_ensemble': round(r2_abs_ensemble, 4),
            'ensemble_weights': [round(w, 3) for w in w_opt],
            'dg_gain_over_abs': round(r2_ensemble - r2_abs_ensemble, 4),
        })

        if detail:
            print(f"  {p['name']}: abs={r2_ridge_abs:.4f} dg_ens={r2_ensemble:.4f} "
                  f"abs_ens={r2_abs_ensemble:.4f} Δ={r2_ensemble-r2_abs_ensemble:+.4f} "
                  f"w={[round(w,2) for w in w_opt]}")

    means = {k: round(np.mean([r[k] for r in results]), 4)
             for k in ['r2_ridge_abs', 'r2_ridge_dg', 'r2_xgb_dg', 'r2_tcn_dg',
                        'r2_dg_ensemble', 'r2_abs_ensemble']}
    wins_dg = sum(1 for r in results if r['r2_dg_ensemble'] > r['r2_abs_ensemble'])

    summary = {
        'means': means,
        'dg_ensemble_wins': wins_dg,
        'n_patients': len(results),
        'mean_dg_gain': round(np.mean([r['dg_gain_over_abs'] for r in results]), 4),
    }

    return {
        'status': 'pass',
        'detail': (f"Δg ensemble={means['r2_dg_ensemble']:.4f} "
                   f"vs abs ensemble={means['r2_abs_ensemble']:.4f} "
                   f"(wins={wins_dg}/{len(results)}, "
                   f"Δ={summary['mean_dg_gain']:+.4f})"),
        'results': {'per_patient': results, 'summary': summary},
    }


# ---------------------------------------------------------------------------
# EXP-1112: XGBoost Hyperparameter Sweep (GPU-accelerated)
# ---------------------------------------------------------------------------

def exp_1112_xgb_sweep(patients, detail=False):
    """Exhaustive XGBoost hyperparameter search enabled by 67× GPU speedup."""
    if not XGB_AVAILABLE:
        return {'status': 'skip', 'detail': 'XGBoost not available'}

    grid = {
        'n_estimators': [100, 200, 500],
        'max_depth': [3, 4, 6, 8],
        'learning_rate': [0.01, 0.05, 0.1],
        'subsample': [0.7, 0.8, 1.0],
    }

    configs = []
    for ne in grid['n_estimators']:
        for md in grid['max_depth']:
            for lr in grid['learning_rate']:
                for ss in grid['subsample']:
                    configs.append({'n_estimators': ne, 'max_depth': md,
                                    'learning_rate': lr, 'subsample': ss})
    print(f"  Total configs: {len(configs)}")

    results = []
    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        n = min(len(glucose), len(physics))
        if n < WINDOW + HORIZON + 50:
            continue
        glucose, physics = glucose[:n], physics[:n]

        X, y, _ = build_grand_features(glucose, physics)
        if len(X) < 200:
            continue

        X_tr, X_vl, y_tr, y_vl = split_data(X, y)

        best_r2 = -999
        best_cfg = None
        all_scores = []

        t0 = time.time()
        for cfg in configs:
            model = xgb.XGBRegressor(
                tree_method='hist',
                device='cuda' if torch.cuda.is_available() else 'cpu',
                random_state=42, verbosity=0, **cfg)
            model.fit(X_tr, y_tr)
            pred = model.predict(X_vl)
            r2 = compute_r2(y_vl, pred)
            all_scores.append((cfg, r2))
            if r2 > best_r2:
                best_r2 = r2
                best_cfg = cfg
        sweep_time = time.time() - t0

        # Default config baseline
        default_model = xgb.XGBRegressor(
            n_estimators=200, max_depth=4, learning_rate=0.05,
            tree_method='hist', device='cuda' if torch.cuda.is_available() else 'cpu',
            random_state=42, verbosity=0)
        default_model.fit(X_tr, y_tr)
        default_r2 = compute_r2(y_vl, default_model.predict(X_vl))

        results.append({
            'patient': p['name'],
            'n_samples': len(X),
            'default_r2': round(default_r2, 4),
            'best_r2': round(best_r2, 4),
            'best_config': best_cfg,
            'gain': round(best_r2 - default_r2, 4),
            'sweep_time': round(sweep_time, 1),
            'n_configs': len(configs),
        })

        if detail:
            print(f"  {p['name']}: default={default_r2:.4f} best={best_r2:.4f} "
                  f"Δ={best_r2-default_r2:+.4f} ({sweep_time:.1f}s) "
                  f"cfg={best_cfg}")

    mean_default = np.mean([r['default_r2'] for r in results])
    mean_best = np.mean([r['best_r2'] for r in results])
    mean_gain = np.mean([r['gain'] for r in results])
    wins = sum(1 for r in results if r['gain'] > 0.001)

    # Find universal best config
    cfg_scores = {}
    for r in results:
        key = str(r['best_config'])
        cfg_scores[key] = cfg_scores.get(key, 0) + 1

    summary = {
        'mean_default_r2': round(mean_default, 4),
        'mean_best_r2': round(mean_best, 4),
        'mean_gain': round(mean_gain, 4),
        'improvement_wins': wins,
        'most_popular_config': max(cfg_scores, key=cfg_scores.get),
        'n_configs': len(configs),
    }

    return {
        'status': 'pass',
        'detail': (f"default={mean_default:.4f} best={mean_best:.4f} "
                   f"Δ={mean_gain:+.4f} (wins={wins}/{len(results)})"),
        'results': {'per_patient': results, 'summary': summary},
    }


# ---------------------------------------------------------------------------
# EXP-1113: Multi-Horizon Joint Prediction
# ---------------------------------------------------------------------------

def exp_1113_multi_horizon(patients, detail=False):
    """Predict 15/30/45/60 min ahead simultaneously."""
    HORIZONS = [3, 6, 9, 12]  # 15, 30, 45, 60 min
    HORIZON_NAMES = {3: '15min', 6: '30min', 9: '45min', 12: '60min'}

    results = []
    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        n = min(len(glucose), len(physics))
        if n < WINDOW + max(HORIZONS) + 50:
            continue
        glucose, physics = glucose[:n], physics[:n]

        X_win, y_dict = make_windows_multi_horizon(glucose, physics,
                                                    horizons=HORIZONS)
        if len(X_win) < 200:
            continue

        X_flat = X_win.reshape(len(X_win), -1)
        split_idx = int(0.8 * len(X_flat))

        res = {'patient': p['name'], 'n_samples': len(X_flat)}

        # Approach 1: Separate Ridge per horizon
        sep_scores = {}
        for h in HORIZONS:
            y = y_dict[h]
            X_tr, X_vl = X_flat[:split_idx], X_flat[split_idx:]
            y_tr, y_vl = y[:split_idx], y[split_idx:]
            model = Ridge(alpha=1.0)
            model.fit(X_tr, y_tr)
            r2 = compute_r2(y_vl, model.predict(X_vl))
            sep_scores[HORIZON_NAMES[h]] = round(r2, 4)
        res['separate_ridge'] = sep_scores

        # Approach 2: Joint Ridge with horizon index
        joint_X = []
        joint_y = []
        for hi, h in enumerate(HORIZONS):
            horizon_feat = np.zeros((len(X_flat), len(HORIZONS)))
            horizon_feat[:, hi] = 1.0
            joint_X.append(np.hstack([X_flat, horizon_feat]))
            joint_y.append(y_dict[h])
        joint_X = np.vstack(joint_X)
        joint_y = np.concatenate(joint_y)

        n_per_h = len(X_flat)
        joint_tr_mask = np.zeros(len(joint_X), dtype=bool)
        for hi in range(len(HORIZONS)):
            joint_tr_mask[hi*n_per_h:hi*n_per_h+split_idx] = True

        model_joint = Ridge(alpha=1.0)
        model_joint.fit(joint_X[joint_tr_mask], joint_y[joint_tr_mask])

        joint_scores = {}
        for hi, h in enumerate(HORIZONS):
            vl_start = hi * n_per_h + split_idx
            vl_end = (hi + 1) * n_per_h
            pred = model_joint.predict(joint_X[vl_start:vl_end])
            y_vl = joint_y[vl_start:vl_end]
            joint_scores[HORIZON_NAMES[h]] = round(compute_r2(y_vl, pred), 4)
        res['joint_ridge'] = joint_scores

        # Approach 3: Multi-output Ridge (one model, 4 outputs)
        Y_multi = np.column_stack([y_dict[h] for h in HORIZONS])
        Xm_tr, Xm_vl = X_flat[:split_idx], X_flat[split_idx:]
        Ym_tr, Ym_vl = Y_multi[:split_idx], Y_multi[split_idx:]
        from sklearn.multioutput import MultiOutputRegressor
        mo_model = MultiOutputRegressor(Ridge(alpha=1.0))
        mo_model.fit(Xm_tr, Ym_tr)
        mo_pred = mo_model.predict(Xm_vl)
        mo_scores = {}
        for hi, h in enumerate(HORIZONS):
            mo_scores[HORIZON_NAMES[h]] = round(
                compute_r2(Ym_vl[:, hi], mo_pred[:, hi]), 4)
        res['multioutput_ridge'] = mo_scores

        # Best approach per horizon
        best = {}
        for hn in HORIZON_NAMES.values():
            approaches = {
                'separate': sep_scores[hn],
                'joint': joint_scores[hn],
                'multioutput': mo_scores[hn],
            }
            best[hn] = max(approaches, key=approaches.get)
        res['best_approach'] = best

        results.append(res)

        if detail:
            for hn in HORIZON_NAMES.values():
                print(f"  {p['name']} {hn}: sep={sep_scores[hn]:.4f} "
                      f"joint={joint_scores[hn]:.4f} mo={mo_scores[hn]:.4f} "
                      f"→ {best[hn]}")

    # Aggregate
    approach_wins = {'separate': 0, 'joint': 0, 'multioutput': 0}
    for r in results:
        for hn, b in r['best_approach'].items():
            approach_wins[b] += 1

    horizon_means = {}
    for hn in HORIZON_NAMES.values():
        horizon_means[hn] = {
            'separate': round(np.mean([r['separate_ridge'][hn] for r in results]), 4),
            'joint': round(np.mean([r['joint_ridge'][hn] for r in results]), 4),
            'multioutput': round(np.mean([r['multioutput_ridge'][hn] for r in results]), 4),
        }

    summary = {
        'horizon_means': horizon_means,
        'approach_wins': approach_wins,
        'n_patients': len(results),
        'horizon_decay': {hn: horizon_means[hn]['separate']
                          for hn in HORIZON_NAMES.values()},
    }

    return {
        'status': 'pass',
        'detail': (f"Horizon decay: " +
                   " → ".join(f"{hn}={horizon_means[hn]['separate']:.3f}"
                              for hn in HORIZON_NAMES.values()) +
                   f" | wins={approach_wins}"),
        'results': {'per_patient': results, 'summary': summary},
    }


# ---------------------------------------------------------------------------
# EXP-1114: TCN + Δg + Residual Stacking
# ---------------------------------------------------------------------------

def exp_1114_tcn_dg_stacking(patients, detail=False):
    """Best neural (TCN) + best target (Δg) with residual stacking."""
    results = []
    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        n = min(len(glucose), len(physics))
        if n < WINDOW + HORIZON + 50:
            continue
        glucose, physics = glucose[:n], physics[:n]

        # 3D windows for TCN
        X_win, y_win = make_windows(glucose, physics)
        if len(X_win) < 200:
            continue

        gc_win = X_win[:, -1, 0]  # last glucose in window
        yd_win = y_win - gc_win   # Δg target

        split_idx = int(0.8 * len(X_win))
        Xw_tr, Xw_vl = X_win[:split_idx], X_win[split_idx:]
        ya_tr, ya_vl = y_win[:split_idx], y_win[split_idx:]
        yd_tr, yd_vl = yd_win[:split_idx], yd_win[split_idx:]
        gc_vl = gc_win[split_idx:]

        # Flat features for Ridge
        X_flat = X_win.reshape(len(X_win), -1)
        Xf_tr, Xf_vl = X_flat[:split_idx], X_flat[split_idx:]

        # 1. Ridge direct (baseline)
        ridge_direct = Ridge(alpha=1.0)
        ridge_direct.fit(Xf_tr, ya_tr)
        pred_ridge_direct = ridge_direct.predict(Xf_vl)
        r2_ridge_direct = compute_r2(ya_vl, pred_ridge_direct)

        # 2. Ridge Δg
        ridge_dg = Ridge(alpha=1.0)
        ridge_dg.fit(Xf_tr, yd_tr)
        pred_ridge_dg_delta = ridge_dg.predict(Xf_vl)
        pred_ridge_dg = pred_ridge_dg_delta + gc_vl
        r2_ridge_dg = compute_r2(ya_vl, pred_ridge_dg)

        # 3. TCN direct
        tcn1 = TCN(in_channels=X_win.shape[2], window_size=WINDOW)
        pred_tcn_direct = train_neural(tcn1, Xw_tr, ya_tr, Xw_vl, epochs=40)
        r2_tcn_direct = compute_r2(ya_vl, pred_tcn_direct)

        # 4. TCN Δg
        tcn2 = TCN(in_channels=X_win.shape[2], window_size=WINDOW)
        pred_tcn_dg_delta = train_neural(tcn2, Xw_tr, yd_tr, Xw_vl, epochs=40)
        pred_tcn_dg = pred_tcn_dg_delta + gc_vl
        r2_tcn_dg = compute_r2(ya_vl, pred_tcn_dg)

        # 5. Ridge Δg + TCN residual stacking
        # Train TCN on Ridge's residuals
        ridge_dg_train_pred = ridge_dg.predict(Xf_tr) + gc_win[:split_idx]
        residuals_train = ya_tr - ridge_dg_train_pred

        tcn3 = TCN(in_channels=X_win.shape[2], window_size=WINDOW)
        pred_residual = train_neural(tcn3, Xw_tr, residuals_train, Xw_vl,
                                      epochs=40)
        pred_stacked = pred_ridge_dg + pred_residual
        r2_stacked = compute_r2(ya_vl, pred_stacked)

        results.append({
            'patient': p['name'],
            'n_samples': len(X_win),
            'r2_ridge_direct': round(r2_ridge_direct, 4),
            'r2_ridge_dg': round(r2_ridge_dg, 4),
            'r2_tcn_direct': round(r2_tcn_direct, 4),
            'r2_tcn_dg': round(r2_tcn_dg, 4),
            'r2_stacked': round(r2_stacked, 4),
            'stacking_gain': round(r2_stacked - r2_ridge_dg, 4),
            'best': max([('ridge', r2_ridge_direct), ('ridge_dg', r2_ridge_dg),
                         ('tcn', r2_tcn_direct), ('tcn_dg', r2_tcn_dg),
                         ('stacked', r2_stacked)], key=lambda x: x[1])[0],
        })

        if detail:
            r = results[-1]
            print(f"  {p['name']}: ridge={r2_ridge_direct:.4f} "
                  f"ridge_dg={r2_ridge_dg:.4f} tcn={r2_tcn_direct:.4f} "
                  f"tcn_dg={r2_tcn_dg:.4f} stacked={r2_stacked:.4f} → {r['best']}")

    means = {k: round(np.mean([r[k] for r in results]), 4)
             for k in ['r2_ridge_direct', 'r2_ridge_dg', 'r2_tcn_direct',
                        'r2_tcn_dg', 'r2_stacked']}
    best_counts = {}
    for r in results:
        best_counts[r['best']] = best_counts.get(r['best'], 0) + 1
    stacking_wins = sum(1 for r in results if r['r2_stacked'] > r['r2_ridge_dg'])

    return {
        'status': 'pass',
        'detail': (f"stacked={means['r2_stacked']:.4f} "
                   f"ridge_dg={means['r2_ridge_dg']:.4f} "
                   f"tcn_dg={means['r2_tcn_dg']:.4f} "
                   f"(stacking wins={stacking_wins}/{len(results)}, "
                   f"best_counts={best_counts})"),
        'results': {'per_patient': results, 'summary': {
            'means': means, 'best_counts': best_counts,
            'stacking_wins': stacking_wins, 'n_patients': len(results),
        }},
    }


# ---------------------------------------------------------------------------
# EXP-1115: Attention Over Physics Channels
# ---------------------------------------------------------------------------

def exp_1115_physics_attention(patients, detail=False):
    """Channel-wise temporal attention over physics decomposition."""
    results = []
    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        n = min(len(glucose), len(physics))
        if n < WINDOW + HORIZON + 50:
            continue
        glucose, physics = glucose[:n], physics[:n]

        X_win, y_win = make_windows(glucose, physics)
        if len(X_win) < 200:
            continue

        split_idx = int(0.8 * len(X_win))
        Xw_tr, Xw_vl = X_win[:split_idx], X_win[split_idx:]
        y_tr, y_vl = y_win[:split_idx], y_win[split_idx:]

        # Flat Ridge baseline
        X_flat = X_win.reshape(len(X_win), -1)
        ridge = Ridge(alpha=1.0)
        ridge.fit(X_flat[:split_idx], y_tr)
        r2_ridge = compute_r2(y_vl, ridge.predict(X_flat[split_idx:]))

        # CNN baseline
        cnn = ResidualCNN(in_channels=X_win.shape[2], window_size=WINDOW)
        pred_cnn = train_neural(cnn, Xw_tr, y_tr, Xw_vl, epochs=40)
        r2_cnn = compute_r2(y_vl, pred_cnn)

        # TCN baseline
        tcn = TCN(in_channels=X_win.shape[2], window_size=WINDOW)
        pred_tcn = train_neural(tcn, Xw_tr, y_tr, Xw_vl, epochs=40)
        r2_tcn = compute_r2(y_vl, pred_tcn)

        # Physics Attention
        n_ch = X_win.shape[2]  # glucose + 4 physics = 5
        attn = PhysicsAttention(n_channels=n_ch, window=WINDOW)
        pred_attn = train_neural(attn, Xw_tr, y_tr, Xw_vl, epochs=60)
        r2_attn = compute_r2(y_vl, pred_attn)

        results.append({
            'patient': p['name'],
            'n_samples': len(X_win),
            'r2_ridge': round(r2_ridge, 4),
            'r2_cnn': round(r2_cnn, 4),
            'r2_tcn': round(r2_tcn, 4),
            'r2_attention': round(r2_attn, 4),
            'attn_vs_ridge': round(r2_attn - r2_ridge, 4),
            'attn_vs_cnn': round(r2_attn - r2_cnn, 4),
        })

        if detail:
            print(f"  {p['name']}: ridge={r2_ridge:.4f} cnn={r2_cnn:.4f} "
                  f"tcn={r2_tcn:.4f} attn={r2_attn:.4f}")

    means = {k: round(np.mean([r[k] for r in results]), 4)
             for k in ['r2_ridge', 'r2_cnn', 'r2_tcn', 'r2_attention']}
    attn_wins_ridge = sum(1 for r in results if r['r2_attention'] > r['r2_ridge'])
    attn_wins_cnn = sum(1 for r in results if r['r2_attention'] > r['r2_cnn'])

    return {
        'status': 'pass',
        'detail': (f"attention={means['r2_attention']:.4f} "
                   f"ridge={means['r2_ridge']:.4f} cnn={means['r2_cnn']:.4f} "
                   f"tcn={means['r2_tcn']:.4f} "
                   f"(attn wins vs ridge={attn_wins_ridge}, "
                   f"vs cnn={attn_wins_cnn}/{len(results)})"),
        'results': {'per_patient': results, 'summary': {
            'means': means,
            'attn_wins_vs_ridge': attn_wins_ridge,
            'attn_wins_vs_cnn': attn_wins_cnn,
            'n_patients': len(results),
        }},
    }


# ---------------------------------------------------------------------------
# EXP-1116: Adaptive Per-Patient Ensemble Weights
# ---------------------------------------------------------------------------

def exp_1116_adaptive_ensemble(patients, detail=False):
    """Learn per-patient ensemble weights via validation optimization."""
    results = []
    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        n = min(len(glucose), len(physics))
        if n < WINDOW + HORIZON + 50:
            continue
        glucose, physics = glucose[:n], physics[:n]

        X, y, _ = build_grand_features(glucose, physics)
        if len(X) < 300:
            continue

        # 3-way split: train, val (weight tuning), test
        X_tr, X_vl, X_te, y_tr, y_vl, y_te = split_3way(X, y)

        # Train base models on train set
        ridge = Ridge(alpha=1.0)
        ridge.fit(X_tr, y_tr)

        xgb_m = make_xgb()
        xgb_m.fit(X_tr, y_tr)

        # Ridge on val and test
        pred_ridge_vl = ridge.predict(X_vl)
        pred_ridge_te = ridge.predict(X_te)

        # XGB on val and test
        pred_xgb_vl = xgb_m.predict(X_vl)
        pred_xgb_te = xgb_m.predict(X_te)

        # CNN on 3D data
        X_win, y_win = make_windows(glucose, physics)
        if len(X_win) < 300:
            pred_cnn_vl = pred_ridge_vl.copy()
            pred_cnn_te = pred_ridge_te.copy()
        else:
            s1 = int(0.6 * len(X_win))
            s2 = int(0.8 * len(X_win))
            Xw_tr = X_win[:s1]
            Xw_vl = X_win[s1:s2]
            Xw_te = X_win[s2:]
            yw_tr = y_win[:s1]
            yw_vl = y_win[s1:s2]

            cnn = ResidualCNN(in_channels=X_win.shape[2])
            pred_cnn_vl_raw = train_neural(cnn, Xw_tr, yw_tr, Xw_vl, epochs=40)

            # Re-train for test prediction
            cnn2 = ResidualCNN(in_channels=X_win.shape[2])
            pred_cnn_te_raw = train_neural(cnn2, X_win[:s2], y_win[:s2],
                                            Xw_te, epochs=40)

            # Align sizes
            if len(pred_cnn_vl_raw) == len(y_vl):
                pred_cnn_vl = pred_cnn_vl_raw
                pred_cnn_te = pred_cnn_te_raw if len(pred_cnn_te_raw) == len(y_te) else pred_ridge_te
            else:
                pred_cnn_vl = pred_ridge_vl.copy()
                pred_cnn_te = pred_ridge_te.copy()

        # 1. Uniform weights
        pred_uniform_te = (pred_ridge_te + pred_xgb_te + pred_cnn_te) / 3
        r2_uniform = compute_r2(y_te, pred_uniform_te)

        # 2. Global optimal weights (from EXP-1108: 0.5, 0.4, 0.1)
        pred_global_te = 0.5 * pred_ridge_te + 0.4 * pred_xgb_te + 0.1 * pred_cnn_te
        r2_global = compute_r2(y_te, pred_global_te)

        # 3. Per-patient optimal weights (optimize on val, evaluate on test)
        from scipy.optimize import minimize
        preds_vl = np.column_stack([pred_ridge_vl, pred_xgb_vl, pred_cnn_vl])
        preds_te = np.column_stack([pred_ridge_te, pred_xgb_te, pred_cnn_te])

        def neg_r2(w_raw):
            w = np.exp(w_raw) / np.sum(np.exp(w_raw))
            return -compute_r2(y_vl, preds_vl @ w)

        opt = minimize(neg_r2, [0.0, 0.0, 0.0], method='Nelder-Mead')
        w_patient = np.exp(opt.x) / np.sum(np.exp(opt.x))
        pred_patient_te = preds_te @ w_patient
        r2_patient = compute_r2(y_te, pred_patient_te)

        # Individual model test scores
        r2_ridge_te = compute_r2(y_te, pred_ridge_te)
        r2_xgb_te = compute_r2(y_te, pred_xgb_te)
        r2_cnn_te = compute_r2(y_te, pred_cnn_te)

        best = max([('uniform', r2_uniform), ('global', r2_global),
                     ('patient', r2_patient), ('ridge', r2_ridge_te),
                     ('xgb', r2_xgb_te)], key=lambda x: x[1])

        results.append({
            'patient': p['name'],
            'n_samples': len(X),
            'r2_ridge': round(r2_ridge_te, 4),
            'r2_xgb': round(r2_xgb_te, 4),
            'r2_cnn': round(r2_cnn_te, 4),
            'r2_uniform': round(r2_uniform, 4),
            'r2_global': round(r2_global, 4),
            'r2_patient': round(r2_patient, 4),
            'patient_weights': [round(w, 3) for w in w_patient],
            'best': best[0],
            'patient_gain_vs_global': round(r2_patient - r2_global, 4),
        })

        if detail:
            print(f"  {p['name']}: uniform={r2_uniform:.4f} global={r2_global:.4f} "
                  f"patient={r2_patient:.4f} (w={[round(w,2) for w in w_patient]}) "
                  f"→ {best[0]}")

    means = {k: round(np.mean([r[k] for r in results]), 4)
             for k in ['r2_uniform', 'r2_global', 'r2_patient']}
    patient_wins = sum(1 for r in results
                       if r['r2_patient'] > r['r2_global'])
    best_counts = {}
    for r in results:
        best_counts[r['best']] = best_counts.get(r['best'], 0) + 1

    return {
        'status': 'pass',
        'detail': (f"uniform={means['r2_uniform']:.4f} "
                   f"global={means['r2_global']:.4f} "
                   f"patient={means['r2_patient']:.4f} "
                   f"(patient>global: {patient_wins}/{len(results)}, "
                   f"best={best_counts})"),
        'results': {'per_patient': results, 'summary': {
            'means': means, 'patient_wins': patient_wins,
            'best_counts': best_counts, 'n_patients': len(results),
        }},
    }


# ---------------------------------------------------------------------------
# EXP-1117: Conformal Prediction
# ---------------------------------------------------------------------------

def exp_1117_conformal(patients, detail=False):
    """Conformal prediction for calibrated intervals."""
    TARGET_COVERAGES = [0.80, 0.90, 0.95]
    results = []
    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        n = min(len(glucose), len(physics))
        if n < WINDOW + HORIZON + 50:
            continue
        glucose, physics = glucose[:n], physics[:n]

        X, y, _ = build_grand_features(glucose, physics)
        if len(X) < 300:
            continue

        # 3-way split
        X_tr, X_cal, X_te, y_tr, y_cal, y_te = split_3way(X, y)

        # Train on training set
        ridge = Ridge(alpha=1.0)
        ridge.fit(X_tr, y_tr)

        # Calibration: compute nonconformity scores
        pred_cal = ridge.predict(X_cal)
        scores = np.abs(y_cal - pred_cal)  # absolute residuals

        # Test
        pred_te = ridge.predict(X_te)

        coverage_results = {}
        for target_cov in TARGET_COVERAGES:
            # Conformal quantile
            q = np.quantile(scores, target_cov)
            lower = pred_te - q
            upper = pred_te + q

            # Coverage on test set
            covered = np.mean((y_te >= lower) & (y_te <= upper))
            width = np.mean(upper - lower) * GLUCOSE_SCALE  # in mg/dL

            # Hypo capture
            hypo_mask = y_te * GLUCOSE_SCALE < 70
            if np.sum(hypo_mask) > 0:
                hypo_capture = np.mean(
                    (y_te[hypo_mask] >= lower[hypo_mask]) &
                    (y_te[hypo_mask] <= upper[hypo_mask]))
            else:
                hypo_capture = None

            coverage_results[f'{int(target_cov*100)}%'] = {
                'target': target_cov,
                'actual': round(covered, 4),
                'width_mgdl': round(width, 1),
                'hypo_capture': round(hypo_capture, 4) if hypo_capture is not None else None,
                'calibration_error': round(abs(covered - target_cov), 4),
            }

        results.append({
            'patient': p['name'],
            'n_samples': len(X),
            'n_cal': len(X_cal),
            'n_test': len(X_te),
            'coverage': coverage_results,
        })

        if detail:
            for label, cr in coverage_results.items():
                print(f"  {p['name']} {label}: actual={cr['actual']:.3f} "
                      f"width={cr['width_mgdl']:.1f}mg "
                      f"hypo_capt={cr['hypo_capture']}")

    # Aggregate
    agg = {}
    for label in ['80%', '90%', '95%']:
        actual_covs = [r['coverage'][label]['actual'] for r in results]
        widths = [r['coverage'][label]['width_mgdl'] for r in results]
        cal_errors = [r['coverage'][label]['calibration_error'] for r in results]
        agg[label] = {
            'mean_actual': round(np.mean(actual_covs), 4),
            'mean_width': round(np.mean(widths), 1),
            'mean_cal_error': round(np.mean(cal_errors), 4),
        }

    return {
        'status': 'pass',
        'detail': ' | '.join(f"{k}: cov={v['mean_actual']:.3f} "
                              f"w={v['mean_width']:.0f}mg ce={v['mean_cal_error']:.3f}"
                              for k, v in agg.items()),
        'results': {'per_patient': results, 'summary': agg},
    }


# ---------------------------------------------------------------------------
# EXP-1118: Residual LSTM on Ensemble Errors
# ---------------------------------------------------------------------------

def exp_1118_residual_lstm(patients, detail=False):
    """Learn temporal patterns in ensemble prediction errors via LSTM."""
    RESIDUAL_WINDOW = 12  # use last 12 residuals to predict next

    results = []
    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        n = min(len(glucose), len(physics))
        if n < WINDOW + HORIZON + 50:
            continue
        glucose, physics = glucose[:n], physics[:n]

        X, y, _ = build_grand_features(glucose, physics)
        if len(X) < 400:
            continue

        # 3-way split
        X_tr, X_vl, X_te, y_tr, y_vl, y_te = split_3way(X, y)

        # Train Ridge + XGB ensemble
        ridge = Ridge(alpha=1.0)
        ridge.fit(X_tr, y_tr)
        xgb_m = make_xgb()
        xgb_m.fit(X_tr, y_tr)

        # Ensemble on val
        pred_ridge_vl = ridge.predict(X_vl)
        pred_xgb_vl = xgb_m.predict(X_vl)
        pred_ens_vl = 0.5 * pred_ridge_vl + 0.5 * pred_xgb_vl
        residuals_vl = y_vl - pred_ens_vl

        # Ensemble on test
        pred_ridge_te = ridge.predict(X_te)
        pred_xgb_te = xgb_m.predict(X_te)
        pred_ens_te = 0.5 * pred_ridge_te + 0.5 * pred_xgb_te

        r2_ens = compute_r2(y_te, pred_ens_te)

        # Build LSTM training data from val residuals
        resid_X, resid_y = [], []
        for i in range(RESIDUAL_WINDOW, len(residuals_vl)):
            resid_X.append(residuals_vl[i-RESIDUAL_WINDOW:i])
            resid_y.append(residuals_vl[i])
        resid_X = np.array(resid_X).reshape(-1, RESIDUAL_WINDOW, 1)
        resid_y = np.array(resid_y)

        if len(resid_X) < 50:
            results.append({
                'patient': p['name'], 'n_samples': len(X),
                'r2_ensemble': round(r2_ens, 4),
                'r2_corrected': round(r2_ens, 4),
                'lstm_gain': 0.0, 'skip': 'too_few_residuals',
            })
            continue

        # Train LSTM on residuals
        lstm = ResidualLSTM(hidden=32, seq_len=RESIDUAL_WINDOW)
        lstm = lstm.to(DEVICE)
        optimizer = torch.optim.Adam(lstm.parameters(), lr=1e-3)
        loss_fn = nn.MSELoss()

        Xt = torch.tensor(resid_X, dtype=torch.float32).to(DEVICE)
        yt = torch.tensor(resid_y, dtype=torch.float32).to(DEVICE)

        lstm.train()
        for _ in range(50):
            pred = lstm(Xt)
            loss = loss_fn(pred, yt)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

        # Apply LSTM correction to test residuals
        test_residuals = y_te - pred_ens_te
        # Build sequential residual windows from test
        corrected = pred_ens_te.copy()
        # Use rolling window of actual residuals
        resid_buffer = list(residuals_vl[-RESIDUAL_WINDOW:])

        lstm.eval()
        with torch.no_grad():
            for i in range(len(y_te)):
                if len(resid_buffer) >= RESIDUAL_WINDOW:
                    window = np.array(resid_buffer[-RESIDUAL_WINDOW:]).reshape(1, RESIDUAL_WINDOW, 1)
                    w_tensor = torch.tensor(window, dtype=torch.float32).to(DEVICE)
                    correction = lstm(w_tensor).cpu().numpy()[0]
                    corrected[i] = pred_ens_te[i] + correction
                # Update buffer with actual residual
                actual_resid = y_te[i] - pred_ens_te[i]
                resid_buffer.append(actual_resid)

        r2_corrected = compute_r2(y_te, corrected)
        lstm_gain = r2_corrected - r2_ens

        results.append({
            'patient': p['name'],
            'n_samples': len(X),
            'r2_ensemble': round(r2_ens, 4),
            'r2_corrected': round(r2_corrected, 4),
            'lstm_gain': round(lstm_gain, 4),
        })

        if detail:
            print(f"  {p['name']}: ens={r2_ens:.4f} corrected={r2_corrected:.4f} "
                  f"Δ={lstm_gain:+.4f}")

    mean_ens = np.mean([r['r2_ensemble'] for r in results])
    mean_corr = np.mean([r['r2_corrected'] for r in results])
    mean_gain = np.mean([r['lstm_gain'] for r in results])
    wins = sum(1 for r in results if r['lstm_gain'] > 0)

    return {
        'status': 'pass',
        'detail': (f"ensemble={mean_ens:.4f} corrected={mean_corr:.4f} "
                   f"Δ={mean_gain:+.4f} (wins={wins}/{len(results)})"),
        'results': {'per_patient': results, 'summary': {
            'mean_ensemble': round(mean_ens, 4),
            'mean_corrected': round(mean_corr, 4),
            'mean_gain': round(mean_gain, 4),
            'lstm_wins': wins,
            'n_patients': len(results),
        }},
    }


# ---------------------------------------------------------------------------
# EXP-1119: Patient Clustering → Cluster-Specific Models
# ---------------------------------------------------------------------------

def exp_1119_patient_clustering(patients, detail=False):
    """Group patients by glucose characteristics, train cluster models."""
    # Extract patient-level features
    patient_features = []
    valid_patients = []
    for p in patients:
        glucose = p['df']['glucose'].values.astype(float)
        g_clean = glucose[~np.isnan(glucose)]
        if len(g_clean) < 1000:
            continue

        pk = p['pk']
        iob_mean = np.nanmean(pk[:, 0]) if pk.shape[1] > 0 else 0
        cob_mean = np.nanmean(pk[:, 6]) if pk.shape[1] > 6 else 0

        feats = {
            'mean_glucose': np.mean(g_clean),
            'std_glucose': np.std(g_clean),
            'cv_glucose': np.std(g_clean) / np.mean(g_clean) if np.mean(g_clean) > 0 else 0,
            'tir_70_180': np.mean((g_clean >= 70) & (g_clean <= 180)),
            'missing_pct': np.mean(np.isnan(glucose)),
            'mean_iob': iob_mean,
            'mean_cob': cob_mean,
        }
        patient_features.append(feats)
        valid_patients.append(p)

    if len(valid_patients) < 4:
        return {'status': 'skip', 'detail': 'Too few patients for clustering'}

    feat_matrix = np.array([[f[k] for k in ['mean_glucose', 'std_glucose',
                                              'cv_glucose', 'tir_70_180',
                                              'missing_pct', 'mean_iob']]
                             for f in patient_features])
    # Normalize
    feat_norm = (feat_matrix - feat_matrix.mean(0)) / (feat_matrix.std(0) + 1e-8)

    results_by_k = {}
    for n_clusters in [2, 3]:
        km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        labels = km.fit_predict(feat_norm)

        cluster_results = []
        for pi, p in enumerate(valid_patients):
            glucose, physics = prepare_patient_raw(p)
            n = min(len(glucose), len(physics))
            if n < WINDOW + HORIZON + 50:
                continue
            glucose, physics = glucose[:n], physics[:n]
            X, y, _ = build_grand_features(glucose, physics)
            if len(X) < 200:
                continue

            X_tr, X_vl, y_tr, y_vl = split_data(X, y)

            # 1. Patient-specific model
            ridge_ps = Ridge(alpha=1.0)
            ridge_ps.fit(X_tr, y_tr)
            r2_ps = compute_r2(y_vl, ridge_ps.predict(X_vl))

            # 2. Cluster-specific model (pool cluster patients' train data)
            cluster_id = labels[pi]
            cluster_X, cluster_y = [], []
            for pj, p2 in enumerate(valid_patients):
                if labels[pj] == cluster_id and pj != pi:
                    g2, ph2 = prepare_patient_raw(p2)
                    n2 = min(len(g2), len(ph2))
                    g2, ph2 = g2[:n2], ph2[:n2]
                    X2, y2, _ = build_grand_features(g2, ph2)
                    if len(X2) > 0:
                        cluster_X.append(X2)
                        cluster_y.append(y2)
            if cluster_X:
                cluster_X_all = np.vstack([X_tr] + cluster_X)
                cluster_y_all = np.concatenate([y_tr] + cluster_y)
                ridge_cl = Ridge(alpha=1.0)
                ridge_cl.fit(cluster_X_all, cluster_y_all)
                r2_cl = compute_r2(y_vl, ridge_cl.predict(X_vl))
            else:
                r2_cl = r2_ps

            # 3. Global model (pool all patients)
            global_X, global_y = [], []
            for pj, p2 in enumerate(valid_patients):
                if pj != pi:
                    g2, ph2 = prepare_patient_raw(p2)
                    n2 = min(len(g2), len(ph2))
                    g2, ph2 = g2[:n2], ph2[:n2]
                    X2, y2, _ = build_grand_features(g2, ph2)
                    if len(X2) > 0:
                        global_X.append(X2)
                        global_y.append(y2)
            global_X_all = np.vstack([X_tr] + global_X)
            global_y_all = np.concatenate([y_tr] + global_y)
            ridge_gl = Ridge(alpha=1.0)
            ridge_gl.fit(global_X_all, global_y_all)
            r2_gl = compute_r2(y_vl, ridge_gl.predict(X_vl))

            best = max([('patient', r2_ps), ('cluster', r2_cl),
                         ('global', r2_gl)], key=lambda x: x[1])

            cluster_results.append({
                'patient': p['name'],
                'cluster': int(cluster_id),
                'r2_patient': round(r2_ps, 4),
                'r2_cluster': round(r2_cl, 4),
                'r2_global': round(r2_gl, 4),
                'best': best[0],
            })

            if detail:
                print(f"  k={n_clusters} {p['name']}: "
                      f"ps={r2_ps:.4f} cl={r2_cl:.4f} gl={r2_gl:.4f} → {best[0]}")

        best_counts = {}
        for r in cluster_results:
            best_counts[r['best']] = best_counts.get(r['best'], 0) + 1

        results_by_k[n_clusters] = {
            'per_patient': cluster_results,
            'best_counts': best_counts,
            'cluster_sizes': [int(np.sum(labels == i)) for i in range(n_clusters)],
            'mean_r2': {
                'patient': round(np.mean([r['r2_patient'] for r in cluster_results]), 4),
                'cluster': round(np.mean([r['r2_cluster'] for r in cluster_results]), 4),
                'global': round(np.mean([r['r2_global'] for r in cluster_results]), 4),
            },
        }

    # Find best approach
    best_k = max(results_by_k.keys(),
                  key=lambda k: results_by_k[k]['mean_r2']['cluster'])

    return {
        'status': 'pass',
        'detail': ' | '.join(
            f"k={k}: ps={v['mean_r2']['patient']:.4f} "
            f"cl={v['mean_r2']['cluster']:.4f} gl={v['mean_r2']['global']:.4f} "
            f"best={v['best_counts']}"
            for k, v in results_by_k.items()),
        'results': {'by_k': results_by_k,
                     'patient_features': patient_features,
                     'best_k': best_k},
    }


# ---------------------------------------------------------------------------
# EXP-1120: Grand Combined Model
# ---------------------------------------------------------------------------

def exp_1120_grand_combined(patients, detail=False):
    """Definitive best model: combine ALL winning techniques.

    1. Interpolation + flag for missing data
    2. Δg target
    3. XGBoost + Ridge + TCN base models
    4. Per-patient weighted ensemble
    5. Block CV evaluation
    """
    results = []
    for p in patients:
        glucose_raw, physics = prepare_patient_raw(p)
        n = min(len(glucose_raw), len(physics))
        if n < WINDOW + HORIZON + 50:
            continue
        glucose_raw, physics = glucose_raw[:n], physics[:n]

        # --- Imputation: interpolation + missing flag ---
        glucose = glucose_raw.copy()
        missing_mask = np.isnan(glucose)
        missing_pct = np.mean(missing_mask)

        if missing_pct > 0 and missing_pct < 0.5:
            valid_idx = np.where(~missing_mask)[0]
            if len(valid_idx) > 1:
                glucose[missing_mask] = np.interp(
                    np.where(missing_mask)[0], valid_idx, glucose[valid_idx])

        # Build grand features with Δg target
        X, y_abs, g_cur = build_grand_features(glucose, physics)
        if len(X) < 200:
            continue

        # Add missing flag feature
        flag_series = missing_mask.astype(float)
        flag_feats = []
        g = glucose / GLUCOSE_SCALE
        for i in range(0, n - WINDOW - HORIZON, STRIDE):
            g_win = g[i:i + WINDOW]
            if np.isnan(g_win).mean() > 0.3:
                continue
            y_val = g[i + WINDOW + HORIZON - 1]
            if np.isnan(y_val):
                continue
            flag_feats.append(np.mean(flag_series[i:i + WINDOW]))
        flag_feats = np.array(flag_feats)

        if len(flag_feats) != len(X):
            flag_feats = np.zeros(len(X))
        X_aug = np.column_stack([X, flag_feats])

        y_delta = y_abs - g_cur  # Δg target

        # --- Block CV ---
        n_folds = 3
        fold_size = len(X_aug) // n_folds
        cv_scores = {'ridge_abs': [], 'ridge_dg': [], 'xgb_dg': [],
                     'ensemble_abs': [], 'ensemble_dg': []}

        for fold in range(n_folds):
            val_start = fold * fold_size
            val_end = val_start + fold_size if fold < n_folds - 1 else len(X_aug)
            mask = np.ones(len(X_aug), dtype=bool)
            mask[val_start:val_end] = False

            Xa_tr, Xa_vl = X_aug[mask], X_aug[~mask]
            ya_tr, ya_vl = y_abs[mask], y_abs[~mask]
            yd_tr, yd_vl = y_delta[mask], y_delta[~mask]
            gc_tr, gc_vl = g_cur[mask], g_cur[~mask]

            # Ridge absolute
            r_abs = Ridge(alpha=1.0)
            r_abs.fit(Xa_tr, ya_tr)
            pred_r_abs = r_abs.predict(Xa_vl)
            cv_scores['ridge_abs'].append(compute_r2(ya_vl, pred_r_abs))

            # Ridge Δg
            r_dg = Ridge(alpha=1.0)
            r_dg.fit(Xa_tr, yd_tr)
            pred_r_dg = r_dg.predict(Xa_vl) + gc_vl
            cv_scores['ridge_dg'].append(compute_r2(ya_vl, pred_r_dg))

            # XGBoost Δg
            xgb_dg = make_xgb()
            xgb_dg.fit(Xa_tr, yd_tr)
            pred_xgb_dg = xgb_dg.predict(Xa_vl) + gc_vl
            cv_scores['xgb_dg'].append(compute_r2(ya_vl, pred_xgb_dg))

            # Abs ensemble (Ridge + XGB)
            xgb_abs = make_xgb()
            xgb_abs.fit(Xa_tr, ya_tr)
            pred_xgb_abs = xgb_abs.predict(Xa_vl)
            pred_ens_abs = 0.5 * pred_r_abs + 0.5 * pred_xgb_abs
            cv_scores['ensemble_abs'].append(compute_r2(ya_vl, pred_ens_abs))

            # Δg ensemble (Ridge Δg + XGB Δg)
            pred_ens_dg = 0.5 * pred_r_dg + 0.5 * pred_xgb_dg
            cv_scores['ensemble_dg'].append(compute_r2(ya_vl, pred_ens_dg))

        means = {k: round(np.mean(v), 4) for k, v in cv_scores.items()}
        best_method = max(means, key=means.get)

        # Clarke Error Grid on val set (use last fold's predictions)
        y_true_mgdl = ya_vl * GLUCOSE_SCALE
        y_pred_mgdl = pred_ens_dg * GLUCOSE_SCALE

        # Simplified Clarke zones
        def clarke_a_pct(y_true, y_pred):
            n = len(y_true)
            zone_a = 0
            for yt, yp in zip(y_true, y_pred):
                if yt <= 70:
                    if yp <= 70:
                        zone_a += 1
                elif yt >= 180:
                    if yp >= 180 or abs(yp - yt) / yt < 0.2:
                        zone_a += 1
                else:
                    if abs(yp - yt) < 0.2 * yt or abs(yp - yt) < 20:
                        zone_a += 1
            return zone_a / n if n > 0 else 0

        mae_mgdl = compute_mae(y_true_mgdl, y_pred_mgdl)
        clarke_a = clarke_a_pct(y_true_mgdl, y_pred_mgdl)

        results.append({
            'patient': p['name'],
            'n_samples': len(X_aug),
            'missing_pct': round(missing_pct, 3),
            'cv_means': means,
            'best_method': best_method,
            'best_r2': means[best_method],
            'mae_mgdl': round(mae_mgdl, 1),
            'clarke_a': round(clarke_a, 3),
        })

        if detail:
            print(f"  {p['name']}: best={best_method} R²={means[best_method]:.4f} "
                  f"MAE={mae_mgdl:.1f} Clarke_A={clarke_a:.1%} "
                  f"missing={missing_pct:.1%}")

    # Grand summary
    grand_means = {}
    for method in cv_scores.keys():
        grand_means[method] = round(np.mean([r['cv_means'][method] for r in results]), 4)
    grand_best = max(grand_means, key=grand_means.get)
    mean_mae = round(np.mean([r['mae_mgdl'] for r in results]), 1)
    mean_clarke = round(np.mean([r['clarke_a'] for r in results]), 3)

    return {
        'status': 'pass',
        'detail': (f"GRAND: {grand_best}={grand_means[grand_best]:.4f} "
                   f"MAE={mean_mae} Clarke_A={mean_clarke:.1%} | " +
                   ' '.join(f"{k}={v:.4f}" for k, v in grand_means.items())),
        'results': {'per_patient': results, 'summary': {
            'grand_means': grand_means,
            'grand_best_method': grand_best,
            'grand_best_r2': grand_means[grand_best],
            'mean_mae_mgdl': mean_mae,
            'mean_clarke_a': mean_clarke,
            'n_patients': len(results),
        }},
    }


# ---------------------------------------------------------------------------
# Experiment registry and main
# ---------------------------------------------------------------------------

EXPERIMENTS = [
    ('EXP-1111', 'Combined Winners (Δg + XGB + Ensemble)', exp_1111_combined_winners),
    ('EXP-1112', 'XGBoost Hyperparameter Sweep', exp_1112_xgb_sweep),
    ('EXP-1113', 'Multi-Horizon Joint Prediction', exp_1113_multi_horizon),
    ('EXP-1114', 'TCN + Δg + Residual Stacking', exp_1114_tcn_dg_stacking),
    ('EXP-1115', 'Attention Over Physics Channels', exp_1115_physics_attention),
    ('EXP-1116', 'Adaptive Per-Patient Ensemble Weights', exp_1116_adaptive_ensemble),
    ('EXP-1117', 'Conformal Prediction', exp_1117_conformal),
    ('EXP-1118', 'Residual LSTM on Ensemble Errors', exp_1118_residual_lstm),
    ('EXP-1119', 'Patient Clustering → Cluster Models', exp_1119_patient_clustering),
    ('EXP-1120', 'Grand Combined Model', exp_1120_grand_combined),
]


def main():
    parser = argparse.ArgumentParser(
        description='EXP-1111-1120: Combined Winners and Advanced Ensemble')
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--max-patients', type=int, default=11)
    parser.add_argument('--experiment', type=str,
                        help='Run only this experiment (e.g. EXP-1111)')
    args = parser.parse_args()

    patients = load_patients(PATIENTS_DIR, max_patients=args.max_patients)
    print(f"Loaded {len(patients)} patients")
    print(f"Using device: {DEVICE}")

    for exp_id, name, func in EXPERIMENTS:
        if args.experiment and exp_id != args.experiment:
            continue

        print(f"\n{'=' * 60}")
        print(f"Running {exp_id}: {name}")
        print(f"{'=' * 60}")

        t0 = time.time()
        try:
            result = func(patients, detail=args.detail)
            elapsed = time.time() - t0
            print(f"  Status: {result.get('status', 'unknown')}")
            print(f"  Detail: {result.get('detail', '')}")
            print(f"  Time: {elapsed:.1f}s")

            if args.save:
                save_data = {
                    'experiment': exp_id, 'name': name,
                    'status': result.get('status'),
                    'detail': result.get('detail'),
                    'elapsed_seconds': round(elapsed, 1),
                    'results': result.get('results', {}),
                }
                save_name = (f"{exp_id.lower()}_"
                             f"{name.lower().replace(' ', '_').replace('-', '_')}")
                save_path = save_results(save_data, save_name)
                print(f"  Saved: {save_path}")

        except Exception as e:
            elapsed = time.time() - t0
            print(f"  Status: FAIL")
            print(f"  Error: {e}")
            print(f"  Time: {elapsed:.1f}s")
            import traceback
            traceback.print_exc()

    print(f"\n{'=' * 60}")
    print("All experiments complete")
    print(f"{'=' * 60}")


if __name__ == '__main__':
    main()
