#!/usr/bin/env python3
"""EXP-881–890: New Information Extraction & Research-Informed Features

After 50 experiments confirming 99.9% bias-dominated error and a linear ceiling,
the only path forward is extracting NEW information from existing data. This wave
focuses on extended history windows, causal signal decomposition, meal detection,
sensor denoising, phase analysis, and deep learning ceiling estimation.

EXP-881: Extended History Window (4h, 6h, 12h rolling statistics)
EXP-882: Causal EMA Decomposition (multi-timescale trend separation)
EXP-883: Meal Onset Detection from BG Dynamics
EXP-884: Kalman Filter BG Denoising
EXP-885: Glucose Rate-of-Change Clinical Binning
EXP-886: Supply-Demand Phase Analysis
EXP-887: Residual Persistence Features
EXP-888: Time-Since-Last-Insulin Feature
EXP-889: Simple MLP Sequence Model (ceiling estimation)
EXP-890: Best-of-Campaign Stacked Benchmark
"""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy.ndimage import uniform_filter1d

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
        features[i, 1] = np.sum(fd['supply'][max(0,i-h_steps):i])
        features[i, 2] = np.sum(fd['demand'][max(0,i-h_steps):i])
        features[i, 3] = np.sum(fd['hepatic'][max(0,i-h_steps):i])
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
            x_arr = np.arange(len(vw))
            extra[i, 6] = np.polyfit(x_arr, vw, 1)[0]
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


def _causal_ema(x, alpha):
    """Strictly causal EMA: ema[i] = alpha*x[i] + (1-alpha)*ema[i-1]."""
    out = np.empty_like(x, dtype=float)
    out[0] = x[0]
    for i in range(1, len(x)):
        if np.isfinite(x[i]):
            out[i] = alpha * x[i] + (1 - alpha) * out[i - 1]
        else:
            out[i] = out[i - 1]
    return out


def _causal_rolling(x, win):
    """Strictly causal rolling stats (mean, std, min, max, slope) over backward window."""
    n = len(x)
    rmean = np.full(n, np.nan)
    rstd = np.full(n, np.nan)
    rmin = np.full(n, np.nan)
    rmax = np.full(n, np.nan)
    rslope = np.full(n, np.nan)
    for i in range(n):
        s = max(0, i - win + 1)
        w = x[s:i+1]
        v = w[np.isfinite(w)]
        if len(v) >= 3:
            rmean[i] = np.mean(v)
            rstd[i] = np.std(v)
            rmin[i] = np.min(v)
            rmax[i] = np.max(v)
            t = np.arange(len(v))
            rslope[i] = np.polyfit(t, v, 1)[0]
        elif len(v) >= 1:
            rmean[i] = np.mean(v)
            rstd[i] = 0.0
            rmin[i] = np.min(v)
            rmax[i] = np.max(v)
            rslope[i] = 0.0
    return rmean, rstd, rmin, rmax, rslope


def _train_horizon_models(fd, bg, hours, nr, start, usable, split, horizons):
    predictions = {}
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
    return predictions


# ── EXP-881: Extended History Window ──────────────────────────────────────────

@register('EXP-881', 'Extended History Window')
def exp_881(patients, detail=False):
    """Test 4h, 6h, 12h rolling statistics as features.
    Current features use ~2h history. Extending captures circadian patterns,
    meal regularity, and longer-term trends.
    """
    h_steps = 12
    start = 144  # need 12h of history (144 steps)
    windows = {'4h': 48, '6h': 72, '12h': 144}
    base_r2s = []
    results_by_window = {k: [] for k in windows}

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
        features = features[:usable]
        split = int(0.8 * usable)

        # Base model
        X_tr, X_val = features[:split], features[split:]
        y_tr, y_val = actual[:split], actual[split:]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        vm_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
        if vm_tr.sum() < 50:
            continue
        pred_base, _ = _ridge_predict(X_tr[vm_tr], y_tr[vm_tr], X_val[vm_val])
        base_r2s.append(_r2(pred_base, y_val[vm_val]))

        # Extended windows
        for wname, win in windows.items():
            rmean, rstd, rmin, rmax, rslope = _causal_rolling(bg[:n_pred], win)
            # Supply/demand rolling mean
            sd_rmean, _, _, _, _ = _causal_rolling(fd['supply'][:n_pred] - fd['demand'][:n_pred], win)

            ext = np.column_stack([
                rmean[start:start+usable],
                rstd[start:start+usable],
                rmin[start:start+usable],
                rmax[start:start+usable],
                rslope[start:start+usable],
                sd_rmean[start:start+usable],
            ])
            X_ext = np.hstack([features, ext])
            X_tr_e, X_val_e = X_ext[:split], X_ext[split:]
            vm_tr_e = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_e), axis=1)
            vm_val_e = np.isfinite(y_val) & np.all(np.isfinite(X_val_e), axis=1)
            if vm_tr_e.sum() < 50:
                continue
            pred_e, _ = _ridge_predict(X_tr_e[vm_tr_e], y_tr[vm_tr_e], X_val_e[vm_val_e])
            results_by_window[wname].append(_r2(pred_e, y_val[vm_val_e]))

    base = round(float(np.mean(base_r2s)), 3) if base_r2s else None
    win_results = {k: round(float(np.mean(v)), 3) if v else None for k, v in results_by_window.items()}
    best_win = max(win_results, key=lambda k: win_results[k] or -1) if win_results else None
    best_r2 = win_results.get(best_win)
    delta = round(best_r2 - base, 3) if best_r2 and base else None

    return {
        'experiment': 'EXP-881', 'name': 'Extended History Window',
        'status': 'pass',
        'detail': f'base={base}, windows={win_results}, best={best_win}({best_r2}), Δ={delta:+.3f}' if delta else f'base={base}, windows={win_results}',
        'results': {'base': base, 'per_window': win_results, 'best_window': best_win, 'improvement': delta},
    }


# ── EXP-882: Causal EMA Decomposition ────────────────────────────────────────

@register('EXP-882', 'Causal EMA Decomposition')
def exp_882(patients, detail=False):
    """Decompose BG with causal EMAs at multiple timescales.
    Trend (12h EMA), medium (1h EMA - 12h EMA), fast (BG - 1h EMA).
    Predict each band separately and sum, or use as features.
    """
    h_steps = 12
    start = 24
    # EMA time constants → alpha = 2/(N+1) where N=steps
    ema_configs = {
        '15min': 2.0/(3+1),    # 3 steps
        '1h': 2.0/(12+1),      # 12 steps
        '4h': 2.0/(48+1),      # 48 steps
        '12h': 2.0/(144+1),    # 144 steps
    }

    base_r2s, decomp_r2s, feat_r2s = [], [], []

    for p in patients:
        d = _prepare_patient(p, h_steps, start)
        if d is None:
            continue
        bg, fd, actual, features, split, usable = d['bg'], d['fd'], d['actual'], d['features'], d['split'], d['usable']
        y_tr, y_val = actual[:split], actual[split:]

        # Base
        X_tr, X_val = features[:split], features[split:]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        vm_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
        if vm_tr.sum() < 50:
            continue
        pred_b, _ = _ridge_predict(X_tr[vm_tr], y_tr[vm_tr], X_val[vm_val])
        base_r2s.append(_r2(pred_b, y_val[vm_val]))

        # Compute causal EMAs
        emas = {}
        n_pred = d['n_pred']
        bg_sig = bg[:n_pred].copy()
        bg_sig[~np.isfinite(bg_sig)] = np.nanmean(bg_sig)
        for name, alpha in ema_configs.items():
            emas[name] = _causal_ema(bg_sig, alpha)

        # Decompose: trend=12h, medium=1h-12h, fast=bg-1h
        trend = emas['12h'][start:start+usable]
        medium = emas['1h'][start:start+usable] - trend
        fast = bg_sig[start:start+usable] - emas['1h'][start:start+usable]

        # Method A: predict each band separately, sum
        target_trend = _causal_ema(bg[h_steps+1:h_steps+1+n_pred].astype(float), ema_configs['12h'])[start:start+usable]
        bands_pred_val = np.zeros(usable - split)
        for band_y_offset, band_x in [(target_trend, trend)]:
            bx = band_x.reshape(-1, 1)
            bx_tr, bx_val = bx[:split], bx[split:]
            by_tr = band_y_offset[:split]
            bv = np.isfinite(by_tr) & np.all(np.isfinite(bx_tr), axis=1)
            if bv.sum() < 10:
                continue
            bp, _ = _ridge_predict(bx_tr[bv], by_tr[bv], bx_val)
            bands_pred_val += bp[:len(bands_pred_val)]

        # Method B: use EMAs as additional features
        ema_feats = np.column_stack([emas[k][start:start+usable] for k in ema_configs])
        X_ema = np.hstack([features, ema_feats])
        X_tr_e, X_val_e = X_ema[:split], X_ema[split:]
        vm_tr_e = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_e), axis=1)
        vm_val_e = np.isfinite(y_val) & np.all(np.isfinite(X_val_e), axis=1)
        if vm_tr_e.sum() < 50:
            continue
        pred_f, _ = _ridge_predict(X_tr_e[vm_tr_e], y_tr[vm_tr_e], X_val_e[vm_val_e])
        feat_r2s.append(_r2(pred_f, y_val[vm_val_e]))

    base = round(float(np.mean(base_r2s)), 3) if base_r2s else None
    feat = round(float(np.mean(feat_r2s)), 3) if feat_r2s else None
    delta = round(feat - base, 3) if feat and base else None

    return {
        'experiment': 'EXP-882', 'name': 'Causal EMA Decomposition',
        'status': 'pass',
        'detail': f'base={base}, +ema_feats={feat}, Δ={delta:+.3f}' if delta else f'base={base}',
        'results': {'base': base, 'ema_features': feat, 'improvement': delta},
    }


# ── EXP-883: Meal Onset Detection ────────────────────────────────────────────

@register('EXP-883', 'Meal Onset Detection from BG Dynamics')
def exp_883(patients, detail=False):
    """Detect meal onset from BG acceleration. Create binary meal-detected
    feature + time-since-meal + max-acceleration. All backward-looking.
    """
    h_steps = 12
    start = 24
    base_r2s, meal_r2s = [], []

    for p in patients:
        d = _prepare_patient(p, h_steps, start)
        if d is None:
            continue
        bg, fd, actual, features, split, usable = d['bg'], d['fd'], d['actual'], d['features'], d['split'], d['usable']
        y_tr, y_val = actual[:split], actual[split:]
        n_pred = d['n_pred']

        # Base
        X_tr, X_val = features[:split], features[split:]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        vm_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
        if vm_tr.sum() < 50:
            continue
        pred_b, _ = _ridge_predict(X_tr[vm_tr], y_tr[vm_tr], X_val[vm_val])
        base_r2s.append(_r2(pred_b, y_val[vm_val]))

        # Meal detection (causal)
        bg_sig = bg[:n_pred].astype(float)
        vel = np.zeros(n_pred)
        accel = np.zeros(n_pred)
        for i in range(1, n_pred):
            vel[i] = bg_sig[i] - bg_sig[i-1]
        for i in range(2, n_pred):
            accel[i] = vel[i] - vel[i-1]

        # Detect meal: sustained acceleration + positive velocity
        meal_detected = np.zeros(n_pred)
        time_since_meal = np.full(n_pred, 999.0)
        max_accel_30 = np.zeros(n_pred)
        last_meal = -999

        for i in range(6, n_pred):  # need 30min history
            # Check if recent acceleration pattern suggests meal
            recent_accel = accel[i-5:i+1]
            recent_vel = vel[i-5:i+1]
            pos_accel = np.sum(recent_accel > 0.5)
            pos_vel = np.mean(recent_vel) > 0.3
            if pos_accel >= 3 and pos_vel:
                meal_detected[i] = 1.0
                last_meal = i
            time_since_meal[i] = (i - last_meal) * 5.0  # minutes
            max_accel_30[i] = np.max(accel[max(0,i-6):i+1])

        meal_feats = np.column_stack([
            meal_detected[start:start+usable],
            np.minimum(time_since_meal[start:start+usable], 300) / 300.0,
            max_accel_30[start:start+usable],
        ])

        X_meal = np.hstack([features, meal_feats])
        X_tr_m, X_val_m = X_meal[:split], X_meal[split:]
        vm_tr_m = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_m), axis=1)
        vm_val_m = np.isfinite(y_val) & np.all(np.isfinite(X_val_m), axis=1)
        if vm_tr_m.sum() < 50:
            continue
        pred_m, _ = _ridge_predict(X_tr_m[vm_tr_m], y_tr[vm_tr_m], X_val_m[vm_val_m])
        meal_r2s.append(_r2(pred_m, y_val[vm_val_m]))

    base = round(float(np.mean(base_r2s)), 3) if base_r2s else None
    meal = round(float(np.mean(meal_r2s)), 3) if meal_r2s else None
    delta = round(meal - base, 3) if meal and base else None

    return {
        'experiment': 'EXP-883', 'name': 'Meal Onset Detection from BG Dynamics',
        'status': 'pass',
        'detail': f'base={base}, +meal_detect={meal}, Δ={delta:+.3f}' if delta else f'base={base}',
        'results': {'base': base, 'with_meal_detect': meal, 'improvement': delta},
    }


# ── EXP-884: Kalman Filter BG Denoising ──────────────────────────────────────

@register('EXP-884', 'Kalman Filter BG Denoising')
def exp_884(patients, detail=False):
    """Apply causal Kalman filter to denoise CGM. Model: state=[BG, vel],
    measurement=noisy BG. Use filtered BG for feature extraction.
    """
    h_steps = 12
    start = 24
    base_r2s, kalman_r2s = [], []

    def kalman_filter(z, Q_scale=1.0, R=225.0):
        """1D Kalman: state=[bg, velocity], measure=bg."""
        n = len(z)
        dt = 5.0  # minutes
        F = np.array([[1, dt], [0, 1]])
        H = np.array([[1, 0]])
        Q = Q_scale * np.array([[dt**2/4, dt/2], [dt/2, 1]])
        R_mat = np.array([[R]])
        x = np.array([z[0], 0.0])
        P = np.eye(2) * 100
        filtered = np.zeros(n)
        filtered_vel = np.zeros(n)
        for i in range(n):
            # Predict
            x = F @ x
            P = F @ P @ F.T + Q
            # Update
            if np.isfinite(z[i]):
                y_inn = z[i] - H @ x
                S = H @ P @ H.T + R_mat
                K = P @ H.T @ np.linalg.inv(S)
                x = x + (K @ y_inn).flatten()
                P = (np.eye(2) - K @ H) @ P
            filtered[i] = x[0]
            filtered_vel[i] = x[1]
        return filtered, filtered_vel

    for p in patients:
        d = _prepare_patient(p, h_steps, start)
        if d is None:
            continue
        bg, fd, actual, features, split, usable = d['bg'], d['fd'], d['actual'], d['features'], d['split'], d['usable']
        y_tr, y_val = actual[:split], actual[split:]
        n_pred = d['n_pred']

        # Base
        X_tr, X_val = features[:split], features[split:]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        vm_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
        if vm_tr.sum() < 50:
            continue
        pred_b, _ = _ridge_predict(X_tr[vm_tr], y_tr[vm_tr], X_val[vm_val])
        base_r2s.append(_r2(pred_b, y_val[vm_val]))

        # Kalman-filtered features
        bg_raw = bg[:n_pred].astype(float)
        bg_filt, bg_vel_filt = kalman_filter(bg_raw)
        bg_accel_filt = np.gradient(bg_vel_filt)

        # Rebuild features with filtered BG
        fd_filt = dict(fd)
        fd_filt['bg'] = np.concatenate([bg_filt, bg[n_pred:]])
        features_k, _ = _build_enhanced_features(fd_filt, bg_filt, d['hours'], n_pred, h_steps, start)
        # Add Kalman extras: filtered velocity, filtered accel, innovation (raw-filtered)
        innovation = bg_raw[start:start+usable] - bg_filt[start:start+usable]
        k_extras = np.column_stack([
            bg_vel_filt[start:start+usable],
            bg_accel_filt[start:start+usable],
            innovation,
        ])
        X_k = np.hstack([features_k[:usable], k_extras])

        X_tr_k, X_val_k = X_k[:split], X_k[split:]
        vm_tr_k = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_k), axis=1)
        vm_val_k = np.isfinite(y_val) & np.all(np.isfinite(X_val_k), axis=1)
        if vm_tr_k.sum() < 50:
            continue
        pred_k, _ = _ridge_predict(X_tr_k[vm_tr_k], y_tr[vm_tr_k], X_val_k[vm_val_k])
        kalman_r2s.append(_r2(pred_k, y_val[vm_val_k]))

    base = round(float(np.mean(base_r2s)), 3) if base_r2s else None
    kalman = round(float(np.mean(kalman_r2s)), 3) if kalman_r2s else None
    delta = round(kalman - base, 3) if kalman and base else None

    return {
        'experiment': 'EXP-884', 'name': 'Kalman Filter BG Denoising',
        'status': 'pass',
        'detail': f'base={base}, +kalman={kalman}, Δ={delta:+.3f}' if delta else f'base={base}',
        'results': {'base': base, 'with_kalman': kalman, 'improvement': delta},
    }


# ── EXP-885: Glucose Rate-of-Change Binning ──────────────────────────────────

@register('EXP-885', 'Glucose Rate-of-Change Clinical Binning')
def exp_885(patients, detail=False):
    """Bin rate-of-change into clinical categories (rapid fall/fall/stable/rise/rapid rise)
    and BG into clinical ranges. Use one-hot features.
    """
    h_steps = 12
    start = 24
    base_r2s, binned_r2s = [], []

    # Rate bins: mg/dL per 5min step → mg/dL/min by /5
    roc_edges = [-np.inf, -3, -1, 1, 3, np.inf]  # mg/dL per step
    bg_edges = [0, 70, 80, 120, 180, 250, 500]

    for p in patients:
        d = _prepare_patient(p, h_steps, start)
        if d is None:
            continue
        bg, fd, actual, features, split, usable = d['bg'], d['fd'], d['actual'], d['features'], d['split'], d['usable']
        y_tr, y_val = actual[:split], actual[split:]
        n_pred = d['n_pred']

        # Base
        X_tr, X_val = features[:split], features[split:]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        vm_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
        if vm_tr.sum() < 50:
            continue
        pred_b, _ = _ridge_predict(X_tr[vm_tr], y_tr[vm_tr], X_val[vm_val])
        base_r2s.append(_r2(pred_b, y_val[vm_val]))

        # Compute 15-min rate of change (3 steps, backward-looking)
        bg_sig = bg[:n_pred].astype(float)
        roc_15 = np.zeros(n_pred)
        for i in range(3, n_pred):
            roc_15[i] = (bg_sig[i] - bg_sig[i-3]) / 3.0  # per step

        # One-hot ROC
        roc_cat = np.digitize(roc_15, roc_edges) - 1
        n_roc_bins = len(roc_edges) - 1
        roc_onehot = np.zeros((n_pred, n_roc_bins))
        for i in range(n_pred):
            c = min(max(roc_cat[i], 0), n_roc_bins - 1)
            roc_onehot[i, c] = 1.0

        # One-hot BG range
        bg_cat = np.digitize(bg_sig, bg_edges) - 1
        n_bg_bins = len(bg_edges) - 1
        bg_onehot = np.zeros((n_pred, n_bg_bins))
        for i in range(n_pred):
            c = min(max(bg_cat[i], 0), n_bg_bins - 1)
            bg_onehot[i, c] = 1.0

        bin_feats = np.hstack([roc_onehot[start:start+usable], bg_onehot[start:start+usable]])
        X_bin = np.hstack([features, bin_feats])
        X_tr_b, X_val_b = X_bin[:split], X_bin[split:]
        vm_tr_b = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_b), axis=1)
        vm_val_b = np.isfinite(y_val) & np.all(np.isfinite(X_val_b), axis=1)
        if vm_tr_b.sum() < 50:
            continue
        pred_bn, _ = _ridge_predict(X_tr_b[vm_tr_b], y_tr[vm_tr_b], X_val_b[vm_val_b])
        binned_r2s.append(_r2(pred_bn, y_val[vm_val_b]))

    base = round(float(np.mean(base_r2s)), 3) if base_r2s else None
    binned = round(float(np.mean(binned_r2s)), 3) if binned_r2s else None
    delta = round(binned - base, 3) if binned and base else None

    return {
        'experiment': 'EXP-885', 'name': 'Glucose Rate-of-Change Clinical Binning',
        'status': 'pass',
        'detail': f'base={base}, +binned={binned}, Δ={delta:+.3f}' if delta else f'base={base}',
        'results': {'base': base, 'with_binned': binned, 'improvement': delta},
    }


# ── EXP-886: Supply-Demand Phase Analysis ────────────────────────────────────

@register('EXP-886', 'Supply-Demand Phase Analysis')
def exp_886(patients, detail=False):
    """Analyze phase relationship between supply and demand curves.
    Compute phase lag, correlation, and imbalance features.
    """
    h_steps = 12
    start = 24
    base_r2s, phase_r2s = [], []

    for p in patients:
        d = _prepare_patient(p, h_steps, start)
        if d is None:
            continue
        bg, fd, actual, features, split, usable = d['bg'], d['fd'], d['actual'], d['features'], d['split'], d['usable']
        y_tr, y_val = actual[:split], actual[split:]
        n_pred = d['n_pred']

        # Base
        X_tr, X_val = features[:split], features[split:]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        vm_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
        if vm_tr.sum() < 50:
            continue
        pred_b, _ = _ridge_predict(X_tr[vm_tr], y_tr[vm_tr], X_val[vm_val])
        base_r2s.append(_r2(pred_b, y_val[vm_val]))

        # Phase features (causal, backward-looking windows)
        supply = fd['supply'][:n_pred]
        demand = fd['demand'][:n_pred]
        phase_feats = np.zeros((n_pred, 5))

        for i in range(24, n_pred):
            s_win = supply[i-24:i]
            d_win = demand[i-24:i]
            sv, dv = s_win[np.isfinite(s_win)], d_win[np.isfinite(d_win)]
            if len(sv) < 6 or len(dv) < 6:
                continue
            # Cross-correlation to find phase lag
            s_norm = sv - np.mean(sv)
            d_norm = dv - np.mean(dv)
            if np.std(s_norm) > 1e-6 and np.std(d_norm) > 1e-6:
                cc = np.correlate(s_norm, d_norm, 'full')
                peak_lag = np.argmax(cc) - len(sv) + 1
                phase_feats[i, 0] = peak_lag * 5.0  # lag in minutes
                phase_feats[i, 1] = np.max(cc) / (np.std(sv) * np.std(dv) * len(sv))

            # Current imbalance
            phase_feats[i, 2] = np.sum(s_win) - np.sum(d_win)
            # Imbalance derivative (trend)
            if i >= 30:
                prev_imb = np.sum(supply[i-30:i-6]) - np.sum(demand[i-30:i-6])
                curr_imb = phase_feats[i, 2]
                phase_feats[i, 3] = curr_imb - prev_imb
            # Supply/demand ratio
            d_sum = np.sum(np.abs(d_win))
            if d_sum > 0.01:
                phase_feats[i, 4] = np.sum(s_win) / d_sum

        pf = phase_feats[start:start+usable]
        X_phase = np.hstack([features, pf])
        X_tr_p, X_val_p = X_phase[:split], X_phase[split:]
        vm_tr_p = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_p), axis=1)
        vm_val_p = np.isfinite(y_val) & np.all(np.isfinite(X_val_p), axis=1)
        if vm_tr_p.sum() < 50:
            continue
        pred_p, _ = _ridge_predict(X_tr_p[vm_tr_p], y_tr[vm_tr_p], X_val_p[vm_val_p])
        phase_r2s.append(_r2(pred_p, y_val[vm_val_p]))

    base = round(float(np.mean(base_r2s)), 3) if base_r2s else None
    phase = round(float(np.mean(phase_r2s)), 3) if phase_r2s else None
    delta = round(phase - base, 3) if phase and base else None

    return {
        'experiment': 'EXP-886', 'name': 'Supply-Demand Phase Analysis',
        'status': 'pass',
        'detail': f'base={base}, +phase={phase}, Δ={delta:+.3f}' if delta else f'base={base}',
        'results': {'base': base, 'with_phase': phase, 'improvement': delta},
    }


# ── EXP-887: Residual Persistence Features ───────────────────────────────────

@register('EXP-887', 'Residual Persistence Features')
def exp_887(patients, detail=False):
    """Use the persistence of PK residuals as features: rolling mean |resid|,
    sign persistence count, rolling std. Encodes recent model performance.
    """
    h_steps = 12
    start = 24
    base_r2s, resid_r2s = [], []

    for p in patients:
        d = _prepare_patient(p, h_steps, start)
        if d is None:
            continue
        bg, fd, actual, features, split, usable = d['bg'], d['fd'], d['actual'], d['features'], d['split'], d['usable']
        y_tr, y_val = actual[:split], actual[split:]
        n_pred = d['n_pred']

        # Base
        X_tr, X_val = features[:split], features[split:]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        vm_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
        if vm_tr.sum() < 50:
            continue
        pred_b, _ = _ridge_predict(X_tr[vm_tr], y_tr[vm_tr], X_val[vm_val])
        base_r2s.append(_r2(pred_b, y_val[vm_val]))

        # Residual features (from PK residual, not prediction residual)
        resid = fd['resid']
        nr = len(resid)
        resid_feats = np.zeros((n_pred, 4))

        for i in range(6, n_pred):
            r_win = resid[max(0,i-6):min(i,nr)]
            rv = r_win[np.isfinite(r_win)]
            if len(rv) >= 2:
                resid_feats[i, 0] = np.mean(np.abs(rv))  # mean |resid| 30min
                resid_feats[i, 1] = np.std(rv)  # std resid

            # Sign persistence: how many consecutive same-sign
            if i < nr and i >= 1:
                sign = np.sign(resid[i])
                count = 1
                for j in range(i-1, max(0, i-24), -1):
                    if j < nr and np.sign(resid[j]) == sign:
                        count += 1
                    else:
                        break
                resid_feats[i, 2] = count

            # Longer window mean (2h)
            r_win2 = resid[max(0,i-24):min(i,nr)]
            rv2 = r_win2[np.isfinite(r_win2)]
            if len(rv2) >= 3:
                resid_feats[i, 3] = np.mean(rv2)  # signed mean 2h

        rf = resid_feats[start:start+usable]
        X_res = np.hstack([features, rf])
        X_tr_r, X_val_r = X_res[:split], X_res[split:]
        vm_tr_r = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_r), axis=1)
        vm_val_r = np.isfinite(y_val) & np.all(np.isfinite(X_val_r), axis=1)
        if vm_tr_r.sum() < 50:
            continue
        pred_r, _ = _ridge_predict(X_tr_r[vm_tr_r], y_tr[vm_tr_r], X_val_r[vm_val_r])
        resid_r2s.append(_r2(pred_r, y_val[vm_val_r]))

    base = round(float(np.mean(base_r2s)), 3) if base_r2s else None
    rp = round(float(np.mean(resid_r2s)), 3) if resid_r2s else None
    delta = round(rp - base, 3) if rp and base else None

    return {
        'experiment': 'EXP-887', 'name': 'Residual Persistence Features',
        'status': 'pass',
        'detail': f'base={base}, +resid_persist={rp}, Δ={delta:+.3f}' if delta else f'base={base}',
        'results': {'base': base, 'with_resid_persist': rp, 'improvement': delta},
    }


# ── EXP-888: Time-Since-Last-Insulin Feature ─────────────────────────────────

@register('EXP-888', 'Time-Since-Last-Insulin Feature')
def exp_888(patients, detail=False):
    """Track time since last significant insulin delivery (demand spike).
    Captures active insulin timing more directly.
    """
    h_steps = 12
    start = 24
    base_r2s, insulin_r2s = [], []

    for p in patients:
        d = _prepare_patient(p, h_steps, start)
        if d is None:
            continue
        bg, fd, actual, features, split, usable = d['bg'], d['fd'], d['actual'], d['features'], d['split'], d['usable']
        y_tr, y_val = actual[:split], actual[split:]
        n_pred = d['n_pred']

        # Base
        X_tr, X_val = features[:split], features[split:]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        vm_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
        if vm_tr.sum() < 50:
            continue
        pred_b, _ = _ridge_predict(X_tr[vm_tr], y_tr[vm_tr], X_val[vm_val])
        base_r2s.append(_r2(pred_b, y_val[vm_val]))

        # Insulin delivery features from demand curve
        demand = fd['demand'][:n_pred]
        demand_threshold = np.percentile(demand[demand > 0], 75) if np.sum(demand > 0) > 10 else 0.1

        ins_feats = np.zeros((n_pred, 4))
        last_bolus_step = -999

        for i in range(n_pred):
            if demand[i] > demand_threshold:
                last_bolus_step = i

            ins_feats[i, 0] = min((i - last_bolus_step) * 5.0, 720) / 720.0  # time since, normalized
            ins_feats[i, 1] = demand[last_bolus_step] if last_bolus_step >= 0 else 0  # magnitude
            # Cumulative demand last 2h
            ins_feats[i, 2] = np.sum(demand[max(0,i-24):i])
            # Demand pattern: basal-only (low variance) vs bolus-active
            d_win = demand[max(0,i-12):i]
            if len(d_win) >= 3:
                ins_feats[i, 3] = np.std(d_win) / (np.mean(d_win) + 0.001)  # coefficient of variation

        inf = ins_feats[start:start+usable]
        X_ins = np.hstack([features, inf])
        X_tr_i, X_val_i = X_ins[:split], X_ins[split:]
        vm_tr_i = np.isfinite(y_tr) & np.all(np.isfinite(X_tr_i), axis=1)
        vm_val_i = np.isfinite(y_val) & np.all(np.isfinite(X_val_i), axis=1)
        if vm_tr_i.sum() < 50:
            continue
        pred_i, _ = _ridge_predict(X_tr_i[vm_tr_i], y_tr[vm_tr_i], X_val_i[vm_val_i])
        insulin_r2s.append(_r2(pred_i, y_val[vm_val_i]))

    base = round(float(np.mean(base_r2s)), 3) if base_r2s else None
    ins = round(float(np.mean(insulin_r2s)), 3) if insulin_r2s else None
    delta = round(ins - base, 3) if ins and base else None

    return {
        'experiment': 'EXP-888', 'name': 'Time-Since-Last-Insulin Feature',
        'status': 'pass',
        'detail': f'base={base}, +insulin_timing={ins}, Δ={delta:+.3f}' if delta else f'base={base}',
        'results': {'base': base, 'with_insulin_timing': ins, 'improvement': delta},
    }


# ── EXP-889: MLP Sequence Model (ceiling estimation) ─────────────────────────

@register('EXP-889', 'MLP Sequence Model Ceiling')
def exp_889(patients, detail=False):
    """Train sklearn MLPRegressor on flattened sequence windows to estimate
    how much temporal patterns add beyond hand-crafted features.
    """
    h_steps = 12
    start = 24
    seq_len = 24  # 2h window
    base_r2s, mlp_r2s = [], []

    for p in patients:
        d = _prepare_patient(p, h_steps, start)
        if d is None:
            continue
        bg, fd, actual, features, split, usable = d['bg'], d['fd'], d['actual'], d['features'], d['split'], d['usable']
        y_tr, y_val = actual[:split], actual[split:]
        n_pred = d['n_pred']

        # Base
        X_tr, X_val = features[:split], features[split:]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        vm_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
        if vm_tr.sum() < 50:
            continue
        pred_b, _ = _ridge_predict(X_tr[vm_tr], y_tr[vm_tr], X_val[vm_val])
        base_r2s.append(_r2(pred_b, y_val[vm_val]))

        # Build sequence features: flatten last seq_len steps of [bg, supply, demand, resid]
        n_channels = 4
        seq_feats = np.zeros((usable, seq_len * n_channels))
        bg_sig = bg[:n_pred].astype(float)
        supply = fd['supply'][:n_pred]
        demand = fd['demand'][:n_pred]
        resid = fd['resid']
        nr = len(resid)

        for i in range(usable):
            orig = i + start
            for j in range(seq_len):
                idx = orig - seq_len + j + 1
                if idx >= 0:
                    seq_feats[i, j*n_channels + 0] = bg_sig[idx] if np.isfinite(bg_sig[idx]) else 0
                    seq_feats[i, j*n_channels + 1] = supply[idx]
                    seq_feats[i, j*n_channels + 2] = demand[idx]
                    seq_feats[i, j*n_channels + 3] = resid[idx] if idx < nr else 0

        # Normalize sequence features
        mean_s = np.nanmean(seq_feats[:split], axis=0)
        std_s = np.nanstd(seq_feats[:split], axis=0)
        std_s[std_s < 1e-6] = 1.0
        seq_feats = (seq_feats - mean_s) / std_s
        seq_feats = np.nan_to_num(seq_feats, 0)

        try:
            from sklearn.neural_network import MLPRegressor
            X_tr_s, X_val_s = seq_feats[:split], seq_feats[split:]
            y_tr_clean = y_tr.copy()
            y_tr_clean[~np.isfinite(y_tr_clean)] = np.nanmean(y_tr_clean)

            mlp = MLPRegressor(hidden_layer_sizes=(64, 32), max_iter=200,
                             early_stopping=True, validation_fraction=0.15,
                             random_state=42, learning_rate_init=0.001)
            mlp.fit(X_tr_s, y_tr_clean)
            pred_mlp = mlp.predict(X_val_s)
            vm_val_s = np.isfinite(y_val)
            mlp_r2s.append(_r2(pred_mlp[vm_val_s], y_val[vm_val_s]))
        except Exception:
            pass

    base = round(float(np.mean(base_r2s)), 3) if base_r2s else None
    mlp = round(float(np.mean(mlp_r2s)), 3) if mlp_r2s else None
    delta = round(mlp - base, 3) if mlp and base else None

    return {
        'experiment': 'EXP-889', 'name': 'MLP Sequence Model Ceiling',
        'status': 'pass',
        'detail': f'base_ridge={base}, mlp_seq={mlp}, Δ={delta:+.3f}' if delta else f'base={base}',
        'results': {'base_ridge': base, 'mlp_sequence': mlp, 'improvement': delta},
    }


# ── EXP-890: Best-of-Campaign Stacked Benchmark ──────────────────────────────

@register('EXP-890', 'Best-of-Campaign Stacked Benchmark')
def exp_890(patients, detail=False):
    """Combine best features with CV stacking: multi-horizon + EMA + phase +
    meal detection + residual persistence. Use 5-fold CV for Level-0.
    """
    h_steps = 12
    start = 24
    horizons = [1, 3, 6, 12]
    n_folds = 5
    base_r2s, combined_r2s = [], []
    per_patient = []

    for p in patients:
        d = _prepare_patient(p, h_steps, start)
        if d is None:
            continue
        bg, fd, actual, features, split, usable = d['bg'], d['fd'], d['actual'], d['features'], d['split'], d['usable']
        y_tr, y_val = actual[:split], actual[split:]
        nr, n_pred = d['nr'], d['n_pred']
        hours = d['hours']

        # Base
        X_tr, X_val = features[:split], features[split:]
        vm_tr = np.isfinite(y_tr) & np.all(np.isfinite(X_tr), axis=1)
        vm_val = np.isfinite(y_val) & np.all(np.isfinite(X_val), axis=1)
        if vm_tr.sum() < 50:
            continue
        pred_b, _ = _ridge_predict(X_tr[vm_tr], y_tr[vm_tr], X_val[vm_val])
        b_r2 = _r2(pred_b, y_val[vm_val])
        base_r2s.append(b_r2)

        # === Collect best additional features ===

        # 1. Causal EMAs (from EXP-882)
        bg_sig = bg[:n_pred].astype(float)
        bg_sig[~np.isfinite(bg_sig)] = np.nanmean(bg_sig)
        ema_1h = _causal_ema(bg_sig, 2.0/(12+1))
        ema_4h = _causal_ema(bg_sig, 2.0/(48+1))
        ema_12h = _causal_ema(bg_sig, 2.0/(144+1))

        # 2. Meal detection (from EXP-883)
        vel = np.zeros(n_pred)
        accel = np.zeros(n_pred)
        for i in range(1, n_pred):
            vel[i] = bg_sig[i] - bg_sig[i-1]
        for i in range(2, n_pred):
            accel[i] = vel[i] - vel[i-1]
        meal_det = np.zeros(n_pred)
        time_since_meal = np.full(n_pred, 999.0)
        last_meal = -999
        for i in range(6, n_pred):
            ra = accel[i-5:i+1]
            rv = vel[i-5:i+1]
            if np.sum(ra > 0.5) >= 3 and np.mean(rv) > 0.3:
                meal_det[i] = 1.0
                last_meal = i
            time_since_meal[i] = (i - last_meal) * 5.0

        # 3. Residual persistence (from EXP-887)
        resid = fd['resid']
        nr_r = len(resid)
        resid_mean_abs = np.zeros(n_pred)
        resid_sign_pers = np.zeros(n_pred)
        for i in range(6, n_pred):
            rw = resid[max(0,i-6):min(i,nr_r)]
            rv_r = rw[np.isfinite(rw)]
            if len(rv_r) >= 2:
                resid_mean_abs[i] = np.mean(np.abs(rv_r))
            if i < nr_r and i >= 1:
                sign = np.sign(resid[i])
                count = 1
                for j in range(i-1, max(0, i-24), -1):
                    if j < nr_r and np.sign(resid[j]) == sign:
                        count += 1
                    else:
                        break
                resid_sign_pers[i] = count

        # 4. Phase features (from EXP-886)
        supply = fd['supply'][:n_pred]
        demand = fd['demand'][:n_pred]
        phase_imbalance = np.zeros(n_pred)
        for i in range(24, n_pred):
            phase_imbalance[i] = np.sum(supply[i-24:i]) - np.sum(demand[i-24:i])

        # Combine all extra features
        extra_feats = np.column_stack([
            ema_1h[start:start+usable],
            ema_4h[start:start+usable],
            ema_12h[start:start+usable],
            meal_det[start:start+usable],
            np.minimum(time_since_meal[start:start+usable], 300) / 300.0,
            resid_mean_abs[start:start+usable],
            resid_sign_pers[start:start+usable],
            phase_imbalance[start:start+usable],
        ])

        # === Multi-horizon predictions with CV stacking ===
        h_preds = _train_horizon_models(fd, bg, hours, nr, start, usable, split, horizons)
        if len(h_preds) < 2:
            continue
        stack_feats = np.column_stack([h_preds[h] for h in sorted(h_preds)])

        # Combine: enhanced + extra + horizon predictions
        X_combined = np.hstack([features, extra_feats, stack_feats])

        # CV stacking for Level-0
        X_tr_c, X_val_c = X_combined[:split], X_combined[split:]
        y_tr_c = y_tr.copy()

        # Generate OOF predictions via 5-fold CV
        fold_size = split // n_folds
        oof_preds = np.full(split, np.nan)
        for fold in range(n_folds):
            val_s = fold * fold_size
            val_e = min((fold + 1) * fold_size, split)
            train_mask = np.ones(split, dtype=bool)
            train_mask[val_s:val_e] = False
            vm_fold = np.isfinite(y_tr_c) & np.all(np.isfinite(X_tr_c), axis=1)
            fold_train = train_mask & vm_fold
            fold_val = (~train_mask) & vm_fold
            if fold_train.sum() < 50 or fold_val.sum() < 5:
                continue
            p_fold, _ = _ridge_predict(X_tr_c[fold_train], y_tr_c[fold_train], X_tr_c[fold_val])
            oof_preds[fold_val] = p_fold

        # Level-1: predict val using model trained on OOF
        oof_valid = np.isfinite(oof_preds) & np.isfinite(y_tr_c)
        if oof_valid.sum() < 50:
            continue

        # Train final model on all training data
        vm_final = np.isfinite(y_tr_c) & np.all(np.isfinite(X_tr_c), axis=1)
        vm_val_c = np.isfinite(y_val) & np.all(np.isfinite(X_val_c), axis=1)
        if vm_final.sum() < 50:
            continue
        pred_c, _ = _ridge_predict(X_tr_c[vm_final], y_tr_c[vm_final], X_val_c[vm_val_c])
        c_r2 = _r2(pred_c, y_val[vm_val_c])
        combined_r2s.append(c_r2)

        per_patient.append({
            'patient': d['name'],
            'base': round(b_r2, 3),
            'combined': round(c_r2, 3),
            'delta': round(c_r2 - b_r2, 3),
        })

    base = round(float(np.mean(base_r2s)), 3) if base_r2s else None
    combined = round(float(np.mean(combined_r2s)), 3) if combined_r2s else None
    delta = round(combined - base, 3) if combined and base else None

    return {
        'experiment': 'EXP-890', 'name': 'Best-of-Campaign Stacked Benchmark',
        'status': 'pass',
        'detail': f'base={base}, combined={combined}, Δ={delta:+.3f}' if delta else f'base={base}',
        'results': {
            'base': base, 'combined': combined, 'improvement': delta,
            'per_patient': per_patient,
            'n_extra_features': 8, 'n_horizons': len(horizons),
        },
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def _save(result, save_dir):
    if save_dir is None:
        return
    save_dir = Path(save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)
    name = f"exp_{result['experiment'].lower().replace('-','_')}_{result['name'].lower().replace(' ','_').replace('/', '_')}.json"
    with open(save_dir / name, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    print(f"  Saved: {save_dir / name}")


def main():
    parser = argparse.ArgumentParser()
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
        print(f"\n{'='*60}")
        print(f"Running {exp_id}: {exp_info['name']}")
        print(f"{'='*60}")
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
    print(f"\n{'='*60}")
    print("All experiments complete")


if __name__ == '__main__':
    main()
