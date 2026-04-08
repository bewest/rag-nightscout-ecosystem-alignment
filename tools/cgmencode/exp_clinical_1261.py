#!/usr/bin/env python3
"""EXP-1261 through EXP-1270: Optimized Production Stack & Deep Diagnostics.

Key goals:
- Combine ALL optimal params: depth-2, lr=0.03, 300 trees, transfer, quantile
- Short-horizon optimization (30-min with full stack)
- Feature importance analysis and pruning
- Causal vs non-causal AR investigation
- Leave-one-out cross-patient transfer
- Clinical validation of optimized production pipeline
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


def make_optimized_model(depth=2, lr=0.03, n_est=300):
    """Create XGBoost with all optimal hyperparameters."""
    return xgb.XGBRegressor(
        n_estimators=n_est, max_depth=depth, learning_rate=lr,
        tree_method='hist', device='cuda',
        subsample=0.8, colsample_bytree=0.8,
    )


def make_quantile_model(q=0.5, depth=2, lr=0.03, n_est=300):
    """Create optimized XGBoost quantile regressor."""
    return xgb.XGBRegressor(
        n_estimators=n_est, max_depth=depth, learning_rate=lr,
        objective='reg:quantileerror', quantile_alpha=q,
        tree_method='hist', device='cuda',
        subsample=0.8, colsample_bytree=0.8,
    )


def get_patient_stats(patients):
    stats = []
    for p in patients:
        glucose, _ = prepare_patient_raw(p)
        g = glucose[~np.isnan(glucose)] * GLUCOSE_SCALE
        stats.append({'name': p['name'], 'mean': np.mean(g), 'std': np.std(g)})
    return stats


def find_similar(target_idx, patient_stats, k=2):
    target = patient_stats[target_idx]
    dists = []
    for j, ps in enumerate(patient_stats):
        if j == target_idx:
            continue
        d = ((target['mean'] - ps['mean'])/50)**2 + ((target['std'] - ps['std'])/20)**2
        dists.append((d, j))
    dists.sort()
    return [idx for _, idx in dists[:k]]


def augment_with_transfer(X_train, y_train, target_idx, patients, patient_stats, weight=0.3):
    """Augment training data with samples from similar patients."""
    similar_idxs = find_similar(target_idx, patient_stats, k=2)
    all_X = [X_train]
    all_y = [y_train]
    all_w = [np.ones(len(X_train))]

    for si in similar_idxs:
        p = patients[si]
        glucose, physics = prepare_patient_raw(p)
        X_s, y_s, _ = build_enhanced_features(p, glucose, physics)
        if len(X_s) > 0:
            all_X.append(X_s)
            all_y.append(y_s)
            all_w.append(np.full(len(X_s), weight))

    return np.vstack(all_X), np.concatenate(all_y), np.concatenate(all_w)


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
# EXP-1261: Fully Optimized Production Stack (5-fold CV)
# ============================================================
def exp_1261_optimized_full_stack(patients, detail=False):
    """Combine ALL optimal: depth-2, lr=0.03, 300 trees, transfer, quantile, multi-horizon."""
    results = {'experiment': 'EXP-1261', 'name': 'Optimized Full Stack (d2/lr0.03/300t)'}
    patient_stats = get_patient_stats(patients)
    horizons = (6, 12, 18)
    all_base, all_opt = [], []

    for pi, p in enumerate(patients):
        name = p['name']
        glucose, physics = prepare_patient_raw(p)
        X, y_dict, g_cur = build_enhanced_multi_horizon(p, glucose, physics, horizons=horizons)
        if len(X) < 200:
            continue
        y_target = y_dict[12]

        # Build transfer-augmented data
        X_base, y_base, _ = build_enhanced_features(p, glucose, physics)
        X_aug, y_aug, w_aug = augment_with_transfer(
            X_base, y_base, pi, patients, patient_stats)

        tscv = TimeSeriesSplit(n_splits=5)
        fold_base, fold_opt = [], []

        for fold, (tr_idx, te_idx) in enumerate(tscv.split(X)):
            vt = int(len(tr_idx) * 0.8)
            tr_train, tr_val = tr_idx[:vt], tr_idx[vt:]

            # --- Baseline: default params, no transfer ---
            m_base = make_xgb_sota()
            m_base.fit(X[tr_train], y_target[tr_train],
                       eval_set=[(X[tr_val], y_target[tr_val])], verbose=False)
            pred_base = m_base.predict(X[te_idx])
            fold_base.append(compute_r2(y_target[te_idx], pred_base))

            # --- Optimized: d2/lr0.03/300t + transfer + quantile + multi-horizon ---
            # Build transfer-augmented training for multi-horizon
            sim_idxs = find_similar(pi, patient_stats, k=2)
            all_Xtr = [X[tr_train]]
            all_wtr = [np.ones(len(tr_train))]
            y_aug_dict = {h: [y_dict[h][tr_train]] for h in horizons}
            w_lists = [np.ones(len(tr_train))]

            for si in sim_idxs:
                sp = patients[si]
                sg, sph = prepare_patient_raw(sp)
                sX, sy_dict, _ = build_enhanced_multi_horizon(sp, sg, sph, horizons=horizons)
                if len(sX) > 0:
                    all_Xtr.append(sX)
                    w_lists.append(np.full(len(sX), 0.3))
                    for h in horizons:
                        y_aug_dict[h].append(sy_dict[h])

            X_train_aug = np.vstack(all_Xtr)
            w_train = np.concatenate(w_lists)
            y_train_aug = {h: np.concatenate(y_aug_dict[h]) for h in horizons}

            # Train multi-horizon quantile + MSE models
            sub_val, sub_test = [], []
            for h in horizons:
                for q in [0.25, 0.5, 0.75]:
                    m_q = make_quantile_model(q=q)
                    m_q.fit(X_train_aug, y_train_aug[h],
                            sample_weight=w_train,
                            eval_set=[(X[tr_val], y_dict[h][tr_val])], verbose=False)
                    sub_val.append(m_q.predict(X[tr_val]))
                    sub_test.append(m_q.predict(X[te_idx]))

                m_mse = make_optimized_model()
                m_mse.fit(X_train_aug, y_train_aug[h],
                          sample_weight=w_train,
                          eval_set=[(X[tr_val], y_dict[h][tr_val])], verbose=False)
                sub_val.append(m_mse.predict(X[tr_val]))
                sub_test.append(m_mse.predict(X[te_idx]))

            Sv = np.column_stack(sub_val)
            St = np.column_stack(sub_test)
            yv = y_target[tr_val]
            yt = y_target[te_idx]

            meta = Ridge(alpha=1.0)
            meta.fit(Sv, yv)
            pred_opt = meta.predict(St)
            fold_opt.append(compute_r2(yt, pred_opt))

        base_mean = np.mean(fold_base)
        opt_mean = np.mean(fold_opt)
        all_base.append(base_mean)
        all_opt.append(opt_mean)
        if detail:
            print(f"  {name}: base={base_mean:.3f} opt={opt_mean:.3f} Δ={opt_mean-base_mean:+.3f}")

    results['base_mean'] = float(np.mean(all_base))
    results['opt_mean'] = float(np.mean(all_opt))
    results['delta'] = float(np.mean(all_opt) - np.mean(all_base))
    results['wins'] = sum(1 for b, o in zip(all_base, all_opt) if o > b)
    results['n_patients'] = len(all_base)
    return results


# ============================================================
# EXP-1262: 30-min Horizon with Full Stack
# ============================================================
def exp_1262_short_horizon_stack(patients, detail=False):
    """30-min horizon with transfer+quantile — expected R² ≈ 0.82."""
    results = {'experiment': 'EXP-1262', 'name': '30-min Horizon Full Stack'}
    patient_stats = get_patient_stats(patients)
    horizons_30 = (3, 6, 9)  # 15/30/45 min for 30-min focused
    all_base, all_opt = [], []

    for pi, p in enumerate(patients):
        name = p['name']
        glucose, physics = prepare_patient_raw(p)
        X, y_dict, g_cur = build_enhanced_multi_horizon(p, glucose, physics, horizons=horizons_30)
        if len(X) < 200:
            continue
        y_target = y_dict[6]  # 30-min target

        sim_idxs = find_similar(pi, patient_stats, k=2)

        tscv = TimeSeriesSplit(n_splits=5)
        fold_base, fold_opt = [], []

        for fold, (tr_idx, te_idx) in enumerate(tscv.split(X)):
            vt = int(len(tr_idx) * 0.8)
            tr_train, tr_val = tr_idx[:vt], tr_idx[vt:]

            # Base: single 30-min model
            m_base = make_xgb_sota()
            m_base.fit(X[tr_train], y_target[tr_train],
                       eval_set=[(X[tr_val], y_target[tr_val])], verbose=False)
            fold_base.append(compute_r2(y_target[te_idx], m_base.predict(X[te_idx])))

            # Optimized: transfer + quantile + multi-horizon
            all_Xtr = [X[tr_train]]
            w_lists = [np.ones(len(tr_train))]
            y_aug_dict = {h: [y_dict[h][tr_train]] for h in horizons_30}

            for si in sim_idxs:
                sp = patients[si]
                sg, sph = prepare_patient_raw(sp)
                sX, sy_d, _ = build_enhanced_multi_horizon(sp, sg, sph, horizons=horizons_30)
                if len(sX) > 0:
                    all_Xtr.append(sX)
                    w_lists.append(np.full(len(sX), 0.3))
                    for h in horizons_30:
                        y_aug_dict[h].append(sy_d[h])

            X_aug = np.vstack(all_Xtr)
            w_aug = np.concatenate(w_lists)
            y_aug = {h: np.concatenate(y_aug_dict[h]) for h in horizons_30}

            sub_val, sub_test = [], []
            for h in horizons_30:
                for q in [0.25, 0.5, 0.75]:
                    m_q = make_quantile_model(q=q)
                    m_q.fit(X_aug, y_aug[h], sample_weight=w_aug,
                            eval_set=[(X[tr_val], y_dict[h][tr_val])], verbose=False)
                    sub_val.append(m_q.predict(X[tr_val]))
                    sub_test.append(m_q.predict(X[te_idx]))
                m_m = make_optimized_model()
                m_m.fit(X_aug, y_aug[h], sample_weight=w_aug,
                        eval_set=[(X[tr_val], y_dict[h][tr_val])], verbose=False)
                sub_val.append(m_m.predict(X[tr_val]))
                sub_test.append(m_m.predict(X[te_idx]))

            Sv = np.column_stack(sub_val)
            St = np.column_stack(sub_test)
            meta = Ridge(alpha=1.0)
            meta.fit(Sv, y_target[tr_val])
            fold_opt.append(compute_r2(y_target[te_idx], meta.predict(St)))

        base_mean = np.mean(fold_base)
        opt_mean = np.mean(fold_opt)
        all_base.append(base_mean)
        all_opt.append(opt_mean)
        if detail:
            print(f"  {name}: base={base_mean:.3f} opt={opt_mean:.3f} Δ={opt_mean-base_mean:+.3f}")

    results['base_30min'] = float(np.mean(all_base))
    results['stack_30min'] = float(np.mean(all_opt))
    results['delta'] = float(np.mean(all_opt) - np.mean(all_base))
    results['wins'] = sum(1 for b, o in zip(all_base, all_opt) if o > b)
    results['n_patients'] = len(all_base)
    return results


# ============================================================
# EXP-1263: Leave-One-Out Transfer Learning
# ============================================================
def exp_1263_loo_transfer(patients, detail=False):
    """Train on ALL other patients, fine-tune on target. LOO evaluation."""
    results = {'experiment': 'EXP-1263', 'name': 'Leave-One-Out Transfer'}
    all_individual, all_loo = [], []

    for pi, p in enumerate(patients):
        name = p['name']
        glucose, physics = prepare_patient_raw(p)
        X, y, g_cur = build_enhanced_features(p, glucose, physics)
        if len(X) < 200:
            continue

        # Build combined other-patient training data
        X_others, y_others = [], []
        for oi, op in enumerate(patients):
            if oi == pi:
                continue
            og, oph = prepare_patient_raw(op)
            oX, oy, _ = build_enhanced_features(op, og, oph)
            if len(oX) > 0:
                X_others.append(oX)
                y_others.append(oy)

        if not X_others:
            continue

        X_other = np.vstack(X_others)
        y_other = np.concatenate(y_others)

        # Split target patient 60/20/20
        n = len(X)
        n_tr, n_val = int(n * 0.6), int(n * 0.2)
        X_tr, X_val, X_te = X[:n_tr], X[n_tr:n_tr+n_val], X[n_tr+n_val:]
        y_tr, y_val, y_te = y[:n_tr], y[n_tr:n_tr+n_val], y[n_tr+n_val:]

        # Individual model (target only)
        m_ind = make_optimized_model()
        m_ind.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=False)
        r2_ind = compute_r2(y_te, m_ind.predict(X_te))
        all_individual.append(r2_ind)

        # LOO model: pre-train on others, fine-tune on target
        # Step 1: train on all others
        m_pre = make_optimized_model(n_est=500, lr=0.03)
        m_pre.fit(X_other, y_other, verbose=False)

        # Step 2: fine-tune on target with lower learning rate
        m_fine = make_optimized_model(n_est=200, lr=0.01)
        m_fine.fit(X_tr, y_tr,
                   eval_set=[(X_val, y_val)], verbose=False,
                   xgb_model=m_pre)
        r2_loo = compute_r2(y_te, m_fine.predict(X_te))
        all_loo.append(r2_loo)

        if detail:
            print(f"  {name}: individual={r2_ind:.3f} loo={r2_loo:.3f} Δ={r2_loo-r2_ind:+.3f}")

    results['individual_mean'] = float(np.mean(all_individual))
    results['loo_mean'] = float(np.mean(all_loo))
    results['delta'] = float(np.mean(all_loo) - np.mean(all_individual))
    results['wins'] = sum(1 for i, l in zip(all_individual, all_loo) if l > i)
    results['n_patients'] = len(all_individual)
    return results


# ============================================================
# EXP-1264: Feature Importance Pruning
# ============================================================
def exp_1264_feature_pruning(patients, detail=False):
    """Keep only top-K features by importance. Test if pruning helps."""
    results = {'experiment': 'EXP-1264', 'name': 'Feature Importance Pruning'}
    ks = [50, 100, 150, 186]  # test different feature counts
    all_by_k = {k: [] for k in ks}
    avg_importance = None

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        X, y, g_cur = build_enhanced_features(p, glucose, physics)
        if len(X) < 200:
            continue

        n = len(X)
        n_tr, n_val = int(n * 0.6), int(n * 0.2)
        X_tr, X_val, X_te = X[:n_tr], X[n_tr:n_tr+n_val], X[n_tr+n_val:]
        y_tr, y_val, y_te = y[:n_tr], y[n_tr:n_tr+n_val], y[n_tr+n_val:]

        # Get feature importance from full model
        m_full = make_optimized_model()
        m_full.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=False)
        imp = m_full.feature_importances_
        if avg_importance is None:
            avg_importance = imp.copy()
        else:
            avg_importance += imp

        sorted_idx = np.argsort(imp)[::-1]

        for k in ks:
            top_k = sorted_idx[:k]
            m_k = make_optimized_model()
            m_k.fit(X_tr[:, top_k], y_tr,
                    eval_set=[(X_val[:, top_k], y_val)], verbose=False)
            r2 = compute_r2(y_te, m_k.predict(X_te[:, top_k]))
            all_by_k[k].append(r2)

        if detail:
            vals = " ".join(f"k={k}:{np.mean([all_by_k[k][-1]]):.3f}" for k in ks)
            print(f"  {p['name']}: {vals}")

    # Average importance
    if avg_importance is not None:
        avg_importance /= len(patients)
        top20_idx = np.argsort(avg_importance)[::-1][:20]
        results['top20_features'] = [int(i) for i in top20_idx]
        results['top20_importance'] = [float(avg_importance[i]) for i in top20_idx]

    for k in ks:
        results[f'r2_k{k}'] = float(np.mean(all_by_k[k]))
    results['best_k'] = max(ks, key=lambda k: np.mean(all_by_k[k]))
    return results


# ============================================================
# EXP-1265: Causal AR Investigation
# ============================================================
def exp_1265_causal_ar(patients, detail=False):
    """Compare: (a) no AR, (b) causal AR (train residuals), (c) online AR (test residuals).
    Goal: understand how much of EXP-1211's 0.781 comes from future info."""
    results = {'experiment': 'EXP-1265', 'name': 'Causal vs Online AR'}
    all_no_ar, all_causal, all_online = [], [], []

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        X, y, g_cur = build_enhanced_features(p, glucose, physics)
        if len(X) < 200:
            continue

        n = len(X)
        n_tr, n_val = int(n * 0.6), int(n * 0.2)
        X_tr, X_val, X_te = X[:n_tr], X[n_tr:n_tr+n_val], X[n_tr+n_val:]
        y_tr, y_val, y_te = y[:n_tr], y[n_tr:n_tr+n_val], y[n_tr+n_val:]

        m = make_optimized_model()
        m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=False)

        pred_val = m.predict(X_val)
        pred_test = m.predict(X_te)

        # (a) No AR
        r2_no = compute_r2(y_te, pred_test)
        all_no_ar.append(r2_no)

        # (b) Causal AR: fit on training residuals, apply with ONLY training residuals
        pred_train = m.predict(X_tr)
        ar_c_train = fit_ar(pred_train, y_tr)

        # For causal: we can only use past residuals (from training period)
        # Stitch train+test predictions, use train residuals but freeze at test boundary
        full_pred = np.concatenate([pred_train, pred_val, pred_test])
        full_y = np.concatenate([y_tr, y_val, y_te])
        full_corrected = apply_ar(full_pred, full_y, ar_c_train)
        # But wait — apply_ar uses y_true at runtime too (test residuals leak)
        # TRUE causal: only use residuals from BEFORE the test set
        causal_pred = pred_test.copy()
        resid_before = y_val - pred_val  # last available residuals before test
        for i in range(len(causal_pred)):
            # Use validation residuals as "most recent known"
            if i < 2:
                causal_pred[i] += ar_c_train[0] * resid_before[-1] + (ar_c_train[1] * resid_before[-2] if len(ar_c_train) > 1 else 0)
            # After that, residuals go stale — no correction
        r2_causal = compute_r2(y_te, causal_pred)
        all_causal.append(r2_causal)

        # (c) Online AR: use test residuals as they "arrive" (non-causal, EXP-1211 style)
        ar_c_val = fit_ar(pred_val, y_val)
        online_pred = apply_ar(pred_test, y_te, ar_c_val)
        r2_online = compute_r2(y_te, online_pred)
        all_online.append(r2_online)

        if detail:
            print(f"  {p['name']}: no_ar={r2_no:.3f} causal={r2_causal:.3f} online={r2_online:.3f}")

    results['no_ar_mean'] = float(np.mean(all_no_ar))
    results['causal_ar_mean'] = float(np.mean(all_causal))
    results['online_ar_mean'] = float(np.mean(all_online))
    results['causal_delta'] = float(np.mean(all_causal) - np.mean(all_no_ar))
    results['online_delta'] = float(np.mean(all_online) - np.mean(all_no_ar))
    return results


# ============================================================
# EXP-1266: Residual Pattern Analysis
# ============================================================
def exp_1266_residual_patterns(patients, detail=False):
    """Analyze what patterns remain hardest to predict."""
    results = {'experiment': 'EXP-1266', 'name': 'Residual Pattern Analysis'}
    all_stats = {'low': [], 'normal': [], 'high': [], 'very_high': [],
                 'rising': [], 'falling': [], 'stable': [],
                 'post_meal': [], 'fasting': []}

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        X, y, g_cur = build_enhanced_features(p, glucose, physics)
        if len(X) < 200:
            continue

        n = len(X)
        n_tr, n_val = int(n * 0.6), int(n * 0.2)
        X_tr, X_val, X_te = X[:n_tr], X[n_tr:n_tr+n_val], X[n_tr+n_val:]
        y_tr, y_val, y_te = y[:n_tr], y[n_tr:n_tr+n_val], y[n_tr+n_val:]
        g_te = g_cur[n_tr+n_val:]

        m = make_optimized_model()
        m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=False)
        pred = m.predict(X_te)
        resid = (y_te - pred) * GLUCOSE_SCALE
        g_mg = g_te * GLUCOSE_SCALE

        # Stratify by glucose level
        for mask, label in [
            (g_mg < 70, 'low'), (( g_mg >= 70) & (g_mg < 180), 'normal'),
            ((g_mg >= 180) & (g_mg < 250), 'high'), (g_mg >= 250, 'very_high')
        ]:
            if mask.sum() > 10:
                all_stats[label].append(float(np.sqrt(np.mean(resid[mask]**2))))

        # Stratify by trend (glucose derivative from features)
        deriv = X_te[:, WINDOW]  # first derivative feature
        for mask, label in [
            (deriv > 0.05, 'rising'), (deriv < -0.05, 'falling'),
            ((deriv >= -0.05) & (deriv <= 0.05), 'stable')
        ]:
            if mask.sum() > 10:
                all_stats[label].append(float(np.sqrt(np.mean(resid[mask]**2))))

        # Post-meal vs fasting (carb activity from physics)
        carb_activity = X_te[:, WINDOW + 7] if X_te.shape[1] > WINDOW + 7 else None
        if carb_activity is not None:
            meal = carb_activity > 0.01
            fast = carb_activity <= 0.01
            if meal.sum() > 10:
                all_stats['post_meal'].append(float(np.sqrt(np.mean(resid[meal]**2))))
            if fast.sum() > 10:
                all_stats['fasting'].append(float(np.sqrt(np.mean(resid[fast]**2))))

    for label, vals in all_stats.items():
        if vals:
            results[f'rmse_{label}'] = float(np.mean(vals))
    return results


# ============================================================
# EXP-1267: Horizon Weight Optimization
# ============================================================
def exp_1267_horizon_weights(patients, detail=False):
    """Compare uniform vs learned weights for multi-horizon ensemble."""
    results = {'experiment': 'EXP-1267', 'name': 'Horizon Weight Optimization'}
    all_uniform, all_learned, all_ridge = [], [], []
    horizons = (6, 12, 18)

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        X, y_dict, g_cur = build_enhanced_multi_horizon(p, glucose, physics, horizons=horizons)
        if len(X) < 200:
            continue
        y_target = y_dict[12]

        tscv = TimeSeriesSplit(n_splits=5)
        fold_uni, fold_learn, fold_ridge = [], [], []

        for fold, (tr_idx, te_idx) in enumerate(tscv.split(X)):
            vt = int(len(tr_idx) * 0.8)
            tr_train, tr_val = tr_idx[:vt], tr_idx[vt:]

            sub_val, sub_test = [], []
            for h in horizons:
                m_h = make_optimized_model()
                m_h.fit(X[tr_train], y_dict[h][tr_train],
                        eval_set=[(X[tr_val], y_dict[h][tr_val])], verbose=False)
                sub_val.append(m_h.predict(X[tr_val]))
                sub_test.append(m_h.predict(X[te_idx]))

            Sv = np.column_stack(sub_val)
            St = np.column_stack(sub_test)
            yv = y_target[tr_val]
            yt = y_target[te_idx]

            # Uniform average
            pred_uni = np.mean(St, axis=1)
            fold_uni.append(compute_r2(yt, pred_uni))

            # Learned weights (minimize MSE on val)
            from scipy.optimize import minimize
            def obj(w):
                pred = Sv @ w
                return np.mean((yv - pred)**2)
            w0 = np.array([1/3, 1/3, 1/3])
            res = minimize(obj, w0, method='Nelder-Mead')
            pred_learn = St @ res.x
            fold_learn.append(compute_r2(yt, pred_learn))

            # Ridge stacking (current approach)
            meta = Ridge(alpha=1.0)
            meta.fit(Sv, yv)
            fold_ridge.append(compute_r2(yt, meta.predict(St)))

        all_uniform.append(np.mean(fold_uni))
        all_learned.append(np.mean(fold_learn))
        all_ridge.append(np.mean(fold_ridge))
        if detail:
            print(f"  {p['name']}: uniform={np.mean(fold_uni):.3f} "
                  f"learned={np.mean(fold_learn):.3f} ridge={np.mean(fold_ridge):.3f}")

    results['uniform_mean'] = float(np.mean(all_uniform))
    results['learned_mean'] = float(np.mean(all_learned))
    results['ridge_mean'] = float(np.mean(all_ridge))
    return results


# ============================================================
# EXP-1268: Monotonic Constraints (Insulin → Lower Glucose)
# ============================================================
def exp_1268_monotonic_constraints(patients, detail=False):
    """Apply monotonic constraint: more insulin → lower future glucose."""
    results = {'experiment': 'EXP-1268', 'name': 'Monotonic Constraints'}
    all_base, all_mono = [], []

    # Feature indices for physics-based features that should be monotonic
    # IOB features (higher IOB → lower glucose): indices WINDOW+0 to WINDOW+5 (PK channels)
    # Carb features (higher COB → higher glucose): WINDOW+6, WINDOW+7

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        X, y, g_cur = build_enhanced_features(p, glucose, physics)
        if len(X) < 200:
            continue

        n_feat = X.shape[1]
        n = len(X)
        n_tr, n_val = int(n * 0.6), int(n * 0.2)
        X_tr, X_val, X_te = X[:n_tr], X[n_tr:n_tr+n_val], X[n_tr+n_val:]
        y_tr, y_val, y_te = y[:n_tr], y[n_tr:n_tr+n_val], y[n_tr+n_val:]

        # Base model
        m_base = make_optimized_model()
        m_base.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=False)
        r2_base = compute_r2(y_te, m_base.predict(X_te))
        all_base.append(r2_base)

        # Monotonic model
        # Build constraint tuple: 0=no constraint, -1=decreasing, +1=increasing
        constraints = [0] * n_feat
        # IOB/activity features should predict LOWER glucose (negative)
        for offset in range(6):  # first 6 PK channels = IOB/activity
            if WINDOW + offset < n_feat:
                constraints[WINDOW + offset] = -1
        # COB/carb features should predict HIGHER glucose (positive)
        for offset in range(6, 8):  # carb_cob, carb_activity
            if WINDOW + offset < n_feat:
                constraints[WINDOW + offset] = 1

        m_mono = make_optimized_model()
        m_mono.set_params(monotone_constraints=tuple(constraints))
        m_mono.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=False)
        r2_mono = compute_r2(y_te, m_mono.predict(X_te))
        all_mono.append(r2_mono)

        if detail:
            print(f"  {p['name']}: base={r2_base:.3f} mono={r2_mono:.3f} Δ={r2_mono-r2_base:+.3f}")

    results['base_mean'] = float(np.mean(all_base))
    results['mono_mean'] = float(np.mean(all_mono))
    results['delta'] = float(np.mean(all_mono) - np.mean(all_base))
    results['wins'] = sum(1 for b, m in zip(all_base, all_mono) if m > b)
    results['n_patients'] = len(all_base)
    return results


# ============================================================
# EXP-1269: Interaction Features (Insulin × Glucose)
# ============================================================
def exp_1269_interaction_features(patients, detail=False):
    """Add explicit insulin×glucose and glucose×trend interactions."""
    results = {'experiment': 'EXP-1269', 'name': 'Explicit Interaction Features'}
    all_base, all_interact = [], []

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        X, y, g_cur = build_enhanced_features(p, glucose, physics)
        if len(X) < 200:
            continue

        # Add interaction features
        # glucose_last × iob, glucose_last × trend, trend × iob
        g_last = X[:, WINDOW-1:WINDOW]  # last glucose value in window
        if X.shape[1] > WINDOW + 7:
            iob = X[:, WINDOW:WINDOW+1]   # total IOB
            carb = X[:, WINDOW+6:WINDOW+7]  # COB
            trend = X[:, WINDOW+8:WINDOW+9] if X.shape[1] > WINDOW+8 else np.zeros_like(g_last)

            interactions = np.column_stack([
                g_last * iob,
                g_last * carb,
                g_last * trend,
                iob * carb,
                iob * trend,
                g_last ** 2,
                iob ** 2,
            ])
            X_int = np.hstack([X, interactions])
        else:
            X_int = X

        n = len(X)
        n_tr, n_val = int(n * 0.6), int(n * 0.2)

        # Base
        m_base = make_optimized_model()
        m_base.fit(X[:n_tr], y[:n_tr],
                   eval_set=[(X[n_tr:n_tr+n_val], y[n_tr:n_tr+n_val])], verbose=False)
        r2_base = compute_r2(y[n_tr+n_val:], m_base.predict(X[n_tr+n_val:]))
        all_base.append(r2_base)

        # With interactions
        m_int = make_optimized_model()
        m_int.fit(X_int[:n_tr], y[:n_tr],
                  eval_set=[(X_int[n_tr:n_tr+n_val], y[n_tr:n_tr+n_val])], verbose=False)
        r2_int = compute_r2(y[n_tr+n_val:], m_int.predict(X_int[n_tr+n_val:]))
        all_interact.append(r2_int)

        if detail:
            print(f"  {p['name']}: base={r2_base:.3f} interact={r2_int:.3f} Δ={r2_int-r2_base:+.3f}")

    results['base_mean'] = float(np.mean(all_base))
    results['interact_mean'] = float(np.mean(all_interact))
    results['delta'] = float(np.mean(all_interact) - np.mean(all_base))
    results['wins'] = sum(1 for b, i in zip(all_base, all_interact) if i > b)
    results['n_patients'] = len(all_base)
    return results


# ============================================================
# EXP-1270: Clinical Validation of Optimized Pipeline
# ============================================================
def exp_1270_clinical_validation(patients, detail=False):
    """Full clinical metrics for the optimized production pipeline."""
    results = {'experiment': 'EXP-1270', 'name': 'Optimized Pipeline Clinical Validation'}
    patient_stats = get_patient_stats(patients)
    all_mard, all_zone_a, all_r2 = [], [], []
    all_rmse_low, all_rmse_normal, all_rmse_high = [], [], []

    for pi, p in enumerate(patients):
        glucose, physics = prepare_patient_raw(p)
        X, y, g_cur = build_enhanced_features(p, glucose, physics)
        if len(X) < 200:
            continue

        n = len(X)
        n_tr, n_val = int(n * 0.6), int(n * 0.2)
        X_tr, X_val, X_te = X[:n_tr], X[n_tr:n_tr+n_val], X[n_tr+n_val:]
        y_tr, y_val, y_te = y[:n_tr], y[n_tr:n_tr+n_val], y[n_tr+n_val:]
        g_te = g_cur[n_tr+n_val:]

        # Transfer-augmented training
        X_aug, y_aug, w_aug = augment_with_transfer(
            X_tr, y_tr, pi, patients, patient_stats)

        m = make_optimized_model()
        m.fit(X_aug, y_aug, sample_weight=w_aug,
              eval_set=[(X_val, y_val)], verbose=False)
        pred = m.predict(X_te)

        # Convert back to mg/dL
        pred_mg = (g_te + pred) * GLUCOSE_SCALE  # predicted future glucose
        actual_mg = (g_te + y_te) * GLUCOSE_SCALE  # actual future glucose
        current_mg = g_te * GLUCOSE_SCALE

        # Clip to reasonable range
        pred_mg = np.clip(pred_mg, 30, 500)
        actual_mg = np.clip(actual_mg, 30, 500)

        valid = (actual_mg > 30) & (pred_mg > 30)
        if valid.sum() < 10:
            continue

        pred_v = pred_mg[valid]
        actual_v = actual_mg[valid]

        # MARD
        mard = np.mean(np.abs(pred_v - actual_v) / actual_v) * 100
        all_mard.append(mard)

        # Clarke Error Grid Zone A (simplified)
        zone_a = 0
        for pv, av in zip(pred_v, actual_v):
            if av <= 70:
                if pv <= 70:
                    zone_a += 1
                elif abs(pv - av) <= 20:
                    zone_a += 1
            elif av <= 180:
                if abs(pv - av) <= 20 or abs(pv - av)/av <= 0.20:
                    zone_a += 1
            else:
                if abs(pv - av)/av <= 0.20:
                    zone_a += 1
        zone_a_pct = zone_a / len(pred_v) * 100
        all_zone_a.append(zone_a_pct)

        # R²
        r2 = compute_r2(y_te, pred)
        all_r2.append(r2)

        # RMSE by glucose zone
        for mask, label, lst in [
            (current_mg < 70, 'low', all_rmse_low),
            ((current_mg >= 70) & (current_mg < 180), 'normal', all_rmse_normal),
            (current_mg >= 180, 'high', all_rmse_high)
        ]:
            if mask.sum() > 5:
                rmse_zone = np.sqrt(np.mean(((y_te[mask] - pred[mask]) * GLUCOSE_SCALE)**2))
                lst.append(rmse_zone)

        if detail:
            print(f"  {p['name']}: R²={r2:.3f} MARD={mard:.1f}% ZoneA={zone_a_pct:.1f}%")

    results['mean_r2'] = float(np.mean(all_r2))
    results['mean_mard'] = float(np.mean(all_mard))
    results['mean_zone_a'] = float(np.mean(all_zone_a))
    results['rmse_low'] = float(np.mean(all_rmse_low)) if all_rmse_low else None
    results['rmse_normal'] = float(np.mean(all_rmse_normal)) if all_rmse_normal else None
    results['rmse_high'] = float(np.mean(all_rmse_high)) if all_rmse_high else None
    results['n_patients'] = len(all_r2)
    return results


# ============================================================
# Main
# ============================================================
EXPERIMENTS = {
    1261: ('Optimized Full Stack', exp_1261_optimized_full_stack),
    1262: ('30-min Horizon Stack', exp_1262_short_horizon_stack),
    1263: ('LOO Transfer', exp_1263_loo_transfer),
    1264: ('Feature Pruning', exp_1264_feature_pruning),
    1265: ('Causal vs Online AR', exp_1265_causal_ar),
    1266: ('Residual Patterns', exp_1266_residual_patterns),
    1267: ('Horizon Weights', exp_1267_horizon_weights),
    1268: ('Monotonic Constraints', exp_1268_monotonic_constraints),
    1269: ('Interaction Features', exp_1269_interaction_features),
    1270: ('Clinical Validation', exp_1270_clinical_validation),
}


def main():
    parser = argparse.ArgumentParser(description='EXP-1261-1270')
    parser.add_argument('--experiments', type=str, default='all')
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--max-patients', type=int, default=11)
    args = parser.parse_args()

    patients = load_patients(PATIENTS_DIR, max_patients=args.max_patients)
    print(f"Loaded {len(patients)} patients")

    if args.experiments == 'all':
        exp_ids = sorted(EXPERIMENTS.keys())
    else:
        exp_ids = [int(x) for x in args.experiments.split(',')]

    all_results = []
    for eid in exp_ids:
        name, func = EXPERIMENTS[eid]
        print(f"\n{'='*60}")
        print(f"EXP-{eid}: {name}")
        print(f"{'='*60}")
        t0 = time.time()
        try:
            result = func(patients, detail=args.detail)
            elapsed = time.time() - t0
            result['elapsed_seconds'] = round(elapsed, 1)
            all_results.append(result)
            print(f"  Completed in {elapsed:.1f}s")
            for k, v in result.items():
                if k not in ('experiment', 'name', 'elapsed_seconds',
                             'top20_features', 'top20_importance'):
                    print(f"  {k}: {v}")
        except Exception as e:
            print(f"  FAILED: {e}")
            import traceback; traceback.print_exc()
            all_results.append({'experiment': f'EXP-{eid}', 'error': str(e)})

    if args.save and all_results:
        save_results(all_results, f'exp_clinical_1261_results')

    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    for r in all_results:
        exp = r.get('experiment', '?')
        name = r.get('name', '?')
        if 'error' in r:
            print(f"  {exp}: FAILED - {r['error']}")
        elif 'delta' in r:
            wins = r.get('wins', '?')
            n = r.get('n_patients', '?')
            print(f"  {exp} ({name}): Δ={r['delta']:+.3f} ({wins}/{n} wins)")
        elif 'opt_mean' in r:
            print(f"  {exp} ({name}): base={r.get('base_mean',0):.3f} opt={r['opt_mean']:.3f}")
        else:
            print(f"  {exp} ({name}): {r}")


if __name__ == '__main__':
    main()
