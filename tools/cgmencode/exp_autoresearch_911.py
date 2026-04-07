#!/usr/bin/env python3
"""EXP-911–920: Forward-Base Feature Engineering & Grand CV Stacking

Building on the 901–910 batch which established:
  - Forward-looking sums: base R²≈0.534 (vs backward 0.506)
  - PK derivatives: +0.009
  - Post-prandial shape: +0.006
  - IOB curve shape: +0.004
  - Multi-horizon CV stacking: +0.027
  - Causal EMA: +0.005
  - Grand CV stacking from backward base: R²=0.560
  - Projected forward+shape+stacking SOTA: ~0.576
  - Oracle ceiling: 0.613

This batch rebuilds every feature on the forward-looking base, combines all
productive signals, and pushes toward the oracle ceiling via enhanced CV
stacking with the best feature set.

EXP-911: Forward-Base Enhanced Features (establish corrected baseline)
EXP-912: Forward-Base + PK Derivatives
EXP-913: Forward-Base + All Shape Features
EXP-914: Forward-Base + All Productive Features Combined
EXP-915: Glucose Momentum Features (multi-scale BG deltas)
EXP-916: Basal vs Bolus Insulin Decomposition
EXP-917: Carb-Free Interval Analysis (diagnostic + feature)
EXP-918: Per-Patient Oracle Ceiling
EXP-919: Forward-Base CV Stacking with Best Features (KEY experiment)
EXP-920: Error Budget Analysis (diagnostic)
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


def _r2(pred, actual):
    pred, actual = np.asarray(pred, dtype=float), np.asarray(actual, dtype=float)
    mask = np.isfinite(pred) & np.isfinite(actual)
    if mask.sum() < 10:
        return float('nan')
    p, a = pred[mask], actual[mask]
    ss_res = np.sum((a - p)**2)
    ss_tot = np.sum((a - np.mean(a))**2)
    return 1.0 - ss_res / ss_tot if ss_tot > 1e-10 else float('nan')


def _build_features_base(fd, hours, n_pred, h_steps):
    bg = fd['bg']
    resid = fd['resid']
    nr = len(resid)
    features = np.zeros((n_pred, 8))
    for i in range(n_pred):
        features[i, 0] = bg[i]
        features[i, 1] = np.sum(fd['supply'][max(0, i - h_steps):i])
        features[i, 2] = np.sum(fd['demand'][max(0, i - h_steps):i])
        features[i, 3] = np.sum(fd['hepatic'][max(0, i - h_steps):i])
        features[i, 4] = resid[i] if i < nr else 0
        if hours is not None and i < len(hours):
            features[i, 5] = np.sin(2 * np.pi * hours[i] / 24.0)
            features[i, 6] = np.cos(2 * np.pi * hours[i] / 24.0)
        features[i, 7] = 1.0
    return features


def _build_features_base_forward(fd, hours, n_pred, h_steps):
    """Like _build_features_base but with FORWARD-looking supply/demand sums."""
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
            extra[i, 6] = np.polyfit(np.arange(len(vw)), vw, 1)[0]
        extra[i, 7] = bg[orig] ** 2 / 1000.0
    return np.hstack([base, extra]), usable


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


def _prepare_patient(p, h_steps=12, start=24):
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


def _prepare_patient_forward(p, h_steps=12, start=24):
    """Like _prepare_patient but with forward-looking supply/demand sums."""
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
    """Post-prandial shape features (from EXP-893)."""
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
    """IOB curve shape features (from EXP-898)."""
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


# ── EXP-911: Forward-Base Enhanced Features ──────────────────────────────────

@register('EXP-911', 'Forward-Base Enhanced Features')
def exp_911(patients, detail=False):
    """Establish the corrected forward-looking baseline. Build 16-feature set
    using FORWARD-looking supply/demand sums (i:i+h_steps) instead of backward
    (i-h_steps:i). Expected base R²≈0.534.
    """
    h_steps = 12
    start = 24
    backward_r2s, forward_r2s = [], []
    per_patient = []

    for p in patients:
        d_back = _prepare_patient(p, h_steps, start)
        if d_back is None:
            continue
        d_fwd = _prepare_patient_forward(p, h_steps, start)
        if d_fwd is None:
            continue

        actual = d_back['actual']
        split = d_back['split']
        y_tr, y_val = actual[:split], actual[split:]

        # Backward baseline
        X_tr_b, X_val_b = d_back['features'][:split], d_back['features'][split:]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_b), axis=1)
        vm_val = np.isfinite(y_val) & np.all(np.isfinite(X_val_b), axis=1)
        if vm_tr.sum() < 50:
            continue
        pred_b, _ = _ridge_predict(
            np.nan_to_num(X_tr_b[vm_tr], nan=0.0), y_tr[vm_tr],
            np.nan_to_num(X_val_b[vm_val], nan=0.0))
        bk_r2 = _r2(pred_b, y_val[vm_val])
        backward_r2s.append(bk_r2)

        # Forward baseline
        X_tr_f, X_val_f = d_fwd['features'][:split], d_fwd['features'][split:]
        vm_tr_f = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_f), axis=1)
        vm_val_f = np.isfinite(y_val) & np.all(np.isfinite(X_val_f), axis=1)
        if vm_tr_f.sum() < 50:
            continue
        pred_f, _ = _ridge_predict(
            np.nan_to_num(X_tr_f[vm_tr_f], nan=0.0), y_tr[vm_tr_f],
            np.nan_to_num(X_val_f[vm_val_f], nan=0.0))
        fw_r2 = _r2(pred_f, y_val[vm_val_f])
        forward_r2s.append(fw_r2)

        if detail:
            per_patient.append({
                'patient': d_back['name'],
                'backward_r2': round(float(bk_r2), 3) if np.isfinite(bk_r2) else None,
                'forward_r2': round(float(fw_r2), 3) if np.isfinite(fw_r2) else None,
            })

    back = round(float(np.mean(backward_r2s)), 3) if backward_r2s else None
    fwd = round(float(np.mean(forward_r2s)), 3) if forward_r2s else None
    delta = round(fwd - back, 3) if fwd is not None and back is not None else None

    results = {
        'backward_base': back, 'forward_base': fwd, 'improvement': delta,
        'n_patients': len(forward_r2s),
    }
    if detail:
        results['per_patient'] = per_patient

    return {
        'experiment': 'EXP-911', 'name': 'Forward-Base Enhanced Features',
        'status': 'pass',
        'detail': (f'backward={back}, forward={fwd}, '
                   f'Δ={delta:+.3f}') if delta is not None else f'backward={back}',
        'results': results,
    }


# ── EXP-912: Forward-Base + PK Derivatives ───────────────────────────────────

@register('EXP-912', 'Forward-Base + PK Derivatives')
def exp_912(patients, detail=False):
    """Add PK derivative features to the forward-looking base: d_supply/dt,
    d_demand/dt, d2_supply/dt2, d2_demand/dt2, and d_net/dt.
    """
    h_steps = 12
    start = 24
    base_r2s, deriv_r2s = [], []

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
        base_r2s.append(_r2(pred_b, y_val[vm_val]))

        # Compute derivatives of supply and demand
        supply = fd['supply'][:n_pred].astype(float)
        demand = fd['demand'][:n_pred].astype(float)
        net = supply - demand

        d_supply = np.gradient(supply)
        d_demand = np.gradient(demand)
        d2_supply = np.gradient(d_supply)
        d2_demand = np.gradient(d_demand)
        d_net = np.gradient(net)

        deriv_feats = np.column_stack([
            d_supply[start:start + usable],
            d_demand[start:start + usable],
            d2_supply[start:start + usable],
            d2_demand[start:start + usable],
            d_net[start:start + usable],
        ])

        X_deriv = np.hstack([features, deriv_feats])
        X_tr_d, X_val_d = X_deriv[:split], X_deriv[split:]
        vm_tr_d = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_d), axis=1)
        vm_val_d = np.isfinite(y_val) & np.all(np.isfinite(X_val_d), axis=1)
        if vm_tr_d.sum() < 50:
            continue
        pred_d, _ = _ridge_predict(
            np.nan_to_num(X_tr_d[vm_tr_d], nan=0.0), y_tr[vm_tr_d],
            np.nan_to_num(X_val_d[vm_val_d], nan=0.0))
        deriv_r2s.append(_r2(pred_d, y_val[vm_val_d]))

    base = round(float(np.mean(base_r2s)), 3) if base_r2s else None
    deriv = round(float(np.mean(deriv_r2s)), 3) if deriv_r2s else None
    delta = round(deriv - base, 3) if deriv is not None and base is not None else None

    return {
        'experiment': 'EXP-912', 'name': 'Forward-Base + PK Derivatives',
        'status': 'pass',
        'detail': (f'forward_base={base}, +derivatives={deriv}, '
                   f'Δ={delta:+.3f}') if delta is not None else f'base={base}',
        'results': {
            'forward_base': base, 'with_derivatives': deriv,
            'improvement': delta, 'n_features_added': 5,
        },
    }


# ── EXP-913: Forward-Base + All Shape Features ──────────────────────────────

@register('EXP-913', 'Forward-Base + All Shape Features')
def exp_913(patients, detail=False):
    """Add post-prandial shape (time-since-last-large-supply, meal-phase-sin/cos,
    post-prandial-slope) and IOB shape (IOB sum, peak, time-since-peak,
    IOB derivative, IOB Gini) to forward-looking base.
    """
    h_steps = 12
    start = 24
    base_r2s, shape_r2s = [], []

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
        base_r2s.append(_r2(pred_b, y_val[vm_val]))

        # Post-prandial shape
        bg_sig = bg[:n_pred].astype(float)
        bg_sig[~np.isfinite(bg_sig)] = np.nanmean(bg_sig)
        supply = fd['supply'][:n_pred]
        demand = fd['demand'][:n_pred]

        pp_feats = _build_pp_features(bg_sig, supply, n_pred)
        iob_feats = _build_iob_features(demand, n_pred)

        shape_feats = np.hstack([
            pp_feats[start:start + usable],
            iob_feats[start:start + usable],
        ])
        X_shape = np.hstack([features, shape_feats])
        X_tr_s, X_val_s = X_shape[:split], X_shape[split:]
        vm_tr_s = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_s), axis=1)
        vm_val_s = np.isfinite(y_val) & np.all(np.isfinite(X_val_s), axis=1)
        if vm_tr_s.sum() < 50:
            continue
        pred_s, _ = _ridge_predict(
            np.nan_to_num(X_tr_s[vm_tr_s], nan=0.0), y_tr[vm_tr_s],
            np.nan_to_num(X_val_s[vm_val_s], nan=0.0))
        shape_r2s.append(_r2(pred_s, y_val[vm_val_s]))

    base = round(float(np.mean(base_r2s)), 3) if base_r2s else None
    shape = round(float(np.mean(shape_r2s)), 3) if shape_r2s else None
    delta = round(shape - base, 3) if shape is not None and base is not None else None

    return {
        'experiment': 'EXP-913', 'name': 'Forward-Base + All Shape Features',
        'status': 'pass',
        'detail': (f'forward_base={base}, +shape={shape}, '
                   f'Δ={delta:+.3f}') if delta is not None else f'base={base}',
        'results': {
            'forward_base': base, 'with_shape': shape,
            'improvement': delta, 'n_features_added': 10,
        },
    }


# ── EXP-914: Forward-Base + All Productive Features Combined ────────────────

@register('EXP-914', 'Forward + All Productive Features')
def exp_914(patients, detail=False):
    """Combine forward-looking sums + PK derivatives + shape features + causal
    EMA into a single feature set. Tests total additivity of all individually
    productive features. Strongest non-stacked result.
    """
    h_steps = 12
    start = 24
    base_r2s, combined_r2s = [], []
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

        bg_sig = bg[:n_pred].astype(float)
        bg_sig[~np.isfinite(bg_sig)] = np.nanmean(bg_sig)
        supply = fd['supply'][:n_pred].astype(float)
        demand = fd['demand'][:n_pred].astype(float)
        net = supply - demand

        # 1. PK derivatives
        d_supply = np.gradient(supply)
        d_demand = np.gradient(demand)
        d2_supply = np.gradient(d_supply)
        d2_demand = np.gradient(d_demand)
        d_net = np.gradient(net)

        # 2. Post-prandial + IOB shape
        pp_feats = _build_pp_features(bg_sig, supply, n_pred)
        iob_feats = _build_iob_features(demand, n_pred)

        # 3. Causal EMAs (EXP-882)
        ema_1h = _causal_ema(bg_sig, 2.0 / (12 + 1))
        ema_4h = _causal_ema(bg_sig, 2.0 / (48 + 1))

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
        ])

        X_combined = np.hstack([features, extra])
        X_tr_c, X_val_c = X_combined[:split], X_combined[split:]
        vm_tr_c = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_c), axis=1)
        vm_val_c = np.isfinite(y_val) & np.all(np.isfinite(X_val_c), axis=1)
        if vm_tr_c.sum() < 50:
            continue
        pred_c, _ = _ridge_predict(
            np.nan_to_num(X_tr_c[vm_tr_c], nan=0.0), y_tr[vm_tr_c],
            np.nan_to_num(X_val_c[vm_val_c], nan=0.0))
        c_r2 = _r2(pred_c, y_val[vm_val_c])
        combined_r2s.append(c_r2)

        if detail:
            per_patient.append({
                'patient': d_fwd['name'],
                'forward_base': round(float(b_r2), 3) if np.isfinite(b_r2) else None,
                'combined': round(float(c_r2), 3) if np.isfinite(c_r2) else None,
            })

    base = round(float(np.mean(base_r2s)), 3) if base_r2s else None
    comb = round(float(np.mean(combined_r2s)), 3) if combined_r2s else None
    delta = round(comb - base, 3) if comb is not None and base is not None else None

    results = {
        'forward_base': base, 'all_productive_combined': comb,
        'improvement': delta, 'n_patients': len(combined_r2s),
        'features_used': [
            'forward_supply_demand_16', 'pk_derivatives_5',
            'postprandial_shape_5', 'iob_shape_5', 'causal_ema_2',
        ],
        'total_features': 33,
    }
    if detail:
        results['per_patient'] = per_patient

    return {
        'experiment': 'EXP-914', 'name': 'Forward + All Productive Features',
        'status': 'pass',
        'detail': (f'forward_base={base}, combined={comb}, '
                   f'Δ={delta:+.3f}') if delta is not None else f'base={base}',
        'results': results,
    }


# ── EXP-915: Glucose Momentum Features ──────────────────────────────────────

@register('EXP-915', 'Glucose Momentum Features')
def exp_915(patients, detail=False):
    """Multi-scale rate of BG change: 5-min, 15-min, 30-min, 60-min, 120-min
    deltas. Added to forward-looking base. Multi-scale momentum captures
    different timescale dynamics.
    """
    h_steps = 12
    start = 24
    base_r2s, momentum_r2s = [], []
    delta_lags = [1, 3, 6, 12, 24]  # 5, 15, 30, 60, 120 min

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

        # Forward baseline
        X_tr, X_val = features[:split], features[split:]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        vm_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
        if vm_tr.sum() < 50:
            continue
        pred_b, _ = _ridge_predict(
            np.nan_to_num(X_tr[vm_tr], nan=0.0), y_tr[vm_tr],
            np.nan_to_num(X_val[vm_val], nan=0.0))
        base_r2s.append(_r2(pred_b, y_val[vm_val]))

        # Build momentum features
        bg_sig = bg.astype(float)
        mom_feats = np.zeros((usable, len(delta_lags)))
        for j, lag in enumerate(delta_lags):
            for i in range(usable):
                orig = i + start
                if orig >= lag and np.isfinite(bg_sig[orig]) and np.isfinite(bg_sig[orig - lag]):
                    mom_feats[i, j] = bg_sig[orig] - bg_sig[orig - lag]

        X_mom = np.hstack([features, mom_feats])
        X_tr_m, X_val_m = X_mom[:split], X_mom[split:]
        vm_tr_m = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_m), axis=1)
        vm_val_m = np.isfinite(y_val) & np.all(np.isfinite(X_val_m), axis=1)
        if vm_tr_m.sum() < 50:
            continue
        pred_m, _ = _ridge_predict(
            np.nan_to_num(X_tr_m[vm_tr_m], nan=0.0), y_tr[vm_tr_m],
            np.nan_to_num(X_val_m[vm_val_m], nan=0.0))
        momentum_r2s.append(_r2(pred_m, y_val[vm_val_m]))

    base = round(float(np.mean(base_r2s)), 3) if base_r2s else None
    mom = round(float(np.mean(momentum_r2s)), 3) if momentum_r2s else None
    delta = round(mom - base, 3) if mom is not None and base is not None else None

    return {
        'experiment': 'EXP-915', 'name': 'Glucose Momentum Features',
        'status': 'pass',
        'detail': (f'forward_base={base}, +momentum={mom}, '
                   f'Δ={delta:+.3f}') if delta is not None else f'base={base}',
        'results': {
            'forward_base': base, 'with_momentum': mom,
            'improvement': delta, 'n_features_added': len(delta_lags),
            'delta_minutes': [lag * 5 for lag in delta_lags],
        },
    }


# ── EXP-916: Basal vs Bolus Insulin Decomposition ───────────────────────────

@register('EXP-916', 'Basal vs Bolus Decomposition')
def exp_916(patients, detail=False):
    """Separate insulin activity into basal and bolus channels. If insulin dose
    > 2x median recent rate, classify as bolus; otherwise basal. Features:
    bolus_activity, basal_activity, bolus_fraction.
    """
    h_steps = 12
    start = 24
    base_r2s, decomp_r2s = [], []

    for p in patients:
        d_fwd = _prepare_patient_forward(p, h_steps, start)
        if d_fwd is None:
            continue
        fd = d_fwd['fd']
        actual = d_fwd['actual']
        features = d_fwd['features']
        split = d_fwd['split']
        usable = d_fwd['usable']
        n_pred = d_fwd['n_pred']
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
        base_r2s.append(_r2(pred_b, y_val[vm_val]))

        # Decompose demand into basal/bolus
        demand = fd['demand'][:n_pred].astype(float)
        decomp_feats = np.zeros((usable, 3))

        for i in range(usable):
            orig = i + start
            # Rolling median of demand over past 2 hours (24 steps)
            window = demand[max(0, orig - 24):orig]
            if len(window) < 6:
                med_rate = np.median(demand[:orig + 1]) if orig > 0 else 0.01
            else:
                med_rate = np.median(window)
            med_rate = max(med_rate, 1e-6)

            # Forward window for insulin activity decomposition
            fwd_win = demand[orig:min(orig + h_steps, n_pred)]
            if len(fwd_win) == 0:
                continue
            bolus_mask = fwd_win > 2.0 * med_rate
            basal_mask = ~bolus_mask

            decomp_feats[i, 0] = np.sum(fwd_win[bolus_mask])  # bolus_activity
            decomp_feats[i, 1] = np.sum(fwd_win[basal_mask])  # basal_activity
            total = decomp_feats[i, 0] + decomp_feats[i, 1]
            if total > 1e-6:
                decomp_feats[i, 2] = decomp_feats[i, 0] / total  # bolus_fraction

        X_dec = np.hstack([features, decomp_feats])
        X_tr_d, X_val_d = X_dec[:split], X_dec[split:]
        vm_tr_d = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_d), axis=1)
        vm_val_d = np.isfinite(y_val) & np.all(np.isfinite(X_val_d), axis=1)
        if vm_tr_d.sum() < 50:
            continue
        pred_d, _ = _ridge_predict(
            np.nan_to_num(X_tr_d[vm_tr_d], nan=0.0), y_tr[vm_tr_d],
            np.nan_to_num(X_val_d[vm_val_d], nan=0.0))
        decomp_r2s.append(_r2(pred_d, y_val[vm_val_d]))

    base = round(float(np.mean(base_r2s)), 3) if base_r2s else None
    dec = round(float(np.mean(decomp_r2s)), 3) if decomp_r2s else None
    delta = round(dec - base, 3) if dec is not None and base is not None else None

    return {
        'experiment': 'EXP-916', 'name': 'Basal vs Bolus Decomposition',
        'status': 'pass',
        'detail': (f'forward_base={base}, +basal_bolus={dec}, '
                   f'Δ={delta:+.3f}') if delta is not None else f'base={base}',
        'results': {
            'forward_base': base, 'with_basal_bolus': dec,
            'improvement': delta, 'n_features_added': 3,
        },
    }


# ── EXP-917: Carb-Free Interval Analysis ────────────────────────────────────

@register('EXP-917', 'Carb-Free Interval Analysis')
def exp_917(patients, detail=False):
    """Compute time-since-last-carbs and exponential recency decay as features.
    Diagnostic: report R² by carb-free-interval bucket (0-1h, 1-3h, 3-6h, 6+h).
    """
    h_steps = 12
    start = 24
    base_r2s, carb_r2s = [], []
    bucket_errors = {'0-1h': [], '1-3h': [], '3-6h': [], '6h+': []}

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
        base_r2s.append(_r2(pred_b, y_val[vm_val]))

        # Compute time-since-last-carbs
        supply = fd['supply'][:n_pred].astype(float)
        carb_supply = fd.get('carb_supply', supply)
        if isinstance(carb_supply, (list, np.ndarray)):
            carb_supply = np.asarray(carb_supply[:n_pred], dtype=float)
        else:
            carb_supply = supply.copy()

        carb_thresh = np.percentile(carb_supply[carb_supply > 0], 50) if np.sum(carb_supply > 0) > 10 else 0.05

        carb_feats = np.zeros((usable, 2))
        last_carb_step = -999
        for i in range(n_pred):
            if carb_supply[i] > carb_thresh:
                last_carb_step = i
            if i >= start and (i - start) < usable:
                idx = i - start
                hours_since = (i - last_carb_step) * 5.0 / 60.0
                carb_feats[idx, 0] = min(hours_since, 12.0)
                carb_feats[idx, 1] = np.exp(-hours_since / 2.0)  # decay τ=2h

        X_carb = np.hstack([features, carb_feats])
        X_tr_c, X_val_c = X_carb[:split], X_carb[split:]
        vm_tr_c = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_c), axis=1)
        vm_val_c = np.isfinite(y_val) & np.all(np.isfinite(X_val_c), axis=1)
        if vm_tr_c.sum() < 50:
            continue
        pred_c, _ = _ridge_predict(
            np.nan_to_num(X_tr_c[vm_tr_c], nan=0.0), y_tr[vm_tr_c],
            np.nan_to_num(X_val_c[vm_val_c], nan=0.0))
        carb_r2s.append(_r2(pred_c, y_val[vm_val_c]))

        # Diagnostic: errors by carb-free-interval bucket
        val_errors = np.abs(y_val[vm_val] - pred_b)
        val_carb_hours = carb_feats[split:][vm_val, 0]
        for j in range(len(val_errors)):
            h = val_carb_hours[j] if j < len(val_carb_hours) else 12.0
            err = float(val_errors[j])
            if h < 1.0:
                bucket_errors['0-1h'].append(err)
            elif h < 3.0:
                bucket_errors['1-3h'].append(err)
            elif h < 6.0:
                bucket_errors['3-6h'].append(err)
            else:
                bucket_errors['6h+'].append(err)

    base = round(float(np.mean(base_r2s)), 3) if base_r2s else None
    carb = round(float(np.mean(carb_r2s)), 3) if carb_r2s else None
    delta = round(carb - base, 3) if carb is not None and base is not None else None

    bucket_mae = {k: round(float(np.mean(v)), 1) if v else None
                  for k, v in bucket_errors.items()}

    return {
        'experiment': 'EXP-917', 'name': 'Carb-Free Interval Analysis',
        'status': 'pass',
        'detail': (f'forward_base={base}, +carb_interval={carb}, Δ={delta:+.3f}, '
                   f'MAE_by_bucket={bucket_mae}') if delta is not None else f'base={base}',
        'results': {
            'forward_base': base, 'with_carb_interval': carb,
            'improvement': delta,
            'mae_by_carb_free_bucket': bucket_mae,
            'n_features_added': 2,
        },
    }


# ── EXP-918: Per-Patient Oracle Ceiling ──────────────────────────────────────

@register('EXP-918', 'Per-Patient Oracle Ceiling')
def exp_918(patients, detail=False):
    """For each patient, compute individual oracle ceiling: ridge trained on
    ACTUAL future BG as feature. Reveals per-patient potential and identifies
    who has room to improve.
    """
    h_steps = 12
    start = 24
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

        # Current model R²
        X_tr, X_val = features[:split], features[split:]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        vm_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
        if vm_tr.sum() < 50:
            continue
        pred_m, _ = _ridge_predict(
            np.nan_to_num(X_tr[vm_tr], nan=0.0), y_tr[vm_tr],
            np.nan_to_num(X_val[vm_val], nan=0.0))
        model_r2 = _r2(pred_m, y_val[vm_val])

        # Oracle: use actual future BG as a feature (cheating, but gives ceiling)
        oracle_feat = actual.reshape(-1, 1)
        X_oracle = np.hstack([features, oracle_feat])
        X_tr_o, X_val_o = X_oracle[:split], X_oracle[split:]
        vm_tr_o = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_o), axis=1)
        vm_val_o = np.isfinite(y_val) & np.all(np.isfinite(X_val_o), axis=1)
        if vm_tr_o.sum() < 50:
            continue
        pred_o, _ = _ridge_predict(
            np.nan_to_num(X_tr_o[vm_tr_o], nan=0.0), y_tr[vm_tr_o],
            np.nan_to_num(X_val_o[vm_val_o], nan=0.0))
        oracle_r2 = _r2(pred_o, y_val[vm_val_o])

        if np.isfinite(model_r2) and np.isfinite(oracle_r2):
            gap = oracle_r2 - model_r2
            per_patient.append({
                'patient': d_fwd['name'],
                'model_r2': round(float(model_r2), 3),
                'oracle_r2': round(float(oracle_r2), 3),
                'gap': round(float(gap), 3),
                'pct_of_oracle_achieved': round(
                    float(model_r2 / oracle_r2 * 100) if oracle_r2 > 0.01 else 0.0, 1),
            })

    if not per_patient:
        return {
            'experiment': 'EXP-918', 'name': 'Per-Patient Oracle Ceiling',
            'status': 'pass', 'detail': 'insufficient patients',
            'results': {'per_patient': []},
        }

    per_patient.sort(key=lambda x: x['gap'], reverse=True)
    model_r2s = [p['model_r2'] for p in per_patient]
    oracle_r2s = [p['oracle_r2'] for p in per_patient]
    gaps = [p['gap'] for p in per_patient]

    mean_model = round(float(np.mean(model_r2s)), 3)
    mean_oracle = round(float(np.mean(oracle_r2s)), 3)
    mean_gap = round(float(np.mean(gaps)), 3)
    most_room = per_patient[0]
    least_room = per_patient[-1]

    return {
        'experiment': 'EXP-918', 'name': 'Per-Patient Oracle Ceiling',
        'status': 'pass',
        'detail': (f'mean_model={mean_model}, mean_oracle={mean_oracle}, '
                   f'mean_gap={mean_gap}, most_room={most_room["patient"]}('
                   f'gap={most_room["gap"]}), least_room={least_room["patient"]}('
                   f'gap={least_room["gap"]})'),
        'results': {
            'mean_model_r2': mean_model, 'mean_oracle_r2': mean_oracle,
            'mean_gap': mean_gap,
            'most_room_patient': most_room,
            'least_room_patient': least_room,
            'per_patient': per_patient,
            'n_patients': len(per_patient),
        },
    }


# ── EXP-919: Forward-Base CV Stacking with Best Features (KEY) ──────────────

@register('EXP-919', 'Forward CV Stacking SOTA')
def exp_919(patients, detail=False):
    """KEY experiment: 5-fold CV stacking using forward-looking base (R²≈0.534)
    + PK derivatives + shape features + causal EMA + multi-horizon predictions
    at 3/5/7 horizons. Each fold trains ridge on enhanced forward features,
    generates OOF predictions at each horizon, then meta-ridge combines them.
    This should set the new absolute SOTA.
    """
    h_steps = 12
    start = 24
    horizons = [6, 10, 14]  # 30, 50, 70 min
    n_folds = 5
    backward_r2s, forward_r2s, grand_r2s = [], [], []
    per_patient = []

    for p in patients:
        # Backward baseline for comparison
        d_back = _prepare_patient(p, h_steps, start)
        if d_back is None:
            continue
        d_fwd = _prepare_patient_forward(p, h_steps, start)
        if d_fwd is None:
            continue

        fd = d_back['fd']
        bg = d_back['bg']
        actual = d_back['actual']
        split = d_back['split']
        usable = d_back['usable']
        n_pred = d_back['n_pred']
        nr = d_back['nr']
        hours = d_back['hours']
        y_tr, y_val = actual[:split], actual[split:]

        # Backward baseline R²
        X_tr_bk, X_val_bk = d_back['features'][:split], d_back['features'][split:]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_bk), axis=1)
        vm_val = np.isfinite(y_val) & np.all(np.isfinite(X_val_bk), axis=1)
        if vm_tr.sum() < 50:
            continue
        pred_bk, _ = _ridge_predict(
            np.nan_to_num(X_tr_bk[vm_tr], nan=0.0), y_tr[vm_tr],
            np.nan_to_num(X_val_bk[vm_val], nan=0.0))
        bk_r2 = _r2(pred_bk, y_val[vm_val])
        backward_r2s.append(bk_r2)

        # Forward baseline R²
        X_tr_fw, X_val_fw = d_fwd['features'][:split], d_fwd['features'][split:]
        vm_tr_f = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_fw), axis=1)
        vm_val_f = np.isfinite(y_val) & np.all(np.isfinite(X_val_fw), axis=1)
        if vm_tr_f.sum() < 50:
            continue
        pred_fw, _ = _ridge_predict(
            np.nan_to_num(X_tr_fw[vm_tr_f], nan=0.0), y_tr[vm_tr_f],
            np.nan_to_num(X_val_fw[vm_val_f], nan=0.0))
        fw_r2 = _r2(pred_fw, y_val[vm_val_f])
        forward_r2s.append(fw_r2)

        # === Build ALL productive features on forward base ===
        bg_sig = bg[:n_pred].astype(float)
        bg_sig[~np.isfinite(bg_sig)] = np.nanmean(bg_sig)
        supply = fd['supply'][:n_pred].astype(float)
        demand = fd['demand'][:n_pred].astype(float)
        net = supply - demand
        n_supply = len(fd['supply'])

        # 1. Causal EMAs (EXP-882)
        ema_1h = _causal_ema(bg_sig, 2.0 / (12 + 1))
        ema_4h = _causal_ema(bg_sig, 2.0 / (48 + 1))

        # 2. Post-prandial shape (EXP-893)
        pp_feats = _build_pp_features(bg_sig, supply, n_pred)

        # 3. IOB shape (EXP-898)
        iob_feats = _build_iob_features(demand, n_pred)

        # 4. PK derivatives (EXP-901)
        d_supply = np.gradient(supply)
        d_demand = np.gradient(demand)
        d2_supply = np.gradient(d_supply)
        d2_demand = np.gradient(d_demand)
        d_net = np.gradient(net)

        # 5. Glucose momentum (EXP-915)
        mom_feats = np.zeros((n_pred, 5))
        for lag_j, lag in enumerate([1, 3, 6, 12, 24]):
            for i in range(lag, n_pred):
                if np.isfinite(bg_sig[i]) and np.isfinite(bg_sig[i - lag]):
                    mom_feats[i, lag_j] = bg_sig[i] - bg_sig[i - lag]

        # Assemble extra features (sliced to usable range)
        extra = np.column_stack([
            ema_1h[start:start + usable],
            ema_4h[start:start + usable],
            pp_feats[start:start + usable],
            iob_feats[start:start + usable],
            d_supply[start:start + usable],
            d_demand[start:start + usable],
            d2_supply[start:start + usable],
            d2_demand[start:start + usable],
            d_net[start:start + usable],
            mom_feats[start:start + usable],
        ])

        # 6. Multi-horizon predictions
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
            continue

        stack = np.column_stack([h_preds[h] for h in sorted(h_preds)])
        pred_std = np.std(stack, axis=1, keepdims=True)

        # Combine: forward features + extra + horizon stack + disagreement
        X_grand = np.hstack([d_fwd['features'], extra, stack, pred_std])

        X_tr_g = X_grand[:split]
        X_val_g = X_grand[split:]
        vm_tr_g = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_g), axis=1)
        vm_val_g = np.isfinite(y_val) & np.all(np.isfinite(X_val_g), axis=1)

        if vm_tr_g.sum() < 100:
            # Fallback: try with lower threshold
            if vm_tr_g.sum() < 50:
                continue

        # === 5-fold CV stacking ===
        n_valid_tr = int(vm_tr_g.sum())
        fold_size = n_valid_tr // n_folds
        if fold_size < 20:
            # Not enough data for CV stacking, use direct prediction
            pred_g, _ = _ridge_predict(
                np.nan_to_num(X_tr_g[vm_tr_g], nan=0.0), y_tr[vm_tr_g],
                np.nan_to_num(X_val_g[vm_val_g], nan=0.0), lam=10.0)
            g_r2 = _r2(pred_g, y_val[vm_val_g])
            if np.isfinite(g_r2):
                grand_r2s.append(g_r2)
                per_patient.append({
                    'patient': d_back['name'],
                    'backward_base': round(float(bk_r2), 3),
                    'forward_base': round(float(fw_r2), 3),
                    'grand': round(float(g_r2), 3),
                    'delta_vs_backward': round(float(g_r2 - bk_r2), 3),
                    'method': 'direct',
                })
            continue

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

        # Meta-features: OOF predictions column
        oof_col = oof_predictions[:split].reshape(-1, 1)
        X_meta_tr = np.hstack([X_tr_g, oof_col])

        # For validation: train on ALL training data, predict val, use as meta
        pred_full_train, w_full = _ridge_predict(
            np.nan_to_num(X_tr_g[vm_tr_g], nan=0.0), y_tr[vm_tr_g],
            np.nan_to_num(X_val_g, nan=0.0), lam=10.0)

        # Build val meta features
        X_meta_val = np.hstack([X_val_g, pred_full_train.reshape(-1, 1)])

        vm_meta_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_meta_tr), axis=1)
        vm_meta_val = np.isfinite(y_val) & np.all(np.isfinite(X_meta_val), axis=1)

        if vm_meta_tr.sum() < 50:
            # Fallback: use grand features directly
            pred_g, _ = _ridge_predict(
                np.nan_to_num(X_tr_g[vm_tr_g], nan=0.0), y_tr[vm_tr_g],
                np.nan_to_num(X_val_g[vm_val_g], nan=0.0), lam=10.0)
            g_r2 = _r2(pred_g, y_val[vm_val_g])
        else:
            X_meta_tr_clean = np.nan_to_num(X_meta_tr[vm_meta_tr], nan=0.0)
            X_meta_val_clean = np.nan_to_num(X_meta_val[vm_meta_val], nan=0.0)
            pred_meta, _ = _ridge_predict(
                X_meta_tr_clean, y_tr[vm_meta_tr],
                X_meta_val_clean, lam=10.0)
            g_r2 = _r2(pred_meta, y_val[vm_meta_val])

        if np.isfinite(g_r2):
            grand_r2s.append(g_r2)
            per_patient.append({
                'patient': d_back['name'],
                'backward_base': round(float(bk_r2), 3),
                'forward_base': round(float(fw_r2), 3),
                'grand': round(float(g_r2), 3),
                'delta_vs_backward': round(float(g_r2 - bk_r2), 3),
                'method': 'cv_stacking',
            })

    back = round(float(np.mean(backward_r2s)), 3) if backward_r2s else None
    fwd = round(float(np.mean(forward_r2s)), 3) if forward_r2s else None
    grand = round(float(np.mean(grand_r2s)), 3) if grand_r2s else None
    delta_vs_back = round(grand - back, 3) if grand is not None and back is not None else None
    delta_vs_fwd = round(grand - fwd, 3) if grand is not None and fwd is not None else None

    results = {
        'backward_base': back, 'forward_base': fwd,
        'grand_cv_stacking': grand,
        'delta_vs_backward': delta_vs_back,
        'delta_vs_forward': delta_vs_fwd,
        'per_patient': per_patient,
        'n_patients': len(grand_r2s),
        'features_used': [
            'forward_supply_demand_16', 'causal_ema_2',
            'postprandial_shape_5', 'iob_shape_5',
            'pk_derivatives_5', 'glucose_momentum_5',
            'multi_horizon_stack_3', 'prediction_disagreement_1',
            'cv_stacking_meta_1',
        ],
        'horizons_min': [h * 5 for h in horizons],
        'n_folds': n_folds,
    }

    return {
        'experiment': 'EXP-919', 'name': 'Forward CV Stacking SOTA',
        'status': 'pass',
        'detail': (f'backward_base={back}, forward_base={fwd}, '
                   f'grand_cv_stack={grand}, '
                   f'Δ_vs_back={delta_vs_back:+.3f}, '
                   f'Δ_vs_fwd={delta_vs_fwd:+.3f}') if delta_vs_back is not None else f'base={back}',
        'results': results,
    }


# ── EXP-920: Error Budget Analysis ──────────────────────────────────────────

@register('EXP-920', 'Error Budget Analysis')
def exp_920(patients, detail=False):
    """Decompose remaining error from the best model into:
    - Systematic bias (mean residual by patient, time-of-day, meal proximity)
    - Random noise (residual after removing systematic components)
    - Theoretical reducibility estimate
    Uses the best available model (forward + all features).
    """
    h_steps = 12
    start = 24
    decomp = {
        'patient_bias': [], 'tod_bias': [], 'meal_proximity_bias': [],
        'random_noise': [], 'total_var': [],
    }
    reducibility = []

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

        bg_sig = bg[:n_pred].astype(float)
        bg_sig[~np.isfinite(bg_sig)] = np.nanmean(bg_sig)
        supply = fd['supply'][:n_pred].astype(float)
        demand = fd['demand'][:n_pred].astype(float)
        net = supply - demand

        # Build full feature set (same as EXP-914)
        d_supply = np.gradient(supply)
        d_demand = np.gradient(demand)
        d2_supply = np.gradient(d_supply)
        d2_demand = np.gradient(d_demand)
        d_net = np.gradient(net)
        pp_feats = _build_pp_features(bg_sig, supply, n_pred)
        iob_feats = _build_iob_features(demand, n_pred)
        ema_1h = _causal_ema(bg_sig, 2.0 / (12 + 1))
        ema_4h = _causal_ema(bg_sig, 2.0 / (48 + 1))

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
        ])

        X_full = np.hstack([features, extra])
        X_tr_f, X_val_f = X_full[:split], X_full[split:]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_f), axis=1)
        vm_val = np.isfinite(y_val) & np.all(np.isfinite(X_val_f), axis=1)
        if vm_tr.sum() < 50 or vm_val.sum() < 20:
            continue

        pred, _ = _ridge_predict(
            np.nan_to_num(X_tr_f[vm_tr], nan=0.0), y_tr[vm_tr],
            np.nan_to_num(X_val_f[vm_val], nan=0.0))
        residuals = y_val[vm_val] - pred
        total_var = float(np.var(residuals))
        if total_var < 1e-6:
            continue

        # 1. Patient-level systematic bias: mean residual
        patient_bias = float(np.mean(residuals) ** 2)

        # 2. Time-of-day systematic bias
        tod_var = 0.0
        val_start = start + split
        val_indices = np.where(vm_val)[0]
        if hours is not None:
            val_hours = []
            for idx_i in val_indices:
                orig = val_start + idx_i
                if orig < len(hours):
                    val_hours.append(int(hours[orig]) % 24)
                else:
                    val_hours.append(0)
            val_hours = np.array(val_hours)
            hour_means = np.zeros(24)
            for hr in range(24):
                mask_hr = val_hours == hr
                if mask_hr.sum() > 5:
                    hour_means[hr] = np.mean(residuals[mask_hr])
            tod_systematic = np.array([hour_means[h] for h in val_hours])
            tod_var = float(np.var(tod_systematic))

        # 3. Meal proximity systematic bias
        meal_prox_var = 0.0
        carb_supply = supply.copy()
        carb_thresh = np.percentile(carb_supply[carb_supply > 0], 50) if np.sum(carb_supply > 0) > 10 else 0.05
        near_meal_resid, far_meal_resid = [], []
        last_carb = -999
        for orig_i in range(n_pred):
            if carb_supply[orig_i] > carb_thresh:
                last_carb = orig_i
        # Recompute with tracking
        last_carb = -999
        for j, idx_i in enumerate(val_indices):
            orig = val_start + idx_i
            # Update last_carb up to orig
            for k in range(max(0, orig - 36), orig + 1):
                if k < n_pred and carb_supply[k] > carb_thresh:
                    last_carb = k
            hours_since = (orig - last_carb) * 5.0 / 60.0 if last_carb >= 0 else 12.0
            if hours_since < 2.0:
                near_meal_resid.append(float(residuals[j]))
            else:
                far_meal_resid.append(float(residuals[j]))

        if len(near_meal_resid) > 10 and len(far_meal_resid) > 10:
            meal_prox_var = max(0.0, np.var(near_meal_resid) - np.var(far_meal_resid))
            meal_prox_var = min(meal_prox_var, total_var * 0.5)

        # 4. Random noise (remainder)
        systematic_var = patient_bias + tod_var + meal_prox_var
        random_var = max(0.0, total_var - systematic_var)

        decomp['patient_bias'].append(patient_bias / total_var * 100)
        decomp['tod_bias'].append(tod_var / total_var * 100)
        decomp['meal_proximity_bias'].append(meal_prox_var / total_var * 100)
        decomp['random_noise'].append(random_var / total_var * 100)
        decomp['total_var'].append(total_var)

        # Reducibility estimate: systematic is theoretically reducible
        pct_reducible = (patient_bias + tod_var + meal_prox_var) / total_var * 100
        reducibility.append(min(pct_reducible, 100.0))

    means = {k: round(float(np.mean(v)), 1) if v else None for k, v in decomp.items()}
    mean_reducible = round(float(np.mean(reducibility)), 1) if reducibility else None
    mean_irreducible = round(100.0 - mean_reducible, 1) if mean_reducible is not None else None

    # Compute sensor noise floor estimate (high-freq BG variation)
    sensor_noise_pct = []
    for p in patients:
        d_fwd = _prepare_patient_forward(p, h_steps, start)
        if d_fwd is None:
            continue
        bg_all = d_fwd['bg'].astype(float)
        bg_valid = bg_all[np.isfinite(bg_all)]
        if len(bg_valid) < 100:
            continue
        # 3-point rolling noise
        noise_stds = []
        for i in range(2, len(bg_valid)):
            w3 = bg_valid[i - 2:i + 1]
            noise_stds.append(np.std(w3))
        if noise_stds:
            bg_var = np.var(bg_valid)
            if bg_var > 1e-6:
                sensor_noise_pct.append(float(np.mean(noise_stds) ** 2 / bg_var * 100))

    sensor_noise = round(float(np.mean(sensor_noise_pct)), 1) if sensor_noise_pct else None

    return {
        'experiment': 'EXP-920', 'name': 'Error Budget Analysis',
        'status': 'pass',
        'detail': (f'patient_bias={means["patient_bias"]}%, '
                   f'tod={means["tod_bias"]}%, '
                   f'meal_prox={means["meal_proximity_bias"]}%, '
                   f'random={means["random_noise"]}%, '
                   f'reducible={mean_reducible}%, '
                   f'sensor_noise≈{sensor_noise}%'),
        'results': {
            'pct_patient_bias': means['patient_bias'],
            'pct_tod_bias': means['tod_bias'],
            'pct_meal_proximity_bias': means['meal_proximity_bias'],
            'pct_random_noise': means['random_noise'],
            'mean_total_var': means['total_var'],
            'pct_theoretically_reducible': mean_reducible,
            'pct_irreducible': mean_irreducible,
            'sensor_noise_pct_of_bg_var': sensor_noise,
            'n_patients': len(decomp['total_var']),
        },
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
        description='EXP-911–920: Forward-Base Feature Engineering & Grand CV Stacking')
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
