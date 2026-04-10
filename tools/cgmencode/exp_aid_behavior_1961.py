#!/usr/bin/env python3
"""EXP-1961–1968: AID Loop Behavior Characterization.

With glycemic patterns mapped (EXP-1951–1958), this batch analyzes HOW
AID loops compensate for parameter mismatch, and WHERE loop behavior
creates opportunities for algorithm improvement.

Experiments:
  EXP-1961: Loop aggressiveness profiling — how much does the loop deviate from scheduled basal?
  EXP-1962: Prediction accuracy — how well does the loop predict 30/60 min glucose?
  EXP-1963: Correction response — what does the loop do when glucose is high vs low?
  EXP-1964: Meal detection & response — how quickly does the loop react to meals?
  EXP-1965: Overnight loop behavior — basal modulation patterns 10PM–6AM
  EXP-1966: Loop compensation vs glucose outcome — does more compensation = better TIR?
  EXP-1967: Suspension analysis — when and why does the loop suspend delivery?
  EXP-1968: Synthesis — loop behavior phenotypes and algorithm improvement targets
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
RESULTS_PATH = Path('externals/experiments/exp-1961_aid_behavior.json')
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
    meals = []
    for i in range(len(carbs)):
        if np.isfinite(carbs[i]) and carbs[i] >= min_carbs:
            start = max(0, i - pre_window)
            end = min(len(carbs), i + post_window)
            meals.append({'idx': i, 'start': start, 'end': end, 'carbs': carbs[i]})
    return meals


# =====================================================================
def exp_1961(patients, save_fig=False):
    """Profile how aggressively the loop modulates basal delivery."""
    print("\n" + "=" * 70)
    print("EXP-1961: Loop Aggressiveness Profiling")
    print("=" * 70)

    all_results = []
    for p in patients:
        name = p['name']
        df = p['df']
        basal_sched = get_basal(p)

        net_basal = df['net_basal'].values if 'net_basal' in df.columns else np.zeros(len(df))
        temp_rate = df['temp_rate'].values if 'temp_rate' in df.columns else np.zeros(len(df))
        glucose = df['glucose'].values

        valid = np.isfinite(net_basal) & np.isfinite(glucose)
        if valid.sum() < 1000:
            continue

        nb = net_basal[valid]
        g = glucose[valid]

        # Aggressiveness metrics
        # net_basal > 0 means delivering above scheduled, < 0 means below
        increasing = (nb > 0.05).sum() / len(nb) * 100  # >5% above scheduled
        decreasing = (nb < -0.05).sum() / len(nb) * 100  # >5% below scheduled
        zero_delivery = (temp_rate[valid] == 0).sum() / len(nb) * 100 if 'temp_rate' in df.columns else 0

        # Mean deviation from scheduled
        mean_dev = float(np.mean(nb))
        std_dev = float(np.std(nb))

        # Aggressiveness by glucose range
        ranges = {
            'hypo (<70)': g < 70,
            'low (70-100)': (g >= 70) & (g < 100),
            'target (100-140)': (g >= 100) & (g < 140),
            'high (140-180)': (g >= 140) & (g < 180),
            'hyper (>180)': g >= 180,
        }
        by_range = {}
        for label, mask in ranges.items():
            if mask.sum() > 10:
                by_range[label] = {
                    'mean_net_basal': float(np.mean(nb[mask])),
                    'pct_time': float(mask.sum() / len(g) * 100),
                }

        # Modulation rate (how often does net_basal change direction?)
        sign_changes = np.sum(np.diff(np.sign(nb)) != 0) / len(nb) * 100

        result = {
            'patient': name,
            'scheduled_basal': float(basal_sched),
            'pct_increasing': float(increasing),
            'pct_decreasing': float(decreasing),
            'pct_zero_delivery': float(zero_delivery),
            'mean_deviation': float(mean_dev),
            'std_deviation': float(std_dev),
            'sign_change_rate': float(sign_changes),
            'by_glucose_range': by_range,
        }
        all_results.append(result)

        print(f"  {name}: ↑{increasing:.0f}% ↓{decreasing:.0f}% zero={zero_delivery:.0f}% "
              f"mean_dev={mean_dev:+.2f} U/h churn={sign_changes:.0f}%")

    if save_fig:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt

            fig, axes = plt.subplots(1, 3, figsize=(18, 6))

            # Panel 1: Increasing vs decreasing by patient
            names = [r['patient'] for r in all_results]
            inc = [r['pct_increasing'] for r in all_results]
            dec = [r['pct_decreasing'] for r in all_results]
            zero = [r['pct_zero_delivery'] for r in all_results]
            x = np.arange(len(names))
            axes[0].bar(x, inc, 0.25, label='Increasing', color='#e74c3c')
            axes[0].bar(x + 0.25, dec, 0.25, label='Decreasing', color='#3498db')
            axes[0].bar(x + 0.5, zero, 0.25, label='Zero delivery', color='#2c3e50')
            axes[0].set_xticks(x + 0.25)
            axes[0].set_xticklabels(names)
            axes[0].set_ylabel('% of time')
            axes[0].set_title('Loop Modulation Direction')
            axes[0].legend()

            # Panel 2: Net basal by glucose range
            range_labels = ['hypo (<70)', 'low (70-100)', 'target (100-140)', 'high (140-180)', 'hyper (>180)']
            for r in all_results:
                vals = [r['by_glucose_range'].get(rl, {}).get('mean_net_basal', np.nan) for rl in range_labels]
                axes[1].plot(range_labels, vals, 'o-', label=r['patient'], alpha=0.6)
            axes[1].axhline(0, color='k', linestyle='--', alpha=0.3)
            axes[1].set_ylabel('Mean net basal (U/h)')
            axes[1].set_title('Loop Response by Glucose Range')
            axes[1].tick_params(axis='x', rotation=30)
            axes[1].legend(fontsize=7, ncol=2)

            # Panel 3: Mean deviation vs TIR
            glucose_data = []
            for pp in patients:
                g = pp['df']['glucose'].values
                valid_g = g[np.isfinite(g)]
                if len(valid_g) > 0:
                    tir = float(np.mean((valid_g >= 70) & (valid_g <= 180)) * 100)
                    glucose_data.append((pp['name'], tir))
            tir_map = dict(glucose_data)
            devs = [abs(r['mean_deviation']) for r in all_results]
            tirs = [tir_map.get(r['patient'], 70) for r in all_results]
            axes[2].scatter(devs, tirs, s=80, c='#e74c3c')
            for r, tir in zip(all_results, tirs):
                axes[2].annotate(r['patient'], (abs(r['mean_deviation']), tir),
                                fontsize=9, ha='center', va='bottom')
            axes[2].set_xlabel('|Mean net basal deviation| (U/h)')
            axes[2].set_ylabel('TIR (%)')
            axes[2].set_title('Loop Deviation vs Outcomes')

            plt.tight_layout()
            plt.savefig(FIGURES_DIR / 'aid-fig01-aggressiveness.png', dpi=150)
            plt.close()
            print(f"  → Saved aid-fig01-aggressiveness.png")
        except Exception as e:
            print(f"  → Figure failed: {e}")

    # Population summary
    pop_inc = np.mean([r['pct_increasing'] for r in all_results])
    pop_dec = np.mean([r['pct_decreasing'] for r in all_results])
    pop_zero = np.mean([r['pct_zero_delivery'] for r in all_results])
    verdict = f"INC_{pop_inc:.0f}%_DEC_{pop_dec:.0f}%_ZERO_{pop_zero:.0f}%"
    print(f"\n  ✓ EXP-1961 verdict: {verdict}")
    return {'experiment': 'EXP-1961', 'verdict': verdict, 'per_patient': all_results}


# =====================================================================
def exp_1962(patients, save_fig=False):
    """How accurate are the loop's own glucose predictions?"""
    print("\n" + "=" * 70)
    print("EXP-1962: Loop Prediction Accuracy")
    print("=" * 70)

    all_results = []
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        pred30 = df['predicted_30'].values if 'predicted_30' in df.columns else np.full(len(df), np.nan)
        pred60 = df['predicted_60'].values if 'predicted_60' in df.columns else np.full(len(df), np.nan)

        # Compare predicted_30 at time t to actual glucose at t+6 (30 min)
        errors_30, errors_60 = [], []
        for i in range(len(glucose)):
            if i + 6 < len(glucose) and np.isfinite(pred30[i]) and np.isfinite(glucose[i + 6]):
                errors_30.append(glucose[i + 6] - pred30[i])
            if i + 12 < len(glucose) and np.isfinite(pred60[i]) and np.isfinite(glucose[i + 12]):
                errors_60.append(glucose[i + 12] - pred60[i])

        if len(errors_30) < 100:
            continue

        e30 = np.array(errors_30)
        e60 = np.array(errors_60) if len(errors_60) > 100 else np.array([np.nan])

        # By glucose range at prediction time
        pred_accuracy_by_range = {}
        for i in range(len(glucose)):
            if i + 6 < len(glucose) and np.isfinite(pred30[i]) and np.isfinite(glucose[i + 6]) and np.isfinite(glucose[i]):
                g = glucose[i]
                err = glucose[i + 6] - pred30[i]
                if g < 70:
                    rng = 'hypo'
                elif g < 100:
                    rng = 'low'
                elif g < 180:
                    rng = 'target'
                else:
                    rng = 'hyper'
                if rng not in pred_accuracy_by_range:
                    pred_accuracy_by_range[rng] = []
                pred_accuracy_by_range[rng].append(err)

        by_range_summary = {}
        for rng, errs in pred_accuracy_by_range.items():
            ea = np.array(errs)
            by_range_summary[rng] = {
                'mean_error': float(np.mean(ea)),
                'rmse': float(np.sqrt(np.mean(ea ** 2))),
                'n': len(ea),
            }

        result = {
            'patient': name,
            'n_pred30': len(errors_30),
            'mean_error_30': float(np.mean(e30)),
            'rmse_30': float(np.sqrt(np.mean(e30 ** 2))),
            'mae_30': float(np.mean(np.abs(e30))),
            'mean_error_60': float(np.nanmean(e60)),
            'rmse_60': float(np.sqrt(np.nanmean(e60 ** 2))),
            'by_range': by_range_summary,
        }
        all_results.append(result)

        print(f"  {name}: 30min RMSE={result['rmse_30']:.1f} bias={result['mean_error_30']:+.1f} | "
              f"60min RMSE={result['rmse_60']:.1f} bias={result['mean_error_60']:+.1f}")

    if save_fig:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt

            fig, axes = plt.subplots(1, 3, figsize=(18, 6))

            names = [r['patient'] for r in all_results]
            rmse30 = [r['rmse_30'] for r in all_results]
            rmse60 = [r['rmse_60'] for r in all_results]
            bias30 = [r['mean_error_30'] for r in all_results]

            x = np.arange(len(names))
            axes[0].bar(x, rmse30, 0.35, label='30-min RMSE', color='#3498db')
            axes[0].bar(x + 0.35, rmse60, 0.35, label='60-min RMSE', color='#e74c3c')
            axes[0].set_xticks(x + 0.175)
            axes[0].set_xticklabels(names)
            axes[0].set_ylabel('RMSE (mg/dL)')
            axes[0].set_title('Loop Prediction Error')
            axes[0].legend()

            # Bias
            axes[1].bar(x, bias30, color=['#e74c3c' if b > 0 else '#3498db' for b in bias30])
            axes[1].set_xticks(x)
            axes[1].set_xticklabels(names)
            axes[1].axhline(0, color='k', linestyle='--')
            axes[1].set_ylabel('Mean Error (mg/dL)')
            axes[1].set_title('30-min Prediction Bias (+= underestimates)')

            # By range
            range_labels = ['hypo', 'low', 'target', 'hyper']
            for r in all_results:
                vals = [r['by_range'].get(rl, {}).get('rmse', np.nan) for rl in range_labels]
                axes[2].plot(range_labels, vals, 'o-', label=r['patient'], alpha=0.6)
            axes[2].set_ylabel('30-min RMSE (mg/dL)')
            axes[2].set_title('Prediction Error by Glucose Range')
            axes[2].legend(fontsize=7, ncol=2)

            plt.tight_layout()
            plt.savefig(FIGURES_DIR / 'aid-fig02-prediction.png', dpi=150)
            plt.close()
            print(f"  → Saved aid-fig02-prediction.png")
        except Exception as e:
            print(f"  → Figure failed: {e}")

    pop_rmse30 = np.mean([r['rmse_30'] for r in all_results])
    pop_rmse60 = np.mean([r['rmse_60'] for r in all_results])
    verdict = f"RMSE30_{pop_rmse30:.0f}_RMSE60_{pop_rmse60:.0f}"
    print(f"\n  ✓ EXP-1962 verdict: {verdict}")
    return {'experiment': 'EXP-1962', 'verdict': verdict, 'per_patient': all_results}


# =====================================================================
def exp_1963(patients, save_fig=False):
    """How does the loop respond to high vs low glucose?"""
    print("\n" + "=" * 70)
    print("EXP-1963: Loop Correction Response")
    print("=" * 70)

    all_results = []
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        net_basal = df['net_basal'].values if 'net_basal' in df.columns else np.zeros(len(df))
        temp_rate = df['temp_rate'].values if 'temp_rate' in df.columns else np.zeros(len(df))

        valid = np.isfinite(glucose) & np.isfinite(net_basal)
        if valid.sum() < 1000:
            continue

        g = glucose[valid]
        nb = net_basal[valid]
        tr = temp_rate[valid]

        # Response latency: when glucose crosses 180, how many steps until loop increases?
        high_crossings = []
        i = 1
        while i < len(g) - 36:
            if g[i] >= 180 and g[i - 1] < 180:
                # Find first step where net_basal > 0.1
                latency = None
                for j in range(i, min(i + 36, len(g))):
                    if nb[j] > 0.1:
                        latency = (j - i) * 5  # minutes
                        break
                high_crossings.append({
                    'latency_min': latency,
                    'peak_response': float(np.max(nb[i:min(i + 36, len(g))])),
                })
                i += 12  # skip ahead
            i += 1

        # Low response: when glucose < 80, how fast does loop reduce?
        low_crossings = []
        i = 1
        while i < len(g) - 36:
            if g[i] <= 80 and g[i - 1] > 80:
                latency = None
                for j in range(i, min(i + 36, len(g))):
                    if nb[j] < -0.1 or tr[j] == 0:
                        latency = (j - i) * 5
                        break
                low_crossings.append({
                    'latency_min': latency,
                    'min_response': float(np.min(nb[i:min(i + 36, len(g))])),
                    'suspension': bool(any(tr[i:min(i + 36, len(g))] == 0)),
                })
                i += 12
            i += 1

        # Compute valid latencies
        high_lats = [h['latency_min'] for h in high_crossings if h['latency_min'] is not None]
        low_lats = [l['latency_min'] for l in low_crossings if l['latency_min'] is not None]
        low_susp = [l['suspension'] for l in low_crossings]

        result = {
            'patient': name,
            'n_high_cross': len(high_crossings),
            'high_latency_min': float(np.median(high_lats)) if high_lats else None,
            'high_peak_response': float(np.mean([h['peak_response'] for h in high_crossings])) if high_crossings else None,
            'n_low_cross': len(low_crossings),
            'low_latency_min': float(np.median(low_lats)) if low_lats else None,
            'low_suspension_pct': float(np.mean(low_susp) * 100) if low_susp else None,
        }
        all_results.append(result)

        hl = result['high_latency_min']
        ll = result['low_latency_min']
        print(f"  {name}: high→↑ latency={hl:.0f}min ({len(high_crossings)} events) | "
              f"low→↓ latency={ll:.0f}min ({len(low_crossings)} events) "
              f"suspend={result['low_suspension_pct']:.0f}%"
              if hl is not None and ll is not None else
              f"  {name}: insufficient crossings")

    if save_fig:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt

            fig, axes = plt.subplots(1, 3, figsize=(18, 6))

            valid_results = [r for r in all_results if r['high_latency_min'] is not None and r['low_latency_min'] is not None]
            names = [r['patient'] for r in valid_results]
            x = np.arange(len(names))

            # Latency comparison
            high_lat = [r['high_latency_min'] for r in valid_results]
            low_lat = [r['low_latency_min'] for r in valid_results]
            axes[0].bar(x, high_lat, 0.35, label='High→Increase', color='#e74c3c')
            axes[0].bar(x + 0.35, low_lat, 0.35, label='Low→Decrease', color='#3498db')
            axes[0].set_xticks(x + 0.175)
            axes[0].set_xticklabels(names)
            axes[0].set_ylabel('Latency (minutes)')
            axes[0].set_title('Loop Response Latency')
            axes[0].legend()

            # Asymmetry
            asymmetry = [h - l for h, l in zip(high_lat, low_lat)]
            colors = ['#e74c3c' if a > 0 else '#3498db' for a in asymmetry]
            axes[1].bar(x, asymmetry, color=colors)
            axes[1].set_xticks(x)
            axes[1].set_xticklabels(names)
            axes[1].axhline(0, color='k', linestyle='--')
            axes[1].set_ylabel('High latency - Low latency (min)')
            axes[1].set_title('Response Asymmetry (+ = slower to correct high)')

            # Suspension rate
            susp = [r['low_suspension_pct'] for r in valid_results]
            axes[2].bar(x, susp, color='#2c3e50')
            axes[2].set_xticks(x)
            axes[2].set_xticklabels(names)
            axes[2].set_ylabel('% of low events with suspension')
            axes[2].set_title('Loop Suspension During Lows')

            plt.tight_layout()
            plt.savefig(FIGURES_DIR / 'aid-fig03-correction.png', dpi=150)
            plt.close()
            print(f"  → Saved aid-fig03-correction.png")
        except Exception as e:
            print(f"  → Figure failed: {e}")

    valid_results = [r for r in all_results if r['high_latency_min'] is not None]
    if valid_results:
        pop_high = np.mean([r['high_latency_min'] for r in valid_results])
        pop_low = np.mean([r['low_latency_min'] for r in valid_results if r['low_latency_min'] is not None])
        verdict = f"HIGH_LAT_{pop_high:.0f}min_LOW_LAT_{pop_low:.0f}min"
    else:
        verdict = "INSUFFICIENT_DATA"
    print(f"\n  ✓ EXP-1963 verdict: {verdict}")
    return {'experiment': 'EXP-1963', 'verdict': verdict, 'per_patient': all_results}


# =====================================================================
def exp_1964(patients, save_fig=False):
    """How quickly does the loop detect and respond to meals?"""
    print("\n" + "=" * 70)
    print("EXP-1964: Meal Detection & Loop Response")
    print("=" * 70)

    all_results = []
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        net_basal = df['net_basal'].values if 'net_basal' in df.columns else np.zeros(len(df))
        iob = df['iob'].values if 'iob' in df.columns else np.zeros(len(df))
        meals = find_meals(df, min_carbs=10)

        if len(meals) < 10:
            continue

        meal_responses = []
        for m in meals:
            idx = m['idx']
            if idx + 36 >= len(glucose) or idx < 6:
                continue

            # Pre-meal net basal (30 min before)
            pre_nb = np.nanmean(net_basal[max(0, idx - 6):idx])
            # Post-meal net basal peak (3 hours after)
            post_nb = net_basal[idx:min(idx + 36, len(net_basal))]
            if len(post_nb) == 0:
                continue
            valid_post = post_nb[np.isfinite(post_nb)]
            if len(valid_post) == 0:
                continue
            peak_nb = float(np.max(valid_post))

            # Time to peak response
            peak_idx = np.argmax(valid_post)
            time_to_peak = peak_idx * 5  # minutes

            # IOB change
            pre_iob = iob[idx] if np.isfinite(iob[idx]) else 0
            post_iob_vals = iob[idx:min(idx + 36, len(iob))]
            valid_iob = post_iob_vals[np.isfinite(post_iob_vals)]
            peak_iob = float(np.max(valid_iob)) if len(valid_iob) > 0 else 0
            iob_rise = peak_iob - pre_iob

            meal_responses.append({
                'carbs': float(m['carbs']),
                'pre_nb': float(pre_nb) if np.isfinite(pre_nb) else 0,
                'peak_nb': float(peak_nb),
                'time_to_peak': int(time_to_peak),
                'iob_rise': float(iob_rise),
            })

        if len(meal_responses) < 5:
            continue

        times = [m['time_to_peak'] for m in meal_responses]
        peaks = [m['peak_nb'] for m in meal_responses]
        iob_rises = [m['iob_rise'] for m in meal_responses]

        # Correlation of carb size with loop response
        carb_vals = np.array([m['carbs'] for m in meal_responses])
        peak_vals = np.array(peaks)
        corr = float(np.corrcoef(carb_vals, peak_vals)[0, 1]) if len(carb_vals) > 5 else np.nan

        result = {
            'patient': name,
            'n_meals': len(meal_responses),
            'median_time_to_peak': float(np.median(times)),
            'mean_peak_nb': float(np.mean(peaks)),
            'mean_iob_rise': float(np.mean(iob_rises)),
            'carb_response_corr': float(corr) if np.isfinite(corr) else None,
        }
        all_results.append(result)

        print(f"  {name}: peak_response={np.mean(peaks):.2f}U/h at {np.median(times):.0f}min "
              f"IOB_rise={np.mean(iob_rises):.1f}U carb_corr={corr:.2f} n={len(meal_responses)}")

    if save_fig:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt

            fig, axes = plt.subplots(1, 3, figsize=(18, 6))

            names = [r['patient'] for r in all_results]
            x = np.arange(len(names))

            # Time to peak response
            times = [r['median_time_to_peak'] for r in all_results]
            axes[0].bar(x, times, color='#e74c3c')
            axes[0].set_xticks(x)
            axes[0].set_xticklabels(names)
            axes[0].set_ylabel('Time to peak (min)')
            axes[0].set_title('Loop Meal Response Latency')

            # Peak response magnitude
            peaks = [r['mean_peak_nb'] for r in all_results]
            axes[1].bar(x, peaks, color='#3498db')
            axes[1].set_xticks(x)
            axes[1].set_xticklabels(names)
            axes[1].set_ylabel('Peak net basal above scheduled (U/h)')
            axes[1].set_title('Loop Meal Correction Magnitude')

            # Carb-response correlation
            corrs = [r['carb_response_corr'] if r['carb_response_corr'] is not None else 0 for r in all_results]
            colors = ['#27ae60' if c > 0.1 else '#e74c3c' for c in corrs]
            axes[2].bar(x, corrs, color=colors)
            axes[2].set_xticks(x)
            axes[2].set_xticklabels(names)
            axes[2].axhline(0, color='k', linestyle='--')
            axes[2].set_ylabel('Correlation')
            axes[2].set_title('Carb Size → Loop Response Correlation')

            plt.tight_layout()
            plt.savefig(FIGURES_DIR / 'aid-fig04-meal-response.png', dpi=150)
            plt.close()
            print(f"  → Saved aid-fig04-meal-response.png")
        except Exception as e:
            print(f"  → Figure failed: {e}")

    pop_time = np.mean([r['median_time_to_peak'] for r in all_results])
    pop_corr = np.nanmean([r['carb_response_corr'] for r in all_results if r['carb_response_corr'] is not None])
    verdict = f"PEAK_{pop_time:.0f}min_CORR_{pop_corr:.2f}"
    print(f"\n  ✓ EXP-1964 verdict: {verdict}")
    return {'experiment': 'EXP-1964', 'verdict': verdict, 'per_patient': all_results}


# =====================================================================
def exp_1965(patients, save_fig=False):
    """Overnight loop behavior: how does the loop handle basal and dawn phenomenon?"""
    print("\n" + "=" * 70)
    print("EXP-1965: Overnight Loop Behavior")
    print("=" * 70)

    all_results = []
    pop_nb_by_hour = {h: [] for h in range(24)}

    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        net_basal = df['net_basal'].values if 'net_basal' in df.columns else np.zeros(len(df))
        temp_rate = df['temp_rate'].values if 'temp_rate' in df.columns else np.zeros(len(df))

        n_days = len(glucose) // STEPS_PER_DAY
        if n_days < 7:
            continue

        # Net basal by hour (overnight focus)
        nb_by_hour = {h: [] for h in range(24)}
        for day in range(n_days):
            for hour in range(24):
                start = day * STEPS_PER_DAY + hour * STEPS_PER_HOUR
                end = start + STEPS_PER_HOUR
                if end > len(net_basal):
                    break
                chunk = net_basal[start:end]
                valid = chunk[np.isfinite(chunk)]
                if len(valid) > 0:
                    nb_by_hour[hour].append(float(np.mean(valid)))
                    pop_nb_by_hour[hour].append(float(np.mean(valid)))

        # Overnight pattern (10PM-6AM)
        overnight_hours = [22, 23, 0, 1, 2, 3, 4, 5]
        early_night = [22, 23, 0, 1]  # 10PM-2AM
        dawn_hours = [2, 3, 4, 5]  # 2AM-6AM

        early_nb = np.mean([np.mean(nb_by_hour[h]) for h in early_night if nb_by_hour[h]])
        dawn_nb = np.mean([np.mean(nb_by_hour[h]) for h in dawn_hours if nb_by_hour[h]])
        dawn_ramp = dawn_nb - early_nb  # positive = loop increasing for dawn

        # Suspension events overnight
        overnight_suspensions = 0
        overnight_periods = 0
        for day in range(n_days):
            for hour in overnight_hours:
                actual_hour = hour if hour >= 22 else hour
                if hour < 22:
                    start = (day + 1) * STEPS_PER_DAY + hour * STEPS_PER_HOUR
                else:
                    start = day * STEPS_PER_DAY + hour * STEPS_PER_HOUR
                end = start + STEPS_PER_HOUR
                if end > len(temp_rate):
                    break
                chunk = temp_rate[start:end]
                overnight_periods += 1
                if any(chunk == 0):
                    overnight_suspensions += 1

        suspension_rate = overnight_suspensions / max(overnight_periods, 1) * 100

        # Hour-by-hour net basal profile
        hourly_nb = {}
        for h in range(24):
            if nb_by_hour[h]:
                hourly_nb[str(h)] = float(np.mean(nb_by_hour[h]))

        result = {
            'patient': name,
            'early_night_nb': float(early_nb),
            'dawn_nb': float(dawn_nb),
            'dawn_ramp': float(dawn_ramp),
            'overnight_suspension_pct': float(suspension_rate),
            'hourly_nb': hourly_nb,
        }
        all_results.append(result)

        print(f"  {name}: early={early_nb:+.2f}U/h dawn={dawn_nb:+.2f}U/h ramp={dawn_ramp:+.2f} "
              f"suspend={suspension_rate:.0f}%")

    if save_fig:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt

            fig, axes = plt.subplots(1, 3, figsize=(18, 6))

            # Panel 1: Net basal by hour (all patients)
            hours = list(range(24))
            for r in all_results:
                vals = [r['hourly_nb'].get(str(h), np.nan) for h in hours]
                axes[0].plot(hours, vals, 'o-', label=r['patient'], alpha=0.5, markersize=3)
            # Population mean
            pop_mean = [np.mean(pop_nb_by_hour[h]) if pop_nb_by_hour[h] else np.nan for h in hours]
            axes[0].plot(hours, pop_mean, 'k-', linewidth=3, label='Population', zorder=10)
            axes[0].axhline(0, color='gray', linestyle='--', alpha=0.3)
            axes[0].axvspan(22, 24, alpha=0.1, color='blue')
            axes[0].axvspan(0, 6, alpha=0.1, color='blue')
            axes[0].set_xlabel('Hour')
            axes[0].set_ylabel('Mean net basal (U/h)')
            axes[0].set_title('24-Hour Loop Modulation Profile')
            axes[0].legend(fontsize=7, ncol=2)

            # Panel 2: Dawn ramp
            names = [r['patient'] for r in all_results]
            ramps = [r['dawn_ramp'] for r in all_results]
            x = np.arange(len(names))
            colors = ['#e74c3c' if r > 0 else '#3498db' for r in ramps]
            axes[1].bar(x, ramps, color=colors)
            axes[1].set_xticks(x)
            axes[1].set_xticklabels(names)
            axes[1].axhline(0, color='k', linestyle='--')
            axes[1].set_ylabel('Dawn ramp (U/h)')
            axes[1].set_title('Dawn Phenomenon Loop Compensation\n(+= loop increasing basal)')

            # Panel 3: Overnight suspension
            susp = [r['overnight_suspension_pct'] for r in all_results]
            axes[2].bar(x, susp, color='#2c3e50')
            axes[2].set_xticks(x)
            axes[2].set_xticklabels(names)
            axes[2].set_ylabel('% of overnight hours with suspension')
            axes[2].set_title('Overnight Delivery Suspension Rate')

            plt.tight_layout()
            plt.savefig(FIGURES_DIR / 'aid-fig05-overnight-loop.png', dpi=150)
            plt.close()
            print(f"  → Saved aid-fig05-overnight-loop.png")
        except Exception as e:
            print(f"  → Figure failed: {e}")

    pop_ramp = np.mean([r['dawn_ramp'] for r in all_results])
    pop_susp = np.mean([r['overnight_suspension_pct'] for r in all_results])
    verdict = f"DAWN_RAMP_{pop_ramp:+.2f}_SUSPEND_{pop_susp:.0f}%"
    print(f"\n  ✓ EXP-1965 verdict: {verdict}")
    return {'experiment': 'EXP-1965', 'verdict': verdict, 'per_patient': all_results}


# =====================================================================
def exp_1966(patients, save_fig=False):
    """Does more loop compensation correlate with better or worse outcomes?"""
    print("\n" + "=" * 70)
    print("EXP-1966: Loop Compensation vs Outcomes")
    print("=" * 70)

    all_results = []
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        net_basal = df['net_basal'].values if 'net_basal' in df.columns else np.zeros(len(df))

        valid_g = glucose[np.isfinite(glucose)]
        if len(valid_g) < 1000:
            continue

        valid = np.isfinite(glucose) & np.isfinite(net_basal)
        nb = net_basal[valid]

        # Compensation metrics
        compensation_magnitude = float(np.mean(np.abs(nb)))  # mean |deviation|
        compensation_std = float(np.std(nb))
        pct_active = float((np.abs(nb) > 0.05).sum() / len(nb) * 100)

        # Outcome metrics
        tir = float(np.mean((valid_g >= 70) & (valid_g <= 180)) * 100)
        tbr = float(np.mean(valid_g < 70) * 100)
        tar = float(np.mean(valid_g > 180) * 100)
        cv = float(np.std(valid_g) / np.mean(valid_g) * 100)

        # Day-level correlation: more active days = better TIR?
        n_days = len(glucose) // STEPS_PER_DAY
        day_comp = []
        day_tir = []
        for day in range(n_days):
            s = day * STEPS_PER_DAY
            e = s + STEPS_PER_DAY
            dg = glucose[s:e]
            dnb = net_basal[s:e]
            vg = dg[np.isfinite(dg)]
            vnb = dnb[np.isfinite(dnb)]
            if len(vg) > 100 and len(vnb) > 100:
                day_comp.append(float(np.mean(np.abs(vnb))))
                day_tir.append(float(np.mean((vg >= 70) & (vg <= 180)) * 100))

        day_corr = float(np.corrcoef(day_comp, day_tir)[0, 1]) if len(day_comp) > 10 else np.nan

        result = {
            'patient': name,
            'compensation_magnitude': compensation_magnitude,
            'compensation_std': compensation_std,
            'pct_active': pct_active,
            'tir': tir,
            'tbr': tbr,
            'tar': tar,
            'cv': cv,
            'day_level_corr': float(day_corr) if np.isfinite(day_corr) else None,
        }
        all_results.append(result)

        print(f"  {name}: |comp|={compensation_magnitude:.2f}U/h active={pct_active:.0f}% → "
              f"TIR={tir:.0f}% day_corr={day_corr:+.2f}" if np.isfinite(day_corr) else
              f"  {name}: |comp|={compensation_magnitude:.2f}U/h active={pct_active:.0f}% → TIR={tir:.0f}%")

    if save_fig:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt

            fig, axes = plt.subplots(1, 3, figsize=(18, 6))

            comp_mag = [r['compensation_magnitude'] for r in all_results]
            tirs = [r['tir'] for r in all_results]
            tbrs = [r['tbr'] for r in all_results]
            names = [r['patient'] for r in all_results]

            # Compensation vs TIR
            axes[0].scatter(comp_mag, tirs, s=80, c='#3498db')
            for r in all_results:
                axes[0].annotate(r['patient'], (r['compensation_magnitude'], r['tir']),
                                fontsize=9, ha='center', va='bottom')
            z = np.polyfit(comp_mag, tirs, 1)
            x_line = np.linspace(min(comp_mag), max(comp_mag), 50)
            axes[0].plot(x_line, np.polyval(z, x_line), '--', color='gray')
            corr_pop = float(np.corrcoef(comp_mag, tirs)[0, 1])
            axes[0].set_xlabel('Mean |net basal| compensation (U/h)')
            axes[0].set_ylabel('TIR (%)')
            axes[0].set_title(f'Loop Compensation vs TIR (r={corr_pop:.2f})')

            # Compensation vs TBR
            axes[1].scatter(comp_mag, tbrs, s=80, c='#e74c3c')
            for r in all_results:
                axes[1].annotate(r['patient'], (r['compensation_magnitude'], r['tbr']),
                                fontsize=9, ha='center', va='bottom')
            z2 = np.polyfit(comp_mag, tbrs, 1)
            axes[1].plot(x_line, np.polyval(z2, x_line), '--', color='gray')
            corr_tbr = float(np.corrcoef(comp_mag, tbrs)[0, 1])
            axes[1].set_xlabel('Mean |net basal| compensation (U/h)')
            axes[1].set_ylabel('TBR (%)')
            axes[1].set_title(f'Loop Compensation vs Hypo (r={corr_tbr:.2f})')

            # Day-level correlation histogram
            day_corrs = [r['day_level_corr'] for r in all_results if r['day_level_corr'] is not None]
            axes[2].hist(day_corrs, bins=10, color='#2c3e50', edgecolor='white')
            axes[2].axvline(0, color='red', linestyle='--')
            axes[2].set_xlabel('Day-level correlation (compensation → TIR)')
            axes[2].set_ylabel('Count')
            axes[2].set_title(f'Within-Patient Daily Correlation\n(mean={np.mean(day_corrs):.2f})')

            plt.tight_layout()
            plt.savefig(FIGURES_DIR / 'aid-fig06-compensation.png', dpi=150)
            plt.close()
            print(f"  → Saved aid-fig06-compensation.png")
        except Exception as e:
            print(f"  → Figure failed: {e}")

    pop_corr = np.corrcoef([r['compensation_magnitude'] for r in all_results],
                           [r['tir'] for r in all_results])[0, 1]
    verdict = f"COMP_TIR_CORR_{pop_corr:.2f}"
    print(f"\n  ✓ EXP-1966 verdict: {verdict}")
    return {'experiment': 'EXP-1966', 'verdict': verdict, 'per_patient': all_results}


# =====================================================================
def exp_1967(patients, save_fig=False):
    """When and why does the loop suspend insulin delivery?"""
    print("\n" + "=" * 70)
    print("EXP-1967: Delivery Suspension Analysis")
    print("=" * 70)

    all_results = []
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        temp_rate = df['temp_rate'].values if 'temp_rate' in df.columns else np.zeros(len(df))
        net_basal = df['net_basal'].values if 'net_basal' in df.columns else np.zeros(len(df))

        # Find suspension episodes (temp_rate == 0 for >= 2 consecutive readings)
        suspended = (temp_rate == 0).astype(int)
        episodes = []
        i = 0
        while i < len(suspended) - 2:
            if suspended[i] == 1 and suspended[i + 1] == 1:
                start = i
                while i < len(suspended) and suspended[i] == 1:
                    i += 1
                end = i
                duration = (end - start) * 5  # minutes

                # Context: glucose at start and during
                g_start = glucose[start] if np.isfinite(glucose[start]) else np.nan
                g_during = glucose[start:end]
                g_valid = g_during[np.isfinite(g_during)]
                g_min = float(np.min(g_valid)) if len(g_valid) > 0 else np.nan

                # Hour of day
                hour = (start % STEPS_PER_DAY) // STEPS_PER_HOUR

                # Was glucose actually low?
                was_low = g_start < 80 if np.isfinite(g_start) else False
                was_dropping = False
                if start > 3:
                    pre_g = glucose[start - 3:start]
                    valid_pre = pre_g[np.isfinite(pre_g)]
                    if len(valid_pre) > 1:
                        was_dropping = valid_pre[-1] < valid_pre[0] - 5

                episodes.append({
                    'start': int(start),
                    'duration_min': int(duration),
                    'g_start': float(g_start) if np.isfinite(g_start) else None,
                    'g_min': float(g_min) if np.isfinite(g_min) else None,
                    'hour': int(hour),
                    'was_low': bool(was_low),
                    'was_dropping': bool(was_dropping),
                })
            else:
                i += 1

        if len(episodes) == 0:
            all_results.append({
                'patient': name, 'n_episodes': 0, 'note': 'no suspensions detected'
            })
            print(f"  {name}: 0 suspensions")
            continue

        durations = [e['duration_min'] for e in episodes]
        hours = [e['hour'] for e in episodes]
        low_pct = sum(1 for e in episodes if e['was_low']) / len(episodes) * 100
        dropping_pct = sum(1 for e in episodes if e['was_dropping']) / len(episodes) * 100

        # Hour distribution
        hour_counts = np.zeros(24)
        for h in hours:
            hour_counts[h] += 1
        peak_hour = int(np.argmax(hour_counts))

        n_days = len(glucose) / STEPS_PER_DAY
        rate_per_day = len(episodes) / n_days

        result = {
            'patient': name,
            'n_episodes': len(episodes),
            'rate_per_day': float(rate_per_day),
            'mean_duration': float(np.mean(durations)),
            'median_duration': float(np.median(durations)),
            'pct_glucose_low': float(low_pct),
            'pct_glucose_dropping': float(dropping_pct),
            'peak_hour': peak_hour,
            'hour_distribution': hour_counts.tolist(),
        }
        all_results.append(result)

        print(f"  {name}: {len(episodes)} episodes ({rate_per_day:.1f}/day) "
              f"dur={np.median(durations):.0f}min low={low_pct:.0f}% dropping={dropping_pct:.0f}% "
              f"peak_hour={peak_hour}")

    if save_fig:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt

            fig, axes = plt.subplots(1, 3, figsize=(18, 6))

            valid_r = [r for r in all_results if r.get('n_episodes', 0) > 0 and 'rate_per_day' in r]
            names = [r['patient'] for r in valid_r]
            x = np.arange(len(names))

            # Suspension rate
            rates = [r['rate_per_day'] for r in valid_r]
            axes[0].bar(x, rates, color='#e74c3c')
            axes[0].set_xticks(x)
            axes[0].set_xticklabels(names)
            axes[0].set_ylabel('Suspensions per day')
            axes[0].set_title('Delivery Suspension Frequency')

            # Context (low vs dropping vs neither)
            low = [r['pct_glucose_low'] for r in valid_r]
            drop = [r['pct_glucose_dropping'] for r in valid_r]
            neither = [100 - l - d for l, d in zip(low, drop)]
            axes[1].bar(x, low, label='Glucose <80', color='#e74c3c')
            axes[1].bar(x, drop, bottom=low, label='Dropping', color='#f39c12')
            axes[1].bar(x, neither, bottom=[l + d for l, d in zip(low, drop)],
                       label='Other', color='#95a5a6')
            axes[1].set_xticks(x)
            axes[1].set_xticklabels(names)
            axes[1].set_ylabel('% of suspension events')
            axes[1].set_title('Suspension Context')
            axes[1].legend()

            # Hour distribution (population)
            pop_hours = np.zeros(24)
            for r in valid_r:
                if 'hour_distribution' in r:
                    pop_hours += np.array(r['hour_distribution'])
            axes[2].bar(range(24), pop_hours, color='#2c3e50')
            axes[2].axvspan(22, 24, alpha=0.1, color='blue')
            axes[2].axvspan(0, 6, alpha=0.1, color='blue')
            axes[2].set_xlabel('Hour of day')
            axes[2].set_ylabel('Total suspension events')
            axes[2].set_title('Suspension Timing Distribution')

            plt.tight_layout()
            plt.savefig(FIGURES_DIR / 'aid-fig07-suspension.png', dpi=150)
            plt.close()
            print(f"  → Saved aid-fig07-suspension.png")
        except Exception as e:
            print(f"  → Figure failed: {e}")

    valid_r = [r for r in all_results if r.get('n_episodes', 0) > 0 and 'rate_per_day' in r]
    pop_rate = np.mean([r['rate_per_day'] for r in valid_r]) if valid_r else 0
    pop_low = np.mean([r['pct_glucose_low'] for r in valid_r]) if valid_r else 0
    verdict = f"SUSPEND_{pop_rate:.1f}/day_LOW_{pop_low:.0f}%"
    print(f"\n  ✓ EXP-1967 verdict: {verdict}")
    return {'experiment': 'EXP-1967', 'verdict': verdict, 'per_patient': all_results}


# =====================================================================
def exp_1968(patients, save_fig=False):
    """Synthesize loop behavior into phenotypes and identify algorithm improvement targets."""
    print("\n" + "=" * 70)
    print("EXP-1968: Loop Behavior Phenotyping & Algorithm Targets")
    print("=" * 70)

    all_results = []
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        net_basal = df['net_basal'].values if 'net_basal' in df.columns else np.zeros(len(df))
        temp_rate = df['temp_rate'].values if 'temp_rate' in df.columns else np.zeros(len(df))
        iob = df['iob'].values if 'iob' in df.columns else np.zeros(len(df))
        pred30 = df['predicted_30'].values if 'predicted_30' in df.columns else np.full(len(df), np.nan)

        valid_g = glucose[np.isfinite(glucose)]
        if len(valid_g) < 1000:
            continue

        valid = np.isfinite(glucose) & np.isfinite(net_basal)
        g = glucose[valid]
        nb = net_basal[valid]

        # Metrics
        tir = float(np.mean((valid_g >= 70) & (valid_g <= 180)) * 100)
        tbr = float(np.mean(valid_g < 70) * 100)
        cv = float(np.std(valid_g) / np.mean(valid_g) * 100)
        comp_mag = float(np.mean(np.abs(nb)))

        # Loop mode: mostly increasing or mostly decreasing?
        pct_increasing = float((nb > 0.05).sum() / len(nb) * 100)
        pct_decreasing = float((nb < -0.05).sum() / len(nb) * 100)

        # Mean IOB
        valid_iob = iob[np.isfinite(iob)]
        mean_iob = float(np.mean(valid_iob)) if len(valid_iob) > 0 else 0

        # Prediction accuracy
        pred_errors = []
        for i in range(len(glucose) - 6):
            if np.isfinite(pred30[i]) and np.isfinite(glucose[i + 6]):
                pred_errors.append(glucose[i + 6] - pred30[i])
        pred_rmse = float(np.sqrt(np.mean(np.array(pred_errors) ** 2))) if pred_errors else np.nan

        # Phenotype classification
        phenotype = 'unknown'
        if tir >= 85 and tbr <= 4:
            phenotype = 'WELL_TUNED'
        elif tir >= 85 and tbr > 4:
            phenotype = 'TIGHT_WITH_HYPO'
        elif tir >= 70 and comp_mag > 0.3:
            phenotype = 'COMPENSATED'
        elif tir >= 70 and comp_mag <= 0.3:
            phenotype = 'MODERATE'
        elif tir < 70 and comp_mag > 0.3:
            phenotype = 'STRUGGLING'
        else:
            phenotype = 'UNDER_CONTROLLED'

        # Algorithm improvement target
        targets = []
        if tbr > 4:
            targets.append('REDUCE_HYPO')
        if pct_increasing > 40:
            targets.append('RAISE_BASAL')
        if pct_decreasing > 40:
            targets.append('LOWER_BASAL')
        if comp_mag > 0.5:
            targets.append('BETTER_SETTINGS')
        if pred_rmse > 30:
            targets.append('IMPROVE_PREDICTION')
        if cv > 36:
            targets.append('REDUCE_VARIABILITY')
        if not targets:
            targets.append('MAINTAIN')

        result = {
            'patient': name,
            'tir': tir,
            'tbr': tbr,
            'cv': cv,
            'compensation_magnitude': comp_mag,
            'pct_increasing': pct_increasing,
            'pct_decreasing': pct_decreasing,
            'mean_iob': mean_iob,
            'pred_rmse': float(pred_rmse) if np.isfinite(pred_rmse) else None,
            'phenotype': phenotype,
            'targets': targets,
        }
        all_results.append(result)

        print(f"  {name}: {phenotype} (TIR={tir:.0f}% comp={comp_mag:.2f}) → {', '.join(targets)}")

    if save_fig:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt

            fig, axes = plt.subplots(1, 3, figsize=(18, 6))

            # Panel 1: Phenotype scatter (compensation vs TIR)
            for r in all_results:
                color = {'WELL_TUNED': '#27ae60', 'TIGHT_WITH_HYPO': '#f39c12',
                         'COMPENSATED': '#3498db', 'MODERATE': '#95a5a6',
                         'STRUGGLING': '#e74c3c', 'UNDER_CONTROLLED': '#8e44ad'}.get(r['phenotype'], 'gray')
                axes[0].scatter(r['compensation_magnitude'], r['tir'], s=100, c=color,
                              edgecolors='black', linewidth=0.5, zorder=5)
                axes[0].annotate(f"{r['patient']}\n{r['phenotype']}", (r['compensation_magnitude'], r['tir']),
                                fontsize=7, ha='center', va='bottom')
            axes[0].set_xlabel('Loop compensation magnitude (U/h)')
            axes[0].set_ylabel('TIR (%)')
            axes[0].set_title('Loop Behavior Phenotypes')
            axes[0].axhline(70, color='gray', linestyle='--', alpha=0.3)
            axes[0].axhline(85, color='green', linestyle='--', alpha=0.3)

            # Panel 2: Target distribution
            all_targets = {}
            for r in all_results:
                for t in r['targets']:
                    all_targets[t] = all_targets.get(t, 0) + 1
            sorted_targets = sorted(all_targets.items(), key=lambda x: -x[1])
            tlabels = [t[0] for t in sorted_targets]
            tcounts = [t[1] for t in sorted_targets]
            axes[1].barh(range(len(tlabels)), tcounts, color='#3498db')
            axes[1].set_yticks(range(len(tlabels)))
            axes[1].set_yticklabels(tlabels, fontsize=8)
            axes[1].set_xlabel('Number of patients')
            axes[1].set_title('Algorithm Improvement Targets')

            # Panel 3: Summary table as text
            axes[2].axis('off')
            table_data = []
            for r in all_results:
                table_data.append([r['patient'], f"{r['tir']:.0f}%", r['phenotype'],
                                  ', '.join(r['targets'][:2])])
            table = axes[2].table(cellText=table_data,
                                 colLabels=['Patient', 'TIR', 'Phenotype', 'Top Targets'],
                                 loc='center', cellLoc='left')
            table.auto_set_font_size(False)
            table.set_fontsize(8)
            table.scale(1.0, 1.5)
            axes[2].set_title('Patient Summary')

            plt.tight_layout()
            plt.savefig(FIGURES_DIR / 'aid-fig08-phenotypes.png', dpi=150)
            plt.close()
            print(f"  → Saved aid-fig08-phenotypes.png")
        except Exception as e:
            print(f"  → Figure failed: {e}")

    # Phenotype distribution
    pheno_counts = {}
    for r in all_results:
        pheno_counts[r['phenotype']] = pheno_counts.get(r['phenotype'], 0) + 1
    pheno_str = ' '.join(f"{k}={v}" for k, v in sorted(pheno_counts.items(), key=lambda x: -x[1]))
    verdict = f"PHENOTYPES: {pheno_str}"
    print(f"\n  ✓ EXP-1968 verdict: {verdict}")
    return {'experiment': 'EXP-1968', 'verdict': verdict, 'per_patient': all_results}


# =====================================================================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--figures', action='store_true')
    args = parser.parse_args()

    patients = load_patients('externals/ns-data/patients/')
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 70)
    print("EXP-1961–1968: AID Loop Behavior Characterization")
    print("=" * 70)

    results = {}
    for exp_id, fn in [('EXP-1961', exp_1961), ('EXP-1962', exp_1962), ('EXP-1963', exp_1963),
                        ('EXP-1964', exp_1964), ('EXP-1965', exp_1965), ('EXP-1966', exp_1966),
                        ('EXP-1967', exp_1967), ('EXP-1968', exp_1968)]:
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
    print("SYNTHESIS: AID Loop Behavior Characterization")
    print("=" * 70)
    for k, v in results.items():
        print(f"  {k}: {v.get('verdict', 'N/A')}")


if __name__ == '__main__':
    main()
