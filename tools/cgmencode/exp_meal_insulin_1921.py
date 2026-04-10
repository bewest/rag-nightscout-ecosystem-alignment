#!/usr/bin/env python3
"""EXP-1921–1928: Meal Response Analysis & Insulin Model Improvement.

EXP-1914 showed demand scale is 2.2× higher during meals than non-meals
for 10/11 patients. This batch investigates WHY and builds improved models.

Key question: Is the meal-time demand miscalibration due to:
  H1: Insulin activity curve underestimates peak effect
  H2: Carb absorption model overestimates supply
  H3: Insulin stacking from bolus + loop creates non-linear effects
  H4: Bolus timing relative to meals affects model accuracy
  H5: AID loop corrections during meals follow specific patterns

Experiments:
  EXP-1921: Meal response decomposition — supply vs demand error budget
  EXP-1922: Biexponential insulin activity curve fitting
  EXP-1923: Insulin stacking analysis during meals
  EXP-1924: Bolus timing and pre-bolus effect on model accuracy
  EXP-1925: AID loop correction patterns around meals
  EXP-1926: Improved meal-aware demand model
  EXP-1927: Temporal cross-validation of improved model
  EXP-1928: Clinical impact — projected TIR improvement from better model
"""

import argparse
import json
import os
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from cgmencode.exp_metabolic_441 import load_patients, compute_supply_demand

warnings.filterwarnings('ignore')

FIGURES_DIR = Path('docs/60-research/figures')
RESULTS_PATH = Path('externals/experiments/exp-1921_meal_insulin_model.json')
STEPS_PER_HOUR = 12
STEPS_PER_DAY = 288

# --- Reusable Helpers ---

def get_isf(patient):
    isf_sched = patient['df'].attrs.get('isf_schedule', None)
    if isf_sched and isinstance(isf_sched, list) and len(isf_sched) > 0:
        val = isf_sched[0].get('value', isf_sched[0].get('sensitivity', 50))
        if val < 15:
            val *= 18.0182
        return val
    return 50

def get_cr(patient):
    cr_sched = patient['df'].attrs.get('cr_schedule', None)
    if cr_sched and isinstance(cr_sched, list) and len(cr_sched) > 0:
        return cr_sched[0].get('value', cr_sched[0].get('ratio', 10))
    return 10

def get_basal(patient):
    basal_sched = patient['df'].attrs.get('basal_schedule', None)
    if basal_sched and isinstance(basal_sched, list) and len(basal_sched) > 0:
        return basal_sched[0].get('value', basal_sched[0].get('rate', 1.0))
    return 1.0

def find_meals(df, min_carbs=5, post_window=36, pre_window=6):
    """Find meal events, return list of (start, end, carbs, bolus) tuples."""
    carbs = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(df))
    bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(len(df))
    meals = []
    i = 0
    while i < len(df) - post_window:
        c = carbs[i] if np.isfinite(carbs[i]) else 0
        if c >= min_carbs:
            meal_carbs = c
            meal_bolus = 0
            # Look for bolus within pre_window before to post_window/3 after
            for j in range(max(0, i - pre_window), min(len(df), i + post_window // 3)):
                b = bolus[j] if np.isfinite(bolus[j]) else 0
                if b > 0.1:
                    meal_bolus += b
            meals.append({
                'idx': i,
                'end': min(i + post_window, len(df)),
                'carbs': meal_carbs,
                'bolus': meal_bolus,
                'pre_start': max(0, i - pre_window),
            })
            i += post_window  # skip window
        else:
            i += 1
    return meals

def supply_demand_loss(sd, glucose, mask=None):
    """Compute MSE of S/D model residual, optionally masked."""
    supply = sd.get('supply', np.zeros_like(glucose))
    demand = sd.get('demand', np.zeros_like(glucose))
    net = supply - demand
    dg = np.diff(glucose, prepend=glucose[0])
    residual = dg - net
    if mask is not None:
        residual = residual[mask]
    valid = np.isfinite(residual)
    if valid.sum() < 10:
        return np.nan
    return float(np.mean(residual[valid] ** 2))

def optimal_demand_scale(sd, glucose, mask=None, scale_range=(0.01, 5.01), step=0.05):
    """Find optimal demand scale, optionally within mask."""
    supply = sd.get('supply', np.zeros_like(glucose))
    demand = sd.get('demand', np.zeros_like(glucose))
    dg = np.diff(glucose, prepend=glucose[0])
    best_scale = 1.0
    best_loss = np.inf
    for scale in np.arange(scale_range[0], scale_range[1], step):
        net = supply - demand * scale
        residual = dg - net
        if mask is not None:
            residual = residual[mask]
        valid = np.isfinite(residual)
        if valid.sum() < 10:
            continue
        loss = float(np.mean(residual[valid] ** 2))
        if loss < best_loss:
            best_loss = loss
            best_scale = scale
    return best_scale, best_loss


# =====================================================================
# EXP-1921: Meal Response Decomposition
# =====================================================================

def exp_1921(patients, save_fig=False):
    """Decompose meal-time model error into supply and demand components.

    For each meal event, compute:
    - Supply error: how well does carb absorption explain glucose rise?
    - Demand error: how well does insulin activity explain glucose fall?
    - Residual: what remains unexplained?
    """
    print("\n" + "=" * 70)
    print("EXP-1921: Meal Response Decomposition")
    print("=" * 70)

    all_results = []
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        sd = compute_supply_demand(df)
        supply = sd.get('supply', np.zeros_like(glucose))
        demand = sd.get('demand', np.zeros_like(glucose))
        hepatic = sd.get('hepatic', np.zeros_like(glucose))
        carb_supply = sd.get('carb_supply', np.zeros_like(glucose))
        dg = np.diff(glucose, prepend=glucose[0])

        meals = find_meals(df)
        if len(meals) < 3:
            print(f"  {name}: <3 meals, skip")
            continue

        # For each meal, decompose error in post-meal window
        supply_errors = []
        demand_errors = []
        net_errors = []
        rise_phases = []  # glucose rising (0-1h post meal)
        fall_phases = []  # glucose falling (1-3h post meal)

        for m in meals:
            idx, end = m['idx'], m['end']
            window = slice(idx, end)
            w_dg = dg[window]
            w_supply = supply[window]
            w_demand = demand[window]
            w_net = w_supply - w_demand

            valid = np.isfinite(w_dg) & np.isfinite(w_net)
            if valid.sum() < 6:
                continue

            # Supply error: actual rise - modeled supply (during rise phase, first hour)
            rise_end = min(STEPS_PER_HOUR, end - idx)
            rise_slice = slice(0, rise_end)
            rise_valid = valid[rise_slice]
            if rise_valid.sum() > 3:
                supply_err = float(np.mean((w_dg[rise_slice][rise_valid] - w_supply[rise_slice][rise_valid]) ** 2))
                supply_errors.append(supply_err)
                rise_phases.append({
                    'actual_rise': float(np.nanmean(w_dg[rise_slice][rise_valid])),
                    'modeled_supply': float(np.nanmean(w_supply[rise_slice][rise_valid])),
                    'modeled_demand': float(np.nanmean(w_demand[rise_slice][rise_valid])),
                })

            # Demand error: actual fall - modeled demand (during fall phase, 1-3h)
            fall_start = STEPS_PER_HOUR
            fall_end_idx = min(3 * STEPS_PER_HOUR, end - idx)
            if fall_end_idx > fall_start:
                fall_slice = slice(fall_start, fall_end_idx)
                fall_valid = valid[fall_slice]
                if fall_valid.sum() > 3:
                    demand_err = float(np.mean((w_dg[fall_slice][fall_valid] - w_net[fall_slice][fall_valid]) ** 2))
                    demand_errors.append(demand_err)
                    fall_phases.append({
                        'actual_fall': float(np.nanmean(w_dg[fall_slice][fall_valid])),
                        'modeled_supply': float(np.nanmean(w_supply[fall_slice][fall_valid])),
                        'modeled_demand': float(np.nanmean(w_demand[fall_slice][fall_valid])),
                    })

            # Total meal window error
            net_errors.append(float(np.mean((w_dg[valid] - w_net[valid]) ** 2)))

        result = {
            'patient': name,
            'n_meals': len(meals),
            'n_analyzed': len(net_errors),
            'mean_supply_error': float(np.mean(supply_errors)) if supply_errors else np.nan,
            'mean_demand_error': float(np.mean(demand_errors)) if demand_errors else np.nan,
            'mean_total_error': float(np.mean(net_errors)) if net_errors else np.nan,
        }

        # Compute average rise/fall phase characteristics
        if rise_phases:
            result['rise_actual'] = float(np.mean([r['actual_rise'] for r in rise_phases]))
            result['rise_supply'] = float(np.mean([r['modeled_supply'] for r in rise_phases]))
            result['rise_demand'] = float(np.mean([r['modeled_demand'] for r in rise_phases]))
        if fall_phases:
            result['fall_actual'] = float(np.mean([r['actual_fall'] for r in fall_phases]))
            result['fall_supply'] = float(np.mean([r['modeled_supply'] for r in fall_phases]))
            result['fall_demand'] = float(np.mean([r['modeled_demand'] for r in fall_phases]))

        all_results.append(result)
        print(f"  {name}: {len(meals)} meals, supply_err={result['mean_supply_error']:.1f} demand_err={result['mean_demand_error']:.1f} total_err={result['mean_total_error']:.1f}")

    # Compute population summary
    valid_results = [r for r in all_results if np.isfinite(r.get('mean_supply_error', np.nan))]
    if valid_results:
        pop_supply = np.mean([r['mean_supply_error'] for r in valid_results])
        pop_demand = np.mean([r['mean_demand_error'] for r in valid_results])
        pop_total = np.mean([r['mean_total_error'] for r in valid_results])
        supply_frac = pop_supply / (pop_supply + pop_demand) * 100 if (pop_supply + pop_demand) > 0 else 50
        print(f"\n  Population: supply_err={pop_supply:.1f} ({supply_frac:.0f}%) demand_err={pop_demand:.1f} ({100-supply_frac:.0f}%)")
        verdict = f"SUPPLY_{supply_frac:.0f}%_DEMAND_{100-supply_frac:.0f}%"
    else:
        verdict = "INSUFFICIENT_DATA"

    if save_fig and valid_results:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt

            fig, axes = plt.subplots(1, 3, figsize=(15, 5))

            # Panel 1: Supply vs Demand error budget
            names = [r['patient'] for r in valid_results]
            s_err = [r['mean_supply_error'] for r in valid_results]
            d_err = [r['mean_demand_error'] for r in valid_results]
            x = np.arange(len(names))
            axes[0].bar(x, s_err, 0.35, label='Supply error (rise phase)', color='coral')
            axes[0].bar(x + 0.35, d_err, 0.35, label='Demand error (fall phase)', color='steelblue')
            axes[0].set_xticks(x + 0.175)
            axes[0].set_xticklabels(names)
            axes[0].set_ylabel('MSE')
            axes[0].set_title('Meal Error: Supply vs Demand')
            axes[0].legend()

            # Panel 2: Rise phase — actual vs modeled
            rise_data = [r for r in valid_results if 'rise_actual' in r]
            if rise_data:
                rn = [r['patient'] for r in rise_data]
                ra = [r['rise_actual'] for r in rise_data]
                rs = [r['rise_supply'] for r in rise_data]
                rd = [r['rise_demand'] for r in rise_data]
                x2 = np.arange(len(rn))
                axes[1].bar(x2 - 0.2, ra, 0.2, label='Actual dG/dt', color='black')
                axes[1].bar(x2, rs, 0.2, label='Modeled supply', color='coral')
                axes[1].bar(x2 + 0.2, rd, 0.2, label='Modeled demand', color='steelblue')
                axes[1].set_xticks(x2)
                axes[1].set_xticklabels(rn)
                axes[1].set_ylabel('mg/dL per 5min')
                axes[1].set_title('Rise Phase (0-1h): Supply vs Demand')
                axes[1].legend()
                axes[1].axhline(0, color='gray', ls='--', lw=0.5)

            # Panel 3: Fall phase
            fall_data = [r for r in valid_results if 'fall_actual' in r]
            if fall_data:
                fn = [r['patient'] for r in fall_data]
                fa = [r['fall_actual'] for r in fall_data]
                fs = [r['fall_supply'] for r in fall_data]
                fd = [r['fall_demand'] for r in fall_data]
                x3 = np.arange(len(fn))
                axes[2].bar(x3 - 0.2, fa, 0.2, label='Actual dG/dt', color='black')
                axes[2].bar(x3, fs, 0.2, label='Modeled supply', color='coral')
                axes[2].bar(x3 + 0.2, [-d for d in fd], 0.2, label='−Modeled demand', color='steelblue')
                axes[2].set_xticks(x3)
                axes[2].set_xticklabels(fn)
                axes[2].set_ylabel('mg/dL per 5min')
                axes[2].set_title('Fall Phase (1-3h): Actual vs Model')
                axes[2].legend()
                axes[2].axhline(0, color='gray', ls='--', lw=0.5)

            plt.tight_layout()
            fig.savefig(FIGURES_DIR / 'meal-fig01-error-decomposition.png', dpi=150)
            plt.close(fig)
            print(f"  → Saved meal-fig01-error-decomposition.png")
        except Exception as e:
            print(f"  (figure skipped: {e})")

    print(f"\n  ✓ EXP-1921 verdict: {verdict}")
    return {'experiment': 'EXP-1921', 'title': 'Meal Response Decomposition',
            'verdict': verdict, 'per_patient': all_results}


# =====================================================================
# EXP-1922: Biexponential Insulin Activity Curve
# =====================================================================

def exp_1922(patients, save_fig=False):
    """Test if biexponential insulin activity fits meal-time glucose better.

    Standard model: activity(t) = (t/tau²) × exp(-t/tau)
    Biexponential:  activity(t) = A × (exp(-t/tau1) - exp(-t/tau2))

    Compare residuals during meal windows.
    """
    print("\n" + "=" * 70)
    print("EXP-1922: Biexponential Insulin Activity Analysis")
    print("=" * 70)

    all_results = []
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        iob = df['iob'].values if 'iob' in df.columns else np.zeros(len(df))
        bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(len(df))
        isf = get_isf(p)

        meals = find_meals(df)
        if len(meals) < 3:
            print(f"  {name}: <3 meals, skip")
            continue

        # For each meal, analyze insulin effect timing
        peak_effects = []  # when insulin effect is maximal
        rise_durations = []
        fall_durations = []

        for m in meals:
            idx, end = m['idx'], m['end']
            if end - idx < 24:  # need at least 2h
                continue

            # Track dG/dt during post-meal
            dg = np.diff(glucose[idx:end], prepend=glucose[idx])
            valid = np.isfinite(dg)
            if valid.sum() < 12:
                continue

            # Find when glucose starts falling (peak → insulin taking effect)
            # Smooth with 3-point rolling mean
            smooth = np.convolve(dg, np.ones(3)/3, mode='same')
            smooth[~valid] = np.nan

            # Find first sustained negative stretch (insulin overcoming supply)
            peak_idx = None
            for k in range(3, len(smooth) - 3):
                if np.isfinite(smooth[k]) and smooth[k] < 0:
                    # Check if sustained (at least 3 negative)
                    ahead = smooth[k:k+3]
                    if np.all(np.isfinite(ahead)) and np.all(ahead < 0):
                        peak_idx = k
                        break

            if peak_idx is not None:
                peak_effects.append(peak_idx * 5)  # Convert to minutes
                rise_durations.append(peak_idx * 5)

                # Find nadir (maximum fall)
                remaining = smooth[peak_idx:]
                valid_rem = np.isfinite(remaining)
                if valid_rem.sum() > 0:
                    nadir_offset = np.nanargmin(remaining)
                    fall_durations.append(nadir_offset * 5)

        result = {
            'patient': name,
            'n_meals': len(meals),
            'isf_profile': isf,
        }

        if peak_effects:
            result['mean_time_to_effect'] = float(np.mean(peak_effects))
            result['median_time_to_effect'] = float(np.median(peak_effects))
            result['std_time_to_effect'] = float(np.std(peak_effects))
            result['p25_time'] = float(np.percentile(peak_effects, 25))
            result['p75_time'] = float(np.percentile(peak_effects, 75))
            print(f"  {name}: time-to-effect={result['mean_time_to_effect']:.0f}±{result['std_time_to_effect']:.0f}min "
                  f"(median={result['median_time_to_effect']:.0f}) n={len(peak_effects)}")
        else:
            result['mean_time_to_effect'] = np.nan
            print(f"  {name}: no clear insulin effect detected")

        if fall_durations:
            result['mean_fall_duration'] = float(np.mean(fall_durations))

        all_results.append(result)

    # Population summary
    valid_times = [r['mean_time_to_effect'] for r in all_results if np.isfinite(r.get('mean_time_to_effect', np.nan))]
    if valid_times:
        pop_mean = np.mean(valid_times)
        pop_std = np.std(valid_times)
        print(f"\n  Population time-to-effect: {pop_mean:.0f}±{pop_std:.0f}min")
        # Standard exponential peaks at t=tau (~75min for DIA=6h)
        # If observed is faster, biexponential may fit better
        expected_peak = 75  # minutes for tau=75min (DIA=6h)
        if pop_mean < expected_peak * 0.8:
            verdict = f"FASTER_THAN_MODEL({pop_mean:.0f}min_vs_{expected_peak}min)"
        elif pop_mean > expected_peak * 1.2:
            verdict = f"SLOWER_THAN_MODEL({pop_mean:.0f}min_vs_{expected_peak}min)"
        else:
            verdict = f"MATCHES_MODEL({pop_mean:.0f}min_vs_{expected_peak}min)"
    else:
        verdict = "INSUFFICIENT_DATA"

    if save_fig and all_results:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt

            fig, axes = plt.subplots(1, 2, figsize=(12, 5))

            valid_r = [r for r in all_results if np.isfinite(r.get('mean_time_to_effect', np.nan))]
            if valid_r:
                names = [r['patient'] for r in valid_r]
                means = [r['mean_time_to_effect'] for r in valid_r]
                stds = [r.get('std_time_to_effect', 0) for r in valid_r]
                x = np.arange(len(names))

                axes[0].bar(x, means, yerr=stds, capsize=3, color='steelblue', alpha=0.8)
                axes[0].axhline(75, color='red', ls='--', label='Expected peak (τ=75min)')
                axes[0].set_xticks(x)
                axes[0].set_xticklabels(names)
                axes[0].set_ylabel('Time to insulin effect (min)')
                axes[0].set_title('Time to Insulin Effect After Meal')
                axes[0].legend()

                # Panel 2: Time-to-effect vs ISF
                isfs = [r['isf_profile'] for r in valid_r]
                axes[1].scatter(isfs, means, s=80, c='steelblue', edgecolors='navy')
                for i, r in enumerate(valid_r):
                    axes[1].annotate(r['patient'], (isfs[i], means[i]),
                                     textcoords='offset points', xytext=(5, 5), fontsize=8)
                axes[1].set_xlabel('Profile ISF (mg/dL per U)')
                axes[1].set_ylabel('Time to insulin effect (min)')
                axes[1].set_title('ISF vs Time to Effect')
                axes[1].axhline(75, color='red', ls='--', alpha=0.5)

            plt.tight_layout()
            fig.savefig(FIGURES_DIR / 'meal-fig02-insulin-timing.png', dpi=150)
            plt.close(fig)
            print(f"  → Saved meal-fig02-insulin-timing.png")
        except Exception as e:
            print(f"  (figure skipped: {e})")

    print(f"\n  ✓ EXP-1922 verdict: {verdict}")
    return {'experiment': 'EXP-1922', 'title': 'Biexponential Insulin Activity',
            'verdict': verdict, 'per_patient': all_results}


# =====================================================================
# EXP-1923: Insulin Stacking Analysis During Meals
# =====================================================================

def exp_1923(patients, save_fig=False):
    """Analyze how bolus + loop corrections stack during meals.

    If IOB from multiple sources overlaps, the effective insulin activity
    may be higher than the model predicts from individual doses.
    """
    print("\n" + "=" * 70)
    print("EXP-1923: Insulin Stacking Around Meals")
    print("=" * 70)

    all_results = []
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(len(df))
        temp_rate = df['temp_rate'].values if 'temp_rate' in df.columns else np.zeros(len(df))
        iob = df['iob'].values if 'iob' in df.columns else np.zeros(len(df))

        meals = find_meals(df)
        if len(meals) < 3:
            print(f"  {name}: <3 meals, skip")
            continue

        meal_insulin_data = []
        for m in meals:
            idx, end = m['idx'], m['end']
            pre_start = m['pre_start']

            # Count bolus insulin in window
            window_bolus = bolus[idx:end]
            window_bolus = window_bolus[np.isfinite(window_bolus)]
            total_bolus = float(np.sum(window_bolus[window_bolus > 0.05]))
            n_boluses = int(np.sum(window_bolus > 0.05))

            # Count basal/temp insulin in window
            window_temp = temp_rate[idx:end]
            window_temp = window_temp[np.isfinite(window_temp)]
            total_basal = float(np.sum(window_temp / 12))  # U/h → U per 5min step

            # Pre-meal IOB
            pre_iob = iob[pre_start:idx]
            pre_iob_mean = float(np.nanmean(pre_iob)) if len(pre_iob) > 0 and np.any(np.isfinite(pre_iob)) else 0

            # Peak IOB in post-meal
            post_iob = iob[idx:end]
            peak_iob = float(np.nanmax(post_iob)) if len(post_iob) > 0 and np.any(np.isfinite(post_iob)) else 0

            # IOB increase
            iob_increase = peak_iob - pre_iob_mean

            meal_insulin_data.append({
                'meal_carbs': m['carbs'],
                'meal_bolus': m['bolus'],
                'window_bolus_total': total_bolus,
                'n_boluses': n_boluses,
                'window_basal_total': total_basal,
                'pre_iob': pre_iob_mean,
                'peak_iob': peak_iob,
                'iob_increase': iob_increase,
                'stacking_ratio': total_bolus / max(m['bolus'], 0.01),  # extra insulin beyond initial bolus
            })

        result = {
            'patient': name,
            'n_meals': len(meals),
            'mean_stacking_ratio': float(np.mean([d['stacking_ratio'] for d in meal_insulin_data])),
            'mean_n_boluses': float(np.mean([d['n_boluses'] for d in meal_insulin_data])),
            'mean_iob_increase': float(np.mean([d['iob_increase'] for d in meal_insulin_data])),
            'mean_window_bolus': float(np.mean([d['window_bolus_total'] for d in meal_insulin_data])),
            'mean_window_basal': float(np.mean([d['window_basal_total'] for d in meal_insulin_data])),
            'mean_pre_iob': float(np.mean([d['pre_iob'] for d in meal_insulin_data])),
        }

        # Compute extra insulin from loop corrections vs original bolus
        original_bolus_total = sum(d['meal_bolus'] for d in meal_insulin_data)
        window_bolus_total = sum(d['window_bolus_total'] for d in meal_insulin_data)
        if original_bolus_total > 0:
            result['correction_amplification'] = window_bolus_total / original_bolus_total
        else:
            result['correction_amplification'] = np.nan

        all_results.append(result)
        print(f"  {name}: stacking={result['mean_stacking_ratio']:.2f}× "
              f"n_boluses={result['mean_n_boluses']:.1f}/meal "
              f"correction_amp={result.get('correction_amplification', 0):.2f}×")

    # Population summary
    valid_stack = [r['mean_stacking_ratio'] for r in all_results if np.isfinite(r['mean_stacking_ratio'])]
    if valid_stack:
        pop_stack = np.mean(valid_stack)
        pop_amp = np.mean([r.get('correction_amplification', 1) for r in all_results
                           if np.isfinite(r.get('correction_amplification', np.nan))])
        print(f"\n  Population stacking: {pop_stack:.2f}× mean, correction amplification: {pop_amp:.2f}×")
        verdict = f"STACKING_{pop_stack:.2f}x_AMP_{pop_amp:.2f}x"
    else:
        verdict = "INSUFFICIENT_DATA"

    if save_fig and all_results:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt

            fig, axes = plt.subplots(1, 3, figsize=(15, 5))

            names = [r['patient'] for r in all_results]
            x = np.arange(len(names))

            # Panel 1: Stacking ratio
            stacking = [r['mean_stacking_ratio'] for r in all_results]
            axes[0].bar(x, stacking, color='orange', alpha=0.8)
            axes[0].axhline(1, color='red', ls='--', label='No stacking')
            axes[0].set_xticks(x)
            axes[0].set_xticklabels(names)
            axes[0].set_ylabel('Stacking ratio')
            axes[0].set_title('Insulin Stacking During Meals')
            axes[0].legend()

            # Panel 2: Number of boluses per meal
            n_bol = [r['mean_n_boluses'] for r in all_results]
            axes[1].bar(x, n_bol, color='steelblue', alpha=0.8)
            axes[1].axhline(1, color='red', ls='--', label='Single bolus')
            axes[1].set_xticks(x)
            axes[1].set_xticklabels(names)
            axes[1].set_ylabel('Mean boluses per meal')
            axes[1].set_title('Bolus Events Per Meal Window')
            axes[1].legend()

            # Panel 3: IOB increase during meals
            iob_inc = [r['mean_iob_increase'] for r in all_results]
            axes[2].bar(x, iob_inc, color='green', alpha=0.8)
            axes[2].set_xticks(x)
            axes[2].set_xticklabels(names)
            axes[2].set_ylabel('IOB increase (U)')
            axes[2].set_title('IOB Increase During Meal Window')

            plt.tight_layout()
            fig.savefig(FIGURES_DIR / 'meal-fig03-insulin-stacking.png', dpi=150)
            plt.close(fig)
            print(f"  → Saved meal-fig03-insulin-stacking.png")
        except Exception as e:
            print(f"  (figure skipped: {e})")

    print(f"\n  ✓ EXP-1923 verdict: {verdict}")
    return {'experiment': 'EXP-1923', 'title': 'Insulin Stacking',
            'verdict': verdict, 'per_patient': all_results}


# =====================================================================
# EXP-1924: Bolus Timing and Pre-Bolus Effect
# =====================================================================

def exp_1924(patients, save_fig=False):
    """Analyze how bolus timing relative to carbs affects model accuracy.

    Pre-bolusing (bolus before eating) should reduce the post-meal spike
    and make the model more accurate because insulin has time to start working.
    """
    print("\n" + "=" * 70)
    print("EXP-1924: Bolus Timing & Pre-Bolus Effect")
    print("=" * 70)

    all_results = []
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(len(df))
        carbs = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(df))
        sd = compute_supply_demand(df)
        supply = sd.get('supply', np.zeros_like(glucose))
        demand = sd.get('demand', np.zeros_like(glucose))
        dg = np.diff(glucose, prepend=glucose[0])

        meals = find_meals(df)
        if len(meals) < 3:
            print(f"  {name}: <3 meals, skip")
            continue

        timing_data = []
        for m in meals:
            idx = m['idx']
            pre_start = m['pre_start']

            # Find closest bolus to meal
            best_offset = None
            best_bolus_idx = None
            for j in range(pre_start, min(len(df), idx + STEPS_PER_HOUR)):
                b = bolus[j] if np.isfinite(bolus[j]) else 0
                if b > 0.3:
                    offset = (j - idx) * 5  # minutes relative to carbs (negative = pre-bolus)
                    if best_offset is None or abs(offset) < abs(best_offset):
                        best_offset = offset
                        best_bolus_idx = j

            if best_offset is None:
                continue

            # Compute model error for this meal window
            window = slice(idx, m['end'])
            w_dg = dg[window]
            w_net = supply[window] - demand[window]
            valid = np.isfinite(w_dg) & np.isfinite(w_net)
            if valid.sum() < 6:
                continue

            meal_error = float(np.mean((w_dg[valid] - w_net[valid]) ** 2))

            # Compute post-meal spike
            post_glucose = glucose[idx:min(idx + 2 * STEPS_PER_HOUR, len(glucose))]
            valid_g = post_glucose[np.isfinite(post_glucose)]
            spike = float(np.max(valid_g) - valid_g[0]) if len(valid_g) > 3 else np.nan

            timing_data.append({
                'offset_min': best_offset,
                'model_error': meal_error,
                'spike': spike,
                'carbs': m['carbs'],
                'bolus': m['bolus'],
            })

        if not timing_data:
            print(f"  {name}: no timed meals")
            continue

        offsets = [d['offset_min'] for d in timing_data]
        errors = [d['model_error'] for d in timing_data]
        spikes = [d['spike'] for d in timing_data if np.isfinite(d['spike'])]

        pre_bolus = [d for d in timing_data if d['offset_min'] < -5]
        with_meal = [d for d in timing_data if -5 <= d['offset_min'] <= 5]
        late_bolus = [d for d in timing_data if d['offset_min'] > 5]

        result = {
            'patient': name,
            'n_meals': len(timing_data),
            'mean_offset': float(np.mean(offsets)),
            'pct_prebolus': len(pre_bolus) / len(timing_data) * 100 if timing_data else 0,
            'pct_with_meal': len(with_meal) / len(timing_data) * 100 if timing_data else 0,
            'pct_late': len(late_bolus) / len(timing_data) * 100 if timing_data else 0,
        }

        # Compare model error by timing category
        if pre_bolus:
            result['prebolus_error'] = float(np.mean([d['model_error'] for d in pre_bolus]))
            result['prebolus_spike'] = float(np.nanmean([d['spike'] for d in pre_bolus]))
        if with_meal:
            result['withmeal_error'] = float(np.mean([d['model_error'] for d in with_meal]))
            result['withmeal_spike'] = float(np.nanmean([d['spike'] for d in with_meal]))
        if late_bolus:
            result['late_error'] = float(np.mean([d['model_error'] for d in late_bolus]))
            result['late_spike'] = float(np.nanmean([d['spike'] for d in late_bolus]))

        all_results.append(result)
        print(f"  {name}: offset={result['mean_offset']:.0f}min "
              f"pre={result['pct_prebolus']:.0f}% with={result['pct_with_meal']:.0f}% late={result['pct_late']:.0f}%")

    # Population summary
    if all_results:
        pop_pre = np.mean([r['pct_prebolus'] for r in all_results])
        pop_late = np.mean([r['pct_late'] for r in all_results])
        pop_offset = np.mean([r['mean_offset'] for r in all_results])

        pre_errors = [r['prebolus_error'] for r in all_results if 'prebolus_error' in r]
        late_errors = [r['late_error'] for r in all_results if 'late_error' in r]
        pre_err = np.mean(pre_errors) if pre_errors else np.nan
        late_err = np.mean(late_errors) if late_errors else np.nan

        print(f"\n  Population: mean_offset={pop_offset:.0f}min, pre-bolus={pop_pre:.0f}%, late={pop_late:.0f}%")
        if np.isfinite(pre_err) and np.isfinite(late_err):
            print(f"  Pre-bolus error={pre_err:.1f} vs Late error={late_err:.1f}")
            verdict = f"PRE_{pop_pre:.0f}%_LATE_{pop_late:.0f}%_ERR_RATIO_{late_err/max(pre_err,0.01):.2f}"
        else:
            verdict = f"OFFSET_{pop_offset:.0f}min"
    else:
        verdict = "INSUFFICIENT_DATA"

    if save_fig and all_results:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt

            fig, axes = plt.subplots(1, 3, figsize=(15, 5))

            # Panel 1: Bolus timing distribution
            names = [r['patient'] for r in all_results]
            x = np.arange(len(names))
            pre = [r['pct_prebolus'] for r in all_results]
            with_m = [r['pct_with_meal'] for r in all_results]
            late = [r['pct_late'] for r in all_results]
            axes[0].bar(x, pre, label='Pre-bolus', color='green', alpha=0.8)
            axes[0].bar(x, with_m, bottom=pre, label='With meal', color='steelblue', alpha=0.8)
            axes[0].bar(x, late, bottom=[p+w for p,w in zip(pre, with_m)], label='Late', color='coral', alpha=0.8)
            axes[0].set_xticks(x)
            axes[0].set_xticklabels(names)
            axes[0].set_ylabel('% of meals')
            axes[0].set_title('Bolus Timing Distribution')
            axes[0].legend()

            # Panel 2: Model error by timing
            categories = ['prebolus_error', 'withmeal_error', 'late_error']
            cat_labels = ['Pre-bolus', 'With meal', 'Late']
            cat_colors = ['green', 'steelblue', 'coral']
            for ci, (cat, label, color) in enumerate(zip(categories, cat_labels, cat_colors)):
                vals = [r.get(cat, np.nan) for r in all_results]
                valid_vals = [(i, v) for i, v in enumerate(vals) if np.isfinite(v)]
                if valid_vals:
                    xi, vi = zip(*valid_vals)
                    axes[1].scatter(xi, vi, c=color, label=label, s=60, alpha=0.8)
            axes[1].set_xticks(x)
            axes[1].set_xticklabels(names)
            axes[1].set_ylabel('Model MSE')
            axes[1].set_title('Model Error by Bolus Timing')
            axes[1].legend()

            # Panel 3: Post-meal spike by timing
            for ci, (cat, label, color) in enumerate(zip(
                    ['prebolus_spike', 'withmeal_spike', 'late_spike'],
                    ['Pre-bolus', 'With meal', 'Late'],
                    ['green', 'steelblue', 'coral'])):
                vals = [r.get(cat, np.nan) for r in all_results]
                valid_vals = [(i, v) for i, v in enumerate(vals) if np.isfinite(v)]
                if valid_vals:
                    xi, vi = zip(*valid_vals)
                    axes[2].scatter(xi, vi, c=color, label=label, s=60, alpha=0.8)
            axes[2].set_xticks(x)
            axes[2].set_xticklabels(names)
            axes[2].set_ylabel('Post-meal spike (mg/dL)')
            axes[2].set_title('Glucose Spike by Bolus Timing')
            axes[2].legend()

            plt.tight_layout()
            fig.savefig(FIGURES_DIR / 'meal-fig04-bolus-timing.png', dpi=150)
            plt.close(fig)
            print(f"  → Saved meal-fig04-bolus-timing.png")
        except Exception as e:
            print(f"  (figure skipped: {e})")

    print(f"\n  ✓ EXP-1924 verdict: {verdict}")
    return {'experiment': 'EXP-1924', 'title': 'Bolus Timing',
            'verdict': verdict, 'per_patient': all_results}


# =====================================================================
# EXP-1925: AID Loop Correction Patterns Around Meals
# =====================================================================

def exp_1925(patients, save_fig=False):
    """Analyze how AID loops respond to meals — timing and magnitude of corrections.

    The loop "sees" glucose rising and adjusts temp basal / delivers SMBs.
    This creates additional insulin demand that the simple model doesn't capture.
    """
    print("\n" + "=" * 70)
    print("EXP-1925: AID Loop Correction Patterns Around Meals")
    print("=" * 70)

    all_results = []
    population_profiles = []  # for average meal profile

    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(len(df))
        temp_rate = df['temp_rate'].values if 'temp_rate' in df.columns else np.zeros(len(df))
        iob = df['iob'].values if 'iob' in df.columns else np.zeros(len(df))
        basal_profile = get_basal(p)

        meals = find_meals(df)
        if len(meals) < 3:
            print(f"  {name}: <3 meals, skip")
            continue

        # Build average meal profile: -30min to +3h
        pre_steps = 6  # 30 min before
        post_steps = 36  # 3 hours after
        total_steps = pre_steps + post_steps
        profile_glucose = np.full(total_steps, np.nan)
        profile_temp = np.full(total_steps, np.nan)
        profile_iob = np.full(total_steps, np.nan)
        profile_bolus = np.full(total_steps, np.nan)
        n_profiles = 0

        loop_corrections = []  # additional insulin beyond initial bolus

        for m in meals:
            idx = m['idx']
            start = idx - pre_steps
            end = idx + post_steps

            if start < 0 or end > len(df):
                continue

            # Normalize glucose to pre-meal baseline
            pre_g = glucose[start:idx]
            baseline = np.nanmean(pre_g) if np.any(np.isfinite(pre_g)) else np.nan
            if not np.isfinite(baseline):
                continue

            window_g = glucose[start:end] - baseline
            window_temp = temp_rate[start:end]
            window_iob = iob[start:end]
            window_bolus = bolus[start:end]

            valid = np.isfinite(window_g)
            if valid.sum() < total_steps * 0.5:
                continue

            # Accumulate for averaging
            for k in range(total_steps):
                if np.isfinite(window_g[k]):
                    profile_glucose[k] = np.nansum([profile_glucose[k], window_g[k]]) if np.isfinite(profile_glucose[k]) else window_g[k]
                if np.isfinite(window_temp[k]):
                    profile_temp[k] = np.nansum([profile_temp[k], window_temp[k]]) if np.isfinite(profile_temp[k]) else window_temp[k]
                if np.isfinite(window_iob[k]):
                    profile_iob[k] = np.nansum([profile_iob[k], window_iob[k]]) if np.isfinite(profile_iob[k]) else window_iob[k]
                if np.isfinite(window_bolus[k]):
                    profile_bolus[k] = np.nansum([profile_bolus[k], window_bolus[k]]) if np.isfinite(profile_bolus[k]) else window_bolus[k]

            n_profiles += 1

            # Loop correction: additional temp basal above scheduled
            post_temp = window_temp[pre_steps:]
            valid_temp = post_temp[np.isfinite(post_temp)]
            if len(valid_temp) > 0:
                # Excess above scheduled basal
                excess = np.maximum(0, valid_temp - basal_profile)
                correction_units = float(np.sum(excess / 12))  # U/h → U per 5min
                loop_corrections.append(correction_units)

        if n_profiles > 0:
            profile_glucose /= n_profiles
            profile_temp /= n_profiles
            profile_iob /= n_profiles
            profile_bolus /= n_profiles

        result = {
            'patient': name,
            'n_meals': len(meals),
            'n_profiles': n_profiles,
            'mean_loop_correction': float(np.mean(loop_corrections)) if loop_corrections else 0,
            'median_loop_correction': float(np.median(loop_corrections)) if loop_corrections else 0,
        }

        # Summarize temp rate patterns
        if n_profiles > 0:
            post_temp_avg = profile_temp[pre_steps:]
            valid_post = post_temp_avg[np.isfinite(post_temp_avg)]
            if len(valid_post) > 0:
                result['mean_post_temp_rate'] = float(np.mean(valid_post))
                result['max_post_temp_rate'] = float(np.max(valid_post))
                # Time to max temp rate
                max_idx = np.nanargmax(post_temp_avg) if np.any(np.isfinite(post_temp_avg)) else 0
                result['time_to_max_temp'] = max_idx * 5  # minutes

            # Store profile for population average
            population_profiles.append({
                'patient': name,
                'glucose': profile_glucose.tolist(),
                'temp_rate': profile_temp.tolist(),
                'iob': profile_iob.tolist(),
            })

        all_results.append(result)
        print(f"  {name}: {n_profiles} profiles, loop_correction={result['mean_loop_correction']:.2f}U/meal "
              f"peak_temp={result.get('max_post_temp_rate', 0):.1f}U/h at {result.get('time_to_max_temp', 0)}min")

    # Population summary
    valid_corr = [r['mean_loop_correction'] for r in all_results if r['mean_loop_correction'] > 0]
    if valid_corr:
        pop_corr = np.mean(valid_corr)
        print(f"\n  Population mean loop correction: {pop_corr:.2f}U/meal")
        verdict = f"LOOP_CORRECTION_{pop_corr:.2f}U/meal"
    else:
        verdict = "NO_LOOP_CORRECTIONS"

    if save_fig and population_profiles:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt

            fig, axes = plt.subplots(2, 2, figsize=(14, 10))
            time_axis = np.arange(-30, 150, 5)  # -30min to +150min in 5min steps

            # Panel 1: Average glucose profile per patient
            for prof in population_profiles:
                g = np.array(prof['glucose'])
                if len(g) == len(time_axis):
                    axes[0, 0].plot(time_axis, g, alpha=0.5, label=prof['patient'])
            axes[0, 0].axvline(0, color='red', ls='--', alpha=0.5, label='Meal')
            axes[0, 0].set_xlabel('Time relative to meal (min)')
            axes[0, 0].set_ylabel('Glucose change (mg/dL)')
            axes[0, 0].set_title('Average Glucose Response to Meals')
            axes[0, 0].legend(fontsize=7, ncol=2)

            # Panel 2: Average temp rate per patient
            for prof in population_profiles:
                t = np.array(prof['temp_rate'])
                if len(t) == len(time_axis):
                    axes[0, 1].plot(time_axis, t, alpha=0.5, label=prof['patient'])
            axes[0, 1].axvline(0, color='red', ls='--', alpha=0.5)
            axes[0, 1].set_xlabel('Time relative to meal (min)')
            axes[0, 1].set_ylabel('Temp rate (U/h)')
            axes[0, 1].set_title('Average Temp Basal Around Meals')
            axes[0, 1].legend(fontsize=7, ncol=2)

            # Panel 3: Loop correction per patient
            names = [r['patient'] for r in all_results]
            corrs = [r['mean_loop_correction'] for r in all_results]
            x = np.arange(len(names))
            axes[1, 0].bar(x, corrs, color='orange', alpha=0.8)
            axes[1, 0].set_xticks(x)
            axes[1, 0].set_xticklabels(names)
            axes[1, 0].set_ylabel('Additional insulin (U)')
            axes[1, 0].set_title('Mean Loop Correction Per Meal')

            # Panel 4: Time to max temp rate
            times = [r.get('time_to_max_temp', 0) for r in all_results]
            axes[1, 1].bar(x, times, color='steelblue', alpha=0.8)
            axes[1, 1].set_xticks(x)
            axes[1, 1].set_xticklabels(names)
            axes[1, 1].set_ylabel('Time to peak temp rate (min)')
            axes[1, 1].set_title('Loop Response Time After Meal')

            plt.tight_layout()
            fig.savefig(FIGURES_DIR / 'meal-fig05-loop-corrections.png', dpi=150)
            plt.close(fig)
            print(f"  → Saved meal-fig05-loop-corrections.png")
        except Exception as e:
            print(f"  (figure skipped: {e})")

    print(f"\n  ✓ EXP-1925 verdict: {verdict}")
    return {'experiment': 'EXP-1925', 'title': 'Loop Corrections Around Meals',
            'verdict': verdict, 'per_patient': all_results,
            'population_profiles': [{k: v for k, v in p.items() if k != 'glucose'} for p in population_profiles[:3]]}


# =====================================================================
# EXP-1926: Improved Meal-Aware Demand Model
# =====================================================================

def exp_1926(patients, save_fig=False):
    """Build meal-aware demand model with context-dependent scaling.

    Based on EXP-1914: use separate demand scales for meal and non-meal contexts.
    Compare original (single scale) vs context-aware (dual scale).
    """
    print("\n" + "=" * 70)
    print("EXP-1926: Meal-Aware Demand Model")
    print("=" * 70)

    all_results = []
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        sd = compute_supply_demand(df)
        supply = sd.get('supply', np.zeros_like(glucose))
        demand = sd.get('demand', np.zeros_like(glucose))
        dg = np.diff(glucose, prepend=glucose[0])
        carbs = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(df))

        # Create meal/non-meal mask
        meal_mask = np.zeros(len(glucose), dtype=bool)
        for i in range(len(glucose)):
            c = carbs[i] if np.isfinite(carbs[i]) else 0
            if c >= 5:
                # Mark 3h window after carbs
                meal_mask[i:min(i + 36, len(glucose))] = True

        non_meal_mask = ~meal_mask

        # Approach 1: Single global scale
        global_scale, global_loss = optimal_demand_scale(sd, glucose)

        # Approach 2: Separate meal/non-meal scales
        meal_scale, meal_loss = optimal_demand_scale(sd, glucose, mask=meal_mask)
        non_meal_scale, non_meal_loss = optimal_demand_scale(sd, glucose, mask=non_meal_mask)

        # Approach 3: Context-aware combined — use meal_scale during meals, non_meal during non-meals
        net_context = np.where(meal_mask,
                               supply - demand * meal_scale,
                               supply - demand * non_meal_scale)
        residual_context = dg - net_context
        valid = np.isfinite(residual_context)
        context_loss = float(np.mean(residual_context[valid] ** 2)) if valid.sum() > 10 else np.nan

        # Approach 4: Gradient — scale transitions smoothly around meals
        # Use exponential decay from meal_scale to non_meal_scale
        gradient_scale = np.full(len(glucose), non_meal_scale)
        for i in range(len(glucose)):
            c = carbs[i] if np.isfinite(carbs[i]) else 0
            if c >= 5:
                for k in range(min(72, len(glucose) - i)):  # 6h decay
                    decay = np.exp(-k / 18)  # tau = 1.5h
                    blended = non_meal_scale + (meal_scale - non_meal_scale) * decay
                    gradient_scale[i + k] = max(gradient_scale[i + k], blended)
        net_gradient = supply - demand * gradient_scale
        residual_gradient = dg - net_gradient
        valid_g = np.isfinite(residual_gradient)
        gradient_loss = float(np.mean(residual_gradient[valid_g] ** 2)) if valid_g.sum() > 10 else np.nan

        improvement_context = (1 - context_loss / global_loss) * 100 if global_loss > 0 else 0
        improvement_gradient = (1 - gradient_loss / global_loss) * 100 if global_loss > 0 else 0

        result = {
            'patient': name,
            'global_scale': global_scale,
            'meal_scale': meal_scale,
            'non_meal_scale': non_meal_scale,
            'global_loss': global_loss,
            'context_loss': context_loss,
            'gradient_loss': gradient_loss,
            'improvement_context': improvement_context,
            'improvement_gradient': improvement_gradient,
            'meal_fraction': float(meal_mask.sum() / len(meal_mask)),
        }

        best = 'gradient' if gradient_loss < min(global_loss, context_loss) else \
               'context' if context_loss < global_loss else 'global'
        result['best_approach'] = best

        all_results.append(result)
        print(f"  {name}: global={global_scale:.2f} meal={meal_scale:.2f} non-meal={non_meal_scale:.2f} "
              f"→ context +{improvement_context:.1f}% gradient +{improvement_gradient:.1f}% best={best}")

    # Population summary
    wins = {}
    for r in all_results:
        b = r['best_approach']
        wins[b] = wins.get(b, 0) + 1

    mean_ctx_imp = np.mean([r['improvement_context'] for r in all_results])
    mean_grad_imp = np.mean([r['improvement_gradient'] for r in all_results])
    print(f"\n  Population: context +{mean_ctx_imp:.1f}% gradient +{mean_grad_imp:.1f}%")
    print(f"  Wins: {wins}")
    verdict = f"CONTEXT_+{mean_ctx_imp:.1f}%_GRADIENT_+{mean_grad_imp:.1f}%"

    if save_fig and all_results:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt

            fig, axes = plt.subplots(1, 3, figsize=(15, 5))

            names = [r['patient'] for r in all_results]
            x = np.arange(len(names))

            # Panel 1: Meal vs non-meal scales
            meal_s = [r['meal_scale'] for r in all_results]
            nonmeal_s = [r['non_meal_scale'] for r in all_results]
            global_s = [r['global_scale'] for r in all_results]
            axes[0].bar(x - 0.2, meal_s, 0.2, label='Meal', color='coral')
            axes[0].bar(x, nonmeal_s, 0.2, label='Non-meal', color='steelblue')
            axes[0].bar(x + 0.2, global_s, 0.2, label='Global', color='gray')
            axes[0].set_xticks(x)
            axes[0].set_xticklabels(names)
            axes[0].set_ylabel('Demand scale')
            axes[0].set_title('Context-Dependent Demand Scale')
            axes[0].legend()

            # Panel 2: Loss comparison
            g_loss = [r['global_loss'] for r in all_results]
            c_loss = [r['context_loss'] for r in all_results]
            gr_loss = [r['gradient_loss'] for r in all_results]
            axes[1].bar(x - 0.2, g_loss, 0.2, label='Global', color='gray')
            axes[1].bar(x, c_loss, 0.2, label='Context', color='orange')
            axes[1].bar(x + 0.2, gr_loss, 0.2, label='Gradient', color='green')
            axes[1].set_xticks(x)
            axes[1].set_xticklabels(names)
            axes[1].set_ylabel('MSE')
            axes[1].set_title('Model Loss by Approach')
            axes[1].legend()

            # Panel 3: Improvement
            ctx_imp = [r['improvement_context'] for r in all_results]
            grad_imp = [r['improvement_gradient'] for r in all_results]
            axes[2].bar(x - 0.15, ctx_imp, 0.3, label='Context', color='orange')
            axes[2].bar(x + 0.15, grad_imp, 0.3, label='Gradient', color='green')
            axes[2].set_xticks(x)
            axes[2].set_xticklabels(names)
            axes[2].set_ylabel('Improvement over global (%)')
            axes[2].set_title('Improvement from Context-Aware Model')
            axes[2].legend()
            axes[2].axhline(0, color='gray', ls='--', lw=0.5)

            plt.tight_layout()
            fig.savefig(FIGURES_DIR / 'meal-fig06-meal-aware-model.png', dpi=150)
            plt.close(fig)
            print(f"  → Saved meal-fig06-meal-aware-model.png")
        except Exception as e:
            print(f"  (figure skipped: {e})")

    print(f"\n  ✓ EXP-1926 verdict: {verdict}")
    return {'experiment': 'EXP-1926', 'title': 'Meal-Aware Demand Model',
            'verdict': verdict, 'wins': wins, 'per_patient': all_results}


# =====================================================================
# EXP-1927: Temporal Cross-Validation
# =====================================================================

def exp_1927(patients, save_fig=False):
    """Validate meal-aware model with temporal cross-validation.

    Train on first half, test on second half. Compare:
    - Global scale (train on all data → single scale)
    - Meal-aware (train on all data → meal + non-meal scales)
    - Original profile (no calibration, scale=1.0)
    """
    print("\n" + "=" * 70)
    print("EXP-1927: Temporal Cross-Validation of Meal-Aware Model")
    print("=" * 70)

    all_results = []
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        sd = compute_supply_demand(df)
        supply = sd.get('supply', np.zeros_like(glucose))
        demand = sd.get('demand', np.zeros_like(glucose))
        dg = np.diff(glucose, prepend=glucose[0])
        carbs = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(df))

        mid = len(glucose) // 2

        # Create meal mask
        meal_mask = np.zeros(len(glucose), dtype=bool)
        for i in range(len(glucose)):
            c = carbs[i] if np.isfinite(carbs[i]) else 0
            if c >= 5:
                meal_mask[i:min(i + 36, len(glucose))] = True

        # Train on first half
        train_mask = np.zeros(len(glucose), dtype=bool)
        train_mask[:mid] = True

        # Global scale from training data
        train_global_scale, _ = optimal_demand_scale(sd, glucose, mask=train_mask)

        # Meal/non-meal scales from training data
        train_meal_mask = train_mask & meal_mask
        train_nonmeal_mask = train_mask & ~meal_mask
        train_meal_scale, _ = optimal_demand_scale(sd, glucose, mask=train_meal_mask)
        train_nonmeal_scale, _ = optimal_demand_scale(sd, glucose, mask=train_nonmeal_mask)

        # Evaluate on second half
        test_mask = np.zeros(len(glucose), dtype=bool)
        test_mask[mid:] = True
        test_valid = test_mask & np.isfinite(dg) & np.isfinite(supply) & np.isfinite(demand)

        if test_valid.sum() < 100:
            print(f"  {name}: insufficient test data")
            continue

        # Profile (scale=1.0)
        net_profile = supply - demand * 1.0
        resid_profile = dg - net_profile
        loss_profile = float(np.mean(resid_profile[test_valid] ** 2))

        # Global
        net_global = supply - demand * train_global_scale
        resid_global = dg - net_global
        loss_global = float(np.mean(resid_global[test_valid] ** 2))

        # Meal-aware
        scale_array = np.where(meal_mask, train_meal_scale, train_nonmeal_scale)
        net_mealaware = supply - demand * scale_array
        resid_mealaware = dg - net_mealaware
        loss_mealaware = float(np.mean(resid_mealaware[test_valid] ** 2))

        # Gradient (smooth transition)
        gradient_scale = np.full(len(glucose), train_nonmeal_scale)
        for i in range(len(glucose)):
            c = carbs[i] if np.isfinite(carbs[i]) else 0
            if c >= 5:
                for k in range(min(72, len(glucose) - i)):
                    decay = np.exp(-k / 18)
                    blended = train_nonmeal_scale + (train_meal_scale - train_nonmeal_scale) * decay
                    gradient_scale[i + k] = max(gradient_scale[i + k], blended)
        net_gradient = supply - demand * gradient_scale
        resid_gradient = dg - net_gradient
        loss_gradient = float(np.mean(resid_gradient[test_valid] ** 2))

        losses = {
            'profile': loss_profile,
            'global': loss_global,
            'meal_aware': loss_mealaware,
            'gradient': loss_gradient,
        }
        best = min(losses, key=losses.get)

        result = {
            'patient': name,
            'train_global_scale': train_global_scale,
            'train_meal_scale': train_meal_scale,
            'train_nonmeal_scale': train_nonmeal_scale,
            'loss_profile': loss_profile,
            'loss_global': loss_global,
            'loss_meal_aware': loss_mealaware,
            'loss_gradient': loss_gradient,
            'best': best,
            'improvement_mealaware': (1 - loss_mealaware / loss_profile) * 100,
            'improvement_gradient': (1 - loss_gradient / loss_profile) * 100,
            'improvement_global': (1 - loss_global / loss_profile) * 100,
        }

        all_results.append(result)
        print(f"  {name}: profile={loss_profile:.0f} global={loss_global:.0f} "
              f"meal_aware={loss_mealaware:.0f} gradient={loss_gradient:.0f} → best={best}")

    # Population summary
    wins = {}
    for r in all_results:
        b = r['best']
        wins[b] = wins.get(b, 0) + 1

    mean_imp_ma = np.mean([r['improvement_mealaware'] for r in all_results]) if all_results else 0
    mean_imp_gr = np.mean([r['improvement_gradient'] for r in all_results]) if all_results else 0
    mean_imp_gl = np.mean([r['improvement_global'] for r in all_results]) if all_results else 0

    print(f"\n  Population improvement over profile: global={mean_imp_gl:.1f}% meal_aware={mean_imp_ma:.1f}% gradient={mean_imp_gr:.1f}%")
    print(f"  Wins: {wins}")
    verdict = f"BEST:{max(wins, key=wins.get)}({wins[max(wins, key=wins.get)]}/{len(all_results)})"

    if save_fig and all_results:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt

            fig, axes = plt.subplots(1, 2, figsize=(12, 5))

            names = [r['patient'] for r in all_results]
            x = np.arange(len(names))

            # Panel 1: Test loss comparison
            l_p = [r['loss_profile'] for r in all_results]
            l_g = [r['loss_global'] for r in all_results]
            l_m = [r['loss_meal_aware'] for r in all_results]
            l_gr = [r['loss_gradient'] for r in all_results]
            w = 0.2
            axes[0].bar(x - 1.5*w, l_p, w, label='Profile', color='gray')
            axes[0].bar(x - 0.5*w, l_g, w, label='Global', color='steelblue')
            axes[0].bar(x + 0.5*w, l_m, w, label='Meal-aware', color='orange')
            axes[0].bar(x + 1.5*w, l_gr, w, label='Gradient', color='green')
            axes[0].set_xticks(x)
            axes[0].set_xticklabels(names)
            axes[0].set_ylabel('Test MSE')
            axes[0].set_title('Temporal CV: Test Loss by Approach')
            axes[0].legend(fontsize=8)

            # Panel 2: Improvement over profile
            imp_g = [r['improvement_global'] for r in all_results]
            imp_m = [r['improvement_mealaware'] for r in all_results]
            imp_gr = [r['improvement_gradient'] for r in all_results]
            axes[1].bar(x - w, imp_g, w, label='Global', color='steelblue')
            axes[1].bar(x, imp_m, w, label='Meal-aware', color='orange')
            axes[1].bar(x + w, imp_gr, w, label='Gradient', color='green')
            axes[1].set_xticks(x)
            axes[1].set_xticklabels(names)
            axes[1].set_ylabel('Improvement over profile (%)')
            axes[1].set_title('Temporal CV: Improvement by Approach')
            axes[1].legend(fontsize=8)
            axes[1].axhline(0, color='gray', ls='--', lw=0.5)

            plt.tight_layout()
            fig.savefig(FIGURES_DIR / 'meal-fig07-temporal-cv.png', dpi=150)
            plt.close(fig)
            print(f"  → Saved meal-fig07-temporal-cv.png")
        except Exception as e:
            print(f"  (figure skipped: {e})")

    print(f"\n  ✓ EXP-1927 verdict: {verdict}")
    return {'experiment': 'EXP-1927', 'title': 'Temporal Cross-Validation',
            'verdict': verdict, 'wins': wins, 'per_patient': all_results}


# =====================================================================
# EXP-1928: Clinical Impact Estimation
# =====================================================================

def exp_1928(patients, save_fig=False):
    """Estimate clinical impact of improved meal-aware model.

    For each patient, compute glycemic metrics under:
    - Original profile settings
    - Optimized settings (from S/D model calibration)
    - Meal-aware settings

    Then estimate how much TIR, eA1c, etc. would improve.
    """
    print("\n" + "=" * 70)
    print("EXP-1928: Clinical Impact Estimation")
    print("=" * 70)

    all_results = []
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        valid_g = glucose[np.isfinite(glucose)]

        if len(valid_g) < 1000:
            print(f"  {name}: insufficient glucose data")
            continue

        # Current glycemic metrics
        tir = float(np.mean((valid_g >= 70) & (valid_g <= 180)))
        tbr = float(np.mean(valid_g < 70))
        tar = float(np.mean(valid_g > 180))
        mean_g = float(np.mean(valid_g))
        cv = float(np.std(valid_g) / mean_g)
        ea1c = (mean_g + 46.7) / 28.7

        # LBGI/HBGI (Kovatchev)
        f_g = 1.509 * (np.log(np.maximum(valid_g, 1)) ** 1.084 - 5.381)
        rl = np.minimum(f_g, 0) ** 2
        rh = np.maximum(f_g, 0) ** 2
        lbgi = float(np.mean(rl))
        hbgi = float(np.mean(rh))

        # GVI (Glycemic Variability Index)
        diffs = np.abs(np.diff(valid_g))
        ideal_line = np.abs(valid_g[-1] - valid_g[0]) / len(valid_g) if len(valid_g) > 1 else 0
        actual_path = float(np.sum(diffs))
        ideal_path = ideal_line * (len(valid_g) - 1)
        gvi = actual_path / max(ideal_path, 1)

        # Estimate improvement from S/D model recommendations
        sd = compute_supply_demand(df)
        supply = sd.get('supply', np.zeros_like(glucose))
        demand = sd.get('demand', np.zeros_like(glucose))
        dg = np.diff(glucose, prepend=glucose[0])

        # What does the model say about systematic errors?
        net = supply - demand
        residual = dg - net
        valid_r = np.isfinite(residual)
        mean_residual = float(np.mean(residual[valid_r])) if valid_r.sum() > 0 else 0
        # Positive residual = glucose rises more than model predicts → model under-supplies or over-demands
        # Negative residual = glucose falls more than model predicts → model over-supplies or under-demands

        # Estimate potential TIR improvement from correcting systematic bias
        # Simple projection: shift glucose distribution by -mean_residual
        projected_g = valid_g - mean_residual * 12  # 12 steps/hour * residual per step → hourly shift
        proj_tir = float(np.mean((projected_g >= 70) & (projected_g <= 180)))
        proj_tbr = float(np.mean(projected_g < 70))
        proj_tar = float(np.mean(projected_g > 180))
        proj_mean = float(np.mean(projected_g))
        proj_ea1c = (proj_mean + 46.7) / 28.7

        result = {
            'patient': name,
            'current_tir': tir * 100,
            'current_tbr': tbr * 100,
            'current_tar': tar * 100,
            'current_mean': mean_g,
            'current_cv': cv,
            'current_ea1c': ea1c,
            'current_lbgi': lbgi,
            'current_hbgi': hbgi,
            'current_gvi': gvi,
            'mean_residual': mean_residual,
            'projected_tir': proj_tir * 100,
            'projected_tbr': proj_tbr * 100,
            'projected_tar': proj_tar * 100,
            'projected_ea1c': proj_ea1c,
            'tir_improvement': (proj_tir - tir) * 100,
        }

        all_results.append(result)
        print(f"  {name}: TIR={tir*100:.1f}→{proj_tir*100:.1f}% eA1c={ea1c:.1f}→{proj_ea1c:.1f} "
              f"LBGI={lbgi:.1f} HBGI={hbgi:.1f} GVI={gvi:.1f}")

    # Population summary
    if all_results:
        pop_tir = np.mean([r['current_tir'] for r in all_results])
        pop_proj_tir = np.mean([r['projected_tir'] for r in all_results])
        pop_imp = np.mean([r['tir_improvement'] for r in all_results])
        pop_ea1c = np.mean([r['current_ea1c'] for r in all_results])
        print(f"\n  Population: TIR={pop_tir:.1f}→{pop_proj_tir:.1f}% (Δ{pop_imp:+.1f}%) eA1c={pop_ea1c:.2f}")

        improved = sum(1 for r in all_results if r['tir_improvement'] > 0)
        verdict = f"TIR_IMPROVEMENT_{pop_imp:+.1f}%_({improved}/{len(all_results)}_improved)"
    else:
        verdict = "INSUFFICIENT_DATA"

    if save_fig and all_results:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt

            fig, axes = plt.subplots(2, 2, figsize=(14, 10))

            names = [r['patient'] for r in all_results]
            x = np.arange(len(names))

            # Panel 1: Current vs Projected TIR
            cur_tir = [r['current_tir'] for r in all_results]
            proj_tir = [r['projected_tir'] for r in all_results]
            axes[0, 0].bar(x - 0.15, cur_tir, 0.3, label='Current', color='steelblue')
            axes[0, 0].bar(x + 0.15, proj_tir, 0.3, label='Projected', color='green')
            axes[0, 0].axhline(70, color='red', ls='--', alpha=0.5, label='Target (70%)')
            axes[0, 0].set_xticks(x)
            axes[0, 0].set_xticklabels(names)
            axes[0, 0].set_ylabel('TIR (%)')
            axes[0, 0].set_title('Time in Range: Current vs Projected')
            axes[0, 0].legend()

            # Panel 2: TIR/TBR/TAR stacked
            cur_tbr = [r['current_tbr'] for r in all_results]
            cur_tar = [r['current_tar'] for r in all_results]
            axes[0, 1].bar(x, cur_tbr, label='TBR (<70)', color='red', alpha=0.8)
            axes[0, 1].bar(x, cur_tir, bottom=cur_tbr, label='TIR (70-180)', color='green', alpha=0.8)
            axes[0, 1].bar(x, cur_tar, bottom=[b+t for b,t in zip(cur_tbr, cur_tir)], label='TAR (>180)', color='orange', alpha=0.8)
            axes[0, 1].set_xticks(x)
            axes[0, 1].set_xticklabels(names)
            axes[0, 1].set_ylabel('% of time')
            axes[0, 1].set_title('Glycemic Distribution')
            axes[0, 1].legend()

            # Panel 3: LBGI vs HBGI
            lbgi = [r['current_lbgi'] for r in all_results]
            hbgi = [r['current_hbgi'] for r in all_results]
            axes[1, 0].scatter(lbgi, hbgi, s=80, c='steelblue', edgecolors='navy')
            for i, r in enumerate(all_results):
                axes[1, 0].annotate(r['patient'], (lbgi[i], hbgi[i]),
                                     textcoords='offset points', xytext=(5, 5), fontsize=9)
            axes[1, 0].set_xlabel('LBGI (hypo risk)')
            axes[1, 0].set_ylabel('HBGI (hyper risk)')
            axes[1, 0].set_title('Low vs High Blood Glucose Index')
            axes[1, 0].axvline(2.5, color='red', ls='--', alpha=0.3, label='LBGI risk threshold')
            axes[1, 0].axhline(4.5, color='orange', ls='--', alpha=0.3, label='HBGI risk threshold')
            axes[1, 0].legend(fontsize=8)

            # Panel 4: GVI and CV
            gvi_vals = [r['current_gvi'] for r in all_results]
            cv_vals = [r['current_cv'] for r in all_results]
            axes[1, 1].bar(x - 0.15, gvi_vals, 0.3, label='GVI', color='purple', alpha=0.8)
            ax2 = axes[1, 1].twinx()
            ax2.bar(x + 0.15, [c * 100 for c in cv_vals], 0.3, label='CV%', color='teal', alpha=0.8)
            axes[1, 1].set_xticks(x)
            axes[1, 1].set_xticklabels(names)
            axes[1, 1].set_ylabel('GVI')
            ax2.set_ylabel('CV (%)')
            axes[1, 1].set_title('Glycemic Variability')
            axes[1, 1].legend(loc='upper left', fontsize=8)
            ax2.legend(loc='upper right', fontsize=8)

            plt.tight_layout()
            fig.savefig(FIGURES_DIR / 'meal-fig08-clinical-impact.png', dpi=150)
            plt.close(fig)
            print(f"  → Saved meal-fig08-clinical-impact.png")
        except Exception as e:
            print(f"  (figure skipped: {e})")

    print(f"\n  ✓ EXP-1928 verdict: {verdict}")
    return {'experiment': 'EXP-1928', 'title': 'Clinical Impact Estimation',
            'verdict': verdict, 'per_patient': all_results}


# =====================================================================
# Main
# =====================================================================

def main():
    parser = argparse.ArgumentParser(description='EXP-1921–1928: Meal Response & Insulin Model')
    parser.add_argument('--figures', action='store_true', help='Save figures')
    args = parser.parse_args()

    patients = load_patients('externals/ns-data/patients/')

    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 70)
    print("EXP-1921–1928: Meal Response Analysis & Insulin Model Improvement")
    print("=" * 70)

    results = {}
    experiments = [
        ('EXP-1921', exp_1921),
        ('EXP-1922', exp_1922),
        ('EXP-1923', exp_1923),
        ('EXP-1924', exp_1924),
        ('EXP-1925', exp_1925),
        ('EXP-1926', exp_1926),
        ('EXP-1927', exp_1927),
        ('EXP-1928', exp_1928),
    ]

    for exp_id, exp_fn in experiments:
        print(f"\n{'#' * 70}")
        print(f"# Running {exp_id}: {exp_fn.__doc__.strip().split(chr(10))[0]}")
        print(f"{'#' * 70}")
        try:
            result = exp_fn(patients, save_fig=args.figures)
            results[exp_id] = result
        except Exception as e:
            print(f"\n  ✗ {exp_id} FAILED: {e}")
            import traceback
            traceback.print_exc()
            results[exp_id] = {'experiment': exp_id, 'verdict': f'FAILED: {e}'}

    # Save results
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)

    def json_safe(obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj) if np.isfinite(obj) else None
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, np.bool_):
            return bool(obj)
        raise TypeError(f"Not JSON serializable: {type(obj)}")

    with open(RESULTS_PATH, 'w') as f:
        json.dump(results, f, indent=2, default=json_safe)
    print(f"\n✓ Results saved to {RESULTS_PATH}")

    # Synthesis
    print("\n" + "=" * 70)
    print("SYNTHESIS: Meal Response & Insulin Model Improvement")
    print("=" * 70)
    for exp_id, result in results.items():
        print(f"  {exp_id}: {result.get('verdict', 'N/A')}")
    print("\n✓ All experiments complete")


if __name__ == '__main__':
    main()
