#!/usr/bin/env python3
"""EXP-1161 to EXP-1170: Causal PK Leakage Resolution.

Campaign status after 160 experiments:
- SOTA: R²≈0.58+ (XGBoost + PK lead, single split)
- 5-fold CV: R²≈0.549 (definitive)
- CRITICAL DISCOVERY: PK lead 45min gives +0.042–0.132 R²
- PROBLEM: Leading PK channels uses FUTURE bolus/insulin data = DATA LEAKAGE
- This batch resolves the leakage question definitively.

This batch systematically decomposes and replaces leaked signal:
  EXP-1161: Causal PK Projection (No Leakage) ★★★★★
  EXP-1162: Basal-Only Lead (Partial Causal) ★★★★
  EXP-1163: Bolus-Only Lead (Leakage Quantification) ★★★★
  EXP-1164: PK Rate of Change Features (Causal Alternative) ★★★★
  EXP-1165: PK Trajectory Features (Causal Alternative) ★★★
  EXP-1166: Causal PK Projection + Enhanced Features ★★★★★
  EXP-1167: PK Momentum Features ★★★
  EXP-1168: Lead Leakage Quantification (Systematic) ★★★★★
  EXP-1169: 5-Fold CV: Causal vs Leaked Lead ★★★★★
  EXP-1170: Best Causal SOTA Pipeline ★★★★★

Run:
    PYTHONPATH=tools python -m cgmencode.exp_clinical_1161 --detail --save --max-patients 11
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


def make_xgb_sota():
    """Standard SOTA XGBoost configuration per spec."""
    return make_xgb(n_estimators=500, max_depth=4, learning_rate=0.05,
                    subsample=0.8, colsample_bytree=0.8)


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


# ---------------------------------------------------------------------------
# PK Projection and Causal Feature helpers
# ---------------------------------------------------------------------------

def project_pk_forward(pk_current, lead_steps, dia_steps=72, carb_abs_steps=36):
    """Project PK state forward by lead_steps using known absorption curves.

    This is CAUSAL - uses only information available at current time.
    dia_steps: DIA in 5-min steps (6h = 72 steps)
    carb_abs_steps: carb absorption time in 5-min steps (3h = 36 steps)
    """
    projected = np.zeros_like(pk_current)
    # IOB channels (0,2,4): exponential-like decay
    for ch in [0, 2, 4]:  # total_iob, basal_iob, bolus_iob
        decay_frac = max(0.0, 1.0 - lead_steps / dia_steps)
        projected[ch] = pk_current[ch] * decay_frac
    # Activity channels (1,3,5): peak then decay (simplified triangle)
    for ch in [1, 3, 5]:
        peak_step = dia_steps // 5  # ~72/5 ≈ 14 steps ≈ 70 min
        if lead_steps < peak_step:
            projected[ch] = pk_current[ch] * (1 + 0.5 * lead_steps / peak_step)
        else:
            projected[ch] = pk_current[ch] * max(
                0, 1 - (lead_steps - peak_step) / (dia_steps - peak_step))
    # COB channel (6): linear decay
    for ch in [6]:
        decay_frac = max(0.0, 1.0 - lead_steps / carb_abs_steps)
        projected[ch] = pk_current[ch] * decay_frac
    # Carb activity channel (7): linear decay
    for ch in [7]:
        projected[ch] = pk_current[ch] * max(0.0, 1.0 - lead_steps / carb_abs_steps)
    return projected


def compute_pk_roc(pk_win):
    """Rate of change and acceleration of PK channels within current window."""
    if len(pk_win) < 3:
        return np.zeros(8), np.zeros(8)
    d1 = np.diff(pk_win, axis=0)
    roc = np.mean(d1, axis=0)  # (8,) mean rate of change
    d2 = np.diff(d1, axis=0)
    accel = np.mean(d2, axis=0) if len(d2) > 0 else np.zeros(8)  # (8,)
    return roc, accel


def compute_pk_trajectory(pk_win):
    """Extract trajectory features from PK window."""
    n_steps = len(pk_win)
    n_ch = pk_win.shape[1] if pk_win.ndim > 1 else 1
    feats = []

    for ch in range(n_ch):
        col = pk_win[:, ch] if pk_win.ndim > 1 else pk_win
        # Slope via linear fit
        x = np.arange(n_steps, dtype=float)
        if n_steps > 1 and np.std(col) > 1e-10:
            slope = np.polyfit(x, col, 1)[0]
        else:
            slope = 0.0
        feats.append(slope)

        # Curvature (second derivative mean)
        d2 = np.diff(col, n=2)
        curvature = np.mean(d2) if len(d2) > 0 else 0.0
        feats.append(curvature)

        # Position relative to window min/max
        col_min, col_max = np.min(col), np.max(col)
        col_range = col_max - col_min
        rel_pos = (col[-1] - col_min) / (col_range + 1e-10) if col_range > 1e-10 else 0.5
        feats.append(rel_pos)

        # Is rising? (1 if last > first)
        feats.append(1.0 if col[-1] > col[0] else 0.0)

    # Time since last IOB peak (channel 0)
    iob = pk_win[:, 0] if pk_win.ndim > 1 else pk_win
    peak_idx = np.argmax(iob)
    feats.append(float(n_steps - 1 - peak_idx))

    # Time since last COB peak (channel 6)
    cob = pk_win[:, 6] if pk_win.ndim > 1 and pk_win.shape[1] > 6 else pk_win
    cob_peak_idx = np.argmax(cob)
    feats.append(float(n_steps - 1 - cob_peak_idx))

    return np.array(feats, dtype=float)


def compute_pk_momentum(pk_win, alpha=0.3):
    """Exponentially weighted momentum of PK channels."""
    n = len(pk_win)
    if n < 2:
        return np.zeros(pk_win.shape[1] if pk_win.ndim > 1 else 1)
    pk_ema_fast = pk_win[-1]
    weights = np.exp(-alpha * np.arange(n)[::-1])
    weights /= weights.sum()
    pk_ema_slow = np.average(pk_win, axis=0, weights=weights)
    momentum = pk_ema_fast - pk_ema_slow  # Positive = increasing
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


def build_lead_windows(glucose, pk, physics, lead_steps=9,
                       window=WINDOW, horizon=HORIZON, stride=STRIDE):
    """Windows with full PK lead shift (potentially leaked)."""
    g = glucose / GLUCOSE_SCALE
    n = len(g)
    X_list, y_list, g_cur_list = [], [], []

    for i in range(0, n - window - horizon - lead_steps, stride):
        g_win = g[i:i + window]
        if np.isnan(g_win).mean() > 0.3:
            continue
        g_win = np.nan_to_num(
            g_win, nan=np.nanmean(g_win) if np.any(~np.isnan(g_win)) else 0.4)

        pk_start = i + lead_steps
        pk_end = pk_start + window
        if pk_end > n:
            continue
        pk_win = pk[pk_start:pk_end]
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
                            include_interactions=True, pk_lead_steps=0):
    """Build features with all proven enhancements and optional PK lead."""
    g = glucose / GLUCOSE_SCALE
    pk = p['pk']
    n = len(g)
    X_list, y_list, g_cur_list = [], [], []

    max_i = n - window - horizon - pk_lead_steps
    for i in range(0, max_i, stride):
        g_win = g[i:i + window]
        if np.isnan(g_win).mean() > 0.3:
            continue
        g_win = np.nan_to_num(
            g_win, nan=np.nanmean(g_win) if np.any(~np.isnan(g_win)) else 0.4)
        p_win = physics[i:i + window]
        if np.isnan(p_win).any():
            p_win = np.nan_to_num(p_win, nan=0.0)

        pk_start = i + pk_lead_steps
        pk_end = pk_start + window
        if pk_end > n:
            continue
        pk_win = pk[pk_start:pk_end]
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
# EXP-1161: Causal PK Projection (No Leakage)
# ---------------------------------------------------------------------------

def exp_1161_causal_pk_projection(patients, detail=False):
    """Project current PK state forward using known absorption curves — fully causal."""
    per_patient = {}
    scores_base, scores_leaked, scores_causal = [], [], []

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']
        g = glucose / GLUCOSE_SCALE
        pk = p['pk']
        n = len(g)
        lead_steps = 9  # 45 min

        X_base_list, X_leaked_list, X_causal_list = [], [], []
        y_list, g_cur_list = [], []

        for i in range(0, n - WINDOW - HORIZON - lead_steps, STRIDE):
            g_win = g[i:i + WINDOW]
            if np.isnan(g_win).mean() > 0.3:
                continue
            g_win = np.nan_to_num(
                g_win, nan=np.nanmean(g_win) if np.any(~np.isnan(g_win)) else 0.4)
            p_win = physics[i:i + WINDOW]
            if np.isnan(p_win).any():
                p_win = np.nan_to_num(p_win, nan=0.0)

            # Current PK (lag0)
            pk_cur = pk[i:i + WINDOW]
            if np.isnan(pk_cur).any():
                pk_cur = np.nan_to_num(pk_cur, nan=0.0)

            # Future PK (leaked)
            pk_lead_start = i + lead_steps
            pk_lead_end = pk_lead_start + WINDOW
            if pk_lead_end > n:
                continue
            pk_future = pk[pk_lead_start:pk_lead_end]
            if np.isnan(pk_future).any():
                pk_future = np.nan_to_num(pk_future, nan=0.0)

            y_val = g[i + WINDOW + HORIZON - 1]
            if np.isnan(y_val):
                continue

            g_current = g_win[-1]

            # Causal projection: project last PK value forward
            pk_projected = project_pk_forward(pk_cur[-1], lead_steps)

            # Base: lag0 PK only
            feat_base = np.concatenate([
                g_win, p_win.ravel(),
                pk_cur.mean(axis=0), pk_cur[-1],
            ])
            # Leaked: actual future PK
            feat_leaked = np.concatenate([
                g_win, p_win.ravel(),
                pk_cur.mean(axis=0), pk_cur[-1],
                pk_future.mean(axis=0), pk_future[-1],
            ])
            # Causal: projected PK instead of future PK
            feat_causal = np.concatenate([
                g_win, p_win.ravel(),
                pk_cur.mean(axis=0), pk_cur[-1],
                pk_projected,
            ])

            X_base_list.append(feat_base)
            X_leaked_list.append(feat_leaked)
            X_causal_list.append(feat_causal)
            y_list.append(y_val)
            g_cur_list.append(g_current)

        results_p = {}
        y_arr = np.array(y_list)
        g_cur_arr = np.array(g_cur_list)

        for X_list, key, score_list in [
            (X_base_list, 'base', scores_base),
            (X_leaked_list, 'leaked_lead', scores_leaked),
            (X_causal_list, 'causal_lead', scores_causal),
        ]:
            if len(X_list) < 100:
                results_p[key] = 0.0
                continue
            X = np.nan_to_num(np.array(X_list), nan=0.0)
            y_dg = y_arr - g_cur_arr
            X_tr, X_te, y_tr, y_te = split_data(X, y_dg)
            g_cur_te = g_cur_arr[len(X) - len(X_te):]

            m = make_xgb(n_estimators=300, max_depth=3)
            m.fit(X_tr, y_tr)
            pred = m.predict(X_te) + g_cur_te
            y_abs = y_te + g_cur_te
            r2 = compute_r2(y_abs, pred)
            results_p[key] = r2
            score_list.append(r2)

        per_patient[pname] = results_p
        if detail:
            r = results_p
            leaked_gain = r.get('leaked_lead', 0) - r.get('base', 0)
            causal_gain = r.get('causal_lead', 0) - r.get('base', 0)
            leakage_frac = (1 - causal_gain / leaked_gain) if leaked_gain > 0.001 else 0
            print(f"  {pname}: base={r.get('base',0):.4f}"
                  f" leaked={r.get('leaked_lead',0):.4f}"
                  f" causal={r.get('causal_lead',0):.4f}"
                  f" leak_frac={leakage_frac:.1%}")

    means = {k: float(np.mean(v)) if v else 0
             for k, v in [('base', scores_base), ('leaked_lead', scores_leaked),
                          ('causal_lead', scores_causal)]}
    leaked_delta = means['leaked_lead'] - means['base']
    causal_delta = means['causal_lead'] - means['base']
    leakage = leaked_delta - causal_delta

    return {
        'name': 'EXP-1161',
        'status': 'pass',
        'detail': (f"base={means['base']:.4f} leaked={means['leaked_lead']:.4f}"
                   f" causal={means['causal_lead']:.4f}"
                   f" Δ_leaked={leaked_delta:+.4f} Δ_causal={causal_delta:+.4f}"
                   f" leakage={leakage:+.4f}"),
        'per_patient': per_patient,
        'results': means,
    }


# ---------------------------------------------------------------------------
# EXP-1162: Basal-Only Lead (Partial Causal)
# ---------------------------------------------------------------------------

def exp_1162_basal_only_lead(patients, detail=False):
    """Lead ONLY basal PK channels (2,3) by 45min — fully causal for pump users."""
    per_patient = {}
    scores_base, scores_basal, scores_full = [], [], []
    lead_steps = 9  # 45 min

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']
        g = glucose / GLUCOSE_SCALE
        pk = p['pk']
        n = len(g)

        X_base_list, X_basal_list, X_full_list = [], [], []
        y_list, g_cur_list = [], []

        for i in range(0, n - WINDOW - HORIZON - lead_steps, STRIDE):
            g_win = g[i:i + WINDOW]
            if np.isnan(g_win).mean() > 0.3:
                continue
            g_win = np.nan_to_num(
                g_win, nan=np.nanmean(g_win) if np.any(~np.isnan(g_win)) else 0.4)
            p_win = physics[i:i + WINDOW]
            if np.isnan(p_win).any():
                p_win = np.nan_to_num(p_win, nan=0.0)

            pk_cur = pk[i:i + WINDOW]
            if np.isnan(pk_cur).any():
                pk_cur = np.nan_to_num(pk_cur, nan=0.0)

            pk_lead_start = i + lead_steps
            pk_lead_end = pk_lead_start + WINDOW
            if pk_lead_end > n:
                continue
            pk_future = pk[pk_lead_start:pk_lead_end]
            if np.isnan(pk_future).any():
                pk_future = np.nan_to_num(pk_future, nan=0.0)

            y_val = g[i + WINDOW + HORIZON - 1]
            if np.isnan(y_val):
                continue

            g_current = g_win[-1]
            base_feats = np.concatenate([g_win, p_win.ravel()])

            # Base: lag0 PK only
            feat_base = np.concatenate([
                base_feats, pk_cur.mean(axis=0), pk_cur[-1]])

            # Basal-only lead: future for channels 2,3 only
            feat_basal = np.concatenate([
                base_feats, pk_cur.mean(axis=0), pk_cur[-1],
                pk_future.mean(axis=0)[2:4],  # basal_iob, basal_activity mean
                pk_future[-1, 2:4],            # basal_iob, basal_activity last
            ])

            # Full lead: all channels from future
            feat_full = np.concatenate([
                base_feats,
                pk_future.mean(axis=0), pk_future[-1]])

            X_base_list.append(feat_base)
            X_basal_list.append(feat_basal)
            X_full_list.append(feat_full)
            y_list.append(y_val)
            g_cur_list.append(g_current)

        results_p = {}
        y_arr = np.array(y_list)
        g_cur_arr = np.array(g_cur_list)

        for X_list, key, score_list in [
            (X_base_list, 'base', scores_base),
            (X_basal_list, 'basal_lead', scores_basal),
            (X_full_list, 'full_lead', scores_full),
        ]:
            if len(X_list) < 100:
                results_p[key] = 0.0
                continue
            X = np.nan_to_num(np.array(X_list), nan=0.0)
            y_dg = y_arr - g_cur_arr
            X_tr, X_te, y_tr, y_te = split_data(X, y_dg)
            g_cur_te = g_cur_arr[len(X) - len(X_te):]

            m = make_xgb(n_estimators=300, max_depth=3)
            m.fit(X_tr, y_tr)
            pred = m.predict(X_te) + g_cur_te
            y_abs = y_te + g_cur_te
            r2 = compute_r2(y_abs, pred)
            results_p[key] = r2
            score_list.append(r2)

        per_patient[pname] = results_p
        if detail:
            r = results_p
            print(f"  {pname}: base={r.get('base',0):.4f}"
                  f" basal_lead={r.get('basal_lead',0):.4f}"
                  f" full_lead={r.get('full_lead',0):.4f}"
                  f" Δ_basal={r.get('basal_lead',0)-r.get('base',0):+.4f}")

    means = {k: float(np.mean(v)) if v else 0
             for k, v in [('base', scores_base), ('basal_lead', scores_basal),
                          ('full_lead', scores_full)]}
    basal_delta = means['basal_lead'] - means['base']
    full_delta = means['full_lead'] - means['base']

    return {
        'name': 'EXP-1162',
        'status': 'pass',
        'detail': (f"base={means['base']:.4f} basal_lead={means['basal_lead']:.4f}"
                   f" full_lead={means['full_lead']:.4f}"
                   f" Δ_basal={basal_delta:+.4f} Δ_full={full_delta:+.4f}"),
        'per_patient': per_patient,
        'results': means,
    }


# ---------------------------------------------------------------------------
# EXP-1163: Bolus-Only Lead (Leakage Quantification)
# ---------------------------------------------------------------------------

def exp_1163_bolus_only_lead(patients, detail=False):
    """Lead ONLY bolus channels (4,5) by 45min — quantifies leakage from future boluses."""
    per_patient = {}
    scores_base, scores_bolus, scores_full = [], [], []
    lead_steps = 9

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']
        g = glucose / GLUCOSE_SCALE
        pk = p['pk']
        n = len(g)

        X_base_list, X_bolus_list, X_full_list = [], [], []
        y_list, g_cur_list = [], []

        for i in range(0, n - WINDOW - HORIZON - lead_steps, STRIDE):
            g_win = g[i:i + WINDOW]
            if np.isnan(g_win).mean() > 0.3:
                continue
            g_win = np.nan_to_num(
                g_win, nan=np.nanmean(g_win) if np.any(~np.isnan(g_win)) else 0.4)
            p_win = physics[i:i + WINDOW]
            if np.isnan(p_win).any():
                p_win = np.nan_to_num(p_win, nan=0.0)

            pk_cur = pk[i:i + WINDOW]
            if np.isnan(pk_cur).any():
                pk_cur = np.nan_to_num(pk_cur, nan=0.0)

            pk_lead_start = i + lead_steps
            pk_lead_end = pk_lead_start + WINDOW
            if pk_lead_end > n:
                continue
            pk_future = pk[pk_lead_start:pk_lead_end]
            if np.isnan(pk_future).any():
                pk_future = np.nan_to_num(pk_future, nan=0.0)

            y_val = g[i + WINDOW + HORIZON - 1]
            if np.isnan(y_val):
                continue

            g_current = g_win[-1]
            base_feats = np.concatenate([g_win, p_win.ravel()])

            # Base: lag0 PK only
            feat_base = np.concatenate([
                base_feats, pk_cur.mean(axis=0), pk_cur[-1]])

            # Bolus-only lead: future for channels 4,5 only
            feat_bolus = np.concatenate([
                base_feats, pk_cur.mean(axis=0), pk_cur[-1],
                pk_future.mean(axis=0)[4:6],
                pk_future[-1, 4:6],
            ])

            # Full lead
            feat_full = np.concatenate([
                base_feats, pk_future.mean(axis=0), pk_future[-1]])

            X_base_list.append(feat_base)
            X_bolus_list.append(feat_bolus)
            X_full_list.append(feat_full)
            y_list.append(y_val)
            g_cur_list.append(g_current)

        results_p = {}
        y_arr = np.array(y_list)
        g_cur_arr = np.array(g_cur_list)

        for X_list, key, score_list in [
            (X_base_list, 'base', scores_base),
            (X_bolus_list, 'bolus_lead', scores_bolus),
            (X_full_list, 'full_lead', scores_full),
        ]:
            if len(X_list) < 100:
                results_p[key] = 0.0
                continue
            X = np.nan_to_num(np.array(X_list), nan=0.0)
            y_dg = y_arr - g_cur_arr
            X_tr, X_te, y_tr, y_te = split_data(X, y_dg)
            g_cur_te = g_cur_arr[len(X) - len(X_te):]

            m = make_xgb(n_estimators=300, max_depth=3)
            m.fit(X_tr, y_tr)
            pred = m.predict(X_te) + g_cur_te
            y_abs = y_te + g_cur_te
            r2 = compute_r2(y_abs, pred)
            results_p[key] = r2
            score_list.append(r2)

        per_patient[pname] = results_p
        if detail:
            r = results_p
            bolus_frac = 0.0
            full_d = r.get('full_lead', 0) - r.get('base', 0)
            bolus_d = r.get('bolus_lead', 0) - r.get('base', 0)
            if full_d > 0.001:
                bolus_frac = bolus_d / full_d
            print(f"  {pname}: base={r.get('base',0):.4f}"
                  f" bolus_lead={r.get('bolus_lead',0):.4f}"
                  f" full_lead={r.get('full_lead',0):.4f}"
                  f" bolus_frac_of_lead={bolus_frac:.1%}")

    means = {k: float(np.mean(v)) if v else 0
             for k, v in [('base', scores_base), ('bolus_lead', scores_bolus),
                          ('full_lead', scores_full)]}
    bolus_delta = means['bolus_lead'] - means['base']
    full_delta = means['full_lead'] - means['base']
    bolus_frac = bolus_delta / full_delta if full_delta > 0.001 else 0

    return {
        'name': 'EXP-1163',
        'status': 'pass',
        'detail': (f"base={means['base']:.4f} bolus_lead={means['bolus_lead']:.4f}"
                   f" full_lead={means['full_lead']:.4f}"
                   f" Δ_bolus={bolus_delta:+.4f} bolus_share={bolus_frac:.1%}"),
        'per_patient': per_patient,
        'results': means,
    }


# ---------------------------------------------------------------------------
# EXP-1164: PK Rate of Change Features (Causal Alternative)
# ---------------------------------------------------------------------------

def exp_1164_pk_rate_of_change(patients, detail=False):
    """Use rate of change and acceleration of PK channels — fully causal."""
    per_patient = {}
    scores_base, scores_roc = [], []

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']
        g = glucose / GLUCOSE_SCALE
        pk = p['pk']
        n = len(g)

        X_base_list, X_roc_list = [], []
        y_list, g_cur_list = [], []

        for i in range(0, n - WINDOW - HORIZON, STRIDE):
            g_win = g[i:i + WINDOW]
            if np.isnan(g_win).mean() > 0.3:
                continue
            g_win = np.nan_to_num(
                g_win, nan=np.nanmean(g_win) if np.any(~np.isnan(g_win)) else 0.4)
            p_win = physics[i:i + WINDOW]
            if np.isnan(p_win).any():
                p_win = np.nan_to_num(p_win, nan=0.0)

            pk_win = pk[i:i + WINDOW]
            if np.isnan(pk_win).any():
                pk_win = np.nan_to_num(pk_win, nan=0.0)

            y_val = g[i + WINDOW + HORIZON - 1]
            if np.isnan(y_val):
                continue

            g_current = g_win[-1]
            pk_mean = pk_win.mean(axis=0)
            pk_last = pk_win[-1]
            base_feats = np.concatenate([g_win, p_win.ravel(), pk_mean, pk_last])

            # Rate of change and acceleration
            pk_roc, pk_accel = compute_pk_roc(pk_win)

            feat_base = base_feats
            feat_roc = np.concatenate([base_feats, pk_roc, pk_accel])

            X_base_list.append(feat_base)
            X_roc_list.append(feat_roc)
            y_list.append(y_val)
            g_cur_list.append(g_current)

        results_p = {}
        y_arr = np.array(y_list)
        g_cur_arr = np.array(g_cur_list)

        for X_list, key, score_list in [
            (X_base_list, 'base', scores_base),
            (X_roc_list, 'pk_roc', scores_roc),
        ]:
            if len(X_list) < 100:
                results_p[key] = 0.0
                continue
            X = np.nan_to_num(np.array(X_list), nan=0.0)
            y_dg = y_arr - g_cur_arr
            X_tr, X_te, y_tr, y_te = split_data(X, y_dg)
            g_cur_te = g_cur_arr[len(X) - len(X_te):]

            m = make_xgb(n_estimators=300, max_depth=3)
            m.fit(X_tr, y_tr)
            pred = m.predict(X_te) + g_cur_te
            y_abs = y_te + g_cur_te
            r2 = compute_r2(y_abs, pred)
            results_p[key] = r2
            score_list.append(r2)

        per_patient[pname] = results_p
        if detail:
            r = results_p
            print(f"  {pname}: base={r.get('base',0):.4f}"
                  f" pk_roc={r.get('pk_roc',0):.4f}"
                  f" Δ={r.get('pk_roc',0)-r.get('base',0):+.4f}")

    means = {k: float(np.mean(v)) if v else 0
             for k, v in [('base', scores_base), ('pk_roc', scores_roc)]}
    delta = means['pk_roc'] - means['base']
    wins = sum(1 for pp in per_patient.values()
               if pp.get('pk_roc', 0) > pp.get('base', 0))

    return {
        'name': 'EXP-1164',
        'status': 'pass',
        'detail': (f"base={means['base']:.4f} pk_roc={means['pk_roc']:.4f}"
                   f" Δ={delta:+.4f} (wins={wins}/{len(patients)})"),
        'per_patient': per_patient,
        'results': means,
    }


# ---------------------------------------------------------------------------
# EXP-1165: PK Trajectory Features (Causal Alternative)
# ---------------------------------------------------------------------------

def exp_1165_pk_trajectory(patients, detail=False):
    """Extract trajectory features (slope, curvature, peak timing) — fully causal."""
    per_patient = {}
    scores_base, scores_traj = [], []

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']
        g = glucose / GLUCOSE_SCALE
        pk = p['pk']
        n = len(g)

        X_base_list, X_traj_list = [], []
        y_list, g_cur_list = [], []

        for i in range(0, n - WINDOW - HORIZON, STRIDE):
            g_win = g[i:i + WINDOW]
            if np.isnan(g_win).mean() > 0.3:
                continue
            g_win = np.nan_to_num(
                g_win, nan=np.nanmean(g_win) if np.any(~np.isnan(g_win)) else 0.4)
            p_win = physics[i:i + WINDOW]
            if np.isnan(p_win).any():
                p_win = np.nan_to_num(p_win, nan=0.0)

            pk_win = pk[i:i + WINDOW]
            if np.isnan(pk_win).any():
                pk_win = np.nan_to_num(pk_win, nan=0.0)

            y_val = g[i + WINDOW + HORIZON - 1]
            if np.isnan(y_val):
                continue

            g_current = g_win[-1]
            pk_mean = pk_win.mean(axis=0)
            pk_last = pk_win[-1]
            base_feats = np.concatenate([g_win, p_win.ravel(), pk_mean, pk_last])

            # Trajectory features
            traj = compute_pk_trajectory(pk_win)

            feat_base = base_feats
            feat_traj = np.concatenate([base_feats, traj])

            X_base_list.append(feat_base)
            X_traj_list.append(feat_traj)
            y_list.append(y_val)
            g_cur_list.append(g_current)

        results_p = {}
        y_arr = np.array(y_list)
        g_cur_arr = np.array(g_cur_list)

        for X_list, key, score_list in [
            (X_base_list, 'base', scores_base),
            (X_traj_list, 'pk_traj', scores_traj),
        ]:
            if len(X_list) < 100:
                results_p[key] = 0.0
                continue
            X = np.nan_to_num(np.array(X_list), nan=0.0)
            y_dg = y_arr - g_cur_arr
            X_tr, X_te, y_tr, y_te = split_data(X, y_dg)
            g_cur_te = g_cur_arr[len(X) - len(X_te):]

            m = make_xgb(n_estimators=300, max_depth=3)
            m.fit(X_tr, y_tr)
            pred = m.predict(X_te) + g_cur_te
            y_abs = y_te + g_cur_te
            r2 = compute_r2(y_abs, pred)
            results_p[key] = r2
            score_list.append(r2)

        per_patient[pname] = results_p
        if detail:
            r = results_p
            print(f"  {pname}: base={r.get('base',0):.4f}"
                  f" pk_traj={r.get('pk_traj',0):.4f}"
                  f" Δ={r.get('pk_traj',0)-r.get('base',0):+.4f}")

    means = {k: float(np.mean(v)) if v else 0
             for k, v in [('base', scores_base), ('pk_traj', scores_traj)]}
    delta = means['pk_traj'] - means['base']
    wins = sum(1 for pp in per_patient.values()
               if pp.get('pk_traj', 0) > pp.get('base', 0))

    return {
        'name': 'EXP-1165',
        'status': 'pass',
        'detail': (f"base={means['base']:.4f} pk_traj={means['pk_traj']:.4f}"
                   f" Δ={delta:+.4f} (wins={wins}/{len(patients)})"),
        'per_patient': per_patient,
        'results': means,
    }


# ---------------------------------------------------------------------------
# EXP-1166: Causal PK Projection + Enhanced Features
# ---------------------------------------------------------------------------

def exp_1166_causal_enhanced(patients, detail=False):
    """Causal PK projection + all enhanced features — the honest SOTA attempt."""
    per_patient = {}
    scores_base, scores_enh, scores_causal_enh = [], [], []

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']
        g = glucose / GLUCOSE_SCALE
        pk = p['pk']
        n = len(g)
        lead_steps = 9

        X_base_list, X_enh_list, X_causal_enh_list = [], [], []
        y_list, g_cur_list = [], []

        max_i = n - WINDOW - HORIZON - lead_steps
        for i in range(0, max_i, STRIDE):
            g_win = g[i:i + WINDOW]
            if np.isnan(g_win).mean() > 0.3:
                continue
            g_win = np.nan_to_num(
                g_win, nan=np.nanmean(g_win) if np.any(~np.isnan(g_win)) else 0.4)
            p_win = physics[i:i + WINDOW]
            if np.isnan(p_win).any():
                p_win = np.nan_to_num(p_win, nan=0.0)

            pk_win = pk[i:i + WINDOW]
            if np.isnan(pk_win).any():
                pk_win = np.nan_to_num(pk_win, nan=0.0)

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

            pk_mean = pk_win.mean(axis=0)
            pk_last = pk_win[-1]

            # Enhanced features
            deriv_feats = np.array(compute_derivative_features(g_win))
            hour = get_hour(p, i + WINDOW - 1)
            time_feats = np.array(compute_time_features(hour))
            inter_feats = np.array(compute_interaction_features(g_win, pk_win))

            # Causal PK projection
            pk_projected = project_pk_forward(pk_last, lead_steps)

            # Base: no enhancements
            feat_base = np.concatenate([base, phys_inter, stats, pk_mean, pk_last])

            # Enhanced: all enhancements, no projection
            feat_enh = np.concatenate([
                base, phys_inter, stats, pk_mean, pk_last,
                deriv_feats, time_feats, inter_feats,
            ])

            # Causal enhanced: all enhancements + causal projection
            feat_causal_enh = np.concatenate([
                base, phys_inter, stats, pk_mean, pk_last,
                deriv_feats, time_feats, inter_feats,
                pk_projected,
            ])

            X_base_list.append(feat_base)
            X_enh_list.append(feat_enh)
            X_causal_enh_list.append(feat_causal_enh)
            y_list.append(y_val)
            g_cur_list.append(g_current)

        results_p = {}
        y_arr = np.array(y_list)
        g_cur_arr = np.array(g_cur_list)

        for X_list, key, score_list in [
            (X_base_list, 'base', scores_base),
            (X_enh_list, 'enhanced', scores_enh),
            (X_causal_enh_list, 'causal_enhanced', scores_causal_enh),
        ]:
            if len(X_list) < 100:
                results_p[key] = 0.0
                continue
            X = np.nan_to_num(np.array(X_list), nan=0.0)
            y_dg = y_arr - g_cur_arr
            X_tr, X_te, y_tr, y_te = split_data(X, y_dg)
            g_cur_te = g_cur_arr[len(X) - len(X_te):]

            m = make_xgb(n_estimators=300, max_depth=3)
            m.fit(X_tr, y_tr)
            pred = m.predict(X_te) + g_cur_te
            y_abs = y_te + g_cur_te
            r2 = compute_r2(y_abs, pred)
            results_p[key] = r2
            score_list.append(r2)

        per_patient[pname] = results_p
        if detail:
            r = results_p
            print(f"  {pname}: base={r.get('base',0):.4f}"
                  f" enh={r.get('enhanced',0):.4f}"
                  f" causal_enh={r.get('causal_enhanced',0):.4f}"
                  f" Δ={r.get('causal_enhanced',0)-r.get('base',0):+.4f}")

    means = {k: float(np.mean(v)) if v else 0
             for k, v in [('base', scores_base), ('enhanced', scores_enh),
                          ('causal_enhanced', scores_causal_enh)]}
    delta_enh = means['enhanced'] - means['base']
    delta_causal = means['causal_enhanced'] - means['base']
    proj_gain = means['causal_enhanced'] - means['enhanced']

    return {
        'name': 'EXP-1166',
        'status': 'pass',
        'detail': (f"base={means['base']:.4f} enh={means['enhanced']:.4f}"
                   f" causal_enh={means['causal_enhanced']:.4f}"
                   f" Δ_enh={delta_enh:+.4f} Δ_causal={delta_causal:+.4f}"
                   f" proj_gain={proj_gain:+.4f}"),
        'per_patient': per_patient,
        'results': means,
    }


# ---------------------------------------------------------------------------
# EXP-1167: PK Momentum Features
# ---------------------------------------------------------------------------

def exp_1167_pk_momentum(patients, detail=False):
    """Exponentially weighted PK momentum — captures trending direction causally."""
    per_patient = {}
    scores_base, scores_momentum = [], []

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']
        g = glucose / GLUCOSE_SCALE
        pk = p['pk']
        n = len(g)

        X_base_list, X_mom_list = [], []
        y_list, g_cur_list = [], []

        for i in range(0, n - WINDOW - HORIZON, STRIDE):
            g_win = g[i:i + WINDOW]
            if np.isnan(g_win).mean() > 0.3:
                continue
            g_win = np.nan_to_num(
                g_win, nan=np.nanmean(g_win) if np.any(~np.isnan(g_win)) else 0.4)
            p_win = physics[i:i + WINDOW]
            if np.isnan(p_win).any():
                p_win = np.nan_to_num(p_win, nan=0.0)

            pk_win = pk[i:i + WINDOW]
            if np.isnan(pk_win).any():
                pk_win = np.nan_to_num(pk_win, nan=0.0)

            y_val = g[i + WINDOW + HORIZON - 1]
            if np.isnan(y_val):
                continue

            g_current = g_win[-1]
            pk_mean = pk_win.mean(axis=0)
            pk_last = pk_win[-1]
            base_feats = np.concatenate([g_win, p_win.ravel(), pk_mean, pk_last])

            # Momentum with two alpha values for different time scales
            momentum_fast = compute_pk_momentum(pk_win, alpha=0.3)
            momentum_slow = compute_pk_momentum(pk_win, alpha=0.1)

            feat_base = base_feats
            feat_mom = np.concatenate([base_feats, momentum_fast, momentum_slow])

            X_base_list.append(feat_base)
            X_mom_list.append(feat_mom)
            y_list.append(y_val)
            g_cur_list.append(g_current)

        results_p = {}
        y_arr = np.array(y_list)
        g_cur_arr = np.array(g_cur_list)

        for X_list, key, score_list in [
            (X_base_list, 'base', scores_base),
            (X_mom_list, 'momentum', scores_momentum),
        ]:
            if len(X_list) < 100:
                results_p[key] = 0.0
                continue
            X = np.nan_to_num(np.array(X_list), nan=0.0)
            y_dg = y_arr - g_cur_arr
            X_tr, X_te, y_tr, y_te = split_data(X, y_dg)
            g_cur_te = g_cur_arr[len(X) - len(X_te):]

            m = make_xgb(n_estimators=300, max_depth=3)
            m.fit(X_tr, y_tr)
            pred = m.predict(X_te) + g_cur_te
            y_abs = y_te + g_cur_te
            r2 = compute_r2(y_abs, pred)
            results_p[key] = r2
            score_list.append(r2)

        per_patient[pname] = results_p
        if detail:
            r = results_p
            print(f"  {pname}: base={r.get('base',0):.4f}"
                  f" momentum={r.get('momentum',0):.4f}"
                  f" Δ={r.get('momentum',0)-r.get('base',0):+.4f}")

    means = {k: float(np.mean(v)) if v else 0
             for k, v in [('base', scores_base), ('momentum', scores_momentum)]}
    delta = means['momentum'] - means['base']
    wins = sum(1 for pp in per_patient.values()
               if pp.get('momentum', 0) > pp.get('base', 0))

    return {
        'name': 'EXP-1167',
        'status': 'pass',
        'detail': (f"base={means['base']:.4f} momentum={means['momentum']:.4f}"
                   f" Δ={delta:+.4f} (wins={wins}/{len(patients)})"),
        'per_patient': per_patient,
        'results': means,
    }


# ---------------------------------------------------------------------------
# EXP-1168: Lead Leakage Quantification (Systematic)
# ---------------------------------------------------------------------------

def exp_1168_leakage_quantification(patients, detail=False):
    """For 5 lead times, decompose improvement into causal vs leaked components."""
    per_patient = {}
    lead_minutes = [15, 30, 45, 60, 75]
    lead_steps_list = [3, 6, 9, 12, 15]

    # Collect scores across patients for each lead and method
    all_base = []
    all_results = {lm: {'actual': [], 'basal_only': [], 'causal_proj': []}
                   for lm in lead_minutes}

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']
        g = glucose / GLUCOSE_SCALE
        pk = p['pk']
        n = len(g)

        max_lead = max(lead_steps_list)
        results_p = {'base': 0.0}

        # Build windows that work for ALL lead times
        X_base_list = []
        X_actual = {lm: [] for lm in lead_minutes}
        X_basal = {lm: [] for lm in lead_minutes}
        X_causal = {lm: [] for lm in lead_minutes}
        y_list, g_cur_list = [], []

        for i in range(0, n - WINDOW - HORIZON - max_lead, STRIDE):
            g_win = g[i:i + WINDOW]
            if np.isnan(g_win).mean() > 0.3:
                continue
            g_win = np.nan_to_num(
                g_win, nan=np.nanmean(g_win) if np.any(~np.isnan(g_win)) else 0.4)
            p_win = physics[i:i + WINDOW]
            if np.isnan(p_win).any():
                p_win = np.nan_to_num(p_win, nan=0.0)

            pk_cur = pk[i:i + WINDOW]
            if np.isnan(pk_cur).any():
                pk_cur = np.nan_to_num(pk_cur, nan=0.0)

            y_val = g[i + WINDOW + HORIZON - 1]
            if np.isnan(y_val):
                continue

            g_current = g_win[-1]
            base_feats = np.concatenate([g_win, p_win.ravel()])

            # Base
            feat_base = np.concatenate([base_feats, pk_cur.mean(axis=0), pk_cur[-1]])
            X_base_list.append(feat_base)

            valid = True
            for lm, ls in zip(lead_minutes, lead_steps_list):
                pk_lead_end = i + ls + WINDOW
                if pk_lead_end > n:
                    valid = False
                    break
                pk_future = pk[i + ls:pk_lead_end]
                if np.isnan(pk_future).any():
                    pk_future = np.nan_to_num(pk_future, nan=0.0)

                # Actual lead (potentially leaked)
                feat_actual = np.concatenate([
                    base_feats, pk_future.mean(axis=0), pk_future[-1]])
                X_actual[lm].append(feat_actual)

                # Basal-only lead: only channels 2,3 from future
                pk_hybrid = pk_cur.copy()
                pk_hybrid[:, 2:4] = pk_future[:, 2:4]
                feat_basal = np.concatenate([
                    base_feats, pk_hybrid.mean(axis=0), pk_hybrid[-1]])
                X_basal[lm].append(feat_basal)

                # Causal projection
                pk_projected = project_pk_forward(pk_cur[-1], ls)
                feat_causal = np.concatenate([
                    base_feats, pk_cur.mean(axis=0), pk_cur[-1], pk_projected])
                X_causal[lm].append(feat_causal)

            if not valid:
                # Remove the base entry we just added
                X_base_list.pop()
                continue

            y_list.append(y_val)
            g_cur_list.append(g_current)

        if len(X_base_list) < 100:
            per_patient[pname] = results_p
            continue

        y_arr = np.array(y_list)
        g_cur_arr = np.array(g_cur_list)
        y_dg = y_arr - g_cur_arr

        # Evaluate base
        X = np.nan_to_num(np.array(X_base_list), nan=0.0)
        X_tr, X_te, y_tr, y_te = split_data(X, y_dg)
        g_cur_te = g_cur_arr[len(X) - len(X_te):]
        m = make_xgb(n_estimators=300, max_depth=3)
        m.fit(X_tr, y_tr)
        pred = m.predict(X_te) + g_cur_te
        y_abs = y_te + g_cur_te
        r2_base = compute_r2(y_abs, pred)
        results_p['base'] = r2_base
        all_base.append(r2_base)

        # Evaluate each lead time × method
        for lm in lead_minutes:
            for method, X_dict in [('actual', X_actual),
                                   ('basal_only', X_basal),
                                   ('causal_proj', X_causal)]:
                X_m = np.nan_to_num(np.array(X_dict[lm]), nan=0.0)
                if len(X_m) < 100:
                    continue
                X_tr, X_te, y_tr, y_te = split_data(X_m, y_dg)
                g_cur_te = g_cur_arr[len(X_m) - len(X_te):]
                m2 = make_xgb(n_estimators=300, max_depth=3)
                m2.fit(X_tr, y_tr)
                pred2 = m2.predict(X_te) + g_cur_te
                y_abs2 = y_te + g_cur_te
                r2 = compute_r2(y_abs2, pred2)
                results_p[f'{method}_{lm}min'] = r2
                all_results[lm][method].append(r2)

        per_patient[pname] = results_p

    # Build leakage table
    mean_base = float(np.mean(all_base)) if all_base else 0
    table_rows = []
    for lm in lead_minutes:
        actual = float(np.mean(all_results[lm]['actual'])) if all_results[lm]['actual'] else mean_base
        basal = float(np.mean(all_results[lm]['basal_only'])) if all_results[lm]['basal_only'] else mean_base
        causal = float(np.mean(all_results[lm]['causal_proj'])) if all_results[lm]['causal_proj'] else mean_base
        total_gain = actual - mean_base
        causal_gain = causal - mean_base
        leakage = total_gain - causal_gain
        leak_frac = leakage / total_gain if total_gain > 0.001 else 0
        table_rows.append({
            'lead_min': lm, 'actual': actual, 'basal': basal,
            'causal': causal, 'total_gain': total_gain,
            'causal_gain': causal_gain, 'leakage': leakage,
            'leak_frac': leak_frac,
        })

    if detail:
        print(f"\n  {'Lead':>6} {'Actual':>8} {'Basal':>8} {'Causal':>8}"
              f" {'Δ_total':>8} {'Δ_causal':>8} {'Leak%':>7}")
        print(f"  {'-'*6} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*7}")
        for row in table_rows:
            print(f"  {row['lead_min']:>4}m"
                  f" {row['actual']:>8.4f} {row['basal']:>8.4f}"
                  f" {row['causal']:>8.4f} {row['total_gain']:>+8.4f}"
                  f" {row['causal_gain']:>+8.4f} {row['leak_frac']:>6.1%}")
        print(f"  base={mean_base:.4f}")

    best_row = max(table_rows, key=lambda r: r['causal_gain']) if table_rows else {}

    return {
        'name': 'EXP-1168',
        'status': 'pass',
        'detail': (f"base={mean_base:.4f}"
                   f" best_causal_at={best_row.get('lead_min','?')}min"
                   f" Δ_causal={best_row.get('causal_gain',0):+.4f}"
                   f" leak_frac@45min="
                   + (f"{table_rows[2]['leak_frac']:.1%}" if len(table_rows) > 2 else "?")),
        'per_patient': per_patient,
        'results': {'base': mean_base, 'table': table_rows},
    }


# ---------------------------------------------------------------------------
# EXP-1169: 5-Fold CV: Causal vs Leaked Lead
# ---------------------------------------------------------------------------

def exp_1169_cv_causal_vs_leaked(patients, detail=False):
    """Rigorous TimeSeriesSplit: base vs causal projection vs leaked lead."""
    from sklearn.model_selection import TimeSeriesSplit

    per_patient = {}
    all_base_cv, all_causal_cv, all_leaked_cv = [], [], []
    lead_steps = 9

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']
        g = glucose / GLUCOSE_SCALE
        pk = p['pk']
        n = len(g)

        # Build all three feature sets
        X_base_list, X_causal_list, X_leaked_list = [], [], []
        y_list, g_cur_list = [], []

        for i in range(0, n - WINDOW - HORIZON - lead_steps, STRIDE):
            g_win = g[i:i + WINDOW]
            if np.isnan(g_win).mean() > 0.3:
                continue
            g_win = np.nan_to_num(
                g_win, nan=np.nanmean(g_win) if np.any(~np.isnan(g_win)) else 0.4)
            p_win = physics[i:i + WINDOW]
            if np.isnan(p_win).any():
                p_win = np.nan_to_num(p_win, nan=0.0)

            pk_cur = pk[i:i + WINDOW]
            if np.isnan(pk_cur).any():
                pk_cur = np.nan_to_num(pk_cur, nan=0.0)

            pk_lead_end = i + lead_steps + WINDOW
            if pk_lead_end > n:
                continue
            pk_future = pk[i + lead_steps:pk_lead_end]
            if np.isnan(pk_future).any():
                pk_future = np.nan_to_num(pk_future, nan=0.0)

            y_val = g[i + WINDOW + HORIZON - 1]
            if np.isnan(y_val):
                continue

            g_current = g_win[-1]
            base_feats = np.concatenate([g_win, p_win.ravel()])

            # Base
            feat_base = np.concatenate([base_feats, pk_cur.mean(axis=0), pk_cur[-1]])
            # Causal projection
            pk_projected = project_pk_forward(pk_cur[-1], lead_steps)
            feat_causal = np.concatenate([base_feats, pk_cur.mean(axis=0), pk_cur[-1],
                                          pk_projected])
            # Leaked: actual future PK
            feat_leaked = np.concatenate([base_feats, pk_future.mean(axis=0), pk_future[-1]])

            X_base_list.append(feat_base)
            X_causal_list.append(feat_causal)
            X_leaked_list.append(feat_leaked)
            y_list.append(y_val)
            g_cur_list.append(g_current)

        if len(X_base_list) < 200:
            per_patient[pname] = {
                'base_cv': {'mean': 0, 'std': 0},
                'causal_cv': {'mean': 0, 'std': 0},
                'leaked_cv': {'mean': 0, 'std': 0},
            }
            continue

        y_arr = np.array(y_list)
        g_cur_arr = np.array(g_cur_list)

        results_p = {}
        for X_list, key, cv_list in [
            (X_base_list, 'base_cv', all_base_cv),
            (X_causal_list, 'causal_cv', all_causal_cv),
            (X_leaked_list, 'leaked_cv', all_leaked_cv),
        ]:
            X = np.nan_to_num(np.array(X_list), nan=0.0)
            y_dg = y_arr - g_cur_arr

            tscv = TimeSeriesSplit(n_splits=5)
            fold_scores = []
            for train_idx, test_idx in tscv.split(X):
                X_tr, X_te = X[train_idx], X[test_idx]
                y_tr, y_te = y_dg[train_idx], y_dg[test_idx]
                g_te = g_cur_arr[test_idx]

                m = make_xgb(n_estimators=300, max_depth=3)
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

        per_patient[pname] = results_p
        if detail:
            b = results_p['base_cv']
            c = results_p['causal_cv']
            l = results_p['leaked_cv']
            print(f"  {pname}: base_cv={b['mean']:.4f}±{b['std']:.3f}"
                  f" causal_cv={c['mean']:.4f}±{c['std']:.3f}"
                  f" leaked_cv={l['mean']:.4f}±{l['std']:.3f}"
                  f" Δ_causal={c['mean']-b['mean']:+.4f}"
                  f" Δ_leaked={l['mean']-b['mean']:+.4f}")

    mean_b = float(np.mean(all_base_cv)) if all_base_cv else 0
    mean_c = float(np.mean(all_causal_cv)) if all_causal_cv else 0
    mean_l = float(np.mean(all_leaked_cv)) if all_leaked_cv else 0
    causal_wins = sum(1 for pp in per_patient.values()
                      if pp.get('causal_cv', {}).get('mean', 0) >
                      pp.get('base_cv', {}).get('mean', 0))
    leaked_wins = sum(1 for pp in per_patient.values()
                      if pp.get('leaked_cv', {}).get('mean', 0) >
                      pp.get('base_cv', {}).get('mean', 0))

    return {
        'name': 'EXP-1169',
        'status': 'pass',
        'detail': (f"5-fold CV: base={mean_b:.4f} causal={mean_c:.4f}"
                   f" leaked={mean_l:.4f}"
                   f" Δ_causal={mean_c-mean_b:+.4f}"
                   f" Δ_leaked={mean_l-mean_b:+.4f}"
                   f" causal_wins={causal_wins} leaked_wins={leaked_wins}"),
        'per_patient': per_patient,
        'results': {'base_cv': mean_b, 'causal_cv': mean_c, 'leaked_cv': mean_l},
    }


# ---------------------------------------------------------------------------
# EXP-1170: Best Causal SOTA Pipeline
# ---------------------------------------------------------------------------

def exp_1170_best_causal_sota(patients, detail=False):
    """Combine ALL causal winners: projection + RoC + trajectory + momentum + enhanced."""
    per_patient = {}
    scores_base, scores_enh, scores_causal_sota = [], [], []
    lead_steps = 9

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']
        g = glucose / GLUCOSE_SCALE
        pk = p['pk']
        n = len(g)

        X_base_list, X_enh_list, X_sota_list = [], [], []
        y_list, g_cur_list = [], []

        max_i = n - WINDOW - HORIZON - lead_steps
        for i in range(0, max_i, STRIDE):
            g_win = g[i:i + WINDOW]
            if np.isnan(g_win).mean() > 0.3:
                continue
            g_win = np.nan_to_num(
                g_win, nan=np.nanmean(g_win) if np.any(~np.isnan(g_win)) else 0.4)
            p_win = physics[i:i + WINDOW]
            if np.isnan(p_win).any():
                p_win = np.nan_to_num(p_win, nan=0.0)

            pk_win = pk[i:i + WINDOW]
            if np.isnan(pk_win).any():
                pk_win = np.nan_to_num(pk_win, nan=0.0)

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

            pk_mean = pk_win.mean(axis=0)
            pk_last = pk_win[-1]

            # Enhanced features (proven winners)
            deriv_feats = np.array(compute_derivative_features(g_win))
            hour = get_hour(p, i + WINDOW - 1)
            time_feats = np.array(compute_time_features(hour))
            inter_feats = np.array(compute_interaction_features(g_win, pk_win))

            # Causal PK features
            pk_projected = project_pk_forward(pk_last, lead_steps)
            pk_roc, pk_accel = compute_pk_roc(pk_win)
            pk_traj = compute_pk_trajectory(pk_win)
            pk_mom_fast = compute_pk_momentum(pk_win, alpha=0.3)
            pk_mom_slow = compute_pk_momentum(pk_win, alpha=0.1)

            # Base (no enhancements)
            feat_base = np.concatenate([base, phys_inter, stats, pk_mean, pk_last])

            # Enhanced only (no causal PK extras)
            feat_enh = np.concatenate([
                base, phys_inter, stats, pk_mean, pk_last,
                deriv_feats, time_feats, inter_feats,
            ])

            # Full causal SOTA: everything
            feat_sota = np.concatenate([
                base, phys_inter, stats, pk_mean, pk_last,
                deriv_feats, time_feats, inter_feats,
                pk_projected,         # Causal PK projection (EXP-1161)
                pk_roc, pk_accel,     # PK rate of change (EXP-1164)
                pk_traj,              # PK trajectory features (EXP-1165)
                pk_mom_fast, pk_mom_slow,  # PK momentum (EXP-1167)
            ])

            X_base_list.append(feat_base)
            X_enh_list.append(feat_enh)
            X_sota_list.append(feat_sota)
            y_list.append(y_val)
            g_cur_list.append(g_current)

        results_p = {}
        y_arr = np.array(y_list)
        g_cur_arr = np.array(g_cur_list)

        for X_list, key, score_list in [
            (X_base_list, 'base', scores_base),
            (X_enh_list, 'enhanced', scores_enh),
            (X_sota_list, 'causal_sota', scores_causal_sota),
        ]:
            if len(X_list) < 100:
                results_p[key] = 0.0
                continue
            X = np.nan_to_num(np.array(X_list), nan=0.0)
            y_dg = y_arr - g_cur_arr

            # 3-way split for SOTA model with early stopping
            X_tr, X_val, X_te, y_tr, y_val, y_te = split_3way(X, y_dg)
            g_cur_te = g_cur_arr[len(X) - len(X_te):]

            m = make_xgb_sota()
            m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=False)
            pred = m.predict(X_te) + g_cur_te
            y_abs = y_te + g_cur_te
            r2 = compute_r2(y_abs, pred)
            results_p[key] = r2
            score_list.append(r2)

        per_patient[pname] = results_p
        if detail:
            r = results_p
            print(f"  {pname}: base={r.get('base',0):.4f}"
                  f" enh={r.get('enhanced',0):.4f}"
                  f" causal_sota={r.get('causal_sota',0):.4f}"
                  f" Δ_total={r.get('causal_sota',0)-r.get('base',0):+.4f}")

    means = {k: float(np.mean(v)) if v else 0
             for k, v in [('base', scores_base), ('enhanced', scores_enh),
                          ('causal_sota', scores_causal_sota)]}
    delta_enh = means['enhanced'] - means['base']
    delta_sota = means['causal_sota'] - means['base']
    wins = sum(1 for pp in per_patient.values()
               if pp.get('causal_sota', 0) > pp.get('enhanced', 0))

    return {
        'name': 'EXP-1170',
        'status': 'pass',
        'detail': (f"base={means['base']:.4f} enh={means['enhanced']:.4f}"
                   f" causal_sota={means['causal_sota']:.4f}"
                   f" Δ_enh={delta_enh:+.4f} Δ_sota={delta_sota:+.4f}"
                   f" (wins={wins}/{len(patients)})"),
        'per_patient': per_patient,
        'results': means,
    }


# ---------------------------------------------------------------------------
# Registry and main
# ---------------------------------------------------------------------------

EXPERIMENTS = [
    ('EXP-1161', 'Causal PK Projection (No Leakage)', exp_1161_causal_pk_projection),
    ('EXP-1162', 'Basal-Only Lead (Partial Causal)', exp_1162_basal_only_lead),
    ('EXP-1163', 'Bolus-Only Lead (Leakage Quantification)', exp_1163_bolus_only_lead),
    ('EXP-1164', 'PK Rate of Change Features', exp_1164_pk_rate_of_change),
    ('EXP-1165', 'PK Trajectory Features', exp_1165_pk_trajectory),
    ('EXP-1166', 'Causal PK Projection + Enhanced', exp_1166_causal_enhanced),
    ('EXP-1167', 'PK Momentum Features', exp_1167_pk_momentum),
    ('EXP-1168', 'Lead Leakage Quantification (Systematic)', exp_1168_leakage_quantification),
    ('EXP-1169', '5-Fold CV Causal vs Leaked Lead', exp_1169_cv_causal_vs_leaked),
    ('EXP-1170', 'Best Causal SOTA Pipeline', exp_1170_best_causal_sota),
]


def main():
    parser = argparse.ArgumentParser(
        description='EXP-1161-1170: Causal PK Leakage Resolution')
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--max-patients', type=int, default=11)
    parser.add_argument('--experiment', type=str,
                        help='Run only this experiment (e.g. EXP-1161)')
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
