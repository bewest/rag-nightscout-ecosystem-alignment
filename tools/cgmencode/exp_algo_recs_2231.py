#!/usr/bin/env python3
"""
EXP-2231–2238: AID Algorithm Recommendations & Production Readiness

Maps research findings from ~180 experiments into concrete algorithm
recommendations for Loop, AAPS, and Trio. Tests which findings are
production-ready vs need more validation.

Experiments:
  2231 - Basal Schedule Generator (optimal circadian basal profiles)
  2232 - ISF Schedule Generator (circadian + dose-dependent ISF)
  2233 - CR Schedule Generator (meal-type-aware CR profiles)
  2234 - DIA Estimation (population-level from stacking constraints)
  2235 - Glucose Quality Score (single number for therapy quality)
  2236 - Settings Drift Detection (when do settings need updating?)
  2237 - Risk Score Decomposition (basal vs bolus vs meal risk)
  2238 - Algorithm Recommendation Summary (per-patient action plans)

Usage:
    PYTHONPATH=tools python3 tools/cgmencode/exp_algo_recs_2231.py --figures
"""

import argparse
import json
import os
import sys
import warnings
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings('ignore')

from cgmencode.exp_metabolic_441 import load_patients

STEPS_PER_HOUR = 12
STEPS_PER_DAY = 288
HYPO_THRESHOLD = 70
TARGET_LOW = 70
TARGET_HIGH = 180


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


def get_profile_value(schedule, hour):
    if not schedule:
        return None
    val = schedule[0].get('value', None)
    for entry in schedule:
        t = entry.get('timeAsSeconds', 0) / 3600.0
        if t <= hour:
            val = entry.get('value', val)
    return val


def compute_tir_tbr(glucose):
    valid = glucose[~np.isnan(glucose)]
    if len(valid) == 0:
        return 0.0, 0.0, 0.0
    tir = np.mean((valid >= TARGET_LOW) & (valid <= TARGET_HIGH)) * 100
    tbr = np.mean(valid < TARGET_LOW) * 100
    tar = np.mean(valid > TARGET_HIGH) * 100
    return tir, tbr, tar


# ─────────────────────────────────────────────────────────────────
# EXP-2231: Basal Schedule Generator
# ─────────────────────────────────────────────────────────────────
def exp_2231_basal_schedule(patients):
    """
    Generate optimal circadian basal profiles by analyzing the loop's
    actual delivery pattern (what it delivers vs what's scheduled).
    """
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        glucose = df['glucose'].values
        enacted = df['enacted_rate'].values if 'enacted_rate' in df.columns else None
        n = len(glucose)
        basal_sched = df.attrs.get('basal_schedule', [])

        if enacted is None or not basal_sched:
            results[name] = {'skip': True, 'reason': 'no enacted/basal data'}
            continue

        # Compute hourly delivery ratio
        hours = np.arange(n) / STEPS_PER_HOUR % 24
        hourly_delivery = np.zeros(24)
        hourly_scheduled = np.zeros(24)
        hourly_count = np.zeros(24)

        for i in range(n):
            if np.isnan(enacted[i]):
                continue
            h = int(hours[i])
            sched_val = get_profile_value(basal_sched, hours[i])
            if sched_val is None or sched_val <= 0:
                continue
            hourly_delivery[h] += enacted[i]
            hourly_scheduled[h] += sched_val
            hourly_count[h] += 1

        # Compute delivery ratio per hour
        hourly_ratio = np.zeros(24)
        for h in range(24):
            if hourly_scheduled[h] > 0:
                hourly_ratio[h] = hourly_delivery[h] / hourly_scheduled[h]

        # Overall delivery ratio
        total_ratio = np.sum(hourly_delivery) / np.sum(hourly_scheduled) if np.sum(hourly_scheduled) > 0 else 0

        # Generate recommended schedule: actual_delivery = ratio * scheduled
        # But cap at reasonable range (0.1 to 3.0 U/h)
        recommended = []
        profile_rate = get_profile_value(basal_sched, 0) or 1.0
        for h in range(24):
            if hourly_count[h] > 0:
                actual_rate = hourly_delivery[h] / hourly_count[h]
            else:
                actual_rate = profile_rate * total_ratio
            actual_rate = max(0.05, min(3.0, actual_rate))
            recommended.append({
                'hour': h,
                'current_rate': round(get_profile_value(basal_sched, h) or 0, 3),
                'recommended_rate': round(actual_rate, 3),
                'delivery_ratio': round(hourly_ratio[h], 3),
            })

        # Peak/trough of recommended
        rec_rates = [r['recommended_rate'] for r in recommended]
        peak_hour = int(np.argmax(rec_rates))
        trough_hour = int(np.argmin(rec_rates))
        circadian_range = max(rec_rates) / max(min(rec_rates), 0.05)

        results[name] = {
            'overall_delivery_ratio': round(total_ratio, 3),
            'recommended_schedule': recommended,
            'peak_hour': peak_hour,
            'trough_hour': trough_hour,
            'circadian_range': round(circadian_range, 2),
            'current_mean_rate': round(float(np.mean([r['current_rate'] for r in recommended])), 3),
            'recommended_mean_rate': round(float(np.mean(rec_rates)), 3),
        }
    return results


# ─────────────────────────────────────────────────────────────────
# EXP-2232: ISF Schedule Generator
# ─────────────────────────────────────────────────────────────────
def exp_2232_isf_schedule(patients):
    """
    Generate circadian ISF profiles from correction response data.
    """
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        glucose = df['glucose'].values
        bolus = df['bolus'].values if 'bolus' in df.columns else None
        carbs = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(glucose))
        n = len(glucose)
        isf_sched = df.attrs.get('isf_schedule', [])

        if bolus is None:
            results[name] = {'skip': True}
            continue

        # Find corrections by time of day
        hourly_isf = {h: [] for h in range(24)}

        for i in range(STEPS_PER_HOUR, n - STEPS_PER_HOUR * 4):
            if np.isnan(bolus[i]) or bolus[i] < 0.1:
                continue
            if np.isnan(glucose[i]) or glucose[i] < 120:
                continue
            # No carbs ±30min
            c_win = carbs[max(0, i - 6):min(i + 6, n)]
            if np.nansum(c_win) > 1:
                continue

            # Measure drop at 3h
            g3h = glucose[min(i + STEPS_PER_HOUR * 3, n - 1)]
            if np.isnan(g3h):
                continue

            isf_eff = (glucose[i] - g3h) / bolus[i]
            if isf_eff > 0:  # Valid correction (glucose dropped)
                hour = int((i / STEPS_PER_HOUR) % 24)
                hourly_isf[hour].append(isf_eff)

        # Build schedule
        schedule = []
        profile_isf = get_profile_value(isf_sched, 12) if isf_sched else None
        if profile_isf and profile_isf < 15:
            profile_isf *= 18.0182

        for h in range(24):
            vals = hourly_isf[h]
            current = get_profile_value(isf_sched, h)
            if current and current < 15:
                current *= 18.0182

            if len(vals) >= 3:
                eff = float(np.median(vals))
                schedule.append({
                    'hour': h,
                    'current_isf': round(current, 1) if current else None,
                    'effective_isf': round(eff, 1),
                    'n': len(vals),
                    'ratio': round(eff / current, 2) if current and current > 0 else None,
                })
            else:
                schedule.append({
                    'hour': h,
                    'current_isf': round(current, 1) if current else None,
                    'effective_isf': None,
                    'n': len(vals),
                    'ratio': None,
                })

        # Summarize
        eff_vals = [s['effective_isf'] for s in schedule if s['effective_isf'] is not None]
        ratios = [s['ratio'] for s in schedule if s['ratio'] is not None]

        results[name] = {
            'schedule': schedule,
            'n_total_corrections': sum(len(hourly_isf[h]) for h in range(24)),
            'mean_effective_isf': round(float(np.mean(eff_vals)), 1) if eff_vals else None,
            'mean_ratio': round(float(np.mean(ratios)), 2) if ratios else None,
            'circadian_range': round(max(eff_vals) / min(eff_vals), 2) if eff_vals and min(eff_vals) > 0 else None,
            'profile_isf': round(profile_isf, 1) if profile_isf else None,
        }
    return results


# ─────────────────────────────────────────────────────────────────
# EXP-2233: CR Schedule Generator
# ─────────────────────────────────────────────────────────────────
def exp_2233_cr_schedule(patients):
    """
    Generate meal-time CR profiles from post-meal response data.
    """
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        glucose = df['glucose'].values
        bolus = df['bolus'].values if 'bolus' in df.columns else None
        carbs = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(glucose))
        n = len(glucose)
        cr_sched = df.attrs.get('cr_schedule', [])

        if bolus is None:
            results[name] = {'skip': True}
            continue

        # Find meals by time of day
        periods = {
            'breakfast (6-10)': (6, 10),
            'lunch (10-14)': (10, 14),
            'afternoon (14-18)': (14, 18),
            'dinner (18-22)': (18, 22),
            'overnight (22-6)': (22, 6),
        }

        period_data = {}
        for period_name, (start_h, end_h) in periods.items():
            spikes = []
            net_changes = []
            carb_amounts = []
            bolus_amounts = []

            for i in range(STEPS_PER_HOUR, n - STEPS_PER_HOUR * 4):
                if np.isnan(carbs[i]) or carbs[i] < 5:
                    continue
                hour = (i / STEPS_PER_HOUR) % 24
                if start_h < end_h:
                    if not (start_h <= hour < end_h):
                        continue
                else:  # overnight wraps around
                    if not (hour >= start_h or hour < end_h):
                        continue

                g_pre = np.nanmean(glucose[max(0, i - 3):i + 1])
                if np.isnan(g_pre):
                    continue

                g_post = glucose[i:min(i + STEPS_PER_HOUR * 3, n)]
                if len(g_post) < STEPS_PER_HOUR:
                    continue

                spike = np.nanmax(g_post) - g_pre
                g_3h = glucose[min(i + STEPS_PER_HOUR * 3, n - 1)]
                net = g_3h - g_pre if not np.isnan(g_3h) else np.nan

                b_win = bolus[max(0, i - STEPS_PER_HOUR):min(i + STEPS_PER_HOUR, n)]
                total_b = float(np.nansum(b_win[~np.isnan(b_win)]))

                spikes.append(float(spike))
                if not np.isnan(net):
                    net_changes.append(float(net))
                carb_amounts.append(float(carbs[i]))
                bolus_amounts.append(total_b)

            if spikes:
                # Effective CR from bolus/carbs ratio
                effective_crs = []
                for c, b in zip(carb_amounts, bolus_amounts):
                    if b > 0.1 and c > 0:
                        effective_crs.append(c / b)

                period_data[period_name] = {
                    'n_meals': len(spikes),
                    'mean_spike': round(float(np.mean(spikes)), 1),
                    'mean_net_3h': round(float(np.mean(net_changes)), 1) if net_changes else 0,
                    'mean_carbs': round(float(np.mean(carb_amounts)), 1),
                    'mean_effective_cr': round(float(np.median(effective_crs)), 1) if effective_crs else None,
                    'assessment': 'over-bolusing' if net_changes and np.mean(net_changes) < -20 else
                                 'under-bolusing' if net_changes and np.mean(net_changes) > 20 else 'adequate',
                }

        # Overall
        profile_cr = get_profile_value(cr_sched, 12) if cr_sched else None

        results[name] = {
            'periods': period_data,
            'profile_cr': profile_cr,
            'n_periods_analyzed': len(period_data),
        }
    return results


# ─────────────────────────────────────────────────────────────────
# EXP-2234: DIA Estimation
# ─────────────────────────────────────────────────────────────────
def exp_2234_dia_estimation(patients):
    """
    Estimate effective DIA from population data despite stacking.
    Uses the autocorrelation of glucose response to boluses as a proxy.
    """
    results = {}

    # Collect all patients' correction data
    all_corrections = []

    for pat in patients:
        name = pat['name']
        df = pat['df']
        glucose = df['glucose'].values
        bolus = df['bolus'].values if 'bolus' in df.columns else None
        carbs = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(glucose))
        iob = df['iob'].values if 'iob' in df.columns else None
        n = len(glucose)

        if bolus is None:
            results[name] = {'skip': True}
            continue

        # All boluses > 0.1U (not just isolated)
        bolus_indices = np.where(~np.isnan(bolus) & (bolus > 0.1))[0]

        # Track glucose response duration
        durations = []
        for idx in bolus_indices:
            if idx + STEPS_PER_HOUR * 8 >= n or idx < STEPS_PER_HOUR:
                continue
            # No carbs ±30min
            c_win = carbs[max(0, idx - 6):min(idx + 6, n)]
            if np.nansum(c_win) > 1:
                continue

            g_pre = glucose[idx]
            if np.isnan(g_pre) or g_pre < 100:
                continue

            # Find nadir (maximum drop)
            g_post = glucose[idx:idx + STEPS_PER_HOUR * 8]
            nadir_idx = np.nanargmin(g_post)
            nadir_time_h = nadir_idx / STEPS_PER_HOUR

            # Find when glucose returns to within 10% of starting
            recovery_idx = None
            for j in range(nadir_idx, len(g_post)):
                if not np.isnan(g_post[j]) and abs(g_post[j] - g_pre) < g_pre * 0.05:
                    recovery_idx = j
                    break

            if recovery_idx:
                dia_effective = recovery_idx / STEPS_PER_HOUR
                durations.append(dia_effective)

            all_corrections.append({
                'patient': name,
                'nadir_time_h': float(nadir_time_h),
                'bolus': float(bolus[idx]),
            })

        if durations:
            results[name] = {
                'n_corrections': len(durations),
                'median_dia_h': round(float(np.median(durations)), 2),
                'mean_dia_h': round(float(np.mean(durations)), 2),
                'std_dia_h': round(float(np.std(durations)), 2),
                'p25_dia_h': round(float(np.percentile(durations, 25)), 2),
                'p75_dia_h': round(float(np.percentile(durations, 75)), 2),
                'profile_dia': 6.0,
            }
        else:
            results[name] = {'skip': True, 'n_corrections': 0}

    # Population-level estimate
    all_nadirs = [c['nadir_time_h'] for c in all_corrections]
    if all_nadirs:
        results['_population'] = {
            'n_corrections': len(all_nadirs),
            'median_nadir_time_h': round(float(np.median(all_nadirs)), 2),
            'mean_nadir_time_h': round(float(np.mean(all_nadirs)), 2),
            'estimated_dia_h': round(float(np.median(all_nadirs)) * 2.5, 1),  # nadir ≈ 40% of DIA
        }

    return results


# ─────────────────────────────────────────────────────────────────
# EXP-2235: Glucose Quality Score
# ─────────────────────────────────────────────────────────────────
def exp_2235_quality_score(patients):
    """
    Compute a single glucose quality score (0-100) combining TIR, TBR,
    variability, and stability.
    """
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        glucose = df['glucose'].values
        n = len(glucose)

        valid = glucose[~np.isnan(glucose)]
        if len(valid) < STEPS_PER_DAY:
            results[name] = {'skip': True}
            continue

        tir, tbr, tar = compute_tir_tbr(glucose)
        mean_g = float(np.mean(valid))
        cv = float(np.std(valid) / np.mean(valid) * 100)

        # GVI (Glycemic Variability Index)
        diffs = np.abs(np.diff(valid))
        straight_line = abs(valid[-1] - valid[0])
        actual_line = np.sum(diffs)
        gvi = actual_line / max(straight_line, 1)

        # LBGI (Low Blood Glucose Index)
        f_bg = 1.509 * (np.log(valid) ** 1.084 - 5.381)
        rl = np.where(f_bg < 0, 10 * f_bg ** 2, 0)
        lbgi = float(np.mean(rl))

        # HBGI (High Blood Glucose Index)
        rh = np.where(f_bg > 0, 10 * f_bg ** 2, 0)
        hbgi = float(np.mean(rh))

        # Composite score (0-100)
        # TIR contribution (0-40): >70% = full marks
        tir_score = min(40, tir * 40 / 70)
        # TBR contribution (0-30): <1% = full marks, >10% = 0
        tbr_score = max(0, 30 - tbr * 3)
        # CV contribution (0-15): <33% = full marks, >50% = 0
        cv_score = max(0, min(15, (50 - cv) * 15 / 17))
        # Stability contribution (0-15): low GVI = good
        gvi_score = max(0, min(15, (3 - gvi) * 15 / 2))

        quality_score = round(tir_score + tbr_score + cv_score + gvi_score, 1)

        results[name] = {
            'quality_score': quality_score,
            'components': {
                'tir_score': round(tir_score, 1),
                'tbr_score': round(tbr_score, 1),
                'cv_score': round(cv_score, 1),
                'gvi_score': round(gvi_score, 1),
            },
            'metrics': {
                'tir': round(tir, 1),
                'tbr': round(tbr, 1),
                'tar': round(tar, 1),
                'mean_glucose': round(mean_g, 1),
                'cv': round(cv, 1),
                'gvi': round(gvi, 1),
                'lbgi': round(lbgi, 2),
                'hbgi': round(hbgi, 2),
            },
        }
    return results


# ─────────────────────────────────────────────────────────────────
# EXP-2236: Settings Drift Detection
# ─────────────────────────────────────────────────────────────────
def exp_2236_drift_detection(patients):
    """
    Detect when AID settings become stale by analyzing temporal
    drift in key metrics.
    """
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        glucose = df['glucose'].values
        enacted = df['enacted_rate'].values if 'enacted_rate' in df.columns else None
        n = len(glucose)

        if n < STEPS_PER_DAY * 30:
            results[name] = {'skip': True}
            continue

        # Monthly segments
        month_size = STEPS_PER_DAY * 30
        n_months = n // month_size
        monthly = []

        for m in range(n_months):
            s = m * month_size
            e = s + month_size
            g = glucose[s:e]
            tir, tbr, tar = compute_tir_tbr(g)
            mean_g = float(np.nanmean(g))
            cv = float(np.nanstd(g[~np.isnan(g)]) / np.nanmean(g[~np.isnan(g)]) * 100) if np.nanmean(g[~np.isnan(g)]) > 0 else 0

            dr = np.nan
            if enacted is not None:
                en = enacted[s:e]
                basal_sched = df.attrs.get('basal_schedule', [])
                if basal_sched:
                    hours = np.arange(len(en)) / STEPS_PER_HOUR % 24
                    sched = np.array([get_profile_value(basal_sched, h) or 0.0 for h in hours])
                    sched_sum = np.nansum(sched)
                    if sched_sum > 0:
                        dr = np.nansum(en) / sched_sum

            monthly.append({
                'month': m + 1,
                'tir': round(tir, 1),
                'tbr': round(tbr, 1),
                'mean_glucose': round(mean_g, 1),
                'cv': round(cv, 1),
                'delivery_ratio': round(float(dr), 3) if not np.isnan(dr) else None,
            })

        # Trend analysis
        tir_trend = [m['tir'] for m in monthly]
        tbr_trend = [m['tbr'] for m in monthly]

        if len(tir_trend) >= 3:
            slope_tir, _, r_tir, p_tir, _ = stats.linregress(range(len(tir_trend)), tir_trend)
            slope_tbr, _, r_tbr, p_tbr, _ = stats.linregress(range(len(tbr_trend)), tbr_trend)
        else:
            slope_tir, r_tir, p_tir = 0, 0, 1
            slope_tbr, r_tbr, p_tbr = 0, 0, 1

        # Drift detection: is TIR declining or TBR increasing?
        needs_update = (slope_tir < -2 and p_tir < 0.1) or (slope_tbr > 1 and p_tbr < 0.1)

        results[name] = {
            'n_months': n_months,
            'monthly_data': monthly,
            'tir_slope_per_month': round(slope_tir, 2),
            'tbr_slope_per_month': round(slope_tbr, 2),
            'tir_trend_p': round(float(p_tir), 3),
            'tbr_trend_p': round(float(p_tbr), 3),
            'needs_settings_update': bool(needs_update),
        }
    return results


# ─────────────────────────────────────────────────────────────────
# EXP-2237: Risk Score Decomposition
# ─────────────────────────────────────────────────────────────────
def exp_2237_risk_decomposition(patients):
    """
    Decompose hypoglycemia risk into basal vs bolus vs meal contributions.
    """
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        glucose = df['glucose'].values
        bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(len(glucose))
        carbs = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(glucose))
        enacted = df['enacted_rate'].values if 'enacted_rate' in df.columns else None
        n = len(glucose)

        # Find hypo events
        hypo_events = []
        in_hypo = False
        hypo_start = 0
        for i in range(n):
            if np.isnan(glucose[i]):
                continue
            if glucose[i] < HYPO_THRESHOLD:
                if not in_hypo:
                    hypo_start = i
                    in_hypo = True
            else:
                if in_hypo:
                    hypo_events.append({'start': hypo_start, 'end': i,
                                        'nadir': float(np.nanmin(glucose[hypo_start:i]))})
                    in_hypo = False

        if not hypo_events:
            results[name] = {
                'n_hypos': 0,
                'basal_attributed': 0,
                'bolus_attributed': 0,
                'meal_attributed': 0,
                'unknown': 0,
            }
            continue

        # Classify each hypo by preceding event
        basal_count = 0
        bolus_count = 0
        meal_count = 0
        unknown_count = 0

        for event in hypo_events:
            start = event['start']
            # Look back 3h for causes
            window_start = max(0, start - STEPS_PER_HOUR * 3)

            had_bolus = np.any(~np.isnan(bolus[window_start:start]) & (bolus[window_start:start] > 0.05))
            had_carbs = np.any(~np.isnan(carbs[window_start:start]) & (carbs[window_start:start] > 2))

            if had_carbs and had_bolus:
                meal_count += 1  # Post-meal hypo (likely over-bolused meal)
            elif had_bolus:
                bolus_count += 1  # Correction hypo
            elif enacted is not None:
                # Was basal being delivered?
                en_pre = enacted[window_start:start]
                if np.nanmean(en_pre) > 0.1:
                    basal_count += 1
                else:
                    unknown_count += 1  # Hypo with suspended basal = IOB tail
            else:
                unknown_count += 1

        total = len(hypo_events)
        days = n / STEPS_PER_DAY

        results[name] = {
            'n_hypos': total,
            'hypos_per_day': round(total / days, 2),
            'basal_attributed': basal_count,
            'basal_pct': round(basal_count / total * 100, 1) if total > 0 else 0,
            'bolus_attributed': bolus_count,
            'bolus_pct': round(bolus_count / total * 100, 1) if total > 0 else 0,
            'meal_attributed': meal_count,
            'meal_pct': round(meal_count / total * 100, 1) if total > 0 else 0,
            'unknown': unknown_count,
            'unknown_pct': round(unknown_count / total * 100, 1) if total > 0 else 0,
        }
    return results


# ─────────────────────────────────────────────────────────────────
# EXP-2238: Algorithm Recommendation Summary
# ─────────────────────────────────────────────────────────────────
def exp_2238_recommendation_summary(patients, all_results):
    """
    Generate per-patient action plans combining all findings.
    """
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        glucose = df['glucose'].values
        n = len(glucose)

        tir, tbr, tar = compute_tir_tbr(glucose)

        # Gather from other experiments
        basal_data = all_results.get('exp_2231', {}).get(name, {})
        isf_data = all_results.get('exp_2232', {}).get(name, {})
        quality_data = all_results.get('exp_2235', {}).get(name, {})
        risk_data = all_results.get('exp_2237', {}).get(name, {})
        drift_data = all_results.get('exp_2236', {}).get(name, {})

        recommendations = []
        priority = 'LOW'

        # Basal recommendation
        dr = basal_data.get('overall_delivery_ratio', 1.0)
        if dr == 0:
            # No delivery data (e.g. patient j) — skip basal recommendation
            pass
        elif dr < 0.3:
            recommendations.append({
                'setting': 'Basal',
                'action': 'Reduce 50%',
                'urgency': 'HIGH',
                'rationale': f'Delivery ratio {dr:.2f} — basal is {1/dr:.0f}× too high',
            })
            priority = 'HIGH'
        elif dr < 0.5:
            recommendations.append({
                'setting': 'Basal',
                'action': 'Reduce 25%',
                'urgency': 'MODERATE',
                'rationale': f'Delivery ratio {dr:.2f} — basal is {1/dr:.1f}× too high',
            })
            if priority == 'LOW':
                priority = 'MODERATE'
        elif dr > 1.5:
            recommendations.append({
                'setting': 'Basal',
                'action': 'Increase 25%',
                'urgency': 'MODERATE',
                'rationale': f'Delivery ratio {dr:.2f} — basal is under-set',
            })

        # ISF recommendation
        isf_ratio = isf_data.get('mean_ratio')
        if isf_ratio and isf_ratio > 2.0:
            recommendations.append({
                'setting': 'ISF',
                'action': f'Increase {isf_ratio:.1f}×',
                'urgency': 'HIGH' if isf_ratio > 3 else 'MODERATE',
                'rationale': f'Insulin is {isf_ratio:.1f}× more effective than profile setting',
            })
        elif isf_ratio and isf_ratio < 0.7:
            recommendations.append({
                'setting': 'ISF',
                'action': 'Decrease',
                'urgency': 'MODERATE',
                'rationale': f'Corrections less effective than expected (ratio {isf_ratio:.2f})',
            })

        # TBR recommendation
        if tbr > 4:
            recommendations.append({
                'setting': 'Target',
                'action': 'Raise glucose target',
                'urgency': 'HIGH',
                'rationale': f'TBR {tbr:.1f}% exceeds clinical threshold (4%)',
            })
            priority = 'CRITICAL'

        # Quality score
        qs = quality_data.get('quality_score', 0)
        quality_grade = 'A' if qs >= 80 else 'B' if qs >= 65 else 'C' if qs >= 50 else 'D'

        # Settings freshness
        needs_update = drift_data.get('needs_settings_update', False)

        results[name] = {
            'tir': round(tir, 1),
            'tbr': round(tbr, 1),
            'quality_score': qs,
            'quality_grade': quality_grade,
            'priority': priority,
            'n_recommendations': len(recommendations),
            'recommendations': recommendations,
            'needs_settings_update': needs_update,
            'primary_risk_source': max(
                [('basal', risk_data.get('basal_pct', 0)),
                 ('bolus', risk_data.get('bolus_pct', 0)),
                 ('meal', risk_data.get('meal_pct', 0)),
                 ('unknown', risk_data.get('unknown_pct', 0))],
                key=lambda x: x[1]
            )[0] if risk_data else 'unknown',
        }
    return results


# ─────────────────────────────────────────────────────────────────
# Figure Generation
# ─────────────────────────────────────────────────────────────────
def generate_figures(all_results, fig_dir):
    os.makedirs(fig_dir, exist_ok=True)
    colors = plt.cm.tab10(np.linspace(0, 1, 11))

    # Fig 1: Basal Schedule (EXP-2231) — current vs recommended for 4 patients
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    r2231 = all_results['exp_2231']
    plot_pats = sorted([n for n in r2231 if not r2231[n].get('skip', False)])[:4]
    for idx, n in enumerate(plot_pats):
        ax = axes[idx // 2, idx % 2]
        data = r2231[n]
        hours = range(24)
        current = [s['current_rate'] for s in data['recommended_schedule']]
        recommended = [s['recommended_rate'] for s in data['recommended_schedule']]
        ax.step(hours, current, 'r-', linewidth=2, where='post', label='Current')
        ax.step(hours, recommended, 'b-', linewidth=2, where='post', label='Recommended')
        ax.fill_between(hours, recommended, step='post', alpha=0.2, color='blue')
        ax.set_xlabel('Hour of Day')
        ax.set_ylabel('Basal Rate (U/h)')
        ax.set_title(f'Patient {n}: DR={data["overall_delivery_ratio"]:.2f}')
        ax.legend()
        ax.set_xlim(0, 23)
    plt.tight_layout()
    plt.savefig(f'{fig_dir}/algo-fig01-basal-schedule.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  [fig] algo-fig01-basal-schedule.png")

    # Fig 2: ISF Schedule (EXP-2232)
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    r2232 = all_results['exp_2232']
    names2 = sorted([n for n in r2232 if not r2232[n].get('skip', False)])

    ratios = [r2232[n].get('mean_ratio', 0) or 0 for n in names2]
    circ = [r2232[n].get('circadian_range', 0) or 0 for n in names2]

    axes[0].bar(np.arange(len(names2)), ratios, color=[colors[i] for i in range(len(names2))], alpha=0.8)
    axes[0].set_xticks(np.arange(len(names2)))
    axes[0].set_xticklabels(names2)
    axes[0].set_ylabel('Effective/Profile ISF Ratio')
    axes[0].set_title('EXP-2232: ISF Mismatch Ratio')
    axes[0].axhline(1.0, color='green', ls='--', alpha=0.5, label='Perfect match')
    axes[0].legend()

    axes[1].bar(np.arange(len(names2)), circ, color=[colors[i] for i in range(len(names2))], alpha=0.8)
    axes[1].set_xticks(np.arange(len(names2)))
    axes[1].set_xticklabels(names2)
    axes[1].set_ylabel('Circadian ISF Range (max/min)')
    axes[1].set_title('EXP-2232: Circadian ISF Variation')

    plt.tight_layout()
    plt.savefig(f'{fig_dir}/algo-fig02-isf-schedule.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  [fig] algo-fig02-isf-schedule.png")

    # Fig 3: CR by Meal Period (EXP-2233)
    fig, ax = plt.subplots(figsize=(14, 6))
    r2233 = all_results['exp_2233']
    names3 = sorted([n for n in r2233 if not r2233[n].get('skip', False)])
    periods = ['breakfast (6-10)', 'lunch (10-14)', 'dinner (18-22)']
    period_colors = ['#ff6b6b', '#42a5f5', '#66bb6a']

    x = np.arange(len(names3))
    w = 0.25
    for pi, (period, pc) in enumerate(zip(periods, period_colors)):
        vals = []
        for n in names3:
            pd_data = r2233[n].get('periods', {}).get(period, {})
            vals.append(pd_data.get('mean_net_3h', 0))
        ax.bar(x + pi * w - w, vals, w, label=period.split('(')[0].strip(), color=pc, alpha=0.8)

    ax.set_xticks(x)
    ax.set_xticklabels(names3)
    ax.set_ylabel('Net 3h Glucose Change (mg/dL)')
    ax.set_title('EXP-2233: Post-Meal Net Change by Period')
    ax.axhline(0, color='black', ls='-', alpha=0.3)
    ax.axhline(-20, color='red', ls='--', alpha=0.3, label='Over-bolusing')
    ax.axhline(20, color='orange', ls='--', alpha=0.3, label='Under-bolusing')
    ax.legend(fontsize=8)

    plt.tight_layout()
    plt.savefig(f'{fig_dir}/algo-fig03-cr-periods.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  [fig] algo-fig03-cr-periods.png")

    # Fig 4: DIA Estimation (EXP-2234)
    fig, ax = plt.subplots(figsize=(12, 5))
    r2234 = all_results['exp_2234']
    names4 = sorted([n for n in r2234 if not r2234[n].get('skip', False) and n != '_population'])

    medians = [r2234[n]['median_dia_h'] for n in names4]
    p25s = [r2234[n]['p25_dia_h'] for n in names4]
    p75s = [r2234[n]['p75_dia_h'] for n in names4]

    x = np.arange(len(names4))
    ax.bar(x, medians, color=[colors[i] for i in range(len(names4))], alpha=0.8)
    ax.errorbar(x, medians, yerr=[np.array(medians) - np.array(p25s), np.array(p75s) - np.array(medians)],
                fmt='none', ecolor='black', capsize=3)
    ax.axhline(6.0, color='red', ls='--', label='Profile DIA (6.0h)')
    ax.set_xticks(x)
    ax.set_xticklabels(names4)
    ax.set_ylabel('Effective DIA (hours)')
    ax.set_title('EXP-2234: Effective vs Profile DIA')
    ax.legend()

    plt.tight_layout()
    plt.savefig(f'{fig_dir}/algo-fig04-dia.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  [fig] algo-fig04-dia.png")

    # Fig 5: Quality Score (EXP-2235)
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    r2235 = all_results['exp_2235']
    names5 = sorted([n for n in r2235 if not r2235[n].get('skip', False)])

    scores = [r2235[n]['quality_score'] for n in names5]
    grade_colors = ['#2ecc71' if s >= 80 else '#f39c12' if s >= 65 else '#e74c3c' if s >= 50 else '#c0392b' for s in scores]

    axes[0].bar(np.arange(len(names5)), scores, color=grade_colors, alpha=0.8)
    axes[0].set_xticks(np.arange(len(names5)))
    axes[0].set_xticklabels(names5)
    axes[0].set_ylabel('Quality Score (0-100)')
    axes[0].set_title('EXP-2235: Glucose Quality Score')
    axes[0].axhline(80, color='green', ls='--', alpha=0.3, label='A grade')
    axes[0].axhline(65, color='orange', ls='--', alpha=0.3, label='B grade')
    axes[0].legend()

    # Component breakdown
    components = ['tir_score', 'tbr_score', 'cv_score', 'gvi_score']
    comp_colors = ['#3498db', '#e74c3c', '#f39c12', '#2ecc71']
    bottom = np.zeros(len(names5))
    for comp, cc in zip(components, comp_colors):
        vals = [r2235[n]['components'][comp] for n in names5]
        axes[1].bar(np.arange(len(names5)), vals, bottom=bottom, label=comp.replace('_', ' ').title(), color=cc, alpha=0.8)
        bottom += np.array(vals)
    axes[1].set_xticks(np.arange(len(names5)))
    axes[1].set_xticklabels(names5)
    axes[1].set_ylabel('Score Components')
    axes[1].set_title('EXP-2235: Quality Score Decomposition')
    axes[1].legend(fontsize=8)

    plt.tight_layout()
    plt.savefig(f'{fig_dir}/algo-fig05-quality.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  [fig] algo-fig05-quality.png")

    # Fig 6: Drift Detection (EXP-2236)
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    r2236 = all_results['exp_2236']
    names6 = sorted([n for n in r2236 if not r2236[n].get('skip', False)])

    for i, n in enumerate(names6[:6]):
        data = r2236[n]
        months = [m['month'] for m in data['monthly_data']]
        tirs = [m['tir'] for m in data['monthly_data']]
        axes[0].plot(months, tirs, 'o-', color=colors[i], label=n, linewidth=2)
    axes[0].set_xlabel('Month')
    axes[0].set_ylabel('TIR (%)')
    axes[0].set_title('EXP-2236: TIR Trend Over Time')
    axes[0].legend(fontsize=8)

    for i, n in enumerate(names6[6:], 6):
        data = r2236[n]
        months = [m['month'] for m in data['monthly_data']]
        tirs = [m['tir'] for m in data['monthly_data']]
        axes[1].plot(months, tirs, 'o-', color=colors[i], label=n, linewidth=2)
    axes[1].set_xlabel('Month')
    axes[1].set_ylabel('TIR (%)')
    axes[1].set_title('EXP-2236: TIR Trend (continued)')
    axes[1].legend(fontsize=8)

    plt.tight_layout()
    plt.savefig(f'{fig_dir}/algo-fig06-drift.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  [fig] algo-fig06-drift.png")

    # Fig 7: Risk Decomposition (EXP-2237)
    fig, ax = plt.subplots(figsize=(12, 6))
    r2237 = all_results['exp_2237']
    names7 = sorted([n for n in r2237 if r2237[n].get('n_hypos', 0) > 0])

    cats = ['basal_pct', 'bolus_pct', 'meal_pct', 'unknown_pct']
    cat_labels = ['Basal', 'Bolus', 'Meal', 'Unknown (IOB tail)']
    cat_colors = ['#3498db', '#e74c3c', '#f39c12', '#95a5a6']

    x = np.arange(len(names7))
    bottom = np.zeros(len(names7))
    for cat, cl, cc in zip(cats, cat_labels, cat_colors):
        vals = [r2237[n].get(cat, 0) for n in names7]
        ax.bar(x, vals, bottom=bottom, label=cl, color=cc, alpha=0.8)
        bottom += np.array(vals)
    ax.set_xticks(x)
    ax.set_xticklabels(names7)
    ax.set_ylabel('% of Hypo Events')
    ax.set_title('EXP-2237: Hypoglycemia Risk Decomposition')
    ax.legend()

    plt.tight_layout()
    plt.savefig(f'{fig_dir}/algo-fig07-risk.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  [fig] algo-fig07-risk.png")

    # Fig 8: Recommendation Summary (EXP-2238)
    fig, ax = plt.subplots(figsize=(14, 6))
    r2238 = all_results.get('exp_2238', {})
    # Filter to patient entries only (dicts with 'priority' key)
    names8 = sorted([n for n in r2238 if isinstance(r2238[n], dict) and 'priority' in r2238[n]])

    # Summary table as text figure
    priority_colors = {'CRITICAL': '#c0392b', 'HIGH': '#e74c3c', 'MODERATE': '#f39c12', 'LOW': '#2ecc71'}
    y = len(names8)
    for i, n in enumerate(names8):
        data = r2238[n]
        pc = priority_colors.get(data['priority'], '#95a5a6')
        ax.barh(y - i, data['n_recommendations'], color=pc, alpha=0.8, height=0.6)
        label = f"  {n}: {data['quality_grade']} ({data['quality_score']:.0f}) | TIR={data['tir']:.0f}% TBR={data['tbr']:.1f}% | {data['priority']}"
        ax.text(data['n_recommendations'] + 0.1, y - i, label, va='center', fontsize=9)

    ax.set_ylabel('Patient')
    ax.set_xlabel('Number of Recommendations')
    ax.set_title('EXP-2238: Patient Action Plans')
    ax.set_yticks(range(1, y + 1))
    ax.set_yticklabels(list(reversed(names8)))

    # Legend
    from matplotlib.patches import Patch
    legend_elements = [Patch(facecolor=c, label=l) for l, c in priority_colors.items()]
    ax.legend(handles=legend_elements, loc='lower right')

    plt.tight_layout()
    plt.savefig(f'{fig_dir}/algo-fig08-recommendations.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  [fig] algo-fig08-recommendations.png")


# ─────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description='EXP-2231–2238: Algorithm Recommendations')
    parser.add_argument('--figures', action='store_true', help='Generate figures')
    args = parser.parse_args()

    print("Loading patients...")
    patients = load_patients('externals/ns-data/patients/')
    print(f"  Loaded {len(patients)} patients")

    results = {}
    experiments = [
        ('exp_2231', 'Basal Schedule Generator', lambda p: exp_2231_basal_schedule(p)),
        ('exp_2232', 'ISF Schedule Generator', lambda p: exp_2232_isf_schedule(p)),
        ('exp_2233', 'CR Schedule Generator', lambda p: exp_2233_cr_schedule(p)),
        ('exp_2234', 'DIA Estimation', lambda p: exp_2234_dia_estimation(p)),
        ('exp_2235', 'Glucose Quality Score', lambda p: exp_2235_quality_score(p)),
        ('exp_2236', 'Settings Drift Detection', lambda p: exp_2236_drift_detection(p)),
        ('exp_2237', 'Risk Score Decomposition', lambda p: exp_2237_risk_decomposition(p)),
    ]

    for key, name, func in experiments:
        exp_id = key.replace('exp_', 'EXP-')
        print(f"\n{'=' * 60}")
        print(f"  {exp_id}: {name}")
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

    # EXP-2238 depends on other results
    print(f"\n{'=' * 60}")
    print(f"  EXP-2238: Algorithm Recommendation Summary")
    print(f"{'=' * 60}")
    try:
        results['exp_2238'] = exp_2238_recommendation_summary(patients, results)
        print(f"  ✓ EXP-2238 PASSED")
        for pname, pdata in sorted(results['exp_2238'].items()):
            print(f"    {pname}: grade={pdata['quality_grade']}, priority={pdata['priority']}, recs={pdata['n_recommendations']}")
    except Exception as e:
        print(f"  ✗ EXP-2238 FAILED: {e}")
        import traceback
        traceback.print_exc()
        results['exp_2238'] = {'error': str(e)}

    # Save results
    out_dir = 'externals/experiments'
    os.makedirs(out_dir, exist_ok=True)
    out_file = f'{out_dir}/exp-2231-2238_algo_recs.json'
    with open(out_file, 'w') as f:
        json.dump(results, f, indent=2, cls=NumpyEncoder)
    print(f"\nResults saved to {out_file}")

    if args.figures:
        fig_dir = 'docs/60-research/figures'
        print("\nGenerating figures...")
        generate_figures(results, fig_dir)
        print("All figures generated.")

    print("\n" + "=" * 60)
    print("  SUMMARY: EXP-2231–2238")
    print("=" * 60)
    passed = sum(1 for k in results if 'error' not in results[k])
    print(f"  {passed}/8 experiments passed")

    return results


if __name__ == '__main__':
    main()
