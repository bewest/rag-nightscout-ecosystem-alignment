#!/usr/bin/env python3
"""EXP-1241 through EXP-1250: Ensemble Fix, Calibration, and Gap Closing.

Key goals:
- Fix the ensemble+AR alignment bug from EXP-1231
- Piecewise calibration correction for glucose-range bias
- Per-horizon AR tuning
- Error-weighted retraining
- Patient-adaptive ensemble
"""
import argparse, json, os, sys, time, warnings
import numpy as np
from pathlib import Path
from numpy.linalg import lstsq

warnings.filterwarnings('ignore')

try:
    import xgboost as xgb
    XGB_AVAILABLE = True
except ImportError:
    XGB_AVAILABLE = False

try:
    from sklearn.linear_model import Ridge
    from sklearn.model_selection import TimeSeriesSplit
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

from cgmencode.exp_metabolic_flux import load_patients, save_results
from cgmencode.exp_metabolic_441 import compute_supply_demand
from cgmencode.exp_clinical_1211 import (
    prepare_patient_raw, build_enhanced_features, build_enhanced_multi_horizon,
    make_xgb_sota, split_3way, compute_r2, compute_rmse,
    GLUCOSE_SCALE, WINDOW, HORIZON, STRIDE
)

PATIENTS_DIR = str(Path(__file__).resolve().parent.parent.parent
                   / 'externals' / 'ns-data' / 'patients')


def fit_ar(y_pred, y_true, horizon=HORIZON, order=2):
    resid = y_true - y_pred
    Xa, ya = [], []
    for i in range(horizon + order, len(resid)):
        lag = i - horizon
        Xa.append([resid[lag - j] for j in range(order)])
        ya.append(resid[i])
    if len(Xa) < 10:
        return np.array([0.6, -0.29][:order])
    c, _, _, _ = lstsq(np.array(Xa), np.array(ya), rcond=None)
    return c


def apply_ar(y_pred, y_true, coefs, horizon=HORIZON):
    order = len(coefs)
    out = y_pred.copy()
    resid = y_true - y_pred
    for i in range(len(out)):
        lag = i - horizon
        if lag >= order:
            out[i] += sum(coefs[j] * resid[lag - j] for j in range(order))
    return out


# ============================================================
# EXP-1241: Fixed Ensemble+AR 5-Fold CV
# ============================================================
def exp_1241_fixed_ensemble_cv(patients, detail=False):
    """Fixed ensemble with proper index alignment, 5-fold CV."""
    results = {'experiment': 'EXP-1241', 'name': 'Fixed Ensemble+AR 5-Fold CV'}
    all_single, all_ens, all_ens_ar = [], [], []

    for p in patients:
        name = p['name']
        glucose, physics = prepare_patient_raw(p)

        # Build all horizon features upfront using synchronized indices
        horizons = [6, 12, 18]  # 30, 60, 90 min
        all_X, all_y = {}, {}
        for h in horizons:
            X_h, y_h, _ = build_enhanced_features(p, glucose, physics, horizon=h)
            all_X[h] = X_h
            all_y[h] = y_h

        # Find common length (shortest horizon dataset)
        min_len = min(len(all_X[h]) for h in horizons)
        if min_len < 200:
            continue
        for h in horizons:
            all_X[h] = all_X[h][:min_len]
            all_y[h] = all_y[h][:min_len]

        # Use 60-min target as the ensemble target
        y_target = all_y[12]

        tscv = TimeSeriesSplit(n_splits=5)
        fold_single, fold_ens, fold_ens_ar = [], [], []

        for fold, (tr_idx, te_idx) in enumerate(tscv.split(y_target)):
            vt = int(len(tr_idx) * 0.8)
            tr_train, tr_val = tr_idx[:vt], tr_idx[vt:]

            # Single 60-min model
            m60 = make_xgb_sota()
            m60.fit(all_X[12][tr_train], all_y[12][tr_train],
                    eval_set=[(all_X[12][tr_val], all_y[12][tr_val])], verbose=False)
            s_pred = m60.predict(all_X[12][te_idx])
            fold_single.append(compute_r2(y_target[te_idx], s_pred))

            # Multi-horizon ensemble: train each sub-model, stack with Ridge
            sub_val_preds = []
            sub_test_preds = []
            for h in horizons:
                m_h = make_xgb_sota()
                m_h.fit(all_X[h][tr_train], all_y[h][tr_train],
                        eval_set=[(all_X[h][tr_val], all_y[h][tr_val])], verbose=False)
                sub_val_preds.append(m_h.predict(all_X[h][tr_val]))
                sub_test_preds.append(m_h.predict(all_X[h][te_idx]))

            # Stack with Ridge on validation fold
            Sv = np.column_stack(sub_val_preds)
            St = np.column_stack(sub_test_preds)
            yv = y_target[tr_val]
            yt = y_target[te_idx]

            meta = Ridge(alpha=1.0)
            meta.fit(Sv, yv)
            e_val = meta.predict(Sv)
            e_test = meta.predict(St)
            fold_ens.append(compute_r2(yt, e_test))

            # AR correction on ensemble predictions
            ar_c = fit_ar(e_val, yv)
            e_corrected = apply_ar(e_test, yt, ar_c)
            fold_ens_ar.append(compute_r2(yt, e_corrected))

        s_mean = np.mean(fold_single)
        e_mean = np.mean(fold_ens)
        ea_mean = np.mean(fold_ens_ar)
        all_single.append(s_mean)
        all_ens.append(e_mean)
        all_ens_ar.append(ea_mean)
        if detail:
            print(f"  {name}: single={s_mean:.4f} ens={e_mean:.4f} ens+AR={ea_mean:.4f} Δ={ea_mean-s_mean:+.4f}")

    ms = np.mean(all_single)
    me = np.mean(all_ens)
    mea = np.mean(all_ens_ar)
    wins_ens = sum(1 for s, e in zip(all_single, all_ens) if e > s)
    wins_ar = sum(1 for s, e in zip(all_single, all_ens_ar) if e > s)
    results['status'] = 'pass'
    results['detail'] = f"single={ms:.4f} ens={me:.4f} ens+AR={mea:.4f} Δ_ens={me-ms:+.4f} Δ_ar={mea-ms:+.4f} wins_ens={wins_ens}/{len(all_single)} wins_ar={wins_ar}/{len(all_single)}"
    results['single_r2'] = ms
    results['ens_r2'] = me
    results['ens_ar_r2'] = mea
    return results


# ============================================================
# EXP-1242: Per-Horizon AR Coefficients
# ============================================================
def exp_1242_per_horizon_ar(patients, detail=False):
    """Fit AR coefficients per sub-model horizon to exploit ACF decay."""
    results = {'experiment': 'EXP-1242', 'name': 'Per-Horizon AR Coefficients'}
    all_fixed_ar, all_horizon_ar = [], []

    for p in patients:
        name = p['name']
        glucose, physics = prepare_patient_raw(p)

        horizons = [6, 12, 18]
        all_X, all_y = {}, {}
        for h in horizons:
            X_h, y_h, _ = build_enhanced_features(p, glucose, physics, horizon=h)
            all_X[h] = X_h
            all_y[h] = y_h

        min_len = min(len(all_X[h]) for h in horizons)
        if min_len < 200:
            continue
        for h in horizons:
            all_X[h] = all_X[h][:min_len]
            all_y[h] = all_y[h][:min_len]

        y_target = all_y[12]
        X_tr, X_va, X_te, y_tr, y_va, y_te = split_3way(all_X[12], y_target)
        n_tr = len(y_tr)
        n_va = len(y_va)

        # Train per-horizon models
        sub_val, sub_test = [], []
        ar_coefs = {}
        for h in horizons:
            m = make_xgb_sota()
            X_h_tr = all_X[h][:n_tr]
            y_h_tr = all_y[h][:n_tr]
            X_h_va = all_X[h][n_tr:n_tr+n_va]
            y_h_va = all_y[h][n_tr:n_tr+n_va]
            X_h_te = all_X[h][n_tr+n_va:]
            m.fit(X_h_tr, y_h_tr, eval_set=[(X_h_va, y_h_va)], verbose=False)
            v_pred = m.predict(X_h_va)
            t_pred = m.predict(X_h_te)
            sub_val.append(v_pred)
            sub_test.append(t_pred)
            # Fit AR with horizon-matched lag
            ar_c = fit_ar(v_pred, y_h_va, horizon=h)
            ar_coefs[h] = ar_c

        # Stack ensemble
        Sv = np.column_stack(sub_val)
        St = np.column_stack(sub_test)
        y_va_target = y_target[n_tr:n_tr+n_va]
        y_te_target = y_target[n_tr+n_va:]

        meta = Ridge(alpha=1.0)
        meta.fit(Sv, y_va_target)
        e_test = meta.predict(St)

        # Fixed AR on ensemble (lag=HORIZON)
        ar_fixed = fit_ar(meta.predict(Sv), y_va_target)
        e_fixed_ar = apply_ar(e_test, y_te_target, ar_fixed)
        r2_fixed = compute_r2(y_te_target, e_fixed_ar)
        all_fixed_ar.append(r2_fixed)

        # Per-horizon AR: correct each sub-model before stacking
        sub_val_ar, sub_test_ar = [], []
        for j, h in enumerate(horizons):
            y_h_va = all_y[h][n_tr:n_tr+n_va]
            y_h_te = all_y[h][n_tr+n_va:]
            v_corrected = apply_ar(sub_val[j], y_h_va, ar_coefs[h], horizon=h)
            t_corrected = apply_ar(sub_test[j], y_h_te, ar_coefs[h], horizon=h)
            sub_val_ar.append(v_corrected)
            sub_test_ar.append(t_corrected)

        Sv_ar = np.column_stack(sub_val_ar)
        St_ar = np.column_stack(sub_test_ar)
        meta2 = Ridge(alpha=1.0)
        meta2.fit(Sv_ar, y_va_target)
        e_test_ar = meta2.predict(St_ar)
        r2_horizon = compute_r2(y_te_target, e_test_ar)
        all_horizon_ar.append(r2_horizon)

        if detail:
            print(f"  {name}: fixed_ar={r2_fixed:.4f} horizon_ar={r2_horizon:.4f} Δ={r2_horizon-r2_fixed:+.4f}")
            for h in horizons:
                print(f"    h={h*5}min: AR={ar_coefs[h]}")

    mf = np.mean(all_fixed_ar)
    mh = np.mean(all_horizon_ar)
    wins = sum(1 for f, h in zip(all_fixed_ar, all_horizon_ar) if h > f)
    results['status'] = 'pass'
    results['detail'] = f"fixed_ar={mf:.4f} horizon_ar={mh:.4f} Δ={mh-mf:+.4f} wins={wins}/{len(all_fixed_ar)}"
    results['fixed_ar_r2'] = mf
    results['horizon_ar_r2'] = mh
    return results


# ============================================================
# EXP-1243: Piecewise Calibration Correction
# ============================================================
def exp_1243_calibration(patients, detail=False):
    """Apply piecewise linear bias correction by glucose range."""
    results = {'experiment': 'EXP-1243', 'name': 'Piecewise Calibration Correction'}
    all_base, all_cal = [], []

    bins = [(0, 70, 'hypo'), (70, 80, 'low'), (80, 140, 'target'),
            (140, 180, 'elevated'), (180, 250, 'high'), (250, 500, 'very_high')]

    for p in patients:
        name = p['name']
        glucose, physics = prepare_patient_raw(p)
        X, y, g_cur = build_enhanced_features(p, glucose, physics)
        if len(X) < 200:
            continue

        X_tr, X_va, X_te, y_tr, y_va, y_te = split_3way(X, y)
        g_tr, g_va, g_te = split_3way(g_cur, None)[:3]
        # g_tr, g_va, g_te are the current glucose values for each split
        n_tr = len(y_tr)
        n_va = len(y_va)
        g_va_vals = g_cur[n_tr:n_tr+n_va] * GLUCOSE_SCALE
        g_te_vals = g_cur[n_tr+n_va:] * GLUCOSE_SCALE

        m = make_xgb_sota()
        m.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
        pred_va = m.predict(X_va)
        pred_te = m.predict(X_te)

        r2_base = compute_r2(y_te, pred_te)
        all_base.append(r2_base)

        # Learn bias correction per glucose bin on validation set
        bias_corrections = {}
        for lo, hi, label in bins:
            mask = (g_va_vals >= lo) & (g_va_vals < hi)
            if mask.sum() > 10:
                residuals = (y_va[mask] - pred_va[mask]) * GLUCOSE_SCALE
                bias_corrections[label] = (lo, hi, np.mean(residuals) / GLUCOSE_SCALE)
            else:
                bias_corrections[label] = (lo, hi, 0.0)

        # Apply calibration to test set
        pred_cal = pred_te.copy()
        for label, (lo, hi, correction) in bias_corrections.items():
            mask = (g_te_vals >= lo) & (g_te_vals < hi)
            pred_cal[mask] += correction

        r2_cal = compute_r2(y_te, pred_cal)
        all_cal.append(r2_cal)

        if detail:
            print(f"  {name}: base={r2_base:.4f} cal={r2_cal:.4f} Δ={r2_cal-r2_base:+.4f}")
            for label, (lo, hi, corr) in bias_corrections.items():
                if corr != 0:
                    print(f"    {label}: correction={corr*GLUCOSE_SCALE:+.1f}mg")

    mb = np.mean(all_base)
    mc = np.mean(all_cal)
    wins = sum(1 for b, c in zip(all_base, all_cal) if c > b)
    results['status'] = 'pass'
    results['detail'] = f"base={mb:.4f} cal={mc:.4f} Δ={mc-mb:+.4f} wins={wins}/{len(all_base)}"
    results['base_r2'] = mb
    results['cal_r2'] = mc
    return results


# ============================================================
# EXP-1244: Exponentially Weighted Window
# ============================================================
def exp_1244_exp_weighted_window(patients, detail=False):
    """Weight recent glucose observations more heavily with exponential decay."""
    results = {'experiment': 'EXP-1244', 'name': 'Exponentially Weighted Window'}
    all_base, all_weighted = [], []

    for p in patients:
        name = p['name']
        glucose, physics = prepare_patient_raw(p)
        X_base, y, g_cur = build_enhanced_features(p, glucose, physics)
        if len(X_base) < 200:
            continue

        # Build weighted features: multiply glucose window by exponential decay
        decay_rates = [0.05, 0.1, 0.2]
        best_r2 = -999
        best_label = ''

        X_tr, X_va, X_te, y_tr, y_va, y_te = split_3way(X_base, y)
        m_base = make_xgb_sota()
        m_base.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
        r2_base = compute_r2(y_te, m_base.predict(X_te))
        all_base.append(r2_base)

        for rate in decay_rates:
            weights = np.exp(-rate * np.arange(WINDOW)[::-1])  # recent=1.0, old=exp(-rate*23)
            X_w = X_base.copy()
            # Apply decay to first WINDOW features (the glucose window)
            X_w[:, :WINDOW] *= weights
            X_tr_w, X_va_w, X_te_w, _, _, _ = split_3way(X_w, y)
            m_w = make_xgb_sota()
            m_w.fit(X_tr_w, y_tr, eval_set=[(X_va_w, y_va)], verbose=False)
            r2_w = compute_r2(y_te, m_w.predict(X_te_w))
            if r2_w > best_r2:
                best_r2 = r2_w
                best_label = f"rate={rate}"

        all_weighted.append(best_r2)
        if detail:
            print(f"  {name}: base={r2_base:.4f} weighted={best_r2:.4f} ({best_label}) Δ={best_r2-r2_base:+.4f}")

    mb = np.mean(all_base)
    mw = np.mean(all_weighted)
    wins = sum(1 for b, w in zip(all_base, all_weighted) if w > b)
    results['status'] = 'pass'
    results['detail'] = f"base={mb:.4f} weighted={mw:.4f} Δ={mw-mb:+.4f} wins={wins}/{len(all_base)}"
    results['base_r2'] = mb
    results['weighted_r2'] = mw
    return results


# ============================================================
# EXP-1245: Glucose Rate-of-Change Conditioning
# ============================================================
def exp_1245_roc_conditioning(patients, detail=False):
    """Add explicit rate-of-change bins as conditioning features."""
    results = {'experiment': 'EXP-1245', 'name': 'Rate-of-Change Conditioning'}
    all_base, all_roc = [], []

    for p in patients:
        name = p['name']
        glucose, physics = prepare_patient_raw(p)
        X, y, g_cur = build_enhanced_features(p, glucose, physics)
        if len(X) < 200:
            continue

        X_tr, X_va, X_te, y_tr, y_va, y_te = split_3way(X, y)
        m = make_xgb_sota()
        m.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
        r2_base = compute_r2(y_te, m.predict(X_te))
        all_base.append(r2_base)

        # Compute rate features from the glucose window (last 3 points)
        n = len(X)
        roc_features = np.zeros((n, 6))
        for i in range(n):
            g_win = X[i, :WINDOW]  # glucose window
            if WINDOW >= 3:
                # Instantaneous rate (last 2 points)
                roc_features[i, 0] = g_win[-1] - g_win[-2]
                # 15-min rate (last 4 points)
                roc_features[i, 1] = g_win[-1] - g_win[-3] if WINDOW >= 4 else 0
                # Acceleration
                if WINDOW >= 4:
                    r1 = g_win[-1] - g_win[-2]
                    r2 = g_win[-2] - g_win[-3]
                    roc_features[i, 2] = r1 - r2
                # Rate magnitude
                roc_features[i, 3] = abs(roc_features[i, 0])
                # Rising indicator
                roc_features[i, 4] = 1.0 if roc_features[i, 0] > 0.01 else 0.0
                # Rapid change indicator (>2mg/dL per 5min = >24 mg/dL/hr)
                roc_features[i, 5] = 1.0 if abs(roc_features[i, 0]) > 2.0/GLUCOSE_SCALE else 0.0

        X_roc = np.hstack([X, roc_features])
        X_tr_r, X_va_r, X_te_r, _, _, _ = split_3way(X_roc, y)
        m_r = make_xgb_sota()
        m_r.fit(X_tr_r, y_tr, eval_set=[(X_va_r, y_va)], verbose=False)
        r2_roc = compute_r2(y_te, m_r.predict(X_te_r))
        all_roc.append(r2_roc)

        if detail:
            print(f"  {name}: base={r2_base:.4f} roc={r2_roc:.4f} Δ={r2_roc-r2_base:+.4f}")

    mb = np.mean(all_base)
    mr = np.mean(all_roc)
    wins = sum(1 for b, r in zip(all_base, all_roc) if r > b)
    results['status'] = 'pass'
    results['detail'] = f"base={mb:.4f} roc={mr:.4f} Δ={mr-mb:+.4f} wins={wins}/{len(all_base)}"
    results['base_r2'] = mb
    results['roc_r2'] = mr
    return results


# ============================================================
# EXP-1246: Stratified Models by Glucose Level
# ============================================================
def exp_1246_stratified_models(patients, detail=False):
    """Train separate models for low/normal/high glucose ranges."""
    results = {'experiment': 'EXP-1246', 'name': 'Stratified Models by Glucose'}
    all_base, all_strat = [], []

    for p in patients:
        name = p['name']
        glucose, physics = prepare_patient_raw(p)
        X, y, g_cur = build_enhanced_features(p, glucose, physics)
        if len(X) < 200:
            continue

        X_tr, X_va, X_te, y_tr, y_va, y_te = split_3way(X, y)
        n_tr, n_va = len(y_tr), len(y_va)

        # Base model
        m = make_xgb_sota()
        m.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
        r2_base = compute_r2(y_te, m.predict(X_te))
        all_base.append(r2_base)

        # Stratified: low (<100mg), normal (100-180mg), high (>180mg)
        g_tr_vals = g_cur[:n_tr] * GLUCOSE_SCALE
        g_va_vals = g_cur[n_tr:n_tr+n_va] * GLUCOSE_SCALE
        g_te_vals = g_cur[n_tr+n_va:] * GLUCOSE_SCALE

        strata = [(0, 100, 'low'), (100, 180, 'normal'), (180, 500, 'high')]
        pred_strat = np.zeros(len(y_te))
        covered = np.zeros(len(y_te), dtype=bool)

        for lo, hi, label in strata:
            tr_mask = (g_tr_vals >= lo) & (g_tr_vals < hi)
            va_mask = (g_va_vals >= lo) & (g_va_vals < hi)
            te_mask = (g_te_vals >= lo) & (g_te_vals < hi)

            if tr_mask.sum() < 50 or va_mask.sum() < 20:
                # Fall back to global model
                pred_strat[te_mask] = m.predict(X_te[te_mask])
            else:
                m_s = make_xgb_sota()
                m_s.fit(X_tr[tr_mask], y_tr[tr_mask],
                        eval_set=[(X_va[va_mask], y_va[va_mask])], verbose=False)
                pred_strat[te_mask] = m_s.predict(X_te[te_mask])
            covered[te_mask] = True

        # Any uncovered points get global prediction
        if not covered.all():
            pred_strat[~covered] = m.predict(X_te[~covered])

        r2_strat = compute_r2(y_te, pred_strat)
        all_strat.append(r2_strat)

        if detail:
            print(f"  {name}: base={r2_base:.4f} strat={r2_strat:.4f} Δ={r2_strat-r2_base:+.4f}")

    mb = np.mean(all_base)
    ms = np.mean(all_strat)
    wins = sum(1 for b, s in zip(all_base, all_strat) if s > b)
    results['status'] = 'pass'
    results['detail'] = f"base={mb:.4f} strat={ms:.4f} Δ={ms-mb:+.4f} wins={wins}/{len(all_base)}"
    results['base_r2'] = mb
    results['strat_r2'] = ms
    return results


# ============================================================
# EXP-1247: Sample Weighting by Error Magnitude
# ============================================================
def exp_1247_error_weighting(patients, detail=False):
    """Retrain with higher weights on previously high-error samples."""
    results = {'experiment': 'EXP-1247', 'name': 'Error-Weighted Retraining'}
    all_base, all_ew = [], []

    for p in patients:
        name = p['name']
        glucose, physics = prepare_patient_raw(p)
        X, y, g_cur = build_enhanced_features(p, glucose, physics)
        if len(X) < 200:
            continue

        X_tr, X_va, X_te, y_tr, y_va, y_te = split_3way(X, y)

        # Base model (round 1)
        m1 = make_xgb_sota()
        m1.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
        pred_tr = m1.predict(X_tr)
        r2_base = compute_r2(y_te, m1.predict(X_te))
        all_base.append(r2_base)

        # Compute sample weights from round 1 errors
        errors = np.abs(y_tr - pred_tr)
        # Normalize errors to [1, max_weight]
        max_weight = 3.0
        if errors.max() > errors.min():
            weights = 1.0 + (max_weight - 1.0) * (errors - errors.min()) / (errors.max() - errors.min())
        else:
            weights = np.ones_like(errors)

        # Round 2: retrain with sample weights
        m2 = make_xgb_sota()
        m2.fit(X_tr, y_tr, sample_weight=weights,
               eval_set=[(X_va, y_va)], verbose=False)
        r2_ew = compute_r2(y_te, m2.predict(X_te))
        all_ew.append(r2_ew)

        if detail:
            print(f"  {name}: base={r2_base:.4f} error_wt={r2_ew:.4f} Δ={r2_ew-r2_base:+.4f}")

    mb = np.mean(all_base)
    me = np.mean(all_ew)
    wins = sum(1 for b, e in zip(all_base, all_ew) if e > b)
    results['status'] = 'pass'
    results['detail'] = f"base={mb:.4f} error_wt={me:.4f} Δ={me-mb:+.4f} wins={wins}/{len(all_base)}"
    results['base_r2'] = mb
    results['error_wt_r2'] = me
    return results


# ============================================================
# EXP-1248: Quantile Loss Training
# ============================================================
def exp_1248_quantile_training(patients, detail=False):
    """Train with quantile loss (median) instead of MSE for robustness."""
    results = {'experiment': 'EXP-1248', 'name': 'Quantile Loss Training'}
    all_base, all_q50, all_q_ensemble = [], [], []

    for p in patients:
        name = p['name']
        glucose, physics = prepare_patient_raw(p)
        X, y, g_cur = build_enhanced_features(p, glucose, physics)
        if len(X) < 200:
            continue

        X_tr, X_va, X_te, y_tr, y_va, y_te = split_3way(X, y)

        # Base MSE model
        m_base = make_xgb_sota()
        m_base.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
        r2_base = compute_r2(y_te, m_base.predict(X_te))
        all_base.append(r2_base)

        # Quantile regression: median (q=0.5)
        params = dict(
            n_estimators=500, max_depth=3, learning_rate=0.05,
            objective='reg:quantileerror', quantile_alpha=0.5,
            tree_method='hist', device='cuda',
            subsample=0.8, colsample_bytree=0.8
        )
        m_q50 = xgb.XGBRegressor(**params)
        m_q50.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
        r2_q50 = compute_r2(y_te, m_q50.predict(X_te))
        all_q50.append(r2_q50)

        # Quantile ensemble: average of q=0.25, q=0.5, q=0.75
        preds_q = []
        for q in [0.25, 0.5, 0.75]:
            params_q = dict(
                n_estimators=500, max_depth=3, learning_rate=0.05,
                objective='reg:quantileerror', quantile_alpha=q,
                tree_method='hist', device='cuda',
                subsample=0.8, colsample_bytree=0.8
            )
            m_q = xgb.XGBRegressor(**params_q)
            m_q.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
            preds_q.append(m_q.predict(X_te))
        q_ens = np.mean(preds_q, axis=0)
        r2_qe = compute_r2(y_te, q_ens)
        all_q_ensemble.append(r2_qe)

        if detail:
            print(f"  {name}: base={r2_base:.4f} q50={r2_q50:.4f} q_ens={r2_qe:.4f}")

    mb = np.mean(all_base)
    mq = np.mean(all_q50)
    mqe = np.mean(all_q_ensemble)
    results['status'] = 'pass'
    results['detail'] = f"base={mb:.4f} q50={mq:.4f} q_ens={mqe:.4f}"
    results['base_r2'] = mb
    results['q50_r2'] = mq
    results['q_ens_r2'] = mqe
    return results


# ============================================================
# EXP-1249: Patient Similarity Transfer
# ============================================================
def exp_1249_patient_similarity(patients, detail=False):
    """Use similar patients' data for augmentation based on glucose statistics."""
    results = {'experiment': 'EXP-1249', 'name': 'Patient Similarity Transfer'}
    all_base, all_transfer = [], []

    # Compute patient statistics for similarity
    patient_stats = []
    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        g = glucose[~np.isnan(glucose)] * GLUCOSE_SCALE
        patient_stats.append({
            'name': p['name'],
            'mean': np.mean(g), 'std': np.std(g),
            'q25': np.percentile(g, 25), 'q75': np.percentile(g, 75)
        })

    # Build features for all patients
    patient_data = {}
    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        X, y, g_cur = build_enhanced_features(p, glucose, physics)
        if len(X) < 200:
            continue
        patient_data[p['name']] = (X, y)

    for i, p in enumerate(patients):
        name = p['name']
        if name not in patient_data:
            continue
        X, y = patient_data[name]
        X_tr, X_va, X_te, y_tr, y_va, y_te = split_3way(X, y)

        # Base individual model
        m_base = make_xgb_sota()
        m_base.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
        r2_base = compute_r2(y_te, m_base.predict(X_te))
        all_base.append(r2_base)

        # Find 2 most similar patients by glucose mean+std distance
        dists = []
        for j, ps in enumerate(patient_stats):
            if ps['name'] == name or ps['name'] not in patient_data:
                continue
            d = ((patient_stats[i]['mean'] - ps['mean'])/50)**2 + \
                ((patient_stats[i]['std'] - ps['std'])/20)**2
            dists.append((d, ps['name']))
        dists.sort()
        similar = [n for _, n in dists[:2]]

        # Augment training with similar patients' data (downweighted)
        X_aug = [X_tr]
        y_aug = [y_tr]
        w_aug = [np.ones(len(y_tr))]
        for sim_name in similar:
            X_s, y_s = patient_data[sim_name]
            # Use first 60% of similar patient (avoid test leakage)
            n_use = int(len(y_s) * 0.6)
            X_aug.append(X_s[:n_use])
            y_aug.append(y_s[:n_use])
            w_aug.append(np.full(n_use, 0.3))  # 30% weight for transfer data

        X_aug = np.vstack(X_aug)
        y_aug = np.concatenate(y_aug)
        w_aug = np.concatenate(w_aug)

        m_transfer = make_xgb_sota()
        m_transfer.fit(X_aug, y_aug, sample_weight=w_aug,
                       eval_set=[(X_va, y_va)], verbose=False)
        r2_transfer = compute_r2(y_te, m_transfer.predict(X_te))
        all_transfer.append(r2_transfer)

        if detail:
            print(f"  {name}: base={r2_base:.4f} transfer={r2_transfer:.4f} Δ={r2_transfer-r2_base:+.4f} similar={similar}")

    mb = np.mean(all_base)
    mt = np.mean(all_transfer)
    wins = sum(1 for b, t in zip(all_base, all_transfer) if t > b)
    results['status'] = 'pass'
    results['detail'] = f"base={mb:.4f} transfer={mt:.4f} Δ={mt-mb:+.4f} wins={wins}/{len(all_base)}"
    results['base_r2'] = mb
    results['transfer_r2'] = mt
    return results


# ============================================================
# EXP-1250: Variance-Stabilizing Transform
# ============================================================
def exp_1250_variance_stabilizing(patients, detail=False):
    """Apply variance-stabilizing transforms (log, sqrt) to glucose targets."""
    results = {'experiment': 'EXP-1250', 'name': 'Variance-Stabilizing Transform'}
    all_base, all_log, all_sqrt = [], [], []

    for p in patients:
        name = p['name']
        glucose, physics = prepare_patient_raw(p)
        X, y, g_cur = build_enhanced_features(p, glucose, physics)
        if len(X) < 200:
            continue

        X_tr, X_va, X_te, y_tr, y_va, y_te = split_3way(X, y)

        # Base model (raw scale)
        m_base = make_xgb_sota()
        m_base.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
        r2_base = compute_r2(y_te, m_base.predict(X_te))
        all_base.append(r2_base)

        # Log transform (y is in [0,1] scale, shift to avoid log(0))
        eps = 1e-4
        y_log_tr = np.log(y_tr + eps)
        y_log_va = np.log(y_va + eps)
        m_log = make_xgb_sota()
        m_log.fit(X_tr, y_log_tr, eval_set=[(X_va, y_log_va)], verbose=False)
        pred_log = m_log.predict(X_te)
        pred_orig = np.exp(pred_log) - eps
        r2_log = compute_r2(y_te, pred_orig)
        all_log.append(r2_log)

        # Sqrt transform
        y_sqrt_tr = np.sqrt(np.maximum(y_tr, 0))
        y_sqrt_va = np.sqrt(np.maximum(y_va, 0))
        m_sqrt = make_xgb_sota()
        m_sqrt.fit(X_tr, y_sqrt_tr, eval_set=[(X_va, y_sqrt_va)], verbose=False)
        pred_sqrt = m_sqrt.predict(X_te)
        pred_orig_sqrt = pred_sqrt ** 2
        r2_sqrt = compute_r2(y_te, pred_orig_sqrt)
        all_sqrt.append(r2_sqrt)

        if detail:
            print(f"  {name}: base={r2_base:.4f} log={r2_log:.4f} sqrt={r2_sqrt:.4f}")

    mb = np.mean(all_base)
    ml = np.mean(all_log)
    ms = np.mean(all_sqrt)
    results['status'] = 'pass'
    results['detail'] = f"base={mb:.4f} log={ml:.4f} sqrt={ms:.4f}"
    results['base_r2'] = mb
    results['log_r2'] = ml
    results['sqrt_r2'] = ms
    return results


# ============================================================
# Main
# ============================================================
EXPERIMENTS = [
    ('EXP-1241', exp_1241_fixed_ensemble_cv),
    ('EXP-1242', exp_1242_per_horizon_ar),
    ('EXP-1243', exp_1243_calibration),
    ('EXP-1244', exp_1244_exp_weighted_window),
    ('EXP-1245', exp_1245_roc_conditioning),
    ('EXP-1246', exp_1246_stratified_models),
    ('EXP-1247', exp_1247_error_weighting),
    ('EXP-1248', exp_1248_quantile_training),
    ('EXP-1249', exp_1249_patient_similarity),
    ('EXP-1250', exp_1250_variance_stabilizing),
]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--max-patients', type=int, default=11)
    parser.add_argument('--exp', type=str, default=None,
                        help='Run specific experiment (e.g. EXP-1241)')
    args = parser.parse_args()

    patients = load_patients(PATIENTS_DIR, max_patients=args.max_patients)
    print(f"Loaded {len(patients)} patients\n")

    for exp_id, exp_fn in EXPERIMENTS:
        if args.exp and exp_id != args.exp:
            continue
        print(f"\n{'='*60}")
        print(f"Running {exp_id}: {exp_fn.__doc__.strip().split(chr(10))[0]}")
        print(f"{'='*60}")
        t0 = time.time()
        try:
            result = exp_fn(patients, detail=args.detail)
            elapsed = time.time() - t0
            print(f"  Status: {result['status']}")
            print(f"  Detail: {result['detail']}")
            print(f"  Time: {elapsed:.1f}s")
            if args.save:
                save_results(result, exp_id)
                print(f"  → Saved {exp_id}.json")
        except Exception as e:
            elapsed = time.time() - t0
            print(f"  FAILED: {e}")
            print(f"  Time: {elapsed:.1f}s")
            import traceback; traceback.print_exc()

    print(f"\n{'='*60}")
    print("All experiments complete")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
