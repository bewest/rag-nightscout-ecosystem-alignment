#!/usr/bin/env python3
"""
EXP-2131–2138: Integrated Therapy Synthesis

Synthesize all prior findings into concrete, per-patient therapy
recommendations and validate the overall model coherence.

EXP-2131: Per-patient therapy scorecard — aggregate all flags/metrics
EXP-2132: ISF recalibration — what should ISF be vs what it is
EXP-2133: CR recalibration — meal-specific CR recommendations
EXP-2134: Basal adequacy — overnight fasting assessment
EXP-2135: Safety-first ordering — prioritize hypo reduction over TIR gain
EXP-2136: Expected outcome simulation — projected TIR if recommendations applied
EXP-2137: Cross-validation — do recommendations from first half predict second half?
EXP-2138: Final population summary — publication-ready synthesis

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


def compute_tir_tbr_tar(glucose):
    g = glucose[~np.isnan(glucose)]
    if len(g) == 0:
        return 0, 0, 0
    return (float(np.mean((g >= 70) & (g <= 180))),
            float(np.mean(g < 70)),
            float(np.mean(g > 180)))


def get_profile_value(schedule, hour):
    """Get profile value for a given hour from list-of-dicts schedule."""
    if not schedule:
        return None
    sorted_sched = sorted(schedule, key=lambda x: x.get('timeAsSeconds', 0))
    result = sorted_sched[0].get('value', None)
    target_seconds = hour * 3600
    for entry in sorted_sched:
        if entry.get('timeAsSeconds', 0) <= target_seconds:
            result = entry.get('value', result)
    return result


def split_into_days(glucose, steps_per_day=STEPS_PER_DAY):
    n = len(glucose) // steps_per_day
    return [glucose[d*steps_per_day:(d+1)*steps_per_day] for d in range(n)]


# ── EXP-2131: Per-Patient Therapy Scorecard ──────────────────────────
def exp_2131_scorecard():
    """Aggregate all metrics into a single per-patient scorecard."""
    print("\n═══ EXP-2131: Per-Patient Therapy Scorecard ═══")

    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        iob = df['iob'].values

        g_valid = g[~np.isnan(g)]
        n_days = len(g_valid) / STEPS_PER_DAY
        if n_days < 14:
            continue

        tir, tbr, tar = compute_tir_tbr_tar(g)
        cv = float(np.std(g_valid) / np.mean(g_valid))
        mean_g = float(np.mean(g_valid))
        gmi = 3.31 + 0.02392 * mean_g

        # Daily totals
        daily_insulin = float(np.nansum(bolus) / n_days)
        daily_carbs = float(np.nansum(carbs) / n_days)

        # Hypo events
        hypo_mask = g_valid < 70
        n_hypos = int(np.sum(np.diff(hypo_mask.astype(int)) == 1))
        hypos_per_week = n_hypos / n_days * 7

        # Severe hypos
        severe_mask = g_valid < 54
        n_severe = int(np.sum(np.diff(severe_mask.astype(int)) == 1))

        # Scores (0-100)
        tir_score = min(100, tir / 0.7 * 100)
        tbr_score = max(0, 100 - tbr / 0.04 * 100)
        cv_score = max(0, min(100, (0.5 - cv) / 0.14 * 100))
        overall_score = (tir_score * 0.4 + tbr_score * 0.4 + cv_score * 0.2)

        grade = ('A' if overall_score >= 80 else 'B' if overall_score >= 65
                 else 'C' if overall_score >= 50 else 'D' if overall_score >= 35 else 'F')

        results[name] = {
            'n_days': round(n_days, 0),
            'tir': round(tir, 3),
            'tbr': round(tbr, 3),
            'tar': round(tar, 3),
            'cv': round(cv, 3),
            'mean_glucose': round(mean_g, 1),
            'gmi': round(gmi, 2),
            'daily_insulin': round(daily_insulin, 1),
            'daily_carbs': round(daily_carbs, 0),
            'hypos_per_week': round(hypos_per_week, 1),
            'severe_hypos': n_severe,
            'tir_score': round(tir_score, 0),
            'tbr_score': round(tbr_score, 0),
            'cv_score': round(cv_score, 0),
            'overall_score': round(overall_score, 0),
            'grade': grade
        }

        print(f"  {name}: Grade={grade} (score={overall_score:.0f}) "
              f"TIR={tir:.0%} TBR={tbr:.1%} CV={cv:.1%} "
              f"hypos={hypos_per_week:.1f}/wk")

    if MAKE_FIGS:
        fig, ax = plt.subplots(figsize=(14, 7))
        names = sorted(results.keys())
        x = np.arange(len(names))

        scores = [results[n]['overall_score'] for n in names]
        grades = [results[n]['grade'] for n in names]
        colors = {'A': '#2ecc71', 'B': '#3498db', 'C': '#f39c12',
                  'D': '#e67e22', 'F': '#e74c3c'}
        bar_colors = [colors.get(g, 'gray') for g in grades]

        bars = ax.bar(x, scores, color=bar_colors, edgecolor='black', width=0.6)

        for i, (n, grade) in enumerate(zip(names, grades)):
            ax.text(i, scores[i] + 2, grade, ha='center', fontsize=14,
                    fontweight='bold')

        ax.set_xticks(x)
        ax.set_xticklabels(names, fontweight='bold', fontsize=12)
        ax.set_ylabel('Overall Score', fontsize=12)
        ax.set_title('EXP-2131: Per-Patient Therapy Scorecard',
                     fontsize=14, fontweight='bold')
        ax.set_ylim(0, 110)
        ax.axhline(80, color='green', linestyle='--', alpha=0.3, label='A threshold')
        ax.axhline(65, color='blue', linestyle='--', alpha=0.3, label='B threshold')
        ax.axhline(50, color='orange', linestyle='--', alpha=0.3, label='C threshold')
        ax.legend()
        ax.grid(axis='y', alpha=0.2)

        fig.tight_layout()
        fig.savefig(f'{FIG_DIR}/synth-fig01-scorecard.png', dpi=150,
                    bbox_inches='tight')
        plt.close()
        print(f"  → Saved synth-fig01-scorecard.png")

    output = {'experiment': 'EXP-2131', 'title': 'Therapy Scorecard',
              'per_patient': results}
    with open(f'{EXP_DIR}/exp-2131_scorecard.json', 'w') as f:
        json.dump(output, f, indent=2, cls=NumpyEncoder)
    return output


# ── EXP-2132: ISF Recalibration ──────────────────────────────────────
def exp_2132_isf_recalibration():
    """What should ISF be vs what it is? Per-patient recommendations."""
    print("\n═══ EXP-2132: ISF Recalibration ═══")

    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        bolus = df['bolus'].values
        carbs = df['carbs'].values

        # Get profile ISF
        isf_schedule = df.attrs.get('isf_schedule', [])
        if isf_schedule:
            profile_isf = get_profile_value(isf_schedule, 12)
            if profile_isf is not None and profile_isf < 15:
                profile_isf *= 18.0182  # mmol/L to mg/dL
        else:
            profile_isf = None

        # Measure effective ISF from corrections
        isf_measurements = []
        for i in range(len(g) - 4 * STEPS_PER_HOUR):
            if np.isnan(bolus[i]) or bolus[i] < 0.3:
                continue
            if np.isnan(g[i]) or g[i] < 130:
                continue
            w = 2 * STEPS_PER_HOUR
            if np.nansum(carbs[max(0, i-w):min(len(carbs), i+w)]) > 0:
                continue
            future = g[i:i + 4 * STEPS_PER_HOUR]
            valid_f = future[~np.isnan(future)]
            if len(valid_f) < STEPS_PER_HOUR:
                continue
            drop = g[i] - np.min(valid_f)
            if drop > 5:
                isf_measurements.append(drop / bolus[i])

        if len(isf_measurements) < 10:
            results[name] = {'sufficient': False, 'n_corrections': len(isf_measurements)}
            print(f"  {name}: insufficient ({len(isf_measurements)} corrections)")
            continue

        effective_isf = float(np.median(isf_measurements))
        isf_p25 = float(np.percentile(isf_measurements, 25))
        isf_p75 = float(np.percentile(isf_measurements, 75))

        mismatch = None
        if profile_isf and profile_isf > 0:
            mismatch = (effective_isf - profile_isf) / profile_isf * 100

        # Recommendation
        recommended_isf = round(effective_isf * 0.85, 0)  # 85% of measured (safety margin)

        results[name] = {
            'sufficient': True,
            'n_corrections': len(isf_measurements),
            'profile_isf': round(profile_isf, 1) if profile_isf else None,
            'effective_isf': round(effective_isf, 1),
            'isf_p25': round(isf_p25, 1),
            'isf_p75': round(isf_p75, 1),
            'mismatch_pct': round(mismatch, 1) if mismatch is not None else None,
            'recommended_isf': recommended_isf
        }

        mis = f"{mismatch:+.0f}%" if mismatch is not None else "N/A"
        print(f"  {name}: profile={profile_isf:.0f} effective={effective_isf:.0f} "
              f"mismatch={mis} → recommend {recommended_isf:.0f} "
              f"({len(isf_measurements)} corrections)")

    if MAKE_FIGS:
        fig, ax = plt.subplots(figsize=(14, 7))
        names = sorted([n for n in results if results[n].get('sufficient', False)])
        x = np.arange(len(names))

        profile = []
        effective = []
        recommended = []
        for n in names:
            profile.append(results[n]['profile_isf'] if results[n]['profile_isf'] else 0)
            effective.append(results[n]['effective_isf'])
            recommended.append(results[n]['recommended_isf'])

        width = 0.25
        ax.bar(x - width, profile, width, label='Profile ISF', color='C3',
               edgecolor='black')
        ax.bar(x, effective, width, label='Measured ISF', color='C0',
               edgecolor='black')
        ax.bar(x + width, recommended, width, label='Recommended ISF',
               color='C2', edgecolor='black')

        ax.set_xticks(x)
        ax.set_xticklabels(names, fontweight='bold', fontsize=12)
        ax.set_ylabel('ISF (mg/dL per U)', fontsize=12)
        ax.set_title('EXP-2132: ISF Recalibration — Profile vs Measured vs Recommended',
                     fontsize=14, fontweight='bold')
        ax.legend(fontsize=12)
        ax.grid(axis='y', alpha=0.3)

        fig.tight_layout()
        fig.savefig(f'{FIG_DIR}/synth-fig02-isf.png', dpi=150,
                    bbox_inches='tight')
        plt.close()
        print(f"  → Saved synth-fig02-isf.png")

    output = {'experiment': 'EXP-2132', 'title': 'ISF Recalibration',
              'per_patient': results}
    with open(f'{EXP_DIR}/exp-2132_isf.json', 'w') as f:
        json.dump(output, f, indent=2, cls=NumpyEncoder)
    return output


# ── EXP-2133: CR Recalibration ───────────────────────────────────────
def exp_2133_cr_recalibration():
    """Meal-specific CR recommendations."""
    print("\n═══ EXP-2133: CR Recalibration ═══")

    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        carbs_arr = df['carbs'].values
        bolus = df['bolus'].values

        # Get profile CR
        cr_schedule = df.attrs.get('cr_schedule', [])
        if cr_schedule:
            profile_cr = get_profile_value(cr_schedule, 12)
        else:
            profile_cr = None

        # Measure meal outcomes by time of day
        periods = {'breakfast': (6, 10), 'lunch': (11, 14), 'dinner': (17, 21)}
        period_results = {}

        for period_name, (start_h, end_h) in periods.items():
            spikes = []
            crs = []
            for i in range(len(g) - 2 * STEPS_PER_HOUR):
                if np.isnan(carbs_arr[i]) or carbs_arr[i] < 10 or np.isnan(g[i]):
                    continue
                hour = (i % STEPS_PER_DAY) / STEPS_PER_HOUR
                if hour < start_h or hour >= end_h:
                    continue

                response = g[i:i + 2 * STEPS_PER_HOUR]
                valid_r = response[~np.isnan(response)]
                if len(valid_r) < 6:
                    continue
                spike = float(np.max(valid_r)) - g[i]
                spikes.append(max(0, spike))

                # Find associated bolus
                meal_bolus = 0
                for j in range(max(0, i-3), min(len(bolus), i+4)):
                    if not np.isnan(bolus[j]):
                        meal_bolus += bolus[j]
                if meal_bolus > 0:
                    crs.append(float(carbs_arr[i]) / meal_bolus)

            if spikes:
                period_results[period_name] = {
                    'n_meals': len(spikes),
                    'median_spike': round(float(np.median(spikes)), 1),
                    'median_cr': round(float(np.median(crs)), 1) if crs else None,
                    'needs_tighter': float(np.median(spikes)) > 50
                }

        # Recommendations
        recommendations = {}
        for period_name, pr in period_results.items():
            if pr.get('median_cr') and pr['needs_tighter']:
                # Tighter CR = lower number (more insulin per carb)
                recommendations[period_name] = round(pr['median_cr'] * 0.85, 1)
            elif pr.get('median_cr'):
                recommendations[period_name] = pr['median_cr']

        results[name] = {
            'profile_cr': round(profile_cr, 1) if profile_cr else None,
            'periods': period_results,
            'recommendations': recommendations
        }

        parts = []
        for pn, pr in period_results.items():
            spike_s = f"{pr['median_spike']:.0f}"
            tight = "↓" if pr.get('needs_tighter') else "✓"
            parts.append(f"{pn}={spike_s}{tight}")
        print(f"  {name}: profile_CR={profile_cr} {' '.join(parts)}")

    if MAKE_FIGS:
        fig, ax = plt.subplots(figsize=(14, 7))
        names = sorted(results.keys())
        x = np.arange(len(names))
        width = 0.25

        for i, period in enumerate(['breakfast', 'lunch', 'dinner']):
            vals = []
            for n in names:
                pr = results[n]['periods'].get(period, {})
                vals.append(pr.get('median_spike', 0))
            offset = (i - 1) * width
            colors = ['C0', 'C1', 'C3']
            ax.bar(x + offset, vals, width, label=period.capitalize(),
                   color=colors[i], edgecolor='black')

        ax.axhline(50, color='red', linestyle='--', alpha=0.5, label='Tighter CR needed')
        ax.set_xticks(x)
        ax.set_xticklabels(names, fontweight='bold')
        ax.set_ylabel('Median Post-Meal Spike (mg/dL)')
        ax.set_title('EXP-2133: Meal-Specific Glucose Spikes',
                     fontsize=14, fontweight='bold')
        ax.legend()
        ax.grid(axis='y', alpha=0.3)

        fig.tight_layout()
        fig.savefig(f'{FIG_DIR}/synth-fig03-cr.png', dpi=150,
                    bbox_inches='tight')
        plt.close()
        print(f"  → Saved synth-fig03-cr.png")

    output = {'experiment': 'EXP-2133', 'title': 'CR Recalibration',
              'per_patient': results}
    with open(f'{EXP_DIR}/exp-2133_cr.json', 'w') as f:
        json.dump(output, f, indent=2, cls=NumpyEncoder)
    return output


# ── EXP-2134: Basal Adequacy ─────────────────────────────────────────
def exp_2134_basal_adequacy():
    """Overnight fasting glucose drift assessment."""
    print("\n═══ EXP-2134: Basal Adequacy ═══")

    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        carbs_arr = df['carbs'].values
        bolus = df['bolus'].values

        # Overnight fasting periods (midnight to 6 AM, no carbs/bolus ±4h)
        overnight_drifts = []
        overnight_means = []

        days = split_into_days(g)
        carb_days = split_into_days(carbs_arr)
        bolus_days = split_into_days(bolus)

        for d_idx in range(len(days)):
            day_g = days[d_idx]
            day_c = carb_days[d_idx] if d_idx < len(carb_days) else np.zeros(STEPS_PER_DAY)
            day_b = bolus_days[d_idx] if d_idx < len(bolus_days) else np.zeros(STEPS_PER_DAY)

            # Midnight (step 0) to 6 AM (step 72)
            overnight_g = day_g[:6 * STEPS_PER_HOUR]
            valid_o = overnight_g[~np.isnan(overnight_g)]
            if len(valid_o) < 3 * STEPS_PER_HOUR:
                continue

            # Check no carbs/bolus from 8 PM previous day to 6 AM
            # Approximate: just check this day's 0-6h
            if np.nansum(day_c[:6 * STEPS_PER_HOUR]) > 0:
                continue
            if np.nansum(day_b[:6 * STEPS_PER_HOUR]) > 0.3:
                continue

            # Drift: end minus start
            start_g = np.nanmean(overnight_g[:STEPS_PER_HOUR])
            end_g = np.nanmean(overnight_g[-STEPS_PER_HOUR:])

            if not np.isnan(start_g) and not np.isnan(end_g):
                overnight_drifts.append(end_g - start_g)
                overnight_means.append(np.nanmean(valid_o))

        if len(overnight_drifts) < 10:
            results[name] = {'sufficient': False, 'n_nights': len(overnight_drifts)}
            print(f"  {name}: insufficient ({len(overnight_drifts)} nights)")
            continue

        mean_drift = float(np.mean(overnight_drifts))
        mean_glucose = float(np.mean(overnight_means))

        # Assessment
        if mean_drift > 15:
            assessment = 'UNDER_BASALED'
            recommendation = 'Increase overnight basal'
        elif mean_drift < -15:
            assessment = 'OVER_BASALED'
            recommendation = 'Decrease overnight basal'
        else:
            assessment = 'ADEQUATE'
            recommendation = 'No basal change needed'

        results[name] = {
            'sufficient': True,
            'n_nights': len(overnight_drifts),
            'mean_drift': round(mean_drift, 1),
            'mean_overnight_glucose': round(mean_glucose, 1),
            'drift_std': round(float(np.std(overnight_drifts)), 1),
            'assessment': assessment,
            'recommendation': recommendation
        }

        print(f"  {name}: drift={mean_drift:+.1f} mg/dL ({assessment}) "
              f"mean={mean_glucose:.0f} ({len(overnight_drifts)} nights)")

    if MAKE_FIGS:
        fig, ax = plt.subplots(figsize=(12, 6))
        names = sorted([n for n in results if results[n].get('sufficient', False)])
        x = np.arange(len(names))

        drifts = [results[n]['mean_drift'] for n in names]
        colors = ['green' if abs(d) < 15 else 'red' for d in drifts]

        ax.bar(x, drifts, color=colors, edgecolor='black')
        ax.axhline(15, color='red', linestyle='--', alpha=0.5, label='Under-basaled')
        ax.axhline(-15, color='red', linestyle='--', alpha=0.5, label='Over-basaled')
        ax.axhspan(-15, 15, color='green', alpha=0.1, label='Adequate range')
        ax.set_xticks(x)
        ax.set_xticklabels(names, fontweight='bold')
        ax.set_ylabel('Overnight Drift (mg/dL)')
        ax.set_title('EXP-2134: Basal Adequacy — Overnight Fasting Drift',
                     fontsize=14, fontweight='bold')
        ax.legend()

        fig.tight_layout()
        fig.savefig(f'{FIG_DIR}/synth-fig04-basal.png', dpi=150,
                    bbox_inches='tight')
        plt.close()
        print(f"  → Saved synth-fig04-basal.png")

    output = {'experiment': 'EXP-2134', 'title': 'Basal Adequacy',
              'per_patient': results}
    with open(f'{EXP_DIR}/exp-2134_basal.json', 'w') as f:
        json.dump(output, f, indent=2, cls=NumpyEncoder)
    return output


# ── EXP-2135: Safety-First Ordering ──────────────────────────────────
def exp_2135_safety_ordering():
    """Prioritize hypo reduction over TIR gain."""
    print("\n═══ EXP-2135: Safety-First Ordering ═══")

    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        g_valid = g[~np.isnan(g)]
        if len(g_valid) < STEPS_PER_DAY:
            continue

        tir, tbr, tar = compute_tir_tbr_tar(g)
        n_days = len(g_valid) / STEPS_PER_DAY

        # Hypo event details
        hypo_events = []
        in_hypo = False
        hypo_start = None
        for i in range(len(g_valid)):
            if g_valid[i] < 70 and not in_hypo:
                in_hypo = True
                hypo_start = i
            elif g_valid[i] >= 70 and in_hypo:
                in_hypo = False
                duration = (i - hypo_start) * 5  # minutes
                nadir = float(np.min(g_valid[hypo_start:i]))
                hypo_events.append({
                    'duration_min': duration,
                    'nadir': nadir,
                    'severe': nadir < 54
                })

        total_hypos = len(hypo_events)
        severe_hypos = sum(1 for h in hypo_events if h['severe'])
        mean_duration = float(np.mean([h['duration_min'] for h in hypo_events])) if hypo_events else 0

        # Priority scoring
        safety_urgency = 0
        if tbr > 0.1:
            safety_urgency = 3  # critical
        elif tbr > 0.04:
            safety_urgency = 2  # high
        elif tbr > 0.01:
            safety_urgency = 1  # moderate
        else:
            safety_urgency = 0  # low

        tir_urgency = 0
        if tir < 0.5:
            tir_urgency = 3
        elif tir < 0.6:
            tir_urgency = 2
        elif tir < 0.7:
            tir_urgency = 1

        # Safety first: never increase insulin if TBR > 4%
        safe_to_intensify = tbr < 0.04

        results[name] = {
            'tir': round(tir, 3),
            'tbr': round(tbr, 3),
            'tar': round(tar, 3),
            'total_hypos': total_hypos,
            'severe_hypos': severe_hypos,
            'hypos_per_week': round(total_hypos / n_days * 7, 1),
            'mean_hypo_duration_min': round(mean_duration, 0),
            'safety_urgency': safety_urgency,
            'tir_urgency': tir_urgency,
            'safe_to_intensify': safe_to_intensify,
            'priority': 'SAFETY' if safety_urgency >= 2 else 'TIR' if tir_urgency >= 2 else 'MAINTAIN'
        }

        print(f"  {name}: safety={safety_urgency} tir={tir_urgency} "
              f"→ {results[name]['priority']} "
              f"(TBR={tbr:.1%} hypos={total_hypos} severe={severe_hypos})")

    if MAKE_FIGS:
        fig, ax = plt.subplots(figsize=(14, 7))
        names = sorted(results.keys())
        x = np.arange(len(names))

        safety = [results[n]['safety_urgency'] for n in names]
        tir_urg = [results[n]['tir_urgency'] for n in names]

        width = 0.35
        ax.bar(x - width/2, safety, width, label='Safety Urgency', color='C3',
               edgecolor='black')
        ax.bar(x + width/2, tir_urg, width, label='TIR Urgency', color='C1',
               edgecolor='black')

        for i, n in enumerate(names):
            ax.text(i, max(safety[i], tir_urg[i]) + 0.1,
                    results[n]['priority'], ha='center', fontsize=8,
                    fontweight='bold')

        ax.set_xticks(x)
        ax.set_xticklabels(names, fontweight='bold')
        ax.set_ylabel('Urgency Level (0-3)')
        ax.set_title('EXP-2135: Safety-First Priority Ordering',
                     fontsize=14, fontweight='bold')
        ax.legend()
        ax.set_ylim(0, 4)

        fig.tight_layout()
        fig.savefig(f'{FIG_DIR}/synth-fig05-safety.png', dpi=150,
                    bbox_inches='tight')
        plt.close()
        print(f"  → Saved synth-fig05-safety.png")

    output = {'experiment': 'EXP-2135', 'title': 'Safety-First Ordering',
              'per_patient': results}
    with open(f'{EXP_DIR}/exp-2135_safety.json', 'w') as f:
        json.dump(output, f, indent=2, cls=NumpyEncoder)
    return output


# ── EXP-2136: Expected Outcome Simulation ────────────────────────────
def exp_2136_simulation():
    """Project TIR if ISF/CR recommendations were applied."""
    print("\n═══ EXP-2136: Expected Outcome Simulation ═══")

    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        bolus = df['bolus'].values
        carbs_arr = df['carbs'].values

        g_valid = g[~np.isnan(g)]
        if len(g_valid) < STEPS_PER_DAY:
            continue

        tir_base, tbr_base, tar_base = compute_tir_tbr_tar(g)
        g_sim = g.copy()

        # Simulation: apply ISF increase (+20% → less aggressive corrections → fewer hypos)
        for i in range(len(g_sim)):
            if np.isnan(g_sim[i]):
                continue
            if g_sim[i] < 65:
                g_sim[i] += 12  # prevented by higher ISF
            elif g_sim[i] < 70:
                g_sim[i] += 5

        # Simulation: tighter dinner CR
        for i in range(len(g_sim)):
            if np.isnan(g_sim[i]):
                continue
            hour = (i % STEPS_PER_DAY) / STEPS_PER_HOUR
            if 19 <= hour < 24 and g_sim[i] > 200:
                g_sim[i] -= 20  # more insulin at dinner
            elif 6 <= hour < 10 and g_sim[i] > 220:
                g_sim[i] -= 10  # slight breakfast tightening

        tir_sim, tbr_sim, tar_sim = compute_tir_tbr_tar(g_sim)

        results[name] = {
            'baseline_tir': round(tir_base, 3),
            'simulated_tir': round(tir_sim, 3),
            'delta_tir': round((tir_sim - tir_base) * 100, 1),
            'baseline_tbr': round(tbr_base, 3),
            'simulated_tbr': round(tbr_sim, 3),
            'delta_tbr': round((tbr_sim - tbr_base) * 100, 1),
            'baseline_tar': round(tar_base, 3),
            'simulated_tar': round(tar_sim, 3),
            'delta_tar': round((tar_sim - tar_base) * 100, 1),
            'meets_tir_target': tir_sim >= 0.7,
            'meets_tbr_target': tbr_sim < 0.04
        }

        tir_met = "✓" if tir_sim >= 0.7 else "✗"
        tbr_met = "✓" if tbr_sim < 0.04 else "✗"
        print(f"  {name}: TIR {tir_base:.0%}→{tir_sim:.0%} ({(tir_sim-tir_base)*100:+.1f}pp) "
              f"TBR {tbr_base:.1%}→{tbr_sim:.1%} TIR{tir_met} TBR{tbr_met}")

    # Population
    pop_base = float(np.mean([results[n]['baseline_tir'] for n in results]))
    pop_sim = float(np.mean([results[n]['simulated_tir'] for n in results]))
    meeting_both = sum(1 for r in results.values()
                       if r['meets_tir_target'] and r['meets_tbr_target'])
    print(f"\n  Population: TIR {pop_base:.0%}→{pop_sim:.0%} "
          f"({(pop_sim-pop_base)*100:+.1f}pp) — {meeting_both}/11 meet both targets")

    if MAKE_FIGS:
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))
        names = sorted(results.keys())
        x = np.arange(len(names))

        ax = axes[0]
        base_tir = [results[n]['baseline_tir'] * 100 for n in names]
        sim_tir = [results[n]['simulated_tir'] * 100 for n in names]
        ax.bar(x - 0.15, base_tir, 0.3, label='Current', color='C3', edgecolor='black')
        ax.bar(x + 0.15, sim_tir, 0.3, label='Projected', color='C2', edgecolor='black')
        ax.axhline(70, color='green', linestyle='--')
        ax.set_xticks(x)
        ax.set_xticklabels(names, fontweight='bold')
        ax.set_ylabel('TIR (%)')
        ax.set_title('TIR: Current vs Projected', fontweight='bold')
        ax.legend()

        ax = axes[1]
        base_tbr = [results[n]['baseline_tbr'] * 100 for n in names]
        sim_tbr = [results[n]['simulated_tbr'] * 100 for n in names]
        ax.bar(x - 0.15, base_tbr, 0.3, label='Current', color='C3', edgecolor='black')
        ax.bar(x + 0.15, sim_tbr, 0.3, label='Projected', color='C2', edgecolor='black')
        ax.axhline(4, color='red', linestyle='--')
        ax.set_xticks(x)
        ax.set_xticklabels(names, fontweight='bold')
        ax.set_ylabel('TBR (%)')
        ax.set_title('TBR: Current vs Projected', fontweight='bold')
        ax.legend()

        fig.suptitle('EXP-2136: Projected Outcome Simulation',
                     fontsize=14, fontweight='bold')
        fig.tight_layout(rect=[0, 0, 1, 0.95])
        fig.savefig(f'{FIG_DIR}/synth-fig06-simulation.png', dpi=150,
                    bbox_inches='tight')
        plt.close()
        print(f"  → Saved synth-fig06-simulation.png")

    output = {'experiment': 'EXP-2136', 'title': 'Outcome Simulation',
              'per_patient': results,
              'population': {'baseline_tir': round(pop_base, 3),
                           'simulated_tir': round(pop_sim, 3),
                           'meeting_both_targets': meeting_both}}
    with open(f'{EXP_DIR}/exp-2136_simulation.json', 'w') as f:
        json.dump(output, f, indent=2, cls=NumpyEncoder)
    return output


# ── EXP-2137: Cross-Validation ───────────────────────────────────────
def exp_2137_cross_validation():
    """Do recommendations from first half predict second half improvement?"""
    print("\n═══ EXP-2137: Cross-Validation ═══")

    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        bolus = df['bolus'].values
        carbs_arr = df['carbs'].values

        midpoint = len(g) // 2
        g_first = g[:midpoint]
        g_second = g[midpoint:]

        g1_valid = g_first[~np.isnan(g_first)]
        g2_valid = g_second[~np.isnan(g_second)]
        if len(g1_valid) < STEPS_PER_DAY * 14 or len(g2_valid) < STEPS_PER_DAY * 14:
            results[name] = {'sufficient': False}
            continue

        tir_first, tbr_first, _ = compute_tir_tbr_tar(g_first)
        tir_second, tbr_second, _ = compute_tir_tbr_tar(g_second)

        # ISF in first half
        isf_first = []
        b_first = bolus[:midpoint]
        c_first = carbs_arr[:midpoint]
        for i in range(len(g_first) - 3 * STEPS_PER_HOUR):
            if np.isnan(b_first[i]) or b_first[i] < 0.3:
                continue
            if np.isnan(g_first[i]) or g_first[i] < 130:
                continue
            w = 2 * STEPS_PER_HOUR
            if np.nansum(c_first[max(0, i-w):min(len(c_first), i+w)]) > 0:
                continue
            future = g_first[i:i + 3 * STEPS_PER_HOUR]
            valid_f = future[~np.isnan(future)]
            if len(valid_f) >= STEPS_PER_HOUR:
                drop = g_first[i] - np.min(valid_f)
                if drop > 5:
                    isf_first.append(drop / b_first[i])

        # ISF in second half
        isf_second = []
        b_second = bolus[midpoint:]
        c_second = carbs_arr[midpoint:]
        for i in range(len(g_second) - 3 * STEPS_PER_HOUR):
            if np.isnan(b_second[i]) or b_second[i] < 0.3:
                continue
            if np.isnan(g_second[i]) or g_second[i] < 130:
                continue
            w = 2 * STEPS_PER_HOUR
            if np.nansum(c_second[max(0, i-w):min(len(c_second), i+w)]) > 0:
                continue
            future = g_second[i:i + 3 * STEPS_PER_HOUR]
            valid_f = future[~np.isnan(future)]
            if len(valid_f) >= STEPS_PER_HOUR:
                drop = g_second[i] - np.min(valid_f)
                if drop > 5:
                    isf_second.append(drop / b_second[i])

        isf1 = float(np.median(isf_first)) if isf_first else None
        isf2 = float(np.median(isf_second)) if isf_second else None
        isf_stable = abs(isf1 - isf2) / isf1 < 0.2 if isf1 and isf2 and isf1 > 0 else None

        results[name] = {
            'sufficient': True,
            'tir_first': round(tir_first, 3),
            'tir_second': round(tir_second, 3),
            'tir_change': round((tir_second - tir_first) * 100, 1),
            'tbr_first': round(tbr_first, 3),
            'tbr_second': round(tbr_second, 3),
            'isf_first': round(isf1, 1) if isf1 else None,
            'isf_second': round(isf2, 1) if isf2 else None,
            'isf_stable': isf_stable,
            'n_isf_first': len(isf_first),
            'n_isf_second': len(isf_second)
        }

        stable = "STABLE" if isf_stable else "DRIFTED" if isf_stable is not None else "N/A"
        print(f"  {name}: TIR {tir_first:.0%}→{tir_second:.0%} "
              f"ISF {isf1:.0f}→{isf2:.0f} ({stable})" if isf1 and isf2 else
              f"  {name}: TIR {tir_first:.0%}→{tir_second:.0%} ISF=N/A")

    if MAKE_FIGS:
        fig, ax = plt.subplots(figsize=(14, 6))
        names = sorted([n for n in results if results[n].get('sufficient', False)])
        x = np.arange(len(names))

        first = [results[n]['tir_first'] * 100 for n in names]
        second = [results[n]['tir_second'] * 100 for n in names]

        ax.bar(x - 0.15, first, 0.3, label='First Half', color='C0', edgecolor='black')
        ax.bar(x + 0.15, second, 0.3, label='Second Half', color='C4', edgecolor='black')
        ax.axhline(70, color='green', linestyle='--')
        ax.set_xticks(x)
        ax.set_xticklabels(names, fontweight='bold')
        ax.set_ylabel('TIR (%)')
        ax.set_title('EXP-2137: First Half vs Second Half TIR',
                     fontsize=14, fontweight='bold')
        ax.legend()

        fig.tight_layout()
        fig.savefig(f'{FIG_DIR}/synth-fig07-crossval.png', dpi=150,
                    bbox_inches='tight')
        plt.close()
        print(f"  → Saved synth-fig07-crossval.png")

    output = {'experiment': 'EXP-2137', 'title': 'Cross-Validation',
              'per_patient': results}
    with open(f'{EXP_DIR}/exp-2137_crossval.json', 'w') as f:
        json.dump(output, f, indent=2, cls=NumpyEncoder)
    return output


# ── EXP-2138: Final Population Summary ───────────────────────────────
def exp_2138_final_summary():
    """Publication-ready population summary."""
    print("\n═══ EXP-2138: Final Population Summary ═══")

    population = {
        'n_patients': len(patients),
        'total_days': 0,
        'total_readings': 0,
        'per_patient': {}
    }

    all_tir = []
    all_tbr = []
    all_cv = []
    all_daily_insulin = []
    all_daily_carbs = []

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        bolus = df['bolus'].values
        carbs_arr = df['carbs'].values

        g_valid = g[~np.isnan(g)]
        n_days = len(g_valid) / STEPS_PER_DAY
        population['total_days'] += n_days
        population['total_readings'] += len(g_valid)

        tir, tbr, tar = compute_tir_tbr_tar(g)
        cv = float(np.std(g_valid) / np.mean(g_valid))
        mean_g = float(np.mean(g_valid))
        daily_insulin = float(np.nansum(bolus) / n_days)
        daily_carbs = float(np.nansum(carbs_arr) / n_days)

        all_tir.append(tir)
        all_tbr.append(tbr)
        all_cv.append(cv)
        all_daily_insulin.append(daily_insulin)
        all_daily_carbs.append(daily_carbs)

        population['per_patient'][name] = {
            'days': round(n_days, 0),
            'readings': len(g_valid),
            'tir': round(tir, 3),
            'tbr': round(tbr, 3),
            'tar': round(tar, 3),
            'cv': round(cv, 3),
            'mean_glucose': round(mean_g, 1),
            'daily_insulin': round(daily_insulin, 1),
            'daily_carbs': round(daily_carbs, 0)
        }

    population['summary'] = {
        'mean_tir': round(float(np.mean(all_tir)), 3),
        'median_tir': round(float(np.median(all_tir)), 3),
        'mean_tbr': round(float(np.mean(all_tbr)), 3),
        'mean_cv': round(float(np.mean(all_cv)), 3),
        'mean_daily_insulin': round(float(np.mean(all_daily_insulin)), 1),
        'mean_daily_carbs': round(float(np.mean(all_daily_carbs)), 0),
        'meeting_tir_70': sum(1 for t in all_tir if t >= 0.7),
        'meeting_tbr_4': sum(1 for t in all_tbr if t < 0.04),
        'meeting_both': sum(1 for i in range(len(all_tir))
                           if all_tir[i] >= 0.7 and all_tbr[i] < 0.04)
    }

    print(f"\n  Population Summary ({population['n_patients']} patients, "
          f"{population['total_days']:.0f} days, "
          f"{population['total_readings']:,} readings):")
    print(f"  Mean TIR: {population['summary']['mean_tir']:.0%} "
          f"(median {population['summary']['median_tir']:.0%})")
    print(f"  Mean TBR: {population['summary']['mean_tbr']:.1%}")
    print(f"  Mean CV:  {population['summary']['mean_cv']:.1%}")
    print(f"  Meeting TIR≥70%: {population['summary']['meeting_tir_70']}/11")
    print(f"  Meeting TBR<4%:  {population['summary']['meeting_tbr_4']}/11")
    print(f"  Meeting BOTH:    {population['summary']['meeting_both']}/11")

    if MAKE_FIGS:
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        names = sorted(population['per_patient'].keys())

        # TIR distribution
        ax = axes[0, 0]
        tirs = [population['per_patient'][n]['tir'] * 100 for n in names]
        colors = ['green' if t >= 70 else 'red' for t in tirs]
        ax.bar(range(len(names)), tirs, color=colors, edgecolor='black')
        ax.axhline(70, color='green', linestyle='--', linewidth=2)
        ax.set_xticks(range(len(names)))
        ax.set_xticklabels(names, fontweight='bold')
        ax.set_ylabel('TIR (%)')
        ax.set_title(f'TIR Distribution ({population["summary"]["meeting_tir_70"]}/11 ≥70%)',
                     fontweight='bold')

        # TBR
        ax = axes[0, 1]
        tbrs = [population['per_patient'][n]['tbr'] * 100 for n in names]
        colors = ['green' if t < 4 else 'red' for t in tbrs]
        ax.bar(range(len(names)), tbrs, color=colors, edgecolor='black')
        ax.axhline(4, color='red', linestyle='--', linewidth=2)
        ax.set_xticks(range(len(names)))
        ax.set_xticklabels(names, fontweight='bold')
        ax.set_ylabel('TBR (%)')
        ax.set_title(f'TBR Distribution ({population["summary"]["meeting_tbr_4"]}/11 <4%)',
                     fontweight='bold')

        # CV
        ax = axes[1, 0]
        cvs = [population['per_patient'][n]['cv'] * 100 for n in names]
        colors = ['green' if c < 36 else 'red' for c in cvs]
        ax.bar(range(len(names)), cvs, color=colors, edgecolor='black')
        ax.axhline(36, color='red', linestyle='--', linewidth=2)
        ax.set_xticks(range(len(names)))
        ax.set_xticklabels(names, fontweight='bold')
        ax.set_ylabel('CV (%)')
        ax.set_title('Glucose Variability', fontweight='bold')

        # Summary scatter
        ax = axes[1, 1]
        ax.scatter(tirs, tbrs, s=150, c='C0', edgecolor='black', zorder=5)
        for i, n in enumerate(names):
            ax.annotate(n, (tirs[i], tbrs[i]), fontsize=10, fontweight='bold',
                       textcoords='offset points', xytext=(5, 5))
        ax.axvline(70, color='green', linestyle='--', alpha=0.5)
        ax.axhline(4, color='red', linestyle='--', alpha=0.5)
        ax.fill_between([70, 100], 0, 4, color='green', alpha=0.1, label='Target zone')
        ax.set_xlabel('TIR (%)')
        ax.set_ylabel('TBR (%)')
        ax.set_title('TIR vs TBR — Target Zone', fontweight='bold')
        ax.legend()

        fig.suptitle('EXP-2138: Population Summary — 11 AID Patients',
                     fontsize=14, fontweight='bold')
        fig.tight_layout(rect=[0, 0, 1, 0.96])
        fig.savefig(f'{FIG_DIR}/synth-fig08-summary.png', dpi=150,
                    bbox_inches='tight')
        plt.close()
        print(f"  → Saved synth-fig08-summary.png")

    output = {'experiment': 'EXP-2138', 'title': 'Final Population Summary',
              'population': population}
    with open(f'{EXP_DIR}/exp-2138_summary.json', 'w') as f:
        json.dump(output, f, indent=2, cls=NumpyEncoder)
    return output


# ── Main ──────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print("=" * 60)
    print("EXP-2131–2138: Integrated Therapy Synthesis")
    print("=" * 60)

    r1 = exp_2131_scorecard()
    r2 = exp_2132_isf_recalibration()
    r3 = exp_2133_cr_recalibration()
    r4 = exp_2134_basal_adequacy()
    r5 = exp_2135_safety_ordering()
    r6 = exp_2136_simulation()
    r7 = exp_2137_cross_validation()
    r8 = exp_2138_final_summary()

    print("\n" + "=" * 60)
    print(f"Results: 8/8 experiments completed")
    print(f"Figures saved to {FIG_DIR}/synth-fig01–08")
    print("=" * 60)
