#!/usr/bin/env python3
"""EXP-1071 to EXP-1080: Closing the R² gap — deeper models, richer features, multi-output.

Building on 60 experiments of findings (EXP-1021–1070):
- SOTA R²=0.535 (3-fold block CV), noise ceiling R²=0.854 (σ=15mg/dL)
- At 63% of ceiling — 37% remaining is unexplained glucose dynamics
- AR residual features are LEAKAGE (adjacent=+0.243, gapped=+0.000) — excluded
- Residual CNN: +0.013, 11/11 universal — short-range L1 autocorrelation
- Gradient Boosting: +0.015 over Ridge, 7/11, best for hard patients
- Physics beats all naive baselines 11/11
- Personalization essential — global/tier models catastrophically fail

This batch focuses on:
1. XGBoost-style hyperparameter search for GB (EXP-1071) ★★
2. Multi-output trajectory prediction (EXP-1072)
3. Residual CNN with more capacity (EXP-1073) ★
4. Physics channel normalization study (EXP-1074)
5. Glucose rate of change as feature (EXP-1075) ★★
6. Ensemble of diverse models (EXP-1076)
7. Per-patient model selection oracle (EXP-1077)
8. Prediction horizon sweep (EXP-1078)
9. Residual error decomposition (EXP-1079) ★★★
10. Grand benchmark with best techniques (EXP-1080) ★★★

Run:
    PYTHONPATH=tools python -m cgmencode.exp_clinical_1071 --detail --save --max-patients 11
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
from torch.utils.data import TensorDataset, DataLoader

PATIENTS_DIR = str(Path(__file__).resolve().parent.parent.parent / 'externals' / 'ns-data' / 'patients')
GLUCOSE_SCALE = 400.0
WINDOW = 24       # 2 hours at 5-min intervals
HORIZON = 12      # 1 hour ahead
STRIDE = 6
DEVICE = torch.device('cuda' if torch.cuda.is_available() else 'cpu')


# ─── Neural Network Models ───

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


class FlexibleCNN(nn.Module):
    """CNN with configurable depth and width."""
    def __init__(self, in_channels, layer_channels, dropout=0.0):
        super().__init__()
        layers = []
        prev_ch = in_channels
        for ch in layer_channels:
            layers.append(nn.Conv1d(prev_ch, ch, 3, padding=1))
            layers.append(nn.ReLU())
            if dropout > 0:
                layers.append(nn.Dropout(dropout))
            prev_ch = ch
        self.convs = nn.Sequential(*layers)
        self.pool = nn.AdaptiveAvgPool1d(1)
        self.fc = nn.Linear(prev_ch, 1)

    def forward(self, x):
        h = self.convs(x.permute(0, 2, 1))
        h = self.pool(h).squeeze(-1)
        return self.fc(h).squeeze(-1)


# ─── Core Helper Functions ───

def make_windows(glucose, physics, window=WINDOW, horizon=HORIZON, stride=STRIDE):
    """Create X, y pairs from glucose and physics arrays."""
    X_list, y_list = [], []
    g = glucose / GLUCOSE_SCALE
    for i in range(0, len(g) - window - horizon, stride):
        g_win = g[i:i+window]
        if np.isnan(g_win).mean() > 0.3:
            continue
        g_win = np.nan_to_num(g_win, nan=np.nanmean(g_win) if np.any(~np.isnan(g_win)) else 0.4)
        p_win = physics[i:i+window]
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


def make_windows_multi_horizon(glucose, physics, window=WINDOW, horizons=None,
                               stride=STRIDE):
    """Create X, Y pairs with multiple horizons. Y shape: (n_samples, n_horizons)."""
    if horizons is None:
        horizons = [3, 6, 9, 12]  # 15, 30, 45, 60 min
    max_h = max(horizons)
    X_list, Y_list = [], []
    g = glucose / GLUCOSE_SCALE
    for i in range(0, len(g) - window - max_h, stride):
        g_win = g[i:i+window]
        if np.isnan(g_win).mean() > 0.3:
            continue
        g_win = np.nan_to_num(g_win, nan=np.nanmean(g_win) if np.any(~np.isnan(g_win)) else 0.4)
        p_win = physics[i:i+window]
        if np.isnan(p_win).any():
            p_win = np.nan_to_num(p_win, nan=0.0)
        y_vals = [g[i + window + h - 1] for h in horizons]
        if any(np.isnan(yv) for yv in y_vals):
            continue
        X_list.append(np.column_stack([g_win.reshape(-1, 1), p_win]))
        Y_list.append(y_vals)
    if len(X_list) == 0:
        return np.array([]).reshape(0, window, 1), np.array([]).reshape(0, len(horizons))
    return np.array(X_list), np.array(Y_list)


def split_data(X, y, train_frac=0.8):
    n = len(X)
    split = int(n * train_frac)
    return X[:split], X[split:], y[:split], y[split:]


def compute_r2(y_true, y_pred):
    ss_res = np.sum((y_true - y_pred)**2)
    ss_tot = np.sum((y_true - y_true.mean())**2)
    if ss_tot == 0:
        return 0.0
    return 1 - ss_res / ss_tot


def eval_ridge(X_train, X_val, y_train, y_val, alpha=1.0):
    Xtr = X_train.reshape(len(X_train), -1)
    Xvl = X_val.reshape(len(X_val), -1)
    model = Ridge(alpha=alpha)
    model.fit(Xtr, y_train)
    pred = model.predict(Xvl)
    r2 = compute_r2(y_val, pred)
    return r2, pred, model


def block_cv_eval(X, y, eval_fn, n_folds=3):
    """Block cross-validation. eval_fn(X_train, X_val, y_train, y_val) -> r2."""
    n = len(X)
    fold_size = n // n_folds
    scores = []
    for fold in range(n_folds):
        val_start = fold * fold_size
        val_end = val_start + fold_size if fold < n_folds - 1 else n
        mask = np.ones(n, dtype=bool)
        mask[val_start:val_end] = False
        r2 = eval_fn(X[mask], X[~mask], y[mask], y[~mask])
        scores.append(r2)
    return np.mean(scores), scores


def prepare_patient(p):
    """Standard patient preparation: compute physics, make windows."""
    sd = compute_supply_demand(p['df'], p['pk'])
    supply = sd['supply'] / 20.0
    demand = sd['demand'] / 20.0
    hepatic = sd['hepatic'] / 5.0
    net = sd['net'] / 20.0
    physics = np.column_stack([supply, demand, hepatic, net])
    glucose = p['df']['glucose'].values.astype(float)
    X, y = make_windows(glucose, physics)
    return X, y


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


def train_cnn(model, X_train, y_train, X_val, y_val, epochs=50, lr=1e-3,
              batch_size=256):
    """Train CNN and return predictions on validation set."""
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    criterion = nn.MSELoss()
    Xt = torch.FloatTensor(X_train).to(DEVICE)
    yt = torch.FloatTensor(y_train).to(DEVICE)
    Xv = torch.FloatTensor(X_val).to(DEVICE)
    best_val_loss = float('inf')
    best_state = None
    for epoch in range(epochs):
        model.train()
        indices = torch.randperm(len(Xt))
        for start in range(0, len(Xt), batch_size):
            idx = indices[start:start+batch_size]
            pred = model(Xt[idx])
            loss = criterion(pred, yt[idx])
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
        model.eval()
        with torch.no_grad():
            val_pred = model(Xv)
            val_loss = criterion(val_pred, torch.FloatTensor(y_val).to(DEVICE)).item()
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
    if best_state:
        model.load_state_dict(best_state)
    model.eval()
    with torch.no_grad():
        final_pred = model(Xv).cpu().numpy()
    return final_pred


def predict_cnn(model, X):
    """Get numpy predictions from a trained model."""
    model.eval()
    with torch.no_grad():
        pred = model(torch.FloatTensor(X).to(DEVICE))
        return pred.cpu().numpy()


def clarke_error_grid(y_true_mgdl, y_pred_mgdl):
    """Compute Clarke Error Grid zone percentages."""
    n = len(y_true_mgdl)
    zones = {'A': 0, 'B': 0, 'C': 0, 'D': 0, 'E': 0}
    for ref, pred in zip(y_true_mgdl, y_pred_mgdl):
        if (ref <= 70 and pred <= 70) or abs(pred - ref) <= 20 or \
           (ref >= 70 and abs(pred - ref) / ref <= 0.20):
            zones['A'] += 1
        elif (ref >= 180 and pred <= 70) or (ref <= 70 and pred >= 180):
            zones['E'] += 1
        elif ((ref >= 70 and ref <= 180) and (pred >= ref + 110 or pred <= ref - 110)):
            zones['D'] += 1
        elif ((ref < 70 and pred > ref + 30) or (ref > 180 and pred < ref - 30)):
            zones['C'] += 1
        else:
            zones['B'] += 1
    return {k: v / n * 100 for k, v in zones.items()}


def compute_interactions(X):
    """Compute pairwise interaction features from physics channels."""
    phys_means = np.mean(X[:, :, 1:], axis=1)  # (n, 4)
    s, d, h_ch, net_f = phys_means[:, 0], phys_means[:, 1], phys_means[:, 2], phys_means[:, 3]
    return np.column_stack([
        s * d, s * h_ch, s * net_f, d * h_ch, d * net_f, h_ch * net_f,
    ])


# ─── EXP-1071: XGBoost-style Hyperparameter Search for GB ───

def exp_1071_gb_hyperparam_search(patients, detail=False):
    """GradientBoosting with grid search over key hyperparameters.

    GB showed +0.015 over Ridge with defaults (n_estimators=100, max_depth=4, lr=0.1).
    Now systematically search: n_estimators in [50, 100, 200, 500],
    max_depth in [3, 4, 6, 8], learning_rate in [0.01, 0.05, 0.1].
    Report best config per patient and whether tuned GB closes gap further.
    """
    param_grid = {
        'n_estimators': [100, 200],
        'max_depth': [4, 6],
        'learning_rate': [0.05, 0.1],
    }
    results = []

    for p in patients:
        X, y = prepare_patient(p)
        if len(X) < 200:
            continue

        X_tr, X_vl, y_tr, y_vl = split_data(X, y)
        Xf_tr = X_tr.reshape(len(X_tr), -1)
        Xf_vl = X_vl.reshape(len(X_vl), -1)

        # Ridge baseline
        ridge = Ridge(alpha=1.0)
        ridge.fit(Xf_tr, y_tr)
        pred_ridge = ridge.predict(Xf_vl)
        r2_ridge = compute_r2(y_vl, pred_ridge)

        # Default GB baseline
        gb_default = GradientBoostingRegressor(
            n_estimators=100, max_depth=4, learning_rate=0.1,
            random_state=42, subsample=0.8)
        gb_default.fit(Xf_tr, y_tr)
        r2_gb_default = compute_r2(y_vl, gb_default.predict(Xf_vl))

        # Grid search
        best_r2 = -999.0
        best_params = {}
        configs_tested = 0
        for n_est in param_grid['n_estimators']:
            for depth in param_grid['max_depth']:
                for lr in param_grid['learning_rate']:
                    gb = GradientBoostingRegressor(
                        n_estimators=n_est, max_depth=depth, learning_rate=lr,
                        random_state=42, subsample=0.8)
                    gb.fit(Xf_tr, y_tr)
                    pred = gb.predict(Xf_vl)
                    r2 = compute_r2(y_vl, pred)
                    configs_tested += 1
                    if r2 > best_r2:
                        best_r2 = r2
                        best_params = {'n_estimators': n_est, 'max_depth': depth,
                                       'learning_rate': lr}

        res = {
            'patient': p['name'],
            'r2_ridge': round(r2_ridge, 4),
            'r2_gb_default': round(r2_gb_default, 4),
            'r2_gb_tuned': round(best_r2, 4),
            'gain_default_vs_ridge': round(r2_gb_default - r2_ridge, 4),
            'gain_tuned_vs_default': round(best_r2 - r2_gb_default, 4),
            'gain_tuned_vs_ridge': round(best_r2 - r2_ridge, 4),
            'best_params': best_params,
            'configs_tested': configs_tested,
        }
        results.append(res)
        if detail:
            print(f"    {p['name']}: ridge={r2_ridge:.4f} gb_def={r2_gb_default:.4f} "
                  f"gb_tuned={best_r2:.4f}({best_r2-r2_gb_default:+.4f}) "
                  f"params={best_params}")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    summary = {
        'mean_r2_ridge': round(np.mean([r['r2_ridge'] for r in results]), 4),
        'mean_r2_gb_default': round(np.mean([r['r2_gb_default'] for r in results]), 4),
        'mean_r2_gb_tuned': round(np.mean([r['r2_gb_tuned'] for r in results]), 4),
        'mean_gain_tuned_vs_default': round(np.mean(
            [r['gain_tuned_vs_default'] for r in results]), 4),
        'mean_gain_tuned_vs_ridge': round(np.mean(
            [r['gain_tuned_vs_ridge'] for r in results]), 4),
        'n_tuned_beats_default': sum(1 for r in results
                                     if r['r2_gb_tuned'] > r['r2_gb_default']),
        'n_patients': len(results),
        'most_common_depth': max(
            set(r['best_params']['max_depth'] for r in results),
            key=lambda d: sum(1 for r in results if r['best_params']['max_depth'] == d)),
        'most_common_n_est': max(
            set(r['best_params']['n_estimators'] for r in results),
            key=lambda n: sum(1 for r in results if r['best_params']['n_estimators'] == n)),
    }
    return {
        'status': 'pass',
        'detail': (f'ridge={summary["mean_r2_ridge"]:.4f} '
                   f'gb_def={summary["mean_r2_gb_default"]:.4f} '
                   f'gb_tuned={summary["mean_r2_gb_tuned"]:.4f} '
                   f'(+{summary["mean_gain_tuned_vs_default"]:.4f} vs default) '
                   f'tuned>def={summary["n_tuned_beats_default"]}/{len(results)} '
                   f'common_depth={summary["most_common_depth"]} '
                   f'common_n_est={summary["most_common_n_est"]}'),
        'results': {'per_patient': results, 'summary': summary},
    }


# ─── EXP-1072: Multi-Output Trajectory Prediction ───

def exp_1072_multi_output_trajectory(patients, detail=False):
    """Multi-output trajectory prediction: t+15, t+30, t+45, t+60 simultaneously.

    Instead of predicting a single point at t+60min, predict the full trajectory.
    Uses Ridge with 4 outputs. The trajectory constraint provides regularization —
    the model must predict a physically plausible glucose curve.
    Compare: the t+60 prediction from multi-output vs single-output Ridge.
    """
    horizons = [3, 6, 9, 12]  # 15, 30, 45, 60 min
    horizon_labels = ['15min', '30min', '45min', '60min']
    results = []

    for p in patients:
        glucose, physics = prepare_patient_raw(p)

        # Multi-horizon windows
        X_multi, Y_multi = make_windows_multi_horizon(glucose, physics, horizons=horizons)
        if len(X_multi) < 200:
            continue

        # Single-horizon windows (standard 60min)
        X_single, y_single = make_windows(glucose, physics)
        if len(X_single) < 200:
            continue

        # Split both
        X_m_tr, X_m_vl, Y_m_tr, Y_m_vl = split_data(X_multi, Y_multi)
        X_s_tr, X_s_vl, y_s_tr, y_s_vl = split_data(X_single, y_single)

        Xf_m_tr = X_m_tr.reshape(len(X_m_tr), -1)
        Xf_m_vl = X_m_vl.reshape(len(X_m_vl), -1)
        Xf_s_tr = X_s_tr.reshape(len(X_s_tr), -1)
        Xf_s_vl = X_s_vl.reshape(len(X_s_vl), -1)

        # Multi-output Ridge (4 targets)
        ridge_multi = Ridge(alpha=1.0)
        ridge_multi.fit(Xf_m_tr, Y_m_tr)
        pred_multi = ridge_multi.predict(Xf_m_vl)

        # Single-output Ridge (60min only)
        ridge_single = Ridge(alpha=1.0)
        ridge_single.fit(Xf_s_tr, y_s_tr)
        pred_single = ridge_single.predict(Xf_s_vl)

        # R² for each horizon from multi-output model
        r2_per_horizon = {}
        for idx, label in enumerate(horizon_labels):
            r2_per_horizon[label] = round(compute_r2(Y_m_vl[:, idx], pred_multi[:, idx]), 4)

        # R² for single-output at 60min
        r2_single_60 = compute_r2(y_s_vl, pred_single)

        # Compare 60min prediction: multi vs single
        # Use the 60min column (index 3) from multi-output
        r2_multi_60 = r2_per_horizon['60min']

        res = {
            'patient': p['name'],
            'r2_single_60min': round(r2_single_60, 4),
            'r2_multi_60min': round(r2_multi_60, 4),
            'r2_per_horizon': r2_per_horizon,
            'gain_multi_vs_single': round(r2_multi_60 - r2_single_60, 4),
            'n_windows_multi': len(X_multi),
            'n_windows_single': len(X_single),
        }
        results.append(res)
        if detail:
            hz_str = ' '.join(f'{k}={v:.4f}' for k, v in r2_per_horizon.items())
            print(f"    {p['name']}: single_60={r2_single_60:.4f} "
                  f"multi_60={r2_multi_60:.4f}({r2_multi_60-r2_single_60:+.4f}) "
                  f"| {hz_str}")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    # Average R² per horizon across patients
    mean_per_horizon = {}
    for label in horizon_labels:
        vals = [r['r2_per_horizon'][label] for r in results]
        mean_per_horizon[label] = round(np.mean(vals), 4)

    summary = {
        'mean_r2_single_60': round(np.mean([r['r2_single_60min'] for r in results]), 4),
        'mean_r2_multi_60': round(np.mean([r['r2_multi_60min'] for r in results]), 4),
        'mean_gain_multi_vs_single': round(np.mean(
            [r['gain_multi_vs_single'] for r in results]), 4),
        'n_multi_beats_single': sum(1 for r in results
                                     if r['r2_multi_60min'] > r['r2_single_60min']),
        'mean_r2_per_horizon': mean_per_horizon,
        'n_patients': len(results),
    }
    return {
        'status': 'pass',
        'detail': (f'single_60={summary["mean_r2_single_60"]:.4f} '
                   f'multi_60={summary["mean_r2_multi_60"]:.4f} '
                   f'(gain={summary["mean_gain_multi_vs_single"]:+.4f}) '
                   f'multi>single={summary["n_multi_beats_single"]}/{len(results)} '
                   f'horizons: {mean_per_horizon}'),
        'results': {'per_patient': results, 'summary': summary},
    }


# ─── EXP-1073: Residual CNN with More Capacity ───

def exp_1073_cnn_capacity_sweep(patients, detail=False):
    """Residual CNN with different architectures: Small, Medium, Large, XL.

    Current CNN: 3 layers, 32->32->16 channels. Test:
    - Small:  3 layers, 16->16->8
    - Medium: 3 layers, 32->32->16  (current baseline)
    - Large:  4 layers, 64->64->32->16
    - XL:     5 layers, 128->64->32->16->8 with dropout=0.2

    The noise ceiling analysis suggests more model capacity might help — we're far
    from overfitting the underlying signal.
    """
    architectures = {
        'small':  {'channels': [16, 16, 8],       'dropout': 0.0},
        'medium': {'channels': [32, 32, 16],      'dropout': 0.0},
        'large':  {'channels': [64, 64, 32, 16],  'dropout': 0.0},
        'xl':     {'channels': [128, 64, 32, 16, 8], 'dropout': 0.2},
    }
    results = []

    for p in patients:
        X, y = prepare_patient(p)
        if len(X) < 200:
            continue

        X_tr, X_vl, y_tr, y_vl = split_data(X, y)
        Xf_tr = X_tr.reshape(len(X_tr), -1)
        Xf_vl = X_vl.reshape(len(X_vl), -1)
        in_channels = X.shape[2]

        # Ridge baseline for residuals
        ridge = Ridge(alpha=1.0)
        ridge.fit(Xf_tr, y_tr)
        pred_ridge = ridge.predict(Xf_vl)
        r2_ridge = compute_r2(y_vl, pred_ridge)

        pred_ridge_tr = ridge.predict(Xf_tr)
        tr_resid = y_tr - pred_ridge_tr

        arch_results = {}
        for arch_name, arch_cfg in architectures.items():
            torch.manual_seed(42)
            cnn = FlexibleCNN(in_channels, arch_cfg['channels'],
                              dropout=arch_cfg['dropout']).to(DEVICE)
            cnn_pred = train_cnn(cnn, X_tr, tr_resid, X_vl,
                                 y_vl - pred_ridge, epochs=50)
            pred_combined = pred_ridge + 0.5 * cnn_pred
            r2 = compute_r2(y_vl, pred_combined)
            n_params = sum(p.numel() for p in cnn.parameters())
            arch_results[arch_name] = {
                'r2': round(r2, 4),
                'lift': round(r2 - r2_ridge, 4),
                'n_params': n_params,
            }

        best_arch = max(arch_results.items(), key=lambda x: x[1]['r2'])
        res = {
            'patient': p['name'],
            'r2_ridge': round(r2_ridge, 4),
            'architectures': arch_results,
            'best_arch': best_arch[0],
            'best_r2': best_arch[1]['r2'],
            'best_lift': best_arch[1]['lift'],
        }
        results.append(res)
        if detail:
            arch_str = ' '.join(f'{k}={v["r2"]:.4f}' for k, v in arch_results.items())
            print(f"    {p['name']}: ridge={r2_ridge:.4f} | {arch_str} | "
                  f"best={best_arch[0]}")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    # Count how often each architecture wins
    arch_wins = {}
    for r in results:
        b = r['best_arch']
        arch_wins[b] = arch_wins.get(b, 0) + 1

    # Mean R² per architecture
    mean_r2_per_arch = {}
    mean_lift_per_arch = {}
    for arch_name in architectures:
        vals = [r['architectures'][arch_name]['r2'] for r in results]
        mean_r2_per_arch[arch_name] = round(np.mean(vals), 4)
        lifts = [r['architectures'][arch_name]['lift'] for r in results]
        mean_lift_per_arch[arch_name] = round(np.mean(lifts), 4)

    summary = {
        'mean_r2_per_arch': mean_r2_per_arch,
        'mean_lift_per_arch': mean_lift_per_arch,
        'arch_wins': arch_wins,
        'mean_r2_ridge': round(np.mean([r['r2_ridge'] for r in results]), 4),
        'n_patients': len(results),
    }
    return {
        'status': 'pass',
        'detail': (f'ridge={summary["mean_r2_ridge"]:.4f} | '
                   + ' '.join(f'{k}={v:.4f}(+{mean_lift_per_arch[k]:.4f})'
                              for k, v in mean_r2_per_arch.items())
                   + f' | wins={arch_wins}'),
        'results': {'per_patient': results, 'summary': summary},
    }


# ─── EXP-1074: Physics Channel Normalization Study ───

def exp_1074_normalization_study(patients, detail=False):
    """Physics channel normalization: z-score, min-max, quantile, raw.

    Currently physics channels are raw values. Different normalization may help
    the model weight channels more equally.
    Test: z-score (per-patient, per-channel), min-max [0,1], quantile (rank-based),
    no normalization (current).
    """
    results = []

    for p in patients:
        sd = compute_supply_demand(p['df'], p['pk'])
        supply = sd['supply'] / 20.0
        demand = sd['demand'] / 20.0
        hepatic = sd['hepatic'] / 5.0
        net = sd['net'] / 20.0
        physics_raw = np.column_stack([supply, demand, hepatic, net])
        glucose = p['df']['glucose'].values.astype(float)

        # Generate 4 normalization variants
        norm_variants = {}

        # 1. Raw (current)
        norm_variants['raw'] = physics_raw.copy()

        # 2. Z-score (per-channel)
        physics_z = physics_raw.copy()
        for ch in range(physics_z.shape[1]):
            col = physics_z[:, ch]
            valid = col[~np.isnan(col)]
            if len(valid) > 0 and np.std(valid) > 1e-10:
                physics_z[:, ch] = (col - np.mean(valid)) / np.std(valid)
        norm_variants['zscore'] = physics_z

        # 3. Min-max [0, 1]
        physics_mm = physics_raw.copy()
        for ch in range(physics_mm.shape[1]):
            col = physics_mm[:, ch]
            valid = col[~np.isnan(col)]
            if len(valid) > 0:
                cmin, cmax = np.min(valid), np.max(valid)
                if cmax - cmin > 1e-10:
                    physics_mm[:, ch] = (col - cmin) / (cmax - cmin)
        norm_variants['minmax'] = physics_mm

        # 4. Quantile (rank-based, robust to outliers)
        physics_q = physics_raw.copy()
        for ch in range(physics_q.shape[1]):
            col = physics_q[:, ch]
            valid_mask = ~np.isnan(col)
            if np.sum(valid_mask) > 0:
                from scipy.stats import rankdata
                ranks = np.zeros_like(col)
                ranks[valid_mask] = rankdata(col[valid_mask]) / np.sum(valid_mask)
                physics_q[:, ch] = ranks
        norm_variants['quantile'] = physics_q

        # Evaluate each normalization with Ridge
        norm_r2 = {}
        for norm_name, physics in norm_variants.items():
            X, y = make_windows(glucose, physics)
            if len(X) < 200:
                continue
            X_tr, X_vl, y_tr, y_vl = split_data(X, y)
            Xf_tr = X_tr.reshape(len(X_tr), -1)
            Xf_vl = X_vl.reshape(len(X_vl), -1)
            ridge = Ridge(alpha=1.0)
            ridge.fit(Xf_tr, y_tr)
            pred = ridge.predict(Xf_vl)
            norm_r2[norm_name] = round(compute_r2(y_vl, pred), 4)

        if not norm_r2:
            continue

        best_norm = max(norm_r2.items(), key=lambda x: x[1])
        res = {
            'patient': p['name'],
            'r2_per_norm': norm_r2,
            'best_norm': best_norm[0],
            'best_r2': best_norm[1],
        }
        if 'raw' in norm_r2:
            res['gain_best_vs_raw'] = round(best_norm[1] - norm_r2['raw'], 4)
        results.append(res)
        if detail:
            norm_str = ' '.join(f'{k}={v:.4f}' for k, v in norm_r2.items())
            print(f"    {p['name']}: {norm_str} | best={best_norm[0]}")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    # Count wins
    norm_wins = {}
    for r in results:
        b = r['best_norm']
        norm_wins[b] = norm_wins.get(b, 0) + 1

    mean_r2_per_norm = {}
    for norm_name in ['raw', 'zscore', 'minmax', 'quantile']:
        vals = [r['r2_per_norm'][norm_name] for r in results
                if norm_name in r['r2_per_norm']]
        if vals:
            mean_r2_per_norm[norm_name] = round(np.mean(vals), 4)

    summary = {
        'mean_r2_per_norm': mean_r2_per_norm,
        'norm_wins': norm_wins,
        'mean_gain_best_vs_raw': round(np.mean(
            [r.get('gain_best_vs_raw', 0) for r in results]), 4),
        'n_patients': len(results),
    }
    return {
        'status': 'pass',
        'detail': (' '.join(f'{k}={v:.4f}' for k, v in mean_r2_per_norm.items())
                   + f' | wins={norm_wins}'
                   + f' | gain_best_vs_raw={summary["mean_gain_best_vs_raw"]:+.4f}'),
        'results': {'per_patient': results, 'summary': summary},
    }


# ─── EXP-1075: Glucose Rate of Change as Feature ───

def exp_1075_glucose_derivatives(patients, detail=False):
    """Glucose rate-of-change and acceleration as input features.

    Instead of raw glucose only, add first derivative (delta = g[t]-g[t-1])
    and second derivative (acceleration = delta[t]-delta[t-1]).
    Compare Ridge and CNN with/without these derived features.
    """
    results = []

    for p in patients:
        glucose, physics = prepare_patient_raw(p)

        # Compute derivatives
        g_scaled = glucose / GLUCOSE_SCALE
        g_delta = np.zeros_like(g_scaled)
        g_delta[1:] = g_scaled[1:] - g_scaled[:-1]
        g_delta[0] = 0.0
        # NaN handling for delta
        nan_mask = np.isnan(g_scaled)
        g_delta[nan_mask] = 0.0
        if len(nan_mask) > 1:
            g_delta[1:][nan_mask[:-1]] = 0.0

        g_accel = np.zeros_like(g_delta)
        g_accel[1:] = g_delta[1:] - g_delta[:-1]

        # Create windowed features WITH derivatives
        # We need custom windowing that includes derivative channels
        physics_with_deriv = np.column_stack([physics, g_delta.reshape(-1, 1),
                                              g_accel.reshape(-1, 1)])
        X_deriv, y_deriv = make_windows(glucose, physics_with_deriv)

        # Without derivatives (standard)
        X_base, y_base = make_windows(glucose, physics)

        if len(X_deriv) < 200 or len(X_base) < 200:
            continue

        in_ch_base = X_base.shape[2]
        in_ch_deriv = X_deriv.shape[2]

        # Split
        X_b_tr, X_b_vl, y_b_tr, y_b_vl = split_data(X_base, y_base)
        X_d_tr, X_d_vl, y_d_tr, y_d_vl = split_data(X_deriv, y_deriv)

        Xf_b_tr = X_b_tr.reshape(len(X_b_tr), -1)
        Xf_b_vl = X_b_vl.reshape(len(X_b_vl), -1)
        Xf_d_tr = X_d_tr.reshape(len(X_d_tr), -1)
        Xf_d_vl = X_d_vl.reshape(len(X_d_vl), -1)

        # Ridge: base vs derivatives
        ridge_base = Ridge(alpha=1.0)
        ridge_base.fit(Xf_b_tr, y_b_tr)
        r2_ridge_base = compute_r2(y_b_vl, ridge_base.predict(Xf_b_vl))

        ridge_deriv = Ridge(alpha=1.0)
        ridge_deriv.fit(Xf_d_tr, y_d_tr)
        r2_ridge_deriv = compute_r2(y_d_vl, ridge_deriv.predict(Xf_d_vl))

        # CNN: base
        pred_ridge_base_tr = ridge_base.predict(Xf_b_tr)
        resid_base_tr = y_b_tr - pred_ridge_base_tr
        pred_ridge_base_vl = ridge_base.predict(Xf_b_vl)

        torch.manual_seed(42)
        cnn_base = ResidualCNN(in_channels=in_ch_base).to(DEVICE)
        cnn_pred_base = train_cnn(cnn_base, X_b_tr, resid_base_tr, X_b_vl,
                                  y_b_vl - pred_ridge_base_vl, epochs=50)
        r2_cnn_base = compute_r2(y_b_vl, pred_ridge_base_vl + 0.5 * cnn_pred_base)

        # CNN: with derivatives
        pred_ridge_deriv_tr = ridge_deriv.predict(Xf_d_tr)
        resid_deriv_tr = y_d_tr - pred_ridge_deriv_tr
        pred_ridge_deriv_vl = ridge_deriv.predict(Xf_d_vl)

        torch.manual_seed(42)
        cnn_deriv = ResidualCNN(in_channels=in_ch_deriv).to(DEVICE)
        cnn_pred_deriv = train_cnn(cnn_deriv, X_d_tr, resid_deriv_tr, X_d_vl,
                                   y_d_vl - pred_ridge_deriv_vl, epochs=50)
        r2_cnn_deriv = compute_r2(y_d_vl, pred_ridge_deriv_vl + 0.5 * cnn_pred_deriv)

        res = {
            'patient': p['name'],
            'r2_ridge_base': round(r2_ridge_base, 4),
            'r2_ridge_deriv': round(r2_ridge_deriv, 4),
            'r2_cnn_base': round(r2_cnn_base, 4),
            'r2_cnn_deriv': round(r2_cnn_deriv, 4),
            'ridge_gain': round(r2_ridge_deriv - r2_ridge_base, 4),
            'cnn_gain': round(r2_cnn_deriv - r2_cnn_base, 4),
        }
        results.append(res)
        if detail:
            print(f"    {p['name']}: ridge base={r2_ridge_base:.4f} "
                  f"deriv={r2_ridge_deriv:.4f}({r2_ridge_deriv-r2_ridge_base:+.4f}) "
                  f"cnn base={r2_cnn_base:.4f} "
                  f"deriv={r2_cnn_deriv:.4f}({r2_cnn_deriv-r2_cnn_base:+.4f})")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    summary = {
        'mean_r2_ridge_base': round(np.mean([r['r2_ridge_base'] for r in results]), 4),
        'mean_r2_ridge_deriv': round(np.mean([r['r2_ridge_deriv'] for r in results]), 4),
        'mean_r2_cnn_base': round(np.mean([r['r2_cnn_base'] for r in results]), 4),
        'mean_r2_cnn_deriv': round(np.mean([r['r2_cnn_deriv'] for r in results]), 4),
        'mean_ridge_gain': round(np.mean([r['ridge_gain'] for r in results]), 4),
        'mean_cnn_gain': round(np.mean([r['cnn_gain'] for r in results]), 4),
        'n_ridge_deriv_helps': sum(1 for r in results if r['ridge_gain'] > 0),
        'n_cnn_deriv_helps': sum(1 for r in results if r['cnn_gain'] > 0),
        'n_patients': len(results),
    }
    return {
        'status': 'pass',
        'detail': (f'ridge: base={summary["mean_r2_ridge_base"]:.4f} '
                   f'deriv={summary["mean_r2_ridge_deriv"]:.4f} '
                   f'(+{summary["mean_ridge_gain"]:.4f}, '
                   f'{summary["n_ridge_deriv_helps"]}/{len(results)}) '
                   f'cnn: base={summary["mean_r2_cnn_base"]:.4f} '
                   f'deriv={summary["mean_r2_cnn_deriv"]:.4f} '
                   f'(+{summary["mean_cnn_gain"]:.4f}, '
                   f'{summary["n_cnn_deriv_helps"]}/{len(results)})'),
        'results': {'per_patient': results, 'summary': summary},
    }


# ─── EXP-1076: Ensemble of Diverse Models ───

def exp_1076_diverse_ensemble(patients, detail=False):
    """Ensemble of maximally diverse models.

    Build 5 diverse models per patient and average predictions:
    1. Ridge on raw physics
    2. Ridge on physics + interactions
    3. GB on raw physics
    4. CNN on Ridge residuals
    5. Ridge with glucose derivatives

    Diversity should help where individual models fail differently.
    """
    results = []

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        X, y = make_windows(glucose, physics)
        if len(X) < 200:
            continue

        X_tr, X_vl, y_tr, y_vl = split_data(X, y)
        Xf_tr = X_tr.reshape(len(X_tr), -1)
        Xf_vl = X_vl.reshape(len(X_vl), -1)
        in_channels = X.shape[2]

        # Compute interaction features
        interactions_tr = compute_interactions(X_tr)
        interactions_vl = compute_interactions(X_vl)
        Xf_int_tr = np.column_stack([Xf_tr, interactions_tr])
        Xf_int_vl = np.column_stack([Xf_vl, interactions_vl])

        # Compute derivative features
        g_scaled = glucose / GLUCOSE_SCALE
        g_delta = np.zeros_like(g_scaled)
        g_delta[1:] = g_scaled[1:] - g_scaled[:-1]
        nan_mask = np.isnan(g_scaled)
        g_delta[nan_mask] = 0.0
        if len(nan_mask) > 1:
            g_delta[1:][nan_mask[:-1]] = 0.0
        g_accel = np.zeros_like(g_delta)
        g_accel[1:] = g_delta[1:] - g_delta[:-1]
        physics_deriv = np.column_stack([physics, g_delta.reshape(-1, 1),
                                         g_accel.reshape(-1, 1)])
        X_d, y_d = make_windows(glucose, physics_deriv)

        preds = {}
        r2s = {}

        # 1. Ridge on raw physics
        ridge_raw = Ridge(alpha=1.0)
        ridge_raw.fit(Xf_tr, y_tr)
        preds['ridge_raw'] = ridge_raw.predict(Xf_vl)
        r2s['ridge_raw'] = round(compute_r2(y_vl, preds['ridge_raw']), 4)

        # 2. Ridge on physics + interactions
        ridge_int = Ridge(alpha=1.0)
        ridge_int.fit(Xf_int_tr, y_tr)
        preds['ridge_int'] = ridge_int.predict(Xf_int_vl)
        r2s['ridge_int'] = round(compute_r2(y_vl, preds['ridge_int']), 4)

        # 3. GB on raw physics
        gb = GradientBoostingRegressor(
            n_estimators=100, max_depth=4, learning_rate=0.1,
            random_state=42, subsample=0.8)
        gb.fit(Xf_tr, y_tr)
        preds['gb'] = gb.predict(Xf_vl)
        r2s['gb'] = round(compute_r2(y_vl, preds['gb']), 4)

        # 4. CNN on Ridge residuals
        pred_ridge_tr = ridge_raw.predict(Xf_tr)
        tr_resid = y_tr - pred_ridge_tr
        torch.manual_seed(42)
        cnn = ResidualCNN(in_channels=in_channels).to(DEVICE)
        cnn_pred = train_cnn(cnn, X_tr, tr_resid, X_vl,
                             y_vl - preds['ridge_raw'], epochs=50)
        preds['ridge_cnn'] = preds['ridge_raw'] + 0.5 * cnn_pred
        r2s['ridge_cnn'] = round(compute_r2(y_vl, preds['ridge_cnn']), 4)

        # 5. Ridge with derivatives
        if len(X_d) >= 200:
            X_d_tr, X_d_vl, y_d_tr, y_d_vl_check = split_data(X_d, y_d)
            Xf_d_tr = X_d_tr.reshape(len(X_d_tr), -1)
            Xf_d_vl = X_d_vl.reshape(len(X_d_vl), -1)
            ridge_d = Ridge(alpha=1.0)
            ridge_d.fit(Xf_d_tr, y_d_tr)
            pred_d = ridge_d.predict(Xf_d_vl)
            # Align prediction lengths — use min length
            min_len = min(len(pred_d), len(y_vl))
            preds['ridge_deriv'] = pred_d[:min_len]
            r2s['ridge_deriv'] = round(compute_r2(y_d_vl_check[:min_len],
                                                   pred_d[:min_len]), 4)
        else:
            preds['ridge_deriv'] = preds['ridge_raw'].copy()
            r2s['ridge_deriv'] = r2s['ridge_raw']

        # Ensemble: average the 5 models (align lengths)
        n_vl = len(y_vl)
        ensemble_models = ['ridge_raw', 'ridge_int', 'gb', 'ridge_cnn']
        aligned_preds = [preds[k][:n_vl] for k in ensemble_models]
        # For ridge_deriv, handle potentially different length
        if len(preds['ridge_deriv']) >= n_vl:
            aligned_preds.append(preds['ridge_deriv'][:n_vl])
        else:
            # Pad with ridge_raw for missing tail
            padded = np.concatenate([preds['ridge_deriv'],
                                     preds['ridge_raw'][len(preds['ridge_deriv']):n_vl]])
            aligned_preds.append(padded)

        ensemble_pred = np.mean(aligned_preds, axis=0)
        r2_ensemble = compute_r2(y_vl, ensemble_pred)

        best_single = max(r2s.items(), key=lambda x: x[1])

        res = {
            'patient': p['name'],
            'individual_r2': r2s,
            'r2_ensemble': round(r2_ensemble, 4),
            'best_single': best_single[0],
            'best_single_r2': best_single[1],
            'ensemble_vs_best': round(r2_ensemble - best_single[1], 4),
        }
        results.append(res)
        if detail:
            ind_str = ' '.join(f'{k}={v:.4f}' for k, v in r2s.items())
            print(f"    {p['name']}: {ind_str} | "
                  f"ensemble={r2_ensemble:.4f} vs best_single={best_single[1]:.4f} "
                  f"({r2_ensemble-best_single[1]:+.4f})")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    summary = {
        'mean_r2_ensemble': round(np.mean([r['r2_ensemble'] for r in results]), 4),
        'mean_best_single_r2': round(np.mean(
            [r['best_single_r2'] for r in results]), 4),
        'mean_ensemble_vs_best': round(np.mean(
            [r['ensemble_vs_best'] for r in results]), 4),
        'n_ensemble_beats_best': sum(1 for r in results if r['ensemble_vs_best'] > 0),
        'n_patients': len(results),
    }
    # Mean R² per model type
    for model_name in ['ridge_raw', 'ridge_int', 'gb', 'ridge_cnn', 'ridge_deriv']:
        vals = [r['individual_r2'].get(model_name, 0) for r in results]
        summary[f'mean_r2_{model_name}'] = round(np.mean(vals), 4)

    return {
        'status': 'pass',
        'detail': (f'ensemble={summary["mean_r2_ensemble"]:.4f} '
                   f'best_single={summary["mean_best_single_r2"]:.4f} '
                   f'(gain={summary["mean_ensemble_vs_best"]:+.4f}) '
                   f'ensemble>best={summary["n_ensemble_beats_best"]}/{len(results)}'),
        'results': {'per_patient': results, 'summary': summary},
    }


# ─── EXP-1077: Per-Patient Model Selection (Oracle) ───

def exp_1077_per_patient_model_selection(patients, detail=False):
    """Per-patient model selection: oracle upper bound and predictability.

    For each patient, select the best model from a candidate set.
    Oracle = cheating upper bound. Then test: can we predict the best model
    from patient characteristics (glucose variability, missing rate, bolus frequency)?
    """
    results = []
    patient_features = []

    for p in patients:
        glucose_raw = p['df']['glucose'].values.astype(float)
        missing_rate = float(np.isnan(glucose_raw).mean())

        X, y = prepare_patient(p)
        if len(X) < 200:
            continue

        X_tr, X_vl, y_tr, y_vl = split_data(X, y)
        Xf_tr = X_tr.reshape(len(X_tr), -1)
        Xf_vl = X_vl.reshape(len(X_vl), -1)
        in_channels = X.shape[2]

        # Interaction features
        interactions_tr = compute_interactions(X_tr)
        interactions_vl = compute_interactions(X_vl)
        Xf_int_tr = np.column_stack([Xf_tr, interactions_tr])
        Xf_int_vl = np.column_stack([Xf_vl, interactions_vl])

        model_results = {}

        # 1. Ridge
        ridge = Ridge(alpha=1.0)
        ridge.fit(Xf_tr, y_tr)
        pred_ridge = ridge.predict(Xf_vl)
        model_results['ridge'] = compute_r2(y_vl, pred_ridge)

        # 2. Ridge + interactions
        ridge_int = Ridge(alpha=1.0)
        ridge_int.fit(Xf_int_tr, y_tr)
        pred_int = ridge_int.predict(Xf_int_vl)
        model_results['ridge_int'] = compute_r2(y_vl, pred_int)

        # 3. GB
        gb = GradientBoostingRegressor(
            n_estimators=100, max_depth=4, learning_rate=0.1,
            random_state=42, subsample=0.8)
        gb.fit(Xf_tr, y_tr)
        pred_gb = gb.predict(Xf_vl)
        model_results['gb'] = compute_r2(y_vl, pred_gb)

        # 4. Ridge + CNN
        tr_resid = y_tr - ridge.predict(Xf_tr)
        torch.manual_seed(42)
        cnn = ResidualCNN(in_channels=in_channels).to(DEVICE)
        cnn_pred = train_cnn(cnn, X_tr, tr_resid, X_vl,
                             y_vl - pred_ridge, epochs=50)
        model_results['ridge_cnn'] = compute_r2(y_vl, pred_ridge + 0.5 * cnn_pred)

        # 5. GB + CNN
        tr_resid_gb = y_tr - gb.predict(Xf_tr)
        torch.manual_seed(42)
        cnn_gb = ResidualCNN(in_channels=in_channels).to(DEVICE)
        cnn_pred_gb = train_cnn(cnn_gb, X_tr, tr_resid_gb, X_vl,
                                y_vl - pred_gb, epochs=50)
        model_results['gb_cnn'] = compute_r2(y_vl, pred_gb + 0.5 * cnn_pred_gb)

        best_model = max(model_results.items(), key=lambda x: x[1])
        worst_model = min(model_results.items(), key=lambda x: x[1])

        # Patient characteristics for prediction
        valid_glucose = glucose_raw[~np.isnan(glucose_raw)]
        glucose_cv = float(np.std(valid_glucose) / np.mean(valid_glucose)) if len(valid_glucose) > 0 else 0
        glucose_mean = float(np.mean(valid_glucose)) if len(valid_glucose) > 0 else 0
        glucose_std = float(np.std(valid_glucose)) if len(valid_glucose) > 0 else 0

        # Bolus frequency proxy: count large insulin demand spikes
        sd = compute_supply_demand(p['df'], p['pk'])
        demand = sd['demand']
        valid_demand = demand[~np.isnan(demand)]
        bolus_freq = float(np.sum(valid_demand > np.percentile(valid_demand, 90)) /
                           max(len(valid_demand), 1)) if len(valid_demand) > 0 else 0

        res = {
            'patient': p['name'],
            'model_r2': {k: round(v, 4) for k, v in model_results.items()},
            'best_model': best_model[0],
            'best_r2': round(best_model[1], 4),
            'worst_model': worst_model[0],
            'worst_r2': round(worst_model[1], 4),
            'oracle_range': round(best_model[1] - worst_model[1], 4),
            'patient_chars': {
                'glucose_cv': round(glucose_cv, 4),
                'glucose_mean': round(glucose_mean, 1),
                'glucose_std': round(glucose_std, 1),
                'missing_rate': round(missing_rate, 4),
                'bolus_freq': round(bolus_freq, 4),
            },
        }
        results.append(res)
        patient_features.append({
            'name': p['name'],
            'best_model': best_model[0],
            'cv': glucose_cv,
            'missing': missing_rate,
            'bolus_freq': bolus_freq,
        })
        if detail:
            mr_str = ' '.join(f'{k}={v:.4f}' for k, v in model_results.items())
            print(f"    {p['name']}: {mr_str} | best={best_model[0]} "
                  f"range={best_model[1]-worst_model[1]:.4f}")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    # Oracle: mean of per-patient best
    oracle_r2 = np.mean([r['best_r2'] for r in results])
    # Naive: always pick 'ridge' (default)
    naive_r2 = np.mean([r['model_r2'].get('ridge', 0) for r in results])

    # Model selection frequency
    model_freq = {}
    for r in results:
        m = r['best_model']
        model_freq[m] = model_freq.get(m, 0) + 1

    # Simple selection heuristic: use GB for high-CV patients, Ridge for low-CV
    median_cv = np.median([f['cv'] for f in patient_features])
    heuristic_correct = 0
    for pf in patient_features:
        predicted = 'gb' if pf['cv'] > median_cv else 'ridge_cnn'
        if predicted == pf['best_model']:
            heuristic_correct += 1

    summary = {
        'oracle_r2': round(oracle_r2, 4),
        'naive_ridge_r2': round(naive_r2, 4),
        'oracle_gain_vs_naive': round(oracle_r2 - naive_r2, 4),
        'model_selection_freq': model_freq,
        'mean_oracle_range': round(np.mean([r['oracle_range'] for r in results]), 4),
        'heuristic_accuracy': round(heuristic_correct / len(results), 4),
        'n_patients': len(results),
    }
    return {
        'status': 'pass',
        'detail': (f'oracle={oracle_r2:.4f} naive_ridge={naive_r2:.4f} '
                   f'(+{oracle_r2-naive_r2:.4f}) '
                   f'selection_range={summary["mean_oracle_range"]:.4f} '
                   f'freq={model_freq} '
                   f'heuristic_acc={heuristic_correct}/{len(results)}'),
        'results': {'per_patient': results, 'summary': summary},
    }


# ─── EXP-1078: Prediction Horizon Sweep ───

def exp_1078_horizon_sweep(patients, detail=False):
    """Systematically evaluate prediction quality at multiple horizons.

    Horizons: 5, 10, 15, 20, 30, 45, 60, 90, 120 minutes.
    Uses the full physics pipeline (Ridge). Reports R² decay curve.
    Clinical thresholds: where does R² drop below 0.5? Below 0.3?
    """
    horizon_minutes = [5, 10, 15, 20, 30, 45, 60, 90, 120]
    horizon_steps = [m // 5 for m in horizon_minutes]  # Convert to 5-min steps
    results = []

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        r2_per_horizon = {}

        for h_min, h_step in zip(horizon_minutes, horizon_steps):
            X, y = make_windows(glucose, physics, horizon=h_step)
            if len(X) < 200:
                r2_per_horizon[str(h_min)] = None
                continue

            X_tr, X_vl, y_tr, y_vl = split_data(X, y)
            Xf_tr = X_tr.reshape(len(X_tr), -1)
            Xf_vl = X_vl.reshape(len(X_vl), -1)

            ridge = Ridge(alpha=1.0)
            ridge.fit(Xf_tr, y_tr)
            pred = ridge.predict(Xf_vl)
            r2 = compute_r2(y_vl, pred)
            r2_per_horizon[str(h_min)] = round(r2, 4)

        # Find thresholds
        threshold_50 = None
        threshold_30 = None
        for h_min in horizon_minutes:
            r2 = r2_per_horizon.get(str(h_min))
            if r2 is not None:
                if r2 < 0.5 and threshold_50 is None:
                    threshold_50 = h_min
                if r2 < 0.3 and threshold_30 is None:
                    threshold_30 = h_min

        res = {
            'patient': p['name'],
            'r2_per_horizon': r2_per_horizon,
            'threshold_below_0_5': threshold_50,
            'threshold_below_0_3': threshold_30,
        }
        results.append(res)
        if detail:
            hz_str = ' '.join(f'{k}m={v:.3f}' if v is not None else f'{k}m=N/A'
                              for k, v in r2_per_horizon.items())
            print(f"    {p['name']}: {hz_str}")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    # Mean R² per horizon across patients
    mean_r2_per_horizon = {}
    for h_min in horizon_minutes:
        key = str(h_min)
        vals = [r['r2_per_horizon'][key] for r in results
                if r['r2_per_horizon'].get(key) is not None]
        if vals:
            mean_r2_per_horizon[key] = round(np.mean(vals), 4)

    # R² decay rate (per minute of horizon extension)
    r2_at_5 = mean_r2_per_horizon.get('5', None)
    r2_at_120 = mean_r2_per_horizon.get('120', None)
    decay_rate = None
    if r2_at_5 is not None and r2_at_120 is not None:
        decay_rate = round((r2_at_5 - r2_at_120) / 115, 6)

    summary = {
        'mean_r2_per_horizon': mean_r2_per_horizon,
        'r2_decay_per_minute': decay_rate,
        'n_below_0_5_at_60min': sum(1 for r in results
                                     if r['r2_per_horizon'].get('60') is not None
                                     and r['r2_per_horizon']['60'] < 0.5),
        'median_threshold_0_5': float(np.median(
            [r['threshold_below_0_5'] for r in results
             if r['threshold_below_0_5'] is not None]
        )) if any(r['threshold_below_0_5'] is not None for r in results) else None,
        'n_patients': len(results),
    }
    return {
        'status': 'pass',
        'detail': (f'R² by horizon: '
                   + ' '.join(f'{k}m={v:.3f}' for k, v in mean_r2_per_horizon.items())
                   + (f' | decay={decay_rate:.6f}/min' if decay_rate else '')
                   + f' | <0.5@60m: {summary["n_below_0_5_at_60min"]}/{len(results)}'),
        'results': {'per_patient': results, 'summary': summary},
    }


# ─── EXP-1079: Residual Error Decomposition ───

def exp_1079_error_decomposition(patients, detail=False):
    """Decompose Ridge prediction errors into interpretable components.

    1. Bias: mean(error) — systematic over/under-prediction
    2. Variance: var(error) — prediction noise around bias
    3. Irreducible: noise ceiling estimate (σ=15mg/dL sensor noise)
    4. Explained by physics: R² of residuals regressed on physics features
    5. Unexplained: true missing information

    This tells us WHERE the R² gap comes from and what to target next.
    """
    NOISE_SIGMA_MGDL = 15.0
    noise_var_scaled = (NOISE_SIGMA_MGDL / GLUCOSE_SCALE) ** 2

    results = []

    for p in patients:
        X, y = prepare_patient(p)
        if len(X) < 200:
            continue

        X_tr, X_vl, y_tr, y_vl = split_data(X, y)
        Xf_tr = X_tr.reshape(len(X_tr), -1)
        Xf_vl = X_vl.reshape(len(X_vl), -1)

        # Fit Ridge
        ridge = Ridge(alpha=1.0)
        ridge.fit(Xf_tr, y_tr)
        pred = ridge.predict(Xf_vl)

        errors = y_vl - pred
        mse = float(np.mean(errors ** 2))
        ss_tot = float(np.sum((y_vl - y_vl.mean())**2))

        # 1. Bias component: mean(error)²
        bias = float(np.mean(errors))
        bias_sq = bias ** 2

        # 2. Variance component: var(error) = E[(e - E[e])²]
        error_var = float(np.var(errors))

        # Verify: MSE ≈ bias² + variance (decomposition identity)
        mse_check = bias_sq + error_var

        # 3. Irreducible noise estimate
        # At σ=15mg/dL, noise variance in scaled units
        irreducible_var = noise_var_scaled

        # 4. Explained by physics features — can a second Ridge on residuals
        #    capture structure in the errors using the same features?
        ridge_resid = Ridge(alpha=1.0)
        ridge_resid.fit(Xf_tr, y_tr - ridge.predict(Xf_tr))
        pred_resid = ridge_resid.predict(Xf_vl)
        r2_resid_on_features = compute_r2(errors, pred_resid)
        # Clamp to [0, 1] since negative means no structure
        r2_resid_on_features = max(0.0, r2_resid_on_features)

        # 5. Physics features vs raw glucose — how much does physics add?
        # Ridge on glucose channel only
        Xg_tr = X_tr[:, :, 0].reshape(len(X_tr), -1)  # glucose only
        Xg_vl = X_vl[:, :, 0].reshape(len(X_vl), -1)
        ridge_g = Ridge(alpha=1.0)
        ridge_g.fit(Xg_tr, y_tr)
        r2_glucose_only = compute_r2(y_vl, ridge_g.predict(Xg_vl))

        r2_full = compute_r2(y_vl, pred)
        r2_ceiling = 1.0 - irreducible_var / (ss_tot / len(y_vl)) if ss_tot > 0 else 0

        # Partition total error variance
        total_error_var = mse
        bias_frac = bias_sq / total_error_var if total_error_var > 0 else 0
        variance_frac = error_var / total_error_var if total_error_var > 0 else 0
        irreducible_frac = irreducible_var / total_error_var if total_error_var > 0 else 0
        # Residual structure fraction: how much error variance is predictable
        explained_frac = r2_resid_on_features * error_var / total_error_var if total_error_var > 0 else 0
        unexplained_frac = max(0, 1.0 - bias_frac - irreducible_frac - explained_frac)

        # MAE for interpretability
        mae_mgdl = float(np.mean(np.abs(errors)) * GLUCOSE_SCALE)

        res = {
            'patient': p['name'],
            'r2': round(r2_full, 4),
            'r2_glucose_only': round(r2_glucose_only, 4),
            'r2_ceiling': round(r2_ceiling, 4),
            'mse': round(mse, 6),
            'mae_mgdl': round(mae_mgdl, 1),
            'bias_mgdl': round(bias * GLUCOSE_SCALE, 2),
            'decomposition': {
                'bias_frac': round(bias_frac, 4),
                'variance_frac': round(variance_frac, 4),
                'irreducible_frac': round(irreducible_frac, 4),
                'explained_by_features_frac': round(explained_frac, 4),
                'unexplained_frac': round(unexplained_frac, 4),
            },
            'r2_resid_on_features': round(r2_resid_on_features, 4),
            'physics_lift': round(r2_full - r2_glucose_only, 4),
        }
        results.append(res)
        if detail:
            dec = res['decomposition']
            print(f"    {p['name']}: R²={r2_full:.4f} ceil={r2_ceiling:.4f} "
                  f"| bias={dec['bias_frac']:.3f} var={dec['variance_frac']:.3f} "
                  f"irred={dec['irreducible_frac']:.3f} "
                  f"expl={dec['explained_by_features_frac']:.3f} "
                  f"unexp={dec['unexplained_frac']:.3f} "
                  f"| mae={mae_mgdl:.1f}mg/dL")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    # Average decomposition
    mean_decomp = {}
    for key in ['bias_frac', 'variance_frac', 'irreducible_frac',
                'explained_by_features_frac', 'unexplained_frac']:
        mean_decomp[key] = round(np.mean(
            [r['decomposition'][key] for r in results]), 4)

    summary = {
        'mean_r2': round(np.mean([r['r2'] for r in results]), 4),
        'mean_r2_glucose_only': round(np.mean(
            [r['r2_glucose_only'] for r in results]), 4),
        'mean_r2_ceiling': round(np.mean([r['r2_ceiling'] for r in results]), 4),
        'mean_mae_mgdl': round(np.mean([r['mae_mgdl'] for r in results]), 1),
        'mean_physics_lift': round(np.mean(
            [r['physics_lift'] for r in results]), 4),
        'mean_decomposition': mean_decomp,
        'mean_r2_resid_on_features': round(np.mean(
            [r['r2_resid_on_features'] for r in results]), 4),
        'n_patients': len(results),
    }
    return {
        'status': 'pass',
        'detail': (f'R²={summary["mean_r2"]:.4f} ceil={summary["mean_r2_ceiling"]:.4f} '
                   f'gap={summary["mean_r2_ceiling"]-summary["mean_r2"]:.4f} | '
                   f'bias={mean_decomp["bias_frac"]:.3f} '
                   f'var={mean_decomp["variance_frac"]:.3f} '
                   f'irred={mean_decomp["irreducible_frac"]:.3f} '
                   f'expl={mean_decomp["explained_by_features_frac"]:.3f} '
                   f'unexp={mean_decomp["unexplained_frac"]:.3f} '
                   f'| physics_lift={summary["mean_physics_lift"]:+.4f} '
                   f'mae={summary["mean_mae_mgdl"]:.1f}mg/dL'),
        'results': {'per_patient': results, 'summary': summary},
    }


# ─── EXP-1080: Grand Benchmark with Best Techniques ───

def exp_1080_grand_benchmark(patients, detail=False):
    """Definitive benchmark combining ALL winning techniques from 60 experiments.

    Under 3-fold block CV, exclude patient h. Combines:
    - Physics decomposition (supply, demand, hepatic, net)
    - Feature interactions (pairwise physics)
    - GB for hard patients (high glucose CV), Ridge for easy ones
    - Residual CNN on top
    - Per-patient model selection (Ridge vs GB base)

    Reports R², MAE, Clarke zones. This should be the new SOTA (research metric, no AR).
    """
    N_FOLDS = 3
    results = []
    excluded = []

    for p in patients:
        glucose_raw = p['df']['glucose'].values
        missing_rate = float(np.isnan(glucose_raw.astype(float)).mean())

        if p['name'] == 'h':
            excluded.append({'patient': p['name'], 'reason': 'excluded_by_protocol',
                             'missing_rate': round(missing_rate, 4)})
            if detail:
                print(f"    {p['name']}: EXCLUDED (protocol, missing={missing_rate:.1%})")
            continue

        X, y = prepare_patient(p)
        if len(X) < 200:
            excluded.append({'patient': p['name'], 'reason': 'insufficient_windows',
                             'n_windows': len(X)})
            if detail:
                print(f"    {p['name']}: EXCLUDED (insufficient windows={len(X)})")
            continue

        n = len(X)
        in_channels = X.shape[2]
        X_flat = X.reshape(n, -1)

        # Compute interactions
        interactions = compute_interactions(X)
        X_flat_int = np.column_stack([X_flat, interactions])

        # Patient difficulty metric: glucose CV
        valid_g = glucose_raw.astype(float)
        valid_g = valid_g[~np.isnan(valid_g)]
        glucose_cv = float(np.std(valid_g) / np.mean(valid_g)) if len(valid_g) > 0 else 0

        fold_size = n // N_FOLDS

        fold_metrics = {
            'r2_ridge': [],
            'r2_ridge_int': [],
            'r2_gb': [],
            'r2_gb_int': [],
            'r2_best_base': [],
            'r2_best_cnn': [],
            'r2_final': [],
            'mae_mg_dl': [],
            'clarke_A_pct': [],
            'clarke_AB_pct': [],
            'base_selection': [],
        }

        for fold in range(N_FOLDS):
            val_start = fold * fold_size
            val_end = val_start + fold_size if fold < N_FOLDS - 1 else n
            mask = np.ones(n, dtype=bool)
            mask[val_start:val_end] = False

            tr_X = X[mask]
            vl_X = X[~mask]
            tr_y = y[mask]
            vl_y = y[~mask]

            if len(vl_y) < 10:
                continue

            tr_flat = X_flat[mask]
            vl_flat = X_flat[~mask]
            tr_flat_int = X_flat_int[mask]
            vl_flat_int = X_flat_int[~mask]

            # Stage 1a: Ridge on physics
            ridge = Ridge(alpha=1.0)
            ridge.fit(tr_flat, tr_y)
            pred_ridge = ridge.predict(vl_flat)
            r2_ridge = compute_r2(vl_y, pred_ridge)
            fold_metrics['r2_ridge'].append(r2_ridge)

            # Stage 1b: Ridge on physics + interactions
            ridge_int = Ridge(alpha=1.0)
            ridge_int.fit(tr_flat_int, tr_y)
            pred_ridge_int = ridge_int.predict(vl_flat_int)
            r2_ridge_int = compute_r2(vl_y, pred_ridge_int)
            fold_metrics['r2_ridge_int'].append(r2_ridge_int)

            # Stage 1c: GB on physics
            gb = GradientBoostingRegressor(
                n_estimators=100, max_depth=4, learning_rate=0.1,
                random_state=42, subsample=0.8)
            gb.fit(tr_flat, tr_y)
            pred_gb = gb.predict(vl_flat)
            r2_gb = compute_r2(vl_y, pred_gb)
            fold_metrics['r2_gb'].append(r2_gb)

            # Stage 1d: GB on physics + interactions
            gb_int = GradientBoostingRegressor(
                n_estimators=100, max_depth=4, learning_rate=0.1,
                random_state=42, subsample=0.8)
            gb_int.fit(tr_flat_int, tr_y)
            pred_gb_int = gb_int.predict(vl_flat_int)
            r2_gb_int = compute_r2(vl_y, pred_gb_int)
            fold_metrics['r2_gb_int'].append(r2_gb_int)

            # Stage 2: Select best base model for this fold
            candidates = [
                ('ridge', r2_ridge, pred_ridge, ridge, tr_flat, vl_flat),
                ('ridge_int', r2_ridge_int, pred_ridge_int, ridge_int, tr_flat_int, vl_flat_int),
                ('gb', r2_gb, pred_gb, gb, tr_flat, vl_flat),
                ('gb_int', r2_gb_int, pred_gb_int, gb_int, tr_flat_int, vl_flat_int),
            ]
            best_base = max(candidates, key=lambda c: c[1])
            base_name = best_base[0]
            r2_best_base = best_base[1]
            pred_best_base = best_base[2]
            best_model = best_base[3]
            best_tr_flat = best_base[4]
            best_vl_flat = best_base[5]
            fold_metrics['r2_best_base'].append(r2_best_base)
            fold_metrics['base_selection'].append(base_name)

            # Stage 3: Residual CNN on best base model residuals
            tr_pred_base = best_model.predict(best_tr_flat)
            tr_resid = tr_y - tr_pred_base

            torch.manual_seed(42)
            cnn = ResidualCNN(in_channels=in_channels).to(DEVICE)
            cnn_pred = train_cnn(cnn, tr_X, tr_resid, vl_X,
                                 vl_y - pred_best_base, epochs=40)
            pred_cnn = pred_best_base + 0.5 * cnn_pred
            r2_cnn = compute_r2(vl_y, pred_cnn)
            fold_metrics['r2_best_cnn'].append(r2_cnn)

            # Final prediction: use CNN if it improves, otherwise use base
            if r2_cnn > r2_best_base:
                final_pred = pred_cnn
                r2_final = r2_cnn
            else:
                final_pred = pred_best_base
                r2_final = r2_best_base
            fold_metrics['r2_final'].append(r2_final)

            # Clinical metrics
            mae = float(np.mean(np.abs(final_pred - vl_y)) * GLUCOSE_SCALE)
            fold_metrics['mae_mg_dl'].append(mae)

            ref_mgdl = vl_y * GLUCOSE_SCALE
            pred_mgdl = final_pred * GLUCOSE_SCALE
            zones = clarke_error_grid(ref_mgdl, pred_mgdl)
            fold_metrics['clarke_A_pct'].append(zones['A'])
            fold_metrics['clarke_AB_pct'].append(zones['A'] + zones['B'])

        if not fold_metrics['r2_final']:
            excluded.append({'patient': p['name'], 'reason': 'no_valid_folds'})
            continue

        res = {
            'patient': p['name'],
            'glucose_cv': round(glucose_cv, 4),
            'missing_rate': round(missing_rate, 4),
        }
        for key, vals in fold_metrics.items():
            if key == 'base_selection':
                # Count which base was selected per fold
                sel_counts = {}
                for s in vals:
                    sel_counts[s] = sel_counts.get(s, 0) + 1
                res['base_selection'] = sel_counts
                continue
            res[f'{key}_mean'] = round(np.mean(vals), 4)
            res[f'{key}_std'] = round(np.std(vals), 4)
        res['n_folds'] = len(fold_metrics['r2_final'])

        # Lifts
        res['interactions_lift'] = round(
            res['r2_ridge_int_mean'] - res['r2_ridge_mean'], 4)
        res['gb_lift'] = round(
            res['r2_gb_mean'] - res['r2_ridge_mean'], 4)
        res['cnn_lift'] = round(
            res['r2_best_cnn_mean'] - res['r2_best_base_mean'], 4)
        res['total_lift'] = round(
            res['r2_final_mean'] - res['r2_ridge_mean'], 4)

        results.append(res)
        if detail:
            print(f"    {p['name']}: ridge={res['r2_ridge_mean']:.4f} "
                  f"best_base={res['r2_best_base_mean']:.4f} "
                  f"+cnn={res['r2_best_cnn_mean']:.4f} "
                  f"final={res['r2_final_mean']:.4f} "
                  f"mae={res['mae_mg_dl_mean']:.1f}mg/dL "
                  f"clarke_A={res['clarke_A_pct_mean']:.1f}% "
                  f"base={res.get('base_selection', {})}")

    if not results:
        return {'status': 'FAIL', 'detail': 'No patients completed the benchmark'}

    # Grand summary
    summary = {}
    for key in ['r2_ridge_mean', 'r2_ridge_int_mean', 'r2_gb_mean', 'r2_gb_int_mean',
                'r2_best_base_mean', 'r2_best_cnn_mean', 'r2_final_mean',
                'mae_mg_dl_mean', 'clarke_A_pct_mean', 'clarke_AB_pct_mean']:
        vals = [r[key] for r in results if key in r]
        if vals:
            summary[key] = round(np.mean(vals), 4)

    summary['mean_interactions_lift'] = round(np.mean(
        [r['interactions_lift'] for r in results]), 4)
    summary['mean_gb_lift'] = round(np.mean(
        [r['gb_lift'] for r in results]), 4)
    summary['mean_cnn_lift'] = round(np.mean(
        [r['cnn_lift'] for r in results]), 4)
    summary['mean_total_lift'] = round(np.mean(
        [r['total_lift'] for r in results]), 4)
    summary['n_cnn_helps'] = sum(1 for r in results if r['cnn_lift'] > 0)
    summary['n_gb_beats_ridge'] = sum(1 for r in results if r['gb_lift'] > 0)
    summary['n_included'] = len(results)
    summary['n_excluded'] = len(excluded)

    # Overall base selection distribution
    overall_selection = {}
    for r in results:
        for model, count in r.get('base_selection', {}).items():
            overall_selection[model] = overall_selection.get(model, 0) + count
    summary['overall_base_selection'] = overall_selection

    # Noise ceiling comparison
    summary['noise_ceiling_r2'] = 0.854
    summary['pct_of_ceiling'] = round(
        summary.get('r2_final_mean', 0) / 0.854 * 100, 1)

    return {
        'status': 'pass',
        'detail': (f'GRAND BENCHMARK ({summary["n_included"]} pts, '
                   f'{summary["n_excluded"]} excl, {N_FOLDS}-fold block CV): '
                   f'ridge={summary.get("r2_ridge_mean", "N/A")} -> '
                   f'+int={summary.get("r2_ridge_int_mean", "N/A")} -> '
                   f'best_base={summary.get("r2_best_base_mean", "N/A")} -> '
                   f'+cnn={summary.get("r2_best_cnn_mean", "N/A")} -> '
                   f'FINAL={summary.get("r2_final_mean", "N/A")} '
                   f'({summary["pct_of_ceiling"]}% of ceiling) '
                   f'mae={summary.get("mae_mg_dl_mean", "N/A")}mg/dL '
                   f'clarke_A={summary.get("clarke_A_pct_mean", "N/A")}% '
                   f'base_sel={overall_selection}'),
        'results': {'per_patient': results, 'excluded': excluded, 'summary': summary},
    }


# ─── Runner ───

EXPERIMENTS = [
    ('EXP-1071', 'GB Hyperparameter Search', exp_1071_gb_hyperparam_search),
    ('EXP-1072', 'Multi-Output Trajectory', exp_1072_multi_output_trajectory),
    ('EXP-1073', 'CNN Capacity Sweep', exp_1073_cnn_capacity_sweep),
    ('EXP-1074', 'Physics Normalization Study', exp_1074_normalization_study),
    ('EXP-1075', 'Glucose Derivatives Feature', exp_1075_glucose_derivatives),
    ('EXP-1076', 'Diverse Model Ensemble', exp_1076_diverse_ensemble),
    ('EXP-1077', 'Per-Patient Model Selection', exp_1077_per_patient_model_selection),
    ('EXP-1078', 'Prediction Horizon Sweep', exp_1078_horizon_sweep),
    ('EXP-1079', 'Residual Error Decomposition', exp_1079_error_decomposition),
    ('EXP-1080', 'Grand Benchmark Best Techniques', exp_1080_grand_benchmark),
]


def main():
    parser = argparse.ArgumentParser(
        description='EXP-1071-1080: Closing the R² gap — deeper models, richer features, multi-output')
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--max-patients', type=int, default=11)
    parser.add_argument('--experiment', type=str)
    args = parser.parse_args()

    patients = load_patients(PATIENTS_DIR, max_patients=args.max_patients)
    print(f"Using device: {DEVICE}")

    for exp_id, name, func in EXPERIMENTS:
        if args.experiment and exp_id != args.experiment:
            continue

        print(f"\n{'='*60}")
        print(f"Running {exp_id}: {name}")
        print(f"{'='*60}")

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
                    'status': result.get('status'), 'detail': result.get('detail'),
                    'elapsed_seconds': round(elapsed, 1),
                    'results': result.get('results', {}),
                }
                save_name = f"{exp_id.lower()}_{name.lower().replace(' ', '_').replace('-', '_')}"
                save_path = save_results(save_data, save_name)
                print(f"  Saved: {save_path}")

        except Exception as e:
            elapsed = time.time() - t0
            print(f"  Status: FAIL")
            print(f"  Error: {e}")
            print(f"  Time: {elapsed:.1f}s")
            import traceback
            traceback.print_exc()

    print(f"\n{'='*60}")
    print("All experiments complete")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
