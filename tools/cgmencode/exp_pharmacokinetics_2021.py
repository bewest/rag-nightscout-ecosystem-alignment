#!/usr/bin/env python3
"""
EXP-2021–2028: Insulin Pharmacokinetics & Temporal Dynamics

Measuring real-world insulin action curves, DIA, and temporal stability
from CGM/AID data. These directly affect ISF/CR/basal accuracy.

EXP-2021: Effective DIA from correction tail analysis
EXP-2022: Insulin onset and peak timing from bolus responses
EXP-2023: Stacking risk — insulin overlap from rapid corrections
EXP-2024: Temporal stability of therapy parameters (month-over-month)
EXP-2025: Weekday vs weekend glycemic patterns
EXP-2026: Sensor artifact detection (compression lows, warmup)
EXP-2027: Hidden variable identification (what predicts TIR beyond known features)
EXP-2028: Synthesis — personalized pharmacokinetic profiles

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


def glucose_metrics(glucose):
    valid = glucose[np.isfinite(glucose)]
    if len(valid) < 100:
        return {'tir': np.nan, 'tbr': np.nan, 'tar': np.nan, 'mean': np.nan, 'cv': np.nan}
    return {
        'tir': float(np.mean((valid >= TARGET_LOW) & (valid <= TARGET_HIGH)) * 100),
        'tbr': float(np.mean(valid < TARGET_LOW) * 100),
        'tar': float(np.mean(valid > TARGET_HIGH) * 100),
        'mean': float(np.nanmean(valid)),
        'cv': float(np.nanstd(valid) / np.nanmean(valid) * 100) if np.nanmean(valid) > 0 else np.nan,
    }


patients = load_patients(PATIENT_DIR)
results = {}


# ══════════════════════════════════════════════════════════════
# EXP-2021: Effective DIA from Correction Tail Analysis
# ══════════════════════════════════════════════════════════════
print("\n" + "#" * 70)
print("# Running EXP-2021")
print("#" * 70)
print("\n" + "=" * 70)
print("EXP-2021: Effective DIA from Correction Tail Analysis")
print("=" * 70)

exp2021 = {}
for p in patients:
    name = p['name']
    df = p['df']
    glucose = df['glucose'].values.astype(float)
    bolus = df['bolus'].values.astype(float) if 'bolus' in df.columns else np.zeros(len(glucose))
    carbs = df['carbs'].values.astype(float) if 'carbs' in df.columns else np.zeros(len(glucose))
    iob = df['iob'].values.astype(float) if 'iob' in df.columns else np.full(len(glucose), np.nan)

    # Find isolated corrections: bolus > 0.5U, no carbs ±2h, glucose > 140
    # Track glucose for 6h after correction
    correction_curves = []
    for i in range(len(glucose) - 72):
        if bolus[i] < 0.5:
            continue
        carb_window = carbs[max(0, i-24):min(len(carbs), i+24)]
        if np.nansum(carb_window) > 1:
            continue
        if not np.isfinite(glucose[i]) or glucose[i] < 140:
            continue
        # No additional bolus within 3h
        bolus_after = bolus[i+1:min(i+36, len(bolus))]
        if np.nansum(bolus_after) > 0.1:
            continue

        window = glucose[i:i + 72]  # 6h
        if np.sum(np.isfinite(window)) < 50:
            continue

        # Normalize: delta from starting glucose, per unit of insulin
        baseline = glucose[i]
        delta = (window - baseline) / bolus[i]
        correction_curves.append(delta)

    if len(correction_curves) < 5:
        exp2021[name] = {'n_corrections': len(correction_curves), 'status': 'insufficient'}
        print(f"  {name}: only {len(correction_curves)} isolated corrections")
        continue

    curves = np.array(correction_curves)
    mean_curve = np.nanmean(curves, axis=0)

    # Find DIA: when effect reaches 90% of maximum
    max_effect = np.nanmin(mean_curve)  # most negative = maximum glucose drop
    max_effect_idx = np.nanargmin(mean_curve)

    # Find 90% recovery: when curve returns to within 10% of max effect
    dia_idx = len(mean_curve) - 1
    threshold_90 = max_effect * 0.1  # 90% of effect has dissipated
    for ri in range(max_effect_idx, len(mean_curve)):
        if mean_curve[ri] > threshold_90:
            dia_idx = ri
            break

    dia_hours = dia_idx * 5 / 60
    peak_time_hours = max_effect_idx * 5 / 60
    max_effect_per_unit = float(max_effect)

    # Fit exponential decay: delta(t) = A * (1 - exp(-t/tau))
    # Simplified: tau from peak time
    tau_hours = peak_time_hours / 1.0 if peak_time_hours > 0 else 2.0

    exp2021[name] = {
        'n_corrections': len(correction_curves),
        'dia_hours': round(dia_hours, 1),
        'peak_time_hours': round(peak_time_hours, 1),
        'max_effect_per_unit': round(max_effect_per_unit, 1),
        'tau_hours': round(tau_hours, 1),
        'mean_curve': [round(float(v), 2) for v in mean_curve],
    }

    print(f"  {name}: n={len(correction_curves)} DIA={dia_hours:.1f}h "
          f"peak={peak_time_hours:.1f}h effect={max_effect_per_unit:.0f}mg/dL/U tau={tau_hours:.1f}h")

if MAKE_FIGS:
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    time_h = np.arange(72) * 5 / 60

    ax = axes[0, 0]
    for p_data in patients:
        name = p_data['name']
        if name not in exp2021 or 'mean_curve' not in exp2021[name]:
            continue
        curve = exp2021[name]['mean_curve']
        ax.plot(time_h[:len(curve)], curve, '-', label=f"{name} (DIA={exp2021[name]['dia_hours']}h)", alpha=0.7)
    ax.axhline(0, color='gray', ls='--', alpha=0.5)
    ax.set_xlabel('Time (hours)')
    ax.set_ylabel('Glucose Change per Unit Insulin (mg/dL/U)')
    ax.set_title('Insulin Action Curves (normalized per unit)')
    ax.legend(fontsize=7, ncol=2)
    ax.grid(True, alpha=0.3)

    ax = axes[0, 1]
    dias = [exp2021[n]['dia_hours'] for n in exp2021 if 'dia_hours' in exp2021[n]]
    dia_names = [n for n in exp2021 if 'dia_hours' in exp2021[n]]
    colors = ['red' if d > 5 else 'green' for d in dias]
    ax.barh(range(len(dia_names)), dias, color=colors, alpha=0.7)
    ax.set_yticks(range(len(dia_names)))
    ax.set_yticklabels(dia_names)
    ax.set_xlabel('Effective DIA (hours)')
    ax.set_title('Duration of Insulin Action (red >5h)')
    ax.axvline(5, color='black', ls='--', alpha=0.5, label='Typical profile DIA')
    ax.legend()
    ax.grid(True, alpha=0.3, axis='x')

    ax = axes[1, 0]
    peaks = [exp2021[n]['peak_time_hours'] for n in dia_names]
    effects = [abs(exp2021[n]['max_effect_per_unit']) for n in dia_names]
    ax.scatter(peaks, effects, s=60, zorder=3)
    for n, pk, ef in zip(dia_names, peaks, effects):
        ax.annotate(n, (pk, ef), fontsize=9)
    ax.set_xlabel('Time to Peak Effect (hours)')
    ax.set_ylabel('Max Effect (mg/dL per U)')
    ax.set_title('Peak Time vs Maximum Effect')
    ax.grid(True, alpha=0.3)

    ax = axes[1, 1]
    n_corr = [exp2021[n]['n_corrections'] for n in dia_names]
    ax.bar(range(len(dia_names)), n_corr, color='steelblue', alpha=0.7)
    ax.set_xticks(range(len(dia_names)))
    ax.set_xticklabels(dia_names)
    ax.set_ylabel('Number of Isolated Corrections')
    ax.set_title('Data Points for DIA Estimation')
    ax.grid(True, alpha=0.3, axis='y')

    plt.suptitle('EXP-2021: Effective DIA from Correction Tail Analysis', fontsize=14)
    plt.tight_layout()
    plt.savefig(f'{FIG_DIR}/pk-fig01-dia.png', dpi=150)
    plt.close()
    print(f"  → Saved pk-fig01-dia.png")

all_dias = [exp2021[n]['dia_hours'] for n in exp2021 if 'dia_hours' in exp2021[n]]
verdict_2021 = f"MEDIAN_DIA={np.median(all_dias):.1f}h_RANGE={min(all_dias):.1f}-{max(all_dias):.1f}h"
results['EXP-2021'] = verdict_2021
print(f"\n  ✓ EXP-2021 verdict: {verdict_2021}")


# ══════════════════════════════════════════════════════════════
# EXP-2022: Insulin Onset and Peak from Bolus Responses
# ══════════════════════════════════════════════════════════════
print("\n" + "#" * 70)
print("# Running EXP-2022")
print("#" * 70)
print("\n" + "=" * 70)
print("EXP-2022: Insulin Onset and Peak Timing")
print("=" * 70)

exp2022 = {}
for p in patients:
    name = p['name']
    df = p['df']
    glucose = df['glucose'].values.astype(float)
    bolus = df['bolus'].values.astype(float) if 'bolus' in df.columns else np.zeros(len(glucose))
    carbs = df['carbs'].values.astype(float) if 'carbs' in df.columns else np.zeros(len(glucose))

    # Find correction boluses with clean follow-up
    onset_times = []
    peak_times = []
    for i in range(len(glucose) - 36):
        if bolus[i] < 0.3:
            continue
        carb_window = carbs[max(0, i-12):min(len(carbs), i+12)]
        if np.nansum(carb_window) > 1:
            continue
        if not np.isfinite(glucose[i]) or glucose[i] < 120:
            continue

        window = glucose[i:i + 36]  # 3h
        if np.sum(np.isfinite(window)) < 20:
            continue

        # Onset: first time glucose drops by > 5 mg/dL from peak
        peak_g = glucose[i]
        onset_found = False
        for j in range(1, len(window)):
            if np.isfinite(window[j]) and peak_g - window[j] > 5:
                onset_times.append(j * 5)  # minutes
                onset_found = True
                break

        # Peak effect: maximum rate of glucose decline
        dg = np.diff(window)
        valid_dg = np.where(np.isfinite(dg))[0]
        if len(valid_dg) > 3:
            # Smooth with rolling window
            dg_smooth = np.convolve(dg[np.isfinite(dg)], np.ones(3)/3, mode='valid')
            if len(dg_smooth) > 0:
                peak_decline_idx = np.argmin(dg_smooth)
                peak_times.append(peak_decline_idx * 5)

    if len(onset_times) < 5:
        exp2022[name] = {'status': 'insufficient', 'n': len(onset_times)}
        print(f"  {name}: only {len(onset_times)} events")
        continue

    exp2022[name] = {
        'n_events': len(onset_times),
        'onset_median_min': int(np.median(onset_times)),
        'onset_p25_min': int(np.percentile(onset_times, 25)),
        'onset_p75_min': int(np.percentile(onset_times, 75)),
        'peak_median_min': int(np.median(peak_times)) if peak_times else np.nan,
    }

    print(f"  {name}: n={len(onset_times)} onset={np.median(onset_times):.0f}min "
          f"[{np.percentile(onset_times, 25):.0f}-{np.percentile(onset_times, 75):.0f}] "
          f"peak_decline={np.median(peak_times):.0f}min")

if MAKE_FIGS:
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    ax = axes[0]
    names_list = [n for n in exp2022 if 'onset_median_min' in exp2022[n]]
    onsets = [exp2022[n]['onset_median_min'] for n in names_list]
    ax.barh(range(len(names_list)), onsets, color='steelblue', alpha=0.7)
    ax.set_yticks(range(len(names_list)))
    ax.set_yticklabels(names_list)
    ax.set_xlabel('Median Onset Time (min)')
    ax.set_title('Time to First 5 mg/dL Drop After Correction')
    ax.grid(True, alpha=0.3, axis='x')

    ax = axes[1]
    peaks = [exp2022[n].get('peak_median_min', 0) for n in names_list]
    ax.scatter(onsets, peaks, s=60, zorder=3)
    for n, o, pk in zip(names_list, onsets, peaks):
        ax.annotate(n, (o, pk), fontsize=9)
    ax.set_xlabel('Onset Time (min)')
    ax.set_ylabel('Peak Decline Time (min)')
    ax.set_title('Onset vs Peak Effect Timing')
    ax.grid(True, alpha=0.3)

    plt.suptitle('EXP-2022: Insulin Onset and Peak Timing', fontsize=14)
    plt.tight_layout()
    plt.savefig(f'{FIG_DIR}/pk-fig02-onset-peak.png', dpi=150)
    plt.close()
    print(f"  → Saved pk-fig02-onset-peak.png")

all_onsets = [exp2022[n]['onset_median_min'] for n in exp2022 if 'onset_median_min' in exp2022[n]]
verdict_2022 = f"MEDIAN_ONSET={np.median(all_onsets):.0f}min"
results['EXP-2022'] = verdict_2022
print(f"\n  ✓ EXP-2022 verdict: {verdict_2022}")


# ══════════════════════════════════════════════════════════════
# EXP-2023: Stacking Risk — Insulin Overlap
# ══════════════════════════════════════════════════════════════
print("\n" + "#" * 70)
print("# Running EXP-2023")
print("#" * 70)
print("\n" + "=" * 70)
print("EXP-2023: Stacking Risk — Insulin Overlap from Rapid Corrections")
print("=" * 70)

exp2023 = {}
for p in patients:
    name = p['name']
    df = p['df']
    glucose = df['glucose'].values.astype(float)
    bolus = df['bolus'].values.astype(float) if 'bolus' in df.columns else np.zeros(len(glucose))
    iob = df['iob'].values.astype(float) if 'iob' in df.columns else np.full(len(glucose), np.nan)

    # Find rapid correction sequences: 2+ boluses within 2h
    stacking_events = 0
    stacking_hypos = 0
    non_stacking_events = 0
    non_stacking_hypos = 0
    total_boluses = 0

    for i in range(24, len(glucose) - 24):
        if bolus[i] < 0.3:
            continue
        total_boluses += 1

        # Check for prior bolus within 2h
        prior_boluses = bolus[max(0, i-24):i]
        has_stack = np.nansum(prior_boluses) > 0.3

        # Check for hypo within 3h
        future_g = glucose[i:min(i + 36, len(glucose))]
        has_hypo = np.any(future_g[np.isfinite(future_g)] < HYPO_THRESH) if np.any(np.isfinite(future_g)) else False

        if has_stack:
            stacking_events += 1
            if has_hypo:
                stacking_hypos += 1
        else:
            non_stacking_events += 1
            if has_hypo:
                non_stacking_hypos += 1

    stack_hypo_rate = stacking_hypos / stacking_events * 100 if stacking_events > 0 else 0
    non_stack_hypo_rate = non_stacking_hypos / non_stacking_events * 100 if non_stacking_events > 0 else 0
    risk_ratio = stack_hypo_rate / non_stack_hypo_rate if non_stack_hypo_rate > 0 else np.nan

    exp2023[name] = {
        'total_boluses': total_boluses,
        'stacking_events': stacking_events,
        'stacking_pct': round(stacking_events / total_boluses * 100, 1) if total_boluses > 0 else 0,
        'stack_hypo_rate': round(stack_hypo_rate, 1),
        'non_stack_hypo_rate': round(non_stack_hypo_rate, 1),
        'risk_ratio': round(risk_ratio, 2) if np.isfinite(risk_ratio) else np.nan,
    }

    print(f"  {name}: boluses={total_boluses} stacked={stacking_events}({stacking_events/total_boluses*100:.0f}%) "
          f"hypo_rate: stacked={stack_hypo_rate:.0f}% single={non_stack_hypo_rate:.0f}% RR={risk_ratio:.2f}")

if MAKE_FIGS:
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    ax = axes[0]
    names_list = list(exp2023.keys())
    stack_rates = [exp2023[n]['stack_hypo_rate'] for n in names_list]
    non_stack_rates = [exp2023[n]['non_stack_hypo_rate'] for n in names_list]
    x = np.arange(len(names_list))
    width = 0.35
    ax.bar(x - width/2, non_stack_rates, width, label='Single Bolus', color='green', alpha=0.7)
    ax.bar(x + width/2, stack_rates, width, label='Stacked Bolus', color='red', alpha=0.7)
    ax.set_xticks(x)
    ax.set_xticklabels(names_list)
    ax.set_ylabel('Hypo Rate Within 3h (%)')
    ax.set_title('Hypo Risk: Single vs Stacked Boluses')
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')

    ax = axes[1]
    risk_ratios = [exp2023[n]['risk_ratio'] for n in names_list if np.isfinite(exp2023[n].get('risk_ratio', np.nan))]
    rr_names = [n for n in names_list if np.isfinite(exp2023[n].get('risk_ratio', np.nan))]
    colors = ['red' if rr > 1.5 else 'orange' if rr > 1 else 'green' for rr in risk_ratios]
    ax.barh(range(len(rr_names)), risk_ratios, color=colors, alpha=0.7)
    ax.set_yticks(range(len(rr_names)))
    ax.set_yticklabels(rr_names)
    ax.set_xlabel('Risk Ratio (stacked/single)')
    ax.set_title('Stacking Risk Ratio (red >1.5×)')
    ax.axvline(1.0, color='black', ls='--', alpha=0.5)
    ax.grid(True, alpha=0.3, axis='x')

    plt.suptitle('EXP-2023: Insulin Stacking Risk', fontsize=14)
    plt.tight_layout()
    plt.savefig(f'{FIG_DIR}/pk-fig03-stacking.png', dpi=150)
    plt.close()
    print(f"  → Saved pk-fig03-stacking.png")

all_rr = [exp2023[n]['risk_ratio'] for n in exp2023 if np.isfinite(exp2023[n].get('risk_ratio', np.nan))]
verdict_2023 = f"STACKING_RR={np.median(all_rr):.2f}x_MEDIAN"
results['EXP-2023'] = verdict_2023
print(f"\n  ✓ EXP-2023 verdict: {verdict_2023}")


# ══════════════════════════════════════════════════════════════
# EXP-2024: Temporal Stability (Month-over-Month)
# ══════════════════════════════════════════════════════════════
print("\n" + "#" * 70)
print("# Running EXP-2024")
print("#" * 70)
print("\n" + "=" * 70)
print("EXP-2024: Temporal Stability of Therapy Parameters")
print("=" * 70)

exp2024 = {}
for p in patients:
    name = p['name']
    df = p['df']
    glucose = df['glucose'].values.astype(float)
    n_days = len(glucose) // STEPS_PER_DAY

    # Split into 30-day months
    months = []
    for m in range(n_days // 30):
        start = m * 30 * STEPS_PER_DAY
        end = start + 30 * STEPS_PER_DAY
        if end > len(glucose):
            break
        month_g = glucose[start:end]
        metrics = glucose_metrics(month_g)
        months.append({
            'month': m + 1,
            **metrics,
        })

    if len(months) < 3:
        exp2024[name] = {'status': 'insufficient', 'months': len(months)}
        print(f"  {name}: only {len(months)} months")
        continue

    # Trend analysis: is TIR improving or declining?
    tirs = [m['tir'] for m in months]
    tbrs = [m['tbr'] for m in months]
    cvs = [m['cv'] for m in months]

    # Linear regression for trend
    x = np.arange(len(tirs))
    if len(x) >= 3:
        tir_slope = np.polyfit(x, tirs, 1)[0]  # pp per month
        tbr_slope = np.polyfit(x, tbrs, 1)[0]
        cv_slope = np.polyfit(x, cvs, 1)[0]
    else:
        tir_slope = tbr_slope = cv_slope = 0

    # Stability: SD of monthly TIR
    tir_sd = float(np.std(tirs))

    exp2024[name] = {
        'n_months': len(months),
        'monthly_tir': [round(t, 1) for t in tirs],
        'monthly_tbr': [round(t, 1) for t in tbrs],
        'tir_slope_per_month': round(tir_slope, 2),
        'tbr_slope_per_month': round(tbr_slope, 2),
        'cv_slope_per_month': round(cv_slope, 2),
        'tir_sd': round(tir_sd, 1),
        'tir_trend': 'improving' if tir_slope > 0.5 else 'declining' if tir_slope < -0.5 else 'stable',
    }

    print(f"  {name}: {len(months)} months TIR={tirs[0]:.0f}→{tirs[-1]:.0f}% "
          f"slope={tir_slope:+.1f}pp/mo SD={tir_sd:.1f} trend={exp2024[name]['tir_trend']}")

if MAKE_FIGS:
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    ax = axes[0, 0]
    for n in exp2024:
        if 'monthly_tir' not in exp2024[n]:
            continue
        tirs = exp2024[n]['monthly_tir']
        ax.plot(range(1, len(tirs) + 1), tirs, 'o-', label=n, alpha=0.7, markersize=4)
    ax.set_xlabel('Month')
    ax.set_ylabel('TIR (%)')
    ax.set_title('Monthly TIR Trajectory')
    ax.legend(fontsize=8, ncol=2)
    ax.grid(True, alpha=0.3)

    ax = axes[0, 1]
    names_stable = [n for n in exp2024 if 'tir_slope_per_month' in exp2024[n]]
    slopes = [exp2024[n]['tir_slope_per_month'] for n in names_stable]
    colors = ['green' if s > 0.5 else 'red' if s < -0.5 else 'gray' for s in slopes]
    ax.barh(range(len(names_stable)), slopes, color=colors, alpha=0.7)
    ax.set_yticks(range(len(names_stable)))
    ax.set_yticklabels(names_stable)
    ax.set_xlabel('TIR Slope (pp/month)')
    ax.set_title('TIR Trend Direction')
    ax.axvline(0, color='black', ls='--', alpha=0.5)
    ax.grid(True, alpha=0.3, axis='x')

    ax = axes[1, 0]
    sds = [exp2024[n].get('tir_sd', 0) for n in names_stable]
    ax.barh(range(len(names_stable)), sds, color='steelblue', alpha=0.7)
    ax.set_yticks(range(len(names_stable)))
    ax.set_yticklabels(names_stable)
    ax.set_xlabel('Monthly TIR Standard Deviation')
    ax.set_title('TIR Stability (lower = more stable)')
    ax.grid(True, alpha=0.3, axis='x')

    ax = axes[1, 1]
    for n in exp2024:
        if 'monthly_tbr' not in exp2024[n]:
            continue
        tbrs = exp2024[n]['monthly_tbr']
        ax.plot(range(1, len(tbrs) + 1), tbrs, 'o-', label=n, alpha=0.7, markersize=4)
    ax.axhline(4, color='red', ls='--', alpha=0.5, label='4% target')
    ax.set_xlabel('Month')
    ax.set_ylabel('TBR (%)')
    ax.set_title('Monthly TBR Trajectory')
    ax.legend(fontsize=8, ncol=2)
    ax.grid(True, alpha=0.3)

    plt.suptitle('EXP-2024: Temporal Stability', fontsize=14)
    plt.tight_layout()
    plt.savefig(f'{FIG_DIR}/pk-fig04-temporal.png', dpi=150)
    plt.close()
    print(f"  → Saved pk-fig04-temporal.png")

improving = sum(1 for v in exp2024.values() if v.get('tir_trend') == 'improving')
declining = sum(1 for v in exp2024.values() if v.get('tir_trend') == 'declining')
stable = sum(1 for v in exp2024.values() if v.get('tir_trend') == 'stable')
verdict_2024 = f"IMPROVING={improving}_STABLE={stable}_DECLINING={declining}"
results['EXP-2024'] = verdict_2024
print(f"\n  ✓ EXP-2024 verdict: {verdict_2024}")


# ══════════════════════════════════════════════════════════════
# EXP-2025: Weekday vs Weekend Glycemic Patterns
# ══════════════════════════════════════════════════════════════
print("\n" + "#" * 70)
print("# Running EXP-2025")
print("#" * 70)
print("\n" + "=" * 70)
print("EXP-2025: Weekday vs Weekend Glycemic Patterns")
print("=" * 70)

exp2025 = {}
for p in patients:
    name = p['name']
    df = p['df']
    glucose = df['glucose'].values.astype(float)
    n_days = len(glucose) // STEPS_PER_DAY

    weekday_g = []
    weekend_g = []
    for d in range(n_days):
        # Approximate: d=0 is Monday, d%7 in [5,6] is weekend
        day_g = glucose[d * STEPS_PER_DAY:(d + 1) * STEPS_PER_DAY]
        valid = day_g[np.isfinite(day_g)]
        if len(valid) < 100:
            continue
        if d % 7 >= 5:
            weekend_g.extend(valid)
        else:
            weekday_g.extend(valid)

    if len(weekday_g) < 1000 or len(weekend_g) < 500:
        exp2025[name] = {'status': 'insufficient'}
        print(f"  {name}: insufficient data")
        continue

    wd_metrics = glucose_metrics(np.array(weekday_g))
    we_metrics = glucose_metrics(np.array(weekend_g))

    exp2025[name] = {
        'weekday_tir': round(wd_metrics['tir'], 1),
        'weekend_tir': round(we_metrics['tir'], 1),
        'tir_diff': round(we_metrics['tir'] - wd_metrics['tir'], 1),
        'weekday_tbr': round(wd_metrics['tbr'], 1),
        'weekend_tbr': round(we_metrics['tbr'], 1),
        'weekday_mean': round(wd_metrics['mean'], 0),
        'weekend_mean': round(we_metrics['mean'], 0),
    }

    print(f"  {name}: weekday_TIR={wd_metrics['tir']:.0f}% weekend_TIR={we_metrics['tir']:.0f}% "
          f"Δ={we_metrics['tir'] - wd_metrics['tir']:+.1f}pp mean: {wd_metrics['mean']:.0f}→{we_metrics['mean']:.0f}")

if MAKE_FIGS:
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    ax = axes[0]
    names_list = [n for n in exp2025 if 'weekday_tir' in exp2025[n]]
    wd = [exp2025[n]['weekday_tir'] for n in names_list]
    we = [exp2025[n]['weekend_tir'] for n in names_list]
    x = np.arange(len(names_list))
    width = 0.35
    ax.bar(x - width/2, wd, width, label='Weekday', color='steelblue', alpha=0.7)
    ax.bar(x + width/2, we, width, label='Weekend', color='coral', alpha=0.7)
    ax.set_xticks(x)
    ax.set_xticklabels(names_list)
    ax.set_ylabel('TIR (%)')
    ax.set_title('Weekday vs Weekend TIR')
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')

    ax = axes[1]
    diffs = [exp2025[n]['tir_diff'] for n in names_list]
    colors = ['green' if d > 2 else 'red' if d < -2 else 'gray' for d in diffs]
    ax.barh(range(len(names_list)), diffs, color=colors, alpha=0.7)
    ax.set_yticks(range(len(names_list)))
    ax.set_yticklabels(names_list)
    ax.set_xlabel('Weekend − Weekday TIR (pp)')
    ax.set_title('Weekend vs Weekday Difference')
    ax.axvline(0, color='black', ls='--', alpha=0.5)
    ax.grid(True, alpha=0.3, axis='x')

    plt.suptitle('EXP-2025: Weekday vs Weekend', fontsize=14)
    plt.tight_layout()
    plt.savefig(f'{FIG_DIR}/pk-fig05-weekday-weekend.png', dpi=150)
    plt.close()
    print(f"  → Saved pk-fig05-weekday-weekend.png")

diffs = [exp2025[n].get('tir_diff', 0) for n in exp2025 if 'tir_diff' in exp2025[n]]
verdict_2025 = f"WEEKEND_Δ={np.mean(diffs):+.1f}pp"
results['EXP-2025'] = verdict_2025
print(f"\n  ✓ EXP-2025 verdict: {verdict_2025}")


# ══════════════════════════════════════════════════════════════
# EXP-2026: Sensor Artifact Detection
# ══════════════════════════════════════════════════════════════
print("\n" + "#" * 70)
print("# Running EXP-2026")
print("#" * 70)
print("\n" + "=" * 70)
print("EXP-2026: Sensor Artifact Detection")
print("=" * 70)

exp2026 = {}
for p in patients:
    name = p['name']
    df = p['df']
    glucose = df['glucose'].values.astype(float)
    sage = df['sage_hours'].values.astype(float) if 'sage_hours' in df.columns else np.full(len(glucose), np.nan)

    n_total = np.sum(np.isfinite(glucose))

    # Compression lows: rapid drop to <60 followed by rapid recovery in 30-60min
    compression_candidates = 0
    for i in range(6, len(glucose) - 12):
        if not np.isfinite(glucose[i]) or glucose[i] >= 60:
            continue
        # Check rapid drop before
        pre = glucose[max(0, i-6):i]
        if np.sum(np.isfinite(pre)) == 0:
            continue
        pre_mean = np.nanmean(pre)
        if pre_mean - glucose[i] < 30:
            continue  # not a rapid drop
        # Check rapid recovery after
        post = glucose[i+1:min(i+12, len(glucose))]
        if np.sum(np.isfinite(post)) == 0:
            continue
        post_max = np.nanmax(post)
        if post_max - glucose[i] > 40 and post_max > pre_mean - 20:
            compression_candidates += 1

    # Sensor warmup: TIR in first 12h vs rest
    warmup_g = []
    main_g = []
    for i in range(len(glucose)):
        if not np.isfinite(glucose[i]):
            continue
        if np.isfinite(sage[i]) and sage[i] < 12:
            warmup_g.append(glucose[i])
        else:
            main_g.append(glucose[i])

    warmup_tir = glucose_metrics(np.array(warmup_g))['tir'] if len(warmup_g) > 50 else np.nan
    main_tir = glucose_metrics(np.array(main_g))['tir'] if len(main_g) > 1000 else np.nan

    # Gap analysis
    gap_count = 0
    gap_total_steps = 0
    in_gap = False
    for i in range(len(glucose)):
        if not np.isfinite(glucose[i]):
            if not in_gap:
                in_gap = True
                gap_count += 1
            gap_total_steps += 1
        else:
            in_gap = False

    cgm_coverage = n_total / len(glucose) * 100

    exp2026[name] = {
        'cgm_coverage_pct': round(cgm_coverage, 1),
        'compression_candidates': compression_candidates,
        'compression_rate_per_1000': round(compression_candidates / n_total * 1000, 2) if n_total > 0 else 0,
        'warmup_tir': round(warmup_tir, 1) if np.isfinite(warmup_tir) else None,
        'main_tir': round(main_tir, 1) if np.isfinite(main_tir) else None,
        'warmup_tir_diff': round(warmup_tir - main_tir, 1) if np.isfinite(warmup_tir) and np.isfinite(main_tir) else None,
        'gap_count': gap_count,
        'gap_pct': round(gap_total_steps / len(glucose) * 100, 1),
    }

    warmup_diff = exp2026[name].get('warmup_tir_diff', 'N/A')
    print(f"  {name}: coverage={cgm_coverage:.0f}% compression={compression_candidates} "
          f"warmup_Δ={warmup_diff}pp gaps={gap_count}({gap_total_steps/len(glucose)*100:.1f}%)")

if MAKE_FIGS:
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    ax = axes[0, 0]
    names_list = list(exp2026.keys())
    coverage = [exp2026[n]['cgm_coverage_pct'] for n in names_list]
    ax.barh(range(len(names_list)), coverage, color='steelblue', alpha=0.7)
    ax.set_yticks(range(len(names_list)))
    ax.set_yticklabels(names_list)
    ax.set_xlabel('CGM Coverage (%)')
    ax.set_title('Sensor Data Availability')
    ax.axvline(90, color='green', ls='--', alpha=0.5, label='90% target')
    ax.legend()
    ax.grid(True, alpha=0.3, axis='x')

    ax = axes[0, 1]
    comps = [exp2026[n]['compression_candidates'] for n in names_list]
    ax.barh(range(len(names_list)), comps, color='orange', alpha=0.7)
    ax.set_yticks(range(len(names_list)))
    ax.set_yticklabels(names_list)
    ax.set_xlabel('Compression Low Candidates')
    ax.set_title('Potential Compression Artifacts')
    ax.grid(True, alpha=0.3, axis='x')

    ax = axes[1, 0]
    warmup_main = [(exp2026[n].get('warmup_tir'), exp2026[n].get('main_tir')) for n in names_list]
    warmups = [wm[0] if wm[0] is not None else 0 for wm in warmup_main]
    mains = [wm[1] if wm[1] is not None else 0 for wm in warmup_main]
    x = np.arange(len(names_list))
    width = 0.35
    ax.bar(x - width/2, warmups, width, label='Warmup (<12h)', color='orange', alpha=0.7)
    ax.bar(x + width/2, mains, width, label='Main', color='green', alpha=0.7)
    ax.set_xticks(x)
    ax.set_xticklabels(names_list)
    ax.set_ylabel('TIR (%)')
    ax.set_title('Warmup vs Main Sensor TIR')
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')

    ax = axes[1, 1]
    gaps = [exp2026[n]['gap_pct'] for n in names_list]
    ax.barh(range(len(names_list)), gaps, color='red', alpha=0.7)
    ax.set_yticks(range(len(names_list)))
    ax.set_yticklabels(names_list)
    ax.set_xlabel('Gap Percentage (%)')
    ax.set_title('Sensor Gap Rate')
    ax.grid(True, alpha=0.3, axis='x')

    plt.suptitle('EXP-2026: Sensor Artifact Detection', fontsize=14)
    plt.tight_layout()
    plt.savefig(f'{FIG_DIR}/pk-fig06-artifacts.png', dpi=150)
    plt.close()
    print(f"  → Saved pk-fig06-artifacts.png")

mean_comp = np.mean([exp2026[n]['compression_candidates'] for n in exp2026])
mean_cov = np.mean([exp2026[n]['cgm_coverage_pct'] for n in exp2026])
verdict_2026 = f"COVERAGE_{mean_cov:.0f}%_COMPRESSION_{mean_comp:.0f}_MEAN"
results['EXP-2026'] = verdict_2026
print(f"\n  ✓ EXP-2026 verdict: {verdict_2026}")


# ══════════════════════════════════════════════════════════════
# EXP-2027: Hidden Variable Identification
# ══════════════════════════════════════════════════════════════
print("\n" + "#" * 70)
print("# Running EXP-2027")
print("#" * 70)
print("\n" + "=" * 70)
print("EXP-2027: Hidden Variable Identification")
print("=" * 70)

exp2027 = {}

# Collect per-patient features and TIR
features_all = {}
for p in patients:
    name = p['name']
    df = p['df']
    glucose = df['glucose'].values.astype(float)
    bolus = df['bolus'].values.astype(float) if 'bolus' in df.columns else np.zeros(len(glucose))
    carbs = df['carbs'].values.astype(float) if 'carbs' in df.columns else np.zeros(len(glucose))
    net_basal = df['net_basal'].values.astype(float) if 'net_basal' in df.columns else np.zeros(len(glucose))
    iob = df['iob'].values.astype(float) if 'iob' in df.columns else np.full(len(glucose), np.nan)

    metrics = glucose_metrics(glucose)
    n_days = len(glucose) // STEPS_PER_DAY

    # Compute many features
    # Basic
    daily_insulin = np.nansum(bolus) / (n_days if n_days > 0 else 1)
    daily_carbs = np.nansum(carbs) / (n_days if n_days > 0 else 1)
    meals_per_day = np.sum(carbs >= 10) / (n_days if n_days > 0 else 1)

    # Variability features
    dg = np.diff(glucose)
    dg_valid = dg[np.isfinite(dg)]
    mean_abs_change = float(np.mean(np.abs(dg_valid))) if len(dg_valid) > 0 else 0
    max_rise = float(np.percentile(dg_valid, 99)) if len(dg_valid) > 100 else 0
    max_drop = float(np.percentile(dg_valid, 1)) if len(dg_valid) > 100 else 0

    # IOB statistics
    iob_valid = iob[np.isfinite(iob)]
    mean_iob = float(np.mean(iob_valid)) if len(iob_valid) > 0 else 0
    max_iob = float(np.percentile(iob_valid, 95)) if len(iob_valid) > 100 else 0

    # Basal patterns
    basal_valid = net_basal[np.isfinite(net_basal)]
    zero_delivery_pct = float(np.mean(basal_valid < 0.05) * 100) if len(basal_valid) > 0 else 0

    features_all[name] = {
        'tir': metrics['tir'],
        'tbr': metrics['tbr'],
        'tar': metrics['tar'],
        'cv': metrics['cv'],
        'mean_glucose': metrics['mean'],
        'daily_insulin': round(daily_insulin, 1),
        'daily_carbs': round(daily_carbs, 0),
        'meals_per_day': round(meals_per_day, 1),
        'mean_abs_change': round(mean_abs_change, 2),
        'max_rise_rate': round(max_rise, 1),
        'max_drop_rate': round(max_drop, 1),
        'mean_iob': round(mean_iob, 2),
        'max_iob': round(max_iob, 2),
        'zero_delivery_pct': round(zero_delivery_pct, 1),
    }

# Find features that best predict TIR residual (after known features)
feature_names = [k for k in list(features_all.values())[0].keys() if k != 'tir']
tirs = [features_all[n]['tir'] for n in features_all]

print("  Feature correlations with TIR:")
correlations = {}
for feat in feature_names:
    vals = [features_all[n][feat] for n in features_all]
    valid = [(v, t) for v, t in zip(vals, tirs) if np.isfinite(v) and np.isfinite(t)]
    if len(valid) < 5:
        continue
    vv = np.array([x[0] for x in valid])
    tt = np.array([x[1] for x in valid])
    corr = float(np.corrcoef(vv, tt)[0, 1])
    correlations[feat] = round(corr, 3)
    sign = "+" if corr > 0 else ""
    print(f"    {feat}: r={sign}{corr:.3f}")

# Sort by absolute correlation
sorted_corr = sorted(correlations.items(), key=lambda x: abs(x[1]), reverse=True)
top_predictor = sorted_corr[0] if sorted_corr else ('none', 0)

# Residual analysis: after removing top predictor, what explains remaining TIR?
if sorted_corr and len(sorted_corr) > 1:
    top_feat = sorted_corr[0][0]
    top_vals = np.array([features_all[n][top_feat] for n in features_all])
    tir_array = np.array(tirs)
    valid_mask = np.isfinite(top_vals) & np.isfinite(tir_array)
    if np.sum(valid_mask) >= 5:
        p_fit = np.polyfit(top_vals[valid_mask], tir_array[valid_mask], 1)
        predicted = np.polyval(p_fit, top_vals[valid_mask])
        residual = tir_array[valid_mask] - predicted
        residual_sd = float(np.std(residual))
        names_valid = [n for n, m in zip(features_all.keys(), valid_mask) if m]

        print(f"\n  After removing {top_feat} (r={sorted_corr[0][1]:.3f}):")
        print(f"    Residual TIR SD = {residual_sd:.1f}pp")

        # Find what predicts residual
        residual_corrs = {}
        for feat in feature_names:
            if feat == top_feat:
                continue
            vals = np.array([features_all[n][feat] for n in names_valid])
            valid2 = np.isfinite(vals)
            if np.sum(valid2) >= 5:
                rc = float(np.corrcoef(vals[valid2], residual[valid2])[0, 1])
                residual_corrs[feat] = round(rc, 3)
        sorted_resid = sorted(residual_corrs.items(), key=lambda x: abs(x[1]), reverse=True)
        for feat, rc in sorted_resid[:5]:
            print(f"    {feat}: r={rc:+.3f} (residual)")

exp2027 = {
    'feature_correlations': correlations,
    'top_predictor': top_predictor[0],
    'top_correlation': top_predictor[1],
    'sorted_predictors': [{'feature': f, 'correlation': c} for f, c in sorted_corr[:10]],
    'residual_sd': round(residual_sd, 1) if 'residual_sd' in dir() else np.nan,
}

if MAKE_FIGS:
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    ax = axes[0]
    feat_names = [f for f, _ in sorted_corr]
    corr_vals = [c for _, c in sorted_corr]
    colors = ['green' if c > 0 else 'red' for c in corr_vals]
    ax.barh(range(len(feat_names)), corr_vals, color=colors, alpha=0.7)
    ax.set_yticks(range(len(feat_names)))
    ax.set_yticklabels(feat_names, fontsize=8)
    ax.set_xlabel('Correlation with TIR')
    ax.set_title('Feature Importance for TIR Prediction')
    ax.axvline(0, color='black', ls='--', alpha=0.5)
    ax.grid(True, alpha=0.3, axis='x')

    ax = axes[1]
    # Scatter: top predictor vs TIR
    top_feat = sorted_corr[0][0] if sorted_corr else 'cv'
    top_vals = [features_all[n].get(top_feat, 0) for n in features_all]
    ax.scatter(top_vals, tirs, s=60, zorder=3)
    for n, tv, t in zip(features_all.keys(), top_vals, tirs):
        ax.annotate(n, (tv, t), fontsize=9)
    ax.set_xlabel(f'{top_feat}')
    ax.set_ylabel('TIR (%)')
    ax.set_title(f'Top Predictor: {top_feat} (r={sorted_corr[0][1]:.3f})')
    ax.grid(True, alpha=0.3)

    plt.suptitle('EXP-2027: Hidden Variable Identification', fontsize=14)
    plt.tight_layout()
    plt.savefig(f'{FIG_DIR}/pk-fig07-hidden-vars.png', dpi=150)
    plt.close()
    print(f"\n  → Saved pk-fig07-hidden-vars.png")

verdict_2027 = f"TOP_PREDICTOR={top_predictor[0]}_r={top_predictor[1]:.3f}"
results['EXP-2027'] = verdict_2027
print(f"\n  ✓ EXP-2027 verdict: {verdict_2027}")


# ══════════════════════════════════════════════════════════════
# EXP-2028: Synthesis — Personalized Pharmacokinetic Profiles
# ══════════════════════════════════════════════════════════════
print("\n" + "#" * 70)
print("# Running EXP-2028")
print("#" * 70)
print("\n" + "=" * 70)
print("EXP-2028: Synthesis — Personalized Pharmacokinetic Profiles")
print("=" * 70)

exp2028 = {}
for p in patients:
    name = p['name']
    profile = {}

    # DIA
    if name in exp2021 and 'dia_hours' in exp2021[name]:
        profile['dia_hours'] = exp2021[name]['dia_hours']
        profile['peak_time_hours'] = exp2021[name]['peak_time_hours']
        profile['tau_hours'] = exp2021[name]['tau_hours']

    # Onset
    if name in exp2022 and 'onset_median_min' in exp2022[name]:
        profile['onset_min'] = exp2022[name]['onset_median_min']

    # Stacking risk
    if name in exp2023:
        profile['stacking_risk_ratio'] = exp2023[name].get('risk_ratio', np.nan)
        profile['stacking_pct'] = exp2023[name].get('stacking_pct', 0)

    # Temporal stability
    if name in exp2024 and 'tir_trend' in exp2024[name]:
        profile['tir_trend'] = exp2024[name]['tir_trend']
        profile['tir_sd'] = exp2024[name]['tir_sd']

    # Weekend effect
    if name in exp2025 and 'tir_diff' in exp2025[name]:
        profile['weekend_tir_diff'] = exp2025[name]['tir_diff']

    # Sensor quality
    if name in exp2026:
        profile['cgm_coverage'] = exp2026[name]['cgm_coverage_pct']
        profile['compression_artifacts'] = exp2026[name]['compression_candidates']

    # Risk classification
    risks = []
    if profile.get('stacking_risk_ratio', 0) > 1.5:
        risks.append('HIGH_STACKING_RISK')
    if profile.get('tir_sd', 0) > 5:
        risks.append('UNSTABLE_TIR')
    if profile.get('compression_artifacts', 0) > 50:
        risks.append('SENSOR_ARTIFACTS')
    if profile.get('dia_hours', 5) > 5.5:
        risks.append('LONG_DIA')
    profile['risk_flags'] = risks

    exp2028[name] = profile

    dia_str = f"DIA={profile.get('dia_hours', '?')}h" if 'dia_hours' in profile else "DIA=?"
    onset_str = f"onset={profile.get('onset_min', '?')}min"
    trend_str = profile.get('tir_trend', '?')
    risks_str = ','.join(risks) if risks else 'NONE'
    print(f"  {name}: {dia_str} {onset_str} trend={trend_str} risks={risks_str}")

if MAKE_FIGS:
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))

    ax = axes[0, 0]
    names_list = [n for n in exp2028 if 'dia_hours' in exp2028[n]]
    dias = [exp2028[n]['dia_hours'] for n in names_list]
    onsets = [exp2028[n].get('onset_min', 0) for n in names_list]
    ax.scatter(onsets, dias, s=60, zorder=3)
    for n, o, d in zip(names_list, onsets, dias):
        ax.annotate(n, (o, d), fontsize=9)
    ax.set_xlabel('Onset Time (min)')
    ax.set_ylabel('DIA (hours)')
    ax.set_title('Insulin Pharmacokinetic Profile')
    ax.axhline(5, color='gray', ls='--', alpha=0.5, label='Standard DIA')
    ax.legend()
    ax.grid(True, alpha=0.3)

    ax = axes[0, 1]
    names_risk = list(exp2028.keys())
    n_risks = [len(exp2028[n].get('risk_flags', [])) for n in names_risk]
    colors = ['red' if r >= 2 else 'orange' if r >= 1 else 'green' for r in n_risks]
    ax.barh(range(len(names_risk)), n_risks, color=colors, alpha=0.7)
    ax.set_yticks(range(len(names_risk)))
    ax.set_yticklabels(names_risk)
    ax.set_xlabel('Number of Risk Flags')
    ax.set_title('Risk Flag Count by Patient')
    ax.grid(True, alpha=0.3, axis='x')

    ax = axes[1, 0]
    names_stab = [n for n in exp2028 if 'tir_sd' in exp2028[n]]
    sds = [exp2028[n]['tir_sd'] for n in names_stab]
    trends = [exp2028[n].get('tir_trend', 'stable') for n in names_stab]
    colors = ['green' if t == 'improving' else 'red' if t == 'declining' else 'gray' for t in trends]
    ax.barh(range(len(names_stab)), sds, color=colors, alpha=0.7)
    ax.set_yticks(range(len(names_stab)))
    ax.set_yticklabels(names_stab)
    ax.set_xlabel('Monthly TIR SD')
    ax.set_title('Stability (green=improving, red=declining)')
    ax.grid(True, alpha=0.3, axis='x')

    ax = axes[1, 1]
    names_cov = [n for n in exp2028 if 'cgm_coverage' in exp2028[n]]
    covs = [exp2028[n]['cgm_coverage'] for n in names_cov]
    comps = [exp2028[n].get('compression_artifacts', 0) for n in names_cov]
    ax.scatter(covs, comps, s=60, zorder=3)
    for n, c, cm in zip(names_cov, covs, comps):
        ax.annotate(n, (c, cm), fontsize=9)
    ax.set_xlabel('CGM Coverage (%)')
    ax.set_ylabel('Compression Artifacts')
    ax.set_title('Sensor Quality Assessment')
    ax.grid(True, alpha=0.3)

    plt.suptitle('EXP-2028: Personalized PK Profiles', fontsize=14)
    plt.tight_layout()
    plt.savefig(f'{FIG_DIR}/pk-fig08-synthesis.png', dpi=150)
    plt.close()
    print(f"  → Saved pk-fig08-synthesis.png")

flagged = sum(1 for v in exp2028.values() if len(v.get('risk_flags', [])) > 0)
verdict_2028 = f"FLAGGED_{flagged}/11_PATIENTS"
results['EXP-2028'] = verdict_2028
print(f"\n  ✓ EXP-2028 verdict: {verdict_2028}")


# ══════════════════════════════════════════════════════════════
# SYNTHESIS
# ══════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("SYNTHESIS: Insulin Pharmacokinetics & Temporal Dynamics")
print("=" * 70)
for k, v in sorted(results.items()):
    print(f"  {k}: {v}")

output = {
    'experiment_group': 'EXP-2021–2028',
    'title': 'Insulin Pharmacokinetics & Temporal Dynamics',
    'results': results,
    'exp2021_dia': {k: {kk: vv for kk, vv in v.items() if kk != 'mean_curve'} for k, v in exp2021.items()},
    'exp2022_onset': exp2022,
    'exp2023_stacking': exp2023,
    'exp2024_temporal': {k: {kk: vv for kk, vv in v.items() if kk not in ('monthly_tir', 'monthly_tbr')} for k, v in exp2024.items()},
    'exp2025_weekday': exp2025,
    'exp2026_artifacts': exp2026,
    'exp2027_hidden': exp2027,
    'exp2028_synthesis': exp2028,
}

with open(f'{EXP_DIR}/exp-2021_pharmacokinetics.json', 'w') as f:
    json.dump(output, f, indent=2, default=str)
print(f"\nSaved results to {EXP_DIR}/exp-2021_pharmacokinetics.json")
