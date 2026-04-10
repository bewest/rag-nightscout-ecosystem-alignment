#!/usr/bin/env python3
"""
EXP-2221–2228: Meal Pharmacodynamics & Pre-Bolus Optimization

Characterizes individual carb absorption profiles, meal timing patterns,
and pre-bolus optimization opportunities. Meals are the #1 uncontrolled
disturbance (EXP-2214: only 26-68% recover within 3h).

Experiments:
  2221 - Carb Absorption Curves (individual glucose response shapes)
  2222 - Meal Size Dose-Response (spike vs carbs relationship)
  2223 - Pre-Bolus Timing Analysis (time between bolus and carbs)
  2224 - Meal Type Classification (fast vs slow absorption patterns)
  2225 - Post-Meal Loop Behavior (what does the loop do after meals?)
  2226 - Meal-to-Meal Variability (same carbs → different responses?)
  2227 - Optimal Pre-Bolus Estimation (what timing minimizes spike?)
  2228 - Meal Recovery Prediction (can we predict which meals recover fast?)

Usage:
    PYTHONPATH=tools python3 tools/cgmencode/exp_meal_pharma_2221.py --figures
"""

import argparse
import json
import os
import sys
import warnings
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings('ignore')

from cgmencode.exp_metabolic_441 import load_patients

STEPS_PER_HOUR = 12
STEPS_PER_DAY = 288
HYPO_THRESHOLD = 70
TARGET_LOW = 70
TARGET_HIGH = 180


class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


def find_meals(df, min_carbs=5):
    """Find meal events with sufficient post-meal glucose data."""
    carbs = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(df))
    glucose = df['glucose'].values
    bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(len(df))
    n = len(glucose)

    meals = []
    for i in range(STEPS_PER_HOUR, n - STEPS_PER_HOUR * 6):
        if np.isnan(carbs[i]) or carbs[i] < min_carbs:
            continue
        # Need valid glucose before and after
        g_pre = glucose[max(0, i - 3):i + 1]
        if np.sum(~np.isnan(g_pre)) < 2:
            continue
        g_post = glucose[i:min(i + STEPS_PER_HOUR * 6, n)]
        if np.sum(~np.isnan(g_post)) < STEPS_PER_HOUR:
            continue

        # Find associated bolus (within ±60 min)
        bolus_window = bolus[max(0, i - STEPS_PER_HOUR):min(i + STEPS_PER_HOUR, n)]
        total_bolus = np.nansum(bolus_window[~np.isnan(bolus_window)])

        # Pre-bolus timing: find first bolus before carbs (within 60min)
        pre_bolus_time = 0  # minutes
        for j in range(max(0, i - STEPS_PER_HOUR), i):
            if not np.isnan(bolus[j]) and bolus[j] > 0.05:
                pre_bolus_time = (i - j) * 5  # minutes
                break

        # Post-bolus: find first bolus after carbs (within 30min)
        if pre_bolus_time == 0:
            for j in range(i, min(i + 6, n)):
                if not np.isnan(bolus[j]) and bolus[j] > 0.05:
                    pre_bolus_time = -(j - i) * 5  # negative = bolus AFTER carbs
                    break

        meals.append({
            'idx': i,
            'carbs': float(carbs[i]),
            'bolus': float(total_bolus),
            'pre_bolus_min': pre_bolus_time,
            'glucose_pre': float(np.nanmean(g_pre)),
            'glucose_post': g_post.tolist(),
            'hour': (i / STEPS_PER_HOUR) % 24,
        })
    return meals


# ─────────────────────────────────────────────────────────────────
# EXP-2221: Carb Absorption Curves
# ─────────────────────────────────────────────────────────────────
def exp_2221_absorption_curves(patients):
    """
    Compute mean glucose response curve post-meal, normalized by carbs.
    This reveals the carb absorption profile for each patient.
    """
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        meals = find_meals(df)

        if len(meals) < 10:
            results[name] = {'skip': True, 'n_meals': len(meals)}
            continue

        # Collect normalized response curves (mg/dL per gram of carbs)
        window = STEPS_PER_HOUR * 5  # 5h post-meal
        curves = []
        raw_curves = []
        for m in meals:
            g_post = np.array(m['glucose_post'][:window])
            if len(g_post) < window:
                g_post = np.pad(g_post, (0, window - len(g_post)), constant_values=np.nan)
            g_relative = g_post - m['glucose_pre']
            raw_curves.append(g_relative)
            if m['carbs'] > 0:
                curves.append(g_relative / m['carbs'])

        if not curves:
            results[name] = {'skip': True, 'n_meals': len(meals)}
            continue

        curves = np.array(curves)
        raw_curves = np.array(raw_curves)
        mean_curve = np.nanmean(curves, axis=0)
        mean_raw = np.nanmean(raw_curves, axis=0)
        std_raw = np.nanstd(raw_curves, axis=0)

        # Key metrics from the mean curve
        time_h = np.arange(window) / STEPS_PER_HOUR
        peak_idx = np.nanargmax(mean_raw)
        peak_time_h = peak_idx / STEPS_PER_HOUR
        peak_value = float(np.nanmax(mean_raw))

        # Time to return to baseline (within ±10 mg/dL)
        recovery_time = 5.0
        for i in range(peak_idx, window):
            if not np.isnan(mean_raw[i]) and abs(mean_raw[i]) < 10:
                recovery_time = i / STEPS_PER_HOUR
                break

        # AUC (integral of glucose excursion)
        auc = float(np.nansum(mean_raw[~np.isnan(mean_raw)])) * 5 / 60  # mg·h/dL

        results[name] = {
            'n_meals': len(meals),
            'peak_time_h': round(peak_time_h, 2),
            'peak_value_mg_dl': round(peak_value, 1),
            'recovery_time_h': round(recovery_time, 2),
            'auc_mg_h_dl': round(auc, 1),
            'mean_curve': mean_raw.tolist(),
            'std_curve': std_raw.tolist(),
            'normalized_curve': mean_curve.tolist(),
        }
    return results


# ─────────────────────────────────────────────────────────────────
# EXP-2222: Meal Size Dose-Response
# ─────────────────────────────────────────────────────────────────
def exp_2222_dose_response(patients):
    """
    Analyze spike magnitude vs carb amount. Is the relationship linear?
    Does the loop compensate larger meals better?
    """
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        meals = find_meals(df)

        if len(meals) < 15:
            results[name] = {'skip': True, 'n_meals': len(meals)}
            continue

        carbs_arr = np.array([m['carbs'] for m in meals])
        spikes = []
        for m in meals:
            g_post = np.array(m['glucose_post'][:STEPS_PER_HOUR * 3])
            spike = np.nanmax(g_post) - m['glucose_pre']
            spikes.append(float(spike))
        spikes = np.array(spikes)

        # Linear fit: spike = a * carbs + b
        valid = ~np.isnan(spikes) & ~np.isnan(carbs_arr) & (carbs_arr > 0)
        if np.sum(valid) < 10:
            results[name] = {'skip': True, 'n_meals': len(meals)}
            continue

        slope, intercept, r, p, se = stats.linregress(carbs_arr[valid], spikes[valid])

        # Bin by carb amount
        bins = [0, 15, 30, 50, 80, 200]
        bin_labels = ['<15g', '15-30g', '30-50g', '50-80g', '>80g']
        bin_spikes = []
        bin_counts = []
        for i in range(len(bins) - 1):
            mask = valid & (carbs_arr >= bins[i]) & (carbs_arr < bins[i + 1])
            if np.sum(mask) > 0:
                bin_spikes.append(float(np.mean(spikes[mask])))
                bin_counts.append(int(np.sum(mask)))
            else:
                bin_spikes.append(0)
                bin_counts.append(0)

        results[name] = {
            'n_meals': int(np.sum(valid)),
            'slope_mg_dl_per_g': round(slope, 3),
            'intercept_mg_dl': round(intercept, 1),
            'r': round(r, 3),
            'r_squared': round(r ** 2, 3),
            'p_value': float(p),
            'bin_labels': bin_labels,
            'bin_spikes': bin_spikes,
            'bin_counts': bin_counts,
            'mean_carbs': round(float(np.mean(carbs_arr[valid])), 1),
            'mean_spike': round(float(np.mean(spikes[valid])), 1),
        }
    return results


# ─────────────────────────────────────────────────────────────────
# EXP-2223: Pre-Bolus Timing Analysis
# ─────────────────────────────────────────────────────────────────
def exp_2223_prebolus_timing(patients):
    """
    Analyze the relationship between pre-bolus timing and meal spike.
    Longer pre-bolus → should reduce spike by allowing insulin to act first.
    """
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        meals = find_meals(df)

        if len(meals) < 15:
            results[name] = {'skip': True}
            continue

        # Categorize by pre-bolus timing
        timings = np.array([m['pre_bolus_min'] for m in meals])
        spikes = []
        for m in meals:
            g_post = np.array(m['glucose_post'][:STEPS_PER_HOUR * 3])
            spike = np.nanmax(g_post) - m['glucose_pre']
            spikes.append(float(spike))
        spikes = np.array(spikes)

        # Categories: late (bolus after carbs), simultaneous, 5-15min pre, >15min pre
        categories = {
            'late (bolus after carbs)': timings < 0,
            'simultaneous (0-5min)': (timings >= 0) & (timings <= 5),
            'short pre-bolus (5-15min)': (timings > 5) & (timings <= 15),
            'good pre-bolus (15-30min)': (timings > 15) & (timings <= 30),
            'long pre-bolus (>30min)': timings > 30,
        }

        cat_results = {}
        for cat_name, mask in categories.items():
            n_cat = int(np.sum(mask))
            if n_cat > 0:
                cat_results[cat_name] = {
                    'n': n_cat,
                    'mean_spike': round(float(np.mean(spikes[mask])), 1),
                    'median_spike': round(float(np.median(spikes[mask])), 1),
                    'mean_timing_min': round(float(np.mean(timings[mask])), 1),
                }

        # Correlation: timing → spike
        valid = ~np.isnan(spikes)
        if np.sum(valid) >= 10:
            r, p = stats.pearsonr(timings[valid], spikes[valid])
        else:
            r, p = np.nan, np.nan

        # Overall timing distribution
        mean_timing = float(np.mean(timings))
        pct_prebolus = float(np.mean(timings > 5) * 100)

        results[name] = {
            'n_meals': len(meals),
            'categories': cat_results,
            'r_timing_spike': round(float(r), 3) if not np.isnan(r) else None,
            'p_timing_spike': float(p) if not np.isnan(p) else None,
            'mean_timing_min': round(mean_timing, 1),
            'pct_prebolus_gt5min': round(pct_prebolus, 1),
        }
    return results


# ─────────────────────────────────────────────────────────────────
# EXP-2224: Meal Type Classification
# ─────────────────────────────────────────────────────────────────
def exp_2224_meal_types(patients):
    """
    Classify meals by their glucose response shape:
    - Fast absorption: sharp spike, fast recovery
    - Slow absorption: gradual rise, slow recovery
    - Overshoot: bolus-dominant, glucose drops below baseline
    - Flat: minimal response (well-matched bolus)
    """
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        meals = find_meals(df)

        if len(meals) < 10:
            results[name] = {'skip': True}
            continue

        classifications = {'fast': 0, 'slow': 0, 'overshoot': 0, 'flat': 0}
        meal_details = []

        for m in meals:
            g_post = np.array(m['glucose_post'][:STEPS_PER_HOUR * 4])
            if len(g_post) < STEPS_PER_HOUR * 2:
                continue
            g_rel = g_post - m['glucose_pre']

            spike = np.nanmax(g_rel)
            nadir = np.nanmin(g_rel)
            peak_idx = np.nanargmax(g_rel)
            peak_time_h = peak_idx / STEPS_PER_HOUR

            # Classify
            if spike < 20:
                meal_type = 'flat'
            elif nadir < -20:
                meal_type = 'overshoot'
            elif peak_time_h < 1.0:
                meal_type = 'fast'
            else:
                meal_type = 'slow'

            classifications[meal_type] += 1
            meal_details.append({
                'type': meal_type,
                'spike': float(spike),
                'nadir': float(nadir),
                'peak_time_h': round(peak_time_h, 2),
                'carbs': m['carbs'],
            })

        total = sum(classifications.values())
        pct = {k: round(v / total * 100, 1) if total > 0 else 0 for k, v in classifications.items()}

        # Mean spike by type
        type_spikes = {}
        for mt in ['fast', 'slow', 'overshoot', 'flat']:
            type_meals = [d for d in meal_details if d['type'] == mt]
            if type_meals:
                type_spikes[mt] = {
                    'mean_spike': round(np.mean([d['spike'] for d in type_meals]), 1),
                    'mean_carbs': round(np.mean([d['carbs'] for d in type_meals]), 1),
                    'mean_peak_time': round(np.mean([d['peak_time_h'] for d in type_meals]), 2),
                }

        results[name] = {
            'n_meals': total,
            'classifications': classifications,
            'percentages': pct,
            'type_details': type_spikes,
        }
    return results


# ─────────────────────────────────────────────────────────────────
# EXP-2225: Post-Meal Loop Behavior
# ─────────────────────────────────────────────────────────────────
def exp_2225_postmeal_loop(patients):
    """
    What does the AID loop do after meals? Does it:
    - Increase delivery to combat the spike?
    - Suspend delivery as glucose rises (paradoxical)?
    - Micro-dose corrections?
    """
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        meals = find_meals(df)
        enacted = df['enacted_rate'].values if 'enacted_rate' in df.columns else None
        bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(len(df))
        n = len(df)

        if enacted is None or len(meals) < 10:
            results[name] = {'skip': True}
            continue

        # Post-meal insulin delivery patterns (4h window)
        window = STEPS_PER_HOUR * 4
        post_meal_enacted = []
        post_meal_bolus_count = []
        post_meal_total_insulin = []

        for m in meals:
            idx = m['idx']
            if idx + window > n:
                continue
            en = enacted[idx:idx + window]
            bol = bolus[idx:idx + window]

            post_meal_enacted.append(en)
            post_meal_bolus_count.append(int(np.sum(~np.isnan(bol) & (bol > 0.05))))
            post_meal_total_insulin.append(float(np.nansum(en) / STEPS_PER_HOUR + np.nansum(bol[~np.isnan(bol)])))

        if not post_meal_enacted:
            results[name] = {'skip': True}
            continue

        enacted_matrix = np.array([e[:window] if len(e) >= window else
                                   np.pad(e, (0, window - len(e)), constant_values=np.nan)
                                   for e in post_meal_enacted])
        mean_enacted = np.nanmean(enacted_matrix, axis=0)

        # Pre-meal baseline (1h before)
        pre_meal_rates = []
        for m in meals:
            idx = m['idx']
            if idx - STEPS_PER_HOUR < 0:
                continue
            pre = enacted[idx - STEPS_PER_HOUR:idx]
            pre_meal_rates.append(float(np.nanmean(pre)))

        pre_mean = np.mean(pre_meal_rates) if pre_meal_rates else 0

        # Post-meal phases
        # Phase 1: 0-1h (spike rising)
        phase1_rate = float(np.nanmean(mean_enacted[:STEPS_PER_HOUR]))
        # Phase 2: 1-2h (peak)
        phase2_rate = float(np.nanmean(mean_enacted[STEPS_PER_HOUR:2 * STEPS_PER_HOUR]))
        # Phase 3: 2-4h (recovery)
        phase3_rate = float(np.nanmean(mean_enacted[2 * STEPS_PER_HOUR:]))

        # Suspend percentage per phase
        phase1_suspend = float(np.mean(mean_enacted[:STEPS_PER_HOUR] < 0.05) * 100)
        phase2_suspend = float(np.mean(mean_enacted[STEPS_PER_HOUR:2 * STEPS_PER_HOUR] < 0.05) * 100)
        phase3_suspend = float(np.mean(mean_enacted[2 * STEPS_PER_HOUR:] < 0.05) * 100)

        results[name] = {
            'n_meals': len(post_meal_enacted),
            'pre_meal_rate': round(pre_mean, 3),
            'phase1_rate_0_1h': round(phase1_rate, 3),
            'phase2_rate_1_2h': round(phase2_rate, 3),
            'phase3_rate_2_4h': round(phase3_rate, 3),
            'phase1_suspend_pct': round(phase1_suspend, 1),
            'phase2_suspend_pct': round(phase2_suspend, 1),
            'phase3_suspend_pct': round(phase3_suspend, 1),
            'mean_post_bolus_corrections': round(np.mean(post_meal_bolus_count), 1),
            'mean_total_insulin_4h': round(np.mean(post_meal_total_insulin), 2),
            'mean_enacted_curve': mean_enacted.tolist(),
        }
    return results


# ─────────────────────────────────────────────────────────────────
# EXP-2226: Meal-to-Meal Variability
# ─────────────────────────────────────────────────────────────────
def exp_2226_meal_variability(patients):
    """
    Same carbs → same response? Quantify intra-patient meal variability.
    """
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        meals = find_meals(df)

        if len(meals) < 20:
            results[name] = {'skip': True}
            continue

        # Group by similar carb amount (±5g bins)
        carb_groups = {}
        for m in meals:
            g_post = np.array(m['glucose_post'][:STEPS_PER_HOUR * 3])
            spike = np.nanmax(g_post) - m['glucose_pre']

            # Round to nearest 10g
            carb_bin = round(m['carbs'] / 10) * 10
            if carb_bin not in carb_groups:
                carb_groups[carb_bin] = []
            carb_groups[carb_bin].append({
                'spike': float(spike),
                'glucose_pre': m['glucose_pre'],
                'hour': m['hour'],
                'bolus': m['bolus'],
            })

        # For each bin with ≥5 meals, compute variability
        bin_results = {}
        for carb_bin, group_meals in sorted(carb_groups.items()):
            if len(group_meals) < 5:
                continue
            spikes = np.array([m['spike'] for m in group_meals])
            cv = float(np.std(spikes) / np.mean(spikes) * 100) if np.mean(spikes) > 0 else 0

            bin_results[f'{int(carb_bin)}g'] = {
                'n': len(group_meals),
                'mean_spike': round(float(np.mean(spikes)), 1),
                'std_spike': round(float(np.std(spikes)), 1),
                'cv_pct': round(cv, 1),
                'min_spike': round(float(np.min(spikes)), 1),
                'max_spike': round(float(np.max(spikes)), 1),
            }

        # Overall variability
        all_spikes = []
        for m in meals:
            g_post = np.array(m['glucose_post'][:STEPS_PER_HOUR * 3])
            spike = np.nanmax(g_post) - m['glucose_pre']
            all_spikes.append(spike)
        all_spikes = np.array(all_spikes)

        results[name] = {
            'n_meals': len(meals),
            'overall_spike_mean': round(float(np.mean(all_spikes)), 1),
            'overall_spike_std': round(float(np.std(all_spikes)), 1),
            'overall_cv_pct': round(float(np.std(all_spikes) / np.mean(all_spikes) * 100), 1) if np.mean(all_spikes) > 0 else 0,
            'n_carb_bins': len(bin_results),
            'bin_results': bin_results,
        }
    return results


# ─────────────────────────────────────────────────────────────────
# EXP-2227: Optimal Pre-Bolus Estimation
# ─────────────────────────────────────────────────────────────────
def exp_2227_optimal_prebolus(patients):
    """
    Estimate the optimal pre-bolus timing for each patient by analyzing
    the relationship between timing and post-meal outcomes.
    """
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        meals = find_meals(df)

        if len(meals) < 20:
            results[name] = {'skip': True}
            continue

        timings = []
        spikes = []
        nadirs = []
        time_in_range_3h = []

        for m in meals:
            g_post = np.array(m['glucose_post'][:STEPS_PER_HOUR * 3])
            if len(g_post) < STEPS_PER_HOUR:
                continue
            spike = np.nanmax(g_post) - m['glucose_pre']
            nadir = np.nanmin(g_post)
            tir = np.mean((g_post >= TARGET_LOW) & (g_post <= TARGET_HIGH) & (~np.isnan(g_post))) * 100

            timings.append(m['pre_bolus_min'])
            spikes.append(float(spike))
            nadirs.append(float(nadir))
            time_in_range_3h.append(float(tir))

        timings = np.array(timings)
        spikes = np.array(spikes)
        nadirs = np.array(nadirs)
        time_in_range_3h = np.array(time_in_range_3h)

        # Find optimal timing that minimizes spike while keeping nadir > 70
        # Bin by timing
        timing_bins = [-30, -5, 0, 5, 10, 15, 20, 30, 60]
        bin_results = {}
        for i in range(len(timing_bins) - 1):
            mask = (timings >= timing_bins[i]) & (timings < timing_bins[i + 1])
            n_bin = int(np.sum(mask))
            if n_bin >= 3:
                bin_results[f'{timing_bins[i]}_to_{timing_bins[i+1]}min'] = {
                    'n': n_bin,
                    'mean_spike': round(float(np.mean(spikes[mask])), 1),
                    'mean_nadir': round(float(np.mean(nadirs[mask])), 1),
                    'mean_tir_3h': round(float(np.mean(time_in_range_3h[mask])), 1),
                    'hypo_pct': round(float(np.mean(nadirs[mask] < HYPO_THRESHOLD) * 100), 1),
                }

        # Best timing: minimize spike while hypo_pct < 10%
        best_timing = None
        best_spike = 999
        for bin_name, bin_data in bin_results.items():
            if bin_data['hypo_pct'] < 15 and bin_data['mean_spike'] < best_spike:
                best_spike = bin_data['mean_spike']
                best_timing = bin_name

        results[name] = {
            'n_meals': len(timings),
            'current_mean_timing': round(float(np.mean(timings)), 1),
            'current_pct_prebolus': round(float(np.mean(timings > 5) * 100), 1),
            'timing_bins': bin_results,
            'optimal_timing_bin': best_timing,
            'optimal_spike': best_spike if best_spike < 999 else None,
        }
    return results


# ─────────────────────────────────────────────────────────────────
# EXP-2228: Meal Recovery Prediction
# ─────────────────────────────────────────────────────────────────
def exp_2228_recovery_prediction(patients):
    """
    Can we predict which meals will recover quickly vs slowly?
    Features: pre-meal glucose, carb amount, bolus, timing, IOB, hour.
    """
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        meals = find_meals(df)
        iob = df['iob'].values if 'iob' in df.columns else np.zeros(len(df))

        if len(meals) < 20:
            results[name] = {'skip': True}
            continue

        features = []
        labels = []  # 1 = fast recovery (< 2h), 0 = slow

        for m in meals:
            g_post = np.array(m['glucose_post'][:STEPS_PER_HOUR * 4])
            if len(g_post) < STEPS_PER_HOUR * 2:
                continue
            spike = np.nanmax(g_post) - m['glucose_pre']
            peak_idx = np.nanargmax(g_post)

            # Recovery: time to return within ±20 of pre
            recovered = False
            for ri in range(peak_idx, len(g_post)):
                if not np.isnan(g_post[ri]) and abs(g_post[ri] - m['glucose_pre']) <= 20:
                    recovery_h = ri / STEPS_PER_HOUR
                    recovered = True
                    break
            if not recovered:
                recovery_h = 4.0

            labels.append(1 if recovery_h < 2.0 else 0)

            # Features
            idx = m['idx']
            iob_pre = float(iob[idx]) if not np.isnan(iob[idx]) else 0

            features.append({
                'glucose_pre': m['glucose_pre'],
                'carbs': m['carbs'],
                'bolus': m['bolus'],
                'pre_bolus_min': m['pre_bolus_min'],
                'iob_pre': iob_pre,
                'hour': m['hour'],
                'recovery_h': recovery_h,
            })

        labels = np.array(labels)
        if len(labels) < 20:
            results[name] = {'skip': True}
            continue

        fast_pct = float(np.mean(labels) * 100)

        # Correlations with recovery
        recovery_times = np.array([f['recovery_h'] for f in features])
        correlations = {}
        for feat_name in ['glucose_pre', 'carbs', 'bolus', 'pre_bolus_min', 'iob_pre', 'hour']:
            feat_vals = np.array([f[feat_name] for f in features])
            valid = ~np.isnan(feat_vals) & ~np.isnan(recovery_times)
            if np.sum(valid) >= 10:
                r, p = stats.pearsonr(feat_vals[valid], recovery_times[valid])
                correlations[feat_name] = {'r': round(float(r), 3), 'p': float(p)}
            else:
                correlations[feat_name] = {'r': None, 'p': None}

        # Best predictor
        best_feat = max(correlations.items(),
                        key=lambda x: abs(x[1]['r']) if x[1]['r'] is not None else 0)

        results[name] = {
            'n_meals': len(labels),
            'fast_recovery_pct': round(fast_pct, 1),
            'mean_recovery_h': round(float(np.mean(recovery_times)), 2),
            'correlations': correlations,
            'best_predictor': best_feat[0],
            'best_predictor_r': best_feat[1]['r'],
        }
    return results


# ─────────────────────────────────────────────────────────────────
# Figure Generation
# ─────────────────────────────────────────────────────────────────
def generate_figures(all_results, fig_dir):
    os.makedirs(fig_dir, exist_ok=True)
    colors = plt.cm.tab10(np.linspace(0, 1, 11))

    # Fig 1: Absorption Curves (EXP-2221)
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    r2221 = all_results['exp_2221']
    plot_patients = sorted([n for n in r2221 if not r2221[n].get('skip', False)])

    # Pick 4 representative patients
    selected = plot_patients[:4] if len(plot_patients) >= 4 else plot_patients
    for idx, n in enumerate(selected):
        ax = axes[idx // 2, idx % 2]
        data = r2221[n]
        curve = np.array(data['mean_curve'])
        std = np.array(data['std_curve'])
        time_h = np.arange(len(curve)) / STEPS_PER_HOUR
        ax.plot(time_h, curve, 'b-', linewidth=2, label='Mean')
        ax.fill_between(time_h, curve - std, curve + std, alpha=0.2, color='blue')
        ax.axhline(0, color='gray', ls=':', alpha=0.5)
        ax.set_xlabel('Hours post-meal')
        ax.set_ylabel('ΔGlucose (mg/dL)')
        ax.set_title(f'Patient {n}: Absorption Curve (n={data["n_meals"]}, peak={data["peak_time_h"]}h)')
        ax.legend()

    plt.tight_layout()
    plt.savefig(f'{fig_dir}/meal-fig01-absorption.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  [fig] meal-fig01-absorption.png")

    # Fig 2: Dose-Response (EXP-2222)
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    r2222 = all_results['exp_2222']
    names2 = sorted([n for n in r2222 if not r2222[n].get('skip', False)])

    slopes = [r2222[n]['slope_mg_dl_per_g'] for n in names2]
    r_vals = [r2222[n]['r'] for n in names2]

    axes[0].bar(np.arange(len(names2)), slopes, color=[colors[i] for i in range(len(names2))], alpha=0.8)
    axes[0].set_xticks(np.arange(len(names2)))
    axes[0].set_xticklabels(names2)
    axes[0].set_ylabel('Spike per gram carbs (mg/dL/g)')
    axes[0].set_title('EXP-2222: Dose-Response Slope')

    axes[1].bar(np.arange(len(names2)), r_vals, color=[colors[i] for i in range(len(names2))], alpha=0.8)
    axes[1].set_xticks(np.arange(len(names2)))
    axes[1].set_xticklabels(names2)
    axes[1].set_ylabel('Correlation (r)')
    axes[1].set_title('EXP-2222: Carbs-Spike Correlation')

    plt.tight_layout()
    plt.savefig(f'{fig_dir}/meal-fig02-doseresponse.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  [fig] meal-fig02-doseresponse.png")

    # Fig 3: Pre-Bolus Timing (EXP-2223)
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    r2223 = all_results['exp_2223']
    names3 = sorted([n for n in r2223 if not r2223[n].get('skip', False)])

    mean_timings = [r2223[n]['mean_timing_min'] for n in names3]
    pct_prebolus = [r2223[n]['pct_prebolus_gt5min'] for n in names3]

    axes[0].bar(np.arange(len(names3)), mean_timings, color=[colors[i] for i in range(len(names3))], alpha=0.8)
    axes[0].set_xticks(np.arange(len(names3)))
    axes[0].set_xticklabels(names3)
    axes[0].set_ylabel('Mean Pre-Bolus Time (min)')
    axes[0].set_title('EXP-2223: Pre-Bolus Timing')
    axes[0].axhline(15, color='green', ls='--', alpha=0.5, label='Recommended 15min')
    axes[0].legend()

    axes[1].bar(np.arange(len(names3)), pct_prebolus, color=[colors[i] for i in range(len(names3))], alpha=0.8)
    axes[1].set_xticks(np.arange(len(names3)))
    axes[1].set_xticklabels(names3)
    axes[1].set_ylabel('% Meals with Pre-Bolus >5min')
    axes[1].set_title('EXP-2223: Pre-Bolus Adherence')

    plt.tight_layout()
    plt.savefig(f'{fig_dir}/meal-fig03-prebolus.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  [fig] meal-fig03-prebolus.png")

    # Fig 4: Meal Types (EXP-2224)
    fig, ax = plt.subplots(figsize=(12, 6))
    r2224 = all_results['exp_2224']
    names4 = sorted([n for n in r2224 if not r2224[n].get('skip', False)])

    types = ['fast', 'slow', 'overshoot', 'flat']
    type_colors = ['#ff6b6b', '#ffa726', '#42a5f5', '#66bb6a']
    bottom = np.zeros(len(names4))
    for mt, tc in zip(types, type_colors):
        vals = [r2224[n]['percentages'].get(mt, 0) for n in names4]
        ax.bar(np.arange(len(names4)), vals, bottom=bottom, label=mt, color=tc, alpha=0.8)
        bottom += np.array(vals)
    ax.set_xticks(np.arange(len(names4)))
    ax.set_xticklabels(names4)
    ax.set_ylabel('Percentage (%)')
    ax.set_title('EXP-2224: Meal Response Type Distribution')
    ax.legend()

    plt.tight_layout()
    plt.savefig(f'{fig_dir}/meal-fig04-types.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  [fig] meal-fig04-types.png")

    # Fig 5: Post-Meal Loop (EXP-2225)
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    r2225 = all_results['exp_2225']
    names5 = sorted([n for n in r2225 if not r2225[n].get('skip', False)])

    phase1 = [r2225[n]['phase1_rate_0_1h'] for n in names5]
    phase2 = [r2225[n]['phase2_rate_1_2h'] for n in names5]
    phase3 = [r2225[n]['phase3_rate_2_4h'] for n in names5]

    x = np.arange(len(names5))
    w = 0.25
    axes[0].bar(x - w, phase1, w, label='0-1h (rise)', color='coral', alpha=0.8)
    axes[0].bar(x, phase2, w, label='1-2h (peak)', color='steelblue', alpha=0.8)
    axes[0].bar(x + w, phase3, w, label='2-4h (recovery)', color='forestgreen', alpha=0.8)
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(names5)
    axes[0].set_ylabel('Mean Enacted Rate (U/h)')
    axes[0].set_title('EXP-2225: Post-Meal Insulin Delivery by Phase')
    axes[0].legend()

    susp1 = [r2225[n]['phase1_suspend_pct'] for n in names5]
    susp2 = [r2225[n]['phase2_suspend_pct'] for n in names5]
    susp3 = [r2225[n]['phase3_suspend_pct'] for n in names5]

    axes[1].bar(x - w, susp1, w, label='0-1h', color='coral', alpha=0.8)
    axes[1].bar(x, susp2, w, label='1-2h', color='steelblue', alpha=0.8)
    axes[1].bar(x + w, susp3, w, label='2-4h', color='forestgreen', alpha=0.8)
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(names5)
    axes[1].set_ylabel('Suspend Percentage (%)')
    axes[1].set_title('EXP-2225: Post-Meal Suspend Rate by Phase')
    axes[1].legend()

    plt.tight_layout()
    plt.savefig(f'{fig_dir}/meal-fig05-postmeal-loop.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  [fig] meal-fig05-postmeal-loop.png")

    # Fig 6: Meal Variability (EXP-2226)
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    r2226 = all_results['exp_2226']
    names6 = sorted([n for n in r2226 if not r2226[n].get('skip', False)])

    cvs = [r2226[n]['overall_cv_pct'] for n in names6]
    spike_stds = [r2226[n]['overall_spike_std'] for n in names6]

    axes[0].bar(np.arange(len(names6)), cvs, color=[colors[i] for i in range(len(names6))], alpha=0.8)
    axes[0].set_xticks(np.arange(len(names6)))
    axes[0].set_xticklabels(names6)
    axes[0].set_ylabel('Spike CV (%)')
    axes[0].set_title('EXP-2226: Meal Response Variability (CV)')

    axes[1].bar(np.arange(len(names6)), spike_stds, color=[colors[i] for i in range(len(names6))], alpha=0.8)
    axes[1].set_xticks(np.arange(len(names6)))
    axes[1].set_xticklabels(names6)
    axes[1].set_ylabel('Spike StdDev (mg/dL)')
    axes[1].set_title('EXP-2226: Meal Spike Standard Deviation')

    plt.tight_layout()
    plt.savefig(f'{fig_dir}/meal-fig06-variability.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  [fig] meal-fig06-variability.png")

    # Fig 7: Optimal Pre-Bolus (EXP-2227)
    fig, ax = plt.subplots(figsize=(12, 6))
    r2227 = all_results['exp_2227']
    names7 = sorted([n for n in r2227 if not r2227[n].get('skip', False)])

    current = [r2227[n]['current_mean_timing'] for n in names7]
    optimal = []
    for n in names7:
        opt = r2227[n].get('optimal_timing_bin', '')
        if opt and '_to_' in opt:
            parts = opt.split('_to_')
            mid = (int(parts[0]) + int(parts[1].replace('min', ''))) / 2
            optimal.append(mid)
        else:
            optimal.append(0)

    x = np.arange(len(names7))
    w = 0.35
    ax.bar(x - w / 2, current, w, label='Current Mean', color='coral', alpha=0.8)
    ax.bar(x + w / 2, optimal, w, label='Optimal Bin Center', color='forestgreen', alpha=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(names7)
    ax.set_ylabel('Timing (minutes before carbs)')
    ax.set_title('EXP-2227: Current vs Optimal Pre-Bolus Timing')
    ax.legend()

    plt.tight_layout()
    plt.savefig(f'{fig_dir}/meal-fig07-optimal-prebolus.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  [fig] meal-fig07-optimal-prebolus.png")

    # Fig 8: Recovery Prediction (EXP-2228)
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    r2228 = all_results['exp_2228']
    names8 = sorted([n for n in r2228 if not r2228[n].get('skip', False)])

    fast_pct = [r2228[n]['fast_recovery_pct'] for n in names8]
    best_r = [abs(r2228[n]['best_predictor_r']) if r2228[n]['best_predictor_r'] else 0 for n in names8]

    axes[0].bar(np.arange(len(names8)), fast_pct, color=[colors[i] for i in range(len(names8))], alpha=0.8)
    axes[0].set_xticks(np.arange(len(names8)))
    axes[0].set_xticklabels(names8)
    axes[0].set_ylabel('% Fast Recovery (<2h)')
    axes[0].set_title('EXP-2228: Fast Meal Recovery Rate')

    axes[1].bar(np.arange(len(names8)), best_r, color=[colors[i] for i in range(len(names8))], alpha=0.8)
    axes[1].set_xticks(np.arange(len(names8)))
    axes[1].set_xticklabels(names8)
    axes[1].set_ylabel('|r| of Best Predictor')
    axes[1].set_title('EXP-2228: Recovery Predictability')
    # Annotate best predictor name
    for i, n in enumerate(names8):
        bp = r2228[n]['best_predictor']
        axes[1].annotate(bp, (i, best_r[i] + 0.01), ha='center', fontsize=7, rotation=45)

    plt.tight_layout()
    plt.savefig(f'{fig_dir}/meal-fig08-recovery.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  [fig] meal-fig08-recovery.png")


# ─────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description='EXP-2221–2228: Meal Pharmacodynamics')
    parser.add_argument('--figures', action='store_true', help='Generate figures')
    args = parser.parse_args()

    print("Loading patients...")
    patients = load_patients('externals/ns-data/patients/')
    print(f"  Loaded {len(patients)} patients")

    results = {}
    experiments = [
        ('exp_2221', 'Carb Absorption Curves', exp_2221_absorption_curves),
        ('exp_2222', 'Meal Size Dose-Response', exp_2222_dose_response),
        ('exp_2223', 'Pre-Bolus Timing Analysis', exp_2223_prebolus_timing),
        ('exp_2224', 'Meal Type Classification', exp_2224_meal_types),
        ('exp_2225', 'Post-Meal Loop Behavior', exp_2225_postmeal_loop),
        ('exp_2226', 'Meal-to-Meal Variability', exp_2226_meal_variability),
        ('exp_2227', 'Optimal Pre-Bolus Estimation', exp_2227_optimal_prebolus),
        ('exp_2228', 'Meal Recovery Prediction', exp_2228_recovery_prediction),
    ]

    for key, name, func in experiments:
        exp_id = key.replace('exp_', 'EXP-')
        print(f"\n{'=' * 60}")
        print(f"  {exp_id}: {name}")
        print(f"{'=' * 60}")
        try:
            results[key] = func(patients)
            print(f"  ✓ {exp_id} PASSED")

            if isinstance(results[key], dict):
                for pname, pdata in sorted(results[key].items()):
                    if isinstance(pdata, dict) and not pdata.get('skip', False):
                        summary = []
                        for k, v in list(pdata.items())[:5]:
                            if isinstance(v, (int, float)) and not isinstance(v, bool):
                                summary.append(f"{k}={v}")
                        if summary:
                            print(f"    {pname}: {', '.join(summary[:3])}")
        except Exception as e:
            print(f"  ✗ {exp_id} FAILED: {e}")
            import traceback
            traceback.print_exc()
            results[key] = {'error': str(e)}

    # Save results
    out_dir = 'externals/experiments'
    os.makedirs(out_dir, exist_ok=True)
    out_file = f'{out_dir}/exp-2221-2228_meal_pharma.json'
    with open(out_file, 'w') as f:
        json.dump(results, f, indent=2, cls=NumpyEncoder)
    print(f"\nResults saved to {out_file}")

    if args.figures:
        fig_dir = 'docs/60-research/figures'
        print("\nGenerating figures...")
        generate_figures(results, fig_dir)
        print("All figures generated.")

    print("\n" + "=" * 60)
    print("  SUMMARY: EXP-2221–2228")
    print("=" * 60)
    passed = sum(1 for k in results if 'error' not in results[k])
    print(f"  {passed}/8 experiments passed")

    return results


if __name__ == '__main__':
    main()
