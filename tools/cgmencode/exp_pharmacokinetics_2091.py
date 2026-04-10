#!/usr/bin/env python3
"""
EXP-2091–2098: Insulin Pharmacokinetics & Meal Absorption Dynamics

Supply-side modeling is the primary error source (1.5-2× demand RMSE, EXP-2087).
This batch investigates WHY supply modeling fails and how to fix it.

EXP-2091: Insulin onset/peak/duration per patient (PK curve fitting)
EXP-2092: Dose-response nonlinearity (ISF vs bolus size)
EXP-2093: Injection site and time-of-day effects on insulin action
EXP-2094: Carb absorption rate estimation (fast vs slow carbs)
EXP-2095: Pre-bolus timing effect (early vs late vs no pre-bolus)
EXP-2096: Stacking detection (multiple boluses within DIA window)
EXP-2097: Insulin-on-board accuracy (predicted vs observed decay)
EXP-2098: Combined PK model — personalized insulin action curve

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
DIA_STEPS = 6 * STEPS_PER_HOUR  # 6 hours default DIA


patients = load_patients(PATIENT_DIR)


# ── EXP-2091: Insulin PK Curve Fitting ───────────────────────────────
def exp_2091_insulin_pk():
    """Fit insulin action curve per patient from correction events."""
    print("\n═══ EXP-2091: Insulin PK Curve Fitting ═══")

    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        bolus = df['bolus'].values
        carbs = df['carbs'].values

        # Find isolated correction boluses (no carbs within ±2h, bolus > 1U, glucose > 150)
        events = []
        for i in range(len(g) - DIA_STEPS):
            if np.isnan(bolus[i]) or bolus[i] < 1.0:
                continue
            if np.isnan(g[i]) or g[i] < 150:
                continue
            # No carbs within ±2h
            window = 2 * STEPS_PER_HOUR
            cs = max(0, i - window)
            ce = min(len(carbs), i + window)
            if np.nansum(carbs[cs:ce]) > 0:
                continue
            # No other bolus within ±2h
            bs = max(0, i - window)
            be = min(len(bolus), i + window)
            other_bolus = np.nansum(bolus[bs:be]) - bolus[i]
            if other_bolus > 0.5:
                continue
            # Extract glucose response curve (6h post-bolus)
            response = g[i:i + DIA_STEPS]
            if np.sum(np.isnan(response)) > DIA_STEPS * 0.3:
                continue
            # Normalize by bolus size
            response_normalized = (response - g[i]) / bolus[i]
            events.append({
                'idx': i,
                'dose': float(bolus[i]),
                'start_glucose': float(g[i]),
                'response': response_normalized.tolist(),
                'hour': (i % STEPS_PER_DAY) / STEPS_PER_HOUR
            })

        if len(events) < 3:
            print(f"  {name}: insufficient corrections ({len(events)} events)")
            results[name] = {'n_events': len(events), 'sufficient': False}
            continue

        # Average response curve
        all_responses = np.array([e['response'] for e in events])
        # Handle NaN by nanmean
        mean_response = np.nanmean(all_responses, axis=0)
        std_response = np.nanstd(all_responses, axis=0)

        # Find onset (first significant drop), peak (minimum), and duration
        # Onset: first time response drops below -2 mg/dL/U
        onset_idx = 0
        for j in range(len(mean_response)):
            if mean_response[j] < -2:
                onset_idx = j
                break
        onset_min = onset_idx * 5  # minutes

        # Peak (maximum glucose drop per unit)
        peak_idx = np.nanargmin(mean_response)
        peak_min = peak_idx * 5
        peak_effect = float(mean_response[peak_idx])

        # Duration (90% of effect complete)
        if peak_effect < -1:
            threshold_90 = peak_effect * 0.1  # 90% recovered
            dur_idx = peak_idx
            for j in range(peak_idx, len(mean_response)):
                if mean_response[j] > threshold_90:
                    dur_idx = j
                    break
            duration_min = dur_idx * 5
        else:
            duration_min = 360  # default 6h

        # Effective ISF from peak effect
        eff_isf = abs(peak_effect) if peak_effect < 0 else 0

        results[name] = {
            'n_events': len(events),
            'sufficient': True,
            'onset_min': onset_min,
            'peak_min': peak_min,
            'peak_effect_per_unit': round(peak_effect, 1),
            'duration_min': duration_min,
            'effective_isf': round(eff_isf, 1),
            'mean_dose': round(float(np.mean([e['dose'] for e in events])), 1),
            'mean_response': [round(float(v), 1) if not np.isnan(v) else None
                             for v in mean_response],
            'std_response': [round(float(v), 1) if not np.isnan(v) else None
                            for v in std_response]
        }

        print(f"  {name}: onset={onset_min}min peak={peak_min}min({peak_effect:.0f}mg/dL/U) "
              f"dur={duration_min}min ({len(events)} events)")

    if MAKE_FIGS:
        fig, axes = plt.subplots(3, 4, figsize=(20, 15))
        axes = axes.flatten()
        time_axis = np.arange(DIA_STEPS) * 5 / 60  # hours

        plot_idx = 0
        for name, r in sorted(results.items()):
            if not r.get('sufficient', False) or plot_idx >= 11:
                continue
            ax = axes[plot_idx]
            mean_r = np.array([v if v is not None else np.nan for v in r['mean_response']])
            std_r = np.array([v if v is not None else np.nan for v in r['std_response']])

            ax.plot(time_axis, mean_r, 'b-', linewidth=2)
            ax.fill_between(time_axis, mean_r - std_r, mean_r + std_r,
                           alpha=0.2, color='blue')
            ax.axhline(0, color='gray', linestyle='--', linewidth=0.5)
            ax.axvline(r['onset_min'] / 60, color='green', linestyle=':', label='Onset')
            ax.axvline(r['peak_min'] / 60, color='red', linestyle=':', label='Peak')
            ax.set_title(f"Patient {name} (n={r['n_events']})",
                        fontweight='bold', fontsize=11)
            ax.set_xlabel('Hours post-bolus')
            ax.set_ylabel('ΔGlucose per unit (mg/dL/U)')
            ax.legend(fontsize=7)
            ax.grid(True, alpha=0.3)
            plot_idx += 1

        for idx in range(plot_idx, len(axes)):
            axes[idx].set_visible(False)

        fig.suptitle('EXP-2091: Insulin Action Curves (Correction Boluses)',
                     fontsize=14, fontweight='bold')
        fig.tight_layout(rect=[0, 0, 1, 0.95])
        fig.savefig(f'{FIG_DIR}/pk-fig01-insulin-curves.png', dpi=150,
                    bbox_inches='tight')
        plt.close()
        print(f"  → Saved pk-fig01-insulin-curves.png")

    output = {'experiment': 'EXP-2091', 'title': 'Insulin PK Curve Fitting',
              'per_patient': results}
    with open(f'{EXP_DIR}/exp-2091_insulin_pk.json', 'w') as f:
        json.dump(output, f, indent=2, cls=NumpyEncoder)
    return output


# ── EXP-2092: Dose-Response Nonlinearity ──────────────────────────────
def exp_2092_dose_response():
    """Does ISF change with bolus size? (Dose-dependent kinetics)"""
    print("\n═══ EXP-2092: Dose-Response Nonlinearity ═══")

    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        bolus = df['bolus'].values
        carbs = df['carbs'].values

        # Collect correction events with dose and glucose drop
        events = []
        for i in range(len(g) - 3 * STEPS_PER_HOUR):
            if np.isnan(bolus[i]) or bolus[i] < 0.3:
                continue
            if np.isnan(g[i]) or g[i] < 130:
                continue
            # No carbs ±2h
            w = 2 * STEPS_PER_HOUR
            if np.nansum(carbs[max(0, i-w):min(len(carbs), i+w)]) > 0:
                continue
            # Glucose drop over 3h
            future = g[i:i + 3 * STEPS_PER_HOUR]
            valid_future = future[~np.isnan(future)]
            if len(valid_future) < STEPS_PER_HOUR:
                continue
            drop = g[i] - np.min(valid_future)
            if drop < 5:
                continue
            isf = drop / bolus[i]
            events.append({
                'dose': float(bolus[i]),
                'drop': float(drop),
                'isf': float(isf),
                'start_glucose': float(g[i])
            })

        if len(events) < 10:
            results[name] = {'n_events': len(events), 'sufficient': False}
            print(f"  {name}: insufficient ({len(events)} events)")
            continue

        doses = np.array([e['dose'] for e in events])
        isfs = np.array([e['isf'] for e in events])

        # Bin by dose size
        small = doses < np.percentile(doses, 33)
        medium = (doses >= np.percentile(doses, 33)) & (doses < np.percentile(doses, 67))
        large = doses >= np.percentile(doses, 67)

        small_isf = float(np.median(isfs[small])) if np.sum(small) > 3 else np.nan
        medium_isf = float(np.median(isfs[medium])) if np.sum(medium) > 3 else np.nan
        large_isf = float(np.median(isfs[large])) if np.sum(large) > 3 else np.nan

        # Correlation between dose and ISF
        corr = float(np.corrcoef(doses, isfs)[0, 1])

        # Nonlinearity: if ISF decreases with dose → dose-dependent (sublinear)
        if not np.isnan(small_isf) and not np.isnan(large_isf) and small_isf > 0:
            nonlinearity = large_isf / small_isf
        else:
            nonlinearity = 1.0

        results[name] = {
            'n_events': len(events),
            'sufficient': True,
            'median_dose': round(float(np.median(doses)), 1),
            'dose_range': [round(float(np.min(doses)), 1),
                          round(float(np.max(doses)), 1)],
            'small_isf': round(small_isf, 1) if not np.isnan(small_isf) else None,
            'medium_isf': round(medium_isf, 1) if not np.isnan(medium_isf) else None,
            'large_isf': round(large_isf, 1) if not np.isnan(large_isf) else None,
            'dose_isf_corr': round(corr, 3),
            'nonlinearity_ratio': round(nonlinearity, 2),
            'is_nonlinear': abs(nonlinearity - 1) > 0.2
        }

        linear = "LINEAR" if abs(nonlinearity - 1) <= 0.2 else \
                 "SUBLINEAR" if nonlinearity < 0.8 else "SUPERLINEAR"
        print(f"  {name}: {linear} (small={small_isf:.0f} large={large_isf:.0f} "
              f"ratio={nonlinearity:.2f} r={corr:.2f}, n={len(events)})")

    if MAKE_FIGS:
        fig, axes = plt.subplots(3, 4, figsize=(20, 15))
        axes = axes.flatten()

        plot_idx = 0
        for name, r in sorted(results.items()):
            if not r.get('sufficient', False) or plot_idx >= 11:
                continue
            ax = axes[plot_idx]

            # Scatter dose vs ISF
            events_p = [e for e in [p for p in patients if p['name'] == name]]
            # Re-extract for plotting
            df = [pt for pt in patients if pt['name'] == name][0]['df']
            g_p = df['glucose'].values
            bolus_p = df['bolus'].values
            carbs_p = df['carbs'].values

            plot_doses = []
            plot_isfs = []
            for i in range(len(g_p) - 3 * STEPS_PER_HOUR):
                if np.isnan(bolus_p[i]) or bolus_p[i] < 0.3:
                    continue
                if np.isnan(g_p[i]) or g_p[i] < 130:
                    continue
                w = 2 * STEPS_PER_HOUR
                if np.nansum(carbs_p[max(0, i-w):min(len(carbs_p), i+w)]) > 0:
                    continue
                future = g_p[i:i + 3 * STEPS_PER_HOUR]
                valid_f = future[~np.isnan(future)]
                if len(valid_f) < STEPS_PER_HOUR:
                    continue
                drop = g_p[i] - np.min(valid_f)
                if drop < 5:
                    continue
                plot_doses.append(bolus_p[i])
                plot_isfs.append(drop / bolus_p[i])

            ax.scatter(plot_doses, plot_isfs, alpha=0.3, s=20, c='C0')

            # Trend line
            if len(plot_doses) > 5:
                z = np.polyfit(plot_doses, plot_isfs, 1)
                x_line = np.linspace(min(plot_doses), max(plot_doses), 50)
                ax.plot(x_line, np.polyval(z, x_line), 'r-', linewidth=2)

            ax.set_title(f"{name} (r={r['dose_isf_corr']:.2f}, n={r['n_events']})",
                        fontweight='bold', fontsize=10)
            ax.set_xlabel('Dose (U)')
            ax.set_ylabel('ISF (mg/dL/U)')
            ax.grid(True, alpha=0.3)
            plot_idx += 1

        for idx in range(plot_idx, len(axes)):
            axes[idx].set_visible(False)

        fig.suptitle('EXP-2092: Dose-Response Relationship',
                     fontsize=14, fontweight='bold')
        fig.tight_layout(rect=[0, 0, 1, 0.95])
        fig.savefig(f'{FIG_DIR}/pk-fig02-dose-response.png', dpi=150,
                    bbox_inches='tight')
        plt.close()
        print(f"  → Saved pk-fig02-dose-response.png")

    output = {'experiment': 'EXP-2092', 'title': 'Dose-Response Nonlinearity',
              'per_patient': results}
    with open(f'{EXP_DIR}/exp-2092_dose_response.json', 'w') as f:
        json.dump(output, f, indent=2, cls=NumpyEncoder)
    return output


# ── EXP-2093: Time-of-Day Insulin Action ─────────────────────────────
def exp_2093_time_of_day():
    """How does insulin action speed vary by time of day?"""
    print("\n═══ EXP-2093: Time-of-Day Insulin Action ═══")

    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        bolus = df['bolus'].values
        carbs = df['carbs'].values

        # Collect correction events by time of day
        hourly_isf = {h: [] for h in range(24)}
        hourly_onset = {h: [] for h in range(24)}

        for i in range(len(g) - 3 * STEPS_PER_HOUR):
            if np.isnan(bolus[i]) or bolus[i] < 0.5:
                continue
            if np.isnan(g[i]) or g[i] < 140:
                continue
            w = 2 * STEPS_PER_HOUR
            if np.nansum(carbs[max(0, i-w):min(len(carbs), i+w)]) > 0:
                continue

            hour = int((i % STEPS_PER_DAY) / STEPS_PER_HOUR)
            future = g[i:i + 3 * STEPS_PER_HOUR]
            valid_f = future[~np.isnan(future)]
            if len(valid_f) < 6:
                continue

            drop = g[i] - np.min(valid_f)
            if drop < 5:
                continue

            isf = drop / bolus[i]
            hourly_isf[hour].append(isf)

            # Onset: time to first 10% of total drop
            threshold = g[i] - drop * 0.1
            onset = 0
            for j in range(len(future)):
                if not np.isnan(future[j]) and future[j] < threshold:
                    onset = j * 5  # minutes
                    break
            if onset > 0:
                hourly_onset[hour].append(onset)

        # Summarize
        hourly_summary = {}
        for h in range(24):
            if len(hourly_isf[h]) >= 3:
                hourly_summary[h] = {
                    'median_isf': round(float(np.median(hourly_isf[h])), 1),
                    'onset_min': round(float(np.median(hourly_onset[h])), 0) if hourly_onset[h] else None,
                    'n': len(hourly_isf[h])
                }

        if len(hourly_summary) < 4:
            results[name] = {'sufficient': False, 'n_hours': len(hourly_summary)}
            print(f"  {name}: insufficient ({len(hourly_summary)} hours with data)")
            continue

        # Morning vs evening comparison
        morning_isf = []
        evening_isf = []
        for h, s in hourly_summary.items():
            if 6 <= h < 12:
                morning_isf.extend(hourly_isf[h])
            elif 18 <= h < 24:
                evening_isf.extend(hourly_isf[h])

        am_isf = float(np.median(morning_isf)) if morning_isf else np.nan
        pm_isf = float(np.median(evening_isf)) if evening_isf else np.nan
        ratio = pm_isf / am_isf if am_isf > 0 and not np.isnan(pm_isf) else np.nan

        results[name] = {
            'sufficient': True,
            'n_hours': len(hourly_summary),
            'hourly': hourly_summary,
            'morning_isf': round(am_isf, 1) if not np.isnan(am_isf) else None,
            'evening_isf': round(pm_isf, 1) if not np.isnan(pm_isf) else None,
            'pm_am_ratio': round(ratio, 2) if not np.isnan(ratio) else None
        }

        ratio_str = f"{ratio:.2f}×" if not np.isnan(ratio) else "N/A"
        print(f"  {name}: AM ISF={am_isf:.0f} PM ISF={pm_isf:.0f} ratio={ratio_str} "
              f"({len(hourly_summary)} hours)")

    if MAKE_FIGS:
        fig, ax = plt.subplots(figsize=(14, 7))

        for name, r in sorted(results.items()):
            if not r.get('sufficient', False):
                continue
            hours = sorted(r['hourly'].keys())
            isfs = [r['hourly'][h]['median_isf'] for h in hours]
            ax.plot(hours, isfs, 'o-', label=name, linewidth=1.5, markersize=6)

        ax.set_xlabel('Hour of Day', fontsize=12)
        ax.set_ylabel('Effective ISF (mg/dL per Unit)', fontsize=12)
        ax.set_title('EXP-2093: Insulin Sensitivity by Time of Day',
                     fontsize=14, fontweight='bold')
        ax.legend(loc='center left', bbox_to_anchor=(1.02, 0.5), fontsize=9)
        ax.set_xticks(range(0, 24, 2))
        ax.grid(True, alpha=0.3)
        ax.axvspan(6, 12, alpha=0.05, color='yellow', label='Morning')
        ax.axvspan(18, 24, alpha=0.05, color='blue', label='Evening')

        fig.tight_layout()
        fig.savefig(f'{FIG_DIR}/pk-fig03-time-of-day.png', dpi=150,
                    bbox_inches='tight')
        plt.close()
        print(f"  → Saved pk-fig03-time-of-day.png")

    output = {'experiment': 'EXP-2093', 'title': 'Time-of-Day Insulin Action',
              'per_patient': results}
    with open(f'{EXP_DIR}/exp-2093_tod_insulin.json', 'w') as f:
        json.dump(output, f, indent=2, cls=NumpyEncoder)
    return output


# ── EXP-2094: Carb Absorption Rate ───────────────────────────────────
def exp_2094_carb_absorption():
    """Estimate carb absorption rate from meal glucose excursions."""
    print("\n═══ EXP-2094: Carb Absorption Rate ═══")

    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        carbs_col = df['carbs'].values
        bolus = df['bolus'].values
        iob = df['iob'].values

        meal_events = []

        for i in range(len(g) - 3 * STEPS_PER_HOUR):
            if np.isnan(carbs_col[i]) or carbs_col[i] < 10:
                continue
            if np.isnan(g[i]):
                continue

            # Get post-meal glucose response
            response = g[i:i + 3 * STEPS_PER_HOUR]
            valid_r = response[~np.isnan(response)]
            if len(valid_r) < STEPS_PER_HOUR:
                continue

            # Time to peak
            peak_idx = np.nanargmax(response)
            peak_value = float(response[peak_idx])
            spike = peak_value - g[i]
            time_to_peak = peak_idx * 5  # minutes

            if spike < 10:
                continue

            # Rise rate (first 30 min)
            first_30 = response[:6]
            first_30_valid = first_30[~np.isnan(first_30)]
            if len(first_30_valid) > 1:
                rise_rate = (first_30_valid[-1] - first_30_valid[0]) / (len(first_30_valid) * 5)
            else:
                rise_rate = 0

            # Estimate absorption rate: spike / carbs gives mg/dL per gram
            # Then convert using ISF and body weight estimate
            absorption_rate = spike / carbs_col[i] if carbs_col[i] > 0 else 0

            meal_events.append({
                'carbs': float(carbs_col[i]),
                'spike': round(spike, 1),
                'time_to_peak_min': time_to_peak,
                'rise_rate': round(rise_rate, 2),
                'absorption_rate': round(absorption_rate, 2),
                'hour': (i % STEPS_PER_DAY) / STEPS_PER_HOUR
            })

        if len(meal_events) < 5:
            results[name] = {'n_meals': len(meal_events), 'sufficient': False}
            print(f"  {name}: insufficient ({len(meal_events)} meals)")
            continue

        peaks = [e['time_to_peak_min'] for e in meal_events]
        rates = [e['rise_rate'] for e in meal_events]
        spikes = [e['spike'] for e in meal_events]

        # Fast vs slow carb classification
        fast_meals = [e for e in meal_events if e['time_to_peak_min'] <= 45]
        slow_meals = [e for e in meal_events if e['time_to_peak_min'] > 60]

        results[name] = {
            'n_meals': len(meal_events),
            'sufficient': True,
            'median_time_to_peak': round(float(np.median(peaks)), 0),
            'median_rise_rate': round(float(np.median(rates)), 2),
            'median_spike': round(float(np.median(spikes)), 1),
            'p25_peak': round(float(np.percentile(peaks, 25)), 0),
            'p75_peak': round(float(np.percentile(peaks, 75)), 0),
            'n_fast_meals': len(fast_meals),
            'n_slow_meals': len(slow_meals),
            'fast_fraction': round(len(fast_meals) / len(meal_events), 2),
            'fast_spike': round(float(np.median([e['spike'] for e in fast_meals])), 1) if fast_meals else None,
            'slow_spike': round(float(np.median([e['spike'] for e in slow_meals])), 1) if slow_meals else None
        }

        print(f"  {name}: peak={np.median(peaks):.0f}min spike={np.median(spikes):.0f}mg/dL "
              f"fast={len(fast_meals)}/{len(meal_events)} ({len(meal_events)} meals)")

    if MAKE_FIGS:
        fig, axes = plt.subplots(1, 3, figsize=(18, 6))

        names = sorted([n for n in results if results[n].get('sufficient', False)])

        # Time to peak distribution
        ax = axes[0]
        peaks_all = []
        labels_all = []
        for n in names:
            peaks_all.append(results[n]['median_time_to_peak'])
            labels_all.append(n)
        ax.bar(range(len(names)), peaks_all, color='C0', edgecolor='black')
        ax.set_xticks(range(len(names)))
        ax.set_xticklabels(names, fontweight='bold')
        ax.set_ylabel('Median Time to Peak (min)')
        ax.set_title('Carb Absorption Speed', fontweight='bold')
        ax.axhline(45, color='green', linestyle='--', label='Fast threshold')
        ax.axhline(60, color='red', linestyle='--', label='Slow threshold')
        ax.legend()

        # Fast vs slow fraction
        ax = axes[1]
        fast = [results[n]['fast_fraction'] for n in names]
        slow = [1 - f for f in fast]
        ax.bar(range(len(names)), fast, label='Fast (<45min)', color='C2',
               edgecolor='black')
        ax.bar(range(len(names)), slow, bottom=fast, label='Slow (>60min)',
               color='C3', edgecolor='black')
        ax.set_xticks(range(len(names)))
        ax.set_xticklabels(names, fontweight='bold')
        ax.set_ylabel('Fraction')
        ax.set_title('Fast vs Slow Meals', fontweight='bold')
        ax.legend()

        # Rise rate
        ax = axes[2]
        rates_all = [results[n]['median_rise_rate'] for n in names]
        ax.bar(range(len(names)), rates_all, color='C1', edgecolor='black')
        ax.set_xticks(range(len(names)))
        ax.set_xticklabels(names, fontweight='bold')
        ax.set_ylabel('Rise Rate (mg/dL/min)')
        ax.set_title('Post-Meal Glucose Rise Rate', fontweight='bold')

        fig.suptitle('EXP-2094: Carb Absorption Dynamics',
                     fontsize=14, fontweight='bold')
        fig.tight_layout(rect=[0, 0, 1, 0.95])
        fig.savefig(f'{FIG_DIR}/pk-fig04-carb-absorption.png', dpi=150,
                    bbox_inches='tight')
        plt.close()
        print(f"  → Saved pk-fig04-carb-absorption.png")

    output = {'experiment': 'EXP-2094', 'title': 'Carb Absorption Rate',
              'per_patient': results}
    with open(f'{EXP_DIR}/exp-2094_carb_absorption.json', 'w') as f:
        json.dump(output, f, indent=2, cls=NumpyEncoder)
    return output


# ── EXP-2095: Pre-Bolus Timing Effect ────────────────────────────────
def exp_2095_prebolus():
    """How does timing between bolus and meal affect glucose excursion?"""
    print("\n═══ EXP-2095: Pre-Bolus Timing Effect ═══")

    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        bolus = df['bolus'].values
        carbs_col = df['carbs'].values

        timing_events = []

        for i in range(len(g) - 3 * STEPS_PER_HOUR):
            if np.isnan(carbs_col[i]) or carbs_col[i] < 10:
                continue
            if np.isnan(g[i]):
                continue

            # Find nearest bolus within ±30 min
            search_window = 6  # 30 min = 6 steps
            best_bolus_idx = None
            best_bolus_val = 0

            for j in range(max(0, i - search_window), min(len(bolus), i + search_window + 1)):
                if not np.isnan(bolus[j]) and bolus[j] > 0.5:
                    if bolus[j] > best_bolus_val:
                        best_bolus_val = bolus[j]
                        best_bolus_idx = j

            if best_bolus_idx is None:
                # No bolus found — count as "no pre-bolus"
                timing_min = None
            else:
                timing_min = (i - best_bolus_idx) * 5  # positive = pre-bolus

            # Post-meal spike
            response = g[i:i + 2 * STEPS_PER_HOUR]
            valid_r = response[~np.isnan(response)]
            if len(valid_r) < 6:
                continue

            spike = float(np.max(valid_r)) - g[i]
            if spike < 0:
                spike = 0

            timing_events.append({
                'timing_min': timing_min,
                'spike': spike,
                'carbs': float(carbs_col[i]),
                'bolus': best_bolus_val
            })

        if len(timing_events) < 10:
            results[name] = {'n_events': len(timing_events), 'sufficient': False}
            print(f"  {name}: insufficient ({len(timing_events)} events)")
            continue

        # Group by timing
        pre_bolus = [e for e in timing_events if e['timing_min'] is not None and e['timing_min'] > 5]
        concurrent = [e for e in timing_events if e['timing_min'] is not None and -5 <= e['timing_min'] <= 5]
        late_bolus = [e for e in timing_events if e['timing_min'] is not None and e['timing_min'] < -5]
        no_bolus = [e for e in timing_events if e['timing_min'] is None]

        pre_spike = float(np.median([e['spike'] for e in pre_bolus])) if pre_bolus else np.nan
        conc_spike = float(np.median([e['spike'] for e in concurrent])) if concurrent else np.nan
        late_spike = float(np.median([e['spike'] for e in late_bolus])) if late_bolus else np.nan
        no_spike = float(np.median([e['spike'] for e in no_bolus])) if no_bolus else np.nan

        results[name] = {
            'n_events': len(timing_events),
            'sufficient': True,
            'n_pre_bolus': len(pre_bolus),
            'n_concurrent': len(concurrent),
            'n_late_bolus': len(late_bolus),
            'n_no_bolus': len(no_bolus),
            'pre_bolus_spike': round(pre_spike, 1) if not np.isnan(pre_spike) else None,
            'concurrent_spike': round(conc_spike, 1) if not np.isnan(conc_spike) else None,
            'late_bolus_spike': round(late_spike, 1) if not np.isnan(late_spike) else None,
            'no_bolus_spike': round(no_spike, 1) if not np.isnan(no_spike) else None
        }

        print(f"  {name}: pre={pre_spike:.0f} conc={conc_spike:.0f} "
              f"late={late_spike:.0f} no={no_spike:.0f}mg/dL "
              f"(pre={len(pre_bolus)} conc={len(concurrent)} late={len(late_bolus)} "
              f"no={len(no_bolus)})")

    if MAKE_FIGS:
        fig, ax = plt.subplots(figsize=(14, 7))

        names = sorted([n for n in results if results[n].get('sufficient', False)])
        x = np.arange(len(names))
        width = 0.2

        pre_vals = [results[n].get('pre_bolus_spike') or 0 for n in names]
        conc_vals = [results[n].get('concurrent_spike') or 0 for n in names]
        late_vals = [results[n].get('late_bolus_spike') or 0 for n in names]
        no_vals = [results[n].get('no_bolus_spike') or 0 for n in names]

        ax.bar(x - 1.5*width, pre_vals, width, label='Pre-bolus (>5min)', color='C2',
               edgecolor='black')
        ax.bar(x - 0.5*width, conc_vals, width, label='Concurrent (±5min)', color='C0',
               edgecolor='black')
        ax.bar(x + 0.5*width, late_vals, width, label='Late bolus (<-5min)', color='C1',
               edgecolor='black')
        ax.bar(x + 1.5*width, no_vals, width, label='No bolus', color='C3',
               edgecolor='black')

        ax.set_xticks(x)
        ax.set_xticklabels(names, fontweight='bold')
        ax.set_ylabel('Median Post-Meal Spike (mg/dL)')
        ax.set_title('EXP-2095: Pre-Bolus Timing Effect on Meal Spikes',
                     fontsize=14, fontweight='bold')
        ax.legend()
        ax.grid(axis='y', alpha=0.3)

        fig.tight_layout()
        fig.savefig(f'{FIG_DIR}/pk-fig05-prebolus.png', dpi=150,
                    bbox_inches='tight')
        plt.close()
        print(f"  → Saved pk-fig05-prebolus.png")

    output = {'experiment': 'EXP-2095', 'title': 'Pre-Bolus Timing Effect',
              'per_patient': results}
    with open(f'{EXP_DIR}/exp-2095_prebolus.json', 'w') as f:
        json.dump(output, f, indent=2, cls=NumpyEncoder)
    return output


# ── EXP-2096: Insulin Stacking Detection ─────────────────────────────
def exp_2096_stacking():
    """Detect and quantify insulin stacking (multiple boluses within DIA)."""
    print("\n═══ EXP-2096: Insulin Stacking Detection ═══")

    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        bolus = df['bolus'].values

        n_days = np.sum(~np.isnan(g)) / STEPS_PER_DAY

        # Find bolus sequences
        bolus_times = []
        for i in range(len(bolus)):
            if not np.isnan(bolus[i]) and bolus[i] > 0.3:
                bolus_times.append((i, float(bolus[i])))

        if len(bolus_times) < 5:
            results[name] = {'n_boluses': len(bolus_times), 'sufficient': False}
            print(f"  {name}: insufficient ({len(bolus_times)} boluses)")
            continue

        # Detect stacking: bolus within 2h of previous bolus
        stacking_window = 2 * STEPS_PER_HOUR
        stacking_events = []
        for j in range(1, len(bolus_times)):
            gap = bolus_times[j][0] - bolus_times[j-1][0]
            if gap <= stacking_window:
                idx = bolus_times[j][0]
                # Check glucose outcome 3h after stacked bolus
                future_g = g[idx:idx + 3 * STEPS_PER_HOUR]
                valid_f = future_g[~np.isnan(future_g)]
                hypo = bool(np.any(valid_f < 70)) if len(valid_f) > 0 else False

                stacking_events.append({
                    'gap_min': gap * 5,
                    'dose_1': bolus_times[j-1][1],
                    'dose_2': bolus_times[j][1],
                    'total_stacked': bolus_times[j-1][1] + bolus_times[j][1],
                    'caused_hypo': hypo,
                    'glucose_at_stack': float(g[idx]) if not np.isnan(g[idx]) else None
                })

        n_stacking = len(stacking_events)
        stacking_rate = n_stacking / n_days if n_days > 0 else 0
        hypo_from_stacking = sum(1 for e in stacking_events if e['caused_hypo'])
        hypo_rate = hypo_from_stacking / n_stacking if n_stacking > 0 else 0

        results[name] = {
            'n_boluses': len(bolus_times),
            'sufficient': True,
            'n_stacking_events': n_stacking,
            'stacking_per_day': round(stacking_rate, 1),
            'hypo_from_stacking': hypo_from_stacking,
            'stacking_hypo_rate': round(hypo_rate, 3),
            'mean_gap_min': round(float(np.mean([e['gap_min'] for e in stacking_events])), 0) if stacking_events else None,
            'mean_total_dose': round(float(np.mean([e['total_stacked'] for e in stacking_events])), 1) if stacking_events else None
        }

        print(f"  {name}: {n_stacking} stacking events ({stacking_rate:.1f}/day), "
              f"hypo rate={hypo_rate:.0%} ({hypo_from_stacking} hypos)")

    if MAKE_FIGS:
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))

        names = sorted([n for n in results if results[n].get('sufficient', False)])
        x = np.arange(len(names))

        # Stacking frequency
        ax = axes[0]
        vals = [results[n]['stacking_per_day'] for n in names]
        ax.bar(x, vals, color='C0', edgecolor='black')
        ax.set_xticks(x)
        ax.set_xticklabels(names, fontweight='bold')
        ax.set_ylabel('Stacking Events per Day')
        ax.set_title('Insulin Stacking Frequency', fontweight='bold')
        ax.grid(axis='y', alpha=0.3)

        # Stacking → hypo rate
        ax = axes[1]
        vals = [results[n]['stacking_hypo_rate'] * 100 for n in names]
        colors = ['green' if v < 15 else 'orange' if v < 30 else 'red' for v in vals]
        ax.bar(x, vals, color=colors, edgecolor='black')
        ax.set_xticks(x)
        ax.set_xticklabels(names, fontweight='bold')
        ax.set_ylabel('Hypo Rate from Stacking (%)')
        ax.set_title('Stacking → Hypoglycemia Rate', fontweight='bold')
        ax.axhline(15, color='green', linestyle='--', label='Low risk')
        ax.axhline(30, color='red', linestyle='--', label='High risk')
        ax.legend()
        ax.grid(axis='y', alpha=0.3)

        fig.suptitle('EXP-2096: Insulin Stacking Detection',
                     fontsize=14, fontweight='bold')
        fig.tight_layout(rect=[0, 0, 1, 0.95])
        fig.savefig(f'{FIG_DIR}/pk-fig06-stacking.png', dpi=150,
                    bbox_inches='tight')
        plt.close()
        print(f"  → Saved pk-fig06-stacking.png")

    output = {'experiment': 'EXP-2096', 'title': 'Insulin Stacking Detection',
              'per_patient': results}
    with open(f'{EXP_DIR}/exp-2096_stacking.json', 'w') as f:
        json.dump(output, f, indent=2, cls=NumpyEncoder)
    return output


# ── EXP-2097: IOB Accuracy ───────────────────────────────────────────
def exp_2097_iob_accuracy():
    """How accurately does predicted IOB match observed insulin effect?"""
    print("\n═══ EXP-2097: IOB Accuracy ═══")

    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        iob = df['iob'].values
        bolus = df['bolus'].values
        carbs_col = df['carbs'].values

        # After bolus, track IOB decay and glucose response
        decay_events = []

        for i in range(len(g) - DIA_STEPS):
            if np.isnan(bolus[i]) or bolus[i] < 1.0:
                continue
            if np.isnan(g[i]) or g[i] < 140:
                continue
            # No carbs ±2h
            w = 2 * STEPS_PER_HOUR
            if np.nansum(carbs_col[max(0, i-w):min(len(carbs_col), i+w)]) > 0:
                continue

            # Track IOB decay curve
            iob_curve = iob[i:i + DIA_STEPS]
            g_curve = g[i:i + DIA_STEPS]

            if np.sum(np.isnan(iob_curve)) > DIA_STEPS * 0.3:
                continue

            # Expected glucose effect: each IOB unit should be acting
            # Compare IOB decay rate to glucose drop rate
            iob_valid = iob_curve[~np.isnan(iob_curve)]
            g_valid_c = g_curve[~np.isnan(g_curve)]

            if len(iob_valid) < STEPS_PER_HOUR and len(g_valid_c) < STEPS_PER_HOUR:
                continue

            # IOB half-life (time to 50% of initial)
            iob_start = iob_valid[0] if len(iob_valid) > 0 else 0
            if iob_start < 0.5:
                continue

            half_idx = 0
            for j in range(len(iob_valid)):
                if iob_valid[j] < iob_start * 0.5:
                    half_idx = j
                    break
            iob_halflife = half_idx * 5  # minutes

            # Glucose drop correlation with IOB decay
            min_len_c = min(len(iob_curve), len(g_curve))
            iob_trim = iob_curve[:min_len_c]
            g_trim = g_curve[:min_len_c]
            valid_both = ~np.isnan(iob_trim) & ~np.isnan(g_trim)
            if np.sum(valid_both) > 10:
                corr = float(np.corrcoef(iob_trim[valid_both],
                                         g_trim[valid_both])[0, 1])
            else:
                corr = np.nan

            decay_events.append({
                'iob_start': float(iob_start),
                'iob_halflife_min': iob_halflife,
                'iob_glucose_corr': corr if not np.isnan(corr) else None,
                'bolus_dose': float(bolus[i])
            })

        if len(decay_events) < 3:
            results[name] = {'n_events': len(decay_events), 'sufficient': False}
            print(f"  {name}: insufficient ({len(decay_events)} events)")
            continue

        halflives = [e['iob_halflife_min'] for e in decay_events if e['iob_halflife_min'] > 0]
        corrs = [e['iob_glucose_corr'] for e in decay_events if e['iob_glucose_corr'] is not None]

        results[name] = {
            'n_events': len(decay_events),
            'sufficient': True,
            'median_halflife_min': round(float(np.median(halflives)), 0) if halflives else None,
            'mean_iob_glucose_corr': round(float(np.mean(corrs)), 3) if corrs else None,
            'halflife_range': [round(float(np.percentile(halflives, 25)), 0),
                              round(float(np.percentile(halflives, 75)), 0)] if len(halflives) > 3 else None
        }

        hl = float(np.median(halflives)) if halflives else 0
        cr = float(np.mean(corrs)) if corrs else 0
        print(f"  {name}: halflife={hl:.0f}min corr(IOB,glucose)={cr:.3f} "
              f"({len(decay_events)} events)")

    if MAKE_FIGS:
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))

        names = sorted([n for n in results if results[n].get('sufficient', False)])
        x = np.arange(len(names))

        # IOB half-life
        ax = axes[0]
        vals = [results[n].get('median_halflife_min') or 0 for n in names]
        ax.bar(x, vals, color='C0', edgecolor='black')
        ax.set_xticks(x)
        ax.set_xticklabels(names, fontweight='bold')
        ax.set_ylabel('IOB Half-life (min)')
        ax.set_title('IOB Decay Half-life', fontweight='bold')
        ax.axhline(75, color='gray', linestyle='--', label='Expected (rapid analog)')
        ax.legend()
        ax.grid(axis='y', alpha=0.3)

        # IOB-Glucose correlation
        ax = axes[1]
        vals = [results[n].get('mean_iob_glucose_corr') or 0 for n in names]
        colors = ['green' if abs(v) > 0.3 else 'orange' if abs(v) > 0.1 else 'red'
                  for v in vals]
        ax.bar(x, vals, color=colors, edgecolor='black')
        ax.set_xticks(x)
        ax.set_xticklabels(names, fontweight='bold')
        ax.set_ylabel('Correlation (IOB vs Glucose)')
        ax.set_title('IOB Tracking Accuracy', fontweight='bold')
        ax.grid(axis='y', alpha=0.3)

        fig.suptitle('EXP-2097: IOB Accuracy Assessment',
                     fontsize=14, fontweight='bold')
        fig.tight_layout(rect=[0, 0, 1, 0.95])
        fig.savefig(f'{FIG_DIR}/pk-fig07-iob-accuracy.png', dpi=150,
                    bbox_inches='tight')
        plt.close()
        print(f"  → Saved pk-fig07-iob-accuracy.png")

    output = {'experiment': 'EXP-2097', 'title': 'IOB Accuracy',
              'per_patient': results}
    with open(f'{EXP_DIR}/exp-2097_iob_accuracy.json', 'w') as f:
        json.dump(output, f, indent=2, cls=NumpyEncoder)
    return output


# ── EXP-2098: Combined PK Model ──────────────────────────────────────
def exp_2098_combined_pk():
    """Synthesize per-patient personalized insulin action parameters."""
    print("\n═══ EXP-2098: Combined PK Model — Personalized Parameters ═══")

    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        g_valid = g[~np.isnan(g)]
        bolus = df['bolus'].values
        iob = df['iob'].values
        carbs_col = df['carbs'].values

        if len(g_valid) < STEPS_PER_DAY:
            continue

        n_days = len(g_valid) / STEPS_PER_DAY
        tir = float(np.mean((g_valid >= 70) & (g_valid <= 180)))
        tbr = float(np.mean(g_valid < 70))

        # Correction event analysis for PK parameters
        onset_times = []
        peak_times = []
        durations = []
        effective_isfs = []

        for i in range(len(g) - DIA_STEPS):
            if np.isnan(bolus[i]) or bolus[i] < 0.5:
                continue
            if np.isnan(g[i]) or g[i] < 140:
                continue
            w = 2 * STEPS_PER_HOUR
            if np.nansum(carbs_col[max(0, i-w):min(len(carbs_col), i+w)]) > 0:
                continue

            response = g[i:i + DIA_STEPS]
            valid_r = response[~np.isnan(response)]
            if len(valid_r) < STEPS_PER_HOUR:
                continue

            drop = g[i] - np.min(valid_r)
            if drop < 10:
                continue

            # Onset
            threshold = g[i] - drop * 0.1
            for j in range(len(response)):
                if not np.isnan(response[j]) and response[j] < threshold:
                    onset_times.append(j * 5)
                    break

            # Peak
            nadir_idx = np.nanargmin(response)
            peak_times.append(nadir_idx * 5)

            # Duration (90% recovery)
            threshold_90 = g[i] - drop * 0.1
            for j in range(nadir_idx, len(response)):
                if not np.isnan(response[j]) and response[j] > threshold_90:
                    durations.append(j * 5)
                    break

            effective_isfs.append(drop / bolus[i])

        # Meal analysis
        meal_peaks = []
        for i in range(len(g) - 2 * STEPS_PER_HOUR):
            if np.isnan(carbs_col[i]) or carbs_col[i] < 10 or np.isnan(g[i]):
                continue
            response = g[i:i + 2 * STEPS_PER_HOUR]
            valid_r = response[~np.isnan(response)]
            if len(valid_r) < 6:
                continue
            spike = float(np.max(valid_r)) - g[i]
            if spike > 0:
                peak_idx = np.nanargmax(response)
                meal_peaks.append(peak_idx * 5)

        # Synthesize
        pk_params = {
            'insulin_onset_min': round(float(np.median(onset_times)), 0) if onset_times else None,
            'insulin_peak_min': round(float(np.median(peak_times)), 0) if peak_times else None,
            'insulin_duration_min': round(float(np.median(durations)), 0) if durations else None,
            'effective_isf': round(float(np.median(effective_isfs)), 1) if effective_isfs else None,
            'meal_peak_min': round(float(np.median(meal_peaks)), 0) if meal_peaks else None,
            'n_correction_events': len(effective_isfs),
            'n_meal_events': len(meal_peaks)
        }

        # Therapy quality assessment
        quality_flags = []
        if pk_params['insulin_onset_min'] and pk_params['insulin_onset_min'] > 30:
            quality_flags.append("SLOW_ONSET")
        if pk_params['insulin_duration_min'] and pk_params['insulin_duration_min'] > 300:
            quality_flags.append("LONG_TAIL")
        if pk_params['effective_isf'] and pk_params['effective_isf'] > 100:
            quality_flags.append("HIGH_SENSITIVITY")
        if tbr > 0.04:
            quality_flags.append("HYPO_PRONE")
        if tir < 0.70:
            quality_flags.append("LOW_TIR")

        results[name] = {
            'pk_params': pk_params,
            'tir': round(tir, 3),
            'tbr': round(tbr, 3),
            'quality_flags': quality_flags
        }

        onset = pk_params['insulin_onset_min'] or 0
        peak = pk_params['insulin_peak_min'] or 0
        dur = pk_params['insulin_duration_min'] or 0
        isf = pk_params['effective_isf'] or 0
        flags = ", ".join(quality_flags) if quality_flags else "OK"
        print(f"  {name}: onset={onset:.0f}min peak={peak:.0f}min "
              f"dur={dur:.0f}min ISF={isf:.0f} → {flags}")

    if MAKE_FIGS:
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))

        names = sorted(results.keys())
        x = np.arange(len(names))

        # Insulin timing parameters
        ax = axes[0, 0]
        onsets = [results[n]['pk_params'].get('insulin_onset_min') or 0 for n in names]
        peaks = [results[n]['pk_params'].get('insulin_peak_min') or 0 for n in names]
        ax.bar(x - 0.15, onsets, 0.3, label='Onset', color='C2', edgecolor='black')
        ax.bar(x + 0.15, peaks, 0.3, label='Peak', color='C0', edgecolor='black')
        ax.set_xticks(x)
        ax.set_xticklabels(names, fontweight='bold')
        ax.set_ylabel('Minutes')
        ax.set_title('Insulin Timing', fontweight='bold')
        ax.legend()
        ax.grid(axis='y', alpha=0.3)

        # Duration
        ax = axes[0, 1]
        durs = [results[n]['pk_params'].get('insulin_duration_min') or 0 for n in names]
        colors = ['green' if d < 240 else 'orange' if d < 360 else 'red' for d in durs]
        ax.bar(x, durs, color=colors, edgecolor='black')
        ax.set_xticks(x)
        ax.set_xticklabels(names, fontweight='bold')
        ax.set_ylabel('Duration (min)')
        ax.set_title('Insulin Duration of Action', fontweight='bold')
        ax.axhline(300, color='gray', linestyle='--', label='Standard DIA (5h)')
        ax.legend()

        # Effective ISF
        ax = axes[1, 0]
        isfs = [results[n]['pk_params'].get('effective_isf') or 0 for n in names]
        ax.bar(x, isfs, color='C1', edgecolor='black')
        ax.set_xticks(x)
        ax.set_xticklabels(names, fontweight='bold')
        ax.set_ylabel('Effective ISF (mg/dL/U)')
        ax.set_title('Effective Insulin Sensitivity', fontweight='bold')

        # Quality flags
        ax = axes[1, 1]
        n_flags = [len(results[n]['quality_flags']) for n in names]
        colors = ['green' if f <= 1 else 'orange' if f <= 2 else 'red' for f in n_flags]
        ax.barh(x, n_flags, color=colors, edgecolor='black')
        ax.set_yticks(x)
        ax.set_yticklabels(names, fontweight='bold')
        ax.set_xlabel('Number of Quality Flags')
        ax.set_title('PK Quality Assessment', fontweight='bold')

        # Add flag labels
        for i, n in enumerate(names):
            flags = results[n]['quality_flags']
            if flags:
                ax.text(n_flags[i] + 0.1, i, ", ".join(flags), va='center',
                       fontsize=7)

        fig.suptitle('EXP-2098: Personalized PK Parameters',
                     fontsize=14, fontweight='bold')
        fig.tight_layout(rect=[0, 0, 1, 0.95])
        fig.savefig(f'{FIG_DIR}/pk-fig08-combined-pk.png', dpi=150,
                    bbox_inches='tight')
        plt.close()
        print(f"  → Saved pk-fig08-combined-pk.png")

    output = {'experiment': 'EXP-2098', 'title': 'Combined PK Model',
              'per_patient': results}
    with open(f'{EXP_DIR}/exp-2098_combined_pk.json', 'w') as f:
        json.dump(output, f, indent=2, cls=NumpyEncoder)
    return output


# ── Main ──────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print("=" * 60)
    print("EXP-2091–2098: Insulin Pharmacokinetics & Meal Absorption")
    print("=" * 60)

    r1 = exp_2091_insulin_pk()
    r2 = exp_2092_dose_response()
    r3 = exp_2093_time_of_day()
    r4 = exp_2094_carb_absorption()
    r5 = exp_2095_prebolus()
    r6 = exp_2096_stacking()
    r7 = exp_2097_iob_accuracy()
    r8 = exp_2098_combined_pk()

    print("\n" + "=" * 60)
    print(f"Results: 8/8 experiments completed")
    print(f"Figures saved to {FIG_DIR}/pk-fig01–08")
    print("=" * 60)
