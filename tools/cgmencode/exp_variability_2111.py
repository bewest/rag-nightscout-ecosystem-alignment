#!/usr/bin/env python3
"""
EXP-2111–2118: Glycemic Variability & Temporal Patterns

Investigate what drives day-to-day glucose variability and whether
temporal patterns predict therapy adjustment needs.

EXP-2111: Glycemic variability metrics — GVI, MAGE, CV, LBGI per patient
EXP-2112: Day-type classification — good vs bad days, what distinguishes them
EXP-2113: Circadian stability — which hours are most/least predictable
EXP-2114: Weekly patterns — day-of-week effects on glycemic control
EXP-2115: Streak analysis — runs of good/bad days, persistence
EXP-2116: Entropy and predictability — information-theoretic glucose analysis
EXP-2117: Cross-patient variability drivers — why do some patients vary more
EXP-2118: Actionable pattern detection — which patterns predict therapy needs

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


def compute_daily_metrics(glucose_day):
    """Compute per-day glycemic metrics."""
    g = glucose_day[~np.isnan(glucose_day)]
    if len(g) < STEPS_PER_HOUR * 12:  # need at least 12 hours
        return None

    mean_g = float(np.mean(g))
    std_g = float(np.std(g))
    cv = std_g / mean_g if mean_g > 0 else 0
    tir = float(np.mean((g >= 70) & (g <= 180)))
    tbr = float(np.mean(g < 70))
    tar = float(np.mean(g > 180))
    gmi = 3.31 + 0.02392 * mean_g  # Glucose Management Indicator

    # MAGE: Mean Amplitude of Glycemic Excursions
    diffs = np.abs(np.diff(g))
    threshold = std_g
    excursions = diffs[diffs > threshold]
    mage = float(np.mean(excursions)) if len(excursions) > 0 else 0

    # LBGI: Low Blood Glucose Index
    fbg = 1.509 * (np.log(g) ** 1.084 - 5.381)
    rl = np.where(fbg < 0, 10 * fbg ** 2, 0)
    lbgi = float(np.mean(rl))

    # HBGI: High Blood Glucose Index
    rh = np.where(fbg > 0, 10 * fbg ** 2, 0)
    hbgi = float(np.mean(rh))

    # GVI: Glycemic Variability Index
    line_length = float(np.sum(np.sqrt(1 + np.diff(g) ** 2)))
    ideal_length = len(g) - 1
    gvi = line_length / ideal_length if ideal_length > 0 else 1

    return {
        'mean': round(mean_g, 1),
        'std': round(std_g, 1),
        'cv': round(cv, 3),
        'tir': round(tir, 3),
        'tbr': round(tbr, 3),
        'tar': round(tar, 3),
        'gmi': round(gmi, 2),
        'mage': round(mage, 1),
        'lbgi': round(lbgi, 2),
        'hbgi': round(hbgi, 2),
        'gvi': round(gvi, 2),
        'n_readings': len(g)
    }


def split_into_days(glucose, steps_per_day=STEPS_PER_DAY):
    """Split glucose array into per-day chunks."""
    n_days = len(glucose) // steps_per_day
    days = []
    for d in range(n_days):
        start = d * steps_per_day
        end = start + steps_per_day
        days.append(glucose[start:end])
    return days


# ── EXP-2111: Glycemic Variability Metrics ────────────────────────────
def exp_2111_variability_metrics():
    """Comprehensive glycemic variability profiling per patient."""
    print("\n═══ EXP-2111: Glycemic Variability Metrics ═══")

    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values

        days = split_into_days(g)
        daily_metrics = []
        for day_g in days:
            m = compute_daily_metrics(day_g)
            if m is not None:
                daily_metrics.append(m)

        if len(daily_metrics) < 14:
            results[name] = {'sufficient': False, 'n_days': len(daily_metrics)}
            continue

        # Aggregate
        overall = compute_daily_metrics(g)
        if overall is None:
            continue

        day_to_day_cv = float(np.std([m['mean'] for m in daily_metrics]) /
                              np.mean([m['mean'] for m in daily_metrics]))

        results[name] = {
            'sufficient': True,
            'n_days': len(daily_metrics),
            'overall': overall,
            'day_to_day_cv': round(day_to_day_cv, 3),
            'tir_range': [round(float(np.percentile([m['tir'] for m in daily_metrics], 10)), 3),
                         round(float(np.percentile([m['tir'] for m in daily_metrics], 90)), 3)],
            'mage_median': round(float(np.median([m['mage'] for m in daily_metrics])), 1),
            'lbgi_median': round(float(np.median([m['lbgi'] for m in daily_metrics])), 2),
            'hbgi_median': round(float(np.median([m['hbgi'] for m in daily_metrics])), 2),
            'cv_median': round(float(np.median([m['cv'] for m in daily_metrics])), 3)
        }

        print(f"  {name}: CV={overall['cv']:.1%} MAGE={overall['mage']:.0f} "
              f"LBGI={overall['lbgi']:.1f} HBGI={overall['hbgi']:.1f} "
              f"day-to-day CV={day_to_day_cv:.1%} ({len(daily_metrics)} days)")

    if MAKE_FIGS:
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        names = sorted([n for n in results if results[n].get('sufficient', False)])
        x = np.arange(len(names))

        ax = axes[0, 0]
        vals = [results[n]['overall']['cv'] * 100 for n in names]
        colors = ['green' if v < 36 else 'red' for v in vals]
        ax.bar(x, vals, color=colors, edgecolor='black')
        ax.axhline(36, color='red', linestyle='--', label='CV target (<36%)')
        ax.set_xticks(x)
        ax.set_xticklabels(names, fontweight='bold')
        ax.set_ylabel('CV (%)')
        ax.set_title('Coefficient of Variation', fontweight='bold')
        ax.legend()

        ax = axes[0, 1]
        vals = [results[n]['overall']['mage'] for n in names]
        ax.bar(x, vals, color='C1', edgecolor='black')
        ax.set_xticks(x)
        ax.set_xticklabels(names, fontweight='bold')
        ax.set_ylabel('MAGE (mg/dL)')
        ax.set_title('Mean Amplitude of Glycemic Excursions', fontweight='bold')

        ax = axes[1, 0]
        lbgi = [results[n]['overall']['lbgi'] for n in names]
        hbgi = [results[n]['overall']['hbgi'] for n in names]
        ax.bar(x - 0.15, lbgi, 0.3, label='LBGI (hypo risk)', color='C3', edgecolor='black')
        ax.bar(x + 0.15, hbgi, 0.3, label='HBGI (hyper risk)', color='C1', edgecolor='black')
        ax.set_xticks(x)
        ax.set_xticklabels(names, fontweight='bold')
        ax.set_ylabel('Risk Index')
        ax.set_title('Low/High Blood Glucose Index', fontweight='bold')
        ax.legend()

        ax = axes[1, 1]
        vals = [results[n]['day_to_day_cv'] * 100 for n in names]
        ax.bar(x, vals, color='C4', edgecolor='black')
        ax.set_xticks(x)
        ax.set_xticklabels(names, fontweight='bold')
        ax.set_ylabel('Day-to-Day CV (%)')
        ax.set_title('Inter-Day Glucose Variability', fontweight='bold')

        fig.suptitle('EXP-2111: Glycemic Variability Metrics',
                     fontsize=14, fontweight='bold')
        fig.tight_layout(rect=[0, 0, 1, 0.96])
        fig.savefig(f'{FIG_DIR}/var-fig01-metrics.png', dpi=150,
                    bbox_inches='tight')
        plt.close()
        print(f"  → Saved var-fig01-metrics.png")

    output = {'experiment': 'EXP-2111', 'title': 'Glycemic Variability Metrics',
              'per_patient': results}
    with open(f'{EXP_DIR}/exp-2111_variability.json', 'w') as f:
        json.dump(output, f, indent=2, cls=NumpyEncoder)
    return output


# ── EXP-2112: Day-Type Classification ─────────────────────────────────
def exp_2112_day_types():
    """Classify days as good/bad and identify distinguishing features."""
    print("\n═══ EXP-2112: Day-Type Classification ═══")

    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        bolus = df['bolus'].values
        carbs = df['carbs'].values

        days_g = split_into_days(g)
        days_b = split_into_days(bolus)
        days_c = split_into_days(carbs)

        good_days = []
        bad_days = []

        for d_idx, (dg, db, dc) in enumerate(zip(days_g, days_b, days_c)):
            m = compute_daily_metrics(dg)
            if m is None:
                continue

            day_info = {
                'day': d_idx,
                'tir': m['tir'],
                'tbr': m['tbr'],
                'mean': m['mean'],
                'cv': m['cv'],
                'total_bolus': float(np.nansum(db)),
                'total_carbs': float(np.nansum(dc)),
                'n_boluses': int(np.sum(~np.isnan(db) & (db > 0))),
                'n_meals': int(np.sum(~np.isnan(dc) & (dc > 0))),
            }

            if m['tir'] >= 0.7 and m['tbr'] < 0.04:
                good_days.append(day_info)
            elif m['tir'] < 0.5 or m['tbr'] >= 0.1:
                bad_days.append(day_info)

        if len(good_days) < 5 or len(bad_days) < 5:
            results[name] = {
                'sufficient': False,
                'n_good': len(good_days),
                'n_bad': len(bad_days)
            }
            print(f"  {name}: insufficient (good={len(good_days)} bad={len(bad_days)})")
            continue

        # Compare good vs bad
        good_carbs = float(np.mean([d['total_carbs'] for d in good_days]))
        bad_carbs = float(np.mean([d['total_carbs'] for d in bad_days]))
        good_bolus = float(np.mean([d['total_bolus'] for d in good_days]))
        bad_bolus = float(np.mean([d['total_bolus'] for d in bad_days]))
        good_meals = float(np.mean([d['n_meals'] for d in good_days]))
        bad_meals = float(np.mean([d['n_meals'] for d in bad_days]))
        good_cv = float(np.mean([d['cv'] for d in good_days]))
        bad_cv = float(np.mean([d['cv'] for d in bad_days]))

        results[name] = {
            'sufficient': True,
            'n_good': len(good_days),
            'n_bad': len(bad_days),
            'good_pct': round(len(good_days) / (len(good_days) + len(bad_days)), 2),
            'good_day': {
                'mean_carbs': round(good_carbs, 0),
                'mean_bolus': round(good_bolus, 1),
                'mean_meals': round(good_meals, 1),
                'mean_cv': round(good_cv, 3)
            },
            'bad_day': {
                'mean_carbs': round(bad_carbs, 0),
                'mean_bolus': round(bad_bolus, 1),
                'mean_meals': round(bad_meals, 1),
                'mean_cv': round(bad_cv, 3)
            },
            'carb_ratio': round(bad_carbs / good_carbs, 2) if good_carbs > 0 else None,
            'bolus_ratio': round(bad_bolus / good_bolus, 2) if good_bolus > 0 else None
        }

        cr = f"{bad_carbs/good_carbs:.2f}×" if good_carbs > 0 else "N/A"
        print(f"  {name}: good={len(good_days)} bad={len(bad_days)} "
              f"carb ratio={cr} CV good={good_cv:.1%} bad={bad_cv:.1%}")

    if MAKE_FIGS:
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))
        names = sorted([n for n in results if results[n].get('sufficient', False)])
        x = np.arange(len(names))

        ax = axes[0]
        good_carbs = [results[n]['good_day']['mean_carbs'] for n in names]
        bad_carbs = [results[n]['bad_day']['mean_carbs'] for n in names]
        ax.bar(x - 0.15, good_carbs, 0.3, label='Good Days', color='C2', edgecolor='black')
        ax.bar(x + 0.15, bad_carbs, 0.3, label='Bad Days', color='C3', edgecolor='black')
        ax.set_xticks(x)
        ax.set_xticklabels(names, fontweight='bold')
        ax.set_ylabel('Total Daily Carbs (g)')
        ax.set_title('Daily Carbs: Good vs Bad Days', fontweight='bold')
        ax.legend()

        ax = axes[1]
        good_cv = [results[n]['good_day']['mean_cv'] * 100 for n in names]
        bad_cv = [results[n]['bad_day']['mean_cv'] * 100 for n in names]
        ax.bar(x - 0.15, good_cv, 0.3, label='Good Days', color='C2', edgecolor='black')
        ax.bar(x + 0.15, bad_cv, 0.3, label='Bad Days', color='C3', edgecolor='black')
        ax.set_xticks(x)
        ax.set_xticklabels(names, fontweight='bold')
        ax.set_ylabel('CV (%)')
        ax.set_title('Glucose CV: Good vs Bad Days', fontweight='bold')
        ax.legend()

        fig.suptitle('EXP-2112: Good vs Bad Day Characteristics',
                     fontsize=14, fontweight='bold')
        fig.tight_layout(rect=[0, 0, 1, 0.95])
        fig.savefig(f'{FIG_DIR}/var-fig02-day-types.png', dpi=150,
                    bbox_inches='tight')
        plt.close()
        print(f"  → Saved var-fig02-day-types.png")

    output = {'experiment': 'EXP-2112', 'title': 'Day-Type Classification',
              'per_patient': results}
    with open(f'{EXP_DIR}/exp-2112_day_types.json', 'w') as f:
        json.dump(output, f, indent=2, cls=NumpyEncoder)
    return output


# ── EXP-2113: Circadian Stability ─────────────────────────────────────
def exp_2113_circadian_stability():
    """Which hours of the day are most/least predictable?"""
    print("\n═══ EXP-2113: Circadian Stability ═══")

    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values

        hourly_stats = {}
        for h in range(24):
            # Extract all glucose values at this hour
            start_step = h * STEPS_PER_HOUR
            hour_values = []
            for d in range(len(g) // STEPS_PER_DAY):
                for s in range(STEPS_PER_HOUR):
                    idx = d * STEPS_PER_DAY + start_step + s
                    if idx < len(g) and not np.isnan(g[idx]):
                        hour_values.append(g[idx])

            if len(hour_values) < 30:
                continue

            arr = np.array(hour_values)
            hourly_stats[h] = {
                'mean': round(float(np.mean(arr)), 1),
                'std': round(float(np.std(arr)), 1),
                'cv': round(float(np.std(arr) / np.mean(arr)), 3),
                'tir': round(float(np.mean((arr >= 70) & (arr <= 180))), 3),
                'p10': round(float(np.percentile(arr, 10)), 1),
                'p90': round(float(np.percentile(arr, 90)), 1),
                'range_90': round(float(np.percentile(arr, 90) - np.percentile(arr, 10)), 1),
                'n': len(hour_values)
            }

        if len(hourly_stats) < 20:
            results[name] = {'sufficient': False}
            continue

        # Find best/worst hours
        best_hour = min(hourly_stats, key=lambda h: hourly_stats[h]['cv'])
        worst_hour = max(hourly_stats, key=lambda h: hourly_stats[h]['cv'])
        best_tir_hour = max(hourly_stats, key=lambda h: hourly_stats[h]['tir'])
        worst_tir_hour = min(hourly_stats, key=lambda h: hourly_stats[h]['tir'])

        results[name] = {
            'sufficient': True,
            'hourly': hourly_stats,
            'most_stable_hour': best_hour,
            'least_stable_hour': worst_hour,
            'best_tir_hour': best_tir_hour,
            'worst_tir_hour': worst_tir_hour,
            'stability_ratio': round(hourly_stats[worst_hour]['cv'] /
                                    hourly_stats[best_hour]['cv'], 2)
        }

        print(f"  {name}: stable={best_hour}:00 (CV={hourly_stats[best_hour]['cv']:.1%}) "
              f"unstable={worst_hour}:00 (CV={hourly_stats[worst_hour]['cv']:.1%}) "
              f"ratio={results[name]['stability_ratio']:.1f}×")

    if MAKE_FIGS:
        fig, axes = plt.subplots(2, 1, figsize=(14, 10))
        names = sorted([n for n in results if results[n].get('sufficient', False)])

        # Hourly CV heatmap
        ax = axes[0]
        matrix = np.zeros((len(names), 24))
        for i, n in enumerate(names):
            for h in range(24):
                if h in results[n]['hourly']:
                    matrix[i, h] = results[n]['hourly'][h]['cv'] * 100
        im = ax.imshow(matrix, aspect='auto', cmap='RdYlGn_r',
                       vmin=15, vmax=50)
        ax.set_yticks(range(len(names)))
        ax.set_yticklabels(names, fontweight='bold')
        ax.set_xticks(range(24))
        ax.set_xticklabels([f'{h}:00' for h in range(24)], rotation=45, fontsize=8)
        ax.set_title('Hourly Glucose CV (%) — Red = More Variable', fontweight='bold')
        plt.colorbar(im, ax=ax, label='CV (%)')

        # Hourly TIR
        ax = axes[1]
        for n in names:
            hours = sorted(results[n]['hourly'].keys())
            tirs = [results[n]['hourly'][h]['tir'] * 100 for h in hours]
            ax.plot(hours, tirs, marker='o', markersize=3, alpha=0.6, label=n)
        ax.axhline(70, color='green', linestyle='--', alpha=0.5)
        ax.set_xlabel('Hour')
        ax.set_ylabel('TIR (%)')
        ax.set_title('Hourly Time-in-Range', fontweight='bold')
        ax.legend(fontsize=8, ncol=3)
        ax.set_xlim(0, 23)

        fig.suptitle('EXP-2113: Circadian Stability Analysis',
                     fontsize=14, fontweight='bold')
        fig.tight_layout(rect=[0, 0, 1, 0.96])
        fig.savefig(f'{FIG_DIR}/var-fig03-circadian.png', dpi=150,
                    bbox_inches='tight')
        plt.close()
        print(f"  → Saved var-fig03-circadian.png")

    output = {'experiment': 'EXP-2113', 'title': 'Circadian Stability',
              'per_patient': results}
    with open(f'{EXP_DIR}/exp-2113_circadian.json', 'w') as f:
        json.dump(output, f, indent=2, cls=NumpyEncoder)
    return output


# ── EXP-2114: Weekly Patterns ─────────────────────────────────────────
def exp_2114_weekly_patterns():
    """Day-of-week effects on glycemic control."""
    print("\n═══ EXP-2114: Weekly Patterns ═══")

    results = {}
    dow_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values

        days = split_into_days(g)
        dow_metrics = {d: [] for d in range(7)}

        for d_idx, day_g in enumerate(days):
            m = compute_daily_metrics(day_g)
            if m is None:
                continue
            dow = d_idx % 7
            dow_metrics[dow].append(m)

        has_data = all(len(dow_metrics[d]) >= 5 for d in range(7))
        if not has_data:
            results[name] = {'sufficient': False}
            print(f"  {name}: insufficient")
            continue

        dow_summary = {}
        for d in range(7):
            metrics = dow_metrics[d]
            dow_summary[dow_names[d]] = {
                'mean_tir': round(float(np.mean([m['tir'] for m in metrics])), 3),
                'mean_cv': round(float(np.mean([m['cv'] for m in metrics])), 3),
                'mean_glucose': round(float(np.mean([m['mean'] for m in metrics])), 1),
                'n_days': len(metrics)
            }

        tirs = [dow_summary[dow_names[d]]['mean_tir'] for d in range(7)]
        best_dow = dow_names[np.argmax(tirs)]
        worst_dow = dow_names[np.argmin(tirs)]
        weekend = (np.mean([dow_summary['Sat']['mean_tir'], dow_summary['Sun']['mean_tir']]))
        weekday = (np.mean([dow_summary[d]['mean_tir'] for d in ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']]))

        results[name] = {
            'sufficient': True,
            'dow_summary': dow_summary,
            'best_day': best_dow,
            'worst_day': worst_dow,
            'weekend_tir': round(weekend, 3),
            'weekday_tir': round(weekday, 3),
            'weekend_effect': round((weekend - weekday) * 100, 1)
        }

        effect = results[name]['weekend_effect']
        direction = "better" if effect > 0 else "worse"
        print(f"  {name}: best={best_dow} worst={worst_dow} "
              f"weekend {direction} by {abs(effect):.1f}pp")

    if MAKE_FIGS:
        fig, ax = plt.subplots(figsize=(14, 7))
        names = sorted([n for n in results if results[n].get('sufficient', False)])

        for n in names:
            tirs = [results[n]['dow_summary'][d]['mean_tir'] * 100 for d in dow_names]
            ax.plot(dow_names, tirs, marker='o', label=n, alpha=0.7)

        ax.axhline(70, color='green', linestyle='--', alpha=0.5, label='TIR target')
        ax.axvspan(4.5, 6.5, color='lightyellow', alpha=0.3, label='Weekend')
        ax.set_ylabel('TIR (%)')
        ax.set_title('EXP-2114: Day-of-Week TIR Patterns',
                     fontsize=14, fontweight='bold')
        ax.legend(fontsize=8, ncol=3)
        ax.grid(axis='y', alpha=0.3)

        fig.tight_layout()
        fig.savefig(f'{FIG_DIR}/var-fig04-weekly.png', dpi=150,
                    bbox_inches='tight')
        plt.close()
        print(f"  → Saved var-fig04-weekly.png")

    output = {'experiment': 'EXP-2114', 'title': 'Weekly Patterns',
              'per_patient': results}
    with open(f'{EXP_DIR}/exp-2114_weekly.json', 'w') as f:
        json.dump(output, f, indent=2, cls=NumpyEncoder)
    return output


# ── EXP-2115: Streak Analysis ─────────────────────────────────────────
def exp_2115_streaks():
    """Runs of good/bad days — is control persistent or random?"""
    print("\n═══ EXP-2115: Streak Analysis ═══")

    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values

        days = split_into_days(g)
        day_quality = []  # 1=good, 0=bad, -1=neutral

        for day_g in days:
            m = compute_daily_metrics(day_g)
            if m is None:
                day_quality.append(-1)
                continue
            if m['tir'] >= 0.7 and m['tbr'] < 0.04:
                day_quality.append(1)
            elif m['tir'] < 0.5 or m['tbr'] >= 0.1:
                day_quality.append(0)
            else:
                day_quality.append(-1)

        # Compute streaks
        good_streaks = []
        bad_streaks = []
        current_streak = 0
        current_type = -1

        for q in day_quality:
            if q == -1:
                if current_streak > 0:
                    if current_type == 1:
                        good_streaks.append(current_streak)
                    elif current_type == 0:
                        bad_streaks.append(current_streak)
                current_streak = 0
                current_type = -1
            elif q == current_type:
                current_streak += 1
            else:
                if current_streak > 0:
                    if current_type == 1:
                        good_streaks.append(current_streak)
                    elif current_type == 0:
                        bad_streaks.append(current_streak)
                current_streak = 1
                current_type = q

        if current_streak > 0:
            if current_type == 1:
                good_streaks.append(current_streak)
            elif current_type == 0:
                bad_streaks.append(current_streak)

        # Autocorrelation of daily TIR
        daily_tirs = []
        for day_g in days:
            m = compute_daily_metrics(day_g)
            if m is not None:
                daily_tirs.append(m['tir'])

        if len(daily_tirs) < 14:
            results[name] = {'sufficient': False}
            continue

        tir_arr = np.array(daily_tirs)
        tir_centered = tir_arr - np.mean(tir_arr)
        if np.std(tir_arr) > 0.001:
            lag1_corr = float(np.corrcoef(tir_centered[:-1], tir_centered[1:])[0, 1])
        else:
            lag1_corr = 0

        results[name] = {
            'sufficient': True,
            'n_days': len(day_quality),
            'n_good': sum(1 for q in day_quality if q == 1),
            'n_bad': sum(1 for q in day_quality if q == 0),
            'good_streak_max': max(good_streaks) if good_streaks else 0,
            'good_streak_mean': round(float(np.mean(good_streaks)), 1) if good_streaks else 0,
            'bad_streak_max': max(bad_streaks) if bad_streaks else 0,
            'bad_streak_mean': round(float(np.mean(bad_streaks)), 1) if bad_streaks else 0,
            'lag1_autocorr': round(lag1_corr, 3),
            'persistent': abs(lag1_corr) > 0.15
        }

        persist = "YES" if abs(lag1_corr) > 0.15 else "NO"
        print(f"  {name}: good streaks max={results[name]['good_streak_max']} "
              f"bad max={results[name]['bad_streak_max']} "
              f"lag1={lag1_corr:.3f} persistent={persist}")

    if MAKE_FIGS:
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))
        names = sorted([n for n in results if results[n].get('sufficient', False)])
        x = np.arange(len(names))

        ax = axes[0]
        good_max = [results[n]['good_streak_max'] for n in names]
        bad_max = [results[n]['bad_streak_max'] for n in names]
        ax.bar(x - 0.15, good_max, 0.3, label='Good Streak Max', color='C2', edgecolor='black')
        ax.bar(x + 0.15, bad_max, 0.3, label='Bad Streak Max', color='C3', edgecolor='black')
        ax.set_xticks(x)
        ax.set_xticklabels(names, fontweight='bold')
        ax.set_ylabel('Streak Length (days)')
        ax.set_title('Maximum Streak Length', fontweight='bold')
        ax.legend()

        ax = axes[1]
        lag1 = [results[n]['lag1_autocorr'] for n in names]
        colors = ['C2' if v > 0.15 else 'C3' if v < -0.15 else 'gray' for v in lag1]
        ax.bar(x, lag1, color=colors, edgecolor='black')
        ax.axhline(0.15, color='green', linestyle='--', alpha=0.5)
        ax.axhline(-0.15, color='red', linestyle='--', alpha=0.5)
        ax.set_xticks(x)
        ax.set_xticklabels(names, fontweight='bold')
        ax.set_ylabel('Lag-1 Autocorrelation')
        ax.set_title('Daily TIR Persistence', fontweight='bold')

        fig.suptitle('EXP-2115: Streak Analysis',
                     fontsize=14, fontweight='bold')
        fig.tight_layout(rect=[0, 0, 1, 0.95])
        fig.savefig(f'{FIG_DIR}/var-fig05-streaks.png', dpi=150,
                    bbox_inches='tight')
        plt.close()
        print(f"  → Saved var-fig05-streaks.png")

    output = {'experiment': 'EXP-2115', 'title': 'Streak Analysis',
              'per_patient': results}
    with open(f'{EXP_DIR}/exp-2115_streaks.json', 'w') as f:
        json.dump(output, f, indent=2, cls=NumpyEncoder)
    return output


# ── EXP-2116: Entropy and Predictability ──────────────────────────────
def exp_2116_entropy():
    """Information-theoretic analysis of glucose predictability."""
    print("\n═══ EXP-2116: Entropy and Predictability ═══")

    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        g_valid = g[~np.isnan(g)]

        if len(g_valid) < STEPS_PER_DAY * 7:
            results[name] = {'sufficient': False}
            continue

        # Bin glucose into 10 mg/dL bins for entropy calculation
        bins = np.arange(40, 401, 10)
        hist, _ = np.histogram(g_valid, bins=bins)
        probs = hist / hist.sum()
        probs = probs[probs > 0]
        entropy = float(-np.sum(probs * np.log2(probs)))
        max_entropy = np.log2(len(bins) - 1)
        normalized_entropy = entropy / max_entropy

        # Sample entropy (regularity measure)
        # Use simplified approach: sequential differences
        diffs = np.diff(g_valid)
        diff_bins = np.arange(-50, 51, 5)
        diff_hist, _ = np.histogram(diffs, bins=diff_bins)
        diff_probs = diff_hist / diff_hist.sum()
        diff_probs = diff_probs[diff_probs > 0]
        diff_entropy = float(-np.sum(diff_probs * np.log2(diff_probs)))

        # Conditional entropy: how much does knowing current glucose reduce
        # uncertainty about the next reading?
        # Approximate as H(diff) = H(next|current) for stationary process
        conditional_entropy = diff_entropy
        mutual_info = entropy - conditional_entropy

        # Predictability score: how much of the entropy is resolved by knowing state
        predictability = 1 - (conditional_entropy / entropy) if entropy > 0 else 0

        # Time-scale analysis: entropy at different resolutions
        scale_entropy = {}
        for scale in [1, 3, 6, 12, 36]:  # 5min, 15min, 30min, 1h, 3h
            decimated = g_valid[::scale]
            h, _ = np.histogram(decimated, bins=bins)
            p = h / h.sum()
            p = p[p > 0]
            scale_entropy[f'{scale * 5}min'] = round(float(-np.sum(p * np.log2(p))), 3)

        results[name] = {
            'sufficient': True,
            'entropy_bits': round(entropy, 3),
            'max_entropy_bits': round(max_entropy, 3),
            'normalized_entropy': round(normalized_entropy, 3),
            'diff_entropy': round(diff_entropy, 3),
            'conditional_entropy': round(conditional_entropy, 3),
            'mutual_information': round(mutual_info, 3),
            'predictability': round(predictability, 3),
            'scale_entropy': scale_entropy,
            'n_readings': len(g_valid)
        }

        print(f"  {name}: H={entropy:.2f}bits norm={normalized_entropy:.1%} "
              f"predictability={predictability:.1%} MI={mutual_info:.2f}bits")

    if MAKE_FIGS:
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))
        names = sorted([n for n in results if results[n].get('sufficient', False)])
        x = np.arange(len(names))

        ax = axes[0]
        vals = [results[n]['normalized_entropy'] * 100 for n in names]
        colors = ['green' if v < 70 else 'orange' if v < 80 else 'red' for v in vals]
        ax.bar(x, vals, color=colors, edgecolor='black')
        ax.set_xticks(x)
        ax.set_xticklabels(names, fontweight='bold')
        ax.set_ylabel('Normalized Entropy (%)')
        ax.set_title('Glucose Distribution Entropy', fontweight='bold')

        ax = axes[1]
        pred = [results[n]['predictability'] * 100 for n in names]
        ax.bar(x, pred, color='C0', edgecolor='black')
        ax.set_xticks(x)
        ax.set_xticklabels(names, fontweight='bold')
        ax.set_ylabel('Predictability (%)')
        ax.set_title('Next-Step Predictability', fontweight='bold')

        fig.suptitle('EXP-2116: Entropy and Predictability',
                     fontsize=14, fontweight='bold')
        fig.tight_layout(rect=[0, 0, 1, 0.95])
        fig.savefig(f'{FIG_DIR}/var-fig06-entropy.png', dpi=150,
                    bbox_inches='tight')
        plt.close()
        print(f"  → Saved var-fig06-entropy.png")

    output = {'experiment': 'EXP-2116', 'title': 'Entropy and Predictability',
              'per_patient': results}
    with open(f'{EXP_DIR}/exp-2116_entropy.json', 'w') as f:
        json.dump(output, f, indent=2, cls=NumpyEncoder)
    return output


# ── EXP-2117: Cross-Patient Variability Drivers ──────────────────────
def exp_2117_variability_drivers():
    """Why do some patients vary more? What predicts variability?"""
    print("\n═══ EXP-2117: Cross-Patient Variability Drivers ═══")

    patient_profiles = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        bolus = df['bolus'].values
        carbs = df['carbs'].values

        g_valid = g[~np.isnan(g)]
        if len(g_valid) < STEPS_PER_DAY:
            continue

        n_days = len(g_valid) / STEPS_PER_DAY

        patient_profiles[name] = {
            'cv': float(np.std(g_valid) / np.mean(g_valid)),
            'mean_glucose': float(np.mean(g_valid)),
            'tir': float(np.mean((g_valid >= 70) & (g_valid <= 180))),
            'daily_insulin': float(np.nansum(bolus) / n_days),
            'daily_carbs': float(np.nansum(carbs) / n_days),
            'meals_per_day': float(np.sum(~np.isnan(carbs) & (carbs > 0)) / n_days),
            'boluses_per_day': float(np.sum(~np.isnan(bolus) & (bolus > 0)) / n_days),
            'n_days': round(n_days, 0)
        }

    # Compute correlations between variability and drivers
    names = sorted(patient_profiles.keys())
    cvs = np.array([patient_profiles[n]['cv'] for n in names])

    correlations = {}
    for feature in ['mean_glucose', 'daily_insulin', 'daily_carbs',
                    'meals_per_day', 'boluses_per_day']:
        vals = np.array([patient_profiles[n][feature] for n in names])
        if np.std(vals) > 0:
            r = float(np.corrcoef(cvs, vals)[0, 1])
            correlations[feature] = round(r, 3)

    # Rank by CV
    ranked = sorted(names, key=lambda n: patient_profiles[n]['cv'])
    most_stable = ranked[0]
    most_variable = ranked[-1]

    results = {
        'patient_profiles': patient_profiles,
        'correlations': correlations,
        'most_stable': most_stable,
        'most_variable': most_variable,
        'cv_range': [round(patient_profiles[ranked[0]]['cv'], 3),
                    round(patient_profiles[ranked[-1]]['cv'], 3)]
    }

    print(f"  Most stable: {most_stable} (CV={patient_profiles[most_stable]['cv']:.1%})")
    print(f"  Most variable: {most_variable} (CV={patient_profiles[most_variable]['cv']:.1%})")
    print(f"  Correlations with CV:")
    for feat, r in sorted(correlations.items(), key=lambda x: abs(x[1]), reverse=True):
        print(f"    {feat}: r={r:.3f}")

    if MAKE_FIGS:
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))

        ax = axes[0, 0]
        cvs_pct = [patient_profiles[n]['cv'] * 100 for n in names]
        ax.bar(range(len(names)), cvs_pct, color='C0', edgecolor='black')
        ax.set_xticks(range(len(names)))
        ax.set_xticklabels(names, fontweight='bold')
        ax.set_ylabel('CV (%)')
        ax.set_title('Glucose CV by Patient', fontweight='bold')
        ax.axhline(36, color='red', linestyle='--', label='Target (<36%)')
        ax.legend()

        ax = axes[0, 1]
        carbs = [patient_profiles[n]['daily_carbs'] for n in names]
        ax.scatter(carbs, cvs_pct, s=100, c='C1', edgecolor='black')
        for i, n in enumerate(names):
            ax.annotate(n, (carbs[i], cvs_pct[i]), fontsize=9, fontweight='bold')
        ax.set_xlabel('Daily Carbs (g)')
        ax.set_ylabel('CV (%)')
        ax.set_title(f'Carbs vs Variability (r={correlations.get("daily_carbs", 0):.2f})',
                     fontweight='bold')

        ax = axes[1, 0]
        insulin = [patient_profiles[n]['daily_insulin'] for n in names]
        ax.scatter(insulin, cvs_pct, s=100, c='C2', edgecolor='black')
        for i, n in enumerate(names):
            ax.annotate(n, (insulin[i], cvs_pct[i]), fontsize=9, fontweight='bold')
        ax.set_xlabel('Daily Insulin (U)')
        ax.set_ylabel('CV (%)')
        ax.set_title(f'Insulin vs Variability (r={correlations.get("daily_insulin", 0):.2f})',
                     fontweight='bold')

        ax = axes[1, 1]
        meals = [patient_profiles[n]['meals_per_day'] for n in names]
        ax.scatter(meals, cvs_pct, s=100, c='C4', edgecolor='black')
        for i, n in enumerate(names):
            ax.annotate(n, (meals[i], cvs_pct[i]), fontsize=9, fontweight='bold')
        ax.set_xlabel('Meals per Day')
        ax.set_ylabel('CV (%)')
        ax.set_title(f'Meals vs Variability (r={correlations.get("meals_per_day", 0):.2f})',
                     fontweight='bold')

        fig.suptitle('EXP-2117: Cross-Patient Variability Drivers',
                     fontsize=14, fontweight='bold')
        fig.tight_layout(rect=[0, 0, 1, 0.96])
        fig.savefig(f'{FIG_DIR}/var-fig07-drivers.png', dpi=150,
                    bbox_inches='tight')
        plt.close()
        print(f"  → Saved var-fig07-drivers.png")

    output = {'experiment': 'EXP-2117', 'title': 'Cross-Patient Variability Drivers',
              'results': results}
    with open(f'{EXP_DIR}/exp-2117_drivers.json', 'w') as f:
        json.dump(output, f, indent=2, cls=NumpyEncoder)
    return output


# ── EXP-2118: Actionable Pattern Detection ───────────────────────────
def exp_2118_actionable_patterns():
    """Which variability patterns predict therapy adjustment needs?"""
    print("\n═══ EXP-2118: Actionable Pattern Detection ═══")

    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values

        days = split_into_days(g)
        daily_tirs = []
        for day_g in days:
            m = compute_daily_metrics(day_g)
            if m is not None:
                daily_tirs.append(m['tir'])

        if len(daily_tirs) < 30:
            results[name] = {'sufficient': False}
            continue

        tir_arr = np.array(daily_tirs)

        # Pattern 1: Rolling deterioration (7-day trend)
        window = 7
        rolling_mean = np.convolve(tir_arr, np.ones(window)/window, mode='valid')
        if len(rolling_mean) > window:
            # Trend in rolling mean
            x_trend = np.arange(len(rolling_mean))
            slope = float(np.polyfit(x_trend, rolling_mean, 1)[0])
            deteriorating = slope < -0.001  # losing >0.1pp/day
        else:
            slope = 0
            deteriorating = False

        # Pattern 2: Volatility clustering (GARCH-like)
        tir_diffs = np.abs(np.diff(tir_arr))
        vol_autocorr = float(np.corrcoef(tir_diffs[:-1], tir_diffs[1:])[0, 1]) if len(tir_diffs) > 2 else 0
        vol_clusters = vol_autocorr > 0.15

        # Pattern 3: Range compression (converging to narrow band — may mean
        # therapy is working but room for improvement)
        first_half_std = float(np.std(tir_arr[:len(tir_arr)//2]))
        second_half_std = float(np.std(tir_arr[len(tir_arr)//2:]))
        compressing = second_half_std < first_half_std * 0.7

        # Pattern 4: Bimodal days (two distinct modes suggesting two different states)
        p25 = float(np.percentile(tir_arr, 25))
        p75 = float(np.percentile(tir_arr, 75))
        iqr = p75 - p25
        bimodal = iqr > 0.25  # large spread suggests multiple modes

        # Recommendations
        recommendations = []
        if deteriorating:
            recommendations.append('INVESTIGATE_DECLINE')
        if vol_clusters:
            recommendations.append('VOLATILE_CONTROL')
        if bimodal:
            recommendations.append('DUAL_MODE_BEHAVIOR')
        if compressing:
            recommendations.append('THERAPY_STABILIZING')
        if not recommendations:
            recommendations.append('STABLE')

        results[name] = {
            'sufficient': True,
            'n_days': len(daily_tirs),
            'tir_trend_slope': round(slope * 100, 3),
            'deteriorating': deteriorating,
            'volatility_autocorr': round(vol_autocorr, 3),
            'volatility_clusters': vol_clusters,
            'first_half_std': round(first_half_std, 3),
            'second_half_std': round(second_half_std, 3),
            'compressing': compressing,
            'iqr': round(iqr, 3),
            'bimodal': bimodal,
            'recommendations': recommendations
        }

        flags = ', '.join(recommendations)
        print(f"  {name}: slope={slope*100:.3f}pp/day "
              f"vol_r={vol_autocorr:.2f} IQR={iqr:.2f} → {flags}")

    if MAKE_FIGS:
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        names = sorted([n for n in results if results[n].get('sufficient', False)])

        ax = axes[0, 0]
        slopes = [results[n]['tir_trend_slope'] for n in names]
        colors = ['red' if s < -0.1 else 'green' if s > 0.1 else 'gray' for s in slopes]
        ax.bar(range(len(names)), slopes, color=colors, edgecolor='black')
        ax.set_xticks(range(len(names)))
        ax.set_xticklabels(names, fontweight='bold')
        ax.set_ylabel('TIR Trend (pp/day)')
        ax.set_title('Daily TIR Trend', fontweight='bold')
        ax.axhline(0, color='black', linewidth=0.5)

        ax = axes[0, 1]
        vol = [results[n]['volatility_autocorr'] for n in names]
        colors = ['C3' if v > 0.15 else 'C2' for v in vol]
        ax.bar(range(len(names)), vol, color=colors, edgecolor='black')
        ax.set_xticks(range(len(names)))
        ax.set_xticklabels(names, fontweight='bold')
        ax.set_ylabel('Volatility Autocorrelation')
        ax.set_title('Volatility Clustering', fontweight='bold')
        ax.axhline(0.15, color='red', linestyle='--')

        ax = axes[1, 0]
        iqrs = [results[n]['iqr'] * 100 for n in names]
        colors = ['C3' if v > 25 else 'C2' for v in iqrs]
        ax.bar(range(len(names)), iqrs, color=colors, edgecolor='black')
        ax.set_xticks(range(len(names)))
        ax.set_xticklabels(names, fontweight='bold')
        ax.set_ylabel('TIR IQR (pp)')
        ax.set_title('Day-to-Day TIR Spread', fontweight='bold')

        ax = axes[1, 1]
        # Recommendation summary
        rec_counts = {}
        for n in names:
            for r in results[n]['recommendations']:
                rec_counts[r] = rec_counts.get(r, 0) + 1
        recs = sorted(rec_counts.keys())
        counts = [rec_counts[r] for r in recs]
        ax.barh(recs, counts, color='C0', edgecolor='black')
        ax.set_xlabel('Number of Patients')
        ax.set_title('Pattern-Based Recommendations', fontweight='bold')

        fig.suptitle('EXP-2118: Actionable Pattern Detection',
                     fontsize=14, fontweight='bold')
        fig.tight_layout(rect=[0, 0, 1, 0.96])
        fig.savefig(f'{FIG_DIR}/var-fig08-patterns.png', dpi=150,
                    bbox_inches='tight')
        plt.close()
        print(f"  → Saved var-fig08-patterns.png")

    output = {'experiment': 'EXP-2118', 'title': 'Actionable Pattern Detection',
              'per_patient': results}
    with open(f'{EXP_DIR}/exp-2118_patterns.json', 'w') as f:
        json.dump(output, f, indent=2, cls=NumpyEncoder)
    return output


# ── Main ──────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print("=" * 60)
    print("EXP-2111–2118: Glycemic Variability & Temporal Patterns")
    print("=" * 60)

    r1 = exp_2111_variability_metrics()
    r2 = exp_2112_day_types()
    r3 = exp_2113_circadian_stability()
    r4 = exp_2114_weekly_patterns()
    r5 = exp_2115_streaks()
    r6 = exp_2116_entropy()
    r7 = exp_2117_variability_drivers()
    r8 = exp_2118_actionable_patterns()

    print("\n" + "=" * 60)
    print(f"Results: 8/8 experiments completed")
    print(f"Figures saved to {FIG_DIR}/var-fig01–08")
    print("=" * 60)
