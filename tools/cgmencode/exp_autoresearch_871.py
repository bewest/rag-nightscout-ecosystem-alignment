#!/usr/bin/env python3
"""EXP-871–880: Bias Reduction & Advanced Stacking

The remaining gap to oracle is 0.055 (R²=0.558 vs 0.613) and is 99.9%
bias-dominated (EXP-843). Nonlinear models, feature interactions, and
context-splitting have all failed. This wave focuses on bias reduction
through cross-validated stacking, native uncertainty, patient-specific
feature selection, temporal lag exploitation, residual regime decomposition,
quantile ensembles, recursive feature elimination, error-correcting codes,
wavelet decomposition, and a comprehensive benchmark combining all gains.

EXP-871: Cross-Validated Stacking (5-fold CV for Level-0 predictions)
EXP-872: Bayesian Ridge for Native Uncertainty
EXP-873: Patient-Specific Feature Selection (LASSO ablation)
EXP-874: Temporal Stacking (lag predictions from t-5, t-10 as features)
EXP-875: Residual Regime Decomposition (over- vs under-prediction models)
EXP-876: Quantile Regression Ensemble (median + quantile spread features)
EXP-877: Recursive Feature Elimination (greedy backward selection)
EXP-878: Error-Correcting Output Codes (BG bucket classifiers → features)
EXP-879: Wavelet-Based Decomposition (frequency band separation)
EXP-880: Comprehensive Stacking Benchmark (best of all combined)
"""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from exp_metabolic_441 import compute_supply_demand
from exp_metabolic_flux import load_patients

PATIENTS_DIR = Path(__file__).parent.parent.parent / "externals" / "ns-data" / "patients"

EXPERIMENTS = {}


def _get_bg(df):
    col = 'glucose' if 'glucose' in df.columns else 'sgv'
    return df[col]


def _compute_flux(p):
    df = p['df']
    pk = p.get('pk')
    if pk is None:
        pk = np.zeros(len(_get_bg(df)))
    fd = compute_supply_demand(df, pk)
    bg = np.asarray(_get_bg(df), dtype=float)
    n = len(fd['supply'])
    bg = bg[:n]
    supply = fd['supply']
    demand = fd['demand']
    hepatic = fd.get('hepatic', np.full(n, 0.5))
    flux_pred = supply - demand + hepatic + (120.0 - bg) * 0.005
    resid = bg[1:] - (bg[:-1] + flux_pred[:-1])
    return {'bg': bg, 'supply': supply, 'demand': demand,
            'hepatic': hepatic, 'flux_pred': flux_pred, 'resid': resid, 'n': n}


def _get_hours(df, n):
    import pandas as pd
    idx = df.index[:n]
    if isinstance(idx, pd.DatetimeIndex):
        return np.asarray(idx.hour + idx.minute / 60.0, dtype=float)
    return None


def _r2(pred, actual):
    pred = np.asarray(pred, dtype=float)
    actual = np.asarray(actual, dtype=float)
    mask = np.isfinite(pred) & np.isfinite(actual)
    if mask.sum() < 10:
        return float('nan')
    p, a = pred[mask], actual[mask]
    ss_res = np.sum((a - p)**2)
    ss_tot = np.sum((a - np.mean(a))**2)
    if ss_tot < 1e-10:
        return float('nan')
    return 1.0 - ss_res / ss_tot


def _mae(pred, actual):
    pred = np.asarray(pred, dtype=float)
    actual = np.asarray(actual, dtype=float)
    mask = np.isfinite(pred) & np.isfinite(actual)
    if mask.sum() < 10:
        return float('nan')
    return float(np.mean(np.abs(pred[mask] - actual[mask])))


def _build_features_base(fd, hours, n_pred, h_steps):
    bg = fd['bg']
    resid = fd['resid']
    nr = len(resid)
    features = np.zeros((n_pred, 8))
    for i in range(n_pred):
        features[i, 0] = bg[i]
        features[i, 1] = np.sum(fd['supply'][i:i+h_steps])
        features[i, 2] = np.sum(fd['demand'][i:i+h_steps])
        features[i, 3] = np.sum(fd['hepatic'][i:i+h_steps])
        features[i, 4] = resid[i] if i < nr else 0
        if hours is not None and i < len(hours):
            features[i, 5] = np.sin(2 * np.pi * hours[i] / 24.0)
            features[i, 6] = np.cos(2 * np.pi * hours[i] / 24.0)
        features[i, 7] = 1.0
    return features


def _build_enhanced_features(fd, bg, hours, n_pred, h_steps, start=24):
    base = _build_features_base(fd, hours, n_pred, h_steps)
    usable = n_pred - start
    base = base[start:start + usable]

    extra = np.zeros((usable, 8))
    for i in range(usable):
        orig = i + start
        if orig >= 1:
            extra[i, 0] = bg[orig] - bg[orig - 1]
        if orig >= 2:
            extra[i, 1] = bg[orig] - 2 * bg[orig - 1] + bg[orig - 2]
        if orig >= 6:
            extra[i, 2] = bg[orig - 6]
        if orig >= 12:
            extra[i, 3] = bg[orig - 12]
        w = bg[max(0, orig - 24):orig + 1]
        vw = w[np.isfinite(w)]
        if len(vw) >= 3:
            extra[i, 4] = np.mean(vw)
            extra[i, 5] = np.std(vw)
            x = np.arange(len(vw))
            extra[i, 6] = np.polyfit(x, vw, 1)[0]
        extra[i, 7] = bg[orig] ** 2 / 1000.0

    return np.hstack([base, extra]), usable


def _ridge_predict(X_train, y_train, X_val, lam=1.0):
    XtX = X_train.T @ X_train + lam * np.eye(X_train.shape[1])
    try:
        w = np.linalg.solve(XtX, X_train.T @ y_train)
        return X_val @ w, w
    except np.linalg.LinAlgError:
        return np.full(X_val.shape[0], np.nan), None


def register(exp_id, name):
    def decorator(func):
        EXPERIMENTS[exp_id] = {'name': name, 'func': func}
        return func
    return decorator


def _train_horizon_models(fd, bg, hours, nr, start, usable, split, horizons):
    """Train models at multiple horizons and return their predictions."""
    predictions = {}
    weights = {}

    for h in horizons:
        n_pred_h = nr - h
        if n_pred_h - start < usable:
            continue

        actual_h = bg[h + 1 + start: h + 1 + start + usable]
        feat_h = _build_features_base(fd, hours, n_pred_h, h)
        feat_h = feat_h[start:start + usable]

        X_tr_h = feat_h[:split]
        y_tr_h = actual_h[:split]
        valid_h = np.isfinite(y_tr_h) & np.all(np.isfinite(X_tr_h), axis=1)

        if valid_h.sum() < 50:
            continue

        _, w_h = _ridge_predict(X_tr_h[valid_h], y_tr_h[valid_h], X_tr_h[:1], lam=0.1)
        if w_h is not None:
            predictions[h] = feat_h @ w_h
            weights[h] = w_h

    return predictions, weights


def _prepare_patient(p, h_steps=12, start=24):
    """Prepare standard patient data dict. Returns None if insufficient data."""
    fd = _compute_flux(p)
    bg = fd['bg']
    n = fd['n']
    hours = _get_hours(p['df'], n)
    nr = len(fd['resid'])
    n_pred = nr - h_steps
    usable = n_pred - start
    if usable < 200:
        return None

    actual = bg[h_steps + 1 + start: h_steps + 1 + start + usable]
    features, _ = _build_enhanced_features(fd, bg, hours, n_pred, h_steps, start)
    split = int(0.8 * usable)

    return {
        'fd': fd, 'bg': bg, 'hours': hours, 'nr': nr,
        'n_pred': n_pred, 'usable': usable, 'actual': actual,
        'features': features, 'split': split, 'name': p.get('name', '?'),
    }


# ── EXP-871: Cross-Validated Stacking ────────────────────────────────────────

@register('EXP-871', 'Cross-Validated Stacking')
def exp_871(patients, detail=False):
    """Use 5-fold CV for Level-0 predictions to reduce stacking overfitting.

    Current stacking (EXP-862) trains Level-0 on the training set and evaluates
    on validation. If Level-0 predictions overfit the training data, the Level-2
    meta-learner receives biased inputs. Using K-fold CV for Level-0 ensures the
    meta-learner trains on out-of-fold predictions, better matching test-time
    conditions.
    """
    h_steps = 12
    lam = 10.0
    start = 24
    horizons = [1, 3, 6, 12]  # 5/15/30/60min
    n_folds = 5

    naive_r2s, cv_stack_r2s = [], []
    per_patient = {}

    for p in patients:
        d = _prepare_patient(p, h_steps, start)
        if d is None:
            continue

        features, actual, split, usable = d['features'], d['actual'], d['split'], d['usable']
        fd, bg, hours, nr = d['fd'], d['bg'], d['hours'], d['nr']
        y_tr, y_val = actual[:split], actual[split:]

        # Naive stacking baseline (same as EXP-862)
        h_preds, _ = _train_horizon_models(fd, bg, hours, nr, start, usable, split, horizons)
        if len(h_preds) < 3:
            continue

        stack_feats = np.column_stack([h_preds[h] for h in sorted(h_preds)])
        combined_naive = np.hstack([features, stack_feats])

        X_tr_n, X_val_n = combined_naive[:split], combined_naive[split:]
        valid_tr_n = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_n), axis=1)
        valid_val_n = np.isfinite(y_val) & np.all(np.isfinite(X_val_n), axis=1)

        pred_naive, _ = _ridge_predict(X_tr_n[valid_tr_n], y_tr[valid_tr_n],
                                        X_val_n, lam=lam * 5)
        r2_naive = _r2(pred_naive[valid_val_n], y_val[valid_val_n])

        # CV stacking: generate out-of-fold Level-0 predictions on train set
        fold_size = split // n_folds
        oof_preds = {}
        for h in sorted(h_preds):
            oof_preds[h] = np.full(split, np.nan)

        for fold_i in range(n_folds):
            fold_start = fold_i * fold_size
            fold_end = min((fold_i + 1) * fold_size, split)
            train_idx = np.concatenate([np.arange(0, fold_start),
                                         np.arange(fold_end, split)])
            val_idx = np.arange(fold_start, fold_end)

            for h in sorted(h_preds):
                n_pred_h = nr - h
                if n_pred_h - start < usable:
                    continue
                actual_h = bg[h + 1 + start: h + 1 + start + usable]
                feat_h = _build_features_base(fd, hours, n_pred_h, h)
                feat_h = feat_h[start:start + usable]

                X_fold_tr = feat_h[train_idx]
                y_fold_tr = actual_h[train_idx]
                X_fold_val = feat_h[val_idx]

                valid_fold = np.isfinite(y_fold_tr) & np.all(np.isfinite(X_fold_tr), axis=1)
                if valid_fold.sum() < 30:
                    continue

                pred_fold, _ = _ridge_predict(X_fold_tr[valid_fold], y_fold_tr[valid_fold],
                                               X_fold_val, lam=0.1)
                oof_preds[h][val_idx] = pred_fold

        # Build CV-based stack features for training
        oof_stack = np.column_stack([oof_preds[h] for h in sorted(oof_preds)])
        cv_combined_tr = np.hstack([features[:split], oof_stack])

        # For validation, use full-train horizon predictions (same as naive)
        cv_combined_val = X_val_n

        valid_tr_cv = np.isfinite(y_tr) & np.all(np.isfinite(cv_combined_tr), axis=1)
        valid_val_cv = np.isfinite(y_val) & np.all(np.isfinite(cv_combined_val), axis=1)

        if valid_tr_cv.sum() < 50:
            continue

        pred_cv, _ = _ridge_predict(cv_combined_tr[valid_tr_cv], y_tr[valid_tr_cv],
                                     cv_combined_val, lam=lam * 5)
        r2_cv = _r2(pred_cv[valid_val_cv], y_val[valid_val_cv])

        if np.isfinite(r2_naive) and np.isfinite(r2_cv):
            naive_r2s.append(r2_naive)
            cv_stack_r2s.append(r2_cv)
            if detail:
                per_patient[d['name']] = {
                    'naive': round(r2_naive, 3), 'cv': round(r2_cv, 3)}

    results = {
        'naive_stacking': round(float(np.mean(naive_r2s)), 3) if naive_r2s else None,
        'cv_stacking': round(float(np.mean(cv_stack_r2s)), 3) if cv_stack_r2s else None,
        'improvement': round(float(np.mean(cv_stack_r2s) - np.mean(naive_r2s)), 3) if naive_r2s else None,
        'n_patients': len(naive_r2s),
    }
    if detail:
        results['per_patient'] = per_patient

    return {
        'status': 'pass',
        'detail': f"naive={results['naive_stacking']}, cv={results['cv_stacking']}, Δ={results['improvement']:+.3f}",
        'results': results,
    }


# ── EXP-872: Bayesian Ridge for Native Uncertainty ───────────────────────────

@register('EXP-872', 'Bayesian Ridge Native Uncertainty')
def exp_872(patients, detail=False):
    """Replace ridge with BayesianRidge from sklearn for native uncertainty.

    BayesianRidge provides posterior variance for each prediction, giving a
    principled uncertainty estimate. Compare: (a) point prediction R², (b)
    calibration of uncertainty (do high-uncertainty points have larger errors?),
    (c) whether uncertainty can be used as a feature to improve predictions.
    """
    from sklearn.linear_model import BayesianRidge, Ridge

    h_steps = 12
    start = 24

    ridge_r2s, bayes_r2s, bayes_unc_r2s = [], [], []
    calibration_stats = []

    for p in patients:
        d = _prepare_patient(p, h_steps, start)
        if d is None:
            continue

        features, actual, split = d['features'], d['actual'], d['split']
        X_tr, X_val = features[:split], features[split:]
        y_tr, y_val = actual[:split], actual[split:]

        valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        valid_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)

        if valid_tr.sum() < 50 or valid_val.sum() < 20:
            continue

        X_tr_v, y_tr_v = X_tr[valid_tr], y_tr[valid_tr]
        X_val_v, y_val_v = X_val[valid_val], y_val[valid_val]

        # Standard ridge baseline
        ridge = Ridge(alpha=30.0)
        ridge.fit(X_tr_v, y_tr_v)
        pred_ridge = ridge.predict(X_val_v)
        r2_ridge = _r2(pred_ridge, y_val_v)

        # Bayesian ridge
        bay = BayesianRidge(max_iter=300, tol=1e-4)
        bay.fit(X_tr_v, y_tr_v)
        pred_bay, pred_std = bay.predict(X_val_v, return_std=True)
        r2_bay = _r2(pred_bay, y_val_v)

        # Calibration: bin by predicted uncertainty, measure actual error
        abs_err = np.abs(y_val_v - pred_bay)
        n_bins = 5
        bin_edges = np.percentile(pred_std, np.linspace(0, 100, n_bins + 1))
        bin_mae = []
        bin_unc = []
        for bi in range(n_bins):
            mask_bin = (pred_std >= bin_edges[bi]) & (pred_std < bin_edges[bi + 1] + 1e-10)
            if mask_bin.sum() > 5:
                bin_mae.append(float(np.mean(abs_err[mask_bin])))
                bin_unc.append(float(np.mean(pred_std[mask_bin])))
        # Correlation between binned uncertainty and binned MAE
        if len(bin_mae) >= 3:
            cal_corr = float(np.corrcoef(bin_unc, bin_mae)[0, 1])
        else:
            cal_corr = float('nan')

        # Use uncertainty as an additional feature
        bay_full = BayesianRidge(max_iter=300, tol=1e-4)
        bay_full.fit(X_tr_v, y_tr_v)
        pred_tr_bay, std_tr_bay = bay_full.predict(X_tr_v, return_std=True)
        pred_val_bay, std_val_bay = bay_full.predict(X_val_v, return_std=True)

        # Augment features with uncertainty and predicted value
        X_tr_aug = np.column_stack([X_tr_v, std_tr_bay, pred_tr_bay])
        X_val_aug = np.column_stack([X_val_v, std_val_bay, pred_val_bay])

        ridge_aug = Ridge(alpha=30.0)
        ridge_aug.fit(X_tr_aug, y_tr_v)
        pred_aug = ridge_aug.predict(X_val_aug)
        r2_aug = _r2(pred_aug, y_val_v)

        if np.isfinite(r2_ridge) and np.isfinite(r2_bay):
            ridge_r2s.append(r2_ridge)
            bayes_r2s.append(r2_bay)
            if np.isfinite(r2_aug):
                bayes_unc_r2s.append(r2_aug)
            if np.isfinite(cal_corr):
                calibration_stats.append(cal_corr)

    results = {
        'ridge_baseline': round(float(np.mean(ridge_r2s)), 3) if ridge_r2s else None,
        'bayesian_ridge': round(float(np.mean(bayes_r2s)), 3) if bayes_r2s else None,
        'bayes_unc_as_feature': round(float(np.mean(bayes_unc_r2s)), 3) if bayes_unc_r2s else None,
        'improvement_bayes': round(float(np.mean(bayes_r2s) - np.mean(ridge_r2s)), 3) if ridge_r2s else None,
        'improvement_unc_feat': round(float(np.mean(bayes_unc_r2s) - np.mean(ridge_r2s)), 3) if bayes_unc_r2s else None,
        'mean_calibration_corr': round(float(np.mean(calibration_stats)), 3) if calibration_stats else None,
        'n_patients': len(ridge_r2s),
    }

    return {
        'status': 'pass',
        'detail': (f"ridge={results['ridge_baseline']}, bayes={results['bayesian_ridge']}, "
                   f"+unc_feat={results['bayes_unc_as_feature']}, cal_corr={results['mean_calibration_corr']}"),
        'results': results,
    }


# ── EXP-873: Patient-Specific Feature Selection ─────────────────────────────

@register('EXP-873', 'Patient-Specific Feature Selection')
def exp_873(patients, detail=False):
    """For each patient, use LASSO to find optimal feature subset.

    Patient h consistently degrades with more features (data quality issue).
    Rather than one feature set for all patients, let LASSO select features
    per-patient. Compare: (a) full 16 features, (b) LASSO-selected subset,
    (c) cross-validated LASSO alpha selection.
    """
    from sklearn.linear_model import Lasso, LassoCV, Ridge

    h_steps = 12
    start = 24

    full_r2s, lasso_r2s, lassocv_r2s = [], [], []
    feature_counts = []
    per_patient = {}

    for p in patients:
        d = _prepare_patient(p, h_steps, start)
        if d is None:
            continue

        features, actual, split = d['features'], d['actual'], d['split']
        X_tr, X_val = features[:split], features[split:]
        y_tr, y_val = actual[:split], actual[split:]

        valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        valid_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)

        if valid_tr.sum() < 50 or valid_val.sum() < 20:
            continue

        X_tr_v, y_tr_v = X_tr[valid_tr], y_tr[valid_tr]
        X_val_v, y_val_v = X_val[valid_val], y_val[valid_val]

        # Standardize for LASSO
        mu = X_tr_v.mean(axis=0)
        sigma = X_tr_v.std(axis=0)
        sigma[sigma < 1e-10] = 1.0
        X_tr_s = (X_tr_v - mu) / sigma
        X_val_s = (X_val_v - mu) / sigma

        # Full 16-feature ridge baseline
        ridge = Ridge(alpha=30.0)
        ridge.fit(X_tr_v, y_tr_v)
        pred_full = ridge.predict(X_val_v)
        r2_full = _r2(pred_full, y_val_v)

        # Fixed-alpha LASSO for feature selection
        lasso = Lasso(alpha=1.0, max_iter=5000)
        lasso.fit(X_tr_s, y_tr_v)
        selected = np.abs(lasso.coef_) > 1e-8
        n_selected = int(selected.sum())

        if n_selected >= 2:
            # Retrain ridge on selected features only
            ridge_sel = Ridge(alpha=30.0)
            ridge_sel.fit(X_tr_v[:, selected], y_tr_v)
            pred_lasso = ridge_sel.predict(X_val_v[:, selected])
            r2_lasso = _r2(pred_lasso, y_val_v)
        else:
            r2_lasso = r2_full
            n_selected = features.shape[1]

        # Cross-validated LASSO alpha
        try:
            lasso_cv = LassoCV(cv=5, max_iter=5000, n_alphas=20)
            lasso_cv.fit(X_tr_s, y_tr_v)
            selected_cv = np.abs(lasso_cv.coef_) > 1e-8
            n_sel_cv = int(selected_cv.sum())

            if n_sel_cv >= 2:
                ridge_cv = Ridge(alpha=30.0)
                ridge_cv.fit(X_tr_v[:, selected_cv], y_tr_v)
                pred_cv = ridge_cv.predict(X_val_v[:, selected_cv])
                r2_cv = _r2(pred_cv, y_val_v)
            else:
                r2_cv = r2_full
        except Exception:
            r2_cv = r2_full

        if np.isfinite(r2_full) and np.isfinite(r2_lasso) and np.isfinite(r2_cv):
            full_r2s.append(r2_full)
            lasso_r2s.append(r2_lasso)
            lassocv_r2s.append(r2_cv)
            feature_counts.append(n_selected)
            if detail:
                per_patient[d['name']] = {
                    'full': round(r2_full, 3),
                    'lasso': round(r2_lasso, 3),
                    'lasso_cv': round(r2_cv, 3),
                    'n_features': n_selected,
                }

    results = {
        'full_16feat': round(float(np.mean(full_r2s)), 3) if full_r2s else None,
        'lasso_selected': round(float(np.mean(lasso_r2s)), 3) if lasso_r2s else None,
        'lasso_cv_selected': round(float(np.mean(lassocv_r2s)), 3) if lassocv_r2s else None,
        'improvement_lasso': round(float(np.mean(lasso_r2s) - np.mean(full_r2s)), 3) if full_r2s else None,
        'improvement_cv': round(float(np.mean(lassocv_r2s) - np.mean(full_r2s)), 3) if full_r2s else None,
        'mean_features_selected': round(float(np.mean(feature_counts)), 1) if feature_counts else None,
        'n_patients': len(full_r2s),
    }
    if detail:
        results['per_patient'] = per_patient

    return {
        'status': 'pass',
        'detail': (f"full={results['full_16feat']}, lasso={results['lasso_selected']}, "
                   f"cv={results['lasso_cv_selected']}, mean_feats={results['mean_features_selected']}"),
        'results': results,
    }


# ── EXP-874: Temporal Stacking (Lag Predictions) ────────────────────────────

@register('EXP-874', 'Temporal Stacking Lag Predictions')
def exp_874(patients, detail=False):
    """Use predictions from t-5min and t-10min as features (no leakage).

    At time t, the prediction made at t-5min was computed from data available at
    t-5min (features prior to t-5min), predicting BG at t-5+60=t+55. Similarly,
    the prediction from t-10min targeted t+50. These stale predictions were made
    with DIFFERENT information windows and may complement the fresh prediction.

    Implementation: first train a base model, then compute predictions at every
    timestep. For each validation point at index i, use the base prediction
    computed at i-1 (targeting i+h-1) and i-2 (targeting i+h-2) as extra features.
    These are from training-time model applied to different input points.
    """
    h_steps = 12
    lam = 10.0
    start = 24

    base_r2s, lag1_r2s, lag2_r2s = [], [], []

    for p in patients:
        d = _prepare_patient(p, h_steps, start)
        if d is None:
            continue

        features, actual, split, usable = d['features'], d['actual'], d['split'], d['usable']
        y_tr, y_val = actual[:split], actual[split:]

        valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(features[:split]), axis=1)
        valid_val = np.isfinite(y_val) & np.all(np.isfinite(features[split:]), axis=1)

        if valid_tr.sum() < 50:
            continue

        # Train base model on training set
        X_tr_v, y_tr_v = features[:split][valid_tr], y_tr[valid_tr]
        _, w_base = _ridge_predict(X_tr_v, y_tr_v, X_tr_v[:1], lam=lam * 3)
        if w_base is None:
            continue

        # Compute base predictions for ALL samples (train + val)
        all_preds = features @ w_base

        # Base R²
        pred_base_val = all_preds[split:]
        r2_base = _r2(pred_base_val[valid_val], y_val[valid_val])

        # Lag-1: prediction from 1 step ago (features at i-1)
        # For sample i, the model applied to features[i-1] yields all_preds[i-1]
        lag1_pred = np.full(usable, np.nan)
        lag1_pred[1:] = all_preds[:-1]

        # Lag-2: prediction from 2 steps ago
        lag2_pred = np.full(usable, np.nan)
        lag2_pred[2:] = all_preds[:-2]

        # Augment with lag-1 only
        feat_lag1 = np.column_stack([features, lag1_pred])
        X_tr_l1, X_val_l1 = feat_lag1[:split], feat_lag1[split:]
        valid_tr_l1 = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_l1), axis=1)
        valid_val_l1 = np.isfinite(y_val) & np.all(np.isfinite(X_val_l1), axis=1)

        if valid_tr_l1.sum() >= 50:
            pred_l1, _ = _ridge_predict(X_tr_l1[valid_tr_l1], y_tr[valid_tr_l1],
                                         X_val_l1, lam=lam * 3)
            r2_l1 = _r2(pred_l1[valid_val_l1], y_val[valid_val_l1])
        else:
            r2_l1 = float('nan')

        # Augment with lag-1 + lag-2 + diff
        lag_diff = lag1_pred - lag2_pred
        feat_lag2 = np.column_stack([features, lag1_pred, lag2_pred, lag_diff])
        X_tr_l2, X_val_l2 = feat_lag2[:split], feat_lag2[split:]
        valid_tr_l2 = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_l2), axis=1)
        valid_val_l2 = np.isfinite(y_val) & np.all(np.isfinite(X_val_l2), axis=1)

        if valid_tr_l2.sum() >= 50:
            pred_l2, _ = _ridge_predict(X_tr_l2[valid_tr_l2], y_tr[valid_tr_l2],
                                         X_val_l2, lam=lam * 4)
            r2_l2 = _r2(pred_l2[valid_val_l2], y_val[valid_val_l2])
        else:
            r2_l2 = float('nan')

        if np.isfinite(r2_base):
            base_r2s.append(r2_base)
            if np.isfinite(r2_l1):
                lag1_r2s.append(r2_l1)
            if np.isfinite(r2_l2):
                lag2_r2s.append(r2_l2)

    results = {
        'base': round(float(np.mean(base_r2s)), 3) if base_r2s else None,
        'with_lag1': round(float(np.mean(lag1_r2s)), 3) if lag1_r2s else None,
        'with_lag1_lag2': round(float(np.mean(lag2_r2s)), 3) if lag2_r2s else None,
        'improvement_lag1': round(float(np.mean(lag1_r2s) - np.mean(base_r2s)), 3) if lag1_r2s and base_r2s else None,
        'improvement_lag2': round(float(np.mean(lag2_r2s) - np.mean(base_r2s)), 3) if lag2_r2s and base_r2s else None,
        'n_patients': len(base_r2s),
    }

    return {
        'status': 'pass',
        'detail': (f"base={results['base']}, +lag1={results['with_lag1']}, "
                   f"+lag1+2={results['with_lag1_lag2']}"),
        'results': results,
    }


# ── EXP-875: Residual Regime Decomposition ───────────────────────────────────

@register('EXP-875', 'Residual Regime Decomposition')
def exp_875(patients, detail=False):
    """Fit separate models for recent over- vs under-prediction regimes.

    Error is bias-dominated. If the model consistently under-predicts (positive
    residual sign) vs over-predicts (negative), the bias structure differs. Use
    the sign and magnitude of recent prediction residuals (computed on training
    data using the trained model) as regime indicators. Train regime-specific
    correction layers.
    """
    h_steps = 12
    lam = 10.0
    start = 24

    base_r2s, regime_r2s, correction_r2s = [], [], []

    for p in patients:
        d = _prepare_patient(p, h_steps, start)
        if d is None:
            continue

        features, actual, split, usable = d['features'], d['actual'], d['split'], d['usable']
        y_tr, y_val = actual[:split], actual[split:]

        valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(features[:split]), axis=1)
        valid_val = np.isfinite(y_val) & np.all(np.isfinite(features[split:]), axis=1)

        if valid_tr.sum() < 50:
            continue

        X_tr_v, y_tr_v = features[:split][valid_tr], y_tr[valid_tr]

        # Base model
        pred_base_all, w_base = _ridge_predict(X_tr_v, y_tr_v, features, lam=lam * 3)
        if w_base is None:
            continue

        pred_val = pred_base_all[split:]
        r2_base = _r2(pred_val[valid_val], y_val[valid_val])

        # Compute training residuals
        pred_tr = pred_base_all[:split]
        train_resid = actual[:split] - pred_tr

        # Rolling residual sign and magnitude (window=12 = 1 hour lookback)
        window = 12
        resid_sign = np.zeros(usable)
        resid_mag = np.zeros(usable)
        for i in range(usable):
            lo = max(0, i - window)
            r_window = train_resid[lo:i] if i <= split else train_resid[max(0, split - window):split]
            valid_w = r_window[np.isfinite(r_window)]
            if len(valid_w) > 0:
                resid_sign[i] = np.sign(np.mean(valid_w))
                resid_mag[i] = np.mean(np.abs(valid_w))

        # Regime-specific models: split training data by residual sign
        under_mask = resid_sign[:split] > 0  # model under-predicts
        over_mask = resid_sign[:split] < 0   # model over-predicts

        under_valid = under_mask & valid_tr
        over_valid = over_mask & valid_tr

        # Train regime-specific models
        if under_valid.sum() >= 30 and over_valid.sum() >= 30:
            _, w_under = _ridge_predict(features[:split][under_valid], y_tr[under_valid],
                                         features[:1], lam=lam * 3)
            _, w_over = _ridge_predict(features[:split][over_valid], y_tr[over_valid],
                                        features[:1], lam=lam * 3)

            if w_under is not None and w_over is not None:
                # For validation, select model based on recent residual sign
                pred_regime = np.zeros(usable - split)
                for i in range(usable - split):
                    vi = split + i
                    if resid_sign[vi] > 0:
                        pred_regime[i] = features[vi] @ w_under
                    elif resid_sign[vi] < 0:
                        pred_regime[i] = features[vi] @ w_over
                    else:
                        pred_regime[i] = pred_val[i]

                r2_regime = _r2(pred_regime[valid_val], y_val[valid_val])
            else:
                r2_regime = float('nan')
        else:
            r2_regime = float('nan')

        # Correction approach: add residual features to main model
        resid_feats = np.column_stack([resid_sign, resid_mag])
        combined = np.hstack([features, resid_feats])
        X_tr_c, X_val_c = combined[:split], combined[split:]
        valid_tr_c = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_c), axis=1)
        valid_val_c = np.isfinite(y_val) & np.all(np.isfinite(X_val_c), axis=1)

        pred_corr, _ = _ridge_predict(X_tr_c[valid_tr_c], y_tr[valid_tr_c],
                                       X_val_c, lam=lam * 3)
        r2_corr = _r2(pred_corr[valid_val_c], y_val[valid_val_c])

        if np.isfinite(r2_base):
            base_r2s.append(r2_base)
            if np.isfinite(r2_regime):
                regime_r2s.append(r2_regime)
            if np.isfinite(r2_corr):
                correction_r2s.append(r2_corr)

    results = {
        'base': round(float(np.mean(base_r2s)), 3) if base_r2s else None,
        'regime_switching': round(float(np.mean(regime_r2s)), 3) if regime_r2s else None,
        'residual_correction': round(float(np.mean(correction_r2s)), 3) if correction_r2s else None,
        'improvement_regime': round(float(np.mean(regime_r2s) - np.mean(base_r2s)), 3) if regime_r2s and base_r2s else None,
        'improvement_correction': round(float(np.mean(correction_r2s) - np.mean(base_r2s)), 3) if correction_r2s and base_r2s else None,
        'n_patients': len(base_r2s),
    }

    return {
        'status': 'pass',
        'detail': (f"base={results['base']}, regime={results['regime_switching']}, "
                   f"correction={results['residual_correction']}"),
        'results': results,
    }


# ── EXP-876: Quantile Regression Ensemble ────────────────────────────────────

@register('EXP-876', 'Quantile Regression Ensemble')
def exp_876(patients, detail=False):
    """Train ridge at quantiles [0.1, 0.25, 0.5, 0.75, 0.9] using pinball loss.

    Use quantile spread (q90-q10) as uncertainty, skewness (q75-q50 vs q50-q25)
    as directional risk feature. Combine quantile predictions + spread as
    features for a meta-model.

    Quantile regression via iteratively reweighted least squares (IRLS):
    for quantile tau, minimize sum of rho_tau(y - Xw) where
    rho_tau(u) = u*(tau - I(u<0)).
    """
    h_steps = 12
    lam = 10.0
    start = 24
    quantiles = [0.1, 0.25, 0.5, 0.75, 0.9]

    def _quantile_ridge(X_tr, y_tr, X_val, tau, lam_q=1.0, n_iter=30):
        """Fit quantile regression via IRLS (vectorized, no dense diag)."""
        n, p = X_tr.shape
        w = np.linalg.lstsq(X_tr, y_tr, rcond=None)[0]
        for _ in range(n_iter):
            resid = y_tr - X_tr @ w
            weights = np.where(resid >= 0, tau, 1.0 - tau)
            weights = np.maximum(weights, 1e-6)
            Xw = X_tr * np.sqrt(weights)[:, None]
            XtWX = Xw.T @ Xw + lam_q * np.eye(p)
            try:
                w = np.linalg.solve(XtWX, X_tr.T @ (weights * y_tr))
            except np.linalg.LinAlgError:
                break
        return X_val @ w, w

    base_r2s, median_r2s, meta_r2s = [], [], []

    for p in patients:
        d = _prepare_patient(p, h_steps, start)
        if d is None:
            continue

        features, actual, split = d['features'], d['actual'], d['split']
        X_tr, X_val = features[:split], features[split:]
        y_tr, y_val = actual[:split], actual[split:]

        valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        valid_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)

        if valid_tr.sum() < 50 or valid_val.sum() < 20:
            continue

        X_tr_v, y_tr_v = X_tr[valid_tr], y_tr[valid_tr]
        X_val_v, y_val_v = X_val[valid_val], y_val[valid_val]

        # Ridge baseline
        pred_ridge, _ = _ridge_predict(X_tr_v, y_tr_v, X_val_v, lam=lam * 3)
        r2_ridge = _r2(pred_ridge, y_val_v)

        # Quantile predictions
        q_preds_tr = {}
        q_preds_val = {}
        for tau in quantiles:
            pred_val_q, w_q = _quantile_ridge(X_tr_v, y_tr_v, X_val_v, tau, lam_q=lam)
            pred_tr_q = X_tr_v @ w_q if w_q is not None else np.full(len(X_tr_v), np.nan)
            q_preds_tr[tau] = pred_tr_q
            q_preds_val[tau] = pred_val_q

        # Median prediction R²
        r2_median = _r2(q_preds_val[0.5], y_val_v)

        # Build quantile-derived features
        q_vals_tr = np.column_stack([q_preds_tr[tau] for tau in quantiles])
        q_vals_val = np.column_stack([q_preds_val[tau] for tau in quantiles])

        # Spread: q90 - q10
        spread_tr = q_preds_tr[0.9] - q_preds_tr[0.1]
        spread_val = q_preds_val[0.9] - q_preds_val[0.1]

        # Skewness: (q75-q50) - (q50-q25)
        skew_tr = (q_preds_tr[0.75] - q_preds_tr[0.5]) - (q_preds_tr[0.5] - q_preds_tr[0.25])
        skew_val = (q_preds_val[0.75] - q_preds_val[0.5]) - (q_preds_val[0.5] - q_preds_val[0.25])

        meta_tr = np.column_stack([X_tr_v, q_vals_tr, spread_tr, skew_tr])
        meta_val = np.column_stack([X_val_v, q_vals_val, spread_val, skew_val])

        valid_meta_tr = np.all(np.isfinite(meta_tr), axis=1)
        valid_meta_val = np.all(np.isfinite(meta_val), axis=1)

        if valid_meta_tr.sum() >= 50 and valid_meta_val.sum() >= 10:
            pred_meta, _ = _ridge_predict(meta_tr[valid_meta_tr], y_tr_v[valid_meta_tr],
                                           meta_val, lam=lam * 5)
            r2_meta = _r2(pred_meta[valid_meta_val], y_val_v[valid_meta_val])
        else:
            r2_meta = float('nan')

        if np.isfinite(r2_ridge):
            base_r2s.append(r2_ridge)
            if np.isfinite(r2_median):
                median_r2s.append(r2_median)
            if np.isfinite(r2_meta):
                meta_r2s.append(r2_meta)

    results = {
        'ridge_baseline': round(float(np.mean(base_r2s)), 3) if base_r2s else None,
        'quantile_median': round(float(np.mean(median_r2s)), 3) if median_r2s else None,
        'quantile_meta': round(float(np.mean(meta_r2s)), 3) if meta_r2s else None,
        'improvement_median': round(float(np.mean(median_r2s) - np.mean(base_r2s)), 3) if median_r2s and base_r2s else None,
        'improvement_meta': round(float(np.mean(meta_r2s) - np.mean(base_r2s)), 3) if meta_r2s and base_r2s else None,
        'n_patients': len(base_r2s),
    }

    return {
        'status': 'pass',
        'detail': (f"ridge={results['ridge_baseline']}, median={results['quantile_median']}, "
                   f"meta={results['quantile_meta']}"),
        'results': results,
    }


# ── EXP-877: Recursive Feature Elimination ──────────────────────────────────

@register('EXP-877', 'Recursive Feature Elimination')
def exp_877(patients, detail=False):
    """Systematically remove least-important features from the 16-feature set.

    Greedy backward elimination: start with all 16 features, remove one at a
    time (the one whose removal LEAST reduces R²), stop when R² drops below
    threshold. This finds the minimum feature set that preserves performance.
    """
    h_steps = 12
    lam = 10.0
    start = 24

    FEATURE_NAMES = [
        'bg', 'supply_sum', 'demand_sum', 'hepatic_sum', 'resid',
        'sin_h', 'cos_h', 'bias',
        'velocity', 'accel', 'bg_lag30', 'bg_lag60',
        'bg_mean_2h', 'bg_std_2h', 'bg_slope_2h', 'bg_sq',
    ]

    full_r2s = []
    optimal_r2s = []
    feature_survival = np.zeros(16)  # how often each feature survives
    optimal_sizes = []
    per_patient = {}

    for p in patients:
        d = _prepare_patient(p, h_steps, start)
        if d is None:
            continue

        features, actual, split = d['features'], d['actual'], d['split']
        y_tr, y_val = actual[:split], actual[split:]

        valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(features[:split]), axis=1)
        valid_val = np.isfinite(y_val) & np.all(np.isfinite(features[split:]), axis=1)

        if valid_tr.sum() < 50 or valid_val.sum() < 20:
            continue

        n_feats = features.shape[1]
        active = list(range(n_feats))

        def _eval_subset(cols):
            X_tr_s = features[:split][:, cols]
            X_val_s = features[split:][:, cols]
            vt = valid_tr & np.all(np.isfinite(X_tr_s), axis=1)
            vv = valid_val & np.all(np.isfinite(X_val_s), axis=1)
            if vt.sum() < 30:
                return float('nan')
            pred, _ = _ridge_predict(X_tr_s[vt], y_tr[vt], X_val_s, lam=lam * 3)
            return _r2(pred[vv], y_val[vv])

        # Full baseline
        r2_full = _eval_subset(active)
        if not np.isfinite(r2_full):
            continue

        # Greedy backward elimination
        best_r2 = r2_full
        best_active = list(active)
        elimination_log = [(len(active), r2_full)]

        while len(active) > 2:
            best_drop = None
            best_drop_r2 = -1e10

            for feat_idx in active:
                subset = [f for f in active if f != feat_idx]
                r2_sub = _eval_subset(subset)
                if np.isfinite(r2_sub) and r2_sub > best_drop_r2:
                    best_drop_r2 = r2_sub
                    best_drop = feat_idx

            if best_drop is None:
                break

            active = [f for f in active if f != best_drop]
            elimination_log.append((len(active), best_drop_r2))

            if best_drop_r2 >= best_r2:
                best_r2 = best_drop_r2
                best_active = list(active)

            # Stop if R² drops more than 0.02 from peak
            if best_drop_r2 < best_r2 - 0.02:
                break

        full_r2s.append(r2_full)
        optimal_r2s.append(best_r2)
        optimal_sizes.append(len(best_active))
        for f in best_active:
            if f < 16:
                feature_survival[f] += 1

        if detail:
            surviving_names = [FEATURE_NAMES[f] for f in best_active if f < len(FEATURE_NAMES)]
            per_patient[d['name']] = {
                'full_r2': round(r2_full, 3),
                'optimal_r2': round(best_r2, 3),
                'n_features': len(best_active),
                'features': surviving_names,
            }

    # Normalize survival counts
    n_patients_done = len(full_r2s)
    if n_patients_done > 0:
        feature_importance = {
            FEATURE_NAMES[i]: round(feature_survival[i] / n_patients_done, 2)
            for i in range(min(16, len(FEATURE_NAMES)))
        }
    else:
        feature_importance = {}

    results = {
        'full_16feat': round(float(np.mean(full_r2s)), 3) if full_r2s else None,
        'optimal_subset': round(float(np.mean(optimal_r2s)), 3) if optimal_r2s else None,
        'improvement': round(float(np.mean(optimal_r2s) - np.mean(full_r2s)), 3) if full_r2s else None,
        'mean_optimal_size': round(float(np.mean(optimal_sizes)), 1) if optimal_sizes else None,
        'feature_survival_rate': feature_importance,
        'n_patients': n_patients_done,
    }
    if detail:
        results['per_patient'] = per_patient

    return {
        'status': 'pass',
        'detail': (f"full={results['full_16feat']}, optimal={results['optimal_subset']}, "
                   f"Δ={results['improvement']:+.3f}, mean_size={results['mean_optimal_size']}"),
        'results': results,
    }


# ── EXP-878: Error-Correcting Output Codes ──────────────────────────────────

@register('EXP-878', 'Error-Correcting Output Codes')
def exp_878(patients, detail=False):
    """Train binary classifiers for BG buckets, use class probabilities as features.

    Buckets: <70 (hypo), 70-120 (target low), 120-180 (target high), >180 (hyper).
    Each bucket gets a binary classifier (ridge on 0/1 labels). The predicted
    probability encodes where the model thinks BG will land. These probabilities
    become features for the continuous prediction model, combining classification
    evidence with regression.
    """
    h_steps = 12
    lam = 10.0
    start = 24
    thresholds = [70, 120, 180]  # defines 4 buckets

    base_r2s, ecoc_r2s = [], []

    for p in patients:
        d = _prepare_patient(p, h_steps, start)
        if d is None:
            continue

        features, actual, split = d['features'], d['actual'], d['split']
        y_tr, y_val = actual[:split], actual[split:]

        valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(features[:split]), axis=1)
        valid_val = np.isfinite(y_val) & np.all(np.isfinite(features[split:]), axis=1)

        if valid_tr.sum() < 50 or valid_val.sum() < 20:
            continue

        X_tr_v, y_tr_v = features[:split][valid_tr], y_tr[valid_tr]
        X_val_v, y_val_v = features[split:][valid_val], y_val[valid_val]

        # Ridge baseline
        pred_base, _ = _ridge_predict(X_tr_v, y_tr_v, X_val_v, lam=lam * 3)
        r2_base = _r2(pred_base, y_val_v)

        # Train binary classifiers for each threshold
        prob_tr_all = []
        prob_val_all = []

        for thresh in thresholds:
            # Binary label: 1 if BG > threshold, 0 otherwise
            label_tr = (y_tr_v > thresh).astype(float)

            # Check class balance
            if label_tr.sum() < 10 or (1 - label_tr).sum() < 10:
                prob_tr_all.append(np.full(len(X_tr_v), 0.5))
                prob_val_all.append(np.full(len(X_val_v), 0.5))
                continue

            # Ridge on binary labels (approximates logistic regression)
            pred_tr_bin, w_bin = _ridge_predict(X_tr_v, label_tr, X_tr_v, lam=lam)
            pred_val_bin = X_val_v @ w_bin if w_bin is not None else np.full(len(X_val_v), 0.5)

            # Clip to [0, 1] as pseudo-probability
            prob_tr_all.append(np.clip(pred_tr_bin, 0, 1))
            prob_val_all.append(np.clip(pred_val_bin, 0, 1))

        # Also add a "bucket centroid" feature: weighted average of bucket centers
        bucket_centers = np.array([35.0, 95.0, 150.0, 250.0])
        prob_tr_mat = np.column_stack(prob_tr_all)
        prob_val_mat = np.column_stack(prob_val_all)

        # Convert threshold probs to bucket probs: P(bucket_k) = P(>t_{k-1}) - P(>t_k)
        bucket_prob_tr = np.zeros((len(X_tr_v), 4))
        bucket_prob_val = np.zeros((len(X_val_v), 4))

        # P(< 70) = 1 - P(>70)
        bucket_prob_tr[:, 0] = 1.0 - prob_tr_mat[:, 0]
        bucket_prob_val[:, 0] = 1.0 - prob_val_mat[:, 0]
        # P(70-120) = P(>70) - P(>120)
        bucket_prob_tr[:, 1] = prob_tr_mat[:, 0] - prob_tr_mat[:, 1]
        bucket_prob_val[:, 1] = prob_val_mat[:, 0] - prob_val_mat[:, 1]
        # P(120-180) = P(>120) - P(>180)
        bucket_prob_tr[:, 2] = prob_tr_mat[:, 1] - prob_tr_mat[:, 2]
        bucket_prob_val[:, 2] = prob_val_mat[:, 1] - prob_val_mat[:, 2]
        # P(> 180) = P(>180)
        bucket_prob_tr[:, 3] = prob_tr_mat[:, 2]
        bucket_prob_val[:, 3] = prob_val_mat[:, 2]

        # Clip negative probabilities
        bucket_prob_tr = np.maximum(bucket_prob_tr, 0)
        bucket_prob_val = np.maximum(bucket_prob_val, 0)

        # Weighted centroid
        centroid_tr = bucket_prob_tr @ bucket_centers
        centroid_val = bucket_prob_val @ bucket_centers

        # Combine: original features + bucket probs + centroid
        X_tr_ecoc = np.column_stack([X_tr_v, bucket_prob_tr, centroid_tr])
        X_val_ecoc = np.column_stack([X_val_v, bucket_prob_val, centroid_val])

        valid_ecoc_tr = np.all(np.isfinite(X_tr_ecoc), axis=1)
        valid_ecoc_val = np.all(np.isfinite(X_val_ecoc), axis=1)

        if valid_ecoc_tr.sum() >= 50 and valid_ecoc_val.sum() >= 10:
            pred_ecoc, _ = _ridge_predict(X_tr_ecoc[valid_ecoc_tr], y_tr_v[valid_ecoc_tr],
                                           X_val_ecoc, lam=lam * 5)
            r2_ecoc = _r2(pred_ecoc[valid_ecoc_val], y_val_v[valid_ecoc_val])
        else:
            r2_ecoc = float('nan')

        if np.isfinite(r2_base) and np.isfinite(r2_ecoc):
            base_r2s.append(r2_base)
            ecoc_r2s.append(r2_ecoc)

    results = {
        'ridge_baseline': round(float(np.mean(base_r2s)), 3) if base_r2s else None,
        'ecoc_augmented': round(float(np.mean(ecoc_r2s)), 3) if ecoc_r2s else None,
        'improvement': round(float(np.mean(ecoc_r2s) - np.mean(base_r2s)), 3) if base_r2s else None,
        'n_patients': len(base_r2s),
    }

    return {
        'status': 'pass',
        'detail': (f"base={results['ridge_baseline']}, ecoc={results['ecoc_augmented']}, "
                   f"Δ={results['improvement']:+.3f}"),
        'results': results,
    }


# ── EXP-879: Wavelet-Based Decomposition ────────────────────────────────────

@register('EXP-879', 'Wavelet-Based Decomposition')
def exp_879(patients, detail=False):
    """Decompose BG and flux signals into frequency bands and predict separately.

    Low-frequency (trend) captures slow drift from basal/sensitivity changes.
    High-frequency captures rapid meal/correction dynamics. Predict each band
    independently with features tailored to that band's timescale, then sum.

    Uses simple moving-average decomposition instead of proper wavelets to avoid
    scipy.signal dependency issues. Low-freq = MA(window), high-freq = original - MA.
    """
    h_steps = 12
    lam = 10.0
    start = 24

    base_r2s, decomp_r2s, sum_r2s = [], [], []
    band_configs = [
        ('short', 6),    # 30-min window
        ('medium', 12),  # 60-min window
        ('long', 24),    # 2-hour window
    ]

    for p in patients:
        d = _prepare_patient(p, h_steps, start)
        if d is None:
            continue

        features, actual, split, usable = d['features'], d['actual'], d['split'], d['usable']
        fd, bg = d['fd'], d['bg']
        y_tr, y_val = actual[:split], actual[split:]

        valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(features[:split]), axis=1)
        valid_val = np.isfinite(y_val) & np.all(np.isfinite(features[split:]), axis=1)

        if valid_tr.sum() < 50 or valid_val.sum() < 20:
            continue

        # Base model
        X_tr_v, y_tr_v = features[:split][valid_tr], y_tr[valid_tr]
        X_val_v, y_val_v = features[split:][valid_val], y_val[valid_val]
        pred_base, _ = _ridge_predict(X_tr_v, y_tr_v, X_val_v, lam=lam * 3)
        r2_base = _r2(pred_base, y_val_v)

        # Decompose target BG into frequency bands
        # Use medium window (60min) for decomposition
        win = 12
        target_full = bg[h_steps + 1 + start: h_steps + 1 + start + usable]

        # Compute MA of target (low-frequency component)
        target_lo = np.convolve(target_full, np.ones(win) / win, mode='same')
        target_hi = target_full - target_lo

        y_lo_tr, y_lo_val = target_lo[:split], target_lo[split:]
        y_hi_tr, y_hi_val = target_hi[:split], target_hi[split:]

        # Build band-specific features
        # Low-freq features: smoothed versions of base features
        feat_lo = np.zeros_like(features)
        for col in range(features.shape[1]):
            feat_lo[:, col] = np.convolve(features[:, col], np.ones(win) / win, mode='same')

        feat_hi = features - feat_lo

        # Train separate models for each band
        X_tr_lo = feat_lo[:split][valid_tr]
        X_tr_hi = feat_hi[:split][valid_tr]

        y_lo_tr_v = y_lo_tr[valid_tr]
        y_hi_tr_v = y_hi_tr[valid_tr]

        pred_lo, _ = _ridge_predict(X_tr_lo, y_lo_tr_v,
                                     feat_lo[split:][valid_val], lam=lam * 3)
        pred_hi, _ = _ridge_predict(X_tr_hi, y_hi_tr_v,
                                     feat_hi[split:][valid_val], lam=lam * 3)

        # Decomposed R² (sum of band predictions)
        pred_decomp = pred_lo + pred_hi
        r2_decomp = _r2(pred_decomp, y_val_v)

        # Enhanced: use BOTH band features + original features
        feat_all_bands = np.hstack([features, feat_lo, feat_hi])
        X_tr_all = feat_all_bands[:split]
        X_val_all = feat_all_bands[split:]

        valid_tr_all = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_all), axis=1)
        valid_val_all = np.isfinite(y_val) & np.all(np.isfinite(X_val_all), axis=1)

        if valid_tr_all.sum() >= 50 and valid_val_all.sum() >= 10:
            pred_sum, _ = _ridge_predict(X_tr_all[valid_tr_all], y_tr[valid_tr_all],
                                          X_val_all, lam=lam * 6)
            r2_sum = _r2(pred_sum[valid_val_all], y_val[valid_val_all])
        else:
            r2_sum = float('nan')

        if np.isfinite(r2_base):
            base_r2s.append(r2_base)
            if np.isfinite(r2_decomp):
                decomp_r2s.append(r2_decomp)
            if np.isfinite(r2_sum):
                sum_r2s.append(r2_sum)

    results = {
        'base': round(float(np.mean(base_r2s)), 3) if base_r2s else None,
        'decomposed_sum': round(float(np.mean(decomp_r2s)), 3) if decomp_r2s else None,
        'all_bands_combined': round(float(np.mean(sum_r2s)), 3) if sum_r2s else None,
        'improvement_decomp': round(float(np.mean(decomp_r2s) - np.mean(base_r2s)), 3) if decomp_r2s and base_r2s else None,
        'improvement_combined': round(float(np.mean(sum_r2s) - np.mean(base_r2s)), 3) if sum_r2s and base_r2s else None,
        'n_patients': len(base_r2s),
    }

    return {
        'status': 'pass',
        'detail': (f"base={results['base']}, decomp={results['decomposed_sum']}, "
                   f"combined={results['all_bands_combined']}"),
        'results': results,
    }


# ── EXP-880: Comprehensive Stacking Benchmark ───────────────────────────────

@register('EXP-880', 'Comprehensive Stacking Benchmark')
def exp_880(patients, detail=False):
    """Combine the best discoveries into a single benchmark.

    Integrates: (a) CV stacking from EXP-871, (b) multi-horizon predictions
    from EXP-862, (c) disagreement features from EXP-867, (d) residual regime
    features from EXP-875, and (e) patient-specific feature selection from
    EXP-873 via LASSO. Full comparison against all prior SOTAs.

    Architecture:
    - Level-0: Multi-horizon models at [1, 3, 6, 9, 12] steps
    - Disagreement features: std, range, consensus across Level-0 predictions
    - Residual features: sign and magnitude of recent prediction error
    - Level-1 meta-learner: Ridge on (enhanced + horizons + disagreement + residual)
    - Optional LASSO filter on combined feature set
    """
    from sklearn.linear_model import Lasso, Ridge

    h_steps = 12
    lam = 10.0
    start = 24
    horizons = [1, 3, 6, 9, 12]
    n_folds = 5

    base_r2s, full_stack_r2s, lasso_stack_r2s = [], [], []
    base_maes, full_stack_maes = [], []
    per_patient = {}

    for p in patients:
        d = _prepare_patient(p, h_steps, start)
        if d is None:
            continue

        features, actual, split, usable = d['features'], d['actual'], d['split'], d['usable']
        fd, bg, hours, nr = d['fd'], d['bg'], d['hours'], d['nr']
        y_tr, y_val = actual[:split], actual[split:]

        # ── Step 1: Multi-horizon Level-0 predictions ────────────────────
        h_preds, _ = _train_horizon_models(fd, bg, hours, nr, start, usable, split, horizons)
        if len(h_preds) < 3:
            continue

        horizon_feats = np.column_stack([h_preds[h] for h in sorted(h_preds)])

        # ── Step 2: Disagreement features ────────────────────────────────
        disagree_feats = np.zeros((usable, 4))
        for i in range(usable):
            row = horizon_feats[i]
            valid_row = row[np.isfinite(row)]
            if len(valid_row) >= 2:
                disagree_feats[i, 0] = np.std(valid_row)
                disagree_feats[i, 1] = np.max(valid_row) - np.min(valid_row)
                disagree_feats[i, 2] = np.mean(valid_row)
                disagree_feats[i, 3] = valid_row[-1] - valid_row[0]

        # ── Step 3: Residual regime features ─────────────────────────────
        # Train base model to compute residuals
        valid_tr_base = np.isfinite(y_tr) & np.all(np.isfinite(features[:split]), axis=1)
        if valid_tr_base.sum() < 50:
            continue

        _, w_base = _ridge_predict(features[:split][valid_tr_base], y_tr[valid_tr_base],
                                    features[:1], lam=lam * 3)
        if w_base is None:
            continue

        pred_tr_base = features[:split] @ w_base
        train_resid = actual[:split] - pred_tr_base

        resid_sign = np.zeros(usable)
        resid_mag = np.zeros(usable)
        window = 12
        for i in range(usable):
            lo = max(0, i - window)
            if i <= split:
                r_w = train_resid[lo:i]
            else:
                r_w = train_resid[max(0, split - window):split]
            valid_w = r_w[np.isfinite(r_w)]
            if len(valid_w) > 0:
                resid_sign[i] = np.sign(np.mean(valid_w))
                resid_mag[i] = np.mean(np.abs(valid_w))

        resid_feats = np.column_stack([resid_sign, resid_mag])

        # ── Step 4: CV stacking for Level-0 ──────────────────────────────
        fold_size = split // n_folds
        oof_horizon = {}
        for h in sorted(h_preds):
            oof_horizon[h] = np.full(split, np.nan)

        for fold_i in range(n_folds):
            fold_start = fold_i * fold_size
            fold_end = min((fold_i + 1) * fold_size, split)
            train_idx = np.concatenate([np.arange(0, fold_start),
                                         np.arange(fold_end, split)])
            val_idx = np.arange(fold_start, fold_end)

            for h in sorted(h_preds):
                n_pred_h = nr - h
                if n_pred_h - start < usable:
                    continue
                actual_h = bg[h + 1 + start: h + 1 + start + usable]
                feat_h = _build_features_base(fd, hours, n_pred_h, h)
                feat_h = feat_h[start:start + usable]

                X_fold_tr = feat_h[train_idx]
                y_fold_tr = actual_h[train_idx]
                X_fold_val = feat_h[val_idx]

                valid_fold = np.isfinite(y_fold_tr) & np.all(np.isfinite(X_fold_tr), axis=1)
                if valid_fold.sum() < 30:
                    continue

                pred_fold, _ = _ridge_predict(X_fold_tr[valid_fold], y_fold_tr[valid_fold],
                                               X_fold_val, lam=0.1)
                oof_horizon[h][val_idx] = pred_fold

        oof_stack = np.column_stack([oof_horizon[h] for h in sorted(oof_horizon)])

        # ── Step 5: Combine all features ─────────────────────────────────
        # For training: use OOF horizon predictions
        combined_tr = np.hstack([
            features[:split], oof_stack,
            disagree_feats[:split], resid_feats[:split],
        ])

        # For validation: use full-train horizon predictions
        combined_val = np.hstack([
            features[split:], horizon_feats[split:],
            disagree_feats[split:], resid_feats[split:],
        ])

        valid_tr_full = np.isfinite(y_tr) & np.all(np.isfinite(combined_tr), axis=1)
        valid_val_full = np.isfinite(y_val) & np.all(np.isfinite(combined_val), axis=1)

        if valid_tr_full.sum() < 50 or valid_val_full.sum() < 10:
            continue

        X_tr_full, y_tr_full = combined_tr[valid_tr_full], y_tr[valid_tr_full]
        X_val_full, y_val_full = combined_val[valid_val_full], y_val[valid_val_full]

        # Base 16-feature model
        valid_val_b = np.isfinite(y_val) & np.all(np.isfinite(features[split:]), axis=1)
        pred_base, _ = _ridge_predict(features[:split][valid_tr_base], y_tr[valid_tr_base],
                                       features[split:], lam=lam * 3)
        r2_base = _r2(pred_base[valid_val_b], y_val[valid_val_b])
        mae_base = _mae(pred_base[valid_val_b], y_val[valid_val_b])

        # Full stacked model
        pred_full, _ = _ridge_predict(X_tr_full, y_tr_full, X_val_full, lam=lam * 6)
        r2_full = _r2(pred_full, y_val_full)
        mae_full = _mae(pred_full, y_val_full)

        # LASSO-filtered stacking
        mu_c = X_tr_full.mean(axis=0)
        sigma_c = X_tr_full.std(axis=0)
        sigma_c[sigma_c < 1e-10] = 1.0
        X_tr_normed = (X_tr_full - mu_c) / sigma_c
        X_val_normed = (X_val_full - mu_c) / sigma_c

        try:
            lasso = Lasso(alpha=0.5, max_iter=5000)
            lasso.fit(X_tr_normed, y_tr_full)
            selected = np.abs(lasso.coef_) > 1e-8
            n_sel = int(selected.sum())

            if n_sel >= 3:
                ridge_sel = Ridge(alpha=lam * 5)
                ridge_sel.fit(X_tr_full[:, selected], y_tr_full)
                pred_lasso = ridge_sel.predict(X_val_full[:, selected])
                r2_lasso = _r2(pred_lasso, y_val_full)
            else:
                r2_lasso = r2_full
        except Exception:
            r2_lasso = r2_full

        if np.isfinite(r2_base) and np.isfinite(r2_full):
            base_r2s.append(r2_base)
            full_stack_r2s.append(r2_full)
            base_maes.append(mae_base)
            full_stack_maes.append(mae_full)
            if np.isfinite(r2_lasso):
                lasso_stack_r2s.append(r2_lasso)

            if detail:
                per_patient[d['name']] = {
                    'base_r2': round(r2_base, 3),
                    'full_stack_r2': round(r2_full, 3),
                    'lasso_stack_r2': round(r2_lasso, 3) if np.isfinite(r2_lasso) else None,
                    'base_mae': round(mae_base, 1),
                    'full_stack_mae': round(mae_full, 1),
                }

    results = {
        'base_16feat_r2': round(float(np.mean(base_r2s)), 3) if base_r2s else None,
        'full_stacked_r2': round(float(np.mean(full_stack_r2s)), 3) if full_stack_r2s else None,
        'lasso_stacked_r2': round(float(np.mean(lasso_stack_r2s)), 3) if lasso_stack_r2s else None,
        'base_mae': round(float(np.mean(base_maes)), 1) if base_maes else None,
        'full_stacked_mae': round(float(np.mean(full_stack_maes)), 1) if full_stack_maes else None,
        'improvement_full': round(float(np.mean(full_stack_r2s) - np.mean(base_r2s)), 3) if full_stack_r2s else None,
        'improvement_lasso': round(float(np.mean(lasso_stack_r2s) - np.mean(base_r2s)), 3) if lasso_stack_r2s else None,
        'oracle_gap': round(0.613 - float(np.mean(full_stack_r2s)), 3) if full_stack_r2s else None,
        'pct_oracle': round(float(np.mean(full_stack_r2s)) / 0.613 * 100, 1) if full_stack_r2s else None,
        'n_patients': len(base_r2s),
    }
    if detail:
        results['per_patient'] = per_patient

    best_r2 = max(
        results.get('full_stacked_r2') or 0,
        results.get('lasso_stacked_r2') or 0,
    )
    best_method = 'full_stacked' if (results.get('full_stacked_r2') or 0) >= (results.get('lasso_stacked_r2') or 0) else 'lasso_stacked'
    results['best_method'] = best_method
    results['best_r2'] = round(best_r2, 3)

    return {
        'status': 'pass',
        'detail': (f"base={results['base_16feat_r2']}, full_stack={results['full_stacked_r2']}, "
                   f"lasso_stack={results['lasso_stacked_r2']}, oracle_gap={results['oracle_gap']}"),
        'results': results,
    }


# ── Runner ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='EXP-871-880: Bias Reduction & Advanced Stacking')
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--max-patients', type=int, default=11)
    parser.add_argument('--experiment', type=str, default=None)
    args = parser.parse_args()

    patients = load_patients(str(PATIENTS_DIR), max_patients=args.max_patients)
    print(f"Loaded {len(patients)} patients")

    exp_dir = Path(__file__).parent.parent.parent / 'externals' / 'experiments'
    exp_dir.mkdir(exist_ok=True)

    for exp_id in sorted(EXPERIMENTS.keys(), key=lambda x: int(x.split('-')[1])):
        if args.experiment and exp_id != args.experiment:
            continue

        exp = EXPERIMENTS[exp_id]
        print(f"\n{'='*60}")
        print(f"Running {exp_id}: {exp['name']}")
        print(f"{'='*60}")

        t0 = time.time()
        try:
            result = exp['func'](patients, detail=args.detail)
        except Exception as e:
            import traceback
            traceback.print_exc()
            result = {'status': 'fail', 'detail': str(e)}

        elapsed = time.time() - t0
        status = result.get('status', 'unknown')
        detail = result.get('detail', '')

        print(f"  Status: {status}")
        print(f"  Detail: {detail}")
        print(f"  Time: {elapsed:.1f}s")

        if args.save and 'results' in result:
            fname = f"exp_{exp_id.split('-')[1]}_{exp['name'].lower().replace(' ', '_').replace('/', '_')}.json"
            fpath = exp_dir / fname
            save_data = {
                'experiment': exp_id,
                'name': exp['name'],
                'status': status,
                'detail': detail,
                'elapsed_seconds': round(elapsed, 1),
                'results': result['results'],
            }
            with open(fpath, 'w') as f:
                json.dump(save_data, f, indent=2, default=str)
            print(f"  Saved: {fpath}")

    print(f"\n{'='*60}")
    print("All experiments complete")


if __name__ == '__main__':
    main()
