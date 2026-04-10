#!/usr/bin/env python3
"""
EXP-2201–2208: Integrated Settings Recalibration

Combines findings from ~160 prior experiments to generate concrete,
patient-specific AID setting recommendations with confidence intervals.

Experiments:
  2201 - Basal Rate Recalibration (delivery ratio → optimal basal)
  2202 - ISF Recalibration (circadian + dose-dependent)
  2203 - CR Recalibration (absorption phenotype + meal timing)
  2204 - DIA Recalibration (effective vs profile)
  2205 - Target Range Optimization (risk-adjusted targets)
  2206 - Combined Settings Simulation (projected outcomes)
  2207 - Confidence Assessment (data quality + stability)
  2208 - Implementation Priority Matrix (which changes first)

Usage:
    PYTHONPATH=tools python3 tools/cgmencode/exp_settings_recal_2201.py --figures
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

warnings.filterwarnings('ignore')

from cgmencode.exp_metabolic_441 import load_patients

STEPS_PER_HOUR = 12
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
    """Get profile value for a given hour from schedule."""
    if not schedule:
        return None
    sorted_entries = sorted(schedule, key=lambda x: x.get('timeAsSeconds', 0))
    value = sorted_entries[0].get('value', None)
    for entry in sorted_entries:
        t_sec = entry.get('timeAsSeconds', 0)
        if t_sec / 3600 <= hour:
            value = entry.get('value', value)
    return value


def compute_period_stats(df, periods):
    """Compute glucose stats for time-of-day periods."""
    stats = {}
    for name, hours in periods.items():
        mask = df.index.hour.isin(hours)
        g = df.loc[mask, 'glucose']
        if g.notna().sum() < 100:
            continue
        stats[name] = {
            'mean': float(g.mean()),
            'std': float(g.std()),
            'tir': float(((g >= 70) & (g <= 180)).mean()),
            'tbr': float((g < 70).mean()),
            'tar': float((g > 180).mean()),
            'cv': float(g.std() / g.mean()) if g.mean() > 0 else None,
        }
    return stats


def exp_2201_basal_recalibration(patients, save_dir=None):
    """EXP-2201: Recalibrate basal rates using delivery ratio and overnight fasting."""
    print("\n=== EXP-2201: Basal Rate Recalibration ===")
    results = {}

    periods = {
        'night': list(range(0, 6)),
        'morning': list(range(6, 10)),
        'midday': list(range(10, 14)),
        'afternoon': list(range(14, 18)),
        'evening': list(range(18, 22)),
        'late': list(range(22, 24)),
    }

    for p in patients:
        name = p['name']
        df = p['df']
        basal_schedule = df.attrs.get('basal_schedule', [])
        if not basal_schedule:
            print(f"  {name}: no basal schedule, skipping")
            continue

        # Compute delivery ratio per period
        period_data = {}
        for pname, hours in periods.items():
            mask = df.index.hour.isin(hours)
            enacted = df.loc[mask, 'enacted_rate']
            valid = enacted.notna()
            if valid.sum() < 100:
                continue

            # Scheduled basal for this period
            mid_hour = np.mean(hours)
            scheduled = get_profile_value(basal_schedule, mid_hour)
            if not scheduled or scheduled == 0:
                continue

            actual_mean = float(enacted[valid].mean())
            delivery_ratio = actual_mean / scheduled

            # Glucose during this period
            g = df.loc[mask, 'glucose']
            g_mean = float(g.mean()) if g.notna().sum() > 0 else None
            tbr = float((g < 70).mean()) if g.notna().sum() > 0 else None

            # Recommended basal
            if delivery_ratio < 0.3:
                # Loop suspends >70% — basal WAY too high
                recommended = round(scheduled * 0.5, 2)  # Cut in half
            elif delivery_ratio < 0.7:
                # Loop suspends often — reduce
                recommended = round(scheduled * 0.75, 2)
            elif delivery_ratio > 1.5:
                # Loop increases — basal too low
                recommended = round(scheduled * 1.25, 2)
            else:
                recommended = scheduled

            period_data[pname] = {
                'scheduled': round(scheduled, 3),
                'actual_mean': round(actual_mean, 3),
                'delivery_ratio': round(delivery_ratio, 3),
                'recommended': recommended,
                'change_pct': round(100 * (recommended - scheduled) / scheduled, 1),
                'mean_glucose': round(g_mean, 1) if g_mean else None,
                'tbr': round(100 * tbr, 1) if tbr else None,
            }

        # Overall
        enacted_all = df['enacted_rate']
        valid_all = enacted_all.notna()
        if valid_all.sum() > 0:
            scheduled_avg = np.mean([e.get('value', 0) for e in basal_schedule])
            actual_avg = float(enacted_all[valid_all].mean())
            overall_ratio = actual_avg / scheduled_avg if scheduled_avg > 0 else None
        else:
            overall_ratio = None

        results[name] = {
            'overall_delivery_ratio': round(overall_ratio, 3) if overall_ratio else None,
            'periods': period_data,
        }
        print(f"  {name}: delivery_ratio={overall_ratio:.3f}, periods={len(period_data)}" if overall_ratio else f"  {name}: insufficient data")

    if save_dir:
        _save_json(results, save_dir, 'exp-2201_basal_recalibration.json')
    return results


def exp_2202_isf_recalibration(patients, save_dir=None):
    """EXP-2202: Compute circadian ISF with dose-dependent correction."""
    print("\n=== EXP-2202: ISF Recalibration ===")
    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        isf_schedule = df.attrs.get('isf_schedule', [])
        profile_units = df.attrs.get('profile_units', 'mg/dL')

        if not isf_schedule:
            print(f"  {name}: no ISF schedule, skipping")
            continue

        # Get profile ISF (convert if mmol)
        profile_isf = get_profile_value(isf_schedule, 12)
        if profile_isf and profile_isf < 15:
            profile_isf *= 18.0182

        # Find corrections: bolus > 0, no carbs ±30min, glucose > 120
        bolus = df['bolus'].fillna(0)
        carbs = df['carbs'].fillna(0)
        glucose = df['glucose']

        correction_events = []
        bolus_idx = np.where(bolus.values > 0.1)[0]

        for idx in bolus_idx:
            if idx + 36 >= len(df) or idx < 6:
                continue
            g_pre = glucose.iloc[idx]
            if pd.isna(g_pre) or g_pre < 120:
                continue
            # No carbs ±30min
            carb_window = carbs.iloc[max(0, idx-6):idx+6].sum()
            if carb_window > 0:
                continue
            # Glucose 3h later
            g_post = glucose.iloc[idx + 36]
            if pd.isna(g_post):
                continue

            dose = float(bolus.iloc[idx])
            delta = float(g_pre - g_post)
            hour = df.index[idx].hour
            effective_isf = delta / dose if dose > 0 else None

            if effective_isf and 5 < effective_isf < 500:
                correction_events.append({
                    'hour': hour,
                    'dose': dose,
                    'delta': delta,
                    'effective_isf': effective_isf,
                    'g_pre': float(g_pre),
                })

        if len(correction_events) < 10:
            print(f"  {name}: only {len(correction_events)} corrections, skipping")
            results[name] = {'n_corrections': len(correction_events), 'insufficient': True}
            continue

        events_df = pd.DataFrame(correction_events)

        # Circadian ISF: by 4 time periods
        period_isf = {}
        for period, hours in [('night', range(0, 6)), ('morning', range(6, 12)),
                               ('afternoon', range(12, 18)), ('evening', range(18, 24))]:
            mask = events_df['hour'].isin(hours)
            if mask.sum() >= 5:
                isf_vals = events_df.loc[mask, 'effective_isf']
                period_isf[period] = {
                    'n': int(mask.sum()),
                    'median_isf': round(float(isf_vals.median()), 1),
                    'mean_isf': round(float(isf_vals.mean()), 1),
                    'std_isf': round(float(isf_vals.std()), 1),
                    'ci_low': round(float(isf_vals.quantile(0.25)), 1),
                    'ci_high': round(float(isf_vals.quantile(0.75)), 1),
                }

        # Dose-dependent ISF: sublinear model ISF = base * dose^(-alpha)
        doses = events_df['dose'].values
        isfs = events_df['effective_isf'].values
        if len(doses) > 20 and doses.std() > 0.1:
            try:
                log_doses = np.log(doses)
                log_isfs = np.log(isfs)
                valid = np.isfinite(log_doses) & np.isfinite(log_isfs)
                if valid.sum() > 10:
                    slope, intercept = np.polyfit(log_doses[valid], log_isfs[valid], 1)
                    alpha = -slope
                    base_isf = np.exp(intercept)
                    dose_dependent = {
                        'alpha': round(float(alpha), 3),
                        'base_isf': round(float(base_isf), 1),
                        'model': f'ISF = {base_isf:.1f} × dose^(-{alpha:.2f})',
                    }
                else:
                    dose_dependent = None
            except Exception:
                dose_dependent = None
        else:
            dose_dependent = None

        # Overall
        overall_median = float(events_df['effective_isf'].median())
        ratio = overall_median / profile_isf if profile_isf else None

        results[name] = {
            'n_corrections': len(correction_events),
            'profile_isf': round(profile_isf, 1) if profile_isf else None,
            'effective_isf_median': round(overall_median, 1),
            'effective_to_profile_ratio': round(ratio, 2) if ratio else None,
            'circadian_isf': period_isf,
            'dose_dependent': dose_dependent,
        }
        print(f"  {name}: n={len(correction_events)}, profile={profile_isf:.0f}, effective={overall_median:.0f}, ratio={ratio:.2f}x" if ratio else f"  {name}: {len(correction_events)} corrections")

    if save_dir:
        _save_json(results, save_dir, 'exp-2202_isf_recalibration.json')
    return results


def exp_2203_cr_recalibration(patients, save_dir=None):
    """EXP-2203: Recalibrate carb ratios from meal response data."""
    print("\n=== EXP-2203: CR Recalibration ===")
    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        cr_schedule = df.attrs.get('cr_schedule', [])

        profile_cr = get_profile_value(cr_schedule, 12) if cr_schedule else None

        # Find meals: carbs > 0
        carbs = df['carbs'].fillna(0)
        bolus = df['bolus'].fillna(0)
        glucose = df['glucose']

        meal_idx = np.where(carbs.values > 5)[0]  # >5g carbs
        meal_data = []

        for idx in meal_idx:
            if idx + 36 >= len(df) or idx < 6:
                continue
            g_pre = glucose.iloc[idx]
            if pd.isna(g_pre):
                continue
            carb_amt = float(carbs.iloc[idx])
            # Total bolus within ±30min
            bolus_window = bolus.iloc[max(0, idx-6):idx+7].sum()
            if bolus_window < 0.1:
                continue

            # Peak glucose in 2h
            peak_window = glucose.iloc[idx:idx+24]
            if peak_window.notna().sum() < 12:
                continue
            peak = float(peak_window.max())
            spike = peak - float(g_pre)

            # Glucose at 3h
            g_3h = glucose.iloc[idx + 36]
            if pd.isna(g_3h):
                continue
            net_change = float(g_3h) - float(g_pre)

            hour = df.index[idx].hour

            # Effective CR: carbs that would have resulted in flat glucose
            # If net_change > 0 (glucose rose), too few bolus → CR too high
            # If net_change < 0 (glucose fell), too much bolus → CR too low
            if bolus_window > 0:
                actual_cr = carb_amt / float(bolus_window)
                meal_data.append({
                    'hour': hour,
                    'carbs': carb_amt,
                    'bolus': float(bolus_window),
                    'actual_cr': actual_cr,
                    'spike': spike,
                    'net_change': net_change,
                    'g_pre': float(g_pre),
                })

        if len(meal_data) < 10:
            print(f"  {name}: only {len(meal_data)} meals, skipping")
            results[name] = {'n_meals': len(meal_data), 'insufficient': True}
            continue

        meals_df = pd.DataFrame(meal_data)

        # Period-specific CR
        period_cr = {}
        for period, hours in [('breakfast', range(5, 10)), ('lunch', range(10, 15)),
                               ('dinner', range(15, 21)), ('snack', list(range(21, 24)) + list(range(0, 5)))]:
            mask = meals_df['hour'].isin(hours)
            if mask.sum() >= 5:
                cr_vals = meals_df.loc[mask, 'actual_cr']
                spikes = meals_df.loc[mask, 'spike']
                net = meals_df.loc[mask, 'net_change']
                period_cr[period] = {
                    'n': int(mask.sum()),
                    'median_cr': round(float(cr_vals.median()), 1),
                    'mean_spike': round(float(spikes.mean()), 1),
                    'mean_net_change': round(float(net.mean()), 1),
                    'needs_lower_cr': bool(net.mean() > 20),
                    'needs_higher_cr': bool(net.mean() < -20),
                }

        overall_cr = float(meals_df['actual_cr'].median())
        mean_spike = float(meals_df['spike'].mean())
        mean_net = float(meals_df['net_change'].mean())

        results[name] = {
            'n_meals': len(meal_data),
            'profile_cr': round(profile_cr, 1) if profile_cr else None,
            'effective_cr_median': round(overall_cr, 1),
            'mean_spike': round(mean_spike, 1),
            'mean_net_change': round(mean_net, 1),
            'period_cr': period_cr,
            'recommendation': 'lower CR' if mean_net > 20 else ('higher CR' if mean_net < -20 else 'adequate'),
        }
        ratio = overall_cr / profile_cr if profile_cr else None
        print(f"  {name}: profile_cr={profile_cr:.1f}, effective={overall_cr:.1f}, spike={mean_spike:.0f}, net={mean_net:+.0f}" if profile_cr else f"  {name}: {len(meal_data)} meals")

    if save_dir:
        _save_json(results, save_dir, 'exp-2203_cr_recalibration.json')
    return results


def exp_2204_dia_recalibration(patients, save_dir=None):
    """EXP-2204: Estimate effective DIA from isolated corrections."""
    print("\n=== EXP-2204: DIA Recalibration ===")
    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        profile_dia = df.attrs.get('patient_dia', None)

        bolus = df['bolus'].fillna(0)
        carbs = df['carbs'].fillna(0)
        glucose = df['glucose']

        # Find isolated corrections: no carbs ±30min, no other bolus ±4h, glucose > 120
        bolus_idx = np.where(bolus.values > 0.1)[0]
        isolated = []

        for idx in bolus_idx:
            if idx + 60 >= len(df) or idx < 6:
                continue
            # No carbs
            if carbs.iloc[max(0, idx-6):idx+6].sum() > 0:
                continue
            # No other bolus ±4h
            other_bolus = False
            for other_idx in bolus_idx:
                if other_idx != idx and abs(other_idx - idx) < 48:  # 4h
                    other_bolus = True
                    break
            if other_bolus:
                continue

            g_pre = glucose.iloc[idx]
            if pd.isna(g_pre) or g_pre < 120:
                continue

            # Track glucose trajectory over 5h
            trajectory = []
            for t in range(0, 60):  # 5h in 5-min steps
                if idx + t < len(df):
                    g = glucose.iloc[idx + t]
                    if pd.notna(g):
                        trajectory.append((t * 5 / 60, float(g)))  # (hours, glucose)

            if len(trajectory) > 20:
                traj_arr = np.array(trajectory)
                # Find nadir
                nadir_idx = np.argmin(traj_arr[:, 1])
                nadir_time = traj_arr[nadir_idx, 0]
                nadir_glucose = traj_arr[nadir_idx, 1]
                drop = float(g_pre) - nadir_glucose

                # Find 90% recovery
                recovery_target = nadir_glucose + 0.9 * drop
                recovery_time = None
                for ti in range(nadir_idx, len(traj_arr)):
                    if traj_arr[ti, 1] >= recovery_target:
                        recovery_time = traj_arr[ti, 0]
                        break

                isolated.append({
                    'nadir_time_h': nadir_time,
                    'recovery_time_h': recovery_time,
                    'drop': drop,
                    'dose': float(bolus.iloc[idx]),
                })

        if len(isolated) < 3:
            print(f"  {name}: only {len(isolated)} isolated corrections")
            results[name] = {'n_isolated': len(isolated), 'insufficient': True}
            continue

        iso_df = pd.DataFrame(isolated)
        median_nadir = float(iso_df['nadir_time_h'].median())
        recovery_vals = iso_df['recovery_time_h'].dropna()
        median_recovery = float(recovery_vals.median()) if len(recovery_vals) > 0 else None

        results[name] = {
            'n_isolated': len(isolated),
            'profile_dia': profile_dia,
            'effective_nadir_h': round(median_nadir, 1),
            'effective_dia_h': round(median_recovery, 1) if median_recovery else None,
            'dia_mismatch': round(median_recovery - profile_dia, 1) if median_recovery and profile_dia else None,
        }
        print(f"  {name}: n={len(isolated)}, profile_DIA={profile_dia}h, effective={median_recovery:.1f}h" if median_recovery else f"  {name}: n={len(isolated)}")

    if save_dir:
        _save_json(results, save_dir, 'exp-2204_dia_recalibration.json')
    return results


def exp_2205_target_optimization(patients, save_dir=None):
    """EXP-2205: Risk-adjusted target range optimization."""
    print("\n=== EXP-2205: Target Range Optimization ===")
    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose']

        if glucose.notna().sum() < 1000:
            continue

        # Current performance
        g = glucose.dropna()
        current_tir = float(((g >= 70) & (g <= 180)).mean())
        current_tbr = float((g < 70).mean())
        current_tar = float((g > 180).mean())
        current_mean = float(g.mean())
        current_cv = float(g.std() / g.mean())

        # Glucose distribution analysis
        p10 = float(g.quantile(0.10))
        p25 = float(g.quantile(0.25))
        p50 = float(g.quantile(0.50))
        p75 = float(g.quantile(0.75))
        p90 = float(g.quantile(0.90))

        # Risk-adjusted target
        # If TBR > 4%, raise target; if TAR > 25%, lower target
        if current_tbr > 0.04:
            suggested_low = 80
            suggested_target = max(100, round(p50 + 10))
        elif current_tar > 0.25:
            suggested_low = 70
            suggested_target = min(120, round(p50 - 10))
        else:
            suggested_low = 75
            suggested_target = round(p50)

        # How many hypos would a higher target prevent?
        # If target raised by 10, estimate how many hypo events start from 70-80 range
        g_marginal = ((g >= 60) & (g < 80)).sum()
        total_hypo_events = (g < 70).sum()

        results[name] = {
            'current_tir': round(100 * current_tir, 1),
            'current_tbr': round(100 * current_tbr, 1),
            'current_tar': round(100 * current_tar, 1),
            'current_mean': round(current_mean, 1),
            'current_cv': round(current_cv, 3),
            'p10': round(p10, 1),
            'p50': round(p50, 1),
            'p90': round(p90, 1),
            'suggested_target': suggested_target,
            'suggested_low': suggested_low,
            'marginal_hypo_readings': int(g_marginal),
        }
        print(f"  {name}: TIR={100*current_tir:.1f}%, TBR={100*current_tbr:.1f}%, target→{suggested_target}")

    if save_dir:
        _save_json(results, save_dir, 'exp-2205_target_optimization.json')
    return results


def exp_2206_combined_simulation(patients, save_dir=None):
    """EXP-2206: Simulate projected outcomes with recalibrated settings."""
    print("\n=== EXP-2206: Combined Settings Simulation ===")
    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        basal_schedule = df.attrs.get('basal_schedule', [])
        isf_schedule = df.attrs.get('isf_schedule', [])
        cr_schedule = df.attrs.get('cr_schedule', [])

        glucose = df['glucose']
        enacted = df['enacted_rate']
        bolus = df['bolus'].fillna(0)
        carbs = df['carbs'].fillna(0)

        if glucose.notna().sum() < 1000 or enacted.notna().sum() < 1000:
            continue

        # Current stats
        g = glucose.dropna()
        current_tir = float(((g >= 70) & (g <= 180)).mean())
        current_tbr = float((g < 70).mean())

        # Compute what would change with:
        # 1. Basal reduction (delivery_ratio approach)
        valid_enacted = enacted.notna()
        if valid_enacted.sum() > 0 and basal_schedule:
            sched_mean = np.mean([e.get('value', 0) for e in basal_schedule])
            actual_mean = float(enacted[valid_enacted].mean())
            delivery_ratio = actual_mean / sched_mean if sched_mean > 0 else 1
            basal_reduction = max(0.5, min(1.0, delivery_ratio * 1.5))
        else:
            delivery_ratio = 1
            basal_reduction = 1

        # 2. ISF correction factor
        profile_isf = get_profile_value(isf_schedule, 12) if isf_schedule else None
        if profile_isf and profile_isf < 15:
            profile_isf *= 18.0182

        # Find effective ISF from corrections
        bolus_idx = np.where(bolus.values > 0.1)[0]
        isf_ratios = []
        for idx in bolus_idx[:500]:
            if idx + 36 >= len(df) or idx < 6:
                continue
            g_pre = glucose.iloc[idx]
            if pd.isna(g_pre) or g_pre < 150:
                continue
            if carbs.iloc[max(0, idx-6):idx+6].sum() > 0:
                continue
            g_post = glucose.iloc[idx + 36]
            if pd.isna(g_post):
                continue
            actual_drop = float(g_pre - g_post)
            expected_drop = float(bolus.iloc[idx]) * (profile_isf or 50)
            if expected_drop > 0:
                isf_ratios.append(actual_drop / expected_drop)

        isf_correction = float(np.median(isf_ratios)) if len(isf_ratios) > 5 else 1.0

        # Projected improvement estimates (conservative)
        # TBR reduction: basal reduction removes unnecessary insulin
        tbr_reduction_est = min(0.7, basal_reduction) * current_tbr if basal_reduction < 1 else current_tbr
        # TIR improvement: better ISF + basal → less overshoot
        tir_improvement_est = min(0.05, (1 - current_tir) * 0.3)

        results[name] = {
            'current_tir': round(100 * current_tir, 1),
            'current_tbr': round(100 * current_tbr, 1),
            'delivery_ratio': round(delivery_ratio, 3),
            'basal_reduction_factor': round(basal_reduction, 2),
            'isf_correction_factor': round(isf_correction, 2),
            'n_isf_events': len(isf_ratios),
            'projected_tbr': round(100 * tbr_reduction_est, 1),
            'projected_tir': round(100 * (current_tir + tir_improvement_est), 1),
            'projected_tbr_reduction': round(100 * (current_tbr - tbr_reduction_est), 1),
        }
        print(f"  {name}: TBR {100*current_tbr:.1f}%→{100*tbr_reduction_est:.1f}%, TIR {100*current_tir:.1f}%→{100*(current_tir+tir_improvement_est):.1f}%")

    if save_dir:
        _save_json(results, save_dir, 'exp-2206_simulation.json')
    return results


def exp_2207_confidence(patients, save_dir=None):
    """EXP-2207: Assess confidence in each recommendation."""
    print("\n=== EXP-2207: Confidence Assessment ===")
    results = {}

    for p in patients:
        name = p['name']
        df = p['df']

        glucose = df['glucose']
        enacted = df['enacted_rate']
        bolus = df['bolus'].fillna(0)

        # Data quality metrics
        cgm_coverage = float(glucose.notna().mean())
        loop_coverage = float(enacted.notna().mean())
        total_days = len(df) / (288)
        bolus_count = int((bolus > 0).sum())

        # Temporal stability: compare first half vs second half
        mid = len(df) // 2
        g_first = glucose.iloc[:mid].dropna()
        g_second = glucose.iloc[mid:].dropna()

        if len(g_first) > 100 and len(g_second) > 100:
            tir_first = float(((g_first >= 70) & (g_first <= 180)).mean())
            tir_second = float(((g_second >= 70) & (g_second <= 180)).mean())
            tir_stability = abs(tir_first - tir_second)
            mean_stability = abs(float(g_first.mean()) - float(g_second.mean()))
        else:
            tir_stability = None
            mean_stability = None

        # Confidence score
        score = 0
        if cgm_coverage > 0.7: score += 1
        if cgm_coverage > 0.9: score += 1
        if loop_coverage > 0.7: score += 1
        if total_days > 60: score += 1
        if total_days > 120: score += 1
        if bolus_count > 100: score += 1
        if tir_stability and tir_stability < 0.05: score += 1
        if mean_stability and mean_stability < 10: score += 1

        confidence = 'HIGH' if score >= 6 else ('MEDIUM' if score >= 4 else 'LOW')

        results[name] = {
            'cgm_coverage': round(cgm_coverage, 3),
            'loop_coverage': round(loop_coverage, 3),
            'total_days': round(total_days, 1),
            'bolus_count': bolus_count,
            'tir_stability': round(tir_stability, 3) if tir_stability is not None else None,
            'mean_stability': round(mean_stability, 1) if mean_stability is not None else None,
            'confidence_score': score,
            'confidence': confidence,
        }
        print(f"  {name}: CGM={cgm_coverage:.1%}, days={total_days:.0f}, stability={tir_stability:.3f}, confidence={confidence}" if tir_stability else f"  {name}: confidence={confidence}")

    if save_dir:
        _save_json(results, save_dir, 'exp-2207_confidence.json')
    return results


def exp_2208_priority_matrix(patients, all_results, save_dir=None):
    """EXP-2208: Implementation priority matrix — what to change first."""
    print("\n=== EXP-2208: Implementation Priority Matrix ===")
    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose']

        if glucose.notna().sum() < 1000:
            continue

        g = glucose.dropna()
        tbr = float((g < 70).mean())
        tir = float(((g >= 70) & (g <= 180)).mean())
        tar = float((g > 180).mean())

        interventions = []

        # 1. Basal adjustment
        basal_data = all_results.get('exp_2201', {}).get(name, {})
        delivery_ratio = basal_data.get('overall_delivery_ratio', 1)
        if delivery_ratio and delivery_ratio < 0.5:
            interventions.append({
                'setting': 'basal',
                'priority': 'HIGH',
                'rationale': f'Loop suspends {100*(1-delivery_ratio):.0f}% — basal ~{1/delivery_ratio:.1f}× too high',
                'expected_impact': 'Reduce TBR by 30-50%',
                'risk': 'LOW',
            })
        elif delivery_ratio and delivery_ratio < 0.8:
            interventions.append({
                'setting': 'basal',
                'priority': 'MEDIUM',
                'rationale': f'Loop suspends {100*(1-delivery_ratio):.0f}% — basal needs reduction',
                'expected_impact': 'Reduce TBR by 10-30%',
                'risk': 'LOW',
            })

        # 2. ISF adjustment
        isf_data = all_results.get('exp_2202', {}).get(name, {})
        isf_ratio = isf_data.get('effective_to_profile_ratio')
        if isf_ratio and (isf_ratio > 1.5 or isf_ratio < 0.7):
            direction = 'too low' if isf_ratio > 1 else 'too high'
            interventions.append({
                'setting': 'ISF',
                'priority': 'HIGH' if abs(isf_ratio - 1) > 0.5 else 'MEDIUM',
                'rationale': f'Profile ISF {direction} (effective/profile = {isf_ratio:.2f}×)',
                'expected_impact': 'Improve correction accuracy',
                'risk': 'MEDIUM',
            })

        # 3. CR adjustment
        cr_data = all_results.get('exp_2203', {}).get(name, {})
        mean_spike = cr_data.get('mean_spike')
        mean_net = cr_data.get('mean_net_change')
        if mean_net and abs(mean_net) > 30:
            direction = 'lower' if mean_net > 0 else 'higher'
            interventions.append({
                'setting': 'CR',
                'priority': 'MEDIUM',
                'rationale': f'Post-meal net change {mean_net:+.0f} mg/dL — CR too {direction}',
                'expected_impact': 'Reduce post-meal excursions',
                'risk': 'MEDIUM',
            })

        # Safety priority
        if tbr > 0.04:
            safety = 'CRITICAL'
        elif tbr > 0.02:
            safety = 'MODERATE'
        else:
            safety = 'LOW'

        # Sort interventions by priority
        priority_order = {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2}
        interventions.sort(key=lambda x: priority_order.get(x['priority'], 3))

        results[name] = {
            'current_tbr': round(100 * tbr, 1),
            'current_tir': round(100 * tir, 1),
            'safety_priority': safety,
            'n_interventions': len(interventions),
            'interventions': interventions,
            'first_action': interventions[0]['setting'] if interventions else 'none',
        }
        print(f"  {name}: safety={safety}, {len(interventions)} interventions, first={interventions[0]['setting'] if interventions else 'none'}")

    if save_dir:
        _save_json(results, save_dir, 'exp-2208_priority_matrix.json')
    return results


def _save_json(data, save_dir, filename):
    path = os.path.join(save_dir, filename)
    os.makedirs(save_dir, exist_ok=True)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2, cls=NumpyEncoder)
    print(f"  Saved {path}")


def generate_figures(all_results, fig_dir):
    """Generate 8 figures for settings recalibration."""
    os.makedirs(fig_dir, exist_ok=True)

    # Fig 1: Basal Delivery Ratio
    r2201 = all_results.get('exp_2201', {})
    if r2201:
        fig, axes = plt.subplots(1, 2, figsize=(16, 6))
        names = sorted([n for n in r2201 if r2201[n].get('overall_delivery_ratio')])
        ratios = [r2201[n]['overall_delivery_ratio'] for n in names]

        colors = ['#d62728' if r < 0.3 else '#ff7f0e' if r < 0.7 else '#2ca02c' if r <= 1.3 else '#1f77b4' for r in ratios]
        axes[0].barh(names, ratios, color=colors)
        axes[0].axvline(1.0, color='k', linestyle='--', alpha=0.5, label='Optimal')
        axes[0].set_xlabel('Delivery Ratio (actual/scheduled)')
        axes[0].set_title('Overall Basal Delivery Ratio')
        axes[0].legend()

        # Period breakdown for selected patients
        for idx, n in enumerate(names[:6]):
            periods = r2201[n].get('periods', {})
            if periods:
                p_names = list(periods.keys())
                p_ratios = [periods[pn]['delivery_ratio'] for pn in p_names]
                axes[1].plot(p_names, p_ratios, 'o-', label=n, alpha=0.7)
        axes[1].axhline(1.0, color='k', linestyle='--', alpha=0.3)
        axes[1].set_ylabel('Delivery Ratio')
        axes[1].set_title('Period-Specific Delivery Ratios')
        axes[1].legend(fontsize=7)
        axes[1].tick_params(axis='x', rotation=30)

        plt.suptitle('EXP-2201: Basal Rate Recalibration', fontsize=14, fontweight='bold')
        plt.tight_layout()
        plt.savefig(os.path.join(fig_dir, 'recal-fig01-basal.png'), dpi=150)
        plt.close()
        print("  Fig 1: Basal recalibration")

    # Fig 2: ISF Profile vs Effective
    r2202 = all_results.get('exp_2202', {})
    if r2202:
        fig, axes = plt.subplots(1, 2, figsize=(16, 6))
        names = sorted([n for n in r2202 if not r2202[n].get('insufficient')])

        profile_vals = [r2202[n].get('profile_isf', 0) or 0 for n in names]
        effective_vals = [r2202[n].get('effective_isf_median', 0) for n in names]

        x = np.arange(len(names))
        axes[0].bar(x - 0.2, profile_vals, 0.35, label='Profile ISF', color='#1f77b4')
        axes[0].bar(x + 0.2, effective_vals, 0.35, label='Effective ISF', color='#ff7f0e')
        axes[0].set_xticks(x)
        axes[0].set_xticklabels(names)
        axes[0].set_ylabel('ISF (mg/dL per U)')
        axes[0].set_title('Profile vs Effective ISF')
        axes[0].legend()

        # Circadian ISF for selected patients
        for n in names[:4]:
            circ = r2202[n].get('circadian_isf', {})
            if circ:
                periods = ['night', 'morning', 'afternoon', 'evening']
                vals = [circ.get(p, {}).get('median_isf', None) for p in periods]
                if all(v is not None for v in vals):
                    axes[1].plot(periods, vals, 'o-', label=n, alpha=0.7)
        axes[1].set_ylabel('ISF (mg/dL per U)')
        axes[1].set_title('Circadian ISF Variation')
        axes[1].legend()
        axes[1].tick_params(axis='x', rotation=30)

        plt.suptitle('EXP-2202: ISF Recalibration', fontsize=14, fontweight='bold')
        plt.tight_layout()
        plt.savefig(os.path.join(fig_dir, 'recal-fig02-isf.png'), dpi=150)
        plt.close()
        print("  Fig 2: ISF recalibration")

    # Fig 3: CR Recalibration
    r2203 = all_results.get('exp_2203', {})
    if r2203:
        fig, axes = plt.subplots(1, 2, figsize=(16, 6))
        names = sorted([n for n in r2203 if not r2203[n].get('insufficient')])

        spikes = [r2203[n].get('mean_spike', 0) for n in names]
        nets = [r2203[n].get('mean_net_change', 0) for n in names]

        colors_spike = ['#d62728' if s > 60 else '#ff7f0e' if s > 30 else '#2ca02c' for s in spikes]
        axes[0].barh(names, spikes, color=colors_spike)
        axes[0].set_xlabel('Mean Post-Meal Spike (mg/dL)')
        axes[0].set_title('Meal Spike Magnitude')
        axes[0].axvline(30, color='k', linestyle='--', alpha=0.3, label='Target <30')

        colors_net = ['#d62728' if abs(n) > 30 else '#2ca02c' for n in nets]
        axes[1].barh(names, nets, color=colors_net)
        axes[1].set_xlabel('Net 3h Change (mg/dL)')
        axes[1].set_title('Post-Meal Net Change (0 = perfect)')
        axes[1].axvline(0, color='k', linewidth=1)

        plt.suptitle('EXP-2203: CR Recalibration', fontsize=14, fontweight='bold')
        plt.tight_layout()
        plt.savefig(os.path.join(fig_dir, 'recal-fig03-cr.png'), dpi=150)
        plt.close()
        print("  Fig 3: CR recalibration")

    # Fig 4: DIA Profile vs Effective
    r2204 = all_results.get('exp_2204', {})
    if r2204:
        fig, ax = plt.subplots(figsize=(12, 6))
        names = sorted([n for n in r2204 if not r2204[n].get('insufficient')])

        profile_dias = [r2204[n].get('profile_dia', 0) or 0 for n in names]
        effective_dias = [r2204[n].get('effective_dia_h', 0) or 0 for n in names]
        nadir_times = [r2204[n].get('effective_nadir_h', 0) or 0 for n in names]

        x = np.arange(len(names))
        ax.bar(x - 0.25, profile_dias, 0.25, label='Profile DIA', color='#1f77b4')
        ax.bar(x, effective_dias, 0.25, label='Effective DIA', color='#ff7f0e')
        ax.bar(x + 0.25, nadir_times, 0.25, label='Nadir Time', color='#2ca02c')
        ax.set_xticks(x)
        ax.set_xticklabels(names)
        ax.set_ylabel('Hours')
        ax.set_title('EXP-2204: DIA — Profile vs Effective')
        ax.legend()

        plt.tight_layout()
        plt.savefig(os.path.join(fig_dir, 'recal-fig04-dia.png'), dpi=150)
        plt.close()
        print("  Fig 4: DIA recalibration")

    # Fig 5: Target Optimization
    r2205 = all_results.get('exp_2205', {})
    if r2205:
        fig, axes = plt.subplots(1, 2, figsize=(16, 6))
        names = sorted(r2205.keys())

        tbrs = [r2205[n]['current_tbr'] for n in names]
        tirs = [r2205[n]['current_tir'] for n in names]
        tars = [r2205[n]['current_tar'] for n in names]

        x = np.arange(len(names))
        axes[0].bar(x, tbrs, color='#d62728', label='TBR', alpha=0.8)
        axes[0].bar(x, tirs, bottom=tbrs, color='#2ca02c', label='TIR', alpha=0.8)
        bars_tar = [tbrs[i] + tirs[i] for i in range(len(names))]
        axes[0].bar(x, tars, bottom=bars_tar, color='#ff7f0e', label='TAR', alpha=0.8)
        axes[0].set_xticks(x)
        axes[0].set_xticklabels(names)
        axes[0].set_ylabel('%')
        axes[0].set_title('Current Glucose Distribution')
        axes[0].legend()

        # Suggested targets
        targets = [r2205[n]['suggested_target'] for n in names]
        p50s = [r2205[n]['p50'] for n in names]
        axes[1].bar(x - 0.2, p50s, 0.35, label='Median Glucose', color='#1f77b4')
        axes[1].bar(x + 0.2, targets, 0.35, label='Suggested Target', color='#2ca02c')
        axes[1].set_xticks(x)
        axes[1].set_xticklabels(names)
        axes[1].set_ylabel('mg/dL')
        axes[1].set_title('Target Optimization')
        axes[1].legend()

        plt.suptitle('EXP-2205: Target Range Optimization', fontsize=14, fontweight='bold')
        plt.tight_layout()
        plt.savefig(os.path.join(fig_dir, 'recal-fig05-targets.png'), dpi=150)
        plt.close()
        print("  Fig 5: Target optimization")

    # Fig 6: Combined Simulation
    r2206 = all_results.get('exp_2206', {})
    if r2206:
        fig, axes = plt.subplots(1, 2, figsize=(16, 6))
        names = sorted(r2206.keys())

        current_tbr = [r2206[n]['current_tbr'] for n in names]
        projected_tbr = [r2206[n]['projected_tbr'] for n in names]
        current_tir = [r2206[n]['current_tir'] for n in names]
        projected_tir = [r2206[n]['projected_tir'] for n in names]

        x = np.arange(len(names))
        axes[0].bar(x - 0.2, current_tbr, 0.35, label='Current TBR', color='#d62728', alpha=0.7)
        axes[0].bar(x + 0.2, projected_tbr, 0.35, label='Projected TBR', color='#ff7f0e', alpha=0.7)
        axes[0].axhline(4, color='k', linestyle='--', alpha=0.3, label='TBR <4% target')
        axes[0].set_xticks(x)
        axes[0].set_xticklabels(names)
        axes[0].set_ylabel('TBR (%)')
        axes[0].set_title('TBR: Current vs Projected')
        axes[0].legend()

        axes[1].bar(x - 0.2, current_tir, 0.35, label='Current TIR', color='#2ca02c', alpha=0.7)
        axes[1].bar(x + 0.2, projected_tir, 0.35, label='Projected TIR', color='#1f77b4', alpha=0.7)
        axes[1].axhline(70, color='k', linestyle='--', alpha=0.3, label='TIR ≥70% target')
        axes[1].set_xticks(x)
        axes[1].set_xticklabels(names)
        axes[1].set_ylabel('TIR (%)')
        axes[1].set_title('TIR: Current vs Projected')
        axes[1].legend()

        plt.suptitle('EXP-2206: Combined Settings Simulation', fontsize=14, fontweight='bold')
        plt.tight_layout()
        plt.savefig(os.path.join(fig_dir, 'recal-fig06-simulation.png'), dpi=150)
        plt.close()
        print("  Fig 6: Simulation")

    # Fig 7: Confidence Assessment
    r2207 = all_results.get('exp_2207', {})
    if r2207:
        fig, ax = plt.subplots(figsize=(12, 7))
        names = sorted(r2207.keys())
        scores = [r2207[n]['confidence_score'] for n in names]
        confidence = [r2207[n]['confidence'] for n in names]
        colors = ['#2ca02c' if c == 'HIGH' else '#ff7f0e' if c == 'MEDIUM' else '#d62728' for c in confidence]

        ax.barh(names, scores, color=colors)
        for i, (n, s, c) in enumerate(zip(names, scores, confidence)):
            ax.text(s + 0.1, i, f'{c} ({s}/8)', va='center', fontsize=10)
        ax.set_xlabel('Confidence Score (max 8)')
        ax.set_title('EXP-2207: Data Quality & Recommendation Confidence')
        ax.set_xlim(0, 10)

        plt.tight_layout()
        plt.savefig(os.path.join(fig_dir, 'recal-fig07-confidence.png'), dpi=150)
        plt.close()
        print("  Fig 7: Confidence")

    # Fig 8: Priority Matrix
    r2208 = all_results.get('exp_2208', {})
    if r2208:
        fig, ax = plt.subplots(figsize=(14, 8))
        names = sorted(r2208.keys())

        y_pos = 0
        yticks = []
        ylabels = []
        priority_colors = {'HIGH': '#d62728', 'MEDIUM': '#ff7f0e', 'LOW': '#2ca02c'}

        for n in names:
            interventions = r2208[n].get('interventions', [])
            safety = r2208[n].get('safety_priority', 'LOW')
            for intv in interventions:
                color = priority_colors.get(intv['priority'], '#999999')
                ax.barh(y_pos, 1, color=color, alpha=0.8)
                ax.text(1.05, y_pos, f"{intv['setting']}: {intv['rationale'][:60]}",
                       va='center', fontsize=7)
                yticks.append(y_pos)
                ylabels.append(f"{n}")
                y_pos += 1
            if not interventions:
                ax.barh(y_pos, 0.1, color='#2ca02c', alpha=0.3)
                ax.text(0.15, y_pos, 'No changes needed', va='center', fontsize=7)
                yticks.append(y_pos)
                ylabels.append(f"{n}")
                y_pos += 1
            y_pos += 0.5  # gap between patients

        ax.set_yticks(yticks)
        ax.set_yticklabels(ylabels, fontsize=8)
        ax.set_xlim(0, 5)
        ax.set_title('EXP-2208: Implementation Priority Matrix')

        # Legend
        for priority, color in priority_colors.items():
            ax.barh([], [], color=color, label=priority)
        ax.legend(loc='upper right')

        plt.tight_layout()
        plt.savefig(os.path.join(fig_dir, 'recal-fig08-priorities.png'), dpi=150)
        plt.close()
        print("  Fig 8: Priority matrix")


def main():
    parser = argparse.ArgumentParser(description='EXP-2201–2208: Settings Recalibration')
    parser.add_argument('--figures', action='store_true')
    parser.add_argument('--data-dir', default='externals/ns-data/patients/')
    parser.add_argument('--save-dir', default='externals/experiments/')
    parser.add_argument('--fig-dir', default='docs/60-research/figures/')
    args = parser.parse_args()

    print("Loading patient data...")
    patients = load_patients(args.data_dir)
    print(f"Loaded {len(patients)} patients\n")

    all_results = {}

    all_results['exp_2201'] = exp_2201_basal_recalibration(patients, args.save_dir)
    all_results['exp_2202'] = exp_2202_isf_recalibration(patients, args.save_dir)
    all_results['exp_2203'] = exp_2203_cr_recalibration(patients, args.save_dir)
    all_results['exp_2204'] = exp_2204_dia_recalibration(patients, args.save_dir)
    all_results['exp_2205'] = exp_2205_target_optimization(patients, args.save_dir)
    all_results['exp_2206'] = exp_2206_combined_simulation(patients, args.save_dir)
    all_results['exp_2207'] = exp_2207_confidence(patients, args.save_dir)
    all_results['exp_2208'] = exp_2208_priority_matrix(patients, all_results, args.save_dir)

    if args.figures:
        print("\n=== Generating Figures ===")
        generate_figures(all_results, args.fig_dir)

    print("\n=== All 8 experiments complete ===")


if __name__ == '__main__':
    main()
