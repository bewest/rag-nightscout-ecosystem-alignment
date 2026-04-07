#!/usr/bin/env python3
"""EXP-961–970: Correct AR, Combined Improvements, Conformal Prediction

Building on 130 experiments (EXP-831–960):
  - EXP-951 SOTA: R²=0.581 (regime + grand stacking)
  - EXP-955: R²=0.581 (polynomial meta-learner)
  - EXP-952: LEAKY AR correction (lag-1 residuals contain future info)
  - Multi-horizon: 30min=0.785, 60min=0.577, 90min=0.430
  - Oracle ceiling: R²=0.616

EXP-961: Correct AR Correction (lag-13 causal residuals)
EXP-962: Regime + Polynomial Combined (both +0.004 independently)
EXP-963: Regime + Interactions + Polynomial (triple combination)
EXP-964: Extended Horizon Stacking (add 90min/120min to stacking)
EXP-965: Temporal Block CV of SOTA (honest estimate of R²=0.581)
EXP-966: Conformal Prediction Bands (calibrated uncertainty)
EXP-967: Patient Clustering + Cluster Models (group similar patients)
EXP-968: Error Autocorrelation Exploitation (causal lag-13 regime)
EXP-969: Mixed-Effects Decomposition (fixed + random patient effects)
EXP-970: Ultimate Combined Model (all productive techniques)
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


# ── Helpers (from EXP-941/951) ───────────────────────────────────────────────

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


def _build_features_base_bidirectional(fd, hours, n_pred, h_steps):
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


def _build_enhanced_features_bidirectional(fd, bg, hours, n_pred, h_steps,
                                           start=24):
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
    supply_thresh = (np.percentile(supply[supply > 0], 75)
                     if np.sum(supply > 0) > 10 else 0.1)
    pp_feats = np.zeros((n_pred, 5))
    last_meal_step = -999
    for i in range(n_pred):
        if supply[i] > supply_thresh:
            if i - last_meal_step > 6:
                pass
            last_meal_step = i
        time_since = (i - last_meal_step) * 5.0
        pp_feats[i, 0] = min(time_since, 360) / 360.0
        if time_since < 60:
            pp_feats[i, 1] = 1.0
        elif time_since < 180:
            pp_feats[i, 1] = 0.5
        phase_rad = 2.0 * np.pi * min(time_since, 240) / 240.0
        pp_feats[i, 2] = np.sin(phase_rad)
        pp_feats[i, 3] = np.cos(phase_rad)
        if i >= 3:
            pp_feats[i, 4] = bg_sig[i] - bg_sig[max(0, i - 3)]
    return pp_feats


def _build_iob_features(demand, n_pred):
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
    """Build EXP-950 grand feature set (39 features)."""
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
    """EXP-871 CV stacking on grand features. Returns dict or None."""
    fd = d_back['fd']
    bg = d_back['bg']
    hours = d_back['hours']
    nr = d_back['nr']
    start = 24
    usable = d_back['usable']
    split = d_back['split']
    actual = d_back['actual']
    y_tr, y_val = actual[:split], actual[split:]

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

    h_preds, _ = _train_horizon_models(fd, bg, hours, nr, start, usable,
                                       split, horizons)
    if len(h_preds) < 3:
        return None
    stack_feats = np.column_stack([h_preds[h] for h in sorted(h_preds)])
    combined_naive = np.hstack([grand_features, stack_feats])
    X_val_n = combined_naive[split:]

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
        'r2_base': r2_base, 'r2_stacked': r2_stacked,
        'pred_val': pred_cv, 'actual_val': y_val,
        'valid_val_cv': valid_val_cv, 'w_meta': w_meta,
    }


def _build_regime_feature(grand_features, actual, split):
    """Compute regime feature: running median |error| from base model."""
    y_tr = actual[:split]
    X_tr = grand_features[:split]
    vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
    if vm_tr.sum() < 50:
        return None
    pred_base, _ = _ridge_predict(
        np.nan_to_num(X_tr[vm_tr], nan=0.0), y_tr[vm_tr],
        np.nan_to_num(grand_features, nan=0.0))
    usable = len(actual)
    base_err = np.abs(actual - pred_base[:usable])
    base_err[~np.isfinite(base_err)] = np.nanmedian(base_err[np.isfinite(base_err)])
    regime_win = 24
    regime_feat = np.zeros(usable)
    for i in range(usable):
        win = base_err[max(0, i - regime_win):i + 1]
        vw = win[np.isfinite(win)]
        regime_feat[i] = np.median(vw) if len(vw) > 0 else 0
    return regime_feat.reshape(-1, 1)


# ── EXP-961: Correct AR Correction (lag-13) ─────────────────────────────────

@register('EXP-961', 'Correct AR Correction (lag-13)')
def exp_961(patients, detail=False):
    """Fix the leakage bug from EXP-952. Use lag = h_steps+1 = 13 so the
    residual we use is from the LAST REALIZED prediction, not the previous
    timestep. At time t, the last prediction that has been verified is the one
    made at t-h_steps-1 which predicted bg[t]."""
    h_steps = 12
    start = 24
    horizons = [1, 3, 6, 12]
    correct_lag = h_steps + 1  # 13 steps = 65 min

    uncorrected_r2s, corrected_r2s = [], []
    alphas = []
    per_patient = []

    for p in patients:
        grand_features, d_back = _build_grand_features(p, h_steps, start)
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
        usable = d_back['usable']
        uncorrected_r2s.append(res['r2_stacked'])

        # Get full predictions for residual computation
        X_tr = grand_features[:split]
        y_tr = actual[:split]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        if vm_tr.sum() < 50:
            corrected_r2s.append(res['r2_stacked'])
            continue
        pred_full, _ = _ridge_predict(
            np.nan_to_num(X_tr[vm_tr], nan=0.0), y_tr[vm_tr],
            np.nan_to_num(grand_features, nan=0.0))
        residuals = actual - pred_full[:usable]
        residuals[~np.isfinite(residuals)] = 0.0

        # Fit alpha using CORRECT lag on training set
        tr_resid_lag = np.zeros(split)
        for i in range(correct_lag, split):
            tr_resid_lag[i] = residuals[i - correct_lag]
        tr_correction = residuals[:split]
        valid_alpha = (np.isfinite(tr_correction) & np.isfinite(tr_resid_lag)
                       & (np.arange(split) >= correct_lag))
        if valid_alpha.sum() < 50:
            alpha_opt = 0.0
        else:
            x_a = tr_resid_lag[valid_alpha]
            y_a = tr_correction[valid_alpha]
            alpha_opt = float(np.dot(x_a, y_a) / (np.dot(x_a, x_a) + 1e-10))
            alpha_opt = np.clip(alpha_opt, 0.0, 1.0)
        alphas.append(alpha_opt)

        # Apply causal AR correction to validation predictions
        val_resid_lag = np.zeros(len(pred_val))
        for j in range(len(pred_val)):
            idx = split + j
            lag_idx = idx - correct_lag
            if 0 <= lag_idx < len(residuals):
                val_resid_lag[j] = residuals[lag_idx]
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
        'uncorrected_r2': uncorr, 'corrected_r2': corr,
        'mean_alpha': mean_alpha, 'correct_lag': correct_lag,
        'delta': round(corr - uncorr, 3) if (uncorr and corr) else None,
        'n_patients': len(corrected_r2s),
    }
    if detail:
        results['per_patient'] = per_patient

    return {
        'experiment': 'EXP-961', 'name': 'Correct AR Correction (lag-13)',
        'status': 'pass',
        'detail': f'uncorrected={uncorr}, corrected={corr}, alpha={mean_alpha}, lag={correct_lag}',
        'results': results,
    }


# ── EXP-962: Regime + Polynomial Combined ───────────────────────────────────

@register('EXP-962', 'Regime + Polynomial Combined')
def exp_962(patients, detail=False):
    """Combine regime feature (EXP-951: +0.004) with polynomial meta-learner
    (EXP-955: +0.004). Are they additive?"""
    h_steps = 12
    start = 24
    horizons = [1, 3, 6, 12]
    n_folds = 5
    lam = 10.0

    base_r2s, combined_r2s = [], []
    per_patient = []

    for p in patients:
        grand_features, d_back = _build_grand_features(p, h_steps, start)
        if grand_features is None:
            continue

        actual = d_back['actual']
        split = d_back['split']
        fd = d_back['fd']
        bg = d_back['bg']
        hours = d_back['hours']
        nr = d_back['nr']
        usable = d_back['usable']
        y_tr, y_val = actual[:split], actual[split:]

        # Standard baseline
        res_base = _grand_cv_stacking(grand_features, d_back, horizons)
        if res_base is None:
            continue
        base_r2s.append(res_base['r2_stacked'])

        # Add regime feature
        regime_col = _build_regime_feature(grand_features, actual, split)
        if regime_col is None:
            continue
        grand_plus_regime = np.hstack([grand_features, regime_col])

        # Polynomial stacking with regime
        h_preds, _ = _train_horizon_models(fd, bg, hours, nr, start, usable,
                                           split, horizons)
        if len(h_preds) < 3:
            continue
        stack_feats = np.column_stack([h_preds[h] for h in sorted(h_preds)])
        n_h = stack_feats.shape[1]
        poly_cols = []
        for ii in range(n_h):
            for jj in range(ii, n_h):
                poly_cols.append(stack_feats[:, ii] * stack_feats[:, jj] / 1e4)
        poly_stack = np.column_stack(poly_cols)
        combined_full = np.hstack([grand_plus_regime, stack_feats, poly_stack])
        X_val_full = combined_full[split:]

        # OOF for polynomial stacking
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
        oof_poly_arr = np.column_stack(oof_poly)
        cv_combined_tr = np.hstack([grand_plus_regime[:split], oof_stack, oof_poly_arr])
        cv_combined_val = X_val_full
        valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(cv_combined_tr), axis=1)
        valid_val = np.isfinite(y_val) & np.all(np.isfinite(cv_combined_val), axis=1)
        if valid_tr.sum() < 50:
            continue
        pred_combined, _ = _ridge_predict(cv_combined_tr[valid_tr],
                                          y_tr[valid_tr],
                                          cv_combined_val, lam=lam * 10)
        r2_combined = _r2(pred_combined[valid_val], y_val[valid_val])
        combined_r2s.append(r2_combined)

        if detail:
            per_patient.append({
                'patient': d_back['name'],
                'base_r2': round(float(res_base['r2_stacked']), 3),
                'combined_r2': round(float(r2_combined), 3),
                'delta': round(float(r2_combined - res_base['r2_stacked']), 3),
            })

    base = round(float(np.mean(base_r2s)), 3) if base_r2s else None
    comb = round(float(np.mean(combined_r2s)), 3) if combined_r2s else None

    results = {
        'base_stacked_r2': base, 'regime_poly_r2': comb,
        'delta': round(comb - base, 3) if (base and comb) else None,
        'n_patients': len(combined_r2s),
    }
    if detail:
        results['per_patient'] = per_patient

    return {
        'experiment': 'EXP-962', 'name': 'Regime + Polynomial Combined',
        'status': 'pass',
        'detail': f'base={base}, regime_poly={comb}, delta={results.get("delta")}',
        'results': results,
    }


# ── EXP-963: Regime + Interactions + Polynomial ─────────────────────────────

@register('EXP-963', 'Regime + Interactions + Poly')
def exp_963(patients, detail=False):
    """Triple combination: regime + interaction features + polynomial meta."""
    h_steps = 12
    start = 24
    horizons = [1, 3, 6, 12]
    n_folds = 5
    lam = 10.0

    base_r2s, triple_r2s = [], []
    per_patient = []

    for p in patients:
        grand_features, d_back = _build_grand_features(p, h_steps, start)
        if grand_features is None:
            continue

        fd = d_back['fd']
        bg = d_back['bg']
        hours = d_back['hours']
        nr = d_back['nr']
        actual = d_back['actual']
        split = d_back['split']
        usable = d_back['usable']
        n_pred = d_back['n_pred']
        y_tr, y_val = actual[:split], actual[split:]

        res_base = _grand_cv_stacking(grand_features, d_back, horizons)
        if res_base is None:
            continue
        base_r2s.append(res_base['r2_stacked'])

        # Regime feature
        regime_col = _build_regime_feature(grand_features, actual, split)
        if regime_col is None:
            continue

        # Interaction features (6 features)
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

        grand_plus_all = np.hstack([grand_features, regime_col, interact_feats])

        # Polynomial stacking
        h_preds, _ = _train_horizon_models(fd, bg, hours, nr, start, usable,
                                           split, horizons)
        if len(h_preds) < 3:
            continue
        stack_feats = np.column_stack([h_preds[h] for h in sorted(h_preds)])
        n_h = stack_feats.shape[1]
        poly_cols = []
        for ii in range(n_h):
            for jj in range(ii, n_h):
                poly_cols.append(stack_feats[:, ii] * stack_feats[:, jj] / 1e4)
        poly_stack = np.column_stack(poly_cols)
        combined_full = np.hstack([grand_plus_all, stack_feats, poly_stack])
        X_val_full = combined_full[split:]

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
        oof_poly_arr = np.column_stack(oof_poly)
        cv_combined_tr = np.hstack([grand_plus_all[:split], oof_stack, oof_poly_arr])
        cv_combined_val = X_val_full
        valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(cv_combined_tr), axis=1)
        valid_val = np.isfinite(y_val) & np.all(np.isfinite(cv_combined_val), axis=1)
        if valid_tr.sum() < 50:
            continue
        pred_triple, _ = _ridge_predict(cv_combined_tr[valid_tr],
                                        y_tr[valid_tr],
                                        cv_combined_val, lam=lam * 10)
        r2_triple = _r2(pred_triple[valid_val], y_val[valid_val])
        triple_r2s.append(r2_triple)

        if detail:
            per_patient.append({
                'patient': d_back['name'],
                'base_r2': round(float(res_base['r2_stacked']), 3),
                'triple_r2': round(float(r2_triple), 3),
                'delta': round(float(r2_triple - res_base['r2_stacked']), 3),
            })

    base = round(float(np.mean(base_r2s)), 3) if base_r2s else None
    triple = round(float(np.mean(triple_r2s)), 3) if triple_r2s else None

    results = {
        'base_stacked_r2': base, 'triple_r2': triple,
        'delta': round(triple - base, 3) if (base and triple) else None,
        'n_patients': len(triple_r2s),
    }
    if detail:
        results['per_patient'] = per_patient

    return {
        'experiment': 'EXP-963', 'name': 'Regime + Interactions + Poly',
        'status': 'pass',
        'detail': f'base={base}, triple={triple}, delta={results.get("delta")}',
        'results': results,
    }


# ── EXP-964: Extended Horizon Stacking ───────────────────────────────────────

@register('EXP-964', 'Extended Horizon Stacking')
def exp_964(patients, detail=False):
    """Add 90min (18 steps) and 120min (24 steps) horizons to stacking."""
    h_steps = 12
    start = 24
    standard_horizons = [1, 3, 6, 12]
    extended_horizons = [1, 3, 6, 12, 18, 24]

    std_r2s, ext_r2s = [], []
    per_patient = []

    for p in patients:
        grand_features, d_back = _build_grand_features(p, h_steps, start)
        if grand_features is None:
            continue

        res_std = _grand_cv_stacking(grand_features, d_back, standard_horizons)
        if res_std is None:
            continue
        std_r2s.append(res_std['r2_stacked'])

        res_ext = _grand_cv_stacking(grand_features, d_back, extended_horizons)
        if res_ext is None:
            continue
        ext_r2s.append(res_ext['r2_stacked'])

        if detail:
            per_patient.append({
                'patient': d_back['name'],
                'standard_r2': round(float(res_std['r2_stacked']), 3),
                'extended_r2': round(float(res_ext['r2_stacked']), 3),
                'delta': round(float(res_ext['r2_stacked'] - res_std['r2_stacked']), 3),
            })

    std = round(float(np.mean(std_r2s)), 3) if std_r2s else None
    ext = round(float(np.mean(ext_r2s)), 3) if ext_r2s else None

    results = {
        'standard_horizons_r2': std, 'extended_horizons_r2': ext,
        'delta': round(ext - std, 3) if (std and ext) else None,
        'standard_horizons': standard_horizons, 'extended_horizons': extended_horizons,
        'n_patients': len(ext_r2s),
    }
    if detail:
        results['per_patient'] = per_patient

    return {
        'experiment': 'EXP-964', 'name': 'Extended Horizon Stacking',
        'status': 'pass',
        'detail': f'standard={std}, extended={ext}, delta={results.get("delta")}',
        'results': results,
    }


# ── EXP-965: Temporal Block CV of SOTA ───────────────────────────────────────

@register('EXP-965', 'Block CV of SOTA')
def exp_965(patients, detail=False):
    """Honest temporal block CV estimate of the R²=0.581 SOTA."""
    h_steps = 12
    start = 24
    horizons = [1, 3, 6, 12]
    n_blocks = 5

    standard_r2s = []
    block_r2s_all = []
    per_patient = []

    for p in patients:
        grand_features, d_back = _build_grand_features(p, h_steps, start)
        if grand_features is None:
            continue

        actual = d_back['actual']
        usable = d_back['usable']
        split = d_back['split']

        # Add regime feature (SOTA model)
        regime_col = _build_regime_feature(grand_features, actual, split)
        if regime_col is None:
            continue
        grand_plus_regime = np.hstack([grand_features, regime_col])

        # Standard 80/20 SOTA
        res_std = _grand_cv_stacking(grand_plus_regime, d_back, horizons)
        if res_std is None:
            continue
        standard_r2s.append(res_std['r2_stacked'])

        # Block CV
        block_size = usable // n_blocks
        block_r2s = []
        for bi in range(n_blocks):
            val_start = bi * block_size
            val_end = min((bi + 1) * block_size, usable)
            train_idx = np.concatenate([np.arange(0, val_start),
                                        np.arange(val_end, usable)])
            val_idx = np.arange(val_start, val_end)

            if len(train_idx) < 100 or len(val_idx) < 50:
                continue

            X_tr = grand_plus_regime[train_idx]
            y_tr = actual[train_idx]
            X_val = grand_plus_regime[val_idx]
            y_val = actual[val_idx]

            vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
            vm_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
            if vm_tr.sum() < 50 or vm_val.sum() < 10:
                continue

            pred_b, _ = _ridge_predict(
                np.nan_to_num(X_tr[vm_tr], nan=0.0), y_tr[vm_tr],
                np.nan_to_num(X_val[vm_val], nan=0.0))
            r2_b = _r2(pred_b, y_val[vm_val])
            if np.isfinite(r2_b):
                block_r2s.append(r2_b)

        if block_r2s:
            mean_block = float(np.mean(block_r2s))
            block_r2s_all.append(mean_block)
            if detail:
                per_patient.append({
                    'patient': d_back['name'],
                    'standard_r2': round(float(res_std['r2_stacked']), 3),
                    'block_cv_r2': round(mean_block, 3),
                    'overstatement': round(float(res_std['r2_stacked']) - mean_block, 3),
                    'n_blocks': len(block_r2s),
                })

    std = round(float(np.mean(standard_r2s)), 3) if standard_r2s else None
    blk = round(float(np.mean(block_r2s_all)), 3) if block_r2s_all else None

    results = {
        'standard_r2': std, 'block_cv_r2': blk,
        'overstatement': round(std - blk, 3) if (std and blk) else None,
        'n_blocks': n_blocks,
        'n_patients': len(block_r2s_all),
    }
    if detail:
        results['per_patient'] = per_patient

    return {
        'experiment': 'EXP-965', 'name': 'Block CV of SOTA',
        'status': 'pass',
        'detail': f'standard={std}, block_cv={blk}, overstatement={results.get("overstatement")}',
        'results': results,
    }


# ── EXP-966: Conformal Prediction Bands ─────────────────────────────────────

@register('EXP-966', 'Conformal Prediction Bands')
def exp_966(patients, detail=False):
    """Calibrated prediction intervals using split conformal prediction."""
    h_steps = 12
    start = 24
    horizons = [1, 3, 6, 12]
    alpha_levels = [0.1, 0.2, 0.3]  # 90%, 80%, 70% intervals

    per_patient = []
    coverage_by_alpha = {a: [] for a in alpha_levels}
    width_by_alpha = {a: [] for a in alpha_levels}

    for p in patients:
        grand_features, d_back = _build_grand_features(p, h_steps, start)
        if grand_features is None:
            continue

        actual = d_back['actual']
        split = d_back['split']
        usable = d_back['usable']

        # Add regime feature
        regime_col = _build_regime_feature(grand_features, actual, split)
        if regime_col is None:
            continue
        grand_plus = np.hstack([grand_features, regime_col])

        res = _grand_cv_stacking(grand_plus, d_back, horizons)
        if res is None:
            continue

        pred_val = res['pred_val']
        actual_val = res['actual_val']
        valid_val = res['valid_val_cv']

        # Split training into proper-train + calibration (last 20% of train)
        cal_start = int(0.6 * usable)
        cal_end = split

        X_train_proper = grand_plus[:cal_start]
        y_train_proper = actual[:cal_start]
        X_cal = grand_plus[cal_start:cal_end]
        y_cal = actual[cal_start:cal_end]

        vm_tr = np.isfinite(y_train_proper) & np.all(np.isfinite(X_train_proper), axis=1)
        if vm_tr.sum() < 50:
            continue

        pred_cal, _ = _ridge_predict(
            np.nan_to_num(X_train_proper[vm_tr], nan=0.0), y_train_proper[vm_tr],
            np.nan_to_num(X_cal, nan=0.0))

        # Conformity scores: absolute residuals on calibration set
        cal_valid = np.isfinite(y_cal) & np.isfinite(pred_cal)
        if cal_valid.sum() < 20:
            continue
        cal_scores = np.abs(y_cal[cal_valid] - pred_cal[cal_valid])

        pp_row = {'patient': d_back['name'],
                  'r2': round(float(res['r2_stacked']), 3)}

        for alpha in alpha_levels:
            # Conformal quantile
            q = np.quantile(cal_scores, 1.0 - alpha)
            # Prediction bands on validation
            p_val = pred_val[valid_val]
            a_val = actual_val[valid_val]
            covered = np.abs(a_val - p_val) <= q
            coverage = float(np.mean(covered))
            width = 2 * q
            coverage_by_alpha[alpha].append(coverage)
            width_by_alpha[alpha].append(width)
            pp_row[f'coverage_{int((1-alpha)*100)}'] = round(coverage, 3)
            pp_row[f'width_{int((1-alpha)*100)}'] = round(width, 1)

        if detail:
            per_patient.append(pp_row)

    results = {}
    for alpha in alpha_levels:
        target = 1.0 - alpha
        cov = round(float(np.mean(coverage_by_alpha[alpha])), 3) if coverage_by_alpha[alpha] else None
        wid = round(float(np.mean(width_by_alpha[alpha])), 1) if width_by_alpha[alpha] else None
        results[f'coverage_{int(target*100)}'] = cov
        results[f'width_{int(target*100)}'] = wid
    results['n_patients'] = len(coverage_by_alpha[0.1])
    if detail:
        results['per_patient'] = per_patient

    parts = []
    for alpha in alpha_levels:
        t = int((1-alpha)*100)
        parts.append(f'{t}%: cov={results.get(f"coverage_{t}")}, w={results.get(f"width_{t}")}')

    return {
        'experiment': 'EXP-966', 'name': 'Conformal Prediction Bands',
        'status': 'pass',
        'detail': ', '.join(parts),
        'results': results,
    }


# ── EXP-967: Patient Clustering + Cluster Models ────────────────────────────

@register('EXP-967', 'Patient Clustering')
def exp_967(patients, detail=False):
    """Cluster patients by glucose statistics and evaluate whether cluster-
    specific models outperform individual models for LOPO."""
    h_steps = 12
    start = 24
    horizons = [1, 3, 6, 12]

    patient_stats = []
    patient_data = []

    for p in patients:
        grand_features, d_back = _build_grand_features(p, h_steps, start)
        if grand_features is None:
            continue
        bg = d_back['bg']
        actual = d_back['actual']
        split = d_back['split']
        bg_valid = bg[np.isfinite(bg)]

        stats = {
            'name': d_back['name'],
            'mean_bg': float(np.mean(bg_valid)),
            'std_bg': float(np.std(bg_valid)),
            'tir': float(np.mean((bg_valid >= 70) & (bg_valid <= 180))),
            'cv': float(np.std(bg_valid) / np.mean(bg_valid)),
        }
        patient_stats.append(stats)
        patient_data.append((grand_features, d_back))

    if len(patient_stats) < 4:
        return {
            'experiment': 'EXP-967', 'name': 'Patient Clustering',
            'status': 'skip', 'detail': 'Not enough patients',
            'results': {'n_patients': len(patient_stats)},
        }

    # Simple clustering by TIR (above/below median)
    tirs = [s['tir'] for s in patient_stats]
    median_tir = np.median(tirs)
    clusters = {}
    for i, s in enumerate(patient_stats):
        c = 'high_control' if s['tir'] >= median_tir else 'low_control'
        clusters.setdefault(c, []).append(i)

    # LOPO with cluster-specific models
    individual_r2s, cluster_r2s = [], []
    per_patient = []

    for test_i in range(len(patient_data)):
        test_feat, test_d = patient_data[test_i]
        test_name = patient_stats[test_i]['name']

        # Individual model (all other patients)
        all_other_X = []
        all_other_y = []
        for j in range(len(patient_data)):
            if j == test_i:
                continue
            gf, db = patient_data[j]
            all_other_X.append(gf)
            all_other_y.append(db['actual'])

        if not all_other_X:
            continue

        X_others = np.vstack(all_other_X)
        y_others = np.concatenate(all_other_y)
        vm = np.isfinite(y_others) & np.all(np.isfinite(X_others), axis=1)
        if vm.sum() < 100:
            continue

        split = test_d['split']
        X_test = test_feat[split:]
        y_test = test_d['actual'][split:]
        vm_test = np.isfinite(y_test) & np.all(np.isfinite(X_test), axis=1)
        if vm_test.sum() < 20:
            continue

        pred_all, _ = _ridge_predict(
            np.nan_to_num(X_others[vm], nan=0.0), y_others[vm],
            np.nan_to_num(X_test[vm_test], nan=0.0))
        r2_all = _r2(pred_all, y_test[vm_test])
        individual_r2s.append(r2_all)

        # Cluster model (only same-cluster patients)
        test_cluster = 'high_control' if patient_stats[test_i]['tir'] >= median_tir else 'low_control'
        cluster_X, cluster_y = [], []
        for j in clusters[test_cluster]:
            if j == test_i:
                continue
            gf, db = patient_data[j]
            cluster_X.append(gf)
            cluster_y.append(db['actual'])

        if not cluster_X:
            cluster_r2s.append(r2_all)
            continue

        X_clust = np.vstack(cluster_X)
        y_clust = np.concatenate(cluster_y)
        vm_c = np.isfinite(y_clust) & np.all(np.isfinite(X_clust), axis=1)
        if vm_c.sum() < 100:
            cluster_r2s.append(r2_all)
            continue

        pred_clust, _ = _ridge_predict(
            np.nan_to_num(X_clust[vm_c], nan=0.0), y_clust[vm_c],
            np.nan_to_num(X_test[vm_test], nan=0.0))
        r2_clust = _r2(pred_clust, y_test[vm_test])
        cluster_r2s.append(r2_clust)

        if detail:
            per_patient.append({
                'patient': test_name,
                'cluster': test_cluster,
                'tir': round(patient_stats[test_i]['tir'], 3),
                'all_patients_r2': round(float(r2_all), 3),
                'cluster_r2': round(float(r2_clust), 3),
                'delta': round(float(r2_clust - r2_all), 3),
            })

    ind = round(float(np.mean(individual_r2s)), 3) if individual_r2s else None
    clust = round(float(np.mean(cluster_r2s)), 3) if cluster_r2s else None

    results = {
        'all_patients_lopo_r2': ind, 'cluster_lopo_r2': clust,
        'delta': round(clust - ind, 3) if (ind and clust) else None,
        'n_patients': len(individual_r2s),
        'clusters': {k: [patient_stats[i]['name'] for i in v] for k, v in clusters.items()},
        'median_tir': round(float(median_tir), 3),
    }
    if detail:
        results['per_patient'] = per_patient

    return {
        'experiment': 'EXP-967', 'name': 'Patient Clustering',
        'status': 'pass',
        'detail': f'all_lopo={ind}, cluster_lopo={clust}, delta={results.get("delta")}',
        'results': results,
    }


# ── EXP-968: Error Autocorrelation Exploitation ─────────────────────────────

@register('EXP-968', 'Error Autocorrelation Features')
def exp_968(patients, detail=False):
    """Instead of post-hoc AR correction, add CAUSAL error features directly
    to the model: running mean/std of recent realized errors at lag >= h_steps+1."""
    h_steps = 12
    start = 24
    horizons = [1, 3, 6, 12]
    correct_lag = h_steps + 1

    base_r2s, err_feat_r2s = [], []
    per_patient = []

    for p in patients:
        grand_features, d_back = _build_grand_features(p, h_steps, start)
        if grand_features is None:
            continue

        actual = d_back['actual']
        split = d_back['split']
        usable = d_back['usable']

        # Baseline
        res_base = _grand_cv_stacking(grand_features, d_back, horizons)
        if res_base is None:
            continue
        base_r2s.append(res_base['r2_stacked'])

        # Compute base model predictions for error features
        X_tr = grand_features[:split]
        y_tr = actual[:split]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        if vm_tr.sum() < 50:
            continue
        pred_full, _ = _ridge_predict(
            np.nan_to_num(X_tr[vm_tr], nan=0.0), y_tr[vm_tr],
            np.nan_to_num(grand_features, nan=0.0))
        residuals = actual - pred_full[:usable]
        residuals[~np.isfinite(residuals)] = 0.0

        # Build CAUSAL error features (lag >= correct_lag)
        err_feats = np.zeros((usable, 4))
        for i in range(usable):
            # Last realized error (lag-13)
            lag_idx = i - correct_lag
            if lag_idx >= 0:
                err_feats[i, 0] = residuals[lag_idx]
            # Running mean of realized errors (last 12 realized)
            lag_start = max(0, i - correct_lag - 12)
            lag_end = max(0, i - correct_lag + 1)
            if lag_end > lag_start:
                win = residuals[lag_start:lag_end]
                err_feats[i, 1] = np.mean(win)
                err_feats[i, 2] = np.std(win) if len(win) > 1 else 0
            # Sign of recent errors (bias direction)
            if lag_idx >= 0:
                err_feats[i, 3] = np.sign(residuals[lag_idx])

        grand_plus_err = np.hstack([grand_features, err_feats])
        res_err = _grand_cv_stacking(grand_plus_err, d_back, horizons)
        if res_err is None:
            continue
        err_feat_r2s.append(res_err['r2_stacked'])

        if detail:
            per_patient.append({
                'patient': d_back['name'],
                'base_r2': round(float(res_base['r2_stacked']), 3),
                'err_feat_r2': round(float(res_err['r2_stacked']), 3),
                'delta': round(float(res_err['r2_stacked'] - res_base['r2_stacked']), 3),
            })

    base = round(float(np.mean(base_r2s)), 3) if base_r2s else None
    err = round(float(np.mean(err_feat_r2s)), 3) if err_feat_r2s else None

    results = {
        'base_stacked_r2': base, 'with_error_features_r2': err,
        'delta': round(err - base, 3) if (base and err) else None,
        'correct_lag': correct_lag,
        'error_features': ['last_realized_error', 'running_mean_error',
                           'running_std_error', 'error_sign'],
        'n_patients': len(err_feat_r2s),
    }
    if detail:
        results['per_patient'] = per_patient

    return {
        'experiment': 'EXP-968', 'name': 'Error Autocorrelation Features',
        'status': 'pass',
        'detail': f'base={base}, with_err_feats={err}, delta={results.get("delta")}',
        'results': results,
    }


# ── EXP-969: Mixed-Effects Decomposition ────────────────────────────────────

@register('EXP-969', 'Mixed-Effects Decomposition')
def exp_969(patients, detail=False):
    """Approximate mixed-effects model: fit fixed effects on pooled data,
    then patient-specific random intercepts/slopes."""
    h_steps = 12
    start = 24

    all_X, all_y, all_pid = [], [], []
    patient_splits = []
    patient_datas = []

    for pi, p in enumerate(patients):
        grand_features, d_back = _build_grand_features(p, h_steps, start)
        if grand_features is None:
            continue
        all_X.append(grand_features)
        all_y.append(d_back['actual'])
        all_pid.append(np.full(d_back['usable'], pi))
        patient_splits.append(d_back['split'])
        patient_datas.append(d_back)

    if len(all_X) < 3:
        return {
            'experiment': 'EXP-969', 'name': 'Mixed-Effects Decomposition',
            'status': 'skip', 'detail': 'Not enough patients',
            'results': {},
        }

    # Pool all training data
    pool_X_tr, pool_y_tr, pool_pid_tr = [], [], []
    pool_X_val, pool_y_val, pool_pid_val = [], [], []
    for i, (X, y, pid) in enumerate(zip(all_X, all_y, all_pid)):
        split = patient_splits[i]
        pool_X_tr.append(X[:split])
        pool_y_tr.append(y[:split])
        pool_pid_tr.append(pid[:split])
        pool_X_val.append(X[split:])
        pool_y_val.append(y[split:])
        pool_pid_val.append(pid[split:])

    X_pool_tr = np.vstack(pool_X_tr)
    y_pool_tr = np.concatenate(pool_y_tr)
    pid_pool_tr = np.concatenate(pool_pid_tr)
    X_pool_val = np.vstack(pool_X_val)
    y_pool_val = np.concatenate(pool_y_val)
    pid_pool_val = np.concatenate(pool_pid_val)

    vm_tr = np.isfinite(y_pool_tr) & np.all(np.isfinite(X_pool_tr), axis=1)
    vm_val = np.isfinite(y_pool_val) & np.all(np.isfinite(X_pool_val), axis=1)

    # Fixed effects (pooled ridge)
    pred_fixed_val, w_fixed = _ridge_predict(
        np.nan_to_num(X_pool_tr[vm_tr], nan=0.0), y_pool_tr[vm_tr],
        np.nan_to_num(X_pool_val[vm_val], nan=0.0))
    r2_fixed = _r2(pred_fixed_val, y_pool_val[vm_val])

    # Patient-specific random intercepts
    pred_fixed_tr, _ = _ridge_predict(
        np.nan_to_num(X_pool_tr[vm_tr], nan=0.0), y_pool_tr[vm_tr],
        np.nan_to_num(X_pool_tr, nan=0.0))
    residuals_tr = y_pool_tr - pred_fixed_tr
    patient_intercepts = {}
    unique_pids = np.unique(pid_pool_tr)
    for pid in unique_pids:
        mask = (pid_pool_tr == pid) & np.isfinite(residuals_tr)
        if mask.sum() > 0:
            patient_intercepts[pid] = float(np.mean(residuals_tr[mask]))

    # Apply random intercepts to validation
    pred_mixed_val = pred_fixed_val.copy()
    val_valid_idx = np.where(vm_val)[0]
    for ii, vi in enumerate(val_valid_idx):
        pid = pid_pool_val[vi]
        if pid in patient_intercepts:
            pred_mixed_val[ii] += patient_intercepts[pid]
    r2_mixed = _r2(pred_mixed_val, y_pool_val[vm_val])

    # Per-patient comparison
    per_patient = []
    individual_r2s = []
    for i, (X, y, d_back) in enumerate(zip(all_X, all_y, patient_datas)):
        split = patient_splits[i]
        X_tr_i = X[:split]
        y_tr_i = y[:split]
        X_val_i = X[split:]
        y_val_i = y[split:]
        vm_i = np.isfinite(y_tr_i) & np.all(np.isfinite(X_tr_i), axis=1)
        vm_vi = np.isfinite(y_val_i) & np.all(np.isfinite(X_val_i), axis=1)
        if vm_i.sum() < 50 or vm_vi.sum() < 10:
            continue
        pred_i, _ = _ridge_predict(
            np.nan_to_num(X_tr_i[vm_i], nan=0.0), y_tr_i[vm_i],
            np.nan_to_num(X_val_i[vm_vi], nan=0.0))
        r2_i = _r2(pred_i, y_val_i[vm_vi])
        individual_r2s.append(r2_i)

        if detail:
            per_patient.append({
                'patient': d_back['name'],
                'individual_r2': round(float(r2_i), 3),
                'intercept': round(float(patient_intercepts.get(i, 0)), 1),
            })

    ind_mean = round(float(np.mean(individual_r2s)), 3) if individual_r2s else None

    results = {
        'fixed_effects_r2': round(float(r2_fixed), 3),
        'mixed_effects_r2': round(float(r2_mixed), 3),
        'individual_mean_r2': ind_mean,
        'intercept_improvement': round(float(r2_mixed - r2_fixed), 3),
        'n_patients': len(unique_pids),
    }
    if detail:
        results['per_patient'] = per_patient
        results['patient_intercepts'] = {
            patient_datas[int(k)]['name'] if int(k) < len(patient_datas) else str(k):
            round(v, 1) for k, v in patient_intercepts.items()
        }

    return {
        'experiment': 'EXP-969', 'name': 'Mixed-Effects Decomposition',
        'status': 'pass',
        'detail': (f'fixed={results["fixed_effects_r2"]}, mixed={results["mixed_effects_r2"]}, '
                   f'individual={ind_mean}'),
        'results': results,
    }


# ── EXP-970: Ultimate Combined Model ────────────────────────────────────────

@register('EXP-970', 'Ultimate Combined Model')
def exp_970(patients, detail=False):
    """Combine ALL productive techniques discovered across 130 experiments:
    grand features + regime + interactions + causal error features +
    polynomial CV stacking. This is the definitive best model."""
    h_steps = 12
    start = 24
    horizons = [1, 3, 6, 12]
    n_folds = 5
    lam = 10.0
    correct_lag = h_steps + 1

    base_r2s, ultimate_r2s = [], []
    per_patient = []

    for p in patients:
        grand_features, d_back = _build_grand_features(p, h_steps, start)
        if grand_features is None:
            continue

        fd = d_back['fd']
        bg = d_back['bg']
        hours = d_back['hours']
        nr = d_back['nr']
        actual = d_back['actual']
        split = d_back['split']
        usable = d_back['usable']
        n_pred = d_back['n_pred']
        y_tr, y_val = actual[:split], actual[split:]

        # Baseline
        res_base = _grand_cv_stacking(grand_features, d_back, horizons)
        if res_base is None:
            continue
        base_r2s.append(res_base['r2_stacked'])

        # Regime feature
        regime_col = _build_regime_feature(grand_features, actual, split)
        if regime_col is None:
            continue

        # Interaction features (6)
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

        # Causal error features (4)
        X_tr_base = grand_features[:split]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_base), axis=1)
        if vm_tr.sum() < 50:
            continue
        pred_full, _ = _ridge_predict(
            np.nan_to_num(X_tr_base[vm_tr], nan=0.0), y_tr[vm_tr],
            np.nan_to_num(grand_features, nan=0.0))
        residuals = actual - pred_full[:usable]
        residuals[~np.isfinite(residuals)] = 0.0

        err_feats = np.zeros((usable, 4))
        for i in range(usable):
            lag_idx = i - correct_lag
            if lag_idx >= 0:
                err_feats[i, 0] = residuals[lag_idx]
            lag_start = max(0, i - correct_lag - 12)
            lag_end = max(0, i - correct_lag + 1)
            if lag_end > lag_start:
                win = residuals[lag_start:lag_end]
                err_feats[i, 1] = np.mean(win)
                err_feats[i, 2] = np.std(win) if len(win) > 1 else 0
            if lag_idx >= 0:
                err_feats[i, 3] = np.sign(residuals[lag_idx])

        # Ultimate feature set: 39 + 1 + 6 + 4 = 50 features
        ultimate_features = np.hstack([
            grand_features, regime_col, interact_feats, err_feats
        ])

        # Polynomial CV stacking on ultimate features
        h_preds, _ = _train_horizon_models(fd, bg, hours, nr, start, usable,
                                           split, horizons)
        if len(h_preds) < 3:
            continue
        stack_feats = np.column_stack([h_preds[h] for h in sorted(h_preds)])
        n_h = stack_feats.shape[1]
        poly_cols = []
        for ii in range(n_h):
            for jj in range(ii, n_h):
                poly_cols.append(stack_feats[:, ii] * stack_feats[:, jj] / 1e4)
        poly_stack = np.column_stack(poly_cols)
        combined_full = np.hstack([ultimate_features, stack_feats, poly_stack])
        X_val_full = combined_full[split:]

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
        oof_poly_arr = np.column_stack(oof_poly)
        cv_combined_tr = np.hstack([ultimate_features[:split], oof_stack, oof_poly_arr])
        cv_combined_val = X_val_full

        valid_tr = np.isfinite(y_tr) & np.all(np.isfinite(cv_combined_tr), axis=1)
        valid_val = np.isfinite(y_val) & np.all(np.isfinite(cv_combined_val), axis=1)

        if valid_tr.sum() < 50:
            continue

        pred_ultimate, _ = _ridge_predict(cv_combined_tr[valid_tr],
                                          y_tr[valid_tr],
                                          cv_combined_val, lam=lam * 10)
        r2_ultimate = _r2(pred_ultimate[valid_val], y_val[valid_val])
        ultimate_r2s.append(r2_ultimate)

        if detail:
            per_patient.append({
                'patient': d_back['name'],
                'base_r2': round(float(res_base['r2_stacked']), 3),
                'ultimate_r2': round(float(r2_ultimate), 3),
                'delta': round(float(r2_ultimate - res_base['r2_stacked']), 3),
                'n_features': ultimate_features.shape[1],
            })

    base = round(float(np.mean(base_r2s)), 3) if base_r2s else None
    ult = round(float(np.mean(ultimate_r2s)), 3) if ultimate_r2s else None
    delta = round(ult - base, 3) if (base and ult) else None
    oracle_gap = round(0.616 - ult, 3) if ult else None
    pct_oracle = round(ult / 0.616 * 100, 1) if ult else None

    results = {
        'base_stacked_r2': base, 'ultimate_r2': ult,
        'delta_vs_base': delta,
        'oracle_gap': oracle_gap, 'pct_oracle': pct_oracle,
        'n_features': 50,
        'technique_stack': ['grand_39', 'regime_1', 'interactions_6',
                            'causal_errors_4', 'poly_cv_stacking'],
        'n_patients': len(ultimate_r2s),
    }
    if detail:
        results['per_patient'] = per_patient

    return {
        'experiment': 'EXP-970', 'name': 'Ultimate Combined Model',
        'status': 'pass',
        'detail': (f'base={base}, ULTIMATE={ult}, delta={delta}, '
                   f'oracle_gap={oracle_gap}, pct_oracle={pct_oracle}%'),
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
        description='EXP-961-970: Correct AR, Combined Improvements, Conformal')
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
