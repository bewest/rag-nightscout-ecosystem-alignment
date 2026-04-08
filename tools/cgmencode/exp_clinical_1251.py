#!/usr/bin/env python3
"""EXP-1251 through EXP-1260: Stacking Winners & Production Pipeline.

Key goals:
- Stack transfer + quantile + multi-horizon ensemble (use proper builder)
- Fix calibration bug from EXP-1243
- Test deeper trees, longer horizons, patient-specific tuning
- Production pipeline benchmark with all improvements
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


def get_patient_stats(patients):
    """Compute glucose statistics for patient similarity."""
    stats = []
    for p in patients:
        glucose, _ = prepare_patient_raw(p)
        g = glucose[~np.isnan(glucose)] * GLUCOSE_SCALE
        stats.append({
            'name': p['name'], 'mean': np.mean(g), 'std': np.std(g),
        })
    return stats


def find_similar(target_idx, patient_stats, k=2):
    """Find k most similar patients by glucose distance."""
    target = patient_stats[target_idx]
    dists = []
    for j, ps in enumerate(patient_stats):
        if j == target_idx:
            continue
        d = ((target['mean'] - ps['mean'])/50)**2 + ((target['std'] - ps['std'])/20)**2
        dists.append((d, j))
    dists.sort()
    return [idx for _, idx in dists[:k]]


def make_quantile_model(q=0.5):
    """Create XGBoost quantile regressor."""
    return xgb.XGBRegressor(
        n_estimators=500, max_depth=3, learning_rate=0.05,
        objective='reg:quantileerror', quantile_alpha=q,
        tree_method='hist', device='cuda',
        subsample=0.8, colsample_bytree=0.8,
    )


# ============================================================
# EXP-1251: Multi-Horizon Ensemble with Proper Builder + 5-Fold CV
# ============================================================
def exp_1251_proper_multi_horizon(patients, detail=False):
    """Multi-horizon ensemble using build_enhanced_multi_horizon, 5-fold CV."""
    results = {'experiment': 'EXP-1251', 'name': 'Proper Multi-Horizon Ensemble CV'}
    all_single, all_ens, all_ens_ar = [], [], []
    horizons = (6, 12, 18)

    for p in patients:
        name = p['name']
        glucose, physics = prepare_patient_raw(p)
        X, y_dict, g_cur = build_enhanced_multi_horizon(p, glucose, physics, horizons=horizons)
        if len(X) < 200:
            continue
        y_target = y_dict[12]  # 60-min target

        tscv = TimeSeriesSplit(n_splits=5)
        fold_single, fold_ens, fold_ens_ar = [], [], []

        for fold, (tr_idx, te_idx) in enumerate(tscv.split(X)):
            vt = int(len(tr_idx) * 0.8)
            tr_train, tr_val = tr_idx[:vt], tr_idx[vt:]

            # Single 60-min model
            m60 = make_xgb_sota()
            m60.fit(X[tr_train], y_target[tr_train],
                    eval_set=[(X[tr_val], y_target[tr_val])], verbose=False)
            s_pred = m60.predict(X[te_idx])
            fold_single.append(compute_r2(y_target[te_idx], s_pred))

            # Multi-horizon ensemble: same X, different y per horizon
            sub_val, sub_test = [], []
            for h in horizons:
                m_h = make_xgb_sota()
                m_h.fit(X[tr_train], y_dict[h][tr_train],
                        eval_set=[(X[tr_val], y_dict[h][tr_val])], verbose=False)
                sub_val.append(m_h.predict(X[tr_val]))
                sub_test.append(m_h.predict(X[te_idx]))

            # Stack with Ridge targeting 60-min
            Sv = np.column_stack(sub_val)
            St = np.column_stack(sub_test)
            yv = y_target[tr_val]
            yt = y_target[te_idx]

            meta = Ridge(alpha=1.0)
            meta.fit(Sv, yv)
            e_test = meta.predict(St)
            fold_ens.append(compute_r2(yt, e_test))

            # AR correction
            e_val = meta.predict(Sv)
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
            print(f"  {name}: single={s_mean:.4f} ens={e_mean:.4f} ens+AR={ea_mean:.4f} Δ_ens={e_mean-s_mean:+.4f}")

    ms = np.mean(all_single)
    me = np.mean(all_ens)
    mea = np.mean(all_ens_ar)
    wins = sum(1 for s, e in zip(all_single, all_ens) if e > s)
    results['status'] = 'pass'
    results['detail'] = f"single={ms:.4f} ens={me:.4f} ens+AR={mea:.4f} Δ_ens={me-ms:+.4f} wins={wins}/{len(all_single)}"
    results['single_r2'] = ms
    results['ens_r2'] = me
    results['ens_ar_r2'] = mea
    return results


# ============================================================
# EXP-1252: Transfer + Quantile Stacking
# ============================================================
def exp_1252_transfer_quantile(patients, detail=False):
    """Combine patient transfer augmentation with quantile ensemble."""
    results = {'experiment': 'EXP-1252', 'name': 'Transfer + Quantile Stacking'}
    all_base, all_transfer, all_tq = [], [], []
    patient_stats = get_patient_stats(patients)

    # Pre-build features for all patients
    patient_data = {}
    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        X, y, g_cur = build_enhanced_features(p, glucose, physics)
        if len(X) >= 200:
            patient_data[p['name']] = (X, y)

    for i, p in enumerate(patients):
        name = p['name']
        if name not in patient_data:
            continue
        X, y = patient_data[name]
        X_tr, X_va, X_te, y_tr, y_va, y_te = split_3way(X, y)

        # Baseline MSE
        m_base = make_xgb_sota()
        m_base.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
        r2_base = compute_r2(y_te, m_base.predict(X_te))
        all_base.append(r2_base)

        # Transfer: augment with similar patients
        similar_idxs = find_similar(i, patient_stats, k=2)
        X_aug, y_aug, w_aug = [X_tr], [y_tr], [np.ones(len(y_tr))]
        for si in similar_idxs:
            sim_name = patients[si]['name']
            if sim_name in patient_data:
                Xs, ys = patient_data[sim_name]
                n_use = int(len(ys) * 0.6)
                X_aug.append(Xs[:n_use])
                y_aug.append(ys[:n_use])
                w_aug.append(np.full(n_use, 0.3))
        X_aug = np.vstack(X_aug)
        y_aug = np.concatenate(y_aug)
        w_aug = np.concatenate(w_aug)

        # Transfer-only model
        m_transfer = make_xgb_sota()
        m_transfer.fit(X_aug, y_aug, sample_weight=w_aug,
                       eval_set=[(X_va, y_va)], verbose=False)
        r2_transfer = compute_r2(y_te, m_transfer.predict(X_te))
        all_transfer.append(r2_transfer)

        # Transfer + Quantile ensemble
        preds_q = []
        for q in [0.25, 0.5, 0.75]:
            m_q = make_quantile_model(q)
            m_q.fit(X_aug, y_aug, sample_weight=w_aug,
                    eval_set=[(X_va, y_va)], verbose=False)
            preds_q.append(m_q.predict(X_te))
        q_ens = np.mean(preds_q, axis=0)
        r2_tq = compute_r2(y_te, q_ens)
        all_tq.append(r2_tq)

        if detail:
            print(f"  {name}: base={r2_base:.4f} transfer={r2_transfer:.4f} T+Q={r2_tq:.4f} Δ={r2_tq-r2_base:+.4f}")

    mb = np.mean(all_base)
    mt = np.mean(all_transfer)
    mtq = np.mean(all_tq)
    wins = sum(1 for b, t in zip(all_base, all_tq) if t > b)
    results['status'] = 'pass'
    results['detail'] = f"base={mb:.4f} transfer={mt:.4f} T+Q={mtq:.4f} Δ={mtq-mb:+.4f} wins={wins}/{len(all_base)}"
    results['base_r2'] = mb
    results['transfer_r2'] = mt
    results['tq_r2'] = mtq
    return results


# ============================================================
# EXP-1253: Fixed Piecewise Calibration
# ============================================================
def exp_1253_calibration_fixed(patients, detail=False):
    """Piecewise bias correction — fixed split_3way bug."""
    results = {'experiment': 'EXP-1253', 'name': 'Fixed Piecewise Calibration'}
    all_base, all_cal = [], []
    bins = [(0, 70, 'hypo'), (70, 80, 'low'), (80, 140, 'target'),
            (140, 180, 'elevated'), (180, 250, 'high'), (250, 500, 'very_high')]

    for p in patients:
        name = p['name']
        glucose, physics = prepare_patient_raw(p)
        X, y, g_cur = build_enhanced_features(p, glucose, physics)
        if len(X) < 200:
            continue

        n = len(X)
        s1 = int(n * 0.6)
        s2 = int(n * 0.8)
        X_tr, X_va, X_te = X[:s1], X[s1:s2], X[s2:]
        y_tr, y_va, y_te = y[:s1], y[s1:s2], y[s2:]
        g_va_vals = g_cur[s1:s2] * GLUCOSE_SCALE
        g_te_vals = g_cur[s2:] * GLUCOSE_SCALE

        m = make_xgb_sota()
        m.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
        pred_va = m.predict(X_va)
        pred_te = m.predict(X_te)

        r2_base = compute_r2(y_te, pred_te)
        all_base.append(r2_base)

        # Learn per-bin bias correction
        corrections = {}
        for lo, hi, label in bins:
            mask = (g_va_vals >= lo) & (g_va_vals < hi)
            if mask.sum() > 10:
                residuals = (y_va[mask] - pred_va[mask]) * GLUCOSE_SCALE
                corrections[label] = (lo, hi, np.mean(residuals) / GLUCOSE_SCALE)
            else:
                corrections[label] = (lo, hi, 0.0)

        # Apply
        pred_cal = pred_te.copy()
        for label, (lo, hi, corr) in corrections.items():
            mask = (g_te_vals >= lo) & (g_te_vals < hi)
            pred_cal[mask] += corr

        r2_cal = compute_r2(y_te, pred_cal)
        all_cal.append(r2_cal)

        if detail:
            print(f"  {name}: base={r2_base:.4f} cal={r2_cal:.4f} Δ={r2_cal-r2_base:+.4f}")
            for label, (lo, hi, corr) in corrections.items():
                if abs(corr) > 0.001:
                    print(f"    {label}: {corr*GLUCOSE_SCALE:+.1f}mg")

    mb = np.mean(all_base)
    mc = np.mean(all_cal)
    wins = sum(1 for b, c in zip(all_base, all_cal) if c > b)
    results['status'] = 'pass'
    results['detail'] = f"base={mb:.4f} cal={mc:.4f} Δ={mc-mb:+.4f} wins={wins}/{len(all_base)}"
    results['base_r2'] = mb
    results['cal_r2'] = mc
    return results


# ============================================================
# EXP-1254: Multi-Horizon + Transfer + Quantile (Full Stack)
# ============================================================
def exp_1254_full_stack(patients, detail=False):
    """Stack ALL winners: multi-horizon + transfer + quantile, 5-fold CV."""
    results = {'experiment': 'EXP-1254', 'name': 'Full Stack (MH+Transfer+Quantile)'}
    all_single, all_stack = [], []
    horizons = (6, 12, 18)
    patient_stats = get_patient_stats(patients)

    # Pre-build multi-horizon features
    patient_mh = {}
    for idx, p in enumerate(patients):
        glucose, physics = prepare_patient_raw(p)
        X, y_dict, g_cur = build_enhanced_multi_horizon(p, glucose, physics, horizons=horizons)
        if len(X) >= 200:
            patient_mh[idx] = (X, y_dict, g_cur)

    for idx, p in enumerate(patients):
        name = p['name']
        if idx not in patient_mh:
            continue
        X, y_dict, g_cur = patient_mh[idx]
        y_target = y_dict[12]

        # Find similar patients for augmentation
        similar_idxs = find_similar(idx, patient_stats, k=2)

        tscv = TimeSeriesSplit(n_splits=5)
        fold_single, fold_stack = [], []

        for fold, (tr_idx, te_idx) in enumerate(tscv.split(X)):
            vt = int(len(tr_idx) * 0.8)
            tr_train, tr_val = tr_idx[:vt], tr_idx[vt:]

            # Single baseline
            m60 = make_xgb_sota()
            m60.fit(X[tr_train], y_target[tr_train],
                    eval_set=[(X[tr_val], y_target[tr_val])], verbose=False)
            fold_single.append(compute_r2(y_target[te_idx], m60.predict(X[te_idx])))

            # Augmented training data from similar patients
            X_aug = [X[tr_train]]
            w_aug = [np.ones(len(tr_train))]
            y_aug_dict = {h: [y_dict[h][tr_train]] for h in horizons}
            for si in similar_idxs:
                if si in patient_mh:
                    Xs, yds, _ = patient_mh[si]
                    n_use = int(len(Xs) * 0.6)
                    X_aug.append(Xs[:n_use])
                    w_aug.append(np.full(n_use, 0.3))
                    for h in horizons:
                        y_aug_dict[h].append(yds[h][:n_use])
            X_aug_all = np.vstack(X_aug)
            w_aug_all = np.concatenate(w_aug)
            y_aug_all = {h: np.concatenate(y_aug_dict[h]) for h in horizons}

            # Multi-horizon quantile ensemble
            sub_val, sub_test = [], []
            for h in horizons:
                for q in [0.25, 0.5, 0.75]:
                    m_q = make_quantile_model(q)
                    m_q.fit(X_aug_all, y_aug_all[h], sample_weight=w_aug_all,
                            eval_set=[(X[tr_val], y_dict[h][tr_val])], verbose=False)
                    sub_val.append(m_q.predict(X[tr_val]))
                    sub_test.append(m_q.predict(X[te_idx]))

            # Also add MSE models for each horizon
            for h in horizons:
                m_h = make_xgb_sota()
                m_h.fit(X_aug_all, y_aug_all[h], sample_weight=w_aug_all,
                        eval_set=[(X[tr_val], y_dict[h][tr_val])], verbose=False)
                sub_val.append(m_h.predict(X[tr_val]))
                sub_test.append(m_h.predict(X[te_idx]))

            # Stack: 9 quantile + 3 MSE = 12 sub-models → Ridge
            Sv = np.column_stack(sub_val)
            St = np.column_stack(sub_test)
            yv = y_target[tr_val]
            yt = y_target[te_idx]

            meta = Ridge(alpha=1.0)
            meta.fit(Sv, yv)
            e_test = meta.predict(St)

            # AR correction
            e_val = meta.predict(Sv)
            ar_c = fit_ar(e_val, yv)
            e_corrected = apply_ar(e_test, yt, ar_c)
            fold_stack.append(compute_r2(yt, e_corrected))

        s_mean = np.mean(fold_single)
        st_mean = np.mean(fold_stack)
        all_single.append(s_mean)
        all_stack.append(st_mean)
        if detail:
            print(f"  {name}: single={s_mean:.4f} full_stack={st_mean:.4f} Δ={st_mean-s_mean:+.4f}")

    ms = np.mean(all_single)
    mst = np.mean(all_stack)
    wins = sum(1 for s, t in zip(all_single, all_stack) if t > s)
    results['status'] = 'pass'
    results['detail'] = f"single={ms:.4f} full_stack={mst:.4f} Δ={mst-ms:+.4f} wins={wins}/{len(all_single)}"
    results['single_r2'] = ms
    results['full_stack_r2'] = mst
    return results


# ============================================================
# EXP-1255: Tree Depth Ablation
# ============================================================
def exp_1255_depth_ablation(patients, detail=False):
    """Test tree depths 2, 3, 4, 5 for optimal complexity."""
    results = {'experiment': 'EXP-1255', 'name': 'Tree Depth Ablation'}
    depth_results = {d: [] for d in [2, 3, 4, 5]}

    for p in patients:
        name = p['name']
        glucose, physics = prepare_patient_raw(p)
        X, y, g_cur = build_enhanced_features(p, glucose, physics)
        if len(X) < 200:
            continue

        X_tr, X_va, X_te, y_tr, y_va, y_te = split_3way(X, y)
        per_patient = {}
        for depth in [2, 3, 4, 5]:
            m = xgb.XGBRegressor(
                n_estimators=500, max_depth=depth, learning_rate=0.05,
                tree_method='hist', device='cuda',
                subsample=0.8, colsample_bytree=0.8,
            )
            m.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
            r2 = compute_r2(y_te, m.predict(X_te))
            depth_results[depth].append(r2)
            per_patient[depth] = r2

        if detail:
            print(f"  {name}: " + " ".join(f"d{d}={per_patient[d]:.4f}" for d in [2,3,4,5]))

    means = {d: np.mean(depth_results[d]) for d in [2,3,4,5]}
    best_d = max(means, key=means.get)
    results['status'] = 'pass'
    results['detail'] = " ".join(f"d{d}={means[d]:.4f}" for d in [2,3,4,5]) + f" best=d{best_d}"
    results['depth_r2'] = means
    return results


# ============================================================
# EXP-1256: Longer Horizons (2h, 3h)
# ============================================================
def exp_1256_longer_horizons(patients, detail=False):
    """Test 2h and 3h prediction horizons."""
    results = {'experiment': 'EXP-1256', 'name': 'Longer Prediction Horizons'}
    horizon_results = {}

    for h_min, h_steps in [(30, 6), (60, 12), (90, 18), (120, 24), (180, 36)]:
        h_r2s = []
        for p in patients:
            name = p['name']
            glucose, physics = prepare_patient_raw(p)
            X, y, g_cur = build_enhanced_features(p, glucose, physics, horizon=h_steps)
            if len(X) < 200:
                continue
            X_tr, X_va, X_te, y_tr, y_va, y_te = split_3way(X, y)
            m = make_xgb_sota()
            m.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
            r2 = compute_r2(y_te, m.predict(X_te))
            h_r2s.append(r2)
        horizon_results[h_min] = np.mean(h_r2s) if h_r2s else 0
        if detail:
            print(f"  h={h_min}min: R²={horizon_results[h_min]:.4f} (n={len(h_r2s)})")

    results['status'] = 'pass'
    results['detail'] = " ".join(f"{h}min={r:.4f}" for h, r in horizon_results.items())
    results['horizon_r2'] = horizon_results
    return results


# ============================================================
# EXP-1257: Transfer + Quantile + Multi-Horizon (Simple Stack)
# ============================================================
def exp_1257_simple_stack(patients, detail=False):
    """Simpler version of full stack: transfer+quantile on multi-horizon builder."""
    results = {'experiment': 'EXP-1257', 'name': 'Simple Transfer+Quantile Stack'}
    all_base, all_stack = [], []
    horizons = (6, 12, 18)
    patient_stats = get_patient_stats(patients)

    # Pre-build
    patient_mh = {}
    for idx, p in enumerate(patients):
        glucose, physics = prepare_patient_raw(p)
        X, y_dict, g_cur = build_enhanced_multi_horizon(p, glucose, physics, horizons=horizons)
        if len(X) >= 200:
            patient_mh[idx] = (X, y_dict)

    for idx, p in enumerate(patients):
        name = p['name']
        if idx not in patient_mh:
            continue
        X, y_dict = patient_mh[idx]
        y_target = y_dict[12]

        n = len(X)
        s1, s2 = int(n * 0.6), int(n * 0.8)
        X_tr, X_va, X_te = X[:s1], X[s1:s2], X[s2:]
        y_tr, y_va, y_te = y_target[:s1], y_target[s1:s2], y_target[s2:]

        # Baseline
        m_base = make_xgb_sota()
        m_base.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
        r2_base = compute_r2(y_te, m_base.predict(X_te))
        all_base.append(r2_base)

        # Transfer augmentation
        similar_idxs = find_similar(idx, patient_stats, k=2)
        X_aug = [X_tr]
        w_aug = [np.ones(len(X_tr))]
        y_aug = {h: [y_dict[h][:s1]] for h in horizons}
        for si in similar_idxs:
            if si in patient_mh:
                Xs, yds = patient_mh[si]
                n_use = int(len(Xs) * 0.6)
                X_aug.append(Xs[:n_use])
                w_aug.append(np.full(n_use, 0.3))
                for h in horizons:
                    y_aug[h].append(yds[h][:n_use])
        X_aug_all = np.vstack(X_aug)
        w_aug_all = np.concatenate(w_aug)
        y_aug_all = {h: np.concatenate(y_aug[h]) for h in horizons}

        # Multi-horizon quantile: 3 horizons × 3 quantiles = 9 models
        sub_val, sub_test = [], []
        for h in horizons:
            for q in [0.25, 0.5, 0.75]:
                m_q = make_quantile_model(q)
                m_q.fit(X_aug_all, y_aug_all[h], sample_weight=w_aug_all,
                        eval_set=[(X_va, y_dict[h][s1:s2])], verbose=False)
                sub_val.append(m_q.predict(X_va))
                sub_test.append(m_q.predict(X_te))

        # Stack
        Sv = np.column_stack(sub_val)
        St = np.column_stack(sub_test)
        meta = Ridge(alpha=1.0)
        meta.fit(Sv, y_va)
        e_test = meta.predict(St)

        # AR
        e_val = meta.predict(Sv)
        ar_c = fit_ar(e_val, y_va)
        e_corrected = apply_ar(e_test, y_te, ar_c)
        r2_stack = compute_r2(y_te, e_corrected)
        all_stack.append(r2_stack)

        if detail:
            print(f"  {name}: base={r2_base:.4f} stack={r2_stack:.4f} Δ={r2_stack-r2_base:+.4f}")

    mb = np.mean(all_base)
    ms = np.mean(all_stack)
    wins = sum(1 for b, s in zip(all_base, all_stack) if s > b)
    results['status'] = 'pass'
    results['detail'] = f"base={mb:.4f} stack={ms:.4f} Δ={ms-mb:+.4f} wins={wins}/{len(all_base)}"
    results['base_r2'] = mb
    results['stack_r2'] = ms
    return results


# ============================================================
# EXP-1258: Patient-Specific Hyperparameter Tuning
# ============================================================
def exp_1258_patient_hpo(patients, detail=False):
    """Tune n_estimators and learning_rate per patient on validation set."""
    results = {'experiment': 'EXP-1258', 'name': 'Patient-Specific Hyperparameter Tuning'}
    all_base, all_tuned = [], []

    configs = [
        (300, 0.03), (300, 0.05), (300, 0.1),
        (500, 0.03), (500, 0.05), (500, 0.1),
        (800, 0.03), (800, 0.05),
    ]

    for p in patients:
        name = p['name']
        glucose, physics = prepare_patient_raw(p)
        X, y, g_cur = build_enhanced_features(p, glucose, physics)
        if len(X) < 200:
            continue

        X_tr, X_va, X_te, y_tr, y_va, y_te = split_3way(X, y)

        # Baseline (default params)
        m_base = make_xgb_sota()
        m_base.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
        r2_base = compute_r2(y_te, m_base.predict(X_te))
        all_base.append(r2_base)

        # HPO: try configs on validation set
        best_val_r2, best_config = -999, configs[0]
        for n_est, lr in configs:
            m = xgb.XGBRegressor(
                n_estimators=n_est, max_depth=3, learning_rate=lr,
                tree_method='hist', device='cuda',
                subsample=0.8, colsample_bytree=0.8,
            )
            m.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
            val_r2 = compute_r2(y_va, m.predict(X_va))
            if val_r2 > best_val_r2:
                best_val_r2 = val_r2
                best_config = (n_est, lr)

        # Retrain with best config
        m_tuned = xgb.XGBRegressor(
            n_estimators=best_config[0], max_depth=3, learning_rate=best_config[1],
            tree_method='hist', device='cuda',
            subsample=0.8, colsample_bytree=0.8,
        )
        m_tuned.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
        r2_tuned = compute_r2(y_te, m_tuned.predict(X_te))
        all_tuned.append(r2_tuned)

        if detail:
            print(f"  {name}: base={r2_base:.4f} tuned={r2_tuned:.4f} best={best_config} Δ={r2_tuned-r2_base:+.4f}")

    mb = np.mean(all_base)
    mt = np.mean(all_tuned)
    wins = sum(1 for b, t in zip(all_base, all_tuned) if t > b)
    results['status'] = 'pass'
    results['detail'] = f"base={mb:.4f} tuned={mt:.4f} Δ={mt-mb:+.4f} wins={wins}/{len(all_base)}"
    results['base_r2'] = mb
    results['tuned_r2'] = mt
    return results


# ============================================================
# EXP-1259: Wider Window (3h, 4h input)
# ============================================================
def exp_1259_wider_window(patients, detail=False):
    """Test 3h and 4h input windows (36, 48 steps) vs 2h baseline."""
    results = {'experiment': 'EXP-1259', 'name': 'Wider Input Windows'}
    window_results = {}

    for w_steps, w_label in [(24, '2h'), (36, '3h'), (48, '4h')]:
        w_r2s = []
        for p in patients:
            name = p['name']
            glucose, physics = prepare_patient_raw(p)
            X, y, g_cur = build_enhanced_features(p, glucose, physics,
                                                    window=w_steps)
            if len(X) < 200:
                continue
            X_tr, X_va, X_te, y_tr, y_va, y_te = split_3way(X, y)
            m = make_xgb_sota()
            m.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
            r2 = compute_r2(y_te, m.predict(X_te))
            w_r2s.append(r2)
        window_results[w_label] = np.mean(w_r2s) if w_r2s else 0
        if detail:
            print(f"  window={w_label}: R²={window_results[w_label]:.4f} (n={len(w_r2s)})")

    results['status'] = 'pass'
    results['detail'] = " ".join(f"{w}={r:.4f}" for w, r in window_results.items())
    results['window_r2'] = window_results
    return results


# ============================================================
# EXP-1260: Production Pipeline Benchmark
# ============================================================
def exp_1260_production_benchmark(patients, detail=False):
    """Benchmark the recommended production pipeline, 5-fold CV.
    Pipeline: Transfer + MSE (single 60-min model), the simplest proven winner."""
    results = {'experiment': 'EXP-1260', 'name': 'Production Pipeline Benchmark'}
    all_naive, all_base, all_prod = [], [], []
    patient_stats = get_patient_stats(patients)

    patient_data = {}
    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        X, y, g_cur = build_enhanced_features(p, glucose, physics)
        if len(X) >= 200:
            patient_data[p['name']] = (X, y, g_cur)

    for idx, p in enumerate(patients):
        name = p['name']
        if name not in patient_data:
            continue
        X, y, g_cur = patient_data[name]

        tscv = TimeSeriesSplit(n_splits=5)
        fold_naive, fold_base, fold_prod = [], [], []

        for fold, (tr_idx, te_idx) in enumerate(tscv.split(X)):
            vt = int(len(tr_idx) * 0.8)
            tr_train, tr_val = tr_idx[:vt], tr_idx[vt:]
            yt = y[te_idx]

            # Naive: last glucose value
            naive_pred = g_cur[te_idx]
            fold_naive.append(compute_r2(yt, naive_pred))

            # Base: individual model
            m = make_xgb_sota()
            m.fit(X[tr_train], y[tr_train],
                  eval_set=[(X[tr_val], y[tr_val])], verbose=False)
            fold_base.append(compute_r2(yt, m.predict(X[te_idx])))

            # Production: transfer augmentation
            similar_idxs = find_similar(idx, patient_stats, k=2)
            X_aug = [X[tr_train]]
            y_aug_list = [y[tr_train]]
            w_aug = [np.ones(len(tr_train))]
            for si in similar_idxs:
                sim_name = patients[si]['name']
                if sim_name in patient_data:
                    Xs, ys, _ = patient_data[sim_name]
                    n_use = int(len(ys) * 0.6)
                    X_aug.append(Xs[:n_use])
                    y_aug_list.append(ys[:n_use])
                    w_aug.append(np.full(n_use, 0.3))
            X_a = np.vstack(X_aug)
            y_a = np.concatenate(y_aug_list)
            w_a = np.concatenate(w_aug)

            m_prod = make_xgb_sota()
            m_prod.fit(X_a, y_a, sample_weight=w_a,
                       eval_set=[(X[tr_val], y[tr_val])], verbose=False)
            fold_prod.append(compute_r2(yt, m_prod.predict(X[te_idx])))

        n_mean = np.mean(fold_naive)
        b_mean = np.mean(fold_base)
        p_mean = np.mean(fold_prod)
        all_naive.append(n_mean)
        all_base.append(b_mean)
        all_prod.append(p_mean)
        if detail:
            rmse_prod = compute_rmse(y[te_idx], m_prod.predict(X[te_idx])) * GLUCOSE_SCALE
            print(f"  {name}: naive={n_mean:.4f} base={b_mean:.4f} prod={p_mean:.4f} Δ={p_mean-b_mean:+.4f} RMSE={rmse_prod:.1f}mg")

    mn = np.mean(all_naive)
    mb = np.mean(all_base)
    mp = np.mean(all_prod)
    wins = sum(1 for b, p in zip(all_base, all_prod) if p > b)
    results['status'] = 'pass'
    results['detail'] = f"naive={mn:.4f} base={mb:.4f} prod={mp:.4f} Δ={mp-mb:+.4f} wins={wins}/{len(all_base)}"
    results['naive_r2'] = mn
    results['base_r2'] = mb
    results['prod_r2'] = mp
    return results


# ============================================================
# Main
# ============================================================
EXPERIMENTS = [
    ('EXP-1251', exp_1251_proper_multi_horizon),
    ('EXP-1252', exp_1252_transfer_quantile),
    ('EXP-1253', exp_1253_calibration_fixed),
    ('EXP-1254', exp_1254_full_stack),
    ('EXP-1255', exp_1255_depth_ablation),
    ('EXP-1256', exp_1256_longer_horizons),
    ('EXP-1257', exp_1257_simple_stack),
    ('EXP-1258', exp_1258_patient_hpo),
    ('EXP-1259', exp_1259_wider_window),
    ('EXP-1260', exp_1260_production_benchmark),
]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--max-patients', type=int, default=11)
    parser.add_argument('--exp', type=str, default=None)
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
