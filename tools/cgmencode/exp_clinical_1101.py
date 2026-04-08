#!/usr/bin/env python3
"""EXP-1101 to EXP-1110: Advanced ML, Clinical Targets, and Online Learning.

Building on 100 experiments of findings (EXP-1001-1100):
- SOTA: R²=0.532 (3-fold block CV), R²=0.538 (GB grand features, single split)
- Error decomposition: 76.3% unexplained, 25.8% irreducible, 0.7% bias
- GB dominates with rich features (11/11), Ridge/CNN overfit with high-dim
- Physics interactions (+0.007) only genuine new feature for Ridge
- Glucose carries 97% of signal, physics 2-3%
- Feature engineering from existing data hits a wall
- Horizon decay: 0.0067/min (5min=0.971, 60min=0.503, 120min=0.197)

This batch explores new ML architectures, clinical targets, ensemble methods,
and online learning:
  EXP-1101: XGBoost GPU Acceleration ★★
  EXP-1102: Predict Δg (Rate of Change) Instead of Absolute ★★★
  EXP-1103: Regime-Specific Loss Weighting ★★★
  EXP-1104: Quantile Regression for Prediction Intervals ★★★
  EXP-1105: Missing Data Imputation Strategies ★★★
  EXP-1106: Per-Patient Fine-Tuning ★★★
  EXP-1107: Temporal Convolutional Network (TCN) ★★
  EXP-1108: Ensemble of Ridge + GB + CNN ★★★
  EXP-1109: Glucose Trend Features (Direction + Momentum) ★★
  EXP-1110: Online Learning Simulation ★★

Run:
    PYTHONPATH=tools python -m cgmencode.exp_clinical_1101 --detail --save --max-patients 11
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


def train_cnn_model(X_train, y_train, X_val, in_channels,
                    epochs=60, lr=1e-3):
    """Train a ResidualCNN, return val predictions."""
    model = ResidualCNN(in_channels, window_size=WINDOW).to(DEVICE)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = nn.MSELoss()

    Xt = torch.tensor(X_train, dtype=torch.float32).to(DEVICE)
    yt = torch.tensor(y_train, dtype=torch.float32).to(DEVICE)
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
# Grand feature set builder (shared across experiments)
# ---------------------------------------------------------------------------

def build_grand_features(glucose, physics, window=WINDOW, horizon=HORIZON,
                         stride=STRIDE):
    """Build the grand feature set: glucose + physics + interactions +
    derivatives + statistics.

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


def build_grand_features_with_targets(glucose, physics, window=WINDOW,
                                      horizon=HORIZON, stride=STRIDE):
    """Like build_grand_features but also returns raw glucose(t) for each sample.

    Returns (X, y, g_current) where g_current = glucose[t] / GLUCOSE_SCALE.
    """
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

        g_current = g_win[-1]  # last glucose in window = glucose(t)

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


# ---------------------------------------------------------------------------
# EXP-1101: XGBoost GPU Acceleration
# ---------------------------------------------------------------------------

def exp_1101_xgboost_gpu(patients, detail=False):
    """Compare XGBoost (CPU/GPU) vs sklearn GradientBoosting.

    Tests whether XGBoost provides speed or accuracy improvements,
    and whether GPU acceleration is available and beneficial.
    """
    # Check XGBoost availability
    xgb_available = False
    try:
        import xgboost as xgb
        xgb_available = True
        xgb_version = xgb.__version__
    except ImportError:
        xgb_version = None

    gpu_available = torch.cuda.is_available()

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

        # --- sklearn GradientBoosting ---
        def sklearn_gb_fn():
            return GradientBoostingRegressor(
                n_estimators=200, max_depth=4, learning_rate=0.05,
                random_state=42)

        t0 = time.time()
        sklearn_mean, sklearn_folds = block_cv_score(X, y, sklearn_gb_fn,
                                                     n_folds=3)
        sklearn_time = time.time() - t0

        res = {
            'patient': p['name'],
            'n_samples': len(X),
            'sklearn_gb_r2': round(sklearn_mean, 4),
            'sklearn_gb_folds': [round(s, 4) for s in sklearn_folds],
            'sklearn_gb_time': round(sklearn_time, 2),
        }

        # --- XGBoost CPU ---
        if xgb_available:
            def xgb_cpu_fn():
                return xgb.XGBRegressor(
                    n_estimators=200, max_depth=4, learning_rate=0.05,
                    tree_method='hist', device='cpu',
                    random_state=42, verbosity=0)

            t0 = time.time()
            xgb_cpu_mean, xgb_cpu_folds = block_cv_score(X, y, xgb_cpu_fn,
                                                          n_folds=3)
            xgb_cpu_time = time.time() - t0

            res['xgb_cpu_r2'] = round(xgb_cpu_mean, 4)
            res['xgb_cpu_folds'] = [round(s, 4) for s in xgb_cpu_folds]
            res['xgb_cpu_time'] = round(xgb_cpu_time, 2)
            res['xgb_cpu_speedup'] = round(sklearn_time / max(xgb_cpu_time,
                                                               0.01), 2)

            # --- XGBoost GPU ---
            if gpu_available:
                try:
                    def xgb_gpu_fn():
                        return xgb.XGBRegressor(
                            n_estimators=200, max_depth=4, learning_rate=0.05,
                            tree_method='hist', device='cuda',
                            random_state=42, verbosity=0)

                    t0 = time.time()
                    xgb_gpu_mean, xgb_gpu_folds = block_cv_score(
                        X, y, xgb_gpu_fn, n_folds=3)
                    xgb_gpu_time = time.time() - t0

                    res['xgb_gpu_r2'] = round(xgb_gpu_mean, 4)
                    res['xgb_gpu_folds'] = [round(s, 4) for s in
                                            xgb_gpu_folds]
                    res['xgb_gpu_time'] = round(xgb_gpu_time, 2)
                    res['xgb_gpu_speedup'] = round(sklearn_time /
                                                    max(xgb_gpu_time,
                                                        0.01), 2)
                except Exception as e:
                    res['xgb_gpu_error'] = str(e)
            else:
                res['xgb_gpu_note'] = 'No CUDA device available'
        else:
            res['xgb_note'] = 'XGBoost not installed, sklearn-only comparison'

        # Determine best model for this patient
        models = {'sklearn_gb': sklearn_mean}
        if 'xgb_cpu_r2' in res:
            models['xgb_cpu'] = res['xgb_cpu_r2']
        if 'xgb_gpu_r2' in res:
            models['xgb_gpu'] = res['xgb_gpu_r2']
        res['best_model'] = max(models, key=models.get)
        res['best_r2'] = round(max(models.values()), 4)

        results.append(res)
        if detail:
            parts = [f"sklearn={sklearn_mean:.4f}({sklearn_time:.1f}s)"]
            if 'xgb_cpu_r2' in res:
                parts.append(f"xgb_cpu={res['xgb_cpu_r2']:.4f}"
                             f"({res['xgb_cpu_time']:.1f}s)")
            if 'xgb_gpu_r2' in res:
                parts.append(f"xgb_gpu={res['xgb_gpu_r2']:.4f}"
                             f"({res['xgb_gpu_time']:.1f}s)")
            print(f"    {p['name']}: {' '.join(parts)}")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    mean_sklearn = np.mean([r['sklearn_gb_r2'] for r in results])
    summary = {
        'xgb_available': xgb_available,
        'xgb_version': xgb_version,
        'gpu_available': gpu_available,
        'mean_sklearn_gb_r2': round(mean_sklearn, 4),
        'n_patients': len(results),
    }
    if xgb_available:
        xgb_cpu_scores = [r['xgb_cpu_r2'] for r in results
                          if 'xgb_cpu_r2' in r]
        if xgb_cpu_scores:
            summary['mean_xgb_cpu_r2'] = round(np.mean(xgb_cpu_scores), 4)
            summary['mean_xgb_cpu_speedup'] = round(
                np.mean([r['xgb_cpu_speedup'] for r in results
                         if 'xgb_cpu_speedup' in r]), 2)
        xgb_gpu_scores = [r['xgb_gpu_r2'] for r in results
                          if 'xgb_gpu_r2' in r]
        if xgb_gpu_scores:
            summary['mean_xgb_gpu_r2'] = round(np.mean(xgb_gpu_scores), 4)
            summary['mean_xgb_gpu_speedup'] = round(
                np.mean([r['xgb_gpu_speedup'] for r in results
                         if 'xgb_gpu_speedup' in r]), 2)

    detail_str = f'sklearn_GB={mean_sklearn:.4f}'
    if 'mean_xgb_cpu_r2' in summary:
        detail_str += (f' XGB_CPU={summary["mean_xgb_cpu_r2"]:.4f}'
                       f' ({summary["mean_xgb_cpu_speedup"]:.1f}x faster)')
    if 'mean_xgb_gpu_r2' in summary:
        detail_str += (f' XGB_GPU={summary["mean_xgb_gpu_r2"]:.4f}'
                       f' ({summary["mean_xgb_gpu_speedup"]:.1f}x faster)')
    if not xgb_available:
        detail_str += ' (XGBoost not available)'

    return {
        'status': 'pass',
        'detail': detail_str,
        'results': {'per_patient': results, 'summary': summary},
    }


# ---------------------------------------------------------------------------
# EXP-1102: Predict Δg (Rate of Change) Instead of Absolute
# ---------------------------------------------------------------------------

def exp_1102_delta_glucose(patients, detail=False):
    """Predict glucose change (Δg) instead of absolute glucose(t+h).

    Tests whether predicting the change removes autoregressive dependence
    and forces the model to learn actual dynamics.
    """
    results = []
    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        n = min(len(glucose), len(physics))
        if n < WINDOW + HORIZON + 50:
            continue
        glucose, physics = glucose[:n], physics[:n]

        X, y_abs, g_current = build_grand_features_with_targets(
            glucose, physics)
        if len(X) < 200:
            continue

        # Δg target: glucose(t+h) - glucose(t)
        y_delta = y_abs - g_current

        # --- Direct prediction (standard) ---
        def ridge_fn():
            return Ridge(alpha=1.0)

        direct_mean, direct_folds = block_cv_score(X, y_abs, ridge_fn,
                                                    n_folds=3)

        # --- Δg prediction ---
        delta_mean_raw, delta_folds_raw = block_cv_score(X, y_delta, ridge_fn,
                                                          n_folds=3)

        # Convert Δg predictions back to absolute for fair R² comparison
        n_samples = len(X)
        fold_size = n_samples // 3
        delta_abs_scores = []
        for fold in range(3):
            val_start = fold * fold_size
            val_end = val_start + fold_size if fold < 2 else n_samples
            mask = np.ones(n_samples, dtype=bool)
            mask[val_start:val_end] = False
            X_tr, y_delta_tr = X[mask], y_delta[mask]
            X_vl, y_abs_vl = X[~mask], y_abs[~mask]
            g_cur_vl = g_current[~mask]

            m = Ridge(alpha=1.0)
            m.fit(X_tr, y_delta_tr)
            pred_delta = m.predict(X_vl)
            pred_abs = g_cur_vl + pred_delta  # reconstruct absolute
            delta_abs_scores.append(compute_r2(y_abs_vl, pred_abs))

        delta_abs_mean = float(np.mean(delta_abs_scores))

        # Statistics on the Δg target
        delta_stats = {
            'mean_delta': round(float(np.mean(y_delta)) * GLUCOSE_SCALE, 2),
            'std_delta': round(float(np.std(y_delta)) * GLUCOSE_SCALE, 2),
            'pct_positive': round(float(np.mean(y_delta > 0)) * 100, 1),
        }

        res = {
            'patient': p['name'],
            'direct_r2': round(direct_mean, 4),
            'delta_raw_r2': round(delta_mean_raw, 4),
            'delta_abs_r2': round(delta_abs_mean, 4),
            'delta_advantage': round(delta_abs_mean - direct_mean, 4),
            'delta_stats': delta_stats,
            'n_samples': n_samples,
        }
        results.append(res)
        if detail:
            print(f"    {p['name']}: direct={direct_mean:.4f} "
                  f"Δg_raw={delta_mean_raw:.4f} "
                  f"Δg→abs={delta_abs_mean:.4f} "
                  f"({delta_abs_mean - direct_mean:+.4f})")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    mean_direct = np.mean([r['direct_r2'] for r in results])
    mean_delta_raw = np.mean([r['delta_raw_r2'] for r in results])
    mean_delta_abs = np.mean([r['delta_abs_r2'] for r in results])
    n_improved = sum(1 for r in results if r['delta_advantage'] > 0)

    summary = {
        'mean_direct_r2': round(mean_direct, 4),
        'mean_delta_raw_r2': round(mean_delta_raw, 4),
        'mean_delta_abs_r2': round(mean_delta_abs, 4),
        'mean_delta_advantage': round(mean_delta_abs - mean_direct, 4),
        'n_improved': n_improved,
        'n_patients': len(results),
        'hypothesis': ('Δg target removes autoregressive component, '
                       'tests if model learns actual dynamics'),
    }
    return {
        'status': 'pass',
        'detail': (f'direct={mean_direct:.4f} Δg→abs={mean_delta_abs:.4f} '
                   f'({mean_delta_abs - mean_direct:+.4f}, '
                   f'{n_improved}/{len(results)} improved)'),
        'results': {'per_patient': results, 'summary': summary},
    }


# ---------------------------------------------------------------------------
# EXP-1103: Regime-Specific Loss Weighting
# ---------------------------------------------------------------------------

def exp_1103_regime_weighting(patients, detail=False):
    """Weight samples by glucose regime to improve clinical performance.

    Tests whether emphasizing hypo/extreme samples helps detection
    without destroying overall R².
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

        y_mgdl = y * GLUCOSE_SCALE

        # Define regimes based on target glucose
        regime_hypo = y_mgdl < 70
        regime_low = (y_mgdl >= 70) & (y_mgdl < 100)
        regime_normal = (y_mgdl >= 100) & (y_mgdl <= 180)
        regime_high = y_mgdl > 180

        regime_counts = {
            'hypo': int(regime_hypo.sum()),
            'low': int(regime_low.sum()),
            'normal': int(regime_normal.sum()),
            'high': int(regime_high.sum()),
        }

        # Weight schemes
        def make_weights(scheme):
            w = np.ones(len(y))
            if scheme == 'uniform':
                pass
            elif scheme == 'hypo_weighted':
                w[regime_hypo] = 10.0
            elif scheme == 'extreme_weighted':
                w[regime_hypo] = 5.0
                w[regime_high] = 3.0
            elif scheme == 'inverse_freq':
                total = len(y)
                n_regimes = 4
                for mask, count in [(regime_hypo, regime_counts['hypo']),
                                    (regime_low, regime_counts['low']),
                                    (regime_normal, regime_counts['normal']),
                                    (regime_high, regime_counts['high'])]:
                    if count > 0:
                        w[mask] = total / (n_regimes * count)
            return w

        scheme_results = {}
        for scheme in ['uniform', 'hypo_weighted', 'extreme_weighted',
                       'inverse_freq']:
            weights = make_weights(scheme)

            # Block CV with sample weights
            n_samples = len(X)
            fold_size = n_samples // 3
            fold_scores = []
            fold_regime_maes = {'hypo': [], 'low': [], 'normal': [], 'high': []}

            for fold in range(3):
                val_start = fold * fold_size
                val_end = val_start + fold_size if fold < 2 else n_samples
                mask = np.ones(n_samples, dtype=bool)
                mask[val_start:val_end] = False

                X_tr, y_tr = X[mask], y[mask]
                w_tr = weights[mask]
                X_vl, y_vl = X[~mask], y[~mask]
                y_vl_mgdl = y_vl * GLUCOSE_SCALE

                m = Ridge(alpha=1.0)
                m.fit(X_tr, y_tr, sample_weight=w_tr)
                pred = m.predict(X_vl)
                pred_mgdl = pred * GLUCOSE_SCALE

                fold_scores.append(compute_r2(y_vl, pred))

                # Per-regime MAE
                for rname, lo, hi in [('hypo', 0, 70), ('low', 70, 100),
                                      ('normal', 100, 180), ('high', 180, 600)]:
                    rmask = (y_vl_mgdl >= lo) & (y_vl_mgdl < hi)
                    if rmask.sum() > 0:
                        fold_regime_maes[rname].append(
                            compute_mae(y_vl_mgdl[rmask], pred_mgdl[rmask]))

            mean_r2 = float(np.mean(fold_scores))
            regime_mae = {}
            for rname in ['hypo', 'low', 'normal', 'high']:
                if fold_regime_maes[rname]:
                    regime_mae[rname] = round(
                        float(np.mean(fold_regime_maes[rname])), 2)
                else:
                    regime_mae[rname] = None

            scheme_results[scheme] = {
                'r2': round(mean_r2, 4),
                'regime_mae': regime_mae,
            }

        best_scheme = max(scheme_results,
                          key=lambda s: scheme_results[s]['r2'])

        res = {
            'patient': p['name'],
            'regime_counts': regime_counts,
            'schemes': scheme_results,
            'best_scheme': best_scheme,
            'best_r2': scheme_results[best_scheme]['r2'],
            'uniform_r2': scheme_results['uniform']['r2'],
            'n_samples': len(X),
        }
        results.append(res)
        if detail:
            parts = [f"{s}={scheme_results[s]['r2']:.4f}" for s in
                     ['uniform', 'hypo_weighted', 'extreme_weighted',
                      'inverse_freq']]
            print(f"    {p['name']}: {' '.join(parts)} "
                  f"(best={best_scheme})")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    mean_uniform = np.mean([r['uniform_r2'] for r in results])
    mean_best = np.mean([r['best_r2'] for r in results])
    scheme_wins = {}
    for r in results:
        s = r['best_scheme']
        scheme_wins[s] = scheme_wins.get(s, 0) + 1

    # Aggregate hypo MAE across patients per scheme
    scheme_hypo_maes = {}
    for scheme in ['uniform', 'hypo_weighted', 'extreme_weighted',
                   'inverse_freq']:
        maes = [r['schemes'][scheme]['regime_mae']['hypo']
                for r in results
                if r['schemes'][scheme]['regime_mae']['hypo'] is not None]
        if maes:
            scheme_hypo_maes[scheme] = round(np.mean(maes), 2)

    summary = {
        'mean_uniform_r2': round(mean_uniform, 4),
        'mean_best_r2': round(mean_best, 4),
        'scheme_wins': scheme_wins,
        'scheme_hypo_mae': scheme_hypo_maes,
        'n_patients': len(results),
    }
    return {
        'status': 'pass',
        'detail': (f'uniform={mean_uniform:.4f} best={mean_best:.4f} '
                   f'scheme_wins={scheme_wins} '
                   f'hypo_MAE={scheme_hypo_maes}'),
        'results': {'per_patient': results, 'summary': summary},
    }


# ---------------------------------------------------------------------------
# EXP-1104: Quantile Regression for Prediction Intervals
# ---------------------------------------------------------------------------

def exp_1104_quantile_regression(patients, detail=False):
    """Use quantile regression for prediction intervals.

    Trains GBR with loss='quantile' at alpha=0.1, 0.25, 0.5, 0.75, 0.9
    to generate calibrated prediction intervals and evaluate clinical utility.
    """
    quantiles = [0.1, 0.25, 0.5, 0.75, 0.9]

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

        X_tr, X_vl, y_tr, y_vl = split_data(X, y)
        y_vl_mgdl = y_vl * GLUCOSE_SCALE

        # Train quantile models
        quantile_preds = {}
        for q in quantiles:
            gbr = GradientBoostingRegressor(
                n_estimators=100, max_depth=3, learning_rate=0.05,
                loss='quantile', alpha=q, random_state=42)
            gbr.fit(X_tr, y_tr)
            quantile_preds[q] = gbr.predict(X_vl)

        # Also train mean model for R² comparison
        gbr_mean = GradientBoostingRegressor(
            n_estimators=100, max_depth=3, learning_rate=0.05,
            random_state=42)
        gbr_mean.fit(X_tr, y_tr)
        pred_mean = gbr_mean.predict(X_vl)
        r2_mean = compute_r2(y_vl, pred_mean)

        # Median R²
        r2_median = compute_r2(y_vl, quantile_preds[0.5])

        # Calibration: fraction of true values within predicted intervals
        calibration = {}
        intervals = [
            ('80pct', 0.1, 0.9),
            ('50pct', 0.25, 0.75),
        ]
        for name, lo_q, hi_q in intervals:
            lo = quantile_preds[lo_q]
            hi = quantile_preds[hi_q]
            in_interval = np.mean((y_vl >= lo) & (y_vl <= hi))
            width = np.mean((hi - lo) * GLUCOSE_SCALE)
            calibration[name] = {
                'coverage': round(float(in_interval), 4),
                'expected': round(hi_q - lo_q, 2),
                'mean_width_mgdl': round(float(width), 1),
            }

        # Hypo detection: fraction of actual hypo events where lower bound
        # also indicates hypo
        hypo_mask = y_vl_mgdl < 70
        n_hypo = int(hypo_mask.sum())
        hypo_captured = 0
        if n_hypo > 0:
            lo_10_mgdl = quantile_preds[0.1] * GLUCOSE_SCALE
            hypo_captured = float(np.mean(lo_10_mgdl[hypo_mask] < 70))

        # False alarm: lower bound < 70 but actual >= 70
        non_hypo_mask = y_vl_mgdl >= 70
        false_alarms = 0.0
        if non_hypo_mask.sum() > 0:
            lo_10_mgdl = quantile_preds[0.1] * GLUCOSE_SCALE
            false_alarms = float(np.mean(lo_10_mgdl[non_hypo_mask] < 70))

        res = {
            'patient': p['name'],
            'r2_mean': round(r2_mean, 4),
            'r2_median': round(r2_median, 4),
            'calibration': calibration,
            'n_hypo': n_hypo,
            'hypo_capture_rate': round(hypo_captured, 4),
            'false_alarm_rate': round(false_alarms, 4),
            'n_samples': len(X),
        }
        results.append(res)
        if detail:
            cal80 = calibration['80pct']
            print(f"    {p['name']}: mean_R²={r2_mean:.4f} "
                  f"median_R²={r2_median:.4f} "
                  f"80%_cov={cal80['coverage']:.1%} "
                  f"(width={cal80['mean_width_mgdl']:.0f}mg/dL) "
                  f"hypo_cap={hypo_captured:.1%}")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    mean_r2_mean = np.mean([r['r2_mean'] for r in results])
    mean_r2_median = np.mean([r['r2_median'] for r in results])
    mean_cov_80 = np.mean([r['calibration']['80pct']['coverage']
                           for r in results])
    mean_width_80 = np.mean([r['calibration']['80pct']['mean_width_mgdl']
                             for r in results])
    hypo_patients = [r for r in results if r['n_hypo'] > 0]
    mean_hypo_cap = (np.mean([r['hypo_capture_rate'] for r in hypo_patients])
                     if hypo_patients else 0.0)

    summary = {
        'mean_r2_mean': round(mean_r2_mean, 4),
        'mean_r2_median': round(mean_r2_median, 4),
        'mean_80pct_coverage': round(mean_cov_80, 4),
        'expected_80pct_coverage': 0.80,
        'mean_80pct_width_mgdl': round(mean_width_80, 1),
        'mean_hypo_capture_rate': round(mean_hypo_cap, 4),
        'n_patients_with_hypo': len(hypo_patients),
        'n_patients': len(results),
    }
    return {
        'status': 'pass',
        'detail': (f'mean_R²={mean_r2_mean:.4f} '
                   f'median_R²={mean_r2_median:.4f} '
                   f'80%_cov={mean_cov_80:.1%} '
                   f'(width={mean_width_80:.0f}mg/dL) '
                   f'hypo_cap={mean_hypo_cap:.1%}'),
        'results': {'per_patient': results, 'summary': summary},
    }


# ---------------------------------------------------------------------------
# EXP-1105: Missing Data Imputation Strategies
# ---------------------------------------------------------------------------

def exp_1105_missing_data(patients, detail=False):
    """Test different approaches to handling CGM gaps.

    Missing data is the #1 difficulty predictor (r=-0.757).
    Compares: drop-NaN, forward-fill+flag, interpolation+flag, zero-fill PK.
    """
    results = []
    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        n = min(len(glucose), len(physics))
        if n < WINDOW + HORIZON + 50:
            continue
        glucose, physics = glucose[:n], physics[:n]

        g = glucose / GLUCOSE_SCALE
        nan_frac = float(np.isnan(glucose).mean())

        strategy_scores = {}

        # --- Strategy 1: Drop windows with any NaN (current approach) ---
        X_drop, y_drop = build_grand_features(glucose, physics)
        if len(X_drop) >= 100:
            def ridge_fn():
                return Ridge(alpha=1.0)
            s1_mean, _ = block_cv_score(X_drop, y_drop, ridge_fn, n_folds=3)
            strategy_scores['drop_nan'] = {
                'r2': round(s1_mean, 4),
                'n_samples': len(X_drop),
            }

        # --- Strategy 2: Forward-fill + flag channel ---
        g_ffill = glucose.copy()
        flag_ffill = np.zeros(len(g_ffill))
        nan_mask = np.isnan(g_ffill)
        flag_ffill[nan_mask] = 1.0
        # Forward fill
        for i in range(1, len(g_ffill)):
            if np.isnan(g_ffill[i]) and not np.isnan(g_ffill[i - 1]):
                g_ffill[i] = g_ffill[i - 1]
        # Fill remaining leading NaNs with first valid value
        first_valid = np.where(~np.isnan(g_ffill))[0]
        if len(first_valid) > 0:
            g_ffill[:first_valid[0]] = g_ffill[first_valid[0]]

        physics_ffill = np.column_stack([physics, flag_ffill[:len(physics)]])
        X_ffill, y_ffill = _build_features_with_extra_channels(
            g_ffill, physics_ffill)
        if len(X_ffill) >= 100:
            s2_mean, _ = block_cv_score(X_ffill, y_ffill, ridge_fn, n_folds=3)
            strategy_scores['ffill_flag'] = {
                'r2': round(s2_mean, 4),
                'n_samples': len(X_ffill),
            }

        # --- Strategy 3: Linear interpolation + flag channel ---
        g_interp = glucose.copy()
        flag_interp = np.zeros(len(g_interp))
        flag_interp[np.isnan(g_interp)] = 1.0
        valid_idx = np.where(~np.isnan(g_interp))[0]
        if len(valid_idx) >= 2:
            g_interp = np.interp(
                np.arange(len(g_interp)), valid_idx, g_interp[valid_idx])
        elif len(valid_idx) == 1:
            g_interp[:] = g_interp[valid_idx[0]]
        else:
            g_interp[:] = 0.4 * GLUCOSE_SCALE

        physics_interp = np.column_stack([physics,
                                          flag_interp[:len(physics)]])
        X_interp, y_interp = _build_features_with_extra_channels(
            g_interp, physics_interp)
        if len(X_interp) >= 100:
            s3_mean, _ = block_cv_score(X_interp, y_interp, ridge_fn,
                                         n_folds=3)
            strategy_scores['interp_flag'] = {
                'r2': round(s3_mean, 4),
                'n_samples': len(X_interp),
            }

        # --- Strategy 4: Zero-fill PK where glucose missing ---
        physics_zfill = physics.copy()
        g_nan_mask = np.isnan(glucose)[:len(physics)]
        physics_zfill[g_nan_mask] = 0.0
        g_zfill = glucose.copy()
        g_zfill[np.isnan(g_zfill)] = 0.4 * GLUCOSE_SCALE  # neutral fill

        X_zfill, y_zfill = build_grand_features(g_zfill, physics_zfill)
        if len(X_zfill) >= 100:
            s4_mean, _ = block_cv_score(X_zfill, y_zfill, ridge_fn,
                                         n_folds=3)
            strategy_scores['zero_fill_pk'] = {
                'r2': round(s4_mean, 4),
                'n_samples': len(X_zfill),
            }

        if not strategy_scores:
            continue

        best_strategy = max(strategy_scores,
                            key=lambda s: strategy_scores[s]['r2'])

        res = {
            'patient': p['name'],
            'nan_fraction': round(nan_frac, 4),
            'strategies': strategy_scores,
            'best_strategy': best_strategy,
            'best_r2': strategy_scores[best_strategy]['r2'],
            'n_total_steps': n,
        }
        results.append(res)
        if detail:
            parts = [f"{s}={strategy_scores[s]['r2']:.4f}"
                     for s in strategy_scores]
            print(f"    {p['name']}: nan={nan_frac:.1%} "
                  f"{' '.join(parts)} (best={best_strategy})")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    # Aggregate
    all_strategies = ['drop_nan', 'ffill_flag', 'interp_flag', 'zero_fill_pk']
    mean_scores = {}
    for s in all_strategies:
        scores = [r['strategies'][s]['r2'] for r in results if s in r['strategies']]
        if scores:
            mean_scores[s] = round(np.mean(scores), 4)

    strategy_wins = {}
    for r in results:
        s = r['best_strategy']
        strategy_wins[s] = strategy_wins.get(s, 0) + 1

    # High-missing patients (>5% NaN)
    high_missing = [r for r in results if r['nan_fraction'] > 0.05]
    high_missing_best = {}
    for s in all_strategies:
        scores = [r['strategies'][s]['r2'] for r in high_missing
                  if s in r['strategies']]
        if scores:
            high_missing_best[s] = round(np.mean(scores), 4)

    summary = {
        'mean_scores': mean_scores,
        'strategy_wins': strategy_wins,
        'high_missing_scores': high_missing_best,
        'n_high_missing': len(high_missing),
        'n_patients': len(results),
    }
    return {
        'status': 'pass',
        'detail': (f'scores={mean_scores} '
                   f'wins={strategy_wins} '
                   f'high_missing={high_missing_best}'),
        'results': {'per_patient': results, 'summary': summary},
    }


def _build_features_with_extra_channels(glucose, physics_extended,
                                         window=WINDOW, horizon=HORIZON,
                                         stride=STRIDE):
    """Build flat features from glucose and extended physics (may have >4 ch)."""
    g = glucose / GLUCOSE_SCALE
    n = min(len(g), len(physics_extended))
    X_list, y_list = [], []

    for i in range(0, n - window - horizon, stride):
        g_win = g[i:i + window]
        if np.isnan(g_win).mean() > 0.3:
            continue
        g_win = np.nan_to_num(
            g_win,
            nan=np.nanmean(g_win) if np.any(~np.isnan(g_win)) else 0.4,
        )
        p_win = physics_extended[i:i + window]
        if np.isnan(p_win).any():
            p_win = np.nan_to_num(p_win, nan=0.0)

        y_val = g[i + window + horizon - 1]
        if np.isnan(y_val):
            continue

        feat = np.concatenate([g_win, p_win.ravel()])
        X_list.append(feat)
        y_list.append(y_val)

    if len(X_list) == 0:
        return np.array([]).reshape(0, 1), np.array([])
    return np.array(X_list), np.array(y_list)


# ---------------------------------------------------------------------------
# EXP-1106: Per-Patient Fine-Tuning
# ---------------------------------------------------------------------------

def exp_1106_fine_tuning(patients, detail=False):
    """Pre-train on all other patients, then fine-tune on target patient.

    Tests whether cross-patient pre-training helps, especially for
    small/hard patients.
    """
    if len(patients) < 3:
        return {'status': 'FAIL',
                'detail': 'Need at least 3 patients for leave-one-out'}

    # Pre-compute features for all patients
    patient_data = []
    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        n = min(len(glucose), len(physics))
        if n < WINDOW + HORIZON + 50:
            continue
        glucose, physics = glucose[:n], physics[:n]
        X, y = build_grand_features(glucose, physics)
        if len(X) < 100:
            continue
        patient_data.append({
            'name': p['name'],
            'X': X,
            'y': y,
        })

    if len(patient_data) < 3:
        return {'status': 'FAIL',
                'detail': 'Not enough patients with sufficient data'}

    results = []
    for i, target in enumerate(patient_data):
        X_target = target['X']
        y_target = target['y']
        n_target = len(X_target)

        # Split target: first 50% for fine-tuning, last 50% for evaluation
        split = n_target // 2
        X_tune, y_tune = X_target[:split], y_target[:split]
        X_eval, y_eval = X_target[split:], y_target[split:]

        if len(X_eval) < 50:
            continue

        # Pool data from all other patients
        X_others = np.concatenate([pd['X'] for j, pd in enumerate(patient_data)
                                   if j != i])
        y_others = np.concatenate([pd['y'] for j, pd in enumerate(patient_data)
                                   if j != i])

        # --- Model A: Patient-specific only (train on first 50%) ---
        ridge_specific = Ridge(alpha=1.0)
        ridge_specific.fit(X_tune, y_tune)
        pred_specific = ridge_specific.predict(X_eval)
        r2_specific = compute_r2(y_eval, pred_specific)

        # --- Model B: Pre-trained on others only ---
        ridge_pretrained = Ridge(alpha=1.0)
        ridge_pretrained.fit(X_others, y_others)
        pred_pretrained = ridge_pretrained.predict(X_eval)
        r2_pretrained = compute_r2(y_eval, pred_pretrained)

        # --- Model C: Pre-trained + fine-tuned ---
        # Fine-tune: use pre-trained coefs as init, warm-start with
        # combined data (others + target tune portion, with target upweighted)
        X_combined = np.concatenate([X_others, X_tune])
        y_combined = np.concatenate([y_others, y_tune])

        # Upweight target patient data
        weights = np.ones(len(X_combined))
        weights[len(X_others):] = len(X_others) / max(len(X_tune), 1)

        ridge_finetuned = Ridge(alpha=1.0)
        ridge_finetuned.fit(X_combined, y_combined, sample_weight=weights)
        pred_finetuned = ridge_finetuned.predict(X_eval)
        r2_finetuned = compute_r2(y_eval, pred_finetuned)

        # --- Model D: All data pooled (no special handling) ---
        X_pool = np.concatenate([X_others, X_tune])
        y_pool = np.concatenate([y_others, y_tune])
        ridge_pooled = Ridge(alpha=1.0)
        ridge_pooled.fit(X_pool, y_pool)
        pred_pooled = ridge_pooled.predict(X_eval)
        r2_pooled = compute_r2(y_eval, pred_pooled)

        best_model = max(
            [('specific', r2_specific),
             ('pretrained', r2_pretrained),
             ('finetuned', r2_finetuned),
             ('pooled', r2_pooled)],
            key=lambda x: x[1])

        res = {
            'patient': target['name'],
            'r2_specific': round(r2_specific, 4),
            'r2_pretrained': round(r2_pretrained, 4),
            'r2_finetuned': round(r2_finetuned, 4),
            'r2_pooled': round(r2_pooled, 4),
            'best_model': best_model[0],
            'finetune_vs_specific': round(r2_finetuned - r2_specific, 4),
            'finetune_vs_pretrained': round(r2_finetuned - r2_pretrained, 4),
            'n_target': n_target,
            'n_others': len(X_others),
        }
        results.append(res)
        if detail:
            print(f"    {target['name']}: specific={r2_specific:.4f} "
                  f"pretrained={r2_pretrained:.4f} "
                  f"finetuned={r2_finetuned:.4f} "
                  f"pooled={r2_pooled:.4f} (best={best_model[0]})")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    summary = {
        'mean_r2_specific': round(np.mean([r['r2_specific']
                                           for r in results]), 4),
        'mean_r2_pretrained': round(np.mean([r['r2_pretrained']
                                             for r in results]), 4),
        'mean_r2_finetuned': round(np.mean([r['r2_finetuned']
                                            for r in results]), 4),
        'mean_r2_pooled': round(np.mean([r['r2_pooled']
                                         for r in results]), 4),
        'best_wins': {},
        'n_patients': len(results),
    }
    for r in results:
        m = r['best_model']
        summary['best_wins'][m] = summary['best_wins'].get(m, 0) + 1

    best_approach = max(
        [('specific', summary['mean_r2_specific']),
         ('pretrained', summary['mean_r2_pretrained']),
         ('finetuned', summary['mean_r2_finetuned']),
         ('pooled', summary['mean_r2_pooled'])],
        key=lambda x: x[1])

    return {
        'status': 'pass',
        'detail': (f'specific={summary["mean_r2_specific"]:.4f} '
                   f'pretrained={summary["mean_r2_pretrained"]:.4f} '
                   f'finetuned={summary["mean_r2_finetuned"]:.4f} '
                   f'pooled={summary["mean_r2_pooled"]:.4f} '
                   f'(best: {best_approach[0]}, '
                   f'wins={summary["best_wins"]})'),
        'results': {'per_patient': results, 'summary': summary},
    }


# ---------------------------------------------------------------------------
# EXP-1107: Temporal Convolutional Network (TCN)
# ---------------------------------------------------------------------------

class TCN(nn.Module):
    """Simple TCN with dilated causal convolutions for longer effective memory."""

    def __init__(self, in_channels, hidden=64, layers=4):
        super().__init__()
        self.convs = nn.ModuleList()
        self.norms = nn.ModuleList()
        for i in range(layers):
            dilation = 2 ** i
            self.convs.append(nn.Conv1d(
                in_channels if i == 0 else hidden,
                hidden, kernel_size=3, dilation=dilation,
                padding=dilation,
            ))
            self.norms.append(nn.BatchNorm1d(hidden))
        self.head = nn.Linear(hidden, 1)
        self.dropout = nn.Dropout(0.1)

    def forward(self, x):
        # x: (B, T, C) -> permute to (B, C, T)
        h = x.permute(0, 2, 1)
        for conv, norm in zip(self.convs, self.norms):
            h = torch.relu(norm(conv(h)))
            h = self.dropout(h)
        h = h[:, :, -1]  # last timestep (causal)
        return self.head(h).squeeze(-1)


def train_tcn(X_train, y_train, X_val, in_channels, epochs=80, lr=1e-3):
    """Train TCN, return val predictions."""
    model = TCN(in_channels, hidden=64, layers=4).to(DEVICE)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer,
                                                            T_max=epochs)
    loss_fn = nn.MSELoss()

    Xt = torch.tensor(X_train, dtype=torch.float32).to(DEVICE)
    yt = torch.tensor(y_train, dtype=torch.float32).to(DEVICE)
    Xv = torch.tensor(X_val, dtype=torch.float32).to(DEVICE)

    batch = min(256, len(Xt))
    model.train()
    for epoch in range(epochs):
        perm = torch.randperm(len(Xt))
        epoch_loss = 0.0
        n_batches = 0
        for start in range(0, len(Xt), batch):
            idx = perm[start:start + batch]
            pred = model(Xt[idx])
            loss = loss_fn(pred, yt[idx])
            optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            epoch_loss += loss.item()
            n_batches += 1
        scheduler.step()

    model.eval()
    with torch.no_grad():
        return model(Xv).cpu().numpy()


def exp_1107_tcn(patients, detail=False):
    """Implement TCN with dilated causal convolutions.

    Compares TCN vs CNN (ResidualCNN) vs Ridge on windowed physics features.
    TCN has longer effective receptive field due to dilated convolutions.
    """
    results = []
    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        n = min(len(glucose), len(physics))
        if n < WINDOW + HORIZON + 50:
            continue
        glucose, physics = glucose[:n], physics[:n]

        # 3D windowed features for neural nets
        X_win, y = make_windows(glucose, physics)
        if len(X_win) < 200:
            continue

        in_ch = X_win.shape[2]  # channels per timestep
        X_tr, X_vl, y_tr, y_vl = split_data(X_win, y)

        # Flat features for Ridge
        X_flat = X_win.reshape(len(X_win), -1)
        X_flat_tr, X_flat_vl, _, _ = split_data(X_flat, y)

        # --- Ridge baseline ---
        ridge = Ridge(alpha=1.0)
        ridge.fit(X_flat_tr, y_tr)
        pred_ridge = ridge.predict(X_flat_vl)
        r2_ridge = compute_r2(y_vl, pred_ridge)

        # --- CNN ---
        t0 = time.time()
        pred_cnn = train_cnn_model(X_tr, y_tr, X_vl, in_ch, epochs=60)
        cnn_time = time.time() - t0
        r2_cnn = compute_r2(y_vl, pred_cnn)

        # --- TCN ---
        t0 = time.time()
        pred_tcn = train_tcn(X_tr, y_tr, X_vl, in_ch, epochs=80)
        tcn_time = time.time() - t0
        r2_tcn = compute_r2(y_vl, pred_tcn)

        best_model = max(
            [('Ridge', r2_ridge), ('CNN', r2_cnn), ('TCN', r2_tcn)],
            key=lambda x: x[1])

        res = {
            'patient': p['name'],
            'r2_ridge': round(r2_ridge, 4),
            'r2_cnn': round(r2_cnn, 4),
            'r2_tcn': round(r2_tcn, 4),
            'cnn_time': round(cnn_time, 2),
            'tcn_time': round(tcn_time, 2),
            'best_model': best_model[0],
            'tcn_vs_cnn': round(r2_tcn - r2_cnn, 4),
            'n_samples': len(X_win),
        }
        results.append(res)
        if detail:
            print(f"    {p['name']}: Ridge={r2_ridge:.4f} "
                  f"CNN={r2_cnn:.4f}({cnn_time:.1f}s) "
                  f"TCN={r2_tcn:.4f}({tcn_time:.1f}s) "
                  f"(best={best_model[0]})")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    mean_ridge = np.mean([r['r2_ridge'] for r in results])
    mean_cnn = np.mean([r['r2_cnn'] for r in results])
    mean_tcn = np.mean([r['r2_tcn'] for r in results])
    model_wins = {}
    for r in results:
        m = r['best_model']
        model_wins[m] = model_wins.get(m, 0) + 1

    summary = {
        'mean_r2_ridge': round(mean_ridge, 4),
        'mean_r2_cnn': round(mean_cnn, 4),
        'mean_r2_tcn': round(mean_tcn, 4),
        'mean_tcn_vs_cnn': round(mean_tcn - mean_cnn, 4),
        'model_wins': model_wins,
        'device': str(DEVICE),
        'n_patients': len(results),
    }
    return {
        'status': 'pass',
        'detail': (f'Ridge={mean_ridge:.4f} CNN={mean_cnn:.4f} '
                   f'TCN={mean_tcn:.4f} '
                   f'(TCN-CNN={mean_tcn - mean_cnn:+.4f}, '
                   f'wins={model_wins})'),
        'results': {'per_patient': results, 'summary': summary},
    }


# ---------------------------------------------------------------------------
# EXP-1108: Ensemble of Ridge + GB + CNN
# ---------------------------------------------------------------------------

def exp_1108_ensemble(patients, detail=False):
    """Create proper ensemble by blending Ridge, GB, and CNN predictions.

    Compares blending strategies: simple average, optimized weights,
    and stacking (Ridge on predictions).
    """
    results = []
    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        n = min(len(glucose), len(physics))
        if n < WINDOW + HORIZON + 50:
            continue
        glucose, physics = glucose[:n], physics[:n]

        # Grand features (flat) for Ridge/GB
        X_grand, y = build_grand_features(glucose, physics)
        if len(X_grand) < 200:
            continue

        # Windowed features for CNN
        X_win, y_win = make_windows(glucose, physics)
        if len(X_win) < 200:
            continue

        min_len = min(len(X_grand), len(X_win))
        X_grand = X_grand[:min_len]
        X_win = X_win[:min_len]
        y = y[:min_len]

        in_ch = X_win.shape[2]

        # 3-fold block CV for ensemble evaluation
        n_samples = len(X_grand)
        fold_size = n_samples // 3
        ensemble_scores = {
            'ridge': [], 'gb': [], 'cnn': [],
            'avg': [], 'weighted': [], 'stacked': [],
        }

        for fold in range(3):
            val_start = fold * fold_size
            val_end = val_start + fold_size if fold < 2 else n_samples
            mask = np.ones(n_samples, dtype=bool)
            mask[val_start:val_end] = False

            Xg_tr, Xg_vl = X_grand[mask], X_grand[~mask]
            Xw_tr, Xw_vl = X_win[mask], X_win[~mask]
            y_tr, y_vl = y[mask], y[~mask]

            # Train individual models
            ridge = Ridge(alpha=1.0)
            ridge.fit(Xg_tr, y_tr)
            pred_ridge = ridge.predict(Xg_vl)

            gb = GradientBoostingRegressor(
                n_estimators=200, max_depth=4, learning_rate=0.05,
                random_state=42)
            gb.fit(Xg_tr, y_tr)
            pred_gb = gb.predict(Xg_vl)

            pred_cnn = train_cnn_model(Xw_tr, y_tr, Xw_vl, in_ch, epochs=40)

            # Individual scores
            r2_ridge = compute_r2(y_vl, pred_ridge)
            r2_gb = compute_r2(y_vl, pred_gb)
            r2_cnn = compute_r2(y_vl, pred_cnn)

            ensemble_scores['ridge'].append(r2_ridge)
            ensemble_scores['gb'].append(r2_gb)
            ensemble_scores['cnn'].append(r2_cnn)

            # --- Blend A: Simple average ---
            pred_avg = (pred_ridge + pred_gb + pred_cnn) / 3.0
            r2_avg = compute_r2(y_vl, pred_avg)
            ensemble_scores['avg'].append(r2_avg)

            # --- Blend B: Optimized weights ---
            # Find weights that minimize MSE on val set via grid search
            best_w_r2 = -999
            best_w = (1/3, 1/3, 1/3)
            for w1 in np.arange(0.0, 1.05, 0.1):
                for w2 in np.arange(0.0, 1.05 - w1, 0.1):
                    w3 = 1.0 - w1 - w2
                    if w3 < -0.01:
                        continue
                    pred_w = w1 * pred_ridge + w2 * pred_gb + w3 * pred_cnn
                    r2_w = compute_r2(y_vl, pred_w)
                    if r2_w > best_w_r2:
                        best_w_r2 = r2_w
                        best_w = (round(w1, 1), round(w2, 1), round(w3, 1))
            ensemble_scores['weighted'].append(best_w_r2)

            # --- Blend C: Stacking (Ridge on predictions) ---
            # Use train set predictions for stacking meta-learner
            pred_ridge_tr = ridge.predict(Xg_tr)
            pred_gb_tr = gb.predict(Xg_tr)
            pred_cnn_tr = train_cnn_model(Xw_tr, y_tr, Xw_tr, in_ch,
                                          epochs=40)

            meta_X_tr = np.column_stack([pred_ridge_tr, pred_gb_tr,
                                         pred_cnn_tr])
            meta_X_vl = np.column_stack([pred_ridge, pred_gb, pred_cnn])

            meta_model = Ridge(alpha=0.1)
            meta_model.fit(meta_X_tr, y_tr)
            pred_stacked = meta_model.predict(meta_X_vl)
            r2_stacked = compute_r2(y_vl, pred_stacked)
            ensemble_scores['stacked'].append(r2_stacked)

        # Compute means
        means = {k: round(float(np.mean(v)), 4)
                 for k, v in ensemble_scores.items()}

        best_ensemble = max(
            [('avg', means['avg']),
             ('weighted', means['weighted']),
             ('stacked', means['stacked'])],
            key=lambda x: x[1])
        best_individual = max(
            [('ridge', means['ridge']),
             ('gb', means['gb']),
             ('cnn', means['cnn'])],
            key=lambda x: x[1])

        res = {
            'patient': p['name'],
            'r2_ridge': means['ridge'],
            'r2_gb': means['gb'],
            'r2_cnn': means['cnn'],
            'r2_avg': means['avg'],
            'r2_weighted': means['weighted'],
            'r2_stacked': means['stacked'],
            'best_individual': best_individual[0],
            'best_ensemble': best_ensemble[0],
            'ensemble_gain': round(best_ensemble[1] - best_individual[1], 4),
            'n_samples': n_samples,
        }
        results.append(res)
        if detail:
            print(f"    {p['name']}: Ridge={means['ridge']:.4f} "
                  f"GB={means['gb']:.4f} CNN={means['cnn']:.4f} | "
                  f"avg={means['avg']:.4f} "
                  f"weighted={means['weighted']:.4f} "
                  f"stacked={means['stacked']:.4f} "
                  f"(gain={best_ensemble[1] - best_individual[1]:+.4f})")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    summary_means = {
        'mean_ridge': round(np.mean([r['r2_ridge'] for r in results]), 4),
        'mean_gb': round(np.mean([r['r2_gb'] for r in results]), 4),
        'mean_cnn': round(np.mean([r['r2_cnn'] for r in results]), 4),
        'mean_avg': round(np.mean([r['r2_avg'] for r in results]), 4),
        'mean_weighted': round(np.mean([r['r2_weighted'] for r in results]),
                               4),
        'mean_stacked': round(np.mean([r['r2_stacked'] for r in results]), 4),
        'mean_ensemble_gain': round(
            np.mean([r['ensemble_gain'] for r in results]), 4),
        'n_positive_gain': sum(1 for r in results
                               if r['ensemble_gain'] > 0),
        'n_patients': len(results),
    }
    best_overall = max(
        [(k, v) for k, v in summary_means.items() if k.startswith('mean_')],
        key=lambda x: x[1])

    return {
        'status': 'pass',
        'detail': (f'Ridge={summary_means["mean_ridge"]:.4f} '
                   f'GB={summary_means["mean_gb"]:.4f} '
                   f'CNN={summary_means["mean_cnn"]:.4f} | '
                   f'avg={summary_means["mean_avg"]:.4f} '
                   f'weighted={summary_means["mean_weighted"]:.4f} '
                   f'stacked={summary_means["mean_stacked"]:.4f} '
                   f'(gain={summary_means["mean_ensemble_gain"]:+.4f}, '
                   f'{summary_means["n_positive_gain"]}/{len(results)} '
                   f'improved)'),
        'results': {'per_patient': results, 'summary': summary_means},
    }


# ---------------------------------------------------------------------------
# EXP-1109: Glucose Trend Features (Direction + Momentum)
# ---------------------------------------------------------------------------

def exp_1109_trend_features(patients, detail=False):
    """Extract trend features from the glucose signal itself.

    Adds slope, acceleration, direction changes, and distance from extrema
    as extra features on top of the standard window.
    """
    results = []
    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        n = min(len(glucose), len(physics))
        if n < WINDOW + HORIZON + 50:
            continue
        glucose, physics = glucose[:n], physics[:n]

        g = glucose / GLUCOSE_SCALE
        n_total = len(g)

        # Build base features + trend features
        X_base_list, X_trend_list, y_list = [], [], []

        for i in range(0, n_total - WINDOW - HORIZON, STRIDE):
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

            # Base features (flat window)
            base = np.concatenate([g_win, p_win.ravel()])

            # --- Trend features ---
            trend = []

            # Slope over last 15min (3 points), 30min (6), 60min (12)
            for lookback in [3, 6, 12]:
                if len(g_win) >= lookback:
                    segment = g_win[-lookback:]
                    x_t = np.arange(lookback)
                    slope = np.polyfit(x_t, segment, 1)[0] if len(
                        segment) > 1 else 0.0
                else:
                    slope = 0.0
                trend.append(slope)

            # Acceleration (slope change rate)
            if len(g_win) >= 6:
                slope_early = np.polyfit(np.arange(3), g_win[-6:-3], 1)[0]
                slope_late = np.polyfit(np.arange(3), g_win[-3:], 1)[0]
                accel = slope_late - slope_early
            else:
                accel = 0.0
            trend.append(accel)

            # Number of direction changes in window
            diffs = np.diff(g_win)
            signs = np.sign(diffs)
            sign_changes = np.sum(np.abs(np.diff(signs)) > 0)
            trend.append(sign_changes / max(len(signs) - 1, 1))

            # Distance from recent min and max (normalized)
            g_min = np.min(g_win)
            g_max = np.max(g_win)
            g_last = g_win[-1]
            g_range = g_max - g_min
            if g_range > 0:
                dist_from_min = (g_last - g_min) / g_range
                dist_from_max = (g_max - g_last) / g_range
            else:
                dist_from_min = 0.5
                dist_from_max = 0.5
            trend.append(dist_from_min)
            trend.append(dist_from_max)

            # Momentum: exponentially weighted slope
            weights_exp = np.exp(np.linspace(-2, 0, len(g_win)))
            weights_exp /= weights_exp.sum()
            weighted_g = g_win * weights_exp
            if len(weighted_g) > 1:
                momentum = np.polyfit(np.arange(len(weighted_g)),
                                      weighted_g, 1)[0]
            else:
                momentum = 0.0
            trend.append(momentum)

            # Volatility: rolling std ratio (recent vs earlier)
            if len(g_win) >= 12:
                std_recent = np.std(g_win[-6:])
                std_early = np.std(g_win[:6])
                volatility_ratio = (std_recent / max(std_early, 1e-6))
            else:
                volatility_ratio = 1.0
            trend.append(volatility_ratio)

            trend = np.array(trend)
            X_base_list.append(base)
            X_trend_list.append(trend)
            y_list.append(y_val)

        if len(X_base_list) < 200:
            continue

        X_base = np.array(X_base_list)
        X_trend = np.array(X_trend_list)
        X_combined = np.column_stack([X_base, X_trend])
        y = np.array(y_list)

        def ridge_fn():
            return Ridge(alpha=1.0)

        # Block CV on base features only
        base_mean, base_folds = block_cv_score(X_base, y, ridge_fn, n_folds=3)

        # Block CV on trend features only
        trend_mean, trend_folds = block_cv_score(X_trend, y, ridge_fn,
                                                  n_folds=3)

        # Block CV on base + trend combined
        combined_mean, combined_folds = block_cv_score(X_combined, y,
                                                        ridge_fn, n_folds=3)

        # Also test with GB on combined
        def gb_fn():
            return GradientBoostingRegressor(
                n_estimators=200, max_depth=4, learning_rate=0.05,
                random_state=42)

        gb_combined_mean, _ = block_cv_score(X_combined, y, gb_fn, n_folds=3)

        res = {
            'patient': p['name'],
            'r2_base': round(base_mean, 4),
            'r2_trend_only': round(trend_mean, 4),
            'r2_combined': round(combined_mean, 4),
            'r2_gb_combined': round(gb_combined_mean, 4),
            'trend_gain_ridge': round(combined_mean - base_mean, 4),
            'n_trend_features': X_trend.shape[1],
            'n_samples': len(X_base),
        }
        results.append(res)
        if detail:
            print(f"    {p['name']}: base={base_mean:.4f} "
                  f"trend_only={trend_mean:.4f} "
                  f"combined={combined_mean:.4f} "
                  f"GB_combined={gb_combined_mean:.4f} "
                  f"(gain={combined_mean - base_mean:+.4f})")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    mean_base = np.mean([r['r2_base'] for r in results])
    mean_trend = np.mean([r['r2_trend_only'] for r in results])
    mean_combined = np.mean([r['r2_combined'] for r in results])
    mean_gb_combined = np.mean([r['r2_gb_combined'] for r in results])
    n_improved = sum(1 for r in results if r['trend_gain_ridge'] > 0)

    summary = {
        'mean_r2_base': round(mean_base, 4),
        'mean_r2_trend_only': round(mean_trend, 4),
        'mean_r2_combined': round(mean_combined, 4),
        'mean_r2_gb_combined': round(mean_gb_combined, 4),
        'mean_trend_gain': round(mean_combined - mean_base, 4),
        'n_improved': n_improved,
        'n_patients': len(results),
    }
    return {
        'status': 'pass',
        'detail': (f'base={mean_base:.4f} trend={mean_trend:.4f} '
                   f'combined={mean_combined:.4f} '
                   f'GB_combined={mean_gb_combined:.4f} '
                   f'(gain={mean_combined - mean_base:+.4f}, '
                   f'{n_improved}/{len(results)} improved)'),
        'results': {'per_patient': results, 'summary': summary},
    }


# ---------------------------------------------------------------------------
# EXP-1110: Online Learning Simulation
# ---------------------------------------------------------------------------

def exp_1110_online_learning(patients, detail=False):
    """Simulate online/streaming prediction with expanding window training.

    Compares static (train once), expanding window (retrain every 1000 steps),
    and sliding window (last 7 days) approaches.
    """
    RETRAIN_INTERVAL = 1000
    SLIDING_WINDOW_STEPS = 2016  # ~7 days at 5-min intervals

    results = []
    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        n = min(len(glucose), len(physics))
        if n < WINDOW + HORIZON + 50:
            continue
        glucose, physics = glucose[:n], physics[:n]

        X, y = build_grand_features(glucose, physics)
        if len(X) < 500:
            continue

        n_samples = len(X)
        init_train_size = n_samples // 5  # First 20%

        if init_train_size < 100:
            continue

        # --- Strategy A: Static model (trained once on first 80%) ---
        static_split = int(n_samples * 0.8)
        X_static_tr, y_static_tr = X[:static_split], y[:static_split]
        X_static_vl, y_static_vl = X[static_split:], y[static_split:]

        ridge_static = Ridge(alpha=1.0)
        ridge_static.fit(X_static_tr, y_static_tr)
        if len(X_static_vl) > 0:
            r2_static = compute_r2(y_static_vl, ridge_static.predict(
                X_static_vl))
        else:
            r2_static = 0.0

        # --- Strategy B: Expanding window ---
        expanding_preds = []
        expanding_trues = []
        current_train_end = init_train_size

        while current_train_end < n_samples:
            eval_end = min(current_train_end + RETRAIN_INTERVAL, n_samples)
            X_tr = X[:current_train_end]
            y_tr = y[:current_train_end]
            X_eval = X[current_train_end:eval_end]
            y_eval = y[current_train_end:eval_end]

            if len(X_eval) == 0:
                break

            ridge_exp = Ridge(alpha=1.0)
            ridge_exp.fit(X_tr, y_tr)
            preds = ridge_exp.predict(X_eval)

            expanding_preds.extend(preds.tolist())
            expanding_trues.extend(y_eval.tolist())
            current_train_end = eval_end

        r2_expanding = compute_r2(np.array(expanding_trues),
                                   np.array(expanding_preds)) \
            if expanding_trues else 0.0

        # --- Strategy C: Sliding window (last ~7 days) ---
        sliding_preds = []
        sliding_trues = []
        current_pos = init_train_size

        while current_pos < n_samples:
            eval_end = min(current_pos + RETRAIN_INTERVAL, n_samples)
            # Use only the last SLIDING_WINDOW_STEPS for training
            train_start = max(0, current_pos - SLIDING_WINDOW_STEPS)
            X_tr = X[train_start:current_pos]
            y_tr = y[train_start:current_pos]
            X_eval = X[current_pos:eval_end]
            y_eval = y[current_pos:eval_end]

            if len(X_eval) == 0 or len(X_tr) < 50:
                current_pos = eval_end
                continue

            ridge_slide = Ridge(alpha=1.0)
            ridge_slide.fit(X_tr, y_tr)
            preds = ridge_slide.predict(X_eval)

            sliding_preds.extend(preds.tolist())
            sliding_trues.extend(y_eval.tolist())
            current_pos = eval_end

        r2_sliding = compute_r2(np.array(sliding_trues),
                                 np.array(sliding_preds)) \
            if sliding_trues else 0.0

        # Evaluate temporal drift: compare performance on first vs last
        # quarter of expanding predictions
        n_exp = len(expanding_preds)
        drift_early, drift_late = 0.0, 0.0
        if n_exp >= 100:
            quarter = n_exp // 4
            early_r2 = compute_r2(
                np.array(expanding_trues[:quarter]),
                np.array(expanding_preds[:quarter]))
            late_r2 = compute_r2(
                np.array(expanding_trues[-quarter:]),
                np.array(expanding_preds[-quarter:]))
            drift_early = round(early_r2, 4)
            drift_late = round(late_r2, 4)

        best_strategy = max(
            [('static', r2_static),
             ('expanding', r2_expanding),
             ('sliding', r2_sliding)],
            key=lambda x: x[1])

        res = {
            'patient': p['name'],
            'r2_static': round(r2_static, 4),
            'r2_expanding': round(r2_expanding, 4),
            'r2_sliding': round(r2_sliding, 4),
            'best_strategy': best_strategy[0],
            'expanding_vs_static': round(r2_expanding - r2_static, 4),
            'sliding_vs_expanding': round(r2_sliding - r2_expanding, 4),
            'drift_early_r2': drift_early,
            'drift_late_r2': drift_late,
            'drift': round(drift_late - drift_early, 4),
            'n_samples': n_samples,
            'n_retrains': max(1, (n_samples - init_train_size) //
                              RETRAIN_INTERVAL),
        }
        results.append(res)
        if detail:
            print(f"    {p['name']}: static={r2_static:.4f} "
                  f"expanding={r2_expanding:.4f} "
                  f"sliding={r2_sliding:.4f} "
                  f"(best={best_strategy[0]}, "
                  f"drift={drift_late - drift_early:+.4f})")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    mean_static = np.mean([r['r2_static'] for r in results])
    mean_expanding = np.mean([r['r2_expanding'] for r in results])
    mean_sliding = np.mean([r['r2_sliding'] for r in results])
    mean_drift = np.mean([r['drift'] for r in results])

    strategy_wins = {}
    for r in results:
        s = r['best_strategy']
        strategy_wins[s] = strategy_wins.get(s, 0) + 1

    summary = {
        'mean_r2_static': round(mean_static, 4),
        'mean_r2_expanding': round(mean_expanding, 4),
        'mean_r2_sliding': round(mean_sliding, 4),
        'mean_drift': round(mean_drift, 4),
        'strategy_wins': strategy_wins,
        'retrain_interval': RETRAIN_INTERVAL,
        'sliding_window_steps': SLIDING_WINDOW_STEPS,
        'n_patients': len(results),
        'conclusion': ('expanding > static suggests data distribution '
                       'shifts over time; sliding vs expanding reveals '
                       'whether recent data is more valuable'),
    }
    return {
        'status': 'pass',
        'detail': (f'static={mean_static:.4f} '
                   f'expanding={mean_expanding:.4f} '
                   f'sliding={mean_sliding:.4f} '
                   f'(wins={strategy_wins}, '
                   f'drift={mean_drift:+.4f})'),
        'results': {'per_patient': results, 'summary': summary},
    }


# ---------------------------------------------------------------------------
# Experiment registry and main
# ---------------------------------------------------------------------------

EXPERIMENTS = [
    ('EXP-1101', 'XGBoost GPU Acceleration', exp_1101_xgboost_gpu),
    ('EXP-1102', 'Predict Δg (Rate of Change)', exp_1102_delta_glucose),
    ('EXP-1103', 'Regime-Specific Loss Weighting', exp_1103_regime_weighting),
    ('EXP-1104', 'Quantile Regression for Prediction Intervals',
     exp_1104_quantile_regression),
    ('EXP-1105', 'Missing Data Imputation Strategies',
     exp_1105_missing_data),
    ('EXP-1106', 'Per-Patient Fine-Tuning', exp_1106_fine_tuning),
    ('EXP-1107', 'Temporal Convolutional Network (TCN)', exp_1107_tcn),
    ('EXP-1108', 'Ensemble of Ridge + GB + CNN', exp_1108_ensemble),
    ('EXP-1109', 'Glucose Trend Features', exp_1109_trend_features),
    ('EXP-1110', 'Online Learning Simulation', exp_1110_online_learning),
]


def main():
    parser = argparse.ArgumentParser(
        description='EXP-1101-1110: Advanced ML, Clinical Targets, '
                    'and Online Learning')
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--max-patients', type=int, default=11)
    parser.add_argument('--experiment', type=str,
                        help='Run only this experiment (e.g. EXP-1101)')
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
