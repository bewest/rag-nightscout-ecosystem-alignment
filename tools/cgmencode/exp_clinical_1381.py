#!/usr/bin/env python3
"""EXP-1381–1390: Temporal Smoothing, Complex Cases, Prospective Validation

Addresses remaining gaps from 90-experiment campaign:
1. Recommendations unstable (2/11 stable) → temporal smoothing (EXP-1381)
2. Complex cases (a,b) evade triage → multi-factor deep dive (EXP-1382)
3. Need prospective validation → train-on-first, test-on-second (EXP-1383)
4. Bayesian ISF with prior shrinkage (EXP-1384)
5. Score weight optimization for archetype separation (EXP-1385)
6. Recommendation priority ordering → impact-based ranking (EXP-1386)
7. Seasonal/temporal patterns in therapy drift (EXP-1387)
8. Cross-patient recommendation transfer (EXP-1388)
9. Minimum data requirements for reliable recommendations (EXP-1389)
10. End-to-end triage pipeline accuracy assessment (EXP-1390)
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


def fit_correction_events(glucose, bolus, carbs, n, min_bolus=0.3,
                          min_bg=150, exercise_mask=None):
    """Fit exponential decay to correction events."""
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
        if exercise_mask is not None and np.any(exercise_mask[i:i + window]):
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
                'bolus': float(bolus[i]), 'drop': best_amp,
            })
    return events


def compute_fasting_drift(glucose, bolus, carbs, n, block_mask, valid):
    """Compute fasting glucose drift (mg/dL per hour)."""
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
            'step': i, 'carbs': float(carbs[i]),
            'bolus': float(np.sum(bolus[max(0, i - 2):min(n, i + 6)])),
        })
    return excursions


def detect_exercise(df, pk, n):
    """Detect exercise: negative residual + low demand."""
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
    expanded = exercise.copy()
    for i in range(n):
        if exercise[i]:
            s = max(0, i - STEPS_PER_HOUR)
            e = min(n, i + STEPS_PER_HOUR)
            expanded[s:e] = True
    return expanded, uam_mask, sd


def compute_window_metrics(glucose, bolus, carbs, n, isf_profile):
    """Compute all therapy metrics for a data window."""
    valid = ~np.isnan(glucose)
    gv = glucose[valid]
    if len(gv) < STEPS_PER_DAY:
        return None

    tir = float(np.sum((gv >= 70) & (gv <= 180))) / len(gv) * 100
    tbr = float(np.sum(gv < 70)) / len(gv) * 100
    tar = float(np.sum(gv > 180)) / len(gv) * 100
    mean_bg = float(np.nanmean(gv))
    cv = float(np.std(gv)) / (mean_bg + 1e-6)

    # Overnight drift
    on_mask = np.zeros(n, dtype=bool)
    for i in range(n):
        hour = (i % STEPS_PER_DAY) / STEPS_PER_HOUR
        if 0 <= hour < 6:
            on_mask[i] = True
    drift, n_drift = compute_fasting_drift(glucose, bolus, carbs, n, on_mask, valid)
    drift = drift if drift is not None else 0.0

    # Meal excursions
    exc_all = get_meal_excursions(glucose, bolus, carbs, n)
    exc_dinner = get_meal_excursions(glucose, bolus, carbs, n, 14, 20)
    mean_exc = float(np.mean([e['excursion'] for e in exc_all])) if exc_all else 0.0
    mean_dinner = float(np.mean([e['excursion'] for e in exc_dinner])) if exc_dinner else 0.0

    # ISF (deconfounded)
    events = fit_correction_events(glucose, bolus, carbs, n, min_bolus=2.0)
    isf_ratio = (float(np.median([e['isf'] for e in events])) / (isf_profile + 1e-6)
                 if len(events) >= 3 else 1.0)

    return {
        'tir': tir, 'tbr': tbr, 'tar': tar, 'mean_bg': mean_bg, 'cv': cv,
        'drift': drift, 'n_drift': n_drift,
        'mean_excursion': mean_exc, 'dinner_excursion': mean_dinner,
        'n_meals': len(exc_all), 'n_dinners': len(exc_dinner),
        'isf_ratio': isf_ratio, 'n_corrections': len(events),
    }


def compute_therapy_score(metrics):
    """Compute 0-100 therapy health score from metrics dict."""
    tir_s = min(40, metrics['tir'] * 40 / 85)
    basal_s = max(0, 20 - abs(metrics['drift']) * 2)
    cr_s = max(0, 20 - (metrics['mean_excursion'] - 30) * 0.25)
    isf_s = max(0, 10 - abs(metrics['isf_ratio'] - 1.0) * 5)
    cv_s = max(0, 10 - metrics['cv'] * 30)
    return max(0, min(100, tir_s + basal_s + cr_s + isf_s + cv_s))


def generate_recommendations(metrics, thresholds=None):
    """Generate therapy recommendations from metrics."""
    if thresholds is None:
        thresholds = {'drift': 5.0, 'excursion': 70.0, 'isf_ratio': 2.0}
    recs = []
    if abs(metrics['drift']) > thresholds['drift']:
        recs.append({
            'param': 'basal',
            'action': 'increase' if metrics['drift'] > 0 else 'decrease',
            'magnitude': abs(metrics['drift']),
            'confidence': min(1.0, metrics['n_drift'] / (STEPS_PER_DAY * 3)),
        })
    if metrics['dinner_excursion'] > thresholds['excursion']:
        recs.append({
            'param': 'dinner_cr',
            'action': 'tighten',
            'magnitude': metrics['dinner_excursion'],
            'confidence': min(1.0, metrics['n_dinners'] / 15.0),
        })
    if abs(metrics['isf_ratio'] - 1.0) > (thresholds['isf_ratio'] - 1.0):
        recs.append({
            'param': 'isf',
            'action': 'increase' if metrics['isf_ratio'] > 1 else 'decrease',
            'magnitude': abs(metrics['isf_ratio'] - 1.0),
            'confidence': min(1.0, metrics['n_corrections'] / 10.0),
        })
    return recs


# ─── EXP-1381: Temporal Smoothing ───────────────────────────────────

def exp_1381_temporal_smoothing(patients, detail=False, preconditions=None):
    """Require N consecutive windows to agree before recommending."""
    results = {'name': 'EXP-1381: Temporal smoothing',
               'n_patients': len(patients), 'per_patient': []}

    WINDOW_DAYS = 30
    WINDOW_STEPS = WINDOW_DAYS * STEPS_PER_DAY
    STRIDE_STEPS = 15 * STEPS_PER_DAY  # 50% overlap
    AGREEMENT_LEVELS = [1, 2, 3]  # Require 1, 2, or 3 consecutive windows

    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        n = len(glucose)
        isf_profile = float(np.nanmean(pk[:, 7] * 200.0))

        # Compute per-window recommendations
        window_recs = []
        for start in range(0, n - WINDOW_STEPS, STRIDE_STEPS):
            end = start + WINDOW_STEPS
            m = compute_window_metrics(glucose[start:end], bolus[start:end],
                                        carbs[start:end], end - start, isf_profile)
            if m is not None:
                recs = generate_recommendations(m)
                window_recs.append({
                    'start_day': start // STEPS_PER_DAY,
                    'basal_flag': any(r['param'] == 'basal' for r in recs),
                    'cr_flag': any(r['param'] == 'dinner_cr' for r in recs),
                    'isf_flag': any(r['param'] == 'isf' for r in recs),
                    'n_recs': len(recs),
                })

        if len(window_recs) < 3:
            results['per_patient'].append({
                'patient': p['name'], 'n_windows': len(window_recs),
                'note': 'Too few windows'})
            continue

        # Check agreement at each level
        level_results = {}
        for k in AGREEMENT_LEVELS:
            stable_basal, stable_cr = 0, 0
            total_checks = 0
            for i in range(k - 1, len(window_recs)):
                total_checks += 1
                # Check if last k windows agree on basal
                basal_flags = [window_recs[j]['basal_flag'] for j in range(i - k + 1, i + 1)]
                cr_flags = [window_recs[j]['cr_flag'] for j in range(i - k + 1, i + 1)]
                if all(basal_flags) or all(not f for f in basal_flags):
                    stable_basal += 1
                if all(cr_flags) or all(not f for f in cr_flags):
                    stable_cr += 1

            level_results[f'require_{k}'] = {
                'basal_stability': round(stable_basal / max(1, total_checks), 2),
                'cr_stability': round(stable_cr / max(1, total_checks), 2),
                'total_checks': total_checks,
            }

        results['per_patient'].append({
            'patient': p['name'],
            'n_windows': len(window_recs),
            'levels': level_results,
            'windows': window_recs if detail else [],
        })

    pp = [r for r in results['per_patient'] if r.get('n_windows', 0) >= 3]
    if pp:
        for k in AGREEMENT_LEVELS:
            key = f'require_{k}'
            basal_stabs = [r['levels'][key]['basal_stability'] for r in pp if key in r.get('levels', {})]
            cr_stabs = [r['levels'][key]['cr_stability'] for r in pp if key in r.get('levels', {})]
            results[f'mean_basal_stability_k{k}'] = round(float(np.mean(basal_stabs)), 2) if basal_stabs else 0
            results[f'mean_cr_stability_k{k}'] = round(float(np.mean(cr_stabs)), 2) if cr_stabs else 0
    return results


# ─── EXP-1382: Complex Case Analysis ────────────────────────────────

def exp_1382_complex_cases(patients, detail=False, preconditions=None):
    """Deep analysis of patients that evade standard triage (a, b)."""
    results = {'name': 'EXP-1382: Complex case analysis',
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
        isf_profile = float(np.nanmean(pk[:, 7] * 200.0))
        scheduled_rate = get_scheduled_basal_rate(p)
        archetype = PATIENT_ARCHETYPE.get(p['name'], 'unknown')

        gv = glucose[valid]
        if len(gv) < STEPS_PER_DAY:
            results['per_patient'].append({'patient': p['name'], 'note': 'Insufficient data'})
            continue

        tir = float(np.sum((gv >= 70) & (gv <= 180))) / len(gv) * 100

        # Per-block TIR breakdown
        block_tir = {}
        for bname, (blo, bhi) in zip(BLOCK_NAMES, BLOCK_RANGES):
            block_mask = np.zeros(n, dtype=bool)
            for i in range(n):
                hour = (i % STEPS_PER_DAY) / STEPS_PER_HOUR
                if blo <= hour < bhi:
                    block_mask[i] = True
            bv = glucose[valid & block_mask]
            if len(bv) > 0:
                block_tir[bname] = round(float(np.sum((bv >= 70) & (bv <= 180))) / len(bv) * 100, 1)

        # Time above vs below
        tar = float(np.sum(gv > 180)) / len(gv) * 100
        tbr = float(np.sum(gv < 70)) / len(gv) * 100

        # Loop behavior analysis
        tr_valid = temp_rate[~np.isnan(temp_rate)]
        if len(tr_valid) > 0:
            loop_aggr = float(np.std(tr_valid)) / (scheduled_rate + 1e-6)
            pct_suspended = float(np.sum(tr_valid < 0.01)) / len(tr_valid) * 100
            pct_max = float(np.sum(tr_valid > scheduled_rate * 2)) / len(tr_valid) * 100
        else:
            loop_aggr, pct_suspended, pct_max = 0, 0, 0

        # Meal pattern analysis
        meals_per_day = 0
        last_meal = -3 * STEPS_PER_HOUR
        meal_count = 0
        for i in range(n):
            if carbs[i] >= 5 and (i - last_meal) >= 2 * STEPS_PER_HOUR:
                meal_count += 1
                last_meal = i
        meals_per_day = meal_count / (n / STEPS_PER_DAY)

        # Correction frequency
        corrections_per_day = float(np.sum(bolus > 0.3)) / (n / STEPS_PER_DAY)

        # Mean glucose by quintile of days
        day_means = []
        for d_start in range(0, n - STEPS_PER_DAY, STEPS_PER_DAY):
            d_g = glucose[d_start:d_start + STEPS_PER_DAY]
            dv = d_g[~np.isnan(d_g)]
            if len(dv) > STEPS_PER_HOUR:
                day_means.append(float(np.mean(dv)))

        if len(day_means) >= 5:
            q_size = len(day_means) // 5
            quintiles = [round(float(np.mean(day_means[i * q_size:(i + 1) * q_size])), 1)
                         for i in range(5)]
            trend = round(quintiles[-1] - quintiles[0], 1)
        else:
            quintiles = []
            trend = 0.0

        # Identify the dominant problem
        problems = []
        if tar > 30:
            problems.append(f'high_tar({tar:.0f}%)')
        if tbr > 5:
            problems.append(f'high_tbr({tbr:.0f}%)')
        if loop_aggr > 1.0:
            problems.append(f'loop_aggressive({loop_aggr:.1f})')
        if pct_suspended > 20:
            problems.append(f'frequently_suspended({pct_suspended:.0f}%)')
        if meals_per_day < 1.5:
            problems.append(f'few_meals({meals_per_day:.1f}/d)')
        if corrections_per_day > 5:
            problems.append(f'frequent_corrections({corrections_per_day:.1f}/d)')
        if abs(trend) > 15:
            problems.append(f'glucose_trend({trend:+.0f}mg/dL)')

        results['per_patient'].append({
            'patient': p['name'],
            'archetype': archetype,
            'tir': round(tir, 1),
            'tar': round(tar, 1),
            'tbr': round(tbr, 1),
            'block_tir': block_tir,
            'loop_aggressiveness': round(loop_aggr, 2),
            'pct_suspended': round(pct_suspended, 1),
            'pct_max_delivery': round(pct_max, 1),
            'meals_per_day': round(meals_per_day, 1),
            'corrections_per_day': round(corrections_per_day, 1),
            'glucose_quintile_trend': trend,
            'quintiles': quintiles,
            'problems': problems,
            'n_problems': len(problems),
        })

    return results


# ─── EXP-1383: Prospective Validation ───────────────────────────────

def exp_1383_prospective(patients, detail=False, preconditions=None):
    """Train recommendations on first half, measure if second half is better/worse
    in the direction the recommendations predict."""
    results = {'name': 'EXP-1383: Prospective validation',
               'n_patients': len(patients), 'per_patient': []}

    THIRDS = 3

    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        n = len(glucose)
        isf_profile = float(np.nanmean(pk[:, 7] * 200.0))
        third = n // THIRDS

        # Compute metrics for each third
        third_metrics = []
        for t in range(THIRDS):
            start = t * third
            end = (t + 1) * third if t < THIRDS - 1 else n
            m = compute_window_metrics(glucose[start:end], bolus[start:end],
                                        carbs[start:end], end - start, isf_profile)
            if m is not None:
                m['score'] = compute_therapy_score(m)
                third_metrics.append(m)

        if len(third_metrics) < THIRDS:
            results['per_patient'].append({
                'patient': p['name'], 'note': 'Insufficient data per third'})
            continue

        # Recommendations from first third
        recs_t1 = generate_recommendations(third_metrics[0])

        # Track predicted direction vs actual change
        predictions = []
        for rec in recs_t1:
            if rec['param'] == 'basal':
                # Predicted: drift should decrease if basal changed
                actual_change = abs(third_metrics[2]['drift']) - abs(third_metrics[0]['drift'])
                predicted_direction = 'decrease_drift'
                correct = actual_change < 0
            elif rec['param'] == 'dinner_cr':
                actual_change = third_metrics[2]['dinner_excursion'] - third_metrics[0]['dinner_excursion']
                predicted_direction = 'decrease_excursion'
                correct = actual_change < 0
            elif rec['param'] == 'isf':
                actual_change = abs(third_metrics[2]['isf_ratio'] - 1.0) - abs(third_metrics[0]['isf_ratio'] - 1.0)
                predicted_direction = 'closer_to_1'
                correct = actual_change < 0
            else:
                continue
            predictions.append({
                'param': rec['param'],
                'predicted': predicted_direction,
                'actual_change': round(actual_change, 2),
                'correct_direction': correct,
                'confidence': rec['confidence'],
            })

        score_t1 = third_metrics[0]['score']
        score_t2 = third_metrics[1]['score']
        score_t3 = third_metrics[2]['score']
        natural_trend = score_t3 - score_t1

        results['per_patient'].append({
            'patient': p['name'],
            'archetype': PATIENT_ARCHETYPE.get(p['name'], 'unknown'),
            'score_t1': round(score_t1, 1),
            'score_t2': round(score_t2, 1),
            'score_t3': round(score_t3, 1),
            'natural_trend': round(natural_trend, 1),
            'n_recommendations': len(recs_t1),
            'predictions': predictions,
            'n_correct': sum(1 for p2 in predictions if p2['correct_direction']),
            'accuracy': round(sum(1 for p2 in predictions if p2['correct_direction']) /
                              max(1, len(predictions)), 2),
        })

    pp = [r for r in results['per_patient'] if r.get('n_recommendations', 0) > 0]
    if pp:
        results['n_with_recs'] = len(pp)
        results['mean_accuracy'] = round(
            float(np.mean([r['accuracy'] for r in pp])), 2)
        results['mean_natural_trend'] = round(
            float(np.mean([r['natural_trend'] for r in pp])), 1)
    all_pp = [r for r in results['per_patient'] if 'score_t1' in r]
    if all_pp:
        results['n_patients_with_data'] = len(all_pp)
        results['mean_score_t1'] = round(float(np.mean([r['score_t1'] for r in all_pp])), 1)
        results['mean_score_t3'] = round(float(np.mean([r['score_t3'] for r in all_pp])), 1)
    return results


# ─── EXP-1384: Bayesian ISF Estimation ──────────────────────────────

def exp_1384_bayesian_isf(patients, detail=False, preconditions=None):
    """Bayesian ISF: shrink estimates toward profile using prior strength."""
    results = {'name': 'EXP-1384: Bayesian ISF estimation',
               'n_patients': len(patients), 'per_patient': []}

    PRIOR_STRENGTHS = [0.0, 0.25, 0.5, 0.75, 1.0]  # 0=pure data, 1=pure prior

    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        n = len(glucose)
        isf_profile = float(np.nanmean(pk[:, 7] * 200.0))

        # All events and deconfounded events
        all_events = fit_correction_events(glucose, bolus, carbs, n)
        deconf_events = fit_correction_events(glucose, bolus, carbs, n, min_bolus=2.0)

        # Split-half for validation
        mid = n // 2
        events_h1 = fit_correction_events(glucose[:mid], bolus[:mid], carbs[:mid], mid, min_bolus=2.0)
        events_h2 = fit_correction_events(glucose[mid:], bolus[mid:], carbs[mid:], n - mid, min_bolus=2.0)
        true_isf_h2 = float(np.median([e['isf'] for e in events_h2])) if events_h2 else isf_profile

        sweep = {}
        for alpha in PRIOR_STRENGTHS:
            if events_h1:
                data_isf = float(np.median([e['isf'] for e in events_h1]))
                n_events = len(events_h1)
                # Bayesian: weighted average of prior and data
                # Effective alpha: shrink more when n is small
                effective_alpha = alpha + (1 - alpha) * max(0, 1 - n_events / 10)
                bayesian_isf = effective_alpha * isf_profile + (1 - effective_alpha) * data_isf
            else:
                bayesian_isf = isf_profile
                n_events = 0

            error = abs(bayesian_isf - true_isf_h2) / (true_isf_h2 + 1e-6)
            sweep[f'alpha_{alpha}'] = {
                'bayesian_isf': round(bayesian_isf, 1),
                'h2_isf': round(true_isf_h2, 1),
                'error_pct': round(error * 100, 1),
                'n_h1_events': n_events,
            }

        best_alpha = min(sweep, key=lambda k: sweep[k]['error_pct'])

        results['per_patient'].append({
            'patient': p['name'],
            'archetype': PATIENT_ARCHETYPE.get(p['name'], 'unknown'),
            'profile_isf': round(isf_profile, 1),
            'n_all_events': len(all_events),
            'n_deconf_events': len(deconf_events),
            'best_alpha': best_alpha,
            'best_error_pct': sweep[best_alpha]['error_pct'],
            'sweep': sweep if detail else {},
        })

    pp = [r for r in results['per_patient'] if r.get('n_deconf_events', 0) > 0]
    if pp:
        alpha_votes = defaultdict(int)
        for r in pp:
            alpha_votes[r['best_alpha']] += 1
        results['alpha_distribution'] = dict(alpha_votes)
        results['mean_best_error'] = round(
            float(np.mean([r['best_error_pct'] for r in pp])), 1)
    return results


# ─── EXP-1385: Score Weight Optimization ─────────────────────────────

def exp_1385_score_weights(patients, detail=False, preconditions=None):
    """Optimize score component weights for better archetype separation."""
    results = {'name': 'EXP-1385: Score weight optimization',
               'n_patients': len(patients), 'per_patient': []}

    WEIGHT_CONFIGS = [
        ('default', [40, 20, 20, 10, 10]),
        ('tir_heavy', [60, 15, 15, 5, 5]),
        ('balanced', [30, 20, 20, 15, 15]),
        ('basal_cr_focused', [25, 30, 30, 10, 5]),
        ('clinical', [35, 25, 25, 10, 5]),
    ]

    patient_components = []
    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        n = len(glucose)
        isf_profile = float(np.nanmean(pk[:, 7] * 200.0))
        archetype = PATIENT_ARCHETYPE.get(p['name'], 'unknown')

        m = compute_window_metrics(glucose, bolus, carbs, n, isf_profile)
        if m is None:
            continue

        # Raw component values (0-1 normalized)
        tir_raw = min(1, m['tir'] / 85)
        basal_raw = max(0, 1 - abs(m['drift']) / 10)
        cr_raw = max(0, 1 - (m['mean_excursion'] - 30) / 80)
        isf_raw = max(0, 1 - abs(m['isf_ratio'] - 1.0) / 2)
        cv_raw = max(0, 1 - m['cv'] / 0.33)

        patient_components.append({
            'patient': p['name'],
            'archetype': archetype,
            'components': [tir_raw, basal_raw, cr_raw, isf_raw, cv_raw],
        })

    # Evaluate each weight config
    config_results = {}
    for cname, weights in WEIGHT_CONFIGS:
        total_w = sum(weights)
        norm_w = [w / total_w for w in weights]

        scores_by_arch = defaultdict(list)
        for pc in patient_components:
            score = sum(c * w for c, w in zip(pc['components'], norm_w)) * 100
            scores_by_arch[pc['archetype']].append(score)

        # Separation metric: gap between well-cal mean and needs-tuning mean
        wc_mean = float(np.mean(scores_by_arch.get('well-calibrated', [0])))
        nt_mean = float(np.mean(scores_by_arch.get('needs-tuning', [0])))
        separation = wc_mean - nt_mean

        # Also check within-group variance
        wc_std = float(np.std(scores_by_arch.get('well-calibrated', [0])))
        nt_std = float(np.std(scores_by_arch.get('needs-tuning', [0])))
        cohens_d = separation / (np.sqrt((wc_std ** 2 + nt_std ** 2) / 2) + 1e-6)

        config_results[cname] = {
            'weights': weights,
            'well_cal_mean': round(wc_mean, 1),
            'needs_tuning_mean': round(nt_mean, 1),
            'separation': round(separation, 1),
            'cohens_d': round(cohens_d, 2),
        }

    results['configs'] = config_results
    best_config = max(config_results, key=lambda k: config_results[k]['cohens_d'])
    results['best_config'] = best_config
    results['best_cohens_d'] = config_results[best_config]['cohens_d']
    results['best_weights'] = config_results[best_config]['weights']
    results['per_patient'] = patient_components
    return results


# ─── EXP-1386: Impact-Based Recommendation Ranking ──────────────────

def exp_1386_impact_ranking(patients, detail=False, preconditions=None):
    """Rank recommendations by expected TIR impact."""
    results = {'name': 'EXP-1386: Impact-based recommendation ranking',
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

        gv = glucose[valid]
        if len(gv) < STEPS_PER_DAY:
            results['per_patient'].append({'patient': p['name'], 'note': 'Insufficient data'})
            continue

        tir = float(np.sum((gv >= 70) & (gv <= 180))) / len(gv) * 100

        # Estimate impact of each intervention
        impacts = []

        # Basal impact: steps spent drifting out of range overnight
        on_mask = np.zeros(n, dtype=bool)
        for i in range(n):
            hour = (i % STEPS_PER_DAY) / STEPS_PER_HOUR
            if 0 <= hour < 6:
                on_mask[i] = True
        on_glucose = glucose[valid & on_mask]
        if len(on_glucose) > 0:
            on_oor = float(np.sum((on_glucose < 70) | (on_glucose > 180))) / len(on_glucose) * 100
            overnight_frac = float(np.sum(valid & on_mask)) / float(np.sum(valid))
            basal_tir_impact = on_oor * overnight_frac * 0.5  # 50% correction assumption
            impacts.append({
                'param': 'basal', 'estimated_tir_gain': round(basal_tir_impact, 1),
                'current_oor_pct': round(on_oor, 1), 'time_fraction': round(overnight_frac, 2),
            })

        # CR impact: post-meal OOR contribution
        MEAL_BLOCKS = [('dinner', 14, 20), ('lunch', 10, 14), ('breakfast', 6, 10)]
        for bname, blo, bhi in MEAL_BLOCKS:
            exc = get_meal_excursions(glucose, bolus, carbs, n, blo, bhi)
            if len(exc) < 3:
                continue
            high_exc = [e for e in exc if e['excursion'] > 70]
            if not high_exc:
                continue
            # Estimate post-meal OOR minutes per day
            mean_exc = float(np.mean([e['excursion'] for e in high_exc]))
            meals_per_day = len(exc) / (n / STEPS_PER_DAY)
            # Each high excursion meal spends ~2h above range
            cr_tir_impact = (len(high_exc) / len(exc)) * meals_per_day * (2 / 24) * 50
            impacts.append({
                'param': f'{bname}_cr', 'estimated_tir_gain': round(cr_tir_impact, 1),
                'n_flagged': len(high_exc), 'n_total': len(exc),
                'mean_excursion': round(mean_exc, 1),
            })

        # Sort by impact
        impacts.sort(key=lambda x: x['estimated_tir_gain'], reverse=True)

        results['per_patient'].append({
            'patient': p['name'],
            'archetype': PATIENT_ARCHETYPE.get(p['name'], 'unknown'),
            'current_tir': round(tir, 1),
            'ranked_impacts': impacts,
            'top_priority': impacts[0]['param'] if impacts else 'none',
            'total_estimated_gain': round(sum(i['estimated_tir_gain'] for i in impacts), 1),
        })

    return results


# ─── EXP-1387: Temporal Therapy Drift Patterns ──────────────────────

def exp_1387_temporal_drift(patients, detail=False, preconditions=None):
    """Detect seasonal or temporal patterns in therapy quality."""
    results = {'name': 'EXP-1387: Temporal therapy drift',
               'n_patients': len(patients), 'per_patient': []}

    WEEK_STEPS = 7 * STEPS_PER_DAY

    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        n = len(glucose)
        isf_profile = float(np.nanmean(pk[:, 7] * 200.0))

        weekly_scores = []
        for start in range(0, n - WEEK_STEPS, WEEK_STEPS):
            end = start + WEEK_STEPS
            m = compute_window_metrics(glucose[start:end], bolus[start:end],
                                        carbs[start:end], end - start, isf_profile)
            if m is not None:
                weekly_scores.append({
                    'week': start // WEEK_STEPS,
                    'score': compute_therapy_score(m),
                    'tir': m['tir'],
                    'drift': m['drift'],
                    'excursion': m['mean_excursion'],
                })

        if len(weekly_scores) < 8:
            results['per_patient'].append({
                'patient': p['name'], 'n_weeks': len(weekly_scores),
                'note': 'Too few weeks'})
            continue

        scores = np.array([w['score'] for w in weekly_scores])
        weeks = np.arange(len(scores))

        # Linear trend
        if np.std(weeks) > 0:
            try:
                coeffs = np.polyfit(weeks, scores, 1)
                trend_per_month = float(coeffs[0]) * 4.3
                r2 = 1 - (np.sum((scores - np.polyval(coeffs, weeks)) ** 2) /
                          (np.sum((scores - np.mean(scores)) ** 2) + 1e-10))
            except np.linalg.LinAlgError:
                trend_per_month, r2 = 0.0, 0.0
        else:
            trend_per_month, r2 = 0.0, 0.0

        # Detect regime changes (score shifts >10 points)
        regime_changes = 0
        for i in range(4, len(scores)):
            before = float(np.mean(scores[max(0, i - 4):i]))
            after = float(np.mean(scores[i:min(len(scores), i + 4)]))
            if abs(after - before) > 10:
                regime_changes += 1

        results['per_patient'].append({
            'patient': p['name'],
            'n_weeks': len(weekly_scores),
            'mean_score': round(float(np.mean(scores)), 1),
            'score_std': round(float(np.std(scores)), 1),
            'trend_per_month': round(trend_per_month, 1),
            'trend_r2': round(r2, 3),
            'trend_direction': 'improving' if trend_per_month > 2 else (
                               'declining' if trend_per_month < -2 else 'stable'),
            'regime_changes': regime_changes,
            'best_week_score': round(float(np.max(scores)), 1),
            'worst_week_score': round(float(np.min(scores)), 1),
            'weeks': weekly_scores if detail else [],
        })

    pp = [r for r in results['per_patient'] if r.get('n_weeks', 0) >= 8]
    if pp:
        results['n_patients_with_data'] = len(pp)
        results['n_improving'] = sum(1 for r in pp if r.get('trend_direction') == 'improving')
        results['n_declining'] = sum(1 for r in pp if r.get('trend_direction') == 'declining')
        results['n_stable'] = sum(1 for r in pp if r.get('trend_direction') == 'stable')
        results['mean_regime_changes'] = round(
            float(np.mean([r['regime_changes'] for r in pp])), 1)
    return results


# ─── EXP-1388: Cross-Patient Recommendation Transfer ────────────────

def exp_1388_transfer(patients, detail=False, preconditions=None):
    """Test if recommendations from one patient's archetype apply to others."""
    results = {'name': 'EXP-1388: Cross-patient recommendation transfer',
               'n_patients': len(patients), 'per_patient': []}

    # Compute per-patient metrics and recommendations
    patient_data = []
    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        n = len(glucose)
        isf_profile = float(np.nanmean(pk[:, 7] * 200.0))
        archetype = PATIENT_ARCHETYPE.get(p['name'], 'unknown')

        m = compute_window_metrics(glucose, bolus, carbs, n, isf_profile)
        if m is None:
            continue
        recs = generate_recommendations(m)
        patient_data.append({
            'patient': p['name'], 'archetype': archetype,
            'metrics': m, 'recs': recs,
            'score': compute_therapy_score(m),
        })

    # For each patient, check if same-archetype recommendations match
    for pd in patient_data:
        same_arch = [o for o in patient_data
                     if o['archetype'] == pd['archetype'] and o['patient'] != pd['patient']]
        if not same_arch:
            results['per_patient'].append({
                'patient': pd['patient'], 'note': 'Only member of archetype'})
            continue

        # Check recommendation agreement
        my_params = set(r['param'] for r in pd['recs'])
        agreements = []
        for other in same_arch:
            other_params = set(r['param'] for r in other['recs'])
            overlap = my_params & other_params
            union = my_params | other_params
            jaccard = len(overlap) / max(1, len(union))
            agreements.append(jaccard)

        results['per_patient'].append({
            'patient': pd['patient'],
            'archetype': pd['archetype'],
            'n_recs': len(pd['recs']),
            'rec_params': list(my_params),
            'n_same_arch': len(same_arch),
            'mean_jaccard': round(float(np.mean(agreements)), 2),
            'score': round(pd['score'], 1),
        })

    pp = [r for r in results['per_patient'] if 'mean_jaccard' in r]
    if pp:
        for arch in ARCHETYPES:
            arch_pp = [r for r in pp if r.get('archetype') == arch]
            if arch_pp:
                results[f'{arch}_mean_jaccard'] = round(
                    float(np.mean([r['mean_jaccard'] for r in arch_pp])), 2)
    return results


# ─── EXP-1389: Minimum Data Requirements ────────────────────────────

def exp_1389_min_data(patients, detail=False, preconditions=None):
    """How much data is needed for reliable recommendations?"""
    results = {'name': 'EXP-1389: Minimum data requirements',
               'n_patients': len(patients), 'per_patient': []}

    DURATIONS_DAYS = [7, 14, 21, 30, 45, 60, 90]

    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        n = len(glucose)
        isf_profile = float(np.nanmean(pk[:, 7] * 200.0))

        # Full dataset as ground truth
        m_full = compute_window_metrics(glucose, bolus, carbs, n, isf_profile)
        if m_full is None:
            results['per_patient'].append({'patient': p['name'], 'note': 'Insufficient data'})
            continue
        recs_full = generate_recommendations(m_full)
        full_params = set(r['param'] for r in recs_full)
        score_full = compute_therapy_score(m_full)

        duration_results = {}
        for days in DURATIONS_DAYS:
            steps = days * STEPS_PER_DAY
            if steps >= n:
                continue

            # Average over multiple starting points
            agreements = []
            score_errors = []
            for start in range(0, n - steps, steps // 2):
                end = start + steps
                m = compute_window_metrics(glucose[start:end], bolus[start:end],
                                            carbs[start:end], end - start, isf_profile)
                if m is None:
                    continue
                recs = generate_recommendations(m)
                sub_params = set(r['param'] for r in recs)
                union = full_params | sub_params
                overlap = full_params & sub_params
                jaccard = len(overlap) / max(1, len(union)) if union else 1.0
                agreements.append(jaccard)
                score_errors.append(abs(compute_therapy_score(m) - score_full))

            if agreements:
                duration_results[f'{days}d'] = {
                    'mean_agreement': round(float(np.mean(agreements)), 2),
                    'mean_score_error': round(float(np.mean(score_errors)), 1),
                    'n_windows': len(agreements),
                }

        results['per_patient'].append({
            'patient': p['name'],
            'full_score': round(score_full, 1),
            'full_n_recs': len(recs_full),
            'durations': duration_results,
        })

    # Find minimum duration for 80% agreement
    pp = [r for r in results['per_patient'] if 'durations' in r]
    if pp:
        for days in DURATIONS_DAYS:
            key = f'{days}d'
            agrees = [r['durations'][key]['mean_agreement']
                      for r in pp if key in r.get('durations', {})]
            errors = [r['durations'][key]['mean_score_error']
                      for r in pp if key in r.get('durations', {})]
            if agrees:
                results[f'{days}d_mean_agreement'] = round(float(np.mean(agrees)), 2)
                results[f'{days}d_mean_score_error'] = round(float(np.mean(errors)), 1)

        # Find threshold
        for days in DURATIONS_DAYS:
            key = f'{days}d_mean_agreement'
            if results.get(key, 0) >= 0.8:
                results['min_days_80pct_agreement'] = days
                break
    return results


# ─── EXP-1390: End-to-End Triage Accuracy ───────────────────────────

def exp_1390_triage_accuracy(patients, detail=False, preconditions=None):
    """Full pipeline accuracy: preconditions → scoring → recommendations → validation."""
    results = {'name': 'EXP-1390: End-to-end triage accuracy',
               'n_patients': len(patients), 'per_patient': []}

    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        n = len(glucose)
        isf_profile = float(np.nanmean(pk[:, 7] * 200.0))
        archetype = PATIENT_ARCHETYPE.get(p['name'], 'unknown')

        # Step 1: Preconditions
        pc = assess_preconditions(p)
        precond_met = sum(1 for v in pc['preconditions'].values() if v['met'])
        precond_total = len(pc['preconditions'])
        precond_pass = precond_met >= 4

        # Step 2: Compute score
        m = compute_window_metrics(glucose, bolus, carbs, n, isf_profile)
        if m is None:
            results['per_patient'].append({
                'patient': p['name'], 'note': 'No metrics'})
            continue
        score = compute_therapy_score(m)
        grade = ('A' if score >= 80 else 'B' if score >= 65 else
                 'C' if score >= 50 else 'D' if score >= 35 else 'F')

        # Step 3: Recommendations (optimized thresholds)
        recs = generate_recommendations(m, thresholds={
            'drift': 5.0, 'excursion': 70.0, 'isf_ratio': 2.0})

        # Step 4: Validate with split-half
        mid = n // 2
        m_h1 = compute_window_metrics(glucose[:mid], bolus[:mid], carbs[:mid],
                                       mid, isf_profile)
        m_h2 = compute_window_metrics(glucose[mid:], bolus[mid:], carbs[mid:],
                                       n - mid, isf_profile)

        if m_h1 and m_h2:
            recs_h1 = generate_recommendations(m_h1, thresholds={
                'drift': 5.0, 'excursion': 70.0, 'isf_ratio': 2.0})
            recs_h2 = generate_recommendations(m_h2, thresholds={
                'drift': 5.0, 'excursion': 70.0, 'isf_ratio': 2.0})
            h1_params = set(r['param'] for r in recs_h1)
            h2_params = set(r['param'] for r in recs_h2)
            union = h1_params | h2_params
            overlap = h1_params & h2_params
            temporal_agreement = len(overlap) / max(1, len(union)) if union else 1.0
            score_h1 = compute_therapy_score(m_h1)
            score_h2 = compute_therapy_score(m_h2)
            score_stability = 1 - abs(score_h1 - score_h2) / max(score_h1, score_h2, 1)
        else:
            temporal_agreement = 0.0
            score_stability = 0.0
            score_h1, score_h2 = score, score

        # Triage appropriateness check
        expected_actions = {
            'well-calibrated': (0, 1),
            'needs-tuning': (1, 4),
            'miscalibrated': (2, 6),
        }
        exp_lo, exp_hi = expected_actions.get(archetype, (0, 6))
        actions_appropriate = exp_lo <= len(recs) <= exp_hi

        results['per_patient'].append({
            'patient': p['name'],
            'archetype': archetype,
            'precond_pass': precond_pass,
            'precond_met': f'{precond_met}/{precond_total}',
            'score': round(score, 1),
            'grade': grade,
            'n_recommendations': len(recs),
            'rec_params': [r['param'] for r in recs],
            'temporal_agreement': round(temporal_agreement, 2),
            'score_stability': round(score_stability, 2),
            'score_h1': round(score_h1, 1),
            'score_h2': round(score_h2, 1),
            'actions_appropriate': actions_appropriate,
        })

    pp = results['per_patient']
    valid = [r for r in pp if 'score' in r]
    if valid:
        results['n_precond_pass'] = sum(1 for r in valid if r.get('precond_pass'))
        results['n_appropriate_actions'] = sum(1 for r in valid if r.get('actions_appropriate'))
        results['mean_temporal_agreement'] = round(
            float(np.mean([r['temporal_agreement'] for r in valid])), 2)
        results['mean_score_stability'] = round(
            float(np.mean([r['score_stability'] for r in valid])), 2)
        results['grade_accuracy'] = round(
            sum(1 for r in valid
                if (r['grade'] in ('A', 'B') and r['archetype'] == 'well-calibrated')
                or (r['grade'] in ('C', 'D') and r['archetype'] != 'well-calibrated'))
            / len(valid), 2)
    return results


# ─── Experiment Registry ─────────────────────────────────────────────

EXPERIMENTS = {
    1381: ('Temporal smoothing', exp_1381_temporal_smoothing),
    1382: ('Complex case analysis', exp_1382_complex_cases),
    1383: ('Prospective validation', exp_1383_prospective),
    1384: ('Bayesian ISF estimation', exp_1384_bayesian_isf),
    1385: ('Score weight optimization', exp_1385_score_weights),
    1386: ('Impact-based ranking', exp_1386_impact_ranking),
    1387: ('Temporal therapy drift', exp_1387_temporal_drift),
    1388: ('Cross-patient transfer', exp_1388_transfer),
    1389: ('Minimum data requirements', exp_1389_min_data),
    1390: ('End-to-end triage accuracy', exp_1390_triage_accuracy),
}


def main():
    parser = argparse.ArgumentParser(
        description='EXP-1381-1390: Temporal Smoothing & Pipeline Validation')
    parser.add_argument('--exp', type=int, help='Run single experiment')
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--max-patients', type=int, default=11)
    args = parser.parse_args()

    print(f"Loading patients (max={args.max_patients})...")
    patients = load_patients(PATIENTS_DIR, max_patients=args.max_patients)
    print(f"Loaded {len(patients)} patients")

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
                             'configs', 'sweep', 'levels', 'windows',
                             'durations', 'weeks', 'components'):
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

    print(f"\n{'='*60}")
    print("TEMPORAL SMOOTHING & PIPELINE VALIDATION SUMMARY")
    print(f"{'='*60}")
    for eid, result in sorted(all_results.items()):
        name = EXPERIMENTS[eid][0]
        if 'error' in result:
            print(f"  EXP-{eid} {name}: FAILED - {result['error']}")
        else:
            key_metrics = {
                1381: f"basal_k2={result.get('mean_basal_stability_k2','?')}, cr_k2={result.get('mean_cr_stability_k2','?')}",
                1382: f"complex case profiles generated",
                1383: f"accuracy={result.get('mean_accuracy','?')}, trend={result.get('mean_natural_trend','?')}",
                1384: f"best_alpha={result.get('alpha_distribution','?')}, error={result.get('mean_best_error','?')}%",
                1385: f"best={result.get('best_config','?')}, d={result.get('best_cohens_d','?')}",
                1386: f"impact-ranked recommendations per patient",
                1387: f"improving={result.get('n_improving','?')}, declining={result.get('n_declining','?')}, stable={result.get('n_stable','?')}",
                1388: f"well-cal jaccard={result.get('well-calibrated_mean_jaccard','?')}, needs={result.get('needs-tuning_mean_jaccard','?')}",
                1389: f"min_days={result.get('min_days_80pct_agreement','?')}",
                1390: f"grade_acc={result.get('grade_accuracy','?')}, temporal_agree={result.get('mean_temporal_agreement','?')}",
            }
            print(f"  EXP-{eid} {name}: {key_metrics.get(eid, 'done')}")

    return all_results


if __name__ == '__main__':
    main()
