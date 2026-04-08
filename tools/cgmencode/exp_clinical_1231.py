#!/usr/bin/env python3
"""EXP-1231 through EXP-1240: Full Pipeline Validation & Residual Analysis.

Uses the proven 186-feature builder from exp_clinical_1211 for proper comparison.
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
# EXP-1231: Full Pipeline 5-Fold CV (186 features + 2-model ensemble + AR)
# ============================================================
def exp_1231_full_pipeline_cv(patients, detail=False):
    """Full 186-feature pipeline with 2-model ensemble + AR, 5-fold CV."""
    results = {'experiment': 'EXP-1231', 'name': 'Full Pipeline 5-Fold CV'}
    all_single, all_ens, all_ens_ar = [], [], []

    for p in patients:
        name = p['name']
        glucose, physics = prepare_patient_raw(p)

        tscv = TimeSeriesSplit(n_splits=5)
        X_ref, y_ref, _ = build_enhanced_features(p, glucose, physics, horizon=HORIZON)
        if len(X_ref) < 200:
            continue

        fold_single, fold_ens, fold_ens_ar = [], [], []
        for fold, (tr_idx, te_idx) in enumerate(tscv.split(X_ref)):
            # Single 60-min model
            vt = int(len(tr_idx) * 0.8)
            m = make_xgb_sota()
            m.fit(X_ref[tr_idx[:vt]], y_ref[tr_idx[:vt]],
                  eval_set=[(X_ref[tr_idx[vt:]], y_ref[tr_idx[vt:]])], verbose=False)
            s_pred = m.predict(X_ref[te_idx])
            fold_single.append(compute_r2(y_ref[te_idx], s_pred))

            # 2-model ensemble (30+90 min)
            horizons = [6, 18]
            sub_val, sub_test = [], []
            y_vals = []
            for h in horizons:
                X_h, y_h, _ = build_enhanced_features(p, glucose, physics, horizon=h)
                min_n = min(len(X_h), len(X_ref))
                X_h, y_h = X_h[:min_n], y_h[:min_n]
                valid_tr = tr_idx[tr_idx < min_n]
                valid_te = te_idx[te_idx < min_n]
                if len(valid_tr) < 100 or len(valid_te) < 50:
                    break
                vt2 = int(len(valid_tr) * 0.8)
                m2 = make_xgb_sota()
                m2.fit(X_h[valid_tr[:vt2]], y_h[valid_tr[:vt2]],
                       eval_set=[(X_h[valid_tr[vt2:]], y_h[valid_tr[vt2:]])], verbose=False)
                sub_val.append(m2.predict(X_h[valid_tr[vt2:]]))
                sub_test.append(m2.predict(X_h[valid_te]))
                if not y_vals:
                    y_vals = (y_h[valid_tr[vt2:]], y_h[valid_te])

            if len(sub_val) < 2:
                fold_ens.append(fold_single[-1])
                fold_ens_ar.append(fold_single[-1])
                continue

            min_v = min(len(s) for s in sub_val)
            min_t = min(len(s) for s in sub_test)
            Sv = np.column_stack([s[:min_v] for s in sub_val])
            St = np.column_stack([s[:min_t] for s in sub_test])
            yv = y_ref[tr_idx[int(len(tr_idx)*0.8):]][:min_v]
            yt = y_ref[te_idx[:min_t]]

            meta = Ridge(alpha=1.0)
            meta.fit(Sv, yv)
            e_val = meta.predict(Sv)
            e_test = meta.predict(St)
            fold_ens.append(compute_r2(yt, e_test))

            # AR correction
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
    wins = sum(1 for s, e in zip(all_single, all_ens_ar) if e > s)
    results['status'] = 'pass'
    results['detail'] = f"single={ms:.4f} ens={me:.4f} ens+AR={mea:.4f} Δ={mea-ms:+.4f} wins={wins}/{len(all_single)}"
    results['single_r2'] = ms
    results['ens_r2'] = me
    results['ens_ar_r2'] = mea
    return results


# ============================================================
# EXP-1232: Residual Spectral Analysis
# ============================================================
def exp_1232_residual_analysis(patients, detail=False):
    """Analyze residual patterns: temporal, amplitude, autocorrelation."""
    results = {'experiment': 'EXP-1232', 'name': 'Residual Spectral Analysis'}
    all_stats = []

    for p in patients:
        name = p['name']
        glucose, physics = prepare_patient_raw(p)
        X, y, g_cur = build_enhanced_features(p, glucose, physics)
        if len(X) < 200:
            continue

        X_tr, X_va, X_te, y_tr, y_va, y_te = split_3way(X, y)
        m = make_xgb_sota()
        m.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
        pred = m.predict(X_te)
        ar_c = fit_ar(m.predict(X_va), y_va)
        pred_ar = apply_ar(pred, y_te, ar_c)

        resid = (y_te - pred_ar) * GLUCOSE_SCALE
        # Autocorrelation at lags 1-12
        acf = []
        for lag in range(1, 13):
            if len(resid) > lag:
                c = np.corrcoef(resid[:-lag], resid[lag:])[0, 1]
                acf.append(c)
            else:
                acf.append(0.0)

        # Skewness and kurtosis
        skew = float(np.mean(((resid - np.mean(resid)) / np.std(resid))**3)) if np.std(resid) > 0 else 0
        kurt = float(np.mean(((resid - np.mean(resid)) / np.std(resid))**4)) if np.std(resid) > 0 else 0

        # Error by glucose level
        g_test = g_cur[len(g_cur)-len(y_te):][:len(resid)] * GLUCOSE_SCALE if len(g_cur) >= len(y_te) else None
        level_rmse = {}
        if g_test is not None and len(g_test) == len(resid):
            for label, lo, hi in [('hypo', 0, 70), ('low', 70, 100), ('normal', 100, 180), ('high', 180, 250), ('hyper', 250, 500)]:
                mask = (g_test >= lo) & (g_test < hi)
                if mask.sum() > 10:
                    level_rmse[label] = float(np.sqrt(np.mean(resid[mask]**2)))

        stats = {
            'acf1': acf[0], 'acf6': acf[5], 'acf12': acf[11],
            'skew': skew, 'kurtosis': kurt,
            'mean_resid': float(np.mean(resid)),
            'std_resid': float(np.std(resid)),
            'level_rmse': level_rmse
        }
        all_stats.append(stats)
        if detail:
            print(f"  {name}: ACF(1)={acf[0]:.3f} ACF(6)={acf[5]:.3f} skew={skew:.3f} kurt={kurt:.2f} mean={np.mean(resid):.1f}mg std={np.std(resid):.1f}mg")

    mean_acf1 = np.mean([s['acf1'] for s in all_stats])
    mean_skew = np.mean([s['skew'] for s in all_stats])
    results['status'] = 'pass'
    results['detail'] = f"ACF(1)={mean_acf1:.3f} skew={mean_skew:.3f} n={len(all_stats)}"
    results['stats'] = all_stats
    return results


# ============================================================
# EXP-1233: Dawn Phenomenon Conditioning
# ============================================================
def exp_1233_dawn_conditioning(patients, detail=False):
    """Test adding dawn phenomenon conditioning features."""
    results = {'experiment': 'EXP-1233', 'name': 'Dawn Phenomenon Conditioning'}
    all_base, all_dawn = [], []

    for p in patients:
        name = p['name']
        glucose, physics = prepare_patient_raw(p)
        X, y, _ = build_enhanced_features(p, glucose, physics)
        if len(X) < 200:
            continue

        X_tr, X_va, X_te, y_tr, y_va, y_te = split_3way(X, y)

        # Base
        m = make_xgb_sota()
        m.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
        pred = m.predict(X_te)
        ar_c = fit_ar(m.predict(X_va), y_va)
        base_pred = apply_ar(pred, y_te, ar_c)
        base_r2 = compute_r2(y_te, base_pred)

        # Dawn conditioning: compute patient-specific dawn effect
        # Group train residuals by hour, compute mean shift
        pred_tr = m.predict(X_tr)
        resid_tr = (y_tr - pred_tr) * GLUCOSE_SCALE
        n_tr = len(X_tr)

        hour_residuals = {}
        for i in range(n_tr):
            h = (i * STRIDE * 5 // 60) % 24
            if h not in hour_residuals:
                hour_residuals[h] = []
            hour_residuals[h].append(resid_tr[i])

        # Create dawn correction curve
        dawn_correction = np.zeros(24)
        for h in range(24):
            if h in hour_residuals and len(hour_residuals[h]) > 10:
                dawn_correction[h] = np.mean(hour_residuals[h]) / GLUCOSE_SCALE

        # Apply dawn correction to test predictions
        dawn_pred = base_pred.copy()
        for i in range(len(dawn_pred)):
            h = ((len(X_tr) + len(X_va) + i) * STRIDE * 5 // 60) % 24
            dawn_pred[i] += dawn_correction[h]

        dawn_r2 = compute_r2(y_te, dawn_pred)

        all_base.append(base_r2)
        all_dawn.append(dawn_r2)
        if detail:
            # Show dawn effect magnitude
            dawn_mag = max(dawn_correction) - min(dawn_correction)
            print(f"  {name}: base={base_r2:.4f} dawn={dawn_r2:.4f} Δ={dawn_r2-base_r2:+.4f} dawn_range={dawn_mag*GLUCOSE_SCALE:.1f}mg")

    mb = np.mean(all_base)
    md = np.mean(all_dawn)
    wins = sum(1 for b, d in zip(all_base, all_dawn) if d > b)
    results['status'] = 'pass'
    results['detail'] = f"base={mb:.4f} dawn={md:.4f} Δ={md-mb:+.4f} wins={wins}/{len(all_base)}"
    return results


# ============================================================
# EXP-1234: Conformal PI with Full Pipeline
# ============================================================
def exp_1234_full_conformal(patients, detail=False):
    """Conformal PIs using full 186-feature ensemble+AR pipeline."""
    results = {'experiment': 'EXP-1234', 'name': 'Full Pipeline Conformal PIs'}
    all_metrics = []

    for p in patients:
        name = p['name']
        glucose, physics = prepare_patient_raw(p)
        X, y, _ = build_enhanced_features(p, glucose, physics)
        if len(X) < 200:
            continue

        X_tr, X_va, X_te, y_tr, y_va, y_te = split_3way(X, y)
        m = make_xgb_sota()
        m.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
        pred_va = m.predict(X_va)
        pred_te = m.predict(X_te)

        # AR
        ar_c = fit_ar(pred_va, y_va)
        pred_va_ar = apply_ar(pred_va, y_va, ar_c)
        pred_te_ar = apply_ar(pred_te, y_te, ar_c)

        r2 = compute_r2(y_te, pred_te_ar)
        rmse = compute_rmse(y_te, pred_te_ar) * GLUCOSE_SCALE

        # Conformal calibration on validation residuals
        val_resid = np.abs(y_va - pred_va_ar) * GLUCOSE_SCALE
        for alpha, label in [(0.80, '80%'), (0.90, '90%'), (0.95, '95%')]:
            q = np.percentile(val_resid, alpha * 100)
            test_resid = np.abs(y_te - pred_te_ar) * GLUCOSE_SCALE
            cov = np.mean(test_resid <= q)
            width = 2 * q
            if label == '80%':
                metrics = {'name': name, 'r2': r2, 'rmse': rmse,
                          'cov80': cov, 'w80': width}
            elif label == '90%':
                metrics['cov90'] = cov
                metrics['w90'] = width
            else:
                metrics['cov95'] = cov
                metrics['w95'] = width

        all_metrics.append(metrics)
        if detail:
            print(f"  {name}: R²={r2:.4f} RMSE={rmse:.1f}mg | 80%: cov={metrics['cov80']:.1%} w={metrics['w80']:.0f}mg | 90%: cov={metrics['cov90']:.1%} w={metrics['w90']:.0f}mg | 95%: cov={metrics['cov95']:.1%} w={metrics['w95']:.0f}mg")

    mr = np.mean([m['r2'] for m in all_metrics])
    mc80 = np.mean([m['cov80'] for m in all_metrics])
    mw80 = np.mean([m['w80'] for m in all_metrics])
    mc90 = np.mean([m['cov90'] for m in all_metrics])
    mc95 = np.mean([m['cov95'] for m in all_metrics])
    results['status'] = 'pass'
    results['detail'] = f"R²={mr:.4f} | 80%: cov={mc80:.1%} w={mw80:.0f}mg | 90%: cov={mc90:.1%} | 95%: cov={mc95:.1%}"
    results['metrics'] = all_metrics
    return results


# ============================================================
# EXP-1235: Error by Prediction Confidence
# ============================================================
def exp_1235_confidence_stratification(patients, detail=False):
    """Stratify predictions by model confidence (tree variance)."""
    results = {'experiment': 'EXP-1235', 'name': 'Error by Prediction Confidence'}
    all_strat = []

    for p in patients:
        name = p['name']
        glucose, physics = prepare_patient_raw(p)
        X, y, _ = build_enhanced_features(p, glucose, physics)
        if len(X) < 200:
            continue

        X_tr, X_va, X_te, y_tr, y_va, y_te = split_3way(X, y)
        m = make_xgb_sota()
        m.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)

        # Get individual tree predictions for variance estimate
        pred_te = m.predict(X_te)
        ar_c = fit_ar(m.predict(X_va), y_va)
        pred_ar = apply_ar(pred_te, y_te, ar_c)

        # Use absolute residual on validation as proxy for uncertainty
        pred_va = m.predict(X_va)
        pred_va_ar = apply_ar(pred_va, y_va, ar_c)
        val_abs_resid = np.abs(y_va - pred_va_ar) * GLUCOSE_SCALE

        # For each test point, find similar validation points by feature similarity
        # Simplified: use prediction magnitude as proxy for confidence
        test_abs_pred = np.abs(pred_ar - np.mean(pred_ar))
        test_resid = np.abs(y_te - pred_ar) * GLUCOSE_SCALE

        # Quartile analysis
        quartiles = np.percentile(test_abs_pred, [25, 50, 75])
        strat = {}
        for label, lo, hi in [('Q1_near_mean', -np.inf, quartiles[0]),
                               ('Q2', quartiles[0], quartiles[1]),
                               ('Q3', quartiles[1], quartiles[2]),
                               ('Q4_far_mean', quartiles[2], np.inf)]:
            mask = (test_abs_pred >= lo) & (test_abs_pred < hi)
            if mask.sum() > 10:
                strat[label] = float(np.sqrt(np.mean(test_resid[mask]**2)))

        all_strat.append(strat)
        if detail:
            parts = [f"{k}={v:.1f}mg" for k, v in strat.items()]
            print(f"  {name}: " + " | ".join(parts))

    results['status'] = 'pass'
    mean_strat = {}
    for key in ['Q1_near_mean', 'Q2', 'Q3', 'Q4_far_mean']:
        vals = [s.get(key, 0) for s in all_strat if key in s]
        if vals:
            mean_strat[key] = np.mean(vals)
    results['detail'] = " | ".join(f"{k}={v:.1f}mg" for k, v in mean_strat.items())
    return results


# ============================================================
# EXP-1236: 3-Model Ensemble vs 2-Model with Full Features
# ============================================================
def exp_1236_ensemble_sizing(patients, detail=False):
    """Compare 2-model (30+90), 3-model (30+60+90), 5-model with full feature builder."""
    results = {'experiment': 'EXP-1236', 'name': 'Ensemble Sizing (Full Features)'}
    configs = {
        '2m': [6, 18],    # 30+90 min
        '3m': [6, 12, 18],   # 30+60+90 min
        '5m': [6, 9, 12, 18, 24],   # 30-120 min
    }
    all_r2 = {k: [] for k in configs}
    all_r2['single'] = []

    for p in patients:
        name = p['name']
        glucose, physics = prepare_patient_raw(p)

        # Single model
        X, y, _ = build_enhanced_features(p, glucose, physics)
        if len(X) < 200:
            continue
        X_tr, X_va, X_te, y_tr, y_va, y_te = split_3way(X, y)
        m = make_xgb_sota()
        m.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
        pred = m.predict(X_te)
        ar_c = fit_ar(m.predict(X_va), y_va)
        single_r2 = compute_r2(y_te, apply_ar(pred, y_te, ar_c))
        all_r2['single'].append(single_r2)

        for cfg_name, horizons in configs.items():
            sub_val, sub_test = [], []
            for h in horizons:
                X_h, y_h, _ = build_enhanced_features(p, glucose, physics, horizon=h)
                min_n = min(len(X_h), len(X))
                X_h, y_h = X_h[:min_n], y_h[:min_n]
                tr_e = int(min_n * 0.6)
                va_e = int(min_n * 0.8)
                if tr_e < 50:
                    break
                mh = make_xgb_sota()
                mh.fit(X_h[:tr_e], y_h[:tr_e],
                       eval_set=[(X_h[tr_e:va_e], y_h[tr_e:va_e])], verbose=False)
                sub_val.append(mh.predict(X_h[tr_e:va_e]))
                sub_test.append(mh.predict(X_h[va_e:min_n]))

            if len(sub_val) < 2:
                all_r2[cfg_name].append(single_r2)
                continue

            min_v = min(len(s) for s in sub_val)
            min_t = min(len(s) for s in sub_test)
            Sv = np.column_stack([s[:min_v] for s in sub_val])
            St = np.column_stack([s[:min_t] for s in sub_test])
            yv = y[int(len(y)*0.6):int(len(y)*0.8)][:min_v]
            yt = y[int(len(y)*0.8):][:min_t]

            meta = Ridge(alpha=1.0)
            meta.fit(Sv, yv)
            ev = meta.predict(Sv)
            et = meta.predict(St)
            ar_e = fit_ar(ev, yv)
            r2 = compute_r2(yt, apply_ar(et, yt, ar_e))
            all_r2[cfg_name].append(r2)

        if detail:
            parts = [f"{k}={all_r2[k][-1]:.4f}" for k in ['single', '2m', '3m', '5m']]
            print(f"  {name}: " + " ".join(parts))

    means = {k: np.mean(v) for k, v in all_r2.items()}
    best = max(means, key=means.get)
    results['status'] = 'pass'
    results['detail'] = " ".join(f"{k}={v:.4f}" for k, v in means.items()) + f" best={best}"
    results['means'] = means
    return results


# ============================================================
# EXP-1237: Per-Patient AR Coefficient Analysis
# ============================================================
def exp_1237_ar_coefficient_analysis(patients, detail=False):
    """Analyze AR(2) coefficients across patients and folds."""
    results = {'experiment': 'EXP-1237', 'name': 'AR Coefficient Analysis'}
    all_coefs = []

    for p in patients:
        name = p['name']
        glucose, physics = prepare_patient_raw(p)
        X, y, _ = build_enhanced_features(p, glucose, physics)
        if len(X) < 200:
            continue

        tscv = TimeSeriesSplit(n_splits=5)
        fold_coefs = []
        for fold, (tr_idx, te_idx) in enumerate(tscv.split(X)):
            vt = int(len(tr_idx) * 0.8)
            m = make_xgb_sota()
            m.fit(X[tr_idx[:vt]], y[tr_idx[:vt]],
                  eval_set=[(X[tr_idx[vt:]], y[tr_idx[vt:]])], verbose=False)
            pred_va = m.predict(X[tr_idx[vt:]])
            coefs = fit_ar(pred_va, y[tr_idx[vt:]])
            fold_coefs.append(coefs)

        coefs_arr = np.array(fold_coefs)
        mean_c = np.mean(coefs_arr, axis=0)
        std_c = np.std(coefs_arr, axis=0)
        all_coefs.append({
            'name': name,
            'alpha_mean': mean_c[0], 'alpha_std': std_c[0],
            'beta_mean': mean_c[1], 'beta_std': std_c[1],
        })
        if detail:
            print(f"  {name}: α={mean_c[0]:.3f}±{std_c[0]:.3f} β={mean_c[1]:.3f}±{std_c[1]:.3f}")

    mean_alpha = np.mean([c['alpha_mean'] for c in all_coefs])
    mean_beta = np.mean([c['beta_mean'] for c in all_coefs])
    results['status'] = 'pass'
    results['detail'] = f"α={mean_alpha:.3f} β={mean_beta:.3f} n={len(all_coefs)}"
    results['coefs'] = all_coefs
    return results


# ============================================================
# EXP-1238: Online Learning Impact with Full Features
# ============================================================
def exp_1238_online_learning(patients, detail=False):
    """Test weekly online model updates with full 186-feature pipeline."""
    results = {'experiment': 'EXP-1238', 'name': 'Online Learning (Full Features)'}
    all_base, all_online = [], []

    for p in patients:
        name = p['name']
        glucose, physics = prepare_patient_raw(p)
        X, y, _ = build_enhanced_features(p, glucose, physics)
        if len(X) < 200:
            continue

        X_tr, X_va, X_te, y_tr, y_va, y_te = split_3way(X, y)

        # Base: static model + AR
        m = make_xgb_sota()
        m.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
        pred_te = m.predict(X_te)
        ar_c = fit_ar(m.predict(X_va), y_va)
        base_pred = apply_ar(pred_te, y_te, ar_c)
        base_r2 = compute_r2(y_te, base_pred)

        # Online: retrain weekly
        week = 2016 // STRIDE
        online_pred = np.zeros_like(y_te)
        X_accum = X_tr.copy()
        y_accum = y_tr.copy()

        for start in range(0, len(X_te), week):
            end = min(start + week, len(X_te))

            # Retrain on accumulated data
            m_online = make_xgb_sota()
            va_split = int(len(X_accum) * 0.9)
            m_online.fit(X_accum[:va_split], y_accum[:va_split],
                        eval_set=[(X_accum[va_split:], y_accum[va_split:])], verbose=False)

            # Predict this week
            chunk_pred = m_online.predict(X_te[start:end])
            online_pred[start:end] = chunk_pred

            # Add this week's data to accumulator
            X_accum = np.vstack([X_accum, X_te[start:end]])
            y_accum = np.concatenate([y_accum, y_te[start:end]])

        # AR on online predictions
        ar_online = fit_ar(m.predict(X_va), y_va)
        online_ar = apply_ar(online_pred, y_te, ar_online)
        online_r2 = compute_r2(y_te, online_ar)

        all_base.append(base_r2)
        all_online.append(online_r2)
        if detail:
            print(f"  {name}: base={base_r2:.4f} online={online_r2:.4f} Δ={online_r2-base_r2:+.4f}")

    mb = np.mean(all_base)
    mo = np.mean(all_online)
    wins = sum(1 for b, o in zip(all_base, all_online) if o > b)
    results['status'] = 'pass'
    results['detail'] = f"base={mb:.4f} online={mo:.4f} Δ={mo-mb:+.4f} wins={wins}/{len(all_base)}"
    return results


# ============================================================
# EXP-1239: Prediction Calibration Analysis
# ============================================================
def exp_1239_calibration_analysis(patients, detail=False):
    """Analyze prediction calibration: predicted vs actual glucose levels."""
    results = {'experiment': 'EXP-1239', 'name': 'Prediction Calibration'}
    all_cal = []

    for p in patients:
        name = p['name']
        glucose, physics = prepare_patient_raw(p)
        X, y, _ = build_enhanced_features(p, glucose, physics)
        if len(X) < 200:
            continue

        X_tr, X_va, X_te, y_tr, y_va, y_te = split_3way(X, y)
        m = make_xgb_sota()
        m.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
        pred = m.predict(X_te)
        ar_c = fit_ar(m.predict(X_va), y_va)
        pred_ar = apply_ar(pred, y_te, ar_c)

        # Binned calibration
        pred_mg = pred_ar * GLUCOSE_SCALE
        actual_mg = y_te * GLUCOSE_SCALE
        bins = [(40, 70, 'hypo'), (70, 100, 'low'), (100, 140, 'target'),
                (140, 180, 'elevated'), (180, 250, 'high'), (250, 400, 'very_high')]

        cal = {}
        for lo, hi, label in bins:
            mask = (pred_mg >= lo) & (pred_mg < hi)
            if mask.sum() > 20:
                actual_in_bin = actual_mg[mask]
                cal[label] = {
                    'n': int(mask.sum()),
                    'pred_mean': float(np.mean(pred_mg[mask])),
                    'actual_mean': float(np.mean(actual_in_bin)),
                    'bias': float(np.mean(actual_in_bin) - np.mean(pred_mg[mask])),
                    'rmse': float(np.sqrt(np.mean((actual_in_bin - pred_mg[mask])**2)))
                }

        all_cal.append({'name': name, 'bins': cal})
        if detail:
            parts = [f"{k}: bias={v['bias']:+.1f}mg rmse={v['rmse']:.1f}mg" for k, v in cal.items()]
            print(f"  {name}: " + " | ".join(parts))

    results['status'] = 'pass'
    # Aggregate bias across patients
    all_bias = {}
    for label in ['hypo', 'low', 'target', 'elevated', 'high', 'very_high']:
        biases = [c['bins'][label]['bias'] for c in all_cal if label in c['bins']]
        if biases:
            all_bias[label] = np.mean(biases)
    results['detail'] = " | ".join(f"{k}={v:+.1f}mg" for k, v in all_bias.items())
    results['calibration'] = all_cal
    return results


# ============================================================
# EXP-1240: Clinical Metric Evaluation
# ============================================================
def exp_1240_clinical_metrics(patients, detail=False):
    """Evaluate predictions using clinical diabetes metrics."""
    results = {'experiment': 'EXP-1240', 'name': 'Clinical Metric Evaluation'}
    all_metrics = []

    for p in patients:
        name = p['name']
        glucose, physics = prepare_patient_raw(p)
        X, y, _ = build_enhanced_features(p, glucose, physics)
        if len(X) < 200:
            continue

        X_tr, X_va, X_te, y_tr, y_va, y_te = split_3way(X, y)
        m = make_xgb_sota()
        m.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
        pred = m.predict(X_te)
        ar_c = fit_ar(m.predict(X_va), y_va)
        pred_ar = apply_ar(pred, y_te, ar_c)

        actual_mg = y_te * GLUCOSE_SCALE
        pred_mg = pred_ar * GLUCOSE_SCALE

        r2 = compute_r2(y_te, pred_ar)
        rmse = compute_rmse(y_te, pred_ar) * GLUCOSE_SCALE
        mae = float(np.mean(np.abs(actual_mg - pred_mg)))

        # Clarke Error Grid inspired metrics
        # Zone A: within 20% or both < 70
        in_zone_a = ((np.abs(pred_mg - actual_mg) <= 0.2 * actual_mg) |
                     ((actual_mg < 70) & (pred_mg < 70)))
        zone_a_pct = float(np.mean(in_zone_a))

        # Clinically significant errors: predict safe when actually hypo
        false_safe = (pred_mg >= 80) & (actual_mg < 54)  # Severe hypo missed
        false_safe_rate = float(np.mean(false_safe)) if len(false_safe) > 0 else 0

        # Time in range preservation
        actual_tir = float(np.mean((actual_mg >= 70) & (actual_mg <= 180)))
        pred_tir = float(np.mean((pred_mg >= 70) & (pred_mg <= 180)))
        tir_error = abs(actual_tir - pred_tir)

        # MARD (Mean Absolute Relative Difference)
        valid = actual_mg > 40
        mard = float(np.mean(np.abs(pred_mg[valid] - actual_mg[valid]) / actual_mg[valid])) * 100

        metrics = {
            'name': name, 'r2': r2, 'rmse': rmse, 'mae': mae,
            'zone_a': zone_a_pct, 'false_safe': false_safe_rate,
            'actual_tir': actual_tir, 'pred_tir': pred_tir,
            'tir_error': tir_error, 'mard': mard,
        }
        all_metrics.append(metrics)
        if detail:
            print(f"  {name}: R²={r2:.4f} RMSE={rmse:.1f}mg MARD={mard:.1f}% ZoneA={zone_a_pct:.1%} FalseSafe={false_safe_rate:.2%} TIR_err={tir_error:.3f}")

    mr = np.mean([m['r2'] for m in all_metrics])
    mm = np.mean([m['mard'] for m in all_metrics])
    mz = np.mean([m['zone_a'] for m in all_metrics])
    mfs = np.mean([m['false_safe'] for m in all_metrics])
    results['status'] = 'pass'
    results['detail'] = f"R²={mr:.4f} MARD={mm:.1f}% ZoneA={mz:.1%} FalseSafe={mfs:.3%}"
    results['metrics'] = all_metrics
    return results


# ============================================================
EXPERIMENTS = {
    'EXP-1231': ('Full Pipeline 5-Fold CV', exp_1231_full_pipeline_cv),
    'EXP-1232': ('Residual Spectral Analysis', exp_1232_residual_analysis),
    'EXP-1233': ('Dawn Phenomenon Conditioning', exp_1233_dawn_conditioning),
    'EXP-1234': ('Full Pipeline Conformal PIs', exp_1234_full_conformal),
    'EXP-1235': ('Error by Prediction Confidence', exp_1235_confidence_stratification),
    'EXP-1236': ('Ensemble Sizing (Full Features)', exp_1236_ensemble_sizing),
    'EXP-1237': ('AR Coefficient Analysis', exp_1237_ar_coefficient_analysis),
    'EXP-1238': ('Online Learning (Full Features)', exp_1238_online_learning),
    'EXP-1239': ('Prediction Calibration', exp_1239_calibration_analysis),
    'EXP-1240': ('Clinical Metric Evaluation', exp_1240_clinical_metrics),
}


def main():
    parser = argparse.ArgumentParser(description='EXP-1231–1240')
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--max-patients', type=int, default=11)
    parser.add_argument('--experiment', type=str, default=None)
    args = parser.parse_args()

    patients = load_patients(PATIENTS_DIR, max_patients=args.max_patients)
    print(f"Loaded {len(patients)} patients\n")

    to_run = {args.experiment: EXPERIMENTS[args.experiment]} if args.experiment and args.experiment in EXPERIMENTS else EXPERIMENTS

    for exp_id, (exp_name, func) in to_run.items():
        print(f"\n{'='*60}")
        print(f"Running {exp_id}: {exp_name}")
        print(f"{'='*60}")

        t0 = time.time()
        try:
            result = func(patients, detail=args.detail)
            elapsed = time.time() - t0
            result['time_seconds'] = elapsed
            print(f"  Status: {result.get('status', 'unknown')}")
            print(f"  Detail: {result.get('detail', 'N/A')}")
            print(f"  Time: {elapsed:.1f}s")
            if args.save:
                save_results(result, exp_id)
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
