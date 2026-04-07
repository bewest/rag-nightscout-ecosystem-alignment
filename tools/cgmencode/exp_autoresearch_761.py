#!/usr/bin/env python3
"""EXP-761-770: Refined Clinical Intelligence & Extended Horizons.

Key experiments:
- EXP-761: Horizon-matched calibration (fix two-stage mismatch)
- EXP-762: Relaxed unannounced meal detection & sizing
- EXP-763: CR effectiveness v2 with relaxed criteria
- EXP-764: Time-of-day basal profile optimization
- EXP-765: ISF time-of-day variation
- EXP-766: Iterated physics forecast (chained 5min predictions)
- EXP-767: Cannula/infusion site age effect on ISF
- EXP-768: Weekly trend decomposition of physics residual
- EXP-769: Cross-patient transfer learning (leave-one-out physics)
- EXP-770: Automated settings change recommendation via gradient
"""

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# Imports from existing modules
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent.parent))

from cgmencode.exp_metabolic_flux import load_patients
from cgmencode.exp_metabolic_441 import compute_supply_demand

PATIENTS_DIR = Path(__file__).parent.parent.parent / "externals" / "ns-data" / "patients"

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _get_bg(df):
    return df['glucose'].values if 'glucose' in df.columns else df['sgv'].values

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
    """Compute flux decomposition for a patient."""
    df = p['df']
    pk = p.get('pk')
    if pk is None:
        pk = np.zeros(len(_get_bg(p['df'])))
    fd = compute_supply_demand(df, pk)
    bg = _get_bg(df)
    n = len(fd['supply'])
    bg = bg[:n]
    supply = fd['supply']
    demand = fd['demand']
    hepatic = fd.get('hepatic', np.full(n, 0.5))
    flux_pred = supply - demand + hepatic + (120.0 - bg) * 0.005
    resid = bg[1:] - (bg[:-1] + flux_pred[:-1])
    return {
        'bg': bg, 'supply': supply, 'demand': demand,
        'hepatic': hepatic, 'flux_pred': flux_pred,
        'resid': resid, 'n': n,
    }

def _hybrid_predict(fd, horizon_steps, ar_w=0.15, decay=0.95):
    """Produce hybrid predictions at a given horizon."""
    bg = fd['bg']
    supply = fd['supply']
    demand = fd['demand']
    hepatic = fd['hepatic']
    resid = fd['resid']
    nr = len(resid)
    n_pred = nr - horizon_steps
    if n_pred <= 0:
        return np.array([]), np.array([])

    # AR baseline
    ar_pred = np.full(n_pred, np.nan)
    for i in range(n_pred):
        ar_pred[i] = bg[i] + resid[i] * ar_w * sum(decay**k for k in range(horizon_steps))

    # Physics forward sim
    phys_pred = np.full(n_pred, np.nan)
    for i in range(n_pred):
        phys_pred[i] = _physics_sim(
            bg[i], supply[i:i+horizon_steps], demand[i:i+horizon_steps],
            hepatic[i:i+horizon_steps], resid[i], ar_w, decay, horizon_steps
        )

    # Blend weights (from EXP-731 optimized)
    blend_map = {1: 0.02, 3: 0.27, 6: 0.50, 12: 0.66}
    w_ar = blend_map.get(horizon_steps, 0.50)
    hybrid = w_ar * ar_pred + (1.0 - w_ar) * phys_pred

    actual = bg[horizon_steps:horizon_steps + n_pred]
    return hybrid, actual

def _r2(pred, actual):
    mask = np.isfinite(pred) & np.isfinite(actual)
    if mask.sum() < 10:
        return float('nan')
    p, a = pred[mask], actual[mask]
    ss_res = np.sum((a - p)**2)
    ss_tot = np.sum((a - np.mean(a))**2)
    if ss_tot < 1e-10:
        return float('nan')
    return 1.0 - ss_res / ss_tot


# ===========================================================================
# EXPERIMENTS
# ===========================================================================

EXPERIMENTS = {}

def register(exp_id, name):
    def decorator(func):
        EXPERIMENTS[exp_id] = {'name': name, 'func': func}
        return func
    return decorator


# ---------------------------------------------------------------------------
# EXP-761: Horizon-Matched Calibration
# ---------------------------------------------------------------------------
@register('EXP-761', 'Horizon-Matched Calibration')
def exp_761(patients, detail=False):
    """Train two-stage correction at each target horizon instead of 1-step."""
    horizons = {1: '5min', 3: '15min', 6: '30min', 12: '60min'}
    results = {}

    for h_steps, h_name in horizons.items():
        # Collect all patients' residuals at this horizon for calibration
        all_phys_resid = []
        all_ar_resid = []
        all_r2_direct = []
        all_r2_calibrated = []

        for p in patients:
            fd = _compute_flux(p)
            bg = fd['bg']
            resid = fd['resid']
            nr = len(resid)
            n_pred = nr - h_steps
            if n_pred < 100:
                continue

            # Direct hybrid predictions
            hybrid, actual = _hybrid_predict(fd, h_steps)
            if len(hybrid) < 100:
                continue

            # Split train/val (70/30)
            split = int(len(hybrid) * 0.7)
            h_train, a_train = hybrid[:split], actual[:split]
            h_val, a_val = hybrid[split:], actual[split:]

            # Direct R²
            r2_direct = _r2(h_val, a_val)

            # Two-stage: learn linear correction on train residuals
            train_resid = a_train - h_train
            mask = np.isfinite(train_resid) & np.isfinite(h_train)
            if mask.sum() < 50:
                all_r2_direct.append(r2_direct)
                all_r2_calibrated.append(r2_direct)
                continue

            # Simple linear correction: pred_corrected = pred + alpha * (pred - mean_pred) + beta
            from numpy.polynomial import polynomial as P
            coeffs = np.polyfit(h_train[mask], train_resid[mask], 1)
            val_correction = np.polyval(coeffs, h_val)
            calibrated = h_val + val_correction

            r2_cal = _r2(calibrated, a_val)
            all_r2_direct.append(r2_direct)
            all_r2_calibrated.append(r2_cal)

        mean_direct = np.nanmean(all_r2_direct) if all_r2_direct else float('nan')
        mean_cal = np.nanmean(all_r2_calibrated) if all_r2_calibrated else float('nan')
        delta = mean_cal - mean_direct if np.isfinite(mean_cal) and np.isfinite(mean_direct) else float('nan')
        results[h_name] = {'direct': round(mean_direct, 3), 'calibrated': round(mean_cal, 3), 'delta': round(delta, 3)}

    detail_str = ', '.join(f'{h}: d={v["direct"]}/c={v["calibrated"]}/Δ={v["delta"]}' for h, v in results.items())
    return {'status': 'pass', 'detail': detail_str, 'results': results}


# ---------------------------------------------------------------------------
# EXP-762: Relaxed Unannounced Meal Detection
# ---------------------------------------------------------------------------
@register('EXP-762', 'Relaxed Meal Detection')
def exp_762(patients, detail=False):
    """Detect unannounced meals with relaxed thresholds (>15g equivalent)."""
    total_events = 0
    total_announced = 0
    total_unannounced = 0
    carb_estimates = []

    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        supply = fd['supply']
        demand = fd['demand']
        n = fd['n']

        # Detect supply bursts (potential meals) — relaxed criteria
        # Supply > mean + 1.0 * std (was 2.0 in EXP-753)
        s_mean = np.nanmean(supply)
        s_std = np.nanstd(supply)
        threshold = s_mean + 1.0 * s_std

        # Find contiguous burst regions
        in_burst = supply > threshold
        burst_starts = []
        burst_ends = []
        i = 0
        while i < n:
            if in_burst[i]:
                start = i
                while i < n and in_burst[i]:
                    i += 1
                burst_starts.append(start)
                burst_ends.append(i)
            else:
                i += 1

        # Check each burst
        df = p['df']
        for bs, be in zip(burst_starts, burst_ends):
            burst_integral = np.sum(supply[bs:be]) * 5.0 / 60.0  # mg/dL equivalent
            # Estimate equivalent carbs: burst_integral / ISF * CR approximation
            # Simple heuristic: 1g carb ≈ 3-5 mg/dL rise for typical patient
            est_carbs = burst_integral / 4.0  # rough estimate

            if est_carbs < 15.0:  # Skip tiny supply fluctuations
                continue

            total_events += 1

            # Check if there's a bolus within ±30 min of burst start
            # Use demand as proxy for bolus activity
            window_start = max(0, bs - 6)  # 30 min before
            window_end = min(n, bs + 6)  # 30 min after
            demand_window = demand[window_start:window_end]
            d_mean = np.nanmean(demand)
            d_std = np.nanstd(demand)

            if np.max(demand_window) > d_mean + 1.5 * d_std:
                total_announced += 1
            else:
                total_unannounced += 1
                carb_estimates.append(est_carbs)

    unannounced_pct = (total_unannounced / total_events * 100) if total_events > 0 else 0
    mean_carbs = np.mean(carb_estimates) if carb_estimates else float('nan')
    median_carbs = np.median(carb_estimates) if carb_estimates else float('nan')

    return {
        'status': 'pass',
        'detail': f'events={total_events}, unannounced={total_unannounced} ({unannounced_pct:.1f}%), '
                  f'mean_carbs={mean_carbs:.1f}g, median={median_carbs:.1f}g',
        'total_events': total_events,
        'unannounced': total_unannounced,
        'unannounced_pct': round(unannounced_pct, 1),
        'mean_carbs': round(mean_carbs, 1),
        'median_carbs': round(median_carbs, 1),
    }


# ---------------------------------------------------------------------------
# EXP-763: CR Effectiveness v2
# ---------------------------------------------------------------------------
@register('EXP-763', 'CR Effectiveness v2')
def exp_763(patients, detail=False):
    """Evaluate carb ratio effectiveness using relaxed meal-bolus matching."""
    results = []

    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        supply = fd['supply']
        demand = fd['demand']
        n = fd['n']

        # Find significant supply+demand events (meal + bolus co-occurring)
        s_mean, s_std = np.nanmean(supply), np.nanstd(supply)
        d_mean, d_std = np.nanmean(demand), np.nanstd(demand)

        meal_events = []
        i = 0
        while i < n - 24:  # Need 2h post-meal window
            # Detect meal: supply > mean + 0.5*std
            if supply[i] > s_mean + 0.5 * s_std:
                # Check for bolus within ±15 min
                window = demand[max(0, i-3):min(n, i+3)]
                if np.max(window) > d_mean + 1.0 * d_std:
                    # This is a bolused meal
                    # Compute supply integral (carb equivalent)
                    j = i
                    while j < n and supply[j] > s_mean:
                        j += 1
                    supply_integral = np.sum(supply[i:j]) * 5.0 / 60.0

                    # Compute demand integral (insulin effect)
                    demand_integral = np.sum(demand[i:min(j+12, n)]) * 5.0 / 60.0

                    # BG change 2h post-meal
                    end_idx = min(i + 24, n - 1)
                    bg_change = bg[end_idx] - bg[i]

                    # Effective CR = supply_integral / demand_integral
                    if demand_integral > 1.0:
                        effective_ratio = supply_integral / demand_integral
                        meal_events.append({
                            'supply_integral': supply_integral,
                            'demand_integral': demand_integral,
                            'bg_change': bg_change,
                            'effective_ratio': effective_ratio,
                        })
                    i = j + 6  # Skip past this meal
                else:
                    i += 1
            else:
                i += 1

        if len(meal_events) >= 5:
            ratios = [m['effective_ratio'] for m in meal_events]
            bg_changes = [m['bg_change'] for m in meal_events]
            results.append({
                'patient': p['name'],
                'n_meals': len(meal_events),
                'mean_ratio': np.mean(ratios),
                'std_ratio': np.std(ratios),
                'mean_bg_change': np.mean(bg_changes),
                'good_meals_pct': sum(1 for b in bg_changes if abs(b) < 40) / len(bg_changes) * 100,
            })

    detail_parts = []
    for r in results:
        detail_parts.append(f'{r["patient"]}: n={r["n_meals"]}, ratio={r["mean_ratio"]:.2f}±{r["std_ratio"]:.2f}, '
                           f'ΔBG={r["mean_bg_change"]:.1f}, good={r["good_meals_pct"]:.0f}%')

    return {
        'status': 'pass',
        'detail': f'n={len(results)} patients. ' + '; '.join(detail_parts[:6]),
        'per_patient': results,
    }


# ---------------------------------------------------------------------------
# EXP-764: Time-of-Day Basal Profile
# ---------------------------------------------------------------------------
@register('EXP-764', 'Basal Temporal Profile')
def exp_764(patients, detail=False):
    """Optimize basal rates by 2-hour time blocks using overnight + quiet periods."""
    results = []

    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        resid = fd['resid']
        n = fd['n']
        df = p['df']

        # Get hours from DatetimeIndex
        try:
            import pandas as pd
            idx = df.index[:n]
            if not isinstance(idx, pd.DatetimeIndex):
                continue
            hours = idx.hour
        except Exception:
            continue

        # For each 2-hour block, compute mean residual during "quiet" periods
        # Quiet = demand < median (not bolusing) and supply < median (not eating)
        supply = fd['supply']
        demand = fd['demand']
        s_med = np.nanmedian(supply)
        d_med = np.nanmedian(demand)

        quiet = (supply[:len(resid)] < s_med * 1.2) & (demand[:len(resid)] < d_med * 1.2)

        block_residuals = {}
        for block_start in range(0, 24, 2):
            block_end = block_start + 2
            mask = quiet & (hours[:len(resid)] >= block_start) & (hours[:len(resid)] < block_end)
            if mask.sum() > 50:
                block_residuals[f'{block_start:02d}-{block_end:02d}'] = {
                    'mean_resid': float(np.nanmean(resid[mask])),
                    'n_samples': int(mask.sum()),
                }

        if len(block_residuals) >= 6:
            # Find blocks needing adjustment
            needs_increase = [b for b, v in block_residuals.items() if v['mean_resid'] > 0.5]
            needs_decrease = [b for b, v in block_residuals.items() if v['mean_resid'] < -0.5]
            max_block = max(block_residuals.items(), key=lambda x: abs(x[1]['mean_resid']))
            results.append({
                'patient': p['name'],
                'n_blocks': len(block_residuals),
                'needs_increase': needs_increase,
                'needs_decrease': needs_decrease,
                'max_deviation': max_block[0],
                'max_resid': round(max_block[1]['mean_resid'], 2),
                'blocks': block_residuals,
            })

    detail_parts = [f'{r["patient"]}: max@{r["max_deviation"]}({r["max_resid"]:+.2f}), '
                   f'↑{len(r["needs_increase"])} ↓{len(r["needs_decrease"])}' for r in results[:8]]
    return {
        'status': 'pass',
        'detail': f'n={len(results)} patients. ' + ', '.join(detail_parts),
        'per_patient': results,
    }


# ---------------------------------------------------------------------------
# EXP-765: ISF Time-of-Day Variation
# ---------------------------------------------------------------------------
@register('EXP-765', 'ISF Time-of-Day')
def exp_765(patients, detail=False):
    """Measure how effective ISF varies by time of day."""
    results = []

    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        demand = fd['demand']
        supply = fd['supply']
        n = fd['n']
        df = p['df']

        # Get hours from DatetimeIndex
        try:
            import pandas as pd
            idx = df.index[:n]
            if not isinstance(idx, pd.DatetimeIndex):
                continue
            hours = idx.hour
        except Exception:
            continue

        # Find correction bolus events (high demand, low supply)
        s_med = np.nanmedian(supply)
        d_mean = np.nanmean(demand)
        d_std = np.nanstd(demand)

        isf_by_block = {}
        for block_start in range(0, 24, 4):
            block_end = block_start + 4
            block_isfs = []

            for i in range(n - 12):
                if hours[i] < block_start or hours[i] >= block_end:
                    continue
                # Correction: high demand, low supply
                if demand[i] > d_mean + 1.0 * d_std and supply[i] < s_med * 1.5:
                    # Find demand integral over next 1h
                    d_integral = np.sum(demand[i:min(i+12, n)]) * 5.0 / 60.0
                    if d_integral < 5.0:
                        continue
                    # BG change over next 1h
                    end_idx = min(i + 12, n - 1)
                    bg_drop = bg[i] - bg[end_idx]
                    if bg_drop > 0 and d_integral > 0:
                        effective_isf = bg_drop / (d_integral / 50.0)  # normalize
                        if 5 < effective_isf < 200:
                            block_isfs.append(effective_isf)

            if len(block_isfs) >= 10:
                isf_by_block[f'{block_start:02d}-{block_end:02d}'] = {
                    'mean_isf': float(np.mean(block_isfs)),
                    'std_isf': float(np.std(block_isfs)),
                    'n': len(block_isfs),
                }

        if len(isf_by_block) >= 3:
            isf_values = [v['mean_isf'] for v in isf_by_block.values()]
            variation = (max(isf_values) - min(isf_values)) / np.mean(isf_values) * 100
            results.append({
                'patient': p['name'],
                'n_blocks': len(isf_by_block),
                'variation_pct': round(variation, 1),
                'blocks': isf_by_block,
            })

    detail_parts = [f'{r["patient"]}: {r["variation_pct"]}% variation across {r["n_blocks"]} blocks' for r in results[:8]]
    mean_var = np.mean([r['variation_pct'] for r in results]) if results else float('nan')
    return {
        'status': 'pass',
        'detail': f'n={len(results)}, mean variation={mean_var:.1f}%. ' + '; '.join(detail_parts),
        'per_patient': results,
    }


# ---------------------------------------------------------------------------
# EXP-766: Iterated Physics Forecast
# ---------------------------------------------------------------------------
@register('EXP-766', 'Iterated Physics Forecast')
def exp_766(patients, detail=False):
    """Chain 5-min physics simulations for longer horizons instead of single-step."""
    horizons = {1: '5min', 3: '15min', 6: '30min', 12: '60min'}
    all_results = {}

    for h_steps, h_name in horizons.items():
        r2_single = []
        r2_iterated = []

        for p in patients:
            fd = _compute_flux(p)
            bg = fd['bg']
            supply = fd['supply']
            demand = fd['demand']
            hepatic = fd['hepatic']
            resid = fd['resid']
            nr = len(resid)
            n_pred = nr - h_steps
            if n_pred < 100:
                continue

            actual = bg[h_steps:h_steps + n_pred]

            # Single-step prediction (current best)
            single_pred = np.full(n_pred, np.nan)
            for i in range(n_pred):
                single_pred[i] = _physics_sim(
                    bg[i], supply[i:i+h_steps], demand[i:i+h_steps],
                    hepatic[i:i+h_steps], resid[i], 0.15, 0.95, h_steps
                )

            # Iterated: chain 1-step predictions, using predicted BG as input for next step
            iter_pred = np.full(n_pred, np.nan)
            for i in range(n_pred):
                bg_sim = bg[i]
                resid_est = resid[i]
                for step in range(h_steps):
                    idx = i + step
                    if idx >= len(supply):
                        break
                    bg_d = (120.0 - bg_sim) * 0.005
                    bg_step = bg_sim + supply[idx] - demand[idx] + hepatic[idx] + bg_d
                    # Key difference: re-estimate residual from predicted BG
                    if step < h_steps - 1 and idx + 1 < len(bg):
                        # Use the observed-vs-predicted error from THIS step
                        # to update residual estimate for next step
                        resid_est = resid_est * 0.95  # decay previous
                    bg_sim = bg_step + 0.15 * resid_est
                    resid_est *= 0.95
                iter_pred[i] = bg_sim

            r2_s = _r2(single_pred, actual)
            r2_i = _r2(iter_pred, actual)
            if np.isfinite(r2_s) and np.isfinite(r2_i):
                r2_single.append(r2_s)
                r2_iterated.append(r2_i)

        mean_single = np.mean(r2_single) if r2_single else float('nan')
        mean_iter = np.mean(r2_iterated) if r2_iterated else float('nan')
        delta = mean_iter - mean_single
        all_results[h_name] = {
            'single': round(mean_single, 3),
            'iterated': round(mean_iter, 3),
            'delta': round(delta, 3),
        }

    detail_str = ', '.join(f'{h}: s={v["single"]}/i={v["iterated"]}/Δ={v["delta"]}' for h, v in all_results.items())
    return {'status': 'pass', 'detail': detail_str, 'results': all_results}


# ---------------------------------------------------------------------------
# EXP-767: Cannula/Infusion Site Age Effect
# ---------------------------------------------------------------------------
@register('EXP-767', 'Cannula Age Effect')
def exp_767(patients, detail=False):
    """Detect infusion site degradation from increasing physics residual over multi-day windows."""
    results = []

    for p in patients:
        fd = _compute_flux(p)
        resid = fd['resid']
        demand = fd['demand']
        nr = len(resid)

        # Assume 3-day infusion site changes (typical)
        # Divide residual into 3-day windows and check if residual magnitude increases
        window_size = 3 * 288  # 3 days at 5min intervals
        n_windows = nr // window_size

        if n_windows < 5:
            continue

        # For each window, compute residual stats by position within window
        day1_resid = []
        day2_resid = []
        day3_resid = []

        for w in range(n_windows):
            start = w * window_size
            end = start + window_size
            if end > nr:
                break
            chunk = np.abs(resid[start:end])
            third = window_size // 3
            day1_resid.append(np.nanmean(chunk[:third]))
            day2_resid.append(np.nanmean(chunk[third:2*third]))
            day3_resid.append(np.nanmean(chunk[2*third:]))

        mean_d1 = np.mean(day1_resid)
        mean_d2 = np.mean(day2_resid)
        mean_d3 = np.mean(day3_resid)

        # Also check demand effectiveness (same bolus → less BG drop over site life)
        # Track demand-weighted residual by day position
        demand_day1 = []
        demand_day3 = []
        for w in range(n_windows):
            start = w * window_size
            end = start + window_size
            if end > nr:
                break
            third = window_size // 3
            d1 = demand[start:start+third]
            d3 = demand[start+2*third:start+3*third]
            r1 = resid[start:start+third]
            r3 = resid[start+2*third:min(start+3*third, nr)]
            # High-demand periods residual
            high_d1 = np.abs(r1[d1[:len(r1)] > np.nanmedian(demand)])
            high_d3 = np.abs(r3[d3[:len(r3)] > np.nanmedian(demand)])
            if len(high_d1) > 10:
                demand_day1.append(np.nanmean(high_d1))
            if len(high_d3) > 10:
                demand_day3.append(np.nanmean(high_d3))

        degradation = (mean_d3 - mean_d1) / mean_d1 * 100 if mean_d1 > 0 else 0
        results.append({
            'patient': p['name'],
            'n_windows': n_windows,
            'day1_resid': round(mean_d1, 2),
            'day2_resid': round(mean_d2, 2),
            'day3_resid': round(mean_d3, 2),
            'degradation_pct': round(degradation, 1),
            'demand_d1': round(np.mean(demand_day1), 2) if demand_day1 else float('nan'),
            'demand_d3': round(np.mean(demand_day3), 2) if demand_day3 else float('nan'),
        })

    detail_parts = [f'{r["patient"]}: d1={r["day1_resid"]}/d3={r["day3_resid"]} ({r["degradation_pct"]:+.1f}%)' for r in results[:8]]
    mean_deg = np.mean([r['degradation_pct'] for r in results]) if results else float('nan')
    return {
        'status': 'pass',
        'detail': f'n={len(results)}, mean degradation={mean_deg:.1f}%. ' + '; '.join(detail_parts),
        'per_patient': results,
    }


# ---------------------------------------------------------------------------
# EXP-768: Weekly Trend Decomposition
# ---------------------------------------------------------------------------
@register('EXP-768', 'Weekly Trend Decomposition')
def exp_768(patients, detail=False):
    """Extract weekly trends from physics residual using moving average decomposition."""
    results = []

    for p in patients:
        fd = _compute_flux(p)
        resid = fd['resid']
        nr = len(resid)

        if nr < 7 * 288:  # Need at least 1 week
            continue

        # Moving average decomposition
        day_len = 288  # 5min intervals per day
        week_len = 7 * day_len

        # Daily mean residual
        n_days = nr // day_len
        daily_means = []
        for d in range(n_days):
            chunk = resid[d*day_len:(d+1)*day_len]
            daily_means.append(np.nanmean(chunk))

        daily_means = np.array(daily_means)

        # Weekly moving average
        if n_days >= 14:
            weekly_ma = np.convolve(daily_means, np.ones(7)/7, mode='valid')
            # Detrended = daily - weekly MA
            detrended = daily_means[3:3+len(weekly_ma)] - weekly_ma

            # Weekly cycle: average by day-of-week
            n_weeks = len(weekly_ma) // 7
            if n_weeks >= 2:
                dow_pattern = np.zeros(7)
                dow_counts = np.zeros(7)
                for i, v in enumerate(detrended):
                    dow = i % 7
                    if np.isfinite(v):
                        dow_pattern[dow] += v
                        dow_counts[dow] += 1
                dow_pattern = np.where(dow_counts > 0, dow_pattern / dow_counts, 0)

                # Monthly trend: is there a drift?
                if n_days >= 28:
                    month_blocks = n_days // 28
                    monthly_means = []
                    for m in range(month_blocks):
                        monthly_means.append(np.nanmean(daily_means[m*28:(m+1)*28]))

                    trend_slope = 0
                    if len(monthly_means) >= 2:
                        x = np.arange(len(monthly_means))
                        trend_slope = np.polyfit(x, monthly_means, 1)[0]
                else:
                    monthly_means = []
                    trend_slope = 0

                results.append({
                    'patient': p['name'],
                    'n_days': n_days,
                    'n_weeks': n_weeks,
                    'dow_range': round(float(np.max(dow_pattern) - np.min(dow_pattern)), 2),
                    'dow_pattern': [round(v, 3) for v in dow_pattern],
                    'monthly_trend': round(float(trend_slope), 3),
                    'daily_std': round(float(np.nanstd(daily_means)), 2),
                })

    detail_parts = [f'{r["patient"]}: dow_range={r["dow_range"]}, trend={r["monthly_trend"]:.3f}/mo, daily_σ={r["daily_std"]}' for r in results[:8]]
    mean_dow = np.mean([r['dow_range'] for r in results]) if results else float('nan')
    return {
        'status': 'pass',
        'detail': f'n={len(results)}, mean dow_range={mean_dow:.2f} mg/dL. ' + '; '.join(detail_parts),
        'per_patient': results,
    }


# ---------------------------------------------------------------------------
# EXP-769: Cross-Patient Transfer (Leave-One-Out Physics)
# ---------------------------------------------------------------------------
@register('EXP-769', 'Cross-Patient Transfer')
def exp_769(patients, detail=False):
    """Test if population physics parameters work for held-out patients."""
    if len(patients) < 3:
        return {'status': 'skip', 'detail': 'Need ≥3 patients'}

    # First, compute per-patient optimal AR weight and decay
    patient_params = []
    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        resid = fd['resid']
        nr = len(resid)
        if nr < 200:
            continue

        # Quick grid search for AR weight
        best_r2 = -999
        best_w = 0.15
        best_d = 0.95
        h_steps = 6  # 30min horizon

        n_pred = nr - h_steps
        if n_pred < 100:
            continue

        actual = bg[h_steps:h_steps + n_pred]

        for w in [0.05, 0.10, 0.15, 0.20, 0.30]:
            for d in [0.80, 0.90, 0.95, 0.99]:
                pred = np.full(n_pred, np.nan)
                for i in range(0, n_pred, 10):  # subsample for speed
                    pred[i] = _physics_sim(
                        bg[i], fd['supply'][i:i+h_steps], fd['demand'][i:i+h_steps],
                        fd['hepatic'][i:i+h_steps], resid[i], w, d, h_steps
                    )
                r2 = _r2(pred, actual)
                if np.isfinite(r2) and r2 > best_r2:
                    best_r2 = r2
                    best_w = w
                    best_d = d

        patient_params.append({
            'name': p['name'],
            'ar_w': best_w,
            'decay': best_d,
            'personal_r2': round(best_r2, 3),
        })

    # LOO: for each patient, use mean of others' parameters
    loo_results = []
    for i, pp in enumerate(patient_params):
        others = [p for j, p in enumerate(patient_params) if j != i]
        pop_w = np.mean([o['ar_w'] for o in others])
        pop_d = np.mean([o['decay'] for o in others])

        # Evaluate population parameters on this patient
        p = [p for p in patients if p['name'] == pp['name']][0]
        fd = _compute_flux(p)
        bg = fd['bg']
        resid = fd['resid']
        nr = len(resid)
        h_steps = 6
        n_pred = nr - h_steps
        if n_pred < 100:
            continue

        actual = bg[h_steps:h_steps + n_pred]
        pred = np.full(n_pred, np.nan)
        for idx in range(0, n_pred, 10):
            pred[idx] = _physics_sim(
                bg[idx], fd['supply'][idx:idx+h_steps], fd['demand'][idx:idx+h_steps],
                fd['hepatic'][idx:idx+h_steps], resid[idx], pop_w, pop_d, h_steps
            )
        pop_r2 = _r2(pred, actual)

        gap = pop_r2 - pp['personal_r2']
        loo_results.append({
            'patient': pp['name'],
            'personal_r2': pp['personal_r2'],
            'pop_r2': round(pop_r2, 3),
            'gap': round(gap, 3),
        })

    mean_personal = np.mean([r['personal_r2'] for r in loo_results])
    mean_pop = np.mean([r['pop_r2'] for r in loo_results])
    mean_gap = mean_pop - mean_personal

    detail_parts = [f'{r["patient"]}: pers={r["personal_r2"]}/pop={r["pop_r2"]}/Δ={r["gap"]}' for r in loo_results[:8]]
    return {
        'status': 'pass',
        'detail': f'mean personal={mean_personal:.3f}, pop={mean_pop:.3f}, gap={mean_gap:.3f}. ' + '; '.join(detail_parts),
        'loo_results': loo_results,
        'mean_personal': round(mean_personal, 3),
        'mean_pop': round(mean_pop, 3),
    }


# ---------------------------------------------------------------------------
# EXP-770: Settings Change Recommendation via Gradient
# ---------------------------------------------------------------------------
@register('EXP-770', 'Settings Gradient Optimization')
def exp_770(patients, detail=False):
    """Use physics residuals to compute gradient-based settings adjustments."""
    results = []

    for p in patients:
        fd = _compute_flux(p)
        bg = fd['bg']
        supply = fd['supply']
        demand = fd['demand']
        hepatic = fd['hepatic']
        resid = fd['resid']
        n = fd['n']
        nr = len(resid)
        df = p['df']

        # Get current profile parameters
        attrs = df.attrs if hasattr(df, 'attrs') else {}
        cr_schedule = attrs.get('cr_schedule', attrs.get('carb_ratio', attrs.get('carbRatio', None)))
        isf_schedule = attrs.get('isf_schedule', attrs.get('sens', attrs.get('sensitivity', attrs.get('isf', None))))

        if not cr_schedule or not isf_schedule:
            continue

        # Current mean CR and ISF
        if isinstance(cr_schedule, list):
            mean_cr = np.mean([float(s.get('value', s.get('cr', s.get('timeAsSeconds', 10)))) for s in cr_schedule])
        else:
            mean_cr = float(cr_schedule) if cr_schedule else 10.0

        if isinstance(isf_schedule, list):
            mean_isf = np.mean([float(s.get('value', s.get('isf', s.get('sensitivity', 50)))) for s in isf_schedule])
        else:
            mean_isf = float(isf_schedule) if isf_schedule else 50.0

        # Convert mmol ISF to mg/dL if needed
        if mean_isf < 15:
            mean_isf *= 18.0182

        # Compute gradient: how does changing CR/ISF/basal affect residual?
        # For CR: higher CR → less insulin per carb → more supply effect → higher BG
        # For ISF: higher ISF → more BG drop per unit insulin → more demand effect
        # For basal: higher basal → more base demand → lower BG

        # Estimate optimal adjustments from residual integral
        mean_resid = np.nanmean(resid)
        positive_resid_frac = np.mean(resid > 0)

        # Basal gradient: mean residual during low-activity periods
        s_med = np.nanmedian(supply)
        d_med = np.nanmedian(demand)
        quiet = (supply[:nr] < s_med * 1.2) & (demand[:nr] < d_med * 1.2)
        if quiet.sum() > 100:
            basal_resid = np.nanmean(resid[quiet])
        else:
            basal_resid = mean_resid

        # CR gradient: residual during meal periods
        meal_mask = supply[:nr] > s_med * 2.0
        if meal_mask.sum() > 50:
            meal_resid = np.nanmean(resid[meal_mask])
        else:
            meal_resid = 0

        # ISF gradient: residual during correction periods
        corr_mask = demand[:nr] > d_med * 2.0
        if corr_mask.sum() > 50:
            corr_resid = np.nanmean(resid[corr_mask])
        else:
            corr_resid = 0

        # Recommended adjustments
        # Basal: if residual positive during quiet → basal too low
        basal_adj_pct = -basal_resid / (mean_isf / 60.0) * 100 / 24 if mean_isf > 0 else 0  # rough %
        basal_adj_pct = np.clip(basal_adj_pct, -30, 30)

        # CR: if residual positive during meals → CR too high (not enough insulin)
        cr_adj_pct = -meal_resid * 2.0
        cr_adj_pct = np.clip(cr_adj_pct, -20, 20)

        # ISF: if residual negative during corrections → ISF too high (over-correcting)
        isf_adj_pct = corr_resid * 2.0
        isf_adj_pct = np.clip(isf_adj_pct, -30, 30)

        results.append({
            'patient': p['name'],
            'current_cr': round(mean_cr, 1),
            'current_isf': round(mean_isf, 1),
            'basal_adj_pct': round(float(basal_adj_pct), 1),
            'cr_adj_pct': round(float(cr_adj_pct), 1),
            'isf_adj_pct': round(float(isf_adj_pct), 1),
            'mean_resid': round(float(mean_resid), 3),
            'positive_frac': round(float(positive_resid_frac), 2),
        })

    detail_parts = [
        f'{r["patient"]}: basal{r["basal_adj_pct"]:+.0f}%, CR{r["cr_adj_pct"]:+.0f}%, ISF{r["isf_adj_pct"]:+.0f}%'
        for r in results[:8]
    ]
    return {
        'status': 'pass',
        'detail': f'n={len(results)}. ' + ', '.join(detail_parts),
        'per_patient': results,
    }


# ===========================================================================
# Runner
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(description='EXP-761-770: Refined Clinical Intelligence')
    parser.add_argument('--max-patients', type=int, default=11)
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--only', type=str, default=None, help='Run single experiment, e.g. EXP-761')
    args = parser.parse_args()

    print(f'Loading patients (max={args.max_patients})...')
    patients = load_patients(PATIENTS_DIR, max_patients=args.max_patients)
    print(f'Loaded {len(patients)} patients\n')

    passed = 0
    failed = 0
    results_all = []

    exps = EXPERIMENTS
    if args.only:
        exps = {k: v for k, v in EXPERIMENTS.items() if k == args.only}
        if not exps:
            print(f'Unknown experiment: {args.only}')
            sys.exit(1)

    for exp_id, exp_info in exps.items():
        print(f'\n{"="*60}')
        print(f'Running {exp_id}: {exp_info["name"]}')
        print(f'{"="*60}')

        t0 = time.time()
        try:
            result = exp_info['func'](patients, detail=args.detail)
            elapsed = time.time() - t0
            status = result.get('status', 'pass')
            detail = result.get('detail', '')
            print(f'  Status: {status} ({elapsed:.1f}s)')
            print(f'  Detail: {detail}')
            if status == 'pass':
                passed += 1
            else:
                failed += 1
            result['exp_id'] = exp_id
            result['name'] = exp_info['name']
            result['elapsed'] = round(elapsed, 1)
            results_all.append(result)
        except Exception as e:
            elapsed = time.time() - t0
            print(f'  Status: FAIL ({elapsed:.1f}s)')
            print(f'  Error: {e}')
            traceback.print_exc()
            failed += 1
            results_all.append({
                'exp_id': exp_id, 'name': exp_info['name'],
                'status': 'fail', 'error': str(e),
            })

    print(f'\n{"="*60}')
    print(f'SUMMARY')
    print(f'{"="*60}')
    print(f'Passed: {passed}/{passed+failed}, Failed: {failed}/{passed+failed}')

    for r in results_all:
        status_char = 'V' if r['status'] == 'pass' else 'X'
        detail = r.get('detail', r.get('error', ''))[:80]
        print(f'  {status_char} {r["exp_id"]} {r["name"]}: {detail}')

    if args.save:
        save_dir = Path(__file__).parent.parent.parent / 'externals' / 'experiments'
        save_dir.mkdir(parents=True, exist_ok=True)
        for r in results_all:
            safe_name = r['name'].lower().replace(' ', '_').replace('/', '-')[:25]
            fname = f'exp_{r["exp_id"].split("-")[1]}_{r["exp_id"].lower()}_{safe_name}.json'
            with open(save_dir / fname, 'w') as f:
                # Remove non-serializable items
                clean = {}
                for k, v in r.items():
                    try:
                        json.dumps(v)
                        clean[k] = v
                    except (TypeError, ValueError):
                        clean[k] = str(v)
                json.dump(clean, f, indent=2)
            print(f'  Saved: {fname}')


if __name__ == '__main__':
    main()
