#!/usr/bin/env python3
"""EXP-921–930: Time-of-Day, Guards, RFE, Clinical Metrics & Definitive SOTA

Building on the 911–920 batch which established:
  - Forward-looking sums: base R²≈0.533 (EXP-911)
  - Forward + all features: R²≈0.545 (EXP-914)
  - Forward CV stacking: R²≈0.549 (EXP-919)
  - Prior SOTA: R²=0.561 (EXP-871, backward base + CV stacking)
  - Error budget: 72.6% irreducible, 22.5% meal, 4.4% ToD
  - Practical ceiling: ~R²=0.567
  - Oracle ceiling: R²=0.613

This batch adds time-of-day conditioning, regime-split models, minimum-data
stacking guards, recursive feature elimination, heteroscedastic prediction,
residual clustering, proper cross-validated oracle, the definitive best model,
Clarke error grid evaluation, and multi-step recursive prediction.

EXP-921: Time-of-Day Conditioning
EXP-922: Dawn/Day/Night Separate Models
EXP-923: Minimum-Data Stacking Guard
EXP-924: RFE on Forward Base Combined Features
EXP-925: Heteroscedastic Prediction
EXP-926: Residual Pattern Clustering
EXP-927: Cross-Validated Oracle with Proper Split
EXP-928: Definitive Best Model (KEY experiment)
EXP-929: Clarke Error Grid Evaluation
EXP-930: Multi-Step Recursive Prediction
"""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from cgmencode import exp_metabolic_flux, exp_metabolic_441
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


def _get_hours_fallback(df, n):
    """Get fractional hours from timestamps, with index-based fallback."""
    import pandas as pd
    idx = df.index[:n]
    if isinstance(idx, pd.DatetimeIndex):
        return np.asarray(idx.hour + idx.minute / 60.0, dtype=float)
    if 'dateString' in df.columns:
        try:
            ts = pd.to_datetime(df['dateString'].iloc[:n])
            return np.asarray(ts.dt.hour + ts.dt.minute / 60.0, dtype=float)
        except Exception:
            pass
    # Index-based fallback: assume 5-min intervals from midnight
    return np.asarray([((i * 5) / 60.0) % 24.0 for i in range(n)], dtype=float)


def _r2(pred, actual):
    pred, actual = np.asarray(pred, dtype=float), np.asarray(actual, dtype=float)
    mask = np.isfinite(pred) & np.isfinite(actual)
    if mask.sum() < 10:
        return float('nan')
    p, a = pred[mask], actual[mask]
    ss_res = np.sum((a - p)**2)
    ss_tot = np.sum((a - np.mean(a))**2)
    return 1.0 - ss_res / ss_tot if ss_tot > 1e-10 else float('nan')


def _build_features_base_forward(fd, hours, n_pred, h_steps):
    """Forward-looking supply/demand sums."""
    bg = fd['bg']
    resid = fd['resid']
    nr = len(resid)
    n_supply = len(fd['supply'])
    features = np.zeros((n_pred, 8))
    for i in range(n_pred):
        features[i, 0] = bg[i]
        features[i, 1] = np.sum(fd['supply'][i:min(i + h_steps, n_supply)])
        features[i, 2] = np.sum(fd['demand'][i:min(i + h_steps, n_supply)])
        features[i, 3] = np.sum(fd['hepatic'][i:min(i + h_steps, n_supply)])
        features[i, 4] = resid[i] if i < nr else 0
        if hours is not None and i < len(hours):
            features[i, 5] = np.sin(2 * np.pi * hours[i] / 24.0)
            features[i, 6] = np.cos(2 * np.pi * hours[i] / 24.0)
        features[i, 7] = 1.0
    return features


def _build_enhanced_features_forward(fd, bg, hours, n_pred, h_steps, start=24):
    """Enhanced features with forward-looking supply/demand sums."""
    base = _build_features_base_forward(fd, hours, n_pred, h_steps)
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
            extra[i, 6] = np.polyfit(np.arange(len(vw)), vw, 1)[0]
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


def _prepare_patient_forward(p, h_steps=12, start=24):
    """Prepare patient data with forward-looking supply/demand sums."""
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
    features, _ = _build_enhanced_features_forward(fd, bg, hours, n_pred, h_steps, start)
    split = int(0.8 * usable)
    return {
        'fd': fd, 'bg': bg, 'hours': hours, 'nr': nr,
        'n_pred': n_pred, 'usable': usable, 'actual': actual,
        'features': features, 'split': split, 'name': p.get('name', '?'),
    }


def _causal_ema(x, alpha):
    out = np.empty_like(x, dtype=float)
    out[0] = x[0] if np.isfinite(x[0]) else 120.0
    for i in range(1, len(x)):
        out[i] = alpha * x[i] + (1 - alpha) * out[i - 1] if np.isfinite(x[i]) else out[i - 1]
    return out


def _build_pp_features(bg_sig, supply, n_pred):
    """Post-prandial shape features."""
    supply_thresh = np.percentile(supply[supply > 0], 75) if np.sum(supply > 0) > 10 else 0.1
    pp_feats = np.zeros((n_pred, 5))
    last_meal_step = -999
    meal_start_bg = 0.0
    for i in range(n_pred):
        if supply[i] > supply_thresh:
            if i - last_meal_step > 6:
                meal_start_bg = bg_sig[i]
            last_meal_step = i
        time_since = (i - last_meal_step) * 5.0
        pp_feats[i, 0] = min(time_since, 360) / 360.0
        if time_since < 60:
            pp_feats[i, 1] = 1.0
        elif time_since < 180:
            pp_feats[i, 1] = 0.5
        else:
            pp_feats[i, 1] = 0.0
        phase_rad = 2.0 * np.pi * min(time_since, 240) / 240.0
        pp_feats[i, 2] = np.sin(phase_rad)
        pp_feats[i, 3] = np.cos(phase_rad)
        if i >= 3:
            pp_feats[i, 4] = bg_sig[i] - bg_sig[max(0, i - 3)]
    return pp_feats


def _build_iob_features(demand, n_pred):
    """IOB curve shape features."""
    iob_feats = np.zeros((n_pred, 5))
    for i in range(24, n_pred):
        d_win = demand[max(0, i - 72):i]
        if len(d_win) < 6:
            continue
        iob_feats[i, 0] = np.sum(d_win)
        iob_feats[i, 1] = np.max(d_win)
        peak_idx = np.argmax(d_win)
        iob_feats[i, 2] = (len(d_win) - peak_idx) * 5.0 / 60.0
        if len(d_win) >= 6:
            iob_feats[i, 3] = np.mean(d_win[-6:]) - np.mean(d_win[:6])
        d_sorted = np.sort(d_win)
        cum = np.cumsum(d_sorted)
        total = cum[-1] if cum[-1] > 0 else 1
        iob_feats[i, 4] = 1.0 - 2.0 * np.sum(cum / total) / len(d_win)
    return iob_feats


def _build_all_extra_features(fd, bg, hours, n_pred, usable, start):
    """Build the full set of extra features (PK derivatives + shape + causal EMA +
    momentum) aligned to the [start:start+usable] window."""
    bg_sig = bg[:n_pred].astype(float)
    bg_sig[~np.isfinite(bg_sig)] = np.nanmean(bg_sig)
    supply = fd['supply'][:n_pred].astype(float)
    demand = fd['demand'][:n_pred].astype(float)
    net = supply - demand

    # PK derivatives
    d_supply = np.gradient(supply)
    d_demand = np.gradient(demand)
    d2_supply = np.gradient(d_supply)
    d2_demand = np.gradient(d_demand)
    d_net = np.gradient(net)

    # Post-prandial + IOB shape
    pp_feats = _build_pp_features(bg_sig, supply, n_pred)
    iob_feats = _build_iob_features(demand, n_pred)

    # Causal EMAs
    ema_1h = _causal_ema(bg_sig, 2.0 / (12 + 1))
    ema_4h = _causal_ema(bg_sig, 2.0 / (48 + 1))

    # Glucose momentum
    mom_feats = np.zeros((n_pred, 5))
    for lag_j, lag in enumerate([1, 3, 6, 12, 24]):
        for i in range(lag, n_pred):
            if np.isfinite(bg_sig[i]) and np.isfinite(bg_sig[i - lag]):
                mom_feats[i, lag_j] = bg_sig[i] - bg_sig[i - lag]

    extra = np.column_stack([
        d_supply[start:start + usable],
        d_demand[start:start + usable],
        d2_supply[start:start + usable],
        d2_demand[start:start + usable],
        d_net[start:start + usable],
        pp_feats[start:start + usable],
        iob_feats[start:start + usable],
        ema_1h[start:start + usable],
        ema_4h[start:start + usable],
        mom_feats[start:start + usable],
    ])
    return extra


def _build_tod_features(hours, n_pred, usable, start):
    """Build time-of-day conditioning features."""
    tod_feats = np.zeros((usable, 4))
    if hours is None:
        return tod_feats
    for i in range(usable):
        orig = i + start
        if orig < len(hours):
            h = hours[orig]
            tod_feats[i, 0] = np.sin(2 * np.pi * h / 24.0)
            tod_feats[i, 1] = np.cos(2 * np.pi * h / 24.0)
            h_int = int(h) % 24
            tod_feats[i, 2] = 1.0 if h_int in [4, 5, 6, 7, 8] else 0.0
            tod_feats[i, 3] = 1.0 if h_int in [22, 23, 0, 1, 2, 3] else 0.0
    return tod_feats


# ── EXP-921: Time-of-Day Conditioning ────────────────────────────────────────

@register('EXP-921', 'Time-of-Day Conditioning')
def exp_921(patients, detail=False):
    """Add hour-of-day features to the forward-looking base. Error budget shows
    4.4% is systematic ToD error. Features: hour_sin, hour_cos, is_dawn, is_night.
    """
    h_steps = 12
    start = 24
    base_r2s, tod_r2s = [], []
    per_patient = []

    for p in patients:
        d_fwd = _prepare_patient_forward(p, h_steps, start)
        if d_fwd is None:
            continue
        fd = d_fwd['fd']
        bg = d_fwd['bg']
        actual = d_fwd['actual']
        features = d_fwd['features']
        split = d_fwd['split']
        usable = d_fwd['usable']
        n_pred = d_fwd['n_pred']
        hours = d_fwd['hours']
        y_tr, y_val = actual[:split], actual[split:]

        # Forward baseline
        X_tr, X_val = features[:split], features[split:]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        vm_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
        if vm_tr.sum() < 50:
            continue
        pred_b, _ = _ridge_predict(
            np.nan_to_num(X_tr[vm_tr], nan=0.0), y_tr[vm_tr],
            np.nan_to_num(X_val[vm_val], nan=0.0))
        b_r2 = _r2(pred_b, y_val[vm_val])
        base_r2s.append(b_r2)

        # Use fallback hours if needed
        hours_fb = hours
        if hours_fb is None:
            hours_fb = _get_hours_fallback(p['df'], fd['n'])

        # Build ToD features
        tod_feats = _build_tod_features(hours_fb, n_pred, usable, start)

        X_tod = np.hstack([features, tod_feats])
        X_tr_t, X_val_t = X_tod[:split], X_tod[split:]
        vm_tr_t = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_t), axis=1)
        vm_val_t = np.isfinite(y_val) & np.all(np.isfinite(X_val_t), axis=1)
        if vm_tr_t.sum() < 50:
            continue
        pred_t, _ = _ridge_predict(
            np.nan_to_num(X_tr_t[vm_tr_t], nan=0.0), y_tr[vm_tr_t],
            np.nan_to_num(X_val_t[vm_val_t], nan=0.0))
        t_r2 = _r2(pred_t, y_val[vm_val_t])
        tod_r2s.append(t_r2)

        if detail:
            per_patient.append({
                'patient': d_fwd['name'],
                'forward_base': round(float(b_r2), 3) if np.isfinite(b_r2) else None,
                'with_tod': round(float(t_r2), 3) if np.isfinite(t_r2) else None,
            })

    base = round(float(np.mean(base_r2s)), 3) if base_r2s else None
    tod = round(float(np.mean(tod_r2s)), 3) if tod_r2s else None
    delta = round(tod - base, 3) if tod is not None and base is not None else None

    results = {
        'forward_base': base, 'with_tod': tod, 'improvement': delta,
        'n_patients': len(tod_r2s),
        'features_added': ['hour_sin', 'hour_cos', 'is_dawn', 'is_night'],
    }
    if detail:
        results['per_patient'] = per_patient

    return {
        'experiment': 'EXP-921', 'name': 'Time-of-Day Conditioning',
        'status': 'pass',
        'detail': (f'forward_base={base}, +tod={tod}, '
                   f'Δ={delta:+.3f}') if delta is not None else f'base={base}',
        'results': results,
    }


# ── EXP-922: Dawn/Day/Night Separate Models ─────────────────────────────────

@register('EXP-922', 'Dawn/Day/Night Separate Models')
def exp_922(patients, detail=False):
    """Split data into 3 time regimes (dawn 4-10, day 10-22, night 22-4).
    Train separate ridge models for each regime. Combine predictions based
    on time-of-day. Compare to single global model.
    """
    h_steps = 12
    start = 24
    global_r2s, regime_r2s = [], []
    per_patient = []

    def _hour_regime(h):
        h_int = int(h) % 24
        if 4 <= h_int < 10:
            return 'dawn'
        elif 10 <= h_int < 22:
            return 'day'
        else:
            return 'night'

    for p in patients:
        d_fwd = _prepare_patient_forward(p, h_steps, start)
        if d_fwd is None:
            continue
        fd = d_fwd['fd']
        bg = d_fwd['bg']
        actual = d_fwd['actual']
        features = d_fwd['features']
        split = d_fwd['split']
        usable = d_fwd['usable']
        n_pred = d_fwd['n_pred']
        hours = d_fwd['hours']
        y_tr, y_val = actual[:split], actual[split:]

        hours_fb = hours if hours is not None else _get_hours_fallback(p['df'], fd['n'])

        # Global forward baseline
        X_tr, X_val = features[:split], features[split:]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        vm_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
        if vm_tr.sum() < 50:
            continue
        pred_g, _ = _ridge_predict(
            np.nan_to_num(X_tr[vm_tr], nan=0.0), y_tr[vm_tr],
            np.nan_to_num(X_val[vm_val], nan=0.0))
        g_r2 = _r2(pred_g, y_val[vm_val])
        global_r2s.append(g_r2)

        # Assign regime labels
        regime_labels_tr = np.array([
            _hour_regime(hours_fb[i + start]) if (i + start) < len(hours_fb) else 'day'
            for i in range(split)])
        regime_labels_val = np.array([
            _hour_regime(hours_fb[i + start]) if (i + start) < len(hours_fb) else 'day'
            for i in range(split, usable)])

        # Train per-regime models, combine predictions
        combined_pred = np.full(usable - split, np.nan)
        combined_actual = y_val.copy()
        regime_ok = True

        for regime in ['dawn', 'day', 'night']:
            tr_mask = (regime_labels_tr == regime) & np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
            val_mask = (regime_labels_val == regime) & np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)

            if tr_mask.sum() < 30:
                # Fall back to global model for this regime
                if val_mask.sum() > 0:
                    pred_fb, _ = _ridge_predict(
                        np.nan_to_num(X_tr[vm_tr], nan=0.0), y_tr[vm_tr],
                        np.nan_to_num(X_val[val_mask], nan=0.0))
                    combined_pred[np.where(val_mask)[0]] = pred_fb
                continue

            pred_r, _ = _ridge_predict(
                np.nan_to_num(X_tr[tr_mask], nan=0.0), y_tr[tr_mask],
                np.nan_to_num(X_val[val_mask], nan=0.0))
            combined_pred[np.where(val_mask)[0]] = pred_r

        valid_combined = np.isfinite(combined_pred) & np.isfinite(combined_actual)
        if valid_combined.sum() < 20:
            continue
        r_r2 = _r2(combined_pred[valid_combined], combined_actual[valid_combined])
        regime_r2s.append(r_r2)

        if detail:
            regime_counts = {r: int(np.sum(regime_labels_val == r)) for r in ['dawn', 'day', 'night']}
            per_patient.append({
                'patient': d_fwd['name'],
                'global_r2': round(float(g_r2), 3) if np.isfinite(g_r2) else None,
                'regime_r2': round(float(r_r2), 3) if np.isfinite(r_r2) else None,
                'val_regime_counts': regime_counts,
            })

    base = round(float(np.mean(global_r2s)), 3) if global_r2s else None
    regime = round(float(np.mean(regime_r2s)), 3) if regime_r2s else None
    delta = round(regime - base, 3) if regime is not None and base is not None else None

    results = {
        'global_model': base, 'regime_model': regime, 'improvement': delta,
        'n_patients': len(regime_r2s),
        'regimes': {'dawn': '4am-10am', 'day': '10am-10pm', 'night': '10pm-4am'},
    }
    if detail:
        results['per_patient'] = per_patient

    return {
        'experiment': 'EXP-922', 'name': 'Dawn/Day/Night Separate Models',
        'status': 'pass',
        'detail': (f'global={base}, regime={regime}, '
                   f'Δ={delta:+.3f}') if delta is not None else f'global={base}',
        'results': results,
    }


# ── EXP-923: Minimum-Data Stacking Guard ────────────────────────────────────

@register('EXP-923', 'Min-Data Stacking Guard')
def exp_923(patients, detail=False):
    """Patient j (17K steps) degrades badly with CV stacking (-0.088). Test
    stacking with a data minimum threshold: if usable < 25K, fall back to
    simple ridge. Also test: regularize meta-learner more (alpha*=5) for
    small datasets (n < 30K).
    """
    h_steps = 12
    start = 24
    horizons = [6, 10, 14]
    n_folds = 5
    MIN_STEPS_STACKING = 25000
    SMALL_DATASET_THRESH = 30000

    unguarded_r2s, guarded_r2s, adaptive_r2s = [], [], []
    per_patient = []

    for p in patients:
        d_fwd = _prepare_patient_forward(p, h_steps, start)
        if d_fwd is None:
            continue
        fd = d_fwd['fd']
        bg = d_fwd['bg']
        actual = d_fwd['actual']
        features = d_fwd['features']
        split = d_fwd['split']
        usable = d_fwd['usable']
        n_pred = d_fwd['n_pred']
        hours = d_fwd['hours']
        nr = d_fwd['nr']
        y_tr, y_val = actual[:split], actual[split:]

        # Build extended features
        extra = _build_all_extra_features(fd, bg, hours, n_pred, usable, start)
        X_full = np.hstack([features, extra])
        X_tr_f, X_val_f = X_full[:split], X_full[split:]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_f), axis=1)
        vm_val = np.isfinite(y_val) & np.all(np.isfinite(X_val_f), axis=1)
        if vm_tr.sum() < 50:
            continue

        # --- Simple ridge (no stacking) ---
        pred_simple, _ = _ridge_predict(
            np.nan_to_num(X_tr_f[vm_tr], nan=0.0), y_tr[vm_tr],
            np.nan_to_num(X_val_f[vm_val], nan=0.0))
        simple_r2 = _r2(pred_simple, y_val[vm_val])

        # --- CV stacking (unguarded) ---
        def _do_cv_stacking(X_tr_in, y_tr_in, X_val_in, y_val_in, vm_tr_in, vm_val_in, meta_lam=10.0):
            n_valid_tr = int(vm_tr_in.sum())
            fold_size = n_valid_tr // n_folds
            if fold_size < 20:
                pred_fb, _ = _ridge_predict(
                    np.nan_to_num(X_tr_in[vm_tr_in], nan=0.0), y_tr_in[vm_tr_in],
                    np.nan_to_num(X_val_in[vm_val_in], nan=0.0), lam=10.0)
                return _r2(pred_fb, y_val_in[vm_val_in])

            train_valid_indices = np.where(vm_tr_in)[0]
            oof_predictions = np.full(len(y_tr_in), np.nan)

            for fold_i in range(n_folds):
                f_start = fold_i * fold_size
                f_end = min((fold_i + 1) * fold_size, len(train_valid_indices))
                if fold_i == n_folds - 1:
                    f_end = len(train_valid_indices)
                fold_val_idx = train_valid_indices[f_start:f_end]
                fold_tr_idx = np.concatenate([
                    train_valid_indices[:f_start], train_valid_indices[f_end:]])
                if len(fold_tr_idx) < 50 or len(fold_val_idx) < 10:
                    continue
                X_fold_tr = np.nan_to_num(X_tr_in[fold_tr_idx], nan=0.0)
                y_fold_tr = y_tr_in[fold_tr_idx]
                X_fold_val = np.nan_to_num(X_tr_in[fold_val_idx], nan=0.0)
                pred_fold, _ = _ridge_predict(X_fold_tr, y_fold_tr, X_fold_val, lam=10.0)
                oof_predictions[fold_val_idx] = pred_fold

            oof_col = oof_predictions.reshape(-1, 1)
            X_meta_tr = np.hstack([X_tr_in, oof_col])
            pred_full, _ = _ridge_predict(
                np.nan_to_num(X_tr_in[vm_tr_in], nan=0.0), y_tr_in[vm_tr_in],
                np.nan_to_num(X_val_in, nan=0.0), lam=10.0)
            X_meta_val = np.hstack([X_val_in, pred_full.reshape(-1, 1)])
            vm_meta_tr = np.isfinite(y_tr_in) & np.all(np.isfinite(X_meta_tr), axis=1)
            vm_meta_val = np.isfinite(y_val_in) & np.all(np.isfinite(X_meta_val), axis=1)
            if vm_meta_tr.sum() < 50:
                pred_fb, _ = _ridge_predict(
                    np.nan_to_num(X_tr_in[vm_tr_in], nan=0.0), y_tr_in[vm_tr_in],
                    np.nan_to_num(X_val_in[vm_val_in], nan=0.0), lam=10.0)
                return _r2(pred_fb, y_val_in[vm_val_in])
            pred_meta, _ = _ridge_predict(
                np.nan_to_num(X_meta_tr[vm_meta_tr], nan=0.0), y_tr_in[vm_meta_tr],
                np.nan_to_num(X_meta_val[vm_meta_val], nan=0.0), lam=meta_lam)
            return _r2(pred_meta, y_val_in[vm_meta_val])

        # Unguarded: always do CV stacking
        ungrd_r2 = _do_cv_stacking(X_tr_f, y_tr, X_val_f, y_val, vm_tr, vm_val, meta_lam=10.0)
        unguarded_r2s.append(ungrd_r2)

        # Guarded: fall back to simple ridge if too few steps
        if usable < MIN_STEPS_STACKING:
            grd_r2 = simple_r2
        else:
            grd_r2 = _do_cv_stacking(X_tr_f, y_tr, X_val_f, y_val, vm_tr, vm_val, meta_lam=10.0)
        guarded_r2s.append(grd_r2)

        # Adaptive: higher regularization for small datasets
        if usable < MIN_STEPS_STACKING:
            adp_r2 = simple_r2
        elif usable < SMALL_DATASET_THRESH:
            adp_r2 = _do_cv_stacking(X_tr_f, y_tr, X_val_f, y_val, vm_tr, vm_val, meta_lam=50.0)
        else:
            adp_r2 = _do_cv_stacking(X_tr_f, y_tr, X_val_f, y_val, vm_tr, vm_val, meta_lam=10.0)
        adaptive_r2s.append(adp_r2)

        if detail:
            per_patient.append({
                'patient': d_fwd['name'], 'usable_steps': usable,
                'simple_r2': round(float(simple_r2), 3) if np.isfinite(simple_r2) else None,
                'unguarded_stacking': round(float(ungrd_r2), 3) if np.isfinite(ungrd_r2) else None,
                'guarded_stacking': round(float(grd_r2), 3) if np.isfinite(grd_r2) else None,
                'adaptive_stacking': round(float(adp_r2), 3) if np.isfinite(adp_r2) else None,
                'method': 'simple' if usable < MIN_STEPS_STACKING else 'stacking',
            })

    ungrd = round(float(np.mean(unguarded_r2s)), 3) if unguarded_r2s else None
    grd = round(float(np.mean(guarded_r2s)), 3) if guarded_r2s else None
    adp = round(float(np.mean(adaptive_r2s)), 3) if adaptive_r2s else None

    results = {
        'unguarded_stacking': ungrd, 'guarded_stacking': grd,
        'adaptive_stacking': adp, 'n_patients': len(guarded_r2s),
        'min_steps_for_stacking': MIN_STEPS_STACKING,
        'small_dataset_threshold': SMALL_DATASET_THRESH,
    }
    if detail:
        results['per_patient'] = per_patient

    return {
        'experiment': 'EXP-923', 'name': 'Min-Data Stacking Guard',
        'status': 'pass',
        'detail': (f'unguarded={ungrd}, guarded={grd}, '
                   f'adaptive={adp}'),
        'results': results,
    }


# ── EXP-924: RFE on Forward Base Combined Features ──────────────────────────

@register('EXP-924', 'RFE Forward Combined')
def exp_924(patients, detail=False):
    """Start with all ~24+ combined features (forward sums + shape + PK
    derivatives + causal EMA + momentum). Use Recursive Feature Elimination
    to find optimal subset. Test subsets of size 8, 12, 16, 20, 24.
    """
    h_steps = 12
    start = 24
    subset_sizes = [8, 12, 16, 20, 24]

    # Collect data from all patients first
    all_X_tr, all_y_tr, all_X_val, all_y_val = [], [], [], []
    patient_slices = []

    for p in patients:
        d_fwd = _prepare_patient_forward(p, h_steps, start)
        if d_fwd is None:
            continue
        fd = d_fwd['fd']
        bg = d_fwd['bg']
        actual = d_fwd['actual']
        features = d_fwd['features']
        split = d_fwd['split']
        usable = d_fwd['usable']
        n_pred = d_fwd['n_pred']
        hours = d_fwd['hours']
        y_tr, y_val = actual[:split], actual[split:]

        extra = _build_all_extra_features(fd, bg, hours, n_pred, usable, start)
        X_full = np.hstack([features, extra])
        X_tr_f, X_val_f = X_full[:split], X_full[split:]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_f), axis=1)
        vm_val = np.isfinite(y_val) & np.all(np.isfinite(X_val_f), axis=1)
        if vm_tr.sum() < 50:
            continue

        all_X_tr.append(np.nan_to_num(X_tr_f[vm_tr], nan=0.0))
        all_y_tr.append(y_tr[vm_tr])
        all_X_val.append(np.nan_to_num(X_val_f[vm_val], nan=0.0))
        all_y_val.append(y_val[vm_val])
        patient_slices.append(d_fwd['name'])

    if not all_X_tr:
        return {
            'experiment': 'EXP-924', 'name': 'RFE Forward Combined',
            'status': 'pass', 'detail': 'insufficient data',
            'results': {},
        }

    X_tr_all = np.vstack(all_X_tr)
    y_tr_all = np.concatenate(all_y_tr)
    X_val_all = np.vstack(all_X_val)
    y_val_all = np.concatenate(all_y_val)
    n_features = X_tr_all.shape[1]

    # Full model baseline
    pred_full, w_full = _ridge_predict(X_tr_all, y_tr_all, X_val_all, lam=1.0)
    full_r2 = _r2(pred_full, y_val_all)

    # RFE: rank features by absolute weight, then test subsets
    if w_full is None:
        return {
            'experiment': 'EXP-924', 'name': 'RFE Forward Combined',
            'status': 'pass', 'detail': 'ridge solve failed',
            'results': {},
        }

    feat_importance = np.abs(w_full)
    feat_ranking = np.argsort(feat_importance)[::-1]  # most important first

    subset_results = {}
    for size in subset_sizes:
        if size > n_features:
            size = n_features
        selected = feat_ranking[:size]
        X_tr_sub = X_tr_all[:, selected]
        X_val_sub = X_val_all[:, selected]
        pred_sub, _ = _ridge_predict(X_tr_sub, y_tr_all, X_val_sub, lam=1.0)
        sub_r2 = _r2(pred_sub, y_val_all)
        subset_results[size] = round(float(sub_r2), 4) if np.isfinite(sub_r2) else None

    # Per-patient RFE with best subset
    best_size = max(subset_results, key=lambda k: subset_results[k] if subset_results[k] is not None else -1)
    best_selected = feat_ranking[:best_size]
    per_patient_r2s = []
    per_patient_detail = []

    for i in range(len(all_X_tr)):
        X_tr_sub = all_X_tr[i][:, best_selected]
        X_val_sub = all_X_val[i][:, best_selected]
        pred_sub, _ = _ridge_predict(X_tr_sub, all_y_tr[i], X_val_sub, lam=1.0)
        sub_r2 = _r2(pred_sub, all_y_val[i])
        per_patient_r2s.append(sub_r2)
        if detail:
            per_patient_detail.append({
                'patient': patient_slices[i],
                'rfe_r2': round(float(sub_r2), 3) if np.isfinite(sub_r2) else None,
            })

    mean_rfe = round(float(np.nanmean(per_patient_r2s)), 3) if per_patient_r2s else None

    results = {
        'full_model_r2': round(float(full_r2), 4) if np.isfinite(full_r2) else None,
        'n_total_features': n_features,
        'subset_r2s': subset_results,
        'best_subset_size': best_size,
        'mean_per_patient_rfe_r2': mean_rfe,
        'top_10_features': feat_ranking[:10].tolist(),
        'n_patients': len(patient_slices),
    }
    if detail:
        results['per_patient'] = per_patient_detail

    return {
        'experiment': 'EXP-924', 'name': 'RFE Forward Combined',
        'status': 'pass',
        'detail': (f'full={round(float(full_r2), 3)}, '
                   f'subsets={subset_results}, best_k={best_size}'),
        'results': results,
    }


# ── EXP-925: Heteroscedastic Prediction ─────────────────────────────────────

@register('EXP-925', 'Heteroscedastic Prediction')
def exp_925(patients, detail=False):
    """Model not just E[y|x] but also Var[y|x]:
    1. Train base ridge model
    2. Compute squared residuals
    3. Train second ridge model to predict log(squared_residual) from same features
    4. Use predicted variance for adaptive confidence intervals
    Report: correlation between predicted and actual squared residuals, coverage at 90%.
    """
    h_steps = 12
    start = 24
    correlations = []
    coverages_90 = []
    per_patient = []

    for p in patients:
        d_fwd = _prepare_patient_forward(p, h_steps, start)
        if d_fwd is None:
            continue
        fd = d_fwd['fd']
        bg = d_fwd['bg']
        actual = d_fwd['actual']
        features = d_fwd['features']
        split = d_fwd['split']
        usable = d_fwd['usable']
        n_pred = d_fwd['n_pred']
        hours = d_fwd['hours']
        y_tr, y_val = actual[:split], actual[split:]

        extra = _build_all_extra_features(fd, bg, hours, n_pred, usable, start)
        X_full = np.hstack([features, extra])
        X_tr_f, X_val_f = X_full[:split], X_full[split:]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_f), axis=1)
        vm_val = np.isfinite(y_val) & np.all(np.isfinite(X_val_f), axis=1)
        if vm_tr.sum() < 100:
            continue

        # Step 1: train base ridge
        X_tr_clean = np.nan_to_num(X_tr_f[vm_tr], nan=0.0)
        X_val_clean = np.nan_to_num(X_val_f[vm_val], nan=0.0)
        pred_base, _ = _ridge_predict(X_tr_clean, y_tr[vm_tr], X_val_clean)

        # Step 2: compute squared residuals on training set
        pred_tr, _ = _ridge_predict(X_tr_clean, y_tr[vm_tr], X_tr_clean)
        train_sq_resid = (y_tr[vm_tr] - pred_tr) ** 2
        log_sq_resid = np.log(train_sq_resid + 1e-6)

        # Step 3: train variance model
        pred_log_var_val, _ = _ridge_predict(
            np.nan_to_num(X_tr_clean, nan=0.0), log_sq_resid,
            np.nan_to_num(X_val_clean, nan=0.0), lam=10.0)

        # Actual squared residuals on validation
        actual_sq_resid = (y_val[vm_val] - pred_base) ** 2

        # Predicted variance
        pred_var = np.exp(pred_log_var_val)
        pred_std = np.sqrt(np.maximum(pred_var, 1e-6))

        # Correlation between predicted and actual squared residuals
        valid_mask = np.isfinite(pred_var) & np.isfinite(actual_sq_resid)
        if valid_mask.sum() < 20:
            continue
        corr = np.corrcoef(pred_var[valid_mask], actual_sq_resid[valid_mask])[0, 1]
        correlations.append(float(corr) if np.isfinite(corr) else 0.0)

        # 90% coverage: check if actual value falls within ±1.645*predicted_std
        z_90 = 1.645
        lower = pred_base - z_90 * pred_std
        upper = pred_base + z_90 * pred_std
        in_interval = (y_val[vm_val] >= lower) & (y_val[vm_val] <= upper)
        coverage = float(np.mean(in_interval))
        coverages_90.append(coverage)

        if detail:
            per_patient.append({
                'patient': d_fwd['name'],
                'var_correlation': round(float(corr), 3) if np.isfinite(corr) else None,
                'coverage_90': round(coverage, 3),
                'mean_pred_std': round(float(np.mean(pred_std)), 1),
            })

    mean_corr = round(float(np.mean(correlations)), 3) if correlations else None
    mean_cov = round(float(np.mean(coverages_90)), 3) if coverages_90 else None

    results = {
        'mean_var_correlation': mean_corr,
        'mean_coverage_90pct': mean_cov,
        'target_coverage': 0.90,
        'n_patients': len(correlations),
    }
    if detail:
        results['per_patient'] = per_patient

    return {
        'experiment': 'EXP-925', 'name': 'Heteroscedastic Prediction',
        'status': 'pass',
        'detail': (f'var_corr={mean_corr}, coverage_90={mean_cov}'),
        'results': results,
    }


# ── EXP-926: Residual Pattern Clustering ────────────────────────────────────

@register('EXP-926', 'Residual Pattern Clustering')
def exp_926(patients, detail=False):
    """Cluster prediction residuals to find systematic failure modes:
    1. Context vector: [hour, meal_proximity, bg_level, bg_velocity, supply_demand_ratio]
    2. Bin residuals into 10 quantile-based clusters by context
    3. Report mean residual and MAE per cluster
    4. Identify which contexts have highest systematic bias
    """
    h_steps = 12
    start = 24
    all_contexts = []
    all_residuals = []

    for p in patients:
        d_fwd = _prepare_patient_forward(p, h_steps, start)
        if d_fwd is None:
            continue
        fd = d_fwd['fd']
        bg = d_fwd['bg']
        actual = d_fwd['actual']
        features = d_fwd['features']
        split = d_fwd['split']
        usable = d_fwd['usable']
        n_pred = d_fwd['n_pred']
        hours = d_fwd['hours']
        y_tr, y_val = actual[:split], actual[split:]

        hours_fb = hours if hours is not None else _get_hours_fallback(p['df'], fd['n'])

        X_tr, X_val = features[:split], features[split:]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        vm_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
        if vm_tr.sum() < 50:
            continue

        pred_val, _ = _ridge_predict(
            np.nan_to_num(X_tr[vm_tr], nan=0.0), y_tr[vm_tr],
            np.nan_to_num(X_val[vm_val], nan=0.0))
        residuals = y_val[vm_val] - pred_val

        supply = fd['supply'][:n_pred].astype(float)
        demand = fd['demand'][:n_pred].astype(float)
        bg_sig = bg[:n_pred].astype(float)
        bg_sig[~np.isfinite(bg_sig)] = np.nanmean(bg_sig)

        # Meal proximity
        carb_thresh = np.percentile(supply[supply > 0], 50) if np.sum(supply > 0) > 10 else 0.05
        last_meal = -999
        meal_prox = np.zeros(n_pred)
        for i in range(n_pred):
            if supply[i] > carb_thresh:
                last_meal = i
            meal_prox[i] = min((i - last_meal) * 5.0 / 60.0, 12.0)

        val_indices = np.where(vm_val)[0]
        for j, idx_j in enumerate(val_indices):
            orig = split + idx_j + start
            if orig >= n_pred or orig >= len(hours_fb):
                continue
            h = hours_fb[orig]
            mp = meal_prox[orig] if orig < len(meal_prox) else 12.0
            bg_level = bg_sig[orig] if orig < len(bg_sig) else 120.0
            bg_vel = (bg_sig[orig] - bg_sig[orig - 1]) if orig >= 1 and orig < len(bg_sig) else 0.0
            sd_ratio = (supply[orig] / max(demand[orig], 1e-6)) if orig < len(supply) else 1.0
            all_contexts.append([h, mp, bg_level, bg_vel, sd_ratio])
            all_residuals.append(float(residuals[j]))

    if len(all_contexts) < 100:
        return {
            'experiment': 'EXP-926', 'name': 'Residual Pattern Clustering',
            'status': 'pass', 'detail': 'insufficient data',
            'results': {},
        }

    contexts = np.array(all_contexts)
    residuals_arr = np.array(all_residuals)
    n_clusters = 10
    context_labels = ['hour', 'meal_proximity', 'bg_level', 'bg_velocity', 'supply_demand_ratio']

    cluster_results = []
    for dim, label in enumerate(context_labels):
        dim_vals = contexts[:, dim]
        try:
            quantiles = np.percentile(dim_vals, np.linspace(0, 100, n_clusters + 1))
        except Exception:
            continue
        bins = np.digitize(dim_vals, quantiles[1:-1])

        dim_clusters = []
        for b in range(n_clusters):
            mask = bins == b
            if mask.sum() < 10:
                continue
            mean_resid = float(np.mean(residuals_arr[mask]))
            mae = float(np.mean(np.abs(residuals_arr[mask])))
            dim_clusters.append({
                'bin': b,
                'range': f'{quantiles[b]:.1f}-{quantiles[min(b+1, len(quantiles)-1)]:.1f}',
                'n': int(mask.sum()),
                'mean_residual': round(mean_resid, 2),
                'mae': round(mae, 1),
                'systematic_bias': round(abs(mean_resid), 2),
            })

        # Sort by systematic bias descending
        dim_clusters.sort(key=lambda x: x['systematic_bias'], reverse=True)
        cluster_results.append({
            'dimension': label,
            'clusters': dim_clusters,
            'worst_bias_bin': dim_clusters[0] if dim_clusters else None,
        })

    # Overall worst bias contexts
    worst_dims = sorted(cluster_results,
                        key=lambda x: x['worst_bias_bin']['systematic_bias'] if x['worst_bias_bin'] else 0,
                        reverse=True)

    return {
        'experiment': 'EXP-926', 'name': 'Residual Pattern Clustering',
        'status': 'pass',
        'detail': (f'n_points={len(residuals_arr)}, '
                   f'worst_bias_dim={worst_dims[0]["dimension"] if worst_dims else "?"}, '
                   f'bias={worst_dims[0]["worst_bias_bin"]["systematic_bias"] if worst_dims and worst_dims[0]["worst_bias_bin"] else "?"}'),
        'results': {
            'n_data_points': len(residuals_arr),
            'n_clusters': n_clusters,
            'per_dimension': cluster_results,
            'worst_dimension': worst_dims[0]['dimension'] if worst_dims else None,
            'overall_mae': round(float(np.mean(np.abs(residuals_arr))), 1),
            'overall_mean_residual': round(float(np.mean(residuals_arr)), 2),
        },
    }


# ── EXP-927: Cross-Validated Oracle with Proper Split ───────────────────────

@register('EXP-927', 'CV Oracle Proper Split')
def exp_927(patients, detail=False):
    """Fix the trivial oracle (EXP-918 gave R²=1.0). Compute proper oracle:
    feature = actual future BG at prediction time (BG[i+12] for 60-min),
    but use cross-validation: train on folds 1-4, predict fold 5.
    This gives the true upper bound on R² with future information.
    The oracle should be LESS than 1.0 due to regularization and noise.
    """
    h_steps = 12
    start = 24
    n_folds = 5
    model_r2s, oracle_r2s = [], []
    per_patient = []

    for p in patients:
        d_fwd = _prepare_patient_forward(p, h_steps, start)
        if d_fwd is None:
            continue
        bg = d_fwd['bg']
        actual = d_fwd['actual']
        features = d_fwd['features']
        split = d_fwd['split']
        usable = d_fwd['usable']
        y_tr, y_val = actual[:split], actual[split:]

        # Standard model R²
        X_tr, X_val = features[:split], features[split:]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        vm_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
        if vm_tr.sum() < 100:
            continue
        pred_m, _ = _ridge_predict(
            np.nan_to_num(X_tr[vm_tr], nan=0.0), y_tr[vm_tr],
            np.nan_to_num(X_val[vm_val], nan=0.0))
        m_r2 = _r2(pred_m, y_val[vm_val])
        model_r2s.append(m_r2)

        # Oracle features: actual future BG as feature, but with CV
        oracle_feat = actual.reshape(-1, 1)
        X_oracle = np.hstack([features, oracle_feat])
        X_tr_o = X_oracle[:split]
        X_val_o = X_oracle[split:]

        # 5-fold CV on validation set to prevent oracle leakage
        vm_val_o = np.isfinite(y_val) & np.all(np.isfinite(X_val_o), axis=1)
        val_valid_indices = np.where(vm_val_o)[0]
        n_val_valid = len(val_valid_indices)
        if n_val_valid < 50:
            continue

        fold_size = n_val_valid // n_folds
        if fold_size < 10:
            continue

        oracle_preds = np.full(len(y_val), np.nan)
        for fold_i in range(n_folds):
            f_start = fold_i * fold_size
            f_end = min((fold_i + 1) * fold_size, n_val_valid)
            if fold_i == n_folds - 1:
                f_end = n_val_valid

            test_idx = val_valid_indices[f_start:f_end]
            train_idx = np.concatenate([val_valid_indices[:f_start], val_valid_indices[f_end:]])
            if len(train_idx) < 30 or len(test_idx) < 5:
                continue

            # Combine original training set + CV-train portion of validation
            X_cv_tr = np.vstack([
                np.nan_to_num(X_tr_o[vm_tr], nan=0.0),
                np.nan_to_num(X_val_o[train_idx], nan=0.0)])
            y_cv_tr = np.concatenate([y_tr[vm_tr], y_val[train_idx]])

            X_cv_test = np.nan_to_num(X_val_o[test_idx], nan=0.0)
            pred_fold, _ = _ridge_predict(X_cv_tr, y_cv_tr, X_cv_test, lam=1.0)
            oracle_preds[test_idx] = pred_fold

        valid_oracle = np.isfinite(oracle_preds) & np.isfinite(y_val)
        if valid_oracle.sum() < 20:
            continue
        o_r2 = _r2(oracle_preds[valid_oracle], y_val[valid_oracle])
        oracle_r2s.append(o_r2)

        if detail or True:
            per_patient.append({
                'patient': d_fwd['name'],
                'model_r2': round(float(m_r2), 3) if np.isfinite(m_r2) else None,
                'cv_oracle_r2': round(float(o_r2), 3) if np.isfinite(o_r2) else None,
                'gap': round(float(o_r2 - m_r2), 3) if np.isfinite(m_r2) and np.isfinite(o_r2) else None,
            })

    mean_model = round(float(np.mean(model_r2s)), 3) if model_r2s else None
    mean_oracle = round(float(np.mean(oracle_r2s)), 3) if oracle_r2s else None
    mean_gap = round(mean_oracle - mean_model, 3) if mean_model is not None and mean_oracle is not None else None

    results = {
        'mean_model_r2': mean_model, 'mean_cv_oracle_r2': mean_oracle,
        'mean_gap': mean_gap, 'n_patients': len(oracle_r2s),
        'n_folds': n_folds,
        'per_patient': per_patient,
    }

    return {
        'experiment': 'EXP-927', 'name': 'CV Oracle Proper Split',
        'status': 'pass',
        'detail': (f'model={mean_model}, cv_oracle={mean_oracle}, '
                   f'gap={mean_gap}'),
        'results': results,
    }


# ── EXP-928: Definitive Best Model ──────────────────────────────────────────

@register('EXP-928', 'Definitive Best Model')
def exp_928(patients, detail=False):
    """KEY experiment: Combine the best techniques from 100 experiments:
    1. Forward-looking supply/demand sums (base=0.533)
    2. All shape features (postprandial + IOB)
    3. Causal EMA
    4. ToD features (from EXP-921)
    5. 5-fold CV stacking at horizons 3/5/7
    6. Minimum-data guard for small patients
    7. Per-patient evaluation with guard rails
    This should produce the definitive campaign SOTA.
    """
    h_steps = 12
    start = 24
    horizons = [6, 10, 14]  # 30, 50, 70 min
    n_folds = 5
    MIN_STEPS_STACKING = 25000

    base_r2s, sota_r2s = [], []
    per_patient = []

    for p in patients:
        d_fwd = _prepare_patient_forward(p, h_steps, start)
        if d_fwd is None:
            continue
        fd = d_fwd['fd']
        bg = d_fwd['bg']
        actual = d_fwd['actual']
        features = d_fwd['features']
        split = d_fwd['split']
        usable = d_fwd['usable']
        n_pred = d_fwd['n_pred']
        hours = d_fwd['hours']
        nr = d_fwd['nr']
        y_tr, y_val = actual[:split], actual[split:]

        # Forward baseline for reference
        X_tr, X_val = features[:split], features[split:]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        vm_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
        if vm_tr.sum() < 50:
            continue
        pred_b, _ = _ridge_predict(
            np.nan_to_num(X_tr[vm_tr], nan=0.0), y_tr[vm_tr],
            np.nan_to_num(X_val[vm_val], nan=0.0))
        b_r2 = _r2(pred_b, y_val[vm_val])
        base_r2s.append(b_r2)

        # === Build ALL productive features ===
        hours_fb = hours if hours is not None else _get_hours_fallback(p['df'], fd['n'])

        # 1. Standard extra features (PK deriv + shape + causal EMA + momentum)
        extra = _build_all_extra_features(fd, bg, hours, n_pred, usable, start)

        # 2. ToD features (EXP-921)
        tod_feats = _build_tod_features(hours_fb, n_pred, usable, start)

        # 3. Multi-horizon predictions
        h_preds = {}
        for h in horizons:
            n_pred_h = nr - h
            if n_pred_h - start < usable:
                continue
            actual_h = bg[h + 1 + start: h + 1 + start + usable]
            if len(actual_h) < usable:
                continue
            feat_h = _build_features_base_forward(fd, hours, n_pred_h, h)
            feat_h = feat_h[start:start + usable]
            X_tr_h = feat_h[:split]
            y_tr_h = actual_h[:split]
            valid_h = np.isfinite(y_tr_h) & np.all(np.isfinite(X_tr_h), axis=1)
            if valid_h.sum() < 50:
                continue
            _, w_h = _ridge_predict(
                np.nan_to_num(X_tr_h[valid_h], nan=0.0), y_tr_h[valid_h],
                np.nan_to_num(X_tr_h[:1], nan=0.0), lam=0.1)
            if w_h is not None:
                h_preds[h] = np.nan_to_num(feat_h, nan=0.0) @ w_h

        if len(h_preds) < 2:
            # Without multi-horizon, use simple model with all features
            X_full = np.hstack([features, extra, tod_feats])
            X_tr_f, X_val_f = X_full[:split], X_full[split:]
            vm_tr_f = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_f), axis=1)
            vm_val_f = np.isfinite(y_val) & np.all(np.isfinite(X_val_f), axis=1)
            if vm_tr_f.sum() < 50:
                continue
            pred_s, _ = _ridge_predict(
                np.nan_to_num(X_tr_f[vm_tr_f], nan=0.0), y_tr[vm_tr_f],
                np.nan_to_num(X_val_f[vm_val_f], nan=0.0))
            s_r2 = _r2(pred_s, y_val[vm_val_f])
            if np.isfinite(s_r2):
                sota_r2s.append(s_r2)
                per_patient.append({
                    'patient': d_fwd['name'],
                    'forward_base': round(float(b_r2), 3) if np.isfinite(b_r2) else None,
                    'sota': round(float(s_r2), 3),
                    'delta': round(float(s_r2 - b_r2), 3) if np.isfinite(b_r2) else None,
                    'method': 'simple_all_features',
                })
            continue

        stack = np.column_stack([h_preds[h] for h in sorted(h_preds)])
        pred_std = np.std(stack, axis=1, keepdims=True)

        # Combine: forward features + extra + tod + horizon stack + disagreement
        X_grand = np.hstack([features, extra, tod_feats, stack, pred_std])

        X_tr_g = X_grand[:split]
        X_val_g = X_grand[split:]
        vm_tr_g = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_g), axis=1)
        vm_val_g = np.isfinite(y_val) & np.all(np.isfinite(X_val_g), axis=1)

        if vm_tr_g.sum() < 50:
            continue

        # === Apply stacking guard ===
        use_stacking = usable >= MIN_STEPS_STACKING

        if not use_stacking:
            # Simple ridge for small patients
            pred_g, _ = _ridge_predict(
                np.nan_to_num(X_tr_g[vm_tr_g], nan=0.0), y_tr[vm_tr_g],
                np.nan_to_num(X_val_g[vm_val_g], nan=0.0), lam=10.0)
            g_r2 = _r2(pred_g, y_val[vm_val_g])
            method = 'simple_guarded'
        else:
            # 5-fold CV stacking
            n_valid_tr = int(vm_tr_g.sum())
            fold_size = n_valid_tr // n_folds
            if fold_size < 20:
                pred_g, _ = _ridge_predict(
                    np.nan_to_num(X_tr_g[vm_tr_g], nan=0.0), y_tr[vm_tr_g],
                    np.nan_to_num(X_val_g[vm_val_g], nan=0.0), lam=10.0)
                g_r2 = _r2(pred_g, y_val[vm_val_g])
                method = 'simple_fold_guard'
            else:
                train_valid_indices = np.where(vm_tr_g)[0]
                oof_predictions = np.full(split, np.nan)

                for fold_i in range(n_folds):
                    f_start = fold_i * fold_size
                    f_end = min((fold_i + 1) * fold_size, len(train_valid_indices))
                    if fold_i == n_folds - 1:
                        f_end = len(train_valid_indices)
                    fold_val_idx = train_valid_indices[f_start:f_end]
                    fold_tr_idx = np.concatenate([
                        train_valid_indices[:f_start], train_valid_indices[f_end:]])
                    if len(fold_tr_idx) < 50 or len(fold_val_idx) < 10:
                        continue
                    X_fold_tr = np.nan_to_num(X_tr_g[fold_tr_idx], nan=0.0)
                    y_fold_tr = y_tr[fold_tr_idx]
                    X_fold_val = np.nan_to_num(X_tr_g[fold_val_idx], nan=0.0)
                    pred_fold, _ = _ridge_predict(X_fold_tr, y_fold_tr, X_fold_val, lam=10.0)
                    oof_predictions[fold_val_idx] = pred_fold

                oof_col = oof_predictions[:split].reshape(-1, 1)
                X_meta_tr = np.hstack([X_tr_g, oof_col])

                pred_full_train, _ = _ridge_predict(
                    np.nan_to_num(X_tr_g[vm_tr_g], nan=0.0), y_tr[vm_tr_g],
                    np.nan_to_num(X_val_g, nan=0.0), lam=10.0)
                X_meta_val = np.hstack([X_val_g, pred_full_train.reshape(-1, 1)])

                vm_meta_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_meta_tr), axis=1)
                vm_meta_val = np.isfinite(y_val) & np.all(np.isfinite(X_meta_val), axis=1)

                if vm_meta_tr.sum() < 50:
                    pred_g, _ = _ridge_predict(
                        np.nan_to_num(X_tr_g[vm_tr_g], nan=0.0), y_tr[vm_tr_g],
                        np.nan_to_num(X_val_g[vm_val_g], nan=0.0), lam=10.0)
                    g_r2 = _r2(pred_g, y_val[vm_val_g])
                    method = 'simple_meta_guard'
                else:
                    pred_meta, _ = _ridge_predict(
                        np.nan_to_num(X_meta_tr[vm_meta_tr], nan=0.0), y_tr[vm_meta_tr],
                        np.nan_to_num(X_meta_val[vm_meta_val], nan=0.0), lam=10.0)
                    g_r2 = _r2(pred_meta, y_val[vm_meta_val])
                    method = 'cv_stacking'

        if np.isfinite(g_r2):
            sota_r2s.append(g_r2)
            per_patient.append({
                'patient': d_fwd['name'],
                'forward_base': round(float(b_r2), 3) if np.isfinite(b_r2) else None,
                'sota': round(float(g_r2), 3),
                'delta': round(float(g_r2 - b_r2), 3) if np.isfinite(b_r2) else None,
                'method': method,
                'usable_steps': usable,
            })

    base = round(float(np.mean(base_r2s)), 3) if base_r2s else None
    sota = round(float(np.mean(sota_r2s)), 3) if sota_r2s else None
    delta = round(sota - base, 3) if sota is not None and base is not None else None

    # Per-patient sort by SOTA R²
    per_patient.sort(key=lambda x: x['sota'], reverse=True)

    results = {
        'forward_base': base, 'definitive_sota': sota,
        'improvement_vs_base': delta,
        'n_patients': len(sota_r2s),
        'practical_ceiling': 0.567,
        'oracle_ceiling': 0.613,
        'pct_of_oracle': round(float(sota / 0.613 * 100), 1) if sota else None,
        'features_used': [
            'forward_supply_demand_16', 'pk_derivatives_5',
            'postprandial_shape_5', 'iob_shape_5', 'causal_ema_2',
            'glucose_momentum_5', 'tod_features_4',
            'multi_horizon_stack_3', 'prediction_disagreement_1',
            'cv_stacking_meta_1',
        ],
        'total_features': '~47 + meta',
        'stacking_guard': f'simple if usable < {MIN_STEPS_STACKING}',
        'per_patient': per_patient,
    }

    return {
        'experiment': 'EXP-928', 'name': 'Definitive Best Model',
        'status': 'pass',
        'detail': (f'forward_base={base}, SOTA={sota}, '
                   f'Δ={delta:+.3f}, '
                   f'%oracle={results["pct_of_oracle"]}%') if delta is not None else f'base={base}',
        'results': results,
    }


# ── EXP-929: Clarke Error Grid Evaluation ───────────────────────────────────

@register('EXP-929', 'Clarke Error Grid')
def exp_929(patients, detail=False):
    """Evaluate the best model on clinical metrics:
    - Zone A: within 20% or both < 70 mg/dL (clinically accurate)
    - Zone B: > 20% but would not lead to inappropriate treatment
    - Compute % in each Clarke zone (A through E)
    - Also compute: MAE, RMSE, MARD (mean absolute relative difference)
    For each patient, report Clarke A% and MARD.
    """
    h_steps = 12
    start = 24
    per_patient = []
    all_pred, all_actual = [], []

    def _clarke_zone(ref, pred_val):
        """Classify a single (reference, prediction) pair into Clarke zone A-E.
        Both values in mg/dL."""
        if ref <= 0:
            return 'E'
        # Zone A: within 20% or both < 70
        if (ref < 70 and pred_val < 70):
            return 'A'
        if ref != 0 and abs(pred_val - ref) / ref <= 0.20:
            return 'A'
        # Zone E: ref < 70 and pred > 180, or ref > 180 and pred < 70
        if (ref >= 180 and pred_val <= 70) or (ref <= 70 and pred_val >= 180):
            return 'E'
        # Zone D: ref < 70 and pred 70-180, or ref > 240 and pred 70-180
        if ref <= 70 and 70 < pred_val < 180:
            return 'D'
        if ref >= 240 and 70 < pred_val < 180:
            return 'D'
        # Zone C: ref 70-180 and pred < 70, or ref 70-180 and pred > 180
        if 70 < ref < 180 and pred_val < 70:
            return 'C'
        if 70 < ref < 180 and pred_val > 180:
            return 'C'
        # Zone B: everything else
        return 'B'

    for p in patients:
        d_fwd = _prepare_patient_forward(p, h_steps, start)
        if d_fwd is None:
            continue
        fd = d_fwd['fd']
        bg = d_fwd['bg']
        actual = d_fwd['actual']
        features = d_fwd['features']
        split = d_fwd['split']
        usable = d_fwd['usable']
        n_pred = d_fwd['n_pred']
        hours = d_fwd['hours']
        y_tr, y_val = actual[:split], actual[split:]

        # Build full feature set (same as EXP-928 without stacking for simplicity)
        extra = _build_all_extra_features(fd, bg, hours, n_pred, usable, start)
        hours_fb = hours if hours is not None else _get_hours_fallback(p['df'], fd['n'])
        tod_feats = _build_tod_features(hours_fb, n_pred, usable, start)

        X_full = np.hstack([features, extra, tod_feats])
        X_tr_f, X_val_f = X_full[:split], X_full[split:]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_f), axis=1)
        vm_val = np.isfinite(y_val) & np.all(np.isfinite(X_val_f), axis=1)
        if vm_tr.sum() < 50 or vm_val.sum() < 20:
            continue

        pred, _ = _ridge_predict(
            np.nan_to_num(X_tr_f[vm_tr], nan=0.0), y_tr[vm_tr],
            np.nan_to_num(X_val_f[vm_val], nan=0.0))

        ref_vals = y_val[vm_val]
        pred_vals = pred

        # Ensure mg/dL: if ISF < 15 in the patient data, values might be mmol/L
        if np.nanmean(ref_vals) < 30:
            ref_vals = ref_vals * 18.0182
            pred_vals = pred_vals * 18.0182

        valid = np.isfinite(ref_vals) & np.isfinite(pred_vals) & (ref_vals > 0)
        ref_v = ref_vals[valid]
        pred_v = pred_vals[valid]

        if len(ref_v) < 20:
            continue

        all_pred.extend(pred_v.tolist())
        all_actual.extend(ref_v.tolist())

        # Clarke zones
        zones = {'A': 0, 'B': 0, 'C': 0, 'D': 0, 'E': 0}
        for j in range(len(ref_v)):
            z = _clarke_zone(ref_v[j], pred_v[j])
            zones[z] += 1
        total = sum(zones.values())
        zone_pct = {k: round(v / total * 100, 1) for k, v in zones.items()}

        # MAE, RMSE, MARD
        errors = np.abs(ref_v - pred_v)
        mae = float(np.mean(errors))
        rmse = float(np.sqrt(np.mean(errors ** 2)))
        rel_errors = errors / np.maximum(ref_v, 1.0)
        mard = float(np.mean(rel_errors) * 100)  # in percent

        per_patient.append({
            'patient': d_fwd['name'],
            'clarke_A_pct': zone_pct['A'],
            'clarke_B_pct': zone_pct['B'],
            'clarke_zones': zone_pct,
            'mae_mgdl': round(mae, 1),
            'rmse_mgdl': round(rmse, 1),
            'mard_pct': round(mard, 1),
            'n_predictions': total,
        })

    if not per_patient:
        return {
            'experiment': 'EXP-929', 'name': 'Clarke Error Grid',
            'status': 'pass', 'detail': 'insufficient data',
            'results': {},
        }

    # Aggregate
    mean_clarke_a = round(float(np.mean([p['clarke_A_pct'] for p in per_patient])), 1)
    mean_clarke_ab = round(float(np.mean([p['clarke_A_pct'] + p['clarke_B_pct'] for p in per_patient])), 1)
    mean_mae = round(float(np.mean([p['mae_mgdl'] for p in per_patient])), 1)
    mean_rmse = round(float(np.mean([p['rmse_mgdl'] for p in per_patient])), 1)
    mean_mard = round(float(np.mean([p['mard_pct'] for p in per_patient])), 1)

    return {
        'experiment': 'EXP-929', 'name': 'Clarke Error Grid',
        'status': 'pass',
        'detail': (f'Clarke_A={mean_clarke_a}%, A+B={mean_clarke_ab}%, '
                   f'MAE={mean_mae}mg/dL, MARD={mean_mard}%'),
        'results': {
            'mean_clarke_A_pct': mean_clarke_a,
            'mean_clarke_AB_pct': mean_clarke_ab,
            'mean_mae_mgdl': mean_mae,
            'mean_rmse_mgdl': mean_rmse,
            'mean_mard_pct': mean_mard,
            'n_patients': len(per_patient),
            'per_patient': per_patient,
        },
    }


# ── EXP-930: Multi-Step Recursive Prediction ───────────────────────────────

@register('EXP-930', 'Multi-Step Recursive Prediction')
def exp_930(patients, detail=False):
    """Test recursive prediction: predict BG+30min, then use that prediction
    as input feature to predict BG+60min:
    1. Train model_30: features -> BG+30
    2. Train model_60: features + predicted_BG+30 -> BG+60
    3. Compare to direct 60-min prediction
    Tests whether intermediate predictions carry useful information.
    """
    h_steps_30 = 6   # 30-min horizon
    h_steps_60 = 12  # 60-min horizon
    start = 24
    direct_r2s, recursive_r2s = [], []
    per_patient = []

    for p in patients:
        d_fwd = _prepare_patient_forward(p, h_steps_60, start)
        if d_fwd is None:
            continue
        fd = d_fwd['fd']
        bg = d_fwd['bg']
        actual_60 = d_fwd['actual']
        features = d_fwd['features']
        split = d_fwd['split']
        usable = d_fwd['usable']
        n_pred = d_fwd['n_pred']
        hours = d_fwd['hours']
        nr = d_fwd['nr']
        y_tr_60, y_val_60 = actual_60[:split], actual_60[split:]

        # Direct 60-min model
        extra = _build_all_extra_features(fd, bg, hours, n_pred, usable, start)
        X_full = np.hstack([features, extra])
        X_tr, X_val = X_full[:split], X_full[split:]
        vm_tr = np.isfinite(y_tr_60) & np.all(np.isfinite(X_tr), axis=1)
        vm_val = np.isfinite(y_val_60) & np.all(np.isfinite(X_val), axis=1)
        if vm_tr.sum() < 50:
            continue

        pred_direct, _ = _ridge_predict(
            np.nan_to_num(X_tr[vm_tr], nan=0.0), y_tr_60[vm_tr],
            np.nan_to_num(X_val[vm_val], nan=0.0))
        dir_r2 = _r2(pred_direct, y_val_60[vm_val])
        direct_r2s.append(dir_r2)

        # Step 1: 30-min model
        # Need actual 30-min BG values for training
        actual_30 = bg[h_steps_30 + 1 + start: h_steps_30 + 1 + start + usable]
        if len(actual_30) < usable:
            continue

        y_tr_30, y_val_30 = actual_30[:split], actual_30[split:]
        vm_tr_30 = np.isfinite(y_tr_30) & np.all(np.isfinite(X_tr), axis=1)
        if vm_tr_30.sum() < 50:
            continue

        # Train 30-min model on training set
        pred_30_tr, w_30 = _ridge_predict(
            np.nan_to_num(X_tr[vm_tr_30], nan=0.0), y_tr_30[vm_tr_30],
            np.nan_to_num(X_tr, nan=0.0))
        if w_30 is None:
            continue

        # Predict 30-min for all data points
        pred_30_all = np.nan_to_num(X_full, nan=0.0) @ w_30

        # Step 2: 60-min model with predicted BG+30 as extra feature
        pred_30_col = pred_30_all.reshape(-1, 1)
        X_recursive = np.hstack([X_full, pred_30_col])
        X_tr_r, X_val_r = X_recursive[:split], X_recursive[split:]
        vm_tr_r = np.isfinite(y_tr_60) & np.all(np.isfinite(X_tr_r), axis=1)
        vm_val_r = np.isfinite(y_val_60) & np.all(np.isfinite(X_val_r), axis=1)
        if vm_tr_r.sum() < 50:
            continue

        pred_recursive, _ = _ridge_predict(
            np.nan_to_num(X_tr_r[vm_tr_r], nan=0.0), y_tr_60[vm_tr_r],
            np.nan_to_num(X_val_r[vm_val_r], nan=0.0))
        rec_r2 = _r2(pred_recursive, y_val_60[vm_val_r])
        recursive_r2s.append(rec_r2)

        if detail:
            # Also report 30-min model accuracy
            pred_30_val = np.nan_to_num(X_val, nan=0.0) @ w_30
            vm_30_val = np.isfinite(y_val_30) & np.isfinite(pred_30_val)
            r2_30 = _r2(pred_30_val[vm_30_val], y_val_30[vm_30_val])
            per_patient.append({
                'patient': d_fwd['name'],
                'direct_60min_r2': round(float(dir_r2), 3) if np.isfinite(dir_r2) else None,
                'recursive_60min_r2': round(float(rec_r2), 3) if np.isfinite(rec_r2) else None,
                'model_30min_r2': round(float(r2_30), 3) if np.isfinite(r2_30) else None,
            })

    direct = round(float(np.mean(direct_r2s)), 3) if direct_r2s else None
    recursive = round(float(np.mean(recursive_r2s)), 3) if recursive_r2s else None
    delta = round(recursive - direct, 3) if recursive is not None and direct is not None else None

    results = {
        'direct_60min': direct, 'recursive_60min': recursive,
        'improvement': delta, 'n_patients': len(recursive_r2s),
        'method': 'features -> BG+30 -> features+pred_30 -> BG+60',
    }
    if detail:
        results['per_patient'] = per_patient

    return {
        'experiment': 'EXP-930', 'name': 'Multi-Step Recursive Prediction',
        'status': 'pass',
        'detail': (f'direct_60min={direct}, recursive={recursive}, '
                   f'Δ={delta:+.3f}') if delta is not None else f'direct={direct}',
        'results': results,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def _save(result, save_dir):
    save_dir = Path(save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)
    name = (f"exp_{result['experiment'].lower().replace('-', '_')}_"
            f"{result['name'].lower().replace(' ', '_').replace('/', '_')}.json")
    with open(save_dir / name, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    print(f"  Saved: {save_dir / name}")


def main():
    parser = argparse.ArgumentParser(
        description='EXP-921–930: ToD, Guards, RFE, Clinical Metrics & Definitive SOTA')
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--max-patients', type=int, default=11)
    parser.add_argument('--experiment', type=str, default=None)
    args = parser.parse_args()

    save_dir = PATIENTS_DIR.parent.parent / "experiments" if args.save else None
    patients = load_patients(PATIENTS_DIR, max_patients=args.max_patients)

    for exp_id, exp_info in EXPERIMENTS.items():
        if args.experiment and exp_id != args.experiment:
            continue
        print(f"\n{'=' * 60}")
        print(f"Running {exp_id}: {exp_info['name']}")
        print(f"{'=' * 60}")
        t0 = time.time()
        try:
            result = exp_info['func'](patients, detail=args.detail)
            result['elapsed_seconds'] = round(time.time() - t0, 1)
            print(f"  Status: {result['status']}")
            print(f"  Detail: {result['detail']}")
            print(f"  Time: {result['elapsed_seconds']}s")
            if args.save and save_dir:
                _save(result, save_dir)
        except Exception as e:
            print(f"  FAILED: {e}")
            import traceback; traceback.print_exc()
    print(f"\n{'=' * 60}")
    print("All experiments complete")


if __name__ == '__main__':
    main()
