#!/usr/bin/env python3
"""
EXP-2181–2188: Insulin Pharmacokinetics & Duration of Action Analysis

Characterize effective insulin action duration (DIA), bolus-to-effect timing,
and insulin stacking patterns that drive the universal hypoglycemia problem.

EXP-2181: Effective DIA estimation — how long does insulin actually act?
EXP-2182: Bolus-to-nadir timing — when does glucose bottom out after bolus?
EXP-2183: Insulin stacking analysis — overlapping bolus effects
EXP-2184: Correction bolus effectiveness — does correction actually correct?
EXP-2185: Meal bolus timing optimization — pre-bolus benefit quantification
EXP-2186: IOB decay curve — actual vs model IOB
EXP-2187: Insulin sensitivity by time of day — circadian ISF variation
EXP-2188: Integrated PK recommendations — per-patient DIA/timing strategy

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


# ── EXP-2181: Effective DIA Estimation ──────────────────────────────
def exp_2181_dia_estimation():
    """How long does insulin actually act based on glucose response?"""
    print("\n═══ EXP-2181: Effective DIA Estimation ═══")

    all_results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        bolus = df['bolus'].values if 'bolus' in df.columns else None
        iob = df['iob'].values if 'iob' in df.columns else None
        carbs = df['carbs'].values if 'carbs' in df.columns else None

        if bolus is None:
            continue

        # Find correction boluses (bolus without carbs within ±30min)
        correction_events = []
        for i in range(len(bolus)):
            if np.isnan(bolus[i]) or bolus[i] < 0.5:
                continue

            # Check for carbs within ±30min (±6 steps)
            carb_window = slice(max(0, i - 6), min(len(g), i + 7))
            nearby_carbs = carbs[carb_window] if carbs is not None else np.zeros(1)
            if np.nansum(nearby_carbs) > 2:
                continue  # This is a meal bolus, skip

            # Need 6 hours of glucose data after
            window_end = min(i + 6 * STEPS_PER_HOUR, len(g))
            if window_end - i < 4 * STEPS_PER_HOUR:
                continue

            # Check no additional boluses in next 4 hours
            next_bolus_window = bolus[i + 1:min(i + 4 * STEPS_PER_HOUR, len(bolus))]
            if np.nansum(next_bolus_window) > 0.5:
                continue  # Overlapping bolus

            pre_g = g[i] if not np.isnan(g[i]) else np.nan
            if np.isnan(pre_g):
                continue

            # Track glucose response
            response = g[i:window_end]
            valid = ~np.isnan(response)
            if valid.sum() < len(response) * 0.5:
                continue

            # Find nadir and recovery
            response_clean = response.copy()
            response_clean[~valid] = np.interp(
                np.where(~valid)[0],
                np.where(valid)[0],
                response[valid]
            ) if valid.sum() >= 2 else response

            nadir_idx = int(np.argmin(response_clean))
            nadir_time_h = nadir_idx / STEPS_PER_HOUR
            nadir_g = float(response_clean[nadir_idx])
            drop = pre_g - nadir_g

            if drop < 5:  # Minimal effect
                continue

            # Find when glucose returns to 90% of pre-bolus level
            recovery_threshold = pre_g - drop * 0.1  # 90% recovery
            recovery_idx = None
            for t in range(nadir_idx, len(response_clean)):
                if response_clean[t] >= recovery_threshold:
                    recovery_idx = t
                    break

            recovery_time_h = recovery_idx / STEPS_PER_HOUR if recovery_idx else None

            # Find when effect is essentially done (glucose stabilizes)
            # Use 5-point rolling std
            if len(response_clean) > 10:
                rolling_std = np.array([np.std(response_clean[max(0, t-5):t+1])
                                        for t in range(len(response_clean))])
                stable_idx = None
                for t in range(nadir_idx + 6, len(rolling_std)):
                    if rolling_std[t] < 3:  # < 3 mg/dL variation
                        stable_idx = t
                        break
                stable_time_h = stable_idx / STEPS_PER_HOUR if stable_idx else None
            else:
                stable_time_h = None

            correction_events.append({
                'bolus_size': float(bolus[i]),
                'pre_glucose': float(pre_g),
                'nadir_glucose': nadir_g,
                'drop': float(drop),
                'nadir_time_h': nadir_time_h,
                'recovery_time_h': recovery_time_h,
                'stable_time_h': stable_time_h,
                'effective_isf': float(drop / bolus[i])
            })

        if len(correction_events) < 3:
            print(f"  {name}: only {len(correction_events)} isolated corrections")
            all_results[name] = {'n_events': len(correction_events)}
            continue

        nadir_times = [e['nadir_time_h'] for e in correction_events]
        recovery_times = [e['recovery_time_h'] for e in correction_events
                          if e['recovery_time_h'] is not None]
        stable_times = [e['stable_time_h'] for e in correction_events
                        if e['stable_time_h'] is not None]

        # Profile DIA
        dia_schedule = df.attrs.get('dia', None)
        if dia_schedule is None:
            dia_schedule = df.attrs.get('insulin_action_curve', None)
        profile_dia = float(dia_schedule) if dia_schedule and isinstance(dia_schedule, (int, float)) else None

        effective_dia = float(np.median(recovery_times)) if recovery_times else None

        all_results[name] = {
            'n_events': len(correction_events),
            'median_nadir_time_h': float(np.median(nadir_times)),
            'mean_nadir_time_h': float(np.mean(nadir_times)),
            'median_recovery_time_h': float(np.median(recovery_times)) if recovery_times else None,
            'median_stable_time_h': float(np.median(stable_times)) if stable_times else None,
            'profile_dia': profile_dia,
            'effective_dia': effective_dia,
            'dia_mismatch': (effective_dia / profile_dia if effective_dia and profile_dia else None),
            'mean_drop': float(np.mean([e['drop'] for e in correction_events])),
            'mean_effective_isf': float(np.mean([e['effective_isf'] for e in correction_events]))
        }

        print(f"  {name}: {len(correction_events)} corrections, "
              f"nadir={np.median(nadir_times):.1f}h, "
              f"recovery={np.median(recovery_times):.1f}h" if recovery_times else "",
              f"profile_DIA={profile_dia}" if profile_dia else "")

    with open(f'{EXP_DIR}/exp-2181_dia.json', 'w') as f:
        json.dump(all_results, f, indent=2, cls=NumpyEncoder)

    if MAKE_FIGS and all_results:
        fig, axes = plt.subplots(1, 3, figsize=(16, 5))

        patient_names = sorted([pn for pn in all_results if all_results[pn].get('median_nadir_time_h')])

        if patient_names:
            # Panel 1: Nadir timing
            nadirs = [all_results[pn]['median_nadir_time_h'] for pn in patient_names]
            axes[0].bar(patient_names, nadirs, color='steelblue', alpha=0.7)
            axes[0].set_ylabel('Median Nadir Time (hours)')
            axes[0].set_title('Time to Peak Insulin Effect')
            axes[0].tick_params(axis='x', labelsize=8)
            axes[0].grid(True, alpha=0.3, axis='y')

            # Panel 2: Recovery time (effective DIA)
            recoveries = [all_results[pn].get('median_recovery_time_h', 0) or 0
                          for pn in patient_names]
            axes[1].bar(patient_names, recoveries, color='coral', alpha=0.7)
            axes[1].axhline(y=5, color='gray', linestyle='--', alpha=0.5, label='Typical DIA=5h')
            axes[1].set_ylabel('Median Recovery Time (hours)')
            axes[1].set_title('Effective DIA (90% recovery)')
            axes[1].legend(fontsize=8)
            axes[1].tick_params(axis='x', labelsize=8)
            axes[1].grid(True, alpha=0.3, axis='y')

            # Panel 3: Effective ISF from corrections
            isfs = [all_results[pn].get('mean_effective_isf', 0) for pn in patient_names]
            axes[2].bar(patient_names, isfs, color='green', alpha=0.7)
            axes[2].set_ylabel('Effective ISF (mg/dL per U)')
            axes[2].set_title('Correction Effectiveness')
            axes[2].tick_params(axis='x', labelsize=8)
            axes[2].grid(True, alpha=0.3, axis='y')

        plt.tight_layout()
        plt.savefig(f'{FIG_DIR}/pk-fig01-dia.png', dpi=150)
        plt.close()
        print("  → Saved pk-fig01-dia.png")

    return all_results


# ── EXP-2182: Bolus-to-Nadir Timing ────────────────────────────────
def exp_2182_bolus_nadir():
    """When does glucose bottom out after any bolus?"""
    print("\n═══ EXP-2182: Bolus-to-Nadir Timing ═══")

    all_results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        bolus = df['bolus'].values if 'bolus' in df.columns else None
        carbs = df['carbs'].values if 'carbs' in df.columns else None

        if bolus is None:
            continue

        meal_nadirs = []
        correction_nadirs = []

        for i in range(len(bolus)):
            if np.isnan(bolus[i]) or bolus[i] < 0.5:
                continue

            window_end = min(i + 6 * STEPS_PER_HOUR, len(g))
            if window_end - i < 3 * STEPS_PER_HOUR:
                continue

            pre_g = g[i] if not np.isnan(g[i]) else np.nan
            if np.isnan(pre_g):
                continue

            response = g[i:window_end]
            valid = ~np.isnan(response)
            if valid.sum() < 10:
                continue

            # Find nadir
            response_valid = response[valid]
            min_idx_in_valid = int(np.argmin(response_valid))
            nadir_g = float(response_valid[min_idx_in_valid])

            # Map back to original index
            valid_indices = np.where(valid)[0]
            nadir_idx = valid_indices[min_idx_in_valid]
            nadir_time_h = nadir_idx / STEPS_PER_HOUR

            # Is this a meal or correction?
            carb_window = slice(max(0, i - 6), min(len(g), i + 7))
            nearby_carbs = carbs[carb_window] if carbs is not None else np.zeros(1)
            is_meal = np.nansum(nearby_carbs) > 2

            entry = {
                'nadir_time_h': nadir_time_h,
                'nadir_g': nadir_g,
                'pre_g': float(pre_g),
                'bolus_size': float(bolus[i]),
                'drop': float(pre_g - nadir_g)
            }

            if is_meal:
                meal_nadirs.append(entry)
            else:
                correction_nadirs.append(entry)

        all_results[name] = {
            'n_meal': len(meal_nadirs),
            'n_correction': len(correction_nadirs),
            'meal_median_nadir_h': float(np.median([e['nadir_time_h'] for e in meal_nadirs]))
                if meal_nadirs else None,
            'correction_median_nadir_h': float(np.median([e['nadir_time_h'] for e in correction_nadirs]))
                if correction_nadirs else None,
            'meal_median_drop': float(np.median([e['drop'] for e in meal_nadirs]))
                if meal_nadirs else None,
            'correction_median_drop': float(np.median([e['drop'] for e in correction_nadirs]))
                if correction_nadirs else None
        }

        m_time = np.median([e['nadir_time_h'] for e in meal_nadirs]) if meal_nadirs else 0
        c_time = np.median([e['nadir_time_h'] for e in correction_nadirs]) if correction_nadirs else 0
        print(f"  {name}: meal nadir={m_time:.1f}h ({len(meal_nadirs)} events), "
              f"correction nadir={c_time:.1f}h ({len(correction_nadirs)} events)")

    with open(f'{EXP_DIR}/exp-2182_nadir.json', 'w') as f:
        json.dump(all_results, f, indent=2, cls=NumpyEncoder)

    if MAKE_FIGS and all_results:
        fig, axes = plt.subplots(1, 3, figsize=(16, 5))
        patient_names = sorted(all_results.keys())
        x = np.arange(len(patient_names))

        meal_times = [all_results[pn].get('meal_median_nadir_h', 0) or 0 for pn in patient_names]
        corr_times = [all_results[pn].get('correction_median_nadir_h', 0) or 0 for pn in patient_names]

        w = 0.3
        axes[0].bar(x - w/2, meal_times, w, label='Meal', color='orange', alpha=0.7)
        axes[0].bar(x + w/2, corr_times, w, label='Correction', color='steelblue', alpha=0.7)
        axes[0].set_xticks(x)
        axes[0].set_xticklabels(patient_names, fontsize=8)
        axes[0].set_ylabel('Median Nadir Time (hours)')
        axes[0].set_title('Bolus-to-Nadir: Meal vs Correction')
        axes[0].legend(fontsize=8)
        axes[0].grid(True, alpha=0.3, axis='y')

        meal_drops = [all_results[pn].get('meal_median_drop', 0) or 0 for pn in patient_names]
        corr_drops = [all_results[pn].get('correction_median_drop', 0) or 0 for pn in patient_names]
        axes[1].bar(x - w/2, meal_drops, w, label='Meal', color='orange', alpha=0.7)
        axes[1].bar(x + w/2, corr_drops, w, label='Correction', color='steelblue', alpha=0.7)
        axes[1].set_xticks(x)
        axes[1].set_xticklabels(patient_names, fontsize=8)
        axes[1].set_ylabel('Median Glucose Drop (mg/dL)')
        axes[1].set_title('Glucose Drop by Bolus Type')
        axes[1].legend(fontsize=8)
        axes[1].grid(True, alpha=0.3, axis='y')

        # Panel 3: Event counts
        meal_n = [all_results[pn]['n_meal'] for pn in patient_names]
        corr_n = [all_results[pn]['n_correction'] for pn in patient_names]
        axes[2].bar(x - w/2, meal_n, w, label='Meal', color='orange', alpha=0.7)
        axes[2].bar(x + w/2, corr_n, w, label='Correction', color='steelblue', alpha=0.7)
        axes[2].set_xticks(x)
        axes[2].set_xticklabels(patient_names, fontsize=8)
        axes[2].set_ylabel('Number of Events')
        axes[2].set_title('Bolus Event Counts')
        axes[2].legend(fontsize=8)
        axes[2].grid(True, alpha=0.3, axis='y')

        plt.tight_layout()
        plt.savefig(f'{FIG_DIR}/pk-fig02-nadir.png', dpi=150)
        plt.close()
        print("  → Saved pk-fig02-nadir.png")

    return all_results


# ── EXP-2183: Insulin Stacking Analysis ─────────────────────────────
def exp_2183_stacking():
    """How often do bolus effects overlap, and what's the consequence?"""
    print("\n═══ EXP-2183: Insulin Stacking Analysis ═══")

    all_results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        bolus = df['bolus'].values if 'bolus' in df.columns else None
        iob = df['iob'].values if 'iob' in df.columns else None

        if bolus is None:
            continue

        # Find bolus events
        bolus_times = []
        for i in range(len(bolus)):
            if not np.isnan(bolus[i]) and bolus[i] > 0.3:
                bolus_times.append(i)

        if len(bolus_times) < 5:
            continue

        # Analyze inter-bolus intervals
        intervals = []
        for idx in range(1, len(bolus_times)):
            gap_h = (bolus_times[idx] - bolus_times[idx - 1]) / STEPS_PER_HOUR
            intervals.append(gap_h)

        stacked_count = sum(1 for gap in intervals if gap < 3)  # <3h = stacking
        rapid_count = sum(1 for gap in intervals if gap < 1)    # <1h = rapid stacking

        # Check IOB at bolus time
        iob_at_bolus = []
        if iob is not None:
            for bt in bolus_times:
                if not np.isnan(iob[bt]):
                    iob_at_bolus.append(float(iob[bt]))

        # Outcome: glucose after stacked vs non-stacked
        stacked_outcomes = []
        non_stacked_outcomes = []

        for idx in range(1, len(bolus_times)):
            bt = bolus_times[idx]
            gap_h = (bt - bolus_times[idx - 1]) / STEPS_PER_HOUR
            is_stacked = gap_h < 3

            # Look at 3h post-bolus glucose
            end = min(bt + 3 * STEPS_PER_HOUR, len(g))
            if end - bt < 2 * STEPS_PER_HOUR:
                continue

            post_g = g[bt:end]
            valid = post_g[~np.isnan(post_g)]
            if len(valid) < 5:
                continue

            nadir = float(np.min(valid))
            had_hypo = nadir < 70

            if is_stacked:
                stacked_outcomes.append({'nadir': nadir, 'hypo': had_hypo})
            else:
                non_stacked_outcomes.append({'nadir': nadir, 'hypo': had_hypo})

        stacked_hypo_rate = (np.mean([o['hypo'] for o in stacked_outcomes])
                             if stacked_outcomes else 0)
        non_stacked_hypo_rate = (np.mean([o['hypo'] for o in non_stacked_outcomes])
                                  if non_stacked_outcomes else 0)

        all_results[name] = {
            'n_boluses': len(bolus_times),
            'stacked_count': stacked_count,
            'stacked_pct': stacked_count / len(intervals) * 100 if intervals else 0,
            'rapid_count': rapid_count,
            'rapid_pct': rapid_count / len(intervals) * 100 if intervals else 0,
            'median_interval_h': float(np.median(intervals)),
            'mean_iob_at_bolus': float(np.mean(iob_at_bolus)) if iob_at_bolus else None,
            'stacked_hypo_rate': float(stacked_hypo_rate) * 100,
            'non_stacked_hypo_rate': float(non_stacked_hypo_rate) * 100,
            'hypo_risk_ratio': (float(stacked_hypo_rate / non_stacked_hypo_rate)
                                if non_stacked_hypo_rate > 0 else None)
        }

        print(f"  {name}: {len(bolus_times)} boluses, "
              f"stacked={stacked_count} ({stacked_count*100//max(1,len(intervals))}%), "
              f"stacked_hypo={stacked_hypo_rate*100:.0f}% vs "
              f"non_stacked={non_stacked_hypo_rate*100:.0f}%")

    with open(f'{EXP_DIR}/exp-2183_stacking.json', 'w') as f:
        json.dump(all_results, f, indent=2, cls=NumpyEncoder)

    if MAKE_FIGS and all_results:
        fig, axes = plt.subplots(1, 3, figsize=(16, 5))
        patient_names = sorted(all_results.keys())
        x = np.arange(len(patient_names))

        stacked_pcts = [all_results[pn]['stacked_pct'] for pn in patient_names]
        axes[0].bar(patient_names, stacked_pcts, color='coral', alpha=0.7)
        axes[0].set_ylabel('% Boluses Stacked (<3h apart)')
        axes[0].set_title('Insulin Stacking Frequency')
        axes[0].tick_params(axis='x', labelsize=8)
        axes[0].grid(True, alpha=0.3, axis='y')

        s_hypo = [all_results[pn]['stacked_hypo_rate'] for pn in patient_names]
        ns_hypo = [all_results[pn]['non_stacked_hypo_rate'] for pn in patient_names]
        w = 0.3
        axes[1].bar(x - w/2, s_hypo, w, label='Stacked', color='red', alpha=0.7)
        axes[1].bar(x + w/2, ns_hypo, w, label='Non-stacked', color='green', alpha=0.7)
        axes[1].set_xticks(x)
        axes[1].set_xticklabels(patient_names, fontsize=8)
        axes[1].set_ylabel('Hypo Rate (%)')
        axes[1].set_title('Hypo Rate: Stacked vs Non-stacked')
        axes[1].legend(fontsize=8)
        axes[1].grid(True, alpha=0.3, axis='y')

        intervals = [all_results[pn]['median_interval_h'] for pn in patient_names]
        axes[2].bar(patient_names, intervals, color='steelblue', alpha=0.7)
        axes[2].axhline(y=3, color='red', linestyle='--', alpha=0.3, label='Stacking threshold')
        axes[2].set_ylabel('Median Inter-bolus Interval (hours)')
        axes[2].set_title('Bolus Spacing')
        axes[2].legend(fontsize=8)
        axes[2].tick_params(axis='x', labelsize=8)
        axes[2].grid(True, alpha=0.3, axis='y')

        plt.tight_layout()
        plt.savefig(f'{FIG_DIR}/pk-fig03-stacking.png', dpi=150)
        plt.close()
        print("  → Saved pk-fig03-stacking.png")

    return all_results


# ── EXP-2184: Correction Bolus Effectiveness ───────────────────────
def exp_2184_correction_effectiveness():
    """Does correction actually achieve target glucose?"""
    print("\n═══ EXP-2184: Correction Bolus Effectiveness ═══")

    all_results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        bolus = df['bolus'].values if 'bolus' in df.columns else None
        carbs = df['carbs'].values if 'carbs' in df.columns else None

        if bolus is None:
            continue

        isf_schedule = df.attrs.get('isf_schedule', [])
        if not isf_schedule:
            continue

        corrections = []
        for i in range(len(bolus)):
            if np.isnan(bolus[i]) or bolus[i] < 0.3:
                continue

            carb_window = slice(max(0, i - 6), min(len(g), i + 7))
            nearby_carbs = carbs[carb_window] if carbs is not None else np.zeros(1)
            if np.nansum(nearby_carbs) > 2:
                continue

            pre_g = g[i] if not np.isnan(g[i]) else np.nan
            if np.isnan(pre_g) or pre_g < 150:  # Only corrections from high glucose
                continue

            # Expected drop
            hour = (i % STEPS_PER_DAY) / STEPS_PER_HOUR
            isf = get_profile_value(isf_schedule, hour)
            if isf is None:
                continue
            if isf < 15:
                isf *= 18.0182

            expected_drop = bolus[i] * isf

            # Actual glucose at 3h post
            t3h = i + 3 * STEPS_PER_HOUR
            if t3h >= len(g):
                continue
            post_g = g[t3h] if not np.isnan(g[t3h]) else np.nan
            if np.isnan(post_g):
                continue

            actual_drop = pre_g - post_g

            corrections.append({
                'pre_g': float(pre_g),
                'post_g': float(post_g),
                'bolus': float(bolus[i]),
                'expected_drop': float(expected_drop),
                'actual_drop': float(actual_drop),
                'ratio': float(actual_drop / expected_drop) if expected_drop > 0 else 0,
                'overcorrected': post_g < 70,
                'undercorrected': post_g > 180
            })

        if len(corrections) < 3:
            all_results[name] = {'n_corrections': len(corrections)}
            print(f"  {name}: only {len(corrections)} qualifying corrections")
            continue

        ratios = [c['ratio'] for c in corrections]
        overcorrected = sum(1 for c in corrections if c['overcorrected'])
        undercorrected = sum(1 for c in corrections if c['undercorrected'])
        on_target = len(corrections) - overcorrected - undercorrected

        all_results[name] = {
            'n_corrections': len(corrections),
            'mean_ratio': float(np.mean(ratios)),
            'median_ratio': float(np.median(ratios)),
            'overcorrected_pct': overcorrected / len(corrections) * 100,
            'undercorrected_pct': undercorrected / len(corrections) * 100,
            'on_target_pct': on_target / len(corrections) * 100,
            'mean_expected_drop': float(np.mean([c['expected_drop'] for c in corrections])),
            'mean_actual_drop': float(np.mean([c['actual_drop'] for c in corrections]))
        }

        print(f"  {name}: {len(corrections)} corrections, "
              f"actual/expected={np.median(ratios):.2f}×, "
              f"over={overcorrected*100//len(corrections)}% "
              f"under={undercorrected*100//len(corrections)}% "
              f"target={on_target*100//len(corrections)}%")

    with open(f'{EXP_DIR}/exp-2184_correction.json', 'w') as f:
        json.dump(all_results, f, indent=2, cls=NumpyEncoder)

    if MAKE_FIGS and all_results:
        fig, axes = plt.subplots(1, 3, figsize=(16, 5))
        patient_names = sorted([pn for pn in all_results if all_results[pn].get('mean_ratio')])

        if patient_names:
            ratios = [all_results[pn]['median_ratio'] for pn in patient_names]
            colors_r = ['red' if r > 1.5 else 'orange' if r > 1.2 else 'green'
                        if 0.8 <= r <= 1.2 else 'blue' for r in ratios]
            axes[0].bar(patient_names, ratios, color=colors_r, alpha=0.7)
            axes[0].axhline(y=1, color='black', linestyle='--', alpha=0.5)
            axes[0].set_ylabel('Actual / Expected Drop')
            axes[0].set_title('Correction Effectiveness Ratio')
            axes[0].tick_params(axis='x', labelsize=8)
            axes[0].grid(True, alpha=0.3, axis='y')

            over_pcts = [all_results[pn]['overcorrected_pct'] for pn in patient_names]
            under_pcts = [all_results[pn]['undercorrected_pct'] for pn in patient_names]
            target_pcts = [all_results[pn]['on_target_pct'] for pn in patient_names]
            x = np.arange(len(patient_names))
            bottom1 = np.zeros(len(patient_names))
            axes[1].bar(patient_names, target_pcts, label='On target', color='green', alpha=0.7)
            bottom1 += target_pcts
            axes[1].bar(patient_names, under_pcts, bottom=bottom1, label='Under', color='orange', alpha=0.7)
            bottom1 = np.array(bottom1) + np.array(under_pcts)
            axes[1].bar(patient_names, over_pcts, bottom=bottom1, label='Over (hypo)', color='red', alpha=0.7)
            axes[1].set_ylabel('% of Corrections')
            axes[1].set_title('Correction Outcomes')
            axes[1].legend(fontsize=8)
            axes[1].tick_params(axis='x', labelsize=8)

            exp_drops = [all_results[pn]['mean_expected_drop'] for pn in patient_names]
            act_drops = [all_results[pn]['mean_actual_drop'] for pn in patient_names]
            w = 0.3
            axes[2].bar(x - w/2, exp_drops, w, label='Expected', color='gray', alpha=0.7)
            axes[2].bar(x + w/2, act_drops, w, label='Actual', color='steelblue', alpha=0.7)
            axes[2].set_xticks(x)
            axes[2].set_xticklabels(patient_names, fontsize=8)
            axes[2].set_ylabel('Mean Glucose Drop (mg/dL)')
            axes[2].set_title('Expected vs Actual Correction')
            axes[2].legend(fontsize=8)
            axes[2].grid(True, alpha=0.3, axis='y')

        plt.tight_layout()
        plt.savefig(f'{FIG_DIR}/pk-fig04-correction.png', dpi=150)
        plt.close()
        print("  → Saved pk-fig04-correction.png")

    return all_results


# ── EXP-2185: Meal Bolus Timing ─────────────────────────────────────
def exp_2185_meal_timing():
    """Pre-bolus benefit quantification."""
    print("\n═══ EXP-2185: Meal Bolus Timing Optimization ═══")

    all_results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        bolus = df['bolus'].values if 'bolus' in df.columns else None
        carbs = df['carbs'].values if 'carbs' in df.columns else None

        if bolus is None or carbs is None:
            continue

        meals = []
        for i in range(len(carbs)):
            if np.isnan(carbs[i]) or carbs[i] < 10:
                continue

            # Find nearest bolus within ±60min
            search_start = max(0, i - 12)
            search_end = min(len(bolus), i + 13)
            bolus_window = bolus[search_start:search_end]

            bolus_idx = None
            for bi in range(len(bolus_window)):
                if not np.isnan(bolus_window[bi]) and bolus_window[bi] > 0.3:
                    bolus_idx = search_start + bi
                    break

            if bolus_idx is None:
                continue

            # Timing: negative = pre-bolus, positive = bolus after carbs
            timing_min = (bolus_idx - i) * 5  # minutes

            # Post-meal peak
            peak_window = g[i:min(i + 36, len(g))]  # 3 hours
            valid = peak_window[~np.isnan(peak_window)]
            if len(valid) < 10:
                continue

            pre_g = g[i] if not np.isnan(g[i]) else np.nan
            if np.isnan(pre_g):
                continue

            peak = float(np.max(valid))
            spike = peak - pre_g

            meals.append({
                'timing_min': timing_min,
                'spike': float(spike),
                'peak': peak,
                'pre_g': float(pre_g),
                'carbs': float(carbs[i])
            })

        if len(meals) < 10:
            continue

        # Group by timing
        pre_bolus = [m for m in meals if m['timing_min'] < -5]
        concurrent = [m for m in meals if -5 <= m['timing_min'] <= 5]
        late_bolus = [m for m in meals if m['timing_min'] > 5]

        all_results[name] = {
            'n_meals': len(meals),
            'n_pre_bolus': len(pre_bolus),
            'n_concurrent': len(concurrent),
            'n_late_bolus': len(late_bolus),
            'pre_bolus_spike': float(np.median([m['spike'] for m in pre_bolus])) if pre_bolus else None,
            'concurrent_spike': float(np.median([m['spike'] for m in concurrent])) if concurrent else None,
            'late_bolus_spike': float(np.median([m['spike'] for m in late_bolus])) if late_bolus else None,
            'pre_bolus_benefit': (float(np.median([m['spike'] for m in late_bolus]) -
                                        np.median([m['spike'] for m in pre_bolus]))
                                  if pre_bolus and late_bolus else None)
        }

        pb_spike = np.median([m['spike'] for m in pre_bolus]) if pre_bolus else 0
        lb_spike = np.median([m['spike'] for m in late_bolus]) if late_bolus else 0
        print(f"  {name}: {len(meals)} meals, pre-bolus spike={pb_spike:.0f} "
              f"vs late={lb_spike:.0f} mg/dL "
              f"(n_pre={len(pre_bolus)}, n_late={len(late_bolus)})")

    with open(f'{EXP_DIR}/exp-2185_timing.json', 'w') as f:
        json.dump(all_results, f, indent=2, cls=NumpyEncoder)

    if MAKE_FIGS and all_results:
        fig, axes = plt.subplots(1, 3, figsize=(16, 5))
        patient_names = sorted(all_results.keys())
        x = np.arange(len(patient_names))

        pb = [all_results[pn].get('pre_bolus_spike', 0) or 0 for pn in patient_names]
        conc = [all_results[pn].get('concurrent_spike', 0) or 0 for pn in patient_names]
        lb = [all_results[pn].get('late_bolus_spike', 0) or 0 for pn in patient_names]
        w = 0.25
        axes[0].bar(x - w, pb, w, label='Pre-bolus', color='green', alpha=0.7)
        axes[0].bar(x, conc, w, label='Concurrent', color='orange', alpha=0.7)
        axes[0].bar(x + w, lb, w, label='Late bolus', color='red', alpha=0.7)
        axes[0].set_xticks(x)
        axes[0].set_xticklabels(patient_names, fontsize=8)
        axes[0].set_ylabel('Median Post-Meal Spike (mg/dL)')
        axes[0].set_title('Spike by Bolus Timing')
        axes[0].legend(fontsize=8)
        axes[0].grid(True, alpha=0.3, axis='y')

        benefit = [all_results[pn].get('pre_bolus_benefit', 0) or 0 for pn in patient_names]
        colors_b = ['green' if b > 10 else 'gray' for b in benefit]
        axes[1].bar(patient_names, benefit, color=colors_b, alpha=0.7)
        axes[1].set_ylabel('Spike Reduction (mg/dL)')
        axes[1].set_title('Pre-bolus Benefit')
        axes[1].tick_params(axis='x', labelsize=8)
        axes[1].grid(True, alpha=0.3, axis='y')

        counts = [(all_results[pn]['n_pre_bolus'], all_results[pn]['n_concurrent'],
                    all_results[pn]['n_late_bolus']) for pn in patient_names]
        axes[2].bar(x - w, [c[0] for c in counts], w, label='Pre', color='green', alpha=0.7)
        axes[2].bar(x, [c[1] for c in counts], w, label='Concurrent', color='orange', alpha=0.7)
        axes[2].bar(x + w, [c[2] for c in counts], w, label='Late', color='red', alpha=0.7)
        axes[2].set_xticks(x)
        axes[2].set_xticklabels(patient_names, fontsize=8)
        axes[2].set_ylabel('Count')
        axes[2].set_title('Bolus Timing Distribution')
        axes[2].legend(fontsize=8)
        axes[2].grid(True, alpha=0.3, axis='y')

        plt.tight_layout()
        plt.savefig(f'{FIG_DIR}/pk-fig05-timing.png', dpi=150)
        plt.close()
        print("  → Saved pk-fig05-timing.png")

    return all_results


# ── EXP-2186: IOB Decay Curve ───────────────────────────────────────
def exp_2186_iob_decay():
    """Actual vs model IOB decay after bolus."""
    print("\n═══ EXP-2186: IOB Decay Curve Analysis ═══")

    all_results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        iob = df['iob'].values if 'iob' in df.columns else None
        bolus = df['bolus'].values if 'bolus' in df.columns else None

        if iob is None or bolus is None:
            continue

        # Find isolated boluses and track IOB decay
        decay_curves = []
        for i in range(len(bolus)):
            if np.isnan(bolus[i]) or bolus[i] < 1.0:
                continue

            # No other boluses within 4h
            window = bolus[max(0, i-48):i]
            if np.nansum(window) > 0.5:
                continue
            window_after = bolus[i+1:min(i+48, len(bolus))]
            if np.nansum(window_after) > 0.5:
                continue

            # Track IOB for 6h
            end = min(i + 72, len(iob))
            iob_curve = iob[i:end]
            valid = ~np.isnan(iob_curve)
            if valid.sum() < 20:
                continue

            # Normalize to peak IOB
            peak_iob = float(np.nanmax(iob_curve[:6]))  # Peak within 30 min
            if peak_iob < 0.5:
                continue

            normalized = iob_curve / peak_iob
            decay_curves.append({
                'bolus': float(bolus[i]),
                'peak_iob': peak_iob,
                'curve': normalized.tolist(),
                'valid': valid.tolist()
            })

        if len(decay_curves) < 3:
            all_results[name] = {'n_curves': len(decay_curves)}
            print(f"  {name}: only {len(decay_curves)} isolated boluses for IOB tracking")
            continue

        # Average decay curve
        max_len = max(len(c['curve']) for c in decay_curves)
        avg_curve = np.zeros(max_len)
        counts = np.zeros(max_len)
        for c in decay_curves:
            curve = np.array(c['curve'])
            valid = np.array(c['valid'])
            for t in range(len(curve)):
                if valid[t]:
                    avg_curve[t] += curve[t]
                    counts[t] += 1

        for t in range(max_len):
            if counts[t] > 0:
                avg_curve[t] /= counts[t]

        # Find when IOB reaches 10% (effective DIA)
        dia_10pct_idx = None
        for t in range(len(avg_curve)):
            if counts[t] > 0 and avg_curve[t] < 0.1:
                dia_10pct_idx = t
                break
        dia_10pct_h = dia_10pct_idx / STEPS_PER_HOUR if dia_10pct_idx else None

        # Find when IOB reaches 50% (half-life)
        half_life_idx = None
        for t in range(len(avg_curve)):
            if counts[t] > 0 and avg_curve[t] < 0.5:
                half_life_idx = t
                break
        half_life_h = half_life_idx / STEPS_PER_HOUR if half_life_idx else None

        all_results[name] = {
            'n_curves': len(decay_curves),
            'avg_curve': avg_curve[:72].tolist(),  # 6h max
            'dia_10pct_h': dia_10pct_h,
            'half_life_h': half_life_h,
            'mean_peak_iob': float(np.mean([c['peak_iob'] for c in decay_curves]))
        }

        print(f"  {name}: {len(decay_curves)} curves, "
              f"half-life={half_life_h:.1f}h" if half_life_h else "",
              f"DIA(10%)={dia_10pct_h:.1f}h" if dia_10pct_h else "")

    with open(f'{EXP_DIR}/exp-2186_iob_decay.json', 'w') as f:
        json.dump(all_results, f, indent=2, cls=NumpyEncoder)

    if MAKE_FIGS and all_results:
        fig, axes = plt.subplots(1, 3, figsize=(16, 5))

        patient_names = sorted([pn for pn in all_results if all_results[pn].get('avg_curve')])

        if patient_names:
            for pn in patient_names:
                curve = all_results[pn]['avg_curve']
                hours = [t / STEPS_PER_HOUR for t in range(len(curve))]
                axes[0].plot(hours, curve, '-', label=pn, alpha=0.7)
            axes[0].axhline(y=0.1, color='red', linestyle='--', alpha=0.3, label='10% threshold')
            axes[0].axhline(y=0.5, color='orange', linestyle='--', alpha=0.3, label='50% (half-life)')
            axes[0].set_xlabel('Hours After Bolus')
            axes[0].set_ylabel('Normalized IOB')
            axes[0].set_title('IOB Decay Curves')
            axes[0].legend(fontsize=7, ncol=2)
            axes[0].grid(True, alpha=0.3)

            half_lives = [all_results[pn].get('half_life_h', 0) or 0 for pn in patient_names]
            axes[1].bar(patient_names, half_lives, color='steelblue', alpha=0.7)
            axes[1].set_ylabel('IOB Half-Life (hours)')
            axes[1].set_title('Insulin Half-Life')
            axes[1].tick_params(axis='x', labelsize=8)
            axes[1].grid(True, alpha=0.3, axis='y')

            dias = [all_results[pn].get('dia_10pct_h', 0) or 0 for pn in patient_names]
            axes[2].bar(patient_names, dias, color='coral', alpha=0.7)
            axes[2].axhline(y=5, color='gray', linestyle='--', alpha=0.5, label='Typical DIA=5h')
            axes[2].set_ylabel('Effective DIA (hours to 10%)')
            axes[2].set_title('Duration of Insulin Action')
            axes[2].legend(fontsize=8)
            axes[2].tick_params(axis='x', labelsize=8)
            axes[2].grid(True, alpha=0.3, axis='y')

        plt.tight_layout()
        plt.savefig(f'{FIG_DIR}/pk-fig06-iob.png', dpi=150)
        plt.close()
        print("  → Saved pk-fig06-iob.png")

    return all_results


# ── EXP-2187: Circadian ISF Variation ───────────────────────────────
def exp_2187_circadian_isf():
    """Insulin sensitivity by time of day."""
    print("\n═══ EXP-2187: Circadian ISF Variation ═══")

    all_results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        bolus = df['bolus'].values if 'bolus' in df.columns else None
        carbs = df['carbs'].values if 'carbs' in df.columns else None

        if bolus is None:
            continue

        # Compute effective ISF for each bolus by time of day
        hourly_isfs = {h: [] for h in range(24)}

        for i in range(len(bolus)):
            if np.isnan(bolus[i]) or bolus[i] < 0.5:
                continue

            # Correction only (no carbs)
            carb_window = slice(max(0, i - 6), min(len(g), i + 7))
            nearby_carbs = carbs[carb_window] if carbs is not None else np.zeros(1)
            if np.nansum(nearby_carbs) > 2:
                continue

            pre_g = g[i] if not np.isnan(g[i]) else np.nan
            if np.isnan(pre_g) or pre_g < 120:
                continue

            # Post-bolus glucose at 3h
            t3h = i + 3 * STEPS_PER_HOUR
            if t3h >= len(g):
                continue
            post_g = g[t3h]
            if np.isnan(post_g):
                continue

            drop = pre_g - post_g
            if drop < 0:
                continue  # Glucose rose — not a correction response

            effective_isf = drop / bolus[i]
            hour = (i % STEPS_PER_DAY) // STEPS_PER_HOUR

            hourly_isfs[hour].append(effective_isf)

        # Summarize
        hourly_summary = {}
        for h in range(24):
            if len(hourly_isfs[h]) >= 2:
                hourly_summary[h] = {
                    'mean_isf': float(np.mean(hourly_isfs[h])),
                    'median_isf': float(np.median(hourly_isfs[h])),
                    'n': len(hourly_isfs[h])
                }

        if len(hourly_summary) < 6:
            all_results[name] = {'n_hours': len(hourly_summary)}
            print(f"  {name}: only {len(hourly_summary)} hours with data")
            continue

        isf_values = [hourly_summary[h]['median_isf'] for h in sorted(hourly_summary.keys())]
        circadian_ratio = max(isf_values) / min(isf_values) if min(isf_values) > 0 else 1

        # Morning vs afternoon
        morning = [hourly_summary[h]['median_isf'] for h in range(6, 12) if h in hourly_summary]
        afternoon = [hourly_summary[h]['median_isf'] for h in range(12, 18) if h in hourly_summary]
        evening = [hourly_summary[h]['median_isf'] for h in range(18, 24) if h in hourly_summary]

        all_results[name] = {
            'hourly': hourly_summary,
            'circadian_ratio': float(circadian_ratio),
            'morning_isf': float(np.mean(morning)) if morning else None,
            'afternoon_isf': float(np.mean(afternoon)) if afternoon else None,
            'evening_isf': float(np.mean(evening)) if evening else None,
            'n_hours': len(hourly_summary)
        }

        m_isf = np.mean(morning) if morning else 0
        a_isf = np.mean(afternoon) if afternoon else 0
        e_isf = np.mean(evening) if evening else 0
        print(f"  {name}: circadian ratio={circadian_ratio:.1f}×, "
              f"morning={m_isf:.0f} afternoon={a_isf:.0f} evening={e_isf:.0f}")

    with open(f'{EXP_DIR}/exp-2187_circadian_isf.json', 'w') as f:
        json.dump(all_results, f, indent=2, cls=NumpyEncoder)

    if MAKE_FIGS and all_results:
        fig, axes = plt.subplots(1, 3, figsize=(16, 5))
        patient_names = sorted([pn for pn in all_results if all_results[pn].get('hourly')])

        if patient_names:
            for pn in patient_names:
                hourly = all_results[pn]['hourly']
                hours = sorted([int(h) for h in hourly.keys()])
                isfs = [hourly[h]['median_isf'] for h in hours]
                axes[0].plot(hours, isfs, '-o', label=pn, markersize=3, alpha=0.7)
            axes[0].set_xlabel('Hour of Day')
            axes[0].set_ylabel('Effective ISF (mg/dL per U)')
            axes[0].set_title('Circadian ISF Variation')
            axes[0].legend(fontsize=7, ncol=2)
            axes[0].set_xticks(range(0, 24, 3))
            axes[0].grid(True, alpha=0.3)

            ratios = [all_results[pn]['circadian_ratio'] for pn in patient_names]
            axes[1].bar(patient_names, ratios, color='steelblue', alpha=0.7)
            axes[1].axhline(y=1, color='black', linestyle='--', alpha=0.3)
            axes[1].set_ylabel('Max/Min ISF Ratio')
            axes[1].set_title('Circadian ISF Range')
            axes[1].tick_params(axis='x', labelsize=8)
            axes[1].grid(True, alpha=0.3, axis='y')

            x = np.arange(len(patient_names))
            m = [all_results[pn].get('morning_isf', 0) or 0 for pn in patient_names]
            a = [all_results[pn].get('afternoon_isf', 0) or 0 for pn in patient_names]
            e = [all_results[pn].get('evening_isf', 0) or 0 for pn in patient_names]
            w = 0.25
            axes[2].bar(x - w, m, w, label='Morning', color='orange', alpha=0.7)
            axes[2].bar(x, a, w, label='Afternoon', color='green', alpha=0.7)
            axes[2].bar(x + w, e, w, label='Evening', color='purple', alpha=0.7)
            axes[2].set_xticks(x)
            axes[2].set_xticklabels(patient_names, fontsize=8)
            axes[2].set_ylabel('Mean ISF (mg/dL per U)')
            axes[2].set_title('ISF by Time Period')
            axes[2].legend(fontsize=8)
            axes[2].grid(True, alpha=0.3, axis='y')

        plt.tight_layout()
        plt.savefig(f'{FIG_DIR}/pk-fig07-circadian-isf.png', dpi=150)
        plt.close()
        print("  → Saved pk-fig07-circadian-isf.png")

    return all_results


# ── EXP-2188: Integrated PK Recommendations ────────────────────────
def exp_2188_pk_recommendations():
    """Per-patient DIA/timing strategy recommendations."""
    print("\n═══ EXP-2188: Integrated PK Recommendations ═══")

    all_results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        bolus = df['bolus'].values if 'bolus' in df.columns else None
        iob = df['iob'].values if 'iob' in df.columns else None

        if bolus is None:
            continue

        recommendations = []
        pk_profile = {}

        # 1. Bolus frequency
        n_boluses = sum(1 for b in bolus if not np.isnan(b) and b > 0.3)
        n_days = len(g) // STEPS_PER_DAY
        bolus_per_day = n_boluses / max(1, n_days)
        pk_profile['bolus_per_day'] = float(bolus_per_day)

        if bolus_per_day > 8:
            recommendations.append('HIGH_BOLUS_FREQUENCY: Consider consolidating boluses')
        elif bolus_per_day < 2:
            recommendations.append('LOW_BOLUS_FREQUENCY: May be missing meal boluses')

        # 2. Total daily insulin
        daily_bolus = float(np.nansum(bolus)) / max(1, n_days)
        pk_profile['mean_daily_bolus'] = daily_bolus

        # 3. Bolus size distribution
        bolus_sizes = bolus[~np.isnan(bolus) & (bolus > 0.3)]
        if len(bolus_sizes) > 0:
            pk_profile['mean_bolus_size'] = float(np.mean(bolus_sizes))
            pk_profile['median_bolus_size'] = float(np.median(bolus_sizes))
            pk_profile['max_bolus_size'] = float(np.max(bolus_sizes))

            if np.max(bolus_sizes) > 10:
                recommendations.append('LARGE_BOLUSES: Max bolus > 10U, consider splitting')

        # 4. IOB patterns
        if iob is not None:
            iob_valid = iob[~np.isnan(iob)]
            if len(iob_valid) > 0:
                pk_profile['mean_iob'] = float(np.mean(iob_valid))
                pk_profile['max_iob'] = float(np.max(iob_valid))
                pk_profile['high_iob_pct'] = float(np.mean(iob_valid > 5) * 100)

                if np.mean(iob_valid > 5) > 0.1:
                    recommendations.append('HIGH_IOB_FREQUENT: IOB >5U more than 10% of time')

        # 5. Post-bolus hypo check
        hypo_after_bolus = 0
        total_checks = 0
        for i in range(len(bolus)):
            if np.isnan(bolus[i]) or bolus[i] < 0.5:
                continue
            window = g[i:min(i + 4 * STEPS_PER_HOUR, len(g))]
            valid = window[~np.isnan(window)]
            if len(valid) > 5:
                total_checks += 1
                if np.min(valid) < 70:
                    hypo_after_bolus += 1

        if total_checks > 0:
            post_bolus_hypo_rate = hypo_after_bolus / total_checks
            pk_profile['post_bolus_hypo_rate'] = float(post_bolus_hypo_rate) * 100

            if post_bolus_hypo_rate > 0.3:
                recommendations.append('POST_BOLUS_HYPO: >30% of boluses cause hypo in 4h')

        # Overall priority
        if any('SAFETY' in r or 'POST_BOLUS_HYPO' in r for r in recommendations):
            priority = 'SAFETY'
        elif len(recommendations) > 2:
            priority = 'OPTIMIZE'
        elif recommendations:
            priority = 'FINE_TUNE'
        else:
            priority = 'MAINTAIN'

        all_results[name] = {
            'pk_profile': pk_profile,
            'recommendations': recommendations,
            'priority': priority,
            'n_recommendations': len(recommendations)
        }

        print(f"  {name}: [{priority}] {bolus_per_day:.1f} bolus/day, "
              f"{daily_bolus:.1f}U/day, {len(recommendations)} recommendations")

    with open(f'{EXP_DIR}/exp-2188_pk_recs.json', 'w') as f:
        json.dump(all_results, f, indent=2, cls=NumpyEncoder)

    if MAKE_FIGS and all_results:
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        patient_names = sorted(all_results.keys())

        bpd = [all_results[pn]['pk_profile']['bolus_per_day'] for pn in patient_names]
        axes[0, 0].bar(patient_names, bpd, color='steelblue', alpha=0.7)
        axes[0, 0].set_ylabel('Boluses per Day')
        axes[0, 0].set_title('Bolus Frequency')
        axes[0, 0].tick_params(axis='x', labelsize=8)
        axes[0, 0].grid(True, alpha=0.3, axis='y')

        ddi = [all_results[pn]['pk_profile']['mean_daily_bolus'] for pn in patient_names]
        axes[0, 1].bar(patient_names, ddi, color='coral', alpha=0.7)
        axes[0, 1].set_ylabel('Mean Daily Bolus Insulin (U)')
        axes[0, 1].set_title('Daily Bolus Dose')
        axes[0, 1].tick_params(axis='x', labelsize=8)
        axes[0, 1].grid(True, alpha=0.3, axis='y')

        hypo_rates = [all_results[pn]['pk_profile'].get('post_bolus_hypo_rate', 0)
                      for pn in patient_names]
        colors_h = ['red' if r > 30 else 'orange' if r > 15 else 'green' for r in hypo_rates]
        axes[1, 0].bar(patient_names, hypo_rates, color=colors_h, alpha=0.7)
        axes[1, 0].axhline(y=30, color='red', linestyle='--', alpha=0.3)
        axes[1, 0].set_ylabel('% Boluses Causing Hypo')
        axes[1, 0].set_title('Post-Bolus Hypo Rate')
        axes[1, 0].tick_params(axis='x', labelsize=8)
        axes[1, 0].grid(True, alpha=0.3, axis='y')

        n_recs = [all_results[pn]['n_recommendations'] for pn in patient_names]
        priorities = [all_results[pn]['priority'] for pn in patient_names]
        p_colors = {'SAFETY': 'red', 'OPTIMIZE': 'orange', 'FINE_TUNE': 'yellow',
                     'MAINTAIN': 'green'}
        bar_colors = [p_colors.get(pr, 'gray') for pr in priorities]
        axes[1, 1].bar(patient_names, n_recs, color=bar_colors, alpha=0.7)
        axes[1, 1].set_ylabel('Number of PK Recommendations')
        axes[1, 1].set_title('PK Intervention Priority')
        axes[1, 1].tick_params(axis='x', labelsize=8)
        axes[1, 1].grid(True, alpha=0.3, axis='y')

        plt.tight_layout()
        plt.savefig(f'{FIG_DIR}/pk-fig08-recommendations.png', dpi=150)
        plt.close()
        print("  → Saved pk-fig08-recommendations.png")

    return all_results


# ══════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    print("=" * 60)
    print("EXP-2181–2188: Insulin Pharmacokinetics & DIA Analysis")
    print("=" * 60)

    r1 = exp_2181_dia_estimation()
    r2 = exp_2182_bolus_nadir()
    r3 = exp_2183_stacking()
    r4 = exp_2184_correction_effectiveness()
    r5 = exp_2185_meal_timing()
    r6 = exp_2186_iob_decay()
    r7 = exp_2187_circadian_isf()
    r8 = exp_2188_pk_recommendations()

    print("\n" + "=" * 60)
    n_complete = sum(1 for r in [r1, r2, r3, r4, r5, r6, r7, r8] if r)
    print(f"Results: {n_complete}/8 experiments completed")
    print(f"Figures saved to {FIG_DIR}/pk-fig01–08")
    print("=" * 60)
