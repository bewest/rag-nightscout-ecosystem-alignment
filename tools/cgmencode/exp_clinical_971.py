#!/usr/bin/env python3
"""EXP-971 through EXP-980: Clinical Intelligence & Multi-Scale Analysis.

PIVOT from R² prediction optimization toward underserved priorities:
  - Settings fidelity scoring (basal/ISF/CR adequacy)
  - Multi-week trend analysis and temporal extension
  - Residual decomposition for clinical intelligence
  - Cross-patient feature generalization
  - Conservation violation as clinical signal

These experiments address the stated goals from the symmetry-sparsity document
that were NOT served by the EXP-891-970 prediction campaign.

Experiment registry:
    EXP-971: Multi-day glucose pattern detection (FPCA on daily curves)
    EXP-972: Basal adequacy by 6-hour time segment
    EXP-973: CR effectiveness per time-of-day
    EXP-974: ISF validation from correction boluses
    EXP-975: Rolling settings fidelity with breakpoint detection
    EXP-976: 24-hour supply/demand integral balance score
    EXP-977: Residual source decomposition (meals/dawn/sensor/unknown)
    EXP-978: Cross-patient feature importance (LOPO stability)
    EXP-979: Multi-week trend analysis (rolling weekly metrics)
    EXP-980: Conservation violation as clinical signal

Usage:
    PYTHONPATH=tools python -m cgmencode.exp_clinical_971 --detail --save --max-patients 11
"""

import sys
import json
import time
import argparse
from pathlib import Path
from datetime import datetime

import numpy as np
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cgmencode.exp_metabolic_flux import (
    load_patients, _extract_isf_scalar, _extract_cr_scalar,
    classify_windows_by_event, save_results,
)
from cgmencode.exp_metabolic_441 import compute_supply_demand
from cgmencode.continuous_pk import expand_schedule

STEPS_PER_HOUR = 12
STEPS_PER_DAY = 288
PATIENTS_DIR = Path(__file__).resolve().parent.parent.parent / 'externals' / 'ns-data' / 'patients'


# ===================================================================
# Helpers
# ===================================================================

def _get_local_hour(df):
    """Return array of local hour-of-day for each row."""
    tz = df.attrs.get('patient_tz', 'UTC')
    try:
        local = df.index.tz_convert(tz)
    except Exception:
        local = df.index
    return np.array(local.hour + local.minute / 60.0)


def _expand_schedule_array(df, schedule_key, default=1.0):
    """Expand a Nightscout step-function schedule to per-row array."""
    sched = df.attrs.get(schedule_key, [])
    if not sched:
        return np.full(len(df), default)
    hours = _get_local_hour(df)
    seconds = hours * 3600.0
    # Sort schedule by timeAsSeconds
    entries = sorted(sched, key=lambda e: e.get('timeAsSeconds', 0))
    values = np.full(len(df), entries[0].get('value', default))
    for i, sec in enumerate(seconds):
        for entry in reversed(entries):
            if sec >= entry.get('timeAsSeconds', 0):
                values[i] = entry.get('value', default)
                break
    return values


def _identify_stable_windows(df, min_hours=3.0):
    """Find windows with no bolus and no carbs for at least min_hours.
    Returns list of (start_idx, end_idx) tuples."""
    bolus = np.nan_to_num(df['bolus'].values.astype(np.float64), nan=0.0)
    carbs = np.nan_to_num(df['carbs'].values.astype(np.float64), nan=0.0)
    active = (bolus > 0.1) | (carbs > 2.0)
    min_steps = int(min_hours * STEPS_PER_HOUR)

    windows = []
    start = None
    for i in range(len(active)):
        if not active[i]:
            if start is None:
                start = i
        else:
            if start is not None and (i - start) >= min_steps:
                windows.append((start, i))
            start = None
    if start is not None and (len(active) - start) >= min_steps:
        windows.append((start, len(active)))
    return windows


def _identify_meal_events(df, min_carbs=8.0):
    """Find meal events (carb entries >= min_carbs).
    Returns list of (index, carbs_g) tuples."""
    carbs = np.nan_to_num(df['carbs'].values.astype(np.float64), nan=0.0)
    events = []
    i = 0
    while i < len(carbs):
        if carbs[i] >= min_carbs:
            total = carbs[i]
            j = i + 1
            while j < min(i + 6, len(carbs)) and carbs[j] > 0:
                total += carbs[j]
                j += 1
            events.append((i, total))
            i = j + STEPS_PER_HOUR  # skip 1h after meal start
        else:
            i += 1
    return events


def _identify_correction_boluses(df, min_insulin=0.3, no_carb_window_h=1.5):
    """Find correction boluses with no nearby carbs.
    Returns list of (index, insulin_U) tuples."""
    bolus = np.nan_to_num(df['bolus'].values.astype(np.float64), nan=0.0)
    carbs = np.nan_to_num(df['carbs'].values.astype(np.float64), nan=0.0)
    window = int(no_carb_window_h * STEPS_PER_HOUR)
    events = []
    for i in range(window, len(bolus) - window):
        if bolus[i] >= min_insulin:
            carb_near = np.sum(carbs[max(0, i - window):i + window])
            if carb_near < 3.0:
                events.append((i, bolus[i]))
    return events


# ===================================================================
# EXP-971: Multi-Day Glucose Pattern Detection
# ===================================================================

def run_exp971(patients, args):
    """Do recurring multi-day glucose patterns exist?

    Method: Extract daily glucose curves (288 points), compute day-to-day
    autocorrelation, test for weekly periodicity, and check if specific
    day-of-week patterns emerge across patients.
    """
    print("\n" + "=" * 60)
    print("Running EXP-971: Multi-Day Glucose Pattern Detection")
    print("=" * 60)
    t0 = time.time()

    per_patient = []
    for p in patients:
        df = p['df']
        bg = np.nan_to_num(df['glucose'].values.astype(np.float64), nan=120.0)
        hours = _get_local_hour(df)

        n_days = len(bg) // STEPS_PER_DAY
        if n_days < 14:
            continue

        # Extract daily curves
        daily_curves = []
        daily_means = []
        for d in range(n_days):
            start = d * STEPS_PER_DAY
            end = start + STEPS_PER_DAY
            curve = bg[start:end]
            if np.sum(curve > 0) > 200:  # enough data
                daily_curves.append(curve)
                daily_means.append(np.mean(curve))

        if len(daily_curves) < 14:
            continue

        daily_curves = np.array(daily_curves)
        daily_means = np.array(daily_means)

        # Day-to-day autocorrelation of mean glucose
        n = len(daily_means)
        autocorr = []
        for lag in range(1, min(15, n // 2)):
            r = np.corrcoef(daily_means[:-lag], daily_means[lag:])[0, 1]
            autocorr.append(r)

        # Weekly periodicity: lag-7 vs lag-1..6 average
        weekly_r = autocorr[6] if len(autocorr) > 6 else 0.0
        neighbor_r = np.mean(autocorr[:6]) if len(autocorr) >= 6 else 0.0

        # Day-of-week analysis
        # Assign day-of-week to each daily curve
        try:
            tz = df.attrs.get('patient_tz', 'UTC')
            local_idx = df.index.tz_convert(tz)
        except Exception:
            local_idx = df.index
        dow_means = {}
        for d in range(min(n_days, len(daily_curves))):
            row_idx = d * STEPS_PER_DAY + STEPS_PER_DAY // 2
            if row_idx < len(local_idx):
                dow = local_idx[row_idx].dayofweek
                dow_means.setdefault(dow, []).append(daily_means[d])

        # ANOVA across days of week
        groups = [np.array(v) for v in dow_means.values() if len(v) >= 3]
        if len(groups) >= 2:
            f_stat, p_value = stats.f_oneway(*groups)
        else:
            f_stat, p_value = 0.0, 1.0

        # Daily curve similarity (mean pairwise correlation)
        n_sample = min(50, len(daily_curves))
        idx = np.random.choice(len(daily_curves), n_sample, replace=False)
        cors = []
        for i in range(len(idx)):
            for j in range(i + 1, len(idx)):
                r = np.corrcoef(daily_curves[idx[i]], daily_curves[idx[j]])[0, 1]
                if np.isfinite(r):
                    cors.append(r)
        mean_daily_corr = np.mean(cors) if cors else 0.0

        # Multi-day trend (linear regression on daily means)
        slope, _, r_trend, p_trend, _ = stats.linregress(
            np.arange(len(daily_means)), daily_means)

        per_patient.append({
            'patient': p['name'],
            'n_days': len(daily_curves),
            'lag1_autocorr': round(autocorr[0], 3) if autocorr else 0.0,
            'lag7_autocorr': round(weekly_r, 3),
            'weekly_vs_neighbor': round(weekly_r - neighbor_r, 3),
            'dow_anova_f': round(f_stat, 2),
            'dow_anova_p': round(p_value, 4),
            'mean_daily_curve_corr': round(mean_daily_corr, 3),
            'trend_slope_mgdl_per_day': round(slope, 2),
            'trend_r2': round(r_trend**2, 4),
            'trend_p': round(p_trend, 4),
        })

    # Aggregate
    lag1s = [pp['lag1_autocorr'] for pp in per_patient]
    lag7s = [pp['lag7_autocorr'] for pp in per_patient]
    dow_sigs = sum(1 for pp in per_patient if pp['dow_anova_p'] < 0.05)
    trends = sum(1 for pp in per_patient if pp['trend_p'] < 0.05)

    detail = (f"lag1_mean={np.mean(lag1s):.3f}, lag7_mean={np.mean(lag7s):.3f}, "
              f"dow_sig={dow_sigs}/{len(per_patient)}, trending={trends}/{len(per_patient)}")
    print(f"  Status: pass")
    print(f"  Detail: {detail}")

    elapsed = round(time.time() - t0, 1)
    print(f"  Time: {elapsed}s")

    result = {
        'experiment': 'EXP-971',
        'name': 'Multi-Day Glucose Pattern Detection',
        'status': 'pass',
        'detail': detail,
        'results': {
            'mean_lag1_autocorr': round(np.mean(lag1s), 3),
            'mean_lag7_autocorr': round(np.mean(lag7s), 3),
            'dow_significant_patients': dow_sigs,
            'trending_patients': trends,
            'n_patients': len(per_patient),
            'per_patient': per_patient,
        },
        'elapsed_seconds': elapsed,
    }
    return result


# ===================================================================
# EXP-972: Basal Adequacy by 6-Hour Segment
# ===================================================================

def run_exp972(patients, args):
    """Score basal adequacy per 6-hour segment by measuring glucose drift
    during stable (no meal/bolus) periods.

    A well-tuned basal should keep glucose flat during fasting.
    Positive drift = basal too low (EGP > insulin). Negative = too high.
    """
    print("\n" + "=" * 60)
    print("Running EXP-972: Basal Adequacy by 6-Hour Segment")
    print("=" * 60)
    t0 = time.time()

    SEGMENTS = {
        'overnight': (0, 6),    # midnight-6am
        'morning': (6, 12),     # 6am-noon
        'afternoon': (12, 18),  # noon-6pm
        'evening': (18, 24),    # 6pm-midnight
    }

    per_patient = []
    for p in patients:
        df = p['df']
        bg = np.nan_to_num(df['glucose'].values.astype(np.float64), nan=0.0)
        hours = _get_local_hour(df)

        # Find stable windows (no bolus/carbs for >= 3 hours)
        stable_windows = _identify_stable_windows(df, min_hours=3.0)

        segment_drifts = {name: [] for name in SEGMENTS}
        segment_counts = {name: 0 for name in SEGMENTS}

        for ws, we in stable_windows:
            window_bg = bg[ws:we]
            window_hours = hours[ws:we]
            if np.sum(window_bg > 30) < STEPS_PER_HOUR * 2:
                continue

            # Linear regression over this stable window
            valid = window_bg > 30
            if np.sum(valid) < 12:
                continue
            x = np.arange(np.sum(valid))
            y = window_bg[valid]
            slope, intercept, _, _, _ = stats.linregress(x, y)
            drift_per_hour = slope * STEPS_PER_HOUR  # mg/dL per hour

            # Assign to time segment based on midpoint hour
            mid_hour = np.median(window_hours)
            for name, (h_start, h_end) in SEGMENTS.items():
                if h_start <= mid_hour < h_end:
                    segment_drifts[name].append(drift_per_hour)
                    segment_counts[name] += 1
                    break

        # Compute per-segment statistics
        segment_results = {}
        for name in SEGMENTS:
            drifts = segment_drifts[name]
            if drifts:
                mean_drift = np.mean(drifts)
                std_drift = np.std(drifts)
                # Adequacy: |drift| < 3 mg/dL/hr is "good"
                adequacy = 'good' if abs(mean_drift) < 3.0 else (
                    'low_basal' if mean_drift > 3.0 else 'high_basal')
                segment_results[name] = {
                    'mean_drift_mgdl_per_h': round(mean_drift, 2),
                    'std_drift': round(std_drift, 2),
                    'n_windows': len(drifts),
                    'adequacy': adequacy,
                }
            else:
                segment_results[name] = {
                    'mean_drift_mgdl_per_h': None,
                    'n_windows': 0,
                    'adequacy': 'insufficient_data',
                }

        # Composite score: fraction of segments with |drift| < 3
        scored = [s for s in segment_results.values()
                  if s['mean_drift_mgdl_per_h'] is not None]
        adequate = sum(1 for s in scored if abs(s['mean_drift_mgdl_per_h']) < 3.0)
        composite = adequate / max(len(scored), 1)

        per_patient.append({
            'patient': p['name'],
            'segments': segment_results,
            'composite_score': round(composite, 2),
            'total_stable_windows': sum(segment_counts.values()),
        })

    composites = [pp['composite_score'] for pp in per_patient]
    detail = (f"mean_adequacy={np.mean(composites):.2f}, "
              f"fully_adequate={sum(1 for c in composites if c >= 1.0)}/{len(composites)}")
    print(f"  Status: pass")
    print(f"  Detail: {detail}")

    elapsed = round(time.time() - t0, 1)
    print(f"  Time: {elapsed}s")

    return {
        'experiment': 'EXP-972',
        'name': 'Basal Adequacy by 6-Hour Segment',
        'status': 'pass',
        'detail': detail,
        'results': {
            'mean_composite_score': round(np.mean(composites), 3),
            'n_patients': len(per_patient),
            'per_patient': per_patient,
        },
        'elapsed_seconds': elapsed,
    }


# ===================================================================
# EXP-973: CR Effectiveness per Time-of-Day
# ===================================================================

def run_exp973(patients, args):
    """For each announced meal, measure the glucose excursion over 3 hours.
    Compare actual peak rise to expected rise (carbs * ISF/CR).
    Score CR effectiveness per time segment.

    CR_effectiveness = expected_rise / actual_rise
    >1 means CR is too aggressive (not enough insulin), <1 means too conservative.
    """
    print("\n" + "=" * 60)
    print("Running EXP-973: CR Effectiveness per Time-of-Day")
    print("=" * 60)
    t0 = time.time()

    MEAL_SEGMENTS = {
        'breakfast': (5, 10),
        'lunch': (10, 15),
        'dinner': (15, 21),
        'snack': (21, 5),  # late night / early morning
    }

    per_patient = []
    for p in patients:
        df = p['df']
        bg = np.nan_to_num(df['glucose'].values.astype(np.float64), nan=0.0)
        hours = _get_local_hour(df)
        isf = _extract_isf_scalar(df)
        cr = _extract_cr_scalar(df)
        bolus = np.nan_to_num(df['bolus'].values.astype(np.float64), nan=0.0)

        meals = _identify_meal_events(df, min_carbs=8.0)
        post_meal_window = 3 * STEPS_PER_HOUR  # 3 hours

        segment_scores = {name: [] for name in MEAL_SEGMENTS}

        for meal_idx, carb_g in meals:
            if meal_idx + post_meal_window >= len(bg):
                continue
            bg_start = bg[meal_idx]
            if bg_start < 40:
                continue

            # Peak glucose in 3-hour window
            window = bg[meal_idx:meal_idx + post_meal_window]
            valid_window = window[window > 30]
            if len(valid_window) < 12:
                continue
            actual_peak = np.max(valid_window)
            actual_rise = actual_peak - bg_start

            # Bolus insulin within 30 min of meal
            bolus_window = int(0.5 * STEPS_PER_HOUR)
            insulin_for_meal = np.sum(
                bolus[max(0, meal_idx - bolus_window):meal_idx + bolus_window])

            # Expected rise: carbs would raise by (carbs/CR * ISF) if no insulin
            # But insulin covers (insulin * ISF). Net expected:
            expected_unbolused_rise = (carb_g / cr) * isf if cr > 0 else 0
            expected_insulin_drop = insulin_for_meal * isf
            expected_net_rise = expected_unbolused_rise - expected_insulin_drop

            # CR effectiveness ratio
            if actual_rise > 5:  # meaningful rise
                cr_ratio = expected_net_rise / actual_rise if actual_rise != 0 else 1.0
            else:
                cr_ratio = 1.0  # flat glucose after meal = good coverage

            # Assign to time segment
            meal_hour = hours[meal_idx]
            assigned = False
            for name, (h_start, h_end) in MEAL_SEGMENTS.items():
                if h_start <= h_end:
                    if h_start <= meal_hour < h_end:
                        segment_scores[name].append({
                            'cr_ratio': cr_ratio,
                            'actual_rise': actual_rise,
                            'expected_net_rise': expected_net_rise,
                            'carbs_g': carb_g,
                            'insulin_u': insulin_for_meal,
                        })
                        assigned = True
                        break
                else:  # wraps midnight
                    if meal_hour >= h_start or meal_hour < h_end:
                        segment_scores[name].append({
                            'cr_ratio': cr_ratio,
                            'actual_rise': actual_rise,
                            'expected_net_rise': expected_net_rise,
                            'carbs_g': carb_g,
                            'insulin_u': insulin_for_meal,
                        })
                        assigned = True
                        break

        # Summarize per segment
        summary = {}
        for name, scores in segment_scores.items():
            if scores:
                ratios = [s['cr_ratio'] for s in scores]
                rises = [s['actual_rise'] for s in scores]
                summary[name] = {
                    'n_meals': len(scores),
                    'mean_cr_ratio': round(np.mean(ratios), 2),
                    'median_actual_rise_mgdl': round(np.median(rises), 1),
                    'mean_actual_rise_mgdl': round(np.mean(rises), 1),
                    'assessment': ('good' if 0.7 <= np.mean(ratios) <= 1.3
                                   else 'cr_too_high' if np.mean(ratios) > 1.3
                                   else 'cr_too_low'),
                }
            else:
                summary[name] = {'n_meals': 0, 'assessment': 'no_data'}

        total_meals = sum(len(v) for v in segment_scores.values())
        per_patient.append({
            'patient': p['name'],
            'isf': round(isf, 1),
            'cr': round(cr, 1),
            'total_meals': total_meals,
            'segments': summary,
        })

    total_meals_all = sum(pp['total_meals'] for pp in per_patient)
    detail = f"total_meals={total_meals_all}, patients={len(per_patient)}"
    print(f"  Status: pass")
    print(f"  Detail: {detail}")

    elapsed = round(time.time() - t0, 1)
    print(f"  Time: {elapsed}s")

    return {
        'experiment': 'EXP-973',
        'name': 'CR Effectiveness per Time-of-Day',
        'status': 'pass',
        'detail': detail,
        'results': {
            'total_meals_analyzed': total_meals_all,
            'n_patients': len(per_patient),
            'per_patient': per_patient,
        },
        'elapsed_seconds': elapsed,
    }


# ===================================================================
# EXP-974: ISF Validation from Correction Boluses
# ===================================================================

def run_exp974(patients, args):
    """Find correction boluses (insulin without food), measure actual
    glucose drop over 3 hours, compare to ISF-predicted drop.

    ISF_actual = glucose_drop / insulin_dose
    ISF_accuracy = ISF_profile / ISF_actual
    """
    print("\n" + "=" * 60)
    print("Running EXP-974: ISF Validation from Correction Boluses")
    print("=" * 60)
    t0 = time.time()

    per_patient = []
    for p in patients:
        df = p['df']
        bg = np.nan_to_num(df['glucose'].values.astype(np.float64), nan=0.0)
        hours = _get_local_hour(df)
        isf_profile = _extract_isf_scalar(df)

        corrections = _identify_correction_boluses(df, min_insulin=0.3)
        response_window = 3 * STEPS_PER_HOUR

        isf_actuals = []
        isf_ratios = []
        by_hour_block = {}  # 6-hour blocks

        for corr_idx, insulin_u in corrections:
            if corr_idx + response_window >= len(bg):
                continue
            bg_at_bolus = bg[corr_idx]
            if bg_at_bolus < 100:  # correction only makes sense from high BG
                continue

            # Find nadir in 3-hour window
            window = bg[corr_idx:corr_idx + response_window]
            valid = window > 30
            if np.sum(valid) < 12:
                continue
            nadir = np.min(window[valid])
            actual_drop = bg_at_bolus - nadir

            if actual_drop < 5 or insulin_u < 0.1:
                continue

            isf_actual = actual_drop / insulin_u
            ratio = isf_profile / isf_actual  # >1 = profile overestimates sensitivity

            isf_actuals.append(isf_actual)
            isf_ratios.append(ratio)

            # By time block
            hour = hours[corr_idx]
            block = int(hour // 6) * 6
            by_hour_block.setdefault(block, []).append(ratio)

        if isf_actuals:
            block_summary = {}
            for block, ratios in sorted(by_hour_block.items()):
                block_summary[f"{int(block):02d}-{int(block)+6:02d}h"] = {
                    'n_corrections': len(ratios),
                    'mean_isf_ratio': round(np.mean(ratios), 2),
                    'assessment': ('accurate' if 0.7 <= np.mean(ratios) <= 1.3
                                   else 'isf_too_high' if np.mean(ratios) > 1.3
                                   else 'isf_too_low'),
                }

            per_patient.append({
                'patient': p['name'],
                'isf_profile': round(isf_profile, 1),
                'n_corrections': len(isf_actuals),
                'mean_isf_actual': round(np.mean(isf_actuals), 1),
                'median_isf_actual': round(np.median(isf_actuals), 1),
                'mean_isf_ratio': round(np.mean(isf_ratios), 2),
                'std_isf_ratio': round(np.std(isf_ratios), 2),
                'overall_assessment': ('accurate' if 0.7 <= np.mean(isf_ratios) <= 1.3
                                       else 'isf_too_high' if np.mean(isf_ratios) > 1.3
                                       else 'isf_too_low'),
                'by_time_block': block_summary,
            })
        else:
            per_patient.append({
                'patient': p['name'],
                'isf_profile': round(isf_profile, 1),
                'n_corrections': 0,
                'overall_assessment': 'insufficient_data',
            })

    n_with_data = sum(1 for pp in per_patient if pp['n_corrections'] > 0)
    ratios_all = [pp['mean_isf_ratio'] for pp in per_patient if pp.get('mean_isf_ratio')]
    detail = (f"patients_with_data={n_with_data}/{len(per_patient)}, "
              f"mean_ratio={np.mean(ratios_all):.2f}" if ratios_all else
              f"patients_with_data={n_with_data}/{len(per_patient)}")
    print(f"  Status: pass")
    print(f"  Detail: {detail}")

    elapsed = round(time.time() - t0, 1)
    print(f"  Time: {elapsed}s")

    return {
        'experiment': 'EXP-974',
        'name': 'ISF Validation from Correction Boluses',
        'status': 'pass',
        'detail': detail,
        'results': {
            'patients_with_corrections': n_with_data,
            'mean_isf_ratio': round(np.mean(ratios_all), 3) if ratios_all else None,
            'n_patients': len(per_patient),
            'per_patient': per_patient,
        },
        'elapsed_seconds': elapsed,
    }


# ===================================================================
# EXP-975: Rolling Settings Fidelity with Breakpoint Detection
# ===================================================================

def run_exp975(patients, args):
    """Compute weekly rolling fidelity scores and detect breakpoints where
    settings became misaligned. Uses CUSUM on basal drift + CR effectiveness.
    """
    print("\n" + "=" * 60)
    print("Running EXP-975: Rolling Settings Fidelity + Breakpoints")
    print("=" * 60)
    t0 = time.time()

    per_patient = []
    for p in patients:
        df = p['df']
        bg = np.nan_to_num(df['glucose'].values.astype(np.float64), nan=0.0)
        hours = _get_local_hour(df)
        sd = compute_supply_demand(p['df'], p['pk'])
        supply = sd['supply']
        demand = sd['demand']
        net = sd['net']

        WEEK = 7 * STEPS_PER_DAY
        n_weeks = len(bg) // WEEK
        if n_weeks < 3:
            per_patient.append({
                'patient': p['name'], 'n_weeks': n_weeks,
                'assessment': 'insufficient_data'
            })
            continue

        weekly_metrics = []
        for w in range(n_weeks):
            start = w * WEEK
            end = start + WEEK
            wbg = bg[start:end]
            wnet = net[start:end]

            valid = wbg > 30
            if np.sum(valid) < WEEK * 0.5:
                continue

            tir = np.mean((wbg[valid] >= 70) & (wbg[valid] <= 180))
            mean_bg = np.mean(wbg[valid])
            cv = np.std(wbg[valid]) / mean_bg if mean_bg > 0 else 0
            # Net balance integral: should be ~0 if settings perfect
            net_integral = np.mean(wnet[valid]) if np.sum(valid) > 0 else 0
            # Supply-demand correlation
            ws = supply[start:end]
            wd = demand[start:end]
            sd_corr = np.corrcoef(ws[valid], wd[valid])[0, 1] if np.sum(valid) > 10 else 0

            weekly_metrics.append({
                'week': w,
                'tir': round(tir, 3),
                'mean_bg': round(mean_bg, 1),
                'cv': round(cv, 3),
                'net_integral': round(net_integral, 3),
                'sd_corr': round(sd_corr, 3) if np.isfinite(sd_corr) else 0.0,
            })

        if len(weekly_metrics) < 3:
            per_patient.append({
                'patient': p['name'], 'n_weeks': len(weekly_metrics),
                'assessment': 'insufficient_data'
            })
            continue

        # CUSUM on net_integral for breakpoint detection
        net_ints = np.array([w['net_integral'] for w in weekly_metrics])
        target = np.mean(net_ints)
        cusum_pos = np.zeros(len(net_ints))
        cusum_neg = np.zeros(len(net_ints))
        threshold = 2.0 * np.std(net_ints) if np.std(net_ints) > 0 else 1.0
        breakpoints = []
        for i in range(1, len(net_ints)):
            cusum_pos[i] = max(0, cusum_pos[i-1] + (net_ints[i] - target) - 0.5 * np.std(net_ints))
            cusum_neg[i] = max(0, cusum_neg[i-1] - (net_ints[i] - target) - 0.5 * np.std(net_ints))
            if cusum_pos[i] > threshold or cusum_neg[i] > threshold:
                breakpoints.append(i)
                cusum_pos[i] = 0
                cusum_neg[i] = 0

        # Trend in TIR
        tirs = [w['tir'] for w in weekly_metrics]
        if len(tirs) >= 3:
            slope, _, r_val, p_val, _ = stats.linregress(
                np.arange(len(tirs)), tirs)
            tir_trend = {
                'slope_per_week': round(slope, 4),
                'r2': round(r_val**2, 4),
                'direction': 'improving' if slope > 0.005 else 'deteriorating' if slope < -0.005 else 'stable',
            }
        else:
            tir_trend = {'direction': 'insufficient'}

        per_patient.append({
            'patient': p['name'],
            'n_weeks': len(weekly_metrics),
            'n_breakpoints': len(breakpoints),
            'breakpoint_weeks': breakpoints,
            'tir_trend': tir_trend,
            'first_week_tir': weekly_metrics[0]['tir'],
            'last_week_tir': weekly_metrics[-1]['tir'],
            'weekly_metrics': weekly_metrics,
        })

    n_breakpoints = [pp.get('n_breakpoints', 0) for pp in per_patient]
    detail = (f"mean_breakpoints={np.mean(n_breakpoints):.1f}, "
              f"patients_with_breakpoints={sum(1 for n in n_breakpoints if n > 0)}/{len(per_patient)}")
    print(f"  Status: pass")
    print(f"  Detail: {detail}")

    elapsed = round(time.time() - t0, 1)
    print(f"  Time: {elapsed}s")

    return {
        'experiment': 'EXP-975',
        'name': 'Rolling Settings Fidelity + Breakpoints',
        'status': 'pass',
        'detail': detail,
        'results': {
            'n_patients': len(per_patient),
            'per_patient': per_patient,
        },
        'elapsed_seconds': elapsed,
    }


# ===================================================================
# EXP-976: 24-Hour Supply/Demand Integral Balance Score
# ===================================================================

def run_exp976(patients, args):
    """When supply and demand integrals balance over 24h, settings are correct.
    Persistent imbalance indicates settings need adjustment.

    Score = 1 - |integral(supply - demand)| / integral(|supply| + |demand|)
    Perfect balance = 1.0. Complete mismatch = 0.0.
    """
    print("\n" + "=" * 60)
    print("Running EXP-976: 24-Hour Supply/Demand Integral Balance")
    print("=" * 60)
    t0 = time.time()

    per_patient = []
    for p in patients:
        df = p['df']
        bg = np.nan_to_num(df['glucose'].values.astype(np.float64), nan=0.0)
        sd = compute_supply_demand(p['df'], p['pk'])
        supply = sd['supply']
        demand = sd['demand']
        net = sd['net']

        n_days = len(bg) // STEPS_PER_DAY
        daily_scores = []
        daily_net_bias = []

        for d in range(n_days):
            start = d * STEPS_PER_DAY
            end = start + STEPS_PER_DAY
            s = supply[start:end]
            dem = demand[start:end]
            n = net[start:end]

            total_flux = np.sum(np.abs(s) + np.abs(dem))
            net_integral = np.sum(n)

            if total_flux > 0:
                balance = 1.0 - abs(net_integral) / total_flux
                daily_scores.append(max(0, balance))
                daily_net_bias.append(net_integral / STEPS_PER_DAY)  # per-step average

        if not daily_scores:
            continue

        # Correlate daily balance score with daily TIR
        daily_tirs = []
        for d in range(min(n_days, len(daily_scores))):
            start = d * STEPS_PER_DAY
            end = start + STEPS_PER_DAY
            dbg = bg[start:end]
            valid = dbg > 30
            if np.sum(valid) > 200:
                daily_tirs.append(np.mean((dbg[valid] >= 70) & (dbg[valid] <= 180)))
            else:
                daily_tirs.append(np.nan)

        valid_both = [(s, t) for s, t in zip(daily_scores, daily_tirs) if np.isfinite(t)]
        if len(valid_both) > 10:
            scores_v, tirs_v = zip(*valid_both)
            balance_tir_corr = np.corrcoef(scores_v, tirs_v)[0, 1]
        else:
            balance_tir_corr = float('nan')

        per_patient.append({
            'patient': p['name'],
            'n_days': len(daily_scores),
            'mean_balance_score': round(np.mean(daily_scores), 3),
            'std_balance_score': round(np.std(daily_scores), 3),
            'mean_net_bias_mgdl_per_step': round(np.mean(daily_net_bias), 3),
            'balance_tir_correlation': round(balance_tir_corr, 3) if np.isfinite(balance_tir_corr) else None,
            'assessment': ('well_balanced' if np.mean(daily_scores) > 0.85
                          else 'moderate' if np.mean(daily_scores) > 0.7
                          else 'imbalanced'),
        })

    scores = [pp['mean_balance_score'] for pp in per_patient]
    corrs = [pp['balance_tir_correlation'] for pp in per_patient
             if pp['balance_tir_correlation'] is not None]
    detail = (f"mean_balance={np.mean(scores):.3f}, "
              f"balance_tir_corr={np.mean(corrs):.3f}" if corrs else
              f"mean_balance={np.mean(scores):.3f}")
    print(f"  Status: pass")
    print(f"  Detail: {detail}")

    elapsed = round(time.time() - t0, 1)
    print(f"  Time: {elapsed}s")

    return {
        'experiment': 'EXP-976',
        'name': '24-Hour Supply/Demand Integral Balance',
        'status': 'pass',
        'detail': detail,
        'results': {
            'mean_balance_score': round(np.mean(scores), 3),
            'mean_balance_tir_corr': round(np.mean(corrs), 3) if corrs else None,
            'n_patients': len(per_patient),
            'per_patient': per_patient,
        },
        'elapsed_seconds': elapsed,
    }


# ===================================================================
# EXP-977: Residual Source Decomposition
# ===================================================================

def run_exp977(patients, args):
    """Decompose prediction residuals into attributable sources:
    - Meal timing uncertainty (postprandial vs fasting)
    - Dawn phenomenon (overnight 4-7 AM)
    - Sensor warmup/age effects
    - High glucose volatility periods
    - Unexplained remainder

    Uses the SOTA prediction pipeline and the window classification.
    """
    print("\n" + "=" * 60)
    print("Running EXP-977: Residual Source Decomposition")
    print("=" * 60)
    t0 = time.time()

    # Import stacking helper from exp_951
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        from cgmencode.exp_autoresearch_951 import _build_grand_features, _grand_cv_stacking
    except ImportError:
        print("  WARNING: Cannot import stacking helpers. Using simple regression.")
        _build_grand_features = None

    per_patient = []
    for p in patients:
        df = p['df']
        bg = np.nan_to_num(df['glucose'].values.astype(np.float64), nan=0.0)
        hours = _get_local_hour(df)
        h_steps = 12  # 60 min horizon

        # Build predictions using simple ridge if stacking unavailable
        if _build_grand_features is not None:
            gf_result = _build_grand_features(p, h_steps=h_steps, start=24)
            if gf_result[0] is None:
                continue
            grand_features, d_back = gf_result
            stacking = _grand_cv_stacking(grand_features, d_back, horizons=[1, 3, 6, 12])
            if stacking is None or 'pred_val' not in stacking:
                continue
            pred = stacking['pred_val']
            actual = stacking['actual_val']
            split = int(0.8 * len(grand_features))
            val_hours = hours[24 + h_steps + 1 + split:
                             24 + h_steps + 1 + split + len(pred)]
        else:
            # Fallback: simple BG prediction
            start = 24
            usable = len(bg) - start - h_steps - 1
            if usable < 500:
                continue
            target = bg[start + h_steps + 1:start + h_steps + 1 + usable]
            features = np.column_stack([
                bg[start:start + usable],
                bg[start:start + usable] ** 2 / 1000,
            ])
            split = int(0.8 * usable)
            from numpy.linalg import lstsq
            X_train = np.column_stack([features[:split], np.ones(split)])
            y_train = target[:split]
            coef, _, _, _ = lstsq(X_train, y_train, rcond=None)
            X_val = np.column_stack([features[split:], np.ones(usable - split)])
            pred = X_val @ coef
            actual = target[split:]
            val_hours = hours[start + h_steps + 1 + split:
                             start + h_steps + 1 + split + len(pred)]

        residuals = actual - pred
        abs_residuals = np.abs(residuals)
        n_val = len(residuals)

        if n_val < 100 or len(val_hours) < n_val:
            continue
        val_hours = val_hours[:n_val]

        # Classify each residual by context
        bolus_arr = np.nan_to_num(df['bolus'].values.astype(np.float64), nan=0.0)
        carbs_arr = np.nan_to_num(df['carbs'].values.astype(np.float64), nan=0.0)

        # Build context masks (simplified: based on val-set hours)
        dawn_mask = (val_hours >= 4) & (val_hours < 7)
        postprandial_mask = np.zeros(n_val, dtype=bool)
        high_bg_mask = (actual > 200)
        low_bg_mask = (actual < 80)

        # Detect postprandial periods in validation set
        val_start_idx = len(bg) - n_val  # approximate
        for i in range(n_val):
            global_idx = val_start_idx + i
            if global_idx < 3 * STEPS_PER_HOUR:
                continue
            # Check if any carbs in prior 3 hours
            lookback = min(3 * STEPS_PER_HOUR, global_idx)
            if global_idx < len(carbs_arr):
                if np.sum(carbs_arr[global_idx - lookback:global_idx]) > 5:
                    postprandial_mask[i] = True

        # Sensor warmup (first 2h after sensor start)
        sensor_warmup_mask = np.zeros(n_val, dtype=bool)
        if 'sensor_warmup' in df.columns:
            warmup = df['sensor_warmup'].values
            val_warmup = warmup[len(warmup) - n_val:]
            sensor_warmup_mask = val_warmup > 0.5

        # Remaining = not any of the above
        any_attributed = (dawn_mask | postprandial_mask | high_bg_mask |
                         low_bg_mask | sensor_warmup_mask)
        unexplained_mask = ~any_attributed

        # Compute MAE by source
        sources = {
            'postprandial': postprandial_mask,
            'dawn_phenomenon': dawn_mask,
            'high_bg': high_bg_mask,
            'low_bg': low_bg_mask,
            'sensor_warmup': sensor_warmup_mask,
            'unexplained': unexplained_mask,
        }

        source_results = {}
        total_mae = np.mean(abs_residuals)
        for name, mask in sources.items():
            if np.sum(mask) > 10:
                mae = np.mean(abs_residuals[mask])
                pct = np.sum(mask) / n_val
                contribution = mae * pct / total_mae  # weighted contribution
                source_results[name] = {
                    'mae_mgdl': round(mae, 1),
                    'pct_of_time': round(pct, 3),
                    'relative_difficulty': round(mae / total_mae, 2),
                    'weighted_contribution': round(contribution, 3),
                }
            else:
                source_results[name] = {'mae_mgdl': None, 'pct_of_time': 0}

        per_patient.append({
            'patient': p['name'],
            'overall_mae': round(total_mae, 1),
            'overall_rmse': round(np.sqrt(np.mean(residuals**2)), 1),
            'n_val_points': n_val,
            'sources': source_results,
        })

    detail_str = f"patients={len(per_patient)}"
    if per_patient:
        mean_mae = np.mean([pp['overall_mae'] for pp in per_patient])
        # Find dominant source across patients
        source_names = ['postprandial', 'dawn_phenomenon', 'high_bg', 'unexplained']
        mean_difficulties = {}
        for sn in source_names:
            diffs = [pp['sources'].get(sn, {}).get('relative_difficulty', 1.0)
                     for pp in per_patient
                     if pp['sources'].get(sn, {}).get('relative_difficulty') is not None]
            if diffs:
                mean_difficulties[sn] = np.mean(diffs)
        hardest = max(mean_difficulties, key=mean_difficulties.get) if mean_difficulties else 'unknown'
        detail_str = f"mae={mean_mae:.1f}, hardest={hardest}"
    print(f"  Status: pass")
    print(f"  Detail: {detail_str}")

    elapsed = round(time.time() - t0, 1)
    print(f"  Time: {elapsed}s")

    return {
        'experiment': 'EXP-977',
        'name': 'Residual Source Decomposition',
        'status': 'pass',
        'detail': detail_str,
        'results': {
            'n_patients': len(per_patient),
            'per_patient': per_patient,
        },
        'elapsed_seconds': elapsed,
    }


# ===================================================================
# EXP-978: Cross-Patient Feature Importance (LOPO Stability)
# ===================================================================

def run_exp978(patients, args):
    """Which features generalize across patients vs are patient-specific?

    Train ridge on each patient individually, compare feature coefficients.
    Features with consistent sign/magnitude = generalizable.
    Features with high variance = patient-specific.
    """
    print("\n" + "=" * 60)
    print("Running EXP-978: Cross-Patient Feature Importance")
    print("=" * 60)
    t0 = time.time()

    try:
        from cgmencode.exp_autoresearch_951 import _build_grand_features
    except ImportError:
        print("  ERROR: Cannot import _build_grand_features")
        return {'experiment': 'EXP-978', 'status': 'error'}

    h_steps = 12
    all_coefs = []
    patient_names = []

    feature_names = [
        'bg', 'fwd_supply', 'fwd_demand', 'fwd_hepatic',
        'fwd_supply2', 'fwd_demand2', 'fwd_hepatic2',
        'bwd_supply', 'bwd_demand', 'bwd_hepatic',
        'residual', 'sin_hour', 'cos_hour', 'bias',
        'bg_delta', 'bg_accel', 'bg_lag6', 'bg_lag12',
        'mean24h', 'std24h', 'trend24h', 'bg_sq',
        'd_supply', 'd_demand', 'd2_supply', 'd2_demand', 'd_net',
        'pp_time', 'pp_phase', 'pp_sin', 'pp_cos', 'pp_rise',
        'iob_f1', 'iob_f2', 'iob_f3', 'iob_f4', 'iob_f5',
        'ema_1h', 'ema_4h',
        'bias_term',
    ]

    for p in patients:
        result = _build_grand_features(p, h_steps=h_steps, start=24)
        if result[0] is None:
            continue
        grand_features, d_back = result
        bg = d_back['bg']
        start = 24
        usable = grand_features.shape[0]
        target = bg[start + h_steps + 1:start + h_steps + 1 + usable]

        # Standardize features
        X = grand_features.copy()
        means = np.mean(X, axis=0)
        stds = np.std(X, axis=0)
        stds[stds < 1e-8] = 1.0
        X = (X - means) / stds

        # Add bias
        X = np.column_stack([X, np.ones(usable)])

        # Ridge regression (standardized coefficients)
        lam = 0.1
        XtX = X.T @ X + lam * np.eye(X.shape[1])
        Xty = X.T @ target
        coef = np.linalg.solve(XtX, Xty)

        all_coefs.append(coef)
        patient_names.append(p['name'])

    if len(all_coefs) < 3:
        print("  ERROR: Not enough patients")
        return {'experiment': 'EXP-978', 'status': 'error'}

    coef_matrix = np.array(all_coefs)  # (n_patients, n_features+1)
    n_feat = coef_matrix.shape[1]
    n_names = min(n_feat, len(feature_names))

    # Analyze each feature
    feature_analysis = []
    for f in range(n_names):
        coefs = coef_matrix[:, f]
        mean_coef = np.mean(coefs)
        std_coef = np.std(coefs)
        cv = abs(std_coef / mean_coef) if abs(mean_coef) > 1e-6 else float('inf')
        sign_consistency = abs(np.mean(np.sign(coefs)))  # 1.0 = all same sign

        feature_analysis.append({
            'feature': feature_names[f] if f < len(feature_names) else f'feat_{f}',
            'mean_coef': round(mean_coef, 4),
            'std_coef': round(std_coef, 4),
            'cv': round(cv, 2) if np.isfinite(cv) else 999.0,
            'sign_consistency': round(sign_consistency, 2),
            'generalizable': cv < 1.0 and sign_consistency >= 0.8,
        })

    # Sort by generalizability
    generalizable = [f for f in feature_analysis if f['generalizable']]
    patient_specific = [f for f in feature_analysis if not f['generalizable']]

    # Sort by absolute mean coefficient (importance)
    generalizable.sort(key=lambda x: abs(x['mean_coef']), reverse=True)
    patient_specific.sort(key=lambda x: abs(x['mean_coef']), reverse=True)

    detail = (f"generalizable={len(generalizable)}/{n_names}, "
              f"patient_specific={len(patient_specific)}/{n_names}")
    print(f"  Status: pass")
    print(f"  Detail: {detail}")

    elapsed = round(time.time() - t0, 1)
    print(f"  Time: {elapsed}s")

    return {
        'experiment': 'EXP-978',
        'name': 'Cross-Patient Feature Importance',
        'status': 'pass',
        'detail': detail,
        'results': {
            'n_features': n_names,
            'n_generalizable': len(generalizable),
            'n_patient_specific': len(patient_specific),
            'top_generalizable': generalizable[:10],
            'top_patient_specific': patient_specific[:10],
            'n_patients': len(patient_names),
            'all_features': feature_analysis,
        },
        'elapsed_seconds': elapsed,
    }


# ===================================================================
# EXP-979: Multi-Week Trend Analysis
# ===================================================================

def run_exp979(patients, args):
    """Rolling weekly metrics — detect improvement or deterioration.

    Track: TIR, mean BG, glucose CV, supply/demand balance, correction
    frequency, hypo rate. Test for significant trends.
    """
    print("\n" + "=" * 60)
    print("Running EXP-979: Multi-Week Trend Analysis")
    print("=" * 60)
    t0 = time.time()

    per_patient = []
    for p in patients:
        df = p['df']
        bg = np.nan_to_num(df['glucose'].values.astype(np.float64), nan=0.0)
        bolus = np.nan_to_num(df['bolus'].values.astype(np.float64), nan=0.0)
        carbs_arr = np.nan_to_num(df['carbs'].values.astype(np.float64), nan=0.0)
        sd = compute_supply_demand(p['df'], p['pk'])

        WEEK = 7 * STEPS_PER_DAY
        n_weeks = len(bg) // WEEK
        if n_weeks < 4:
            continue

        weeks = []
        for w in range(n_weeks):
            start = w * WEEK
            end = start + WEEK
            wbg = bg[start:end]
            valid = wbg > 30

            if np.sum(valid) < WEEK * 0.5:
                continue

            wbg_v = wbg[valid]
            tir = np.mean((wbg_v >= 70) & (wbg_v <= 180))
            tbr = np.mean(wbg_v < 70)
            tar = np.mean(wbg_v > 180)
            mean_bg = np.mean(wbg_v)
            cv = np.std(wbg_v) / mean_bg if mean_bg > 0 else 0

            # Treatment intensity
            w_bolus = bolus[start:end]
            w_carbs = carbs_arr[start:end]
            daily_insulin = np.sum(w_bolus) / 7.0
            daily_carbs = np.sum(w_carbs) / 7.0
            n_boluses = np.sum(w_bolus > 0.1) / 7.0
            n_meals = np.sum(w_carbs > 5.0) / 7.0

            # Supply/demand balance
            w_net = sd['net'][start:end]
            net_balance = np.mean(w_net[valid])

            weeks.append({
                'week': w,
                'tir': round(tir, 3),
                'tbr': round(tbr, 4),
                'tar': round(tar, 3),
                'mean_bg': round(mean_bg, 1),
                'cv': round(cv, 3),
                'daily_bolus_insulin': round(daily_insulin, 1),
                'daily_carbs_g': round(daily_carbs, 0),
                'boluses_per_day': round(n_boluses, 1),
                'meals_per_day': round(n_meals, 1),
                'net_balance': round(net_balance, 3),
            })

        if len(weeks) < 4:
            continue

        # Test trends for each metric
        trends = {}
        for metric in ['tir', 'mean_bg', 'cv', 'tbr', 'daily_bolus_insulin',
                        'daily_carbs_g', 'net_balance']:
            values = [w[metric] for w in weeks]
            x = np.arange(len(values))
            slope, intercept, r_val, p_val, _ = stats.linregress(x, values)
            trends[metric] = {
                'slope_per_week': round(slope, 4),
                'p_value': round(p_val, 4),
                'significant': p_val < 0.05,
                'direction': ('improving' if
                              (metric in ['tir'] and slope > 0) or
                              (metric in ['mean_bg', 'cv', 'tbr'] and slope < 0)
                              else 'deteriorating' if
                              (metric in ['tir'] and slope < 0) or
                              (metric in ['mean_bg', 'cv', 'tbr'] and slope > 0)
                              else 'stable'),
            }

        per_patient.append({
            'patient': p['name'],
            'n_weeks': len(weeks),
            'trends': trends,
            'first_week': weeks[0],
            'last_week': weeks[-1],
        })

    # Aggregate significant trends
    sig_trends = {}
    for metric in ['tir', 'mean_bg', 'cv', 'tbr']:
        improving = sum(1 for pp in per_patient
                       if pp['trends'].get(metric, {}).get('significant', False)
                       and pp['trends'][metric]['direction'] == 'improving')
        deteriorating = sum(1 for pp in per_patient
                           if pp['trends'].get(metric, {}).get('significant', False)
                           and pp['trends'][metric]['direction'] == 'deteriorating')
        sig_trends[metric] = {'improving': improving, 'deteriorating': deteriorating}

    detail = f"patients={len(per_patient)}, sig_tir_trends={sig_trends.get('tir', {})}"
    print(f"  Status: pass")
    print(f"  Detail: {detail}")

    elapsed = round(time.time() - t0, 1)
    print(f"  Time: {elapsed}s")

    return {
        'experiment': 'EXP-979',
        'name': 'Multi-Week Trend Analysis',
        'status': 'pass',
        'detail': detail,
        'results': {
            'n_patients': len(per_patient),
            'significant_trends': sig_trends,
            'per_patient': per_patient,
        },
        'elapsed_seconds': elapsed,
    }


# ===================================================================
# EXP-980: Conservation Violation as Clinical Signal
# ===================================================================

def run_exp980(patients, args):
    """When PK model supply-demand doesn't match observed glucose changes,
    the violation is a clinical signal. Persistent positive violation =
    unmodeled glucose source. Persistent negative = unmodeled glucose sink.

    Correlate conservation violation magnitude with:
    - Time of day (dawn phenomenon?)
    - Sensor age (degradation?)
    - Days since site change (cannula occlusion?)
    - Post-meal timing (absorption model error?)
    """
    print("\n" + "=" * 60)
    print("Running EXP-980: Conservation Violation as Clinical Signal")
    print("=" * 60)
    t0 = time.time()

    per_patient = []
    for p in patients:
        df = p['df']
        bg = np.nan_to_num(df['glucose'].values.astype(np.float64), nan=0.0)
        hours = _get_local_hour(df)
        sd = compute_supply_demand(p['df'], p['pk'])

        # Conservation violation: observed ΔBG - predicted ΔBG (from supply/demand)
        delta_bg_obs = np.zeros_like(bg)
        delta_bg_obs[1:] = bg[1:] - bg[:-1]
        delta_bg_pred = sd['net']  # supply - demand = predicted ΔBG

        violation = delta_bg_obs - delta_bg_pred
        abs_violation = np.abs(violation)

        valid = bg > 30
        if np.sum(valid) < 1000:
            continue

        # By time of day (6-hour blocks)
        tod_violations = {}
        for block_start in [0, 6, 12, 18]:
            mask = valid & (hours >= block_start) & (hours < block_start + 6)
            if np.sum(mask) > 100:
                tod_violations[f"{block_start:02d}-{block_start+6:02d}h"] = {
                    'mean_violation': round(np.mean(violation[mask]), 3),
                    'abs_mean': round(np.mean(abs_violation[mask]), 3),
                    'std': round(np.std(violation[mask]), 3),
                    'n_points': int(np.sum(mask)),
                }

        # By sensor age (if available)
        sage_analysis = None
        if 'sage_hours' in df.columns:
            sage = df['sage_hours'].values
            sage_valid = sage[valid]
            viol_valid = violation[valid]
            # Bin by sensor day
            sage_bins = {}
            for day in range(0, 11):
                mask = (sage_valid >= day * 24) & (sage_valid < (day + 1) * 24)
                if np.sum(mask) > 50:
                    sage_bins[f"day_{day}"] = {
                        'mean_abs_violation': round(np.mean(np.abs(viol_valid[mask])), 3),
                        'n_points': int(np.sum(mask)),
                    }
            if sage_bins:
                sage_analysis = sage_bins

        # By cannula age (if available)
        cage_analysis = None
        if 'cage_hours' in df.columns:
            cage = df['cage_hours'].values
            cage_valid = cage[valid]
            viol_valid = violation[valid]
            cage_bins = {}
            for day in range(0, 5):
                mask = (cage_valid >= day * 24) & (cage_valid < (day + 1) * 24)
                if np.sum(mask) > 50:
                    cage_bins[f"day_{day}"] = {
                        'mean_abs_violation': round(np.mean(np.abs(viol_valid[mask])), 3),
                        'n_points': int(np.sum(mask)),
                    }
            if cage_bins:
                cage_analysis = cage_bins

        # Postprandial vs fasting violation
        carbs_arr = np.nan_to_num(df['carbs'].values.astype(np.float64), nan=0.0)
        postprandial = np.zeros(len(bg), dtype=bool)
        for i in range(len(carbs_arr)):
            if carbs_arr[i] > 5:
                end = min(i + 3 * STEPS_PER_HOUR, len(bg))
                postprandial[i:end] = True

        pp_mask = valid & postprandial
        fasting_mask = valid & ~postprandial

        meal_violation = np.mean(abs_violation[pp_mask]) if np.sum(pp_mask) > 100 else None
        fasting_violation = np.mean(abs_violation[fasting_mask]) if np.sum(fasting_mask) > 100 else None

        overall_rmse = np.sqrt(np.mean(violation[valid]**2))
        overall_bias = np.mean(violation[valid])

        per_patient.append({
            'patient': p['name'],
            'overall_rmse': round(overall_rmse, 2),
            'overall_bias': round(overall_bias, 3),
            'mean_abs_violation': round(np.mean(abs_violation[valid]), 2),
            'postprandial_violation': round(meal_violation, 2) if meal_violation else None,
            'fasting_violation': round(fasting_violation, 2) if fasting_violation else None,
            'meal_vs_fasting_ratio': round(meal_violation / fasting_violation, 2)
                if meal_violation and fasting_violation and fasting_violation > 0 else None,
            'by_time_of_day': tod_violations,
            'by_sensor_age': sage_analysis,
            'by_cannula_age': cage_analysis,
        })

    # Aggregate
    rmses = [pp['overall_rmse'] for pp in per_patient]
    ratios = [pp['meal_vs_fasting_ratio'] for pp in per_patient
              if pp['meal_vs_fasting_ratio'] is not None]
    detail = (f"mean_rmse={np.mean(rmses):.2f}, "
              f"meal/fasting_ratio={np.mean(ratios):.2f}" if ratios else
              f"mean_rmse={np.mean(rmses):.2f}")
    print(f"  Status: pass")
    print(f"  Detail: {detail}")

    elapsed = round(time.time() - t0, 1)
    print(f"  Time: {elapsed}s")

    return {
        'experiment': 'EXP-980',
        'name': 'Conservation Violation as Clinical Signal',
        'status': 'pass',
        'detail': detail,
        'results': {
            'mean_overall_rmse': round(np.mean(rmses), 2),
            'mean_meal_fasting_ratio': round(np.mean(ratios), 2) if ratios else None,
            'n_patients': len(per_patient),
            'per_patient': per_patient,
        },
        'elapsed_seconds': elapsed,
    }


# ===================================================================
# Main
# ===================================================================

EXPERIMENTS = {
    971: ('Multi-Day Glucose Pattern Detection', run_exp971),
    972: ('Basal Adequacy by 6-Hour Segment', run_exp972),
    973: ('CR Effectiveness per Time-of-Day', run_exp973),
    974: ('ISF Validation from Correction Boluses', run_exp974),
    975: ('Rolling Settings Fidelity + Breakpoints', run_exp975),
    976: ('24-Hour Supply/Demand Integral Balance', run_exp976),
    977: ('Residual Source Decomposition', run_exp977),
    978: ('Cross-Patient Feature Importance', run_exp978),
    979: ('Multi-Week Trend Analysis', run_exp979),
    980: ('Conservation Violation as Clinical Signal', run_exp980),
}


def main():
    parser = argparse.ArgumentParser(
        description='EXP-971-980: Clinical Intelligence & Multi-Scale Analysis')
    parser.add_argument('--detail', action='store_true',
                        help='Print per-patient details')
    parser.add_argument('--save', action='store_true',
                        help='Save results to JSON')
    parser.add_argument('--max-patients', type=int, default=11)
    parser.add_argument('--experiments', type=str, default='all',
                        help='Comma-separated experiment numbers or "all"')
    args = parser.parse_args()

    patients = load_patients(str(PATIENTS_DIR), max_patients=args.max_patients)

    if args.experiments == 'all':
        exp_nums = sorted(EXPERIMENTS.keys())
    else:
        exp_nums = [int(x.strip()) for x in args.experiments.split(',')]

    results = {}
    for num in exp_nums:
        if num not in EXPERIMENTS:
            print(f"Unknown experiment: {num}")
            continue
        name, func = EXPERIMENTS[num]
        try:
            result = func(patients, args)
            results[num] = result
            if args.save and result and result.get('status') != 'error':
                save_dir = Path(__file__).resolve().parent.parent.parent / 'externals' / 'experiments'
                save_dir.mkdir(parents=True, exist_ok=True)
                safe_name = name.lower().replace(' ', '_').replace('+', '_').replace('/', '_')
                fname = save_dir / f"exp_exp_{num}_{safe_name}.json"
                with open(fname, 'w') as f:
                    json.dump(result, f, indent=2, default=str)
                print(f"  Saved: {fname}")
        except Exception as e:
            print(f"  ERROR in EXP-{num}: {e}")
            import traceback
            traceback.print_exc()
            results[num] = {'experiment': f'EXP-{num}', 'status': 'error',
                           'error': str(e)}

    print("\n" + "=" * 60)
    print("All experiments complete")
    print("=" * 60)


if __name__ == '__main__':
    main()
