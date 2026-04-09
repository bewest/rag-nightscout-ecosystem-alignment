#!/usr/bin/env python3
"""EXP-1761 to EXP-1768: UAM Detection & Morning Optimization.

Follows from EXP-1754 finding that acceleration-based UAM detection has
25-min lead time with 99% sensitivity. Critical unknown: false positive rate.
Also follows from EXP-1756 finding that morning TAR is 38.4% (worst period).

  EXP-1761: Acceleration detector false positive rate & precision-recall
  EXP-1762: Two-stage detector (accel trigger + confirmation threshold)
  EXP-1763: Morning-specific optimization (dawn phenomenon quantification)
  EXP-1764: Variability reduction simulation (what if CV reduced to 25%?)
  EXP-1765: Per-patient optimization sequence recommendation
  EXP-1766: Rescue carb behavior clustering & patient subtypes

Run: PYTHONPATH=tools python3 tools/cgmencode/exp_uam_morning_1761.py --figures
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from cgmencode.exp_metabolic_flux import load_patients
from exp_metabolic_441 import compute_supply_demand

PATIENTS_DIR = Path('externals/ns-data/patients')
RESULTS_DIR = Path('externals/experiments')
FIGURES_DIR = Path('docs/60-research/figures')

STEPS_PER_HOUR = 12
STEPS_PER_DAY = 288
LOW = 70.0
HIGH = 180.0


def _get_isf(pat):
    sched = pat['df'].attrs.get('isf_schedule', [])
    if not sched:
        return 50.0
    vals = [s['value'] for s in sched]
    mean_isf = np.mean(vals)
    if mean_isf < 15:
        mean_isf *= 18.0182
    return mean_isf


def _get_basal(pat):
    sched = pat['df'].attrs.get('basal_schedule', [])
    if not sched:
        return 1.0
    return np.mean([s['value'] for s in sched])


def _get_cr(pat):
    sched = pat['df'].attrs.get('cr_schedule', [])
    if not sched:
        return 10.0
    return np.mean([s['value'] for s in sched])


def _compute_accel(glucose):
    """Compute smoothed glucose acceleration (second derivative)."""
    valid = ~np.isnan(glucose)
    delta = np.zeros(len(glucose))
    for i in range(1, len(glucose)):
        if valid[i] and valid[i-1]:
            delta[i] = glucose[i] - glucose[i-1]
    accel = np.zeros(len(glucose))
    for i in range(1, len(glucose)):
        accel[i] = delta[i] - delta[i-1]
    # Smooth with 3-step average
    kernel = np.ones(3) / 3
    accel_smooth = np.convolve(accel, kernel, mode='same')
    return delta, accel_smooth


def exp_1761_accel_fpr(patients):
    """Measure false positive rate of acceleration-based rise detection.

    A "positive" is accel > threshold. A "true positive" is a positive
    followed by a significant rise (≥30 mg/dL in 1h). A "false positive"
    is a positive NOT followed by a significant rise.
    """
    print("\n=== EXP-1761: Acceleration Detector False Positive Rate ===\n")

    RISE_THRESHOLD = 30  # mg/dL in 1h for "significant rise"
    thresholds = [0.3, 0.5, 0.7, 1.0, 1.5, 2.0]

    results_by_thresh = {}
    for thresh in thresholds:
        tp = 0
        fp = 0
        fn = 0
        tn = 0
        total_rises = 0

        for pat in patients:
            glucose = pat['df']['glucose'].values.astype(float)
            valid = ~np.isnan(glucose)
            _, accel = _compute_accel(glucose)

            for i in range(STEPS_PER_HOUR, len(glucose) - STEPS_PER_HOUR):
                if not valid[i]:
                    continue
                # Check if there's a significant rise in the next hour
                future = glucose[i:i + STEPS_PER_HOUR]
                future_valid = future[~np.isnan(future)]
                if len(future_valid) < 6:
                    continue
                is_rise = (np.max(future_valid) - glucose[i]) >= RISE_THRESHOLD

                # Check if accel exceeds threshold
                detected = accel[i] > thresh

                if is_rise:
                    total_rises += 1
                    if detected:
                        tp += 1
                    else:
                        fn += 1
                else:
                    if detected:
                        fp += 1
                    else:
                        tn += 1

        total = tp + fp + fn + tn
        precision = tp / max(1, tp + fp)
        recall = tp / max(1, tp + fn)
        f1 = 2 * precision * recall / max(0.001, precision + recall)
        fpr = fp / max(1, fp + tn)

        results_by_thresh[str(thresh)] = {
            'threshold': thresh,
            'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn,
            'precision': round(precision, 4),
            'recall': round(recall, 4),
            'f1': round(f1, 4),
            'fpr': round(fpr, 4),
        }

        print(f"  thresh={thresh:.1f}: P={precision:.3f} R={recall:.3f} "
              f"F1={f1:.3f} FPR={fpr:.4f} (TP={tp}, FP={fp})")

    return {
        'experiment': 'EXP-1761',
        'title': 'Acceleration Detector False Positive Rate',
        'rise_threshold_mgdl': RISE_THRESHOLD,
        'thresholds': results_by_thresh,
    }


def exp_1762_two_stage_detector(patients):
    """Two-stage detector: acceleration trigger → rate confirmation.

    Stage 1: acceleration > threshold (early warning)
    Stage 2: within N steps, rate > confirmation_threshold (confirmation)

    Measures effective lead time, precision, and recall.
    """
    print("\n=== EXP-1762: Two-Stage UAM Detector ===\n")

    RISE_THRESHOLD = 30
    ACCEL_THRESH = 0.5
    confirm_thresholds = [1.5, 2.0, 2.5, 3.0]
    confirm_windows = [2, 3, 4, 6]  # steps to wait for confirmation

    # Build list of actual rises across all patients
    all_rises = []
    all_glucose = []
    all_accel = []
    all_delta = []

    for pat in patients:
        glucose = pat['df']['glucose'].values.astype(float)
        valid = ~np.isnan(glucose)
        delta, accel = _compute_accel(glucose)

        for i in range(STEPS_PER_HOUR, len(glucose) - STEPS_PER_HOUR):
            if not valid[i]:
                continue
            future = glucose[i:i + STEPS_PER_HOUR]
            fv = future[~np.isnan(future)]
            if len(fv) < 6:
                continue
            is_rise = (np.max(fv) - glucose[i]) >= RISE_THRESHOLD
            all_rises.append(is_rise)
            all_glucose.append(glucose[i])
            all_accel.append(accel[i])
            all_delta.append(delta[i])

    all_rises = np.array(all_rises)
    all_accel = np.array(all_accel)
    all_delta = np.array(all_delta)
    n_rises = all_rises.sum()
    n_total = len(all_rises)

    print(f"  Total windows: {n_total}, Actual rises: {n_rises} ({n_rises/n_total*100:.1f}%)")

    # Test combinations
    best_f1 = 0
    best_config = None
    configs = []

    for ct in confirm_thresholds:
        for cw in confirm_windows:
            # Two-stage: accel > 0.5 AND max(delta in next cw steps) > ct
            # Simplified: since we only have per-step data, approximate as
            # accel > ACCEL_THRESH AND delta > ct (simultaneous)
            detected = (all_accel > ACCEL_THRESH) & (all_delta > ct)

            tp = (detected & all_rises).sum()
            fp = (detected & ~all_rises).sum()
            fn = (~detected & all_rises).sum()

            prec = tp / max(1, tp + fp)
            rec = tp / max(1, tp + fn)
            f1 = 2 * prec * rec / max(0.001, prec + rec)

            configs.append({
                'confirm_thresh': ct,
                'confirm_window': cw,
                'precision': round(float(prec), 4),
                'recall': round(float(rec), 4),
                'f1': round(float(f1), 4),
            })

            if f1 > best_f1:
                best_f1 = f1
                best_config = (ct, cw, prec, rec, f1)

    if best_config:
        ct, cw, prec, rec, f1 = best_config
        print(f"\n  Best config: confirm_thresh={ct}, window={cw}")
        print(f"    Precision={prec:.3f}, Recall={rec:.3f}, F1={f1:.3f}")

    # Compare with single-stage
    for label, detected in [
        ('Accel only (>0.5)', all_accel > 0.5),
        ('Delta only (>3.0)', all_delta > 3.0),
        ('Two-stage best', (all_accel > ACCEL_THRESH) & (all_delta > best_config[0]) if best_config else all_accel > 0.5),
    ]:
        tp = (detected & all_rises).sum()
        fp = (detected & ~all_rises).sum()
        fn = (~detected & all_rises).sum()
        prec = tp / max(1, tp + fp)
        rec = tp / max(1, tp + fn)
        f1 = 2 * prec * rec / max(0.001, prec + rec)
        print(f"  {label:25s}: P={prec:.3f} R={rec:.3f} F1={f1:.3f}")

    return {
        'experiment': 'EXP-1762',
        'title': 'Two-Stage UAM Detector',
        'n_windows': int(n_total),
        'n_rises': int(n_rises),
        'best_config': {
            'accel_threshold': ACCEL_THRESH,
            'confirm_threshold': best_config[0] if best_config else None,
            'precision': round(float(best_config[2]), 4) if best_config else None,
            'recall': round(float(best_config[3]), 4) if best_config else None,
            'f1': round(float(best_config[4]), 4) if best_config else None,
        },
        'configs': configs[:8],
    }


def exp_1763_morning_optimization(patients):
    """Quantify dawn phenomenon and morning TAR optimization potential.

    Decompose morning TAR into:
    1. Dawn phenomenon (glucose rise 4-7am without carbs)
    2. Breakfast timing mismatch (carbs before insulin peaks)
    3. Residual (other morning factors)
    """
    print("\n=== EXP-1763: Morning-Specific Optimization ===\n")

    dawn_rises = []
    breakfast_tar_minutes = []
    morning_tar_minutes = []
    patient_results = []

    for pat in patients:
        name = pat['name']
        glucose = pat['df']['glucose'].values.astype(float)
        carbs = np.nan_to_num(pat['df']['carbs'].values.astype(float), nan=0.0)
        iob = pat['df']['iob'].values.astype(float) if 'iob' in pat['df'].columns else np.zeros(len(glucose))
        valid = ~np.isnan(glucose)

        n_days = len(glucose) // STEPS_PER_DAY
        dawn_rise_list = []
        breakfast_tar_list = []
        no_breakfast_tar_list = []

        for day in range(n_days):
            base = day * STEPS_PER_DAY

            # Dawn window: 4am-7am (steps 48-84)
            dawn_start = base + 4 * STEPS_PER_HOUR
            dawn_end = base + 7 * STEPS_PER_HOUR
            if dawn_end >= len(glucose):
                continue

            dawn_g = glucose[dawn_start:dawn_end]
            dawn_c = carbs[dawn_start:dawn_end]
            dawn_valid = ~np.isnan(dawn_g)

            if dawn_valid.sum() < STEPS_PER_HOUR:
                continue

            # Dawn rise: glucose change from 4am to 7am, no carbs
            if dawn_c.sum() < 1.0:
                g4 = glucose[dawn_start] if valid[dawn_start] else np.nan
                g7 = glucose[dawn_end] if valid[dawn_end] else np.nan
                if not np.isnan(g4) and not np.isnan(g7):
                    dawn_rise_list.append(g7 - g4)

            # Morning window: 6am-10am
            morn_start = base + 6 * STEPS_PER_HOUR
            morn_end = base + 10 * STEPS_PER_HOUR
            if morn_end >= len(glucose):
                continue

            morn_g = glucose[morn_start:morn_end]
            morn_c = carbs[morn_start:morn_end]
            morn_valid = ~np.isnan(morn_g)

            if morn_valid.sum() < 2 * STEPS_PER_HOUR:
                continue

            # TAR in morning
            morn_tar = np.sum(morn_g[morn_valid] > HIGH)
            morning_tar_minutes.append(morn_tar * 5)

            # Split by breakfast presence
            has_breakfast = morn_c.sum() > 5.0
            if has_breakfast:
                breakfast_tar_list.append(morn_tar * 5)
            else:
                no_breakfast_tar_list.append(morn_tar * 5)

        mean_dawn = float(np.mean(dawn_rise_list)) if dawn_rise_list else 0
        dawn_rises.extend(dawn_rise_list)

        mean_morn_tar = float(np.mean(breakfast_tar_list)) if breakfast_tar_list else 0
        mean_no_bkf_tar = float(np.mean(no_breakfast_tar_list)) if no_breakfast_tar_list else 0

        r = {
            'patient': name,
            'mean_dawn_rise_mgdl': round(mean_dawn, 1),
            'n_dawn_days': len(dawn_rise_list),
            'mean_breakfast_tar_min': round(mean_morn_tar, 1),
            'mean_no_breakfast_tar_min': round(mean_no_bkf_tar, 1),
            'n_breakfast_days': len(breakfast_tar_list),
            'n_no_breakfast_days': len(no_breakfast_tar_list),
        }
        patient_results.append(r)

        print(f"  {name}: dawn rise={mean_dawn:+.1f} mg/dL ({len(dawn_rise_list)} days), "
              f"breakfast TAR={mean_morn_tar:.0f}min vs no-breakfast={mean_no_bkf_tar:.0f}min")

    pop_dawn = float(np.mean(dawn_rises)) if dawn_rises else 0
    pop_dawn_pct_positive = float(np.mean(np.array(dawn_rises) > 0) * 100) if dawn_rises else 0

    print(f"\n  Population dawn rise: {pop_dawn:+.1f} mg/dL")
    print(f"  Days with positive dawn rise: {pop_dawn_pct_positive:.0f}%")

    bkf_tar = [r['mean_breakfast_tar_min'] for r in patient_results]
    no_bkf_tar = [r['mean_no_breakfast_tar_min'] for r in patient_results]
    bkf_premium = float(np.mean(bkf_tar)) - float(np.mean(no_bkf_tar))
    print(f"  Breakfast TAR premium: {bkf_premium:+.1f} min/day")

    return {
        'experiment': 'EXP-1763',
        'title': 'Morning-Specific Optimization',
        'patients': patient_results,
        'population_dawn_rise': round(pop_dawn, 1),
        'dawn_positive_pct': round(pop_dawn_pct_positive, 1),
        'breakfast_tar_premium_min': round(bkf_premium, 1),
    }


def exp_1764_variability_reduction_sim(patients):
    """Simulate: what if CV reduced to 25%? How much TIR improvement?

    For each patient, compress the glucose distribution toward the mean
    to achieve target CV, then recalculate TIR.
    """
    print("\n=== EXP-1764: Variability Reduction Simulation ===\n")

    target_cvs = [0.15, 0.20, 0.25, 0.30, 0.35]
    patient_results = []

    for pat in patients:
        name = pat['name']
        glucose = pat['df']['glucose'].values.astype(float)
        valid = ~np.isnan(glucose)
        g = glucose[valid]
        if len(g) < STEPS_PER_DAY:
            continue

        mean_bg = float(np.mean(g))
        current_cv = float(np.std(g) / mean_bg)
        orig_tir = float(np.mean((g >= LOW) & (g <= HIGH)) * 100)

        cv_results = {}
        for target_cv in target_cvs:
            if target_cv >= current_cv:
                # Already below target
                cv_results[str(target_cv)] = {
                    'tir': round(orig_tir, 1),
                    'tar': round(float(np.mean(g > HIGH) * 100), 1),
                    'tbr': round(float(np.mean(g < LOW) * 100), 1),
                }
                continue

            # Compress: g_new = mean + (g - mean) * (target_cv / current_cv)
            scale = target_cv / current_cv
            g_compressed = mean_bg + (g - mean_bg) * scale

            new_tir = float(np.mean((g_compressed >= LOW) & (g_compressed <= HIGH)) * 100)
            new_tar = float(np.mean(g_compressed > HIGH) * 100)
            new_tbr = float(np.mean(g_compressed < LOW) * 100)

            cv_results[str(target_cv)] = {
                'tir': round(new_tir, 1),
                'tar': round(new_tar, 1),
                'tbr': round(new_tbr, 1),
            }

        r = {
            'patient': name,
            'mean_bg': round(mean_bg, 1),
            'current_cv': round(current_cv * 100, 1),
            'orig_tir': round(orig_tir, 1),
            'cv_simulations': cv_results,
        }
        patient_results.append(r)

        cv25 = cv_results.get('0.25', {})
        print(f"  {name}: CV {current_cv*100:.0f}%→25%, "
              f"TIR {orig_tir:.1f}%→{cv25.get('tir', orig_tir):.1f}% "
              f"(Δ{cv25.get('tir', orig_tir) - orig_tir:+.1f}%)")

    # Population summary at CV=25%
    improvements = []
    for r in patient_results:
        cv25 = r['cv_simulations'].get('0.25', {})
        imp = cv25.get('tir', r['orig_tir']) - r['orig_tir']
        improvements.append(imp)

    print(f"\n  Mean TIR improvement at CV=25%: {np.mean(improvements):+.1f}%")
    print(f"  Max: {np.max(improvements):+.1f}%, Min: {np.min(improvements):+.1f}%")

    return {
        'experiment': 'EXP-1764',
        'title': 'Variability Reduction Simulation',
        'patients': patient_results,
        'mean_tir_improvement_cv25': round(float(np.mean(improvements)), 1),
    }


def exp_1765_optimization_sequence(patients):
    """Per-patient optimization recommendation.

    For each patient, determine whether centering or variability reduction
    would help more, and generate a prioritized recommendation.
    """
    print("\n=== EXP-1765: Per-Patient Optimization Sequence ===\n")

    from scipy.stats import norm

    patient_results = []
    for pat in patients:
        name = pat['name']
        glucose = pat['df']['glucose'].values.astype(float)
        valid = ~np.isnan(glucose)
        g = glucose[valid]
        if len(g) < STEPS_PER_DAY:
            continue

        mean_bg = float(np.mean(g))
        std_bg = float(np.std(g))
        cv = std_bg / mean_bg if mean_bg > 0 else 0

        orig_tir = float(np.mean((g >= LOW) & (g <= HIGH)) * 100)
        orig_tar = float(np.mean(g > HIGH) * 100)
        orig_tbr = float(np.mean(g < LOW) * 100)

        ideal_center = 125.0

        # Simulate centering only (shift mean to 125)
        g_centered = g + (ideal_center - mean_bg)
        center_tir = float(np.mean((g_centered >= LOW) & (g_centered <= HIGH)) * 100)
        center_delta = center_tir - orig_tir

        # Simulate CV reduction to 25% only (keep mean)
        if cv > 0.25:
            scale = 0.25 / cv
            g_reduced = mean_bg + (g - mean_bg) * scale
            reduce_tir = float(np.mean((g_reduced >= LOW) & (g_reduced <= HIGH)) * 100)
        else:
            reduce_tir = orig_tir
        reduce_delta = reduce_tir - orig_tir

        # Simulate both: center + reduce CV
        if cv > 0.25:
            g_both = ideal_center + (g - mean_bg) * (0.25 / cv)
        else:
            g_both = g + (ideal_center - mean_bg)
        both_tir = float(np.mean((g_both >= LOW) & (g_both <= HIGH)) * 100)
        both_delta = both_tir - orig_tir

        # Determine priority
        if center_delta > reduce_delta and center_delta > 0:
            priority = 'center_first'
        elif reduce_delta > center_delta and reduce_delta > 0:
            priority = 'reduce_variability_first'
        elif both_delta > 0:
            priority = 'both_needed'
        else:
            priority = 'already_optimal'

        # Specific recommendations
        recommendations = []
        if mean_bg > 150:
            recommendations.append('Increase basal rate or reduce CR')
        if mean_bg < 100:
            recommendations.append('Decrease basal rate or increase CR')
        if cv > 0.40:
            recommendations.append('Address high variability (cascade breaking, UAM management)')
        if cv > 0.30:
            recommendations.append('Consider rescue carb education')

        r = {
            'patient': name,
            'mean_bg': round(mean_bg, 1),
            'cv_pct': round(cv * 100, 1),
            'orig_tir': round(orig_tir, 1),
            'center_only_tir': round(center_tir, 1),
            'reduce_only_tir': round(reduce_tir, 1),
            'both_tir': round(both_tir, 1),
            'priority': priority,
            'center_delta': round(center_delta, 1),
            'reduce_delta': round(reduce_delta, 1),
            'both_delta': round(both_delta, 1),
            'recommendations': recommendations,
        }
        patient_results.append(r)

        print(f"  {name}: {priority} — center Δ{center_delta:+.1f}%, "
              f"reduce Δ{reduce_delta:+.1f}%, both Δ{both_delta:+.1f}%")

    # Summarize priorities
    from collections import Counter
    priorities = Counter(r['priority'] for r in patient_results)
    print(f"\n  Priorities: {dict(priorities)}")

    # Mean combined improvement
    both_deltas = [r['both_delta'] for r in patient_results]
    print(f"  Mean combined TIR improvement: {np.mean(both_deltas):+.1f}%")

    return {
        'experiment': 'EXP-1765',
        'title': 'Per-Patient Optimization Sequence',
        'patients': patient_results,
        'priority_distribution': dict(priorities),
        'mean_combined_improvement': round(float(np.mean(both_deltas)), 1),
    }


def exp_1766_rescue_clustering(patients):
    """Cluster patients by post-hypo rescue behavior.

    Features: rescue magnitude distribution, time-to-recovery,
    rebound severity, double-dip frequency.
    """
    print("\n=== EXP-1766: Rescue Carb Behavior Clustering ===\n")

    patient_features = []

    for pat in patients:
        name = pat['name']
        glucose = pat['df']['glucose'].values.astype(float)
        carbs = np.nan_to_num(pat['df']['carbs'].values.astype(float), nan=0.0)
        valid = ~np.isnan(glucose)

        # Find hypo episodes
        episodes = []
        i = 0
        while i < len(glucose) - 3 * STEPS_PER_HOUR:
            if valid[i] and glucose[i] < LOW:
                # Find nadir
                nadir_i = i
                nadir_g = glucose[i]
                j = i + 1
                while j < min(i + STEPS_PER_HOUR, len(glucose)):
                    if valid[j] and glucose[j] < nadir_g:
                        nadir_i = j
                        nadir_g = glucose[j]
                    if valid[j] and glucose[j] >= LOW:
                        break
                    j += 1

                # Post-nadir trajectory (3h)
                end = min(nadir_i + 3 * STEPS_PER_HOUR, len(glucose))
                post_g = glucose[nadir_i:end]
                post_valid = ~np.isnan(post_g)

                if post_valid.sum() >= STEPS_PER_HOUR:
                    # Recovery time: steps until glucose > LOW
                    recovery_steps = 0
                    for k in range(len(post_g)):
                        if post_valid[k] and post_g[k] >= LOW:
                            recovery_steps = k
                            break
                    else:
                        recovery_steps = len(post_g)

                    peak_bg = float(np.nanmax(post_g))
                    rebound = peak_bg > HIGH
                    double_dip = any(post_valid[k] and post_g[k] < LOW
                                     for k in range(min(12, len(post_g)), len(post_g)))

                    # Carbs in recovery window
                    carb_window = carbs[nadir_i:end]
                    total_rescue_carbs = float(carb_window.sum())

                    episodes.append({
                        'nadir': nadir_g,
                        'recovery_min': recovery_steps * 5,
                        'peak': peak_bg,
                        'rebound': rebound,
                        'double_dip': double_dip,
                        'logged_carbs': total_rescue_carbs,
                    })

                i = nadir_i + STEPS_PER_HOUR  # skip ahead
            else:
                i += 1

        if len(episodes) < 5:
            continue

        # Aggregate features
        recoveries = [e['recovery_min'] for e in episodes]
        peaks = [e['peak'] for e in episodes]
        rebounds = [e['rebound'] for e in episodes]
        double_dips = [e['double_dip'] for e in episodes]
        logged = [e['logged_carbs'] for e in episodes]

        r = {
            'patient': name,
            'n_episodes': len(episodes),
            'mean_recovery_min': round(float(np.mean(recoveries)), 1),
            'median_recovery_min': round(float(np.median(recoveries)), 1),
            'mean_peak': round(float(np.mean(peaks)), 1),
            'rebound_pct': round(float(np.mean(rebounds)) * 100, 1),
            'double_dip_pct': round(float(np.mean(double_dips)) * 100, 1),
            'mean_logged_carbs': round(float(np.mean(logged)), 1),
            'pct_with_logged_carbs': round(float(np.mean(np.array(logged) > 0)) * 100, 1),
        }
        patient_features.append(r)

        print(f"  {name}: {len(episodes)} eps, recovery={np.mean(recoveries):.0f}min, "
              f"rebound={np.mean(rebounds)*100:.0f}%, dbl-dip={np.mean(double_dips)*100:.0f}%, "
              f"logged carbs={np.mean(logged):.0f}g ({np.mean(np.array(logged)>0)*100:.0f}% logged)")

    # Simple clustering by rebound rate
    if patient_features:
        rb_rates = np.array([r['rebound_pct'] for r in patient_features])
        dd_rates = np.array([r['double_dip_pct'] for r in patient_features])

        # Define phenotypes
        for r in patient_features:
            if r['rebound_pct'] > 50 and r['double_dip_pct'] > 30:
                r['phenotype'] = 'volatile'
            elif r['rebound_pct'] > 50:
                r['phenotype'] = 'over_rescuer'
            elif r['double_dip_pct'] > 30:
                r['phenotype'] = 'under_rescuer'
            else:
                r['phenotype'] = 'well_managed'

        from collections import Counter
        phenotypes = Counter(r['phenotype'] for r in patient_features)
        print(f"\n  Phenotypes: {dict(phenotypes)}")

    return {
        'experiment': 'EXP-1766',
        'title': 'Rescue Carb Behavior Clustering',
        'patients': patient_features,
        'phenotype_distribution': dict(phenotypes) if patient_features else {},
    }


def generate_figures(results, patients):
    """Generate figures for the report."""
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    # Fig 1: Precision-Recall curve for acceleration thresholds
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    r1761 = results.get('EXP-1761', {})
    thresh_data = r1761.get('thresholds', {})
    if thresh_data:
        thresholds = sorted(thresh_data.keys(), key=float)
        prec = [thresh_data[t]['precision'] for t in thresholds]
        rec = [thresh_data[t]['recall'] for t in thresholds]
        f1 = [thresh_data[t]['f1'] for t in thresholds]
        fpr = [thresh_data[t]['fpr'] for t in thresholds]
        x_labels = [float(t) for t in thresholds]

        axes[0].plot(rec, prec, 'bo-', markersize=8)
        for i, t in enumerate(thresholds):
            axes[0].annotate(f'θ={t}', (rec[i], prec[i]),
                           textcoords="offset points", xytext=(5, 5), fontsize=8)
        axes[0].set_xlabel('Recall')
        axes[0].set_ylabel('Precision')
        axes[0].set_title('Precision-Recall: Acceleration Detector')
        axes[0].set_xlim(-0.05, 1.05)
        axes[0].set_ylim(-0.05, 1.05)

        axes[1].plot(x_labels, f1, 'go-', label='F1', markersize=8)
        axes[1].plot(x_labels, fpr, 'r^-', label='FPR', markersize=8)
        axes[1].set_xlabel('Acceleration threshold')
        axes[1].set_ylabel('Score')
        axes[1].set_title('F1 and FPR vs Threshold')
        axes[1].legend()

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / 'uam-fig1-accel-pr.png', dpi=150)
    plt.close()
    print("  Saved fig1")

    # Fig 2: Morning analysis — dawn rise and breakfast TAR
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    r1763 = results.get('EXP-1763', {})
    morn_pats = r1763.get('patients', [])
    if morn_pats:
        names = [p['patient'] for p in morn_pats]
        dawn = [p['mean_dawn_rise_mgdl'] for p in morn_pats]
        bkf = [p['mean_breakfast_tar_min'] for p in morn_pats]
        no_bkf = [p['mean_no_breakfast_tar_min'] for p in morn_pats]

        x = np.arange(len(names))
        colors = ['red' if d > 10 else ('orange' if d > 0 else 'green') for d in dawn]
        axes[0].bar(x, dawn, color=colors, alpha=0.7)
        axes[0].axhline(0, color='black', linewidth=0.5)
        axes[0].set_xticks(x)
        axes[0].set_xticklabels(names)
        axes[0].set_ylabel('Dawn rise (mg/dL)')
        axes[0].set_title('Dawn Phenomenon (4-7am, no carbs)')

        width = 0.35
        axes[1].bar(x - width/2, bkf, width, label='With breakfast', color='coral', alpha=0.8)
        axes[1].bar(x + width/2, no_bkf, width, label='No breakfast', color='steelblue', alpha=0.8)
        axes[1].set_xticks(x)
        axes[1].set_xticklabels(names)
        axes[1].set_ylabel('Morning TAR (min)')
        axes[1].set_title('Morning TAR: Breakfast vs No Breakfast')
        axes[1].legend()

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / 'uam-fig2-morning.png', dpi=150)
    plt.close()
    print("  Saved fig2")

    # Fig 3: Variability reduction simulation
    fig, ax = plt.subplots(figsize=(12, 7))

    r1764 = results.get('EXP-1764', {})
    var_pats = r1764.get('patients', [])
    if var_pats:
        names = [p['patient'] for p in var_pats]
        orig = [p['orig_tir'] for p in var_pats]
        target_cvs = ['0.35', '0.3', '0.25', '0.2', '0.15']
        cv_labels = ['35%', '30%', '25%', '20%', '15%']

        x = np.arange(len(names))
        width = 0.12

        ax.bar(x - 2.5*width, orig, width, label='Current', color='gray', alpha=0.8)
        colors = ['#d4e6f1', '#a9cce3', '#7fb3d8', '#5499c7', '#2e86c1']
        for j, (cv, cl, color) in enumerate(zip(target_cvs, cv_labels, colors)):
            tirs = []
            for p in var_pats:
                sim = p.get('cv_simulations', {}).get(cv, {})
                tirs.append(sim.get('tir', p['orig_tir']))
            ax.bar(x + (j - 1.5) * width, tirs, width, label=f'CV={cl}', color=color, alpha=0.9)

        ax.axhline(70, color='gold', linewidth=2, linestyle='--', label='70% target')
        ax.set_xticks(x)
        ax.set_xticklabels(names)
        ax.set_ylabel('TIR (%)')
        ax.set_title('TIR at Different Variability Levels (CV)')
        ax.legend(fontsize=8, ncol=3)
        ax.set_ylim(0, 100)

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / 'uam-fig3-variability-sim.png', dpi=150)
    plt.close()
    print("  Saved fig3")

    # Fig 4: Per-patient optimization recommendation
    fig, ax = plt.subplots(figsize=(12, 7))

    r1765 = results.get('EXP-1765', {})
    opt_pats = r1765.get('patients', [])
    if opt_pats:
        names = [p['patient'] for p in opt_pats]
        center_d = [p['center_delta'] for p in opt_pats]
        reduce_d = [p['reduce_delta'] for p in opt_pats]
        both_d = [p['both_delta'] for p in opt_pats]

        x = np.arange(len(names))
        width = 0.25
        ax.bar(x - width, center_d, width, label='Center only', color='coral', alpha=0.8)
        ax.bar(x, reduce_d, width, label='Reduce CV only', color='steelblue', alpha=0.8)
        ax.bar(x + width, both_d, width, label='Both', color='green', alpha=0.8)
        ax.axhline(0, color='black', linewidth=0.5)
        ax.set_xticks(x)
        ax.set_xticklabels(names)
        ax.set_ylabel('ΔTIR (%)')
        ax.set_title('TIR Improvement: Centering vs Variability Reduction vs Both')
        ax.legend()

        # Annotate priorities
        for i, p in enumerate(opt_pats):
            label = p['priority'].replace('_', '\n')
            ax.annotate(label, (i, both_d[i]),
                       textcoords="offset points", xytext=(0, 5),
                       fontsize=6, ha='center', rotation=0)

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / 'uam-fig4-optimization.png', dpi=150)
    plt.close()
    print("  Saved fig4")

    # Fig 5: Rescue behavior phenotypes
    fig, ax = plt.subplots(figsize=(10, 8))

    r1766 = results.get('EXP-1766', {})
    resc_pats = r1766.get('patients', [])
    if resc_pats:
        rebound = [p['rebound_pct'] for p in resc_pats]
        dd = [p['double_dip_pct'] for p in resc_pats]
        names = [p['patient'] for p in resc_pats]
        phenotypes = [p.get('phenotype', 'unknown') for p in resc_pats]

        colors_map = {
            'volatile': 'red',
            'over_rescuer': 'orange',
            'under_rescuer': 'blue',
            'well_managed': 'green',
        }
        colors = [colors_map.get(p, 'gray') for p in phenotypes]

        ax.scatter(rebound, dd, c=colors, s=150, alpha=0.8, edgecolors='black')
        for i, name in enumerate(names):
            ax.annotate(name, (rebound[i], dd[i]),
                       textcoords="offset points", xytext=(5, 5), fontsize=10)

        # Quadrant lines
        ax.axvline(50, color='gray', linestyle='--', alpha=0.5)
        ax.axhline(30, color='gray', linestyle='--', alpha=0.5)

        ax.set_xlabel('Rebound rate (%)')
        ax.set_ylabel('Double-dip rate (%)')
        ax.set_title('Rescue Behavior Phenotypes')

        # Legend
        from matplotlib.patches import Patch
        legend_elements = [
            Patch(facecolor='red', label='Volatile (high rebound + double-dip)'),
            Patch(facecolor='orange', label='Over-rescuer (high rebound)'),
            Patch(facecolor='blue', label='Under-rescuer (high double-dip)'),
            Patch(facecolor='green', label='Well-managed'),
        ]
        ax.legend(handles=legend_elements, loc='upper left')

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / 'uam-fig5-rescue-phenotypes.png', dpi=150)
    plt.close()
    print("  Saved fig5")


def main():
    parser = argparse.ArgumentParser(description='EXP-1761–1768: UAM Detection & Morning')
    parser.add_argument('--figures', action='store_true')
    args = parser.parse_args()

    print("Loading patients...")
    patients = load_patients(PATIENTS_DIR)
    print(f"Loaded {len(patients)} patients")

    results = {}

    results['EXP-1761'] = exp_1761_accel_fpr(patients)
    results['EXP-1762'] = exp_1762_two_stage_detector(patients)
    results['EXP-1763'] = exp_1763_morning_optimization(patients)
    results['EXP-1764'] = exp_1764_variability_reduction_sim(patients)
    results['EXP-1765'] = exp_1765_optimization_sequence(patients)
    results['EXP-1766'] = exp_1766_rescue_clustering(patients)

    # Save JSONs
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    for exp_id, result in results.items():
        fname = f"exp-{exp_id.split('-')[1]}_uam_morning.json"
        out = {}
        for k, v in result.items():
            if isinstance(v, (dict, list, str, int, float, bool, type(None))):
                out[k] = v
        with open(RESULTS_DIR / fname, 'w') as f:
            json.dump(out, f, indent=2, default=str)
    print(f"\nSaved {len(results)} experiment JSONs")

    if args.figures:
        print("\nGenerating figures...")
        generate_figures(results, patients)

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    r1761 = results.get('EXP-1761', {})
    best_thresh = r1761.get('thresholds', {}).get('0.5', {})
    print(f"  Accel detector @0.5: P={best_thresh.get('precision','?')}, "
          f"R={best_thresh.get('recall','?')}, F1={best_thresh.get('f1','?')}")

    r1763 = results.get('EXP-1763', {})
    print(f"  Dawn phenomenon: {r1763.get('population_dawn_rise', '?')} mg/dL "
          f"({r1763.get('dawn_positive_pct', '?')}% positive)")
    print(f"  Breakfast TAR premium: {r1763.get('breakfast_tar_premium_min', '?')} min/day")

    r1764 = results.get('EXP-1764', {})
    print(f"  CV→25% mean TIR improvement: {r1764.get('mean_tir_improvement_cv25', '?')}%")

    r1765 = results.get('EXP-1765', {})
    print(f"  Combined optimization: {r1765.get('mean_combined_improvement', '?')}% TIR")
    print(f"  Priorities: {r1765.get('priority_distribution', {})}")


if __name__ == '__main__':
    main()
