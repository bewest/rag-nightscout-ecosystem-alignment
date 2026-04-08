#!/usr/bin/env python3
"""EXP-1271 through EXP-1280: Uniform Averaging Stack & Novel Features.

Key goals:
- Apply uniform averaging discovery (EXP-1267) to full stack
- Explore glucose velocity/acceleration features at multiple scales
- Temporal data augmentation
- Cross-patient generalization hold-out test
- Final production pipeline benchmark with all learnings
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
    return xgb.XGBRegressor(
        n_estimators=n_est, max_depth=depth, learning_rate=lr,
        tree_method='hist', device='cuda',
        subsample=0.8, colsample_bytree=0.8,
    )


def make_quantile_model(q=0.5, depth=2, lr=0.03, n_est=300):
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


def augment_with_transfer_mh(X_train, y_dict_train, target_idx, patients,
                              patient_stats, horizons, weight=0.3):
    """Transfer augmentation for multi-horizon data."""
    sim_idxs = find_similar(target_idx, patient_stats, k=2)
    all_X = [X_train]
    all_w = [np.ones(len(X_train))]
    all_y = {h: [y_dict_train[h]] for h in horizons}

    for si in sim_idxs:
        sp = patients[si]
        sg, sph = prepare_patient_raw(sp)
        sX, sy_d, _ = build_enhanced_multi_horizon(sp, sg, sph, horizons=horizons)
        if len(sX) > 0:
            all_X.append(sX)
            all_w.append(np.full(len(sX), weight))
            for h in horizons:
                all_y[h].append(sy_d[h])

    X_aug = np.vstack(all_X)
    w_aug = np.concatenate(all_w)
    y_aug = {h: np.concatenate(all_y[h]) for h in horizons}
    return X_aug, y_aug, w_aug


# ============================================================
# EXP-1271: Full Stack with Uniform Averaging (5-fold CV)
# ============================================================
def exp_1271_uniform_full_stack(patients, detail=False):
    """Full stack using UNIFORM averaging instead of Ridge stacking."""
    results = {'experiment': 'EXP-1271', 'name': 'Full Stack + Uniform Averaging'}
    patient_stats = get_patient_stats(patients)
    horizons = (6, 12, 18)
    all_ridge, all_uniform = [], []

    for pi, p in enumerate(patients):
        name = p['name']
        glucose, physics = prepare_patient_raw(p)
        X, y_dict, g_cur = build_enhanced_multi_horizon(p, glucose, physics, horizons=horizons)
        if len(X) < 200:
            continue
        y_target = y_dict[12]

        tscv = TimeSeriesSplit(n_splits=5)
        fold_ridge, fold_uniform = [], []

        for fold, (tr_idx, te_idx) in enumerate(tscv.split(X)):
            vt = int(len(tr_idx) * 0.8)
            tr_train, tr_val = tr_idx[:vt], tr_idx[vt:]

            # Build transfer-augmented data
            y_dict_tr = {h: y_dict[h][tr_train] for h in horizons}
            X_aug, y_aug, w_aug = augment_with_transfer_mh(
                X[tr_train], y_dict_tr, pi, patients, patient_stats, horizons)

            sub_val, sub_test = [], []
            for h in horizons:
                # Quantile models
                for q in [0.25, 0.5, 0.75]:
                    m_q = make_quantile_model(q=q)
                    m_q.fit(X_aug, y_aug[h], sample_weight=w_aug,
                            eval_set=[(X[tr_val], y_dict[h][tr_val])], verbose=False)
                    sub_val.append(m_q.predict(X[tr_val]))
                    sub_test.append(m_q.predict(X[te_idx]))
                # MSE model
                m_m = make_optimized_model()
                m_m.fit(X_aug, y_aug[h], sample_weight=w_aug,
                        eval_set=[(X[tr_val], y_dict[h][tr_val])], verbose=False)
                sub_val.append(m_m.predict(X[tr_val]))
                sub_test.append(m_m.predict(X[te_idx]))

            St = np.column_stack(sub_test)
            Sv = np.column_stack(sub_val)
            yt = y_target[te_idx]
            yv = y_target[tr_val]

            # Uniform averaging
            pred_uni = np.mean(St, axis=1)
            fold_uniform.append(compute_r2(yt, pred_uni))

            # Ridge stacking
            meta = Ridge(alpha=1.0)
            meta.fit(Sv, yv)
            pred_ridge = meta.predict(St)
            fold_ridge.append(compute_r2(yt, pred_ridge))

        ridge_mean = np.mean(fold_ridge)
        uni_mean = np.mean(fold_uniform)
        all_ridge.append(ridge_mean)
        all_uniform.append(uni_mean)
        if detail:
            print(f"  {name}: ridge={ridge_mean:.3f} uniform={uni_mean:.3f} "
                  f"Δ(uni-ridge)={uni_mean-ridge_mean:+.3f}")

    results['ridge_mean'] = float(np.mean(all_ridge))
    results['uniform_mean'] = float(np.mean(all_uniform))
    results['delta_uni_vs_ridge'] = float(np.mean(all_uniform) - np.mean(all_ridge))
    results['uniform_wins'] = sum(1 for r, u in zip(all_ridge, all_uniform) if u > r)
    results['n_patients'] = len(all_ridge)
    return results


# ============================================================
# EXP-1272: Multi-Scale Glucose Velocity Features
# ============================================================
def exp_1272_velocity_features(patients, detail=False):
    """Add glucose velocity at 5/15/30/60 min scales + acceleration."""
    results = {'experiment': 'EXP-1272', 'name': 'Multi-Scale Velocity Features'}
    all_base, all_vel = [], []

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        X, y, g_cur = build_enhanced_features(p, glucose, physics)
        if len(X) < 200:
            continue

        # Extract glucose window (first WINDOW features)
        g_win = X[:, :WINDOW]
        # Velocity at multiple scales (1-step=5min, 3-step=15min, 6-step=30min, 12-step=60min)
        vel_features = []
        for step in [1, 3, 6, 12]:
            if step < WINDOW:
                vel = g_win[:, -1] - g_win[:, -1-step]  # change over step
                vel_features.append(vel.reshape(-1, 1))
                # Velocity of velocity = acceleration
                if step * 2 < WINDOW:
                    acc = (g_win[:, -1] - g_win[:, -1-step]) - (g_win[:, -1-step] - g_win[:, -1-2*step])
                    vel_features.append(acc.reshape(-1, 1))

        if vel_features:
            X_vel = np.hstack([X] + vel_features)
        else:
            X_vel = X

        n = len(X)
        n_tr, n_val = int(n * 0.6), int(n * 0.2)

        m_base = make_optimized_model()
        m_base.fit(X[:n_tr], y[:n_tr],
                   eval_set=[(X[n_tr:n_tr+n_val], y[n_tr:n_tr+n_val])], verbose=False)
        r2_base = compute_r2(y[n_tr+n_val:], m_base.predict(X[n_tr+n_val:]))
        all_base.append(r2_base)

        m_vel = make_optimized_model()
        m_vel.fit(X_vel[:n_tr], y[:n_tr],
                  eval_set=[(X_vel[n_tr:n_tr+n_val], y[n_tr:n_tr+n_val])], verbose=False)
        r2_vel = compute_r2(y[n_tr+n_val:], m_vel.predict(X_vel[n_tr+n_val:]))
        all_vel.append(r2_vel)

        if detail:
            print(f"  {p['name']}: base={r2_base:.3f} vel={r2_vel:.3f} Δ={r2_vel-r2_base:+.3f}")

    results['base_mean'] = float(np.mean(all_base))
    results['vel_mean'] = float(np.mean(all_vel))
    results['delta'] = float(np.mean(all_vel) - np.mean(all_base))
    results['wins'] = sum(1 for b, v in zip(all_base, all_vel) if v > b)
    results['n_features_added'] = len(vel_features) if vel_features else 0
    results['n_patients'] = len(all_base)
    return results


# ============================================================
# EXP-1273: Adaptive Transfer Weight
# ============================================================
def exp_1273_adaptive_transfer(patients, detail=False):
    """Learn optimal transfer weight per patient via validation."""
    results = {'experiment': 'EXP-1273', 'name': 'Adaptive Transfer Weight'}
    patient_stats = get_patient_stats(patients)
    all_fixed, all_adaptive = [], []
    optimal_weights = []

    for pi, p in enumerate(patients):
        glucose, physics = prepare_patient_raw(p)
        X, y, g_cur = build_enhanced_features(p, glucose, physics)
        if len(X) < 200:
            continue

        n = len(X)
        n_tr, n_val = int(n * 0.6), int(n * 0.2)
        X_tr, X_val, X_te = X[:n_tr], X[n_tr:n_tr+n_val], X[n_tr+n_val:]
        y_tr, y_val, y_te = y[:n_tr], y[n_tr:n_tr+n_val], y[n_tr+n_val:]

        # Get similar patients' data
        sim_idxs = find_similar(pi, patient_stats, k=2)
        X_others, y_others = [], []
        for si in sim_idxs:
            sp = patients[si]
            sg, sph = prepare_patient_raw(sp)
            sX, sy, _ = build_enhanced_features(sp, sg, sph)
            if len(sX) > 0:
                X_others.append(sX)
                y_others.append(sy)

        if not X_others:
            continue

        X_other = np.vstack(X_others)
        y_other = np.concatenate(y_others)

        # Fixed weight = 0.3
        X_aug_f = np.vstack([X_tr, X_other])
        y_aug_f = np.concatenate([y_tr, y_other])
        w_aug_f = np.concatenate([np.ones(len(X_tr)), np.full(len(X_other), 0.3)])

        m_fixed = make_optimized_model()
        m_fixed.fit(X_aug_f, y_aug_f, sample_weight=w_aug_f,
                    eval_set=[(X_val, y_val)], verbose=False)
        r2_fixed = compute_r2(y_te, m_fixed.predict(X_te))
        all_fixed.append(r2_fixed)

        # Adaptive: try different weights, pick best on validation
        best_w, best_val_r2 = 0.3, -999
        for w in [0.0, 0.1, 0.2, 0.3, 0.5, 0.7, 1.0]:
            w_aug = np.concatenate([np.ones(len(X_tr)), np.full(len(X_other), w)])
            m_w = make_optimized_model()
            m_w.fit(X_aug_f, y_aug_f, sample_weight=w_aug,
                    eval_set=[(X_val, y_val)], verbose=False)
            val_r2 = compute_r2(y_val, m_w.predict(X_val))
            if val_r2 > best_val_r2:
                best_w, best_val_r2 = w, val_r2

        # Train with best weight
        w_aug_best = np.concatenate([np.ones(len(X_tr)), np.full(len(X_other), best_w)])
        m_adapt = make_optimized_model()
        m_adapt.fit(X_aug_f, y_aug_f, sample_weight=w_aug_best,
                    eval_set=[(X_val, y_val)], verbose=False)
        r2_adapt = compute_r2(y_te, m_adapt.predict(X_te))
        all_adaptive.append(r2_adapt)
        optimal_weights.append(best_w)

        if detail:
            print(f"  {p['name']}: fixed={r2_fixed:.3f} adapt={r2_adapt:.3f} "
                  f"best_w={best_w} Δ={r2_adapt-r2_fixed:+.3f}")

    results['fixed_mean'] = float(np.mean(all_fixed))
    results['adaptive_mean'] = float(np.mean(all_adaptive))
    results['delta'] = float(np.mean(all_adaptive) - np.mean(all_fixed))
    results['wins'] = sum(1 for f, a in zip(all_fixed, all_adaptive) if a > f)
    results['optimal_weights'] = optimal_weights
    results['n_patients'] = len(all_fixed)
    return results


# ============================================================
# EXP-1274: Production Multi-Output (30/60/90 min)
# ============================================================
def exp_1274_production_multi_output(patients, detail=False):
    """Production multi-output predictions at 30/60/90 min with uniform avg stack."""
    results = {'experiment': 'EXP-1274', 'name': 'Production Multi-Output 30/60/90'}
    patient_stats = get_patient_stats(patients)
    horizon_map = {6: '30min', 12: '60min', 18: '90min'}
    horizons = (6, 12, 18)
    all_by_horizon = {h: {'base': [], 'stack': []} for h in horizons}

    for pi, p in enumerate(patients):
        name = p['name']
        glucose, physics = prepare_patient_raw(p)
        X, y_dict, g_cur = build_enhanced_multi_horizon(p, glucose, physics, horizons=horizons)
        if len(X) < 200:
            continue

        tscv = TimeSeriesSplit(n_splits=5)

        for target_h in horizons:
            fold_base, fold_stack = [], []
            for fold, (tr_idx, te_idx) in enumerate(tscv.split(X)):
                vt = int(len(tr_idx) * 0.8)
                tr_train, tr_val = tr_idx[:vt], tr_idx[vt:]

                # Base: single model per horizon
                m_base = make_optimized_model()
                m_base.fit(X[tr_train], y_dict[target_h][tr_train],
                           eval_set=[(X[tr_val], y_dict[target_h][tr_val])], verbose=False)
                fold_base.append(compute_r2(y_dict[target_h][te_idx],
                                            m_base.predict(X[te_idx])))

                # Stack: train all 3 horizons, uniform average targeting this horizon
                y_dict_tr = {h: y_dict[h][tr_train] for h in horizons}
                X_aug, y_aug, w_aug = augment_with_transfer_mh(
                    X[tr_train], y_dict_tr, pi, patients, patient_stats, horizons)

                sub_test = []
                for h in horizons:
                    m_h = make_optimized_model()
                    m_h.fit(X_aug, y_aug[h], sample_weight=w_aug,
                            eval_set=[(X[tr_val], y_dict[h][tr_val])], verbose=False)
                    sub_test.append(m_h.predict(X[te_idx]))

                pred_stack = np.mean(np.column_stack(sub_test), axis=1)
                fold_stack.append(compute_r2(y_dict[target_h][te_idx], pred_stack))

            all_by_horizon[target_h]['base'].append(np.mean(fold_base))
            all_by_horizon[target_h]['stack'].append(np.mean(fold_stack))

        if detail:
            for h in horizons:
                b = all_by_horizon[h]['base'][-1]
                s = all_by_horizon[h]['stack'][-1]
                print(f"  {name} {horizon_map[h]}: base={b:.3f} stack={s:.3f} Δ={s-b:+.3f}")

    for h in horizons:
        label = horizon_map[h]
        results[f'base_{label}'] = float(np.mean(all_by_horizon[h]['base']))
        results[f'stack_{label}'] = float(np.mean(all_by_horizon[h]['stack']))
        results[f'delta_{label}'] = float(
            np.mean(all_by_horizon[h]['stack']) - np.mean(all_by_horizon[h]['base']))
    return results


# ============================================================
# EXP-1275: Temporal Data Augmentation
# ============================================================
def exp_1275_temporal_augmentation(patients, detail=False):
    """Augment by shifting windows 1-2 steps, doubling/tripling data."""
    results = {'experiment': 'EXP-1275', 'name': 'Temporal Augmentation'}
    all_base, all_aug1, all_aug2 = [], [], []

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        X, y, g_cur = build_enhanced_features(p, glucose, physics)
        if len(X) < 200:
            continue

        n = len(X)
        n_tr, n_val = int(n * 0.6), int(n * 0.2)
        X_tr, X_val, X_te = X[:n_tr], X[n_tr:n_tr+n_val], X[n_tr+n_val:]
        y_tr, y_val, y_te = y[:n_tr], y[n_tr:n_tr+n_val], y[n_tr+n_val:]

        # Base
        m_base = make_optimized_model()
        m_base.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=False)
        r2_base = compute_r2(y_te, m_base.predict(X_te))
        all_base.append(r2_base)

        # Aug +1: shift by 1 step (add slightly offset windows)
        if n_tr > 2:
            X_aug1 = np.vstack([X_tr, X_tr[1:]])  # shifted by 1
            y_aug1 = np.concatenate([y_tr, y_tr[1:]])
            m_aug1 = make_optimized_model()
            m_aug1.fit(X_aug1, y_aug1, eval_set=[(X_val, y_val)], verbose=False)
            r2_aug1 = compute_r2(y_te, m_aug1.predict(X_te))
        else:
            r2_aug1 = r2_base
        all_aug1.append(r2_aug1)

        # Aug +noise: add Gaussian noise to glucose features
        noise_X = X_tr.copy()
        noise_X[:, :WINDOW] += np.random.randn(len(X_tr), WINDOW) * 0.01  # ~4mg noise
        X_aug2 = np.vstack([X_tr, noise_X])
        y_aug2 = np.concatenate([y_tr, y_tr])
        m_aug2 = make_optimized_model()
        m_aug2.fit(X_aug2, y_aug2, eval_set=[(X_val, y_val)], verbose=False)
        r2_aug2 = compute_r2(y_te, m_aug2.predict(X_te))
        all_aug2.append(r2_aug2)

        if detail:
            print(f"  {p['name']}: base={r2_base:.3f} shift={r2_aug1:.3f} "
                  f"noise={r2_aug2:.3f}")

    results['base_mean'] = float(np.mean(all_base))
    results['shift_mean'] = float(np.mean(all_aug1))
    results['noise_mean'] = float(np.mean(all_aug2))
    results['delta_shift'] = float(np.mean(all_aug1) - np.mean(all_base))
    results['delta_noise'] = float(np.mean(all_aug2) - np.mean(all_base))
    return results


# ============================================================
# EXP-1276: Error-Aware Prediction Intervals
# ============================================================
def exp_1276_error_aware_pi(patients, detail=False):
    """Widen prediction intervals based on current glucose level."""
    results = {'experiment': 'EXP-1276', 'name': 'Error-Aware Prediction Intervals'}
    all_coverage_flat, all_coverage_adaptive = [], []
    all_width_flat, all_width_adaptive = [], []

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

        # Train quantile models for PI
        m_lo = make_quantile_model(q=0.1)
        m_hi = make_quantile_model(q=0.9)
        m_lo.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=False)
        m_hi.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=False)

        lo_pred = m_lo.predict(X_te)
        hi_pred = m_hi.predict(X_te)

        # Flat PI coverage
        covered_flat = ((y_te >= lo_pred) & (y_te <= hi_pred)).mean()
        width_flat = np.mean((hi_pred - lo_pred) * GLUCOSE_SCALE)
        all_coverage_flat.append(covered_flat)
        all_width_flat.append(width_flat)

        # Adaptive: widen PI at high glucose
        g_mg = g_te * GLUCOSE_SCALE
        scale = np.ones(len(g_te))
        scale[g_mg > 180] = 1.3   # 30% wider at high
        scale[g_mg > 250] = 1.5   # 50% wider at very high
        scale[g_mg < 70] = 1.2    # 20% wider at low

        center = (lo_pred + hi_pred) / 2
        half_width = (hi_pred - lo_pred) / 2
        lo_adapt = center - half_width * scale
        hi_adapt = center + half_width * scale

        covered_adapt = ((y_te >= lo_adapt) & (y_te <= hi_adapt)).mean()
        width_adapt = np.mean((hi_adapt - lo_adapt) * GLUCOSE_SCALE)
        all_coverage_adaptive.append(covered_adapt)
        all_width_adaptive.append(width_adapt)

        if detail:
            print(f"  {p['name']}: flat_cov={covered_flat:.3f} adapt_cov={covered_adapt:.3f} "
                  f"flat_w={width_flat:.0f} adapt_w={width_adapt:.0f}")

    results['flat_coverage'] = float(np.mean(all_coverage_flat))
    results['adaptive_coverage'] = float(np.mean(all_coverage_adaptive))
    results['flat_width'] = float(np.mean(all_width_flat))
    results['adaptive_width'] = float(np.mean(all_width_adaptive))
    results['target_coverage'] = 0.80
    return results


# ============================================================
# EXP-1277: Cross-Patient Generalization (Train 8, Test 3)
# ============================================================
def exp_1277_cross_patient(patients, detail=False):
    """Train on 8 patients, test on 3 held-out patients. Repeat 3x."""
    results = {'experiment': 'EXP-1277', 'name': 'Cross-Patient Generalization'}
    all_individual, all_cross = [], []
    np.random.seed(42)

    n = len(patients)
    if n < 5:
        results['error'] = 'Too few patients'
        return results

    # 3 random splits of train(8)/test(3)
    for trial in range(3):
        perm = np.random.permutation(n)
        test_idxs = perm[:3]
        train_idxs = perm[3:]

        # Build combined training data from train patients
        X_train_all, y_train_all = [], []
        for ti in train_idxs:
            p = patients[ti]
            glucose, physics = prepare_patient_raw(p)
            X_p, y_p, _ = build_enhanced_features(p, glucose, physics)
            if len(X_p) > 0:
                X_train_all.append(X_p)
                y_train_all.append(y_p)

        if not X_train_all:
            continue
        X_train = np.vstack(X_train_all)
        y_train = np.concatenate(y_train_all)

        # Train cross-patient model
        m_cross = make_optimized_model(n_est=500)
        m_cross.fit(X_train, y_train, verbose=False)

        for ti in test_idxs:
            p = patients[ti]
            glucose, physics = prepare_patient_raw(p)
            X_p, y_p, _ = build_enhanced_features(p, glucose, physics)
            if len(X_p) < 100:
                continue

            n_p = len(X_p)
            n_tr_p = int(n_p * 0.6)
            n_val_p = int(n_p * 0.2)
            X_te_p = X_p[n_tr_p+n_val_p:]
            y_te_p = y_p[n_tr_p+n_val_p:]

            # Cross-patient prediction
            r2_cross = compute_r2(y_te_p, m_cross.predict(X_te_p))
            all_cross.append(r2_cross)

            # Individual patient model
            m_ind = make_optimized_model()
            m_ind.fit(X_p[:n_tr_p], y_p[:n_tr_p],
                      eval_set=[(X_p[n_tr_p:n_tr_p+n_val_p], y_p[n_tr_p:n_tr_p+n_val_p])],
                      verbose=False)
            r2_ind = compute_r2(y_te_p, m_ind.predict(X_te_p))
            all_individual.append(r2_ind)

            if detail:
                print(f"  Trial {trial+1} {p['name']}: indiv={r2_ind:.3f} "
                      f"cross={r2_cross:.3f} Δ={r2_cross-r2_ind:+.3f}")

    results['individual_mean'] = float(np.mean(all_individual))
    results['cross_mean'] = float(np.mean(all_cross))
    results['generalization_gap'] = float(np.mean(all_individual) - np.mean(all_cross))
    results['n_evaluations'] = len(all_cross)
    return results


# ============================================================
# EXP-1278: Recent Sample Emphasis
# ============================================================
def exp_1278_recent_emphasis(patients, detail=False):
    """Weight recent training samples higher (temporal decay)."""
    results = {'experiment': 'EXP-1278', 'name': 'Recent Sample Emphasis'}
    all_base, all_recent = [], []

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        X, y, g_cur = build_enhanced_features(p, glucose, physics)
        if len(X) < 200:
            continue

        n = len(X)
        n_tr, n_val = int(n * 0.6), int(n * 0.2)
        X_tr, X_val, X_te = X[:n_tr], X[n_tr:n_tr+n_val], X[n_tr+n_val:]
        y_tr, y_val, y_te = y[:n_tr], y[n_tr:n_tr+n_val], y[n_tr+n_val:]

        # Base: uniform weights
        m_base = make_optimized_model()
        m_base.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=False)
        r2_base = compute_r2(y_te, m_base.predict(X_te))
        all_base.append(r2_base)

        # Recent emphasis: exponential decay (most recent training = weight 1, oldest = 0.3)
        t = np.linspace(0, 1, len(X_tr))
        w_recent = 0.3 + 0.7 * t  # linear from 0.3 to 1.0
        m_recent = make_optimized_model()
        m_recent.fit(X_tr, y_tr, sample_weight=w_recent,
                     eval_set=[(X_val, y_val)], verbose=False)
        r2_recent = compute_r2(y_te, m_recent.predict(X_te))
        all_recent.append(r2_recent)

        if detail:
            print(f"  {p['name']}: base={r2_base:.3f} recent={r2_recent:.3f} "
                  f"Δ={r2_recent-r2_base:+.3f}")

    results['base_mean'] = float(np.mean(all_base))
    results['recent_mean'] = float(np.mean(all_recent))
    results['delta'] = float(np.mean(all_recent) - np.mean(all_base))
    results['wins'] = sum(1 for b, r in zip(all_base, all_recent) if r > b)
    results['n_patients'] = len(all_base)
    return results


# ============================================================
# EXP-1279: Glucose Variability Features
# ============================================================
def exp_1279_variability_features(patients, detail=False):
    """Add glucose variability metrics: CV, range, IQR within window."""
    results = {'experiment': 'EXP-1279', 'name': 'Glucose Variability Features'}
    all_base, all_var = [], []

    for p in patients:
        glucose, physics = prepare_patient_raw(p)
        X, y, g_cur = build_enhanced_features(p, glucose, physics)
        if len(X) < 200:
            continue

        g_win = X[:, :WINDOW]
        # Variability features
        cv = np.std(g_win, axis=1) / (np.mean(g_win, axis=1) + 1e-8)  # coeff of variation
        g_range = np.max(g_win, axis=1) - np.min(g_win, axis=1)  # range
        q25 = np.percentile(g_win, 25, axis=1)
        q75 = np.percentile(g_win, 75, axis=1)
        iqr = q75 - q25
        # Local trend strength (R² of linear fit within window)
        t_vals = np.arange(WINDOW)
        t_mean = t_vals.mean()
        t_var = np.sum((t_vals - t_mean)**2)
        slopes = np.sum((g_win - g_win.mean(axis=1, keepdims=True)) *
                        (t_vals - t_mean), axis=1) / (t_var + 1e-8)
        trend_pred = g_win.mean(axis=1, keepdims=True) + slopes.reshape(-1, 1) * (t_vals - t_mean)
        ss_res = np.sum((g_win - trend_pred)**2, axis=1)
        ss_tot = np.sum((g_win - g_win.mean(axis=1, keepdims=True))**2, axis=1)
        linearity = 1.0 - ss_res / (ss_tot + 1e-8)
        linearity = np.clip(linearity, 0, 1)

        var_feats = np.column_stack([cv, g_range, iqr, slopes, linearity])
        X_var = np.hstack([X, var_feats])

        n = len(X)
        n_tr, n_val = int(n * 0.6), int(n * 0.2)

        m_base = make_optimized_model()
        m_base.fit(X[:n_tr], y[:n_tr],
                   eval_set=[(X[n_tr:n_tr+n_val], y[n_tr:n_tr+n_val])], verbose=False)
        r2_base = compute_r2(y[n_tr+n_val:], m_base.predict(X[n_tr+n_val:]))
        all_base.append(r2_base)

        m_var = make_optimized_model()
        m_var.fit(X_var[:n_tr], y[:n_tr],
                  eval_set=[(X_var[n_tr:n_tr+n_val], y[n_tr:n_tr+n_val])], verbose=False)
        r2_var = compute_r2(y[n_tr+n_val:], m_var.predict(X_var[n_tr+n_val:]))
        all_var.append(r2_var)

        if detail:
            print(f"  {p['name']}: base={r2_base:.3f} var={r2_var:.3f} Δ={r2_var-r2_base:+.3f}")

    results['base_mean'] = float(np.mean(all_base))
    results['var_mean'] = float(np.mean(all_var))
    results['delta'] = float(np.mean(all_var) - np.mean(all_base))
    results['wins'] = sum(1 for b, v in zip(all_base, all_var) if v > b)
    results['n_patients'] = len(all_base)
    return results


# ============================================================
# EXP-1280: Final Production Benchmark (Everything Combined)
# ============================================================
def exp_1280_final_benchmark(patients, detail=False):
    """Complete benchmark: naive vs base vs optimized-transfer vs full-stack."""
    results = {'experiment': 'EXP-1280', 'name': 'Final Production Benchmark'}
    patient_stats = get_patient_stats(patients)
    horizons = (6, 12, 18)
    all_naive, all_base, all_transfer, all_full = [], [], [], []

    for pi, p in enumerate(patients):
        name = p['name']
        glucose, physics = prepare_patient_raw(p)
        X, y_dict, g_cur = build_enhanced_multi_horizon(p, glucose, physics, horizons=horizons)
        if len(X) < 200:
            continue
        y_target = y_dict[12]

        tscv = TimeSeriesSplit(n_splits=5)
        fold_naive, fold_base, fold_transfer, fold_full = [], [], [], []

        for fold, (tr_idx, te_idx) in enumerate(tscv.split(X)):
            vt = int(len(tr_idx) * 0.8)
            tr_train, tr_val = tr_idx[:vt], tr_idx[vt:]
            yt = y_target[te_idx]

            # Naive: predict 0 change
            fold_naive.append(compute_r2(yt, np.zeros_like(yt)))

            # Base: default XGBoost on 60-min
            m_base = make_xgb_sota()
            m_base.fit(X[tr_train], y_target[tr_train],
                       eval_set=[(X[tr_val], y_target[tr_val])], verbose=False)
            fold_base.append(compute_r2(yt, m_base.predict(X[te_idx])))

            # Transfer: optimized XGBoost + transfer augmentation
            sim_idxs = find_similar(pi, patient_stats, k=2)
            all_Xtr = [X[tr_train]]
            all_ytr = [y_target[tr_train]]
            all_wtr = [np.ones(len(tr_train))]
            for si in sim_idxs:
                sp = patients[si]
                sg, sph = prepare_patient_raw(sp)
                sX, sy, _ = build_enhanced_features(sp, sg, sph)
                if len(sX) > 0:
                    all_Xtr.append(sX)
                    all_ytr.append(sy)
                    all_wtr.append(np.full(len(sX), 0.3))
            X_t = np.vstack(all_Xtr)
            y_t = np.concatenate(all_ytr)
            w_t = np.concatenate(all_wtr)
            m_trans = make_optimized_model()
            m_trans.fit(X_t, y_t, sample_weight=w_t,
                        eval_set=[(X[tr_val], y_target[tr_val])], verbose=False)
            fold_transfer.append(compute_r2(yt, m_trans.predict(X[te_idx])))

            # Full stack: transfer + quantile + multi-horizon + uniform avg
            y_dict_tr = {h: y_dict[h][tr_train] for h in horizons}
            X_aug, y_aug, w_aug = augment_with_transfer_mh(
                X[tr_train], y_dict_tr, pi, patients, patient_stats, horizons)

            sub_test = []
            for h in horizons:
                for q in [0.25, 0.5, 0.75]:
                    m_q = make_quantile_model(q=q)
                    m_q.fit(X_aug, y_aug[h], sample_weight=w_aug,
                            eval_set=[(X[tr_val], y_dict[h][tr_val])], verbose=False)
                    sub_test.append(m_q.predict(X[te_idx]))
                m_m = make_optimized_model()
                m_m.fit(X_aug, y_aug[h], sample_weight=w_aug,
                        eval_set=[(X[tr_val], y_dict[h][tr_val])], verbose=False)
                sub_test.append(m_m.predict(X[te_idx]))

            pred_full = np.mean(np.column_stack(sub_test), axis=1)
            fold_full.append(compute_r2(yt, pred_full))

        naive_m = np.mean(fold_naive)
        base_m = np.mean(fold_base)
        trans_m = np.mean(fold_transfer)
        full_m = np.mean(fold_full)
        all_naive.append(naive_m)
        all_base.append(base_m)
        all_transfer.append(trans_m)
        all_full.append(full_m)
        if detail:
            print(f"  {name}: naive={naive_m:.3f} base={base_m:.3f} "
                  f"transfer={trans_m:.3f} full={full_m:.3f}")

    results['naive_mean'] = float(np.mean(all_naive))
    results['base_mean'] = float(np.mean(all_base))
    results['transfer_mean'] = float(np.mean(all_transfer))
    results['full_mean'] = float(np.mean(all_full))
    results['delta_transfer'] = float(np.mean(all_transfer) - np.mean(all_base))
    results['delta_full'] = float(np.mean(all_full) - np.mean(all_base))
    results['full_wins'] = sum(1 for b, f in zip(all_base, all_full) if f > b)
    results['n_patients'] = len(all_base)
    return results


# ============================================================
# Main
# ============================================================
EXPERIMENTS = {
    1271: ('Uniform Full Stack', exp_1271_uniform_full_stack),
    1272: ('Velocity Features', exp_1272_velocity_features),
    1273: ('Adaptive Transfer', exp_1273_adaptive_transfer),
    1274: ('Multi-Output 30/60/90', exp_1274_production_multi_output),
    1275: ('Temporal Augmentation', exp_1275_temporal_augmentation),
    1276: ('Error-Aware PI', exp_1276_error_aware_pi),
    1277: ('Cross-Patient Gen.', exp_1277_cross_patient),
    1278: ('Recent Emphasis', exp_1278_recent_emphasis),
    1279: ('Variability Features', exp_1279_variability_features),
    1280: ('Final Benchmark', exp_1280_final_benchmark),
}


def main():
    parser = argparse.ArgumentParser(description='EXP-1271-1280')
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
                             'optimal_weights'):
                    print(f"  {k}: {v}")
        except Exception as e:
            print(f"  FAILED: {e}")
            import traceback; traceback.print_exc()
            all_results.append({'experiment': f'EXP-{eid}', 'error': str(e)})

    if args.save and all_results:
        save_results(all_results, f'exp_clinical_1271_results')

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
        elif 'delta_full' in r:
            print(f"  {exp} ({name}): full Δ={r['delta_full']:+.3f} ({r.get('full_wins','?')}/{r.get('n_patients','?')} wins)")
        else:
            print(f"  {exp} ({name}): done")


if __name__ == '__main__':
    main()
