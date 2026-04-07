#!/usr/bin/env python3
"""EXP-741-750: Residual Structure, Longer Horizons, & Production Pipeline.

Key insights from EXP-721-740:
- Optimized hybrid: 5min=0.987, 15min=0.926, 30min=0.789, 60min=0.437
- Multi-day step physics DIVERGES → need segment-level approach
- Adaptive blend adds +0.035 at 60min
- Population prior retains 96.6% of personal

This wave focuses on:
- Segment-level multi-day prediction (fix EXP-738 failure)
- Physics residual autocorrelation structure
- Meta-ensemble combining direct + two-stage
- State-dependent blending (meal vs sleep vs activity)
- Unannounced meal detection from physics residuals
- Full production ensemble pipeline
"""

import argparse
import json
import time
import traceback
from pathlib import Path

import numpy as np
import pandas as pd

from cgmencode.exp_metabolic_flux import load_patients
from cgmencode.exp_metabolic_441 import compute_supply_demand

PATIENTS_DIR = Path(__file__).parent.parent.parent / "externals" / "ns-data" / "patients"


# === shared utilities ===
def _detect_spikes(resid, sigma_mult=2.0):
    jumps = np.abs(np.diff(resid))
    valid = np.isfinite(jumps)
    mu = np.nanmean(jumps[valid])
    sigma = np.nanstd(jumps[valid])
    threshold = mu + sigma_mult * sigma
    spike_idx = np.where(valid & (jumps > threshold))[0] + 1
    return spike_idx, threshold


def _interpolate_spikes(arr, spike_idx, window=3):
    out = arr.copy()
    n = len(out)
    for idx in spike_idx:
        lo = max(0, idx - window)
        hi = min(n, idx + window + 1)
        mask = np.ones(hi - lo, dtype=bool)
        center = idx - lo
        mask[max(0, center - 1):min(len(mask), center + 2)] = False
        neighbors = out[lo:hi][mask]
        good = neighbors[np.isfinite(neighbors)]
        if len(good) > 0:
            out[idx] = np.mean(good)
    return out


def _clean_residuals(resid, sigma_mult=2.0):
    spike_idx, _ = _detect_spikes(resid, sigma_mult)
    cleaned = _interpolate_spikes(resid, spike_idx)
    return cleaned, spike_idx


def _compute_flux(p):
    df = p['df'].copy()
    bg_col = 'glucose' if 'glucose' in df.columns else 'sgv'
    bg = df[bg_col].values.astype(float)
    pk = p.get('pk')
    if pk is None:
        pk = np.zeros(len(bg))
    fd = compute_supply_demand(df, pk)
    supply = fd['supply']
    demand = fd['demand']
    hepatic = fd.get('hepatic', np.zeros_like(supply))
    carb_supply = fd.get('carb_supply', np.zeros_like(supply))
    n = min(len(bg), len(supply), len(demand), len(hepatic))
    bg = bg[:n]; supply = supply[:n]; demand = demand[:n]
    hepatic = hepatic[:n]
    carb_supply = carb_supply[:n] if len(carb_supply) >= n else np.zeros(n)
    bg_decay = (120.0 - bg) * 0.005
    flux_pred = bg[:-1] + supply[:-1] - demand[:-1] + hepatic[:-1] + bg_decay[:-1]
    resid = bg[1:] - flux_pred
    return {
        'bg': bg, 'supply': supply, 'demand': demand,
        'hepatic': hepatic, 'carb_supply': carb_supply,
        'resid': resid, 'n': n, 'df': df,
    }


def _build_features(resid, bg, demand, order=6, extra_cols=None):
    n = len(resid)
    n_base = order + 4
    n_extra = extra_cols.shape[1] if extra_cols is not None else 0
    X = np.zeros((n, n_base + n_extra))
    for lag in range(1, order + 1):
        X[lag:, lag - 1] = resid[:-lag]
    bg_c = bg[:n] - 120.0
    X[:, order] = bg_c ** 2 / 10000.0
    X[:, order + 1] = demand[:n] ** 2 / 1000.0
    X[:, order + 2] = bg_c * demand[:n] / 1000.0
    X[:, order + 3] = 1.0 / (1.0 + np.exp(-bg_c / 30.0)) - 0.5
    if extra_cols is not None:
        X[:, n_base:] = extra_cols[:n]
    return X


def _ridge_fit(X_train, y_train, alpha=1.0):
    mask = np.all(np.isfinite(X_train), axis=1) & np.isfinite(y_train)
    Xtr = X_train[mask]; ytr = y_train[mask]
    if len(Xtr) < X_train.shape[1] + 5:
        return np.zeros(X_train.shape[1])
    A = Xtr.T @ Xtr + alpha * np.eye(Xtr.shape[1])
    return np.linalg.solve(A, Xtr.T @ ytr)


def _ridge_fit_predict(X_train, y_train, X_test, y_test, alpha=1.0):
    mask_tr = np.all(np.isfinite(X_train), axis=1) & np.isfinite(y_train)
    mask_te = np.all(np.isfinite(X_test), axis=1)
    Xtr = X_train[mask_tr]; ytr = y_train[mask_tr]
    if len(Xtr) < X_train.shape[1] + 5:
        return np.nan, np.nan, np.zeros(X_train.shape[1])
    A = Xtr.T @ Xtr + alpha * np.eye(Xtr.shape[1])
    w = np.linalg.solve(A, Xtr.T @ ytr)
    pred = np.full(len(X_test), np.nan)
    pred[mask_te] = X_test[mask_te] @ w
    valid = mask_te & np.isfinite(y_test)
    if valid.sum() < 10:
        return np.nan, np.nan, w
    ss_res = np.sum((y_test[valid] - pred[valid]) ** 2)
    ss_tot = np.sum((y_test[valid] - np.mean(y_test[valid])) ** 2)
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan
    rmse = np.sqrt(ss_res / valid.sum())
    return r2, rmse, w


def _physics_sim(bg_start, supply, demand, hepatic, resid_start, ar_w, decay, n_steps):
    bg_sim = bg_start
    resid_est = resid_start
    for step in range(n_steps):
        if step >= len(supply):
            break
        bg_d = (120.0 - bg_sim) * 0.005
        bg_sim = bg_sim + supply[step] - demand[step] + hepatic[step] + bg_d
        bg_sim += ar_w * resid_est
        resid_est *= decay
    return bg_sim


def _compute_r2(preds, actuals):
    valid = np.isfinite(preds) & np.isfinite(actuals)
    if valid.sum() < 10:
        return np.nan
    ss_res = np.sum((actuals[valid] - preds[valid]) ** 2)
    ss_tot = np.sum((actuals[valid] - np.mean(actuals[valid])) ** 2)
    return 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan


# === Experiments ===

def exp_741_segmented_multi_day(patients, detail=False):
    """EXP-741: Predict daily mean BG and range instead of point values."""
    results = []

    for p in patients:
        fd = _compute_flux(p)
        resid_clean, _ = _clean_residuals(fd['resid'])
        bg = fd['bg']
        supply = fd['supply']
        demand = fd['demand']
        hepatic = fd['hepatic']
        n = fd['n']
        nr = len(resid_clean)

        # Compute daily statistics
        steps_per_day = 288
        n_days = n // steps_per_day
        if n_days < 10:
            continue

        daily_stats = []
        for d in range(n_days):
            start = d * steps_per_day
            end = min(start + steps_per_day, n)
            bg_day = bg[start:end]
            valid = bg_day[np.isfinite(bg_day)]
            if len(valid) < 100:
                continue

            sup_day = supply[start:end]
            dem_day = demand[start:end]
            hep_day = hepatic[start:end]
            resid_day = resid_clean[start:min(end, nr)]
            resid_valid = resid_day[np.isfinite(resid_day)] if len(resid_day) > 0 else np.array([0.0])

            daily_stats.append({
                'day': d,
                'mean_bg': float(np.mean(valid)),
                'std_bg': float(np.std(valid)),
                'min_bg': float(np.min(valid)),
                'max_bg': float(np.max(valid)),
                'tir': float(np.mean((valid >= 70) & (valid <= 180))),
                'mean_supply': float(np.mean(sup_day)),
                'mean_demand': float(np.mean(dem_day)),
                'mean_hepatic': float(np.mean(hep_day)),
                'mean_resid': float(np.mean(resid_valid)),
                'std_resid': float(np.std(resid_valid)),
            })

        if len(daily_stats) < 10:
            continue

        # Predict next-day mean BG from today's stats
        split_day = int(len(daily_stats) * 0.8)
        n_feat = 7
        X_daily = np.zeros((len(daily_stats) - 1, n_feat))
        y_daily = np.zeros(len(daily_stats) - 1)

        for i in range(len(daily_stats) - 1):
            ds = daily_stats[i]
            X_daily[i] = [ds['mean_bg'], ds['std_bg'], ds['mean_supply'],
                          ds['mean_demand'], ds['mean_hepatic'],
                          ds['mean_resid'], ds['tir']]
            y_daily[i] = daily_stats[i + 1]['mean_bg']

        r2_mean, rmse_mean, _ = _ridge_fit_predict(
            X_daily[:split_day], y_daily[:split_day],
            X_daily[split_day:], y_daily[split_day:], alpha=10.0)

        # Also predict 3-day and 7-day ahead
        r2_3d = np.nan
        r2_7d = np.nan
        if len(daily_stats) > split_day + 7:
            y_3d = np.full(len(daily_stats) - 3, np.nan)
            for i in range(len(daily_stats) - 3):
                y_3d[i] = np.mean([daily_stats[i+j+1]['mean_bg'] for j in range(3)])
            r2_3d, _, _ = _ridge_fit_predict(
                X_daily[:split_day], y_3d[:split_day],
                X_daily[split_day:len(y_3d)], y_3d[split_day:], alpha=10.0)

            y_7d = np.full(len(daily_stats) - 7, np.nan)
            for i in range(len(daily_stats) - 7):
                y_7d[i] = np.mean([daily_stats[i+j+1]['mean_bg'] for j in range(7)])
            if split_day < len(y_7d):
                r2_7d, _, _ = _ridge_fit_predict(
                    X_daily[:split_day], y_7d[:split_day],
                    X_daily[split_day:len(y_7d)], y_7d[split_day:], alpha=10.0)

        results.append({
            'patient': p['name'],
            'n_days': len(daily_stats),
            'r2_1d': float(r2_mean) if np.isfinite(r2_mean) else np.nan,
            'rmse_1d': float(rmse_mean) if np.isfinite(rmse_mean) else np.nan,
            'r2_3d': float(r2_3d) if np.isfinite(r2_3d) else np.nan,
            'r2_7d': float(r2_7d) if np.isfinite(r2_7d) else np.nan,
        })

    r2_1d_vals = [r['r2_1d'] for r in results if np.isfinite(r.get('r2_1d', np.nan))]
    r2_3d_vals = [r['r2_3d'] for r in results if np.isfinite(r.get('r2_3d', np.nan))]
    r2_7d_vals = [r['r2_7d'] for r in results if np.isfinite(r.get('r2_7d', np.nan))]

    return {
        'name': 'EXP-741 Segmented Multi-Day',
        'status': 'pass',
        'mean_r2_1d': float(np.mean(r2_1d_vals)) if r2_1d_vals else np.nan,
        'mean_r2_3d': float(np.mean(r2_3d_vals)) if r2_3d_vals else np.nan,
        'mean_r2_7d': float(np.mean(r2_7d_vals)) if r2_7d_vals else np.nan,
        'per_patient': results,
        'detail': f"1d R2={np.mean(r2_1d_vals):.3f}, 3d R2={np.mean(r2_3d_vals):.3f}, 7d R2={np.mean(r2_7d_vals):.3f}" if r2_1d_vals else "insufficient data"
    }


def exp_742_residual_autocorrelation(patients, detail=False):
    """EXP-742: PACF and spectral analysis of physics residuals."""
    results = []

    for p in patients:
        fd = _compute_flux(p)
        resid_clean, _ = _clean_residuals(fd['resid'])
        nr = len(resid_clean)
        valid = np.isfinite(resid_clean)
        resid_valid = resid_clean[valid]

        if len(resid_valid) < 500:
            continue

        # Autocorrelation at various lags
        acf_lags = [1, 2, 3, 6, 12, 24, 48, 72, 144, 288]  # 5min to 24h
        acf_values = {}
        mean_r = np.mean(resid_valid)
        var_r = np.var(resid_valid)
        for lag in acf_lags:
            if lag >= len(resid_valid):
                acf_values[lag] = np.nan
                continue
            cov = np.mean((resid_valid[:-lag] - mean_r) * (resid_valid[lag:] - mean_r))
            acf_values[lag] = float(cov / var_r) if var_r > 0 else 0.0

        # Spectral analysis via FFT (find dominant frequencies)
        n_fft = min(len(resid_valid), 8192)
        fft_vals = np.fft.rfft(resid_valid[:n_fft])
        power = np.abs(fft_vals) ** 2
        freqs = np.fft.rfftfreq(n_fft, d=5.0/60.0)  # in cycles/hour

        # Find peak frequencies (excluding DC)
        peak_idx = np.argsort(power[1:])[-5:] + 1
        peak_freqs = freqs[peak_idx]
        peak_periods_hours = 1.0 / peak_freqs
        peak_powers = power[peak_idx]

        # Circadian component (period 20-28h)
        circ_mask = (freqs > 1.0/28.0) & (freqs < 1.0/20.0)
        circ_power = float(np.sum(power[circ_mask]) / np.sum(power[1:])) if np.sum(power[1:]) > 0 else 0.0

        # Meal frequency component (period 4-8h)
        meal_mask = (freqs > 1.0/8.0) & (freqs < 1.0/4.0)
        meal_power = float(np.sum(power[meal_mask]) / np.sum(power[1:])) if np.sum(power[1:]) > 0 else 0.0

        results.append({
            'patient': p['name'],
            'acf': {str(k): float(v) for k, v in acf_values.items()},
            'circadian_power_frac': circ_power,
            'meal_power_frac': meal_power,
            'dominant_period_hours': float(peak_periods_hours[-1]) if len(peak_periods_hours) > 0 else np.nan,
            'acf_1step': float(acf_values.get(1, np.nan)),
            'acf_1h': float(acf_values.get(12, np.nan)),
            'acf_24h': float(acf_values.get(288, np.nan)),
        })

    mean_acf1 = np.mean([r['acf_1step'] for r in results if np.isfinite(r['acf_1step'])])
    mean_acf1h = np.mean([r['acf_1h'] for r in results if np.isfinite(r['acf_1h'])])
    mean_acf24h = np.mean([r['acf_24h'] for r in results if np.isfinite(r['acf_24h'])])
    mean_circ = np.mean([r['circadian_power_frac'] for r in results])
    mean_meal = np.mean([r['meal_power_frac'] for r in results])

    return {
        'name': 'EXP-742 Residual Autocorrelation',
        'status': 'pass',
        'mean_acf_1step': float(mean_acf1),
        'mean_acf_1h': float(mean_acf1h),
        'mean_acf_24h': float(mean_acf24h),
        'mean_circadian_power': float(mean_circ),
        'mean_meal_power': float(mean_meal),
        'per_patient': results,
        'detail': f"ACF: 1step={mean_acf1:.3f}, 1h={mean_acf1h:.3f}, 24h={mean_acf24h:.3f}, circ={mean_circ:.3f}, meal={mean_meal:.3f}"
    }


def exp_743_meta_ensemble(patients, detail=False):
    """EXP-743: Meta-ensemble combining direct blend + two-stage correction."""
    horizons = [1, 3, 6, 12]
    horizon_names = ['5min', '15min', '30min', '60min']
    results = {h: {'direct': [], 'twostage': [], 'meta': []} for h in horizon_names}

    for p in patients:
        fd = _compute_flux(p)
        resid_clean, _ = _clean_residuals(fd['resid'])
        bg = fd['bg']
        supply = fd['supply']
        demand = fd['demand']
        hepatic = fd['hepatic']
        n = fd['n']
        nr = len(resid_clean)
        split = int(n * 0.8)
        val_start = int(n * 0.6)

        X_ar1 = np.zeros((nr, 1))
        X_ar1[1:, 0] = resid_clean[:-1]
        w_ar1 = _ridge_fit(X_ar1[:split], resid_clean[:split], alpha=1.0)
        ar_coeff = w_ar1[0] if len(w_ar1) > 0 else 0.0

        X = _build_features(resid_clean, bg, demand, order=6)

        for h, hname in zip(horizons, horizon_names):
            y_ar = np.full(nr, np.nan)
            if h == 1:
                y_ar = resid_clean.copy()
            else:
                y_ar[:nr-h] = resid_clean[h:]
            _, _, w_ar = _ridge_fit_predict(X[:split], y_ar[:split], X[split:], y_ar[split:])

            # Collect physics residuals for two-stage on validation set
            phys_resids_val = []
            phys_pred_bg_val = []
            for t in range(val_start, split, 1):
                pred = _physics_sim(bg[t], supply[t:t+h], demand[t:t+h],
                                   hepatic[t:t+h],
                                   resid_clean[t] if t < nr else 0.0,
                                   ar_coeff, 0.95, h)
                if t + h < n:
                    phys_resids_val.append(bg[t + h] - pred)
                    phys_pred_bg_val.append(bg[t])

            phys_resids_arr = np.array(phys_resids_val) if phys_resids_val else np.zeros(1)
            n_val = len(phys_resids_arr)

            # Two-stage correction model
            X_corr = np.zeros((n_val, 4))
            for lag in range(1, 4):
                X_corr[lag:, lag-1] = phys_resids_arr[:-lag]
            X_corr[:, 3] = (np.array(phys_pred_bg_val[:n_val]) - 120.0) / 100.0
            corr_split = int(n_val * 0.8)
            w_corr = _ridge_fit(X_corr[:corr_split], phys_resids_arr[:corr_split], alpha=10.0)

            # Test set predictions from all three methods
            direct_preds, twostage_preds, meta_preds, actuals = [], [], [], []
            prev_phys_resids = np.zeros(3)

            for t in range(split, n - h, 3):
                if t + h >= n:
                    break

                # AR prediction
                if np.all(np.isfinite(X[t])):
                    ar_pred = bg[t] + X[t] @ w_ar
                else:
                    ar_pred = bg[t]

                # Physics prediction
                phys_pred = _physics_sim(
                    bg[t], supply[t:t+h], demand[t:t+h], hepatic[t:t+h],
                    resid_clean[t] if t < nr else 0.0, ar_coeff, 0.95, h)

                # Direct blend (50/50 or optimized)
                direct_pred = 0.5 * phys_pred + 0.5 * ar_pred

                # Two-stage corrected physics
                x_c = np.zeros(4)
                x_c[:3] = prev_phys_resids
                x_c[3] = (bg[t] - 120.0) / 100.0
                correction = x_c @ w_corr
                twostage_pred = phys_pred + correction

                # Meta-ensemble: average of direct blend and two-stage
                meta_pred = 0.5 * direct_pred + 0.5 * twostage_pred

                actual = bg[t + h]
                direct_preds.append(direct_pred)
                twostage_preds.append(twostage_pred)
                meta_preds.append(meta_pred)
                actuals.append(actual)

                # Update physics residual tracking
                prev_phys_resids = np.roll(prev_phys_resids, 1)
                prev_phys_resids[0] = actual - phys_pred

            acts = np.array(actuals)
            r2_direct = _compute_r2(np.array(direct_preds), acts)
            r2_twostage = _compute_r2(np.array(twostage_preds), acts)
            r2_meta = _compute_r2(np.array(meta_preds), acts)

            results[hname]['direct'].append(float(r2_direct) if np.isfinite(r2_direct) else np.nan)
            results[hname]['twostage'].append(float(r2_twostage) if np.isfinite(r2_twostage) else np.nan)
            results[hname]['meta'].append(float(r2_meta) if np.isfinite(r2_meta) else np.nan)

    summary = {}
    for hname in horizon_names:
        d = [v for v in results[hname]['direct'] if np.isfinite(v)]
        t = [v for v in results[hname]['twostage'] if np.isfinite(v)]
        m = [v for v in results[hname]['meta'] if np.isfinite(v)]
        summary[hname] = {
            'direct': float(np.mean(d)) if d else np.nan,
            'twostage': float(np.mean(t)) if t else np.nan,
            'meta': float(np.mean(m)) if m else np.nan,
        }

    return {
        'name': 'EXP-743 Meta-Ensemble',
        'status': 'pass',
        'summary': summary,
        'detail': ", ".join(f"{h}: dir={summary[h]['direct']:.3f}/2st={summary[h]['twostage']:.3f}/meta={summary[h]['meta']:.3f}" for h in horizon_names)
    }


def exp_744_state_dependent_blend(patients, detail=False):
    """EXP-744: Blend weight depends on metabolic state (meal, fasting, correction)."""
    horizons = [6, 12]
    horizon_names = ['30min', '60min']
    results = {h: {'uniform': [], 'state_dep': []} for h in horizon_names}

    for p in patients:
        fd = _compute_flux(p)
        resid_clean, _ = _clean_residuals(fd['resid'])
        bg = fd['bg']
        supply = fd['supply']
        demand = fd['demand']
        hepatic = fd['hepatic']
        carb_supply = fd['carb_supply']
        n = fd['n']
        nr = len(resid_clean)
        split = int(n * 0.8)

        X_ar1 = np.zeros((nr, 1))
        X_ar1[1:, 0] = resid_clean[:-1]
        w_ar1 = _ridge_fit(X_ar1[:split], resid_clean[:split], alpha=1.0)
        ar_coeff = w_ar1[0] if len(w_ar1) > 0 else 0.0

        X = _build_features(resid_clean, bg, demand, order=6)

        # Detect metabolic states
        def _get_state(t, lookback=12):
            """Classify metabolic state at time t."""
            cs_window = carb_supply[max(0, t-lookback):t+1]
            d_window = demand[max(0, t-lookback):t+1]
            bg_rate = bg[t] - bg[max(0, t-3)] if t >= 3 else 0
            if np.sum(cs_window) > 1.0:
                return 'meal'  # Recent carb activity
            elif np.mean(d_window) > np.median(demand) * 1.5:
                return 'correction'  # High insulin demand
            elif abs(bg_rate) < 2.0 and bg[t] > 70 and bg[t] < 180:
                return 'stable'  # Steady state in range
            else:
                return 'other'

        for h, hname in zip(horizons, horizon_names):
            y_ar = np.full(nr, np.nan)
            if h == 1:
                y_ar = resid_clean.copy()
            else:
                y_ar[:nr-h] = resid_clean[h:]
            _, _, w_ar = _ridge_fit_predict(X[:split], y_ar[:split], X[split:], y_ar[split:])

            # Calibration: find optimal blend per state on validation set
            val_start = int(n * 0.6)
            state_errors = {'meal': {'ar': [], 'phys': []},
                           'correction': {'ar': [], 'phys': []},
                           'stable': {'ar': [], 'phys': []},
                           'other': {'ar': [], 'phys': []}}

            for t in range(val_start, split, 3):
                if t + h >= n:
                    break
                state = _get_state(t)
                if np.all(np.isfinite(X[t])):
                    ar_pred = bg[t] + X[t] @ w_ar
                else:
                    ar_pred = bg[t]
                phys_pred = _physics_sim(
                    bg[t], supply[t:t+h], demand[t:t+h], hepatic[t:t+h],
                    resid_clean[t] if t < nr else 0.0, ar_coeff, 0.95, h)
                actual = bg[t + h]
                state_errors[state]['ar'].append((actual - ar_pred) ** 2)
                state_errors[state]['phys'].append((actual - phys_pred) ** 2)

            # Optimal per-state blend weights
            state_blend = {}
            for state in state_errors:
                ar_mse = np.mean(state_errors[state]['ar']) if state_errors[state]['ar'] else 1.0
                phys_mse = np.mean(state_errors[state]['phys']) if state_errors[state]['phys'] else 1.0
                total = ar_mse + phys_mse
                state_blend[state] = ar_mse / total if total > 0 else 0.5  # Weight toward lower-error method

            # Test set
            uniform_preds, state_dep_preds, actuals = [], [], []
            for t in range(split, n - h, 3):
                if t + h >= n:
                    break
                if np.all(np.isfinite(X[t])):
                    ar_pred = bg[t] + X[t] @ w_ar
                else:
                    ar_pred = bg[t]
                phys_pred = _physics_sim(
                    bg[t], supply[t:t+h], demand[t:t+h], hepatic[t:t+h],
                    resid_clean[t] if t < nr else 0.0, ar_coeff, 0.95, h)
                actual = bg[t + h]

                uniform_preds.append(0.5 * phys_pred + 0.5 * ar_pred)
                state = _get_state(t)
                w_phys = state_blend.get(state, 0.5)
                state_dep_preds.append(w_phys * phys_pred + (1 - w_phys) * ar_pred)
                actuals.append(actual)

            acts = np.array(actuals)
            r2_uni = _compute_r2(np.array(uniform_preds), acts)
            r2_sd = _compute_r2(np.array(state_dep_preds), acts)
            results[hname]['uniform'].append(float(r2_uni) if np.isfinite(r2_uni) else np.nan)
            results[hname]['state_dep'].append(float(r2_sd) if np.isfinite(r2_sd) else np.nan)

    summary = {}
    for hname in horizon_names:
        u = [v for v in results[hname]['uniform'] if np.isfinite(v)]
        s = [v for v in results[hname]['state_dep'] if np.isfinite(v)]
        summary[hname] = {
            'uniform': float(np.mean(u)) if u else np.nan,
            'state_dep': float(np.mean(s)) if s else np.nan,
        }

    return {
        'name': 'EXP-744 State-Dependent Blend',
        'status': 'pass',
        'summary': summary,
        'detail': ", ".join(f"{h}: uni={summary[h]['uniform']:.3f}/state={summary[h]['state_dep']:.3f}" for h in horizon_names)
    }


def exp_745_physics_residual_forecaster(patients, detail=False):
    """EXP-745: Multi-step AR forecaster on physics residuals."""
    horizons = [6, 12, 24]
    horizon_names = ['30min', '60min', '120min']
    results = {h: {'naive': [], 'ar_corrected': []} for h in horizon_names}

    for p in patients:
        fd = _compute_flux(p)
        resid_clean, _ = _clean_residuals(fd['resid'])
        bg = fd['bg']
        supply = fd['supply']
        demand = fd['demand']
        hepatic = fd['hepatic']
        n = fd['n']
        nr = len(resid_clean)
        split = int(n * 0.8)

        X_ar1 = np.zeros((nr, 1))
        X_ar1[1:, 0] = resid_clean[:-1]
        w_ar1 = _ridge_fit(X_ar1[:split], resid_clean[:split], alpha=1.0)
        ar_coeff = w_ar1[0] if len(w_ar1) > 0 else 0.0

        # Build physics residual series on training set
        phys_resids = np.full(n, np.nan)
        for t in range(1, split):
            pred_1step = _physics_sim(bg[t], supply[t:t+1], demand[t:t+1],
                                     hepatic[t:t+1],
                                     resid_clean[t] if t < nr else 0.0,
                                     ar_coeff, 0.95, 1)
            if t + 1 < n:
                phys_resids[t] = bg[t + 1] - pred_1step

        # AR model on physics residuals
        valid_pr = np.isfinite(phys_resids[:split])
        pr_clean = phys_resids.copy()
        pr_clean[~np.isfinite(pr_clean)] = 0.0

        for h, hname in zip(horizons, horizon_names):
            # Multi-step physics residual AR
            X_pr = np.zeros((split, 6))
            for lag in range(1, 7):
                X_pr[lag:, lag-1] = pr_clean[:split-lag]
            y_pr = np.full(split, np.nan)
            for t in range(h, split):
                if np.isfinite(phys_resids[t]):
                    y_pr[t-h] = phys_resids[t]  # h-step ahead physics residual
            w_pr = _ridge_fit(X_pr[:split-h], y_pr[:split-h], alpha=10.0)

            naive_preds, ar_corr_preds, actuals_list = [], [], []
            for t in range(split, n - h, 3):
                # Naive physics prediction (no correction)
                naive_pred = _physics_sim(
                    bg[t], supply[t:t+h], demand[t:t+h], hepatic[t:t+h],
                    resid_clean[t] if t < nr else 0.0, ar_coeff, 0.95, h)

                # AR-corrected physics prediction
                x_pr_t = np.zeros(6)
                for lag in range(1, 7):
                    if t - lag >= 0 and np.isfinite(pr_clean[t - lag]):
                        x_pr_t[lag-1] = pr_clean[t - lag]
                correction = x_pr_t @ w_pr if np.all(np.isfinite(x_pr_t)) else 0.0
                ar_corr_pred = naive_pred + correction

                if t + h < n:
                    naive_preds.append(naive_pred)
                    ar_corr_preds.append(ar_corr_pred)
                    actuals_list.append(bg[t + h])

            acts = np.array(actuals_list)
            r2_naive = _compute_r2(np.array(naive_preds), acts)
            r2_corr = _compute_r2(np.array(ar_corr_preds), acts)
            results[hname]['naive'].append(float(r2_naive) if np.isfinite(r2_naive) else np.nan)
            results[hname]['ar_corrected'].append(float(r2_corr) if np.isfinite(r2_corr) else np.nan)

    summary = {}
    for hname in horizon_names:
        nv = [v for v in results[hname]['naive'] if np.isfinite(v)]
        ac = [v for v in results[hname]['ar_corrected'] if np.isfinite(v)]
        summary[hname] = {
            'naive': float(np.mean(nv)) if nv else np.nan,
            'ar_corrected': float(np.mean(ac)) if ac else np.nan,
        }

    return {
        'name': 'EXP-745 Physics Residual Forecaster',
        'status': 'pass',
        'summary': summary,
        'detail': ", ".join(f"{h}: naive={summary[h]['naive']:.3f}/corr={summary[h]['ar_corrected']:.3f}" for h in horizon_names)
    }


def exp_746_basal_assessment_v2(patients, detail=False):
    """EXP-746: Overnight physics residual integral for basal adequacy."""
    results = []

    for p in patients:
        fd = _compute_flux(p)
        resid_clean, _ = _clean_residuals(fd['resid'])
        bg = fd['bg']
        supply = fd['supply']
        demand = fd['demand']
        carb_supply = fd['carb_supply']
        n = fd['n']
        nr = len(resid_clean)

        # Find overnight segments: midnight to 6am (steps 0-72 in day)
        # with NO carb supply (fasting)
        steps_per_day = 288
        n_days = n // steps_per_day
        overnight_analyses = []

        for d in range(n_days):
            start = d * steps_per_day  # midnight
            end = min(start + 72, n)  # 6am
            if end - start < 50:
                continue

            # Check for no carb activity
            cs_seg = carb_supply[start:end]
            if np.sum(cs_seg) > 0.5:
                continue  # Skip nights with carbs

            # Also skip if significant bolus demand
            dem_seg = demand[start:end]
            if np.max(dem_seg) > np.median(demand) * 2:
                continue  # Skip correction nights

            resid_seg = resid_clean[start:min(end, nr)]
            bg_seg = bg[start:end]
            valid_r = np.isfinite(resid_seg)
            valid_bg = np.isfinite(bg_seg)

            if valid_r.sum() < 30 or valid_bg.sum() < 30:
                continue

            overnight_analyses.append({
                'day': d,
                'resid_integral': float(np.sum(resid_seg[valid_r])),
                'resid_mean': float(np.mean(resid_seg[valid_r])),
                'bg_drift': float(bg_seg[valid_bg][-1] - bg_seg[valid_bg][0]),
                'bg_mean': float(np.mean(bg_seg[valid_bg])),
                'bg_std': float(np.std(bg_seg[valid_bg])),
            })

        if len(overnight_analyses) >= 5:
            resid_integrals = [o['resid_integral'] for o in overnight_analyses]
            bg_drifts = [o['bg_drift'] for o in overnight_analyses]
            bg_means = [o['bg_mean'] for o in overnight_analyses]

            mean_resid = float(np.mean(resid_integrals))
            mean_drift = float(np.mean(bg_drifts))
            mean_bg = float(np.mean(bg_means))

            # Assessment: positive drift = basal too low, negative = too high
            if mean_drift > 10:
                assessment = 'too_low'
            elif mean_drift < -10:
                assessment = 'too_high'
            else:
                assessment = 'appropriate'

            results.append({
                'patient': p['name'],
                'n_nights': len(overnight_analyses),
                'mean_resid_integral': mean_resid,
                'mean_bg_drift': mean_drift,
                'mean_overnight_bg': mean_bg,
                'assessment': assessment,
            })

    assessments = [r['assessment'] for r in results]
    assessment_counts = {a: assessments.count(a) for a in set(assessments)}

    return {
        'name': 'EXP-746 Basal Assessment v2',
        'status': 'pass',
        'assessment_counts': assessment_counts,
        'per_patient': results,
        'detail': f"n={len(results)}, " + ", ".join(f"{k}={v}" for k, v in assessment_counts.items())
    }


def exp_747_isf_response_validation(patients, detail=False):
    """EXP-747: Compare ISF from profile vs ISF from physics correction events."""
    results = []

    for p in patients:
        fd = _compute_flux(p)
        resid_clean, _ = _clean_residuals(fd['resid'])
        bg = fd['bg']
        supply = fd['supply']
        demand = fd['demand']
        carb_supply = fd['carb_supply']
        n = fd['n']
        nr = len(resid_clean)
        df = fd['df']

        # Get profile ISF
        isf_schedule = df.attrs.get('isf_schedule', df.attrs.get('sens', []))
        if not isf_schedule:
            continue
        profile_isf = float(isf_schedule[0]['value'] if isinstance(isf_schedule[0], dict) else isf_schedule[0])
        if profile_isf < 15:
            profile_isf *= 18.0182  # mmol/L → mg/dL

        # Find correction events (high demand, no carbs, BG dropping)
        correction_events = []
        for t in range(24, n - 36):
            # High demand, no recent carbs, BG > 150
            if (demand[t] > np.percentile(demand, 75) and
                np.sum(carb_supply[max(0,t-12):t+1]) < 0.5 and
                bg[t] > 150):
                # Measure BG drop over next 2 hours
                end_t = min(t + 24, n)
                bg_drop = bg[t] - bg[end_t - 1]
                demand_integral = np.sum(demand[t:end_t])

                if demand_integral > 0.5 and bg_drop > 5:
                    effective_isf = bg_drop / (demand_integral / profile_isf * 0.1)  # Approximate
                    correction_events.append({
                        'time': t,
                        'bg_start': float(bg[t]),
                        'bg_drop': float(bg_drop),
                        'demand_integral': float(demand_integral),
                        'effective_isf_approx': float(effective_isf) if np.isfinite(effective_isf) else np.nan,
                    })

        if len(correction_events) >= 5:
            effective_isfs = [e['effective_isf_approx'] for e in correction_events
                            if np.isfinite(e['effective_isf_approx']) and 0 < e['effective_isf_approx'] < 500]
            if len(effective_isfs) >= 5:
                results.append({
                    'patient': p['name'],
                    'profile_isf': float(profile_isf),
                    'effective_isf_mean': float(np.mean(effective_isfs)),
                    'effective_isf_std': float(np.std(effective_isfs)),
                    'n_corrections': len(effective_isfs),
                    'ratio': float(np.mean(effective_isfs) / profile_isf) if profile_isf > 0 else np.nan,
                })

    mean_ratio = np.mean([r['ratio'] for r in results if np.isfinite(r.get('ratio', np.nan))]) if results else np.nan

    return {
        'name': 'EXP-747 ISF Response Validation',
        'status': 'pass',
        'mean_effective_to_profile_ratio': float(mean_ratio),
        'per_patient': results,
        'detail': f"n_patients={len(results)}, mean ISF ratio (effective/profile)={mean_ratio:.2f}"
    }


def exp_748_unannounced_meal_detection(patients, detail=False):
    """EXP-748: Detect unannounced meals from large positive physics residual bursts."""
    results = []

    for p in patients:
        fd = _compute_flux(p)
        resid_clean, _ = _clean_residuals(fd['resid'])
        bg = fd['bg']
        supply = fd['supply']
        carb_supply = fd['carb_supply']
        n = fd['n']
        nr = len(resid_clean)

        # Detect large positive residual bursts (BG rising faster than model predicts)
        # This suggests unmodeled glucose input = unannounced carbs
        resid_std = np.nanstd(resid_clean)
        threshold = 2.0 * resid_std

        # Rolling sum of positive residuals (30min window)
        window = 6
        resid_pos = np.maximum(resid_clean, 0)
        rolling_pos = np.convolve(resid_pos, np.ones(window), mode='same')

        burst_threshold = threshold * window * 0.5
        burst_starts = np.where(rolling_pos > burst_threshold)[0]

        # Cluster into events
        events = []
        if len(burst_starts) > 0:
            current = [burst_starts[0]]
            for i in range(1, len(burst_starts)):
                if burst_starts[i] - burst_starts[i-1] <= 12:
                    current.append(burst_starts[i])
                else:
                    events.append(current[0])
                    current = [burst_starts[i]]
            events.append(current[0])

        # Classify each event: announced (has carb_supply) or unannounced
        announced = 0
        unannounced = 0
        for ev in events:
            lookback = 6  # 30min before
            lookahead = 12  # 60min after
            start = max(0, ev - lookback)
            end = min(n, ev + lookahead)
            cs_around = np.sum(carb_supply[start:end])
            if cs_around > 0.5:
                announced += 1
            else:
                unannounced += 1

        total = announced + unannounced
        results.append({
            'patient': p['name'],
            'total_events': total,
            'announced': announced,
            'unannounced': unannounced,
            'unannounced_frac': float(unannounced / total) if total > 0 else 0.0,
            'events_per_day': total / (n / 288) if n > 0 else 0,
        })

    mean_unanno_frac = np.mean([r['unannounced_frac'] for r in results]) if results else np.nan
    total_events = sum(r['total_events'] for r in results)
    total_unanno = sum(r['unannounced'] for r in results)

    return {
        'name': 'EXP-748 Unannounced Meal Detection',
        'status': 'pass',
        'total_events': total_events,
        'total_unannounced': total_unanno,
        'mean_unannounced_frac': float(mean_unanno_frac),
        'per_patient': results,
        'detail': f"total={total_events}, unannounced={total_unanno} ({mean_unanno_frac:.1%})"
    }


def exp_749_hybrid_for_classification(patients, detail=False):
    """EXP-749: Use hybrid prediction errors as features for hypo prediction."""
    results = []

    for p in patients:
        fd = _compute_flux(p)
        resid_clean, _ = _clean_residuals(fd['resid'])
        bg = fd['bg']
        supply = fd['supply']
        demand = fd['demand']
        hepatic = fd['hepatic']
        n = fd['n']
        nr = len(resid_clean)
        split = int(n * 0.8)

        X_ar1 = np.zeros((nr, 1))
        X_ar1[1:, 0] = resid_clean[:-1]
        w_ar1 = _ridge_fit(X_ar1[:split], resid_clean[:split], alpha=1.0)
        ar_coeff = w_ar1[0] if len(w_ar1) > 0 else 0.0

        X = _build_features(resid_clean, bg, demand, order=6)
        y_ar_6 = np.full(nr, np.nan)
        y_ar_6[:nr-6] = resid_clean[6:]
        _, _, w_ar = _ridge_fit_predict(X[:split], y_ar_6[:split], X[split:], y_ar_6[split:])

        # Build classification dataset: predict hypo (<70) in next 30min
        hypo_threshold = 70.0
        h = 6  # 30min

        # Features: recent residuals, physics prediction, AR prediction, BG trend
        n_feat = 8
        X_cls = np.zeros((n - h, n_feat))
        y_cls = np.zeros(n - h)

        for t in range(n - h):
            # BG features
            X_cls[t, 0] = bg[t]
            X_cls[t, 1] = bg[t] - bg[max(0, t-3)] if t >= 3 else 0  # 15min trend
            X_cls[t, 2] = bg[t] - bg[max(0, t-6)] if t >= 6 else 0  # 30min trend

            # Physics prediction
            phys_pred = _physics_sim(bg[t], supply[t:t+h], demand[t:t+h],
                                    hepatic[t:t+h],
                                    resid_clean[t] if t < nr else 0.0,
                                    ar_coeff, 0.95, h)
            X_cls[t, 3] = phys_pred
            X_cls[t, 4] = phys_pred - bg[t]  # Predicted change

            # AR prediction
            if t < nr and np.all(np.isfinite(X[t])):
                X_cls[t, 5] = bg[t] + X[t] @ w_ar
            else:
                X_cls[t, 5] = bg[t]

            # Residual features
            X_cls[t, 6] = resid_clean[t] if t < nr else 0.0
            X_cls[t, 7] = demand[t]

            # Label
            future_min = np.min(bg[t+1:t+h+1])
            y_cls[t] = 1.0 if future_min < hypo_threshold else 0.0

        # Split and evaluate with logistic-like approach (ridge on binary)
        split_cls = int(len(X_cls) * 0.8)

        # Baseline: BG only (features 0-2)
        w_base = _ridge_fit(X_cls[:split_cls, :3], y_cls[:split_cls], alpha=1.0)
        pred_base = X_cls[split_cls:, :3] @ w_base
        y_test = y_cls[split_cls:]

        # Full: all features including physics
        w_full = _ridge_fit(X_cls[:split_cls], y_cls[:split_cls], alpha=1.0)
        pred_full = X_cls[split_cls:] @ w_full

        # Evaluate with AUC approximation
        def _simple_auc(preds, labels):
            pos = preds[labels > 0.5]
            neg = preds[labels < 0.5]
            if len(pos) == 0 or len(neg) == 0:
                return np.nan
            concordant = sum(p > n for p in pos for n in neg)
            total = len(pos) * len(neg)
            return concordant / total if total > 0 else np.nan

        auc_base = _simple_auc(pred_base, y_test)
        auc_full = _simple_auc(pred_full, y_test)
        hypo_rate = float(np.mean(y_cls))

        results.append({
            'patient': p['name'],
            'auc_baseline': float(auc_base) if np.isfinite(auc_base) else np.nan,
            'auc_with_physics': float(auc_full) if np.isfinite(auc_full) else np.nan,
            'hypo_rate': hypo_rate,
        })

    mean_auc_base = np.mean([r['auc_baseline'] for r in results if np.isfinite(r.get('auc_baseline', np.nan))])
    mean_auc_full = np.mean([r['auc_with_physics'] for r in results if np.isfinite(r.get('auc_with_physics', np.nan))])

    return {
        'name': 'EXP-749 Hybrid for Classification',
        'status': 'pass',
        'mean_auc_baseline': float(mean_auc_base),
        'mean_auc_with_physics': float(mean_auc_full),
        'delta_auc': float(mean_auc_full - mean_auc_base),
        'per_patient': results,
        'detail': f"AUC: baseline={mean_auc_base:.3f}, +physics={mean_auc_full:.3f}, Δ={mean_auc_full - mean_auc_base:.3f}"
    }


def exp_750_production_ensemble(patients, detail=False):
    """EXP-750: Full optimized production ensemble pipeline with benchmarks."""
    import time as time_mod
    horizons = [1, 3, 6, 12]
    horizon_names = ['5min', '15min', '30min', '60min']
    results = {h: [] for h in horizon_names}
    latencies = []

    for p in patients:
        fd = _compute_flux(p)
        resid_clean, _ = _clean_residuals(fd['resid'])
        bg = fd['bg']
        supply = fd['supply']
        demand = fd['demand']
        hepatic = fd['hepatic']
        n = fd['n']
        nr = len(resid_clean)
        split = int(n * 0.8)

        # Production setup: fit once on training data
        X_ar1 = np.zeros((nr, 1))
        X_ar1[1:, 0] = resid_clean[:-1]
        w_ar1 = _ridge_fit(X_ar1[:split], resid_clean[:split], alpha=1.0)
        ar_coeff = w_ar1[0] if len(w_ar1) > 0 else 0.0

        X = _build_features(resid_clean, bg, demand, order=6)

        # Per-horizon AR weights and optimal blend (from validation)
        val_start = int(n * 0.6)
        horizon_config = {}

        for h, hname in zip(horizons, horizon_names):
            y_ar = np.full(nr, np.nan)
            if h == 1:
                y_ar = resid_clean.copy()
            else:
                y_ar[:nr-h] = resid_clean[h:]
            _, _, w_ar = _ridge_fit_predict(X[:split], y_ar[:split], X[split:], y_ar[split:])

            # Find optimal blend on validation set
            best_blend = 0.5
            best_r2 = -np.inf
            for blend in [0.0, 0.25, 0.5, 0.75, 1.0]:
                preds_v, acts_v = [], []
                for t in range(val_start, split, 6):
                    if t + h >= n:
                        break
                    ar_p = bg[t] + X[t] @ w_ar if np.all(np.isfinite(X[t])) else bg[t]
                    ph_p = _physics_sim(bg[t], supply[t:t+h], demand[t:t+h],
                                       hepatic[t:t+h],
                                       resid_clean[t] if t < nr else 0.0,
                                       ar_coeff, 0.95, h)
                    preds_v.append(blend * ph_p + (1 - blend) * ar_p)
                    acts_v.append(bg[t + h])
                r2 = _compute_r2(np.array(preds_v), np.array(acts_v))
                if np.isfinite(r2) and r2 > best_r2:
                    best_r2 = r2
                    best_blend = blend
            horizon_config[hname] = {'w_ar': w_ar, 'blend': best_blend}

        # Production test: measure latency and accuracy
        for h, hname in zip(horizons, horizon_names):
            cfg = horizon_config[hname]
            preds, acts = [], []
            for t in range(split, n - h, 3):
                t0 = time_mod.perf_counter_ns()

                ar_p = bg[t] + X[t] @ cfg['w_ar'] if np.all(np.isfinite(X[t])) else bg[t]
                ph_p = _physics_sim(bg[t], supply[t:t+h], demand[t:t+h],
                                   hepatic[t:t+h],
                                   resid_clean[t] if t < nr else 0.0,
                                   ar_coeff, 0.95, h)
                pred = cfg['blend'] * ph_p + (1 - cfg['blend']) * ar_p

                elapsed_ns = time_mod.perf_counter_ns() - t0
                latencies.append(elapsed_ns)

                if t + h < n:
                    preds.append(pred)
                    acts.append(bg[t + h])

            r2 = _compute_r2(np.array(preds), np.array(acts))
            rmse = float(np.sqrt(np.mean((np.array(preds) - np.array(acts)) ** 2)))
            mae = float(np.mean(np.abs(np.array(preds) - np.array(acts))))
            results[hname].append({
                'patient': p['name'], 'r2': float(r2) if np.isfinite(r2) else np.nan,
                'rmse': rmse, 'mae': mae, 'blend': cfg['blend']
            })

    summary = {}
    for hname in horizon_names:
        r2s = [r['r2'] for r in results[hname] if np.isfinite(r.get('r2', np.nan))]
        rmses = [r['rmse'] for r in results[hname]]
        maes = [r['mae'] for r in results[hname]]
        blends = [r['blend'] for r in results[hname]]
        summary[hname] = {
            'mean_r2': float(np.mean(r2s)) if r2s else np.nan,
            'mean_rmse': float(np.mean(rmses)) if rmses else np.nan,
            'mean_mae': float(np.mean(maes)) if maes else np.nan,
            'mean_blend': float(np.mean(blends)),
        }

    mean_latency_us = np.mean(latencies) / 1000.0 if latencies else np.nan
    p99_latency_us = np.percentile(latencies, 99) / 1000.0 if latencies else np.nan

    return {
        'name': 'EXP-750 Production Ensemble',
        'status': 'pass',
        'summary': summary,
        'mean_latency_us': float(mean_latency_us),
        'p99_latency_us': float(p99_latency_us),
        'detail': f"latency={mean_latency_us:.0f}μs, " + ", ".join(f"{h}: R2={summary[h]['mean_r2']:.3f}/RMSE={summary[h]['mean_rmse']:.1f}" for h in horizon_names)
    }


# === Runner ===

EXPERIMENTS = [
    ('EXP-741', 'Segmented Multi-Day', exp_741_segmented_multi_day,
     'EXP-741: Predict daily mean BG and range instead of point values.'),
    ('EXP-742', 'Residual Autocorrelation', exp_742_residual_autocorrelation,
     'EXP-742: PACF and spectral analysis of physics residuals.'),
    ('EXP-743', 'Meta-Ensemble', exp_743_meta_ensemble,
     'EXP-743: Meta-ensemble combining direct blend + two-stage correction.'),
    ('EXP-744', 'State-Dependent Blend', exp_744_state_dependent_blend,
     'EXP-744: Blend weight depends on metabolic state (meal, fasting, correction).'),
    ('EXP-745', 'Physics Residual Forecaster', exp_745_physics_residual_forecaster,
     'EXP-745: Multi-step AR forecaster on physics residuals.'),
    ('EXP-746', 'Basal Assessment v2', exp_746_basal_assessment_v2,
     'EXP-746: Overnight physics residual integral for basal adequacy.'),
    ('EXP-747', 'ISF Response Validation', exp_747_isf_response_validation,
     'EXP-747: Compare ISF from profile vs ISF from physics correction events.'),
    ('EXP-748', 'Unannounced Meal Detection', exp_748_unannounced_meal_detection,
     'EXP-748: Detect unannounced meals from large positive physics residual bursts.'),
    ('EXP-749', 'Hybrid for Classification', exp_749_hybrid_for_classification,
     'EXP-749: Use hybrid prediction errors as features for hypo prediction.'),
    ('EXP-750', 'Production Ensemble', exp_750_production_ensemble,
     'EXP-750: Full optimized production ensemble pipeline with benchmarks.'),
]


def run_all(patients, detail=False, save=False, only=None):
    results_all = []
    passed = 0
    failed = 0

    for exp_id, short_name, func, desc in EXPERIMENTS:
        if only and exp_id != only:
            continue
        print(f"\n{'='*60}")
        print(f"Running {exp_id}: {desc}")
        print(f"{'='*60}")
        t0 = time.time()
        try:
            res = func(patients, detail=detail)
            elapsed = time.time() - t0
            res['elapsed'] = elapsed
            res['exp_id'] = exp_id
            status = res.get('status', 'pass')
            print(f"  Status: {status} ({elapsed:.1f}s)")
            print(f"  Detail: {res.get('detail', 'N/A')}")
            results_all.append(res)
            passed += 1
        except Exception as e:
            elapsed = time.time() - t0
            print(f"  FAILED ({elapsed:.1f}s): {e}")
            traceback.print_exc()
            results_all.append({
                'exp_id': exp_id, 'name': short_name,
                'status': 'fail', 'error': str(e), 'elapsed': elapsed
            })
            failed += 1

    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")
    print(f"Passed: {passed}/{passed+failed}, Failed: {failed}/{passed+failed}")
    for r in results_all:
        marker = 'V' if r.get('status') == 'pass' else 'X'
        detail_str = r.get('detail', r.get('error', 'N/A'))
        print(f"  {marker} {r['exp_id']} {r.get('name', '')}: {detail_str[:80]}")

    if save:
        save_dir = Path(__file__).parent.parent.parent / "externals" / "experiments"
        save_dir.mkdir(parents=True, exist_ok=True)
        for r in results_all:
            eid = r['exp_id'].lower().replace('-', '_')
            short = r.get('name', '').lower().replace(' ', '_')[:25]
            fname = f"{eid}_{short}.json" if short else f"{eid}.json"
            with open(save_dir / fname, 'w') as f:
                json.dump(r, f, indent=2, default=str)
            print(f"  Saved: {fname}")

    return results_all


def main():
    parser = argparse.ArgumentParser(description="EXP-741-750: Residual Structure & Production")
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--max-patients', type=int, default=11)
    parser.add_argument('--only', type=str, default=None)
    args = parser.parse_args()

    print(f"Loading patients (max={args.max_patients})...")
    patients = load_patients(PATIENTS_DIR, max_patients=args.max_patients)
    print(f"Loaded {len(patients)} patients\n")

    run_all(patients, detail=args.detail, save=args.save, only=args.only)


if __name__ == '__main__':
    main()
