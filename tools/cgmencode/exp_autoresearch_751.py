#!/usr/bin/env python3
"""EXP-751-760: Advanced Clinical Intelligence & Settings Assessment.

Key findings from EXP-741-750:
- Meta-ensemble best: 30min R2=0.805, 60min R2=0.477
- 46.5% of glucose rises are unannounced meals
- Physics features boost hypo AUC by +0.176
- Effective ISF = 2.91x profile ISF
- 5/8 patients have insufficient basal

This wave focuses on:
- Weighted meta-ensemble optimization
- Unannounced meal size estimation
- Comprehensive settings assessment (basal + CR + ISF)
- Dawn phenomenon quantification
- Per-patient settings quality report
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


# === shared utilities (same as prior waves) ===
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

def exp_751_weighted_meta_ensemble(patients, detail=False):
    """EXP-751: Optimize meta weights instead of 50/50."""
    horizons = [1, 3, 6, 12]
    horizon_names = ['5min', '15min', '30min', '60min']
    meta_weights = [0.0, 0.25, 0.33, 0.5, 0.67, 0.75, 1.0]
    results = {h: {} for h in horizon_names}

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

        # Two-stage correction calibration
        phys_resids_val = []
        phys_bg_val = []
        for t in range(val_start, split):
            pred = _physics_sim(bg[t], supply[t:t+1], demand[t:t+1],
                               hepatic[t:t+1], resid_clean[t] if t < nr else 0.0,
                               ar_coeff, 0.95, 1)
            if t + 1 < n:
                phys_resids_val.append(bg[t + 1] - pred)
                phys_bg_val.append(bg[t])
        phys_resids_arr = np.array(phys_resids_val) if phys_resids_val else np.zeros(10)
        n_val = len(phys_resids_arr)
        X_corr = np.zeros((n_val, 4))
        for lag in range(1, 4):
            X_corr[lag:, lag-1] = phys_resids_arr[:-lag]
        X_corr[:, 3] = (np.array(phys_bg_val[:n_val]) - 120.0) / 100.0
        corr_split = int(n_val * 0.8)
        w_corr = _ridge_fit(X_corr[:corr_split], phys_resids_arr[:corr_split], alpha=10.0)

        for h, hname in zip(horizons, horizon_names):
            y_ar = np.full(nr, np.nan)
            if h == 1:
                y_ar = resid_clean.copy()
            else:
                y_ar[:nr-h] = resid_clean[h:]
            _, _, w_ar = _ridge_fit_predict(X[:split], y_ar[:split], X[split:], y_ar[split:])

            prev_phys_resids = np.zeros(3)
            for mw in meta_weights:
                preds_mw, acts_mw = [], []
                prev_pr = np.zeros(3)
                for t in range(split, n - h, 3):
                    if t + h >= n:
                        break
                    ar_pred = bg[t] + X[t] @ w_ar if np.all(np.isfinite(X[t])) else bg[t]
                    phys_pred = _physics_sim(bg[t], supply[t:t+h], demand[t:t+h],
                                           hepatic[t:t+h], resid_clean[t] if t < nr else 0.0,
                                           ar_coeff, 0.95, h)
                    direct = 0.5 * phys_pred + 0.5 * ar_pred
                    x_c = np.zeros(4)
                    x_c[:3] = prev_pr
                    x_c[3] = (bg[t] - 120.0) / 100.0
                    twostage = phys_pred + x_c @ w_corr
                    meta = mw * direct + (1 - mw) * twostage
                    preds_mw.append(meta)
                    acts_mw.append(bg[t + h])
                    prev_pr = np.roll(prev_pr, 1)
                    prev_pr[0] = bg[t + h] - phys_pred

                r2 = _compute_r2(np.array(preds_mw), np.array(acts_mw))
                key = f'mw_{mw:.2f}'
                if key not in results[hname]:
                    results[hname][key] = []
                results[hname][key].append(float(r2) if np.isfinite(r2) else np.nan)

    summary = {}
    for hname in horizon_names:
        best_mw = 0.5
        best_r2 = -np.inf
        for mw in meta_weights:
            key = f'mw_{mw:.2f}'
            vals = [v for v in results[hname].get(key, []) if np.isfinite(v)]
            mr2 = float(np.mean(vals)) if vals else np.nan
            if np.isfinite(mr2) and mr2 > best_r2:
                best_r2 = mr2
                best_mw = mw
        summary[hname] = {'best_mw': best_mw, 'best_r2': best_r2}

    return {
        'name': 'EXP-751 Weighted Meta-Ensemble',
        'status': 'pass',
        'summary': summary,
        'detail': ", ".join(f"{h}: mw={summary[h]['best_mw']:.2f}/R2={summary[h]['best_r2']:.3f}" for h in horizon_names)
    }


def exp_752_physics_confidence(patients, detail=False):
    """EXP-752: Per-prediction confidence score based on recent physics accuracy."""
    results = []
    h = 6  # 30min horizon

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

        # Track rolling physics errors
        rolling_window = 50
        phys_errors = []
        confident_preds, confident_acts = [], []
        uncertain_preds, uncertain_acts = [], []

        for t in range(split, n - h, 1):
            if t + h >= n:
                break
            phys_pred = _physics_sim(bg[t], supply[t:t+h], demand[t:t+h],
                                   hepatic[t:t+h], resid_clean[t] if t < nr else 0.0,
                                   ar_coeff, 0.95, h)
            actual = bg[t + h]
            error = abs(actual - phys_pred)
            phys_errors.append(error)

            if len(phys_errors) >= rolling_window:
                recent_mae = np.mean(phys_errors[-rolling_window:])
                median_mae = np.median(phys_errors)
                if recent_mae < median_mae:
                    confident_preds.append(phys_pred)
                    confident_acts.append(actual)
                else:
                    uncertain_preds.append(phys_pred)
                    uncertain_acts.append(actual)

        r2_conf = _compute_r2(np.array(confident_preds), np.array(confident_acts))
        r2_uncert = _compute_r2(np.array(uncertain_preds), np.array(uncertain_acts))

        results.append({
            'patient': p['name'],
            'r2_confident': float(r2_conf) if np.isfinite(r2_conf) else np.nan,
            'r2_uncertain': float(r2_uncert) if np.isfinite(r2_uncert) else np.nan,
            'n_confident': len(confident_preds),
            'n_uncertain': len(uncertain_preds),
        })

    mean_conf = np.mean([r['r2_confident'] for r in results if np.isfinite(r.get('r2_confident', np.nan))])
    mean_uncert = np.mean([r['r2_uncertain'] for r in results if np.isfinite(r.get('r2_uncertain', np.nan))])

    return {
        'name': 'EXP-752 Physics Confidence',
        'status': 'pass',
        'mean_r2_confident': float(mean_conf),
        'mean_r2_uncertain': float(mean_uncert),
        'per_patient': results,
        'detail': f"confident R2={mean_conf:.3f}, uncertain R2={mean_uncert:.3f}, gap={mean_conf-mean_uncert:.3f}"
    }


def exp_753_unannounced_meal_size(patients, detail=False):
    """EXP-753: Estimate unannounced carb grams from residual integral."""
    results = []

    for p in patients:
        fd = _compute_flux(p)
        resid_clean, _ = _clean_residuals(fd['resid'])
        bg = fd['bg']
        supply = fd['supply']
        carb_supply = fd['carb_supply']
        n = fd['n']
        nr = len(resid_clean)
        df = fd['df']

        # Get CR from profile for conversion
        cr_schedule = df.attrs.get('carb_ratio_schedule', df.attrs.get('carbratio', []))
        if not cr_schedule:
            continue
        cr_val = float(cr_schedule[0]['value'] if isinstance(cr_schedule[0], dict) else cr_schedule[0])

        resid_std = np.nanstd(resid_clean)
        threshold = 2.0 * resid_std

        # Detect positive residual bursts
        resid_pos = np.maximum(resid_clean, 0)
        window = 6
        rolling_pos = np.convolve(resid_pos, np.ones(window), mode='same')
        burst_threshold = threshold * window * 0.5
        burst_starts = np.where(rolling_pos > burst_threshold)[0]

        events = []
        if len(burst_starts) > 0:
            current = [burst_starts[0]]
            for i in range(1, len(burst_starts)):
                if burst_starts[i] - burst_starts[i-1] <= 12:
                    current.append(burst_starts[i])
                else:
                    events.append((current[0], current[-1]))
                    current = [burst_starts[i]]
            events.append((current[0], current[-1]))

        announced_sizes = []
        unannounced_sizes = []
        for ev_start, ev_end in events:
            lookback = 6
            lookahead = 36  # 3h absorption window
            cs_start = max(0, ev_start - lookback)
            cs_end = min(n, ev_start + lookahead)
            cs_total = np.sum(carb_supply[cs_start:cs_end])

            # Residual integral as proxy for glucose excess
            r_start = ev_start
            r_end = min(nr, ev_start + lookahead)
            resid_integral = float(np.sum(resid_clean[r_start:r_end]))

            # Convert residual integral to approximate carb grams
            # Rough calibration: 1g carb raises BG by ~(ISF/CR) mg/dL
            # Integrate over absorption window: residual_sum * 5min / (ISF/CR)
            # Simplified: estimated_carbs = resid_integral * CR / ISF_approx
            isf_approx = 50.0  # rough average ISF
            estimated_carbs = abs(resid_integral) * cr_val / isf_approx if isf_approx > 0 else 0

            if cs_total > 0.5:
                announced_sizes.append({
                    'announced_carbs': float(cs_total / cr_val * 10) if cr_val > 0 else 0,
                    'estimated_carbs': float(estimated_carbs),
                    'resid_integral': resid_integral,
                })
            else:
                unannounced_sizes.append({
                    'estimated_carbs': float(estimated_carbs),
                    'resid_integral': resid_integral,
                })

        if len(unannounced_sizes) >= 3:
            est_carbs = [u['estimated_carbs'] for u in unannounced_sizes]
            results.append({
                'patient': p['name'],
                'n_announced': len(announced_sizes),
                'n_unannounced': len(unannounced_sizes),
                'mean_unannounced_carbs': float(np.mean(est_carbs)),
                'median_unannounced_carbs': float(np.median(est_carbs)),
                'std_unannounced_carbs': float(np.std(est_carbs)),
            })

    mean_carbs = np.mean([r['mean_unannounced_carbs'] for r in results]) if results else np.nan
    median_carbs = np.mean([r['median_unannounced_carbs'] for r in results]) if results else np.nan

    return {
        'name': 'EXP-753 Unannounced Meal Size',
        'status': 'pass',
        'mean_estimated_carbs': float(mean_carbs),
        'median_estimated_carbs': float(median_carbs),
        'per_patient': results,
        'detail': f"n_patients={len(results)}, mean est. carbs={mean_carbs:.1f}g, median={median_carbs:.1f}g"
    }


def exp_754_basal_optimization(patients, detail=False):
    """EXP-754: Find optimal basal rate adjustment from overnight physics residuals."""
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

        steps_per_day = 288
        n_days = n // steps_per_day
        overnight_drifts = []

        for d in range(n_days):
            start = d * steps_per_day  # midnight
            end = min(start + 72, n)  # 6am
            if end - start < 50:
                continue
            if np.sum(carb_supply[start:end]) > 0.5:
                continue
            if np.max(demand[start:end]) > np.median(demand) * 2:
                continue

            bg_seg = bg[start:end]
            valid = np.isfinite(bg_seg)
            if valid.sum() < 30:
                continue

            # Linear regression: BG = a*t + b over overnight
            t_arr = np.arange(valid.sum()).astype(float)
            bg_valid = bg_seg[valid]
            if len(t_arr) < 20:
                continue
            slope = (np.mean(t_arr * bg_valid) - np.mean(t_arr) * np.mean(bg_valid)) / \
                    (np.mean(t_arr**2) - np.mean(t_arr)**2 + 1e-10)
            overnight_drifts.append({
                'day': d,
                'slope_per_5min': float(slope),
                'slope_per_hour': float(slope * 12),
                'start_bg': float(bg_seg[valid][0]),
                'end_bg': float(bg_seg[valid][-1]),
            })

        if len(overnight_drifts) >= 5:
            slopes = [o['slope_per_hour'] for o in overnight_drifts]
            mean_slope = float(np.mean(slopes))

            # Optimal basal adjustment: positive slope means basal too low
            # Each mg/dL/hour of drift suggests basal needs ~adjustment
            # ISF: 1U insulin changes BG by ~50 mg/dL, so drift/ISF_approx = U/h adjustment
            isf_approx = 50.0
            basal_adjustment_u_h = mean_slope / isf_approx

            results.append({
                'patient': p['name'],
                'n_nights': len(overnight_drifts),
                'mean_slope_per_hour': mean_slope,
                'std_slope': float(np.std(slopes)),
                'basal_adjustment_u_h': float(basal_adjustment_u_h),
                'assessment': 'increase' if mean_slope > 2 else ('decrease' if mean_slope < -2 else 'appropriate'),
            })

    return {
        'name': 'EXP-754 Basal Optimization',
        'status': 'pass',
        'per_patient': results,
        'detail': f"n={len(results)}, " + ", ".join(f"{r['patient']}={r['assessment']}({r['mean_slope_per_hour']:.1f}mg/dL/h)" for r in results[:6])
    }


def exp_755_cr_validation(patients, detail=False):
    """EXP-755: Compare announced CR vs effective CR from post-meal physics analysis."""
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

        cr_schedule = df.attrs.get('carb_ratio_schedule', df.attrs.get('carbratio', []))
        if not cr_schedule:
            continue
        profile_cr = float(cr_schedule[0]['value'] if isinstance(cr_schedule[0], dict) else cr_schedule[0])

        # Find meals with clear response
        cs_diff = np.diff(carb_supply)
        meal_starts = np.where(cs_diff > 0.5)[0]
        meals = []
        if len(meal_starts) > 0:
            cur = [meal_starts[0]]
            for i in range(1, len(meal_starts)):
                if meal_starts[i] - meal_starts[i-1] <= 6:
                    cur.append(meal_starts[i])
                else:
                    meals.append(cur[0])
                    cur = [meal_starts[i]]
            meals.append(cur[0])

        meal_analyses = []
        for m in meals:
            window = 36  # 3h
            if m + window >= n or m < 6:
                continue
            # Total carb supply in window
            total_supply = float(np.sum(carb_supply[m:m+window]))
            # Total demand (insulin) in window
            total_demand = float(np.sum(demand[m:m+window]))
            # BG excursion
            bg_peak = float(np.max(bg[m:min(m+window, n)]))
            bg_start = float(bg[m])
            bg_excursion = bg_peak - bg_start
            # Residual integral
            resid_int = float(np.sum(resid_clean[m:min(m+window, nr)])) if m + window <= nr else np.nan

            if total_supply > 1 and total_demand > 0.1:
                # Effective CR: how many grams of carb-equivalent per unit of insulin
                effective_cr_proxy = total_supply / total_demand * 10  # scaled proxy
                meal_analyses.append({
                    'supply': total_supply,
                    'demand': total_demand,
                    'excursion': bg_excursion,
                    'resid_integral': resid_int,
                    'effective_cr_proxy': effective_cr_proxy,
                })

        if len(meal_analyses) >= 10:
            excursions = [m['excursion'] for m in meal_analyses]
            resid_ints = [m['resid_integral'] for m in meal_analyses if np.isfinite(m['resid_integral'])]
            cr_proxies = [m['effective_cr_proxy'] for m in meal_analyses]

            results.append({
                'patient': p['name'],
                'profile_cr': profile_cr,
                'n_meals': len(meal_analyses),
                'mean_excursion': float(np.mean(excursions)),
                'mean_resid_integral': float(np.mean(resid_ints)) if resid_ints else np.nan,
                'mean_cr_proxy': float(np.mean(cr_proxies)),
                'cr_assessment': 'too_high' if np.mean(excursions) > 50 else ('too_low' if np.mean(excursions) < -10 else 'appropriate'),
            })

    return {
        'name': 'EXP-755 CR Validation',
        'status': 'pass',
        'per_patient': results,
        'detail': f"n={len(results)}, " + ", ".join(f"{r['patient']}={r['cr_assessment']}(exc={r['mean_excursion']:.0f})" for r in results[:6])
    }


def exp_756_insulin_stacking_v2(patients, detail=False):
    """EXP-756: Use physics demand integral to detect insulin stacking risk."""
    results = []

    for p in patients:
        fd = _compute_flux(p)
        resid_clean, _ = _clean_residuals(fd['resid'])
        bg = fd['bg']
        demand = fd['demand']
        n = fd['n']

        # Rolling demand integral (IOB proxy) over 4h window
        iob_window = 48  # 4 hours
        rolling_iob = np.convolve(demand, np.ones(iob_window), mode='same')

        # Detect high IOB events (> 2x median)
        iob_threshold = np.median(rolling_iob) * 2
        high_iob_mask = rolling_iob > iob_threshold

        # Count stacking events and their outcomes
        stacking_events = []
        i = 0
        while i < n:
            if high_iob_mask[i]:
                start = i
                while i < n and high_iob_mask[i]:
                    i += 1
                end = i
                # Check if hypo follows within 2h
                check_end = min(end + 24, n)
                min_bg_after = float(np.min(bg[end:check_end])) if check_end > end else 200.0
                stacking_events.append({
                    'start': start,
                    'duration_steps': end - start,
                    'peak_iob': float(np.max(rolling_iob[start:end])),
                    'min_bg_after': min_bg_after,
                    'led_to_hypo': min_bg_after < 70,
                })
            else:
                i += 1

        if stacking_events:
            n_hypo = sum(1 for e in stacking_events if e['led_to_hypo'])
            results.append({
                'patient': p['name'],
                'n_stacking_events': len(stacking_events),
                'n_led_to_hypo': n_hypo,
                'hypo_conversion_rate': float(n_hypo / len(stacking_events)),
                'mean_peak_iob': float(np.mean([e['peak_iob'] for e in stacking_events])),
            })

    total_events = sum(r['n_stacking_events'] for r in results)
    total_hypo = sum(r['n_led_to_hypo'] for r in results)
    mean_conversion = total_hypo / total_events if total_events > 0 else 0

    return {
        'name': 'EXP-756 Insulin Stacking v2',
        'status': 'pass',
        'total_stacking_events': total_events,
        'total_hypo_conversions': total_hypo,
        'mean_conversion_rate': float(mean_conversion),
        'per_patient': results,
        'detail': f"events={total_events}, hypo={total_hypo}, rate={mean_conversion:.1%}"
    }


def exp_757_noise_vs_signal(patients, detail=False):
    """EXP-757: Separate sensor noise from metabolic signal in consecutive readings."""
    results = []

    for p in patients:
        fd = _compute_flux(p)
        resid_clean, _ = _clean_residuals(fd['resid'])
        bg = fd['bg']
        n = fd['n']
        nr = len(resid_clean)

        # Allan variance-style analysis: variance at different time scales
        scales = [1, 2, 3, 6, 12, 24, 48, 144, 288]
        scale_names = ['5min', '10min', '15min', '30min', '1h', '2h', '4h', '12h', '24h']
        variances = {}

        for scale, sname in zip(scales, scale_names):
            if scale >= nr:
                variances[sname] = np.nan
                continue
            diffs = resid_clean[scale:] - resid_clean[:-scale]
            valid = np.isfinite(diffs)
            if valid.sum() < 100:
                variances[sname] = np.nan
            else:
                variances[sname] = float(np.var(diffs[valid]) / 2)  # Allan variance

        # Sensor noise estimate: variance of consecutive differences / 2
        consec_diffs = np.diff(bg)
        valid_cd = np.isfinite(consec_diffs)
        sensor_noise_var = float(np.var(consec_diffs[valid_cd]) / 2) if valid_cd.sum() > 100 else np.nan

        # Total residual variance
        valid_r = np.isfinite(resid_clean)
        total_var = float(np.var(resid_clean[valid_r])) if valid_r.sum() > 100 else np.nan

        # Noise fraction
        noise_frac = sensor_noise_var / total_var if total_var and total_var > 0 else np.nan

        results.append({
            'patient': p['name'],
            'sensor_noise_var': sensor_noise_var,
            'total_resid_var': total_var,
            'noise_fraction': float(noise_frac) if np.isfinite(noise_frac) else np.nan,
            'allan_variances': variances,
        })

    mean_noise_frac = np.mean([r['noise_fraction'] for r in results if np.isfinite(r.get('noise_fraction', np.nan))])

    return {
        'name': 'EXP-757 Noise vs Signal',
        'status': 'pass',
        'mean_noise_fraction': float(mean_noise_frac),
        'per_patient': results,
        'detail': f"noise_frac={mean_noise_frac:.3f} ({mean_noise_frac*100:.1f}% of residual is sensor noise)"
    }


def exp_758_dawn_phenomenon(patients, detail=False):
    """EXP-758: Quantify dawn effect from 4-8am physics residuals in fasting segments."""
    results = []

    for p in patients:
        fd = _compute_flux(p)
        resid_clean, _ = _clean_residuals(fd['resid'])
        bg = fd['bg']
        carb_supply = fd['carb_supply']
        n = fd['n']
        nr = len(resid_clean)

        steps_per_day = 288
        n_days = n // steps_per_day
        dawn_effects = []

        for d in range(n_days):
            # Dawn window: 4am-8am = steps 48-96 in day
            dawn_start = d * steps_per_day + 48
            dawn_end = min(d * steps_per_day + 96, n)
            # Pre-dawn reference: midnight-4am = steps 0-48
            pre_start = d * steps_per_day
            pre_end = d * steps_per_day + 48

            if dawn_end > nr or pre_end > nr:
                continue
            if np.sum(carb_supply[pre_start:dawn_end]) > 0.5:
                continue

            dawn_resid = resid_clean[dawn_start:dawn_end]
            pre_resid = resid_clean[pre_start:pre_end]
            dawn_bg = bg[dawn_start:min(dawn_end, n)]
            pre_bg = bg[pre_start:min(pre_end, n)]

            dv = dawn_resid[np.isfinite(dawn_resid)]
            pv = pre_resid[np.isfinite(pre_resid)]
            dbv = dawn_bg[np.isfinite(dawn_bg)]
            pbv = pre_bg[np.isfinite(pre_bg)]

            if len(dv) > 20 and len(pv) > 20 and len(dbv) > 20 and len(pbv) > 20:
                dawn_effects.append({
                    'day': d,
                    'dawn_resid_mean': float(np.mean(dv)),
                    'pre_resid_mean': float(np.mean(pv)),
                    'dawn_bg_mean': float(np.mean(dbv)),
                    'pre_bg_mean': float(np.mean(pbv)),
                    'bg_rise': float(np.mean(dbv) - np.mean(pbv)),
                    'resid_rise': float(np.mean(dv) - np.mean(pv)),
                })

        if len(dawn_effects) >= 5:
            bg_rises = [d['bg_rise'] for d in dawn_effects]
            resid_rises = [d['resid_rise'] for d in dawn_effects]
            results.append({
                'patient': p['name'],
                'n_nights': len(dawn_effects),
                'mean_bg_rise': float(np.mean(bg_rises)),
                'std_bg_rise': float(np.std(bg_rises)),
                'mean_resid_rise': float(np.mean(resid_rises)),
                'has_dawn_effect': float(np.mean(bg_rises)) > 5,
            })

    dawn_patients = sum(1 for r in results if r['has_dawn_effect'])
    mean_rise = np.mean([r['mean_bg_rise'] for r in results]) if results else np.nan

    return {
        'name': 'EXP-758 Dawn Phenomenon',
        'status': 'pass',
        'n_with_dawn': dawn_patients,
        'n_total': len(results),
        'mean_bg_rise': float(mean_rise),
        'per_patient': results,
        'detail': f"{dawn_patients}/{len(results)} patients have dawn effect, mean rise={mean_rise:.1f} mg/dL"
    }


def exp_759_exercise_recovery(patients, detail=False):
    """EXP-759: Characterize post-exercise glucose dynamics from anomalous demand drops."""
    results = []

    for p in patients:
        fd = _compute_flux(p)
        resid_clean, _ = _clean_residuals(fd['resid'])
        bg = fd['bg']
        demand = fd['demand']
        supply = fd['supply']
        n = fd['n']
        nr = len(resid_clean)

        # Detect exercise-like events: BG drop > 3 mg/dL/5min without high demand
        bg_rate = np.zeros(n)
        bg_rate[1:] = np.diff(bg)

        window = 12
        exercise_events = []
        for start in range(0, n - window * 3, window):
            end = min(start + window, n)
            mean_rate = np.mean(bg_rate[start:end])
            mean_demand = np.mean(demand[start:end])

            if mean_rate < -3.0 and mean_demand < np.median(demand) * 1.5:
                # Potential exercise window - track recovery
                recovery_start = end
                recovery_end = min(end + 48, n)  # 4h recovery
                if recovery_end > n:
                    continue

                recovery_bg = bg[recovery_start:recovery_end]
                valid = np.isfinite(recovery_bg)
                if valid.sum() < 20:
                    continue

                exercise_events.append({
                    'time': start,
                    'drop_rate': float(mean_rate),
                    'nadir_bg': float(np.min(bg[start:recovery_end])),
                    'recovery_1h': float(bg[min(recovery_start + 12, n-1)] - bg[recovery_start]) if recovery_start + 12 < n else np.nan,
                    'recovery_2h': float(bg[min(recovery_start + 24, n-1)] - bg[recovery_start]) if recovery_start + 24 < n else np.nan,
                })

        if len(exercise_events) >= 5:
            results.append({
                'patient': p['name'],
                'n_events': len(exercise_events),
                'mean_drop_rate': float(np.mean([e['drop_rate'] for e in exercise_events])),
                'mean_nadir': float(np.mean([e['nadir_bg'] for e in exercise_events])),
                'mean_recovery_1h': float(np.mean([e['recovery_1h'] for e in exercise_events if np.isfinite(e['recovery_1h'])])),
                'mean_recovery_2h': float(np.mean([e['recovery_2h'] for e in exercise_events if np.isfinite(e['recovery_2h'])])),
            })

    total_events = sum(r['n_events'] for r in results)
    mean_recovery = np.mean([r['mean_recovery_1h'] for r in results]) if results else np.nan

    return {
        'name': 'EXP-759 Exercise Recovery',
        'status': 'pass',
        'total_events': total_events,
        'mean_1h_recovery': float(mean_recovery),
        'per_patient': results,
        'detail': f"n_patients={len(results)}, events={total_events}, 1h recovery={mean_recovery:.1f} mg/dL"
    }


def exp_760_comprehensive_settings(patients, detail=False):
    """EXP-760: Per-patient comprehensive settings assessment report."""
    results = []

    for p in patients:
        fd = _compute_flux(p)
        resid_clean, _ = _clean_residuals(fd['resid'])
        bg = fd['bg']
        supply = fd['supply']
        demand = fd['demand']
        carb_supply = fd['carb_supply']
        hepatic = fd['hepatic']
        n = fd['n']
        nr = len(resid_clean)
        df = fd['df']

        # === Basal Score ===
        steps_per_day = 288
        n_days = n // steps_per_day
        overnight_slopes = []
        for d in range(n_days):
            start = d * steps_per_day
            end = min(start + 72, n)
            if end - start < 50 or np.sum(carb_supply[start:end]) > 0.5:
                continue
            bg_seg = bg[start:end]
            valid = np.isfinite(bg_seg)
            if valid.sum() < 30:
                continue
            t_arr = np.arange(valid.sum()).astype(float)
            bg_v = bg_seg[valid]
            denom = np.mean(t_arr**2) - np.mean(t_arr)**2 + 1e-10
            slope = (np.mean(t_arr * bg_v) - np.mean(t_arr) * np.mean(bg_v)) / denom
            overnight_slopes.append(slope * 12)  # per hour

        basal_score = 50.0
        if len(overnight_slopes) >= 3:
            mean_slope = abs(np.mean(overnight_slopes))
            basal_score = max(0, min(100, 100 - mean_slope * 10))

        # === CR Score ===
        cs_diff = np.diff(carb_supply)
        meal_starts = np.where(cs_diff > 0.5)[0]
        meals = []
        if len(meal_starts) > 0:
            cur = [meal_starts[0]]
            for i in range(1, len(meal_starts)):
                if meal_starts[i] - meal_starts[i-1] <= 6:
                    cur.append(meal_starts[i])
                else:
                    meals.append(cur[0])
                    cur = [meal_starts[i]]
            meals.append(cur[0])

        meal_excursions = []
        for m in meals:
            if m + 36 >= n:
                continue
            peak = float(np.max(bg[m:m+36]))
            excursion = peak - bg[m]
            meal_excursions.append(excursion)

        cr_score = 50.0
        if len(meal_excursions) >= 5:
            mean_exc = np.mean(meal_excursions)
            cr_score = max(0, min(100, 100 - abs(mean_exc - 30) * 1.5))

        # === ISF Score ===
        correction_excursions = []
        for t in range(12, n - 24):
            if demand[t] > np.percentile(demand, 80) and np.sum(carb_supply[max(0,t-6):t+1]) < 0.5 and bg[t] > 150:
                bg_drop = bg[t] - bg[min(t+24, n-1)]
                correction_excursions.append(bg_drop)

        isf_score = 50.0
        if len(correction_excursions) >= 5:
            mean_drop = np.mean(correction_excursions)
            isf_score = max(0, min(100, 100 - abs(mean_drop - 40) * 1.5))

        # === TIR Score ===
        valid_bg = bg[np.isfinite(bg)]
        tir = float(np.mean((valid_bg >= 70) & (valid_bg <= 180))) if len(valid_bg) > 100 else 0.5
        tir_score = tir * 100

        # === Overall ===
        overall = (basal_score + cr_score + isf_score + tir_score) / 4

        results.append({
            'patient': p['name'],
            'basal_score': float(basal_score),
            'cr_score': float(cr_score),
            'isf_score': float(isf_score),
            'tir_score': float(tir_score),
            'overall_score': float(overall),
            'n_nights': len(overnight_slopes),
            'n_meals': len(meal_excursions),
            'tir': float(tir),
        })

    mean_overall = np.mean([r['overall_score'] for r in results]) if results else np.nan

    return {
        'name': 'EXP-760 Comprehensive Settings',
        'status': 'pass',
        'mean_overall': float(mean_overall),
        'per_patient': results,
        'detail': f"mean={mean_overall:.1f}/100, " + ", ".join(f"{r['patient']}={r['overall_score']:.0f}" for r in results[:6])
    }


# === Runner ===
EXPERIMENTS = [
    ('EXP-751', 'Weighted Meta-Ensemble', exp_751_weighted_meta_ensemble,
     'EXP-751: Optimize meta weights instead of 50/50.'),
    ('EXP-752', 'Physics Confidence', exp_752_physics_confidence,
     'EXP-752: Per-prediction confidence score based on recent physics accuracy.'),
    ('EXP-753', 'Unannounced Meal Size', exp_753_unannounced_meal_size,
     'EXP-753: Estimate unannounced carb grams from residual integral.'),
    ('EXP-754', 'Basal Optimization', exp_754_basal_optimization,
     'EXP-754: Find optimal basal rate adjustment from overnight physics residuals.'),
    ('EXP-755', 'CR Validation', exp_755_cr_validation,
     'EXP-755: Compare announced CR vs effective CR from post-meal physics analysis.'),
    ('EXP-756', 'Insulin Stacking v2', exp_756_insulin_stacking_v2,
     'EXP-756: Use physics demand integral to detect insulin stacking risk.'),
    ('EXP-757', 'Noise vs Signal', exp_757_noise_vs_signal,
     'EXP-757: Separate sensor noise from metabolic signal in consecutive readings.'),
    ('EXP-758', 'Dawn Phenomenon', exp_758_dawn_phenomenon,
     'EXP-758: Quantify dawn effect from 4-8am physics residuals in fasting segments.'),
    ('EXP-759', 'Exercise Recovery', exp_759_exercise_recovery,
     'EXP-759: Characterize post-exercise glucose dynamics from anomalous demand drops.'),
    ('EXP-760', 'Comprehensive Settings', exp_760_comprehensive_settings,
     'EXP-760: Per-patient comprehensive settings assessment report.'),
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
    parser = argparse.ArgumentParser(description="EXP-751-760: Clinical Intelligence & Settings")
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
