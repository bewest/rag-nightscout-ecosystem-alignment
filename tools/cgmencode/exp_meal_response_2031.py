#!/usr/bin/env python3
"""
EXP-2031–2038: Meal Response & Absorption Dynamics

Personalized carb absorption analysis: speed, shape, and what predicts
meal outcome. This directly feeds ISF/CR accuracy and algorithm improvements.

EXP-2031: Per-patient carb absorption curves (time to peak, magnitude)
EXP-2032: Pre-meal glucose as predictor of post-meal spike
EXP-2033: Bolus timing relative to meal (pre-bolus vs late bolus effect)
EXP-2034: Meal size vs spike magnitude (is CR linear?)
EXP-2035: Post-meal trajectory classification (spike-and-return, spike-and-plateau, sustained)
EXP-2036: Second meal effect (how prior meals affect next meal response)
EXP-2037: Time-of-day meal response differences (breakfast vs lunch vs dinner)
EXP-2038: Synthesis — personalized meal response profiles

Depends on: exp_metabolic_441.py
"""

import json
import sys
import os
import numpy as np
import warnings
warnings.filterwarnings('ignore')

from exp_metabolic_441 import load_patients, compute_supply_demand

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
HYPO_THRESH = 70
TARGET_LOW = 70
TARGET_HIGH = 180


def find_meals(df, min_carbs=10):
    """Find meal events with ≥min_carbs grams."""
    carbs = df['carbs'].values.astype(float) if 'carbs' in df.columns else np.zeros(len(df['glucose'].values))
    glucose = df['glucose'].values.astype(float)
    bolus = df['bolus'].values.astype(float) if 'bolus' in df.columns else np.zeros(len(glucose))

    meals = []
    for i in range(len(carbs)):
        if carbs[i] >= min_carbs:
            pre_g = glucose[max(0, i-3):i+1]
            pre_g_valid = pre_g[np.isfinite(pre_g)]
            pre_glucose = float(np.mean(pre_g_valid)) if len(pre_g_valid) > 0 else np.nan

            # Post-meal window: 4h
            post_window = min(i + 48, len(glucose))
            post_g = glucose[i:post_window]

            # Find bolus within ±30min
            bolus_window = bolus[max(0, i-6):min(i+6, len(bolus))]
            meal_bolus = float(np.nansum(bolus_window))

            # Bolus timing: minutes before/after carb entry
            # Negative = pre-bolus, positive = late bolus
            bolus_timing_min = 0
            for j in range(max(0, i-6), min(i+6, len(bolus))):
                if bolus[j] > 0.3:
                    bolus_timing_min = (j - i) * 5  # minutes
                    break

            meals.append({
                'index': i,
                'carbs': float(carbs[i]),
                'pre_glucose': pre_glucose,
                'post_glucose': post_g.copy(),
                'meal_bolus': meal_bolus,
                'bolus_timing_min': bolus_timing_min,
                'hour': (i % STEPS_PER_DAY) / STEPS_PER_HOUR,
            })

    return meals


patients = load_patients(PATIENT_DIR)
results = {}


# ══════════════════════════════════════════════════════════════
# EXP-2031: Per-Patient Carb Absorption Curves
# ══════════════════════════════════════════════════════════════
print("\n" + "#" * 70)
print("# Running EXP-2031")
print("#" * 70)
print("\n" + "=" * 70)
print("EXP-2031: Per-Patient Carb Absorption Curves")
print("=" * 70)

exp2031 = {}
for p in patients:
    name = p['name']
    df = p['df']
    meals = find_meals(df, min_carbs=15)

    if len(meals) < 10:
        exp2031[name] = {'n_meals': len(meals), 'status': 'insufficient'}
        print(f"  {name}: only {len(meals)} meals")
        continue

    # Compute average post-meal glucose curve (delta from pre-meal)
    curves = []
    for meal in meals:
        if not np.isfinite(meal['pre_glucose']):
            continue
        post = meal['post_glucose']
        if len(post) < 36:  # need 3h minimum
            continue
        delta = post[:48] - meal['pre_glucose']
        if len(delta) < 36:
            continue
        # Pad with NaN if shorter than 48
        if len(delta) < 48:
            delta = np.concatenate([delta, np.full(48 - len(delta), np.nan)])
        curves.append(delta)

    if len(curves) < 10:
        exp2031[name] = {'n_meals': len(curves), 'status': 'insufficient_valid'}
        print(f"  {name}: only {len(curves)} valid curves")
        continue

    curves_array = np.array(curves)
    mean_curve = np.nanmean(curves_array, axis=0)

    # Find peak
    peak_idx = np.nanargmax(mean_curve)
    peak_time_min = peak_idx * 5
    peak_magnitude = float(mean_curve[peak_idx])

    # Find time to return to baseline (within 10 mg/dL)
    return_idx = len(mean_curve) - 1
    for ri in range(peak_idx, len(mean_curve)):
        if mean_curve[ri] < 10:
            return_idx = ri
            break
    return_time_min = return_idx * 5

    # Classification
    if peak_time_min <= 45:
        speed = 'FAST'
    elif peak_time_min <= 75:
        speed = 'MODERATE'
    else:
        speed = 'SLOW'

    # Sustained or returns
    end_delta = float(np.nanmean(mean_curve[-6:]))  # last 30min
    shape = 'sustained' if end_delta > peak_magnitude * 0.5 else 'returns'

    exp2031[name] = {
        'n_meals': len(curves),
        'peak_time_min': int(peak_time_min),
        'peak_magnitude': round(peak_magnitude, 1),
        'return_time_min': int(return_time_min),
        'end_delta': round(end_delta, 1),
        'speed': speed,
        'shape': shape,
        'mean_curve': [round(float(v), 1) for v in mean_curve],
    }

    print(f"  {name}: n={len(curves)} peak={peak_time_min}min +{peak_magnitude:.0f}mg/dL "
          f"return={return_time_min}min speed={speed} shape={shape}")

if MAKE_FIGS:
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    time_h = np.arange(48) * 5 / 60

    ax = axes[0, 0]
    for n in exp2031:
        if 'mean_curve' not in exp2031[n]:
            continue
        curve = exp2031[n]['mean_curve']
        ax.plot(time_h[:len(curve)], curve, '-', label=f"{n} ({exp2031[n]['speed']})", alpha=0.7)
    ax.axhline(0, color='gray', ls='--', alpha=0.5)
    ax.set_xlabel('Time After Meal (hours)')
    ax.set_ylabel('Glucose Change (mg/dL)')
    ax.set_title('Mean Post-Meal Glucose Curves')
    ax.legend(fontsize=7, ncol=2)
    ax.grid(True, alpha=0.3)

    ax = axes[0, 1]
    names_list = [n for n in exp2031 if 'peak_time_min' in exp2031[n]]
    peaks = [exp2031[n]['peak_time_min'] for n in names_list]
    mags = [exp2031[n]['peak_magnitude'] for n in names_list]
    ax.scatter(peaks, mags, s=60, zorder=3)
    for n, pk, mg in zip(names_list, peaks, mags):
        ax.annotate(n, (pk, mg), fontsize=9)
    ax.set_xlabel('Peak Time (min)')
    ax.set_ylabel('Peak Magnitude (mg/dL)')
    ax.set_title('Absorption Speed vs Spike Height')
    ax.grid(True, alpha=0.3)

    ax = axes[1, 0]
    speeds = [exp2031[n].get('speed', '') for n in names_list]
    speed_colors = {'FAST': 'green', 'MODERATE': 'orange', 'SLOW': 'red'}
    c = [speed_colors.get(s, 'gray') for s in speeds]
    ax.barh(range(len(names_list)), peaks, color=c, alpha=0.7)
    ax.set_yticks(range(len(names_list)))
    ax.set_yticklabels(names_list)
    ax.set_xlabel('Peak Time (min)')
    ax.set_title('Absorption Speed Classification')
    ax.axvline(45, color='green', ls='--', alpha=0.3, label='FAST cutoff')
    ax.axvline(75, color='red', ls='--', alpha=0.3, label='SLOW cutoff')
    ax.legend()
    ax.grid(True, alpha=0.3, axis='x')

    ax = axes[1, 1]
    n_meals = [exp2031[n].get('n_meals', 0) for n in names_list]
    ax.bar(range(len(names_list)), n_meals, color='steelblue', alpha=0.7)
    ax.set_xticks(range(len(names_list)))
    ax.set_xticklabels(names_list)
    ax.set_ylabel('Number of Meals')
    ax.set_title('Meal Count per Patient')
    ax.grid(True, alpha=0.3, axis='y')

    plt.suptitle('EXP-2031: Carb Absorption Curves', fontsize=14)
    plt.tight_layout()
    plt.savefig(f'{FIG_DIR}/meal-fig01-absorption.png', dpi=150)
    plt.close()
    print(f"  → Saved meal-fig01-absorption.png")

all_peaks = [exp2031[n]['peak_time_min'] for n in exp2031 if 'peak_time_min' in exp2031[n]]
verdict_2031 = f"MEDIAN_PEAK={int(np.median(all_peaks))}min"
results['EXP-2031'] = verdict_2031
print(f"\n  ✓ EXP-2031 verdict: {verdict_2031}")


# ══════════════════════════════════════════════════════════════
# EXP-2032: Pre-Meal Glucose as Predictor of Post-Meal Spike
# ══════════════════════════════════════════════════════════════
print("\n" + "#" * 70)
print("# Running EXP-2032")
print("#" * 70)
print("\n" + "=" * 70)
print("EXP-2032: Pre-Meal Glucose → Post-Meal Spike Prediction")
print("=" * 70)

exp2032 = {}
for p in patients:
    name = p['name']
    df = p['df']
    meals = find_meals(df, min_carbs=10)

    pre_glucoses = []
    spikes = []
    for meal in meals:
        if not np.isfinite(meal['pre_glucose']):
            continue
        post = meal['post_glucose']
        valid_post = post[np.isfinite(post)]
        if len(valid_post) < 12:
            continue
        spike = float(np.max(valid_post[:36]) - meal['pre_glucose'])
        pre_glucoses.append(meal['pre_glucose'])
        spikes.append(spike)

    if len(pre_glucoses) < 20:
        exp2032[name] = {'status': 'insufficient', 'n': len(pre_glucoses)}
        print(f"  {name}: only {len(pre_glucoses)} meals")
        continue

    pre_arr = np.array(pre_glucoses)
    spike_arr = np.array(spikes)
    corr = float(np.corrcoef(pre_arr, spike_arr)[0, 1])

    # Bin by pre-meal glucose ranges
    bins = [(60, 100, 'low'), (100, 140, 'in-range'), (140, 180, 'elevated'), (180, 300, 'high')]
    bin_results = {}
    for lo, hi, label in bins:
        mask = (pre_arr >= lo) & (pre_arr < hi)
        if np.sum(mask) >= 5:
            bin_results[label] = {
                'n': int(np.sum(mask)),
                'mean_spike': round(float(np.mean(spike_arr[mask])), 1),
                'median_spike': round(float(np.median(spike_arr[mask])), 1),
            }

    exp2032[name] = {
        'n_meals': len(pre_glucoses),
        'correlation': round(corr, 3),
        'mean_spike': round(float(np.mean(spikes)), 1),
        'bins': bin_results,
    }

    print(f"  {name}: n={len(pre_glucoses)} r={corr:.3f} mean_spike={np.mean(spikes):.0f}mg/dL")

if MAKE_FIGS:
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    ax = axes[0]
    names_list = [n for n in exp2032 if 'correlation' in exp2032[n]]
    corrs = [exp2032[n]['correlation'] for n in names_list]
    colors = ['green' if c < -0.1 else 'red' if c > 0.1 else 'gray' for c in corrs]
    ax.barh(range(len(names_list)), corrs, color=colors, alpha=0.7)
    ax.set_yticks(range(len(names_list)))
    ax.set_yticklabels(names_list)
    ax.set_xlabel('Correlation (pre-meal glucose ↔ spike)')
    ax.set_title('Does Starting Glucose Predict Spike?')
    ax.axvline(0, color='black', ls='--', alpha=0.5)
    ax.grid(True, alpha=0.3, axis='x')

    ax = axes[1]
    # Scatter for all patients combined
    all_pre = []
    all_spike = []
    all_names = []
    for n in names_list:
        all_pre.extend([exp2032[n].get('mean_spike', 0)] * 1)
    # Use bin data instead
    labels = ['low', 'in-range', 'elevated', 'high']
    for label in labels:
        bin_spikes = []
        for n in names_list:
            if label in exp2032[n].get('bins', {}):
                bin_spikes.append(exp2032[n]['bins'][label]['mean_spike'])
        if bin_spikes:
            ax.bar(label, np.mean(bin_spikes), yerr=np.std(bin_spikes) if len(bin_spikes) > 1 else 0,
                   color='steelblue', alpha=0.7, capsize=5)
    ax.set_xlabel('Pre-Meal Glucose Range')
    ax.set_ylabel('Mean Post-Meal Spike (mg/dL)')
    ax.set_title('Spike Size by Pre-Meal Glucose')
    ax.grid(True, alpha=0.3, axis='y')

    plt.suptitle('EXP-2032: Pre-Meal Glucose → Spike Prediction', fontsize=14)
    plt.tight_layout()
    plt.savefig(f'{FIG_DIR}/meal-fig02-premeal.png', dpi=150)
    plt.close()
    print(f"  → Saved meal-fig02-premeal.png")

all_corrs = [exp2032[n]['correlation'] for n in exp2032 if 'correlation' in exp2032[n]]
verdict_2032 = f"MEAN_CORR={np.mean(all_corrs):.3f}"
results['EXP-2032'] = verdict_2032
print(f"\n  ✓ EXP-2032 verdict: {verdict_2032}")


# ══════════════════════════════════════════════════════════════
# EXP-2033: Bolus Timing Effect (Pre-bolus vs Late)
# ══════════════════════════════════════════════════════════════
print("\n" + "#" * 70)
print("# Running EXP-2033")
print("#" * 70)
print("\n" + "=" * 70)
print("EXP-2033: Bolus Timing Effect")
print("=" * 70)

exp2033 = {}
for p in patients:
    name = p['name']
    df = p['df']
    glucose = df['glucose'].values.astype(float)
    bolus = df['bolus'].values.astype(float) if 'bolus' in df.columns else np.zeros(len(glucose))
    carbs = df['carbs'].values.astype(float) if 'carbs' in df.columns else np.zeros(len(glucose))

    pre_bolus_spikes = []
    late_bolus_spikes = []
    no_bolus_spikes = []

    for i in range(len(carbs)):
        if carbs[i] < 15:
            continue
        if not np.isfinite(glucose[i]) or glucose[i] < 50:
            continue

        # Post-meal window
        post = glucose[i:min(i + 36, len(glucose))]
        valid_post = post[np.isfinite(post)]
        if len(valid_post) < 12:
            continue
        spike = float(np.max(valid_post) - glucose[i])

        # Check bolus timing: look 30min before to 30min after
        pre_bolus = bolus[max(0, i-6):i]  # 30min before
        co_bolus = bolus[i:min(i+2, len(bolus))]  # concurrent (±10min)
        late_bolus_arr = bolus[min(i+2, len(bolus)):min(i+6, len(bolus))]  # 10-30min after

        has_pre = np.nansum(pre_bolus) > 0.3
        has_co = np.nansum(co_bolus) > 0.3
        has_late = np.nansum(late_bolus_arr) > 0.3

        if has_pre:
            pre_bolus_spikes.append(spike)
        elif has_late:
            late_bolus_spikes.append(spike)
        elif not has_co and not has_pre and not has_late:
            no_bolus_spikes.append(spike)

    exp2033[name] = {
        'pre_bolus_n': len(pre_bolus_spikes),
        'pre_bolus_spike': round(float(np.mean(pre_bolus_spikes)), 1) if pre_bolus_spikes else np.nan,
        'late_bolus_n': len(late_bolus_spikes),
        'late_bolus_spike': round(float(np.mean(late_bolus_spikes)), 1) if late_bolus_spikes else np.nan,
        'no_bolus_n': len(no_bolus_spikes),
        'no_bolus_spike': round(float(np.mean(no_bolus_spikes)), 1) if no_bolus_spikes else np.nan,
    }

    pre_s = f"pre={np.mean(pre_bolus_spikes):.0f}" if pre_bolus_spikes else "pre=N/A"
    late_s = f"late={np.mean(late_bolus_spikes):.0f}" if late_bolus_spikes else "late=N/A"
    no_s = f"none={np.mean(no_bolus_spikes):.0f}" if no_bolus_spikes else "none=N/A"
    print(f"  {name}: {pre_s}(n={len(pre_bolus_spikes)}) "
          f"{late_s}(n={len(late_bolus_spikes)}) {no_s}(n={len(no_bolus_spikes)})")

if MAKE_FIGS:
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    ax = axes[0]
    names_list = list(exp2033.keys())
    pre_vals = [exp2033[n].get('pre_bolus_spike', 0) or 0 for n in names_list]
    late_vals = [exp2033[n].get('late_bolus_spike', 0) or 0 for n in names_list]
    no_vals = [exp2033[n].get('no_bolus_spike', 0) or 0 for n in names_list]
    x = np.arange(len(names_list))
    width = 0.25
    ax.bar(x - width, pre_vals, width, label='Pre-bolus', color='green', alpha=0.7)
    ax.bar(x, late_vals, width, label='Late bolus', color='orange', alpha=0.7)
    ax.bar(x + width, no_vals, width, label='No bolus', color='red', alpha=0.7)
    ax.set_xticks(x)
    ax.set_xticklabels(names_list)
    ax.set_ylabel('Mean Spike (mg/dL)')
    ax.set_title('Spike by Bolus Timing')
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')

    ax = axes[1]
    # Pre-bolus benefit = no_bolus - pre_bolus
    benefits = []
    benefit_names = []
    for n in names_list:
        pre = exp2033[n].get('pre_bolus_spike')
        no = exp2033[n].get('no_bolus_spike')
        if pre is not None and no is not None and np.isfinite(pre) and np.isfinite(no):
            benefits.append(no - pre)
            benefit_names.append(n)
    colors = ['green' if b > 0 else 'red' for b in benefits]
    ax.barh(range(len(benefit_names)), benefits, color=colors, alpha=0.7)
    ax.set_yticks(range(len(benefit_names)))
    ax.set_yticklabels(benefit_names)
    ax.set_xlabel('Pre-Bolus Benefit (mg/dL spike reduction)')
    ax.set_title('Spike Reduction from Pre-Bolusing')
    ax.axvline(0, color='black', ls='--', alpha=0.5)
    ax.grid(True, alpha=0.3, axis='x')

    plt.suptitle('EXP-2033: Bolus Timing Effect', fontsize=14)
    plt.tight_layout()
    plt.savefig(f'{FIG_DIR}/meal-fig03-timing.png', dpi=150)
    plt.close()
    print(f"  → Saved meal-fig03-timing.png")

pre_spikes = [exp2033[n]['pre_bolus_spike'] for n in exp2033 if np.isfinite(exp2033[n].get('pre_bolus_spike', np.nan))]
late_spikes = [exp2033[n]['late_bolus_spike'] for n in exp2033 if np.isfinite(exp2033[n].get('late_bolus_spike', np.nan))]
verdict_2033 = f"PRE={np.mean(pre_spikes):.0f}_LATE={np.mean(late_spikes):.0f}mg/dL"
results['EXP-2033'] = verdict_2033
print(f"\n  ✓ EXP-2033 verdict: {verdict_2033}")


# ══════════════════════════════════════════════════════════════
# EXP-2034: Meal Size vs Spike (Is CR Linear?)
# ══════════════════════════════════════════════════════════════
print("\n" + "#" * 70)
print("# Running EXP-2034")
print("#" * 70)
print("\n" + "=" * 70)
print("EXP-2034: Meal Size vs Spike Magnitude")
print("=" * 70)

exp2034 = {}
for p in patients:
    name = p['name']
    df = p['df']
    meals = find_meals(df, min_carbs=5)

    carb_vals = []
    spike_vals = []
    for meal in meals:
        if not np.isfinite(meal['pre_glucose']):
            continue
        post = meal['post_glucose']
        valid_post = post[np.isfinite(post)]
        if len(valid_post) < 12:
            continue
        spike = float(np.max(valid_post[:36]) - meal['pre_glucose'])
        carb_vals.append(meal['carbs'])
        spike_vals.append(spike)

    if len(carb_vals) < 20:
        exp2034[name] = {'status': 'insufficient', 'n': len(carb_vals)}
        print(f"  {name}: only {len(carb_vals)} meals")
        continue

    carb_arr = np.array(carb_vals)
    spike_arr = np.array(spike_vals)
    corr = float(np.corrcoef(carb_arr, spike_arr)[0, 1])

    # Linear fit: spike = slope * carbs + intercept
    slope, intercept = np.polyfit(carb_arr, spike_arr, 1)

    # Non-linearity check: fit quadratic
    poly2 = np.polyfit(carb_arr, spike_arr, 2)
    # Compare R² of linear vs quadratic
    linear_pred = slope * carb_arr + intercept
    quad_pred = np.polyval(poly2, carb_arr)
    ss_total = np.sum((spike_arr - np.mean(spike_arr))**2)
    r2_linear = 1 - np.sum((spike_arr - linear_pred)**2) / ss_total if ss_total > 0 else 0
    r2_quad = 1 - np.sum((spike_arr - quad_pred)**2) / ss_total if ss_total > 0 else 0

    # Bin analysis
    bins = [(5, 20, 'small'), (20, 40, 'medium'), (40, 80, 'large'), (80, 200, 'very_large')]
    bin_results = {}
    for lo, hi, label in bins:
        mask = (carb_arr >= lo) & (carb_arr < hi)
        if np.sum(mask) >= 5:
            bin_results[label] = {
                'n': int(np.sum(mask)),
                'mean_carbs': round(float(np.mean(carb_arr[mask])), 0),
                'mean_spike': round(float(np.mean(spike_arr[mask])), 1),
                'spike_per_g': round(float(np.mean(spike_arr[mask]) / np.mean(carb_arr[mask])), 2),
            }

    exp2034[name] = {
        'n_meals': len(carb_vals),
        'correlation': round(corr, 3),
        'slope_mg_per_g': round(float(slope), 2),
        'intercept': round(float(intercept), 1),
        'r2_linear': round(float(r2_linear), 4),
        'r2_quadratic': round(float(r2_quad), 4),
        'bins': bin_results,
    }

    print(f"  {name}: n={len(carb_vals)} r={corr:.3f} slope={slope:.2f}mg/dL/g "
          f"R²_lin={r2_linear:.4f} R²_quad={r2_quad:.4f}")

if MAKE_FIGS:
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    ax = axes[0]
    names_list = [n for n in exp2034 if 'slope_mg_per_g' in exp2034[n]]
    slopes = [exp2034[n]['slope_mg_per_g'] for n in names_list]
    ax.barh(range(len(names_list)), slopes, color='steelblue', alpha=0.7)
    ax.set_yticks(range(len(names_list)))
    ax.set_yticklabels(names_list)
    ax.set_xlabel('Spike per Gram Carb (mg/dL/g)')
    ax.set_title('Carb Sensitivity (dose-response slope)')
    ax.grid(True, alpha=0.3, axis='x')

    ax = axes[1]
    # R² comparison: linear vs quadratic
    r2_lin = [exp2034[n]['r2_linear'] for n in names_list]
    r2_quad = [exp2034[n]['r2_quadratic'] for n in names_list]
    x = np.arange(len(names_list))
    width = 0.35
    ax.bar(x - width/2, r2_lin, width, label='Linear', color='steelblue', alpha=0.7)
    ax.bar(x + width/2, r2_quad, width, label='Quadratic', color='coral', alpha=0.7)
    ax.set_xticks(x)
    ax.set_xticklabels(names_list)
    ax.set_ylabel('R²')
    ax.set_title('Linear vs Quadratic Fit')
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')

    plt.suptitle('EXP-2034: Meal Size vs Spike', fontsize=14)
    plt.tight_layout()
    plt.savefig(f'{FIG_DIR}/meal-fig04-doseresponse.png', dpi=150)
    plt.close()
    print(f"  → Saved meal-fig04-doseresponse.png")

all_slopes = [exp2034[n]['slope_mg_per_g'] for n in exp2034 if 'slope_mg_per_g' in exp2034[n]]
verdict_2034 = f"MEAN_SLOPE={np.mean(all_slopes):.2f}mg/dL/g"
results['EXP-2034'] = verdict_2034
print(f"\n  ✓ EXP-2034 verdict: {verdict_2034}")


# ══════════════════════════════════════════════════════════════
# EXP-2035: Post-Meal Trajectory Classification
# ══════════════════════════════════════════════════════════════
print("\n" + "#" * 70)
print("# Running EXP-2035")
print("#" * 70)
print("\n" + "=" * 70)
print("EXP-2035: Post-Meal Trajectory Classification")
print("=" * 70)

exp2035 = {}
for p in patients:
    name = p['name']
    df = p['df']
    meals = find_meals(df, min_carbs=15)

    trajectories = {'spike_return': 0, 'spike_plateau': 0, 'sustained_rise': 0, 'no_spike': 0, 'drop': 0}
    total = 0

    for meal in meals:
        if not np.isfinite(meal['pre_glucose']):
            continue
        post = meal['post_glucose']
        if len(post) < 36:
            continue
        total += 1

        baseline = meal['pre_glucose']
        # Segment into phases
        first_hour = post[:12]  # 0-60min
        second_hour = post[12:24]  # 60-120min
        third_hour = post[24:36]  # 120-180min

        valid_1h = first_hour[np.isfinite(first_hour)]
        valid_2h = second_hour[np.isfinite(second_hour)]
        valid_3h = third_hour[np.isfinite(third_hour)]

        if len(valid_1h) < 6 or len(valid_2h) < 6:
            continue

        peak_1h = float(np.max(valid_1h)) - baseline
        mean_2h = float(np.mean(valid_2h)) - baseline
        mean_3h = float(np.mean(valid_3h)) - baseline if len(valid_3h) >= 3 else mean_2h

        if peak_1h < 20:
            trajectories['no_spike'] += 1
        elif peak_1h < 0:
            trajectories['drop'] += 1
        elif mean_3h < peak_1h * 0.3:
            trajectories['spike_return'] += 1
        elif mean_3h > peak_1h * 0.7:
            trajectories['sustained_rise'] += 1
        else:
            trajectories['spike_plateau'] += 1

    pcts = {k: round(v / total * 100, 1) if total > 0 else 0 for k, v in trajectories.items()}
    exp2035[name] = {
        'n_meals': total,
        'counts': trajectories,
        'percentages': pcts,
        'dominant': max(pcts, key=pcts.get) if pcts else 'unknown',
    }

    print(f"  {name}: n={total} return={pcts.get('spike_return', 0):.0f}% "
          f"plateau={pcts.get('spike_plateau', 0):.0f}% "
          f"sustained={pcts.get('sustained_rise', 0):.0f}% "
          f"no_spike={pcts.get('no_spike', 0):.0f}%")

if MAKE_FIGS:
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    ax = axes[0]
    names_list = [n for n in exp2035 if 'percentages' in exp2035[n]]
    categories = ['spike_return', 'spike_plateau', 'sustained_rise', 'no_spike']
    cat_colors = ['green', 'orange', 'red', 'gray']
    bottom = np.zeros(len(names_list))
    for cat, color in zip(categories, cat_colors):
        vals = [exp2035[n]['percentages'].get(cat, 0) for n in names_list]
        ax.barh(range(len(names_list)), vals, left=bottom, label=cat, color=color, alpha=0.7)
        bottom += vals
    ax.set_yticks(range(len(names_list)))
    ax.set_yticklabels(names_list)
    ax.set_xlabel('Percentage')
    ax.set_title('Meal Trajectory Distribution')
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3, axis='x')

    ax = axes[1]
    # Pie chart of population-level distribution
    pop_counts = {cat: 0 for cat in categories}
    for n in names_list:
        for cat in categories:
            pop_counts[cat] += exp2035[n]['counts'].get(cat, 0)
    total_pop = sum(pop_counts.values())
    if total_pop > 0:
        sizes = [pop_counts[cat] / total_pop * 100 for cat in categories]
        wedges, _, _ = ax.pie(sizes, labels=categories, colors=cat_colors, autopct='%1.0f%%')
        for w in wedges:
            w.set_alpha(0.7)
        ax.set_title('Population Trajectory Distribution')

    plt.suptitle('EXP-2035: Post-Meal Trajectories', fontsize=14)
    plt.tight_layout()
    plt.savefig(f'{FIG_DIR}/meal-fig05-trajectories.png', dpi=150)
    plt.close()
    print(f"  → Saved meal-fig05-trajectories.png")

pop_return = np.mean([exp2035[n]['percentages'].get('spike_return', 0) for n in exp2035])
pop_sustained = np.mean([exp2035[n]['percentages'].get('sustained_rise', 0) for n in exp2035])
verdict_2035 = f"RETURN={pop_return:.0f}%_SUSTAINED={pop_sustained:.0f}%"
results['EXP-2035'] = verdict_2035
print(f"\n  ✓ EXP-2035 verdict: {verdict_2035}")


# ══════════════════════════════════════════════════════════════
# EXP-2036: Second Meal Effect
# ══════════════════════════════════════════════════════════════
print("\n" + "#" * 70)
print("# Running EXP-2036")
print("#" * 70)
print("\n" + "=" * 70)
print("EXP-2036: Second Meal Effect")
print("=" * 70)

exp2036 = {}
for p in patients:
    name = p['name']
    df = p['df']
    carbs = df['carbs'].values.astype(float) if 'carbs' in df.columns else np.zeros(len(df['glucose'].values))
    glucose = df['glucose'].values.astype(float)

    first_meal_spikes = []
    second_meal_spikes = []

    # Find meal pairs: two meals within 2-4h
    meal_indices = [i for i in range(len(carbs)) if carbs[i] >= 15]

    for m_idx in range(len(meal_indices)):
        i = meal_indices[m_idx]
        if not np.isfinite(glucose[i]) or glucose[i] < 50:
            continue

        # Is this a "first" meal? No meal in prior 4h
        is_first = True
        for j in range(max(0, m_idx - 5), m_idx):
            if meal_indices[j] > i - 48:  # within 4h
                is_first = False
                break

        if not is_first:
            continue

        # Spike for first meal
        post1 = glucose[i:min(i + 36, len(glucose))]
        valid1 = post1[np.isfinite(post1)]
        if len(valid1) < 12:
            continue
        spike1 = float(np.max(valid1) - glucose[i])
        first_meal_spikes.append(spike1)

        # Find second meal within 2-5h
        for j in range(m_idx + 1, min(m_idx + 10, len(meal_indices))):
            i2 = meal_indices[j]
            gap_hours = (i2 - i) * 5 / 60
            if gap_hours < 2 or gap_hours > 5:
                continue
            if not np.isfinite(glucose[i2]) or glucose[i2] < 50:
                continue
            post2 = glucose[i2:min(i2 + 36, len(glucose))]
            valid2 = post2[np.isfinite(post2)]
            if len(valid2) < 12:
                continue
            spike2 = float(np.max(valid2) - glucose[i2])
            second_meal_spikes.append(spike2)
            break

    if len(first_meal_spikes) < 10 or len(second_meal_spikes) < 10:
        exp2036[name] = {'status': 'insufficient',
                         'first_n': len(first_meal_spikes),
                         'second_n': len(second_meal_spikes)}
        print(f"  {name}: first={len(first_meal_spikes)} second={len(second_meal_spikes)}")
        continue

    first_mean = float(np.mean(first_meal_spikes))
    second_mean = float(np.mean(second_meal_spikes))
    diff = second_mean - first_mean

    exp2036[name] = {
        'first_meal_n': len(first_meal_spikes),
        'second_meal_n': len(second_meal_spikes),
        'first_spike': round(first_mean, 1),
        'second_spike': round(second_mean, 1),
        'second_meal_effect': round(diff, 1),
        'pct_change': round(diff / first_mean * 100, 1) if first_mean != 0 else 0,
    }

    print(f"  {name}: first={first_mean:.0f} second={second_mean:.0f} Δ={diff:+.0f}mg/dL "
          f"({diff/first_mean*100:+.0f}%)")

if MAKE_FIGS:
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    ax = axes[0]
    names_list = [n for n in exp2036 if 'first_spike' in exp2036[n]]
    first_s = [exp2036[n]['first_spike'] for n in names_list]
    second_s = [exp2036[n]['second_spike'] for n in names_list]
    x = np.arange(len(names_list))
    width = 0.35
    ax.bar(x - width/2, first_s, width, label='First Meal', color='green', alpha=0.7)
    ax.bar(x + width/2, second_s, width, label='Second Meal', color='red', alpha=0.7)
    ax.set_xticks(x)
    ax.set_xticklabels(names_list)
    ax.set_ylabel('Mean Spike (mg/dL)')
    ax.set_title('First vs Second Meal Spike')
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')

    ax = axes[1]
    effects = [exp2036[n]['second_meal_effect'] for n in names_list]
    colors = ['red' if e > 5 else 'green' if e < -5 else 'gray' for e in effects]
    ax.barh(range(len(names_list)), effects, color=colors, alpha=0.7)
    ax.set_yticks(range(len(names_list)))
    ax.set_yticklabels(names_list)
    ax.set_xlabel('Second Meal Effect (mg/dL)')
    ax.set_title('Additional Spike from Second Meal')
    ax.axvline(0, color='black', ls='--', alpha=0.5)
    ax.grid(True, alpha=0.3, axis='x')

    plt.suptitle('EXP-2036: Second Meal Effect', fontsize=14)
    plt.tight_layout()
    plt.savefig(f'{FIG_DIR}/meal-fig06-secondmeal.png', dpi=150)
    plt.close()
    print(f"  → Saved meal-fig06-secondmeal.png")

all_effects = [exp2036[n]['second_meal_effect'] for n in exp2036 if 'second_meal_effect' in exp2036[n]]
verdict_2036 = f"SECOND_MEAL_Δ={np.mean(all_effects):+.0f}mg/dL"
results['EXP-2036'] = verdict_2036
print(f"\n  ✓ EXP-2036 verdict: {verdict_2036}")


# ══════════════════════════════════════════════════════════════
# EXP-2037: Time-of-Day Meal Response
# ══════════════════════════════════════════════════════════════
print("\n" + "#" * 70)
print("# Running EXP-2037")
print("#" * 70)
print("\n" + "=" * 70)
print("EXP-2037: Time-of-Day Meal Response")
print("=" * 70)

exp2037 = {}
for p in patients:
    name = p['name']
    df = p['df']
    meals = find_meals(df, min_carbs=15)

    tod_spikes = {'breakfast': [], 'lunch': [], 'dinner': [], 'snack': []}

    for meal in meals:
        if not np.isfinite(meal['pre_glucose']):
            continue
        post = meal['post_glucose']
        valid_post = post[np.isfinite(post)]
        if len(valid_post) < 12:
            continue
        spike = float(np.max(valid_post[:36]) - meal['pre_glucose'])

        hour = meal['hour']
        if 5 <= hour < 10:
            tod_spikes['breakfast'].append(spike)
        elif 10 <= hour < 14:
            tod_spikes['lunch'].append(spike)
        elif 16 <= hour < 21:
            tod_spikes['dinner'].append(spike)
        else:
            tod_spikes['snack'].append(spike)

    result = {}
    for tod, spikes in tod_spikes.items():
        if len(spikes) >= 5:
            result[tod] = {
                'n': len(spikes),
                'mean_spike': round(float(np.mean(spikes)), 1),
                'median_spike': round(float(np.median(spikes)), 1),
            }

    # Breakfast vs dinner difference
    breakfast_spike = result.get('breakfast', {}).get('mean_spike', np.nan)
    dinner_spike = result.get('dinner', {}).get('mean_spike', np.nan)
    bkf_dinner_diff = breakfast_spike - dinner_spike if np.isfinite(breakfast_spike) and np.isfinite(dinner_spike) else np.nan

    exp2037[name] = {
        'tod_results': result,
        'breakfast_dinner_diff': round(bkf_dinner_diff, 1) if np.isfinite(bkf_dinner_diff) else None,
    }

    bkf = f"bkf={result.get('breakfast', {}).get('mean_spike', 'N/A')}"
    lch = f"lunch={result.get('lunch', {}).get('mean_spike', 'N/A')}"
    din = f"dinner={result.get('dinner', {}).get('mean_spike', 'N/A')}"
    diff_str = f"bkf-din={bkf_dinner_diff:+.0f}" if np.isfinite(bkf_dinner_diff) else "bkf-din=N/A"
    print(f"  {name}: {bkf} {lch} {din} {diff_str}")

if MAKE_FIGS:
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    ax = axes[0]
    names_list = list(exp2037.keys())
    tods = ['breakfast', 'lunch', 'dinner', 'snack']
    tod_colors = ['coral', 'gold', 'steelblue', 'gray']
    x = np.arange(len(names_list))
    width = 0.2
    for ti, (tod, color) in enumerate(zip(tods, tod_colors)):
        vals = [exp2037[n]['tod_results'].get(tod, {}).get('mean_spike', 0) for n in names_list]
        ax.bar(x + (ti - 1.5) * width, vals, width, label=tod, color=color, alpha=0.7)
    ax.set_xticks(x)
    ax.set_xticklabels(names_list)
    ax.set_ylabel('Mean Spike (mg/dL)')
    ax.set_title('Spike by Time of Day')
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')

    ax = axes[1]
    diffs = [exp2037[n].get('breakfast_dinner_diff') for n in names_list]
    valid_diffs = [(n, d) for n, d in zip(names_list, diffs) if d is not None]
    if valid_diffs:
        vd_names = [x[0] for x in valid_diffs]
        vd_vals = [x[1] for x in valid_diffs]
        colors = ['red' if d > 10 else 'green' if d < -10 else 'gray' for d in vd_vals]
        ax.barh(range(len(vd_names)), vd_vals, color=colors, alpha=0.7)
        ax.set_yticks(range(len(vd_names)))
        ax.set_yticklabels(vd_names)
        ax.set_xlabel('Breakfast − Dinner Spike (mg/dL)')
        ax.set_title('Breakfast Effect (red = worse mornings)')
        ax.axvline(0, color='black', ls='--', alpha=0.5)
        ax.grid(True, alpha=0.3, axis='x')

    plt.suptitle('EXP-2037: Time-of-Day Meal Response', fontsize=14)
    plt.tight_layout()
    plt.savefig(f'{FIG_DIR}/meal-fig07-timeofday.png', dpi=150)
    plt.close()
    print(f"  → Saved meal-fig07-timeofday.png")

bkf_diffs = [exp2037[n]['breakfast_dinner_diff'] for n in exp2037
             if exp2037[n].get('breakfast_dinner_diff') is not None]
verdict_2037 = f"BREAKFAST_WORSE={np.mean(bkf_diffs):+.0f}mg/dL" if bkf_diffs else "INSUFFICIENT"
results['EXP-2037'] = verdict_2037
print(f"\n  ✓ EXP-2037 verdict: {verdict_2037}")


# ══════════════════════════════════════════════════════════════
# EXP-2038: Synthesis — Personalized Meal Response Profiles
# ══════════════════════════════════════════════════════════════
print("\n" + "#" * 70)
print("# Running EXP-2038")
print("#" * 70)
print("\n" + "=" * 70)
print("EXP-2038: Synthesis — Personalized Meal Response Profiles")
print("=" * 70)

exp2038 = {}
for p in patients:
    name = p['name']
    profile = {}

    # Absorption
    if name in exp2031 and 'peak_time_min' in exp2031[name]:
        profile['absorption_speed'] = exp2031[name]['speed']
        profile['peak_time_min'] = exp2031[name]['peak_time_min']
        profile['peak_magnitude'] = exp2031[name]['peak_magnitude']

    # Pre-meal prediction
    if name in exp2032 and 'correlation' in exp2032[name]:
        profile['premeal_corr'] = exp2032[name]['correlation']

    # Bolus timing
    if name in exp2033:
        profile['pre_bolus_spike'] = exp2033[name].get('pre_bolus_spike')
        profile['no_bolus_spike'] = exp2033[name].get('no_bolus_spike')
        pre = exp2033[name].get('pre_bolus_spike')
        no = exp2033[name].get('no_bolus_spike')
        if pre is not None and no is not None and np.isfinite(pre) and np.isfinite(no):
            profile['pre_bolus_benefit'] = round(no - pre, 1)

    # Dose response
    if name in exp2034 and 'slope_mg_per_g' in exp2034[name]:
        profile['carb_sensitivity'] = exp2034[name]['slope_mg_per_g']

    # Trajectory
    if name in exp2035 and 'dominant' in exp2035[name]:
        profile['dominant_trajectory'] = exp2035[name]['dominant']

    # Second meal
    if name in exp2036 and 'second_meal_effect' in exp2036[name]:
        profile['second_meal_effect'] = exp2036[name]['second_meal_effect']

    # TOD
    if name in exp2037 and exp2037[name].get('breakfast_dinner_diff') is not None:
        profile['breakfast_dinner_diff'] = exp2037[name]['breakfast_dinner_diff']

    # Meal strategy recommendation
    strategies = []
    if profile.get('absorption_speed') == 'SLOW':
        strategies.append('EXTEND_BOLUS')
    if profile.get('pre_bolus_benefit', 0) > 20:
        strategies.append('ENCOURAGE_PREBOLUS')
    if profile.get('breakfast_dinner_diff', 0) > 15:
        strategies.append('MORNING_ISF_ADJUSTMENT')
    if profile.get('second_meal_effect', 0) > 15:
        strategies.append('SECOND_MEAL_COMPENSATION')
    profile['strategies'] = strategies

    exp2038[name] = profile

    speed = profile.get('absorption_speed', '?')
    benefit = profile.get('pre_bolus_benefit', '?')
    traj = profile.get('dominant_trajectory', '?')
    strats = ','.join(strategies) if strategies else 'NONE'
    print(f"  {name}: speed={speed} pre_bolus_benefit={benefit} "
          f"trajectory={traj} strategies={strats}")

if MAKE_FIGS:
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))

    ax = axes[0, 0]
    names_list = [n for n in exp2038 if 'peak_time_min' in exp2038[n]]
    peaks = [exp2038[n]['peak_time_min'] for n in names_list]
    mags = [exp2038[n].get('peak_magnitude', 0) for n in names_list]
    speeds = [exp2038[n].get('absorption_speed', '?') for n in names_list]
    speed_colors = {'FAST': 'green', 'MODERATE': 'orange', 'SLOW': 'red'}
    c = [speed_colors.get(s, 'gray') for s in speeds]
    ax.scatter(peaks, mags, c=c, s=80, zorder=3)
    for n, pk, mg in zip(names_list, peaks, mags):
        ax.annotate(n, (pk, mg), fontsize=9)
    ax.set_xlabel('Peak Time (min)')
    ax.set_ylabel('Peak Spike (mg/dL)')
    ax.set_title('Absorption Profile (green=fast, red=slow)')
    ax.grid(True, alpha=0.3)

    ax = axes[0, 1]
    names_strat = list(exp2038.keys())
    n_strats = [len(exp2038[n].get('strategies', [])) for n in names_strat]
    colors = ['red' if s >= 2 else 'orange' if s >= 1 else 'green' for s in n_strats]
    ax.barh(range(len(names_strat)), n_strats, color=colors, alpha=0.7)
    ax.set_yticks(range(len(names_strat)))
    ax.set_yticklabels(names_strat)
    ax.set_xlabel('Number of Strategies')
    ax.set_title('Personalized Strategy Count')
    ax.grid(True, alpha=0.3, axis='x')

    ax = axes[1, 0]
    names_timing = [n for n in exp2038 if 'pre_bolus_benefit' in exp2038[n]]
    benefits = [exp2038[n]['pre_bolus_benefit'] for n in names_timing]
    colors = ['green' if b > 10 else 'gray' for b in benefits]
    ax.barh(range(len(names_timing)), benefits, color=colors, alpha=0.7)
    ax.set_yticks(range(len(names_timing)))
    ax.set_yticklabels(names_timing)
    ax.set_xlabel('Pre-Bolus Benefit (mg/dL spike reduction)')
    ax.set_title('Who Benefits from Pre-Bolusing?')
    ax.axvline(0, color='black', ls='--', alpha=0.5)
    ax.grid(True, alpha=0.3, axis='x')

    ax = axes[1, 1]
    names_bkf = [n for n in exp2038 if 'breakfast_dinner_diff' in exp2038[n]]
    bkf_d = [exp2038[n]['breakfast_dinner_diff'] for n in names_bkf]
    colors = ['red' if d > 10 else 'green' if d < -10 else 'gray' for d in bkf_d]
    ax.barh(range(len(names_bkf)), bkf_d, color=colors, alpha=0.7)
    ax.set_yticks(range(len(names_bkf)))
    ax.set_yticklabels(names_bkf)
    ax.set_xlabel('Breakfast − Dinner Spike (mg/dL)')
    ax.set_title('Morning vs Evening Insulin Resistance')
    ax.axvline(0, color='black', ls='--', alpha=0.5)
    ax.grid(True, alpha=0.3, axis='x')

    plt.suptitle('EXP-2038: Personalized Meal Profiles', fontsize=14)
    plt.tight_layout()
    plt.savefig(f'{FIG_DIR}/meal-fig08-synthesis.png', dpi=150)
    plt.close()
    print(f"  → Saved meal-fig08-synthesis.png")

with_strats = sum(1 for v in exp2038.values() if len(v.get('strategies', [])) > 0)
verdict_2038 = f"STRATEGIES_{with_strats}/11_PATIENTS"
results['EXP-2038'] = verdict_2038
print(f"\n  ✓ EXP-2038 verdict: {verdict_2038}")


# ══════════════════════════════════════════════════════════════
# SYNTHESIS
# ══════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("SYNTHESIS: Meal Response & Absorption Dynamics")
print("=" * 70)
for k, v in sorted(results.items()):
    print(f"  {k}: {v}")

output = {
    'experiment_group': 'EXP-2031–2038',
    'title': 'Meal Response & Absorption Dynamics',
    'results': results,
    'exp2031_absorption': {k: {kk: vv for kk, vv in v.items() if kk != 'mean_curve'} for k, v in exp2031.items()},
    'exp2032_premeal': exp2032,
    'exp2033_timing': exp2033,
    'exp2034_doseresponse': exp2034,
    'exp2035_trajectories': exp2035,
    'exp2036_secondmeal': exp2036,
    'exp2037_timeofday': exp2037,
    'exp2038_synthesis': exp2038,
}

with open(f'{EXP_DIR}/exp-2031_meal_response.json', 'w') as f:
    json.dump(output, f, indent=2, default=str)
print(f"\nSaved results to {EXP_DIR}/exp-2031_meal_response.json")
