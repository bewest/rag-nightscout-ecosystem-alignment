#!/usr/bin/env python3
"""
EXP-2051–2058: Circadian Therapy Profiling

Quantifying how insulin sensitivity, basal needs, and glucose dynamics
change throughout the 24-hour cycle. Builds on prior findings: dinner
worse than breakfast (+21 mg/dL, EXP-2037), dawn phenomenon +14 mg/dL
(EXP-2045), 76% suspension (EXP-2042), 15% overcorrection (EXP-2044).

EXP-2051: Circadian ISF profile (hourly insulin sensitivity estimation)
EXP-2052: Circadian basal needs (hourly optimal basal rate)
EXP-2053: Dawn phenomenon characterization (onset, amplitude, predictors)
EXP-2054: Post-meal ISF by time of day (breakfast vs lunch vs dinner)
EXP-2055: Glucose rate-of-change patterns (circadian rhythm in dG/dt)
EXP-2056: IOB-dependent insulin sensitivity (diminishing returns at high IOB)
EXP-2057: Counter-regulatory response quantification (post-hypo rebound dynamics)
EXP-2058: Synthesis — optimal 24h therapy profile

Depends on: exp_metabolic_441.py
"""

import json
import sys
import os
import numpy as np
import warnings
warnings.filterwarnings('ignore')

from exp_metabolic_441 import load_patients, compute_supply_demand

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


patients = load_patients(PATIENT_DIR)

# ── EXP-2051: Circadian ISF Profile ─────────────────────────────────
def exp_2051_circadian_isf():
    """Estimate hour-by-hour insulin sensitivity from correction events."""
    print("\n═══ EXP-2051: Circadian ISF Profile ═══")

    results = {}
    all_hourly_isf = {h: [] for h in range(24)}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        iob = df['iob'].values
        bolus = df['bolus'].values

        # Find correction events: bolus given when glucose > 150, no carbs within ±1h
        carbs = df['carbs'].values
        hourly_isf = {h: [] for h in range(24)}

        for i in range(STEPS_PER_HOUR, len(g) - 4 * STEPS_PER_HOUR):
            if bolus[i] < 0.5 or np.isnan(g[i]):
                continue
            if g[i] < 150:
                continue
            # No carbs within ±1h
            carb_window = carbs[max(0, i - STEPS_PER_HOUR):i + STEPS_PER_HOUR]
            if np.nansum(carb_window) > 1:
                continue

            # Look for glucose nadir in next 4h
            future_g = g[i:i + 4 * STEPS_PER_HOUR]
            valid = ~np.isnan(future_g)
            if valid.sum() < STEPS_PER_HOUR:
                continue

            delta_g = g[i] - np.nanmin(future_g)
            if delta_g < 10:
                continue

            isf_est = delta_g / bolus[i]
            if isf_est < 5 or isf_est > 300:
                continue

            hour = (i % STEPS_PER_DAY) // STEPS_PER_HOUR
            hourly_isf[hour].append(isf_est)
            all_hourly_isf[hour].append(isf_est)

        patient_hourly = {}
        for h in range(24):
            if len(hourly_isf[h]) >= 3:
                patient_hourly[h] = {
                    'median': float(np.median(hourly_isf[h])),
                    'mean': float(np.mean(hourly_isf[h])),
                    'n': len(hourly_isf[h]),
                    'iqr': float(np.percentile(hourly_isf[h], 75) - np.percentile(hourly_isf[h], 25))
                }

        total_events = sum(len(v) for v in hourly_isf.values())
        hours_with_data = len(patient_hourly)

        # Circadian ratio: max ISF hour / min ISF hour
        if hours_with_data >= 6:
            medians = [v['median'] for v in patient_hourly.values()]
            circ_ratio = max(medians) / min(medians) if min(medians) > 0 else float('nan')
        else:
            circ_ratio = float('nan')

        results[name] = {
            'total_corrections': total_events,
            'hours_with_data': hours_with_data,
            'circadian_ratio': round(circ_ratio, 2) if not np.isnan(circ_ratio) else None,
            'hourly': patient_hourly
        }
        print(f"  {name}: {total_events} corrections, {hours_with_data} hours with data, "
              f"circadian ratio={circ_ratio:.2f}" if not np.isnan(circ_ratio) else
              f"  {name}: {total_events} corrections, {hours_with_data} hours with data")

    # Population circadian profile
    pop_hourly = {}
    for h in range(24):
        if len(all_hourly_isf[h]) >= 5:
            pop_hourly[h] = {
                'median': float(np.median(all_hourly_isf[h])),
                'mean': float(np.mean(all_hourly_isf[h])),
                'n': len(all_hourly_isf[h]),
                'iqr': float(np.percentile(all_hourly_isf[h], 75) -
                             np.percentile(all_hourly_isf[h], 25))
            }

    print(f"\n  Population: {sum(len(v) for v in all_hourly_isf.values())} total corrections")
    for h in sorted(pop_hourly.keys()):
        v = pop_hourly[h]
        print(f"    {h:02d}:00  ISF={v['median']:.0f} (n={v['n']}, IQR={v['iqr']:.0f})")

    if MAKE_FIGS:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        # Left: population circadian ISF
        hours = sorted(pop_hourly.keys())
        medians = [pop_hourly[h]['median'] for h in hours]
        iqrs = [pop_hourly[h]['iqr'] for h in hours]
        ns = [pop_hourly[h]['n'] for h in hours]

        ax = axes[0]
        ax.fill_between(hours,
                        [m - q/2 for m, q in zip(medians, iqrs)],
                        [m + q/2 for m, q in zip(medians, iqrs)],
                        alpha=0.3, color='steelblue')
        ax.plot(hours, medians, 'o-', color='steelblue', linewidth=2)
        ax.set_xlabel('Hour of Day')
        ax.set_ylabel('ISF (mg/dL per unit)')
        ax.set_title('Population Circadian ISF Profile')
        ax.set_xticks(range(0, 24, 3))
        ax.axvspan(0, 6, alpha=0.05, color='navy', label='Night')
        ax.axvspan(6, 9, alpha=0.05, color='orange', label='Dawn')
        ax.legend(loc='upper right')
        ax.grid(True, alpha=0.3)

        # Right: per-patient circadian ratios
        ax = axes[1]
        names_with_ratio = [(r, n) for n, r in results.items()
                            if r.get('circadian_ratio') is not None]
        if names_with_ratio:
            names_with_ratio.sort(key=lambda x: x[0]['circadian_ratio'], reverse=True)
            pnames = [n for _, n in names_with_ratio]
            ratios = [r['circadian_ratio'] for r, _ in names_with_ratio]
            colors = ['#d62728' if r > 2 else '#ff7f0e' if r > 1.5 else '#2ca02c' for r in ratios]
            ax.barh(pnames, ratios, color=colors)
            ax.axvline(x=1, color='black', linestyle='--', alpha=0.5)
            ax.set_xlabel('Circadian ISF Ratio (max/min hour)')
            ax.set_title('ISF Variation Across Day')
            ax.grid(True, alpha=0.3, axis='x')

        plt.tight_layout()
        fig.savefig(f'{FIG_DIR}/circ-fig01-isf-profile.png', dpi=150, bbox_inches='tight')
        plt.close()
        print(f"  → Saved circ-fig01-isf-profile.png")

    output = {'experiment': 'EXP-2051', 'title': 'Circadian ISF Profile',
              'per_patient': results, 'population_hourly': pop_hourly}
    with open(f'{EXP_DIR}/exp-2051_circadian_isf.json', 'w') as f:
        json.dump(output, f, indent=2)
    return output


# ── EXP-2052: Circadian Basal Needs ─────────────────────────────────
def exp_2052_circadian_basal():
    """Estimate hour-by-hour basal needs from glucose drift during fasting."""
    print("\n═══ EXP-2052: Circadian Basal Needs ═══")

    results = {}
    all_hourly_drift = {h: [] for h in range(24)}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        carbs = df['carbs'].values
        bolus = df['bolus'].values
        net_basal = df['net_basal'].values if 'net_basal' in df.columns else np.zeros(len(g))

        hourly_drift = {h: [] for h in range(24)}

        # Find fasting windows: no carbs or bolus within ±2h, glucose 80-180
        for i in range(2 * STEPS_PER_HOUR, len(g) - 2 * STEPS_PER_HOUR):
            if np.isnan(g[i]) or g[i] < 80 or g[i] > 180:
                continue

            # No carbs or bolus within ±2h
            window = slice(max(0, i - 2 * STEPS_PER_HOUR), i + 2 * STEPS_PER_HOUR)
            if np.nansum(carbs[window]) > 0 or np.nansum(bolus[window]) > 0.5:
                continue

            # Compute 1h glucose drift
            if i + STEPS_PER_HOUR < len(g) and not np.isnan(g[i + STEPS_PER_HOUR]):
                drift = g[i + STEPS_PER_HOUR] - g[i]  # mg/dL per hour
                if abs(drift) < 100:  # sanity
                    hour = (i % STEPS_PER_DAY) // STEPS_PER_HOUR
                    hourly_drift[hour].append(drift)
                    all_hourly_drift[hour].append(drift)

        patient_hourly = {}
        for h in range(24):
            if len(hourly_drift[h]) >= 5:
                vals = hourly_drift[h]
                patient_hourly[h] = {
                    'median_drift': float(np.median(vals)),
                    'mean_drift': float(np.mean(vals)),
                    'n': len(vals),
                    'std': float(np.std(vals))
                }

        # Basal adequacy: positive drift = under-basaled, negative = over-basaled
        adequate_hours = sum(1 for v in patient_hourly.values() if abs(v['median_drift']) < 5)
        total_hours = len(patient_hourly)

        results[name] = {
            'total_fasting_windows': sum(len(v) for v in hourly_drift.values()),
            'hours_with_data': total_hours,
            'adequate_hours': adequate_hours,
            'hourly': patient_hourly
        }
        print(f"  {name}: {results[name]['total_fasting_windows']} windows, "
              f"{adequate_hours}/{total_hours} hours adequate")

    # Population hourly drift
    pop_hourly = {}
    for h in range(24):
        if len(all_hourly_drift[h]) >= 10:
            vals = all_hourly_drift[h]
            pop_hourly[h] = {
                'median_drift': float(np.median(vals)),
                'mean_drift': float(np.mean(vals)),
                'n': len(vals)
            }

    print("\n  Population hourly drift (mg/dL/hr during fasting):")
    for h in sorted(pop_hourly.keys()):
        v = pop_hourly[h]
        direction = "↑" if v['median_drift'] > 2 else "↓" if v['median_drift'] < -2 else "→"
        print(f"    {h:02d}:00  {direction} {v['median_drift']:+.1f} mg/dL/hr (n={v['n']})")

    if MAKE_FIGS:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        # Left: population drift by hour
        hours = sorted(pop_hourly.keys())
        drifts = [pop_hourly[h]['median_drift'] for h in hours]
        colors = ['#d62728' if d > 5 else '#2ca02c' if d < -5 else '#7f7f7f' for d in drifts]

        ax = axes[0]
        ax.bar(hours, drifts, color=colors, alpha=0.7)
        ax.axhline(y=0, color='black', linewidth=1)
        ax.axhline(y=5, color='red', linestyle='--', alpha=0.5, label='Under-basaled')
        ax.axhline(y=-5, color='green', linestyle='--', alpha=0.5, label='Over-basaled')
        ax.set_xlabel('Hour of Day')
        ax.set_ylabel('Glucose Drift (mg/dL/hr)')
        ax.set_title('Fasting Glucose Drift by Hour (Population)')
        ax.set_xticks(range(0, 24, 3))
        ax.legend()
        ax.grid(True, alpha=0.3)

        # Right: per-patient drift heatmap
        ax = axes[1]
        patient_names = [p['name'] for p in patients]
        drift_matrix = np.full((len(patient_names), 24), np.nan)
        for pi, pn in enumerate(patient_names):
            if pn in results:
                for h, v in results[pn].get('hourly', {}).items():
                    drift_matrix[pi, int(h)] = v['median_drift']

        im = ax.imshow(drift_matrix, aspect='auto', cmap='RdYlGn_r',
                       vmin=-15, vmax=15, interpolation='nearest')
        ax.set_xticks(range(0, 24, 3))
        ax.set_xticklabels([f'{h:02d}' for h in range(0, 24, 3)])
        ax.set_yticks(range(len(patient_names)))
        ax.set_yticklabels(patient_names)
        ax.set_xlabel('Hour of Day')
        ax.set_title('Per-Patient Fasting Drift (mg/dL/hr)')
        plt.colorbar(im, ax=ax, label='Drift mg/dL/hr', shrink=0.8)

        plt.tight_layout()
        fig.savefig(f'{FIG_DIR}/circ-fig02-basal-needs.png', dpi=150, bbox_inches='tight')
        plt.close()
        print(f"  → Saved circ-fig02-basal-needs.png")

    output = {'experiment': 'EXP-2052', 'title': 'Circadian Basal Needs',
              'per_patient': results, 'population_hourly': pop_hourly}
    with open(f'{EXP_DIR}/exp-2052_circadian_basal.json', 'w') as f:
        json.dump(output, f, indent=2)
    return output


# ── EXP-2053: Dawn Phenomenon Characterization ──────────────────────
def exp_2053_dawn_phenomenon():
    """Characterize dawn phenomenon: onset, amplitude, predictors."""
    print("\n═══ EXP-2053: Dawn Phenomenon Characterization ═══")

    results = {}
    all_dawn_amplitudes = []
    all_dawn_onsets = []

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values

        dawn_events = []
        n_days = len(g) // STEPS_PER_DAY

        for day in range(n_days):
            start = day * STEPS_PER_DAY
            # Night window: midnight to 3am (looking for nadir)
            night_start = start + 0 * STEPS_PER_HOUR  # midnight
            night_end = start + 4 * STEPS_PER_HOUR    # 4am
            # Dawn window: 4am to 8am (looking for rise)
            dawn_start = start + 4 * STEPS_PER_HOUR
            dawn_end = start + 8 * STEPS_PER_HOUR

            if dawn_end > len(g):
                break

            night_g = g[night_start:night_end]
            dawn_g = g[dawn_start:dawn_end]

            night_valid = ~np.isnan(night_g)
            dawn_valid = ~np.isnan(dawn_g)

            if night_valid.sum() < 6 or dawn_valid.sum() < 6:
                continue

            night_nadir = np.nanmin(night_g)
            night_nadir_idx = np.nanargmin(night_g)
            dawn_peak = np.nanmax(dawn_g)
            dawn_peak_idx = np.nanargmax(dawn_g)

            amplitude = dawn_peak - night_nadir

            # Onset: first time glucose starts rising > 2 mg/dL above nadir
            onset_idx = None
            full_window = g[night_start:dawn_end]
            nadir_pos = np.nanargmin(full_window[:len(night_g)])
            for idx in range(nadir_pos, len(full_window)):
                if not np.isnan(full_window[idx]) and full_window[idx] > night_nadir + 5:
                    onset_idx = idx
                    break

            onset_hour = (onset_idx / STEPS_PER_HOUR) if onset_idx is not None else None

            # Pre-bed glucose (10pm-midnight)
            if start >= 2 * STEPS_PER_HOUR:
                prebed = g[start - 2 * STEPS_PER_HOUR:start]
                prebed_g = np.nanmean(prebed) if np.sum(~np.isnan(prebed)) > 3 else None
            else:
                prebed_g = None

            dawn_events.append({
                'amplitude': float(amplitude),
                'night_nadir': float(night_nadir),
                'dawn_peak': float(dawn_peak),
                'onset_hour': float(onset_hour) if onset_hour else None,
                'prebed_glucose': float(prebed_g) if prebed_g else None
            })

            all_dawn_amplitudes.append(amplitude)
            if onset_hour is not None:
                all_dawn_onsets.append(onset_hour)

        amplitudes = [e['amplitude'] for e in dawn_events]
        onsets = [e['onset_hour'] for e in dawn_events if e['onset_hour'] is not None]

        # Dawn presence: amplitude > 20 mg/dL on > 30% of nights
        dawn_present = sum(1 for a in amplitudes if a > 20) / max(len(amplitudes), 1)

        # Pre-bed correlation
        valid_pairs = [(e['prebed_glucose'], e['amplitude'])
                       for e in dawn_events
                       if e['prebed_glucose'] is not None and not np.isnan(e['amplitude'])]
        if len(valid_pairs) >= 10:
            x, y = zip(*valid_pairs)
            r = np.corrcoef(x, y)[0, 1]
        else:
            r = float('nan')

        results[name] = {
            'n_nights': len(dawn_events),
            'amplitude_median': float(np.median(amplitudes)) if amplitudes else None,
            'amplitude_mean': float(np.mean(amplitudes)) if amplitudes else None,
            'amplitude_sd': float(np.std(amplitudes)) if amplitudes else None,
            'onset_median': float(np.median(onsets)) if onsets else None,
            'dawn_present_frac': round(dawn_present, 2),
            'prebed_correlation': round(r, 3) if not np.isnan(r) else None
        }
        print(f"  {name}: {len(dawn_events)} nights, amp={np.median(amplitudes):.0f}±{np.std(amplitudes):.0f} mg/dL, "
              f"onset={np.median(onsets):.1f}h, present={dawn_present:.0%}")

    if MAKE_FIGS:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        # Left: amplitude distribution by patient
        ax = axes[0]
        patient_amps = []
        pnames = []
        for n, r in sorted(results.items()):
            if r['amplitude_median'] is not None:
                pnames.append(n)
                patient_amps.append(r['amplitude_median'])
        colors = ['#d62728' if a > 40 else '#ff7f0e' if a > 20 else '#2ca02c' for a in patient_amps]
        ax.barh(pnames, patient_amps, color=colors, alpha=0.7)
        ax.axvline(x=20, color='orange', linestyle='--', alpha=0.7, label='Clinically significant')
        ax.set_xlabel('Dawn Amplitude (mg/dL)')
        ax.set_title('Dawn Phenomenon Amplitude by Patient')
        ax.legend()
        ax.grid(True, alpha=0.3, axis='x')

        # Right: onset time distribution
        ax = axes[1]
        if all_dawn_onsets:
            ax.hist(all_dawn_onsets, bins=np.arange(0, 8.5, 0.5), color='steelblue',
                    alpha=0.7, edgecolor='white')
            ax.axvline(x=np.median(all_dawn_onsets), color='red', linestyle='--',
                       label=f'Median={np.median(all_dawn_onsets):.1f}h')
            ax.set_xlabel('Onset Time (hours after midnight)')
            ax.set_ylabel('Count')
            ax.set_title('Dawn Rise Onset Time Distribution')
            ax.legend()
            ax.grid(True, alpha=0.3)

        plt.tight_layout()
        fig.savefig(f'{FIG_DIR}/circ-fig03-dawn.png', dpi=150, bbox_inches='tight')
        plt.close()
        print(f"  → Saved circ-fig03-dawn.png")

    output = {'experiment': 'EXP-2053', 'title': 'Dawn Phenomenon',
              'per_patient': results,
              'population': {
                  'amplitude_median': float(np.median(all_dawn_amplitudes)),
                  'onset_median': float(np.median(all_dawn_onsets)) if all_dawn_onsets else None,
                  'n_total': len(all_dawn_amplitudes)
              }}
    with open(f'{EXP_DIR}/exp-2053_dawn_phenomenon.json', 'w') as f:
        json.dump(output, f, indent=2)
    return output


# ── EXP-2054: Time-of-Day Meal ISF ──────────────────────────────────
def exp_2054_meal_isf_by_time():
    """Compare insulin effectiveness after meals at different times of day."""
    print("\n═══ EXP-2054: Post-Meal ISF by Time of Day ═══")

    results = {}
    period_all = {'breakfast': [], 'lunch': [], 'dinner': [], 'snack': []}

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
        iob = df['iob'].values

        period_data = {'breakfast': [], 'lunch': [], 'dinner': [], 'snack': []}

        for i in range(len(g) - 4 * STEPS_PER_HOUR):
            if np.isnan(carbs[i]) or carbs[i] < 10:
                continue
            if np.isnan(g[i]):
                continue

            # Measure: glucose spike in 2h, total insulin in 4h
            future_g = g[i:i + 3 * STEPS_PER_HOUR]
            valid = ~np.isnan(future_g)
            if valid.sum() < STEPS_PER_HOUR:
                continue

            spike = np.nanmax(future_g) - g[i]

            # Total bolus insulin in next 2h
            total_insulin = np.nansum(bolus[i:i + 2 * STEPS_PER_HOUR])
            if total_insulin < 0.5:
                continue

            # Effective ISF: spike per unit insulin (lower = more sensitive)
            # Actually: spike per carb, adjusted for insulin
            effectiveness = spike / total_insulin  # mg/dL per unit

            period = classify_meal_time(i)
            period_data[period].append({
                'spike': float(spike),
                'insulin': float(total_insulin),
                'effectiveness': float(effectiveness),
                'carbs': float(carbs[i]),
                'pre_glucose': float(g[i])
            })
            period_all[period].append(effectiveness)

        patient_result = {}
        for period, events in period_data.items():
            if len(events) >= 5:
                effs = [e['effectiveness'] for e in events]
                spikes = [e['spike'] for e in events]
                patient_result[period] = {
                    'n': len(events),
                    'effectiveness_median': float(np.median(effs)),
                    'spike_median': float(np.median(spikes)),
                }

        results[name] = patient_result
        summary = ", ".join(f"{k}={v['effectiveness_median']:.0f}" for k, v in patient_result.items())
        print(f"  {name}: {summary}")

    # Population summary
    print("\n  Population effectiveness (mg/dL spike per unit insulin):")
    pop_summary = {}
    for period in ['breakfast', 'lunch', 'dinner', 'snack']:
        if len(period_all[period]) >= 10:
            med = np.median(period_all[period])
            n = len(period_all[period])
            pop_summary[period] = {'median': float(med), 'n': n}
            print(f"    {period:>10}: {med:.0f} mg/dL/U (n={n})")

    if MAKE_FIGS:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        # Left: population comparison
        ax = axes[0]
        periods = [p for p in ['breakfast', 'lunch', 'dinner', 'snack'] if p in pop_summary]
        meds = [pop_summary[p]['median'] for p in periods]
        ns = [pop_summary[p]['n'] for p in periods]
        colors = ['#ff7f0e', '#2ca02c', '#d62728', '#7f7f7f']
        bars = ax.bar(periods, meds, color=colors[:len(periods)], alpha=0.7)
        for bar, n in zip(bars, ns):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
                    f'n={n}', ha='center', va='bottom', fontsize=9)
        ax.set_ylabel('Spike per Unit Insulin (mg/dL/U)')
        ax.set_title('Insulin Effectiveness by Meal Time')
        ax.grid(True, alpha=0.3, axis='y')

        # Right: per-patient dinner/breakfast ratio
        ax = axes[1]
        ratios = []
        pnames = []
        for name, pr in sorted(results.items()):
            if 'breakfast' in pr and 'dinner' in pr:
                ratio = pr['dinner']['effectiveness_median'] / max(pr['breakfast']['effectiveness_median'], 0.1)
                ratios.append(ratio)
                pnames.append(name)
        if ratios:
            colors = ['#d62728' if r > 1.3 else '#2ca02c' if r < 0.7 else '#7f7f7f' for r in ratios]
            ax.barh(pnames, ratios, color=colors, alpha=0.7)
            ax.axvline(x=1, color='black', linestyle='--', alpha=0.5)
            ax.set_xlabel('Dinner/Breakfast Effectiveness Ratio')
            ax.set_title('Insulin Less Effective at Dinner (>1)')
            ax.grid(True, alpha=0.3, axis='x')

        plt.tight_layout()
        fig.savefig(f'{FIG_DIR}/circ-fig04-meal-isf.png', dpi=150, bbox_inches='tight')
        plt.close()
        print(f"  → Saved circ-fig04-meal-isf.png")

    output = {'experiment': 'EXP-2054', 'title': 'Meal ISF by Time of Day',
              'per_patient': results, 'population': pop_summary}
    with open(f'{EXP_DIR}/exp-2054_meal_isf_time.json', 'w') as f:
        json.dump(output, f, indent=2)
    return output


# ── EXP-2055: Glucose Rate-of-Change Patterns ───────────────────────
def exp_2055_roc_patterns():
    """Circadian rhythm in glucose rate of change."""
    print("\n═══ EXP-2055: Glucose Rate-of-Change Circadian Patterns ═══")

    results = {}
    all_hourly_roc = {h: [] for h in range(24)}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values

        hourly_roc = {h: [] for h in range(24)}

        for i in range(1, len(g)):
            if np.isnan(g[i]) or np.isnan(g[i-1]):
                continue
            roc = (g[i] - g[i-1]) * STEPS_PER_HOUR  # mg/dL per hour
            if abs(roc) > 200:
                continue  # artifact
            hour = (i % STEPS_PER_DAY) // STEPS_PER_HOUR
            hourly_roc[hour].append(roc)
            all_hourly_roc[hour].append(roc)

        patient_hourly = {}
        for h in range(24):
            if len(hourly_roc[h]) >= 50:
                vals = hourly_roc[h]
                patient_hourly[h] = {
                    'mean': float(np.mean(vals)),
                    'std': float(np.std(vals)),
                    'positive_frac': float(np.mean([v > 0 for v in vals])),
                    'abs_mean': float(np.mean(np.abs(vals)))
                }

        # Volatility ratio: max_std / min_std
        if len(patient_hourly) >= 12:
            stds = [v['std'] for v in patient_hourly.values()]
            volatility_ratio = max(stds) / min(stds) if min(stds) > 0 else float('nan')
        else:
            volatility_ratio = float('nan')

        results[name] = {
            'hours_with_data': len(patient_hourly),
            'volatility_ratio': round(volatility_ratio, 2) if not np.isnan(volatility_ratio) else None,
            'hourly': patient_hourly
        }
        print(f"  {name}: volatility ratio={volatility_ratio:.2f}" if not np.isnan(volatility_ratio) else
              f"  {name}: insufficient data")

    # Population
    pop_hourly = {}
    for h in range(24):
        if len(all_hourly_roc[h]) >= 100:
            vals = all_hourly_roc[h]
            pop_hourly[h] = {
                'mean': float(np.mean(vals)),
                'std': float(np.std(vals)),
                'abs_mean': float(np.mean(np.abs(vals))),
                'positive_frac': float(np.mean([v > 0 for v in vals]))
            }

    print("\n  Population glucose volatility by hour:")
    for h in sorted(pop_hourly.keys()):
        v = pop_hourly[h]
        print(f"    {h:02d}:00  mean={v['mean']:+.1f}, |RoC|={v['abs_mean']:.1f}, "
              f"std={v['std']:.1f}, ↑{v['positive_frac']:.0%}")

    if MAKE_FIGS:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        hours = sorted(pop_hourly.keys())
        # Left: mean RoC and volatility
        ax = axes[0]
        means = [pop_hourly[h]['mean'] for h in hours]
        stds = [pop_hourly[h]['std'] for h in hours]
        ax.fill_between(hours, [m - s for m, s in zip(means, stds)],
                        [m + s for m, s in zip(means, stds)],
                        alpha=0.2, color='steelblue')
        ax.plot(hours, means, 'o-', color='steelblue', linewidth=2, label='Mean RoC')
        ax.axhline(y=0, color='black', linewidth=1)
        ax.set_xlabel('Hour of Day')
        ax.set_ylabel('Rate of Change (mg/dL/hr)')
        ax.set_title('Circadian Glucose Velocity')
        ax.set_xticks(range(0, 24, 3))
        ax.legend()
        ax.grid(True, alpha=0.3)

        # Right: absolute volatility
        ax = axes[1]
        abs_means = [pop_hourly[h]['abs_mean'] for h in hours]
        ax.bar(hours, abs_means, color='coral', alpha=0.7)
        ax.set_xlabel('Hour of Day')
        ax.set_ylabel('|Rate of Change| (mg/dL/hr)')
        ax.set_title('Glucose Volatility by Hour (Higher = More Unstable)')
        ax.set_xticks(range(0, 24, 3))
        ax.grid(True, alpha=0.3)

        plt.tight_layout()
        fig.savefig(f'{FIG_DIR}/circ-fig05-roc-patterns.png', dpi=150, bbox_inches='tight')
        plt.close()
        print(f"  → Saved circ-fig05-roc-patterns.png")

    output = {'experiment': 'EXP-2055', 'title': 'Rate-of-Change Patterns',
              'per_patient': results, 'population_hourly': pop_hourly}
    with open(f'{EXP_DIR}/exp-2055_roc_patterns.json', 'w') as f:
        json.dump(output, f, indent=2)
    return output


# ── EXP-2056: IOB-Dependent Insulin Sensitivity ─────────────────────
def exp_2056_iob_sensitivity():
    """Does insulin sensitivity decrease with high IOB (diminishing returns)?"""
    print("\n═══ EXP-2056: IOB-Dependent Insulin Sensitivity ═══")

    results = {}
    all_iob_bins = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        iob = df['iob'].values
        bolus = df['bolus'].values
        carbs = df['carbs'].values

        # Find correction events (bolus > 0.5U, no carbs ±1h, glucose > 150)
        corrections = []
        for i in range(STEPS_PER_HOUR, len(g) - 4 * STEPS_PER_HOUR):
            if bolus[i] < 0.5 or np.isnan(g[i]) or g[i] < 150:
                continue
            carb_window = carbs[max(0, i - STEPS_PER_HOUR):i + STEPS_PER_HOUR]
            if np.nansum(carb_window) > 1:
                continue

            future_g = g[i:i + 3 * STEPS_PER_HOUR]
            if np.sum(~np.isnan(future_g)) < STEPS_PER_HOUR:
                continue

            delta_g = g[i] - np.nanmin(future_g)
            if delta_g < 5:
                continue

            current_iob = iob[i] if not np.isnan(iob[i]) else 0
            isf_eff = delta_g / bolus[i]

            if isf_eff < 5 or isf_eff > 300:
                continue

            corrections.append({
                'iob': float(current_iob),
                'isf': float(isf_eff),
                'dose': float(bolus[i]),
                'glucose': float(g[i])
            })

        if len(corrections) < 10:
            results[name] = {'n_corrections': len(corrections), 'iob_effect': None}
            print(f"  {name}: {len(corrections)} corrections (insufficient)")
            continue

        # Bin by IOB quartiles
        iobs = [c['iob'] for c in corrections]
        isfs = [c['isf'] for c in corrections]
        q25, q50, q75 = np.percentile(iobs, [25, 50, 75])

        bins = {
            'low_iob': [c['isf'] for c in corrections if c['iob'] <= q25],
            'med_iob': [c['isf'] for c in corrections if q25 < c['iob'] <= q75],
            'high_iob': [c['isf'] for c in corrections if c['iob'] > q75],
        }

        bin_medians = {}
        for bname, vals in bins.items():
            if len(vals) >= 3:
                bin_medians[bname] = float(np.median(vals))

        # Correlation
        r = np.corrcoef(iobs, isfs)[0, 1] if len(iobs) >= 10 else float('nan')

        # IOB sensitivity ratio: low_iob ISF / high_iob ISF
        if 'low_iob' in bin_medians and 'high_iob' in bin_medians and bin_medians['high_iob'] > 0:
            sensitivity_ratio = bin_medians['low_iob'] / bin_medians['high_iob']
        else:
            sensitivity_ratio = float('nan')

        results[name] = {
            'n_corrections': len(corrections),
            'iob_isf_correlation': round(r, 3) if not np.isnan(r) else None,
            'sensitivity_ratio': round(sensitivity_ratio, 2) if not np.isnan(sensitivity_ratio) else None,
            'bin_medians': bin_medians,
            'iob_quartiles': [round(q25, 1), round(q50, 1), round(q75, 1)]
        }

        # Store for population
        for bname, vals in bins.items():
            if bname not in all_iob_bins:
                all_iob_bins[bname] = []
            all_iob_bins[bname].extend(vals)

        print(f"  {name}: {len(corrections)} corrections, r(IOB,ISF)={r:.3f}, "
              f"ratio={sensitivity_ratio:.2f}" if not np.isnan(sensitivity_ratio) else
              f"  {name}: {len(corrections)} corrections, r(IOB,ISF)={r:.3f}")

    # Population
    pop_bins = {}
    for bname, vals in all_iob_bins.items():
        if len(vals) >= 10:
            pop_bins[bname] = float(np.median(vals))

    print(f"\n  Population ISF by IOB level:")
    for bname in ['low_iob', 'med_iob', 'high_iob']:
        if bname in pop_bins:
            print(f"    {bname}: ISF={pop_bins[bname]:.0f}")

    if MAKE_FIGS:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        # Left: population IOB bins
        ax = axes[0]
        if pop_bins:
            bnames = [b for b in ['low_iob', 'med_iob', 'high_iob'] if b in pop_bins]
            vals = [pop_bins[b] for b in bnames]
            labels = ['Low IOB\n(Q1)', 'Medium IOB\n(Q2-Q3)', 'High IOB\n(Q4)'][:len(bnames)]
            colors = ['#2ca02c', '#ff7f0e', '#d62728'][:len(bnames)]
            ax.bar(labels, vals, color=colors, alpha=0.7)
            ax.set_ylabel('ISF (mg/dL per unit)')
            ax.set_title('Insulin Sensitivity by IOB Level (Population)')
            ax.grid(True, alpha=0.3, axis='y')

        # Right: per-patient sensitivity ratios
        ax = axes[1]
        ratios = []
        pnames = []
        for name, r in sorted(results.items()):
            sr = r.get('sensitivity_ratio')
            if sr is not None and not np.isnan(sr):
                ratios.append(sr)
                pnames.append(name)
        if ratios:
            colors = ['#d62728' if r > 1.5 else '#ff7f0e' if r > 1.2 else '#2ca02c' for r in ratios]
            ax.barh(pnames, ratios, color=colors, alpha=0.7)
            ax.axvline(x=1, color='black', linestyle='--', alpha=0.5, label='No IOB effect')
            ax.set_xlabel('Low-IOB/High-IOB ISF Ratio (>1 = diminishing returns)')
            ax.set_title('IOB-Dependent Sensitivity Loss')
            ax.legend()
            ax.grid(True, alpha=0.3, axis='x')

        plt.tight_layout()
        fig.savefig(f'{FIG_DIR}/circ-fig06-iob-sensitivity.png', dpi=150, bbox_inches='tight')
        plt.close()
        print(f"  → Saved circ-fig06-iob-sensitivity.png")

    output = {'experiment': 'EXP-2056', 'title': 'IOB-Dependent Sensitivity',
              'per_patient': results, 'population_bins': pop_bins}
    with open(f'{EXP_DIR}/exp-2056_iob_sensitivity.json', 'w') as f:
        json.dump(output, f, indent=2)
    return output


# ── EXP-2057: Counter-Regulatory Response Quantification ────────────
def exp_2057_counter_regulatory():
    """Quantify post-hypo rebound: amplitude, duration, and predictors."""
    print("\n═══ EXP-2057: Counter-Regulatory Response Quantification ═══")

    results = {}
    all_rebounds = []

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        carbs = df['carbs'].values

        hypo_events = []

        # Find hypo events: glucose < 70
        in_hypo = False
        hypo_start = None

        for i in range(len(g) - 4 * STEPS_PER_HOUR):
            if np.isnan(g[i]):
                continue

            if g[i] < HYPO_THRESH and not in_hypo:
                in_hypo = True
                hypo_start = i
            elif g[i] >= HYPO_THRESH and in_hypo:
                in_hypo = False
                hypo_nadir = np.nanmin(g[hypo_start:i])
                hypo_duration = (i - hypo_start) / STEPS_PER_HOUR  # hours

                # Track post-hypo trajectory for 4h
                post = g[i:i + 4 * STEPS_PER_HOUR]
                post_valid = ~np.isnan(post)
                if post_valid.sum() < STEPS_PER_HOUR:
                    continue

                post_peak = np.nanmax(post)
                rebound_amplitude = post_peak - g[i]  # from exit to peak
                time_to_peak = np.nanargmax(post) / STEPS_PER_HOUR

                # Did they go hyper?
                went_hyper = post_peak > TARGET_HIGH

                # Was carb treatment involved?
                carb_window = carbs[max(hypo_start - 2, 0):i + STEPS_PER_HOUR]
                carb_treatment = np.nansum(carb_window)

                hypo_events.append({
                    'nadir': float(hypo_nadir),
                    'duration': float(hypo_duration),
                    'exit_glucose': float(g[i]),
                    'rebound_amplitude': float(rebound_amplitude),
                    'peak_post': float(post_peak),
                    'time_to_peak': float(time_to_peak),
                    'went_hyper': bool(went_hyper),
                    'carb_treatment': float(carb_treatment)
                })
                all_rebounds.append({
                    'nadir': float(hypo_nadir),
                    'rebound': float(rebound_amplitude),
                    'went_hyper': bool(went_hyper),
                    'duration': float(hypo_duration)
                })

        if not hypo_events:
            results[name] = {'n_events': 0}
            print(f"  {name}: no hypo events")
            continue

        rebounds = [e['rebound_amplitude'] for e in hypo_events]
        hyper_frac = np.mean([e['went_hyper'] for e in hypo_events])
        nadirs = [e['nadir'] for e in hypo_events]
        durations = [e['duration'] for e in hypo_events]

        # Correlation: deeper hypo → bigger rebound?
        if len(rebounds) >= 5:
            r_nadir = np.corrcoef(nadirs, rebounds)[0, 1]
        else:
            r_nadir = float('nan')

        results[name] = {
            'n_events': len(hypo_events),
            'rebound_median': float(np.median(rebounds)),
            'rebound_mean': float(np.mean(rebounds)),
            'went_hyper_frac': round(hyper_frac, 2),
            'nadir_median': float(np.median(nadirs)),
            'duration_median': float(np.median(durations)),
            'nadir_rebound_corr': round(r_nadir, 3) if not np.isnan(r_nadir) else None,
            'carb_treatment_median': float(np.median([e['carb_treatment'] for e in hypo_events]))
        }
        print(f"  {name}: {len(hypo_events)} events, rebound={np.median(rebounds):.0f} mg/dL, "
              f"→hyper={hyper_frac:.0%}, nadir={np.median(nadirs):.0f}")

    # Population
    if all_rebounds:
        pop_rebound = float(np.median([r['rebound'] for r in all_rebounds]))
        pop_hyper = float(np.mean([r['went_hyper'] for r in all_rebounds]))
        pop_nadir = float(np.median([r['nadir'] for r in all_rebounds]))
        pop_duration = float(np.median([r['duration'] for r in all_rebounds]))

        print(f"\n  Population: {len(all_rebounds)} total hypos")
        print(f"    Rebound: {pop_rebound:.0f} mg/dL")
        print(f"    →Hyper: {pop_hyper:.0%}")
        print(f"    Nadir: {pop_nadir:.0f} mg/dL")
        print(f"    Duration: {pop_duration:.1f} hours")
    else:
        pop_rebound = pop_hyper = pop_nadir = pop_duration = None

    if MAKE_FIGS:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        # Left: rebound amplitude by patient
        ax = axes[0]
        pnames = []
        rebds = []
        hyper_fracs = []
        for name, r in sorted(results.items()):
            if r.get('rebound_median') is not None:
                pnames.append(name)
                rebds.append(r['rebound_median'])
                hyper_fracs.append(r['went_hyper_frac'])

        if pnames:
            colors = ['#d62728' if h > 0.3 else '#ff7f0e' if h > 0.1 else '#2ca02c'
                       for h in hyper_fracs]
            bars = ax.barh(pnames, rebds, color=colors, alpha=0.7)
            ax.axvline(x=110, color='red', linestyle='--', alpha=0.5,
                       label='Hyper threshold (180-70)')
            ax.set_xlabel('Post-Hypo Rebound (mg/dL)')
            ax.set_title('Counter-Regulatory Rebound Amplitude')
            ax.legend()
            ax.grid(True, alpha=0.3, axis='x')

        # Right: nadir vs rebound scatter
        ax = axes[1]
        if all_rebounds:
            nadirs = [r['nadir'] for r in all_rebounds]
            rebounds = [r['rebound'] for r in all_rebounds]
            colors = ['#d62728' if r['went_hyper'] else '#2ca02c' for r in all_rebounds]
            ax.scatter(nadirs, rebounds, c=colors, alpha=0.2, s=10)
            ax.set_xlabel('Hypo Nadir (mg/dL)')
            ax.set_ylabel('Rebound Amplitude (mg/dL)')
            ax.set_title('Deeper Hypo → Bigger Rebound?')
            ax.axhline(y=110, color='red', linestyle='--', alpha=0.5, label='→Hyper level')
            ax.legend()
            ax.grid(True, alpha=0.3)

        plt.tight_layout()
        fig.savefig(f'{FIG_DIR}/circ-fig07-counter-regulatory.png', dpi=150, bbox_inches='tight')
        plt.close()
        print(f"  → Saved circ-fig07-counter-regulatory.png")

    output = {'experiment': 'EXP-2057', 'title': 'Counter-Regulatory Response',
              'per_patient': results,
              'population': {
                  'rebound_median': pop_rebound, 'went_hyper_frac': pop_hyper,
                  'nadir_median': pop_nadir, 'duration_median': pop_duration,
                  'n_total': len(all_rebounds)
              }}
    with open(f'{EXP_DIR}/exp-2057_counter_regulatory.json', 'w') as f:
        json.dump(output, f, indent=2)
    return output


# ── EXP-2058: Synthesis — Optimal 24h Therapy Profile ────────────────
def exp_2058_synthesis():
    """Combine circadian findings into optimal therapy profile."""
    print("\n═══ EXP-2058: Synthesis — Optimal 24h Therapy Profile ═══")

    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        iob = df['iob'].values
        carbs = df['carbs'].values
        bolus = df['bolus'].values

        # Get profile settings
        isf_schedule = df.attrs.get('isf_schedule', {})
        cr_schedule = df.attrs.get('cr_schedule', {})
        basal_schedule = df.attrs.get('basal_schedule', {})

        # Compute hourly metrics
        hourly_metrics = {}
        for h in range(24):
            mask = np.zeros(len(g), dtype=bool)
            for day in range(len(g) // STEPS_PER_DAY):
                start = day * STEPS_PER_DAY + h * STEPS_PER_HOUR
                end = start + STEPS_PER_HOUR
                if end <= len(g):
                    mask[start:end] = True

            hour_g = g[mask]
            valid = ~np.isnan(hour_g)
            if valid.sum() < 30:
                continue

            hour_g_valid = hour_g[valid]
            tir = np.mean((hour_g_valid >= TARGET_LOW) & (hour_g_valid <= TARGET_HIGH))
            tbr = np.mean(hour_g_valid < TARGET_LOW)
            tar = np.mean(hour_g_valid > TARGET_HIGH)
            mean_g = np.mean(hour_g_valid)
            std_g = np.std(hour_g_valid)

            hour_iob = iob[mask]
            mean_iob = np.nanmean(hour_iob)

            hour_carbs = carbs[mask]
            mean_carbs = np.nanmean(hour_carbs) * STEPS_PER_HOUR  # carbs per hour

            hourly_metrics[h] = {
                'tir': round(float(tir), 3),
                'tbr': round(float(tbr), 3),
                'tar': round(float(tar), 3),
                'mean_glucose': round(float(mean_g), 1),
                'std_glucose': round(float(std_g), 1),
                'mean_iob': round(float(mean_iob), 2),
                'carbs_per_hour': round(float(mean_carbs), 1)
            }

        # Identify problem hours (TIR < 60% or TBR > 10%)
        problem_hours = []
        for h, m in hourly_metrics.items():
            issues = []
            if m['tir'] < 0.6:
                issues.append('LOW_TIR')
            if m['tbr'] > 0.10:
                issues.append('HIGH_TBR')
            if m['tar'] > 0.35:
                issues.append('HIGH_TAR')
            if issues:
                problem_hours.append({'hour': h, 'issues': issues, **m})

        # Compute optimization priority
        n_problem = len(problem_hours)
        worst_hour = min(hourly_metrics.items(), key=lambda x: x[1]['tir']) if hourly_metrics else None
        best_hour = max(hourly_metrics.items(), key=lambda x: x[1]['tir']) if hourly_metrics else None

        # Time-varying ISF recommendation based on TIR patterns
        recommendations = []
        for ph in problem_hours:
            if 'HIGH_TAR' in ph['issues']:
                recommendations.append(f"Hour {ph['hour']:02d}: Increase ISF/reduce target (TAR={ph['tar']:.0%})")
            if 'HIGH_TBR' in ph['issues']:
                recommendations.append(f"Hour {ph['hour']:02d}: Decrease ISF/raise target (TBR={ph['tbr']:.0%})")

        results[name] = {
            'hourly_metrics': hourly_metrics,
            'problem_hours': len(problem_hours),
            'worst_hour': worst_hour[0] if worst_hour else None,
            'worst_tir': worst_hour[1]['tir'] if worst_hour else None,
            'best_hour': best_hour[0] if best_hour else None,
            'best_tir': best_hour[1]['tir'] if best_hour else None,
            'recommendations': recommendations[:5],  # top 5
            'tir_range': round(best_hour[1]['tir'] - worst_hour[1]['tir'], 3) if best_hour and worst_hour else None
        }

        print(f"  {name}: {len(problem_hours)} problem hours, "
              f"worst={worst_hour[0]:02d}:00 ({worst_hour[1]['tir']:.0%}), "
              f"best={best_hour[0]:02d}:00 ({best_hour[1]['tir']:.0%}), "
              f"range={results[name]['tir_range']:.0%}" if worst_hour and best_hour else
              f"  {name}: insufficient data")

    # Population synthesis
    print("\n  Population hourly TIR profile:")
    pop_hourly = {}
    for h in range(24):
        tirs = [r['hourly_metrics'].get(h, {}).get('tir') for r in results.values()
                if h in r.get('hourly_metrics', {})]
        tirs = [t for t in tirs if t is not None]
        if tirs:
            pop_hourly[h] = {
                'mean_tir': float(np.mean(tirs)),
                'min_tir': float(np.min(tirs)),
                'max_tir': float(np.max(tirs)),
                'n': len(tirs)
            }
            print(f"    {h:02d}:00  TIR={np.mean(tirs):.0%} "
                  f"[{np.min(tirs):.0%}-{np.max(tirs):.0%}]")

    if MAKE_FIGS:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        # Left: population hourly TIR
        ax = axes[0]
        hours = sorted(pop_hourly.keys())
        tirs = [pop_hourly[h]['mean_tir'] * 100 for h in hours]
        mins = [pop_hourly[h]['min_tir'] * 100 for h in hours]
        maxs = [pop_hourly[h]['max_tir'] * 100 for h in hours]

        ax.fill_between(hours, mins, maxs, alpha=0.2, color='steelblue', label='Range')
        ax.plot(hours, tirs, 'o-', color='steelblue', linewidth=2, label='Mean')
        ax.axhline(y=70, color='green', linestyle='--', alpha=0.5, label='70% target')
        ax.set_xlabel('Hour of Day')
        ax.set_ylabel('Time in Range (%)')
        ax.set_title('Population Hourly TIR Profile')
        ax.set_xticks(range(0, 24, 3))
        ax.set_ylim(0, 100)
        ax.legend()
        ax.grid(True, alpha=0.3)

        # Right: problem hours heatmap
        ax = axes[1]
        patient_names = sorted(results.keys())
        problem_matrix = np.zeros((len(patient_names), 24))
        for pi, pn in enumerate(patient_names):
            for h in range(24):
                m = results[pn].get('hourly_metrics', {}).get(h)
                if m:
                    problem_matrix[pi, h] = m['tir'] * 100

        im = ax.imshow(problem_matrix, aspect='auto', cmap='RdYlGn',
                       vmin=30, vmax=100, interpolation='nearest')
        ax.set_xticks(range(0, 24, 3))
        ax.set_xticklabels([f'{h:02d}' for h in range(0, 24, 3)])
        ax.set_yticks(range(len(patient_names)))
        ax.set_yticklabels(patient_names)
        ax.set_xlabel('Hour of Day')
        ax.set_title('Per-Patient Hourly TIR (%)')
        plt.colorbar(im, ax=ax, label='TIR %', shrink=0.8)

        plt.tight_layout()
        fig.savefig(f'{FIG_DIR}/circ-fig08-synthesis.png', dpi=150, bbox_inches='tight')
        plt.close()
        print(f"  → Saved circ-fig08-synthesis.png")

    output = {'experiment': 'EXP-2058', 'title': 'Optimal 24h Therapy Profile',
              'per_patient': {k: {kk: vv for kk, vv in v.items() if kk != 'hourly_metrics'}
                             for k, v in results.items()},
              'population_hourly': pop_hourly}
    with open(f'{EXP_DIR}/exp-2058_synthesis.json', 'w') as f:
        json.dump(output, f, indent=2)
    return output


# ── Main ─────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print("=" * 60)
    print("EXP-2051–2058: Circadian Therapy Profiling")
    print("=" * 60)

    r1 = exp_2051_circadian_isf()
    r2 = exp_2052_circadian_basal()
    r3 = exp_2053_dawn_phenomenon()
    r4 = exp_2054_meal_isf_by_time()
    r5 = exp_2055_roc_patterns()
    r6 = exp_2056_iob_sensitivity()
    r7 = exp_2057_counter_regulatory()
    r8 = exp_2058_synthesis()

    print("\n" + "=" * 60)
    passed = sum(1 for r in [r1, r2, r3, r4, r5, r6, r7, r8] if r is not None)
    print(f"Results: {passed}/8 experiments completed")
    if MAKE_FIGS:
        print(f"Figures saved to {FIG_DIR}/circ-fig01–08")
    print("=" * 60)
