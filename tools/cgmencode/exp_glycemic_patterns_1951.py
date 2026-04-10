#!/usr/bin/env python3
"""EXP-1951–1958: Glycemic Pattern Analysis & Actionable Insights.

With the corrected model production-ready (+63.9%), this batch shifts focus
to identifying WHICH glucose patterns drive poor outcomes, and generating
actionable insights for algorithm improvement.

Experiments:
  EXP-1951: Post-meal excursion profiling — which meals go worst?
  EXP-1952: Time-in-range decomposition — what hours drive TIR loss?
  EXP-1953: Hypo risk prediction — which patients/times are at risk?
  EXP-1954: Overnight glucose quality — dawn phenomenon vs basal errors
  EXP-1955: Meal response variability — reproducibility of glucose response
  EXP-1956: Model residual patterns — what does the model miss?
  EXP-1957: Best-day vs worst-day comparison — what separates good control?
  EXP-1958: Actionable summary — top 3 recommendations per patient
"""

import argparse
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from cgmencode.exp_metabolic_441 import load_patients, compute_supply_demand

warnings.filterwarnings('ignore')

FIGURES_DIR = Path('docs/60-research/figures')
RESULTS_PATH = Path('externals/experiments/exp-1951_glycemic_patterns.json')
STEPS_PER_HOUR = 12
STEPS_PER_DAY = 288

def get_isf(p):
    s = p['df'].attrs.get('isf_schedule', None)
    if s and isinstance(s, list) and len(s) > 0:
        v = s[0].get('value', s[0].get('sensitivity', 50))
        return v * 18.0182 if v < 15 else v
    return 50

def get_cr(p):
    s = p['df'].attrs.get('cr_schedule', None)
    if s and isinstance(s, list) and len(s) > 0:
        return s[0].get('value', s[0].get('ratio', 10))
    return 10

def get_basal(p):
    s = p['df'].attrs.get('basal_schedule', None)
    if s and isinstance(s, list) and len(s) > 0:
        return s[0].get('value', s[0].get('rate', 1.0))
    return 1.0

def find_meals(df, min_carbs=5, post_window=36, pre_window=6):
    carbs = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(df))
    bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(len(df))
    meals, i = [], 0
    while i < len(df) - post_window:
        c = carbs[i] if np.isfinite(carbs[i]) else 0
        if c >= min_carbs:
            mb = sum(bolus[j] for j in range(max(0,i-pre_window), min(len(df),i+post_window//3))
                     if np.isfinite(bolus[j]) and bolus[j] > 0.1)
            meals.append({'idx': i, 'end': min(i+post_window, len(df)), 'carbs': c, 'bolus': mb})
            i += post_window
        else:
            i += 1
    return meals


# =====================================================================
# EXP-1951: Post-Meal Excursion Profiling
# =====================================================================

def exp_1951(patients, save_fig=False):
    """Profile meal excursions: spike height, time to peak, time to return."""
    print("\n" + "=" * 70)
    print("EXP-1951: Post-Meal Excursion Profiling")
    print("=" * 70)

    all_results = []
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        meals = find_meals(df, min_carbs=5)
        if len(meals) < 3: continue

        spikes, return_times, out_of_range = [], [], []
        for m in meals:
            idx, end = m['idx'], m['end']
            g0 = glucose[idx] if np.isfinite(glucose[idx]) else np.nan
            if not np.isfinite(g0): continue
            post_g = glucose[idx:end]
            valid = np.isfinite(post_g)
            if valid.sum() < 6: continue

            vg = post_g[valid]
            spike = float(np.max(vg) - g0)
            spikes.append(spike)
            peak_idx = int(np.argmax(vg))
            peak_time = peak_idx * 5  # approximate (gaps make this inexact)

            # Time above 180 in window
            oor = float(np.sum(vg > 180)) / len(vg) * 100
            out_of_range.append(oor)

            # Return to within 20 of baseline
            returned = np.where(np.abs(vg[peak_idx:] - g0) < 20)[0]
            if len(returned) > 0:
                return_times.append((peak_idx + returned[0]) * 5)
            else:
                return_times.append(180)

        result = {
            'patient': name, 'n_meals': len(spikes),
            'mean_spike': float(np.mean(spikes)),
            'median_spike': float(np.median(spikes)),
            'p90_spike': float(np.percentile(spikes, 90)),
            'mean_return': float(np.mean(return_times)),
            'mean_oor_pct': float(np.mean(out_of_range)),
            'big_spikes_pct': float(np.mean([s > 60 for s in spikes])) * 100,
        }
        all_results.append(result)
        print(f"  {name}: spike={result['mean_spike']:.0f}mg/dL (p90={result['p90_spike']:.0f}) "
              f"return={result['mean_return']:.0f}min oor={result['mean_oor_pct']:.0f}%")

    if all_results:
        pop_spike = np.mean([r['mean_spike'] for r in all_results])
        pop_big = np.mean([r['big_spikes_pct'] for r in all_results])
        verdict = f"SPIKE_{pop_spike:.0f}mg_BIG_{pop_big:.0f}%"
    else:
        verdict = "INSUFFICIENT_DATA"

    if save_fig and all_results:
        try:
            import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
            fig, axes = plt.subplots(1, 3, figsize=(15, 5))
            names = [r['patient'] for r in all_results]; x = np.arange(len(names))
            axes[0].bar(x, [r['mean_spike'] for r in all_results], color='coral', alpha=0.8)
            axes[0].bar(x, [r['p90_spike'] for r in all_results], color='coral', alpha=0.3, label='P90')
            axes[0].axhline(60, color='red', ls='--', alpha=0.5, label='60mg threshold')
            axes[0].set_xticks(x); axes[0].set_xticklabels(names)
            axes[0].set_ylabel('Spike (mg/dL)'); axes[0].set_title('Post-Meal Spikes'); axes[0].legend()

            axes[1].bar(x, [r['mean_return'] for r in all_results], color='steelblue')
            axes[1].set_xticks(x); axes[1].set_xticklabels(names)
            axes[1].set_ylabel('Minutes'); axes[1].set_title('Time to Return to Baseline')

            axes[2].bar(x, [r['mean_oor_pct'] for r in all_results], color='orange')
            axes[2].set_xticks(x); axes[2].set_xticklabels(names)
            axes[2].set_ylabel('% of window'); axes[2].set_title('Out-of-Range Time After Meals')

            plt.tight_layout()
            fig.savefig(FIGURES_DIR / 'pattern-fig01-meal-excursions.png', dpi=150)
            plt.close(fig)
            print(f"  → Saved pattern-fig01-meal-excursions.png")
        except Exception as e:
            print(f"  (figure skipped: {e})")

    print(f"\n  ✓ EXP-1951 verdict: {verdict}")
    return {'experiment': 'EXP-1951', 'verdict': verdict, 'per_patient': all_results}


# =====================================================================
# EXP-1952: Time-in-Range Decomposition by Hour
# =====================================================================

def exp_1952(patients, save_fig=False):
    """Decompose TIR by hour of day to find problematic time periods."""
    print("\n" + "=" * 70)
    print("EXP-1952: TIR Decomposition by Hour")
    print("=" * 70)

    all_results = []
    pop_tir_by_hour = np.zeros(24)
    pop_count = np.zeros(24)

    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values

        tir_by_hour = np.full(24, np.nan)
        tbr_by_hour = np.full(24, np.nan)
        tar_by_hour = np.full(24, np.nan)

        for hour in range(24):
            # Collect glucose readings for this hour across all days
            hour_readings = []
            for day in range(len(glucose) // STEPS_PER_DAY):
                start = day * STEPS_PER_DAY + hour * STEPS_PER_HOUR
                end = start + STEPS_PER_HOUR
                if end > len(glucose): break
                g = glucose[start:end]
                valid = g[np.isfinite(g)]
                hour_readings.extend(valid)

            if len(hour_readings) < 50: continue
            arr = np.array(hour_readings)
            tir_by_hour[hour] = float(np.mean((arr >= 70) & (arr <= 180))) * 100
            tbr_by_hour[hour] = float(np.mean(arr < 70)) * 100
            tar_by_hour[hour] = float(np.mean(arr > 180)) * 100

            pop_tir_by_hour[hour] += tir_by_hour[hour]
            pop_count[hour] += 1

        worst_hour = int(np.nanargmin(tir_by_hour)) if np.any(np.isfinite(tir_by_hour)) else 0
        best_hour = int(np.nanargmax(tir_by_hour)) if np.any(np.isfinite(tir_by_hour)) else 0

        result = {
            'patient': name,
            'worst_hour': worst_hour, 'worst_tir': float(tir_by_hour[worst_hour]) if np.isfinite(tir_by_hour[worst_hour]) else 0,
            'best_hour': best_hour, 'best_tir': float(tir_by_hour[best_hour]) if np.isfinite(tir_by_hour[best_hour]) else 0,
            'range': float(np.nanmax(tir_by_hour) - np.nanmin(tir_by_hour)) if np.any(np.isfinite(tir_by_hour)) else 0,
            'tir_by_hour': tir_by_hour.tolist(),
        }
        all_results.append(result)
        print(f"  {name}: worst={worst_hour}:00 ({result['worst_tir']:.0f}%) "
              f"best={best_hour}:00 ({result['best_tir']:.0f}%) range={result['range']:.0f}pp")

    # Population average
    pop_avg = np.where(pop_count > 0, pop_tir_by_hour / pop_count, np.nan)
    worst_pop = int(np.nanargmin(pop_avg))
    best_pop = int(np.nanargmax(pop_avg))
    pop_range = float(np.nanmax(pop_avg) - np.nanmin(pop_avg))
    print(f"\n  Population: worst={worst_pop}:00 best={best_pop}:00 range={pop_range:.0f}pp")
    verdict = f"WORST_{worst_pop}:00_BEST_{best_pop}:00_RANGE_{pop_range:.0f}pp"

    if save_fig and all_results:
        try:
            import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
            fig, axes = plt.subplots(1, 2, figsize=(14, 5))

            # Population average
            hours = np.arange(24)
            axes[0].bar(hours, pop_avg, color='steelblue', alpha=0.8)
            axes[0].axhline(70, color='green', ls='--', alpha=0.5, label='70% target')
            axes[0].set_xticks(hours[::2]); axes[0].set_xlabel('Hour'); axes[0].set_ylabel('TIR (%)')
            axes[0].set_title('Population TIR by Hour'); axes[0].legend()

            # Per-patient heatmap
            tir_matrix = np.array([r['tir_by_hour'] for r in all_results])
            im = axes[1].imshow(tir_matrix, aspect='auto', cmap='RdYlGn', vmin=30, vmax=100)
            axes[1].set_yticks(range(len(all_results)))
            axes[1].set_yticklabels([r['patient'] for r in all_results])
            axes[1].set_xticks(hours[::2]); axes[1].set_xlabel('Hour')
            axes[1].set_title('TIR by Hour (per patient)')
            plt.colorbar(im, ax=axes[1], label='TIR %')

            plt.tight_layout()
            fig.savefig(FIGURES_DIR / 'pattern-fig02-tir-by-hour.png', dpi=150)
            plt.close(fig)
            print(f"  → Saved pattern-fig02-tir-by-hour.png")
        except Exception as e:
            print(f"  (figure skipped: {e})")

    print(f"\n  ✓ EXP-1952 verdict: {verdict}")
    return {'experiment': 'EXP-1952', 'verdict': verdict, 'pop_tir_by_hour': pop_avg.tolist(),
            'per_patient': [{k: v for k, v in r.items() if k != 'tir_by_hour'} for r in all_results]}


# =====================================================================
# EXP-1953: Hypo Risk Prediction
# =====================================================================

def exp_1953(patients, save_fig=False):
    """Analyze hypoglycemia patterns: timing, preceding context, risk factors."""
    print("\n" + "=" * 70)
    print("EXP-1953: Hypoglycemia Risk Analysis")
    print("=" * 70)

    all_results = []
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(len(df))
        iob = df['iob'].values if 'iob' in df.columns else np.zeros(len(df))

        # Find hypo events (glucose < 70 for at least 3 readings)
        hypo_events = []
        i = 0
        while i < len(glucose) - 3:
            if np.isfinite(glucose[i]) and glucose[i] < 70:
                # Find extent
                end = i + 1
                while end < len(glucose) and np.isfinite(glucose[end]) and glucose[end] < 70:
                    end += 1
                duration = (end - i) * 5  # minutes
                if duration >= 15:  # At least 15 min
                    nadir = float(np.nanmin(glucose[i:end]))
                    hour = (i % STEPS_PER_DAY) // STEPS_PER_HOUR

                    # Context: IOB before hypo
                    pre_iob = iob[max(0, i-6):i]
                    pre_iob_val = float(np.nanmean(pre_iob)) if np.any(np.isfinite(pre_iob)) else 0

                    # Recent bolus
                    recent_bolus = bolus[max(0, i-24):i]
                    had_recent_bolus = bool(np.nansum(recent_bolus[np.isfinite(recent_bolus)]) > 0.5)

                    # Preceding glucose rate
                    if i >= 6:
                        pre_g = glucose[i-6:i]
                        valid_pre = pre_g[np.isfinite(pre_g)]
                        if len(valid_pre) >= 2:
                            fall_rate = float((valid_pre[-1] - valid_pre[0]) / len(valid_pre))
                        else:
                            fall_rate = 0
                    else:
                        fall_rate = 0

                    hypo_events.append({
                        'hour': hour, 'duration': duration, 'nadir': nadir,
                        'pre_iob': pre_iob_val, 'had_bolus': had_recent_bolus,
                        'fall_rate': fall_rate,
                    })
                i = end
            else:
                i += 1

        valid_g = glucose[np.isfinite(glucose)]
        days = len(valid_g) / STEPS_PER_DAY

        result = {
            'patient': name,
            'n_hypos': len(hypo_events),
            'hypos_per_week': len(hypo_events) / max(days, 1) * 7,
            'tbr': float(np.mean(valid_g < 70)) * 100 if len(valid_g) > 0 else 0,
        }

        if hypo_events:
            result['mean_duration'] = float(np.mean([h['duration'] for h in hypo_events]))
            result['mean_nadir'] = float(np.mean([h['nadir'] for h in hypo_events]))
            hours = [h['hour'] for h in hypo_events]
            # Most common hour
            hour_counts = np.bincount(hours, minlength=24)
            result['peak_hour'] = int(np.argmax(hour_counts))
            result['pct_post_bolus'] = float(np.mean([h['had_bolus'] for h in hypo_events])) * 100
            result['mean_fall_rate'] = float(np.mean([h['fall_rate'] for h in hypo_events]))
            result['overnight_pct'] = float(np.mean([0 <= h['hour'] < 6 for h in hypo_events])) * 100

        all_results.append(result)
        print(f"  {name}: {len(hypo_events)} hypos ({result['hypos_per_week']:.1f}/wk) TBR={result['tbr']:.1f}% "
              f"peak_hour={result.get('peak_hour', '?')} post-bolus={result.get('pct_post_bolus', 0):.0f}%")

    if all_results:
        pop_rate = np.mean([r['hypos_per_week'] for r in all_results])
        pop_tbr = np.mean([r['tbr'] for r in all_results])
        verdict = f"HYPO_{pop_rate:.1f}/wk_TBR_{pop_tbr:.1f}%"
    else:
        verdict = "INSUFFICIENT_DATA"

    if save_fig and all_results:
        try:
            import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
            fig, axes = plt.subplots(1, 3, figsize=(15, 5))
            names = [r['patient'] for r in all_results]; x = np.arange(len(names))

            axes[0].bar(x, [r['hypos_per_week'] for r in all_results], color='red', alpha=0.8)
            axes[0].set_xticks(x); axes[0].set_xticklabels(names)
            axes[0].set_ylabel('Events/week'); axes[0].set_title('Hypoglycemia Frequency')

            axes[1].bar(x, [r['tbr'] for r in all_results], color='darkred', alpha=0.8)
            axes[1].axhline(4, color='orange', ls='--', label='4% target')
            axes[1].set_xticks(x); axes[1].set_xticklabels(names)
            axes[1].set_ylabel('TBR (%)'); axes[1].set_title('Time Below Range'); axes[1].legend()

            pb = [r.get('pct_post_bolus', 0) for r in all_results]
            on = [r.get('overnight_pct', 0) for r in all_results]
            axes[2].bar(x - 0.15, pb, 0.3, label='Post-bolus', color='coral')
            axes[2].bar(x + 0.15, on, 0.3, label='Overnight', color='navy')
            axes[2].set_xticks(x); axes[2].set_xticklabels(names)
            axes[2].set_ylabel('% of hypos'); axes[2].set_title('Hypo Context'); axes[2].legend()

            plt.tight_layout()
            fig.savefig(FIGURES_DIR / 'pattern-fig03-hypo-risk.png', dpi=150)
            plt.close(fig)
            print(f"  → Saved pattern-fig03-hypo-risk.png")
        except Exception as e:
            print(f"  (figure skipped: {e})")

    print(f"\n  ✓ EXP-1953 verdict: {verdict}")
    return {'experiment': 'EXP-1953', 'verdict': verdict, 'per_patient': all_results}


# =====================================================================
# EXP-1954: Overnight Glucose Quality
# =====================================================================

def exp_1954(patients, save_fig=False):
    """Analyze overnight glucose: dawn phenomenon, loop behavior, quality."""
    print("\n" + "=" * 70)
    print("EXP-1954: Overnight Glucose Quality")
    print("=" * 70)

    all_results = []
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        temp_rate = df['temp_rate'].values if 'temp_rate' in df.columns else np.zeros(len(df))

        n_days = len(glucose) // STEPS_PER_DAY
        overnight_tirs = []
        dawn_rises = []
        early_night_tirs = []

        for day in range(n_days):
            # Early night: 10pm-2am
            en_start = day * STEPS_PER_DAY + 22 * STEPS_PER_HOUR
            en_end = en_start + 4 * STEPS_PER_HOUR
            if en_end > len(glucose): continue

            # Dawn: 4am-7am
            dawn_start = day * STEPS_PER_DAY + 4 * STEPS_PER_HOUR if day < n_days - 1 else en_end
            # For simplicity, use same-day 4-7am
            ds = (day + 1) * STEPS_PER_DAY + 4 * STEPS_PER_HOUR if day < n_days - 1 else 0
            de = ds + 3 * STEPS_PER_HOUR
            if de > len(glucose): continue

            # Full overnight: midnight-6am
            midnight = (day + 1) * STEPS_PER_DAY if day < n_days - 1 else 0
            six_am = midnight + 6 * STEPS_PER_HOUR
            if six_am > len(glucose): continue

            g_night = glucose[midnight:six_am]
            valid = np.isfinite(g_night)
            if valid.sum() < 36:
                continue

            vg = g_night[valid]
            tir = float(np.mean((vg >= 70) & (vg <= 180))) * 100
            overnight_tirs.append(tir)

            # Dawn phenomenon: glucose rise from 4am to 7am
            g_dawn = glucose[ds:de]
            valid_d = np.isfinite(g_dawn)
            if valid_d.sum() >= 18:
                vd = g_dawn[valid_d]
                dawn_rise = float(vd[-1] - vd[0])
                dawn_rises.append(dawn_rise)

        result = {
            'patient': name, 'n_nights': len(overnight_tirs),
            'mean_overnight_tir': float(np.mean(overnight_tirs)) if overnight_tirs else 0,
            'mean_dawn_rise': float(np.mean(dawn_rises)) if dawn_rises else 0,
            'dawn_gt_20': float(np.mean([d > 20 for d in dawn_rises])) * 100 if dawn_rises else 0,
        }
        all_results.append(result)
        print(f"  {name}: overnight_TIR={result['mean_overnight_tir']:.0f}% "
              f"dawn_rise={result['mean_dawn_rise']:+.0f}mg/dL dawn>20={result['dawn_gt_20']:.0f}%")

    if all_results:
        pop_tir = np.mean([r['mean_overnight_tir'] for r in all_results])
        pop_dawn = np.mean([r['mean_dawn_rise'] for r in all_results])
        verdict = f"OVERNIGHT_TIR_{pop_tir:.0f}%_DAWN_{pop_dawn:+.0f}"
    else:
        verdict = "INSUFFICIENT_DATA"

    if save_fig and all_results:
        try:
            import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
            fig, axes = plt.subplots(1, 2, figsize=(12, 5))
            names = [r['patient'] for r in all_results]; x = np.arange(len(names))

            axes[0].bar(x, [r['mean_overnight_tir'] for r in all_results], color='navy', alpha=0.8)
            axes[0].axhline(70, color='green', ls='--', alpha=0.5)
            axes[0].set_xticks(x); axes[0].set_xticklabels(names)
            axes[0].set_ylabel('TIR (%)'); axes[0].set_title('Overnight TIR (midnight-6am)')

            axes[1].bar(x, [r['mean_dawn_rise'] for r in all_results],
                       color=['coral' if r['mean_dawn_rise']>0 else 'green' for r in all_results])
            axes[1].axhline(0, color='gray', ls='--', lw=0.5)
            axes[1].set_xticks(x); axes[1].set_xticklabels(names)
            axes[1].set_ylabel('mg/dL'); axes[1].set_title('Dawn Phenomenon (4-7am rise)')

            plt.tight_layout()
            fig.savefig(FIGURES_DIR / 'pattern-fig04-overnight.png', dpi=150)
            plt.close(fig)
            print(f"  → Saved pattern-fig04-overnight.png")
        except Exception as e:
            print(f"  (figure skipped: {e})")

    print(f"\n  ✓ EXP-1954 verdict: {verdict}")
    return {'experiment': 'EXP-1954', 'verdict': verdict, 'per_patient': all_results}


# =====================================================================
# EXP-1955: Meal Response Variability
# =====================================================================

def exp_1955(patients, save_fig=False):
    """How reproducible is a patient's glucose response to similar meals?"""
    print("\n" + "=" * 70)
    print("EXP-1955: Meal Response Variability")
    print("=" * 70)

    all_results = []
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        meals = find_meals(df, min_carbs=10)
        if len(meals) < 10: continue

        # For similar-sized meals, compute glucose response variability
        spikes = []
        for m in meals:
            idx, end = m['idx'], m['end']
            g0 = glucose[idx] if np.isfinite(glucose[idx]) else np.nan
            if not np.isfinite(g0): continue
            post = glucose[idx:end]
            valid = np.isfinite(post)
            if valid.sum() < 6: continue
            spike = float(np.max(post[valid]) - g0)
            spikes.append({'carbs': m['carbs'], 'spike': spike})

        if len(spikes) < 10: continue

        spike_vals = [s['spike'] for s in spikes]
        spike_cv = np.std(spike_vals) / max(np.mean(spike_vals), 0.01)

        # Bin by carb size and check within-bin variability
        carb_bins = {'small': [], 'medium': [], 'large': []}
        for s in spikes:
            if s['carbs'] < 20: carb_bins['small'].append(s['spike'])
            elif s['carbs'] < 50: carb_bins['medium'].append(s['spike'])
            else: carb_bins['large'].append(s['spike'])

        within_cv = {}
        for bin_name, bin_vals in carb_bins.items():
            if len(bin_vals) >= 5:
                within_cv[bin_name] = float(np.std(bin_vals) / max(np.mean(bin_vals), 0.01))

        result = {
            'patient': name, 'n_meals': len(spikes),
            'overall_cv': float(spike_cv),
            'within_bin_cv': within_cv,
            'mean_spike': float(np.mean(spike_vals)),
            'std_spike': float(np.std(spike_vals)),
        }
        all_results.append(result)
        print(f"  {name}: spike={result['mean_spike']:.0f}±{result['std_spike']:.0f}mg/dL CV={spike_cv:.2f}")

    if all_results:
        pop_cv = np.mean([r['overall_cv'] for r in all_results])
        verdict = f"MEAL_CV_{pop_cv:.2f}"
    else:
        verdict = "INSUFFICIENT_DATA"

    if save_fig and all_results:
        try:
            import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
            fig, ax = plt.subplots(figsize=(10, 5))
            names = [r['patient'] for r in all_results]; x = np.arange(len(names))
            ax.bar(x, [r['overall_cv'] for r in all_results], color='purple', alpha=0.8)
            ax.set_xticks(x); ax.set_xticklabels(names)
            ax.set_ylabel('CV of spike'); ax.set_title('Meal Response Variability')
            plt.tight_layout()
            fig.savefig(FIGURES_DIR / 'pattern-fig05-meal-variability.png', dpi=150)
            plt.close(fig)
            print(f"  → Saved pattern-fig05-meal-variability.png")
        except Exception as e:
            print(f"  (figure skipped: {e})")

    print(f"\n  ✓ EXP-1955 verdict: {verdict}")
    return {'experiment': 'EXP-1955', 'verdict': verdict, 'per_patient': all_results}


# =====================================================================
# EXP-1956: Model Residual Patterns
# =====================================================================

def exp_1956(patients, save_fig=False):
    """What patterns remain in the corrected model's residuals?"""
    print("\n" + "=" * 70)
    print("EXP-1956: Model Residual Pattern Analysis")
    print("=" * 70)

    all_results = []
    pop_resid_by_hour = np.zeros(24)
    pop_count = np.zeros(24)

    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        sd = compute_supply_demand(df)
        supply = sd.get('supply', np.zeros_like(glucose))
        demand = sd.get('demand', np.zeros_like(glucose))
        dg = np.diff(glucose, prepend=glucose[0])

        # Use supply scale 0.3 (universal finding)
        net = supply * 0.3 - demand * 0.3
        resid = dg - net

        # Residual by hour
        resid_by_hour = np.full(24, np.nan)
        for hour in range(24):
            hour_resids = []
            for day in range(len(glucose) // STEPS_PER_DAY):
                start = day * STEPS_PER_DAY + hour * STEPS_PER_HOUR
                end = start + STEPS_PER_HOUR
                if end > len(glucose): break
                r = resid[start:end]
                valid = r[np.isfinite(r)]
                hour_resids.extend(valid)
            if len(hour_resids) > 50:
                resid_by_hour[hour] = float(np.mean(hour_resids))
                pop_resid_by_hour[hour] += resid_by_hour[hour]
                pop_count[hour] += 1

        # Autocorrelation of residuals
        valid_resid = resid[np.isfinite(resid)]
        if len(valid_resid) > 100:
            acf_1 = float(np.corrcoef(valid_resid[:-1], valid_resid[1:])[0, 1])
            acf_12 = float(np.corrcoef(valid_resid[:-12], valid_resid[12:])[0, 1]) if len(valid_resid) > 24 else 0
        else:
            acf_1 = acf_12 = 0

        result = {
            'patient': name,
            'mean_resid': float(np.nanmean(resid)),
            'std_resid': float(np.nanstd(resid)),
            'acf_1': acf_1,
            'acf_12': acf_12,
            'max_hour_bias': float(np.nanmax(np.abs(resid_by_hour))) if np.any(np.isfinite(resid_by_hour)) else 0,
        }
        all_results.append(result)
        print(f"  {name}: mean_resid={result['mean_resid']:.2f} std={result['std_resid']:.1f} "
              f"ACF(1)={acf_1:.3f} ACF(1h)={acf_12:.3f}")

    pop_avg = np.where(pop_count > 0, pop_resid_by_hour / pop_count, np.nan)
    pop_acf = np.mean([r['acf_1'] for r in all_results])
    verdict = f"ACF1_{pop_acf:.3f}_MAX_HOUR_BIAS_{np.nanmax(np.abs(pop_avg)):.2f}"

    if save_fig and all_results:
        try:
            import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
            fig, axes = plt.subplots(1, 2, figsize=(12, 5))

            axes[0].bar(range(24), pop_avg, color='steelblue', alpha=0.8)
            axes[0].axhline(0, color='gray', ls='--', lw=0.5)
            axes[0].set_xlabel('Hour'); axes[0].set_ylabel('Mean residual (mg/dL/5min)')
            axes[0].set_title('Population Model Residual by Hour')

            names = [r['patient'] for r in all_results]; x = np.arange(len(names))
            axes[1].bar(x - 0.15, [r['acf_1'] for r in all_results], 0.3, label='ACF(1 step)', color='steelblue')
            axes[1].bar(x + 0.15, [r['acf_12'] for r in all_results], 0.3, label='ACF(1 hour)', color='coral')
            axes[1].set_xticks(x); axes[1].set_xticklabels(names)
            axes[1].set_ylabel('Autocorrelation'); axes[1].set_title('Residual Autocorrelation'); axes[1].legend()

            plt.tight_layout()
            fig.savefig(FIGURES_DIR / 'pattern-fig06-residuals.png', dpi=150)
            plt.close(fig)
            print(f"  → Saved pattern-fig06-residuals.png")
        except Exception as e:
            print(f"  (figure skipped: {e})")

    print(f"\n  ✓ EXP-1956 verdict: {verdict}")
    return {'experiment': 'EXP-1956', 'verdict': verdict, 'per_patient': all_results}


# =====================================================================
# EXP-1957: Best Day vs Worst Day
# =====================================================================

def exp_1957(patients, save_fig=False):
    """Compare best vs worst TIR days to find what differentiates them."""
    print("\n" + "=" * 70)
    print("EXP-1957: Best Day vs Worst Day Analysis")
    print("=" * 70)

    all_results = []
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        carbs_col = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(df))
        bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(len(df))

        n_days = len(glucose) // STEPS_PER_DAY
        day_stats = []

        for day in range(n_days):
            start = day * STEPS_PER_DAY
            end = start + STEPS_PER_DAY
            g = glucose[start:end]
            valid = np.isfinite(g)
            if valid.sum() < STEPS_PER_DAY * 0.5: continue

            vg = g[valid]
            tir = float(np.mean((vg >= 70) & (vg <= 180))) * 100
            c = carbs_col[start:end]
            b = bolus[start:end]
            total_carbs = float(np.nansum(c[np.isfinite(c)]))
            total_bolus = float(np.nansum(b[np.isfinite(b)]))
            n_meals = int(np.sum(c[np.isfinite(c)] >= 5))
            mean_g = float(np.mean(vg))
            cv = float(np.std(vg) / mean_g) * 100

            day_stats.append({
                'day': day, 'tir': tir, 'carbs': total_carbs,
                'bolus': total_bolus, 'n_meals': n_meals,
                'mean_g': mean_g, 'cv': cv,
            })

        if len(day_stats) < 20: continue

        # Sort by TIR
        sorted_days = sorted(day_stats, key=lambda d: d['tir'])
        worst_10 = sorted_days[:len(sorted_days)//10 + 1]
        best_10 = sorted_days[-(len(sorted_days)//10 + 1):]

        result = {
            'patient': name, 'n_days': len(day_stats),
            'best_tir': float(np.mean([d['tir'] for d in best_10])),
            'worst_tir': float(np.mean([d['tir'] for d in worst_10])),
            'best_carbs': float(np.mean([d['carbs'] for d in best_10])),
            'worst_carbs': float(np.mean([d['carbs'] for d in worst_10])),
            'best_meals': float(np.mean([d['n_meals'] for d in best_10])),
            'worst_meals': float(np.mean([d['n_meals'] for d in worst_10])),
            'best_cv': float(np.mean([d['cv'] for d in best_10])),
            'worst_cv': float(np.mean([d['cv'] for d in worst_10])),
        }
        all_results.append(result)
        print(f"  {name}: best_TIR={result['best_tir']:.0f}% worst_TIR={result['worst_tir']:.0f}% "
              f"Δcarbs={result['worst_carbs']-result['best_carbs']:+.0f}g "
              f"Δmeals={result['worst_meals']-result['best_meals']:+.1f}")

    if all_results:
        pop_gap = np.mean([r['best_tir'] - r['worst_tir'] for r in all_results])
        verdict = f"BEST_WORST_GAP_{pop_gap:.0f}pp"
    else:
        verdict = "INSUFFICIENT_DATA"

    if save_fig and all_results:
        try:
            import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
            fig, axes = plt.subplots(1, 2, figsize=(12, 5))
            names = [r['patient'] for r in all_results]; x = np.arange(len(names))

            axes[0].bar(x - 0.15, [r['best_tir'] for r in all_results], 0.3, label='Best 10%', color='green')
            axes[0].bar(x + 0.15, [r['worst_tir'] for r in all_results], 0.3, label='Worst 10%', color='red')
            axes[0].set_xticks(x); axes[0].set_xticklabels(names)
            axes[0].set_ylabel('TIR (%)'); axes[0].set_title('Best vs Worst Days'); axes[0].legend()

            d_carbs = [r['worst_carbs'] - r['best_carbs'] for r in all_results]
            axes[1].bar(x, d_carbs, color=['coral' if d > 0 else 'green' for d in d_carbs])
            axes[1].axhline(0, color='gray', ls='--', lw=0.5)
            axes[1].set_xticks(x); axes[1].set_xticklabels(names)
            axes[1].set_ylabel('Carb difference (g)'); axes[1].set_title('Worst Day Excess Carbs')

            plt.tight_layout()
            fig.savefig(FIGURES_DIR / 'pattern-fig07-best-worst.png', dpi=150)
            plt.close(fig)
            print(f"  → Saved pattern-fig07-best-worst.png")
        except Exception as e:
            print(f"  (figure skipped: {e})")

    print(f"\n  ✓ EXP-1957 verdict: {verdict}")
    return {'experiment': 'EXP-1957', 'verdict': verdict, 'per_patient': all_results}


# =====================================================================
# EXP-1958: Actionable Summary
# =====================================================================

def exp_1958(patients, save_fig=False):
    """Generate top 3 actionable recommendations per patient."""
    print("\n" + "=" * 70)
    print("EXP-1958: Actionable Summary — Top 3 Recommendations")
    print("=" * 70)

    all_results = []
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        carbs_col = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(df))
        bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(len(df))

        valid_g = glucose[np.isfinite(glucose)]
        if len(valid_g) < 1000: continue

        isf_p = get_isf(p); cr_p = get_cr(p); basal_p = get_basal(p)
        tir = float(np.mean((valid_g >= 70) & (valid_g <= 180))) * 100
        tbr = float(np.mean(valid_g < 70)) * 100
        tar = float(np.mean(valid_g > 180)) * 100
        cv = float(np.std(valid_g) / np.mean(valid_g)) * 100

        # Meal analysis
        meals = find_meals(df, min_carbs=10)
        meal_deltas = []
        for m in meals:
            if m['bolus'] < 0.5: continue
            idx = m['idx']
            end = min(idx + 2*STEPS_PER_HOUR, len(glucose))
            g0 = glucose[idx]; g1 = glucose[end-1]
            if np.isfinite(g0) and np.isfinite(g1):
                meal_deltas.append(g1 - g0)

        mean_delta = float(np.mean(meal_deltas)) if meal_deltas else 0

        # Overnight analysis
        overnight_drifts = []
        for day in range(len(glucose) // STEPS_PER_DAY):
            midnight = day * STEPS_PER_DAY
            six_am = midnight + 6 * STEPS_PER_HOUR
            if six_am > len(glucose): continue
            g_night = glucose[midnight:six_am]
            valid = np.isfinite(g_night)
            if valid.sum() < 3 * STEPS_PER_HOUR: continue
            vg = g_night[valid]
            drift = (vg[-1] - vg[0]) / (valid.sum() / STEPS_PER_HOUR)
            overnight_drifts.append(drift)
        mean_drift = float(np.mean(overnight_drifts)) if overnight_drifts else 0

        # Generate recommendations
        recs = []
        # CR assessment
        if mean_delta > 30:
            recs.append(f"LOWER CR from {cr_p:.0f} (post-meal Δ={mean_delta:+.0f}mg/dL → meals under-bolused)")
        elif mean_delta < -30:
            recs.append(f"RAISE CR from {cr_p:.0f} (post-meal Δ={mean_delta:+.0f}mg/dL → meals over-bolused)")

        # Basal assessment
        if mean_drift > 5:
            recs.append(f"RAISE basal from {basal_p:.2f} (overnight drift={mean_drift:+.1f}mg/dL/h)")
        elif mean_drift < -5:
            recs.append(f"LOWER basal from {basal_p:.2f} (overnight drift={mean_drift:+.1f}mg/dL/h)")

        # TBR
        if tbr > 4:
            recs.append(f"REDUCE hypo risk (TBR={tbr:.1f}% > 4% target)")

        # TAR
        if tar > 25:
            recs.append(f"ADDRESS hyperglycemia (TAR={tar:.0f}%)")

        # CV
        if cv > 36:
            recs.append(f"REDUCE variability (CV={cv:.0f}% > 36% target)")

        # No changes needed
        if not recs:
            recs.append("Settings appear well-calibrated. Continue monitoring.")

        result = {
            'patient': name, 'tir': tir, 'tbr': tbr, 'tar': tar, 'cv': cv,
            'mean_meal_delta': mean_delta, 'mean_overnight_drift': mean_drift,
            'recommendations': recs[:3],  # Top 3
        }
        all_results.append(result)
        print(f"\n  {name} (TIR={tir:.0f}%):")
        for i, rec in enumerate(recs[:3], 1):
            print(f"    {i}. {rec}")

    verdict = f"GENERATED_{len(all_results)}_PATIENTS"

    if save_fig and all_results:
        try:
            import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
            fig, ax = plt.subplots(figsize=(14, 8))

            # Summary table as figure
            cell_text = []
            for r in all_results:
                row = [r['patient'], f"{r['tir']:.0f}%", f"{r['tbr']:.1f}%",
                       f"{r['mean_meal_delta']:+.0f}", f"{r['mean_overnight_drift']:+.1f}",
                       '; '.join(r['recommendations'][:2])]
                cell_text.append(row)

            table = ax.table(cellText=cell_text,
                           colLabels=['Patient', 'TIR', 'TBR', 'Meal Δ', 'Night drift', 'Top Recommendations'],
                           loc='center', cellLoc='left')
            table.auto_set_font_size(False)
            table.set_fontsize(8)
            table.scale(1, 1.8)
            ax.axis('off')
            ax.set_title('Actionable Therapy Recommendations', fontsize=14, pad=20)

            plt.tight_layout()
            fig.savefig(FIGURES_DIR / 'pattern-fig08-recommendations.png', dpi=150)
            plt.close(fig)
            print(f"\n  → Saved pattern-fig08-recommendations.png")
        except Exception as e:
            print(f"  (figure skipped: {e})")

    print(f"\n  ✓ EXP-1958 verdict: {verdict}")
    return {'experiment': 'EXP-1958', 'verdict': verdict, 'per_patient': all_results}


# =====================================================================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--figures', action='store_true')
    args = parser.parse_args()

    patients = load_patients('externals/ns-data/patients/')
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 70)
    print("EXP-1951–1958: Glycemic Pattern Analysis")
    print("=" * 70)

    results = {}
    for exp_id, fn in [('EXP-1951', exp_1951), ('EXP-1952', exp_1952), ('EXP-1953', exp_1953),
                        ('EXP-1954', exp_1954), ('EXP-1955', exp_1955), ('EXP-1956', exp_1956),
                        ('EXP-1957', exp_1957), ('EXP-1958', exp_1958)]:
        print(f"\n{'#' * 70}")
        print(f"# Running {exp_id}")
        print(f"{'#' * 70}")
        try:
            results[exp_id] = fn(patients, save_fig=args.figures)
        except Exception as e:
            print(f"\n  ✗ {exp_id} FAILED: {e}")
            import traceback; traceback.print_exc()
            results[exp_id] = {'experiment': exp_id, 'verdict': f'FAILED: {e}'}

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    def json_safe(obj):
        if isinstance(obj, (np.integer,)): return int(obj)
        if isinstance(obj, (np.floating,)): return float(obj) if np.isfinite(obj) else None
        if isinstance(obj, np.ndarray): return obj.tolist()
        if isinstance(obj, np.bool_): return bool(obj)
        raise TypeError(f"Not JSON serializable: {type(obj)}")

    with open(RESULTS_PATH, 'w') as f:
        json.dump(results, f, indent=2, default=json_safe)

    print("\n" + "=" * 70)
    print("SYNTHESIS: Glycemic Pattern Analysis")
    print("=" * 70)
    for k, v in results.items():
        print(f"  {k}: {v.get('verdict', 'N/A')}")

if __name__ == '__main__':
    main()
