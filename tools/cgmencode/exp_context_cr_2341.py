#!/usr/bin/env python3
"""
EXP-2341 through EXP-2348: Context-Aware Carb Ratio Analysis

Single CR explains <16% of glucose rise variance (EXP-2301). This batch
builds context-aware CR models incorporating pre-meal BG, time of day,
IOB, and recent activity to improve meal coverage predictions.

Experiments:
  2341: Pre-meal glucose effect on post-meal rise
  2342: Time-of-day CR variation (circadian insulin sensitivity)
  2343: IOB effect on meal response (stacking quantification)
  2344: Multi-factor CR model (combined context features)
  2345: Optimal meal bolus simulation
  2346: Patient-specific vs population CR models
  2347: Meal classification (type inference from glucose trajectory)
  2348: Comprehensive CR recommendation engine

Usage:
  PYTHONPATH=tools python3 tools/cgmencode/exp_context_cr_2341.py --figures
  PYTHONPATH=tools python3 tools/cgmencode/exp_context_cr_2341.py --figures --tiny
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
from scipy import stats

warnings.filterwarnings('ignore')

STEPS_PER_HOUR = 12


def load_patients_parquet(parquet_dir='externals/ns-parquet/training'):
    grid = pd.read_parquet(os.path.join(parquet_dir, 'grid.parquet'))
    patients = []
    for pid in sorted(grid['patient_id'].unique()):
        pdf = grid[grid['patient_id'] == pid].copy()
        pdf = pdf.set_index('time').sort_index()
        patients.append({'name': pid, 'df': pdf})
        print(f"  {pid}: {len(pdf)} steps")
    return patients


def find_meals(df, min_carbs=5):
    """Find meal events with context windows."""
    bg = df['glucose'].values
    carbs = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(df))
    iob = df['iob'].values if 'iob' in df.columns else np.zeros(len(df))
    bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(len(df))
    cr = df['scheduled_cr'].values if 'scheduled_cr' in df.columns else np.full(len(df), 10)
    isf = df['scheduled_isf'].values if 'scheduled_isf' in df.columns else np.full(len(df), 50)
    
    meals = []
    i = 0
    while i < len(df) - 36:  # Need 3h post-meal window
        if not np.isnan(carbs[i]) and carbs[i] >= min_carbs:
            # Pre-meal context
            pre_bg = bg[max(0, i-3):i+1]  # 15min before
            pre_bg_valid = pre_bg[~np.isnan(pre_bg)]
            if len(pre_bg_valid) == 0:
                i += 6
                continue
            
            # Post-meal window (3 hours)
            post_bg = bg[i:i+36]
            post_valid = ~np.isnan(post_bg)
            if post_valid.sum() < 12:  # Need at least 1h of data
                i += 6
                continue
            
            # Peak rise
            post_max = np.nanmax(post_bg)
            pre_mean = float(np.mean(pre_bg_valid))
            rise = post_max - pre_mean
            
            # Time to peak
            peak_idx = np.nanargmax(post_bg)
            time_to_peak = peak_idx * 5  # minutes
            
            # IOB at meal
            iob_at_meal = float(iob[i]) if not np.isnan(iob[i]) else 0
            
            # Bolus within ±30 min
            bolus_window = bolus[max(0, i-6):i+7]
            total_bolus = float(np.nansum(bolus_window))
            
            # Hour of day
            hour = df.index[i].hour + df.index[i].minute / 60
            
            # 3h post-meal BG
            end_bg = post_bg[-6:]
            end_bg_valid = end_bg[~np.isnan(end_bg)]
            bg_3h = float(np.mean(end_bg_valid)) if len(end_bg_valid) > 0 else np.nan
            
            meals.append({
                'idx': i,
                'time': df.index[i],
                'carbs': float(carbs[i]),
                'pre_bg': pre_mean,
                'peak_bg': float(post_max),
                'rise': float(rise),
                'bg_3h': bg_3h,
                'time_to_peak': int(time_to_peak),
                'iob': iob_at_meal,
                'bolus': total_bolus,
                'hour': float(hour),
                'cr': float(cr[i]) if not np.isnan(cr[i]) else 10,
                'isf': float(isf[i]) if not np.isnan(isf[i]) else 50,
            })
            
            # Skip ahead to avoid double-counting
            i += 12  # 1 hour minimum gap
        else:
            i += 1
    
    return meals


# ── Experiments ──────────────────────────────────────────────────────────

def exp_2341_premeal(patients):
    """Pre-meal glucose effect on post-meal rise."""
    results = {}
    for pat in patients:
        name = pat['name']
        meals = find_meals(pat['df'])
        
        if len(meals) < 20:
            results[name] = {'skipped': True, 'n_meals': len(meals)}
            print(f"  {name}: skipped ({len(meals)} meals)")
            continue
        
        pre_bg = np.array([m['pre_bg'] for m in meals])
        rise = np.array([m['rise'] for m in meals])
        carbs = np.array([m['carbs'] for m in meals])
        
        # Correlation between pre-meal BG and rise
        valid = (~np.isnan(pre_bg)) & (~np.isnan(rise))
        if valid.sum() < 20:
            results[name] = {'skipped': True}
            continue
        
        r_prebg_rise, p = stats.pearsonr(pre_bg[valid], rise[valid])
        r_carbs_rise, p2 = stats.pearsonr(carbs[valid], rise[valid])
        
        # Pre-meal BG quartile analysis
        quartiles = np.quantile(pre_bg[valid], [0.25, 0.5, 0.75])
        by_premeal = {}
        labels = ['Q1_low', 'Q2', 'Q3', 'Q4_high']
        bounds = [0, quartiles[0], quartiles[1], quartiles[2], 500]
        for j in range(4):
            mask = valid & (pre_bg >= bounds[j]) & (pre_bg < bounds[j+1])
            if mask.sum() > 3:
                by_premeal[labels[j]] = {
                    'mean_pre_bg': round(float(np.mean(pre_bg[mask])), 0),
                    'mean_rise': round(float(np.mean(rise[mask])), 1),
                    'mean_carbs': round(float(np.mean(carbs[mask])), 1),
                    'n': int(mask.sum()),
                }
        
        # Effective CR: how many mg/dL does each gram of carb raise glucose?
        # Simple: rise / carbs
        effective_cr_ratio = rise[valid] / (carbs[valid] + 1e-8)
        
        results[name] = {
            'n_meals': len(meals),
            'r_premeal_rise': round(float(r_prebg_rise), 3),
            'r_carbs_rise': round(float(r_carbs_rise), 3),
            'premeal_explains_pct': round(float(r_prebg_rise**2 * 100), 1),
            'carbs_explain_pct': round(float(r_carbs_rise**2 * 100), 1),
            'by_premeal': by_premeal,
            'mean_effective_cr_ratio': round(float(np.mean(effective_cr_ratio)), 2),
        }
        print(f"  {name}: pre-meal r={r_prebg_rise:.2f} ({r_prebg_rise**2*100:.0f}%), "
              f"carbs r={r_carbs_rise:.2f} ({r_carbs_rise**2*100:.0f}%), {len(meals)} meals")
    return results


def exp_2342_circadian_cr(patients):
    """Time-of-day CR variation."""
    results = {}
    for pat in patients:
        name = pat['name']
        meals = find_meals(pat['df'])
        
        if len(meals) < 30:
            results[name] = {'skipped': True}
            continue
        
        # Bin meals by time period
        periods = {
            'breakfast': (5, 10),
            'lunch': (10, 14),
            'afternoon': (14, 18),
            'dinner': (18, 22),
            'night': (22, 5),  # wraps
        }
        
        by_period = {}
        for period, (start, end) in periods.items():
            if period == 'night':
                mask = [m['hour'] >= 22 or m['hour'] < 5 for m in meals]
            else:
                mask = [start <= m['hour'] < end for m in meals]
            
            period_meals = [m for m, keep in zip(meals, mask) if keep]
            if len(period_meals) < 3:
                continue
            
            rises = [m['rise'] for m in period_meals]
            carbs_vals = [m['carbs'] for m in period_meals]
            
            # Effective mg/dL per gram
            ratios = [r / (c + 1e-8) for r, c in zip(rises, carbs_vals)]
            
            by_period[period] = {
                'n_meals': len(period_meals),
                'mean_rise': round(float(np.mean(rises)), 1),
                'mean_carbs': round(float(np.mean(carbs_vals)), 1),
                'mean_ratio': round(float(np.mean(ratios)), 2),
                'std_ratio': round(float(np.std(ratios)), 2),
            }
        
        if not by_period:
            results[name] = {'skipped': True}
            continue
        
        # Circadian range
        ratios = [v['mean_ratio'] for v in by_period.values()]
        cr_range = max(ratios) / (min(ratios) + 1e-8) if ratios else 1
        
        results[name] = {
            'by_period': by_period,
            'cr_range_ratio': round(float(cr_range), 1),
            'most_sensitive_period': max(by_period.items(), key=lambda x: x[1]['mean_ratio'])[0],
            'least_sensitive_period': min(by_period.items(), key=lambda x: x[1]['mean_ratio'])[0],
        }
        print(f"  {name}: CR range {cr_range:.1f}×, "
              f"most sensitive={results[name]['most_sensitive_period']}")
    return results


def exp_2343_iob_effect(patients):
    """IOB effect on meal response."""
    results = {}
    for pat in patients:
        name = pat['name']
        meals = find_meals(pat['df'])
        
        if len(meals) < 20:
            results[name] = {'skipped': True}
            continue
        
        iob_vals = np.array([m['iob'] for m in meals])
        rise_vals = np.array([m['rise'] for m in meals])
        bolus_vals = np.array([m['bolus'] for m in meals])
        carbs_vals = np.array([m['carbs'] for m in meals])
        
        valid = ~np.isnan(iob_vals)
        if valid.sum() < 20:
            results[name] = {'skipped': True}
            continue
        
        # IOB-rise correlation
        r_iob_rise, p = stats.pearsonr(iob_vals[valid], rise_vals[valid])
        
        # IOB quartile analysis
        iob_q = np.quantile(iob_vals[valid], [0.25, 0.5, 0.75])
        by_iob = {}
        labels = ['Q1_low', 'Q2', 'Q3', 'Q4_high']
        bounds = [iob_vals[valid].min() - 0.1, iob_q[0], iob_q[1], iob_q[2], iob_vals[valid].max() + 0.1]
        for j in range(4):
            mask = valid & (iob_vals >= bounds[j]) & (iob_vals < bounds[j+1])
            if mask.sum() > 3:
                by_iob[labels[j]] = {
                    'mean_iob': round(float(np.mean(iob_vals[mask])), 2),
                    'mean_rise': round(float(np.mean(rise_vals[mask])), 1),
                    'mean_carbs': round(float(np.mean(carbs_vals[mask])), 1),
                    'n': int(mask.sum()),
                }
        
        # Stacking detection: meals with IOB > 50% of bolus
        stacking = iob_vals[valid] > bolus_vals[valid] * 0.5
        stacking_rate = float(stacking.mean() * 100)
        
        results[name] = {
            'r_iob_rise': round(float(r_iob_rise), 3),
            'by_iob': by_iob,
            'stacking_rate': round(stacking_rate, 1),
            'mean_iob_at_meal': round(float(np.mean(iob_vals[valid])), 2),
        }
        print(f"  {name}: IOB-rise r={r_iob_rise:.2f}, stacking={stacking_rate:.0f}%")
    return results


def exp_2344_multifactor(patients):
    """Multi-factor CR model."""
    results = {}
    for pat in patients:
        name = pat['name']
        meals = find_meals(pat['df'])
        
        if len(meals) < 30:
            results[name] = {'skipped': True}
            continue
        
        # Build feature matrix
        X = np.array([
            [m['carbs'], m['pre_bg'], m['iob'],
             np.sin(2 * np.pi * m['hour'] / 24),
             np.cos(2 * np.pi * m['hour'] / 24),
             m['bolus']]
            for m in meals
        ])
        y = np.array([m['rise'] for m in meals])
        
        valid = ~np.any(np.isnan(X), axis=1) & ~np.isnan(y)
        if valid.sum() < 30:
            results[name] = {'skipped': True}
            continue
        
        X_v = X[valid]
        y_v = y[valid]
        
        # Add intercept
        X_full = np.column_stack([np.ones(len(X_v)), X_v])
        
        try:
            coefs, _, _, _ = np.linalg.lstsq(X_full, y_v, rcond=None)
            predicted = X_full @ coefs
            ss_res = np.sum((y_v - predicted)**2)
            ss_tot = np.sum((y_v - np.mean(y_v))**2)
            r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
            mae = float(np.mean(np.abs(y_v - predicted)))
            
            # Compare with carbs-only model
            X_carbs = np.column_stack([np.ones(len(X_v)), X_v[:, 0]])
            coefs_carbs, _, _, _ = np.linalg.lstsq(X_carbs, y_v, rcond=None)
            pred_carbs = X_carbs @ coefs_carbs
            r2_carbs = 1 - np.sum((y_v - pred_carbs)**2) / ss_tot if ss_tot > 0 else 0
            mae_carbs = float(np.mean(np.abs(y_v - pred_carbs)))
            
            feature_names = ['intercept', 'carbs', 'pre_bg', 'iob', 'sin_hour', 'cos_hour', 'bolus']
            
            results[name] = {
                'r2_full': round(float(r2), 3),
                'r2_carbs_only': round(float(r2_carbs), 3),
                'r2_improvement': round(float(r2 - r2_carbs), 3),
                'mae_full': round(mae, 1),
                'mae_carbs_only': round(mae_carbs, 1),
                'coefs': {feature_names[i]: round(float(coefs[i]), 4) for i in range(len(coefs))},
                'n_meals': int(valid.sum()),
            }
            print(f"  {name}: R² carbs={r2_carbs:.3f} → full={r2:.3f} (+{r2-r2_carbs:.3f}), "
                  f"MAE {mae_carbs:.0f}→{mae:.0f}")
        except Exception as e:
            results[name] = {'skipped': True, 'error': str(e)}
    return results


def exp_2345_optimal_bolus(patients):
    """Optimal meal bolus simulation."""
    results = {}
    for pat in patients:
        name = pat['name']
        meals = find_meals(pat['df'])
        
        if len(meals) < 20:
            results[name] = {'skipped': True}
            continue
        
        # For each meal, what bolus would have achieved target (120) at 3h?
        optimal_boluses = []
        actual_boluses = []
        carbs_vals = []
        
        for m in meals:
            if np.isnan(m['bg_3h']) or m['isf'] < 1:
                continue
            
            # BG at 3h relative to target (120)
            bg_excess = m['bg_3h'] - 120
            
            # Additional insulin needed (or less needed if negative)
            additional_insulin = bg_excess / m['isf']
            
            optimal_bolus = m['bolus'] + additional_insulin
            optimal_bolus = max(0, optimal_bolus)  # can't have negative bolus
            
            optimal_boluses.append(optimal_bolus)
            actual_boluses.append(m['bolus'])
            carbs_vals.append(m['carbs'])
        
        if len(optimal_boluses) < 10:
            results[name] = {'skipped': True}
            continue
        
        optimal = np.array(optimal_boluses)
        actual = np.array(actual_boluses)
        carbs = np.array(carbs_vals)
        
        # Effective CR from optimal boluses
        optimal_cr = carbs / (optimal + 1e-8)
        actual_cr_eff = carbs / (actual + 1e-8)
        
        under_bolused = float(np.mean(optimal > actual * 1.1) * 100)  # >10% more needed
        over_bolused = float(np.mean(optimal < actual * 0.9) * 100)  # >10% less needed
        
        results[name] = {
            'n_meals': len(optimal_boluses),
            'mean_optimal_bolus': round(float(np.mean(optimal)), 2),
            'mean_actual_bolus': round(float(np.mean(actual)), 2),
            'bolus_ratio': round(float(np.mean(optimal)) / (np.mean(actual) + 1e-8), 2),
            'under_bolused_pct': round(under_bolused, 1),
            'over_bolused_pct': round(over_bolused, 1),
            'mean_optimal_cr': round(float(np.median(optimal_cr[optimal > 0.1])), 1) if np.any(optimal > 0.1) else 0,
            'mean_actual_cr': round(float(np.median(actual_cr_eff[actual > 0.1])), 1) if np.any(actual > 0.1) else 0,
        }
        print(f"  {name}: {under_bolused:.0f}% under-bolused, {over_bolused:.0f}% over-bolused, "
              f"optimal CR={results[name]['mean_optimal_cr']}")
    return results


def exp_2346_population(patients):
    """Patient-specific vs population CR model."""
    # Collect all meals
    all_meals = []
    patient_meals = {}
    for pat in patients:
        name = pat['name']
        meals = find_meals(pat['df'])
        if len(meals) < 20:
            continue
        patient_meals[name] = meals
        for m in meals:
            m['patient'] = name
            all_meals.append(m)
    
    if len(all_meals) < 100:
        return {'skipped': True}
    
    # Build population model
    X_all = np.array([
        [m['carbs'], m['pre_bg'], m['iob'],
         np.sin(2 * np.pi * m['hour'] / 24),
         np.cos(2 * np.pi * m['hour'] / 24)]
        for m in all_meals
    ])
    y_all = np.array([m['rise'] for m in all_meals])
    
    valid = ~np.any(np.isnan(X_all), axis=1) & ~np.isnan(y_all)
    X_v = np.column_stack([np.ones(valid.sum()), X_all[valid]])
    y_v = y_all[valid]
    
    pop_coefs, _, _, _ = np.linalg.lstsq(X_v, y_v, rcond=None)
    pop_pred = X_v @ pop_coefs
    pop_r2 = 1 - np.sum((y_v - pop_pred)**2) / np.sum((y_v - np.mean(y_v))**2)
    
    # Compare per-patient
    results = {
        'population_r2': round(float(pop_r2), 3),
        'population_n': int(valid.sum()),
        'patients': {},
    }
    
    for name, meals in patient_meals.items():
        X_pat = np.array([
            [m['carbs'], m['pre_bg'], m['iob'],
             np.sin(2 * np.pi * m['hour'] / 24),
             np.cos(2 * np.pi * m['hour'] / 24)]
            for m in meals
        ])
        y_pat = np.array([m['rise'] for m in meals])
        
        v = ~np.any(np.isnan(X_pat), axis=1) & ~np.isnan(y_pat)
        if v.sum() < 10:
            continue
        
        X_pv = np.column_stack([np.ones(v.sum()), X_pat[v]])
        y_pv = y_pat[v]
        
        # Individual model
        try:
            ind_coefs, _, _, _ = np.linalg.lstsq(X_pv, y_pv, rcond=None)
            ind_pred = X_pv @ ind_coefs
            ind_r2 = 1 - np.sum((y_pv - ind_pred)**2) / np.sum((y_pv - np.mean(y_pv))**2)
        except:
            ind_r2 = 0
        
        # Population model on this patient's data
        pop_pred_pat = X_pv @ pop_coefs
        pop_r2_pat = 1 - np.sum((y_pv - pop_pred_pat)**2) / np.sum((y_pv - np.mean(y_pv))**2)
        
        results['patients'][name] = {
            'individual_r2': round(float(ind_r2), 3),
            'population_r2_on_patient': round(float(pop_r2_pat), 3),
            'individual_better': float(ind_r2) > float(pop_r2_pat),
            'n_meals': int(v.sum()),
        }
    
    ind_wins = sum(1 for v in results['patients'].values() if v['individual_better'])
    print(f"  Population R²={pop_r2:.3f}, individual wins {ind_wins}/{len(results['patients'])}")
    return results


def exp_2347_classification(patients):
    """Meal type classification from glucose trajectory."""
    results = {}
    for pat in patients:
        name = pat['name']
        meals = find_meals(pat['df'])
        
        if len(meals) < 20:
            results[name] = {'skipped': True}
            continue
        
        # Classify meals by trajectory shape
        fast_rise = 0  # Peak within 30 min
        slow_rise = 0  # Peak 30-90 min
        delayed = 0    # Peak > 90 min
        flat = 0       # Rise < 20 mg/dL
        
        for m in meals:
            if m['rise'] < 20:
                flat += 1
            elif m['time_to_peak'] <= 30:
                fast_rise += 1
            elif m['time_to_peak'] <= 90:
                slow_rise += 1
            else:
                delayed += 1
        
        total = len(meals)
        results[name] = {
            'n_meals': total,
            'fast_rise_pct': round(fast_rise / total * 100, 1),
            'slow_rise_pct': round(slow_rise / total * 100, 1),
            'delayed_pct': round(delayed / total * 100, 1),
            'flat_pct': round(flat / total * 100, 1),
            'mean_time_to_peak': round(float(np.mean([m['time_to_peak'] for m in meals])), 0),
            'mean_rise': round(float(np.mean([m['rise'] for m in meals])), 1),
        }
        print(f"  {name}: fast={fast_rise} slow={slow_rise} delayed={delayed} flat={flat}")
    return results


def exp_2348_recommendations(patients, all_results):
    """Comprehensive CR recommendation engine."""
    results = {}
    for pat in patients:
        name = pat['name']
        meals = find_meals(pat['df'])
        
        if len(meals) < 10:
            results[name] = {'skipped': True}
            continue
        
        # Gather from all experiments
        premeal = all_results.get('exp_2341', {}).get(name, {})
        circadian = all_results.get('exp_2342', {}).get(name, {})
        iob_eff = all_results.get('exp_2343', {}).get(name, {})
        multifactor = all_results.get('exp_2344', {}).get(name, {})
        optimal = all_results.get('exp_2345', {}).get(name, {})
        classify = all_results.get('exp_2347', {}).get(name, {})
        
        recommendations = []
        
        # Pre-meal BG matters
        premeal_r = premeal.get('r_premeal_rise', 0)
        if abs(premeal_r) > 0.2:
            recommendations.append({
                'type': 'pre_meal_bg_adjustment',
                'detail': f'Pre-meal BG explains {premeal_r**2*100:.0f}% of rise variance',
                'action': 'Increase bolus when pre-meal BG > 150, reduce when < 100',
            })
        
        # Circadian variation
        cr_range = circadian.get('cr_range_ratio', 1) if not circadian.get('skipped') else 1
        if cr_range > 1.5:
            most = circadian.get('most_sensitive_period', '?')
            recommendations.append({
                'type': 'circadian_cr',
                'detail': f'CR varies {cr_range:.1f}× across day',
                'action': f'Use different CR for {most} (most sensitive)',
            })
        
        # Under-bolusing
        under = optimal.get('under_bolused_pct', 0) if not optimal.get('skipped') else 0
        if under > 50:
            ratio = optimal.get('bolus_ratio', 1)
            recommendations.append({
                'type': 'increase_bolus',
                'detail': f'{under:.0f}% of meals under-bolused, need {ratio:.1f}× current',
                'action': 'Decrease CR (increase bolus per gram)',
            })
        
        # Stacking
        stacking = iob_eff.get('stacking_rate', 0)
        if stacking > 50:
            recommendations.append({
                'type': 'reduce_stacking',
                'detail': f'{stacking:.0f}% of meals have significant IOB stacking',
                'action': 'Space meals further apart or use IOB-aware dosing',
            })
        
        # Multi-factor improvement
        r2_improvement = multifactor.get('r2_improvement', 0) if not multifactor.get('skipped') else 0
        if r2_improvement > 0.05:
            recommendations.append({
                'type': 'context_aware_cr',
                'detail': f'Context model improves R² by {r2_improvement:.3f}',
                'action': 'Use multi-factor model (pre-BG + time + IOB)',
            })
        
        results[name] = {
            'n_meals': len(meals),
            'n_recommendations': len(recommendations),
            'recommendations': recommendations,
            'current_cr': round(float(pat['df']['scheduled_cr'].median()), 1) if 'scheduled_cr' in pat['df'].columns else None,
            'optimal_cr': optimal.get('mean_optimal_cr') if not optimal.get('skipped') else None,
        }
        print(f"  {name}: {len(recommendations)} recommendations, "
              f"CR {results[name]['current_cr']}→{results[name]['optimal_cr']}")
    return results


# ── Figures ──────────────────────────────────────────────────────────────

def generate_figures(results, patients, fig_dir):
    os.makedirs(fig_dir, exist_ok=True)
    names = sorted([p['name'] for p in patients])
    active = [n for n in names if not results.get('exp_2341', {}).get(n, {}).get('skipped')]
    
    # Fig 1: Pre-meal BG effect
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    r2341 = results['exp_2341']
    r_pre = [r2341.get(n, {}).get('r_premeal_rise', 0) for n in active]
    r_carbs = [r2341.get(n, {}).get('r_carbs_rise', 0) for n in active]
    
    x = np.arange(len(active))
    axes[0].bar(x - 0.2, [r**2*100 for r in r_pre], 0.35, color='purple', alpha=0.7, label='Pre-meal BG')
    axes[0].bar(x + 0.2, [r**2*100 for r in r_carbs], 0.35, color='orange', alpha=0.7, label='Carbs')
    axes[0].set_xticks(x); axes[0].set_xticklabels(active)
    axes[0].set_ylabel('Variance Explained (%)'); axes[0].legend()
    axes[0].set_title('What Explains Post-Meal Rise?')
    
    # Pre-meal quartile rises (average across patients)
    q_labels = ['Q1_low', 'Q2', 'Q3', 'Q4_high']
    q_rises = {q: [] for q in q_labels}
    for n in active:
        by_pre = r2341.get(n, {}).get('by_premeal', {})
        for q in q_labels:
            if q in by_pre:
                q_rises[q].append(by_pre[q]['mean_rise'])
    q_means = [np.mean(q_rises[q]) if q_rises[q] else 0 for q in q_labels]
    axes[1].bar(range(4), q_means, color=['green', 'yellowgreen', 'orange', 'red'], alpha=0.7)
    axes[1].set_xticks(range(4)); axes[1].set_xticklabels(['Low\nPre-BG', 'Q2', 'Q3', 'High\nPre-BG'])
    axes[1].set_ylabel('Mean Rise (mg/dL)'); axes[1].set_title('Rise by Pre-Meal BG Quartile')
    
    fig.suptitle('EXP-2341: Pre-Meal Glucose Effect', fontsize=14, fontweight='bold')
    plt.tight_layout(); plt.savefig(f'{fig_dir}/cr-fig01-premeal.png', dpi=150, bbox_inches='tight'); plt.close()
    print("  Figure 1: pre-meal")
    
    # Fig 2: Circadian CR variation
    fig, ax = plt.subplots(figsize=(12, 6))
    r2342 = results['exp_2342']
    periods = ['breakfast', 'lunch', 'afternoon', 'dinner', 'night']
    colors = ['#f39c12', '#27ae60', '#3498db', '#9b59b6', '#2c3e50']
    
    for idx, n in enumerate(active[:6]):
        data = r2342.get(n, {})
        if data.get('skipped'):
            continue
        by_period = data.get('by_period', {})
        ratios = [by_period.get(p, {}).get('mean_ratio', np.nan) for p in periods]
        ax.plot(range(len(periods)), ratios, 'o-', label=n, alpha=0.7)
    
    ax.set_xticks(range(len(periods))); ax.set_xticklabels(periods)
    ax.set_ylabel('Rise per Gram Carbs (mg/dL/g)'); ax.legend()
    ax.set_title('EXP-2342: CR Sensitivity by Time of Day', fontsize=14, fontweight='bold')
    plt.tight_layout(); plt.savefig(f'{fig_dir}/cr-fig02-circadian.png', dpi=150, bbox_inches='tight'); plt.close()
    print("  Figure 2: circadian")
    
    # Fig 3: IOB effect
    fig, ax = plt.subplots(figsize=(12, 5))
    r2343 = results['exp_2343']
    r_iob = [r2343.get(n, {}).get('r_iob_rise', 0) for n in active if not r2343.get(n, {}).get('skipped')]
    active_iob = [n for n in active if not r2343.get(n, {}).get('skipped')]
    stacking = [r2343.get(n, {}).get('stacking_rate', 0) for n in active_iob]
    
    x = np.arange(len(active_iob))
    ax.bar(x - 0.2, r_iob, 0.35, color='steelblue', alpha=0.7, label='IOB-Rise correlation')
    ax2 = ax.twinx()
    ax2.bar(x + 0.2, stacking, 0.35, color='coral', alpha=0.7, label='Stacking rate %')
    ax.set_xticks(x); ax.set_xticklabels(active_iob)
    ax.set_ylabel('Correlation', color='steelblue')
    ax2.set_ylabel('Stacking Rate %', color='coral')
    ax.legend(loc='upper left'); ax2.legend(loc='upper right')
    ax.set_title('EXP-2343: IOB Effect on Meal Response', fontsize=14, fontweight='bold')
    plt.tight_layout(); plt.savefig(f'{fig_dir}/cr-fig03-iob.png', dpi=150, bbox_inches='tight'); plt.close()
    print("  Figure 3: IOB")
    
    # Fig 4: Multi-factor model improvement
    fig, ax = plt.subplots(figsize=(12, 5))
    r2344 = results['exp_2344']
    active_mf = [n for n in active if not r2344.get(n, {}).get('skipped')]
    r2_carbs = [r2344[n].get('r2_carbs_only', 0) for n in active_mf]
    r2_full = [r2344[n].get('r2_full', 0) for n in active_mf]
    
    x = np.arange(len(active_mf))
    ax.bar(x - 0.2, r2_carbs, 0.35, color='gray', alpha=0.7, label='Carbs only')
    ax.bar(x + 0.2, r2_full, 0.35, color='green', alpha=0.7, label='Full context model')
    ax.set_xticks(x); ax.set_xticklabels(active_mf)
    ax.set_ylabel('R²'); ax.legend()
    ax.set_title('EXP-2344: Multi-Factor CR Model Improvement', fontsize=14, fontweight='bold')
    plt.tight_layout(); plt.savefig(f'{fig_dir}/cr-fig04-multifactor.png', dpi=150, bbox_inches='tight'); plt.close()
    print("  Figure 4: multi-factor")
    
    # Fig 5: Optimal bolus
    fig, ax = plt.subplots(figsize=(12, 5))
    r2345 = results['exp_2345']
    active_opt = [n for n in active if not r2345.get(n, {}).get('skipped')]
    under = [r2345[n].get('under_bolused_pct', 0) for n in active_opt]
    over = [r2345[n].get('over_bolused_pct', 0) for n in active_opt]
    
    x = np.arange(len(active_opt))
    ax.bar(x - 0.2, under, 0.35, color='red', alpha=0.7, label='Under-bolused')
    ax.bar(x + 0.2, over, 0.35, color='blue', alpha=0.7, label='Over-bolused')
    ax.axhline(50, color='gray', ls='--', alpha=0.3)
    ax.set_xticks(x); ax.set_xticklabels(active_opt)
    ax.set_ylabel('%'); ax.legend()
    ax.set_title('EXP-2345: Meal Bolus Adequacy', fontsize=14, fontweight='bold')
    plt.tight_layout(); plt.savefig(f'{fig_dir}/cr-fig05-optimal.png', dpi=150, bbox_inches='tight'); plt.close()
    print("  Figure 5: optimal bolus")
    
    # Fig 6: Population vs individual
    fig, ax = plt.subplots(figsize=(12, 5))
    r2346 = results['exp_2346']
    if not r2346.get('skipped'):
        pats = r2346.get('patients', {})
        active_pop = [n for n in active if n in pats]
        ind_r2 = [pats[n].get('individual_r2', 0) for n in active_pop]
        pop_r2_val = [pats[n].get('population_r2_on_patient', 0) for n in active_pop]
        
        x = np.arange(len(active_pop))
        ax.bar(x - 0.2, pop_r2_val, 0.35, color='orange', alpha=0.7, label='Population model')
        ax.bar(x + 0.2, ind_r2, 0.35, color='green', alpha=0.7, label='Individual model')
        ax.set_xticks(x); ax.set_xticklabels(active_pop)
        ax.set_ylabel('R²'); ax.legend()
    
    ax.set_title('EXP-2346: Population vs Individual CR Model', fontsize=14, fontweight='bold')
    plt.tight_layout(); plt.savefig(f'{fig_dir}/cr-fig06-population.png', dpi=150, bbox_inches='tight'); plt.close()
    print("  Figure 6: population vs individual")
    
    # Fig 7: Meal type classification
    fig, ax = plt.subplots(figsize=(14, 6))
    r2347 = results['exp_2347']
    active_cls = [n for n in active if not r2347.get(n, {}).get('skipped')]
    categories = ['fast_rise_pct', 'slow_rise_pct', 'delayed_pct', 'flat_pct']
    cat_labels = ['Fast\n(≤30m)', 'Slow\n(30-90m)', 'Delayed\n(>90m)', 'Flat\n(<20 mg/dL)']
    cat_colors = ['red', 'orange', 'blue', 'gray']
    
    x = np.arange(len(active_cls))
    bottom = np.zeros(len(active_cls))
    for cat, label, color in zip(categories, cat_labels, cat_colors):
        vals = [r2347[n].get(cat, 0) for n in active_cls]
        ax.bar(x, vals, bottom=bottom, color=color, alpha=0.7, label=label)
        bottom += vals
    
    ax.set_xticks(x); ax.set_xticklabels(active_cls)
    ax.set_ylabel('% of Meals'); ax.legend(ncol=4, bbox_to_anchor=(0.5, -0.1), loc='upper center')
    ax.set_title('EXP-2347: Meal Response Classification', fontsize=14, fontweight='bold')
    plt.tight_layout(); plt.savefig(f'{fig_dir}/cr-fig07-classify.png', dpi=150, bbox_inches='tight'); plt.close()
    print("  Figure 7: classification")
    
    # Fig 8: Recommendation summary
    fig, ax = plt.subplots(figsize=(14, 6))
    r2348 = results['exp_2348']
    active_rec = [n for n in active if not r2348.get(n, {}).get('skipped')]
    
    rec_types = ['pre_meal_bg_adjustment', 'circadian_cr', 'increase_bolus', 'reduce_stacking', 'context_aware_cr']
    rec_labels = ['Pre-meal\nBG adj', 'Circadian\nCR', 'Increase\nbolus', 'Reduce\nstacking', 'Context\naware']
    rec_colors = ['purple', 'teal', 'red', 'orange', 'green']
    
    data = np.zeros((len(active_rec), len(rec_types)))
    for i, n in enumerate(active_rec):
        recs = r2348[n].get('recommendations', [])
        for rec in recs:
            if rec['type'] in rec_types:
                j = rec_types.index(rec['type'])
                data[i, j] = 1
    
    im = ax.imshow(data.T, aspect='auto', cmap='Greens', vmin=0, vmax=1)
    ax.set_xticks(range(len(active_rec))); ax.set_xticklabels(active_rec)
    ax.set_yticks(range(len(rec_labels))); ax.set_yticklabels(rec_labels)
    for i in range(len(active_rec)):
        for j in range(len(rec_types)):
            ax.text(i, j, '✓' if data[i, j] else '', ha='center', va='center', fontsize=14)
    
    ax.set_title('EXP-2348: CR Recommendation Map', fontsize=14, fontweight='bold')
    plt.tight_layout(); plt.savefig(f'{fig_dir}/cr-fig08-recommendations.png', dpi=150, bbox_inches='tight'); plt.close()
    print("  Figure 8: recommendations")


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--figures', action='store_true')
    parser.add_argument('--tiny', action='store_true')
    args = parser.parse_args()

    parquet_dir = 'externals/ns-parquet-tiny/training' if args.tiny else 'externals/ns-parquet/training'
    print(f"Loading patients from {parquet_dir}...")
    patients = load_patients_parquet(parquet_dir)
    print(f"Loaded {len(patients)} patients\n")

    results = {}

    for exp_id, exp_name, exp_fn in [
        ('exp_2341', 'Pre-Meal BG Effect', lambda: exp_2341_premeal(patients)),
        ('exp_2342', 'Circadian CR', lambda: exp_2342_circadian_cr(patients)),
        ('exp_2343', 'IOB Effect', lambda: exp_2343_iob_effect(patients)),
        ('exp_2344', 'Multi-Factor Model', lambda: exp_2344_multifactor(patients)),
        ('exp_2345', 'Optimal Bolus', lambda: exp_2345_optimal_bolus(patients)),
        ('exp_2346', 'Population vs Individual', lambda: exp_2346_population(patients)),
        ('exp_2347', 'Meal Classification', lambda: exp_2347_classification(patients)),
    ]:
        print(f"Running {exp_id}: {exp_name}...")
        results[exp_id] = exp_fn()
        print(f"  ✓ completed\n")

    print("Running exp_2348: Recommendations...")
    results['exp_2348'] = exp_2348_recommendations(patients, results)
    print("  ✓ completed\n")

    out_path = 'externals/experiments/exp-2341-2348_context_cr.json'
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    def convert(obj):
        if isinstance(obj, (np.integer,)): return int(obj)
        if isinstance(obj, (np.floating,)): return float(obj)
        if isinstance(obj, np.ndarray): return obj.tolist()
        if isinstance(obj, (np.bool_,)): return bool(obj)
        if isinstance(obj, pd.Timestamp): return str(obj)
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
