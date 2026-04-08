#!/usr/bin/env python3
"""EXP-1211 to EXP-1220: Horizon Ensemble CV + Asymmetric Loss + Diagnostics.

Campaign status after 210 experiments (EXP-1001 to EXP-1210):
- Full production stack 5-fold CV: R²=0.664 (combined+AR+online)
- Horizon ensemble + AR: R²=0.839 (single split, UNVALIDATED)
- Conformal PIs: 80% coverage, 75.5 mg/dL width (AR-corrected)
- AR benefit scales with horizon: 120min +0.430 lift

This batch validates the horizon ensemble and explores remaining frontiers:

  EXP-1211: Horizon Ensemble 5-Fold CV                       ★★★★★ CRITICAL
  EXP-1212: Asymmetric Loss for Spike Prediction              ★★★★
  EXP-1213: Adaptive Rolling AR Coefficients                  ★★★★
  EXP-1214: Patient h Data Imputation                         ★★★
  EXP-1215: Conformal PI at Multiple Horizons                 ★★★★
  EXP-1216: Ensemble with Fewer Models                        ★★★
  EXP-1217: Feature Importance Stability                      ★★★
  EXP-1218: Prediction Error by Glucose Context               ★★★
  EXP-1219: Multi-Patient Pooled Model                        ★★★★
  EXP-1220: Production Pipeline Robustness                    ★★★

Run:
    PYTHONPATH=tools python -m cgmencode.exp_clinical_1211 --detail --save --max-patients 11
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
from sklearn.linear_model import LinearRegression, Ridge

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
# Shared helpers (mirror exp_clinical_1201 patterns)
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
    params = dict(n_estimators=500, max_depth=4, learning_rate=0.05,
                  subsample=0.8, colsample_bytree=0.8)
    params.update(overrides)
    return make_xgb(**params)


def split_3way(X, y, fracs=(0.6, 0.2, 0.2)):
    n = len(X)
    s1 = int(n * fracs[0])
    s2 = int(n * (fracs[0] + fracs[1]))
    return (X[:s1], X[s1:s2], X[s2:], y[:s1], y[s1:s2], y[s2:])


def get_hour(p, idx):
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
# Feature builders (from exp_clinical_1201)
# ---------------------------------------------------------------------------

def compute_derivative_features(g_win):
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
    n = len(pk_win)
    if n < 2:
        return np.zeros(pk_win.shape[1] if pk_win.ndim > 1 else 1)
    weights = np.exp(-alpha * np.arange(n)[::-1])
    weights /= weights.sum()
    pk_ema_slow = np.average(pk_win, axis=0, weights=weights)
    return pk_win[-1] - pk_ema_slow


def _build_window_features(p, g_win, p_win, pk_win, i, window):
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


def _fit_ar_coeffs(residuals, order=2):
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
    order = len(coeffs)
    buf = list(bootstrap_resids[-order:])
    corrections = np.zeros(len(pred_te))
    for t in range(len(pred_te)):
        corr = sum(coeffs[j] * buf[-(j + 1)] for j in range(order))
        corrections[t] = corr
        buf.append(residuals_te[t])
    return pred_te + corrections


def _pipeline_single(p, horizon=HORIZON):
    """Run single-model pipeline: build features, train, predict, AR correct."""
    glucose, physics = prepare_patient_raw(p)
    X, y, g_cur = build_enhanced_features(p, glucose, physics, horizon=horizon)
    if len(X) < 50:
        return None
    X_tr, X_va, X_te, y_tr, y_va, y_te = split_3way(X, y)
    model = make_xgb_sota()
    model.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
    pred_va = model.predict(X_va)
    pred_te = model.predict(X_te)
    r2_base = compute_r2(y_te, pred_te)
    resid_va = y_va - pred_va
    resid_te = y_te - pred_te
    coeffs = _fit_ar_coeffs(resid_va, order=2)
    pred_ar = _apply_ar_causal(pred_te, resid_te, coeffs, resid_va)
    r2_ar = compute_r2(y_te, pred_ar)
    return {
        'model': model, 'X_tr': X_tr, 'y_tr': y_tr,
        'X_va': X_va, 'y_va': y_va, 'X_te': X_te, 'y_te': y_te,
        'pred_va': pred_va, 'pred_te': pred_te, 'pred_ar': pred_ar,
        'resid_va': resid_va, 'resid_te': resid_te,
        'coeffs': coeffs, 'r2_base': r2_base, 'r2_ar': r2_ar,
        'glucose': glucose, 'physics': physics,
    }


# ---------------------------------------------------------------------------
# EXP-1211: Horizon Ensemble 5-Fold CV (CRITICAL)
# ---------------------------------------------------------------------------

def exp_1211_horizon_ensemble_cv(patients, detail=False):
    """Validate R²=0.839 horizon ensemble+AR with 5-fold TimeSeriesSplit."""
    horizons = [6, 9, 12, 15, 18]  # 30, 45, 60, 75, 90 min
    per_patient = {}

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        # Build features for max horizon
        X, y_dict, g_cur = build_enhanced_multi_horizon(
            p, glucose, physics, horizons=horizons)
        y_60 = y_dict[12]  # primary target

        if len(X) < 100:
            print(f"  {p['name']}: SKIP (insufficient data)")
            continue

        tscv = TimeSeriesSplit(n_splits=5)
        single_scores, ens_scores, ens_ar_scores = [], [], []

        for fold, (train_idx, test_idx) in enumerate(tscv.split(X)):
            # Split train into train+val for AR fitting
            n_train = len(train_idx)
            val_size = max(int(n_train * 0.25), 20)
            tr_idx = train_idx[:n_train - val_size]
            va_idx = train_idx[n_train - val_size:]

            X_tr, X_va, X_te = X[tr_idx], X[va_idx], X[test_idx]
            y_te = y_60[test_idx]

            # Train single 60-min model
            m60 = make_xgb_sota()
            m60.fit(X_tr, y_dict[12][tr_idx],
                    eval_set=[(X_va, y_dict[12][va_idx])], verbose=False)
            pred_single = m60.predict(X_te)
            single_scores.append(compute_r2(y_te, pred_single))

            # Train per-horizon models
            preds_va = {}
            preds_te = {}
            for h in horizons:
                m = make_xgb_sota()
                m.fit(X_tr, y_dict[h][tr_idx],
                      eval_set=[(X_va, y_dict[h][va_idx])], verbose=False)
                preds_va[h] = m.predict(X_va)
                preds_te[h] = m.predict(X_te)

            # Stack: fit linear weights on val predicting 60-min target
            stack_va = np.column_stack([preds_va[h] for h in horizons])
            stack_te = np.column_stack([preds_te[h] for h in horizons])
            stacker = Ridge(alpha=1.0)
            stacker.fit(stack_va, y_dict[12][va_idx])
            pred_ens = stacker.predict(stack_te)
            ens_scores.append(compute_r2(y_te, pred_ens))

            # AR correct each sub-model, then re-stack
            preds_ar_te = {}
            for h in horizons:
                resid_va_h = y_dict[h][va_idx] - preds_va[h]
                resid_te_h = y_dict[h][test_idx] - preds_te[h]
                coeffs_h = _fit_ar_coeffs(resid_va_h, order=2)
                preds_ar_te[h] = _apply_ar_causal(
                    preds_te[h], resid_te_h, coeffs_h, resid_va_h)

            stack_ar_te = np.column_stack([preds_ar_te[h] for h in horizons])
            # Re-fit stacker on AR-corrected val predictions
            preds_ar_va = {}
            for h in horizons:
                resid_va_h = y_dict[h][va_idx] - preds_va[h]
                # Self-AR on val (using leave-one-out style)
                coeffs_h = _fit_ar_coeffs(resid_va_h, order=2)
                preds_ar_va[h] = preds_va[h].copy()
                for t in range(2, len(preds_va[h])):
                    corr = coeffs_h[0] * resid_va_h[t-1] + coeffs_h[1] * resid_va_h[t-2]
                    preds_ar_va[h][t] += corr

            stack_ar_va = np.column_stack([preds_ar_va[h] for h in horizons])
            stacker_ar = Ridge(alpha=1.0)
            stacker_ar.fit(stack_ar_va, y_dict[12][va_idx])
            pred_ens_ar = stacker_ar.predict(stack_ar_te)
            ens_ar_scores.append(compute_r2(y_te, pred_ens_ar))

        ms = np.mean(single_scores)
        me = np.mean(ens_scores)
        mea = np.mean(ens_ar_scores)
        print(f"  {p['name']}: single={ms:.4f} ens={me:.4f} ens+AR={mea:.4f}"
              f" Δ_ens={me-ms:+.4f} Δ_ens_ar={mea-ms:+.4f}")
        per_patient[p['name']] = {
            'single_cv': round(ms, 4), 'ensemble_cv': round(me, 4),
            'ensemble_ar_cv': round(mea, 4),
        }

    names = list(per_patient.keys())
    ms = np.mean([per_patient[n]['single_cv'] for n in names])
    me = np.mean([per_patient[n]['ensemble_cv'] for n in names])
    mea = np.mean([per_patient[n]['ensemble_ar_cv'] for n in names])
    wins = sum(1 for n in names if per_patient[n]['ensemble_ar_cv'] > per_patient[n]['single_cv'])

    return {
        'status': 'pass',
        'detail': (f"5-fold CV: single={ms:.4f} ensemble={me:.4f} "
                   f"ens+AR={mea:.4f} Δ={mea-ms:+.4f} (wins={wins}/{len(names)})"),
        'per_patient': per_patient,
        'results': {'single_cv': ms, 'ensemble_cv': me, 'ensemble_ar_cv': mea},
    }


# ---------------------------------------------------------------------------
# EXP-1212: Asymmetric Loss for Spike Prediction
# ---------------------------------------------------------------------------

def exp_1212_asymmetric_loss(patients, detail=False):
    """Asymmetric loss to improve spike (>200 mg/dL) prediction."""
    per_patient = {}

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        X, y, g_cur = build_enhanced_features(p, glucose, physics)
        if len(X) < 50:
            continue
        X_tr, X_va, X_te, y_tr, y_va, y_te = split_3way(X, y)

        # Standard model
        m_std = make_xgb_sota()
        m_std.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
        pred_std = m_std.predict(X_te)
        r2_std = compute_r2(y_te, pred_std)

        # Spike mask (glucose > 200 mg/dL = 0.5 scaled)
        spike_mask = y_te > (200.0 / GLUCOSE_SCALE)
        rmse_std_spike = compute_rmse(y_te[spike_mask], pred_std[spike_mask]) if spike_mask.sum() > 10 else float('nan')

        best_gamma = 1.0
        best_spike_rmse = rmse_std_spike
        best_r2 = r2_std
        results_by_gamma = {'1.0': {'r2': r2_std, 'spike_rmse': rmse_std_spike}}

        for gamma in [1.5, 2.0, 3.0]:
            def make_asym_obj(g):
                def asym_obj(y_true, y_pred):
                    residual = y_true - y_pred
                    grad = np.where(residual > 0, -g * residual, -residual)
                    hess = np.where(residual > 0, g * np.ones_like(residual),
                                    np.ones_like(residual))
                    return grad, hess
                return asym_obj

            m_asym = make_xgb_sota()
            if XGB_AVAILABLE:
                m_asym = xgb.XGBRegressor(
                    n_estimators=500, max_depth=4, learning_rate=0.05,
                    subsample=0.8, colsample_bytree=0.8,
                    tree_method='hist', device='cuda', random_state=42,
                    verbosity=0, objective=make_asym_obj(gamma))
            m_asym.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
            pred_asym = m_asym.predict(X_te)
            r2_asym = compute_r2(y_te, pred_asym)
            rmse_asym_spike = compute_rmse(y_te[spike_mask], pred_asym[spike_mask]) if spike_mask.sum() > 10 else float('nan')

            results_by_gamma[str(gamma)] = {'r2': r2_asym, 'spike_rmse': rmse_asym_spike}
            if not np.isnan(rmse_asym_spike) and rmse_asym_spike < best_spike_rmse:
                best_spike_rmse = rmse_asym_spike
                best_gamma = gamma
                best_r2 = r2_asym

        print(f"  {p['name']}: std_R²={r2_std:.4f} spike_RMSE={rmse_std_spike:.1f}"
              f" best_γ={best_gamma} best_spike={best_spike_rmse:.1f}"
              f" R²@best={best_r2:.4f} n_spike={spike_mask.sum()}")
        per_patient[p['name']] = {
            'r2_standard': round(r2_std, 4),
            'spike_rmse_standard': round(rmse_std_spike, 1) if not np.isnan(rmse_std_spike) else None,
            'best_gamma': best_gamma,
            'r2_best': round(best_r2, 4),
            'spike_rmse_best': round(best_spike_rmse, 1) if not np.isnan(best_spike_rmse) else None,
            'n_spikes': int(spike_mask.sum()),
            'by_gamma': results_by_gamma,
        }

    names = list(per_patient.keys())
    mr2_std = np.mean([per_patient[n]['r2_standard'] for n in names])
    mr2_best = np.mean([per_patient[n]['r2_best'] for n in names])
    spike_improve = sum(1 for n in names
                        if per_patient[n]['spike_rmse_best'] is not None
                        and per_patient[n]['spike_rmse_standard'] is not None
                        and per_patient[n]['spike_rmse_best'] < per_patient[n]['spike_rmse_standard'])

    return {
        'status': 'pass',
        'detail': (f"std_R²={mr2_std:.4f} best_R²={mr2_best:.4f} "
                   f"spike_improved={spike_improve}/{len(names)}"),
        'per_patient': per_patient,
        'results': {'r2_standard': mr2_std, 'r2_best': mr2_best,
                    'spike_improved': spike_improve},
    }


# ---------------------------------------------------------------------------
# EXP-1213: Adaptive Rolling AR Coefficients
# ---------------------------------------------------------------------------

def exp_1213_adaptive_ar(patients, detail=False):
    """Compare fixed vs rolling-window AR coefficient fitting."""
    windows = [36, 72, 144, 288]  # 3h, 6h, 12h, 24h in 5-min steps
    per_patient = {}

    for p in patients:
        res = _pipeline_single(p)
        if res is None:
            continue

        r2_fixed = res['r2_ar']
        resid_va = res['resid_va']
        pred_te = res['pred_te']
        resid_te = res['resid_te']
        y_te = res['y_te']

        # Fixed AR (baseline)
        results = {'fixed': r2_fixed}

        # Rolling AR for each window size
        all_resids = np.concatenate([resid_va, resid_te])
        va_len = len(resid_va)

        for win in windows:
            pred_rolling = pred_te.copy()
            for t in range(len(pred_te)):
                # Use residuals from [va_len+t-win : va_len+t] to fit AR
                end_idx = va_len + t
                start_idx = max(0, end_idx - win)
                r_window = all_resids[start_idx:end_idx]
                if len(r_window) < 5:
                    continue
                coeffs = _fit_ar_coeffs(r_window, order=2)
                corr = coeffs[0] * all_resids[end_idx - 1] + coeffs[1] * all_resids[end_idx - 2]
                pred_rolling[t] += corr

            r2_rolling = compute_r2(y_te, pred_rolling)
            results[f'w{win}'] = r2_rolling

        best_key = max(results, key=results.get)
        print(f"  {p['name']}: fixed={r2_fixed:.4f}"
              + ''.join(f" w{w}={results[f'w{w}']:.4f}" for w in windows)
              + f" best={best_key}")
        per_patient[p['name']] = {k: round(v, 4) for k, v in results.items()}

    names = list(per_patient.keys())
    means = {}
    for key in ['fixed'] + [f'w{w}' for w in windows]:
        vals = [per_patient[n].get(key, 0) for n in names]
        means[key] = np.mean(vals)

    best_key = max(means, key=means.get)
    return {
        'status': 'pass',
        'detail': ' '.join(f"{k}={v:.4f}" for k, v in means.items()) + f" best={best_key}",
        'per_patient': per_patient,
        'results': means,
    }


# ---------------------------------------------------------------------------
# EXP-1214: Patient h Data Imputation
# ---------------------------------------------------------------------------

def exp_1214_imputation(patients, detail=False):
    """Test imputation strategies for high-NaN patients."""
    per_patient = {}

    for p in patients:
        glucose_raw = p['df']['glucose'].values.astype(float)
        nan_rate = np.isnan(glucose_raw).mean()

        # Strategy 0: Standard (baseline)
        res0 = _pipeline_single(p)
        r2_base = res0['r2_base'] if res0 else 0.0
        r2_ar_base = res0['r2_ar'] if res0 else 0.0

        # Strategy 1: Linear interpolation of short gaps (≤30 min)
        glucose_interp = glucose_raw.copy()
        nan_mask = np.isnan(glucose_interp)
        if nan_mask.any():
            valid = np.where(~nan_mask)[0]
            if len(valid) > 2:
                glucose_interp[nan_mask] = np.interp(
                    np.where(nan_mask)[0], valid, glucose_interp[valid])
        # Only interpolate gaps ≤ 6 steps
        glucose_short = glucose_raw.copy()
        in_gap = False
        gap_start = 0
        for i in range(len(glucose_short)):
            if np.isnan(glucose_short[i]):
                if not in_gap:
                    in_gap = True
                    gap_start = i
            else:
                if in_gap:
                    gap_len = i - gap_start
                    if gap_len <= 6:  # ≤30 min gap
                        # Linear interpolate
                        if gap_start > 0:
                            start_val = glucose_short[gap_start - 1]
                            end_val = glucose_short[i]
                            for j in range(gap_start, i):
                                frac = (j - gap_start + 1) / (gap_len + 1)
                                glucose_short[j] = start_val + frac * (end_val - start_val)
                    in_gap = False

        # Strategy 2: Full interpolation
        glucose_full_interp = glucose_raw.copy()
        nan_mask2 = np.isnan(glucose_full_interp)
        if nan_mask2.any():
            valid2 = np.where(~nan_mask2)[0]
            if len(valid2) > 2:
                glucose_full_interp[nan_mask2] = np.interp(
                    np.where(nan_mask2)[0], valid2, glucose_full_interp[valid2])

        # Strategy 3: Skip high-NaN windows (lower NaN threshold)
        # Already handled in build_enhanced_features with nan_threshold

        strategies = {}
        for strat_name, gluc in [('short_interp', glucose_short),
                                  ('full_interp', glucose_full_interp)]:
            # Rebuild with imputed glucose
            p_copy = dict(p)
            import pandas as pd
            df_copy = p['df'].copy()
            df_copy['glucose'] = gluc
            p_copy['df'] = df_copy
            try:
                res = _pipeline_single(p_copy)
                if res:
                    strategies[strat_name] = {
                        'r2': round(res['r2_base'], 4),
                        'r2_ar': round(res['r2_ar'], 4),
                    }
                else:
                    strategies[strat_name] = {'r2': 0.0, 'r2_ar': 0.0}
            except Exception:
                strategies[strat_name] = {'r2': 0.0, 'r2_ar': 0.0}

        best_strat = 'baseline'
        best_r2 = r2_ar_base
        for sn, sv in strategies.items():
            if sv['r2_ar'] > best_r2:
                best_r2 = sv['r2_ar']
                best_strat = sn

        print(f"  {p['name']}: NaN={nan_rate:.1%} base={r2_base:.4f} +AR={r2_ar_base:.4f}"
              + ''.join(f" {sn}={sv['r2_ar']:.4f}" for sn, sv in strategies.items())
              + f" best={best_strat}")
        per_patient[p['name']] = {
            'nan_rate': round(nan_rate, 3),
            'base_r2': round(r2_base, 4),
            'base_r2_ar': round(r2_ar_base, 4),
            'strategies': strategies,
            'best': best_strat,
        }

    names = list(per_patient.keys())
    m_base = np.mean([per_patient[n]['base_r2_ar'] for n in names])
    m_short = np.mean([per_patient[n]['strategies'].get('short_interp', {}).get('r2_ar', 0) for n in names])
    m_full = np.mean([per_patient[n]['strategies'].get('full_interp', {}).get('r2_ar', 0) for n in names])

    return {
        'status': 'pass',
        'detail': f"base_AR={m_base:.4f} short_interp={m_short:.4f} full_interp={m_full:.4f}",
        'per_patient': per_patient,
        'results': {'base_ar': m_base, 'short_interp': m_short, 'full_interp': m_full},
    }


# ---------------------------------------------------------------------------
# EXP-1215: Conformal PI at Multiple Horizons
# ---------------------------------------------------------------------------

def exp_1215_conformal_multi_horizon(patients, detail=False):
    """Conformal PIs at 30, 60, 90, 120 min horizons."""
    horizons_min = [30, 60, 90, 120]
    horizons_steps = [6, 12, 18, 24]
    alpha = 0.2  # 80% PI
    per_patient = {}

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        p_results = {}

        for h_min, h_step in zip(horizons_min, horizons_steps):
            X, y, g_cur = build_enhanced_features(p, glucose, physics, horizon=h_step)
            if len(X) < 50:
                p_results[f'{h_min}min'] = {'r2': 0.0, 'coverage': 0.0, 'width': 0.0}
                continue

            X_tr, X_cal, X_te, y_tr, y_cal, y_te = split_3way(X, y)
            model = make_xgb_sota()
            model.fit(X_tr, y_tr, eval_set=[(X_cal, y_cal)], verbose=False)
            pred_cal = model.predict(X_cal)
            pred_te = model.predict(X_te)

            # AR correction
            resid_cal = y_cal - pred_cal
            resid_te = y_te - pred_te
            coeffs = _fit_ar_coeffs(resid_cal, order=2)
            pred_ar = _apply_ar_causal(pred_te, resid_te, coeffs, resid_cal)
            r2_ar = compute_r2(y_te, pred_ar)

            # Conformal scores on AR-corrected calibration
            pred_cal_ar = pred_cal.copy()
            for t in range(2, len(pred_cal)):
                corr = coeffs[0] * resid_cal[t-1] + coeffs[1] * resid_cal[t-2]
                pred_cal_ar[t] += corr
            scores_ar = np.abs(y_cal - pred_cal_ar)
            q = np.quantile(scores_ar, 1 - alpha)

            # Apply conformal PI
            lower = pred_ar - q
            upper = pred_ar + q
            coverage = np.mean((y_te >= lower) & (y_te <= upper))
            width = 2 * q * GLUCOSE_SCALE  # in mg/dL

            p_results[f'{h_min}min'] = {
                'r2_ar': round(r2_ar, 4),
                'coverage': round(coverage, 3),
                'width': round(width, 1),
            }

        # Format output
        parts = [f"{k}: R²={v['r2_ar']:.3f} cov={v['coverage']:.1%} w={v['width']:.0f}mg"
                 for k, v in p_results.items()]
        print(f"  {p['name']}: " + " | ".join(parts))
        per_patient[p['name']] = p_results

    names = list(per_patient.keys())
    summary = {}
    for h_min in horizons_min:
        key = f'{h_min}min'
        covs = [per_patient[n][key]['coverage'] for n in names if key in per_patient[n]]
        widths = [per_patient[n][key]['width'] for n in names if key in per_patient[n]]
        r2s = [per_patient[n][key]['r2_ar'] for n in names if key in per_patient[n]]
        summary[key] = {
            'mean_r2': round(np.mean(r2s), 4),
            'mean_coverage': round(np.mean(covs), 3),
            'mean_width': round(np.mean(widths), 1),
        }

    detail_str = ' | '.join(
        f"{k}: R²={v['mean_r2']:.3f} cov={v['mean_coverage']:.1%} w={v['mean_width']:.0f}mg"
        for k, v in summary.items()
    )
    return {
        'status': 'pass',
        'detail': detail_str,
        'per_patient': per_patient,
        'results': summary,
    }


# ---------------------------------------------------------------------------
# EXP-1216: Ensemble with Fewer Models
# ---------------------------------------------------------------------------

def exp_1216_ensemble_size(patients, detail=False):
    """Find optimal number of horizon models for ensemble."""
    configs = {
        '2m': [6, 18],          # 30 + 90 min
        '3m': [6, 12, 18],      # 30 + 60 + 90 min
        '5m': [6, 9, 12, 15, 18],  # every 15 min
        '7m': [3, 6, 9, 12, 15, 18, 21],  # every 15 min wider
    }
    per_patient = {}

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        all_horizons = sorted(set(h for hs in configs.values() for h in hs))
        X, y_dict, g_cur = build_enhanced_multi_horizon(
            p, glucose, physics, horizons=all_horizons)

        if len(X) < 50:
            continue

        n = len(X)
        s1 = int(n * 0.6)
        s2 = int(n * 0.8)
        X_tr, X_va, X_te = X[:s1], X[s1:s2], X[s2:]
        y60_te = y_dict[12][s2:]
        y60_va = y_dict[12][s1:s2]

        # Train all sub-models once
        models = {}
        preds_va_all = {}
        preds_te_all = {}
        for h in all_horizons:
            m = make_xgb_sota()
            m.fit(X_tr, y_dict[h][:s1],
                  eval_set=[(X_va, y_dict[h][s1:s2])], verbose=False)
            models[h] = m
            preds_va_all[h] = m.predict(X_va)
            preds_te_all[h] = m.predict(X_te)

        # Single 60-min baseline
        r2_single = compute_r2(y60_te, preds_te_all[12])

        # Test each config
        p_results = {'single': r2_single}
        for cfg_name, horizons in configs.items():
            stack_va = np.column_stack([preds_va_all[h] for h in horizons])
            stack_te = np.column_stack([preds_te_all[h] for h in horizons])
            stacker = Ridge(alpha=1.0)
            stacker.fit(stack_va, y60_va)
            pred_ens = stacker.predict(stack_te)
            r2_ens = compute_r2(y60_te, pred_ens)

            # AR correct
            resid_va_ens = y60_va - stacker.predict(stack_va)
            resid_te_ens = y60_te - pred_ens
            coeffs = _fit_ar_coeffs(resid_va_ens, order=2)
            pred_ens_ar = _apply_ar_causal(pred_ens, resid_te_ens, coeffs, resid_va_ens)
            r2_ens_ar = compute_r2(y60_te, pred_ens_ar)

            p_results[cfg_name] = r2_ens
            p_results[f'{cfg_name}_ar'] = r2_ens_ar

        best_key = max(p_results, key=p_results.get)
        print(f"  {p['name']}: single={r2_single:.4f}"
              + ''.join(f" {k}={v:.4f}" for k, v in p_results.items() if k != 'single')
              + f" best={best_key}")
        per_patient[p['name']] = {k: round(v, 4) for k, v in p_results.items()}

    names = list(per_patient.keys())
    means = {}
    all_keys = set()
    for n in names:
        all_keys.update(per_patient[n].keys())
    for key in sorted(all_keys):
        vals = [per_patient[n].get(key, 0) for n in names]
        means[key] = round(np.mean(vals), 4)

    best_key = max(means, key=means.get)
    return {
        'status': 'pass',
        'detail': ' '.join(f"{k}={v:.4f}" for k, v in means.items()) + f" best={best_key}",
        'per_patient': per_patient,
        'results': means,
    }


# ---------------------------------------------------------------------------
# EXP-1217: Feature Importance Stability
# ---------------------------------------------------------------------------

def exp_1217_feature_importance(patients, detail=False):
    """Analyze which features matter consistently across patients."""
    per_patient = {}
    all_importances = []

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        X, y, g_cur = build_enhanced_features(p, glucose, physics)
        if len(X) < 50:
            continue

        X_tr, X_va, X_te, y_tr, y_va, y_te = split_3way(X, y)
        model = make_xgb_sota()
        model.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)

        if hasattr(model, 'feature_importances_'):
            imp = model.feature_importances_
        else:
            imp = np.zeros(X.shape[1])

        # Normalize to sum to 1
        imp_sum = imp.sum()
        if imp_sum > 0:
            imp_norm = imp / imp_sum
        else:
            imp_norm = imp

        all_importances.append(imp_norm)
        # Top 10 features
        top10 = np.argsort(imp_norm)[-10:][::-1]
        top10_str = ','.join(f"f{i}({imp_norm[i]:.3f})" for i in top10[:5])
        print(f"  {p['name']}: top5=[{top10_str}] n_nonzero={np.sum(imp > 0)}/{len(imp)}")
        per_patient[p['name']] = {
            'top10_indices': [int(i) for i in top10],
            'top10_importances': [round(float(imp_norm[i]), 4) for i in top10],
            'n_nonzero': int(np.sum(imp > 0)),
            'n_total': len(imp),
        }

    if len(all_importances) > 0:
        imp_matrix = np.array(all_importances)
        mean_imp = np.mean(imp_matrix, axis=0)
        std_imp = np.std(imp_matrix, axis=0)
        stability = mean_imp / (std_imp + 1e-8)

        # Top 10 stable features
        top_stable = np.argsort(stability)[-10:][::-1]
        # Top 10 by mean importance
        top_mean = np.argsort(mean_imp)[-10:][::-1]

        # Feature groups (approximate mapping)
        n_feat = len(mean_imp)
        groups = {}
        groups['glucose_window'] = list(range(min(24, n_feat)))
        groups['physics'] = list(range(24, min(120, n_feat)))
        groups['stats'] = list(range(120, min(130, n_feat)))
        groups['pk'] = list(range(130, min(150, n_feat)))
        groups['derivatives'] = list(range(150, min(160, n_feat)))
        groups['temporal'] = list(range(160, min(171, n_feat)))
        groups['interactions'] = list(range(171, min(181, n_feat)))

        group_importance = {}
        for gname, indices in groups.items():
            valid_idx = [i for i in indices if i < n_feat]
            if valid_idx:
                group_importance[gname] = round(float(np.sum(mean_imp[valid_idx])), 4)

        summary = {
            'top10_stable_indices': [int(i) for i in top_stable],
            'top10_mean_indices': [int(i) for i in top_mean],
            'group_importance': group_importance,
            'n_features': n_feat,
        }
    else:
        summary = {}

    return {
        'status': 'pass',
        'detail': f"n_features={summary.get('n_features', 0)} groups={summary.get('group_importance', {})}",
        'per_patient': per_patient,
        'results': summary,
    }


# ---------------------------------------------------------------------------
# EXP-1218: Prediction Error by Glucose Context
# ---------------------------------------------------------------------------

def exp_1218_error_by_context(patients, detail=False):
    """Break prediction errors by glucose context (rising, falling, stable, etc.)."""
    per_patient = {}

    for p in patients:
        res = _pipeline_single(p)
        if res is None:
            continue

        y_te = res['y_te'] * GLUCOSE_SCALE  # back to mg/dL
        pred_ar = res['pred_ar'] * GLUCOSE_SCALE
        pred_te = res['pred_te'] * GLUCOSE_SCALE
        X_te = res['X_te']

        # Glucose rate from features (first derivative feature)
        # g_win is first 24 features, rate is in derivative features
        g_last = X_te[:, WINDOW - 1] * GLUCOSE_SCALE  # last glucose in window
        g_prev = X_te[:, WINDOW - 2] * GLUCOSE_SCALE if WINDOW > 1 else g_last

        rate = (g_last - g_prev) / 5.0  # mg/dL per minute

        # Define contexts
        contexts = {
            'rising_fast': rate > 2.0,
            'rising': (rate > 0.5) & (rate <= 2.0),
            'stable': (rate >= -0.5) & (rate <= 0.5),
            'falling': (rate < -0.5) & (rate >= -2.0),
            'falling_fast': rate < -2.0,
        }

        # By glucose level
        level_contexts = {
            'hypo': g_last < 70,
            'normal': (g_last >= 70) & (g_last <= 180),
            'hyper': g_last > 180,
        }

        p_results = {}
        for ctx_name, mask in {**contexts, **level_contexts}.items():
            n = mask.sum()
            if n < 10:
                p_results[ctx_name] = {'n': int(n), 'rmse': None, 'rmse_ar': None}
                continue
            rmse = compute_rmse(y_te[mask], pred_te[mask])
            rmse_ar = compute_rmse(y_te[mask], pred_ar[mask])
            p_results[ctx_name] = {
                'n': int(n), 'rmse': round(rmse, 1), 'rmse_ar': round(rmse_ar, 1),
            }

        # Print summary for this patient
        worst = max((v['rmse_ar'] for v in p_results.values() if v['rmse_ar'] is not None), default=0)
        best = min((v['rmse_ar'] for v in p_results.values() if v['rmse_ar'] is not None), default=0)
        worst_ctx = [k for k, v in p_results.items() if v.get('rmse_ar') == worst]
        print(f"  {p['name']}: worst={worst_ctx[0] if worst_ctx else '?'}({worst:.0f}mg) "
              f"best_ctx(RMSE_AR)={best:.0f}mg overall_AR={compute_rmse(y_te, pred_ar):.0f}mg")
        per_patient[p['name']] = p_results

    # Aggregate across patients
    names = list(per_patient.keys())
    all_contexts = set()
    for n in names:
        all_contexts.update(per_patient[n].keys())

    summary = {}
    for ctx in sorted(all_contexts):
        rmses = [per_patient[n][ctx]['rmse_ar']
                 for n in names if ctx in per_patient[n] and per_patient[n][ctx]['rmse_ar'] is not None]
        if rmses:
            summary[ctx] = round(np.mean(rmses), 1)

    return {
        'status': 'pass',
        'detail': f"RMSE by context: {summary}",
        'per_patient': per_patient,
        'results': summary,
    }


# ---------------------------------------------------------------------------
# EXP-1219: Multi-Patient Pooled Model
# ---------------------------------------------------------------------------

def exp_1219_pooled_model(patients, detail=False):
    """Compare per-patient vs pooled vs transfer learning models."""
    per_patient = {}

    # First collect all features
    all_data = {}
    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        X, y, g_cur = build_enhanced_features(p, glucose, physics)
        if len(X) < 50:
            continue
        X_tr, X_va, X_te, y_tr, y_va, y_te = split_3way(X, y)
        all_data[p['name']] = {
            'X_tr': X_tr, 'X_va': X_va, 'X_te': X_te,
            'y_tr': y_tr, 'y_va': y_va, 'y_te': y_te,
        }

    if not all_data:
        return {'status': 'fail', 'detail': 'No data', 'per_patient': {}, 'results': {}}

    # Strategy 1: Per-patient (baseline)
    for pname, d in all_data.items():
        m = make_xgb_sota()
        m.fit(d['X_tr'], d['y_tr'], eval_set=[(d['X_va'], d['y_va'])], verbose=False)
        pred = m.predict(d['X_te'])
        all_data[pname]['r2_individual'] = compute_r2(d['y_te'], pred)

    # Strategy 2: Global pooled model
    X_pool_tr = np.concatenate([d['X_tr'] for d in all_data.values()])
    y_pool_tr = np.concatenate([d['y_tr'] for d in all_data.values()])
    X_pool_va = np.concatenate([d['X_va'] for d in all_data.values()])
    y_pool_va = np.concatenate([d['y_va'] for d in all_data.values()])

    m_global = make_xgb_sota(n_estimators=800)
    m_global.fit(X_pool_tr, y_pool_tr,
                 eval_set=[(X_pool_va, y_pool_va)], verbose=False)

    for pname, d in all_data.items():
        pred = m_global.predict(d['X_te'])
        all_data[pname]['r2_global'] = compute_r2(d['y_te'], pred)

    # Strategy 3: Global + patient ID feature
    names_list = list(all_data.keys())
    name_to_id = {n: i for i, n in enumerate(names_list)}

    def add_pid(X, pid):
        pid_col = np.full((len(X), 1), pid / len(names_list))
        return np.hstack([X, pid_col])

    X_pid_tr = np.concatenate([add_pid(d['X_tr'], name_to_id[n])
                                for n, d in all_data.items()])
    y_pid_tr = np.concatenate([d['y_tr'] for d in all_data.values()])
    X_pid_va = np.concatenate([add_pid(d['X_va'], name_to_id[n])
                                for n, d in all_data.items()])
    y_pid_va = np.concatenate([d['y_va'] for d in all_data.values()])

    m_pid = make_xgb_sota(n_estimators=800)
    m_pid.fit(X_pid_tr, y_pid_tr,
              eval_set=[(X_pid_va, y_pid_va)], verbose=False)

    for pname, d in all_data.items():
        X_te_pid = add_pid(d['X_te'], name_to_id[pname])
        pred = m_pid.predict(X_te_pid)
        all_data[pname]['r2_pid'] = compute_r2(d['y_te'], pred)

    # Strategy 4: Transfer learning (global pretrained + fine-tuned)
    for pname, d in all_data.items():
        m_ft = make_xgb_sota(n_estimators=200)
        # Use global model predictions as feature
        global_pred_tr = m_global.predict(d['X_tr'])
        global_pred_va = m_global.predict(d['X_va'])
        global_pred_te = m_global.predict(d['X_te'])

        X_tr_aug = np.hstack([d['X_tr'], global_pred_tr.reshape(-1, 1)])
        X_va_aug = np.hstack([d['X_va'], global_pred_va.reshape(-1, 1)])
        X_te_aug = np.hstack([d['X_te'], global_pred_te.reshape(-1, 1)])

        m_ft.fit(X_tr_aug, d['y_tr'],
                 eval_set=[(X_va_aug, d['y_va'])], verbose=False)
        pred = m_ft.predict(X_te_aug)
        all_data[pname]['r2_transfer'] = compute_r2(d['y_te'], pred)

    # Report
    for pname in names_list:
        d = all_data[pname]
        print(f"  {pname}: indiv={d['r2_individual']:.4f} global={d['r2_global']:.4f}"
              f" +pid={d['r2_pid']:.4f} transfer={d['r2_transfer']:.4f}")
        per_patient[pname] = {
            'individual': round(d['r2_individual'], 4),
            'global': round(d['r2_global'], 4),
            'global_pid': round(d['r2_pid'], 4),
            'transfer': round(d['r2_transfer'], 4),
        }

    means = {
        'individual': np.mean([per_patient[n]['individual'] for n in names_list]),
        'global': np.mean([per_patient[n]['global'] for n in names_list]),
        'global_pid': np.mean([per_patient[n]['global_pid'] for n in names_list]),
        'transfer': np.mean([per_patient[n]['transfer'] for n in names_list]),
    }
    best_key = max(means, key=means.get)
    wins = sum(1 for n in names_list
               if per_patient[n]['transfer'] > per_patient[n]['individual'])

    return {
        'status': 'pass',
        'detail': ' '.join(f"{k}={v:.4f}" for k, v in means.items())
                  + f" best={best_key} transfer_wins={wins}/{len(names_list)}",
        'per_patient': per_patient,
        'results': {k: round(v, 4) for k, v in means.items()},
    }


# ---------------------------------------------------------------------------
# EXP-1220: Production Pipeline Robustness
# ---------------------------------------------------------------------------

def exp_1220_robustness(patients, detail=False):
    """Stress-test production pipeline: gaps, noise, bias."""
    per_patient = {}

    for p in patients:
        glucose_orig = p['df']['glucose'].values.astype(float).copy()
        physics_orig = prepare_patient_raw(p)[1]

        # Baseline
        res = _pipeline_single(p)
        if res is None:
            continue
        r2_base = res['r2_ar']

        tests = {}

        # Test 1: Artificial gaps (30, 60, 120 min)
        import pandas as pd
        for gap_min in [30, 60, 120]:
            gap_steps = gap_min // 5
            glucose_gap = glucose_orig.copy()
            # Create gaps every 6 hours
            for start in range(0, len(glucose_gap), 72):  # every 6h
                end = min(start + gap_steps, len(glucose_gap))
                glucose_gap[start:end] = np.nan

            p_gap = dict(p)
            df_gap = p['df'].copy()
            df_gap['glucose'] = glucose_gap
            p_gap['df'] = df_gap
            try:
                res_gap = _pipeline_single(p_gap)
                r2_gap = res_gap['r2_ar'] if res_gap else 0.0
            except Exception:
                r2_gap = 0.0
            tests[f'gap_{gap_min}min'] = round(r2_gap, 4)

        # Test 2: Noise injection (σ = 5, 10, 20 mg/dL)
        for sigma in [5, 10, 20]:
            np.random.seed(42)
            noise = np.random.normal(0, sigma, len(glucose_orig))
            glucose_noisy = glucose_orig + noise

            p_noisy = dict(p)
            df_noisy = p['df'].copy()
            df_noisy['glucose'] = glucose_noisy
            p_noisy['df'] = df_noisy
            try:
                res_noisy = _pipeline_single(p_noisy)
                r2_noisy = res_noisy['r2_ar'] if res_noisy else 0.0
            except Exception:
                r2_noisy = 0.0
            tests[f'noise_σ{sigma}'] = round(r2_noisy, 4)

        # Test 3: Systematic bias (±10, ±20 mg/dL)
        for bias in [10, -10, 20, -20]:
            glucose_biased = glucose_orig + bias

            p_biased = dict(p)
            df_biased = p['df'].copy()
            df_biased['glucose'] = glucose_biased
            p_biased['df'] = df_biased
            try:
                res_biased = _pipeline_single(p_biased)
                r2_biased = res_biased['r2_ar'] if res_biased else 0.0
            except Exception:
                r2_biased = 0.0
            tests[f'bias_{bias:+d}mg'] = round(r2_biased, 4)

        # Worst degradation
        worst = min(tests.values())
        worst_test = [k for k, v in tests.items() if v == worst][0]
        print(f"  {p['name']}: base={r2_base:.4f} worst={worst_test}({worst:.4f})"
              f" gap30={tests.get('gap_30min', 0):.4f}"
              f" noise10={tests.get('noise_σ10', 0):.4f}"
              f" bias+20={tests.get('bias_+20mg', 0):.4f}")
        per_patient[p['name']] = {'baseline': round(r2_base, 4), **tests}

    names = list(per_patient.keys())
    means = {}
    all_keys = set()
    for n in names:
        all_keys.update(per_patient[n].keys())
    for key in sorted(all_keys):
        vals = [per_patient[n].get(key, 0) for n in names]
        means[key] = round(np.mean(vals), 4)

    return {
        'status': 'pass',
        'detail': f"baseline={means.get('baseline', 0):.4f} "
                  f"gap30={means.get('gap_30min', 0):.4f} "
                  f"noise10={means.get('noise_σ10', 0):.4f} "
                  f"bias+20={means.get('bias_+20mg', 0):.4f}",
        'per_patient': per_patient,
        'results': means,
    }


# ---------------------------------------------------------------------------
# Registry and main
# ---------------------------------------------------------------------------

EXPERIMENTS = [
    ('EXP-1211', 'Horizon Ensemble 5-Fold CV',
     exp_1211_horizon_ensemble_cv),
    ('EXP-1212', 'Asymmetric Loss for Spike Prediction',
     exp_1212_asymmetric_loss),
    ('EXP-1213', 'Adaptive Rolling AR Coefficients',
     exp_1213_adaptive_ar),
    ('EXP-1214', 'Patient h Data Imputation',
     exp_1214_imputation),
    ('EXP-1215', 'Conformal PI at Multiple Horizons',
     exp_1215_conformal_multi_horizon),
    ('EXP-1216', 'Ensemble with Fewer Models',
     exp_1216_ensemble_size),
    ('EXP-1217', 'Feature Importance Stability',
     exp_1217_feature_importance),
    ('EXP-1218', 'Prediction Error by Glucose Context',
     exp_1218_error_by_context),
    ('EXP-1219', 'Multi-Patient Pooled Model',
     exp_1219_pooled_model),
    ('EXP-1220', 'Production Pipeline Robustness',
     exp_1220_robustness),
]


def main():
    parser = argparse.ArgumentParser(
        description='EXP-1211-1220: Horizon Ensemble CV + Asymmetric Loss + Diagnostics')
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--max-patients', type=int, default=11)
    parser.add_argument('--experiments', type=str, default='all',
                        help='Comma-separated exp numbers or "all"')
    parser.add_argument('--experiment', type=str,
                        help='Run only this experiment (e.g. EXP-1211)')
    args = parser.parse_args()

    patients = load_patients(PATIENTS_DIR, max_patients=args.max_patients)
    print(f"Loaded {len(patients)} patients")

    if args.experiment:
        to_run = {args.experiment}
    elif args.experiments == 'all':
        to_run = None
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
