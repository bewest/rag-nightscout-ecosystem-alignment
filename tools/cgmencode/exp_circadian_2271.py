#!/usr/bin/env python3
"""
EXP-2271 through EXP-2278: Circadian Therapy Profiling

Builds actionable time-varying ISF, CR, and basal profiles from CGM/AID data.
Directly motivated by EXP-2261-2268 finding that circadian rhythm is the
dominant variability source for 9/11 patients.

Experiments:
  2271: 24h ISF profiles (response-curve ISF at each hour)
  2272: 24h basal profiles (overnight drift analysis per hour)
  2273: 24h CR profiles (meal response by time of day)
  2274: Dawn phenomenon quantification
  2275: Circadian profile stability (month-to-month)
  2276: Projected TIR improvement with time-varying profiles
  2277: Profile complexity vs benefit (2-zone vs 6-zone vs 24h)
  2278: Cross-patient profile universality

Usage:
  PYTHONPATH=tools python3 tools/cgmencode/exp_circadian_2271.py --figures
"""

import argparse
import json
import os
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

warnings.filterwarnings('ignore', category=FutureWarning)
warnings.filterwarnings('ignore', category=RuntimeWarning)

# Import shared helpers
from cgmencode.exp_metabolic_441 import load_patients

STEPS_PER_HOUR = 12  # 5-min steps
STEPS_PER_DAY = 288

# ── Helpers ──────────────────────────────────────────────────────────────

def hour_of_day(df):
    """Return hour-of-day (0-23) for each row."""
    if 'hour' in df.columns:
        return df['hour'].values
    idx = pd.to_datetime(df.index) if not isinstance(df.index, pd.DatetimeIndex) else df.index
    return idx.hour

def find_corrections(df, glucose_col='bg', bolus_col='bolus',
                     min_glucose=150, min_bolus=0.3, window_steps=36):
    """Find correction bolus episodes and compute ISF via response curve.
    Returns list of dicts with hour, isf, bolus, bg_start, bg_end."""
    bg = df[glucose_col].values if glucose_col in df.columns else df['glucose'].values
    bolus = df[bolus_col].values if bolus_col in df.columns else np.zeros(len(df))
    hours = hour_of_day(df)
    carbs = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(df))

    corrections = []
    i = 0
    while i < len(bg) - window_steps:
        if bolus[i] >= min_bolus and bg[i] >= min_glucose:
            # Check no carbs in window
            carb_sum = np.nansum(carbs[i:i+window_steps])
            if carb_sum <= 1.0:  # negligible carbs
                bg_window = bg[i:i+window_steps]
                valid = ~np.isnan(bg_window)
                if valid.sum() >= window_steps // 2:
                    bg_start = bg_window[0]
                    bg_min_idx = np.nanargmin(bg_window)
                    if bg_min_idx > 2:  # glucose actually dropped
                        bg_end = bg_window[bg_min_idx]
                        drop = bg_start - bg_end
                        if drop > 5:  # meaningful correction
                            isf = drop / bolus[i]
                            corrections.append({
                                'hour': int(hours[i]),
                                'isf': float(isf),
                                'bolus': float(bolus[i]),
                                'bg_start': float(bg_start),
                                'bg_end': float(bg_end),
                                'drop': float(drop),
                                'step': int(i)
                            })
                            i += window_steps  # skip past this correction
                            continue
        i += 1
    return corrections


def find_meals(df, carb_col='carbs', glucose_col='bg', min_carbs=5,
               window_steps=36):
    """Find meal episodes and compute CR from glucose rise.
    Returns list of dicts with hour, cr, carbs, bg_rise."""
    bg = df[glucose_col].values if glucose_col in df.columns else df['glucose'].values
    carbs = df[carb_col].values if carb_col in df.columns else np.zeros(len(df))
    hours = hour_of_day(df)
    bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(len(df))

    meals = []
    i = 0
    while i < len(bg) - window_steps:
        if carbs[i] >= min_carbs:
            bg_window = bg[i:i+window_steps]
            valid = ~np.isnan(bg_window)
            if valid.sum() >= window_steps // 2:
                bg_start = bg_window[0]
                # Look at glucose rise in first 2h
                rise_window = bg[i:i+24]  # 2 hours
                valid_rise = ~np.isnan(rise_window)
                if valid_rise.sum() >= 6:
                    bg_peak = np.nanmax(rise_window)
                    rise = bg_peak - bg_start
                    # Compute effective CR: carbs / (rise / ISF_proxy + bolus)
                    # Simplified: just use carbs / bolus if bolus given
                    total_bolus = np.nansum(bolus[max(0,i-2):i+6])
                    if total_bolus > 0.5:
                        cr = carbs[i] / total_bolus
                        meals.append({
                            'hour': int(hours[i]),
                            'cr': float(cr),
                            'carbs': float(carbs[i]),
                            'bolus': float(total_bolus),
                            'bg_start': float(bg_start),
                            'bg_peak': float(bg_peak),
                            'rise': float(rise),
                            'step': int(i)
                        })
                        i += window_steps
                        continue
        i += 1
    return meals


def compute_overnight_drift(df, glucose_col='bg'):
    """Compute overnight glucose drift rates for basal assessment.
    Returns hourly drift rates (mg/dL per hour) for overnight hours."""
    bg = df[glucose_col].values if glucose_col in df.columns else df['glucose'].values
    hours = hour_of_day(df)
    carbs = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(df))
    bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(len(df))

    # Look for quiet periods: no carbs, no bolus for 2h before and 1h after
    quiet_mask = np.ones(len(bg), dtype=bool)
    for offset in range(-24, 12):  # 2h before to 1h after
        shifted_carbs = np.roll(carbs, -offset)
        shifted_bolus = np.roll(bolus, -offset)
        quiet_mask &= (shifted_carbs <= 0.5) & (shifted_bolus <= 0.1)

    # Compute glucose rate of change (mg/dL per 5min → per hour)
    rate = np.full(len(bg), np.nan)
    rate[1:] = (bg[1:] - bg[:-1]) * STEPS_PER_HOUR  # per hour

    # Hourly drift rates during quiet periods
    hourly_drift = {}
    for h in range(24):
        mask = (hours == h) & quiet_mask & ~np.isnan(rate) & ~np.isnan(bg)
        if mask.sum() >= 10:
            hourly_drift[h] = {
                'drift_per_hour': float(np.nanmedian(rate[mask])),
                'drift_std': float(np.nanstd(rate[mask])),
                'n_samples': int(mask.sum()),
                'mean_bg': float(np.nanmean(bg[mask]))
            }
    return hourly_drift


def compute_profile_isf(patient_dict):
    """Extract the profile ISF from patient data."""
    pk = patient_dict.get('pk', {})
    if isinstance(pk, dict):
        isf = pk.get('isf', pk.get('correction_factor', None))
        if isf is not None:
            return float(isf)
    return None


def compute_profile_cr(patient_dict):
    """Extract the profile CR from patient data."""
    pk = patient_dict.get('pk', {})
    if isinstance(pk, dict):
        cr = pk.get('carb_ratio', pk.get('cr', None))
        if cr is not None:
            return float(cr)
    return None


def compute_profile_basal(patient_dict):
    """Extract the profile basal rate from patient data."""
    pk = patient_dict.get('pk', {})
    if isinstance(pk, dict):
        basal = pk.get('basal', pk.get('basal_rate', None))
        if basal is not None:
            return float(basal)
    return None


def compute_tir(bg_array, low=70, high=180):
    """Compute time-in-range percentage."""
    valid = bg_array[~np.isnan(bg_array)]
    if len(valid) == 0:
        return np.nan
    return float(np.mean((valid >= low) & (valid <= high)) * 100)


# ── Experiments ──────────────────────────────────────────────────────────

def exp_2271_isf_profiles(patients):
    """24h ISF profiles: estimate ISF at each hour of day."""
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        corrections = find_corrections(df)
        if len(corrections) < 10:
            results[name] = {'n_corrections': len(corrections), 'skipped': True}
            continue

        # Hourly ISF
        hourly_isf = {}
        for h in range(24):
            hour_corr = [c for c in corrections if c['hour'] == h]
            if len(hour_corr) >= 2:
                isfs = [c['isf'] for c in hour_corr]
                hourly_isf[str(h)] = {
                    'median_isf': float(np.median(isfs)),
                    'mean_isf': float(np.mean(isfs)),
                    'std_isf': float(np.std(isfs)),
                    'n': len(hour_corr)
                }

        # Overall stats
        all_isfs = [c['isf'] for c in corrections]
        profile_isf = compute_profile_isf(pat)

        # Peak and trough hours
        valid_hours = {int(h): v['median_isf'] for h, v in hourly_isf.items()}
        if len(valid_hours) >= 4:
            peak_hour = max(valid_hours, key=valid_hours.get)
            trough_hour = min(valid_hours, key=valid_hours.get)
            ratio = valid_hours[peak_hour] / valid_hours[trough_hour] if valid_hours[trough_hour] > 0 else np.nan
        else:
            peak_hour = trough_hour = ratio = None

        results[name] = {
            'n_corrections': len(corrections),
            'hourly_isf': hourly_isf,
            'overall_median': float(np.median(all_isfs)),
            'overall_mean': float(np.mean(all_isfs)),
            'overall_cv': float(np.std(all_isfs) / np.mean(all_isfs)) if np.mean(all_isfs) > 0 else np.nan,
            'profile_isf': profile_isf,
            'peak_hour': peak_hour,
            'trough_hour': trough_hour,
            'peak_trough_ratio': float(ratio) if ratio is not None else None,
            'hours_with_data': len(hourly_isf)
        }
        print(f"  {name}: {len(corrections)} corrections, peak_h={peak_hour}, trough_h={trough_hour}, ratio={ratio:.2f}" if ratio else f"  {name}: {len(corrections)} corrections, insufficient hourly data")
    return results


def exp_2272_basal_profiles(patients):
    """24h basal profiles from overnight glucose drift analysis."""
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        drift = compute_overnight_drift(df)

        if len(drift) < 6:
            results[name] = {'n_hours': len(drift), 'skipped': True}
            continue

        profile_basal = compute_profile_basal(pat)

        # Ideal basal adjustment: negative drift means glucose falling → reduce basal
        # positive drift means glucose rising → increase basal
        # adjustment = drift / ISF_proxy (simplified)
        profile_isf = compute_profile_isf(pat) or 50.0
        adjustments = {}
        for h, d in drift.items():
            # basal_adj = drift_per_hour / ISF → U/hr adjustment needed
            adj = d['drift_per_hour'] / profile_isf
            adjustments[str(h)] = {
                'drift_per_hour': d['drift_per_hour'],
                'basal_adjustment': float(adj),
                'n_samples': d['n_samples'],
                'mean_bg': d['mean_bg']
            }

        # Dawn phenomenon: drift increase between 3am-8am vs midnight-3am
        night_drift = [drift[h]['drift_per_hour'] for h in range(0, 3) if h in drift]
        dawn_drift = [drift[h]['drift_per_hour'] for h in range(3, 8) if h in drift]
        dawn_effect = np.mean(dawn_drift) - np.mean(night_drift) if night_drift and dawn_drift else None

        results[name] = {
            'n_hours': len(drift),
            'hourly_drift': {str(h): v for h, v in drift.items()},
            'adjustments': adjustments,
            'profile_basal': profile_basal,
            'dawn_effect': float(dawn_effect) if dawn_effect is not None else None,
            'max_drift_hour': max(drift.keys(), key=lambda h: drift[h]['drift_per_hour']),
            'min_drift_hour': min(drift.keys(), key=lambda h: drift[h]['drift_per_hour']),
        }
        print(f"  {name}: {len(drift)} hours covered, dawn_effect={dawn_effect:.1f} mg/dL/h" if dawn_effect else f"  {name}: {len(drift)} hours covered")
    return results


def exp_2273_cr_profiles(patients):
    """24h CR profiles: estimate carb ratio at each hour of day."""
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        meals = find_meals(df)

        if len(meals) < 10:
            results[name] = {'n_meals': len(meals), 'skipped': True}
            continue

        # Hourly CR
        hourly_cr = {}
        for h in range(24):
            hour_meals = [m for m in meals if m['hour'] == h]
            if len(hour_meals) >= 2:
                crs = [m['cr'] for m in hour_meals]
                hourly_cr[str(h)] = {
                    'median_cr': float(np.median(crs)),
                    'mean_cr': float(np.mean(crs)),
                    'std_cr': float(np.std(crs)),
                    'n': len(hour_meals)
                }

        all_crs = [m['cr'] for m in meals]
        profile_cr = compute_profile_cr(pat)

        valid_hours = {int(h): v['median_cr'] for h, v in hourly_cr.items()}
        if len(valid_hours) >= 4:
            peak_hour = max(valid_hours, key=valid_hours.get)
            trough_hour = min(valid_hours, key=valid_hours.get)
            ratio = valid_hours[peak_hour] / valid_hours[trough_hour] if valid_hours[trough_hour] > 0 else np.nan
        else:
            peak_hour = trough_hour = ratio = None

        results[name] = {
            'n_meals': len(meals),
            'hourly_cr': hourly_cr,
            'overall_median': float(np.median(all_crs)),
            'overall_mean': float(np.mean(all_crs)),
            'overall_cv': float(np.std(all_crs) / np.mean(all_crs)) if np.mean(all_crs) > 0 else np.nan,
            'profile_cr': profile_cr,
            'peak_hour': peak_hour,
            'trough_hour': trough_hour,
            'peak_trough_ratio': float(ratio) if ratio is not None else None,
            'hours_with_data': len(hourly_cr)
        }
        print(f"  {name}: {len(meals)} meals, peak_h={peak_hour}, trough_h={trough_hour}" if peak_hour is not None else f"  {name}: {len(meals)} meals, insufficient hourly data")
    return results


def exp_2274_dawn_phenomenon(patients):
    """Quantify dawn phenomenon: magnitude, timing, prevalence."""
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        bg_col = 'bg' if 'bg' in df.columns else 'glucose'
        bg = df[bg_col].values
        hours = hour_of_day(df)

        # Compute hourly mean glucose
        hourly_bg = {}
        for h in range(24):
            mask = (hours == h) & ~np.isnan(bg)
            if mask.sum() >= 50:
                hourly_bg[h] = float(np.nanmean(bg[mask]))

        if len(hourly_bg) < 20:
            results[name] = {'skipped': True, 'n_hours': len(hourly_bg)}
            continue

        # Dawn phenomenon: rise from nadir (typically 2-4am) to morning peak (6-10am)
        night_hours = [h for h in range(0, 5) if h in hourly_bg]
        morning_hours = [h for h in range(5, 10) if h in hourly_bg]

        if night_hours and morning_hours:
            night_bg = [hourly_bg[h] for h in night_hours]
            morning_bg = [hourly_bg[h] for h in morning_hours]
            nadir = min(night_bg)
            nadir_hour = night_hours[night_bg.index(nadir)]
            morning_peak = max(morning_bg)
            morning_peak_hour = morning_hours[morning_bg.index(morning_peak)]
            dawn_rise = morning_peak - nadir
        else:
            nadir = nadir_hour = morning_peak = morning_peak_hour = dawn_rise = None

        # Dusk phenomenon: afternoon rise
        afternoon_hours = [h for h in range(14, 19) if h in hourly_bg]
        midday_hours = [h for h in range(11, 14) if h in hourly_bg]
        if afternoon_hours and midday_hours:
            midday_bg = np.mean([hourly_bg[h] for h in midday_hours])
            afternoon_peak = max([hourly_bg[h] for h in afternoon_hours])
            dusk_rise = afternoon_peak - midday_bg
        else:
            dusk_rise = None

        # Overall circadian amplitude
        all_bg = [hourly_bg[h] for h in sorted(hourly_bg.keys())]
        amplitude = max(all_bg) - min(all_bg)

        # Day-to-day variability of dawn
        # Compute per-day dawn rise (4am to 8am glucose change)
        n_days = len(bg) // STEPS_PER_DAY
        daily_dawn = []
        for d in range(n_days):
            start = d * STEPS_PER_DAY
            # 4am = step 48, 8am = step 96
            bg_4am = bg[start + 48:start + 54]  # 4:00-4:25
            bg_8am = bg[start + 96:start + 102]  # 8:00-8:25
            v4 = bg_4am[~np.isnan(bg_4am)]
            v8 = bg_8am[~np.isnan(bg_8am)]
            if len(v4) >= 2 and len(v8) >= 2:
                daily_dawn.append(float(np.mean(v8) - np.mean(v4)))

        results[name] = {
            'hourly_bg': {str(h): v for h, v in hourly_bg.items()},
            'dawn_rise': float(dawn_rise) if dawn_rise is not None else None,
            'nadir_hour': nadir_hour,
            'morning_peak_hour': morning_peak_hour,
            'nadir_bg': float(nadir) if nadir is not None else None,
            'morning_peak_bg': float(morning_peak) if morning_peak is not None else None,
            'dusk_rise': float(dusk_rise) if dusk_rise is not None else None,
            'circadian_amplitude': float(amplitude),
            'daily_dawn_mean': float(np.mean(daily_dawn)) if daily_dawn else None,
            'daily_dawn_std': float(np.std(daily_dawn)) if daily_dawn else None,
            'daily_dawn_pct_positive': float(np.mean([d > 0 for d in daily_dawn]) * 100) if daily_dawn else None,
            'n_days_analyzed': len(daily_dawn)
        }
        if dawn_rise is not None:
            print(f"  {name}: dawn={dawn_rise:.1f} mg/dL ({nadir_hour}→{morning_peak_hour}h), amplitude={amplitude:.1f}, {len(daily_dawn)} days")
        else:
            print(f"  {name}: insufficient data for dawn analysis")
    return results


def exp_2275_stability(patients):
    """Circadian profile stability: do time-of-day patterns change month to month?"""
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        bg_col = 'bg' if 'bg' in df.columns else 'glucose'
        bg = df[bg_col].values
        hours = hour_of_day(df)
        n_steps = len(bg)
        n_days = n_steps // STEPS_PER_DAY

        if n_days < 60:
            results[name] = {'skipped': True, 'n_days': n_days}
            continue

        # Split into 30-day windows
        window_days = 30
        window_steps = window_days * STEPS_PER_DAY
        n_windows = n_steps // window_steps
        if n_windows < 2:
            results[name] = {'skipped': True, 'n_days': n_days, 'reason': 'insufficient windows'}
            continue

        window_profiles = []
        for w in range(n_windows):
            start = w * window_steps
            end = start + window_steps
            w_bg = bg[start:end]
            w_hours = hours[start:end]
            profile = []
            for h in range(24):
                mask = (w_hours == h) & ~np.isnan(w_bg)
                if mask.sum() >= 10:
                    profile.append(float(np.nanmean(w_bg[mask])))
                else:
                    profile.append(np.nan)
            window_profiles.append(profile)

        # Compute pairwise correlations between window profiles
        profiles = np.array(window_profiles)
        n_w = len(profiles)
        correlations = []
        for i in range(n_w):
            for j in range(i+1, n_w):
                p1, p2 = profiles[i], profiles[j]
                valid = ~np.isnan(p1) & ~np.isnan(p2)
                if valid.sum() >= 12:
                    r = np.corrcoef(p1[valid], p2[valid])[0, 1]
                    correlations.append(float(r))

        # Compute profile drift: how much does the 24h profile change?
        drifts = []
        for i in range(n_w - 1):
            p1, p2 = profiles[i], profiles[i+1]
            valid = ~np.isnan(p1) & ~np.isnan(p2)
            if valid.sum() >= 12:
                rmse = float(np.sqrt(np.mean((p1[valid] - p2[valid])**2)))
                drifts.append(rmse)

        # Overall stability score: mean pairwise correlation
        stability = float(np.mean(correlations)) if correlations else np.nan

        results[name] = {
            'n_windows': n_w,
            'window_days': window_days,
            'stability_score': stability,
            'mean_correlation': stability,
            'min_correlation': float(np.min(correlations)) if correlations else None,
            'max_correlation': float(np.max(correlations)) if correlations else None,
            'mean_drift_rmse': float(np.mean(drifts)) if drifts else None,
            'max_drift_rmse': float(np.max(drifts)) if drifts else None,
            'window_profiles': [[float(v) if not np.isnan(v) else None for v in p] for p in window_profiles],
            'correlations': correlations
        }
        print(f"  {name}: {n_w} windows, stability={stability:.3f}, mean_drift={np.mean(drifts):.1f} mg/dL" if drifts else f"  {name}: {n_w} windows")
    return results


def exp_2276_tir_projection(patients):
    """Project TIR improvement if time-varying profiles were used."""
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        bg_col = 'bg' if 'bg' in df.columns else 'glucose'
        bg = df[bg_col].values
        hours = hour_of_day(df)

        # Current TIR
        current_tir = compute_tir(bg)

        # Compute hourly mean glucose
        hourly_bg = {}
        for h in range(24):
            mask = (hours == h) & ~np.isnan(bg)
            if mask.sum() >= 50:
                hourly_bg[h] = np.nanmean(bg[mask])

        if len(hourly_bg) < 20:
            results[name] = {'skipped': True, 'current_tir': current_tir}
            continue

        # Simulate profile correction: shift glucose at each hour to target 120
        target = 120.0
        corrected_bg = bg.copy()
        for h in range(24):
            if h in hourly_bg:
                offset = hourly_bg[h] - target
                mask = (hours == h) & ~np.isnan(bg)
                # Apply proportional correction (not full shift, since profile
                # correction can't eliminate all variability — assume 50% effective)
                corrected_bg[mask] = bg[mask] - offset * 0.5

        projected_tir = compute_tir(corrected_bg)

        # Also simulate a simpler 2-zone correction (day/night)
        day_bg = np.mean([hourly_bg[h] for h in range(7, 22) if h in hourly_bg])
        night_bg = np.mean([hourly_bg[h] for h in list(range(0, 7)) + [22, 23] if h in hourly_bg])
        corrected_2zone = bg.copy()
        day_offset = (day_bg - target) * 0.5
        night_offset = (night_bg - target) * 0.5
        day_mask = np.isin(hours, list(range(7, 22))) & ~np.isnan(bg)
        night_mask = ~np.isin(hours, list(range(7, 22))) & ~np.isnan(bg)
        corrected_2zone[day_mask] -= day_offset
        corrected_2zone[night_mask] -= night_offset
        projected_2zone = compute_tir(corrected_2zone)

        # Compute time below range (TBR) changes
        current_tbr = float(np.mean(bg[~np.isnan(bg)] < 70) * 100)
        projected_tbr = float(np.mean(corrected_bg[~np.isnan(corrected_bg)] < 70) * 100)
        projected_tbr_2zone = float(np.mean(corrected_2zone[~np.isnan(corrected_2zone)] < 70) * 100)

        results[name] = {
            'current_tir': current_tir,
            'projected_tir_24h': projected_tir,
            'projected_tir_2zone': projected_2zone,
            'tir_gain_24h': projected_tir - current_tir,
            'tir_gain_2zone': projected_2zone - current_tir,
            'current_tbr': current_tbr,
            'projected_tbr_24h': projected_tbr,
            'projected_tbr_2zone': projected_tbr_2zone,
            'day_mean_bg': float(day_bg),
            'night_mean_bg': float(night_bg),
            'day_night_diff': float(day_bg - night_bg)
        }
        print(f"  {name}: TIR {current_tir:.1f}→{projected_tir:.1f} (+{projected_tir-current_tir:.1f}pp 24h), 2zone: +{projected_2zone-current_tir:.1f}pp")
    return results


def exp_2277_complexity(patients):
    """Profile complexity vs benefit: 2-zone vs 6-zone vs 24h."""
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        bg_col = 'bg' if 'bg' in df.columns else 'glucose'
        bg = df[bg_col].values
        hours = hour_of_day(df)
        current_tir = compute_tir(bg)

        hourly_bg = {}
        for h in range(24):
            mask = (hours == h) & ~np.isnan(bg)
            if mask.sum() >= 50:
                hourly_bg[h] = np.nanmean(bg[mask])

        if len(hourly_bg) < 20:
            results[name] = {'skipped': True, 'current_tir': current_tir}
            continue

        target = 120.0
        effectiveness = 0.5  # 50% correction effectiveness

        # Zone definitions
        zones = {
            '1_flat': [(list(range(24)),)],
            '2_day_night': [(list(range(7, 22)),), (list(range(0, 7)) + [22, 23],)],
            '3_meals': [(list(range(0, 7)) + [22, 23],), (list(range(7, 13)),), (list(range(13, 22)),)],
            '6_quarter': [
                (list(range(0, 4)),), (list(range(4, 8)),),
                (list(range(8, 12)),), (list(range(12, 16)),),
                (list(range(16, 20)),), (list(range(20, 24)),)
            ],
            '24_hourly': [([h],) for h in range(24)]
        }

        zone_results = {}
        for zone_name, zone_def in zones.items():
            corrected = bg.copy()
            for zone_hours_tuple in zone_def:
                zone_hours = zone_hours_tuple[0]
                zone_bg = np.mean([hourly_bg[h] for h in zone_hours if h in hourly_bg])
                offset = (zone_bg - target) * effectiveness
                mask = np.isin(hours, zone_hours) & ~np.isnan(bg)
                corrected[mask] -= offset

            tir = compute_tir(corrected)
            tbr = float(np.mean(corrected[~np.isnan(corrected)] < 70) * 100)
            zone_results[zone_name] = {
                'tir': tir,
                'tir_gain': tir - current_tir,
                'tbr': tbr,
                'n_zones': len(zone_def)
            }

        # Marginal benefit: gain per additional zone
        zone_order = ['1_flat', '2_day_night', '3_meals', '6_quarter', '24_hourly']
        for i in range(1, len(zone_order)):
            prev = zone_results[zone_order[i-1]]['tir_gain']
            curr = zone_results[zone_order[i]]['tir_gain']
            zone_results[zone_order[i]]['marginal_gain'] = curr - prev

        # Find optimal zone count (diminishing returns threshold)
        gains = [(zone_results[z]['n_zones'], zone_results[z]['tir_gain']) for z in zone_order]

        results[name] = {
            'current_tir': current_tir,
            'zones': zone_results,
            'zone_gains': gains,
            'best_zone': max(zone_results.keys(), key=lambda z: zone_results[z]['tir_gain'])
        }
        flat_gain = zone_results['1_flat']['tir_gain']
        two_gain = zone_results['2_day_night']['tir_gain']
        full_gain = zone_results['24_hourly']['tir_gain']
        print(f"  {name}: flat={flat_gain:+.1f}, 2-zone={two_gain:+.1f}, 24h={full_gain:+.1f}")
    return results


def exp_2278_universality(patients):
    """Cross-patient profile universality: are circadian patterns similar?"""
    # Build 24h glucose profiles for each patient
    profiles = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        bg_col = 'bg' if 'bg' in df.columns else 'glucose'
        bg = df[bg_col].values
        hours = hour_of_day(df)

        hourly_bg = []
        for h in range(24):
            mask = (hours == h) & ~np.isnan(bg)
            if mask.sum() >= 50:
                hourly_bg.append(float(np.nanmean(bg[mask])))
            else:
                hourly_bg.append(np.nan)
        profiles[name] = hourly_bg

    # Normalize profiles (subtract mean, divide by std) for shape comparison
    norm_profiles = {}
    for name, prof in profiles.items():
        arr = np.array(prof)
        valid = ~np.isnan(arr)
        if valid.sum() >= 20:
            mean = np.nanmean(arr)
            std = np.nanstd(arr)
            if std > 0:
                norm_profiles[name] = (arr - mean) / std
            else:
                norm_profiles[name] = arr - mean

    # Pairwise correlation of normalized profiles
    names = sorted(norm_profiles.keys())
    n = len(names)
    corr_matrix = np.full((n, n), np.nan)
    for i in range(n):
        for j in range(n):
            p1, p2 = norm_profiles[names[i]], norm_profiles[names[j]]
            valid = ~np.isnan(p1) & ~np.isnan(p2)
            if valid.sum() >= 12:
                corr_matrix[i, j] = np.corrcoef(p1[valid], p2[valid])[0, 1]

    # Cluster patients by profile shape
    # Simple: find highly correlated pairs (r > 0.7)
    high_corr_pairs = []
    for i in range(n):
        for j in range(i+1, n):
            if not np.isnan(corr_matrix[i, j]) and corr_matrix[i, j] > 0.7:
                high_corr_pairs.append((names[i], names[j], float(corr_matrix[i, j])))

    # Population template: mean of all normalized profiles
    all_norm = np.array([norm_profiles[n] for n in names if n in norm_profiles])
    template = np.nanmean(all_norm, axis=0)
    template_corrs = {}
    for name in names:
        p = norm_profiles.get(name)
        if p is not None:
            valid = ~np.isnan(p) & ~np.isnan(template)
            if valid.sum() >= 12:
                template_corrs[name] = float(np.corrcoef(p[valid], template[valid])[0, 1])

    # How well does the template predict individual patients?
    mean_template_corr = float(np.mean(list(template_corrs.values()))) if template_corrs else np.nan

    results = {
        'correlation_matrix': corr_matrix.tolist(),
        'patient_names': names,
        'high_corr_pairs': high_corr_pairs,
        'template_correlations': template_corrs,
        'mean_template_correlation': mean_template_corr,
        'template_profile': template.tolist(),
        'raw_profiles': {n: profiles[n] for n in names},
        'norm_profiles': {n: norm_profiles[n].tolist() for n in names if n in norm_profiles}
    }

    print(f"  Template correlation: mean={mean_template_corr:.3f}")
    print(f"  High-correlation pairs (r>0.7): {len(high_corr_pairs)}")
    for p1, p2, r in high_corr_pairs:
        print(f"    {p1}-{p2}: r={r:.3f}")

    return results


# ── Figure Generation ────────────────────────────────────────────────────

def generate_figures(results, fig_dir):
    """Generate all 8 figures."""
    os.makedirs(fig_dir, exist_ok=True)

    # Fig 1: 24h ISF profiles
    fig, axes = plt.subplots(3, 4, figsize=(16, 10))
    axes = axes.flatten()
    r2271 = results['exp_2271']
    for idx, name in enumerate(sorted(r2271.keys())):
        if idx >= 11:
            break
        ax = axes[idx]
        data = r2271[name]
        if data.get('skipped'):
            ax.text(0.5, 0.5, f'{name}\nskipped', ha='center', va='center', transform=ax.transAxes)
            ax.set_title(name)
            continue
        hourly = data.get('hourly_isf', {})
        hours_list = sorted([int(h) for h in hourly.keys()])
        isfs = [hourly[str(h)]['median_isf'] for h in hours_list]
        ns = [hourly[str(h)]['n'] for h in hours_list]
        ax.bar(hours_list, isfs, color='steelblue', alpha=0.7)
        if data.get('profile_isf'):
            ax.axhline(data['profile_isf'], color='red', ls='--', label='Profile')
        ax.axhline(data['overall_median'], color='orange', ls=':', label='Median')
        ax.set_title(f"{name} (n={data['n_corrections']})")
        ax.set_xlabel('Hour')
        ax.set_ylabel('ISF (mg/dL/U)')
        ax.set_xlim(-0.5, 23.5)
    axes[-1].axis('off')
    axes[-1].legend(*axes[0].get_legend_handles_labels(), loc='center', fontsize=12)
    fig.suptitle('EXP-2271: 24h ISF Profiles by Hour of Day', fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(f'{fig_dir}/circ-fig01-isf-profiles.png', dpi=150, bbox_inches='tight')
    plt.close()
    print("  Figure 1: ISF profiles")

    # Fig 2: Basal drift profiles
    fig, axes = plt.subplots(3, 4, figsize=(16, 10))
    axes = axes.flatten()
    r2272 = results['exp_2272']
    for idx, name in enumerate(sorted(r2272.keys())):
        if idx >= 11:
            break
        ax = axes[idx]
        data = r2272[name]
        if data.get('skipped'):
            ax.text(0.5, 0.5, f'{name}\nskipped', ha='center', va='center', transform=ax.transAxes)
            ax.set_title(name)
            continue
        drift = data.get('hourly_drift', {})
        hours_list = sorted([int(h) for h in drift.keys()])
        rates = [drift[str(h)]['drift_per_hour'] for h in hours_list]
        colors = ['red' if r > 0 else 'blue' for r in rates]
        ax.bar(hours_list, rates, color=colors, alpha=0.7)
        ax.axhline(0, color='black', lw=0.5)
        ax.set_title(f"{name}")
        ax.set_xlabel('Hour')
        ax.set_ylabel('Drift (mg/dL/h)')
        ax.set_xlim(-0.5, 23.5)
        # Shade dawn period
        ax.axvspan(3, 8, alpha=0.1, color='orange')
    axes[-1].axis('off')
    fig.suptitle('EXP-2272: Hourly Glucose Drift (red=rising, blue=falling)\nOrange shading = dawn period (3-8am)', fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(f'{fig_dir}/circ-fig02-basal-drift.png', dpi=150, bbox_inches='tight')
    plt.close()
    print("  Figure 2: basal drift")

    # Fig 3: CR profiles
    fig, axes = plt.subplots(3, 4, figsize=(16, 10))
    axes = axes.flatten()
    r2273 = results['exp_2273']
    for idx, name in enumerate(sorted(r2273.keys())):
        if idx >= 11:
            break
        ax = axes[idx]
        data = r2273[name]
        if data.get('skipped'):
            ax.text(0.5, 0.5, f'{name}\nskipped', ha='center', va='center', transform=ax.transAxes)
            ax.set_title(name)
            continue
        hourly = data.get('hourly_cr', {})
        hours_list = sorted([int(h) for h in hourly.keys()])
        crs = [hourly[str(h)]['median_cr'] for h in hours_list]
        ax.bar(hours_list, crs, color='green', alpha=0.7)
        if data.get('profile_cr'):
            ax.axhline(data['profile_cr'], color='red', ls='--', label='Profile')
        ax.axhline(data['overall_median'], color='orange', ls=':', label='Median')
        ax.set_title(f"{name} (n={data['n_meals']})")
        ax.set_xlabel('Hour')
        ax.set_ylabel('CR (g/U)')
        ax.set_xlim(-0.5, 23.5)
    axes[-1].axis('off')
    axes[-1].legend(*axes[0].get_legend_handles_labels(), loc='center', fontsize=12)
    fig.suptitle('EXP-2273: 24h Carb Ratio Profiles by Hour of Day', fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(f'{fig_dir}/circ-fig03-cr-profiles.png', dpi=150, bbox_inches='tight')
    plt.close()
    print("  Figure 3: CR profiles")

    # Fig 4: Dawn phenomenon
    fig, axes = plt.subplots(3, 4, figsize=(16, 10))
    axes = axes.flatten()
    r2274 = results['exp_2274']
    for idx, name in enumerate(sorted(r2274.keys())):
        if idx >= 11:
            break
        ax = axes[idx]
        data = r2274[name]
        if data.get('skipped'):
            ax.text(0.5, 0.5, f'{name}\nskipped', ha='center', va='center', transform=ax.transAxes)
            ax.set_title(name)
            continue
        hourly = data.get('hourly_bg', {})
        hours_list = sorted([int(h) for h in hourly.keys()])
        bgs = [hourly[str(h)] for h in hours_list]
        ax.plot(hours_list, bgs, 'b-o', markersize=3)
        ax.axhspan(70, 180, alpha=0.1, color='green')
        ax.axvspan(3, 8, alpha=0.1, color='orange')
        if data.get('dawn_rise') is not None:
            ax.set_title(f"{name}: dawn={data['dawn_rise']:.0f} mg/dL")
        else:
            ax.set_title(name)
        ax.set_xlabel('Hour')
        ax.set_ylabel('Mean BG (mg/dL)')
        ax.set_xlim(-0.5, 23.5)
    axes[-1].axis('off')
    fig.suptitle('EXP-2274: 24h Mean Glucose Profile & Dawn Phenomenon\nGreen=target range, orange=dawn window', fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(f'{fig_dir}/circ-fig04-dawn-phenomenon.png', dpi=150, bbox_inches='tight')
    plt.close()
    print("  Figure 4: dawn phenomenon")

    # Fig 5: Profile stability
    fig, axes = plt.subplots(3, 4, figsize=(16, 10))
    axes = axes.flatten()
    r2275 = results['exp_2275']
    for idx, name in enumerate(sorted(r2275.keys())):
        if idx >= 11:
            break
        ax = axes[idx]
        data = r2275[name]
        if data.get('skipped'):
            ax.text(0.5, 0.5, f'{name}\nskipped', ha='center', va='center', transform=ax.transAxes)
            ax.set_title(name)
            continue
        profiles = data.get('window_profiles', [])
        colors = plt.cm.viridis(np.linspace(0, 1, len(profiles)))
        for i, (prof, color) in enumerate(zip(profiles, colors)):
            valid_h = [h for h in range(24) if prof[h] is not None]
            valid_bg = [prof[h] for h in valid_h]
            ax.plot(valid_h, valid_bg, color=color, alpha=0.7, lw=1)
        ax.set_title(f"{name}: r={data['stability_score']:.2f}")
        ax.set_xlabel('Hour')
        ax.set_ylabel('BG (mg/dL)')
        ax.set_xlim(-0.5, 23.5)
    axes[-1].axis('off')
    fig.suptitle('EXP-2275: 30-Day Window Glucose Profiles (darker=earlier)\nCorrelation = profile shape stability', fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(f'{fig_dir}/circ-fig05-stability.png', dpi=150, bbox_inches='tight')
    plt.close()
    print("  Figure 5: stability")

    # Fig 6: TIR projection
    fig, ax = plt.subplots(figsize=(12, 6))
    r2276 = results['exp_2276']
    names_sorted = sorted([n for n in r2276.keys() if not r2276[n].get('skipped')])
    x = np.arange(len(names_sorted))
    current = [r2276[n]['current_tir'] for n in names_sorted]
    proj_2z = [r2276[n]['projected_tir_2zone'] for n in names_sorted]
    proj_24 = [r2276[n]['projected_tir_24h'] for n in names_sorted]
    w = 0.25
    ax.bar(x - w, current, w, label='Current', color='gray', alpha=0.7)
    ax.bar(x, proj_2z, w, label='2-Zone Profile', color='orange', alpha=0.7)
    ax.bar(x + w, proj_24, w, label='24h Profile', color='steelblue', alpha=0.7)
    ax.set_xticks(x)
    ax.set_xticklabels(names_sorted)
    ax.set_ylabel('TIR %')
    ax.set_xlabel('Patient')
    ax.axhline(70, color='green', ls='--', alpha=0.5, label='70% Target')
    ax.legend()
    ax.set_title('EXP-2276: Projected TIR with Time-Varying Profiles\n(50% correction effectiveness assumed)')
    plt.tight_layout()
    plt.savefig(f'{fig_dir}/circ-fig06-tir-projection.png', dpi=150, bbox_inches='tight')
    plt.close()
    print("  Figure 6: TIR projection")

    # Fig 7: Complexity vs benefit
    fig, ax = plt.subplots(figsize=(12, 6))
    r2277 = results['exp_2277']
    zone_names = ['1_flat', '2_day_night', '3_meals', '6_quarter', '24_hourly']
    zone_labels = ['Flat', '2-Zone\n(Day/Night)', '3-Zone\n(Meals)', '6-Zone\n(4h)', '24-Zone\n(Hourly)']
    for name in sorted(r2277.keys()):
        data = r2277[name]
        if data.get('skipped'):
            continue
        gains = [data['zones'][z]['tir_gain'] for z in zone_names]
        ax.plot(range(len(zone_names)), gains, 'o-', label=name, alpha=0.7, markersize=4)
    ax.set_xticks(range(len(zone_names)))
    ax.set_xticklabels(zone_labels)
    ax.set_ylabel('TIR Gain (pp)')
    ax.set_xlabel('Profile Complexity')
    ax.axhline(0, color='black', lw=0.5)
    ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left', fontsize=8)
    ax.set_title('EXP-2277: TIR Gain vs Profile Complexity\nDiminishing returns beyond 2-zone for most patients')
    plt.tight_layout()
    plt.savefig(f'{fig_dir}/circ-fig07-complexity.png', dpi=150, bbox_inches='tight')
    plt.close()
    print("  Figure 7: complexity")

    # Fig 8: Cross-patient universality
    r2278 = results['exp_2278']
    fig = plt.figure(figsize=(14, 6))
    gs = GridSpec(1, 2, width_ratios=[1.2, 1])

    # Correlation matrix
    ax1 = fig.add_subplot(gs[0])
    names_list = r2278['patient_names']
    corr = np.array(r2278['correlation_matrix'])
    im = ax1.imshow(corr, cmap='RdBu_r', vmin=-1, vmax=1, aspect='auto')
    ax1.set_xticks(range(len(names_list)))
    ax1.set_xticklabels(names_list)
    ax1.set_yticks(range(len(names_list)))
    ax1.set_yticklabels(names_list)
    plt.colorbar(im, ax=ax1, label='Correlation')
    ax1.set_title('Profile Shape Correlation')

    # Normalized profiles
    ax2 = fig.add_subplot(gs[1])
    norm = r2278.get('norm_profiles', {})
    template = r2278.get('template_profile', [])
    for name in sorted(norm.keys()):
        ax2.plot(range(24), norm[name], alpha=0.4, lw=1, label=name)
    if template:
        ax2.plot(range(24), template, 'k-', lw=3, label='Template', zorder=10)
    ax2.set_xlabel('Hour')
    ax2.set_ylabel('Normalized BG')
    ax2.set_title(f'Normalized Profiles (template r={r2278["mean_template_correlation"]:.2f})')
    ax2.legend(fontsize=7, ncol=2)

    fig.suptitle('EXP-2278: Cross-Patient Circadian Profile Universality', fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(f'{fig_dir}/circ-fig08-universality.png', dpi=150, bbox_inches='tight')
    plt.close()
    print("  Figure 8: universality")


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Circadian Therapy Profiling (EXP-2271–2278)')
    parser.add_argument('--figures', action='store_true', help='Generate figures')
    args = parser.parse_args()

    print("Loading patients...")
    patients = load_patients('externals/ns-data/patients/')
    for p in patients:
        print(f"  Loaded {p['name']}: {len(p['df'])} steps")
    print(f"Loaded {len(patients)} patients\n")

    results = {}

    # Run all 8 experiments
    experiments = [
        ('exp_2271', '24h ISF Profiles', exp_2271_isf_profiles),
        ('exp_2272', '24h Basal Drift Profiles', exp_2272_basal_profiles),
        ('exp_2273', '24h CR Profiles', exp_2273_cr_profiles),
        ('exp_2274', 'Dawn Phenomenon Quantification', exp_2274_dawn_phenomenon),
        ('exp_2275', 'Circadian Profile Stability', exp_2275_stability),
        ('exp_2276', 'TIR Projection with Profiles', exp_2276_tir_projection),
        ('exp_2277', 'Profile Complexity vs Benefit', exp_2277_complexity),
        ('exp_2278', 'Cross-Patient Universality', exp_2278_universality),
    ]

    for exp_id, title, func in experiments:
        print(f"Running {exp_id}: {title}...")
        results[exp_id] = func(patients)
        print(f"  ✓ completed")

    # Save results
    out_path = 'externals/experiments/exp-2271-2278_circadian.json'
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    # Convert numpy types for JSON
    def convert(obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2, default=convert)
    print(f"\nResults saved to {out_path}")

    if args.figures:
        fig_dir = 'docs/60-research/figures'
        print(f"\nGenerating figures...")
        generate_figures(results, fig_dir)
        print("All figures generated.")


if __name__ == '__main__':
    main()
