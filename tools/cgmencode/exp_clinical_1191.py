#!/usr/bin/env python3
"""EXP-1191 to EXP-1200: Combined + AR + Multi-Horizon + Production Pipeline.

Campaign status after 190 experiments (EXP-1001 to EXP-1190):
- Combined pipeline = best offline: R²=0.551 single, 0.488 CV
  (enhanced features + multi-horizon + tuned XGBoost + PK momentum + dawn)
- Linear AR correction = biggest production win: +0.124 R², reaching 0.655
  (α·r[t-1] + β·r[t-2] fitted on validation residuals via OLS)
- LSTM overfits — avoid LSTM approaches
- Log-glucose hurts — XGBoost handles nonlinearity natively
- XGBoost stacking hurts — single well-tuned model beats two-stage

This batch combines all validated winners and explores AR depth, multi-horizon,
recursive prediction, attention weighting, clustering, online learning,
error-aware intervals, feature interactions, and the grand final benchmark:

  EXP-1191: Combined Pipeline + AR Correction (Full Stack)  ★★★★★
  EXP-1192: AR Correction Depth Analysis                    ★★★★
  EXP-1193: Multi-Horizon Prediction (30, 60, 90, 120 min)  ★★★★
  EXP-1194: Recursive Multi-Step Prediction                 ★★★
  EXP-1195: Attention-Weighted Features                     ★★★
  EXP-1196: Patient Clustering + Cluster Models             ★★★
  EXP-1197: Online Learning Simulation                      ★★★★
  EXP-1198: Error-Aware Prediction Intervals                ★★★★
  EXP-1199: Feature Interaction Discovery                   ★★★
  EXP-1200: Grand Final Benchmark — Best Known Pipeline     ★★★★★

Run:
    PYTHONPATH=tools python -m cgmencode.exp_clinical_1191 --detail --save --max-patients 11
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

PATIENTS_DIR = str(Path(__file__).resolve().parent.parent.parent
                   / 'externals' / 'ns-data' / 'patients')
GLUCOSE_SCALE = 400.0
WINDOW = 24       # 2 hours at 5-min intervals
HORIZON = 12      # 1 hour ahead
STRIDE = 6        # 30-min stride


# ---------------------------------------------------------------------------
# Shared helpers (mirror exp_clinical_1181 patterns)
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
# Feature builders (from exp_clinical_1181)
# ---------------------------------------------------------------------------

def compute_derivative_features(g_win):
    """Compute 10 glucose velocity/acceleration features."""
    d1 = np.diff(g_win)
    d2 = np.diff(d1) if len(d1) > 1 else np.array([0.0])
    feats = [
        d1[-1] if len(d1) > 0 else 0,
        np.mean(d1[-6:]) if len(d1) >= 6 else (np.mean(d1) if len(d1) > 0 else 0),
        np.mean(d1[-12:]) if len(d1) >= 12 else (np.mean(d1) if len(d1) > 0 else 0),
        d2[-1] if len(d2) > 0 else 0,
        np.mean(d2[-6:]) if len(d2) >= 6 else (np.mean(d2) if len(d2) > 0 else 0),
        float(np.average(d1[-6:], weights=np.exp(np.linspace(-1, 0, min(6, len(d1))))))
        if len(d1) > 0 else 0,
        np.std(g_win[-12:]) if len(g_win) >= 12 else np.std(g_win),
        np.std(g_win[-6:]) if len(g_win) >= 6 else np.std(g_win),
        np.max(np.abs(d1[-6:])) if len(d1) >= 6 else (np.max(np.abs(d1)) if len(d1) > 0 else 0),
        float(np.sum(np.diff(np.sign(d1[-12:])) != 0) / 12.0)
        if len(d1) >= 12 else 0,
    ]
    return feats


def compute_time_features(hour):
    """11 circadian + meal-timing features."""
    hour_rad = 2 * np.pi * hour / 24.0
    dawn_proximity = np.exp(-((hour - 5.0) ** 2) / (2 * 1.5 ** 2))
    dawn_ramp = max(0.0, 1.0 - abs(hour - 5.0) / 3.0)
    post_dawn = np.exp(-((hour - 8.0) ** 2) / (2 * 2.0 ** 2))
    cortisol_proxy = np.exp(-((hour - 7.0) ** 2) / (2 * 2.5 ** 2))
    return [
        np.sin(hour_rad), np.cos(hour_rad),
        1.0 if 3 <= hour < 7 else 0.0,
        1.0 if 7 <= hour < 12 else 0.0,
        1.0 if 12 <= hour < 17 else 0.0,
        1.0 if 17 <= hour < 22 else 0.0,
        1.0 if hour >= 22 or hour < 3 else 0.0,
        dawn_proximity, dawn_ramp, post_dawn, cortisol_proxy,
    ]


def compute_interaction_features(g_win, pk_win):
    """10 cross-term features: glucose × insulin/carb state."""
    iob = pk_win[:, 0]
    activity = pk_win[:, 1]
    cob = pk_win[:, 6] if pk_win.shape[1] > 6 else np.zeros(len(pk_win))
    carb_act = pk_win[:, 7] if pk_win.shape[1] > 7 else np.zeros(len(pk_win))
    g_last = g_win[-1]
    g_mean = np.mean(g_win)
    d1 = np.diff(g_win)
    g_trend = np.mean(d1[-6:]) if len(d1) >= 6 else (np.mean(d1) if len(d1) > 0 else 0)
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
    """EMA-weighted PK delta from slow baseline."""
    n = len(pk_win)
    if n < 2:
        return np.zeros(pk_win.shape[1] if pk_win.ndim > 1 else 1)
    weights = np.exp(-alpha * np.arange(n)[::-1])
    weights /= weights.sum()
    pk_ema_slow = np.average(pk_win, axis=0, weights=weights)
    return pk_win[-1] - pk_ema_slow


def _build_window_features(p, g_win, p_win, pk_win, i, window):
    """Build the full enhanced feature vector for one window.

    Returns a 1-D numpy array with all feature groups concatenated.
    """
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
    return np.concatenate(parts)


def build_enhanced_features(p, glucose, physics, window=WINDOW,
                            horizon=HORIZON, stride=STRIDE):
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

        feat = _build_window_features(p, g_win, p_win, pk_win, i, window)
        X_list.append(feat)
        y_list.append(y_val)
        g_cur_list.append(g_win[-1])

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

        feat = _build_window_features(p, g_win, p_win, pk_win, i, window)
        X_list.append(feat)
        for h in horizons:
            y_dict[h].append(targets[h])
        g_cur_list.append(g_win[-1])

    if len(X_list) == 0:
        empty = np.array([]).reshape(0, 1)
        return empty, {h: np.array([]) for h in horizons}, np.array([])
    return (np.array(X_list),
            {h: np.array(y_dict[h]) for h in horizons},
            np.array(g_cur_list))


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
    best_params = grid[1]
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


def _fit_ar_coeffs(residuals, order=2):
    """Fit AR coefficients on a residual sequence via OLS.

    Returns coefficient array of length *order*, or zeros on failure.
    """
    n = len(residuals)
    if n <= order + 1:
        return np.zeros(order)
    R = np.column_stack([residuals[order - 1 - j:n - 1 - j]
                         for j in range(order)])
    y_r = residuals[order:]
    try:
        coeffs, _, _, _ = np.linalg.lstsq(R, y_r, rcond=None)
        return coeffs
    except Exception:
        return np.zeros(order)


def _apply_ar_causal(pred_te, residuals_te, coeffs, bootstrap_resids):
    """Apply AR correction sequentially using a causal rolling buffer.

    *bootstrap_resids* seeds the buffer (last *order* validation residuals).
    Returns corrected prediction array (same length as pred_te).
    """
    order = len(coeffs)
    buf = list(bootstrap_resids[-order:])
    corrections = np.zeros(len(pred_te))
    for t in range(len(pred_te)):
        corr = sum(coeffs[j] * buf[-(j + 1)] for j in range(order))
        corrections[t] = corr
        buf.append(residuals_te[t])
    return pred_te + corrections


# ---------------------------------------------------------------------------
# EXP-1191: Combined Pipeline + AR Correction (Full Stack)
# ---------------------------------------------------------------------------

def exp_1191_combined_ar(patients, detail=False):
    """Ultimate production model: combined pipeline (EXP-1181) + linear AR
    correction (EXP-1182).

    Tests two XGBoost param sets (d3/lr0.03 and d6/lr0.03) and picks best per
    patient.  AR(2) coefficients fitted on validation residuals, applied
    causally to test predictions.
    """
    per_patient = {}
    scores_base, scores_combined, scores_ar = [], [], []
    horizons = [6, 12, 18]
    h_weights = {6: 0.2, 12: 0.6, 18: 0.2}

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']

        # Baseline
        X_base, y_base, g_cur_base = build_base_windows(glucose, p['pk'], physics)
        if len(X_base) < 200:
            per_patient[pname] = {'base': 0, 'combined': 0, 'combined_ar': 0}
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

        # Combined pipeline
        X_mh, y_mh, g_cur_mh = build_enhanced_multi_horizon(
            p, glucose, physics, horizons=horizons)
        if len(X_mh) < 200:
            per_patient[pname] = {'base': r2_base, 'combined': r2_base,
                                  'combined_ar': r2_base, 'delta_ar': 0}
            scores_base.append(r2_base)
            scores_combined.append(r2_base)
            scores_ar.append(r2_base)
            continue
        X_mh = np.nan_to_num(X_mh, nan=0.0)

        y_dg_60 = y_mh[12] - g_cur_mh
        X_tr, X_va, X_te, y_tr_60, y_va_60, y_te_60 = split_3way(X_mh, y_dg_60)
        g_cur_va = g_cur_mh[len(X_tr):len(X_tr) + len(X_va)]
        g_cur_te = g_cur_mh[len(X_mh) - len(X_te):]

        # Try two param sets, pick best on validation
        param_sets = [
            dict(max_depth=3, learning_rate=0.03),
            dict(max_depth=6, learning_rate=0.03),
        ]
        best_va_r2 = -1e9
        best_preds_va = best_preds_te = None
        best_params = param_sets[0]
        for ps in param_sets:
            preds_h_va, preds_h_te = {}, {}
            for h in horizons:
                y_dg_h = y_mh[h] - g_cur_mh
                _, _, _, y_tr_h, y_va_h, y_te_h = split_3way(X_mh, y_dg_h)
                m = make_xgb(n_estimators=500, subsample=0.8,
                             colsample_bytree=0.8, **ps)
                m.fit(X_tr, y_tr_h, eval_set=[(X_va, y_va_h)], verbose=False)
                preds_h_va[h] = m.predict(X_va)
                preds_h_te[h] = m.predict(X_te)
            comb_va = sum(h_weights[h] * preds_h_va[h] for h in horizons)
            r2_va = compute_r2(y_va_60, comb_va)
            if r2_va > best_va_r2:
                best_va_r2 = r2_va
                best_preds_va = comb_va
                best_preds_te = sum(h_weights[h] * preds_h_te[h]
                                    for h in horizons)
                best_params = ps

        combined_abs = best_preds_te + g_cur_te
        y_abs_te = y_te_60 + g_cur_te
        r2_combined = compute_r2(y_abs_te, combined_abs)

        # AR(2) correction: fit on validation residuals, apply to test
        resid_va = y_va_60 - best_preds_va
        resid_te = y_te_60 - best_preds_te
        coeffs = _fit_ar_coeffs(resid_va, order=2)
        corrected = _apply_ar_causal(
            best_preds_te, resid_te, coeffs,
            bootstrap_resids=resid_va)
        pred_ar_abs = corrected + g_cur_te
        r2_ar = compute_r2(y_abs_te, pred_ar_abs)

        delta_ar = r2_ar - r2_base
        per_patient[pname] = {
            'base': float(r2_base), 'combined': float(r2_combined),
            'combined_ar': float(r2_ar), 'delta_ar': float(delta_ar),
            'ar_coeffs': [float(c) for c in coeffs],
            'tuned_params': best_params,
        }
        scores_base.append(r2_base)
        scores_combined.append(r2_combined)
        scores_ar.append(r2_ar)

        if detail:
            print(f"  {pname}: base={r2_base:.4f} combined={r2_combined:.4f}"
                  f" +AR={r2_ar:.4f} Δ={delta_ar:+.4f}"
                  f" α={coeffs[0]:.3f} β={coeffs[1]:.3f}")

    mean_b = float(np.mean(scores_base)) if scores_base else 0
    mean_c = float(np.mean(scores_combined)) if scores_combined else 0
    mean_a = float(np.mean(scores_ar)) if scores_ar else 0
    wins = sum(1 for pp in per_patient.values() if pp.get('delta_ar', 0) > 0)

    return {
        'name': 'EXP-1191',
        'status': 'pass',
        'detail': (f"base={mean_b:.4f} combined={mean_c:.4f}"
                   f" +AR={mean_a:.4f}"
                   f" Δ_AR={mean_a - mean_b:+.4f}"
                   f" (wins={wins}/{len(patients)})"),
        'per_patient': per_patient,
        'results': {'base': mean_b, 'combined': mean_c,
                    'combined_ar': mean_a,
                    'delta_combined': mean_c - mean_b,
                    'delta_ar': mean_a - mean_b, 'wins': wins},
    }


# ---------------------------------------------------------------------------
# EXP-1192: AR Correction Depth Analysis
# ---------------------------------------------------------------------------

def exp_1192_ar_depth(patients, detail=False):
    """Test AR orders 1, 2, 3, 5, 10 and a nonlinear AR (small XGBoost on
    past residuals).  Fit on validation residuals, evaluate on test.
    """
    per_patient = {}
    ar_orders = [1, 2, 3, 5, 10]
    # Collect per-order mean scores for summary
    order_scores = {o: [] for o in ar_orders}
    order_scores['nonlinear'] = []
    base_scores = []

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']

        X_enh, y_enh, g_cur = build_enhanced_features(p, glucose, physics)
        if len(X_enh) < 300:
            per_patient[pname] = {'base': 0}
            continue
        X_enh = np.nan_to_num(X_enh, nan=0.0)
        y_dg = y_enh - g_cur

        X_tr, X_va, X_te, y_tr, y_va, y_te = split_3way(X_enh, y_dg)
        g_cur_te = g_cur[len(X_enh) - len(X_te):]
        y_abs_te = y_te + g_cur_te

        m = make_xgb_sota()
        m.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
        pred_va = m.predict(X_va)
        pred_te = m.predict(X_te)
        resid_va = y_va - pred_va
        resid_te = y_te - pred_te

        pred_abs = pred_te + g_cur_te
        r2_base = compute_r2(y_abs_te, pred_abs)
        base_scores.append(r2_base)

        p_result = {'base': float(r2_base)}

        # Linear AR at each order
        for order in ar_orders:
            coeffs = _fit_ar_coeffs(resid_va, order=order)
            corrected = _apply_ar_causal(
                pred_te, resid_te, coeffs,
                bootstrap_resids=resid_va)
            pred_ar = corrected + g_cur_te
            r2_ar = compute_r2(y_abs_te, pred_ar)
            key = f'AR({order})'
            p_result[key] = float(r2_ar)
            p_result[f'delta_{key}'] = float(r2_ar - r2_base)
            order_scores[order].append(r2_ar)

        # Nonlinear AR: small XGBoost on past-10 residuals
        nl_order = 10
        if len(resid_va) > nl_order + 10:
            R_va = np.column_stack([resid_va[nl_order - 1 - j:len(resid_va) - 1 - j]
                                    for j in range(nl_order)])
            y_r_va = resid_va[nl_order:]
            m_nl = make_xgb(n_estimators=50, max_depth=2, learning_rate=0.1)
            # Use last 20% of R_va as eval set for early stopping
            split_pt = int(len(R_va) * 0.8)
            m_nl.fit(R_va[:split_pt], y_r_va[:split_pt],
                     eval_set=[(R_va[split_pt:], y_r_va[split_pt:])],
                     verbose=False)
            # Apply causally on test
            buf = list(resid_va[-(nl_order):])
            corrections = np.zeros(len(resid_te))
            for t in range(len(resid_te)):
                feat_row = np.array(buf[-nl_order:]).reshape(1, -1)
                corrections[t] = float(m_nl.predict(feat_row)[0])
                buf.append(resid_te[t])
            pred_nl = pred_te + corrections + g_cur_te
            r2_nl = compute_r2(y_abs_te, pred_nl)
        else:
            r2_nl = r2_base
        p_result['nonlinear'] = float(r2_nl)
        p_result['delta_nonlinear'] = float(r2_nl - r2_base)
        order_scores['nonlinear'].append(r2_nl)

        per_patient[pname] = p_result

        if detail:
            parts = [f"base={r2_base:.4f}"]
            for order in ar_orders:
                key = f'AR({order})'
                parts.append(f"{key}={p_result[key]:.4f}")
            parts.append(f"NL={r2_nl:.4f}")
            print(f"  {pname}: {' '.join(parts)}")

    mean_b = float(np.mean(base_scores)) if base_scores else 0
    summary_parts = [f"base={mean_b:.4f}"]
    results = {'base': mean_b}
    for order in ar_orders:
        key = f'AR({order})'
        mean_o = float(np.mean(order_scores[order])) if order_scores[order] else 0
        results[key] = mean_o
        summary_parts.append(f"{key}={mean_o:.4f}")
    mean_nl = float(np.mean(order_scores['nonlinear'])) if order_scores['nonlinear'] else 0
    results['nonlinear'] = mean_nl
    summary_parts.append(f"NL={mean_nl:.4f}")

    best_key = max([f'AR({o})' for o in ar_orders] + ['nonlinear'],
                   key=lambda k: results[k])

    return {
        'name': 'EXP-1192',
        'status': 'pass',
        'detail': ' '.join(summary_parts) + f' best={best_key}',
        'per_patient': per_patient,
        'results': results,
    }


# ---------------------------------------------------------------------------
# EXP-1193: Multi-Horizon Prediction (30, 60, 90, 120 min)
# ---------------------------------------------------------------------------

def exp_1193_multi_horizon(patients, detail=False):
    """Train separate models for horizons 6/12/18/24 (30/60/90/120 min).
    Shows how prediction difficulty scales with forecast distance.
    """
    per_patient = {}
    horizons = [6, 12, 18, 24]
    horizon_scores = {h: [] for h in horizons}

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']

        X_mh, y_mh, g_cur_mh = build_enhanced_multi_horizon(
            p, glucose, physics, horizons=horizons)
        if len(X_mh) < 200:
            per_patient[pname] = {f'{h*5}min': 0 for h in horizons}
            continue
        X_mh = np.nan_to_num(X_mh, nan=0.0)

        p_result = {}
        for h in horizons:
            y_dg = y_mh[h] - g_cur_mh
            X_tr, X_va, X_te, y_tr, y_va, y_te = split_3way(X_mh, y_dg)
            g_cur_te = g_cur_mh[len(X_mh) - len(X_te):]
            y_abs_te = y_te + g_cur_te

            m = make_xgb_sota()
            m.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
            pred = m.predict(X_te) + g_cur_te
            r2 = compute_r2(y_abs_te, pred)
            rmse = compute_rmse(y_abs_te * GLUCOSE_SCALE, pred * GLUCOSE_SCALE)

            label = f'{h * 5}min'
            p_result[label] = float(r2)
            p_result[f'rmse_{label}'] = float(rmse)
            horizon_scores[h].append(r2)

        per_patient[pname] = p_result

        if detail:
            parts = [f"{h*5}min={p_result[f'{h*5}min']:.4f}" for h in horizons]
            print(f"  {pname}: {' '.join(parts)}")

    results = {}
    summary_parts = []
    for h in horizons:
        label = f'{h * 5}min'
        mean_r2 = float(np.mean(horizon_scores[h])) if horizon_scores[h] else 0
        results[label] = mean_r2
        summary_parts.append(f"{label}={mean_r2:.4f}")

    return {
        'name': 'EXP-1193',
        'status': 'pass',
        'detail': ' '.join(summary_parts),
        'per_patient': per_patient,
        'results': results,
    }


# ---------------------------------------------------------------------------
# EXP-1194: Recursive Multi-Step Prediction
# ---------------------------------------------------------------------------

def exp_1194_recursive(patients, detail=False):
    """Recursive 12-step prediction vs direct 60-min.

    Uses simpler features (glucose + PK only) to keep recursive tractable.
    Predicts one step (5 min) ahead, appends prediction, slides window, repeats.
    """
    per_patient = {}
    scores_direct, scores_recursive = [], []

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']
        pk = p['pk']
        g = glucose / GLUCOSE_SCALE
        n = len(g)

        # Build simple windows for 1-step-ahead (horizon=1)
        X_list, y1_list, y12_list, g_cur_list = [], [], [], []
        for i in range(0, n - WINDOW - HORIZON, STRIDE):
            g_win = g[i:i + WINDOW]
            if np.isnan(g_win).mean() > 0.3:
                continue
            g_win = np.nan_to_num(
                g_win, nan=np.nanmean(g_win) if np.any(~np.isnan(g_win)) else 0.4)
            pk_win = pk[i:i + WINDOW]
            if np.isnan(pk_win).any():
                pk_win = np.nan_to_num(pk_win, nan=0.0)

            y1 = g[i + WINDOW]  # 1-step ahead
            y12 = g[i + WINDOW + HORIZON - 1]  # 12-step ahead
            if np.isnan(y1) or np.isnan(y12):
                continue

            pk_mean = np.mean(pk_win, axis=0)
            pk_last = pk_win[-1]
            feat = np.concatenate([g_win, pk_mean, pk_last])
            X_list.append(feat)
            y1_list.append(y1)
            y12_list.append(y12)
            g_cur_list.append(g_win[-1])

        if len(X_list) < 200:
            per_patient[pname] = {'direct': 0, 'recursive': 0}
            continue

        X_all = np.nan_to_num(np.array(X_list), nan=0.0)
        y1_all = np.array(y1_list)
        y12_all = np.array(y12_list)
        g_cur_all = np.array(g_cur_list)
        n_feat_base = WINDOW  # glucose portion of feature vector
        n_pk_feats = X_all.shape[1] - n_feat_base

        # Split
        y_dg_12 = y12_all - g_cur_all
        X_tr, X_va, X_te, y_tr_12, y_va_12, y_te_12 = split_3way(X_all, y_dg_12)
        g_cur_te = g_cur_all[len(X_all) - len(X_te):]
        y_abs_te = y_te_12 + g_cur_te

        # Direct 12-step model
        m_direct = make_xgb_sota()
        m_direct.fit(X_tr, y_tr_12, eval_set=[(X_va, y_va_12)], verbose=False)
        pred_direct = m_direct.predict(X_te) + g_cur_te
        r2_direct = compute_r2(y_abs_te, pred_direct)

        # 1-step model for recursive use
        y_dg_1 = y1_all - g_cur_all
        _, _, _, y_tr_1, y_va_1, _ = split_3way(X_all, y_dg_1)
        m_1step = make_xgb_sota()
        m_1step.fit(X_tr, y_tr_1, eval_set=[(X_va, y_va_1)], verbose=False)

        # Recursive: iterate 12 times per test window
        recursive_preds = []
        for idx in range(len(X_te)):
            window_vec = X_te[idx].copy()
            g_window = window_vec[:n_feat_base].copy()
            pk_part = window_vec[n_feat_base:]
            for step in range(HORIZON):
                feat_in = np.concatenate([g_window, pk_part]).reshape(1, -1)
                delta = float(m_1step.predict(feat_in)[0])
                next_g = g_window[-1] + delta
                g_window = np.roll(g_window, -1)
                g_window[-1] = next_g
            recursive_preds.append(g_window[-1])

        recursive_preds = np.array(recursive_preds)
        r2_recursive = compute_r2(y_abs_te, recursive_preds)

        delta = r2_recursive - r2_direct
        per_patient[pname] = {
            'direct': float(r2_direct), 'recursive': float(r2_recursive),
            'delta': float(delta),
        }
        scores_direct.append(r2_direct)
        scores_recursive.append(r2_recursive)

        if detail:
            print(f"  {pname}: direct={r2_direct:.4f} recursive={r2_recursive:.4f}"
                  f" Δ={delta:+.4f}")

    mean_d = float(np.mean(scores_direct)) if scores_direct else 0
    mean_r = float(np.mean(scores_recursive)) if scores_recursive else 0
    wins = sum(1 for pp in per_patient.values() if pp.get('delta', 0) > 0)

    return {
        'name': 'EXP-1194',
        'status': 'pass',
        'detail': (f"direct={mean_d:.4f} recursive={mean_r:.4f}"
                   f" Δ={mean_r - mean_d:+.4f} (wins={wins}/{len(patients)})"),
        'per_patient': per_patient,
        'results': {'direct': mean_d, 'recursive': mean_r,
                    'delta': mean_r - mean_d, 'wins': wins},
    }


# ---------------------------------------------------------------------------
# EXP-1195: Attention-Weighted Features
# ---------------------------------------------------------------------------

def exp_1195_attention(patients, detail=False):
    """Test recency-weighted features: weight timestep t by
    exp(-decay * (WINDOW-1-t)), so recent values count more.

    Compares uniform vs decay=0.05, 0.10, 0.15.
    """
    per_patient = {}
    decay_values = [0.0, 0.05, 0.10, 0.15]
    decay_scores = {d: [] for d in decay_values}

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']
        pk = p['pk']
        g = glucose / GLUCOSE_SCALE
        n = len(g)

        p_result = {}
        for decay in decay_values:
            weights_ts = np.exp(-decay * np.arange(WINDOW)[::-1])
            weights_ts /= weights_ts.mean()  # normalize to mean=1

            X_list, y_list, g_cur_list = [], [], []
            for i in range(0, n - WINDOW - HORIZON, STRIDE):
                g_win = g[i:i + WINDOW]
                if np.isnan(g_win).mean() > 0.3:
                    continue
                g_win = np.nan_to_num(
                    g_win,
                    nan=np.nanmean(g_win) if np.any(~np.isnan(g_win)) else 0.4)
                pk_win = pk[i:i + WINDOW]
                if np.isnan(pk_win).any():
                    pk_win = np.nan_to_num(pk_win, nan=0.0)
                p_win = physics[i:i + WINDOW]
                if np.isnan(p_win).any():
                    p_win = np.nan_to_num(p_win, nan=0.0)

                y_val = g[i + WINDOW + HORIZON - 1]
                if np.isnan(y_val):
                    continue

                # Apply recency weights to time-series features
                g_w = g_win * weights_ts
                p_w = p_win * weights_ts[:, None]
                pk_w = pk_win * weights_ts[:, None]

                feat = _build_window_features(p, g_w, p_w, pk_w, i, WINDOW)
                X_list.append(feat)
                y_list.append(y_val)
                g_cur_list.append(g_win[-1])

            if len(X_list) < 200:
                label = f'decay={decay}'
                p_result[label] = 0.0
                continue

            X_all = np.nan_to_num(np.array(X_list), nan=0.0)
            y_all = np.array(y_list)
            g_cur_all = np.array(g_cur_list)
            y_dg = y_all - g_cur_all

            X_tr, X_va, X_te, y_tr, y_va, y_te = split_3way(X_all, y_dg)
            g_cur_te = g_cur_all[len(X_all) - len(X_te):]
            y_abs_te = y_te + g_cur_te

            m = make_xgb_sota()
            m.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
            pred = m.predict(X_te) + g_cur_te
            r2 = compute_r2(y_abs_te, pred)

            label = f'decay={decay}'
            p_result[label] = float(r2)
            decay_scores[decay].append(r2)

        # Compute delta vs uniform (decay=0)
        uniform_r2 = p_result.get('decay=0.0', p_result.get('decay=0', 0))
        best_decay = max(decay_values, key=lambda d: p_result.get(f'decay={d}', 0))
        p_result['best_decay'] = best_decay
        p_result['delta'] = p_result.get(f'decay={best_decay}', 0) - uniform_r2
        per_patient[pname] = p_result

        if detail:
            parts = [f"d={d}:{p_result.get(f'decay={d}', 0):.4f}"
                     for d in decay_values]
            print(f"  {pname}: {' '.join(parts)} best={best_decay}")

    results = {}
    summary_parts = []
    for d in decay_values:
        label = f'decay={d}'
        mean_r2 = float(np.mean(decay_scores[d])) if decay_scores[d] else 0
        results[label] = mean_r2
        summary_parts.append(f"d={d}:{mean_r2:.4f}")

    best_mean_decay = max(decay_values,
                          key=lambda d: results.get(f'decay={d}', 0))
    results['best_decay'] = best_mean_decay

    return {
        'name': 'EXP-1195',
        'status': 'pass',
        'detail': ' '.join(summary_parts) + f' best={best_mean_decay}',
        'per_patient': per_patient,
        'results': results,
    }


# ---------------------------------------------------------------------------
# EXP-1196: Patient Clustering + Cluster Models
# ---------------------------------------------------------------------------

def exp_1196_clustering(patients, detail=False):
    """Cluster patients by glucose statistics, train cluster-specific models,
    compare vs per-patient models.
    """
    from sklearn.cluster import KMeans
    from sklearn.preprocessing import StandardScaler

    per_patient = {}
    scores_individual, scores_cluster = [], []

    # Step 1: compute per-patient statistics for clustering
    patient_stats = []
    valid_patients = []
    patient_data = {}

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']
        g = glucose / GLUCOSE_SCALE
        pk = p['pk']

        X_enh, y_enh, g_cur = build_enhanced_features(p, glucose, physics)
        if len(X_enh) < 200:
            per_patient[pname] = {'individual': 0, 'cluster': 0}
            continue

        X_enh = np.nan_to_num(X_enh, nan=0.0)
        y_dg = y_enh - g_cur

        g_raw = glucose[~np.isnan(glucose)]
        tir = float(np.mean((g_raw >= 70) & (g_raw <= 180))) if len(g_raw) > 0 else 0
        iob_vals = pk[:, 0]
        cob_vals = pk[:, 6] if pk.shape[1] > 6 else np.zeros(len(pk))
        meal_freq = float(np.sum(np.diff(cob_vals) > 0.1)) / max(len(cob_vals) / 288, 1)

        stats_vec = [
            np.mean(g_raw) if len(g_raw) > 0 else 0,
            np.std(g_raw) if len(g_raw) > 0 else 0,
            tir,
            float(np.median(iob_vals)),
            meal_freq,
        ]
        patient_stats.append(stats_vec)
        valid_patients.append(p)
        patient_data[pname] = (X_enh, y_dg, g_cur)

    if len(valid_patients) < 3:
        return {
            'name': 'EXP-1196',
            'status': 'skip',
            'detail': f'Need ≥3 patients for clustering, got {len(valid_patients)}',
            'per_patient': per_patient,
            'results': {},
        }

    # Step 2: cluster
    stats_arr = np.array(patient_stats)
    scaler = StandardScaler()
    stats_scaled = scaler.fit_transform(stats_arr)
    n_clusters = min(3, len(valid_patients))
    km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    labels = km.fit_predict(stats_scaled)

    # Step 3: build cluster pools
    cluster_pools = {c: {'X_tr': [], 'y_tr': [], 'X_va': [], 'y_va': []}
                     for c in range(n_clusters)}

    for idx, p in enumerate(valid_patients):
        pname = p['name']
        X_enh, y_dg, g_cur = patient_data[pname]
        X_tr, X_va, X_te, y_tr, y_va, y_te = split_3way(X_enh, y_dg)
        c = labels[idx]
        cluster_pools[c]['X_tr'].append(X_tr)
        cluster_pools[c]['y_tr'].append(y_tr)
        cluster_pools[c]['X_va'].append(X_va)
        cluster_pools[c]['y_va'].append(y_va)

    # Train cluster models
    cluster_models = {}
    for c in range(n_clusters):
        pool = cluster_pools[c]
        if not pool['X_tr']:
            continue
        X_tr_c = np.vstack(pool['X_tr'])
        y_tr_c = np.concatenate(pool['y_tr'])
        X_va_c = np.vstack(pool['X_va'])
        y_va_c = np.concatenate(pool['y_va'])
        m = make_xgb_sota()
        m.fit(X_tr_c, y_tr_c, eval_set=[(X_va_c, y_va_c)], verbose=False)
        cluster_models[c] = m

    # Step 4: evaluate individual vs cluster
    for idx, p in enumerate(valid_patients):
        pname = p['name']
        X_enh, y_dg, g_cur = patient_data[pname]
        X_tr, X_va, X_te, y_tr, y_va, y_te = split_3way(X_enh, y_dg)
        g_cur_te = g_cur[len(X_enh) - len(X_te):]
        y_abs_te = y_te + g_cur_te

        # Individual model
        m_ind = make_xgb_sota()
        m_ind.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
        pred_ind = m_ind.predict(X_te) + g_cur_te
        r2_ind = compute_r2(y_abs_te, pred_ind)

        # Cluster model
        c = labels[idx]
        if c in cluster_models:
            pred_clust = cluster_models[c].predict(X_te) + g_cur_te
            r2_clust = compute_r2(y_abs_te, pred_clust)
        else:
            r2_clust = r2_ind

        delta = r2_clust - r2_ind
        per_patient[pname] = {
            'individual': float(r2_ind), 'cluster': float(r2_clust),
            'delta': float(delta), 'cluster_id': int(c),
        }
        scores_individual.append(r2_ind)
        scores_cluster.append(r2_clust)

        if detail:
            print(f"  {pname}: individual={r2_ind:.4f} cluster={r2_clust:.4f}"
                  f" Δ={delta:+.4f} (cluster={c})")

    mean_i = float(np.mean(scores_individual)) if scores_individual else 0
    mean_c = float(np.mean(scores_cluster)) if scores_cluster else 0
    wins = sum(1 for pp in per_patient.values() if pp.get('delta', 0) > 0)

    return {
        'name': 'EXP-1196',
        'status': 'pass',
        'detail': (f"individual={mean_i:.4f} cluster={mean_c:.4f}"
                   f" Δ={mean_c - mean_i:+.4f}"
                   f" n_clusters={n_clusters} (wins={wins}/{len(valid_patients)})"),
        'per_patient': per_patient,
        'results': {'individual': mean_i, 'cluster': mean_c,
                    'delta': mean_c - mean_i, 'n_clusters': n_clusters,
                    'wins': wins},
    }


# ---------------------------------------------------------------------------
# EXP-1197: Online Learning Simulation
# ---------------------------------------------------------------------------

def exp_1197_online_learning(patients, detail=False):
    """Simulate production: process test data in weekly chunks, retrain
    incrementally via xgboost's xgb_model parameter.

    Reports per-week R² to detect concept drift.
    """
    per_patient = {}
    scores_static, scores_online = [], []
    week_steps = 288 * 7  # 7 days at 5-min intervals
    # In terms of windows (stride=6): ~336 windows per week
    windows_per_week = week_steps // STRIDE

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']

        X_enh, y_enh, g_cur = build_enhanced_features(p, glucose, physics)
        if len(X_enh) < 400:
            per_patient[pname] = {'static': 0, 'online': 0}
            continue
        X_enh = np.nan_to_num(X_enh, nan=0.0)
        y_dg = y_enh - g_cur

        X_tr, X_va, X_te, y_tr, y_va, y_te = split_3way(X_enh, y_dg)
        g_cur_te = g_cur[len(X_enh) - len(X_te):]
        y_abs_te = y_te + g_cur_te

        # Static model (trained once, never updated)
        m_static = make_xgb_sota()
        m_static.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
        pred_static = m_static.predict(X_te) + g_cur_te
        r2_static = compute_r2(y_abs_te, pred_static)

        # Online: process test in weekly chunks with incremental retraining
        n_te = len(X_te)
        n_weeks = max(1, n_te // windows_per_week)
        week_r2_static = []
        week_r2_online = []

        # Initial training data for online model
        X_online_tr = np.vstack([X_tr, X_va])
        y_online_tr = np.concatenate([y_tr, y_va])

        # Train initial online model
        val_split = int(len(X_online_tr) * 0.85)
        m_online = make_xgb_sota()
        m_online.fit(X_online_tr[:val_split], y_online_tr[:val_split],
                     eval_set=[(X_online_tr[val_split:],
                                y_online_tr[val_split:])],
                     verbose=False)

        for w in range(n_weeks):
            start = w * windows_per_week
            end = min((w + 1) * windows_per_week, n_te)
            if start >= n_te:
                break

            X_week = X_te[start:end]
            y_week = y_te[start:end]
            g_cur_week = g_cur_te[start:end]
            y_abs_week = y_week + g_cur_week

            # Static prediction
            pred_s = m_static.predict(X_week) + g_cur_week
            r2_s = compute_r2(y_abs_week, pred_s)
            week_r2_static.append(r2_s)

            # Online prediction (before update)
            pred_o = m_online.predict(X_week) + g_cur_week
            r2_o = compute_r2(y_abs_week, pred_o)
            week_r2_online.append(r2_o)

            # Incremental retrain: add this week's data and continue training
            if XGB_AVAILABLE and end < n_te:
                X_online_tr = np.vstack([X_online_tr, X_week])
                y_online_tr = np.concatenate([y_online_tr, y_week])
                val_split = int(len(X_online_tr) * 0.85)
                m_new = make_xgb(n_estimators=100, max_depth=4,
                                 learning_rate=0.05, subsample=0.8,
                                 colsample_bytree=0.8)
                m_new.fit(X_online_tr[:val_split], y_online_tr[:val_split],
                          eval_set=[(X_online_tr[val_split:],
                                     y_online_tr[val_split:])],
                          verbose=False,
                          xgb_model=m_online.get_booster())
                m_online = m_new

        # Overall online R²
        pred_online_all = m_online.predict(X_te) + g_cur_te
        r2_online = compute_r2(y_abs_te, pred_online_all)

        per_patient[pname] = {
            'static': float(r2_static), 'online': float(r2_online),
            'delta': float(r2_online - r2_static),
            'week_r2_static': [float(r) for r in week_r2_static],
            'week_r2_online': [float(r) for r in week_r2_online],
            'n_weeks': len(week_r2_online),
        }
        scores_static.append(r2_static)
        scores_online.append(r2_online)

        if detail:
            print(f"  {pname}: static={r2_static:.4f} online={r2_online:.4f}"
                  f" Δ={r2_online - r2_static:+.4f}"
                  f" weeks={len(week_r2_online)}")

    mean_s = float(np.mean(scores_static)) if scores_static else 0
    mean_o = float(np.mean(scores_online)) if scores_online else 0
    wins = sum(1 for pp in per_patient.values() if pp.get('delta', 0) > 0)

    return {
        'name': 'EXP-1197',
        'status': 'pass',
        'detail': (f"static={mean_s:.4f} online={mean_o:.4f}"
                   f" Δ={mean_o - mean_s:+.4f}"
                   f" (wins={wins}/{len(patients)})"),
        'per_patient': per_patient,
        'results': {'static': mean_s, 'online': mean_o,
                    'delta': mean_o - mean_s, 'wins': wins},
    }


# ---------------------------------------------------------------------------
# EXP-1198: Error-Aware Prediction Intervals
# ---------------------------------------------------------------------------

def exp_1198_error_aware_pi(patients, detail=False):
    """Quantile regression (0.1, 0.25, 0.5, 0.75, 0.9) + AR correction on
    each quantile's predictions.  Report calibration.
    """
    if not XGB_AVAILABLE:
        return {
            'name': 'EXP-1198', 'status': 'skip',
            'detail': 'xgboost not available (quantile loss requires xgboost)',
            'per_patient': {}, 'results': {},
        }

    per_patient = {}
    alphas = [0.10, 0.25, 0.50, 0.75, 0.90]
    all_cal_raw = {a: [] for a in alphas}
    all_cal_ar = {a: [] for a in alphas}

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']

        X_enh, y_enh, g_cur = build_enhanced_features(p, glucose, physics)
        if len(X_enh) < 300:
            per_patient[pname] = {'base_r2': 0}
            continue
        X_enh = np.nan_to_num(X_enh, nan=0.0)
        y_dg = y_enh - g_cur

        X_tr, X_va, X_te, y_tr, y_va, y_te = split_3way(X_enh, y_dg)
        g_cur_te = g_cur[len(X_enh) - len(X_te):]
        y_abs_te = y_te + g_cur_te

        # Mean regression baseline
        m_mean = make_xgb_sota()
        m_mean.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
        pred_mean = m_mean.predict(X_te) + g_cur_te
        r2_base = compute_r2(y_abs_te, pred_mean)

        p_result = {'base_r2': float(r2_base)}

        # Train quantile models + AR correct each
        preds_raw = {}
        preds_ar = {}
        for alpha in alphas:
            m_q = xgb.XGBRegressor(
                n_estimators=500, max_depth=4, learning_rate=0.05,
                subsample=0.8, colsample_bytree=0.8,
                tree_method='hist', device='cuda',
                objective='reg:quantileerror', quantile_alpha=alpha,
                random_state=42, verbosity=0)
            m_q.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)

            pred_q_va = m_q.predict(X_va)
            pred_q_te = m_q.predict(X_te)

            # Raw quantile predictions
            preds_raw[alpha] = pred_q_te + g_cur_te

            # AR correct this quantile
            resid_va_q = y_va - pred_q_va
            resid_te_q = y_te - pred_q_te
            coeffs_q = _fit_ar_coeffs(resid_va_q, order=2)
            corrected_q = _apply_ar_causal(
                pred_q_te, resid_te_q, coeffs_q,
                bootstrap_resids=resid_va_q)
            preds_ar[alpha] = corrected_q + g_cur_te

        # Calibration: fraction of actuals below each quantile
        for alpha in alphas:
            cal_raw = float(np.mean(y_abs_te <= preds_raw[alpha]))
            cal_ar = float(np.mean(y_abs_te <= preds_ar[alpha]))
            p_result[f'cal_raw_{alpha}'] = cal_raw
            p_result[f'cal_ar_{alpha}'] = cal_ar
            all_cal_raw[alpha].append(cal_raw)
            all_cal_ar[alpha].append(cal_ar)

        # Prediction interval widths (80% PI = q90-q10, 50% PI = q75-q25)
        pi80_raw = float(np.mean((preds_raw[0.90] - preds_raw[0.10]) * GLUCOSE_SCALE))
        pi50_raw = float(np.mean((preds_raw[0.75] - preds_raw[0.25]) * GLUCOSE_SCALE))
        pi80_ar = float(np.mean((preds_ar[0.90] - preds_ar[0.10]) * GLUCOSE_SCALE))
        pi50_ar = float(np.mean((preds_ar[0.75] - preds_ar[0.25]) * GLUCOSE_SCALE))

        p_result['pi80_raw_mgdl'] = pi80_raw
        p_result['pi50_raw_mgdl'] = pi50_raw
        p_result['pi80_ar_mgdl'] = pi80_ar
        p_result['pi50_ar_mgdl'] = pi50_ar

        # Coverage: what fraction fall inside the 80% PI?
        in_80_raw = float(np.mean((y_abs_te >= preds_raw[0.10]) &
                                  (y_abs_te <= preds_raw[0.90])))
        in_80_ar = float(np.mean((y_abs_te >= preds_ar[0.10]) &
                                 (y_abs_te <= preds_ar[0.90])))
        p_result['coverage_80_raw'] = in_80_raw
        p_result['coverage_80_ar'] = in_80_ar

        per_patient[pname] = p_result

        if detail:
            print(f"  {pname}: base_R²={r2_base:.4f}"
                  f" PI80_raw={pi80_raw:.1f}mg/dL cov={in_80_raw:.1%}"
                  f" PI80_ar={pi80_ar:.1f}mg/dL cov={in_80_ar:.1%}")

    # Summarize calibration
    results = {}
    for alpha in alphas:
        results[f'cal_raw_{alpha}'] = float(np.mean(all_cal_raw[alpha])) if all_cal_raw[alpha] else 0
        results[f'cal_ar_{alpha}'] = float(np.mean(all_cal_ar[alpha])) if all_cal_ar[alpha] else 0

    # Mean calibration error
    cal_err_raw = np.mean([abs(results[f'cal_raw_{a}'] - a) for a in alphas])
    cal_err_ar = np.mean([abs(results[f'cal_ar_{a}'] - a) for a in alphas])
    results['mean_cal_error_raw'] = float(cal_err_raw)
    results['mean_cal_error_ar'] = float(cal_err_ar)

    return {
        'name': 'EXP-1198',
        'status': 'pass',
        'detail': (f"mean_cal_error: raw={cal_err_raw:.4f} ar={cal_err_ar:.4f}"
                   f" Δ={cal_err_ar - cal_err_raw:+.4f}"),
        'per_patient': per_patient,
        'results': results,
    }


# ---------------------------------------------------------------------------
# EXP-1199: Feature Interaction Discovery
# ---------------------------------------------------------------------------

def exp_1199_interactions(patients, detail=False):
    """Add pairwise interaction features (products) of top-10 most important
    features from initial XGBoost.  45 new features total.
    """
    per_patient = {}
    scores_base, scores_inter = [], []

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']

        X_enh, y_enh, g_cur = build_enhanced_features(p, glucose, physics)
        if len(X_enh) < 200:
            per_patient[pname] = {'base': 0, 'interactions': 0}
            continue
        X_enh = np.nan_to_num(X_enh, nan=0.0)
        y_dg = y_enh - g_cur

        X_tr, X_va, X_te, y_tr, y_va, y_te = split_3way(X_enh, y_dg)
        g_cur_te = g_cur[len(X_enh) - len(X_te):]
        y_abs_te = y_te + g_cur_te

        # Baseline enhanced model
        m_base = make_xgb_sota()
        m_base.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
        pred_base = m_base.predict(X_te) + g_cur_te
        r2_base = compute_r2(y_abs_te, pred_base)

        # Get feature importances and top-10 indices
        if hasattr(m_base, 'feature_importances_'):
            importances = m_base.feature_importances_
        else:
            importances = np.ones(X_enh.shape[1])
        top_k = min(10, len(importances))
        top_indices = np.argsort(importances)[-top_k:]

        # Create pairwise interaction features
        n_interactions = top_k * (top_k - 1) // 2
        X_inter_tr = np.zeros((len(X_tr), n_interactions))
        X_inter_va = np.zeros((len(X_va), n_interactions))
        X_inter_te = np.zeros((len(X_te), n_interactions))

        col = 0
        interaction_pairs = []
        for ii in range(top_k):
            for jj in range(ii + 1, top_k):
                fi, fj = top_indices[ii], top_indices[jj]
                X_inter_tr[:, col] = X_tr[:, fi] * X_tr[:, fj]
                X_inter_va[:, col] = X_va[:, fi] * X_va[:, fj]
                X_inter_te[:, col] = X_te[:, fi] * X_te[:, fj]
                interaction_pairs.append((int(fi), int(fj)))
                col += 1

        # Augmented feature sets
        X_tr_aug = np.hstack([X_tr, X_inter_tr])
        X_va_aug = np.hstack([X_va, X_inter_va])
        X_te_aug = np.hstack([X_te, X_inter_te])

        m_inter = make_xgb_sota()
        m_inter.fit(X_tr_aug, y_tr, eval_set=[(X_va_aug, y_va)], verbose=False)
        pred_inter = m_inter.predict(X_te_aug) + g_cur_te
        r2_inter = compute_r2(y_abs_te, pred_inter)

        # Which interactions matter most?
        if hasattr(m_inter, 'feature_importances_'):
            inter_imp = m_inter.feature_importances_[X_enh.shape[1]:]
            if len(inter_imp) > 0:
                best_inter_idx = int(np.argmax(inter_imp))
                best_pair = interaction_pairs[best_inter_idx] if best_inter_idx < len(interaction_pairs) else (0, 0)
            else:
                best_pair = (0, 0)
        else:
            best_pair = (0, 0)

        delta = r2_inter - r2_base
        per_patient[pname] = {
            'base': float(r2_base), 'interactions': float(r2_inter),
            'delta': float(delta),
            'n_interactions': n_interactions,
            'best_pair': list(best_pair),
        }
        scores_base.append(r2_base)
        scores_inter.append(r2_inter)

        if detail:
            print(f"  {pname}: base={r2_base:.4f} +interactions={r2_inter:.4f}"
                  f" Δ={delta:+.4f} n_inter={n_interactions}"
                  f" best_pair={best_pair}")

    mean_b = float(np.mean(scores_base)) if scores_base else 0
    mean_i = float(np.mean(scores_inter)) if scores_inter else 0
    wins = sum(1 for pp in per_patient.values() if pp.get('delta', 0) > 0)

    return {
        'name': 'EXP-1199',
        'status': 'pass',
        'detail': (f"base={mean_b:.4f} +interactions={mean_i:.4f}"
                   f" Δ={mean_i - mean_b:+.4f}"
                   f" (wins={wins}/{len(patients)})"),
        'per_patient': per_patient,
        'results': {'base': mean_b, 'interactions': mean_i,
                    'delta': mean_i - mean_b, 'wins': wins},
    }


# ---------------------------------------------------------------------------
# EXP-1200: Grand Final Benchmark — Best Known Pipeline
# ---------------------------------------------------------------------------

def exp_1200_grand_final(patients, detail=False):
    """Definitive benchmark: enhanced features + multi-horizon + per-patient
    tuning + AR correction, evaluated with 5-fold TimeSeriesSplit CV.

    Reports: offline CV R², production CV R² (with AR).
    """
    per_patient = {}
    all_offline_cv, all_production_cv = [], []
    horizons = [6, 12, 18]
    h_weights = {6: 0.2, 12: 0.6, 18: 0.2}
    n_splits = 5

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']

        X_mh, y_mh, g_cur_mh = build_enhanced_multi_horizon(
            p, glucose, physics, horizons=horizons)
        if len(X_mh) < 300:
            per_patient[pname] = {
                'offline_cv': {'mean': 0, 'std': 0, 'folds': []},
                'production_cv': {'mean': 0, 'std': 0, 'folds': []},
            }
            continue
        X_mh = np.nan_to_num(X_mh, nan=0.0)
        y_dg_60 = y_mh[12] - g_cur_mh

        tscv = TimeSeriesSplit(n_splits=n_splits)
        offline_folds = []
        production_folds = []

        for train_idx, test_idx in tscv.split(X_mh):
            X_tr = X_mh[train_idx]
            X_te = X_mh[test_idx]
            g_cur_te = g_cur_mh[test_idx]

            # Inner val split for early stopping & tuning
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
            r2_offline = compute_r2(y_abs_te, combined_abs)
            offline_folds.append(r2_offline)

            # AR correction: fit on validation residuals, apply to test
            pred_va = sum(h_weights[h] * make_xgb(
                n_estimators=500, subsample=0.8, colsample_bytree=0.8,
                **best_params).fit(
                    X_tr_inner, (y_mh[h] - g_cur_mh)[train_idx][:val_split],
                    eval_set=[(X_va_inner,
                               (y_mh[h] - g_cur_mh)[train_idx][val_split:])],
                    verbose=False
                ).predict(X_va_inner)
                for h in horizons)
            resid_va = y_va_60_inner - pred_va
            resid_te = y_te_60 - combined_pred
            coeffs = _fit_ar_coeffs(resid_va, order=2)
            corrected = _apply_ar_causal(
                combined_pred, resid_te, coeffs,
                bootstrap_resids=resid_va)
            pred_ar_abs = corrected + g_cur_te
            r2_production = compute_r2(y_abs_te, pred_ar_abs)
            production_folds.append(r2_production)

        results_p = {
            'offline_cv': {
                'mean': float(np.mean(offline_folds)),
                'std': float(np.std(offline_folds)),
                'folds': [float(f) for f in offline_folds],
            },
            'production_cv': {
                'mean': float(np.mean(production_folds)),
                'std': float(np.std(production_folds)),
                'folds': [float(f) for f in production_folds],
            },
        }
        all_offline_cv.append(results_p['offline_cv']['mean'])
        all_production_cv.append(results_p['production_cv']['mean'])
        per_patient[pname] = results_p

        if detail:
            o = results_p['offline_cv']
            pr = results_p['production_cv']
            print(f"  {pname}: offline_cv={o['mean']:.4f}±{o['std']:.3f}"
                  f" production_cv={pr['mean']:.4f}±{pr['std']:.3f}"
                  f" Δ={pr['mean'] - o['mean']:+.4f}")

    mean_o = float(np.mean(all_offline_cv)) if all_offline_cv else 0
    mean_p = float(np.mean(all_production_cv)) if all_production_cv else 0
    wins = sum(1 for pp in per_patient.values()
               if pp.get('production_cv', {}).get('mean', 0) >
               pp.get('offline_cv', {}).get('mean', 0))

    return {
        'name': 'EXP-1200',
        'status': 'pass',
        'detail': (f"5-fold CV: offline={mean_o:.4f} production(+AR)={mean_p:.4f}"
                   f" Δ={mean_p - mean_o:+.4f}"
                   f" (wins={wins}/{len(patients)})"),
        'per_patient': per_patient,
        'results': {'offline_cv': mean_o, 'production_cv': mean_p,
                    'delta': mean_p - mean_o, 'wins': wins},
    }


# ---------------------------------------------------------------------------
# Registry and main
# ---------------------------------------------------------------------------

EXPERIMENTS = [
    ('EXP-1191', 'Combined Pipeline + AR Correction (Full Stack)',
     exp_1191_combined_ar),
    ('EXP-1192', 'AR Correction Depth Analysis',
     exp_1192_ar_depth),
    ('EXP-1193', 'Multi-Horizon Prediction (30, 60, 90, 120 min)',
     exp_1193_multi_horizon),
    ('EXP-1194', 'Recursive Multi-Step Prediction',
     exp_1194_recursive),
    ('EXP-1195', 'Attention-Weighted Features',
     exp_1195_attention),
    ('EXP-1196', 'Patient Clustering + Cluster Models',
     exp_1196_clustering),
    ('EXP-1197', 'Online Learning Simulation',
     exp_1197_online_learning),
    ('EXP-1198', 'Error-Aware Prediction Intervals',
     exp_1198_error_aware_pi),
    ('EXP-1199', 'Feature Interaction Discovery',
     exp_1199_interactions),
    ('EXP-1200', 'Grand Final Benchmark — Best Known Pipeline',
     exp_1200_grand_final),
]


def main():
    parser = argparse.ArgumentParser(
        description='EXP-1191-1200: Combined + AR + Multi-Horizon + '
                    'Production Pipeline')
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--max-patients', type=int, default=11)
    parser.add_argument('--experiments', type=str, default='all',
                        help='Comma-separated exp numbers or "all"')
    parser.add_argument('--experiment', type=str,
                        help='Run only this experiment (e.g. EXP-1191)')
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
                             .replace('-', '_').replace('—', '_'))
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
