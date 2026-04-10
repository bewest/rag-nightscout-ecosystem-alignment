#!/usr/bin/env python3
"""
EXP-2151–2158: Meal Response Personalization & Carb Absorption

Characterize individual meal absorption dynamics, timing, and responses
to inform personalized CR and pre-bolus timing recommendations.

EXP-2151: Individual meal absorption curves — per-patient glucose excursion profiles
EXP-2152: Meal size effects — do larger meals produce proportionally larger spikes?
EXP-2153: Pre-bolus timing impact — does bolus-to-meal timing affect excursion?
EXP-2154: Meal-period glucose signatures — breakfast vs lunch vs dinner response shape
EXP-2155: Post-meal nadir analysis — when does the post-meal low occur?
EXP-2156: Carb-to-spike correlation — how well do carbs predict spike magnitude?
EXP-2157: Fat/protein effect proxy — do meals with similar carbs but different spikes
          suggest composition effects?
EXP-2158: Personalized CR recommendations — per-patient, per-meal-period CR with CI

Depends on: exp_metabolic_441.py
"""

import json
import sys
import os
import numpy as np
import warnings
warnings.filterwarnings('ignore')

from exp_metabolic_441 import load_patients, compute_supply_demand


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


PATIENT_DIR = 'externals/ns-data/patients/'
FIG_DIR = 'docs/60-research/figures'
EXP_DIR = 'externals/experiments'
MAKE_FIGS = '--figures' in sys.argv

if MAKE_FIGS:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    os.makedirs(FIG_DIR, exist_ok=True)

os.makedirs(EXP_DIR, exist_ok=True)

STEPS_PER_HOUR = 12
STEPS_PER_DAY = 288

patients = load_patients(PATIENT_DIR)


def get_profile_value(schedule, hour):
    """Get profile value for a given hour from list-of-dicts schedule."""
    if not schedule:
        return None
    sorted_sched = sorted(schedule, key=lambda x: x.get('timeAsSeconds', 0))
    result = sorted_sched[0].get('value', None)
    target_seconds = hour * 3600
    for entry in sorted_sched:
        if entry.get('timeAsSeconds', 0) <= target_seconds:
            result = entry.get('value', result)
    return result


def find_meals(g, carbs, bolus, min_carbs=5):
    """Find meal events with sufficient post-meal glucose data."""
    meals = []
    for t in range(STEPS_PER_HOUR, len(g) - 4 * STEPS_PER_HOUR):
        if np.isnan(carbs[t]) or carbs[t] < min_carbs:
            continue
        # Check for sufficient glucose data in 4h window
        post_g = g[t:t + 4 * STEPS_PER_HOUR]
        if np.sum(np.isnan(post_g)) > len(post_g) * 0.3:
            continue
        # Skip if another meal within 2h
        other_carbs = np.nansum(carbs[t+1:min(t + 2 * STEPS_PER_HOUR, len(carbs))])
        if other_carbs > min_carbs:
            continue

        hour = (t % STEPS_PER_DAY) / STEPS_PER_HOUR
        pre_g = g[max(0, t-3):t+1]
        pre_glucose = float(np.nanmean(pre_g)) if np.any(~np.isnan(pre_g)) else np.nan

        # Bolus associated with meal (within ±30 min)
        meal_bolus = float(np.nansum(bolus[max(0, t-6):min(t+6, len(bolus))]))

        # Pre-bolus timing: bolus before carbs?
        pre_bolus_steps = 0
        for pb in range(max(0, t-6), t):
            if not np.isnan(bolus[pb]) and bolus[pb] > 0.3:
                pre_bolus_steps = t - pb
                break

        meals.append({
            'step': t,
            'hour': float(hour),
            'carbs': float(carbs[t]),
            'bolus': meal_bolus,
            'pre_glucose': pre_glucose,
            'pre_bolus_steps': pre_bolus_steps,
            'post_glucose': post_g.tolist()
        })
    return meals


# ── EXP-2151: Individual Meal Absorption Curves ─────────────────────
def exp_2151_absorption_curves():
    """Per-patient average glucose excursion profile after meals."""
    print("\n═══ EXP-2151: Individual Meal Absorption Curves ═══")

    all_results = {}
    window = 4 * STEPS_PER_HOUR  # 4 hours post-meal

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        carbs_arr = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(g))
        bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(len(g))

        meals = find_meals(g, carbs_arr, bolus)
        if len(meals) < 10:
            print(f"  {name}: insufficient meals ({len(meals)})")
            continue

        # Compute mean excursion curve (delta from pre-meal glucose)
        excursions = []
        for m in meals:
            post = np.array(m['post_glucose'])
            delta = post - m['pre_glucose']
            if len(delta) == window:
                excursions.append(delta)

        if not excursions:
            continue

        excursion_arr = np.array(excursions)
        mean_curve = np.nanmean(excursion_arr, axis=0)
        std_curve = np.nanstd(excursion_arr, axis=0)
        median_curve = np.nanmedian(excursion_arr, axis=0)

        # Peak metrics
        peak_idx = np.nanargmax(mean_curve)
        peak_time_min = peak_idx * 5
        peak_rise = float(mean_curve[peak_idx])

        # Time to return to baseline
        baseline_cross = window
        for i in range(peak_idx, len(mean_curve)):
            if mean_curve[i] <= 0:
                baseline_cross = i
                break
        return_time_min = baseline_cross * 5

        # Area under the curve (excursion AUC, first 3h)
        auc_3h = float(np.nansum(mean_curve[:36]) * 5)  # mg·min/dL

        all_results[name] = {
            'n_meals': len(meals),
            'n_excursions': len(excursions),
            'peak_time_min': peak_time_min,
            'peak_rise_mgdl': peak_rise,
            'return_to_baseline_min': return_time_min,
            'auc_3h': auc_3h,
            'mean_curve': mean_curve.tolist(),
            'std_curve': std_curve.tolist(),
            'median_curve': median_curve.tolist()
        }

        print(f"  {name}: {len(excursions)} meals, peak +{peak_rise:.0f} mg/dL "
              f"at {peak_time_min}min, return {return_time_min}min, "
              f"AUC={auc_3h:.0f} mg·min/dL")

    with open(f'{EXP_DIR}/exp-2151_absorption_curves.json', 'w') as f:
        json.dump(all_results, f, indent=2, cls=NumpyEncoder)

    if MAKE_FIGS and all_results:
        fig, axes = plt.subplots(1, 3, figsize=(16, 5))

        patient_names = sorted(all_results.keys())
        time_axis = np.arange(window) * 5  # minutes

        # Panel 1: All mean curves overlaid
        for pn in patient_names:
            curve = all_results[pn]['mean_curve']
            axes[0].plot(time_axis[:len(curve)], curve, '-', label=pn, alpha=0.7)
        axes[0].axhline(y=0, color='black', linewidth=0.5)
        axes[0].set_xlabel('Minutes Post-Meal')
        axes[0].set_ylabel('Glucose Δ (mg/dL)')
        axes[0].set_title('Mean Post-Meal Excursion')
        axes[0].legend(fontsize=7, ncol=2)
        axes[0].grid(True, alpha=0.3)

        # Panel 2: Peak rise vs peak time
        peaks = [all_results[pn]['peak_rise_mgdl'] for pn in patient_names]
        times = [all_results[pn]['peak_time_min'] for pn in patient_names]
        axes[1].scatter(times, peaks, s=100, c='coral', edgecolors='black', zorder=3)
        for i, pn in enumerate(patient_names):
            axes[1].annotate(pn, (times[i], peaks[i]),
                             textcoords="offset points", xytext=(5, 5), fontsize=8)
        axes[1].set_xlabel('Peak Time (min)')
        axes[1].set_ylabel('Peak Rise (mg/dL)')
        axes[1].set_title('Peak Timing vs Magnitude')
        axes[1].grid(True, alpha=0.3)

        # Panel 3: AUC comparison
        aucs = [all_results[pn]['auc_3h'] for pn in patient_names]
        colors_auc = ['green' if a < 3000 else 'orange' if a < 5000 else 'red' for a in aucs]
        axes[2].bar(patient_names, aucs, color=colors_auc, alpha=0.7)
        axes[2].set_ylabel('3h Excursion AUC (mg·min/dL)')
        axes[2].set_title('Meal Excursion Burden')
        axes[2].tick_params(axis='x', labelsize=8)
        axes[2].grid(True, alpha=0.3, axis='y')

        plt.tight_layout()
        plt.savefig(f'{FIG_DIR}/meal-fig01-absorption.png', dpi=150)
        plt.close()
        print("  → Saved meal-fig01-absorption.png")

    return all_results


# ── EXP-2152: Meal Size Effects ─────────────────────────────────────
def exp_2152_meal_size():
    """Do larger meals produce proportionally larger spikes?"""
    print("\n═══ EXP-2152: Meal Size Effects ═══")

    all_results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        carbs_arr = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(g))
        bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(len(g))

        meals = find_meals(g, carbs_arr, bolus)
        if len(meals) < 15:
            continue

        # Compute peak excursion for each meal
        meal_sizes = []
        peak_rises = []
        for m in meals:
            post = np.array(m['post_glucose'])
            peak = float(np.nanmax(post)) - m['pre_glucose']
            meal_sizes.append(m['carbs'])
            peak_rises.append(peak)

        meal_sizes = np.array(meal_sizes)
        peak_rises = np.array(peak_rises)

        # Correlation
        valid = ~np.isnan(peak_rises) & ~np.isnan(meal_sizes)
        if valid.sum() < 10:
            continue

        r = np.corrcoef(meal_sizes[valid], peak_rises[valid])[0, 1]

        # Bin by meal size
        small = meal_sizes < np.percentile(meal_sizes, 33)
        medium = (meal_sizes >= np.percentile(meal_sizes, 33)) & (meal_sizes < np.percentile(meal_sizes, 67))
        large = meal_sizes >= np.percentile(meal_sizes, 67)

        bins = {
            'small': {'mean_carbs': float(np.mean(meal_sizes[small])),
                      'mean_peak': float(np.nanmean(peak_rises[small])),
                      'n': int(small.sum())},
            'medium': {'mean_carbs': float(np.mean(meal_sizes[medium])),
                       'mean_peak': float(np.nanmean(peak_rises[medium])),
                       'n': int(medium.sum())},
            'large': {'mean_carbs': float(np.mean(meal_sizes[large])),
                      'mean_peak': float(np.nanmean(peak_rises[large])),
                      'n': int(large.sum())}
        }

        # Linearity test: is spike proportional to carbs?
        if valid.sum() > 5:
            slope, intercept = np.polyfit(meal_sizes[valid], peak_rises[valid], 1)
        else:
            slope, intercept = 0, 0

        all_results[name] = {
            'n_meals': len(meals),
            'correlation': float(r) if not np.isnan(r) else 0,
            'slope_mgdl_per_g': float(slope),
            'intercept': float(intercept),
            'bins': bins,
            'is_proportional': abs(r) > 0.3
        }

        print(f"  {name}: r={r:.3f} slope={slope:.2f} mg/dL per g carb, "
              f"{'proportional' if abs(r) > 0.3 else 'NOT proportional'} "
              f"({len(meals)} meals)")

    with open(f'{EXP_DIR}/exp-2152_meal_size.json', 'w') as f:
        json.dump(all_results, f, indent=2, cls=NumpyEncoder)

    if MAKE_FIGS and all_results:
        fig, axes = plt.subplots(1, 3, figsize=(16, 5))

        patient_names = sorted(all_results.keys())

        # Panel 1: Correlation between meal size and spike
        corrs = [all_results[pn]['correlation'] for pn in patient_names]
        colors = ['green' if abs(c) > 0.3 else 'gray' for c in corrs]
        axes[0].bar(patient_names, corrs, color=colors, alpha=0.7)
        axes[0].axhline(y=0.3, color='green', linestyle='--', alpha=0.3)
        axes[0].axhline(y=-0.3, color='green', linestyle='--', alpha=0.3)
        axes[0].set_ylabel('Correlation (r)')
        axes[0].set_title('Carbs vs Peak Spike Correlation')
        axes[0].tick_params(axis='x', labelsize=8)
        axes[0].grid(True, alpha=0.3, axis='y')

        # Panel 2: Small/Medium/Large spike comparison
        x = np.arange(len(patient_names))
        w = 0.25
        small_peaks = [all_results[pn]['bins']['small']['mean_peak'] for pn in patient_names]
        med_peaks = [all_results[pn]['bins']['medium']['mean_peak'] for pn in patient_names]
        large_peaks = [all_results[pn]['bins']['large']['mean_peak'] for pn in patient_names]
        axes[1].bar(x - w, small_peaks, w, label='Small meals', color='green', alpha=0.7)
        axes[1].bar(x, med_peaks, w, label='Medium meals', color='steelblue', alpha=0.7)
        axes[1].bar(x + w, large_peaks, w, label='Large meals', color='coral', alpha=0.7)
        axes[1].set_xticks(x)
        axes[1].set_xticklabels(patient_names, fontsize=8)
        axes[1].set_ylabel('Mean Peak Spike (mg/dL)')
        axes[1].set_title('Spike by Meal Size Tercile')
        axes[1].legend(fontsize=8)
        axes[1].grid(True, alpha=0.3, axis='y')

        # Panel 3: Slope (mg/dL per gram)
        slopes = [all_results[pn]['slope_mgdl_per_g'] for pn in patient_names]
        axes[2].bar(patient_names, slopes, color='steelblue', alpha=0.7)
        axes[2].set_ylabel('Spike per Gram Carb (mg/dL/g)')
        axes[2].set_title('Individual Carb Sensitivity')
        axes[2].tick_params(axis='x', labelsize=8)
        axes[2].grid(True, alpha=0.3, axis='y')

        plt.tight_layout()
        plt.savefig(f'{FIG_DIR}/meal-fig02-size.png', dpi=150)
        plt.close()
        print("  → Saved meal-fig02-size.png")

    return all_results


# ── EXP-2153: Pre-bolus Timing Impact ───────────────────────────────
def exp_2153_prebolus_timing():
    """Does bolus-to-meal timing affect excursion magnitude?"""
    print("\n═══ EXP-2153: Pre-bolus Timing Impact ═══")

    all_results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        carbs_arr = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(g))
        bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(len(g))

        meals = find_meals(g, carbs_arr, bolus)
        if len(meals) < 15:
            continue

        # Classify by pre-bolus timing
        pre_bolused = []  # Bolus ≥10 min before carbs
        concurrent = []   # Bolus within ±10 min
        late_bolus = []   # No bolus before carbs

        for m in meals:
            post = np.array(m['post_glucose'])
            peak = float(np.nanmax(post)) - m['pre_glucose']
            if np.isnan(peak):
                continue

            if m['pre_bolus_steps'] >= 2:  # ≥10 min pre-bolus
                pre_bolused.append(peak)
            elif m['bolus'] > 0.3:
                concurrent.append(peak)
            else:
                late_bolus.append(peak)

        result = {
            'n_meals': len(meals),
            'pre_bolus': {
                'n': len(pre_bolused),
                'mean_peak': float(np.mean(pre_bolused)) if pre_bolused else None,
                'median_peak': float(np.median(pre_bolused)) if pre_bolused else None
            },
            'concurrent': {
                'n': len(concurrent),
                'mean_peak': float(np.mean(concurrent)) if concurrent else None,
                'median_peak': float(np.median(concurrent)) if concurrent else None
            },
            'no_bolus': {
                'n': len(late_bolus),
                'mean_peak': float(np.mean(late_bolus)) if late_bolus else None,
                'median_peak': float(np.median(late_bolus)) if late_bolus else None
            }
        }

        # Benefit of pre-bolusing
        if pre_bolused and concurrent:
            benefit = float(np.mean(concurrent)) - float(np.mean(pre_bolused))
            result['prebolus_benefit_mgdl'] = benefit
        else:
            benefit = None
            result['prebolus_benefit_mgdl'] = None

        all_results[name] = result

        pre_str = f"{np.mean(pre_bolused):.0f}" if pre_bolused else "N/A"
        con_str = f"{np.mean(concurrent):.0f}" if concurrent else "N/A"
        no_str = f"{np.mean(late_bolus):.0f}" if late_bolus else "N/A"
        ben_str = f"{benefit:+.0f}" if benefit is not None else "N/A"
        print(f"  {name}: pre-bolus={pre_str}({len(pre_bolused)}) "
              f"concurrent={con_str}({len(concurrent)}) "
              f"no-bolus={no_str}({len(late_bolus)}) "
              f"benefit={ben_str} mg/dL")

    with open(f'{EXP_DIR}/exp-2153_prebolus.json', 'w') as f:
        json.dump(all_results, f, indent=2, cls=NumpyEncoder)

    if MAKE_FIGS and all_results:
        fig, axes = plt.subplots(1, 3, figsize=(16, 5))

        patient_names = sorted(all_results.keys())
        x = np.arange(len(patient_names))
        w = 0.25

        # Panel 1: Peak by timing category
        pre = [all_results[pn]['pre_bolus']['mean_peak'] or 0 for pn in patient_names]
        con = [all_results[pn]['concurrent']['mean_peak'] or 0 for pn in patient_names]
        nob = [all_results[pn]['no_bolus']['mean_peak'] or 0 for pn in patient_names]
        axes[0].bar(x - w, pre, w, label='Pre-bolus (≥10min)', color='green', alpha=0.7)
        axes[0].bar(x, con, w, label='Concurrent', color='steelblue', alpha=0.7)
        axes[0].bar(x + w, nob, w, label='No bolus', color='coral', alpha=0.7)
        axes[0].set_xticks(x)
        axes[0].set_xticklabels(patient_names, fontsize=8)
        axes[0].set_ylabel('Mean Peak Spike (mg/dL)')
        axes[0].set_title('Spike by Bolus Timing')
        axes[0].legend(fontsize=8)
        axes[0].grid(True, alpha=0.3, axis='y')

        # Panel 2: Pre-bolus benefit
        benefits = [all_results[pn].get('prebolus_benefit_mgdl', 0) or 0 for pn in patient_names]
        colors_b = ['green' if b > 0 else 'red' for b in benefits]
        axes[1].bar(patient_names, benefits, color=colors_b, alpha=0.7)
        axes[1].axhline(y=0, color='black', linewidth=0.5)
        axes[1].set_ylabel('Pre-bolus Benefit (mg/dL)')
        axes[1].set_title('Spike Reduction from Pre-bolusing')
        axes[1].tick_params(axis='x', labelsize=8)
        axes[1].grid(True, alpha=0.3, axis='y')

        # Panel 3: Count by category
        n_pre = [all_results[pn]['pre_bolus']['n'] for pn in patient_names]
        n_con = [all_results[pn]['concurrent']['n'] for pn in patient_names]
        n_nob = [all_results[pn]['no_bolus']['n'] for pn in patient_names]
        bottom1 = np.array(n_pre)
        bottom2 = bottom1 + np.array(n_con)
        axes[2].bar(patient_names, n_pre, label='Pre-bolus', color='green', alpha=0.7)
        axes[2].bar(patient_names, n_con, bottom=n_pre, label='Concurrent', color='steelblue', alpha=0.7)
        axes[2].bar(patient_names, n_nob, bottom=bottom2.tolist(), label='No bolus', color='coral', alpha=0.7)
        axes[2].set_ylabel('Number of Meals')
        axes[2].set_title('Bolus Timing Distribution')
        axes[2].legend(fontsize=8)
        axes[2].tick_params(axis='x', labelsize=8)

        plt.tight_layout()
        plt.savefig(f'{FIG_DIR}/meal-fig03-prebolus.png', dpi=150)
        plt.close()
        print("  → Saved meal-fig03-prebolus.png")

    return all_results


# ── EXP-2154: Meal-Period Glucose Signatures ────────────────────────
def exp_2154_meal_period_signatures():
    """Breakfast vs lunch vs dinner response shape differences."""
    print("\n═══ EXP-2154: Meal-Period Glucose Signatures ═══")

    all_results = {}
    window = 4 * STEPS_PER_HOUR

    periods = {
        'breakfast': (5, 10),
        'lunch': (11, 15),
        'dinner': (17, 22)
    }

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        carbs_arr = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(g))
        bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(len(g))

        meals = find_meals(g, carbs_arr, bolus)
        if len(meals) < 15:
            continue

        period_results = {}
        for period_name, (start_h, end_h) in periods.items():
            period_meals = [m for m in meals if start_h <= m['hour'] < end_h]
            if len(period_meals) < 3:
                continue

            excursions = []
            peaks = []
            for m in period_meals:
                post = np.array(m['post_glucose'])
                if len(post) == window:
                    delta = post - m['pre_glucose']
                    excursions.append(delta)
                    peaks.append(float(np.nanmax(delta)))

            if not excursions:
                continue

            mean_curve = np.nanmean(excursions, axis=0)
            peak_idx = np.nanargmax(mean_curve)

            period_results[period_name] = {
                'n_meals': len(period_meals),
                'mean_peak': float(np.nanmean(peaks)),
                'median_peak': float(np.nanmedian(peaks)),
                'peak_time_min': int(peak_idx * 5),
                'mean_carbs': float(np.mean([m['carbs'] for m in period_meals])),
                'mean_curve': mean_curve.tolist()
            }

        if not period_results:
            continue

        # Dinner-to-breakfast ratio
        if 'dinner' in period_results and 'breakfast' in period_results:
            d_peak = period_results['dinner']['mean_peak']
            b_peak = period_results['breakfast']['mean_peak']
            ratio = d_peak / b_peak if b_peak > 0 else float('inf')
        else:
            ratio = None

        all_results[name] = {
            'periods': period_results,
            'dinner_breakfast_ratio': float(ratio) if ratio and not np.isinf(ratio) else None
        }

        parts = []
        for pn in ['breakfast', 'lunch', 'dinner']:
            if pn in period_results:
                parts.append(f"{pn[0].upper()}={period_results[pn]['mean_peak']:.0f}")
        ratio_str = f" D/B={ratio:.1f}×" if ratio and not np.isinf(ratio) else ""
        print(f"  {name}: {' '.join(parts)}{ratio_str}")

    with open(f'{EXP_DIR}/exp-2154_meal_periods.json', 'w') as f:
        json.dump(all_results, f, indent=2, cls=NumpyEncoder)

    if MAKE_FIGS and all_results:
        fig, axes = plt.subplots(1, 3, figsize=(16, 5))

        patient_names = sorted(all_results.keys())
        time_axis = np.arange(window) * 5

        # Panel 1: Population mean curves by period
        period_curves = {pn: [] for pn in periods}
        for pat_name in patient_names:
            for pn in periods:
                if pn in all_results[pat_name]['periods']:
                    curve = all_results[pat_name]['periods'][pn]['mean_curve']
                    period_curves[pn].append(curve)

        colors_p = {'breakfast': 'orange', 'lunch': 'steelblue', 'dinner': 'purple'}
        for pn in periods:
            if period_curves[pn]:
                mean_c = np.nanmean(period_curves[pn], axis=0)
                axes[0].plot(time_axis[:len(mean_c)], mean_c, '-', color=colors_p[pn],
                             label=pn.capitalize(), linewidth=2)
        axes[0].axhline(y=0, color='black', linewidth=0.5)
        axes[0].set_xlabel('Minutes Post-Meal')
        axes[0].set_ylabel('Glucose Δ (mg/dL)')
        axes[0].set_title('Population Mean Excursion by Period')
        axes[0].legend(fontsize=10)
        axes[0].grid(True, alpha=0.3)

        # Panel 2: Per-patient peak by period
        x = np.arange(len(patient_names))
        w = 0.25
        for pi, pn in enumerate(['breakfast', 'lunch', 'dinner']):
            peaks_p = []
            for pat_name in patient_names:
                if pn in all_results[pat_name]['periods']:
                    peaks_p.append(all_results[pat_name]['periods'][pn]['mean_peak'])
                else:
                    peaks_p.append(0)
            offset = (pi - 1) * w
            axes[1].bar(x + offset, peaks_p, w, label=pn.capitalize(),
                        color=colors_p[pn], alpha=0.7)
        axes[1].set_xticks(x)
        axes[1].set_xticklabels(patient_names, fontsize=8)
        axes[1].set_ylabel('Mean Peak Spike (mg/dL)')
        axes[1].set_title('Peak Spike by Meal Period')
        axes[1].legend(fontsize=8)
        axes[1].grid(True, alpha=0.3, axis='y')

        # Panel 3: Dinner/breakfast ratio
        ratios = [all_results[pn].get('dinner_breakfast_ratio', 0) or 0 for pn in patient_names]
        colors_r = ['red' if r > 1.5 else 'orange' if r > 1 else 'green' for r in ratios]
        axes[2].bar(patient_names, ratios, color=colors_r, alpha=0.7)
        axes[2].axhline(y=1, color='black', linewidth=0.5, linestyle='--')
        axes[2].axhline(y=1.5, color='red', linewidth=0.5, linestyle='--', alpha=0.3)
        axes[2].set_ylabel('Dinner/Breakfast Peak Ratio')
        axes[2].set_title('Circadian Insulin Resistance')
        axes[2].tick_params(axis='x', labelsize=8)
        axes[2].grid(True, alpha=0.3, axis='y')

        plt.tight_layout()
        plt.savefig(f'{FIG_DIR}/meal-fig04-periods.png', dpi=150)
        plt.close()
        print("  → Saved meal-fig04-periods.png")

    return all_results


# ── EXP-2155: Post-Meal Nadir Analysis ──────────────────────────────
def exp_2155_postmeal_nadir():
    """When does the post-meal low occur (reactive hypoglycemia risk)?"""
    print("\n═══ EXP-2155: Post-Meal Nadir Analysis ═══")

    all_results = {}
    window = 5 * STEPS_PER_HOUR  # 5h post-meal to capture nadir

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        carbs_arr = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(g))
        bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(len(g))

        meals = find_meals(g, carbs_arr, bolus, min_carbs=10)
        if len(meals) < 10:
            continue

        nadir_times = []
        nadir_values = []
        overshoots = 0  # Glucose drops below pre-meal
        reactive_hypos = 0  # Glucose drops below 70 after meal

        for m in meals:
            t = m['step']
            if t + window >= len(g):
                continue
            post = g[t:t + window]
            if np.sum(np.isnan(post)) > window * 0.3:
                continue

            # Find the peak first, then find nadir after peak
            peak_idx = np.nanargmax(post[:3*STEPS_PER_HOUR])  # Peak within 3h
            post_peak = post[peak_idx:]
            if len(post_peak) < STEPS_PER_HOUR:
                continue

            nadir_idx = np.nanargmin(post_peak)
            nadir_abs_idx = peak_idx + nadir_idx
            nadir_time = nadir_abs_idx * 5
            nadir_val = float(post_peak[nadir_idx])

            nadir_times.append(nadir_time)
            nadir_values.append(nadir_val)

            if nadir_val < m['pre_glucose']:
                overshoots += 1
            if nadir_val < 70:
                reactive_hypos += 1

        if not nadir_times:
            continue

        all_results[name] = {
            'n_meals': len(meals),
            'n_analyzed': len(nadir_times),
            'median_nadir_time_min': float(np.median(nadir_times)),
            'mean_nadir_time_min': float(np.mean(nadir_times)),
            'median_nadir_value': float(np.median(nadir_values)),
            'overshoot_rate': overshoots / len(nadir_times),
            'reactive_hypo_rate': reactive_hypos / len(nadir_times),
            'n_overshoots': overshoots,
            'n_reactive_hypos': reactive_hypos
        }

        print(f"  {name}: nadir at {np.median(nadir_times):.0f}min "
              f"(value={np.median(nadir_values):.0f}), "
              f"overshoot={overshoots}/{len(nadir_times)} ({overshoots*100//len(nadir_times)}%), "
              f"reactive_hypo={reactive_hypos}/{len(nadir_times)} ({reactive_hypos*100//len(nadir_times)}%)")

    with open(f'{EXP_DIR}/exp-2155_nadir.json', 'w') as f:
        json.dump(all_results, f, indent=2, cls=NumpyEncoder)

    if MAKE_FIGS and all_results:
        fig, axes = plt.subplots(1, 3, figsize=(16, 5))

        patient_names = sorted(all_results.keys())

        # Panel 1: Nadir timing
        nadir_t = [all_results[pn]['median_nadir_time_min'] for pn in patient_names]
        axes[0].bar(patient_names, nadir_t, color='steelblue', alpha=0.7)
        axes[0].set_ylabel('Median Nadir Time (min post-meal)')
        axes[0].set_title('Post-Peak Nadir Timing')
        axes[0].tick_params(axis='x', labelsize=8)
        axes[0].grid(True, alpha=0.3, axis='y')

        # Panel 2: Overshoot and reactive hypo rates
        x = np.arange(len(patient_names))
        overshoot = [all_results[pn]['overshoot_rate'] * 100 for pn in patient_names]
        reactive = [all_results[pn]['reactive_hypo_rate'] * 100 for pn in patient_names]
        axes[1].bar(x - 0.15, overshoot, 0.3, label='Overshoot (below pre-meal)',
                    color='orange', alpha=0.7)
        axes[1].bar(x + 0.15, reactive, 0.3, label='Reactive hypo (<70)',
                    color='coral', alpha=0.7)
        axes[1].set_xticks(x)
        axes[1].set_xticklabels(patient_names, fontsize=8)
        axes[1].set_ylabel('Rate (%)')
        axes[1].set_title('Post-Meal Overshoot & Reactive Hypo')
        axes[1].legend(fontsize=8)
        axes[1].grid(True, alpha=0.3, axis='y')

        # Panel 3: Nadir value distribution
        nadir_v = [all_results[pn]['median_nadir_value'] for pn in patient_names]
        colors_n = ['red' if v < 70 else 'orange' if v < 90 else 'green' for v in nadir_v]
        axes[2].bar(patient_names, nadir_v, color=colors_n, alpha=0.7)
        axes[2].axhline(y=70, color='red', linestyle='--', alpha=0.3, label='Hypo threshold')
        axes[2].set_ylabel('Median Nadir Value (mg/dL)')
        axes[2].set_title('Post-Meal Nadir Depth')
        axes[2].legend(fontsize=8)
        axes[2].tick_params(axis='x', labelsize=8)
        axes[2].grid(True, alpha=0.3, axis='y')

        plt.tight_layout()
        plt.savefig(f'{FIG_DIR}/meal-fig05-nadir.png', dpi=150)
        plt.close()
        print("  → Saved meal-fig05-nadir.png")

    return all_results


# ── EXP-2156: Carb-to-Spike Correlation ─────────────────────────────
def exp_2156_carb_spike_correlation():
    """How well do entered carbs predict actual spike magnitude?"""
    print("\n═══ EXP-2156: Carb-to-Spike Correlation ═══")

    all_results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        carbs_arr = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(g))
        bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(len(g))

        meals = find_meals(g, carbs_arr, bolus)
        if len(meals) < 15:
            continue

        # For each meal, compute actual spike and expected spike
        actual_spikes = []
        entered_carbs = []
        bolus_given = []
        pre_glucoses = []

        for m in meals:
            post = np.array(m['post_glucose'])
            if len(post) < 2 * STEPS_PER_HOUR:
                continue
            peak = float(np.nanmax(post[:3*STEPS_PER_HOUR])) - m['pre_glucose']
            if np.isnan(peak):
                continue
            actual_spikes.append(peak)
            entered_carbs.append(m['carbs'])
            bolus_given.append(m['bolus'])
            pre_glucoses.append(m['pre_glucose'])

        if len(actual_spikes) < 10:
            continue

        actual = np.array(actual_spikes)
        carbs_a = np.array(entered_carbs)
        bolus_a = np.array(bolus_given)
        pre_g = np.array(pre_glucoses)

        # Correlations
        r_carbs = float(np.corrcoef(carbs_a, actual)[0, 1])
        r_bolus = float(np.corrcoef(bolus_a, actual)[0, 1]) if np.std(bolus_a) > 0 else 0
        r_preg = float(np.corrcoef(pre_g, actual)[0, 1]) if np.std(pre_g) > 0 else 0

        # Net effect: carbs minus bolus effect (using profile CR)
        cr_schedule = df.attrs.get('cr_schedule', [])
        profile_cr = get_profile_value(cr_schedule, 12)
        if profile_cr and profile_cr > 0:
            isf_schedule = df.attrs.get('isf_schedule', [])
            profile_isf = get_profile_value(isf_schedule, 12)
            if profile_isf and profile_isf > 0:
                if profile_isf < 15:
                    profile_isf *= 18.0182
                expected_spike = (carbs_a / profile_cr - bolus_a) * profile_isf
                r_expected = float(np.corrcoef(expected_spike, actual)[0, 1])
            else:
                expected_spike = None
                r_expected = 0
        else:
            expected_spike = None
            r_expected = 0

        # Residual variability (how much is unexplained)
        residual_cv = float(np.std(actual) / abs(np.mean(actual))) if np.mean(actual) != 0 else 0

        all_results[name] = {
            'n_meals': len(actual_spikes),
            'r_carbs_spike': r_carbs if not np.isnan(r_carbs) else 0,
            'r_bolus_spike': r_bolus if not np.isnan(r_bolus) else 0,
            'r_preglucose_spike': r_preg if not np.isnan(r_preg) else 0,
            'r_expected_spike': r_expected if not np.isnan(r_expected) else 0,
            'mean_spike': float(np.mean(actual)),
            'std_spike': float(np.std(actual)),
            'residual_cv': residual_cv
        }

        print(f"  {name}: r(carbs)={r_carbs:.3f} r(bolus)={r_bolus:.3f} "
              f"r(expected)={r_expected:.3f} residual_CV={residual_cv:.2f} "
              f"({len(actual_spikes)} meals)")

    with open(f'{EXP_DIR}/exp-2156_carb_spike.json', 'w') as f:
        json.dump(all_results, f, indent=2, cls=NumpyEncoder)

    if MAKE_FIGS and all_results:
        fig, axes = plt.subplots(1, 3, figsize=(16, 5))

        patient_names = sorted(all_results.keys())
        x = np.arange(len(patient_names))

        # Panel 1: Correlation comparison
        r_carbs = [all_results[pn]['r_carbs_spike'] for pn in patient_names]
        r_bolus = [all_results[pn]['r_bolus_spike'] for pn in patient_names]
        r_exp = [all_results[pn]['r_expected_spike'] for pn in patient_names]
        w = 0.25
        axes[0].bar(x - w, r_carbs, w, label='Carbs alone', color='orange', alpha=0.7)
        axes[0].bar(x, r_bolus, w, label='Bolus alone', color='steelblue', alpha=0.7)
        axes[0].bar(x + w, r_exp, w, label='Expected (CR model)', color='green', alpha=0.7)
        axes[0].set_xticks(x)
        axes[0].set_xticklabels(patient_names, fontsize=8)
        axes[0].set_ylabel('Correlation with Actual Spike')
        axes[0].set_title('Spike Prediction by Feature')
        axes[0].legend(fontsize=8)
        axes[0].axhline(y=0, color='black', linewidth=0.5)
        axes[0].grid(True, alpha=0.3, axis='y')

        # Panel 2: Residual variability
        resid = [all_results[pn]['residual_cv'] for pn in patient_names]
        axes[1].bar(patient_names, resid, color='coral', alpha=0.7)
        axes[1].set_ylabel('Residual CV (unexplained variability)')
        axes[1].set_title('Unexplained Spike Variability')
        axes[1].tick_params(axis='x', labelsize=8)
        axes[1].grid(True, alpha=0.3, axis='y')

        # Panel 3: Mean spike with error bars
        means = [all_results[pn]['mean_spike'] for pn in patient_names]
        stds = [all_results[pn]['std_spike'] for pn in patient_names]
        axes[2].bar(patient_names, means, color='steelblue', alpha=0.7)
        axes[2].errorbar(patient_names, means, yerr=stds, fmt='none', color='black',
                         capsize=3)
        axes[2].set_ylabel('Mean Spike ± SD (mg/dL)')
        axes[2].set_title('Spike Magnitude and Variability')
        axes[2].tick_params(axis='x', labelsize=8)
        axes[2].grid(True, alpha=0.3, axis='y')

        plt.tight_layout()
        plt.savefig(f'{FIG_DIR}/meal-fig06-correlation.png', dpi=150)
        plt.close()
        print("  → Saved meal-fig06-correlation.png")

    return all_results


# ── EXP-2157: Fat/Protein Effect Proxy ──────────────────────────────
def exp_2157_composition_effects():
    """Meals with similar carbs but different spikes suggest composition effects."""
    print("\n═══ EXP-2157: Fat/Protein Effect Proxy ═══")

    all_results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        carbs_arr = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(g))
        bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(len(g))

        meals = find_meals(g, carbs_arr, bolus, min_carbs=10)
        if len(meals) < 20:
            continue

        # Compute spike for each meal
        meal_data = []
        for m in meals:
            post = np.array(m['post_glucose'])
            if len(post) < 3 * STEPS_PER_HOUR:
                continue
            peak = float(np.nanmax(post[:3*STEPS_PER_HOUR])) - m['pre_glucose']
            if np.isnan(peak):
                continue

            # Also compute the time to peak
            peak_idx = np.nanargmax(post[:3*STEPS_PER_HOUR])
            peak_time = peak_idx * 5

            # And the "tail" behavior (is there a late rise suggesting fat/protein?)
            late_rise = 0
            if len(post) >= 4 * STEPS_PER_HOUR:
                late_g = post[3*STEPS_PER_HOUR:4*STEPS_PER_HOUR]
                early_post = post[2*STEPS_PER_HOUR:3*STEPS_PER_HOUR]
                late_rise = float(np.nanmean(late_g) - np.nanmean(early_post))

            meal_data.append({
                'carbs': m['carbs'],
                'peak': peak,
                'peak_time': peak_time,
                'late_rise': late_rise,
                'hour': m['hour']
            })

        if len(meal_data) < 15:
            continue

        # Find matched pairs: similar carbs (within 20%) but different spikes
        carbs_a = np.array([m['carbs'] for m in meal_data])
        peaks_a = np.array([m['peak'] for m in meal_data])
        late_rises = np.array([m['late_rise'] for m in meal_data])

        # Within similar-carb groups, how variable are spikes?
        # Group by carb terciles
        t33 = np.percentile(carbs_a, 33)
        t67 = np.percentile(carbs_a, 67)

        groups = {
            'low_carb': carbs_a < t33,
            'mid_carb': (carbs_a >= t33) & (carbs_a < t67),
            'high_carb': carbs_a >= t67
        }

        within_group_cv = {}
        for gn, mask in groups.items():
            if mask.sum() >= 5:
                g_peaks = peaks_a[mask]
                cv = float(np.std(g_peaks) / abs(np.mean(g_peaks))) if np.mean(g_peaks) != 0 else 0
                within_group_cv[gn] = cv

        # Late rise analysis: do some meals have delayed secondary rise?
        has_late_rise = float(np.mean(late_rises > 10))  # >10 mg/dL late rise
        mean_late_rise = float(np.mean(late_rises))

        # Peak time variability within similar carb meals
        peak_times = np.array([m['peak_time'] for m in meal_data])
        peak_time_cv = float(np.std(peak_times) / np.mean(peak_times)) if np.mean(peak_times) > 0 else 0

        all_results[name] = {
            'n_meals': len(meal_data),
            'within_group_cv': within_group_cv,
            'mean_within_cv': float(np.mean(list(within_group_cv.values()))) if within_group_cv else 0,
            'late_rise_fraction': has_late_rise,
            'mean_late_rise': mean_late_rise,
            'peak_time_cv': peak_time_cv,
            'mean_peak_time': float(np.mean(peak_times))
        }

        cv_str = f"{np.mean(list(within_group_cv.values())):.2f}" if within_group_cv else "N/A"
        print(f"  {name}: within-group CV={cv_str}, "
              f"late_rise={has_late_rise:.0%} of meals, "
              f"peak_time_CV={peak_time_cv:.2f}, "
              f"mean_peak={np.mean(peak_times):.0f}min ({len(meal_data)} meals)")

    with open(f'{EXP_DIR}/exp-2157_composition.json', 'w') as f:
        json.dump(all_results, f, indent=2, cls=NumpyEncoder)

    if MAKE_FIGS and all_results:
        fig, axes = plt.subplots(1, 3, figsize=(16, 5))

        patient_names = sorted(all_results.keys())

        # Panel 1: Within-group CV (variability not explained by carb count)
        mean_cvs = [all_results[pn]['mean_within_cv'] for pn in patient_names]
        axes[0].bar(patient_names, mean_cvs, color='coral', alpha=0.7)
        axes[0].set_ylabel('Within-Group CV')
        axes[0].set_title('Spike Variability (Same Carb Level)')
        axes[0].tick_params(axis='x', labelsize=8)
        axes[0].grid(True, alpha=0.3, axis='y')

        # Panel 2: Late rise fraction (fat/protein proxy)
        late_frac = [all_results[pn]['late_rise_fraction'] * 100 for pn in patient_names]
        axes[1].bar(patient_names, late_frac, color='steelblue', alpha=0.7)
        axes[1].set_ylabel('% Meals with Late Rise (>10 mg/dL)')
        axes[1].set_title('Delayed Secondary Rise (Fat/Protein Proxy)')
        axes[1].tick_params(axis='x', labelsize=8)
        axes[1].grid(True, alpha=0.3, axis='y')

        # Panel 3: Peak time variability
        peak_cvs = [all_results[pn]['peak_time_cv'] for pn in patient_names]
        axes[2].bar(patient_names, peak_cvs, color='green', alpha=0.7)
        axes[2].set_ylabel('Peak Time CV')
        axes[2].set_title('Peak Timing Variability')
        axes[2].tick_params(axis='x', labelsize=8)
        axes[2].grid(True, alpha=0.3, axis='y')

        plt.tight_layout()
        plt.savefig(f'{FIG_DIR}/meal-fig07-composition.png', dpi=150)
        plt.close()
        print("  → Saved meal-fig07-composition.png")

    return all_results


# ── EXP-2158: Personalized CR Recommendations ──────────────────────
def exp_2158_personalized_cr():
    """Per-patient, per-meal-period CR with confidence intervals."""
    print("\n═══ EXP-2158: Personalized CR Recommendations ═══")

    all_results = {}

    periods = {
        'breakfast': (5, 10),
        'lunch': (11, 15),
        'dinner': (17, 22)
    }

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        carbs_arr = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(g))
        bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(len(g))

        # Get profile CR and ISF
        cr_schedule = df.attrs.get('cr_schedule', [])
        isf_schedule = df.attrs.get('isf_schedule', [])
        profile_cr = get_profile_value(cr_schedule, 12)
        profile_isf = get_profile_value(isf_schedule, 12)

        if not profile_cr or profile_cr == 0:
            continue
        if profile_isf and profile_isf < 15:
            profile_isf = profile_isf * 18.0182

        meals = find_meals(g, carbs_arr, bolus, min_carbs=5)
        if len(meals) < 10:
            continue

        period_crs = {}
        for period_name, (start_h, end_h) in periods.items():
            period_meals = [m for m in meals if start_h <= m['hour'] < end_h]
            if len(period_meals) < 5:
                continue

            # For each meal, compute effective CR
            effective_crs = []
            for m in period_meals:
                post = np.array(m['post_glucose'])
                if len(post) < 3 * STEPS_PER_HOUR:
                    continue

                # Glucose at 3h vs pre-meal
                g_3h = float(np.nanmean(post[2*STEPS_PER_HOUR:3*STEPS_PER_HOUR]))
                delta = g_3h - m['pre_glucose']

                # Total insulin effect: bolus (if any)
                total_bolus = m['bolus']
                if total_bolus < 0.1:
                    continue

                # Effective carbs absorbed = carbs - (bolus effect / ISF)
                if profile_isf and profile_isf > 0:
                    # How many carbs did the bolus "cover"?
                    # If glucose rose by delta, unmatched carbs = delta / ISF * CR
                    # CR_effective = carbs / (bolus + delta/ISF)
                    effective_insulin = total_bolus + delta / profile_isf
                    if effective_insulin > 0.1:
                        eff_cr = m['carbs'] / effective_insulin
                        if 1 < eff_cr < 50:
                            effective_crs.append(eff_cr)

            if len(effective_crs) < 3:
                continue

            cr_arr = np.array(effective_crs)
            ci_95 = 1.96 * np.std(cr_arr) / np.sqrt(len(cr_arr))

            period_crs[period_name] = {
                'n_meals': len(effective_crs),
                'median_cr': float(np.median(cr_arr)),
                'mean_cr': float(np.mean(cr_arr)),
                'std_cr': float(np.std(cr_arr)),
                'ci_95': float(ci_95),
                'recommended_cr': float(np.median(cr_arr)),
                'profile_cr': float(profile_cr),
                'mismatch_pct': float((np.median(cr_arr) - profile_cr) / profile_cr * 100)
            }

        if not period_crs:
            continue

        all_results[name] = {
            'profile_cr': float(profile_cr),
            'periods': period_crs
        }

        parts = []
        for pn in ['breakfast', 'lunch', 'dinner']:
            if pn in period_crs:
                r = period_crs[pn]
                parts.append(f"{pn[0].upper()}={r['median_cr']:.1f}"
                             f"({r['mismatch_pct']:+.0f}%)")
        print(f"  {name}: profile_CR={profile_cr:.1f} → {' '.join(parts)}")

    with open(f'{EXP_DIR}/exp-2158_personalized_cr.json', 'w') as f:
        json.dump(all_results, f, indent=2, cls=NumpyEncoder)

    if MAKE_FIGS and all_results:
        fig, axes = plt.subplots(1, 3, figsize=(16, 5))

        patient_names = sorted(all_results.keys())

        # Panel 1: Profile CR vs recommended by period
        x = np.arange(len(patient_names))
        w = 0.2
        colors_p = {'breakfast': 'orange', 'lunch': 'steelblue', 'dinner': 'purple'}

        # Profile
        profile_crs = [all_results[pn]['profile_cr'] for pn in patient_names]
        axes[0].bar(x - 1.5*w, profile_crs, w, label='Profile', color='gray', alpha=0.7)

        for pi, pn_name in enumerate(['breakfast', 'lunch', 'dinner']):
            vals = []
            for pat in patient_names:
                if pn_name in all_results[pat]['periods']:
                    vals.append(all_results[pat]['periods'][pn_name]['median_cr'])
                else:
                    vals.append(0)
            offset = (pi - 0.5) * w
            axes[0].bar(x + offset, vals, w, label=pn_name.capitalize(),
                        color=colors_p[pn_name], alpha=0.7)

        axes[0].set_xticks(x)
        axes[0].set_xticklabels(patient_names, fontsize=8)
        axes[0].set_ylabel('Carb Ratio (g/U)')
        axes[0].set_title('Profile vs Effective CR by Period')
        axes[0].legend(fontsize=7)
        axes[0].grid(True, alpha=0.3, axis='y')

        # Panel 2: Mismatch percentage by period
        for pn_name in ['breakfast', 'lunch', 'dinner']:
            mismatches = []
            for pat in patient_names:
                if pn_name in all_results[pat]['periods']:
                    mismatches.append(all_results[pat]['periods'][pn_name]['mismatch_pct'])
                else:
                    mismatches.append(0)
            axes[1].plot(patient_names, mismatches, 'o-', label=pn_name.capitalize(),
                         color=colors_p[pn_name], alpha=0.7)
        axes[1].axhline(y=0, color='black', linewidth=0.5)
        axes[1].set_ylabel('CR Mismatch (%)')
        axes[1].set_title('CR Mismatch by Period')
        axes[1].legend(fontsize=8)
        axes[1].tick_params(axis='x', labelsize=8)
        axes[1].grid(True, alpha=0.3)

        # Panel 3: Confidence intervals for dinner CR
        dinner_names = [pn for pn in patient_names if 'dinner' in all_results[pn]['periods']]
        if dinner_names:
            d_crs = [all_results[pn]['periods']['dinner']['median_cr'] for pn in dinner_names]
            d_cis = [all_results[pn]['periods']['dinner']['ci_95'] for pn in dinner_names]
            d_prof = [all_results[pn]['profile_cr'] for pn in dinner_names]

            axes[2].errorbar(dinner_names, d_crs, yerr=d_cis, fmt='o', color='purple',
                             capsize=5, markersize=8, label='Effective ± 95% CI')
            axes[2].scatter(dinner_names, d_prof, marker='x', s=100, color='gray',
                            label='Profile CR', zorder=5)
            axes[2].set_ylabel('Dinner CR (g/U)')
            axes[2].set_title('Dinner CR with Confidence Intervals')
            axes[2].legend(fontsize=8)
            axes[2].tick_params(axis='x', labelsize=8)
            axes[2].grid(True, alpha=0.3)

        plt.tight_layout()
        plt.savefig(f'{FIG_DIR}/meal-fig08-cr.png', dpi=150)
        plt.close()
        print("  → Saved meal-fig08-cr.png")

    return all_results


# ══════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    print("=" * 60)
    print("EXP-2151–2158: Meal Response Personalization & Carb Absorption")
    print("=" * 60)

    r1 = exp_2151_absorption_curves()
    r2 = exp_2152_meal_size()
    r3 = exp_2153_prebolus_timing()
    r4 = exp_2154_meal_period_signatures()
    r5 = exp_2155_postmeal_nadir()
    r6 = exp_2156_carb_spike_correlation()
    r7 = exp_2157_composition_effects()
    r8 = exp_2158_personalized_cr()

    print("\n" + "=" * 60)
    n_complete = sum(1 for r in [r1, r2, r3, r4, r5, r6, r7, r8] if r)
    print(f"Results: {n_complete}/8 experiments completed")
    print(f"Figures saved to {FIG_DIR}/meal-fig01–08")
    print("=" * 60)
