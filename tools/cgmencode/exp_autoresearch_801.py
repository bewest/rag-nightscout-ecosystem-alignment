#!/usr/bin/env python3
"""EXP-801–810: Ridge Regression Deep Dive & Feature Engineering

Following the EXP-800 breakthrough (ridge R²=0.803/0.519 at 30/60min),
this wave explores feature importance, optimal regularization, extended
features, cross-patient generalization, and residual analysis.

EXP-801: Feature Importance (ablation study)
EXP-802: Regularization Sweep (optimal λ)
EXP-803: Extended Features (interactions, derivatives, quadratics)
EXP-804: Leave-One-Patient-Out Ridge Validation
EXP-805: Per-Patient Ridge Analysis (which patients benefit most)
EXP-806: Rolling Ridge (adaptive online learning)
EXP-807: Ridge Residual Analysis (what remains unexplained)
EXP-808: Supply-Demand Ratio as Feature
EXP-809: Multi-Horizon Joint Ridge (one model, all horizons)
EXP-810: Ridge vs Lasso vs ElasticNet
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
    """Build the base 8-feature matrix from EXP-792/800."""
    bg = fd['bg']
    resid = fd['resid']
    nr = len(resid)
    n = fd['n']
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

def _ridge_predict(X_train, y_train, X_val, lam=1.0):
    """Fit ridge regression and predict."""
    XtX = X_train.T @ X_train + lam * np.eye(X_train.shape[1])
    try:
        w = np.linalg.solve(XtX, X_train.T @ y_train)
        return X_val @ w, w
    except np.linalg.LinAlgError:
        return np.full(X_val.shape[0], np.nan), None

FEATURE_NAMES = ['bg', 'Σsupply', 'Σdemand', 'Σhepatic', 'resid', 'sin_h', 'cos_h', 'bias']

def register(exp_id, name):
    def decorator(func):
        EXPERIMENTS[exp_id] = {'name': name, 'func': func}
        return func
    return decorator


# ---------------------------------------------------------------------------
# EXP-801: Feature Importance (Ablation)
# ---------------------------------------------------------------------------
@register('EXP-801', 'Feature Ablation')
def exp_801(patients, detail=False):
    """Measure importance of each feature by leave-one-out ablation."""
    h_steps = 12  # 60min
    results = {}

    for feat_idx in range(8):
        r2_full = []
        r2_ablated = []

        for p in patients:
            fd = _compute_flux(p)
            bg = fd['bg']
            n = fd['n']
            nr = len(fd['resid'])
            df = p['df']
            hours = _get_hours(df, n)
            if hours is None:
                continue

            n_pred = nr - h_steps
            if n_pred < 500:
                continue

            actual = bg[h_steps:h_steps + n_pred]
            features = _build_features_base(fd, hours, n_pred, h_steps)

            valid = np.all(np.isfinite(features), axis=1) & np.isfinite(actual)
            split = int(n_pred * 0.7)
            train_m = valid[:split]
            val_m = valid[split:]

            if train_m.sum() < 200 or val_m.sum() < 100:
                continue

            X_tr = features[:split][train_m]
            y_tr = actual[:split][train_m]
            X_va = features[split:][val_m]
            y_va = actual[split:][val_m]

            # Full model
            pred_full, _ = _ridge_predict(X_tr, y_tr, X_va)
            r2_f = _r2(pred_full, y_va)

            # Ablated model (zero out feature)
            X_tr_abl = X_tr.copy()
            X_va_abl = X_va.copy()
            X_tr_abl[:, feat_idx] = 0
            X_va_abl[:, feat_idx] = 0
            pred_abl, _ = _ridge_predict(X_tr_abl, y_tr, X_va_abl)
            r2_a = _r2(pred_abl, y_va)

            if np.isfinite(r2_f) and np.isfinite(r2_a):
                r2_full.append(r2_f)
                r2_ablated.append(r2_a)

        mean_full = np.mean(r2_full) if r2_full else float('nan')
        mean_abl = np.mean(r2_ablated) if r2_ablated else float('nan')
        importance = mean_full - mean_abl
        results[FEATURE_NAMES[feat_idx]] = {
            'full_r2': round(mean_full, 3),
            'ablated_r2': round(mean_abl, 3),
            'importance': round(importance, 3),
        }

    # Sort by importance
    sorted_feats = sorted(results.items(), key=lambda x: x[1]['importance'], reverse=True)
    detail_str = ', '.join(f'{name}: Δ={v["importance"]:+.3f}' for name, v in sorted_feats)
    return {'status': 'pass', 'detail': detail_str, 'results': results}


# ---------------------------------------------------------------------------
# EXP-802: Regularization Sweep
# ---------------------------------------------------------------------------
@register('EXP-802', 'Regularization Sweep')
def exp_802(patients, detail=False):
    """Find optimal ridge regularization parameter λ."""
    lambdas = [0.001, 0.01, 0.1, 1.0, 10.0, 100.0, 1000.0]
    horizons = {6: '30min', 12: '60min'}
    results = {}

    for h_steps, h_name in horizons.items():
        lambda_results = {}
        for lam in lambdas:
            r2_list = []
            for p in patients:
                fd = _compute_flux(p)
                bg = fd['bg']
                n = fd['n']
                nr = len(fd['resid'])
                df = p['df']
                hours = _get_hours(df, n)
                if hours is None:
                    continue

                n_pred = nr - h_steps
                if n_pred < 500:
                    continue

                actual = bg[h_steps:h_steps + n_pred]
                features = _build_features_base(fd, hours, n_pred, h_steps)

                valid = np.all(np.isfinite(features), axis=1) & np.isfinite(actual)
                split = int(n_pred * 0.7)
                train_m = valid[:split]
                val_m = valid[split:]
                if train_m.sum() < 200 or val_m.sum() < 100:
                    continue

                pred, _ = _ridge_predict(
                    features[:split][train_m], actual[:split][train_m],
                    features[split:][val_m], lam=lam)
                r2 = _r2(pred, actual[split:][val_m])
                if np.isfinite(r2):
                    r2_list.append(r2)

            mean_r2 = np.mean(r2_list) if r2_list else float('nan')
            lambda_results[str(lam)] = round(mean_r2, 3)

        best_lam = max(lambda_results, key=lambda k: lambda_results[k] if np.isfinite(lambda_results[k]) else -999)
        results[h_name] = {'lambdas': lambda_results, 'best_lambda': float(best_lam), 'best_r2': lambda_results[best_lam]}

    detail_str = ', '.join(f'{h}: best λ={v["best_lambda"]}, R²={v["best_r2"]}' for h, v in results.items())
    return {'status': 'pass', 'detail': detail_str, 'results': results}


# ---------------------------------------------------------------------------
# EXP-803: Extended Features
# ---------------------------------------------------------------------------
@register('EXP-803', 'Extended Features')
def exp_803(patients, detail=False):
    """Add interaction terms, derivatives, and quadratics to ridge."""
    horizons = {6: '30min', 12: '60min'}
    results = {}

    for h_steps, h_name in horizons.items():
        r2_base = []
        r2_extended = []
        per_patient = []

        for p in patients:
            fd = _compute_flux(p)
            bg = fd['bg']
            resid = fd['resid']
            n = fd['n']
            nr = len(resid)
            df = p['df']
            hours = _get_hours(df, n)
            if hours is None:
                continue

            n_pred = nr - h_steps
            if n_pred < 500:
                continue

            actual = bg[h_steps:h_steps + n_pred]

            # Base features
            base = _build_features_base(fd, hours, n_pred, h_steps)

            # Extended features: add derivatives and interactions
            ext = np.zeros((n_pred, 16))
            ext[:, :8] = base
            for i in range(n_pred):
                # BG derivative (trend)
                ext[i, 8] = bg[i] - bg[max(0, i-1)] if i > 0 else 0
                # Second derivative (acceleration)
                ext[i, 9] = (bg[i] - 2*bg[max(0,i-1)] + bg[max(0,i-2)]) if i > 1 else 0
                # Supply-demand net
                ext[i, 10] = ext[i, 1] - ext[i, 2]  # net flux
                # BG × time interaction
                ext[i, 11] = bg[i] * ext[i, 5]  # bg × sin
                ext[i, 12] = bg[i] * ext[i, 6]  # bg × cos
                # Quadratic BG (for nonlinearity)
                ext[i, 13] = bg[i]**2 / 10000
                # Resid × time
                ext[i, 14] = ext[i, 4] * ext[i, 5]  # resid × sin
                ext[i, 15] = 1.0  # bias (redundant but harmless)

            valid = np.all(np.isfinite(ext), axis=1) & np.isfinite(actual)
            split = int(n_pred * 0.7)
            train_m = valid[:split]
            val_m = valid[split:]
            if train_m.sum() < 200 or val_m.sum() < 100:
                continue

            y_tr = actual[:split][train_m]
            y_va = actual[split:][val_m]

            # Base model
            pred_b, _ = _ridge_predict(base[:split][train_m], y_tr, base[split:][val_m])
            r2_b = _r2(pred_b, y_va)

            # Extended model
            pred_e, _ = _ridge_predict(ext[:split][train_m], y_tr, ext[split:][val_m], lam=10.0)
            r2_e = _r2(pred_e, y_va)

            if np.isfinite(r2_b) and np.isfinite(r2_e):
                r2_base.append(r2_b)
                r2_extended.append(r2_e)
                per_patient.append({
                    'patient': p['name'],
                    'base': round(r2_b, 3), 'extended': round(r2_e, 3),
                    'delta': round(r2_e - r2_b, 3)
                })

        mb = np.mean(r2_base) if r2_base else float('nan')
        me = np.mean(r2_extended) if r2_extended else float('nan')
        results[h_name] = {'base': round(mb, 3), 'extended': round(me, 3),
                           'delta': round(me - mb, 3), 'per_patient': per_patient}

    detail_str = ', '.join(f'{h}: base={v["base"]}/ext={v["extended"]}/Δ={v["delta"]}' for h, v in results.items())
    return {'status': 'pass', 'detail': detail_str, 'results': results}


# ---------------------------------------------------------------------------
# EXP-804: Leave-One-Patient-Out
# ---------------------------------------------------------------------------
@register('EXP-804', 'LOO Cross-Validation')
def exp_804(patients, detail=False):
    """Leave-one-patient-out cross-validation for ridge regression."""
    h_steps = 12  # 60min
    results = []

    # Build pooled features for all patients
    all_features = []
    all_targets = []
    patient_indices = []

    for p_idx, p in enumerate(patients):
        fd = _compute_flux(p)
        bg = fd['bg']
        n = fd['n']
        nr = len(fd['resid'])
        df = p['df']
        hours = _get_hours(df, n)
        if hours is None:
            continue

        n_pred = nr - h_steps
        if n_pred < 500:
            continue

        actual = bg[h_steps:h_steps + n_pred]
        features = _build_features_base(fd, hours, n_pred, h_steps)

        # Use val split (last 30%) for fair comparison with personal model
        split = int(n_pred * 0.7)
        valid = np.all(np.isfinite(features), axis=1) & np.isfinite(actual)

        # Train part
        train_m = valid[:split]
        if train_m.sum() < 100:
            continue

        all_features.append(features[:split][train_m])
        all_targets.append(actual[:split][train_m])
        patient_indices.append(p_idx)

    # LOO: for each patient, train on all others, test on held-out
    for loo_idx in range(len(patient_indices)):
        p_idx = patient_indices[loo_idx]
        p = patients[p_idx]
        fd = _compute_flux(p)
        bg = fd['bg']
        n = fd['n']
        nr = len(fd['resid'])
        df = p['df']
        hours = _get_hours(df, n)
        if hours is None:
            continue

        n_pred = nr - h_steps
        actual = bg[h_steps:h_steps + n_pred]
        features = _build_features_base(fd, hours, n_pred, h_steps)
        split = int(n_pred * 0.7)
        valid = np.all(np.isfinite(features), axis=1) & np.isfinite(actual)

        val_m = valid[split:]
        if val_m.sum() < 100:
            continue

        X_val = features[split:][val_m]
        y_val = actual[split:][val_m]

        # Personal model
        train_m = valid[:split]
        if train_m.sum() < 100:
            continue
        pred_personal, _ = _ridge_predict(features[:split][train_m], actual[:split][train_m], X_val)
        r2_personal = _r2(pred_personal, y_val)

        # Population model (all others)
        X_pop = np.vstack([all_features[j] for j in range(len(patient_indices)) if j != loo_idx])
        y_pop = np.concatenate([all_targets[j] for j in range(len(patient_indices)) if j != loo_idx])
        pred_pop, _ = _ridge_predict(X_pop, y_pop, X_val, lam=10.0)
        r2_pop = _r2(pred_pop, y_val)

        if np.isfinite(r2_personal) and np.isfinite(r2_pop):
            results.append({
                'patient': p['name'],
                'personal_r2': round(r2_personal, 3),
                'population_r2': round(r2_pop, 3),
                'gap': round(r2_pop - r2_personal, 3),
            })

    mean_personal = np.mean([r['personal_r2'] for r in results]) if results else float('nan')
    mean_pop = np.mean([r['population_r2'] for r in results]) if results else float('nan')
    detail_parts = [f'{r["patient"]}: pers={r["personal_r2"]}/pop={r["population_r2"]}/gap={r["gap"]}'
                    for r in results[:8]]
    return {
        'status': 'pass',
        'detail': f'mean personal={mean_personal:.3f}, pop={mean_pop:.3f}, gap={mean_pop-mean_personal:.3f}. ' + '; '.join(detail_parts),
        'per_patient': results,
    }


# ---------------------------------------------------------------------------
# EXP-805: Per-Patient Ridge Analysis
# ---------------------------------------------------------------------------
@register('EXP-805', 'Per-Patient Ridge')
def exp_805(patients, detail=False):
    """Analyze ridge weights and performance for each patient individually."""
    h_steps = 12
    results = []

    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        n = fd['n']
        nr = len(fd['resid'])
        df = p['df']
        hours = _get_hours(df, n)
        if hours is None:
            continue

        n_pred = nr - h_steps
        if n_pred < 500:
            continue

        actual = bg[h_steps:h_steps + n_pred]
        features = _build_features_base(fd, hours, n_pred, h_steps)

        valid = np.all(np.isfinite(features), axis=1) & np.isfinite(actual)
        split = int(n_pred * 0.7)
        train_m = valid[:split]
        val_m = valid[split:]
        if train_m.sum() < 200 or val_m.sum() < 100:
            continue

        X_tr = features[:split][train_m]
        y_tr = actual[:split][train_m]
        X_va = features[split:][val_m]
        y_va = actual[split:][val_m]

        pred, w = _ridge_predict(X_tr, y_tr, X_va)
        r2 = _r2(pred, y_va)
        mae = _mae(pred, y_va)

        if w is not None:
            # Normalize weights by feature std for comparability
            feat_stds = np.std(X_tr, axis=0)
            feat_stds[feat_stds < 1e-10] = 1.0
            w_normalized = w * feat_stds

            results.append({
                'patient': p['name'],
                'r2': round(r2, 3) if np.isfinite(r2) else None,
                'mae': round(mae, 1) if np.isfinite(mae) else None,
                'weights': {FEATURE_NAMES[i]: round(float(w[i]), 4) for i in range(8)},
                'importance': {FEATURE_NAMES[i]: round(float(abs(w_normalized[i])), 2) for i in range(8)},
                'top_feature': FEATURE_NAMES[int(np.argmax(np.abs(w_normalized)))],
            })

    detail_parts = [f'{r["patient"]}: R²={r["r2"]}, MAE={r["mae"]}, top={r["top_feature"]}'
                    for r in results[:8]]
    return {
        'status': 'pass',
        'detail': f'n={len(results)}. ' + '; '.join(detail_parts),
        'per_patient': results,
    }


# ---------------------------------------------------------------------------
# EXP-806: Rolling Ridge (Online Learning)
# ---------------------------------------------------------------------------
@register('EXP-806', 'Rolling Ridge')
def exp_806(patients, detail=False):
    """Adaptive ridge with rolling training window."""
    h_steps = 12  # 60min
    windows = [288*7, 288*14, 288*30, 288*60]  # 1wk, 2wk, 1mo, 2mo
    window_names = ['1wk', '2wk', '1mo', '2mo']
    results = {}

    for w_size, w_name in zip(windows, window_names):
        r2_list = []
        for p in patients:
            fd = _compute_flux(p)
            bg = fd['bg']
            n = fd['n']
            nr = len(fd['resid'])
            df = p['df']
            hours = _get_hours(df, n)
            if hours is None:
                continue

            n_pred = nr - h_steps
            if n_pred < w_size + 1000:
                continue

            actual = bg[h_steps:h_steps + n_pred]
            features = _build_features_base(fd, hours, n_pred, h_steps)

            # Rolling prediction: train on window, predict next chunk
            chunk_size = 288  # 1 day chunks
            preds = []
            actuals = []

            for start in range(w_size, n_pred - chunk_size, chunk_size):
                train_start = start - w_size
                X_tr = features[train_start:start]
                y_tr = actual[train_start:start]
                X_va = features[start:start+chunk_size]
                y_va = actual[start:start+chunk_size]

                valid_tr = np.all(np.isfinite(X_tr), axis=1) & np.isfinite(y_tr)
                valid_va = np.all(np.isfinite(X_va), axis=1) & np.isfinite(y_va)

                if valid_tr.sum() < 100 or valid_va.sum() < 10:
                    continue

                pred, _ = _ridge_predict(X_tr[valid_tr], y_tr[valid_tr], X_va[valid_va])
                preds.extend(pred.tolist())
                actuals.extend(y_va[valid_va].tolist())

            if len(preds) >= 100:
                r2 = _r2(np.array(preds), np.array(actuals))
                if np.isfinite(r2):
                    r2_list.append(r2)

        mean_r2 = np.mean(r2_list) if r2_list else float('nan')
        results[w_name] = {'r2': round(mean_r2, 3), 'n': len(r2_list)}

    # Also compare with full training
    r2_full = []
    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        n = fd['n']
        nr = len(fd['resid'])
        df = p['df']
        hours = _get_hours(df, n)
        if hours is None:
            continue
        n_pred = nr - h_steps
        if n_pred < 500:
            continue
        actual = bg[h_steps:h_steps + n_pred]
        features = _build_features_base(fd, hours, n_pred, h_steps)
        valid = np.all(np.isfinite(features), axis=1) & np.isfinite(actual)
        split = int(n_pred * 0.7)
        train_m = valid[:split]
        val_m = valid[split:]
        if train_m.sum() < 200 or val_m.sum() < 100:
            continue
        pred, _ = _ridge_predict(features[:split][train_m], actual[:split][train_m], features[split:][val_m])
        r2 = _r2(pred, actual[split:][val_m])
        if np.isfinite(r2):
            r2_full.append(r2)
    results['full'] = {'r2': round(np.mean(r2_full), 3) if r2_full else float('nan'), 'n': len(r2_full)}

    detail_str = ', '.join(f'{k}: R²={v["r2"]}' for k, v in results.items())
    return {'status': 'pass', 'detail': detail_str, 'results': results}


# ---------------------------------------------------------------------------
# EXP-807: Ridge Residual Analysis
# ---------------------------------------------------------------------------
@register('EXP-807', 'Ridge Residual Analysis')
def exp_807(patients, detail=False):
    """Analyze what ridge regression can't predict (residual patterns)."""
    h_steps = 12  # 60min
    results = []

    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        n = fd['n']
        nr = len(fd['resid'])
        df = p['df']
        hours = _get_hours(df, n)
        if hours is None:
            continue

        n_pred = nr - h_steps
        if n_pred < 500:
            continue

        actual = bg[h_steps:h_steps + n_pred]
        features = _build_features_base(fd, hours, n_pred, h_steps)

        valid = np.all(np.isfinite(features), axis=1) & np.isfinite(actual)
        split = int(n_pred * 0.7)
        train_m = valid[:split]
        val_m = valid[split:]
        if train_m.sum() < 200 or val_m.sum() < 100:
            continue

        pred, _ = _ridge_predict(features[:split][train_m], actual[:split][train_m], features[split:][val_m])
        y_val = actual[split:][val_m]

        ridge_resid = y_val - pred
        valid_resid = ridge_resid[np.isfinite(ridge_resid)]

        if len(valid_resid) < 100:
            continue

        # Residual statistics
        mean_resid = float(np.mean(valid_resid))
        std_resid = float(np.std(valid_resid))
        skew = float(np.mean((valid_resid - mean_resid)**3) / std_resid**3) if std_resid > 0 else 0
        kurtosis = float(np.mean((valid_resid - mean_resid)**4) / std_resid**4 - 3) if std_resid > 0 else 0

        # Autocorrelation of residual
        if len(valid_resid) > 20:
            ac1 = float(np.corrcoef(valid_resid[:-1], valid_resid[1:])[0, 1])
        else:
            ac1 = 0

        # Residual by time of day
        pred_hours = hours[:n_pred] if hours is not None else None
        val_hours = pred_hours[split:][val_m] if pred_hours is not None else None
        circadian_strength = 0
        if val_hours is not None and len(val_hours) == len(ridge_resid):
            valid_h = val_hours[np.isfinite(ridge_resid)]
            if len(valid_h) > 100:
                # Fit sin/cos to residual
                sin_h = np.sin(2 * np.pi * valid_h / 24.0)
                cos_h = np.cos(2 * np.pi * valid_h / 24.0)
                X = np.column_stack([sin_h, cos_h, np.ones(len(sin_h))])
                try:
                    c = np.linalg.lstsq(X, valid_resid, rcond=None)[0]
                    circadian_amplitude = np.sqrt(c[0]**2 + c[1]**2)
                    circadian_strength = round(circadian_amplitude / std_resid * 100, 1) if std_resid > 0 else 0
                except Exception:
                    pass

        results.append({
            'patient': p['name'],
            'mean_resid': round(mean_resid, 2),
            'std_resid': round(std_resid, 1),
            'skew': round(skew, 2),
            'kurtosis': round(kurtosis, 2),
            'autocorrelation': round(ac1, 3),
            'circadian_pct': circadian_strength,
        })

    detail_parts = [f'{r["patient"]}: std={r["std_resid"]}, AC={r["autocorrelation"]}, circ={r["circadian_pct"]}%'
                    for r in results[:8]]
    mean_std = np.mean([r['std_resid'] for r in results]) if results else 0
    mean_ac = np.mean([r['autocorrelation'] for r in results]) if results else 0
    return {
        'status': 'pass',
        'detail': f'n={len(results)}, mean resid std={mean_std:.1f}, mean AC={mean_ac:.3f}. ' + '; '.join(detail_parts),
        'per_patient': results,
    }


# ---------------------------------------------------------------------------
# EXP-808: Supply-Demand Ratio Feature
# ---------------------------------------------------------------------------
@register('EXP-808', 'Supply-Demand Ratio')
def exp_808(patients, detail=False):
    """Test supply/demand ratio as additional feature for ridge."""
    horizons = {6: '30min', 12: '60min'}
    results = {}

    for h_steps, h_name in horizons.items():
        r2_base = []
        r2_ratio = []

        for p in patients:
            fd = _compute_flux(p)
            bg = fd['bg']
            n = fd['n']
            nr = len(fd['resid'])
            df = p['df']
            hours = _get_hours(df, n)
            if hours is None:
                continue

            n_pred = nr - h_steps
            if n_pred < 500:
                continue

            actual = bg[h_steps:h_steps + n_pred]

            # Base features
            base = _build_features_base(fd, hours, n_pred, h_steps)

            # Add ratio feature
            ratio_feat = np.zeros((n_pred, 10))
            ratio_feat[:, :8] = base
            for i in range(n_pred):
                s = base[i, 1]  # Σsupply
                d = base[i, 2]  # Σdemand
                ratio_feat[i, 8] = s / max(d, 0.01)  # supply/demand ratio
                ratio_feat[i, 9] = s - d  # net flux

            valid = np.all(np.isfinite(ratio_feat), axis=1) & np.isfinite(actual)
            split = int(n_pred * 0.7)
            train_m = valid[:split]
            val_m = valid[split:]
            if train_m.sum() < 200 or val_m.sum() < 100:
                continue

            y_tr = actual[:split][train_m]
            y_va = actual[split:][val_m]

            pred_b, _ = _ridge_predict(base[:split][train_m], y_tr, base[split:][val_m])
            pred_r, _ = _ridge_predict(ratio_feat[:split][train_m], y_tr, ratio_feat[split:][val_m])

            r2_b = _r2(pred_b, y_va)
            r2_r = _r2(pred_r, y_va)

            if np.isfinite(r2_b) and np.isfinite(r2_r):
                r2_base.append(r2_b)
                r2_ratio.append(r2_r)

        mb = np.mean(r2_base) if r2_base else float('nan')
        mr = np.mean(r2_ratio) if r2_ratio else float('nan')
        results[h_name] = {'base': round(mb, 3), 'ratio': round(mr, 3), 'delta': round(mr - mb, 3)}

    detail_str = ', '.join(f'{h}: base={v["base"]}/ratio={v["ratio"]}/Δ={v["delta"]}' for h, v in results.items())
    return {'status': 'pass', 'detail': detail_str, 'results': results}


# ---------------------------------------------------------------------------
# EXP-809: Multi-Horizon Joint Ridge
# ---------------------------------------------------------------------------
@register('EXP-809', 'Multi-Horizon Joint')
def exp_809(patients, detail=False):
    """Train one ridge model to predict multiple horizons simultaneously."""
    horizons = [1, 3, 6, 12]  # 5, 15, 30, 60 min
    horizon_names = ['5min', '15min', '30min', '60min']
    results = {'joint': {}, 'individual': {}}

    # Individual models (baseline)
    for h_steps, h_name in zip(horizons, horizon_names):
        r2_list = []
        for p in patients:
            fd = _compute_flux(p)
            bg = fd['bg']
            n = fd['n']
            nr = len(fd['resid'])
            df = p['df']
            hours = _get_hours(df, n)
            if hours is None:
                continue
            n_pred = nr - max(horizons)
            if n_pred < 500:
                continue

            actual = bg[h_steps:h_steps + n_pred]
            features = _build_features_base(fd, hours, n_pred, h_steps)
            valid = np.all(np.isfinite(features), axis=1) & np.isfinite(actual)
            split = int(n_pred * 0.7)
            train_m = valid[:split]
            val_m = valid[split:]
            if train_m.sum() < 200 or val_m.sum() < 100:
                continue

            pred, _ = _ridge_predict(features[:split][train_m], actual[:split][train_m], features[split:][val_m])
            r2 = _r2(pred, actual[split:][val_m])
            if np.isfinite(r2):
                r2_list.append(r2)

        results['individual'][h_name] = round(np.mean(r2_list), 3) if r2_list else float('nan')

    # Joint model: augment features with horizon indicator
    r2_joint = {h: [] for h in horizon_names}
    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        n = fd['n']
        nr = len(fd['resid'])
        df = p['df']
        hours = _get_hours(df, n)
        if hours is None:
            continue
        n_pred = nr - max(horizons)
        if n_pred < 500:
            continue

        split = int(n_pred * 0.7)

        # Build joint training data
        X_trains = []
        y_trains = []
        X_vals = {h: None for h in horizon_names}
        y_vals = {h: None for h in horizon_names}

        for h_steps, h_name in zip(horizons, horizon_names):
            actual = bg[h_steps:h_steps + n_pred]
            base = _build_features_base(fd, hours, n_pred, h_steps)

            # Add horizon indicator (one-hot style)
            feat = np.zeros((n_pred, 12))
            feat[:, :8] = base
            h_idx = horizons.index(h_steps)
            feat[:, 8 + h_idx] = 1.0  # one-hot horizon

            valid = np.all(np.isfinite(feat), axis=1) & np.isfinite(actual)
            train_m = valid[:split]
            val_m = valid[split:]

            if train_m.sum() < 100 or val_m.sum() < 50:
                continue

            X_trains.append(feat[:split][train_m])
            y_trains.append(actual[:split][train_m])
            X_vals[h_name] = feat[split:][val_m]
            y_vals[h_name] = actual[split:][val_m]

        if len(X_trains) < 4:
            continue

        X_joint = np.vstack(X_trains)
        y_joint = np.concatenate(y_trains)

        for h_name in horizon_names:
            if X_vals[h_name] is not None:
                pred, _ = _ridge_predict(X_joint, y_joint, X_vals[h_name], lam=10.0)
                r2 = _r2(pred, y_vals[h_name])
                if np.isfinite(r2):
                    r2_joint[h_name].append(r2)

    for h_name in horizon_names:
        results['joint'][h_name] = round(np.mean(r2_joint[h_name]), 3) if r2_joint[h_name] else float('nan')

    detail_parts = []
    for h in horizon_names:
        indiv = results['individual'].get(h, float('nan'))
        joint = results['joint'].get(h, float('nan'))
        delta = round(joint - indiv, 3) if np.isfinite(joint) and np.isfinite(indiv) else float('nan')
        detail_parts.append(f'{h}: indiv={indiv}/joint={joint}/Δ={delta}')

    return {'status': 'pass', 'detail': ', '.join(detail_parts), 'results': results}


# ---------------------------------------------------------------------------
# EXP-810: Ridge vs Lasso vs ElasticNet
# ---------------------------------------------------------------------------
@register('EXP-810', 'Ridge vs Lasso vs ElasticNet')
def exp_810(patients, detail=False):
    """Compare L2 (ridge), L1 (lasso), and mixed regularization."""
    h_steps = 12  # 60min
    results = {'ridge': [], 'lasso': [], 'elasticnet': []}

    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        n = fd['n']
        nr = len(fd['resid'])
        df = p['df']
        hours = _get_hours(df, n)
        if hours is None:
            continue

        n_pred = nr - h_steps
        if n_pred < 500:
            continue

        actual = bg[h_steps:h_steps + n_pred]
        features = _build_features_base(fd, hours, n_pred, h_steps)

        valid = np.all(np.isfinite(features), axis=1) & np.isfinite(actual)
        split = int(n_pred * 0.7)
        train_m = valid[:split]
        val_m = valid[split:]
        if train_m.sum() < 200 or val_m.sum() < 100:
            continue

        X_tr = features[:split][train_m]
        y_tr = actual[:split][train_m]
        X_va = features[split:][val_m]
        y_va = actual[split:][val_m]

        # Ridge (L2)
        pred_ridge, _ = _ridge_predict(X_tr, y_tr, X_va, lam=1.0)
        r2_ridge = _r2(pred_ridge, y_va)

        # Lasso (L1) via coordinate descent (simplified)
        # Use iterative soft-thresholding
        n_feat = X_tr.shape[1]
        w_lasso = np.linalg.lstsq(X_tr, y_tr, rcond=None)[0]  # Initialize with OLS
        lam_l1 = 0.1
        for iteration in range(100):
            for j in range(n_feat):
                r_j = y_tr - X_tr @ w_lasso + X_tr[:, j] * w_lasso[j]
                z_j = X_tr[:, j] @ r_j / len(y_tr)
                norm_j = np.sum(X_tr[:, j]**2) / len(y_tr)
                if norm_j > 0:
                    w_lasso[j] = np.sign(z_j) * max(0, abs(z_j) - lam_l1) / norm_j
        pred_lasso = X_va @ w_lasso
        r2_lasso = _r2(pred_lasso, y_va)

        # ElasticNet (L1 + L2)
        w_en = np.linalg.lstsq(X_tr, y_tr, rcond=None)[0]
        lam_l1_en = 0.05
        lam_l2_en = 0.5
        for iteration in range(100):
            for j in range(n_feat):
                r_j = y_tr - X_tr @ w_en + X_tr[:, j] * w_en[j]
                z_j = X_tr[:, j] @ r_j / len(y_tr)
                norm_j = np.sum(X_tr[:, j]**2) / len(y_tr) + lam_l2_en
                if norm_j > 0:
                    w_en[j] = np.sign(z_j) * max(0, abs(z_j) - lam_l1_en) / norm_j
        pred_en = X_va @ w_en
        r2_en = _r2(pred_en, y_va)

        if all(np.isfinite([r2_ridge, r2_lasso, r2_en])):
            results['ridge'].append(r2_ridge)
            results['lasso'].append(r2_lasso)
            results['elasticnet'].append(r2_en)

    means = {k: round(np.mean(v), 3) if v else float('nan') for k, v in results.items()}
    best = max(means, key=lambda k: means[k] if np.isfinite(means[k]) else -999)
    return {
        'status': 'pass',
        'detail': f'Ridge={means["ridge"]}, Lasso={means["lasso"]}, EN={means["elasticnet"]}. Best: {best}',
        'results': means,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description='EXP-801-810: Ridge Deep Dive')
    parser.add_argument('--max-patients', type=int, default=11)
    parser.add_argument('--only', type=str, default=None)
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    args = parser.parse_args()

    print(f'Loading patients (max={args.max_patients})...')
    patients = load_patients(PATIENTS_DIR, max_patients=args.max_patients)
    print(f'Loaded {len(patients)} patients\n')

    to_run = {args.only: EXPERIMENTS[args.only]} if args.only else EXPERIMENTS
    passed = 0
    failed = 0
    results_all = {}

    for exp_id, exp_info in to_run.items():
        print(f'\n{"="*60}')
        print(f'Running {exp_id}: {exp_info["name"]}')
        print(f'{"="*60}')
        t0 = time.time()
        try:
            result = exp_info['func'](patients, detail=args.detail)
            elapsed = time.time() - t0
            result['exp_id'] = exp_id
            result['name'] = exp_info['name']
            result['elapsed'] = round(elapsed, 1)
            results_all[exp_id] = result
            status = result.get('status', 'unknown')
            if status == 'pass':
                passed += 1
                print(f'  Status: pass ({elapsed:.1f}s)')
            else:
                failed += 1
                print(f'  Status: FAIL ({elapsed:.1f}s)')
            if 'detail' in result:
                print(f'  Detail: {result["detail"][:200]}')
        except Exception as e:
            elapsed = time.time() - t0
            failed += 1
            import traceback
            traceback.print_exc()
            print(f'  Status: FAIL ({elapsed:.1f}s)')
            print(f'  Error: {e}')
            results_all[exp_id] = {
                'status': 'fail', 'error': str(e),
                'exp_id': exp_id, 'name': exp_info['name'], 'elapsed': round(elapsed, 1)
            }

    print(f'\n{"="*60}')
    print('SUMMARY')
    print(f'{"="*60}')
    print(f'Passed: {passed}/{passed+failed}, Failed: {failed}/{passed+failed}')
    for exp_id, r in results_all.items():
        status = 'V' if r.get('status') == 'pass' else 'X'
        detail = r.get('detail', r.get('error', ''))[:100]
        print(f'  {status} {exp_id} {r.get("name", "")}: {detail}')

    if args.save:
        save_dir = Path(__file__).parent.parent.parent / 'externals' / 'experiments'
        save_dir.mkdir(parents=True, exist_ok=True)
        for exp_id, r in results_all.items():
            slug = f'{exp_id.lower().replace("-", "_")}_{r.get("name", "").lower().replace(" ", "_")[:30]}'
            fname = save_dir / f'{slug}.json'
            with open(fname, 'w') as f:
                json.dump(r, f, indent=2, default=str)
            print(f'  Saved: {fname.name}')


if __name__ == '__main__':
    main()
