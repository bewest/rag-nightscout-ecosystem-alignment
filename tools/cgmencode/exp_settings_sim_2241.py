#!/usr/bin/env python3
"""
EXP-2241–2248: Settings Correction Simulation & Outcome Projection

Replays historical CGM/insulin data under corrected settings to project outcomes.
Uses the recommendations from EXP-2231–2238 to simulate what-if scenarios.

Experiments:
  EXP-2241: Basal correction replay — simulate loop behavior with corrected basal
  EXP-2242: ISF correction replay — simulate correction bolus outcomes with true ISF
  EXP-2243: Combined correction replay — both basal + ISF corrected
  EXP-2244: Oscillation reduction projection — fewer suspend-surge cycles
  EXP-2245: Hypo prevention projection — how many hypos would be eliminated
  EXP-2246: Time-in-range improvement projection — expected TIR gains
  EXP-2247: Safety margin analysis — risk of over-correction with new settings
  EXP-2248: Graduated transition design — stepwise change schedule

Usage:
  PYTHONPATH=tools python3 tools/cgmencode/exp_settings_sim_2241.py --figures
"""

import argparse
import json
import os
import sys
import warnings
from collections import defaultdict

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

warnings.filterwarnings('ignore')

STEP_MIN = 5
STEPS_PER_HOUR = 12
STEPS_PER_DAY = 288

# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────

class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


def load_patients(data_dir='externals/ns-data/patients/'):
    from cgmencode.exp_metabolic_441 import load_patients as _load
    return _load(data_dir)


def get_schedule_value(schedule, hour):
    """Get scheduled value for a given hour from a schedule list."""
    if not schedule:
        return 0
    val = schedule[0].get('value', 0)
    for entry in schedule:
        entry_h = entry.get('timeAsSeconds', 0) / 3600
        if entry_h <= hour:
            val = entry.get('value', 0)
    return val


def build_scheduled_array(schedule, hours):
    """Vectorized: build scheduled value array for all hours at once."""
    if not schedule:
        return np.zeros(len(hours))
    # Sort entries by timeAsSeconds
    entries = sorted(schedule, key=lambda e: e.get('timeAsSeconds', 0))
    result = np.full(len(hours), entries[0].get('value', 0), dtype=float)
    for entry in entries:
        entry_h = entry.get('timeAsSeconds', 0) / 3600
        mask = hours >= entry_h
        result[mask] = entry.get('value', 0)
    return result


def compute_tir_tbr_tar(glucose):
    """Compute TIR, TBR, TAR from glucose array."""
    valid = glucose[~np.isnan(glucose)]
    if len(valid) == 0:
        return 0, 0, 0
    tir = np.mean((valid >= 70) & (valid <= 180)) * 100
    tbr = np.mean(valid < 70) * 100
    tar = np.mean(valid > 180) * 100
    return tir, tbr, tar


def identify_hypo_events(glucose, threshold=70, min_duration_steps=3):
    """Identify contiguous hypo events (< threshold for >= min_duration_steps)."""
    below = glucose < threshold
    events = []
    in_event = False
    start = 0
    for i in range(len(below)):
        if below[i] and not np.isnan(glucose[i]):
            if not in_event:
                start = i
                in_event = True
        else:
            if in_event:
                if i - start >= min_duration_steps:
                    events.append((start, i))
                in_event = False
    if in_event and len(below) - start >= min_duration_steps:
        events.append((start, len(below)))
    return events


def get_hourly_delivery(df):
    """Get hourly actual vs scheduled delivery arrays."""
    glucose = df['glucose'].values
    n = len(glucose)
    hours = np.arange(n) * STEP_MIN / 60 % 24

    # Get enacted rates
    enacted = df['enacted_rate'].values if 'enacted_rate' in df.columns else np.full(n, np.nan)
    net_basal = df['net_basal'].values if 'net_basal' in df.columns else np.full(n, np.nan)

    # Use net_basal as fallback
    actual_rate = np.where(np.isnan(enacted), net_basal, enacted)

    return hours, actual_rate


def compute_actual_delivery(df, scheduled):
    """Compute actual delivery rate array from best available data.

    Priority: enacted_rate (absolute). Fallback: scheduled + net_basal (delta).
    Returns actual delivery rate array (same length as df).
    """
    n = len(df)
    enacted = df['enacted_rate'].values if 'enacted_rate' in df.columns else np.full(n, np.nan)
    net_basal = df['net_basal'].values if 'net_basal' in df.columns else np.full(n, np.nan)

    # Use enacted_rate where valid; fall back to scheduled + net_basal
    actual = enacted.copy()
    nan_mask = np.isnan(actual)
    if nan_mask.any() and not np.all(np.isnan(net_basal)):
        actual[nan_mask] = scheduled[nan_mask] + np.where(
            np.isnan(net_basal[nan_mask]), 0, net_basal[nan_mask])

    return actual


def compute_delivery_ratio_sum(actual, scheduled, valid_mask):
    """Sum-based delivery ratio: total delivered / total scheduled.
    More accurate than per-step median for suspend-surge patterns."""
    if valid_mask.sum() == 0:
        return 0
    total_delivered = np.nansum(actual[valid_mask])
    total_scheduled = np.nansum(scheduled[valid_mask])
    if total_scheduled <= 0:
        return 0
    return total_delivered / total_scheduled


def find_corrections_vectorized(glucose, bolus, carbs, n, min_bolus=0.5, min_glucose=150):
    """Vectorized correction finder: bolus >= min_bolus, glucose > min_glucose, no carbs ±2h.
    Returns list of (index, dose, glucose_at_bolus, effective_isf, nadir) tuples."""
    # Candidate mask: bolus >= threshold AND glucose > threshold
    bolus_mask = ~np.isnan(bolus) & (bolus >= min_bolus)
    glucose_mask = ~np.isnan(glucose) & (glucose > min_glucose)
    candidates = np.where(bolus_mask & glucose_mask)[0]

    if len(candidates) == 0:
        return []

    # Rolling carb sum: use cumsum for O(1) window queries
    carbs_clean = np.where(np.isnan(carbs), 0, carbs)
    carbs_cumsum = np.cumsum(carbs_clean)

    corrections = []
    for idx in candidates:
        # Carb window: ±2h
        cw_start = max(0, idx - STEPS_PER_HOUR * 2)
        cw_end = min(n, idx + STEPS_PER_HOUR * 2)
        carb_sum = carbs_cumsum[cw_end - 1] - (carbs_cumsum[cw_start - 1] if cw_start > 0 else 0)
        if carb_sum > 1:
            continue

        # Post-bolus window: 3h
        post_end = min(n, idx + STEPS_PER_HOUR * 3)
        if post_end - idx < STEPS_PER_HOUR:
            continue
        post_g = glucose[idx:post_end]
        if np.isnan(post_g).mean() > 0.3:
            continue

        nadir = np.nanmin(post_g)
        drop = glucose[idx] - nadir
        if drop > 0:
            eff_isf = drop / bolus[idx]
            corrections.append((idx, bolus[idx], glucose[idx], eff_isf, nadir))

    return corrections


# ─────────────────────────────────────────────────────────────────
# EXP-2241: Basal Correction Replay
# ─────────────────────────────────────────────────────────────────

def exp_2241_basal_correction_replay(patients):
    """
    Simulate: if basal were set to match delivery ratio, how would the
    loop's behavior change? We compute what fraction of time the loop
    would NO LONGER need to suspend/reduce delivery.
    """
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        glucose = df['glucose'].values
        n = len(glucose)

        # Get schedules
        basal_sched = df.attrs.get('basal_schedule', [])
        if not basal_sched:
            results[name] = {'skip': True, 'reason': 'no basal schedule'}
            continue

        hours = np.arange(n) * STEP_MIN / 60 % 24

        # Build scheduled basal array
        scheduled = build_scheduled_array(basal_sched, hours)

        # Get actual delivery
        actual = compute_actual_delivery(df, scheduled)

        valid_mask = ~np.isnan(actual) & ~np.isnan(scheduled) & (scheduled > 0)
        if valid_mask.sum() < STEPS_PER_DAY:
            results[name] = {'skip': True, 'reason': 'insufficient delivery data'}
            continue

        # Current: fraction of time loop reduces/suspends
        ratio = np.where(valid_mask, actual / np.maximum(scheduled, 0.01), np.nan)
        current_suspend_pct = np.nanmean(ratio[valid_mask] < 0.1) * 100
        current_reduce_pct = np.nanmean(ratio[valid_mask] < 0.5) * 100
        current_full_pct = np.nanmean((ratio[valid_mask] >= 0.8) & (ratio[valid_mask] <= 1.2)) * 100

        # Corrected basal = scheduled * delivery_ratio_by_hour (sum-based)
        hourly_dr = np.zeros(24)
        for h in range(24):
            hmask = valid_mask & (hours.astype(int) == h)
            if hmask.sum() > 0:
                hourly_dr[h] = np.nansum(actual[hmask]) / np.nansum(scheduled[hmask]) if np.nansum(scheduled[hmask]) > 0 else 1.0
            else:
                hourly_dr[h] = 1.0

        corrected_sched = np.array([scheduled[i] * hourly_dr[int(hours[i])] for i in range(n)])

        # With corrected basal, the loop would deliver closer to 100% of scheduled
        # (because scheduled now matches what the loop actually wanted to deliver)
        new_ratio = np.where(valid_mask & (corrected_sched > 0.01),
                            actual / corrected_sched, np.nan)
        new_full_pct = np.nanmean((new_ratio[valid_mask] >= 0.8) & (new_ratio[valid_mask] <= 1.2)) * 100
        new_suspend_pct = np.nanmean(new_ratio[valid_mask] < 0.1) * 100
        new_reduce_pct = np.nanmean(new_ratio[valid_mask] < 0.5) * 100

        # Overall delivery ratio (sum-based for accuracy with suspend-surge patterns)
        overall_dr = compute_delivery_ratio_sum(actual, scheduled, valid_mask)

        results[name] = {
            'overall_delivery_ratio': round(overall_dr, 3),
            'current_suspend_pct': round(current_suspend_pct, 1),
            'current_reduce_pct': round(current_reduce_pct, 1),
            'current_full_delivery_pct': round(current_full_pct, 1),
            'corrected_suspend_pct': round(new_suspend_pct, 1),
            'corrected_reduce_pct': round(new_reduce_pct, 1),
            'corrected_full_delivery_pct': round(new_full_pct, 1),
            'suspend_reduction_pct': round(current_suspend_pct - new_suspend_pct, 1),
            'full_delivery_gain_pct': round(new_full_pct - current_full_pct, 1),
            'hourly_delivery_ratio': [round(h, 3) for h in hourly_dr],
        }

    return results


# ─────────────────────────────────────────────────────────────────
# EXP-2242: ISF Correction Replay
# ─────────────────────────────────────────────────────────────────

def exp_2242_isf_correction_replay(patients):
    """
    Simulate: if ISF matched observed effectiveness, how would correction
    bolus doses differ? Compute dose reduction and projected glucose outcomes.
    """
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        glucose = df['glucose'].values
        n = len(glucose)

        isf_sched = df.attrs.get('isf_schedule', [])
        if not isf_sched:
            results[name] = {'skip': True, 'reason': 'no ISF schedule'}
            continue

        # Get profile ISF (convert mmol if needed)
        profile_isf = isf_sched[0].get('value', 50)
        if profile_isf < 15:
            profile_isf *= 18.0182

        bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(n)
        carbs = df['carbs'].values if 'carbs' in df.columns else np.zeros(n)

        # Find correction boluses: bolus >= 0.5U, glucose > 150, no carbs ±2h
        corrections = []
        for i in range(n):
            if np.isnan(bolus[i]) or bolus[i] < 0.5:
                continue
            if np.isnan(glucose[i]) or glucose[i] <= 150:
                continue
            # No carbs within ±2h
            carb_window = slice(max(0, i - STEPS_PER_HOUR * 2), min(n, i + STEPS_PER_HOUR * 2))
            if np.nansum(carbs[carb_window]) > 1:
                continue
            # Track 3h post-bolus glucose
            post_end = min(n, i + STEPS_PER_HOUR * 3)
            if post_end - i < STEPS_PER_HOUR:
                continue
            post_glucose = glucose[i:post_end]
            if np.isnan(post_glucose).mean() > 0.3:
                continue

            nadir = np.nanmin(post_glucose)
            drop = glucose[i] - nadir
            effective_isf = drop / bolus[i] if bolus[i] > 0 else 0

            # What dose would have been with corrected ISF?
            target = 110  # typical target
            current_dose = bolus[i]
            correction_needed = glucose[i] - target
            if effective_isf > 0:
                corrected_dose = correction_needed / effective_isf
            else:
                corrected_dose = current_dose

            corrections.append({
                'idx': i,
                'glucose': glucose[i],
                'dose': current_dose,
                'drop': drop,
                'effective_isf': effective_isf,
                'corrected_dose': max(0, corrected_dose),
                'dose_reduction': current_dose - max(0, corrected_dose),
                'nadir': nadir,
                'projected_nadir': glucose[i] - max(0, corrected_dose) * effective_isf if effective_isf > 0 else nadir,
            })

        if len(corrections) < 5:
            results[name] = {'skip': True, 'reason': f'insufficient corrections ({len(corrections)})'}
            continue

        doses = np.array([c['dose'] for c in corrections])
        corrected_doses = np.array([c['corrected_dose'] for c in corrections])
        reductions = np.array([c['dose_reduction'] for c in corrections])
        effective_isfs = np.array([c['effective_isf'] for c in corrections])
        nadirs = np.array([c['nadir'] for c in corrections])
        projected_nadirs = np.array([c['projected_nadir'] for c in corrections])

        # How many hypos would be prevented?
        current_hypos = np.sum(nadirs < 70)
        projected_hypos = np.sum(projected_nadirs < 70)

        results[name] = {
            'n_corrections': len(corrections),
            'profile_isf': round(profile_isf, 1),
            'mean_effective_isf': round(np.mean(effective_isfs), 1),
            'isf_ratio': round(np.mean(effective_isfs) / profile_isf, 2) if profile_isf > 0 else 0,
            'mean_current_dose': round(np.mean(doses), 2),
            'mean_corrected_dose': round(np.mean(corrected_doses), 2),
            'mean_dose_reduction_u': round(np.mean(reductions), 2),
            'mean_dose_reduction_pct': round(np.mean(reductions / np.maximum(doses, 0.1)) * 100, 1),
            'current_correction_hypos': int(current_hypos),
            'projected_correction_hypos': int(projected_hypos),
            'hypos_prevented': int(current_hypos - projected_hypos),
            'hypo_prevention_pct': round((current_hypos - projected_hypos) / max(current_hypos, 1) * 100, 1),
        }

    return results


# ─────────────────────────────────────────────────────────────────
# EXP-2243: Combined Correction Replay
# ─────────────────────────────────────────────────────────────────

def exp_2243_combined_correction(patients):
    """
    Simulate combined basal + ISF correction. Estimate the net effect on
    glucose distribution: reduced suspension time + appropriate correction doses.
    """
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        glucose = df['glucose'].values
        n = len(glucose)

        basal_sched = df.attrs.get('basal_schedule', [])
        isf_sched = df.attrs.get('isf_schedule', [])

        if not basal_sched or not isf_sched:
            results[name] = {'skip': True, 'reason': 'missing schedule data'}
            continue

        profile_isf = isf_sched[0].get('value', 50)
        if profile_isf < 15:
            profile_isf *= 18.0182

        hours = np.arange(n) * STEP_MIN / 60 % 24
        scheduled = build_scheduled_array(basal_sched, hours)
        actual = compute_actual_delivery(df, scheduled)
        bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(n)

        valid_mask = ~np.isnan(actual) & ~np.isnan(scheduled) & (scheduled > 0)
        if valid_mask.sum() < STEPS_PER_DAY:
            results[name] = {'skip': True, 'reason': 'insufficient data'}
            continue

        # Current glucose stats
        tir, tbr, tar = compute_tir_tbr_tar(glucose)

        # Current total daily insulin
        basal_daily = np.nansum(actual[valid_mask]) * STEP_MIN / 60 / (valid_mask.sum() / STEPS_PER_DAY)
        bolus_daily = np.nansum(bolus) * STEPS_PER_DAY / n

        # Delivery ratio (sum-based)
        dr = compute_delivery_ratio_sum(actual, scheduled, valid_mask)

        # Simulate: corrected basal = actual delivery (no more suspension needed)
        # Corrected ISF → smaller correction boluses
        # Estimate: current over-bolusing fraction
        isf_ratio = 1.0  # how much more effective insulin is vs profile
        # Find corrections to estimate ISF ratio (vectorized)
        carbs_arr = df['carbs'].values if 'carbs' in df.columns else np.zeros(n)
        corrections = find_corrections_vectorized(glucose, bolus, carbs_arr, n)

        if corrections:
            effective_isf = np.median([c[3] for c in corrections])
            isf_ratio = effective_isf / profile_isf if profile_isf > 0 else 1.0
        else:
            effective_isf = profile_isf
            isf_ratio = 1.0

        # Projected savings
        # 1. Basal: corrected basal means less total basal insulin wasted on suspension
        corrected_basal_daily = basal_daily  # same total (loop already delivered what it wanted)

        # 2. Bolus: with corrected ISF, correction boluses reduced by (1 - 1/ratio)
        bolus_reduction_factor = 1 / max(isf_ratio, 1.0)
        corrected_bolus_daily = bolus_daily * bolus_reduction_factor

        # 3. Total insulin change
        current_tdd = basal_daily + bolus_daily
        corrected_tdd = corrected_basal_daily + corrected_bolus_daily

        # Projected TBR reduction (empirical: each halving of over-bolusing ~halves TBR)
        projected_tbr = tbr * bolus_reduction_factor if isf_ratio > 1 else tbr

        # Projected TIR (reduced variability → more time in range)
        # Empirical estimate: reduced oscillation improves TIR by ~5-15%
        variability_reduction = 1 - bolus_reduction_factor
        projected_tir_gain = variability_reduction * 10  # ~10% per unit reduction
        projected_tir = min(100, tir + projected_tir_gain)

        results[name] = {
            'current_tir': round(tir, 1),
            'current_tbr': round(tbr, 1),
            'current_tar': round(tar, 1),
            'delivery_ratio': round(dr, 3),
            'isf_ratio': round(isf_ratio, 2),
            'current_tdd': round(current_tdd, 1),
            'corrected_tdd': round(corrected_tdd, 1),
            'tdd_change_pct': round((corrected_tdd - current_tdd) / max(current_tdd, 0.1) * 100, 1),
            'bolus_reduction_pct': round((1 - bolus_reduction_factor) * 100, 1),
            'projected_tir': round(projected_tir, 1),
            'projected_tbr': round(projected_tbr, 1),
            'projected_tir_gain': round(projected_tir_gain, 1),
            'projected_tbr_reduction': round(tbr - projected_tbr, 1),
        }

    return results


# ─────────────────────────────────────────────────────────────────
# EXP-2244: Oscillation Reduction Projection
# ─────────────────────────────────────────────────────────────────

def exp_2244_oscillation_reduction(patients):
    """
    Estimate how many suspend-surge oscillation cycles would be eliminated
    by correcting basal rates. An oscillation cycle = suspension followed
    by a surge delivery period.
    """
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        glucose = df['glucose'].values
        n = len(glucose)

        basal_sched = df.attrs.get('basal_schedule', [])
        if not basal_sched:
            results[name] = {'skip': True, 'reason': 'no basal schedule'}
            continue

        hours = np.arange(n) * STEP_MIN / 60 % 24
        scheduled = build_scheduled_array(basal_sched, hours)
        actual = compute_actual_delivery(df, scheduled)

        valid_mask = ~np.isnan(actual) & ~np.isnan(scheduled) & (scheduled > 0)
        if valid_mask.sum() < STEPS_PER_DAY:
            results[name] = {'skip': True, 'reason': 'insufficient data'}
            continue

        ratio = np.where(valid_mask, actual / np.maximum(scheduled, 0.01), np.nan)

        # Detect oscillation cycles vectorized: transition from low (<0.2) to high (>1.5)
        # Use state transitions on valid data only
        valid_ratio = ratio[valid_mask]
        in_suspend_v = valid_ratio < 0.2
        in_surge_v = valid_ratio > 1.5

        # Build state array: 0=normal, 1=suspend, 2=surge
        state = np.zeros(len(valid_ratio), dtype=int)
        state[in_suspend_v] = 1
        state[in_surge_v] = 2

        # Find transitions: suspend (1) → surge (2) via diff on cumulative state tracking
        # A cycle occurs when we see state=2 after having seen state=1 since last state=2
        # Vectorized: track "last suspend seen" vs "last surge seen"
        suspend_cumsum = np.cumsum(state == 1)
        surge_indices = np.where(state == 2)[0]

        # For each surge, check if any suspend occurred since the previous surge
        cycles = 0
        last_surge_idx = -1
        for si in surge_indices:
            # Any suspend between last_surge_idx and si?
            if last_surge_idx < 0:
                if suspend_cumsum[si] > 0:
                    cycles += 1
            else:
                suspend_before = suspend_cumsum[last_surge_idx] if last_surge_idx < len(suspend_cumsum) else 0
                if suspend_cumsum[si] > suspend_before:
                    cycles += 1
            last_surge_idx = si

        # Estimate basal-related fraction: using bolus rolling sum
        bolus_arr = df['bolus'].values if 'bolus' in df.columns else np.zeros(n)
        bolus_clean = np.where(np.isnan(bolus_arr), 0, bolus_arr)
        # Rolling 2h bolus sum
        window_size = STEPS_PER_HOUR * 2
        bolus_cumsum = np.cumsum(bolus_clean)
        bolus_rolling = np.zeros(n)
        bolus_rolling[window_size:] = bolus_cumsum[window_size:] - bolus_cumsum[:-window_size]
        bolus_rolling[:window_size] = bolus_cumsum[:window_size]

        # Surge points with no recent bolus = basal-related
        valid_indices = np.where(valid_mask)[0]
        surge_global_indices = valid_indices[surge_indices] if len(surge_indices) > 0 else np.array([], dtype=int)
        if len(surge_global_indices) > 0:
            basal_related_surges = np.sum(bolus_rolling[surge_global_indices] < 0.1)
            basal_fraction = basal_related_surges / max(len(surge_global_indices), 1)
        else:
            basal_fraction = 0
        basal_related_cycles = int(cycles * basal_fraction)

        n_days = valid_mask.sum() / STEPS_PER_DAY
        cycles_per_day = cycles / max(n_days, 1)
        basal_cycles_per_day = basal_related_cycles / max(n_days, 1)

        # With corrected basal, basal-related cycles would be eliminated
        projected_cycles_per_day = cycles_per_day - basal_cycles_per_day

        # Time spent in suspension
        suspend_pct = np.mean(in_suspend_v) * 100
        surge_pct = np.mean(in_surge_v) * 100
        normal_pct = 100 - suspend_pct - surge_pct

        results[name] = {
            'total_cycles': int(cycles),
            'cycles_per_day': round(cycles_per_day, 1),
            'basal_related_cycles': int(basal_related_cycles),
            'basal_cycles_per_day': round(basal_cycles_per_day, 1),
            'projected_cycles_per_day': round(projected_cycles_per_day, 1),
            'cycle_reduction_pct': round(basal_related_cycles / max(cycles, 1) * 100, 1),
            'suspend_pct': round(suspend_pct, 1),
            'surge_pct': round(surge_pct, 1),
            'normal_delivery_pct': round(normal_pct, 1),
        }

    return results


# ─────────────────────────────────────────────────────────────────
# EXP-2245: Hypo Prevention Projection
# ─────────────────────────────────────────────────────────────────

def exp_2245_hypo_prevention(patients):
    """
    Classify each hypo event by cause and estimate which would be prevented
    by settings correction. Basal-hypos → prevented by basal reduction.
    Bolus-hypos → prevented by ISF correction.
    """
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        glucose = df['glucose'].values
        n = len(glucose)

        bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(n)
        carbs = df['carbs'].values if 'carbs' in df.columns else np.zeros(n)
        enacted = df['enacted_rate'].values if 'enacted_rate' in df.columns else np.full(n, np.nan)

        hypo_events = identify_hypo_events(glucose)
        if not hypo_events:
            results[name] = {
                'n_hypos': 0, 'preventable': 0, 'prevention_rate': 0,
                'basal_hypos': 0, 'bolus_hypos': 0, 'meal_hypos': 0, 'unknown_hypos': 0,
            }
            continue

        basal_hypos = 0
        bolus_hypos = 0
        meal_hypos = 0
        unknown_hypos = 0

        for start, end in hypo_events:
            # Check 2h before onset
            window = slice(max(0, start - STEPS_PER_HOUR * 2), start)
            recent_bolus = np.nansum(bolus[window])
            recent_carbs = np.nansum(carbs[window])
            recent_high_basal = False
            if not np.all(np.isnan(enacted[window])):
                recent_high_basal = np.nanmean(enacted[window]) > 0

            if recent_bolus >= 0.5 and recent_carbs <= 1:
                bolus_hypos += 1  # Correction bolus → preventable by ISF fix
            elif recent_carbs > 1 and recent_bolus >= 0.3:
                meal_hypos += 1  # Over-bolusing for meal → partially preventable
            elif recent_high_basal and recent_bolus < 0.3:
                basal_hypos += 1  # Basal-only → preventable by basal reduction
            else:
                unknown_hypos += 1

        # Preventable = basal_hypos (full) + bolus_hypos (most) + meal_hypos (partial)
        preventable = basal_hypos + int(bolus_hypos * 0.8) + int(meal_hypos * 0.3)
        n_days = n / STEPS_PER_DAY
        n_hypos = len(hypo_events)

        results[name] = {
            'n_hypos': n_hypos,
            'hypos_per_day': round(n_hypos / n_days, 2),
            'basal_hypos': basal_hypos,
            'bolus_hypos': bolus_hypos,
            'meal_hypos': meal_hypos,
            'unknown_hypos': unknown_hypos,
            'preventable': preventable,
            'prevention_rate': round(preventable / max(n_hypos, 1) * 100, 1),
            'projected_hypos_per_day': round((n_hypos - preventable) / n_days, 2),
            'basal_pct': round(basal_hypos / max(n_hypos, 1) * 100, 1),
            'bolus_pct': round(bolus_hypos / max(n_hypos, 1) * 100, 1),
            'meal_pct': round(meal_hypos / max(n_hypos, 1) * 100, 1),
        }

    return results


# ─────────────────────────────────────────────────────────────────
# EXP-2246: Time-in-Range Improvement Projection
# ─────────────────────────────────────────────────────────────────

def exp_2246_tir_projection(patients):
    """
    Estimate TIR improvement from reduced oscillation and corrected dosing.
    Uses the relationship between delivery ratio, ISF mismatch, and TIR.
    """
    results = {}

    # First pass: collect all patients' data for cross-patient regression
    all_data = []
    for pat in patients:
        name = pat['name']
        df = pat['df']
        glucose = df['glucose'].values
        n = len(glucose)

        basal_sched = df.attrs.get('basal_schedule', [])
        isf_sched = df.attrs.get('isf_schedule', [])

        tir, tbr, tar = compute_tir_tbr_tar(glucose)

        # Delivery ratio
        hours = np.arange(n) * STEP_MIN / 60 % 24
        if basal_sched:
            scheduled = build_scheduled_array(basal_sched, hours)
        else:
            scheduled = np.ones(n)
        actual = compute_actual_delivery(df, scheduled)

        valid = ~np.isnan(actual) & ~np.isnan(scheduled) & (scheduled > 0)
        dr = compute_delivery_ratio_sum(actual, scheduled, valid) if valid.sum() > 0 else 1.0

        # Glucose CV
        valid_g = glucose[~np.isnan(glucose)]
        cv = np.std(valid_g) / np.mean(valid_g) * 100 if len(valid_g) > 0 else 0

        all_data.append({
            'name': name, 'tir': tir, 'tbr': tbr, 'tar': tar,
            'dr': dr, 'cv': cv,
        })

    # Empirical model: patients with DR closer to 1.0 tend to have less variability
    # Projected: if we correct DR to ~1.0, estimate TIR gain
    for d in all_data:
        name = d['name']

        # DR correction: moving from current DR toward 1.0
        dr_distance = abs(1.0 - d['dr'])
        # Empirical: each 0.1 improvement in DR distance → ~1% TIR gain
        tir_from_basal = dr_distance * 10  # bounded estimate

        # CV reduction from less oscillation → TIR improvement
        # High CV → more room for improvement
        cv_improvement = max(0, (d['cv'] - 30)) * 0.2  # ~0.2% TIR per % CV above 30%

        projected_tir_gain = min(25, tir_from_basal + cv_improvement)  # cap at 25%
        projected_tir = min(100, d['tir'] + projected_tir_gain)

        # TBR reduction: primarily from ISF correction
        projected_tbr = max(0, d['tbr'] * 0.5)  # conservative 50% reduction

        results[name] = {
            'current_tir': round(d['tir'], 1),
            'current_tbr': round(d['tbr'], 1),
            'current_tar': round(d['tar'], 1),
            'current_cv': round(d['cv'], 1),
            'delivery_ratio': round(d['dr'], 3),
            'projected_tir': round(projected_tir, 1),
            'projected_tbr': round(projected_tbr, 1),
            'projected_tir_gain': round(projected_tir_gain, 1),
            'projected_tbr_reduction': round(d['tbr'] - projected_tbr, 1),
            'meets_guidelines': projected_tir >= 70 and projected_tbr < 4,
        }

    return results


# ─────────────────────────────────────────────────────────────────
# EXP-2247: Safety Margin Analysis
# ─────────────────────────────────────────────────────────────────

def exp_2247_safety_margins(patients):
    """
    Analyze risk of over-correction: if we reduce basal too much or raise
    ISF too high, what's the safety margin? Use worst-case scenarios.
    """
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        glucose = df['glucose'].values
        n = len(glucose)

        basal_sched = df.attrs.get('basal_schedule', [])
        isf_sched = df.attrs.get('isf_schedule', [])

        if not basal_sched:
            results[name] = {'skip': True, 'reason': 'no schedule data'}
            continue

        hours = np.arange(n) * STEP_MIN / 60 % 24
        scheduled = build_scheduled_array(basal_sched, hours)
        actual = compute_actual_delivery(df, scheduled)

        valid = ~np.isnan(actual) & ~np.isnan(scheduled) & (scheduled > 0)
        if valid.sum() < STEPS_PER_DAY:
            results[name] = {'skip': True, 'reason': 'insufficient data'}
            continue

        ratio = actual[valid] / np.maximum(scheduled[valid], 0.01)

        # Overall sum-based delivery ratio
        dr_overall = compute_delivery_ratio_sum(actual, scheduled, valid)

        # Per-step delivery ratio statistics for safety margin analysis
        dr_median = np.nanmedian(ratio)
        dr_p10 = np.nanpercentile(ratio, 10)
        dr_p25 = np.nanpercentile(ratio, 25)
        dr_p75 = np.nanpercentile(ratio, 75)
        dr_p90 = np.nanpercentile(ratio, 90)

        # Safety test: if we set basal = scheduled * dr_overall,
        # how often would the new scheduled EXCEED the actual delivery?
        corrected_sched = scheduled * dr_overall
        under_delivery_risk = np.nanmean(actual[valid] < corrected_sched[valid] * 0.5) * 100

        # What if we're conservative and use 25th percentile instead?
        conservative_sched = scheduled * dr_p25
        conservative_risk = np.nanmean(actual[valid] < conservative_sched[valid] * 0.5) * 100

        # Worst-case glucose: when DR is at its lowest, what glucose level?
        low_dr_mask = valid & (actual / np.maximum(scheduled, 0.01) < dr_p10)
        if low_dr_mask.sum() > 0:
            worst_glucose = np.nanmean(glucose[low_dr_mask])
        else:
            worst_glucose = np.nanmean(glucose[~np.isnan(glucose)])

        # High DR periods: when loop delivers MORE than scheduled, what's happening?
        high_dr_mask = valid & (actual / np.maximum(scheduled, 0.01) > dr_p90)
        if high_dr_mask.sum() > 0:
            high_dr_glucose = np.nanmean(glucose[high_dr_mask])
        else:
            high_dr_glucose = np.nanmean(glucose[~np.isnan(glucose)])

        results[name] = {
            'dr_overall': round(dr_overall, 3),
            'dr_median': round(dr_median, 3),
            'dr_p10': round(dr_p10, 3),
            'dr_p25': round(dr_p25, 3),
            'dr_p75': round(dr_p75, 3),
            'dr_p90': round(dr_p90, 3),
            'dr_iqr': round(dr_p75 - dr_p25, 3),
            'under_delivery_risk_pct': round(under_delivery_risk, 1),
            'conservative_risk_pct': round(conservative_risk, 1),
            'worst_case_glucose': round(worst_glucose, 1),
            'high_dr_glucose': round(high_dr_glucose, 1),
            'safety_recommendation': 'conservative' if under_delivery_risk > 10 else 'standard',
        }

    return results


# ─────────────────────────────────────────────────────────────────
# EXP-2248: Graduated Transition Design
# ─────────────────────────────────────────────────────────────────

def exp_2248_graduated_transition(patients, all_results):
    """
    Design a graduated transition plan: instead of changing settings all at once,
    propose a stepwise schedule with monitoring milestones.
    """
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        glucose = df['glucose'].values
        n = len(glucose)

        basal_sched = df.attrs.get('basal_schedule', [])
        isf_sched = df.attrs.get('isf_schedule', [])

        if not basal_sched:
            results[name] = {'skip': True, 'reason': 'no schedule data'}
            continue

        profile_isf = isf_sched[0].get('value', 50) if isf_sched else 50
        if profile_isf < 15:
            profile_isf *= 18.0182

        hours = np.arange(n) * STEP_MIN / 60 % 24
        scheduled = build_scheduled_array(basal_sched, hours)
        actual = compute_actual_delivery(df, scheduled)

        valid = ~np.isnan(actual) & ~np.isnan(scheduled) & (scheduled > 0)
        if valid.sum() < STEPS_PER_DAY:
            results[name] = {'skip': True, 'reason': 'insufficient data'}
            continue

        dr = compute_delivery_ratio_sum(actual, scheduled, valid)

        # ISF ratio from corrections (vectorized)
        bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(n)
        carbs_arr = df['carbs'].values if 'carbs' in df.columns else np.zeros(n)
        corrections = find_corrections_vectorized(glucose, bolus, carbs_arr, n)

        if corrections:
            effective_isf = np.median([c[3] for c in corrections])
            isf_ratio = effective_isf / profile_isf if profile_isf > 0 else 1.0
        else:
            effective_isf = profile_isf
            isf_ratio = 1.0

        # Design graduated steps
        # Step 1: Basal reduction (25% toward target)
        # Step 2: Basal reduction (50% toward target)
        # Step 3: ISF adjustment (50% toward target)
        # Step 4: Full correction
        target_basal_factor = dr  # target = current * dr
        target_isf = effective_isf

        steps = []
        current_basal_factor = 1.0
        current_isf = profile_isf

        if abs(dr - 1.0) > 0.1:
            # Step 1: 25% basal correction
            step1_factor = 1.0 + (dr - 1.0) * 0.25
            steps.append({
                'step': 1,
                'action': f'Reduce basal to {step1_factor:.0%} of current',
                'basal_factor': round(step1_factor, 2),
                'isf': round(current_isf, 1),
                'monitoring': 'Check TIR/TBR after 3 days',
                'safety_gate': 'No increase in TBR >1%',
            })

            # Step 2: 50% basal correction
            step2_factor = 1.0 + (dr - 1.0) * 0.5
            steps.append({
                'step': 2,
                'action': f'Reduce basal to {step2_factor:.0%} of current',
                'basal_factor': round(step2_factor, 2),
                'isf': round(current_isf, 1),
                'monitoring': 'Check TIR/TBR after 3 days',
                'safety_gate': 'TBR <4% maintained',
            })

        if isf_ratio > 1.3:
            # Step 3: ISF correction (50% toward target)
            mid_isf = profile_isf + (effective_isf - profile_isf) * 0.5
            steps.append({
                'step': len(steps) + 1,
                'action': f'Raise ISF to {mid_isf:.0f} mg/dL/U',
                'basal_factor': round(1.0 + (dr - 1.0) * 0.5, 2),
                'isf': round(mid_isf, 1),
                'monitoring': 'Check correction outcomes after 5 days',
                'safety_gate': 'No correction bolus drops glucose below 70',
            })

            # Step 4: Full ISF correction
            steps.append({
                'step': len(steps) + 1,
                'action': f'Raise ISF to {effective_isf:.0f} mg/dL/U (full correction)',
                'basal_factor': round(dr, 2),
                'isf': round(effective_isf, 1),
                'monitoring': 'Full review after 7 days',
                'safety_gate': 'TIR ≥70% and TBR <4%',
            })

        if not steps:
            steps.append({
                'step': 1,
                'action': 'No changes needed — settings well-calibrated',
                'basal_factor': 1.0,
                'isf': round(profile_isf, 1),
                'monitoring': 'Routine monitoring',
                'safety_gate': 'N/A',
            })

        tir, tbr, _ = compute_tir_tbr_tar(glucose)

        results[name] = {
            'delivery_ratio': round(dr, 3),
            'isf_ratio': round(isf_ratio, 2),
            'profile_isf': round(profile_isf, 1),
            'effective_isf': round(effective_isf, 1),
            'n_steps': len(steps),
            'transition_steps': steps,
            'current_tir': round(tir, 1),
            'current_tbr': round(tbr, 1),
            'estimated_weeks': len(steps) * 1,  # ~1 week per step
        }

    return results


# ─────────────────────────────────────────────────────────────────
# Figure Generation
# ─────────────────────────────────────────────────────────────────

def generate_figures(all_results, fig_dir):
    os.makedirs(fig_dir, exist_ok=True)
    colors = plt.cm.tab10(np.linspace(0, 1, 11))

    # Fig 1: Basal Correction — Current vs Projected Delivery (EXP-2241)
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    r2241 = all_results['exp_2241']
    names = sorted([n for n in r2241 if not r2241[n].get('skip', False)])

    ax = axes[0]
    x = np.arange(len(names))
    current_full = [r2241[n]['current_full_delivery_pct'] for n in names]
    corrected_full = [r2241[n]['corrected_full_delivery_pct'] for n in names]
    ax.bar(x - 0.2, current_full, 0.35, label='Current', color='#e74c3c', alpha=0.8)
    ax.bar(x + 0.2, corrected_full, 0.35, label='Corrected', color='#2ecc71', alpha=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(names)
    ax.set_ylabel('Full Delivery Time (%)')
    ax.set_title('Loop Operating at 80–120% of Scheduled')
    ax.legend()
    ax.axhline(50, color='gray', linestyle='--', alpha=0.5)

    ax = axes[1]
    current_suspend = [r2241[n]['current_suspend_pct'] for n in names]
    corrected_suspend = [r2241[n]['corrected_suspend_pct'] for n in names]
    ax.bar(x - 0.2, current_suspend, 0.35, label='Current', color='#e74c3c', alpha=0.8)
    ax.bar(x + 0.2, corrected_suspend, 0.35, label='Corrected', color='#2ecc71', alpha=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(names)
    ax.set_ylabel('Suspension Time (%)')
    ax.set_title('Time in Full Suspension (<10% delivery)')
    ax.legend()

    plt.suptitle('EXP-2241: Basal Correction — Delivery Pattern Improvement', fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(f'{fig_dir}/sim-fig01-basal-correction.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  [fig] sim-fig01-basal-correction.png")

    # Fig 2: ISF Correction — Dose Reduction (EXP-2242)
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    r2242 = all_results['exp_2242']
    names2 = sorted([n for n in r2242 if not r2242[n].get('skip', False)])

    ax = axes[0]
    x = np.arange(len(names2))
    dose_red = [r2242[n]['mean_dose_reduction_pct'] for n in names2]
    colors2 = ['#e74c3c' if d > 50 else '#f39c12' if d > 25 else '#2ecc71' for d in dose_red]
    ax.bar(x, dose_red, color=colors2, alpha=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(names2)
    ax.set_ylabel('Correction Dose Reduction (%)')
    ax.set_title('With Corrected ISF')
    ax.axhline(50, color='gray', linestyle='--', alpha=0.5, label='50% reduction')
    ax.legend()

    ax = axes[1]
    current_h = [r2242[n]['current_correction_hypos'] for n in names2]
    projected_h = [r2242[n]['projected_correction_hypos'] for n in names2]
    ax.bar(x - 0.2, current_h, 0.35, label='Current', color='#e74c3c', alpha=0.8)
    ax.bar(x + 0.2, projected_h, 0.35, label='Projected', color='#2ecc71', alpha=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(names2)
    ax.set_ylabel('Post-Correction Hypos')
    ax.set_title('Correction Bolus Hypos: Current vs Projected')
    ax.legend()

    plt.suptitle('EXP-2242: ISF Correction — Dose & Hypo Reduction', fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(f'{fig_dir}/sim-fig02-isf-correction.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  [fig] sim-fig02-isf-correction.png")

    # Fig 3: Combined Impact (EXP-2243)
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    r2243 = all_results['exp_2243']
    names3 = sorted([n for n in r2243 if not r2243[n].get('skip', False)])

    ax = axes[0]
    x = np.arange(len(names3))
    current_tir = [r2243[n]['current_tir'] for n in names3]
    projected_tir = [r2243[n]['projected_tir'] for n in names3]
    ax.bar(x - 0.2, current_tir, 0.35, label='Current TIR', color='#3498db', alpha=0.8)
    ax.bar(x + 0.2, projected_tir, 0.35, label='Projected TIR', color='#2ecc71', alpha=0.8)
    ax.axhline(70, color='red', linestyle='--', alpha=0.7, label='70% target')
    ax.set_xticks(x)
    ax.set_xticklabels(names3)
    ax.set_ylabel('TIR (%)')
    ax.set_title('Time in Range: Current vs Projected')
    ax.legend()

    ax = axes[1]
    current_tbr = [r2243[n]['current_tbr'] for n in names3]
    projected_tbr = [r2243[n]['projected_tbr'] for n in names3]
    ax.bar(x - 0.2, current_tbr, 0.35, label='Current TBR', color='#e74c3c', alpha=0.8)
    ax.bar(x + 0.2, projected_tbr, 0.35, label='Projected TBR', color='#2ecc71', alpha=0.8)
    ax.axhline(4, color='red', linestyle='--', alpha=0.7, label='4% limit')
    ax.set_xticks(x)
    ax.set_xticklabels(names3)
    ax.set_ylabel('TBR (%)')
    ax.set_title('Time Below Range: Current vs Projected')
    ax.legend()

    plt.suptitle('EXP-2243: Combined Correction — TIR/TBR Projection', fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(f'{fig_dir}/sim-fig03-combined-projection.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  [fig] sim-fig03-combined-projection.png")

    # Fig 4: Oscillation Reduction (EXP-2244)
    fig, ax = plt.subplots(figsize=(12, 6))
    r2244 = all_results['exp_2244']
    names4 = sorted([n for n in r2244 if not r2244[n].get('skip', False)])

    x = np.arange(len(names4))
    total_cycles = [r2244[n]['cycles_per_day'] for n in names4]
    basal_cycles = [r2244[n]['basal_cycles_per_day'] for n in names4]
    remaining = [r2244[n]['projected_cycles_per_day'] for n in names4]

    ax.bar(x, total_cycles, color='#e74c3c', alpha=0.6, label='Total cycles/day')
    ax.bar(x, remaining, color='#2ecc71', alpha=0.8, label='Projected (after basal fix)')
    ax.set_xticks(x)
    ax.set_xticklabels(names4)
    ax.set_ylabel('Oscillation Cycles per Day')
    ax.set_title('EXP-2244: Suspend-Surge Oscillation Reduction')
    ax.legend()

    plt.tight_layout()
    plt.savefig(f'{fig_dir}/sim-fig04-oscillation-reduction.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  [fig] sim-fig04-oscillation-reduction.png")

    # Fig 5: Hypo Prevention (EXP-2245)
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    r2245 = all_results['exp_2245']
    names5 = sorted(r2245.keys())

    ax = axes[0]
    x = np.arange(len(names5))
    hypo_rates = [r2245[n]['hypos_per_day'] for n in names5]
    projected_rates = [r2245[n]['projected_hypos_per_day'] for n in names5]
    ax.bar(x - 0.2, hypo_rates, 0.35, label='Current', color='#e74c3c', alpha=0.8)
    ax.bar(x + 0.2, projected_rates, 0.35, label='Projected', color='#2ecc71', alpha=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(names5)
    ax.set_ylabel('Hypo Events per Day')
    ax.set_title('Current vs Projected Hypo Rate')
    ax.legend()

    ax = axes[1]
    prevention = [r2245[n]['prevention_rate'] for n in names5]
    colors5 = ['#2ecc71' if p > 50 else '#f39c12' if p > 25 else '#e74c3c' for p in prevention]
    ax.bar(x, prevention, color=colors5, alpha=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(names5)
    ax.set_ylabel('Prevention Rate (%)')
    ax.set_title('Fraction of Hypos Preventable')
    ax.axhline(50, color='gray', linestyle='--', alpha=0.5)

    plt.suptitle('EXP-2245: Hypo Prevention Projection', fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(f'{fig_dir}/sim-fig05-hypo-prevention.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  [fig] sim-fig05-hypo-prevention.png")

    # Fig 6: TIR Improvement (EXP-2246)
    fig, ax = plt.subplots(figsize=(12, 6))
    r2246 = all_results['exp_2246']
    names6 = sorted(r2246.keys())

    x = np.arange(len(names6))
    current = [r2246[n]['current_tir'] for n in names6]
    projected = [r2246[n]['projected_tir'] for n in names6]
    meets = [r2246[n]['meets_guidelines'] for n in names6]

    ax.bar(x - 0.2, current, 0.35, label='Current TIR', color='#3498db', alpha=0.8)
    bars = ax.bar(x + 0.2, projected, 0.35, label='Projected TIR', alpha=0.8,
                  color=['#2ecc71' if m else '#f39c12' for m in meets])
    ax.axhline(70, color='red', linestyle='--', alpha=0.7, label='70% target')
    ax.set_xticks(x)
    ax.set_xticklabels(names6)
    ax.set_ylabel('TIR (%)')
    ax.set_title('EXP-2246: Projected TIR After Settings Correction')
    ax.legend()

    plt.tight_layout()
    plt.savefig(f'{fig_dir}/sim-fig06-tir-projection.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  [fig] sim-fig06-tir-projection.png")

    # Fig 7: Safety Margins (EXP-2247)
    fig, ax = plt.subplots(figsize=(12, 6))
    r2247 = all_results['exp_2247']
    names7 = sorted([n for n in r2247 if not r2247[n].get('skip', False)])

    x = np.arange(len(names7))
    dr_overall = [r2247[n]['dr_overall'] for n in names7]
    dr_p10 = [r2247[n]['dr_p10'] for n in names7]
    dr_p90 = [r2247[n]['dr_p90'] for n in names7]

    ax.bar(x, dr_overall, color='#3498db', alpha=0.8, label='Sum-based DR')
    ax.errorbar(x, dr_overall, yerr=[np.array(dr_overall) - np.array(dr_p10),
                                   np.array(dr_p90) - np.array(dr_overall)],
                fmt='none', color='black', capsize=5, label='10th-90th percentile')
    ax.axhline(1.0, color='green', linestyle='--', alpha=0.7, label='Ideal (1.0)')
    ax.set_xticks(x)
    ax.set_xticklabels(names7)
    ax.set_ylabel('Delivery Ratio')
    ax.set_title('EXP-2247: Delivery Ratio Distribution & Safety Margins')
    ax.legend()

    plt.tight_layout()
    plt.savefig(f'{fig_dir}/sim-fig07-safety-margins.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  [fig] sim-fig07-safety-margins.png")

    # Fig 8: Graduated Transition (EXP-2248)
    fig, ax = plt.subplots(figsize=(14, 6))
    r2248 = all_results['exp_2248']
    names8 = sorted([n for n in r2248 if not r2248[n].get('skip', False)])

    y = len(names8)
    for i, n in enumerate(names8):
        data = r2248[n]
        n_steps = data['n_steps']
        weeks = data['estimated_weeks']
        dr = data['delivery_ratio']
        isf_r = data['isf_ratio']
        ax.barh(y - i, weeks, color=plt.cm.RdYlGn(min(1.0, dr)), alpha=0.8, height=0.6)
        label = f"  {n}: {n_steps} steps, ~{weeks}w | DR={dr:.2f} ISF×{isf_r:.1f} | TIR={data['current_tir']:.0f}% → target"
        ax.text(weeks + 0.1, y - i, label, va='center', fontsize=9)

    ax.set_ylabel('Patient')
    ax.set_xlabel('Transition Weeks')
    ax.set_title('EXP-2248: Graduated Settings Transition Plan')
    ax.set_yticks(range(1, y + 1))
    ax.set_yticklabels(list(reversed(names8)))

    plt.tight_layout()
    plt.savefig(f'{fig_dir}/sim-fig08-graduated-transition.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  [fig] sim-fig08-graduated-transition.png")


# ─────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--figures', action='store_true')
    args = parser.parse_args()

    print("Loading patients...")
    patients = load_patients()

    results = {}
    experiments = [
        ('exp_2241', 'EXP-2241', 'Basal Correction Replay', exp_2241_basal_correction_replay),
        ('exp_2242', 'EXP-2242', 'ISF Correction Replay', exp_2242_isf_correction_replay),
        ('exp_2243', 'EXP-2243', 'Combined Correction Replay', exp_2243_combined_correction),
        ('exp_2244', 'EXP-2244', 'Oscillation Reduction Projection', exp_2244_oscillation_reduction),
        ('exp_2245', 'EXP-2245', 'Hypo Prevention Projection', exp_2245_hypo_prevention),
        ('exp_2246', 'EXP-2246', 'TIR Improvement Projection', exp_2246_tir_projection),
        ('exp_2247', 'EXP-2247', 'Safety Margin Analysis', exp_2247_safety_margins),
    ]

    for key, exp_id, title, func in experiments:
        print(f"\n{'=' * 60}")
        print(f"  {exp_id}: {title}")
        print(f"{'=' * 60}")
        try:
            results[key] = func(patients)
            print(f"  ✓ {exp_id} PASSED")
            if isinstance(results[key], dict):
                for pname, pdata in sorted(results[key].items()):
                    if isinstance(pdata, dict) and not pdata.get('skip', False):
                        summary = []
                        for k, v in list(pdata.items())[:5]:
                            if isinstance(v, (int, float)) and not isinstance(v, bool):
                                summary.append(f"{k}={v}")
                        if summary:
                            print(f"    {pname}: {', '.join(summary[:3])}")
        except Exception as e:
            print(f"  ✗ {exp_id} FAILED: {e}")
            import traceback
            traceback.print_exc()
            results[key] = {'error': str(e)}

    # EXP-2248 depends on other results
    print(f"\n{'=' * 60}")
    print(f"  EXP-2248: Graduated Transition Design")
    print(f"{'=' * 60}")
    try:
        results['exp_2248'] = exp_2248_graduated_transition(patients, results)
        print(f"  ✓ EXP-2248 PASSED")
        for pname, pdata in sorted(results['exp_2248'].items()):
            if isinstance(pdata, dict) and not pdata.get('skip', False):
                print(f"    {pname}: steps={pdata['n_steps']}, weeks={pdata['estimated_weeks']}, DR={pdata['delivery_ratio']:.2f}")
    except Exception as e:
        print(f"  ✗ EXP-2248 FAILED: {e}")
        import traceback
        traceback.print_exc()
        results['exp_2248'] = {'error': str(e)}

    # Save results
    out_dir = 'externals/experiments'
    os.makedirs(out_dir, exist_ok=True)
    out_file = f'{out_dir}/exp-2241-2248_settings_sim.json'
    with open(out_file, 'w') as f:
        json.dump(results, f, indent=2, cls=NumpyEncoder)
    print(f"\nResults saved to {out_file}")

    if args.figures:
        fig_dir = 'docs/60-research/figures'
        print("\nGenerating figures...")
        generate_figures(results, fig_dir)
        print("All figures generated.")

    print("\n" + "=" * 60)
    print("  SUMMARY: EXP-2241–2248")
    print("=" * 60)
    passed = sum(1 for k in results if 'error' not in results.get(k, {}))
    print(f"  {passed}/8 experiments passed")

    return results


if __name__ == '__main__':
    main()
