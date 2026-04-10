#!/usr/bin/env python3
"""
EXP-2351 through EXP-2358: Insulin Timing & Pharmacokinetic Profiling

Quantifies patient-specific insulin activity curves from observational data.
Prior work found effective DIA=6.0h median (vs 5h profile), fast vs slow
responders, and that insulin is 30% faster than profile assumes.

Experiments:
  2351: Correction bolus response curves (time-to-nadir, decay rate)
  2352: Meal bolus timing analysis (pre-bolus benefit quantification)
  2353: IOB decay validation (actual vs modeled IOB curves)
  2354: DIA estimation from glucose response
  2355: Onset/peak/duration profiling per patient
  2356: Circadian PK variation (does insulin work faster at certain times?)
  2357: Stacking risk from PK mismatch
  2358: PK-informed dosing recommendations

Usage:
  PYTHONPATH=tools python3 tools/cgmencode/exp_insulin_pk_2351.py --figures
  PYTHONPATH=tools python3 tools/cgmencode/exp_insulin_pk_2351.py --figures --tiny
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
from scipy.optimize import curve_fit
from scipy import stats

warnings.filterwarnings('ignore')

STEPS_PER_HOUR = 12
STEP_MIN = 5


def load_patients_parquet(parquet_dir='externals/ns-parquet/training'):
    grid = pd.read_parquet(os.path.join(parquet_dir, 'grid.parquet'))
    patients = []
    for pid in sorted(grid['patient_id'].unique()):
        pdf = grid[grid['patient_id'] == pid].copy()
        pdf = pdf.set_index('time').sort_index()
        patients.append({'name': pid, 'df': pdf})
        print(f"  {pid}: {len(pdf)} steps")
    return patients


def find_correction_boluses(df, min_bolus=0.5, max_carbs=1, window_hours=4):
    """Find isolated correction boluses (no carbs nearby)."""
    bg = df['glucose'].values
    bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(len(df))
    carbs = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(df))
    iob = df['iob'].values if 'iob' in df.columns else np.zeros(len(df))
    isf = df['scheduled_isf'].values if 'scheduled_isf' in df.columns else np.full(len(df), 50)
    
    window = int(window_hours * STEPS_PER_HOUR)
    events = []
    
    i = 0
    while i < len(df) - window:
        if not np.isnan(bolus[i]) and bolus[i] >= min_bolus:
            # Check no carbs within ±1 hour
            carb_window = carbs[max(0, i-12):min(len(df), i+13)]
            if np.nansum(carb_window) <= max_carbs:
                # Get post-bolus glucose trajectory
                post_bg = bg[i:i+window]
                valid = ~np.isnan(post_bg)
                if valid.sum() >= window * 0.5:  # Need 50% coverage
                    pre_bg = bg[max(0, i-3):i+1]
                    pre_bg_valid = pre_bg[~np.isnan(pre_bg)]
                    if len(pre_bg_valid) > 0:
                        events.append({
                            'idx': i,
                            'time': df.index[i],
                            'bolus': float(bolus[i]),
                            'pre_bg': float(np.mean(pre_bg_valid)),
                            'iob_before': float(iob[i]) if not np.isnan(iob[i]) else 0,
                            'isf': float(isf[i]) if not np.isnan(isf[i]) else 50,
                            'post_bg': post_bg.tolist(),
                            'hour': df.index[i].hour + df.index[i].minute / 60,
                        })
                i += window  # Skip ahead
            else:
                i += 1
        else:
            i += 1
    
    return events


def exp_response_model(t, bg_start, amplitude, tau):
    """Exponential decay response: BG(t) = bg_start - amplitude*(1 - exp(-t/tau))"""
    return bg_start - amplitude * (1 - np.exp(-t / tau))


# ── Experiments ──────────────────────────────────────────────────────────

def exp_2351_correction_curves(patients):
    """Correction bolus response curves."""
    results = {}
    for pat in patients:
        name = pat['name']
        events = find_correction_boluses(pat['df'])
        
        if len(events) < 5:
            results[name] = {'skipped': True, 'n_corrections': len(events)}
            print(f"  {name}: skipped ({len(events)} corrections)")
            continue
        
        nadirs = []
        time_to_nadirs = []
        drops = []
        drops_per_unit = []
        
        for ev in events:
            post = np.array(ev['post_bg'])
            valid_mask = ~np.isnan(post)
            if valid_mask.sum() < 6:
                continue
            
            nadir = np.nanmin(post)
            nadir_idx = np.nanargmin(post)
            time_to_nadir = nadir_idx * STEP_MIN  # minutes
            drop = ev['pre_bg'] - nadir
            drop_per_u = drop / ev['bolus'] if ev['bolus'] > 0 else 0
            
            nadirs.append(nadir)
            time_to_nadirs.append(time_to_nadir)
            drops.append(drop)
            drops_per_unit.append(drop_per_u)
        
        if len(drops) < 5:
            results[name] = {'skipped': True}
            continue
        
        results[name] = {
            'n_corrections': len(events),
            'n_analyzed': len(drops),
            'mean_drop': round(float(np.mean(drops)), 1),
            'mean_drop_per_unit': round(float(np.mean(drops_per_unit)), 1),
            'median_time_to_nadir': round(float(np.median(time_to_nadirs)), 0),
            'mean_time_to_nadir': round(float(np.mean(time_to_nadirs)), 0),
            'std_time_to_nadir': round(float(np.std(time_to_nadirs)), 0),
            'profile_isf': round(float(np.mean([e['isf'] for e in events])), 1),
            'effective_isf': round(float(np.mean(drops_per_unit)), 1),
            'isf_ratio': round(float(np.mean(drops_per_unit)) / (np.mean([e['isf'] for e in events]) + 1e-8), 2),
        }
        print(f"  {name}: nadir={np.median(time_to_nadirs):.0f}min, "
              f"drop/U={np.mean(drops_per_unit):.0f}, ISF ratio={results[name]['isf_ratio']:.2f}, "
              f"n={len(drops)}")
    return results


def exp_2352_meal_timing(patients):
    """Meal bolus timing analysis."""
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        bg = df['glucose'].values
        bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(len(df))
        carbs = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(df))
        
        # Find meals with boluses
        meals = []
        i = 0
        while i < len(df) - 36:
            if not np.isnan(carbs[i]) and carbs[i] >= 5:
                # Find nearest bolus within ±60 min
                search_start = max(0, i - 12)
                search_end = min(len(df), i + 13)
                bolus_window = bolus[search_start:search_end]
                
                bolus_found = False
                for j_offset in range(len(bolus_window)):
                    if not np.isnan(bolus_window[j_offset]) and bolus_window[j_offset] > 0:
                        j = search_start + j_offset
                        timing = (j - i) * STEP_MIN  # negative = pre-bolus
                        
                        # Post-meal trajectory
                        post = bg[i:i+36]
                        if np.sum(~np.isnan(post)) >= 12:
                            peak_rise = np.nanmax(post) - (bg[i] if not np.isnan(bg[i]) else np.nanmean(post[:3]))
                            meals.append({
                                'timing_min': timing,
                                'rise': float(peak_rise),
                                'carbs': float(carbs[i]),
                                'bolus': float(bolus_window[j_offset]),
                            })
                        bolus_found = True
                        break
                
                i += 12
            else:
                i += 1
        
        if len(meals) < 20:
            results[name] = {'skipped': True, 'n_meals': len(meals)}
            continue
        
        timings = np.array([m['timing_min'] for m in meals])
        rises = np.array([m['rise'] for m in meals])
        
        # Pre-bolus vs post-bolus
        pre_bolus = timings < 0
        post_bolus = timings > 0
        at_meal = timings == 0
        
        by_timing = {}
        if pre_bolus.sum() > 3:
            by_timing['pre_bolus'] = {
                'n': int(pre_bolus.sum()),
                'mean_rise': round(float(np.mean(rises[pre_bolus])), 1),
                'mean_timing': round(float(np.mean(timings[pre_bolus])), 0),
            }
        if at_meal.sum() > 3:
            by_timing['at_meal'] = {
                'n': int(at_meal.sum()),
                'mean_rise': round(float(np.mean(rises[at_meal])), 1),
            }
        if post_bolus.sum() > 3:
            by_timing['post_bolus'] = {
                'n': int(post_bolus.sum()),
                'mean_rise': round(float(np.mean(rises[post_bolus])), 1),
                'mean_timing': round(float(np.mean(timings[post_bolus])), 0),
            }
        
        # Correlation between timing and rise
        r_timing_rise, p = stats.pearsonr(timings, rises) if len(timings) > 10 else (0, 1)
        
        results[name] = {
            'n_meals': len(meals),
            'by_timing': by_timing,
            'r_timing_rise': round(float(r_timing_rise), 3),
            'mean_timing': round(float(np.mean(timings)), 0),
            'pct_pre_bolus': round(float(pre_bolus.mean()) * 100, 1),
        }
        print(f"  {name}: {len(meals)} meals, pre-bolus={pre_bolus.mean()*100:.0f}%, "
              f"timing-rise r={r_timing_rise:.2f}")
    return results


def exp_2353_iob_decay(patients):
    """IOB decay validation — actual vs modeled."""
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        iob = df['iob'].values if 'iob' in df.columns else None
        
        if iob is None or np.all(np.isnan(iob)):
            results[name] = {'skipped': True}
            continue
        
        # Find IOB peaks (after boluses) and track decay
        bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(len(df))
        
        decay_curves = []
        i = 0
        while i < len(df) - 72:  # Need 6h window
            if not np.isnan(bolus[i]) and bolus[i] >= 1.0:
                # Track IOB for 6 hours
                iob_window = iob[i:i+72]
                valid = ~np.isnan(iob_window)
                if valid.sum() >= 36:
                    peak_iob = np.nanmax(iob_window[:6])  # Peak within 30 min
                    if peak_iob > 0.5:
                        # Find half-life
                        half_target = peak_iob / 2
                        half_idx = None
                        for j in range(len(iob_window)):
                            if not np.isnan(iob_window[j]) and iob_window[j] <= half_target:
                                half_idx = j
                                break
                        
                        # Find 90% decay
                        tenth_target = peak_iob * 0.1
                        dia_idx = None
                        for j in range(len(iob_window)):
                            if not np.isnan(iob_window[j]) and iob_window[j] <= tenth_target:
                                dia_idx = j
                                break
                        
                        decay_curves.append({
                            'peak_iob': float(peak_iob),
                            'half_life_min': half_idx * STEP_MIN if half_idx else None,
                            'dia_min': dia_idx * STEP_MIN if dia_idx else None,
                            'bolus': float(bolus[i]),
                        })
                
                i += 72
            else:
                i += 1
        
        if len(decay_curves) < 5:
            results[name] = {'skipped': True}
            continue
        
        half_lives = [d['half_life_min'] for d in decay_curves if d['half_life_min'] is not None]
        dias = [d['dia_min'] for d in decay_curves if d['dia_min'] is not None]
        
        results[name] = {
            'n_curves': len(decay_curves),
            'median_half_life_min': round(float(np.median(half_lives)), 0) if half_lives else None,
            'mean_half_life_min': round(float(np.mean(half_lives)), 0) if half_lives else None,
            'median_dia_min': round(float(np.median(dias)), 0) if dias else None,
            'mean_dia_hours': round(float(np.mean(dias)) / 60, 1) if dias else None,
            'dia_std_hours': round(float(np.std(dias)) / 60, 1) if len(dias) > 1 else 0,
        }
        print(f"  {name}: t½={np.median(half_lives):.0f}min, "
              f"DIA={np.mean(dias)/60:.1f}h, n={len(decay_curves)}")
    return results


def exp_2354_dia_estimation(patients):
    """DIA estimation from glucose response curves."""
    results = {}
    for pat in patients:
        name = pat['name']
        events = find_correction_boluses(pat['df'], min_bolus=0.5, max_carbs=1)
        
        if len(events) < 5:
            results[name] = {'skipped': True}
            continue
        
        # Fit exponential decay to each correction
        taus = []
        amplitudes = []
        r2s = []
        
        for ev in events:
            post = np.array(ev['post_bg'])
            valid = ~np.isnan(post)
            if valid.sum() < 12:
                continue
            
            t = np.arange(len(post)) * STEP_MIN / 60  # hours
            t_v = t[valid]
            bg_v = post[valid]
            
            try:
                popt, pcov = curve_fit(
                    exp_response_model, t_v, bg_v,
                    p0=[ev['pre_bg'], 30, 2.0],
                    bounds=([50, 0, 0.5], [400, 200, 8.0]),
                    maxfev=1000
                )
                bg_start, amplitude, tau = popt
                predicted = exp_response_model(t_v, *popt)
                ss_res = np.sum((bg_v - predicted)**2)
                ss_tot = np.sum((bg_v - np.mean(bg_v))**2)
                r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
                
                if r2 > 0.1 and amplitude > 5:
                    taus.append(tau)
                    amplitudes.append(amplitude)
                    r2s.append(r2)
            except:
                pass
        
        if len(taus) < 3:
            results[name] = {'skipped': True, 'n_fits': len(taus)}
            continue
        
        # DIA ≈ 5τ (time for 99% of effect)
        effective_dia = np.array(taus) * 5
        
        results[name] = {
            'n_fits': len(taus),
            'median_tau': round(float(np.median(taus)), 2),
            'mean_tau': round(float(np.mean(taus)), 2),
            'median_dia_hours': round(float(np.median(effective_dia)), 1),
            'mean_dia_hours': round(float(np.mean(effective_dia)), 1),
            'std_dia_hours': round(float(np.std(effective_dia)), 1),
            'mean_r2': round(float(np.mean(r2s)), 3),
            'profile_dia': 5.0,  # Assumed standard
            'dia_ratio': round(float(np.median(effective_dia)) / 5.0, 2),
        }
        print(f"  {name}: τ={np.median(taus):.1f}h, DIA={np.median(effective_dia):.1f}h, "
              f"R²={np.mean(r2s):.2f}, n={len(taus)}")
    return results


def exp_2355_onset_peak_duration(patients):
    """Onset/peak/duration profiling per patient."""
    results = {}
    for pat in patients:
        name = pat['name']
        events = find_correction_boluses(pat['df'])
        
        if len(events) < 5:
            results[name] = {'skipped': True}
            continue
        
        onsets = []  # Time to first 10% of total drop
        peaks = []   # Time to maximum rate of drop
        durations = []  # Time to 90% of total drop
        
        for ev in events:
            post = np.array(ev['post_bg'])
            valid = ~np.isnan(post)
            if valid.sum() < 12:
                continue
            
            total_drop = ev['pre_bg'] - np.nanmin(post)
            if total_drop < 10:
                continue
            
            # Onset: first time BG drops by 10% of total
            onset_threshold = ev['pre_bg'] - total_drop * 0.1
            onset_idx = None
            for j in range(len(post)):
                if not np.isnan(post[j]) and post[j] <= onset_threshold:
                    onset_idx = j
                    break
            
            # Peak effect: maximum rate of BG decrease (steepest drop)
            rate = np.diff(post)
            rate_valid = ~np.isnan(rate)
            if rate_valid.sum() > 0:
                peak_rate_idx = np.nanargmin(rate)  # Most negative = steepest drop
                peaks.append(peak_rate_idx * STEP_MIN)
            
            # Duration: 90% of total drop
            dur_threshold = ev['pre_bg'] - total_drop * 0.9
            dur_idx = None
            for j in range(len(post)):
                if not np.isnan(post[j]) and post[j] <= dur_threshold:
                    dur_idx = j
                    break
            
            if onset_idx is not None:
                onsets.append(onset_idx * STEP_MIN)
            if dur_idx is not None:
                durations.append(dur_idx * STEP_MIN)
        
        if len(onsets) < 3:
            results[name] = {'skipped': True}
            continue
        
        results[name] = {
            'n_events': len(events),
            'median_onset_min': round(float(np.median(onsets)), 0),
            'median_peak_min': round(float(np.median(peaks)), 0) if peaks else None,
            'median_duration_min': round(float(np.median(durations)), 0) if durations else None,
            'mean_onset_min': round(float(np.mean(onsets)), 0),
            'onset_std': round(float(np.std(onsets)), 0),
            'responder_type': 'fast' if np.median(onsets) < 20 else 'slow' if np.median(onsets) > 40 else 'medium',
        }
        print(f"  {name}: onset={np.median(onsets):.0f}min, peak={np.median(peaks):.0f}min, "
              f"dur={np.median(durations):.0f}min → {results[name]['responder_type']}")
    return results


def exp_2356_circadian_pk(patients):
    """Circadian PK variation."""
    results = {}
    for pat in patients:
        name = pat['name']
        events = find_correction_boluses(pat['df'])
        
        if len(events) < 10:
            results[name] = {'skipped': True}
            continue
        
        # Split by time period
        periods = {'morning': (6, 12), 'afternoon': (12, 18), 'evening': (18, 24), 'night': (0, 6)}
        by_period = {}
        
        for period, (start, end) in periods.items():
            period_events = [e for e in events if start <= e['hour'] < end]
            if len(period_events) < 3:
                continue
            
            drops = []
            nadirs = []
            for ev in period_events:
                post = np.array(ev['post_bg'])
                drop = ev['pre_bg'] - np.nanmin(post)
                nadir_idx = np.nanargmin(post)
                drops.append(drop / ev['bolus'] if ev['bolus'] > 0 else 0)
                nadirs.append(nadir_idx * STEP_MIN)
            
            by_period[period] = {
                'n': len(period_events),
                'mean_drop_per_unit': round(float(np.mean(drops)), 1),
                'mean_nadir_min': round(float(np.mean(nadirs)), 0),
            }
        
        if len(by_period) < 2:
            results[name] = {'skipped': True}
            continue
        
        # Circadian ratio
        drops_by_period = [v['mean_drop_per_unit'] for v in by_period.values()]
        pk_range = max(drops_by_period) / (min(drops_by_period) + 1e-8) if drops_by_period else 1
        
        results[name] = {
            'by_period': by_period,
            'pk_range': round(float(pk_range), 1),
            'most_effective_period': max(by_period.items(), key=lambda x: x[1]['mean_drop_per_unit'])[0],
        }
        print(f"  {name}: PK range {pk_range:.1f}×, most effective={results[name]['most_effective_period']}")
    return results


def exp_2357_stacking_risk(patients):
    """Stacking risk from PK mismatch."""
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        iob = df['iob'].values if 'iob' in df.columns else None
        bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(len(df))
        bg = df['glucose'].values
        
        if iob is None or np.all(np.isnan(iob)):
            results[name] = {'skipped': True}
            continue
        
        # Find high-IOB periods that lead to hypo
        high_iob_thresh = np.nanpercentile(iob[~np.isnan(iob)], 90)
        
        high_iob_mask = iob > high_iob_thresh
        n_high_iob = high_iob_mask.sum()
        
        # Of high IOB periods, how many lead to hypo within 2h?
        hypo_after_high_iob = 0
        for i in range(len(df) - 24):
            if high_iob_mask[i]:
                future_bg = bg[i:i+24]
                if np.any(future_bg < 70):
                    hypo_after_high_iob += 1
        
        hypo_rate = hypo_after_high_iob / max(1, n_high_iob)
        
        # Compare with low IOB
        low_iob_mask = (~np.isnan(iob)) & (iob < np.nanpercentile(iob[~np.isnan(iob)], 25))
        hypo_after_low_iob = 0
        for i in range(len(df) - 24):
            if low_iob_mask[i]:
                future_bg = bg[i:i+24]
                if np.any(future_bg < 70):
                    hypo_after_low_iob += 1
        
        low_hypo_rate = hypo_after_low_iob / max(1, low_iob_mask.sum())
        
        results[name] = {
            'high_iob_threshold': round(float(high_iob_thresh), 2),
            'n_high_iob_steps': int(n_high_iob),
            'hypo_rate_high_iob': round(float(hypo_rate) * 100, 1),
            'hypo_rate_low_iob': round(float(low_hypo_rate) * 100, 1),
            'risk_ratio': round(float(hypo_rate / max(low_hypo_rate, 0.001)), 1),
        }
        print(f"  {name}: high-IOB hypo={hypo_rate*100:.0f}% vs low={low_hypo_rate*100:.0f}%, "
              f"RR={results[name]['risk_ratio']:.1f}")
    return results


def exp_2358_recommendations(patients, all_results):
    """PK-informed dosing recommendations."""
    results = {}
    for pat in patients:
        name = pat['name']
        
        correction = all_results.get('exp_2351', {}).get(name, {})
        timing = all_results.get('exp_2352', {}).get(name, {})
        iob_decay = all_results.get('exp_2353', {}).get(name, {})
        dia = all_results.get('exp_2354', {}).get(name, {})
        onset = all_results.get('exp_2355', {}).get(name, {})
        circadian = all_results.get('exp_2356', {}).get(name, {})
        stacking = all_results.get('exp_2357', {}).get(name, {})
        
        recommendations = []
        
        # DIA adjustment
        if not dia.get('skipped'):
            effective = dia.get('median_dia_hours', 5)
            if effective > 6:
                recommendations.append(f'Increase DIA to {effective:.0f}h (currently 5h)')
            elif effective < 4:
                recommendations.append(f'Decrease DIA to {effective:.0f}h (currently 5h)')
        
        # Responder type
        if not onset.get('skipped'):
            resp_type = onset.get('responder_type', 'medium')
            if resp_type == 'fast':
                recommendations.append('Fast responder — shorter pre-bolus needed')
            elif resp_type == 'slow':
                recommendations.append('Slow responder — consider 15-20 min pre-bolus')
        
        # Circadian PK
        if not circadian.get('skipped'):
            pk_range = circadian.get('pk_range', 1)
            if pk_range > 2:
                most = circadian.get('most_effective_period', '?')
                recommendations.append(f'PK varies {pk_range:.1f}× — most effective at {most}')
        
        # Stacking risk
        if not stacking.get('skipped'):
            rr = stacking.get('risk_ratio', 1)
            if rr > 3:
                recommendations.append(f'HIGH stacking risk (RR={rr:.1f}) — space doses further')
        
        # ISF ratio
        if not correction.get('skipped'):
            isf_ratio = correction.get('isf_ratio', 1)
            if isf_ratio > 1.3:
                recommendations.append(f'ISF appears {isf_ratio:.1f}× higher than set — increase ISF setting')
            elif isf_ratio < 0.7:
                recommendations.append(f'ISF appears {isf_ratio:.1f}× lower than set — decrease ISF setting')
        
        results[name] = {
            'n_recommendations': len(recommendations),
            'recommendations': recommendations,
            'responder_type': onset.get('responder_type', 'unknown') if not onset.get('skipped') else 'unknown',
            'effective_dia': dia.get('median_dia_hours') if not dia.get('skipped') else None,
            'isf_ratio': correction.get('isf_ratio') if not correction.get('skipped') else None,
        }
        print(f"  {name}: {len(recommendations)} recs, "
              f"type={results[name]['responder_type']}, "
              f"DIA={results[name]['effective_dia']}")
    return results


# ── Figures ──────────────────────────────────────────────────────────────

def generate_figures(results, patients, fig_dir):
    os.makedirs(fig_dir, exist_ok=True)
    names = sorted([p['name'] for p in patients])
    
    # Fig 1: Correction curves — drop per unit and time to nadir
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
    r2351 = results['exp_2351']
    active = [n for n in names if not r2351.get(n, {}).get('skipped')]
    
    drops = [r2351[n].get('mean_drop_per_unit', 0) for n in active]
    isfs = [r2351[n].get('profile_isf', 50) for n in active]
    nadirs = [r2351[n].get('median_time_to_nadir', 0) for n in active]
    
    x = np.arange(len(active))
    ax1.bar(x - 0.2, drops, 0.35, color='steelblue', alpha=0.7, label='Effective ISF')
    ax1.bar(x + 0.2, isfs, 0.35, color='lightcoral', alpha=0.7, label='Profile ISF')
    ax1.set_xticks(x); ax1.set_xticklabels(active)
    ax1.set_ylabel('mg/dL per Unit'); ax1.legend()
    ax1.set_title('Effective vs Profile ISF')
    
    ax2.bar(x, nadirs, color='teal', alpha=0.7)
    ax2.set_xticks(x); ax2.set_xticklabels(active)
    ax2.set_ylabel('Minutes'); ax2.set_title('Time to Nadir (min)')
    
    fig.suptitle('EXP-2351: Correction Bolus Response', fontsize=14, fontweight='bold')
    plt.tight_layout(); plt.savefig(f'{fig_dir}/pk-fig01-correction.png', dpi=150, bbox_inches='tight'); plt.close()
    print("  Figure 1: correction")
    
    # Fig 2: Meal timing
    fig, ax = plt.subplots(figsize=(12, 5))
    r2352 = results['exp_2352']
    active_t = [n for n in names if not r2352.get(n, {}).get('skipped')]
    pre_pct = [r2352[n].get('pct_pre_bolus', 0) for n in active_t]
    ax.bar(range(len(active_t)), pre_pct, color='green', alpha=0.7)
    ax.set_xticks(range(len(active_t))); ax.set_xticklabels(active_t)
    ax.set_ylabel('% Meals with Pre-Bolus')
    ax.set_title('EXP-2352: Pre-Bolus Frequency', fontsize=14, fontweight='bold')
    plt.tight_layout(); plt.savefig(f'{fig_dir}/pk-fig02-timing.png', dpi=150, bbox_inches='tight'); plt.close()
    print("  Figure 2: timing")
    
    # Fig 3: IOB decay — DIA estimates
    fig, ax = plt.subplots(figsize=(12, 5))
    r2353 = results['exp_2353']
    active_d = [n for n in names if not r2353.get(n, {}).get('skipped')]
    dias = [r2353[n].get('mean_dia_hours', 5) for n in active_d]
    halfs = [r2353[n].get('median_half_life_min', 0) for n in active_d]
    
    x = np.arange(len(active_d))
    ax.bar(x - 0.2, dias, 0.35, color='purple', alpha=0.7, label='DIA (hours)')
    ax2 = ax.twinx()
    ax2.bar(x + 0.2, halfs, 0.35, color='orange', alpha=0.7, label='Half-life (min)')
    ax.axhline(5, color='red', ls='--', alpha=0.3, label='Profile DIA (5h)')
    ax.set_xticks(x); ax.set_xticklabels(active_d)
    ax.set_ylabel('DIA (hours)', color='purple')
    ax2.set_ylabel('Half-life (min)', color='orange')
    ax.legend(loc='upper left'); ax2.legend(loc='upper right')
    ax.set_title('EXP-2353: IOB Decay — DIA & Half-Life', fontsize=14, fontweight='bold')
    plt.tight_layout(); plt.savefig(f'{fig_dir}/pk-fig03-decay.png', dpi=150, bbox_inches='tight'); plt.close()
    print("  Figure 3: decay")
    
    # Fig 4: DIA from glucose response
    fig, ax = plt.subplots(figsize=(12, 5))
    r2354 = results['exp_2354']
    active_g = [n for n in names if not r2354.get(n, {}).get('skipped')]
    dia_g = [r2354[n].get('median_dia_hours', 5) for n in active_g]
    r2_g = [r2354[n].get('mean_r2', 0) for n in active_g]
    
    x = np.arange(len(active_g))
    bars = ax.bar(x, dia_g, color='steelblue', alpha=0.7)
    ax.axhline(5, color='red', ls='--', alpha=0.3, label='Profile DIA=5h')
    for i, r2 in enumerate(r2_g):
        ax.text(i, dia_g[i] + 0.2, f'R²={r2:.2f}', ha='center', fontsize=8)
    ax.set_xticks(x); ax.set_xticklabels(active_g)
    ax.set_ylabel('Effective DIA (hours)'); ax.legend()
    ax.set_title('EXP-2354: DIA from Glucose Response Curves', fontsize=14, fontweight='bold')
    plt.tight_layout(); plt.savefig(f'{fig_dir}/pk-fig04-dia.png', dpi=150, bbox_inches='tight'); plt.close()
    print("  Figure 4: DIA")
    
    # Fig 5: Onset/peak/duration
    fig, ax = plt.subplots(figsize=(14, 6))
    r2355 = results['exp_2355']
    active_o = [n for n in names if not r2355.get(n, {}).get('skipped')]
    
    onset = [r2355[n].get('median_onset_min', 0) for n in active_o]
    peak = [r2355[n].get('median_peak_min', 0) for n in active_o]
    dur = [r2355[n].get('median_duration_min', 0) for n in active_o]
    
    x = np.arange(len(active_o))
    ax.bar(x - 0.25, onset, 0.25, color='green', alpha=0.7, label='Onset')
    ax.bar(x, peak, 0.25, color='orange', alpha=0.7, label='Peak Effect')
    ax.bar(x + 0.25, dur, 0.25, color='red', alpha=0.7, label='Duration')
    
    for i, n in enumerate(active_o):
        rtype = r2355[n].get('responder_type', '?')
        ax.text(i, max(onset[i], peak[i], dur[i]) + 5, rtype, ha='center', fontsize=8, fontweight='bold')
    
    ax.set_xticks(x); ax.set_xticklabels(active_o)
    ax.set_ylabel('Minutes'); ax.legend()
    ax.set_title('EXP-2355: Insulin Onset / Peak / Duration', fontsize=14, fontweight='bold')
    plt.tight_layout(); plt.savefig(f'{fig_dir}/pk-fig05-onset.png', dpi=150, bbox_inches='tight'); plt.close()
    print("  Figure 5: onset")
    
    # Fig 6: Circadian PK
    fig, ax = plt.subplots(figsize=(12, 6))
    r2356 = results['exp_2356']
    active_c = [n for n in names if not r2356.get(n, {}).get('skipped')]
    periods = ['morning', 'afternoon', 'evening', 'night']
    
    for idx, n in enumerate(active_c[:6]):
        data = r2356[n].get('by_period', {})
        vals = [data.get(p, {}).get('mean_drop_per_unit', np.nan) for p in periods]
        ax.plot(range(4), vals, 'o-', label=n, alpha=0.7)
    
    ax.set_xticks(range(4)); ax.set_xticklabels(periods)
    ax.set_ylabel('Drop per Unit (mg/dL/U)'); ax.legend()
    ax.set_title('EXP-2356: Circadian Insulin Effectiveness', fontsize=14, fontweight='bold')
    plt.tight_layout(); plt.savefig(f'{fig_dir}/pk-fig06-circadian.png', dpi=150, bbox_inches='tight'); plt.close()
    print("  Figure 6: circadian")
    
    # Fig 7: Stacking risk
    fig, ax = plt.subplots(figsize=(12, 5))
    r2357 = results['exp_2357']
    active_s = [n for n in names if not r2357.get(n, {}).get('skipped')]
    rr = [r2357[n].get('risk_ratio', 1) for n in active_s]
    
    colors = ['red' if r > 3 else 'orange' if r > 2 else 'green' for r in rr]
    ax.bar(range(len(active_s)), rr, color=colors, alpha=0.7)
    ax.axhline(1, color='gray', ls='--', alpha=0.3, label='No excess risk')
    ax.axhline(3, color='red', ls='--', alpha=0.3, label='High risk threshold')
    ax.set_xticks(range(len(active_s))); ax.set_xticklabels(active_s)
    ax.set_ylabel('Relative Risk'); ax.legend()
    ax.set_title('EXP-2357: Hypo Risk Ratio (High IOB vs Low IOB)', fontsize=14, fontweight='bold')
    plt.tight_layout(); plt.savefig(f'{fig_dir}/pk-fig07-stacking.png', dpi=150, bbox_inches='tight'); plt.close()
    print("  Figure 7: stacking")
    
    # Fig 8: Summary dashboard
    fig, ax = plt.subplots(figsize=(14, 6))
    r2358 = results['exp_2358']
    active_r = [n for n in names if r2358.get(n, {}).get('effective_dia') is not None]
    
    data = []
    for n in active_r:
        d = r2358[n]
        data.append([
            d.get('effective_dia', 5),
            d.get('isf_ratio', 1),
        ])
    
    if data:
        data = np.array(data)
        scatter = ax.scatter(data[:, 0], data[:, 1], s=200, c='steelblue', alpha=0.7, edgecolors='black')
        for i, n in enumerate(active_r):
            rtype = r2358[n].get('responder_type', '?')
            ax.annotate(f'{n} ({rtype})', (data[i, 0], data[i, 1]),
                       fontsize=10, ha='center', va='bottom')
        ax.axhline(1, color='gray', ls='--', alpha=0.3, label='ISF ratio = 1.0')
        ax.axvline(5, color='red', ls='--', alpha=0.3, label='Profile DIA = 5h')
        ax.set_xlabel('Effective DIA (hours)'); ax.set_ylabel('ISF Ratio (effective/profile)')
        ax.legend()
    
    ax.set_title('EXP-2358: PK Summary — DIA vs ISF Ratio', fontsize=14, fontweight='bold')
    plt.tight_layout(); plt.savefig(f'{fig_dir}/pk-fig08-summary.png', dpi=150, bbox_inches='tight'); plt.close()
    print("  Figure 8: summary")


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
        ('exp_2351', 'Correction Curves', lambda: exp_2351_correction_curves(patients)),
        ('exp_2352', 'Meal Timing', lambda: exp_2352_meal_timing(patients)),
        ('exp_2353', 'IOB Decay', lambda: exp_2353_iob_decay(patients)),
        ('exp_2354', 'DIA Estimation', lambda: exp_2354_dia_estimation(patients)),
        ('exp_2355', 'Onset/Peak/Duration', lambda: exp_2355_onset_peak_duration(patients)),
        ('exp_2356', 'Circadian PK', lambda: exp_2356_circadian_pk(patients)),
        ('exp_2357', 'Stacking Risk', lambda: exp_2357_stacking_risk(patients)),
    ]:
        print(f"Running {exp_id}: {exp_name}...")
        results[exp_id] = exp_fn()
        print(f"  ✓ completed\n")

    print("Running exp_2358: Recommendations...")
    results['exp_2358'] = exp_2358_recommendations(patients, results)
    print("  ✓ completed\n")

    out_path = 'externals/experiments/exp-2351-2358_insulin_pk.json'
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
