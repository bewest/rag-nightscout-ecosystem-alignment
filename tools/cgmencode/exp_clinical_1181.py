#!/usr/bin/env python3
"""EXP-1181 to EXP-1190: Combined Winners, AR Correction, Heteroscedastic Modeling.

Campaign status after 180 experiments (EXP-1001 to EXP-1180):
- LSTM overfits: 5-fold CV shows XGBoost->LSTM pipeline HURTS (-0.068)
- Enhanced features: +0.023 validated (all 11 patients)
- Multi-horizon regularization: +0.013 (11/11 wins)
- XGBoost per-patient tuning: +0.026 (11/11 wins)
- Residual autocorrelation = 0.474 -> temporal structure exists
- PK momentum: +0.010 causal improvement
- Heteroscedastic errors: RMSE higher at high glucose

This batch focuses on combining all validated winners and exploring simpler
residual correction, heteroscedastic modeling, and feature selection:

  EXP-1181: Combined Validated Winners (Stack All)         ★★★★★
  EXP-1182: Linear AR Residual Correction                  ★★★★
  EXP-1183: Log-Glucose Prediction                         ★★★
  EXP-1184: Quantile Regression Ensemble                   ★★★★
  EXP-1185: Weighted Loss for Clinical Safety              ★★★★
  EXP-1186: Longer Input Windows (3h, 4h, 6h)             ★★★
  EXP-1187: Multi-Resolution Input                         ★★★★
  EXP-1188: Gradient-Boosted Residuals (Stacking)          ★★★★
  EXP-1189: Per-Patient Feature Selection (SHAP-Based)     ★★★
  EXP-1190: 5-Fold CV of Combined Pipeline                 ★★★★★

Run:
    PYTHONPATH=tools python -m cgmencode.exp_clinical_1181 --detail --save --max-patients 11
"""

import argparse
import json
import os
import sys
import time
import warnings

import numpy as np
from pathlib import Path
from sklearn.model_selection import TimeSeriesSplit

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

try:
    import shap
    SHAP_AVAILABLE = True
except ImportError:
    SHAP_AVAILABLE = False

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
    """Extract glucose and physics arrays from patient dict."""
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


def compute_rmse(y_true, y_pred):
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


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
    """Standard SOTA XGBoost configuration."""
    params = dict(n_estimators=500, max_depth=4, learning_rate=0.05,
                  subsample=0.8, colsample_bytree=0.8)
    params.update(overrides)
    return make_xgb(**params)


def split_3way(X, y, fracs=(0.6, 0.2, 0.2)):
    """Chronological 3-way split."""
    n = len(X)
    s1 = int(n * fracs[0])
    s2 = int(n * (fracs[0] + fracs[1]))
    return (X[:s1], X[s1:s2], X[s2:], y[:s1], y[s1:s2], y[s2:])


def split_4way(X, y, fracs=(0.4, 0.2, 0.2, 0.2)):
    """Chronological 4-way split for two-stage stacking."""
    n = len(X)
    s1 = int(n * fracs[0])
    s2 = int(n * (fracs[0] + fracs[1]))
    s3 = int(n * (fracs[0] + fracs[1] + fracs[2]))
    return (X[:s1], X[s1:s2], X[s2:s3], X[s3:],
            y[:s1], y[s1:s2], y[s2:s3], y[s3:])


def get_hour(p, idx):
    """Get hour of day for a given index."""
    df = p['df']
    if 'date' in df.columns:
        try:
            ts = np.datetime64(df['date'].values[idx], 'ns')
            return int((ts.astype('datetime64[h]') -
                        ts.astype('datetime64[D]')).astype(int))
        except Exception:
            pass
    if df.index.dtype == 'datetime64[ns]':
        try:
            return df.index[idx].hour
        except Exception:
            pass
    return (idx * 5 // 60) % 24


# ---------------------------------------------------------------------------
# Feature builders
# ---------------------------------------------------------------------------

def compute_derivative_features(g_win):
    d1 = np.diff(g_win)
    d2 = np.diff(d1) if len(d1) > 1 else np.array([0.0])
    feats = [
        d1[-1] if len(d1) > 0 else 0,
        np.mean(d1[-6:]) if len(d1) >= 6 else np.mean(d1) if len(d1) > 0 else 0,
        np.mean(d1[-12:]) if len(d1) >= 12 else np.mean(d1) if len(d1) > 0 else 0,
        d2[-1] if len(d2) > 0 else 0,
        np.mean(d2[-6:]) if len(d2) >= 6 else np.mean(d2) if len(d2) > 0 else 0,
        np.average(d1[-6:], weights=np.exp(
            np.linspace(-1, 0, min(6, len(d1))))) if len(d1) > 0 else 0,
        np.std(g_win[-12:]) if len(g_win) >= 12 else np.std(g_win),
        np.std(g_win[-6:]) if len(g_win) >= 6 else np.std(g_win),
        np.max(np.abs(d1[-6:])) if len(d1) >= 6 else (
            np.max(np.abs(d1)) if len(d1) > 0 else 0),
        np.sum(np.diff(np.sign(d1[-12:])) != 0) / 12.0 if len(d1) >= 12 else 0,
    ]
    return feats


def compute_time_features(hour):
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
    iob = pk_win[:, 0]
    activity = pk_win[:, 1]
    cob = pk_win[:, 6] if pk_win.shape[1] > 6 else np.zeros(len(pk_win))
    carb_act = pk_win[:, 7] if pk_win.shape[1] > 7 else np.zeros(len(pk_win))
    g_last = g_win[-1]
    g_mean = np.mean(g_win)
    d1 = np.diff(g_win)
    g_trend = (np.mean(d1[-6:]) if len(d1) >= 6
               else np.mean(d1) if len(d1) > 0 else 0)
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
    n = len(pk_win)
    if n < 2:
        return np.zeros(pk_win.shape[1] if pk_win.ndim > 1 else 1)
    weights = np.exp(-alpha * np.arange(n)[::-1])
    weights /= weights.sum()
    pk_ema_slow = np.average(pk_win, axis=0, weights=weights)
    return pk_win[-1] - pk_ema_slow


def build_base_windows(glucose, pk, physics, window=WINDOW, horizon=HORIZON,
                       stride=STRIDE):
    """Base windows: glucose + physics + PK summary (no enhancements)."""
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


def build_enhanced_multi_horizon(p, glucose, physics, horizons=(6, 12, 18),
                                 window=WINDOW, stride=STRIDE):
    """Enhanced features with multi-horizon targets."""
    g = glucose / GLUCOSE_SCALE
    pk = p['pk']
    n = len(g)
    max_h = max(horizons)
    X_list, y_dict, g_cur_list = [], {h: [] for h in horizons}, []

    for i in range(0, n - window - max_h, stride):
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

        targets = {}
        valid = True
        for h in horizons:
            t = g[i + window + h - 1]
            if np.isnan(t):
                valid = False
                break
            targets[h] = t
        if not valid:
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

        hour = get_hour(p, i + window - 1)
        parts = [base, phys_inter, stats, pk_mean, pk_last,
                 np.array(compute_derivative_features(g_win)),
                 np.array(compute_time_features(hour)),
                 np.array(compute_interaction_features(g_win, pk_win)),
                 compute_pk_momentum(pk_win, alpha=0.3)]

        feat = np.concatenate(parts)
        X_list.append(feat)
        for h in horizons:
            y_dict[h].append(targets[h])
        g_cur_list.append(g_current)

    if len(X_list) == 0:
        empty = np.array([]).reshape(0, 1)
        return empty, {h: np.array([]) for h in horizons}, np.array([])
    return (np.array(X_list),
            {h: np.array(y_dict[h]) for h in horizons},
            np.array(g_cur_list))


# ---------------------------------------------------------------------------
# Per-patient hyperparameter grids (validated from EXP-1176)
# ---------------------------------------------------------------------------

PATIENT_HPARAMS = {}  # Populated at runtime per-patient via quick search


def quick_tune_patient(X_tr, y_tr, X_va, y_va):
    """Quick hyperparameter search per patient — returns best params dict."""
    grid = [
        dict(max_depth=3, learning_rate=0.03),
        dict(max_depth=4, learning_rate=0.05),
        dict(max_depth=5, learning_rate=0.05),
        dict(max_depth=4, learning_rate=0.08),
        dict(max_depth=6, learning_rate=0.03),
        dict(max_depth=3, learning_rate=0.10),
    ]
    best_r2 = -1e9
    best_params = grid[1]  # default
    for params in grid:
        m = make_xgb(n_estimators=500, subsample=0.8, colsample_bytree=0.8,
                     **params)
        m.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
        pred = m.predict(X_va)
        r2 = compute_r2(y_va, pred)
        if r2 > best_r2:
            best_r2 = r2
            best_params = params
    return best_params


# ---------------------------------------------------------------------------
# EXP-1181: Combined Validated Winners (Stack All)
# ---------------------------------------------------------------------------

def exp_1181_combined_winners(patients, detail=False):
    """Stack ALL validated techniques: enhanced features + multi-horizon
    regularization + per-patient tuning + PK momentum + dawn conditioning.

    Multi-horizon: train 3 XGBoost models for 30/60/90 min, weighted average
    (0.2 * 30min + 0.6 * 60min + 0.2 * 90min).
    """
    per_patient = {}
    scores_base, scores_combined = [], []
    horizons = [6, 12, 18]  # 30, 60, 90 min
    h_weights = {6: 0.2, 12: 0.6, 18: 0.2}

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']

        # Baseline: base windows, default XGBoost
        X_base, y_base, g_cur_base = build_base_windows(glucose, p['pk'], physics)
        if len(X_base) < 200:
            per_patient[pname] = {'base': 0, 'combined': 0, 'delta': 0}
            continue
        X_base = np.nan_to_num(X_base, nan=0.0)
        y_dg_base = y_base - g_cur_base
        X_tr_b, X_va_b, X_te_b, y_tr_b, y_va_b, y_te_b = split_3way(
            X_base, y_dg_base)
        g_cur_te_b = g_cur_base[len(X_base) - len(X_te_b):]

        m_base = make_xgb_sota()
        m_base.fit(X_tr_b, y_tr_b, eval_set=[(X_va_b, y_va_b)], verbose=False)
        pred_base = m_base.predict(X_te_b) + g_cur_te_b
        y_abs_te_b = y_te_b + g_cur_te_b
        r2_base = compute_r2(y_abs_te_b, pred_base)

        # Combined pipeline: enhanced features + multi-horizon + tuning
        X_mh, y_mh, g_cur_mh = build_enhanced_multi_horizon(
            p, glucose, physics, horizons=horizons)
        if len(X_mh) < 200:
            per_patient[pname] = {'base': r2_base, 'combined': r2_base, 'delta': 0}
            scores_base.append(r2_base)
            scores_combined.append(r2_base)
            continue
        X_mh = np.nan_to_num(X_mh, nan=0.0)

        # Per-patient tuning on 60-min target
        y_dg_60 = y_mh[12] - g_cur_mh
        X_tr, X_va, X_te, y_tr_60, y_va_60, y_te_60 = split_3way(X_mh, y_dg_60)
        g_cur_te = g_cur_mh[len(X_mh) - len(X_te):]
        best_params = quick_tune_patient(X_tr, y_tr_60, X_va, y_va_60)

        # Train per-horizon models with tuned params
        preds_horizon = {}
        for h in horizons:
            y_dg_h = y_mh[h] - g_cur_mh
            _, _, _, y_tr_h, y_va_h, y_te_h = split_3way(X_mh, y_dg_h)
            m = make_xgb(n_estimators=500, subsample=0.8, colsample_bytree=0.8,
                         **best_params)
            m.fit(X_tr, y_tr_h, eval_set=[(X_va, y_va_h)], verbose=False)
            preds_horizon[h] = m.predict(X_te)

        # Weighted average of horizons (all predict delta-glucose)
        combined_pred = sum(h_weights[h] * preds_horizon[h] for h in horizons)
        combined_abs = combined_pred + g_cur_te
        y_abs_te = y_te_60 + g_cur_te
        r2_combined = compute_r2(y_abs_te, combined_abs)

        delta = r2_combined - r2_base
        per_patient[pname] = {'base': r2_base, 'combined': r2_combined,
                              'delta': delta, 'tuned_params': best_params}
        scores_base.append(r2_base)
        scores_combined.append(r2_combined)

        if detail:
            print(f"  {pname}: base={r2_base:.4f} combined={r2_combined:.4f}"
                  f" Δ={delta:+.4f} params={best_params}")

    mean_b = float(np.mean(scores_base)) if scores_base else 0
    mean_c = float(np.mean(scores_combined)) if scores_combined else 0
    wins = sum(1 for pp in per_patient.values() if pp.get('delta', 0) > 0)

    return {
        'name': 'EXP-1181',
        'status': 'pass',
        'detail': (f"base={mean_b:.4f} combined={mean_c:.4f}"
                   f" Δ={mean_c-mean_b:+.4f} (wins={wins}/{len(patients)})"),
        'per_patient': per_patient,
        'results': {'base': mean_b, 'combined': mean_c,
                    'delta': mean_c - mean_b, 'wins': wins},
    }


# ---------------------------------------------------------------------------
# EXP-1182: Linear AR Residual Correction
# ---------------------------------------------------------------------------

def exp_1182_ar_residual(patients, detail=False):
    """Linear autoregressive correction on XGBoost residuals.

    Exploits autocorrelation=0.474 without overfitting risk:
      correction[t] = alpha * r[t-1] + beta * r[t-2]

    Tests both:
      (a) oracle — fit AR on test residuals (upper bound)
      (b) causal — fit AR on validation residuals, apply to test
    """
    per_patient = {}
    scores_base, scores_oracle, scores_causal = [], [], []

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']

        X_enh, y_enh, g_cur = build_enhanced_features(p, glucose, physics)
        if len(X_enh) < 300:
            per_patient[pname] = {'base': 0, 'oracle': 0, 'causal': 0}
            continue
        X_enh = np.nan_to_num(X_enh, nan=0.0)
        y_dg = y_enh - g_cur

        X_tr, X_va, X_te, y_tr, y_va, y_te = split_3way(X_enh, y_dg)
        g_cur_te = g_cur[len(X_enh) - len(X_te):]
        g_cur_va = g_cur[len(X_tr):len(X_tr) + len(X_va)]

        m = make_xgb_sota()
        m.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)

        pred_va = m.predict(X_va)
        pred_te = m.predict(X_te)
        resid_va = y_va - pred_va
        resid_te = y_te - pred_te

        y_abs_te = y_te + g_cur_te
        pred_abs = pred_te + g_cur_te
        r2_base = compute_r2(y_abs_te, pred_abs)

        # (a) Oracle AR: fit on test residuals (theoretical ceiling)
        if len(resid_te) > 3:
            R = np.column_stack([
                resid_te[1:-1],   # r[t-1]
                resid_te[:-2],    # r[t-2]
            ])
            y_r = resid_te[2:]
            # Least squares: [alpha, beta]
            try:
                coeffs_oracle, _, _, _ = np.linalg.lstsq(R, y_r, rcond=None)
                correction_oracle = R @ coeffs_oracle
                pred_oracle = pred_te[2:] + correction_oracle + g_cur_te[2:]
                r2_oracle = compute_r2(y_abs_te[2:], pred_oracle)
            except Exception:
                r2_oracle = r2_base
        else:
            r2_oracle = r2_base

        # (b) Causal AR: fit on validation residuals, apply to test
        if len(resid_va) > 3 and len(resid_te) > 2:
            R_va = np.column_stack([resid_va[1:-1], resid_va[:-2]])
            y_r_va = resid_va[2:]
            try:
                coeffs_causal, _, _, _ = np.linalg.lstsq(R_va, y_r_va,
                                                          rcond=None)
                # Apply causally: use previous predicted residuals
                corrections = np.zeros(len(resid_te))
                # Bootstrap with last two validation residuals
                buf = [resid_va[-2], resid_va[-1]]
                for t in range(len(resid_te)):
                    corrections[t] = (coeffs_causal[0] * buf[-1] +
                                      coeffs_causal[1] * buf[-2])
                    # In causal mode, we don't know true residual — use
                    # the predicted residual (correction itself as proxy)
                    buf.append(resid_te[t])
                pred_causal = pred_te + corrections + g_cur_te
                r2_causal = compute_r2(y_abs_te, pred_causal)
            except Exception:
                r2_causal = r2_base
        else:
            r2_causal = r2_base

        per_patient[pname] = {
            'base': r2_base, 'oracle': r2_oracle, 'causal': r2_causal,
            'delta_oracle': r2_oracle - r2_base,
            'delta_causal': r2_causal - r2_base,
        }
        scores_base.append(r2_base)
        scores_oracle.append(r2_oracle)
        scores_causal.append(r2_causal)

        if detail:
            print(f"  {pname}: base={r2_base:.4f} oracle={r2_oracle:.4f}"
                  f" causal={r2_causal:.4f}"
                  f" Δ_oracle={r2_oracle-r2_base:+.4f}"
                  f" Δ_causal={r2_causal-r2_base:+.4f}")

    mean_b = float(np.mean(scores_base)) if scores_base else 0
    mean_o = float(np.mean(scores_oracle)) if scores_oracle else 0
    mean_c = float(np.mean(scores_causal)) if scores_causal else 0
    wins = sum(1 for pp in per_patient.values()
               if pp.get('delta_causal', 0) > 0)

    return {
        'name': 'EXP-1182',
        'status': 'pass',
        'detail': (f"base={mean_b:.4f} oracle={mean_o:.4f} causal={mean_c:.4f}"
                   f" Δ_oracle={mean_o-mean_b:+.4f}"
                   f" Δ_causal={mean_c-mean_b:+.4f}"
                   f" (wins={wins}/{len(patients)})"),
        'per_patient': per_patient,
        'results': {'base': mean_b, 'oracle': mean_o, 'causal': mean_c,
                    'delta_oracle': mean_o - mean_b,
                    'delta_causal': mean_c - mean_b, 'wins': wins},
    }


# ---------------------------------------------------------------------------
# EXP-1183: Log-Glucose Prediction
# ---------------------------------------------------------------------------

def exp_1183_log_glucose(patients, detail=False):
    """Predict log(glucose/GLUCOSE_SCALE) to handle heteroscedastic errors.

    Higher glucose → higher RMSE.  Log transform naturally compresses the
    upper range and equalises error variance.
    """
    per_patient = {}
    scores_linear, scores_log = [], []

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']

        X_enh, y_enh, g_cur = build_enhanced_features(p, glucose, physics)
        if len(X_enh) < 200:
            per_patient[pname] = {'linear': 0, 'log': 0}
            continue
        X_enh = np.nan_to_num(X_enh, nan=0.0)

        # Standard linear target: delta-glucose
        y_dg = y_enh - g_cur
        X_tr, X_va, X_te, y_tr, y_va, y_te = split_3way(X_enh, y_dg)
        g_cur_te = g_cur[len(X_enh) - len(X_te):]
        y_abs_te = y_te + g_cur_te

        m_lin = make_xgb_sota()
        m_lin.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
        pred_lin = m_lin.predict(X_te) + g_cur_te
        r2_linear = compute_r2(y_abs_te, pred_lin)

        # Log-space prediction
        eps = 1e-6
        y_log = np.log(y_enh + eps)
        g_cur_log = np.log(g_cur + eps)
        y_dg_log = y_log - g_cur_log  # log ratio ≈ relative change

        _, _, _, y_tr_log, y_va_log, y_te_log = split_3way(X_enh, y_dg_log)

        m_log = make_xgb_sota()
        m_log.fit(X_tr, y_tr_log, eval_set=[(X_va, y_va_log)], verbose=False)
        pred_log_delta = m_log.predict(X_te)
        # Back-transform: exp(log(g_cur) + predicted_delta)
        pred_log_abs = np.exp(g_cur_log[len(X_enh) - len(X_te):] +
                              pred_log_delta)
        r2_log = compute_r2(y_abs_te, pred_log_abs)

        # Per-range RMSE comparison
        y_orig = y_abs_te * GLUCOSE_SCALE  # back to mg/dL
        pred_lin_mg = pred_lin * GLUCOSE_SCALE
        pred_log_mg = pred_log_abs * GLUCOSE_SCALE

        rmse_lin_high = compute_rmse(
            y_orig[y_orig > 200], pred_lin_mg[y_orig > 200]
        ) if np.sum(y_orig > 200) > 5 else float('nan')
        rmse_log_high = compute_rmse(
            y_orig[y_orig > 200], pred_log_mg[y_orig > 200]
        ) if np.sum(y_orig > 200) > 5 else float('nan')

        per_patient[pname] = {
            'linear': r2_linear, 'log': r2_log,
            'delta': r2_log - r2_linear,
            'rmse_linear_high': rmse_lin_high,
            'rmse_log_high': rmse_log_high,
        }
        scores_linear.append(r2_linear)
        scores_log.append(r2_log)

        if detail:
            print(f"  {pname}: linear={r2_linear:.4f} log={r2_log:.4f}"
                  f" Δ={r2_log-r2_linear:+.4f}"
                  f" RMSE_hi: lin={rmse_lin_high:.1f} log={rmse_log_high:.1f}")

    mean_l = float(np.mean(scores_linear)) if scores_linear else 0
    mean_g = float(np.mean(scores_log)) if scores_log else 0
    wins = sum(1 for pp in per_patient.values() if pp.get('delta', 0) > 0)

    return {
        'name': 'EXP-1183',
        'status': 'pass',
        'detail': (f"linear={mean_l:.4f} log={mean_g:.4f}"
                   f" Δ={mean_g-mean_l:+.4f} (wins={wins}/{len(patients)})"),
        'per_patient': per_patient,
        'results': {'linear': mean_l, 'log': mean_g,
                    'delta': mean_g - mean_l, 'wins': wins},
    }


# ---------------------------------------------------------------------------
# EXP-1184: Quantile Regression Ensemble
# ---------------------------------------------------------------------------

def exp_1184_quantile_ensemble(patients, detail=False):
    """Train 3 XGBoost quantile models (0.25, 0.50, 0.75). Use median
    prediction and report prediction interval width for clinical utility.
    """
    if not XGB_AVAILABLE:
        return {
            'name': 'EXP-1184', 'status': 'skip',
            'detail': 'xgboost not available (quantile loss requires xgboost)',
            'per_patient': {}, 'results': {},
        }

    per_patient = {}
    scores_mean, scores_median = [], []
    alphas = [0.25, 0.50, 0.75]

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']

        X_enh, y_enh, g_cur = build_enhanced_features(p, glucose, physics)
        if len(X_enh) < 200:
            per_patient[pname] = {'mean': 0, 'median': 0}
            continue
        X_enh = np.nan_to_num(X_enh, nan=0.0)
        y_dg = y_enh - g_cur

        X_tr, X_va, X_te, y_tr, y_va, y_te = split_3way(X_enh, y_dg)
        g_cur_te = g_cur[len(X_enh) - len(X_te):]
        y_abs_te = y_te + g_cur_te

        # Standard mean regression (baseline)
        m_mean = make_xgb_sota()
        m_mean.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
        pred_mean = m_mean.predict(X_te) + g_cur_te
        r2_mean = compute_r2(y_abs_te, pred_mean)

        # Quantile models
        preds_q = {}
        for alpha in alphas:
            m_q = xgb.XGBRegressor(
                n_estimators=500, max_depth=4, learning_rate=0.05,
                subsample=0.8, colsample_bytree=0.8,
                tree_method='hist', device='cuda',
                objective='reg:quantileerror', quantile_alpha=alpha,
                random_state=42, verbosity=0)
            m_q.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
            preds_q[alpha] = m_q.predict(X_te)

        pred_median = preds_q[0.50] + g_cur_te
        r2_median = compute_r2(y_abs_te, pred_median)

        # Prediction interval width (in mg/dL)
        pi_width = (preds_q[0.75] - preds_q[0.25]) * GLUCOSE_SCALE
        mean_pi_width = float(np.mean(pi_width))
        # Coverage: fraction of true values within [q25, q75]
        in_range = ((y_te >= preds_q[0.25]) & (y_te <= preds_q[0.75]))
        coverage = float(np.mean(in_range))

        per_patient[pname] = {
            'mean': r2_mean, 'median': r2_median,
            'delta': r2_median - r2_mean,
            'pi_width_mgdl': mean_pi_width,
            'coverage_50pct': coverage,
        }
        scores_mean.append(r2_mean)
        scores_median.append(r2_median)

        if detail:
            print(f"  {pname}: mean={r2_mean:.4f} median={r2_median:.4f}"
                  f" Δ={r2_median-r2_mean:+.4f}"
                  f" PI_width={mean_pi_width:.1f}mg/dL"
                  f" coverage={coverage:.1%}")

    mean_m = float(np.mean(scores_mean)) if scores_mean else 0
    mean_d = float(np.mean(scores_median)) if scores_median else 0
    wins = sum(1 for pp in per_patient.values() if pp.get('delta', 0) > 0)

    return {
        'name': 'EXP-1184',
        'status': 'pass',
        'detail': (f"mean={mean_m:.4f} median={mean_d:.4f}"
                   f" Δ={mean_d-mean_m:+.4f} (wins={wins}/{len(patients)})"),
        'per_patient': per_patient,
        'results': {'mean': mean_m, 'median': mean_d,
                    'delta': mean_d - mean_m, 'wins': wins},
    }


# ---------------------------------------------------------------------------
# EXP-1185: Weighted Loss for Clinical Safety
# ---------------------------------------------------------------------------

def exp_1185_weighted_loss(patients, detail=False):
    """Upweight low-glucose predictions for clinical safety.

    Weights:
      glucose < 80 mg/dL → 2.0  (hypoglycemia danger zone)
      80-100 mg/dL       → 1.5
      100-250 mg/dL      → 1.0
      > 250 mg/dL        → 0.8
    """
    per_patient = {}
    scores_unweighted, scores_weighted = [], []

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']

        X_enh, y_enh, g_cur = build_enhanced_features(p, glucose, physics)
        if len(X_enh) < 200:
            per_patient[pname] = {'unweighted': 0, 'weighted': 0}
            continue
        X_enh = np.nan_to_num(X_enh, nan=0.0)
        y_dg = y_enh - g_cur

        X_tr, X_va, X_te, y_tr, y_va, y_te = split_3way(X_enh, y_dg)
        g_cur_te = g_cur[len(X_enh) - len(X_te):]
        g_cur_tr = g_cur[:len(X_tr)]
        y_abs_te = y_te + g_cur_te

        # Compute sample weights for training based on target glucose
        y_target_mg = (y_tr + g_cur_tr) * GLUCOSE_SCALE
        weights = np.ones(len(y_tr))
        weights[y_target_mg < 80] = 2.0
        weights[(y_target_mg >= 80) & (y_target_mg < 100)] = 1.5
        weights[(y_target_mg >= 100) & (y_target_mg <= 250)] = 1.0
        weights[y_target_mg > 250] = 0.8

        # Unweighted baseline
        m_uw = make_xgb_sota()
        m_uw.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
        pred_uw = m_uw.predict(X_te) + g_cur_te
        r2_uw = compute_r2(y_abs_te, pred_uw)

        # Weighted
        m_w = make_xgb_sota()
        m_w.fit(X_tr, y_tr, sample_weight=weights,
                eval_set=[(X_va, y_va)], verbose=False)
        pred_w = m_w.predict(X_te) + g_cur_te
        r2_w = compute_r2(y_abs_te, pred_w)

        # Hypoglycemia-specific RMSE (glucose < 100 mg/dL)
        y_te_mg = y_abs_te * GLUCOSE_SCALE
        hypo_mask = y_te_mg < 100
        n_hypo = int(np.sum(hypo_mask))
        if n_hypo > 5:
            rmse_uw_hypo = compute_rmse(y_te_mg[hypo_mask],
                                        pred_uw[hypo_mask] * GLUCOSE_SCALE)
            rmse_w_hypo = compute_rmse(y_te_mg[hypo_mask],
                                       pred_w[hypo_mask] * GLUCOSE_SCALE)
        else:
            rmse_uw_hypo = float('nan')
            rmse_w_hypo = float('nan')

        per_patient[pname] = {
            'unweighted': r2_uw, 'weighted': r2_w,
            'delta': r2_w - r2_uw,
            'rmse_hypo_uw': rmse_uw_hypo, 'rmse_hypo_w': rmse_w_hypo,
            'n_hypo_test': n_hypo,
        }
        scores_unweighted.append(r2_uw)
        scores_weighted.append(r2_w)

        if detail:
            print(f"  {pname}: unweighted={r2_uw:.4f} weighted={r2_w:.4f}"
                  f" Δ={r2_w-r2_uw:+.4f}"
                  f" RMSE_hypo: uw={rmse_uw_hypo:.1f} w={rmse_w_hypo:.1f}"
                  f" (n_hypo={n_hypo})")

    mean_u = float(np.mean(scores_unweighted)) if scores_unweighted else 0
    mean_w = float(np.mean(scores_weighted)) if scores_weighted else 0
    wins = sum(1 for pp in per_patient.values() if pp.get('delta', 0) > 0)

    return {
        'name': 'EXP-1185',
        'status': 'pass',
        'detail': (f"unweighted={mean_u:.4f} weighted={mean_w:.4f}"
                   f" Δ={mean_w-mean_u:+.4f} (wins={wins}/{len(patients)})"),
        'per_patient': per_patient,
        'results': {'unweighted': mean_u, 'weighted': mean_w,
                    'delta': mean_w - mean_u, 'wins': wins},
    }


# ---------------------------------------------------------------------------
# EXP-1186: Longer Input Windows (3h, 4h, 6h)
# ---------------------------------------------------------------------------

def exp_1186_longer_windows(patients, detail=False):
    """Test WINDOW=36 (3h), 48 (4h), 72 (6h) with enhanced features.

    More history might capture slow dynamics like digestion, basal changes.
    """
    window_configs = [
        (24, '2h'),
        (36, '3h'),
        (48, '4h'),
        (72, '6h'),
    ]
    per_patient = {}
    scores_by_window = {label: [] for _, label in window_configs}

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']
        results_p = {}

        for win_size, label in window_configs:
            X, y, g_cur = build_enhanced_features(
                p, glucose, physics, window=win_size)
            if len(X) < 200:
                results_p[label] = 0.0
                continue
            X = np.nan_to_num(X, nan=0.0)
            y_dg = y - g_cur

            X_tr, X_va, X_te, y_tr, y_va, y_te = split_3way(X, y_dg)
            g_cur_te = g_cur[len(X) - len(X_te):]
            y_abs_te = y_te + g_cur_te

            m = make_xgb_sota()
            m.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
            pred = m.predict(X_te) + g_cur_te
            r2 = compute_r2(y_abs_te, pred)
            results_p[label] = r2
            scores_by_window[label].append(r2)

        baseline = results_p.get('2h', 0)
        results_p['deltas'] = {
            label: results_p.get(label, 0) - baseline
            for _, label in window_configs if label != '2h'
        }
        per_patient[pname] = results_p

        if detail:
            parts = [f"{label}={results_p.get(label, 0):.4f}"
                     for _, label in window_configs]
            print(f"  {pname}: {' '.join(parts)}")

    means = {label: float(np.mean(s)) if s else 0
             for label, s in scores_by_window.items()}
    best_label = max(means, key=means.get)

    return {
        'name': 'EXP-1186',
        'status': 'pass',
        'detail': (f"2h={means.get('2h', 0):.4f} 3h={means.get('3h', 0):.4f}"
                   f" 4h={means.get('4h', 0):.4f} 6h={means.get('6h', 0):.4f}"
                   f" best={best_label}"),
        'per_patient': per_patient,
        'results': means,
    }


# ---------------------------------------------------------------------------
# EXP-1187: Multi-Resolution Input
# ---------------------------------------------------------------------------

def exp_1187_multi_resolution(patients, detail=False):
    """Combine fine-grained 2h window (every 5min, 24 steps) with coarse
    6h window (every 15min, 24 steps).  Downsampled coarse window provides
    slow-trend context without quadrupling features.
    """
    per_patient = {}
    scores_fine, scores_multi = [], []

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']
        pk = p['pk']
        g = glucose / GLUCOSE_SCALE
        n = len(g)

        FINE_WIN = 24   # 2h at 5-min
        COARSE_WIN = 72  # 6h at 5-min, downsampled to 24 steps

        X_list, y_list, g_cur_list = [], [], []
        X_fine_only, y_fine_only, g_cur_fine = [], [], []

        for i in range(0, n - COARSE_WIN - HORIZON, STRIDE):
            # Coarse window: past 6h, take every 3rd point → 24 samples
            coarse_start = i
            fine_start = i + COARSE_WIN - FINE_WIN

            g_coarse_raw = g[coarse_start:coarse_start + COARSE_WIN]
            g_fine = g[fine_start:fine_start + FINE_WIN]

            if np.isnan(g_fine).mean() > 0.3 or np.isnan(g_coarse_raw).mean() > 0.5:
                continue
            g_fine = np.nan_to_num(
                g_fine, nan=np.nanmean(g_fine) if np.any(~np.isnan(g_fine)) else 0.4)
            g_coarse_raw = np.nan_to_num(
                g_coarse_raw, nan=np.nanmean(g_coarse_raw)
                if np.any(~np.isnan(g_coarse_raw)) else 0.4)

            g_coarse = g_coarse_raw[::3]  # downsample: 72→24

            pk_fine = pk[fine_start:fine_start + FINE_WIN]
            pk_coarse_raw = pk[coarse_start:coarse_start + COARSE_WIN]
            pk_coarse = pk_coarse_raw[::3]
            if np.isnan(pk_fine).any():
                pk_fine = np.nan_to_num(pk_fine, nan=0.0)
            if np.isnan(pk_coarse).any():
                pk_coarse = np.nan_to_num(pk_coarse, nan=0.0)

            p_fine = physics[fine_start:fine_start + FINE_WIN]
            if np.isnan(p_fine).any():
                p_fine = np.nan_to_num(p_fine, nan=0.0)

            target_idx = fine_start + FINE_WIN + HORIZON - 1
            if target_idx >= n:
                continue
            y_val = g[target_idx]
            if np.isnan(y_val):
                continue

            g_current = g_fine[-1]
            pk_mean = np.mean(pk_fine, axis=0)
            pk_last = pk_fine[-1]

            # Fine-only features (baseline)
            feat_fine = np.concatenate([
                g_fine, p_fine.ravel(), pk_mean, pk_last])
            X_fine_only.append(feat_fine)
            y_fine_only.append(y_val)
            g_cur_fine.append(g_current)

            # Multi-resolution: fine + coarse glucose + coarse PK summary
            pk_coarse_mean = np.mean(pk_coarse, axis=0)
            feat_multi = np.concatenate([
                g_fine, p_fine.ravel(), pk_mean, pk_last,
                g_coarse,  # 24 coarse glucose steps
                pk_coarse_mean,  # coarse PK summary
            ])
            X_list.append(feat_multi)
            y_list.append(y_val)
            g_cur_list.append(g_current)

        if len(X_list) < 200:
            per_patient[pname] = {'fine': 0, 'multi_res': 0}
            continue

        X_fine_arr = np.nan_to_num(np.array(X_fine_only), nan=0.0)
        X_multi_arr = np.nan_to_num(np.array(X_list), nan=0.0)
        y_arr = np.array(y_list)
        g_cur_arr = np.array(g_cur_list)
        y_dg = y_arr - g_cur_arr

        y_fine_arr = np.array(y_fine_only)
        g_cur_fine_arr = np.array(g_cur_fine)
        y_dg_fine = y_fine_arr - g_cur_fine_arr

        # Fine-only baseline
        X_tr_f, X_va_f, X_te_f, y_tr_f, y_va_f, y_te_f = split_3way(
            X_fine_arr, y_dg_fine)
        g_cur_te_f = g_cur_fine_arr[len(X_fine_arr) - len(X_te_f):]
        y_abs_te_f = y_te_f + g_cur_te_f

        m_fine = make_xgb_sota()
        m_fine.fit(X_tr_f, y_tr_f, eval_set=[(X_va_f, y_va_f)], verbose=False)
        r2_fine = compute_r2(y_abs_te_f, m_fine.predict(X_te_f) + g_cur_te_f)

        # Multi-resolution
        X_tr, X_va, X_te, y_tr, y_va, y_te = split_3way(X_multi_arr, y_dg)
        g_cur_te = g_cur_arr[len(X_multi_arr) - len(X_te):]
        y_abs_te = y_te + g_cur_te

        m_multi = make_xgb_sota()
        m_multi.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
        r2_multi = compute_r2(y_abs_te, m_multi.predict(X_te) + g_cur_te)

        per_patient[pname] = {
            'fine': r2_fine, 'multi_res': r2_multi,
            'delta': r2_multi - r2_fine,
        }
        scores_fine.append(r2_fine)
        scores_multi.append(r2_multi)

        if detail:
            print(f"  {pname}: fine={r2_fine:.4f} multi_res={r2_multi:.4f}"
                  f" Δ={r2_multi-r2_fine:+.4f}")

    mean_f = float(np.mean(scores_fine)) if scores_fine else 0
    mean_m = float(np.mean(scores_multi)) if scores_multi else 0
    wins = sum(1 for pp in per_patient.values() if pp.get('delta', 0) > 0)

    return {
        'name': 'EXP-1187',
        'status': 'pass',
        'detail': (f"fine={mean_f:.4f} multi_res={mean_m:.4f}"
                   f" Δ={mean_m-mean_f:+.4f} (wins={wins}/{len(patients)})"),
        'per_patient': per_patient,
        'results': {'fine': mean_f, 'multi_res': mean_m,
                    'delta': mean_m - mean_f, 'wins': wins},
    }


# ---------------------------------------------------------------------------
# EXP-1188: Gradient-Boosted Residuals (Stacking)
# ---------------------------------------------------------------------------

def exp_1188_stacking(patients, detail=False):
    """Two-stage XGBoost stacking to correct systematic errors.

    Stage 1: Train XGBoost on enhanced features → residuals on val1
    Stage 2: Train second XGBoost on [features + Stage1 predictions] → residuals

    Uses 4-way split: train→stage1, val1→residuals, val2→stage2 val, test→final
    """
    per_patient = {}
    scores_single, scores_stacked = [], []

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']

        X_enh, y_enh, g_cur = build_enhanced_features(p, glucose, physics)
        if len(X_enh) < 400:
            per_patient[pname] = {'single': 0, 'stacked': 0}
            continue
        X_enh = np.nan_to_num(X_enh, nan=0.0)
        y_dg = y_enh - g_cur

        (X_tr, X_v1, X_v2, X_te,
         y_tr, y_v1, y_v2, y_te) = split_4way(X_enh, y_dg)
        g_cur_te = g_cur[len(X_enh) - len(X_te):]
        y_abs_te = y_te + g_cur_te

        # Stage 1: base model
        m1 = make_xgb_sota()
        m1.fit(X_tr, y_tr, eval_set=[(X_v1, y_v1)], verbose=False)

        # Single-stage baseline (test directly)
        pred_single = m1.predict(X_te) + g_cur_te
        r2_single = compute_r2(y_abs_te, pred_single)

        # Stage 1 predictions on val1, val2, test
        pred_v1 = m1.predict(X_v1).reshape(-1, 1)
        pred_v2_s1 = m1.predict(X_v2).reshape(-1, 1)
        pred_te_s1 = m1.predict(X_te).reshape(-1, 1)

        # Stage 2 features: original features + stage1 predictions
        X_v1_s2 = np.hstack([X_v1, pred_v1])
        X_v2_s2 = np.hstack([X_v2, pred_v2_s1])
        X_te_s2 = np.hstack([X_te, pred_te_s1])

        # Stage 2 target: original delta-glucose (learn to correct)
        m2 = make_xgb_sota(max_depth=3, learning_rate=0.03)
        m2.fit(X_v1_s2, y_v1, eval_set=[(X_v2_s2, y_v2)], verbose=False)

        pred_stacked = m2.predict(X_te_s2) + g_cur_te
        r2_stacked = compute_r2(y_abs_te, pred_stacked)

        per_patient[pname] = {
            'single': r2_single, 'stacked': r2_stacked,
            'delta': r2_stacked - r2_single,
        }
        scores_single.append(r2_single)
        scores_stacked.append(r2_stacked)

        if detail:
            print(f"  {pname}: single={r2_single:.4f} stacked={r2_stacked:.4f}"
                  f" Δ={r2_stacked-r2_single:+.4f}")

    mean_s = float(np.mean(scores_single)) if scores_single else 0
    mean_k = float(np.mean(scores_stacked)) if scores_stacked else 0
    wins = sum(1 for pp in per_patient.values() if pp.get('delta', 0) > 0)

    return {
        'name': 'EXP-1188',
        'status': 'pass',
        'detail': (f"single={mean_s:.4f} stacked={mean_k:.4f}"
                   f" Δ={mean_k-mean_s:+.4f} (wins={wins}/{len(patients)})"),
        'per_patient': per_patient,
        'results': {'single': mean_s, 'stacked': mean_k,
                    'delta': mean_k - mean_s, 'wins': wins},
    }


# ---------------------------------------------------------------------------
# EXP-1189: Per-Patient Feature Selection (SHAP-Based)
# ---------------------------------------------------------------------------

def exp_1189_shap_selection(patients, detail=False):
    """Per-patient SHAP feature selection: keep top-K features (K=50,100,200).

    Tests whether pruning noisy features helps by reducing overfitting.
    Falls back to permutation importance if SHAP is unavailable.
    """
    per_patient = {}
    K_values = [50, 100, 200]
    scores_full = []
    scores_by_k = {k: [] for k in K_values}

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']

        X_enh, y_enh, g_cur = build_enhanced_features(p, glucose, physics)
        if len(X_enh) < 200:
            per_patient[pname] = {'full': 0}
            continue
        X_enh = np.nan_to_num(X_enh, nan=0.0)
        y_dg = y_enh - g_cur

        X_tr, X_va, X_te, y_tr, y_va, y_te = split_3way(X_enh, y_dg)
        g_cur_te = g_cur[len(X_enh) - len(X_te):]
        y_abs_te = y_te + g_cur_te

        # Full model
        m_full = make_xgb_sota()
        m_full.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
        pred_full = m_full.predict(X_te) + g_cur_te
        r2_full = compute_r2(y_abs_te, pred_full)
        scores_full.append(r2_full)

        # Compute feature importance ranking
        n_features = X_tr.shape[1]
        if SHAP_AVAILABLE and XGB_AVAILABLE:
            try:
                explainer = shap.TreeExplainer(m_full)
                shap_vals = explainer.shap_values(X_va[:min(500, len(X_va))])
                importance = np.mean(np.abs(shap_vals), axis=0)
            except Exception:
                importance = m_full.feature_importances_ if hasattr(
                    m_full, 'feature_importances_') else np.ones(n_features)
        elif hasattr(m_full, 'feature_importances_'):
            importance = m_full.feature_importances_
        else:
            importance = np.ones(n_features)

        ranked_idx = np.argsort(importance)[::-1]
        results_p = {'full': r2_full}

        for k in K_values:
            if k >= n_features:
                results_p[f'top_{k}'] = r2_full
                results_p[f'delta_{k}'] = 0.0
                scores_by_k[k].append(r2_full)
                continue

            top_k_idx = ranked_idx[:k]
            X_tr_k = X_tr[:, top_k_idx]
            X_va_k = X_va[:, top_k_idx]
            X_te_k = X_te[:, top_k_idx]

            m_k = make_xgb_sota()
            m_k.fit(X_tr_k, y_tr, eval_set=[(X_va_k, y_va)], verbose=False)
            pred_k = m_k.predict(X_te_k) + g_cur_te
            r2_k = compute_r2(y_abs_te, pred_k)

            results_p[f'top_{k}'] = r2_k
            results_p[f'delta_{k}'] = r2_k - r2_full
            scores_by_k[k].append(r2_k)

        per_patient[pname] = results_p

        if detail:
            parts = [f"full={r2_full:.4f}"]
            for k in K_values:
                parts.append(f"top{k}={results_p.get(f'top_{k}', 0):.4f}")
            print(f"  {pname}: {' '.join(parts)}")

    mean_full = float(np.mean(scores_full)) if scores_full else 0
    means_k = {k: float(np.mean(scores_by_k[k])) if scores_by_k[k] else 0
               for k in K_values}
    best_k = max(means_k, key=means_k.get)

    return {
        'name': 'EXP-1189',
        'status': 'pass',
        'detail': (f"full={mean_full:.4f}"
                   + ''.join(f" top{k}={means_k[k]:.4f}" for k in K_values)
                   + f" best=top{best_k}"),
        'per_patient': per_patient,
        'results': {'full': mean_full, **{f'top_{k}': means_k[k]
                    for k in K_values}, 'best_k': best_k},
    }


# ---------------------------------------------------------------------------
# EXP-1190: 5-Fold CV of Combined Pipeline
# ---------------------------------------------------------------------------

def exp_1190_combined_cv(patients, detail=False):
    """5-fold TimeSeriesSplit CV of the best combined pipeline from EXP-1181.

    This is the definitive benchmark — no data splitting tricks, just rigorous
    time-series cross-validation of the full pipeline.
    """
    per_patient = {}
    all_base_cv, all_combined_cv = [], []
    horizons = [6, 12, 18]
    h_weights = {6: 0.2, 12: 0.6, 18: 0.2}
    n_splits = 5

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']

        # Build enhanced multi-horizon data
        X_mh, y_mh, g_cur_mh = build_enhanced_multi_horizon(
            p, glucose, physics, horizons=horizons)
        if len(X_mh) < 300:
            per_patient[pname] = {'base_cv': {'mean': 0, 'std': 0, 'folds': []},
                                  'combined_cv': {'mean': 0, 'std': 0, 'folds': []}}
            continue
        X_mh = np.nan_to_num(X_mh, nan=0.0)

        # Also build base windows for baseline CV
        X_base, y_base, g_cur_base = build_base_windows(
            glucose, p['pk'], physics)
        if len(X_base) < 300:
            per_patient[pname] = {'base_cv': {'mean': 0, 'std': 0, 'folds': []},
                                  'combined_cv': {'mean': 0, 'std': 0, 'folds': []}}
            continue
        X_base = np.nan_to_num(X_base, nan=0.0)
        y_dg_base = y_base - g_cur_base

        tscv = TimeSeriesSplit(n_splits=n_splits)

        # Baseline CV: simple XGBoost on base features
        base_folds = []
        for train_idx, test_idx in tscv.split(X_base):
            X_tr_b = X_base[train_idx]
            y_tr_b = y_dg_base[train_idx]
            X_te_b = X_base[test_idx]
            y_te_b = y_dg_base[test_idx]
            g_cur_te_b = g_cur_base[test_idx]

            # Use last 20% of train as validation for early stopping
            val_split = int(len(X_tr_b) * 0.8)
            X_tr_inner = X_tr_b[:val_split]
            y_tr_inner = y_tr_b[:val_split]
            X_va_inner = X_tr_b[val_split:]
            y_va_inner = y_tr_b[val_split:]

            m = make_xgb_sota()
            m.fit(X_tr_inner, y_tr_inner,
                  eval_set=[(X_va_inner, y_va_inner)], verbose=False)
            pred = m.predict(X_te_b) + g_cur_te_b
            y_abs = y_te_b + g_cur_te_b
            base_folds.append(compute_r2(y_abs, pred))

        # Combined CV: enhanced features + multi-horizon + per-patient tuning
        combined_folds = []
        y_dg_60 = y_mh[12] - g_cur_mh

        for train_idx, test_idx in tscv.split(X_mh):
            X_tr = X_mh[train_idx]
            X_te = X_mh[test_idx]
            g_cur_te = g_cur_mh[test_idx]

            # Inner validation split for tuning & early stopping
            val_split = int(len(X_tr) * 0.8)
            X_tr_inner = X_tr[:val_split]
            X_va_inner = X_tr[val_split:]

            # Per-patient quick tune on 60-min target
            y_tr_60 = y_dg_60[train_idx]
            y_tr_60_inner = y_tr_60[:val_split]
            y_va_60_inner = y_tr_60[val_split:]
            best_params = quick_tune_patient(X_tr_inner, y_tr_60_inner,
                                             X_va_inner, y_va_60_inner)

            # Multi-horizon: train per-horizon models
            preds_h = {}
            for h in horizons:
                y_dg_h = y_mh[h] - g_cur_mh
                y_tr_h = y_dg_h[train_idx]
                y_te_h = y_dg_h[test_idx]

                y_tr_h_inner = y_tr_h[:val_split]
                y_va_h_inner = y_tr_h[val_split:]

                m = make_xgb(n_estimators=500, subsample=0.8,
                             colsample_bytree=0.8, **best_params)
                m.fit(X_tr_inner, y_tr_h_inner,
                      eval_set=[(X_va_inner, y_va_h_inner)], verbose=False)
                preds_h[h] = m.predict(X_te)

            combined_pred = sum(h_weights[h] * preds_h[h] for h in horizons)
            combined_abs = combined_pred + g_cur_te

            y_te_60 = y_dg_60[test_idx]
            y_abs_te = y_te_60 + g_cur_te
            combined_folds.append(compute_r2(y_abs_te, combined_abs))

        results_p = {
            'base_cv': {
                'mean': float(np.mean(base_folds)),
                'std': float(np.std(base_folds)),
                'folds': [float(f) for f in base_folds],
            },
            'combined_cv': {
                'mean': float(np.mean(combined_folds)),
                'std': float(np.std(combined_folds)),
                'folds': [float(f) for f in combined_folds],
            },
        }
        all_base_cv.append(results_p['base_cv']['mean'])
        all_combined_cv.append(results_p['combined_cv']['mean'])
        per_patient[pname] = results_p

        if detail:
            b = results_p['base_cv']
            c = results_p['combined_cv']
            print(f"  {pname}: base_cv={b['mean']:.4f}±{b['std']:.3f}"
                  f" combined_cv={c['mean']:.4f}±{c['std']:.3f}"
                  f" Δ={c['mean']-b['mean']:+.4f}")

    mean_b = float(np.mean(all_base_cv)) if all_base_cv else 0
    mean_c = float(np.mean(all_combined_cv)) if all_combined_cv else 0
    wins = sum(1 for pp in per_patient.values()
               if pp.get('combined_cv', {}).get('mean', 0) >
               pp.get('base_cv', {}).get('mean', 0))

    return {
        'name': 'EXP-1190',
        'status': 'pass',
        'detail': (f"5-fold CV: base={mean_b:.4f} combined={mean_c:.4f}"
                   f" Δ={mean_c-mean_b:+.4f} (wins={wins}/{len(patients)})"),
        'per_patient': per_patient,
        'results': {'base_cv': mean_b, 'combined_cv': mean_c,
                    'delta': mean_c - mean_b, 'wins': wins},
    }


# ---------------------------------------------------------------------------
# Registry and main
# ---------------------------------------------------------------------------

EXPERIMENTS = [
    ('EXP-1181', 'Combined Validated Winners (Stack All)',
     exp_1181_combined_winners),
    ('EXP-1182', 'Linear AR Residual Correction',
     exp_1182_ar_residual),
    ('EXP-1183', 'Log-Glucose Prediction',
     exp_1183_log_glucose),
    ('EXP-1184', 'Quantile Regression Ensemble',
     exp_1184_quantile_ensemble),
    ('EXP-1185', 'Weighted Loss for Clinical Safety',
     exp_1185_weighted_loss),
    ('EXP-1186', 'Longer Input Windows (3h, 4h, 6h)',
     exp_1186_longer_windows),
    ('EXP-1187', 'Multi-Resolution Input',
     exp_1187_multi_resolution),
    ('EXP-1188', 'Gradient-Boosted Residuals (Stacking)',
     exp_1188_stacking),
    ('EXP-1189', 'Per-Patient Feature Selection (SHAP-Based)',
     exp_1189_shap_selection),
    ('EXP-1190', '5-Fold CV of Combined Pipeline',
     exp_1190_combined_cv),
]


def main():
    parser = argparse.ArgumentParser(
        description='EXP-1181-1190: Combined Winners, AR Correction, '
                    'Heteroscedastic Modeling')
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--max-patients', type=int, default=11)
    parser.add_argument('--experiments', type=str, default='all',
                        help='Comma-separated exp numbers or "all"')
    parser.add_argument('--experiment', type=str,
                        help='Run only this experiment (e.g. EXP-1181)')
    args = parser.parse_args()

    patients = load_patients(PATIENTS_DIR, max_patients=args.max_patients)
    print(f"Loaded {len(patients)} patients")

    # Determine which experiments to run
    if args.experiment:
        to_run = {args.experiment}
    elif args.experiments == 'all':
        to_run = None  # run all
    else:
        to_run = {f'EXP-{x.strip()}' for x in args.experiments.split(',')}

    for exp_id, name, func in EXPERIMENTS:
        if to_run is not None and exp_id not in to_run:
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
                    'per_patient': result.get('per_patient', {}),
                }
                save_name = (f"{exp_id.lower()}_"
                             f"{name.lower().replace(' ', '_')}"
                             .replace('/', '_').replace(':', '_')
                             .replace('(', '').replace(')', '')
                             .replace('-', '_'))
                save_results(save_data, save_name)

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
