#!/usr/bin/env python3
"""EXP-1351–1360: DIA-Corrected Physics, Multi-Parameter Therapy, Exercise Detection

Resolves key findings from EXP-1331-1340:
1. Physics model ~25% systematic bias → try DIA correction (EXP-1351)
2. Overnight-only simulation insufficient → multi-block approach (EXP-1352)
3. Dinner CR worst (77 mg/dL excursion) → simulate tightening (EXP-1353)
4. Drift bypasses physics bias → drift-only triage (EXP-1354)
5. UAM 20% threshold too aggressive → sweep thresholds (EXP-1355)
6. DIA varies by context → patient-specific profiles (EXP-1356)
7. ISF varies 131% within day → time-block recs (EXP-1357)
8. Need unified recs → multi-param confidence (EXP-1358)
9. AID loop dampens changes → simple loop model (EXP-1359)
10. Exercise vs UAM → separate for better deconfounding (EXP-1360)
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


def fit_correction_tau(glucose, bolus, carbs, n):
    """Fit exponential decay to correction events. Returns list of dicts."""
    events = []
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
            })
    return events


def compute_fasting_drift(glucose, bolus, carbs, n, block_mask, valid):
    """Compute fasting glucose drift rate in a block (mg/dL per hour)."""
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
    drift_per_5min = float(np.mean(dg[mask]))
    return drift_per_5min * STEPS_PER_HOUR, int(mask.sum())


# ─── EXP-1351: DIA-Corrected Physics Model ──────────────────────────

def exp_1351_dia_corrected(patients, detail=False, preconditions=None):
    """Recompute physics model with per-patient actual DIA instead of 5h profile.

    If DIA > 5h, demand is underestimated → net flux biased negative.
    Scale demand by (actual_DIA / profile_DIA) to correct.
    """
    PROFILE_DIA = 5.0
    results = {'name': 'EXP-1351: DIA-corrected physics',
               'n_patients': len(patients), 'per_patient': []}

    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        n = len(glucose)
        archetype = PATIENT_ARCHETYPE.get(p['name'], 'unknown')

        sd = compute_supply_demand(df, pk)
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

        # Fit patient-specific DIA
        events = fit_correction_tau(glucose, bolus, carbs, n)
        if len(events) >= 3:
            patient_tau = float(np.median([e['tau'] for e in events]))
            patient_dia = patient_tau * 3.0
        else:
            patient_tau = 2.0
            patient_dia = 6.0  # Population median from EXP-1334

        dia_ratio = patient_dia / PROFILE_DIA

        # Corrected demand: scale by DIA ratio
        corrected_demand = demand * dia_ratio
        corrected_net = sd['supply'] - corrected_demand

        # Fidelity comparison
        residual_orig = dg[valid] - net_flux[valid]
        residual_corr = dg[valid] - corrected_net[valid]
        ss_tot = float(np.sum((dg[valid] - np.mean(dg[valid])) ** 2))
        r2_orig = 1 - float(np.sum(residual_orig ** 2)) / (ss_tot + 1e-10)
        r2_corr = 1 - float(np.sum(residual_corr ** 2)) / (ss_tot + 1e-10)

        # Basal recommendation with corrected model
        fasting = np.ones(n, dtype=bool)
        for i in range(n):
            ws = max(0, i - STEPS_PER_HOUR * 2)
            we = min(n, i + STEPS_PER_HOUR * 2)
            if np.any(bolus[ws:we] > 0) or np.any(carbs[ws:we] > 0):
                fasting[i] = False
        fv = fasting & valid

        if fv.sum() > STEPS_PER_HOUR:
            orig_change = -float(np.mean(net_flux[fv])) / (float(np.mean(demand[fv])) + 1e-6)
            corr_change = -float(np.mean(corrected_net[fv])) / (float(np.mean(corrected_demand[fv])) + 1e-6)
            orig_change = max(-0.5, min(0.5, orig_change))
            corr_change = max(-0.5, min(0.5, corr_change))
        else:
            orig_change, corr_change = 0.0, 0.0

        results['per_patient'].append({
            'patient': p['name'],
            'archetype': archetype,
            'n_correction_events': len(events),
            'patient_tau': round(patient_tau, 2),
            'patient_dia': round(patient_dia, 1),
            'dia_ratio': round(dia_ratio, 2),
            'r2_original': round(r2_orig, 3),
            'r2_corrected': round(r2_corr, 3),
            'r2_improvement': round(r2_corr - r2_orig, 3),
            'basal_change_original_pct': round(orig_change * 100, 1),
            'basal_change_corrected_pct': round(corr_change * 100, 1),
            'bias_reduction_pct': round(
                (abs(orig_change) - abs(corr_change)) / (abs(orig_change) + 1e-6) * 100, 1),
        })

    pp = results['per_patient']
    well_cal = [r for r in pp if r.get('archetype') == 'well-calibrated'
                and 'r2_original' in r]
    all_valid = [r for r in pp if 'r2_original' in r]

    if well_cal:
        results['well_cal_orig_bias'] = round(
            float(np.mean([abs(r['basal_change_original_pct']) for r in well_cal])), 1)
        results['well_cal_corr_bias'] = round(
            float(np.mean([abs(r['basal_change_corrected_pct']) for r in well_cal])), 1)
        results['well_cal_r2_orig'] = round(
            float(np.mean([r['r2_original'] for r in well_cal])), 3)
        results['well_cal_r2_corr'] = round(
            float(np.mean([r['r2_corrected'] for r in well_cal])), 3)
    if all_valid:
        results['mean_r2_improvement'] = round(
            float(np.mean([r['r2_improvement'] for r in all_valid])), 3)
        results['mean_dia_ratio'] = round(
            float(np.mean([r['dia_ratio'] for r in all_valid])), 2)
    return results


# ─── EXP-1352: Multi-Block Basal Simulation ─────────────────────────

def exp_1352_multiblock_sim(patients, detail=False, preconditions=None):
    """Simulate per-time-block basal corrections (not global overnight-only)."""
    results = {'name': 'EXP-1352: Multi-block basal simulation',
               'n_patients': len(patients), 'per_patient': []}

    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        n = len(glucose)
        valid = ~np.isnan(glucose)

        gv = glucose[valid]
        if len(gv) < STEPS_PER_DAY:
            results['per_patient'].append({'patient': p['name'], 'note': 'Insufficient data'})
            continue

        current_tir = float(np.sum((gv >= 70) & (gv <= 180))) / len(gv) * 100

        # Compute per-block drift
        block_corrections = {}
        for bi, (bname, (blo, bhi)) in enumerate(zip(BLOCK_NAMES, BLOCK_RANGES)):
            block_mask = np.zeros(n, dtype=bool)
            for i in range(n):
                hour = (i % STEPS_PER_DAY) / STEPS_PER_HOUR
                if blo <= hour < bhi:
                    block_mask[i] = True
            drift, n_steps = compute_fasting_drift(glucose, bolus, carbs, n, block_mask, valid)
            if drift is not None:
                corr = -drift / STEPS_PER_HOUR
                corr = max(-0.5, min(0.5, corr))
                block_corrections[bi] = {'drift': drift, 'correction': corr, 'n': n_steps}
            else:
                block_corrections[bi] = {'drift': 0.0, 'correction': 0.0, 'n': 0}

        # Apply per-block corrections
        simulated = glucose.copy()
        cumulative = 0.0
        for i in range(n):
            if np.isnan(glucose[i]):
                continue
            bi = get_time_block_idx(i % STEPS_PER_DAY)
            corr = block_corrections.get(bi, {}).get('correction', 0.0)
            cumulative = cumulative * 0.95 + corr
            simulated[i] = glucose[i] + cumulative

        sv = simulated[valid]
        sim_tir = float(np.sum((sv >= 70) & (sv <= 180))) / len(sv) * 100
        sim_tbr = float(np.sum(sv < 70)) / len(sv) * 100

        block_detail = []
        for bi, bname in enumerate(BLOCK_NAMES):
            bc = block_corrections[bi]
            block_detail.append({
                'block': bname,
                'drift_mg_per_h': round(bc['drift'], 2),
                'correction_per_step': round(bc['correction'], 3),
                'n_fasting_steps': bc['n'],
            })

        results['per_patient'].append({
            'patient': p['name'],
            'current_tir': round(current_tir, 1),
            'simulated_tir': round(sim_tir, 1),
            'tir_change': round(sim_tir - current_tir, 1),
            'simulated_tbr': round(sim_tbr, 1),
            'blocks': block_detail if detail else [],
        })

    pp = [r for r in results['per_patient'] if 'current_tir' in r]
    if pp:
        results['n_patients_with_data'] = len(pp)
        results['mean_tir_change'] = round(
            float(np.mean([r['tir_change'] for r in pp])), 1)
        results['n_improved'] = sum(1 for r in pp if r['tir_change'] > 1)
        results['n_worsened'] = sum(1 for r in pp if r['tir_change'] < -1)
    return results


# ─── EXP-1353: CR Tightening Simulation ──────────────────────────────

def exp_1353_cr_simulation(patients, detail=False, preconditions=None):
    """Simulate tightening dinner CR by 10/20/30%."""
    results = {'name': 'EXP-1353: CR tightening simulation',
               'n_patients': len(patients), 'per_patient': []}

    CR_REDUCTIONS = [0.10, 0.20, 0.30]

    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        isf_profile = float(np.nanmean(pk[:, 7] * 200.0))
        n = len(glucose)

        # Find dinner meals (14-20h)
        dinner_meals = []
        last_meal = -3 * STEPS_PER_HOUR
        for i in range(n):
            if carbs[i] < 5 or (i - last_meal) < 2 * STEPS_PER_HOUR:
                continue
            hour = (i % STEPS_PER_DAY) / STEPS_PER_HOUR
            if not (14 <= hour < 20):
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
            excursion = bg_peak - bg_start
            meal_bolus = float(np.sum(bolus[max(0, i - 2):min(n, i + 6)]))

            dinner_meals.append({
                'step': i, 'carbs': float(carbs[i]),
                'bolus': meal_bolus, 'excursion': excursion,
                'bg_start': bg_start,
            })

        if len(dinner_meals) < 3:
            results['per_patient'].append({
                'patient': p['name'], 'n_dinners': len(dinner_meals),
                'note': 'Too few dinner meals'})
            continue

        orig_exc = [m['excursion'] for m in dinner_meals]

        # Simulate each CR reduction
        sim_results = {}
        for reduction in CR_REDUCTIONS:
            new_excursions = []
            for meal in dinner_meals:
                extra_insulin = meal['bolus'] * reduction / (1 - reduction + 1e-6)
                bg_reduction = extra_insulin * isf_profile * 0.7
                new_exc = max(0, meal['excursion'] - bg_reduction)
                new_excursions.append(new_exc)

            sim_results[f'{int(reduction*100)}pct'] = {
                'mean_excursion': round(float(np.mean(new_excursions)), 1),
                'pct_above_60': round(
                    sum(1 for e in new_excursions if e > 60) /
                    len(new_excursions) * 100, 1),
                'reduction_mg': round(
                    float(np.mean(orig_exc)) - float(np.mean(new_excursions)), 1),
            }

        results['per_patient'].append({
            'patient': p['name'],
            'n_dinners': len(dinner_meals),
            'original_mean_excursion': round(float(np.mean(orig_exc)), 1),
            'original_pct_above_60': round(
                sum(1 for e in orig_exc if e > 60) / len(orig_exc) * 100, 1),
            'simulations': sim_results,
        })

    pp = [r for r in results['per_patient'] if 'simulations' in r]
    if pp:
        results['n_patients_with_data'] = len(pp)
        for pct in ['10pct', '20pct', '30pct']:
            exc = [r['simulations'][pct]['mean_excursion'] for r in pp if pct in r['simulations']]
            flag = [r['simulations'][pct]['pct_above_60'] for r in pp if pct in r['simulations']]
            results[f'population_{pct}_excursion'] = round(float(np.mean(exc)), 1) if exc else 0
            results[f'population_{pct}_pct_above_60'] = round(float(np.mean(flag)), 1) if flag else 0
    return results


# ─── EXP-1354: Drift-Only Triage ────────────────────────────────────

def exp_1354_drift_triage(patients, detail=False, preconditions=None):
    """Complete recommendation using ONLY drift + excursion (no physics)."""
    results = {'name': 'EXP-1354: Drift-only triage',
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

        # 1. BASAL: overnight drift
        overnight_mask = np.zeros(n, dtype=bool)
        for i in range(n):
            hour = (i % STEPS_PER_DAY) / STEPS_PER_HOUR
            if 0 <= hour < 6:
                overnight_mask[i] = True
        drift, n_drift = compute_fasting_drift(glucose, bolus, carbs, n, overnight_mask, valid)
        if drift is not None and abs(drift) > 3.0:
            basal_rec = 'increase' if drift > 0 else 'decrease'
            basal_u_change = drift / (isf_profile + 1e-6)
            basal_u_change = round(max(-0.5, min(0.5, basal_u_change)) * 40) / 40
        else:
            basal_rec = 'ok'
            basal_u_change = 0.0

        # 2. CR: meal excursions by block
        cr_recs = {}
        MEAL_BLOCKS = [('breakfast', 6, 10), ('lunch', 10, 14),
                       ('dinner', 14, 20), ('late', 20, 24)]
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
                pre = glucose[max(0, i - 3):i + 1]
                pre = pre[~np.isnan(pre)]
                if len(pre) == 0:
                    continue
                post_g = glucose[i:post_end]
                if np.all(np.isnan(post_g)):
                    continue
                excursions.append(float(np.nanmax(post_g)) - float(np.mean(pre)))
            if len(excursions) >= 3:
                mean_exc = float(np.mean(excursions))
                cr_recs[bname] = 'tighten' if mean_exc > 60 else 'ok'
            else:
                cr_recs[bname] = 'insufficient_data'

        # 3. ISF: correction response
        events = fit_correction_tau(glucose, bolus, carbs, n)
        if len(events) >= 3:
            measured_isf = float(np.median([e['isf'] for e in events]))
            isf_ratio = measured_isf / (isf_profile + 1e-6)
            isf_rec = ('increase' if isf_ratio > 1.2 else
                       'decrease' if isf_ratio < 0.8 else 'ok')
        else:
            measured_isf = isf_profile
            isf_ratio = 1.0
            isf_rec = 'insufficient_data'

        triage_card = {
            'basal': basal_rec,
            'basal_change_u': basal_u_change,
            'isf': isf_rec,
            'isf_ratio': round(isf_ratio, 2),
        }
        triage_card.update({f'cr_{b}': v for b, v in cr_recs.items()})

        n_actions = sum(1 for v in triage_card.values()
                       if v in ('increase', 'decrease', 'tighten'))

        results['per_patient'].append({
            'patient': p['name'],
            'archetype': PATIENT_ARCHETYPE.get(p['name'], 'unknown'),
            'triage_card': triage_card,
            'n_actions_needed': n_actions,
            'overnight_drift': round(drift, 2) if drift else 0.0,
            'n_drift_samples': n_drift,
            'n_correction_events': len(events),
        })

    pp = results['per_patient']
    results['action_distribution'] = {
        k: sum(1 for r in pp if r.get('n_actions_needed', 0) == k)
        for k in range(7)
    }
    well_cal = [r for r in pp if r.get('archetype') == 'well-calibrated']
    if well_cal:
        results['well_cal_mean_actions'] = round(
            float(np.mean([r['n_actions_needed'] for r in well_cal])), 1)
    return results


# ─── EXP-1355: UAM Threshold Sweep ──────────────────────────────────

def exp_1355_uam_sweep(patients, detail=False, preconditions=None):
    """Find optimal UAM contamination threshold for ISF filtering."""
    THRESHOLDS = [0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90]
    results = {'name': 'EXP-1355: UAM threshold sweep',
               'n_patients': len(patients), 'per_patient': []}

    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        n = len(glucose)

        sd, uam_sup, uam_mask, _ = compute_uam_supply(df, pk)

        sweep = {}
        for thresh in THRESHOLDS:
            estimates = []
            fit_r2s = []
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
                uam_frac = float(uam_mask[i:i + window].sum()) / window
                if uam_frac > thresh:
                    continue
                traj = glucose[i:i + window]
                tv = ~np.isnan(traj)
                if tv.sum() < window * 0.5:
                    continue
                bg_start = float(traj[0])
                t_hours = np.arange(window) * (5.0 / 60.0)
                best_amp, best_tau = 0.0, 1.0
                best_sse = np.inf
                for tau_c in TAU_CANDIDATES[:7]:
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
                    estimates.append(best_amp / float(bolus[i]))
                    pred = bg_start - best_amp * (1 - np.exp(-t_hours / best_tau))
                    ss_res = float(np.sum((traj[tv] - pred[tv]) ** 2))
                    ss_tot = float(np.sum((traj[tv] - np.mean(traj[tv])) ** 2))
                    fit_r2s.append(1 - ss_res / (ss_tot + 1e-10))

            n_events = len(estimates)
            mean_r2 = float(np.mean(fit_r2s)) if fit_r2s else 0.0
            score = n_events * mean_r2
            sweep[f'{int(thresh*100)}pct'] = {
                'n_events': n_events, 'mean_fit_r2': round(mean_r2, 3),
                'score': round(score, 1),
                'median_isf': round(float(np.median(estimates)), 1) if estimates else 0.0,
            }

        best_thresh = max(sweep.keys(), key=lambda k: sweep[k]['score'])
        results['per_patient'].append({
            'patient': p['name'],
            'optimal_threshold': best_thresh,
            'optimal_score': sweep[best_thresh]['score'],
            'sweep': sweep if detail else {},
        })

    pp = results['per_patient']
    thresh_counts = defaultdict(int)
    for r in pp:
        thresh_counts[r.get('optimal_threshold', '?')] += 1
    results['population_optimal'] = max(thresh_counts, key=thresh_counts.get)
    results['threshold_distribution'] = dict(thresh_counts)
    return results


# ─── EXP-1356: Patient-Specific DIA Profiles ────────────────────────

def exp_1356_dia_profiles(patients, detail=False, preconditions=None):
    """DIA variation by bolus size and time of day."""
    results = {'name': 'EXP-1356: Patient-specific DIA profiles',
               'n_patients': len(patients), 'per_patient': []}

    for p in patients:
        df = p['df']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        n = len(glucose)

        events = fit_correction_tau(glucose, bolus, carbs, n)
        if len(events) < 5:
            results['per_patient'].append({
                'patient': p['name'], 'n_events': len(events),
                'note': 'Too few correction events'})
            continue

        # By bolus size
        small = [e for e in events if e['bolus'] < 1.0]
        medium = [e for e in events if 1.0 <= e['bolus'] < 3.0]
        large = [e for e in events if e['bolus'] >= 3.0]

        size_profile = {}
        for label, group in [('small(<1U)', small), ('medium(1-3U)', medium), ('large(>3U)', large)]:
            if len(group) >= 2:
                taus = [e['tau'] for e in group]
                size_profile[label] = {
                    'n': len(group), 'tau_median': round(float(np.median(taus)), 2),
                    'dia_median': round(float(np.median(taus)) * 3, 1),
                }

        # By time of day
        tod_profile = {}
        for bname, (blo, bhi) in zip(BLOCK_NAMES, BLOCK_RANGES):
            block_events = [e for e in events if blo <= e['hour'] < bhi]
            if len(block_events) >= 2:
                taus = [e['tau'] for e in block_events]
                tod_profile[bname] = {
                    'n': len(block_events), 'tau_median': round(float(np.median(taus)), 2),
                    'dia_median': round(float(np.median(taus)) * 3, 1),
                }

        all_taus = [e['tau'] for e in events]
        results['per_patient'].append({
            'patient': p['name'],
            'n_events': len(events),
            'overall_tau': round(float(np.median(all_taus)), 2),
            'overall_dia': round(float(np.median(all_taus)) * 3, 1),
            'tau_cv': round(float(np.std(all_taus)) / (float(np.mean(all_taus)) + 1e-6), 2),
            'by_size': size_profile,
            'by_tod': tod_profile,
        })

    pp = [r for r in results['per_patient'] if r.get('n_events', 0) >= 5]
    if pp:
        results['n_patients_with_data'] = len(pp)
        results['mean_tau_cv'] = round(float(np.mean([r['tau_cv'] for r in pp])), 2)
        size_vars = []
        tod_vars = []
        for r in pp:
            sizes = [v['tau_median'] for v in r.get('by_size', {}).values()]
            tods = [v['tau_median'] for v in r.get('by_tod', {}).values()]
            if len(sizes) >= 2:
                size_vars.append(max(sizes) - min(sizes))
            if len(tods) >= 2:
                tod_vars.append(max(tods) - min(tods))
        if size_vars and tod_vars:
            results['mean_size_variation'] = round(float(np.mean(size_vars)), 2)
            results['mean_tod_variation'] = round(float(np.mean(tod_vars)), 2)
            results['dia_varies_more_by'] = (
                'bolus_size' if float(np.mean(size_vars)) > float(np.mean(tod_vars))
                else 'time_of_day')
    return results


# ─── EXP-1357: ISF Time-Block Recommendations ───────────────────────

def exp_1357_isf_schedule(patients, detail=False, preconditions=None):
    """Generate recommended ISF schedule (6 blocks) from response curves."""
    results = {'name': 'EXP-1357: ISF time-block recommendations',
               'n_patients': len(patients), 'per_patient': []}

    for p in patients:
        df = p['df']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        isf_profile = float(np.nanmean(p['pk'][:, 7] * 200.0))
        n = len(glucose)

        events = fit_correction_tau(glucose, bolus, carbs, n)
        if len(events) < 3:
            results['per_patient'].append({
                'patient': p['name'], 'n_events': len(events),
                'note': 'Insufficient corrections'})
            continue

        overall_isf = float(np.median([e['isf'] for e in events]))

        schedule = {}
        for bname, (blo, bhi) in zip(BLOCK_NAMES, BLOCK_RANGES):
            block_events = [e for e in events if blo <= e['hour'] < bhi]
            if len(block_events) >= 2:
                isfs = [e['isf'] for e in block_events]
                med = float(np.median(isfs))
                ci = 1.28 * float(np.std(isfs)) / np.sqrt(len(isfs))
                schedule[bname] = {
                    'n': len(block_events),
                    'recommended_isf': round(med, 1),
                    'ci_80': round(ci, 1),
                    'vs_profile_pct': round((med - isf_profile) / (isf_profile + 1e-6) * 100, 1),
                }
            else:
                schedule[bname] = {
                    'n': len(block_events),
                    'recommended_isf': round(overall_isf, 1),
                    'note': 'Using overall (insufficient block data)',
                }

        results['per_patient'].append({
            'patient': p['name'],
            'n_events': len(events),
            'profile_isf': round(isf_profile, 1),
            'overall_measured_isf': round(overall_isf, 1),
            'schedule': schedule,
        })

    return results


# ─── EXP-1358: Confidence-Weighted Multi-Parameter ──────────────────

def exp_1358_multi_param(patients, detail=False, preconditions=None):
    """Unified recommendation combining basal + ISF + CR with confidence."""
    results = {'name': 'EXP-1358: Multi-parameter recommendations',
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

        # Basal (drift)
        overnight_mask = np.zeros(n, dtype=bool)
        for i in range(n):
            hour = (i % STEPS_PER_DAY) / STEPS_PER_HOUR
            if 0 <= hour < 6:
                overnight_mask[i] = True
        drift, n_drift = compute_fasting_drift(glucose, bolus, carbs, n, overnight_mask, valid)
        drift = drift if drift is not None else 0.0
        basal_conf = min(1.0, n_drift / (STEPS_PER_DAY * 3))

        # ISF (response-curve)
        events = fit_correction_tau(glucose, bolus, carbs, n)
        if events:
            measured_isf = float(np.median([e['isf'] for e in events]))
            isf_ratio = measured_isf / (isf_profile + 1e-6)
            isf_r2 = float(np.mean([e['r2'] for e in events]))
            isf_conf = min(1.0, len(events) / 20.0) * max(0.1, isf_r2)
        else:
            measured_isf, isf_ratio, isf_r2 = isf_profile, 1.0, 0.0
            isf_conf = 0.0

        # CR (excursion)
        meal_excursions = []
        last_meal = -3 * STEPS_PER_HOUR
        for i in range(n):
            if carbs[i] < 5 or (i - last_meal) < 2 * STEPS_PER_HOUR:
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
            meal_excursions.append(float(np.nanmax(post_g)) - float(np.mean(pre)))

        mean_exc = float(np.mean(meal_excursions)) if meal_excursions else 0.0
        cr_conf = min(1.0, len(meal_excursions) / 30.0) if meal_excursions else 0.0

        composite_conf = (basal_conf * 0.35 + isf_conf * 0.35 + cr_conf * 0.30)
        conf_label = 'high' if composite_conf > 0.5 else (
                     'medium' if composite_conf > 0.25 else 'low')

        actions = []
        if abs(drift) > 3.0:
            actions.append(f"basal: {'increase' if drift > 0 else 'decrease'}")
        if abs(isf_ratio - 1.0) > 0.2:
            actions.append(f"ISF: {'increase' if isf_ratio > 1 else 'decrease'} to ~{measured_isf:.0f}")
        if mean_exc > 60:
            actions.append("CR: tighten (excursion >60)")

        results['per_patient'].append({
            'patient': p['name'],
            'archetype': PATIENT_ARCHETYPE.get(p['name'], 'unknown'),
            'overnight_drift': round(drift, 2),
            'basal_confidence': round(basal_conf, 2),
            'measured_isf': round(measured_isf, 1),
            'isf_ratio': round(isf_ratio, 2),
            'isf_confidence': round(isf_conf, 2),
            'mean_excursion': round(mean_exc, 1),
            'cr_confidence': round(cr_conf, 2),
            'composite_confidence': round(composite_conf, 2),
            'confidence_label': conf_label,
            'n_actions': len(actions),
            'actions': actions,
        })

    pp = results['per_patient']
    results['confidence_distribution'] = {
        lbl: sum(1 for r in pp if r.get('confidence_label') == lbl)
        for lbl in ['high', 'medium', 'low']
    }
    well_cal = [r for r in pp if r.get('archetype') == 'well-calibrated']
    if well_cal:
        results['well_cal_mean_actions'] = round(
            float(np.mean([r['n_actions'] for r in well_cal])), 1)
    return results


# ─── EXP-1359: Simple AID Loop Model ────────────────────────────────

def exp_1359_loop_model(patients, detail=False, preconditions=None):
    """Model AID loop as proportional controller to predict dampening."""
    results = {'name': 'EXP-1359: AID loop model',
               'n_patients': len(patients), 'per_patient': []}

    TARGET_BG = 110.0

    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        temp_rate = df['temp_rate'].values
        n = len(glucose)
        valid = ~np.isnan(glucose)
        isf_profile = float(np.nanmean(pk[:, 7] * 200.0))
        scheduled_rate = get_scheduled_basal_rate(p)

        if valid.sum() < STEPS_PER_DAY or scheduled_rate < 0.01:
            results['per_patient'].append({
                'patient': p['name'], 'note': 'Insufficient data'})
            continue

        # Estimate loop gain K
        gains = []
        for i in range(n):
            if not valid[i]:
                continue
            if abs(glucose[i] - TARGET_BG) < 10:
                continue
            tr = float(temp_rate[i]) if not np.isnan(temp_rate[i]) else scheduled_rate
            k = (tr / scheduled_rate - 1) * isf_profile / (TARGET_BG - glucose[i])
            if -5 < k < 5:
                gains.append(k)

        if len(gains) < 100:
            results['per_patient'].append({
                'patient': p['name'], 'n_gain_samples': len(gains),
                'note': 'Insufficient temp rate data'})
            continue

        K = float(np.median(gains))
        K_std = float(np.std(gains))
        dampening = abs(K) / (1 + abs(K))
        effective_fraction = 1 - dampening

        tr_valid = temp_rate[valid & ~np.isnan(temp_rate)]
        loop_aggr = float(np.std(tr_valid)) / (scheduled_rate + 1e-6) if len(tr_valid) > 0 else 0.0

        results['per_patient'].append({
            'patient': p['name'],
            'archetype': PATIENT_ARCHETYPE.get(p['name'], 'unknown'),
            'estimated_K': round(K, 3),
            'K_std': round(K_std, 3),
            'dampening_pct': round(dampening * 100, 1),
            'effective_fraction': round(effective_fraction, 2),
            'loop_aggressiveness': round(loop_aggr, 2),
            'n_gain_samples': len(gains),
        })

    pp = [r for r in results['per_patient'] if 'estimated_K' in r]
    if pp:
        results['n_patients_with_data'] = len(pp)
        results['mean_K'] = round(float(np.mean([r['estimated_K'] for r in pp])), 3)
        results['mean_dampening_pct'] = round(
            float(np.mean([r['dampening_pct'] for r in pp])), 1)
        results['mean_effective_fraction'] = round(
            float(np.mean([r['effective_fraction'] for r in pp])), 2)
    return results


# ─── EXP-1360: Exercise Detection ───────────────────────────────────

def exp_1360_exercise_detection(patients, detail=False, preconditions=None):
    """Separate exercise from UAM violations for better deconfounding."""
    results = {'name': 'EXP-1360: Exercise detection',
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
        demand = sd['demand']

        dg = np.diff(glucose)
        dg = np.append(dg, 0)
        valid = ~np.isnan(glucose) & ~np.isnan(dg) & (np.abs(dg) < 50)

        violation_threshold = 2.0
        violations = valid & (np.abs(dg - net_flux) > violation_threshold)

        n_violations = int(violations.sum())
        if n_violations < 10:
            results['per_patient'].append({
                'patient': p['name'], 'n_violations': n_violations,
                'note': 'Too few violations'})
            continue

        exercise = np.zeros(n, dtype=bool)
        uam_type = np.zeros(n, dtype=bool)
        other_type = np.zeros(n, dtype=bool)
        demand_median = float(np.median(demand[valid]))

        for i in range(n):
            if not violations[i]:
                continue
            residual = dg[i] - net_flux[i]
            if residual < -violation_threshold and demand[i] < demand_median:
                exercise[i] = True
            elif residual > violation_threshold:
                nearby_carbs = np.sum(carbs[max(0, i - 6):min(n, i + 6)])
                if nearby_carbs < 2:
                    uam_type[i] = True
                else:
                    other_type[i] = True
            else:
                other_type[i] = True

        n_exercise = int(exercise.sum())
        n_uam = int(uam_type.sum())

        # ISF with/without exercise windows
        exercise_free = np.ones(n, dtype=bool)
        for i in range(n):
            if exercise[i]:
                s, e = max(0, i - STEPS_PER_HOUR), min(n, i + STEPS_PER_HOUR)
                exercise_free[s:e] = False

        events_all = fit_correction_tau(glucose, bolus, carbs, n)
        events_clean = [e for e in events_all if exercise_free[e['step']]]

        isf_all = float(np.median([e['isf'] for e in events_all])) if events_all else 0
        isf_clean = float(np.median([e['isf'] for e in events_clean])) if events_clean else 0

        exercise_hours = defaultdict(int)
        for i in range(n):
            if exercise[i]:
                exercise_hours[int((i % STEPS_PER_DAY) / STEPS_PER_HOUR)] += 1

        results['per_patient'].append({
            'patient': p['name'],
            'n_violations': n_violations,
            'n_exercise': n_exercise,
            'n_uam': n_uam,
            'exercise_pct': round(n_exercise / (n_violations + 1e-6) * 100, 1),
            'uam_pct': round(n_uam / (n_violations + 1e-6) * 100, 1),
            'peak_exercise_hour': max(exercise_hours, key=exercise_hours.get) if exercise_hours else None,
            'exercise_hours_per_day': round(n_exercise / STEPS_PER_HOUR / (n / STEPS_PER_DAY + 1e-6), 2),
            'isf_all': round(isf_all, 1),
            'isf_exercise_free': round(isf_clean, 1),
            'isf_shift_pct': round(
                (isf_clean - isf_all) / (isf_all + 1e-6) * 100, 1) if isf_all > 0 else 0,
            'n_events_all': len(events_all),
            'n_events_clean': len(events_clean),
        })

    pp = [r for r in results['per_patient'] if r.get('n_violations', 0) >= 10]
    if pp:
        results['n_patients_with_data'] = len(pp)
        results['mean_exercise_pct'] = round(
            float(np.mean([r['exercise_pct'] for r in pp])), 1)
        results['mean_uam_pct'] = round(
            float(np.mean([r['uam_pct'] for r in pp])), 1)
        results['mean_isf_shift_pct'] = round(
            float(np.mean([r['isf_shift_pct'] for r in pp])), 1)
        results['exercise_improves_isf'] = abs(results['mean_isf_shift_pct']) > 5
    return results


# ─── Experiment Registry ─────────────────────────────────────────────

EXPERIMENTS = {
    1351: ('DIA-corrected physics', exp_1351_dia_corrected),
    1352: ('Multi-block basal simulation', exp_1352_multiblock_sim),
    1353: ('CR tightening simulation', exp_1353_cr_simulation),
    1354: ('Drift-only triage', exp_1354_drift_triage),
    1355: ('UAM threshold sweep', exp_1355_uam_sweep),
    1356: ('Patient-specific DIA profiles', exp_1356_dia_profiles),
    1357: ('ISF time-block recommendations', exp_1357_isf_schedule),
    1358: ('Multi-parameter recommendations', exp_1358_multi_param),
    1359: ('AID loop model', exp_1359_loop_model),
    1360: ('Exercise detection', exp_1360_exercise_detection),
}


def main():
    parser = argparse.ArgumentParser(
        description='EXP-1351-1360: DIA-Corrected & Multi-Parameter Therapy')
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
                             'windows', 'hourly', 'blocks', 'sweep',
                             'population_summary', 'schedule',
                             'threshold_distribution', 'action_distribution'):
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
    print("DIA-CORRECTED & MULTI-PARAMETER SUMMARY")
    print(f"{'='*60}")
    for eid, result in sorted(all_results.items()):
        name = EXPERIMENTS[eid][0]
        if 'error' in result:
            print(f"  EXP-{eid} {name}: FAILED - {result['error']}")
        else:
            key_metrics = {
                1351: f"R² orig={result.get('well_cal_r2_orig','?')}→corr={result.get('well_cal_r2_corr','?')}, "
                      f"bias {result.get('well_cal_orig_bias','?')}→{result.get('well_cal_corr_bias','?')}%",
                1352: f"TIR Δ={result.get('mean_tir_change','?')}, "
                      f"improved={result.get('n_improved','?')}/{result.get('n_patients_with_data','?')}",
                1353: f"10%:{result.get('population_10pct_excursion','?')}, "
                      f"20%:{result.get('population_20pct_excursion','?')}, "
                      f"30%:{result.get('population_30pct_excursion','?')} mg/dL",
                1354: f"well_cal_actions={result.get('well_cal_mean_actions','?')}",
                1355: f"optimal={result.get('population_optimal','?')}",
                1356: f"DIA varies more by {result.get('dia_varies_more_by','?')}",
                1357: f"per-patient ISF schedules generated",
                1358: f"conf={result.get('confidence_distribution','?')}, "
                      f"well_cal_actions={result.get('well_cal_mean_actions','?')}",
                1359: f"K={result.get('mean_K','?')}, dampening={result.get('mean_dampening_pct','?')}%",
                1360: f"exercise={result.get('mean_exercise_pct','?')}%, "
                      f"ISF_shift={result.get('mean_isf_shift_pct','?')}%",
            }
            print(f"  EXP-{eid} {name}: {key_metrics.get(eid, 'done')}")

    return all_results


if __name__ == '__main__':
    main()
