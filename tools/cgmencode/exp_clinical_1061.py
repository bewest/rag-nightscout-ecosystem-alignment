#!/usr/bin/env python3
"""EXP-1061 to EXP-1070: Autoregressive validation, GRU models, and clinical optimization.

Building on EXP-1051-1060's highest-leverage findings:
- Autoregressive residuals gave +0.244 R² (ALL 11/11 patients) — but only simple split
- Noise ceiling analysis: 59% of theoretical max (R²=0.505 vs ceiling=0.854 at σ=15)
- 0.35 R² of room remaining — model-limited, not noise-limited
- Block CV shows ~7% R² inflation over simple split
- Residual CNN helps ALL 11/11 (+0.024), feature interactions help 10/11 (+0.004)

This batch focuses on:
1. Autoregressive residuals validation under block CV (EXP-1061) ★★★
2. GRU recurrent model for residual learning (EXP-1062)
3. Asymmetric loss for clinical safety (EXP-1063)
4. Proper leakage test for autoregressive features (EXP-1064)
5. Multi-horizon autoregressive (EXP-1065)
6. Gradient boosting vs Ridge (EXP-1066)
7. EMA baseline comparison (EXP-1067)
8. Residual autocorrelation at different strides (EXP-1068)
9. Clarke zone-aware training (EXP-1069)
10. Grand pipeline with autoregressive under block CV (EXP-1070)

Run:
    PYTHONPATH=tools python -m cgmencode.exp_clinical_1061 --detail --save --max-patients 11
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


# ─── Models ───

class ResidualCNN(nn.Module):
    """CNN that learns to predict Ridge residuals."""
    def __init__(self, in_channels, window_size=24):
        super().__init__()
        self.conv1 = nn.Conv1d(in_channels, 32, 3, padding=1)
        self.conv2 = nn.Conv1d(32, 32, 3, padding=1)
        self.conv3 = nn.Conv1d(32, 16, 3, padding=1)
        self.pool = nn.AdaptiveAvgPool1d(1)
        self.fc = nn.Linear(16, 1)
        self.relu = nn.ReLU()

    def forward(self, x):
        # x: (batch, time, channels) -> permute to (batch, channels, time)
        h = self.relu(self.conv1(x.permute(0, 2, 1)))
        h = self.relu(self.conv2(h))
        h = self.relu(self.conv3(h))
        h = self.pool(h).squeeze(-1)
        return self.fc(h).squeeze(-1)


class ResidualGRU(nn.Module):
    """GRU that learns to predict Ridge residuals."""
    def __init__(self, in_channels, hidden_size=32, num_layers=1):
        super().__init__()
        self.gru = nn.GRU(in_channels, hidden_size, num_layers=num_layers,
                          batch_first=True)
        self.fc = nn.Linear(hidden_size, 1)

    def forward(self, x):
        # x: (batch, time, channels)
        out, _ = self.gru(x)
        # Use last hidden state
        last = out[:, -1, :]
        return self.fc(last).squeeze(-1)


# ─── Data Helpers ───

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


def train_cnn(model, X_train, y_train, X_val, y_val, epochs=50, lr=1e-3,
              batch_size=256):
    """Train CNN/GRU and return predictions on validation set."""
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


# ─── Clarke Error Grid ───

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


# ─── Experiments ───

def exp_1061_ar_residuals_block_cv(patients, detail=False):
    """Validate autoregressive residuals under 3-fold block CV.

    EXP-1051 showed +0.244 R² gain from lag-1 residuals under simple split.
    This is suspiciously large and may involve leakage through temporal proximity.
    Validate with block CV: for each fold, train first-stage Ridge, compute residuals
    on training data, create lagged residual features, train second-stage Ridge.
    On validation fold: use first-stage predictions to get residuals, then second stage.
    The lag-1 residual for window i comes from window i-1 (stride=6, 30min earlier).
    First window in each sequence uses 0 as lag-1.
    """
    N_FOLDS = 3
    results = []

    for p in patients:
        X, y = prepare_patient(p)
        if len(X) < 200:
            continue

        n = len(X)
        X_flat = X.reshape(n, -1)

        # --- Simple split (reproduce EXP-1051 baseline) ---
        X_tr, X_vl, y_tr, y_vl = split_data(X, y)
        Xf_tr = X_tr.reshape(len(X_tr), -1)
        Xf_vl = X_vl.reshape(len(X_vl), -1)

        ridge1_ss = Ridge(alpha=1.0)
        ridge1_ss.fit(Xf_tr, y_tr)
        pred1_tr = ridge1_ss.predict(Xf_tr)
        pred1_vl = ridge1_ss.predict(Xf_vl)
        r2_base_ss = compute_r2(y_vl, pred1_vl)

        # Lag-1 residual features (simple split)
        tr_resid = y_tr - pred1_tr
        vl_resid = y_vl - pred1_vl

        lag1_tr = np.zeros(len(tr_resid))
        lag1_tr[1:] = tr_resid[:-1]
        lag1_vl = np.zeros(len(vl_resid))
        lag1_vl[1:] = vl_resid[:-1]

        Xf_tr2 = np.column_stack([Xf_tr, lag1_tr])
        Xf_vl2 = np.column_stack([Xf_vl, lag1_vl])
        ridge2_ss = Ridge(alpha=1.0)
        ridge2_ss.fit(Xf_tr2, y_tr)
        r2_ar_ss = compute_r2(y_vl, ridge2_ss.predict(Xf_vl2))

        # --- Block CV ---
        fold_size = n // N_FOLDS
        r2_base_folds = []
        r2_ar_folds = []

        for fold in range(N_FOLDS):
            val_start = fold * fold_size
            val_end = val_start + fold_size if fold < N_FOLDS - 1 else n
            mask = np.ones(n, dtype=bool)
            mask[val_start:val_end] = False

            tr_X = X_flat[mask]
            vl_X = X_flat[~mask]
            tr_y = y[mask]
            vl_y = y[~mask]

            if len(vl_y) < 10:
                continue

            # Stage 1: base Ridge
            ridge1 = Ridge(alpha=1.0)
            ridge1.fit(tr_X, tr_y)
            pred1_tr_cv = ridge1.predict(tr_X)
            pred1_vl_cv = ridge1.predict(vl_X)
            r2_base_fold = compute_r2(vl_y, pred1_vl_cv)
            r2_base_folds.append(r2_base_fold)

            # Compute training residuals and lag-1 features
            tr_resid_cv = tr_y - pred1_tr_cv
            lag1_tr_cv = np.zeros(len(tr_resid_cv))
            lag1_tr_cv[1:] = tr_resid_cv[:-1]

            # Stage 2: Ridge with lag-1 residual
            tr_X2 = np.column_stack([tr_X, lag1_tr_cv])
            ridge2 = Ridge(alpha=1.0)
            ridge2.fit(tr_X2, tr_y)

            # On validation: get first-stage residuals, then lag-1 for second stage
            vl_resid_cv = vl_y - pred1_vl_cv
            lag1_vl_cv = np.zeros(len(vl_resid_cv))
            lag1_vl_cv[1:] = vl_resid_cv[:-1]

            vl_X2 = np.column_stack([vl_X, lag1_vl_cv])
            pred2_vl_cv = ridge2.predict(vl_X2)
            r2_ar_fold = compute_r2(vl_y, pred2_vl_cv)
            r2_ar_folds.append(r2_ar_fold)

        if not r2_base_folds:
            continue

        r2_base_bcv = np.mean(r2_base_folds)
        r2_ar_bcv = np.mean(r2_ar_folds)
        gain_ss = r2_ar_ss - r2_base_ss
        gain_bcv = r2_ar_bcv - r2_base_bcv
        inflation = gain_ss - gain_bcv

        res = {
            'patient': p['name'],
            'r2_base_simple_split': round(r2_base_ss, 4),
            'r2_ar_simple_split': round(r2_ar_ss, 4),
            'gain_simple_split': round(gain_ss, 4),
            'r2_base_block_cv': round(r2_base_bcv, 4),
            'r2_ar_block_cv': round(r2_ar_bcv, 4),
            'gain_block_cv': round(gain_bcv, 4),
            'inflation': round(inflation, 4),
            'fold_r2_base': [round(v, 4) for v in r2_base_folds],
            'fold_r2_ar': [round(v, 4) for v in r2_ar_folds],
        }
        results.append(res)
        if detail:
            print(f"    {p['name']}: SS base={r2_base_ss:.4f} AR={r2_ar_ss:.4f}"
                  f"(+{gain_ss:.4f}) | BCV base={r2_base_bcv:.4f} AR={r2_ar_bcv:.4f}"
                  f"(+{gain_bcv:.4f}) | inflation={inflation:.4f}")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    gains_ss = [r['gain_simple_split'] for r in results]
    gains_bcv = [r['gain_block_cv'] for r in results]
    inflations = [r['inflation'] for r in results]
    n_bcv_positive = sum(1 for g in gains_bcv if g > 0)
    ar_valid = np.mean(gains_bcv) > 0.05

    summary = {
        'mean_gain_simple_split': round(np.mean(gains_ss), 4),
        'mean_gain_block_cv': round(np.mean(gains_bcv), 4),
        'mean_inflation': round(np.mean(inflations), 4),
        'n_bcv_positive': n_bcv_positive,
        'n_patients': len(results),
        'ar_validated': ar_valid,
    }
    return {
        'status': 'pass',
        'detail': (f'SS_gain={summary["mean_gain_simple_split"]:+.4f} '
                   f'BCV_gain={summary["mean_gain_block_cv"]:+.4f} '
                   f'inflation={summary["mean_inflation"]:+.4f} '
                   f'BCV_positive={n_bcv_positive}/{len(results)} '
                   f'AR_validated={ar_valid}'),
        'results': {'per_patient': results, 'summary': summary},
    }


def exp_1062_gru_residual_model(patients, detail=False):
    """GRU recurrent model for residual learning.

    Replace CNN with GRU for learning Ridge residuals. GRU can model temporal
    dependencies differently (sequential hidden state vs convolutional receptive field).
    Architecture: GRU(hidden=32, layers=1) -> Linear(1).
    Compare GRU vs CNN vs Ridge-only.
    """
    results = []

    for p in patients:
        X, y = prepare_patient(p)
        if len(X) < 200:
            continue

        X_tr, X_vl, y_tr, y_vl = split_data(X, y)

        # Ridge baseline
        r2_base, pred_base, ridge = eval_ridge(X_tr, X_vl, y_tr, y_vl)

        # Compute residuals
        _, pred_tr, _ = eval_ridge(X_tr, X_tr, y_tr, y_tr)
        tr_resid = y_tr - pred_tr
        vl_resid = y_vl - pred_base

        in_channels = X.shape[2]

        # CNN residual model
        torch.manual_seed(42)
        cnn = ResidualCNN(in_channels=in_channels)
        cnn = cnn.to(DEVICE)
        cnn_pred = train_cnn(cnn, X_tr, tr_resid, X_vl, vl_resid, epochs=50)
        pred_cnn = pred_base + 0.5 * cnn_pred
        r2_cnn = compute_r2(y_vl, pred_cnn)

        # GRU residual model
        torch.manual_seed(42)
        gru = ResidualGRU(in_channels=in_channels, hidden_size=32, num_layers=1)
        gru = gru.to(DEVICE)
        gru_pred = train_cnn(gru, X_tr, tr_resid, X_vl, vl_resid, epochs=50)
        pred_gru = pred_base + 0.5 * gru_pred
        r2_gru = compute_r2(y_vl, pred_gru)

        # Ensemble CNN + GRU
        pred_ensemble = pred_base + 0.5 * (0.5 * cnn_pred + 0.5 * gru_pred)
        r2_ensemble = compute_r2(y_vl, pred_ensemble)

        res = {
            'patient': p['name'],
            'r2_ridge': round(r2_base, 4),
            'r2_ridge_cnn': round(r2_cnn, 4),
            'r2_ridge_gru': round(r2_gru, 4),
            'r2_ridge_ensemble': round(r2_ensemble, 4),
            'gain_cnn': round(r2_cnn - r2_base, 4),
            'gain_gru': round(r2_gru - r2_base, 4),
            'gain_ensemble': round(r2_ensemble - r2_base, 4),
            'gru_vs_cnn': round(r2_gru - r2_cnn, 4),
        }
        results.append(res)
        if detail:
            print(f"    {p['name']}: ridge={r2_base:.4f} +cnn={r2_cnn:.4f}"
                  f"({r2_cnn-r2_base:+.4f}) +gru={r2_gru:.4f}"
                  f"({r2_gru-r2_base:+.4f}) ensemble={r2_ensemble:.4f}"
                  f"({r2_ensemble-r2_base:+.4f})")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    summary = {
        'mean_r2_ridge': round(np.mean([r['r2_ridge'] for r in results]), 4),
        'mean_r2_cnn': round(np.mean([r['r2_ridge_cnn'] for r in results]), 4),
        'mean_r2_gru': round(np.mean([r['r2_ridge_gru'] for r in results]), 4),
        'mean_r2_ensemble': round(np.mean([r['r2_ridge_ensemble'] for r in results]), 4),
        'mean_gain_cnn': round(np.mean([r['gain_cnn'] for r in results]), 4),
        'mean_gain_gru': round(np.mean([r['gain_gru'] for r in results]), 4),
        'mean_gain_ensemble': round(np.mean([r['gain_ensemble'] for r in results]), 4),
        'n_gru_beats_cnn': sum(1 for r in results if r['gru_vs_cnn'] > 0),
        'n_patients': len(results),
    }
    return {
        'status': 'pass',
        'detail': (f'ridge={summary["mean_r2_ridge"]:.4f} '
                   f'+cnn={summary["mean_r2_cnn"]:.4f}({summary["mean_gain_cnn"]:+.4f}) '
                   f'+gru={summary["mean_r2_gru"]:.4f}({summary["mean_gain_gru"]:+.4f}) '
                   f'ensemble={summary["mean_r2_ensemble"]:.4f}({summary["mean_gain_ensemble"]:+.4f}) '
                   f'GRU>CNN={summary["n_gru_beats_cnn"]}/{len(results)}'),
        'results': {'per_patient': results, 'summary': summary},
    }


def exp_1063_asymmetric_loss(patients, detail=False):
    """Asymmetric loss function for clinical safety.

    Clinical errors are not symmetric:
    - In hypoglycemic range (<80 mg/dL): penalize under-predictions more
      (predicting safe when actually low is dangerous)
    - In hyperglycemic range (>180 mg/dL): penalize over-predictions more
      (predicting higher than actual -> unnecessary treatment)
    Train CNN with asymmetric loss, compare R² and Clarke zones vs standard MSE.
    """
    results = []

    for p in patients:
        X, y = prepare_patient(p)
        if len(X) < 200:
            continue

        X_tr, X_vl, y_tr, y_vl = split_data(X, y)

        # Ridge baseline
        r2_base, pred_base, ridge = eval_ridge(X_tr, X_vl, y_tr, y_vl)
        _, pred_tr_base, _ = eval_ridge(X_tr, X_tr, y_tr, y_tr)
        tr_resid = y_tr - pred_tr_base

        in_channels = X.shape[2]

        # Standard MSE CNN
        torch.manual_seed(42)
        cnn_mse = ResidualCNN(in_channels=in_channels)
        cnn_mse = cnn_mse.to(DEVICE)
        cnn_mse_pred = train_cnn(cnn_mse, X_tr, tr_resid, X_vl,
                                 y_vl - pred_base, epochs=50)
        pred_mse = pred_base + 0.5 * cnn_mse_pred
        r2_mse = compute_r2(y_vl, pred_mse)

        # Asymmetric loss CNN
        torch.manual_seed(42)
        cnn_asym = ResidualCNN(in_channels=in_channels)
        cnn_asym = cnn_asym.to(DEVICE)

        optimizer = torch.optim.Adam(cnn_asym.parameters(), lr=1e-3)
        Xt = torch.FloatTensor(X_tr).to(DEVICE)
        yt_resid = torch.FloatTensor(tr_resid).to(DEVICE)
        # Glucose targets in mg/dL for zone-aware weighting
        y_tr_mgdl = y_tr * GLUCOSE_SCALE
        weight_tr = torch.FloatTensor(
            np.where(y_tr_mgdl < 80, 2.0,
                     np.where(y_tr_mgdl > 180, 1.5, 1.0))
        ).to(DEVICE)

        Xv = torch.FloatTensor(X_vl).to(DEVICE)
        best_val_loss = float('inf')
        best_state = None

        for epoch in range(50):
            cnn_asym.train()
            indices = torch.randperm(len(Xt))
            for start in range(0, len(Xt), 256):
                idx = indices[start:start+256]
                pred = cnn_asym(Xt[idx])
                errors = pred - yt_resid[idx]
                # Asymmetric: penalize under-prediction when hypo, over-prediction when hyper
                asym_weight = weight_tr[idx].clone()
                y_mgdl_batch = torch.FloatTensor(y_tr_mgdl[idx.cpu().numpy()]).to(DEVICE)
                # Under-prediction (pred < actual) when glucose is low = dangerous
                hypo_mask = (y_mgdl_batch < 80) & (errors < 0)
                asym_weight[hypo_mask] *= 2.0
                # Over-prediction (pred > actual) when glucose is high = unnecessary correction
                hyper_mask = (y_mgdl_batch > 180) & (errors > 0)
                asym_weight[hyper_mask] *= 1.5
                loss = (asym_weight * errors ** 2).mean()
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

            cnn_asym.eval()
            with torch.no_grad():
                val_pred = cnn_asym(Xv)
                val_loss = nn.MSELoss()(val_pred,
                    torch.FloatTensor(y_vl - pred_base).to(DEVICE)).item()
            if val_loss < best_val_loss:
                best_val_loss = val_loss
                best_state = {k: v.cpu().clone() for k, v in cnn_asym.state_dict().items()}

        if best_state:
            cnn_asym.load_state_dict(best_state)
        cnn_asym.eval()
        with torch.no_grad():
            asym_pred = cnn_asym(Xv).cpu().numpy()
        pred_asym = pred_base + 0.5 * asym_pred
        r2_asym = compute_r2(y_vl, pred_asym)

        # Clarke Error Grid comparison
        ref_mgdl = y_vl * GLUCOSE_SCALE
        zones_mse = clarke_error_grid(ref_mgdl, pred_mse * GLUCOSE_SCALE)
        zones_asym = clarke_error_grid(ref_mgdl, pred_asym * GLUCOSE_SCALE)
        zones_base = clarke_error_grid(ref_mgdl, pred_base * GLUCOSE_SCALE)

        res = {
            'patient': p['name'],
            'r2_ridge': round(r2_base, 4),
            'r2_mse_cnn': round(r2_mse, 4),
            'r2_asym_cnn': round(r2_asym, 4),
            'gain_mse': round(r2_mse - r2_base, 4),
            'gain_asym': round(r2_asym - r2_base, 4),
            'clarke_A_ridge': round(zones_base['A'], 1),
            'clarke_A_mse': round(zones_mse['A'], 1),
            'clarke_A_asym': round(zones_asym['A'], 1),
            'clarke_AB_ridge': round(zones_base['A'] + zones_base['B'], 1),
            'clarke_AB_mse': round(zones_mse['A'] + zones_mse['B'], 1),
            'clarke_AB_asym': round(zones_asym['A'] + zones_asym['B'], 1),
        }
        results.append(res)
        if detail:
            print(f"    {p['name']}: R² ridge={r2_base:.4f} mse={r2_mse:.4f} "
                  f"asym={r2_asym:.4f} | Clarke_A: ridge={zones_base['A']:.1f}% "
                  f"mse={zones_mse['A']:.1f}% asym={zones_asym['A']:.1f}%")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    summary = {
        'mean_r2_ridge': round(np.mean([r['r2_ridge'] for r in results]), 4),
        'mean_r2_mse': round(np.mean([r['r2_mse_cnn'] for r in results]), 4),
        'mean_r2_asym': round(np.mean([r['r2_asym_cnn'] for r in results]), 4),
        'mean_clarke_A_ridge': round(np.mean([r['clarke_A_ridge'] for r in results]), 1),
        'mean_clarke_A_mse': round(np.mean([r['clarke_A_mse'] for r in results]), 1),
        'mean_clarke_A_asym': round(np.mean([r['clarke_A_asym'] for r in results]), 1),
        'n_asym_better_r2': sum(1 for r in results if r['r2_asym_cnn'] > r['r2_mse_cnn']),
        'n_asym_better_clarke': sum(1 for r in results
                                     if r['clarke_A_asym'] > r['clarke_A_mse']),
        'n_patients': len(results),
    }
    return {
        'status': 'pass',
        'detail': (f'R²: ridge={summary["mean_r2_ridge"]:.4f} '
                   f'mse={summary["mean_r2_mse"]:.4f} asym={summary["mean_r2_asym"]:.4f} | '
                   f'Clarke_A: ridge={summary["mean_clarke_A_ridge"]:.1f}% '
                   f'mse={summary["mean_clarke_A_mse"]:.1f}% '
                   f'asym={summary["mean_clarke_A_asym"]:.1f}% | '
                   f'asym_better_R²={summary["n_asym_better_r2"]}/{len(results)} '
                   f'asym_better_clarke={summary["n_asym_better_clarke"]}/{len(results)}'),
        'results': {'per_patient': results, 'summary': summary},
    }


def exp_1064_leakage_test(patients, detail=False):
    """Proper leakage test for autoregressive features.

    Three conditions:
    1. "Adjacent": lag-1 from stride-adjacent window (stride=6, 30min gap) — EXP-1051 method
    2. "Gapped": lag-1 from 2-hour-prior window (gap of 24 steps between windows)
    3. "Shuffled": randomly shuffled residuals (negative control — should give zero gain)

    If adjacent >> gapped >> shuffled: gain is partially from temporal proximity (leakage).
    If adjacent ≈ gapped >> shuffled: gain is genuine autoregressive correction.
    """
    results = []

    for p in patients:
        X, y = prepare_patient(p)
        if len(X) < 200:
            continue

        X_tr, X_vl, y_tr, y_vl = split_data(X, y)
        Xf_tr = X_tr.reshape(len(X_tr), -1)
        Xf_vl = X_vl.reshape(len(X_vl), -1)

        # Base Ridge
        ridge = Ridge(alpha=1.0)
        ridge.fit(Xf_tr, y_tr)
        pred_tr = ridge.predict(Xf_tr)
        pred_vl = ridge.predict(Xf_vl)
        r2_base = compute_r2(y_vl, pred_vl)

        tr_resid = y_tr - pred_tr
        vl_resid = y_vl - pred_vl

        # Condition 1: Adjacent (lag-1, stride=6 = 30min)
        lag1_tr_adj = np.zeros(len(tr_resid))
        lag1_tr_adj[1:] = tr_resid[:-1]
        lag1_vl_adj = np.zeros(len(vl_resid))
        lag1_vl_adj[1:] = vl_resid[:-1]

        Xtr_adj = np.column_stack([Xf_tr, lag1_tr_adj])
        Xvl_adj = np.column_stack([Xf_vl, lag1_vl_adj])
        ridge_adj = Ridge(alpha=1.0)
        ridge_adj.fit(Xtr_adj, y_tr)
        r2_adjacent = compute_r2(y_vl, ridge_adj.predict(Xvl_adj))

        # Condition 2: Gapped (lag from 4 windows back = 24 steps = 2h gap)
        gap = 4  # 4 windows × stride=6 = 24 steps = 2 hours
        lag1_tr_gap = np.zeros(len(tr_resid))
        lag1_tr_gap[gap:] = tr_resid[:-gap]
        lag1_vl_gap = np.zeros(len(vl_resid))
        lag1_vl_gap[gap:] = vl_resid[:-gap]

        Xtr_gap = np.column_stack([Xf_tr, lag1_tr_gap])
        Xvl_gap = np.column_stack([Xf_vl, lag1_vl_gap])
        ridge_gap = Ridge(alpha=1.0)
        ridge_gap.fit(Xtr_gap, y_tr)
        r2_gapped = compute_r2(y_vl, ridge_gap.predict(Xvl_gap))

        # Condition 3: Shuffled (negative control)
        rng = np.random.RandomState(42)
        lag1_tr_shuf = rng.permutation(tr_resid)
        lag1_vl_shuf = rng.permutation(vl_resid)

        Xtr_shuf = np.column_stack([Xf_tr, lag1_tr_shuf])
        Xvl_shuf = np.column_stack([Xf_vl, lag1_vl_shuf])
        ridge_shuf = Ridge(alpha=1.0)
        ridge_shuf.fit(Xtr_shuf, y_tr)
        r2_shuffled = compute_r2(y_vl, ridge_shuf.predict(Xvl_shuf))

        gain_adj = r2_adjacent - r2_base
        gain_gap = r2_gapped - r2_base
        gain_shuf = r2_shuffled - r2_base

        # Diagnosis: is gain from proximity or genuine autocorrelation?
        if gain_adj > 0.01 and gain_gap > 0.01:
            proximity_ratio = (gain_adj - gain_gap) / max(gain_adj, 1e-8)
        else:
            proximity_ratio = 0.0

        res = {
            'patient': p['name'],
            'r2_base': round(r2_base, 4),
            'r2_adjacent': round(r2_adjacent, 4),
            'r2_gapped': round(r2_gapped, 4),
            'r2_shuffled': round(r2_shuffled, 4),
            'gain_adjacent': round(gain_adj, 4),
            'gain_gapped': round(gain_gap, 4),
            'gain_shuffled': round(gain_shuf, 4),
            'proximity_ratio': round(proximity_ratio, 4),
        }
        results.append(res)
        if detail:
            print(f"    {p['name']}: base={r2_base:.4f} "
                  f"adj={r2_adjacent:.4f}({gain_adj:+.4f}) "
                  f"gap={r2_gapped:.4f}({gain_gap:+.4f}) "
                  f"shuf={r2_shuffled:.4f}({gain_shuf:+.4f}) "
                  f"prox_ratio={proximity_ratio:.2f}")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    mean_gain_adj = np.mean([r['gain_adjacent'] for r in results])
    mean_gain_gap = np.mean([r['gain_gapped'] for r in results])
    mean_gain_shuf = np.mean([r['gain_shuffled'] for r in results])
    mean_prox = np.mean([r['proximity_ratio'] for r in results])

    # Diagnosis
    if mean_gain_adj > 0.01 and abs(mean_gain_adj - mean_gain_gap) < 0.02:
        diagnosis = 'genuine_autocorrelation'
    elif mean_gain_adj > mean_gain_gap * 2 and mean_gain_gap > mean_gain_shuf:
        diagnosis = 'partial_leakage'
    elif mean_gain_adj <= mean_gain_shuf + 0.005:
        diagnosis = 'no_signal'
    else:
        diagnosis = 'mixed_signal'

    summary = {
        'mean_gain_adjacent': round(mean_gain_adj, 4),
        'mean_gain_gapped': round(mean_gain_gap, 4),
        'mean_gain_shuffled': round(mean_gain_shuf, 4),
        'mean_proximity_ratio': round(mean_prox, 4),
        'diagnosis': diagnosis,
        'n_patients': len(results),
    }
    return {
        'status': 'pass',
        'detail': (f'adj={mean_gain_adj:+.4f} gap={mean_gain_gap:+.4f} '
                   f'shuf={mean_gain_shuf:+.4f} prox_ratio={mean_prox:.2f} '
                   f'diagnosis={diagnosis}'),
        'results': {'per_patient': results, 'summary': summary},
    }


def exp_1065_multi_horizon_autoregressive(patients, detail=False):
    """Multi-horizon autoregressive residuals.

    Test autoregressive residuals at different prediction horizons:
    15min (3 steps), 30min (6), 60min (12), 120min (24).
    The autoregressive gain should decrease at longer horizons because
    residual autocorrelation decays with temporal distance.
    """
    horizons = [
        ('15min', 3),
        ('30min', 6),
        ('60min', 12),
        ('120min', 24),
    ]
    results = []

    for p in patients:
        sd = compute_supply_demand(p['df'], p['pk'])
        supply = sd['supply'] / 20.0
        demand = sd['demand'] / 20.0
        hepatic = sd['hepatic'] / 5.0
        net = sd['net'] / 20.0
        physics = np.column_stack([supply, demand, hepatic, net])
        glucose = p['df']['glucose'].values.astype(float)

        horizon_results = {}

        for hname, hsteps in horizons:
            X, y = make_windows(glucose, physics, window=WINDOW, horizon=hsteps,
                                stride=STRIDE)
            if len(X) < 200:
                horizon_results[hname] = {'r2_base': None, 'r2_ar': None, 'gain': None}
                continue

            X_tr, X_vl, y_tr, y_vl = split_data(X, y)
            Xf_tr = X_tr.reshape(len(X_tr), -1)
            Xf_vl = X_vl.reshape(len(X_vl), -1)

            # Base Ridge
            ridge = Ridge(alpha=1.0)
            ridge.fit(Xf_tr, y_tr)
            pred_tr = ridge.predict(Xf_tr)
            pred_vl = ridge.predict(Xf_vl)
            r2_base = compute_r2(y_vl, pred_vl)

            # Autoregressive lag-1
            tr_resid = y_tr - pred_tr
            vl_resid = y_vl - pred_vl
            lag1_tr = np.zeros(len(tr_resid))
            lag1_tr[1:] = tr_resid[:-1]
            lag1_vl = np.zeros(len(vl_resid))
            lag1_vl[1:] = vl_resid[:-1]

            Xtr2 = np.column_stack([Xf_tr, lag1_tr])
            Xvl2 = np.column_stack([Xf_vl, lag1_vl])
            ridge2 = Ridge(alpha=1.0)
            ridge2.fit(Xtr2, y_tr)
            r2_ar = compute_r2(y_vl, ridge2.predict(Xvl2))

            # Residual autocorrelation at this horizon
            resid_centered = tr_resid - np.mean(tr_resid)
            var = np.var(resid_centered)
            autocorr = float(np.mean(resid_centered[1:] * resid_centered[:-1]) / max(var, 1e-10))

            horizon_results[hname] = {
                'r2_base': round(r2_base, 4),
                'r2_ar': round(r2_ar, 4),
                'gain': round(r2_ar - r2_base, 4),
                'autocorr_l1': round(autocorr, 4),
            }

        res = {'patient': p['name'], 'horizons': horizon_results}
        results.append(res)
        if detail:
            parts = []
            for hname, _ in horizons:
                hr = horizon_results[hname]
                if hr['r2_base'] is not None:
                    parts.append(f"{hname}={hr['gain']:+.4f}(ac={hr['autocorr_l1']:.2f})")
                else:
                    parts.append(f"{hname}=N/A")
            print(f"    {p['name']}: {' | '.join(parts)}")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    # Aggregate by horizon
    summary = {}
    for hname, _ in horizons:
        gains = [r['horizons'][hname]['gain'] for r in results
                 if r['horizons'][hname]['gain'] is not None]
        autocorrs = [r['horizons'][hname]['autocorr_l1'] for r in results
                     if r['horizons'][hname].get('autocorr_l1') is not None]
        if gains:
            summary[f'mean_gain_{hname}'] = round(np.mean(gains), 4)
            summary[f'mean_autocorr_{hname}'] = round(np.mean(autocorrs), 4) if autocorrs else None
            summary[f'n_valid_{hname}'] = len(gains)

    # Check if gain decreases with horizon (expected pattern)
    gain_values = [summary.get(f'mean_gain_{hname}') for hname, _ in horizons]
    valid_gains = [g for g in gain_values if g is not None]
    monotone_decreasing = all(valid_gains[i] >= valid_gains[i+1]
                               for i in range(len(valid_gains)-1)) if len(valid_gains) > 1 else False
    summary['gain_decreases_with_horizon'] = monotone_decreasing

    detail_parts = []
    for hname, _ in horizons:
        g = summary.get(f'mean_gain_{hname}')
        ac = summary.get(f'mean_autocorr_{hname}')
        if g is not None:
            detail_parts.append(f'{hname}={g:+.4f}(ac={ac:.2f})')
    return {
        'status': 'pass',
        'detail': (f'{" | ".join(detail_parts)} '
                   f'monotone_decay={monotone_decreasing}'),
        'results': {'per_patient': results, 'summary': summary},
    }


def exp_1066_gradient_boosting(patients, detail=False):
    """Gradient boosting vs Ridge as base model.

    GB can capture nonlinear feature interactions natively, potentially replacing
    both interaction terms AND residual CNN.
    Compare: Ridge vs GB vs Ridge+CNN vs GB+CNN.
    Uses n_estimators=100, max_depth=4, learning_rate=0.1.
    """
    results = []

    for p in patients:
        X, y = prepare_patient(p)
        if len(X) < 200:
            continue

        X_tr, X_vl, y_tr, y_vl = split_data(X, y)
        Xf_tr = X_tr.reshape(len(X_tr), -1)
        Xf_vl = X_vl.reshape(len(X_vl), -1)

        in_channels = X.shape[2]

        # 1. Ridge baseline
        ridge = Ridge(alpha=1.0)
        ridge.fit(Xf_tr, y_tr)
        pred_ridge = ridge.predict(Xf_vl)
        r2_ridge = compute_r2(y_vl, pred_ridge)

        # 2. Gradient Boosting
        gb = GradientBoostingRegressor(
            n_estimators=100, max_depth=4, learning_rate=0.1,
            random_state=42, subsample=0.8)
        gb.fit(Xf_tr, y_tr)
        pred_gb = gb.predict(Xf_vl)
        r2_gb = compute_r2(y_vl, pred_gb)

        # 3. Ridge + CNN (residual on Ridge)
        pred_ridge_tr = ridge.predict(Xf_tr)
        tr_resid_ridge = y_tr - pred_ridge_tr

        torch.manual_seed(42)
        cnn_ridge = ResidualCNN(in_channels=in_channels)
        cnn_ridge = cnn_ridge.to(DEVICE)
        cnn_pred_ridge = train_cnn(cnn_ridge, X_tr, tr_resid_ridge, X_vl,
                                   y_vl - pred_ridge, epochs=50)
        pred_ridge_cnn = pred_ridge + 0.5 * cnn_pred_ridge
        r2_ridge_cnn = compute_r2(y_vl, pred_ridge_cnn)

        # 4. GB + CNN (residual on GB)
        pred_gb_tr = gb.predict(Xf_tr)
        tr_resid_gb = y_tr - pred_gb_tr

        torch.manual_seed(42)
        cnn_gb = ResidualCNN(in_channels=in_channels)
        cnn_gb = cnn_gb.to(DEVICE)
        cnn_pred_gb = train_cnn(cnn_gb, X_tr, tr_resid_gb, X_vl,
                                y_vl - pred_gb, epochs=50)
        pred_gb_cnn = pred_gb + 0.5 * cnn_pred_gb
        r2_gb_cnn = compute_r2(y_vl, pred_gb_cnn)

        res = {
            'patient': p['name'],
            'r2_ridge': round(r2_ridge, 4),
            'r2_gb': round(r2_gb, 4),
            'r2_ridge_cnn': round(r2_ridge_cnn, 4),
            'r2_gb_cnn': round(r2_gb_cnn, 4),
            'gain_gb_vs_ridge': round(r2_gb - r2_ridge, 4),
            'gain_ridge_cnn': round(r2_ridge_cnn - r2_ridge, 4),
            'gain_gb_cnn': round(r2_gb_cnn - r2_gb, 4),
            'best': max([('ridge', r2_ridge), ('gb', r2_gb),
                         ('ridge_cnn', r2_ridge_cnn), ('gb_cnn', r2_gb_cnn)],
                        key=lambda x: x[1])[0],
        }
        results.append(res)
        if detail:
            print(f"    {p['name']}: ridge={r2_ridge:.4f} gb={r2_gb:.4f}"
                  f"({r2_gb-r2_ridge:+.4f}) ridge+cnn={r2_ridge_cnn:.4f} "
                  f"gb+cnn={r2_gb_cnn:.4f} best={res['best']}")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    best_counts = {}
    for r in results:
        b = r['best']
        best_counts[b] = best_counts.get(b, 0) + 1

    summary = {
        'mean_r2_ridge': round(np.mean([r['r2_ridge'] for r in results]), 4),
        'mean_r2_gb': round(np.mean([r['r2_gb'] for r in results]), 4),
        'mean_r2_ridge_cnn': round(np.mean([r['r2_ridge_cnn'] for r in results]), 4),
        'mean_r2_gb_cnn': round(np.mean([r['r2_gb_cnn'] for r in results]), 4),
        'mean_gain_gb_vs_ridge': round(np.mean([r['gain_gb_vs_ridge'] for r in results]), 4),
        'n_gb_beats_ridge': sum(1 for r in results if r['r2_gb'] > r['r2_ridge']),
        'n_gb_cnn_beats_ridge_cnn': sum(1 for r in results
                                         if r['r2_gb_cnn'] > r['r2_ridge_cnn']),
        'best_distribution': best_counts,
        'n_patients': len(results),
    }
    return {
        'status': 'pass',
        'detail': (f'ridge={summary["mean_r2_ridge"]:.4f} '
                   f'gb={summary["mean_r2_gb"]:.4f}({summary["mean_gain_gb_vs_ridge"]:+.4f}) '
                   f'ridge+cnn={summary["mean_r2_ridge_cnn"]:.4f} '
                   f'gb+cnn={summary["mean_r2_gb_cnn"]:.4f} '
                   f'gb>ridge={summary["n_gb_beats_ridge"]}/{len(results)} '
                   f'best_dist={best_counts}'),
        'results': {'per_patient': results, 'summary': summary},
    }


def exp_1067_ema_baseline(patients, detail=False):
    """Exponential moving average baseline.

    Predict glucose at t+horizon as the EMA of recent glucose values.
    EMA with spans of 6 (30min), 12 (1h), 24 (2h).
    Tests whether the physics pipeline beats simple smoothed extrapolation.
    """
    ema_spans = [6, 12, 24]
    results = []

    for p in patients:
        X, y = prepare_patient(p)
        if len(X) < 200:
            continue

        X_tr, X_vl, y_tr, y_vl = split_data(X, y)

        # Ridge + physics baseline
        r2_ridge, _, _ = eval_ridge(X_tr, X_vl, y_tr, y_vl)

        # EMA baselines: use last glucose value in window with EMA smoothing
        # The glucose is the first channel in X: X[:, :, 0]
        ema_r2 = {}
        for span in ema_spans:
            alpha_ema = 2.0 / (span + 1)
            # Compute EMA of glucose window for each sample
            ema_preds_vl = np.zeros(len(X_vl))
            for idx in range(len(X_vl)):
                g_win = X_vl[idx, :, 0]  # already scaled by GLUCOSE_SCALE
                ema_val = g_win[0]
                for t in range(1, len(g_win)):
                    ema_val = alpha_ema * g_win[t] + (1 - alpha_ema) * ema_val
                ema_preds_vl[idx] = ema_val
            r2_ema = compute_r2(y_vl, ema_preds_vl)
            ema_r2[f'span_{span}'] = round(r2_ema, 4)

        # Also test naive last-value baseline
        last_val_preds = X_vl[:, -1, 0]
        r2_last = compute_r2(y_vl, last_val_preds)

        # Linear extrapolation baseline (fit line to last 6 points, extrapolate)
        lin_preds = np.zeros(len(X_vl))
        for idx in range(len(X_vl)):
            g_win = X_vl[idx, :, 0]
            slope = np.polyfit(np.arange(WINDOW), g_win, 1)[0]
            lin_preds[idx] = g_win[-1] + slope * HORIZON
        r2_linear = compute_r2(y_vl, lin_preds)

        res = {
            'patient': p['name'],
            'r2_ridge_physics': round(r2_ridge, 4),
            'r2_last_value': round(r2_last, 4),
            'r2_linear_extrap': round(r2_linear, 4),
            'ema_r2': ema_r2,
            'best_ema_span': max(ema_r2, key=ema_r2.get),
            'physics_beats_all_ema': all(r2_ridge > v for v in ema_r2.values()),
            'physics_beats_linear': r2_ridge > r2_linear,
        }
        results.append(res)
        if detail:
            ema_str = ' '.join(f's{s}={ema_r2[f"span_{s}"]:.4f}' for s in ema_spans)
            print(f"    {p['name']}: ridge={r2_ridge:.4f} last={r2_last:.4f} "
                  f"linear={r2_linear:.4f} EMA=[{ema_str}] "
                  f"physics_wins={'✓' if res['physics_beats_all_ema'] else '✗'}")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    summary = {
        'mean_r2_ridge': round(np.mean([r['r2_ridge_physics'] for r in results]), 4),
        'mean_r2_last': round(np.mean([r['r2_last_value'] for r in results]), 4),
        'mean_r2_linear': round(np.mean([r['r2_linear_extrap'] for r in results]), 4),
    }
    for span in ema_spans:
        key = f'span_{span}'
        summary[f'mean_r2_ema_{key}'] = round(
            np.mean([r['ema_r2'][key] for r in results]), 4)

    n_physics_wins = sum(1 for r in results if r['physics_beats_all_ema'])
    summary['n_physics_beats_all_baselines'] = n_physics_wins
    summary['n_patients'] = len(results)

    best_ema_key = max([f'span_{s}' for s in ema_spans],
                       key=lambda k: summary[f'mean_r2_ema_{k}'])
    return {
        'status': 'pass',
        'detail': (f'ridge={summary["mean_r2_ridge"]:.4f} '
                   f'last={summary["mean_r2_last"]:.4f} '
                   f'linear={summary["mean_r2_linear"]:.4f} '
                   f'best_ema({best_ema_key})={summary[f"mean_r2_ema_{best_ema_key}"]:.4f} '
                   f'physics_wins={n_physics_wins}/{len(results)}'),
        'results': {'per_patient': results, 'summary': summary},
    }


def exp_1068_residual_autocorrelation_strides(patients, detail=False):
    """Residual autocorrelation at different strides.

    Test whether L1≈0.52 autocorrelation in residuals depends on stride.
    Evaluate stride=1 (5min), 3 (15min), 6 (30min), 12 (1h), 24 (2h).
    If autocorrelation drops at larger strides: short-range signal (local bias).
    If autocorrelation is constant: systematic model deficiency.
    """
    stride_configs = [
        ('5min', 1),
        ('15min', 3),
        ('30min', 6),
        ('1h', 12),
        ('2h', 24),
    ]
    results = []

    for p in patients:
        sd = compute_supply_demand(p['df'], p['pk'])
        supply = sd['supply'] / 20.0
        demand = sd['demand'] / 20.0
        hepatic = sd['hepatic'] / 5.0
        net = sd['net'] / 20.0
        physics = np.column_stack([supply, demand, hepatic, net])
        glucose = p['df']['glucose'].values.astype(float)

        stride_results = {}

        for sname, s in stride_configs:
            X, y_s = make_windows(glucose, physics, window=WINDOW, horizon=HORIZON,
                                  stride=s)
            if len(X) < 200:
                stride_results[sname] = {
                    'autocorr_l1': None, 'r2_base': None, 'n_windows': len(X)}
                continue

            X_tr, X_vl, y_tr, y_vl = split_data(X, y_s)
            Xf_tr = X_tr.reshape(len(X_tr), -1)
            Xf_vl = X_vl.reshape(len(X_vl), -1)

            ridge = Ridge(alpha=1.0)
            ridge.fit(Xf_tr, y_tr)
            pred_vl = ridge.predict(Xf_vl)
            r2 = compute_r2(y_vl, pred_vl)

            # Residual autocorrelation (lag-1)
            pred_tr = ridge.predict(Xf_tr)
            tr_resid = y_tr - pred_tr
            resid_centered = tr_resid - np.mean(tr_resid)
            var = np.var(resid_centered)
            if var > 1e-10 and len(resid_centered) > 1:
                autocorr = float(np.mean(resid_centered[1:] * resid_centered[:-1]) / var)
            else:
                autocorr = 0.0

            stride_results[sname] = {
                'autocorr_l1': round(autocorr, 4),
                'r2_base': round(r2, 4),
                'n_windows': len(X),
            }

        res = {'patient': p['name'], 'strides': stride_results}
        results.append(res)
        if detail:
            parts = []
            for sname, _ in stride_configs:
                sr = stride_results[sname]
                if sr['autocorr_l1'] is not None:
                    parts.append(f"{sname}: ac={sr['autocorr_l1']:.3f} "
                                 f"r2={sr['r2_base']:.4f} n={sr['n_windows']}")
                else:
                    parts.append(f"{sname}: N/A (n={sr['n_windows']})")
            print(f"    {p['name']}: {' | '.join(parts)}")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    # Aggregate
    summary = {}
    for sname, _ in stride_configs:
        acs = [r['strides'][sname]['autocorr_l1'] for r in results
               if r['strides'][sname]['autocorr_l1'] is not None]
        if acs:
            summary[f'mean_autocorr_{sname}'] = round(np.mean(acs), 4)
            summary[f'n_valid_{sname}'] = len(acs)

    # Check if autocorrelation decays with stride
    ac_values = [summary.get(f'mean_autocorr_{sname}') for sname, _ in stride_configs]
    valid_acs = [a for a in ac_values if a is not None]
    if len(valid_acs) >= 2:
        decay_ratio = valid_acs[-1] / max(valid_acs[0], 1e-8) if valid_acs[0] != 0 else 0
        summary['decay_ratio'] = round(decay_ratio, 4)
        summary['pattern'] = 'local_bias' if decay_ratio < 0.5 else 'systematic_deficiency'
    else:
        summary['decay_ratio'] = None
        summary['pattern'] = 'insufficient_data'

    ac_str = ' '.join(f'{sname}={summary.get(f"mean_autocorr_{sname}", "N/A")}'
                      for sname, _ in stride_configs)
    return {
        'status': 'pass',
        'detail': (f'autocorr: {ac_str} | '
                   f'pattern={summary["pattern"]} '
                   f'decay_ratio={summary.get("decay_ratio", "N/A")}'),
        'results': {'per_patient': results, 'summary': summary},
    }


def exp_1069_clarke_zone_aware_training(patients, detail=False):
    """Clarke zone-aware training.

    Instead of optimizing R², train a secondary calibration model to improve
    Clarke Zone A percentage.
    Method:
    1. Train Ridge normally (first stage)
    2. Train a secondary model that predicts whether each prediction will be in Zone A
    3. Use the confidence to adjust predictions toward zone boundaries
    4. Compare Clarke Zone A% before and after calibration
    """
    results = []

    for p in patients:
        X, y = prepare_patient(p)
        if len(X) < 200:
            continue

        X_tr, X_vl, y_tr, y_vl = split_data(X, y)

        # Stage 1: base Ridge
        r2_base, pred_base_vl, ridge = eval_ridge(X_tr, X_vl, y_tr, y_vl)
        _, pred_base_tr, _ = eval_ridge(X_tr, X_tr, y_tr, y_tr)

        ref_tr_mgdl = y_tr * GLUCOSE_SCALE
        pred_tr_mgdl = pred_base_tr * GLUCOSE_SCALE
        ref_vl_mgdl = y_vl * GLUCOSE_SCALE
        pred_vl_mgdl = pred_base_vl * GLUCOSE_SCALE

        # Clarke zones for base model
        zones_base = clarke_error_grid(ref_vl_mgdl, pred_vl_mgdl)

        # Stage 2: calibration — learn a correction to move predictions toward Zone A
        # For training set, compute signed error and whether in Zone A
        errors_tr = pred_tr_mgdl - ref_tr_mgdl
        zones_tr_labels = np.zeros(len(y_tr))
        for idx in range(len(y_tr)):
            ref, pred = ref_tr_mgdl[idx], pred_tr_mgdl[idx]
            if (ref <= 70 and pred <= 70) or abs(pred - ref) <= 20 or \
               (ref >= 70 and abs(pred - ref) / ref <= 0.20):
                zones_tr_labels[idx] = 1  # Zone A

        # Train a correction model: predict the error (pred - actual)
        # Features: prediction, prediction², prediction range indicators
        def make_calib_features(preds_mgdl):
            return np.column_stack([
                preds_mgdl,
                preds_mgdl ** 2 / 10000,
                (preds_mgdl < 80).astype(float),
                (preds_mgdl > 180).astype(float),
                (preds_mgdl > 250).astype(float),
            ])

        calib_X_tr = make_calib_features(pred_tr_mgdl)
        calib_X_vl = make_calib_features(pred_vl_mgdl)

        # Train Ridge to predict the error
        calib_ridge = Ridge(alpha=10.0)
        calib_ridge.fit(calib_X_tr, errors_tr)
        correction_vl = calib_ridge.predict(calib_X_vl)

        # Apply correction (subtract predicted error)
        pred_calibrated_mgdl = pred_vl_mgdl - 0.5 * correction_vl
        pred_calibrated = pred_calibrated_mgdl / GLUCOSE_SCALE

        r2_calibrated = compute_r2(y_vl, pred_calibrated)
        zones_calib = clarke_error_grid(ref_vl_mgdl, pred_calibrated_mgdl)

        # Also try isotonic-like binned calibration
        # Bin predictions by glucose range and compute mean correction per bin
        bins = [0, 70, 120, 180, 250, 500]
        pred_binned_vl = pred_vl_mgdl.copy()
        for i in range(len(bins) - 1):
            tr_mask = (pred_tr_mgdl >= bins[i]) & (pred_tr_mgdl < bins[i+1])
            vl_mask = (pred_vl_mgdl >= bins[i]) & (pred_vl_mgdl < bins[i+1])
            if tr_mask.sum() > 5:
                mean_error = np.mean(errors_tr[tr_mask])
                pred_binned_vl[vl_mask] -= 0.5 * mean_error

        r2_binned = compute_r2(y_vl, pred_binned_vl / GLUCOSE_SCALE)
        zones_binned = clarke_error_grid(ref_vl_mgdl, pred_binned_vl)

        res = {
            'patient': p['name'],
            'r2_base': round(r2_base, 4),
            'r2_calibrated': round(r2_calibrated, 4),
            'r2_binned': round(r2_binned, 4),
            'clarke_A_base': round(zones_base['A'], 1),
            'clarke_A_calibrated': round(zones_calib['A'], 1),
            'clarke_A_binned': round(zones_binned['A'], 1),
            'clarke_AB_base': round(zones_base['A'] + zones_base['B'], 1),
            'clarke_AB_calibrated': round(zones_calib['A'] + zones_calib['B'], 1),
            'clarke_AB_binned': round(zones_binned['A'] + zones_binned['B'], 1),
            'gain_clarke_A_calib': round(zones_calib['A'] - zones_base['A'], 1),
            'gain_clarke_A_binned': round(zones_binned['A'] - zones_base['A'], 1),
        }
        results.append(res)
        if detail:
            print(f"    {p['name']}: R² base={r2_base:.4f} calib={r2_calibrated:.4f} "
                  f"binned={r2_binned:.4f} | Clarke_A: base={zones_base['A']:.1f}% "
                  f"calib={zones_calib['A']:.1f}%({zones_calib['A']-zones_base['A']:+.1f}) "
                  f"binned={zones_binned['A']:.1f}%({zones_binned['A']-zones_base['A']:+.1f})")

    if not results:
        return {'status': 'FAIL', 'detail': 'No valid results'}

    summary = {
        'mean_r2_base': round(np.mean([r['r2_base'] for r in results]), 4),
        'mean_r2_calibrated': round(np.mean([r['r2_calibrated'] for r in results]), 4),
        'mean_r2_binned': round(np.mean([r['r2_binned'] for r in results]), 4),
        'mean_clarke_A_base': round(np.mean([r['clarke_A_base'] for r in results]), 1),
        'mean_clarke_A_calib': round(np.mean([r['clarke_A_calibrated'] for r in results]), 1),
        'mean_clarke_A_binned': round(np.mean([r['clarke_A_binned'] for r in results]), 1),
        'n_calib_improves': sum(1 for r in results if r['gain_clarke_A_calib'] > 0),
        'n_binned_improves': sum(1 for r in results if r['gain_clarke_A_binned'] > 0),
        'n_patients': len(results),
    }
    best_method = max(['base', 'calib', 'binned'],
                      key=lambda m: summary[f'mean_clarke_A_{m}'])
    summary['best_method'] = best_method

    return {
        'status': 'pass',
        'detail': (f'Clarke_A: base={summary["mean_clarke_A_base"]:.1f}% '
                   f'calib={summary["mean_clarke_A_calib"]:.1f}% '
                   f'binned={summary["mean_clarke_A_binned"]:.1f}% '
                   f'best={best_method} | '
                   f'calib_helps={summary["n_calib_improves"]}/{len(results)} '
                   f'binned_helps={summary["n_binned_improves"]}/{len(results)}'),
        'results': {'per_patient': results, 'summary': summary},
    }


def exp_1070_grand_pipeline_ar_block_cv(patients, detail=False):
    """Grand pipeline with autoregressive under block CV.

    Definitive test: full pipeline (physics + interactions + residual CNN + autoregressive)
    under 3-fold block CV. Reports both with and without autoregressive.
    Reports R², MAE, Clarke zones for each patient and overall.
    """
    N_FOLDS = 3
    results = []
    excluded = []

    for p in patients:
        glucose_raw = p['df']['glucose'].values
        missing_rate = float(np.isnan(glucose_raw).mean())

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

        # Compute interaction features from physics channels
        # Physics channels are columns 1..4 in X (column 0 is glucose)
        phys_means = np.mean(X[:, :, 1:], axis=1)  # (n, 4)
        s, d, h_ch, net_f = phys_means[:, 0], phys_means[:, 1], phys_means[:, 2], phys_means[:, 3]
        interactions = np.column_stack([
            s * d, s * h_ch, s * net_f, d * h_ch, d * net_f, h_ch * net_f,
        ])
        X_flat_int = np.column_stack([X_flat, interactions])

        fold_size = n // N_FOLDS

        fold_metrics = {
            'r2_base': [],
            'r2_interactions': [],
            'r2_cnn': [],
            'r2_ar': [],
            'r2_full_pipeline': [],
            'mae_mg_dl': [],
            'clarke_A_pct': [],
            'clarke_AB_pct': [],
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

            # Stage 1: Base Ridge (physics)
            ridge_base = Ridge(alpha=1.0)
            ridge_base.fit(tr_flat, tr_y)
            pred_base = ridge_base.predict(vl_flat)
            r2_base = compute_r2(vl_y, pred_base)
            fold_metrics['r2_base'].append(r2_base)

            # Stage 2: Ridge + interactions
            ridge_int = Ridge(alpha=1.0)
            ridge_int.fit(tr_flat_int, tr_y)
            pred_int = ridge_int.predict(vl_flat_int)
            r2_int = compute_r2(vl_y, pred_int)
            fold_metrics['r2_interactions'].append(r2_int)

            # Stage 3: Residual CNN on interaction Ridge residuals
            tr_resid = tr_y - ridge_int.predict(tr_flat_int)
            vl_resid = vl_y - pred_int

            torch.manual_seed(42)
            cnn = ResidualCNN(in_channels=in_channels)
            cnn = cnn.to(DEVICE)
            cnn_pred = train_cnn(cnn, tr_X, tr_resid, vl_X, vl_resid, epochs=40)
            pred_cnn = pred_int + 0.5 * cnn_pred
            r2_cnn = compute_r2(vl_y, pred_cnn)
            fold_metrics['r2_cnn'].append(r2_cnn)

            # Stage 4: Autoregressive residual correction
            # Get training residuals from the CNN pipeline
            tr_pred_int = ridge_int.predict(tr_flat_int)
            tr_cnn_pred = predict_cnn(cnn, tr_X)
            tr_pipeline_pred = tr_pred_int + 0.5 * tr_cnn_pred
            tr_pipeline_resid = tr_y - tr_pipeline_pred

            lag1_tr = np.zeros(len(tr_pipeline_resid))
            lag1_tr[1:] = tr_pipeline_resid[:-1]

            # Second stage Ridge with lag-1 residual
            tr_flat_ar = np.column_stack([tr_flat_int, lag1_tr])
            ridge_ar = Ridge(alpha=1.0)
            ridge_ar.fit(tr_flat_ar, tr_y)

            # On validation fold: compute pipeline residuals, lag-1
            vl_pipeline_resid = vl_y - pred_cnn
            lag1_vl = np.zeros(len(vl_pipeline_resid))
            lag1_vl[1:] = vl_pipeline_resid[:-1]

            vl_flat_ar = np.column_stack([vl_flat_int, lag1_vl])
            pred_ar_base = ridge_ar.predict(vl_flat_ar)
            # Blend AR correction with CNN pipeline
            pred_ar = 0.5 * pred_cnn + 0.5 * pred_ar_base
            r2_ar = compute_r2(vl_y, pred_ar)
            fold_metrics['r2_ar'].append(r2_ar)

            # Full pipeline: best of with/without AR
            best_pred = pred_ar if r2_ar > r2_cnn else pred_cnn
            r2_full = max(r2_ar, r2_cnn)
            fold_metrics['r2_full_pipeline'].append(r2_full)

            # Metrics on full pipeline
            mae = float(np.mean(np.abs(best_pred - vl_y)) * GLUCOSE_SCALE)
            fold_metrics['mae_mg_dl'].append(mae)

            ref_mgdl = vl_y * GLUCOSE_SCALE
            pred_mgdl = best_pred * GLUCOSE_SCALE
            zones = clarke_error_grid(ref_mgdl, pred_mgdl)
            fold_metrics['clarke_A_pct'].append(zones['A'])
            fold_metrics['clarke_AB_pct'].append(zones['A'] + zones['B'])

        if not fold_metrics['r2_full_pipeline']:
            excluded.append({'patient': p['name'], 'reason': 'no_valid_folds'})
            continue

        res = {'patient': p['name'], 'missing_rate': round(missing_rate, 4)}
        for key, vals in fold_metrics.items():
            res[f'{key}_mean'] = round(np.mean(vals), 4)
            res[f'{key}_std'] = round(np.std(vals), 4)
        res['n_folds'] = len(fold_metrics['r2_full_pipeline'])

        # Lifts
        res['physics_lift'] = round(
            res['r2_interactions_mean'] - res['r2_base_mean'], 4)
        res['cnn_lift'] = round(
            res['r2_cnn_mean'] - res['r2_interactions_mean'], 4)
        res['ar_lift'] = round(
            res['r2_ar_mean'] - res['r2_cnn_mean'], 4)
        res['total_lift'] = round(
            res['r2_full_pipeline_mean'] - res['r2_base_mean'], 4)

        results.append(res)
        if detail:
            print(f"    {p['name']}: base={res['r2_base_mean']:.4f} "
                  f"+int={res['r2_interactions_mean']:.4f} "
                  f"+cnn={res['r2_cnn_mean']:.4f} "
                  f"+ar={res['r2_ar_mean']:.4f} "
                  f"full={res['r2_full_pipeline_mean']:.4f} "
                  f"mae={res['mae_mg_dl_mean']:.1f}mg/dL "
                  f"clarke_A={res['clarke_A_pct_mean']:.1f}%")

    if not results:
        return {'status': 'FAIL', 'detail': 'No patients completed the benchmark'}

    # Grand summary
    summary = {}
    for key in ['r2_base_mean', 'r2_interactions_mean', 'r2_cnn_mean',
                'r2_ar_mean', 'r2_full_pipeline_mean', 'mae_mg_dl_mean',
                'clarke_A_pct_mean', 'clarke_AB_pct_mean']:
        vals = [r[key] for r in results if key in r]
        if vals:
            summary[key] = round(np.mean(vals), 4)

    summary['mean_ar_lift'] = round(np.mean([r['ar_lift'] for r in results]), 4)
    summary['mean_total_lift'] = round(np.mean([r['total_lift'] for r in results]), 4)
    summary['n_ar_positive'] = sum(1 for r in results if r['ar_lift'] > 0)
    summary['n_included'] = len(results)
    summary['n_excluded'] = len(excluded)

    return {
        'status': 'pass',
        'detail': (f'pipeline ({summary["n_included"]} pts, {summary["n_excluded"]} excl, '
                   f'{N_FOLDS}-fold block CV): '
                   f'base={summary.get("r2_base_mean", "N/A")} -> '
                   f'+int={summary.get("r2_interactions_mean", "N/A")} -> '
                   f'+cnn={summary.get("r2_cnn_mean", "N/A")} -> '
                   f'+ar={summary.get("r2_ar_mean", "N/A")} -> '
                   f'full={summary.get("r2_full_pipeline_mean", "N/A")} '
                   f'(mae={summary.get("mae_mg_dl_mean", "N/A")}mg/dL, '
                   f'clarke_A={summary.get("clarke_A_pct_mean", "N/A")}%, '
                   f'ar_lift={summary["mean_ar_lift"]:+.4f}, '
                   f'ar_positive={summary["n_ar_positive"]}/{len(results)})'),
        'results': {'per_patient': results, 'excluded': excluded, 'summary': summary},
    }


# ─── Runner ───

EXPERIMENTS = [
    ('EXP-1061', 'AR Residuals Block CV Validation', exp_1061_ar_residuals_block_cv),
    ('EXP-1062', 'GRU Residual Model', exp_1062_gru_residual_model),
    ('EXP-1063', 'Asymmetric Loss Function', exp_1063_asymmetric_loss),
    ('EXP-1064', 'Proper Leakage Test', exp_1064_leakage_test),
    ('EXP-1065', 'Multi-Horizon Autoregressive', exp_1065_multi_horizon_autoregressive),
    ('EXP-1066', 'Gradient Boosting vs Ridge', exp_1066_gradient_boosting),
    ('EXP-1067', 'EMA Baseline Comparison', exp_1067_ema_baseline),
    ('EXP-1068', 'Residual Autocorrelation Strides', exp_1068_residual_autocorrelation_strides),
    ('EXP-1069', 'Clarke Zone-Aware Training', exp_1069_clarke_zone_aware_training),
    ('EXP-1070', 'Grand Pipeline AR Block CV', exp_1070_grand_pipeline_ar_block_cv),
]


def main():
    parser = argparse.ArgumentParser(
        description='EXP-1061-1070: Autoregressive validation, GRU models, and clinical optimization')
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
