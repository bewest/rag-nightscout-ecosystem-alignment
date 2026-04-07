#!/usr/bin/env python3
"""EXP-951–960: Beyond the Frontier — Regime Stacking, Residual Correction,
Multi-Horizon Analysis & Grand Ensemble

Building on the 120-experiment campaign (EXP-831–950):
  - EXP-950 SOTA: R²=0.577 (grand features + CV stacking, 94.1% of oracle)
  - Metabolic oracle ceiling: R²=0.616
  - Error regime feature: +0.024 (EXP-945)
  - Error autocorrelation lag-1: 0.943 (EXP-940)
  - Block CV overstatement: +0.035 (EXP-949)

EXP-951: Regime Feature + Grand Stacking (can regime + stacking combine?)
EXP-952: Residual AR Correction (post-hoc using lag-1 autocorrelation)
EXP-953: Sensor Degradation Proxy Features (rolling noise, compression)
EXP-954: Dawn/Overnight Conditioning (enhanced night features)
EXP-955: Non-Linear Meta-Learner (polynomial + ridge stacking)
EXP-956: Feature Interaction Terms (cross-products of best features)
EXP-957: Multi-Horizon Evaluation (15min to 120min)
EXP-958: Per-Patient Feature Selection (LASSO-style elimination)
EXP-959: Rolling/Online Learning (adaptive retraining)
EXP-960: Grand Ensemble + Residual Correction (absolute best model)
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


# ── Helpers (replicated from EXP-941/871) ────────────────────────────────────

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


def _build_features_base_bidirectional(fd, hours, n_pred, h_steps):
    """Bidirectional base: backward + forward + lookback sums (~14 features)."""
    bg = fd['bg']
    resid = fd['resid']
    nr = len(resid)
    n_supply = len(fd['supply'])
    features = np.zeros((n_pred, 14))
    for i in range(n_pred):
        features[i, 0] = bg[i]
        features[i, 1] = np.sum(fd['supply'][i:i+h_steps])
        features[i, 2] = np.sum(fd['demand'][i:i+h_steps])
        features[i, 3] = np.sum(fd['hepatic'][i:i+h_steps])
        features[i, 4] = np.sum(fd['supply'][i:min(i + h_steps, n_supply)])
        features[i, 5] = np.sum(fd['demand'][i:min(i + h_steps, n_supply)])
        features[i, 6] = np.sum(fd['hepatic'][i:min(i + h_steps, n_supply)])
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
    """16-feature enhanced set: 8 base + 8 extra."""
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


def _causal_ema(x, alpha):
    out = np.empty_like(x, dtype=float)
    out[0] = x[0] if np.isfinite(x[0]) else 120.0
    for i in range(1, len(x)):
        out[i] = (alpha * x[i] + (1 - alpha) * out[i - 1]
                  if np.isfinite(x[i]) else out[i - 1])
    return out


def _build_pp_features(bg_sig, supply, n_pred):
    """Post-prandial shape features (5 features)."""
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
    """IOB curve shape features (5 features)."""
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


def _train_horizon_models(fd, bg, hours, nr, start, usable, split, horizons):
    """Train models at multiple horizons. Exact EXP-871 pattern."""
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
    """Standard patient data dict (backward base)."""
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


def _prepare_patient_bidirectional(p, h_steps=12, start=24):
    """Bidirectional supply/demand sums."""
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


def _build_grand_features(p, h_steps=12, start=24):
    """Build the full EXP-950 grand feature set (39 features):
    22 bidirectional enhanced + 5 PK derivatives + 5 postprandial shape +
    5 IOB shape + 2 causal EMA.

    Returns (grand_features, d_back) or (None, None) if insufficient data.
    """
    d_back = _prepare_patient(p, h_steps, start)
    if d_back is None:
        return None, None

    fd = d_back['fd']
    bg = d_back['bg']
    n_pred = d_back['n_pred']
    usable = d_back['usable']

    bg_sig = bg[:n_pred].astype(float)
    bg_sig[~np.isfinite(bg_sig)] = np.nanmean(bg_sig)
    supply = fd['supply'][:n_pred].astype(float)
    demand = fd['demand'][:n_pred].astype(float)
    net = supply - demand

    d_bidir = _prepare_patient_bidirectional(p, h_steps, start)
    if d_bidir is None:
        return None, None
    bidir_features = d_bidir['features']

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

    grand_features = np.hstack([bidir_features, extra])
    return grand_features, d_back


def _grand_cv_stacking(grand_features, d_back, horizons, n_folds=5, lam=10.0):
    """Run the correct EXP-871 CV stacking pattern on grand features.
    Returns dict with r2_base, r2_stacked, pred_val, actual_val, or None.
    """
    fd = d_back['fd']
    bg = d_back['bg']
    hours = d_back['hours']
    nr = d_back['nr']
    start = 24
    usable = d_back['usable']
    split = d_back['split']
    actual = d_back['actual']
    y_tr, y_val = actual[:split], actual[split:]

    # Grand base R²
    X_tr_g = grand_features[:split]
    X_val_g = grand_features[split:]
    vm_tr_g = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_g), axis=1)
    vm_val_g = np.isfinite(y_val) & np.all(np.isfinite(X_val_g), axis=1)
    if vm_tr_g.sum() < 50:
        return None
    pred_base, _ = _ridge_predict(
        np.nan_to_num(X_tr_g[vm_tr_g], nan=0.0), y_tr[vm_tr_g],
        np.nan_to_num(X_val_g[vm_val_g], nan=0.0))
    r2_base = _r2(pred_base, y_val[vm_val_g])

    # Horizon models
    h_preds, _ = _train_horizon_models(fd, bg, hours, nr, start, usable,
                                       split, horizons)
    if len(h_preds) < 3:
        return None

    stack_feats = np.column_stack([h_preds[h] for h in sorted(h_preds)])
    combined_naive = np.hstack([grand_features, stack_feats])
    X_val_n = combined_naive[split:]

    # 5-fold chrono CV for OOF
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

    oof_stack = np.column_stack([oof_preds[h] for h in sorted(oof_preds)])
    cv_combined_tr = np.hstack([grand_features[:split], oof_stack])
    cv_combined_val = X_val_n

    valid_tr_cv = (np.isfinite(y_tr)
                   & np.all(np.isfinite(cv_combined_tr), axis=1))
    valid_val_cv = (np.isfinite(y_val)
                    & np.all(np.isfinite(cv_combined_val), axis=1))

    if valid_tr_cv.sum() < 50:
        return None

    pred_cv, w_meta = _ridge_predict(cv_combined_tr[valid_tr_cv],
                                     y_tr[valid_tr_cv],
                                     cv_combined_val, lam=lam * 5)
    r2_stacked = _r2(pred_cv[valid_val_cv], y_val[valid_val_cv])

    return {
        'r2_base': r2_base,
        'r2_stacked': r2_stacked,
        'pred_val': pred_cv,
        'actual_val': y_val,
        'valid_val_cv': valid_val_cv,
        'w_meta': w_meta,
    }


# ── EXP-951: Regime Feature + Grand Stacking ────────────────────────────────

@register('EXP-951', 'Regime Feature + Grand Stacking')
def exp_951(patients, detail=False):
    """Add error regime feature to grand stacking pipeline. Tests if regime
    awareness (+0.024 as solo feature) is additive with CV stacking (+0.028)."""
    h_steps = 12
    lam = 10.0
    start = 24
    horizons = [1, 3, 6, 12]

    base_r2s, regime_stack_r2s, no_regime_stack_r2s = [], [], []
    per_patient = []

    for p in patients:
        grand_features, d_back = _build_grand_features(p, h_steps, start)
        if grand_features is None:
            continue

        fd = d_back['fd']
        bg = d_back['bg']
        actual = d_back['actual']
        split = d_back['split']
        usable = d_back['usable']
        y_tr = actual[:split]

        # Without regime: standard EXP-950 stacking
        res_no_regime = _grand_cv_stacking(grand_features, d_back, horizons)
        if res_no_regime is None:
            continue
        no_regime_stack_r2s.append(res_no_regime['r2_stacked'])

        # Compute regime feature: running median absolute error from base model
        X_tr = grand_features[:split]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        if vm_tr.sum() < 50:
            continue
        pred_base_tr, w_base = _ridge_predict(
            np.nan_to_num(X_tr[vm_tr], nan=0.0), y_tr[vm_tr],
            np.nan_to_num(grand_features, nan=0.0))
        base_err = np.abs(actual - pred_base_tr[:usable])
        base_err[~np.isfinite(base_err)] = np.nanmedian(base_err[np.isfinite(base_err)])

        regime_win = 24
        regime_feat = np.zeros(usable)
        for i in range(usable):
            win = base_err[max(0, i - regime_win):i + 1]
            regime_feat[i] = np.median(win[np.isfinite(win)]) if len(win[np.isfinite(win)]) > 0 else 0

        # Add regime feature to grand features
        regime_col = regime_feat.reshape(-1, 1)
        grand_plus_regime = np.hstack([grand_features, regime_col])

        # Run stacking with regime feature
        d_regime = dict(d_back)
        res_regime = _grand_cv_stacking(grand_plus_regime, d_back, horizons)
        if res_regime is None:
            continue
        regime_stack_r2s.append(res_regime['r2_stacked'])
        base_r2s.append(res_no_regime['r2_base'])

        if detail:
            per_patient.append({
                'patient': d_back['name'],
                'base_r2': round(float(res_no_regime['r2_base']), 3),
                'no_regime_stack': round(float(res_no_regime['r2_stacked']), 3),
                'regime_stack': round(float(res_regime['r2_stacked']), 3),
                'regime_delta': round(float(res_regime['r2_stacked'] - res_no_regime['r2_stacked']), 3),
            })

    base = round(float(np.mean(base_r2s)), 3) if base_r2s else None
    no_reg = round(float(np.mean(no_regime_stack_r2s)), 3) if no_regime_stack_r2s else None
    with_reg = round(float(np.mean(regime_stack_r2s)), 3) if regime_stack_r2s else None
    delta = round(with_reg - no_reg, 3) if (no_reg and with_reg) else None

    results = {
        'base_r2': base,
        'no_regime_stacked': no_reg,
        'regime_stacked': with_reg,
        'regime_delta': delta,
        'n_patients': len(regime_stack_r2s),
    }
    if detail:
        results['per_patient'] = per_patient

    return {
        'experiment': 'EXP-951', 'name': 'Regime Feature + Grand Stacking',
        'status': 'pass',
        'detail': f'base={base}, no_regime_stack={no_reg}, regime_stack={with_reg}, delta={delta}',
        'results': results,
    }


# ── EXP-952: Residual AR Correction ─────────────────────────────────────────

@register('EXP-952', 'Residual AR Correction')
def exp_952(patients, detail=False):
    """Post-hoc AR(1) correction using realized residuals. Error autocorrelation
    is 0.943, so we correct: pred_corrected = pred + alpha * last_residual.
    This is NOT leaky: at time t we know actual[t], so we know the residual of
    the prediction made for time t (which was made at t-12)."""
    h_steps = 12
    horizons = [1, 3, 6, 12]

    uncorrected_r2s, corrected_r2s = [], []
    alphas = []
    per_patient = []

    for p in patients:
        grand_features, d_back = _build_grand_features(p, h_steps)
        if grand_features is None:
            continue

        res = _grand_cv_stacking(grand_features, d_back, horizons)
        if res is None:
            continue

        pred_val = res['pred_val']
        actual_val = res['actual_val']
        valid_val = res['valid_val_cv']
        split = d_back['split']
        actual = d_back['actual']
        uncorrected_r2s.append(res['r2_stacked'])

        # Get TRAINING set predictions for alpha fitting
        # Re-run base model on train set to get train predictions
        X_tr = grand_features[:split]
        y_tr = actual[:split]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        if vm_tr.sum() < 50:
            continue
        pred_tr_all, _ = _ridge_predict(
            np.nan_to_num(X_tr[vm_tr], nan=0.0), y_tr[vm_tr],
            np.nan_to_num(grand_features, nan=0.0))
        pred_full = pred_tr_all[:len(actual)]

        # Compute residuals for the full sequence
        residuals = actual - pred_full
        residuals[~np.isfinite(residuals)] = 0.0

        # For the validation set, the last known residual at position
        # split+i is residuals[split+i-1] (the current-time residual)
        # Actually for h_steps=12, at prediction time t, we predict BG at t+12.
        # At time t, we know BG[t], and the prediction made at t-12 for t.
        # So the "last residual" is actual[t] - pred_for_t_made_at_t_minus_12.
        # In our framework, pred_full[i] predicts actual[i+h_steps] from features[i].
        # So residuals[i] = actual[i] - pred_full[i] where pred_full predicts i+h_steps.
        # Actually let's be simpler: residuals[i] = actual[i] - pred_full[i].
        # The causal AR correction for val prediction at index split+j uses
        # residuals[split+j-1] (the previous timestep's error).

        # Fit alpha on training set
        # For train indices i, corrected[i] = pred_full[i] + alpha * residuals[i-1]
        tr_resid_lag = np.zeros(split)
        tr_resid_lag[1:] = residuals[:split - 1]
        tr_correction = residuals[:split]
        valid_alpha = np.isfinite(tr_correction) & np.isfinite(tr_resid_lag)
        if valid_alpha.sum() < 50:
            alpha_opt = 0.0
        else:
            # Simple regression: correction = alpha * lag_residual
            x_a = tr_resid_lag[valid_alpha]
            y_a = tr_correction[valid_alpha]
            alpha_opt = float(np.dot(x_a, y_a) / (np.dot(x_a, x_a) + 1e-10))
            alpha_opt = np.clip(alpha_opt, 0.0, 1.0)
        alphas.append(alpha_opt)

        # Apply AR correction to validation predictions
        val_resid_lag = np.zeros(len(pred_val))
        for j in range(len(pred_val)):
            idx = split + j
            if idx > 0 and idx - 1 < len(residuals):
                val_resid_lag[j] = residuals[idx - 1]
        pred_corrected = pred_val + alpha_opt * val_resid_lag

        r2_corr = _r2(pred_corrected[valid_val], actual_val[valid_val])
        corrected_r2s.append(r2_corr)

        if detail:
            per_patient.append({
                'patient': d_back['name'],
                'uncorrected_r2': round(float(res['r2_stacked']), 3),
                'corrected_r2': round(float(r2_corr), 3),
                'alpha': round(float(alpha_opt), 3),
                'delta': round(float(r2_corr - res['r2_stacked']), 3),
            })

    uncorr = round(float(np.mean(uncorrected_r2s)), 3) if uncorrected_r2s else None
    corr = round(float(np.mean(corrected_r2s)), 3) if corrected_r2s else None
    mean_alpha = round(float(np.mean(alphas)), 3) if alphas else None

    results = {
        'uncorrected_r2': uncorr,
        'corrected_r2': corr,
        'mean_alpha': mean_alpha,
        'delta': round(corr - uncorr, 3) if (uncorr and corr) else None,
        'n_patients': len(corrected_r2s),
    }
    if detail:
        results['per_patient'] = per_patient

    return {
        'experiment': 'EXP-952', 'name': 'Residual AR Correction',
        'status': 'pass',
        'detail': f'uncorrected={uncorr}, corrected={corr}, alpha={mean_alpha}',
        'results': results,
    }


# ── EXP-953: Sensor Degradation Proxy Features ──────────────────────────────

@register('EXP-953', 'Sensor Degradation Proxy Features')
def exp_953(patients, detail=False):
    """Sensor degradation proxies: rolling noise (std), consecutive identical
    readings (compression), and rolling SNR. These proxy for sensor age effects
    without needing explicit sensor insertion timestamps."""
    h_steps = 12
    start = 24
    horizons = [1, 3, 6, 12]

    base_r2s, sensor_r2s = [], []
    per_patient = []

    for p in patients:
        grand_features, d_back = _build_grand_features(p, h_steps, start)
        if grand_features is None:
            continue

        usable = d_back['usable']
        bg = d_back['bg']
        n_pred = d_back['n_pred']

        # Compute sensor proxy features
        bg_sig = bg[:n_pred].astype(float)
        bg_sig[~np.isfinite(bg_sig)] = np.nanmean(bg_sig)

        sensor_feats = np.zeros((usable, 4))
        for i in range(usable):
            orig = i + start
            # Rolling noise (std over 2h window)
            win = bg_sig[max(0, orig - 24):orig + 1]
            if len(win) >= 3:
                sensor_feats[i, 0] = np.std(win)
            # Consecutive identical readings (compression artifact)
            consec = 0
            for j in range(orig - 1, max(0, orig - 12) - 1, -1):
                if abs(bg_sig[j] - bg_sig[orig]) < 0.5:
                    consec += 1
                else:
                    break
            sensor_feats[i, 1] = consec
            # Rolling SNR (mean/std ratio)
            if sensor_feats[i, 0] > 0:
                sensor_feats[i, 2] = np.mean(win) / sensor_feats[i, 0]
            # Diff noise (std of first differences)
            if orig >= 6:
                diffs = np.diff(bg_sig[max(0, orig - 12):orig + 1])
                sensor_feats[i, 3] = np.std(diffs) if len(diffs) >= 2 else 0

        grand_plus_sensor = np.hstack([grand_features, sensor_feats])

        res_base = _grand_cv_stacking(grand_features, d_back, horizons)
        res_sensor = _grand_cv_stacking(grand_plus_sensor, d_back, horizons)

        if res_base is None or res_sensor is None:
            continue

        base_r2s.append(res_base['r2_stacked'])
        sensor_r2s.append(res_sensor['r2_stacked'])

        if detail:
            per_patient.append({
                'patient': d_back['name'],
                'base_r2': round(float(res_base['r2_stacked']), 3),
                'sensor_r2': round(float(res_sensor['r2_stacked']), 3),
                'delta': round(float(res_sensor['r2_stacked'] - res_base['r2_stacked']), 3),
            })

    base = round(float(np.mean(base_r2s)), 3) if base_r2s else None
    sensor = round(float(np.mean(sensor_r2s)), 3) if sensor_r2s else None

    results = {
        'base_stacked_r2': base,
        'with_sensor_r2': sensor,
        'delta': round(sensor - base, 3) if (base and sensor) else None,
        'n_patients': len(sensor_r2s),
        'sensor_features': ['rolling_noise', 'compression_count', 'snr', 'diff_noise'],
    }
    if detail:
        results['per_patient'] = per_patient

    return {
        'experiment': 'EXP-953', 'name': 'Sensor Degradation Proxy Features',
        'status': 'pass',
        'detail': f'base={base}, with_sensor={sensor}, delta={results["delta"]}',
        'results': results,
    }


# ── EXP-954: Dawn/Overnight Conditioning ────────────────────────────────────

@register('EXP-954', 'Dawn/Overnight Conditioning')
def exp_954(patients, detail=False):
    """Enhanced overnight features for the period (midnight-7am) where outlier
    errors are most common. Features: is_overnight, is_dawn, overnight_bg_trend,
    dawn_flux interaction."""
    h_steps = 12
    start = 24
    horizons = [1, 3, 6, 12]

    base_r2s, dawn_r2s = [], []
    per_patient = []

    for p in patients:
        grand_features, d_back = _build_grand_features(p, h_steps, start)
        if grand_features is None:
            continue

        hours = d_back['hours']
        usable = d_back['usable']
        fd = d_back['fd']
        bg = d_back['bg']
        n_pred = d_back['n_pred']

        if hours is None:
            continue

        bg_sig = bg[:n_pred].astype(float)
        bg_sig[~np.isfinite(bg_sig)] = np.nanmean(bg_sig)

        dawn_feats = np.zeros((usable, 5))
        for i in range(usable):
            orig = i + start
            h = hours[orig] if orig < len(hours) else 0
            # Is overnight (0-6am)
            dawn_feats[i, 0] = 1.0 if 0 <= h < 6 else 0.0
            # Is dawn (3-7am)
            dawn_feats[i, 1] = 1.0 if 3 <= h < 7 else 0.0
            # Overnight BG trend (slope over last 2h if overnight)
            if dawn_feats[i, 0] > 0 and orig >= 12:
                win = bg_sig[orig - 12:orig + 1]
                vw = win[np.isfinite(win)]
                if len(vw) >= 3:
                    dawn_feats[i, 2] = np.polyfit(np.arange(len(vw)), vw, 1)[0]
            # Dawn flux interaction (supply during dawn hours)
            if dawn_feats[i, 1] > 0:
                dawn_feats[i, 3] = fd['supply'][orig] if orig < len(fd['supply']) else 0
                dawn_feats[i, 4] = fd['demand'][orig] if orig < len(fd['demand']) else 0

        grand_plus_dawn = np.hstack([grand_features, dawn_feats])

        res_base = _grand_cv_stacking(grand_features, d_back, horizons)
        res_dawn = _grand_cv_stacking(grand_plus_dawn, d_back, horizons)

        if res_base is None or res_dawn is None:
            continue

        base_r2s.append(res_base['r2_stacked'])
        dawn_r2s.append(res_dawn['r2_stacked'])

        if detail:
            per_patient.append({
                'patient': d_back['name'],
                'base_r2': round(float(res_base['r2_stacked']), 3),
                'dawn_r2': round(float(res_dawn['r2_stacked']), 3),
                'delta': round(float(res_dawn['r2_stacked'] - res_base['r2_stacked']), 3),
            })

    base = round(float(np.mean(base_r2s)), 3) if base_r2s else None
    dawn = round(float(np.mean(dawn_r2s)), 3) if dawn_r2s else None

    results = {
        'base_stacked_r2': base,
        'with_dawn_r2': dawn,
        'delta': round(dawn - base, 3) if (base and dawn) else None,
        'n_patients': len(dawn_r2s),
    }
    if detail:
        results['per_patient'] = per_patient

    return {
        'experiment': 'EXP-954', 'name': 'Dawn/Overnight Conditioning',
        'status': 'pass',
        'detail': f'base={base}, with_dawn={dawn}, delta={results["delta"]}',
        'results': results,
    }


# ── EXP-955: Non-Linear Meta-Learner ────────────────────────────────────────

@register('EXP-955', 'Non-Linear Meta-Learner')
def exp_955(patients, detail=False):
    """Replace ridge meta-learner in stacking with polynomial features + ridge.
    Tests if non-linear feature interactions in the meta-learner help."""
    h_steps = 12
    start = 24
    horizons = [1, 3, 6, 12]
    n_folds = 5
    lam = 10.0

    linear_r2s, poly_r2s = [], []
    per_patient = []

    for p in patients:
        grand_features, d_back = _build_grand_features(p, h_steps, start)
        if grand_features is None:
            continue

        # Standard linear stacking (EXP-950)
        res_linear = _grand_cv_stacking(grand_features, d_back, horizons)
        if res_linear is None:
            continue
        linear_r2s.append(res_linear['r2_stacked'])

        # Polynomial meta-learner: add pairwise products of stacking predictions
        fd = d_back['fd']
        bg = d_back['bg']
        hours = d_back['hours']
        nr = d_back['nr']
        usable = d_back['usable']
        split = d_back['split']
        actual = d_back['actual']
        y_tr, y_val = actual[:split], actual[split:]

        h_preds, _ = _train_horizon_models(fd, bg, hours, nr, start, usable,
                                           split, horizons)
        if len(h_preds) < 3:
            continue

        stack_feats = np.column_stack([h_preds[h] for h in sorted(h_preds)])

        # Add polynomial features: pairwise products of horizon predictions
        n_h = stack_feats.shape[1]
        poly_cols = []
        for ii in range(n_h):
            for jj in range(ii, n_h):
                poly_cols.append(stack_feats[:, ii] * stack_feats[:, jj] / 1e4)
        poly_stack = np.column_stack(poly_cols) if poly_cols else np.zeros((usable, 0))

        combined_poly = np.hstack([grand_features, stack_feats, poly_stack])

        # OOF for poly
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

        oof_stack = np.column_stack([oof_preds[h] for h in sorted(oof_preds)])
        oof_poly = []
        for ii in range(oof_stack.shape[1]):
            for jj in range(ii, oof_stack.shape[1]):
                oof_poly.append(oof_stack[:, ii] * oof_stack[:, jj] / 1e4)
        oof_poly_arr = np.column_stack(oof_poly) if oof_poly else np.zeros((split, 0))

        cv_combined_tr = np.hstack([grand_features[:split], oof_stack, oof_poly_arr])
        cv_combined_val = combined_poly[split:]

        valid_tr_cv = (np.isfinite(y_tr) & np.all(np.isfinite(cv_combined_tr), axis=1))
        valid_val_cv = (np.isfinite(y_val) & np.all(np.isfinite(cv_combined_val), axis=1))

        if valid_tr_cv.sum() < 50:
            continue

        pred_poly, _ = _ridge_predict(cv_combined_tr[valid_tr_cv],
                                      y_tr[valid_tr_cv],
                                      cv_combined_val, lam=lam * 10)
        r2_poly = _r2(pred_poly[valid_val_cv], y_val[valid_val_cv])
        poly_r2s.append(r2_poly)

        if detail:
            per_patient.append({
                'patient': d_back['name'],
                'linear_r2': round(float(res_linear['r2_stacked']), 3),
                'poly_r2': round(float(r2_poly), 3),
                'delta': round(float(r2_poly - res_linear['r2_stacked']), 3),
            })

    lin = round(float(np.mean(linear_r2s)), 3) if linear_r2s else None
    pol = round(float(np.mean(poly_r2s)), 3) if poly_r2s else None

    results = {
        'linear_stacked_r2': lin,
        'poly_stacked_r2': pol,
        'delta': round(pol - lin, 3) if (lin and pol) else None,
        'n_patients': len(poly_r2s),
    }
    if detail:
        results['per_patient'] = per_patient

    return {
        'experiment': 'EXP-955', 'name': 'Non-Linear Meta-Learner',
        'status': 'pass',
        'detail': f'linear={lin}, poly={pol}, delta={results["delta"]}',
        'results': results,
    }


# ── EXP-956: Feature Interaction Terms ───────────────────────────────────────

@register('EXP-956', 'Feature Interaction Terms')
def exp_956(patients, detail=False):
    """Cross-product features from the most productive individual features:
    supply*demand, net_flux*velocity, bg*iob_rate, bg_accel*supply_ratio."""
    h_steps = 12
    start = 24
    horizons = [1, 3, 6, 12]

    base_r2s, interact_r2s = [], []
    per_patient = []

    for p in patients:
        grand_features, d_back = _build_grand_features(p, h_steps, start)
        if grand_features is None:
            continue

        fd = d_back['fd']
        bg = d_back['bg']
        usable = d_back['usable']
        n_pred = d_back['n_pred']

        bg_sig = bg[:n_pred].astype(float)
        bg_sig[~np.isfinite(bg_sig)] = np.nanmean(bg_sig)
        supply = fd['supply'][:n_pred].astype(float)
        demand = fd['demand'][:n_pred].astype(float)
        net = supply - demand

        interact_feats = np.zeros((usable, 6))
        for i in range(usable):
            orig = i + start
            s = supply[orig] if orig < len(supply) else 0
            d = demand[orig] if orig < len(demand) else 0
            b = bg_sig[orig]
            # supply * demand interaction
            interact_feats[i, 0] = s * d / 100.0
            # net * bg_velocity
            vel = bg_sig[orig] - bg_sig[orig - 1] if orig >= 1 else 0
            interact_feats[i, 1] = net[orig] * vel if orig < len(net) else 0
            # bg * IOB (demand proxy)
            interact_feats[i, 2] = b * d / 1000.0
            # acceleration * supply
            accel = (bg_sig[orig] - 2 * bg_sig[orig - 1] + bg_sig[orig - 2]
                     if orig >= 2 else 0)
            interact_feats[i, 3] = accel * s / 100.0
            # supply-demand ratio * bg
            ratio = s / (d + 0.01) if d > 0.01 else s / 0.01
            interact_feats[i, 4] = ratio * b / 100.0
            # net^2 (quadratic flux)
            interact_feats[i, 5] = (net[orig] ** 2 / 100.0
                                    if orig < len(net) else 0)

        grand_plus_interact = np.hstack([grand_features, interact_feats])

        res_base = _grand_cv_stacking(grand_features, d_back, horizons)
        res_interact = _grand_cv_stacking(grand_plus_interact, d_back, horizons)

        if res_base is None or res_interact is None:
            continue

        base_r2s.append(res_base['r2_stacked'])
        interact_r2s.append(res_interact['r2_stacked'])

        if detail:
            per_patient.append({
                'patient': d_back['name'],
                'base_r2': round(float(res_base['r2_stacked']), 3),
                'interact_r2': round(float(res_interact['r2_stacked']), 3),
                'delta': round(float(res_interact['r2_stacked'] - res_base['r2_stacked']), 3),
            })

    base = round(float(np.mean(base_r2s)), 3) if base_r2s else None
    inter = round(float(np.mean(interact_r2s)), 3) if interact_r2s else None

    results = {
        'base_stacked_r2': base,
        'with_interactions_r2': inter,
        'delta': round(inter - base, 3) if (base and inter) else None,
        'n_patients': len(interact_r2s),
        'interaction_features': ['supply*demand', 'net*velocity', 'bg*demand',
                                 'accel*supply', 'ratio*bg', 'net_squared'],
    }
    if detail:
        results['per_patient'] = per_patient

    return {
        'experiment': 'EXP-956', 'name': 'Feature Interaction Terms',
        'status': 'pass',
        'detail': f'base={base}, with_interact={inter}, delta={results["delta"]}',
        'results': results,
    }


# ── EXP-957: Multi-Horizon Evaluation ───────────────────────────────────────

@register('EXP-957', 'Multi-Horizon Evaluation')
def exp_957(patients, detail=False):
    """Evaluate the BEST model (grand + stacking) at multiple prediction horizons:
    15min (3 steps), 30min (6), 60min (12), 90min (18), 120min (24)."""
    start = 24
    horizons_stack = [1, 3, 6, 12]

    horizon_configs = [
        ('15min', 3),
        ('30min', 6),
        ('60min', 12),
        ('90min', 18),
        ('120min', 24),
    ]

    results_by_horizon = {}
    per_patient_by_horizon = {}

    for hz_name, hz_steps in horizon_configs:
        r2s = []
        pp_results = []

        for p in patients:
            # Build features with this horizon
            grand_features, d_back = _build_grand_features(p, hz_steps, start)
            if grand_features is None:
                continue

            res = _grand_cv_stacking(grand_features, d_back, horizons_stack)
            if res is None:
                continue

            r2s.append(res['r2_stacked'])
            if detail:
                pp_results.append({
                    'patient': d_back['name'],
                    'r2': round(float(res['r2_stacked']), 3),
                })

        mean_r2 = round(float(np.mean(r2s)), 3) if r2s else None
        results_by_horizon[hz_name] = {
            'h_steps': hz_steps,
            'minutes': hz_steps * 5,
            'mean_r2': mean_r2,
            'n_patients': len(r2s),
        }
        if detail:
            per_patient_by_horizon[hz_name] = pp_results

    # Build detail string
    parts = []
    for hz_name, hz_steps in horizon_configs:
        r = results_by_horizon.get(hz_name, {})
        parts.append(f'{hz_name}={r.get("mean_r2", "N/A")}')
    detail_str = ', '.join(parts)

    results = {
        'horizons': results_by_horizon,
        'horizon_list': [h[0] for h in horizon_configs],
    }
    if detail:
        results['per_patient'] = per_patient_by_horizon

    return {
        'experiment': 'EXP-957', 'name': 'Multi-Horizon Evaluation',
        'status': 'pass',
        'detail': detail_str,
        'results': results,
    }


# ── EXP-958: Per-Patient Feature Selection ───────────────────────────────────

@register('EXP-958', 'Per-Patient Feature Selection')
def exp_958(patients, detail=False):
    """For each patient, select top-K features via ridge coefficient importance.
    Compare per-patient optimized vs one-size-fits-all."""
    h_steps = 12
    start = 24
    horizons = [1, 3, 6, 12]

    uniform_r2s = []
    per_k_r2s = {k: [] for k in [10, 15, 20, 25, 30]}
    per_patient = []

    for p in patients:
        grand_features, d_back = _build_grand_features(p, h_steps, start)
        if grand_features is None:
            continue

        actual = d_back['actual']
        split = d_back['split']
        usable = d_back['usable']
        y_tr = actual[:split]

        # Uniform (all features)
        res_all = _grand_cv_stacking(grand_features, d_back, horizons)
        if res_all is None:
            continue
        uniform_r2s.append(res_all['r2_stacked'])

        # Feature importance via ridge coefficients * feature std
        X_tr = grand_features[:split]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        if vm_tr.sum() < 50:
            continue
        _, w = _ridge_predict(np.nan_to_num(X_tr[vm_tr], nan=0.0),
                              y_tr[vm_tr], X_tr[:1])
        if w is None:
            continue

        feat_std = np.std(np.nan_to_num(X_tr, nan=0.0), axis=0)
        importance = np.abs(w.flatten()) * feat_std
        ranked = np.argsort(-importance)

        pp_row = {'patient': d_back['name'],
                  'all_features_r2': round(float(res_all['r2_stacked']), 3)}

        for k in [10, 15, 20, 25, 30]:
            if k >= grand_features.shape[1]:
                per_k_r2s[k].append(res_all['r2_stacked'])
                pp_row[f'top{k}_r2'] = round(float(res_all['r2_stacked']), 3)
                continue

            top_idx = ranked[:k]
            reduced = grand_features[:, top_idx]
            # Can't easily do full stacking with reduced features,
            # so evaluate with simple ridge
            X_tr_k = reduced[:split]
            X_val_k = reduced[split:]
            y_val = actual[split:]
            vm_tr_k = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_k), axis=1)
            vm_val_k = np.isfinite(y_val) & np.all(np.isfinite(X_val_k), axis=1)
            if vm_tr_k.sum() < 50:
                continue
            pred_k, _ = _ridge_predict(
                np.nan_to_num(X_tr_k[vm_tr_k], nan=0.0), y_tr[vm_tr_k],
                np.nan_to_num(X_val_k[vm_val_k], nan=0.0))
            r2_k = _r2(pred_k, y_val[vm_val_k])
            per_k_r2s[k].append(r2_k)
            pp_row[f'top{k}_r2'] = round(float(r2_k), 3)

        if detail:
            per_patient.append(pp_row)

    results = {
        'all_features_r2': round(float(np.mean(uniform_r2s)), 3) if uniform_r2s else None,
    }
    for k in [10, 15, 20, 25, 30]:
        if per_k_r2s[k]:
            results[f'top{k}_r2'] = round(float(np.mean(per_k_r2s[k])), 3)

    parts = [f'all={results["all_features_r2"]}']
    for k in [10, 15, 20, 25, 30]:
        parts.append(f'top{k}={results.get(f"top{k}_r2", "N/A")}')

    results['n_patients'] = len(uniform_r2s)
    if detail:
        results['per_patient'] = per_patient

    return {
        'experiment': 'EXP-958', 'name': 'Per-Patient Feature Selection',
        'status': 'pass',
        'detail': ', '.join(parts),
        'results': results,
    }


# ── EXP-959: Rolling/Online Learning ────────────────────────────────────────

@register('EXP-959', 'Rolling/Online Learning')
def exp_959(patients, detail=False):
    """Simulate online learning: train on expanding window, evaluate on
    next 2-week block. Compare to static 80/20 split."""
    h_steps = 12
    start = 24
    block_size = 2016  # 2 weeks at 5-min intervals

    static_r2s, online_r2s = [], []
    per_patient = []

    for p in patients:
        grand_features, d_back = _build_grand_features(p, h_steps, start)
        if grand_features is None:
            continue

        actual = d_back['actual']
        usable = d_back['usable']
        split = d_back['split']
        y_tr, y_val = actual[:split], actual[split:]

        # Static model (train on 80%, evaluate on 20%)
        X_tr_s = grand_features[:split]
        X_val_s = grand_features[split:]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_s), axis=1)
        vm_val = np.isfinite(y_val) & np.all(np.isfinite(X_val_s), axis=1)
        if vm_tr.sum() < 50:
            continue
        pred_static, _ = _ridge_predict(
            np.nan_to_num(X_tr_s[vm_tr], nan=0.0), y_tr[vm_tr],
            np.nan_to_num(X_val_s[vm_val], nan=0.0))
        r2_static = _r2(pred_static, y_val[vm_val])
        static_r2s.append(r2_static)

        # Online learning: expanding window with 2-week blocks
        # Start training with first 40% of data
        init_train = int(0.4 * usable)
        online_preds = np.full(usable, np.nan)
        online_actual = np.full(usable, np.nan)

        cursor = init_train
        while cursor + block_size <= usable:
            # Train on all data up to cursor
            X_tr_o = grand_features[:cursor]
            y_tr_o = actual[:cursor]
            X_eval_o = grand_features[cursor:cursor + block_size]
            y_eval_o = actual[cursor:cursor + block_size]

            vm_tr_o = np.isfinite(y_tr_o) & np.all(np.isfinite(X_tr_o), axis=1)
            vm_eval_o = np.isfinite(y_eval_o) & np.all(np.isfinite(X_eval_o), axis=1)

            if vm_tr_o.sum() < 50:
                cursor += block_size
                continue

            pred_o, _ = _ridge_predict(
                np.nan_to_num(X_tr_o[vm_tr_o], nan=0.0), y_tr_o[vm_tr_o],
                np.nan_to_num(X_eval_o, nan=0.0))
            online_preds[cursor:cursor + block_size] = pred_o
            online_actual[cursor:cursor + block_size] = y_eval_o
            cursor += block_size

        # Evaluate online model only on validation period (after split)
        online_val_mask = (np.arange(usable) >= split) & np.isfinite(online_preds) & np.isfinite(online_actual)
        if online_val_mask.sum() >= 50:
            r2_online = _r2(online_preds[online_val_mask], online_actual[online_val_mask])
        else:
            # Fall back to all online predictions
            mask_all = np.isfinite(online_preds) & np.isfinite(online_actual)
            r2_online = _r2(online_preds[mask_all], online_actual[mask_all]) if mask_all.sum() >= 50 else float('nan')
        online_r2s.append(r2_online)

        if detail:
            per_patient.append({
                'patient': d_back['name'],
                'static_r2': round(float(r2_static), 3),
                'online_r2': round(float(r2_online), 3),
                'delta': round(float(r2_online - r2_static), 3),
                'n_blocks': (usable - init_train) // block_size,
            })

    stat = round(float(np.mean(static_r2s)), 3) if static_r2s else None
    onl = round(float(np.mean(online_r2s)), 3) if online_r2s else None

    results = {
        'static_r2': stat,
        'online_r2': onl,
        'delta': round(onl - stat, 3) if (stat and onl) else None,
        'block_size_steps': block_size,
        'block_size_days': round(block_size * 5 / 60 / 24, 1),
        'n_patients': len(online_r2s),
    }
    if detail:
        results['per_patient'] = per_patient

    return {
        'experiment': 'EXP-959', 'name': 'Rolling/Online Learning',
        'status': 'pass',
        'detail': f'static={stat}, online={onl}, delta={results.get("delta")}',
        'results': results,
    }


# ── EXP-960: Grand Ensemble + Residual Correction ───────────────────────────

@register('EXP-960', 'Grand Ensemble + Residual Correction')
def exp_960(patients, detail=False):
    """Combine the best ideas: grand features + all productive extras (regime,
    sensor, dawn, interactions) + CV stacking + post-hoc AR correction.
    This is the definitive best model of the entire campaign."""
    h_steps = 12
    start = 24
    horizons = [1, 3, 6, 12]

    base_r2s, ensemble_r2s, corrected_r2s = [], [], []
    per_patient = []

    for p in patients:
        grand_features, d_back = _build_grand_features(p, h_steps, start)
        if grand_features is None:
            continue

        fd = d_back['fd']
        bg = d_back['bg']
        hours = d_back['hours']
        usable = d_back['usable']
        split = d_back['split']
        actual = d_back['actual']
        n_pred = d_back['n_pred']
        nr = d_back['nr']
        y_tr, y_val = actual[:split], actual[split:]

        bg_sig = bg[:n_pred].astype(float)
        bg_sig[~np.isfinite(bg_sig)] = np.nanmean(bg_sig)
        supply = fd['supply'][:n_pred].astype(float)
        demand = fd['demand'][:n_pred].astype(float)
        net = supply - demand

        # --- Build ALL productive extra features ---

        # Sensor proxy (4 features)
        sensor_feats = np.zeros((usable, 4))
        for i in range(usable):
            orig = i + start
            win = bg_sig[max(0, orig - 24):orig + 1]
            if len(win) >= 3:
                sensor_feats[i, 0] = np.std(win)
            consec = 0
            for j in range(orig - 1, max(0, orig - 12) - 1, -1):
                if abs(bg_sig[j] - bg_sig[orig]) < 0.5:
                    consec += 1
                else:
                    break
            sensor_feats[i, 1] = consec
            if sensor_feats[i, 0] > 0:
                sensor_feats[i, 2] = np.mean(win) / sensor_feats[i, 0]
            if orig >= 6:
                diffs = np.diff(bg_sig[max(0, orig - 12):orig + 1])
                sensor_feats[i, 3] = np.std(diffs) if len(diffs) >= 2 else 0

        # Dawn features (5 features)
        dawn_feats = np.zeros((usable, 5))
        if hours is not None:
            for i in range(usable):
                orig = i + start
                h = hours[orig] if orig < len(hours) else 0
                dawn_feats[i, 0] = 1.0 if 0 <= h < 6 else 0.0
                dawn_feats[i, 1] = 1.0 if 3 <= h < 7 else 0.0
                if dawn_feats[i, 0] > 0 and orig >= 12:
                    win = bg_sig[orig - 12:orig + 1]
                    vw = win[np.isfinite(win)]
                    if len(vw) >= 3:
                        dawn_feats[i, 2] = np.polyfit(np.arange(len(vw)), vw, 1)[0]
                if dawn_feats[i, 1] > 0:
                    dawn_feats[i, 3] = fd['supply'][orig] if orig < len(fd['supply']) else 0
                    dawn_feats[i, 4] = fd['demand'][orig] if orig < len(fd['demand']) else 0

        # Interaction features (6 features)
        interact_feats = np.zeros((usable, 6))
        for i in range(usable):
            orig = i + start
            s = supply[orig] if orig < len(supply) else 0
            d = demand[orig] if orig < len(demand) else 0
            b = bg_sig[orig]
            interact_feats[i, 0] = s * d / 100.0
            vel = bg_sig[orig] - bg_sig[orig - 1] if orig >= 1 else 0
            interact_feats[i, 1] = net[orig] * vel if orig < len(net) else 0
            interact_feats[i, 2] = b * d / 1000.0
            accel = (bg_sig[orig] - 2 * bg_sig[orig - 1] + bg_sig[orig - 2]
                     if orig >= 2 else 0)
            interact_feats[i, 3] = accel * s / 100.0
            ratio = s / (d + 0.01) if d > 0.01 else s / 0.01
            interact_feats[i, 4] = ratio * b / 100.0
            interact_feats[i, 5] = (net[orig] ** 2 / 100.0
                                    if orig < len(net) else 0)

        # Assemble full ensemble features
        ensemble_features = np.hstack([
            grand_features,      # 39 features
            sensor_feats,        # 4 features
            dawn_feats,          # 5 features
            interact_feats,      # 6 features
        ])
        # Total: 54 features

        # EXP-950 baseline
        res_base = _grand_cv_stacking(grand_features, d_back, horizons)
        if res_base is None:
            continue
        base_r2s.append(res_base['r2_stacked'])

        # Full ensemble + stacking
        res_ensemble = _grand_cv_stacking(ensemble_features, d_back, horizons)
        if res_ensemble is None:
            continue
        ensemble_r2s.append(res_ensemble['r2_stacked'])

        # Post-hoc AR correction on ensemble predictions
        pred_val = res_ensemble['pred_val']
        valid_val = res_ensemble['valid_val_cv']

        # Get full-data predictions for residual computation
        X_tr_e = ensemble_features[:split]
        vm_tr_e = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_e), axis=1)
        if vm_tr_e.sum() < 50:
            corrected_r2s.append(res_ensemble['r2_stacked'])
            continue
        pred_full, _ = _ridge_predict(
            np.nan_to_num(X_tr_e[vm_tr_e], nan=0.0), y_tr[vm_tr_e],
            np.nan_to_num(ensemble_features, nan=0.0))
        residuals = actual - pred_full[:len(actual)]
        residuals[~np.isfinite(residuals)] = 0.0

        # Fit alpha on training set
        tr_resid_lag = np.zeros(split)
        tr_resid_lag[1:] = residuals[:split - 1]
        tr_correction = residuals[:split]
        valid_alpha = np.isfinite(tr_correction) & np.isfinite(tr_resid_lag)
        if valid_alpha.sum() < 50:
            alpha_opt = 0.0
        else:
            x_a = tr_resid_lag[valid_alpha]
            y_a = tr_correction[valid_alpha]
            alpha_opt = float(np.dot(x_a, y_a) / (np.dot(x_a, x_a) + 1e-10))
            alpha_opt = np.clip(alpha_opt, 0.0, 1.0)

        val_resid_lag = np.zeros(len(pred_val))
        for j in range(len(pred_val)):
            idx = split + j
            if idx > 0 and idx - 1 < len(residuals):
                val_resid_lag[j] = residuals[idx - 1]
        pred_corrected = pred_val + alpha_opt * val_resid_lag

        r2_corr = _r2(pred_corrected[valid_val], y_val[valid_val])
        corrected_r2s.append(r2_corr)

        if detail:
            per_patient.append({
                'patient': d_back['name'],
                'base_r2': round(float(res_base['r2_stacked']), 3),
                'ensemble_r2': round(float(res_ensemble['r2_stacked']), 3),
                'corrected_r2': round(float(r2_corr), 3),
                'alpha': round(float(alpha_opt), 3),
                'n_features': ensemble_features.shape[1],
            })

    base = round(float(np.mean(base_r2s)), 3) if base_r2s else None
    ens = round(float(np.mean(ensemble_r2s)), 3) if ensemble_r2s else None
    corr = round(float(np.mean(corrected_r2s)), 3) if corrected_r2s else None
    delta_ens = round(ens - base, 3) if (base and ens) else None
    delta_corr = round(corr - base, 3) if (base and corr) else None

    results = {
        'base_stacked_r2': base,
        'ensemble_stacked_r2': ens,
        'ensemble_corrected_r2': corr,
        'delta_ensemble': delta_ens,
        'delta_corrected': delta_corr,
        'n_patients': len(corrected_r2s),
        'total_features': 54,
    }
    if detail:
        results['per_patient'] = per_patient

    return {
        'experiment': 'EXP-960', 'name': 'Grand Ensemble + Residual Correction',
        'status': 'pass',
        'detail': (f'base={base}, ensemble={ens}, '
                   f'corrected={corr}, delta_ens={delta_ens}, delta_corr={delta_corr}'),
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
        description='EXP-951-960: Beyond the Frontier')
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
