#!/usr/bin/env python3
"""EXP-941–950: Correct CV Stacking Variants & Campaign Finale

Building on the full campaign which established:
  - EXP-871 SOTA: R²=0.561 (backward base + correct 5-fold CV stacking)
  - Forward-looking sums: base R²≈0.533 (EXP-911)
  - Bidirectional base: R²≈0.541 (EXP-931)
  - All productive features combined: R²≈0.545 (EXP-914)
  - Forward CV stacking: R²≈0.549 (EXP-919, incorrect stacking)
  - LOPO: R²=0.145 (EXP-938)
  - Oracle ceiling: R²=0.613

Key insight: EXP-871's correct CV stacking pattern is the critical ingredient.
This batch applies the EXACT EXP-871 stacking pattern to every productive
feature set, diagnoses error regimes, improves LOPO with fine-tuning, and
runs the definitive campaign grand finale.

EXP-941: Correct CV Stacking Reproduction (sanity check → R²≈0.561)
EXP-942: Bidirectional Features + Correct CV Stacking
EXP-943: Forward-Enhanced + Correct CV Stacking
EXP-944: All Productive Features + Correct CV Stacking
EXP-945: Error Regime Detection
EXP-946: Outlier Error Analysis
EXP-947: Residual Regime Switching
EXP-948: LOPO with Fine-Tuning
EXP-949: Temporal Block Cross-Validation
EXP-950: Campaign Grand Finale
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


# ── Helpers (replicated from EXP-871) ────────────────────────────────────────

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
    """8-feature base using BACKWARD-looking sums (EXP-871 pattern)."""
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


def _build_features_base_forward(fd, hours, n_pred, h_steps):
    """8-feature base using FORWARD-looking supply/demand sums (EXP-911 pattern)."""
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


def _build_features_base_bidirectional(fd, hours, n_pred, h_steps):
    """Bidirectional base: backward + forward supply/demand sums (~14 features)."""
    bg = fd['bg']
    resid = fd['resid']
    nr = len(resid)
    n_supply = len(fd['supply'])
    features = np.zeros((n_pred, 14))
    for i in range(n_pred):
        features[i, 0] = bg[i]
        # Backward sums
        features[i, 1] = np.sum(fd['supply'][i:i+h_steps])
        features[i, 2] = np.sum(fd['demand'][i:i+h_steps])
        features[i, 3] = np.sum(fd['hepatic'][i:i+h_steps])
        # Forward sums
        features[i, 4] = np.sum(fd['supply'][i:min(i + h_steps, n_supply)])
        features[i, 5] = np.sum(fd['demand'][i:min(i + h_steps, n_supply)])
        features[i, 6] = np.sum(fd['hepatic'][i:min(i + h_steps, n_supply)])
        # Backward sums (lookback window)
        features[i, 7] = np.sum(fd['supply'][max(0, i - h_steps):i])
        features[i, 8] = np.sum(fd['demand'][max(0, i - h_steps):i])
        features[i, 9] = np.sum(fd['hepatic'][max(0, i - h_steps):i])
        features[i, 10] = resid[i] if i < nr else 0
        if hours is not None and i < len(hours):
            features[i, 11] = np.sin(2 * np.pi * hours[i] / 24.0)
            features[i, 12] = np.cos(2 * np.pi * hours[i] / 24.0)
        features[i, 13] = 1.0
    return features


def _build_enhanced_features(fd, bg, hours, n_pred, h_steps, start=24):
    """16-feature enhanced set: 8 base + 8 extra (EXP-871 pattern)."""
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


def _build_enhanced_features_bidirectional(fd, bg, hours, n_pred, h_steps,
                                           start=24):
    """Enhanced features with bidirectional supply/demand sums."""
    base = _build_features_base_bidirectional(fd, hours, n_pred, h_steps)
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


def _train_horizon_models(fd, bg, hours, nr, start, usable, split, horizons):
    """Train models at multiple horizons and return their predictions.

    Exact replica of EXP-871 pattern: for each horizon h, target is ABSOLUTE
    future BG at h+1+start, features use _build_features_base with n_pred_h=nr-h.
    """
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

        _, w_h = _ridge_predict(X_tr_h[valid_h], y_tr_h[valid_h],
                                X_tr_h[:1], lam=0.1)
        if w_h is not None:
            predictions[h] = feat_h @ w_h
            weights[h] = w_h

    return predictions, weights


def _prepare_patient(p, h_steps=12, start=24):
    """Prepare standard patient data dict (backward base). Returns None if
    insufficient data. Exact replica of EXP-871 _prepare_patient."""
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
    features, _ = _build_enhanced_features_forward(fd, bg, hours, n_pred,
                                                   h_steps, start)
    split = int(0.8 * usable)
    return {
        'fd': fd, 'bg': bg, 'hours': hours, 'nr': nr,
        'n_pred': n_pred, 'usable': usable, 'actual': actual,
        'features': features, 'split': split, 'name': p.get('name', '?'),
    }


def _prepare_patient_bidirectional(p, h_steps=12, start=24):
    """Like _prepare_patient but with bidirectional supply/demand sums."""
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
    features, _ = _build_enhanced_features_bidirectional(fd, bg, hours, n_pred,
                                                         h_steps, start)
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
        out[i] = (alpha * x[i] + (1 - alpha) * out[i - 1]
                  if np.isfinite(x[i]) else out[i - 1])
    return out


def _build_pp_features(bg_sig, supply, n_pred):
    """Post-prandial shape features."""
    supply_thresh = (np.percentile(supply[supply > 0], 75)
                     if np.sum(supply > 0) > 10 else 0.1)
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


# ── Core stacking routine (exact EXP-871 pattern) ───────────────────────────

def _cv_stacking_871(features, actual, fd, bg, hours, nr, start, usable, split,
                     horizons, n_folds=5, lam=10.0, detail_name=None):
    """Exact EXP-871 CV stacking pattern.

    1. Train horizon models on training set → naive stacking predictions.
    2. For each horizon, do 5-fold chronological CV on training set → OOF preds.
    3. Stack OOF predictions WITH original features for training meta-ridge.
    4. For validation, use full-train horizon predictions.
    5. Meta-ridge lambda = lam * 5 = 50.
    """
    y_tr, y_val = actual[:split], actual[split:]

    # Naive stacking baseline (same as EXP-862)
    h_preds, _ = _train_horizon_models(fd, bg, hours, nr, start, usable,
                                       split, horizons)
    if len(h_preds) < 3:
        return None

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

            valid_fold = (np.isfinite(y_fold_tr)
                          & np.all(np.isfinite(X_fold_tr), axis=1))
            if valid_fold.sum() < 30:
                continue

            pred_fold, _ = _ridge_predict(X_fold_tr[valid_fold],
                                          y_fold_tr[valid_fold],
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
        return None

    pred_cv, _ = _ridge_predict(cv_combined_tr[valid_tr_cv], y_tr[valid_tr_cv],
                                cv_combined_val, lam=lam * 5)
    r2_cv = _r2(pred_cv[valid_val_cv], y_val[valid_val_cv])

    return {
        'r2_naive': r2_naive, 'r2_cv': r2_cv,
        'pred_cv': pred_cv, 'valid_val_cv': valid_val_cv,
    }


# ── EXP-941: Correct CV Stacking Reproduction ───────────────────────────────

@register('EXP-941', 'Correct CV Stacking Reproduction')
def exp_941(patients, detail=False):
    """Reproduce EXP-871 EXACTLY as a sanity check. Should get R²≈0.561."""
    h_steps = 12
    lam = 10.0
    start = 24
    horizons = [1, 3, 6, 12]
    n_folds = 5

    naive_r2s, cv_stack_r2s = [], []
    per_patient = {}

    for p in patients:
        d = _prepare_patient(p, h_steps, start)
        if d is None:
            continue

        features = d['features']
        actual, split, usable = d['actual'], d['split'], d['usable']
        fd, bg, hours, nr = d['fd'], d['bg'], d['hours'], d['nr']
        y_tr, y_val = actual[:split], actual[split:]

        # Naive stacking baseline (same as EXP-862)
        h_preds, _ = _train_horizon_models(fd, bg, hours, nr, start, usable,
                                           split, horizons)
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

                valid_fold = (np.isfinite(y_fold_tr)
                              & np.all(np.isfinite(X_fold_tr), axis=1))
                if valid_fold.sum() < 30:
                    continue

                pred_fold, _ = _ridge_predict(X_fold_tr[valid_fold],
                                              y_fold_tr[valid_fold],
                                              X_fold_val, lam=0.1)
                oof_preds[h][val_idx] = pred_fold

        # Build CV-based stack features for training
        oof_stack = np.column_stack([oof_preds[h] for h in sorted(oof_preds)])
        cv_combined_tr = np.hstack([features[:split], oof_stack])

        # For validation, use full-train horizon predictions (same as naive)
        cv_combined_val = X_val_n

        valid_tr_cv = (np.isfinite(y_tr)
                       & np.all(np.isfinite(cv_combined_tr), axis=1))
        valid_val_cv = (np.isfinite(y_val)
                        & np.all(np.isfinite(cv_combined_val), axis=1))

        if valid_tr_cv.sum() < 50:
            continue

        pred_cv, _ = _ridge_predict(cv_combined_tr[valid_tr_cv],
                                    y_tr[valid_tr_cv],
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
        'experiment': 'EXP-941', 'name': 'Correct CV Stacking Reproduction',
        'status': 'pass',
        'detail': (f"naive={results['naive_stacking']}, "
                   f"cv={results['cv_stacking']}, "
                   f"Δ={results['improvement']:+.3f}") if results['improvement'] is not None else 'no data',
        'results': results,
    }


# ── EXP-942: Bidirectional Features + Correct CV Stacking ───────────────────

@register('EXP-942', 'Bidirectional + CV Stacking')
def exp_942(patients, detail=False):
    """Use bidirectional supply/demand features (~22 features enhanced), then
    apply the correct EXP-871 CV stacking pattern. Hypothesis: bidirectional
    base (R²≈0.541) + correct stacking should exceed 0.561.
    """
    h_steps = 12
    lam = 10.0
    start = 24
    horizons = [1, 3, 6, 12]
    n_folds = 5

    base_r2s, cv_stack_r2s = [], []
    per_patient = []

    for p in patients:
        d = _prepare_patient_bidirectional(p, h_steps, start)
        if d is None:
            continue

        features = d['features']
        actual, split, usable = d['actual'], d['split'], d['usable']
        fd, bg, hours, nr = d['fd'], d['bg'], d['hours'], d['nr']
        y_tr, y_val = actual[:split], actual[split:]

        # Bidirectional baseline (no stacking)
        X_tr, X_val = features[:split], features[split:]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        vm_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
        if vm_tr.sum() < 50:
            continue
        pred_base, _ = _ridge_predict(
            np.nan_to_num(X_tr[vm_tr], nan=0.0), y_tr[vm_tr],
            np.nan_to_num(X_val[vm_val], nan=0.0))
        r2_base = _r2(pred_base, y_val[vm_val])
        base_r2s.append(r2_base)

        # CV stacking with EXP-871 horizon pattern
        result = _cv_stacking_871(features, actual, fd, bg, hours, nr, start,
                                  usable, split, horizons, n_folds, lam)
        if result is None:
            continue

        r2_cv = result['r2_cv']
        if np.isfinite(r2_cv):
            cv_stack_r2s.append(r2_cv)
            if detail:
                per_patient.append({
                    'patient': d['name'],
                    'base_r2': round(float(r2_base), 3) if np.isfinite(r2_base) else None,
                    'cv_stack_r2': round(float(r2_cv), 3),
                })

    base = round(float(np.mean(base_r2s)), 3) if base_r2s else None
    stacked = round(float(np.mean(cv_stack_r2s)), 3) if cv_stack_r2s else None
    delta = round(stacked - base, 3) if stacked is not None and base is not None else None

    results = {
        'bidirectional_base': base,
        'cv_stacking': stacked,
        'improvement_over_base': delta,
        'vs_871_sota': round(stacked - 0.561, 3) if stacked is not None else None,
        'n_patients': len(cv_stack_r2s),
    }
    if detail:
        results['per_patient'] = per_patient

    return {
        'experiment': 'EXP-942', 'name': 'Bidirectional + CV Stacking',
        'status': 'pass',
        'detail': (f'bidir_base={base}, cv_stack={stacked}, '
                   f'Δbase={delta:+.3f}, vs_871={results["vs_871_sota"]:+.3f}'
                   ) if delta is not None else f'base={base}',
        'results': results,
    }


# ── EXP-943: Forward-Enhanced + Correct CV Stacking ─────────────────────────

@register('EXP-943', 'Forward + CV Stacking')
def exp_943(patients, detail=False):
    """Use forward-looking enhanced features (same as EXP-911, R²≈0.533 base),
    then apply correct EXP-871 CV stacking. Tests what forward stacking actually
    achieves with the correct implementation.
    """
    h_steps = 12
    lam = 10.0
    start = 24
    horizons = [1, 3, 6, 12]
    n_folds = 5

    base_r2s, cv_stack_r2s = [], []
    per_patient = []

    for p in patients:
        d = _prepare_patient_forward(p, h_steps, start)
        if d is None:
            continue

        features = d['features']
        actual, split, usable = d['actual'], d['split'], d['usable']
        fd, bg, hours, nr = d['fd'], d['bg'], d['hours'], d['nr']
        y_tr, y_val = actual[:split], actual[split:]

        # Forward baseline (no stacking)
        X_tr, X_val = features[:split], features[split:]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        vm_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
        if vm_tr.sum() < 50:
            continue
        pred_base, _ = _ridge_predict(
            np.nan_to_num(X_tr[vm_tr], nan=0.0), y_tr[vm_tr],
            np.nan_to_num(X_val[vm_val], nan=0.0))
        r2_base = _r2(pred_base, y_val[vm_val])
        base_r2s.append(r2_base)

        # CV stacking with EXP-871 pattern
        result = _cv_stacking_871(features, actual, fd, bg, hours, nr, start,
                                  usable, split, horizons, n_folds, lam)
        if result is None:
            continue

        r2_cv = result['r2_cv']
        if np.isfinite(r2_cv):
            cv_stack_r2s.append(r2_cv)
            if detail:
                per_patient.append({
                    'patient': d['name'],
                    'base_r2': round(float(r2_base), 3) if np.isfinite(r2_base) else None,
                    'cv_stack_r2': round(float(r2_cv), 3),
                })

    base = round(float(np.mean(base_r2s)), 3) if base_r2s else None
    stacked = round(float(np.mean(cv_stack_r2s)), 3) if cv_stack_r2s else None
    delta = round(stacked - base, 3) if stacked is not None and base is not None else None

    results = {
        'forward_base': base,
        'cv_stacking': stacked,
        'improvement_over_base': delta,
        'vs_871_sota': round(stacked - 0.561, 3) if stacked is not None else None,
        'n_patients': len(cv_stack_r2s),
    }
    if detail:
        results['per_patient'] = per_patient

    return {
        'experiment': 'EXP-943', 'name': 'Forward + CV Stacking',
        'status': 'pass',
        'detail': (f'fwd_base={base}, cv_stack={stacked}, '
                   f'Δbase={delta:+.3f}, vs_871={results["vs_871_sota"]:+.3f}'
                   ) if delta is not None else f'base={base}',
        'results': results,
    }


# ── EXP-944: All Productive Features + Correct CV Stacking ──────────────────

@register('EXP-944', 'All Features + CV Stacking')
def exp_944(patients, detail=False):
    """Use forward base + shape features + causal EMA + PK derivatives
    (~33 features, R²≈0.545 base from EXP-914), then apply correct CV stacking.
    """
    h_steps = 12
    lam = 10.0
    start = 24
    horizons = [1, 3, 6, 12]
    n_folds = 5

    base_r2s, cv_stack_r2s = [], []
    per_patient = []

    for p in patients:
        d_fwd = _prepare_patient_forward(p, h_steps, start)
        if d_fwd is None:
            continue

        fd = d_fwd['fd']
        bg = d_fwd['bg']
        actual = d_fwd['actual']
        split = d_fwd['split']
        usable = d_fwd['usable']
        n_pred = d_fwd['n_pred']
        nr = d_fwd['nr']
        hours = d_fwd['hours']
        y_tr, y_val = actual[:split], actual[split:]

        # Build all productive features (same as EXP-914)
        bg_sig = bg[:n_pred].astype(float)
        bg_sig[~np.isfinite(bg_sig)] = np.nanmean(bg_sig)
        supply = fd['supply'][:n_pred].astype(float)
        demand = fd['demand'][:n_pred].astype(float)
        net = supply - demand

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

        features = np.hstack([d_fwd['features'], extra])

        # Base R² (no stacking)
        X_tr, X_val = features[:split], features[split:]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        vm_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
        if vm_tr.sum() < 50:
            continue
        pred_base, _ = _ridge_predict(
            np.nan_to_num(X_tr[vm_tr], nan=0.0), y_tr[vm_tr],
            np.nan_to_num(X_val[vm_val], nan=0.0))
        r2_base = _r2(pred_base, y_val[vm_val])
        base_r2s.append(r2_base)

        # CV stacking with EXP-871 pattern
        result = _cv_stacking_871(features, actual, fd, bg, hours, nr, start,
                                  usable, split, horizons, n_folds, lam)
        if result is None:
            continue

        r2_cv = result['r2_cv']
        if np.isfinite(r2_cv):
            cv_stack_r2s.append(r2_cv)
            if detail:
                per_patient.append({
                    'patient': d_fwd['name'],
                    'base_r2': round(float(r2_base), 3) if np.isfinite(r2_base) else None,
                    'cv_stack_r2': round(float(r2_cv), 3),
                })

    base = round(float(np.mean(base_r2s)), 3) if base_r2s else None
    stacked = round(float(np.mean(cv_stack_r2s)), 3) if cv_stack_r2s else None
    delta = round(stacked - base, 3) if stacked is not None and base is not None else None

    results = {
        'all_features_base': base,
        'cv_stacking': stacked,
        'improvement_over_base': delta,
        'vs_871_sota': round(stacked - 0.561, 3) if stacked is not None else None,
        'n_features': features.shape[1] if cv_stack_r2s else None,
        'n_patients': len(cv_stack_r2s),
    }
    if detail:
        results['per_patient'] = per_patient

    return {
        'experiment': 'EXP-944', 'name': 'All Features + CV Stacking',
        'status': 'pass',
        'detail': (f'all_base={base}, cv_stack={stacked}, '
                   f'Δbase={delta:+.3f}, vs_871={results["vs_871_sota"]:+.3f}'
                   ) if delta is not None else f'base={base}',
        'results': results,
    }


# ── EXP-945: Error Regime Detection ─────────────────────────────────────────

@register('EXP-945', 'Error Regime Detection')
def exp_945(patients, detail=False):
    """Use running prediction error to detect error regimes.

    1. Train base model, compute running error (EMA of |error| over last 12 steps)
    2. Classify into high-error / low-error regimes via median split
    3. Report R² for each regime
    4. Use running_error_regime as additional feature
    """
    h_steps = 12
    start = 24

    base_r2s, regime_feat_r2s = [], []
    high_regime_r2s, low_regime_r2s = [], []
    per_patient = []

    for p in patients:
        d = _prepare_patient(p, h_steps, start)
        if d is None:
            continue

        features = d['features']
        actual, split, usable = d['actual'], d['split'], d['usable']
        bg = d['bg']
        y_tr, y_val = actual[:split], actual[split:]

        X_tr, X_val = features[:split], features[split:]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        vm_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
        if vm_tr.sum() < 50 or vm_val.sum() < 30:
            continue

        # Train base model
        pred_tr, w_base = _ridge_predict(
            np.nan_to_num(X_tr[vm_tr], nan=0.0), y_tr[vm_tr],
            np.nan_to_num(X_tr, nan=0.0))
        if w_base is None:
            continue

        # Compute training errors
        train_errors = np.abs(y_tr - pred_tr)
        train_errors[~np.isfinite(train_errors)] = 0.0

        # Running error EMA (α for ~12-step window)
        alpha_ema = 2.0 / (12 + 1)
        running_err = _causal_ema(train_errors, alpha_ema)

        # Compute for validation too: full predictions then running error
        all_feats = np.nan_to_num(features, nan=0.0)
        all_pred = all_feats @ w_base
        all_errors = np.abs(actual - all_pred)
        all_errors[~np.isfinite(all_errors)] = 0.0
        running_err_all = _causal_ema(all_errors, alpha_ema)

        # Median split on training running error for threshold
        running_err_tr = running_err_all[:split]
        threshold = np.median(running_err_tr[running_err_tr > 0])
        if threshold <= 0:
            threshold = np.mean(running_err_tr)

        # Regime labels for validation
        running_err_val = running_err_all[split:]
        high_mask = running_err_val >= threshold
        low_mask = ~high_mask

        # R² by regime
        pred_val = np.nan_to_num(X_val, nan=0.0) @ w_base
        high_valid = vm_val & high_mask
        low_valid = vm_val & low_mask

        r2_base = _r2(pred_val[vm_val], y_val[vm_val])
        base_r2s.append(r2_base)

        r2_high = _r2(pred_val[high_valid], y_val[high_valid])
        r2_low = _r2(pred_val[low_valid], y_val[low_valid])
        if np.isfinite(r2_high):
            high_regime_r2s.append(r2_high)
        if np.isfinite(r2_low):
            low_regime_r2s.append(r2_low)

        # Add running error as feature
        regime_feat = running_err_all.reshape(-1, 1)
        regime_binary = (running_err_all >= threshold).astype(float).reshape(-1, 1)
        features_aug = np.hstack([features, regime_feat, regime_binary])

        X_tr_aug, X_val_aug = features_aug[:split], features_aug[split:]
        vm_tr_aug = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_aug), axis=1)
        vm_val_aug = np.isfinite(y_val) & np.all(np.isfinite(X_val_aug), axis=1)

        if vm_tr_aug.sum() < 50:
            continue

        pred_aug, _ = _ridge_predict(
            np.nan_to_num(X_tr_aug[vm_tr_aug], nan=0.0), y_tr[vm_tr_aug],
            np.nan_to_num(X_val_aug[vm_val_aug], nan=0.0))
        r2_aug = _r2(pred_aug, y_val[vm_val_aug])
        if np.isfinite(r2_aug):
            regime_feat_r2s.append(r2_aug)

        if detail:
            per_patient.append({
                'patient': d['name'],
                'base_r2': round(float(r2_base), 3) if np.isfinite(r2_base) else None,
                'high_regime_r2': round(float(r2_high), 3) if np.isfinite(r2_high) else None,
                'low_regime_r2': round(float(r2_low), 3) if np.isfinite(r2_low) else None,
                'regime_feat_r2': round(float(r2_aug), 3) if np.isfinite(r2_aug) else None,
                'n_high': int(high_valid.sum()),
                'n_low': int(low_valid.sum()),
            })

    base = round(float(np.mean(base_r2s)), 3) if base_r2s else None
    high = round(float(np.mean(high_regime_r2s)), 3) if high_regime_r2s else None
    low = round(float(np.mean(low_regime_r2s)), 3) if low_regime_r2s else None
    with_feat = round(float(np.mean(regime_feat_r2s)), 3) if regime_feat_r2s else None
    delta = round(with_feat - base, 3) if with_feat is not None and base is not None else None

    results = {
        'base_r2': base,
        'high_error_regime_r2': high,
        'low_error_regime_r2': low,
        'with_regime_feature': with_feat,
        'improvement': delta,
        'n_patients': len(base_r2s),
        'interpretation': ('High-error regime typically near meals/rapid changes. '
                           'R² gap between regimes indicates exploitable structure.'),
    }
    if detail:
        results['per_patient'] = per_patient

    return {
        'experiment': 'EXP-945', 'name': 'Error Regime Detection',
        'status': 'pass',
        'detail': (f'base={base}, high_regime={high}, low_regime={low}, '
                   f'+regime_feat={with_feat}, Δ={delta:+.3f}') if delta is not None else f'base={base}',
        'results': results,
    }


# ── EXP-946: Outlier Error Analysis ─────────────────────────────────────────

@register('EXP-946', 'Outlier Error Analysis')
def exp_946(patients, detail=False):
    """Analyze P90+ error cases (worst 10% predictions).

    For each patient: identify predictions with error > P90, characterize
    by time-of-day, BG level, BG velocity, and supply/demand activity.
    Compare outlier vs typical error characteristics.
    """
    h_steps = 12
    start = 24

    all_outlier_chars = {
        'bg_level': [], 'bg_velocity': [], 'supply_activity': [],
        'demand_activity': [], 'abs_error': [],
    }
    all_typical_chars = {
        'bg_level': [], 'bg_velocity': [], 'supply_activity': [],
        'demand_activity': [], 'abs_error': [],
    }
    tod_outlier_counts = np.zeros(24)
    tod_typical_counts = np.zeros(24)
    per_patient = []

    for p in patients:
        d = _prepare_patient(p, h_steps, start)
        if d is None:
            continue

        features = d['features']
        actual, split, usable = d['actual'], d['split'], d['usable']
        fd, bg, hours, nr = d['fd'], d['bg'], d['hours'], d['nr']
        y_tr, y_val = actual[:split], actual[split:]

        X_tr, X_val = features[:split], features[split:]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        vm_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
        if vm_tr.sum() < 50 or vm_val.sum() < 30:
            continue

        pred_val, _ = _ridge_predict(
            np.nan_to_num(X_tr[vm_tr], nan=0.0), y_tr[vm_tr],
            np.nan_to_num(X_val[vm_val], nan=0.0))
        y_valid = y_val[vm_val]
        errors = np.abs(y_valid - pred_val)

        p90 = np.percentile(errors, 90)
        outlier_mask = errors >= p90
        typical_mask = errors < p90

        val_offset = start + split
        val_indices = np.where(vm_val)[0]

        n_outliers = 0
        n_typical = 0
        patient_outlier_bg = []
        patient_typical_bg = []

        for j in range(len(val_indices)):
            orig = val_offset + val_indices[j]
            # BG level
            bg_level = bg[orig] if orig < len(bg) else np.nan
            # BG velocity (5-min delta)
            bg_vel = (bg[orig] - bg[orig - 1]) if orig >= 1 and orig < len(bg) else 0.0
            # Supply/demand activity (forward sum)
            sup_act = np.sum(fd['supply'][orig:min(orig + h_steps, fd['n'])])
            dem_act = np.sum(fd['demand'][orig:min(orig + h_steps, fd['n'])])
            # Time of day
            tod = int(hours[orig]) % 24 if hours is not None and orig < len(hours) else 0

            err = float(errors[j])

            if outlier_mask[j]:
                all_outlier_chars['bg_level'].append(float(bg_level))
                all_outlier_chars['bg_velocity'].append(float(bg_vel))
                all_outlier_chars['supply_activity'].append(float(sup_act))
                all_outlier_chars['demand_activity'].append(float(dem_act))
                all_outlier_chars['abs_error'].append(err)
                tod_outlier_counts[tod] += 1
                n_outliers += 1
                patient_outlier_bg.append(float(bg_level))
            else:
                all_typical_chars['bg_level'].append(float(bg_level))
                all_typical_chars['bg_velocity'].append(float(bg_vel))
                all_typical_chars['supply_activity'].append(float(sup_act))
                all_typical_chars['demand_activity'].append(float(dem_act))
                all_typical_chars['abs_error'].append(err)
                tod_typical_counts[tod] += 1
                n_typical += 1
                patient_typical_bg.append(float(bg_level))

        if detail and n_outliers > 0:
            per_patient.append({
                'patient': d['name'],
                'n_outliers': n_outliers,
                'n_typical': n_typical,
                'outlier_mean_bg': round(float(np.mean(patient_outlier_bg)), 1),
                'typical_mean_bg': round(float(np.mean(patient_typical_bg)), 1),
                'p90_threshold': round(float(p90), 1),
            })

    def _safe_mean(lst):
        return round(float(np.mean(lst)), 2) if lst else None

    def _safe_std(lst):
        return round(float(np.std(lst)), 2) if lst else None

    # Peak outlier hours
    if tod_outlier_counts.sum() > 0:
        tod_frac = tod_outlier_counts / (tod_outlier_counts + tod_typical_counts + 1e-10)
        peak_hours = list(np.argsort(tod_frac)[-3:][::-1])
    else:
        peak_hours = []

    results = {
        'outlier_characteristics': {
            'mean_bg_level': _safe_mean(all_outlier_chars['bg_level']),
            'std_bg_level': _safe_std(all_outlier_chars['bg_level']),
            'mean_bg_velocity': _safe_mean(all_outlier_chars['bg_velocity']),
            'std_bg_velocity': _safe_std(all_outlier_chars['bg_velocity']),
            'mean_supply_activity': _safe_mean(all_outlier_chars['supply_activity']),
            'mean_demand_activity': _safe_mean(all_outlier_chars['demand_activity']),
            'mean_abs_error': _safe_mean(all_outlier_chars['abs_error']),
        },
        'typical_characteristics': {
            'mean_bg_level': _safe_mean(all_typical_chars['bg_level']),
            'std_bg_level': _safe_std(all_typical_chars['bg_level']),
            'mean_bg_velocity': _safe_mean(all_typical_chars['bg_velocity']),
            'std_bg_velocity': _safe_std(all_typical_chars['bg_velocity']),
            'mean_supply_activity': _safe_mean(all_typical_chars['supply_activity']),
            'mean_demand_activity': _safe_mean(all_typical_chars['demand_activity']),
            'mean_abs_error': _safe_mean(all_typical_chars['abs_error']),
        },
        'peak_outlier_hours': peak_hours,
        'n_outliers': len(all_outlier_chars['abs_error']),
        'n_typical': len(all_typical_chars['abs_error']),
    }
    if detail:
        results['per_patient'] = per_patient

    outlier_bg = _safe_mean(all_outlier_chars['bg_level'])
    typical_bg = _safe_mean(all_typical_chars['bg_level'])
    outlier_vel = _safe_mean(all_outlier_chars['bg_velocity'])
    typical_vel = _safe_mean(all_typical_chars['bg_velocity'])
    outlier_err = _safe_mean(all_outlier_chars['abs_error'])
    typical_err = _safe_mean(all_typical_chars['abs_error'])

    return {
        'experiment': 'EXP-946', 'name': 'Outlier Error Analysis',
        'status': 'pass',
        'detail': (f'outlier_bg={outlier_bg} vs typical_bg={typical_bg}, '
                   f'outlier_vel={outlier_vel} vs typical_vel={typical_vel}, '
                   f'outlier_err={outlier_err} vs typical_err={typical_err}, '
                   f'peak_hours={peak_hours}'),
        'results': results,
    }


# ── EXP-947: Residual Regime Switching ──────────────────────────────────────

@register('EXP-947', 'Residual Regime Switching')
def exp_947(patients, detail=False):
    """Build a 2-regime model:
    1. Train global ridge → compute residuals
    2. Split residuals into positive bias / negative bias regimes
    3. Train separate ridge models for each regime
    4. At prediction time, predict regime from features, use appropriate model
    """
    h_steps = 12
    start = 24

    single_r2s, regime_r2s = [], []
    per_patient = []

    for p in patients:
        d = _prepare_patient(p, h_steps, start)
        if d is None:
            continue

        features = d['features']
        actual, split = d['actual'], d['split']
        y_tr, y_val = actual[:split], actual[split:]

        X_tr, X_val = features[:split], features[split:]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        vm_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
        if vm_tr.sum() < 100 or vm_val.sum() < 30:
            continue

        X_tr_c = np.nan_to_num(X_tr[vm_tr], nan=0.0)
        y_tr_c = y_tr[vm_tr]
        X_val_c = np.nan_to_num(X_val[vm_val], nan=0.0)
        y_val_c = y_val[vm_val]

        # Step 1: Train global model
        pred_global_tr, w_global = _ridge_predict(X_tr_c, y_tr_c, X_tr_c)
        if w_global is None:
            continue
        pred_global_val = X_val_c @ w_global
        r2_single = _r2(pred_global_val, y_val_c)
        single_r2s.append(r2_single)

        # Step 2: Compute training residuals → split into regimes
        residuals_tr = y_tr_c - pred_global_tr
        pos_mask_tr = residuals_tr >= 0  # under-predicting regime
        neg_mask_tr = residuals_tr < 0   # over-predicting regime

        if pos_mask_tr.sum() < 30 or neg_mask_tr.sum() < 30:
            regime_r2s.append(r2_single)
            continue

        # Step 3: Train separate models per regime
        _, w_pos = _ridge_predict(X_tr_c[pos_mask_tr], y_tr_c[pos_mask_tr],
                                  X_tr_c[:1], lam=1.0)
        _, w_neg = _ridge_predict(X_tr_c[neg_mask_tr], y_tr_c[neg_mask_tr],
                                  X_tr_c[:1], lam=1.0)
        if w_pos is None or w_neg is None:
            regime_r2s.append(r2_single)
            continue

        # Step 4: Predict regime for validation points
        # Use global model residual sign as regime predictor:
        # Train a regime classifier on training features → residual sign
        regime_labels = pos_mask_tr.astype(float)
        _, w_regime = _ridge_predict(X_tr_c, regime_labels, X_tr_c[:1], lam=1.0)
        if w_regime is None:
            regime_r2s.append(r2_single)
            continue

        regime_prob_val = X_val_c @ w_regime
        pred_pos = X_val_c @ w_pos
        pred_neg = X_val_c @ w_neg

        # Soft blend based on regime probability
        regime_prob_val = np.clip(regime_prob_val, 0, 1)
        pred_regime = regime_prob_val * pred_pos + (1 - regime_prob_val) * pred_neg

        r2_regime = _r2(pred_regime, y_val_c)
        if np.isfinite(r2_regime):
            regime_r2s.append(r2_regime)
        else:
            regime_r2s.append(r2_single)

        if detail:
            per_patient.append({
                'patient': d['name'],
                'single_r2': round(float(r2_single), 3) if np.isfinite(r2_single) else None,
                'regime_r2': round(float(r2_regime), 3) if np.isfinite(r2_regime) else None,
                'n_pos_train': int(pos_mask_tr.sum()),
                'n_neg_train': int(neg_mask_tr.sum()),
            })

    single = round(float(np.mean(single_r2s)), 3) if single_r2s else None
    regime = round(float(np.mean(regime_r2s)), 3) if regime_r2s else None
    delta = round(regime - single, 3) if regime is not None and single is not None else None

    results = {
        'single_model_r2': single,
        'regime_switching_r2': regime,
        'improvement': delta,
        'n_patients': len(single_r2s),
    }
    if detail:
        results['per_patient'] = per_patient

    return {
        'experiment': 'EXP-947', 'name': 'Residual Regime Switching',
        'status': 'pass',
        'detail': (f'single={single}, regime={regime}, '
                   f'Δ={delta:+.3f}') if delta is not None else f'single={single}',
        'results': results,
    }


# ── EXP-948: LOPO with Fine-Tuning ──────────────────────────────────────────

@register('EXP-948', 'LOPO with Fine-Tuning')
def exp_948(patients, detail=False):
    """Improve LOPO (EXP-938: R²=0.145):
    1. Train pooled model on N-1 patients
    2. Fine-tune on first 20% of held-out patient (simulate cold-start)
    3. Evaluate on remaining 80%
    Compare: pure LOPO (no fine-tune), pure within-patient, and fine-tuned.
    """
    h_steps = 12
    start = 24
    fine_tune_frac = 0.2

    # Pre-prepare all patients
    all_data = []
    for p in patients:
        d = _prepare_patient_forward(p, h_steps, start)
        if d is None:
            continue
        features = d['features']
        actual = d['actual']
        vm = np.isfinite(actual) & np.all(np.isfinite(features), axis=1)
        if vm.sum() < 100:
            continue
        all_data.append({
            'name': d['name'],
            'features': np.nan_to_num(features[vm], nan=0.0),
            'actual': actual[vm],
            'usable': d['usable'],
            'split': d['split'],
            'features_raw': features,
            'actual_raw': actual,
        })

    if len(all_data) < 3:
        return {
            'experiment': 'EXP-948', 'name': 'LOPO with Fine-Tuning',
            'status': 'pass', 'detail': 'insufficient patients',
            'results': {},
        }

    lopo_r2s, finetune_r2s, within_r2s = [], [], []
    per_patient = []

    for hold_idx in range(len(all_data)):
        held = all_data[hold_idx]

        # Pool training data from other patients
        train_X_parts, train_y_parts = [], []
        for j in range(len(all_data)):
            if j == hold_idx:
                continue
            train_X_parts.append(all_data[j]['features'])
            train_y_parts.append(all_data[j]['actual'])

        X_train_pool = np.vstack(train_X_parts)
        y_train_pool = np.concatenate(train_y_parts)

        # Held-out patient: split into fine-tune (20%) and eval (80%)
        n_held = len(held['actual'])
        ft_split = int(fine_tune_frac * n_held)
        if ft_split < 30 or (n_held - ft_split) < 30:
            continue

        X_held_ft = held['features'][:ft_split]
        y_held_ft = held['actual'][:ft_split]
        X_held_eval = held['features'][ft_split:]
        y_held_eval = held['actual'][ft_split:]

        # Pure LOPO: train on pool, evaluate on held-out eval portion
        pred_lopo, _ = _ridge_predict(X_train_pool, y_train_pool,
                                      X_held_eval, lam=1.0)
        r2_lopo = _r2(pred_lopo, y_held_eval)

        # Fine-tuned: pool + held-out fine-tune portion
        X_ft_combined = np.vstack([X_train_pool, X_held_ft])
        y_ft_combined = np.concatenate([y_train_pool, y_held_ft])
        pred_ft, _ = _ridge_predict(X_ft_combined, y_ft_combined,
                                    X_held_eval, lam=1.0)
        r2_ft = _r2(pred_ft, y_held_eval)

        # Pure within-patient: train on fine-tune portion only
        pred_within, _ = _ridge_predict(X_held_ft, y_held_ft,
                                        X_held_eval, lam=1.0)
        r2_within = _r2(pred_within, y_held_eval)

        if np.isfinite(r2_lopo):
            lopo_r2s.append(r2_lopo)
        if np.isfinite(r2_ft):
            finetune_r2s.append(r2_ft)
        if np.isfinite(r2_within):
            within_r2s.append(r2_within)

        if detail:
            per_patient.append({
                'patient': held['name'],
                'lopo_r2': round(float(r2_lopo), 3) if np.isfinite(r2_lopo) else None,
                'finetune_r2': round(float(r2_ft), 3) if np.isfinite(r2_ft) else None,
                'within_r2': round(float(r2_within), 3) if np.isfinite(r2_within) else None,
                'n_finetune': ft_split,
                'n_eval': n_held - ft_split,
                'n_pool': len(y_train_pool),
            })

    lopo = round(float(np.mean(lopo_r2s)), 3) if lopo_r2s else None
    ft = round(float(np.mean(finetune_r2s)), 3) if finetune_r2s else None
    within = round(float(np.mean(within_r2s)), 3) if within_r2s else None
    ft_vs_lopo = round(ft - lopo, 3) if ft is not None and lopo is not None else None
    ft_vs_within = round(ft - within, 3) if ft is not None and within is not None else None

    results = {
        'pure_lopo_r2': lopo,
        'finetune_r2': ft,
        'within_patient_r2': within,
        'finetune_vs_lopo': ft_vs_lopo,
        'finetune_vs_within': ft_vs_within,
        'fine_tune_fraction': fine_tune_frac,
        'n_patients': len(lopo_r2s),
        'interpretation': ('Fine-tuning adds held-out patient data to pooled model. '
                           'Best of both worlds: population prior + individual calibration.'),
    }
    if detail:
        results['per_patient'] = per_patient

    return {
        'experiment': 'EXP-948', 'name': 'LOPO with Fine-Tuning',
        'status': 'pass',
        'detail': (f'lopo={lopo}, finetune={ft}, within_20pct={within}, '
                   f'ft_vs_lopo={ft_vs_lopo:+.3f}, '
                   f'ft_vs_within={ft_vs_within:+.3f}'
                   ) if ft_vs_lopo is not None else f'lopo={lopo}',
        'results': results,
    }


# ── EXP-949: Temporal Block Cross-Validation ────────────────────────────────

@register('EXP-949', 'Temporal Block CV')
def exp_949(patients, detail=False):
    """Standard 80/20 split may overstate performance if there are long-range
    dependencies. Test 5-fold temporal block CV:
    - Each fold is a contiguous time block
    - Train on 4 blocks, validate on 1
    Report mean and std of R² across folds. Compare to standard 80/20 split.
    """
    h_steps = 12
    start = 24
    n_folds = 5

    standard_r2s, block_cv_means, block_cv_stds = [], [], []
    per_patient = []

    for p in patients:
        d = _prepare_patient(p, h_steps, start)
        if d is None:
            continue

        features = d['features']
        actual, split, usable = d['actual'], d['split'], d['usable']
        y_tr, y_val = actual[:split], actual[split:]

        X_tr, X_val = features[:split], features[split:]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        vm_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
        if vm_tr.sum() < 50 or vm_val.sum() < 20:
            continue

        # Standard 80/20 R²
        pred_std, _ = _ridge_predict(
            np.nan_to_num(X_tr[vm_tr], nan=0.0), y_tr[vm_tr],
            np.nan_to_num(X_val[vm_val], nan=0.0))
        r2_std = _r2(pred_std, y_val[vm_val])
        standard_r2s.append(r2_std)

        # 5-fold temporal block CV on ALL data (not just train)
        all_features = np.nan_to_num(features, nan=0.0)
        all_actual = actual
        n_total = len(all_actual)
        block_size = n_total // n_folds

        fold_r2s = []
        for fold_i in range(n_folds):
            val_start = fold_i * block_size
            val_end = min((fold_i + 1) * block_size, n_total)
            if fold_i == n_folds - 1:
                val_end = n_total

            train_idx = np.concatenate([np.arange(0, val_start),
                                        np.arange(val_end, n_total)])
            val_idx = np.arange(val_start, val_end)

            if len(train_idx) < 50 or len(val_idx) < 20:
                continue

            X_fold_tr = all_features[train_idx]
            y_fold_tr = all_actual[train_idx]
            X_fold_val = all_features[val_idx]
            y_fold_val = all_actual[val_idx]

            vm_ft = np.isfinite(y_fold_tr) & np.all(np.isfinite(X_fold_tr), axis=1)
            vm_fv = np.isfinite(y_fold_val) & np.all(np.isfinite(X_fold_val), axis=1)

            if vm_ft.sum() < 30 or vm_fv.sum() < 10:
                continue

            pred_fold, _ = _ridge_predict(X_fold_tr[vm_ft], y_fold_tr[vm_ft],
                                          X_fold_val[vm_fv])
            r2_fold = _r2(pred_fold, y_fold_val[vm_fv])
            if np.isfinite(r2_fold):
                fold_r2s.append(r2_fold)

        if len(fold_r2s) >= 3:
            mean_cv = float(np.mean(fold_r2s))
            std_cv = float(np.std(fold_r2s))
            block_cv_means.append(mean_cv)
            block_cv_stds.append(std_cv)

            if detail:
                per_patient.append({
                    'patient': d['name'],
                    'standard_r2': round(float(r2_std), 3) if np.isfinite(r2_std) else None,
                    'block_cv_mean': round(mean_cv, 3),
                    'block_cv_std': round(std_cv, 3),
                    'fold_r2s': [round(r, 3) for r in fold_r2s],
                    'overstatement': round(float(r2_std) - mean_cv, 3) if np.isfinite(r2_std) else None,
                })

    std_mean = round(float(np.mean(standard_r2s)), 3) if standard_r2s else None
    cv_mean = round(float(np.mean(block_cv_means)), 3) if block_cv_means else None
    cv_std_mean = round(float(np.mean(block_cv_stds)), 3) if block_cv_stds else None
    overstatement = round(std_mean - cv_mean, 3) if std_mean is not None and cv_mean is not None else None

    results = {
        'standard_8020_r2': std_mean,
        'block_cv_mean_r2': cv_mean,
        'block_cv_mean_std': cv_std_mean,
        'overstatement': overstatement,
        'n_folds': n_folds,
        'n_patients': len(block_cv_means),
        'interpretation': ('Positive overstatement means 80/20 is optimistic. '
                           'High std across folds indicates temporal non-stationarity.'),
    }
    if detail:
        results['per_patient'] = per_patient

    return {
        'experiment': 'EXP-949', 'name': 'Temporal Block CV',
        'status': 'pass',
        'detail': (f'standard={std_mean}, block_cv={cv_mean}±{cv_std_mean}, '
                   f'overstatement={overstatement:+.3f}'
                   ) if overstatement is not None else f'standard={std_mean}',
        'results': results,
    }


# ── EXP-950: Campaign Grand Finale ──────────────────────────────────────────

@register('EXP-950', 'Campaign Grand Finale')
def exp_950(patients, detail=False):
    """The definitive experiment combining ALL productive signals with correct
    CV stacking:
    1. Bidirectional features (forward + backward sums)
    2. All shape features (postprandial + IOB)
    3. Causal EMA
    4. ToD features (already in base)
    5. Correct CV stacking from EXP-871 pattern
    6. 5-fold chronological CV with horizons [1, 3, 6, 12]
    7. Meta-ridge lam=50

    This SHOULD set the new campaign SOTA.
    """
    h_steps = 12
    lam = 10.0
    start = 24
    horizons = [1, 3, 6, 12]
    n_folds = 5

    backward_base_r2s, forward_base_r2s = [], []
    grand_base_r2s, grand_stack_r2s = [], []
    per_patient = []

    for p in patients:
        # Backward baseline for comparison
        d_back = _prepare_patient(p, h_steps, start)
        if d_back is None:
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
        X_tr_bk = d_back['features'][:split]
        X_val_bk = d_back['features'][split:]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_bk), axis=1)
        vm_val = np.isfinite(y_val) & np.all(np.isfinite(X_val_bk), axis=1)
        if vm_tr.sum() < 50:
            continue
        pred_bk, _ = _ridge_predict(
            np.nan_to_num(X_tr_bk[vm_tr], nan=0.0), y_tr[vm_tr],
            np.nan_to_num(X_val_bk[vm_val], nan=0.0))
        bk_r2 = _r2(pred_bk, y_val[vm_val])
        backward_base_r2s.append(bk_r2)

        # Build grand feature set: bidirectional base + all extras
        bg_sig = bg[:n_pred].astype(float)
        bg_sig[~np.isfinite(bg_sig)] = np.nanmean(bg_sig)
        supply = fd['supply'][:n_pred].astype(float)
        demand = fd['demand'][:n_pred].astype(float)
        net = supply - demand
        n_supply = len(fd['supply'])

        # Bidirectional base (14 features → enhanced to 22)
        d_bidir = _prepare_patient_bidirectional(p, h_steps, start)
        if d_bidir is None:
            continue
        bidir_features = d_bidir['features']

        # PK derivatives (5 features)
        d_supply = np.gradient(supply)
        d_demand = np.gradient(demand)
        d2_supply = np.gradient(d_supply)
        d2_demand = np.gradient(d_demand)
        d_net = np.gradient(net)

        # Post-prandial shape (5 features)
        pp_feats = _build_pp_features(bg_sig, supply, n_pred)

        # IOB shape (5 features)
        iob_feats = _build_iob_features(demand, n_pred)

        # Causal EMAs (2 features)
        ema_1h = _causal_ema(bg_sig, 2.0 / (12 + 1))
        ema_4h = _causal_ema(bg_sig, 2.0 / (48 + 1))

        # Assemble extra features
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

        grand_features = np.hstack([bidir_features, extra])
        n_grand_feats = grand_features.shape[1]

        # Grand base R² (no stacking)
        X_tr_g = grand_features[:split]
        X_val_g = grand_features[split:]
        vm_tr_g = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_g), axis=1)
        vm_val_g = np.isfinite(y_val) & np.all(np.isfinite(X_val_g), axis=1)
        if vm_tr_g.sum() < 50:
            continue
        pred_grand_base, _ = _ridge_predict(
            np.nan_to_num(X_tr_g[vm_tr_g], nan=0.0), y_tr[vm_tr_g],
            np.nan_to_num(X_val_g[vm_val_g], nan=0.0))
        r2_grand_base = _r2(pred_grand_base, y_val[vm_val_g])
        grand_base_r2s.append(r2_grand_base)

        # === Correct EXP-871 CV Stacking ===

        # Step 1: Train horizon models using backward base (EXP-871 pattern)
        h_preds, _ = _train_horizon_models(fd, bg, hours, nr, start, usable,
                                           split, horizons)
        if len(h_preds) < 3:
            continue

        # Naive stacking features for validation
        stack_feats = np.column_stack([h_preds[h] for h in sorted(h_preds)])
        combined_naive = np.hstack([grand_features, stack_feats])
        X_val_n = combined_naive[split:]

        # Step 2: 5-fold chronological CV for OOF predictions
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

                valid_fold = (np.isfinite(y_fold_tr)
                              & np.all(np.isfinite(X_fold_tr), axis=1))
                if valid_fold.sum() < 30:
                    continue

                pred_fold, _ = _ridge_predict(X_fold_tr[valid_fold],
                                              y_fold_tr[valid_fold],
                                              X_fold_val, lam=0.1)
                oof_preds[h][val_idx] = pred_fold

        # Step 3: Build CV-based stack features for training
        oof_stack = np.column_stack([oof_preds[h] for h in sorted(oof_preds)])
        cv_combined_tr = np.hstack([grand_features[:split], oof_stack])

        # For validation, use full-train horizon predictions
        cv_combined_val = X_val_n

        valid_tr_cv = (np.isfinite(y_tr)
                       & np.all(np.isfinite(cv_combined_tr), axis=1))
        valid_val_cv = (np.isfinite(y_val)
                        & np.all(np.isfinite(cv_combined_val), axis=1))

        if valid_tr_cv.sum() < 50:
            continue

        # Step 4: Meta-ridge with lam * 5 = 50
        pred_cv, _ = _ridge_predict(cv_combined_tr[valid_tr_cv],
                                    y_tr[valid_tr_cv],
                                    cv_combined_val, lam=lam * 5)
        r2_grand_stack = _r2(pred_cv[valid_val_cv], y_val[valid_val_cv])

        if np.isfinite(r2_grand_stack):
            grand_stack_r2s.append(r2_grand_stack)
            if detail:
                per_patient.append({
                    'patient': d_back['name'],
                    'backward_base': round(float(bk_r2), 3) if np.isfinite(bk_r2) else None,
                    'grand_base': round(float(r2_grand_base), 3) if np.isfinite(r2_grand_base) else None,
                    'grand_stacked': round(float(r2_grand_stack), 3),
                    'delta_vs_871': round(float(r2_grand_stack - bk_r2), 3) if np.isfinite(bk_r2) else None,
                })

    back = round(float(np.mean(backward_base_r2s)), 3) if backward_base_r2s else None
    grand_base = round(float(np.mean(grand_base_r2s)), 3) if grand_base_r2s else None
    grand_stack = round(float(np.mean(grand_stack_r2s)), 3) if grand_stack_r2s else None
    delta_vs_871 = round(grand_stack - 0.561, 3) if grand_stack is not None else None
    oracle_gap = round(0.613 - grand_stack, 3) if grand_stack is not None else None
    pct_oracle = round(grand_stack / 0.613 * 100, 1) if grand_stack is not None else None

    results = {
        'backward_base_r2': back,
        'grand_base_r2': grand_base,
        'grand_stacked_r2': grand_stack,
        'delta_vs_871_sota': delta_vs_871,
        'oracle_gap': oracle_gap,
        'pct_oracle': pct_oracle,
        'oracle_ceiling': 0.613,
        'prior_sota': 0.561,
        'n_grand_features': n_grand_feats if grand_stack_r2s else None,
        'horizons': horizons,
        'n_folds': n_folds,
        'meta_ridge_lam': lam * 5,
        'fold_ridge_lam': 0.1,
        'features_used': [
            'bidirectional_supply_demand_22',
            'pk_derivatives_5',
            'postprandial_shape_5',
            'iob_shape_5',
            'causal_ema_2',
            'cv_stacking_horizons_4',
        ],
        'n_patients': len(grand_stack_r2s),
    }
    if detail:
        results['per_patient'] = per_patient

    return {
        'experiment': 'EXP-950', 'name': 'Campaign Grand Finale',
        'status': 'pass',
        'detail': (f'backward_base={back}, grand_base={grand_base}, '
                   f'GRAND_STACKED={grand_stack}, '
                   f'vs_871={delta_vs_871:+.3f}, '
                   f'oracle_gap={oracle_gap}, pct_oracle={pct_oracle}%'
                   ) if grand_stack is not None else f'base={back}',
        'results': results,
    }


# ── Runner ────────────────────────────────────────────────────────────────────

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
        description='EXP-941-950: Correct CV Stacking Variants & Campaign Finale')
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--max-patients', type=int, default=11)
    parser.add_argument('--experiment', type=str, default=None)
    args = parser.parse_args()

    save_dir = PATIENTS_DIR.parent.parent / "experiments" if args.save else None
    patients = load_patients(PATIENTS_DIR, max_patients=args.max_patients)
    print(f"Loaded {len(patients)} patients")

    for exp_id in sorted(EXPERIMENTS.keys(), key=lambda x: int(x.split('-')[1])):
        if args.experiment and exp_id != args.experiment:
            continue

        exp = EXPERIMENTS[exp_id]
        print(f"\n{'=' * 60}")
        print(f"Running {exp_id}: {exp['name']}")
        print(f"{'=' * 60}")

        t0 = time.time()
        try:
            result = exp['func'](patients, detail=args.detail)
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
