#!/usr/bin/env python3
"""
EXP-2301 through EXP-2308: Meal Response Characterization

Analyzes individual meal responses to understand CR personalization,
meal timing effects, and the relationship between bolus timing and outcomes.

Experiments:
  2301: Meal detection and classification (carb vs UAM vs mixed)
  2302: Post-meal glucose trajectory profiles
  2303: Bolus timing effect on post-meal peak
  2304: Time-of-day CR variation
  2305: Meal size effect on absorption dynamics
  2306: Pre-meal glucose influence on outcomes
  2307: Insulin stacking and correction patterns
  2308: Meal response quality scorecard

Usage:
  PYTHONPATH=tools python3 tools/cgmencode/exp_meal_response_2301.py --figures
  PYTHONPATH=tools python3 tools/cgmencode/exp_meal_response_2301.py --figures --tiny
"""

import argparse
import json
import os
import warnings

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

warnings.filterwarnings('ignore')

STEPS_PER_HOUR = 12
STEP_MINUTES = 5


def load_patients_parquet(parquet_dir='externals/ns-parquet/training'):
    """Load patients from parquet — 40× faster than JSON."""
    grid = pd.read_parquet(os.path.join(parquet_dir, 'grid.parquet'))
    patients = []
    for pid in sorted(grid['patient_id'].unique()):
        pdf = grid[grid['patient_id'] == pid].copy()
        pdf = pdf.set_index('time').sort_index()
        profile = {
            'isf': float(pdf['scheduled_isf'].median()),
            'cr': float(pdf['scheduled_cr'].median()),
            'basal': float(pdf['scheduled_basal_rate'].median()),
        }
        patients.append({'name': pid, 'df': pdf, 'profile': profile})
        print(f"  {pid}: {len(pdf)} steps")
    return patients


def find_meals(df, min_carbs=5.0, min_gap_hours=2.0):
    """Find meal events from carb entries, separated by at least min_gap_hours."""
    carbs = df['carbs'].values
    glucose = df['glucose'].values
    bolus = df['bolus'].values
    idx = df.index

    meals = []
    last_meal_step = -min_gap_hours * STEPS_PER_HOUR
    for i in range(len(df)):
        if carbs[i] >= min_carbs and (i - last_meal_step) >= min_gap_hours * STEPS_PER_HOUR:
            # Extract post-meal trajectory (4 hours = 48 steps)
            window = 48  # 4 hours
            pre_window = 6  # 30 min before

            if i + window > len(df):
                continue

            post_bg = glucose[i:i + window]
            pre_bg = glucose[max(0, i - pre_window):i]

            # Skip if too many NaNs
            if np.isnan(post_bg).mean() > 0.3:
                continue

            start_bg = glucose[i] if not np.isnan(glucose[i]) else np.nanmean(pre_bg)
            if np.isnan(start_bg):
                continue

            # Find peak
            valid_post = np.where(~np.isnan(post_bg))[0]
            if len(valid_post) < 5:
                continue
            peak_idx = valid_post[np.nanargmax(post_bg[valid_post])]
            peak_bg = post_bg[peak_idx]
            peak_time_min = peak_idx * STEP_MINUTES

            # Bolus within ±30 min of carb entry
            bolus_window = bolus[max(0, i - 6):min(len(bolus), i + 6)]
            total_bolus = float(np.nansum(bolus_window))

            # IOB at meal time
            iob_at_meal = float(df['iob'].iloc[i]) if 'iob' in df.columns and not np.isnan(df['iob'].iloc[i]) else 0

            # Hour of day
            hour = idx[i].hour if hasattr(idx[i], 'hour') else pd.Timestamp(idx[i]).hour

            # 2-hour post-meal mean
            post_2h = glucose[i:i + 24]
            mean_2h = float(np.nanmean(post_2h)) if np.sum(~np.isnan(post_2h)) > 5 else np.nan

            meals.append({
                'step': i,
                'time': str(idx[i]),
                'hour': hour,
                'carbs': float(carbs[i]),
                'bolus': total_bolus,
                'iob': iob_at_meal,
                'start_bg': float(start_bg),
                'peak_bg': float(peak_bg),
                'rise': float(peak_bg - start_bg),
                'peak_time_min': int(peak_time_min),
                'mean_2h': mean_2h,
                'post_trajectory': post_bg.tolist(),
            })
            last_meal_step = i
    return meals


# ── Experiments ──────────────────────────────────────────────────────────

def exp_2301_classification(patients):
    """Meal detection and classification."""
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']

        # Find annotated meals (carbs > 0)
        carb_meals = find_meals(df, min_carbs=5.0)

        # Find UAM events (glucose rise > 30 mg/dL in 1h without carbs)
        glucose = df['glucose'].values
        carbs = df['carbs'].values
        roc = df['glucose_roc'].values if 'glucose_roc' in df.columns else np.full(len(df), np.nan)

        uam_events = 0
        for i in range(STEPS_PER_HOUR, len(df) - STEPS_PER_HOUR):
            # Check for sustained rise without carbs
            window_carbs = carbs[max(0, i - STEPS_PER_HOUR):i + STEPS_PER_HOUR]
            if np.nansum(window_carbs) > 1:
                continue
            if np.isnan(glucose[i]) or np.isnan(glucose[i - STEPS_PER_HOUR]):
                continue
            rise = glucose[i] - glucose[i - STEPS_PER_HOUR]
            if rise > 30:
                uam_events += 1

        # Classify meals by size
        small = [m for m in carb_meals if m['carbs'] < 20]
        medium = [m for m in carb_meals if 20 <= m['carbs'] < 50]
        large = [m for m in carb_meals if m['carbs'] >= 50]

        n_days = len(df) / (STEPS_PER_HOUR * 24)
        results[name] = {
            'total_meals': len(carb_meals),
            'meals_per_day': round(len(carb_meals) / n_days, 1),
            'uam_events_approx': uam_events,
            'uam_per_day': round(uam_events / n_days, 1),
            'small_meals': len(small),
            'medium_meals': len(medium),
            'large_meals': len(large),
            'mean_carbs': round(float(np.mean([m['carbs'] for m in carb_meals])), 1) if carb_meals else 0,
            'mean_rise': round(float(np.mean([m['rise'] for m in carb_meals])), 1) if carb_meals else 0,
            'mean_peak_time': round(float(np.mean([m['peak_time_min'] for m in carb_meals])), 0) if carb_meals else 0,
        }
        print(f"  {name}: {len(carb_meals)} meals ({len(carb_meals)/n_days:.1f}/day), ~{uam_events} UAM, mean rise={results[name]['mean_rise']:.0f}")
    return results


def exp_2302_trajectories(patients):
    """Post-meal glucose trajectory profiles."""
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        meals = find_meals(df, min_carbs=5.0)

        if not meals:
            results[name] = {'skipped': True}
            continue

        # Average trajectory (aligned to meal time)
        trajectories = []
        for m in meals:
            traj = np.array(m['post_trajectory'])
            # Normalize to start at 0
            start = m['start_bg']
            norm_traj = traj - start
            trajectories.append(norm_traj)

        # Pad to same length
        max_len = max(len(t) for t in trajectories)
        padded = np.full((len(trajectories), max_len), np.nan)
        for i, t in enumerate(trajectories):
            padded[i, :len(t)] = t

        mean_traj = np.nanmean(padded, axis=0)
        p25_traj = np.nanpercentile(padded, 25, axis=0)
        p75_traj = np.nanpercentile(padded, 75, axis=0)

        # Time to return to baseline
        above_5 = np.where(mean_traj > 5)[0]
        return_time = int(above_5[-1] * STEP_MINUTES) if len(above_5) > 0 else 0

        results[name] = {
            'n_meals': len(meals),
            'mean_trajectory': mean_traj.tolist(),
            'p25_trajectory': p25_traj.tolist(),
            'p75_trajectory': p75_traj.tolist(),
            'mean_peak_rise': round(float(np.nanmax(mean_traj)), 1),
            'mean_peak_time_min': int(np.nanargmax(mean_traj) * STEP_MINUTES),
            'return_to_baseline_min': return_time,
        }
        print(f"  {name}: peak +{results[name]['mean_peak_rise']:.0f} at {results[name]['mean_peak_time_min']}min, return at {return_time}min")
    return results


def exp_2303_bolus_timing(patients):
    """Bolus timing effect on post-meal peak."""
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        meals = find_meals(df, min_carbs=5.0)

        if len(meals) < 10:
            results[name] = {'skipped': True, 'reason': 'insufficient meals'}
            continue

        # Classify by bolus timing relative to carbs
        pre_bolus = []   # bolus > 0 before carb entry
        with_bolus = []  # bolus at same time as carbs
        no_bolus = []    # no bolus near carbs

        for m in meals:
            if m['bolus'] > 0.5:
                pre_bolus.append(m)  # simplified: any bolus near meal
            else:
                no_bolus.append(m)

        results[name] = {
            'n_with_bolus': len(pre_bolus),
            'n_no_bolus': len(no_bolus),
            'rise_with_bolus': round(float(np.mean([m['rise'] for m in pre_bolus])), 1) if pre_bolus else np.nan,
            'rise_no_bolus': round(float(np.mean([m['rise'] for m in no_bolus])), 1) if no_bolus else np.nan,
            'peak_time_with_bolus': round(float(np.mean([m['peak_time_min'] for m in pre_bolus])), 0) if pre_bolus else np.nan,
            'peak_time_no_bolus': round(float(np.mean([m['peak_time_min'] for m in no_bolus])), 0) if no_bolus else np.nan,
        }
        rise_b = results[name]['rise_with_bolus']
        rise_n = results[name]['rise_no_bolus']
        print(f"  {name}: bolus={len(pre_bolus)} (rise +{rise_b:.0f}), no_bolus={len(no_bolus)} (rise +{rise_n:.0f})" if not np.isnan(rise_n) else f"  {name}: bolus={len(pre_bolus)} (rise +{rise_b:.0f}), no_bolus=0")
    return results


def exp_2304_tod_cr(patients):
    """Time-of-day CR variation — effective CR by meal hour."""
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        profile = pat['profile']
        meals = find_meals(df, min_carbs=5.0)

        if len(meals) < 20:
            results[name] = {'skipped': True}
            continue

        # Group meals by time-of-day
        morning = [m for m in meals if 5 <= m['hour'] < 11]     # breakfast
        midday = [m for m in meals if 11 <= m['hour'] < 15]     # lunch
        afternoon = [m for m in meals if 15 <= m['hour'] < 19]  # snack/dinner
        evening = [m for m in meals if 19 <= m['hour'] or m['hour'] < 5]  # late meal

        periods = {'morning': morning, 'midday': midday, 'afternoon': afternoon, 'evening': evening}

        period_stats = {}
        for period_name, period_meals in periods.items():
            if len(period_meals) < 3:
                period_stats[period_name] = {'n': len(period_meals), 'skipped': True}
                continue

            rises = [m['rise'] for m in period_meals]
            carbs_list = [m['carbs'] for m in period_meals]
            boluses = [m['bolus'] for m in period_meals]

            # Effective CR = carbs / (rise / ISF) — how many carbs per unit rise
            # Alternatively: mean rise per gram of carb
            rise_per_g = float(np.mean([m['rise'] / m['carbs'] for m in period_meals if m['carbs'] > 0]))

            period_stats[period_name] = {
                'n': len(period_meals),
                'mean_rise': round(float(np.mean(rises)), 1),
                'mean_carbs': round(float(np.mean(carbs_list)), 1),
                'mean_bolus': round(float(np.mean(boluses)), 2),
                'rise_per_gram': round(rise_per_g, 2),
            }

        # Compute max/min ratio
        valid_rpg = [v['rise_per_gram'] for v in period_stats.values() if not v.get('skipped') and 'rise_per_gram' in v]
        cr_variation = round(max(valid_rpg) / min(valid_rpg), 2) if valid_rpg and min(valid_rpg) > 0 else np.nan

        results[name] = {
            'periods': period_stats,
            'cr_variation_ratio': cr_variation,
            'profile_cr': profile['cr'],
        }
        print(f"  {name}: CR variation={cr_variation:.1f}×" if not np.isnan(cr_variation) else f"  {name}: insufficient data")
    return results


def exp_2305_meal_size(patients):
    """Meal size effect on absorption dynamics."""
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        meals = find_meals(df, min_carbs=5.0)

        if len(meals) < 10:
            results[name] = {'skipped': True}
            continue

        # Bin by carb amount
        small = [m for m in meals if m['carbs'] < 20]
        medium = [m for m in meals if 20 <= m['carbs'] < 50]
        large = [m for m in meals if m['carbs'] >= 50]

        bins = {'small_lt20': small, 'medium_20_50': medium, 'large_gt50': large}
        bin_stats = {}
        for bin_name, bin_meals in bins.items():
            if len(bin_meals) < 3:
                bin_stats[bin_name] = {'n': len(bin_meals), 'skipped': True}
                continue

            bin_stats[bin_name] = {
                'n': len(bin_meals),
                'mean_carbs': round(float(np.mean([m['carbs'] for m in bin_meals])), 1),
                'mean_rise': round(float(np.mean([m['rise'] for m in bin_meals])), 1),
                'mean_peak_time': round(float(np.mean([m['peak_time_min'] for m in bin_meals])), 0),
                'rise_per_gram': round(float(np.mean([m['rise'] / m['carbs'] for m in bin_meals if m['carbs'] > 0])), 2),
            }

        # Does rise scale linearly with carbs?
        all_carbs = np.array([m['carbs'] for m in meals])
        all_rises = np.array([m['rise'] for m in meals])
        mask = ~np.isnan(all_rises)
        if mask.sum() > 10:
            corr = float(np.corrcoef(all_carbs[mask], all_rises[mask])[0, 1])
        else:
            corr = np.nan

        results[name] = {
            'bins': bin_stats,
            'carb_rise_correlation': round(corr, 3),
            'n_meals': len(meals),
        }
        print(f"  {name}: carb-rise r={corr:.2f}, {len(meals)} meals")
    return results


def exp_2306_pre_meal_bg(patients):
    """Pre-meal glucose influence on outcomes."""
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        meals = find_meals(df, min_carbs=5.0)

        if len(meals) < 10:
            results[name] = {'skipped': True}
            continue

        # Group by starting BG
        low_start = [m for m in meals if m['start_bg'] < 100]
        normal_start = [m for m in meals if 100 <= m['start_bg'] < 150]
        high_start = [m for m in meals if m['start_bg'] >= 150]

        groups = {'low_lt100': low_start, 'normal_100_150': normal_start, 'high_gt150': high_start}
        group_stats = {}
        for group_name, group_meals in groups.items():
            if len(group_meals) < 3:
                group_stats[group_name] = {'n': len(group_meals), 'skipped': True}
                continue

            group_stats[group_name] = {
                'n': len(group_meals),
                'mean_start': round(float(np.mean([m['start_bg'] for m in group_meals])), 1),
                'mean_rise': round(float(np.mean([m['rise'] for m in group_meals])), 1),
                'mean_peak': round(float(np.mean([m['peak_bg'] for m in group_meals])), 1),
                'mean_2h': round(float(np.nanmean([m['mean_2h'] for m in group_meals if not np.isnan(m['mean_2h'])])), 1),
                'pct_hyper_after': round(float(np.mean([1 for m in group_meals if m['peak_bg'] > 180]) / len(group_meals) * 100), 1),
            }

        results[name] = {
            'groups': group_stats,
            'n_meals': len(meals),
        }
        # Summarize
        for gn, gs in group_stats.items():
            if not gs.get('skipped'):
                print(f"  {name} [{gn}]: n={gs['n']}, rise=+{gs['mean_rise']:.0f}, {gs['pct_hyper_after']:.0f}% hyper")
    return results


def exp_2307_stacking(patients):
    """Insulin stacking and correction patterns post-meal."""
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        meals = find_meals(df, min_carbs=5.0)

        if len(meals) < 10:
            results[name] = {'skipped': True}
            continue

        # For each meal, check if additional boluses follow within 2h
        bolus = df['bolus'].values
        stacking_events = 0
        total_extra_insulin = []

        for m in meals:
            step = m['step']
            # Check for additional boluses 30min-2h after meal
            post_bolus = bolus[step + 6:step + 24]  # 30min to 2h
            extra = float(np.nansum(post_bolus))
            if extra > 0.1:
                stacking_events += 1
                total_extra_insulin.append(extra)

        stacking_rate = stacking_events / len(meals) * 100 if meals else 0
        mean_extra = float(np.mean(total_extra_insulin)) if total_extra_insulin else 0

        # Compare outcomes: stacking vs no stacking
        stacked_meals = []
        clean_meals = []
        for m in meals:
            step = m['step']
            post_bolus = bolus[step + 6:step + 24]
            if float(np.nansum(post_bolus)) > 0.1:
                stacked_meals.append(m)
            else:
                clean_meals.append(m)

        results[name] = {
            'n_meals': len(meals),
            'stacking_events': stacking_events,
            'stacking_rate': round(stacking_rate, 1),
            'mean_extra_insulin': round(mean_extra, 2),
            'stacked_mean_rise': round(float(np.mean([m['rise'] for m in stacked_meals])), 1) if stacked_meals else np.nan,
            'clean_mean_rise': round(float(np.mean([m['rise'] for m in clean_meals])), 1) if clean_meals else np.nan,
            'stacked_mean_2h': round(float(np.nanmean([m['mean_2h'] for m in stacked_meals if not np.isnan(m['mean_2h'])])), 1) if stacked_meals else np.nan,
            'clean_mean_2h': round(float(np.nanmean([m['mean_2h'] for m in clean_meals if not np.isnan(m['mean_2h'])])), 1) if clean_meals else np.nan,
        }
        print(f"  {name}: {stacking_rate:.0f}% stacking ({stacking_events}/{len(meals)}), extra={mean_extra:.1f}U")
    return results


def exp_2308_scorecard(patients, all_results):
    """Meal response quality scorecard."""
    results = {}
    for pat in patients:
        name = pat['name']

        r2301 = all_results.get('exp_2301', {}).get(name, {})
        r2302 = all_results.get('exp_2302', {}).get(name, {})
        r2304 = all_results.get('exp_2304', {}).get(name, {})
        r2305 = all_results.get('exp_2305', {}).get(name, {})
        r2307 = all_results.get('exp_2307', {}).get(name, {})

        if r2302.get('skipped') or r2305.get('skipped'):
            results[name] = {'skipped': True}
            continue

        # Score components (0-100 each)
        scores = {}

        # 1. Peak control: <40 rise = 100, >80 rise = 0
        peak = r2302.get('mean_peak_rise', 60)
        scores['peak_control'] = max(0, min(100, 100 - (peak - 40) * 100 / 40))

        # 2. Return speed: <120min = 100, >240min = 0
        ret = r2302.get('return_to_baseline_min', 180)
        scores['return_speed'] = max(0, min(100, 100 - (ret - 120) * 100 / 120))

        # 3. CR consistency: variation < 1.5 = 100, > 3.0 = 0
        var = r2304.get('cr_variation_ratio', 2.0) if not r2304.get('skipped') else 2.0
        scores['cr_consistency'] = max(0, min(100, 100 - (var - 1.5) * 100 / 1.5))

        # 4. Carb-rise linearity: r > 0.5 = 100, r < 0 = 0
        corr = r2305.get('carb_rise_correlation', 0.2)
        scores['linearity'] = max(0, min(100, corr * 200))

        # 5. Low stacking: < 10% = 100, > 50% = 0
        stack = r2307.get('stacking_rate', 20) if not r2307.get('skipped') else 20
        scores['low_stacking'] = max(0, min(100, 100 - (stack - 10) * 100 / 40))

        overall = round(float(np.mean(list(scores.values()))), 1)

        # Grade
        if overall >= 80: grade = 'A'
        elif overall >= 60: grade = 'B'
        elif overall >= 40: grade = 'C'
        else: grade = 'D'

        results[name] = {
            'scores': {k: round(v, 1) for k, v in scores.items()},
            'overall': overall,
            'grade': grade,
            'meals_per_day': r2301.get('meals_per_day', 0),
        }
        print(f"  {name}: {grade} ({overall:.0f}/100) — peak={scores['peak_control']:.0f}, return={scores['return_speed']:.0f}, CR={scores['cr_consistency']:.0f}")
    return results


# ── Figures ──────────────────────────────────────────────────────────────

def generate_figures(results, patients, fig_dir):
    os.makedirs(fig_dir, exist_ok=True)
    names = sorted([p['name'] for p in patients])

    # Fig 1: Meal classification
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    r2301 = results['exp_2301']
    x = np.arange(len(names))
    mpd = [r2301[n]['meals_per_day'] for n in names]
    uam = [r2301[n]['uam_per_day'] for n in names]
    axes[0].bar(x, mpd, color='steelblue', alpha=0.7, label='Annotated meals/day')
    axes[0].bar(x, uam, bottom=mpd, color='orange', alpha=0.5, label='UAM events/day (approx)')
    axes[0].set_xticks(x); axes[0].set_xticklabels(names)
    axes[0].set_ylabel('Events/day'); axes[0].legend()
    axes[0].set_title('Meal Frequency')

    rises = [r2301[n]['mean_rise'] for n in names]
    axes[1].bar(x, rises, color='coral', alpha=0.7)
    axes[1].axhline(40, color='green', ls='--', label='Good (<40)')
    axes[1].axhline(80, color='red', ls='--', label='Poor (>80)')
    axes[1].set_xticks(x); axes[1].set_xticklabels(names)
    axes[1].set_ylabel('Mean Rise (mg/dL)'); axes[1].legend()
    axes[1].set_title('Mean Post-Meal Rise')
    fig.suptitle('EXP-2301: Meal Classification', fontsize=14, fontweight='bold')
    plt.tight_layout(); plt.savefig(f'{fig_dir}/meal-fig01-classification.png', dpi=150, bbox_inches='tight'); plt.close()
    print("  Figure 1: classification")

    # Fig 2: Average trajectories
    fig, axes = plt.subplots(3, 4, figsize=(16, 10))
    axes = axes.flatten()
    r2302 = results['exp_2302']
    for idx, name in enumerate(names):
        if idx >= 11: break
        ax = axes[idx]
        data = r2302.get(name, {})
        if data.get('skipped'):
            ax.text(0.5, 0.5, 'No data', ha='center', va='center', transform=ax.transAxes)
            ax.set_title(name)
            continue
        t = np.arange(len(data['mean_trajectory'])) * STEP_MINUTES
        ax.fill_between(t, data['p25_trajectory'], data['p75_trajectory'], alpha=0.2, color='blue')
        ax.plot(t, data['mean_trajectory'], 'b-', lw=2)
        ax.axhline(0, color='black', lw=0.5, ls='--')
        ax.set_title(f"{name}: +{data['mean_peak_rise']:.0f} at {data['mean_peak_time_min']}min")
        ax.set_xlim(0, 240); ax.set_xlabel('min')
    axes[-1].axis('off')
    fig.suptitle('EXP-2302: Post-Meal Glucose Trajectories (normalized)', fontsize=14, fontweight='bold')
    plt.tight_layout(); plt.savefig(f'{fig_dir}/meal-fig02-trajectories.png', dpi=150, bbox_inches='tight'); plt.close()
    print("  Figure 2: trajectories")

    # Fig 3: Bolus timing
    fig, ax = plt.subplots(figsize=(12, 5))
    r2303 = results['exp_2303']
    valid = [n for n in names if not r2303.get(n, {}).get('skipped')]
    x = np.arange(len(valid))
    wb = [r2303[n]['rise_with_bolus'] for n in valid]
    nb = [r2303[n].get('rise_no_bolus', 0) for n in valid]
    nb = [v if not np.isnan(v) else 0 for v in nb]
    w = 0.35
    ax.bar(x - w/2, wb, w, label='With bolus', color='steelblue', alpha=0.7)
    ax.bar(x + w/2, nb, w, label='No bolus', color='orange', alpha=0.7)
    ax.set_xticks(x); ax.set_xticklabels(valid)
    ax.set_ylabel('Mean Rise (mg/dL)'); ax.legend()
    ax.set_title('EXP-2303: Post-Meal Rise by Bolus Presence')
    plt.tight_layout(); plt.savefig(f'{fig_dir}/meal-fig03-bolus-timing.png', dpi=150, bbox_inches='tight'); plt.close()
    print("  Figure 3: bolus timing")

    # Fig 4: Time-of-day CR
    fig, axes = plt.subplots(3, 4, figsize=(16, 10))
    axes = axes.flatten()
    r2304 = results['exp_2304']
    for idx, name in enumerate(names):
        if idx >= 11: break
        ax = axes[idx]
        data = r2304.get(name, {})
        if data.get('skipped'):
            ax.text(0.5, 0.5, 'No data', ha='center', va='center', transform=ax.transAxes)
            ax.set_title(name)
            continue
        periods = data['periods']
        period_names = ['morning', 'midday', 'afternoon', 'evening']
        rpg = []
        for pn in period_names:
            if pn in periods and not periods[pn].get('skipped'):
                rpg.append(periods[pn]['rise_per_gram'])
            else:
                rpg.append(0)
        ax.bar(range(4), rpg, color=['gold', 'orange', 'coral', 'purple'], alpha=0.7)
        ax.set_xticks(range(4)); ax.set_xticklabels(['Morn', 'Mid', 'Aft', 'Eve'], fontsize=8)
        ax.set_ylabel('mg/dL per g', fontsize=8)
        ax.set_title(f"{name}: var={data['cr_variation_ratio']:.1f}×" if not np.isnan(data.get('cr_variation_ratio', np.nan)) else name)
    axes[-1].axis('off')
    fig.suptitle('EXP-2304: Rise per Gram of Carb by Time of Day', fontsize=14, fontweight='bold')
    plt.tight_layout(); plt.savefig(f'{fig_dir}/meal-fig04-tod-cr.png', dpi=150, bbox_inches='tight'); plt.close()
    print("  Figure 4: TOD CR")

    # Fig 5: Meal size
    fig, ax = plt.subplots(figsize=(12, 5))
    r2305 = results['exp_2305']
    valid = [n for n in names if not r2305.get(n, {}).get('skipped')]
    x = np.arange(len(valid))
    corrs = [r2305[n]['carb_rise_correlation'] for n in valid]
    colors = ['green' if c > 0.3 else 'orange' if c > 0 else 'red' for c in corrs]
    ax.bar(x, corrs, color=colors, alpha=0.7)
    ax.axhline(0.3, color='green', ls='--', alpha=0.5, label='r=0.3')
    ax.axhline(0, color='black', lw=0.5)
    ax.set_xticks(x); ax.set_xticklabels(valid)
    ax.set_ylabel('Correlation (r)'); ax.legend()
    ax.set_title('EXP-2305: Carb Amount vs Glucose Rise Correlation')
    plt.tight_layout(); plt.savefig(f'{fig_dir}/meal-fig05-meal-size.png', dpi=150, bbox_inches='tight'); plt.close()
    print("  Figure 5: meal size")

    # Fig 6: Pre-meal BG effect
    fig, axes = plt.subplots(3, 4, figsize=(16, 10))
    axes = axes.flatten()
    r2306 = results['exp_2306']
    for idx, name in enumerate(names):
        if idx >= 11: break
        ax = axes[idx]
        data = r2306.get(name, {})
        if data.get('skipped'):
            ax.text(0.5, 0.5, 'No data', ha='center', va='center', transform=ax.transAxes)
            ax.set_title(name)
            continue
        groups = data['groups']
        gnames = ['low_lt100', 'normal_100_150', 'high_gt150']
        glabels = ['<100', '100-150', '>150']
        rises = [groups[g]['mean_rise'] if g in groups and not groups[g].get('skipped') else 0 for g in gnames]
        ax.bar(range(3), rises, color=['blue', 'green', 'red'], alpha=0.7)
        ax.set_xticks(range(3)); ax.set_xticklabels(glabels, fontsize=8)
        ax.set_ylabel('Rise (mg/dL)', fontsize=8)
        ax.set_title(name)
    axes[-1].axis('off')
    fig.suptitle('EXP-2306: Post-Meal Rise by Pre-Meal Glucose', fontsize=14, fontweight='bold')
    plt.tight_layout(); plt.savefig(f'{fig_dir}/meal-fig06-pre-meal-bg.png', dpi=150, bbox_inches='tight'); plt.close()
    print("  Figure 6: pre-meal BG")

    # Fig 7: Stacking
    fig, ax = plt.subplots(figsize=(12, 5))
    r2307 = results['exp_2307']
    valid = [n for n in names if not r2307.get(n, {}).get('skipped')]
    x = np.arange(len(valid))
    rates = [r2307[n]['stacking_rate'] for n in valid]
    ax.bar(x, rates, color='mediumpurple', alpha=0.7)
    ax.axhline(25, color='red', ls='--', label='High stacking (>25%)')
    ax.set_xticks(x); ax.set_xticklabels(valid)
    ax.set_ylabel('Stacking Rate (%)'); ax.legend()
    ax.set_title('EXP-2307: Insulin Stacking Rate (additional bolus within 2h of meal)')
    plt.tight_layout(); plt.savefig(f'{fig_dir}/meal-fig07-stacking.png', dpi=150, bbox_inches='tight'); plt.close()
    print("  Figure 7: stacking")

    # Fig 8: Scorecard
    fig, ax = plt.subplots(figsize=(14, 6))
    r2308 = results['exp_2308']
    valid = [n for n in names if not r2308.get(n, {}).get('skipped')]
    categories = ['peak_control', 'return_speed', 'cr_consistency', 'linearity', 'low_stacking']
    cat_labels = ['Peak\nControl', 'Return\nSpeed', 'CR\nConsist.', 'Linearity', 'Low\nStacking']
    data_matrix = np.array([[r2308[n]['scores'][c] for c in categories] for n in valid])
    im = ax.imshow(data_matrix.T, aspect='auto', cmap='RdYlGn', vmin=0, vmax=100)
    ax.set_xticks(range(len(valid))); ax.set_xticklabels(valid)
    ax.set_yticks(range(len(cat_labels))); ax.set_yticklabels(cat_labels)
    # Add text
    for i in range(len(valid)):
        for j in range(len(categories)):
            val = data_matrix[i, j]
            ax.text(i, j, f'{val:.0f}', ha='center', va='center', fontsize=9,
                    color='white' if val < 40 else 'black')
        # Add grade on top
        grade = r2308[valid[i]]['grade']
        overall = r2308[valid[i]]['overall']
        ax.text(i, -0.6, f'{grade} ({overall:.0f})', ha='center', va='center', fontsize=10, fontweight='bold')
    plt.colorbar(im, label='Score (0-100)')
    ax.set_title('EXP-2308: Meal Response Quality Scorecard', fontsize=14, fontweight='bold')
    plt.tight_layout(); plt.savefig(f'{fig_dir}/meal-fig08-scorecard.png', dpi=150, bbox_inches='tight'); plt.close()
    print("  Figure 8: scorecard")


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--figures', action='store_true')
    parser.add_argument('--tiny', action='store_true', help='Use tiny parquet for fast dev')
    args = parser.parse_args()

    parquet_dir = 'externals/ns-parquet-tiny/training' if args.tiny else 'externals/ns-parquet/training'
    print(f"Loading patients from {parquet_dir}...")
    patients = load_patients_parquet(parquet_dir)
    print(f"Loaded {len(patients)} patients\n")

    results = {}

    print("Running exp_2301: Meal Classification...")
    results['exp_2301'] = exp_2301_classification(patients)
    print("  ✓ completed\n")

    print("Running exp_2302: Trajectory Profiles...")
    results['exp_2302'] = exp_2302_trajectories(patients)
    print("  ✓ completed\n")

    print("Running exp_2303: Bolus Timing...")
    results['exp_2303'] = exp_2303_bolus_timing(patients)
    print("  ✓ completed\n")

    print("Running exp_2304: Time-of-Day CR...")
    results['exp_2304'] = exp_2304_tod_cr(patients)
    print("  ✓ completed\n")

    print("Running exp_2305: Meal Size...")
    results['exp_2305'] = exp_2305_meal_size(patients)
    print("  ✓ completed\n")

    print("Running exp_2306: Pre-Meal BG...")
    results['exp_2306'] = exp_2306_pre_meal_bg(patients)
    print("  ✓ completed\n")

    print("Running exp_2307: Insulin Stacking...")
    results['exp_2307'] = exp_2307_stacking(patients)
    print("  ✓ completed\n")

    print("Running exp_2308: Scorecard...")
    results['exp_2308'] = exp_2308_scorecard(patients, results)
    print("  ✓ completed\n")

    out_path = 'externals/experiments/exp-2301-2308_meal_response.json'
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    def convert(obj):
        if isinstance(obj, (np.integer,)): return int(obj)
        if isinstance(obj, (np.floating,)): return float(obj)
        if isinstance(obj, np.ndarray): return obj.tolist()
        if isinstance(obj, (np.bool_,)): return bool(obj)
        raise TypeError(f"Not serializable: {type(obj)}")
    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2, default=convert)
    print(f"Results saved to {out_path}")

    if args.figures:
        print("\nGenerating figures...")
        generate_figures(results, patients, 'docs/60-research/figures')
        print("All figures generated.")


if __name__ == '__main__':
    main()
