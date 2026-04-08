#!/usr/bin/env python3
"""EXP-1311–1320: UAM-aware therapy scoring, response-curve ISF by time,
confidence-weighted recommendations, and cross-patient transfer.

Builds on EXP-1301-1310 breakthroughs:
1. UAM augmentation (EXP-1309): R² from -0.508 to +0.351
2. Response-curve ISF (EXP-1301): Exponential decay fit R²=0.805, τ=2.0h
3. Violation decomposition (EXP-1305): 47% violated, 70% UAM, 30% exercise
4. Patient archetypes (EXP-1310): 3 clusters — well-calibrated, needs-tuning, miscalibrated
"""
import argparse, json, os, sys, time, warnings
import numpy as np
from pathlib import Path
from collections import defaultdict

warnings.filterwarnings('ignore')

from cgmencode.exp_metabolic_flux import load_patients
from cgmencode.exp_metabolic_441 import compute_supply_demand
from cgmencode.exp_clinical_1291 import (
    assess_preconditions, check_precondition, get_fidelity_metrics,
    get_scheduled_basal_rate, get_time_blocks
)

PATIENTS_DIR = str(Path(__file__).resolve().parent.parent.parent
                   / 'externals' / 'ns-data' / 'patients')

GLUCOSE_SCALE = 400.0
STEPS_PER_HOUR = 12
STEPS_PER_DAY = 288
DIA_STEPS = STEPS_PER_HOUR * 5  # 5-hour DIA

BLOCK_NAMES = ['overnight(0-6)', 'morning(6-10)', 'midday(10-14)',
               'afternoon(14-18)', 'evening(18-22)', 'night(22-24)']
BLOCK_RANGES = [(0, 6), (6, 10), (10, 14), (14, 18), (18, 22), (22, 24)]

MEAL_BLOCK_NAMES = ['breakfast(6-10)', 'lunch(10-14)',
                    'dinner(14-20)', 'late(20-24)']

# Archetype assignments from EXP-1310
ARCHETYPES = {
    'well-calibrated': ['d', 'h', 'j', 'k'],
    'needs-tuning': ['b', 'c', 'e', 'f', 'g', 'i'],
    'miscalibrated': ['a'],
}
PATIENT_ARCHETYPE = {}
for arch, members in ARCHETYPES.items():
    for m in members:
        PATIENT_ARCHETYPE[m] = arch


def get_time_block(step_in_day):
    """Map a step within a day to a 6-block time block index."""
    hour = (step_in_day / STEPS_PER_HOUR) % 24
    for i, (lo, hi) in enumerate(BLOCK_RANGES):
        if lo <= hour < hi:
            return i
    return 5


def compute_uam_supply(df, pk):
    """Compute UAM supply: max(0, actual_dBG/dt - net_flux) when no carbs.

    Returns (sd_dict, uam_supply, uam_mask, augmented_supply).
    """
    sd = compute_supply_demand(df, pk)
    glucose = df['glucose'].values.astype(float)
    carbs = df['carbs'].values
    n = len(glucose)

    dg = np.diff(glucose)
    dg = np.append(dg, 0)
    net_flux = sd['net']

    residual = dg - net_flux
    no_carbs = np.ones(n, dtype=bool)
    for i in range(n):
        if carbs[i] >= 2:
            s, e = max(0, i - 6), min(n, i + 36)  # -30min to +3h
            no_carbs[s:e] = False

    uam_supply = np.where(
        no_carbs & (residual > 0) & ~np.isnan(glucose) & ~np.isnan(dg),
        residual, 0.0)
    uam_mask = uam_supply > 0
    augmented_supply = sd['supply'] + uam_supply
    return sd, uam_supply, uam_mask, augmented_supply


# ─── EXP-1311: UAM-Aware Therapy Scoring ─────────────────────────────
def exp_1311_uam_therapy(patients, detail=False, preconditions=None):
    """Recompute therapy metrics using UAM-augmented physics model.

    Compare UAM-aware basal recommendations vs raw (EXP-1292).
    """
    results = {'name': 'EXP-1311: UAM-aware therapy scoring',
               'n_patients': len(patients), 'per_patient': []}

    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        temp_rate = df['temp_rate'].values
        n = len(glucose)

        sd, uam_sup, uam_mask, aug_supply = compute_uam_supply(df, pk)
        net_flux = sd['net']
        demand = sd['demand']

        dg = np.diff(glucose)
        dg = np.append(dg, 0)
        valid = ~np.isnan(glucose) & ~np.isnan(dg) & (np.abs(dg) < 50)

        if valid.sum() < STEPS_PER_DAY:
            results['per_patient'].append({
                'patient': p['name'], 'note': 'Insufficient data'})
            continue

        # Baseline R²
        residual_base = dg[valid] - net_flux[valid]
        ss_tot = float(np.sum((dg[valid] - np.mean(dg[valid])) ** 2))
        r2_base = 1 - float(np.sum(residual_base ** 2)) / (ss_tot + 1e-10)

        # Augmented R²
        aug_flux = net_flux + uam_sup
        residual_aug = dg[valid] - aug_flux[valid]
        r2_aug = 1 - float(np.sum(residual_aug ** 2)) / (ss_tot + 1e-10)

        # UAM-filtered fasting windows for basal assessment
        fasting = np.ones(n, dtype=bool)
        for i in range(n):
            ws, we = max(0, i - STEPS_PER_HOUR * 2), min(n, i + STEPS_PER_HOUR * 2)
            if np.any(bolus[ws:we] > 0) or np.any(carbs[ws:we] > 0):
                fasting[i] = False

        non_uam_fasting = fasting & ~uam_mask & valid
        raw_fasting = fasting & valid

        scheduled_rate = get_scheduled_basal_rate(p)

        # Raw basal recommendation (EXP-1292 style)
        if raw_fasting.sum() > STEPS_PER_HOUR:
            raw_net = float(np.mean(net_flux[raw_fasting]))
            raw_demand = float(np.mean(demand[raw_fasting]))
            raw_change = -raw_net / (raw_demand + 1e-6)
            raw_change = max(-0.5, min(0.5, raw_change))
        else:
            raw_net, raw_change = 0.0, 0.0

        # UAM-filtered basal recommendation
        if non_uam_fasting.sum() > STEPS_PER_HOUR:
            clean_net = float(np.mean(net_flux[non_uam_fasting]))
            clean_demand = float(np.mean(demand[non_uam_fasting]))
            clean_change = -clean_net / (clean_demand + 1e-6)
            clean_change = max(-0.5, min(0.5, clean_change))
        else:
            clean_net, clean_change = 0.0, 0.0

        rec_changed = abs(raw_change - clean_change) > 0.05

        results['per_patient'].append({
            'patient': p['name'],
            'r2_baseline': round(r2_base, 3),
            'r2_augmented': round(r2_aug, 3),
            'r2_improvement': round(r2_aug - r2_base, 3),
            'n_uam_steps': int(uam_mask.sum()),
            'uam_pct': round(float(uam_mask.sum()) / (valid.sum() + 1e-6) * 100, 1),
            'raw_fasting_steps': int(raw_fasting.sum()),
            'clean_fasting_steps': int(non_uam_fasting.sum()),
            'raw_basal_change_pct': round(raw_change * 100, 1),
            'clean_basal_change_pct': round(clean_change * 100, 1),
            'recommendation_changed': rec_changed,
            'delta_recommendation_pct': round((clean_change - raw_change) * 100, 1),
        })

    with_data = [r for r in results['per_patient'] if 'r2_baseline' in r]
    results['n_patients_with_data'] = len(with_data)
    if with_data:
        results['mean_r2_baseline'] = round(
            float(np.mean([r['r2_baseline'] for r in with_data])), 3)
        results['mean_r2_augmented'] = round(
            float(np.mean([r['r2_augmented'] for r in with_data])), 3)
        results['n_changed'] = sum(1 for r in with_data if r['recommendation_changed'])
        results['n_unchanged'] = sum(1 for r in with_data if not r['recommendation_changed'])
    return results


# ─── EXP-1312: Response-Curve ISF by Time-of-Day ─────────────────────
def exp_1312_isf_timeblock(patients, detail=False, preconditions=None):
    """Apply EXP-1301 exponential decay ISF method per time block.

    Detect circadian ISF variation. Dawn ISF boost = morning / overnight.
    """
    results = {'name': 'EXP-1312: Response-curve ISF by time-of-day',
               'n_patients': len(patients), 'per_patient': [],
               'precondition_filter': 'correction_validation'}

    TAU_CANDIDATES = [0.3, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0]
    CORRECTION_WINDOW = 3 * STEPS_PER_HOUR

    for p in patients:
        met, reason = check_precondition(p, preconditions, 'correction_validation')
        if not met:
            results['per_patient'].append({
                'patient': p['name'], 'skipped': True, 'reason': reason})
            continue

        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        isf_profile = pk[:, 7] * 200.0
        n = len(glucose)
        blocks = get_time_blocks(n)

        # Collect corrections with block labels
        block_corrections = defaultdict(list)
        for i in range(n):
            if bolus[i] < 0.3 or np.isnan(glucose[i]) or glucose[i] <= 150:
                continue
            cw = slice(max(0, i - 6), min(n, i + 6))
            if np.sum(carbs[cw]) > 2:
                continue
            if i + CORRECTION_WINDOW >= n:
                continue
            if np.sum(bolus[i + 1:i + CORRECTION_WINDOW]) > 0.5:
                continue
            if np.sum(carbs[i + 1:i + CORRECTION_WINDOW]) > 2:
                continue

            traj = glucose[i:i + CORRECTION_WINDOW].copy()
            tv = ~np.isnan(traj)
            if tv.sum() < CORRECTION_WINDOW * 0.5:
                continue

            bg_start = float(traj[0])
            t_hours = np.arange(CORRECTION_WINDOW) * (5.0 / 60.0)

            best_sse, best_tau, best_amp = np.inf, 1.0, 0.0
            for tau_c in TAU_CANDIDATES:
                basis = 1.0 - np.exp(-t_hours / tau_c)
                bv = basis[tv]
                target = bg_start - traj[tv]
                denom = float(np.sum(bv ** 2))
                if denom < 1e-6:
                    continue
                amp = float(np.sum(bv * target) / denom)
                if amp < 5:
                    continue
                predicted = bg_start - amp * basis
                sse = float(np.sum((traj[tv] - predicted[tv]) ** 2))
                if sse < best_sse:
                    best_sse, best_tau, best_amp = sse, tau_c, amp

            if best_amp < 5:
                continue

            mean_bg = float(np.nanmean(traj[tv]))
            ss_tot = float(np.sum((traj[tv] - mean_bg) ** 2))
            fit_r2 = 1 - best_sse / (ss_tot + 1e-10)
            isf_curve = best_amp / float(bolus[i])

            block_corrections[int(blocks[i])].append({
                'isf_curve': isf_curve, 'tau': best_tau, 'fit_r2': fit_r2,
            })

        if not any(block_corrections.values()):
            results['per_patient'].append({
                'patient': p['name'], 'n_corrections': 0,
                'note': 'No qualifying corrections'})
            continue

        block_results = {}
        block_isfs = {}
        for b in range(6):
            corrs = block_corrections.get(b, [])
            if not corrs:
                block_results[BLOCK_NAMES[b]] = {'n_corrections': 0}
                continue
            isfs = [c['isf_curve'] for c in corrs]
            taus = [c['tau'] for c in corrs]
            r2s = [c['fit_r2'] for c in corrs]
            block_isfs[b] = float(np.median(isfs))
            block_results[BLOCK_NAMES[b]] = {
                'n_corrections': len(corrs),
                'mean_isf': round(float(np.mean(isfs)), 1),
                'median_isf': round(float(np.median(isfs)), 1),
                'std_isf': round(float(np.std(isfs)), 1) if len(isfs) > 1 else 0.0,
                'mean_tau': round(float(np.mean(taus)), 2),
                'mean_fit_r2': round(float(np.mean(r2s)), 3),
            }

        # Dawn ISF boost: morning / overnight
        overnight_isf = block_isfs.get(0)
        morning_isf = block_isfs.get(1)
        dawn_boost = (round(morning_isf / (overnight_isf + 1e-6), 2)
                      if overnight_isf and morning_isf else None)

        # Kruskal-Wallis style: ANOVA F-statistic across blocks
        all_groups = [block_corrections[b] for b in sorted(block_corrections)
                      if len(block_corrections[b]) >= 2]
        if len(all_groups) >= 2:
            all_isfs_flat = []
            for g in all_groups:
                all_isfs_flat.extend([c['isf_curve'] for c in g])
            grand_mean = float(np.mean(all_isfs_flat))
            ss_between = sum(len(g) * (np.mean([c['isf_curve'] for c in g]) - grand_mean) ** 2
                             for g in all_groups)
            ss_within = sum(np.sum([(c['isf_curve'] - np.mean([c2['isf_curve'] for c2 in g])) ** 2
                                    for c in g]) for g in all_groups)
            df_between = len(all_groups) - 1
            df_within = len(all_isfs_flat) - len(all_groups)
            f_stat = ((ss_between / max(1, df_between)) /
                      (ss_within / max(1, df_within) + 1e-10))
            circadian_variation = f_stat > 2.5
        else:
            f_stat, circadian_variation = None, None

        total_corrs = sum(len(v) for v in block_corrections.values())
        results['per_patient'].append({
            'patient': p['name'],
            'n_corrections': total_corrs,
            'block_isf': block_results,
            'dawn_isf_boost': dawn_boost,
            'anova_f': round(f_stat, 2) if f_stat is not None else None,
            'circadian_variation': circadian_variation,
        })

    with_data = [r for r in results['per_patient'] if r.get('n_corrections', 0) > 0]
    results['n_patients_with_data'] = len(with_data)
    if with_data:
        dawn_boosts = [r['dawn_isf_boost'] for r in with_data
                       if r['dawn_isf_boost'] is not None]
        results['mean_dawn_boost'] = (round(float(np.mean(dawn_boosts)), 2)
                                      if dawn_boosts else None)
        results['n_circadian'] = sum(1 for r in with_data
                                     if r.get('circadian_variation'))
    return results


# ─── EXP-1313: UAM Event Classification ──────────────────────────────
def exp_1313_uam_classify(patients, detail=False, preconditions=None):
    """Classify UAM events into meal, slow-absorption, hepatic, artifact."""
    results = {'name': 'EXP-1313: UAM event classification',
               'n_patients': len(patients), 'per_patient': []}

    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        temp_rate = df['temp_rate'].values
        basal_ratio = pk[:, 2] * 2.0
        n = len(glucose)

        sd, uam_sup, uam_mask, _ = compute_uam_supply(df, pk)

        dg = np.diff(glucose)
        dg = np.append(dg, 0)
        valid = ~np.isnan(glucose) & ~np.isnan(dg)

        if valid.sum() < STEPS_PER_DAY:
            results['per_patient'].append({
                'patient': p['name'], 'note': 'Insufficient data'})
            continue

        # Identify contiguous UAM runs
        uam_runs = []
        in_run = False
        run_start = 0
        for i in range(n):
            if uam_mask[i] and valid[i]:
                if not in_run:
                    in_run = True
                    run_start = i
            else:
                if in_run:
                    uam_runs.append((run_start, i))
                    in_run = False
        if in_run:
            uam_runs.append((run_start, n))

        counts = {'meal_uam': 0, 'slow_absorption': 0,
                  'hepatic_variation': 0, 'sensor_artifact': 0}
        events = []

        for (rs, re) in uam_runs:
            duration_min = (re - rs) * 5
            seg_dg = dg[rs:re]
            mean_rate = float(np.nanmean(seg_dg))  # mg/dL per 5min
            step_in_day = rs % STEPS_PER_DAY
            hour = step_in_day / STEPS_PER_HOUR

            category = 'meal_uam'  # default

            # Sensor artifact: spike >5 mg/dL/5min that reverses within 30min
            if mean_rate > 5 and duration_min <= 30:
                post_end = min(n, re + 6)
                if post_end > re:
                    post_dg = dg[re:post_end]
                    if len(post_dg) > 0 and float(np.nanmean(post_dg)) < -2:
                        category = 'sensor_artifact'

            # Hepatic variation: pre-dawn 4-7 AM
            elif 4 <= hour < 7:
                category = 'hepatic_variation'

            # Slow absorption: gradual drift <1 mg/dL/5min for >1h
            elif mean_rate < 1 and duration_min > 60:
                category = 'slow_absorption'

            # Meal UAM: rise >2 mg/dL/5min for >15min, then insulin response
            elif mean_rate > 2 and duration_min > 15:
                has_response = False
                resp_end = min(n, re + 6)  # 30min after
                if resp_end > re:
                    if np.sum(bolus[re:resp_end]) > 0.1:
                        has_response = True
                    elif np.mean(basal_ratio[re:resp_end]) > 1.3:
                        has_response = True
                category = 'meal_uam'

            counts[category] += 1
            if detail:
                events.append({
                    'start': int(rs), 'end': int(re),
                    'duration_min': duration_min,
                    'mean_rate': round(mean_rate, 2),
                    'hour': round(hour, 1),
                    'category': category,
                })

        total = sum(counts.values())
        pct = {k: round(v / (total + 1e-6) * 100, 1) for k, v in counts.items()}
        dominant = max(counts, key=counts.get) if total > 0 else 'none'

        rec = {
            'patient': p['name'],
            'total_uam_runs': total,
            'counts': counts,
            'pct_breakdown': pct,
            'dominant_type': dominant,
        }
        if detail:
            rec['events'] = events[:20]
        results['per_patient'].append(rec)

    with_data = [r for r in results['per_patient'] if 'total_uam_runs' in r]
    results['n_patients_with_data'] = len(with_data)
    if with_data:
        agg_counts = defaultdict(int)
        for r in with_data:
            for k, v in r['counts'].items():
                agg_counts[k] += v
        total_all = sum(agg_counts.values())
        results['aggregate_counts'] = dict(agg_counts)
        results['aggregate_pct'] = {k: round(v / (total_all + 1e-6) * 100, 1)
                                    for k, v in agg_counts.items()}
        results['population_dominant'] = max(agg_counts, key=agg_counts.get)
    return results


# ─── EXP-1314: Basal Assessment with UAM Correction ──────────────────
def exp_1314_basal_uam(patients, detail=False, preconditions=None):
    """Compute overnight basal drift using ONLY non-UAM timesteps.

    Compare UAM-corrected slope vs raw slope from EXP-1296.
    """
    results = {'name': 'EXP-1314: Basal assessment with UAM correction',
               'n_patients': len(patients), 'per_patient': [],
               'precondition_filter': 'basal_assessment'}

    UAM_THRESHOLD = 3.0  # mg/dL per 5min

    for p in patients:
        met, reason = check_precondition(p, preconditions, 'basal_assessment')
        if not met:
            results['per_patient'].append({
                'patient': p['name'], 'skipped': True, 'reason': reason})
            continue

        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        n = len(glucose)
        n_days = n // STEPS_PER_DAY

        sd = compute_supply_demand(df, pk)
        net_flux = sd['net']
        dg = np.diff(glucose)
        dg = np.append(dg, 0)

        # UAM mask: |actual_dBG/dt - net_flux| > threshold
        residual = np.abs(dg - net_flux)
        uam_step = residual > UAM_THRESHOLD

        raw_slopes, clean_slopes = [], []
        raw_n_steps, clean_n_steps = [], []

        for d in range(n_days):
            start = d * STEPS_PER_DAY
            end = start + STEPS_PER_HOUR * 6  # 0-6 AM
            if end > n:
                break

            night_g = glucose[start:end]
            night_b = bolus[start:end]
            night_c = carbs[start:end]

            if np.sum(night_b) > 0.1 or np.sum(night_c) > 1:
                continue

            valid_raw = ~np.isnan(night_g)
            valid_clean = valid_raw & ~uam_step[start:end]

            # Raw slope
            if valid_raw.sum() >= STEPS_PER_HOUR * 3:
                x = np.arange(len(night_g))[valid_raw] * (5.0 / 60.0)
                y = night_g[valid_raw]
                if len(x) >= 10:
                    slope = float(np.polyfit(x, y, 1)[0])
                    raw_slopes.append(slope)
                    raw_n_steps.append(int(valid_raw.sum()))

            # UAM-corrected slope
            if valid_clean.sum() >= STEPS_PER_HOUR * 2:
                x = np.arange(len(night_g))[valid_clean] * (5.0 / 60.0)
                y = night_g[valid_clean]
                if len(x) >= 8:
                    slope = float(np.polyfit(x, y, 1)[0])
                    clean_slopes.append(slope)
                    clean_n_steps.append(int(valid_clean.sum()))

        if not raw_slopes and not clean_slopes:
            results['per_patient'].append({
                'patient': p['name'], 'n_nights': 0,
                'note': 'No clean fasting nights'})
            continue

        rec = {
            'patient': p['name'],
            'n_raw_nights': len(raw_slopes),
            'n_clean_nights': len(clean_slopes),
        }
        if raw_slopes:
            rec['raw_mean_slope'] = round(float(np.mean(raw_slopes)), 2)
            rec['raw_median_slope'] = round(float(np.median(raw_slopes)), 2)
            rec['raw_assessment'] = ('basal_appropriate' if abs(np.median(raw_slopes)) <= 3
                                     else 'basal_too_low' if np.median(raw_slopes) > 3
                                     else 'basal_too_high')
        if clean_slopes:
            rec['clean_mean_slope'] = round(float(np.mean(clean_slopes)), 2)
            rec['clean_median_slope'] = round(float(np.median(clean_slopes)), 2)
            rec['clean_assessment'] = ('basal_appropriate' if abs(np.median(clean_slopes)) <= 3
                                       else 'basal_too_low' if np.median(clean_slopes) > 3
                                       else 'basal_too_high')
            rec['mean_clean_steps'] = round(float(np.mean(clean_n_steps)), 0)

        if raw_slopes and clean_slopes:
            rec['slope_delta'] = round(
                float(np.mean(clean_slopes)) - float(np.mean(raw_slopes)), 2)
            rec['assessment_changed'] = rec.get('raw_assessment') != rec.get('clean_assessment')
        else:
            rec['slope_delta'] = None
            rec['assessment_changed'] = False

        results['per_patient'].append(rec)

    with_data = [r for r in results['per_patient']
                 if r.get('n_clean_nights', 0) > 0]
    results['n_patients_with_data'] = len(with_data)
    if with_data:
        results['mean_raw_slope'] = round(
            float(np.mean([r['raw_mean_slope'] for r in with_data
                           if 'raw_mean_slope' in r])), 2)
        results['mean_clean_slope'] = round(
            float(np.mean([r['clean_mean_slope'] for r in with_data])), 2)
        results['n_assessment_changed'] = sum(
            1 for r in with_data if r.get('assessment_changed'))
    return results


# ─── EXP-1315: Confidence-Weighted Recommendations ───────────────────
def exp_1315_confidence_recs(patients, detail=False, preconditions=None):
    """Produce single settings recommendation per patient with confidence.

    Combine basal (EXP-1292), ISF (EXP-1301 curve), CR (EXP-1307).
    Weight by n_events, fidelity R², recommendation stability.
    """
    results = {'name': 'EXP-1315: Confidence-weighted recommendations',
               'n_patients': len(patients), 'per_patient': []}

    TAU_CANDIDATES = [0.3, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0]

    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        temp_rate = df['temp_rate'].values
        basal_ratio = pk[:, 2] * 2.0
        isf_profile = pk[:, 7] * 200.0
        n = len(glucose)
        valid = ~np.isnan(glucose)

        sd = compute_supply_demand(df, pk)
        net_flux = sd['net']
        demand = sd['demand']

        # Fidelity R²
        dg = np.diff(glucose)
        dg = np.append(dg, 0)
        vboth = valid & ~np.isnan(dg) & (np.abs(dg) < 50)
        if vboth.sum() > 100:
            res = dg[vboth] - net_flux[vboth]
            ss_tot = float(np.sum((dg[vboth] - np.mean(dg[vboth])) ** 2))
            fidelity_r2 = 1 - float(np.sum(res ** 2)) / (ss_tot + 1e-10)
        else:
            fidelity_r2 = -1.0

        # --- Basal recommendation ---
        fasting = np.ones(n, dtype=bool)
        for i in range(n):
            ws, we = max(0, i - STEPS_PER_HOUR * 2), min(n, i + STEPS_PER_HOUR * 2)
            if np.any(bolus[ws:we] > 0) or np.any(carbs[ws:we] > 0):
                fasting[i] = False
        fv = fasting & valid
        n_fasting = int(fv.sum())

        scheduled_rate = get_scheduled_basal_rate(p)
        if n_fasting > STEPS_PER_HOUR:
            mean_net = float(np.mean(net_flux[fv]))
            mean_demand = float(np.mean(demand[fv]))
            basal_change = -mean_net / (mean_demand + 1e-6)
            basal_change = max(-0.5, min(0.5, basal_change))
        else:
            basal_change = 0.0

        # --- ISF recommendation (response-curve) ---
        isf_estimates = []
        for i in range(n):
            if bolus[i] < 0.3 or np.isnan(glucose[i]) or glucose[i] <= 150:
                continue
            cw = slice(max(0, i - 6), min(n, i + 6))
            if np.sum(carbs[cw]) > 2:
                continue
            window = 3 * STEPS_PER_HOUR
            if i + window >= n:
                continue
            if np.sum(bolus[i + 1:i + window]) > 0.5:
                continue
            if np.sum(carbs[i + 1:i + window]) > 2:
                continue
            traj = glucose[i:i + window]
            tv = ~np.isnan(traj)
            if tv.sum() < window * 0.5:
                continue
            bg_start = float(traj[0])
            t_hours = np.arange(window) * (5.0 / 60.0)
            best_sse, best_amp = np.inf, 0.0
            for tau_c in TAU_CANDIDATES:
                basis = 1.0 - np.exp(-t_hours / tau_c)
                bv = basis[tv]
                denom = float(np.sum(bv ** 2))
                if denom < 1e-6:
                    continue
                amp = float(np.sum(bv * (bg_start - traj[tv])) / denom)
                if amp < 5:
                    continue
                sse = float(np.sum((traj[tv] - (bg_start - amp * basis[tv])) ** 2))
                if sse < best_sse:
                    best_sse, best_amp = sse, amp
            if best_amp >= 5:
                isf_estimates.append(best_amp / float(bolus[i]))

        n_corrections = len(isf_estimates)
        mean_isf_profile = float(np.mean(isf_profile[valid])) if valid.sum() > 0 else 50.0
        if isf_estimates:
            measured_isf = float(np.median(isf_estimates))
            isf_ratio = measured_isf / (mean_isf_profile + 1e-6)
            isf_iqr = float(np.percentile(isf_estimates, 75) -
                            np.percentile(isf_estimates, 25))
        else:
            measured_isf, isf_ratio, isf_iqr = mean_isf_profile, 1.0, 0.0

        # --- CR recommendation (meal rises) ---
        meal_rises = []
        last_meal = -STEPS_PER_HOUR * 3
        for i in range(n):
            if carbs[i] < 5 or (i - last_meal) < STEPS_PER_HOUR * 2:
                continue
            last_meal = i
            post_end = min(n, i + 3 * STEPS_PER_HOUR)
            if post_end - i < STEPS_PER_HOUR:
                continue
            post_g = glucose[i:post_end]
            pre_g = glucose[max(0, i - 3):i + 1]
            pre_g = pre_g[~np.isnan(pre_g)]
            if len(pre_g) == 0:
                continue
            bg_peak = float(np.nanmax(post_g))
            bg_start = float(np.mean(pre_g))
            if not np.isnan(bg_peak):
                meal_rises.append(bg_peak - bg_start)
        n_meals = len(meal_rises)
        mean_excursion = float(np.mean(meal_rises)) if meal_rises else 0.0

        # --- Confidence weighting ---
        # Factors: n_events, fidelity, and consistency (ISF IQR)
        basal_confidence_score = min(1.0, n_fasting / (STEPS_PER_DAY * 3))
        isf_confidence_score = min(1.0, n_corrections / 20.0)
        fidelity_weight = max(0.1, min(1.0, (fidelity_r2 + 1.0) / 2.0))
        consistency_weight = max(0.2, 1.0 - isf_iqr / (measured_isf + 1e-6))

        composite_conf = (basal_confidence_score * 0.3 +
                          isf_confidence_score * 0.3 +
                          fidelity_weight * 0.2 +
                          consistency_weight * 0.2)
        conf_label = ('high' if composite_conf > 0.6 else
                      'medium' if composite_conf > 0.35 else 'low')

        # 80% CI for basal change (assume normal, use fasting variance)
        if fv.sum() > 10:
            se_net = float(np.std(net_flux[fv])) / np.sqrt(fv.sum())
            ci_half = 1.28 * se_net / (float(np.mean(demand[fv])) + 1e-6) * 100
        else:
            ci_half = 25.0
        ci_half = min(ci_half, 50.0)

        # ISF CI
        if len(isf_estimates) > 2:
            isf_se = float(np.std(isf_estimates)) / np.sqrt(len(isf_estimates))
            isf_ci_half = round(1.28 * isf_se, 1)
        else:
            isf_ci_half = round(measured_isf * 0.3, 1)

        # Textual recommendation
        basal_dir = 'decrease' if basal_change < -0.05 else 'increase' if basal_change > 0.05 else 'maintain'
        isf_dir = ('increase' if isf_ratio > 1.15 else
                   'decrease' if isf_ratio < 0.85 else 'maintain')

        basal_text = (f"{basal_dir} basal by {abs(basal_change)*100:.0f}% "
                      f"\u00b1 {ci_half:.0f}% (confidence: {conf_label})")
        isf_text = (f"{isf_dir} ISF to ~{measured_isf:.0f} "
                    f"\u00b1 {isf_ci_half:.0f} (confidence: {conf_label})")

        results['per_patient'].append({
            'patient': p['name'],
            'scheduled_rate': round(scheduled_rate, 3),
            'basal_change_pct': round(basal_change * 100, 1),
            'basal_ci_80_pct': round(ci_half, 1),
            'basal_recommendation': basal_text,
            'measured_isf': round(measured_isf, 1),
            'profile_isf': round(mean_isf_profile, 1),
            'isf_ratio': round(isf_ratio, 2),
            'isf_ci_80': round(isf_ci_half, 1),
            'isf_recommendation': isf_text,
            'n_corrections': n_corrections,
            'n_meals': n_meals,
            'mean_excursion': round(mean_excursion, 1),
            'fidelity_r2': round(fidelity_r2, 3),
            'confidence_score': round(composite_conf, 2),
            'confidence_label': conf_label,
        })

    with_data = results['per_patient']
    results['confidence_distribution'] = {
        lbl: sum(1 for r in with_data if r.get('confidence_label') == lbl)
        for lbl in ['high', 'medium', 'low']
    }
    return results


# ─── EXP-1316: Per-Archetype Assessment Pipeline ─────────────────────
def exp_1316_archetype(patients, detail=False, preconditions=None):
    """Different analysis depth based on patient archetype (EXP-1310).

    Well-calibrated: light (TIR trends, monthly ISF check).
    Needs-tuning: full (all settings, UAM-corrected).
    Miscalibrated: comprehensive (settings review + data quality audit).
    """
    results = {'name': 'EXP-1316: Per-archetype assessment pipeline',
               'n_patients': len(patients), 'per_patient': []}

    archetype_results = defaultdict(list)

    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        temp_rate = df['temp_rate'].values
        basal_ratio = pk[:, 2] * 2.0
        isf_profile = pk[:, 7] * 200.0
        n = len(glucose)

        valid_g = glucose[~np.isnan(glucose)]
        if len(valid_g) < STEPS_PER_DAY:
            results['per_patient'].append({
                'patient': p['name'], 'note': 'Insufficient data'})
            continue

        archetype = PATIENT_ARCHETYPE.get(p['name'], 'needs-tuning')

        # Common metrics
        tir = float(np.mean((valid_g >= 70) & (valid_g <= 180)) * 100)
        tbr = float(np.mean(valid_g < 70) * 100)
        cv = float(np.std(valid_g) / (np.mean(valid_g) + 1e-6) * 100)
        mean_bg = float(np.mean(valid_g))

        rec = {
            'patient': p['name'],
            'archetype': archetype,
            'tir': round(tir, 1),
            'tbr': round(tbr, 1),
            'cv': round(cv, 1),
            'mean_bg': round(mean_bg, 1),
        }

        if archetype == 'well-calibrated':
            # Light assessment: TIR trends and monthly ISF check
            rec['assessment_level'] = 'light'
            mean_isf_prof = float(np.mean(isf_profile[~np.isnan(glucose)]))
            mean_br = float(np.mean(basal_ratio[~np.isnan(glucose)]))
            rec['mean_isf_profile'] = round(mean_isf_prof, 1)
            rec['mean_basal_ratio'] = round(mean_br, 2)
            rec['intervention'] = ('none' if tir >= 65 and tbr < 4
                                   else 'monitor_tbr' if tbr >= 4
                                   else 'review_tir')

        elif archetype == 'needs-tuning':
            # Full assessment: all settings, UAM-corrected
            rec['assessment_level'] = 'full'
            sd, uam_sup, uam_mask, _ = compute_uam_supply(df, pk)
            net_flux = sd['net']
            demand = sd['demand']

            # Basal assessment (UAM-corrected)
            fasting = np.ones(n, dtype=bool)
            for i in range(n):
                ws, we = max(0, i - STEPS_PER_HOUR * 2), min(n, i + STEPS_PER_HOUR * 2)
                if np.any(bolus[ws:we] > 0) or np.any(carbs[ws:we] > 0):
                    fasting[i] = False
            clean = fasting & ~uam_mask & ~np.isnan(glucose)
            if clean.sum() > STEPS_PER_HOUR:
                mean_net = float(np.mean(net_flux[clean]))
                mean_d = float(np.mean(demand[clean]))
                basal_change = -mean_net / (mean_d + 1e-6)
                basal_change = max(-0.5, min(0.5, basal_change))
            else:
                basal_change = 0.0

            # ISF quick estimate
            isf_vals = []
            for i in range(n):
                if bolus[i] < 0.3 or np.isnan(glucose[i]) or glucose[i] <= 120:
                    continue
                cw = slice(max(0, i - 6), min(n, i + 6))
                if np.sum(carbs[cw]) > 2:
                    continue
                fe = min(n, i + DIA_STEPS)
                if fe - i < STEPS_PER_HOUR * 2:
                    continue
                fbg = glucose[i:fe]
                if np.sum(~np.isnan(fbg)) < len(fbg) * 0.3:
                    continue
                delta = glucose[i] - np.nanmin(fbg)
                if delta > 10:
                    isf_vals.append(delta / bolus[i])
            mean_isf_prof = float(np.mean(isf_profile[~np.isnan(glucose)]))
            if isf_vals:
                measured_isf = float(np.median(isf_vals))
                isf_ratio = measured_isf / (mean_isf_prof + 1e-6)
            else:
                measured_isf, isf_ratio = mean_isf_prof, 1.0

            rec['basal_change_pct'] = round(basal_change * 100, 1)
            rec['measured_isf'] = round(measured_isf, 1)
            rec['isf_ratio'] = round(isf_ratio, 2)
            rec['n_uam_steps'] = int(uam_mask.sum())
            interventions = []
            if abs(basal_change) > 0.1:
                interventions.append('adjust_basal')
            if abs(isf_ratio - 1.0) > 0.2:
                interventions.append('adjust_isf')
            if tbr >= 4:
                interventions.append('address_hypo')
            rec['intervention'] = ', '.join(interventions) if interventions else 'fine_tune'

        else:  # miscalibrated
            # Comprehensive: settings review + data quality audit
            rec['assessment_level'] = 'comprehensive'
            cgm_coverage = float((~np.isnan(glucose)).mean() * 100)
            insulin_coverage = float(((bolus > 0) | (temp_rate > 0)).mean() * 100)
            pct_suspended = float((basal_ratio < 0.1).mean() * 100)
            mean_br = float(np.mean(basal_ratio[~np.isnan(glucose)]))

            sd = compute_supply_demand(df, pk)
            dg = np.diff(glucose)
            dg = np.append(dg, 0)
            vb = ~np.isnan(glucose) & ~np.isnan(dg) & (np.abs(dg) < 50)
            if vb.sum() > 100:
                res_arr = dg[vb] - sd['net'][vb]
                ss_t = float(np.sum((dg[vb] - np.mean(dg[vb])) ** 2))
                fid_r2 = 1 - float(np.sum(res_arr ** 2)) / (ss_t + 1e-10)
            else:
                fid_r2 = -1.0

            rec['cgm_coverage_pct'] = round(cgm_coverage, 1)
            rec['insulin_coverage_pct'] = round(insulin_coverage, 1)
            rec['pct_suspended'] = round(pct_suspended, 1)
            rec['mean_basal_ratio'] = round(mean_br, 2)
            rec['fidelity_r2'] = round(fid_r2, 3)
            issues = []
            if cgm_coverage < 70:
                issues.append('poor_cgm_coverage')
            if pct_suspended > 30:
                issues.append('excessive_suspension')
            if mean_br > 1.8 or mean_br < 0.5:
                issues.append('basal_far_from_nominal')
            if fid_r2 < -0.5:
                issues.append('physics_model_invalid')
            rec['data_quality_issues'] = issues
            rec['intervention'] = ('full_settings_review' if issues
                                   else 'targeted_adjustment')

        archetype_results[archetype].append(rec)
        results['per_patient'].append(rec)

    # Archetype summary
    results['archetype_summary'] = {}
    for arch in ['well-calibrated', 'needs-tuning', 'miscalibrated']:
        members = archetype_results.get(arch, [])
        if members:
            results['archetype_summary'][arch] = {
                'n_patients': len(members),
                'mean_tir': round(float(np.mean([r['tir'] for r in members])), 1),
                'mean_tbr': round(float(np.mean([r['tbr'] for r in members])), 1),
                'interventions': [r.get('intervention', 'unknown') for r in members],
            }
    return results


# ─── EXP-1317: Realistic Post-Meal Thresholds ────────────────────────
def exp_1317_meal_thresholds(patients, detail=False, preconditions=None):
    """Recalibrate meal excursion thresholds using percentile-based flagging.

    Compare fixed 180, fixed 250, and per-patient percentile-based approaches.
    """
    results = {'name': 'EXP-1317: Realistic post-meal thresholds',
               'n_patients': len(patients), 'per_patient': [],
               'precondition_filter': 'cr_assessment'}

    POST_MEAL_WINDOW = 3 * STEPS_PER_HOUR

    for p in patients:
        met, reason = check_precondition(p, preconditions, 'cr_assessment')
        if not met:
            results['per_patient'].append({
                'patient': p['name'], 'skipped': True, 'reason': reason})
            continue

        df = p['df']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        n = len(glucose)

        peaks = []
        last_meal = -STEPS_PER_HOUR * 3
        for i in range(n):
            if carbs[i] < 5 or (i - last_meal) < STEPS_PER_HOUR * 2:
                continue
            last_meal = i
            if i + POST_MEAL_WINDOW >= n:
                continue
            post_g = glucose[i:i + POST_MEAL_WINDOW]
            valid_post = ~np.isnan(post_g)
            if valid_post.sum() < POST_MEAL_WINDOW * 0.4:
                continue
            peak = float(np.nanmax(post_g))
            if not np.isnan(peak):
                peaks.append(peak)

        if not peaks:
            results['per_patient'].append({
                'patient': p['name'], 'n_meals': 0,
                'note': 'No qualifying meals'})
            continue

        peaks_arr = np.array(peaks)
        p75 = float(np.percentile(peaks_arr, 75))

        # Fixed threshold approach
        flagged_180 = int(np.sum(peaks_arr > 180))
        flagged_250 = int(np.sum(peaks_arr > 250))
        # Percentile approach: worst 25%
        flagged_pct = int(np.sum(peaks_arr > p75))

        n_meals = len(peaks)
        fpr_180 = round(flagged_180 / n_meals * 100, 1)
        fpr_250 = round(flagged_250 / n_meals * 100, 1)
        fpr_pct = round(flagged_pct / n_meals * 100, 1)  # should be ~25%

        rec = {
            'patient': p['name'],
            'n_meals': n_meals,
            'mean_peak': round(float(np.mean(peaks_arr)), 1),
            'median_peak': round(float(np.median(peaks_arr)), 1),
            'p25_peak': round(float(np.percentile(peaks_arr, 25)), 1),
            'p75_peak': round(p75, 1),
            'p90_peak': round(float(np.percentile(peaks_arr, 90)), 1),
            'threshold_180': {
                'flagged': flagged_180,
                'flag_rate_pct': fpr_180,
            },
            'threshold_250': {
                'flagged': flagged_250,
                'flag_rate_pct': fpr_250,
            },
            'threshold_percentile': {
                'threshold_value': round(p75, 1),
                'flagged': flagged_pct,
                'flag_rate_pct': fpr_pct,
            },
            'recommended_threshold': ('percentile' if fpr_180 > 60
                                      else '180' if fpr_180 <= 40
                                      else 'percentile'),
        }
        results['per_patient'].append(rec)

    with_data = [r for r in results['per_patient'] if r.get('n_meals', 0) > 0]
    results['n_patients_with_data'] = len(with_data)
    if with_data:
        results['mean_flag_rate_180'] = round(
            float(np.mean([r['threshold_180']['flag_rate_pct'] for r in with_data])), 1)
        results['mean_flag_rate_250'] = round(
            float(np.mean([r['threshold_250']['flag_rate_pct'] for r in with_data])), 1)
        results['mean_flag_rate_pct'] = round(
            float(np.mean([r['threshold_percentile']['flag_rate_pct']
                           for r in with_data])), 1)
        results['recommendation_distribution'] = {
            t: sum(1 for r in with_data if r.get('recommended_threshold') == t)
            for t in ['180', '250', 'percentile']
        }
    return results


# ─── EXP-1318: Long-Window Stability Analysis ────────────────────────
def exp_1318_long_stability(patients, detail=False, preconditions=None):
    """Extend EXP-1304 stability analysis across 1/2/4/8 week windows.

    Find minimum window where recommendation CV < 0.20.
    """
    results = {'name': 'EXP-1318: Long-window stability analysis',
               'n_patients': len(patients), 'per_patient': [],
               'precondition_filter': 'multiday_tracking'}

    WINDOW_DAYS_LIST = [7, 14, 28, 56]
    STRIDE_DAYS = 7

    for p in patients:
        met, reason = check_precondition(p, preconditions, 'multiday_tracking')
        if not met:
            results['per_patient'].append({
                'patient': p['name'], 'skipped': True, 'reason': reason})
            continue

        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        n = len(glucose)

        sd = compute_supply_demand(df, pk)
        net_flux = sd['net']
        demand = sd['demand']

        window_results = {}
        optimal_window = None

        for win_days in WINDOW_DAYS_LIST:
            win_steps = win_days * STEPS_PER_DAY
            stride_steps = STRIDE_DAYS * STEPS_PER_DAY

            if win_steps > n:
                continue

            basal_recs = []
            start = 0
            while start + win_steps <= n:
                end = start + win_steps
                w_g = glucose[start:end]
                w_b = bolus[start:end]
                w_c = carbs[start:end]
                w_net = net_flux[start:end]
                w_dem = demand[start:end]
                w_valid = ~np.isnan(w_g)

                if w_valid.sum() < win_steps * 0.4:
                    start += stride_steps
                    continue

                # Fasting filter
                w_fasting = np.ones(len(w_g), dtype=bool)
                for i in range(len(w_g)):
                    ws_i = max(0, i - STEPS_PER_HOUR * 2)
                    we_i = min(len(w_g), i + STEPS_PER_HOUR * 2)
                    if np.sum(w_b[ws_i:we_i]) > 0.1 or np.sum(w_c[ws_i:we_i]) > 1:
                        w_fasting[i] = False
                fv = w_fasting & w_valid

                if fv.sum() > STEPS_PER_HOUR * 4:
                    mn = float(np.mean(w_net[fv]))
                    md = float(np.mean(w_dem[fv]))
                    change = -mn / (md + 1e-6)
                    change = max(-0.5, min(0.5, change))
                    basal_recs.append(change * 100)

                start += stride_steps

            if len(basal_recs) >= 2:
                mean_rec = float(np.mean(basal_recs))
                std_rec = float(np.std(basal_recs, ddof=1))
                cv = std_rec / (abs(mean_rec) + 1e-6)
                window_results[f'{win_days}d'] = {
                    'n_windows': len(basal_recs),
                    'mean_change_pct': round(mean_rec, 1),
                    'std_change_pct': round(std_rec, 1),
                    'cv': round(cv, 2),
                    'stable': cv < 0.20,
                }
                if cv < 0.20 and optimal_window is None:
                    optimal_window = win_days
            elif len(basal_recs) == 1:
                window_results[f'{win_days}d'] = {
                    'n_windows': 1,
                    'mean_change_pct': round(basal_recs[0], 1),
                    'note': 'Single window — CV undefined',
                }

        rec = {
            'patient': p['name'],
            'window_analysis': window_results,
            'optimal_window_days': optimal_window,
        }
        results['per_patient'].append(rec)

    with_data = [r for r in results['per_patient']
                 if r.get('optimal_window_days') is not None]
    all_assessed = [r for r in results['per_patient'] if 'window_analysis' in r]
    results['n_patients_assessed'] = len(all_assessed)
    results['n_stable_found'] = len(with_data)
    if with_data:
        opt_wins = [r['optimal_window_days'] for r in with_data]
        results['mean_optimal_window'] = round(float(np.mean(opt_wins)), 0)
        results['optimal_distribution'] = {
            f'{d}d': sum(1 for w in opt_wins if w == d)
            for d in WINDOW_DAYS_LIST
        }
    return results


# ─── EXP-1319: Loop-Observed ISF ─────────────────────────────────────
def exp_1319_loop_isf(patients, detail=False, preconditions=None):
    """What ISF does the AID loop effectively apply?

    Loop ISF_observed = ΔBG / total_insulin per correction window.
    Compare to profile ISF and response-curve ISF.
    """
    results = {'name': 'EXP-1319: Loop-observed ISF',
               'n_patients': len(patients), 'per_patient': [],
               'precondition_filter': 'isf_estimation'}

    for p in patients:
        met, reason = check_precondition(p, preconditions, 'isf_estimation')
        if not met:
            results['per_patient'].append({
                'patient': p['name'], 'skipped': True, 'reason': reason})
            continue

        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        temp_rate = df['temp_rate'].values
        isf_profile = pk[:, 7] * 200.0
        n = len(glucose)

        # Find correction windows: high BG followed by glucose drop
        loop_isfs = []
        response_isfs = []

        for i in range(n):
            if np.isnan(glucose[i]) or glucose[i] <= 150:
                continue
            # Need a 3h correction window
            window = 3 * STEPS_PER_HOUR
            if i + window >= n:
                continue
            # Skip if carbs in window
            cw = slice(max(0, i - 6), min(n, i + window))
            if np.sum(carbs[cw]) > 2:
                continue

            traj = glucose[i:i + window]
            tv = ~np.isnan(traj)
            if tv.sum() < window * 0.4:
                continue

            bg_start = float(traj[0])
            bg_end = float(np.nanmin(traj))
            delta_bg = bg_start - bg_end
            if delta_bg < 10:
                continue

            # Total insulin delivered in this window (bolus + basal)
            total_bolus = float(np.sum(bolus[i:i + window]))
            basal_delivered = float(np.sum(temp_rate[i:i + window])) * (5.0 / 60.0)
            total_insulin = total_bolus + basal_delivered

            if total_insulin < 0.1:
                continue

            loop_isf_val = delta_bg / total_insulin
            # Response-curve ISF (bolus-only, if any)
            if total_bolus > 0.1:
                response_isf_val = delta_bg / total_bolus
                response_isfs.append(response_isf_val)
            else:
                response_isf_val = None

            loop_isfs.append({
                'loop_isf': loop_isf_val,
                'response_isf': response_isf_val,
                'delta_bg': delta_bg,
                'total_insulin': total_insulin,
                'total_bolus': total_bolus,
                'basal_insulin': basal_delivered,
            })

        if not loop_isfs:
            results['per_patient'].append({
                'patient': p['name'], 'n_windows': 0,
                'note': 'No qualifying correction windows'})
            continue

        mean_loop_isf = float(np.mean([c['loop_isf'] for c in loop_isfs]))
        mean_profile_isf = float(np.mean(isf_profile[~np.isnan(glucose)]))
        ratio = mean_loop_isf / (mean_profile_isf + 1e-6)

        if ratio > 1.3:
            assessment = 'loop_over_dosing'
            suggestion = 'decrease ISF (increase number)'
        elif ratio < 0.7:
            assessment = 'loop_under_dosing'
            suggestion = 'increase ISF (decrease number)'
        else:
            assessment = 'isf_well_matched'
            suggestion = 'no change needed'

        rec = {
            'patient': p['name'],
            'n_windows': len(loop_isfs),
            'mean_loop_isf': round(mean_loop_isf, 1),
            'mean_profile_isf': round(mean_profile_isf, 1),
            'loop_profile_ratio': round(ratio, 2),
            'assessment': assessment,
            'suggestion': suggestion,
        }
        if response_isfs:
            rec['mean_response_isf'] = round(float(np.mean(response_isfs)), 1)
            rec['response_vs_loop_ratio'] = round(
                float(np.mean(response_isfs)) / (mean_loop_isf + 1e-6), 2)
        if detail:
            rec['windows'] = [{k: round(v, 2) if isinstance(v, float) else v
                               for k, v in w.items()} for w in loop_isfs[:10]]
        results['per_patient'].append(rec)

    with_data = [r for r in results['per_patient'] if r.get('n_windows', 0) > 0]
    results['n_patients_with_data'] = len(with_data)
    if with_data:
        results['mean_loop_profile_ratio'] = round(
            float(np.mean([r['loop_profile_ratio'] for r in with_data])), 2)
        results['assessment_distribution'] = {
            a: sum(1 for r in with_data if r.get('assessment') == a)
            for a in ['loop_over_dosing', 'loop_under_dosing', 'isf_well_matched']
        }
    return results


# ─── EXP-1320: Cross-Patient UAM Transfer ────────────────────────────
def exp_1320_uam_transfer(patients, detail=False, preconditions=None):
    """Can UAM patterns from one patient improve modeling of another?

    Train per-patient UAM thresholds, test cross-patient transfer.
    Find universal threshold that works for >80% of patients.
    """
    results = {'name': 'EXP-1320: Cross-patient UAM transfer',
               'n_patients': len(patients), 'per_patient': []}

    # Step 1: Compute per-patient optimal UAM threshold
    patient_data = []
    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        carbs = df['carbs'].values
        n = len(glucose)

        sd = compute_supply_demand(df, pk)
        net_flux = sd['net']
        dg = np.diff(glucose)
        dg = np.append(dg, 0)
        valid = ~np.isnan(glucose) & ~np.isnan(dg) & (np.abs(dg) < 50)

        if valid.sum() < STEPS_PER_DAY:
            results['per_patient'].append({
                'patient': p['name'], 'note': 'Insufficient data'})
            continue

        residual = dg - net_flux
        # No-carb mask
        no_carbs = np.ones(n, dtype=bool)
        for i in range(n):
            if carbs[i] >= 2:
                s, e = max(0, i - 6), min(n, i + 36)
                no_carbs[s:e] = False

        ss_tot = float(np.sum((dg[valid] - np.mean(dg[valid])) ** 2))
        r2_base = 1 - float(np.sum((dg[valid] - net_flux[valid]) ** 2)) / (ss_tot + 1e-10)

        # Try candidate thresholds for UAM detection
        candidates = [1.0, 2.0, 3.0, 4.0, 5.0, 7.0, 10.0]
        best_thresh, best_r2 = 3.0, r2_base
        thresh_r2s = {}

        for thresh in candidates:
            uam = np.zeros(n)
            for i in range(n):
                if valid[i] and no_carbs[i] and residual[i] > thresh:
                    # Require ≥3 consecutive steps
                    if i >= 2 and valid[i-1] and valid[i-2]:
                        if residual[i-1] > thresh * 0.5 or residual[i-2] > thresh * 0.5:
                            uam[i] = residual[i]
                    elif i + 2 < n and valid[i+1]:
                        if residual[i+1] > thresh * 0.5:
                            uam[i] = residual[i]

            aug_flux = net_flux + uam
            ss_res = float(np.sum((dg[valid] - aug_flux[valid]) ** 2))
            r2 = 1 - ss_res / (ss_tot + 1e-10)
            thresh_r2s[thresh] = round(r2, 4)
            if r2 > best_r2:
                best_r2, best_thresh = r2, thresh

        patient_data.append({
            'name': p['name'],
            'residual': residual,
            'valid': valid,
            'no_carbs': no_carbs,
            'dg': dg,
            'net_flux': net_flux,
            'ss_tot': ss_tot,
            'r2_base': r2_base,
            'best_thresh': best_thresh,
            'best_r2': best_r2,
        })

        results['per_patient'].append({
            'patient': p['name'],
            'r2_baseline': round(r2_base, 3),
            'optimal_threshold': best_thresh,
            'r2_at_optimal': round(best_r2, 3),
            'r2_improvement': round(best_r2 - r2_base, 3),
            'threshold_sweep': thresh_r2s,
        })

    if len(patient_data) < 2:
        results['note'] = 'Too few patients for cross-patient transfer'
        return results

    # Step 2: Cross-patient transfer matrix
    n_pat = len(patient_data)
    transfer_matrix = np.zeros((n_pat, n_pat))
    names = [pd['name'] for pd in patient_data]

    for i, src in enumerate(patient_data):
        for j, tgt in enumerate(patient_data):
            thresh = src['best_thresh']
            res = tgt['residual']
            val = tgt['valid']
            nc = tgt['no_carbs']
            dg_t = tgt['dg']
            nf_t = tgt['net_flux']
            n_t = len(dg_t)

            uam = np.zeros(n_t)
            for k in range(n_t):
                if val[k] and nc[k] and res[k] > thresh:
                    uam[k] = res[k]

            aug_flux = nf_t + uam
            ss_res = float(np.sum((dg_t[val] - aug_flux[val]) ** 2))
            r2 = 1 - ss_res / (tgt['ss_tot'] + 1e-10)
            transfer_matrix[i, j] = r2

    # Step 3: Find universal threshold
    universal_results = {}
    for thresh in candidates:
        improved_count = 0
        for pd in patient_data:
            res = pd['residual']
            val = pd['valid']
            nc = pd['no_carbs']
            dg_p = pd['dg']
            nf_p = pd['net_flux']
            n_p = len(dg_p)

            uam = np.zeros(n_p)
            for k in range(n_p):
                if val[k] and nc[k] and res[k] > thresh:
                    uam[k] = res[k]

            aug = nf_p + uam
            ss_res = float(np.sum((dg_p[val] - aug[val]) ** 2))
            r2 = 1 - ss_res / (pd['ss_tot'] + 1e-10)
            if r2 > pd['r2_base']:
                improved_count += 1

        universal_results[thresh] = {
            'n_improved': improved_count,
            'pct_improved': round(improved_count / n_pat * 100, 1),
        }

    # Best universal threshold
    best_universal = max(universal_results,
                         key=lambda t: universal_results[t]['n_improved'])
    pct_improved = universal_results[best_universal]['pct_improved']

    # Transfer matrix summary
    transfer_list = []
    for i in range(n_pat):
        for j in range(n_pat):
            if i != j:
                transfer_list.append({
                    'source': names[i], 'target': names[j],
                    'r2_with_transfer': round(float(transfer_matrix[i, j]), 3),
                    'r2_baseline': round(float(patient_data[j]['r2_base']), 3),
                    'improvement': round(float(transfer_matrix[i, j] -
                                               patient_data[j]['r2_base']), 3),
                })

    results['universal_threshold'] = best_universal
    results['universal_pct_improved'] = pct_improved
    results['universal_meets_80pct'] = pct_improved >= 80
    results['universal_sweep'] = universal_results
    if detail:
        results['transfer_pairs'] = sorted(transfer_list,
                                           key=lambda x: -x['improvement'])[:20]

    # Mean cross-patient improvement
    improvements = [t['improvement'] for t in transfer_list]
    results['mean_transfer_improvement'] = round(float(np.mean(improvements)), 3)
    results['n_positive_transfers'] = sum(1 for x in improvements if x > 0)
    results['n_total_transfers'] = len(improvements)
    return results


# ─── Experiment Registry ─────────────────────────────────────────────
EXPERIMENTS = {
    1311: ('UAM-aware therapy scoring', exp_1311_uam_therapy),
    1312: ('Response-curve ISF by time', exp_1312_isf_timeblock),
    1313: ('UAM event classification', exp_1313_uam_classify),
    1314: ('Basal with UAM correction', exp_1314_basal_uam),
    1315: ('Confidence-weighted recs', exp_1315_confidence_recs),
    1316: ('Per-archetype assessment', exp_1316_archetype),
    1317: ('Realistic meal thresholds', exp_1317_meal_thresholds),
    1318: ('Long-window stability', exp_1318_long_stability),
    1319: ('Loop-observed ISF', exp_1319_loop_isf),
    1320: ('Cross-patient UAM transfer', exp_1320_uam_transfer),
}


def main():
    parser = argparse.ArgumentParser(
        description='EXP-1311-1320: UAM-aware therapy & cross-patient transfer')
    parser.add_argument('--exp', type=int, help='Run single experiment')
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--max-patients', type=int, default=11)
    args = parser.parse_args()

    patients = load_patients(PATIENTS_DIR, max_patients=args.max_patients)
    print(f"Loaded {len(patients)} patients")

    # Precondition assessment
    precond_results = {}
    for p in patients:
        precond_results[p['name']] = assess_preconditions(p)

    # Run experiments
    exps_to_run = [args.exp] if args.exp else sorted(EXPERIMENTS.keys())
    all_results = {}
    for eid in exps_to_run:
        if eid not in EXPERIMENTS:
            print(f"Unknown experiment: {eid}")
            continue
        name, func = EXPERIMENTS[eid]
        print(f"\nEXP-{eid}: {name}")
        t0 = time.time()
        try:
            result = func(patients, detail=args.detail,
                          preconditions=precond_results)
            result['elapsed_sec'] = round(time.time() - t0, 1)
            all_results[eid] = result
            # Print summary
            n_pp = len(result.get('per_patient', []))
            print(f"  {n_pp} patients processed in {result['elapsed_sec']}s")
            if args.save:
                fname = f'exp-{eid}_therapy.json'
                with open(fname, 'w') as f:
                    json.dump(result, f, indent=2, default=str)
                print(f"  Saved → {fname}")
        except Exception as e:
            import traceback
            traceback.print_exc()
            all_results[eid] = {'error': str(e)}

    return all_results


if __name__ == '__main__':
    main()
