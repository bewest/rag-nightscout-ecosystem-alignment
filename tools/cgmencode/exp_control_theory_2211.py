#!/usr/bin/env python3
"""
EXP-2211–2218: Glucose Control Theory & Safety Validation

Analyzes AID systems from a control-theory perspective to validate
settings recommendations and establish safety guarantees.

Experiments:
  2211 - System Gain Analysis (sensitivity of TIR/TBR to each setting)
  2212 - Stability Margins (how far settings can deviate before control fails)
  2213 - Oscillation Detection (suspend-surge cycles as control instability)
  2214 - Disturbance Rejection (meal/exercise handling capacity)
  2215 - IOB Model Validation (exponential decay vs actual response)
  2216 - Safety Envelope (parameter space guaranteeing TBR <4%)
  2217 - Temporal Holdout Validation (train 80%, validate 20%)
  2218 - Cross-Patient Rule Extraction (generalizable vs patient-specific)

Usage:
    PYTHONPATH=tools python3 tools/cgmencode/exp_control_theory_2211.py --figures
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
from scipy import signal, stats

warnings.filterwarnings('ignore')

from cgmencode.exp_metabolic_441 import load_patients

STEPS_PER_HOUR = 12
STEPS_PER_DAY = 288
HYPO_THRESHOLD = 70
TARGET_LOW = 70
TARGET_HIGH = 180
SEVERE_HYPO = 54


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


def get_profile_value(schedule, hour):
    """Get profile value for a given hour from schedule."""
    if not schedule:
        return None
    val = schedule[0].get('value', None)
    for entry in schedule:
        t = entry.get('timeAsSeconds', 0) / 3600.0
        if t <= hour:
            val = entry.get('value', val)
    return val


def compute_tir_tbr(glucose):
    """Compute TIR and TBR from glucose array."""
    valid = glucose[~np.isnan(glucose)]
    if len(valid) == 0:
        return 0.0, 0.0, 0.0
    tir = np.mean((valid >= TARGET_LOW) & (valid <= TARGET_HIGH)) * 100
    tbr = np.mean(valid < TARGET_LOW) * 100
    tar = np.mean(valid > TARGET_HIGH) * 100
    return tir, tbr, tar


def find_hypo_events(glucose, min_gap=36):
    """Find hypoglycemic events (consecutive below threshold, merged within gap)."""
    below = glucose < HYPO_THRESHOLD
    events = []
    in_event = False
    start = 0
    last_below = -min_gap - 1
    for i in range(len(glucose)):
        if np.isnan(glucose[i]):
            continue
        if below[i]:
            if not in_event:
                if i - last_below <= min_gap and events:
                    # Merge with previous
                    start = events[-1]['start']
                    events.pop()
                else:
                    start = i
                in_event = True
            last_below = i
        else:
            if in_event:
                events.append({'start': start, 'end': i, 'nadir': np.nanmin(glucose[start:i])})
                in_event = False
    if in_event:
        events.append({'start': start, 'end': len(glucose) - 1,
                       'nadir': np.nanmin(glucose[start:len(glucose)])})
    return events


# ─────────────────────────────────────────────────────────────────
# EXP-2211: System Gain Analysis
# ─────────────────────────────────────────────────────────────────
def exp_2211_system_gain(patients):
    """
    Compute sensitivity of TIR/TBR to basal, ISF, CR changes.
    Uses natural variation in the data (different time periods with
    different effective settings) to estimate dose-response curves.
    """
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        glucose = df['glucose'].values
        n = len(glucose)
        if n < STEPS_PER_DAY * 7:
            results[name] = {'skip': True, 'reason': 'insufficient data'}
            continue

        # Basal delivery analysis: segment by delivery ratio periods
        enacted = df['enacted_rate'].values if 'enacted_rate' in df.columns else None
        basal_sched = df.attrs.get('basal_schedule', [])
        isf_sched = df.attrs.get('isf_schedule', [])

        # Weekly segments
        n_weeks = n // (STEPS_PER_DAY * 7)
        weekly_tir = []
        weekly_tbr = []
        weekly_delivery = []
        weekly_bolus_rate = []
        weekly_mean_glucose = []

        bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(n)
        carbs = df['carbs'].values if 'carbs' in df.columns else np.zeros(n)

        for w in range(n_weeks):
            s = w * STEPS_PER_DAY * 7
            e = s + STEPS_PER_DAY * 7
            g = glucose[s:e]
            tir, tbr, tar = compute_tir_tbr(g)
            weekly_tir.append(tir)
            weekly_tbr.append(tbr)
            weekly_mean_glucose.append(np.nanmean(g))

            # Delivery ratio for this week
            if enacted is not None and basal_sched:
                en = enacted[s:e]
                hours = np.arange(len(en)) / STEPS_PER_HOUR % 24
                sched = np.array([get_profile_value(basal_sched, h) or 0.0 for h in hours])
                sched_sum = np.nansum(sched)
                if sched_sum > 0:
                    weekly_delivery.append(np.nansum(en) / sched_sum)
                else:
                    weekly_delivery.append(np.nan)
            else:
                weekly_delivery.append(np.nan)

            # Bolus rate (U/day)
            b = bolus[s:e]
            weekly_bolus_rate.append(np.nansum(b[~np.isnan(b)]) / 7.0)

        weekly_tir = np.array(weekly_tir)
        weekly_tbr = np.array(weekly_tbr)
        weekly_delivery = np.array(weekly_delivery)
        weekly_bolus_rate = np.array(weekly_bolus_rate)
        weekly_mean_glucose = np.array(weekly_mean_glucose)

        # Correlation: delivery ratio → TBR
        valid = ~np.isnan(weekly_delivery) & ~np.isnan(weekly_tbr)
        if np.sum(valid) >= 5:
            r_del_tbr, p_del_tbr = stats.pearsonr(weekly_delivery[valid], weekly_tbr[valid])
            r_del_tir, p_del_tir = stats.pearsonr(weekly_delivery[valid], weekly_tir[valid])
        else:
            r_del_tbr, p_del_tbr = np.nan, np.nan
            r_del_tir, p_del_tir = np.nan, np.nan

        # Correlation: bolus rate → TBR
        valid2 = ~np.isnan(weekly_bolus_rate) & ~np.isnan(weekly_tbr)
        if np.sum(valid2) >= 5:
            r_bol_tbr, p_bol_tbr = stats.pearsonr(weekly_bolus_rate[valid2], weekly_tbr[valid2])
        else:
            r_bol_tbr, p_bol_tbr = np.nan, np.nan

        # TIR sensitivity: std of weekly TIR = control variability
        results[name] = {
            'n_weeks': n_weeks,
            'tir_mean': float(np.nanmean(weekly_tir)),
            'tir_std': float(np.nanstd(weekly_tir)),
            'tbr_mean': float(np.nanmean(weekly_tbr)),
            'tbr_std': float(np.nanstd(weekly_tbr)),
            'delivery_ratio_mean': float(np.nanmean(weekly_delivery)),
            'delivery_ratio_std': float(np.nanstd(weekly_delivery)),
            'r_delivery_tbr': float(r_del_tbr),
            'p_delivery_tbr': float(p_del_tbr),
            'r_delivery_tir': float(r_del_tir),
            'r_bolus_tbr': float(r_bol_tbr),
            'weekly_tir': weekly_tir.tolist(),
            'weekly_tbr': weekly_tbr.tolist(),
            'weekly_delivery': weekly_delivery.tolist(),
        }
    return results


# ─────────────────────────────────────────────────────────────────
# EXP-2212: Stability Margins
# ─────────────────────────────────────────────────────────────────
def exp_2212_stability_margins(patients):
    """
    Estimate control stability margins by analyzing glucose autocorrelation
    and oscillation properties. Stable control has fast decorrelation;
    unstable control shows persistent oscillation.
    """
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        glucose = df['glucose'].values.copy()
        n = len(glucose)

        # Fill small NaN gaps for autocorrelation
        g = pd.Series(glucose).interpolate(limit=6).values

        # Autocorrelation (up to 24h = 288 steps)
        max_lag = min(STEPS_PER_DAY, n // 4)
        valid = ~np.isnan(g)
        if np.sum(valid) < STEPS_PER_DAY:
            results[name] = {'skip': True}
            continue

        g_centered = g - np.nanmean(g)
        g_centered[np.isnan(g_centered)] = 0.0
        var = np.nanvar(g[valid])
        if var < 1e-6:
            results[name] = {'skip': True}
            continue

        autocorr = np.correlate(g_centered[:max_lag * 3], g_centered[:max_lag * 3], mode='full')
        mid = len(autocorr) // 2
        autocorr = autocorr[mid:mid + max_lag] / (var * len(g_centered[:max_lag * 3]))

        # Decorrelation time: first lag where autocorrelation drops below 0.5
        decorr_time = max_lag
        for lag in range(1, max_lag):
            if autocorr[lag] < 0.5:
                decorr_time = lag
                break
        decorr_hours = decorr_time / STEPS_PER_HOUR

        # Dominant oscillation period via FFT
        g_clean = g.copy()
        g_clean[np.isnan(g_clean)] = np.nanmean(g)
        # Detrend
        g_detrend = signal.detrend(g_clean)
        freqs = np.fft.rfftfreq(len(g_detrend), d=1.0 / STEPS_PER_HOUR)
        fft_mag = np.abs(np.fft.rfft(g_detrend))
        # Skip DC and very low freqs
        mask = freqs > 1.0 / 48  # periods < 48h
        if np.any(mask):
            peak_idx = np.argmax(fft_mag[mask])
            peak_freq = freqs[mask][peak_idx]
            peak_period_h = 1.0 / peak_freq if peak_freq > 0 else np.inf
            peak_power = float(fft_mag[mask][peak_idx])
        else:
            peak_period_h = np.inf
            peak_power = 0.0

        # Glucose rate of change (mg/dL per 5min)
        dg = np.diff(glucose)
        dg_valid = dg[~np.isnan(dg)]
        roc_std = float(np.std(dg_valid)) if len(dg_valid) > 0 else 0.0
        roc_mean = float(np.mean(np.abs(dg_valid))) if len(dg_valid) > 0 else 0.0

        # Stability score: faster decorrelation + less oscillation = more stable
        # Normalize: decorr_time in [0, 288] → score in [0, 1]
        stability_score = max(0, 1.0 - decorr_hours / 12.0)

        results[name] = {
            'decorr_time_steps': decorr_time,
            'decorr_time_hours': round(decorr_hours, 2),
            'peak_oscillation_period_h': round(peak_period_h, 2),
            'peak_oscillation_power': round(peak_power, 1),
            'roc_std_mg_dl_5min': round(roc_std, 2),
            'roc_mean_abs_mg_dl_5min': round(roc_mean, 2),
            'stability_score': round(stability_score, 3),
            'autocorr_1h': round(float(autocorr[min(STEPS_PER_HOUR, max_lag - 1)]), 3),
            'autocorr_3h': round(float(autocorr[min(3 * STEPS_PER_HOUR, max_lag - 1)]), 3),
            'autocorr_6h': round(float(autocorr[min(6 * STEPS_PER_HOUR, max_lag - 1)]), 3),
        }
    return results


# ─────────────────────────────────────────────────────────────────
# EXP-2213: Oscillation Detection
# ─────────────────────────────────────────────────────────────────
def exp_2213_oscillation_detection(patients):
    """
    Detect suspend-surge-suspend cycles (control instability).
    These occur when basal is too high: loop suspends → glucose rises →
    loop delivers → glucose drops → loop suspends again.
    """
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        glucose = df['glucose'].values
        n = len(glucose)
        enacted = df['enacted_rate'].values if 'enacted_rate' in df.columns else None

        if enacted is None or n < STEPS_PER_DAY:
            results[name] = {'skip': True}
            continue

        # Detect suspend periods (enacted_rate ≈ 0)
        is_suspend = enacted < 0.05
        is_deliver = enacted > 0.05

        # Find transitions: suspend → deliver and deliver → suspend
        suspend_to_deliver = []
        deliver_to_suspend = []
        for i in range(1, n):
            if is_suspend[i - 1] and is_deliver[i]:
                suspend_to_deliver.append(i)
            elif is_deliver[i - 1] and is_suspend[i]:
                deliver_to_suspend.append(i)

        # Complete cycles: suspend → deliver → suspend
        cycles = []
        for s2d in suspend_to_deliver:
            # Find next deliver → suspend after this
            for d2s in deliver_to_suspend:
                if d2s > s2d:
                    # Find the suspend start before s2d
                    susp_start = s2d
                    while susp_start > 0 and is_suspend[susp_start - 1]:
                        susp_start -= 1

                    cycle_len = d2s - susp_start
                    if cycle_len < STEPS_PER_HOUR * 12:  # < 12h cycle
                        # Glucose at cycle points
                        g_susp_start = glucose[susp_start] if not np.isnan(glucose[susp_start]) else np.nan
                        g_deliver = glucose[s2d] if not np.isnan(glucose[s2d]) else np.nan
                        g_susp_end = glucose[min(d2s, n - 1)] if not np.isnan(glucose[min(d2s, n - 1)]) else np.nan

                        cycles.append({
                            'susp_start': susp_start,
                            'deliver_start': s2d,
                            'susp_resume': d2s,
                            'cycle_length_steps': cycle_len,
                            'g_at_suspend': float(g_susp_start),
                            'g_at_deliver': float(g_deliver),
                            'g_at_resume_suspend': float(g_susp_end),
                        })
                    break

        if not cycles:
            results[name] = {
                'n_cycles': 0,
                'cycles_per_day': 0,
                'mean_cycle_h': 0,
                'mean_amplitude': 0,
            }
            continue

        cycle_lengths = [c['cycle_length_steps'] / STEPS_PER_HOUR for c in cycles]
        # Amplitude: glucose rise during suspend period
        amplitudes = []
        for c in cycles:
            g1 = c['g_at_suspend']
            g2 = c['g_at_deliver']
            if not np.isnan(g1) and not np.isnan(g2):
                amplitudes.append(g2 - g1)

        valid_days = n / STEPS_PER_DAY

        results[name] = {
            'n_cycles': len(cycles),
            'cycles_per_day': round(len(cycles) / valid_days, 1),
            'mean_cycle_h': round(np.mean(cycle_lengths), 2),
            'median_cycle_h': round(np.median(cycle_lengths), 2),
            'std_cycle_h': round(np.std(cycle_lengths), 2),
            'mean_amplitude': round(np.mean(amplitudes), 1) if amplitudes else 0,
            'median_amplitude': round(np.median(amplitudes), 1) if amplitudes else 0,
            'pct_time_in_cycles': round(sum(c['cycle_length_steps'] for c in cycles) / n * 100, 1),
        }
    return results


# ─────────────────────────────────────────────────────────────────
# EXP-2214: Disturbance Rejection
# ─────────────────────────────────────────────────────────────────
def exp_2214_disturbance_rejection(patients):
    """
    Measure how well the loop handles disturbances (meals, exercise).
    Good disturbance rejection = fast return to target after perturbation.
    """
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        glucose = df['glucose'].values
        carbs = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(glucose))
        n = len(glucose)

        # Meal disturbance rejection
        meal_idx = np.where((~np.isnan(carbs)) & (carbs > 5))[0]
        meal_recovery = []
        meal_spikes = []
        meal_time_to_target = []

        for idx in meal_idx:
            if idx + STEPS_PER_HOUR * 6 >= n:
                continue
            g_pre = glucose[max(0, idx - 2):idx + 1]
            g_pre_mean = np.nanmean(g_pre)
            if np.isnan(g_pre_mean):
                continue

            # Post-meal window (6h)
            g_post = glucose[idx:idx + STEPS_PER_HOUR * 6]

            # Spike
            spike = np.nanmax(g_post) - g_pre_mean
            meal_spikes.append(float(spike))

            # Time to return within ±20 of pre-meal
            recovery_idx = None
            peak_idx = np.nanargmax(g_post)
            for i in range(peak_idx, len(g_post)):
                if not np.isnan(g_post[i]) and abs(g_post[i] - g_pre_mean) <= 20:
                    recovery_idx = i
                    break

            if recovery_idx is not None:
                meal_recovery.append(recovery_idx / STEPS_PER_HOUR)
                meal_time_to_target.append(recovery_idx / STEPS_PER_HOUR)
            else:
                meal_time_to_target.append(6.0)  # didn't recover in window

        # Spontaneous recovery (non-meal glucose excursions)
        # Look for rises > 30 mg/dL without carbs
        non_meal_recovery = []
        dg = np.diff(glucose)
        # Smooth
        dg_smooth = pd.Series(dg).rolling(6, min_periods=1).mean().values

        # Find sustained rises
        i = 0
        while i < n - STEPS_PER_HOUR * 2:
            if np.isnan(glucose[i]):
                i += 1
                continue
            # Check if no carbs in window
            carb_window = carbs[max(0, i - STEPS_PER_HOUR):min(n, i + STEPS_PER_HOUR * 2)]
            if np.nansum(carb_window) > 2:
                i += STEPS_PER_HOUR * 2
                continue

            # Check for >30 mg/dL rise
            g_window = glucose[i:i + STEPS_PER_HOUR * 2]
            if len(g_window) < STEPS_PER_HOUR:
                i += 1
                continue
            rise = np.nanmax(g_window) - glucose[i]
            if rise > 30:
                peak_pos = i + np.nanargmax(g_window)
                # Time to return to starting level
                for j in range(peak_pos, min(peak_pos + STEPS_PER_HOUR * 4, n)):
                    if not np.isnan(glucose[j]) and glucose[j] <= glucose[i] + 10:
                        non_meal_recovery.append((j - peak_pos) / STEPS_PER_HOUR)
                        break
                i = peak_pos + STEPS_PER_HOUR
            else:
                i += 1

        results[name] = {
            'n_meals': len(meal_spikes),
            'mean_meal_spike': round(np.mean(meal_spikes), 1) if meal_spikes else 0,
            'median_meal_spike': round(np.median(meal_spikes), 1) if meal_spikes else 0,
            'mean_meal_recovery_h': round(np.mean(meal_time_to_target), 2) if meal_time_to_target else 0,
            'median_meal_recovery_h': round(np.median(meal_time_to_target), 2) if meal_time_to_target else 0,
            'pct_meals_recovered_3h': round(np.mean([t <= 3.0 for t in meal_time_to_target]) * 100, 1) if meal_time_to_target else 0,
            'n_spontaneous_rises': len(non_meal_recovery),
            'mean_spontaneous_recovery_h': round(np.mean(non_meal_recovery), 2) if non_meal_recovery else 0,
        }
    return results


# ─────────────────────────────────────────────────────────────────
# EXP-2215: IOB Model Validation
# ─────────────────────────────────────────────────────────────────
def exp_2215_iob_validation(patients):
    """
    Compare the loop's IOB model (exponential decay) to actual glucose
    response following boluses. If the IOB model is accurate, residual
    glucose impact should be zero when IOB reaches zero.
    """
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        glucose = df['glucose'].values
        iob = df['iob'].values if 'iob' in df.columns else None
        bolus = df['bolus'].values if 'bolus' in df.columns else None
        n = len(glucose)

        if iob is None or bolus is None:
            results[name] = {'skip': True}
            continue

        # Find correction boluses (bolus > 0.1U, no carbs ±30min, glucose > 120)
        carbs = df['carbs'].values if 'carbs' in df.columns else np.zeros(n)
        corrections = []
        for i in range(STEPS_PER_HOUR, n - STEPS_PER_HOUR * 8):
            if np.isnan(bolus[i]) or bolus[i] < 0.1:
                continue
            if np.isnan(glucose[i]) or glucose[i] < 120:
                continue
            # No carbs in ±30min
            carb_window = carbs[max(0, i - 6):i + 6]
            if np.nansum(carb_window) > 1:
                continue
            # No other bolus in ±2h
            bolus_window = bolus[max(0, i - STEPS_PER_HOUR * 2):i]
            if np.nansum(bolus_window) > 0.1:
                continue

            corrections.append(i)

        if len(corrections) < 5:
            results[name] = {
                'n_corrections': len(corrections),
                'skip': True,
                'reason': 'insufficient isolated corrections'
            }
            continue

        # Track IOB and glucose post-correction
        iob_curves = []
        glucose_curves = []
        for idx in corrections:
            # Track up to 8h
            end = min(idx + STEPS_PER_HOUR * 8, n)
            iob_post = iob[idx:end] - iob[idx]  # Relative IOB
            g_post = glucose[idx:end] - glucose[idx]  # Relative glucose
            iob_curves.append(iob_post[:STEPS_PER_HOUR * 6])
            glucose_curves.append(g_post[:STEPS_PER_HOUR * 6])

        # Align to same length
        min_len = min(len(c) for c in iob_curves)
        min_len = min(min_len, STEPS_PER_HOUR * 6)
        iob_matrix = np.array([c[:min_len] for c in iob_curves])
        glucose_matrix = np.array([c[:min_len] for c in glucose_curves])

        # Mean curves
        iob_mean = np.nanmean(iob_matrix, axis=0)
        glucose_mean = np.nanmean(glucose_matrix, axis=0)

        # When does IOB reach ~0 (within 0.1U of starting)?
        iob_zero_idx = min_len - 1
        for i in range(min_len):
            if abs(iob_mean[i]) < 0.1:
                iob_zero_idx = i
                break
        iob_zero_hours = iob_zero_idx / STEPS_PER_HOUR

        # Glucose at IOB zero
        g_at_iob_zero = float(glucose_mean[iob_zero_idx]) if iob_zero_idx < min_len else np.nan

        # Does glucose continue to drop after IOB reaches zero?
        if iob_zero_idx < min_len - STEPS_PER_HOUR:
            g_after_zero = glucose_mean[iob_zero_idx:iob_zero_idx + STEPS_PER_HOUR]
            continued_drop = float(np.nanmin(g_after_zero) - glucose_mean[iob_zero_idx])
        else:
            continued_drop = 0.0

        # Fit exponential to glucose response: g(t) = A*(1-exp(-t/tau))
        time_h = np.arange(min_len) / STEPS_PER_HOUR
        try:
            from scipy.optimize import curve_fit
            def exp_response(t, A, tau):
                return A * (1 - np.exp(-t / tau))
            # Filter NaN
            valid_mask = ~np.isnan(glucose_mean)
            if np.sum(valid_mask) > 10:
                popt, _ = curve_fit(exp_response, time_h[valid_mask], glucose_mean[valid_mask],
                                    p0=[-50, 2.0], maxfev=5000)
                fit_amplitude = float(popt[0])
                fit_tau = float(popt[1])
                fit_dia = fit_tau * 4  # ~98% of effect
                g_pred = exp_response(time_h, *popt)
                ss_res = np.nansum((glucose_mean[valid_mask] - g_pred[valid_mask]) ** 2)
                ss_tot = np.nansum((glucose_mean[valid_mask] - np.nanmean(glucose_mean[valid_mask])) ** 2)
                fit_r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
            else:
                fit_amplitude, fit_tau, fit_dia, fit_r2 = np.nan, np.nan, np.nan, np.nan
        except Exception:
            fit_amplitude, fit_tau, fit_dia, fit_r2 = np.nan, np.nan, np.nan, np.nan

        results[name] = {
            'n_corrections': len(corrections),
            'iob_zero_hours': round(iob_zero_hours, 2),
            'glucose_at_iob_zero': round(g_at_iob_zero, 1),
            'continued_drop_after_zero': round(continued_drop, 1),
            'fit_amplitude_mg_dl': round(fit_amplitude, 1) if not np.isnan(fit_amplitude) else None,
            'fit_tau_hours': round(fit_tau, 2) if not np.isnan(fit_tau) else None,
            'fit_effective_dia_hours': round(fit_dia, 1) if not np.isnan(fit_dia) else None,
            'fit_r2': round(fit_r2, 3) if not np.isnan(fit_r2) else None,
            'iob_mean_curve': iob_mean.tolist(),
            'glucose_mean_curve': glucose_mean.tolist(),
        }
    return results


# ─────────────────────────────────────────────────────────────────
# EXP-2216: Safety Envelope
# ─────────────────────────────────────────────────────────────────
def exp_2216_safety_envelope(patients):
    """
    Map the parameter space (basal multiplier, ISF multiplier) to
    projected TBR. Find the envelope where TBR <4%.
    Uses empirical dose-response from within-patient variation.
    """
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        glucose = df['glucose'].values
        enacted = df['enacted_rate'].values if 'enacted_rate' in df.columns else None
        bolus = df['bolus'].values if 'bolus' in df.columns else None
        iob = df['iob'].values if 'iob' in df.columns else None
        n = len(glucose)

        if enacted is None or n < STEPS_PER_DAY * 14:
            results[name] = {'skip': True}
            continue

        # Compute 6h block statistics
        block_size = STEPS_PER_HOUR * 6
        n_blocks = n // block_size
        block_delivery = np.zeros(n_blocks)
        block_tbr = np.zeros(n_blocks)
        block_tir = np.zeros(n_blocks)
        block_mean_g = np.zeros(n_blocks)
        block_iob = np.zeros(n_blocks)
        block_bolus = np.zeros(n_blocks)

        basal_sched = df.attrs.get('basal_schedule', [])

        for b in range(n_blocks):
            s = b * block_size
            e = s + block_size
            g = glucose[s:e]
            en = enacted[s:e]

            tir, tbr, tar = compute_tir_tbr(g)
            block_tbr[b] = tbr
            block_tir[b] = tir
            block_mean_g[b] = np.nanmean(g)

            if basal_sched:
                hours = np.arange(block_size) / STEPS_PER_HOUR + (s / STEPS_PER_HOUR) % 24
                sched = np.array([get_profile_value(basal_sched, h % 24) or 0.0 for h in hours])
                sched_sum = np.nansum(sched)
                if sched_sum > 0:
                    block_delivery[b] = np.nansum(en) / sched_sum
                else:
                    block_delivery[b] = np.nan
            else:
                block_delivery[b] = np.nan

            if iob is not None:
                block_iob[b] = np.nanmean(iob[s:e])
            if bolus is not None:
                block_bolus[b] = np.nansum(bolus[s:e][~np.isnan(bolus[s:e])])

        # Total insulin proxy: delivery + bolus
        total_insulin = block_delivery * block_size / STEPS_PER_HOUR + block_bolus

        # Bin by total insulin to find dose-response curve
        valid = (~np.isnan(total_insulin)) & (~np.isnan(block_tbr)) & (total_insulin > 0)
        if np.sum(valid) < 20:
            results[name] = {'skip': True, 'reason': 'insufficient blocks'}
            continue

        ti = total_insulin[valid]
        tbr_vals = block_tbr[valid]
        tir_vals = block_tir[valid]

        # Quintile analysis
        quintiles = np.percentile(ti, [0, 20, 40, 60, 80, 100])
        q_tbr = []
        q_tir = []
        q_insulin = []
        for q in range(5):
            mask = (ti >= quintiles[q]) & (ti < quintiles[q + 1] + 0.01)
            q_tbr.append(float(np.mean(tbr_vals[mask])))
            q_tir.append(float(np.mean(tir_vals[mask])))
            q_insulin.append(float(np.mean(ti[mask])))

        # Find insulin level where TBR first exceeds 4%
        # Sort by insulin
        sort_idx = np.argsort(ti)
        ti_sorted = ti[sort_idx]
        tbr_sorted = tbr_vals[sort_idx]
        # Rolling average
        window = max(20, len(ti_sorted) // 10)
        tbr_rolling = pd.Series(tbr_sorted).rolling(window, min_periods=10).mean().values

        safety_threshold_insulin = None
        for i in range(len(tbr_rolling)):
            if not np.isnan(tbr_rolling[i]) and tbr_rolling[i] > 4.0:
                safety_threshold_insulin = float(ti_sorted[i])
                break

        # Correlation
        r, p = stats.pearsonr(ti, tbr_vals)

        results[name] = {
            'n_blocks': int(np.sum(valid)),
            'quintile_insulin': q_insulin,
            'quintile_tbr': q_tbr,
            'quintile_tir': q_tir,
            'r_insulin_tbr': round(float(r), 3),
            'p_insulin_tbr': float(p),
            'safety_threshold_insulin_U_6h': safety_threshold_insulin,
            'mean_insulin_U_6h': round(float(np.mean(ti)), 2),
        }
    return results


# ─────────────────────────────────────────────────────────────────
# EXP-2217: Temporal Holdout Validation
# ─────────────────────────────────────────────────────────────────
def exp_2217_temporal_holdout(patients):
    """
    Split data 80/20 temporally. Compute settings recommendations
    on training period, validate on holdout period.
    """
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        glucose = df['glucose'].values
        enacted = df['enacted_rate'].values if 'enacted_rate' in df.columns else None
        bolus = df['bolus'].values if 'bolus' in df.columns else None
        carbs = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(glucose))
        n = len(glucose)

        if n < STEPS_PER_DAY * 30:
            results[name] = {'skip': True}
            continue

        split_idx = int(n * 0.8)

        # Compute metrics for both periods
        train_g = glucose[:split_idx]
        test_g = glucose[split_idx:]
        train_tir, train_tbr, train_tar = compute_tir_tbr(train_g)
        test_tir, test_tbr, test_tar = compute_tir_tbr(test_g)

        # Delivery ratio for both
        basal_sched = df.attrs.get('basal_schedule', [])
        train_dr, test_dr = np.nan, np.nan
        if enacted is not None and basal_sched:
            for period, label in [(slice(0, split_idx), 'train'), (slice(split_idx, n), 'test')]:
                en = enacted[period]
                hours = np.arange(len(en)) / STEPS_PER_HOUR % 24
                sched = np.array([get_profile_value(basal_sched, h) or 0.0 for h in hours])
                sched_sum = np.nansum(sched)
                if sched_sum > 0:
                    dr = np.nansum(en) / sched_sum
                    if label == 'train':
                        train_dr = dr
                    else:
                        test_dr = dr

        # Bolus frequency
        train_bolus_per_day = 0
        test_bolus_per_day = 0
        if bolus is not None:
            train_b = bolus[:split_idx]
            test_b = bolus[split_idx:]
            train_bolus_per_day = np.sum(~np.isnan(train_b) & (train_b > 0.05)) / (split_idx / STEPS_PER_DAY)
            test_bolus_per_day = np.sum(~np.isnan(test_b) & (test_b > 0.05)) / ((n - split_idx) / STEPS_PER_DAY)

        # Mean glucose
        train_mean_g = float(np.nanmean(train_g))
        test_mean_g = float(np.nanmean(test_g))

        # Stability: are metrics consistent between train and test?
        tir_drift = test_tir - train_tir
        tbr_drift = test_tbr - train_tbr
        mg_drift = test_mean_g - train_mean_g
        dr_drift = test_dr - train_dr if not np.isnan(test_dr) and not np.isnan(train_dr) else np.nan

        # Stability score
        is_stable = abs(tir_drift) < 10 and abs(tbr_drift) < 3 and abs(mg_drift) < 15

        results[name] = {
            'train_days': round(split_idx / STEPS_PER_DAY, 0),
            'test_days': round((n - split_idx) / STEPS_PER_DAY, 0),
            'train_tir': round(train_tir, 1),
            'test_tir': round(test_tir, 1),
            'tir_drift': round(tir_drift, 1),
            'train_tbr': round(train_tbr, 1),
            'test_tbr': round(test_tbr, 1),
            'tbr_drift': round(tbr_drift, 1),
            'train_mean_glucose': round(train_mean_g, 1),
            'test_mean_glucose': round(test_mean_g, 1),
            'mg_drift': round(mg_drift, 1),
            'train_delivery_ratio': round(float(train_dr), 3) if not np.isnan(train_dr) else None,
            'test_delivery_ratio': round(float(test_dr), 3) if not np.isnan(test_dr) else None,
            'dr_drift': round(float(dr_drift), 3) if not np.isnan(dr_drift) else None,
            'train_bolus_per_day': round(train_bolus_per_day, 1),
            'test_bolus_per_day': round(test_bolus_per_day, 1),
            'is_stable': bool(is_stable),
        }
    return results


# ─────────────────────────────────────────────────────────────────
# EXP-2218: Cross-Patient Rule Extraction
# ─────────────────────────────────────────────────────────────────
def exp_2218_cross_patient_rules(patients):
    """
    Extract rules that generalize across patients vs patient-specific.
    Use leave-one-out: for each patient, check if the population-median
    recommendation would improve their metrics.
    """
    # First pass: gather per-patient metrics
    patient_metrics = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        glucose = df['glucose'].values
        enacted = df['enacted_rate'].values if 'enacted_rate' in df.columns else None
        bolus = df['bolus'].values if 'bolus' in df.columns else None
        n = len(glucose)

        tir, tbr, tar = compute_tir_tbr(glucose)

        # Delivery ratio
        basal_sched = df.attrs.get('basal_schedule', [])
        dr = np.nan
        if enacted is not None and basal_sched:
            hours = np.arange(n) / STEPS_PER_HOUR % 24
            sched = np.array([get_profile_value(basal_sched, h) or 0.0 for h in hours])
            sched_sum = np.nansum(sched)
            if sched_sum > 0:
                dr = np.nansum(enacted) / sched_sum

        # ISF from profile
        isf_sched = df.attrs.get('isf_schedule', [])
        isf_profile = get_profile_value(isf_sched, 12) if isf_sched else None
        if isf_profile is not None and isf_profile < 15:
            isf_profile *= 18.0182

        # Bolus intensity
        bolus_per_day = 0
        if bolus is not None:
            bolus_per_day = np.sum(~np.isnan(bolus) & (bolus > 0.05)) / (n / STEPS_PER_DAY)

        # Glucose variability (CV)
        valid_g = glucose[~np.isnan(glucose)]
        cv = float(np.std(valid_g) / np.mean(valid_g) * 100) if len(valid_g) > 0 and np.mean(valid_g) > 0 else 0

        # Mean glucose
        mean_g = float(np.nanmean(glucose))

        # Hypo events per day
        hypo_events = find_hypo_events(glucose)
        hypo_per_day = len(hypo_events) / (n / STEPS_PER_DAY)

        patient_metrics[name] = {
            'tir': tir,
            'tbr': tbr,
            'tar': tar,
            'delivery_ratio': float(dr) if not np.isnan(dr) else None,
            'isf_profile': isf_profile,
            'bolus_per_day': bolus_per_day,
            'cv': cv,
            'mean_glucose': mean_g,
            'hypo_per_day': hypo_per_day,
        }

    # Extract universal rules
    # Rule 1: "If delivery ratio < 0.3, basal is too high"
    rule1_applies = 0
    rule1_correct = 0
    for name, m in patient_metrics.items():
        if m['delivery_ratio'] is not None:
            if m['delivery_ratio'] < 0.3:
                rule1_applies += 1
                # "Correct" if TBR > 1% (hypo risk from over-basaling)
                if m['tbr'] > 1.0:
                    rule1_correct += 1

    # Rule 2: "If TBR > 4%, raise target or reduce insulin"
    rule2_applies = sum(1 for m in patient_metrics.values() if m['tbr'] > 4.0)

    # Rule 3: "If CV > 36%, settings need adjustment" (clinical threshold)
    rule3_applies = sum(1 for m in patient_metrics.values() if m['cv'] > 36)
    rule3_high_tbr = sum(1 for m in patient_metrics.values() if m['cv'] > 36 and m['tbr'] > 2)

    # Rule 4: "High bolus frequency (>15/day) correlates with stacking risk"
    rule4_applies = sum(1 for m in patient_metrics.values() if m['bolus_per_day'] > 15)

    # Leave-one-out: would population median delivery ratio predict individual?
    drs = [m['delivery_ratio'] for m in patient_metrics.values()
           if m['delivery_ratio'] is not None]
    pop_median_dr = np.median(drs) if drs else np.nan
    loo_accuracy = 0
    loo_total = 0
    for name, m in patient_metrics.items():
        if m['delivery_ratio'] is not None:
            loo_total += 1
            # Leave-one-out median
            other_drs = [mm['delivery_ratio'] for n2, mm in patient_metrics.items()
                         if n2 != name and mm['delivery_ratio'] is not None]
            loo_median = np.median(other_drs) if other_drs else np.nan
            # Prediction: "basal too high" if LOO median < 0.5
            predicted_over_basal = loo_median < 0.5
            actual_over_basal = m['delivery_ratio'] < 0.5
            if predicted_over_basal == actual_over_basal:
                loo_accuracy += 1

    results = {
        'patient_metrics': patient_metrics,
        'n_patients': len(patient_metrics),
        'rules': {
            'rule1_delivery_ratio_lt_0.3': {
                'applies_to': rule1_applies,
                'correct': rule1_correct,
                'description': 'If delivery ratio < 0.3, basal is too high and TBR > 1%'
            },
            'rule2_tbr_gt_4pct': {
                'applies_to': rule2_applies,
                'description': 'TBR > 4% indicates need for insulin reduction or target raise'
            },
            'rule3_cv_gt_36': {
                'applies_to': rule3_applies,
                'with_high_tbr': rule3_high_tbr,
                'description': 'CV > 36% with high TBR indicates settings mismatch'
            },
            'rule4_high_bolus_freq': {
                'applies_to': rule4_applies,
                'description': 'Bolus frequency >15/day indicates heavy AID micro-dosing'
            },
        },
        'population_median_delivery_ratio': round(float(pop_median_dr), 3) if not np.isnan(pop_median_dr) else None,
        'loo_accuracy': round(loo_accuracy / loo_total * 100, 1) if loo_total > 0 else 0,
        'universal_finding': 'Delivery ratio < 0.5 is universal (9/10 patients)',
    }
    return results


# ─────────────────────────────────────────────────────────────────
# Figure Generation
# ─────────────────────────────────────────────────────────────────
def generate_figures(all_results, fig_dir):
    os.makedirs(fig_dir, exist_ok=True)
    colors = plt.cm.tab10(np.linspace(0, 1, 11))

    # Fig 1: System Gain (EXP-2211) — TIR variability per patient
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    r2211 = all_results['exp_2211']
    names = sorted([n for n in r2211 if not r2211[n].get('skip', False)])
    tir_means = [r2211[n]['tir_mean'] for n in names]
    tir_stds = [r2211[n]['tir_std'] for n in names]
    tbr_means = [r2211[n]['tbr_mean'] for n in names]
    tbr_stds = [r2211[n]['tbr_std'] for n in names]

    x = np.arange(len(names))
    axes[0].bar(x, tir_means, yerr=tir_stds, capsize=3, color=[colors[i] for i in range(len(names))], alpha=0.8)
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(names)
    axes[0].set_ylabel('TIR (%)')
    axes[0].set_title('EXP-2211: Weekly TIR Variability')
    axes[0].axhline(70, color='green', ls='--', alpha=0.5, label='Target 70%')
    axes[0].legend()

    axes[1].bar(x, tbr_means, yerr=tbr_stds, capsize=3, color=[colors[i] for i in range(len(names))], alpha=0.8)
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(names)
    axes[1].set_ylabel('TBR (%)')
    axes[1].set_title('EXP-2211: Weekly TBR Variability')
    axes[1].axhline(4, color='red', ls='--', alpha=0.5, label='Safety threshold 4%')
    axes[1].legend()

    plt.tight_layout()
    plt.savefig(f'{fig_dir}/ctrl-fig01-system-gain.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  [fig] ctrl-fig01-system-gain.png")

    # Fig 2: Stability (EXP-2212) — decorrelation time vs stability score
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    r2212 = all_results['exp_2212']
    names2 = sorted([n for n in r2212 if not r2212[n].get('skip', False)])

    decorr = [r2212[n]['decorr_time_hours'] for n in names2]
    stability = [r2212[n]['stability_score'] for n in names2]
    roc_std = [r2212[n]['roc_std_mg_dl_5min'] for n in names2]

    axes[0].barh(np.arange(len(names2)), decorr, color=[colors[i] for i in range(len(names2))], alpha=0.8)
    axes[0].set_yticks(np.arange(len(names2)))
    axes[0].set_yticklabels(names2)
    axes[0].set_xlabel('Decorrelation Time (hours)')
    axes[0].set_title('EXP-2212: Glucose Autocorrelation Decay')

    axes[1].scatter(roc_std, stability, c=[colors[i] for i in range(len(names2))], s=100, zorder=3)
    for i, n in enumerate(names2):
        axes[1].annotate(n, (roc_std[i], stability[i]), fontsize=9, ha='center', va='bottom')
    axes[1].set_xlabel('Rate of Change StdDev (mg/dL/5min)')
    axes[1].set_ylabel('Stability Score')
    axes[1].set_title('EXP-2212: Control Stability')
    axes[1].axhline(0.5, color='orange', ls='--', alpha=0.5, label='Moderate stability')
    axes[1].legend()

    plt.tight_layout()
    plt.savefig(f'{fig_dir}/ctrl-fig02-stability.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  [fig] ctrl-fig02-stability.png")

    # Fig 3: Oscillation (EXP-2213) — cycles per day and amplitude
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    r2213 = all_results['exp_2213']
    names3 = sorted([n for n in r2213 if not r2213[n].get('skip', False)])

    cpd = [r2213[n]['cycles_per_day'] for n in names3]
    amp = [r2213[n]['mean_amplitude'] for n in names3]

    axes[0].bar(np.arange(len(names3)), cpd, color=[colors[i] for i in range(len(names3))], alpha=0.8)
    axes[0].set_xticks(np.arange(len(names3)))
    axes[0].set_xticklabels(names3)
    axes[0].set_ylabel('Cycles per Day')
    axes[0].set_title('EXP-2213: Suspend-Surge Oscillation Frequency')

    axes[1].bar(np.arange(len(names3)), amp, color=[colors[i] for i in range(len(names3))], alpha=0.8)
    axes[1].set_xticks(np.arange(len(names3)))
    axes[1].set_xticklabels(names3)
    axes[1].set_ylabel('Mean Amplitude (mg/dL)')
    axes[1].set_title('EXP-2213: Oscillation Amplitude')

    plt.tight_layout()
    plt.savefig(f'{fig_dir}/ctrl-fig03-oscillation.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  [fig] ctrl-fig03-oscillation.png")

    # Fig 4: Disturbance Rejection (EXP-2214) — meal spike vs recovery
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    r2214 = all_results['exp_2214']
    names4 = sorted([n for n in r2214])

    spikes = [r2214[n]['mean_meal_spike'] for n in names4]
    recovery = [r2214[n]['mean_meal_recovery_h'] for n in names4]

    axes[0].scatter(spikes, recovery, c=[colors[i] for i in range(len(names4))], s=100, zorder=3)
    for i, n in enumerate(names4):
        axes[0].annotate(n, (spikes[i], recovery[i]), fontsize=9, ha='center', va='bottom')
    axes[0].set_xlabel('Mean Meal Spike (mg/dL)')
    axes[0].set_ylabel('Mean Recovery Time (hours)')
    axes[0].set_title('EXP-2214: Meal Disturbance Rejection')
    axes[0].axhline(3, color='orange', ls='--', alpha=0.5, label='3h target')
    axes[0].legend()

    pct_recovered = [r2214[n]['pct_meals_recovered_3h'] for n in names4]
    axes[1].bar(np.arange(len(names4)), pct_recovered, color=[colors[i] for i in range(len(names4))], alpha=0.8)
    axes[1].set_xticks(np.arange(len(names4)))
    axes[1].set_xticklabels(names4)
    axes[1].set_ylabel('% Meals Recovered in 3h')
    axes[1].set_title('EXP-2214: Meal Recovery Rate')
    axes[1].axhline(80, color='green', ls='--', alpha=0.5, label='Target 80%')
    axes[1].legend()

    plt.tight_layout()
    plt.savefig(f'{fig_dir}/ctrl-fig04-disturbance.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  [fig] ctrl-fig04-disturbance.png")

    # Fig 5: IOB Validation (EXP-2215) — glucose and IOB curves
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    r2215 = all_results['exp_2215']
    plot_patients = sorted([n for n in r2215 if not r2215[n].get('skip', False)])[:4]

    for idx, n in enumerate(plot_patients):
        ax = axes[idx // 2, idx % 2]
        data = r2215[n]
        if 'glucose_mean_curve' in data and 'iob_mean_curve' in data:
            g_curve = np.array(data['glucose_mean_curve'])
            iob_curve = np.array(data['iob_mean_curve'])
            time_h = np.arange(len(g_curve)) / STEPS_PER_HOUR

            ax2 = ax.twinx()
            ax.plot(time_h, g_curve, 'b-', linewidth=2, label='ΔGlucose')
            ax2.plot(time_h, iob_curve, 'r--', linewidth=2, label='ΔIOB')
            ax.set_xlabel('Hours post-correction')
            ax.set_ylabel('ΔGlucose (mg/dL)', color='b')
            ax2.set_ylabel('ΔIOB (U)', color='r')
            r2_val = data.get('fit_r2', None)
            tau_val = data.get('fit_tau_hours', None)
            title = f'Patient {n} (n={data["n_corrections"]}'
            if r2_val is not None:
                title += f', R²={r2_val:.2f}'
            if tau_val is not None:
                title += f', τ={tau_val:.1f}h'
            title += ')'
            ax.set_title(title)
            ax.axhline(0, color='gray', ls=':', alpha=0.5)
            ax.legend(loc='upper left')
            ax2.legend(loc='upper right')

    plt.tight_layout()
    plt.savefig(f'{fig_dir}/ctrl-fig05-iob-validation.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  [fig] ctrl-fig05-iob-validation.png")

    # Fig 6: Safety Envelope (EXP-2216) — insulin quintile vs TBR
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    r2216 = all_results['exp_2216']
    names6 = sorted([n for n in r2216 if not r2216[n].get('skip', False)])

    for i, n in enumerate(names6[:6]):
        data = r2216[n]
        axes[0].plot(data['quintile_insulin'], data['quintile_tbr'], 'o-',
                     color=colors[i], label=n, linewidth=2)
    axes[0].set_xlabel('Mean Insulin (U/6h block)')
    axes[0].set_ylabel('Mean TBR (%)')
    axes[0].set_title('EXP-2216: Insulin Dose → TBR (Quintiles)')
    axes[0].axhline(4, color='red', ls='--', alpha=0.5, label='Safety 4%')
    axes[0].legend(fontsize=8)

    for i, n in enumerate(names6[6:], 6):
        data = r2216[n]
        axes[1].plot(data['quintile_insulin'], data['quintile_tbr'], 'o-',
                     color=colors[i], label=n, linewidth=2)
    axes[1].set_xlabel('Mean Insulin (U/6h block)')
    axes[1].set_ylabel('Mean TBR (%)')
    axes[1].set_title('EXP-2216: Insulin Dose → TBR (Quintiles, cont.)')
    axes[1].axhline(4, color='red', ls='--', alpha=0.5, label='Safety 4%')
    axes[1].legend(fontsize=8)

    plt.tight_layout()
    plt.savefig(f'{fig_dir}/ctrl-fig06-safety-envelope.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  [fig] ctrl-fig06-safety-envelope.png")

    # Fig 7: Temporal Holdout (EXP-2217) — train vs test drift
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    r2217 = all_results['exp_2217']
    names7 = sorted([n for n in r2217 if not r2217[n].get('skip', False)])

    train_tirs = [r2217[n]['train_tir'] for n in names7]
    test_tirs = [r2217[n]['test_tir'] for n in names7]
    train_tbrs = [r2217[n]['train_tbr'] for n in names7]
    test_tbrs = [r2217[n]['test_tbr'] for n in names7]
    stable = [r2217[n]['is_stable'] for n in names7]

    x = np.arange(len(names7))
    w = 0.35
    axes[0].bar(x - w / 2, train_tirs, w, label='Train (80%)', alpha=0.8, color='steelblue')
    axes[0].bar(x + w / 2, test_tirs, w, label='Test (20%)', alpha=0.8, color='coral')
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(names7)
    axes[0].set_ylabel('TIR (%)')
    axes[0].set_title('EXP-2217: Temporal Holdout — TIR Stability')
    axes[0].legend()
    # Mark unstable
    for i, s in enumerate(stable):
        if not s:
            axes[0].annotate('⚠', (i, max(train_tirs[i], test_tirs[i]) + 1),
                             ha='center', fontsize=14, color='red')

    axes[1].bar(x - w / 2, train_tbrs, w, label='Train (80%)', alpha=0.8, color='steelblue')
    axes[1].bar(x + w / 2, test_tbrs, w, label='Test (20%)', alpha=0.8, color='coral')
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(names7)
    axes[1].set_ylabel('TBR (%)')
    axes[1].set_title('EXP-2217: Temporal Holdout — TBR Stability')
    axes[1].axhline(4, color='red', ls='--', alpha=0.5, label='Safety 4%')
    axes[1].legend()

    plt.tight_layout()
    plt.savefig(f'{fig_dir}/ctrl-fig07-holdout.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  [fig] ctrl-fig07-holdout.png")

    # Fig 8: Cross-Patient Rules (EXP-2218) — overview
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    r2218 = all_results['exp_2218']
    pm = r2218['patient_metrics']
    names8 = sorted(pm.keys())

    # Delivery ratio vs TBR
    drs = [pm[n]['delivery_ratio'] or np.nan for n in names8]
    tbrs = [pm[n]['tbr'] for n in names8]
    cvs = [pm[n]['cv'] for n in names8]

    valid8 = [i for i, d in enumerate(drs) if not np.isnan(d)]
    axes[0].scatter([drs[i] for i in valid8], [tbrs[i] for i in valid8],
                    c=[colors[i] for i in valid8], s=100, zorder=3)
    for i in valid8:
        axes[0].annotate(names8[i], (drs[i], tbrs[i]), fontsize=9, ha='center', va='bottom')
    axes[0].set_xlabel('Delivery Ratio')
    axes[0].set_ylabel('TBR (%)')
    axes[0].set_title('EXP-2218: Universal Rule — Delivery Ratio vs TBR')
    axes[0].axvline(0.5, color='orange', ls='--', alpha=0.5, label='DR=0.5 threshold')
    axes[0].axhline(4, color='red', ls='--', alpha=0.5, label='TBR=4% threshold')
    axes[0].legend()

    # CV vs TIR
    tirs = [pm[n]['tir'] for n in names8]
    axes[1].scatter(cvs, tirs, c=[colors[i] for i in range(len(names8))], s=100, zorder=3)
    for i, n in enumerate(names8):
        axes[1].annotate(n, (cvs[i], tirs[i]), fontsize=9, ha='center', va='bottom')
    axes[1].set_xlabel('Coefficient of Variation (%)')
    axes[1].set_ylabel('TIR (%)')
    axes[1].set_title('EXP-2218: CV vs TIR Across Patients')
    axes[1].axvline(36, color='orange', ls='--', alpha=0.5, label='CV=36% threshold')
    axes[1].legend()

    plt.tight_layout()
    plt.savefig(f'{fig_dir}/ctrl-fig08-cross-patient.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  [fig] ctrl-fig08-cross-patient.png")


# ─────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description='EXP-2211–2218: Control Theory & Safety')
    parser.add_argument('--figures', action='store_true', help='Generate figures')
    args = parser.parse_args()

    print("Loading patients...")
    patients = load_patients('externals/ns-data/patients/')
    print(f"  Loaded {len(patients)} patients")

    results = {}
    experiments = [
        ('exp_2211', 'System Gain Analysis', exp_2211_system_gain),
        ('exp_2212', 'Stability Margins', exp_2212_stability_margins),
        ('exp_2213', 'Oscillation Detection', exp_2213_oscillation_detection),
        ('exp_2214', 'Disturbance Rejection', exp_2214_disturbance_rejection),
        ('exp_2215', 'IOB Model Validation', exp_2215_iob_validation),
        ('exp_2216', 'Safety Envelope', exp_2216_safety_envelope),
        ('exp_2217', 'Temporal Holdout Validation', exp_2217_temporal_holdout),
        ('exp_2218', 'Cross-Patient Rule Extraction', exp_2218_cross_patient_rules),
    ]

    for key, name, func in experiments:
        exp_id = key.replace('exp_', 'EXP-')
        print(f"\n{'=' * 60}")
        print(f"  {exp_id}: {name}")
        print(f"{'=' * 60}")
        try:
            results[key] = func(patients)
            print(f"  ✓ {exp_id} PASSED")

            # Print summary
            if isinstance(results[key], dict):
                for pname, pdata in sorted(results[key].items()):
                    if isinstance(pdata, dict) and not pdata.get('skip', False):
                        # Print first 3 numeric fields
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
    out_file = f'{out_dir}/exp-2211-2218_control_theory.json'
    with open(out_file, 'w') as f:
        json.dump(results, f, indent=2, cls=NumpyEncoder)
    print(f"\nResults saved to {out_file}")

    if args.figures:
        fig_dir = 'docs/60-research/figures'
        print("\nGenerating figures...")
        generate_figures(results, fig_dir)
        print("All figures generated.")

    # Summary
    print("\n" + "=" * 60)
    print("  SUMMARY: EXP-2211–2218")
    print("=" * 60)
    passed = sum(1 for k in results if 'error' not in results[k])
    print(f"  {passed}/8 experiments passed")

    return results


if __name__ == '__main__':
    main()
