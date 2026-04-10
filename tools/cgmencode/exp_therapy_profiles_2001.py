#!/usr/bin/env python3
"""
EXP-2001–2008: Data-Driven Therapy Profiles

Building personalized therapy profiles from CGM/AID data that could
replace static pump settings with data-derived optimal profiles.

EXP-2001: Personalized carb absorption curves
EXP-2002: Hourly effective ISF profiles with confidence
EXP-2003: Data-driven basal rate optimization
EXP-2004: Non-meal variability driver decomposition
EXP-2005: Automated meal detection and classification from CGM
EXP-2006: Hypo recovery and rebound characterization
EXP-2007: Loop intervention effectiveness scoring
EXP-2008: Synthesis — optimal personalized therapy profiles

Depends on: exp_metabolic_441.py (load_patients, compute_supply_demand)
Prior findings: EXP-1991–1998 (absorption slow, non-meal 60%, transfer fails)
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
    """Compute standard glucose metrics from array."""
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


def hour_of_step(step_idx, total_steps):
    """Return hour (0-23) for step index."""
    return (step_idx % STEPS_PER_DAY) // STEPS_PER_HOUR


# ─── Load data ───────────────────────────────────────────────
patients = load_patients(PATIENT_DIR)
results = {}

# ══════════════════════════════════════════════════════════════
# EXP-2001: Personalized Carb Absorption Curves
# ══════════════════════════════════════════════════════════════
print("\n" + "#" * 70)
print("# Running EXP-2001")
print("#" * 70)
print("\n" + "=" * 70)
print("EXP-2001: Personalized Carb Absorption Curves")
print("=" * 70)

exp2001 = {}
for p in patients:
    name = p['name']
    df = p['df']
    glucose = df['glucose'].values.astype(float)
    carbs = df['carbs'].values.astype(float)

    # Find meals >= 10g
    meal_steps = np.where(carbs >= 10)[0]
    # Filter: need 3h (36 steps) of glucose after meal, valid glucose
    curves = []
    curve_details = []
    for ms in meal_steps:
        if ms + 36 > len(glucose):
            continue
        window = glucose[ms:ms + 36]
        if np.sum(np.isfinite(window)) < 30:
            continue
        # Baseline is glucose at meal time
        baseline = glucose[ms]
        if not np.isfinite(baseline):
            continue
        # Normalize: delta from baseline
        delta = window - baseline
        curves.append(delta)
        # Characterize this meal
        peak_idx = np.nanargmax(window)
        peak_val = np.nanmax(window) - baseline
        # Time to return to baseline
        above = window > baseline
        return_idx = 36  # default: didn't return
        for ri in range(peak_idx, 36):
            if not above[ri]:
                return_idx = ri
                break
        curve_details.append({
            'carbs': float(carbs[ms]),
            'baseline': float(baseline),
            'peak_delta': float(peak_val),
            'peak_time_min': int(peak_idx * 5),
            'return_time_min': int(return_idx * 5),
        })

    if len(curves) < 5:
        exp2001[name] = {'n_meals': len(curves), 'status': 'insufficient'}
        print(f"  {name}: only {len(curves)} valid meals, skipping")
        continue

    curves = np.array(curves)
    # Compute mean curve and percentile bands
    mean_curve = np.nanmean(curves, axis=0)
    p25_curve = np.nanpercentile(curves, 25, axis=0)
    p75_curve = np.nanpercentile(curves, 75, axis=0)

    # Fit absorption model: delta(t) = A * (1 - exp(-t/tau_rise)) * exp(-t/tau_fall)
    # Simple parametric: find peak time and half-return time
    peak_time = np.argmax(mean_curve) * 5  # minutes
    peak_amplitude = float(np.max(mean_curve))

    # Half-return: when curve drops below peak/2 after peak
    peak_idx = np.argmax(mean_curve)
    half_return = 180  # default
    for ri in range(peak_idx, len(mean_curve)):
        if mean_curve[ri] < peak_amplitude / 2:
            half_return = ri * 5
            break

    # Classify shape: spike-and-return, sustained rise, or gradual
    end_val = mean_curve[-1]
    shape = 'sustained' if end_val > peak_amplitude * 0.5 else ('spike' if peak_time < 45 else 'gradual')

    # Carb-size dependent absorption
    carb_sizes = np.array([d['carbs'] for d in curve_details])
    peak_deltas = np.array([d['peak_delta'] for d in curve_details])
    peak_times = np.array([d['peak_time_min'] for d in curve_details])

    small_mask = carb_sizes < 30
    large_mask = carb_sizes >= 50
    med_mask = ~small_mask & ~large_mask

    size_profiles = {}
    for label, mask in [('small', small_mask), ('medium', med_mask), ('large', large_mask)]:
        if np.sum(mask) >= 3:
            size_profiles[label] = {
                'n': int(np.sum(mask)),
                'mean_peak_time': float(np.mean(peak_times[mask])),
                'mean_peak_delta': float(np.mean(peak_deltas[mask])),
                'mean_carbs': float(np.mean(carb_sizes[mask])),
            }

    exp2001[name] = {
        'n_meals': len(curves),
        'peak_time_min': int(peak_time),
        'peak_amplitude': round(peak_amplitude, 1),
        'half_return_min': int(half_return),
        'shape': shape,
        'mean_curve': [round(float(v), 1) for v in mean_curve],
        'size_profiles': size_profiles,
    }
    sizes_str = ','.join(f'{k}={v["n"]}' for k, v in size_profiles.items())
    print(f"  {name}: n={len(curves)} peak={peak_time}min amp={peak_amplitude:.0f}mg/dL "
          f"half_return={half_return}min shape={shape} sizes={sizes_str}")

if MAKE_FIGS:
    fig, axes = plt.subplots(2, 3, figsize=(18, 12))
    time_min = np.arange(36) * 5  # 0–175 min
    # Top row: individual patient curves
    for idx, p in enumerate(patients[:6]):
        ax = axes[idx // 3, idx % 3]
        name = p['name']
        if name in exp2001 and 'mean_curve' in exp2001[name]:
            ax.plot(time_min, exp2001[name]['mean_curve'], 'b-', lw=2, label='Mean')
            ax.axhline(0, color='gray', ls='--', alpha=0.5)
            ax.axvline(exp2001[name]['peak_time_min'], color='r', ls=':', label=f"Peak {exp2001[name]['peak_time_min']}min")
            ax.set_title(f"Patient {name} (n={exp2001[name]['n_meals']})", fontsize=12)
        else:
            ax.text(0.5, 0.5, f"Patient {name}\nInsufficient data", transform=ax.transAxes, ha='center')
        ax.set_xlabel('Time since meal (min)')
        ax.set_ylabel('Δ Glucose (mg/dL)')
        ax.legend(fontsize=8)
    plt.suptitle('EXP-2001: Personalized Carb Absorption Curves', fontsize=14)
    plt.tight_layout()
    plt.savefig(f'{FIG_DIR}/therapy-fig01-absorption-curves.png', dpi=150)
    plt.close()
    print(f"  → Saved therapy-fig01-absorption-curves.png")

# Verdict
shapes = [v.get('shape', 'unknown') for v in exp2001.values() if 'shape' in v]
peak_times = [v.get('peak_time_min', 0) for v in exp2001.values() if 'peak_time_min' in v]
verdict_2001 = f"MEDIAN_PEAK_{int(np.median(peak_times))}min_SHAPES_{'_'.join(f'{s}={shapes.count(s)}' for s in set(shapes))}"
results['EXP-2001'] = verdict_2001
print(f"\n  ✓ EXP-2001 verdict: {verdict_2001}")


# ══════════════════════════════════════════════════════════════
# EXP-2002: Hourly Effective ISF Profiles
# ══════════════════════════════════════════════════════════════
print("\n" + "#" * 70)
print("# Running EXP-2002")
print("#" * 70)
print("\n" + "=" * 70)
print("EXP-2002: Hourly Effective ISF Profiles")
print("=" * 70)

exp2002 = {}
for p in patients:
    name = p['name']
    df = p['df']
    glucose = df['glucose'].values.astype(float)
    iob = df['iob'].values.astype(float) if 'iob' in df.columns else np.full(len(glucose), np.nan)
    bolus = df['bolus'].values.astype(float) if 'bolus' in df.columns else np.zeros(len(glucose))
    carbs = df['carbs'].values.astype(float) if 'carbs' in df.columns else np.zeros(len(glucose))

    # Profile ISF
    isf_profile = df.attrs.get('isf_schedule', [{'value': 50}])
    profile_isf = isf_profile[0]['value'] if isf_profile else 50
    if profile_isf < 15:
        profile_isf *= 18.0182

    # Find correction events: bolus > 0, no carbs within ±1h, glucose > 120
    hourly_isf = {h: [] for h in range(24)}
    for i in range(len(glucose) - 24):  # need 2h follow-up
        if bolus[i] < 0.3:
            continue
        # No carbs within ±12 steps (1h)
        carb_window = carbs[max(0, i-12):min(len(carbs), i+12)]
        if np.nansum(carb_window) > 1:
            continue
        # Starting glucose > 120
        if not np.isfinite(glucose[i]) or glucose[i] < 120:
            continue
        # Glucose 2h later
        g_after = glucose[min(i + 24, len(glucose) - 1)]
        if not np.isfinite(g_after):
            continue
        # Effective ISF = (g_before - g_after) / bolus
        delta_g = glucose[i] - g_after
        if delta_g <= 0:
            continue  # correction didn't work
        eff_isf = delta_g / bolus[i]
        if eff_isf < 5 or eff_isf > 500:
            continue  # outlier
        hour = hour_of_step(i, len(glucose))
        hourly_isf[hour].append(eff_isf)

    # Build hourly profile
    hourly_profile = {}
    for h in range(24):
        vals = hourly_isf[h]
        if len(vals) >= 3:
            hourly_profile[str(h)] = {
                'n': len(vals),
                'median': round(float(np.median(vals)), 1),
                'p25': round(float(np.percentile(vals, 25)), 1),
                'p75': round(float(np.percentile(vals, 75)), 1),
            }

    # Compute morning/evening/overnight averages
    morning_vals = [v for h in range(6, 11) for v in hourly_isf[h]]
    afternoon_vals = [v for h in range(11, 17) for v in hourly_isf[h]]
    evening_vals = [v for h in range(17, 23) for v in hourly_isf[h]]
    overnight_vals = [v for h in list(range(23, 24)) + list(range(0, 6)) for v in hourly_isf[h]]

    periods = {}
    for label, vals in [('morning', morning_vals), ('afternoon', afternoon_vals),
                        ('evening', evening_vals), ('overnight', overnight_vals)]:
        if len(vals) >= 5:
            periods[label] = {
                'n': len(vals),
                'median': round(float(np.median(vals)), 1),
                'iqr': round(float(np.percentile(vals, 75) - np.percentile(vals, 25)), 1),
            }

    total_corrections = sum(len(v) for v in hourly_isf.values())
    all_isf_vals = [v for vals in hourly_isf.values() for v in vals]
    overall_median = round(float(np.median(all_isf_vals)), 1) if all_isf_vals else np.nan
    ratio = round(profile_isf / overall_median, 2) if overall_median and np.isfinite(overall_median) and overall_median > 0 else np.nan

    exp2002[name] = {
        'profile_isf': round(profile_isf, 1),
        'effective_isf_median': overall_median,
        'profile_vs_effective_ratio': ratio,
        'total_corrections': total_corrections,
        'hourly_profile': hourly_profile,
        'period_profile': periods,
    }

    period_str = ' '.join(f"{k}={v['median']}" for k, v in periods.items())
    print(f"  {name}: profile={profile_isf:.0f} effective={overall_median} ratio={ratio} "
          f"n={total_corrections} {period_str}")

if MAKE_FIGS:
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    # Top-left: hourly ISF for all patients
    ax = axes[0, 0]
    for p in patients:
        name = p['name']
        if name not in exp2002:
            continue
        hp = exp2002[name]['hourly_profile']
        hours = sorted([int(h) for h in hp.keys()])
        medians = [hp[str(h)]['median'] for h in hours]
        if len(hours) > 5:
            ax.plot(hours, medians, 'o-', markersize=3, label=name, alpha=0.7)
    ax.set_xlabel('Hour of Day')
    ax.set_ylabel('Effective ISF (mg/dL/U)')
    ax.set_title('Hourly ISF Profile by Patient')
    ax.legend(fontsize=8, ncol=2)
    ax.set_xlim(0, 23)
    ax.grid(True, alpha=0.3)

    # Top-right: profile vs effective ISF
    ax = axes[0, 1]
    profile_vals = [exp2002[n]['profile_isf'] for n in exp2002]
    effective_vals = [exp2002[n]['effective_isf_median'] for n in exp2002 if np.isfinite(exp2002[n]['effective_isf_median'])]
    names = [n for n in exp2002 if np.isfinite(exp2002[n]['effective_isf_median'])]
    profile_filtered = [exp2002[n]['profile_isf'] for n in names]
    ax.scatter(profile_filtered, effective_vals, s=60, zorder=3)
    for n, pv, ev in zip(names, profile_filtered, effective_vals):
        ax.annotate(n, (pv, ev), fontsize=9, ha='left')
    lims = [min(min(profile_filtered), min(effective_vals)) * 0.8,
            max(max(profile_filtered), max(effective_vals)) * 1.2]
    ax.plot(lims, lims, 'k--', alpha=0.5, label='Perfect match')
    ax.set_xlabel('Profile ISF (mg/dL/U)')
    ax.set_ylabel('Effective ISF (mg/dL/U)')
    ax.set_title('Profile vs Data-Derived ISF')
    ax.legend()
    ax.grid(True, alpha=0.3)

    # Bottom-left: period ISF comparison
    ax = axes[1, 0]
    period_labels = ['morning', 'afternoon', 'evening', 'overnight']
    x = np.arange(len(period_labels))
    width = 0.06
    for idx, name in enumerate(exp2002.keys()):
        periods_data = exp2002[name].get('period_profile', {})
        vals = [periods_data.get(pl, {}).get('median', np.nan) for pl in period_labels]
        ax.bar(x + idx * width, vals, width, label=name, alpha=0.8)
    ax.set_xticks(x + width * len(exp2002) / 2)
    ax.set_xticklabels(period_labels)
    ax.set_ylabel('Effective ISF (mg/dL/U)')
    ax.set_title('ISF by Time Period')
    ax.legend(fontsize=7, ncol=3)
    ax.grid(True, alpha=0.3, axis='y')

    # Bottom-right: ISF ratio distribution
    ax = axes[1, 1]
    ratios = [exp2002[n]['profile_vs_effective_ratio'] for n in exp2002
              if np.isfinite(exp2002[n].get('profile_vs_effective_ratio', np.nan))]
    ratio_names = [n for n in exp2002
                   if np.isfinite(exp2002[n].get('profile_vs_effective_ratio', np.nan))]
    colors = ['red' if r > 1.3 or r < 0.7 else 'green' for r in ratios]
    ax.barh(range(len(ratios)), ratios, color=colors, alpha=0.7)
    ax.set_yticks(range(len(ratios)))
    ax.set_yticklabels(ratio_names)
    ax.axvline(1.0, color='black', ls='--', label='Perfect match')
    ax.set_xlabel('Profile ISF / Effective ISF Ratio')
    ax.set_title('ISF Mismatch Ratio (green=good, red=mismatch)')
    ax.legend()
    ax.grid(True, alpha=0.3, axis='x')

    plt.suptitle('EXP-2002: Hourly Effective ISF Profiles', fontsize=14)
    plt.tight_layout()
    plt.savefig(f'{FIG_DIR}/therapy-fig02-isf-profiles.png', dpi=150)
    plt.close()
    print(f"  → Saved therapy-fig02-isf-profiles.png")

all_ratios = [exp2002[n]['profile_vs_effective_ratio'] for n in exp2002
              if np.isfinite(exp2002[n].get('profile_vs_effective_ratio', np.nan))]
mismatch_count = sum(1 for r in all_ratios if r > 1.3 or r < 0.7)
verdict_2002 = f"MEDIAN_RATIO_{np.median(all_ratios):.2f}_MISMATCH_{mismatch_count}/{len(all_ratios)}"
results['EXP-2002'] = verdict_2002
print(f"\n  ✓ EXP-2002 verdict: {verdict_2002}")


# ══════════════════════════════════════════════════════════════
# EXP-2003: Data-Driven Basal Rate Optimization
# ══════════════════════════════════════════════════════════════
print("\n" + "#" * 70)
print("# Running EXP-2003")
print("#" * 70)
print("\n" + "=" * 70)
print("EXP-2003: Data-Driven Basal Rate Optimization")
print("=" * 70)

exp2003 = {}
for p in patients:
    name = p['name']
    df = p['df']
    glucose = df['glucose'].values.astype(float)
    net_basal = df['net_basal'].values.astype(float) if 'net_basal' in df.columns else np.zeros(len(glucose))
    carbs = df['carbs'].values.astype(float) if 'carbs' in df.columns else np.zeros(len(glucose))
    bolus = df['bolus'].values.astype(float) if 'bolus' in df.columns else np.zeros(len(glucose))

    # Profile basal
    basal_schedule = df.attrs.get('basal_schedule', [{'value': 1.0}])
    profile_basal = basal_schedule[0]['value'] if basal_schedule else 1.0

    # Compute hourly glucose drift in non-meal periods
    # Non-meal: no carbs/bolus in ±2h window
    hourly_drift = {h: [] for h in range(24)}
    hourly_basal_actual = {h: [] for h in range(24)}

    for i in range(24, len(glucose) - 24):
        # No carbs or bolus within ±2h
        carb_window = carbs[max(0, i-24):min(len(carbs), i+24)]
        bolus_window = bolus[max(0, i-24):min(len(bolus), i+24)]
        if np.nansum(carb_window) > 0.5 or np.nansum(bolus_window) > 0.1:
            continue
        # Valid glucose
        if not np.isfinite(glucose[i]) or not np.isfinite(glucose[i+1]):
            continue
        drift = (glucose[i+1] - glucose[i]) * STEPS_PER_HOUR  # mg/dL/hour
        hour = hour_of_step(i, len(glucose))
        hourly_drift[hour].append(drift)
        if np.isfinite(net_basal[i]):
            hourly_basal_actual[hour].append(net_basal[i])

    # Optimal basal adjustment: if glucose drifts up, need more basal
    # Rough: Δbasal = drift / ISF_per_hour
    isf_schedule = df.attrs.get('isf_schedule', [{'value': 50}])
    profile_isf = isf_schedule[0]['value'] if isf_schedule else 50
    if profile_isf < 15:
        profile_isf *= 18.0182

    hourly_optimal = {}
    for h in range(24):
        if len(hourly_drift[h]) >= 10:
            median_drift = float(np.median(hourly_drift[h]))
            # Positive drift = glucose rising = need more basal
            # Δbasal = drift / (ISF * steps_per_hour) ... simplified
            basal_adj = median_drift / (profile_isf / 3.0)  # rough conversion
            actual_basal = float(np.median(hourly_basal_actual[h])) if hourly_basal_actual[h] else profile_basal
            hourly_optimal[str(h)] = {
                'n': len(hourly_drift[h]),
                'median_drift': round(median_drift, 2),
                'actual_basal': round(actual_basal, 2),
                'suggested_adjustment': round(basal_adj, 3),
                'suggested_basal': round(actual_basal + basal_adj, 2),
            }

    # Dawn phenomenon detection: drift 4-8AM vs 0-4AM
    dawn_drifts = [v for h in range(4, 8) for v in hourly_drift[h]]
    pre_dawn_drifts = [v for h in range(0, 4) for v in hourly_drift[h]]
    dawn_phenomenon = False
    dawn_magnitude = 0.0
    if len(dawn_drifts) >= 10 and len(pre_dawn_drifts) >= 10:
        dawn_med = np.median(dawn_drifts)
        pre_dawn_med = np.median(pre_dawn_drifts)
        if dawn_med > pre_dawn_med + 5:
            dawn_phenomenon = True
            dawn_magnitude = float(dawn_med - pre_dawn_med)

    exp2003[name] = {
        'profile_basal': round(profile_basal, 2),
        'hourly_optimal': hourly_optimal,
        'dawn_phenomenon': dawn_phenomenon,
        'dawn_magnitude_mg_dl_h': round(dawn_magnitude, 1),
        'n_fasting_hours': len([h for h in hourly_optimal if hourly_optimal[h]['n'] >= 10]),
    }

    dawn_str = f"dawn={dawn_magnitude:.1f}mg/dL/h" if dawn_phenomenon else "no_dawn"
    n_adj = sum(1 for h in hourly_optimal.values() if abs(h['suggested_adjustment']) > 0.05)
    print(f"  {name}: profile_basal={profile_basal:.2f} {dawn_str} "
          f"hours_with_data={len(hourly_optimal)} hours_need_adj={n_adj}")

if MAKE_FIGS:
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    # Top-left: hourly glucose drift
    ax = axes[0, 0]
    for p in patients:
        name = p['name']
        if name not in exp2003:
            continue
        hp = exp2003[name]['hourly_optimal']
        hours = sorted([int(h) for h in hp.keys()])
        drifts = [hp[str(h)]['median_drift'] for h in hours]
        if len(hours) > 5:
            ax.plot(hours, drifts, 'o-', markersize=3, label=name, alpha=0.7)
    ax.axhline(0, color='black', ls='--', alpha=0.5)
    ax.set_xlabel('Hour of Day')
    ax.set_ylabel('Glucose Drift (mg/dL/h)')
    ax.set_title('Fasting Glucose Drift by Hour')
    ax.legend(fontsize=8, ncol=2)
    ax.grid(True, alpha=0.3)

    # Top-right: dawn phenomenon
    ax = axes[0, 1]
    names_list = list(exp2003.keys())
    dawn_mags = [exp2003[n]['dawn_magnitude_mg_dl_h'] for n in names_list]
    dawn_colors = ['red' if exp2003[n]['dawn_phenomenon'] else 'gray' for n in names_list]
    ax.barh(range(len(names_list)), dawn_mags, color=dawn_colors, alpha=0.7)
    ax.set_yticks(range(len(names_list)))
    ax.set_yticklabels(names_list)
    ax.set_xlabel('Dawn Magnitude (mg/dL/h above pre-dawn)')
    ax.set_title('Dawn Phenomenon Detection (red=detected)')
    ax.grid(True, alpha=0.3, axis='x')

    # Bottom-left: actual vs profile basal
    ax = axes[1, 0]
    hours_all = list(range(24))
    for p in patients[:6]:
        name = p['name']
        if name not in exp2003:
            continue
        hp = exp2003[name]['hourly_optimal']
        hours = sorted([int(h) for h in hp.keys()])
        actual = [hp[str(h)]['actual_basal'] for h in hours]
        if len(hours) > 5:
            ax.plot(hours, actual, 'o-', markersize=3, label=f"{name}", alpha=0.7)
    ax.set_xlabel('Hour of Day')
    ax.set_ylabel('Actual Basal Rate (U/h)')
    ax.set_title('Hourly Actual Basal Delivery (first 6 patients)')
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    # Bottom-right: suggested adjustments
    ax = axes[1, 1]
    for p in patients[:6]:
        name = p['name']
        if name not in exp2003:
            continue
        hp = exp2003[name]['hourly_optimal']
        hours = sorted([int(h) for h in hp.keys()])
        adj = [hp[str(h)]['suggested_adjustment'] for h in hours]
        if len(hours) > 5:
            ax.plot(hours, adj, 'o-', markersize=3, label=name, alpha=0.7)
    ax.axhline(0, color='black', ls='--', alpha=0.5)
    ax.set_xlabel('Hour of Day')
    ax.set_ylabel('Suggested Basal Adjustment (U/h)')
    ax.set_title('Data-Driven Basal Adjustments')
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    plt.suptitle('EXP-2003: Data-Driven Basal Rate Optimization', fontsize=14)
    plt.tight_layout()
    plt.savefig(f'{FIG_DIR}/therapy-fig03-basal-optimization.png', dpi=150)
    plt.close()
    print(f"  → Saved therapy-fig03-basal-optimization.png")

dawn_count = sum(1 for v in exp2003.values() if v['dawn_phenomenon'])
verdict_2003 = f"DAWN_{dawn_count}/{len(exp2003)}_PATIENTS"
results['EXP-2003'] = verdict_2003
print(f"\n  ✓ EXP-2003 verdict: {verdict_2003}")


# ══════════════════════════════════════════════════════════════
# EXP-2004: Non-Meal Variability Driver Decomposition
# ══════════════════════════════════════════════════════════════
print("\n" + "#" * 70)
print("# Running EXP-2004")
print("#" * 70)
print("\n" + "=" * 70)
print("EXP-2004: Non-Meal Variability Driver Decomposition")
print("=" * 70)

exp2004 = {}
for p in patients:
    name = p['name']
    df = p['df']
    glucose = df['glucose'].values.astype(float)
    carbs = df['carbs'].values.astype(float) if 'carbs' in df.columns else np.zeros(len(glucose))
    iob = df['iob'].values.astype(float) if 'iob' in df.columns else np.full(len(glucose), np.nan)
    net_basal = df['net_basal'].values.astype(float) if 'net_basal' in df.columns else np.zeros(len(glucose))

    n_days = len(glucose) // STEPS_PER_DAY
    if n_days < 7:
        exp2004[name] = {'status': 'insufficient'}
        continue

    # Compute variability by category
    # 1. Circadian: hour-of-day mean glucose pattern (predictable)
    hourly_means = np.zeros(24)
    for h in range(24):
        step_start = h * STEPS_PER_HOUR
        hour_vals = []
        for d in range(n_days):
            start = d * STEPS_PER_DAY + step_start
            end = start + STEPS_PER_HOUR
            if end <= len(glucose):
                vals = glucose[start:end]
                valid = vals[np.isfinite(vals)]
                if len(valid) > 0:
                    hour_vals.extend(valid)
        hourly_means[h] = np.mean(hour_vals) if hour_vals else np.nan

    # Circadian variance
    circadian_var = float(np.nanvar(hourly_means)) if np.sum(np.isfinite(hourly_means)) > 12 else 0

    # 2. Day-to-day: variance of daily means
    daily_means = []
    for d in range(n_days):
        start = d * STEPS_PER_DAY
        end = start + STEPS_PER_DAY
        day_g = glucose[start:end]
        valid = day_g[np.isfinite(day_g)]
        if len(valid) > 100:
            daily_means.append(np.mean(valid))
    day_to_day_var = float(np.var(daily_means)) if len(daily_means) > 7 else 0

    # 3. IOB-driven: correlation between IOB changes and glucose changes
    dg = np.diff(glucose)
    d_iob = np.diff(iob)
    mask = np.isfinite(dg) & np.isfinite(d_iob)
    iob_corr = float(np.corrcoef(dg[mask], d_iob[mask])[0, 1]) if np.sum(mask) > 100 else 0
    iob_explained_var = iob_corr ** 2 * 100  # R² as percentage

    # 4. Post-meal residual: unexplained variance in 2h after meals
    meal_steps = np.where(carbs >= 10)[0]
    post_meal_vars = []
    for ms in meal_steps:
        window = glucose[ms:ms + 24]  # 2h
        valid = window[np.isfinite(window)]
        if len(valid) > 6:
            # Remove linear trend
            x = np.arange(len(valid))
            p_fit = np.polyfit(x, valid, 1)
            residual = valid - np.polyval(p_fit, x)
            post_meal_vars.append(float(np.var(residual)))
    post_meal_residual = float(np.mean(post_meal_vars)) if post_meal_vars else 0

    # 5. Fasting glucose variability (overnight, 0-6AM)
    fasting_vals = []
    for d in range(n_days):
        start = d * STEPS_PER_DAY  # midnight
        end = start + 6 * STEPS_PER_HOUR  # 6 AM
        if end <= len(glucose):
            window = glucose[start:end]
            valid = window[np.isfinite(window)]
            if len(valid) > 30:
                fasting_vals.extend(valid)
    fasting_var = float(np.var(fasting_vals)) if len(fasting_vals) > 100 else 0

    # 6. Loop intervention variance: variance explained by basal adjustments
    d_net = np.diff(net_basal)
    mask_net = np.isfinite(dg) & np.isfinite(d_net)
    loop_corr = float(np.corrcoef(dg[mask_net], d_net[mask_net])[0, 1]) if np.sum(mask_net) > 100 else 0
    loop_explained = loop_corr ** 2 * 100

    total_var = float(np.nanvar(glucose))

    exp2004[name] = {
        'total_var': round(total_var, 1),
        'circadian_var': round(circadian_var, 1),
        'circadian_pct': round(circadian_var / total_var * 100, 1) if total_var > 0 else 0,
        'day_to_day_var': round(day_to_day_var, 1),
        'day_to_day_pct': round(day_to_day_var / total_var * 100, 1) if total_var > 0 else 0,
        'iob_explained_pct': round(iob_explained_var, 1),
        'loop_explained_pct': round(loop_explained, 1),
        'fasting_var': round(fasting_var, 1),
        'fasting_pct': round(fasting_var / total_var * 100, 1) if total_var > 0 else 0,
        'post_meal_residual_var': round(post_meal_residual, 1),
    }

    print(f"  {name}: total_var={total_var:.0f} circadian={circadian_var/total_var*100:.0f}% "
          f"day2day={day_to_day_var/total_var*100:.0f}% IOB_R²={iob_explained_var:.1f}% "
          f"loop_R²={loop_explained:.1f}% fasting={fasting_var/total_var*100:.0f}%")

if MAKE_FIGS:
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    # Top-left: variance decomposition stacked bars
    ax = axes[0, 0]
    names_list = [n for n in exp2004 if 'circadian_pct' in exp2004[n]]
    circ = [exp2004[n]['circadian_pct'] for n in names_list]
    d2d = [exp2004[n]['day_to_day_pct'] for n in names_list]
    fast = [exp2004[n]['fasting_pct'] for n in names_list]
    x = np.arange(len(names_list))
    ax.bar(x, circ, label='Circadian', alpha=0.8)
    ax.bar(x, d2d, bottom=circ, label='Day-to-day', alpha=0.8)
    ax.bar(x, fast, bottom=[c+d for c,d in zip(circ, d2d)], label='Fasting', alpha=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(names_list)
    ax.set_ylabel('% of Total Variance')
    ax.set_title('Non-Meal Variability Components')
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')

    # Top-right: IOB vs loop explained variance
    ax = axes[0, 1]
    iob_pcts = [exp2004[n]['iob_explained_pct'] for n in names_list]
    loop_pcts = [exp2004[n]['loop_explained_pct'] for n in names_list]
    ax.scatter(iob_pcts, loop_pcts, s=60, zorder=3)
    for n, iv, lv in zip(names_list, iob_pcts, loop_pcts):
        ax.annotate(n, (iv, lv), fontsize=9)
    ax.set_xlabel('IOB Explained Variance (%)')
    ax.set_ylabel('Loop Basal Explained Variance (%)')
    ax.set_title('Insulin vs Loop Explanatory Power')
    ax.grid(True, alpha=0.3)

    # Bottom-left: fasting variance vs TIR
    ax = axes[1, 0]
    for p_data in patients:
        name = p_data['name']
        if name not in exp2004 or 'fasting_pct' not in exp2004[name]:
            continue
        g = p_data['df']['glucose'].values.astype(float)
        tir = np.mean((g[np.isfinite(g)] >= 70) & (g[np.isfinite(g)] <= 180)) * 100
        ax.scatter(exp2004[name]['fasting_pct'], tir, s=60, zorder=3)
        ax.annotate(name, (exp2004[name]['fasting_pct'], tir), fontsize=9)
    ax.set_xlabel('Fasting Variance (% of total)')
    ax.set_ylabel('TIR (%)')
    ax.set_title('Fasting Variability vs Control Quality')
    ax.grid(True, alpha=0.3)

    # Bottom-right: total variance ranking
    ax = axes[1, 1]
    sorted_names = sorted(names_list, key=lambda n: exp2004[n]['total_var'])
    total_vars = [exp2004[n]['total_var'] for n in sorted_names]
    colors = ['green' if v < 3000 else 'orange' if v < 5000 else 'red' for v in total_vars]
    ax.barh(range(len(sorted_names)), total_vars, color=colors, alpha=0.7)
    ax.set_yticks(range(len(sorted_names)))
    ax.set_yticklabels(sorted_names)
    ax.set_xlabel('Total Glucose Variance (mg²/dL²)')
    ax.set_title('Patient Variability Ranking')
    ax.grid(True, alpha=0.3, axis='x')

    plt.suptitle('EXP-2004: Non-Meal Variability Driver Decomposition', fontsize=14)
    plt.tight_layout()
    plt.savefig(f'{FIG_DIR}/therapy-fig04-nonmeal-variability.png', dpi=150)
    plt.close()
    print(f"  → Saved therapy-fig04-nonmeal-variability.png")

circ_mean = np.mean([exp2004[n]['circadian_pct'] for n in exp2004 if 'circadian_pct' in exp2004[n]])
iob_mean = np.mean([exp2004[n]['iob_explained_pct'] for n in exp2004 if 'iob_explained_pct' in exp2004[n]])
verdict_2004 = f"CIRCADIAN_{circ_mean:.0f}%_IOB_R²={iob_mean:.1f}%"
results['EXP-2004'] = verdict_2004
print(f"\n  ✓ EXP-2004 verdict: {verdict_2004}")


# ══════════════════════════════════════════════════════════════
# EXP-2005: Automated Meal Detection from CGM
# ══════════════════════════════════════════════════════════════
print("\n" + "#" * 70)
print("# Running EXP-2005")
print("#" * 70)
print("\n" + "=" * 70)
print("EXP-2005: Automated Meal Detection from CGM")
print("=" * 70)

exp2005 = {}
for p in patients:
    name = p['name']
    df = p['df']
    glucose = df['glucose'].values.astype(float)
    carbs = df['carbs'].values.astype(float) if 'carbs' in df.columns else np.zeros(len(glucose))

    # Ground truth meals
    meal_steps = set(np.where(carbs >= 10)[0])
    total_meals = len(meal_steps)

    # Simple CGM-based meal detector:
    # Rising glucose > threshold for sustained period
    dg = np.diff(glucose)
    dg = np.append(dg, 0)

    # Smooth: 15-min rolling average of glucose change rate
    window = 3
    dg_smooth = np.convolve(dg, np.ones(window)/window, mode='same')

    # Detection thresholds
    thresholds = [1.0, 1.5, 2.0, 3.0]  # mg/dL per 5 min
    threshold_results = {}

    for thresh in thresholds:
        # Rising above threshold
        rising = dg_smooth > thresh
        # Detect onset: transition from not-rising to rising
        detections = []
        in_rise = False
        rise_start = 0
        for i in range(len(rising)):
            if rising[i] and not in_rise:
                in_rise = True
                rise_start = i
            elif not rising[i] and in_rise:
                in_rise = False
                # This was a rise event from rise_start to i
                duration = (i - rise_start) * 5  # minutes
                if duration >= 10:  # at least 10 min
                    detections.append(rise_start)

        # Match detections to meals (within ±30 min)
        tp = 0
        fp = 0
        matched_meals = set()
        for det in detections:
            found = False
            for ms in meal_steps:
                if abs(det - ms) <= 6:  # ±30min (6 steps)
                    if ms not in matched_meals:
                        tp += 1
                        matched_meals.add(ms)
                        found = True
                        break
            if not found:
                fp += 1

        fn = total_meals - len(matched_meals)
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

        threshold_results[str(thresh)] = {
            'threshold': thresh,
            'detections': len(detections),
            'tp': tp, 'fp': fp, 'fn': fn,
            'precision': round(precision, 3),
            'recall': round(recall, 3),
            'f1': round(f1, 3),
        }

    # Best F1
    best_thresh = max(threshold_results.values(), key=lambda x: x['f1'])

    exp2005[name] = {
        'total_meals': total_meals,
        'threshold_results': threshold_results,
        'best_threshold': best_thresh['threshold'],
        'best_f1': best_thresh['f1'],
        'best_precision': best_thresh['precision'],
        'best_recall': best_thresh['recall'],
    }

    print(f"  {name}: meals={total_meals} best_thresh={best_thresh['threshold']} "
          f"F1={best_thresh['f1']:.3f} P={best_thresh['precision']:.3f} R={best_thresh['recall']:.3f}")

if MAKE_FIGS:
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    # Top-left: F1 by threshold across patients
    ax = axes[0, 0]
    for thresh in thresholds:
        f1s = [exp2005[n]['threshold_results'][str(thresh)]['f1'] for n in exp2005]
        ax.plot(range(len(exp2005)), f1s, 'o-', label=f'Thresh={thresh}', alpha=0.7)
    ax.set_xticks(range(len(exp2005)))
    ax.set_xticklabels(list(exp2005.keys()))
    ax.set_ylabel('F1 Score')
    ax.set_title('Meal Detection F1 by Threshold')
    ax.legend()
    ax.grid(True, alpha=0.3)

    # Top-right: precision-recall curve (aggregated)
    ax = axes[0, 1]
    for n in exp2005:
        precs = [exp2005[n]['threshold_results'][str(t)]['precision'] for t in thresholds]
        recs = [exp2005[n]['threshold_results'][str(t)]['recall'] for t in thresholds]
        ax.plot(recs, precs, 'o-', label=n, alpha=0.7, markersize=4)
    ax.set_xlabel('Recall')
    ax.set_ylabel('Precision')
    ax.set_title('Precision-Recall by Patient')
    ax.legend(fontsize=8, ncol=2)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.grid(True, alpha=0.3)

    # Bottom-left: best F1 by patient
    ax = axes[1, 0]
    names_list = list(exp2005.keys())
    f1s = [exp2005[n]['best_f1'] for n in names_list]
    colors = ['green' if f > 0.5 else 'orange' if f > 0.3 else 'red' for f in f1s]
    ax.barh(range(len(names_list)), f1s, color=colors, alpha=0.7)
    ax.set_yticks(range(len(names_list)))
    ax.set_yticklabels(names_list)
    ax.set_xlabel('Best F1 Score')
    ax.set_title('Meal Detection Performance (best threshold per patient)')
    ax.axvline(0.5, color='black', ls='--', alpha=0.5)
    ax.grid(True, alpha=0.3, axis='x')

    # Bottom-right: detections vs actual meals
    ax = axes[1, 1]
    total_m = [exp2005[n]['total_meals'] for n in names_list]
    best_det = [exp2005[n]['threshold_results'][str(exp2005[n]['best_threshold'])]['detections'] for n in names_list]
    ax.scatter(total_m, best_det, s=60, zorder=3)
    for n, tm, bd in zip(names_list, total_m, best_det):
        ax.annotate(n, (tm, bd), fontsize=9)
    max_val = max(max(total_m), max(best_det)) * 1.1
    ax.plot([0, max_val], [0, max_val], 'k--', alpha=0.5, label='Perfect')
    ax.set_xlabel('Actual Meals')
    ax.set_ylabel('Detected Events')
    ax.set_title('Detections vs Actual Meals')
    ax.legend()
    ax.grid(True, alpha=0.3)

    plt.suptitle('EXP-2005: Automated Meal Detection from CGM', fontsize=14)
    plt.tight_layout()
    plt.savefig(f'{FIG_DIR}/therapy-fig05-meal-detection.png', dpi=150)
    plt.close()
    print(f"  → Saved therapy-fig05-meal-detection.png")

mean_f1 = np.mean([exp2005[n]['best_f1'] for n in exp2005])
verdict_2005 = f"MEAN_F1={mean_f1:.3f}_BEST_THRESH={np.median([exp2005[n]['best_threshold'] for n in exp2005])}"
results['EXP-2005'] = verdict_2005
print(f"\n  ✓ EXP-2005 verdict: {verdict_2005}")


# ══════════════════════════════════════════════════════════════
# EXP-2006: Hypo Recovery and Rebound Characterization
# ══════════════════════════════════════════════════════════════
print("\n" + "#" * 70)
print("# Running EXP-2006")
print("#" * 70)
print("\n" + "=" * 70)
print("EXP-2006: Hypo Recovery and Rebound Characterization")
print("=" * 70)

exp2006 = {}
for p in patients:
    name = p['name']
    df = p['df']
    glucose = df['glucose'].values.astype(float)
    carbs = df['carbs'].values.astype(float) if 'carbs' in df.columns else np.zeros(len(glucose))

    # Find hypo events: glucose < 70 for first time (onset)
    hypo_events = []
    in_hypo = False
    hypo_start = -1
    for i in range(len(glucose)):
        if not np.isfinite(glucose[i]):
            continue
        if glucose[i] < HYPO_THRESH and not in_hypo:
            in_hypo = True
            hypo_start = i
        elif glucose[i] >= HYPO_THRESH and in_hypo:
            in_hypo = False
            hypo_events.append(hypo_start)

    # Analyze recovery for each event
    recovery_times = []
    recovery_curves = []
    rebound_heights = []
    rebound_peaks = []
    carb_rescues = []

    for hs in hypo_events:
        if hs + 72 > len(glucose):  # need 6h follow-up
            continue
        # Recovery window: 6h after hypo onset
        window = glucose[hs:hs + 72]
        if np.sum(np.isfinite(window)) < 30:
            continue

        nadir = np.nanmin(window[:12])  # nadir within 1h
        nadir_idx = np.nanargmin(window[:12])

        # Time to return to 80 mg/dL
        recovery_time = 360  # default: didn't recover in 6h
        for ri in range(nadir_idx, len(window)):
            if np.isfinite(window[ri]) and window[ri] >= 80:
                recovery_time = (ri - nadir_idx) * 5
                break
        recovery_times.append(recovery_time)

        # Rebound: max glucose in 2-4h after nadir
        rebound_window = window[nadir_idx + 24:min(nadir_idx + 48, len(window))]
        if len(rebound_window) > 0 and np.sum(np.isfinite(rebound_window)) > 0:
            rebound_peak = float(np.nanmax(rebound_window))
            rebound_heights.append(rebound_peak - 80)  # height above target
            rebound_peaks.append(rebound_peak)

        # Carb rescue: any carbs within 30min of hypo onset
        carb_window = carbs[hs:min(hs + 6, len(carbs))]
        rescue = bool(np.nansum(carb_window) > 0)
        carb_rescues.append(rescue)

        # Store normalized curve (delta from nadir)
        curve = window - nadir
        recovery_curves.append(curve)

    if len(recovery_times) < 3:
        exp2006[name] = {'n_hypos': len(hypo_events), 'status': 'insufficient_recovery_data'}
        print(f"  {name}: only {len(recovery_times)} analyzable hypos")
        continue

    # Recovery speed classification
    fast_recovery = sum(1 for t in recovery_times if t <= 30)
    slow_recovery = sum(1 for t in recovery_times if t > 60)

    # Rebound classification
    rebound_hyper = sum(1 for h in rebound_peaks if h > 180)  # rebounded above 180
    rebound_pct = rebound_hyper / len(rebound_peaks) * 100 if rebound_peaks else 0

    exp2006[name] = {
        'n_hypos': len(hypo_events),
        'n_analyzed': len(recovery_times),
        'median_recovery_min': int(np.median(recovery_times)),
        'mean_recovery_min': round(float(np.mean(recovery_times)), 1),
        'fast_recovery_pct': round(fast_recovery / len(recovery_times) * 100, 1),
        'slow_recovery_pct': round(slow_recovery / len(recovery_times) * 100, 1),
        'median_rebound_peak': round(float(np.median(rebound_peaks)), 1) if rebound_peaks else np.nan,
        'rebound_to_hyper_pct': round(rebound_pct, 1),
        'carb_rescue_pct': round(sum(carb_rescues) / len(carb_rescues) * 100, 1) if carb_rescues else 0,
        'mean_curve': [round(float(np.nanmean([c[i] for c in recovery_curves if i < len(c)])), 1)
                       for i in range(min(72, min(len(c) for c in recovery_curves)))] if recovery_curves else [],
    }

    print(f"  {name}: hypos={len(hypo_events)} analyzed={len(recovery_times)} "
          f"recovery={np.median(recovery_times):.0f}min "
          f"rebound_peak={np.median(rebound_peaks):.0f}mg/dL "
          f"rebound→hyper={rebound_pct:.0f}% rescue={sum(carb_rescues)/len(carb_rescues)*100:.0f}%")

if MAKE_FIGS:
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))

    # Top-left: recovery curves by patient (mean)
    ax = axes[0, 0]
    time_min = np.arange(72) * 5
    for p_data in patients:
        name = p_data['name']
        if name not in exp2006 or 'mean_curve' not in exp2006[name]:
            continue
        curve = exp2006[name].get('mean_curve', [])
        if len(curve) > 5:
            ax.plot(time_min[:len(curve)], curve, '-', label=name, alpha=0.7)
    ax.axhline(0, color='gray', ls='--', alpha=0.5)
    ax.axhline(80, color='green', ls=':', alpha=0.5, label='Target (80)')
    ax.set_xlabel('Time since nadir (min)')
    ax.set_ylabel('Δ Glucose from nadir (mg/dL)')
    ax.set_title('Mean Recovery Curve by Patient')
    ax.legend(fontsize=8, ncol=2)
    ax.grid(True, alpha=0.3)

    # Top-right: recovery time distribution
    ax = axes[0, 1]
    names_list = [n for n in exp2006 if 'median_recovery_min' in exp2006[n]]
    rec_times = [exp2006[n]['median_recovery_min'] for n in names_list]
    colors = ['green' if t <= 30 else 'orange' if t <= 60 else 'red' for t in rec_times]
    ax.barh(range(len(names_list)), rec_times, color=colors, alpha=0.7)
    ax.set_yticks(range(len(names_list)))
    ax.set_yticklabels(names_list)
    ax.set_xlabel('Median Recovery Time (min)')
    ax.set_title('Time to Return to 80 mg/dL')
    ax.axvline(30, color='green', ls='--', alpha=0.5, label='Fast (30min)')
    ax.axvline(60, color='orange', ls='--', alpha=0.5, label='Slow (60min)')
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3, axis='x')

    # Bottom-left: rebound to hyperglycemia
    ax = axes[1, 0]
    rebound_pcts = [exp2006[n].get('rebound_to_hyper_pct', 0) for n in names_list]
    rebound_colors = ['red' if r > 30 else 'orange' if r > 15 else 'green' for r in rebound_pcts]
    ax.barh(range(len(names_list)), rebound_pcts, color=rebound_colors, alpha=0.7)
    ax.set_yticks(range(len(names_list)))
    ax.set_yticklabels(names_list)
    ax.set_xlabel('Rebound to Hyperglycemia (%)')
    ax.set_title('% of Hypos Rebounding Above 180 mg/dL')
    ax.grid(True, alpha=0.3, axis='x')

    # Bottom-right: carb rescue rate
    ax = axes[1, 1]
    rescue_pcts = [exp2006[n].get('carb_rescue_pct', 0) for n in names_list]
    ax.barh(range(len(names_list)), rescue_pcts, color='steelblue', alpha=0.7)
    ax.set_yticks(range(len(names_list)))
    ax.set_yticklabels(names_list)
    ax.set_xlabel('Carb Rescue Rate (%)')
    ax.set_title('% of Hypos with Carb Treatment Within 30min')
    ax.grid(True, alpha=0.3, axis='x')

    plt.suptitle('EXP-2006: Hypo Recovery & Rebound Characterization', fontsize=14)
    plt.tight_layout()
    plt.savefig(f'{FIG_DIR}/therapy-fig06-hypo-recovery.png', dpi=150)
    plt.close()
    print(f"  → Saved therapy-fig06-hypo-recovery.png")

med_recovery = np.median([exp2006[n]['median_recovery_min'] for n in exp2006 if 'median_recovery_min' in exp2006[n]])
rebound_hyper_mean = np.mean([exp2006[n].get('rebound_to_hyper_pct', 0) for n in exp2006 if 'median_recovery_min' in exp2006[n]])
verdict_2006 = f"RECOVERY_{med_recovery:.0f}min_REBOUND_HYPER_{rebound_hyper_mean:.0f}%"
results['EXP-2006'] = verdict_2006
print(f"\n  ✓ EXP-2006 verdict: {verdict_2006}")


# ══════════════════════════════════════════════════════════════
# EXP-2007: Loop Intervention Effectiveness Scoring
# ══════════════════════════════════════════════════════════════
print("\n" + "#" * 70)
print("# Running EXP-2007")
print("#" * 70)
print("\n" + "=" * 70)
print("EXP-2007: Loop Intervention Effectiveness Scoring")
print("=" * 70)

exp2007 = {}
for p in patients:
    name = p['name']
    df = p['df']
    glucose = df['glucose'].values.astype(float)
    net_basal = df['net_basal'].values.astype(float) if 'net_basal' in df.columns else np.zeros(len(glucose))
    enacted_rate = df['enacted_rate'].values.astype(float) if 'enacted_rate' in df.columns else np.full(len(glucose), np.nan)

    basal_schedule = df.attrs.get('basal_schedule', [{'value': 1.0}])
    profile_basal = basal_schedule[0]['value'] if basal_schedule else 1.0

    # Classify loop actions
    # 1. Suspension: enacted_rate ≈ 0 or net_basal << profile_basal
    # 2. Increase: net_basal > profile_basal * 1.2
    # 3. Normal: within ±20% of profile
    n_total = 0
    n_suspend = 0
    n_increase = 0
    n_normal = 0

    # Track outcome: glucose 30min later
    suspend_outcomes = []  # delta glucose after suspension
    increase_outcomes = []
    normal_outcomes = []

    for i in range(len(glucose) - 6):
        if not np.isfinite(net_basal[i]) or not np.isfinite(glucose[i]) or not np.isfinite(glucose[i + 6]):
            continue
        n_total += 1
        delta_g = glucose[i + 6] - glucose[i]

        if net_basal[i] < profile_basal * 0.2:
            n_suspend += 1
            suspend_outcomes.append(delta_g)
        elif net_basal[i] > profile_basal * 1.3:
            n_increase += 1
            increase_outcomes.append(delta_g)
        else:
            n_normal += 1
            normal_outcomes.append(delta_g)

    # Effectiveness: did the action achieve its purpose?
    # Suspension should prevent lows (glucose should rise or stay stable)
    suspend_effective = sum(1 for d in suspend_outcomes if d > -5) / len(suspend_outcomes) * 100 if suspend_outcomes else 0
    # Increase should lower highs (glucose should drop or stay stable)
    increase_effective = sum(1 for d in increase_outcomes if d < 5) / len(increase_outcomes) * 100 if increase_outcomes else 0

    # Context: what was glucose when each action was taken?
    suspend_glucose = []
    increase_glucose = []
    for i in range(len(glucose) - 6):
        if not np.isfinite(net_basal[i]) or not np.isfinite(glucose[i]):
            continue
        if net_basal[i] < profile_basal * 0.2:
            suspend_glucose.append(glucose[i])
        elif net_basal[i] > profile_basal * 1.3:
            increase_glucose.append(glucose[i])

    exp2007[name] = {
        'n_total': n_total,
        'suspend_pct': round(n_suspend / n_total * 100, 1) if n_total > 0 else 0,
        'increase_pct': round(n_increase / n_total * 100, 1) if n_total > 0 else 0,
        'normal_pct': round(n_normal / n_total * 100, 1) if n_total > 0 else 0,
        'suspend_effective_pct': round(suspend_effective, 1),
        'increase_effective_pct': round(increase_effective, 1),
        'suspend_mean_outcome': round(float(np.mean(suspend_outcomes)), 1) if suspend_outcomes else np.nan,
        'increase_mean_outcome': round(float(np.mean(increase_outcomes)), 1) if increase_outcomes else np.nan,
        'suspend_at_glucose': round(float(np.median(suspend_glucose)), 0) if suspend_glucose else np.nan,
        'increase_at_glucose': round(float(np.median(increase_glucose)), 0) if increase_glucose else np.nan,
    }

    print(f"  {name}: suspend={n_suspend/n_total*100:.0f}% increase={n_increase/n_total*100:.0f}% "
          f"suspend_eff={suspend_effective:.0f}% increase_eff={increase_effective:.0f}% "
          f"susp@{np.median(suspend_glucose):.0f}mg/dL inc@{np.median(increase_glucose):.0f}mg/dL")

if MAKE_FIGS:
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))

    # Top-left: action distribution
    ax = axes[0, 0]
    names_list = list(exp2007.keys())
    susp = [exp2007[n]['suspend_pct'] for n in names_list]
    incr = [exp2007[n]['increase_pct'] for n in names_list]
    norm = [exp2007[n]['normal_pct'] for n in names_list]
    x = np.arange(len(names_list))
    ax.bar(x, susp, label='Suspend', color='blue', alpha=0.7)
    ax.bar(x, norm, bottom=susp, label='Normal', color='gray', alpha=0.7)
    ax.bar(x, incr, bottom=[s+n for s,n in zip(susp, norm)], label='Increase', color='red', alpha=0.7)
    ax.set_xticks(x)
    ax.set_xticklabels(names_list)
    ax.set_ylabel('% of Time')
    ax.set_title('Loop Action Distribution')
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')

    # Top-right: effectiveness
    ax = axes[0, 1]
    susp_eff = [exp2007[n]['suspend_effective_pct'] for n in names_list]
    incr_eff = [exp2007[n]['increase_effective_pct'] for n in names_list]
    x = np.arange(len(names_list))
    width = 0.35
    ax.bar(x - width/2, susp_eff, width, label='Suspend Effective', color='blue', alpha=0.7)
    ax.bar(x + width/2, incr_eff, width, label='Increase Effective', color='red', alpha=0.7)
    ax.set_xticks(x)
    ax.set_xticklabels(names_list)
    ax.set_ylabel('Effectiveness (%)')
    ax.set_title('Loop Action Effectiveness')
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')

    # Bottom-left: glucose at action
    ax = axes[1, 0]
    susp_g = [exp2007[n]['suspend_at_glucose'] for n in names_list]
    incr_g = [exp2007[n]['increase_at_glucose'] for n in names_list]
    ax.scatter(susp_g, incr_g, s=60, zorder=3)
    for n, sg, ig in zip(names_list, susp_g, incr_g):
        if np.isfinite(sg) and np.isfinite(ig):
            ax.annotate(n, (sg, ig), fontsize=9)
    ax.set_xlabel('Median Glucose at Suspend (mg/dL)')
    ax.set_ylabel('Median Glucose at Increase (mg/dL)')
    ax.set_title('Glucose Context for Loop Actions')
    ax.axhline(180, color='red', ls='--', alpha=0.3)
    ax.axvline(100, color='green', ls='--', alpha=0.3)
    ax.grid(True, alpha=0.3)

    # Bottom-right: outcome by action type
    ax = axes[1, 1]
    susp_out = [exp2007[n]['suspend_mean_outcome'] for n in names_list]
    incr_out = [exp2007[n]['increase_mean_outcome'] for n in names_list]
    x = np.arange(len(names_list))
    ax.bar(x - width/2, susp_out, width, label='Suspend Outcome', color='blue', alpha=0.7)
    ax.bar(x + width/2, incr_out, width, label='Increase Outcome', color='red', alpha=0.7)
    ax.axhline(0, color='black', ls='--', alpha=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels(names_list)
    ax.set_ylabel('Mean Δ Glucose 30min (mg/dL)')
    ax.set_title('Glucose Outcome by Action Type')
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')

    plt.suptitle('EXP-2007: Loop Intervention Effectiveness Scoring', fontsize=14)
    plt.tight_layout()
    plt.savefig(f'{FIG_DIR}/therapy-fig07-loop-effectiveness.png', dpi=150)
    plt.close()
    print(f"  → Saved therapy-fig07-loop-effectiveness.png")

mean_susp_eff = np.mean([exp2007[n]['suspend_effective_pct'] for n in exp2007])
mean_incr_eff = np.mean([exp2007[n]['increase_effective_pct'] for n in exp2007])
mean_susp_pct = np.mean([exp2007[n]['suspend_pct'] for n in exp2007])
verdict_2007 = f"SUSPEND_{mean_susp_pct:.0f}%_SUSP_EFF={mean_susp_eff:.0f}%_INCR_EFF={mean_incr_eff:.0f}%"
results['EXP-2007'] = verdict_2007
print(f"\n  ✓ EXP-2007 verdict: {verdict_2007}")


# ══════════════════════════════════════════════════════════════
# EXP-2008: Synthesis — Optimal Personalized Therapy Profiles
# ══════════════════════════════════════════════════════════════
print("\n" + "#" * 70)
print("# Running EXP-2008")
print("#" * 70)
print("\n" + "=" * 70)
print("EXP-2008: Synthesis — Optimal Personalized Therapy Profiles")
print("=" * 70)

exp2008 = {}
for p in patients:
    name = p['name']
    df = p['df']
    glucose = df['glucose'].values.astype(float)
    metrics = glucose_metrics(glucose)

    # Gather all findings for this patient
    profile = {
        'tir': metrics['tir'],
        'tbr': metrics['tbr'],
        'tar': metrics['tar'],
        'cv': metrics['cv'],
    }

    # From EXP-2001: absorption
    if name in exp2001 and 'shape' in exp2001[name]:
        profile['absorption_peak_min'] = exp2001[name]['peak_time_min']
        profile['absorption_shape'] = exp2001[name]['shape']

    # From EXP-2002: ISF
    if name in exp2002:
        profile['isf_profile'] = exp2002[name]['profile_isf']
        profile['isf_effective'] = exp2002[name]['effective_isf_median']
        profile['isf_ratio'] = exp2002[name]['profile_vs_effective_ratio']

    # From EXP-2003: basal/dawn
    if name in exp2003:
        profile['dawn_phenomenon'] = exp2003[name]['dawn_phenomenon']
        profile['dawn_magnitude'] = exp2003[name]['dawn_magnitude_mg_dl_h']

    # From EXP-2004: variability drivers
    if name in exp2004 and 'circadian_pct' in exp2004[name]:
        profile['var_circadian_pct'] = exp2004[name]['circadian_pct']
        profile['var_iob_R2'] = exp2004[name]['iob_explained_pct']
        profile['var_fasting_pct'] = exp2004[name]['fasting_pct']

    # From EXP-2006: hypo recovery
    if name in exp2006 and 'median_recovery_min' in exp2006[name]:
        profile['hypo_recovery_min'] = exp2006[name]['median_recovery_min']
        profile['rebound_hyper_pct'] = exp2006[name]['rebound_to_hyper_pct']

    # From EXP-2007: loop effectiveness
    if name in exp2007:
        profile['loop_suspend_pct'] = exp2007[name]['suspend_pct']
        profile['loop_suspend_eff'] = exp2007[name]['suspend_effective_pct']
        profile['loop_increase_eff'] = exp2007[name]['increase_effective_pct']

    # Generate recommendations
    recs = []
    # ISF mismatch
    if 'isf_ratio' in profile and np.isfinite(profile['isf_ratio']):
        if profile['isf_ratio'] > 1.3:
            recs.append(f"ISF too low in profile: effective {profile['isf_effective']} vs profile {profile['isf_profile']} ({profile['isf_ratio']:.1f}×)")
        elif profile['isf_ratio'] < 0.7:
            recs.append(f"ISF too high in profile: effective {profile['isf_effective']} vs profile {profile['isf_profile']} ({profile['isf_ratio']:.1f}×)")

    # Dawn phenomenon
    if profile.get('dawn_phenomenon'):
        recs.append(f"Dawn phenomenon detected: +{profile['dawn_magnitude']:.0f} mg/dL/h; consider dawn ramp basal")

    # Slow absorption
    if profile.get('absorption_peak_min', 0) > 75:
        recs.append(f"Slow absorber (peak {profile['absorption_peak_min']}min): use extended bolus / slower absorption model")

    # High hypo rebound
    if profile.get('rebound_hyper_pct', 0) > 25:
        recs.append(f"Hypo rebound to hyper {profile['rebound_hyper_pct']:.0f}%: reduce rescue carbs or post-hypo algorithm")

    # High TBR
    if profile.get('tbr', 0) > 4:
        recs.append(f"TBR {profile['tbr']:.1f}% exceeds 4% target: reduce aggressiveness")

    # Low loop effectiveness
    if profile.get('loop_suspend_eff', 100) < 60:
        recs.append(f"Suspension only {profile['loop_suspend_eff']:.0f}% effective: insulin still active when suspending")

    profile['recommendations'] = recs
    profile['n_recommendations'] = len(recs)

    # Priority score: higher = more urgent
    priority = 0
    if metrics['tbr'] > 5:
        priority += 3
    if metrics['tir'] < 60:
        priority += 2
    if len(recs) > 2:
        priority += 1
    profile['priority'] = priority

    exp2008[name] = profile
    print(f"  {name}: TIR={metrics['tir']:.0f}% priority={priority} recs={len(recs)}")
    for r in recs:
        print(f"    → {r}")

if MAKE_FIGS:
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))

    # Top-left: recommendation count by patient (ordered by priority)
    ax = axes[0, 0]
    sorted_names = sorted(exp2008.keys(), key=lambda n: exp2008[n].get('priority', 0), reverse=True)
    n_recs = [exp2008[n]['n_recommendations'] for n in sorted_names]
    priorities = [exp2008[n].get('priority', 0) for n in sorted_names]
    colors = ['red' if p >= 3 else 'orange' if p >= 2 else 'green' for p in priorities]
    ax.barh(range(len(sorted_names)), n_recs, color=colors, alpha=0.7)
    ax.set_yticks(range(len(sorted_names)))
    ax.set_yticklabels([f"{n} (P{exp2008[n].get('priority',0)})" for n in sorted_names])
    ax.set_xlabel('Number of Recommendations')
    ax.set_title('Therapy Profile: Recommendations by Priority')
    ax.grid(True, alpha=0.3, axis='x')

    # Top-right: absorption vs ISF mismatch
    ax = axes[0, 1]
    for n in exp2008:
        peak = exp2008[n].get('absorption_peak_min', np.nan)
        ratio = exp2008[n].get('isf_ratio', np.nan)
        if np.isfinite(peak) and np.isfinite(ratio):
            color = 'red' if exp2008[n].get('priority', 0) >= 3 else 'blue'
            ax.scatter(peak, ratio, s=60, color=color, zorder=3)
            ax.annotate(n, (peak, ratio), fontsize=9)
    ax.axhline(1.0, color='black', ls='--', alpha=0.5, label='ISF match')
    ax.axvline(60, color='green', ls='--', alpha=0.3, label='Normal peak')
    ax.set_xlabel('Absorption Peak Time (min)')
    ax.set_ylabel('ISF Profile/Effective Ratio')
    ax.set_title('Absorption Speed vs ISF Accuracy')
    ax.legend()
    ax.grid(True, alpha=0.3)

    # Bottom-left: comprehensive radar chart (simplified as bar chart)
    ax = axes[1, 0]
    metrics_to_show = ['tir', 'tbr', 'cv']
    for idx, metric in enumerate(metrics_to_show):
        vals = [exp2008[n].get(metric, 0) for n in sorted_names]
        ax.barh(np.arange(len(sorted_names)) + idx * 0.25, vals, 0.25,
                label=metric.upper(), alpha=0.7)
    ax.set_yticks(np.arange(len(sorted_names)) + 0.25)
    ax.set_yticklabels(sorted_names)
    ax.set_xlabel('Value')
    ax.set_title('Key Metrics by Patient')
    ax.legend()
    ax.grid(True, alpha=0.3, axis='x')

    # Bottom-right: dawn vs absorption peak (two key actionable findings)
    ax = axes[1, 1]
    for n in exp2008:
        peak = exp2008[n].get('absorption_peak_min', np.nan)
        dawn = exp2008[n].get('dawn_magnitude', 0)
        if np.isfinite(peak):
            color = 'red' if exp2008[n].get('dawn_phenomenon') else 'blue'
            ax.scatter(peak, dawn, s=60, color=color, zorder=3)
            ax.annotate(n, (peak, dawn), fontsize=9)
    ax.set_xlabel('Absorption Peak (min)')
    ax.set_ylabel('Dawn Magnitude (mg/dL/h)')
    ax.set_title('Two Key Actionable Findings (red=dawn detected)')
    ax.grid(True, alpha=0.3)

    plt.suptitle('EXP-2008: Optimal Personalized Therapy Profiles', fontsize=14)
    plt.tight_layout()
    plt.savefig(f'{FIG_DIR}/therapy-fig08-synthesis.png', dpi=150)
    plt.close()
    print(f"  → Saved therapy-fig08-synthesis.png")

high_priority = sum(1 for v in exp2008.values() if v.get('priority', 0) >= 3)
total_recs = sum(v['n_recommendations'] for v in exp2008.values())
verdict_2008 = f"HIGH_PRIORITY_{high_priority}/11_TOTAL_RECS_{total_recs}"
results['EXP-2008'] = verdict_2008
print(f"\n  ✓ EXP-2008 verdict: {verdict_2008}")


# ══════════════════════════════════════════════════════════════
# SYNTHESIS
# ══════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("SYNTHESIS: Data-Driven Therapy Profiles")
print("=" * 70)
for k, v in sorted(results.items()):
    print(f"  {k}: {v}")

# Save results
output = {
    'experiment_group': 'EXP-2001–2008',
    'title': 'Data-Driven Therapy Profiles',
    'results': results,
    'exp2001_absorption': {k: {kk: vv for kk, vv in v.items() if kk != 'mean_curve'} for k, v in exp2001.items()},
    'exp2002_isf': exp2002,
    'exp2003_basal': {k: {kk: vv for kk, vv in v.items() if kk != 'hourly_optimal'} for k, v in exp2003.items()},
    'exp2004_variability': exp2004,
    'exp2005_meal_detection': {k: {kk: vv for kk, vv in v.items() if kk != 'threshold_results'} for k, v in exp2005.items()},
    'exp2006_hypo_recovery': {k: {kk: vv for kk, vv in v.items() if kk != 'mean_curve'} for k, v in exp2006.items()},
    'exp2007_loop_effectiveness': exp2007,
    'exp2008_synthesis': {k: {kk: vv for kk, vv in v.items()} for k, v in exp2008.items()},
}

with open(f'{EXP_DIR}/exp-2001_therapy_profiles.json', 'w') as f:
    json.dump(output, f, indent=2, default=str)
print(f"\nSaved results to {EXP_DIR}/exp-2001_therapy_profiles.json")
