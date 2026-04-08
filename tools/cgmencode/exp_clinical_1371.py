#!/usr/bin/env python3
"""EXP-1371–1380: ISF Deconfounding, Loop-Aware Simulation, Threshold Optimization

Addresses key gaps from EXP-1351-1360:
1. ISF systematically overestimated for well-cal patients → deconfound (EXP-1371)
2. Simple simulation fails 0/11 → loop-aware simulation (EXP-1372)
3. CR tightening works but needs validation against actuals (EXP-1373)
4. Triage over-triggers on well-cal → threshold optimization (EXP-1374)
5. ISF + exercise + UAM combined deconfounding (EXP-1375)
6. Basal recommendation precision → dose-response curve (EXP-1376)
7. Recommendation stability over rolling windows (EXP-1377)
8. Archetype-specific recommendation profiles (EXP-1378)
9. Confidence calibration → how often are high-conf recs correct? (EXP-1379)
10. Composite score: single therapy health metric (EXP-1380)
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
from cgmencode.exp_clinical_1311 import compute_uam_supply

PATIENTS_DIR = str(Path(__file__).resolve().parent.parent.parent
                   / 'externals' / 'ns-data' / 'patients')
OUTPUT_DIR = str(Path(__file__).resolve().parent.parent.parent
                 / 'externals' / 'experiments')

GLUCOSE_SCALE = 400.0
STEPS_PER_HOUR = 12
STEPS_PER_DAY = 288
DIA_STEPS = STEPS_PER_HOUR * 5

BLOCK_NAMES = ['overnight(0-6)', 'morning(6-10)', 'midday(10-14)',
               'afternoon(14-18)', 'evening(18-22)', 'night(22-24)']
BLOCK_RANGES = [(0, 6), (6, 10), (10, 14), (14, 18), (18, 22), (22, 24)]

ARCHETYPES = {
    'well-calibrated': ['d', 'h', 'j', 'k'],
    'needs-tuning': ['b', 'c', 'e', 'f', 'g', 'i'],
    'miscalibrated': ['a'],
}
PATIENT_ARCHETYPE = {}
for arch, members in ARCHETYPES.items():
    for m in members:
        PATIENT_ARCHETYPE[m] = arch

TAU_CANDIDATES = [0.3, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0]


def get_time_block_idx(step_in_day):
    hour = (step_in_day / STEPS_PER_HOUR) % 24
    for i, (lo, hi) in enumerate(BLOCK_RANGES):
        if lo <= hour < hi:
            return i
    return 5


def fit_correction_events(glucose, bolus, carbs, n, min_bolus=0.3,
                          min_bg=150, exercise_mask=None, uam_thresh=0.90,
                          uam_mask=None):
    """Fit exponential decay to correction events with configurable gates.

    Returns list of event dicts with tau, isf, r2, etc.
    """
    events = []
    window = 3 * STEPS_PER_HOUR
    for i in range(n):
        if bolus[i] < min_bolus or np.isnan(glucose[i]) or glucose[i] <= min_bg:
            continue
        cw = slice(max(0, i - 6), min(n, i + 6))
        if np.sum(carbs[cw]) > 2:
            continue
        if i + window >= n:
            continue
        if np.sum(bolus[i + 1:i + window]) > 0.5:
            continue
        if np.sum(carbs[i + 1:i + window]) > 2:
            continue
        # Exercise gate
        if exercise_mask is not None:
            ex_window = exercise_mask[i:i + window]
            if np.any(ex_window):
                continue
        # UAM gate
        if uam_mask is not None and uam_thresh < 1.0:
            uam_frac = float(uam_mask[i:i + window].sum()) / window
            if uam_frac > uam_thresh:
                continue
        traj = glucose[i:i + window]
        tv = ~np.isnan(traj)
        if tv.sum() < window * 0.5:
            continue
        bg_start = float(traj[0])
        t_hours = np.arange(window) * (5.0 / 60.0)
        best_sse, best_amp, best_tau = np.inf, 0.0, 2.0
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
                best_sse, best_amp, best_tau = sse, amp, tau_c
        if best_amp >= 5:
            pred = bg_start - best_amp * (1 - np.exp(-t_hours / best_tau))
            ss_res = float(np.sum((traj[tv] - pred[tv]) ** 2))
            ss_tot = float(np.sum((traj[tv] - np.mean(traj[tv])) ** 2))
            fit_r2 = 1 - ss_res / (ss_tot + 1e-10)
            events.append({
                'tau': best_tau, 'isf': best_amp / float(bolus[i]),
                'r2': fit_r2, 'step': i,
                'hour': (i % STEPS_PER_DAY) / STEPS_PER_HOUR,
                'bolus': float(bolus[i]),
                'bg_start': bg_start,
                'drop': best_amp,
            })
    return events


def compute_fasting_drift(glucose, bolus, carbs, n, block_mask, valid):
    """Compute fasting glucose drift in a block (mg/dL per hour)."""
    fasting = np.ones(n, dtype=bool)
    for i in range(n):
        ws = max(0, i - STEPS_PER_HOUR * 2)
        we = min(n, i + STEPS_PER_HOUR * 2)
        if np.any(bolus[ws:we] > 0) or np.any(carbs[ws:we] > 0):
            fasting[i] = False
    dg = np.diff(glucose)
    dg = np.append(dg, 0)
    mask = fasting & valid & block_mask & ~np.isnan(dg) & (np.abs(dg) < 50)
    if mask.sum() < STEPS_PER_HOUR:
        return None, 0
    return float(np.mean(dg[mask])) * STEPS_PER_HOUR, int(mask.sum())


def detect_exercise(df, pk, n):
    """Detect exercise periods: negative residual + low demand."""
    sd, uam_sup, uam_mask, _ = compute_uam_supply(df, pk)
    glucose = df['glucose'].values.astype(float)
    dg = np.diff(glucose)
    dg = np.append(dg, 0)
    valid = ~np.isnan(glucose) & ~np.isnan(dg) & (np.abs(dg) < 50)
    net_flux = sd['net']
    demand = sd['demand']
    demand_med = float(np.nanmedian(demand[valid]))
    exercise = np.zeros(n, dtype=bool)
    for i in range(n):
        if not valid[i]:
            continue
        residual = dg[i] - net_flux[i]
        if residual < -2.0 and demand[i] < demand_med:
            exercise[i] = True
    # Expand by ±1h
    expanded = exercise.copy()
    for i in range(n):
        if exercise[i]:
            s = max(0, i - STEPS_PER_HOUR)
            e = min(n, i + STEPS_PER_HOUR)
            expanded[s:e] = True
    return expanded, uam_mask, sd


def get_meal_excursions(glucose, bolus, carbs, n, blo=0, bhi=24):
    """Get post-meal excursions in a time window."""
    excursions = []
    last_meal = -3 * STEPS_PER_HOUR
    for i in range(n):
        if carbs[i] < 5 or (i - last_meal) < 2 * STEPS_PER_HOUR:
            continue
        hour = (i % STEPS_PER_DAY) / STEPS_PER_HOUR
        if not (blo <= hour < bhi):
            continue
        last_meal = i
        post_end = min(n, i + 3 * STEPS_PER_HOUR)
        if post_end - i < STEPS_PER_HOUR:
            continue
        pre = glucose[max(0, i - 3):i + 1]
        pre = pre[~np.isnan(pre)]
        if len(pre) == 0:
            continue
        post_g = glucose[i:post_end]
        if np.all(np.isnan(post_g)):
            continue
        excursions.append({
            'excursion': float(np.nanmax(post_g)) - float(np.mean(pre)),
            'step': i,
            'carbs': float(carbs[i]),
            'bolus': float(np.sum(bolus[max(0, i - 2):min(n, i + 6)])),
        })
    return excursions


# ─── EXP-1371: ISF Deconfounded Estimation ──────────────────────────

def exp_1371_isf_deconfounded(patients, detail=False, preconditions=None):
    """ISF estimation gated on bolus ≥2U, exercise-free, 90% UAM threshold.

    Combines all three improvements from EXP-1355/1360 findings.
    """
    results = {'name': 'EXP-1371: ISF deconfounded estimation',
               'n_patients': len(patients), 'per_patient': []}

    CONFIGS = [
        ('baseline', {'min_bolus': 0.3, 'exercise': False, 'uam_thresh': 1.0}),
        ('bolus_gate', {'min_bolus': 2.0, 'exercise': False, 'uam_thresh': 1.0}),
        ('exercise_free', {'min_bolus': 0.3, 'exercise': True, 'uam_thresh': 1.0}),
        ('uam_90', {'min_bolus': 0.3, 'exercise': False, 'uam_thresh': 0.90}),
        ('all_combined', {'min_bolus': 2.0, 'exercise': True, 'uam_thresh': 0.90}),
        ('strict', {'min_bolus': 3.0, 'exercise': True, 'uam_thresh': 0.70}),
    ]

    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        n = len(glucose)
        isf_profile = float(np.nanmean(pk[:, 7] * 200.0))

        exercise_mask, uam_mask, _ = detect_exercise(df, pk, n)

        config_results = {}
        for cname, cfg in CONFIGS:
            events = fit_correction_events(
                glucose, bolus, carbs, n,
                min_bolus=cfg['min_bolus'],
                exercise_mask=exercise_mask if cfg['exercise'] else None,
                uam_thresh=cfg['uam_thresh'],
                uam_mask=uam_mask,
            )
            if events:
                isfs = [e['isf'] for e in events]
                r2s = [e['r2'] for e in events]
                config_results[cname] = {
                    'n_events': len(events),
                    'median_isf': round(float(np.median(isfs)), 1),
                    'isf_ratio': round(float(np.median(isfs)) / (isf_profile + 1e-6), 2),
                    'isf_cv': round(float(np.std(isfs)) / (float(np.mean(isfs)) + 1e-6), 2),
                    'mean_r2': round(float(np.mean(r2s)), 3),
                    'mean_bolus': round(float(np.mean([e['bolus'] for e in events])), 2),
                }
            else:
                config_results[cname] = {'n_events': 0}

        # Best config: lowest ISF CV with ≥5 events
        valid_configs = {k: v for k, v in config_results.items()
                         if v.get('n_events', 0) >= 5}
        if valid_configs:
            best = min(valid_configs, key=lambda k: valid_configs[k].get('isf_cv', 99))
            best_isf_ratio = valid_configs[best].get('isf_ratio', 1.0)
        else:
            best = 'baseline'
            best_isf_ratio = config_results.get('baseline', {}).get('isf_ratio', 1.0)

        results['per_patient'].append({
            'patient': p['name'],
            'archetype': PATIENT_ARCHETYPE.get(p['name'], 'unknown'),
            'profile_isf': round(isf_profile, 1),
            'best_config': best,
            'best_isf_ratio': best_isf_ratio,
            'configs': config_results if detail else {
                k: {'n': v.get('n_events', 0), 'ratio': v.get('isf_ratio', '?'),
                     'cv': v.get('isf_cv', '?')}
                for k, v in config_results.items()
            },
        })

    pp = results['per_patient']
    well_cal = [r for r in pp if r.get('archetype') == 'well-calibrated']
    needs_tuning = [r for r in pp if r.get('archetype') == 'needs-tuning']

    if well_cal:
        for cname, _ in CONFIGS:
            ratios = [r['configs'].get(cname, {}).get('isf_ratio',
                      r['configs'].get(cname, {}).get('ratio', None))
                      for r in well_cal]
            ratios = [r for r in ratios if r is not None and r != '?']
            if ratios:
                results[f'well_cal_{cname}_ratio'] = round(float(np.mean(ratios)), 2)

    config_votes = defaultdict(int)
    for r in pp:
        config_votes[r.get('best_config', '?')] += 1
    results['best_config_distribution'] = dict(config_votes)
    return results


# ─── EXP-1372: Loop-Aware Basal Simulation ──────────────────────────

def exp_1372_loop_aware_sim(patients, detail=False, preconditions=None):
    """Simulate basal changes accounting for AID loop dampening."""
    results = {'name': 'EXP-1372: Loop-aware basal simulation',
               'n_patients': len(patients), 'per_patient': []}

    TARGET_BG = 110.0

    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        temp_rate = df['temp_rate'].values
        n = len(glucose)
        valid = ~np.isnan(glucose)
        isf_profile = float(np.nanmean(pk[:, 7] * 200.0))
        scheduled_rate = get_scheduled_basal_rate(p)

        if valid.sum() < STEPS_PER_DAY or scheduled_rate < 0.01:
            results['per_patient'].append({
                'patient': p['name'], 'note': 'Insufficient data'})
            continue

        gv = glucose[valid]
        current_tir = float(np.sum((gv >= 70) & (gv <= 180))) / len(gv) * 100

        # Estimate loop gain K (from EXP-1359)
        gains = []
        for i in range(n):
            if not valid[i] or abs(glucose[i] - TARGET_BG) < 10:
                continue
            tr = float(temp_rate[i]) if not np.isnan(temp_rate[i]) else scheduled_rate
            k = (tr / scheduled_rate - 1) * isf_profile / (TARGET_BG - glucose[i])
            if -5 < k < 5:
                gains.append(k)
        K = float(np.median(gains)) if len(gains) > 100 else 0.3

        # Overnight drift
        overnight_mask = np.zeros(n, dtype=bool)
        for i in range(n):
            hour = (i % STEPS_PER_DAY) / STEPS_PER_HOUR
            if 0 <= hour < 6:
                overnight_mask[i] = True
        drift, n_drift = compute_fasting_drift(glucose, bolus, carbs, n,
                                                overnight_mask, valid)
        drift = drift if drift is not None else 0.0

        # Recommended basal change (drift-based, dampening-compensated)
        dampening = abs(K) / (1 + abs(K))
        effective_frac = 1 - dampening
        raw_change = drift / (isf_profile + 1e-6)
        compensated_change = raw_change / (effective_frac + 1e-6)
        compensated_change = max(-0.5, min(0.5, compensated_change))

        # Simulate with loop-aware model
        simulated = glucose.copy()
        for i in range(n):
            if np.isnan(glucose[i]):
                continue
            bg_error = glucose[i] - TARGET_BG

            # Without basal change, loop adjusts by K * bg_error / ISF
            current_loop_adj = K * bg_error / (isf_profile + 1e-6)

            # With basal change, effective insulin changes, loop re-adjusts
            # Net effect: basal_change * effective_frac * ISF
            net_bg_change = -compensated_change * effective_frac * isf_profile / STEPS_PER_HOUR
            net_bg_change = max(-2, min(2, net_bg_change))

            simulated[i] = glucose[i] + net_bg_change

        sv = simulated[valid]
        sim_tir = float(np.sum((sv >= 70) & (sv <= 180))) / len(sv) * 100
        sim_tbr = float(np.sum(sv < 70)) / len(sv) * 100

        results['per_patient'].append({
            'patient': p['name'],
            'archetype': PATIENT_ARCHETYPE.get(p['name'], 'unknown'),
            'estimated_K': round(K, 3),
            'dampening_pct': round(dampening * 100, 1),
            'overnight_drift': round(drift, 2),
            'raw_basal_change': round(raw_change, 3),
            'compensated_change': round(compensated_change, 3),
            'current_tir': round(current_tir, 1),
            'simulated_tir': round(sim_tir, 1),
            'tir_change': round(sim_tir - current_tir, 1),
            'simulated_tbr': round(sim_tbr, 1),
        })

    pp = [r for r in results['per_patient'] if 'current_tir' in r]
    if pp:
        results['n_patients_with_data'] = len(pp)
        results['mean_tir_change'] = round(
            float(np.mean([r['tir_change'] for r in pp])), 1)
        results['n_improved'] = sum(1 for r in pp if r['tir_change'] > 0.5)
        results['n_worsened'] = sum(1 for r in pp if r['tir_change'] < -0.5)
        results['mean_tbr'] = round(
            float(np.mean([r['simulated_tbr'] for r in pp])), 1)
    return results


# ─── EXP-1373: CR Recommendation Validation ─────────────────────────

def exp_1373_cr_validation(patients, detail=False, preconditions=None):
    """Validate CR recommendations by comparing first-half prediction to second-half."""
    results = {'name': 'EXP-1373: CR recommendation validation',
               'n_patients': len(patients), 'per_patient': []}

    for p in patients:
        df = p['df']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        n = len(glucose)
        mid = n // 2

        MEAL_BLOCKS = [('breakfast', 6, 10), ('lunch', 10, 14),
                       ('dinner', 14, 20), ('late', 20, 24)]

        block_results = {}
        for bname, blo, bhi in MEAL_BLOCKS:
            # First half
            exc_h1 = get_meal_excursions(glucose[:mid], bolus[:mid], carbs[:mid],
                                          mid, blo, bhi)
            # Second half
            exc_h2 = get_meal_excursions(glucose[mid:], bolus[mid:], carbs[mid:],
                                          n - mid, blo, bhi)

            if len(exc_h1) >= 3 and len(exc_h2) >= 3:
                mean_h1 = float(np.mean([e['excursion'] for e in exc_h1]))
                mean_h2 = float(np.mean([e['excursion'] for e in exc_h2]))
                # Would h1-based recommendation help h2?
                h1_flag = mean_h1 > 60
                h2_flag = mean_h2 > 60
                agreement = h1_flag == h2_flag

                block_results[bname] = {
                    'n_h1': len(exc_h1), 'n_h2': len(exc_h2),
                    'mean_h1': round(mean_h1, 1),
                    'mean_h2': round(mean_h2, 1),
                    'h1_flag': h1_flag, 'h2_flag': h2_flag,
                    'agreement': agreement,
                    'drift': round(mean_h2 - mean_h1, 1),
                }
            else:
                block_results[bname] = {
                    'n_h1': len(exc_h1), 'n_h2': len(exc_h2),
                    'note': 'insufficient_data',
                }

        n_agree = sum(1 for v in block_results.values()
                      if v.get('agreement') is True)
        n_total = sum(1 for v in block_results.values()
                      if v.get('agreement') is not None)

        results['per_patient'].append({
            'patient': p['name'],
            'blocks': block_results,
            'agreement_rate': round(n_agree / max(1, n_total), 2),
            'n_blocks_assessed': n_total,
        })

    pp = [r for r in results['per_patient'] if r.get('n_blocks_assessed', 0) > 0]
    if pp:
        results['n_patients_with_data'] = len(pp)
        results['mean_agreement_rate'] = round(
            float(np.mean([r['agreement_rate'] for r in pp])), 2)
        # Per-block agreement
        for bname, _, _ in [('breakfast', 6, 10), ('lunch', 10, 14),
                             ('dinner', 14, 20), ('late', 20, 24)]:
            agrees = [r['blocks'].get(bname, {}).get('agreement')
                      for r in pp if bname in r.get('blocks', {})]
            agrees = [a for a in agrees if a is not None]
            if agrees:
                results[f'{bname}_agreement'] = round(sum(agrees) / len(agrees), 2)
    return results


# ─── EXP-1374: Threshold Optimization ───────────────────────────────

def exp_1374_threshold_opt(patients, detail=False, preconditions=None):
    """Sweep drift, excursion, ISF ratio thresholds to minimize false positives
    on well-calibrated patients while catching real issues in needs-tuning."""
    results = {'name': 'EXP-1374: Threshold optimization',
               'n_patients': len(patients), 'per_patient': []}

    DRIFT_THRESHOLDS = [3.0, 5.0, 7.0, 10.0]
    EXC_THRESHOLDS = [40, 50, 60, 70, 80]
    ISF_THRESHOLDS = [1.2, 1.5, 2.0, 3.0, 5.0]

    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        n = len(glucose)
        valid = ~np.isnan(glucose)
        isf_profile = float(np.nanmean(pk[:, 7] * 200.0))
        archetype = PATIENT_ARCHETYPE.get(p['name'], 'unknown')

        # Overnight drift
        overnight_mask = np.zeros(n, dtype=bool)
        for i in range(n):
            hour = (i % STEPS_PER_DAY) / STEPS_PER_HOUR
            if 0 <= hour < 6:
                overnight_mask[i] = True
        drift, _ = compute_fasting_drift(glucose, bolus, carbs, n, overnight_mask, valid)
        drift = abs(drift) if drift is not None else 0.0

        # Meal excursions
        exc = get_meal_excursions(glucose, bolus, carbs, n)
        mean_exc = float(np.mean([e['excursion'] for e in exc])) if exc else 0.0

        # ISF ratio (using deconfounded method)
        exercise_mask, uam_mask, _ = detect_exercise(df, pk, n)
        events = fit_correction_events(glucose, bolus, carbs, n, min_bolus=2.0,
                                        exercise_mask=exercise_mask,
                                        uam_thresh=0.90, uam_mask=uam_mask)
        isf_ratio = (float(np.median([e['isf'] for e in events])) / (isf_profile + 1e-6)
                     if len(events) >= 3 else 1.0)

        sweep = {}
        for dt in DRIFT_THRESHOLDS:
            for et in EXC_THRESHOLDS:
                for it in ISF_THRESHOLDS:
                    n_actions = 0
                    if drift > dt:
                        n_actions += 1
                    if mean_exc > et:
                        n_actions += 1
                    if abs(isf_ratio - 1.0) > (it - 1.0):
                        n_actions += 1
                    key = f'd{dt}_e{et}_i{it}'
                    sweep[key] = n_actions

        results['per_patient'].append({
            'patient': p['name'],
            'archetype': archetype,
            'drift': round(drift, 2),
            'mean_excursion': round(mean_exc, 1),
            'isf_ratio': round(isf_ratio, 2),
            'n_deconfounded_events': len(events),
            'sweep': sweep if detail else {},
        })

    # Find threshold combo that minimizes well-cal actions while keeping needs-tuning ≥ 1
    pp = results['per_patient']
    well_cal = [r for r in pp if r.get('archetype') == 'well-calibrated']
    needs_t = [r for r in pp if r.get('archetype') == 'needs-tuning']

    best_score = 999
    best_combo = None
    for dt in DRIFT_THRESHOLDS:
        for et in EXC_THRESHOLDS:
            for it in ISF_THRESHOLDS:
                wc_actions = []
                nt_actions = []
                for r in well_cal:
                    n_act = 0
                    if r['drift'] > dt: n_act += 1
                    if r['mean_excursion'] > et: n_act += 1
                    if abs(r['isf_ratio'] - 1.0) > (it - 1.0): n_act += 1
                    wc_actions.append(n_act)
                for r in needs_t:
                    n_act = 0
                    if r['drift'] > dt: n_act += 1
                    if r['mean_excursion'] > et: n_act += 1
                    if abs(r['isf_ratio'] - 1.0) > (it - 1.0): n_act += 1
                    nt_actions.append(n_act)

                wc_mean = float(np.mean(wc_actions)) if wc_actions else 0
                nt_mean = float(np.mean(nt_actions)) if nt_actions else 0

                # Score: minimize well-cal FP, penalize low needs-tuning detection
                score = wc_mean * 3 + max(0, 1 - nt_mean) * 5
                if score < best_score:
                    best_score = score
                    best_combo = {
                        'drift_threshold': dt,
                        'excursion_threshold': et,
                        'isf_ratio_threshold': it,
                        'well_cal_mean_actions': round(wc_mean, 2),
                        'needs_tuning_mean_actions': round(nt_mean, 2),
                        'score': round(score, 2),
                    }

    results['optimal_thresholds'] = best_combo

    # Also show current thresholds (d=5, e=60, i=1.2) performance
    current_wc = []
    current_nt = []
    for r in well_cal:
        n_act = 0
        if r['drift'] > 5: n_act += 1
        if r['mean_excursion'] > 60: n_act += 1
        if abs(r['isf_ratio'] - 1.0) > 0.2: n_act += 1
        current_wc.append(n_act)
    for r in needs_t:
        n_act = 0
        if r['drift'] > 5: n_act += 1
        if r['mean_excursion'] > 60: n_act += 1
        if abs(r['isf_ratio'] - 1.0) > 0.2: n_act += 1
        current_nt.append(n_act)
    results['current_thresholds'] = {
        'drift': 5, 'excursion': 60, 'isf_ratio': 1.2,
        'well_cal_mean_actions': round(float(np.mean(current_wc)), 2) if current_wc else 0,
        'needs_tuning_mean_actions': round(float(np.mean(current_nt)), 2) if current_nt else 0,
    }
    return results


# ─── EXP-1375: Combined ISF Pipeline ────────────────────────────────

def exp_1375_combined_isf(patients, detail=False, preconditions=None):
    """Full ISF pipeline: bolus gate + exercise filter + deconfounded estimation.
    Compare to naive baseline and quantify improvement."""
    results = {'name': 'EXP-1375: Combined ISF pipeline',
               'n_patients': len(patients), 'per_patient': []}

    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        n = len(glucose)
        isf_profile = float(np.nanmean(pk[:, 7] * 200.0))

        exercise_mask, uam_mask, _ = detect_exercise(df, pk, n)

        # Naive ISF (all corrections, no filtering)
        naive_events = fit_correction_events(glucose, bolus, carbs, n)
        # Deconfounded ISF (bolus ≥2U, exercise-free, UAM 90%)
        deconf_events = fit_correction_events(
            glucose, bolus, carbs, n, min_bolus=2.0,
            exercise_mask=exercise_mask, uam_thresh=0.90, uam_mask=uam_mask)

        naive_isf = float(np.median([e['isf'] for e in naive_events])) if naive_events else isf_profile
        deconf_isf = float(np.median([e['isf'] for e in deconf_events])) if deconf_events else isf_profile
        naive_cv = (float(np.std([e['isf'] for e in naive_events])) /
                    (float(np.mean([e['isf'] for e in naive_events])) + 1e-6)
                    if len(naive_events) >= 3 else 99.0)
        deconf_cv = (float(np.std([e['isf'] for e in deconf_events])) /
                     (float(np.mean([e['isf'] for e in deconf_events])) + 1e-6)
                     if len(deconf_events) >= 3 else 99.0)

        # Split-half stability: first half vs second half ISF
        mid = n // 2
        deconf_h1 = fit_correction_events(
            glucose[:mid], bolus[:mid], carbs[:mid], mid, min_bolus=2.0,
            exercise_mask=exercise_mask[:mid], uam_thresh=0.90,
            uam_mask=uam_mask[:mid])
        deconf_h2 = fit_correction_events(
            glucose[mid:], bolus[mid:], carbs[mid:], n - mid, min_bolus=2.0,
            exercise_mask=exercise_mask[mid:], uam_thresh=0.90,
            uam_mask=uam_mask[mid:])

        isf_h1 = float(np.median([e['isf'] for e in deconf_h1])) if deconf_h1 else deconf_isf
        isf_h2 = float(np.median([e['isf'] for e in deconf_h2])) if deconf_h2 else deconf_isf
        stability = 1 - abs(isf_h1 - isf_h2) / (max(isf_h1, isf_h2) + 1e-6)

        results['per_patient'].append({
            'patient': p['name'],
            'archetype': PATIENT_ARCHETYPE.get(p['name'], 'unknown'),
            'profile_isf': round(isf_profile, 1),
            'naive_isf': round(naive_isf, 1),
            'naive_ratio': round(naive_isf / (isf_profile + 1e-6), 2),
            'naive_cv': round(naive_cv, 2),
            'naive_n': len(naive_events),
            'deconf_isf': round(deconf_isf, 1),
            'deconf_ratio': round(deconf_isf / (isf_profile + 1e-6), 2),
            'deconf_cv': round(deconf_cv, 2),
            'deconf_n': len(deconf_events),
            'cv_improvement': round(naive_cv - deconf_cv, 2),
            'split_half_stability': round(stability, 2),
        })

    pp = results['per_patient']
    well_cal = [r for r in pp if r.get('archetype') == 'well-calibrated']
    if well_cal:
        results['well_cal_naive_ratio'] = round(
            float(np.mean([r['naive_ratio'] for r in well_cal])), 2)
        results['well_cal_deconf_ratio'] = round(
            float(np.mean([r['deconf_ratio'] for r in well_cal])), 2)
        results['well_cal_cv_improvement'] = round(
            float(np.mean([r['cv_improvement'] for r in well_cal])), 2)
    all_valid = [r for r in pp if r.get('deconf_n', 0) >= 3]
    if all_valid:
        results['mean_cv_improvement'] = round(
            float(np.mean([r['cv_improvement'] for r in all_valid])), 2)
        results['mean_stability'] = round(
            float(np.mean([r['split_half_stability'] for r in all_valid])), 2)
    return results


# ─── EXP-1376: Basal Dose-Response Curve ─────────────────────────────

def exp_1376_basal_dose_response(patients, detail=False, preconditions=None):
    """Map relationship between basal rate and overnight drift across patients."""
    results = {'name': 'EXP-1376: Basal dose-response curve',
               'n_patients': len(patients), 'per_patient': []}

    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        temp_rate = df['temp_rate'].values
        n = len(glucose)
        valid = ~np.isnan(glucose)
        scheduled_rate = get_scheduled_basal_rate(p)

        # Bin nights by actual temp_rate level
        night_drifts = []
        for day_start in range(0, n - STEPS_PER_DAY, STEPS_PER_DAY):
            # Overnight window: 0-6h within each day
            overnight_start = day_start
            overnight_end = day_start + 6 * STEPS_PER_HOUR
            if overnight_end > n:
                continue

            window = slice(overnight_start, overnight_end)
            g_window = glucose[window]
            b_window = bolus[window]
            c_window = carbs[window]
            tr_window = temp_rate[window]

            # Skip if any bolus/carbs
            if np.any(b_window > 0) or np.any(c_window > 0):
                continue

            v = ~np.isnan(g_window)
            if v.sum() < 3 * STEPS_PER_HOUR:
                continue

            drift = (float(np.nanmean(g_window[v][-6:])) -
                     float(np.nanmean(g_window[v][:6])))
            drift_per_h = drift / 6.0

            tr_valid = tr_window[~np.isnan(tr_window)]
            mean_tr = float(np.mean(tr_valid)) if len(tr_valid) > 0 else scheduled_rate
            rate_ratio = mean_tr / (scheduled_rate + 1e-6)

            night_drifts.append({
                'drift_per_h': drift_per_h,
                'mean_temp_rate': mean_tr,
                'rate_ratio': rate_ratio,
            })

        if len(night_drifts) < 5:
            results['per_patient'].append({
                'patient': p['name'], 'n_nights': len(night_drifts),
                'note': 'Too few clean overnights'})
            continue

        # Bin by rate ratio
        drifts = np.array([nd['drift_per_h'] for nd in night_drifts])
        ratios = np.array([nd['rate_ratio'] for nd in night_drifts])

        bins = [0.0, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0]
        dose_response = []
        for b_lo, b_hi in zip(bins[:-1], bins[1:]):
            mask = (ratios >= b_lo) & (ratios < b_hi)
            if mask.sum() >= 2:
                dose_response.append({
                    'rate_range': f'{b_lo}-{b_hi}',
                    'n_nights': int(mask.sum()),
                    'mean_drift': round(float(np.mean(drifts[mask])), 2),
                    'std_drift': round(float(np.std(drifts[mask])), 2),
                })

        # Linear fit: drift = a * rate_ratio + b
        if len(ratios) >= 5 and np.std(ratios) > 1e-6:
            try:
                coeffs = np.polyfit(ratios, drifts, 1)
                zero_drift_ratio = -coeffs[1] / (coeffs[0] + 1e-10)
                ss_res = np.sum((drifts - np.polyval(coeffs, ratios)) ** 2)
                ss_tot = np.sum((drifts - np.mean(drifts)) ** 2)
                r2 = 1 - ss_res / (ss_tot + 1e-10) if ss_tot > 1e-10 else 0.0
            except np.linalg.LinAlgError:
                zero_drift_ratio, r2 = 1.0, 0.0
                coeffs = [0, 0]
        else:
            zero_drift_ratio, r2 = 1.0, 0.0
            coeffs = [0, 0]

        results['per_patient'].append({
            'patient': p['name'],
            'n_clean_nights': len(night_drifts),
            'scheduled_rate': round(scheduled_rate, 3),
            'slope': round(float(coeffs[0]), 2),
            'intercept': round(float(coeffs[1]), 2),
            'zero_drift_ratio': round(float(zero_drift_ratio), 2),
            'optimal_rate': round(scheduled_rate * float(zero_drift_ratio), 3),
            'fit_r2': round(float(r2), 3),
            'dose_response': dose_response if detail else [],
        })

    pp = [r for r in results['per_patient'] if r.get('fit_r2') is not None]
    if pp:
        results['n_patients_with_data'] = len(pp)
        results['mean_fit_r2'] = round(
            float(np.mean([r['fit_r2'] for r in pp])), 3)
        results['mean_zero_drift_ratio'] = round(
            float(np.mean([r['zero_drift_ratio'] for r in pp])), 2)
    return results


# ─── EXP-1377: Recommendation Rolling Stability ─────────────────────

def exp_1377_rolling_stability(patients, detail=False, preconditions=None):
    """Check if recommendations change over rolling 30-day windows."""
    results = {'name': 'EXP-1377: Recommendation rolling stability',
               'n_patients': len(patients), 'per_patient': []}
    WINDOW_DAYS = 30
    WINDOW_STEPS = WINDOW_DAYS * STEPS_PER_DAY

    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        n = len(glucose)
        valid = ~np.isnan(glucose)
        isf_profile = float(np.nanmean(pk[:, 7] * 200.0))

        windows = []
        for start in range(0, n - WINDOW_STEPS, WINDOW_STEPS // 2):
            end = start + WINDOW_STEPS
            if end > n:
                break

            g_w = glucose[start:end]
            b_w = bolus[start:end]
            c_w = carbs[start:end]
            n_w = len(g_w)
            v_w = ~np.isnan(g_w)

            # Drift
            on_mask = np.zeros(n_w, dtype=bool)
            for i in range(n_w):
                hour = ((start + i) % STEPS_PER_DAY) / STEPS_PER_HOUR
                if 0 <= hour < 6:
                    on_mask[i] = True
            drift, _ = compute_fasting_drift(g_w, b_w, c_w, n_w, on_mask, v_w)
            drift = drift if drift is not None else 0.0

            # Excursion
            exc = get_meal_excursions(g_w, b_w, c_w, n_w, 14, 20)
            mean_exc = float(np.mean([e['excursion'] for e in exc])) if exc else 0.0

            # ISF
            events = fit_correction_events(g_w, b_w, c_w, n_w, min_bolus=2.0)
            isf = (float(np.median([e['isf'] for e in events]))
                   if len(events) >= 3 else isf_profile)

            windows.append({
                'window_start_day': start // STEPS_PER_DAY,
                'drift': round(drift, 2),
                'dinner_excursion': round(mean_exc, 1),
                'isf': round(isf, 1),
                'n_meals': len(exc),
                'n_corrections': len(events),
            })

        if len(windows) < 3:
            results['per_patient'].append({
                'patient': p['name'], 'n_windows': len(windows),
                'note': 'Too few windows'})
            continue

        # Stability metrics
        drifts = [w['drift'] for w in windows]
        excs = [w['dinner_excursion'] for w in windows]
        isfs = [w['isf'] for w in windows]

        drift_stable = float(np.std(drifts)) < 3.0
        exc_stable = float(np.std(excs)) < 20.0
        isf_stable = float(np.std(isfs)) / (float(np.mean(isfs)) + 1e-6) < 0.3

        # Would recommendation change between windows?
        rec_changes = 0
        for i in range(1, len(windows)):
            if (abs(drifts[i]) > 5) != (abs(drifts[i - 1]) > 5):
                rec_changes += 1
            if (excs[i] > 60) != (excs[i - 1] > 60):
                rec_changes += 1

        results['per_patient'].append({
            'patient': p['name'],
            'n_windows': len(windows),
            'drift_std': round(float(np.std(drifts)), 2),
            'excursion_std': round(float(np.std(excs)), 1),
            'isf_cv': round(float(np.std(isfs)) / (float(np.mean(isfs)) + 1e-6), 2),
            'drift_stable': drift_stable,
            'excursion_stable': exc_stable,
            'isf_stable': isf_stable,
            'all_stable': drift_stable and exc_stable and isf_stable,
            'rec_changes': rec_changes,
            'windows': windows if detail else [],
        })

    pp = [r for r in results['per_patient'] if r.get('n_windows', 0) >= 3]
    if pp:
        results['n_patients_with_data'] = len(pp)
        results['n_all_stable'] = sum(1 for r in pp if r.get('all_stable'))
        results['mean_rec_changes'] = round(
            float(np.mean([r['rec_changes'] for r in pp])), 1)
    return results


# ─── EXP-1378: Archetype-Specific Recommendations ───────────────────

def exp_1378_archetype_recs(patients, detail=False, preconditions=None):
    """Generate and compare recommendation profiles per archetype."""
    results = {'name': 'EXP-1378: Archetype-specific recommendations',
               'n_patients': len(patients), 'per_patient': []}

    all_recs = []
    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        n = len(glucose)
        valid = ~np.isnan(glucose)
        isf_profile = float(np.nanmean(pk[:, 7] * 200.0))
        scheduled_rate = get_scheduled_basal_rate(p)
        archetype = PATIENT_ARCHETYPE.get(p['name'], 'unknown')

        gv = glucose[valid]
        tir = float(np.sum((gv >= 70) & (gv <= 180))) / len(gv) * 100 if len(gv) > 0 else 0

        # Overnight drift
        overnight_mask = np.zeros(n, dtype=bool)
        for i in range(n):
            hour = (i % STEPS_PER_DAY) / STEPS_PER_HOUR
            if 0 <= hour < 6:
                overnight_mask[i] = True
        drift, _ = compute_fasting_drift(glucose, bolus, carbs, n, overnight_mask, valid)
        drift = drift if drift is not None else 0.0

        # Excursions
        exc = get_meal_excursions(glucose, bolus, carbs, n)
        mean_exc = float(np.mean([e['excursion'] for e in exc])) if exc else 0.0

        # ISF (deconfounded)
        exercise_mask, uam_mask, _ = detect_exercise(df, pk, n)
        events = fit_correction_events(glucose, bolus, carbs, n, min_bolus=2.0,
                                        exercise_mask=exercise_mask,
                                        uam_thresh=0.90, uam_mask=uam_mask)
        isf_ratio = (float(np.median([e['isf'] for e in events])) / (isf_profile + 1e-6)
                     if len(events) >= 3 else 1.0)

        rec = {
            'patient': p['name'],
            'archetype': archetype,
            'tir': round(tir, 1),
            'overnight_drift': round(drift, 2),
            'mean_excursion': round(mean_exc, 1),
            'isf_ratio': round(isf_ratio, 2),
            'scheduled_rate': round(scheduled_rate, 3),
            'priority': 'basal' if abs(drift) > 5 else (
                        'cr' if mean_exc > 60 else (
                        'isf' if abs(isf_ratio - 1.0) > 1.0 else 'monitor')),
        }
        results['per_patient'].append(rec)
        all_recs.append(rec)

    # Per-archetype summary
    for arch_name, members in ARCHETYPES.items():
        arch_recs = [r for r in all_recs if r['archetype'] == arch_name]
        if arch_recs:
            results[f'{arch_name}_summary'] = {
                'n': len(arch_recs),
                'mean_tir': round(float(np.mean([r['tir'] for r in arch_recs])), 1),
                'mean_drift': round(float(np.mean([abs(r['overnight_drift']) for r in arch_recs])), 2),
                'mean_excursion': round(float(np.mean([r['mean_excursion'] for r in arch_recs])), 1),
                'mean_isf_ratio': round(float(np.mean([r['isf_ratio'] for r in arch_recs])), 2),
                'priority_dist': dict(defaultdict(int,
                    {k: sum(1 for r in arch_recs if r['priority'] == k)
                     for k in ['basal', 'cr', 'isf', 'monitor']})),
            }
    return results


# ─── EXP-1379: Confidence Calibration ───────────────────────────────

def exp_1379_confidence_calibration(patients, detail=False, preconditions=None):
    """Assess whether high-confidence recommendations are actually correct.
    Use split-half: recommend from first half, validate against second half."""
    results = {'name': 'EXP-1379: Confidence calibration',
               'n_patients': len(patients), 'per_patient': []}

    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        n = len(glucose)
        mid = n // 2
        valid = ~np.isnan(glucose)
        isf_profile = float(np.nanmean(pk[:, 7] * 200.0))

        # First half: generate recommendations
        # Drift
        on_mask_h1 = np.zeros(mid, dtype=bool)
        for i in range(mid):
            hour = (i % STEPS_PER_DAY) / STEPS_PER_HOUR
            if 0 <= hour < 6:
                on_mask_h1[i] = True
        v_h1 = ~np.isnan(glucose[:mid])
        drift_h1, n_d1 = compute_fasting_drift(glucose[:mid], bolus[:mid], carbs[:mid],
                                                 mid, on_mask_h1, v_h1)
        drift_h1 = drift_h1 if drift_h1 is not None else 0.0
        basal_conf = min(1.0, n_d1 / (STEPS_PER_DAY * 3))

        # Excursion
        exc_h1 = get_meal_excursions(glucose[:mid], bolus[:mid], carbs[:mid], mid, 14, 20)
        mean_exc_h1 = float(np.mean([e['excursion'] for e in exc_h1])) if exc_h1 else 0.0
        cr_conf = min(1.0, len(exc_h1) / 15.0)

        # ISF
        events_h1 = fit_correction_events(glucose[:mid], bolus[:mid], carbs[:mid],
                                            mid, min_bolus=2.0)
        isf_h1 = (float(np.median([e['isf'] for e in events_h1]))
                  if len(events_h1) >= 3 else isf_profile)
        isf_conf = min(1.0, len(events_h1) / 10.0)

        # Second half: validate
        on_mask_h2 = np.zeros(n - mid, dtype=bool)
        for i in range(n - mid):
            hour = ((mid + i) % STEPS_PER_DAY) / STEPS_PER_HOUR
            if 0 <= hour < 6:
                on_mask_h2[i] = True
        v_h2 = ~np.isnan(glucose[mid:])
        drift_h2, _ = compute_fasting_drift(glucose[mid:], bolus[mid:], carbs[mid:],
                                             n - mid, on_mask_h2, v_h2)
        drift_h2 = drift_h2 if drift_h2 is not None else 0.0

        exc_h2 = get_meal_excursions(glucose[mid:], bolus[mid:], carbs[mid:],
                                      n - mid, 14, 20)
        mean_exc_h2 = float(np.mean([e['excursion'] for e in exc_h2])) if exc_h2 else 0.0

        events_h2 = fit_correction_events(glucose[mid:], bolus[mid:], carbs[mid:],
                                            n - mid, min_bolus=2.0)
        isf_h2 = (float(np.median([e['isf'] for e in events_h2]))
                  if len(events_h2) >= 3 else isf_profile)

        # Agreement: does h1 recommendation match h2 reality?
        basal_agree = (abs(drift_h1) > 5) == (abs(drift_h2) > 5)
        if abs(drift_h1) > 5 and abs(drift_h2) > 5:
            basal_agree = (drift_h1 > 0) == (drift_h2 > 0)  # Same direction
        cr_agree = (mean_exc_h1 > 60) == (mean_exc_h2 > 60)
        isf_dir_h1 = 'increase' if isf_h1 / (isf_profile + 1e-6) > 2.0 else 'ok'
        isf_dir_h2 = 'increase' if isf_h2 / (isf_profile + 1e-6) > 2.0 else 'ok'
        isf_agree = isf_dir_h1 == isf_dir_h2

        results['per_patient'].append({
            'patient': p['name'],
            'basal_h1_drift': round(drift_h1, 2),
            'basal_h2_drift': round(drift_h2, 2),
            'basal_conf': round(basal_conf, 2),
            'basal_agree': basal_agree,
            'cr_h1_exc': round(mean_exc_h1, 1),
            'cr_h2_exc': round(mean_exc_h2, 1),
            'cr_conf': round(cr_conf, 2),
            'cr_agree': cr_agree,
            'isf_h1': round(isf_h1, 1),
            'isf_h2': round(isf_h2, 1),
            'isf_conf': round(isf_conf, 2),
            'isf_agree': isf_agree,
        })

    pp = results['per_patient']
    results['basal_agreement_rate'] = round(
        float(np.mean([r['basal_agree'] for r in pp])), 2)
    results['cr_agreement_rate'] = round(
        float(np.mean([r['cr_agree'] for r in pp])), 2)
    results['isf_agreement_rate'] = round(
        float(np.mean([r['isf_agree'] for r in pp])), 2)

    # Calibration: does high confidence → high agreement?
    for param in ['basal', 'cr', 'isf']:
        high_conf = [r for r in pp if r.get(f'{param}_conf', 0) > 0.5]
        low_conf = [r for r in pp if r.get(f'{param}_conf', 0) <= 0.5]
        if high_conf:
            results[f'{param}_high_conf_agreement'] = round(
                float(np.mean([r[f'{param}_agree'] for r in high_conf])), 2)
        if low_conf:
            results[f'{param}_low_conf_agreement'] = round(
                float(np.mean([r[f'{param}_agree'] for r in low_conf])), 2)
    return results


# ─── EXP-1380: Composite Therapy Health Score ────────────────────────

def exp_1380_therapy_score(patients, detail=False, preconditions=None):
    """Compute single composite therapy health score (0-100) per patient."""
    results = {'name': 'EXP-1380: Composite therapy health score',
               'n_patients': len(patients), 'per_patient': []}

    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        n = len(glucose)
        valid = ~np.isnan(glucose)
        isf_profile = float(np.nanmean(pk[:, 7] * 200.0))
        scheduled_rate = get_scheduled_basal_rate(p)
        archetype = PATIENT_ARCHETYPE.get(p['name'], 'unknown')

        gv = glucose[valid]
        if len(gv) < STEPS_PER_DAY:
            results['per_patient'].append({
                'patient': p['name'], 'note': 'Insufficient data'})
            continue

        # Component 1: TIR (0-40 points)
        tir = float(np.sum((gv >= 70) & (gv <= 180))) / len(gv) * 100
        tir_score = min(40, tir * 40 / 85)  # 85% TIR = perfect

        # Component 2: Basal health — abs(drift) (0-20 points)
        overnight_mask = np.zeros(n, dtype=bool)
        for i in range(n):
            hour = (i % STEPS_PER_DAY) / STEPS_PER_HOUR
            if 0 <= hour < 6:
                overnight_mask[i] = True
        drift, _ = compute_fasting_drift(glucose, bolus, carbs, n, overnight_mask, valid)
        drift = abs(drift) if drift is not None else 0.0
        basal_score = max(0, 20 - drift * 2)  # 0 drift = 20, 10 mg/h = 0

        # Component 3: CR health — mean excursion (0-20 points)
        exc = get_meal_excursions(glucose, bolus, carbs, n)
        mean_exc = float(np.mean([e['excursion'] for e in exc])) if exc else 0.0
        cr_score = max(0, 20 - (mean_exc - 30) * 0.25)  # 30 mg = 20, 110 mg = 0

        # Component 4: ISF alignment (0-10 points)
        events = fit_correction_events(glucose, bolus, carbs, n, min_bolus=2.0)
        if len(events) >= 3:
            isf_ratio = float(np.median([e['isf'] for e in events])) / (isf_profile + 1e-6)
            isf_score = max(0, 10 - abs(isf_ratio - 1.0) * 5)
        else:
            isf_score = 5  # Neutral if no data

        # Component 5: Low variability (0-10 points)
        glucose_cv = float(np.std(gv)) / (float(np.mean(gv)) + 1e-6)
        cv_score = max(0, 10 - glucose_cv * 30)  # CV 0.20 = 4, CV 0.33 = 0

        composite = tir_score + basal_score + cr_score + isf_score + cv_score
        composite = max(0, min(100, composite))

        grade = ('A' if composite >= 80 else
                 'B' if composite >= 65 else
                 'C' if composite >= 50 else
                 'D' if composite >= 35 else 'F')

        results['per_patient'].append({
            'patient': p['name'],
            'archetype': archetype,
            'composite_score': round(composite, 1),
            'grade': grade,
            'tir_score': round(tir_score, 1),
            'basal_score': round(basal_score, 1),
            'cr_score': round(cr_score, 1),
            'isf_score': round(isf_score, 1),
            'cv_score': round(cv_score, 1),
            'tir': round(tir, 1),
            'overnight_drift': round(drift, 2),
            'mean_excursion': round(mean_exc, 1),
        })

    pp = [r for r in results['per_patient'] if 'composite_score' in r]
    if pp:
        results['population_mean_score'] = round(
            float(np.mean([r['composite_score'] for r in pp])), 1)
        results['grade_distribution'] = {
            g: sum(1 for r in pp if r.get('grade') == g)
            for g in ['A', 'B', 'C', 'D', 'F']
        }
        for arch in ARCHETYPES:
            arch_pp = [r for r in pp if r.get('archetype') == arch]
            if arch_pp:
                results[f'{arch}_mean_score'] = round(
                    float(np.mean([r['composite_score'] for r in arch_pp])), 1)
    return results


# ─── Experiment Registry ─────────────────────────────────────────────

EXPERIMENTS = {
    1371: ('ISF deconfounded estimation', exp_1371_isf_deconfounded),
    1372: ('Loop-aware basal simulation', exp_1372_loop_aware_sim),
    1373: ('CR recommendation validation', exp_1373_cr_validation),
    1374: ('Threshold optimization', exp_1374_threshold_opt),
    1375: ('Combined ISF pipeline', exp_1375_combined_isf),
    1376: ('Basal dose-response curve', exp_1376_basal_dose_response),
    1377: ('Recommendation rolling stability', exp_1377_rolling_stability),
    1378: ('Archetype-specific recommendations', exp_1378_archetype_recs),
    1379: ('Confidence calibration', exp_1379_confidence_calibration),
    1380: ('Composite therapy health score', exp_1380_therapy_score),
}


def main():
    parser = argparse.ArgumentParser(
        description='EXP-1371-1380: ISF Deconfounding & Threshold Optimization')
    parser.add_argument('--exp', type=int, help='Run single experiment')
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--max-patients', type=int, default=11)
    args = parser.parse_args()

    print(f"Loading patients (max={args.max_patients})...")
    patients = load_patients(PATIENTS_DIR, max_patients=args.max_patients)
    print(f"Loaded {len(patients)} patients")

    # Precondition assessment
    print(f"\n{'='*60}")
    print("PRECONDITION ASSESSMENT")
    print(f"{'='*60}")
    precond_results = {}
    for p in patients:
        pc = assess_preconditions(p)
        precond_results[p['name']] = pc
        met = sum(1 for v in pc['preconditions'].values() if v['met'])
        total = len(pc['preconditions'])
        m = pc['metrics']
        print(f"  {p['name']}: {met}/{total} met | "
              f"CGM={m['cgm_coverage_pct']}% ins={m['insulin_telemetry_pct']}% "
              f"R²={m['fidelity_r2']}")

    # Run experiments
    exps_to_run = [args.exp] if args.exp else sorted(EXPERIMENTS.keys())
    all_results = {}
    outdir = Path(OUTPUT_DIR)
    outdir.mkdir(parents=True, exist_ok=True)

    for eid in exps_to_run:
        if eid not in EXPERIMENTS:
            print(f"Unknown experiment: {eid}")
            continue
        name, func = EXPERIMENTS[eid]
        print(f"\n{'='*60}")
        print(f"EXP-{eid}: {name}")
        print(f"{'='*60}")
        t0 = time.time()
        try:
            result = func(patients, detail=args.detail,
                          preconditions=precond_results)
            result['elapsed_sec'] = round(time.time() - t0, 1)
            all_results[eid] = result
            print(f"  Completed in {result['elapsed_sec']}s")
            for k, v in result.items():
                if k not in ('per_patient', 'elapsed_sec', 'name',
                             'configs', 'sweep', 'dose_response', 'windows',
                             'blocks', 'schedule'):
                    print(f"  {k}: {v}")
            if args.save:
                fname = outdir / f'exp-{eid}_therapy.json'
                with open(fname, 'w') as f:
                    json.dump(result, f, indent=2, default=str)
                print(f"  Saved → {fname}")
        except Exception as e:
            import traceback
            traceback.print_exc()
            all_results[eid] = {'error': str(e)}

    # Summary
    print(f"\n{'='*60}")
    print("ISF DECONFOUNDING & THRESHOLD OPTIMIZATION SUMMARY")
    print(f"{'='*60}")
    for eid, result in sorted(all_results.items()):
        name = EXPERIMENTS[eid][0]
        if 'error' in result:
            print(f"  EXP-{eid} {name}: FAILED - {result['error']}")
        else:
            key_metrics = {
                1371: f"best_config={result.get('best_config_distribution','?')}",
                1372: f"TIR Δ={result.get('mean_tir_change','?')}, improved={result.get('n_improved','?')}",
                1373: f"agreement={result.get('mean_agreement_rate','?')}",
                1374: f"optimal={result.get('optimal_thresholds',{}).get('well_cal_mean_actions','?')} well-cal actions",
                1375: f"well_cal_ratio: naive={result.get('well_cal_naive_ratio','?')}→deconf={result.get('well_cal_deconf_ratio','?')}",
                1376: f"fit R²={result.get('mean_fit_r2','?')}, zero_drift_ratio={result.get('mean_zero_drift_ratio','?')}",
                1377: f"stable={result.get('n_all_stable','?')}/{result.get('n_patients_with_data','?')}, mean_changes={result.get('mean_rec_changes','?')}",
                1378: f"per-archetype profiles generated",
                1379: f"basal={result.get('basal_agreement_rate','?')} cr={result.get('cr_agreement_rate','?')} isf={result.get('isf_agreement_rate','?')}",
                1380: f"mean_score={result.get('population_mean_score','?')}, grades={result.get('grade_distribution','?')}",
            }
            print(f"  EXP-{eid} {name}: {key_metrics.get(eid, 'done')}")

    return all_results


if __name__ == '__main__':
    main()
