#!/usr/bin/env python3
"""EXP-1931–1938: Carb Absorption Model Investigation.

EXP-1921 revealed 93% of meal-time model error is supply-side (carb absorption).
This batch investigates the carb absorption model and builds improvements.

Key question: Why does the carb absorption model overestimate glucose appearance?
Hypotheses:
  H1: Absorption rate is too fast (carbs appear too quickly in model)
  H2: Not all logged carbs are absorbed (fiber, overestimation)
  H3: Carb absorption varies by meal size
  H4: Individual absorption rates differ significantly
  H5: Fixing carb absorption revises CR estimates

Experiments:
  EXP-1931: Observed vs modeled glucose rise rates after meals
  EXP-1932: Effective absorption rate fitting per patient
  EXP-1933: Meal-size dependence of absorption rate
  EXP-1934: Individual carb absorption profiles (population variation)
  EXP-1935: Improved carb absorption model with fitted rates
  EXP-1936: Impact on CR estimation (does fixing absorption fix CR?)
  EXP-1937: Temporal validation of improved absorption model
  EXP-1938: Absorption model + gradient demand (combined improvement)
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
RESULTS_PATH = Path('externals/experiments/exp-1931_carb_absorption.json')
STEPS_PER_HOUR = 12
STEPS_PER_DAY = 288

# --- Helpers ---

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

def find_meals(df, min_carbs=5, post_window=36, pre_window=6):
    """Find meal events."""
    carbs = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(df))
    bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(len(df))
    meals = []
    i = 0
    while i < len(df) - post_window:
        c = carbs[i] if np.isfinite(carbs[i]) else 0
        if c >= min_carbs:
            meal_bolus = 0
            for j in range(max(0, i - pre_window), min(len(df), i + post_window // 3)):
                b = bolus[j] if np.isfinite(bolus[j]) else 0
                if b > 0.1:
                    meal_bolus += b
            meals.append({
                'idx': i, 'end': min(i + post_window, len(df)),
                'carbs': c, 'bolus': meal_bolus,
            })
            i += post_window
        else:
            i += 1
    return meals

def optimal_demand_scale(sd, glucose, mask=None, scale_range=(0.01, 5.01), step=0.05):
    """Find optimal demand scale."""
    supply = sd.get('supply', np.zeros_like(glucose))
    demand = sd.get('demand', np.zeros_like(glucose))
    dg = np.diff(glucose, prepend=glucose[0])
    best_scale, best_loss = 1.0, np.inf
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
# EXP-1931: Observed vs Modeled Glucose Rise
# =====================================================================

def exp_1931(patients, save_fig=False):
    """Compare actual glucose rise rate to modeled carb supply in first hour post-meal.

    The model computes carb_supply from carb entries using an absorption curve.
    We compare this to the actual dG/dt during the glucose rise phase.
    """
    print("\n" + "=" * 70)
    print("EXP-1931: Observed vs Modeled Glucose Rise")
    print("=" * 70)

    all_results = []
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        sd = compute_supply_demand(df)
        carb_supply = sd.get('carb_supply', np.zeros_like(glucose))
        supply = sd.get('supply', np.zeros_like(glucose))
        demand = sd.get('demand', np.zeros_like(glucose))
        dg = np.diff(glucose, prepend=glucose[0])

        meals = find_meals(df)
        if len(meals) < 3:
            print(f"  {name}: <3 meals, skip")
            continue

        actual_rises = []
        modeled_supplies = []
        modeled_carb_supplies = []
        supply_ratios = []

        for m in meals:
            idx = m['idx']
            rise_end = min(idx + STEPS_PER_HOUR, len(glucose))

            # Actual glucose rise in first hour
            w_dg = dg[idx:rise_end]
            valid = np.isfinite(w_dg)
            if valid.sum() < 6:
                continue
            actual_rise = float(np.nanmean(w_dg))

            # Modeled carb supply
            w_carb = carb_supply[idx:rise_end]
            w_supply = supply[idx:rise_end]
            w_demand = demand[idx:rise_end]
            modeled_carb = float(np.nanmean(w_carb))
            modeled_total = float(np.nanmean(w_supply))
            modeled_demand_val = float(np.nanmean(w_demand))

            # Net rise should account for demand too
            # Actual = supply - demand + residual
            # So actual_rise + demand ≈ true supply
            implied_supply = actual_rise + modeled_demand_val
            ratio = implied_supply / max(modeled_carb, 0.01) if modeled_carb > 0.01 else np.nan

            actual_rises.append(actual_rise)
            modeled_supplies.append(modeled_total)
            modeled_carb_supplies.append(modeled_carb)
            if np.isfinite(ratio) and ratio > 0 and ratio < 100:
                supply_ratios.append(ratio)

        if not actual_rises:
            print(f"  {name}: no valid meals")
            continue

        result = {
            'patient': name,
            'n_meals': len(actual_rises),
            'mean_actual_rise': float(np.mean(actual_rises)),
            'mean_modeled_supply': float(np.mean(modeled_supplies)),
            'mean_modeled_carb': float(np.mean(modeled_carb_supplies)),
            'overestimation_ratio': float(np.mean(modeled_carb_supplies)) / max(abs(float(np.mean(actual_rises))), 0.01),
        }
        if supply_ratios:
            result['implied_supply_ratio'] = float(np.median(supply_ratios))

        all_results.append(result)
        print(f"  {name}: actual_rise={result['mean_actual_rise']:.2f} modeled_carb={result['mean_modeled_carb']:.2f} "
              f"overest={result['overestimation_ratio']:.2f}×")

    # Population
    valid_r = [r for r in all_results if 'overestimation_ratio' in r]
    if valid_r:
        pop_overest = np.mean([r['overestimation_ratio'] for r in valid_r])
        print(f"\n  Population overestimation ratio: {pop_overest:.2f}×")
        verdict = f"OVERESTIMATION_{pop_overest:.2f}x"
    else:
        verdict = "INSUFFICIENT_DATA"

    if save_fig and valid_r:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            fig, axes = plt.subplots(1, 2, figsize=(12, 5))

            names = [r['patient'] for r in valid_r]
            x = np.arange(len(names))
            actual = [r['mean_actual_rise'] for r in valid_r]
            modeled = [r['mean_modeled_carb'] for r in valid_r]

            axes[0].bar(x - 0.15, actual, 0.3, label='Actual dG/dt', color='steelblue')
            axes[0].bar(x + 0.15, modeled, 0.3, label='Modeled carb supply', color='coral')
            axes[0].set_xticks(x)
            axes[0].set_xticklabels(names)
            axes[0].set_ylabel('mg/dL per 5min')
            axes[0].set_title('Rise Phase: Actual vs Modeled (0-1h)')
            axes[0].legend()
            axes[0].axhline(0, color='gray', ls='--', lw=0.5)

            overest = [r['overestimation_ratio'] for r in valid_r]
            axes[1].bar(x, overest, color='orange')
            axes[1].axhline(1, color='red', ls='--', label='Perfect model')
            axes[1].set_xticks(x)
            axes[1].set_xticklabels(names)
            axes[1].set_ylabel('Overestimation ratio')
            axes[1].set_title('Carb Supply Overestimation')
            axes[1].legend()

            plt.tight_layout()
            fig.savefig(FIGURES_DIR / 'carb-fig01-rise-comparison.png', dpi=150)
            plt.close(fig)
            print(f"  → Saved carb-fig01-rise-comparison.png")
        except Exception as e:
            print(f"  (figure skipped: {e})")

    print(f"\n  ✓ EXP-1931 verdict: {verdict}")
    return {'experiment': 'EXP-1931', 'title': 'Observed vs Modeled Rise',
            'verdict': verdict, 'per_patient': all_results}


# =====================================================================
# EXP-1932: Effective Absorption Rate Fitting
# =====================================================================

def exp_1932(patients, save_fig=False):
    """Fit effective carb absorption rate per patient.

    Model: glucose_rise(t) = carbs × absorption_rate × exp(-t/tau_absorb) / tau_absorb
    Fit tau_absorb to minimize MSE between modeled and actual glucose rise.
    """
    print("\n" + "=" * 70)
    print("EXP-1932: Effective Absorption Rate Fitting")
    print("=" * 70)

    all_results = []
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        carbs_col = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(df))
        dg = np.diff(glucose, prepend=glucose[0])
        sd = compute_supply_demand(df)
        demand = sd.get('demand', np.zeros_like(glucose))

        meals = find_meals(df, min_carbs=10)  # Need substantial meals for fitting
        if len(meals) < 5:
            print(f"  {name}: <5 meals with ≥10g, skip")
            continue

        # Fit tau_absorb using grid search
        best_tau = 30  # minutes
        best_loss = np.inf

        for tau_min in range(10, 121, 5):  # 10 to 120 minutes
            tau_steps = tau_min / 5  # Convert to 5-min steps
            total_err = 0
            n_valid = 0

            for m in meals:
                idx = m['idx']
                end = min(idx + 3 * STEPS_PER_HOUR, len(glucose))  # 3h window
                carb_g = m['carbs']

                # Model: carb absorption with this tau
                t = np.arange(0, end - idx) * 5  # time in minutes
                if tau_min > 0:
                    modeled_rate = carb_g * (t / (tau_min ** 2)) * np.exp(-t / tau_min)
                else:
                    continue

                # Actual dG/dt corrected for insulin demand
                actual = dg[idx:end] + demand[idx:end]  # Add back demand to get supply
                valid = np.isfinite(actual)
                if valid.sum() < 6:
                    continue

                err = np.mean((actual[valid] - modeled_rate[:len(actual)][valid]) ** 2)
                total_err += err
                n_valid += 1

            if n_valid > 0:
                avg_err = total_err / n_valid
                if avg_err < best_loss:
                    best_loss = avg_err
                    best_tau = tau_min

        # Also compute the model's implied tau
        # The default model uses a specific absorption curve; compare
        sd_carb = sd.get('carb_supply', np.zeros_like(glucose))
        # Find typical carb supply peak time
        peak_times = []
        for m in meals:
            idx = m['idx']
            end = min(idx + 3 * STEPS_PER_HOUR, len(glucose))
            cs = sd_carb[idx:end]
            valid = np.isfinite(cs) & (cs > 0.01)
            if valid.sum() > 0:
                peak_idx = np.nanargmax(cs)
                peak_times.append(peak_idx * 5)

        model_peak = float(np.median(peak_times)) if peak_times else np.nan

        result = {
            'patient': name,
            'n_meals': len(meals),
            'fitted_tau': best_tau,
            'fitted_loss': best_loss,
            'model_peak_time': model_peak,
            'fitted_peak_time': best_tau,  # For exponential, peak is at tau
        }

        all_results.append(result)
        print(f"  {name}: fitted_tau={best_tau}min model_peak={model_peak:.0f}min loss={best_loss:.1f}")

    # Population
    if all_results:
        pop_tau = np.mean([r['fitted_tau'] for r in all_results])
        pop_model_peak = np.nanmean([r['model_peak_time'] for r in all_results])
        print(f"\n  Population: fitted_tau={pop_tau:.0f}min vs model_peak={pop_model_peak:.0f}min")
        verdict = f"FITTED_TAU_{pop_tau:.0f}min_vs_MODEL_{pop_model_peak:.0f}min"
    else:
        verdict = "INSUFFICIENT_DATA"

    if save_fig and all_results:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            fig, axes = plt.subplots(1, 2, figsize=(12, 5))

            names = [r['patient'] for r in all_results]
            x = np.arange(len(names))
            fitted = [r['fitted_tau'] for r in all_results]
            model_p = [r['model_peak_time'] for r in all_results]

            axes[0].bar(x - 0.15, fitted, 0.3, label='Fitted τ', color='steelblue')
            axes[0].bar(x + 0.15, model_p, 0.3, label='Model peak', color='coral')
            axes[0].set_xticks(x)
            axes[0].set_xticklabels(names)
            axes[0].set_ylabel('Time (min)')
            axes[0].set_title('Carb Absorption: Fitted vs Model')
            axes[0].legend()

            # Absorption curves comparison
            t = np.arange(0, 180)
            tau_fitted = pop_tau
            tau_model = pop_model_peak if np.isfinite(pop_model_peak) else 30
            curve_fitted = (t / tau_fitted ** 2) * np.exp(-t / tau_fitted) if tau_fitted > 0 else np.zeros_like(t)
            curve_model = (t / tau_model ** 2) * np.exp(-t / tau_model) if tau_model > 0 else np.zeros_like(t)
            axes[1].plot(t, curve_fitted / max(curve_fitted.max(), 1e-6), label=f'Fitted (τ={tau_fitted:.0f}min)', color='steelblue', lw=2)
            axes[1].plot(t, curve_model / max(curve_model.max(), 1e-6), label=f'Model (τ={tau_model:.0f}min)', color='coral', lw=2)
            axes[1].set_xlabel('Time after meal (min)')
            axes[1].set_ylabel('Normalized absorption rate')
            axes[1].set_title('Absorption Curve: Fitted vs Model')
            axes[1].legend()

            plt.tight_layout()
            fig.savefig(FIGURES_DIR / 'carb-fig02-absorption-fitting.png', dpi=150)
            plt.close(fig)
            print(f"  → Saved carb-fig02-absorption-fitting.png")
        except Exception as e:
            print(f"  (figure skipped: {e})")

    print(f"\n  ✓ EXP-1932 verdict: {verdict}")
    return {'experiment': 'EXP-1932', 'title': 'Absorption Rate Fitting',
            'verdict': verdict, 'per_patient': all_results}


# =====================================================================
# EXP-1933: Meal Size Dependence
# =====================================================================

def exp_1933(patients, save_fig=False):
    """Test if absorption rate depends on meal size.

    Larger meals may absorb more slowly due to gastric emptying delays.
    """
    print("\n" + "=" * 70)
    print("EXP-1933: Meal Size vs Absorption Rate")
    print("=" * 70)

    all_data = []
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        dg = np.diff(glucose, prepend=glucose[0])

        meals = find_meals(df, min_carbs=5)
        if len(meals) < 5:
            continue

        for m in meals:
            idx = m['idx']
            carbs = m['carbs']
            end = min(idx + 2 * STEPS_PER_HOUR, len(glucose))  # 2h window

            # Peak rise rate in first 2 hours
            w_dg = dg[idx:end]
            valid = np.isfinite(w_dg)
            if valid.sum() < 6:
                continue

            peak_rise = float(np.nanmax(w_dg))
            mean_rise = float(np.nanmean(w_dg[:STEPS_PER_HOUR]))  # first hour

            # Time to peak glucose
            w_g = glucose[idx:end]
            valid_g = np.isfinite(w_g)
            if valid_g.sum() > 3:
                peak_g_idx = np.nanargmax(w_g)
                time_to_peak = peak_g_idx * 5  # minutes
            else:
                time_to_peak = np.nan

            # Per-gram rise rate
            per_gram = mean_rise / max(carbs, 1)

            all_data.append({
                'patient': name,
                'carbs': carbs,
                'peak_rise': peak_rise,
                'mean_rise': mean_rise,
                'per_gram': per_gram,
                'time_to_peak': time_to_peak,
            })

    if not all_data:
        verdict = "INSUFFICIENT_DATA"
        print(f"\n  ✓ EXP-1933 verdict: {verdict}")
        return {'experiment': 'EXP-1933', 'title': 'Meal Size Dependence', 'verdict': verdict}

    # Bin by meal size
    carbs_arr = np.array([d['carbs'] for d in all_data])
    small = [d for d in all_data if d['carbs'] < 20]
    medium = [d for d in all_data if 20 <= d['carbs'] < 50]
    large = [d for d in all_data if d['carbs'] >= 50]

    results = {
        'total_meals': len(all_data),
        'small_n': len(small),
        'medium_n': len(medium),
        'large_n': len(large),
    }

    for label, group in [('small', small), ('medium', medium), ('large', large)]:
        if group:
            results[f'{label}_mean_rise'] = float(np.mean([d['mean_rise'] for d in group]))
            results[f'{label}_per_gram'] = float(np.mean([d['per_gram'] for d in group]))
            results[f'{label}_time_to_peak'] = float(np.nanmean([d['time_to_peak'] for d in group]))

    # Correlation: carbs vs per-gram rise
    per_grams = np.array([d['per_gram'] for d in all_data])
    valid = np.isfinite(per_grams) & np.isfinite(carbs_arr)
    if valid.sum() > 10:
        corr = np.corrcoef(carbs_arr[valid], per_grams[valid])[0, 1]
        results['carbs_vs_pergram_corr'] = float(corr)
    else:
        corr = np.nan
        results['carbs_vs_pergram_corr'] = None

    # Correlation: carbs vs time to peak
    ttp = np.array([d['time_to_peak'] for d in all_data])
    valid_ttp = np.isfinite(ttp) & np.isfinite(carbs_arr)
    if valid_ttp.sum() > 10:
        corr_ttp = np.corrcoef(carbs_arr[valid_ttp], ttp[valid_ttp])[0, 1]
        results['carbs_vs_ttp_corr'] = float(corr_ttp)
    else:
        corr_ttp = np.nan
        results['carbs_vs_ttp_corr'] = None

    print(f"  Total meals: {len(all_data)}")
    print(f"  Small (<20g, n={len(small)}): per-gram={results.get('small_per_gram', 0):.3f} ttp={results.get('small_time_to_peak', 0):.0f}min")
    print(f"  Medium (20-50g, n={len(medium)}): per-gram={results.get('medium_per_gram', 0):.3f} ttp={results.get('medium_time_to_peak', 0):.0f}min")
    print(f"  Large (>50g, n={len(large)}): per-gram={results.get('large_per_gram', 0):.3f} ttp={results.get('large_time_to_peak', 0):.0f}min")
    print(f"  Carbs vs per-gram corr: r={corr:.3f}")
    print(f"  Carbs vs time-to-peak corr: r={corr_ttp:.3f}")

    if np.isfinite(corr) and abs(corr) > 0.1:
        verdict = f"SIZE_MATTERS(r={corr:.3f}_ttp_r={corr_ttp:.3f})"
    else:
        verdict = f"SIZE_INDEPENDENT(r={corr:.3f})"

    if save_fig:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            fig, axes = plt.subplots(1, 3, figsize=(15, 5))

            # Scatter: carbs vs per-gram rise
            c = [d['carbs'] for d in all_data]
            pg = [d['per_gram'] for d in all_data]
            axes[0].scatter(c, pg, alpha=0.2, s=10, c='steelblue')
            axes[0].set_xlabel('Meal carbs (g)')
            axes[0].set_ylabel('Per-gram rise rate (mg/dL/5min/g)')
            axes[0].set_title(f'Carb Size vs Rise Rate (r={corr:.3f})')

            # Binned comparison
            labels = ['Small\n(<20g)', 'Medium\n(20-50g)', 'Large\n(>50g)']
            pg_means = [results.get(f'{l}_per_gram', 0) for l in ['small', 'medium', 'large']]
            axes[1].bar(range(3), pg_means, color=['green', 'steelblue', 'coral'])
            axes[1].set_xticks(range(3))
            axes[1].set_xticklabels(labels)
            axes[1].set_ylabel('Per-gram rise rate')
            axes[1].set_title('Absorption Efficiency by Meal Size')

            # Time to peak by size
            ttp_means = [results.get(f'{l}_time_to_peak', 0) for l in ['small', 'medium', 'large']]
            axes[2].bar(range(3), ttp_means, color=['green', 'steelblue', 'coral'])
            axes[2].set_xticks(range(3))
            axes[2].set_xticklabels(labels)
            axes[2].set_ylabel('Time to peak glucose (min)')
            axes[2].set_title('Peak Timing by Meal Size')

            plt.tight_layout()
            fig.savefig(FIGURES_DIR / 'carb-fig03-meal-size.png', dpi=150)
            plt.close(fig)
            print(f"  → Saved carb-fig03-meal-size.png")
        except Exception as e:
            print(f"  (figure skipped: {e})")

    print(f"\n  ✓ EXP-1933 verdict: {verdict}")
    return {'experiment': 'EXP-1933', 'title': 'Meal Size Dependence',
            'verdict': verdict, 'data': results}


# =====================================================================
# EXP-1934: Individual Absorption Profiles
# =====================================================================

def exp_1934(patients, save_fig=False):
    """Build average glucose response profile per patient to characterize
    individual carb absorption patterns.
    """
    print("\n" + "=" * 70)
    print("EXP-1934: Individual Carb Absorption Profiles")
    print("=" * 70)

    all_results = []
    profiles = {}

    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        carbs_col = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(df))

        meals = find_meals(df, min_carbs=10)
        if len(meals) < 5:
            print(f"  {name}: <5 meals, skip")
            continue

        # Build normalized average meal response (glucose per gram of carbs)
        response_len = 3 * STEPS_PER_HOUR  # 3h
        accumulated = np.zeros(response_len)
        count = np.zeros(response_len)

        for m in meals:
            idx = m['idx']
            carbs = m['carbs']
            end = min(idx + response_len, len(glucose))

            # Normalize to baseline and per-gram
            baseline = glucose[idx] if np.isfinite(glucose[idx]) else np.nan
            if not np.isfinite(baseline):
                continue

            for k in range(end - idx):
                g = glucose[idx + k]
                if np.isfinite(g):
                    accumulated[k] += (g - baseline) / carbs
                    count[k] += 1

        profile = np.where(count > 0, accumulated / count, np.nan)

        # Characterize profile
        valid = np.isfinite(profile)
        if valid.sum() < 12:
            continue

        peak_val = float(np.nanmax(profile))
        peak_idx = int(np.nanargmax(profile))
        peak_time = peak_idx * 5

        # Time to return to baseline
        after_peak = profile[peak_idx:]
        returned = np.where(np.isfinite(after_peak) & (after_peak <= 0))[0]
        return_time = (peak_idx + returned[0]) * 5 if len(returned) > 0 else 180

        # AUC (area under curve, first 3h)
        auc = float(np.nansum(profile) * 5)  # mg/dL·min per gram

        result = {
            'patient': name,
            'n_meals': len(meals),
            'peak_mg_per_gram': peak_val,
            'peak_time_min': peak_time,
            'return_time_min': return_time,
            'auc_per_gram': auc,
        }
        all_results.append(result)
        profiles[name] = profile.tolist()
        print(f"  {name}: peak={peak_val:.2f}mg/g at {peak_time}min, return={return_time}min, AUC={auc:.0f}")

    # Population
    if all_results:
        pop_peak = np.mean([r['peak_mg_per_gram'] for r in all_results])
        pop_time = np.mean([r['peak_time_min'] for r in all_results])
        pop_auc = np.mean([r['auc_per_gram'] for r in all_results])
        cv_peak = np.std([r['peak_mg_per_gram'] for r in all_results]) / pop_peak
        print(f"\n  Population: peak={pop_peak:.2f}mg/g at {pop_time:.0f}min AUC={pop_auc:.0f} CV_peak={cv_peak:.2f}")
        verdict = f"PEAK_{pop_peak:.2f}mg/g_AT_{pop_time:.0f}min_CV_{cv_peak:.2f}"
    else:
        verdict = "INSUFFICIENT_DATA"

    if save_fig and profiles:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            fig, axes = plt.subplots(1, 2, figsize=(12, 5))

            t = np.arange(0, 180, 5)
            for name, prof in profiles.items():
                prof_arr = np.array(prof[:len(t)])
                if len(prof_arr) == len(t):
                    axes[0].plot(t, prof_arr, alpha=0.6, label=name)
            axes[0].axhline(0, color='gray', ls='--', lw=0.5)
            axes[0].set_xlabel('Time after meal (min)')
            axes[0].set_ylabel('Glucose per gram (mg/dL/g)')
            axes[0].set_title('Normalized Meal Response Profiles')
            axes[0].legend(fontsize=7, ncol=2)

            # Peak vs time scatter
            peaks = [r['peak_mg_per_gram'] for r in all_results]
            times = [r['peak_time_min'] for r in all_results]
            names_list = [r['patient'] for r in all_results]
            axes[1].scatter(times, peaks, s=80, c='steelblue', edgecolors='navy')
            for i, r in enumerate(all_results):
                axes[1].annotate(r['patient'], (times[i], peaks[i]),
                                  textcoords='offset points', xytext=(5, 5), fontsize=9)
            axes[1].set_xlabel('Time to peak (min)')
            axes[1].set_ylabel('Peak glucose per gram (mg/dL/g)')
            axes[1].set_title('Individual Absorption Characteristics')

            plt.tight_layout()
            fig.savefig(FIGURES_DIR / 'carb-fig04-individual-profiles.png', dpi=150)
            plt.close(fig)
            print(f"  → Saved carb-fig04-individual-profiles.png")
        except Exception as e:
            print(f"  (figure skipped: {e})")

    print(f"\n  ✓ EXP-1934 verdict: {verdict}")
    return {'experiment': 'EXP-1934', 'title': 'Individual Absorption Profiles',
            'verdict': verdict, 'per_patient': all_results}


# =====================================================================
# EXP-1935: Improved Carb Absorption Model
# =====================================================================

def exp_1935(patients, save_fig=False):
    """Build improved carb absorption model using fitted per-patient rates.

    Replace the default absorption curve with a slower, patient-fitted version.
    Evaluate using supply/demand model residual.
    """
    print("\n" + "=" * 70)
    print("EXP-1935: Improved Carb Absorption Model")
    print("=" * 70)

    all_results = []
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        sd = compute_supply_demand(df)
        supply_orig = sd.get('supply', np.zeros_like(glucose))
        demand = sd.get('demand', np.zeros_like(glucose))
        carb_supply_orig = sd.get('carb_supply', np.zeros_like(glucose))
        hepatic = sd.get('hepatic', np.zeros_like(glucose))
        dg = np.diff(glucose, prepend=glucose[0])
        carbs_col = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(df))

        meals = find_meals(df, min_carbs=5)
        if len(meals) < 3:
            print(f"  {name}: <3 meals, skip")
            continue

        # Original model loss
        net_orig = supply_orig - demand
        resid_orig = dg - net_orig
        valid = np.isfinite(resid_orig)
        loss_orig = float(np.mean(resid_orig[valid] ** 2)) if valid.sum() > 10 else np.nan

        # Build improved carb supply with different absorption rates
        best_tau = 30
        best_loss = np.inf
        best_scale = 1.0

        for tau_min in [20, 30, 40, 50, 60, 75, 90, 105, 120]:
            for absorb_frac in [0.3, 0.5, 0.7, 0.85, 1.0]:
                # Rebuild carb supply with this tau and absorption fraction
                new_carb_supply = np.zeros_like(glucose)
                for i in range(len(glucose)):
                    c = carbs_col[i] if np.isfinite(carbs_col[i]) else 0
                    if c >= 1:
                        effective_carbs = c * absorb_frac
                        tau_steps = tau_min / 5
                        for k in range(min(int(6 * tau_steps), len(glucose) - i)):
                            t = k  # steps
                            if tau_steps > 0:
                                rate = effective_carbs * (t / (tau_steps ** 2)) * np.exp(-t / tau_steps)
                                new_carb_supply[i + k] += rate

                new_supply = hepatic + new_carb_supply
                new_net = new_supply - demand
                new_resid = dg - new_net
                valid_new = np.isfinite(new_resid)
                if valid_new.sum() < 10:
                    continue
                loss = float(np.mean(new_resid[valid_new] ** 2))
                if loss < best_loss:
                    best_loss = loss
                    best_tau = tau_min
                    best_scale = absorb_frac

        improvement = (1 - best_loss / loss_orig) * 100 if loss_orig > 0 else 0

        result = {
            'patient': name,
            'n_meals': len(meals),
            'original_loss': loss_orig,
            'improved_loss': best_loss,
            'improvement_pct': improvement,
            'fitted_tau': best_tau,
            'fitted_absorb_frac': best_scale,
        }
        all_results.append(result)
        print(f"  {name}: tau={best_tau}min absorb={best_scale:.0%} improvement={improvement:.1f}%")

    # Population
    if all_results:
        pop_imp = np.mean([r['improvement_pct'] for r in all_results])
        pop_tau = np.mean([r['fitted_tau'] for r in all_results])
        pop_frac = np.mean([r['fitted_absorb_frac'] for r in all_results])
        improved = sum(1 for r in all_results if r['improvement_pct'] > 0)
        print(f"\n  Population: improvement={pop_imp:.1f}% tau={pop_tau:.0f}min absorb={pop_frac:.0%} ({improved}/{len(all_results)} improved)")
        verdict = f"IMPROVEMENT_{pop_imp:.1f}%_TAU_{pop_tau:.0f}min_FRAC_{pop_frac:.0%}"
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

            # Improvement
            imp = [r['improvement_pct'] for r in all_results]
            colors = ['green' if i > 0 else 'red' for i in imp]
            axes[0].bar(x, imp, color=colors)
            axes[0].set_xticks(x)
            axes[0].set_xticklabels(names)
            axes[0].set_ylabel('Improvement (%)')
            axes[0].set_title('Model Improvement from Better Absorption')
            axes[0].axhline(0, color='gray', ls='--', lw=0.5)

            # Fitted parameters
            taus = [r['fitted_tau'] for r in all_results]
            fracs = [r['fitted_absorb_frac'] * 100 for r in all_results]
            axes[1].bar(x - 0.15, taus, 0.3, label='τ (min)', color='steelblue')
            ax2 = axes[1].twinx()
            ax2.bar(x + 0.15, fracs, 0.3, label='Absorb %', color='coral')
            axes[1].set_xticks(x)
            axes[1].set_xticklabels(names)
            axes[1].set_ylabel('τ (min)')
            ax2.set_ylabel('Absorption fraction (%)')
            axes[1].set_title('Fitted Absorption Parameters')
            axes[1].legend(loc='upper left', fontsize=8)
            ax2.legend(loc='upper right', fontsize=8)

            # Original vs improved loss
            orig = [r['original_loss'] for r in all_results]
            improv = [r['improved_loss'] for r in all_results]
            axes[2].bar(x - 0.15, orig, 0.3, label='Original', color='coral')
            axes[2].bar(x + 0.15, improv, 0.3, label='Improved', color='green')
            axes[2].set_xticks(x)
            axes[2].set_xticklabels(names)
            axes[2].set_ylabel('MSE')
            axes[2].set_title('Model Loss: Original vs Improved')
            axes[2].legend()

            plt.tight_layout()
            fig.savefig(FIGURES_DIR / 'carb-fig05-improved-model.png', dpi=150)
            plt.close(fig)
            print(f"  → Saved carb-fig05-improved-model.png")
        except Exception as e:
            print(f"  (figure skipped: {e})")

    print(f"\n  ✓ EXP-1935 verdict: {verdict}")
    return {'experiment': 'EXP-1935', 'title': 'Improved Absorption Model',
            'verdict': verdict, 'per_patient': all_results}


# =====================================================================
# EXP-1936: Impact on CR Estimation
# =====================================================================

def exp_1936(patients, save_fig=False):
    """Test if fixing carb absorption changes CR estimates.

    Compare CR from original model vs CR from improved absorption model.
    Original finding: CR 38% too high → equation-based CR improves 20%.
    """
    print("\n" + "=" * 70)
    print("EXP-1936: Absorption Model Impact on CR Estimation")
    print("=" * 70)

    all_results = []
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        cr_profile = get_cr(p)
        isf_profile = get_isf(p)
        dg = np.diff(glucose, prepend=glucose[0])
        carbs_col = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(df))
        bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(len(df))

        meals = find_meals(df, min_carbs=10)
        if len(meals) < 5:
            print(f"  {name}: <5 meals, skip")
            continue

        # For each meal, estimate effective CR from glucose rise
        original_crs = []
        for m in meals:
            idx = m['idx']
            carbs = m['carbs']
            meal_bolus = m['bolus']
            if meal_bolus < 0.5:
                continue

            # Glucose rise in 2h window
            end = min(idx + 2 * STEPS_PER_HOUR, len(glucose))
            pre_g = glucose[idx] if np.isfinite(glucose[idx]) else np.nan
            post_g = glucose[end - 1] if end > idx and np.isfinite(glucose[end - 1]) else np.nan
            if not (np.isfinite(pre_g) and np.isfinite(post_g)):
                continue

            delta_g = post_g - pre_g

            # Effective CR: grams per unit that results in no glucose change
            # If delta_g > 0, CR was too high (not enough insulin)
            # If delta_g < 0, CR was too low (too much insulin)
            # bolus = carbs / CR → CR = carbs / bolus
            actual_cr = carbs / meal_bolus
            # Corrected CR: account for glucose change
            correction_units = delta_g / isf_profile if isf_profile > 0 else 0
            effective_units = meal_bolus + correction_units
            if effective_units > 0.1:
                effective_cr = carbs / effective_units
                original_crs.append({
                    'actual_cr': actual_cr,
                    'effective_cr': effective_cr,
                    'delta_g': delta_g,
                    'carbs': carbs,
                    'bolus': meal_bolus,
                })

        if not original_crs:
            print(f"  {name}: no valid CR estimates")
            continue

        mean_actual_cr = float(np.mean([c['actual_cr'] for c in original_crs]))
        mean_effective_cr = float(np.mean([c['effective_cr'] for c in original_crs]))
        mean_delta_g = float(np.mean([c['delta_g'] for c in original_crs]))

        # CR mismatch
        cr_mismatch = (mean_effective_cr - cr_profile) / cr_profile * 100

        result = {
            'patient': name,
            'n_meals': len(original_crs),
            'cr_profile': cr_profile,
            'mean_actual_cr': mean_actual_cr,
            'mean_effective_cr': mean_effective_cr,
            'mean_delta_g': mean_delta_g,
            'cr_mismatch_pct': cr_mismatch,
        }
        all_results.append(result)
        print(f"  {name}: CR_profile={cr_profile:.1f} effective={mean_effective_cr:.1f} "
              f"mismatch={cr_mismatch:+.0f}% mean_delta_g={mean_delta_g:+.0f}")

    # Population
    if all_results:
        pop_mismatch = np.mean([r['cr_mismatch_pct'] for r in all_results])
        pop_delta = np.mean([r['mean_delta_g'] for r in all_results])
        too_high = sum(1 for r in all_results if r['cr_mismatch_pct'] > 10)
        too_low = sum(1 for r in all_results if r['cr_mismatch_pct'] < -10)
        print(f"\n  Population: CR mismatch={pop_mismatch:+.0f}% delta_g={pop_delta:+.0f}mg/dL")
        print(f"  Too high: {too_high}/{len(all_results)}, Too low: {too_low}/{len(all_results)}")
        verdict = f"CR_MISMATCH_{pop_mismatch:+.0f}%_DG_{pop_delta:+.0f}"
    else:
        verdict = "INSUFFICIENT_DATA"

    if save_fig and all_results:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            fig, axes = plt.subplots(1, 2, figsize=(12, 5))

            names = [r['patient'] for r in all_results]
            x = np.arange(len(names))

            # CR comparison
            cr_prof = [r['cr_profile'] for r in all_results]
            cr_eff = [r['mean_effective_cr'] for r in all_results]
            axes[0].bar(x - 0.15, cr_prof, 0.3, label='Profile CR', color='coral')
            axes[0].bar(x + 0.15, cr_eff, 0.3, label='Effective CR', color='green')
            axes[0].set_xticks(x)
            axes[0].set_xticklabels(names)
            axes[0].set_ylabel('CR (g/U)')
            axes[0].set_title('Profile vs Effective CR')
            axes[0].legend()

            # Mean glucose change after meals
            dgs = [r['mean_delta_g'] for r in all_results]
            colors = ['green' if d < 0 else 'coral' for d in dgs]
            axes[1].bar(x, dgs, color=colors)
            axes[1].axhline(0, color='gray', ls='--', lw=0.5)
            axes[1].set_xticks(x)
            axes[1].set_xticklabels(names)
            axes[1].set_ylabel('Mean 2h glucose change (mg/dL)')
            axes[1].set_title('Post-Meal Glucose Change')

            plt.tight_layout()
            fig.savefig(FIGURES_DIR / 'carb-fig06-cr-impact.png', dpi=150)
            plt.close(fig)
            print(f"  → Saved carb-fig06-cr-impact.png")
        except Exception as e:
            print(f"  (figure skipped: {e})")

    print(f"\n  ✓ EXP-1936 verdict: {verdict}")
    return {'experiment': 'EXP-1936', 'title': 'CR Impact',
            'verdict': verdict, 'per_patient': all_results}


# =====================================================================
# EXP-1937: Temporal Validation of Improved Absorption
# =====================================================================

def exp_1937(patients, save_fig=False):
    """Temporal cross-validation of improved carb absorption model.

    Fit absorption parameters on first half, evaluate on second half.
    """
    print("\n" + "=" * 70)
    print("EXP-1937: Temporal Validation of Absorption Model")
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
        dg = np.diff(glucose, prepend=glucose[0])
        carbs_col = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(df))

        mid = len(glucose) // 2

        # Fit on first half
        best_tau = 30
        best_frac = 1.0
        best_train_loss = np.inf

        for tau_min in [20, 30, 40, 50, 60, 75, 90, 120]:
            for frac in [0.3, 0.5, 0.7, 0.85, 1.0]:
                new_carb = np.zeros_like(glucose)
                for i in range(mid):
                    c = carbs_col[i] if np.isfinite(carbs_col[i]) else 0
                    if c >= 1:
                        tau_s = tau_min / 5
                        for k in range(min(int(6 * tau_s), mid - i)):
                            new_carb[i + k] += c * frac * (k / (tau_s ** 2)) * np.exp(-k / tau_s)

                new_supply = hepatic[:mid] + new_carb[:mid]
                net = new_supply - demand[:mid]
                resid = dg[:mid] - net
                valid = np.isfinite(resid)
                if valid.sum() < 100:
                    continue
                loss = float(np.mean(resid[valid] ** 2))
                if loss < best_train_loss:
                    best_train_loss = loss
                    best_tau = tau_min
                    best_frac = frac

        # Evaluate on second half with fitted params
        new_carb_test = np.zeros_like(glucose)
        for i in range(mid, len(glucose)):
            c = carbs_col[i] if np.isfinite(carbs_col[i]) else 0
            if c >= 1:
                tau_s = best_tau / 5
                for k in range(min(int(6 * tau_s), len(glucose) - i)):
                    new_carb_test[i + k] += c * best_frac * (k / (tau_s ** 2)) * np.exp(-k / tau_s)

        # Test losses
        test_mask = np.zeros(len(glucose), dtype=bool)
        test_mask[mid:] = True

        # Original
        net_orig = supply - demand
        resid_orig = dg - net_orig
        valid_orig = test_mask & np.isfinite(resid_orig)
        loss_orig = float(np.mean(resid_orig[valid_orig] ** 2)) if valid_orig.sum() > 10 else np.nan

        # Improved
        new_supply_test = hepatic + new_carb_test
        net_improved = new_supply_test - demand
        resid_improved = dg - net_improved
        valid_imp = test_mask & np.isfinite(resid_improved)
        loss_improved = float(np.mean(resid_improved[valid_imp] ** 2)) if valid_imp.sum() > 10 else np.nan

        improvement = (1 - loss_improved / loss_orig) * 100 if loss_orig > 0 and np.isfinite(loss_improved) else 0

        result = {
            'patient': name,
            'fitted_tau': best_tau,
            'fitted_frac': best_frac,
            'test_loss_orig': loss_orig,
            'test_loss_improved': loss_improved,
            'improvement_pct': improvement,
        }
        all_results.append(result)
        print(f"  {name}: tau={best_tau}min frac={best_frac:.0%} orig={loss_orig:.0f} improved={loss_improved:.0f} Δ{improvement:+.1f}%")

    if all_results:
        pop_imp = np.mean([r['improvement_pct'] for r in all_results])
        improved = sum(1 for r in all_results if r['improvement_pct'] > 0)
        print(f"\n  Population improvement: {pop_imp:+.1f}% ({improved}/{len(all_results)} improved)")
        verdict = f"VALIDATED_{pop_imp:+.1f}%_({improved}/{len(all_results)})"
    else:
        verdict = "INSUFFICIENT_DATA"

    if save_fig and all_results:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            fig, axes = plt.subplots(1, 2, figsize=(12, 5))

            names = [r['patient'] for r in all_results]
            x = np.arange(len(names))

            imp = [r['improvement_pct'] for r in all_results]
            colors = ['green' if i > 0 else 'red' for i in imp]
            axes[0].bar(x, imp, color=colors)
            axes[0].set_xticks(x)
            axes[0].set_xticklabels(names)
            axes[0].set_ylabel('Improvement (%)')
            axes[0].set_title('Temporal CV: Absorption Model Improvement')
            axes[0].axhline(0, color='gray', ls='--', lw=0.5)

            orig = [r['test_loss_orig'] for r in all_results]
            improv = [r['test_loss_improved'] for r in all_results]
            axes[1].bar(x - 0.15, orig, 0.3, label='Original', color='coral')
            axes[1].bar(x + 0.15, improv, 0.3, label='Improved', color='green')
            axes[1].set_xticks(x)
            axes[1].set_xticklabels(names)
            axes[1].set_ylabel('Test MSE')
            axes[1].set_title('Temporal CV: Test Loss')
            axes[1].legend()

            plt.tight_layout()
            fig.savefig(FIGURES_DIR / 'carb-fig07-temporal-validation.png', dpi=150)
            plt.close(fig)
            print(f"  → Saved carb-fig07-temporal-validation.png")
        except Exception as e:
            print(f"  (figure skipped: {e})")

    print(f"\n  ✓ EXP-1937 verdict: {verdict}")
    return {'experiment': 'EXP-1937', 'title': 'Temporal Validation',
            'verdict': verdict, 'per_patient': all_results}


# =====================================================================
# EXP-1938: Combined Improvement (Absorption + Gradient Demand)
# =====================================================================

def exp_1938(patients, save_fig=False):
    """Combine improved carb absorption with gradient demand model.

    Test the full improved model vs original, using temporal CV.
    """
    print("\n" + "=" * 70)
    print("EXP-1938: Combined Model (Absorption + Gradient Demand)")
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
        dg = np.diff(glucose, prepend=glucose[0])
        carbs_col = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(df))

        mid = len(glucose) // 2

        # Meal mask
        meal_mask = np.zeros(len(glucose), dtype=bool)
        for i in range(len(glucose)):
            c = carbs_col[i] if np.isfinite(carbs_col[i]) else 0
            if c >= 5:
                meal_mask[i:min(i + 36, len(glucose))] = True

        # === Fit all parameters on first half ===

        # 1. Fit absorption parameters
        best_tau = 30
        best_frac = 1.0
        best_abs_loss = np.inf
        for tau_min in [20, 40, 60, 90, 120]:
            for frac in [0.5, 0.7, 0.85, 1.0]:
                new_carb = np.zeros(mid)
                for i in range(mid):
                    c = carbs_col[i] if np.isfinite(carbs_col[i]) else 0
                    if c >= 1:
                        tau_s = tau_min / 5
                        for k in range(min(int(6 * tau_s), mid - i)):
                            new_carb[i + k] += c * frac * (k / (tau_s ** 2)) * np.exp(-k / tau_s)
                new_supply_train = hepatic[:mid] + new_carb
                net = new_supply_train - demand[:mid]
                resid = dg[:mid] - net
                valid = np.isfinite(resid)
                if valid.sum() < 100:
                    continue
                loss = float(np.mean(resid[valid] ** 2))
                if loss < best_abs_loss:
                    best_abs_loss = loss
                    best_tau = tau_min
                    best_frac = frac

        # 2. Fit gradient demand scales on first half with improved absorption
        new_carb_full = np.zeros_like(glucose)
        for i in range(len(glucose)):
            c = carbs_col[i] if np.isfinite(carbs_col[i]) else 0
            if c >= 1:
                tau_s = best_tau / 5
                for k in range(min(int(6 * tau_s), len(glucose) - i)):
                    new_carb_full[i + k] += c * best_frac * (k / (tau_s ** 2)) * np.exp(-k / tau_s)
        new_supply_full = hepatic + new_carb_full

        # Build SD dict for improved supply
        sd_improved = {'supply': new_supply_full, 'demand': demand}

        # Fit meal/non-meal scales on first half
        train_mask = np.zeros(len(glucose), dtype=bool)
        train_mask[:mid] = True

        train_meal = train_mask & meal_mask
        train_nonmeal = train_mask & ~meal_mask
        meal_scale, _ = optimal_demand_scale(sd_improved, glucose, mask=train_meal)
        nonmeal_scale, _ = optimal_demand_scale(sd_improved, glucose, mask=train_nonmeal)

        # === Evaluate on second half ===
        test_mask = np.zeros(len(glucose), dtype=bool)
        test_mask[mid:] = True

        # Approach 1: Original model (no changes)
        net_orig = supply - demand
        resid_orig = dg - net_orig
        valid_orig = test_mask & np.isfinite(resid_orig)
        loss_orig = float(np.mean(resid_orig[valid_orig] ** 2)) if valid_orig.sum() > 10 else np.nan

        # Approach 2: Gradient demand only (from EXP-1927)
        global_scale, _ = optimal_demand_scale({'supply': supply, 'demand': demand}, glucose, mask=train_mask)
        # Meal/nonmeal with original supply
        m_scale_orig, _ = optimal_demand_scale({'supply': supply, 'demand': demand}, glucose, mask=train_meal)
        nm_scale_orig, _ = optimal_demand_scale({'supply': supply, 'demand': demand}, glucose, mask=train_nonmeal)
        grad_scale_orig = np.full(len(glucose), nm_scale_orig)
        for i in range(len(glucose)):
            c = carbs_col[i] if np.isfinite(carbs_col[i]) else 0
            if c >= 5:
                for k in range(min(72, len(glucose) - i)):
                    decay = np.exp(-k / 18)
                    blended = nm_scale_orig + (m_scale_orig - nm_scale_orig) * decay
                    grad_scale_orig[i + k] = max(grad_scale_orig[i + k], blended)
        net_grad_orig = supply - demand * grad_scale_orig
        resid_grad_orig = dg - net_grad_orig
        valid_grad = test_mask & np.isfinite(resid_grad_orig)
        loss_grad_orig = float(np.mean(resid_grad_orig[valid_grad] ** 2)) if valid_grad.sum() > 10 else np.nan

        # Approach 3: Improved absorption only
        net_abs_only = new_supply_full - demand
        resid_abs_only = dg - net_abs_only
        valid_abs = test_mask & np.isfinite(resid_abs_only)
        loss_abs_only = float(np.mean(resid_abs_only[valid_abs] ** 2)) if valid_abs.sum() > 10 else np.nan

        # Approach 4: Combined (improved absorption + gradient demand)
        gradient_scale = np.full(len(glucose), nonmeal_scale)
        for i in range(len(glucose)):
            c = carbs_col[i] if np.isfinite(carbs_col[i]) else 0
            if c >= 5:
                for k in range(min(72, len(glucose) - i)):
                    decay = np.exp(-k / 18)
                    blended = nonmeal_scale + (meal_scale - nonmeal_scale) * decay
                    gradient_scale[i + k] = max(gradient_scale[i + k], blended)
        net_combined = new_supply_full - demand * gradient_scale
        resid_combined = dg - net_combined
        valid_comb = test_mask & np.isfinite(resid_combined)
        loss_combined = float(np.mean(resid_combined[valid_comb] ** 2)) if valid_comb.sum() > 10 else np.nan

        losses = {
            'original': loss_orig,
            'gradient_demand': loss_grad_orig,
            'improved_absorption': loss_abs_only,
            'combined': loss_combined,
        }
        best = min(losses, key=lambda k: losses[k] if np.isfinite(losses[k]) else np.inf)

        result = {
            'patient': name,
            'fitted_tau': best_tau,
            'fitted_frac': best_frac,
            'meal_scale': meal_scale,
            'nonmeal_scale': nonmeal_scale,
            'loss_original': loss_orig,
            'loss_gradient_demand': loss_grad_orig,
            'loss_improved_absorption': loss_abs_only,
            'loss_combined': loss_combined,
            'best': best,
            'improvement_combined': (1 - loss_combined / loss_orig) * 100 if loss_orig > 0 and np.isfinite(loss_combined) else 0,
            'improvement_gradient': (1 - loss_grad_orig / loss_orig) * 100 if loss_orig > 0 and np.isfinite(loss_grad_orig) else 0,
            'improvement_absorption': (1 - loss_abs_only / loss_orig) * 100 if loss_orig > 0 and np.isfinite(loss_abs_only) else 0,
        }
        all_results.append(result)
        print(f"  {name}: orig={loss_orig:.0f} grad={loss_grad_orig:.0f} absorb={loss_abs_only:.0f} "
              f"combined={loss_combined:.0f} → best={best} (+{result['improvement_combined']:.0f}%)")

    if all_results:
        wins = {}
        for r in all_results:
            b = r['best']
            wins[b] = wins.get(b, 0) + 1

        pop_comb = np.mean([r['improvement_combined'] for r in all_results])
        pop_grad = np.mean([r['improvement_gradient'] for r in all_results])
        pop_abs = np.mean([r['improvement_absorption'] for r in all_results])
        print(f"\n  Population improvement: combined={pop_comb:+.1f}% gradient={pop_grad:+.1f}% absorption={pop_abs:+.1f}%")
        print(f"  Wins: {wins}")
        verdict = f"COMBINED_+{pop_comb:.0f}%_WINS:{wins}"
    else:
        verdict = "INSUFFICIENT_DATA"

    if save_fig and all_results:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            fig, axes = plt.subplots(1, 2, figsize=(12, 5))

            names = [r['patient'] for r in all_results]
            x = np.arange(len(names))
            w = 0.2

            # Loss comparison
            l_o = [r['loss_original'] for r in all_results]
            l_g = [r['loss_gradient_demand'] for r in all_results]
            l_a = [r['loss_improved_absorption'] for r in all_results]
            l_c = [r['loss_combined'] for r in all_results]
            axes[0].bar(x - 1.5*w, l_o, w, label='Original', color='gray')
            axes[0].bar(x - 0.5*w, l_g, w, label='Gradient', color='steelblue')
            axes[0].bar(x + 0.5*w, l_a, w, label='Absorption', color='orange')
            axes[0].bar(x + 1.5*w, l_c, w, label='Combined', color='green')
            axes[0].set_xticks(x)
            axes[0].set_xticklabels(names)
            axes[0].set_ylabel('Test MSE')
            axes[0].set_title('Test Loss: 4 Model Variants')
            axes[0].legend(fontsize=8)

            # Improvement comparison
            i_g = [r['improvement_gradient'] for r in all_results]
            i_a = [r['improvement_absorption'] for r in all_results]
            i_c = [r['improvement_combined'] for r in all_results]
            axes[1].bar(x - w, i_g, w, label='Gradient', color='steelblue')
            axes[1].bar(x, i_a, w, label='Absorption', color='orange')
            axes[1].bar(x + w, i_c, w, label='Combined', color='green')
            axes[1].set_xticks(x)
            axes[1].set_xticklabels(names)
            axes[1].set_ylabel('Improvement over original (%)')
            axes[1].set_title('Model Improvement: Components & Combined')
            axes[1].legend(fontsize=8)
            axes[1].axhline(0, color='gray', ls='--', lw=0.5)

            plt.tight_layout()
            fig.savefig(FIGURES_DIR / 'carb-fig08-combined-model.png', dpi=150)
            plt.close(fig)
            print(f"  → Saved carb-fig08-combined-model.png")
        except Exception as e:
            print(f"  (figure skipped: {e})")

    print(f"\n  ✓ EXP-1938 verdict: {verdict}")
    return {'experiment': 'EXP-1938', 'title': 'Combined Model',
            'verdict': verdict, 'per_patient': all_results}


# =====================================================================
# Main
# =====================================================================

def main():
    parser = argparse.ArgumentParser(description='EXP-1931–1938: Carb Absorption Investigation')
    parser.add_argument('--figures', action='store_true')
    args = parser.parse_args()

    patients = load_patients('externals/ns-data/patients/')
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 70)
    print("EXP-1931–1938: Carb Absorption Model Investigation")
    print("=" * 70)

    results = {}
    experiments = [
        ('EXP-1931', exp_1931),
        ('EXP-1932', exp_1932),
        ('EXP-1933', exp_1933),
        ('EXP-1934', exp_1934),
        ('EXP-1935', exp_1935),
        ('EXP-1936', exp_1936),
        ('EXP-1937', exp_1937),
        ('EXP-1938', exp_1938),
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

    print("\n" + "=" * 70)
    print("SYNTHESIS: Carb Absorption Model Investigation")
    print("=" * 70)
    for exp_id, result in results.items():
        print(f"  {exp_id}: {result.get('verdict', 'N/A')}")
    print("\n✓ All experiments complete")


if __name__ == '__main__':
    main()
