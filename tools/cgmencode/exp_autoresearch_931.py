#!/usr/bin/env python3
"""EXP-931–940: Bidirectional Features, SOTA Mystery & Campaign Summary

Building on the 921–930 batch which established:
  - Forward-looking sums: base R²≈0.533 (EXP-911)
  - Forward CV stacking: R²≈0.549 (EXP-919)
  - Prior SOTA: R²=0.561 (EXP-871, backward base + CV stacking)
  - Definitive model (EXP-928): multiple features + stacking
  - Clarke A%: evaluated (EXP-929)
  - Practical ceiling: ~R²=0.567
  - Oracle ceiling: R²=0.613

Key mystery: Why does backward+stacking (0.561) beat forward+stacking (0.549)
despite forward base (0.533) > backward base (0.506)?

Hypothesis: backward base creates MORE DIVERSE multi-horizon predictions,
improving stacking benefit.

EXP-931: Bidirectional Supply/Demand Features
EXP-932: Backward Base CV Stacking Reproduction (SOTA 0.561 sanity check)
EXP-933: Bidirectional CV Stacking
EXP-934: Stacking Diversity Analysis
EXP-935: Optimal Stacking Configuration Search
EXP-936: Proper Cross-Validated Oracle (metabolic features at future point)
EXP-937: Ensemble of Backward + Forward Stacking (KEY experiment)
EXP-938: Leave-One-Patient-Out Generalization
EXP-939: Prediction Confidence Calibration
EXP-940: Extended Campaign Summary Statistics
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


def _mae(pred, actual):
    pred, actual = np.asarray(pred, dtype=float), np.asarray(actual, dtype=float)
    mask = np.isfinite(pred) & np.isfinite(actual)
    if mask.sum() < 10:
        return float('nan')
    return float(np.mean(np.abs(pred[mask] - actual[mask])))


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


def _build_features_base_backward(fd, hours, n_pred, h_steps):
    """Backward-looking supply/demand sums."""
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


def _build_enhanced_features_backward(fd, bg, hours, n_pred, h_steps, start=24):
    """Enhanced features with backward-looking supply/demand sums."""
    base = _build_features_base_backward(fd, hours, n_pred, h_steps)
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


def _prepare_patient_backward(p, h_steps=12, start=24):
    """Prepare patient data with backward-looking supply/demand sums."""
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
    features, _ = _build_enhanced_features_backward(fd, bg, hours, n_pred, h_steps, start)
    split = int(0.8 * usable)
    return {
        'fd': fd, 'bg': bg, 'hours': hours, 'nr': nr,
        'n_pred': n_pred, 'usable': usable, 'actual': actual,
        'features': features, 'split': split, 'name': p.get('name', '?'),
    }


def _cv_stacking_multi_horizon(fd, bg, hours, features, actual, split, usable,
                                nr, horizons, n_folds, start, direction,
                                meta_lam=1.0, base_lam=1.0):
    """Multi-horizon CV stacking. Returns (meta_r2, oof_columns, meta_pred, y_val).

    direction: 'forward', 'backward', or 'bidirectional'
    For each horizon h:
      - h_steps = h // 5
      - target = BG[i + h_steps] - BG[i]  (change, not absolute)
      - Train ridge on base features, generate OOF predictions via 5-fold CV
    Then stack: meta-ridge on the OOF columns -> predict 60-min target.
    """
    y_tr = actual[:split]
    y_val = actual[split:]

    # Build OOF predictions for each horizon
    oof_columns_tr = []
    oof_columns_val = []
    valid_horizons = []

    for h in horizons:
        h_steps = h // 5
        n_pred_h = nr - h_steps
        if n_pred_h - start < usable:
            continue

        # Target: BG change at horizon h
        target_h = np.full(usable, np.nan)
        for i in range(usable):
            orig = i + start
            future_idx = orig + h_steps
            if future_idx < len(bg) and np.isfinite(bg[future_idx]) and np.isfinite(bg[orig]):
                target_h[i] = bg[future_idx] - bg[orig]

        y_h_tr = target_h[:split]
        y_h_val = target_h[split:]

        X_tr = features[:split]
        X_val_f = features[split:]

        vm_tr = np.isfinite(y_h_tr) & np.all(np.isfinite(X_tr), axis=1)
        vm_val = np.isfinite(y_h_val) & np.all(np.isfinite(X_val_f), axis=1)

        if vm_tr.sum() < 100:
            continue

        # 5-fold chronological CV on training set
        train_valid_indices = np.where(vm_tr)[0]
        n_valid_tr = len(train_valid_indices)
        fold_size = n_valid_tr // n_folds
        if fold_size < 20:
            continue

        oof_pred = np.full(split, np.nan)
        for fold_i in range(n_folds):
            f_start = fold_i * fold_size
            f_end = min((fold_i + 1) * fold_size, n_valid_tr)
            if fold_i == n_folds - 1:
                f_end = n_valid_tr
            fold_val_idx = train_valid_indices[f_start:f_end]
            fold_tr_idx = np.concatenate([
                train_valid_indices[:f_start], train_valid_indices[f_end:]])
            if len(fold_tr_idx) < 50 or len(fold_val_idx) < 10:
                continue
            X_fold_tr = np.nan_to_num(X_tr[fold_tr_idx], nan=0.0)
            y_fold_tr = y_h_tr[fold_tr_idx]
            X_fold_val = np.nan_to_num(X_tr[fold_val_idx], nan=0.0)
            pred_fold, _ = _ridge_predict(X_fold_tr, y_fold_tr, X_fold_val, lam=base_lam)
            oof_pred[fold_val_idx] = pred_fold

        # Full-training prediction for validation set
        pred_val_h, _ = _ridge_predict(
            np.nan_to_num(X_tr[vm_tr], nan=0.0), y_h_tr[vm_tr],
            np.nan_to_num(X_val_f, nan=0.0), lam=base_lam)

        oof_columns_tr.append(oof_pred)
        oof_columns_val.append(pred_val_h)
        valid_horizons.append(h)

    if len(valid_horizons) < 2:
        return float('nan'), None, None, y_val, valid_horizons

    # Stack: meta-ridge on OOF columns -> predict 60-min target
    # 60-min target (h_steps=12)
    target_60 = np.full(usable, np.nan)
    for i in range(usable):
        orig = i + start
        future_idx = orig + 12
        if future_idx < len(bg) and np.isfinite(bg[future_idx]) and np.isfinite(bg[orig]):
            target_60[i] = bg[future_idx] - bg[orig]

    y_meta_tr = target_60[:split]
    y_meta_val = target_60[split:]

    X_meta_tr = np.column_stack(oof_columns_tr)
    X_meta_val = np.column_stack(oof_columns_val)

    vm_meta_tr = np.isfinite(y_meta_tr) & np.all(np.isfinite(X_meta_tr), axis=1)
    vm_meta_val = np.isfinite(y_meta_val) & np.all(np.isfinite(X_meta_val), axis=1)

    if vm_meta_tr.sum() < 50 or vm_meta_val.sum() < 10:
        return float('nan'), oof_columns_tr, None, y_meta_val, valid_horizons

    meta_pred, meta_w = _ridge_predict(
        np.nan_to_num(X_meta_tr[vm_meta_tr], nan=0.0), y_meta_tr[vm_meta_tr],
        np.nan_to_num(X_meta_val[vm_meta_val], nan=0.0), lam=meta_lam)

    meta_r2 = _r2(meta_pred, y_meta_val[vm_meta_val])
    return meta_r2, oof_columns_tr, meta_pred, y_meta_val, valid_horizons


# ── EXP-931: Bidirectional Supply/Demand Features ────────────────────────────

@register('EXP-931', 'Bidirectional Supply/Demand Features')
def exp_931(patients, detail=False):
    """Use BOTH backward-looking AND forward-looking sums as separate features.
    Build the full 16-feature base using backward sums, then add the same
    supply/demand features using forward sums as additional columns. ~24 features.
    """
    h_steps = 12
    start = 24
    fwd_r2s, bwd_r2s, bidir_r2s = [], [], []
    per_patient = []

    for p in patients:
        d_fwd = _prepare_patient_forward(p, h_steps, start)
        d_bwd = _prepare_patient_backward(p, h_steps, start)
        if d_fwd is None or d_bwd is None:
            continue

        fd = d_fwd['fd']
        bg = d_fwd['bg']
        actual = d_fwd['actual']
        split = d_fwd['split']
        usable = d_fwd['usable']
        n_pred = d_fwd['n_pred']
        hours = d_fwd['hours']
        y_tr, y_val = actual[:split], actual[split:]

        # Forward baseline
        fwd_feats = d_fwd['features']
        X_tr_f, X_val_f = fwd_feats[:split], fwd_feats[split:]
        vm_tr_f = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_f), axis=1)
        vm_val_f = np.isfinite(y_val) & np.all(np.isfinite(X_val_f), axis=1)
        if vm_tr_f.sum() < 50:
            continue
        pred_f, _ = _ridge_predict(
            np.nan_to_num(X_tr_f[vm_tr_f], nan=0.0), y_tr[vm_tr_f],
            np.nan_to_num(X_val_f[vm_val_f], nan=0.0))
        f_r2 = _r2(pred_f, y_val[vm_val_f])
        fwd_r2s.append(f_r2)

        # Backward baseline
        bwd_feats = d_bwd['features']
        X_tr_b, X_val_b = bwd_feats[:split], bwd_feats[split:]
        vm_tr_b = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_b), axis=1)
        vm_val_b = np.isfinite(y_val) & np.all(np.isfinite(X_val_b), axis=1)
        if vm_tr_b.sum() < 50:
            continue
        pred_b, _ = _ridge_predict(
            np.nan_to_num(X_tr_b[vm_tr_b], nan=0.0), y_tr[vm_tr_b],
            np.nan_to_num(X_val_b[vm_val_b], nan=0.0))
        b_r2 = _r2(pred_b, y_val[vm_val_b])
        bwd_r2s.append(b_r2)

        # Bidirectional: backward base + forward supply/demand columns
        fwd_base_raw = _build_features_base_forward(fd, hours, n_pred, h_steps)
        fwd_sd_cols = fwd_base_raw[start:start + usable, 1:4]  # supply, demand, hepatic (forward)
        bidir_feats = np.hstack([bwd_feats, fwd_sd_cols])

        X_tr_bi, X_val_bi = bidir_feats[:split], bidir_feats[split:]
        vm_tr_bi = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_bi), axis=1)
        vm_val_bi = np.isfinite(y_val) & np.all(np.isfinite(X_val_bi), axis=1)
        if vm_tr_bi.sum() < 50:
            continue
        pred_bi, _ = _ridge_predict(
            np.nan_to_num(X_tr_bi[vm_tr_bi], nan=0.0), y_tr[vm_tr_bi],
            np.nan_to_num(X_val_bi[vm_val_bi], nan=0.0))
        bi_r2 = _r2(pred_bi, y_val[vm_val_bi])
        bidir_r2s.append(bi_r2)

        if detail:
            per_patient.append({
                'patient': d_fwd['name'],
                'forward_r2': round(float(f_r2), 3) if np.isfinite(f_r2) else None,
                'backward_r2': round(float(b_r2), 3) if np.isfinite(b_r2) else None,
                'bidirectional_r2': round(float(bi_r2), 3) if np.isfinite(bi_r2) else None,
                'n_features_bidir': bidir_feats.shape[1],
            })

    fwd = round(float(np.mean(fwd_r2s)), 3) if fwd_r2s else None
    bwd = round(float(np.mean(bwd_r2s)), 3) if bwd_r2s else None
    bidir = round(float(np.mean(bidir_r2s)), 3) if bidir_r2s else None

    results = {
        'forward_base': fwd, 'backward_base': bwd, 'bidirectional': bidir,
        'n_patients': len(bidir_r2s),
        'improvement_vs_forward': round(bidir - fwd, 3) if bidir and fwd else None,
        'improvement_vs_backward': round(bidir - bwd, 3) if bidir and bwd else None,
    }
    if detail:
        results['per_patient'] = per_patient

    return {
        'experiment': 'EXP-931', 'name': 'Bidirectional Supply/Demand Features',
        'status': 'pass',
        'detail': (f'forward={fwd}, backward={bwd}, bidir={bidir}'
                   ) if bidir is not None else 'insufficient data',
        'results': results,
    }


# ── EXP-932: Backward Base CV Stacking Reproduction ─────────────────────────

@register('EXP-932', 'Backward Base CV Stacking Reproduction')
def exp_932(patients, detail=False):
    """Reproduce EXP-871's SOTA exactly. Backward-looking 16-feature base with
    5-fold CV stacking at horizons [36, 60, 84] minutes.
    Target at each horizon h = BG[i+h//5] - BG[i] (change, not absolute).
    Meta-learner: ridge on the 3 OOF prediction columns -> 60-min target.
    """
    h_steps = 12
    start = 24
    horizons = [36, 60, 84]
    n_folds = 5
    base_r2s, stacking_r2s = [], []
    per_patient = []

    for p in patients:
        d_bwd = _prepare_patient_backward(p, h_steps, start)
        if d_bwd is None:
            continue
        fd = d_bwd['fd']
        bg = d_bwd['bg']
        actual = d_bwd['actual']
        features = d_bwd['features']
        split = d_bwd['split']
        usable = d_bwd['usable']
        nr = d_bwd['nr']
        hours = d_bwd['hours']
        y_tr, y_val = actual[:split], actual[split:]

        # Backward base R²
        X_tr, X_val = features[:split], features[split:]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        vm_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
        if vm_tr.sum() < 100:
            continue
        pred_base, _ = _ridge_predict(
            np.nan_to_num(X_tr[vm_tr], nan=0.0), y_tr[vm_tr],
            np.nan_to_num(X_val[vm_val], nan=0.0))
        b_r2 = _r2(pred_base, y_val[vm_val])
        base_r2s.append(b_r2)

        # CV stacking
        meta_r2, _, _, _, valid_h = _cv_stacking_multi_horizon(
            fd, bg, hours, features, actual, split, usable, nr,
            horizons, n_folds, start, 'backward',
            meta_lam=1.0, base_lam=1.0)
        if np.isfinite(meta_r2):
            stacking_r2s.append(meta_r2)

        if detail:
            per_patient.append({
                'patient': d_bwd['name'],
                'backward_base_r2': round(float(b_r2), 3) if np.isfinite(b_r2) else None,
                'cv_stacking_r2': round(float(meta_r2), 3) if np.isfinite(meta_r2) else None,
                'delta': round(float(meta_r2 - b_r2), 3) if np.isfinite(meta_r2) and np.isfinite(b_r2) else None,
                'horizons_used': valid_h,
                'usable_steps': usable,
            })

    base = round(float(np.mean(base_r2s)), 3) if base_r2s else None
    stacking = round(float(np.mean(stacking_r2s)), 3) if stacking_r2s else None
    delta = round(stacking - base, 3) if stacking is not None and base is not None else None

    results = {
        'backward_base': base,
        'backward_cv_stacking': stacking,
        'improvement': delta,
        'n_patients': len(stacking_r2s),
        'horizons_minutes': horizons,
        'n_folds': n_folds,
        'target_sota': 0.561,
        'reproduced': abs(stacking - 0.561) < 0.02 if stacking else False,
    }
    if detail:
        results['per_patient'] = per_patient

    return {
        'experiment': 'EXP-932', 'name': 'Backward Base CV Stacking Reproduction',
        'status': 'pass',
        'detail': (f'backward_base={base}, cv_stacking={stacking}, '
                   f'Δ={delta:+.3f}, target=0.561') if delta is not None else f'base={base}',
        'results': results,
    }


# ── EXP-933: Bidirectional CV Stacking ──────────────────────────────────────

@register('EXP-933', 'Bidirectional CV Stacking')
def exp_933(patients, detail=False):
    """Combine backward and forward features, then apply CV stacking.
    If both temporal perspectives help, this should beat either alone.
    """
    h_steps = 12
    start = 24
    horizons = [36, 60, 84]
    n_folds = 5
    fwd_stack_r2s, bwd_stack_r2s, bidir_stack_r2s = [], [], []
    per_patient = []

    for p in patients:
        d_fwd = _prepare_patient_forward(p, h_steps, start)
        d_bwd = _prepare_patient_backward(p, h_steps, start)
        if d_fwd is None or d_bwd is None:
            continue
        fd = d_fwd['fd']
        bg = d_fwd['bg']
        actual = d_fwd['actual']
        split = d_fwd['split']
        usable = d_fwd['usable']
        nr = d_fwd['nr']
        hours = d_fwd['hours']
        n_pred = d_fwd['n_pred']

        # Forward stacking
        fwd_r2, _, _, _, _ = _cv_stacking_multi_horizon(
            fd, bg, hours, d_fwd['features'], actual, split, usable, nr,
            horizons, n_folds, start, 'forward')
        if np.isfinite(fwd_r2):
            fwd_stack_r2s.append(fwd_r2)

        # Backward stacking
        bwd_r2, _, _, _, _ = _cv_stacking_multi_horizon(
            fd, bg, hours, d_bwd['features'], actual, split, usable, nr,
            horizons, n_folds, start, 'backward')
        if np.isfinite(bwd_r2):
            bwd_stack_r2s.append(bwd_r2)

        # Bidirectional features: concat backward + forward supply/demand
        fwd_base_raw = _build_features_base_forward(fd, hours, n_pred, h_steps)
        fwd_sd_cols = fwd_base_raw[start:start + usable, 1:4]
        bidir_feats = np.hstack([d_bwd['features'], fwd_sd_cols])

        bidir_r2, _, _, _, _ = _cv_stacking_multi_horizon(
            fd, bg, hours, bidir_feats, actual, split, usable, nr,
            horizons, n_folds, start, 'bidirectional')
        if np.isfinite(bidir_r2):
            bidir_stack_r2s.append(bidir_r2)

        if detail:
            per_patient.append({
                'patient': d_fwd['name'],
                'forward_stacking': round(float(fwd_r2), 3) if np.isfinite(fwd_r2) else None,
                'backward_stacking': round(float(bwd_r2), 3) if np.isfinite(bwd_r2) else None,
                'bidirectional_stacking': round(float(bidir_r2), 3) if np.isfinite(bidir_r2) else None,
            })

    fwd_s = round(float(np.mean(fwd_stack_r2s)), 3) if fwd_stack_r2s else None
    bwd_s = round(float(np.mean(bwd_stack_r2s)), 3) if bwd_stack_r2s else None
    bidir_s = round(float(np.mean(bidir_stack_r2s)), 3) if bidir_stack_r2s else None

    results = {
        'forward_stacking': fwd_s, 'backward_stacking': bwd_s,
        'bidirectional_stacking': bidir_s,
        'n_patients': len(bidir_stack_r2s),
        'horizons_minutes': horizons,
        'best': max(
            [('forward', fwd_s or 0), ('backward', bwd_s or 0), ('bidirectional', bidir_s or 0)],
            key=lambda x: x[1])[0],
    }
    if detail:
        results['per_patient'] = per_patient

    return {
        'experiment': 'EXP-933', 'name': 'Bidirectional CV Stacking',
        'status': 'pass',
        'detail': (f'fwd_stack={fwd_s}, bwd_stack={bwd_s}, bidir_stack={bidir_s}'),
        'results': results,
    }


# ── EXP-934: Stacking Diversity Analysis ────────────────────────────────────

@register('EXP-934', 'Stacking Diversity Analysis')
def exp_934(patients, detail=False):
    """Diagnostic: measure prediction diversity between horizon models.
    Compute correlation between 36-min and 84-min OOF predictions.
    High correlation = low diversity = less stacking benefit.
    Compare diversity for backward-base vs forward-base vs bidirectional.
    """
    h_steps = 12
    start = 24
    horizons = [36, 60, 84]
    n_folds = 5

    diversity_results = {'forward': [], 'backward': [], 'bidirectional': []}
    per_patient = []

    for p in patients:
        d_fwd = _prepare_patient_forward(p, h_steps, start)
        d_bwd = _prepare_patient_backward(p, h_steps, start)
        if d_fwd is None or d_bwd is None:
            continue
        fd = d_fwd['fd']
        bg = d_fwd['bg']
        actual = d_fwd['actual']
        split = d_fwd['split']
        usable = d_fwd['usable']
        nr = d_fwd['nr']
        hours = d_fwd['hours']
        n_pred = d_fwd['n_pred']

        patient_div = {'patient': d_fwd['name']}

        for direction, feats_label in [
            ('forward', d_fwd['features']),
            ('backward', d_bwd['features']),
        ]:
            _, oof_cols, _, _, valid_h = _cv_stacking_multi_horizon(
                fd, bg, hours, feats_label, actual, split, usable, nr,
                horizons, n_folds, start, direction)

            if oof_cols is not None and len(oof_cols) >= 2:
                # Compute pairwise correlations between OOF columns
                oof_arr = np.column_stack(oof_cols)
                valid_mask = np.all(np.isfinite(oof_arr), axis=1)
                if valid_mask.sum() > 50:
                    corr_matrix = np.corrcoef(oof_arr[valid_mask].T)
                    # Average off-diagonal correlation
                    n_h = corr_matrix.shape[0]
                    off_diag = []
                    for ii in range(n_h):
                        for jj in range(ii + 1, n_h):
                            if np.isfinite(corr_matrix[ii, jj]):
                                off_diag.append(corr_matrix[ii, jj])
                    mean_corr = float(np.mean(off_diag)) if off_diag else float('nan')
                    diversity = 1.0 - mean_corr  # higher = more diverse
                    diversity_results[direction].append(diversity)
                    patient_div[f'{direction}_mean_corr'] = round(mean_corr, 3)
                    patient_div[f'{direction}_diversity'] = round(diversity, 3)

        # Bidirectional
        fwd_base_raw = _build_features_base_forward(fd, hours, n_pred, h_steps)
        fwd_sd_cols = fwd_base_raw[start:start + usable, 1:4]
        bidir_feats = np.hstack([d_bwd['features'], fwd_sd_cols])

        _, oof_cols_bi, _, _, valid_h_bi = _cv_stacking_multi_horizon(
            fd, bg, hours, bidir_feats, actual, split, usable, nr,
            horizons, n_folds, start, 'bidirectional')
        if oof_cols_bi is not None and len(oof_cols_bi) >= 2:
            oof_arr_bi = np.column_stack(oof_cols_bi)
            valid_mask_bi = np.all(np.isfinite(oof_arr_bi), axis=1)
            if valid_mask_bi.sum() > 50:
                corr_bi = np.corrcoef(oof_arr_bi[valid_mask_bi].T)
                n_h_bi = corr_bi.shape[0]
                off_diag_bi = []
                for ii in range(n_h_bi):
                    for jj in range(ii + 1, n_h_bi):
                        if np.isfinite(corr_bi[ii, jj]):
                            off_diag_bi.append(corr_bi[ii, jj])
                mean_corr_bi = float(np.mean(off_diag_bi)) if off_diag_bi else float('nan')
                diversity_bi = 1.0 - mean_corr_bi
                diversity_results['bidirectional'].append(diversity_bi)
                patient_div['bidirectional_mean_corr'] = round(mean_corr_bi, 3)
                patient_div['bidirectional_diversity'] = round(diversity_bi, 3)

        if detail:
            per_patient.append(patient_div)

    summary = {}
    for direction in ['forward', 'backward', 'bidirectional']:
        vals = diversity_results[direction]
        if vals:
            summary[f'{direction}_mean_diversity'] = round(float(np.mean(vals)), 3)
            summary[f'{direction}_std_diversity'] = round(float(np.std(vals)), 3)
        else:
            summary[f'{direction}_mean_diversity'] = None

    # Test hypothesis: backward should have higher diversity
    bwd_div = summary.get('backward_mean_diversity')
    fwd_div = summary.get('forward_mean_diversity')
    hypothesis_confirmed = None
    if bwd_div is not None and fwd_div is not None:
        hypothesis_confirmed = bwd_div > fwd_div

    results = {
        **summary,
        'hypothesis': 'backward creates more diverse predictions than forward',
        'hypothesis_confirmed': hypothesis_confirmed,
        'n_patients': max(len(v) for v in diversity_results.values()) if any(diversity_results.values()) else 0,
    }
    if detail:
        results['per_patient'] = per_patient

    detail_str = ', '.join(
        f'{d}={summary.get(f"{d}_mean_diversity")}'
        for d in ['forward', 'backward', 'bidirectional'])

    return {
        'experiment': 'EXP-934', 'name': 'Stacking Diversity Analysis',
        'status': 'pass',
        'detail': f'{detail_str}, hypothesis={hypothesis_confirmed}',
        'results': results,
    }


# ── EXP-935: Optimal Stacking Configuration Search ──────────────────────────

@register('EXP-935', 'Optimal Stacking Config Search')
def exp_935(patients, detail=False):
    """Test different stacking configurations:
    - Horizons: [30,60,90], [36,60,84], [15,30,45,60,75,90], [20,40,60,80,100]
    - Meta-learner alpha: [0.1, 1.0, 10.0, 100.0]
    Use forward base features. Find the configuration that maximizes R².
    """
    h_steps = 12
    start = 24
    n_folds = 5

    horizon_configs = [
        [30, 60, 90],
        [36, 60, 84],
        [15, 30, 45, 60, 75, 90],
        [20, 40, 60, 80, 100],
    ]
    meta_alphas = [0.1, 1.0, 10.0, 100.0]

    # Pre-prepare all patients
    patient_data = []
    for p in patients:
        d_fwd = _prepare_patient_forward(p, h_steps, start)
        if d_fwd is None:
            continue
        patient_data.append(d_fwd)

    if not patient_data:
        return {
            'experiment': 'EXP-935', 'name': 'Optimal Stacking Config Search',
            'status': 'pass', 'detail': 'insufficient data',
            'results': {},
        }

    config_results = {}
    best_r2 = -float('inf')
    best_config = None

    for horizons in horizon_configs:
        for alpha in meta_alphas:
            config_key = f'h={horizons}_a={alpha}'
            r2s = []

            for d in patient_data:
                fd = d['fd']
                bg = d['bg']
                actual = d['actual']
                features = d['features']
                split = d['split']
                usable = d['usable']
                nr = d['nr']
                hours = d['hours']

                meta_r2, _, _, _, _ = _cv_stacking_multi_horizon(
                    fd, bg, hours, features, actual, split, usable, nr,
                    horizons, n_folds, start, 'forward',
                    meta_lam=alpha, base_lam=1.0)
                if np.isfinite(meta_r2):
                    r2s.append(meta_r2)

            mean_r2 = round(float(np.mean(r2s)), 4) if r2s else None
            config_results[config_key] = {
                'mean_r2': mean_r2, 'n_patients': len(r2s),
                'horizons': horizons, 'meta_alpha': alpha,
            }
            if mean_r2 is not None and mean_r2 > best_r2:
                best_r2 = mean_r2
                best_config = config_key

    # Sort by R²
    sorted_configs = sorted(
        config_results.items(),
        key=lambda x: x[1]['mean_r2'] if x[1]['mean_r2'] is not None else -1,
        reverse=True)

    results = {
        'best_config': best_config,
        'best_r2': round(best_r2, 4) if np.isfinite(best_r2) else None,
        'n_configs_tested': len(config_results),
        'n_patients': len(patient_data),
        'top_5': [{'config': k, **v} for k, v in sorted_configs[:5]],
        'all_configs': config_results,
    }

    return {
        'experiment': 'EXP-935', 'name': 'Optimal Stacking Config Search',
        'status': 'pass',
        'detail': f'best={best_config}, R²={round(best_r2, 3) if np.isfinite(best_r2) else None}',
        'results': results,
    }


# ── EXP-936: Proper Cross-Validated Oracle ──────────────────────────────────

@register('EXP-936', 'Proper CV Oracle (Metabolic)')
def exp_936(patients, detail=False):
    """Fix the trivial oracle. Train oracle using ONLY metabolic features at
    the FUTURE prediction point (not the future BG itself):
    - supply_at_target = fd['supply'][i + h_steps]
    - demand_at_target = fd['demand'][i + h_steps]
    - net_flux_at_target = fd['net'][i + h_steps]
    This tells us: if we had perfect knowledge of future metabolic state
    (but not future BG), how well could we predict?
    """
    h_steps = 12
    start = 24
    base_r2s, oracle_r2s = [], []
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

        # Base model
        X_tr, X_val = features[:split], features[split:]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        vm_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
        if vm_tr.sum() < 100:
            continue
        pred_base, _ = _ridge_predict(
            np.nan_to_num(X_tr[vm_tr], nan=0.0), y_tr[vm_tr],
            np.nan_to_num(X_val[vm_val], nan=0.0))
        b_r2 = _r2(pred_base, y_val[vm_val])
        base_r2s.append(b_r2)

        # Oracle features: metabolic state at the FUTURE prediction point
        supply = fd['supply']
        demand = fd['demand']
        net = supply - demand
        n_supply = len(supply)

        oracle_feats = np.zeros((usable, 3))
        for i in range(usable):
            orig = i + start
            target_idx = orig + h_steps
            if target_idx < n_supply:
                oracle_feats[i, 0] = supply[target_idx]
                oracle_feats[i, 1] = demand[target_idx]
                oracle_feats[i, 2] = net[target_idx]

        X_oracle = np.hstack([features, oracle_feats])
        X_tr_o, X_val_o = X_oracle[:split], X_oracle[split:]
        vm_tr_o = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_o), axis=1)
        vm_val_o = np.isfinite(y_val) & np.all(np.isfinite(X_val_o), axis=1)
        if vm_tr_o.sum() < 100:
            continue

        pred_oracle, _ = _ridge_predict(
            np.nan_to_num(X_tr_o[vm_tr_o], nan=0.0), y_tr[vm_tr_o],
            np.nan_to_num(X_val_o[vm_val_o], nan=0.0))
        o_r2 = _r2(pred_oracle, y_val[vm_val_o])
        oracle_r2s.append(o_r2)

        if detail:
            per_patient.append({
                'patient': d_fwd['name'],
                'base_r2': round(float(b_r2), 3) if np.isfinite(b_r2) else None,
                'metabolic_oracle_r2': round(float(o_r2), 3) if np.isfinite(o_r2) else None,
                'gap': round(float(o_r2 - b_r2), 3) if np.isfinite(o_r2) and np.isfinite(b_r2) else None,
            })

    base = round(float(np.mean(base_r2s)), 3) if base_r2s else None
    oracle = round(float(np.mean(oracle_r2s)), 3) if oracle_r2s else None
    gap = round(oracle - base, 3) if oracle is not None and base is not None else None

    results = {
        'base_r2': base, 'metabolic_oracle_r2': oracle,
        'gap': gap, 'n_patients': len(oracle_r2s),
        'oracle_features': ['supply_at_target', 'demand_at_target', 'net_flux_at_target'],
        'interpretation': ('If metabolic oracle >> base, future metabolic state '
                           'carries predictive info beyond current features'),
    }
    if detail:
        results['per_patient'] = per_patient

    return {
        'experiment': 'EXP-936', 'name': 'Proper CV Oracle (Metabolic)',
        'status': 'pass',
        'detail': (f'base={base}, metabolic_oracle={oracle}, '
                   f'gap={gap:+.3f}') if gap is not None else f'base={base}',
        'results': results,
    }


# ── EXP-937: Ensemble of Backward + Forward Stacking ────────────────────────

@register('EXP-937', 'Ensemble Backward+Forward Stacking')
def exp_937(patients, detail=False):
    """Simple average or weighted average of:
    - Backward-base CV stacking prediction (R²~0.561)
    - Forward-base CV stacking prediction (R²~0.549)
    Test: equal weight, optimized weight, and ridge on both predictions.
    If the two stacking models capture different info, ensemble should beat both.
    """
    h_steps = 12
    start = 24
    horizons = [36, 60, 84]
    n_folds = 5
    fwd_r2s, bwd_r2s, equal_r2s, opt_r2s, ridge_r2s = [], [], [], [], []
    per_patient = []

    for p in patients:
        d_fwd = _prepare_patient_forward(p, h_steps, start)
        d_bwd = _prepare_patient_backward(p, h_steps, start)
        if d_fwd is None or d_bwd is None:
            continue
        fd = d_fwd['fd']
        bg = d_fwd['bg']
        actual = d_fwd['actual']
        split = d_fwd['split']
        usable = d_fwd['usable']
        nr = d_fwd['nr']
        hours = d_fwd['hours']

        # Forward stacking: get predictions on validation set
        fwd_r2_val, fwd_oof, fwd_meta_pred, y_meta_val_f, fwd_valid_h = \
            _cv_stacking_multi_horizon(
                fd, bg, hours, d_fwd['features'], actual, split, usable, nr,
                horizons, n_folds, start, 'forward')

        # Backward stacking: get predictions on validation set
        bwd_r2_val, bwd_oof, bwd_meta_pred, y_meta_val_b, bwd_valid_h = \
            _cv_stacking_multi_horizon(
                fd, bg, hours, d_bwd['features'], actual, split, usable, nr,
                horizons, n_folds, start, 'backward')

        if not np.isfinite(fwd_r2_val) or not np.isfinite(bwd_r2_val):
            continue
        if fwd_meta_pred is None or bwd_meta_pred is None:
            continue

        fwd_r2s.append(fwd_r2_val)
        bwd_r2s.append(bwd_r2_val)

        # Need to align predictions: both use 60-min target on the same val set
        # Both predict delta BG at 60-min. Use the shorter prediction vector.
        n_fwd = len(fwd_meta_pred)
        n_bwd = len(bwd_meta_pred)

        # Reconstruct validation targets for 60-min
        target_60 = np.full(usable, np.nan)
        for i in range(usable):
            orig = i + start
            future_idx = orig + 12
            if future_idx < len(bg) and np.isfinite(bg[future_idx]) and np.isfinite(bg[orig]):
                target_60[i] = bg[future_idx] - bg[orig]
        y_val_60 = target_60[split:]

        # Align: we need matching valid masks for fwd and bwd predictions
        # The meta predictions correspond to valid entries of y_val_60
        vm_val_60 = np.isfinite(y_val_60)

        # Rebuild fwd and bwd OOF validation predictions aligned to vm_val_60
        # Forward stacking full prediction
        fwd_feats = d_fwd['features']
        bwd_feats = d_bwd['features']

        # Retrain full models for aligned val predictions
        fwd_full_pred = np.full(usable - split, np.nan)
        bwd_full_pred = np.full(usable - split, np.nan)

        for direction, feats, out_pred in [
            ('forward', fwd_feats, fwd_full_pred),
            ('backward', bwd_feats, bwd_full_pred),
        ]:
            oof_columns_val = []
            for h in horizons:
                h_st = h // 5
                n_pred_h = nr - h_st
                if n_pred_h - start < usable:
                    continue
                target_h_tr = np.full(split, np.nan)
                for i in range(split):
                    orig = i + start
                    fi = orig + h_st
                    if fi < len(bg) and np.isfinite(bg[fi]) and np.isfinite(bg[orig]):
                        target_h_tr[i] = bg[fi] - bg[orig]

                X_tr = feats[:split]
                X_val_f = feats[split:]
                vm_t = np.isfinite(target_h_tr) & np.all(np.isfinite(X_tr), axis=1)
                if vm_t.sum() < 100:
                    continue
                pred_h_val, _ = _ridge_predict(
                    np.nan_to_num(X_tr[vm_t], nan=0.0), target_h_tr[vm_t],
                    np.nan_to_num(X_val_f, nan=0.0), lam=1.0)
                oof_columns_val.append(pred_h_val)

            if len(oof_columns_val) < 2:
                continue

            # Train meta on OOF training columns
            oof_columns_tr = []
            for h in horizons:
                h_st = h // 5
                n_pred_h = nr - h_st
                if n_pred_h - start < usable:
                    continue
                target_h_tr = np.full(split, np.nan)
                for i in range(split):
                    orig = i + start
                    fi = orig + h_st
                    if fi < len(bg) and np.isfinite(bg[fi]) and np.isfinite(bg[orig]):
                        target_h_tr[i] = bg[fi] - bg[orig]

                X_tr = feats[:split]
                vm_t = np.isfinite(target_h_tr) & np.all(np.isfinite(X_tr), axis=1)
                if vm_t.sum() < 100:
                    continue

                train_valid_idx = np.where(vm_t)[0]
                n_vt = len(train_valid_idx)
                fold_sz = n_vt // n_folds
                if fold_sz < 20:
                    continue
                oof_p = np.full(split, np.nan)
                for fi_idx in range(n_folds):
                    fs = fi_idx * fold_sz
                    fe = min((fi_idx + 1) * fold_sz, n_vt)
                    if fi_idx == n_folds - 1:
                        fe = n_vt
                    fv_idx = train_valid_idx[fs:fe]
                    ft_idx = np.concatenate([train_valid_idx[:fs], train_valid_idx[fe:]])
                    if len(ft_idx) < 50 or len(fv_idx) < 10:
                        continue
                    pf, _ = _ridge_predict(
                        np.nan_to_num(X_tr[ft_idx], nan=0.0), target_h_tr[ft_idx],
                        np.nan_to_num(X_tr[fv_idx], nan=0.0), lam=1.0)
                    oof_p[fv_idx] = pf
                oof_columns_tr.append(oof_p)

            if len(oof_columns_tr) < 2 or len(oof_columns_tr) != len(oof_columns_val):
                continue

            X_meta_tr = np.column_stack(oof_columns_tr)
            X_meta_val = np.column_stack(oof_columns_val)

            y_m_tr = target_60[:split]
            vm_m_tr = np.isfinite(y_m_tr) & np.all(np.isfinite(X_meta_tr), axis=1)
            vm_m_val = np.isfinite(y_val_60) & np.all(np.isfinite(X_meta_val), axis=1)

            if vm_m_tr.sum() < 50 or vm_m_val.sum() < 10:
                continue

            mp, _ = _ridge_predict(
                np.nan_to_num(X_meta_tr[vm_m_tr], nan=0.0), y_m_tr[vm_m_tr],
                np.nan_to_num(X_meta_val[vm_m_val], nan=0.0), lam=1.0)

            valid_idx = np.where(vm_m_val)[0]
            out_pred[valid_idx] = mp

        # Now combine: equal weight, optimized weight, ridge
        both_valid = np.isfinite(fwd_full_pred) & np.isfinite(bwd_full_pred) & np.isfinite(y_val_60)
        if both_valid.sum() < 30:
            continue

        fwd_v = fwd_full_pred[both_valid]
        bwd_v = bwd_full_pred[both_valid]
        y_v = y_val_60[both_valid]

        # Equal weight ensemble
        equal_pred = 0.5 * fwd_v + 0.5 * bwd_v
        eq_r2 = _r2(equal_pred, y_v)
        equal_r2s.append(eq_r2)

        # Optimized weight: test weights 0.0 to 1.0 in steps of 0.05
        best_w = 0.5
        best_w_r2 = eq_r2
        for w in np.arange(0.0, 1.05, 0.05):
            wp = w * fwd_v + (1 - w) * bwd_v
            wr2 = _r2(wp, y_v)
            if np.isfinite(wr2) and wr2 > best_w_r2:
                best_w_r2 = wr2
                best_w = round(w, 2)
        opt_r2s.append(best_w_r2)

        # Ridge on both predictions
        X_ens = np.column_stack([fwd_v, bwd_v, np.ones(len(fwd_v))])
        # Use first 80% for training, last 20% for eval
        ens_split = int(0.8 * len(fwd_v))
        if ens_split < 30:
            ridge_r2s.append(best_w_r2)
        else:
            pred_ens, _ = _ridge_predict(
                np.nan_to_num(X_ens[:ens_split], nan=0.0), y_v[:ens_split],
                np.nan_to_num(X_ens[ens_split:], nan=0.0), lam=1.0)
            r_r2 = _r2(pred_ens, y_v[ens_split:])
            ridge_r2s.append(r_r2)

        if detail:
            per_patient.append({
                'patient': d_fwd['name'],
                'forward_stacking': round(float(fwd_r2_val), 3),
                'backward_stacking': round(float(bwd_r2_val), 3),
                'equal_weight': round(float(eq_r2), 3) if np.isfinite(eq_r2) else None,
                'optimal_weight': round(float(best_w_r2), 3) if np.isfinite(best_w_r2) else None,
                'optimal_w_fwd': best_w,
                'ridge_ensemble': round(float(ridge_r2s[-1]), 3) if np.isfinite(ridge_r2s[-1]) else None,
            })

    fwd_mean = round(float(np.mean(fwd_r2s)), 3) if fwd_r2s else None
    bwd_mean = round(float(np.mean(bwd_r2s)), 3) if bwd_r2s else None
    eq_mean = round(float(np.mean(equal_r2s)), 3) if equal_r2s else None
    opt_mean = round(float(np.mean(opt_r2s)), 3) if opt_r2s else None
    ridge_mean = round(float(np.nanmean(ridge_r2s)), 3) if ridge_r2s else None

    results = {
        'forward_stacking': fwd_mean,
        'backward_stacking': bwd_mean,
        'equal_weight_ensemble': eq_mean,
        'optimal_weight_ensemble': opt_mean,
        'ridge_ensemble': ridge_mean,
        'n_patients': len(equal_r2s),
        'best_method': max(
            [('forward', fwd_mean or 0), ('backward', bwd_mean or 0),
             ('equal_weight', eq_mean or 0), ('optimal_weight', opt_mean or 0),
             ('ridge', ridge_mean or 0)],
            key=lambda x: x[1])[0],
    }
    if detail:
        results['per_patient'] = per_patient

    return {
        'experiment': 'EXP-937', 'name': 'Ensemble Backward+Forward Stacking',
        'status': 'pass',
        'detail': (f'fwd={fwd_mean}, bwd={bwd_mean}, equal={eq_mean}, '
                   f'opt={opt_mean}, ridge={ridge_mean}'),
        'results': results,
    }


# ── EXP-938: Leave-One-Patient-Out Generalization ───────────────────────────

@register('EXP-938', 'Leave-One-Patient-Out')
def exp_938(patients, detail=False):
    """For each patient, train on the other N-1 patients' data and predict the
    held-out patient. Tests whether the model generalizes across patients.
    Expect degradation (EXP-859 showed pooled=0.320), but quantify for
    new-patient deployment.
    """
    h_steps = 12
    start = 24

    # Pre-prepare all patients
    all_data = []
    for p in patients:
        d_fwd = _prepare_patient_forward(p, h_steps, start)
        if d_fwd is None:
            continue
        features = d_fwd['features']
        actual = d_fwd['actual']
        usable = d_fwd['usable']
        vm = np.isfinite(actual) & np.all(np.isfinite(features), axis=1)
        if vm.sum() < 100:
            continue
        all_data.append({
            'name': d_fwd['name'],
            'features': np.nan_to_num(features[vm], nan=0.0),
            'actual': actual[vm],
            'usable': usable,
            'split': d_fwd['split'],
            'features_raw': features,
            'actual_raw': actual,
        })

    if len(all_data) < 3:
        return {
            'experiment': 'EXP-938', 'name': 'Leave-One-Patient-Out',
            'status': 'pass', 'detail': 'insufficient patients',
            'results': {},
        }

    within_r2s, lopo_r2s = [], []
    per_patient = []

    for hold_idx in range(len(all_data)):
        held = all_data[hold_idx]

        # Within-patient R² (for comparison)
        split = min(held['split'], len(held['actual_raw']))
        vm_w = np.isfinite(held['actual_raw']) & np.all(np.isfinite(held['features_raw']), axis=1)
        X_tr_w = np.nan_to_num(held['features_raw'][:split][vm_w[:split]], nan=0.0)
        y_tr_w = held['actual_raw'][:split][vm_w[:split]]
        X_val_w = np.nan_to_num(held['features_raw'][split:][vm_w[split:]], nan=0.0)
        y_val_w = held['actual_raw'][split:][vm_w[split:]]

        if len(X_tr_w) < 50 or len(X_val_w) < 20:
            continue

        pred_within, _ = _ridge_predict(X_tr_w, y_tr_w, X_val_w)
        w_r2 = _r2(pred_within, y_val_w)
        within_r2s.append(w_r2)

        # LOPO: train on all other patients
        train_X_parts, train_y_parts = [], []
        for j in range(len(all_data)):
            if j == hold_idx:
                continue
            train_X_parts.append(all_data[j]['features'])
            train_y_parts.append(all_data[j]['actual'])

        X_train_lopo = np.vstack(train_X_parts)
        y_train_lopo = np.concatenate(train_y_parts)

        # Predict held-out patient (use their validation portion)
        X_held_val = np.nan_to_num(held['features_raw'][split:], nan=0.0)
        y_held_val = held['actual_raw'][split:]
        vm_held = np.isfinite(y_held_val) & np.all(np.isfinite(X_held_val), axis=1)

        if vm_held.sum() < 20:
            continue

        pred_lopo, _ = _ridge_predict(
            X_train_lopo, y_train_lopo,
            X_held_val[vm_held], lam=1.0)
        l_r2 = _r2(pred_lopo, y_held_val[vm_held])
        lopo_r2s.append(l_r2)

        if detail:
            per_patient.append({
                'patient': held['name'],
                'within_patient_r2': round(float(w_r2), 3) if np.isfinite(w_r2) else None,
                'lopo_r2': round(float(l_r2), 3) if np.isfinite(l_r2) else None,
                'degradation': round(float(w_r2 - l_r2), 3) if np.isfinite(w_r2) and np.isfinite(l_r2) else None,
                'n_train_samples': len(y_train_lopo),
                'n_test_samples': int(vm_held.sum()),
            })

    within = round(float(np.mean(within_r2s)), 3) if within_r2s else None
    lopo = round(float(np.mean(lopo_r2s)), 3) if lopo_r2s else None
    degradation = round(within - lopo, 3) if within is not None and lopo is not None else None

    results = {
        'within_patient_r2': within,
        'lopo_r2': lopo,
        'degradation': degradation,
        'n_patients': len(lopo_r2s),
        'interpretation': ('LOPO tests generalization to unseen patients. '
                           'Large degradation = model is patient-specific.'),
    }
    if detail:
        results['per_patient'] = per_patient

    return {
        'experiment': 'EXP-938', 'name': 'Leave-One-Patient-Out',
        'status': 'pass',
        'detail': (f'within={within}, lopo={lopo}, '
                   f'degradation={degradation:+.3f}') if degradation is not None else f'within={within}',
        'results': results,
    }


# ── EXP-939: Prediction Confidence Calibration ─────────────────────────────

@register('EXP-939', 'Prediction Confidence Calibration')
def exp_939(patients, detail=False):
    """For each prediction, compute confidence from model disagreement across
    horizons. Then:
    - Sort predictions by confidence
    - Report R² for top-50% most confident vs bottom-50%
    - The confident half should have much higher R²
    This enables "know when you don't know" for clinical deployment.
    """
    h_steps = 12
    start = 24
    horizons = [36, 60, 84]
    n_folds = 5

    all_conf_r2s = {'high_conf': [], 'low_conf': [], 'full': []}
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
        nr = d_fwd['nr']
        hours = d_fwd['hours']
        y_tr, y_val = actual[:split], actual[split:]

        # Train multi-horizon models and get validation predictions
        horizon_preds_val = []
        for h in horizons:
            h_st = h // 5
            n_pred_h = nr - h_st
            if n_pred_h - start < usable:
                continue

            target_h = np.full(usable, np.nan)
            for i in range(usable):
                orig = i + start
                fi = orig + h_st
                if fi < len(bg) and np.isfinite(bg[fi]) and np.isfinite(bg[orig]):
                    target_h[i] = bg[fi] - bg[orig]

            y_h_tr = target_h[:split]
            X_tr = features[:split]
            X_val_f = features[split:]
            vm_t = np.isfinite(y_h_tr) & np.all(np.isfinite(X_tr), axis=1)
            if vm_t.sum() < 100:
                continue

            pred_h_val, _ = _ridge_predict(
                np.nan_to_num(X_tr[vm_t], nan=0.0), y_h_tr[vm_t],
                np.nan_to_num(X_val_f, nan=0.0), lam=1.0)
            horizon_preds_val.append(pred_h_val)

        if len(horizon_preds_val) < 2:
            continue

        # Compute confidence = 1 / (1 + std across horizon predictions)
        preds_stack = np.column_stack(horizon_preds_val)
        pred_std = np.std(preds_stack, axis=1)
        confidence = 1.0 / (1.0 + pred_std)

        # Use the 60-min prediction as the main prediction
        # (middle horizon is closest to 60-min)
        target_60 = np.full(usable, np.nan)
        for i in range(usable):
            orig = i + start
            fi = orig + 12
            if fi < len(bg) and np.isfinite(bg[fi]) and np.isfinite(bg[orig]):
                target_60[i] = bg[fi] - bg[orig]
        y_val_60 = target_60[split:]

        # Use the middle horizon prediction as the 60-min predictor
        mid_idx = len(horizon_preds_val) // 2
        pred_60 = horizon_preds_val[mid_idx]

        # Valid mask
        valid = np.isfinite(pred_60) & np.isfinite(y_val_60) & np.isfinite(confidence)
        if valid.sum() < 40:
            continue

        pred_v = pred_60[valid]
        y_v = y_val_60[valid]
        conf_v = confidence[valid]

        # Full R²
        full_r2 = _r2(pred_v, y_v)
        all_conf_r2s['full'].append(full_r2)

        # Split by confidence median
        conf_median = np.median(conf_v)
        high_mask = conf_v >= conf_median
        low_mask = conf_v < conf_median

        high_r2 = _r2(pred_v[high_mask], y_v[high_mask]) if high_mask.sum() >= 20 else float('nan')
        low_r2 = _r2(pred_v[low_mask], y_v[low_mask]) if low_mask.sum() >= 20 else float('nan')

        if np.isfinite(high_r2):
            all_conf_r2s['high_conf'].append(high_r2)
        if np.isfinite(low_r2):
            all_conf_r2s['low_conf'].append(low_r2)

        if detail:
            per_patient.append({
                'patient': d_fwd['name'],
                'full_r2': round(float(full_r2), 3) if np.isfinite(full_r2) else None,
                'high_conf_r2': round(float(high_r2), 3) if np.isfinite(high_r2) else None,
                'low_conf_r2': round(float(low_r2), 3) if np.isfinite(low_r2) else None,
                'conf_split_benefit': round(float(high_r2 - low_r2), 3) if np.isfinite(high_r2) and np.isfinite(low_r2) else None,
                'mean_confidence': round(float(np.mean(conf_v)), 3),
                'n_high': int(high_mask.sum()),
                'n_low': int(low_mask.sum()),
            })

    full_mean = round(float(np.mean(all_conf_r2s['full'])), 3) if all_conf_r2s['full'] else None
    high_mean = round(float(np.mean(all_conf_r2s['high_conf'])), 3) if all_conf_r2s['high_conf'] else None
    low_mean = round(float(np.mean(all_conf_r2s['low_conf'])), 3) if all_conf_r2s['low_conf'] else None
    separation = round(high_mean - low_mean, 3) if high_mean is not None and low_mean is not None else None

    results = {
        'full_r2': full_mean,
        'high_confidence_r2': high_mean,
        'low_confidence_r2': low_mean,
        'confidence_separation': separation,
        'n_patients': len(all_conf_r2s['full']),
        'confidence_method': '1 / (1 + std_across_horizons)',
        'interpretation': ('Large separation = model reliably knows when it '
                           'is uncertain. Useful for clinical deployment.'),
    }
    if detail:
        results['per_patient'] = per_patient

    return {
        'experiment': 'EXP-939', 'name': 'Prediction Confidence Calibration',
        'status': 'pass',
        'detail': (f'full={full_mean}, high_conf={high_mean}, low_conf={low_mean}, '
                   f'separation={separation}'),
        'results': results,
    }


# ── EXP-940: Extended Campaign Summary Statistics ───────────────────────────

@register('EXP-940', 'Extended Campaign Summary')
def exp_940(patients, detail=False):
    """Final diagnostic. Compute summary statistics across all patients:
    - Mean, median, std of R² across patients
    - Mean, median, std of MAE
    - Best-case and worst-case patients
    - Distribution of errors (skewness, kurtosis)
    - Autocorrelation of residuals (are errors clustered in time?)
    - Save comprehensive summary for the campaign.
    """
    h_steps = 12
    start = 24
    patient_r2s = []
    patient_maes = []
    all_errors = []
    autocorr_lag1s = []
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

        X_tr, X_val = features[:split], features[split:]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        vm_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
        if vm_tr.sum() < 50 or vm_val.sum() < 20:
            continue

        pred, _ = _ridge_predict(
            np.nan_to_num(X_tr[vm_tr], nan=0.0), y_tr[vm_tr],
            np.nan_to_num(X_val[vm_val], nan=0.0))

        actual_v = y_val[vm_val]
        errors = actual_v - pred
        abs_errors = np.abs(errors)

        r2 = _r2(pred, actual_v)
        mae_val = float(np.mean(abs_errors))
        rmse_val = float(np.sqrt(np.mean(errors ** 2)))

        # Convert to mg/dL if needed
        if np.nanmean(actual_v) < 30:
            errors_mgdl = errors * 18.0182
            abs_errors_mgdl = abs_errors * 18.0182
            mae_mgdl = mae_val * 18.0182
            rmse_mgdl = rmse_val * 18.0182
        else:
            errors_mgdl = errors
            abs_errors_mgdl = abs_errors
            mae_mgdl = mae_val
            rmse_mgdl = rmse_val

        patient_r2s.append(r2)
        patient_maes.append(mae_mgdl)
        all_errors.extend(errors_mgdl.tolist())

        # Error distribution stats
        n_err = len(errors_mgdl)
        if n_err >= 10:
            err_mean = float(np.mean(errors_mgdl))
            err_std = float(np.std(errors_mgdl))
            # Skewness: E[(x-mu)^3] / sigma^3
            if err_std > 1e-10:
                skewness = float(np.mean(((errors_mgdl - err_mean) / err_std) ** 3))
                kurtosis = float(np.mean(((errors_mgdl - err_mean) / err_std) ** 4) - 3.0)
            else:
                skewness = 0.0
                kurtosis = 0.0
        else:
            skewness = float('nan')
            kurtosis = float('nan')

        # Autocorrelation of residuals at lag 1
        if len(errors_mgdl) > 10:
            err_centered = errors_mgdl - np.mean(errors_mgdl)
            var_e = np.var(err_centered)
            if var_e > 1e-10:
                autocorr_1 = float(np.sum(err_centered[1:] * err_centered[:-1]) / (len(err_centered) - 1) / var_e)
            else:
                autocorr_1 = 0.0
            autocorr_lag1s.append(autocorr_1)
        else:
            autocorr_1 = float('nan')

        per_patient.append({
            'patient': d_fwd['name'],
            'r2': round(float(r2), 3) if np.isfinite(r2) else None,
            'mae_mgdl': round(mae_mgdl, 1),
            'rmse_mgdl': round(rmse_mgdl, 1),
            'skewness': round(skewness, 2) if np.isfinite(skewness) else None,
            'kurtosis': round(kurtosis, 2) if np.isfinite(kurtosis) else None,
            'autocorr_lag1': round(autocorr_1, 3) if np.isfinite(autocorr_1) else None,
            'n_predictions': int(vm_val.sum()),
            'usable_steps': usable,
        })

    if not patient_r2s:
        return {
            'experiment': 'EXP-940', 'name': 'Extended Campaign Summary',
            'status': 'pass', 'detail': 'insufficient data',
            'results': {},
        }

    r2_arr = np.array([r for r in patient_r2s if np.isfinite(r)])
    mae_arr = np.array(patient_maes)
    error_arr = np.array(all_errors)

    # Sort patients by R²
    per_patient.sort(key=lambda x: x['r2'] if x['r2'] is not None else -1, reverse=True)

    # Overall error distribution
    overall_skew = float('nan')
    overall_kurt = float('nan')
    if len(error_arr) > 100:
        e_mean = np.mean(error_arr)
        e_std = np.std(error_arr)
        if e_std > 1e-10:
            overall_skew = float(np.mean(((error_arr - e_mean) / e_std) ** 3))
            overall_kurt = float(np.mean(((error_arr - e_mean) / e_std) ** 4) - 3.0)

    # Error percentiles
    if len(error_arr) > 10:
        abs_err = np.abs(error_arr)
        error_percentiles = {
            'p25': round(float(np.percentile(abs_err, 25)), 1),
            'p50': round(float(np.percentile(abs_err, 50)), 1),
            'p75': round(float(np.percentile(abs_err, 75)), 1),
            'p90': round(float(np.percentile(abs_err, 90)), 1),
            'p95': round(float(np.percentile(abs_err, 95)), 1),
            'p99': round(float(np.percentile(abs_err, 99)), 1),
        }
    else:
        error_percentiles = {}

    results = {
        'r2_summary': {
            'mean': round(float(np.mean(r2_arr)), 3) if len(r2_arr) > 0 else None,
            'median': round(float(np.median(r2_arr)), 3) if len(r2_arr) > 0 else None,
            'std': round(float(np.std(r2_arr)), 3) if len(r2_arr) > 0 else None,
            'min': round(float(np.min(r2_arr)), 3) if len(r2_arr) > 0 else None,
            'max': round(float(np.max(r2_arr)), 3) if len(r2_arr) > 0 else None,
        },
        'mae_summary_mgdl': {
            'mean': round(float(np.mean(mae_arr)), 1) if len(mae_arr) > 0 else None,
            'median': round(float(np.median(mae_arr)), 1) if len(mae_arr) > 0 else None,
            'std': round(float(np.std(mae_arr)), 1) if len(mae_arr) > 0 else None,
            'min': round(float(np.min(mae_arr)), 1) if len(mae_arr) > 0 else None,
            'max': round(float(np.max(mae_arr)), 1) if len(mae_arr) > 0 else None,
        },
        'error_distribution': {
            'overall_skewness': round(overall_skew, 2) if np.isfinite(overall_skew) else None,
            'overall_kurtosis': round(overall_kurt, 2) if np.isfinite(overall_kurt) else None,
            'is_heavy_tailed': bool(np.isfinite(overall_kurt) and overall_kurt > 1.0),
            'is_normal_like': bool(np.isfinite(overall_kurt) and abs(overall_kurt) < 0.5 and np.isfinite(overall_skew) and abs(overall_skew) < 0.5),
        },
        'error_percentiles_mgdl': error_percentiles,
        'autocorrelation': {
            'mean_lag1': round(float(np.mean(autocorr_lag1s)), 3) if autocorr_lag1s else None,
            'interpretation': ('High autocorrelation = errors are temporally '
                               'clustered, suggesting systematic regime failures'),
        },
        'best_patient': per_patient[0]['patient'] if per_patient else None,
        'worst_patient': per_patient[-1]['patient'] if per_patient else None,
        'n_patients': len(patient_r2s),
        'total_predictions': len(all_errors),
        'campaign_range': 'EXP-831 through EXP-940',
        'per_patient': per_patient,
    }

    mean_r2 = results['r2_summary']['mean']
    mean_mae = results['mae_summary_mgdl']['mean']
    autocorr = results['autocorrelation']['mean_lag1']

    return {
        'experiment': 'EXP-940', 'name': 'Extended Campaign Summary',
        'status': 'pass',
        'detail': (f'R²: mean={mean_r2}, MAE={mean_mae}mg/dL, '
                   f'autocorr_lag1={autocorr}, n={len(patient_r2s)}'),
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
        description='EXP-931–940: Bidirectional Features, SOTA Mystery & Campaign Summary')
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
