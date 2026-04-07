#!/usr/bin/env python3
"""EXP-851–860: Context-Conditioned Prediction & Regime Exploitation

With 99.9% bias-dominated error and 2x MAE ratio between easy/hard regimes,
this wave exploits context-specific modeling. Instead of one global model,
we train specialized models for different physiological states and combine
them with difficulty-aware weighting.

EXP-851: Regime-Specific Models (rising/stable/falling separate models)
EXP-852: BG-Level-Conditioned Models (low/target/high separate models)
EXP-853: Time-of-Day-Conditioned Models (morning/afternoon/evening/night)
EXP-854: Gap-Aware Features (data completeness as explicit feature)
EXP-855: Difficulty-Weighted Training (upweight hard regimes)
EXP-856: Adaptive Feature Selection (different features per regime)
EXP-857: Multi-Horizon Regime Detection (use 5/15/30min to detect transitions)
EXP-858: Residual Patterns by Meal Phase (pre-meal/absorption/post-absorption)
EXP-859: Personalized vs Pooled Regime Models
EXP-860: Combined Context-Conditioned Benchmark
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
    """Build the 16-feature enhanced set."""
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


def _classify_regime(velocity, bg_level):
    """Classify into dynamics regime."""
    if velocity > 2:
        dyn = 'rising'
    elif velocity < -2:
        dyn = 'falling'
    else:
        dyn = 'stable'

    if bg_level < 70:
        level = 'low'
    elif bg_level < 180:
        level = 'target'
    else:
        level = 'high'

    return dyn, level


def _prepare_patient_data(p, h_steps=12, start=24):
    """Prepare features and targets for one patient. Returns None if insufficient data."""
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
    val_hours = hours[:n_pred][start:] if hours is not None else np.full(usable, 12.0)

    return {
        'features': features,
        'actual': actual,
        'split': split,
        'usable': usable,
        'bg': bg,
        'fd': fd,
        'hours': val_hours,
        'name': p['name'],
        'n': n,
    }


# ── EXP-851: Regime-Specific Models ──────────────────────────────────────────

@register('EXP-851', 'Regime-Specific Models')
def exp_851(patients, detail=False):
    """Train separate models for rising/stable/falling BG dynamics.

    Compare global model vs 3 specialized models (one per dynamics regime).
    At prediction time, classify current point and use appropriate model.
    """
    h_steps = 12
    lam = 10.0

    global_r2s, regime_r2s = [], []

    for p in patients:
        data = _prepare_patient_data(p, h_steps)
        if data is None:
            continue

        features = data['features']
        actual = data['actual']
        split = data['split']

        X_tr, X_val = features[:split], features[split:]
        y_tr, y_val = actual[:split], actual[split:]
        valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        valid_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)

        # Global model
        pred_global, _ = _ridge_predict(X_tr[valid_tr], y_tr[valid_tr], X_val, lam=lam * 3)
        r2_global = _r2(pred_global[valid_val], y_val[valid_val])

        # Regime classification using velocity (feature index 8)
        vel_tr = X_tr[:, 8] if X_tr.shape[1] > 8 else np.zeros(split)
        vel_val = X_val[:, 8] if X_val.shape[1] > 8 else np.zeros(len(y_val))

        pred_regime = np.full(len(y_val), np.nan)

        for regime_name, vel_lo, vel_hi in [('falling', -999, -2), ('stable', -2, 2), ('rising', 2, 999)]:
            tr_mask = valid_tr & (vel_tr >= vel_lo) & (vel_tr < vel_hi)
            val_mask = (vel_val >= vel_lo) & (vel_val < vel_hi)

            if tr_mask.sum() < 30:
                # Fall back to global for sparse regimes
                pred_regime[val_mask] = pred_global[val_mask]
                continue

            pred_r, _ = _ridge_predict(X_tr[tr_mask], y_tr[tr_mask],
                                        X_val[val_mask], lam=lam * 3)
            pred_regime[val_mask] = pred_r

        r2_regime = _r2(pred_regime[valid_val], y_val[valid_val])

        if np.isfinite(r2_global) and np.isfinite(r2_regime):
            global_r2s.append(r2_global)
            regime_r2s.append(r2_regime)

    results = {
        'global': round(float(np.mean(global_r2s)), 3),
        'regime_specific': round(float(np.mean(regime_r2s)), 3),
        'improvement': round(float(np.mean(regime_r2s) - np.mean(global_r2s)), 3),
        'n_patients': len(global_r2s),
    }

    return {
        'status': 'pass',
        'detail': f"global={results['global']}, regime={results['regime_specific']}, Δ={results['improvement']:+.3f}",
        'results': results,
    }


# ── EXP-852: BG-Level-Conditioned Models ─────────────────────────────────────

@register('EXP-852', 'BG-Level-Conditioned Models')
def exp_852(patients, detail=False):
    """Train separate models for low/target/high BG levels."""
    h_steps = 12
    lam = 10.0

    global_r2s, level_r2s = [], []

    for p in patients:
        data = _prepare_patient_data(p, h_steps)
        if data is None:
            continue

        features = data['features']
        actual = data['actual']
        split = data['split']

        X_tr, X_val = features[:split], features[split:]
        y_tr, y_val = actual[:split], actual[split:]
        valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        valid_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)

        # Global model
        pred_global, _ = _ridge_predict(X_tr[valid_tr], y_tr[valid_tr], X_val, lam=lam * 3)
        r2_global = _r2(pred_global[valid_val], y_val[valid_val])

        # BG level from feature 0
        bg_tr = X_tr[:, 0]
        bg_val = X_val[:, 0]

        pred_level = np.full(len(y_val), np.nan)

        for level_name, bg_lo, bg_hi in [('low', 0, 70), ('target', 70, 180), ('high', 180, 600)]:
            tr_mask = valid_tr & (bg_tr >= bg_lo) & (bg_tr < bg_hi)
            val_mask = (bg_val >= bg_lo) & (bg_val < bg_hi)

            if tr_mask.sum() < 30:
                pred_level[val_mask] = pred_global[val_mask]
                continue

            pred_l, _ = _ridge_predict(X_tr[tr_mask], y_tr[tr_mask],
                                        X_val[val_mask], lam=lam * 3)
            pred_level[val_mask] = pred_l

        r2_level = _r2(pred_level[valid_val], y_val[valid_val])

        if np.isfinite(r2_global) and np.isfinite(r2_level):
            global_r2s.append(r2_global)
            level_r2s.append(r2_level)

    results = {
        'global': round(float(np.mean(global_r2s)), 3),
        'level_specific': round(float(np.mean(level_r2s)), 3),
        'improvement': round(float(np.mean(level_r2s) - np.mean(global_r2s)), 3),
    }

    return {
        'status': 'pass',
        'detail': f"global={results['global']}, level={results['level_specific']}, Δ={results['improvement']:+.3f}",
        'results': results,
    }


# ── EXP-853: Time-of-Day-Conditioned Models ──────────────────────────────────

@register('EXP-853', 'Time-of-Day-Conditioned Models')
def exp_853(patients, detail=False):
    """Train separate models for 4 time periods: overnight(0-6), morning(6-12), afternoon(12-18), evening(18-24)."""
    h_steps = 12
    lam = 10.0

    periods = [('overnight', 0, 6), ('morning', 6, 12), ('afternoon', 12, 18), ('evening', 18, 24)]

    global_r2s, period_r2s = [], []
    period_specific = {name: [] for name, _, _ in periods}

    for p in patients:
        data = _prepare_patient_data(p, h_steps)
        if data is None:
            continue

        features = data['features']
        actual = data['actual']
        split = data['split']
        hours = data['hours']

        X_tr, X_val = features[:split], features[split:]
        y_tr, y_val = actual[:split], actual[split:]
        h_tr = hours[:split]
        h_val = hours[split:split + len(y_val)]
        valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        valid_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)

        # Global
        pred_global, _ = _ridge_predict(X_tr[valid_tr], y_tr[valid_tr], X_val, lam=lam * 3)
        r2_global = _r2(pred_global[valid_val], y_val[valid_val])

        # Period-specific
        pred_period = np.full(len(y_val), np.nan)

        for pname, h_lo, h_hi in periods:
            tr_mask = valid_tr & (h_tr >= h_lo) & (h_tr < h_hi)
            val_mask = (h_val >= h_lo) & (h_val < h_hi) if len(h_val) == len(y_val) else np.zeros(len(y_val), dtype=bool)

            if tr_mask.sum() < 50:
                pred_period[val_mask] = pred_global[val_mask]
                continue

            pred_p, _ = _ridge_predict(X_tr[tr_mask], y_tr[tr_mask],
                                        X_val[val_mask], lam=lam * 3)
            pred_period[val_mask] = pred_p

            # Track per-period R²
            p_valid = valid_val & val_mask
            if p_valid.sum() > 10:
                r2_p = _r2(pred_p[p_valid[val_mask]], y_val[p_valid])
                if np.isfinite(r2_p):
                    period_specific[pname].append(r2_p)

        r2_period = _r2(pred_period[valid_val], y_val[valid_val])

        if np.isfinite(r2_global) and np.isfinite(r2_period):
            global_r2s.append(r2_global)
            period_r2s.append(r2_period)

    results = {
        'global': round(float(np.mean(global_r2s)), 3),
        'period_specific': round(float(np.mean(period_r2s)), 3),
        'improvement': round(float(np.mean(period_r2s) - np.mean(global_r2s)), 3),
        'by_period': {k: round(float(np.mean(v)), 3) if v else None
                      for k, v in period_specific.items()},
    }

    return {
        'status': 'pass',
        'detail': f"global={results['global']}, period={results['period_specific']}, Δ={results['improvement']:+.3f}",
        'results': results,
    }


# ── EXP-854: Gap-Aware Features ──────────────────────────────────────────────

@register('EXP-854', 'Gap-Aware Features')
def exp_854(patients, detail=False):
    """Add data completeness features: gap proximity, consecutive valid count, recent gap fraction.

    Hypothesis: model struggles near data gaps (like patient h). Explicit gap features
    allow the model to appropriately discount uncertain predictions.
    """
    h_steps = 12
    lam = 10.0
    start = 24

    base_r2s, gap_r2s = [], []

    for p in patients:
        data = _prepare_patient_data(p, h_steps)
        if data is None:
            continue

        fd = _compute_flux(p)
        bg = fd['bg']
        n = fd['n']

        features = data['features']
        actual = data['actual']
        split = data['split']
        usable = data['usable']

        # Compute gap features
        gap_feats = np.zeros((usable, 4))
        for i in range(usable):
            orig = i + start

            # 1. Consecutive valid readings before this point
            consecutive = 0
            for j in range(orig, -1, -1):
                if np.isfinite(bg[j]):
                    consecutive += 1
                else:
                    break
            gap_feats[i, 0] = min(consecutive, 288) / 288.0  # Normalize to 1 day

            # 2. Fraction of valid readings in past 2 hours (24 steps)
            window = bg[max(0, orig - 24):orig + 1]
            gap_feats[i, 1] = np.sum(np.isfinite(window)) / len(window) if len(window) > 0 else 0

            # 3. Distance to nearest gap (forward or backward)
            nearest_gap = 288
            for j in range(1, min(49, orig + 1)):
                if not np.isfinite(bg[orig - j]):
                    nearest_gap = j
                    break
            for j in range(1, min(49, n - orig)):
                if not np.isfinite(bg[orig + j]):
                    nearest_gap = min(nearest_gap, j)
                    break
            gap_feats[i, 2] = min(nearest_gap, 48) / 48.0

            # 4. BG derivative quality (finite diffs available?)
            if orig >= 2:
                d1 = bg[orig] - bg[orig - 1]
                d2 = bg[orig - 1] - bg[orig - 2]
                gap_feats[i, 3] = 1.0 if (np.isfinite(d1) and np.isfinite(d2)) else 0.0

        combined = np.hstack([features, gap_feats])

        X_tr_b, X_val_b = features[:split], features[split:]
        X_tr_g, X_val_g = combined[:split], combined[split:]
        y_tr, y_val = actual[:split], actual[split:]

        valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_b), axis=1)
        valid_val = np.isfinite(y_val) & np.all(np.isfinite(X_val_b), axis=1)
        valid_tr_g = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_g), axis=1)
        valid_val_g = np.isfinite(y_val) & np.all(np.isfinite(X_val_g), axis=1)

        pred_base, _ = _ridge_predict(X_tr_b[valid_tr], y_tr[valid_tr], X_val_b, lam=lam * 3)
        pred_gap, _ = _ridge_predict(X_tr_g[valid_tr_g], y_tr[valid_tr_g], X_val_g, lam=lam * 3)

        r2_base = _r2(pred_base[valid_val], y_val[valid_val])
        r2_gap = _r2(pred_gap[valid_val_g], y_val[valid_val_g])

        if np.isfinite(r2_base) and np.isfinite(r2_gap):
            base_r2s.append(r2_base)
            gap_r2s.append(r2_gap)

    results = {
        'base': round(float(np.mean(base_r2s)), 3),
        'with_gap_features': round(float(np.mean(gap_r2s)), 3),
        'improvement': round(float(np.mean(gap_r2s) - np.mean(base_r2s)), 3),
    }

    return {
        'status': 'pass',
        'detail': f"base={results['base']}, +gap={results['with_gap_features']}, Δ={results['improvement']:+.3f}",
        'results': results,
    }


# ── EXP-855: Difficulty-Weighted Training ─────────────────────────────────────

@register('EXP-855', 'Difficulty-Weighted Training')
def exp_855(patients, detail=False):
    """Upweight hard-to-predict regimes in training.

    Assign sample weights: rising+high gets 2x, falling+high gets 1.5x,
    stable+target gets 0.7x (already easy). Use weighted ridge regression.
    """
    h_steps = 12
    lam = 10.0

    global_r2s, weighted_r2s = [], []
    # Also measure per-regime improvement
    regime_improvements = {}

    for p in patients:
        data = _prepare_patient_data(p, h_steps)
        if data is None:
            continue

        features = data['features']
        actual = data['actual']
        split = data['split']

        X_tr, X_val = features[:split], features[split:]
        y_tr, y_val = actual[:split], actual[split:]
        valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        valid_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)

        # Global (unweighted)
        pred_global, _ = _ridge_predict(X_tr[valid_tr], y_tr[valid_tr], X_val, lam=lam * 3)
        r2_global = _r2(pred_global[valid_val], y_val[valid_val])

        # Compute sample weights
        weights = np.ones(split)
        vel_tr = X_tr[:, 8] if X_tr.shape[1] > 8 else np.zeros(split)
        bg_tr = X_tr[:, 0]

        for i in range(split):
            if not valid_tr[i]:
                continue
            # Rising + high: 2x
            if vel_tr[i] > 2 and bg_tr[i] >= 180:
                weights[i] = 2.0
            # Falling + high: 1.5x
            elif vel_tr[i] < -2 and bg_tr[i] >= 180:
                weights[i] = 1.5
            # Rising + target: 1.2x
            elif vel_tr[i] > 2:
                weights[i] = 1.2
            # Stable + target: downweight
            elif abs(vel_tr[i]) <= 2 and 70 <= bg_tr[i] < 180:
                weights[i] = 0.7

        # Weighted ridge: W^(1/2) X, W^(1/2) y
        sqrt_w = np.sqrt(weights[valid_tr])
        X_weighted = X_tr[valid_tr] * sqrt_w[:, np.newaxis]
        y_weighted = y_tr[valid_tr] * sqrt_w

        pred_weighted, _ = _ridge_predict(X_weighted, y_weighted, X_val, lam=lam * 3)
        r2_weighted = _r2(pred_weighted[valid_val], y_val[valid_val])

        if np.isfinite(r2_global) and np.isfinite(r2_weighted):
            global_r2s.append(r2_global)
            weighted_r2s.append(r2_weighted)

            # Per-regime analysis on validation
            vel_val = X_val[:, 8] if X_val.shape[1] > 8 else np.zeros(len(y_val))
            bg_val = X_val[:, 0]
            for rname, vel_lo, vel_hi, bg_lo, bg_hi in [
                ('rising_high', 2, 999, 180, 999),
                ('rising_target', 2, 999, 70, 180),
                ('stable_target', -2, 2, 70, 180),
                ('falling_high', -999, -2, 180, 999),
            ]:
                r_mask = valid_val & (vel_val >= vel_lo) & (vel_val < vel_hi) & \
                         (bg_val >= bg_lo) & (bg_val < bg_hi)
                if r_mask.sum() > 10:
                    mae_g = _mae(pred_global[r_mask], y_val[r_mask])
                    mae_w = _mae(pred_weighted[r_mask], y_val[r_mask])
                    if rname not in regime_improvements:
                        regime_improvements[rname] = []
                    regime_improvements[rname].append(mae_w - mae_g)

    results = {
        'global': round(float(np.mean(global_r2s)), 3),
        'weighted': round(float(np.mean(weighted_r2s)), 3),
        'improvement': round(float(np.mean(weighted_r2s) - np.mean(global_r2s)), 3),
        'regime_mae_changes': {k: round(float(np.mean(v)), 2)
                               for k, v in regime_improvements.items()},
    }

    return {
        'status': 'pass',
        'detail': f"global={results['global']}, weighted={results['weighted']}, Δ={results['improvement']:+.3f}",
        'results': results,
    }


# ── EXP-856: Adaptive Feature Selection ──────────────────────────────────────

@register('EXP-856', 'Adaptive Feature Selection')
def exp_856(patients, detail=False):
    """Use different feature subsets for different regimes.

    Hypothesis: In rising BG, velocity/acceleration matter most.
    In stable BG, lag features and window stats dominate.
    """
    h_steps = 12
    lam = 10.0

    # Feature indices in the 16-feature enhanced set
    # 0:bg, 1:supply, 2:demand, 3:hepatic, 4:resid, 5:sin_h, 6:cos_h, 7:bias
    # 8:velocity, 9:accel, 10:lag6, 11:lag12, 12:window_mean, 13:window_std, 14:trend, 15:bg²

    regime_features = {
        'rising': [0, 1, 2, 3, 4, 7, 8, 9, 15],      # + velocity, acceleration, BG²
        'stable': [0, 1, 2, 3, 4, 7, 10, 11, 12, 13], # + lags, window stats
        'falling': [0, 1, 2, 3, 4, 7, 8, 9, 14],      # + velocity, accel, trend
    }

    global_r2s, adaptive_r2s = [], []

    for p in patients:
        data = _prepare_patient_data(p, h_steps)
        if data is None:
            continue

        features = data['features']
        actual = data['actual']
        split = data['split']

        X_tr, X_val = features[:split], features[split:]
        y_tr, y_val = actual[:split], actual[split:]
        valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        valid_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)

        # Global with all 16 features
        pred_global, _ = _ridge_predict(X_tr[valid_tr], y_tr[valid_tr], X_val, lam=lam * 3)
        r2_global = _r2(pred_global[valid_val], y_val[valid_val])

        # Adaptive feature selection per regime
        vel = features[:, 8]
        pred_adaptive = np.full(len(y_val), np.nan)

        for rname, feat_idx in regime_features.items():
            if rname == 'rising':
                tr_mask = valid_tr & (vel[:split] > 2)
                val_mask = vel[split:split + len(y_val)] > 2
            elif rname == 'falling':
                tr_mask = valid_tr & (vel[:split] < -2)
                val_mask = vel[split:split + len(y_val)] < -2
            else:
                tr_mask = valid_tr & (vel[:split] >= -2) & (vel[:split] <= 2)
                val_mask = (vel[split:split + len(y_val)] >= -2) & (vel[split:split + len(y_val)] <= 2)

            if tr_mask.sum() < 30:
                pred_adaptive[val_mask] = pred_global[val_mask]
                continue

            X_tr_sub = X_tr[tr_mask][:, feat_idx]
            X_val_sub = X_val[val_mask][:, feat_idx]
            pred_r, _ = _ridge_predict(X_tr_sub, y_tr[tr_mask], X_val_sub, lam=lam * 2)
            pred_adaptive[val_mask] = pred_r

        r2_adaptive = _r2(pred_adaptive[valid_val], y_val[valid_val])

        if np.isfinite(r2_global) and np.isfinite(r2_adaptive):
            global_r2s.append(r2_global)
            adaptive_r2s.append(r2_adaptive)

    results = {
        'global_16feat': round(float(np.mean(global_r2s)), 3),
        'adaptive_selection': round(float(np.mean(adaptive_r2s)), 3),
        'improvement': round(float(np.mean(adaptive_r2s) - np.mean(global_r2s)), 3),
    }

    return {
        'status': 'pass',
        'detail': f"global={results['global_16feat']}, adaptive={results['adaptive_selection']}, Δ={results['improvement']:+.3f}",
        'results': results,
    }


# ── EXP-857: Multi-Horizon Regime Detection ──────────────────────────────────

@register('EXP-857', 'Multi-Horizon Regime Detection')
def exp_857(patients, detail=False):
    """Use predictions at shorter horizons (5/15/30min) as features for 60min.

    Train models at 5, 15, 30min horizons. Use their predictions (on validation)
    as additional features for the 60min model. This is VALID because short-horizon
    predictions use only current information.

    NOTE: Must train short-horizon models on TRAINING data only, then generate
    predictions for both train and validation to avoid leakage.
    """
    h_steps = 12
    lam = 10.0
    start = 24
    short_horizons = [1, 3, 6]  # 5min, 15min, 30min in steps

    base_r2s, multi_r2s = [], []

    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        n = fd['n']
        hours = _get_hours(p['df'], n)
        nr = len(fd['resid'])

        # Build features for each horizon
        horizon_preds_train = {}
        horizon_preds_val = {}

        # We need consistent train/val split across horizons
        # Use the 60min usable range as reference
        n_pred_60 = nr - h_steps
        usable_60 = n_pred_60 - start
        if usable_60 < 200:
            continue

        split = int(0.8 * usable_60)

        # 60min target
        actual_60 = bg[h_steps + 1 + start: h_steps + 1 + start + usable_60]

        # Build 60min enhanced features
        features_60, _ = _build_enhanced_features(fd, bg, hours, n_pred_60, h_steps, start)

        # For each short horizon, build model and get predictions
        for sh in short_horizons:
            n_pred_sh = nr - sh
            if n_pred_sh - start < usable_60:
                continue

            actual_sh = bg[sh + 1 + start: sh + 1 + start + usable_60]
            feat_sh = _build_features_base(fd, hours, n_pred_sh, sh)
            feat_sh = feat_sh[start:start + usable_60]

            X_tr_sh = feat_sh[:split]
            y_tr_sh = actual_sh[:split]
            valid_tr_sh = np.isfinite(y_tr_sh) & np.all(np.isfinite(X_tr_sh), axis=1)

            if valid_tr_sh.sum() < 50:
                continue

            # Train on training, predict on both train and val
            _, w_sh = _ridge_predict(X_tr_sh[valid_tr_sh], y_tr_sh[valid_tr_sh],
                                      X_tr_sh[:1], lam=0.1)
            if w_sh is None:
                continue

            pred_sh_all = feat_sh @ w_sh
            horizon_preds_train[sh] = pred_sh_all[:split]
            horizon_preds_val[sh] = pred_sh_all[split:]

        if len(horizon_preds_val) < 2:
            continue

        # Build augmented features for 60min prediction
        extra_tr = np.column_stack([horizon_preds_train[sh] for sh in sorted(horizon_preds_train)])
        extra_val = np.column_stack([horizon_preds_val[sh] for sh in sorted(horizon_preds_val)])

        X_tr_60 = features_60[:split]
        X_val_60 = features_60[split:]
        y_tr = actual_60[:split]
        y_val = actual_60[split:]

        combined_tr = np.hstack([X_tr_60, extra_tr])
        combined_val = np.hstack([X_val_60, extra_val])

        valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_60), axis=1)
        valid_val = np.isfinite(y_val) & np.all(np.isfinite(X_val_60), axis=1)
        valid_tr_c = np.isfinite(y_tr) & np.all(np.isfinite(combined_tr), axis=1)
        valid_val_c = np.isfinite(y_val) & np.all(np.isfinite(combined_val), axis=1)

        # Base 60min model
        pred_base, _ = _ridge_predict(X_tr_60[valid_tr], y_tr[valid_tr], X_val_60, lam=lam * 3)
        r2_base = _r2(pred_base[valid_val], y_val[valid_val])

        # Multi-horizon augmented model
        pred_multi, _ = _ridge_predict(combined_tr[valid_tr_c], y_tr[valid_tr_c],
                                        combined_val, lam=lam * 4)
        r2_multi = _r2(pred_multi[valid_val_c], y_val[valid_val_c])

        if np.isfinite(r2_base) and np.isfinite(r2_multi):
            base_r2s.append(r2_base)
            multi_r2s.append(r2_multi)

    results = {
        'base_60min': round(float(np.mean(base_r2s)), 3),
        'multi_horizon': round(float(np.mean(multi_r2s)), 3),
        'improvement': round(float(np.mean(multi_r2s) - np.mean(base_r2s)), 3),
    }

    return {
        'status': 'pass',
        'detail': f"base={results['base_60min']}, multi={results['multi_horizon']}, Δ={results['improvement']:+.3f}",
        'results': results,
    }


# ── EXP-858: Residual Patterns by Meal Phase ─────────────────────────────────

@register('EXP-858', 'Residual Patterns by Meal Phase')
def exp_858(patients, detail=False):
    """Analyze prediction errors by meal phase.

    Phases (detected from supply signal):
    - No-meal: supply < threshold for 2+ hours
    - Pre-absorption: 0-30min after supply spike
    - Peak-absorption: 30-90min after spike
    - Post-absorption: 90-180min after spike
    - Late-post: 180-360min after spike
    """
    h_steps = 12
    lam = 10.0
    start = 24

    phase_errors = {phase: [] for phase in
                    ['no_meal', 'pre_absorption', 'peak_absorption',
                     'post_absorption', 'late_post']}

    for p in patients:
        data = _prepare_patient_data(p, h_steps)
        if data is None:
            continue

        fd = _compute_flux(p)
        bg = fd['bg']
        supply = fd['supply']

        features = data['features']
        actual = data['actual']
        split = data['split']
        usable = data['usable']

        X_tr, X_val = features[:split], features[split:]
        y_tr, y_val = actual[:split], actual[split:]
        valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        valid_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)

        pred, _ = _ridge_predict(X_tr[valid_tr], y_tr[valid_tr], X_val, lam=lam * 3)

        # Detect meal events from supply spikes
        supply_valid = supply[np.isfinite(supply) & (supply > 0)]
        if len(supply_valid) < 100:
            continue
        meal_thresh = np.percentile(supply_valid, 85)

        # Compute time-since-last-meal for each point
        tslm = np.zeros(len(bg))
        last_meal = -10000
        for i in range(len(bg)):
            if i < len(supply) and supply[i] > meal_thresh:
                last_meal = i
            tslm[i] = (i - last_meal) * 5  # minutes

        # Classify validation points
        for i in range(len(y_val)):
            if not valid_val[i] or not np.isfinite(pred[i]):
                continue

            idx = start + split + i
            if idx >= len(tslm):
                continue

            minutes = tslm[idx]
            err = abs(pred[i] - y_val[i])
            bias = pred[i] - y_val[i]

            if minutes > 360 or minutes < 0:
                phase = 'no_meal'
            elif minutes < 30:
                phase = 'pre_absorption'
            elif minutes < 90:
                phase = 'peak_absorption'
            elif minutes < 180:
                phase = 'post_absorption'
            else:
                phase = 'late_post'

            phase_errors[phase].append({'abs_error': err, 'bias': bias, 'actual': y_val[i]})

    # Aggregate
    results_phases = {}
    for phase, errors in phase_errors.items():
        if len(errors) > 30:
            results_phases[phase] = {
                'n': len(errors),
                'mae': round(float(np.mean([e['abs_error'] for e in errors])), 1),
                'bias': round(float(np.mean([e['bias'] for e in errors])), 1),
                'pct': round(100 * len(errors) / sum(len(v) for v in phase_errors.values()), 1),
            }

    results = {
        'phases': results_phases,
        'worst_phase': max(results_phases, key=lambda k: results_phases[k]['mae']) if results_phases else None,
        'best_phase': min(results_phases, key=lambda k: results_phases[k]['mae']) if results_phases else None,
    }

    return {
        'status': 'pass',
        'detail': f"worst={results['worst_phase']} MAE={results_phases.get(results['worst_phase'],{}).get('mae','?')}, best={results['best_phase']}",
        'results': results,
    }


# ── EXP-859: Personalized vs Pooled Regime Models ────────────────────────────

@register('EXP-859', 'Personalized vs Pooled Regime Models')
def exp_859(patients, detail=False):
    """Compare personalized (per-patient) vs pooled (all-patient) regime models.

    For each regime (rising/stable/falling), compare:
    1. Global: one model for all patients, all regimes
    2. Pooled regime: one model per regime, pooled across patients
    3. Personal regime: one model per regime per patient
    """
    h_steps = 12
    lam = 10.0

    # Collect all patient data
    all_data = []
    for p in patients:
        data = _prepare_patient_data(p, h_steps)
        if data is not None:
            all_data.append(data)

    if len(all_data) < 3:
        return {'status': 'fail', 'detail': 'Not enough patients'}

    # Strategy: Leave-one-out for pooled model, personal model uses own data
    global_r2s, pooled_r2s, personal_r2s = [], [], []

    for test_idx, test_data in enumerate(all_data):
        features = test_data['features']
        actual = test_data['actual']
        split = test_data['split']

        X_val = features[split:]
        y_val = actual[split:]
        valid_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)

        # 1. Global personal model
        X_tr = features[:split]
        y_tr = actual[:split]
        valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        pred_global, _ = _ridge_predict(X_tr[valid_tr], y_tr[valid_tr], X_val, lam=lam * 3)
        r2_global = _r2(pred_global[valid_val], y_val[valid_val])

        # 2. Pooled regime model: use all OTHER patients' training data per regime
        vel_val = X_val[:, 8] if X_val.shape[1] > 8 else np.zeros(len(y_val))
        pred_pooled = np.full(len(y_val), np.nan)

        for rname, vel_lo, vel_hi in [('falling', -999, -2), ('stable', -2, 2), ('rising', 2, 999)]:
            # Collect training data from other patients
            pool_X, pool_y = [], []
            for other_idx, other_data in enumerate(all_data):
                if other_idx == test_idx:
                    continue
                oX = other_data['features'][:other_data['split']]
                oy = other_data['actual'][:other_data['split']]
                vel_o = oX[:, 8] if oX.shape[1] > 8 else np.zeros(len(oy))
                omask = np.isfinite(oy) & np.all(np.isfinite(oX), axis=1) & \
                        (vel_o >= vel_lo) & (vel_o < vel_hi)
                if omask.sum() > 0:
                    pool_X.append(oX[omask])
                    pool_y.append(oy[omask])

            if not pool_X:
                continue

            pool_X = np.vstack(pool_X)
            pool_y = np.concatenate(pool_y)

            val_mask = (vel_val >= vel_lo) & (vel_val < vel_hi)
            if val_mask.sum() < 5 or len(pool_y) < 30:
                pred_pooled[val_mask] = pred_global[val_mask]
                continue

            # Subsample if too large
            if len(pool_y) > 5000:
                rng = np.random.RandomState(42)
                idx = rng.choice(len(pool_y), 5000, replace=False)
                pool_X = pool_X[idx]
                pool_y = pool_y[idx]

            pred_r, _ = _ridge_predict(pool_X, pool_y, X_val[val_mask], lam=lam * 5)
            pred_pooled[val_mask] = pred_r

        r2_pooled = _r2(pred_pooled[valid_val], y_val[valid_val])

        # 3. Personal regime model
        pred_personal = np.full(len(y_val), np.nan)
        vel_tr = X_tr[:, 8] if X_tr.shape[1] > 8 else np.zeros(split)

        for rname, vel_lo, vel_hi in [('falling', -999, -2), ('stable', -2, 2), ('rising', 2, 999)]:
            tr_mask = valid_tr & (vel_tr >= vel_lo) & (vel_tr < vel_hi)
            val_mask = (vel_val >= vel_lo) & (vel_val < vel_hi)

            if tr_mask.sum() < 30:
                pred_personal[val_mask] = pred_global[val_mask]
                continue

            pred_r, _ = _ridge_predict(X_tr[tr_mask], y_tr[tr_mask],
                                        X_val[val_mask], lam=lam * 3)
            pred_personal[val_mask] = pred_r

        r2_personal = _r2(pred_personal[valid_val], y_val[valid_val])

        if np.isfinite(r2_global) and np.isfinite(r2_pooled) and np.isfinite(r2_personal):
            global_r2s.append(r2_global)
            pooled_r2s.append(r2_pooled)
            personal_r2s.append(r2_personal)

    results = {
        'global': round(float(np.mean(global_r2s)), 3),
        'pooled_regime': round(float(np.mean(pooled_r2s)), 3),
        'personal_regime': round(float(np.mean(personal_r2s)), 3),
        'pooled_vs_global': round(float(np.mean(pooled_r2s) - np.mean(global_r2s)), 3),
        'personal_vs_global': round(float(np.mean(personal_r2s) - np.mean(global_r2s)), 3),
    }

    return {
        'status': 'pass',
        'detail': f"global={results['global']}, pooled={results['pooled_regime']}, personal={results['personal_regime']}",
        'results': results,
    }


# ── EXP-860: Combined Context-Conditioned Benchmark ──────────────────────────

@register('EXP-860', 'Combined Context-Conditioned Benchmark')
def exp_860(patients, detail=False):
    """Combine the best context-conditioning strategies.

    Use: personal regime models (851) + gap-aware features (854) +
    multi-horizon predictions (857) as combined approach.
    """
    h_steps = 12
    lam = 10.0
    start = 24
    short_horizons = [1, 3, 6]

    base_r2s, combined_r2s = [], []

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

        # Gap features
        gap_feats = np.zeros((usable, 3))
        for i in range(usable):
            orig = i + start
            # Consecutive valid
            consecutive = 0
            for j in range(orig, max(orig - 289, -1), -1):
                if np.isfinite(bg[j]):
                    consecutive += 1
                else:
                    break
            gap_feats[i, 0] = min(consecutive, 288) / 288.0
            # Fraction valid in 2h
            window = bg[max(0, orig - 24):orig + 1]
            gap_feats[i, 1] = np.sum(np.isfinite(window)) / len(window) if len(window) > 0 else 0
            # Derivative quality
            if orig >= 2:
                d1 = bg[orig] - bg[orig - 1]
                d2 = bg[orig - 1] - bg[orig - 2]
                gap_feats[i, 2] = 1.0 if (np.isfinite(d1) and np.isfinite(d2)) else 0.0

        # Short-horizon predictions
        sh_preds = []
        for sh in short_horizons:
            n_pred_sh = nr - sh
            if n_pred_sh - start < usable:
                continue
            feat_sh = _build_features_base(fd, hours, n_pred_sh, sh)
            feat_sh = feat_sh[start:start + usable]

            actual_sh = bg[sh + 1 + start: sh + 1 + start + usable]
            X_tr_sh = feat_sh[:split]
            y_tr_sh = actual_sh[:split]
            valid_sh = np.isfinite(y_tr_sh) & np.all(np.isfinite(X_tr_sh), axis=1)
            if valid_sh.sum() < 50:
                continue

            _, w_sh = _ridge_predict(X_tr_sh[valid_sh], y_tr_sh[valid_sh],
                                      X_tr_sh[:1], lam=0.1)
            if w_sh is not None:
                sh_preds.append(feat_sh @ w_sh)

        # Build combined features
        extra_cols = [gap_feats]
        for sp in sh_preds:
            extra_cols.append(sp.reshape(-1, 1))

        combined = np.hstack([features] + extra_cols)

        X_tr, X_val = features[:split], features[split:]
        X_tr_c, X_val_c = combined[:split], combined[split:]
        y_tr, y_val = actual[:split], actual[split:]
        valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        valid_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
        valid_tr_c = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_c), axis=1)
        valid_val_c = np.isfinite(y_val) & np.all(np.isfinite(X_val_c), axis=1)

        # Base model
        pred_base, _ = _ridge_predict(X_tr[valid_tr], y_tr[valid_tr], X_val, lam=lam * 3)
        r2_base = _r2(pred_base[valid_val], y_val[valid_val])

        # Combined: regime-specific with enriched features
        vel = combined[:, 8]
        pred_combined = np.full(len(y_val), np.nan)

        for rname, vel_lo, vel_hi in [('falling', -999, -2), ('stable', -2, 2), ('rising', 2, 999)]:
            tr_mask = valid_tr_c & (vel[:split] >= vel_lo) & (vel[:split] < vel_hi)
            val_mask = (vel[split:split + len(y_val)] >= vel_lo) & (vel[split:split + len(y_val)] < vel_hi)

            if tr_mask.sum() < 30:
                # Fallback: global combined model
                pred_fb, _ = _ridge_predict(X_tr_c[valid_tr_c], y_tr[valid_tr_c],
                                             X_val_c[val_mask], lam=lam * 4)
                pred_combined[val_mask] = pred_fb
                continue

            pred_r, _ = _ridge_predict(X_tr_c[tr_mask], y_tr[tr_mask],
                                        X_val_c[val_mask], lam=lam * 4)
            pred_combined[val_mask] = pred_r

        r2_combined = _r2(pred_combined[valid_val_c], y_val[valid_val_c])

        if np.isfinite(r2_base) and np.isfinite(r2_combined):
            base_r2s.append(r2_base)
            combined_r2s.append(r2_combined)

    results = {
        'base_16feat': round(float(np.mean(base_r2s)), 3),
        'combined_context': round(float(np.mean(combined_r2s)), 3),
        'improvement': round(float(np.mean(combined_r2s) - np.mean(base_r2s)), 3),
    }

    return {
        'status': 'pass',
        'detail': f"base={results['base_16feat']}, combined={results['combined_context']}, Δ={results['improvement']:+.3f}",
        'results': results,
    }


# ── Runner ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='EXP-851-860: Context-Conditioned Prediction')
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
            fname = f"exp_{exp_id.split('-')[1]}_{exp['name'].lower().replace(' ', '_')}.json"
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
