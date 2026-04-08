#!/usr/bin/env python3
"""EXP-1431 to EXP-1440: Mixed-magnitude intervention, correction analysis & grade D protocols."""

import argparse
import json
import numpy as np
import os
import sys
import time
import traceback
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from cgmencode.exp_metabolic_flux import load_patients as _load_patients

PATIENTS_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'externals', 'ns-data', 'patients')

STEPS_PER_HOUR = 12
STEPS_PER_DAY = 24 * STEPS_PER_HOUR  # 288
WEEKLY_STEPS = 7 * STEPS_PER_DAY

SEGMENT_NAMES = ['midnight(0-6)', 'morning(6-12)', 'afternoon(12-18)', 'evening(18-24)']
SEGMENT_HOURS = [(0, 6), (6, 12), (12, 18), (18, 24)]

GRADE_D_PATIENTS = {'a', 'c', 'i'}

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
    """Compute glucose drift (mg/dL/h) for a segment on a given day."""
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
    """Compute full therapy assessment."""
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


def simulate_basal_correction(glucose, drift, isf, magnitude_pct=10):
    """Simulate basal correction on glucose trace."""
    corrected = glucose.copy()
    n = len(corrected)
    n_days = n // STEPS_PER_DAY
    correction_factor = magnitude_pct / 100.0
    for d in range(n_days):
        seg_start = d * STEPS_PER_DAY + 0 * STEPS_PER_HOUR
        seg_end = d * STEPS_PER_DAY + 6 * STEPS_PER_HOUR
        if seg_end > n:
            break
        seg_len = seg_end - seg_start
        correction_per_step = drift * correction_factor / STEPS_PER_HOUR
        for s in range(seg_len):
            idx = seg_start + s
            if not np.isnan(corrected[idx]):
                corrected[idx] -= correction_per_step * s
    return corrected


def simulate_cr_correction(glucose, carbs, magnitude_pct=10):
    """Simulate CR correction on glucose trace."""
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
    """Simulate ISF correction on post-correction glucose."""
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


def get_profile_isf(profile):
    """Extract ISF in mg/dL from profile."""
    if not profile:
        return 50.0
    sens = profile.get('sens', profile.get('isfProfile', []))
    units = profile.get('_units', 'mg/dL')
    if not sens:
        return 50.0
    isf = float(sens[0].get('value', 50.0))
    if units == 'mmol/L' or (isinstance(isf, (int, float)) and isf < 10):
        isf *= 18.0182
    return isf


def get_profile_cr(profile):
    """Extract carb ratio from profile."""
    if not profile:
        return 10.0
    cr_schedule = profile.get('carbratio', [])
    if not cr_schedule:
        return 10.0
    return float(cr_schedule[0].get('value', 10.0))


# ---------------------------------------------------------------------------
# EXP-1431: Mixed-Magnitude Sequential Intervention
# ---------------------------------------------------------------------------
@register(1431, "Mixed-Magnitude Sequential Intervention")
def exp_1431(patients, args):
    """Re-run sequential intervention with proper magnitudes: basal@10%, CR@30%, ISF@10%."""
    results = {'name': 'EXP-1431: Mixed-Magnitude Sequential Intervention'}
    per_patient = []
    grade_transitions = 0
    total_patients = 0

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs_arr = pdata['carbs']
        n = len(glucose)

        profile = load_profile(pid)
        isf = get_profile_isf(profile)

        baseline = compute_full_assessment(glucose, bolus, carbs_arr, n)

        # Cycle 1: Basal correction at CONSERVATIVE 10%
        g1 = simulate_basal_correction(glucose, baseline['drift'], isf, magnitude_pct=10)
        cycle1 = compute_full_assessment(g1, bolus, carbs_arr, n)

        # Cycle 2: CR correction at AGGRESSIVE 30%
        g2 = simulate_cr_correction(g1, carbs_arr, magnitude_pct=30)
        cycle2 = compute_full_assessment(g2, bolus, carbs_arr, n)

        # Cycle 3: ISF correction at 10%
        g3 = simulate_isf_correction(g2, bolus, carbs_arr, magnitude_pct=10)
        cycle3 = compute_full_assessment(g3, bolus, carbs_arr, n)

        tir_deltas = [
            round(cycle1['tir'] - baseline['tir'], 1),
            round(cycle2['tir'] - cycle1['tir'], 1),
            round(cycle3['tir'] - cycle2['tir'], 1),
        ]
        total_tir_gain = round(cycle3['tir'] - baseline['tir'], 1)
        grade_trajectory = [baseline['grade'], cycle1['grade'], cycle2['grade'], cycle3['grade']]
        transitioned = cycle3['grade'] != baseline['grade'] and cycle3['score'] > baseline['score']

        if transitioned:
            grade_transitions += 1
        total_patients += 1

        entry = {
            'pid': pid,
            'baseline': baseline,
            'cycle1_basal10': cycle1,
            'cycle2_cr30': cycle2,
            'cycle3_isf10': cycle3,
            'tir_delta_per_cycle': tir_deltas,
            'total_tir_gain': total_tir_gain,
            'grade_trajectory': grade_trajectory,
            'grade_transition': transitioned,
        }
        per_patient.append(entry)

        trajectory_str = ' -> '.join(grade_trajectory)
        marker = ' ***TRANSITION***' if transitioned else ''
        print(f"  {pid}: {trajectory_str}  TIR +{total_tir_gain:+.1f}  "
              f"(basal:{tir_deltas[0]:+.1f} CR:{tir_deltas[1]:+.1f} ISF:{tir_deltas[2]:+.1f}){marker}")

    results['per_patient'] = per_patient
    results['grade_transitions'] = grade_transitions
    results['n_patients'] = total_patients
    results['transition_rate'] = round(grade_transitions / max(total_patients, 1) * 100, 1)

    print(f"\n  Grade transitions: {grade_transitions}/{total_patients} "
          f"({results['transition_rate']:.0f}%)")
    print(f"  Key question: mixed-magnitude beats all-conservative (0/11)?  "
          f"{'YES' if grade_transitions > 0 else 'NO'}")

    return results


# ---------------------------------------------------------------------------
# EXP-1432: Correction Bolus Effectiveness
# ---------------------------------------------------------------------------
@register(1432, "Correction Bolus Effectiveness")
def exp_1432(patients, args):
    """Analyze effectiveness of correction boluses across patients."""
    results = {'name': 'EXP-1432: Correction Bolus Effectiveness'}
    per_patient = []
    carb_window = 30 * (STEPS_PER_HOUR // 60)  # ±30min in 5-min steps = 6 steps
    response_2h = 2 * STEPS_PER_HOUR
    response_4h = 4 * STEPS_PER_HOUR

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs_arr = pdata['carbs']
        n = len(glucose)

        correction_events = []
        for i in range(n):
            if bolus[i] < 0.5 or np.isnan(glucose[i]):
                continue
            # Check no carbs within ±30min
            c_start = max(0, i - carb_window)
            c_end = min(n, i + carb_window + 1)
            if np.nansum(carbs_arr[c_start:c_end]) > 2:
                continue
            # Track glucose response
            bg_at_bolus = glucose[i]
            bg_2h = np.nan
            bg_4h = np.nan
            if i + response_2h < n:
                window_2h = glucose[i:i + response_2h]
                valid_2h = window_2h[~np.isnan(window_2h)]
                if len(valid_2h) > 0:
                    bg_2h = float(valid_2h[-1])
            if i + response_4h < n:
                window_4h = glucose[i:i + response_4h]
                valid_4h = window_4h[~np.isnan(window_4h)]
                if len(valid_4h) > 0:
                    bg_4h = float(valid_4h[-1])

            nadir_4h = np.nan
            if i + response_4h < n:
                window_full = glucose[i:i + response_4h]
                valid_full = window_full[~np.isnan(window_full)]
                if len(valid_full) > 0:
                    nadir_4h = float(np.nanmin(valid_full))

            drop_4h = bg_at_bolus - bg_4h if not np.isnan(bg_4h) else np.nan
            effective = not np.isnan(drop_4h) and drop_4h >= 30
            overcorrection = not np.isnan(nadir_4h) and nadir_4h < 70
            ineffective = (not np.isnan(bg_4h) and bg_4h > 180) or \
                          (not np.isnan(drop_4h) and drop_4h < 0)

            correction_events.append({
                'bg_at_bolus': round(bg_at_bolus, 1),
                'dose': round(float(bolus[i]), 2),
                'drop_4h': round(drop_4h, 1) if not np.isnan(drop_4h) else None,
                'effective': effective,
                'overcorrection': overcorrection,
                'ineffective': ineffective,
            })

        n_events = len(correction_events)
        if n_events == 0:
            per_patient.append({
                'pid': pid, 'n_corrections': 0,
                'effectiveness_rate': None, 'overcorrection_rate': None,
            })
            print(f"  {pid}: no correction boluses detected")
            continue

        n_effective = sum(1 for e in correction_events if e['effective'])
        n_overcorrect = sum(1 for e in correction_events if e['overcorrection'])
        n_ineffective = sum(1 for e in correction_events if e['ineffective'])
        eff_rate = round(n_effective / n_events * 100, 1)
        over_rate = round(n_overcorrect / n_events * 100, 1)
        ineff_rate = round(n_ineffective / n_events * 100, 1)

        assessment = compute_full_assessment(glucose, bolus, carbs_arr, n)

        entry = {
            'pid': pid,
            'n_corrections': n_events,
            'n_effective': n_effective,
            'n_overcorrection': n_overcorrect,
            'n_ineffective': n_ineffective,
            'effectiveness_rate': eff_rate,
            'overcorrection_rate': over_rate,
            'ineffective_rate': ineff_rate,
            'mean_dose': round(float(np.mean([e['dose'] for e in correction_events])), 2),
            'mean_starting_bg': round(float(np.mean([e['bg_at_bolus'] for e in correction_events])), 1),
            'grade': assessment['grade'],
            'tir': assessment['tir'],
        }
        per_patient.append(entry)

        print(f"  {pid}: {n_events} corrections, {eff_rate:.0f}% effective, "
              f"{over_rate:.0f}% overcorrect, {ineff_rate:.0f}% ineffective  "
              f"[grade {assessment['grade']}]")

    # Compare well-calibrated (grade A/B) vs poorly-calibrated (grade C/D)
    good = [p for p in per_patient if p.get('grade') in ('A', 'B') and p['n_corrections'] > 0]
    poor = [p for p in per_patient if p.get('grade') in ('C', 'D') and p['n_corrections'] > 0]
    good_eff = np.mean([p['effectiveness_rate'] for p in good]) if good else 0
    poor_eff = np.mean([p['effectiveness_rate'] for p in poor]) if poor else 0

    results['per_patient'] = per_patient
    results['n_patients'] = len(per_patient)
    results['comparison'] = {
        'well_calibrated_effectiveness': round(good_eff, 1),
        'poorly_calibrated_effectiveness': round(poor_eff, 1),
        'n_well_calibrated': len(good),
        'n_poorly_calibrated': len(poor),
    }

    print(f"\n  Well-calibrated (A/B): {good_eff:.1f}% effective ({len(good)} patients)")
    print(f"  Poorly-calibrated (C/D): {poor_eff:.1f}% effective ({len(poor)} patients)")

    return results


# ---------------------------------------------------------------------------
# EXP-1433: Optimal Basal Fraction Analysis
# ---------------------------------------------------------------------------
@register(1433, "Optimal Basal Fraction Analysis")
def exp_1433(patients, args):
    """Analyze basal fraction vs outcomes. Higher basal = worse grade (r=-0.498)."""
    results = {'name': 'EXP-1433: Optimal Basal Fraction Analysis'}
    per_patient = []

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs_arr = pdata['carbs']
        temp_rate = pdata['temp_rate']
        n = len(glucose)

        profile = load_profile(pid)
        basal_schedule = profile.get('basal', []) if profile else []

        assessment = compute_full_assessment(glucose, bolus, carbs_arr, n)

        # Compute total daily dose (TDD) components
        n_days = n // STEPS_PER_DAY
        daily_bolus_totals = []
        daily_basal_totals = []
        daily_effective_basal_totals = []

        for d in range(n_days):
            ds = d * STEPS_PER_DAY
            de = ds + STEPS_PER_DAY
            if de > n:
                break

            day_bolus = np.nansum(bolus[ds:de])
            daily_bolus_totals.append(day_bolus)

            # Scheduled basal: sum hourly rates / 24
            scheduled_basal = 0.0
            for h in range(24):
                rate = get_basal_rate_at_seconds(basal_schedule, h * 3600)
                scheduled_basal += rate  # each rate is U/h, so sum = TDD_basal
            daily_basal_totals.append(scheduled_basal)

            # Effective basal: include temp_rate adjustments
            effective_basal = 0.0
            for step in range(ds, de):
                if step < len(temp_rate) and temp_rate[step] > 0:
                    effective_basal += temp_rate[step] / STEPS_PER_HOUR
                else:
                    h = (step - ds) // STEPS_PER_HOUR
                    rate = get_basal_rate_at_seconds(basal_schedule, h * 3600)
                    effective_basal += rate / STEPS_PER_HOUR
            daily_effective_basal_totals.append(effective_basal)

        if not daily_bolus_totals:
            per_patient.append({'pid': pid, 'basal_fraction': None})
            continue

        mean_daily_bolus = float(np.mean(daily_bolus_totals))
        mean_scheduled_basal = float(np.mean(daily_basal_totals))
        mean_effective_basal = float(np.mean(daily_effective_basal_totals))

        tdd_scheduled = mean_scheduled_basal + mean_daily_bolus
        tdd_effective = mean_effective_basal + mean_daily_bolus

        basal_fraction_scheduled = mean_scheduled_basal / tdd_scheduled if tdd_scheduled > 0 else 0
        basal_fraction_effective = mean_effective_basal / tdd_effective if tdd_effective > 0 else 0

        entry = {
            'pid': pid,
            'mean_daily_bolus': round(mean_daily_bolus, 2),
            'mean_scheduled_basal': round(mean_scheduled_basal, 2),
            'mean_effective_basal': round(mean_effective_basal, 2),
            'tdd_scheduled': round(tdd_scheduled, 2),
            'tdd_effective': round(tdd_effective, 2),
            'basal_fraction_scheduled': round(basal_fraction_scheduled * 100, 1),
            'basal_fraction_effective': round(basal_fraction_effective * 100, 1),
            'tir': assessment['tir'],
            'grade': assessment['grade'],
            'score': assessment['score'],
        }
        per_patient.append(entry)

        in_range = '✓' if 40 <= basal_fraction_scheduled * 100 <= 60 else '✗'
        print(f"  {pid}: scheduled={basal_fraction_scheduled*100:.0f}% "
              f"effective={basal_fraction_effective*100:.0f}% "
              f"TDD={tdd_effective:.1f}U  TIR={assessment['tir']:.0f}%  "
              f"grade={assessment['grade']}  textbook(40-60%):{in_range}")

    # Stratify by TIR to find optimal basal fraction
    valid_patients = [p for p in per_patient if p.get('basal_fraction_scheduled') is not None]
    if len(valid_patients) >= 3:
        fractions = np.array([p['basal_fraction_scheduled'] for p in valid_patients])
        tirs = np.array([p['tir'] for p in valid_patients])
        if np.std(fractions) > 0:
            corr = float(np.corrcoef(fractions, tirs)[0, 1])
        else:
            corr = 0.0
        # Find fraction range for top-TIR patients
        top_mask = tirs >= np.percentile(tirs, 50)
        top_fractions = fractions[top_mask]
        optimal_range = (round(float(np.min(top_fractions)), 1),
                         round(float(np.max(top_fractions)), 1))
    else:
        corr = 0.0
        optimal_range = (0, 0)

    results['per_patient'] = per_patient
    results['n_patients'] = len(per_patient)
    results['basal_fraction_tir_correlation'] = round(corr, 3)
    results['optimal_range_pct'] = list(optimal_range)
    results['textbook_range_pct'] = [40, 60]

    print(f"\n  Basal fraction ↔ TIR correlation: r={corr:.3f}")
    print(f"  Optimal range (top-50% TIR): {optimal_range[0]:.0f}-{optimal_range[1]:.0f}%")
    print(f"  Textbook range: 40-60%")

    return results


# ---------------------------------------------------------------------------
# EXP-1434: Grade D Improvement Protocol
# ---------------------------------------------------------------------------
@register(1434, "Grade D Improvement Protocol")
def exp_1434(patients, args):
    """Design specific improvement protocol for grade D patients (a, c, i)."""
    results = {'name': 'EXP-1434: Grade D Improvement Protocol'}
    per_patient = []
    grade_c_threshold = 50

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs_arr = pdata['carbs']
        n = len(glucose)

        profile = load_profile(pid)
        isf = get_profile_isf(profile)
        baseline = compute_full_assessment(glucose, bolus, carbs_arr, n)

        # Try increasing magnitudes to find minimum changes for grade C
        best_result = None
        best_basal_mag = 0
        best_cr_mag = 0
        best_isf_mag = 0

        # Search space: basal 0-30% by 5, CR 0-60% by 10, ISF 0-30% by 10
        for basal_mag in range(0, 35, 5):
            for cr_mag in range(0, 70, 10):
                for isf_mag in range(0, 35, 10):
                    if basal_mag == 0 and cr_mag == 0 and isf_mag == 0:
                        continue
                    g_sim = glucose.copy()
                    if basal_mag > 0:
                        g_sim = simulate_basal_correction(
                            g_sim, baseline['drift'], isf, magnitude_pct=basal_mag)
                    if cr_mag > 0:
                        g_sim = simulate_cr_correction(g_sim, carbs_arr, magnitude_pct=cr_mag)
                    if isf_mag > 0:
                        g_sim = simulate_isf_correction(
                            g_sim, bolus, carbs_arr, magnitude_pct=isf_mag)
                    sim_assessment = compute_full_assessment(g_sim, bolus, carbs_arr, n)
                    if sim_assessment['score'] >= grade_c_threshold:
                        total_mag = basal_mag + cr_mag + isf_mag
                        if best_result is None or total_mag < (best_basal_mag + best_cr_mag + best_isf_mag):
                            best_result = sim_assessment
                            best_basal_mag = basal_mag
                            best_cr_mag = cr_mag
                            best_isf_mag = isf_mag

        # Also compute max achievable score with aggressive settings
        g_max = glucose.copy()
        g_max = simulate_basal_correction(g_max, baseline['drift'], isf, magnitude_pct=30)
        g_max = simulate_cr_correction(g_max, carbs_arr, magnitude_pct=60)
        g_max = simulate_isf_correction(g_max, bolus, carbs_arr, magnitude_pct=30)
        max_assessment = compute_full_assessment(g_max, bolus, carbs_arr, n)

        # Determine limiting factor
        limiting_factors = []
        if max_assessment['flags']['basal_flag']:
            limiting_factors.append('basal (drift unresolved)')
        if max_assessment['flags']['cr_flag']:
            limiting_factors.append('CR (excursions remain)')
        if max_assessment['flags']['cv_flag']:
            limiting_factors.append('CV (variability high)')
        if max_assessment['tir'] < 70:
            limiting_factors.append(f"TIR stuck at {max_assessment['tir']:.0f}%")

        achievable = best_result is not None
        entry = {
            'pid': pid,
            'is_grade_d': baseline['grade'] == 'D',
            'baseline': baseline,
            'grade_c_achievable': achievable,
            'minimum_changes': {
                'basal_pct': best_basal_mag,
                'cr_pct': best_cr_mag,
                'isf_pct': best_isf_mag,
            } if achievable else None,
            'result_after_minimum': best_result,
            'max_achievable': max_assessment,
            'limiting_factors': limiting_factors if not achievable else [],
        }
        per_patient.append(entry)

        if baseline['grade'] == 'D':
            if achievable:
                print(f"  {pid}: D → C achievable! basal@{best_basal_mag}% CR@{best_cr_mag}% "
                      f"ISF@{best_isf_mag}%  score {baseline['score']:.0f} → {best_result['score']:.0f}")
            else:
                print(f"  {pid}: D → C NOT achievable. Max score={max_assessment['score']:.0f} "
                      f"({max_assessment['grade']}). Limits: {', '.join(limiting_factors)}")
        else:
            if args.detail:
                print(f"  {pid}: grade {baseline['grade']} (not D), "
                      f"max achievable={max_assessment['score']:.0f}")

    grade_d_entries = [p for p in per_patient if p['is_grade_d']]
    n_achievable = sum(1 for p in grade_d_entries if p['grade_c_achievable'])

    results['per_patient'] = per_patient
    results['n_patients'] = len(per_patient)
    results['n_grade_d'] = len(grade_d_entries)
    results['n_grade_c_achievable'] = n_achievable

    print(f"\n  Grade D patients: {len(grade_d_entries)}")
    print(f"  Grade C achievable: {n_achievable}/{len(grade_d_entries)}")

    return results


# ---------------------------------------------------------------------------
# EXP-1435: Correction vs Meal Bolus Glucose Response
# ---------------------------------------------------------------------------
@register(1435, "Correction vs Meal Bolus Glucose Response")
def exp_1435(patients, args):
    """Compare glucose response curves after correction vs meal boluses."""
    results = {'name': 'EXP-1435: Correction vs Meal Bolus Glucose Response'}
    per_patient = []
    carb_window_steps = 6  # ±30 min in 5-min steps
    response_4h = 4 * STEPS_PER_HOUR

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs_arr = pdata['carbs']
        n = len(glucose)

        correction_curves = []
        meal_curves = []

        for i in range(n):
            if bolus[i] < 0.5 or np.isnan(glucose[i]):
                continue
            if i + response_4h >= n:
                continue

            # Extract 4h response curve (relative to bolus time glucose)
            curve = glucose[i:i + response_4h].copy()
            valid_mask = ~np.isnan(curve)
            if valid_mask.sum() < STEPS_PER_HOUR:
                continue
            curve_relative = curve - glucose[i]

            c_start = max(0, i - carb_window_steps)
            c_end = min(n, i + carb_window_steps + 1)
            has_carbs = np.nansum(carbs_arr[c_start:c_end]) > 2

            if has_carbs:
                meal_curves.append(curve_relative)
            else:
                correction_curves.append(curve_relative)

        # Compute average response curves
        def summarize_curves(curves):
            if not curves:
                return None
            arr = np.array(curves)
            mean_curve = np.nanmean(arr, axis=0)
            valid_per_step = np.sum(~np.isnan(arr), axis=0)
            # Nadir: lowest point in mean curve
            valid_mean = mean_curve[~np.isnan(mean_curve)]
            if len(valid_mean) == 0:
                return None
            nadir_val = float(np.nanmin(mean_curve))
            nadir_idx = int(np.nanargmin(mean_curve))
            nadir_time_h = nadir_idx / STEPS_PER_HOUR
            # Peak (for meals): highest point
            peak_val = float(np.nanmax(mean_curve))
            peak_idx = int(np.nanargmax(mean_curve))
            peak_time_h = peak_idx / STEPS_PER_HOUR
            # Return-to-baseline: first index within ±10 mg/dL after nadir
            rtb_h = None
            search_start = max(nadir_idx, peak_idx)
            for j in range(search_start, len(mean_curve)):
                if not np.isnan(mean_curve[j]) and abs(mean_curve[j]) < 10:
                    rtb_h = j / STEPS_PER_HOUR
                    break
            return {
                'n_events': len(curves),
                'nadir_mg': round(nadir_val, 1),
                'nadir_time_h': round(nadir_time_h, 2),
                'peak_mg': round(peak_val, 1),
                'peak_time_h': round(peak_time_h, 2),
                'return_to_baseline_h': round(rtb_h, 2) if rtb_h else None,
                'mean_curve': [round(float(x), 1) if not np.isnan(x) else None
                               for x in mean_curve[::STEPS_PER_HOUR]],
            }

        corr_summary = summarize_curves(correction_curves)
        meal_summary = summarize_curves(meal_curves)

        # Derive ISF from corrections and meals separately
        isf_correction = np.nan
        if correction_curves:
            drops = []
            for i_ev in range(len(correction_curves)):
                # Find corresponding bolus dose - approximate from mean
                curve = correction_curves[i_ev]
                nadir = np.nanmin(curve)
                if nadir < 0:
                    drops.append(abs(nadir))
            if drops:
                # ISF_correction ≈ median drop (but we don't have per-event dose here)
                isf_correction = float(np.median(drops))

        isf_meal = np.nan
        if meal_curves:
            # For meal boluses, ISF derived from post-peak drop
            drops = []
            for curve in meal_curves:
                peak = np.nanmax(curve)
                nadir_after_peak = np.nanmin(curve[int(np.nanargmax(curve)):])
                drop = peak - nadir_after_peak
                if drop > 0:
                    drops.append(drop)
            if drops:
                isf_meal = float(np.median(drops))

        concordance = None
        if not np.isnan(isf_correction) and not np.isnan(isf_meal) and isf_meal > 0:
            concordance = round(isf_correction / isf_meal, 2)

        entry = {
            'pid': pid,
            'correction_response': corr_summary,
            'meal_response': meal_summary,
            'isf_correction_drop': round(isf_correction, 1) if not np.isnan(isf_correction) else None,
            'isf_meal_drop': round(isf_meal, 1) if not np.isnan(isf_meal) else None,
            'isf_concordance_ratio': concordance,
        }
        per_patient.append(entry)

        n_corr = corr_summary['n_events'] if corr_summary else 0
        n_meal = meal_summary['n_events'] if meal_summary else 0
        conc_str = f"ratio={concordance:.2f}" if concordance else "N/A"
        print(f"  {pid}: {n_corr} corrections, {n_meal} meals  ISF concordance: {conc_str}")

    results['per_patient'] = per_patient
    results['n_patients'] = len(per_patient)

    # Overall concordance
    concordances = [p['isf_concordance_ratio'] for p in per_patient
                    if p['isf_concordance_ratio'] is not None]
    if concordances:
        results['mean_concordance'] = round(float(np.mean(concordances)), 2)
        print(f"\n  Mean ISF concordance (correction/meal): {results['mean_concordance']:.2f}")
        print(f"  (1.0 = perfect match; >1 = corrections more effective than meals predict)")

    return results


# ---------------------------------------------------------------------------
# EXP-1436: AID Aggressiveness Scoring
# ---------------------------------------------------------------------------
@register(1436, "AID Aggressiveness Scoring")
def exp_1436(patients, args):
    """Score each patient's AID system aggressiveness."""
    results = {'name': 'EXP-1436: AID Aggressiveness Scoring'}
    per_patient = []

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs_arr = pdata['carbs']
        temp_rate = pdata['temp_rate']
        n = len(glucose)

        profile = load_profile(pid)
        basal_schedule = profile.get('basal', []) if profile else []

        assessment = compute_full_assessment(glucose, bolus, carbs_arr, n)

        # 1. Temp rate variance (normalized by mean rate)
        valid_temp = temp_rate[temp_rate > 0]
        if len(valid_temp) > 10:
            temp_cv = float(np.std(valid_temp) / np.mean(valid_temp) * 100) if np.mean(valid_temp) > 0 else 0
            temp_max_min_ratio = float(np.max(valid_temp) / np.min(valid_temp)) if np.min(valid_temp) > 0 else 1.0
        else:
            temp_cv = 0.0
            temp_max_min_ratio = 1.0

        # 2. Override frequency: how often is temp_rate != 0 (AID is adjusting)
        n_nonzero_temp = int(np.sum(temp_rate > 0))
        override_frequency = round(n_nonzero_temp / max(n, 1) * 100, 1)

        # 3. Rate change frequency: how often does temp_rate change significantly
        if len(valid_temp) > 1:
            rate_changes = np.abs(np.diff(temp_rate))
            significant_changes = np.sum(rate_changes > 0.1)
            change_rate = float(significant_changes / max(n, 1) * STEPS_PER_HOUR)  # changes/hour
        else:
            change_rate = 0.0

        # 4. Response time proxy: average steps between glucose >180 and next temp_rate change
        response_times = []
        i = 0
        while i < n - 1:
            if not np.isnan(glucose[i]) and glucose[i] > 180:
                for j in range(i + 1, min(i + 2 * STEPS_PER_HOUR, n)):
                    if temp_rate[j] > 0 and (j == 0 or abs(temp_rate[j] - temp_rate[j - 1]) > 0.05):
                        response_times.append(j - i)
                        break
                i = j if 'j' in dir() else i + 1
            else:
                i += 1
        avg_response = float(np.mean(response_times)) / STEPS_PER_HOUR if response_times else np.nan

        # Composite aggressiveness score (0-100)
        # High temp_cv, high override freq, high max/min ratio, fast response → aggressive
        score_temp_cv = min(temp_cv / 100, 1.0) * 25  # 0-25 from variance
        score_override = min(override_frequency / 50, 1.0) * 25  # 0-25 from frequency
        score_range = min((temp_max_min_ratio - 1) / 10, 1.0) * 25  # 0-25 from range
        score_response = 25 * (1.0 - min(avg_response / 2, 1.0)) if not np.isnan(avg_response) else 12.5
        aggressiveness = round(score_temp_cv + score_override + score_range + score_response, 1)

        category = 'aggressive' if aggressiveness > 50 else ('moderate' if aggressiveness > 25 else 'passive')

        entry = {
            'pid': pid,
            'temp_rate_cv': round(temp_cv, 1),
            'override_frequency_pct': override_frequency,
            'max_min_ratio': round(temp_max_min_ratio, 2),
            'change_rate_per_hour': round(change_rate, 2),
            'avg_response_time_h': round(avg_response, 2) if not np.isnan(avg_response) else None,
            'aggressiveness_score': aggressiveness,
            'category': category,
            'tir': assessment['tir'],
            'grade': assessment['grade'],
        }
        per_patient.append(entry)

        print(f"  {pid}: aggressiveness={aggressiveness:.0f} ({category})  "
              f"temp_cv={temp_cv:.0f}%  override={override_frequency:.0f}%  "
              f"range={temp_max_min_ratio:.1f}x  TIR={assessment['tir']:.0f}%  "
              f"grade={assessment['grade']}")

    # Correlate aggressiveness with outcomes
    valid = [p for p in per_patient if p['aggressiveness_score'] > 0]
    if len(valid) >= 3:
        agg_scores = np.array([p['aggressiveness_score'] for p in valid])
        tirs = np.array([p['tir'] for p in valid])
        if np.std(agg_scores) > 0:
            corr_tir = float(np.corrcoef(agg_scores, tirs)[0, 1])
        else:
            corr_tir = 0.0
    else:
        corr_tir = 0.0

    results['per_patient'] = per_patient
    results['n_patients'] = len(per_patient)
    results['aggressiveness_tir_correlation'] = round(corr_tir, 3)

    print(f"\n  Aggressiveness ↔ TIR correlation: r={corr_tir:.3f}")

    return results


# ---------------------------------------------------------------------------
# EXP-1437: Glucose Variability Decomposition
# ---------------------------------------------------------------------------
@register(1437, "Glucose Variability Decomposition")
def exp_1437(patients, args):
    """Decompose glucose CV into basal, meal, correction, and unexplained components."""
    results = {'name': 'EXP-1437: Glucose Variability Decomposition'}
    per_patient = []
    carb_window_steps = 6  # ±30 min

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs_arr = pdata['carbs']
        n = len(glucose)
        n_days = n // STEPS_PER_DAY

        total_cv = compute_cv(glucose)

        # 1. Basal variability: overnight 0-6am with no meals/boluses
        overnight_values = []
        for d in range(n_days):
            seg_start = d * STEPS_PER_DAY + 0 * STEPS_PER_HOUR
            seg_end = d * STEPS_PER_DAY + 6 * STEPS_PER_HOUR
            if seg_end > n:
                break
            # Check no bolus/carbs in window
            if np.nansum(bolus[seg_start:seg_end]) > 0.3:
                continue
            if np.nansum(carbs_arr[seg_start:seg_end]) > 2:
                continue
            seg_g = glucose[seg_start:seg_end]
            valid = seg_g[~np.isnan(seg_g)]
            if len(valid) >= STEPS_PER_HOUR:
                overnight_values.extend(valid.tolist())

        basal_cv = compute_cv(np.array(overnight_values)) if len(overnight_values) >= 10 else 0.0

        # 2. Meal variability: 2-4h after carb events
        meal_values = []
        for i in range(n):
            if carbs_arr[i] < 5 or np.isnan(glucose[i]):
                continue
            start = i + 2 * STEPS_PER_HOUR
            end = i + 4 * STEPS_PER_HOUR
            if end > n:
                continue
            seg_g = glucose[start:end]
            valid = seg_g[~np.isnan(seg_g)]
            if len(valid) >= 6:
                meal_values.extend(valid.tolist())

        meal_cv = compute_cv(np.array(meal_values)) if len(meal_values) >= 10 else 0.0

        # 3. Correction variability: 2-4h after correction bolus (no carbs)
        correction_values = []
        for i in range(n):
            if bolus[i] < 0.5 or np.isnan(glucose[i]):
                continue
            c_start = max(0, i - carb_window_steps)
            c_end = min(n, i + carb_window_steps + 1)
            if np.nansum(carbs_arr[c_start:c_end]) > 2:
                continue
            start = i + 2 * STEPS_PER_HOUR
            end = i + 4 * STEPS_PER_HOUR
            if end > n:
                continue
            seg_g = glucose[start:end]
            valid = seg_g[~np.isnan(seg_g)]
            if len(valid) >= 6:
                correction_values.extend(valid.tolist())

        correction_cv = compute_cv(np.array(correction_values)) if len(correction_values) >= 10 else 0.0

        # 4. Unexplained: total variance - sum of component variances
        total_var = (total_cv / 100 * np.nanmean(glucose[~np.isnan(glucose)])) ** 2 if total_cv > 0 else 0
        basal_var = (basal_cv / 100 * np.mean(overnight_values)) ** 2 if overnight_values and basal_cv > 0 else 0
        meal_var = (meal_cv / 100 * np.mean(meal_values)) ** 2 if meal_values and meal_cv > 0 else 0
        corr_var = (correction_cv / 100 * np.mean(correction_values)) ** 2 if correction_values and correction_cv > 0 else 0

        explained_var = basal_var + meal_var + corr_var
        unexplained_var = max(0, total_var - explained_var)
        unexplained_cv = round(np.sqrt(unexplained_var) / np.nanmean(glucose[~np.isnan(glucose)]) * 100, 1) \
            if total_var > 0 else 0.0

        # Determine dominant source
        components = {
            'basal': basal_cv,
            'meal': meal_cv,
            'correction': correction_cv,
            'unexplained': unexplained_cv,
        }
        dominant = max(components, key=components.get)

        # Map to recommendation
        rec_map = {
            'basal': 'Adjust basal rates (overnight drift)',
            'meal': 'Adjust carb ratio (meal spikes)',
            'correction': 'Adjust ISF (correction response)',
            'unexplained': 'Complex — may need timing/pattern changes',
        }

        entry = {
            'pid': pid,
            'total_cv': round(total_cv, 1),
            'basal_cv': round(basal_cv, 1),
            'meal_cv': round(meal_cv, 1),
            'correction_cv': round(correction_cv, 1),
            'unexplained_cv': round(unexplained_cv, 1),
            'n_overnight_values': len(overnight_values),
            'n_meal_values': len(meal_values),
            'n_correction_values': len(correction_values),
            'dominant_source': dominant,
            'recommendation': rec_map[dominant],
        }
        per_patient.append(entry)

        print(f"  {pid}: total={total_cv:.1f}%  basal={basal_cv:.1f}%  "
              f"meal={meal_cv:.1f}%  corr={correction_cv:.1f}%  "
              f"unexp={unexplained_cv:.1f}%  → {dominant}")

    # Aggregate: which source dominates most often?
    dominant_counts = defaultdict(int)
    for p in per_patient:
        dominant_counts[p['dominant_source']] += 1

    results['per_patient'] = per_patient
    results['n_patients'] = len(per_patient)
    results['dominant_source_distribution'] = dict(dominant_counts)

    print(f"\n  Dominant source distribution: {dict(dominant_counts)}")

    return results


# ---------------------------------------------------------------------------
# EXP-1438: Weekly Grade Prediction Model
# ---------------------------------------------------------------------------
@register(1438, "Weekly Grade Prediction Model")
def exp_1438(patients, args):
    """Predict next-week grade from this-week metrics using correlation analysis."""
    results = {'name': 'EXP-1438: Weekly Grade Prediction Model'}
    grade_map = {'A': 4, 'B': 3, 'C': 2, 'D': 1}

    all_week_pairs = []  # (this_week_features, next_week_grade_num)

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs_arr = pdata['carbs']
        n = len(glucose)
        n_weeks = n // WEEKLY_STEPS

        weekly_data = []
        for w in range(n_weeks):
            ws = w * WEEKLY_STEPS
            we = ws + WEEKLY_STEPS
            if we > n:
                break
            g = glucose[ws:we]
            b = bolus[ws:we]
            c = carbs_arr[ws:we]
            wn = len(g)

            tir = compute_tir(g)
            cv = compute_cv(g)
            exc = compute_max_excursion(g, c, wn)

            # Compute drift for this week
            drifts = []
            for d in range(7):
                dr = compute_segment_drift(glucose, bolus, carbs_arr, ws + d * STEPS_PER_DAY, 0, 6)
                if not np.isnan(dr):
                    drifts.append(abs(dr))
            drift = float(np.median(drifts)) if drifts else 0.0

            isf = compute_isf_ratio(g, b, c, wn)
            score = compute_therapy_score(tir, drift, exc, isf, cv)
            grade = get_grade(score)

            bolus_count = int(np.sum(b > 0.1))
            carb_count = int(np.sum(c > 2))

            weekly_data.append({
                'week': w,
                'tir': tir,
                'drift': drift,
                'excursion': exc,
                'cv': cv,
                'bolus_count': bolus_count,
                'carb_count': carb_count,
                'score': score,
                'grade': grade,
                'grade_num': grade_map.get(grade, 1),
            })

        # Create pairs: this-week features → next-week grade
        for i in range(len(weekly_data) - 1):
            this_week = weekly_data[i]
            next_grade = weekly_data[i + 1]['grade_num']
            all_week_pairs.append((this_week, next_grade))

    if len(all_week_pairs) < 5:
        print("  Insufficient weekly data for analysis")
        results['per_patient'] = []
        results['n_pairs'] = 0
        results['best_predictor'] = None
        return results

    # Feature correlation with next-week grade
    features = ['tir', 'drift', 'excursion', 'cv', 'bolus_count', 'carb_count', 'score']
    feature_correlations = {}
    next_grades = np.array([p[1] for p in all_week_pairs])

    for feat in features:
        feat_vals = np.array([p[0][feat] for p in all_week_pairs])
        if np.std(feat_vals) > 0 and np.std(next_grades) > 0:
            corr = float(np.corrcoef(feat_vals, next_grades)[0, 1])
        else:
            corr = 0.0
        feature_correlations[feat] = round(corr, 3)

    # Best predictor = highest absolute correlation
    best_feat = max(feature_correlations, key=lambda k: abs(feature_correlations[k]))
    best_corr = feature_correlations[best_feat]

    # Simple prediction accuracy: predict next-week grade = this-week grade
    correct_predictions = sum(1 for tw, ng in all_week_pairs
                              if tw['grade_num'] == ng)
    naive_accuracy = round(correct_predictions / len(all_week_pairs) * 100, 1)

    # Score-threshold prediction: use this-week score to predict next-week grade
    score_predictions_correct = 0
    for tw, ng in all_week_pairs:
        predicted_grade_num = grade_map.get(get_grade(tw['score']), 1)
        if predicted_grade_num == ng:
            score_predictions_correct += 1
    score_accuracy = round(score_predictions_correct / len(all_week_pairs) * 100, 1)

    results['n_pairs'] = len(all_week_pairs)
    results['feature_correlations'] = feature_correlations
    results['best_predictor'] = best_feat
    results['best_predictor_correlation'] = best_corr
    results['naive_accuracy_pct'] = naive_accuracy
    results['score_accuracy_pct'] = score_accuracy
    results['n_patients'] = len(patients)

    print(f"  {len(all_week_pairs)} week-pairs across {len(patients)} patients")
    print(f"  Feature correlations with next-week grade:")
    for feat in sorted(feature_correlations, key=lambda k: abs(feature_correlations[k]), reverse=True):
        print(f"    {feat:15s}: r={feature_correlations[feat]:+.3f}")
    print(f"\n  Best predictor: {best_feat} (r={best_corr:+.3f})")
    print(f"  Naive (same-grade) accuracy: {naive_accuracy:.0f}%")
    print(f"  Score-based accuracy: {score_accuracy:.0f}%")

    return results


# ---------------------------------------------------------------------------
# EXP-1439: Intervention Impact Estimation
# ---------------------------------------------------------------------------
@register(1439, "Intervention Impact Estimation")
def exp_1439(patients, args):
    """Estimate TIR improvement from each intervention type per patient."""
    results = {'name': 'EXP-1439: Intervention Impact Estimation'}
    per_patient = []

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs_arr = pdata['carbs']
        n = len(glucose)

        profile = load_profile(pid)
        isf = get_profile_isf(profile)
        baseline = compute_full_assessment(glucose, bolus, carbs_arr, n)
        baseline_tir = baseline['tir']

        # 1. Basal fix: remove overnight drift
        g_basal = simulate_basal_correction(glucose, baseline['drift'], isf, magnitude_pct=100)
        tir_basal = compute_tir(g_basal)
        gain_basal = round(tir_basal - baseline_tir, 2)

        # 2. CR fix: reduce excursions by 30%
        g_cr = simulate_cr_correction(glucose, carbs_arr, magnitude_pct=30)
        tir_cr = compute_tir(g_cr)
        gain_cr = round(tir_cr - baseline_tir, 2)

        # 3. ISF fix: improve correction effectiveness
        g_isf = simulate_isf_correction(glucose, bolus, carbs_arr, magnitude_pct=30)
        tir_isf = compute_tir(g_isf)
        gain_isf = round(tir_isf - baseline_tir, 2)

        # 4. Combined: all three together
        g_all = simulate_basal_correction(glucose, baseline['drift'], isf, magnitude_pct=100)
        g_all = simulate_cr_correction(g_all, carbs_arr, magnitude_pct=30)
        g_all = simulate_isf_correction(g_all, bolus, carbs_arr, magnitude_pct=30)
        tir_combined = compute_tir(g_all)
        gain_combined = round(tir_combined - baseline_tir, 2)

        # Additivity check: is combined ≈ sum of individual gains?
        sum_individual = gain_basal + gain_cr + gain_isf
        if sum_individual > 0:
            additivity_ratio = round(gain_combined / sum_individual, 2)
        else:
            additivity_ratio = None

        entry = {
            'pid': pid,
            'baseline_tir': baseline_tir,
            'gain_basal_fix': gain_basal,
            'gain_cr_fix': gain_cr,
            'gain_isf_fix': gain_isf,
            'gain_combined': gain_combined,
            'sum_individual': round(sum_individual, 2),
            'additivity_ratio': additivity_ratio,
            'is_subadditive': additivity_ratio is not None and additivity_ratio < 0.9,
            'grade': baseline['grade'],
        }
        per_patient.append(entry)

        add_str = f"ratio={additivity_ratio:.2f}" if additivity_ratio else "N/A"
        sub = " (sub-additive)" if entry['is_subadditive'] else ""
        print(f"  {pid}: baseline TIR={baseline_tir:.0f}%  "
              f"basal:+{gain_basal:.1f}  CR:+{gain_cr:.1f}  ISF:+{gain_isf:.1f}  "
              f"combined:+{gain_combined:.1f}  {add_str}{sub}")

    # Aggregate
    n_subadditive = sum(1 for p in per_patient if p['is_subadditive'])
    avg_gains = {
        'basal': round(float(np.mean([p['gain_basal_fix'] for p in per_patient])), 2),
        'cr': round(float(np.mean([p['gain_cr_fix'] for p in per_patient])), 2),
        'isf': round(float(np.mean([p['gain_isf_fix'] for p in per_patient])), 2),
        'combined': round(float(np.mean([p['gain_combined'] for p in per_patient])), 2),
    }

    results['per_patient'] = per_patient
    results['n_patients'] = len(per_patient)
    results['avg_gains'] = avg_gains
    results['n_subadditive'] = n_subadditive

    print(f"\n  Average TIR gains: basal={avg_gains['basal']:+.1f}  CR={avg_gains['cr']:+.1f}  "
          f"ISF={avg_gains['isf']:+.1f}  combined={avg_gains['combined']:+.1f}")
    print(f"  Sub-additive: {n_subadditive}/{len(per_patient)} patients")

    return results


# ---------------------------------------------------------------------------
# EXP-1440: Clinical Decision Support Summary
# ---------------------------------------------------------------------------
@register(1440, "Clinical Decision Support Summary")
def exp_1440(patients, args):
    """Generate per-patient clinical decision support dashboard."""
    results = {'name': 'EXP-1440: Clinical Decision Support Summary'}
    per_patient = []

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs_arr = pdata['carbs']
        temp_rate = pdata['temp_rate']
        n = len(glucose)
        n_days = n // STEPS_PER_DAY

        profile = load_profile(pid)
        isf = get_profile_isf(profile)

        # --- Current assessment ---
        baseline = compute_full_assessment(glucose, bolus, carbs_arr, n)

        # --- Trend: compare first-half vs second-half ---
        mid = n // 2
        if mid > WEEKLY_STEPS:
            first_half = compute_full_assessment(glucose[:mid], bolus[:mid], carbs_arr[:mid], mid)
            second_half = compute_full_assessment(glucose[mid:], bolus[mid:], carbs_arr[mid:], n - mid)
            score_trend = round(second_half['score'] - first_half['score'], 1)
            if score_trend > 5:
                trend = 'improving'
            elif score_trend < -5:
                trend = 'declining'
            else:
                trend = 'stable'
        else:
            score_trend = 0.0
            trend = 'unknown'

        # --- Urgency ---
        urgency_score = 0
        if baseline['grade'] == 'D':
            urgency_score += 3
        elif baseline['grade'] == 'C':
            urgency_score += 1
        if trend == 'declining':
            urgency_score += 2
        if baseline['tir'] < 50:
            urgency_score += 2
        if baseline['cv'] > 50:
            urgency_score += 1

        if urgency_score >= 5:
            urgency = 'HIGH'
        elif urgency_score >= 3:
            urgency = 'MEDIUM'
        else:
            urgency = 'LOW'

        # --- Top 3 actions with magnitudes ---
        actions = []

        # Action 1: Basal
        if baseline['flags']['basal_flag']:
            g_basal = simulate_basal_correction(glucose, baseline['drift'], isf, magnitude_pct=10)
            tir_gain = compute_tir(g_basal) - baseline['tir']
            actions.append({
                'parameter': 'basal',
                'direction': 'increase' if baseline['drift'] > 0 else 'decrease',
                'magnitude_pct': 10,
                'estimated_tir_gain': round(tir_gain, 1),
                'reason': f"Overnight drift {baseline['drift']:+.1f} mg/dL/h",
                'priority': 1 if abs(baseline['drift']) > 2 * DRIFT_THRESHOLD else 2,
            })

        # Action 2: CR
        if baseline['flags']['cr_flag']:
            g_cr = simulate_cr_correction(glucose, carbs_arr, magnitude_pct=30)
            tir_gain = compute_tir(g_cr) - baseline['tir']
            actions.append({
                'parameter': 'carb_ratio',
                'direction': 'tighten',
                'magnitude_pct': 30,
                'estimated_tir_gain': round(tir_gain, 1),
                'reason': f"Post-meal excursion {baseline['excursion']:.0f} mg/dL",
                'priority': 1 if baseline['excursion'] > 2 * EXCURSION_THRESHOLD else 2,
            })

        # Action 3: CV / ISF
        if baseline['flags']['cv_flag']:
            g_isf = simulate_isf_correction(glucose, bolus, carbs_arr, magnitude_pct=10)
            tir_gain = compute_tir(g_isf) - baseline['tir']
            actions.append({
                'parameter': 'isf',
                'direction': 'decrease',
                'magnitude_pct': 10,
                'estimated_tir_gain': round(tir_gain, 1),
                'reason': f"CV {baseline['cv']:.1f}% above threshold",
                'priority': 3,
            })

        # Sort by priority, take top 3
        actions.sort(key=lambda a: a['priority'])
        top_actions = actions[:3]

        # --- Time-of-day focus ---
        segment_tirs = {}
        for seg_name, (h_start, h_end) in zip(SEGMENT_NAMES, SEGMENT_HOURS):
            seg_values = []
            for d in range(n_days):
                seg_start = d * STEPS_PER_DAY + h_start * STEPS_PER_HOUR
                seg_end = d * STEPS_PER_DAY + h_end * STEPS_PER_HOUR
                if seg_end > n:
                    break
                seg_g = glucose[seg_start:seg_end]
                valid = seg_g[~np.isnan(seg_g)]
                if len(valid) > 0:
                    seg_values.extend(valid.tolist())
            if seg_values:
                seg_tir = float(np.mean((np.array(seg_values) >= 70) &
                                        (np.array(seg_values) <= 180)) * 100)
                segment_tirs[seg_name] = round(seg_tir, 1)
            else:
                segment_tirs[seg_name] = None

        worst_segment = min(
            ((k, v) for k, v in segment_tirs.items() if v is not None),
            key=lambda x: x[1], default=(None, None)
        )

        # --- AID ceiling check ---
        valid_temp = temp_rate[temp_rate > 0]
        if len(valid_temp) > 10:
            max_ratio = float(np.max(valid_temp) / np.mean(valid_temp)) if np.mean(valid_temp) > 0 else 1
            at_ceiling = max_ratio > 5
        else:
            max_ratio = 1.0
            at_ceiling = False

        # --- Confidence (bootstrap CI) ---
        n_bootstrap = 100
        bootstrap_tirs = []
        valid_glucose = glucose[~np.isnan(glucose)]
        for _ in range(n_bootstrap):
            sample = np.random.choice(valid_glucose, size=len(valid_glucose), replace=True)
            bootstrap_tirs.append(compute_tir(sample))
        ci_lower = round(float(np.percentile(bootstrap_tirs, 2.5)), 1)
        ci_upper = round(float(np.percentile(bootstrap_tirs, 97.5)), 1)
        confidence = 'high' if (ci_upper - ci_lower) < 5 else ('moderate' if (ci_upper - ci_lower) < 10 else 'low')

        decision_support = {
            'pid': pid,
            'current_grade': baseline['grade'],
            'current_score': baseline['score'],
            'current_tir': baseline['tir'],
            'tir_ci_95': [ci_lower, ci_upper],
            'confidence': confidence,
            'trend': trend,
            'score_trend': score_trend,
            'urgency': urgency,
            'top_actions': top_actions,
            'n_actions': len(top_actions),
            'segment_tirs': segment_tirs,
            'worst_time_of_day': worst_segment[0],
            'worst_segment_tir': worst_segment[1],
            'aid_ceiling': at_ceiling,
            'aid_max_ratio': round(max_ratio, 1),
            'assessment': baseline,
        }
        per_patient.append(decision_support)

        action_strs = [f"{a['parameter']}@{a['magnitude_pct']}% (+{a['estimated_tir_gain']:.1f})"
                       for a in top_actions]
        actions_desc = ', '.join(action_strs) if action_strs else 'none flagged'
        ceiling_str = ' ⚠CEILING' if at_ceiling else ''
        print(f"  {pid}: grade={baseline['grade']}  trend={trend}  urgency={urgency}  "
              f"confidence={confidence}  actions: {actions_desc}{ceiling_str}")

    # Summary statistics
    grade_dist = defaultdict(int)
    urgency_dist = defaultdict(int)
    for p in per_patient:
        grade_dist[p['current_grade']] += 1
        urgency_dist[p['urgency']] += 1

    results['per_patient'] = per_patient
    results['n_patients'] = len(per_patient)
    results['grade_distribution'] = dict(grade_dist)
    results['urgency_distribution'] = dict(urgency_dist)

    print(f"\n  === CLINICAL DASHBOARD SUMMARY ===")
    print(f"  Patients: {len(per_patient)}")
    print(f"  Grades: {dict(grade_dist)}")
    print(f"  Urgency: {dict(urgency_dist)}")
    n_with_actions = sum(1 for p in per_patient if p['n_actions'] > 0)
    print(f"  Patients needing action: {n_with_actions}/{len(per_patient)}")

    return results


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description='EXP-1431 to EXP-1440: Mixed-magnitude intervention & correction analysis')
    parser.add_argument('--detail', action='store_true', help='Show detailed output')
    parser.add_argument('--save', action='store_true', help='Save results to JSON')
    parser.add_argument('--max-patients', type=int, default=11, help='Max patients to load')
    parser.add_argument('--exp', type=int, nargs='*', help='Run specific experiments')
    args = parser.parse_args()

    patients = load_patients(max_patients=args.max_patients)
    print(f"Loaded {len(patients)} patients")

    for pid, pdata in sorted(patients.items()):
        n = len(pdata['glucose'])
        n_days = n // STEPS_PER_DAY
        valid_pct = round(pdata['valid'].sum() / max(n, 1) * 100, 1)
        tags = []
        if pid in GRADE_D_PATIENTS:
            tags.append('GRADE-D')
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
            print(f"  EXP-{exp_id}: OK ({r.get('elapsed_sec', '?')}s, "
                  f"{r.get('n_patients', '?')} patients)")
        elif exp_id in EXPERIMENTS:
            print(f"  EXP-{exp_id}: FAILED")


if __name__ == '__main__':
    main()
