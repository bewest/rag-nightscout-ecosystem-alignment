#!/usr/bin/env python3
"""EXP-901–910: Physics-Based Metabolic Flux Features & Grand Benchmark

Building on 80+ experiments that established the prediction frontier, this wave
focuses on extracting MORE from known physics (PK derivatives, curve shapes),
quantifying irreducible error sources, and combining ALL validated improvements
into a definitive benchmark.

Key themes:
1. Derivative features from PK/PD curves (rate-of-change of metabolic flux)
2. Uncertainty quantification (meal uncertainty, conformal prediction)
3. Forward-looking features + shape combination (THE KEY experiment)
4. Residual variance decomposition (what's fundamentally unpredictable?)
5. Grand benchmark combining ALL productive features with CV stacking

EXP-901: PK Derivative Features (d/dt of supply & demand)
EXP-902: Meal Uncertainty Quantification (diagnostic)
EXP-903: Forward-Looking + Shape Features Combined
EXP-904: Residual Variance Decomposition (diagnostic)
EXP-905: Multi-Horizon Shape Ensemble
EXP-906: Patient Difficulty Predictor (diagnostic)
EXP-907: Conformal Prediction Bands
EXP-908: Asymmetric Loss (Linex via IRLS)
EXP-909: Phase-Conditioned Prediction
EXP-910: Grand Benchmark with CV Stacking
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


# ── EXP-901: PK Derivative Features ─────────────────────────────────────────

@register('EXP-901', 'PK Derivative Features')
def exp_901(patients, detail=False):
    """Build first and second derivatives of insulin and carb activity curves.
    Uses np.gradient() on supply and demand arrays. Captures rate-of-change
    of metabolic flux which determines future BG trajectory.
    """
    h_steps = 12
    start = 24
    base_r2s, deriv_r2s = [], []

    for p in patients:
        d = _prepare_patient(p, h_steps, start)
        if d is None:
            continue
        bg, fd, actual, features, split, usable = (
            d['bg'], d['fd'], d['actual'], d['features'], d['split'], d['usable'])
        y_tr, y_val = actual[:split], actual[split:]
        n_pred = d['n_pred']

        X_tr, X_val = features[:split], features[split:]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        vm_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
        if vm_tr.sum() < 50:
            continue
        X_tr_clean = np.nan_to_num(X_tr[vm_tr], nan=0.0)
        pred_b, _ = _ridge_predict(X_tr_clean, y_tr[vm_tr], np.nan_to_num(X_val[vm_val], nan=0.0))
        base_r2s.append(_r2(pred_b, y_val[vm_val]))

        # Compute derivatives of supply and demand
        supply = fd['supply'][:n_pred].astype(float)
        demand = fd['demand'][:n_pred].astype(float)

        d_supply = np.gradient(supply)
        d_demand = np.gradient(demand)
        d2_supply = np.gradient(d_supply)
        d2_demand = np.gradient(d_demand)

        deriv_feats = np.column_stack([
            d_supply[start:start + usable],
            d_demand[start:start + usable],
            d2_supply[start:start + usable],
            d2_demand[start:start + usable],
        ])

        X_deriv = np.hstack([features, deriv_feats])
        X_tr_d, X_val_d = X_deriv[:split], X_deriv[split:]
        vm_tr_d = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_d), axis=1)
        vm_val_d = np.isfinite(y_val) & np.all(np.isfinite(X_val_d), axis=1)
        if vm_tr_d.sum() < 50:
            continue
        X_tr_d_clean = np.nan_to_num(X_tr_d[vm_tr_d], nan=0.0)
        X_val_d_clean = np.nan_to_num(X_val_d[vm_val_d], nan=0.0)
        pred_d, _ = _ridge_predict(X_tr_d_clean, y_tr[vm_tr_d], X_val_d_clean)
        deriv_r2s.append(_r2(pred_d, y_val[vm_val_d]))

    base = round(float(np.mean(base_r2s)), 3) if base_r2s else None
    deriv = round(float(np.mean(deriv_r2s)), 3) if deriv_r2s else None
    delta = round(deriv - base, 3) if deriv and base else None

    return {
        'experiment': 'EXP-901', 'name': 'PK Derivative Features',
        'status': 'pass',
        'detail': f'base={base}, +derivatives={deriv}, Δ={delta:+.3f}' if delta else f'base={base}',
        'results': {'base': base, 'with_derivatives': deriv, 'improvement': delta},
    }


# ── EXP-902: Meal Uncertainty Quantification ─────────────────────────────────

@register('EXP-902', 'Meal Uncertainty Quantification')
def exp_902(patients, detail=False):
    """Diagnostic: compute local meal uncertainty as rolling std of glucose
    changes during detected meal periods vs basal. Compare model error in
    high-uncertainty vs low-uncertainty regimes.
    """
    h_steps = 12
    start = 24
    all_meal_err, all_basal_err = [], []
    all_hi_unc_err, all_lo_unc_err = [], []

    for p in patients:
        d = _prepare_patient(p, h_steps, start)
        if d is None:
            continue
        bg, fd, actual, features, split, usable = (
            d['bg'], d['fd'], d['actual'], d['features'], d['split'], d['usable'])
        y_tr, y_val = actual[:split], actual[split:]
        n_pred = d['n_pred']

        X_tr, X_val = features[:split], features[split:]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        vm_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
        if vm_tr.sum() < 50:
            continue
        X_tr_clean = np.nan_to_num(X_tr[vm_tr], nan=0.0)
        pred_v, _ = _ridge_predict(X_tr_clean, y_tr[vm_tr], np.nan_to_num(X_val[vm_val], nan=0.0))
        errors = np.abs(y_val[vm_val] - pred_v)

        # Classify val timesteps: meal period vs basal
        supply = fd['supply'][:n_pred]
        bg_sig = bg[:n_pred].astype(float)
        val_start = start + split

        # Rolling std of BG changes (uncertainty proxy)
        bg_diff = np.diff(bg_sig)
        roll_std = np.zeros(n_pred)
        for i in range(12, n_pred - 1):
            w = bg_diff[max(0, i - 12):i]
            v = w[np.isfinite(w)]
            if len(v) >= 3:
                roll_std[i] = np.std(v)

        # Median split for high/low uncertainty
        val_roll_std = []
        val_indices = np.where(vm_val)[0]
        for idx_i in val_indices:
            orig = val_start + idx_i
            if orig < n_pred:
                val_roll_std.append(roll_std[orig])
            else:
                val_roll_std.append(0.0)
        val_roll_std = np.array(val_roll_std)

        meal_errs, basal_errs = [], []
        for idx_i, err in zip(val_indices, errors):
            orig = val_start + idx_i
            if orig >= n_pred:
                continue
            s_act = np.sum(supply[max(0, orig - 24):orig]) > 0.5
            if s_act:
                meal_errs.append(float(err))
            else:
                basal_errs.append(float(err))

        if meal_errs:
            all_meal_err.append(np.mean(meal_errs))
        if basal_errs:
            all_basal_err.append(np.mean(basal_errs))

        if len(val_roll_std) > 10:
            median_unc = np.median(val_roll_std)
            hi_mask = val_roll_std > median_unc
            lo_mask = ~hi_mask
            if hi_mask.sum() > 5:
                all_hi_unc_err.append(float(np.mean(errors[hi_mask])))
            if lo_mask.sum() > 5:
                all_lo_unc_err.append(float(np.mean(errors[lo_mask])))

    meal_mae = round(float(np.mean(all_meal_err)), 1) if all_meal_err else None
    basal_mae = round(float(np.mean(all_basal_err)), 1) if all_basal_err else None
    hi_unc_mae = round(float(np.mean(all_hi_unc_err)), 1) if all_hi_unc_err else None
    lo_unc_mae = round(float(np.mean(all_lo_unc_err)), 1) if all_lo_unc_err else None
    ratio = round(hi_unc_mae / lo_unc_mae, 2) if hi_unc_mae and lo_unc_mae and lo_unc_mae > 0 else None

    return {
        'experiment': 'EXP-902', 'name': 'Meal Uncertainty Quantification',
        'status': 'pass',
        'detail': (f'MAE: meal={meal_mae}, basal={basal_mae}, '
                   f'hi_unc={hi_unc_mae}, lo_unc={lo_unc_mae}, ratio={ratio}'),
        'results': {
            'meal_mae': meal_mae, 'basal_mae': basal_mae,
            'hi_uncertainty_mae': hi_unc_mae, 'lo_uncertainty_mae': lo_unc_mae,
            'hi_lo_ratio': ratio,
        },
    }


# ── EXP-903: Forward-Looking + Shape Features Combined ──────────────────────

@register('EXP-903', 'Forward-Looking + Shape Combined')
def exp_903(patients, detail=False):
    """THE KEY experiment. Use forward-looking supply/demand sums (base=0.534)
    then add post-prandial shape (EXP-893) and IOB shape (EXP-898) features.
    Tests if improvements are additive, potentially reaching R²≈0.555+.
    """
    h_steps = 12
    start = 24
    backward_r2s, forward_r2s, combined_r2s = [], [], []

    for p in patients:
        # Backward-looking baseline
        d_back = _prepare_patient(p, h_steps, start)
        if d_back is None:
            continue
        # Forward-looking
        d_fwd = _prepare_patient_forward(p, h_steps, start)
        if d_fwd is None:
            continue

        fd = d_back['fd']
        bg = d_back['bg']
        actual = d_back['actual']
        split = d_back['split']
        usable = d_back['usable']
        n_pred = d_back['n_pred']

        # Backward baseline
        y_tr, y_val = actual[:split], actual[split:]
        X_tr_b, X_val_b = d_back['features'][:split], d_back['features'][split:]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_b), axis=1)
        vm_val = np.isfinite(y_val) & np.all(np.isfinite(X_val_b), axis=1)
        if vm_tr.sum() < 50:
            continue
        pred_b, _ = _ridge_predict(
            np.nan_to_num(X_tr_b[vm_tr], nan=0.0), y_tr[vm_tr],
            np.nan_to_num(X_val_b[vm_val], nan=0.0))
        backward_r2s.append(_r2(pred_b, y_val[vm_val]))

        # Forward baseline
        X_tr_f, X_val_f = d_fwd['features'][:split], d_fwd['features'][split:]
        vm_tr_f = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_f), axis=1)
        vm_val_f = np.isfinite(y_val) & np.all(np.isfinite(X_val_f), axis=1)
        if vm_tr_f.sum() < 50:
            continue
        pred_f, _ = _ridge_predict(
            np.nan_to_num(X_tr_f[vm_tr_f], nan=0.0), y_tr[vm_tr_f],
            np.nan_to_num(X_val_f[vm_val_f], nan=0.0))
        forward_r2s.append(_r2(pred_f, y_val[vm_val_f]))

        # === Post-prandial shape features (from EXP-893) ===
        supply = fd['supply'][:n_pred]
        supply_thresh = np.percentile(supply[supply > 0], 75) if np.sum(supply > 0) > 10 else 0.1

        pp_feats = np.zeros((n_pred, 5))
        last_meal_step = -999
        meal_peak_bg = 0.0
        meal_start_bg = 0.0

        for i in range(n_pred):
            if supply[i] > supply_thresh:
                if i - last_meal_step > 6:
                    meal_start_bg = bg[i]
                last_meal_step = i
                meal_peak_bg = max(meal_peak_bg, bg[i])

            time_since = (i - last_meal_step) * 5.0
            pp_feats[i, 0] = min(time_since, 360) / 360.0
            if time_since < 60:
                pp_feats[i, 1] = 1.0
            elif time_since < 180:
                pp_feats[i, 1] = 0.5
            else:
                pp_feats[i, 1] = 0.0
            if meal_start_bg > 0 and last_meal_step >= 0:
                pp_feats[i, 2] = bg[i] - meal_start_bg
            if last_meal_step >= 0:
                pp_feats[i, 3] = np.sum(supply[max(0, last_meal_step):i + 1])
            if i >= 3:
                pp_feats[i, 4] = supply[i] - supply[max(0, i - 3)]

        # === IOB shape features (from EXP-898) ===
        demand = fd['demand'][:n_pred]
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

        # Combine forward features + shape features
        shape_feats = np.hstack([
            pp_feats[start:start + usable],
            iob_feats[start:start + usable],
        ])
        X_combined = np.hstack([d_fwd['features'], shape_feats])
        X_tr_c, X_val_c = X_combined[:split], X_combined[split:]
        vm_tr_c = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_c), axis=1)
        vm_val_c = np.isfinite(y_val) & np.all(np.isfinite(X_val_c), axis=1)
        if vm_tr_c.sum() < 50:
            continue
        pred_c, _ = _ridge_predict(
            np.nan_to_num(X_tr_c[vm_tr_c], nan=0.0), y_tr[vm_tr_c],
            np.nan_to_num(X_val_c[vm_val_c], nan=0.0))
        combined_r2s.append(_r2(pred_c, y_val[vm_val_c]))

    back = round(float(np.mean(backward_r2s)), 3) if backward_r2s else None
    fwd = round(float(np.mean(forward_r2s)), 3) if forward_r2s else None
    comb = round(float(np.mean(combined_r2s)), 3) if combined_r2s else None
    delta_fwd = round(fwd - back, 3) if fwd and back else None
    delta_comb = round(comb - back, 3) if comb and back else None

    return {
        'experiment': 'EXP-903', 'name': 'Forward-Looking + Shape Combined',
        'status': 'pass',
        'detail': (f'backward={back}, forward={fwd}(Δ={delta_fwd:+.3f}), '
                   f'fwd+shape={comb}(Δ={delta_comb:+.3f})') if delta_comb else f'backward={back}',
        'results': {
            'backward_base': back, 'forward_base': fwd, 'forward_plus_shape': comb,
            'delta_forward': delta_fwd, 'delta_combined': delta_comb,
        },
    }


# ── EXP-904: Residual Variance Decomposition ────────────────────────────────

@register('EXP-904', 'Residual Variance Decomposition')
def exp_904(patients, detail=False):
    """Diagnostic: decompose prediction residuals into sensor noise, meal
    uncertainty, time-of-day systematic error, and remaining variance.
    """
    h_steps = 12
    start = 24
    decomp = {'sensor_noise': [], 'meal_var': [], 'tod_systematic': [], 'remaining': [], 'total': []}

    for p in patients:
        d = _prepare_patient(p, h_steps, start)
        if d is None:
            continue
        bg, fd, actual, features, split, usable, hours = (
            d['bg'], d['fd'], d['actual'], d['features'], d['split'], d['usable'], d['hours'])
        y_tr, y_val = actual[:split], actual[split:]
        n_pred = d['n_pred']

        X_tr, X_val = features[:split], features[split:]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        vm_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
        if vm_tr.sum() < 50:
            continue
        X_tr_clean = np.nan_to_num(X_tr[vm_tr], nan=0.0)
        pred, _ = _ridge_predict(X_tr_clean, y_tr[vm_tr], np.nan_to_num(X_val[vm_val], nan=0.0))
        residuals = y_val[vm_val] - pred
        total_var = float(np.var(residuals))
        if total_var < 1e-6:
            continue

        # 1. Sensor noise: high-frequency BG variation (rolling std of 3-point windows)
        bg_sig = bg[:n_pred].astype(float)
        noise_stds = []
        for i in range(2, len(bg_sig)):
            w3 = bg_sig[i - 2:i + 1]
            if np.all(np.isfinite(w3)):
                noise_stds.append(np.std(w3))
        sensor_noise_var = float(np.mean(noise_stds) ** 2) if noise_stds else 0.0

        # 2. Meal uncertainty: residual variance during meal vs basal
        supply = fd['supply'][:n_pred]
        val_start = start + split
        meal_resid, basal_resid = [], []
        val_indices = np.where(vm_val)[0]
        for idx_i, res in zip(val_indices, residuals):
            orig = val_start + idx_i
            if orig >= n_pred:
                continue
            s_act = np.sum(supply[max(0, orig - 24):orig]) > 0.5
            if s_act:
                meal_resid.append(res)
            else:
                basal_resid.append(res)
        meal_var = float(np.var(meal_resid)) if len(meal_resid) > 10 else 0.0
        basal_var = float(np.var(basal_resid)) if len(basal_resid) > 10 else 0.0
        meal_extra_var = max(0.0, meal_var - basal_var)

        # 3. Time-of-day systematic: residual mean by hour
        tod_var = 0.0
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

        # 4. Remaining
        remaining_var = max(0.0, total_var - sensor_noise_var - meal_extra_var - tod_var)

        decomp['sensor_noise'].append(sensor_noise_var / total_var * 100 if total_var > 0 else 0)
        decomp['meal_var'].append(meal_extra_var / total_var * 100 if total_var > 0 else 0)
        decomp['tod_systematic'].append(tod_var / total_var * 100 if total_var > 0 else 0)
        decomp['remaining'].append(remaining_var / total_var * 100 if total_var > 0 else 0)
        decomp['total'].append(total_var)

    means = {k: round(float(np.mean(v)), 1) if v else None for k, v in decomp.items()}

    return {
        'experiment': 'EXP-904', 'name': 'Residual Variance Decomposition',
        'status': 'pass',
        'detail': (f'sensor={means["sensor_noise"]}%, meal={means["meal_var"]}%, '
                   f'tod={means["tod_systematic"]}%, remaining={means["remaining"]}%'),
        'results': {
            'pct_sensor_noise': means['sensor_noise'],
            'pct_meal_uncertainty': means['meal_var'],
            'pct_tod_systematic': means['tod_systematic'],
            'pct_remaining': means['remaining'],
            'mean_total_var': means['total'],
        },
    }


# ── EXP-905: Multi-Horizon Shape Ensemble ────────────────────────────────────

@register('EXP-905', 'Multi-Horizon Shape Ensemble')
def exp_905(patients, detail=False):
    """Build post-prandial and IOB shape features at multiple horizons
    (30, 45, 60, 90 min), then use stacked generalization: train ridge per
    horizon, then meta-ridge on horizon predictions.
    """
    h_steps_list = [6, 9, 12, 18]  # 30, 45, 60, 90 min
    start = 24
    base_r2s, stacked_r2s = [], []

    for p in patients:
        d = _prepare_patient(p, 12, start)
        if d is None:
            continue
        fd = d['fd']
        bg = d['bg']
        actual_60 = d['actual']
        split = d['split']
        usable = d['usable']
        n_pred_base = d['n_pred']
        nr = d['nr']
        hours = d['hours']
        y_tr, y_val = actual_60[:split], actual_60[split:]

        # Base 60min prediction
        X_tr, X_val = d['features'][:split], d['features'][split:]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        vm_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
        if vm_tr.sum() < 50:
            continue
        X_tr_clean = np.nan_to_num(X_tr[vm_tr], nan=0.0)
        pred_b, _ = _ridge_predict(X_tr_clean, y_tr[vm_tr], np.nan_to_num(X_val[vm_val], nan=0.0))
        base_r2s.append(_r2(pred_b, y_val[vm_val]))

        # Build shape features for each horizon
        supply = fd['supply']
        demand = fd['demand']
        n_supply = len(supply)

        horizon_preds = {}
        for h in h_steps_list:
            n_pred_h = nr - h
            if n_pred_h - start < usable:
                continue
            actual_h = bg[h + 1 + start: h + 1 + start + usable]
            if len(actual_h) < usable:
                continue

            feat_h = _build_features_base(fd, hours, n_pred_h, h)
            feat_h = feat_h[start:start + usable]

            # Add shape features at this horizon
            pp_shape = np.zeros((usable, 3))
            iob_shape = np.zeros((usable, 3))
            for i in range(usable):
                orig = i + start
                # Post-prandial: supply AUC in horizon window
                pp_shape[i, 0] = np.sum(supply[orig:min(orig + h, n_supply)])
                if orig >= 12:
                    pp_shape[i, 1] = supply[orig] - supply[max(0, orig - 6)]
                pp_shape[i, 2] = np.sum(supply[max(0, orig - h):orig])
                # IOB: demand shape in horizon window
                iob_shape[i, 0] = np.sum(demand[orig:min(orig + h, n_supply)])
                if orig >= 12:
                    iob_shape[i, 1] = demand[orig] - demand[max(0, orig - 6)]
                iob_shape[i, 2] = np.sum(demand[max(0, orig - h):orig])

            feat_h_aug = np.hstack([feat_h, pp_shape, iob_shape])
            X_tr_h = feat_h_aug[:split]
            y_tr_h = actual_h[:split]
            valid_h = np.isfinite(y_tr_h) & np.all(np.isfinite(X_tr_h), axis=1)
            if valid_h.sum() < 50:
                continue

            X_tr_h_clean = np.nan_to_num(X_tr_h[valid_h], nan=0.0)
            _, w_h = _ridge_predict(X_tr_h_clean, y_tr_h[valid_h], X_tr_h_clean[:1], lam=0.1)
            if w_h is not None:
                all_preds = np.nan_to_num(feat_h_aug, nan=0.0) @ w_h
                horizon_preds[h] = all_preds

        if len(horizon_preds) < 2:
            continue

        # Meta-ridge: combine horizon predictions
        stack = np.column_stack([horizon_preds[h] for h in sorted(horizon_preds)])
        stack_bias = np.hstack([stack, np.ones((usable, 1))])

        X_tr_meta = stack_bias[:split]
        X_val_meta = stack_bias[split:]
        vm_tr_m = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_meta), axis=1)
        vm_val_m = np.isfinite(y_val) & np.all(np.isfinite(X_val_meta), axis=1)
        if vm_tr_m.sum() < 50:
            continue
        X_tr_m_clean = np.nan_to_num(X_tr_meta[vm_tr_m], nan=0.0)
        X_val_m_clean = np.nan_to_num(X_val_meta[vm_val_m], nan=0.0)
        pred_s, _ = _ridge_predict(X_tr_m_clean, y_tr[vm_tr_m], X_val_m_clean, lam=10.0)
        stacked_r2s.append(_r2(pred_s, y_val[vm_val_m]))

    base = round(float(np.mean(base_r2s)), 3) if base_r2s else None
    stacked = round(float(np.mean(stacked_r2s)), 3) if stacked_r2s else None
    delta = round(stacked - base, 3) if stacked and base else None

    return {
        'experiment': 'EXP-905', 'name': 'Multi-Horizon Shape Ensemble',
        'status': 'pass',
        'detail': f'base={base}, stacked={stacked}, Δ={delta:+.3f}' if delta else f'base={base}',
        'results': {
            'base': base, 'stacked_shape_ensemble': stacked, 'improvement': delta,
            'horizons_min': [h * 5 for h in h_steps_list],
        },
    }


# ── EXP-906: Patient Difficulty Predictor ────────────────────────────────────

@register('EXP-906', 'Patient Difficulty Predictor')
def exp_906(patients, detail=False):
    """Diagnostic: compute patient metadata (TIR, mean BG, CV, meal frequency,
    total daily insulin) and correlate with model R² to identify what makes
    patients easy or hard to predict.
    """
    h_steps = 12
    start = 24
    patient_meta = []

    for p in patients:
        d = _prepare_patient(p, h_steps, start)
        if d is None:
            continue
        bg, fd, actual, features, split, usable, n_pred = (
            d['bg'], d['fd'], d['actual'], d['features'], d['split'], d['usable'], d['n_pred'])
        y_tr, y_val = actual[:split], actual[split:]

        X_tr, X_val = features[:split], features[split:]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        vm_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
        if vm_tr.sum() < 50:
            continue
        X_tr_clean = np.nan_to_num(X_tr[vm_tr], nan=0.0)
        pred, _ = _ridge_predict(X_tr_clean, y_tr[vm_tr], np.nan_to_num(X_val[vm_val], nan=0.0))
        r2 = _r2(pred, y_val[vm_val])
        if not np.isfinite(r2):
            continue

        # Patient metadata
        bg_all = bg[:n_pred].astype(float)
        bg_valid = bg_all[np.isfinite(bg_all)]
        if len(bg_valid) < 100:
            continue

        mean_bg = float(np.mean(bg_valid))
        std_bg = float(np.std(bg_valid))
        cv_bg = std_bg / mean_bg if mean_bg > 0 else 0
        tir = float(np.sum((bg_valid >= 70) & (bg_valid <= 180)) / len(bg_valid) * 100)

        # Meal frequency: supply spikes per day
        supply = fd['supply'][:n_pred]
        supply_thresh = np.percentile(supply[supply > 0], 75) if np.sum(supply > 0) > 10 else 0.1
        meal_starts = 0
        last_meal = -999
        for i in range(n_pred):
            if supply[i] > supply_thresh and i - last_meal > 6:
                meal_starts += 1
                last_meal = i
        days = n_pred / 288.0
        meals_per_day = meal_starts / days if days > 0 else 0

        # Total daily insulin (demand AUC)
        demand = fd['demand'][:n_pred]
        daily_insulin = float(np.sum(demand)) / days if days > 0 else 0

        patient_meta.append({
            'patient': d['name'],
            'r2': round(r2, 3),
            'mean_bg': round(mean_bg, 1),
            'cv_bg': round(cv_bg, 3),
            'tir_pct': round(tir, 1),
            'meals_per_day': round(meals_per_day, 1),
            'daily_insulin_au': round(daily_insulin, 1),
            'n_days': round(days, 1),
        })

    if len(patient_meta) < 3:
        return {
            'experiment': 'EXP-906', 'name': 'Patient Difficulty Predictor',
            'status': 'pass', 'detail': 'insufficient patients',
            'results': {'patients': patient_meta},
        }

    # Correlate metadata with R²
    r2s = np.array([m['r2'] for m in patient_meta])
    correlations = {}
    for key in ['mean_bg', 'cv_bg', 'tir_pct', 'meals_per_day', 'daily_insulin_au']:
        vals = np.array([m[key] for m in patient_meta])
        if np.std(vals) > 1e-6 and np.std(r2s) > 1e-6:
            corr = float(np.corrcoef(vals, r2s)[0, 1])
            correlations[key] = round(corr, 3) if np.isfinite(corr) else None
        else:
            correlations[key] = None

    # Sort patients by difficulty
    patient_meta.sort(key=lambda m: m['r2'])
    easiest = patient_meta[-1] if patient_meta else None
    hardest = patient_meta[0] if patient_meta else None

    return {
        'experiment': 'EXP-906', 'name': 'Patient Difficulty Predictor',
        'status': 'pass',
        'detail': (f'correlations: {correlations}, '
                   f'easiest={easiest["patient"]}(R²={easiest["r2"]}), '
                   f'hardest={hardest["patient"]}(R²={hardest["r2"]})') if easiest and hardest else 'no data',
        'results': {
            'correlations_with_r2': correlations,
            'per_patient': patient_meta,
            'n_patients': len(patient_meta),
        },
    }


# ── EXP-907: Conformal Prediction Bands ─────────────────────────────────────

@register('EXP-907', 'Conformal Prediction Bands')
def exp_907(patients, detail=False):
    """Split conformal prediction: train on first 60%, calibrate on next 20%,
    test on last 20%. Compute nonconformity scores and prediction intervals.
    Report coverage at 90% target and interval width.
    """
    h_steps = 12
    start = 24
    coverages, widths = [], []
    target_coverage = 0.90

    for p in patients:
        d = _prepare_patient(p, h_steps, start)
        if d is None:
            continue
        features, actual, usable = d['features'], d['actual'], d['usable']

        # 60/20/20 split
        train_end = int(0.6 * usable)
        cal_end = int(0.8 * usable)
        if train_end < 100 or (cal_end - train_end) < 50 or (usable - cal_end) < 50:
            continue

        X_train = features[:train_end]
        y_train = actual[:train_end]
        X_cal = features[train_end:cal_end]
        y_cal = actual[train_end:cal_end]
        X_test = features[cal_end:]
        y_test = actual[cal_end:]

        vm_train = np.isfinite(y_train) & np.all(np.isfinite(X_train), axis=1)
        vm_cal = np.isfinite(y_cal) & np.all(np.isfinite(X_cal), axis=1)
        vm_test = np.isfinite(y_test) & np.all(np.isfinite(X_test), axis=1)
        if vm_train.sum() < 50 or vm_cal.sum() < 20 or vm_test.sum() < 20:
            continue

        X_tr_clean = np.nan_to_num(X_train[vm_train], nan=0.0)
        pred_cal, _ = _ridge_predict(X_tr_clean, y_train[vm_train],
                                      np.nan_to_num(X_cal[vm_cal], nan=0.0))
        pred_test, _ = _ridge_predict(X_tr_clean, y_train[vm_train],
                                       np.nan_to_num(X_test[vm_test], nan=0.0))

        # Nonconformity scores on calibration set
        cal_scores = np.abs(y_cal[vm_cal] - pred_cal)
        cal_scores = cal_scores[np.isfinite(cal_scores)]
        if len(cal_scores) < 10:
            continue

        # Conformal quantile (with finite-sample correction)
        n_cal = len(cal_scores)
        q_level = min(1.0, np.ceil((n_cal + 1) * target_coverage) / n_cal)
        q_hat = float(np.quantile(cal_scores, q_level))

        # Prediction intervals on test set
        test_scores = np.abs(y_test[vm_test] - pred_test)
        test_scores_finite = test_scores[np.isfinite(test_scores)]
        if len(test_scores_finite) < 10:
            continue

        coverage = float(np.mean(test_scores_finite <= q_hat))
        width = 2.0 * q_hat  # symmetric interval width

        coverages.append(coverage)
        widths.append(width)

    mean_coverage = round(float(np.mean(coverages)), 3) if coverages else None
    mean_width = round(float(np.mean(widths)), 1) if widths else None

    return {
        'experiment': 'EXP-907', 'name': 'Conformal Prediction Bands',
        'status': 'pass',
        'detail': (f'target=90%, actual_coverage={mean_coverage}, '
                   f'mean_interval_width={mean_width} mg/dL') if mean_coverage else 'insufficient data',
        'results': {
            'target_coverage': target_coverage,
            'actual_coverage': mean_coverage,
            'mean_interval_width_mgdl': mean_width,
            'n_patients': len(coverages),
        },
    }


# ── EXP-908: Asymmetric Loss (Linex via IRLS) ───────────────────────────────

@register('EXP-908', 'Asymmetric Loss IRLS')
def exp_908(patients, detail=False):
    """Train ridge with asymmetric loss: penalize under-prediction (hypo risk)
    2x more than over-prediction. Uses iteratively reweighted least squares.
    Evaluates with standard R² and clinical metrics (hypo sensitivity).
    """
    h_steps = 12
    start = 24
    n_irls_iter = 20
    asym_weight = 2.0  # under-prediction penalty multiplier
    alpha = 1.0

    base_r2s, asym_r2s = [], []
    hypo_sensitivity_base, hypo_sensitivity_asym = [], []

    for p in patients:
        d = _prepare_patient(p, h_steps, start)
        if d is None:
            continue
        features, actual, split, usable = d['features'], d['actual'], d['split'], d['usable']
        y_tr, y_val = actual[:split], actual[split:]

        X_tr, X_val = features[:split], features[split:]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        vm_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
        if vm_tr.sum() < 50:
            continue

        X_tr_v = np.nan_to_num(X_tr[vm_tr], nan=0.0)
        y_tr_v = y_tr[vm_tr]
        X_val_v = np.nan_to_num(X_val[vm_val], nan=0.0)
        y_val_v = y_val[vm_val]

        # Standard ridge baseline
        pred_b, _ = _ridge_predict(X_tr_v, y_tr_v, X_val_v)
        base_r2s.append(_r2(pred_b, y_val_v))

        # IRLS with asymmetric loss
        n_feat = X_tr_v.shape[1]
        I_mat = np.eye(n_feat)
        beta = np.zeros(n_feat)

        for iteration in range(n_irls_iter):
            residuals = y_tr_v - X_tr_v @ beta
            weights = np.where(residuals > 0, 1.0, asym_weight)
            sqrt_w = np.sqrt(weights)
            Xw = X_tr_v * sqrt_w[:, None]
            yw = y_tr_v * sqrt_w
            try:
                beta = np.linalg.lstsq(Xw.T @ Xw + alpha * I_mat, Xw.T @ yw, rcond=None)[0]
            except np.linalg.LinAlgError:
                break

        pred_asym = X_val_v @ beta
        asym_r2s.append(_r2(pred_asym, y_val_v))

        # Clinical: hypo sensitivity (actual < 70, did model predict < 80?)
        hypo_mask = y_val_v < 70
        if hypo_mask.sum() >= 3:
            sens_base = float(np.mean(pred_b[hypo_mask] < 80)) if np.all(np.isfinite(pred_b[hypo_mask])) else 0.0
            sens_asym = float(np.mean(pred_asym[hypo_mask] < 80))
            hypo_sensitivity_base.append(sens_base)
            hypo_sensitivity_asym.append(sens_asym)

    base = round(float(np.mean(base_r2s)), 3) if base_r2s else None
    asym = round(float(np.mean(asym_r2s)), 3) if asym_r2s else None
    delta = round(asym - base, 3) if asym and base else None
    hypo_sens_b = round(float(np.mean(hypo_sensitivity_base)), 3) if hypo_sensitivity_base else None
    hypo_sens_a = round(float(np.mean(hypo_sensitivity_asym)), 3) if hypo_sensitivity_asym else None

    return {
        'experiment': 'EXP-908', 'name': 'Asymmetric Loss IRLS',
        'status': 'pass',
        'detail': (f'base_R²={base}, asym_R²={asym}, Δ={delta:+.3f}, '
                   f'hypo_sens: base={hypo_sens_b}, asym={hypo_sens_a}') if delta else f'base={base}',
        'results': {
            'base_r2': base, 'asymmetric_r2': asym, 'r2_improvement': delta,
            'hypo_sensitivity_base': hypo_sens_b, 'hypo_sensitivity_asym': hypo_sens_a,
            'asym_weight': asym_weight, 'irls_iterations': n_irls_iter,
        },
    }


# ── EXP-909: Phase-Conditioned Prediction ────────────────────────────────────

@register('EXP-909', 'Phase-Conditioned Prediction')
def exp_909(patients, detail=False):
    """Split data into rising (BG[i] > BG[i-1]) and falling glucose phases.
    Train separate ridge models for each phase, then combine predictions.
    Hypothesis: rising/falling have different dynamics.
    """
    h_steps = 12
    start = 24
    base_r2s, phase_r2s = [], []

    for p in patients:
        d = _prepare_patient(p, h_steps, start)
        if d is None:
            continue
        bg, actual, features, split, usable = (
            d['bg'], d['actual'], d['features'], d['split'], d['usable'])
        y_tr, y_val = actual[:split], actual[split:]

        X_tr, X_val = features[:split], features[split:]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        vm_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
        if vm_tr.sum() < 50:
            continue
        X_tr_clean = np.nan_to_num(X_tr[vm_tr], nan=0.0)
        X_val_clean = np.nan_to_num(X_val[vm_val], nan=0.0)

        pred_b, _ = _ridge_predict(X_tr_clean, y_tr[vm_tr], X_val_clean)
        base_r2s.append(_r2(pred_b, y_val[vm_val]))

        # Classify into rising/falling phases
        bg_sig = bg.astype(float)
        rising_train = np.zeros(split, dtype=bool)
        falling_train = np.zeros(split, dtype=bool)
        for i in range(split):
            orig = i + start
            if orig >= 1 and np.isfinite(bg_sig[orig]) and np.isfinite(bg_sig[orig - 1]):
                if bg_sig[orig] > bg_sig[orig - 1]:
                    rising_train[i] = True
                else:
                    falling_train[i] = True

        rising_val = np.zeros(usable - split, dtype=bool)
        falling_val = np.zeros(usable - split, dtype=bool)
        for i in range(usable - split):
            orig = i + start + split
            if orig >= 1 and np.isfinite(bg_sig[orig]) and np.isfinite(bg_sig[orig - 1]):
                if bg_sig[orig] > bg_sig[orig - 1]:
                    rising_val[i] = True
                else:
                    falling_val[i] = True

        # Train separate models: both masks are over X_tr (split length)
        rise_tr = rising_train & vm_tr
        fall_tr = falling_train & vm_tr

        combined_pred = np.full(X_val_clean.shape[0], np.nan)

        if rise_tr.sum() >= 30:
            X_rise = np.nan_to_num(X_tr[rise_tr], nan=0.0)
            pred_rise, _ = _ridge_predict(X_rise, y_tr[rise_tr], X_val_clean)
        else:
            pred_rise = pred_b.copy()

        if fall_tr.sum() >= 30:
            X_fall = np.nan_to_num(X_tr[fall_tr], nan=0.0)
            pred_fall, _ = _ridge_predict(X_fall, y_tr[fall_tr], X_val_clean)
        else:
            pred_fall = pred_b.copy()

        # Combine: use phase-specific prediction for each val point
        rise_val_mask = rising_val[vm_val] if len(rising_val) == (usable - split) else np.zeros(vm_val.sum(), dtype=bool)
        fall_val_mask = falling_val[vm_val] if len(falling_val) == (usable - split) else np.zeros(vm_val.sum(), dtype=bool)

        # Need to align masks: vm_val is boolean of length (usable-split)
        rise_in_val = rising_val & vm_val
        fall_in_val = falling_val & vm_val

        # Map to compressed indices
        val_indices = np.where(vm_val)[0]
        for j, vi in enumerate(val_indices):
            if vi < len(rising_val) and rising_val[vi]:
                combined_pred[j] = pred_rise[j]
            elif vi < len(falling_val) and falling_val[vi]:
                combined_pred[j] = pred_fall[j]
            else:
                combined_pred[j] = pred_b[j] if j < len(pred_b) else np.nan

        finite_mask = np.isfinite(combined_pred)
        if finite_mask.sum() >= 10:
            phase_r2s.append(_r2(combined_pred[finite_mask], y_val[vm_val][finite_mask]))

    base = round(float(np.mean(base_r2s)), 3) if base_r2s else None
    phase = round(float(np.mean(phase_r2s)), 3) if phase_r2s else None
    delta = round(phase - base, 3) if phase and base else None

    return {
        'experiment': 'EXP-909', 'name': 'Phase-Conditioned Prediction',
        'status': 'pass',
        'detail': f'base={base}, phase_cond={phase}, Δ={delta:+.3f}' if delta else f'base={base}',
        'results': {'base': base, 'phase_conditioned': phase, 'improvement': delta},
    }


# ── EXP-910: Grand Benchmark with CV Stacking ───────────────────────────────

@register('EXP-910', 'Grand Benchmark CV Stacking')
def exp_910(patients, detail=False):
    """Definitive benchmark combining ALL productive features:
    - Forward-looking supply/demand sums (base=0.534)
    - Post-prandial shape features (EXP-893: +0.006)
    - IOB curve shape (EXP-898: +0.004)
    - PK derivatives (EXP-901)
    - Multi-horizon stacking at 3/5/7 horizons (EXP-862: +0.024)
    - Prediction disagreement features (EXP-867: +0.013)
    - Causal EMA (EXP-882: +0.005)
    Uses 5-fold CV stacking (EXP-871).
    """
    h_steps = 12
    start = 24
    horizons = [1, 3, 6, 12]
    n_folds = 5
    backward_r2s, grand_r2s = [], []
    per_patient = []

    for p in patients:
        # Backward-looking baseline
        d_back = _prepare_patient(p, h_steps, start)
        if d_back is None:
            continue
        # Forward-looking
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

        # === Build ALL productive features ===
        bg_sig = bg[:n_pred].astype(float)
        bg_sig[~np.isfinite(bg_sig)] = np.nanmean(bg_sig)
        supply = fd['supply'][:n_pred]
        demand = fd['demand'][:n_pred]
        n_supply = len(fd['supply'])

        # 1. Causal EMAs (EXP-882)
        ema_1h = _causal_ema(bg_sig, 2.0 / (12 + 1))
        ema_4h = _causal_ema(bg_sig, 2.0 / (48 + 1))

        # 2. Post-prandial shape (EXP-893)
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
            if meal_start_bg > 0 and last_meal_step >= 0:
                pp_feats[i, 2] = bg_sig[i] - meal_start_bg
            if last_meal_step >= 0:
                pp_feats[i, 3] = np.sum(supply[max(0, last_meal_step):i + 1])
            if i >= 3:
                pp_feats[i, 4] = supply[i] - supply[max(0, i - 3)]

        # 3. IOB shape (EXP-898)
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

        # 4. PK derivatives (EXP-901)
        d_supply = np.gradient(supply.astype(float))
        d_demand = np.gradient(demand.astype(float))
        d2_supply = np.gradient(d_supply)
        d2_demand = np.gradient(d_demand)

        # Assemble extra features
        extra = np.column_stack([
            ema_1h[start:start + usable],
            ema_4h[start:start + usable],
            pp_feats[start:start + usable],
            iob_feats[start:start + usable],
            d_supply[start:start + usable],
            d_demand[start:start + usable],
            d2_supply[start:start + usable],
            d2_demand[start:start + usable],
        ])

        # 5. Multi-horizon predictions (EXP-862) + disagreement (EXP-867)
        h_preds = {}
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
            continue

        # === 5-fold CV stacking (EXP-871) ===
        fold_size = vm_tr_g.sum() // n_folds
        train_valid_indices = np.where(vm_tr_g)[0]
        oof_predictions = np.full(split, np.nan)

        for fold_i in range(n_folds):
            f_start = fold_i * fold_size
            f_end = min((fold_i + 1) * fold_size, len(train_valid_indices))
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

        # Meta-features: OOF predictions + grand features for training
        oof_col = oof_predictions[:split].reshape(-1, 1)
        X_meta_tr = np.hstack([X_tr_g, oof_col])

        # For validation: use full-train predictions as the meta feature
        pred_full_train, _ = _ridge_predict(
            np.nan_to_num(X_tr_g[vm_tr_g], nan=0.0), y_tr[vm_tr_g],
            np.nan_to_num(X_val_g, nan=0.0), lam=10.0)
        pred_full_col = pred_full_train.reshape(-1, 1)
        X_meta_val = np.hstack([X_val_g, np.full((X_val_g.shape[0], 1), np.nan)])
        # Fill val meta col with full-train predictions where valid
        for j in range(X_meta_val.shape[0]):
            if j < len(pred_full_train) and np.isfinite(pred_full_train[j]):
                X_meta_val[j, -1] = pred_full_train[j]

        vm_meta_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_meta_tr), axis=1)
        vm_meta_val = np.isfinite(y_val) & np.all(np.isfinite(X_meta_val), axis=1)

        if vm_meta_tr.sum() < 50:
            # Fallback: use grand features directly without meta
            pred_g, _ = _ridge_predict(
                np.nan_to_num(X_tr_g[vm_tr_g], nan=0.0), y_tr[vm_tr_g],
                np.nan_to_num(X_val_g[vm_val_g], nan=0.0), lam=10.0)
            g_r2 = _r2(pred_g, y_val[vm_val_g])
        else:
            X_meta_tr_clean = np.nan_to_num(X_meta_tr[vm_meta_tr], nan=0.0)
            X_meta_val_clean = np.nan_to_num(X_meta_val[vm_meta_val], nan=0.0)
            pred_meta, _ = _ridge_predict(X_meta_tr_clean, y_tr[vm_meta_tr],
                                           X_meta_val_clean, lam=10.0)
            g_r2 = _r2(pred_meta, y_val[vm_meta_val])

        if np.isfinite(g_r2):
            grand_r2s.append(g_r2)
            per_patient.append({
                'patient': d_back['name'],
                'backward_base': round(bk_r2, 3),
                'grand': round(g_r2, 3),
                'delta': round(g_r2 - bk_r2, 3),
            })

    base = round(float(np.mean(backward_r2s)), 3) if backward_r2s else None
    grand = round(float(np.mean(grand_r2s)), 3) if grand_r2s else None
    delta = round(grand - base, 3) if grand and base else None

    return {
        'experiment': 'EXP-910', 'name': 'Grand Benchmark CV Stacking',
        'status': 'pass',
        'detail': (f'backward_base={base}, grand_cv_stack={grand}, '
                   f'Δ={delta:+.3f}') if delta else f'base={base}',
        'results': {
            'backward_base': base, 'grand_cv_stacking': grand, 'improvement': delta,
            'per_patient': per_patient, 'n_patients': len(grand_r2s),
            'features_used': [
                'forward_supply_demand', 'causal_ema', 'postprandial_shape',
                'iob_shape', 'pk_derivatives', 'multi_horizon_stack',
                'prediction_disagreement', 'cv_stacking_meta',
            ],
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
        description='EXP-901–910: Physics-Based Metabolic Flux Features & Grand Benchmark')
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
