#!/usr/bin/env python3
"""
EXP-2071–2078: Therapy Settings Optimization

Since prediction is fundamentally limited (EXP-2061), the highest-impact
path is computing better therapy settings. Uses circadian ISF (EXP-2051),
basal drift (EXP-2052), counter-regulatory data (EXP-2057), overcorrection
rates (EXP-2044), and meal response (EXP-2031) to compute optimal settings.

EXP-2071: Optimal ISF schedule (hour-by-hour from correction events)
EXP-2072: Optimal CR schedule (from meal spike/insulin relationship)
EXP-2073: Optimal basal schedule (from fasting drift inversion)
EXP-2074: Settings validation (simulate TIR improvement with optimized settings)
EXP-2075: Overcorrection prevention (ISF adjustment to eliminate hypos)
EXP-2076: Dawn protocol optimization (basal ramp to prevent dawn rise)
EXP-2077: Dinner-specific settings (separate dinner CR/ISF)
EXP-2078: Synthesis — complete optimized therapy profile per patient

Depends on: exp_metabolic_441.py
"""

import json
import sys
import os
import numpy as np
import warnings
warnings.filterwarnings('ignore')

from exp_metabolic_441 import load_patients, compute_supply_demand


class NumpyEncoder(json.JSONEncoder):
    """Handle numpy types in JSON serialization."""
    def default(self, obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)

PATIENT_DIR = 'externals/ns-data/patients/'
FIG_DIR = 'docs/60-research/figures'
EXP_DIR = 'externals/experiments'
MAKE_FIGS = '--figures' in sys.argv

if MAKE_FIGS:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    os.makedirs(FIG_DIR, exist_ok=True)

os.makedirs(EXP_DIR, exist_ok=True)

STEPS_PER_HOUR = 12
STEPS_PER_DAY = 288
HYPO_THRESH = 70
TARGET_LOW = 70
TARGET_HIGH = 180
TARGET_MID = 110  # optimal target glucose


patients = load_patients(PATIENT_DIR)


def get_profile_isf(df, hour):
    """Get profile ISF for a given hour, converting mmol if needed."""
    schedule = df.attrs.get('isf_schedule', [])
    if not schedule:
        return None
    # Schedule is list of {time, value, timeAsSeconds} dicts
    sorted_sched = sorted(schedule, key=lambda x: x.get('timeAsSeconds', 0))
    applicable = None
    for entry in sorted_sched:
        time_str = entry.get('time', '00:00')
        val = entry.get('value')
        h, m = map(int, time_str.split(':'))
        sched_hour = h + m / 60
        if sched_hour <= hour:
            applicable = val
    if applicable is None:
        applicable = sorted_sched[0].get('value')
    if applicable is None:
        return None
    # Convert mmol/L to mg/dL if needed
    if applicable < 15:
        applicable *= 18.0182
    return applicable


def get_profile_cr(df, hour):
    """Get profile CR for a given hour."""
    schedule = df.attrs.get('cr_schedule', [])
    if not schedule:
        return None
    sorted_sched = sorted(schedule, key=lambda x: x.get('timeAsSeconds', 0))
    applicable = None
    for entry in sorted_sched:
        time_str = entry.get('time', '00:00')
        val = entry.get('value')
        h, m = map(int, time_str.split(':'))
        sched_hour = h + m / 60
        if sched_hour <= hour:
            applicable = val
    if applicable is None:
        applicable = sorted_sched[0].get('value')
    return applicable


def get_profile_basal(df, hour):
    """Get profile basal rate for a given hour."""
    schedule = df.attrs.get('basal_schedule', [])
    if not schedule:
        return None
    sorted_sched = sorted(schedule, key=lambda x: x.get('timeAsSeconds', 0))
    applicable = None
    for entry in sorted_sched:
        time_str = entry.get('time', '00:00')
        val = entry.get('value')
        h, m = map(int, time_str.split(':'))
        sched_hour = h + m / 60
        if sched_hour <= hour:
            applicable = val
    if applicable is None:
        applicable = sorted_sched[0].get('value')
    return applicable


# ── EXP-2071: Optimal ISF Schedule ──────────────────────────────────
def exp_2071_optimal_isf():
    """Compute hour-by-hour optimal ISF from correction outcomes."""
    print("\n═══ EXP-2071: Optimal ISF Schedule ═══")

    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        bolus = df['bolus'].values
        carbs = df['carbs'].values

        # Collect correction events with outcomes
        hourly_isf = {h: [] for h in range(24)}

        for i in range(STEPS_PER_HOUR, len(g) - 4 * STEPS_PER_HOUR):
            if bolus[i] < 0.3 or np.isnan(g[i]) or g[i] < 130:
                continue
            # No carbs ±1h
            cw = carbs[max(0, i - STEPS_PER_HOUR):i + STEPS_PER_HOUR]
            if np.nansum(cw) > 1:
                continue

            # Track glucose response over 4h
            future = g[i:i + 4 * STEPS_PER_HOUR]
            valid = ~np.isnan(future)
            if valid.sum() < STEPS_PER_HOUR:
                continue

            delta_g = g[i] - np.nanmin(future)
            if delta_g < 5:
                continue

            isf_obs = delta_g / bolus[i]
            if isf_obs < 5 or isf_obs > 400:
                continue

            hour = (i % STEPS_PER_DAY) // STEPS_PER_HOUR
            hourly_isf[hour].append(isf_obs)

        # Compute optimal ISF schedule (use median of observed)
        optimal_schedule = {}
        profile_schedule = {}
        for h in range(24):
            if len(hourly_isf[h]) >= 3:
                optimal_schedule[h] = float(np.median(hourly_isf[h]))
            profile_isf = get_profile_isf(df, h)
            if profile_isf:
                profile_schedule[h] = float(profile_isf)

        # Compute mismatch
        mismatches = []
        for h in optimal_schedule:
            if h in profile_schedule and profile_schedule[h] > 0:
                ratio = optimal_schedule[h] / profile_schedule[h]
                mismatches.append(ratio)

        mean_ratio = float(np.mean(mismatches)) if mismatches else None
        max_ratio = float(np.max(mismatches)) if mismatches else None
        min_ratio = float(np.min(mismatches)) if mismatches else None

        results[name] = {
            'optimal_schedule': optimal_schedule,
            'profile_schedule': profile_schedule,
            'hours_with_data': len(optimal_schedule),
            'mean_ratio': round(mean_ratio, 2) if mean_ratio else None,
            'max_ratio': round(max_ratio, 2) if max_ratio else None,
            'min_ratio': round(min_ratio, 2) if min_ratio else None,
            'total_corrections': sum(len(v) for v in hourly_isf.values())
        }
        print(f"  {name}: {len(optimal_schedule)} hours, ratio={mean_ratio:.2f}×"
              if mean_ratio else f"  {name}: {len(optimal_schedule)} hours")

    if MAKE_FIGS:
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))

        # Top-left: population optimal vs profile ISF by hour
        ax = axes[0, 0]
        all_optimal = {h: [] for h in range(24)}
        all_profile = {h: [] for h in range(24)}
        for r in results.values():
            for h, v in r.get('optimal_schedule', {}).items():
                all_optimal[int(h)].append(v)
            for h, v in r.get('profile_schedule', {}).items():
                all_profile[int(h)].append(v)

        hours = range(24)
        opt_med = [np.median(all_optimal[h]) if all_optimal[h] else np.nan for h in hours]
        prof_med = [np.median(all_profile[h]) if all_profile[h] else np.nan for h in hours]
        ax.plot(hours, opt_med, 'o-', color='#2ca02c', linewidth=2, label='Optimal (observed)')
        ax.plot(hours, prof_med, 's--', color='#d62728', linewidth=2, label='Profile (programmed)')
        ax.set_xlabel('Hour of Day')
        ax.set_ylabel('ISF (mg/dL per unit)')
        ax.set_title('Population: Optimal vs Profile ISF')
        ax.legend()
        ax.set_xticks(range(0, 24, 3))
        ax.grid(True, alpha=0.3)

        # Top-right: per-patient ratio
        ax = axes[0, 1]
        pnames = sorted([n for n, r in results.items() if r.get('mean_ratio')])
        ratios = [results[n]['mean_ratio'] for n in pnames]
        colors = ['#d62728' if r > 1.5 else '#ff7f0e' if r > 1.2 else '#2ca02c'
                  if r > 0.8 else '#1f77b4' for r in ratios]
        ax.barh(pnames, ratios, color=colors, alpha=0.7)
        ax.axvline(x=1, color='black', linestyle='--', alpha=0.5, label='Perfect match')
        ax.set_xlabel('Optimal/Profile ISF Ratio (>1 = profile too low)')
        ax.set_title('ISF Mismatch by Patient')
        ax.legend()
        ax.grid(True, alpha=0.3, axis='x')

        # Bottom-left: best patient schedule detail
        ax = axes[1, 0]
        best = max(results.items(), key=lambda x: x[1].get('hours_with_data', 0))
        bname, br = best
        if br.get('optimal_schedule'):
            oh = sorted(br['optimal_schedule'].keys(), key=int)
            ov = [br['optimal_schedule'][h] for h in oh]
            pv = [br['profile_schedule'].get(int(h), np.nan) for h in oh]
            ax.plot([int(h) for h in oh], ov, 'o-', color='#2ca02c', label='Optimal')
            ax.plot([int(h) for h in oh], pv, 's--', color='#d62728', label='Profile')
            ax.set_xlabel('Hour of Day')
            ax.set_ylabel('ISF (mg/dL per unit)')
            ax.set_title(f'Patient {bname}: Detailed ISF Schedule')
            ax.legend()
            ax.grid(True, alpha=0.3)

        # Bottom-right: circadian ISF range
        ax = axes[1, 1]
        for n, r in sorted(results.items()):
            if r.get('min_ratio') and r.get('max_ratio'):
                ax.plot([r['min_ratio'], r['max_ratio']], [n, n], 'o-',
                        linewidth=2, markersize=8)
        ax.axvline(x=1, color='black', linestyle='--', alpha=0.5)
        ax.set_xlabel('Optimal/Profile Ratio Range')
        ax.set_title('Within-Day ISF Ratio Spread')
        ax.grid(True, alpha=0.3)

        plt.tight_layout()
        fig.savefig(f'{FIG_DIR}/opt-fig01-isf-schedule.png', dpi=150, bbox_inches='tight')
        plt.close()
        print(f"  → Saved opt-fig01-isf-schedule.png")

    output = {'experiment': 'EXP-2071', 'title': 'Optimal ISF Schedule',
              'per_patient': results}
    with open(f'{EXP_DIR}/exp-2071_optimal_isf.json', 'w') as f:
        json.dump(output, f, indent=2, cls=NumpyEncoder)
    return output


# ── EXP-2072: Optimal CR Schedule ───────────────────────────────────
def exp_2072_optimal_cr():
    """Compute optimal CR from meal spike/insulin relationship."""
    print("\n═══ EXP-2072: Optimal CR Schedule ═══")

    results = {}

    def classify_meal_time(step):
        hour = (step % STEPS_PER_DAY) / STEPS_PER_HOUR
        if 5 <= hour < 10:
            return 'breakfast'
        elif 10 <= hour < 14:
            return 'lunch'
        elif 17 <= hour < 21:
            return 'dinner'
        else:
            return 'snack'

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        carbs = df['carbs'].values
        bolus = df['bolus'].values

        meal_data = {'breakfast': [], 'lunch': [], 'dinner': [], 'snack': []}

        for i in range(len(g) - 3 * STEPS_PER_HOUR):
            if np.isnan(carbs[i]) or carbs[i] < 5 or np.isnan(g[i]):
                continue

            # Total bolus within ±30min
            total_bolus = np.nansum(bolus[max(0, i-6):i+6])
            if total_bolus < 0.1:
                continue

            # Post-meal spike
            future = g[i:i + 3 * STEPS_PER_HOUR]
            valid = ~np.isnan(future)
            if valid.sum() < 6:
                continue

            spike = np.nanmax(future) - g[i]
            # 2h post-meal glucose
            idx_2h = min(i + 2 * STEPS_PER_HOUR, len(g) - 1)
            g_2h = g[idx_2h] if not np.isnan(g[idx_2h]) else np.nan

            # Target: 2h post-meal should be near pre-meal
            if not np.isnan(g_2h):
                overshoot = g_2h - g[i]
            else:
                overshoot = spike * 0.5  # estimate

            # Observed CR: carbs / bolus
            cr_obs = carbs[i] / total_bolus

            # Optimal CR: what CR would have produced target glucose?
            # If overshoot > 0, needed more insulin → lower CR
            # If overshoot < 0, gave too much insulin → higher CR
            if total_bolus > 0 and abs(overshoot) > 5:
                # Extra insulin needed = overshoot / ISF
                profile_isf = get_profile_isf(df, (i % STEPS_PER_DAY) / STEPS_PER_HOUR)
                if profile_isf and profile_isf > 0:
                    extra_insulin = overshoot / profile_isf
                    optimal_bolus = total_bolus + extra_insulin
                    if optimal_bolus > 0:
                        cr_optimal = carbs[i] / optimal_bolus
                    else:
                        cr_optimal = cr_obs
                else:
                    cr_optimal = cr_obs
            else:
                cr_optimal = cr_obs

            if 1 < cr_optimal < 50:
                period = classify_meal_time(i)
                meal_data[period].append({
                    'cr_obs': float(cr_obs),
                    'cr_optimal': float(cr_optimal),
                    'carbs': float(carbs[i]),
                    'spike': float(spike),
                    'overshoot': float(overshoot) if not np.isnan(overshoot) else None
                })

        period_summary = {}
        for period, meals in meal_data.items():
            if len(meals) >= 5:
                cr_obs = [m['cr_obs'] for m in meals]
                cr_opt = [m['cr_optimal'] for m in meals]
                profile_cr = get_profile_cr(df, {'breakfast': 7, 'lunch': 12,
                                                  'dinner': 18, 'snack': 15}[period])
                period_summary[period] = {
                    'n': len(meals),
                    'cr_observed_median': float(np.median(cr_obs)),
                    'cr_optimal_median': float(np.median(cr_opt)),
                    'cr_profile': float(profile_cr) if profile_cr else None,
                    'spike_median': float(np.median([m['spike'] for m in meals])),
                    'overshoot_median': float(np.median([m['overshoot'] for m in meals
                                                         if m['overshoot'] is not None]))
                }

        results[name] = {
            'periods': period_summary,
            'total_meals': sum(len(v) for v in meal_data.values())
        }

        summary_parts = []
        for period in ['breakfast', 'lunch', 'dinner']:
            if period in period_summary:
                ps = period_summary[period]
                opt = ps['cr_optimal_median']
                prof = ps.get('cr_profile')
                ratio_str = f" ({opt/prof:.2f}×)" if prof and prof > 0 else ""
                summary_parts.append(f"{period[:3]}=1:{opt:.0f}{ratio_str}")
        print(f"  {name}: {', '.join(summary_parts)}")

    if MAKE_FIGS:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        # Left: optimal CR by meal time (population)
        ax = axes[0]
        for period, color in [('breakfast', '#ff7f0e'), ('lunch', '#2ca02c'),
                               ('dinner', '#d62728'), ('snack', '#7f7f7f')]:
            opt_crs = []
            prof_crs = []
            for r in results.values():
                ps = r.get('periods', {}).get(period)
                if ps:
                    opt_crs.append(ps['cr_optimal_median'])
                    if ps.get('cr_profile'):
                        prof_crs.append(ps['cr_profile'])

            if opt_crs:
                ax.scatter([period] * len(opt_crs), opt_crs, color=color, alpha=0.5,
                          s=80, label=f'{period} optimal', zorder=3)
            if prof_crs:
                ax.scatter([period] * len(prof_crs), prof_crs, color=color, alpha=0.5,
                          s=80, marker='s', zorder=3)

        ax.set_ylabel('Carb Ratio (g/U)')
        ax.set_title('Optimal CR by Meal Time (circles=optimal, squares=profile)')
        ax.grid(True, alpha=0.3, axis='y')

        # Right: dinner vs breakfast CR ratio
        ax = axes[1]
        pnames = []
        ratios = []
        for n, r in sorted(results.items()):
            ps = r.get('periods', {})
            if 'breakfast' in ps and 'dinner' in ps:
                bk = ps['breakfast']['cr_optimal_median']
                dn = ps['dinner']['cr_optimal_median']
                if bk > 0:
                    pnames.append(n)
                    ratios.append(dn / bk)

        if pnames:
            colors = ['#d62728' if r < 0.7 else '#ff7f0e' if r < 0.9 else '#2ca02c' for r in ratios]
            ax.barh(pnames, ratios, color=colors, alpha=0.7)
            ax.axvline(x=1, color='black', linestyle='--', alpha=0.5, label='Same as breakfast')
            ax.set_xlabel('Dinner/Breakfast CR Ratio (<1 = needs more insulin at dinner)')
            ax.set_title('Dinner CR Adjustment Needed')
            ax.legend()
            ax.grid(True, alpha=0.3, axis='x')

        plt.tight_layout()
        fig.savefig(f'{FIG_DIR}/opt-fig02-cr-schedule.png', dpi=150, bbox_inches='tight')
        plt.close()
        print(f"  → Saved opt-fig02-cr-schedule.png")

    output = {'experiment': 'EXP-2072', 'title': 'Optimal CR Schedule',
              'per_patient': results}
    with open(f'{EXP_DIR}/exp-2072_optimal_cr.json', 'w') as f:
        json.dump(output, f, indent=2, cls=NumpyEncoder)
    return output


# ── EXP-2073: Optimal Basal Schedule ────────────────────────────────
def exp_2073_optimal_basal():
    """Compute optimal basal from fasting drift inversion."""
    print("\n═══ EXP-2073: Optimal Basal Schedule ═══")

    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        carbs = df['carbs'].values
        bolus = df['bolus'].values

        hourly_drift = {h: [] for h in range(24)}

        # Find fasting windows: no carbs or bolus ±2h, glucose in range
        for i in range(2 * STEPS_PER_HOUR, len(g) - STEPS_PER_HOUR):
            if np.isnan(g[i]) or g[i] < 80 or g[i] > 180:
                continue

            window = slice(max(0, i - 2*STEPS_PER_HOUR), i + 2*STEPS_PER_HOUR)
            if np.nansum(carbs[window]) > 0 or np.nansum(bolus[window]) > 0.5:
                continue

            if i + STEPS_PER_HOUR < len(g) and not np.isnan(g[i + STEPS_PER_HOUR]):
                drift = g[i + STEPS_PER_HOUR] - g[i]
                if abs(drift) < 80:
                    hour = (i % STEPS_PER_DAY) // STEPS_PER_HOUR
                    hourly_drift[hour].append(drift)

        # Compute optimal basal adjustment
        optimal_adjustment = {}
        profile_basal = {}
        for h in range(24):
            if len(hourly_drift[h]) >= 10:
                median_drift = float(np.median(hourly_drift[h]))
                current_basal = get_profile_basal(df, h)

                if current_basal and current_basal > 0:
                    profile_basal[h] = float(current_basal)
                    # If glucose is drifting UP (+), need MORE basal
                    # If drifting DOWN (-), need LESS basal
                    # Assume ISF ~50 mg/dL/U as rough scale
                    profile_isf = get_profile_isf(df, h) or 50
                    basal_correction = median_drift / profile_isf  # U/hr adjustment
                    optimal_rate = current_basal + basal_correction
                    optimal_rate = max(0, optimal_rate)  # can't go negative

                    optimal_adjustment[h] = {
                        'drift': round(median_drift, 1),
                        'current_basal': round(current_basal, 3),
                        'optimal_basal': round(optimal_rate, 3),
                        'change_pct': round((optimal_rate - current_basal) / current_basal * 100, 1)
                                      if current_basal > 0 else 0,
                        'n': len(hourly_drift[h])
                    }

        # Overall assessment
        changes = [v['change_pct'] for v in optimal_adjustment.values()]
        mean_change = float(np.mean(changes)) if changes else 0
        max_increase = max(changes) if changes else 0
        max_decrease = min(changes) if changes else 0

        results[name] = {
            'hourly': optimal_adjustment,
            'hours_analyzed': len(optimal_adjustment),
            'mean_change_pct': round(mean_change, 1),
            'max_increase_pct': round(max_increase, 1),
            'max_decrease_pct': round(max_decrease, 1),
            'needs_increase_hours': sum(1 for v in optimal_adjustment.values() if v['change_pct'] > 5),
            'needs_decrease_hours': sum(1 for v in optimal_adjustment.values() if v['change_pct'] < -5)
        }
        print(f"  {name}: mean={mean_change:+.0f}%, "
              f"↑{results[name]['needs_increase_hours']}h, ↓{results[name]['needs_decrease_hours']}h")

    if MAKE_FIGS:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        # Left: population drift and adjustment
        ax = axes[0]
        all_drift = {h: [] for h in range(24)}
        all_change = {h: [] for h in range(24)}
        for r in results.values():
            for h, v in r.get('hourly', {}).items():
                all_drift[int(h)].append(v['drift'])
                all_change[int(h)].append(v['change_pct'])

        hours = range(24)
        drifts = [np.median(all_drift[h]) if all_drift[h] else 0 for h in hours]
        changes = [np.median(all_change[h]) if all_change[h] else 0 for h in hours]
        colors = ['#d62728' if d > 3 else '#2ca02c' if d < -3 else '#7f7f7f' for d in drifts]

        ax.bar(hours, drifts, color=colors, alpha=0.7)
        ax.axhline(y=0, color='black', linewidth=1)
        ax.set_xlabel('Hour of Day')
        ax.set_ylabel('Fasting Drift (mg/dL/hr)')
        ax.set_title('Population: Glucose Drift → Basal Adjustment Needed')
        ax.set_xticks(range(0, 24, 3))
        ax.grid(True, alpha=0.3)

        # Right: per-patient basal adequacy
        ax = axes[1]
        pnames = sorted(results.keys())
        inc = [results[n]['needs_increase_hours'] for n in pnames]
        dec = [results[n]['needs_decrease_hours'] for n in pnames]
        x = np.arange(len(pnames))
        ax.barh(x - 0.2, inc, 0.35, label='Need increase', color='#d62728', alpha=0.7)
        ax.barh(x + 0.2, dec, 0.35, label='Need decrease', color='#2ca02c', alpha=0.7)
        ax.set_yticks(x)
        ax.set_yticklabels(pnames)
        ax.set_xlabel('Hours needing adjustment')
        ax.set_title('Basal Schedule Adjustment Hours')
        ax.legend()
        ax.grid(True, alpha=0.3, axis='x')

        plt.tight_layout()
        fig.savefig(f'{FIG_DIR}/opt-fig03-basal-schedule.png', dpi=150, bbox_inches='tight')
        plt.close()
        print(f"  → Saved opt-fig03-basal-schedule.png")

    output = {'experiment': 'EXP-2073', 'title': 'Optimal Basal Schedule',
              'per_patient': results}
    with open(f'{EXP_DIR}/exp-2073_optimal_basal.json', 'w') as f:
        json.dump(output, f, indent=2, cls=NumpyEncoder)
    return output


# ── EXP-2074: Settings Validation (Simulated TIR) ───────────────────
def exp_2074_settings_validation():
    """Estimate TIR improvement if optimal settings were applied."""
    print("\n═══ EXP-2074: Settings Validation ═══")

    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        iob = df['iob'].values

        # Current TIR
        valid = ~np.isnan(g)
        current_tir = float(np.mean((g[valid] >= TARGET_LOW) & (g[valid] <= TARGET_HIGH)))
        current_tbr = float(np.mean(g[valid] < TARGET_LOW))
        current_tar = float(np.mean(g[valid] > TARGET_HIGH))

        # Estimate TIR improvement from fixing overcorrections
        overcorrection_events = 0
        preventable_hypo_time = 0
        for i in range(STEPS_PER_HOUR, len(g) - 4 * STEPS_PER_HOUR):
            if bolus[i] < 0.3 or np.isnan(g[i]) or g[i] < 130:
                continue
            cw = carbs[max(0, i - STEPS_PER_HOUR):i + STEPS_PER_HOUR]
            if np.nansum(cw) > 1:
                continue

            # Check if correction caused hypo
            future = g[i:i + 4 * STEPS_PER_HOUR]
            nadir = np.nanmin(future)
            if nadir < HYPO_THRESH:
                overcorrection_events += 1
                # Count steps below 70
                hypo_steps = np.sum(future[~np.isnan(future)] < HYPO_THRESH)
                preventable_hypo_time += hypo_steps

        # Estimate TIR improvement from fixing post-hypo rebounds
        rebound_hyper_time = 0
        for i in range(len(g) - 4 * STEPS_PER_HOUR):
            if np.isnan(g[i]) or g[i] >= HYPO_THRESH:
                continue
            # Find hypo exit
            for j in range(i+1, min(i + 2*STEPS_PER_HOUR, len(g))):
                if not np.isnan(g[j]) and g[j] >= HYPO_THRESH:
                    # Track rebound
                    post = g[j:j + 4*STEPS_PER_HOUR]
                    rebound_hyper = np.sum(post[~np.isnan(post)] > TARGET_HIGH)
                    rebound_hyper_time += rebound_hyper
                    break

        total_valid = valid.sum()
        # Optimistic scenario: prevent ALL overcorrection hypos + reduce rebounds by 50%
        prevented_tbr_steps = min(preventable_hypo_time, total_valid * current_tbr)
        prevented_tar_steps = rebound_hyper_time * 0.5  # conservative estimate

        optimized_tir = current_tir + (prevented_tbr_steps + prevented_tar_steps) / total_valid
        optimized_tir = min(optimized_tir, 1.0)
        optimized_tbr = max(current_tbr - prevented_tbr_steps / total_valid, 0)
        optimized_tar = max(current_tar - prevented_tar_steps / total_valid, 0)

        improvement = optimized_tir - current_tir

        results[name] = {
            'current_tir': round(current_tir, 3),
            'current_tbr': round(current_tbr, 3),
            'current_tar': round(current_tar, 3),
            'optimized_tir': round(optimized_tir, 3),
            'optimized_tbr': round(optimized_tbr, 3),
            'optimized_tar': round(optimized_tar, 3),
            'improvement_pp': round(improvement * 100, 1),
            'overcorrection_events': overcorrection_events,
            'rebound_hyper_steps': rebound_hyper_time
        }
        print(f"  {name}: TIR {current_tir:.0%}→{optimized_tir:.0%} "
              f"(+{improvement*100:.1f}pp), TBR {current_tbr:.1%}→{optimized_tbr:.1%}")

    # Population
    pop_current = np.mean([r['current_tir'] for r in results.values()])
    pop_optimized = np.mean([r['optimized_tir'] for r in results.values()])
    print(f"\n  Population: TIR {pop_current:.0%}→{pop_optimized:.0%} "
          f"(+{(pop_optimized - pop_current)*100:.1f}pp)")

    if MAKE_FIGS:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        # Left: current vs optimized TIR
        ax = axes[0]
        pnames = sorted(results.keys())
        current = [results[n]['current_tir'] * 100 for n in pnames]
        optimized = [results[n]['optimized_tir'] * 100 for n in pnames]
        x = np.arange(len(pnames))
        ax.barh(x - 0.2, current, 0.35, label='Current', color='#ff7f0e', alpha=0.7)
        ax.barh(x + 0.2, optimized, 0.35, label='Optimized', color='#2ca02c', alpha=0.7)
        ax.axvline(x=70, color='red', linestyle='--', alpha=0.5, label='70% target')
        ax.set_yticks(x)
        ax.set_yticklabels(pnames)
        ax.set_xlabel('TIR (%)')
        ax.set_title('Current vs Optimized TIR')
        ax.legend()
        ax.grid(True, alpha=0.3, axis='x')

        # Right: improvement breakdown
        ax = axes[1]
        improvements = [results[n]['improvement_pp'] for n in pnames]
        colors = ['#2ca02c' if i > 3 else '#ff7f0e' if i > 1 else '#7f7f7f' for i in improvements]
        ax.barh(pnames, improvements, color=colors, alpha=0.7)
        ax.set_xlabel('TIR Improvement (percentage points)')
        ax.set_title('Potential TIR Improvement from Settings Optimization')
        ax.grid(True, alpha=0.3, axis='x')

        plt.tight_layout()
        fig.savefig(f'{FIG_DIR}/opt-fig04-validation.png', dpi=150, bbox_inches='tight')
        plt.close()
        print(f"  → Saved opt-fig04-validation.png")

    output = {'experiment': 'EXP-2074', 'title': 'Settings Validation',
              'per_patient': results,
              'population': {'current_tir': round(pop_current, 3),
                           'optimized_tir': round(pop_optimized, 3)}}
    with open(f'{EXP_DIR}/exp-2074_settings_validation.json', 'w') as f:
        json.dump(output, f, indent=2, cls=NumpyEncoder)
    return output


# ── EXP-2075: Overcorrection Prevention ─────────────────────────────
def exp_2075_overcorrection_prevention():
    """What ISF change would prevent overcorrection hypos?"""
    print("\n═══ EXP-2075: Overcorrection Prevention ═══")

    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        bolus = df['bolus'].values
        carbs = df['carbs'].values

        corrections = []
        overcorrections = []

        for i in range(STEPS_PER_HOUR, len(g) - 4 * STEPS_PER_HOUR):
            if bolus[i] < 0.3 or np.isnan(g[i]) or g[i] < 130:
                continue
            cw = carbs[max(0, i - STEPS_PER_HOUR):i + STEPS_PER_HOUR]
            if np.nansum(cw) > 1:
                continue

            future = g[i:i + 4 * STEPS_PER_HOUR]
            valid_future = ~np.isnan(future)
            if valid_future.sum() < 6:
                continue

            nadir = np.nanmin(future)
            delta = g[i] - nadir
            hour = (i % STEPS_PER_DAY) // STEPS_PER_HOUR
            profile_isf = get_profile_isf(df, hour)

            event = {
                'glucose': float(g[i]),
                'dose': float(bolus[i]),
                'nadir': float(nadir),
                'delta': float(delta),
                'hour': hour,
                'profile_isf': float(profile_isf) if profile_isf else None,
                'observed_isf': float(delta / bolus[i]) if bolus[i] > 0 else None,
                'caused_hypo': nadir < HYPO_THRESH
            }
            corrections.append(event)
            if nadir < HYPO_THRESH:
                overcorrections.append(event)

        if not corrections:
            results[name] = {'n_corrections': 0}
            print(f"  {name}: no corrections")
            continue

        oc_rate = len(overcorrections) / len(corrections)

        # For each overcorrection, compute what ISF would have prevented hypo
        # If nadir was X < 70, needed delta to be (g[i] - 70) instead of (g[i] - nadir)
        safe_isfs = []
        for oc in overcorrections:
            target_delta = oc['glucose'] - HYPO_THRESH  # should have dropped to 70, not below
            safe_isf = target_delta / oc['dose'] if oc['dose'] > 0 else None
            if safe_isf and 5 < safe_isf < 400:
                safe_isfs.append(safe_isf)

        # Compare safe ISF to profile ISF
        if safe_isfs and overcorrections[0].get('profile_isf'):
            profile_isfs = [oc['profile_isf'] for oc in overcorrections if oc.get('profile_isf')]
            if profile_isfs:
                median_safe = np.median(safe_isfs)
                median_profile = np.median(profile_isfs)
                isf_increase_needed = (median_safe / median_profile - 1) * 100
            else:
                isf_increase_needed = None
                median_safe = np.median(safe_isfs)
                median_profile = None
        else:
            isf_increase_needed = None
            median_safe = np.median(safe_isfs) if safe_isfs else None
            median_profile = None

        results[name] = {
            'n_corrections': len(corrections),
            'n_overcorrections': len(overcorrections),
            'overcorrection_rate': round(oc_rate, 3),
            'safe_isf_median': round(median_safe, 1) if median_safe else None,
            'profile_isf_median': round(median_profile, 1) if median_profile else None,
            'isf_increase_needed_pct': round(isf_increase_needed, 1) if isf_increase_needed else None
        }
        print(f"  {name}: {len(overcorrections)}/{len(corrections)} ({oc_rate:.0%}), "
              f"ISF increase needed: {isf_increase_needed:+.0f}%"
              if isf_increase_needed else
              f"  {name}: {len(overcorrections)}/{len(corrections)} ({oc_rate:.0%})")

    if MAKE_FIGS:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        # Left: overcorrection rate vs ISF increase needed
        ax = axes[0]
        pnames = sorted([n for n, r in results.items() if r.get('isf_increase_needed_pct') is not None])
        rates = [results[n]['overcorrection_rate'] * 100 for n in pnames]
        increases = [results[n]['isf_increase_needed_pct'] for n in pnames]
        colors = ['#d62728' if r > 15 else '#ff7f0e' if r > 10 else '#2ca02c' for r in rates]
        ax.scatter(rates, increases, c=colors, s=100, zorder=3)
        for n, r, inc in zip(pnames, rates, increases):
            ax.annotate(n, (r, inc), textcoords="offset points",
                       xytext=(5, 5), fontsize=9)
        ax.set_xlabel('Overcorrection Rate (%)')
        ax.set_ylabel('ISF Increase Needed (%)')
        ax.set_title('Overcorrection Rate vs Required ISF Change')
        ax.grid(True, alpha=0.3)

        # Right: safe ISF vs profile ISF
        ax = axes[1]
        pnames2 = sorted([n for n, r in results.items()
                         if r.get('safe_isf_median') and r.get('profile_isf_median')])
        if pnames2:
            safe = [results[n]['safe_isf_median'] for n in pnames2]
            profile = [results[n]['profile_isf_median'] for n in pnames2]
            x = np.arange(len(pnames2))
            ax.barh(x - 0.2, profile, 0.35, label='Profile ISF', color='#d62728', alpha=0.7)
            ax.barh(x + 0.2, safe, 0.35, label='Safe ISF', color='#2ca02c', alpha=0.7)
            ax.set_yticks(x)
            ax.set_yticklabels(pnames2)
            ax.set_xlabel('ISF (mg/dL per unit)')
            ax.set_title('Profile vs Safe ISF (higher = less aggressive)')
            ax.legend()
            ax.grid(True, alpha=0.3, axis='x')

        plt.tight_layout()
        fig.savefig(f'{FIG_DIR}/opt-fig05-overcorrection.png', dpi=150, bbox_inches='tight')
        plt.close()
        print(f"  → Saved opt-fig05-overcorrection.png")

    output = {'experiment': 'EXP-2075', 'title': 'Overcorrection Prevention',
              'per_patient': results}
    with open(f'{EXP_DIR}/exp-2075_overcorrection.json', 'w') as f:
        json.dump(output, f, indent=2, cls=NumpyEncoder)
    return output


# ── EXP-2076: Dawn Protocol Optimization ────────────────────────────
def exp_2076_dawn_protocol():
    """What basal ramp prevents dawn phenomenon rise?"""
    print("\n═══ EXP-2076: Dawn Protocol Optimization ═══")

    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values

        n_days = len(g) // STEPS_PER_DAY
        dawn_events = []

        for day in range(n_days):
            start = day * STEPS_PER_DAY
            # Night: midnight-4am
            night = g[start:start + 4 * STEPS_PER_HOUR]
            # Dawn: 4am-8am
            dawn = g[start + 4*STEPS_PER_HOUR:start + 8*STEPS_PER_HOUR]

            if start + 8*STEPS_PER_HOUR > len(g):
                break

            night_valid = ~np.isnan(night)
            dawn_valid = ~np.isnan(dawn)
            if night_valid.sum() < 6 or dawn_valid.sum() < 6:
                continue

            nadir = np.nanmin(night)
            nadir_time = np.nanargmin(night) / STEPS_PER_HOUR
            peak = np.nanmax(dawn)
            peak_time = 4 + np.nanargmax(dawn) / STEPS_PER_HOUR
            amplitude = peak - nadir

            # What ISF would cover this rise?
            profile_isf = get_profile_isf(df, 5)  # 5am ISF
            profile_basal = get_profile_basal(df, 5)

            if profile_isf and profile_isf > 0:
                extra_insulin_needed = amplitude / profile_isf
                duration = peak_time - nadir_time
                if duration > 0:
                    extra_basal_rate = extra_insulin_needed / duration
                else:
                    extra_basal_rate = 0
            else:
                extra_insulin_needed = None
                extra_basal_rate = None

            dawn_events.append({
                'nadir': float(nadir),
                'peak': float(peak),
                'amplitude': float(amplitude),
                'nadir_time': round(nadir_time, 1),
                'peak_time': round(peak_time, 1),
                'extra_basal': round(extra_basal_rate, 3) if extra_basal_rate else None
            })

        if not dawn_events:
            results[name] = {'n_nights': 0}
            continue

        amps = [e['amplitude'] for e in dawn_events]
        basals_needed = [e['extra_basal'] for e in dawn_events if e['extra_basal'] is not None]
        nadir_times = [e['nadir_time'] for e in dawn_events]
        peak_times = [e['peak_time'] for e in dawn_events]

        # Recommended protocol
        ramp_start = np.percentile(nadir_times, 25)  # start early (25th pctl)
        ramp_end = np.median(peak_times)
        ramp_rate = np.median(basals_needed) if basals_needed else None

        results[name] = {
            'n_nights': len(dawn_events),
            'amplitude_median': round(float(np.median(amps)), 0),
            'amplitude_p75': round(float(np.percentile(amps, 75)), 0),
            'ramp_start': round(ramp_start, 1),
            'ramp_end': round(ramp_end, 1),
            'extra_basal_median': round(ramp_rate, 3) if ramp_rate else None,
            'profile_basal': round(get_profile_basal(df, 5) or 0, 3),
            'variability': round(float(np.std(amps)), 0)
        }
        print(f"  {name}: amp={np.median(amps):.0f}±{np.std(amps):.0f}, "
              f"ramp {ramp_start:.1f}-{ramp_end:.1f}h, +{ramp_rate:.2f} U/hr"
              if ramp_rate else
              f"  {name}: amp={np.median(amps):.0f}±{np.std(amps):.0f}")

    if MAKE_FIGS:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        # Left: dawn amplitude vs extra basal needed
        ax = axes[0]
        pnames = sorted([n for n, r in results.items()
                        if r.get('amplitude_median') and r.get('extra_basal_median')])
        if pnames:
            amps = [results[n]['amplitude_median'] for n in pnames]
            basals = [results[n]['extra_basal_median'] for n in pnames]
            ax.scatter(amps, basals, s=100, color='steelblue', zorder=3)
            for n, a, b in zip(pnames, amps, basals):
                ax.annotate(n, (a, b), textcoords="offset points",
                           xytext=(5, 5), fontsize=9)
            ax.set_xlabel('Dawn Amplitude (mg/dL)')
            ax.set_ylabel('Extra Basal Needed (U/hr)')
            ax.set_title('Dawn Amplitude → Basal Ramp Requirement')
            ax.grid(True, alpha=0.3)

        # Right: ramp timing
        ax = axes[1]
        pnames2 = sorted([n for n, r in results.items() if r.get('ramp_start')])
        if pnames2:
            starts = [results[n]['ramp_start'] for n in pnames2]
            ends = [results[n]['ramp_end'] for n in pnames2]
            y = range(len(pnames2))
            for yi, (s, e, n) in enumerate(zip(starts, ends, pnames2)):
                ax.barh(yi, e - s, left=s, height=0.6, color='steelblue', alpha=0.7)
            ax.set_yticks(list(y))
            ax.set_yticklabels(pnames2)
            ax.set_xlabel('Time (hours after midnight)')
            ax.set_title('Dawn Basal Ramp Window')
            ax.set_xlim(0, 8)
            ax.grid(True, alpha=0.3, axis='x')

        plt.tight_layout()
        fig.savefig(f'{FIG_DIR}/opt-fig06-dawn-protocol.png', dpi=150, bbox_inches='tight')
        plt.close()
        print(f"  → Saved opt-fig06-dawn-protocol.png")

    output = {'experiment': 'EXP-2076', 'title': 'Dawn Protocol',
              'per_patient': results}
    with open(f'{EXP_DIR}/exp-2076_dawn_protocol.json', 'w') as f:
        json.dump(output, f, indent=2, cls=NumpyEncoder)
    return output


# ── EXP-2077: Dinner-Specific Settings ──────────────────────────────
def exp_2077_dinner_settings():
    """Compute dinner-specific CR and ISF adjustments."""
    print("\n═══ EXP-2077: Dinner-Specific Settings ═══")

    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        carbs = df['carbs'].values
        bolus = df['bolus'].values

        breakfast_data = []
        dinner_data = []

        for i in range(len(g) - 3 * STEPS_PER_HOUR):
            if np.isnan(carbs[i]) or carbs[i] < 5 or np.isnan(g[i]):
                continue

            total_bolus = np.nansum(bolus[max(0, i-6):i+6])
            if total_bolus < 0.1:
                continue

            future = g[i:i + 3 * STEPS_PER_HOUR]
            if np.sum(~np.isnan(future)) < 6:
                continue

            spike = np.nanmax(future) - g[i]
            hour = (i % STEPS_PER_DAY) / STEPS_PER_HOUR

            event = {
                'spike': float(spike),
                'carbs': float(carbs[i]),
                'bolus': float(total_bolus),
                'cr_used': float(carbs[i] / total_bolus),
                'pre_glucose': float(g[i])
            }

            if 5 <= hour < 10:
                breakfast_data.append(event)
            elif 17 <= hour < 21:
                dinner_data.append(event)

        if len(breakfast_data) < 5 or len(dinner_data) < 5:
            results[name] = {'n_breakfast': len(breakfast_data),
                            'n_dinner': len(dinner_data)}
            print(f"  {name}: insufficient data (B={len(breakfast_data)}, D={len(dinner_data)})")
            continue

        bk_spike = np.median([e['spike'] for e in breakfast_data])
        dn_spike = np.median([e['spike'] for e in dinner_data])
        bk_cr = np.median([e['cr_used'] for e in breakfast_data])
        dn_cr = np.median([e['cr_used'] for e in dinner_data])

        # Dinner adjustment: to equalize spikes, need more insulin at dinner
        spike_ratio = dn_spike / bk_spike if bk_spike > 0 else 1
        cr_adjustment = 1 / spike_ratio if spike_ratio > 0 else 1  # multiply CR by this

        # Recommended dinner CR
        recommended_cr = dn_cr * cr_adjustment

        results[name] = {
            'n_breakfast': len(breakfast_data),
            'n_dinner': len(dinner_data),
            'breakfast_spike': round(bk_spike, 1),
            'dinner_spike': round(dn_spike, 1),
            'spike_ratio': round(spike_ratio, 2),
            'current_dinner_cr': round(dn_cr, 1),
            'recommended_dinner_cr': round(recommended_cr, 1),
            'cr_change_pct': round((recommended_cr / dn_cr - 1) * 100, 1) if dn_cr > 0 else 0,
            'breakfast_cr': round(bk_cr, 1)
        }
        print(f"  {name}: B spike={bk_spike:.0f}, D spike={dn_spike:.0f} "
              f"({spike_ratio:.2f}×), CR {dn_cr:.0f}→{recommended_cr:.0f}")

    if MAKE_FIGS:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        # Left: breakfast vs dinner spike
        ax = axes[0]
        pnames = sorted([n for n, r in results.items() if r.get('breakfast_spike') is not None])
        if pnames:
            bk = [results[n]['breakfast_spike'] for n in pnames]
            dn = [results[n]['dinner_spike'] for n in pnames]
            x = np.arange(len(pnames))
            ax.bar(x - 0.2, bk, 0.35, label='Breakfast', color='#ff7f0e', alpha=0.7)
            ax.bar(x + 0.2, dn, 0.35, label='Dinner', color='#d62728', alpha=0.7)
            ax.set_xticks(x)
            ax.set_xticklabels(pnames)
            ax.set_ylabel('Median Spike (mg/dL)')
            ax.set_title('Breakfast vs Dinner Spike')
            ax.legend()
            ax.grid(True, alpha=0.3, axis='y')

        # Right: CR adjustment needed
        ax = axes[1]
        pnames2 = sorted([n for n, r in results.items() if r.get('cr_change_pct') is not None])
        if pnames2:
            changes = [results[n]['cr_change_pct'] for n in pnames2]
            colors = ['#2ca02c' if c < -5 else '#d62728' if c > 5 else '#7f7f7f' for c in changes]
            ax.barh(pnames2, changes, color=colors, alpha=0.7)
            ax.axvline(x=0, color='black', linewidth=1)
            ax.set_xlabel('Dinner CR Change Needed (%)')
            ax.set_title('Dinner CR Adjustment (<0 = need more insulin)')
            ax.grid(True, alpha=0.3, axis='x')

        plt.tight_layout()
        fig.savefig(f'{FIG_DIR}/opt-fig07-dinner-settings.png', dpi=150, bbox_inches='tight')
        plt.close()
        print(f"  → Saved opt-fig07-dinner-settings.png")

    output = {'experiment': 'EXP-2077', 'title': 'Dinner Settings',
              'per_patient': results}
    with open(f'{EXP_DIR}/exp-2077_dinner_settings.json', 'w') as f:
        json.dump(output, f, indent=2, cls=NumpyEncoder)
    return output


# ── EXP-2078: Synthesis — Complete Optimized Profile ─────────────────
def exp_2078_synthesis():
    """Generate complete optimized therapy profile per patient."""
    print("\n═══ EXP-2078: Synthesis — Optimized Therapy Profiles ═══")

    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values

        # Current metrics
        valid = ~np.isnan(g)
        g_valid = g[valid]
        current = {
            'tir': round(float(np.mean((g_valid >= TARGET_LOW) & (g_valid <= TARGET_HIGH))), 3),
            'tbr': round(float(np.mean(g_valid < TARGET_LOW)), 3),
            'tar': round(float(np.mean(g_valid > TARGET_HIGH)), 3),
            'mean_glucose': round(float(np.mean(g_valid)), 1),
            'cv': round(float(np.std(g_valid) / np.mean(g_valid) * 100), 1),
            'eA1c': round(float((np.mean(g_valid) + 46.7) / 28.7), 1)
        }

        # Profile settings (list of {time, value, timeAsSeconds} dicts)
        isf_schedule = df.attrs.get('isf_schedule', [])
        cr_schedule = df.attrs.get('cr_schedule', [])
        basal_schedule = df.attrs.get('basal_schedule', [])

        # Convert ISF if mmol
        profile_isf = {}
        for entry in isf_schedule:
            t = entry.get('time', '00:00')
            v = entry.get('value', 0)
            profile_isf[t] = round(v * 18.0182, 1) if v < 15 else round(v, 1)

        # Priority ranking
        priorities = []
        if current['tbr'] > 0.04:
            priorities.append(('REDUCE_TBR', f"TBR={current['tbr']:.1%} exceeds 4% target"))
        if current['tar'] > 0.25:
            priorities.append(('REDUCE_TAR', f"TAR={current['tar']:.1%} exceeds 25% target"))
        if current['tir'] < 0.70:
            priorities.append(('INCREASE_TIR', f"TIR={current['tir']:.0%} below 70% target"))
        if current['cv'] > 36:
            priorities.append(('REDUCE_CV', f"CV={current['cv']:.0f}% exceeds 36% target"))

        # Top recommendation
        if current['tbr'] > 0.04:
            top_rec = "Increase ISF (less aggressive corrections to reduce hypos)"
        elif current['tar'] > 0.30:
            top_rec = "Decrease ISF and/or CR (more aggressive to reduce highs)"
        elif current['tir'] < 0.70:
            top_rec = "Review basal schedule and meal settings"
        else:
            top_rec = "Settings adequate — monitor for drift"

        results[name] = {
            'current_metrics': current,
            'profile_isf': profile_isf,
            'profile_cr': {e.get('time', '00:00'): round(e.get('value', 0), 1) for e in cr_schedule},
            'profile_basal': {e.get('time', '00:00'): round(e.get('value', 0), 3) for e in basal_schedule},
            'priorities': priorities,
            'n_priorities': len(priorities),
            'top_recommendation': top_rec
        }
        status = "✓" if current['tir'] >= 0.70 and current['tbr'] <= 0.04 else "✗"
        print(f"  {name}: {status} TIR={current['tir']:.0%} TBR={current['tbr']:.1%} "
              f"TAR={current['tar']:.1%} → {top_rec[:50]}")

    # Population summary
    meeting_tir = sum(1 for r in results.values() if r['current_metrics']['tir'] >= 0.70)
    meeting_tbr = sum(1 for r in results.values() if r['current_metrics']['tbr'] <= 0.04)
    n = len(results)

    print(f"\n  Population: {meeting_tir}/{n} meet TIR≥70%, {meeting_tbr}/{n} meet TBR≤4%")

    if MAKE_FIGS:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        # Left: current metrics dashboard
        ax = axes[0]
        pnames = sorted(results.keys())
        tirs = [results[n]['current_metrics']['tir'] * 100 for n in pnames]
        tbrs = [results[n]['current_metrics']['tbr'] * 100 for n in pnames]
        tars = [results[n]['current_metrics']['tar'] * 100 for n in pnames]
        x = np.arange(len(pnames))
        ax.barh(x, tirs, color='#2ca02c', alpha=0.7, label='TIR')
        ax.barh(x, [-t for t in tbrs], color='#d62728', alpha=0.7, label='TBR (left)')
        ax.axvline(x=70, color='green', linestyle='--', alpha=0.5)
        ax.axvline(x=-4, color='red', linestyle='--', alpha=0.5)
        ax.set_yticks(x)
        ax.set_yticklabels(pnames)
        ax.set_xlabel('← TBR% | TIR% →')
        ax.set_title('Current Glycemic Control Dashboard')
        ax.legend(loc='lower right')
        ax.grid(True, alpha=0.3, axis='x')

        # Right: priority counts
        ax = axes[1]
        n_priorities = [results[n]['n_priorities'] for n in pnames]
        colors = ['#d62728' if p >= 3 else '#ff7f0e' if p >= 2 else '#2ca02c' if p >= 1
                  else '#7f7f7f' for p in n_priorities]
        ax.barh(pnames, n_priorities, color=colors, alpha=0.7)
        ax.set_xlabel('Number of Unmet Targets')
        ax.set_title('Optimization Priority Count')
        ax.grid(True, alpha=0.3, axis='x')

        plt.tight_layout()
        fig.savefig(f'{FIG_DIR}/opt-fig08-synthesis.png', dpi=150, bbox_inches='tight')
        plt.close()
        print(f"  → Saved opt-fig08-synthesis.png")

    output = {'experiment': 'EXP-2078', 'title': 'Optimized Therapy Profiles',
              'per_patient': results,
              'population': {
                  'meeting_tir_70': meeting_tir,
                  'meeting_tbr_4': meeting_tbr,
                  'total': n
              }}
    with open(f'{EXP_DIR}/exp-2078_synthesis.json', 'w') as f:
        json.dump(output, f, indent=2, cls=NumpyEncoder)
    return output


# ── Main ─────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print("=" * 60)
    print("EXP-2071–2078: Therapy Settings Optimization")
    print("=" * 60)

    r1 = exp_2071_optimal_isf()
    r2 = exp_2072_optimal_cr()
    r3 = exp_2073_optimal_basal()
    r4 = exp_2074_settings_validation()
    r5 = exp_2075_overcorrection_prevention()
    r6 = exp_2076_dawn_protocol()
    r7 = exp_2077_dinner_settings()
    r8 = exp_2078_synthesis()

    print("\n" + "=" * 60)
    passed = sum(1 for r in [r1, r2, r3, r4, r5, r6, r7, r8] if r is not None)
    print(f"Results: {passed}/8 experiments completed")
    if MAKE_FIGS:
        print(f"Figures saved to {FIG_DIR}/opt-fig01–08")
    print("=" * 60)
