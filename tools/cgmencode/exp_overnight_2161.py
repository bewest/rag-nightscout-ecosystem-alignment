#!/usr/bin/env python3
"""
EXP-2161–2168: Overnight Dynamics & AID Behavior Analysis

Characterize overnight glucose patterns, AID automated delivery behavior,
and derive alternative basal assessment methods that work with AID data.

EXP-2161: Overnight glucose pattern classification — flat, rising, falling, V-shape
EXP-2162: AID overnight delivery analysis — how much does the loop adjust basal?
EXP-2163: Dawn phenomenon quantification — 4am-8am glucose rise by patient
EXP-2164: Alternative basal assessment — use AID delivery as signal, not fasting
EXP-2165: Overnight hypo analysis — when, why, and how deep
EXP-2166: Sleep quality proxy — overnight glucose stability as sleep marker
EXP-2167: Circadian glucose profile — 24h mean glucose curve per patient
EXP-2168: Integrated overnight recommendations — per-patient basal + overnight strategy

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
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
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


def get_profile_value(schedule, hour):
    if not schedule:
        return None
    sorted_sched = sorted(schedule, key=lambda x: x.get('timeAsSeconds', 0))
    result = sorted_sched[0].get('value', None)
    target_seconds = hour * 3600
    for entry in sorted_sched:
        if entry.get('timeAsSeconds', 0) <= target_seconds:
            result = entry.get('value', result)
    return result


# ── EXP-2161: Overnight Glucose Pattern Classification ──────────────
def exp_2161_overnight_patterns():
    """Classify overnight glucose into pattern types."""
    print("\n═══ EXP-2161: Overnight Glucose Pattern Classification ═══")

    all_results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        n_days = len(g) // STEPS_PER_DAY

        patterns = {'flat': 0, 'rising': 0, 'falling': 0, 'v_shape': 0,
                     'peak': 0, 'volatile': 0}
        night_data = []

        for d in range(n_days):
            # Midnight (0h) to 6am
            start = d * STEPS_PER_DAY
            end = start + 6 * STEPS_PER_HOUR
            if end >= len(g):
                continue

            night_g = g[start:end]
            valid = ~np.isnan(night_g)
            if valid.sum() < len(night_g) * 0.6:
                continue

            night_clean = night_g[valid]
            mean_g = float(np.mean(night_clean))
            std_g = float(np.std(night_clean))
            cv = std_g / mean_g if mean_g > 0 else 0

            # First and last third
            n = len(night_clean)
            first = np.mean(night_clean[:n//3])
            middle = np.mean(night_clean[n//3:2*n//3])
            last = np.mean(night_clean[2*n//3:])

            delta = last - first  # Overall change
            min_g = float(np.min(night_clean))
            max_g = float(np.max(night_clean))
            range_g = max_g - min_g

            # Classify
            if cv > 0.15 or range_g > 80:
                pattern = 'volatile'
            elif abs(delta) < 10 and range_g < 30:
                pattern = 'flat'
            elif delta > 15:
                pattern = 'rising'
            elif delta < -15:
                pattern = 'falling'
            elif middle < first - 10 and middle < last - 10:
                pattern = 'v_shape'
            elif middle > first + 10 and middle > last + 10:
                pattern = 'peak'
            else:
                pattern = 'flat'

            patterns[pattern] += 1
            night_data.append({
                'day': d,
                'pattern': pattern,
                'mean': mean_g,
                'std': std_g,
                'delta': float(delta),
                'min': min_g,
                'max': max_g
            })

        total = sum(patterns.values())
        if total == 0:
            continue

        dominant = max(patterns, key=patterns.get)
        all_results[name] = {
            'n_nights': total,
            'patterns': {k: v for k, v in patterns.items()},
            'pattern_pct': {k: v / total * 100 for k, v in patterns.items()},
            'dominant': dominant,
            'mean_overnight_glucose': float(np.mean([n['mean'] for n in night_data])),
            'mean_overnight_delta': float(np.mean([n['delta'] for n in night_data]))
        }

        pcts = [f"{k}={v*100//total}%" for k, v in patterns.items() if v > 0]
        print(f"  {name}: {total} nights, dominant={dominant}, "
              f"mean_delta={np.mean([n['delta'] for n in night_data]):+.1f} mg/dL, "
              f"{' '.join(pcts)}")

    with open(f'{EXP_DIR}/exp-2161_overnight_patterns.json', 'w') as f:
        json.dump(all_results, f, indent=2, cls=NumpyEncoder)

    if MAKE_FIGS and all_results:
        fig, axes = plt.subplots(1, 3, figsize=(16, 5))

        patient_names = sorted(all_results.keys())
        pattern_types = ['flat', 'rising', 'falling', 'v_shape', 'peak', 'volatile']
        colors_p = plt.cm.Set2(np.linspace(0, 1, len(pattern_types)))

        # Panel 1: Stacked bar of pattern types
        bottom = np.zeros(len(patient_names))
        for pi, pt in enumerate(pattern_types):
            vals = [all_results[pn]['patterns'].get(pt, 0) for pn in patient_names]
            if sum(vals) > 0:
                axes[0].bar(patient_names, vals, bottom=bottom, label=pt,
                            color=colors_p[pi], alpha=0.8)
                bottom += vals
        axes[0].set_ylabel('Number of Nights')
        axes[0].set_title('Overnight Pattern Distribution')
        axes[0].legend(fontsize=7, loc='upper right')
        axes[0].tick_params(axis='x', labelsize=8)

        # Panel 2: Mean overnight delta
        deltas = [all_results[pn]['mean_overnight_delta'] for pn in patient_names]
        colors_d = ['red' if d > 10 else 'green' if abs(d) < 10 else 'blue' for d in deltas]
        axes[1].bar(patient_names, deltas, color=colors_d, alpha=0.7)
        axes[1].axhline(y=0, color='black', linewidth=0.5)
        axes[1].axhline(y=10, color='red', linestyle='--', alpha=0.3)
        axes[1].axhline(y=-10, color='blue', linestyle='--', alpha=0.3)
        axes[1].set_ylabel('Mean Overnight Δ (mg/dL)')
        axes[1].set_title('Overnight Glucose Drift')
        axes[1].tick_params(axis='x', labelsize=8)
        axes[1].grid(True, alpha=0.3, axis='y')

        # Panel 3: Mean overnight glucose
        means = [all_results[pn]['mean_overnight_glucose'] for pn in patient_names]
        colors_m = ['green' if 70 <= m <= 180 else 'red' for m in means]
        axes[2].bar(patient_names, means, color=colors_m, alpha=0.7)
        axes[2].axhline(y=70, color='green', linestyle='--', alpha=0.3)
        axes[2].axhline(y=180, color='red', linestyle='--', alpha=0.3)
        axes[2].set_ylabel('Mean Overnight Glucose (mg/dL)')
        axes[2].set_title('Overnight Glucose Level')
        axes[2].tick_params(axis='x', labelsize=8)
        axes[2].grid(True, alpha=0.3, axis='y')

        plt.tight_layout()
        plt.savefig(f'{FIG_DIR}/night-fig01-patterns.png', dpi=150)
        plt.close()
        print("  → Saved night-fig01-patterns.png")

    return all_results


# ── EXP-2162: AID Overnight Delivery Analysis ───────────────────────
def exp_2162_aid_delivery():
    """How much does the AID loop adjust basal overnight?"""
    print("\n═══ EXP-2162: AID Overnight Delivery Analysis ═══")

    all_results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        n_days = len(g) // STEPS_PER_DAY

        # Check for enacted_rate or temp_rate
        has_rate = 'enacted_rate' in df.columns or 'temp_rate' in df.columns
        has_net = 'net_basal' in df.columns

        if has_rate:
            rate_col = 'enacted_rate' if 'enacted_rate' in df.columns else 'temp_rate'
            rates = df[rate_col].values
        elif has_net:
            rates = df['net_basal'].values
        else:
            print(f"  {name}: no delivery data")
            continue

        # Get profile basal rate
        basal_schedule = df.attrs.get('basal_schedule', [])
        if not basal_schedule:
            print(f"  {name}: no basal schedule")
            continue

        # Compute overnight delivery vs scheduled
        nights_analyzed = 0
        total_delivery = []
        total_scheduled = []
        zero_delivery_steps = 0
        total_steps = 0
        adjustments = []  # ratio of actual to scheduled

        for d in range(n_days):
            start = d * STEPS_PER_DAY  # midnight
            end = start + 6 * STEPS_PER_HOUR  # 6am

            if end >= len(rates):
                continue

            night_rates = rates[start:end]
            night_g = g[start:end]

            valid_rates = ~np.isnan(night_rates)
            if valid_rates.sum() < len(night_rates) * 0.5:
                continue

            nights_analyzed += 1

            for t in range(len(night_rates)):
                if np.isnan(night_rates[t]):
                    continue
                hour = t / STEPS_PER_HOUR
                scheduled = get_profile_value(basal_schedule, hour)
                if scheduled is None or scheduled == 0:
                    continue

                total_steps += 1
                actual = night_rates[t]
                total_delivery.append(actual)
                total_scheduled.append(scheduled)

                if actual < 0.01:
                    zero_delivery_steps += 1

                ratio = actual / scheduled
                adjustments.append(ratio)

        if not adjustments:
            print(f"  {name}: insufficient delivery data")
            continue

        adj_arr = np.array(adjustments)
        mean_ratio = float(np.mean(adj_arr))
        zero_pct = zero_delivery_steps / total_steps * 100 if total_steps > 0 else 0

        # Categorize delivery patterns
        suspended_pct = float(np.mean(adj_arr < 0.1)) * 100
        reduced_pct = float(np.mean((adj_arr >= 0.1) & (adj_arr < 0.8))) * 100
        normal_pct = float(np.mean((adj_arr >= 0.8) & (adj_arr <= 1.2))) * 100
        increased_pct = float(np.mean(adj_arr > 1.2)) * 100

        all_results[name] = {
            'n_nights': nights_analyzed,
            'mean_delivery_ratio': mean_ratio,
            'zero_delivery_pct': zero_pct,
            'suspended_pct': suspended_pct,
            'reduced_pct': reduced_pct,
            'normal_pct': normal_pct,
            'increased_pct': increased_pct,
            'mean_scheduled': float(np.mean(total_scheduled)),
            'mean_actual': float(np.mean(total_delivery)),
            'total_steps': total_steps
        }

        print(f"  {name}: {nights_analyzed} nights, delivery ratio={mean_ratio:.2f}×, "
              f"suspended={suspended_pct:.0f}% reduced={reduced_pct:.0f}% "
              f"normal={normal_pct:.0f}% increased={increased_pct:.0f}%")

    with open(f'{EXP_DIR}/exp-2162_aid_delivery.json', 'w') as f:
        json.dump(all_results, f, indent=2, cls=NumpyEncoder)

    if MAKE_FIGS and all_results:
        fig, axes = plt.subplots(1, 3, figsize=(16, 5))

        patient_names = sorted(all_results.keys())
        x = np.arange(len(patient_names))

        # Panel 1: Delivery ratio
        ratios = [all_results[pn]['mean_delivery_ratio'] for pn in patient_names]
        colors_r = ['red' if r < 0.5 else 'orange' if r < 0.8 else 'green'
                     if r <= 1.2 else 'blue' for r in ratios]
        axes[0].bar(patient_names, ratios, color=colors_r, alpha=0.7)
        axes[0].axhline(y=1, color='black', linewidth=0.5, linestyle='--')
        axes[0].set_ylabel('Mean Delivery / Scheduled')
        axes[0].set_title('Overnight Delivery Ratio')
        axes[0].tick_params(axis='x', labelsize=8)
        axes[0].grid(True, alpha=0.3, axis='y')

        # Panel 2: Delivery breakdown
        cats = ['suspended_pct', 'reduced_pct', 'normal_pct', 'increased_pct']
        cat_labels = ['Suspended', 'Reduced', 'Normal', 'Increased']
        cat_colors = ['red', 'orange', 'green', 'blue']
        bottom = np.zeros(len(patient_names))
        for ci, cat in enumerate(cats):
            vals = [all_results[pn][cat] for pn in patient_names]
            axes[1].bar(patient_names, vals, bottom=bottom, label=cat_labels[ci],
                        color=cat_colors[ci], alpha=0.7)
            bottom += vals
        axes[1].set_ylabel('% of Overnight Steps')
        axes[1].set_title('AID Delivery Categories')
        axes[1].legend(fontsize=8)
        axes[1].tick_params(axis='x', labelsize=8)

        # Panel 3: Scheduled vs actual
        scheduled = [all_results[pn]['mean_scheduled'] for pn in patient_names]
        actual = [all_results[pn]['mean_actual'] for pn in patient_names]
        w = 0.3
        axes[2].bar(x - w/2, scheduled, w, label='Scheduled', color='gray', alpha=0.7)
        axes[2].bar(x + w/2, actual, w, label='Actual', color='steelblue', alpha=0.7)
        axes[2].set_xticks(x)
        axes[2].set_xticklabels(patient_names, fontsize=8)
        axes[2].set_ylabel('Basal Rate (U/hr)')
        axes[2].set_title('Scheduled vs Actual Basal')
        axes[2].legend(fontsize=8)
        axes[2].grid(True, alpha=0.3, axis='y')

        plt.tight_layout()
        plt.savefig(f'{FIG_DIR}/night-fig02-delivery.png', dpi=150)
        plt.close()
        print("  → Saved night-fig02-delivery.png")

    return all_results


# ── EXP-2163: Dawn Phenomenon Quantification ────────────────────────
def exp_2163_dawn_phenomenon():
    """Quantify the 4am-8am glucose rise per patient."""
    print("\n═══ EXP-2163: Dawn Phenomenon Quantification ═══")

    all_results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        n_days = len(g) // STEPS_PER_DAY

        dawn_rises = []
        dawn_nadirs = []

        for d in range(n_days):
            base = d * STEPS_PER_DAY
            # 4am = 4 * 12 = 48 steps from midnight
            # 8am = 8 * 12 = 96 steps
            start_4am = base + 4 * STEPS_PER_HOUR
            end_8am = base + 8 * STEPS_PER_HOUR

            if end_8am >= len(g):
                continue

            dawn_g = g[start_4am:end_8am]
            valid = ~np.isnan(dawn_g)
            if valid.sum() < len(dawn_g) * 0.5:
                continue

            dawn_clean = dawn_g[valid]
            nadir = float(np.min(dawn_clean))
            final = float(dawn_clean[-1])
            rise = final - nadir

            dawn_rises.append(rise)
            dawn_nadirs.append(nadir)

        if len(dawn_rises) < 10:
            continue

        rise_arr = np.array(dawn_rises)
        has_dawn = float(np.mean(rise_arr > 10))
        significant = float(np.mean(rise_arr > 20))

        all_results[name] = {
            'n_nights': len(dawn_rises),
            'mean_rise': float(np.mean(rise_arr)),
            'median_rise': float(np.median(rise_arr)),
            'std_rise': float(np.std(rise_arr)),
            'dawn_frequency': has_dawn,
            'significant_dawn_frequency': significant,
            'mean_nadir': float(np.mean(dawn_nadirs)),
            'mean_nadir_to_8am': float(np.mean(rise_arr))
        }

        print(f"  {name}: mean rise={np.mean(rise_arr):+.1f} mg/dL, "
              f"dawn_freq={has_dawn:.0%}, "
              f"significant(>20)={significant:.0%}, "
              f"mean_nadir={np.mean(dawn_nadirs):.0f} ({len(dawn_rises)} nights)")

    with open(f'{EXP_DIR}/exp-2163_dawn.json', 'w') as f:
        json.dump(all_results, f, indent=2, cls=NumpyEncoder)

    if MAKE_FIGS and all_results:
        fig, axes = plt.subplots(1, 3, figsize=(16, 5))

        patient_names = sorted(all_results.keys())

        # Panel 1: Mean dawn rise
        rises = [all_results[pn]['mean_rise'] for pn in patient_names]
        colors_r = ['red' if r > 20 else 'orange' if r > 10 else 'green' for r in rises]
        axes[0].bar(patient_names, rises, color=colors_r, alpha=0.7)
        axes[0].axhline(y=10, color='orange', linestyle='--', alpha=0.3, label='>10 threshold')
        axes[0].axhline(y=20, color='red', linestyle='--', alpha=0.3, label='>20 significant')
        axes[0].set_ylabel('Mean 4am→8am Rise (mg/dL)')
        axes[0].set_title('Dawn Phenomenon Magnitude')
        axes[0].legend(fontsize=8)
        axes[0].tick_params(axis='x', labelsize=8)
        axes[0].grid(True, alpha=0.3, axis='y')

        # Panel 2: Dawn frequency
        freq = [all_results[pn]['dawn_frequency'] * 100 for pn in patient_names]
        sig_freq = [all_results[pn]['significant_dawn_frequency'] * 100 for pn in patient_names]
        x = np.arange(len(patient_names))
        axes[1].bar(x - 0.15, freq, 0.3, label='>10 mg/dL', color='orange', alpha=0.7)
        axes[1].bar(x + 0.15, sig_freq, 0.3, label='>20 mg/dL', color='red', alpha=0.7)
        axes[1].set_xticks(x)
        axes[1].set_xticklabels(patient_names, fontsize=8)
        axes[1].set_ylabel('% of Nights')
        axes[1].set_title('Dawn Phenomenon Frequency')
        axes[1].legend(fontsize=8)
        axes[1].grid(True, alpha=0.3, axis='y')

        # Panel 3: Nadir before dawn
        nadirs = [all_results[pn]['mean_nadir'] for pn in patient_names]
        axes[2].bar(patient_names, nadirs, color='steelblue', alpha=0.7)
        axes[2].axhline(y=70, color='red', linestyle='--', alpha=0.3, label='Hypo')
        axes[2].set_ylabel('Mean 4am-8am Nadir (mg/dL)')
        axes[2].set_title('Pre-Dawn Nadir')
        axes[2].legend(fontsize=8)
        axes[2].tick_params(axis='x', labelsize=8)
        axes[2].grid(True, alpha=0.3, axis='y')

        plt.tight_layout()
        plt.savefig(f'{FIG_DIR}/night-fig03-dawn.png', dpi=150)
        plt.close()
        print("  → Saved night-fig03-dawn.png")

    return all_results


# ── EXP-2164: Alternative Basal Assessment ──────────────────────────
def exp_2164_alt_basal():
    """Use AID delivery as signal for basal adequacy (not fasting)."""
    print("\n═══ EXP-2164: Alternative Basal Assessment ═══")

    all_results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        n_days = len(g) // STEPS_PER_DAY

        has_rate = 'enacted_rate' in df.columns or 'temp_rate' in df.columns
        has_net = 'net_basal' in df.columns

        if has_rate:
            rate_col = 'enacted_rate' if 'enacted_rate' in df.columns else 'temp_rate'
            rates = df[rate_col].values
        elif has_net:
            rates = df['net_basal'].values
        else:
            continue

        basal_schedule = df.attrs.get('basal_schedule', [])
        if not basal_schedule:
            continue

        # Hourly analysis: for each hour, compare mean AID delivery to scheduled
        hourly_ratios = {}
        for hour in range(24):
            hour_rates = []
            hour_scheduled = []
            scheduled = get_profile_value(basal_schedule, hour)
            if scheduled is None or scheduled == 0:
                continue

            for d in range(n_days):
                start = d * STEPS_PER_DAY + hour * STEPS_PER_HOUR
                end = start + STEPS_PER_HOUR
                if end >= len(rates):
                    continue

                hr_rates = rates[start:end]
                valid = ~np.isnan(hr_rates)
                if valid.sum() >= STEPS_PER_HOUR // 2:
                    hour_rates.extend(hr_rates[valid].tolist())
                    hour_scheduled.extend([scheduled] * valid.sum())

            if hour_rates:
                mean_actual = float(np.mean(hour_rates))
                ratio = mean_actual / scheduled
                hourly_ratios[hour] = {
                    'scheduled': scheduled,
                    'mean_actual': mean_actual,
                    'ratio': ratio,
                    'n_samples': len(hour_rates)
                }

        if not hourly_ratios:
            continue

        # Identify hours that need adjustment
        under_hours = [h for h, r in hourly_ratios.items() if r['ratio'] > 1.3]
        over_hours = [h for h, r in hourly_ratios.items() if r['ratio'] < 0.7]

        # Overall assessment
        mean_ratio = float(np.mean([r['ratio'] for r in hourly_ratios.values()]))

        all_results[name] = {
            'hourly': hourly_ratios,
            'mean_ratio': mean_ratio,
            'under_basaled_hours': under_hours,
            'over_basaled_hours': over_hours,
            'needs_adjustment': len(under_hours) > 3 or len(over_hours) > 3
        }

        print(f"  {name}: mean_ratio={mean_ratio:.2f}, "
              f"under-basaled hours={under_hours}, "
              f"over-basaled hours={over_hours}")

    with open(f'{EXP_DIR}/exp-2164_alt_basal.json', 'w') as f:
        json.dump(all_results, f, indent=2, cls=NumpyEncoder)

    if MAKE_FIGS and all_results:
        patient_names = sorted(all_results.keys())
        n = len(patient_names)
        n_cols = 3
        n_rows = (n + n_cols - 1) // n_cols

        fig, axes = plt.subplots(n_rows, n_cols, figsize=(16, 4 * n_rows))
        axes_flat = axes.flatten() if n_rows > 1 else (axes if n > 1 else [axes])

        for pi, pn in enumerate(patient_names):
            ax = axes_flat[pi]
            hourly = all_results[pn]['hourly']
            hours = sorted([int(h) for h in hourly.keys()])
            ratios = [hourly[h]['ratio'] for h in hours]

            ax.bar(hours, ratios, color=['red' if r > 1.3 else 'blue' if r < 0.7
                                         else 'green' for r in ratios], alpha=0.7)
            ax.axhline(y=1, color='black', linewidth=0.5, linestyle='--')
            ax.axhline(y=1.3, color='red', linewidth=0.5, linestyle='--', alpha=0.3)
            ax.axhline(y=0.7, color='blue', linewidth=0.5, linestyle='--', alpha=0.3)
            ax.set_title(f"Patient {pn} (ratio={all_results[pn]['mean_ratio']:.2f})",
                         fontsize=10)
            ax.set_xlabel('Hour', fontsize=8)
            ax.set_ylabel('Actual/Scheduled', fontsize=8)
            ax.set_xticks(range(0, 24, 3))
            ax.grid(True, alpha=0.3)

        for pi in range(n, len(axes_flat)):
            axes_flat[pi].set_visible(False)

        plt.suptitle('Hourly Basal: AID Delivery vs Scheduled', fontsize=14, y=1.01)
        plt.tight_layout()
        plt.savefig(f'{FIG_DIR}/night-fig04-altbasal.png', dpi=150, bbox_inches='tight')
        plt.close()
        print("  → Saved night-fig04-altbasal.png")

    return all_results


# ── EXP-2165: Overnight Hypo Analysis ───────────────────────────────
def exp_2165_overnight_hypo():
    """When, why, and how deep are overnight hypos?"""
    print("\n═══ EXP-2165: Overnight Hypo Analysis ═══")

    all_results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(len(g))
        carbs = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(g))
        iob = df['iob'].values if 'iob' in df.columns else np.zeros(len(g))
        n_days = len(g) // STEPS_PER_DAY

        night_hypos = []

        for d in range(n_days):
            start = d * STEPS_PER_DAY  # midnight
            end = start + 7 * STEPS_PER_HOUR  # 7am

            if end >= len(g):
                continue

            for t in range(start + 1, end):
                if np.isnan(g[t]) or np.isnan(g[t-1]):
                    continue
                if g[t] < 70 and g[t-1] >= 70:
                    hour = ((t - start) / STEPS_PER_HOUR)
                    nadir = float(np.nanmin(g[t:min(t+12, len(g))]))

                    # Context: was there a late dinner bolus?
                    evening_start = max(0, start - 6 * STEPS_PER_HOUR)  # 6pm
                    late_bolus = float(np.nansum(bolus[evening_start:start]))
                    late_carbs = float(np.nansum(carbs[evening_start:start]))
                    current_iob = float(iob[t]) if not np.isnan(iob[t]) else 0

                    night_hypos.append({
                        'hour': float(hour),
                        'nadir': nadir,
                        'is_severe': nadir < 54,
                        'late_bolus': late_bolus > 0.5,
                        'late_carbs': late_carbs > 5,
                        'iob': current_iob
                    })

        if not night_hypos:
            all_results[name] = {'n_hypos': 0, 'rate_per_week': 0}
            print(f"  {name}: 0 overnight hypos")
            continue

        n_hypos = len(night_hypos)
        rate = n_hypos / (n_days / 7)
        severe = sum(1 for h in night_hypos if h['is_severe'])
        late_dinner = sum(1 for h in night_hypos if h['late_bolus'])
        hours = [h['hour'] for h in night_hypos]

        # Peak hour
        hour_hist = np.histogram(hours, bins=np.arange(0, 8, 1))[0]
        peak_hour = int(np.argmax(hour_hist))

        all_results[name] = {
            'n_hypos': n_hypos,
            'rate_per_week': float(rate),
            'severe_count': severe,
            'severe_pct': severe / n_hypos * 100,
            'late_dinner_pct': late_dinner / n_hypos * 100,
            'peak_hour': peak_hour,
            'mean_nadir': float(np.mean([h['nadir'] for h in night_hypos])),
            'mean_iob': float(np.mean([h['iob'] for h in night_hypos])),
            'hour_distribution': hour_hist.tolist()
        }

        print(f"  {name}: {n_hypos} night hypos ({rate:.1f}/wk), "
              f"severe={severe} ({severe*100//n_hypos}%), "
              f"peak hour={peak_hour}:00, "
              f"late_dinner={late_dinner*100//n_hypos}%")

    with open(f'{EXP_DIR}/exp-2165_overnight_hypo.json', 'w') as f:
        json.dump(all_results, f, indent=2, cls=NumpyEncoder)

    if MAKE_FIGS and all_results:
        fig, axes = plt.subplots(1, 3, figsize=(16, 5))

        patient_names = sorted(all_results.keys())

        # Panel 1: Night hypo frequency
        rates = [all_results[pn]['rate_per_week'] for pn in patient_names]
        axes[0].bar(patient_names, rates, color='coral', alpha=0.7)
        axes[0].set_ylabel('Overnight Hypos per Week')
        axes[0].set_title('Overnight Hypo Frequency')
        axes[0].tick_params(axis='x', labelsize=8)
        axes[0].grid(True, alpha=0.3, axis='y')

        # Panel 2: Hourly distribution (population)
        pop_hours = np.zeros(7)
        for pn in patient_names:
            h = all_results[pn].get('hour_distribution', [0]*7)
            pop_hours[:len(h)] += h
        axes[1].bar(range(7), pop_hours, color='steelblue', alpha=0.7)
        axes[1].set_xlabel('Hour (from midnight)')
        axes[1].set_ylabel('Number of Hypos')
        axes[1].set_title('Overnight Hypo Timing (Population)')
        axes[1].set_xticks(range(7))
        axes[1].set_xticklabels(['0am', '1am', '2am', '3am', '4am', '5am', '6am'])
        axes[1].grid(True, alpha=0.3, axis='y')

        # Panel 3: Severe percentage
        severe_pcts = [all_results[pn].get('severe_pct', 0) for pn in patient_names]
        colors_s = ['red' if s > 30 else 'orange' if s > 10 else 'green' for s in severe_pcts]
        axes[2].bar(patient_names, severe_pcts, color=colors_s, alpha=0.7)
        axes[2].set_ylabel('% Severe (<54 mg/dL)')
        axes[2].set_title('Overnight Hypo Severity')
        axes[2].tick_params(axis='x', labelsize=8)
        axes[2].grid(True, alpha=0.3, axis='y')

        plt.tight_layout()
        plt.savefig(f'{FIG_DIR}/night-fig05-hypo.png', dpi=150)
        plt.close()
        print("  → Saved night-fig05-hypo.png")

    return all_results


# ── EXP-2166: Sleep Quality Proxy ───────────────────────────────────
def exp_2166_sleep_proxy():
    """Overnight glucose stability as a proxy for sleep quality."""
    print("\n═══ EXP-2166: Sleep Quality Proxy ═══")

    all_results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        n_days = len(g) // STEPS_PER_DAY

        night_stabilities = []
        night_tirs = []

        for d in range(n_days):
            start = d * STEPS_PER_DAY + 1 * STEPS_PER_HOUR  # 1am (skip settling)
            end = d * STEPS_PER_DAY + 6 * STEPS_PER_HOUR    # 6am

            if end >= len(g):
                continue

            night_g = g[start:end]
            valid = ~np.isnan(night_g)
            if valid.sum() < len(night_g) * 0.5:
                continue

            clean = night_g[valid]
            cv = float(np.std(clean) / np.mean(clean)) * 100 if np.mean(clean) > 0 else 100
            tir = float(np.mean((clean >= 70) & (clean <= 180))) * 100

            night_stabilities.append(cv)
            night_tirs.append(tir)

        if len(night_stabilities) < 10:
            continue

        stab_arr = np.array(night_stabilities)
        tir_arr = np.array(night_tirs)

        good_nights = float(np.mean(stab_arr < 10))  # CV < 10%
        poor_nights = float(np.mean(stab_arr > 20))   # CV > 20%

        all_results[name] = {
            'n_nights': len(night_stabilities),
            'mean_cv': float(np.mean(stab_arr)),
            'median_cv': float(np.median(stab_arr)),
            'mean_tir': float(np.mean(tir_arr)),
            'good_night_pct': good_nights * 100,
            'poor_night_pct': poor_nights * 100,
            'cv_std': float(np.std(stab_arr))
        }

        print(f"  {name}: mean_CV={np.mean(stab_arr):.1f}%, "
              f"good(<10%)={good_nights:.0%}, "
              f"poor(>20%)={poor_nights:.0%}, "
              f"overnight TIR={np.mean(tir_arr):.0f}%")

    with open(f'{EXP_DIR}/exp-2166_sleep_proxy.json', 'w') as f:
        json.dump(all_results, f, indent=2, cls=NumpyEncoder)

    if MAKE_FIGS and all_results:
        fig, axes = plt.subplots(1, 3, figsize=(16, 5))

        patient_names = sorted(all_results.keys())

        # Panel 1: Mean overnight CV
        cvs = [all_results[pn]['mean_cv'] for pn in patient_names]
        colors_c = ['green' if c < 10 else 'orange' if c < 20 else 'red' for c in cvs]
        axes[0].bar(patient_names, cvs, color=colors_c, alpha=0.7)
        axes[0].axhline(y=10, color='green', linestyle='--', alpha=0.3, label='Good (<10%)')
        axes[0].axhline(y=20, color='red', linestyle='--', alpha=0.3, label='Poor (>20%)')
        axes[0].set_ylabel('Mean Overnight CV (%)')
        axes[0].set_title('Overnight Glucose Stability')
        axes[0].legend(fontsize=8)
        axes[0].tick_params(axis='x', labelsize=8)
        axes[0].grid(True, alpha=0.3, axis='y')

        # Panel 2: Good vs poor nights
        good = [all_results[pn]['good_night_pct'] for pn in patient_names]
        poor = [all_results[pn]['poor_night_pct'] for pn in patient_names]
        x = np.arange(len(patient_names))
        axes[1].bar(x - 0.15, good, 0.3, label='Good nights', color='green', alpha=0.7)
        axes[1].bar(x + 0.15, poor, 0.3, label='Poor nights', color='red', alpha=0.7)
        axes[1].set_xticks(x)
        axes[1].set_xticklabels(patient_names, fontsize=8)
        axes[1].set_ylabel('% of Nights')
        axes[1].set_title('Night Quality Distribution')
        axes[1].legend(fontsize=8)
        axes[1].grid(True, alpha=0.3, axis='y')

        # Panel 3: Overnight TIR
        tirs = [all_results[pn]['mean_tir'] for pn in patient_names]
        colors_t = ['green' if t > 80 else 'orange' if t > 60 else 'red' for t in tirs]
        axes[2].bar(patient_names, tirs, color=colors_t, alpha=0.7)
        axes[2].axhline(y=70, color='green', linestyle='--', alpha=0.3)
        axes[2].set_ylabel('Mean Overnight TIR (%)')
        axes[2].set_title('Overnight Time-in-Range')
        axes[2].tick_params(axis='x', labelsize=8)
        axes[2].grid(True, alpha=0.3, axis='y')

        plt.tight_layout()
        plt.savefig(f'{FIG_DIR}/night-fig06-sleep.png', dpi=150)
        plt.close()
        print("  → Saved night-fig06-sleep.png")

    return all_results


# ── EXP-2167: Circadian Glucose Profile ─────────────────────────────
def exp_2167_circadian_profile():
    """24-hour mean glucose curve per patient."""
    print("\n═══ EXP-2167: Circadian Glucose Profile ═══")

    all_results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        n_days = len(g) // STEPS_PER_DAY

        # Compute hourly mean glucose
        hourly_means = np.zeros(24)
        hourly_stds = np.zeros(24)
        hourly_counts = np.zeros(24)

        for d in range(n_days):
            for h in range(24):
                start = d * STEPS_PER_DAY + h * STEPS_PER_HOUR
                end = start + STEPS_PER_HOUR
                if end >= len(g):
                    continue
                hr_g = g[start:end]
                valid = hr_g[~np.isnan(hr_g)]
                if len(valid) > 0:
                    hourly_means[h] += np.mean(valid)
                    hourly_counts[h] += 1

        # Average
        for h in range(24):
            if hourly_counts[h] > 0:
                hourly_means[h] /= hourly_counts[h]

        # Compute hourly std (across days)
        for h in range(24):
            day_means = []
            for d in range(n_days):
                start = d * STEPS_PER_DAY + h * STEPS_PER_HOUR
                end = start + STEPS_PER_HOUR
                if end >= len(g):
                    continue
                hr_g = g[start:end]
                valid = hr_g[~np.isnan(hr_g)]
                if len(valid) > 0:
                    day_means.append(float(np.mean(valid)))
            if day_means:
                hourly_stds[h] = float(np.std(day_means))

        # Find circadian features
        peak_hour = int(np.argmax(hourly_means))
        nadir_hour = int(np.argmin(hourly_means[hourly_means > 0]))
        amplitude = float(np.max(hourly_means) - np.min(hourly_means[hourly_means > 0]))

        all_results[name] = {
            'hourly_means': hourly_means.tolist(),
            'hourly_stds': hourly_stds.tolist(),
            'peak_hour': peak_hour,
            'nadir_hour': nadir_hour,
            'amplitude': amplitude,
            'mean_24h': float(np.mean(hourly_means[hourly_means > 0]))
        }

        print(f"  {name}: peak={peak_hour}:00 ({hourly_means[peak_hour]:.0f}), "
              f"nadir={nadir_hour}:00 ({hourly_means[nadir_hour]:.0f}), "
              f"amplitude={amplitude:.0f} mg/dL")

    with open(f'{EXP_DIR}/exp-2167_circadian.json', 'w') as f:
        json.dump(all_results, f, indent=2, cls=NumpyEncoder)

    if MAKE_FIGS and all_results:
        fig, axes = plt.subplots(1, 3, figsize=(16, 5))

        patient_names = sorted(all_results.keys())
        hours = list(range(24))

        # Panel 1: All circadian curves
        for pn in patient_names:
            curve = all_results[pn]['hourly_means']
            axes[0].plot(hours, curve, '-', label=pn, alpha=0.7)
        axes[0].axhline(y=70, color='red', linestyle='--', alpha=0.2)
        axes[0].axhline(y=180, color='red', linestyle='--', alpha=0.2)
        axes[0].fill_between(hours, 70, 180, alpha=0.05, color='green')
        axes[0].set_xlabel('Hour of Day')
        axes[0].set_ylabel('Mean Glucose (mg/dL)')
        axes[0].set_title('Circadian Glucose Profile')
        axes[0].legend(fontsize=7, ncol=2)
        axes[0].set_xticks(range(0, 24, 3))
        axes[0].grid(True, alpha=0.3)

        # Panel 2: Circadian amplitude
        amplitudes = [all_results[pn]['amplitude'] for pn in patient_names]
        axes[1].bar(patient_names, amplitudes, color='steelblue', alpha=0.7)
        axes[1].set_ylabel('Circadian Amplitude (mg/dL)')
        axes[1].set_title('Daily Glucose Swing')
        axes[1].tick_params(axis='x', labelsize=8)
        axes[1].grid(True, alpha=0.3, axis='y')

        # Panel 3: Peak and nadir hours
        peaks = [all_results[pn]['peak_hour'] for pn in patient_names]
        nadirs = [all_results[pn]['nadir_hour'] for pn in patient_names]
        x = np.arange(len(patient_names))
        axes[2].scatter(x, peaks, s=100, c='red', marker='^', label='Peak', zorder=3)
        axes[2].scatter(x, nadirs, s=100, c='blue', marker='v', label='Nadir', zorder=3)
        axes[2].set_xticks(x)
        axes[2].set_xticklabels(patient_names, fontsize=8)
        axes[2].set_ylabel('Hour of Day')
        axes[2].set_title('Peak and Nadir Timing')
        axes[2].legend(fontsize=8)
        axes[2].set_yticks(range(0, 24, 3))
        axes[2].grid(True, alpha=0.3)

        plt.tight_layout()
        plt.savefig(f'{FIG_DIR}/night-fig07-circadian.png', dpi=150)
        plt.close()
        print("  → Saved night-fig07-circadian.png")

    return all_results


# ── EXP-2168: Integrated Overnight Recommendations ─────────────────
def exp_2168_overnight_recommendations():
    """Per-patient overnight strategy recommendations."""
    print("\n═══ EXP-2168: Integrated Overnight Recommendations ═══")

    all_results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        n_days = len(g) // STEPS_PER_DAY

        # Compute overnight metrics
        overnight_tir = []
        overnight_tbr = []
        overnight_tar = []
        overnight_hypos = 0

        for d in range(n_days):
            start = d * STEPS_PER_DAY
            end = start + 7 * STEPS_PER_HOUR
            if end >= len(g):
                continue

            night_g = g[start:end]
            valid = night_g[~np.isnan(night_g)]
            if len(valid) < len(night_g) * 0.5:
                continue

            tir = float(np.mean((valid >= 70) & (valid <= 180)))
            tbr = float(np.mean(valid < 70))
            tar = float(np.mean(valid > 180))
            overnight_tir.append(tir)
            overnight_tbr.append(tbr)
            overnight_tar.append(tar)

            # Count hypo entries
            for t in range(1, len(night_g)):
                if not np.isnan(night_g[t]) and not np.isnan(night_g[t-1]):
                    if night_g[t] < 70 and night_g[t-1] >= 70:
                        overnight_hypos += 1

        if not overnight_tir:
            continue

        mean_tir = float(np.mean(overnight_tir)) * 100
        mean_tbr = float(np.mean(overnight_tbr)) * 100
        mean_tar = float(np.mean(overnight_tar)) * 100
        hypos_per_week = overnight_hypos / (n_days / 7)

        # Determine primary issue
        issues = []
        if mean_tbr > 5:
            issues.append('HIGH_TBR')
        if mean_tar > 30:
            issues.append('HIGH_TAR')
        if hypos_per_week > 3:
            issues.append('FREQUENT_HYPO')
        if mean_tir < 70:
            issues.append('LOW_TIR')

        # Recommendations
        recommendations = []
        if 'HIGH_TBR' in issues or 'FREQUENT_HYPO' in issues:
            recommendations.append('REDUCE_OVERNIGHT_BASAL')
            recommendations.append('CHECK_DINNER_BOLUS_TIMING')
        if 'HIGH_TAR' in issues:
            recommendations.append('INCREASE_OVERNIGHT_BASAL')
            recommendations.append('CHECK_LATE_SNACKING')
        if not issues:
            recommendations.append('MAINTAIN_CURRENT_SETTINGS')

        priority = 'SAFETY' if 'HIGH_TBR' in issues else 'OPTIMIZE' if issues else 'MAINTAIN'

        all_results[name] = {
            'overnight_tir': mean_tir,
            'overnight_tbr': mean_tbr,
            'overnight_tar': mean_tar,
            'hypos_per_week': hypos_per_week,
            'issues': issues,
            'recommendations': recommendations,
            'priority': priority,
            'n_nights': len(overnight_tir)
        }

        issue_str = ', '.join(issues) if issues else 'NONE'
        print(f"  {name}: [{priority}] TIR={mean_tir:.0f}% TBR={mean_tbr:.1f}% "
              f"TAR={mean_tar:.0f}% hypos={hypos_per_week:.1f}/wk issues={issue_str}")

    with open(f'{EXP_DIR}/exp-2168_overnight_recs.json', 'w') as f:
        json.dump(all_results, f, indent=2, cls=NumpyEncoder)

    if MAKE_FIGS and all_results:
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))

        patient_names = sorted(all_results.keys())
        x = np.arange(len(patient_names))

        # Panel 1: Overnight TIR/TBR/TAR
        tirs = [all_results[pn]['overnight_tir'] for pn in patient_names]
        tbrs = [all_results[pn]['overnight_tbr'] for pn in patient_names]
        tars = [all_results[pn]['overnight_tar'] for pn in patient_names]
        w = 0.25
        axes[0, 0].bar(x - w, tirs, w, label='TIR', color='green', alpha=0.7)
        axes[0, 0].bar(x, tbrs, w, label='TBR', color='red', alpha=0.7)
        axes[0, 0].bar(x + w, tars, w, label='TAR', color='orange', alpha=0.7)
        axes[0, 0].set_xticks(x)
        axes[0, 0].set_xticklabels(patient_names, fontsize=8)
        axes[0, 0].set_ylabel('Percentage')
        axes[0, 0].set_title('Overnight Glucose Distribution')
        axes[0, 0].legend(fontsize=8)
        axes[0, 0].grid(True, alpha=0.3, axis='y')

        # Panel 2: Priority distribution
        priorities = {'SAFETY': 0, 'OPTIMIZE': 0, 'MAINTAIN': 0}
        for pn in patient_names:
            priorities[all_results[pn]['priority']] += 1
        colors_pr = {'SAFETY': 'red', 'OPTIMIZE': 'orange', 'MAINTAIN': 'green'}
        axes[0, 1].pie(priorities.values(), labels=priorities.keys(),
                       colors=[colors_pr[k] for k in priorities.keys()],
                       autopct='%1.0f%%', startangle=90)
        axes[0, 1].set_title('Overnight Priority Distribution')

        # Panel 3: Hypos per week
        hypos = [all_results[pn]['hypos_per_week'] for pn in patient_names]
        colors_h = ['red' if h > 3 else 'orange' if h > 1 else 'green' for h in hypos]
        axes[1, 0].bar(patient_names, hypos, color=colors_h, alpha=0.7)
        axes[1, 0].axhline(y=3, color='red', linestyle='--', alpha=0.3, label='>3/wk threshold')
        axes[1, 0].set_ylabel('Overnight Hypos per Week')
        axes[1, 0].set_title('Overnight Hypo Frequency')
        axes[1, 0].legend(fontsize=8)
        axes[1, 0].tick_params(axis='x', labelsize=8)
        axes[1, 0].grid(True, alpha=0.3, axis='y')

        # Panel 4: Issue frequency
        all_issues = {}
        for pn in patient_names:
            for issue in all_results[pn]['issues']:
                all_issues[issue] = all_issues.get(issue, 0) + 1
        if all_issues:
            axes[1, 1].barh(list(all_issues.keys()), list(all_issues.values()),
                            color='coral', alpha=0.7)
            axes[1, 1].set_xlabel('Number of Patients')
            axes[1, 1].set_title('Issue Frequency')
        else:
            axes[1, 1].text(0.5, 0.5, 'No issues detected', ha='center', va='center')

        plt.tight_layout()
        plt.savefig(f'{FIG_DIR}/night-fig08-recommendations.png', dpi=150)
        plt.close()
        print("  → Saved night-fig08-recommendations.png")

    return all_results


# ══════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    print("=" * 60)
    print("EXP-2161–2168: Overnight Dynamics & AID Behavior Analysis")
    print("=" * 60)

    r1 = exp_2161_overnight_patterns()
    r2 = exp_2162_aid_delivery()
    r3 = exp_2163_dawn_phenomenon()
    r4 = exp_2164_alt_basal()
    r5 = exp_2165_overnight_hypo()
    r6 = exp_2166_sleep_proxy()
    r7 = exp_2167_circadian_profile()
    r8 = exp_2168_overnight_recommendations()

    print("\n" + "=" * 60)
    n_complete = sum(1 for r in [r1, r2, r3, r4, r5, r6, r7, r8] if r)
    print(f"Results: {n_complete}/8 experiments completed")
    print(f"Figures saved to {FIG_DIR}/night-fig01–08")
    print("=" * 60)
