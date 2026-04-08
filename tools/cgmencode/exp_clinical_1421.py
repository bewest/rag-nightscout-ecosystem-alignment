#!/usr/bin/env python3
"""EXP-1421 to EXP-1430: Multi-param intervention cycles, AID limits & long-term stability."""

import argparse
import json
import numpy as np
import os
import sys
import time
import traceback
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from cgmencode.exp_metabolic_flux import load_patients as _load_patients

PATIENTS_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'externals', 'ns-data', 'patients')

STEPS_PER_HOUR = 12
STEPS_PER_DAY = 24 * STEPS_PER_HOUR  # 288
WEEKLY_STEPS = 7 * STEPS_PER_DAY
BIWEEKLY_STEPS = 14 * STEPS_PER_DAY

SEGMENT_NAMES = ['midnight(0-6)', 'morning(6-12)', 'afternoon(12-18)', 'evening(18-24)']
SEGMENT_HOURS = [(0, 6), (6, 12), (12, 18), (18, 24)]

DAWN_PATIENTS = {'a', 'd', 'j'}
GRADE_D_PATIENTS = {'a', 'c', 'i'}
STABLE_PATIENTS = {'k', 'a'}

SCORE_WEIGHTS = {'tir': 60, 'basal': 15, 'cr': 15, 'isf': 5, 'cv': 5}
DRIFT_THRESHOLD = 5.0       # mg/dL/h
EXCURSION_THRESHOLD = 70    # mg/dL
CV_THRESHOLD = 36           # %
MIN_BOLUS_ISF = 2.0         # U
MIN_ISF_EVENTS = 5

EXPERIMENTS = {}


def register(exp_id, title):
    """Decorator to register experiment functions."""
    def decorator(fn):
        EXPERIMENTS[exp_id] = (title, fn)
        return fn
    return decorator


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
def load_patients(max_patients=11):
    """Load patient data with CGM + insulin channels."""
    raw = _load_patients(PATIENTS_DIR, max_patients=max_patients)
    result = {}
    for p in raw:
        pid = p['name']
        df = p['df']
        glucose = df['glucose'].values
        valid = ~np.isnan(glucose)
        if valid.sum() < 1000:
            continue
        result[pid] = {
            'df': df,
            'glucose': glucose,
            'valid': valid,
            'timestamps': df.index,
            'bolus': df['bolus'].values if 'bolus' in df.columns else np.zeros(len(df)),
            'carbs': df['carbs'].values if 'carbs' in df.columns else np.zeros(len(df)),
            'temp_rate': df['temp_rate'].values if 'temp_rate' in df.columns else np.zeros(len(df)),
            'iob': df['iob'].values if 'iob' in df.columns else np.zeros(len(df)),
            'cob': df['cob'].values if 'cob' in df.columns else np.zeros(len(df)),
        }
        if 'pk' in p and p['pk'] is not None:
            result[pid]['pk'] = p['pk']
    return result


def load_profile(pid):
    """Load profile.json for a patient, return the default profile store."""
    profile_path = Path(PATIENTS_DIR) / pid / 'training' / 'profile.json'
    if not profile_path.exists():
        return None
    try:
        with open(profile_path) as f:
            profiles = json.load(f)
        if not profiles:
            return None
        prof = profiles[0] if isinstance(profiles, list) else profiles
        store = prof.get('store', {})
        default_name = prof.get('defaultProfile', 'Default')
        default = store.get(default_name, next(iter(store.values()), None))
        if default:
            default['_units'] = prof.get('units', default.get('units', 'mg/dL'))
        return default
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Shared helper functions
# ---------------------------------------------------------------------------
def get_basal_rate_at_seconds(basal_schedule, time_seconds):
    """Get basal rate (U/h) at a given time-of-day in seconds."""
    if not basal_schedule:
        return 1.0
    rate = basal_schedule[0].get('value', 1.0)
    for entry in basal_schedule:
        t = entry.get('timeAsSeconds', 0)
        if t <= time_seconds:
            rate = entry.get('value', rate)
        else:
            break
    return float(rate)


def get_segment_basal(basal_schedule, h_start, h_end):
    """Get average basal rate across a segment (hourly average)."""
    if not basal_schedule:
        return 1.0
    rates = []
    for h in range(h_start, h_end):
        sec = h * 3600
        rates.append(get_basal_rate_at_seconds(basal_schedule, sec))
    return float(np.mean(rates))


def compute_segment_drift(glucose, bolus, carbs, day_start, h_start, h_end):
    """Compute glucose drift (mg/dL/h) for a segment on a given day.

    Filters out windows with recent bolus (4h) or carbs (3h).
    Returns drift in mg/dL/h or NaN if insufficient data.
    """
    seg_start = day_start + h_start * STEPS_PER_HOUR
    seg_end = day_start + h_end * STEPS_PER_HOUR
    n = len(glucose)
    if seg_end > n or seg_start < 0:
        return np.nan

    seg_g = glucose[seg_start:seg_end].copy()
    seg_valid = ~np.isnan(seg_g)
    if seg_valid.sum() < STEPS_PER_HOUR:
        return np.nan

    lookback_bolus = 4 * STEPS_PER_HOUR
    lookback_carbs = 3 * STEPS_PER_HOUR
    check_start_b = max(0, seg_start - lookback_bolus)
    check_start_c = max(0, seg_start - lookback_carbs)
    if np.nansum(bolus[check_start_b:seg_end]) > 0.3:
        return np.nan
    if np.nansum(carbs[check_start_c:seg_end]) > 2.0:
        return np.nan

    valid_idx = np.where(seg_valid)[0]
    valid_bg = seg_g[valid_idx]
    hours = valid_idx / STEPS_PER_HOUR
    if len(valid_idx) < 3:
        return np.nan
    coeffs = np.polyfit(hours, valid_bg, 1)
    return float(coeffs[0])


def compute_tir(glucose, lo=70, hi=180):
    """Compute time-in-range percentage."""
    valid = glucose[~np.isnan(glucose)]
    if len(valid) == 0:
        return 0.0
    return float(np.mean((valid >= lo) & (valid <= hi)) * 100)


def compute_cv(glucose):
    """Compute coefficient of variation (%)."""
    valid = glucose[~np.isnan(glucose)]
    if len(valid) < 10 or np.mean(valid) < 1:
        return 100.0
    return float(np.std(valid) / np.mean(valid) * 100)


def compute_max_excursion(glucose, carbs, n):
    """Compute max post-meal excursion (90th percentile)."""
    excursions = []
    window = 4 * STEPS_PER_HOUR
    for i in range(n):
        if carbs[i] < 5 or np.isnan(glucose[i]):
            continue
        end = min(i + window, n)
        post = glucose[i:end]
        valid_post = post[~np.isnan(post)]
        if len(valid_post) < STEPS_PER_HOUR:
            continue
        excursion = float(np.nanmax(valid_post) - glucose[i])
        excursions.append(excursion)
    if not excursions:
        return 0.0
    return float(np.percentile(excursions, 90))


def compute_isf_ratio(glucose, bolus, carbs, n):
    """Deconfounded ISF: only correction boluses >=2U, no carbs +-60min, need >=5 events."""
    events = []
    carb_window = STEPS_PER_HOUR
    response_window = 3 * STEPS_PER_HOUR
    for i in range(n):
        if bolus[i] < MIN_BOLUS_ISF or np.isnan(glucose[i]):
            continue
        c_start = max(0, i - carb_window)
        c_end = min(n, i + carb_window)
        if np.nansum(carbs[c_start:c_end]) > 2:
            continue
        end = min(i + response_window, n)
        post = glucose[i:end]
        valid_post = post[~np.isnan(post)]
        if len(valid_post) < response_window // 2:
            continue
        drop = glucose[i] - np.nanmin(valid_post)
        observed_isf = drop / bolus[i] if bolus[i] > 0 else 0
        events.append(observed_isf)
    if len(events) < MIN_ISF_EVENTS:
        return 1.0
    return float(np.median(events))


def compute_therapy_score(tir, drift, max_excursion, isf_ratio, cv):
    """Compute therapy score 0-100."""
    tir_score = min(tir, 100) / 100 * SCORE_WEIGHTS['tir']
    basal_ok = 1.0 if abs(drift) < DRIFT_THRESHOLD else 0.0
    cr_ok = 1.0 if max_excursion < EXCURSION_THRESHOLD else 0.0
    isf_ok = 1.0
    cv_ok = 1.0 if cv < CV_THRESHOLD else 0.0
    return tir_score + basal_ok * SCORE_WEIGHTS['basal'] + cr_ok * SCORE_WEIGHTS['cr'] + \
        isf_ok * SCORE_WEIGHTS['isf'] + cv_ok * SCORE_WEIGHTS['cv']


def get_grade(score):
    if score >= 80:
        return 'A'
    elif score >= 65:
        return 'B'
    elif score >= 50:
        return 'C'
    else:
        return 'D'


def compute_overnight_drift(glucose, bolus, carbs, n_days, n):
    """Compute median overnight drift across all days."""
    drifts = []
    for d in range(min(n_days, 180)):
        dr = compute_segment_drift(glucose, bolus, carbs, d * STEPS_PER_DAY, 0, 6)
        if not np.isnan(dr):
            drifts.append(abs(dr))
    return float(np.median(drifts)) if drifts else 0.0


def compute_full_assessment(glucose, bolus, carbs, n):
    """Compute full therapy assessment: TIR, drift, excursion, ISF ratio, CV, score, grade."""
    tir = compute_tir(glucose)
    n_days = n // STEPS_PER_DAY
    drift = compute_overnight_drift(glucose, bolus, carbs, n_days, n)
    exc = compute_max_excursion(glucose, carbs, n)
    isf = compute_isf_ratio(glucose, bolus, carbs, n)
    cv = compute_cv(glucose)
    score = compute_therapy_score(tir, drift, exc, isf, cv)
    grade = get_grade(score)
    return {
        'tir': round(tir, 1),
        'drift': round(drift, 2),
        'excursion': round(exc, 1),
        'isf_ratio': round(isf, 2),
        'cv': round(cv, 1),
        'score': round(score, 1),
        'grade': grade,
        'flags': {
            'basal_flag': abs(drift) >= DRIFT_THRESHOLD,
            'cr_flag': exc >= EXCURSION_THRESHOLD,
            'cv_flag': cv >= CV_THRESHOLD,
        }
    }


def generate_recommendations(assessment, profile, pid):
    """Generate recommendations from an assessment. Returns list of recommendation dicts."""
    recs = []
    if assessment['flags']['basal_flag']:
        recs.append({
            'parameter': 'basal',
            'direction': 'increase' if assessment['drift'] > 0 else 'decrease',
            'magnitude': abs(assessment['drift']),
            'reason': f"Overnight drift {assessment['drift']:+.1f} mg/dL/h exceeds threshold",
        })
    if assessment['flags']['cr_flag']:
        recs.append({
            'parameter': 'cr',
            'direction': 'tighten',
            'magnitude': assessment['excursion'] - EXCURSION_THRESHOLD,
            'reason': f"Post-meal excursion {assessment['excursion']:.0f} mg/dL exceeds {EXCURSION_THRESHOLD}",
        })
    if assessment['flags']['cv_flag']:
        recs.append({
            'parameter': 'cv',
            'direction': 'reduce_variability',
            'magnitude': assessment['cv'] - CV_THRESHOLD,
            'reason': f"CV {assessment['cv']:.1f}% exceeds {CV_THRESHOLD}%",
        })
    return recs


def simulate_basal_correction(glucose, drift, isf, magnitude_pct=10):
    """Simulate effect of basal correction on glucose trace.

    Applies a constant offset to overnight (0-6h) glucose based on correcting
    a fraction of the observed drift. Returns corrected glucose copy.
    """
    corrected = glucose.copy()
    n = len(corrected)
    n_days = n // STEPS_PER_DAY
    correction_factor = magnitude_pct / 100.0

    for d in range(n_days):
        for h_start, h_end in [(0, 6)]:
            seg_start = d * STEPS_PER_DAY + h_start * STEPS_PER_HOUR
            seg_end = d * STEPS_PER_DAY + h_end * STEPS_PER_HOUR
            if seg_end > n:
                break
            seg_len = seg_end - seg_start
            # Correction ramp: gradually correct drift across the segment
            correction_per_step = drift * correction_factor / STEPS_PER_HOUR
            for s in range(seg_len):
                idx = seg_start + s
                if not np.isnan(corrected[idx]):
                    corrected[idx] -= correction_per_step * s
    return corrected


def simulate_cr_correction(glucose, carbs, magnitude_pct=10):
    """Simulate effect of CR correction on glucose trace.

    Reduces post-meal excursions by attenuating the rise proportionally.
    """
    corrected = glucose.copy()
    n = len(corrected)
    window = 4 * STEPS_PER_HOUR
    correction_factor = magnitude_pct / 100.0

    for i in range(n):
        if carbs[i] < 5 or np.isnan(glucose[i]):
            continue
        pre_meal = glucose[i]
        end = min(i + window, n)
        for j in range(i + 1, end):
            if not np.isnan(corrected[j]):
                rise = corrected[j] - pre_meal
                if rise > 0:
                    corrected[j] -= rise * correction_factor
    return corrected


def simulate_isf_correction(glucose, bolus, carbs, magnitude_pct=10):
    """Simulate effect of ISF correction on post-correction glucose.

    Enhances the drop from correction boluses.
    """
    corrected = glucose.copy()
    n = len(corrected)
    carb_window = STEPS_PER_HOUR
    response_window = 3 * STEPS_PER_HOUR
    correction_factor = magnitude_pct / 100.0

    for i in range(n):
        if bolus[i] < MIN_BOLUS_ISF or np.isnan(glucose[i]):
            continue
        c_start = max(0, i - carb_window)
        c_end = min(n, i + carb_window)
        if np.nansum(carbs[c_start:c_end]) > 2:
            continue
        end = min(i + response_window, n)
        for j in range(i + 1, end):
            if not np.isnan(corrected[j]):
                drop = glucose[i] - corrected[j]
                if drop > 0:
                    corrected[j] -= drop * correction_factor
    return corrected


# ---------------------------------------------------------------------------
# EXP-1421: Sequential Multi-Parameter Intervention Simulation
# ---------------------------------------------------------------------------
@register(1421, "Sequential Multi-Parameter Intervention Simulation")
def exp_1421(patients, args):
    """Simulate 3-cycle intervention: basal -> CR -> ISF, track grade trajectory."""
    results = {'name': 'EXP-1421: Sequential Multi-Parameter Intervention Simulation'}
    per_patient = []

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs = pdata['carbs']
        n = len(glucose)
        n_days = n // STEPS_PER_DAY

        profile = load_profile(pid)
        sens_schedule = profile.get('sens', []) if profile else []
        units = profile.get('_units', 'mg/dL') if profile else 'mg/dL'
        isf = 50.0
        if sens_schedule:
            isf = float(sens_schedule[0].get('value', 50.0))
            if units == 'mmol/L' or (isinstance(isf, (int, float)) and isf < 10):
                isf *= 18.0

        # Baseline assessment
        baseline = compute_full_assessment(glucose, bolus, carbs, n)

        # Cycle 1: Basal correction (weeks 1-2)
        g_after_basal = simulate_basal_correction(glucose, baseline['drift'], isf, magnitude_pct=10)
        cycle1 = compute_full_assessment(g_after_basal, bolus, carbs, n)

        # Cycle 2: CR correction on post-basal glucose (weeks 3-4)
        g_after_cr = simulate_cr_correction(g_after_basal, carbs, magnitude_pct=10)
        cycle2 = compute_full_assessment(g_after_cr, bolus, carbs, n)

        # Cycle 3: ISF correction on post-CR glucose (weeks 5-6)
        g_after_isf = simulate_isf_correction(g_after_cr, bolus, carbs, magnitude_pct=10)
        cycle3 = compute_full_assessment(g_after_isf, bolus, carbs, n)

        trajectory = [baseline['grade'], cycle1['grade'], cycle2['grade'], cycle3['grade']]
        tir_trajectory = [baseline['tir'], cycle1['tir'], cycle2['tir'], cycle3['tir']]
        tir_improvement = round(cycle3['tir'] - baseline['tir'], 1)

        # Determine which cycle had most impact
        deltas = [
            ('basal', cycle1['tir'] - baseline['tir']),
            ('cr', cycle2['tir'] - cycle1['tir']),
            ('isf', cycle3['tir'] - cycle2['tir']),
        ]
        most_impact_cycle = max(deltas, key=lambda x: abs(x[1]))

        rec = {
            'patient': pid,
            'baseline': baseline,
            'cycle1_basal': cycle1,
            'cycle2_cr': cycle2,
            'cycle3_isf': cycle3,
            'grade_trajectory': trajectory,
            'tir_trajectory': tir_trajectory,
            'cumulative_tir_improvement': tir_improvement,
            'most_impact_cycle': most_impact_cycle[0],
            'most_impact_delta': round(most_impact_cycle[1], 1),
        }
        per_patient.append(rec)
        if args.detail:
            print(f"  {pid}: {' -> '.join(trajectory)} | TIR: {' -> '.join(f'{t:.0f}%' for t in tir_trajectory)} | "
                  f"best cycle={most_impact_cycle[0]} (+{most_impact_cycle[1]:.1f}%)")

    results['per_patient'] = per_patient
    results['n_patients'] = len(per_patient)

    # Summary: how many patients improved grade?
    n_improved = sum(1 for p in per_patient if p['grade_trajectory'][-1] < p['grade_trajectory'][0])
    mean_tir_gain = float(np.mean([p['cumulative_tir_improvement'] for p in per_patient]))
    cycle_impact = defaultdict(list)
    for p in per_patient:
        cycle_impact[p['most_impact_cycle']].append(p['patient'])

    results['n_grade_improved'] = n_improved
    results['mean_tir_gain'] = round(mean_tir_gain, 1)
    results['cycle_impact_distribution'] = {k: len(v) for k, v in cycle_impact.items()}

    print(f"\n  Grade improved: {n_improved}/{len(per_patient)}")
    print(f"  Mean TIR gain after 3 cycles: {mean_tir_gain:+.1f}%")
    print(f"  Most impactful cycle: {dict(results['cycle_impact_distribution'])}")
    return results


# ---------------------------------------------------------------------------
# EXP-1422: AID Max Temp Rate Analysis
# ---------------------------------------------------------------------------
@register(1422, "AID Max Temp Rate Analysis")
def exp_1422(patients, args):
    """Analyze AID temp rate distribution and ceiling effects."""
    results = {'name': 'EXP-1422: AID Max Temp Rate Analysis'}
    per_patient = []

    for pid, pdata in sorted(patients.items()):
        temp_rate = pdata['temp_rate']
        glucose = pdata['glucose']
        n = len(temp_rate)

        profile = load_profile(pid)
        basal_schedule = profile.get('basal', []) if profile else []

        valid_tr = temp_rate[~np.isnan(temp_rate)]
        if len(valid_tr) < 100:
            per_patient.append({
                'patient': pid, 'insufficient_data': True,
                'n_valid': len(valid_tr),
            })
            continue

        # Distribution stats
        p10 = float(np.percentile(valid_tr, 10))
        p50 = float(np.percentile(valid_tr, 50))
        p90 = float(np.percentile(valid_tr, 90))
        p95 = float(np.percentile(valid_tr, 95))
        p99 = float(np.percentile(valid_tr, 99))
        tr_max = float(np.max(valid_tr))
        tr_mean = float(np.mean(valid_tr))

        # Compute what % of time AID is at >90th percentile
        ceiling_threshold = p90
        ceiling_pct = float(np.mean(valid_tr >= ceiling_threshold) * 100)

        # Compute max multiplier: max temp_rate / scheduled basal
        # Use mean scheduled basal as denominator
        if basal_schedule:
            sched_rates = []
            for h in range(24):
                sched_rates.append(get_basal_rate_at_seconds(basal_schedule, h * 3600))
            mean_sched = float(np.mean(sched_rates))
        else:
            mean_sched = 1.0

        max_multiplier = tr_max / mean_sched if mean_sched > 0 else 0.0

        # Per-hour ceiling analysis: when is the AID working hardest?
        hourly_ceiling_pct = []
        for h in range(24):
            hour_vals = []
            n_days = n // STEPS_PER_DAY
            for d in range(min(n_days, 180)):
                start = d * STEPS_PER_DAY + h * STEPS_PER_HOUR
                end = start + STEPS_PER_HOUR
                if end > n:
                    break
                seg = temp_rate[start:end]
                valid_seg = seg[~np.isnan(seg)]
                hour_vals.extend(valid_seg.tolist())
            if hour_vals:
                at_ceiling = float(np.mean(np.array(hour_vals) >= ceiling_threshold) * 100)
            else:
                at_ceiling = 0.0
            hourly_ceiling_pct.append(round(at_ceiling, 1))

        # Ceiling hour: hour with highest ceiling %
        peak_ceiling_hour = int(np.argmax(hourly_ceiling_pct))

        # Glucose during ceiling events vs non-ceiling
        at_ceiling_mask = temp_rate >= ceiling_threshold
        both_valid = at_ceiling_mask & ~np.isnan(glucose) & ~np.isnan(temp_rate)
        if both_valid.sum() > 10:
            glucose_at_ceiling = float(np.nanmean(glucose[at_ceiling_mask & ~np.isnan(glucose)]))
        else:
            glucose_at_ceiling = np.nan
        not_ceiling_mask = (temp_rate < ceiling_threshold) & ~np.isnan(temp_rate) & ~np.isnan(glucose)
        if not_ceiling_mask.sum() > 10:
            glucose_not_ceiling = float(np.nanmean(glucose[not_ceiling_mask]))
        else:
            glucose_not_ceiling = np.nan

        hitting_ceiling_frequently = ceiling_pct > 10.0

        rec = {
            'patient': pid,
            'n_valid_readings': len(valid_tr),
            'temp_rate_p10': round(p10, 3),
            'temp_rate_median': round(p50, 3),
            'temp_rate_p90': round(p90, 3),
            'temp_rate_p95': round(p95, 3),
            'temp_rate_p99': round(p99, 3),
            'temp_rate_max': round(tr_max, 3),
            'temp_rate_mean': round(tr_mean, 3),
            'mean_scheduled_basal': round(mean_sched, 3),
            'max_multiplier': round(max_multiplier, 2),
            'ceiling_pct': round(ceiling_pct, 1),
            'hitting_ceiling_frequently': hitting_ceiling_frequently,
            'peak_ceiling_hour': peak_ceiling_hour,
            'hourly_ceiling_pct': hourly_ceiling_pct,
            'glucose_at_ceiling': round(glucose_at_ceiling, 1) if not np.isnan(glucose_at_ceiling) else None,
            'glucose_not_ceiling': round(glucose_not_ceiling, 1) if not np.isnan(glucose_not_ceiling) else None,
        }
        per_patient.append(rec)
        if args.detail or hitting_ceiling_frequently:
            tag = ' ** CEILING **' if hitting_ceiling_frequently else ''
            print(f"  {pid}: max_mult={max_multiplier:.1f}x, ceiling={ceiling_pct:.1f}%, "
                  f"peak_hr={peak_ceiling_hour}:00{tag}")

    results['per_patient'] = per_patient
    results['n_patients'] = len(per_patient)
    ceiling_patients = [p['patient'] for p in per_patient
                        if not p.get('insufficient_data') and p.get('hitting_ceiling_frequently')]
    results['ceiling_patients'] = ceiling_patients
    results['n_ceiling'] = len(ceiling_patients)

    # Special check for patient a
    patient_a = next((p for p in per_patient if p['patient'] == 'a'), None)
    if patient_a and not patient_a.get('insufficient_data'):
        results['patient_a_analysis'] = {
            'max_multiplier': patient_a['max_multiplier'],
            'ceiling_pct': patient_a['ceiling_pct'],
            'bottleneck': patient_a['hitting_ceiling_frequently'],
            'peak_hour': patient_a['peak_ceiling_hour'],
        }

    print(f"\n  Ceiling patients (>10% at ceiling): {ceiling_patients}")
    if patient_a and not patient_a.get('insufficient_data'):
        print(f"  Patient a: {patient_a['max_multiplier']:.1f}x max, "
              f"{patient_a['ceiling_pct']:.1f}% at ceiling → "
              f"{'BOTTLENECK' if patient_a['hitting_ceiling_frequently'] else 'no bottleneck'}")
    return results


# ---------------------------------------------------------------------------
# EXP-1423: CR Magnitude Sensitivity
# ---------------------------------------------------------------------------
@register(1423, "CR Magnitude Sensitivity")
def exp_1423(patients, args):
    """Test conservative (10%) vs moderate (20%) vs aggressive (30%) CR correction."""
    results = {'name': 'EXP-1423: CR Magnitude Sensitivity'}
    per_patient = []
    magnitudes = [10, 20, 30]

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs = pdata['carbs']
        n = len(glucose)

        baseline_exc = compute_max_excursion(glucose, carbs, n)
        baseline_tir = compute_tir(glucose)

        if baseline_exc < EXCURSION_THRESHOLD:
            per_patient.append({
                'patient': pid,
                'baseline_excursion': round(baseline_exc, 1),
                'baseline_tir': round(baseline_tir, 1),
                'needs_cr_fix': False,
                'magnitude_results': [],
            })
            continue

        mag_results = []
        for mag in magnitudes:
            corrected = simulate_cr_correction(glucose, carbs, magnitude_pct=mag)
            new_exc = compute_max_excursion(corrected, carbs, n)
            new_tir = compute_tir(corrected)
            exc_reduction = baseline_exc - new_exc
            tir_change = new_tir - baseline_tir

            # Check for hypoglycemia increase
            baseline_hypo = float(np.nanmean(glucose[~np.isnan(glucose)] < 70) * 100)
            new_hypo = float(np.nanmean(corrected[~np.isnan(corrected)] < 70) * 100)
            hypo_increase = new_hypo - baseline_hypo

            mag_results.append({
                'magnitude_pct': mag,
                'new_excursion': round(new_exc, 1),
                'excursion_reduction': round(exc_reduction, 1),
                'new_tir': round(new_tir, 1),
                'tir_change': round(tir_change, 1),
                'hypo_pct_change': round(hypo_increase, 2),
            })

        # Find optimal magnitude: best TIR without increasing hypo >1%
        optimal = None
        for mr in mag_results:
            if mr['hypo_pct_change'] <= 1.0:
                if optimal is None or mr['tir_change'] > optimal['tir_change']:
                    optimal = mr
        if optimal is None:
            optimal = mag_results[0]  # fallback to 10%

        rec = {
            'patient': pid,
            'baseline_excursion': round(baseline_exc, 1),
            'baseline_tir': round(baseline_tir, 1),
            'needs_cr_fix': True,
            'magnitude_results': mag_results,
            'optimal_magnitude': optimal['magnitude_pct'],
        }
        per_patient.append(rec)

        if args.detail:
            print(f"  {pid}: exc={baseline_exc:.0f} → "
                  f"opt_mag={optimal['magnitude_pct']}% "
                  f"(TIR {optimal['tir_change']:+.1f}%, exc↓{optimal['excursion_reduction']:.0f})")

    results['per_patient'] = per_patient
    results['n_patients'] = len(per_patient)

    needing_cr = [p for p in per_patient if p['needs_cr_fix']]
    results['n_needing_cr'] = len(needing_cr)

    # Aggregate optimal magnitude distribution
    opt_dist = defaultdict(int)
    for p in needing_cr:
        opt_dist[p['optimal_magnitude']] += 1
    results['optimal_magnitude_distribution'] = dict(opt_dist)

    # Compare to basal finding: is conservative also best for CR?
    conservative_best_cr = opt_dist.get(10, 0) >= opt_dist.get(20, 0) and \
                           opt_dist.get(10, 0) >= opt_dist.get(30, 0)
    results['conservative_best_for_cr'] = conservative_best_cr

    print(f"\n  Patients needing CR fix: {results['n_needing_cr']}/{results['n_patients']}")
    print(f"  Optimal magnitude distribution: {dict(opt_dist)}")
    print(f"  Conservative (10%) best for CR? {'YES' if conservative_best_cr else 'NO'} "
          f"(compare to basal where conservative was proven best)")
    return results


# ---------------------------------------------------------------------------
# EXP-1424: Patient f Instability Analysis
# ---------------------------------------------------------------------------
@register(1424, "Patient f Instability Analysis")
def exp_1424(patients, args):
    """Analyze why patient f has 15 grade changes in 25 weeks."""
    results = {'name': 'EXP-1424: Patient f Instability Analysis'}

    focus_patients = {'f': 'unstable'}
    comparison_patients = {}
    for pid in STABLE_PATIENTS:
        if pid in patients:
            comparison_patients[pid] = 'stable'

    all_analysis = {}

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs = pdata['carbs']
        temp_rate = pdata['temp_rate']
        n = len(glucose)
        n_days = n // STEPS_PER_DAY
        n_weeks = n // WEEKLY_STEPS

        if n_weeks < 4:
            continue

        # Weekly TIR, CV, score for this patient
        weekly_tirs = []
        weekly_scores = []
        weekly_grades = []
        weekly_bolus_counts = []
        weekly_carb_counts = []
        weekly_meal_times = []

        for w in range(n_weeks):
            ws = w * WEEKLY_STEPS
            we = ws + WEEKLY_STEPS
            if we > n:
                break
            g = glucose[ws:we]
            b = bolus[ws:we]
            c = carbs[ws:we]
            tr = temp_rate[ws:we]

            tir = compute_tir(g)
            weekly_tirs.append(tir)

            drifts = []
            for d in range(7):
                dr = compute_segment_drift(glucose, bolus, carbs, ws + d * STEPS_PER_DAY, 0, 6)
                if not np.isnan(dr):
                    drifts.append(abs(dr))
            drift = float(np.median(drifts)) if drifts else 0.0

            exc = compute_max_excursion(g, c, len(g))
            cv = compute_cv(g)
            score = compute_therapy_score(tir, drift, exc, 1.0, cv)
            grade = get_grade(score)
            weekly_scores.append(score)
            weekly_grades.append(grade)

            # Bolus count and carb events per week
            bolus_count = int(np.sum(b > 0.1))
            carb_events = int(np.sum(c > 5))
            weekly_bolus_counts.append(bolus_count)
            weekly_carb_counts.append(carb_events)

            # Mean meal time (hour of day) for carb events
            meal_hours = []
            for step in range(len(c)):
                if c[step] > 5:
                    hour = (step % STEPS_PER_DAY) / STEPS_PER_HOUR
                    meal_hours.append(hour)
            if meal_hours:
                weekly_meal_times.append(float(np.std(meal_hours)))
            else:
                weekly_meal_times.append(np.nan)

        # Grade change count
        grade_changes = sum(1 for i in range(1, len(weekly_grades)) if weekly_grades[i] != weekly_grades[i - 1])

        # TIR variance
        tir_std = float(np.std(weekly_tirs)) if weekly_tirs else 0.0
        tir_cv = float(np.std(weekly_tirs) / np.mean(weekly_tirs) * 100) if weekly_tirs and np.mean(weekly_tirs) > 0 else 0.0

        # Score variance
        score_std = float(np.std(weekly_scores)) if weekly_scores else 0.0

        # Bolus regularity
        bolus_count_cv = float(np.std(weekly_bolus_counts) / np.mean(weekly_bolus_counts) * 100) \
            if weekly_bolus_counts and np.mean(weekly_bolus_counts) > 0 else 0.0

        # Carb event regularity
        carb_count_cv = float(np.std(weekly_carb_counts) / np.mean(weekly_carb_counts) * 100) \
            if weekly_carb_counts and np.mean(weekly_carb_counts) > 0 else 0.0

        # Meal timing variance
        valid_meal_std = [v for v in weekly_meal_times if not np.isnan(v)]
        mean_meal_timing_std = float(np.mean(valid_meal_std)) if valid_meal_std else 0.0

        # Day-of-week effect: compare weekend vs weekday TIR
        weekday_tirs = []
        weekend_tirs = []
        for d in range(min(n_days, 180)):
            ds_start = d * STEPS_PER_DAY
            ds_end = ds_start + STEPS_PER_DAY
            if ds_end > n:
                break
            day_tir = compute_tir(glucose[ds_start:ds_end])
            if d % 7 < 5:
                weekday_tirs.append(day_tir)
            else:
                weekend_tirs.append(day_tir)
        weekday_mean = float(np.mean(weekday_tirs)) if weekday_tirs else 0.0
        weekend_mean = float(np.mean(weekend_tirs)) if weekend_tirs else 0.0
        day_of_week_effect = abs(weekday_mean - weekend_mean)

        # CGM coverage week-over-week
        weekly_coverage = []
        for w in range(n_weeks):
            ws = w * WEEKLY_STEPS
            we = ws + WEEKLY_STEPS
            if we > n:
                break
            g = glucose[ws:we]
            cov = float(np.mean(~np.isnan(g)) * 100)
            weekly_coverage.append(cov)
        coverage_cv = float(np.std(weekly_coverage) / np.mean(weekly_coverage) * 100) \
            if weekly_coverage and np.mean(weekly_coverage) > 0 else 0.0

        # Variance decomposition: rank sources
        sources = {
            'meal_timing_variance': mean_meal_timing_std,
            'bolus_count_variability': bolus_count_cv,
            'carb_event_variability': carb_count_cv,
            'cgm_coverage_variability': coverage_cv,
            'day_of_week_effect': day_of_week_effect,
        }
        ranked_sources = sorted(sources.items(), key=lambda x: x[1], reverse=True)

        analysis = {
            'patient': pid,
            'role': focus_patients.get(pid, comparison_patients.get(pid, 'other')),
            'n_weeks': len(weekly_tirs),
            'grade_changes': grade_changes,
            'tir_std': round(tir_std, 1),
            'tir_cv': round(tir_cv, 1),
            'score_std': round(score_std, 1),
            'bolus_count_cv': round(bolus_count_cv, 1),
            'carb_count_cv': round(carb_count_cv, 1),
            'mean_meal_timing_std': round(mean_meal_timing_std, 2),
            'day_of_week_effect': round(day_of_week_effect, 1),
            'coverage_cv': round(coverage_cv, 1),
            'instability_sources_ranked': ranked_sources,
            'weekly_grades': weekly_grades,
        }
        all_analysis[pid] = analysis

        if pid == 'f' or args.detail:
            print(f"  {pid} ({analysis['role']}): {grade_changes} grade changes, "
                  f"TIR_std={tir_std:.1f}, score_std={score_std:.1f}")
            if pid == 'f':
                print(f"    Top instability source: {ranked_sources[0][0]} "
                      f"({ranked_sources[0][1]:.1f})")

    results['all_patients'] = all_analysis
    results['n_patients'] = len(all_analysis)

    # Compare f to stable patients
    f_data = all_analysis.get('f')
    if f_data:
        comparison = {}
        for sp in STABLE_PATIENTS:
            if sp in all_analysis:
                stable = all_analysis[sp]
                comparison[sp] = {
                    'grade_changes_ratio': round(f_data['grade_changes'] / max(stable['grade_changes'], 1), 1),
                    'tir_std_ratio': round(f_data['tir_std'] / max(stable['tir_std'], 0.1), 1),
                    'score_std_ratio': round(f_data['score_std'] / max(stable['score_std'], 0.1), 1),
                }
        results['f_vs_stable'] = comparison
        results['f_dominant_source'] = f_data['instability_sources_ranked'][0] if f_data['instability_sources_ranked'] else None

        print(f"\n  Patient f dominant instability source: "
              f"{f_data['instability_sources_ranked'][0][0] if f_data['instability_sources_ranked'] else 'unknown'}")
        for sp, comp in comparison.items():
            print(f"  f vs {sp}: {comp['grade_changes_ratio']}x grade changes, "
                  f"{comp['tir_std_ratio']}x TIR variability")
    return results


# ---------------------------------------------------------------------------
# EXP-1425: Long-Term Recommendation Stability
# ---------------------------------------------------------------------------
@register(1425, "Long-Term Recommendation Stability")
def exp_1425(patients, args):
    """Split 180d into 3x60d, check recommendation consistency."""
    results = {'name': 'EXP-1425: Long-Term Recommendation Stability'}
    per_patient = []
    block_days = 60
    block_steps = block_days * STEPS_PER_DAY

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs = pdata['carbs']
        n = len(glucose)

        if n < 3 * block_steps:
            per_patient.append({
                'patient': pid, 'insufficient_data': True,
                'n_days': n // STEPS_PER_DAY,
            })
            continue

        profile = load_profile(pid)

        block_assessments = []
        block_recs = []
        for b in range(3):
            bs = b * block_steps
            be = bs + block_steps
            g_block = glucose[bs:be]
            b_block = bolus[bs:be]
            c_block = carbs[bs:be]
            assessment = compute_full_assessment(g_block, b_block, c_block, len(g_block))
            recs = generate_recommendations(assessment, profile, pid)
            block_assessments.append(assessment)
            block_recs.append(recs)

        # Compare recommendations across blocks
        # Extract parameter sets for each block
        param_sets = []
        for recs in block_recs:
            params = set()
            for r in recs:
                params.add((r['parameter'], r['direction']))
            param_sets.append(params)

        # Agreement: params present in ALL 3 blocks
        agreed = param_sets[0] & param_sets[1] & param_sets[2]
        # Present in any block
        all_params = param_sets[0] | param_sets[1] | param_sets[2]
        # Unstable: present in some but not all
        unstable = all_params - agreed

        # For unstable recommendations, check if magnitude or direction changes
        unstable_details = []
        for param, direction in unstable:
            presence = []
            magnitudes = []
            for b_idx, recs in enumerate(block_recs):
                match = [r for r in recs if r['parameter'] == param]
                if match:
                    presence.append(b_idx)
                    magnitudes.append(match[0]['magnitude'])
            if len(set(r['direction'] for recs in block_recs for r in recs if r['parameter'] == param)) > 1:
                change_type = 'direction'
            else:
                change_type = 'magnitude'
            unstable_details.append({
                'parameter': param,
                'direction': direction,
                'change_type': change_type,
                'present_in_blocks': presence,
                'magnitudes': [round(m, 1) for m in magnitudes],
            })

        stability_score = len(agreed) / max(len(all_params), 1) * 100

        rec = {
            'patient': pid,
            'block_assessments': block_assessments,
            'n_agreed': len(agreed),
            'n_unstable': len(unstable),
            'n_total': len(all_params),
            'agreed_recommendations': [{'parameter': p, 'direction': d} for p, d in agreed],
            'unstable_recommendations': unstable_details,
            'stability_score': round(stability_score, 1),
            'grade_trajectory': [a['grade'] for a in block_assessments],
        }
        per_patient.append(rec)

        if args.detail:
            print(f"  {pid}: stability={stability_score:.0f}% | "
                  f"agreed={len(agreed)}, unstable={len(unstable)} | "
                  f"grades={' -> '.join(a['grade'] for a in block_assessments)}")

    results['per_patient'] = per_patient
    results['n_patients'] = len(per_patient)

    valid = [p for p in per_patient if not p.get('insufficient_data')]
    if valid:
        mean_stability = float(np.mean([p['stability_score'] for p in valid]))
        high_stability = sum(1 for p in valid if p['stability_score'] >= 80)
        low_stability = sum(1 for p in valid if p['stability_score'] < 50)
    else:
        mean_stability = 0.0
        high_stability = 0
        low_stability = 0

    results['mean_stability_score'] = round(mean_stability, 1)
    results['n_high_stability'] = high_stability
    results['n_low_stability'] = low_stability

    print(f"\n  Mean stability score: {mean_stability:.1f}%")
    print(f"  High stability (>=80%): {high_stability}, Low (<50%): {low_stability}")
    return results


# ---------------------------------------------------------------------------
# EXP-1426: Insulin Delivery Pattern Classification
# ---------------------------------------------------------------------------
@register(1426, "Insulin Delivery Pattern Classification")
def exp_1426(patients, args):
    """Classify insulin delivery patterns and correlate with therapy grade."""
    results = {'name': 'EXP-1426: Insulin Delivery Pattern Classification'}
    per_patient = []

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs = pdata['carbs']
        temp_rate = pdata['temp_rate']
        iob = pdata['iob']
        n = len(glucose)
        n_days = n // STEPS_PER_DAY

        if n_days < 7:
            continue

        # Total daily dose (TDD)
        daily_bolus_totals = []
        daily_basal_totals = []
        daily_bolus_counts = []
        daily_correction_pcts = []

        for d in range(min(n_days, 180)):
            ds = d * STEPS_PER_DAY
            de = ds + STEPS_PER_DAY
            if de > n:
                break

            day_bolus = bolus[ds:de]
            day_carbs = carbs[ds:de]
            day_tr = temp_rate[ds:de]

            # Bolus total
            total_bolus = float(np.nansum(day_bolus))
            daily_bolus_totals.append(total_bolus)

            # Basal total (temp_rate in U/h, 5-min intervals -> U/h / 12 per step)
            valid_tr = day_tr[~np.isnan(day_tr)]
            if len(valid_tr) > 0:
                total_basal = float(np.sum(valid_tr) / STEPS_PER_HOUR)
            else:
                total_basal = 0.0
            daily_basal_totals.append(total_basal)

            # Bolus count
            bolus_events = int(np.sum(day_bolus > 0.1))
            daily_bolus_counts.append(bolus_events)

            # Correction bolus %: bolus without associated carbs
            correction_count = 0
            for step in range(STEPS_PER_DAY):
                if day_bolus[step] > 0.1:
                    # Check if carbs within +-30min
                    c_start = max(0, step - STEPS_PER_HOUR // 2)
                    c_end = min(STEPS_PER_DAY, step + STEPS_PER_HOUR // 2)
                    if np.nansum(day_carbs[c_start:c_end]) < 3:
                        correction_count += 1
            if bolus_events > 0:
                daily_correction_pcts.append(correction_count / bolus_events * 100)
            else:
                daily_correction_pcts.append(0.0)

        mean_tdd = float(np.mean(daily_bolus_totals)) + float(np.mean(daily_basal_totals))
        mean_basal_total = float(np.mean(daily_basal_totals))
        mean_bolus_total = float(np.mean(daily_bolus_totals))
        basal_fraction = mean_basal_total / max(mean_tdd, 0.01)
        mean_bolus_count = float(np.mean(daily_bolus_counts))
        mean_correction_pct = float(np.mean(daily_correction_pcts))

        # Therapy assessment
        assessment = compute_full_assessment(glucose, bolus, carbs, n)

        # Classify delivery pattern
        if basal_fraction > 0.65:
            pattern = 'basal_dominant'
        elif basal_fraction < 0.35:
            pattern = 'bolus_dominant'
        else:
            pattern = 'balanced'

        if mean_correction_pct > 40:
            pattern += '+correction_heavy'

        rec = {
            'patient': pid,
            'mean_tdd': round(mean_tdd, 1),
            'mean_basal_total': round(mean_basal_total, 1),
            'mean_bolus_total': round(mean_bolus_total, 1),
            'basal_fraction': round(basal_fraction, 3),
            'mean_bolus_count_per_day': round(mean_bolus_count, 1),
            'mean_correction_pct': round(mean_correction_pct, 1),
            'delivery_pattern': pattern,
            'grade': assessment['grade'],
            'score': assessment['score'],
            'tir': assessment['tir'],
        }
        per_patient.append(rec)

        if args.detail:
            print(f"  {pid}: TDD={mean_tdd:.1f}U, basal_frac={basal_fraction:.2f}, "
                  f"bolus/d={mean_bolus_count:.1f}, corr%={mean_correction_pct:.0f}% → "
                  f"{pattern} | grade={assessment['grade']}")

    results['per_patient'] = per_patient
    results['n_patients'] = len(per_patient)

    # Cluster summary
    pattern_grades = defaultdict(list)
    pattern_tirs = defaultdict(list)
    for p in per_patient:
        pattern_grades[p['delivery_pattern']].append(p['grade'])
        pattern_tirs[p['delivery_pattern']].append(p['tir'])

    cluster_summary = {}
    for pattern, grades in pattern_grades.items():
        grade_dist = defaultdict(int)
        for g in grades:
            grade_dist[g] += 1
        cluster_summary[pattern] = {
            'count': len(grades),
            'grade_distribution': dict(grade_dist),
            'mean_tir': round(float(np.mean(pattern_tirs[pattern])), 1),
        }
    results['cluster_summary'] = cluster_summary

    # Correlation: does basal fraction predict grade?
    if len(per_patient) > 3:
        grade_map = {'A': 4, 'B': 3, 'C': 2, 'D': 1}
        basal_fracs = [p['basal_fraction'] for p in per_patient]
        grade_nums = [grade_map.get(p['grade'], 2) for p in per_patient]
        if np.std(basal_fracs) > 0 and np.std(grade_nums) > 0:
            corr = float(np.corrcoef(basal_fracs, grade_nums)[0, 1])
        else:
            corr = 0.0
        results['basal_fraction_grade_correlation'] = round(corr, 3)
    else:
        results['basal_fraction_grade_correlation'] = None

    print(f"\n  Delivery pattern clusters: {dict({k: v['count'] for k, v in cluster_summary.items()})}")
    if results['basal_fraction_grade_correlation'] is not None:
        print(f"  Basal fraction ↔ grade correlation: r={results['basal_fraction_grade_correlation']:.3f}")
    return results


# ---------------------------------------------------------------------------
# EXP-1427: Meal Timing Regularity Score
# ---------------------------------------------------------------------------
@register(1427, "Meal Timing Regularity Score")
def exp_1427(patients, args):
    """Analyze meal timing regularity and correlate with outcomes."""
    results = {'name': 'EXP-1427: Meal Timing Regularity Score'}
    per_patient = []

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs = pdata['carbs']
        n = len(glucose)
        n_days = n // STEPS_PER_DAY

        if n_days < 7:
            continue

        # Extract meal events: carbs > 5g
        daily_meal_counts = []
        daily_meal_hours = []
        daily_carb_amounts = []

        for d in range(min(n_days, 180)):
            ds = d * STEPS_PER_DAY
            de = ds + STEPS_PER_DAY
            if de > n:
                break
            day_carbs = carbs[ds:de]
            meals_today = []
            carbs_today = []

            step = 0
            while step < STEPS_PER_DAY:
                if day_carbs[step] > 5:
                    hour = step / STEPS_PER_HOUR
                    meals_today.append(hour)
                    carbs_today.append(float(day_carbs[step]))
                    # Skip ahead 30min to avoid double-counting same meal
                    step += STEPS_PER_HOUR // 2
                else:
                    step += 1

            daily_meal_counts.append(len(meals_today))
            daily_meal_hours.extend(meals_today)
            daily_carb_amounts.extend(carbs_today)

        if not daily_meal_hours:
            per_patient.append({
                'patient': pid, 'no_meals': True,
                'meals_per_day': 0.0,
            })
            continue

        meals_per_day = float(np.mean(daily_meal_counts))
        meal_count_std = float(np.std(daily_meal_counts))

        # Group meals by approximate time slot
        # Breakfast (5-10), Lunch (10-15), Dinner (15-21), Snack (other)
        slots = {'breakfast': [], 'lunch': [], 'dinner': [], 'snack': []}
        for h in daily_meal_hours:
            if 5 <= h < 10:
                slots['breakfast'].append(h)
            elif 10 <= h < 15:
                slots['lunch'].append(h)
            elif 15 <= h < 21:
                slots['dinner'].append(h)
            else:
                slots['snack'].append(h)

        slot_timing_std = {}
        for slot_name, hours in slots.items():
            if len(hours) >= 3:
                slot_timing_std[slot_name] = round(float(np.std(hours)), 2)
            else:
                slot_timing_std[slot_name] = None

        # Overall meal timing std
        meal_timing_std = float(np.std(daily_meal_hours)) if daily_meal_hours else 0.0

        # Carb amount CV
        carb_cv = float(np.std(daily_carb_amounts) / np.mean(daily_carb_amounts) * 100) \
            if daily_carb_amounts and np.mean(daily_carb_amounts) > 0 else 0.0

        # Regularity score: 100 = perfectly regular, 0 = chaotic
        # Based on: consistent meal count, consistent timing, consistent carbs
        count_score = max(0, 100 - meal_count_std * 30)
        timing_score = max(0, 100 - meal_timing_std * 10)
        carb_score = max(0, 100 - carb_cv)
        regularity_score = (count_score + timing_score + carb_score) / 3

        # Therapy assessment for correlation
        assessment = compute_full_assessment(glucose, bolus, carbs, n)

        rec = {
            'patient': pid,
            'no_meals': False,
            'meals_per_day': round(meals_per_day, 1),
            'meal_count_std': round(meal_count_std, 2),
            'meal_timing_std_hours': round(meal_timing_std, 2),
            'carb_amount_cv': round(carb_cv, 1),
            'slot_timing_std': slot_timing_std,
            'regularity_score': round(regularity_score, 1),
            'tir': assessment['tir'],
            'grade': assessment['grade'],
            'excursion': assessment['excursion'],
        }
        per_patient.append(rec)

        if args.detail:
            print(f"  {pid}: meals/d={meals_per_day:.1f}, timing_std={meal_timing_std:.1f}h, "
                  f"carb_cv={carb_cv:.0f}%, regularity={regularity_score:.0f} | "
                  f"TIR={assessment['tir']:.0f}%")

    results['per_patient'] = per_patient
    results['n_patients'] = len(per_patient)

    # Correlations
    valid = [p for p in per_patient if not p.get('no_meals')]
    if len(valid) > 3:
        reg_scores = [p['regularity_score'] for p in valid]
        tirs = [p['tir'] for p in valid]
        excursions = [p['excursion'] for p in valid]

        if np.std(reg_scores) > 0 and np.std(tirs) > 0:
            corr_tir = float(np.corrcoef(reg_scores, tirs)[0, 1])
        else:
            corr_tir = 0.0
        if np.std(reg_scores) > 0 and np.std(excursions) > 0:
            corr_exc = float(np.corrcoef(reg_scores, excursions)[0, 1])
        else:
            corr_exc = 0.0

        results['regularity_tir_correlation'] = round(corr_tir, 3)
        results['regularity_excursion_correlation'] = round(corr_exc, 3)
    else:
        results['regularity_tir_correlation'] = None
        results['regularity_excursion_correlation'] = None

    labels = [f"{p['patient']}={p['regularity_score']:.0f}" for p in valid[:6]]
    print(f"\n  Regularity scores: {', '.join(labels)}")
    if results['regularity_tir_correlation'] is not None:
        print(f"  Regularity ↔ TIR: r={results['regularity_tir_correlation']:.3f}")
        print(f"  Regularity ↔ excursion: r={results['regularity_excursion_correlation']:.3f}")
    return results


# ---------------------------------------------------------------------------
# EXP-1428: Overnight vs Daytime Therapy Quality
# ---------------------------------------------------------------------------
@register(1428, "Overnight vs Daytime Therapy Quality")
def exp_1428(patients, args):
    """Split TIR and grades into overnight (22-06) and daytime (06-22)."""
    results = {'name': 'EXP-1428: Overnight vs Daytime Therapy Quality'}
    per_patient = []

    overnight_hours = [(22, 24), (0, 6)]  # 22:00-06:00
    daytime_hours = [(6, 22)]              # 06:00-22:00

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs = pdata['carbs']
        n = len(glucose)
        n_days = n // STEPS_PER_DAY

        if n_days < 7:
            continue

        overnight_glucose = []
        daytime_glucose = []
        overnight_drifts = []
        daytime_excursions = []

        for d in range(min(n_days, 180)):
            ds = d * STEPS_PER_DAY

            # Overnight: 22:00-24:00 + next day 00:00-06:00
            for h_start, h_end in overnight_hours:
                seg_start = ds + h_start * STEPS_PER_HOUR
                seg_end = ds + h_end * STEPS_PER_HOUR
                if seg_end > n:
                    continue
                seg = glucose[seg_start:seg_end]
                overnight_glucose.extend(seg[~np.isnan(seg)].tolist())

            # Daytime: 06:00-22:00
            for h_start, h_end in daytime_hours:
                seg_start = ds + h_start * STEPS_PER_HOUR
                seg_end = ds + h_end * STEPS_PER_HOUR
                if seg_end > n:
                    continue
                seg = glucose[seg_start:seg_end]
                daytime_glucose.extend(seg[~np.isnan(seg)].tolist())

            # Overnight drift (0-6)
            dr = compute_segment_drift(glucose, bolus, carbs, ds, 0, 6)
            if not np.isnan(dr):
                overnight_drifts.append(abs(dr))

        overnight_g = np.array(overnight_glucose) if overnight_glucose else np.array([])
        daytime_g = np.array(daytime_glucose) if daytime_glucose else np.array([])

        overnight_tir = compute_tir(overnight_g) if len(overnight_g) > 100 else np.nan
        daytime_tir = compute_tir(daytime_g) if len(daytime_g) > 100 else np.nan
        overnight_cv = compute_cv(overnight_g) if len(overnight_g) > 100 else np.nan
        daytime_cv = compute_cv(daytime_g) if len(daytime_g) > 100 else np.nan

        overnight_mean = float(np.mean(overnight_g)) if len(overnight_g) > 0 else np.nan
        daytime_mean = float(np.mean(daytime_g)) if len(daytime_g) > 0 else np.nan

        # Daytime excursion from full data
        daytime_exc = compute_max_excursion(glucose, carbs, n)

        overnight_drift = float(np.median(overnight_drifts)) if overnight_drifts else 0.0

        # Determine issue pattern
        if not np.isnan(overnight_tir) and not np.isnan(daytime_tir):
            tir_diff = daytime_tir - overnight_tir
            if abs(tir_diff) < 5:
                issue_pattern = 'uniform'
            elif tir_diff > 5:
                issue_pattern = 'overnight_worse'
            else:
                issue_pattern = 'daytime_worse'
        else:
            issue_pattern = 'unknown'

        # Recommendation focus based on pattern
        if issue_pattern == 'overnight_worse':
            rec_focus = 'basal'
            rec_detail = 'Overnight TIR significantly lower — basal adjustment primary'
        elif issue_pattern == 'daytime_worse':
            rec_focus = 'cr_isf'
            rec_detail = 'Daytime TIR significantly lower — CR/ISF adjustment primary'
        else:
            rec_focus = 'both'
            rec_detail = 'Uniform issue — consider all parameters'

        rec = {
            'patient': pid,
            'overnight_tir': round(overnight_tir, 1) if not np.isnan(overnight_tir) else None,
            'daytime_tir': round(daytime_tir, 1) if not np.isnan(daytime_tir) else None,
            'overnight_cv': round(overnight_cv, 1) if not np.isnan(overnight_cv) else None,
            'daytime_cv': round(daytime_cv, 1) if not np.isnan(daytime_cv) else None,
            'overnight_mean_mg_dl': round(overnight_mean, 1) if not np.isnan(overnight_mean) else None,
            'daytime_mean_mg_dl': round(daytime_mean, 1) if not np.isnan(daytime_mean) else None,
            'overnight_drift': round(overnight_drift, 2),
            'daytime_excursion': round(daytime_exc, 1),
            'issue_pattern': issue_pattern,
            'recommendation_focus': rec_focus,
            'recommendation_detail': rec_detail,
        }
        per_patient.append(rec)

        if args.detail:
            o_tir = f"{overnight_tir:.0f}" if not np.isnan(overnight_tir) else '?'
            d_tir = f"{daytime_tir:.0f}" if not np.isnan(daytime_tir) else '?'
            print(f"  {pid}: overnight={o_tir}% daytime={d_tir}% → {issue_pattern} → focus: {rec_focus}")

    results['per_patient'] = per_patient
    results['n_patients'] = len(per_patient)

    # Pattern distribution
    pattern_dist = defaultdict(int)
    focus_dist = defaultdict(int)
    for p in per_patient:
        pattern_dist[p['issue_pattern']] += 1
        focus_dist[p['recommendation_focus']] += 1
    results['issue_pattern_distribution'] = dict(pattern_dist)
    results['recommendation_focus_distribution'] = dict(focus_dist)

    print(f"\n  Issue patterns: {dict(pattern_dist)}")
    print(f"  Recommendation focus: {dict(focus_dist)}")
    return results


# ---------------------------------------------------------------------------
# EXP-1429: Time-to-Action Analysis
# ---------------------------------------------------------------------------
@register(1429, "Time-to-Action Analysis")
def exp_1429(patients, args):
    """Determine minimum data needed to flag therapy issues at >80% confidence."""
    results = {'name': 'EXP-1429: Time-to-Action Analysis'}
    per_patient = []

    # Test data windows from 7 days to 120 days
    test_windows_days = [7, 14, 21, 30, 45, 60, 90, 120]

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs = pdata['carbs']
        n = len(glucose)
        n_days = n // STEPS_PER_DAY

        if n_days < 120:
            per_patient.append({
                'patient': pid, 'insufficient_data': True,
                'n_days': n_days,
            })
            continue

        # Ground truth: full data assessment
        full_assessment = compute_full_assessment(glucose, bolus, carbs, n)
        full_flags = full_assessment['flags']

        # For each window size, compute assessment and check agreement with ground truth
        window_results = []
        per_param_latency = {'basal': None, 'cr': None, 'cv': None}

        for w_days in test_windows_days:
            w_steps = w_days * STEPS_PER_DAY
            if w_steps > n:
                break

            # Use multiple sliding windows to estimate confidence
            n_trials = max(1, (n_days - w_days) // 7)  # every 7-day offset
            n_trials = min(n_trials, 15)  # cap at 15

            param_agreements = {'basal': 0, 'cr': 0, 'cv': 0}
            n_valid_trials = 0

            for trial in range(n_trials):
                offset = trial * 7 * STEPS_PER_DAY
                start = offset
                end = start + w_steps
                if end > n:
                    break

                g_win = glucose[start:end]
                b_win = bolus[start:end]
                c_win = carbs[start:end]
                win_assessment = compute_full_assessment(g_win, b_win, c_win, len(g_win))
                win_flags = win_assessment['flags']
                n_valid_trials += 1

                for param in ['basal', 'cr', 'cv']:
                    flag_key = f'{param}_flag'
                    if win_flags[flag_key] == full_flags[flag_key]:
                        param_agreements[param] += 1

            if n_valid_trials == 0:
                continue

            param_confidence = {}
            for param in ['basal', 'cr', 'cv']:
                conf = param_agreements[param] / n_valid_trials * 100
                param_confidence[param] = round(conf, 1)
                # Track first window to reach 80% confidence
                if per_param_latency[param] is None and conf >= 80:
                    per_param_latency[param] = w_days

            overall_conf = float(np.mean(list(param_confidence.values())))
            window_results.append({
                'window_days': w_days,
                'n_trials': n_valid_trials,
                'param_confidence': param_confidence,
                'overall_confidence': round(overall_conf, 1),
            })

        rec = {
            'patient': pid,
            'ground_truth_flags': {k: v for k, v in full_flags.items()},
            'ground_truth_grade': full_assessment['grade'],
            'window_results': window_results,
            'detection_latency_days': {k: v for k, v in per_param_latency.items()},
        }
        per_patient.append(rec)

        if args.detail:
            latencies = ', '.join(f'{k}={v}d' if v else f'{k}=N/A' for k, v in per_param_latency.items())
            print(f"  {pid}: detection latency: {latencies}")

    results['per_patient'] = per_patient
    results['n_patients'] = len(per_patient)

    # Aggregate latency statistics
    valid_results = [p for p in per_patient if not p.get('insufficient_data')]
    latency_summary = {}
    for param in ['basal', 'cr', 'cv']:
        latencies = [p['detection_latency_days'][param] for p in valid_results
                     if p['detection_latency_days'].get(param) is not None]
        if latencies:
            latency_summary[param] = {
                'min_days': min(latencies),
                'median_days': int(np.median(latencies)),
                'max_days': max(latencies),
                'n_detected': len(latencies),
                'n_total': len(valid_results),
            }
        else:
            latency_summary[param] = {'n_detected': 0, 'n_total': len(valid_results)}
    results['latency_summary'] = latency_summary

    # Can we detect basal issues faster than CR?
    basal_latencies = [p['detection_latency_days']['basal'] for p in valid_results
                       if p['detection_latency_days'].get('basal') is not None]
    cr_latencies = [p['detection_latency_days']['cr'] for p in valid_results
                    if p['detection_latency_days'].get('cr') is not None]
    if basal_latencies and cr_latencies:
        basal_faster = float(np.median(basal_latencies)) < float(np.median(cr_latencies))
    else:
        basal_faster = None
    results['basal_detects_faster_than_cr'] = basal_faster

    print(f"\n  Detection latency summary:")
    for param, summary in latency_summary.items():
        if summary.get('median_days'):
            print(f"    {param}: median={summary['median_days']}d (range {summary['min_days']}-{summary['max_days']}d, "
                  f"{summary['n_detected']}/{summary['n_total']} patients)")
        else:
            print(f"    {param}: not enough detections ({summary['n_detected']}/{summary['n_total']})")
    if basal_faster is not None:
        print(f"  Basal detects faster than CR? {'YES' if basal_faster else 'NO'}")
    return results


# ---------------------------------------------------------------------------
# EXP-1430: Therapy Outcome Prediction
# ---------------------------------------------------------------------------
@register(1430, "Therapy Outcome Prediction")
def exp_1430(patients, args):
    """Predict future grade from current parameters using first 120d → predict 121-180d."""
    results = {'name': 'EXP-1430: Therapy Outcome Prediction'}
    per_patient = []

    train_days = 120
    train_steps = train_days * STEPS_PER_DAY
    test_days = 60
    test_steps = test_days * STEPS_PER_DAY

    features_list = []
    targets_list = []
    patient_ids = []

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs = pdata['carbs']
        temp_rate = pdata['temp_rate']
        n = len(glucose)

        if n < train_steps + test_steps:
            per_patient.append({
                'patient': pid, 'insufficient_data': True,
                'n_days': n // STEPS_PER_DAY,
            })
            continue

        # Train assessment (first 120 days)
        g_train = glucose[:train_steps]
        b_train = bolus[:train_steps]
        c_train = carbs[:train_steps]
        train_assessment = compute_full_assessment(g_train, b_train, c_train, train_steps)
        train_recs = generate_recommendations(train_assessment, load_profile(pid), pid)

        # Test assessment (days 121-180)
        g_test = glucose[train_steps:train_steps + test_steps]
        b_test = bolus[train_steps:train_steps + test_steps]
        c_test = carbs[train_steps:train_steps + test_steps]
        test_assessment = compute_full_assessment(g_test, b_test, c_test, test_steps)

        # Features from training period
        tr_train = temp_rate[:train_steps]
        valid_tr = tr_train[~np.isnan(tr_train)]
        mean_temp_rate = float(np.mean(valid_tr)) if len(valid_tr) > 0 else 0.0

        # Trend in training period: compare first half vs second half
        half = train_steps // 2
        first_half_tir = compute_tir(g_train[:half])
        second_half_tir = compute_tir(g_train[half:])
        tir_trend = second_half_tir - first_half_tir

        # Number of recommendations
        n_recs = len(train_recs)
        has_basal_rec = any(r['parameter'] == 'basal' for r in train_recs)
        has_cr_rec = any(r['parameter'] == 'cr' for r in train_recs)

        features = {
            'tir': train_assessment['tir'],
            'drift': train_assessment['drift'],
            'excursion': train_assessment['excursion'],
            'cv': train_assessment['cv'],
            'score': train_assessment['score'],
            'mean_temp_rate': round(mean_temp_rate, 3),
            'tir_trend': round(tir_trend, 1),
            'n_recommendations': n_recs,
            'has_basal_rec': has_basal_rec,
            'has_cr_rec': has_cr_rec,
        }

        grade_map = {'A': 4, 'B': 3, 'C': 2, 'D': 1}
        train_grade_num = grade_map.get(train_assessment['grade'], 2)
        test_grade_num = grade_map.get(test_assessment['grade'], 2)
        grade_predicted_correctly = (train_assessment['grade'] == test_assessment['grade'])
        grade_change = test_grade_num - train_grade_num

        rec = {
            'patient': pid,
            'train_assessment': train_assessment,
            'test_assessment': test_assessment,
            'features': features,
            'train_grade': train_assessment['grade'],
            'test_grade': test_assessment['grade'],
            'grade_predicted_correctly': grade_predicted_correctly,
            'grade_change': grade_change,
            'n_recommendations': n_recs,
        }
        per_patient.append(rec)

        # Collect for correlation
        feat_vec = [
            features['tir'], features['drift'], features['excursion'],
            features['cv'], features['score'], features['tir_trend'],
            features['n_recommendations'],
        ]
        features_list.append(feat_vec)
        targets_list.append(test_grade_num)
        patient_ids.append(pid)

        if args.detail:
            print(f"  {pid}: train={train_assessment['grade']}({train_assessment['score']:.0f}) → "
                  f"test={test_assessment['grade']}({test_assessment['score']:.0f}) | "
                  f"correct={'✓' if grade_predicted_correctly else '✗'} | "
                  f"trend={tir_trend:+.1f}% | n_recs={n_recs}")

    results['per_patient'] = per_patient
    results['n_patients'] = len(per_patient)

    # Prediction accuracy: how often does train grade == test grade?
    valid = [p for p in per_patient if not p.get('insufficient_data')]
    if valid:
        n_correct = sum(1 for p in valid if p['grade_predicted_correctly'])
        accuracy = n_correct / len(valid) * 100
        results['grade_persistence_accuracy'] = round(accuracy, 1)
        results['n_correct'] = n_correct
        results['n_valid'] = len(valid)
    else:
        results['grade_persistence_accuracy'] = None

    # Feature correlations with future grade
    feature_names = ['tir', 'drift', 'excursion', 'cv', 'score', 'tir_trend', 'n_recs']
    if len(features_list) >= 4:
        feat_arr = np.array(features_list)
        tgt_arr = np.array(targets_list)
        feature_correlations = {}
        for i, fname in enumerate(feature_names):
            if np.std(feat_arr[:, i]) > 0 and np.std(tgt_arr) > 0:
                corr = float(np.corrcoef(feat_arr[:, i], tgt_arr)[0, 1])
            else:
                corr = 0.0
            feature_correlations[fname] = round(corr, 3)

        # Rank features by absolute correlation
        ranked = sorted(feature_correlations.items(), key=lambda x: abs(x[1]), reverse=True)
        results['feature_correlations'] = feature_correlations
        results['top_predictive_features'] = [{'feature': f, 'correlation': c} for f, c in ranked[:3]]
    else:
        results['feature_correlations'] = None
        results['top_predictive_features'] = None

    # Recommendation-outcome correlation:
    # Do patients with more recommendations tend to have worse future grades?
    if len(valid) >= 4:
        n_recs_arr = np.array([p['n_recommendations'] for p in valid])
        grade_change_arr = np.array([p['grade_change'] for p in valid])
        if np.std(n_recs_arr) > 0 and np.std(grade_change_arr) > 0:
            rec_outcome_corr = float(np.corrcoef(n_recs_arr, grade_change_arr)[0, 1])
        else:
            rec_outcome_corr = 0.0
        results['recommendation_outcome_correlation'] = round(rec_outcome_corr, 3)
    else:
        results['recommendation_outcome_correlation'] = None

    if results.get('grade_persistence_accuracy') is not None:
        print(f"\n  Grade persistence accuracy: {results['grade_persistence_accuracy']:.1f}% "
              f"({results['n_correct']}/{results['n_valid']} correct)")
    if results.get('top_predictive_features'):
        print(f"  Top predictive features:")
        for f in results['top_predictive_features']:
            print(f"    {f['feature']}: r={f['correlation']:.3f}")
    if results.get('recommendation_outcome_correlation') is not None:
        print(f"  Recommendation ↔ grade change: r={results['recommendation_outcome_correlation']:.3f}")
    return results


# ---------------------------------------------------------------------------
# Main CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description='EXP-1421 to EXP-1430: Multi-param intervention & long-term stability')
    parser.add_argument('--detail', action='store_true', help='Show detailed per-patient output')
    parser.add_argument('--save', action='store_true', help='Save results to JSON')
    parser.add_argument('--max-patients', type=int, default=11, help='Max patients to load')
    parser.add_argument('--exp', type=int, nargs='*', help='Run specific experiment IDs')
    args = parser.parse_args()

    print(f"Loading patient data from {PATIENTS_DIR} ...")
    patients = load_patients(max_patients=args.max_patients)
    print(f"Loaded {len(patients)} patients: {sorted(patients.keys())}")

    if not patients:
        print("ERROR: No patient data found. Run 'make bootstrap' first.")
        sys.exit(1)

    # Precondition assessment
    print(f"\n{'='*60}")
    print("PRECONDITION ASSESSMENT")
    print(f"{'='*60}")
    for pid, pdata in sorted(patients.items()):
        g = pdata['glucose']
        valid_pct = np.mean(~np.isnan(g)) * 100
        n_days = len(g) // STEPS_PER_DAY
        tags = []
        if pid in DAWN_PATIENTS:
            tags.append('DAWN')
        if pid in GRADE_D_PATIENTS:
            tags.append('GRADE-D')
        if pid in STABLE_PATIENTS:
            tags.append('STABLE')
        if pid == 'f':
            tags.append('UNSTABLE')
        tag_str = f" [{', '.join(tags)}]" if tags else ''
        print(f"  {pid}: {n_days}d, CGM coverage={valid_pct:.1f}%{tag_str}")

    to_run = args.exp if args.exp else sorted(EXPERIMENTS.keys())
    all_results = {}

    for exp_id in to_run:
        if exp_id not in EXPERIMENTS:
            print(f"\nWARNING: EXP-{exp_id} not registered, skipping")
            continue

        title, fn = EXPERIMENTS[exp_id]
        print(f"\n{'='*60}")
        print(f"EXP-{exp_id}: {title}")
        print(f"{'='*60}")

        t0 = time.time()
        try:
            result = fn(patients, args)
            elapsed = time.time() - t0
            result['elapsed_sec'] = round(elapsed, 1)
            all_results[exp_id] = result
            print(f"  Completed in {elapsed:.1f}s")

            if args.save:
                outdir = os.path.join(os.path.dirname(__file__), '..', '..', 'externals', 'experiments')
                os.makedirs(outdir, exist_ok=True)
                outpath = os.path.join(outdir, f'exp-{exp_id}_therapy.json')
                with open(outpath, 'w') as f:
                    json.dump(result, f, indent=2, default=str)
                print(f"  Saved to {outpath}")
        except Exception as e:
            elapsed = time.time() - t0
            print(f"  FAILED in {elapsed:.1f}s: {e}")
            traceback.print_exc()

    # Final summary
    print(f"\n{'='*60}")
    print("BATCH SUMMARY")
    print(f"{'='*60}")
    for exp_id in to_run:
        if exp_id in all_results:
            r = all_results[exp_id]
            print(f"  EXP-{exp_id}: OK ({r.get('elapsed_sec', '?')}s, {r.get('n_patients', '?')} patients)")
        elif exp_id in EXPERIMENTS:
            print(f"  EXP-{exp_id}: FAILED")


if __name__ == '__main__':
    main()
