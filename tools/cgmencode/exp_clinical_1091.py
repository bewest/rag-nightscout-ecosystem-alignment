#!/usr/bin/env python3
"""EXP-1091 to EXP-1100: GB Validation, PK Personalization, and Residual Analysis.

Building on 90 experiments of findings (EXP-1001-1090):
- SOTA: R²=0.532 (3-fold block CV), R²=0.538 (GB grand features, single split)
- Error decomposition: 76.3% unexplained, 25.8% irreducible, 0.7% bias
- GB dominates with rich features (11/11), Ridge/CNN overfit with high-dim
- Physics interactions (+0.007) only genuine new feature for Ridge
- Glucose carries 97% of signal, physics 2-3%
- Feature engineering from existing data hits a wall
- Horizon decay: 0.0067/min (5min=0.971, 60min=0.503, 120min=0.197)

This batch validates the GB SOTA, explores per-patient PK personalization,
multi-scale temporal features, and residual characterization:
  EXP-1091: GB Grand Features Block CV ★★★
  EXP-1092: GB + CNN Residual on Grand Features ★★
  EXP-1093: Per-Patient DIA Optimization ★★★
  EXP-1094: Per-Patient ISF Scaling ★★
  EXP-1095: Multi-Scale Context (6h + 12h + 24h) ★★★
  EXP-1096: Two-Resolution Model ★★
  EXP-1097: Residual Analysis by Context ★★
  EXP-1098: Overnight vs Daytime Models ★★
  EXP-1099: Patient Difficulty Predictors ★
  EXP-1100: Campaign Grand Summary ★★★

Run:
    PYTHONPATH=tools python -m cgmencode.exp_clinical_1091 --detail --save --max-patients 11
"""

import argparse
import json
import os
import sys
import time
import warnings

import numpy as np
from pathlib import Path
from sklearn.linear_model import Ridge
from sklearn.ensemble import GradientBoostingRegressor

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


def prepare_patient_raw(p):
    """Return physics channels and glucose separately for custom windowing."""
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
    """Create (X, y) pairs from glucose and physics arrays."""
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


def split_data(X, y, train_frac=0.8):
    n = len(X)
    split = int(n * train_frac)
    return X[:split], X[split:], y[:split], y[split:]


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


def clarke_error_grid(y_true_mgdl, y_pred_mgdl):
    """Compute Clarke Error Grid zone percentages."""
    n = len(y_true_mgdl)
    if n == 0:
        return {'A': 0.0, 'B': 0.0, 'C': 0.0, 'D': 0.0, 'E': 0.0}
    zones = {'A': 0, 'B': 0, 'C': 0, 'D': 0, 'E': 0}
    for ref, pred in zip(y_true_mgdl, y_pred_mgdl):
        if ref <= 70 and pred <= 70:
            zones['A'] += 1
        elif ref >= 180 and pred >= 180:
            zones['A'] += 1
        elif 70 <= ref <= 180 and abs(pred - ref) <= 20:
            zones['A'] += 1
        elif abs(pred - ref) <= 0.2 * ref:
            zones['A'] += 1
        elif (ref >= 180 and pred <= 70) or (ref <= 70 and pred >= 180):
            zones['E'] += 1
        elif ref <= 70 and pred >= 180:
            zones['E'] += 1
        elif ref >= 240 and pred <= 70:
            zones['E'] += 1
        else:
            zones['B'] += 1
    return {k: v / n for k, v in zones.items()}


def train_cnn_residual(X_train, residuals_train, X_val, in_channels,
                       epochs=60, lr=1e-3):
    """Train a ResidualCNN to predict residuals, return val predictions."""
    model = ResidualCNN(in_channels, window_size=WINDOW).to(DEVICE)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = nn.MSELoss()

    Xt = torch.tensor(X_train, dtype=torch.float32).to(DEVICE)
    yt = torch.tensor(residuals_train, dtype=torch.float32).to(DEVICE)
    Xv = torch.tensor(X_val, dtype=torch.float32).to(DEVICE)

    batch = min(256, len(Xt))
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


# ---------------------------------------------------------------------------
# Grand feature set builder (shared by EXP-1091, 1092, 1100)
# ---------------------------------------------------------------------------

def build_grand_features(glucose, physics, window=WINDOW, horizon=HORIZON,
                         stride=STRIDE):
    """Build the grand feature set: glucose + physics + interactions +
    derivatives + statistics + cross-correlation.

    Returns flat (N, D) feature matrix and (N,) targets.
    """
    g = glucose / GLUCOSE_SCALE
    n = len(g)
    X_list, y_list = [], []

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

        # --- base features ---
        base = np.concatenate([g_win, p_win.ravel()])

        # --- physics interaction terms ---
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

        # --- glucose derivatives at multiple scales ---
        derivatives = []
        for scale in [3, 6, 12]:
            if len(g_win) > scale:
                roc = np.mean(np.diff(g_win[::max(1, scale // 3)]))
            else:
                roc = 0.0
            derivatives.append(roc)
        # acceleration
        if len(g_win) > 2:
            d1 = np.diff(g_win)
            accel = np.mean(np.diff(d1))
        else:
            accel = 0.0
        derivatives.append(accel)
        derivatives = np.array(derivatives)

        # --- window statistics ---
        g_std = np.std(g_win)
        g_min = np.min(g_win)
        g_max = np.max(g_win)
        g_range = g_max - g_min
        g_cv = g_std / g_mean if g_mean > 0 else 0.0
        stats = np.array([g_mean, g_std, g_min, g_max, g_range, g_cv])

        feat = np.concatenate([base, interactions, derivatives, stats])
        X_list.append(feat)
        y_list.append(y_val)

    if len(X_list) == 0:
        return np.array([]).reshape(0, 1), np.array([])
    return np.array(X_list), np.array(y_list)


# ---------------------------------------------------------------------------
# EXP-1091: GB Grand Features Block CV
# ---------------------------------------------------------------------------

def exp_1091_gb_grand_cv(patients, detail=False):
    """Validate GB R²=0.538 under rigorous 3-fold block CV with grand features.

    Compares GB(200, depth=4, lr=0.05) vs Ridge on full grand feature set.
    """
    results = []
    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        n = min(len(glucose), len(physics))
        if n < WINDOW + HORIZON + 50:
            continue
        glucose, physics = glucose[:n], physics[:n]

        X, y = build_grand_features(glucose, physics)
        if len(X) < 200:
            continue

        def gb_fn():
            return GradientBoostingRegressor(
                n_estimators=200, max_depth=4, learning_rate=0.05,
                random_state=42)

        def ridge_fn():
            return Ridge(alpha=1.0)

        gb_mean, gb_folds = block_cv_score(X, y, gb_fn, n_folds=3)
        ridge_mean, ridge_folds = block_cv_score(X, y, ridge_fn, n_folds=3)

        res = {
            'patient': p['name'],
            'gb_r2_mean': round(gb_mean, 4),
            'gb_r2_folds': [round(s, 4) for s in gb_folds],
            'ridge_r2_mean': round(ridge_mean, 4),
            'ridge_r2_folds': [round(s, 4) for s in ridge_folds],
            'gb_advantage': round(gb_mean - ridge_mean, 4),
            'n_samples': len(X),
        }
        results.append(res)
        if detail:
            print(f"    {p['name']}: GB={gb_mean:.4f} Ridge={ridge_mean:.4f} "
                  f"(+{gb_mean - ridge_mean:+.4f})")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    mean_gb = np.mean([r['gb_r2_mean'] for r in results])
    mean_ridge = np.mean([r['ridge_r2_mean'] for r in results])
    summary = {
        'mean_gb_r2': round(mean_gb, 4),
        'mean_ridge_r2': round(mean_ridge, 4),
        'mean_gb_advantage': round(mean_gb - mean_ridge, 4),
        'n_gb_wins': sum(1 for r in results if r['gb_advantage'] > 0),
        'n_patients': len(results),
    }
    return {
        'status': 'pass',
        'detail': (f'GB={mean_gb:.4f} Ridge={mean_ridge:.4f} '
                   f'(+{mean_gb - mean_ridge:+.4f}, '
                   f'{summary["n_gb_wins"]}/{len(results)} GB wins)'),
        'results': {'per_patient': results, 'summary': summary},
    }


# ---------------------------------------------------------------------------
# EXP-1092: GB + CNN Residual on Grand Features
# ---------------------------------------------------------------------------

def exp_1092_gb_cnn_residual(patients, detail=False):
    """Combine GB with CNN residual correction on grand features.

    Pipeline: GB predicts, CNN corrects residuals.
    Compares Ridge, GB, Ridge+CNN, GB+CNN.
    """
    results = []
    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        n = min(len(glucose), len(physics))
        if n < WINDOW + HORIZON + 50:
            continue
        glucose, physics = glucose[:n], physics[:n]

        # Grand features for Ridge/GB
        X_grand, y = build_grand_features(glucose, physics)
        if len(X_grand) < 200:
            continue

        # Window features for CNN (needs 3D: N x W x C)
        X_win, y_win = make_windows(glucose, physics)
        if len(X_win) < 200:
            continue

        # Align lengths (grand and windowed may differ slightly)
        min_len = min(len(X_grand), len(X_win))
        X_grand, X_win, y = X_grand[:min_len], X_win[:min_len], y[:min_len]

        X_g_tr, X_g_vl, y_tr, y_vl = split_data(X_grand, y)
        X_w_tr, X_w_vl, _, _ = split_data(X_win, y)

        # Ridge
        ridge = Ridge(alpha=1.0)
        ridge.fit(X_g_tr, y_tr)
        pred_ridge = ridge.predict(X_g_vl)
        r2_ridge = compute_r2(y_vl, pred_ridge)

        # GB
        gb = GradientBoostingRegressor(
            n_estimators=200, max_depth=4, learning_rate=0.05, random_state=42)
        gb.fit(X_g_tr, y_tr)
        pred_gb = gb.predict(X_g_vl)
        r2_gb = compute_r2(y_vl, pred_gb)

        in_ch = X_win.shape[2]

        # Ridge + CNN residual
        resid_ridge_tr = y_tr - ridge.predict(X_g_tr)
        cnn_corr_ridge = train_cnn_residual(
            X_w_tr, resid_ridge_tr, X_w_vl, in_ch)
        pred_ridge_cnn = pred_ridge + cnn_corr_ridge
        r2_ridge_cnn = compute_r2(y_vl, pred_ridge_cnn)

        # GB + CNN residual
        resid_gb_tr = y_tr - gb.predict(X_g_tr)
        cnn_corr_gb = train_cnn_residual(
            X_w_tr, resid_gb_tr, X_w_vl, in_ch)
        pred_gb_cnn = pred_gb + cnn_corr_gb
        r2_gb_cnn = compute_r2(y_vl, pred_gb_cnn)

        res = {
            'patient': p['name'],
            'r2_ridge': round(r2_ridge, 4),
            'r2_gb': round(r2_gb, 4),
            'r2_ridge_cnn': round(r2_ridge_cnn, 4),
            'r2_gb_cnn': round(r2_gb_cnn, 4),
            'best_model': max(
                [('Ridge', r2_ridge), ('GB', r2_gb),
                 ('Ridge+CNN', r2_ridge_cnn), ('GB+CNN', r2_gb_cnn)],
                key=lambda x: x[1])[0],
            'n_samples': min_len,
        }
        results.append(res)
        if detail:
            print(f"    {p['name']}: Ridge={r2_ridge:.4f} GB={r2_gb:.4f} "
                  f"Ridge+CNN={r2_ridge_cnn:.4f} GB+CNN={r2_gb_cnn:.4f}")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    summary = {
        'mean_ridge': round(np.mean([r['r2_ridge'] for r in results]), 4),
        'mean_gb': round(np.mean([r['r2_gb'] for r in results]), 4),
        'mean_ridge_cnn': round(np.mean([r['r2_ridge_cnn'] for r in results]), 4),
        'mean_gb_cnn': round(np.mean([r['r2_gb_cnn'] for r in results]), 4),
        'best_counts': {m: sum(1 for r in results if r['best_model'] == m)
                        for m in ['Ridge', 'GB', 'Ridge+CNN', 'GB+CNN']},
        'n_patients': len(results),
    }
    best_method = max(
        [('Ridge', summary['mean_ridge']), ('GB', summary['mean_gb']),
         ('Ridge+CNN', summary['mean_ridge_cnn']),
         ('GB+CNN', summary['mean_gb_cnn'])],
        key=lambda x: x[1])
    return {
        'status': 'pass',
        'detail': (f'Ridge={summary["mean_ridge"]:.4f} '
                   f'GB={summary["mean_gb"]:.4f} '
                   f'Ridge+CNN={summary["mean_ridge_cnn"]:.4f} '
                   f'GB+CNN={summary["mean_gb_cnn"]:.4f} '
                   f'(best: {best_method[0]})'),
        'results': {'per_patient': results, 'summary': summary},
    }


# ---------------------------------------------------------------------------
# EXP-1093: Per-Patient DIA Optimization
# ---------------------------------------------------------------------------

def exp_1093_dia_optimization(patients, detail=False):
    """Sweep DIA from 3h to 7h in 0.5h steps per patient.

    Rebuilds PK with build_continuous_pk_features(df, dia_hours=dia),
    recomputes supply/demand, trains Ridge, finds optimal DIA.
    """
    dia_values = np.arange(3.0, 7.5, 0.5)  # 3.0, 3.5, ..., 7.0
    results = []

    for p in patients:
        df = p['df']
        if len(df) < WINDOW + HORIZON + 50:
            continue

        glucose = df['glucose'].values.astype(float)

        dia_scores = {}
        for dia in dia_values:
            try:
                pk_new = build_continuous_pk_features(df, dia_hours=float(dia))
                if pk_new is None:
                    continue
                n = min(len(glucose), len(pk_new))
                sd = compute_supply_demand(df.iloc[:n], pk_new[:n])

                supply = sd['supply'] / 20.0
                demand = sd['demand'] / 20.0
                hepatic = sd['hepatic'] / 5.0
                net = sd['net'] / 20.0
                physics = np.column_stack([supply, demand, hepatic, net])

                X, y = make_windows(glucose[:n], physics)
                if len(X) < 200:
                    continue

                Xf = X.reshape(len(X), -1)
                X_tr, X_vl, y_tr, y_vl = split_data(Xf, y)

                ridge = Ridge(alpha=1.0)
                ridge.fit(X_tr, y_tr)
                r2 = compute_r2(y_vl, ridge.predict(X_vl))
                dia_scores[float(dia)] = round(r2, 4)
            except Exception:
                continue

        if not dia_scores:
            continue

        best_dia = max(dia_scores, key=dia_scores.get)
        default_r2 = dia_scores.get(5.0, 0.0)
        best_r2 = dia_scores[best_dia]

        res = {
            'patient': p['name'],
            'optimal_dia': best_dia,
            'r2_optimal': best_r2,
            'r2_default_5h': default_r2,
            'improvement': round(best_r2 - default_r2, 4),
            'dia_sweep': dia_scores,
        }
        results.append(res)
        if detail:
            print(f"    {p['name']}: optimal DIA={best_dia:.1f}h "
                  f"R²={best_r2:.4f} (default 5h={default_r2:.4f}, "
                  f"+{best_r2 - default_r2:+.4f})")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    summary = {
        'mean_optimal_dia': round(np.mean([r['optimal_dia'] for r in results]), 2),
        'std_optimal_dia': round(np.std([r['optimal_dia'] for r in results]), 2),
        'mean_r2_optimal': round(np.mean([r['r2_optimal'] for r in results]), 4),
        'mean_r2_default': round(np.mean([r['r2_default_5h'] for r in results]), 4),
        'mean_improvement': round(np.mean([r['improvement'] for r in results]), 4),
        'n_improved': sum(1 for r in results if r['improvement'] > 0),
        'n_patients': len(results),
    }
    return {
        'status': 'pass',
        'detail': (f'mean optimal DIA={summary["mean_optimal_dia"]:.1f}h '
                   f'(±{summary["std_optimal_dia"]:.1f}), '
                   f'R²={summary["mean_r2_optimal"]:.4f} vs '
                   f'default={summary["mean_r2_default"]:.4f} '
                   f'(+{summary["mean_improvement"]:+.4f}, '
                   f'{summary["n_improved"]}/{len(results)} improved)'),
        'results': {'per_patient': results, 'summary': summary},
    }


# ---------------------------------------------------------------------------
# EXP-1094: Per-Patient ISF Scaling
# ---------------------------------------------------------------------------

def exp_1094_isf_scaling(patients, detail=False):
    """Scale demand channel by learned factor per patient.

    Sweeps demand scaling from 0.5 to 2.0 in 0.1 steps.
    Simulates different insulin sensitivities.
    """
    scale_values = np.arange(0.5, 2.05, 0.1)
    results = []

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        n = min(len(glucose), len(physics))
        if n < WINDOW + HORIZON + 50:
            continue
        glucose, physics = glucose[:n], physics[:n]

        scale_scores = {}
        for scale in scale_values:
            scaled_physics = physics.copy()
            scaled_physics[:, 1] *= scale  # scale demand channel

            X, y = make_windows(glucose, scaled_physics)
            if len(X) < 200:
                continue

            Xf = X.reshape(len(X), -1)
            X_tr, X_vl, y_tr, y_vl = split_data(Xf, y)

            ridge = Ridge(alpha=1.0)
            ridge.fit(X_tr, y_tr)
            r2 = compute_r2(y_vl, ridge.predict(X_vl))
            scale_scores[round(float(scale), 1)] = round(r2, 4)

        if not scale_scores:
            continue

        best_scale = max(scale_scores, key=scale_scores.get)
        default_r2 = scale_scores.get(1.0, 0.0)
        best_r2 = scale_scores[best_scale]

        res = {
            'patient': p['name'],
            'optimal_scale': best_scale,
            'r2_optimal': best_r2,
            'r2_default_1x': default_r2,
            'improvement': round(best_r2 - default_r2, 4),
            'scale_sweep': scale_scores,
        }
        results.append(res)
        if detail:
            print(f"    {p['name']}: optimal scale={best_scale:.1f}x "
                  f"R²={best_r2:.4f} (default 1x={default_r2:.4f}, "
                  f"+{best_r2 - default_r2:+.4f})")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    summary = {
        'mean_optimal_scale': round(np.mean(
            [r['optimal_scale'] for r in results]), 2),
        'std_optimal_scale': round(np.std(
            [r['optimal_scale'] for r in results]), 2),
        'mean_r2_optimal': round(np.mean(
            [r['r2_optimal'] for r in results]), 4),
        'mean_r2_default': round(np.mean(
            [r['r2_default_1x'] for r in results]), 4),
        'mean_improvement': round(np.mean(
            [r['improvement'] for r in results]), 4),
        'n_improved': sum(1 for r in results if r['improvement'] > 0),
        'n_patients': len(results),
    }
    return {
        'status': 'pass',
        'detail': (f'mean scale={summary["mean_optimal_scale"]:.1f}x '
                   f'(±{summary["std_optimal_scale"]:.1f}), '
                   f'R²={summary["mean_r2_optimal"]:.4f} vs '
                   f'default={summary["mean_r2_default"]:.4f} '
                   f'(+{summary["mean_improvement"]:+.4f}, '
                   f'{summary["n_improved"]}/{len(results)} improved)'),
        'results': {'per_patient': results, 'summary': summary},
    }


# ---------------------------------------------------------------------------
# EXP-1095: Multi-Scale Context (6h + 12h + 24h summaries)
# ---------------------------------------------------------------------------

def _compute_context_stats(glucose_norm, end_idx, context_steps):
    """Compute 5 summary stats for a glucose context window."""
    start = max(0, end_idx - context_steps)
    segment = glucose_norm[start:end_idx]
    segment = segment[~np.isnan(segment)]
    if len(segment) < 3:
        return np.zeros(5)
    mean = np.mean(segment)
    std = np.std(segment)
    mn = np.min(segment)
    mx = np.max(segment)
    # linear trend (slope per step)
    x = np.arange(len(segment), dtype=float)
    if len(segment) > 1:
        slope = np.polyfit(x, segment, 1)[0]
    else:
        slope = 0.0
    return np.array([mean, std, mn, mx, slope])


def exp_1095_multiscale_context(patients, detail=False):
    """Add longer-range glucose context as auxiliary features.

    For each sample, compute mean/std/min/max/trend for 6h, 12h, 24h
    windows preceding the 2h detail window. Adds 15 features.
    """
    STEPS_6H = 72     # 6h / 5min
    STEPS_12H = 144   # 12h / 5min
    STEPS_24H = 288   # 24h / 5min

    results = []
    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        n = min(len(glucose), len(physics))
        if n < STEPS_24H + WINDOW + HORIZON + 50:
            continue
        glucose, physics = glucose[:n], physics[:n]
        g_norm = glucose / GLUCOSE_SCALE

        # Base features
        X_base, y_base = make_windows(glucose, physics)
        if len(X_base) < 200:
            continue
        Xf_base = X_base.reshape(len(X_base), -1)

        # Build multi-scale context features
        context_feats = []
        context_y = []
        for i in range(0, n - WINDOW - HORIZON, STRIDE):
            g_win = g_norm[i:i + WINDOW]
            if np.isnan(g_win).mean() > 0.3:
                continue
            y_val = g_norm[i + WINDOW + HORIZON - 1]
            if np.isnan(y_val):
                continue

            ctx_6h = _compute_context_stats(g_norm, i, STEPS_6H)
            ctx_12h = _compute_context_stats(g_norm, i, STEPS_12H)
            ctx_24h = _compute_context_stats(g_norm, i, STEPS_24H)
            context_feats.append(np.concatenate([ctx_6h, ctx_12h, ctx_24h]))
            context_y.append(y_val)

        if len(context_feats) < 200:
            continue

        context_feats = np.array(context_feats)
        # Align with base features
        min_len = min(len(Xf_base), len(context_feats))
        Xf_base_aligned = Xf_base[:min_len]
        context_aligned = context_feats[:min_len]
        y_aligned = y_base[:min_len]

        X_enhanced = np.hstack([Xf_base_aligned, context_aligned])

        X_b_tr, X_b_vl, y_tr, y_vl = split_data(Xf_base_aligned, y_aligned)
        X_e_tr, X_e_vl, _, _ = split_data(X_enhanced, y_aligned)

        # Ridge
        ridge_base = Ridge(alpha=1.0)
        ridge_base.fit(X_b_tr, y_tr)
        r2_ridge_base = compute_r2(y_vl, ridge_base.predict(X_b_vl))

        ridge_enhanced = Ridge(alpha=1.0)
        ridge_enhanced.fit(X_e_tr, y_tr)
        r2_ridge_enh = compute_r2(y_vl, ridge_enhanced.predict(X_e_vl))

        # GB
        gb_base = GradientBoostingRegressor(
            n_estimators=200, max_depth=4, learning_rate=0.05, random_state=42)
        gb_base.fit(X_b_tr, y_tr)
        r2_gb_base = compute_r2(y_vl, gb_base.predict(X_b_vl))

        gb_enhanced = GradientBoostingRegressor(
            n_estimators=200, max_depth=4, learning_rate=0.05, random_state=42)
        gb_enhanced.fit(X_e_tr, y_tr)
        r2_gb_enh = compute_r2(y_vl, gb_enhanced.predict(X_e_vl))

        res = {
            'patient': p['name'],
            'r2_ridge_base': round(r2_ridge_base, 4),
            'r2_ridge_context': round(r2_ridge_enh, 4),
            'r2_gb_base': round(r2_gb_base, 4),
            'r2_gb_context': round(r2_gb_enh, 4),
            'ridge_gain': round(r2_ridge_enh - r2_ridge_base, 4),
            'gb_gain': round(r2_gb_enh - r2_gb_base, 4),
            'n_samples': min_len,
        }
        results.append(res)
        if detail:
            print(f"    {p['name']}: Ridge {r2_ridge_base:.4f}->"
                  f"{r2_ridge_enh:.4f} ({r2_ridge_enh - r2_ridge_base:+.4f})  "
                  f"GB {r2_gb_base:.4f}->{r2_gb_enh:.4f} "
                  f"({r2_gb_enh - r2_gb_base:+.4f})")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    summary = {
        'mean_ridge_base': round(np.mean(
            [r['r2_ridge_base'] for r in results]), 4),
        'mean_ridge_context': round(np.mean(
            [r['r2_ridge_context'] for r in results]), 4),
        'mean_gb_base': round(np.mean(
            [r['r2_gb_base'] for r in results]), 4),
        'mean_gb_context': round(np.mean(
            [r['r2_gb_context'] for r in results]), 4),
        'mean_ridge_gain': round(np.mean(
            [r['ridge_gain'] for r in results]), 4),
        'mean_gb_gain': round(np.mean(
            [r['gb_gain'] for r in results]), 4),
        'n_patients': len(results),
    }
    return {
        'status': 'pass',
        'detail': (f'Ridge: {summary["mean_ridge_base"]:.4f}->'
                   f'{summary["mean_ridge_context"]:.4f} '
                   f'({summary["mean_ridge_gain"]:+.4f})  '
                   f'GB: {summary["mean_gb_base"]:.4f}->'
                   f'{summary["mean_gb_context"]:.4f} '
                   f'({summary["mean_gb_gain"]:+.4f})'),
        'results': {'per_patient': results, 'summary': summary},
    }


# ---------------------------------------------------------------------------
# EXP-1096: Two-Resolution Model
# ---------------------------------------------------------------------------

def exp_1096_two_resolution(patients, detail=False):
    """Dual-window approach: fine (2h/5min) + coarse (12h/30min).

    Fine: 24 points at 5-min resolution (current approach).
    Coarse: 24 points subsampled from 12h at 30-min resolution.
    Compares: fine-only vs coarse-only vs fine+coarse.
    """
    COARSE_WINDOW_STEPS = 144  # 12h at 5-min = 144 points
    COARSE_SUBSAMPLE = 6       # every 6th -> 24 points at 30-min

    results = []
    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        n = min(len(glucose), len(physics))
        if n < COARSE_WINDOW_STEPS + WINDOW + HORIZON + 50:
            continue
        glucose, physics = glucose[:n], physics[:n]
        g = glucose / GLUCOSE_SCALE

        fine_list, coarse_list, both_list, y_list = [], [], [], []

        start_range = COARSE_WINDOW_STEPS
        for i in range(start_range, n - WINDOW - HORIZON, STRIDE):
            g_fine = g[i:i + WINDOW]
            if np.isnan(g_fine).mean() > 0.3:
                continue
            g_fine = np.nan_to_num(
                g_fine,
                nan=np.nanmean(g_fine) if np.any(~np.isnan(g_fine)) else 0.4,
            )

            # Coarse: 12h history ending at start of fine window
            coarse_start = i - COARSE_WINDOW_STEPS
            g_coarse_full = g[coarse_start:i]
            g_coarse = g_coarse_full[::COARSE_SUBSAMPLE][:WINDOW]
            if len(g_coarse) < WINDOW:
                pad = np.full(WINDOW - len(g_coarse), g_coarse[-1]
                              if len(g_coarse) > 0 else 0.4)
                g_coarse = np.concatenate([pad, g_coarse])
            g_coarse = np.nan_to_num(g_coarse, nan=0.4)

            y_val = g[i + WINDOW + HORIZON - 1]
            if np.isnan(y_val):
                continue

            fine_list.append(g_fine)
            coarse_list.append(g_coarse)
            both_list.append(np.concatenate([g_fine, g_coarse]))
            y_list.append(y_val)

        if len(fine_list) < 200:
            continue

        X_fine = np.array(fine_list)
        X_coarse = np.array(coarse_list)
        X_both = np.array(both_list)
        y = np.array(y_list)

        scores = {}
        for label, X in [('fine', X_fine), ('coarse', X_coarse),
                          ('fine+coarse', X_both)]:
            X_tr, X_vl, y_tr, y_vl = split_data(X, y)
            ridge = Ridge(alpha=1.0)
            ridge.fit(X_tr, y_tr)
            scores[f'ridge_{label}'] = round(compute_r2(
                y_vl, ridge.predict(X_vl)), 4)

            gb = GradientBoostingRegressor(
                n_estimators=200, max_depth=4, learning_rate=0.05,
                random_state=42)
            gb.fit(X_tr, y_tr)
            scores[f'gb_{label}'] = round(compute_r2(
                y_vl, gb.predict(X_vl)), 4)

        res = {'patient': p['name'], 'n_samples': len(y), **scores}
        results.append(res)
        if detail:
            print(f"    {p['name']}: "
                  f"fine={scores['ridge_fine']:.4f}/{scores['gb_fine']:.4f} "
                  f"coarse={scores['ridge_coarse']:.4f}/"
                  f"{scores['gb_coarse']:.4f} "
                  f"both={scores['ridge_fine+coarse']:.4f}/"
                  f"{scores['gb_fine+coarse']:.4f}")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    keys = ['ridge_fine', 'ridge_coarse', 'ridge_fine+coarse',
            'gb_fine', 'gb_coarse', 'gb_fine+coarse']
    summary = {k: round(np.mean([r[k] for r in results]), 4) for k in keys}
    summary['n_patients'] = len(results)
    return {
        'status': 'pass',
        'detail': (f'Ridge fine={summary["ridge_fine"]:.4f} '
                   f'coarse={summary["ridge_coarse"]:.4f} '
                   f'both={summary["ridge_fine+coarse"]:.4f}  '
                   f'GB fine={summary["gb_fine"]:.4f} '
                   f'coarse={summary["gb_coarse"]:.4f} '
                   f'both={summary["gb_fine+coarse"]:.4f}'),
        'results': {'per_patient': results, 'summary': summary},
    }


# ---------------------------------------------------------------------------
# EXP-1097: Residual Analysis by Context
# ---------------------------------------------------------------------------

def exp_1097_residual_analysis(patients, detail=False):
    """Analyze prediction residuals by time-of-day, glucose regime, day-of-week.

    Diagnostic experiment — no model improvement, just understanding
    when predictions fail.
    """
    results = []
    all_tod = {'overnight': [], 'morning': [], 'afternoon': [], 'evening': []}
    all_regime = {'hypo': [], 'low_normal': [], 'in_range': [], 'high': []}
    all_dow = {str(d): [] for d in range(7)}

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        df = p['df']
        n = min(len(glucose), len(physics), len(df))
        if n < WINDOW + HORIZON + 50:
            continue
        glucose, physics = glucose[:n], physics[:n]

        X, y = make_windows(glucose, physics)
        if len(X) < 200:
            continue

        Xf = X.reshape(len(X), -1)
        X_tr, X_vl, y_tr, y_vl = split_data(Xf, y)

        gb = GradientBoostingRegressor(
            n_estimators=200, max_depth=4, learning_rate=0.05, random_state=42)
        gb.fit(X_tr, y_tr)
        pred = gb.predict(X_vl)
        residuals = y_vl - pred

        # Map validation indices to original timestamps
        split_idx = int(len(X) * 0.8)
        val_indices = []
        sample_idx = 0
        for i in range(0, n - WINDOW - HORIZON, STRIDE):
            g_win = glucose[i:i + WINDOW] / GLUCOSE_SCALE
            if np.isnan(g_win).mean() > 0.3:
                continue
            y_val = glucose[i + WINDOW + HORIZON - 1] / GLUCOSE_SCALE
            if np.isnan(y_val):
                continue
            if sample_idx >= split_idx:
                val_indices.append(i + WINDOW + HORIZON - 1)
            sample_idx += 1
            if sample_idx > split_idx + len(y_vl):
                break

        min_vi = min(len(val_indices), len(y_vl))
        val_indices = val_indices[:min_vi]

        tod_scores = {}
        regime_scores = {}
        dow_scores = {}

        for j, vi in enumerate(val_indices):
            if j >= len(y_vl):
                break
            err = float(residuals[j] ** 2)
            ae = float(abs(residuals[j]))
            true_mgdl = float(y_vl[j] * GLUCOSE_SCALE)

            # Time of day
            if vi < len(df) and 'dateString' in df.columns:
                try:
                    ts = df.iloc[vi]['dateString']
                    if hasattr(ts, 'hour'):
                        hour = ts.hour
                    else:
                        import pandas as pd
                        hour = pd.Timestamp(ts).hour
                except Exception:
                    hour = (vi * 5 // 60) % 24

                if 0 <= hour < 6:
                    tod = 'overnight'
                elif 6 <= hour < 12:
                    tod = 'morning'
                elif 12 <= hour < 18:
                    tod = 'afternoon'
                else:
                    tod = 'evening'
            else:
                hour = (vi * 5 // 60) % 24
                if 0 <= hour < 6:
                    tod = 'overnight'
                elif 6 <= hour < 12:
                    tod = 'morning'
                elif 12 <= hour < 18:
                    tod = 'afternoon'
                else:
                    tod = 'evening'

            all_tod[tod].append((float(y_vl[j]), float(pred[j])))

            # Glucose regime
            if true_mgdl < 70:
                regime = 'hypo'
            elif true_mgdl < 100:
                regime = 'low_normal'
            elif true_mgdl <= 180:
                regime = 'in_range'
            else:
                regime = 'high'
            all_regime[regime].append((float(y_vl[j]), float(pred[j])))

            # Day of week
            if vi < len(df) and 'dateString' in df.columns:
                try:
                    ts = df.iloc[vi]['dateString']
                    if hasattr(ts, 'weekday'):
                        dow = str(ts.weekday())
                    else:
                        import pandas as pd
                        dow = str(pd.Timestamp(ts).weekday())
                except Exception:
                    dow = str((vi // 288) % 7)
            else:
                dow = str((vi // 288) % 7)
            all_dow[dow].append((float(y_vl[j]), float(pred[j])))

        r2_patient = compute_r2(y_vl, pred)
        mae_patient = compute_mae(y_vl, pred)
        results.append({
            'patient': p['name'],
            'r2': round(r2_patient, 4),
            'mae': round(mae_patient, 4),
            'n_val_samples': len(y_vl),
        })
        if detail:
            print(f"    {p['name']}: R²={r2_patient:.4f} MAE={mae_patient:.4f}")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    # Aggregate subgroup scores
    def subgroup_metrics(pairs):
        if len(pairs) < 10:
            return {'r2': None, 'mae': None, 'n': len(pairs)}
        yt = np.array([p[0] for p in pairs])
        yp = np.array([p[1] for p in pairs])
        return {
            'r2': round(compute_r2(yt, yp), 4),
            'mae': round(compute_mae(yt, yp), 4),
            'n': len(pairs),
        }

    tod_metrics = {k: subgroup_metrics(v) for k, v in all_tod.items()}
    regime_metrics = {k: subgroup_metrics(v) for k, v in all_regime.items()}
    dow_metrics = {k: subgroup_metrics(v) for k, v in all_dow.items()}

    summary = {
        'time_of_day': tod_metrics,
        'glucose_regime': regime_metrics,
        'day_of_week': dow_metrics,
        'mean_r2': round(np.mean([r['r2'] for r in results]), 4),
        'n_patients': len(results),
    }

    if detail:
        print("\n  Time-of-day breakdown:")
        for k, v in tod_metrics.items():
            r2_str = f"{v['r2']:.4f}" if v['r2'] is not None else "N/A"
            print(f"    {k:12s}: R²={r2_str} (n={v['n']})")
        print("  Glucose regime breakdown:")
        for k, v in regime_metrics.items():
            r2_str = f"{v['r2']:.4f}" if v['r2'] is not None else "N/A"
            print(f"    {k:12s}: R²={r2_str} (n={v['n']})")

    return {
        'status': 'pass',
        'detail': (f'mean R²={summary["mean_r2"]:.4f}, '
                   f'overnight={tod_metrics["overnight"].get("r2", "N/A")}, '
                   f'morning={tod_metrics["morning"].get("r2", "N/A")}, '
                   f'in_range={regime_metrics["in_range"].get("r2", "N/A")}, '
                   f'hypo={regime_metrics["hypo"].get("r2", "N/A")}'),
        'results': {'per_patient': results, 'summary': summary},
    }


# ---------------------------------------------------------------------------
# EXP-1098: Overnight vs Daytime Models
# ---------------------------------------------------------------------------

def exp_1098_overnight_daytime(patients, detail=False):
    """Train separate models for overnight (00:00-06:00) vs daytime (06:00-24:00).

    Hypothesis: overnight (no meals, stable basal) should be more predictable.
    Compares unified model vs separate models on respective subsets.
    """
    results = []

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        df = p['df']
        n = min(len(glucose), len(physics), len(df))
        if n < WINDOW + HORIZON + 50:
            continue
        glucose, physics = glucose[:n], physics[:n]
        g = glucose / GLUCOSE_SCALE

        # Build windows with time-of-day labels
        overnight_X, overnight_y = [], []
        daytime_X, daytime_y = [], []
        all_X, all_y = [], []

        for i in range(0, n - WINDOW - HORIZON, STRIDE):
            g_win = g[i:i + WINDOW]
            if np.isnan(g_win).mean() > 0.3:
                continue
            g_win = np.nan_to_num(
                g_win,
                nan=np.nanmean(g_win) if np.any(~np.isnan(g_win)) else 0.4,
            )
            p_win = physics[i:i + WINDOW]
            if np.isnan(p_win).any():
                p_win = np.nan_to_num(p_win, nan=0.0)
            y_val = g[i + WINDOW + HORIZON - 1]
            if np.isnan(y_val):
                continue

            feat = np.concatenate([g_win, p_win.ravel()])
            all_X.append(feat)
            all_y.append(y_val)

            # Determine time of day for window start
            if i < len(df) and 'dateString' in df.columns:
                try:
                    ts = df.iloc[i]['dateString']
                    if hasattr(ts, 'hour'):
                        hour = ts.hour
                    else:
                        import pandas as pd
                        hour = pd.Timestamp(ts).hour
                except Exception:
                    hour = (i * 5 // 60) % 24
            else:
                hour = (i * 5 // 60) % 24

            if 0 <= hour < 6:
                overnight_X.append(feat)
                overnight_y.append(y_val)
            else:
                daytime_X.append(feat)
                daytime_y.append(y_val)

        if len(all_X) < 200:
            continue

        all_X, all_y = np.array(all_X), np.array(all_y)

        # Unified model (trained on all, evaluated on subsets)
        X_tr, X_vl, y_tr, y_vl = split_data(all_X, all_y)
        gb_unified = GradientBoostingRegressor(
            n_estimators=200, max_depth=4, learning_rate=0.05, random_state=42)
        gb_unified.fit(X_tr, y_tr)
        r2_unified = compute_r2(y_vl, gb_unified.predict(X_vl))

        res = {
            'patient': p['name'],
            'r2_unified': round(r2_unified, 4),
            'n_total': len(all_X),
            'n_overnight': len(overnight_X),
            'n_daytime': len(daytime_X),
        }

        # Separate overnight model
        if len(overnight_X) >= 50:
            on_X, on_y = np.array(overnight_X), np.array(overnight_y)
            on_tr, on_vl, on_ytr, on_yvl = split_data(on_X, on_y)
            gb_on = GradientBoostingRegressor(
                n_estimators=200, max_depth=4, learning_rate=0.05,
                random_state=42)
            gb_on.fit(on_tr, on_ytr)
            r2_on_separate = compute_r2(on_yvl, gb_on.predict(on_vl))
            r2_on_unified = compute_r2(
                on_yvl, gb_unified.predict(on_vl))
            res['r2_overnight_separate'] = round(r2_on_separate, 4)
            res['r2_overnight_unified'] = round(r2_on_unified, 4)
        else:
            res['r2_overnight_separate'] = None
            res['r2_overnight_unified'] = None

        # Separate daytime model
        if len(daytime_X) >= 50:
            day_X, day_y = np.array(daytime_X), np.array(daytime_y)
            day_tr, day_vl, day_ytr, day_yvl = split_data(day_X, day_y)
            gb_day = GradientBoostingRegressor(
                n_estimators=200, max_depth=4, learning_rate=0.05,
                random_state=42)
            gb_day.fit(day_tr, day_ytr)
            r2_day_separate = compute_r2(day_yvl, gb_day.predict(day_vl))
            r2_day_unified = compute_r2(
                day_yvl, gb_unified.predict(day_vl))
            res['r2_daytime_separate'] = round(r2_day_separate, 4)
            res['r2_daytime_unified'] = round(r2_day_unified, 4)
        else:
            res['r2_daytime_separate'] = None
            res['r2_daytime_unified'] = None

        results.append(res)
        if detail:
            on_sep = res.get('r2_overnight_separate')
            on_uni = res.get('r2_overnight_unified')
            day_sep = res.get('r2_daytime_separate')
            day_uni = res.get('r2_daytime_unified')
            on_str = (f"ON: sep={on_sep:.4f} uni={on_uni:.4f}"
                      if on_sep is not None else "ON: N/A")
            day_str = (f"DAY: sep={day_sep:.4f} uni={day_uni:.4f}"
                       if day_sep is not None else "DAY: N/A")
            print(f"    {p['name']}: unified={r2_unified:.4f} {on_str} "
                  f"{day_str}")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    def safe_mean(vals):
        valid = [v for v in vals if v is not None]
        return round(np.mean(valid), 4) if valid else None

    summary = {
        'mean_unified': round(np.mean(
            [r['r2_unified'] for r in results]), 4),
        'mean_overnight_separate': safe_mean(
            [r['r2_overnight_separate'] for r in results]),
        'mean_overnight_unified': safe_mean(
            [r['r2_overnight_unified'] for r in results]),
        'mean_daytime_separate': safe_mean(
            [r['r2_daytime_separate'] for r in results]),
        'mean_daytime_unified': safe_mean(
            [r['r2_daytime_unified'] for r in results]),
        'n_patients': len(results),
    }

    on_sep = summary['mean_overnight_separate']
    day_sep = summary['mean_daytime_separate']
    return {
        'status': 'pass',
        'detail': (f'unified={summary["mean_unified"]:.4f}  '
                   f'overnight_sep={on_sep}  '
                   f'daytime_sep={day_sep}'),
        'results': {'per_patient': results, 'summary': summary},
    }


# ---------------------------------------------------------------------------
# EXP-1099: Patient Difficulty Predictors
# ---------------------------------------------------------------------------

def exp_1099_difficulty_predictors(patients, detail=False):
    """Identify what makes a patient hard to predict.

    Computes patient-level statistics and correlates with R² score.
    """
    results = []

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        df = p['df']
        n = min(len(glucose), len(physics))
        if n < WINDOW + HORIZON + 50:
            continue
        glucose, physics = glucose[:n], physics[:n]

        X, y = make_windows(glucose, physics)
        if len(X) < 200:
            continue

        Xf = X.reshape(len(X), -1)
        X_tr, X_vl, y_tr, y_vl = split_data(Xf, y)

        gb = GradientBoostingRegressor(
            n_estimators=200, max_depth=4, learning_rate=0.05, random_state=42)
        gb.fit(X_tr, y_tr)
        r2 = compute_r2(y_vl, gb.predict(X_vl))

        # Patient-level glucose statistics (in mg/dL)
        g_valid = glucose[~np.isnan(glucose)]
        g_mean = float(np.mean(g_valid)) if len(g_valid) > 0 else 0.0
        g_std = float(np.std(g_valid)) if len(g_valid) > 0 else 0.0
        g_cv = g_std / g_mean if g_mean > 0 else 0.0
        tir = float(np.mean((g_valid >= 70) & (g_valid <= 180))) \
            if len(g_valid) > 0 else 0.0
        pct_missing = float(np.mean(np.isnan(glucose)))

        # Treatment frequency (approximate from PK channels)
        pk = p['pk']
        if pk is not None and len(pk) > 0:
            # insulin_net channel (col 1): nonzero = bolus/temp activity
            insulin_active = float(np.mean(np.abs(pk[:, 1]) > 0.01))
            # carb_rate channel (col 3): nonzero = meals
            carb_active = float(np.mean(np.abs(pk[:, 3]) > 0.01))
        else:
            insulin_active = 0.0
            carb_active = 0.0

        res = {
            'patient': p['name'],
            'r2': round(r2, 4),
            'glucose_mean': round(g_mean, 1),
            'glucose_std': round(g_std, 1),
            'glucose_cv': round(g_cv, 3),
            'time_in_range': round(tir, 3),
            'pct_missing': round(pct_missing, 3),
            'insulin_activity_pct': round(insulin_active, 3),
            'carb_activity_pct': round(carb_active, 3),
            'n_samples': len(X),
            'n_data_points': n,
        }
        results.append(res)
        if detail:
            print(f"    {p['name']}: R²={r2:.4f} mean={g_mean:.0f} "
                  f"std={g_std:.0f} CV={g_cv:.2f} TIR={tir:.2f} "
                  f"missing={pct_missing:.2f}")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    # Correlate patient characteristics with R²
    r2_vals = np.array([r['r2'] for r in results])
    correlations = {}
    stat_keys = ['glucose_mean', 'glucose_std', 'glucose_cv',
                 'time_in_range', 'pct_missing', 'insulin_activity_pct',
                 'carb_activity_pct']
    for key in stat_keys:
        vals = np.array([r[key] for r in results])
        if np.std(vals) > 0 and np.std(r2_vals) > 0:
            corr = float(np.corrcoef(vals, r2_vals)[0, 1])
            correlations[key] = round(corr, 3)
        else:
            correlations[key] = 0.0

    # Sort by absolute correlation
    top_predictors = sorted(correlations.items(),
                            key=lambda x: abs(x[1]), reverse=True)

    summary = {
        'correlations_with_r2': correlations,
        'top_predictors': [{'feature': k, 'correlation': v}
                           for k, v in top_predictors[:3]],
        'mean_r2': round(float(np.mean(r2_vals)), 4),
        'r2_range': [round(float(np.min(r2_vals)), 4),
                     round(float(np.max(r2_vals)), 4)],
        'n_patients': len(results),
    }

    if detail:
        print("\n  R² correlations with patient characteristics:")
        for feat, corr in top_predictors:
            print(f"    {feat:25s}: r={corr:+.3f}")

    top_feat = top_predictors[0][0] if top_predictors else 'N/A'
    top_corr = top_predictors[0][1] if top_predictors else 0.0
    return {
        'status': 'pass',
        'detail': (f'top predictor: {top_feat} (r={top_corr:+.3f}), '
                   f'mean R²={summary["mean_r2"]:.4f}, '
                   f'range=[{summary["r2_range"][0]:.4f}, '
                   f'{summary["r2_range"][1]:.4f}]'),
        'results': {'per_patient': results, 'summary': summary},
    }


# ---------------------------------------------------------------------------
# EXP-1100: Campaign Grand Summary
# ---------------------------------------------------------------------------

def exp_1100_grand_summary(patients, detail=False):
    """Definitive benchmark combining all successful techniques.

    GB with grand features under 3-fold block CV, Clarke Error Grid,
    per-patient best model selection (Ridge or GB per-fold).
    Compare to EXP-1080 benchmark (R²=0.532).
    """
    results = []

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        n = min(len(glucose), len(physics))
        if n < WINDOW + HORIZON + 50:
            continue
        glucose, physics = glucose[:n], physics[:n]

        X, y = build_grand_features(glucose, physics)
        if len(X) < 200:
            continue

        def gb_fn():
            return GradientBoostingRegressor(
                n_estimators=200, max_depth=4, learning_rate=0.05,
                random_state=42)

        def ridge_fn():
            return Ridge(alpha=1.0)

        # 3-fold block CV for both models
        gb_mean, gb_folds = block_cv_score(X, y, gb_fn, n_folds=3)
        ridge_mean, ridge_folds = block_cv_score(X, y, ridge_fn, n_folds=3)

        # Per-fold best selection
        best_folds = []
        fold_size = len(X) // 3
        for fold in range(3):
            val_start = fold * fold_size
            val_end = val_start + fold_size if fold < 2 else len(X)
            mask = np.ones(len(X), dtype=bool)
            mask[val_start:val_end] = False
            X_tr, y_tr = X[mask], y[mask]
            X_vl, y_vl = X[~mask], y[~mask]

            gb_m = gb_fn()
            gb_m.fit(X_tr, y_tr)
            r2_gb = compute_r2(y_vl, gb_m.predict(X_vl))

            ridge_m = ridge_fn()
            ridge_m.fit(X_tr, y_tr)
            r2_ridge = compute_r2(y_vl, ridge_m.predict(X_vl))

            best_folds.append(max(r2_gb, r2_ridge))

        best_mean = float(np.mean(best_folds))

        # Clarke Error Grid (single split for Clarke)
        X_tr, X_vl, y_tr, y_vl = split_data(X, y)
        gb_final = gb_fn()
        gb_final.fit(X_tr, y_tr)
        pred = gb_final.predict(X_vl)

        mae = compute_mae(y_vl, pred)
        r2_split = compute_r2(y_vl, pred)

        y_true_mgdl = y_vl * GLUCOSE_SCALE
        y_pred_mgdl = pred * GLUCOSE_SCALE
        clarke = clarke_error_grid(y_true_mgdl, y_pred_mgdl)

        res = {
            'patient': p['name'],
            'gb_cv_r2': round(gb_mean, 4),
            'ridge_cv_r2': round(ridge_mean, 4),
            'best_selection_cv_r2': round(best_mean, 4),
            'gb_split_r2': round(r2_split, 4),
            'mae_normalized': round(mae, 4),
            'mae_mgdl': round(mae * GLUCOSE_SCALE, 1),
            'clarke_A': round(clarke['A'], 3),
            'clarke_AB': round(clarke['A'] + clarke['B'], 3),
            'clarke_zones': {k: round(v, 4) for k, v in clarke.items()},
            'n_samples': len(X),
        }
        results.append(res)
        if detail:
            print(f"    {p['name']}: GB_CV={gb_mean:.4f} "
                  f"Ridge_CV={ridge_mean:.4f} Best={best_mean:.4f} "
                  f"MAE={mae * GLUCOSE_SCALE:.1f}mg/dL "
                  f"Clarke_A={clarke['A']:.1%} "
                  f"A+B={clarke['A'] + clarke['B']:.1%}")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    summary = {
        'mean_gb_cv_r2': round(np.mean(
            [r['gb_cv_r2'] for r in results]), 4),
        'mean_ridge_cv_r2': round(np.mean(
            [r['ridge_cv_r2'] for r in results]), 4),
        'mean_best_selection_r2': round(np.mean(
            [r['best_selection_cv_r2'] for r in results]), 4),
        'mean_mae_mgdl': round(np.mean(
            [r['mae_mgdl'] for r in results]), 1),
        'mean_clarke_A': round(np.mean(
            [r['clarke_A'] for r in results]), 3),
        'mean_clarke_AB': round(np.mean(
            [r['clarke_AB'] for r in results]), 3),
        'vs_exp1080_benchmark': 0.532,
        'n_patients': len(results),
    }

    improvement = summary['mean_gb_cv_r2'] - 0.532

    return {
        'status': 'pass',
        'detail': (f'GB_CV={summary["mean_gb_cv_r2"]:.4f} '
                   f'(vs EXP-1080: {improvement:+.4f}), '
                   f'Best={summary["mean_best_selection_r2"]:.4f}, '
                   f'MAE={summary["mean_mae_mgdl"]:.1f}mg/dL, '
                   f'Clarke A={summary["mean_clarke_A"]:.1%} '
                   f'A+B={summary["mean_clarke_AB"]:.1%}'),
        'results': {'per_patient': results, 'summary': summary},
    }


# ---------------------------------------------------------------------------
# Experiment registry and main
# ---------------------------------------------------------------------------

EXPERIMENTS = [
    ('EXP-1091', 'GB Grand Features Block CV', exp_1091_gb_grand_cv),
    ('EXP-1092', 'GB + CNN Residual on Grand Features', exp_1092_gb_cnn_residual),
    ('EXP-1093', 'Per-Patient DIA Optimization', exp_1093_dia_optimization),
    ('EXP-1094', 'Per-Patient ISF Scaling', exp_1094_isf_scaling),
    ('EXP-1095', 'Multi-Scale Context (6h+12h+24h)', exp_1095_multiscale_context),
    ('EXP-1096', 'Two-Resolution Model', exp_1096_two_resolution),
    ('EXP-1097', 'Residual Analysis by Context', exp_1097_residual_analysis),
    ('EXP-1098', 'Overnight vs Daytime Models', exp_1098_overnight_daytime),
    ('EXP-1099', 'Patient Difficulty Predictors', exp_1099_difficulty_predictors),
    ('EXP-1100', 'Campaign Grand Summary', exp_1100_grand_summary),
]


def main():
    parser = argparse.ArgumentParser(
        description='EXP-1091-1100: GB Validation, PK Personalization, '
                    'and Residual Analysis')
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--max-patients', type=int, default=11)
    parser.add_argument('--experiment', type=str,
                        help='Run only this experiment (e.g. EXP-1091)')
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
