#!/usr/bin/env python3
"""EXP-1341-1350: Therapy Refinement -- DIA Correction, Multi-Block, Triage

Builds on findings from EXP-1331-1340:
1. Physics model has ~25% systematic bias -- net flux overestimates demand
2. DIA mismatch: population median effective DIA = 6.0h vs 5.0h profile
3. Overnight glucose drift is the best single signal for basal assessment
4. Dinner CR is worst -- 77.3 mg/dL mean excursion, 53.6% flagged
5. ISF varies 131% within day -- single ISF values are insufficient
6. UAM filtering at 20% loses 84.6% of events -- too aggressive
7. Overnight-only simulation gives TIR delta=-1.4% -- need multi-block approach

Resolves:
- Can DIA correction reduce the 25% physics bias? (EXP-1341)
- Does multi-block simulation beat overnight-only? (EXP-1342)
- What CR tightening actually improves dinner excursions? (EXP-1343)
- Can we do therapy triage WITHOUT physics at all? (EXP-1344)
- What is the optimal UAM threshold? (EXP-1345)
- Does DIA vary by bolus size or time of day? (EXP-1346)
- Actionable ISF schedules from response curves (EXP-1347)
- Unified confidence-weighted recommendations (EXP-1348)
- AID loop dampening model (EXP-1349)
- Exercise vs UAM violation classification (EXP-1350)
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

GLUCOSE_SCALE = 400.0
STEPS_PER_HOUR = 12
STEPS_PER_DAY = 288
DIA_STEPS = STEPS_PER_HOUR * 5  # 5-hour DIA

BLOCK_NAMES = ['overnight(0-6)', 'morning(6-10)', 'midday(10-14)',
               'afternoon(14-18)', 'evening(18-22)', 'night(22-24)']
BLOCK_RANGES = [(0, 6), (6, 10), (10, 14), (14, 18), (18, 22), (22, 24)]

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


def get_overnight_mask(df, n):
    """Return boolean mask for overnight hours (0-6 AM)."""
    mask = np.zeros(n, dtype=bool)
    for i in range(n):
        hour = (i % STEPS_PER_DAY) / STEPS_PER_HOUR
        if 0 <= hour < 6:
            mask[i] = True
    return mask


def _fit_correction_tau(glucose, bolus, carbs, n, tau_range=None):
    """Fit exponential decay to correction events.

    Returns list of dicts with tau_h, amplitude, fit_r2, bolus_u, hour.
    """
    if tau_range is None:
        tau_range = np.arange(0.5, 6.1, 0.25)
    events = []
    for i in range(n):
        if bolus[i] < 0.5 or np.isnan(glucose[i]) or glucose[i] <= 150:
            continue
        cw = slice(max(0, i - 6), min(n, i + 6))
        if np.sum(carbs[cw]) > 2:
            continue
        max_window = 8 * STEPS_PER_HOUR
        if i + max_window >= n:
            continue
        if np.sum(bolus[i + 1:i + max_window]) > 0.5:
            continue
        if np.sum(carbs[i + 1:i + max_window]) > 2:
            continue
        traj = glucose[i:i + max_window]
        tv = ~np.isnan(traj)
        if tv.sum() < max_window * 0.4:
            continue
        bg_start = float(traj[0])
        t_hours = np.arange(max_window) * (5.0 / 60.0)
        best_sse, best_amp, best_tau = np.inf, 0.0, 2.0
        for tau_c in tau_range:
            basis = 1.0 - np.exp(-t_hours / tau_c)
            bv = basis[tv]
            denom = float(np.sum(bv ** 2))
            if denom < 1e-6:
                continue
            amp = float(np.sum(bv * (bg_start - traj[tv])) / denom)
            if amp < 10:
                continue
            sse = float(np.sum((traj[tv] - (bg_start - amp * basis[tv])) ** 2))
            if sse < best_sse:
                best_sse, best_amp, best_tau = sse, amp, tau_c
        if best_amp >= 10:
            pred = bg_start - best_amp * (1 - np.exp(-t_hours / best_tau))
            ss_res = float(np.sum((traj[tv] - pred[tv]) ** 2))
            ss_tot = float(np.sum((traj[tv] - np.mean(traj[tv])) ** 2))
            fit_r2 = 1 - ss_res / (ss_tot + 1e-10)
            hour = (i % STEPS_PER_DAY) / STEPS_PER_HOUR
            events.append({
                'step': int(i), 'bolus_u': float(bolus[i]),
                'bg_start': bg_start, 'amplitude': round(best_amp, 1),
                'tau_h': round(best_tau, 2),
                'effective_dia_h': round(best_tau * 3.0, 1),
                'fit_r2': round(fit_r2, 3),
                'isf_observed': round(best_amp / float(bolus[i]), 1),
                'hour': round(hour, 1),
            })
    return events


def _compute_fasting_mask(bolus, carbs, n, lookback_h=2):
    """Return boolean mask for fasting periods."""
    fasting = np.ones(n, dtype=bool)
    for i in range(n):
        ws = max(0, i - STEPS_PER_HOUR * lookback_h)
        we = min(n, i + STEPS_PER_HOUR * lookback_h)
        if np.any(bolus[ws:we] > 0) or np.any(carbs[ws:we] > 0):
            fasting[i] = False
    return fasting


def _compute_block_mask(n, blo, bhi):
    """Return boolean mask for a time-of-day block."""
    mask = np.zeros(n, dtype=bool)
    for i in range(n):
        hour = (i % STEPS_PER_DAY) / STEPS_PER_HOUR
        if blo <= hour < bhi:
            mask[i] = True
    return mask


# --- EXP-1341: DIA-Corrected Physics Model ---------------------------

def exp_1341_dia_corrected(patients, detail=False, preconditions=None):
    """Use per-patient actual DIA instead of 5h profile DIA to reduce physics bias.

    EXP-1334 found population median effective DIA = 6.0h vs 5.0h profile.
    If well-calibrated patients (d,h,j,k) show recommended change closer to 0%
    after DIA correction, the correction works.
    """
    PROFILE_DIA_H = 5.0
    results = {'name': 'EXP-1341: DIA-corrected physics model',
               'n_patients': len(patients), 'per_patient': []}
    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        n = len(glucose)
        archetype = PATIENT_ARCHETYPE.get(p['name'], 'unknown')
        events = _fit_correction_tau(glucose, bolus, carbs, n)
        if events:
            patient_tau = float(np.median([e['tau_h'] for e in events]))
            actual_dia = patient_tau * 3.0
            mean_fit_r2 = float(np.mean([e['fit_r2'] for e in events]))
        else:
            patient_tau = PROFILE_DIA_H / 3.0
            actual_dia = PROFILE_DIA_H
            mean_fit_r2 = 0.0
        dia_ratio = PROFILE_DIA_H / max(actual_dia, 1.0)
        sd, uam_sup, uam_mask, aug_supply = compute_uam_supply(df, pk)
        net_flux = sd['net']
        demand = sd['demand']
        dg = np.diff(glucose)
        dg = np.append(dg, 0)
        valid = ~np.isnan(glucose) & ~np.isnan(dg) & (np.abs(dg) < 50)
        if valid.sum() < STEPS_PER_DAY:
            results['per_patient'].append({
                'patient': p['name'], 'archetype': archetype,
                'note': 'Insufficient data'})
            continue
        fasting = _compute_fasting_mask(bolus, carbs, n)
        raw_fasting = fasting & valid
        if raw_fasting.sum() < STEPS_PER_HOUR:
            results['per_patient'].append({
                'patient': p['name'], 'archetype': archetype,
                'note': 'Insufficient fasting data'})
            continue
        raw_mean_net = float(np.mean(net_flux[raw_fasting]))
        raw_mean_demand = float(np.mean(demand[raw_fasting]))
        original_change = -raw_mean_net / (raw_mean_demand + 1e-6)
        original_change = max(-0.5, min(0.5, original_change))
        corrected_demand = demand * dia_ratio
        corrected_net = sd['supply'] - corrected_demand
        corrected_mean_net = float(np.mean(corrected_net[raw_fasting]))
        corrected_mean_demand = float(np.mean(corrected_demand[raw_fasting]))
        corrected_change = -corrected_mean_net / (corrected_mean_demand + 1e-6)
        corrected_change = max(-0.5, min(0.5, corrected_change))
        dg_fasting = dg[raw_fasting]
        net_fasting_orig = net_flux[raw_fasting]
        net_fasting_corr = corrected_net[raw_fasting]
        def _r2(predicted, actual):
            ss_res = float(np.sum((actual - predicted) ** 2))
            ss_tot = float(np.sum((actual - np.mean(actual)) ** 2))
            return 1 - ss_res / (ss_tot + 1e-10)
        r2_original = _r2(net_fasting_orig, dg_fasting)
        r2_corrected = _r2(net_fasting_corr, dg_fasting)
        results['per_patient'].append({
            'patient': p['name'], 'archetype': archetype,
            'n_correction_events': len(events),
            'patient_tau_h': round(patient_tau, 2),
            'actual_dia_h': round(actual_dia, 1),
            'dia_ratio': round(dia_ratio, 3),
            'mean_fit_r2': round(mean_fit_r2, 3),
            'original_change_pct': round(original_change * 100, 1),
            'corrected_change_pct': round(corrected_change * 100, 1),
            'bias_reduction_pct': round(
                (abs(original_change) - abs(corrected_change)) /
                (abs(original_change) + 1e-6) * 100, 1),
            'r2_original': round(r2_original, 3),
            'r2_corrected': round(r2_corrected, 3),
            'r2_improved': r2_corrected > r2_original,
        })
    pp = results['per_patient']
    well_cal = [r for r in pp if r.get('archetype') == 'well-calibrated'
                and 'original_change_pct' in r]
    if well_cal:
        results['well_cal_original_mean_abs'] = round(
            float(np.mean([abs(r['original_change_pct']) for r in well_cal])), 1)
        results['well_cal_corrected_mean_abs'] = round(
            float(np.mean([abs(r['corrected_change_pct']) for r in well_cal])), 1)
        results['well_cal_bias_reduction'] = round(
            float(np.mean([r['bias_reduction_pct'] for r in well_cal])), 1)
    all_valid = [r for r in pp if 'original_change_pct' in r]
    if all_valid:
        results['population_original_bias_abs'] = round(
            float(np.mean([abs(r['original_change_pct']) for r in all_valid])), 1)
        results['population_corrected_bias_abs'] = round(
            float(np.mean([abs(r['corrected_change_pct']) for r in all_valid])), 1)
        results['population_mean_dia'] = round(
            float(np.mean([r['actual_dia_h'] for r in all_valid])), 1)
        results['n_r2_improved'] = sum(1 for r in all_valid if r.get('r2_improved'))
        results['n_patients_analyzed'] = len(all_valid)
    return results


# --- EXP-1342: Multi-Block Basal Simulation ---------------------------

def exp_1342_multiblock_sim(patients, detail=False, preconditions=None):
    """Simulate per-block basal corrections instead of overnight-only.

    EXP-1340 showed overnight-only TIR change = -1.4% (0/11 improved).
    Apply per-block drift corrections with exponential decay and capping.
    """
    results = {'name': 'EXP-1342: Multi-block basal simulation',
               'n_patients': len(patients), 'per_patient': []}
    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        n = len(glucose)
        dg = np.diff(glucose)
        dg = np.append(dg, 0)
        valid = ~np.isnan(glucose) & ~np.isnan(dg) & (np.abs(dg) < 50)
        fasting = _compute_fasting_mask(bolus, carbs, n)
        gv = glucose[~np.isnan(glucose)]
        if len(gv) < STEPS_PER_DAY:
            results['per_patient'].append({
                'patient': p['name'], 'note': 'Insufficient data'})
            continue
        current_tir = float(np.sum((gv >= 70) & (gv <= 180))) / len(gv) * 100
        current_mean_bg = float(np.mean(gv))
        current_tbr = float(np.sum(gv < 70)) / len(gv) * 100
        block_drifts = {}
        block_corrections = {}
        for bi, (bname, (blo, bhi)) in enumerate(zip(BLOCK_NAMES, BLOCK_RANGES)):
            block_mask = _compute_block_mask(n, blo, bhi)
            bfv = block_mask & fasting & valid
            if bfv.sum() < STEPS_PER_HOUR:
                block_drifts[bname] = 0.0
                block_corrections[bname] = 0.0
                continue
            drift_per_5min = float(np.mean(dg[bfv]))
            drift_per_hour = drift_per_5min * STEPS_PER_HOUR
            block_drifts[bname] = round(drift_per_hour, 3)
            correction_per_step = -drift_per_5min
            correction_per_step = max(-0.5, min(0.5, correction_per_step))
            block_corrections[bname] = round(correction_per_step, 4)
        simulated_glucose = glucose.copy()
        cumulative_correction = 0.0
        for i in range(n):
            if np.isnan(glucose[i]):
                continue
            bi = get_time_block(i % STEPS_PER_DAY)
            bname = BLOCK_NAMES[bi]
            step_correction = block_corrections.get(bname, 0.0)
            cumulative_correction = cumulative_correction * 0.95 + step_correction
            simulated_glucose[i] = glucose[i] + cumulative_correction
        sv = simulated_glucose[~np.isnan(simulated_glucose)]
        sim_tir = float(np.sum((sv >= 70) & (sv <= 180))) / len(sv) * 100
        sim_mean_bg = float(np.mean(sv))
        sim_tbr = float(np.sum(sv < 70)) / len(sv) * 100
        results['per_patient'].append({
            'patient': p['name'],
            'current_tir': round(current_tir, 1),
            'simulated_tir': round(sim_tir, 1),
            'tir_change': round(sim_tir - current_tir, 1),
            'current_mean_bg': round(current_mean_bg, 1),
            'simulated_mean_bg': round(sim_mean_bg, 1),
            'current_tbr': round(current_tbr, 1),
            'simulated_tbr': round(sim_tbr, 1),
            'block_drifts': block_drifts,
            'block_corrections': block_corrections,
        })
    pp = [r for r in results['per_patient'] if 'current_tir' in r]
    if pp:
        results['n_patients_with_data'] = len(pp)
        results['mean_tir_change'] = round(float(np.mean([r['tir_change'] for r in pp])), 1)
        results['mean_current_tir'] = round(float(np.mean([r['current_tir'] for r in pp])), 1)
        results['mean_simulated_tir'] = round(float(np.mean([r['simulated_tir'] for r in pp])), 1)
        results['n_improved'] = sum(1 for r in pp if r['tir_change'] > 1)
        results['n_worsened'] = sum(1 for r in pp if r['tir_change'] < -1)
        results['mean_tbr_change'] = round(
            float(np.mean([r['simulated_tbr'] - r['current_tbr'] for r in pp])), 1)
        block_avg = {}
        for bname in BLOCK_NAMES:
            dvals = [r['block_drifts'].get(bname, 0.0) for r in pp]
            block_avg[bname] = round(float(np.mean(dvals)), 3)
        results['population_block_drifts'] = block_avg
    return results


# --- EXP-1343: CR Tightening Simulation ------------------------------

def exp_1343_cr_tightening(patients, detail=False, preconditions=None):
    """Simulate reducing dinner CR by 10%, 20%, 30% to reduce excursions.

    EXP-1336 found dinner CR is worst: 77.3 mg/dL mean excursion, 53.6% flagged.
    """
    TAU_H = 2.0
    CR_REDUCTIONS = [0.10, 0.20, 0.30]
    results = {'name': 'EXP-1343: CR tightening simulation',
               'n_patients': len(patients), 'per_patient': []}
    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        isf_profile = float(np.nanmean(pk[:, 7] * 200.0))
        cr_profile = float(np.nanmean(pk[:, 3] * 0.5))
        if cr_profile < 1.0:
            cr_profile = 10.0
        n = len(glucose)
        dinner_meals = []
        last_meal_step = -3 * STEPS_PER_HOUR
        for i in range(n):
            if carbs[i] < 10 or (i - last_meal_step) < 2 * STEPS_PER_HOUR:
                continue
            hour = (i % STEPS_PER_DAY) / STEPS_PER_HOUR
            if not (14 <= hour < 20):
                continue
            last_meal_step = i
            post_end = min(n, i + 3 * STEPS_PER_HOUR)
            if post_end - i < STEPS_PER_HOUR:
                continue
            post_g = glucose[i:post_end]
            pre_valid = glucose[max(0, i - 3):i + 1]
            pre_valid = pre_valid[~np.isnan(pre_valid)]
            if len(pre_valid) == 0:
                continue
            bg_start = float(np.mean(pre_valid))
            bg_peak = float(np.nanmax(post_g)) if np.any(~np.isnan(post_g)) else bg_start
            excursion = bg_peak - bg_start
            if np.isnan(excursion):
                continue
            dinner_meals.append({'step': int(i), 'carbs_g': float(carbs[i]),
                                 'bg_start': round(bg_start, 1), 'excursion': round(excursion, 1)})
        if not dinner_meals:
            results['per_patient'].append({'patient': p['name'], 'n_dinners': 0,
                                           'note': 'No qualifying dinner meals'})
            continue
        reduction_results = {}
        for cr_red in CR_REDUCTIONS:
            new_cr = cr_profile * (1 - cr_red)
            sim_excursions = []
            for meal in dinner_meals:
                extra_insulin = meal['carbs_g'] * (1.0 / new_cr - 1.0 / cr_profile)
                peak_reduction = extra_insulin * isf_profile * (1 - np.exp(-1.0 / TAU_H))
                sim_excursion = max(0, meal['excursion'] - peak_reduction)
                sim_excursions.append(sim_excursion)
            reduction_results[f'{int(cr_red * 100)}pct'] = {
                'new_cr': round(new_cr, 1),
                'mean_excursion': round(float(np.mean(sim_excursions)), 1),
                'median_excursion': round(float(np.median(sim_excursions)), 1),
                'pct_above_60': round(sum(1 for e in sim_excursions if e > 60) / len(sim_excursions) * 100, 1),
                'excursion_reduction': round(float(np.mean([m['excursion'] for m in dinner_meals])) -
                                             float(np.mean(sim_excursions)), 1),
            }
        original_mean = float(np.mean([m['excursion'] for m in dinner_meals]))
        original_pct_high = sum(1 for m in dinner_meals if m['excursion'] > 60) / len(dinner_meals) * 100
        results['per_patient'].append({
            'patient': p['name'], 'n_dinners': len(dinner_meals),
            'cr_profile': round(cr_profile, 1), 'isf_profile': round(isf_profile, 1),
            'original_mean_excursion': round(original_mean, 1),
            'original_pct_above_60': round(original_pct_high, 1),
            'reductions': reduction_results,
        })
    pp = [r for r in results['per_patient'] if r.get('n_dinners', 0) > 0]
    if pp:
        results['n_patients_with_data'] = len(pp)
        results['population_original_excursion'] = round(
            float(np.mean([r['original_mean_excursion'] for r in pp])), 1)
        for pct in ['10pct', '20pct', '30pct']:
            vals = [r['reductions'][pct]['mean_excursion'] for r in pp if pct in r.get('reductions', {})]
            if vals:
                results[f'population_{pct}_excursion'] = round(float(np.mean(vals)), 1)
                results[f'population_{pct}_above_60'] = round(
                    float(np.mean([r['reductions'][pct]['pct_above_60'] for r in pp if pct in r.get('reductions', {})])), 1)
    return results


# --- EXP-1344: Drift-Only Triage -------------------------------------

def exp_1344_drift_triage(patients, detail=False, preconditions=None):
    """Build complete recommendation system using ONLY drift and excursion.

    No physics model -- just:
    - Basal: overnight drift direction and magnitude
    - CR: meal excursion by block, flag blocks with mean >60 mg/dL
    - ISF: correction bolus drop/dose ratio
    Compare triage cards vs physics-based recommendations.
    """
    MEAL_BLOCKS = [('breakfast', 6, 10), ('lunch', 10, 14), ('dinner', 14, 20)]
    results = {'name': 'EXP-1344: Drift-only triage',
               'n_patients': len(patients), 'per_patient': []}
    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        n = len(glucose)
        dg = np.diff(glucose)
        dg = np.append(dg, 0)
        valid = ~np.isnan(glucose) & ~np.isnan(dg) & (np.abs(dg) < 50)
        fasting = _compute_fasting_mask(bolus, carbs, n)
        overnight = get_overnight_mask(df, n)
        ovn_fasting = overnight & fasting & valid
        if ovn_fasting.sum() > STEPS_PER_HOUR:
            drift_per_hour = float(np.mean(dg[ovn_fasting])) * STEPS_PER_HOUR
            if np.isnan(drift_per_hour):
                drift_per_hour = 0.0
        else:
            drift_per_hour = 0.0
        basal_rec = 'increase' if drift_per_hour > 3.0 else ('decrease' if drift_per_hour < -3.0 else 'ok')
        cr_recs = {}
        for bname, blo, bhi in MEAL_BLOCKS:
            meal_excursions = []
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
                post_g = glucose[i:post_end]
                pre_g = glucose[max(0, i - 3):i + 1]
                pre_valid = pre_g[~np.isnan(pre_g)]
                if len(pre_valid) == 0:
                    continue
                bg_start = float(np.mean(pre_valid))
                bg_peak = float(np.nanmax(post_g)) if np.any(~np.isnan(post_g)) else bg_start
                exc = bg_peak - bg_start
                if not np.isnan(exc):
                    meal_excursions.append(exc)
            if meal_excursions:
                mean_exc = float(np.mean(meal_excursions))
                cr_recs[bname] = {'n_meals': len(meal_excursions), 'mean_excursion': round(mean_exc, 1),
                                  'recommendation': 'adjust' if mean_exc > 60 else 'ok'}
            else:
                cr_recs[bname] = {'n_meals': 0, 'recommendation': 'insufficient_data'}
        isf_estimates = []
        for i in range(n):
            if bolus[i] < 0.3 or np.isnan(glucose[i]) or glucose[i] <= 150:
                continue
            cw = slice(max(0, i - 6), min(n, i + 6))
            if np.sum(carbs[cw]) > 2:
                continue
            post_end = min(n, i + 3 * STEPS_PER_HOUR)
            if post_end - i < STEPS_PER_HOUR:
                continue
            if np.sum(bolus[i + 1:post_end]) > 0.5:
                continue
            post_g = glucose[i:post_end]
            pv = ~np.isnan(post_g)
            if pv.sum() < STEPS_PER_HOUR // 2:
                continue
            drop = float(post_g[0] - np.nanmin(post_g))
            if drop > 10:
                isf_estimates.append(drop / float(bolus[i]))
        isf_profile = float(np.nanmean(pk[:, 7] * 200.0))
        if isf_estimates:
            observed_isf = float(np.median(isf_estimates))
            isf_ratio = observed_isf / (isf_profile + 1e-6)
            isf_rec = 'adjust' if abs(isf_ratio - 1.0) > 0.2 else 'ok'
        else:
            observed_isf, isf_ratio, isf_rec = isf_profile, 1.0, 'insufficient_data'
        sd = compute_supply_demand(df, pk)
        net_flux = sd['net']
        demand = sd['demand']
        raw_fasting = fasting & valid
        if raw_fasting.sum() > STEPS_PER_HOUR:
            physics_net = float(np.mean(net_flux[raw_fasting]))
            physics_demand = float(np.mean(demand[raw_fasting]))
            physics_change = -physics_net / (physics_demand + 1e-6)
            physics_change = max(-0.5, min(0.5, physics_change))
            physics_rec = 'increase' if physics_change > 0.05 else ('decrease' if physics_change < -0.05 else 'ok')
        else:
            physics_change, physics_rec = 0.0, 'insufficient_data'
        triage_card = {
            'basal': basal_rec,
            'CR_breakfast': cr_recs.get('breakfast', {}).get('recommendation', 'insufficient_data'),
            'CR_lunch': cr_recs.get('lunch', {}).get('recommendation', 'insufficient_data'),
            'CR_dinner': cr_recs.get('dinner', {}).get('recommendation', 'insufficient_data'),
            'ISF': isf_rec,
        }
        results['per_patient'].append({
            'patient': p['name'], 'archetype': PATIENT_ARCHETYPE.get(p['name'], 'unknown'),
            'drift_mg_per_hour': round(drift_per_hour, 2), 'triage_card': triage_card,
            'cr_details': cr_recs, 'observed_isf': round(observed_isf, 1),
            'isf_profile': round(isf_profile, 1), 'isf_ratio': round(isf_ratio, 2),
            'n_isf_events': len(isf_estimates), 'physics_basal_rec': physics_rec,
            'physics_change_pct': round(physics_change * 100, 1),
            'drift_vs_physics_agree': basal_rec == physics_rec,
        })
    pp = results['per_patient']
    valid_pp = [r for r in pp if 'triage_card' in r]
    if valid_pp:
        results['n_patients_analyzed'] = len(valid_pp)
        results['drift_physics_agreement_pct'] = round(
            sum(1 for r in valid_pp if r.get('drift_vs_physics_agree')) / len(valid_pp) * 100, 1)
        for param in ['basal', 'CR_breakfast', 'CR_dinner', 'ISF']:
            dist = defaultdict(int)
            for r in valid_pp:
                dist[r['triage_card'].get(param, 'unknown')] += 1
            results[f'{param}_distribution'] = dict(dist)
    return results


# --- EXP-1345: Gentle UAM Threshold Sweep ----------------------------

def exp_1345_uam_sweep(patients, detail=False, preconditions=None):
    """Find optimal UAM contamination threshold for ISF response-curve filtering.

    EXP-1332 used 20% threshold, losing 84.6% of events.
    Sweep 20%-80% to find threshold maximizing (events_retained * fit_R2).
    """
    THRESHOLDS = [0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80]
    TAU_CANDIDATES = [0.3, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0]
    results = {'name': 'EXP-1345: UAM threshold sweep',
               'n_patients': len(patients), 'per_patient': []}
    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        n = len(glucose)
        sd, uam_sup, uam_mask, _ = compute_uam_supply(df, pk)
        raw_events = []
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
            uam_frac = float(uam_mask[i:i + window].sum()) / window
            bg_start = float(traj[0])
            t_hours = np.arange(window) * (5.0 / 60.0)
            best_sse, best_amp, best_tau = np.inf, 0.0, 1.0
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
                isf_est = best_amp / float(bolus[i])
                pred = bg_start - best_amp * (1 - np.exp(-t_hours / best_tau))
                ss_res = float(np.sum((traj[tv] - pred[tv]) ** 2))
                ss_tot = float(np.sum((traj[tv] - np.mean(traj[tv])) ** 2))
                fit_r2 = 1 - ss_res / (ss_tot + 1e-10)
                raw_events.append({'isf': isf_est, 'tau': best_tau, 'fit_r2': fit_r2, 'uam_frac': uam_frac})
        if not raw_events:
            results['per_patient'].append({'patient': p['name'], 'n_total_events': 0, 'note': 'No correction events'})
            continue
        sweep_results = {}
        best_score, best_threshold = -1, 0.20
        for thresh in THRESHOLDS:
            filtered = [e for e in raw_events if e['uam_frac'] <= thresh]
            n_retained = len(filtered)
            frac_retained = n_retained / len(raw_events)
            if n_retained >= 2:
                median_isf = float(np.median([e['isf'] for e in filtered]))
                mean_r2 = float(np.mean([e['fit_r2'] for e in filtered]))
            else:
                median_isf, mean_r2 = 0.0, 0.0
            score = frac_retained * mean_r2
            sweep_results[f'{int(thresh * 100)}pct'] = {
                'n_retained': n_retained, 'pct_retained': round(frac_retained * 100, 1),
                'median_isf': round(median_isf, 1), 'mean_fit_r2': round(mean_r2, 3),
                'score': round(score, 3),
            }
            if score > best_score:
                best_score, best_threshold = score, thresh
        results['per_patient'].append({
            'patient': p['name'], 'n_total_events': len(raw_events),
            'optimal_threshold': round(best_threshold, 2),
            'optimal_score': round(best_score, 3), 'sweep': sweep_results,
        })
    pp = [r for r in results['per_patient'] if r.get('n_total_events', 0) > 0]
    if pp:
        results['n_patients_with_data'] = len(pp)
        thresholds = [r['optimal_threshold'] for r in pp]
        results['population_optimal_threshold'] = round(float(np.median(thresholds)), 2)
        results['threshold_distribution'] = {
            f'{int(t * 100)}pct': sum(1 for x in thresholds if x == t)
            for t in THRESHOLDS if any(x == t for x in thresholds)
        }
        orig_scores = [r['sweep'].get('20pct', {}).get('score', 0) for r in pp]
        results['mean_score_at_20pct'] = round(float(np.mean(orig_scores)), 3)
        results['mean_score_at_optimal'] = round(float(np.mean([r['optimal_score'] for r in pp])), 3)
    return results


# --- EXP-1346: Patient-Specific DIA Profiles --------------------------

def exp_1346_dia_profiles(patients, detail=False, preconditions=None):
    """Build continuous DIA curve per patient by bolus size and time of day.

    Test if DIA varies with bolus magnitude or circadian rhythm.
    """
    results = {'name': 'EXP-1346: Patient-specific DIA profiles',
               'n_patients': len(patients), 'per_patient': []}
    BOLUS_GROUPS = [('small', 0, 1.0), ('medium', 1.0, 3.0), ('large', 3.0, 100.0)]
    TOD_GROUPS = [('morning', 6, 12), ('afternoon', 12, 18), ('evening', 18, 24)]
    for p in patients:
        df = p['df']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        n = len(glucose)
        events = _fit_correction_tau(glucose, bolus, carbs, n)
        if not events:
            results['per_patient'].append({'patient': p['name'], 'n_events': 0, 'note': 'No correction events'})
            continue
        bolus_groups = {}
        for gname, lo, hi in BOLUS_GROUPS:
            group = [e for e in events if lo <= e['bolus_u'] < hi]
            if group:
                taus = [e['tau_h'] for e in group]
                bolus_groups[gname] = {
                    'n': len(group), 'median_tau': round(float(np.median(taus)), 2),
                    'median_dia': round(float(np.median(taus)) * 3.0, 1),
                    'iqr_tau': round(float(np.percentile(taus, 75) - np.percentile(taus, 25)), 2) if len(taus) >= 4 else None,
                }
        tod_groups = {}
        for gname, lo, hi in TOD_GROUPS:
            group = [e for e in events if lo <= e['hour'] < hi]
            if group:
                taus = [e['tau_h'] for e in group]
                tod_groups[gname] = {
                    'n': len(group), 'median_tau': round(float(np.median(taus)), 2),
                    'median_dia': round(float(np.median(taus)) * 3.0, 1),
                    'iqr_tau': round(float(np.percentile(taus, 75) - np.percentile(taus, 25)), 2) if len(taus) >= 4 else None,
                }
        all_taus = [e['tau_h'] for e in events]
        total_var = float(np.var(all_taus)) if len(all_taus) >= 2 else 0.0
        bg_taus_bolus = [bolus_groups[g]['median_tau'] for g, _, _ in BOLUS_GROUPS if g in bolus_groups]
        bolus_between_var = float(np.var(bg_taus_bolus)) if len(bg_taus_bolus) >= 2 else 0.0
        bg_taus_tod = [tod_groups[g]['median_tau'] for g, _, _ in TOD_GROUPS if g in tod_groups]
        tod_between_var = float(np.var(bg_taus_tod)) if len(bg_taus_tod) >= 2 else 0.0
        results['per_patient'].append({
            'patient': p['name'], 'n_events': len(events),
            'overall_tau': round(float(np.median(all_taus)), 2),
            'overall_dia': round(float(np.median(all_taus)) * 3.0, 1),
            'bolus_groups': bolus_groups, 'tod_groups': tod_groups,
            'total_tau_variance': round(total_var, 4),
            'bolus_size_variance_explained': round(bolus_between_var / (total_var + 1e-10), 3),
            'tod_variance_explained': round(tod_between_var / (total_var + 1e-10), 3),
            'primary_factor': 'bolus_size' if bolus_between_var > tod_between_var else 'time_of_day',
        })
    pp = [r for r in results['per_patient'] if r.get('n_events', 0) > 0]
    if pp:
        results['n_patients_with_data'] = len(pp)
        results['mean_bolus_var_explained'] = round(float(np.mean([r['bolus_size_variance_explained'] for r in pp])), 3)
        results['mean_tod_var_explained'] = round(float(np.mean([r['tod_variance_explained'] for r in pp])), 3)
        results['primary_factor_distribution'] = {
            f: sum(1 for r in pp if r.get('primary_factor') == f) for f in ['bolus_size', 'time_of_day']
        }
        results['population_dia_median'] = round(float(np.median([r['overall_dia'] for r in pp])), 1)
    return results


# --- EXP-1347: ISF Time-Block Recommendations ------------------------

def exp_1347_isf_schedule(patients, detail=False, preconditions=None):
    """Generate actionable time-of-day ISF profiles from response curves.

    For each block with >= 3 correction events, compute median ISF and CI.
    Compare to profile ISF and generate recommendation.
    """
    TAU_CANDIDATES = [0.5, 0.75, 1.0, 1.5, 2.0, 3.0]
    results = {'name': 'EXP-1347: ISF time-block recommendations',
               'n_patients': len(patients), 'per_patient': []}
    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        isf_profile = float(np.nanmean(pk[:, 7] * 200.0))
        n = len(glucose)
        block_isfs = defaultdict(list)
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
            best_amp, best_tau, best_sse = 0.0, 1.0, np.inf
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
                isf_est = best_amp / float(bolus[i])
                bi = get_time_block(i % STEPS_PER_DAY)
                block_isfs[BLOCK_NAMES[bi]].append(isf_est)
        if not block_isfs:
            results['per_patient'].append({'patient': p['name'], 'n_events': 0, 'note': 'No correction events'})
            continue
        block_recs = {}
        for bname in BLOCK_NAMES:
            vals = block_isfs.get(bname, [])
            if len(vals) < 3:
                block_recs[bname] = {'n_events': len(vals), 'recommendation': 'insufficient_data'}
                continue
            median_isf = float(np.median(vals))
            p25 = float(np.percentile(vals, 25))
            p75 = float(np.percentile(vals, 75))
            ratio = median_isf / (isf_profile + 1e-6)
            if ratio > 1.2:
                rec, direction = 'increase', round(median_isf - isf_profile, 1)
            elif ratio < 0.8:
                rec, direction = 'decrease', round(median_isf - isf_profile, 1)
            else:
                rec, direction = 'maintain', 0.0
            recommended_isf = round(median_isf / 5) * 5
            block_recs[bname] = {
                'n_events': len(vals), 'median_isf': round(median_isf, 1),
                'ci_25_75': [round(p25, 1), round(p75, 1)],
                'profile_isf': round(isf_profile, 1), 'ratio_to_profile': round(ratio, 2),
                'recommendation': rec, 'recommended_isf': recommended_isf,
                'change_mg_dl_u': round(direction, 1),
            }
        total_events = sum(len(v) for v in block_isfs.values())
        blocks_with_recs = sum(1 for b in block_recs.values() if b.get('recommendation') not in ('insufficient_data',))
        results['per_patient'].append({
            'patient': p['name'], 'n_events': total_events, 'profile_isf': round(isf_profile, 1),
            'blocks_with_recommendations': blocks_with_recs, 'block_recs': block_recs,
        })
    pp = [r for r in results['per_patient'] if r.get('n_events', 0) > 0]
    if pp:
        results['n_patients_with_data'] = len(pp)
        results['mean_blocks_with_recs'] = round(float(np.mean([r['blocks_with_recommendations'] for r in pp])), 1)
        adj_counts = defaultdict(int)
        for r in pp:
            for bname, brec in r.get('block_recs', {}).items():
                adj_counts[brec.get('recommendation', 'insufficient_data')] += 1
        results['recommendation_distribution'] = dict(adj_counts)
    return results


# --- EXP-1348: Confidence-Weighted Multi-Parameter Recommendations ----

def exp_1348_unified_recs(patients, detail=False, preconditions=None):
    """Unified recommendation combining basal + ISF + CR with confidence.

    Confidence sources:
    - Basal: # overnight windows and drift consistency
    - ISF: # corrections and fit R2
    - CR: # meals per block and excursion consistency
    """
    results = {'name': 'EXP-1348: Confidence-weighted unified recommendations',
               'n_patients': len(patients), 'per_patient': []}
    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        n = len(glucose)
        archetype = PATIENT_ARCHETYPE.get(p['name'], 'unknown')
        dg = np.diff(glucose)
        dg = np.append(dg, 0)
        valid = ~np.isnan(glucose) & ~np.isnan(dg) & (np.abs(dg) < 50)
        fasting = _compute_fasting_mask(bolus, carbs, n)
        overnight = get_overnight_mask(df, n)
        isf_profile = float(np.nanmean(pk[:, 7] * 200.0))
        scheduled_rate = get_scheduled_basal_rate(p)
        # Basal assessment
        ovn_fasting = overnight & fasting & valid
        n_ovn_windows = 0
        drifts = []
        if ovn_fasting.sum() > STEPS_PER_HOUR:
            in_window = False
            for i in range(n):
                if ovn_fasting[i]:
                    if not in_window:
                        n_ovn_windows += 1
                        in_window = True
                    drifts.append(float(dg[i]))
                else:
                    in_window = False
        if drifts:
            mean_drift = float(np.mean(drifts)) * STEPS_PER_HOUR
            drift_std = float(np.std(drifts)) * STEPS_PER_HOUR
            if np.isnan(mean_drift): mean_drift = 0.0
            if np.isnan(drift_std): drift_std = 999.0
            drift_cv = abs(drift_std / (abs(mean_drift) + 1e-6))
            basal_change = mean_drift / (isf_profile + 1e-6)
            basal_change = round(basal_change * 40) / 40
            basal_confidence = 'high' if n_ovn_windows >= 5 and drift_cv < 2.0 else ('medium' if n_ovn_windows >= 3 else 'low')
        else:
            mean_drift, basal_change = 0.0, 0.0
            basal_confidence = 'none'
        # ISF assessment
        events = _fit_correction_tau(glucose, bolus, carbs, n, tau_range=[0.5, 0.75, 1.0, 1.5, 2.0, 3.0])
        if events:
            isf_vals = [e['isf_observed'] for e in events]
            r2_vals = [e['fit_r2'] for e in events]
            observed_isf = float(np.median(isf_vals))
            mean_r2 = float(np.mean(r2_vals))
            isf_change = observed_isf - isf_profile
            isf_change = max(-0.5 * isf_profile, min(0.5 * isf_profile, isf_change))
            isf_confidence = 'high' if len(events) >= 5 and mean_r2 > 0.5 else ('medium' if len(events) >= 3 else 'low')
        else:
            observed_isf, mean_r2, isf_change = isf_profile, 0.0, 0.0
            isf_confidence = 'none'
        # CR assessment
        MEAL_BLOCKS = [('breakfast', 6, 10), ('dinner', 14, 20)]
        cr_recs = {}
        for bname, blo, bhi in MEAL_BLOCKS:
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
                post_g = glucose[i:post_end]
                pre_g = glucose[max(0, i - 3):i + 1]
                pre_valid = pre_g[~np.isnan(pre_g)]
                if len(pre_valid) == 0:
                    continue
                bg_start = float(np.mean(pre_valid))
                bg_peak = float(np.nanmax(post_g)) if np.any(~np.isnan(post_g)) else bg_start
                exc = bg_peak - bg_start
                if not np.isnan(exc):
                    excursions.append(exc)
            if excursions:
                mean_exc = float(np.mean(excursions))
                exc_std = float(np.std(excursions))
                exc_cv = exc_std / (abs(mean_exc) + 1e-6)
                cr_confidence = 'high' if len(excursions) >= 5 and exc_cv < 1.5 else ('medium' if len(excursions) >= 3 else 'low')
                cr_assessment = 'tighten' if mean_exc > 60 else ('loosen' if mean_exc < 20 else 'ok')
                cr_recs[bname] = {'n_meals': len(excursions), 'mean_excursion': round(mean_exc, 1),
                                  'assessment': cr_assessment, 'confidence': cr_confidence}
            else:
                cr_recs[bname] = {'n_meals': 0, 'assessment': 'insufficient_data', 'confidence': 'none'}
        conf_scores = {'high': 3, 'medium': 2, 'low': 1, 'none': 0}
        all_confs = [conf_scores.get(basal_confidence, 0), conf_scores.get(isf_confidence, 0)]
        for brec in cr_recs.values():
            all_confs.append(conf_scores.get(brec.get('confidence', 'none'), 0))
        composite_confidence = round(float(np.mean(all_confs)), 1)
        results['per_patient'].append({
            'patient': p['name'], 'archetype': archetype,
            'basal': {'drift_mg_per_h': round(mean_drift, 2), 'change_u_per_h': round(basal_change, 3),
                      'confidence': basal_confidence},
            'isf': {'profile': round(isf_profile, 1), 'observed': round(observed_isf, 1),
                    'change': round(isf_change, 1), 'n_events': len(events),
                    'mean_r2': round(mean_r2, 3), 'confidence': isf_confidence},
            'cr': cr_recs, 'composite_confidence': composite_confidence,
        })
    pp = results['per_patient']
    valid_pp = [r for r in pp if 'composite_confidence' in r]
    if valid_pp:
        results['n_patients_analyzed'] = len(valid_pp)
        results['mean_composite_confidence'] = round(float(np.mean([r['composite_confidence'] for r in valid_pp])), 1)
        for param, key in [('basal', 'basal'), ('isf', 'isf')]:
            dist = defaultdict(int)
            for r in valid_pp:
                dist[r[key].get('confidence', 'none')] += 1
            results[f'{param}_confidence_dist'] = dict(dist)
    return results


# --- EXP-1349: Simple AID Loop Model ---------------------------------

def exp_1349_aid_loop_model(patients, detail=False, preconditions=None):
    """Model AID loop as proportional controller to predict recommendation interaction.

    Model: temp_basal = scheduled_basal * (1 + K * (target - BG) / ISF)
    K from EXP-1310: well-calibrated K ~ 0.31, miscalibrated K ~ 2.2.
    If scheduled_basal changes, loop DAMPENS the change.
    """
    TARGET_BG = 110.0
    results = {'name': 'EXP-1349: AID loop dampening model',
               'n_patients': len(patients), 'per_patient': []}
    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        temp_rate_col = df['temp_rate'].values if 'temp_rate' in df.columns else np.zeros(len(glucose))
        n = len(glucose)
        archetype = PATIENT_ARCHETYPE.get(p['name'], 'unknown')
        isf_profile = float(np.nanmean(pk[:, 7] * 200.0))
        scheduled_rate = get_scheduled_basal_rate(p)
        valid = ~np.isnan(glucose)
        if valid.sum() < STEPS_PER_DAY:
            results['per_patient'].append({'patient': p['name'], 'archetype': archetype, 'note': 'Insufficient data'})
            continue
        k_estimates = []
        for i in range(n):
            if np.isnan(glucose[i]) or glucose[i] < 50 or glucose[i] > 350:
                continue
            if temp_rate_col[i] <= 0:
                continue
            bg_error = TARGET_BG - glucose[i]
            if abs(bg_error) < 10:
                continue
            ratio = temp_rate_col[i] / (scheduled_rate + 1e-6)
            k_est = (ratio - 1) * isf_profile / (bg_error + 1e-6)
            if 0.01 <= abs(k_est) <= 10:
                k_estimates.append(abs(k_est))
        K = float(np.median(k_estimates)) if k_estimates else (0.31 if archetype == 'well-calibrated' else 1.0)
        test_changes = [0.05, 0.10, 0.20, 0.30]
        dampening_results = {}
        for pct_change in test_changes:
            new_rate = scheduled_rate * (1 + pct_change)
            effective_changes = []
            for i in range(n):
                if not valid[i]:
                    continue
                bg = glucose[i]
                loop_mult = 1 + K * (TARGET_BG - bg) / (isf_profile + 1e-6)
                eff_new = new_rate * max(0, loop_mult)
                eff_orig = scheduled_rate * max(0, loop_mult)
                if eff_orig > 0:
                    eff_change = (eff_new - eff_orig) / eff_orig
                    eff_change = max(-0.5, min(0.5, eff_change))
                    effective_changes.append(eff_change)
            if effective_changes:
                mean_eff = float(np.mean(effective_changes))
                dampening = 1 - mean_eff / pct_change if pct_change > 0 else 0
            else:
                mean_eff, dampening = pct_change, 0.0
            dampening_results[f'{int(pct_change * 100)}pct'] = {
                'intended_change': round(pct_change * 100, 1),
                'effective_change': round(mean_eff * 100, 1),
                'dampening_pct': round(dampening * 100, 1),
            }
        results['per_patient'].append({
            'patient': p['name'], 'archetype': archetype,
            'estimated_K': round(K, 3), 'isf_profile': round(isf_profile, 1),
            'scheduled_rate': round(scheduled_rate, 3), 'n_k_samples': len(k_estimates),
            'dampening': dampening_results,
        })
    pp = [r for r in results['per_patient'] if 'estimated_K' in r]
    if pp:
        results['n_patients_analyzed'] = len(pp)
        results['mean_K'] = round(float(np.mean([r['estimated_K'] for r in pp])), 3)
        well_cal = [r for r in pp if r.get('archetype') == 'well-calibrated']
        needs_tun = [r for r in pp if r.get('archetype') == 'needs-tuning']
        if well_cal:
            results['well_cal_mean_K'] = round(float(np.mean([r['estimated_K'] for r in well_cal])), 3)
        if needs_tun:
            results['needs_tuning_mean_K'] = round(float(np.mean([r['estimated_K'] for r in needs_tun])), 3)
        damp_10 = [r['dampening']['10pct']['dampening_pct'] for r in pp if '10pct' in r.get('dampening', {})]
        if damp_10:
            results['mean_dampening_at_10pct'] = round(float(np.mean(damp_10)), 1)
    return results


# --- EXP-1350: Exercise Detection ------------------------------------

def exp_1350_exercise_detection(patients, detail=False, preconditions=None):
    """Separate exercise-type violations from UAM-type in conservation analysis.

    From EXP-1305: 47% of timesteps violate conservation.
    Exercise: BG drops rapidly while insulin is LOW (supply up, demand low).
    UAM: BG rises while insulin adequate (supply up, no logged carbs).
    Test if excluding exercise windows improves ISF estimation.
    """
    TAU_CANDIDATES = [0.5, 0.75, 1.0, 1.5, 2.0, 3.0]
    results = {'name': 'EXP-1350: Exercise detection',
               'n_patients': len(patients), 'per_patient': []}
    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        n = len(glucose)
        sd, uam_sup, uam_mask, _ = compute_uam_supply(df, pk)
        net_flux = sd['net']
        supply = sd['supply']
        demand = sd['demand']
        dg = np.diff(glucose)
        dg = np.append(dg, 0)
        valid = ~np.isnan(glucose) & ~np.isnan(dg)
        violation_mask = np.abs(dg - net_flux) > 2.0
        n_violations = int((violation_mask & valid).sum())
        n_valid = int(valid.sum())
        exercise_mask = np.zeros(n, dtype=bool)
        uam_violation_mask = np.zeros(n, dtype=bool)
        median_demand = float(np.median(demand[valid]))
        for i in range(1, n):
            if not valid[i] or not violation_mask[i]:
                continue
            if dg[i] < -1.0 and demand[i] < median_demand:
                exercise_mask[i] = True
            elif dg[i] > 1.0 and carbs[max(0, i - 6):i + 1].sum() < 2:
                uam_violation_mask[i] = True
        n_exercise = int((exercise_mask & valid).sum())
        n_uam_violations = int((uam_violation_mask & valid).sum())
        n_days = n / STEPS_PER_DAY
        exercise_per_day = n_exercise / max(n_days, 1)
        exercise_by_block = {}
        for bi, (bname, (blo, bhi)) in enumerate(zip(BLOCK_NAMES, BLOCK_RANGES)):
            block_mask = _compute_block_mask(n, blo, bhi)
            ex_in_block = int((exercise_mask & block_mask & valid).sum())
            block_total = int((block_mask & valid).sum())
            exercise_by_block[bname] = {
                'n_exercise_steps': ex_in_block,
                'pct_of_block': round(ex_in_block / (block_total + 1e-6) * 100, 1),
            }
        def _estimate_isf(exclude_mask):
            estimates = []
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
                if exclude_mask is not None:
                    exc_frac = float(exclude_mask[i:i + window].sum()) / window
                    if exc_frac > 0.1:
                        continue
                traj = glucose[i:i + window]
                tv = ~np.isnan(traj)
                if tv.sum() < window * 0.5:
                    continue
                bg_start = float(traj[0])
                t_hours = np.arange(window) * (5.0 / 60.0)
                best_amp, best_tau, best_sse = 0.0, 1.0, np.inf
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
                    isf_est = best_amp / float(bolus[i])
                    pred = bg_start - best_amp * (1 - np.exp(-t_hours / best_tau))
                    ss_res = float(np.sum((traj[tv] - pred[tv]) ** 2))
                    ss_tot = float(np.sum((traj[tv] - np.mean(traj[tv])) ** 2))
                    r2 = 1 - ss_res / (ss_tot + 1e-10)
                    estimates.append({'isf': isf_est, 'r2': r2})
            return estimates
        all_isf = _estimate_isf(None)
        ex_clean_isf = _estimate_isf(exercise_mask)
        pr = {
            'patient': p['name'],
            'n_violations': n_violations,
            'violation_pct': round(n_violations / (n_valid + 1e-6) * 100, 1),
            'n_exercise': n_exercise, 'n_uam_violations': n_uam_violations,
            'exercise_pct': round(n_exercise / (n_violations + 1e-6) * 100, 1),
            'uam_pct': round(n_uam_violations / (n_violations + 1e-6) * 100, 1),
            'exercise_per_day': round(exercise_per_day, 1),
            'exercise_by_block': exercise_by_block,
        }
        if all_isf:
            pr['all_isf_median'] = round(float(np.median([e['isf'] for e in all_isf])), 1)
            pr['all_isf_r2'] = round(float(np.mean([e['r2'] for e in all_isf])), 3)
            pr['all_n_events'] = len(all_isf)
        else:
            pr['all_n_events'] = 0
        if ex_clean_isf:
            pr['ex_clean_isf_median'] = round(float(np.median([e['isf'] for e in ex_clean_isf])), 1)
            pr['ex_clean_isf_r2'] = round(float(np.mean([e['r2'] for e in ex_clean_isf])), 3)
            pr['ex_clean_n_events'] = len(ex_clean_isf)
            if all_isf:
                pr['r2_improvement'] = round(pr['ex_clean_isf_r2'] - pr['all_isf_r2'], 3)
                pr['events_lost_pct'] = round((1 - len(ex_clean_isf) / (len(all_isf) + 1e-6)) * 100, 1)
        else:
            pr['ex_clean_n_events'] = 0
        results['per_patient'].append(pr)
    pp = [r for r in results['per_patient'] if r.get('n_violations', 0) > 0]
    if pp:
        results['n_patients_with_data'] = len(pp)
        results['mean_violation_pct'] = round(float(np.mean([r['violation_pct'] for r in pp])), 1)
        results['mean_exercise_pct'] = round(float(np.mean([r['exercise_pct'] for r in pp])), 1)
        results['mean_uam_pct'] = round(float(np.mean([r['uam_pct'] for r in pp])), 1)
        results['mean_exercise_per_day'] = round(float(np.mean([r['exercise_per_day'] for r in pp])), 1)
        with_both = [r for r in pp if r.get('all_n_events', 0) > 0 and r.get('ex_clean_n_events', 0) > 0]
        if with_both:
            results['mean_r2_improvement'] = round(float(np.mean([r['r2_improvement'] for r in with_both])), 3)
            results['mean_events_lost_pct'] = round(float(np.mean([r['events_lost_pct'] for r in with_both])), 1)
            results['exercise_exclusion_improves_isf'] = results['mean_r2_improvement'] > 0
    return results


# --- Experiment Registry ----------------------------------------------

EXPERIMENTS = {
    1341: ('DIA-corrected physics', exp_1341_dia_corrected),
    1342: ('Multi-block basal simulation', exp_1342_multiblock_sim),
    1343: ('CR tightening simulation', exp_1343_cr_tightening),
    1344: ('Drift-only triage', exp_1344_drift_triage),
    1345: ('UAM threshold sweep', exp_1345_uam_sweep),
    1346: ('Patient-specific DIA profiles', exp_1346_dia_profiles),
    1347: ('ISF time-block recommendations', exp_1347_isf_schedule),
    1348: ('Confidence-weighted unified recs', exp_1348_unified_recs),
    1349: ('AID loop dampening model', exp_1349_aid_loop_model),
    1350: ('Exercise detection', exp_1350_exercise_detection),
}


def main():
    parser = argparse.ArgumentParser(
        description='EXP-1341-1350: Therapy Refinement')
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
              f"R2={m['fidelity_r2']}")

    # Run experiments
    exps_to_run = [args.exp] if args.exp else sorted(EXPERIMENTS.keys())
    all_results = {}
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
                             'windows', 'hourly', 'blocks',
                             'population_summary', 'block_recs',
                             'population_block_drifts', 'sweep',
                             'dampening', 'exercise_by_block'):
                    print(f"  {k}: {v}")
            if args.save:
                fname = f'exp-{eid}_therapy.json'
                with open(fname, 'w') as f:
                    json.dump(result, f, indent=2, default=str)
                print(f"  Saved -> {fname}")
        except Exception as e:
            import traceback
            traceback.print_exc()
            all_results[eid] = {'error': str(e)}

    # Summary
    print(f"\n{'='*60}")
    print("THERAPY REFINEMENT SUMMARY")
    print(f"{'='*60}")
    for eid, result in sorted(all_results.items()):
        name = EXPERIMENTS[eid][0]
        if 'error' in result:
            print(f"  EXP-{eid} {name}: FAILED - {result['error']}")
        else:
            key_metrics = {
                1341: (f"bias: {result.get('population_original_bias_abs','?')}->"
                       f"{result.get('population_corrected_bias_abs','?')}%, "
                       f"R2 improved={result.get('n_r2_improved','?')}/"
                       f"{result.get('n_patients_analyzed','?')}"),
                1342: (f"TIR: {result.get('mean_current_tir','?')}->"
                       f"{result.get('mean_simulated_tir','?')} "
                       f"(d={result.get('mean_tir_change','?')}), "
                       f"improved={result.get('n_improved','?')}/"
                       f"{result.get('n_patients_with_data','?')}"),
                1343: (f"dinner excursion: "
                       f"{result.get('population_original_excursion','?')}->"
                       f"10%:{result.get('population_10pct_excursion','?')} "
                       f"20%:{result.get('population_20pct_excursion','?')} "
                       f"30%:{result.get('population_30pct_excursion','?')}"),
                1344: (f"drift/physics agree="
                       f"{result.get('drift_physics_agreement_pct','?')}%, "
                       f"basal dist="
                       f"{result.get('basal_distribution','?')}"),
                1345: (f"optimal threshold="
                       f"{result.get('population_optimal_threshold','?')}, "
                       f"score: 20%="
                       f"{result.get('mean_score_at_20pct','?')}->"
                       f"opt={result.get('mean_score_at_optimal','?')}"),
                1346: (f"DIA={result.get('population_dia_median','?')}h, "
                       f"bolus_var="
                       f"{result.get('mean_bolus_var_explained','?')}, "
                       f"tod_var="
                       f"{result.get('mean_tod_var_explained','?')}"),
                1347: (f"mean blocks with recs="
                       f"{result.get('mean_blocks_with_recs','?')}, "
                       f"dist="
                       f"{result.get('recommendation_distribution','?')}"),
                1348: (f"mean confidence="
                       f"{result.get('mean_composite_confidence','?')}, "
                       f"basal conf="
                       f"{result.get('basal_confidence_dist','?')}"),
                1349: (f"mean K={result.get('mean_K','?')}, "
                       f"dampening@10%="
                       f"{result.get('mean_dampening_at_10pct','?')}%"),
                1350: (f"exercise={result.get('mean_exercise_pct','?')}%, "
                       f"UAM={result.get('mean_uam_pct','?')}%, "
                       f"R2 improve="
                       f"{result.get('mean_r2_improvement','?')}"),
            }
            print(f"  EXP-{eid} {name}: {key_metrics.get(eid, 'done')}")

    return all_results


if __name__ == '__main__':
    main()
