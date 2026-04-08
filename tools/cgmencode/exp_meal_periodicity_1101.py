#!/usr/bin/env python3
"""EXP-1101 to EXP-1110: Meal Periodicity, Phase Stability & Proactive Prediction.

Building on supply×demand meal detection (F1=0.939, 18× spectral SNR, EXP-444/748):
- ~4,800 meal events across 11 patients × 180 days
- 46.5% unannounced meals detected via physics residuals
- Current meal_predictor.py uses naive Gaussian — no ML
- Meal timing periodicity and phase stability never formally studied

This batch explores whether detected meal events have learnable periodicity
and whether ML models can predict upcoming meals better than the Gaussian baseline:
  EXP-1101: Meal Periodicity Characterization ★★★
  EXP-1102: Phase Stability Over Weeks ★★★
  EXP-1103: Weekday vs Weekend Meal Patterns ★★
  EXP-1104: Meal Regularity Score ★★★
  EXP-1105: Carb Announcement Timing Alignment ★★
  EXP-1106: XGBoost Meal Timing Predictor ★★★
  EXP-1107: Temporal Point Process Model ★★★
  EXP-1108: Eating-Soon Override Predictor ★★
  EXP-1109: Personalized vs Population Models ★★★
  EXP-1110: Campaign Summary & Pipeline Recommendations ★★★

Run:
    PYTHONPATH=tools python -m cgmencode.exp_meal_periodicity_1101 --detail --save --max-patients 11
"""

import argparse
import json
import os
import sys
import time
import warnings
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy import signal as sig
from scipy import stats

warnings.filterwarnings('ignore')

try:
    from cgmencode.exp_metabolic_flux import load_patients, save_results
    from cgmencode.exp_metabolic_441 import compute_supply_demand
    from cgmencode.continuous_pk import build_continuous_pk_features
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from cgmencode.exp_metabolic_flux import load_patients, save_results
    from cgmencode.exp_metabolic_441 import compute_supply_demand
    from cgmencode.continuous_pk import build_continuous_pk_features

PATIENTS_DIR = str(Path(__file__).resolve().parent.parent.parent
                   / 'externals' / 'ns-data' / 'patients')
GLUCOSE_SCALE = 400.0
STEPS_PER_DAY = 288  # 5-min intervals


# ---------------------------------------------------------------------------
# Shared: Detect meals from supply×demand for all patients
# ---------------------------------------------------------------------------

def detect_meals_from_physics(df, sd, threshold_sigma=2.0, merge_gap_steps=12):
    """Detect meal events from supply×demand residual bursts.

    Args:
        df: Patient DataFrame with glucose column
        sd: Supply-demand dict from compute_supply_demand
        threshold_sigma: Burst detection threshold (multiples of std)
        merge_gap_steps: Merge bursts within this many 5-min steps (60 min default)

    Returns:
        List of dicts with: index, hour, day_index, timestamp_step,
        estimated_size, is_announced, day_of_week
    """
    glucose = df['glucose'].values
    N = len(glucose)

    # Compute residual: actual glucose change - predicted (supply - demand)
    dg = np.diff(glucose, prepend=glucose[0])
    predicted = sd['net']
    residual = dg - predicted

    # Rolling positive residual sum (30 min = 6 steps)
    window = 6
    pos_resid = np.maximum(residual, 0)
    rolling_sum = np.convolve(pos_resid, np.ones(window), mode='same')

    # Threshold for burst detection
    mu = np.nanmean(rolling_sum)
    sigma = np.nanstd(rolling_sum)
    threshold = mu + threshold_sigma * sigma

    # Find burst regions
    above = rolling_sum > threshold
    bursts = []
    in_burst = False
    start = 0
    for i in range(N):
        if above[i] and not in_burst:
            in_burst = True
            start = i
        elif not above[i] and in_burst:
            in_burst = False
            bursts.append((start, i))
    if in_burst:
        bursts.append((start, N - 1))

    # Merge nearby bursts
    merged = []
    for s, e in bursts:
        if merged and s - merged[-1][1] < merge_gap_steps:
            merged[-1] = (merged[-1][0], e)
        else:
            merged.append((s, e))

    # Extract meal events
    meals = []
    # Check for carb_supply from PK
    has_carbs = 'carbs' in df.columns
    carb_supply = sd.get('carb_supply', np.zeros(N))

    for s, e in merged:
        mid = (s + e) // 2
        integral = float(np.sum(pos_resid[s:e]))
        hour = (mid % STEPS_PER_DAY) * 5.0 / 60.0  # fractional hour of day
        day_index = mid // STEPS_PER_DAY

        # Check if announced (carb supply present near burst)
        region = slice(max(0, s - 6), min(N, e + 6))
        announced = bool(np.any(carb_supply[region] > 0.5))

        # Day of week (0=Mon, 6=Sun) — approximate from day_index
        # We don't have actual dates, so use day_index mod 7
        dow = day_index % 7

        meals.append({
            'index': mid,
            'hour': hour,
            'day_index': day_index,
            'step': mid,
            'integral': integral,
            'announced': announced,
            'day_of_week': dow,
        })

    return meals


def meals_to_daily_events(meals, total_days):
    """Convert meal list to per-day event time series.

    Returns:
        event_hours: list of lists, one per day, containing meal hours
        daily_counts: (total_days,) array of meal counts per day
    """
    event_hours = [[] for _ in range(total_days)]
    daily_counts = np.zeros(total_days)
    for m in meals:
        d = m['day_index']
        if 0 <= d < total_days:
            event_hours[d].append(m['hour'])
            daily_counts[d] += 1
    return event_hours, daily_counts


def assign_meal_window(hour):
    """Assign a meal to breakfast/lunch/dinner/snack window."""
    if 5.0 <= hour < 10.0:
        return 'breakfast'
    elif 10.0 <= hour < 14.0:
        return 'lunch'
    elif 17.0 <= hour < 21.0:
        return 'dinner'
    else:
        return 'snack'


# ═══════════════════════════════════════════════════════════════════════
# EXP-1101: Meal Periodicity Characterization
# ═══════════════════════════════════════════════════════════════════════

def exp_1101_periodicity(patients, detail=False):
    """Autocorrelation + FFT of inter-meal intervals and meal event signal.

    Questions:
    1. Is there statistically significant 24h periodicity in meal events?
    2. Is there 4-6h periodicity (inter-meal spacing)?
    3. How strong is the periodic component vs noise?
    """
    results = {}
    summary_rows = []

    for p in patients:
        name = p['name']
        df = p['df']
        sd = compute_supply_demand(df, pk_array=p['pk'])
        meals = detect_meals_from_physics(df, sd)
        total_days = len(df) // STEPS_PER_DAY

        if len(meals) < 20:
            results[name] = {'status': 'insufficient_meals', 'n_meals': len(meals)}
            continue

        # --- 1. Inter-meal interval analysis ---
        meal_steps = sorted([m['step'] for m in meals])
        intervals = np.diff(meal_steps) * 5.0 / 60.0  # hours between consecutive meals

        # Remove overnight gaps (>10h)
        meal_intervals = intervals[intervals < 10.0]
        if len(meal_intervals) < 10:
            results[name] = {'status': 'too_few_intervals', 'n_meals': len(meals)}
            continue

        mean_interval = float(np.mean(meal_intervals))
        std_interval = float(np.std(meal_intervals))
        cv_interval = std_interval / mean_interval if mean_interval > 0 else 999

        # --- 2. Binary meal event signal (1 per 5-min step) ---
        N = len(df)
        meal_signal = np.zeros(N)
        for m in meals:
            idx = m['step']
            if 0 <= idx < N:
                meal_signal[idx] = 1.0

        # --- 3. Autocorrelation of meal signal ---
        # Compute autocorrelation at key lags
        max_lag = min(STEPS_PER_DAY * 3, N // 2)  # up to 3 days
        acf = np.correlate(meal_signal - meal_signal.mean(),
                           meal_signal - meal_signal.mean(),
                           mode='full')
        acf = acf[len(acf)//2:]  # positive lags only
        acf = acf / acf[0] if acf[0] > 0 else acf  # normalize

        # Key lags: 4h, 5h, 6h (inter-meal), 12h, 24h, 48h
        lag_hours = [4, 5, 6, 8, 12, 24, 48]
        lag_steps = [int(h * 12) for h in lag_hours]  # 12 steps per hour
        acf_at_lags = {}
        for h, s in zip(lag_hours, lag_steps):
            if s < len(acf):
                acf_at_lags[f'{h}h'] = round(float(acf[s]), 4)

        # --- 4. FFT of meal signal ---
        # Use Welch's method for power spectral density
        nperseg = min(STEPS_PER_DAY * 2, N // 4)
        if nperseg >= 64:
            freqs, psd = sig.welch(meal_signal, fs=12.0,  # 12 samples/hour
                                   nperseg=nperseg, noverlap=nperseg // 2)
            # Find power at key frequencies
            # 24h period = 1/24 cycles/hour
            # 6h period = 1/6 cycles/hour
            spectral_power = {}
            for period_h in [4, 5, 6, 8, 12, 24]:
                target_freq = 1.0 / period_h
                idx = np.argmin(np.abs(freqs - target_freq))
                spectral_power[f'{period_h}h'] = round(float(psd[idx]), 8)

            # Dominant period
            peak_idx = np.argmax(psd[1:]) + 1  # skip DC
            if freqs[peak_idx] > 0:
                dominant_period_h = round(1.0 / freqs[peak_idx], 1)
            else:
                dominant_period_h = None

            # SNR: power at 24h / mean power at non-harmonic frequencies
            harmonic_mask = np.zeros(len(freqs), dtype=bool)
            for period_h in [24, 12, 8, 6]:
                target_freq = 1.0 / period_h
                idx = np.argmin(np.abs(freqs - target_freq))
                harmonic_mask[max(0, idx-1):idx+2] = True
            noise_power = float(np.mean(psd[~harmonic_mask & (freqs > 0)]))
            signal_power = float(psd[np.argmin(np.abs(freqs - 1/24))])
            snr_24h = round(signal_power / noise_power, 2) if noise_power > 0 else 0
        else:
            spectral_power = {}
            dominant_period_h = None
            snr_24h = 0

        # --- 5. Significance test: permutation test for 24h autocorrelation ---
        acf_24h = acf_at_lags.get('24h', 0)
        n_perm = 200
        perm_acfs = []
        rng = np.random.RandomState(42)
        for _ in range(n_perm):
            shuffled = rng.permutation(meal_signal)
            sc = np.correlate(shuffled - shuffled.mean(),
                              shuffled - shuffled.mean(),
                              mode='full')
            sc = sc[len(sc)//2:]
            sc = sc / sc[0] if sc[0] > 0 else sc
            lag_24 = int(24 * 12)
            if lag_24 < len(sc):
                perm_acfs.append(float(sc[lag_24]))
        if perm_acfs:
            p_value_24h = float(np.mean(np.array(perm_acfs) >= acf_24h))
        else:
            p_value_24h = 1.0

        patient_result = {
            'n_meals': len(meals),
            'meals_per_day': round(len(meals) / max(total_days, 1), 2),
            'mean_interval_h': round(mean_interval, 2),
            'std_interval_h': round(std_interval, 2),
            'cv_interval': round(cv_interval, 3),
            'acf_at_lags': acf_at_lags,
            'spectral_power': spectral_power,
            'dominant_period_h': dominant_period_h,
            'snr_24h': snr_24h,
            'acf_24h': round(acf_24h, 4),
            'p_value_24h': round(p_value_24h, 4),
            'significant_24h': p_value_24h < 0.05,
        }
        results[name] = patient_result

        summary_rows.append({
            'patient': name,
            'meals/day': patient_result['meals_per_day'],
            'interval_μ': patient_result['mean_interval_h'],
            'interval_CV': patient_result['cv_interval'],
            'ACF_24h': patient_result['acf_24h'],
            'p_24h': patient_result['p_value_24h'],
            'sig?': '✓' if patient_result['significant_24h'] else '',
            'SNR_24h': patient_result['snr_24h'],
            'dominant_T': patient_result['dominant_period_h'],
        })

    # Print summary
    sig_count = sum(1 for r in results.values()
                    if isinstance(r, dict) and r.get('significant_24h'))
    total = sum(1 for r in results.values()
                if isinstance(r, dict) and 'acf_24h' in r)

    print(f"\n{'='*70}")
    print(f"EXP-1101: Meal Periodicity Characterization")
    print(f"{'='*70}")
    print(f"{'Patient':>8s} {'meals/d':>7s} {'intv_μ':>7s} {'intv_CV':>7s} "
          f"{'ACF_24h':>7s} {'p_24h':>7s} {'sig':>4s} {'SNR':>6s} {'dom_T':>6s}")
    print('-' * 70)
    for row in summary_rows:
        print(f"{row['patient']:>8s} {row['meals/day']:7.2f} {row['interval_μ']:7.2f} "
              f"{row['interval_CV']:7.3f} {row['ACF_24h']:7.4f} {row['p_24h']:7.4f} "
              f"{row['sig?']:>4s} {row['SNR_24h']:6.1f} "
              f"{str(row['dominant_T']):>6s}")
    print('-' * 70)
    print(f"Significant 24h periodicity: {sig_count}/{total} patients")

    mean_acf = np.mean([r['acf_24h'] for r in results.values() if 'acf_24h' in r])
    mean_snr = np.mean([r['snr_24h'] for r in results.values() if 'snr_24h' in r])
    print(f"Mean ACF@24h: {mean_acf:.4f}, Mean SNR@24h: {mean_snr:.1f}")

    return {
        'status': 'OK',
        'detail': f'{sig_count}/{total} patients show significant 24h meal periodicity '
                  f'(mean ACF={mean_acf:.4f}, SNR={mean_snr:.1f})',
        'results': results,
        'summary': {
            'significant_24h_count': sig_count,
            'total_patients': total,
            'mean_acf_24h': round(mean_acf, 4),
            'mean_snr_24h': round(mean_snr, 1),
        },
    }


# ═══════════════════════════════════════════════════════════════════════
# EXP-1102: Phase Stability Over Weeks
# ═══════════════════════════════════════════════════════════════════════

def exp_1102_phase_stability(patients, detail=False):
    """Track meal timing centroids over sliding weekly windows.

    Questions:
    1. Do meal times stay stable or drift over weeks/months?
    2. Which meal window is most stable?
    3. Can we quantify phase jitter per patient?
    """
    results = {}
    summary_rows = []

    for p in patients:
        name = p['name']
        df = p['df']
        sd = compute_supply_demand(df, pk_array=p['pk'])
        meals = detect_meals_from_physics(df, sd)
        total_days = len(df) // STEPS_PER_DAY

        if len(meals) < 30 or total_days < 21:
            results[name] = {'status': 'insufficient_data'}
            continue

        # Assign meals to windows
        for m in meals:
            m['window'] = assign_meal_window(m['hour'])

        # Sliding 7-day windows with 1-day stride
        window_days = 7
        stride_days = 1
        n_windows = (total_days - window_days) // stride_days + 1

        window_centroids = defaultdict(list)  # window_name → list of (week_idx, mean_hour)

        for w_idx in range(n_windows):
            start_day = w_idx * stride_days
            end_day = start_day + window_days

            for win_name in ['breakfast', 'lunch', 'dinner']:
                hours_in_window = [m['hour'] for m in meals
                                   if start_day <= m['day_index'] < end_day
                                   and m['window'] == win_name]
                if len(hours_in_window) >= 2:
                    centroid = float(np.mean(hours_in_window))
                    window_centroids[win_name].append({
                        'week': w_idx,
                        'centroid': centroid,
                        'n_meals': len(hours_in_window),
                        'std': float(np.std(hours_in_window)),
                    })

        # Compute phase stability metrics per window
        window_stats = {}
        for win_name, centroids in window_centroids.items():
            if len(centroids) < 5:
                continue
            centroid_values = [c['centroid'] for c in centroids]
            # Phase jitter: std of centroids over time
            jitter_hours = float(np.std(centroid_values))
            # Drift: linear regression of centroid vs week
            weeks = np.array([c['week'] for c in centroids])
            vals = np.array(centroid_values)
            if len(weeks) > 2:
                slope, intercept, r, p_val, se = stats.linregress(weeks, vals)
                drift_min_per_week = slope * 60.0  # convert hours/window to min/week
            else:
                drift_min_per_week = 0.0
                p_val = 1.0

            window_stats[win_name] = {
                'n_windows': len(centroids),
                'mean_hour': round(float(np.mean(centroid_values)), 2),
                'jitter_hours': round(jitter_hours, 3),
                'jitter_minutes': round(jitter_hours * 60, 1),
                'drift_min_per_week': round(drift_min_per_week, 2),
                'drift_p_value': round(p_val, 4),
                'significant_drift': p_val < 0.05,
            }

        # Overall stability score: inverse of mean jitter (lower jitter = more stable)
        jitters = [ws['jitter_minutes'] for ws in window_stats.values()]
        if jitters:
            mean_jitter = float(np.mean(jitters))
            stability_score = round(max(0, 100 - mean_jitter * 2), 1)  # 0-100 scale
        else:
            mean_jitter = 999
            stability_score = 0

        patient_result = {
            'total_meals': len(meals),
            'total_days': total_days,
            'window_stats': window_stats,
            'mean_jitter_min': round(mean_jitter, 1),
            'stability_score': stability_score,
        }
        results[name] = patient_result

        drift_flags = sum(1 for ws in window_stats.values() if ws.get('significant_drift'))
        summary_rows.append({
            'patient': name,
            'meals': len(meals),
            'days': total_days,
            'jitter_min': mean_jitter,
            'stability': stability_score,
            'drift_windows': drift_flags,
            'bkf_jitter': window_stats.get('breakfast', {}).get('jitter_minutes', '-'),
            'lunch_jitter': window_stats.get('lunch', {}).get('jitter_minutes', '-'),
            'dinner_jitter': window_stats.get('dinner', {}).get('jitter_minutes', '-'),
        })

    print(f"\n{'='*75}")
    print(f"EXP-1102: Phase Stability Over Weeks")
    print(f"{'='*75}")
    print(f"{'Patient':>8s} {'meals':>6s} {'days':>5s} {'jitter':>7s} "
          f"{'score':>6s} {'drift':>5s} {'bkf±':>7s} {'lnch±':>7s} {'dnr±':>7s}")
    print('-' * 75)
    for row in summary_rows:
        bkf = f"{row['bkf_jitter']:.1f}" if isinstance(row['bkf_jitter'], float) else row['bkf_jitter']
        lnch = f"{row['lunch_jitter']:.1f}" if isinstance(row['lunch_jitter'], float) else row['lunch_jitter']
        dnr = f"{row['dinner_jitter']:.1f}" if isinstance(row['dinner_jitter'], float) else row['dinner_jitter']
        print(f"{row['patient']:>8s} {row['meals']:6d} {row['days']:5d} "
              f"{row['jitter_min']:7.1f} {row['stability']:6.1f} "
              f"{row['drift_windows']:5d} {bkf:>7s} {lnch:>7s} {dnr:>7s}")

    mean_stability = np.mean([r['stability_score'] for r in results.values()
                              if 'stability_score' in r])
    print(f"\nMean stability score: {mean_stability:.1f}/100")

    return {
        'status': 'OK',
        'detail': f'Mean phase stability {mean_stability:.1f}/100 '
                  f'(jitter in minutes per meal window)',
        'results': results,
        'summary': {'mean_stability_score': round(mean_stability, 1)},
    }


# ═══════════════════════════════════════════════════════════════════════
# EXP-1103: Weekday vs Weekend Meal Patterns
# ═══════════════════════════════════════════════════════════════════════

def exp_1103_weekday_weekend(patients, detail=False):
    """Test whether meal timing differs between weekdays and weekends.

    Note: We approximate day-of-week from day_index since actual dates
    are not available. This tests for 7-day cyclicity regardless of
    which day is "Monday".
    """
    results = {}
    summary_rows = []

    for p in patients:
        name = p['name']
        df = p['df']
        sd = compute_supply_demand(df, pk_array=p['pk'])
        meals = detect_meals_from_physics(df, sd)
        total_days = len(df) // STEPS_PER_DAY

        if len(meals) < 30:
            results[name] = {'status': 'insufficient_meals'}
            continue

        # Assign windows
        for m in meals:
            m['window'] = assign_meal_window(m['hour'])

        # Split by "weekday" (days 0-4) vs "weekend" (days 5-6)
        # Using day_index % 7 as proxy
        weekday_meals = [m for m in meals if m['day_of_week'] < 5]
        weekend_meals = [m for m in meals if m['day_of_week'] >= 5]

        window_tests = {}
        for win_name in ['breakfast', 'lunch', 'dinner']:
            wd_hours = [m['hour'] for m in weekday_meals if m['window'] == win_name]
            we_hours = [m['hour'] for m in weekend_meals if m['window'] == win_name]

            if len(wd_hours) >= 5 and len(we_hours) >= 3:
                t_stat, p_val = stats.ttest_ind(wd_hours, we_hours, equal_var=False)
                diff_min = (np.mean(we_hours) - np.mean(wd_hours)) * 60
                window_tests[win_name] = {
                    'weekday_mean_h': round(float(np.mean(wd_hours)), 2),
                    'weekend_mean_h': round(float(np.mean(we_hours)), 2),
                    'diff_minutes': round(float(diff_min), 1),
                    'p_value': round(float(p_val), 4),
                    'significant': p_val < 0.05,
                    'weekday_n': len(wd_hours),
                    'weekend_n': len(we_hours),
                }

        # Day-of-week ANOVA on all meal hours
        dow_groups = defaultdict(list)
        for m in meals:
            dow_groups[m['day_of_week']].append(m['hour'])

        groups = [v for v in dow_groups.values() if len(v) >= 3]
        if len(groups) >= 3:
            f_stat, anova_p = stats.f_oneway(*groups)
        else:
            f_stat, anova_p = 0, 1.0

        # Meals per day by day-of-week
        day_counts = defaultdict(list)
        for d in range(total_days):
            dow = d % 7
            count = sum(1 for m in meals if m['day_index'] == d)
            day_counts[dow].append(count)

        dow_mean_counts = {d: round(float(np.mean(c)), 2)
                          for d, c in sorted(day_counts.items())}

        patient_result = {
            'n_meals': len(meals),
            'weekday_meals': len(weekday_meals),
            'weekend_meals': len(weekend_meals),
            'window_tests': window_tests,
            'anova_f': round(float(f_stat), 3),
            'anova_p': round(float(anova_p), 4),
            'significant_dow': anova_p < 0.05,
            'meals_per_dow': dow_mean_counts,
        }
        results[name] = patient_result

        sig_windows = sum(1 for wt in window_tests.values() if wt.get('significant'))
        bkf_diff = window_tests.get('breakfast', {}).get('diff_minutes', 0)
        summary_rows.append({
            'patient': name,
            'n': len(meals),
            'anova_p': anova_p,
            'sig_dow': '✓' if anova_p < 0.05 else '',
            'sig_wins': sig_windows,
            'bkf_Δ': bkf_diff,
        })

    sig_dow_count = sum(1 for r in results.values()
                        if isinstance(r, dict) and r.get('significant_dow'))
    total_tested = sum(1 for r in results.values()
                       if isinstance(r, dict) and 'anova_p' in r)

    print(f"\n{'='*60}")
    print(f"EXP-1103: Weekday vs Weekend Meal Patterns")
    print(f"{'='*60}")
    print(f"{'Patient':>8s} {'n':>5s} {'ANOVA_p':>8s} {'sig?':>4s} "
          f"{'sig_wins':>8s} {'bkf_Δmin':>8s}")
    print('-' * 60)
    for row in summary_rows:
        print(f"{row['patient']:>8s} {row['n']:5d} {row['anova_p']:8.4f} "
              f"{row['sig_dow']:>4s} {row['sig_wins']:8d} {row['bkf_Δ']:8.1f}")
    print('-' * 60)
    print(f"Significant day-of-week effect: {sig_dow_count}/{total_tested}")

    return {
        'status': 'OK',
        'detail': f'{sig_dow_count}/{total_tested} patients show significant '
                  f'day-of-week meal timing differences',
        'results': results,
    }


# ═══════════════════════════════════════════════════════════════════════
# EXP-1104: Meal Regularity Score
# ═══════════════════════════════════════════════════════════════════════

def exp_1104_regularity_score(patients, detail=False):
    """Composite per-patient meal regularity metric.

    Components:
    1. Timing consistency: low std of meal hours per window
    2. Frequency stability: consistent meals/day
    3. Inter-meal regularity: low CV of meal spacing
    4. Coverage: fraction of days with expected meal pattern
    """
    results = {}
    summary_rows = []

    for p in patients:
        name = p['name']
        df = p['df']
        sd = compute_supply_demand(df, pk_array=p['pk'])
        meals = detect_meals_from_physics(df, sd)
        total_days = len(df) // STEPS_PER_DAY

        if len(meals) < 20:
            results[name] = {'status': 'insufficient_meals'}
            continue

        for m in meals:
            m['window'] = assign_meal_window(m['hour'])

        # 1. Timing consistency per window
        timing_scores = {}
        for win_name in ['breakfast', 'lunch', 'dinner']:
            hours = [m['hour'] for m in meals if m['window'] == win_name]
            if len(hours) >= 5:
                std_h = float(np.std(hours))
                # Score: 100 if std < 0.25h (15 min), 0 if std > 2h
                timing_scores[win_name] = max(0, min(100,
                    100 * (1 - (std_h - 0.25) / 1.75)))
            else:
                timing_scores[win_name] = 0

        timing_consistency = float(np.mean(list(timing_scores.values())))

        # 2. Frequency stability: CV of daily meal count
        event_hours, daily_counts = meals_to_daily_events(meals, total_days)
        # Exclude empty days (gaps in data)
        active_counts = daily_counts[daily_counts > 0]
        if len(active_counts) > 5:
            freq_cv = float(np.std(active_counts) / np.mean(active_counts))
            freq_score = max(0, min(100, 100 * (1 - freq_cv)))
        else:
            freq_score = 0

        # 3. Inter-meal regularity (within-day)
        meal_steps = sorted([m['step'] for m in meals])
        intervals = np.diff(meal_steps) * 5.0 / 60.0
        daytime_intervals = intervals[(intervals > 1.0) & (intervals < 10.0)]
        if len(daytime_intervals) > 10:
            interval_cv = float(np.std(daytime_intervals) / np.mean(daytime_intervals))
            interval_score = max(0, min(100, 100 * (1 - interval_cv)))
        else:
            interval_score = 0

        # 4. Coverage: fraction of days with 2+ meals
        coverage = float(np.mean(daily_counts >= 2))
        coverage_score = coverage * 100

        # Composite score (equal weighting)
        composite = (timing_consistency * 0.35 + freq_score * 0.25 +
                     interval_score * 0.25 + coverage_score * 0.15)

        patient_result = {
            'n_meals': len(meals),
            'total_days': total_days,
            'timing_consistency': round(timing_consistency, 1),
            'timing_per_window': {k: round(v, 1) for k, v in timing_scores.items()},
            'frequency_score': round(freq_score, 1),
            'interval_score': round(interval_score, 1),
            'coverage_score': round(coverage_score, 1),
            'composite_regularity': round(composite, 1),
            'meals_per_day_mean': round(float(np.mean(active_counts)), 2) if len(active_counts) > 0 else 0,
            'meals_per_day_std': round(float(np.std(active_counts)), 2) if len(active_counts) > 0 else 0,
        }
        results[name] = patient_result

        summary_rows.append({
            'patient': name,
            'composite': composite,
            'timing': timing_consistency,
            'freq': freq_score,
            'interval': interval_score,
            'coverage': coverage_score,
            'm_per_d': patient_result['meals_per_day_mean'],
        })

    # Sort by composite score
    summary_rows.sort(key=lambda r: r['composite'], reverse=True)

    print(f"\n{'='*75}")
    print(f"EXP-1104: Meal Regularity Score")
    print(f"{'='*75}")
    print(f"{'Patient':>8s} {'Composite':>9s} {'Timing':>7s} {'Freq':>6s} "
          f"{'IntrvCV':>7s} {'Cover':>6s} {'m/day':>6s}")
    print('-' * 75)
    for row in summary_rows:
        print(f"{row['patient']:>8s} {row['composite']:9.1f} {row['timing']:7.1f} "
              f"{row['freq']:6.1f} {row['interval']:7.1f} {row['coverage']:6.1f} "
              f"{row['m_per_d']:6.2f}")

    composites = [r['composite_regularity'] for r in results.values()
                  if 'composite_regularity' in r]
    mean_composite = float(np.mean(composites)) if composites else 0
    print(f"\nMean composite regularity: {mean_composite:.1f}/100")

    # Classify patients
    regular = [n for n, r in results.items()
               if r.get('composite_regularity', 0) >= 60]
    moderate = [n for n, r in results.items()
                if 40 <= r.get('composite_regularity', 0) < 60]
    irregular = [n for n, r in results.items()
                 if r.get('composite_regularity', 0) < 40]
    print(f"Regular (≥60): {regular}")
    print(f"Moderate (40-60): {moderate}")
    print(f"Irregular (<40): {irregular}")

    return {
        'status': 'OK',
        'detail': f'Mean regularity {mean_composite:.1f}/100. '
                  f'Regular: {len(regular)}, Moderate: {len(moderate)}, '
                  f'Irregular: {len(irregular)}',
        'results': results,
        'summary': {
            'mean_composite': round(mean_composite, 1),
            'regular_patients': regular,
            'moderate_patients': moderate,
            'irregular_patients': irregular,
        },
    }


# ═══════════════════════════════════════════════════════════════════════
# EXP-1105: Carb Announcement Timing Alignment
# ═══════════════════════════════════════════════════════════════════════

def exp_1105_announcement_alignment(patients, detail=False):
    """Measure patient-specific carb logging delay vs physics-detected meal onset.

    Questions:
    1. How late do patients log carbs relative to actual meal start?
    2. Is the delay consistent (learnable)?
    3. Can we correct timestamps to get better training labels?
    """
    results = {}
    summary_rows = []

    for p in patients:
        name = p['name']
        df = p['df']
        sd = compute_supply_demand(df, pk_array=p['pk'])
        meals = detect_meals_from_physics(df, sd)

        if len(meals) < 20:
            results[name] = {'status': 'insufficient_meals'}
            continue

        # Find announced meals (where carb_supply is present)
        carb_supply = sd.get('carb_supply', np.zeros(len(df)))
        announced = [m for m in meals if m['announced']]

        if len(announced) < 10:
            results[name] = {'status': 'few_announced',
                             'n_announced': len(announced),
                             'n_total': len(meals)}
            continue

        # For each announced meal, find the nearest carb_supply onset
        delays = []
        for m in announced:
            idx = m['step']
            # Search backward and forward for carb_supply onset
            search_range = 36  # ±3 hours
            start = max(0, idx - search_range)
            end = min(len(carb_supply), idx + search_range)
            region = carb_supply[start:end]

            # Find first non-zero in region
            nonzero = np.where(region > 0.5)[0]
            if len(nonzero) > 0:
                carb_onset = start + nonzero[0]
                delay_steps = idx - carb_onset  # positive = physics detected after carb entry
                delay_min = delay_steps * 5.0
                delays.append(delay_min)

        if len(delays) < 5:
            results[name] = {'status': 'alignment_failed', 'n_pairs': len(delays)}
            continue

        delays = np.array(delays)
        patient_result = {
            'n_announced': len(announced),
            'n_total': len(meals),
            'announced_fraction': round(len(announced) / len(meals), 3),
            'n_aligned_pairs': len(delays),
            'mean_delay_min': round(float(np.mean(delays)), 1),
            'median_delay_min': round(float(np.median(delays)), 1),
            'std_delay_min': round(float(np.std(delays)), 1),
            'delay_25pct': round(float(np.percentile(delays, 25)), 1),
            'delay_75pct': round(float(np.percentile(delays, 75)), 1),
            'pct_pre_bolus': round(float(np.mean(delays < 0)) * 100, 1),
            'pct_late_log': round(float(np.mean(delays > 15)) * 100, 1),
        }
        results[name] = patient_result

        summary_rows.append({
            'patient': name,
            'pairs': len(delays),
            'ann_frac': patient_result['announced_fraction'],
            'delay_μ': patient_result['mean_delay_min'],
            'delay_med': patient_result['median_delay_min'],
            'delay_σ': patient_result['std_delay_min'],
            'pre_bolus%': patient_result['pct_pre_bolus'],
            'late_log%': patient_result['pct_late_log'],
        })

    print(f"\n{'='*75}")
    print(f"EXP-1105: Carb Announcement Timing Alignment")
    print(f"{'='*75}")
    print(f"{'Patient':>8s} {'pairs':>5s} {'ann%':>5s} {'delay_μ':>7s} "
          f"{'delay_med':>9s} {'delay_σ':>7s} {'pre%':>5s} {'late%':>5s}")
    print('-' * 75)
    for row in summary_rows:
        print(f"{row['patient']:>8s} {row['pairs']:5d} {row['ann_frac']:5.2f} "
              f"{row['delay_μ']:7.1f} {row['delay_med']:9.1f} {row['delay_σ']:7.1f} "
              f"{row['pre_bolus%']:5.1f} {row['late_log%']:5.1f}")

    all_delays = [r['mean_delay_min'] for r in results.values()
                  if 'mean_delay_min' in r]
    if all_delays:
        print(f"\nMean delay across patients: {np.mean(all_delays):.1f} min")
        print(f"Pre-bolus (carb entry before physics detection): "
              f"{np.mean([r.get('pct_pre_bolus', 0) for r in results.values() if 'pct_pre_bolus' in r]):.1f}%")

    return {
        'status': 'OK',
        'detail': f'Mean carb logging delay: {np.mean(all_delays):.1f} min' if all_delays else 'No data',
        'results': results,
    }


# ═══════════════════════════════════════════════════════════════════════
# EXP-1106: XGBoost Meal Timing Predictor
# ═══════════════════════════════════════════════════════════════════════

def exp_1106_xgboost_predictor(patients, detail=False):
    """ML model: time-of-day + recent meal history → P(meal in next 30/60 min).

    Features:
    - Hour of day (sin/cos encoded)
    - Minutes since last meal
    - Meals so far today
    - Day-of-week encoding
    - Glucose trend (15/30 min)
    - IOB level
    - Historical meal probability at this hour (from training set)

    Labels:
    - Positive: meal detected within next 30 min (or 60 min)

    Evaluation: Temporal split (first 80% train, last 20% val)
    """
    try:
        from sklearn.ensemble import GradientBoostingClassifier
        from sklearn.metrics import roc_auc_score, precision_recall_curve, f1_score
    except ImportError:
        return {'status': 'SKIP', 'detail': 'sklearn not available'}

    results = {}
    summary_rows = []

    for p in patients:
        name = p['name']
        df = p['df']
        sd = compute_supply_demand(df, pk_array=p['pk'])
        meals = detect_meals_from_physics(df, sd)
        total_days = len(df) // STEPS_PER_DAY

        if len(meals) < 30:
            results[name] = {'status': 'insufficient_meals'}
            continue

        N = len(df)
        glucose = df['glucose'].values

        # Build meal lookup: for each step, distance to next meal
        meal_steps = sorted(set(m['step'] for m in meals))
        next_meal_dist = np.full(N, 9999, dtype=np.float32)
        for ms in reversed(meal_steps):
            for i in range(max(0, ms - STEPS_PER_DAY), ms):
                dist = (ms - i) * 5  # minutes
                if dist < next_meal_dist[i]:
                    next_meal_dist[i] = dist

        # Previous meal distance
        prev_meal_dist = np.full(N, 9999, dtype=np.float32)
        for ms in meal_steps:
            for i in range(ms, min(N, ms + STEPS_PER_DAY)):
                dist = (i - ms) * 5  # minutes
                if dist < prev_meal_dist[i]:
                    prev_meal_dist[i] = dist

        # Meals so far today
        meals_today = np.zeros(N)
        current_day = -1
        count = 0
        meal_set = set(meal_steps)
        for i in range(N):
            day = i // STEPS_PER_DAY
            if day != current_day:
                current_day = day
                count = 0
            if i in meal_set:
                count += 1
            meals_today[i] = count

        # Historical meal probability at each hour (from first 80%)
        split = int(N * 0.8)
        train_meals = [m for m in meals if m['step'] < split]
        hour_hist = np.zeros(24)
        for m in train_meals:
            h = int(m['hour']) % 24
            hour_hist[h] += 1
        if hour_hist.sum() > 0:
            hour_hist = hour_hist / hour_hist.sum()

        # Build feature matrix
        features = np.zeros((N, 10))
        for i in range(N):
            hour = (i % STEPS_PER_DAY) * 5.0 / 60.0
            features[i, 0] = np.sin(2 * np.pi * hour / 24)  # hour sin
            features[i, 1] = np.cos(2 * np.pi * hour / 24)  # hour cos
            features[i, 2] = prev_meal_dist[i]  # min since last meal
            features[i, 3] = meals_today[i]  # meals so far today
            features[i, 4] = (i // STEPS_PER_DAY) % 7  # day of week proxy
            # Glucose trend (15 min = 3 steps)
            if i >= 3:
                features[i, 5] = glucose[i] - glucose[i-3]
            # Glucose trend (30 min = 6 steps)
            if i >= 6:
                features[i, 6] = glucose[i] - glucose[i-6]
            # Current glucose
            features[i, 7] = glucose[i] / GLUCOSE_SCALE
            # Supply-demand balance
            features[i, 8] = sd['net'][i] if i < len(sd['net']) else 0
            # Historical meal prob at this hour
            h_idx = int(hour) % 24
            features[i, 9] = hour_hist[h_idx]

        # Labels: meal within next 30 min and 60 min
        label_30 = (next_meal_dist <= 30).astype(int)
        label_60 = (next_meal_dist <= 60).astype(int)

        # Temporal split
        X_train, X_val = features[:split], features[split:]
        y_train_30, y_val_30 = label_30[:split], label_30[split:]
        y_train_60, y_val_60 = label_60[:split], label_60[split:]

        patient_result = {'n_meals': len(meals)}

        for horizon, y_tr, y_va, lbl in [
            (30, y_train_30, y_val_30, '30min'),
            (60, y_train_60, y_val_60, '60min'),
        ]:
            if y_tr.sum() < 10 or y_va.sum() < 5:
                patient_result[lbl] = {'status': 'insufficient_positives'}
                continue

            clf = GradientBoostingClassifier(
                n_estimators=100, max_depth=4, learning_rate=0.1,
                subsample=0.8, random_state=42)
            clf.fit(X_train, y_tr)

            proba = clf.predict_proba(X_val)[:, 1]
            auc = roc_auc_score(y_va, proba)

            # Find best F1 threshold
            prec, rec, thresholds = precision_recall_curve(y_va, proba)
            f1s = 2 * prec * rec / (prec + rec + 1e-8)
            best_idx = np.argmax(f1s)
            best_f1 = float(f1s[best_idx])
            best_thresh = float(thresholds[best_idx]) if best_idx < len(thresholds) else 0.5
            best_prec = float(prec[best_idx])
            best_rec = float(rec[best_idx])

            # Baseline: predict using only hour_hist
            baseline_proba = np.array([hour_hist[int((j % STEPS_PER_DAY) * 5 / 60) % 24]
                                       for j in range(split, N)])
            # Normalize baseline to [0, 1]
            if baseline_proba.max() > 0:
                baseline_proba = baseline_proba / baseline_proba.max()
            try:
                baseline_auc = roc_auc_score(y_va, baseline_proba)
            except ValueError:
                baseline_auc = 0.5

            # Feature importance
            feat_names = ['hour_sin', 'hour_cos', 'min_since_meal', 'meals_today',
                          'dow', 'gluc_trend_15', 'gluc_trend_30', 'glucose',
                          'net_flux', 'hist_meal_prob']
            importances = dict(zip(feat_names,
                                   [round(float(x), 4) for x in clf.feature_importances_]))

            patient_result[lbl] = {
                'auc': round(auc, 4),
                'baseline_auc': round(baseline_auc, 4),
                'auc_lift': round(auc - baseline_auc, 4),
                'best_f1': round(best_f1, 4),
                'best_precision': round(best_prec, 4),
                'best_recall': round(best_rec, 4),
                'best_threshold': round(best_thresh, 4),
                'positive_rate_train': round(float(y_tr.mean()), 4),
                'positive_rate_val': round(float(y_va.mean()), 4),
                'feature_importance': importances,
            }

        results[name] = patient_result

        auc_30 = patient_result.get('30min', {}).get('auc', 0)
        auc_60 = patient_result.get('60min', {}).get('auc', 0)
        lift_30 = patient_result.get('30min', {}).get('auc_lift', 0)
        f1_30 = patient_result.get('30min', {}).get('best_f1', 0)
        summary_rows.append({
            'patient': name,
            'auc_30': auc_30,
            'auc_60': auc_60,
            'lift_30': lift_30,
            'f1_30': f1_30,
        })

    print(f"\n{'='*65}")
    print(f"EXP-1106: XGBoost Meal Timing Predictor")
    print(f"{'='*65}")
    print(f"{'Patient':>8s} {'AUC_30':>7s} {'AUC_60':>7s} {'Lift_30':>7s} {'F1_30':>6s}")
    print('-' * 65)
    for row in summary_rows:
        print(f"{row['patient']:>8s} {row['auc_30']:7.4f} {row['auc_60']:7.4f} "
              f"{row['lift_30']:7.4f} {row['f1_30']:6.4f}")

    mean_auc = np.mean([r['auc_30'] for r in summary_rows if r['auc_30'] > 0])
    mean_lift = np.mean([r['lift_30'] for r in summary_rows if r['lift_30'] != 0])
    print(f"\nMean AUC@30min: {mean_auc:.4f}, Mean lift over baseline: {mean_lift:.4f}")

    return {
        'status': 'OK',
        'detail': f'Mean AUC@30min: {mean_auc:.4f}, lift: {mean_lift:.4f}',
        'results': results,
        'summary': {
            'mean_auc_30': round(mean_auc, 4),
            'mean_lift_30': round(mean_lift, 4),
        },
    }


# ═══════════════════════════════════════════════════════════════════════
# EXP-1107: Temporal Point Process Model
# ═══════════════════════════════════════════════════════════════════════

def exp_1107_point_process(patients, detail=False):
    """Lightweight temporal point process: LSTM on meal event sequences.

    Input: sequence of (time_since_last_meal, hour_of_day, meal_size, announced)
    Output: predicted time until next meal (regression)

    This tests whether sequential meal patterns improve over the
    per-window Gaussian baseline.
    """
    try:
        import torch
        import torch.nn as nn
        from torch.utils.data import DataLoader, TensorDataset
    except ImportError:
        return {'status': 'SKIP', 'detail': 'PyTorch not available'}

    class MealSequenceLSTM(nn.Module):
        def __init__(self, input_dim=4, hidden_dim=32, n_layers=1):
            super().__init__()
            self.lstm = nn.LSTM(input_dim, hidden_dim, n_layers, batch_first=True)
            self.fc = nn.Linear(hidden_dim, 1)

        def forward(self, x):
            out, _ = self.lstm(x)
            return self.fc(out[:, -1, :]).squeeze(-1)

    results = {}
    summary_rows = []

    for p in patients:
        name = p['name']
        df = p['df']
        sd = compute_supply_demand(df, pk_array=p['pk'])
        meals = detect_meals_from_physics(df, sd)

        if len(meals) < 40:
            results[name] = {'status': 'insufficient_meals'}
            continue

        # Build sequences: for each meal, look back at last K meals
        K = 8  # sequence length
        sorted_meals = sorted(meals, key=lambda m: m['step'])

        sequences = []
        targets = []
        for i in range(K, len(sorted_meals) - 1):
            seq = []
            for j in range(i - K, i):
                # Time since previous meal (hours)
                if j > 0:
                    dt = (sorted_meals[j]['step'] - sorted_meals[j-1]['step']) * 5.0 / 60.0
                else:
                    dt = 4.0  # default
                dt = min(dt, 24.0)  # cap at 24h

                seq.append([
                    dt,
                    sorted_meals[j]['hour'] / 24.0,  # normalized hour
                    sorted_meals[j]['integral'] / 100.0,  # normalized size
                    1.0 if sorted_meals[j]['announced'] else 0.0,
                ])

            # Target: time until next meal (hours)
            target_dt = (sorted_meals[i]['step'] - sorted_meals[i-1]['step']) * 5.0 / 60.0
            target_dt = min(target_dt, 24.0)

            sequences.append(seq)
            targets.append(target_dt)

        if len(sequences) < 30:
            results[name] = {'status': 'too_few_sequences'}
            continue

        X = torch.tensor(sequences, dtype=torch.float32)
        y = torch.tensor(targets, dtype=torch.float32)

        # Temporal split
        split = int(len(X) * 0.8)
        X_train, X_val = X[:split], X[split:]
        y_train, y_val = y[:split], y[split:]

        # Baseline: predict mean interval from training set
        baseline_pred = float(y_train.mean())
        baseline_mae = float(torch.abs(y_val - baseline_pred).mean())

        # Gaussian baseline: per-window mean from training meals
        train_meals = sorted_meals[:split + K]
        window_means = {}
        for m in train_meals:
            w = assign_meal_window(m['hour'])
            window_means.setdefault(w, []).append(m['hour'])
        window_means = {k: np.mean(v) for k, v in window_means.items()}

        # Train LSTM
        model = MealSequenceLSTM()
        optimizer = torch.optim.Adam(model.parameters(), lr=0.005)
        loss_fn = nn.MSELoss()

        best_val_mae = float('inf')
        patience = 15
        patience_counter = 0

        for epoch in range(100):
            model.train()
            optimizer.zero_grad()
            pred = model(X_train)
            loss = loss_fn(pred, y_train)
            loss.backward()
            optimizer.step()

            model.eval()
            with torch.no_grad():
                val_pred = model(X_val)
                val_mae = float(torch.abs(val_pred - y_val).mean())

            if val_mae < best_val_mae:
                best_val_mae = val_mae
                patience_counter = 0
            else:
                patience_counter += 1
                if patience_counter >= patience:
                    break

        # Convert MAE to minutes
        lstm_mae_h = best_val_mae
        lstm_mae_min = lstm_mae_h * 60

        patient_result = {
            'n_meals': len(meals),
            'n_sequences': len(sequences),
            'lstm_mae_hours': round(lstm_mae_h, 3),
            'lstm_mae_minutes': round(lstm_mae_min, 1),
            'baseline_mae_hours': round(baseline_mae, 3),
            'baseline_mae_minutes': round(baseline_mae * 60, 1),
            'improvement_minutes': round((baseline_mae - lstm_mae_h) * 60, 1),
            'improvement_pct': round((1 - lstm_mae_h / baseline_mae) * 100, 1) if baseline_mae > 0 else 0,
            'mean_interval_h': round(float(y_train.mean()), 2),
        }
        results[name] = patient_result

        summary_rows.append({
            'patient': name,
            'n': len(meals),
            'lstm_mae': lstm_mae_min,
            'base_mae': baseline_mae * 60,
            'Δ_min': (baseline_mae - lstm_mae_h) * 60,
            'Δ%': patient_result['improvement_pct'],
        })

    print(f"\n{'='*65}")
    print(f"EXP-1107: Temporal Point Process (LSTM) Meal Predictor")
    print(f"{'='*65}")
    print(f"{'Patient':>8s} {'n':>5s} {'LSTM_MAE':>8s} {'Base_MAE':>8s} "
          f"{'Δ_min':>7s} {'Δ%':>6s}")
    print('-' * 65)
    for row in summary_rows:
        print(f"{row['patient']:>8s} {row['n']:5d} {row['lstm_mae']:8.1f} "
              f"{row['base_mae']:8.1f} {row['Δ_min']:7.1f} {row['Δ%']:6.1f}%")

    mean_lstm = np.mean([r['lstm_mae'] for r in summary_rows])
    mean_base = np.mean([r['base_mae'] for r in summary_rows])
    wins = sum(1 for r in summary_rows if r['Δ_min'] > 0)
    print(f"\nMean LSTM MAE: {mean_lstm:.1f} min vs Baseline: {mean_base:.1f} min")
    print(f"LSTM wins: {wins}/{len(summary_rows)}")

    return {
        'status': 'OK',
        'detail': f'LSTM MAE={mean_lstm:.1f}min vs baseline={mean_base:.1f}min, '
                  f'wins {wins}/{len(summary_rows)}',
        'results': results,
    }


# ═══════════════════════════════════════════════════════════════════════
# EXP-1108: Eating-Soon Override Predictor
# ═══════════════════════════════════════════════════════════════════════

def exp_1108_eating_soon(patients, detail=False):
    """Use carb entries as proxy labels: predict when to recommend eating-soon.

    The 30-60 min window before a detected meal = the "eating soon" zone.
    Train a classifier to identify when we're in that zone.

    This simulates the production use case: given current state,
    should we suggest an eating-soon override?
    """
    try:
        from sklearn.ensemble import GradientBoostingClassifier
        from sklearn.metrics import roc_auc_score, precision_score, recall_score
    except ImportError:
        return {'status': 'SKIP', 'detail': 'sklearn not available'}

    results = {}
    summary_rows = []

    for p in patients:
        name = p['name']
        df = p['df']
        sd = compute_supply_demand(df, pk_array=p['pk'])
        meals = detect_meals_from_physics(df, sd)

        if len(meals) < 30:
            results[name] = {'status': 'insufficient_meals'}
            continue

        N = len(df)
        glucose = df['glucose'].values

        # Label: 1 if a meal occurs within 30-60 min from now
        # (not within 0-30 min — that's too late for pre-bolus)
        meal_steps = set(m['step'] for m in meals)
        label = np.zeros(N, dtype=int)
        for ms in meal_steps:
            # The "eating soon" window is 30-60 min before the meal
            # That's steps ms-12 to ms-6 (60 to 30 min before)
            for i in range(max(0, ms - 12), max(0, ms - 6)):
                label[i] = 1

        # Features similar to EXP-1106 but focused on pre-meal detection
        features = np.zeros((N, 12))
        # Pre-compute previous meal distances
        prev_meal_dist = np.full(N, 9999.0)
        for ms in sorted(meal_steps):
            for i in range(ms, min(N, ms + STEPS_PER_DAY)):
                d = (i - ms) * 5.0
                if d < prev_meal_dist[i]:
                    prev_meal_dist[i] = d

        for i in range(N):
            hour = (i % STEPS_PER_DAY) * 5.0 / 60.0
            features[i, 0] = np.sin(2 * np.pi * hour / 24)
            features[i, 1] = np.cos(2 * np.pi * hour / 24)
            features[i, 2] = min(prev_meal_dist[i], 720) / 720  # minutes since last meal, capped
            features[i, 3] = glucose[i] / GLUCOSE_SCALE
            if i >= 3:
                features[i, 4] = glucose[i] - glucose[i-3]  # 15-min trend
            if i >= 6:
                features[i, 5] = glucose[i] - glucose[i-6]  # 30-min trend
            features[i, 6] = sd['net'][i] if i < len(sd['net']) else 0
            features[i, 7] = sd['supply'][i] if i < len(sd['supply']) else 0
            features[i, 8] = sd['demand'][i] if i < len(sd['demand']) else 0
            features[i, 9] = sd['carb_supply'][i] if i < len(sd['carb_supply']) else 0
            # Throughput (supply × demand)
            features[i, 10] = sd['product'][i] if i < len(sd['product']) else 0
            features[i, 11] = (i // STEPS_PER_DAY) % 7  # day of week

        # Temporal split
        split = int(N * 0.8)
        X_train, X_val = features[:split], features[split:]
        y_train, y_val = label[:split], label[split:]

        if y_train.sum() < 10 or y_val.sum() < 5:
            results[name] = {'status': 'insufficient_positives'}
            continue

        clf = GradientBoostingClassifier(
            n_estimators=100, max_depth=4, learning_rate=0.1,
            subsample=0.8, random_state=42)
        clf.fit(X_train, y_train)

        proba = clf.predict_proba(X_val)[:, 1]
        auc = roc_auc_score(y_val, proba)

        # At precision ≥ 0.7 threshold (acceptable false alarm rate)
        thresholds = np.linspace(0.01, 0.99, 100)
        best_recall_at_prec70 = 0
        best_thresh = 0.5
        for t in thresholds:
            pred = (proba >= t).astype(int)
            if pred.sum() > 0:
                prec = precision_score(y_val, pred, zero_division=0)
                rec = recall_score(y_val, pred, zero_division=0)
                if prec >= 0.7 and rec > best_recall_at_prec70:
                    best_recall_at_prec70 = rec
                    best_thresh = t

        # Feature importance
        feat_names = ['hour_sin', 'hour_cos', 'min_since_meal', 'glucose',
                      'trend_15', 'trend_30', 'net_flux', 'supply', 'demand',
                      'carb_supply', 'throughput', 'dow']
        importances = dict(zip(feat_names,
                               [round(float(x), 4) for x in clf.feature_importances_]))

        # Lead time analysis: for correct predictions, how much lead time?
        pred_at_thresh = (proba >= best_thresh).astype(int)
        lead_times = []
        for ms in meal_steps:
            if ms >= split:
                # Check if any prediction in 30-90 min before
                check_range = range(max(0, ms - 18 - (N - split)),
                                    max(0, ms - 6 - (N - split)))
                for ci in check_range:
                    if 0 <= ci < len(pred_at_thresh) and pred_at_thresh[ci]:
                        lead = (ms - (ci + split)) * 5
                        lead_times.append(lead)
                        break

        patient_result = {
            'n_meals': len(meals),
            'auc': round(auc, 4),
            'recall_at_prec70': round(best_recall_at_prec70, 4),
            'best_threshold': round(best_thresh, 4),
            'positive_rate': round(float(y_val.mean()), 4),
            'feature_importance': importances,
            'mean_lead_time_min': round(float(np.mean(lead_times)), 1) if lead_times else 0,
            'lead_time_coverage': round(len(lead_times) / max(1, sum(1 for ms in meal_steps if ms >= split)), 3),
        }
        results[name] = patient_result

        summary_rows.append({
            'patient': name,
            'auc': auc,
            'rec@p70': best_recall_at_prec70,
            'lead_min': patient_result['mean_lead_time_min'],
            'coverage': patient_result['lead_time_coverage'],
        })

    print(f"\n{'='*65}")
    print(f"EXP-1108: Eating-Soon Override Predictor")
    print(f"{'='*65}")
    print(f"{'Patient':>8s} {'AUC':>7s} {'Rec@P70':>7s} {'Lead_min':>8s} {'Coverage':>8s}")
    print('-' * 65)
    for row in summary_rows:
        print(f"{row['patient']:>8s} {row['auc']:7.4f} {row['rec@p70']:7.4f} "
              f"{row['lead_min']:8.1f} {row['coverage']:8.3f}")

    mean_auc = np.mean([r['auc'] for r in summary_rows])
    mean_rec = np.mean([r['rec@p70'] for r in summary_rows])
    print(f"\nMean AUC: {mean_auc:.4f}, Mean Recall@Precision70: {mean_rec:.4f}")

    return {
        'status': 'OK',
        'detail': f'Eating-soon AUC={mean_auc:.4f}, Recall@Prec70={mean_rec:.4f}',
        'results': results,
    }


# ═══════════════════════════════════════════════════════════════════════
# EXP-1109: Personalized vs Population Models
# ═══════════════════════════════════════════════════════════════════════

def exp_1109_personal_vs_population(patients, detail=False):
    """Compare per-patient models vs pooled population model for meal prediction.

    Tests the hypothesis from EXP-978 (0/40 features generalize) applied
    specifically to meal timing: do meal patterns transfer across patients?
    """
    try:
        from sklearn.ensemble import GradientBoostingClassifier
        from sklearn.metrics import roc_auc_score
    except ImportError:
        return {'status': 'SKIP', 'detail': 'sklearn not available'}

    # First, build pooled training data from all patients
    all_X_train = []
    all_y_train = []
    per_patient_data = {}

    for p in patients:
        name = p['name']
        df = p['df']
        sd = compute_supply_demand(df, pk_array=p['pk'])
        meals = detect_meals_from_physics(df, sd)

        if len(meals) < 30:
            continue

        N = len(df)
        glucose = df['glucose'].values

        # Build meal distance lookup
        meal_steps = sorted(set(m['step'] for m in meals))
        next_meal_dist = np.full(N, 9999, dtype=np.float32)
        for ms in reversed(meal_steps):
            for i in range(max(0, ms - STEPS_PER_DAY), ms):
                dist = (ms - i) * 5
                if dist < next_meal_dist[i]:
                    next_meal_dist[i] = dist

        prev_meal_dist = np.full(N, 9999.0)
        for ms in meal_steps:
            for i in range(ms, min(N, ms + STEPS_PER_DAY)):
                d = (i - ms) * 5.0
                if d < prev_meal_dist[i]:
                    prev_meal_dist[i] = d

        # Features (same as 1106 but simpler)
        features = np.zeros((N, 8))
        for i in range(N):
            hour = (i % STEPS_PER_DAY) * 5.0 / 60.0
            features[i, 0] = np.sin(2 * np.pi * hour / 24)
            features[i, 1] = np.cos(2 * np.pi * hour / 24)
            features[i, 2] = min(prev_meal_dist[i], 720) / 720
            features[i, 3] = glucose[i] / GLUCOSE_SCALE
            if i >= 6:
                features[i, 4] = glucose[i] - glucose[i-6]
            features[i, 5] = sd['net'][i] if i < len(sd['net']) else 0
            features[i, 6] = sd['product'][i] if i < len(sd['product']) else 0
            features[i, 7] = (i // STEPS_PER_DAY) % 7

        label_60 = (next_meal_dist <= 60).astype(int)
        split = int(N * 0.8)

        per_patient_data[name] = {
            'X_train': features[:split],
            'X_val': features[split:],
            'y_train': label_60[:split],
            'y_val': label_60[split:],
        }

        all_X_train.append(features[:split])
        all_y_train.append(label_60[:split])

    if not all_X_train:
        return {'status': 'FAIL', 'detail': 'No patient data available'}

    # Train pooled model
    pooled_X = np.vstack(all_X_train)
    pooled_y = np.concatenate(all_y_train)

    pooled_clf = GradientBoostingClassifier(
        n_estimators=100, max_depth=4, learning_rate=0.1,
        subsample=0.8, random_state=42)
    pooled_clf.fit(pooled_X, pooled_y)

    # Evaluate both per-patient and pooled on each patient's val set
    results = {}
    summary_rows = []

    for name, data in per_patient_data.items():
        X_tr, X_va = data['X_train'], data['X_val']
        y_tr, y_va = data['y_train'], data['y_val']

        if y_tr.sum() < 10 or y_va.sum() < 5:
            continue

        # Per-patient model
        personal_clf = GradientBoostingClassifier(
            n_estimators=100, max_depth=4, learning_rate=0.1,
            subsample=0.8, random_state=42)
        personal_clf.fit(X_tr, y_tr)

        personal_proba = personal_clf.predict_proba(X_va)[:, 1]
        personal_auc = roc_auc_score(y_va, personal_proba)

        # Pooled model on this patient's val set
        pooled_proba = pooled_clf.predict_proba(X_va)[:, 1]
        pooled_auc = roc_auc_score(y_va, pooled_proba)

        patient_result = {
            'personal_auc': round(personal_auc, 4),
            'pooled_auc': round(pooled_auc, 4),
            'auc_diff': round(personal_auc - pooled_auc, 4),
            'personal_wins': personal_auc > pooled_auc,
        }
        results[name] = patient_result

        summary_rows.append({
            'patient': name,
            'personal': personal_auc,
            'pooled': pooled_auc,
            'diff': personal_auc - pooled_auc,
            'winner': 'Personal' if personal_auc > pooled_auc else 'Pooled',
        })

    print(f"\n{'='*60}")
    print(f"EXP-1109: Personalized vs Population Models")
    print(f"{'='*60}")
    print(f"{'Patient':>8s} {'Personal':>8s} {'Pooled':>8s} {'Diff':>7s} {'Winner':>8s}")
    print('-' * 60)
    for row in summary_rows:
        print(f"{row['patient']:>8s} {row['personal']:8.4f} {row['pooled']:8.4f} "
              f"{row['diff']:+7.4f} {row['winner']:>8s}")

    personal_wins = sum(1 for r in summary_rows if r['winner'] == 'Personal')
    mean_personal = np.mean([r['personal'] for r in summary_rows])
    mean_pooled = np.mean([r['pooled'] for r in summary_rows])
    print(f"\nPersonal wins: {personal_wins}/{len(summary_rows)}")
    print(f"Mean Personal AUC: {mean_personal:.4f} vs Pooled: {mean_pooled:.4f}")

    return {
        'status': 'OK',
        'detail': f'Personal wins {personal_wins}/{len(summary_rows)}, '
                  f'Personal={mean_personal:.4f} vs Pooled={mean_pooled:.4f}',
        'results': results,
        'summary': {
            'personal_wins': personal_wins,
            'total': len(summary_rows),
            'mean_personal_auc': round(mean_personal, 4),
            'mean_pooled_auc': round(mean_pooled, 4),
        },
    }


# ═══════════════════════════════════════════════════════════════════════
# EXP-1110: Campaign Summary & Pipeline Recommendations
# ═══════════════════════════════════════════════════════════════════════

def exp_1110_summary(patients, detail=False, all_results=None):
    """Synthesize findings from EXP-1101–1109 into pipeline recommendations."""
    if all_results is None:
        return {'status': 'SKIP', 'detail': 'Run other experiments first'}

    summary = {
        'periodicity': all_results.get('EXP-1101', {}).get('summary', {}),
        'phase_stability': all_results.get('EXP-1102', {}).get('summary', {}),
        'regularity': all_results.get('EXP-1104', {}).get('summary', {}),
        'xgboost': all_results.get('EXP-1106', {}).get('summary', {}),
        'point_process': all_results.get('EXP-1107', {}),
        'eating_soon': all_results.get('EXP-1108', {}),
        'personal_vs_pooled': all_results.get('EXP-1109', {}).get('summary', {}),
    }

    print(f"\n{'='*70}")
    print(f"EXP-1110: Campaign Summary — Meal Periodicity & Proactive Prediction")
    print(f"{'='*70}")

    # Decision matrix
    print("\n--- DECISION MATRIX ---")

    periodicity = summary.get('periodicity', {})
    if periodicity:
        sig = periodicity.get('significant_24h_count', 0)
        total = periodicity.get('total_patients', 0)
        print(f"24h Periodicity: {sig}/{total} patients significant "
              f"(ACF={periodicity.get('mean_acf_24h', 0):.4f})")

    stability = summary.get('phase_stability', {})
    if stability:
        print(f"Phase Stability: {stability.get('mean_stability_score', 0):.1f}/100")

    regularity = summary.get('regularity', {})
    if regularity:
        print(f"Regularity: {regularity.get('mean_composite', 0):.1f}/100 "
              f"(Regular: {len(regularity.get('regular_patients', []))}, "
              f"Irregular: {len(regularity.get('irregular_patients', []))})")

    xgb = summary.get('xgboost', {})
    if xgb:
        print(f"XGBoost AUC@30min: {xgb.get('mean_auc_30', 0):.4f} "
              f"(lift: {xgb.get('mean_lift_30', 0):.4f})")

    pvp = summary.get('personal_vs_pooled', {})
    if pvp:
        print(f"Personal vs Pooled: Personal wins {pvp.get('personal_wins', 0)}/"
              f"{pvp.get('total', 0)} "
              f"({pvp.get('mean_personal_auc', 0):.4f} vs "
              f"{pvp.get('mean_pooled_auc', 0):.4f})")

    print("\n--- PIPELINE RECOMMENDATION ---")
    xgb_auc = xgb.get('mean_auc_30', 0)
    if xgb_auc >= 0.85:
        print("✅ DEPLOY: XGBoost meal predictor exceeds deployment threshold (AUC ≥ 0.85)")
        recommendation = 'deploy_xgboost'
    elif xgb_auc >= 0.75:
        print("⚠️ PROMISING: XGBoost meal predictor viable with personalization")
        recommendation = 'personalize_and_validate'
    else:
        print("❌ INSUFFICIENT: ML doesn't reliably beat Gaussian baseline yet")
        recommendation = 'continue_research'

    return {
        'status': 'OK',
        'detail': f'Recommendation: {recommendation}',
        'results': summary,
        'recommendation': recommendation,
    }


# ═══════════════════════════════════════════════════════════════════════
# Main dispatcher
# ═══════════════════════════════════════════════════════════════════════

EXPERIMENTS = [
    ('EXP-1101', 'Meal Periodicity Characterization', exp_1101_periodicity),
    ('EXP-1102', 'Phase Stability Over Weeks', exp_1102_phase_stability),
    ('EXP-1103', 'Weekday vs Weekend Meal Patterns', exp_1103_weekday_weekend),
    ('EXP-1104', 'Meal Regularity Score', exp_1104_regularity_score),
    ('EXP-1105', 'Carb Announcement Timing Alignment', exp_1105_announcement_alignment),
    ('EXP-1106', 'XGBoost Meal Timing Predictor', exp_1106_xgboost_predictor),
    ('EXP-1107', 'Temporal Point Process Model', exp_1107_point_process),
    ('EXP-1108', 'Eating-Soon Override Predictor', exp_1108_eating_soon),
    ('EXP-1109', 'Personalized vs Population Models', exp_1109_personal_vs_population),
]


def main():
    parser = argparse.ArgumentParser(
        description='EXP-1101-1110: Meal Periodicity, Phase Stability '
                    '& Proactive Prediction')
    parser.add_argument('--detail', action='store_true',
                        help='Print detailed per-patient results')
    parser.add_argument('--save', action='store_true',
                        help='Save results to externals/experiments/')
    parser.add_argument('--max-patients', type=int, default=11,
                        help='Maximum number of patients to process')
    parser.add_argument('--experiment', type=str, default=None,
                        help='Run only this experiment (e.g. EXP-1101)')
    args = parser.parse_args()

    print("Loading patients...")
    patients = load_patients(PATIENTS_DIR, max_patients=args.max_patients)
    print(f"Loaded {len(patients)} patients\n")

    all_results = {}

    for exp_id, name, func in EXPERIMENTS:
        if args.experiment and exp_id != args.experiment:
            continue

        print(f"\n{'━'*70}")
        print(f"  {exp_id}: {name}")
        print(f"{'━'*70}")
        t0 = time.time()

        try:
            result = func(patients, detail=args.detail)
        except Exception as e:
            import traceback
            traceback.print_exc()
            result = {'status': 'FAIL', 'detail': str(e)}

        elapsed = time.time() - t0
        status = result.get('status', '?')
        detail = result.get('detail', '')
        print(f"\n  → {exp_id} [{status}] {elapsed:.1f}s — {detail}")

        all_results[exp_id] = result

        if args.save and status != 'SKIP':
            save_data = {
                'experiment': exp_id,
                'name': name,
                'status': status,
                'detail': detail,
                'elapsed_seconds': round(elapsed, 1),
                'results': result.get('results', {}),
                'summary': result.get('summary', {}),
            }
            save_name = f"{exp_id.lower().replace('-', '_')}_{name.lower().replace(' ', '_')}"
            save_results(save_data, save_name)

    # Run EXP-1110 summary if we ran all experiments
    if not args.experiment:
        print(f"\n{'━'*70}")
        print(f"  EXP-1110: Campaign Summary")
        print(f"{'━'*70}")
        summary = exp_1110_summary(patients, detail=args.detail,
                                   all_results=all_results)
        print(f"\n  → EXP-1110 [{summary['status']}] — {summary['detail']}")

        if args.save:
            save_data = {
                'experiment': 'EXP-1110',
                'name': 'Campaign Summary',
                'status': summary['status'],
                'detail': summary['detail'],
                'results': summary.get('results', {}),
                'recommendation': summary.get('recommendation', ''),
            }
            save_results(save_data, 'exp_1110_campaign_summary')


if __name__ == '__main__':
    main()
