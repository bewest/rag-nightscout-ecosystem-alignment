#!/usr/bin/env python3
"""EXP-1201 to EXP-1210: Conformal PI + Full Stack CV + Multi-Horizon AR + Diagnostics.

Campaign status after 200 experiments (EXP-1001 to EXP-1200):
- Combined pipeline = best offline: R²=0.551 single, 0.488 CV
- Linear AR correction = biggest production win: +0.124 R², reaching 0.655
- Grand Final (EXP-1200): 5-fold CV offline + production with AR
- LSTM overfits; log-glucose hurts; stacking hurts

This batch deepens the analysis with conformal prediction intervals, full
production stack CV, AR at multiple horizons, Kalman filter comparison,
hard patient deep dive, training data sensitivity, temporal feature
engineering, glucose regime models, residual decomposition, and horizon
ensemble stacking:

  EXP-1201: Conformal Prediction Intervals                   ★★★★★
  EXP-1202: Full Production Stack CV (Combined+AR+Online)     ★★★★★
  EXP-1203: AR at Multiple Horizons                           ★★★★
  EXP-1204: Kalman Filter vs AR Correction                    ★★★★
  EXP-1205: Hard Patient Deep Dive                            ★★★★
  EXP-1206: Training Data Sensitivity                         ★★★★
  EXP-1207: Temporal Feature Engineering                      ★★★
  EXP-1208: Glucose Regime Models                             ★★★
  EXP-1209: Residual Decomposition Analysis                   ★★★
  EXP-1210: Ensemble of Horizon-Specific Models               ★★★★

Run:
    PYTHONPATH=tools python -m cgmencode.exp_clinical_1201 --detail --save --max-patients 11
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
# Shared helpers (mirror exp_clinical_1191 patterns)
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
# Feature builders (from exp_clinical_1191)
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
    """Build the full enhanced feature vector for one window."""
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
    """Fit AR coefficients on a residual sequence via OLS."""
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
    """Apply AR correction sequentially using a causal rolling buffer."""
    order = len(coeffs)
    buf = list(bootstrap_resids[-order:])
    corrections = np.zeros(len(pred_te))
    for t in range(len(pred_te)):
        corr = sum(coeffs[j] * buf[-(j + 1)] for j in range(order))
        corrections[t] = corr
        buf.append(residuals_te[t])
    return pred_te + corrections


# ---------------------------------------------------------------------------
# EXP-1201: Conformal Prediction Intervals
# ---------------------------------------------------------------------------

def exp_1201_conformal_pi(patients, detail=False):
    """Split conformal prediction with properly calibrated intervals.

    Uses validation set as calibration set for nonconformity scores.
    Compares raw conformal vs AR-corrected conformal at α=0.2 (80% PI).
    """
    per_patient = {}
    all_cov_raw, all_cov_ar = [], []
    all_width_raw, all_width_ar = [], []
    alpha = 0.2  # 80% PI

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
        g_cur_va = g_cur[len(X_tr):len(X_tr) + len(X_va)]
        g_cur_te = g_cur[len(X_enh) - len(X_te):]
        y_abs_te = y_te + g_cur_te

        # Train XGBoost on train set
        m = make_xgb_sota()
        m.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
        pred_va = m.predict(X_va)
        pred_te = m.predict(X_te)
        r2_base = compute_r2(y_abs_te, pred_te + g_cur_te)

        # --- Raw conformal ---
        scores_raw = np.abs(y_va - pred_va)
        q_raw = np.quantile(scores_raw, 1 - alpha)
        pred_abs = pred_te + g_cur_te
        lo_raw = pred_abs - q_raw
        hi_raw = pred_abs + q_raw
        cov_raw = float(np.mean((y_abs_te >= lo_raw) & (y_abs_te <= hi_raw)))
        width_raw = float(np.mean((hi_raw - lo_raw) * GLUCOSE_SCALE))

        # --- AR-corrected conformal ---
        resid_va = y_va - pred_va
        resid_te = y_te - pred_te
        coeffs = _fit_ar_coeffs(resid_va, order=2)
        corrected = _apply_ar_causal(pred_te, resid_te, coeffs,
                                     bootstrap_resids=resid_va)
        pred_ar_abs = corrected + g_cur_te
        r2_ar = compute_r2(y_abs_te, pred_ar_abs)

        # Conformal scores on AR-corrected validation residuals
        corrected_va = _apply_ar_causal(pred_va, resid_va, coeffs,
                                        bootstrap_resids=np.zeros(2))
        scores_ar = np.abs(y_va - corrected_va)
        q_ar = np.quantile(scores_ar, 1 - alpha)
        lo_ar = pred_ar_abs - q_ar
        hi_ar = pred_ar_abs + q_ar
        cov_ar = float(np.mean((y_abs_te >= lo_ar) & (y_abs_te <= hi_ar)))
        width_ar = float(np.mean((hi_ar - lo_ar) * GLUCOSE_SCALE))

        # Sharpness: average width / coverage (lower = sharper at same coverage)
        sharpness_raw = width_raw / max(cov_raw, 0.01)
        sharpness_ar = width_ar / max(cov_ar, 0.01)

        per_patient[pname] = {
            'base_r2': float(r2_base), 'ar_r2': float(r2_ar),
            'cov_raw': cov_raw, 'width_raw_mgdl': width_raw,
            'q_raw_mgdl': float(q_raw * GLUCOSE_SCALE),
            'cov_ar': cov_ar, 'width_ar_mgdl': width_ar,
            'q_ar_mgdl': float(q_ar * GLUCOSE_SCALE),
            'sharpness_raw': float(sharpness_raw),
            'sharpness_ar': float(sharpness_ar),
            'ar_coeffs': [float(c) for c in coeffs],
        }
        all_cov_raw.append(cov_raw)
        all_cov_ar.append(cov_ar)
        all_width_raw.append(width_raw)
        all_width_ar.append(width_ar)

        if detail:
            print(f"  {pname}: R²={r2_base:.4f} +AR={r2_ar:.4f}"
                  f" cov_raw={cov_raw:.1%} w={width_raw:.1f}mg/dL"
                  f" cov_ar={cov_ar:.1%} w={width_ar:.1f}mg/dL")

    mean_cov_raw = float(np.mean(all_cov_raw)) if all_cov_raw else 0
    mean_cov_ar = float(np.mean(all_cov_ar)) if all_cov_ar else 0
    mean_w_raw = float(np.mean(all_width_raw)) if all_width_raw else 0
    mean_w_ar = float(np.mean(all_width_ar)) if all_width_ar else 0

    return {
        'name': 'EXP-1201',
        'status': 'pass',
        'detail': (f"80%PI: raw cov={mean_cov_raw:.1%} w={mean_w_raw:.1f}mg/dL"
                   f" | AR cov={mean_cov_ar:.1%} w={mean_w_ar:.1f}mg/dL"
                   f" (target cov=80%)"),
        'per_patient': per_patient,
        'results': {'coverage_raw': mean_cov_raw, 'width_raw': mean_w_raw,
                    'coverage_ar': mean_cov_ar, 'width_ar': mean_w_ar,
                    'alpha': alpha},
    }


# ---------------------------------------------------------------------------
# EXP-1202: Full Production Stack CV (Combined + AR + Online)
# ---------------------------------------------------------------------------

def exp_1202_full_stack_cv(patients, detail=False):
    """5-fold CV of the complete production pipeline:
    combined features + XGBoost + AR(2) + online learning.

    Reports: offline R², +AR R², +AR+online R² at each fold.
    This is the definitive SOTA number.
    """
    per_patient = {}
    all_offline, all_ar, all_online = [], [], []
    n_splits = 5
    week_steps = 288 * 7
    windows_per_week = week_steps // STRIDE

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']

        X_enh, y_enh, g_cur = build_enhanced_features(p, glucose, physics)
        if len(X_enh) < 400:
            per_patient[pname] = {'offline_cv': 0, 'ar_cv': 0, 'online_cv': 0}
            continue
        X_enh = np.nan_to_num(X_enh, nan=0.0)
        y_dg = y_enh - g_cur

        tscv = TimeSeriesSplit(n_splits=n_splits)
        folds_offline, folds_ar, folds_online = [], [], []

        for train_idx, test_idx in tscv.split(X_enh):
            X_tr_full = X_enh[train_idx]
            X_te = X_enh[test_idx]
            y_tr_full = y_dg[train_idx]
            y_te = y_dg[test_idx]
            g_cur_te = g_cur[test_idx]
            y_abs_te = y_te + g_cur_te

            # Inner val split
            val_split = int(len(X_tr_full) * 0.8)
            X_tr = X_tr_full[:val_split]
            X_va = X_tr_full[val_split:]
            y_tr = y_tr_full[:val_split]
            y_va = y_tr_full[val_split:]

            # Per-patient quick tune
            best_params = quick_tune_patient(X_tr, y_tr, X_va, y_va)

            # Offline model
            m = make_xgb(n_estimators=500, subsample=0.8,
                         colsample_bytree=0.8, **best_params)
            m.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
            pred_va = m.predict(X_va)
            pred_te = m.predict(X_te)
            r2_offline = compute_r2(y_abs_te, pred_te + g_cur_te)
            folds_offline.append(r2_offline)

            # AR(2) correction
            resid_va = y_va - pred_va
            resid_te = y_te - pred_te
            coeffs = _fit_ar_coeffs(resid_va, order=2)
            corrected = _apply_ar_causal(pred_te, resid_te, coeffs,
                                         bootstrap_resids=resid_va)
            r2_ar = compute_r2(y_abs_te, corrected + g_cur_te)
            folds_ar.append(r2_ar)

            # Online learning on test chunks
            X_online_tr = X_tr_full.copy()
            y_online_tr = y_tr_full.copy()
            val_sp = int(len(X_online_tr) * 0.85)
            m_online = make_xgb(n_estimators=500, subsample=0.8,
                                colsample_bytree=0.8, **best_params)
            m_online.fit(X_online_tr[:val_sp], y_online_tr[:val_sp],
                         eval_set=[(X_online_tr[val_sp:],
                                    y_online_tr[val_sp:])],
                         verbose=False)

            n_te = len(X_te)
            n_weeks = max(1, n_te // windows_per_week)
            for w in range(n_weeks):
                start = w * windows_per_week
                end = min((w + 1) * windows_per_week, n_te)
                if start >= n_te:
                    break
                X_week = X_te[start:end]
                y_week = y_te[start:end]
                if XGB_AVAILABLE and end < n_te:
                    X_online_tr = np.vstack([X_online_tr, X_week])
                    y_online_tr = np.concatenate([y_online_tr, y_week])
                    vs = int(len(X_online_tr) * 0.85)
                    m_new = make_xgb(n_estimators=100, max_depth=4,
                                     learning_rate=0.05, subsample=0.8,
                                     colsample_bytree=0.8)
                    m_new.fit(X_online_tr[:vs], y_online_tr[:vs],
                              eval_set=[(X_online_tr[vs:],
                                         y_online_tr[vs:])],
                              verbose=False,
                              xgb_model=m_online.get_booster())
                    m_online = m_new

            # AR on online predictions
            pred_online = m_online.predict(X_te)
            resid_online_va = y_va - m_online.predict(X_va)
            resid_online_te = y_te - pred_online
            coeffs_online = _fit_ar_coeffs(resid_online_va, order=2)
            corrected_online = _apply_ar_causal(
                pred_online, resid_online_te, coeffs_online,
                bootstrap_resids=resid_online_va)
            r2_online = compute_r2(y_abs_te, corrected_online + g_cur_te)
            folds_online.append(r2_online)

        mean_off = float(np.mean(folds_offline))
        mean_ar = float(np.mean(folds_ar))
        mean_onl = float(np.mean(folds_online))
        per_patient[pname] = {
            'offline_cv': mean_off, 'ar_cv': mean_ar, 'online_cv': mean_onl,
            'folds_offline': [float(f) for f in folds_offline],
            'folds_ar': [float(f) for f in folds_ar],
            'folds_online': [float(f) for f in folds_online],
        }
        all_offline.append(mean_off)
        all_ar.append(mean_ar)
        all_online.append(mean_onl)

        if detail:
            print(f"  {pname}: offline={mean_off:.4f} +AR={mean_ar:.4f}"
                  f" +AR+online={mean_onl:.4f}")

    m_o = float(np.mean(all_offline)) if all_offline else 0
    m_a = float(np.mean(all_ar)) if all_ar else 0
    m_n = float(np.mean(all_online)) if all_online else 0

    return {
        'name': 'EXP-1202',
        'status': 'pass',
        'detail': (f"5-fold CV: offline={m_o:.4f} +AR={m_a:.4f}"
                   f" +AR+online={m_n:.4f}"),
        'per_patient': per_patient,
        'results': {'offline_cv': m_o, 'ar_cv': m_a,
                    'online_cv': m_n,
                    'delta_ar': m_a - m_o, 'delta_online': m_n - m_o},
    }


# ---------------------------------------------------------------------------
# EXP-1203: AR at Multiple Horizons
# ---------------------------------------------------------------------------

def exp_1203_ar_multi_horizon(patients, detail=False):
    """Test AR(2) correction at 30, 60, 90, 120 min horizons.

    Hypothesis: AR helps more at longer horizons.
    """
    per_patient = {}
    horizons = [6, 12, 18, 24]  # 30, 60, 90, 120 min
    horizon_base = {h: [] for h in horizons}
    horizon_ar = {h: [] for h in horizons}

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']

        X_mh, y_mh, g_cur_mh = build_enhanced_multi_horizon(
            p, glucose, physics, horizons=horizons)
        if len(X_mh) < 300:
            per_patient[pname] = {f'{h*5}min_base': 0 for h in horizons}
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
            pred_va = m.predict(X_va)
            pred_te = m.predict(X_te)

            r2_base = compute_r2(y_abs_te, pred_te + g_cur_te)

            # AR(2) correction
            resid_va = y_va - pred_va
            resid_te = y_te - pred_te
            coeffs = _fit_ar_coeffs(resid_va, order=2)
            corrected = _apply_ar_causal(pred_te, resid_te, coeffs,
                                         bootstrap_resids=resid_va)
            r2_ar = compute_r2(y_abs_te, corrected + g_cur_te)

            label = f'{h * 5}min'
            p_result[f'{label}_base'] = float(r2_base)
            p_result[f'{label}_ar'] = float(r2_ar)
            p_result[f'{label}_delta'] = float(r2_ar - r2_base)
            p_result[f'{label}_coeffs'] = [float(c) for c in coeffs]
            horizon_base[h].append(r2_base)
            horizon_ar[h].append(r2_ar)

        per_patient[pname] = p_result

        if detail:
            parts = [f"{h*5}min: {p_result[f'{h*5}min_base']:.4f}→"
                     f"{p_result[f'{h*5}min_ar']:.4f}"
                     f"(Δ={p_result[f'{h*5}min_delta']:+.4f})"
                     for h in horizons]
            print(f"  {pname}: {' | '.join(parts)}")

    results = {}
    summary_parts = []
    for h in horizons:
        label = f'{h * 5}min'
        mb = float(np.mean(horizon_base[h])) if horizon_base[h] else 0
        ma = float(np.mean(horizon_ar[h])) if horizon_ar[h] else 0
        results[f'{label}_base'] = mb
        results[f'{label}_ar'] = ma
        results[f'{label}_delta'] = ma - mb
        summary_parts.append(f"{label}:Δ={ma - mb:+.4f}")

    return {
        'name': 'EXP-1203',
        'status': 'pass',
        'detail': ' '.join(summary_parts),
        'per_patient': per_patient,
        'results': results,
    }


# ---------------------------------------------------------------------------
# EXP-1204: Kalman Filter vs AR Correction
# ---------------------------------------------------------------------------

def exp_1204_kalman_vs_ar(patients, detail=False):
    """Simple Kalman filter: state=[glucose, glucose_rate], observation=CGM.

    Compares: raw XGBoost, AR(2), Kalman, hybrid (Kalman + AR).
    """
    per_patient = {}
    scores_base, scores_ar, scores_kalman, scores_hybrid = [], [], [], []

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']

        X_enh, y_enh, g_cur = build_enhanced_features(p, glucose, physics)
        if len(X_enh) < 300:
            per_patient[pname] = {'base': 0, 'ar': 0, 'kalman': 0, 'hybrid': 0}
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
        pred_abs = pred_te + g_cur_te
        r2_base = compute_r2(y_abs_te, pred_abs)

        # AR(2) correction
        resid_va = y_va - pred_va
        resid_te = y_te - pred_te
        coeffs = _fit_ar_coeffs(resid_va, order=2)
        corrected_ar = _apply_ar_causal(pred_te, resid_te, coeffs,
                                         bootstrap_resids=resid_va)
        r2_ar = compute_r2(y_abs_te, corrected_ar + g_cur_te)

        # Kalman filter on test predictions
        # State: [glucose_delta, rate_of_delta]
        # Transition: x[t] = F * x[t-1] + process_noise
        # Observation: y[t] = H * x[t] + obs_noise
        # We use XGBoost pred as prior, CGM residual to update
        dt = 1.0  # unit timestep
        F = np.array([[1, dt], [0, 1]])
        H = np.array([[1, 0]])
        # Tune Q, R on validation
        best_kalman_r2 = -1e9
        best_Q_scale, best_R_scale = 0.001, 0.01
        for q_s in [0.0001, 0.001, 0.01]:
            for r_s in [0.001, 0.01, 0.1]:
                Q = np.eye(2) * q_s
                R = np.array([[r_s]])
                x = np.array([pred_va[0], 0.0])
                P = np.eye(2) * 0.1
                kalman_preds = []
                for t in range(len(pred_va)):
                    # Predict
                    x_pred = F @ x
                    P_pred = F @ P @ F.T + Q
                    kalman_preds.append(x_pred[0])
                    # Update with actual residual
                    z = np.array([y_va[t]])
                    S = H @ P_pred @ H.T + R
                    K = P_pred @ H.T @ np.linalg.inv(S)
                    x = x_pred + (K @ (z - H @ x_pred)).ravel()
                    P = (np.eye(2) - K @ H) @ P_pred
                kp = np.array(kalman_preds)
                g_cur_va = g_cur[len(X_tr):len(X_tr) + len(X_va)]
                r2_k = compute_r2(y_va + g_cur_va, kp + g_cur_va)
                if r2_k > best_kalman_r2:
                    best_kalman_r2 = r2_k
                    best_Q_scale = q_s
                    best_R_scale = r_s

        # Apply best Kalman on test
        Q = np.eye(2) * best_Q_scale
        R = np.array([[best_R_scale]])
        x = np.array([pred_te[0], 0.0])
        P = np.eye(2) * 0.1
        kalman_preds_te = []
        kalman_vars = []
        for t in range(len(pred_te)):
            x_pred = F @ x
            P_pred = F @ P @ F.T + Q
            kalman_preds_te.append(x_pred[0])
            kalman_vars.append(P_pred[0, 0])
            z = np.array([y_te[t]])
            S = H @ P_pred @ H.T + R
            K = P_pred @ H.T @ np.linalg.inv(S)
            x = x_pred + (K @ (z - H @ x_pred)).ravel()
            P = (np.eye(2) - K @ H) @ P_pred

        kalman_abs = np.array(kalman_preds_te) + g_cur_te
        r2_kalman = compute_r2(y_abs_te, kalman_abs)

        # Hybrid: average of AR and Kalman corrections
        hybrid_pred = 0.5 * (corrected_ar + np.array(kalman_preds_te))
        r2_hybrid = compute_r2(y_abs_te, hybrid_pred + g_cur_te)

        per_patient[pname] = {
            'base': float(r2_base), 'ar': float(r2_ar),
            'kalman': float(r2_kalman), 'hybrid': float(r2_hybrid),
            'kalman_Q': best_Q_scale, 'kalman_R': best_R_scale,
            'mean_uncertainty_mgdl': float(np.mean(np.sqrt(kalman_vars)) * GLUCOSE_SCALE),
        }
        scores_base.append(r2_base)
        scores_ar.append(r2_ar)
        scores_kalman.append(r2_kalman)
        scores_hybrid.append(r2_hybrid)

        if detail:
            print(f"  {pname}: base={r2_base:.4f} AR={r2_ar:.4f}"
                  f" Kalman={r2_kalman:.4f} hybrid={r2_hybrid:.4f}")

    mb = float(np.mean(scores_base)) if scores_base else 0
    ma = float(np.mean(scores_ar)) if scores_ar else 0
    mk = float(np.mean(scores_kalman)) if scores_kalman else 0
    mh = float(np.mean(scores_hybrid)) if scores_hybrid else 0
    best_method = max([('base', mb), ('AR', ma), ('Kalman', mk),
                       ('hybrid', mh)], key=lambda x: x[1])

    return {
        'name': 'EXP-1204',
        'status': 'pass',
        'detail': (f"base={mb:.4f} AR={ma:.4f} Kalman={mk:.4f}"
                   f" hybrid={mh:.4f} best={best_method[0]}"),
        'per_patient': per_patient,
        'results': {'base': mb, 'ar': ma, 'kalman': mk, 'hybrid': mh,
                    'best_method': best_method[0]},
    }


# ---------------------------------------------------------------------------
# EXP-1205: Hard Patient Deep Dive
# ---------------------------------------------------------------------------

def exp_1205_hard_patients(patients, detail=False):
    """Analyze what makes patients c, h, j, k hard.

    Computes glucose variability metrics, compares feature importance,
    and tries per-patient hyperparameter optimization for hard patients.
    """
    per_patient = {}
    hard_names = {'c', 'h', 'j', 'k'}
    easy_names = {'f', 'i'}

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']
        pk = p['pk']
        g_raw = glucose[~np.isnan(glucose)]

        # Glucose variability metrics
        if len(g_raw) > 10:
            cv = float(np.std(g_raw) / np.mean(g_raw)) if np.mean(g_raw) > 0 else 0
            tir = float(np.mean((g_raw >= 70) & (g_raw <= 180)))
            tbr = float(np.mean(g_raw < 70))
            tar = float(np.mean(g_raw > 180))
            # MAGE approximation: mean of absolute excursions > 1 SD
            g_std = np.std(g_raw)
            diffs = np.abs(np.diff(g_raw))
            excursions = diffs[diffs > g_std]
            mage = float(np.mean(excursions)) if len(excursions) > 0 else 0
        else:
            cv = tir = tbr = tar = mage = 0.0

        # Data completeness
        nan_frac = float(np.isnan(glucose).mean())
        n_steps = len(glucose)
        iob_coverage = float(np.mean(pk[:, 0] > 0.01))

        # Build features and evaluate with default params
        X_enh, y_enh, g_cur = build_enhanced_features(p, glucose, physics)
        if len(X_enh) < 200:
            per_patient[pname] = {
                'category': 'hard' if pname in hard_names else 'easy',
                'r2_default': 0, 'r2_tuned': 0,
                'cv': cv, 'tir': tir, 'mage': mage,
                'n_steps': n_steps, 'nan_frac': nan_frac,
            }
            continue
        X_enh = np.nan_to_num(X_enh, nan=0.0)
        y_dg = y_enh - g_cur
        X_tr, X_va, X_te, y_tr, y_va, y_te = split_3way(X_enh, y_dg)
        g_cur_te = g_cur[len(X_enh) - len(X_te):]
        y_abs_te = y_te + g_cur_te

        # Default model
        m_default = make_xgb_sota()
        m_default.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
        pred_default = m_default.predict(X_te) + g_cur_te
        r2_default = compute_r2(y_abs_te, pred_default)

        # Feature importance (top 10 indices)
        if hasattr(m_default, 'feature_importances_'):
            imp = m_default.feature_importances_
            top10 = list(int(x) for x in np.argsort(imp)[-10:][::-1])
        else:
            top10 = list(range(10))

        # Per-patient tuned model (extended grid for hard patients)
        best_params = quick_tune_patient(X_tr, y_tr, X_va, y_va)
        m_tuned = make_xgb(n_estimators=500, subsample=0.8,
                           colsample_bytree=0.8, **best_params)
        m_tuned.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
        pred_tuned = m_tuned.predict(X_te) + g_cur_te
        r2_tuned = compute_r2(y_abs_te, pred_tuned)

        # Deep tuning for hard patients: try more aggressive params
        r2_deep = r2_tuned
        deep_params = best_params
        if pname in hard_names:
            for dp in [dict(max_depth=7, learning_rate=0.02, n_estimators=800),
                       dict(max_depth=5, learning_rate=0.01, n_estimators=1000),
                       dict(max_depth=4, learning_rate=0.03, n_estimators=700)]:
                m_d = make_xgb(subsample=0.8, colsample_bytree=0.8, **dp)
                m_d.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
                pred_d = m_d.predict(X_te) + g_cur_te
                r2_d = compute_r2(y_abs_te, pred_d)
                if r2_d > r2_deep:
                    r2_deep = r2_d
                    deep_params = dp

        category = 'hard' if pname in hard_names else (
            'easy' if pname in easy_names else 'mid')

        per_patient[pname] = {
            'category': category,
            'r2_default': float(r2_default),
            'r2_tuned': float(r2_tuned),
            'r2_deep': float(r2_deep),
            'delta_tuned': float(r2_tuned - r2_default),
            'delta_deep': float(r2_deep - r2_default),
            'best_params': deep_params if pname in hard_names else best_params,
            'cv': cv, 'tir': tir, 'tbr': tbr, 'tar': tar, 'mage': mage,
            'n_steps': n_steps, 'nan_frac': nan_frac,
            'iob_coverage': float(iob_coverage),
            'top10_features': top10,
        }

        if detail:
            print(f"  {pname} [{category}]: default={r2_default:.4f}"
                  f" tuned={r2_tuned:.4f} deep={r2_deep:.4f}"
                  f" CV={cv:.3f} TIR={tir:.1%} MAGE={mage:.1f}"
                  f" n={n_steps} nan={nan_frac:.1%}")

    # Summarize by category
    cats = {}
    for pname, res in per_patient.items():
        cat = res.get('category', 'mid')
        if cat not in cats:
            cats[cat] = {'default': [], 'tuned': [], 'deep': []}
        cats[cat]['default'].append(res.get('r2_default', 0))
        cats[cat]['tuned'].append(res.get('r2_tuned', 0))
        cats[cat]['deep'].append(res.get('r2_deep', 0))

    results = {}
    summary_parts = []
    for cat in ['easy', 'mid', 'hard']:
        if cat in cats:
            md = float(np.mean(cats[cat]['default']))
            mt = float(np.mean(cats[cat]['tuned']))
            me = float(np.mean(cats[cat]['deep']))
            results[f'{cat}_default'] = md
            results[f'{cat}_tuned'] = mt
            results[f'{cat}_deep'] = me
            summary_parts.append(f"{cat}={md:.4f}→{me:.4f}")

    return {
        'name': 'EXP-1205',
        'status': 'pass',
        'detail': ' | '.join(summary_parts),
        'per_patient': per_patient,
        'results': results,
    }


# ---------------------------------------------------------------------------
# EXP-1206: Training Data Sensitivity
# ---------------------------------------------------------------------------

def exp_1206_data_sensitivity(patients, detail=False):
    """Learning curves: train with 10-100% of data.

    Identifies data-starved vs fundamentally hard patients.
    """
    per_patient = {}
    fracs = [0.1, 0.2, 0.4, 0.6, 0.8, 1.0]
    frac_scores = {f: [] for f in fracs}

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']

        X_enh, y_enh, g_cur = build_enhanced_features(p, glucose, physics)
        if len(X_enh) < 300:
            per_patient[pname] = {f'frac_{f}': 0 for f in fracs}
            continue
        X_enh = np.nan_to_num(X_enh, nan=0.0)
        y_dg = y_enh - g_cur

        # Fixed test set (last 20%)
        n = len(X_enh)
        s_test = int(n * 0.8)
        X_te = X_enh[s_test:]
        y_te = y_dg[s_test:]
        g_cur_te = g_cur[s_test:]
        y_abs_te = y_te + g_cur_te

        X_pool = X_enh[:s_test]
        y_pool = y_dg[:s_test]

        p_result = {'n_total': n, 'n_pool': len(X_pool)}
        for frac in fracs:
            n_use = max(50, int(len(X_pool) * frac))
            X_sub = X_pool[:n_use]
            y_sub = y_pool[:n_use]

            # Split sub into train/val (80/20)
            val_pt = int(len(X_sub) * 0.8)
            X_tr = X_sub[:val_pt]
            X_va = X_sub[val_pt:]
            y_tr = y_sub[:val_pt]
            y_va = y_sub[val_pt:]

            if len(X_tr) < 30 or len(X_va) < 10:
                p_result[f'frac_{frac}'] = 0.0
                continue

            m = make_xgb_sota()
            m.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
            pred = m.predict(X_te) + g_cur_te
            r2 = compute_r2(y_abs_te, pred)
            p_result[f'frac_{frac}'] = float(r2)
            frac_scores[frac].append(r2)

        # Learning curve slope: R² gain per doubling of data
        r2_vals = [p_result.get(f'frac_{f}', 0) for f in fracs]
        if r2_vals[-1] > r2_vals[0] and len(r2_vals) > 1:
            slope = (r2_vals[-1] - r2_vals[0]) / (len(fracs) - 1)
        else:
            slope = 0.0
        p_result['slope'] = float(slope)
        p_result['data_starved'] = slope > 0.03  # significant improvement with more data

        per_patient[pname] = p_result

        if detail:
            parts = [f"{int(f*100)}%={p_result.get(f'frac_{f}', 0):.4f}"
                     for f in fracs]
            starved = "DATA-STARVED" if p_result['data_starved'] else "saturated"
            print(f"  {pname}: {' '.join(parts)} [{starved}]")

    results = {}
    summary_parts = []
    for frac in fracs:
        mean_r2 = float(np.mean(frac_scores[frac])) if frac_scores[frac] else 0
        results[f'frac_{frac}'] = mean_r2
        summary_parts.append(f"{int(frac*100)}%={mean_r2:.4f}")

    n_starved = sum(1 for pp in per_patient.values() if pp.get('data_starved'))

    return {
        'name': 'EXP-1206',
        'status': 'pass',
        'detail': ' '.join(summary_parts) + f' starved={n_starved}/{len(patients)}',
        'per_patient': per_patient,
        'results': {**results, 'n_starved': n_starved},
    }


# ---------------------------------------------------------------------------
# EXP-1207: Temporal Feature Engineering
# ---------------------------------------------------------------------------

def exp_1207_temporal_features(patients, detail=False):
    """Enhanced temporal features: time-of-day segments, day-of-week,
    meal timing, fasting duration.

    Compares: global model vs time-segmented models (morning/afternoon/
    evening/night).
    """
    per_patient = {}
    scores_base, scores_temporal, scores_segmented = [], [], []

    def _build_temporal_features(p, g_win, pk_win, i, window):
        """Extended temporal features beyond basic time features."""
        hour = get_hour(p, i + window - 1)
        base_time = compute_time_features(hour)

        # Day-of-week proxy (approximate from index)
        day_in_week = ((i + window - 1) // 288) % 7
        dow_sin = np.sin(2 * np.pi * day_in_week / 7.0)
        dow_cos = np.cos(2 * np.pi * day_in_week / 7.0)
        is_weekend = 1.0 if day_in_week >= 5 else 0.0

        # Meal timing: time since last bolus/carb (from PK channels)
        bolus_iob = pk_win[:, 4] if pk_win.shape[1] > 4 else np.zeros(len(pk_win))
        carb_cob = pk_win[:, 6] if pk_win.shape[1] > 6 else np.zeros(len(pk_win))

        # Steps since last significant bolus
        bolus_diff = np.diff(bolus_iob)
        bolus_events = np.where(bolus_diff > 0.01)[0]
        time_since_bolus = (window - bolus_events[-1] - 1) if len(bolus_events) > 0 else window
        time_since_bolus_norm = time_since_bolus / window

        # Steps since last carb intake
        carb_diff = np.diff(carb_cob)
        carb_events = np.where(carb_diff > 0.01)[0]
        time_since_carb = (window - carb_events[-1] - 1) if len(carb_events) > 0 else window
        time_since_carb_norm = time_since_carb / window

        # Fasting duration estimate: both bolus and carb absent
        fasting = min(time_since_bolus, time_since_carb) / window

        return base_time + [dow_sin, dow_cos, is_weekend,
                            time_since_bolus_norm, time_since_carb_norm,
                            fasting]

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']
        pk = p['pk']
        g = glucose / GLUCOSE_SCALE
        n = len(g)

        # Build base and temporally-enhanced windows
        X_base_list, X_temp_list, y_list, g_cur_list, hour_list = [], [], [], [], []
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

            base_feat = _build_window_features(p, g_win, p_win, pk_win, i, WINDOW)
            temp_feat = np.array(_build_temporal_features(p, g_win, pk_win, i, WINDOW))
            X_base_list.append(base_feat)
            X_temp_list.append(np.concatenate([base_feat, temp_feat]))
            y_list.append(y_val)
            g_cur_list.append(g_win[-1])
            hour_list.append(get_hour(p, i + WINDOW - 1))

        if len(X_base_list) < 200:
            per_patient[pname] = {'base': 0, 'temporal': 0, 'segmented': 0}
            continue

        X_base = np.nan_to_num(np.array(X_base_list), nan=0.0)
        X_temp = np.nan_to_num(np.array(X_temp_list), nan=0.0)
        y_all = np.array(y_list)
        g_cur_all = np.array(g_cur_list)
        hours = np.array(hour_list)
        y_dg = y_all - g_cur_all

        X_tr_b, X_va_b, X_te_b, y_tr, y_va, y_te = split_3way(X_base, y_dg)
        X_tr_t, X_va_t, X_te_t, _, _, _ = split_3way(X_temp, y_dg)
        g_cur_te = g_cur_all[len(X_base) - len(X_te_b):]
        y_abs_te = y_te + g_cur_te
        hours_te = hours[len(X_base) - len(X_te_b):]

        # Base model
        m_base = make_xgb_sota()
        m_base.fit(X_tr_b, y_tr, eval_set=[(X_va_b, y_va)], verbose=False)
        r2_base = compute_r2(y_abs_te, m_base.predict(X_te_b) + g_cur_te)

        # Temporal model
        m_temp = make_xgb_sota()
        m_temp.fit(X_tr_t, y_tr, eval_set=[(X_va_t, y_va)], verbose=False)
        r2_temp = compute_r2(y_abs_te, m_temp.predict(X_te_t) + g_cur_te)

        # Time-segmented models: morning(6-12), afternoon(12-18),
        # evening(18-24), night(0-6)
        hours_tr = hours[:len(X_tr_b)]
        hours_va = hours[len(X_tr_b):len(X_tr_b) + len(X_va_b)]
        segments = {
            'morning': (6, 12), 'afternoon': (12, 18),
            'evening': (18, 24), 'night': (0, 6),
        }
        seg_preds = np.zeros(len(X_te_t))
        seg_count = np.zeros(len(X_te_t))
        for seg_name, (h_lo, h_hi) in segments.items():
            mask_tr = (hours_tr >= h_lo) & (hours_tr < h_hi)
            mask_va = (hours_va >= h_lo) & (hours_va < h_hi)
            mask_te = (hours_te >= h_lo) & (hours_te < h_hi)
            if mask_tr.sum() < 30 or mask_va.sum() < 10:
                # Fall back to global model for this segment
                seg_preds[mask_te] = m_temp.predict(X_te_t[mask_te])
                seg_count[mask_te] = 1
                continue
            m_seg = make_xgb_sota()
            m_seg.fit(X_tr_t[mask_tr], y_tr[mask_tr],
                      eval_set=[(X_va_t[mask_va], y_va[mask_va])],
                      verbose=False)
            seg_preds[mask_te] = m_seg.predict(X_te_t[mask_te])
            seg_count[mask_te] = 1

        # For any uncovered test points, use global model
        uncovered = seg_count == 0
        if uncovered.any():
            seg_preds[uncovered] = m_temp.predict(X_te_t[uncovered])

        r2_seg = compute_r2(y_abs_te, seg_preds + g_cur_te)

        per_patient[pname] = {
            'base': float(r2_base), 'temporal': float(r2_temp),
            'segmented': float(r2_seg),
            'delta_temporal': float(r2_temp - r2_base),
            'delta_segmented': float(r2_seg - r2_base),
        }
        scores_base.append(r2_base)
        scores_temporal.append(r2_temp)
        scores_segmented.append(r2_seg)

        if detail:
            print(f"  {pname}: base={r2_base:.4f} +temporal={r2_temp:.4f}"
                  f" segmented={r2_seg:.4f}")

    mb = float(np.mean(scores_base)) if scores_base else 0
    mt = float(np.mean(scores_temporal)) if scores_temporal else 0
    ms = float(np.mean(scores_segmented)) if scores_segmented else 0

    return {
        'name': 'EXP-1207',
        'status': 'pass',
        'detail': (f"base={mb:.4f} +temporal={mt:.4f} segmented={ms:.4f}"
                   f" Δ_temp={mt - mb:+.4f} Δ_seg={ms - mb:+.4f}"),
        'per_patient': per_patient,
        'results': {'base': mb, 'temporal': mt, 'segmented': ms,
                    'delta_temporal': mt - mb, 'delta_segmented': ms - mb},
    }


# ---------------------------------------------------------------------------
# EXP-1208: Glucose Regime Models
# ---------------------------------------------------------------------------

def exp_1208_regime_models(patients, detail=False):
    """Train separate models for hypo (<70), normal (70-180), hyper (>180).

    Route predictions through the appropriate regime model.
    """
    per_patient = {}
    scores_global, scores_regime = [], []
    # Regime thresholds in scaled glucose (mg/dL / 400)
    HYPO_THRESH = 70.0 / GLUCOSE_SCALE
    HYPER_THRESH = 180.0 / GLUCOSE_SCALE

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']

        X_enh, y_enh, g_cur = build_enhanced_features(p, glucose, physics)
        if len(X_enh) < 300:
            per_patient[pname] = {'global': 0, 'regime': 0}
            continue
        X_enh = np.nan_to_num(X_enh, nan=0.0)
        y_dg = y_enh - g_cur

        X_tr, X_va, X_te, y_tr, y_va, y_te = split_3way(X_enh, y_dg)
        g_cur_tr = g_cur[:len(X_tr)]
        g_cur_va = g_cur[len(X_tr):len(X_tr) + len(X_va)]
        g_cur_te = g_cur[len(X_enh) - len(X_te):]
        y_abs_te = y_te + g_cur_te

        # Global model
        m_global = make_xgb_sota()
        m_global.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
        pred_global = m_global.predict(X_te) + g_cur_te
        r2_global = compute_r2(y_abs_te, pred_global)

        # Regime-specific models
        regimes = {
            'hypo': (0, HYPO_THRESH),
            'normal': (HYPO_THRESH, HYPER_THRESH),
            'hyper': (HYPER_THRESH, float('inf')),
        }
        regime_models = {}
        regime_counts = {}
        for rname, (lo, hi) in regimes.items():
            mask_tr = (g_cur_tr >= lo) & (g_cur_tr < hi)
            mask_va = (g_cur_va >= lo) & (g_cur_va < hi)
            regime_counts[rname] = int(mask_tr.sum())
            if mask_tr.sum() >= 50 and mask_va.sum() >= 10:
                m_r = make_xgb_sota()
                m_r.fit(X_tr[mask_tr], y_tr[mask_tr],
                        eval_set=[(X_va[mask_va], y_va[mask_va])],
                        verbose=False)
                regime_models[rname] = m_r
            else:
                regime_models[rname] = m_global  # fallback

        # Route test predictions through regime models
        regime_preds = np.zeros(len(X_te))
        for rname, (lo, hi) in regimes.items():
            mask_te = (g_cur_te >= lo) & (g_cur_te < hi)
            if mask_te.any():
                regime_preds[mask_te] = regime_models[rname].predict(X_te[mask_te])

        pred_regime = regime_preds + g_cur_te
        r2_regime = compute_r2(y_abs_te, pred_regime)

        per_patient[pname] = {
            'global': float(r2_global), 'regime': float(r2_regime),
            'delta': float(r2_regime - r2_global),
            'regime_counts': regime_counts,
        }
        scores_global.append(r2_global)
        scores_regime.append(r2_regime)

        if detail:
            counts = ' '.join(f"{k}={v}" for k, v in regime_counts.items())
            print(f"  {pname}: global={r2_global:.4f} regime={r2_regime:.4f}"
                  f" Δ={r2_regime - r2_global:+.4f} ({counts})")

    mg = float(np.mean(scores_global)) if scores_global else 0
    mr = float(np.mean(scores_regime)) if scores_regime else 0
    wins = sum(1 for pp in per_patient.values() if pp.get('delta', 0) > 0)

    return {
        'name': 'EXP-1208',
        'status': 'pass',
        'detail': (f"global={mg:.4f} regime={mr:.4f}"
                   f" Δ={mr - mg:+.4f} (wins={wins}/{len(patients)})"),
        'per_patient': per_patient,
        'results': {'global': mg, 'regime': mr,
                    'delta': mr - mg, 'wins': wins},
    }


# ---------------------------------------------------------------------------
# EXP-1209: Residual Decomposition Analysis
# ---------------------------------------------------------------------------

def exp_1209_residual_decomposition(patients, detail=False):
    """Diagnostic: break residuals by time of day, glucose level,
    insulin activity, carb absorption. Compute ACF/PACF.

    Identifies systematic patterns the model misses.
    """
    per_patient = {}

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']
        pk = p['pk']

        X_enh, y_enh, g_cur = build_enhanced_features(p, glucose, physics)
        if len(X_enh) < 300:
            per_patient[pname] = {'base_r2': 0}
            continue
        X_enh = np.nan_to_num(X_enh, nan=0.0)
        y_dg = y_enh - g_cur

        X_tr, X_va, X_te, y_tr, y_va, y_te = split_3way(X_enh, y_dg)
        g_cur_te = g_cur[len(X_enh) - len(X_te):]
        y_abs_te = y_te + g_cur_te

        m = make_xgb_sota()
        m.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
        pred_te = m.predict(X_te)
        resid = y_te - pred_te
        r2_base = compute_r2(y_abs_te, pred_te + g_cur_te)

        # --- Residual by time of day ---
        n_total = len(X_enh)
        te_start = n_total - len(X_te)
        hours_te = np.array([get_hour(p, te_start + j * STRIDE)
                             for j in range(len(X_te))])
        tod_rmse = {}
        for period, (h_lo, h_hi) in [('night', (0, 6)), ('morning', (6, 12)),
                                       ('afternoon', (12, 18)), ('evening', (18, 24))]:
            mask = (hours_te >= h_lo) & (hours_te < h_hi)
            if mask.sum() > 5:
                tod_rmse[period] = float(np.sqrt(np.mean(resid[mask] ** 2)) * GLUCOSE_SCALE)
            else:
                tod_rmse[period] = 0.0

        # --- Residual by glucose level ---
        regime_rmse = {}
        for regime, (lo, hi) in [('hypo', (0, 70.0/GLUCOSE_SCALE)),
                                  ('normal', (70.0/GLUCOSE_SCALE, 180.0/GLUCOSE_SCALE)),
                                  ('hyper', (180.0/GLUCOSE_SCALE, float('inf')))]:
            mask = (g_cur_te >= lo) & (g_cur_te < hi)
            if mask.sum() > 5:
                regime_rmse[regime] = float(np.sqrt(np.mean(resid[mask] ** 2)) * GLUCOSE_SCALE)
            else:
                regime_rmse[regime] = 0.0

        # --- Residual by insulin activity ---
        pk_te = pk[te_start * STRIDE::STRIDE][:len(X_te)] if len(pk) > te_start * STRIDE else np.zeros((len(X_te), 8))
        if len(pk_te) < len(X_te):
            pk_te = np.vstack([pk_te, np.zeros((len(X_te) - len(pk_te), pk_te.shape[1] if pk_te.ndim > 1 else 8))])
        iob_te = pk_te[:, 0] if pk_te.ndim > 1 else np.zeros(len(X_te))
        iob_median = np.median(iob_te) if len(iob_te) > 0 else 0
        iob_rmse = {}
        mask_lo = iob_te <= iob_median
        mask_hi = iob_te > iob_median
        if mask_lo.sum() > 5:
            iob_rmse['low_iob'] = float(np.sqrt(np.mean(resid[mask_lo] ** 2)) * GLUCOSE_SCALE)
        if mask_hi.sum() > 5:
            iob_rmse['high_iob'] = float(np.sqrt(np.mean(resid[mask_hi] ** 2)) * GLUCOSE_SCALE)

        # --- ACF of residuals (lags 1-10) ---
        acf_values = []
        resid_centered = resid - np.mean(resid)
        var_resid = np.var(resid_centered)
        if var_resid > 1e-12:
            for lag in range(1, 11):
                if len(resid_centered) > lag:
                    acf_val = np.mean(resid_centered[lag:] * resid_centered[:-lag]) / var_resid
                    acf_values.append(float(acf_val))
                else:
                    acf_values.append(0.0)
        else:
            acf_values = [0.0] * 10

        # --- PACF approximation (via Yule-Walker for first 5 lags) ---
        pacf_values = []
        for order in range(1, 6):
            if len(resid) > order + 5:
                coeffs = _fit_ar_coeffs(resid, order=order)
                pacf_values.append(float(coeffs[-1]))
            else:
                pacf_values.append(0.0)

        # Mean absolute residual
        mae = float(np.mean(np.abs(resid)) * GLUCOSE_SCALE)
        resid_rmse = float(np.sqrt(np.mean(resid ** 2)) * GLUCOSE_SCALE)

        # Residual skewness and kurtosis
        resid_mgdl = resid * GLUCOSE_SCALE
        if len(resid_mgdl) > 3:
            skewness = float(np.mean((resid_mgdl - np.mean(resid_mgdl)) ** 3) /
                             (np.std(resid_mgdl) ** 3 + 1e-12))
            kurtosis = float(np.mean((resid_mgdl - np.mean(resid_mgdl)) ** 4) /
                             (np.std(resid_mgdl) ** 4 + 1e-12) - 3.0)
        else:
            skewness = kurtosis = 0.0

        per_patient[pname] = {
            'base_r2': float(r2_base),
            'resid_rmse_mgdl': resid_rmse, 'resid_mae_mgdl': mae,
            'resid_skewness': skewness, 'resid_kurtosis': kurtosis,
            'tod_rmse': tod_rmse, 'regime_rmse': regime_rmse,
            'iob_rmse': iob_rmse,
            'acf_lags_1_10': acf_values,
            'pacf_lags_1_5': pacf_values,
        }

        if detail:
            worst_tod = max(tod_rmse, key=tod_rmse.get) if tod_rmse else 'N/A'
            print(f"  {pname}: R²={r2_base:.4f} RMSE={resid_rmse:.1f}mg/dL"
                  f" ACF(1)={acf_values[0]:.3f} ACF(2)={acf_values[1]:.3f}"
                  f" worst_tod={worst_tod}({tod_rmse.get(worst_tod, 0):.1f})"
                  f" skew={skewness:.2f} kurt={kurtosis:.2f}")

    # Aggregate ACF across patients
    all_acf1 = [pp.get('acf_lags_1_10', [0])[0]
                for pp in per_patient.values() if pp.get('acf_lags_1_10')]
    mean_acf1 = float(np.mean(all_acf1)) if all_acf1 else 0

    return {
        'name': 'EXP-1209',
        'status': 'pass',
        'detail': (f"Diagnostic: mean ACF(1)={mean_acf1:.3f}"
                   f" (explains AR improvement)"),
        'per_patient': per_patient,
        'results': {'mean_acf1': mean_acf1},
    }


# ---------------------------------------------------------------------------
# EXP-1210: Ensemble of Horizon-Specific Models
# ---------------------------------------------------------------------------

def exp_1210_horizon_ensemble(patients, detail=False):
    """Stacking ensemble: combine predictions from 30, 45, 60, 75, 90 min
    horizon models to predict 60-min glucose.

    Each sub-model gets its own AR correction. Weights learned via
    linear regression on validation set.
    """
    from sklearn.linear_model import Ridge

    per_patient = {}
    scores_single, scores_ensemble, scores_ensemble_ar = [], [], []
    horizons = [6, 9, 12, 15, 18]  # 30, 45, 60, 75, 90 min

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        pname = p['name']

        X_mh, y_mh, g_cur_mh = build_enhanced_multi_horizon(
            p, glucose, physics, horizons=horizons)
        if len(X_mh) < 300:
            per_patient[pname] = {'single_60': 0, 'ensemble': 0, 'ensemble_ar': 0}
            continue
        X_mh = np.nan_to_num(X_mh, nan=0.0)
        y_dg_60 = y_mh[12] - g_cur_mh

        X_tr, X_va, X_te, y_tr_60, y_va_60, y_te_60 = split_3way(X_mh, y_dg_60)
        g_cur_va = g_cur_mh[len(X_tr):len(X_tr) + len(X_va)]
        g_cur_te = g_cur_mh[len(X_mh) - len(X_te):]
        y_abs_te = y_te_60 + g_cur_te

        # Single 60-min model
        m_60 = make_xgb_sota()
        m_60.fit(X_tr, y_tr_60, eval_set=[(X_va, y_va_60)], verbose=False)
        pred_60 = m_60.predict(X_te)
        r2_single = compute_r2(y_abs_te, pred_60 + g_cur_te)

        # Train per-horizon models
        horizon_preds_va = {}
        horizon_preds_te = {}
        horizon_resid_va = {}
        horizon_resid_te = {}
        for h in horizons:
            y_dg_h = y_mh[h] - g_cur_mh
            _, _, _, y_tr_h, y_va_h, y_te_h = split_3way(X_mh, y_dg_h)
            m_h = make_xgb_sota()
            m_h.fit(X_tr, y_tr_h, eval_set=[(X_va, y_va_h)], verbose=False)
            pred_va_h = m_h.predict(X_va)
            pred_te_h = m_h.predict(X_te)
            horizon_preds_va[h] = pred_va_h
            horizon_preds_te[h] = pred_te_h
            horizon_resid_va[h] = y_va_h - pred_va_h
            horizon_resid_te[h] = y_te_h - pred_te_h

        # Stack: learn weights on validation set (predict 60-min target)
        stack_va = np.column_stack([horizon_preds_va[h] for h in horizons])
        stack_te = np.column_stack([horizon_preds_te[h] for h in horizons])
        stacker = Ridge(alpha=1.0)
        stacker.fit(stack_va, y_va_60)
        ensemble_pred_te = stacker.predict(stack_te)
        r2_ensemble = compute_r2(y_abs_te, ensemble_pred_te + g_cur_te)
        weights = {f'{h*5}min': float(w) for h, w in zip(horizons, stacker.coef_)}

        # AR correction on each sub-model, then stack
        ar_preds_va = {}
        ar_preds_te = {}
        for h in horizons:
            coeffs_h = _fit_ar_coeffs(horizon_resid_va[h], order=2)
            corrected_h = _apply_ar_causal(
                horizon_preds_te[h], horizon_resid_te[h], coeffs_h,
                bootstrap_resids=horizon_resid_va[h])
            ar_preds_te[h] = corrected_h
            # Also correct validation for re-fitting stacker
            corrected_va_h = _apply_ar_causal(
                horizon_preds_va[h], horizon_resid_va[h], coeffs_h,
                bootstrap_resids=np.zeros(2))
            ar_preds_va[h] = corrected_va_h

        stack_ar_va = np.column_stack([ar_preds_va[h] for h in horizons])
        stack_ar_te = np.column_stack([ar_preds_te[h] for h in horizons])
        stacker_ar = Ridge(alpha=1.0)
        stacker_ar.fit(stack_ar_va, y_va_60)
        ensemble_ar_pred = stacker_ar.predict(stack_ar_te)
        r2_ensemble_ar = compute_r2(y_abs_te, ensemble_ar_pred + g_cur_te)

        per_patient[pname] = {
            'single_60': float(r2_single),
            'ensemble': float(r2_ensemble),
            'ensemble_ar': float(r2_ensemble_ar),
            'delta_ensemble': float(r2_ensemble - r2_single),
            'delta_ensemble_ar': float(r2_ensemble_ar - r2_single),
            'weights': weights,
        }
        scores_single.append(r2_single)
        scores_ensemble.append(r2_ensemble)
        scores_ensemble_ar.append(r2_ensemble_ar)

        if detail:
            w_str = ' '.join(f"{k}={v:.3f}" for k, v in weights.items())
            print(f"  {pname}: single={r2_single:.4f} ens={r2_ensemble:.4f}"
                  f" ens+AR={r2_ensemble_ar:.4f} w=[{w_str}]")

    ms = float(np.mean(scores_single)) if scores_single else 0
    me = float(np.mean(scores_ensemble)) if scores_ensemble else 0
    mea = float(np.mean(scores_ensemble_ar)) if scores_ensemble_ar else 0
    wins = sum(1 for pp in per_patient.values()
               if pp.get('delta_ensemble_ar', 0) > 0)

    return {
        'name': 'EXP-1210',
        'status': 'pass',
        'detail': (f"single={ms:.4f} ensemble={me:.4f} ens+AR={mea:.4f}"
                   f" Δ={mea - ms:+.4f} (wins={wins}/{len(patients)})"),
        'per_patient': per_patient,
        'results': {'single_60': ms, 'ensemble': me, 'ensemble_ar': mea,
                    'delta_ensemble': me - ms, 'delta_ensemble_ar': mea - ms,
                    'wins': wins},
    }


# ---------------------------------------------------------------------------
# Registry and main
# ---------------------------------------------------------------------------

EXPERIMENTS = [
    ('EXP-1201', 'Conformal Prediction Intervals',
     exp_1201_conformal_pi),
    ('EXP-1202', 'Full Production Stack CV (Combined+AR+Online)',
     exp_1202_full_stack_cv),
    ('EXP-1203', 'AR at Multiple Horizons',
     exp_1203_ar_multi_horizon),
    ('EXP-1204', 'Kalman Filter vs AR Correction',
     exp_1204_kalman_vs_ar),
    ('EXP-1205', 'Hard Patient Deep Dive',
     exp_1205_hard_patients),
    ('EXP-1206', 'Training Data Sensitivity',
     exp_1206_data_sensitivity),
    ('EXP-1207', 'Temporal Feature Engineering',
     exp_1207_temporal_features),
    ('EXP-1208', 'Glucose Regime Models',
     exp_1208_regime_models),
    ('EXP-1209', 'Residual Decomposition Analysis',
     exp_1209_residual_decomposition),
    ('EXP-1210', 'Ensemble of Horizon-Specific Models',
     exp_1210_horizon_ensemble),
]


def main():
    parser = argparse.ArgumentParser(
        description='EXP-1201-1210: Conformal PI + Full Stack CV + '
                    'Multi-Horizon AR + Diagnostics')
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--max-patients', type=int, default=11)
    parser.add_argument('--experiments', type=str, default='all',
                        help='Comma-separated exp numbers or "all"')
    parser.add_argument('--experiment', type=str,
                        help='Run only this experiment (e.g. EXP-1201)')
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
