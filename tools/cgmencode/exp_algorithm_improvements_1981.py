#!/usr/bin/env python3
"""
EXP-1981–1988: Actionable Algorithm Improvements

Building on the AID Compensation Paradox (EXP-1971–1978), these experiments
identify specific algorithm changes that COULD improve outcomes — targeting
the gaps that static settings optimization cannot address.

Key hypotheses:
- Time-of-day settings mismatch accounts for morning TIR loss
- Pre-bolus timing is a major lever for meal spike reduction
- Dawn phenomenon requires proactive basal ramp, not reactive correction
- Hypo events have detectable precursors in loop state data
- A formal "Loop Effort Score" can serve as clinical decision support

Depends on: exp_metabolic_441.py (load_patients, compute_supply_demand)
            exp_glycemic_patterns_1951.py (findings)
            exp_aid_behavior_1961.py (findings)
            exp_settings_optimization_1971.py (findings)

Usage: PYTHONPATH=tools python3 tools/cgmencode/exp_algorithm_improvements_1981.py --figures
"""

import sys
import os
import json
import argparse
import numpy as np
import warnings
warnings.filterwarnings('ignore')

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

from cgmencode.exp_metabolic_441 import load_patients, compute_supply_demand

STEPS_PER_HOUR = 12
STEPS_PER_DAY = 288
FIGURES_DIR = 'docs/60-research/figures'
RESULTS_FILE = 'externals/experiments/exp-1981_algorithm_improvements.json'


def find_meals(df, min_carbs=5):
    """Find meal events (carbs > min_carbs)."""
    carbs = df['carbs'].values
    meal_idx = np.where(carbs >= min_carbs)[0]
    return meal_idx


def find_boluses(df, min_bolus=0.1):
    """Find bolus events."""
    bolus = df['bolus'].values
    bolus_idx = np.where(bolus >= min_bolus)[0]
    return bolus_idx


def get_isf(df):
    """Get ISF from patient attrs, convert mmol/L to mg/dL if needed."""
    isf_sched = df.attrs.get('isf_schedule', [{'value': 50}])
    isf = float(isf_sched[0]['value'])
    if isf < 15:
        isf *= 18.0182
    return isf


def get_cr(df):
    """Get CR from patient attrs."""
    cr_sched = df.attrs.get('cr_schedule', [{'value': 10}])
    return float(cr_sched[0]['value'])


def get_basal(df):
    """Get scheduled basal from patient attrs."""
    basal_sched = df.attrs.get('basal_schedule', [{'value': 1.0}])
    return float(basal_sched[0]['value'])


def hour_of_day(idx, steps_per_hour=STEPS_PER_HOUR):
    """Convert step index to hour of day."""
    return (idx % STEPS_PER_DAY) / steps_per_hour


def glucose_metrics(glucose):
    """Compute standard glucose metrics."""
    valid = glucose[~np.isnan(glucose)]
    if len(valid) < 100:
        return {'tir': np.nan, 'tbr': np.nan, 'tar': np.nan, 'cv': np.nan, 'mean': np.nan}
    tir = np.mean((valid >= 70) & (valid <= 180)) * 100
    tbr = np.mean(valid < 70) * 100
    tar = np.mean(valid > 180) * 100
    cv = np.std(valid) / np.mean(valid) * 100
    return {'tir': tir, 'tbr': tbr, 'tar': tar, 'cv': cv, 'mean': np.mean(valid)}


# ============================================================================
# EXP-1981: Time-of-Day Settings Mismatch
# ============================================================================

def exp_1981_time_of_day_mismatch(patients, make_figures=False):
    """Compare scheduled basal profile shape vs actual metabolic need by hour."""
    print("\n" + "=" * 70)
    print("EXP-1981: Time-of-Day Settings Mismatch")
    print("=" * 70)

    results = []
    all_hourly_net = []

    for p in patients:
        pid = p['name']
        df = p['df']
        glucose = df['glucose'].values
        net_basal = df['net_basal'].values
        sched_basal = get_basal(df)
        isf = get_isf(df)
        n = len(glucose)

        # Compute hourly average net basal delivery
        hourly_net = np.zeros(24)
        hourly_glucose = np.zeros(24)
        hourly_tir = np.zeros(24)
        hourly_count = np.zeros(24)

        for i in range(n):
            h = int(hour_of_day(i))
            if h >= 24:
                h = 23
            if not np.isnan(net_basal[i]):
                hourly_net[h] += net_basal[i]
                hourly_count[h] += 1
            if not np.isnan(glucose[i]):
                hourly_glucose[h] += glucose[i]
                hourly_tir[h] += 1 if 70 <= glucose[i] <= 180 else 0

        mask = hourly_count > 0
        hourly_net[mask] /= hourly_count[mask]
        hourly_glucose[mask] /= hourly_count[mask]
        hourly_tir[mask] /= hourly_count[mask]
        hourly_tir *= 100

        # Compute "ideal" basal as net_basal average (what the loop actually delivers)
        # Mismatch = scheduled - actual
        mismatch = sched_basal - hourly_net  # positive = over-scheduled
        worst_hour = np.argmax(np.abs(mismatch))
        worst_mismatch = mismatch[worst_hour]

        # Correlation between mismatch and TIR
        valid_hours = mask & (hourly_tir > 0)
        if valid_hours.sum() > 5:
            corr = np.corrcoef(mismatch[valid_hours], hourly_tir[valid_hours])[0, 1]
        else:
            corr = np.nan

        print(f"  {pid}: sched={sched_basal:.2f} worst_hour={worst_hour:02d}:00 "
              f"mismatch={worst_mismatch:+.2f}U/h corr(mismatch,TIR)={corr:.2f}")

        results.append({
            'patient': pid,
            'scheduled_basal': sched_basal,
            'hourly_net_basal': hourly_net.tolist(),
            'hourly_glucose': hourly_glucose.tolist(),
            'hourly_tir': hourly_tir.tolist(),
            'mismatch': mismatch.tolist(),
            'worst_hour': int(worst_hour),
            'worst_mismatch': float(worst_mismatch),
            'mismatch_tir_corr': float(corr) if not np.isnan(corr) else None
        })
        all_hourly_net.append(hourly_net)

    # Population average
    pop_hourly_net = np.mean(all_hourly_net, axis=0)
    pop_sched = np.mean([r['scheduled_basal'] for r in results])
    morning_excess = np.mean(pop_sched - pop_hourly_net[6:10])  # 6-10AM
    overnight_excess = np.mean(pop_sched - pop_hourly_net[0:6])  # 0-6AM

    if make_figures and HAS_MPL:
        fig, axes = plt.subplots(1, 3, figsize=(18, 5))

        # Plot 1: Hourly net basal vs scheduled for each patient
        hours = np.arange(24)
        for i, p in enumerate(patients):
            axes[0].plot(hours, all_hourly_net[i], alpha=0.4, linewidth=1)
        axes[0].plot(hours, pop_hourly_net, 'k-', linewidth=2, label='Population mean')
        axes[0].axhline(pop_sched, color='red', linestyle='--', label=f'Mean scheduled ({pop_sched:.2f})')
        axes[0].set_xlabel('Hour of Day')
        axes[0].set_ylabel('Net Basal (U/h)')
        axes[0].set_title('Actual vs Scheduled Basal by Hour')
        axes[0].legend()
        axes[0].set_xticks(range(0, 24, 3))

        # Plot 2: Mismatch (scheduled - actual) by hour
        pop_mismatch = pop_sched - pop_hourly_net
        axes[1].bar(hours, pop_mismatch, color=['red' if m > 0 else 'blue' for m in pop_mismatch])
        axes[1].set_xlabel('Hour of Day')
        axes[1].set_ylabel('Mismatch (U/h)')
        axes[1].set_title('Basal Mismatch: Scheduled - Actual')
        axes[1].axhline(0, color='black', linewidth=0.5)
        axes[1].set_xticks(range(0, 24, 3))

        # Plot 3: Mismatch vs TIR scatter
        for r in results:
            axes[2].scatter(r['mismatch'], r['hourly_tir'], alpha=0.3, s=10)
        axes[2].set_xlabel('Basal Mismatch (U/h)')
        axes[2].set_ylabel('TIR (%)')
        axes[2].set_title('Mismatch vs TIR by Hour')

        plt.tight_layout()
        fig_path = os.path.join(FIGURES_DIR, 'algo-fig01-tod-mismatch.png')
        plt.savefig(fig_path, dpi=150)
        plt.close()
        print(f"  → Saved {os.path.basename(fig_path)}")

    verdict = f"MORNING_EXCESS_{morning_excess:+.2f}U/h_OVERNIGHT_{overnight_excess:+.2f}U/h"
    print(f"\n  ✓ EXP-1981 verdict: {verdict}")

    return {
        'experiment': 'EXP-1981',
        'verdict': verdict,
        'per_patient': results,
        'population_hourly_net': pop_hourly_net.tolist(),
        'morning_excess': float(morning_excess),
        'overnight_excess': float(overnight_excess)
    }


# ============================================================================
# EXP-1982: Pre-Bolus Timing Analysis
# ============================================================================

def exp_1982_prebolus_timing(patients, make_figures=False):
    """Analyze timing between bolus and meal, and its impact on post-meal glucose."""
    print("\n" + "=" * 70)
    print("EXP-1982: Pre-Bolus Timing Analysis")
    print("=" * 70)

    results = []
    all_timings = []
    all_spikes = []
    all_prebolusT = []

    for p in patients:
        pid = p['name']
        df = p['df']
        glucose = df['glucose'].values
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        n = len(glucose)

        meals = find_meals(df, min_carbs=5)
        timings = []
        spikes = []

        for meal_idx in meals:
            # Look for nearest bolus within ±1 hour
            search_start = max(0, meal_idx - STEPS_PER_HOUR)
            search_end = min(n, meal_idx + STEPS_PER_HOUR)

            bolus_near = np.where(bolus[search_start:search_end] > 0.1)[0]
            if len(bolus_near) == 0:
                continue

            # Closest bolus
            bolus_offset = bolus_near[np.argmin(np.abs(bolus_near - (meal_idx - search_start)))]
            bolus_idx = search_start + bolus_offset
            timing_min = (bolus_idx - meal_idx) * 5  # minutes, negative = pre-bolus

            # Post-meal spike: max glucose in 2 hours after meal
            post_start = meal_idx
            post_end = min(n, meal_idx + 24)  # 2 hours
            if post_end <= post_start + 3:
                continue
            pre_glucose = glucose[meal_idx] if not np.isnan(glucose[meal_idx]) else np.nan
            if np.isnan(pre_glucose):
                continue
            post_glucose = glucose[post_start:post_end]
            valid_post = post_glucose[~np.isnan(post_glucose)]
            if len(valid_post) < 3:
                continue
            spike = np.max(valid_post) - pre_glucose

            timings.append(timing_min)
            spikes.append(spike)

        timings = np.array(timings)
        spikes = np.array(spikes)

        if len(timings) > 10:
            # Pre-bolus (timing < -5min) vs reactive (timing > 5min)
            pre_mask = timings < -5
            reactive_mask = timings > 5
            simultaneous_mask = (timings >= -5) & (timings <= 5)

            pre_spike = np.median(spikes[pre_mask]) if pre_mask.sum() > 3 else np.nan
            react_spike = np.median(spikes[reactive_mask]) if reactive_mask.sum() > 3 else np.nan
            simul_spike = np.median(spikes[simultaneous_mask]) if simultaneous_mask.sum() > 3 else np.nan

            pct_prebolus = pre_mask.mean() * 100
            median_timing = np.median(timings)

            corr = np.corrcoef(timings, spikes)[0, 1] if len(timings) > 5 else np.nan
        else:
            pre_spike = react_spike = simul_spike = pct_prebolus = median_timing = corr = np.nan

        print(f"  {pid}: n={len(timings)} meals, median_timing={median_timing:+.0f}min, "
              f"pre={pre_spike:.0f}mg/dL simul={simul_spike:.0f}mg/dL react={react_spike:.0f}mg/dL "
              f"pct_pre={pct_prebolus:.0f}% corr={corr:.2f}")

        results.append({
            'patient': pid,
            'n_meals': int(len(timings)),
            'median_timing_min': float(median_timing) if not np.isnan(median_timing) else None,
            'pct_prebolus': float(pct_prebolus) if not np.isnan(pct_prebolus) else None,
            'pre_spike': float(pre_spike) if not np.isnan(pre_spike) else None,
            'simultaneous_spike': float(simul_spike) if not np.isnan(simul_spike) else None,
            'reactive_spike': float(react_spike) if not np.isnan(react_spike) else None,
            'timing_spike_corr': float(corr) if not np.isnan(corr) else None
        })
        all_timings.extend(timings.tolist())
        all_spikes.extend(spikes.tolist())
        all_prebolusT.append(pct_prebolus)

    all_timings = np.array(all_timings)
    all_spikes = np.array(all_spikes)

    # Population statistics
    pop_median_timing = np.median(all_timings)
    pop_pct_pre = np.mean(all_timings < -5) * 100
    pre_mask = all_timings < -5
    react_mask = all_timings > 5
    pop_pre_spike = np.median(all_spikes[pre_mask]) if pre_mask.sum() > 10 else np.nan
    pop_react_spike = np.median(all_spikes[react_mask]) if react_mask.sum() > 10 else np.nan
    spike_reduction = pop_react_spike - pop_pre_spike

    if make_figures and HAS_MPL:
        fig, axes = plt.subplots(1, 3, figsize=(18, 5))

        # Plot 1: Timing distribution
        axes[0].hist(all_timings, bins=np.arange(-60, 65, 5), color='steelblue', edgecolor='black')
        axes[0].axvline(0, color='red', linestyle='--', label='Meal time')
        axes[0].axvline(pop_median_timing, color='orange', linestyle='--',
                       label=f'Median ({pop_median_timing:+.0f}min)')
        axes[0].set_xlabel('Bolus Timing (min, negative=pre-bolus)')
        axes[0].set_ylabel('Count')
        axes[0].set_title('Bolus-Meal Timing Distribution')
        axes[0].legend()

        # Plot 2: Timing vs spike scatter
        axes[1].scatter(all_timings, all_spikes, alpha=0.05, s=5, c='steelblue')
        # Bin means
        bins = np.arange(-55, 60, 10)
        bin_means = []
        bin_centers = []
        for b in range(len(bins) - 1):
            mask = (all_timings >= bins[b]) & (all_timings < bins[b + 1])
            if mask.sum() > 10:
                bin_means.append(np.median(all_spikes[mask]))
                bin_centers.append((bins[b] + bins[b + 1]) / 2)
        axes[1].plot(bin_centers, bin_means, 'ro-', linewidth=2, markersize=6, label='Binned median')
        axes[1].set_xlabel('Bolus Timing (min)')
        axes[1].set_ylabel('Post-Meal Spike (mg/dL)')
        axes[1].set_title('Timing vs Post-Meal Spike')
        axes[1].legend()

        # Plot 3: Per-patient pre-bolus % vs spike reduction
        for r in results:
            if r['pre_spike'] is not None and r['reactive_spike'] is not None:
                reduction = r['reactive_spike'] - r['pre_spike']
                axes[2].scatter(r['pct_prebolus'], reduction, s=60, zorder=5)
                axes[2].annotate(r['patient'], (r['pct_prebolus'], reduction),
                               fontsize=8, ha='center', va='bottom')
        axes[2].set_xlabel('% Meals with Pre-Bolus')
        axes[2].set_ylabel('Spike Reduction (reactive - pre)')
        axes[2].set_title('Pre-Bolus Benefit by Patient')
        axes[2].axhline(0, color='black', linewidth=0.5)

        plt.tight_layout()
        fig_path = os.path.join(FIGURES_DIR, 'algo-fig02-prebolus-timing.png')
        plt.savefig(fig_path, dpi=150)
        plt.close()
        print(f"  → Saved {os.path.basename(fig_path)}")

    verdict = (f"MEDIAN_{pop_median_timing:+.0f}min_{pop_pct_pre:.0f}%PRE_"
               f"SPIKE_REDUCTION_{spike_reduction:.0f}mg/dL")
    print(f"\n  ✓ EXP-1982 verdict: {verdict}")

    return {
        'experiment': 'EXP-1982',
        'verdict': verdict,
        'per_patient': results,
        'population_median_timing': float(pop_median_timing),
        'population_pct_prebolus': float(pop_pct_pre),
        'population_pre_spike': float(pop_pre_spike) if not np.isnan(pop_pre_spike) else None,
        'population_reactive_spike': float(pop_react_spike) if not np.isnan(pop_react_spike) else None,
        'spike_reduction_mg_dl': float(spike_reduction) if not np.isnan(spike_reduction) else None
    }


# ============================================================================
# EXP-1983: Dawn Phenomenon Countermeasure Simulation
# ============================================================================

def exp_1983_dawn_countermeasure(patients, make_figures=False):
    """Simulate proactive dawn basal ramp and measure glucose impact."""
    print("\n" + "=" * 70)
    print("EXP-1983: Dawn Phenomenon Countermeasure Simulation")
    print("=" * 70)

    results = []

    for p in patients:
        pid = p['name']
        df = p['df']
        glucose = df['glucose'].values
        isf = get_isf(df)
        sched_basal = get_basal(df)
        n = len(glucose)

        # Compute dawn rise: mean glucose at 8AM vs 3AM
        hours_3am = []
        hours_8am = []
        for i in range(n):
            h = hour_of_day(i)
            if not np.isnan(glucose[i]):
                if 2.5 <= h < 3.5:
                    hours_3am.append(glucose[i])
                elif 7.5 <= h < 8.5:
                    hours_8am.append(glucose[i])

        dawn_rise = np.mean(hours_8am) - np.mean(hours_3am) if hours_3am and hours_8am else 0

        # Simulate dawn ramp: extra basal from 3-6AM
        # Try different ramp magnitudes
        ramp_results = {}
        for ramp_pct in [0, 25, 50, 75, 100]:
            sim_glucose = glucose.copy()
            ramp_u_h = sched_basal * ramp_pct / 100  # extra U/h

            for i in range(n):
                h = hour_of_day(i)
                if 3 <= h < 6:
                    # Extra insulin effect: glucose drops by ISF * (extra_U / steps_per_hour)
                    # Distribute effect over following 3 hours (36 steps)
                    extra_per_step = ramp_u_h / STEPS_PER_HOUR
                    effect_per_step = isf * extra_per_step
                    # Apply with 1-2h lag
                    lag_start = i + STEPS_PER_HOUR
                    lag_end = min(n, i + 3 * STEPS_PER_HOUR)
                    for j in range(lag_start, lag_end):
                        decay = np.exp(-(j - lag_start) / (2 * STEPS_PER_HOUR))
                        sim_glucose[j] -= effect_per_step * decay

            # Morning metrics (6-10 AM)
            morning_mask = np.array([6 <= hour_of_day(i) < 10 for i in range(n)])
            morning_glucose = sim_glucose[morning_mask]
            metrics = glucose_metrics(morning_glucose)

            ramp_results[ramp_pct] = metrics

        # Find best ramp
        best_ramp = max(ramp_results.keys(), key=lambda k: ramp_results[k]['tir'])
        best_metrics = ramp_results[best_ramp]
        current_metrics = ramp_results[0]

        delta_tir = best_metrics['tir'] - current_metrics['tir']
        delta_tbr = best_metrics['tbr'] - current_metrics['tbr']

        print(f"  {pid}: dawn_rise={dawn_rise:+.0f}mg/dL best_ramp={best_ramp}% "
              f"morning_TIR {current_metrics['tir']:.0f}→{best_metrics['tir']:.0f}% "
              f"Δ={delta_tir:+.1f}pp TBR={best_metrics['tbr']:.1f}%")

        results.append({
            'patient': pid,
            'dawn_rise_mg_dl': float(dawn_rise),
            'best_ramp_pct': int(best_ramp),
            'current_morning_tir': float(current_metrics['tir']),
            'best_morning_tir': float(best_metrics['tir']),
            'delta_tir': float(delta_tir),
            'best_tbr': float(best_metrics['tbr']),
            'ramp_results': {str(k): v for k, v in ramp_results.items()}
        })

    # Population stats
    pop_dawn = np.mean([r['dawn_rise_mg_dl'] for r in results])
    pop_delta_tir = np.mean([r['delta_tir'] for r in results])
    improved = sum(1 for r in results if r['delta_tir'] > 0.5)

    if make_figures and HAS_MPL:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        # Plot 1: Dawn rise vs morning TIR improvement
        dawn_rises = [r['dawn_rise_mg_dl'] for r in results]
        deltas = [r['delta_tir'] for r in results]
        axes[0].scatter(dawn_rises, deltas, s=80, c='steelblue', edgecolor='black')
        for r in results:
            axes[0].annotate(r['patient'], (r['dawn_rise_mg_dl'], r['delta_tir']),
                           fontsize=8, ha='center', va='bottom')
        axes[0].set_xlabel('Dawn Rise (mg/dL, 3AM→8AM)')
        axes[0].set_ylabel('Morning TIR Improvement (pp)')
        axes[0].set_title('Dawn Rise vs Dawn Ramp Benefit')
        axes[0].axhline(0, color='black', linewidth=0.5)

        # Plot 2: Morning TIR by ramp % for each patient
        ramp_pcts = [0, 25, 50, 75, 100]
        for r in results:
            tirs = [r['ramp_results'][str(pct)]['tir'] for pct in ramp_pcts]
            axes[1].plot(ramp_pcts, tirs, 'o-', alpha=0.5, label=r['patient'])
        axes[1].set_xlabel('Dawn Ramp (%)')
        axes[1].set_ylabel('Morning TIR (%)')
        axes[1].set_title('Morning TIR by Dawn Ramp Magnitude')
        axes[1].legend(fontsize=7, ncol=3)

        plt.tight_layout()
        fig_path = os.path.join(FIGURES_DIR, 'algo-fig03-dawn-countermeasure.png')
        plt.savefig(fig_path, dpi=150)
        plt.close()
        print(f"  → Saved {os.path.basename(fig_path)}")

    verdict = f"DAWN_{pop_dawn:+.0f}mg/dL_Δ{pop_delta_tir:+.1f}pp_{improved}/11_IMPROVE"
    print(f"\n  ✓ EXP-1983 verdict: {verdict}")

    return {
        'experiment': 'EXP-1983',
        'verdict': verdict,
        'per_patient': results,
        'population_dawn_rise': float(pop_dawn),
        'population_delta_tir': float(pop_delta_tir),
        'patients_improved': int(improved)
    }


# ============================================================================
# EXP-1984: Meal Response Pattern Clustering
# ============================================================================

def exp_1984_meal_response_clustering(patients, make_figures=False):
    """Cluster post-meal glucose patterns to identify treatable patterns."""
    print("\n" + "=" * 70)
    print("EXP-1984: Meal Response Pattern Clustering")
    print("=" * 70)

    results = []
    all_patterns = []  # For population-level clustering

    WINDOW = 36  # 3 hours post-meal

    for p in patients:
        pid = p['name']
        df = p['df']
        glucose = df['glucose'].values
        carbs = df['carbs'].values
        n = len(glucose)

        meals = find_meals(df, min_carbs=10)
        patterns = {'spike_return': 0, 'delayed_rise': 0, 'sustained_high': 0,
                    'double_peak': 0, 'minimal': 0, 'total': 0}

        meal_traces = []

        for meal_idx in meals:
            if meal_idx + WINDOW >= n:
                continue
            pre = glucose[meal_idx]
            if np.isnan(pre):
                continue
            trace = glucose[meal_idx:meal_idx + WINDOW] - pre
            if np.sum(np.isnan(trace)) > WINDOW * 0.3:
                continue

            # Interpolate nans
            valid_mask = ~np.isnan(trace)
            if valid_mask.sum() < WINDOW * 0.5:
                continue
            trace_interp = np.interp(np.arange(WINDOW),
                                     np.where(valid_mask)[0], trace[valid_mask])

            meal_traces.append(trace_interp)
            peak = np.max(trace_interp)
            peak_idx = np.argmax(trace_interp)
            end_val = trace_interp[-1]

            # Classify pattern
            patterns['total'] += 1
            if peak < 30:
                patterns['minimal'] += 1
            elif peak_idx < 12 and end_val < 30:  # peak <1h, returns to baseline
                patterns['spike_return'] += 1
            elif peak_idx >= 12:  # peak after 1 hour
                patterns['delayed_rise'] += 1
            elif end_val > 50:  # still high after 3 hours
                patterns['sustained_high'] += 1
            else:
                # Check for double peak
                # Find local minima after first peak
                after_peak = trace_interp[peak_idx:]
                if len(after_peak) > 6:
                    min_after = np.min(after_peak[:len(after_peak)//2])
                    max_after = np.max(after_peak[len(after_peak)//2:])
                    if max_after - min_after > 20 and min_after < peak - 20:
                        patterns['double_peak'] += 1
                    else:
                        patterns['spike_return'] += 1
                else:
                    patterns['spike_return'] += 1

        total = patterns['total']
        if total > 0:
            pct = {k: v / total * 100 for k, v in patterns.items() if k != 'total'}
        else:
            pct = {k: 0 for k in patterns if k != 'total'}

        print(f"  {pid}: n={total} spike={pct['spike_return']:.0f}% delayed={pct['delayed_rise']:.0f}% "
              f"sustained={pct['sustained_high']:.0f}% double={pct['double_peak']:.0f}% "
              f"minimal={pct['minimal']:.0f}%")

        results.append({
            'patient': pid,
            'n_meals': total,
            'patterns': patterns,
            'pct': pct
        })

        if meal_traces:
            all_patterns.extend(meal_traces)

    # Population pattern distribution
    pop_patterns = {}
    for key in ['spike_return', 'delayed_rise', 'sustained_high', 'double_peak', 'minimal']:
        pop_patterns[key] = sum(r['patterns'][key] for r in results)
    pop_total = sum(r['patterns']['total'] for r in results)
    pop_pct = {k: v / pop_total * 100 for k, v in pop_patterns.items()} if pop_total > 0 else {}

    if make_figures and HAS_MPL and all_patterns:
        fig, axes = plt.subplots(1, 3, figsize=(18, 5))

        # Plot 1: Population pattern distribution
        labels = list(pop_pct.keys())
        values = [pop_pct[k] for k in labels]
        colors = ['#e74c3c', '#f39c12', '#e67e22', '#9b59b6', '#2ecc71']
        axes[0].bar(range(len(labels)), values, color=colors)
        axes[0].set_xticks(range(len(labels)))
        axes[0].set_xticklabels([l.replace('_', '\n') for l in labels], fontsize=8)
        axes[0].set_ylabel('Percentage')
        axes[0].set_title(f'Meal Response Patterns (n={pop_total})')

        # Plot 2: Sample traces by category (population mean traces)
        # Average trace
        traces_arr = np.array(all_patterns[:min(500, len(all_patterns))])
        mean_trace = np.mean(traces_arr, axis=0)
        p10 = np.percentile(traces_arr, 10, axis=0)
        p90 = np.percentile(traces_arr, 90, axis=0)
        time_min = np.arange(WINDOW) * 5

        axes[1].fill_between(time_min, p10, p90, alpha=0.2, color='steelblue')
        axes[1].plot(time_min, mean_trace, 'b-', linewidth=2, label='Mean')
        axes[1].set_xlabel('Time Since Meal (min)')
        axes[1].set_ylabel('Glucose Change (mg/dL)')
        axes[1].set_title('Average Post-Meal Glucose Trajectory')
        axes[1].axhline(0, color='black', linewidth=0.5)
        axes[1].legend()

        # Plot 3: Per-patient pattern stacked bar
        patients_ids = [r['patient'] for r in results]
        bottom = np.zeros(len(results))
        for key, color in zip(['minimal', 'spike_return', 'delayed_rise', 'sustained_high', 'double_peak'],
                              colors[::-1]):
            vals = [r['pct'].get(key, 0) for r in results]
            axes[2].bar(range(len(results)), vals, bottom=bottom, label=key.replace('_', ' '), color=color)
            bottom += np.array(vals)
        axes[2].set_xticks(range(len(results)))
        axes[2].set_xticklabels(patients_ids)
        axes[2].set_ylabel('Percentage')
        axes[2].set_title('Per-Patient Pattern Distribution')
        axes[2].legend(fontsize=7, loc='upper right')

        plt.tight_layout()
        fig_path = os.path.join(FIGURES_DIR, 'algo-fig04-meal-patterns.png')
        plt.savefig(fig_path, dpi=150)
        plt.close()
        print(f"  → Saved {os.path.basename(fig_path)}")

    dominant = max(pop_pct, key=pop_pct.get) if pop_pct else 'unknown'
    verdict = f"DOMINANT_{dominant}_{pop_pct.get(dominant, 0):.0f}%_n={pop_total}"
    print(f"\n  ✓ EXP-1984 verdict: {verdict}")

    return {
        'experiment': 'EXP-1984',
        'verdict': verdict,
        'per_patient': results,
        'population_patterns': pop_patterns,
        'population_pct': pop_pct,
        'total_meals': pop_total
    }


# ============================================================================
# EXP-1985: Hypo Precursor Signal Detection
# ============================================================================

def exp_1985_hypo_precursors(patients, make_figures=False):
    """Identify data patterns that precede hypoglycemic events."""
    print("\n" + "=" * 70)
    print("EXP-1985: Hypo Precursor Signal Detection")
    print("=" * 70)

    results = []
    all_pre_hypo = {'iob': [], 'trend': [], 'time_since_meal': [], 'net_basal': [],
                    'glucose_30min_ago': [], 'bolus_1h': []}
    all_pre_normal = {'iob': [], 'trend': [], 'time_since_meal': [], 'net_basal': [],
                      'glucose_30min_ago': [], 'bolus_1h': []}

    for p in patients:
        pid = p['name']
        df = p['df']
        glucose = df['glucose'].values
        iob = df['iob'].values
        net_basal = df['net_basal'].values
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        n = len(glucose)

        # Compute trend rate
        trend = np.full(n, np.nan)
        for i in range(3, n):
            if not np.isnan(glucose[i]) and not np.isnan(glucose[i - 3]):
                trend[i] = (glucose[i] - glucose[i - 3]) / 3  # mg/dL per 5min

        # Time since last meal
        time_since_meal = np.full(n, 999.0)
        last_meal = -999
        for i in range(n):
            if carbs[i] >= 5:
                last_meal = i
            time_since_meal[i] = (i - last_meal) * 5 / 60  # hours

        # Recent bolus (sum in last hour)
        bolus_1h = np.zeros(n)
        for i in range(n):
            start = max(0, i - STEPS_PER_HOUR)
            bolus_1h[i] = np.nansum(bolus[start:i + 1])

        # Find hypo events (glucose crosses below 70)
        hypo_starts = []
        in_hypo = False
        for i in range(1, n):
            if not np.isnan(glucose[i]) and glucose[i] < 70 and not in_hypo:
                hypo_starts.append(i)
                in_hypo = True
            elif not np.isnan(glucose[i]) and glucose[i] >= 80:
                in_hypo = False

        # Collect precursor features (30 min before hypo)
        lookback = 6  # 30 minutes
        n_hypo = 0
        n_normal = 0

        for h_idx in hypo_starts:
            pre_idx = h_idx - lookback
            if pre_idx < 0:
                continue
            if np.isnan(iob[pre_idx]) or np.isnan(glucose[pre_idx]):
                continue

            n_hypo += 1
            all_pre_hypo['iob'].append(iob[pre_idx])
            all_pre_hypo['trend'].append(trend[pre_idx] if not np.isnan(trend[pre_idx]) else 0)
            all_pre_hypo['time_since_meal'].append(time_since_meal[pre_idx])
            all_pre_hypo['net_basal'].append(net_basal[pre_idx] if not np.isnan(net_basal[pre_idx]) else 0)
            all_pre_hypo['glucose_30min_ago'].append(glucose[pre_idx])
            all_pre_hypo['bolus_1h'].append(bolus_1h[pre_idx])

        # Sample normal periods for comparison (glucose 100-150, not near hypo)
        normal_candidates = []
        for i in range(lookback, n):
            if (not np.isnan(glucose[i]) and 100 <= glucose[i] <= 150
                    and not np.isnan(iob[i])):
                # Not within 2h of any hypo
                near_hypo = any(abs(i - h) < 24 for h in hypo_starts)
                if not near_hypo:
                    normal_candidates.append(i)

        # Sample same number as hypo events
        if normal_candidates and n_hypo > 0:
            np.random.seed(42)
            sample_n = min(len(normal_candidates), n_hypo * 3)
            sampled = np.random.choice(normal_candidates, sample_n, replace=False)
            for idx in sampled:
                pre_idx = idx - lookback
                if pre_idx < 0:
                    continue
                n_normal += 1
                all_pre_normal['iob'].append(iob[pre_idx])
                all_pre_normal['trend'].append(trend[pre_idx] if not np.isnan(trend[pre_idx]) else 0)
                all_pre_normal['time_since_meal'].append(time_since_meal[pre_idx])
                all_pre_normal['net_basal'].append(net_basal[pre_idx] if not np.isnan(net_basal[pre_idx]) else 0)
                all_pre_normal['glucose_30min_ago'].append(glucose[pre_idx])
                all_pre_normal['bolus_1h'].append(bolus_1h[pre_idx])

        print(f"  {pid}: n_hypo={n_hypo} n_normal={n_normal}")
        results.append({'patient': pid, 'n_hypo': n_hypo, 'n_normal': n_normal})

    # Compare distributions
    feature_diffs = {}
    for feat in all_pre_hypo:
        hypo_vals = np.array(all_pre_hypo[feat])
        norm_vals = np.array(all_pre_normal[feat])
        if len(hypo_vals) > 10 and len(norm_vals) > 10:
            hypo_med = np.median(hypo_vals)
            norm_med = np.median(norm_vals)
            # Effect size (Cohen's d approximation)
            pooled_std = np.sqrt((np.var(hypo_vals) + np.var(norm_vals)) / 2)
            effect_d = (hypo_med - norm_med) / pooled_std if pooled_std > 0 else 0
            feature_diffs[feat] = {
                'hypo_median': float(hypo_med),
                'normal_median': float(norm_med),
                'effect_size_d': float(effect_d)
            }
            print(f"  {feat}: hypo={hypo_med:.2f} normal={norm_med:.2f} d={effect_d:.2f}")

    # Rank features by absolute effect size
    ranked = sorted(feature_diffs.items(), key=lambda x: abs(x[1]['effect_size_d']), reverse=True)
    best_feature = ranked[0][0] if ranked else 'none'
    best_d = ranked[0][1]['effect_size_d'] if ranked else 0

    if make_figures and HAS_MPL:
        fig, axes = plt.subplots(2, 3, figsize=(18, 10))

        for i, feat in enumerate(['glucose_30min_ago', 'trend', 'iob',
                                   'net_basal', 'bolus_1h', 'time_since_meal']):
            ax = axes[i // 3][i % 3]
            hypo_vals = np.array(all_pre_hypo[feat])
            norm_vals = np.array(all_pre_normal[feat])
            if len(hypo_vals) > 5 and len(norm_vals) > 5:
                ax.hist(norm_vals, bins=30, alpha=0.5, density=True, label='Normal', color='green')
                ax.hist(hypo_vals, bins=30, alpha=0.5, density=True, label='Pre-hypo', color='red')
                d_val = feature_diffs.get(feat, {}).get('effect_size_d', 0)
                ax.set_title(f'{feat} (d={d_val:.2f})')
                ax.legend(fontsize=8)
            else:
                ax.set_title(f'{feat} (insufficient data)')

        plt.suptitle('Hypo Precursor Features: 30min Before Event', y=1.02, fontsize=14)
        plt.tight_layout()
        fig_path = os.path.join(FIGURES_DIR, 'algo-fig05-hypo-precursors.png')
        plt.savefig(fig_path, dpi=150, bbox_inches='tight')
        plt.close()
        print(f"  → Saved {os.path.basename(fig_path)}")

    total_hypo = sum(r['n_hypo'] for r in results)
    verdict = f"BEST_{best_feature}_d={best_d:.2f}_n={total_hypo}"
    print(f"\n  ✓ EXP-1985 verdict: {verdict}")

    return {
        'experiment': 'EXP-1985',
        'verdict': verdict,
        'per_patient': results,
        'feature_comparisons': feature_diffs,
        'feature_ranking': [(f, d['effect_size_d']) for f, d in ranked],
        'total_hypo_events': total_hypo
    }


# ============================================================================
# EXP-1986: Loop Effort Score Definition
# ============================================================================

def exp_1986_loop_effort_score(patients, make_figures=False):
    """Define and validate a composite Loop Effort Score for clinical use."""
    print("\n" + "=" * 70)
    print("EXP-1986: Loop Effort Score Definition")
    print("=" * 70)

    results = []

    for p in patients:
        pid = p['name']
        df = p['df']
        glucose = df['glucose'].values
        net_basal = df['net_basal'].values
        sched_basal = get_basal(df)
        iob = df['iob'].values
        n = len(glucose)

        # Component 1: Compensation magnitude (|net_basal - 0| / scheduled)
        valid_nb = net_basal[~np.isnan(net_basal)]
        if sched_basal > 0 and len(valid_nb) > 100:
            comp_magnitude = np.mean(np.abs(valid_nb)) / sched_basal
        else:
            comp_magnitude = 0

        # Component 2: Suspension fraction (net_basal ≈ 0 or negative)
        if len(valid_nb) > 100:
            suspension_frac = np.mean(valid_nb <= 0.05)
        else:
            suspension_frac = 0

        # Component 3: Delivery variability (CV of net_basal)
        if len(valid_nb) > 100 and np.mean(np.abs(valid_nb)) > 0:
            delivery_cv = np.std(valid_nb) / np.mean(np.abs(valid_nb))
        else:
            delivery_cv = 0

        # Component 4: Correction frequency (direction changes per hour)
        if len(valid_nb) > 100:
            direction_changes = np.sum(np.diff(np.sign(np.diff(valid_nb))) != 0)
            hours = len(valid_nb) / STEPS_PER_HOUR
            correction_freq = direction_changes / hours if hours > 0 else 0
        else:
            correction_freq = 0

        # Composite score: normalized 0-100
        # Weights based on clinical relevance
        score = (comp_magnitude * 25 +
                 suspension_frac * 25 +
                 min(delivery_cv, 2) * 12.5 +
                 min(correction_freq / 10, 1) * 12.5)
        score = min(score, 100)

        # Correlate with outcomes
        metrics = glucose_metrics(glucose)
        tir = metrics['tir']
        tbr = metrics['tbr']

        print(f"  {pid}: score={score:.1f} comp={comp_magnitude:.2f} "
              f"susp={suspension_frac:.0%} cv={delivery_cv:.2f} "
              f"freq={correction_freq:.1f}/h TIR={tir:.0f}%")

        results.append({
            'patient': pid,
            'loop_effort_score': float(score),
            'comp_magnitude': float(comp_magnitude),
            'suspension_fraction': float(suspension_frac),
            'delivery_cv': float(delivery_cv),
            'correction_frequency': float(correction_freq),
            'tir': float(tir),
            'tbr': float(tbr)
        })

    # Correlate effort score with outcomes
    scores = np.array([r['loop_effort_score'] for r in results])
    tirs = np.array([r['tir'] for r in results])
    tbrs = np.array([r['tbr'] for r in results])

    score_tir_corr = np.corrcoef(scores, tirs)[0, 1]
    score_tbr_corr = np.corrcoef(scores, tbrs)[0, 1]

    # Define clinical thresholds
    threshold_review = np.percentile(scores, 75)  # top 25% need review
    needs_review = sum(1 for s in scores if s > threshold_review)

    if make_figures and HAS_MPL:
        fig, axes = plt.subplots(1, 3, figsize=(18, 5))

        # Plot 1: Effort score components
        patients_ids = [r['patient'] for r in results]
        x = np.arange(len(results))
        width = 0.2
        axes[0].bar(x - 1.5 * width, [r['comp_magnitude'] for r in results],
                    width, label='Compensation', color='#e74c3c')
        axes[0].bar(x - 0.5 * width, [r['suspension_fraction'] for r in results],
                    width, label='Suspension', color='#f39c12')
        axes[0].bar(x + 0.5 * width, [min(r['delivery_cv'], 2) / 2 for r in results],
                    width, label='Variability', color='#3498db')
        axes[0].bar(x + 1.5 * width, [min(r['correction_frequency'] / 10, 1) for r in results],
                    width, label='Frequency', color='#2ecc71')
        axes[0].set_xticks(x)
        axes[0].set_xticklabels(patients_ids)
        axes[0].set_ylabel('Normalized Component')
        axes[0].set_title('Loop Effort Score Components')
        axes[0].legend(fontsize=7)

        # Plot 2: Score vs TIR
        axes[1].scatter(scores, tirs, s=80, c='steelblue', edgecolor='black')
        for r in results:
            axes[1].annotate(r['patient'], (r['loop_effort_score'], r['tir']),
                           fontsize=9, ha='center', va='bottom')
        axes[1].set_xlabel('Loop Effort Score')
        axes[1].set_ylabel('TIR (%)')
        axes[1].set_title(f'Effort Score vs TIR (r={score_tir_corr:.2f})')
        axes[1].axvline(threshold_review, color='red', linestyle='--',
                       label=f'Review threshold ({threshold_review:.0f})')
        axes[1].legend()

        # Plot 3: Score vs TBR
        axes[2].scatter(scores, tbrs, s=80, c='#e74c3c', edgecolor='black')
        for r in results:
            axes[2].annotate(r['patient'], (r['loop_effort_score'], r['tbr']),
                           fontsize=9, ha='center', va='bottom')
        axes[2].set_xlabel('Loop Effort Score')
        axes[2].set_ylabel('TBR (%)')
        axes[2].set_title(f'Effort Score vs TBR (r={score_tbr_corr:.2f})')
        axes[2].axvline(threshold_review, color='red', linestyle='--')

        plt.tight_layout()
        fig_path = os.path.join(FIGURES_DIR, 'algo-fig06-effort-score.png')
        plt.savefig(fig_path, dpi=150)
        plt.close()
        print(f"  → Saved {os.path.basename(fig_path)}")

    verdict = (f"SCORE_TIR_r={score_tir_corr:.2f}_TBR_r={score_tbr_corr:.2f}_"
               f"REVIEW_{needs_review}/11")
    print(f"\n  ✓ EXP-1986 verdict: {verdict}")

    return {
        'experiment': 'EXP-1986',
        'verdict': verdict,
        'per_patient': results,
        'score_tir_corr': float(score_tir_corr),
        'score_tbr_corr': float(score_tbr_corr),
        'review_threshold': float(threshold_review),
        'needs_review': int(needs_review)
    }


# ============================================================================
# EXP-1987: Meal Size-Specific Algorithm Gaps
# ============================================================================

def exp_1987_meal_size_gaps(patients, make_figures=False):
    """Analyze loop response quality by meal size to identify algorithm gaps."""
    print("\n" + "=" * 70)
    print("EXP-1987: Meal Size-Specific Algorithm Gaps")
    print("=" * 70)

    results = []
    all_meals = {'small': {'spike': [], 'return': [], 'overshoot': []},
                 'medium': {'spike': [], 'return': [], 'overshoot': []},
                 'large': {'spike': [], 'return': [], 'overshoot': []}}

    for p in patients:
        pid = p['name']
        df = p['df']
        glucose = df['glucose'].values
        carbs = df['carbs'].values
        bolus = df['bolus'].values
        n = len(glucose)

        meals = find_meals(df, min_carbs=5)
        patient_meals = {'small': [], 'medium': [], 'large': []}

        for meal_idx in meals:
            carb_amt = carbs[meal_idx]
            if meal_idx + 36 >= n or meal_idx < 6:
                continue
            pre = glucose[meal_idx]
            if np.isnan(pre):
                continue

            # Post-meal trajectory (3h)
            post = glucose[meal_idx:meal_idx + 36]
            valid = ~np.isnan(post)
            if valid.sum() < 10:
                continue

            peak = np.nanmax(post)
            spike = peak - pre
            return_time = 36  # default: didn't return
            for j in range(12, 36):  # after 1h
                if not np.isnan(post[j]) and post[j] <= pre + 10:
                    return_time = j
                    break

            # Overshoot below pre-meal
            post_2h = glucose[meal_idx + 24:meal_idx + 48] if meal_idx + 48 < n else np.array([])
            overshoot = pre - np.nanmin(post_2h) if len(post_2h) > 0 and not np.all(np.isnan(post_2h)) else 0

            meal_data = {'spike': spike, 'return_steps': return_time, 'overshoot': max(0, overshoot)}

            # Categorize by size
            if carb_amt < 20:
                cat = 'small'
            elif carb_amt < 50:
                cat = 'medium'
            else:
                cat = 'large'
            patient_meals[cat].append(meal_data)
            all_meals[cat]['spike'].append(spike)
            all_meals[cat]['return'].append(return_time * 5)  # minutes
            all_meals[cat]['overshoot'].append(max(0, overshoot))

        # Summarize per patient
        patient_summary = {}
        for cat in ['small', 'medium', 'large']:
            if patient_meals[cat]:
                spikes = [m['spike'] for m in patient_meals[cat]]
                returns = [m['return_steps'] for m in patient_meals[cat]]
                overshoots = [m['overshoot'] for m in patient_meals[cat]]
                patient_summary[cat] = {
                    'n': len(spikes),
                    'median_spike': float(np.median(spikes)),
                    'median_return_min': float(np.median(returns)) * 5,
                    'median_overshoot': float(np.median(overshoots))
                }
            else:
                patient_summary[cat] = {'n': 0}

        print(f"  {pid}: small={patient_summary['small'].get('n', 0)} "
              f"med={patient_summary['medium'].get('n', 0)} "
              f"large={patient_summary['large'].get('n', 0)}")

        results.append({
            'patient': pid,
            'meal_summary': patient_summary
        })

    # Population summary
    pop_summary = {}
    for cat in ['small', 'medium', 'large']:
        if all_meals[cat]['spike']:
            pop_summary[cat] = {
                'n': len(all_meals[cat]['spike']),
                'median_spike': float(np.median(all_meals[cat]['spike'])),
                'p75_spike': float(np.percentile(all_meals[cat]['spike'], 75)),
                'median_return_min': float(np.median(all_meals[cat]['return'])),
                'median_overshoot': float(np.median(all_meals[cat]['overshoot']))
            }
            print(f"  Population {cat}: n={pop_summary[cat]['n']} "
                  f"spike={pop_summary[cat]['median_spike']:.0f}mg/dL "
                  f"return={pop_summary[cat]['median_return_min']:.0f}min "
                  f"overshoot={pop_summary[cat]['median_overshoot']:.0f}mg/dL")

    if make_figures and HAS_MPL:
        fig, axes = plt.subplots(1, 3, figsize=(18, 5))

        # Plot 1: Spike by meal size
        cats = ['small', 'medium', 'large']
        spikes_by_cat = [all_meals[c]['spike'] for c in cats]
        bp1 = axes[0].boxplot(spikes_by_cat, labels=['<20g', '20-50g', '>50g'],
                              patch_artist=True)
        colors = ['#2ecc71', '#f39c12', '#e74c3c']
        for patch, color in zip(bp1['boxes'], colors):
            patch.set_facecolor(color)
            patch.set_alpha(0.6)
        axes[0].set_ylabel('Post-Meal Spike (mg/dL)')
        axes[0].set_title('Spike by Meal Size')
        axes[0].axhline(70, color='red', linestyle='--', alpha=0.5, label='70mg/dL')
        axes[0].legend()

        # Plot 2: Return time by meal size
        returns_by_cat = [all_meals[c]['return'] for c in cats]
        bp2 = axes[1].boxplot(returns_by_cat, labels=['<20g', '20-50g', '>50g'],
                              patch_artist=True)
        for patch, color in zip(bp2['boxes'], colors):
            patch.set_facecolor(color)
            patch.set_alpha(0.6)
        axes[1].set_ylabel('Return to Baseline (min)')
        axes[1].set_title('Recovery Time by Meal Size')

        # Plot 3: Overshoot by meal size
        over_by_cat = [all_meals[c]['overshoot'] for c in cats]
        bp3 = axes[2].boxplot(over_by_cat, labels=['<20g', '20-50g', '>50g'],
                              patch_artist=True)
        for patch, color in zip(bp3['boxes'], colors):
            patch.set_facecolor(color)
            patch.set_alpha(0.6)
        axes[2].set_ylabel('Post-Meal Overshoot Below Baseline (mg/dL)')
        axes[2].set_title('Overshoot (Hypo Risk) by Meal Size')

        plt.tight_layout()
        fig_path = os.path.join(FIGURES_DIR, 'algo-fig07-meal-size-gaps.png')
        plt.savefig(fig_path, dpi=150)
        plt.close()
        print(f"  → Saved {os.path.basename(fig_path)}")

    # Worst category
    if pop_summary:
        worst_cat = max(pop_summary, key=lambda c: pop_summary[c]['median_spike'])
        verdict = (f"WORST_{worst_cat}_SPIKE_{pop_summary[worst_cat]['median_spike']:.0f}mg/dL_"
                   f"RETURN_{pop_summary[worst_cat]['median_return_min']:.0f}min")
    else:
        verdict = "NO_DATA"
    print(f"\n  ✓ EXP-1987 verdict: {verdict}")

    return {
        'experiment': 'EXP-1987',
        'verdict': verdict,
        'per_patient': results,
        'population_summary': pop_summary
    }


# ============================================================================
# EXP-1988: Algorithm Improvement Synthesis
# ============================================================================

def exp_1988_algorithm_synthesis(patients, all_results, make_figures=False):
    """Synthesize all findings into prioritized algorithm recommendations."""
    print("\n" + "=" * 70)
    print("EXP-1988: Algorithm Improvement Synthesis")
    print("=" * 70)

    # Extract key metrics from previous experiments
    recommendations = []

    # 1. From EXP-1981: Time-of-day mismatch
    if 'EXP-1981' in all_results:
        r = all_results['EXP-1981']
        morning_excess = r.get('morning_excess', 0)
        recommendations.append({
            'priority': 1,
            'category': 'basal_profile',
            'recommendation': 'Implement time-varying basal that matches metabolic need',
            'evidence': f'Morning basal excess of {morning_excess:+.2f}U/h',
            'expected_impact': 'Morning TIR improvement',
            'implementation': 'Profile learning from net_basal delivery patterns'
        })

    # 2. From EXP-1982: Pre-bolus timing
    if 'EXP-1982' in all_results:
        r = all_results['EXP-1982']
        reduction = r.get('spike_reduction_mg_dl', 0)
        pct_pre = r.get('population_pct_prebolus', 0)
        recommendations.append({
            'priority': 2,
            'category': 'meal_dosing',
            'recommendation': 'Implement pre-bolus timing guidance',
            'evidence': f'Pre-bolus reduces spikes by {reduction:.0f}mg/dL, only {pct_pre:.0f}% of meals pre-bolused',
            'expected_impact': f'{reduction:.0f}mg/dL spike reduction',
            'implementation': 'CGM trend-based timing advice, meal announcement prompt'
        })

    # 3. From EXP-1983: Dawn countermeasure
    if 'EXP-1983' in all_results:
        r = all_results['EXP-1983']
        delta = r.get('population_delta_tir', 0)
        improved = r.get('patients_improved', 0)
        recommendations.append({
            'priority': 3,
            'category': 'dawn_phenomenon',
            'recommendation': 'Proactive dawn basal ramp (3-6AM)',
            'evidence': f'{improved}/11 patients benefit, Δ{delta:+.1f}pp morning TIR',
            'expected_impact': 'Morning glucose reduction',
            'implementation': 'Learn dawn pattern, auto-increase basal 3-6AM'
        })

    # 4. From EXP-1985: Hypo precursors
    if 'EXP-1985' in all_results:
        r = all_results['EXP-1985']
        ranking = r.get('feature_ranking', [])
        if ranking:
            best = ranking[0]
            recommendations.append({
                'priority': 4,
                'category': 'safety',
                'recommendation': f'Early hypo warning using {best[0]}',
                'evidence': f'Effect size d={best[1]:.2f} 30min before hypo',
                'expected_impact': 'Earlier hypo prevention',
                'implementation': f'Monitor {best[0]}, trigger alert when pattern detected'
            })

    # 5. From EXP-1986: Effort score
    if 'EXP-1986' in all_results:
        r = all_results['EXP-1986']
        tir_corr = r.get('score_tir_corr', 0)
        needs = r.get('needs_review', 0)
        recommendations.append({
            'priority': 5,
            'category': 'clinical_decision',
            'recommendation': 'Loop Effort Score as settings review trigger',
            'evidence': f'Score-TIR r={tir_corr:.2f}, {needs}/11 need review',
            'expected_impact': 'Automated settings review flagging',
            'implementation': 'Compute score from 14-day rolling window'
        })

    # 6. From EXP-1987: Meal size gaps
    if 'EXP-1987' in all_results:
        r = all_results['EXP-1987']
        pop = r.get('population_summary', {})
        if 'large' in pop:
            large_spike = pop['large']['median_spike']
            recommendations.append({
                'priority': 6,
                'category': 'meal_algorithm',
                'recommendation': 'Meal-size adaptive dosing',
                'evidence': f'Large meals spike {large_spike:.0f}mg/dL, loop doesn\'t scale',
                'expected_impact': 'Reduced large meal spikes',
                'implementation': 'Meal size estimation from CGM rise rate, progressive dosing'
            })

    # Print synthesis
    for rec in recommendations:
        print(f"  #{rec['priority']}: [{rec['category']}] {rec['recommendation']}")
        print(f"     Evidence: {rec['evidence']}")
        print(f"     Impact: {rec['expected_impact']}")

    # Score each recommendation
    for rec in recommendations:
        # Crude impact score based on evidence strength
        if 'mg/dL' in rec['expected_impact']:
            rec['impact_score'] = 8
        elif 'TIR' in rec['expected_impact']:
            rec['impact_score'] = 7
        elif 'prevention' in rec['expected_impact']:
            rec['impact_score'] = 9  # Safety is highest priority
        else:
            rec['impact_score'] = 5

    if make_figures and HAS_MPL:
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))

        # Plot 1: Recommendation priority matrix
        cats = [r['category'] for r in recommendations]
        impacts = [r['impact_score'] for r in recommendations]
        priorities = [r['priority'] for r in recommendations]

        scatter = axes[0].scatter(priorities, impacts, s=200, c=impacts,
                                  cmap='RdYlGn', edgecolor='black')
        for r in recommendations:
            axes[0].annotate(r['category'].replace('_', '\n'), (r['priority'], r['impact_score']),
                           fontsize=7, ha='center', va='bottom')
        axes[0].set_xlabel('Priority Rank')
        axes[0].set_ylabel('Impact Score')
        axes[0].set_title('Algorithm Improvement Priority Matrix')
        axes[0].invert_xaxis()

        # Plot 2: Category bar chart
        axes[1].barh(range(len(recommendations)), [r['impact_score'] for r in recommendations],
                    color=['#e74c3c', '#f39c12', '#3498db', '#2ecc71', '#9b59b6', '#1abc9c'])
        axes[1].set_yticks(range(len(recommendations)))
        axes[1].set_yticklabels([r['category'].replace('_', ' ') for r in recommendations], fontsize=9)
        axes[1].set_xlabel('Impact Score')
        axes[1].set_title('Recommendations by Impact')

        plt.tight_layout()
        fig_path = os.path.join(FIGURES_DIR, 'algo-fig08-synthesis.png')
        plt.savefig(fig_path, dpi=150)
        plt.close()
        print(f"  → Saved {os.path.basename(fig_path)}")

    verdict = f"{len(recommendations)}_RECOMMENDATIONS_TOP=safety"
    print(f"\n  ✓ EXP-1988 verdict: {verdict}")

    return {
        'experiment': 'EXP-1988',
        'verdict': verdict,
        'recommendations': recommendations
    }


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description='EXP-1981–1988: Algorithm Improvements')
    parser.add_argument('--figures', action='store_true', help='Generate figures')
    args = parser.parse_args()

    # Load data
    patients = load_patients('externals/ns-data/patients/')

    os.makedirs(FIGURES_DIR, exist_ok=True)

    all_results = {}

    # Run experiments
    experiments = [
        ('EXP-1981', exp_1981_time_of_day_mismatch),
        ('EXP-1982', exp_1982_prebolus_timing),
        ('EXP-1983', exp_1983_dawn_countermeasure),
        ('EXP-1984', exp_1984_meal_response_clustering),
        ('EXP-1985', exp_1985_hypo_precursors),
        ('EXP-1986', exp_1986_loop_effort_score),
        ('EXP-1987', exp_1987_meal_size_gaps),
    ]

    for exp_id, func in experiments:
        print(f"\n{'#' * 70}")
        print(f"# Running {exp_id}")
        print(f"{'#' * 70}")
        result = func(patients, make_figures=args.figures)
        all_results[exp_id] = result

    # Synthesis depends on all results
    print(f"\n{'#' * 70}")
    print(f"# Running EXP-1988")
    print(f"{'#' * 70}")
    all_results['EXP-1988'] = exp_1988_algorithm_synthesis(patients, all_results, make_figures=args.figures)

    # Print summary
    print("\n" + "=" * 70)
    print("SYNTHESIS: Algorithm Improvements")
    print("=" * 70)
    for exp_id in sorted(all_results.keys()):
        print(f"  {exp_id}: {all_results[exp_id]['verdict']}")

    # Save results
    with open(RESULTS_FILE, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)


if __name__ == '__main__':
    main()
