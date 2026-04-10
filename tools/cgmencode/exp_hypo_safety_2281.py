#!/usr/bin/env python3
"""
EXP-2281 through EXP-2288: Hypoglycemia Prevention & Safety Profiling

Characterizes hypo events, identifies risk factors, and quantifies
preventable hypos through settings optimization.

Experiments:
  2281: Hypo event characterization (timing, duration, nadir, recovery)
  2282: Circadian hypo risk (time-of-day distribution)
  2283: Pre-hypo glucose patterns (1-3h before hypo onset)
  2284: Insulin context (bolus proximity, basal state at hypo)
  2285: Recovery & rebound dynamics (post-hypo hyperglycemia)
  2286: Risk factor identification (settings vs patterns)
  2287: Preventable hypo estimation
  2288: Per-patient safety scorecard

Usage:
  PYTHONPATH=tools python3 tools/cgmencode/exp_hypo_safety_2281.py --figures
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

from cgmencode.exp_metabolic_441 import load_patients

STEPS_PER_HOUR = 12
STEPS_PER_DAY = 288
HYPO_THRESHOLD = 70  # mg/dL
SEVERE_HYPO = 54     # mg/dL
TARGET_LOW = 70
TARGET_HIGH = 180

def hour_of_day(df):
    idx = pd.to_datetime(df.index) if not isinstance(df.index, pd.DatetimeIndex) else df.index
    return idx.hour

# ── Hypo event detection ─────────────────────────────────────────────────

def detect_hypo_events(bg, hours, min_gap_steps=6):
    """Detect hypoglycemic events from continuous glucose data.
    Returns list of event dicts with onset, nadir, recovery info.
    Events separated by ≥30 min above threshold are distinct."""
    events = []
    in_hypo = False
    onset_idx = None
    nadir_bg = None
    nadir_idx = None

    for i in range(len(bg)):
        if np.isnan(bg[i]):
            continue
        if bg[i] < HYPO_THRESHOLD:
            if not in_hypo:
                in_hypo = True
                onset_idx = i
                nadir_bg = bg[i]
                nadir_idx = i
            else:
                if bg[i] < nadir_bg:
                    nadir_bg = bg[i]
                    nadir_idx = i
        else:
            if in_hypo:
                # Check if this is a genuine recovery (above threshold for min_gap_steps)
                above_count = 0
                for j in range(i, min(i + min_gap_steps, len(bg))):
                    if np.isnan(bg[j]) or bg[j] >= HYPO_THRESHOLD:
                        above_count += 1
                if above_count >= min_gap_steps // 2:
                    # Event ended
                    recovery_idx = i
                    duration_steps = recovery_idx - onset_idx
                    duration_min = duration_steps * 5

                    # Pre-hypo glucose (1h, 2h, 3h before)
                    pre_1h = bg[max(0, onset_idx - 12)] if onset_idx >= 12 and not np.isnan(bg[max(0, onset_idx - 12)]) else None
                    pre_2h = bg[max(0, onset_idx - 24)] if onset_idx >= 24 and not np.isnan(bg[max(0, onset_idx - 24)]) else None
                    pre_3h = bg[max(0, onset_idx - 36)] if onset_idx >= 36 and not np.isnan(bg[max(0, onset_idx - 36)]) else None

                    # Post-hypo glucose (1h, 2h, 3h after recovery)
                    post_1h = bg[min(len(bg)-1, recovery_idx + 12)] if recovery_idx + 12 < len(bg) and not np.isnan(bg[min(len(bg)-1, recovery_idx + 12)]) else None
                    post_2h = bg[min(len(bg)-1, recovery_idx + 24)] if recovery_idx + 24 < len(bg) and not np.isnan(bg[min(len(bg)-1, recovery_idx + 24)]) else None
                    post_3h = bg[min(len(bg)-1, recovery_idx + 36)] if recovery_idx + 36 < len(bg) and not np.isnan(bg[min(len(bg)-1, recovery_idx + 36)]) else None

                    # Rate of decline (mg/dL per 5min) in 30min before onset
                    pre_window = bg[max(0, onset_idx-6):onset_idx+1]
                    valid_pre = pre_window[~np.isnan(pre_window)]
                    rate_of_decline = float((valid_pre[-1] - valid_pre[0]) / max(1, len(valid_pre)-1)) if len(valid_pre) >= 2 else None

                    events.append({
                        'onset_idx': int(onset_idx),
                        'nadir_idx': int(nadir_idx),
                        'recovery_idx': int(recovery_idx),
                        'onset_hour': int(hours[onset_idx]),
                        'nadir_bg': float(nadir_bg),
                        'onset_bg': float(bg[onset_idx]),
                        'duration_min': int(duration_min),
                        'is_severe': nadir_bg < SEVERE_HYPO,
                        'pre_1h_bg': float(pre_1h) if pre_1h is not None else None,
                        'pre_2h_bg': float(pre_2h) if pre_2h is not None else None,
                        'pre_3h_bg': float(pre_3h) if pre_3h is not None else None,
                        'post_1h_bg': float(post_1h) if post_1h is not None else None,
                        'post_2h_bg': float(post_2h) if post_2h is not None else None,
                        'post_3h_bg': float(post_3h) if post_3h is not None else None,
                        'rate_of_decline': rate_of_decline,
                    })
                    in_hypo = False

    # Handle event still in progress at end
    if in_hypo and onset_idx is not None:
        events.append({
            'onset_idx': int(onset_idx),
            'nadir_idx': int(nadir_idx),
            'recovery_idx': int(len(bg) - 1),
            'onset_hour': int(hours[onset_idx]),
            'nadir_bg': float(nadir_bg),
            'onset_bg': float(bg[onset_idx]),
            'duration_min': int((len(bg) - 1 - onset_idx) * 5),
            'is_severe': nadir_bg < SEVERE_HYPO,
            'pre_1h_bg': None, 'pre_2h_bg': None, 'pre_3h_bg': None,
            'post_1h_bg': None, 'post_2h_bg': None, 'post_3h_bg': None,
            'rate_of_decline': None,
        })
    return events


# ── Experiments ──────────────────────────────────────────────────────────

def exp_2281_characterization(patients):
    """Hypo event characterization."""
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        bg_col = 'bg' if 'bg' in df.columns else 'glucose'
        bg = df[bg_col].values
        hours = hour_of_day(df)
        n_days = len(bg) / STEPS_PER_DAY

        events = detect_hypo_events(bg, hours)
        n_events = len(events)
        events_per_day = n_events / n_days if n_days > 0 else 0

        durations = [e['duration_min'] for e in events]
        nadirs = [e['nadir_bg'] for e in events]
        severe = [e for e in events if e['is_severe']]

        # TBR (time below range)
        valid_bg = bg[~np.isnan(bg)]
        tbr = float(np.mean(valid_bg < HYPO_THRESHOLD) * 100) if len(valid_bg) > 0 else 0
        tbr_severe = float(np.mean(valid_bg < SEVERE_HYPO) * 100) if len(valid_bg) > 0 else 0

        results[name] = {
            'n_events': n_events,
            'events_per_day': round(events_per_day, 2),
            'n_severe': len(severe),
            'severe_per_day': round(len(severe) / n_days, 3) if n_days > 0 else 0,
            'median_duration_min': float(np.median(durations)) if durations else 0,
            'mean_duration_min': float(np.mean(durations)) if durations else 0,
            'max_duration_min': int(max(durations)) if durations else 0,
            'median_nadir': float(np.median(nadirs)) if nadirs else None,
            'min_nadir': float(min(nadirs)) if nadirs else None,
            'tbr_pct': tbr,
            'tbr_severe_pct': tbr_severe,
            'n_days': round(n_days, 1),
        }
        print(f"  {name}: {n_events} events ({events_per_day:.1f}/day), {len(severe)} severe, median_dur={np.median(durations):.0f}min, TBR={tbr:.1f}%" if events else f"  {name}: 0 events")
    return results


def exp_2282_circadian_risk(patients):
    """Circadian hypo risk: when do hypos happen?"""
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        bg_col = 'bg' if 'bg' in df.columns else 'glucose'
        bg = df[bg_col].values
        hours = hour_of_day(df)

        events = detect_hypo_events(bg, hours)

        # Hourly distribution
        hourly_counts = {h: 0 for h in range(24)}
        for e in events:
            hourly_counts[e['onset_hour']] += 1

        total = sum(hourly_counts.values())
        hourly_pct = {str(h): round(c / total * 100, 1) if total > 0 else 0 for h, c in hourly_counts.items()}

        # Peak risk hours (top 3)
        sorted_hours = sorted(hourly_counts.items(), key=lambda x: x[1], reverse=True)
        peak_hours = [h for h, c in sorted_hours[:3] if c > 0]

        # Day vs night
        day_events = sum(hourly_counts[h] for h in range(7, 22))
        night_events = sum(hourly_counts[h] for h in list(range(0, 7)) + [22, 23])
        day_night_ratio = day_events / night_events if night_events > 0 else float('inf')

        # Hourly TBR
        hourly_tbr = {}
        for h in range(24):
            mask = (hours == h) & ~np.isnan(bg)
            if mask.sum() > 0:
                hourly_tbr[str(h)] = float(np.mean(bg[mask] < HYPO_THRESHOLD) * 100)

        results[name] = {
            'hourly_counts': {str(h): c for h, c in hourly_counts.items()},
            'hourly_pct': hourly_pct,
            'peak_hours': peak_hours,
            'day_events': day_events,
            'night_events': night_events,
            'day_night_ratio': round(day_night_ratio, 2),
            'hourly_tbr': hourly_tbr,
            'total_events': total,
        }
        print(f"  {name}: peaks at hours {peak_hours}, day/night={day_night_ratio:.1f}×")
    return results


def exp_2283_pre_hypo_patterns(patients):
    """Pre-hypo glucose patterns: what happens 1-3h before hypo onset?"""
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        bg_col = 'bg' if 'bg' in df.columns else 'glucose'
        bg = df[bg_col].values
        hours = hour_of_day(df)

        events = detect_hypo_events(bg, hours)
        if not events:
            results[name] = {'n_events': 0, 'skipped': True}
            continue

        # Collect pre-hypo trajectories (3h = 36 steps before onset)
        trajectories = []
        for e in events:
            onset = e['onset_idx']
            if onset >= 36:
                traj = bg[onset-36:onset+1]
                if np.sum(~np.isnan(traj)) >= 18:  # at least 50% valid
                    trajectories.append(traj)

        if not trajectories:
            results[name] = {'n_events': len(events), 'n_trajectories': 0, 'skipped': True}
            continue

        traj_array = np.array(trajectories)
        # Mean trajectory
        mean_traj = np.nanmean(traj_array, axis=0)
        std_traj = np.nanstd(traj_array, axis=0)

        # Starting glucose (3h before)
        start_bgs = [t[0] for t in trajectories if not np.isnan(t[0])]
        # Rate of decline (per 5min step, averaged over last 30 min)
        rates = []
        for t in trajectories:
            last_30 = t[-7:]  # last 30 min
            valid = last_30[~np.isnan(last_30)]
            if len(valid) >= 2:
                rates.append(float((valid[-1] - valid[0]) / (len(valid) - 1)))

        # Classify pre-hypo patterns
        # Fast drop: starts high, drops rapidly
        # Slow drift: starts near threshold, drifts down
        # Already low: starts below 100
        fast_drops = sum(1 for s in start_bgs if s > 120)
        slow_drifts = sum(1 for s in start_bgs if 90 <= s <= 120)
        already_low = sum(1 for s in start_bgs if s < 90)

        results[name] = {
            'n_events': len(events),
            'n_trajectories': len(trajectories),
            'mean_trajectory': [float(v) if not np.isnan(v) else None for v in mean_traj],
            'std_trajectory': [float(v) if not np.isnan(v) else None for v in std_traj],
            'mean_start_bg': float(np.mean(start_bgs)) if start_bgs else None,
            'median_start_bg': float(np.median(start_bgs)) if start_bgs else None,
            'mean_rate_decline': float(np.mean(rates)) if rates else None,
            'fast_drops_pct': round(fast_drops / len(start_bgs) * 100, 1) if start_bgs else 0,
            'slow_drifts_pct': round(slow_drifts / len(start_bgs) * 100, 1) if start_bgs else 0,
            'already_low_pct': round(already_low / len(start_bgs) * 100, 1) if start_bgs else 0,
        }
        print(f"  {name}: {len(trajectories)} trajectories, start={np.median(start_bgs):.0f} mg/dL, fast={fast_drops}/{len(start_bgs)}, slow={slow_drifts}/{len(start_bgs)}")
    return results


def exp_2284_insulin_context(patients):
    """Insulin context at hypo: was there a recent bolus? High basal?"""
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        bg_col = 'bg' if 'bg' in df.columns else 'glucose'
        bg = df[bg_col].values
        hours = hour_of_day(df)
        bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(len(bg))
        carbs = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(bg))

        events = detect_hypo_events(bg, hours)
        if not events:
            results[name] = {'n_events': 0, 'skipped': True}
            continue

        # For each event, check insulin context
        bolus_associated = 0  # bolus within 3h before
        carb_associated = 0   # carbs within 3h before
        no_context = 0        # no bolus or carbs
        bolus_sizes = []
        carb_sizes = []

        for e in events:
            onset = e['onset_idx']
            # Look back 3h (36 steps) for bolus
            lookback = max(0, onset - 36)
            recent_bolus = np.nansum(bolus[lookback:onset+1])
            recent_carbs = np.nansum(carbs[lookback:onset+1])

            has_bolus = recent_bolus > 0.1
            has_carbs = recent_carbs > 1.0

            if has_bolus:
                bolus_associated += 1
                bolus_sizes.append(float(recent_bolus))
            if has_carbs:
                carb_associated += 1
                carb_sizes.append(float(recent_carbs))
            if not has_bolus and not has_carbs:
                no_context += 1

        n = len(events)
        results[name] = {
            'n_events': n,
            'bolus_associated_pct': round(bolus_associated / n * 100, 1) if n > 0 else 0,
            'carb_associated_pct': round(carb_associated / n * 100, 1) if n > 0 else 0,
            'no_context_pct': round(no_context / n * 100, 1) if n > 0 else 0,
            'mean_preceding_bolus': float(np.mean(bolus_sizes)) if bolus_sizes else 0,
            'mean_preceding_carbs': float(np.mean(carb_sizes)) if carb_sizes else 0,
            'bolus_associated': bolus_associated,
            'carb_associated': carb_associated,
            'no_context': no_context,
        }
        print(f"  {name}: bolus-assoc={bolus_associated}/{n} ({bolus_associated/n*100:.0f}%), no-context={no_context}/{n} ({no_context/n*100:.0f}%)" if n > 0 else f"  {name}: 0 events")
    return results


def exp_2285_recovery(patients):
    """Recovery & rebound dynamics after hypo events."""
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        bg_col = 'bg' if 'bg' in df.columns else 'glucose'
        bg = df[bg_col].values
        hours = hour_of_day(df)

        events = detect_hypo_events(bg, hours)
        if not events:
            results[name] = {'n_events': 0, 'skipped': True}
            continue

        # Post-hypo recovery analysis
        rebound_hyper = 0  # glucose > 180 within 3h of recovery
        recovery_times = []  # time from nadir to first >100 mg/dL
        post_trajectories = []
        max_post_bgs = []

        for e in events:
            recovery = e['recovery_idx']
            # Post-recovery trajectory (3h = 36 steps)
            if recovery + 36 < len(bg):
                post = bg[recovery:recovery+37]
                if np.sum(~np.isnan(post)) >= 18:
                    post_trajectories.append(post)
                    max_post = np.nanmax(post)
                    max_post_bgs.append(float(max_post))
                    if max_post > 180:
                        rebound_hyper += 1

            # Recovery time: nadir to first >100
            nadir_idx = e['nadir_idx']
            for j in range(nadir_idx, min(nadir_idx + 72, len(bg))):  # up to 6h
                if not np.isnan(bg[j]) and bg[j] >= 100:
                    recovery_times.append((j - nadir_idx) * 5)  # in minutes
                    break

        n = len(events)
        n_with_post = len(post_trajectories)
        mean_post_traj = np.nanmean(post_trajectories, axis=0).tolist() if post_trajectories else []

        results[name] = {
            'n_events': n,
            'rebound_hyper_pct': round(rebound_hyper / n_with_post * 100, 1) if n_with_post > 0 else 0,
            'rebound_hyper_count': rebound_hyper,
            'mean_max_post_bg': float(np.mean(max_post_bgs)) if max_post_bgs else None,
            'median_recovery_time_min': float(np.median(recovery_times)) if recovery_times else None,
            'mean_recovery_time_min': float(np.mean(recovery_times)) if recovery_times else None,
            'mean_post_trajectory': [float(v) if not np.isnan(v) else None for v in mean_post_traj] if mean_post_traj else [],
            'n_with_recovery_data': n_with_post,
        }
        print(f"  {name}: rebound_hyper={rebound_hyper}/{n_with_post} ({rebound_hyper/n_with_post*100:.0f}%), recovery={np.median(recovery_times):.0f}min" if n_with_post > 0 and recovery_times else f"  {name}: {n} events, limited recovery data")
    return results


def exp_2286_risk_factors(patients):
    """Risk factor identification: what predicts hypo events?"""
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        bg_col = 'bg' if 'bg' in df.columns else 'glucose'
        bg = df[bg_col].values
        hours = hour_of_day(df)
        bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(len(bg))
        carbs = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(bg))
        n_days = len(bg) / STEPS_PER_DAY

        events = detect_hypo_events(bg, hours)

        # Daily risk factors
        daily_hypos = np.zeros(int(n_days))
        daily_mean_bg = np.full(int(n_days), np.nan)
        daily_bolus_total = np.zeros(int(n_days))
        daily_carbs_total = np.zeros(int(n_days))
        daily_bg_std = np.full(int(n_days), np.nan)

        for d in range(int(n_days)):
            s = d * STEPS_PER_DAY
            e_idx = s + STEPS_PER_DAY
            day_bg = bg[s:e_idx]
            valid = day_bg[~np.isnan(day_bg)]
            if len(valid) > 0:
                daily_mean_bg[d] = np.mean(valid)
                daily_bg_std[d] = np.std(valid)
            daily_bolus_total[d] = np.nansum(bolus[s:e_idx])
            daily_carbs_total[d] = np.nansum(carbs[s:e_idx])

        for event in events:
            day = event['onset_idx'] // STEPS_PER_DAY
            if day < int(n_days):
                daily_hypos[day] += 1

        # Correlate risk factors with hypo occurrence
        valid_days = ~np.isnan(daily_mean_bg)
        risk_factors = {}

        if valid_days.sum() > 10:
            hypo_days = daily_hypos[valid_days] > 0
            no_hypo_days = ~hypo_days

            # Mean BG on hypo vs non-hypo days
            if hypo_days.sum() > 0 and no_hypo_days.sum() > 0:
                risk_factors['mean_bg_hypo_days'] = float(np.mean(daily_mean_bg[valid_days][hypo_days]))
                risk_factors['mean_bg_no_hypo_days'] = float(np.mean(daily_mean_bg[valid_days][no_hypo_days]))
                risk_factors['bg_std_hypo_days'] = float(np.mean(daily_bg_std[valid_days][hypo_days]))
                risk_factors['bg_std_no_hypo_days'] = float(np.mean(daily_bg_std[valid_days][no_hypo_days]))
                risk_factors['bolus_hypo_days'] = float(np.mean(daily_bolus_total[valid_days][hypo_days]))
                risk_factors['bolus_no_hypo_days'] = float(np.mean(daily_bolus_total[valid_days][no_hypo_days]))
                risk_factors['carbs_hypo_days'] = float(np.mean(daily_carbs_total[valid_days][hypo_days]))
                risk_factors['carbs_no_hypo_days'] = float(np.mean(daily_carbs_total[valid_days][no_hypo_days]))

        results[name] = {
            'n_events': len(events),
            'n_days_with_hypo': int(np.sum(daily_hypos > 0)),
            'pct_days_with_hypo': round(np.mean(daily_hypos > 0) * 100, 1),
            'risk_factors': risk_factors,
        }
        hypo_pct = np.mean(daily_hypos > 0) * 100
        print(f"  {name}: {np.sum(daily_hypos > 0):.0f}/{int(n_days)} days with hypo ({hypo_pct:.0f}%)")
    return results


def exp_2287_preventable(patients):
    """Estimate preventable hypos through settings correction."""
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        bg_col = 'bg' if 'bg' in df.columns else 'glucose'
        bg = df[bg_col].values
        hours = hour_of_day(df)

        events = detect_hypo_events(bg, hours)
        if not events:
            results[name] = {'n_events': 0, 'preventable': 0}
            continue

        # A hypo is "preventable" if:
        # 1. The pre-hypo BG was in range (>100) 2h before (controllable trajectory)
        # 2. The rate of decline was moderate (not a crash from very high)
        # These hypos likely result from excess insulin delivery that could be
        # reduced by correct settings.
        preventable = 0
        fast_crash = 0
        already_marginal = 0

        for e in events:
            pre_2h = e.get('pre_2h_bg')
            rate = e.get('rate_of_decline')

            if pre_2h is not None and pre_2h > 100:
                # Started in good range but dropped — settings issue
                preventable += 1
            elif pre_2h is not None and pre_2h <= 100:
                # Was already marginal — harder to prevent
                already_marginal += 1
            elif rate is not None and rate < -3:
                # Fast crash (>3 mg/dL per 5min = 36 mg/dL/h)
                fast_crash += 1
            else:
                already_marginal += 1

        # Simulate basal reduction effect on hypos
        # If we reduce basal by 10%, how many hypo events would be avoided?
        # Rough model: 10% basal reduction ≈ 5-10 mg/dL glucose rise over 4h
        bg_shift_10pct = 8  # mg/dL estimated rise from 10% basal reduction
        corrected_events = 0
        for e in events:
            # Would this event still happen if glucose was bg_shift higher?
            if e['nadir_bg'] + bg_shift_10pct >= HYPO_THRESHOLD:
                corrected_events += 1

        n = len(events)
        results[name] = {
            'n_events': n,
            'preventable': preventable,
            'preventable_pct': round(preventable / n * 100, 1) if n > 0 else 0,
            'fast_crash': fast_crash,
            'already_marginal': already_marginal,
            'corrected_by_10pct_basal': corrected_events,
            'corrected_pct': round(corrected_events / n * 100, 1) if n > 0 else 0,
        }
        print(f"  {name}: {preventable}/{n} preventable ({preventable/n*100:.0f}%), {corrected_events}/{n} corrected by 10% basal reduction" if n > 0 else f"  {name}: 0 events")
    return results


def exp_2288_scorecard(patients, all_results):
    """Per-patient safety scorecard combining all findings."""
    results = {}
    for pat in patients:
        name = pat['name']

        r2281 = all_results.get('exp_2281', {}).get(name, {})
        r2282 = all_results.get('exp_2282', {}).get(name, {})
        r2283 = all_results.get('exp_2283', {}).get(name, {})
        r2284 = all_results.get('exp_2284', {}).get(name, {})
        r2285 = all_results.get('exp_2285', {}).get(name, {})
        r2286 = all_results.get('exp_2286', {}).get(name, {})
        r2287 = all_results.get('exp_2287', {}).get(name, {})

        # Safety score components (0-100, lower is better/safer)
        # Frequency score: hypos per day (0=none, 100=3+/day)
        freq = min(100, r2281.get('events_per_day', 0) / 3 * 100)
        # Severity score: fraction severe
        sev_frac = r2281.get('n_severe', 0) / max(1, r2281.get('n_events', 1))
        severity = sev_frac * 100
        # Duration score: median duration (0=0min, 100=120min+)
        dur = min(100, r2281.get('median_duration_min', 0) / 120 * 100)
        # Rebound score: rebound hyperglycemia percentage
        rebound = r2285.get('rebound_hyper_pct', 0)
        # Nocturnal risk: fraction of events at night
        night_frac = r2282.get('night_events', 0) / max(1, r2282.get('total_events', 1))
        nocturnal = night_frac * 100
        # Preventability
        prev = 100 - r2287.get('preventable_pct', 0)  # higher = less preventable = worse

        # Composite safety score (weighted)
        composite = (
            freq * 0.25 +
            severity * 0.25 +
            dur * 0.15 +
            rebound * 0.10 +
            nocturnal * 0.15 +
            prev * 0.10
        )

        # Risk tier
        if composite < 20:
            tier = 'LOW'
        elif composite < 40:
            tier = 'MODERATE'
        elif composite < 60:
            tier = 'HIGH'
        else:
            tier = 'CRITICAL'

        results[name] = {
            'frequency_score': round(freq, 1),
            'severity_score': round(severity, 1),
            'duration_score': round(dur, 1),
            'rebound_score': round(rebound, 1),
            'nocturnal_score': round(nocturnal, 1),
            'preventability_score': round(prev, 1),
            'composite_score': round(composite, 1),
            'risk_tier': tier,
            'summary': {
                'events_per_day': r2281.get('events_per_day', 0),
                'pct_severe': round(sev_frac * 100, 1),
                'pct_preventable': r2287.get('preventable_pct', 0),
                'pct_rebound_hyper': r2285.get('rebound_hyper_pct', 0),
                'pct_nocturnal': round(night_frac * 100, 1),
                'tbr': r2281.get('tbr_pct', 0),
            }
        }
        print(f"  {name}: {tier} (score={composite:.0f}) | {r2281.get('events_per_day',0):.1f}/day, {sev_frac*100:.0f}% severe, {r2287.get('preventable_pct',0):.0f}% preventable")
    return results


# ── Figures ──────────────────────────────────────────────────────────────

def generate_figures(results, fig_dir):
    os.makedirs(fig_dir, exist_ok=True)

    # Fig 1: Hypo event overview
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    r = results['exp_2281']
    names = sorted(r.keys())
    x = np.arange(len(names))

    # Events per day
    ax = axes[0]
    vals = [r[n]['events_per_day'] for n in names]
    colors = ['red' if v > 1 else 'orange' if v > 0.5 else 'green' for v in vals]
    ax.bar(x, vals, color=colors, alpha=0.7)
    ax.set_xticks(x); ax.set_xticklabels(names)
    ax.set_ylabel('Hypos / Day'); ax.set_title('Hypo Frequency')

    # Duration
    ax = axes[1]
    vals = [r[n]['median_duration_min'] for n in names]
    ax.bar(x, vals, color='steelblue', alpha=0.7)
    ax.set_xticks(x); ax.set_xticklabels(names)
    ax.set_ylabel('Minutes'); ax.set_title('Median Duration')

    # TBR
    ax = axes[2]
    tbr = [r[n]['tbr_pct'] for n in names]
    tbr_sev = [r[n]['tbr_severe_pct'] for n in names]
    ax.bar(x, tbr, color='orange', alpha=0.7, label='<70 mg/dL')
    ax.bar(x, tbr_sev, color='red', alpha=0.7, label='<54 mg/dL')
    ax.set_xticks(x); ax.set_xticklabels(names)
    ax.set_ylabel('% Time'); ax.set_title('Time Below Range')
    ax.legend()

    fig.suptitle('EXP-2281: Hypoglycemia Event Characterization', fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(f'{fig_dir}/hypo-fig01-characterization.png', dpi=150, bbox_inches='tight')
    plt.close()
    print("  Figure 1: characterization")

    # Fig 2: Circadian risk
    fig, axes = plt.subplots(3, 4, figsize=(16, 10))
    axes = axes.flatten()
    r2282 = results['exp_2282']
    for idx, name in enumerate(sorted(r2282.keys())):
        if idx >= 11: break
        ax = axes[idx]
        counts = r2282[name]['hourly_counts']
        hours_list = sorted([int(h) for h in counts.keys()])
        vals = [counts[str(h)] for h in hours_list]
        colors = ['navy' if h < 7 or h >= 22 else 'steelblue' for h in hours_list]
        ax.bar(hours_list, vals, color=colors, alpha=0.7)
        ax.set_title(f"{name} ({r2282[name]['total_events']} events)")
        ax.set_xlim(-0.5, 23.5)
        ax.set_xlabel('Hour'); ax.set_ylabel('Count')
    axes[-1].axis('off')
    fig.suptitle('EXP-2282: Hypo Events by Hour of Day (dark=nighttime)', fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(f'{fig_dir}/hypo-fig02-circadian-risk.png', dpi=150, bbox_inches='tight')
    plt.close()
    print("  Figure 2: circadian risk")

    # Fig 3: Pre-hypo patterns
    fig, axes = plt.subplots(3, 4, figsize=(16, 10))
    axes = axes.flatten()
    r2283 = results['exp_2283']
    time_axis = np.arange(-180, 5, 5)  # -180 to 0 minutes
    for idx, name in enumerate(sorted(r2283.keys())):
        if idx >= 11: break
        ax = axes[idx]
        data = r2283[name]
        if data.get('skipped'):
            ax.text(0.5, 0.5, f'{name}\nskipped', ha='center', va='center', transform=ax.transAxes)
            ax.set_title(name); continue
        traj = data['mean_trajectory']
        std = data.get('std_trajectory', [0]*len(traj))
        t = time_axis[:len(traj)]
        traj_v = [v for v in traj if v is not None]
        std_v = [s for s in std if s is not None]
        if len(traj_v) == len(t):
            ax.plot(t, traj_v, 'b-', lw=2)
            ax.fill_between(t, np.array(traj_v) - np.array(std_v), np.array(traj_v) + np.array(std_v), alpha=0.2)
        ax.axhline(70, color='red', ls='--', alpha=0.5)
        ax.axhline(100, color='orange', ls=':', alpha=0.5)
        ax.set_title(f"{name} (n={data['n_trajectories']})")
        ax.set_xlabel('Min before hypo'); ax.set_ylabel('BG (mg/dL)')
    axes[-1].axis('off')
    fig.suptitle('EXP-2283: Mean Pre-Hypo Glucose Trajectory (3h before onset)', fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(f'{fig_dir}/hypo-fig03-pre-hypo-patterns.png', dpi=150, bbox_inches='tight')
    plt.close()
    print("  Figure 3: pre-hypo patterns")

    # Fig 4: Insulin context
    fig, ax = plt.subplots(figsize=(12, 5))
    r2284 = results['exp_2284']
    names_list = sorted(r2284.keys())
    x = np.arange(len(names_list))
    bolus_pct = [r2284[n].get('bolus_associated_pct', 0) for n in names_list]
    no_ctx_pct = [r2284[n].get('no_context_pct', 0) for n in names_list]
    carb_pct = [r2284[n].get('carb_associated_pct', 0) for n in names_list]
    # Normalize: show only bolus vs no-context split
    ax.bar(x, bolus_pct, label='Bolus-associated', color='red', alpha=0.7)
    ax.bar(x, no_ctx_pct, bottom=bolus_pct, label='No preceding bolus/carbs', color='gray', alpha=0.7)
    ax.set_xticks(x); ax.set_xticklabels(names_list)
    ax.set_ylabel('% of Hypo Events'); ax.legend()
    ax.set_title('EXP-2284: Insulin Context at Hypo Events\n(Red = bolus within 3h, gray = no bolus/carbs)')
    plt.tight_layout()
    plt.savefig(f'{fig_dir}/hypo-fig04-insulin-context.png', dpi=150, bbox_inches='tight')
    plt.close()
    print("  Figure 4: insulin context")

    # Fig 5: Recovery dynamics
    fig, axes = plt.subplots(3, 4, figsize=(16, 10))
    axes = axes.flatten()
    r2285 = results['exp_2285']
    for idx, name in enumerate(sorted(r2285.keys())):
        if idx >= 11: break
        ax = axes[idx]
        data = r2285[name]
        if data.get('skipped') or not data.get('mean_post_trajectory'):
            ax.text(0.5, 0.5, f'{name}\n{data.get("n_events",0)} events', ha='center', va='center', transform=ax.transAxes)
            ax.set_title(name); continue
        traj = data['mean_post_trajectory']
        t = np.arange(0, len(traj) * 5, 5)
        vals = [v for v in traj if v is not None]
        if vals:
            ax.plot(t[:len(vals)], vals, 'b-', lw=2)
            ax.axhline(70, color='red', ls='--', alpha=0.5)
            ax.axhline(180, color='orange', ls='--', alpha=0.5)
            ax.set_title(f"{name}: rebound={data['rebound_hyper_pct']:.0f}%")
        ax.set_xlabel('Min after recovery'); ax.set_ylabel('BG (mg/dL)')
    axes[-1].axis('off')
    fig.suptitle('EXP-2285: Mean Post-Hypo Recovery Trajectory (3h after)\nOrange line = 180 mg/dL hyperglycemia threshold', fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(f'{fig_dir}/hypo-fig05-recovery.png', dpi=150, bbox_inches='tight')
    plt.close()
    print("  Figure 5: recovery")

    # Fig 6: Risk factors
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    r2286 = results['exp_2286']
    names_with_data = [n for n in sorted(r2286.keys()) if r2286[n].get('risk_factors')]
    if names_with_data:
        x = np.arange(len(names_with_data))
        ax = axes[0]
        hypo_bg = [r2286[n]['risk_factors'].get('mean_bg_hypo_days', 0) for n in names_with_data]
        no_hypo_bg = [r2286[n]['risk_factors'].get('mean_bg_no_hypo_days', 0) for n in names_with_data]
        w = 0.35
        ax.bar(x - w/2, hypo_bg, w, label='Hypo days', color='red', alpha=0.7)
        ax.bar(x + w/2, no_hypo_bg, w, label='Non-hypo days', color='green', alpha=0.7)
        ax.set_xticks(x); ax.set_xticklabels(names_with_data)
        ax.set_ylabel('Mean BG (mg/dL)'); ax.legend()
        ax.set_title('Mean BG: Hypo vs Non-Hypo Days')

        ax = axes[1]
        hypo_bolus = [r2286[n]['risk_factors'].get('bolus_hypo_days', 0) for n in names_with_data]
        no_hypo_bolus = [r2286[n]['risk_factors'].get('bolus_no_hypo_days', 0) for n in names_with_data]
        ax.bar(x - w/2, hypo_bolus, w, label='Hypo days', color='red', alpha=0.7)
        ax.bar(x + w/2, no_hypo_bolus, w, label='Non-hypo days', color='green', alpha=0.7)
        ax.set_xticks(x); ax.set_xticklabels(names_with_data)
        ax.set_ylabel('Total Bolus (U)'); ax.legend()
        ax.set_title('Daily Bolus: Hypo vs Non-Hypo Days')
    fig.suptitle('EXP-2286: Risk Factors for Hypoglycemia Days', fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(f'{fig_dir}/hypo-fig06-risk-factors.png', dpi=150, bbox_inches='tight')
    plt.close()
    print("  Figure 6: risk factors")

    # Fig 7: Preventable hypos
    fig, ax = plt.subplots(figsize=(12, 5))
    r2287 = results['exp_2287']
    names_list = sorted(r2287.keys())
    x = np.arange(len(names_list))
    total = [r2287[n]['n_events'] for n in names_list]
    prevent = [r2287[n]['preventable'] for n in names_list]
    corrected = [r2287[n].get('corrected_by_10pct_basal', 0) for n in names_list]
    w = 0.25
    ax.bar(x - w, total, w, label='Total events', color='gray', alpha=0.7)
    ax.bar(x, prevent, w, label='Preventable (started >100)', color='orange', alpha=0.7)
    ax.bar(x + w, corrected, w, label='Fixed by 10% basal ↓', color='green', alpha=0.7)
    ax.set_xticks(x); ax.set_xticklabels(names_list)
    ax.set_ylabel('Events'); ax.legend()
    ax.set_title('EXP-2287: Preventable Hypoglycemia Events')
    plt.tight_layout()
    plt.savefig(f'{fig_dir}/hypo-fig07-preventable.png', dpi=150, bbox_inches='tight')
    plt.close()
    print("  Figure 7: preventable")

    # Fig 8: Safety scorecard
    fig, ax = plt.subplots(figsize=(14, 6))
    r2288 = results['exp_2288']
    names_list = sorted(r2288.keys())
    categories = ['frequency_score', 'severity_score', 'duration_score', 'rebound_score', 'nocturnal_score']
    cat_labels = ['Frequency', 'Severity', 'Duration', 'Rebound', 'Nocturnal']
    x = np.arange(len(names_list))
    bottoms = np.zeros(len(names_list))
    colors_list = ['#e74c3c', '#e67e22', '#f1c40f', '#3498db', '#2c3e50']
    for cat, label, color in zip(categories, cat_labels, colors_list):
        vals = [r2288[n][cat] * 0.25 for n in names_list]  # scale for visibility
        ax.bar(x, vals, bottom=bottoms, label=label, color=color, alpha=0.7)
        bottoms += vals
    # Add composite score text
    for i, n in enumerate(names_list):
        score = r2288[n]['composite_score']
        tier = r2288[n]['risk_tier']
        ax.text(i, bottoms[i] + 1, f'{tier}\n{score:.0f}', ha='center', va='bottom', fontsize=8, fontweight='bold')
    ax.set_xticks(x); ax.set_xticklabels(names_list)
    ax.set_ylabel('Risk Score (weighted)'); ax.legend(loc='upper right')
    ax.set_title('EXP-2288: Hypoglycemia Safety Scorecard')
    plt.tight_layout()
    plt.savefig(f'{fig_dir}/hypo-fig08-scorecard.png', dpi=150, bbox_inches='tight')
    plt.close()
    print("  Figure 8: scorecard")


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Hypo Safety Profiling (EXP-2281–2288)')
    parser.add_argument('--figures', action='store_true')
    args = parser.parse_args()

    print("Loading patients...")
    patients = load_patients('externals/ns-data/patients/')
    for p in patients:
        print(f"  Loaded {p['name']}: {len(p['df'])} steps")
    print(f"Loaded {len(patients)} patients\n")

    results = {}
    experiments = [
        ('exp_2281', 'Hypo Event Characterization', lambda p: exp_2281_characterization(p)),
        ('exp_2282', 'Circadian Hypo Risk', lambda p: exp_2282_circadian_risk(p)),
        ('exp_2283', 'Pre-Hypo Patterns', lambda p: exp_2283_pre_hypo_patterns(p)),
        ('exp_2284', 'Insulin Context', lambda p: exp_2284_insulin_context(p)),
        ('exp_2285', 'Recovery & Rebound', lambda p: exp_2285_recovery(p)),
        ('exp_2286', 'Risk Factors', lambda p: exp_2286_risk_factors(p)),
        ('exp_2287', 'Preventable Hypos', lambda p: exp_2287_preventable(p)),
    ]

    for exp_id, title, func in experiments:
        print(f"Running {exp_id}: {title}...")
        results[exp_id] = func(patients)
        print(f"  ✓ completed")

    # EXP-2288 needs all prior results
    print(f"Running exp_2288: Safety Scorecard...")
    results['exp_2288'] = exp_2288_scorecard(patients, results)
    print(f"  ✓ completed")

    # Save
    out_path = 'externals/experiments/exp-2281-2288_hypo_safety.json'
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    def convert(obj):
        if isinstance(obj, (np.integer,)): return int(obj)
        if isinstance(obj, (np.floating,)): return float(obj)
        if isinstance(obj, np.ndarray): return obj.tolist()
        if isinstance(obj, (np.bool_,)): return bool(obj)
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2, default=convert)
    print(f"\nResults saved to {out_path}")

    if args.figures:
        print(f"\nGenerating figures...")
        generate_figures(results, 'docs/60-research/figures')
        print("All figures generated.")


if __name__ == '__main__':
    main()
