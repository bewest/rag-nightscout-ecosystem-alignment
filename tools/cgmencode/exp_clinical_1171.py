#!/usr/bin/env python3
"""EXP-1171 to EXP-1180: Genuine Causal Improvements.

Campaign status after 170 experiments:
- Validated leakage-free SOTA: R²=0.581 (XGBoost→LSTM pipeline)
- 5-fold CV: R²≈0.549
- CRITICAL: PK temporal lead was 100% leakage — now eliminated
- Proven causal techniques:
    XGBoost→LSTM residual pipeline: +0.038
    Combined features (deriv+time+dawn+interactions): +0.021
    PK momentum: +0.010 (10/11 wins)
    PK trajectory: +0.008 (8/11 wins)
    Physics decomposition: +0.010

This batch explores genuine improvement directions:
  EXP-1171: Enhanced Features + LSTM Pipeline (Careful) ★★★★★
  EXP-1172: Multi-Horizon Regularization ★★★★
  EXP-1173: Glucose Pattern Memory (Same-Time-Yesterday) ★★★
  EXP-1174: Cross-Patient Transfer Learning ★★★★
  EXP-1175: Glucose Encoding Variants ★★★
  EXP-1176: XGBoost Hyperparameter Deep Tune ★★★★
  EXP-1177: Residual Analysis — What's Left to Learn? ★★★
  EXP-1178: Glucose Variability Features ★★★
  EXP-1179: Insulin Stacking Detection ★★★
  EXP-1180: Definitive Causal Benchmark (5-Fold CV) ★★★★★

Run:
    PYTHONPATH=tools python -m cgmencode.exp_clinical_1171 --detail --save --max-patients 11
"""

import argparse
import json
import os
import sys
import time
import warnings

import numpy as np
from pathlib import Path

warnings.filterwarnings('ignore')

try:
    from cgmencode.exp_metabolic_flux import load_patients, save_results
    from cgmencode.exp_metabolic_441 import compute_supply_demand
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from cgmencode.exp_metabolic_flux import load_patients, save_results
    from cgmencode.exp_metabolic_441 import compute_supply_demand

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


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def prepare_patient_raw(p):
    sd = compute_supply_demand(p['df'], p['pk'])
    supply = sd['supply'] / 20.0
    demand = sd['demand'] / 20.0
    hepatic = sd['hepatic'] / 5.0
    net = sd['net'] / 20.0
    physics = np.column_stack([supply, demand, hepatic, net])
    glucose = p['df']['glucose'].values.astype(float)
    return glucose, physics


def compute_r2(y_true, y_pred):
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
    if ss_tot == 0:
        return 0.0
    return 1.0 - ss_res / ss_tot


def compute_mae(y_true, y_pred):
    return float(np.mean(np.abs(y_true - y_pred)))


def make_xgb(n_estimators=200, max_depth=3, learning_rate=0.08, **kwargs):
    if not XGB_AVAILABLE:
        from sklearn.ensemble import GradientBoostingRegressor
        return GradientBoostingRegressor(
            n_estimators=n_estimators, max_depth=max_depth,
            learning_rate=learning_rate, random_state=42)
    return xgb.XGBRegressor(
        n_estimators=n_estimators, max_depth=max_depth,
        learning_rate=learning_rate, tree_method='hist',
        device='cuda', random_state=42, verbosity=0, **kwargs)


def make_xgb_sota(**overrides):
    """Standard SOTA XGBoost configuration per spec."""
    params = dict(n_estimators=500, max_depth=4, learning_rate=0.05,
                  subsample=0.8, colsample_bytree=0.8)
    params.update(overrides)
    return make_xgb(**params)


def split_data(X, y, train_frac=0.8):
    n = len(X)
    split = int(n * train_frac)
    return X[:split], X[split:], y[:split], y[split:]


def split_3way(X, y, fracs=(0.6, 0.2, 0.2)):
    n = len(X)
    s1 = int(n * fracs[0])
    s2 = int(n * (fracs[0] + fracs[1]))
    return (X[:s1], X[s1:s2], X[s2:], y[:s1], y[s1:s2], y[s2:])


def get_hour(p, idx):
    """Get hour of day for a given index."""
    df = p['df']
    if 'date' in df.columns:
        try:
            ts = np.datetime64(df['date'].values[idx], 'ns')
            return int((ts.astype('datetime64[h]') - ts.astype('datetime64[D]')).astype(int))
        except Exception:
            pass
    if df.index.dtype == 'datetime64[ns]':
        try:
            ts = df.index[idx]
            return ts.hour
        except Exception:
            pass
    return (idx * 5 // 60) % 24


def compute_derivative_features(g_win):
    """Compute derivative features from a glucose window."""
    d1 = np.diff(g_win)
    d2 = np.diff(d1) if len(d1) > 1 else np.array([0.0])
    feats = [
        d1[-1] if len(d1) > 0 else 0,
        np.mean(d1[-6:]) if len(d1) >= 6 else np.mean(d1) if len(d1) > 0 else 0,
        np.mean(d1[-12:]) if len(d1) >= 12 else np.mean(d1) if len(d1) > 0 else 0,
        d2[-1] if len(d2) > 0 else 0,
        np.mean(d2[-6:]) if len(d2) >= 6 else np.mean(d2) if len(d2) > 0 else 0,
        np.average(d1[-6:], weights=np.exp(np.linspace(-1, 0, min(6, len(d1))))) if len(d1) > 0 else 0,
        np.std(g_win[-12:]) if len(g_win) >= 12 else np.std(g_win),
        np.std(g_win[-6:]) if len(g_win) >= 6 else np.std(g_win),
        np.max(np.abs(d1[-6:])) if len(d1) >= 6 else np.max(np.abs(d1)) if len(d1) > 0 else 0,
        np.sum(np.diff(np.sign(d1[-12:])) != 0) / 12.0 if len(d1) >= 12 else 0,
    ]
    return feats


def compute_time_features(hour):
    """Compute time-of-day + dawn features."""
    hour_rad = 2 * np.pi * hour / 24.0
    dawn_proximity = np.exp(-((hour - 5.0) ** 2) / (2 * 1.5 ** 2))
    dawn_ramp = max(0, min(1, (hour - 3) / 4.0)) if 3 <= hour <= 7 else 0.0
    post_dawn = max(0, min(1, (hour - 7) / 3.0)) if 7 <= hour <= 10 else 0.0
    cortisol = 0.5 * (1 + np.cos(2 * np.pi * (hour - 8) / 24))
    return [
        np.sin(hour_rad), np.cos(hour_rad),
        1.0 if 3 <= hour < 7 else 0.0,
        1.0 if 7 <= hour < 12 else 0.0,
        1.0 if 12 <= hour < 17 else 0.0,
        1.0 if 17 <= hour < 22 else 0.0,
        1.0 if hour >= 22 or hour < 3 else 0.0,
        dawn_proximity, dawn_ramp, post_dawn, cortisol,
    ]


def compute_interaction_features(g_win, pk_win):
    """Compute insulin-glucose interaction features."""
    iob = pk_win[:, 0]
    activity = pk_win[:, 1]
    cob = pk_win[:, 6]
    carb_act = pk_win[:, 7]
    g_last = g_win[-1]
    g_mean = np.mean(g_win)
    d1 = np.diff(g_win)
    g_trend = np.mean(d1[-6:]) if len(d1) >= 6 else np.mean(d1) if len(d1) > 0 else 0

    return [
        g_last * np.mean(iob),
        g_last * np.mean(cob),
        g_trend * np.mean(iob),
        g_trend * np.mean(activity),
        g_last * np.mean(activity),
        g_mean * np.mean(carb_act),
        np.mean(iob) * np.mean(cob),
        g_trend * np.mean(carb_act),
        np.mean(iob) / (np.mean(cob) + 1e-6),
        np.mean(activity) / (np.mean(carb_act) + 1e-6),
    ]


def compute_pk_momentum(pk_win, alpha=0.3):
    """Exponentially weighted momentum of PK channels."""
    n = len(pk_win)
    if n < 2:
        return np.zeros(pk_win.shape[1] if pk_win.ndim > 1 else 1)
    weights = np.exp(-alpha * np.arange(n)[::-1])
    weights /= weights.sum()
    pk_ema_slow = np.average(pk_win, axis=0, weights=weights)
    momentum = pk_win[-1] - pk_ema_slow
    return momentum


# ---------------------------------------------------------------------------
# Window builders
# ---------------------------------------------------------------------------

def build_base_windows(glucose, pk, physics, window=WINDOW, horizon=HORIZON,
                       stride=STRIDE):
    """Base windows with lag0 PK (no lead, no enhancements)."""
    g = glucose / GLUCOSE_SCALE
    n = len(g)
    X_list, y_list, g_cur_list = [], [], []

    for i in range(0, n - window - horizon, stride):
        g_win = g[i:i + window]
        if np.isnan(g_win).mean() > 0.3:
            continue
        g_win = np.nan_to_num(
            g_win, nan=np.nanmean(g_win) if np.any(~np.isnan(g_win)) else 0.4)

        pk_win = pk[i:i + window]
        if np.isnan(pk_win).any():
            pk_win = np.nan_to_num(pk_win, nan=0.0)

        p_win = physics[i:i + window]
        if np.isnan(p_win).any():
            p_win = np.nan_to_num(p_win, nan=0.0)

        y_val = g[i + window + horizon - 1]
        if np.isnan(y_val):
            continue

        g_current = g_win[-1]
        pk_mean = np.mean(pk_win, axis=0)
        pk_last = pk_win[-1]
        feat = np.concatenate([g_win, p_win.ravel(), pk_mean, pk_last])
        X_list.append(feat)
        y_list.append(y_val)
        g_cur_list.append(g_current)

    if len(X_list) == 0:
        return np.array([]).reshape(0, 1), np.array([]), np.array([])
    return np.array(X_list), np.array(y_list), np.array(g_cur_list)


def build_enhanced_features(p, glucose, physics, window=WINDOW, horizon=HORIZON,
                            stride=STRIDE, include_time=True, include_deriv=True,
                            include_interactions=True, include_pk_momentum=True):
    """Build features with all proven enhancements."""
    g = glucose / GLUCOSE_SCALE
    pk = p['pk']
    n = len(g)
    X_list, y_list, g_cur_list = [], [], []

    for i in range(0, n - window - horizon, stride):
        g_win = g[i:i + window]
        if np.isnan(g_win).mean() > 0.3:
            continue
        g_win = np.nan_to_num(
            g_win, nan=np.nanmean(g_win) if np.any(~np.isnan(g_win)) else 0.4)
        p_win = physics[i:i + window]
        if np.isnan(p_win).any():
            p_win = np.nan_to_num(p_win, nan=0.0)
        pk_win = pk[i:i + window]
        if np.isnan(pk_win).any():
            pk_win = np.nan_to_num(pk_win, nan=0.0)

        y_val = g[i + window + horizon - 1]
        if np.isnan(y_val):
            continue

        g_current = g_win[-1]

        supply = p_win[:, 0]
        demand = p_win[:, 1]
        hepatic = p_win[:, 2]
        net = p_win[:, 3]
        g_mean = np.mean(g_win)

        base = np.concatenate([g_win, p_win.ravel()])
        phys_inter = np.array([
            np.mean(supply * demand), np.mean(supply * g_mean),
            np.mean(demand * g_mean),
            np.mean(np.diff(net)) if len(net) > 1 else 0.0,
            np.mean(hepatic * supply),
        ])

        g_std = np.std(g_win)
        g_min, g_max = np.min(g_win), np.max(g_win)
        g_range = g_max - g_min
        g_cv = g_std / g_mean if g_mean > 0 else 0.0
        stats = np.array([g_mean, g_std, g_min, g_max, g_range, g_cv])

        pk_mean = np.mean(pk_win, axis=0)
        pk_last = pk_win[-1]

        parts = [base, phys_inter, stats, pk_mean, pk_last]

        if include_deriv:
            parts.append(np.array(compute_derivative_features(g_win)))

        if include_time:
            hour = get_hour(p, i + window - 1)
            parts.append(np.array(compute_time_features(hour)))

        if include_interactions:
            parts.append(np.array(compute_interaction_features(g_win, pk_win)))

        if include_pk_momentum:
            parts.append(compute_pk_momentum(pk_win, alpha=0.3))

        feat = np.concatenate(parts)
        X_list.append(feat)
        y_list.append(y_val)
        g_cur_list.append(g_current)

    if len(X_list) == 0:
        return np.array([]).reshape(0, 1), np.array([]), np.array([])
    return np.array(X_list), np.array(y_list), np.array(g_cur_list)


def train_eval_xgb(X, y, g_cur, xgb_factory=None):
    """Train XGBoost on delta-glucose, return test R² on absolute glucose."""
    if len(X) < 100:
        return 0.0
    X = np.nan_to_num(X, nan=0.0)
    y_dg = y - g_cur
    X_tr, X_te, y_tr, y_te = split_data(X, y_dg)
    g_cur_te = g_cur[len(X) - len(X_te):]

    m = xgb_factory() if xgb_factory else make_xgb(n_estimators=300, max_depth=3)
    m.fit(X_tr, y_tr)
    pred = m.predict(X_te) + g_cur_te
    y_abs = y_te + g_cur_te
    return compute_r2(y_abs, pred)


# ---------------------------------------------------------------------------
# LSTM helpers (lazy import)
# ---------------------------------------------------------------------------

def _get_device():
    import torch
    return torch.device('cuda' if torch.cuda.is_available() else 'cpu')


def _make_residual_lstm(hidden=32, n_layers=2, dropout=0.3):
    import torch
    import torch.nn as nn
    DEVICE = _get_device()

    class ResidualLSTM(nn.Module):
        def __init__(self):
            super().__init__()
            self.lstm = nn.LSTM(1, hidden, batch_first=True, num_layers=n_layers,
                               dropout=dropout if n_layers > 1 else 0.0)
            self.head = nn.Linear(hidden, 1)

        def forward(self, x):
            out, _ = self.lstm(x)
            return self.head(out[:, -1, :]).squeeze(-1)

    return ResidualLSTM().to(DEVICE)


def train_lstm_residual(residuals_val, residuals_test, seq_len=12, epochs=10,
                        hidden=32, dropout=0.3, patience=5):
    """Train LSTM on validation residuals, predict test corrections."""
    import torch
    import torch.nn as nn
    DEVICE = _get_device()

    if len(residuals_val) < seq_len + 10:
        return np.zeros_like(residuals_test)

    X_seq, y_seq = [], []
    for i in range(len(residuals_val) - seq_len):
        X_seq.append(residuals_val[i:i + seq_len])
        y_seq.append(residuals_val[i + seq_len])
    X_seq = torch.FloatTensor(np.array(X_seq)).unsqueeze(-1).to(DEVICE)
    y_seq = torch.FloatTensor(np.array(y_seq)).to(DEVICE)

    model = _make_residual_lstm(hidden=hidden, dropout=dropout)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)
    loss_fn = nn.MSELoss()

    best_loss = float('inf')
    wait = 0
    model.train()
    for epoch in range(epochs):
        opt.zero_grad()
        pred = model(X_seq)
        loss = loss_fn(pred, y_seq)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()

        cur_loss = loss.item()
        if cur_loss < best_loss - 1e-6:
            best_loss = cur_loss
            wait = 0
        else:
            wait += 1
            if wait >= patience:
                break

    model.eval()
    corrections = np.zeros(len(residuals_test))
    buffer = list(residuals_val[-seq_len:])
    with torch.no_grad():
        for i in range(len(residuals_test)):
            seq = torch.FloatTensor(np.array(buffer[-seq_len:])).unsqueeze(0).unsqueeze(-1).to(DEVICE)
            corrections[i] = model(seq).item()
            buffer.append(residuals_test[i])
    return corrections


# ---------------------------------------------------------------------------
# EXP-1171: Enhanced Features + LSTM Pipeline (Careful)
# ---------------------------------------------------------------------------

def exp_1171_enhanced_lstm_careful(patients, detail=False):
    """Separated pipeline: base XGB → LSTM correction, plus enhanced XGB branch.

    Previous EXP-1142 destabilized LSTM with enhanced features. This approach:
    1) Train base XGB (no enhancements) to produce structured residuals
    2) Train LSTM on those residuals with strong regularization (dropout=0.4)
    3) Train a separate enhanced XGB
    4) Weighted average: 0.6 * (base_XGB + LSTM) + 0.4 * enhanced_XGB
    """
    per_patient = {}
    scores_base, scores_enh, scores_pipeline, scores_combined = [], [], [], []

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']
        pk = p['pk']

        # Base windows (no enhancements)
        X_base, y_base, g_cur_base = build_base_windows(glucose, pk, physics)
        # Enhanced windows
        X_enh, y_enh, g_cur_enh = build_enhanced_features(
            p, glucose, physics, include_time=True, include_deriv=True,
            include_interactions=True, include_pk_momentum=True)

        if len(X_base) < 200 or len(X_enh) < 200:
            per_patient[pname] = {'base': 0, 'enhanced': 0, 'pipeline': 0, 'combined': 0}
            continue

        X_base = np.nan_to_num(X_base, nan=0.0)
        X_enh = np.nan_to_num(X_enh, nan=0.0)
        y_dg_base = y_base - g_cur_base
        y_dg_enh = y_enh - g_cur_enh

        # 3-way split for base pipeline
        X_tr_b, X_val_b, X_te_b, y_tr_b, y_val_b, y_te_b = split_3way(X_base, y_dg_base)
        g_cur_te_b = g_cur_base[len(X_base) - len(X_te_b):]
        g_cur_val_b = g_cur_base[len(X_tr_b):len(X_tr_b) + len(X_val_b)]
        y_abs_te_b = y_te_b + g_cur_te_b

        # Base XGB (no enhancements)
        m_base = make_xgb_sota()
        m_base.fit(X_tr_b, y_tr_b, eval_set=[(X_val_b, y_val_b)], verbose=False)
        pred_val_base = m_base.predict(X_val_b)
        pred_te_base = m_base.predict(X_te_b)
        r2_base = compute_r2(y_abs_te_b, pred_te_base + g_cur_te_b)

        # LSTM on base residuals with strong regularization
        resid_val = y_val_b - pred_val_base
        resid_te = y_te_b - pred_te_base
        corrections = train_lstm_residual(
            resid_val, resid_te, seq_len=12, epochs=30,
            hidden=32, dropout=0.4, patience=10)
        pred_pipeline = pred_te_base + corrections
        r2_pipeline = compute_r2(y_abs_te_b, pred_pipeline + g_cur_te_b)

        # Enhanced XGB (separate branch)
        X_tr_e, X_val_e, X_te_e, y_tr_e, y_val_e, y_te_e = split_3way(X_enh, y_dg_enh)
        g_cur_te_e = g_cur_enh[len(X_enh) - len(X_te_e):]
        y_abs_te_e = y_te_e + g_cur_te_e

        m_enh = make_xgb_sota()
        m_enh.fit(X_tr_e, y_tr_e, eval_set=[(X_val_e, y_val_e)], verbose=False)
        pred_te_enh = m_enh.predict(X_te_e)
        r2_enh = compute_r2(y_abs_te_e, pred_te_enh + g_cur_te_e)

        # Combined: weighted average (align test sets by using the shorter length)
        n_test = min(len(pred_pipeline), len(pred_te_enh))
        if n_test > 0:
            combined_pred = (0.6 * (pred_pipeline[-n_test:] + g_cur_te_b[-n_test:]) +
                             0.4 * (pred_te_enh[-n_test:] + g_cur_te_e[-n_test:]))
            y_combined_true = y_abs_te_b[-n_test:]
            r2_combined = compute_r2(y_combined_true, combined_pred)
        else:
            r2_combined = 0.0

        per_patient[pname] = {
            'base': r2_base, 'enhanced': r2_enh,
            'pipeline': r2_pipeline, 'combined': r2_combined,
        }
        scores_base.append(r2_base)
        scores_enh.append(r2_enh)
        scores_pipeline.append(r2_pipeline)
        scores_combined.append(r2_combined)

        if detail:
            print(f"  {pname}: base={r2_base:.4f} enh={r2_enh:.4f}"
                  f" pipeline={r2_pipeline:.4f} combined={r2_combined:.4f}"
                  f" Δ_pipe={r2_pipeline - r2_base:+.4f}"
                  f" Δ_comb={r2_combined - r2_base:+.4f}")

    mean_b = float(np.mean(scores_base)) if scores_base else 0
    mean_e = float(np.mean(scores_enh)) if scores_enh else 0
    mean_p = float(np.mean(scores_pipeline)) if scores_pipeline else 0
    mean_c = float(np.mean(scores_combined)) if scores_combined else 0
    wins = sum(1 for pp in per_patient.values()
               if pp.get('combined', 0) > pp.get('base', 0))

    return {
        'name': 'EXP-1171',
        'status': 'pass',
        'detail': (f"base={mean_b:.4f} enh={mean_e:.4f} pipeline={mean_p:.4f}"
                   f" combined={mean_c:.4f} Δ={mean_c-mean_b:+.4f}"
                   f" (wins={wins}/{len(patients)})"),
        'per_patient': per_patient,
        'results': {'base': mean_b, 'enhanced': mean_e,
                    'pipeline': mean_p, 'combined': mean_c},
    }


# ---------------------------------------------------------------------------
# EXP-1172: Multi-Horizon Regularization
# ---------------------------------------------------------------------------

def exp_1172_multi_horizon(patients, detail=False):
    """Train to predict 30min, 60min, 90min simultaneously — multi-horizon regularization.

    The constraint of predicting at multiple horizons regularizes the model and
    may improve the primary 60-min prediction.
    """
    per_patient = {}
    scores_single, scores_multi = [], []
    horizons = [6, 12, 18]  # 30min, 60min, 90min

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']
        pk = p['pk']
        g = glucose / GLUCOSE_SCALE
        n = len(g)

        X_list = []
        y_lists = {h: [] for h in horizons}
        g_cur_list = []

        max_horizon = max(horizons)
        for i in range(0, n - WINDOW - max_horizon, STRIDE):
            g_win = g[i:i + WINDOW]
            if np.isnan(g_win).mean() > 0.3:
                continue
            g_win = np.nan_to_num(
                g_win, nan=np.nanmean(g_win) if np.any(~np.isnan(g_win)) else 0.4)
            pk_win = pk[i:i + WINDOW]
            if np.isnan(pk_win).any():
                pk_win = np.nan_to_num(pk_win, nan=0.0)
            p_win = physics[i:i + WINDOW]
            if np.isnan(p_win).any():
                p_win = np.nan_to_num(p_win, nan=0.0)

            targets = {}
            valid = True
            for h in horizons:
                t = g[i + WINDOW + h - 1]
                if np.isnan(t):
                    valid = False
                    break
                targets[h] = t
            if not valid:
                continue

            g_current = g_win[-1]
            pk_mean = np.mean(pk_win, axis=0)
            pk_last = pk_win[-1]
            feat = np.concatenate([g_win, p_win.ravel(), pk_mean, pk_last])
            X_list.append(feat)
            for h in horizons:
                y_lists[h].append(targets[h])
            g_cur_list.append(g_current)

        if len(X_list) < 100:
            per_patient[pname] = {'single': 0, 'multi': 0}
            continue

        X = np.nan_to_num(np.array(X_list), nan=0.0)
        g_cur_arr = np.array(g_cur_list)

        # Single-horizon model (60min only, baseline)
        y_60 = np.array(y_lists[12])
        y_dg_60 = y_60 - g_cur_arr
        X_tr, X_te, y_tr, y_te = split_data(X, y_dg_60)
        g_cur_te = g_cur_arr[len(X) - len(X_te):]
        y_abs_te = y_te + g_cur_te

        m_single = make_xgb(n_estimators=300, max_depth=3)
        m_single.fit(X_tr, y_tr)
        pred_single = m_single.predict(X_te) + g_cur_te
        r2_single = compute_r2(y_abs_te, pred_single)

        # Multi-horizon models: train separate XGBoost per horizon, average for 60min
        preds_60 = []
        for h in horizons:
            y_h = np.array(y_lists[h])
            y_dg_h = y_h - g_cur_arr
            y_tr_h = y_dg_h[:len(X_tr)]
            y_te_h = y_dg_h[len(X_tr):]

            m_h = make_xgb(n_estimators=300, max_depth=3)
            m_h.fit(X_tr, y_tr_h)
            pred_h = m_h.predict(X_te) + g_cur_te
            preds_60.append(pred_h)

        # Average predictions for the 60-min target
        pred_multi = np.mean(preds_60, axis=0)
        r2_multi = compute_r2(y_abs_te, pred_multi)

        per_patient[pname] = {'single': r2_single, 'multi': r2_multi,
                              'delta': r2_multi - r2_single}
        scores_single.append(r2_single)
        scores_multi.append(r2_multi)

        if detail:
            print(f"  {pname}: single_60m={r2_single:.4f}"
                  f" multi_avg={r2_multi:.4f}"
                  f" Δ={r2_multi - r2_single:+.4f}")

    mean_s = float(np.mean(scores_single)) if scores_single else 0
    mean_m = float(np.mean(scores_multi)) if scores_multi else 0
    wins = sum(1 for pp in per_patient.values()
               if pp.get('multi', 0) > pp.get('single', 0))

    return {
        'name': 'EXP-1172',
        'status': 'pass',
        'detail': (f"single_60m={mean_s:.4f} multi_avg={mean_m:.4f}"
                   f" Δ={mean_m-mean_s:+.4f} (wins={wins}/{len(patients)})"),
        'per_patient': per_patient,
        'results': {'single': mean_s, 'multi': mean_m},
    }


# ---------------------------------------------------------------------------
# EXP-1173: Glucose Pattern Memory (Same-Time-Yesterday)
# ---------------------------------------------------------------------------

def exp_1173_pattern_memory(patients, detail=False):
    """Add same-time-of-day features from previous days as memory features."""
    per_patient = {}
    scores_base, scores_memory = [], []
    steps_per_day = 288  # 24h * 60 / 5

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']
        pk = p['pk']
        g = glucose / GLUCOSE_SCALE
        n = len(g)

        X_base_list, X_mem_list = [], []
        y_list, g_cur_list = [], []

        for i in range(0, n - WINDOW - HORIZON, STRIDE):
            g_win = g[i:i + WINDOW]
            if np.isnan(g_win).mean() > 0.3:
                continue
            g_win = np.nan_to_num(
                g_win, nan=np.nanmean(g_win) if np.any(~np.isnan(g_win)) else 0.4)
            pk_win = pk[i:i + WINDOW]
            if np.isnan(pk_win).any():
                pk_win = np.nan_to_num(pk_win, nan=0.0)
            p_win = physics[i:i + WINDOW]
            if np.isnan(p_win).any():
                p_win = np.nan_to_num(p_win, nan=0.0)

            y_val = g[i + WINDOW + HORIZON - 1]
            if np.isnan(y_val):
                continue

            g_current = g_win[-1]
            pk_mean = np.mean(pk_win, axis=0)
            pk_last = pk_win[-1]
            base_feat = np.concatenate([g_win, p_win.ravel(), pk_mean, pk_last])

            # Yesterday same time
            idx_yesterday = i + WINDOW - 1 - steps_per_day
            if idx_yesterday >= 0 and idx_yesterday < n:
                g_yest_val = g[idx_yesterday]
                g_yesterday = g_yest_val if not np.isnan(g_yest_val) else g_win.mean()
                g_yest_delta = g_current - g_yesterday
            else:
                g_yesterday = g_win.mean()
                g_yest_delta = 0.0

            # 2 days ago same time
            idx_2d = i + WINDOW - 1 - 2 * steps_per_day
            if idx_2d >= 0 and idx_2d < n:
                g_2d_val = g[idx_2d]
                g_2days = g_2d_val if not np.isnan(g_2d_val) else g_win.mean()
            else:
                g_2days = g_win.mean()

            # 7-day pattern: gather same-hour values over past 7 days
            same_hour_vals = []
            for d in range(1, 8):
                idx_d = i + WINDOW - 1 - d * steps_per_day
                if 0 <= idx_d < n:
                    v = g[idx_d]
                    if not np.isnan(v):
                        same_hour_vals.append(v)
            if len(same_hour_vals) >= 2:
                g_7d_mean = float(np.mean(same_hour_vals))
                g_7d_std = float(np.std(same_hour_vals))
            else:
                g_7d_mean = g_win.mean()
                g_7d_std = 0.0

            memory_feats = np.array([
                g_yesterday, g_yest_delta, g_2days,
                g_7d_mean, g_7d_std,
                g_current - g_7d_mean,  # deviation from 7-day pattern
            ])

            X_base_list.append(base_feat)
            X_mem_list.append(np.concatenate([base_feat, memory_feats]))
            y_list.append(y_val)
            g_cur_list.append(g_current)

        if len(X_base_list) < 100:
            per_patient[pname] = {'base': 0, 'memory': 0}
            continue

        X_base = np.nan_to_num(np.array(X_base_list), nan=0.0)
        X_mem = np.nan_to_num(np.array(X_mem_list), nan=0.0)
        y_arr = np.array(y_list)
        g_cur_arr = np.array(g_cur_list)
        y_dg = y_arr - g_cur_arr

        for X_feat, key, score_list in [
            (X_base, 'base', scores_base),
            (X_mem, 'memory', scores_memory),
        ]:
            X_tr, X_te, y_tr, y_te = split_data(X_feat, y_dg)
            g_te = g_cur_arr[len(X_feat) - len(X_te):]
            m = make_xgb(n_estimators=300, max_depth=3)
            m.fit(X_tr, y_tr)
            pred = m.predict(X_te) + g_te
            y_abs = y_te + g_te
            r2 = compute_r2(y_abs, pred)
            per_patient.setdefault(pname, {})[key] = r2
            score_list.append(r2)

        if detail:
            r = per_patient[pname]
            print(f"  {pname}: base={r['base']:.4f} memory={r['memory']:.4f}"
                  f" Δ={r['memory'] - r['base']:+.4f}")

    mean_b = float(np.mean(scores_base)) if scores_base else 0
    mean_m = float(np.mean(scores_memory)) if scores_memory else 0
    wins = sum(1 for pp in per_patient.values()
               if pp.get('memory', 0) > pp.get('base', 0))

    return {
        'name': 'EXP-1173',
        'status': 'pass',
        'detail': (f"base={mean_b:.4f} memory={mean_m:.4f}"
                   f" Δ={mean_m-mean_b:+.4f} (wins={wins}/{len(patients)})"),
        'per_patient': per_patient,
        'results': {'base': mean_b, 'memory': mean_m},
    }


# ---------------------------------------------------------------------------
# EXP-1174: Cross-Patient Transfer Learning
# ---------------------------------------------------------------------------

def exp_1174_cross_patient_transfer(patients, detail=False):
    """Train global XGB on all-but-one, use as feature for per-patient model."""
    per_patient = {}
    scores_local, scores_global, scores_ensemble = [], [], []

    # Build windows per patient
    patient_data = {}
    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']
        pk = p['pk']
        X, y, g_cur = build_base_windows(glucose, pk, physics)
        if len(X) >= 100:
            X = np.nan_to_num(X, nan=0.0)
            patient_data[pname] = {'X': X, 'y': y, 'g_cur': g_cur}

    if len(patient_data) < 3:
        return {
            'name': 'EXP-1174', 'status': 'skip',
            'detail': 'Not enough patients with sufficient data',
            'per_patient': {}, 'results': {},
        }

    for target_name in patient_data:
        td = patient_data[target_name]
        X_t, y_t, g_cur_t = td['X'], td['y'], td['g_cur']
        y_dg_t = y_t - g_cur_t

        # Build global training set from other patients
        X_global_parts, y_global_parts = [], []
        for other_name, other_data in patient_data.items():
            if other_name == target_name:
                continue
            y_dg_o = other_data['y'] - other_data['g_cur']
            X_global_parts.append(other_data['X'])
            y_global_parts.append(y_dg_o)

        X_global = np.concatenate(X_global_parts, axis=0)
        y_global = np.concatenate(y_global_parts, axis=0)

        # Train global model
        m_global = make_xgb(n_estimators=300, max_depth=3)
        m_global.fit(X_global, y_global)

        # Local model (standard split)
        X_tr, X_te, y_tr, y_te = split_data(X_t, y_dg_t)
        g_cur_te = g_cur_t[len(X_t) - len(X_te):]
        y_abs_te = y_te + g_cur_te

        m_local = make_xgb(n_estimators=300, max_depth=3)
        m_local.fit(X_tr, y_tr)
        pred_local = m_local.predict(X_te) + g_cur_te
        r2_local = compute_r2(y_abs_te, pred_local)

        # Global model on target test
        pred_global = m_global.predict(X_te) + g_cur_te
        r2_global = compute_r2(y_abs_te, pred_global)

        # Ensemble: use global prediction as additional feature
        global_pred_train = m_global.predict(X_tr).reshape(-1, 1)
        global_pred_test = m_global.predict(X_te).reshape(-1, 1)

        X_tr_aug = np.hstack([X_tr, global_pred_train])
        X_te_aug = np.hstack([X_te, global_pred_test])

        m_ensemble = make_xgb(n_estimators=300, max_depth=3)
        m_ensemble.fit(X_tr_aug, y_tr)
        pred_ensemble = m_ensemble.predict(X_te_aug) + g_cur_te
        r2_ensemble = compute_r2(y_abs_te, pred_ensemble)

        per_patient[target_name] = {
            'local': r2_local, 'global': r2_global, 'ensemble': r2_ensemble,
            'delta': r2_ensemble - r2_local,
        }
        scores_local.append(r2_local)
        scores_global.append(r2_global)
        scores_ensemble.append(r2_ensemble)

        if detail:
            print(f"  {target_name}: local={r2_local:.4f} global={r2_global:.4f}"
                  f" ensemble={r2_ensemble:.4f}"
                  f" Δ={r2_ensemble - r2_local:+.4f}")

    mean_l = float(np.mean(scores_local)) if scores_local else 0
    mean_g = float(np.mean(scores_global)) if scores_global else 0
    mean_e = float(np.mean(scores_ensemble)) if scores_ensemble else 0
    wins = sum(1 for pp in per_patient.values()
               if pp.get('ensemble', 0) > pp.get('local', 0))

    return {
        'name': 'EXP-1174',
        'status': 'pass',
        'detail': (f"local={mean_l:.4f} global={mean_g:.4f}"
                   f" ensemble={mean_e:.4f} Δ={mean_e-mean_l:+.4f}"
                   f" (wins={wins}/{len(patient_data)})"),
        'per_patient': per_patient,
        'results': {'local': mean_l, 'global': mean_g, 'ensemble': mean_e},
    }


# ---------------------------------------------------------------------------
# EXP-1175: Glucose Encoding Variants
# ---------------------------------------------------------------------------

def exp_1175_encoding_variants(patients, detail=False):
    """Test 4 different glucose window encodings to find the best representation.

    1. Raw scaled (current baseline)
    2. First-differenced (delta encoding)
    3. Normalized to window mean (relative encoding)
    4. Quantile-transformed (uniform distribution)
    """
    per_patient = {}
    scores = {'raw': [], 'delta': [], 'relative': [], 'quantile': []}

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']
        pk = p['pk']
        g = glucose / GLUCOSE_SCALE
        n = len(g)

        data_by_enc = {k: [] for k in scores}
        y_list, g_cur_list = [], []

        for i in range(0, n - WINDOW - HORIZON, STRIDE):
            g_win = g[i:i + WINDOW]
            if np.isnan(g_win).mean() > 0.3:
                continue
            g_win = np.nan_to_num(
                g_win, nan=np.nanmean(g_win) if np.any(~np.isnan(g_win)) else 0.4)
            pk_win = pk[i:i + WINDOW]
            if np.isnan(pk_win).any():
                pk_win = np.nan_to_num(pk_win, nan=0.0)
            p_win = physics[i:i + WINDOW]
            if np.isnan(p_win).any():
                p_win = np.nan_to_num(p_win, nan=0.0)

            y_val = g[i + WINDOW + HORIZON - 1]
            if np.isnan(y_val):
                continue

            g_current = g_win[-1]
            pk_mean = np.mean(pk_win, axis=0)
            pk_last = pk_win[-1]
            shared = np.concatenate([p_win.ravel(), pk_mean, pk_last])

            # 1. Raw
            data_by_enc['raw'].append(np.concatenate([g_win, shared]))

            # 2. Delta (first-differenced, pad first with 0)
            g_delta = np.diff(g_win, prepend=g_win[0])
            data_by_enc['delta'].append(np.concatenate([g_delta, shared]))

            # 3. Relative (normalize to window mean)
            g_mean = np.mean(g_win)
            g_rel = (g_win - g_mean) / (np.std(g_win) + 1e-8)
            data_by_enc['relative'].append(
                np.concatenate([g_rel, np.array([g_mean]), shared]))

            # 4. Quantile (rank-transform to uniform)
            g_sorted = np.sort(g_win)
            g_ranks = np.searchsorted(g_sorted, g_win).astype(float) / (WINDOW - 1)
            data_by_enc['quantile'].append(
                np.concatenate([g_ranks, np.array([g_mean, np.std(g_win)]), shared]))

            y_list.append(y_val)
            g_cur_list.append(g_current)

        if len(y_list) < 100:
            per_patient[pname] = {k: 0 for k in scores}
            continue

        y_arr = np.array(y_list)
        g_cur_arr = np.array(g_cur_list)
        y_dg = y_arr - g_cur_arr

        results_p = {}
        for enc_name in scores:
            X = np.nan_to_num(np.array(data_by_enc[enc_name]), nan=0.0)
            X_tr, X_te, y_tr, y_te = split_data(X, y_dg)
            g_te = g_cur_arr[len(X) - len(X_te):]
            m = make_xgb(n_estimators=300, max_depth=3)
            m.fit(X_tr, y_tr)
            pred = m.predict(X_te) + g_te
            y_abs = y_te + g_te
            r2 = compute_r2(y_abs, pred)
            results_p[enc_name] = r2
            scores[enc_name].append(r2)

        per_patient[pname] = results_p

        if detail:
            r = results_p
            best = max(r, key=r.get)
            print(f"  {pname}: raw={r['raw']:.4f} delta={r['delta']:.4f}"
                  f" rel={r['relative']:.4f} quant={r['quantile']:.4f}"
                  f" best={best}")

    means = {k: float(np.mean(v)) if v else 0 for k, v in scores.items()}
    best_enc = max(means, key=means.get) if means else 'raw'

    return {
        'name': 'EXP-1175',
        'status': 'pass',
        'detail': (f"raw={means['raw']:.4f} delta={means['delta']:.4f}"
                   f" relative={means['relative']:.4f}"
                   f" quantile={means['quantile']:.4f}"
                   f" best={best_enc}({means[best_enc]:.4f})"),
        'per_patient': per_patient,
        'results': means,
    }


# ---------------------------------------------------------------------------
# EXP-1176: XGBoost Hyperparameter Deep Tune
# ---------------------------------------------------------------------------

def exp_1176_hyperparam_tune(patients, detail=False):
    """Systematic hyperparameter tuning for XGBoost beyond defaults."""
    per_patient = {}
    scores_default, scores_tuned = [], []

    depths = [3, 4, 5, 6, 8]
    lrs = [0.01, 0.03, 0.05, 0.1]
    n_ests = [200, 500, 1000]

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']
        pk = p['pk']

        X, y, g_cur = build_base_windows(glucose, pk, physics)
        if len(X) < 200:
            per_patient[pname] = {'default': 0, 'tuned': 0, 'best_params': {}}
            continue

        X = np.nan_to_num(X, nan=0.0)
        y_dg = y - g_cur

        # 3-way split: train/val/test
        X_tr, X_val, X_te, y_tr, y_val, y_te = split_3way(X, y_dg)
        g_cur_te = g_cur[len(X) - len(X_te):]
        y_abs_te = y_te + g_cur_te

        # Default
        m_def = make_xgb(n_estimators=300, max_depth=3)
        m_def.fit(X_tr, y_tr)
        pred_def = m_def.predict(X_te) + g_cur_te
        r2_default = compute_r2(y_abs_te, pred_def)

        # Grid search on validation set
        best_val_r2 = -999
        best_params = {'max_depth': 3, 'learning_rate': 0.08, 'n_estimators': 200}

        g_cur_val = g_cur[len(X_tr):len(X_tr) + len(X_val)]
        y_abs_val = y_val + g_cur_val

        for depth in depths:
            for lr in lrs:
                for n_est in n_ests:
                    m = make_xgb(n_estimators=n_est, max_depth=depth,
                                 learning_rate=lr, subsample=0.8,
                                 colsample_bytree=0.8)
                    m.fit(X_tr, y_tr)
                    pred_val = m.predict(X_val) + g_cur_val
                    val_r2 = compute_r2(y_abs_val, pred_val)
                    if val_r2 > best_val_r2:
                        best_val_r2 = val_r2
                        best_params = {'max_depth': depth,
                                       'learning_rate': lr,
                                       'n_estimators': n_est}

        # Retrain with best params on train+val, evaluate on test
        X_tr_full = np.concatenate([X_tr, X_val], axis=0)
        y_tr_full = np.concatenate([y_tr, y_val])

        m_tuned = make_xgb(**best_params, subsample=0.8, colsample_bytree=0.8)
        m_tuned.fit(X_tr_full, y_tr_full)
        pred_tuned = m_tuned.predict(X_te) + g_cur_te
        r2_tuned = compute_r2(y_abs_te, pred_tuned)

        per_patient[pname] = {
            'default': r2_default, 'tuned': r2_tuned,
            'best_params': best_params, 'delta': r2_tuned - r2_default,
        }
        scores_default.append(r2_default)
        scores_tuned.append(r2_tuned)

        if detail:
            bp = best_params
            print(f"  {pname}: default={r2_default:.4f} tuned={r2_tuned:.4f}"
                  f" Δ={r2_tuned-r2_default:+.4f}"
                  f" best=d{bp['max_depth']}/lr{bp['learning_rate']}"
                  f"/n{bp['n_estimators']}")

    mean_d = float(np.mean(scores_default)) if scores_default else 0
    mean_t = float(np.mean(scores_tuned)) if scores_tuned else 0
    wins = sum(1 for pp in per_patient.values()
               if pp.get('tuned', 0) > pp.get('default', 0))

    return {
        'name': 'EXP-1176',
        'status': 'pass',
        'detail': (f"default={mean_d:.4f} tuned={mean_t:.4f}"
                   f" Δ={mean_t-mean_d:+.4f} (wins={wins}/{len(patients)})"),
        'per_patient': per_patient,
        'results': {'default': mean_d, 'tuned': mean_t},
    }


# ---------------------------------------------------------------------------
# EXP-1177: Residual Analysis — What's Left to Learn?
# ---------------------------------------------------------------------------

def exp_1177_residual_analysis(patients, detail=False):
    """Analyze residuals from the best model to identify improvement opportunities."""
    per_patient = {}

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']
        pk = p['pk']

        X_enh, y_enh, g_cur_enh = build_enhanced_features(
            p, glucose, physics, include_time=True, include_deriv=True,
            include_interactions=True, include_pk_momentum=True)

        if len(X_enh) < 200:
            per_patient[pname] = {'r2': 0, 'analysis': 'insufficient data'}
            continue

        X_enh = np.nan_to_num(X_enh, nan=0.0)
        y_dg = y_enh - g_cur_enh

        X_tr, X_te, y_tr, y_te = split_data(X_enh, y_dg)
        g_cur_te = g_cur_enh[len(X_enh) - len(X_te):]
        y_abs_te = y_te + g_cur_te

        m = make_xgb_sota()
        m.fit(X_tr, y_tr)
        pred = m.predict(X_te) + g_cur_te
        r2 = compute_r2(y_abs_te, pred)

        # Residuals in glucose-scale
        residuals = (y_abs_te - pred) * GLUCOSE_SCALE

        # 1. Autocorrelation (lag 1-5)
        resid_norm = residuals - residuals.mean()
        var = np.sum(resid_norm ** 2)
        autocorr = []
        for lag in range(1, 6):
            if lag < len(resid_norm):
                c = np.sum(resid_norm[:-lag] * resid_norm[lag:]) / var if var > 0 else 0
                autocorr.append(float(c))
            else:
                autocorr.append(0.0)

        # 2. Heteroscedasticity: residual magnitude vs glucose level
        g_abs_te = g_cur_te * GLUCOSE_SCALE
        low_mask = g_abs_te < np.percentile(g_abs_te, 33)
        mid_mask = (g_abs_te >= np.percentile(g_abs_te, 33)) & (g_abs_te < np.percentile(g_abs_te, 66))
        high_mask = g_abs_te >= np.percentile(g_abs_te, 66)
        rmse_low = float(np.sqrt(np.mean(residuals[low_mask] ** 2))) if low_mask.any() else 0
        rmse_mid = float(np.sqrt(np.mean(residuals[mid_mask] ** 2))) if mid_mask.any() else 0
        rmse_high = float(np.sqrt(np.mean(residuals[high_mask] ** 2))) if high_mask.any() else 0

        # 3. Time-of-day analysis (using index-based hour)
        n_total = len(X_enh)
        n_test = len(X_te)
        test_start_idx = n_total - n_test
        hourly_rmse = {}
        for j in range(len(X_te)):
            global_idx = test_start_idx + j
            hour_bin = (global_idx * STRIDE * 5 // 60) % 24
            period = 'night' if hour_bin < 6 else 'morning' if hour_bin < 12 else 'afternoon' if hour_bin < 18 else 'evening'
            hourly_rmse.setdefault(period, []).append(residuals[j] ** 2)
        period_rmse = {k: float(np.sqrt(np.mean(v))) for k, v in hourly_rmse.items()}

        # 4. IOB-stratified analysis (pk channel 0 is total_iob)
        iob_te = pk[test_start_idx * STRIDE:test_start_idx * STRIDE + n_test * STRIDE:STRIDE, 0]
        if len(iob_te) >= n_test:
            iob_te = iob_te[:n_test]
        else:
            iob_te = np.zeros(n_test)
        iob_low = iob_te < np.percentile(iob_te, 50) if len(iob_te) > 0 else np.zeros(n_test, dtype=bool)
        iob_high = ~iob_low
        rmse_iob_low = float(np.sqrt(np.mean(residuals[iob_low] ** 2))) if iob_low.any() else 0
        rmse_iob_high = float(np.sqrt(np.mean(residuals[iob_high] ** 2))) if iob_high.any() else 0

        analysis = {
            'r2': r2,
            'mae_mg': float(np.mean(np.abs(residuals))),
            'rmse_mg': float(np.sqrt(np.mean(residuals ** 2))),
            'autocorr': autocorr,
            'rmse_by_glucose': {'low': rmse_low, 'mid': rmse_mid, 'high': rmse_high},
            'rmse_by_period': period_rmse,
            'rmse_by_iob': {'low': rmse_iob_low, 'high': rmse_iob_high},
            'residual_mean': float(np.mean(residuals)),
            'residual_std': float(np.std(residuals)),
        }
        per_patient[pname] = analysis

        if detail:
            ac_str = ','.join(f"{c:.3f}" for c in autocorr)
            print(f"  {pname}: R²={r2:.4f} MAE={analysis['mae_mg']:.1f}mg/dL"
                  f" RMSE={analysis['rmse_mg']:.1f}mg/dL")
            print(f"    Autocorr(1-5): [{ac_str}]")
            print(f"    RMSE by glucose: low={rmse_low:.1f} mid={rmse_mid:.1f}"
                  f" high={rmse_high:.1f}")
            print(f"    RMSE by period: {period_rmse}")
            print(f"    RMSE by IOB: low={rmse_iob_low:.1f} high={rmse_iob_high:.1f}")

    # Aggregate
    all_r2 = [v['r2'] for v in per_patient.values() if isinstance(v.get('r2'), float) and v['r2'] > 0]
    all_ac1 = [v['autocorr'][0] for v in per_patient.values()
               if isinstance(v.get('autocorr'), list) and len(v['autocorr']) > 0]
    mean_r2 = float(np.mean(all_r2)) if all_r2 else 0
    mean_ac1 = float(np.mean(all_ac1)) if all_ac1 else 0

    return {
        'name': 'EXP-1177',
        'status': 'pass',
        'detail': (f"mean_R²={mean_r2:.4f} mean_autocorr1={mean_ac1:.3f}"
                   f" → {'high temporal structure' if abs(mean_ac1) > 0.3 else 'moderate structure' if abs(mean_ac1) > 0.1 else 'low structure'} in residuals"),
        'per_patient': per_patient,
        'results': {'mean_r2': mean_r2, 'mean_autocorr1': mean_ac1},
    }


# ---------------------------------------------------------------------------
# EXP-1178: Glucose Variability Features
# ---------------------------------------------------------------------------

def exp_1178_variability_features(patients, detail=False):
    """Add glucose variability metrics to the feature set.

    New features: CV, MAGE (simplified), GMI, time-in-tight-range, J-index.
    """
    per_patient = {}
    scores_base, scores_var = [], []

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']
        pk = p['pk']
        g = glucose / GLUCOSE_SCALE
        g_mg = glucose  # raw mg/dL for variability calculations
        n = len(g)

        X_base_list, X_var_list = [], []
        y_list, g_cur_list = [], []

        for i in range(0, n - WINDOW - HORIZON, STRIDE):
            g_win = g[i:i + WINDOW]
            if np.isnan(g_win).mean() > 0.3:
                continue
            g_win = np.nan_to_num(
                g_win, nan=np.nanmean(g_win) if np.any(~np.isnan(g_win)) else 0.4)
            pk_win = pk[i:i + WINDOW]
            if np.isnan(pk_win).any():
                pk_win = np.nan_to_num(pk_win, nan=0.0)
            p_win = physics[i:i + WINDOW]
            if np.isnan(p_win).any():
                p_win = np.nan_to_num(p_win, nan=0.0)

            y_val = g[i + WINDOW + HORIZON - 1]
            if np.isnan(y_val):
                continue

            g_current = g_win[-1]
            pk_mean = np.mean(pk_win, axis=0)
            pk_last = pk_win[-1]
            base_feat = np.concatenate([g_win, p_win.ravel(), pk_mean, pk_last])

            # Variability features (computed on mg/dL scale)
            g_mg_win = np.nan_to_num(g_mg[i:i + WINDOW], nan=0.0)
            g_mg_mean = np.mean(g_mg_win)
            g_mg_std = np.std(g_mg_win)

            # Coefficient of Variation
            cv = g_mg_std / (g_mg_mean + 1e-6)

            # MAGE (simplified: mean of absolute glucose differences)
            mage = float(np.mean(np.abs(np.diff(g_mg_win))))

            # GMI: 3.31 + 0.02392 * mean_glucose (in mg/dL)
            gmi = 3.31 + 0.02392 * g_mg_mean

            # Time in tight range: fraction of values in 70-140 mg/dL
            tir = float(np.mean((g_mg_win >= 70) & (g_mg_win <= 140)))

            # J-index: 0.001 * (mean + std)^2
            j_index = 0.001 * (g_mg_mean + g_mg_std) ** 2

            # Normalize variability features to reasonable scale
            var_feats = np.array([
                cv,
                mage / GLUCOSE_SCALE,
                gmi / 14.0,  # A1C-like scale → normalize to ~0.5
                tir,
                j_index / 100.0,
            ])

            X_base_list.append(base_feat)
            X_var_list.append(np.concatenate([base_feat, var_feats]))
            y_list.append(y_val)
            g_cur_list.append(g_current)

        if len(X_base_list) < 100:
            per_patient[pname] = {'base': 0, 'variability': 0}
            continue

        X_base = np.nan_to_num(np.array(X_base_list), nan=0.0)
        X_var = np.nan_to_num(np.array(X_var_list), nan=0.0)
        y_arr = np.array(y_list)
        g_cur_arr = np.array(g_cur_list)
        y_dg = y_arr - g_cur_arr

        for X_feat, key, score_list in [
            (X_base, 'base', scores_base),
            (X_var, 'variability', scores_var),
        ]:
            X_tr, X_te, y_tr, y_te = split_data(X_feat, y_dg)
            g_te = g_cur_arr[len(X_feat) - len(X_te):]
            m = make_xgb(n_estimators=300, max_depth=3)
            m.fit(X_tr, y_tr)
            pred = m.predict(X_te) + g_te
            y_abs = y_te + g_te
            r2 = compute_r2(y_abs, pred)
            per_patient.setdefault(pname, {})[key] = r2
            score_list.append(r2)

        if detail:
            r = per_patient[pname]
            print(f"  {pname}: base={r['base']:.4f}"
                  f" variability={r['variability']:.4f}"
                  f" Δ={r['variability'] - r['base']:+.4f}")

    mean_b = float(np.mean(scores_base)) if scores_base else 0
    mean_v = float(np.mean(scores_var)) if scores_var else 0
    wins = sum(1 for pp in per_patient.values()
               if pp.get('variability', 0) > pp.get('base', 0))

    return {
        'name': 'EXP-1178',
        'status': 'pass',
        'detail': (f"base={mean_b:.4f} variability={mean_v:.4f}"
                   f" Δ={mean_v-mean_b:+.4f} (wins={wins}/{len(patients)})"),
        'per_patient': per_patient,
        'results': {'base': mean_b, 'variability': mean_v},
    }


# ---------------------------------------------------------------------------
# EXP-1179: Insulin Stacking Detection
# ---------------------------------------------------------------------------

def exp_1179_insulin_stacking(patients, detail=False):
    """Detect insulin stacking patterns and add as causal features.

    Features:
    - bolus_iob / basal_iob ratio (stacking indicator)
    - Number of bolus peaks in window
    - bolus_activity / basal_activity ratio
    - Time since last bolus peak
    """
    per_patient = {}
    scores_base, scores_stacking = [], []

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']
        pk = p['pk']
        g = glucose / GLUCOSE_SCALE
        n = len(g)

        X_base_list, X_stack_list = [], []
        y_list, g_cur_list = [], []

        for i in range(0, n - WINDOW - HORIZON, STRIDE):
            g_win = g[i:i + WINDOW]
            if np.isnan(g_win).mean() > 0.3:
                continue
            g_win = np.nan_to_num(
                g_win, nan=np.nanmean(g_win) if np.any(~np.isnan(g_win)) else 0.4)
            pk_win = pk[i:i + WINDOW]
            if np.isnan(pk_win).any():
                pk_win = np.nan_to_num(pk_win, nan=0.0)
            p_win = physics[i:i + WINDOW]
            if np.isnan(p_win).any():
                p_win = np.nan_to_num(p_win, nan=0.0)

            y_val = g[i + WINDOW + HORIZON - 1]
            if np.isnan(y_val):
                continue

            g_current = g_win[-1]
            pk_mean = np.mean(pk_win, axis=0)
            pk_last = pk_win[-1]
            base_feat = np.concatenate([g_win, p_win.ravel(), pk_mean, pk_last])

            # PK channels: [total_iob(0), total_activity(1), basal_iob(2),
            #   basal_activity(3), bolus_iob(4), bolus_activity(5),
            #   carb_cob(6), carb_activity(7)]
            basal_iob = pk_win[:, 2]
            bolus_iob = pk_win[:, 4]
            basal_act = pk_win[:, 3]
            bolus_act = pk_win[:, 5]

            # Stacking indicator: bolus_iob / basal_iob at last timepoint
            basal_last = basal_iob[-1]
            bolus_last = bolus_iob[-1]
            stacking_ratio = bolus_last / (basal_last + 1e-6)

            # Binary stacking flag: bolus_iob > 2 * basal_iob
            stacking_flag = 1.0 if bolus_last > 2 * (basal_last + 1e-6) else 0.0

            # Number of bolus peaks in window
            bolus_diff = np.diff(bolus_iob)
            # Peak = positive then negative derivative
            n_peaks = 0
            for j in range(len(bolus_diff) - 1):
                if bolus_diff[j] > 0 and bolus_diff[j + 1] <= 0:
                    n_peaks += 1

            # Bolus activity / basal activity ratio
            mean_basal_act = np.mean(basal_act)
            mean_bolus_act = np.mean(bolus_act)
            act_ratio = mean_bolus_act / (mean_basal_act + 1e-6)

            # Time since last bolus peak (in window steps)
            if bolus_iob.max() > 1e-6:
                last_peak_idx = np.argmax(bolus_iob)
                time_since_peak = float(WINDOW - 1 - last_peak_idx) / WINDOW
            else:
                time_since_peak = 1.0  # no bolus activity

            # Mean bolus IOB level (absolute)
            mean_bolus_iob = float(np.mean(bolus_iob))

            stacking_feats = np.array([
                stacking_ratio,
                stacking_flag,
                float(n_peaks) / WINDOW,
                act_ratio,
                time_since_peak,
                mean_bolus_iob,
            ])

            X_base_list.append(base_feat)
            X_stack_list.append(np.concatenate([base_feat, stacking_feats]))
            y_list.append(y_val)
            g_cur_list.append(g_current)

        if len(X_base_list) < 100:
            per_patient[pname] = {'base': 0, 'stacking': 0}
            continue

        X_base = np.nan_to_num(np.array(X_base_list), nan=0.0)
        X_stack = np.nan_to_num(np.array(X_stack_list), nan=0.0)
        y_arr = np.array(y_list)
        g_cur_arr = np.array(g_cur_list)
        y_dg = y_arr - g_cur_arr

        for X_feat, key, score_list in [
            (X_base, 'base', scores_base),
            (X_stack, 'stacking', scores_stacking),
        ]:
            X_tr, X_te, y_tr, y_te = split_data(X_feat, y_dg)
            g_te = g_cur_arr[len(X_feat) - len(X_te):]
            m = make_xgb(n_estimators=300, max_depth=3)
            m.fit(X_tr, y_tr)
            pred = m.predict(X_te) + g_te
            y_abs = y_te + g_te
            r2 = compute_r2(y_abs, pred)
            per_patient.setdefault(pname, {})[key] = r2
            score_list.append(r2)

        if detail:
            r = per_patient[pname]
            print(f"  {pname}: base={r['base']:.4f}"
                  f" stacking={r['stacking']:.4f}"
                  f" Δ={r['stacking'] - r['base']:+.4f}")

    mean_b = float(np.mean(scores_base)) if scores_base else 0
    mean_s = float(np.mean(scores_stacking)) if scores_stacking else 0
    wins = sum(1 for pp in per_patient.values()
               if pp.get('stacking', 0) > pp.get('base', 0))

    return {
        'name': 'EXP-1179',
        'status': 'pass',
        'detail': (f"base={mean_b:.4f} stacking={mean_s:.4f}"
                   f" Δ={mean_s-mean_b:+.4f} (wins={wins}/{len(patients)})"),
        'per_patient': per_patient,
        'results': {'base': mean_b, 'stacking': mean_s},
    }


# ---------------------------------------------------------------------------
# EXP-1180: Definitive Causal Benchmark (5-Fold CV)
# ---------------------------------------------------------------------------

def exp_1180_definitive_cv(patients, detail=False):
    """Definitive 5-fold TimeSeriesSplit benchmark with ALL proven causal techniques.

    Combines: enhanced features + PK momentum + variability + stacking + XGB→LSTM.
    """
    from sklearn.model_selection import TimeSeriesSplit

    per_patient = {}
    all_base_cv, all_full_cv, all_pipeline_cv = [], [], []

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']
        pk = p['pk']
        g = glucose / GLUCOSE_SCALE
        g_mg = glucose
        n = len(g)

        X_base_list, X_full_list = [], []
        y_list, g_cur_list = [], []

        for i in range(0, n - WINDOW - HORIZON, STRIDE):
            g_win = g[i:i + WINDOW]
            if np.isnan(g_win).mean() > 0.3:
                continue
            g_win = np.nan_to_num(
                g_win, nan=np.nanmean(g_win) if np.any(~np.isnan(g_win)) else 0.4)
            pk_win = pk[i:i + WINDOW]
            if np.isnan(pk_win).any():
                pk_win = np.nan_to_num(pk_win, nan=0.0)
            p_win = physics[i:i + WINDOW]
            if np.isnan(p_win).any():
                p_win = np.nan_to_num(p_win, nan=0.0)

            y_val = g[i + WINDOW + HORIZON - 1]
            if np.isnan(y_val):
                continue

            g_current = g_win[-1]

            # Base structural features
            supply = p_win[:, 0]
            demand = p_win[:, 1]
            hepatic = p_win[:, 2]
            net = p_win[:, 3]
            g_mean = np.mean(g_win)

            base = np.concatenate([g_win, p_win.ravel()])
            phys_inter = np.array([
                np.mean(supply * demand), np.mean(supply * g_mean),
                np.mean(demand * g_mean),
                np.mean(np.diff(net)) if len(net) > 1 else 0.0,
                np.mean(hepatic * supply),
            ])
            g_std = np.std(g_win)
            g_min, g_max = np.min(g_win), np.max(g_win)
            g_range = g_max - g_min
            g_cv = g_std / g_mean if g_mean > 0 else 0.0
            stats = np.array([g_mean, g_std, g_min, g_max, g_range, g_cv])

            pk_mean = np.mean(pk_win, axis=0)
            pk_last = pk_win[-1]

            # Base feature vector
            feat_base = np.concatenate([base, phys_inter, stats, pk_mean, pk_last])

            # Enhanced features
            deriv_feats = np.array(compute_derivative_features(g_win))
            hour = get_hour(p, i + WINDOW - 1)
            time_feats = np.array(compute_time_features(hour))
            inter_feats = np.array(compute_interaction_features(g_win, pk_win))

            # PK momentum
            pk_mom = compute_pk_momentum(pk_win, alpha=0.3)

            # Glucose variability (from EXP-1178)
            g_mg_win = np.nan_to_num(g_mg[i:i + WINDOW], nan=0.0)
            g_mg_mean = np.mean(g_mg_win)
            g_mg_std = np.std(g_mg_win)
            cv_feat = g_mg_std / (g_mg_mean + 1e-6)
            mage_feat = float(np.mean(np.abs(np.diff(g_mg_win)))) / GLUCOSE_SCALE
            gmi_feat = (3.31 + 0.02392 * g_mg_mean) / 14.0
            tir_feat = float(np.mean((g_mg_win >= 70) & (g_mg_win <= 140)))
            j_feat = 0.001 * (g_mg_mean + g_mg_std) ** 2 / 100.0
            var_feats = np.array([cv_feat, mage_feat, gmi_feat, tir_feat, j_feat])

            # Insulin stacking (from EXP-1179)
            basal_iob = pk_win[:, 2]
            bolus_iob = pk_win[:, 4]
            basal_act = pk_win[:, 3]
            bolus_act = pk_win[:, 5]
            basal_last = basal_iob[-1]
            bolus_last = bolus_iob[-1]
            stacking_ratio = bolus_last / (basal_last + 1e-6)
            stacking_flag = 1.0 if bolus_last > 2 * (basal_last + 1e-6) else 0.0
            bolus_diff = np.diff(bolus_iob)
            n_peaks = 0
            for j in range(len(bolus_diff) - 1):
                if bolus_diff[j] > 0 and bolus_diff[j + 1] <= 0:
                    n_peaks += 1
            act_ratio = np.mean(bolus_act) / (np.mean(basal_act) + 1e-6)
            if bolus_iob.max() > 1e-6:
                time_since_peak = float(WINDOW - 1 - np.argmax(bolus_iob)) / WINDOW
            else:
                time_since_peak = 1.0
            stacking_feats = np.array([
                stacking_ratio, stacking_flag,
                float(n_peaks) / WINDOW, act_ratio,
                time_since_peak, float(np.mean(bolus_iob)),
            ])

            feat_full = np.concatenate([
                feat_base, deriv_feats, time_feats, inter_feats,
                pk_mom, var_feats, stacking_feats,
            ])

            X_base_list.append(feat_base)
            X_full_list.append(feat_full)
            y_list.append(y_val)
            g_cur_list.append(g_current)

        if len(X_base_list) < 200:
            per_patient[pname] = {
                'base_cv': {'mean': 0, 'std': 0},
                'full_cv': {'mean': 0, 'std': 0},
                'pipeline_cv': {'mean': 0, 'std': 0},
            }
            continue

        y_arr = np.array(y_list)
        g_cur_arr = np.array(g_cur_list)

        results_p = {}
        for X_list, key, cv_list in [
            (X_base_list, 'base_cv', all_base_cv),
            (X_full_list, 'full_cv', all_full_cv),
        ]:
            X = np.nan_to_num(np.array(X_list), nan=0.0)
            y_dg = y_arr - g_cur_arr

            tscv = TimeSeriesSplit(n_splits=5)
            fold_scores = []
            for train_idx, test_idx in tscv.split(X):
                X_tr, X_te = X[train_idx], X[test_idx]
                y_tr, y_te = y_dg[train_idx], y_dg[test_idx]
                g_te = g_cur_arr[test_idx]

                m = make_xgb_sota()
                m.fit(X_tr, y_tr)
                pred = m.predict(X_te) + g_te
                y_abs = y_te + g_te
                fold_scores.append(compute_r2(y_abs, pred))

            results_p[key] = {
                'mean': float(np.mean(fold_scores)),
                'std': float(np.std(fold_scores)),
                'folds': fold_scores,
            }
            cv_list.append(results_p[key]['mean'])

        # Pipeline CV: XGBoost → LSTM on full features
        X_full = np.nan_to_num(np.array(X_full_list), nan=0.0)
        y_dg = y_arr - g_cur_arr

        tscv = TimeSeriesSplit(n_splits=5)
        pipeline_folds = []
        for train_idx, test_idx in tscv.split(X_full):
            X_tr, X_te = X_full[train_idx], X_full[test_idx]
            y_tr, y_te = y_dg[train_idx], y_dg[test_idx]
            g_te = g_cur_arr[test_idx]

            # Split training into train/val for LSTM
            n_tr = len(X_tr)
            val_size = max(int(n_tr * 0.2), 20)
            X_tr_inner = X_tr[:-val_size]
            X_val_inner = X_tr[-val_size:]
            y_tr_inner = y_tr[:-val_size]
            y_val_inner = y_tr[-val_size:]

            m = make_xgb_sota()
            m.fit(X_tr_inner, y_tr_inner)

            pred_val = m.predict(X_val_inner)
            pred_te = m.predict(X_te)

            resid_val = y_val_inner - pred_val
            resid_te = y_te - pred_te

            corrections = train_lstm_residual(
                resid_val, resid_te, seq_len=12, epochs=20,
                hidden=32, dropout=0.4, patience=8)
            pred_pipeline = pred_te + corrections + g_te
            y_abs = y_te + g_te
            pipeline_folds.append(compute_r2(y_abs, pred_pipeline))

        results_p['pipeline_cv'] = {
            'mean': float(np.mean(pipeline_folds)),
            'std': float(np.std(pipeline_folds)),
            'folds': pipeline_folds,
        }
        all_pipeline_cv.append(results_p['pipeline_cv']['mean'])

        per_patient[pname] = results_p
        if detail:
            b = results_p['base_cv']
            f = results_p['full_cv']
            pl = results_p['pipeline_cv']
            print(f"  {pname}: base_cv={b['mean']:.4f}±{b['std']:.3f}"
                  f" full_cv={f['mean']:.4f}±{f['std']:.3f}"
                  f" pipeline_cv={pl['mean']:.4f}±{pl['std']:.3f}"
                  f" Δ_full={f['mean']-b['mean']:+.4f}"
                  f" Δ_pipe={pl['mean']-b['mean']:+.4f}")

    mean_b = float(np.mean(all_base_cv)) if all_base_cv else 0
    mean_f = float(np.mean(all_full_cv)) if all_full_cv else 0
    mean_p = float(np.mean(all_pipeline_cv)) if all_pipeline_cv else 0

    return {
        'name': 'EXP-1180',
        'status': 'pass',
        'detail': (f"5-fold CV: base={mean_b:.4f} full={mean_f:.4f}"
                   f" pipeline={mean_p:.4f}"
                   f" Δ_full={mean_f-mean_b:+.4f}"
                   f" Δ_pipe={mean_p-mean_b:+.4f}"),
        'per_patient': per_patient,
        'results': {'base_cv': mean_b, 'full_cv': mean_f, 'pipeline_cv': mean_p},
    }


# ---------------------------------------------------------------------------
# Registry and main
# ---------------------------------------------------------------------------

EXPERIMENTS = [
    ('EXP-1171', 'Enhanced Features + LSTM Pipeline (Careful)', exp_1171_enhanced_lstm_careful),
    ('EXP-1172', 'Multi-Horizon Regularization', exp_1172_multi_horizon),
    ('EXP-1173', 'Glucose Pattern Memory (Same-Time-Yesterday)', exp_1173_pattern_memory),
    ('EXP-1174', 'Cross-Patient Transfer Learning', exp_1174_cross_patient_transfer),
    ('EXP-1175', 'Glucose Encoding Variants', exp_1175_encoding_variants),
    ('EXP-1176', 'XGBoost Hyperparameter Deep Tune', exp_1176_hyperparam_tune),
    ('EXP-1177', 'Residual Analysis — What\'s Left to Learn?', exp_1177_residual_analysis),
    ('EXP-1178', 'Glucose Variability Features', exp_1178_variability_features),
    ('EXP-1179', 'Insulin Stacking Detection', exp_1179_insulin_stacking),
    ('EXP-1180', 'Definitive Causal Benchmark (5-Fold CV)', exp_1180_definitive_cv),
]


def main():
    parser = argparse.ArgumentParser(
        description='EXP-1171-1180: Genuine Causal Improvements')
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--max-patients', type=int, default=11)
    parser.add_argument('--experiment', type=str,
                        help='Run only this experiment (e.g. EXP-1171)')
    args = parser.parse_args()

    patients = load_patients(PATIENTS_DIR, max_patients=args.max_patients)
    print(f"Loaded {len(patients)} patients")

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
                             f"{name.lower().replace(' ', '_').replace('-', '_')}"
                             .replace('/', '_').replace(':', '_')
                             .replace('(', '').replace(')', ''))
                save_path = save_results(save_data, save_name)
                print(f"  → Saved {save_path}")

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
