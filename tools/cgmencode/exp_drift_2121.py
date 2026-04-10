#!/usr/bin/env python3
"""
EXP-2121–2128: Exercise Detection & Longitudinal Drift

Investigate exercise/activity signatures in CGM data and whether
therapy settings drift over time requiring adjustment.

EXP-2121: Exercise signature detection — rapid glucose drop without insulin
EXP-2122: Post-exercise hypo risk — delayed hypo windows after activity
EXP-2123: Activity-driven glucose patterns — non-meal, non-correction drops
EXP-2124: Monthly therapy drift — do settings effectiveness change over months?
EXP-2125: Seasonal or periodic patterns — multi-week cycles in control quality
EXP-2126: Insulin sensitivity drift — does ISF effectiveness change over time?
EXP-2127: Proactive adjustment triggers — what predicts therapy needs 1 week ahead?
EXP-2128: Comprehensive drift dashboard — per-patient longitudinal assessment

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


patients = load_patients(PATIENT_DIR)


def compute_tir(glucose):
    g = glucose[~np.isnan(glucose)]
    if len(g) == 0:
        return 0, 0, 0
    return (float(np.mean((g >= 70) & (g <= 180))),
            float(np.mean(g < 70)),
            float(np.mean(g > 180)))


def split_into_days(glucose, steps_per_day=STEPS_PER_DAY):
    n_days = len(glucose) // steps_per_day
    return [glucose[d*steps_per_day:(d+1)*steps_per_day] for d in range(n_days)]


# ── EXP-2121: Exercise Signature Detection ────────────────────────────
def exp_2121_exercise_signatures():
    """Detect rapid glucose drops without insulin — exercise proxy."""
    print("\n═══ EXP-2121: Exercise Signature Detection ═══")

    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        iob = df['iob'].values

        n_days = np.sum(~np.isnan(g)) / STEPS_PER_DAY
        if n_days < 14:
            continue

        exercise_events = []

        for i in range(STEPS_PER_HOUR, len(g) - 2 * STEPS_PER_HOUR):
            if np.isnan(g[i]):
                continue

            # Look for rapid drop (>30 mg/dL in 1h) without recent bolus
            future_1h = g[i:i + STEPS_PER_HOUR]
            valid_f = future_1h[~np.isnan(future_1h)]
            if len(valid_f) < 6:
                continue

            drop = g[i] - np.min(valid_f)
            if drop < 30:
                continue

            # No bolus in past 2h
            w = 2 * STEPS_PER_HOUR
            recent_bolus = np.nansum(bolus[max(0, i-w):i+1])
            if recent_bolus > 0.3:
                continue

            # Low IOB (<1U)
            current_iob = iob[i] if not np.isnan(iob[i]) else 0
            if current_iob > 1.0:
                continue

            hour = (i % STEPS_PER_DAY) / STEPS_PER_HOUR

            # Post-event: check for hypo in next 4h
            future_4h = g[i:i + 4 * STEPS_PER_HOUR]
            valid_4h = future_4h[~np.isnan(future_4h)]
            post_hypo = bool(np.any(valid_4h < 70)) if len(valid_4h) > 0 else False

            # Rebound: check for rise after drop
            future_2h = g[i + STEPS_PER_HOUR:i + 3 * STEPS_PER_HOUR] if i + 3 * STEPS_PER_HOUR < len(g) else np.array([])
            valid_2h = future_2h[~np.isnan(future_2h)]
            rebound = float(np.max(valid_2h) - np.min(valid_f)) if len(valid_2h) > 0 else 0

            exercise_events.append({
                'step': i,
                'hour': round(hour, 1),
                'start_glucose': float(g[i]),
                'drop': round(float(drop), 1),
                'iob': round(current_iob, 2),
                'post_hypo': post_hypo,
                'rebound': round(rebound, 1)
            })

        events_per_day = len(exercise_events) / n_days
        hypo_rate = sum(1 for e in exercise_events if e['post_hypo']) / len(exercise_events) if exercise_events else 0

        # Hour distribution
        hour_hist = np.zeros(24)
        for e in exercise_events:
            hour_hist[int(e['hour'])] += 1

        peak_hour = int(np.argmax(hour_hist)) if np.sum(hour_hist) > 0 else -1

        results[name] = {
            'n_events': len(exercise_events),
            'events_per_day': round(events_per_day, 2),
            'hypo_rate': round(hypo_rate, 3),
            'mean_drop': round(float(np.mean([e['drop'] for e in exercise_events])), 1) if exercise_events else 0,
            'mean_rebound': round(float(np.mean([e['rebound'] for e in exercise_events])), 1) if exercise_events else 0,
            'peak_hour': peak_hour,
            'hour_distribution': hour_hist.tolist()
        }

        print(f"  {name}: {len(exercise_events)} events ({events_per_day:.1f}/day) "
              f"drop={results[name]['mean_drop']:.0f} rebound={results[name]['mean_rebound']:.0f} "
              f"hypo={hypo_rate:.0%} peak={peak_hour}:00")

    if MAKE_FIGS:
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))
        names = sorted(results.keys())
        x = np.arange(len(names))

        ax = axes[0]
        vals = [results[n]['events_per_day'] for n in names]
        ax.bar(x, vals, color='C0', edgecolor='black')
        ax.set_xticks(x)
        ax.set_xticklabels(names, fontweight='bold')
        ax.set_ylabel('Events per Day')
        ax.set_title('Exercise-Like Events per Day', fontweight='bold')

        ax = axes[1]
        drops = [results[n]['mean_drop'] for n in names]
        rebounds = [results[n]['mean_rebound'] for n in names]
        ax.bar(x - 0.15, drops, 0.3, label='Mean Drop', color='C3', edgecolor='black')
        ax.bar(x + 0.15, rebounds, 0.3, label='Mean Rebound', color='C2', edgecolor='black')
        ax.set_xticks(x)
        ax.set_xticklabels(names, fontweight='bold')
        ax.set_ylabel('mg/dL')
        ax.set_title('Drop vs Rebound Magnitude', fontweight='bold')
        ax.legend()

        fig.suptitle('EXP-2121: Exercise Signature Detection',
                     fontsize=14, fontweight='bold')
        fig.tight_layout(rect=[0, 0, 1, 0.95])
        fig.savefig(f'{FIG_DIR}/drift-fig01-exercise.png', dpi=150,
                    bbox_inches='tight')
        plt.close()
        print(f"  → Saved drift-fig01-exercise.png")

    output = {'experiment': 'EXP-2121', 'title': 'Exercise Signature Detection',
              'per_patient': results}
    with open(f'{EXP_DIR}/exp-2121_exercise.json', 'w') as f:
        json.dump(output, f, indent=2, cls=NumpyEncoder)
    return output


# ── EXP-2122: Post-Exercise Hypo Risk ────────────────────────────────
def exp_2122_post_exercise_hypo():
    """When does hypo risk peak relative to exercise-like events?"""
    print("\n═══ EXP-2122: Post-Exercise Hypo Risk ═══")

    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        bolus = df['bolus'].values
        iob = df['iob'].values

        # Detect exercise events (same as EXP-2121)
        events = []
        for i in range(STEPS_PER_HOUR, len(g) - 8 * STEPS_PER_HOUR):
            if np.isnan(g[i]) or g[i] < 80:
                continue
            future_1h = g[i:i + STEPS_PER_HOUR]
            valid_f = future_1h[~np.isnan(future_1h)]
            if len(valid_f) < 6:
                continue
            drop = g[i] - np.min(valid_f)
            if drop < 30:
                continue
            w = 2 * STEPS_PER_HOUR
            if np.nansum(bolus[max(0, i-w):i+1]) > 0.3:
                continue
            current_iob = iob[i] if not np.isnan(iob[i]) else 0
            if current_iob > 1.0:
                continue
            events.append(i)

        if len(events) < 10:
            results[name] = {'sufficient': False, 'n_events': len(events)}
            print(f"  {name}: insufficient ({len(events)} events)")
            continue

        # Track hypo risk over 8 hours post-event
        hours_post = list(range(1, 9))
        hypo_by_hour = {h: 0 for h in hours_post}
        total_valid = {h: 0 for h in hours_post}

        for evt in events:
            for h in hours_post:
                window_start = evt + (h-1) * STEPS_PER_HOUR
                window_end = evt + h * STEPS_PER_HOUR
                if window_end >= len(g):
                    continue
                window = g[window_start:window_end]
                valid = window[~np.isnan(window)]
                if len(valid) > 0:
                    total_valid[h] += 1
                    if np.any(valid < 70):
                        hypo_by_hour[h] += 1

        hypo_rates = {}
        for h in hours_post:
            if total_valid[h] > 0:
                hypo_rates[f'{h}h'] = round(hypo_by_hour[h] / total_valid[h], 3)

        peak_hour = max(hypo_rates, key=hypo_rates.get) if hypo_rates else 'N/A'

        results[name] = {
            'sufficient': True,
            'n_events': len(events),
            'hypo_rates': hypo_rates,
            'peak_risk_hour': peak_hour,
            'peak_risk_rate': hypo_rates.get(peak_hour, 0)
        }

        print(f"  {name}: peak risk at {peak_hour} ({hypo_rates.get(peak_hour, 0):.0%}) "
              f"({len(events)} events)")

    if MAKE_FIGS:
        fig, ax = plt.subplots(figsize=(12, 6))
        names = sorted([n for n in results if results[n].get('sufficient', False)])

        for n in names:
            hours = [int(h[:-1]) for h in results[n]['hypo_rates'].keys()]
            rates = [results[n]['hypo_rates'][f'{h}h'] * 100 for h in hours]
            ax.plot(hours, rates, marker='o', label=n, alpha=0.7)

        ax.set_xlabel('Hours Post-Event')
        ax.set_ylabel('Hypo Rate (%)')
        ax.set_title('EXP-2122: Post-Exercise Hypo Risk Window',
                     fontsize=14, fontweight='bold')
        ax.legend(fontsize=8, ncol=3)
        ax.grid(alpha=0.3)

        fig.tight_layout()
        fig.savefig(f'{FIG_DIR}/drift-fig02-post-exercise.png', dpi=150,
                    bbox_inches='tight')
        plt.close()
        print(f"  → Saved drift-fig02-post-exercise.png")

    output = {'experiment': 'EXP-2122', 'title': 'Post-Exercise Hypo Risk',
              'per_patient': results}
    with open(f'{EXP_DIR}/exp-2122_post_exercise.json', 'w') as f:
        json.dump(output, f, indent=2, cls=NumpyEncoder)
    return output


# ── EXP-2123: Activity-Driven Glucose Patterns ───────────────────────
def exp_2123_activity_patterns():
    """Non-meal, non-correction glucose drops — what are they?"""
    print("\n═══ EXP-2123: Activity-Driven Glucose Patterns ═══")

    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        iob = df['iob'].values

        n_days = np.sum(~np.isnan(g)) / STEPS_PER_DAY

        # Classify all glucose drops >20 mg/dL in 1h
        insulin_drops = 0
        carb_drops = 0
        unexplained_drops = 0
        total_drops = 0

        for i in range(len(g) - STEPS_PER_HOUR):
            if np.isnan(g[i]):
                continue
            future = g[i:i + STEPS_PER_HOUR]
            valid_f = future[~np.isnan(future)]
            if len(valid_f) < 6:
                continue
            drop = g[i] - np.min(valid_f)
            if drop < 20:
                continue

            total_drops += 1

            w = 2 * STEPS_PER_HOUR
            has_bolus = np.nansum(bolus[max(0, i-w):i+1]) > 0.3
            has_iob = (iob[i] if not np.isnan(iob[i]) else 0) > 0.5
            has_carbs = np.nansum(carbs[max(0, i-6):i+6]) > 0

            if has_bolus or has_iob:
                insulin_drops += 1
            elif has_carbs:
                carb_drops += 1
            else:
                unexplained_drops += 1

        if total_drops < 10:
            results[name] = {'sufficient': False}
            continue

        results[name] = {
            'sufficient': True,
            'total_drops': total_drops,
            'insulin_attributed': insulin_drops,
            'carb_attributed': carb_drops,
            'unexplained': unexplained_drops,
            'pct_insulin': round(insulin_drops / total_drops, 3),
            'pct_unexplained': round(unexplained_drops / total_drops, 3),
            'unexplained_per_day': round(unexplained_drops / n_days, 1)
        }

        print(f"  {name}: {total_drops} drops → insulin={insulin_drops} "
              f"unexplained={unexplained_drops} ({unexplained_drops/total_drops:.0%}) "
              f"= {unexplained_drops/n_days:.1f}/day")

    if MAKE_FIGS:
        fig, ax = plt.subplots(figsize=(12, 6))
        names = sorted([n for n in results if results[n].get('sufficient', False)])
        x = np.arange(len(names))

        ins = [results[n]['pct_insulin'] * 100 for n in names]
        unx = [results[n]['pct_unexplained'] * 100 for n in names]
        carb = [100 - ins[i] - unx[i] for i in range(len(names))]

        ax.bar(x, ins, label='Insulin-Attributed', color='C0', edgecolor='black')
        ax.bar(x, carb, bottom=ins, label='Carb-Attributed', color='C1', edgecolor='black')
        ax.bar(x, unx, bottom=[ins[i]+carb[i] for i in range(len(names))],
               label='Unexplained (Activity?)', color='C3', edgecolor='black')
        ax.set_xticks(x)
        ax.set_xticklabels(names, fontweight='bold')
        ax.set_ylabel('% of Total Drops')
        ax.set_title('EXP-2123: Glucose Drop Attribution',
                     fontsize=14, fontweight='bold')
        ax.legend()

        fig.tight_layout()
        fig.savefig(f'{FIG_DIR}/drift-fig03-activity.png', dpi=150,
                    bbox_inches='tight')
        plt.close()
        print(f"  → Saved drift-fig03-activity.png")

    output = {'experiment': 'EXP-2123', 'title': 'Activity-Driven Glucose Patterns',
              'per_patient': results}
    with open(f'{EXP_DIR}/exp-2123_activity.json', 'w') as f:
        json.dump(output, f, indent=2, cls=NumpyEncoder)
    return output


# ── EXP-2124: Monthly Therapy Drift ──────────────────────────────────
def exp_2124_monthly_drift():
    """Do therapy metrics drift over months?"""
    print("\n═══ EXP-2124: Monthly Therapy Drift ═══")

    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        bolus = df['bolus'].values

        days = split_into_days(g)
        bolus_days = split_into_days(bolus)
        n_months = len(days) // 30

        if n_months < 3:
            results[name] = {'sufficient': False}
            print(f"  {name}: insufficient ({n_months} months)")
            continue

        monthly_metrics = []
        for m in range(n_months):
            start = m * 30
            end = start + 30
            month_g = np.concatenate(days[start:end])
            month_b = np.concatenate(bolus_days[start:end])

            g_valid = month_g[~np.isnan(month_g)]
            if len(g_valid) < STEPS_PER_DAY * 10:
                continue

            tir, tbr, tar = compute_tir(month_g)
            cv = float(np.std(g_valid) / np.mean(g_valid))
            daily_insulin = float(np.nansum(month_b) / 30)

            monthly_metrics.append({
                'month': m + 1,
                'tir': round(tir, 3),
                'tbr': round(tbr, 3),
                'tar': round(tar, 3),
                'cv': round(cv, 3),
                'mean_glucose': round(float(np.mean(g_valid)), 1),
                'daily_insulin': round(daily_insulin, 1)
            })

        if len(monthly_metrics) < 3:
            results[name] = {'sufficient': False}
            continue

        # Compute trend
        tirs = [m['tir'] for m in monthly_metrics]
        months = list(range(len(tirs)))
        slope = float(np.polyfit(months, tirs, 1)[0]) if len(tirs) >= 3 else 0
        trending = 'IMPROVING' if slope > 0.01 else 'DECLINING' if slope < -0.01 else 'STABLE'

        results[name] = {
            'sufficient': True,
            'n_months': len(monthly_metrics),
            'monthly': monthly_metrics,
            'tir_trend_per_month': round(slope * 100, 2),
            'trending': trending,
            'first_month_tir': monthly_metrics[0]['tir'],
            'last_month_tir': monthly_metrics[-1]['tir'],
            'tir_change': round((monthly_metrics[-1]['tir'] - monthly_metrics[0]['tir']) * 100, 1)
        }

        print(f"  {name}: {trending} slope={slope*100:+.2f}pp/mo "
              f"TIR {monthly_metrics[0]['tir']:.0%}→{monthly_metrics[-1]['tir']:.0%} "
              f"({len(monthly_metrics)} months)")

    if MAKE_FIGS:
        fig, ax = plt.subplots(figsize=(14, 7))
        names = sorted([n for n in results if results[n].get('sufficient', False)])

        for n in names:
            months = [m['month'] for m in results[n]['monthly']]
            tirs = [m['tir'] * 100 for m in results[n]['monthly']]
            style = '--' if results[n]['trending'] == 'DECLINING' else '-'
            ax.plot(months, tirs, marker='o', linestyle=style, label=f"{n} ({results[n]['trending']})")

        ax.axhline(70, color='green', linestyle='--', alpha=0.5, label='Target')
        ax.set_xlabel('Month')
        ax.set_ylabel('TIR (%)')
        ax.set_title('EXP-2124: Monthly TIR Trajectory',
                     fontsize=14, fontweight='bold')
        ax.legend(fontsize=8, ncol=2)
        ax.grid(alpha=0.3)

        fig.tight_layout()
        fig.savefig(f'{FIG_DIR}/drift-fig04-monthly.png', dpi=150,
                    bbox_inches='tight')
        plt.close()
        print(f"  → Saved drift-fig04-monthly.png")

    output = {'experiment': 'EXP-2124', 'title': 'Monthly Therapy Drift',
              'per_patient': results}
    with open(f'{EXP_DIR}/exp-2124_monthly.json', 'w') as f:
        json.dump(output, f, indent=2, cls=NumpyEncoder)
    return output


# ── EXP-2125: Periodic Patterns ──────────────────────────────────────
def exp_2125_periodic():
    """Multi-week cycles in glycemic control quality."""
    print("\n═══ EXP-2125: Periodic Patterns ═══")

    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values

        days = split_into_days(g)
        daily_tirs = []
        for day_g in days:
            g_valid = day_g[~np.isnan(day_g)]
            if len(g_valid) > STEPS_PER_HOUR * 12:
                daily_tirs.append(float(np.mean((g_valid >= 70) & (g_valid <= 180))))
            else:
                daily_tirs.append(np.nan)

        tir_arr = np.array(daily_tirs)
        valid_mask = ~np.isnan(tir_arr)
        if np.sum(valid_mask) < 60:
            results[name] = {'sufficient': False}
            continue

        # Fill NaN with mean for FFT
        tir_filled = tir_arr.copy()
        tir_filled[~valid_mask] = np.nanmean(tir_arr)
        tir_centered = tir_filled - np.mean(tir_filled)

        # FFT to detect periodicities
        fft = np.fft.rfft(tir_centered)
        power = np.abs(fft) ** 2
        freqs = np.fft.rfftfreq(len(tir_centered), d=1.0)  # cycles per day

        # Skip DC and very low frequencies (<7 days)
        min_period = 7
        max_period = len(tir_centered) // 2
        valid_freq = (freqs > 1/max_period) & (freqs < 1/min_period)

        if not np.any(valid_freq):
            results[name] = {'sufficient': False}
            continue

        power_valid = power[valid_freq]
        freqs_valid = freqs[valid_freq]

        # Top 3 frequencies
        top_idx = np.argsort(power_valid)[-3:][::-1]
        top_periods = []
        for idx in top_idx:
            period = 1 / freqs_valid[idx] if freqs_valid[idx] > 0 else 0
            top_periods.append({
                'period_days': round(period, 1),
                'power': round(float(power_valid[idx]), 4),
                'relative_power': round(float(power_valid[idx] / np.sum(power_valid)), 3)
            })

        # Is the dominant period significant?
        dominant_power = top_periods[0]['relative_power']
        has_cycle = dominant_power > 0.15  # >15% of spectral energy

        results[name] = {
            'sufficient': True,
            'n_days': int(np.sum(valid_mask)),
            'top_periods': top_periods,
            'dominant_period': top_periods[0]['period_days'],
            'dominant_power': dominant_power,
            'has_significant_cycle': has_cycle
        }

        sig = "YES" if has_cycle else "NO"
        print(f"  {name}: dominant={top_periods[0]['period_days']:.0f}d "
              f"(power={dominant_power:.1%}) significant={sig}")

    if MAKE_FIGS:
        fig, ax = plt.subplots(figsize=(14, 6))
        names = sorted([n for n in results if results[n].get('sufficient', False)])
        x = np.arange(len(names))

        periods = [results[n]['dominant_period'] for n in names]
        powers = [results[n]['dominant_power'] * 100 for n in names]
        colors = ['C2' if results[n]['has_significant_cycle'] else 'gray' for n in names]

        ax.bar(x, periods, color=colors, edgecolor='black')
        for i, n in enumerate(names):
            ax.text(i, periods[i] + 0.5, f'{powers[i]:.0f}%', ha='center',
                    fontsize=9, fontweight='bold')

        ax.set_xticks(x)
        ax.set_xticklabels(names, fontweight='bold')
        ax.set_ylabel('Dominant Period (days)')
        ax.set_title('EXP-2125: Dominant Periodicities in TIR',
                     fontsize=14, fontweight='bold')
        ax.axhline(7, color='red', linestyle='--', alpha=0.5, label='Weekly')
        ax.axhline(14, color='orange', linestyle='--', alpha=0.5, label='Biweekly')
        ax.axhline(28, color='blue', linestyle='--', alpha=0.5, label='Monthly')
        ax.legend()

        fig.tight_layout()
        fig.savefig(f'{FIG_DIR}/drift-fig05-periodic.png', dpi=150,
                    bbox_inches='tight')
        plt.close()
        print(f"  → Saved drift-fig05-periodic.png")

    output = {'experiment': 'EXP-2125', 'title': 'Periodic Patterns',
              'per_patient': results}
    with open(f'{EXP_DIR}/exp-2125_periodic.json', 'w') as f:
        json.dump(output, f, indent=2, cls=NumpyEncoder)
    return output


# ── EXP-2126: Insulin Sensitivity Drift ──────────────────────────────
def exp_2126_isf_drift():
    """Does effective ISF change over time?"""
    print("\n═══ EXP-2126: Insulin Sensitivity Drift ═══")

    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        bolus = df['bolus'].values
        carbs = df['carbs'].values

        # Collect ISF measurements over time
        isf_events = []

        for i in range(len(g) - 3 * STEPS_PER_HOUR):
            if np.isnan(bolus[i]) or bolus[i] < 0.3:
                continue
            if np.isnan(g[i]) or g[i] < 130:
                continue
            w = 2 * STEPS_PER_HOUR
            if np.nansum(carbs[max(0, i-w):min(len(carbs), i+w)]) > 0:
                continue
            future = g[i:i + 3 * STEPS_PER_HOUR]
            valid_f = future[~np.isnan(future)]
            if len(valid_f) < STEPS_PER_HOUR:
                continue
            drop = g[i] - np.min(valid_f)
            if drop < 5:
                continue

            day = i // STEPS_PER_DAY
            isf_events.append({
                'day': day,
                'isf': float(drop / bolus[i]),
                'dose': float(bolus[i]),
                'drop': float(drop)
            })

        if len(isf_events) < 20:
            results[name] = {'sufficient': False, 'n_events': len(isf_events)}
            print(f"  {name}: insufficient ({len(isf_events)} events)")
            continue

        # Split into thirds
        n = len(isf_events)
        third = n // 3
        early = [e['isf'] for e in isf_events[:third]]
        mid = [e['isf'] for e in isf_events[third:2*third]]
        late = [e['isf'] for e in isf_events[2*third:]]

        early_med = float(np.median(early))
        mid_med = float(np.median(mid))
        late_med = float(np.median(late))

        drift = (late_med - early_med) / early_med * 100 if early_med > 0 else 0
        drifting = abs(drift) > 15

        results[name] = {
            'sufficient': True,
            'n_events': len(isf_events),
            'early_isf': round(early_med, 1),
            'mid_isf': round(mid_med, 1),
            'late_isf': round(late_med, 1),
            'drift_pct': round(drift, 1),
            'drifting': drifting
        }

        flag = "DRIFT" if drifting else "STABLE"
        print(f"  {name}: ISF {early_med:.0f}→{mid_med:.0f}→{late_med:.0f} "
              f"({drift:+.1f}%) {flag}")

    if MAKE_FIGS:
        fig, ax = plt.subplots(figsize=(12, 6))
        names = sorted([n for n in results if results[n].get('sufficient', False)])
        x = np.arange(len(names))
        width = 0.25

        early = [results[n]['early_isf'] for n in names]
        mid = [results[n]['mid_isf'] for n in names]
        late = [results[n]['late_isf'] for n in names]

        ax.bar(x - width, early, width, label='Early', color='C0', edgecolor='black')
        ax.bar(x, mid, width, label='Mid', color='C1', edgecolor='black')
        ax.bar(x + width, late, width, label='Late', color='C2', edgecolor='black')
        ax.set_xticks(x)
        ax.set_xticklabels(names, fontweight='bold')
        ax.set_ylabel('Effective ISF (mg/dL per U)')
        ax.set_title('EXP-2126: ISF Drift Over Time',
                     fontsize=14, fontweight='bold')
        ax.legend()

        fig.tight_layout()
        fig.savefig(f'{FIG_DIR}/drift-fig06-isf-drift.png', dpi=150,
                    bbox_inches='tight')
        plt.close()
        print(f"  → Saved drift-fig06-isf-drift.png")

    output = {'experiment': 'EXP-2126', 'title': 'ISF Drift',
              'per_patient': results}
    with open(f'{EXP_DIR}/exp-2126_isf_drift.json', 'w') as f:
        json.dump(output, f, indent=2, cls=NumpyEncoder)
    return output


# ── EXP-2127: Proactive Adjustment Triggers ──────────────────────────
def exp_2127_proactive_triggers():
    """What predicts therapy needs 1 week ahead?"""
    print("\n═══ EXP-2127: Proactive Adjustment Triggers ═══")

    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values

        days = split_into_days(g)
        n_weeks = len(days) // 7

        if n_weeks < 6:
            results[name] = {'sufficient': False}
            continue

        # Compute weekly TIR
        weekly_tirs = []
        weekly_cvs = []
        for w in range(n_weeks):
            week_g = np.concatenate(days[w*7:(w+1)*7])
            g_valid = week_g[~np.isnan(week_g)]
            if len(g_valid) > STEPS_PER_DAY * 3:
                tir = float(np.mean((g_valid >= 70) & (g_valid <= 180)))
                cv = float(np.std(g_valid) / np.mean(g_valid))
                weekly_tirs.append(tir)
                weekly_cvs.append(cv)
            else:
                weekly_tirs.append(np.nan)
                weekly_cvs.append(np.nan)

        tirs = np.array(weekly_tirs)
        cvs = np.array(weekly_cvs)

        # Predictive features: does this week's TIR predict next week?
        valid = ~np.isnan(tirs[:-1]) & ~np.isnan(tirs[1:])
        if np.sum(valid) < 5:
            results[name] = {'sufficient': False}
            continue

        tir_corr = float(np.corrcoef(tirs[:-1][valid], tirs[1:][valid])[0, 1])

        # Does CV predict next week's TIR?
        valid_cv = ~np.isnan(cvs[:-1]) & ~np.isnan(tirs[1:])
        cv_tir_corr = float(np.corrcoef(cvs[:-1][valid_cv], tirs[1:][valid_cv])[0, 1]) if np.sum(valid_cv) > 4 else 0

        # Declining detection: does 2-week rolling average predict decline?
        declines = 0
        total_transitions = 0
        for i in range(2, len(tirs) - 1):
            if np.isnan(tirs[i]) or np.isnan(tirs[i-1]) or np.isnan(tirs[i+1]):
                continue
            total_transitions += 1
            if tirs[i] < tirs[i-1] and tirs[i+1] < tirs[i]:
                declines += 1

        decline_rate = declines / total_transitions if total_transitions > 0 else 0

        results[name] = {
            'sufficient': True,
            'n_weeks': n_weeks,
            'tir_week_autocorr': round(tir_corr, 3),
            'cv_predicts_tir': round(cv_tir_corr, 3),
            'decline_rate': round(decline_rate, 3),
            'mean_tir': round(float(np.nanmean(tirs)), 3),
            'predictable': abs(tir_corr) > 0.3
        }

        pred = "YES" if abs(tir_corr) > 0.3 else "NO"
        print(f"  {name}: TIR week-autocorr={tir_corr:.3f} CV→TIR={cv_tir_corr:.3f} "
              f"declines={decline_rate:.0%} predictable={pred}")

    if MAKE_FIGS:
        fig, ax = plt.subplots(figsize=(12, 6))
        names = sorted([n for n in results if results[n].get('sufficient', False)])
        x = np.arange(len(names))

        autocorrs = [results[n]['tir_week_autocorr'] for n in names]
        cv_corrs = [results[n]['cv_predicts_tir'] for n in names]

        ax.bar(x - 0.15, autocorrs, 0.3, label='TIR Week Autocorrelation',
               color='C0', edgecolor='black')
        ax.bar(x + 0.15, cv_corrs, 0.3, label='CV → Next Week TIR',
               color='C1', edgecolor='black')
        ax.axhline(0.3, color='green', linestyle='--', alpha=0.5, label='Predictive threshold')
        ax.axhline(-0.3, color='green', linestyle='--', alpha=0.5)
        ax.set_xticks(x)
        ax.set_xticklabels(names, fontweight='bold')
        ax.set_ylabel('Correlation')
        ax.set_title('EXP-2127: Weekly TIR Predictability',
                     fontsize=14, fontweight='bold')
        ax.legend()

        fig.tight_layout()
        fig.savefig(f'{FIG_DIR}/drift-fig07-triggers.png', dpi=150,
                    bbox_inches='tight')
        plt.close()
        print(f"  → Saved drift-fig07-triggers.png")

    output = {'experiment': 'EXP-2127', 'title': 'Proactive Adjustment Triggers',
              'per_patient': results}
    with open(f'{EXP_DIR}/exp-2127_triggers.json', 'w') as f:
        json.dump(output, f, indent=2, cls=NumpyEncoder)
    return output


# ── EXP-2128: Comprehensive Drift Dashboard ──────────────────────────
def exp_2128_dashboard():
    """Per-patient longitudinal assessment summary."""
    print("\n═══ EXP-2128: Comprehensive Drift Dashboard ═══")

    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        bolus = df['bolus'].values

        g_valid = g[~np.isnan(g)]
        n_days = len(g_valid) / STEPS_PER_DAY
        if n_days < 30:
            continue

        tir_overall, tbr_overall, tar_overall = compute_tir(g)

        # First/last 30 days comparison
        days = split_into_days(g)
        first_30 = np.concatenate(days[:30])
        last_30 = np.concatenate(days[-30:]) if len(days) >= 60 else first_30

        tir_first, tbr_first, _ = compute_tir(first_30)
        tir_last, tbr_last, _ = compute_tir(last_30)

        # Daily insulin trend
        bolus_days = split_into_days(bolus)
        daily_insulin = [float(np.nansum(bd)) for bd in bolus_days]
        if len(daily_insulin) >= 60:
            insulin_first = float(np.mean(daily_insulin[:30]))
            insulin_last = float(np.mean(daily_insulin[-30:]))
            insulin_change = (insulin_last - insulin_first) / insulin_first * 100 if insulin_first > 0 else 0
        else:
            insulin_first = float(np.mean(daily_insulin))
            insulin_last = insulin_first
            insulin_change = 0

        # Assessment
        flags = []
        if tir_last < tir_first - 0.05:
            flags.append('TIR_DECLINING')
        if tbr_last > tbr_first + 0.02:
            flags.append('TBR_INCREASING')
        if abs(insulin_change) > 20:
            flags.append('INSULIN_CHANGING')
        if tir_overall < 0.7:
            flags.append('BELOW_TARGET')
        if tbr_overall > 0.04:
            flags.append('EXCESS_HYPO')
        if not flags:
            flags.append('ON_TRACK')

        results[name] = {
            'n_days': round(n_days, 0),
            'tir_overall': round(tir_overall, 3),
            'tbr_overall': round(tbr_overall, 3),
            'tir_first_30': round(tir_first, 3),
            'tir_last_30': round(tir_last, 3),
            'tir_change': round((tir_last - tir_first) * 100, 1),
            'tbr_first_30': round(tbr_first, 3),
            'tbr_last_30': round(tbr_last, 3),
            'insulin_first_30': round(insulin_first, 1),
            'insulin_last_30': round(insulin_last, 1),
            'insulin_change_pct': round(insulin_change, 1),
            'flags': flags
        }

        print(f"  {name}: TIR {tir_first:.0%}→{tir_last:.0%} "
              f"TBR {tbr_first:.1%}→{tbr_last:.1%} "
              f"insulin {insulin_change:+.0f}% → {', '.join(flags)}")

    # Population summary
    on_track = sum(1 for r in results.values() if 'ON_TRACK' in r['flags'])
    declining = sum(1 for r in results.values() if 'TIR_DECLINING' in r['flags'])
    below_target = sum(1 for r in results.values() if 'BELOW_TARGET' in r['flags'])
    print(f"\n  Population: {on_track} on-track, {declining} declining, {below_target} below target")

    if MAKE_FIGS:
        fig, ax = plt.subplots(figsize=(16, 8))
        names = sorted(results.keys())

        # Stacked horizontal bar showing flags per patient
        flag_types = ['ON_TRACK', 'BELOW_TARGET', 'EXCESS_HYPO',
                      'TIR_DECLINING', 'TBR_INCREASING', 'INSULIN_CHANGING']
        colors = ['#2ecc71', '#e74c3c', '#9b59b6', '#e67e22', '#f39c12', '#3498db']

        y = np.arange(len(names))
        for j, flag in enumerate(flag_types):
            vals = [1 if flag in results[n]['flags'] else 0 for n in names]
            left = [sum(1 if ft in results[n]['flags'] else 0
                       for ft in flag_types[:j]) for n in names]
            ax.barh(y, vals, left=left, color=colors[j], label=flag,
                    edgecolor='black', height=0.6)

        ax.set_yticks(y)
        ax.set_yticklabels(names, fontweight='bold', fontsize=12)
        ax.set_xlabel('Number of Flags')
        ax.set_title('EXP-2128: Patient Drift Dashboard',
                     fontsize=14, fontweight='bold')
        ax.legend(fontsize=9, ncol=3, loc='upper right')

        # Add TIR change annotation
        for i, n in enumerate(names):
            change = results[n]['tir_change']
            total_flags = sum(1 if f in results[n]['flags'] else 0 for f in flag_types)
            ax.text(total_flags + 0.1, i, f"TIR: {change:+.1f}pp",
                    va='center', fontsize=9)

        fig.tight_layout()
        fig.savefig(f'{FIG_DIR}/drift-fig08-dashboard.png', dpi=150,
                    bbox_inches='tight')
        plt.close()
        print(f"  → Saved drift-fig08-dashboard.png")

    output = {'experiment': 'EXP-2128', 'title': 'Drift Dashboard',
              'per_patient': results,
              'population': {
                  'on_track': on_track,
                  'declining': declining,
                  'below_target': below_target
              }}
    with open(f'{EXP_DIR}/exp-2128_dashboard.json', 'w') as f:
        json.dump(output, f, indent=2, cls=NumpyEncoder)
    return output


# ── Main ──────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print("=" * 60)
    print("EXP-2121–2128: Exercise Detection & Longitudinal Drift")
    print("=" * 60)

    r1 = exp_2121_exercise_signatures()
    r2 = exp_2122_post_exercise_hypo()
    r3 = exp_2123_activity_patterns()
    r4 = exp_2124_monthly_drift()
    r5 = exp_2125_periodic()
    r6 = exp_2126_isf_drift()
    r7 = exp_2127_proactive_triggers()
    r8 = exp_2128_dashboard()

    print("\n" + "=" * 60)
    print(f"Results: 8/8 experiments completed")
    print(f"Figures saved to {FIG_DIR}/drift-fig01–08")
    print("=" * 60)
