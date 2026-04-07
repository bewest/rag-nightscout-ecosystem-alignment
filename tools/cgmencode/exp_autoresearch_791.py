#!/usr/bin/env python3
"""EXP-791–800: Advanced Integration & Multi-Scale Analysis

Combines breakthroughs from 280 prior experiments into integrated pipelines
and extends analysis to multi-week/multi-month scales.

EXP-791: Circadian + Hybrid Ensemble (combine two best approaches)
EXP-792: Physics-Informed Ridge Regression (proper ML with physics features)
EXP-793: Meal Size from Envelope Shape (estimate actual carb intake from BG trajectory)
EXP-794: Overnight Basal Auto-Tuner (iterative basal adjustment from drift)
EXP-795: Infusion Site Change Detection (detect site changes from residual jumps)
EXP-796: Multi-Week Trend Analysis (monthly settings drift)
EXP-797: Anomaly Detection Pipeline (flag unusual metabolic events)
EXP-798: AID Controller Characterization (model closed-loop response)
EXP-799: Circadian + Compliance + AR Integrated Pipeline
EXP-800: Final Integrated Prediction Benchmark
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

def _get_bg(df):
    col = 'glucose' if 'glucose' in df.columns else 'sgv'
    return df[col]

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

def register(exp_id, name):
    def decorator(func):
        EXPERIMENTS[exp_id] = {'name': name, 'func': func}
        return func
    return decorator


# ---------------------------------------------------------------------------
# EXP-791: Circadian + Hybrid Ensemble
# ---------------------------------------------------------------------------
@register('EXP-791', 'Circadian + Hybrid Ensemble')
def exp_791(patients, detail=False):
    """Combine circadian correction with hybrid physics+AR ensemble."""
    horizons = {1: '5min', 3: '15min', 6: '30min', 12: '60min'}
    results = {}

    for h_steps, h_name in horizons.items():
        r2_phys_only = []
        r2_hybrid = []
        r2_circ_hybrid = []

        for p in patients:
            fd = _compute_flux(p)
            bg = fd['bg']
            resid = fd['resid']
            n = fd['n']
            nr = len(resid)
            df = p['df']
            hours = _get_hours(df, n)
            if hours is None:
                continue

            n_pred = nr - h_steps
            if n_pred < 500:
                continue

            actual = bg[h_steps:h_steps + n_pred]

            # Physics prediction (subsampled)
            phys_pred = np.full(n_pred, np.nan)
            ar_pred = np.full(n_pred, np.nan)
            for i in range(0, n_pred, 3):
                phys_pred[i] = _physics_sim(
                    bg[i], fd['supply'][i:i+h_steps], fd['demand'][i:i+h_steps],
                    fd['hepatic'][i:i+h_steps], resid[i], 0.0, 0.95, h_steps)
                ar_pred[i] = _physics_sim(
                    bg[i], fd['supply'][i:i+h_steps], fd['demand'][i:i+h_steps],
                    fd['hepatic'][i:i+h_steps], resid[i], 0.15, 0.95, h_steps)

            # Train/val split
            split = int(n_pred * 0.7)

            # Circadian correction on hybrid residuals
            train_mask = np.isfinite(ar_pred[:split]) & np.isfinite(actual[:split])
            if train_mask.sum() < 100:
                continue

            train_error = actual[:split][train_mask] - ar_pred[:split][train_mask]
            train_h = hours[:split][train_mask]
            sin_h = np.sin(2 * np.pi * train_h / 24.0)
            cos_h = np.cos(2 * np.pi * train_h / 24.0)
            X = np.column_stack([sin_h, cos_h, np.ones(len(sin_h))])
            try:
                coeffs = np.linalg.lstsq(X, train_error, rcond=None)[0]
            except Exception:
                continue

            # Apply to validation
            val_mask = np.isfinite(ar_pred[split:]) & np.isfinite(actual[split:])
            if val_mask.sum() < 100:
                continue

            val_h = hours[split:split + n_pred - split][val_mask]
            correction = coeffs[0] * np.sin(2 * np.pi * val_h / 24.0) + \
                         coeffs[1] * np.cos(2 * np.pi * val_h / 24.0) + coeffs[2]

            val_actual = actual[split:][val_mask]
            val_phys = phys_pred[split:][val_mask]
            val_hybrid = ar_pred[split:][val_mask]
            val_circ = val_hybrid + correction

            r2_p = _r2(val_phys, val_actual)
            r2_h = _r2(val_hybrid, val_actual)
            r2_ch = _r2(val_circ, val_actual)

            if all(np.isfinite([r2_p, r2_h, r2_ch])):
                r2_phys_only.append(r2_p)
                r2_hybrid.append(r2_h)
                r2_circ_hybrid.append(r2_ch)

        mp = np.mean(r2_phys_only) if r2_phys_only else float('nan')
        mh = np.mean(r2_hybrid) if r2_hybrid else float('nan')
        mc = np.mean(r2_circ_hybrid) if r2_circ_hybrid else float('nan')
        results[h_name] = {
            'physics': round(mp, 3), 'hybrid': round(mh, 3),
            'circ_hybrid': round(mc, 3), 'delta_circ': round(mc - mh, 3),
        }

    detail_str = ', '.join(f'{h}: phys={v["physics"]}/hyb={v["hybrid"]}/circ={v["circ_hybrid"]}/Δ={v["delta_circ"]}'
                           for h, v in results.items())
    return {'status': 'pass', 'detail': detail_str, 'results': results}


# ---------------------------------------------------------------------------
# EXP-792: Physics-Informed Ridge Regression
# ---------------------------------------------------------------------------
@register('EXP-792', 'Physics Ridge Regression')
def exp_792(patients, detail=False):
    """Use ridge regression with physics features for proper ML prediction."""
    horizons = {6: '30min', 12: '60min'}
    results = {}

    for h_steps, h_name in horizons.items():
        r2_ar = []
        r2_ridge = []
        per_patient = []

        for p in patients:
            fd = _compute_flux(p)
            bg = fd['bg']
            resid = fd['resid']
            n = fd['n']
            nr = len(resid)
            df = p['df']
            hours = _get_hours(df, n)
            if hours is None:
                continue

            n_pred = nr - h_steps
            if n_pred < 500:
                continue

            actual = bg[h_steps:h_steps + n_pred]

            # Build feature matrix: [bg, supply_sum, demand_sum, hepatic_sum, resid, sin_h, cos_h]
            features = np.zeros((n_pred, 8))
            for i in range(n_pred):
                features[i, 0] = bg[i]
                features[i, 1] = np.sum(fd['supply'][i:i+h_steps])
                features[i, 2] = np.sum(fd['demand'][i:i+h_steps])
                features[i, 3] = np.sum(fd['hepatic'][i:i+h_steps])
                features[i, 4] = resid[i] if i < nr else 0
                if hours is not None:
                    features[i, 5] = np.sin(2 * np.pi * hours[i] / 24.0)
                    features[i, 6] = np.cos(2 * np.pi * hours[i] / 24.0)
                features[i, 7] = 1.0  # bias

            # Valid samples
            valid = np.isfinite(actual) & np.all(np.isfinite(features), axis=1)
            split = int(n_pred * 0.7)

            train_mask = valid[:split]
            val_mask = valid[split:]

            if train_mask.sum() < 200 or val_mask.sum() < 100:
                continue

            X_train = features[:split][train_mask]
            y_train = actual[:split][train_mask]
            X_val = features[split:][val_mask]
            y_val = actual[split:][val_mask]

            # Ridge regression: (X'X + λI)^-1 X'y
            lam = 1.0
            XtX = X_train.T @ X_train + lam * np.eye(X_train.shape[1])
            try:
                w = np.linalg.solve(XtX, X_train.T @ y_train)
            except np.linalg.LinAlgError:
                continue

            y_pred_ridge = X_val @ w

            # AR baseline
            ar_preds = np.full(val_mask.sum(), np.nan)
            val_indices = np.where(val_mask)[0]
            for idx_i, orig_i in enumerate(val_indices):
                j = split + orig_i
                ar_preds[idx_i] = _physics_sim(
                    bg[j], fd['supply'][j:j+h_steps], fd['demand'][j:j+h_steps],
                    fd['hepatic'][j:j+h_steps], resid[j] if j < nr else 0,
                    0.15, 0.95, h_steps)

            r2_a = _r2(ar_preds, y_val)
            r2_r = _r2(y_pred_ridge, y_val)

            if np.isfinite(r2_a) and np.isfinite(r2_r):
                r2_ar.append(r2_a)
                r2_ridge.append(r2_r)
                per_patient.append({
                    'patient': p['name'],
                    'ar_r2': round(r2_a, 3),
                    'ridge_r2': round(r2_r, 3),
                    'delta': round(r2_r - r2_a, 3),
                })

        mean_ar = np.mean(r2_ar) if r2_ar else float('nan')
        mean_ridge = np.mean(r2_ridge) if r2_ridge else float('nan')
        results[h_name] = {
            'ar': round(mean_ar, 3), 'ridge': round(mean_ridge, 3),
            'delta': round(mean_ridge - mean_ar, 3),
            'per_patient': per_patient,
        }

    detail_str = ', '.join(f'{h}: AR={v["ar"]}/Ridge={v["ridge"]}/Δ={v["delta"]}' for h, v in results.items())
    return {'status': 'pass', 'detail': detail_str, 'results': results}


# ---------------------------------------------------------------------------
# EXP-793: Meal Size from Envelope Shape
# ---------------------------------------------------------------------------
@register('EXP-793', 'Meal Size Estimation')
def exp_793(patients, detail=False):
    """Estimate actual carb intake from post-meal BG trajectory shape."""
    results = []

    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        supply = fd['supply']
        demand = fd['demand']
        n = fd['n']

        s_mean = np.nanmean(supply)
        s_std = np.nanstd(supply)

        meal_events = []
        i = 0
        while i < n - 36:
            if supply[i] > s_mean + 1.5 * s_std:
                # Large supply event = meal
                # Estimate meal size from supply integral (sum over absorption window)
                window = min(36, n - i)
                supply_integral = float(np.sum(supply[i:i+window]))
                demand_integral = float(np.sum(demand[i:i+window]))

                # BG trajectory features
                traj = bg[i:i+window] - bg[i]
                valid_traj = traj[np.isfinite(traj)]
                if len(valid_traj) < 12:
                    i += 36
                    continue

                peak_rise = float(np.nanmax(valid_traj))
                time_to_peak = int(np.nanargmax(valid_traj)) * 5  # minutes
                auc_3h = float(np.nansum(valid_traj)) * 5  # mg/dL * min

                meal_events.append({
                    'supply_integral': supply_integral,
                    'demand_integral': demand_integral,
                    'peak_rise': peak_rise,
                    'time_to_peak': time_to_peak,
                    'auc_3h': auc_3h,
                    'ratio': supply_integral / max(demand_integral, 0.1),
                })
                i += 36
            else:
                i += 1

        if len(meal_events) < 20:
            continue

        # Correlate supply integral with BG peak rise
        si = np.array([m['supply_integral'] for m in meal_events])
        pr = np.array([m['peak_rise'] for m in meal_events])
        auc = np.array([m['auc_3h'] for m in meal_events])

        valid = np.isfinite(si) & np.isfinite(pr) & np.isfinite(auc)
        if valid.sum() < 20:
            continue

        corr_peak = float(np.corrcoef(si[valid], pr[valid])[0, 1])
        corr_auc = float(np.corrcoef(si[valid], auc[valid])[0, 1])

        # Bin by meal size
        small = si < np.percentile(si, 33)
        large = si > np.percentile(si, 67)

        results.append({
            'patient': p['name'],
            'n_meals': len(meal_events),
            'corr_supply_peak': round(corr_peak, 3),
            'corr_supply_auc': round(corr_auc, 3),
            'small_meal_peak': round(float(np.nanmean(pr[small])), 1),
            'large_meal_peak': round(float(np.nanmean(pr[large])), 1),
            'mean_supply_ratio': round(float(np.mean([m['ratio'] for m in meal_events])), 2),
        })

    detail_parts = [f'{r["patient"]}: ρ_peak={r["corr_supply_peak"]}, ρ_auc={r["corr_supply_auc"]}, n={r["n_meals"]}'
                    for r in results[:8]]
    mean_corr = np.mean([r['corr_supply_peak'] for r in results]) if results else float('nan')
    return {
        'status': 'pass',
        'detail': f'n={len(results)}, mean ρ(supply,peak)={mean_corr:.3f}. ' + '; '.join(detail_parts),
        'per_patient': results,
    }


# ---------------------------------------------------------------------------
# EXP-794: Overnight Basal Auto-Tuner
# ---------------------------------------------------------------------------
@register('EXP-794', 'Basal Auto-Tuner')
def exp_794(patients, detail=False):
    """Iteratively tune basal rates using overnight drift analysis."""
    results = []

    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        supply = fd['supply']
        demand = fd['demand']
        hepatic = fd['hepatic']
        n = fd['n']
        df = p['df']
        hours = _get_hours(df, n)
        if hours is None:
            continue

        # Split into 24 hourly blocks, compute overnight drift
        hour_drift = {}
        for h in range(24):
            mask = (hours >= h) & (hours < h + 1)
            indices = np.where(mask)[0]
            if len(indices) < 50:
                continue

            # Mean BG change per 5min in this hour
            drifts = []
            for idx in indices:
                if idx + 1 < n and np.isfinite(bg[idx]) and np.isfinite(bg[idx+1]):
                    drifts.append(bg[idx+1] - bg[idx])
            if len(drifts) >= 20:
                hour_drift[h] = round(float(np.mean(drifts)), 2)

        if len(hour_drift) < 20:
            continue

        # Basal adjustment: if drift > 0, increase basal (more insulin needed)
        # if drift < 0, decrease basal
        # Assume 1 mg/dL/5min drift ≈ 0.05 U/hr basal adjustment
        adjustments = {}
        for h, drift in hour_drift.items():
            adj = drift * 0.05  # U/hr per mg/dL/5min drift
            adjustments[h] = round(adj, 3)

        # Overall drift metrics
        overnight_hours = [h for h in range(0, 6) if h in hour_drift]
        daytime_hours = [h for h in range(8, 20) if h in hour_drift]

        overnight_drift = np.mean([hour_drift[h] for h in overnight_hours]) if overnight_hours else 0
        daytime_drift = np.mean([hour_drift[h] for h in daytime_hours]) if daytime_hours else 0

        results.append({
            'patient': p['name'],
            'overnight_drift_mg5min': round(overnight_drift, 2),
            'daytime_drift_mg5min': round(daytime_drift, 2),
            'max_positive_hour': max(hour_drift, key=hour_drift.get) if hour_drift else -1,
            'max_negative_hour': min(hour_drift, key=hour_drift.get) if hour_drift else -1,
            'max_adj_Uhr': round(max(adjustments.values()), 3) if adjustments else 0,
            'n_hours': len(hour_drift),
        })

    detail_parts = [f'{r["patient"]}: ON={r["overnight_drift_mg5min"]:+.2f}, day={r["daytime_drift_mg5min"]:+.2f}'
                    for r in results[:8]]
    return {
        'status': 'pass',
        'detail': f'n={len(results)}. ' + '; '.join(detail_parts),
        'per_patient': results,
    }


# ---------------------------------------------------------------------------
# EXP-795: Infusion Site Change Detection
# ---------------------------------------------------------------------------
@register('EXP-795', 'Site Change Detection')
def exp_795(patients, detail=False):
    """Detect infusion site changes from residual jump patterns."""
    results = []

    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        resid = fd['resid']
        n = fd['n']
        nr = len(resid)

        # Compute rolling residual magnitude (2h windows)
        window = 24  # 2 hours
        rolling_resid = np.full(nr, np.nan)
        for i in range(window, nr):
            chunk = resid[i-window:i]
            valid = chunk[np.isfinite(chunk)]
            if len(valid) >= 12:
                rolling_resid[i] = np.mean(np.abs(valid))

        # Detect sudden drops in residual (site change = fresh cannula = better absorption)
        valid_rolling = rolling_resid[np.isfinite(rolling_resid)]
        if len(valid_rolling) < 100:
            continue

        threshold = np.percentile(valid_rolling, 25)  # Low residual = good absorption
        jumps = []
        for i in range(window + 1, nr - window):
            if not np.isfinite(rolling_resid[i]) or not np.isfinite(rolling_resid[i-1]):
                continue
            before = rolling_resid[i-1]
            after = rolling_resid[i]
            # Detect sudden improvement: residual drops by >30%
            if before > 0 and (before - after) / before > 0.30 and after < threshold:
                jumps.append({
                    'index': i,
                    'before': round(float(before), 2),
                    'after': round(float(after), 2),
                    'improvement_pct': round((before - after) / before * 100, 1),
                })

        # Filter: expect ~every 3 days = ~60 site changes in 180 days
        # Cluster nearby jumps (within 12h)
        clustered = []
        last_idx = -1000
        for j in jumps:
            if j['index'] - last_idx > 144:  # 12 hours apart
                clustered.append(j)
                last_idx = j['index']

        # Expected: 1 site change every 2-3 days = 60-90 in 180 days
        n_days = n / 288
        expected = n_days / 3

        results.append({
            'patient': p['name'],
            'n_jumps_raw': len(jumps),
            'n_jumps_clustered': len(clustered),
            'expected_changes': round(expected, 0),
            'detection_rate': round(len(clustered) / max(expected, 1) * 100, 1),
            'mean_improvement': round(np.mean([j['improvement_pct'] for j in clustered]), 1) if clustered else 0,
        })

    detail_parts = [f'{r["patient"]}: detected={r["n_jumps_clustered"]}/expected={r["expected_changes"]:.0f} ({r["detection_rate"]}%)'
                    for r in results[:8]]
    return {
        'status': 'pass',
        'detail': f'n={len(results)}. ' + '; '.join(detail_parts),
        'per_patient': results,
    }


# ---------------------------------------------------------------------------
# EXP-796: Multi-Week Trend Analysis
# ---------------------------------------------------------------------------
@register('EXP-796', 'Multi-Week Trends')
def exp_796(patients, detail=False):
    """Analyze weekly and monthly trends in settings effectiveness."""
    results = []

    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        resid = fd['resid']
        n = fd['n']
        nr = len(resid)

        # Split into 2-week windows
        window_size = 288 * 14  # 14 days
        windows = []
        for start in range(0, nr - window_size + 1, window_size):
            end = start + window_size
            chunk_bg = bg[start:end]
            chunk_resid = resid[start:end]

            valid_bg = chunk_bg[np.isfinite(chunk_bg)]
            valid_resid = chunk_resid[np.isfinite(chunk_resid)]

            if len(valid_bg) < 1000 or len(valid_resid) < 1000:
                continue

            tir = float(np.mean((valid_bg >= 70) & (valid_bg <= 180))) * 100
            mean_bg = float(np.mean(valid_bg))
            cv = float(np.std(valid_bg) / np.mean(valid_bg) * 100)
            mean_resid = float(np.mean(np.abs(valid_resid)))

            windows.append({
                'week': len(windows) * 2,
                'tir': round(tir, 1),
                'mean_bg': round(mean_bg, 1),
                'cv': round(cv, 1),
                'mean_abs_resid': round(mean_resid, 2),
            })

        if len(windows) < 4:
            continue

        # Trend analysis: linear regression on TIR and residual over time
        weeks = np.array([w['week'] for w in windows], dtype=float)
        tirs = np.array([w['tir'] for w in windows])
        resids = np.array([w['mean_abs_resid'] for w in windows])

        tir_trend = float(np.polyfit(weeks, tirs, 1)[0])  # TIR change per 2-week
        resid_trend = float(np.polyfit(weeks, resids, 1)[0])

        results.append({
            'patient': p['name'],
            'n_windows': len(windows),
            'tir_trend_per_2wk': round(tir_trend, 2),
            'resid_trend_per_2wk': round(resid_trend, 3),
            'first_tir': windows[0]['tir'],
            'last_tir': windows[-1]['tir'],
            'tir_change': round(windows[-1]['tir'] - windows[0]['tir'], 1),
            'improving': tir_trend > 0.5,
            'deteriorating': tir_trend < -0.5,
        })

    improving = sum(1 for r in results if r['improving'])
    deteriorating = sum(1 for r in results if r['deteriorating'])
    detail_parts = [f'{r["patient"]}: TIR {r["first_tir"]}→{r["last_tir"]}% ({"↑" if r["improving"] else "↓" if r["deteriorating"] else "→"})'
                    for r in results[:8]]
    return {
        'status': 'pass',
        'detail': f'n={len(results)}, {improving} improving, {deteriorating} deteriorating. ' + '; '.join(detail_parts),
        'per_patient': results,
    }


# ---------------------------------------------------------------------------
# EXP-797: Anomaly Detection Pipeline
# ---------------------------------------------------------------------------
@register('EXP-797', 'Anomaly Detection')
def exp_797(patients, detail=False):
    """Flag unusual metabolic events from physics residual patterns."""
    results = []

    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        resid = fd['resid']
        supply = fd['supply']
        demand = fd['demand']
        n = fd['n']
        nr = len(resid)

        valid_resid = resid[np.isfinite(resid)]
        if len(valid_resid) < 1000:
            continue

        resid_mean = np.nanmean(resid)
        resid_std = np.nanstd(resid)

        # Anomaly types
        anomalies = {
            'large_positive': 0,    # Unexpected BG rise (resid >> 0)
            'large_negative': 0,    # Unexpected BG drop (resid << 0)
            'sustained_high': 0,    # Consecutive high residuals (>1h)
            'supply_demand_gap': 0, # Large imbalance without explanation
        }

        # Point anomalies (>3σ)
        threshold = 3.0 * resid_std
        for i in range(nr):
            if not np.isfinite(resid[i]):
                continue
            if resid[i] > resid_mean + threshold:
                anomalies['large_positive'] += 1
            elif resid[i] < resid_mean - threshold:
                anomalies['large_negative'] += 1

        # Sustained anomalies (12+ consecutive steps with |resid| > 2σ)
        streak = 0
        for i in range(nr):
            if np.isfinite(resid[i]) and abs(resid[i] - resid_mean) > 2.0 * resid_std:
                streak += 1
                if streak >= 12:
                    anomalies['sustained_high'] += 1
                    streak = 0
            else:
                streak = 0

        # Supply-demand gap anomalies
        for i in range(n):
            if np.isfinite(supply[i]) and np.isfinite(demand[i]):
                gap = abs(supply[i] - demand[i])
                if gap > np.nanmean(np.abs(supply - demand)) + 3.0 * np.nanstd(np.abs(supply - demand)):
                    anomalies['supply_demand_gap'] += 1

        total = sum(anomalies.values())
        rate_per_day = total / (n / 288)

        results.append({
            'patient': p['name'],
            'total_anomalies': total,
            'rate_per_day': round(rate_per_day, 1),
            'large_positive': anomalies['large_positive'],
            'large_negative': anomalies['large_negative'],
            'sustained': anomalies['sustained_high'],
            'supply_demand_gap': anomalies['supply_demand_gap'],
        })

    detail_parts = [f'{r["patient"]}: {r["total_anomalies"]} total ({r["rate_per_day"]}/day)'
                    for r in results[:8]]
    mean_rate = np.mean([r['rate_per_day'] for r in results]) if results else 0
    return {
        'status': 'pass',
        'detail': f'n={len(results)}, mean {mean_rate:.1f} anomalies/day. ' + '; '.join(detail_parts),
        'per_patient': results,
    }


# ---------------------------------------------------------------------------
# EXP-798: AID Controller Characterization
# ---------------------------------------------------------------------------
@register('EXP-798', 'AID Controller Response')
def exp_798(patients, detail=False):
    """Model the closed-loop AID controller response to glucose excursions."""
    results = []

    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        supply = fd['supply']
        demand = fd['demand']
        n = fd['n']

        # How quickly does demand respond to BG excursions?
        # Cross-correlate bg-120 (deviation from target) with demand
        max_lag = 24  # 2 hours
        bg_dev = bg - 120.0  # Deviation from target

        valid = np.isfinite(bg_dev) & np.isfinite(demand)
        if valid.sum() < 1000:
            continue

        bg_v = bg_dev[valid]
        d_v = demand[valid]

        # Cross-correlation at various lags
        correlations = {}
        for lag in range(0, max_lag + 1, 3):
            if lag == 0:
                c = float(np.corrcoef(bg_v, d_v)[0, 1])
            else:
                if len(bg_v) > lag + 100:
                    c = float(np.corrcoef(bg_v[:-lag], d_v[lag:])[0, 1])
                else:
                    c = float('nan')
            correlations[lag * 5] = round(c, 3)  # Convert to minutes

        # Peak correlation lag = controller response time
        peak_lag = max(correlations, key=lambda k: correlations.get(k, 0) if np.isfinite(correlations.get(k, 0)) else -999)
        peak_corr = correlations[peak_lag]

        # Hypo response: how quickly does demand decrease when BG < 70?
        hypo_mask = bg < 70
        n_hypo = np.sum(hypo_mask & np.isfinite(demand))
        if n_hypo > 10:
            hypo_demand = float(np.nanmean(demand[hypo_mask]))
            normal_demand = float(np.nanmean(demand[~hypo_mask & np.isfinite(demand)]))
            hypo_reduction = round((normal_demand - hypo_demand) / max(normal_demand, 0.01) * 100, 1)
        else:
            hypo_reduction = float('nan')

        # Hyper response: increased demand when BG > 180
        hyper_mask = bg > 180
        n_hyper = np.sum(hyper_mask & np.isfinite(demand))
        if n_hyper > 10:
            hyper_demand = float(np.nanmean(demand[hyper_mask]))
            normal_demand = float(np.nanmean(demand[~hyper_mask & np.isfinite(demand)]))
            hyper_increase = round((hyper_demand - normal_demand) / max(normal_demand, 0.01) * 100, 1)
        else:
            hyper_increase = float('nan')

        results.append({
            'patient': p['name'],
            'peak_response_lag_min': peak_lag,
            'peak_correlation': peak_corr,
            'hypo_demand_reduction_pct': hypo_reduction,
            'hyper_demand_increase_pct': hyper_increase,
            'n_hypo_events': int(n_hypo),
            'n_hyper_events': int(n_hyper),
        })

    detail_parts = [f'{r["patient"]}: lag={r["peak_response_lag_min"]}min, ρ={r["peak_correlation"]}, hypo_red={r["hypo_demand_reduction_pct"]}%'
                    for r in results[:8]]
    mean_lag = np.mean([r['peak_response_lag_min'] for r in results]) if results else 0
    return {
        'status': 'pass',
        'detail': f'n={len(results)}, mean response lag={mean_lag:.0f}min. ' + '; '.join(detail_parts),
        'per_patient': results,
    }


# ---------------------------------------------------------------------------
# EXP-799: Integrated Prediction Pipeline
# ---------------------------------------------------------------------------
@register('EXP-799', 'Integrated Pipeline')
def exp_799(patients, detail=False):
    """Full integrated pipeline: physics + circadian + AR + compliance."""
    horizons = {6: '30min', 12: '60min'}
    results = {}

    for h_steps, h_name in horizons.items():
        component_r2s = {'physics': [], 'physics_ar': [], 'circ_ar': [], 'ridge_full': []}
        per_patient = []

        for p in patients:
            fd = _compute_flux(p)
            bg = fd['bg']
            resid = fd['resid']
            n = fd['n']
            nr = len(resid)
            df = p['df']
            hours = _get_hours(df, n)
            if hours is None:
                continue

            n_pred = nr - h_steps
            if n_pred < 500:
                continue

            actual = bg[h_steps:h_steps + n_pred]
            split = int(n_pred * 0.7)

            # Build all predictions
            phys_pred = np.full(n_pred, np.nan)
            ar_pred = np.full(n_pred, np.nan)

            for i in range(0, n_pred, 3):
                phys_pred[i] = _physics_sim(
                    bg[i], fd['supply'][i:i+h_steps], fd['demand'][i:i+h_steps],
                    fd['hepatic'][i:i+h_steps], 0, 0.0, 0.95, h_steps)
                ar_pred[i] = _physics_sim(
                    bg[i], fd['supply'][i:i+h_steps], fd['demand'][i:i+h_steps],
                    fd['hepatic'][i:i+h_steps], resid[i], 0.15, 0.95, h_steps)

            # Circadian correction trained on AR residuals
            train_mask = np.isfinite(ar_pred[:split]) & np.isfinite(actual[:split])
            if train_mask.sum() < 100:
                continue

            train_err = actual[:split][train_mask] - ar_pred[:split][train_mask]
            train_h = hours[:split][train_mask]
            X_circ = np.column_stack([
                np.sin(2 * np.pi * train_h / 24.0),
                np.cos(2 * np.pi * train_h / 24.0),
                np.ones(len(train_h))
            ])
            try:
                circ_coeffs = np.linalg.lstsq(X_circ, train_err, rcond=None)[0]
            except Exception:
                continue

            # Ridge regression with all features
            features = np.zeros((n_pred, 10))
            for i in range(n_pred):
                features[i, 0] = bg[i]
                features[i, 1] = np.sum(fd['supply'][i:i+h_steps])
                features[i, 2] = np.sum(fd['demand'][i:i+h_steps])
                features[i, 3] = np.sum(fd['hepatic'][i:i+h_steps])
                features[i, 4] = resid[i] if i < nr else 0
                features[i, 5] = np.sin(2 * np.pi * hours[i] / 24.0)
                features[i, 6] = np.cos(2 * np.pi * hours[i] / 24.0)
                features[i, 7] = bg[i] ** 2 / 10000  # Quadratic BG
                features[i, 8] = features[i, 1] * features[i, 5]  # Supply × time interaction
                features[i, 9] = 1.0  # bias

            valid_f = np.all(np.isfinite(features), axis=1) & np.isfinite(actual)
            train_f = valid_f[:split]
            val_f = valid_f[split:]

            if train_f.sum() < 200 or val_f.sum() < 100:
                continue

            X_tr = features[:split][train_f]
            y_tr = actual[:split][train_f]
            X_va = features[split:][val_f]
            y_va = actual[split:][val_f]

            lam = 10.0
            try:
                w = np.linalg.solve(X_tr.T @ X_tr + lam * np.eye(10), X_tr.T @ y_tr)
            except np.linalg.LinAlgError:
                continue

            ridge_pred = X_va @ w

            # Evaluate all components on validation
            val_mask = np.isfinite(ar_pred[split:]) & np.isfinite(actual[split:])
            if val_mask.sum() < 100:
                continue

            va_actual = actual[split:][val_mask]
            va_phys = phys_pred[split:][val_mask]
            va_ar = ar_pred[split:][val_mask]

            # Circadian correction
            va_hours = hours[split:split + n_pred - split][val_mask]
            circ_corr = circ_coeffs[0] * np.sin(2 * np.pi * va_hours / 24.0) + \
                        circ_coeffs[1] * np.cos(2 * np.pi * va_hours / 24.0) + circ_coeffs[2]
            va_circ_ar = va_ar + circ_corr

            r2_p = _r2(va_phys, va_actual)
            r2_a = _r2(va_ar, va_actual)
            r2_ca = _r2(va_circ_ar, va_actual)
            r2_ridge = _r2(ridge_pred, y_va)

            if all(np.isfinite([r2_p, r2_a, r2_ca, r2_ridge])):
                component_r2s['physics'].append(r2_p)
                component_r2s['physics_ar'].append(r2_a)
                component_r2s['circ_ar'].append(r2_ca)
                component_r2s['ridge_full'].append(r2_ridge)
                per_patient.append({
                    'patient': p['name'],
                    'physics': round(r2_p, 3),
                    'physics_ar': round(r2_a, 3),
                    'circ_ar': round(r2_ca, 3),
                    'ridge_full': round(r2_ridge, 3),
                })

        means = {k: round(np.mean(v), 3) if v else float('nan') for k, v in component_r2s.items()}
        results[h_name] = {**means, 'per_patient': per_patient}

    detail_str = ', '.join(
        f'{h}: phys={v["physics"]}/AR={v["physics_ar"]}/circ={v["circ_ar"]}/ridge={v["ridge_full"]}'
        for h, v in results.items())
    return {'status': 'pass', 'detail': detail_str, 'results': results}


# ---------------------------------------------------------------------------
# EXP-800: Final Integrated Benchmark
# ---------------------------------------------------------------------------
@register('EXP-800', 'Final Benchmark')
def exp_800(patients, detail=False):
    """Comprehensive benchmark comparing all prediction approaches."""
    methods = ['naive_last', 'ar_only', 'physics_only', 'physics_ar', 'circ_physics_ar', 'ridge']
    horizons = {1: '5min', 3: '15min', 6: '30min', 12: '60min'}
    results = {}

    for h_steps, h_name in horizons.items():
        method_r2s = {m: [] for m in methods}
        method_maes = {m: [] for m in methods}

        for p in patients:
            fd = _compute_flux(p)
            bg = fd['bg']
            resid = fd['resid']
            n = fd['n']
            nr = len(resid)
            df = p['df']
            hours = _get_hours(df, n)
            if hours is None:
                continue

            n_pred = nr - h_steps
            if n_pred < 500:
                continue

            actual = bg[h_steps:h_steps + n_pred]
            split = int(n_pred * 0.7)

            # Method 1: Naive (last value)
            naive = bg[:n_pred]

            # Method 2: AR only (bg + trend extrapolation)
            ar_only = np.full(n_pred, np.nan)
            for i in range(1, n_pred, 3):
                trend = bg[i] - bg[i-1]
                ar_only[i] = bg[i] + trend * h_steps

            # Method 3-5: Physics variants
            phys = np.full(n_pred, np.nan)
            phys_ar = np.full(n_pred, np.nan)
            for i in range(0, n_pred, 3):
                phys[i] = _physics_sim(
                    bg[i], fd['supply'][i:i+h_steps], fd['demand'][i:i+h_steps],
                    fd['hepatic'][i:i+h_steps], 0, 0.0, 0.95, h_steps)
                phys_ar[i] = _physics_sim(
                    bg[i], fd['supply'][i:i+h_steps], fd['demand'][i:i+h_steps],
                    fd['hepatic'][i:i+h_steps], resid[i], 0.15, 0.95, h_steps)

            # Circadian correction
            train_mask = np.isfinite(phys_ar[:split]) & np.isfinite(actual[:split])
            circ_coeffs = None
            if train_mask.sum() >= 100 and hours is not None:
                train_err = actual[:split][train_mask] - phys_ar[:split][train_mask]
                train_h = hours[:split][train_mask]
                X = np.column_stack([np.sin(2*np.pi*train_h/24), np.cos(2*np.pi*train_h/24), np.ones(len(train_h))])
                try:
                    circ_coeffs = np.linalg.lstsq(X, train_err, rcond=None)[0]
                except Exception:
                    pass

            circ_phys_ar = np.copy(phys_ar)
            if circ_coeffs is not None:
                for i in range(split, n_pred):
                    if np.isfinite(circ_phys_ar[i]) and hours is not None and i < len(hours):
                        h = hours[i]
                        circ_phys_ar[i] += circ_coeffs[0] * np.sin(2*np.pi*h/24) + \
                                           circ_coeffs[1] * np.cos(2*np.pi*h/24) + circ_coeffs[2]

            # Ridge regression
            features = np.zeros((n_pred, 8))
            for i in range(n_pred):
                features[i, 0] = bg[i]
                features[i, 1] = np.sum(fd['supply'][i:i+h_steps])
                features[i, 2] = np.sum(fd['demand'][i:i+h_steps])
                features[i, 3] = np.sum(fd['hepatic'][i:i+h_steps])
                features[i, 4] = resid[i] if i < nr else 0
                if hours is not None:
                    features[i, 5] = np.sin(2*np.pi*hours[i]/24)
                    features[i, 6] = np.cos(2*np.pi*hours[i]/24)
                features[i, 7] = 1.0

            valid_f = np.all(np.isfinite(features), axis=1) & np.isfinite(actual)
            ridge_pred = np.full(n_pred, np.nan)
            if valid_f[:split].sum() >= 200 and valid_f[split:].sum() >= 100:
                X_tr = features[:split][valid_f[:split]]
                y_tr = actual[:split][valid_f[:split]]
                try:
                    w = np.linalg.solve(X_tr.T @ X_tr + np.eye(8), X_tr.T @ y_tr)
                    ridge_pred[split:] = features[split:] @ w
                except np.linalg.LinAlgError:
                    pass

            # Evaluate on validation set only
            preds = {
                'naive_last': naive,
                'ar_only': ar_only,
                'physics_only': phys,
                'physics_ar': phys_ar,
                'circ_physics_ar': circ_phys_ar,
                'ridge': ridge_pred,
            }

            for m_name, m_pred in preds.items():
                val_pred = m_pred[split:]
                val_actual = actual[split:]
                r2_val = _r2(val_pred, val_actual)
                mae_val = _mae(val_pred, val_actual)
                if np.isfinite(r2_val):
                    method_r2s[m_name].append(r2_val)
                if np.isfinite(mae_val):
                    method_maes[m_name].append(mae_val)

        horizon_results = {}
        for m in methods:
            horizon_results[m] = {
                'r2': round(np.mean(method_r2s[m]), 3) if method_r2s[m] else float('nan'),
                'mae': round(np.mean(method_maes[m]), 1) if method_maes[m] else float('nan'),
                'n': len(method_r2s[m]),
            }
        results[h_name] = horizon_results

    # Summary table
    detail_parts = []
    for h_name in ['5min', '15min', '30min', '60min']:
        if h_name in results:
            best = max(results[h_name], key=lambda m: results[h_name][m]['r2'] if np.isfinite(results[h_name][m]['r2']) else -999)
            detail_parts.append(f'{h_name}: best={best} R²={results[h_name][best]["r2"]}')

    return {'status': 'pass', 'detail': '; '.join(detail_parts), 'results': results}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description='EXP-791-800: Advanced Integration & Multi-Scale')
    parser.add_argument('--max-patients', type=int, default=11)
    parser.add_argument('--only', type=str, default=None, help='Run specific experiment')
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    args = parser.parse_args()

    print(f'Loading patients (max={args.max_patients})...')
    patients = load_patients(PATIENTS_DIR, max_patients=args.max_patients)
    print(f'Loaded {len(patients)} patients\n')

    to_run = {args.only: EXPERIMENTS[args.only]} if args.only else EXPERIMENTS
    passed = 0
    failed = 0
    results_all = {}

    for exp_id, exp_info in to_run.items():
        print(f'\n{"="*60}')
        print(f'Running {exp_id}: {exp_info["name"]}')
        print(f'{"="*60}')
        t0 = time.time()
        try:
            result = exp_info['func'](patients, detail=args.detail)
            elapsed = time.time() - t0
            result['exp_id'] = exp_id
            result['name'] = exp_info['name']
            result['elapsed'] = round(elapsed, 1)
            results_all[exp_id] = result
            status = result.get('status', 'unknown')
            if status == 'pass':
                passed += 1
                print(f'  Status: pass ({elapsed:.1f}s)')
            else:
                failed += 1
                print(f'  Status: FAIL ({elapsed:.1f}s)')
            if 'detail' in result:
                print(f'  Detail: {result["detail"][:200]}')
        except Exception as e:
            elapsed = time.time() - t0
            failed += 1
            import traceback
            traceback.print_exc()
            print(f'  Status: FAIL ({elapsed:.1f}s)')
            print(f'  Error: {e}')
            results_all[exp_id] = {
                'status': 'fail', 'error': str(e),
                'exp_id': exp_id, 'name': exp_info['name'], 'elapsed': round(elapsed, 1)
            }

    print(f'\n{"="*60}')
    print('SUMMARY')
    print(f'{"="*60}')
    print(f'Passed: {passed}/{passed+failed}, Failed: {failed}/{passed+failed}')
    for exp_id, r in results_all.items():
        status = 'V' if r.get('status') == 'pass' else 'X'
        detail = r.get('detail', r.get('error', ''))[:100]
        print(f'  {status} {exp_id} {r.get("name", "")}: {detail}')

    if args.save:
        save_dir = Path(__file__).parent.parent.parent / 'externals' / 'experiments'
        save_dir.mkdir(parents=True, exist_ok=True)
        for exp_id, r in results_all.items():
            slug = f'{exp_id.lower().replace("-", "_")}_{r.get("name", "").lower().replace(" ", "_")[:30]}'
            fname = save_dir / f'{slug}.json'
            with open(fname, 'w') as f:
                json.dump(r, f, indent=2, default=str)
            print(f'  Saved: {fname.name}')


if __name__ == '__main__':
    main()
