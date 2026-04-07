#!/usr/bin/env python3
"""EXP-861–870: Multi-Horizon Cascade & Meal-Phase Exploitation

Multi-horizon predictions (EXP-857) yielded +0.012, the best single lever
found since enhanced features. This wave deepens that approach and explores
meal-size estimation from BG acceleration patterns. The goal is to extract
maximum value from the ONE remaining information source: trajectory evidence
from shorter prediction horizons.

EXP-861: Multi-Horizon Cascade with All Horizons (5/10/15/20/25/30/45min)
EXP-862: Stacked Generalization (train 2nd-level model on horizon predictions)
EXP-863: Horizon Confidence Features (short-horizon R² as prediction difficulty)
EXP-864: BG Acceleration Profile as Meal-Size Proxy
EXP-865: Rolling Prediction Update (average predictions made 5/10/15min ago)
EXP-866: Feature Interaction Terms (BG × velocity, supply × demand)
EXP-867: Prediction Disagreement as Uncertainty Feature
EXP-868: Momentum Features (sustained rise/fall duration and magnitude)
EXP-869: Supply-Demand Imbalance Duration
EXP-870: Full Feature Engineering Benchmark (all winning features combined)
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


# ── EXP-861: Full Multi-Horizon Cascade ──────────────────────────────────────

@register('EXP-861', 'Full Multi-Horizon Cascade')
def exp_861(patients, detail=False):
    """Use predictions at all shorter horizons (5/10/15/20/25/30/45min) as features.

    EXP-857 used only 3 horizons. Test whether more horizons provide more info.
    """
    h_steps = 12
    lam = 10.0
    start = 24
    all_horizons = [1, 2, 3, 4, 5, 6, 9]  # 5/10/15/20/25/30/45min

    base_r2s, multi_r2s = [], []
    configs = {}

    # Also test subsets
    horizon_configs = {
        '3_horizons': [1, 3, 6],
        '5_horizons': [1, 2, 3, 6, 9],
        '7_horizons': all_horizons,
    }

    for config_name, horizons in horizon_configs.items():
        c_r2s = []

        for p in patients:
            fd = _compute_flux(p)
            bg = fd['bg']
            n = fd['n']
            hours = _get_hours(p['df'], n)
            nr = len(fd['resid'])
            n_pred = nr - h_steps
            usable = n_pred - start
            if usable < 200:
                continue

            actual = bg[h_steps + 1 + start: h_steps + 1 + start + usable]
            features, _ = _build_enhanced_features(fd, bg, hours, n_pred, h_steps, start)
            split = int(0.8 * usable)

            # Train horizon models
            h_preds, _ = _train_horizon_models(fd, bg, hours, nr, start, usable, split, horizons)
            if len(h_preds) < 2:
                continue

            # Augment features
            extra = np.column_stack([h_preds[h] for h in sorted(h_preds)])
            combined = np.hstack([features, extra])

            X_tr, X_val = features[:split], features[split:]
            X_tr_c, X_val_c = combined[:split], combined[split:]
            y_tr, y_val = actual[:split], actual[split:]

            valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
            valid_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
            valid_tr_c = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_c), axis=1)
            valid_val_c = np.isfinite(y_val) & np.all(np.isfinite(X_val_c), axis=1)

            if config_name == '3_horizons':
                pred_base, _ = _ridge_predict(X_tr[valid_tr], y_tr[valid_tr], X_val, lam=lam * 3)
                r2_base = _r2(pred_base[valid_val], y_val[valid_val])
                if np.isfinite(r2_base):
                    base_r2s.append(r2_base)

            pred_multi, _ = _ridge_predict(X_tr_c[valid_tr_c], y_tr[valid_tr_c],
                                            X_val_c, lam=lam * 4)
            r2_multi = _r2(pred_multi[valid_val_c], y_val[valid_val_c])
            if np.isfinite(r2_multi):
                c_r2s.append(r2_multi)

        configs[config_name] = round(float(np.mean(c_r2s)), 3) if c_r2s else None

    results = {
        'base': round(float(np.mean(base_r2s)), 3) if base_r2s else None,
        'configs': configs,
        'best_config': max(configs, key=lambda k: configs[k] or 0),
    }

    return {
        'status': 'pass',
        'detail': f"base={results['base']}, configs={configs}",
        'results': results,
    }


# ── EXP-862: Stacked Generalization ──────────────────────────────────────────

@register('EXP-862', 'Stacked Generalization')
def exp_862(patients, detail=False):
    """Two-level stacking: Level-1 predicts at each horizon, Level-2 combines.

    Level-1: Train separate models at 5/15/30/60min using base features.
    Level-2: Use ONLY horizon predictions as features (no raw features).
    Compare with: raw features + horizon predictions (from EXP-857).
    """
    h_steps = 12
    lam = 10.0
    start = 24
    horizons = [1, 3, 6, 12]  # 5/15/30/60min

    base_r2s, stacked_only_r2s, stacked_full_r2s = [], [], []

    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        n = fd['n']
        hours = _get_hours(p['df'], n)
        nr = len(fd['resid'])
        n_pred = nr - h_steps
        usable = n_pred - start
        if usable < 200:
            continue

        actual = bg[h_steps + 1 + start: h_steps + 1 + start + usable]
        features, _ = _build_enhanced_features(fd, bg, hours, n_pred, h_steps, start)
        split = int(0.8 * usable)

        y_tr, y_val = actual[:split], actual[split:]

        # Level-1: train horizon models
        h_preds, _ = _train_horizon_models(fd, bg, hours, nr, start, usable, split, horizons)
        if len(h_preds) < 3:
            continue

        # Stack predictions
        stack_feats = np.column_stack([h_preds[h] for h in sorted(h_preds)])
        # Add bias and differences between horizons
        n_h = stack_feats.shape[1]
        diffs = []
        for i in range(n_h - 1):
            diffs.append(stack_feats[:, i + 1] - stack_feats[:, i])
        if diffs:
            stack_feats = np.hstack([stack_feats, np.column_stack(diffs),
                                      np.ones((usable, 1))])

        combined = np.hstack([features, stack_feats])

        # Base model
        X_tr_b, X_val_b = features[:split], features[split:]
        valid_tr_b = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_b), axis=1)
        valid_val_b = np.isfinite(y_val) & np.all(np.isfinite(X_val_b), axis=1)
        pred_base, _ = _ridge_predict(X_tr_b[valid_tr_b], y_tr[valid_tr_b], X_val_b, lam=lam * 3)
        r2_base = _r2(pred_base[valid_val_b], y_val[valid_val_b])

        # Stacked-only (Level-2 on horizon predictions only)
        X_tr_s, X_val_s = stack_feats[:split], stack_feats[split:]
        valid_tr_s = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_s), axis=1)
        valid_val_s = np.isfinite(y_val) & np.all(np.isfinite(X_val_s), axis=1)
        pred_stack, _ = _ridge_predict(X_tr_s[valid_tr_s], y_tr[valid_tr_s], X_val_s, lam=lam)
        r2_stack = _r2(pred_stack[valid_val_s], y_val[valid_val_s])

        # Full combined
        X_tr_c, X_val_c = combined[:split], combined[split:]
        valid_tr_c = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_c), axis=1)
        valid_val_c = np.isfinite(y_val) & np.all(np.isfinite(X_val_c), axis=1)
        pred_full, _ = _ridge_predict(X_tr_c[valid_tr_c], y_tr[valid_tr_c], X_val_c, lam=lam * 5)
        r2_full = _r2(pred_full[valid_val_c], y_val[valid_val_c])

        if np.isfinite(r2_base) and np.isfinite(r2_stack) and np.isfinite(r2_full):
            base_r2s.append(r2_base)
            stacked_only_r2s.append(r2_stack)
            stacked_full_r2s.append(r2_full)

    results = {
        'base_16feat': round(float(np.mean(base_r2s)), 3),
        'stacked_horizon_only': round(float(np.mean(stacked_only_r2s)), 3),
        'stacked_full': round(float(np.mean(stacked_full_r2s)), 3),
        'improvement_stack_only': round(float(np.mean(stacked_only_r2s) - np.mean(base_r2s)), 3),
        'improvement_full': round(float(np.mean(stacked_full_r2s) - np.mean(base_r2s)), 3),
    }

    return {
        'status': 'pass',
        'detail': f"base={results['base_16feat']}, stack_only={results['stacked_horizon_only']}, full={results['stacked_full']}",
        'results': results,
    }


# ── EXP-863: Horizon Confidence Features ─────────────────────────────────────

@register('EXP-863', 'Horizon Confidence Features')
def exp_863(patients, detail=False):
    """Use short-horizon prediction ERRORS as confidence/difficulty features.

    For each test point, compute rolling MAE of short-horizon predictions
    over past 2 hours. High recent error → current point is hard to predict.
    """
    h_steps = 12
    lam = 10.0
    start = 24
    short_horizon = 1  # 5min

    base_r2s, conf_r2s = [], []

    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        n = fd['n']
        hours = _get_hours(p['df'], n)
        nr = len(fd['resid'])
        n_pred = nr - h_steps
        usable = n_pred - start
        if usable < 200:
            continue

        actual_60 = bg[h_steps + 1 + start: h_steps + 1 + start + usable]
        features, _ = _build_enhanced_features(fd, bg, hours, n_pred, h_steps, start)
        split = int(0.8 * usable)

        # Train 5min model and get predictions
        n_pred_5 = nr - short_horizon
        if n_pred_5 - start < usable:
            continue

        actual_5 = bg[short_horizon + 1 + start: short_horizon + 1 + start + usable]
        feat_5 = _build_features_base(fd, hours, n_pred_5, short_horizon)
        feat_5 = feat_5[start:start + usable]

        X_tr_5 = feat_5[:split]
        y_tr_5 = actual_5[:split]
        valid_5 = np.isfinite(y_tr_5) & np.all(np.isfinite(X_tr_5), axis=1)
        if valid_5.sum() < 50:
            continue

        _, w_5 = _ridge_predict(X_tr_5[valid_5], y_tr_5[valid_5], X_tr_5[:1], lam=0.1)
        if w_5 is None:
            continue

        pred_5 = feat_5 @ w_5
        errors_5 = np.abs(actual_5 - pred_5)

        # Compute rolling error features
        conf_feats = np.zeros((usable, 4))
        for i in range(usable):
            # Rolling MAE over past 24 steps (2h)
            window = errors_5[max(0, i - 24):i + 1]
            valid_w = window[np.isfinite(window)]
            if len(valid_w) > 0:
                conf_feats[i, 0] = np.mean(valid_w)
                conf_feats[i, 1] = np.max(valid_w)
                conf_feats[i, 2] = np.std(valid_w)
            # Current 5min prediction (already proved useful)
            conf_feats[i, 3] = pred_5[i] if np.isfinite(pred_5[i]) else bg[start + i]

        combined = np.hstack([features, conf_feats])

        X_tr_b, X_val_b = features[:split], features[split:]
        X_tr_c, X_val_c = combined[:split], combined[split:]
        y_tr, y_val = actual_60[:split], actual_60[split:]

        valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_b), axis=1)
        valid_val = np.isfinite(y_val) & np.all(np.isfinite(X_val_b), axis=1)
        valid_tr_c = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_c), axis=1)
        valid_val_c = np.isfinite(y_val) & np.all(np.isfinite(X_val_c), axis=1)

        pred_base, _ = _ridge_predict(X_tr_b[valid_tr], y_tr[valid_tr], X_val_b, lam=lam * 3)
        pred_conf, _ = _ridge_predict(X_tr_c[valid_tr_c], y_tr[valid_tr_c], X_val_c, lam=lam * 4)

        r2_base = _r2(pred_base[valid_val], y_val[valid_val])
        r2_conf = _r2(pred_conf[valid_val_c], y_val[valid_val_c])

        if np.isfinite(r2_base) and np.isfinite(r2_conf):
            base_r2s.append(r2_base)
            conf_r2s.append(r2_conf)

    results = {
        'base': round(float(np.mean(base_r2s)), 3),
        'with_confidence': round(float(np.mean(conf_r2s)), 3),
        'improvement': round(float(np.mean(conf_r2s) - np.mean(base_r2s)), 3),
    }

    return {
        'status': 'pass',
        'detail': f"base={results['base']}, +confidence={results['with_confidence']}, Δ={results['improvement']:+.3f}",
        'results': results,
    }


# ── EXP-864: BG Acceleration as Meal-Size Proxy ──────────────────────────────

@register('EXP-864', 'BG Acceleration as Meal-Size Proxy')
def exp_864(patients, detail=False):
    """Use BG acceleration patterns to estimate meal size impact.

    Features: max acceleration in past 30/60/90 min, integrated acceleration,
    time since peak acceleration. These proxy for meal size without explicit
    carb data.
    """
    h_steps = 12
    lam = 10.0
    start = 24

    base_r2s, meal_r2s = [], []

    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        n = fd['n']
        hours = _get_hours(p['df'], n)
        nr = len(fd['resid'])
        n_pred = nr - h_steps
        usable = n_pred - start
        if usable < 200:
            continue

        actual = bg[h_steps + 1 + start: h_steps + 1 + start + usable]
        features, _ = _build_enhanced_features(fd, bg, hours, n_pred, h_steps, start)
        split = int(0.8 * usable)

        # Compute acceleration at each point
        accel = np.zeros(n)
        for i in range(2, n):
            if np.isfinite(bg[i]) and np.isfinite(bg[i-1]) and np.isfinite(bg[i-2]):
                accel[i] = bg[i] - 2 * bg[i-1] + bg[i-2]

        # Build meal-size proxy features
        meal_feats = np.zeros((usable, 8))
        for i in range(usable):
            orig = i + start

            # Max positive acceleration in past 6/12/18 steps (30/60/90min)
            for j, window_size in enumerate([6, 12, 18]):
                w = accel[max(0, orig - window_size):orig + 1]
                valid_w = w[np.isfinite(w)]
                if len(valid_w) > 0:
                    meal_feats[i, j] = np.max(valid_w)

            # Integrated positive acceleration in past 60min
            w = accel[max(0, orig - 12):orig + 1]
            valid_w = w[np.isfinite(w)]
            if len(valid_w) > 0:
                meal_feats[i, 3] = np.sum(np.maximum(valid_w, 0))

            # Time since peak acceleration (steps)
            w = accel[max(0, orig - 24):orig + 1]
            valid_w = w[np.isfinite(w)]
            if len(valid_w) > 0:
                peak_idx = np.argmax(valid_w)
                meal_feats[i, 4] = (len(valid_w) - peak_idx) * 5.0 / 60.0  # hours

            # BG rise over past 30min
            if orig >= 6 and np.isfinite(bg[orig]) and np.isfinite(bg[orig - 6]):
                meal_feats[i, 5] = bg[orig] - bg[orig - 6]

            # Supply integrated over past 60min
            s = fd['supply'][max(0, orig - 12):orig + 1]
            meal_feats[i, 6] = np.sum(s[np.isfinite(s)])

            # Supply × acceleration interaction
            meal_feats[i, 7] = meal_feats[i, 6] * meal_feats[i, 3]

        combined = np.hstack([features, meal_feats])

        X_tr_b, X_val_b = features[:split], features[split:]
        X_tr_c, X_val_c = combined[:split], combined[split:]
        y_tr, y_val = actual[:split], actual[split:]

        valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_b), axis=1)
        valid_val = np.isfinite(y_val) & np.all(np.isfinite(X_val_b), axis=1)
        valid_tr_c = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_c), axis=1)
        valid_val_c = np.isfinite(y_val) & np.all(np.isfinite(X_val_c), axis=1)

        pred_base, _ = _ridge_predict(X_tr_b[valid_tr], y_tr[valid_tr], X_val_b, lam=lam * 3)
        pred_meal, _ = _ridge_predict(X_tr_c[valid_tr_c], y_tr[valid_tr_c], X_val_c, lam=lam * 4)

        r2_base = _r2(pred_base[valid_val], y_val[valid_val])
        r2_meal = _r2(pred_meal[valid_val_c], y_val[valid_val_c])

        if np.isfinite(r2_base) and np.isfinite(r2_meal):
            base_r2s.append(r2_base)
            meal_r2s.append(r2_meal)

    results = {
        'base': round(float(np.mean(base_r2s)), 3),
        'with_meal_proxy': round(float(np.mean(meal_r2s)), 3),
        'improvement': round(float(np.mean(meal_r2s) - np.mean(base_r2s)), 3),
    }

    return {
        'status': 'pass',
        'detail': f"base={results['base']}, +meal={results['with_meal_proxy']}, Δ={results['improvement']:+.3f}",
        'results': results,
    }


# ── EXP-865: Rolling Prediction Update ───────────────────────────────────────

@register('EXP-865', 'Rolling Prediction Update')
def exp_865(patients, detail=False):
    """Average predictions from multiple origins for the same target time.

    At time t, we have:
    - A 60min prediction made at time t (standard)
    - A 55min prediction made at time t-1 (predicting t+12 from t-1)
    - A 50min prediction made at time t-2 (predicting t+12 from t-2)
    - etc.

    Average these predictions, weighted by recency. This is VALID because
    each prediction only uses information from its origin time.
    """
    h_steps = 12
    lam = 10.0
    start = 24
    n_origins = 6  # Combine predictions from t, t-1, ..., t-5

    base_r2s, rolling_r2s = [], []

    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        n = fd['n']
        hours = _get_hours(p['df'], n)
        nr = len(fd['resid'])
        n_pred = nr - h_steps
        usable = n_pred - start
        if usable < 200:
            continue

        actual = bg[h_steps + 1 + start: h_steps + 1 + start + usable]
        split = int(0.8 * usable)
        y_tr, y_val = actual[:split], actual[split:]

        # Train models at different horizons (12, 13, 14, 15, 16, 17 steps)
        # These predict the SAME target but from different origin times
        origin_preds_val = []

        for offset in range(n_origins):
            h = h_steps + offset  # 12, 13, 14, 15, 16, 17
            n_pred_h = nr - h
            if n_pred_h - start < usable:
                continue

            # Target: bg at time (start + i + h + 1) for each i
            # For offset=0, this is the standard 60min target
            # For offset=1, this predicts the same target from 1 step earlier

            actual_h = bg[h + 1 + start: h + 1 + start + usable]
            feat_h = _build_features_base(fd, hours, n_pred_h, h)
            feat_h = feat_h[start:start + usable]

            X_tr_h = feat_h[:split]
            y_tr_h = actual_h[:split]
            valid_h = np.isfinite(y_tr_h) & np.all(np.isfinite(X_tr_h), axis=1)

            if valid_h.sum() < 50:
                continue

            pred_h, _ = _ridge_predict(X_tr_h[valid_h], y_tr_h[valid_h], feat_h[split:], lam=lam)
            origin_preds_val.append(pred_h)

        if len(origin_preds_val) < 2:
            continue

        # Base: just the h_steps=12 prediction
        features, _ = _build_enhanced_features(fd, bg, hours, n_pred, h_steps, start)
        X_tr_b = features[:split]
        X_val_b = features[split:]
        valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_b), axis=1)
        valid_val = np.isfinite(y_val) & np.all(np.isfinite(X_val_b), axis=1)

        pred_base, _ = _ridge_predict(X_tr_b[valid_tr], y_tr[valid_tr], X_val_b, lam=lam * 3)
        r2_base = _r2(pred_base[valid_val], y_val[valid_val])

        # Rolling average: weight by 1/offset (most recent gets highest weight)
        n_val = len(y_val)
        weighted_sum = np.zeros(n_val)
        weight_sum = np.zeros(n_val)

        for k, pred_k in enumerate(origin_preds_val):
            w = 1.0 / (k + 1)
            # Each pred_k predicts targets shifted by offset steps
            # Need to align to same target indices
            # pred_k[i] predicts bg at time start + split + i + h_steps + k + 1
            # We want to match it to actual[split + i + k] = bg at time start + split + i + k + h_steps + 1
            # So pred_k[i] aligns with actual[split + i] when k=0
            # For k>0, pred_k[i] predicts the target at actual[split + i + k]
            # But that's a DIFFERENT target, not the same one

            # Actually let me reconsider. To predict the SAME target time:
            # Standard (k=0): from time t, predict bg(t + 12*5min)
            # k=1: from time t-5min, predict bg(t + 12*5min) = bg((t-1) + 13*5min)
            # So we need horizon = 12+k for origin at t-k

            # pred_k[i] uses features at index (start + i) and horizon (h_steps + k)
            # It predicts bg[start + i + h_steps + k + 1]
            # actual[i] = bg[start + i + h_steps + 1]
            # So pred_k[i-k] should predict actual[i]... if i >= k

            for i in range(k, n_val):
                if i - k < len(pred_k) and np.isfinite(pred_k[i - k]):
                    weighted_sum[i] += w * pred_k[i - k]
                    weight_sum[i] += w

        pred_rolling = np.where(weight_sum > 0, weighted_sum / weight_sum, np.nan)
        r2_rolling = _r2(pred_rolling[valid_val], y_val[valid_val])

        if np.isfinite(r2_base) and np.isfinite(r2_rolling):
            base_r2s.append(r2_base)
            rolling_r2s.append(r2_rolling)

    results = {
        'base': round(float(np.mean(base_r2s)), 3),
        'rolling_avg': round(float(np.mean(rolling_r2s)), 3),
        'improvement': round(float(np.mean(rolling_r2s) - np.mean(base_r2s)), 3),
    }

    return {
        'status': 'pass',
        'detail': f"base={results['base']}, rolling={results['rolling_avg']}, Δ={results['improvement']:+.3f}",
        'results': results,
    }


# ── EXP-866: Feature Interaction Terms ────────────────────────────────────────

@register('EXP-866', 'Feature Interaction Terms')
def exp_866(patients, detail=False):
    """Add pairwise interactions between key features.

    bg × velocity, bg × supply, supply × demand, velocity × supply, etc.
    These capture nonlinear effects in a linear model.
    """
    h_steps = 12
    lam = 10.0
    start = 24

    base_r2s, interact_r2s = [], []

    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        n = fd['n']
        hours = _get_hours(p['df'], n)
        nr = len(fd['resid'])
        n_pred = nr - h_steps
        usable = n_pred - start
        if usable < 200:
            continue

        actual = bg[h_steps + 1 + start: h_steps + 1 + start + usable]
        features, _ = _build_enhanced_features(fd, bg, hours, n_pred, h_steps, start)
        split = int(0.8 * usable)

        # Key interaction pairs (using enhanced feature indices)
        # 0:bg, 1:supply, 2:demand, 8:velocity, 9:accel, 13:window_std
        interactions = np.zeros((usable, 8))
        for i in range(usable):
            f = features[i]
            interactions[i, 0] = f[0] * f[8] / 100.0    # bg × velocity
            interactions[i, 1] = f[0] * f[1] * 10       # bg × supply
            interactions[i, 2] = f[1] * f[2] * 100       # supply × demand
            interactions[i, 3] = f[8] * f[1] * 10        # velocity × supply
            interactions[i, 4] = f[8] * f[9]              # velocity × acceleration
            interactions[i, 5] = f[0] * f[13] / 100.0 if f.shape[0] > 13 else 0  # bg × std
            interactions[i, 6] = f[8] * f[2] * 10        # velocity × demand
            interactions[i, 7] = (f[1] - f[2]) * f[0] * 10  # net_flux × bg

        combined = np.hstack([features, interactions])

        X_tr_b, X_val_b = features[:split], features[split:]
        X_tr_c, X_val_c = combined[:split], combined[split:]
        y_tr, y_val = actual[:split], actual[split:]

        valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_b), axis=1)
        valid_val = np.isfinite(y_val) & np.all(np.isfinite(X_val_b), axis=1)
        valid_tr_c = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_c), axis=1)
        valid_val_c = np.isfinite(y_val) & np.all(np.isfinite(X_val_c), axis=1)

        pred_base, _ = _ridge_predict(X_tr_b[valid_tr], y_tr[valid_tr], X_val_b, lam=lam * 3)
        pred_int, _ = _ridge_predict(X_tr_c[valid_tr_c], y_tr[valid_tr_c], X_val_c, lam=lam * 5)

        r2_base = _r2(pred_base[valid_val], y_val[valid_val])
        r2_int = _r2(pred_int[valid_val_c], y_val[valid_val_c])

        if np.isfinite(r2_base) and np.isfinite(r2_int):
            base_r2s.append(r2_base)
            interact_r2s.append(r2_int)

    results = {
        'base': round(float(np.mean(base_r2s)), 3),
        'with_interactions': round(float(np.mean(interact_r2s)), 3),
        'improvement': round(float(np.mean(interact_r2s) - np.mean(base_r2s)), 3),
    }

    return {
        'status': 'pass',
        'detail': f"base={results['base']}, +interact={results['with_interactions']}, Δ={results['improvement']:+.3f}",
        'results': results,
    }


# ── EXP-867: Prediction Disagreement ─────────────────────────────────────────

@register('EXP-867', 'Prediction Disagreement as Uncertainty')
def exp_867(patients, detail=False):
    """Use disagreement between horizon predictions as uncertainty feature.

    If 5min, 15min, and 30min models all agree on the 60min outcome,
    confidence should be high. If they disagree, uncertainty is high.
    """
    h_steps = 12
    lam = 10.0
    start = 24
    horizons = [1, 3, 6]

    base_r2s, disagree_r2s = [], []

    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        n = fd['n']
        hours = _get_hours(p['df'], n)
        nr = len(fd['resid'])
        n_pred = nr - h_steps
        usable = n_pred - start
        if usable < 200:
            continue

        actual = bg[h_steps + 1 + start: h_steps + 1 + start + usable]
        features, _ = _build_enhanced_features(fd, bg, hours, n_pred, h_steps, start)
        split = int(0.8 * usable)

        h_preds, _ = _train_horizon_models(fd, bg, hours, nr, start, usable, split, horizons)
        if len(h_preds) < 2:
            continue

        preds_array = np.column_stack([h_preds[h] for h in sorted(h_preds)])

        # Disagreement features
        disagree_feats = np.zeros((usable, 4))
        for i in range(usable):
            row = preds_array[i]
            valid_row = row[np.isfinite(row)]
            if len(valid_row) >= 2:
                disagree_feats[i, 0] = np.std(valid_row)          # spread
                disagree_feats[i, 1] = np.max(valid_row) - np.min(valid_row)  # range
                disagree_feats[i, 2] = np.mean(valid_row)         # consensus
                disagree_feats[i, 3] = valid_row[-1] - valid_row[0]  # trend across horizons

        combined = np.hstack([features, disagree_feats])

        X_tr_b, X_val_b = features[:split], features[split:]
        X_tr_c, X_val_c = combined[:split], combined[split:]
        y_tr, y_val = actual[:split], actual[split:]

        valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_b), axis=1)
        valid_val = np.isfinite(y_val) & np.all(np.isfinite(X_val_b), axis=1)
        valid_tr_c = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_c), axis=1)
        valid_val_c = np.isfinite(y_val) & np.all(np.isfinite(X_val_c), axis=1)

        pred_base, _ = _ridge_predict(X_tr_b[valid_tr], y_tr[valid_tr], X_val_b, lam=lam * 3)
        pred_dis, _ = _ridge_predict(X_tr_c[valid_tr_c], y_tr[valid_tr_c], X_val_c, lam=lam * 4)

        r2_base = _r2(pred_base[valid_val], y_val[valid_val])
        r2_dis = _r2(pred_dis[valid_val_c], y_val[valid_val_c])

        if np.isfinite(r2_base) and np.isfinite(r2_dis):
            base_r2s.append(r2_base)
            disagree_r2s.append(r2_dis)

    results = {
        'base': round(float(np.mean(base_r2s)), 3),
        'with_disagreement': round(float(np.mean(disagree_r2s)), 3),
        'improvement': round(float(np.mean(disagree_r2s) - np.mean(base_r2s)), 3),
    }

    return {
        'status': 'pass',
        'detail': f"base={results['base']}, +disagree={results['with_disagreement']}, Δ={results['improvement']:+.3f}",
        'results': results,
    }


# ── EXP-868: Momentum Features ───────────────────────────────────────────────

@register('EXP-868', 'Momentum Features')
def exp_868(patients, detail=False):
    """Compute momentum features: sustained rise/fall duration and magnitude.

    Duration of current trend (how long has BG been consistently rising/falling),
    total magnitude of current trend, and whether trend is accelerating or decelerating.
    """
    h_steps = 12
    lam = 10.0
    start = 24

    base_r2s, mom_r2s = [], []

    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        n = fd['n']
        hours = _get_hours(p['df'], n)
        nr = len(fd['resid'])
        n_pred = nr - h_steps
        usable = n_pred - start
        if usable < 200:
            continue

        actual = bg[h_steps + 1 + start: h_steps + 1 + start + usable]
        features, _ = _build_enhanced_features(fd, bg, hours, n_pred, h_steps, start)
        split = int(0.8 * usable)

        # Compute momentum features
        mom_feats = np.zeros((usable, 6))
        for i in range(usable):
            orig = i + start

            # Duration of current trend (consecutive same-direction changes)
            vel = bg[orig] - bg[orig - 1] if orig >= 1 and np.isfinite(bg[orig]) and np.isfinite(bg[orig - 1]) else 0
            trend_dir = 1 if vel > 0.5 else (-1 if vel < -0.5 else 0)
            duration = 0
            magnitude = 0
            for j in range(1, min(49, orig)):
                if orig - j < 1:
                    break
                v = bg[orig - j + 1] - bg[orig - j] if np.isfinite(bg[orig - j + 1]) and np.isfinite(bg[orig - j]) else 0
                d = 1 if v > 0.5 else (-1 if v < -0.5 else 0)
                if d == trend_dir and trend_dir != 0:
                    duration += 1
                    magnitude += v
                else:
                    break

            mom_feats[i, 0] = duration * 5.0 / 60.0  # hours
            mom_feats[i, 1] = magnitude              # total mg/dL change

            # Trend acceleration: is the velocity increasing or decreasing?
            if orig >= 6:
                vel_now = bg[orig] - bg[orig - 1] if np.isfinite(bg[orig]) and np.isfinite(bg[orig - 1]) else 0
                vel_30m = bg[orig - 6] - bg[orig - 7] if np.isfinite(bg[orig - 6]) and np.isfinite(bg[orig - 7]) else 0
                mom_feats[i, 2] = vel_now - vel_30m  # velocity change over 30min

            # Max excursion from recent mean
            if orig >= 12:
                w = bg[orig - 12:orig + 1]
                valid_w = w[np.isfinite(w)]
                if len(valid_w) >= 3:
                    mom_feats[i, 3] = bg[orig] - np.mean(valid_w) if np.isfinite(bg[orig]) else 0
                    mom_feats[i, 4] = np.max(valid_w) - np.min(valid_w)

            # Supply-demand momentum
            if orig >= 6:
                s_now = np.sum(fd['supply'][max(0, orig - 6):orig + 1])
                d_now = np.sum(fd['demand'][max(0, orig - 6):orig + 1])
                mom_feats[i, 5] = s_now - d_now  # net flux momentum

        combined = np.hstack([features, mom_feats])

        X_tr_b, X_val_b = features[:split], features[split:]
        X_tr_c, X_val_c = combined[:split], combined[split:]
        y_tr, y_val = actual[:split], actual[split:]

        valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_b), axis=1)
        valid_val = np.isfinite(y_val) & np.all(np.isfinite(X_val_b), axis=1)
        valid_tr_c = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_c), axis=1)
        valid_val_c = np.isfinite(y_val) & np.all(np.isfinite(X_val_c), axis=1)

        pred_base, _ = _ridge_predict(X_tr_b[valid_tr], y_tr[valid_tr], X_val_b, lam=lam * 3)
        pred_mom, _ = _ridge_predict(X_tr_c[valid_tr_c], y_tr[valid_tr_c], X_val_c, lam=lam * 4)

        r2_base = _r2(pred_base[valid_val], y_val[valid_val])
        r2_mom = _r2(pred_mom[valid_val_c], y_val[valid_val_c])

        if np.isfinite(r2_base) and np.isfinite(r2_mom):
            base_r2s.append(r2_base)
            mom_r2s.append(r2_mom)

    results = {
        'base': round(float(np.mean(base_r2s)), 3),
        'with_momentum': round(float(np.mean(mom_r2s)), 3),
        'improvement': round(float(np.mean(mom_r2s) - np.mean(base_r2s)), 3),
    }

    return {
        'status': 'pass',
        'detail': f"base={results['base']}, +momentum={results['with_momentum']}, Δ={results['improvement']:+.3f}",
        'results': results,
    }


# ── EXP-869: Supply-Demand Imbalance Duration ────────────────────────────────

@register('EXP-869', 'Supply-Demand Imbalance Duration')
def exp_869(patients, detail=False):
    """Track how long supply has exceeded demand (or vice versa) continuously.

    Sustained imbalance predicts larger future BG changes than transient spikes.
    """
    h_steps = 12
    lam = 10.0
    start = 24

    base_r2s, imb_r2s = [], []

    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        n = fd['n']
        hours = _get_hours(p['df'], n)
        nr = len(fd['resid'])
        n_pred = nr - h_steps
        usable = n_pred - start
        if usable < 200:
            continue

        actual = bg[h_steps + 1 + start: h_steps + 1 + start + usable]
        features, _ = _build_enhanced_features(fd, bg, hours, n_pred, h_steps, start)
        split = int(0.8 * usable)

        # Compute supply-demand imbalance features
        net_flux = fd['supply'] - fd['demand']
        imb_feats = np.zeros((usable, 4))

        for i in range(usable):
            orig = i + start

            # Duration of current imbalance direction
            current_sign = 1 if net_flux[orig] > 0.001 else (-1 if net_flux[orig] < -0.001 else 0)
            duration = 0
            total_imbalance = 0
            for j in range(min(49, orig)):
                idx = orig - j
                s = 1 if net_flux[idx] > 0.001 else (-1 if net_flux[idx] < -0.001 else 0)
                if s == current_sign and current_sign != 0:
                    duration += 1
                    total_imbalance += net_flux[idx]
                else:
                    break

            imb_feats[i, 0] = duration * 5.0 / 60.0  # hours of sustained imbalance
            imb_feats[i, 1] = total_imbalance          # integrated imbalance

            # Recent (30min) vs distant (60-90min) imbalance
            recent = np.sum(net_flux[max(0, orig - 6):orig + 1])
            distant = np.sum(net_flux[max(0, orig - 18):max(0, orig - 6)])
            imb_feats[i, 2] = recent
            imb_feats[i, 3] = recent - distant  # imbalance trend

        combined = np.hstack([features, imb_feats])

        X_tr_b, X_val_b = features[:split], features[split:]
        X_tr_c, X_val_c = combined[:split], combined[split:]
        y_tr, y_val = actual[:split], actual[split:]

        valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_b), axis=1)
        valid_val = np.isfinite(y_val) & np.all(np.isfinite(X_val_b), axis=1)
        valid_tr_c = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_c), axis=1)
        valid_val_c = np.isfinite(y_val) & np.all(np.isfinite(X_val_c), axis=1)

        pred_base, _ = _ridge_predict(X_tr_b[valid_tr], y_tr[valid_tr], X_val_b, lam=lam * 3)
        pred_imb, _ = _ridge_predict(X_tr_c[valid_tr_c], y_tr[valid_tr_c], X_val_c, lam=lam * 4)

        r2_base = _r2(pred_base[valid_val], y_val[valid_val])
        r2_imb = _r2(pred_imb[valid_val_c], y_val[valid_val_c])

        if np.isfinite(r2_base) and np.isfinite(r2_imb):
            base_r2s.append(r2_base)
            imb_r2s.append(r2_imb)

    results = {
        'base': round(float(np.mean(base_r2s)), 3),
        'with_imbalance': round(float(np.mean(imb_r2s)), 3),
        'improvement': round(float(np.mean(imb_r2s) - np.mean(base_r2s)), 3),
    }

    return {
        'status': 'pass',
        'detail': f"base={results['base']}, +imbalance={results['with_imbalance']}, Δ={results['improvement']:+.3f}",
        'results': results,
    }


# ── EXP-870: Full Feature Engineering Benchmark ──────────────────────────────

@register('EXP-870', 'Full Feature Engineering Benchmark')
def exp_870(patients, detail=False):
    """Combine ALL winning features into the ultimate benchmark model.

    Includes: enhanced 16 features + multi-horizon predictions (857) +
    meal-size proxy (864) + momentum (868) + interactions (866) +
    supply-demand imbalance (869).
    """
    h_steps = 12
    lam = 10.0
    start = 24
    horizons = [1, 3, 6]

    base_r2s, full_r2s = [], []
    per_patient = []

    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        n = fd['n']
        hours = _get_hours(p['df'], n)
        nr = len(fd['resid'])
        n_pred = nr - h_steps
        usable = n_pred - start
        if usable < 200:
            continue

        actual = bg[h_steps + 1 + start: h_steps + 1 + start + usable]
        features, _ = _build_enhanced_features(fd, bg, hours, n_pred, h_steps, start)
        split = int(0.8 * usable)

        # Multi-horizon predictions
        h_preds, _ = _train_horizon_models(fd, bg, hours, nr, start, usable, split, horizons)
        horizon_cols = np.column_stack([h_preds[h] for h in sorted(h_preds)]) if h_preds else np.zeros((usable, 1))

        # Meal-size proxy features
        accel = np.zeros(n)
        for i in range(2, n):
            if np.isfinite(bg[i]) and np.isfinite(bg[i-1]) and np.isfinite(bg[i-2]):
                accel[i] = bg[i] - 2 * bg[i-1] + bg[i-2]

        meal_feats = np.zeros((usable, 4))
        for i in range(usable):
            orig = i + start
            for j, ws in enumerate([6, 12, 18]):
                w = accel[max(0, orig - ws):orig + 1]
                valid_w = w[np.isfinite(w)]
                if len(valid_w) > 0:
                    meal_feats[i, j] = np.max(valid_w)
            w = accel[max(0, orig - 12):orig + 1]
            valid_w = w[np.isfinite(w)]
            if len(valid_w) > 0:
                meal_feats[i, 3] = np.sum(np.maximum(valid_w, 0))

        # Momentum features
        mom_feats = np.zeros((usable, 3))
        for i in range(usable):
            orig = i + start
            vel = bg[orig] - bg[orig - 1] if orig >= 1 and np.isfinite(bg[orig]) and np.isfinite(bg[orig - 1]) else 0
            trend_dir = 1 if vel > 0.5 else (-1 if vel < -0.5 else 0)
            duration = 0
            magnitude = 0
            for j in range(1, min(49, orig)):
                if orig - j < 1:
                    break
                v = bg[orig - j + 1] - bg[orig - j] if np.isfinite(bg[orig - j + 1]) and np.isfinite(bg[orig - j]) else 0
                d = 1 if v > 0.5 else (-1 if v < -0.5 else 0)
                if d == trend_dir and trend_dir != 0:
                    duration += 1
                    magnitude += v
                else:
                    break
            mom_feats[i, 0] = duration * 5.0 / 60.0
            mom_feats[i, 1] = magnitude
            if orig >= 6:
                vel_now = bg[orig] - bg[orig - 1] if np.isfinite(bg[orig]) and np.isfinite(bg[orig - 1]) else 0
                vel_30m = bg[orig - 6] - bg[orig - 7] if np.isfinite(bg[orig - 6]) and np.isfinite(bg[orig - 7]) else 0
                mom_feats[i, 2] = vel_now - vel_30m

        # Interaction features
        inter_feats = np.zeros((usable, 4))
        for i in range(usable):
            f = features[i]
            inter_feats[i, 0] = f[0] * f[8] / 100.0
            inter_feats[i, 1] = f[0] * f[1] * 10
            inter_feats[i, 2] = f[1] * f[2] * 100
            inter_feats[i, 3] = (f[1] - f[2]) * f[0] * 10

        # Supply-demand imbalance
        net_flux = fd['supply'] - fd['demand']
        imb_feats = np.zeros((usable, 2))
        for i in range(usable):
            orig = i + start
            recent = np.sum(net_flux[max(0, orig - 6):orig + 1])
            distant = np.sum(net_flux[max(0, orig - 18):max(0, orig - 6)])
            imb_feats[i, 0] = recent
            imb_feats[i, 1] = recent - distant

        # Combine everything
        combined = np.hstack([features, horizon_cols, meal_feats, mom_feats, inter_feats, imb_feats])

        X_tr_b, X_val_b = features[:split], features[split:]
        X_tr_c, X_val_c = combined[:split], combined[split:]
        y_tr, y_val = actual[:split], actual[split:]

        valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_b), axis=1)
        valid_val = np.isfinite(y_val) & np.all(np.isfinite(X_val_b), axis=1)
        valid_tr_c = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_c), axis=1)
        valid_val_c = np.isfinite(y_val) & np.all(np.isfinite(X_val_c), axis=1)

        pred_base, _ = _ridge_predict(X_tr_b[valid_tr], y_tr[valid_tr], X_val_b, lam=lam * 3)
        pred_full, _ = _ridge_predict(X_tr_c[valid_tr_c], y_tr[valid_tr_c], X_val_c, lam=lam * 6)

        r2_base = _r2(pred_base[valid_val], y_val[valid_val])
        r2_full = _r2(pred_full[valid_val_c], y_val[valid_val_c])

        if np.isfinite(r2_base) and np.isfinite(r2_full):
            base_r2s.append(r2_base)
            full_r2s.append(r2_full)
            per_patient.append({
                'patient': p['name'],
                'base': round(float(r2_base), 3),
                'full': round(float(r2_full), 3),
                'delta': round(float(r2_full - r2_base), 3),
                'n_features': combined.shape[1],
            })

    results = {
        'base_16feat': round(float(np.mean(base_r2s)), 3),
        'full_benchmark': round(float(np.mean(full_r2s)), 3),
        'improvement': round(float(np.mean(full_r2s) - np.mean(base_r2s)), 3),
        'per_patient': per_patient,
        'total_features': per_patient[0]['n_features'] if per_patient else 0,
    }

    return {
        'status': 'pass',
        'detail': f"base={results['base_16feat']}, full={results['full_benchmark']} ({results['total_features']} feat), Δ={results['improvement']:+.3f}",
        'results': results,
    }


# ── Runner ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='EXP-861-870: Multi-Horizon Cascade')
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
