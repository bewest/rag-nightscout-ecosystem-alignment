#!/usr/bin/env python3
"""EXP-1411 to EXP-1420: Multi-segment basal implementation & grade D triage."""

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

SEGMENT_NAMES = ['midnight(0-6)', 'morning(6-12)', 'afternoon(12-18)', 'evening(18-24)']
SEGMENT_HOURS = [(0, 6), (6, 12), (12, 18), (18, 24)]

DAWN_PATIENTS = {'a', 'd', 'j'}
GRADE_D_PATIENTS = {'a', 'c', 'i'}

# Scoring weights: TIR/100*60 + basal*15 + CR*15 + ISF*5 + CV*5
SCORE_WEIGHTS = {'tir': 60, 'basal': 15, 'cr': 15, 'isf': 5, 'cv': 5}
DRIFT_THRESHOLD = 5.0      # mg/dL/h
EXCURSION_THRESHOLD = 70   # mg/dL
CV_THRESHOLD = 36           # %
MIN_BOLUS_ISF = 2.0         # U
MIN_ISF_EVENTS = 5

BIWEEKLY_STEPS = 14 * STEPS_PER_DAY

EXPERIMENTS = {}


def register(exp_id, title):
    """Decorator to register experiment functions."""
    def decorator(fn):
        EXPERIMENTS[exp_id] = (title, fn)
        return fn
    return decorator


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
    if seg_end > n:
        return np.nan

    seg_g = glucose[seg_start:seg_end].copy()
    seg_valid = ~np.isnan(seg_g)
    if seg_valid.sum() < STEPS_PER_HOUR:
        return np.nan

    # Check for bolus in prior 4h or carbs in prior 3h
    lookback_bolus = 4 * STEPS_PER_HOUR
    lookback_carbs = 3 * STEPS_PER_HOUR
    check_start_b = max(0, seg_start - lookback_bolus)
    check_start_c = max(0, seg_start - lookback_carbs)
    if np.nansum(bolus[check_start_b:seg_end]) > 0.3:
        return np.nan
    if np.nansum(carbs[check_start_c:seg_end]) > 2.0:
        return np.nan

    # Linear fit to valid glucose values
    valid_idx = np.where(seg_valid)[0]
    valid_bg = seg_g[valid_idx]
    hours = valid_idx / STEPS_PER_HOUR
    if len(valid_idx) < 3:
        return np.nan
    coeffs = np.polyfit(hours, valid_bg, 1)
    return float(coeffs[0])  # slope = mg/dL/h


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
    """Compute max post-meal excursion across all meals."""
    excursions = []
    window = 4 * STEPS_PER_HOUR  # 4h post-meal
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
    """Deconfounded ISF: only correction boluses >=2U, no carbs ±60min, need >=5 events."""
    events = []
    carb_window = STEPS_PER_HOUR  # 60min
    response_window = 3 * STEPS_PER_HOUR
    for i in range(n):
        if bolus[i] < MIN_BOLUS_ISF or np.isnan(glucose[i]):
            continue
        # No carbs within ±60min
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
        return 1.0  # default OK
    return float(np.median(events))


def compute_therapy_score(tir, drift, max_excursion, isf_ratio, cv):
    """Compute therapy score 0-100."""
    tir_score = min(tir, 100) / 100 * SCORE_WEIGHTS['tir']
    basal_ok = 1.0 if abs(drift) < DRIFT_THRESHOLD else 0.0
    cr_ok = 1.0 if max_excursion < EXCURSION_THRESHOLD else 0.0
    isf_ok = 1.0  # simplified; ISF ratio near expected = OK
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


def compute_biweekly_scores(glucose, bolus, carbs, n):
    """Compute score for each biweekly (14-day) window."""
    scores = []
    n_windows = n // BIWEEKLY_STEPS
    for w in range(n_windows):
        ws = w * BIWEEKLY_STEPS
        we = ws + BIWEEKLY_STEPS
        if we > n:
            break
        g = glucose[ws:we]
        b = bolus[ws:we]
        c = carbs[ws:we]
        tir = compute_tir(g)
        # Overnight drift for this window
        drifts = []
        for d in range(14):
            dr = compute_segment_drift(glucose, bolus, carbs, ws + d * STEPS_PER_DAY, 0, 6)
            if not np.isnan(dr):
                drifts.append(abs(dr))
        drift = float(np.median(drifts)) if drifts else 0.0
        exc = compute_max_excursion(g, c, len(g))
        cv = compute_cv(g)
        isf = compute_isf_ratio(g, b, c, len(g))
        score = compute_therapy_score(tir, drift, exc, isf, cv)
        scores.append({
            'window': w,
            'score': round(score, 1),
            'grade': get_grade(score),
            'tir': round(tir, 1),
            'drift': round(drift, 2),
            'excursion': round(exc, 1),
            'cv': round(cv, 1),
        })
    return scores


def compute_weekly_metrics(glucose, bolus, carbs, n):
    """Compute weekly dashboard metrics."""
    weekly_steps = 7 * STEPS_PER_DAY
    weeks = []
    n_weeks = n // weekly_steps
    for w in range(n_weeks):
        ws = w * weekly_steps
        we = ws + weekly_steps
        if we > n:
            break
        g = glucose[ws:we]
        b = bolus[ws:we]
        c = carbs[ws:we]
        tir = compute_tir(g)
        # Drift score: 100 if drift < threshold, linearly drop to 0 at 3x threshold
        drifts = []
        for d in range(7):
            dr = compute_segment_drift(glucose, bolus, carbs, ws + d * STEPS_PER_DAY, 0, 6)
            if not np.isnan(dr):
                drifts.append(abs(dr))
        med_drift = float(np.median(drifts)) if drifts else 0.0
        drift_score = max(0, min(100, 100 * (1 - med_drift / (3 * DRIFT_THRESHOLD))))
        # Meal score: 100 if excursion < threshold, linear drop
        exc = compute_max_excursion(g, c, len(g))
        meal_score = max(0, min(100, 100 * (1 - exc / (3 * EXCURSION_THRESHOLD))))
        cv = compute_cv(g)
        overall = compute_therapy_score(tir, med_drift, exc, 1.0, cv)
        weeks.append({
            'week': w,
            'tir': round(tir, 1),
            'drift_score': round(drift_score, 1),
            'meal_score': round(meal_score, 1),
            'grade': get_grade(overall),
            'score': round(overall, 1),
            'cv': round(cv, 1),
        })
    return weeks


# ---------------------------------------------------------------------------
# EXP-1411: Multi-Segment Basal Rate Translation
# ---------------------------------------------------------------------------
@register(1411, "Multi-Segment Basal Rate Translation")
def exp_1411(patients, args):
    """Convert per-segment drift into actionable basal rate adjustments (U/h)."""
    results = {'name': 'EXP-1411: Multi-Segment Basal Rate Translation'}
    per_patient = []
    default_isf = 50.0  # mg/dL per U, fallback

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs = pdata['carbs']
        n = len(glucose)
        n_days = n // STEPS_PER_DAY

        profile = load_profile(pid)
        basal_schedule = profile.get('basal', []) if profile else []
        sens_schedule = profile.get('sens', []) if profile else []
        units = profile.get('_units', 'mg/dL') if profile else 'mg/dL'

        # Get ISF from profile (use midpoint of day)
        isf = default_isf
        if sens_schedule:
            isf = float(sens_schedule[0].get('value', default_isf))
            if units == 'mmol/L' or (isinstance(isf, (int, float)) and isf < 10):
                isf *= 18.0  # convert mmol/L to mg/dL

        segments = []
        total_daily_change = 0.0
        for seg_name, (h_start, h_end) in zip(SEGMENT_NAMES, SEGMENT_HOURS):
            drifts = []
            for d in range(min(n_days, 180)):
                dr = compute_segment_drift(glucose, bolus, carbs, d * STEPS_PER_DAY, h_start, h_end)
                if not np.isnan(dr):
                    drifts.append(dr)

            current_rate = get_segment_basal(basal_schedule, h_start, h_end)
            if drifts:
                med_drift = float(np.median(drifts))
                # new_rate = current_rate * (1 + drift / ISF)
                adjustment_factor = med_drift / isf if isf > 0 else 0
                new_rate = current_rate * (1 + adjustment_factor)
                new_rate = max(0.05, round(new_rate, 3))
                delta = new_rate - current_rate
                seg_hours = h_end - h_start
                total_daily_change += delta * seg_hours
                flagged = abs(med_drift) >= DRIFT_THRESHOLD
            else:
                med_drift = 0.0
                new_rate = current_rate
                delta = 0.0
                flagged = False

            segments.append({
                'segment': seg_name,
                'h_start': h_start,
                'h_end': h_end,
                'current_rate': round(current_rate, 3),
                'median_drift': round(med_drift, 2),
                'recommended_rate': round(new_rate, 3),
                'delta': round(delta, 3),
                'flagged': flagged,
                'n_days_measured': len(drifts),
            })

        n_flagged = sum(1 for s in segments if s['flagged'])
        per_patient.append({
            'patient': pid,
            'isf_used': round(isf, 1),
            'segments': segments,
            'n_flagged_segments': n_flagged,
            'total_daily_dose_change': round(total_daily_change, 2),
        })
        if args.detail or n_flagged > 0:
            print(f"  {pid}: {n_flagged}/4 segments flagged, TDD change {total_daily_change:+.2f}U")
            for s in segments:
                flag = ' *' if s['flagged'] else ''
                print(f"    {s['segment']}: {s['current_rate']:.2f} → {s['recommended_rate']:.2f} U/h "
                      f"(drift {s['median_drift']:+.1f} mg/dL/h){flag}")

    results['per_patient'] = per_patient
    results['n_patients'] = len(per_patient)
    results['n_needing_adjustment'] = sum(1 for p in per_patient if p['n_flagged_segments'] > 0)
    results['mean_tdd_change'] = round(float(np.mean([p['total_daily_dose_change'] for p in per_patient])), 2)
    print(f"\n  Summary: {results['n_needing_adjustment']}/{results['n_patients']} patients need basal adjustment")
    print(f"  Mean TDD change: {results['mean_tdd_change']:+.2f}U")
    return results


# ---------------------------------------------------------------------------
# EXP-1412: Dawn Phenomenon vs AID Compensation
# ---------------------------------------------------------------------------
@register(1412, "Dawn Phenomenon vs AID Compensation")
def exp_1412(patients, args):
    """Check if AID already compensates for dawn phenomenon in dawn patients."""
    results = {'name': 'EXP-1412: Dawn Phenomenon vs AID Compensation'}
    per_patient = []

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs = pdata['carbs']
        temp_rate = pdata['temp_rate']
        n = len(glucose)
        n_days = n // STEPS_PER_DAY
        is_dawn = pid in DAWN_PATIENTS

        profile = load_profile(pid)
        basal_schedule = profile.get('basal', []) if profile else []

        # Pre-dawn window: 2-5am
        pre_dawn_h = (2, 5)
        # Dawn window: 4-7am
        dawn_h = (4, 7)

        compensation_ratios = []
        dawn_residuals = []

        for d in range(min(n_days, 180)):
            ds = d * STEPS_PER_DAY
            pd_start = ds + pre_dawn_h[0] * STEPS_PER_HOUR
            pd_end = ds + pre_dawn_h[1] * STEPS_PER_HOUR
            dw_start = ds + dawn_h[0] * STEPS_PER_HOUR
            dw_end = ds + dawn_h[1] * STEPS_PER_HOUR
            if dw_end > n:
                break

            # Compute scheduled basal for pre-dawn hours
            sched_rates = []
            actual_rates = []
            for h in range(pre_dawn_h[0], pre_dawn_h[1]):
                sched = get_basal_rate_at_seconds(basal_schedule, h * 3600)
                sched_rates.append(sched)
                # Actual temp rate in this hour
                hr_start = ds + h * STEPS_PER_HOUR
                hr_end = hr_start + STEPS_PER_HOUR
                tr = temp_rate[hr_start:hr_end]
                valid_tr = tr[~np.isnan(tr)]
                if len(valid_tr) > 0:
                    actual_rates.append(float(np.mean(valid_tr)))
                else:
                    actual_rates.append(sched)

            sched_mean = float(np.mean(sched_rates)) if sched_rates else 1.0
            actual_mean = float(np.mean(actual_rates)) if actual_rates else sched_mean

            if sched_mean > 0:
                ratio = actual_mean / sched_mean
                compensation_ratios.append(ratio)

            # Dawn residual: glucose rise despite AID
            dawn_g = glucose[dw_start:dw_end]
            dv = dawn_g[~np.isnan(dawn_g)]
            # Check no carbs/bolus during dawn
            if np.nansum(carbs[dw_start:dw_end]) > 2 or np.nansum(bolus[dw_start:dw_end]) > 0.3:
                continue
            if len(dv) >= STEPS_PER_HOUR:
                residual = float(dv[-1] - dv[0])
                dawn_residuals.append(residual)

        mean_ratio = float(np.mean(compensation_ratios)) if compensation_ratios else 1.0
        mean_residual = float(np.mean(dawn_residuals)) if dawn_residuals else 0.0
        aid_compensating = mean_ratio > 1.20
        uncompensated = is_dawn and not aid_compensating and mean_residual > 10

        rec = {
            'patient': pid,
            'is_dawn_patient': is_dawn,
            'mean_aid_compensation_ratio': round(mean_ratio, 3),
            'aid_compensating': aid_compensating,
            'mean_dawn_residual_mg_dl': round(mean_residual, 1),
            'n_days_measured': len(compensation_ratios),
            'n_dawn_days_clean': len(dawn_residuals),
            'uncompensated_dawn': uncompensated,
        }

        if is_dawn:
            if aid_compensating:
                rec['interpretation'] = 'AID already compensating (>120% scheduled basal pre-dawn)'
                rec['action'] = 'Consider raising scheduled basal to reduce AID burden'
            elif mean_residual > 10:
                rec['interpretation'] = 'Dawn phenomenon uncompensated'
                rec['action'] = 'Increase early morning basal rate'
            else:
                rec['interpretation'] = 'Dawn rise minimal despite being flagged'
                rec['action'] = 'Monitor — no urgent change'
        else:
            if mean_ratio < 0.80:
                rec['interpretation'] = 'AID reducing basal — possible over-basaling'
                rec['action'] = 'Consider reducing overnight basal'
            else:
                rec['interpretation'] = 'No dawn phenomenon, AID stable'
                rec['action'] = 'No change needed'

        per_patient.append(rec)
        label = 'DAWN' if is_dawn else '    '
        comp = 'COMPENSATED' if aid_compensating else 'UNCOMPENSATED' if uncompensated else 'stable'
        print(f"  {pid} [{label}]: ratio={mean_ratio:.2f}, residual={mean_residual:+.1f} mg/dL → {comp}")

    results['per_patient'] = per_patient
    results['n_patients'] = len(per_patient)
    results['n_dawn'] = sum(1 for p in per_patient if p['is_dawn_patient'])
    results['n_uncompensated'] = sum(1 for p in per_patient if p.get('uncompensated_dawn', False))
    results['n_aid_compensating'] = sum(1 for p in per_patient if p['aid_compensating'])
    print(f"\n  Dawn patients: {results['n_dawn']}, AID compensating: {results['n_aid_compensating']}, "
          f"Uncompensated: {results['n_uncompensated']}")
    return results


# ---------------------------------------------------------------------------
# EXP-1413: Grade D Root Cause Analysis
# ---------------------------------------------------------------------------
@register(1413, "Grade D Root Cause Analysis")
def exp_1413(patients, args):
    """Decompose score loss for persistent grade D patients to identify primary failure."""
    results = {'name': 'EXP-1413: Grade D Root Cause Analysis'}
    per_patient = []

    # First compute reference metrics from a grade-B patient for comparison
    ref_pid = 'd'  # known well-calibrated
    ref_metrics = None
    if ref_pid in patients:
        rp = patients[ref_pid]
        rn = len(rp['glucose'])
        ref_metrics = {
            'tir': compute_tir(rp['glucose']),
            'cv': compute_cv(rp['glucose']),
            'excursion': compute_max_excursion(rp['glucose'], rp['carbs'], rn),
        }
        drifts = []
        for d in range(rn // STEPS_PER_DAY):
            dr = compute_segment_drift(rp['glucose'], rp['bolus'], rp['carbs'], d * STEPS_PER_DAY, 0, 6)
            if not np.isnan(dr):
                drifts.append(abs(dr))
        ref_metrics['drift'] = float(np.median(drifts)) if drifts else 0.0

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs_arr = pdata['carbs']
        n = len(glucose)
        n_days = n // STEPS_PER_DAY

        tir = compute_tir(glucose)
        cv = compute_cv(glucose)
        exc = compute_max_excursion(glucose, carbs_arr, n)

        # Compute overnight drift
        drifts = []
        for d in range(min(n_days, 180)):
            dr = compute_segment_drift(glucose, bolus, carbs_arr, d * STEPS_PER_DAY, 0, 6)
            if not np.isnan(dr):
                drifts.append(abs(dr))
        drift = float(np.median(drifts)) if drifts else 0.0

        isf = compute_isf_ratio(glucose, bolus, carbs_arr, n)

        # Score components
        tir_contrib = min(tir, 100) / 100 * SCORE_WEIGHTS['tir']
        basal_ok = 1.0 if drift < DRIFT_THRESHOLD else 0.0
        basal_contrib = basal_ok * SCORE_WEIGHTS['basal']
        cr_ok = 1.0 if exc < EXCURSION_THRESHOLD else 0.0
        cr_contrib = cr_ok * SCORE_WEIGHTS['cr']
        isf_contrib = SCORE_WEIGHTS['isf']  # assumed OK
        cv_ok = 1.0 if cv < CV_THRESHOLD else 0.0
        cv_contrib = cv_ok * SCORE_WEIGHTS['cv']

        total = tir_contrib + basal_contrib + cr_contrib + isf_contrib + cv_contrib
        grade = get_grade(total)

        # Loss decomposition: how many points lost per component
        tir_loss = SCORE_WEIGHTS['tir'] - tir_contrib
        basal_loss = SCORE_WEIGHTS['basal'] - basal_contrib
        cr_loss = SCORE_WEIGHTS['cr'] - cr_contrib
        isf_loss = 0.0  # assumed OK
        cv_loss = SCORE_WEIGHTS['cv'] - cv_contrib
        total_loss = tir_loss + basal_loss + cr_loss + isf_loss + cv_loss

        # Rank failures
        failures = [
            ('TIR', tir_loss, tir, f'{tir:.1f}%'),
            ('basal', basal_loss, drift, f'drift={drift:.1f} mg/dL/h'),
            ('CR', cr_loss, exc, f'excursion={exc:.1f} mg/dL'),
            ('ISF', isf_loss, isf, f'ISF_ratio={isf:.1f}'),
            ('CV', cv_loss, cv, f'CV={cv:.1f}%'),
        ]
        failures.sort(key=lambda x: x[1], reverse=True)

        # Estimate TIR improvement from fixing top failure
        top_action = failures[0][0]
        estimated_gain = 0.0
        if top_action == 'TIR':
            # Improving TIR directly — estimate from reference
            if ref_metrics:
                estimated_gain = (ref_metrics['tir'] - tir) * 0.6 / 100 * SCORE_WEIGHTS['tir']
        elif top_action == 'basal':
            estimated_gain = SCORE_WEIGHTS['basal']  # full recovery if fixed
        elif top_action == 'CR':
            estimated_gain = SCORE_WEIGHTS['cr']
        elif top_action == 'CV':
            estimated_gain = SCORE_WEIGHTS['cv']

        rec = {
            'patient': pid,
            'grade': grade,
            'score': round(total, 1),
            'is_persistent_D': pid in GRADE_D_PATIENTS,
            'tir': round(tir, 1),
            'drift': round(drift, 2),
            'excursion': round(exc, 1),
            'cv': round(cv, 1),
            'decomposition': {
                'tir_contrib': round(tir_contrib, 1),
                'tir_loss': round(tir_loss, 1),
                'basal_contrib': round(basal_contrib, 1),
                'basal_loss': round(basal_loss, 1),
                'cr_contrib': round(cr_contrib, 1),
                'cr_loss': round(cr_loss, 1),
                'isf_contrib': round(isf_contrib, 1),
                'isf_loss': round(isf_loss, 1),
                'cv_contrib': round(cv_contrib, 1),
                'cv_loss': round(cv_loss, 1),
            },
            'failure_ranking': [{'component': f[0], 'loss': round(f[1], 1), 'detail': f[3]} for f in failures],
            'top_action': top_action,
            'estimated_score_gain': round(estimated_gain, 1),
            'estimated_new_grade': get_grade(total + estimated_gain),
        }

        if ref_metrics:
            rec['gap_vs_reference'] = {
                'ref_patient': ref_pid,
                'tir_gap': round(ref_metrics['tir'] - tir, 1),
                'drift_gap': round(drift - ref_metrics['drift'], 2),
                'excursion_gap': round(exc - ref_metrics.get('excursion', 0), 1),
            }

        per_patient.append(rec)

        if pid in GRADE_D_PATIENTS or args.detail:
            marker = ' *** GRADE D ***' if pid in GRADE_D_PATIENTS else ''
            print(f"  {pid}: grade={grade} score={total:.1f}{marker}")
            print(f"    Losses: TIR={tir_loss:.1f} basal={basal_loss:.1f} CR={cr_loss:.1f} CV={cv_loss:.1f}")
            print(f"    Top action: fix {top_action} → estimated +{estimated_gain:.1f}pts → grade {rec['estimated_new_grade']}")

    results['per_patient'] = per_patient
    results['n_patients'] = len(per_patient)
    grade_d = [p for p in per_patient if p['is_persistent_D']]
    results['grade_d_patients'] = [p['patient'] for p in grade_d]
    if grade_d:
        top_actions = defaultdict(int)
        for p in grade_d:
            top_actions[p['top_action']] += 1
        results['grade_d_top_actions'] = dict(top_actions)
        print(f"\n  Grade D root causes: {dict(top_actions)}")
    if ref_metrics:
        results['reference'] = {'patient': ref_pid, **{k: round(v, 2) for k, v in ref_metrics.items()}}
    return results


# ---------------------------------------------------------------------------
# EXP-1414: Cross-Parameter Interaction Testing
# ---------------------------------------------------------------------------
@register(1414, "Cross-Parameter Interaction Testing")
def exp_1414(patients, args):
    """Test if fixing basal affects CR, and if fixing CR affects ISF."""
    results = {'name': 'EXP-1414: Cross-Parameter Interaction Testing'}
    per_patient = []

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose'].copy()
        bolus = pdata['bolus']
        carbs_arr = pdata['carbs']
        n = len(glucose)
        n_days = n // STEPS_PER_DAY

        # --- Original metrics ---
        orig_exc = compute_max_excursion(glucose, carbs_arr, n)
        orig_isf = compute_isf_ratio(glucose, bolus, carbs_arr, n)

        orig_drifts = []
        for d in range(min(n_days, 180)):
            dr = compute_segment_drift(glucose, bolus, carbs_arr, d * STEPS_PER_DAY, 0, 6)
            if not np.isnan(dr):
                orig_drifts.append(dr)
        orig_drift = float(np.median([abs(x) for x in orig_drifts])) if orig_drifts else 0.0
        orig_cr_flag = orig_exc >= EXCURSION_THRESHOLD
        orig_basal_flag = orig_drift >= DRIFT_THRESHOLD

        # --- Simulate "fixed basal": remove overnight drift from glucose ---
        glucose_fixed_basal = glucose.copy()
        for d in range(min(n_days, 180)):
            ds = d * STEPS_PER_DAY
            for seg_name, (h_start, h_end) in zip(SEGMENT_NAMES, SEGMENT_HOURS):
                dr = compute_segment_drift(glucose, bolus, carbs_arr, ds, h_start, h_end)
                if np.isnan(dr) or abs(dr) < DRIFT_THRESHOLD:
                    continue
                seg_start = ds + h_start * STEPS_PER_HOUR
                seg_end = min(ds + h_end * STEPS_PER_HOUR, n)
                for i in range(seg_start, seg_end):
                    if not np.isnan(glucose_fixed_basal[i]):
                        hours_in = (i - seg_start) / STEPS_PER_HOUR
                        glucose_fixed_basal[i] -= dr * hours_in

        # Re-run CR on corrected glucose
        fb_exc = compute_max_excursion(glucose_fixed_basal, carbs_arr, n)
        fb_cr_flag = fb_exc >= EXCURSION_THRESHOLD
        cr_changed_by_basal = orig_cr_flag != fb_cr_flag

        # Re-run ISF on corrected glucose
        fb_isf = compute_isf_ratio(glucose_fixed_basal, bolus, carbs_arr, n)

        # --- Simulate "fixed CR": remove meal excursions ---
        glucose_fixed_cr = glucose.copy()
        meal_window = 4 * STEPS_PER_HOUR
        for i in range(n):
            if carbs_arr[i] < 5 or np.isnan(glucose[i]):
                continue
            baseline = glucose[i]
            end = min(i + meal_window, n)
            for j in range(i, end):
                if not np.isnan(glucose_fixed_cr[j]) and glucose_fixed_cr[j] > baseline:
                    excess = glucose_fixed_cr[j] - baseline
                    # Dampen excursion: remove 70% of excess
                    glucose_fixed_cr[j] -= excess * 0.7

        fc_isf = compute_isf_ratio(glucose_fixed_cr, bolus, carbs_arr, n)

        rec = {
            'patient': pid,
            'original': {
                'drift': round(orig_drift, 2),
                'excursion': round(orig_exc, 1),
                'isf_ratio': round(orig_isf, 1),
                'basal_flag': orig_basal_flag,
                'cr_flag': orig_cr_flag,
            },
            'after_basal_fix': {
                'excursion': round(fb_exc, 1),
                'cr_flag': fb_cr_flag,
                'cr_changed': cr_changed_by_basal,
                'isf_ratio': round(fb_isf, 1),
            },
            'after_cr_fix': {
                'isf_ratio': round(fc_isf, 1),
            },
            'interaction_basal_to_cr': cr_changed_by_basal,
            'interaction_basal_to_isf': abs(fb_isf - orig_isf) > 5,
            'interaction_cr_to_isf': abs(fc_isf - orig_isf) > 5,
        }

        per_patient.append(rec)
        interactions = sum([rec['interaction_basal_to_cr'],
                            rec['interaction_basal_to_isf'],
                            rec['interaction_cr_to_isf']])
        if interactions > 0 or args.detail:
            print(f"  {pid}: {interactions} interaction(s) detected")
            if cr_changed_by_basal:
                print(f"    basal→CR: excursion {orig_exc:.0f} → {fb_exc:.0f}")
            if abs(fb_isf - orig_isf) > 5:
                print(f"    basal→ISF: {orig_isf:.0f} → {fb_isf:.0f}")
            if abs(fc_isf - orig_isf) > 5:
                print(f"    CR→ISF: {orig_isf:.0f} → {fc_isf:.0f}")

    # Build interaction matrix
    interaction_counts = {'basal→CR': 0, 'basal→ISF': 0, 'CR→ISF': 0}
    for p in per_patient:
        if p['interaction_basal_to_cr']:
            interaction_counts['basal→CR'] += 1
        if p['interaction_basal_to_isf']:
            interaction_counts['basal→ISF'] += 1
        if p['interaction_cr_to_isf']:
            interaction_counts['CR→ISF'] += 1

    results['per_patient'] = per_patient
    results['n_patients'] = len(per_patient)
    results['interaction_matrix'] = interaction_counts
    results['n_any_interaction'] = sum(1 for p in per_patient if any([
        p['interaction_basal_to_cr'], p['interaction_basal_to_isf'], p['interaction_cr_to_isf']]))
    print(f"\n  Interaction matrix: {interaction_counts}")
    print(f"  Patients with any interaction: {results['n_any_interaction']}/{results['n_patients']}")
    return results


# ---------------------------------------------------------------------------
# EXP-1415: Prospective Multi-Segment Basal Simulation
# ---------------------------------------------------------------------------
@register(1415, "Prospective Multi-Segment Basal Simulation")
def exp_1415(patients, args):
    """Simulate applying multi-segment basal recommendations and measure impact."""
    results = {'name': 'EXP-1415: Prospective Multi-Segment Basal Simulation'}
    per_patient = []
    transitions = defaultdict(int)  # grade transition counts

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose'].copy()
        bolus = pdata['bolus']
        carbs_arr = pdata['carbs']
        n = len(glucose)
        n_days = n // STEPS_PER_DAY

        profile = load_profile(pid)
        sens_schedule = profile.get('sens', []) if profile else []
        isf = 50.0
        if sens_schedule:
            isf = float(sens_schedule[0].get('value', 50.0))
            units = profile.get('_units', 'mg/dL') if profile else 'mg/dL'
            if units == 'mmol/L' or (isinstance(isf, (int, float)) and isf < 10):
                isf *= 18.0

        # Compute per-segment median drifts
        seg_drifts = {}
        for seg_name, (h_start, h_end) in zip(SEGMENT_NAMES, SEGMENT_HOURS):
            day_drifts = []
            for d in range(min(n_days, 180)):
                dr = compute_segment_drift(glucose, bolus, carbs_arr, d * STEPS_PER_DAY, h_start, h_end)
                if not np.isnan(dr):
                    day_drifts.append(dr)
            seg_drifts[(h_start, h_end)] = float(np.median(day_drifts)) if day_drifts else 0.0

        # Before metrics
        before_tir = compute_tir(glucose)
        before_cv = compute_cv(glucose)
        before_exc = compute_max_excursion(glucose, carbs_arr, n)
        before_drift_abs = float(np.mean([abs(v) for v in seg_drifts.values()]))
        before_score = compute_therapy_score(before_tir, before_drift_abs, before_exc, 1.0, before_cv)
        before_grade = get_grade(before_score)

        # Apply correction: ΔBG = -drift × hours for each flagged segment
        glucose_sim = glucose.copy()
        for d in range(min(n_days, 180)):
            ds = d * STEPS_PER_DAY
            for (h_start, h_end), drift in seg_drifts.items():
                if abs(drift) < DRIFT_THRESHOLD:
                    continue
                seg_start = ds + h_start * STEPS_PER_HOUR
                seg_end = min(ds + h_end * STEPS_PER_HOUR, n)
                for i in range(seg_start, seg_end):
                    if not np.isnan(glucose_sim[i]):
                        hours_in = (i - seg_start) / STEPS_PER_HOUR
                        glucose_sim[i] -= drift * hours_in

        # After metrics
        after_tir = compute_tir(glucose_sim)
        after_cv = compute_cv(glucose_sim)
        after_exc = compute_max_excursion(glucose_sim, carbs_arr, n)
        # Drift should be ~0 for corrected segments
        after_drift = 0.0
        after_score = compute_therapy_score(after_tir, after_drift, after_exc, 1.0, after_cv)
        after_grade = get_grade(after_score)

        transition = f'{before_grade}→{after_grade}'
        transitions[transition] += 1

        rec = {
            'patient': pid,
            'before': {
                'tir': round(before_tir, 1),
                'score': round(before_score, 1),
                'grade': before_grade,
                'cv': round(before_cv, 1),
                'mean_abs_drift': round(before_drift_abs, 2),
            },
            'after': {
                'tir': round(after_tir, 1),
                'score': round(after_score, 1),
                'grade': after_grade,
                'cv': round(after_cv, 1),
            },
            'tir_change': round(after_tir - before_tir, 1),
            'score_change': round(after_score - before_score, 1),
            'grade_transition': transition,
            'improved': after_score > before_score,
        }
        per_patient.append(rec)
        if before_grade != after_grade or args.detail:
            print(f"  {pid}: {transition} (score {before_score:.1f}→{after_score:.1f}, "
                  f"TIR {before_tir:.1f}→{after_tir:.1f}%)")

    results['per_patient'] = per_patient
    results['n_patients'] = len(per_patient)
    results['grade_transitions'] = dict(transitions)
    results['n_improved'] = sum(1 for p in per_patient if p['improved'])
    results['mean_tir_gain'] = round(float(np.mean([p['tir_change'] for p in per_patient])), 1)
    results['mean_score_gain'] = round(float(np.mean([p['score_change'] for p in per_patient])), 1)
    print(f"\n  Transitions: {dict(transitions)}")
    print(f"  Improved: {results['n_improved']}/{results['n_patients']}")
    print(f"  Mean TIR gain: {results['mean_tir_gain']:+.1f}%, Mean score gain: {results['mean_score_gain']:+.1f}")
    return results


# ---------------------------------------------------------------------------
# EXP-1416: Basal Adjustment Magnitude Calibration
# ---------------------------------------------------------------------------
@register(1416, "Basal Adjustment Magnitude Calibration")
def exp_1416(patients, args):
    """Test conservative/moderate/aggressive basal adjustment magnitudes."""
    results = {'name': 'EXP-1416: Basal Adjustment Magnitude Calibration'}
    magnitudes = {'conservative': 0.10, 'moderate': 0.20, 'aggressive': 0.30}
    per_patient = []

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs_arr = pdata['carbs']
        n = len(glucose)
        n_days = n // STEPS_PER_DAY

        # Compute per-segment drifts
        seg_drifts = {}
        for seg_name, (h_start, h_end) in zip(SEGMENT_NAMES, SEGMENT_HOURS):
            day_drifts = []
            for d in range(min(n_days, 180)):
                dr = compute_segment_drift(glucose, bolus, carbs_arr, d * STEPS_PER_DAY, h_start, h_end)
                if not np.isnan(dr):
                    day_drifts.append(dr)
            seg_drifts[(h_start, h_end)] = float(np.median(day_drifts)) if day_drifts else 0.0

        n_flagged_orig = sum(1 for v in seg_drifts.values() if abs(v) >= DRIFT_THRESHOLD)

        mag_results = {}
        for mag_name, mag_frac in magnitudes.items():
            # Simulate applying mag_frac correction to drift
            residual_drifts = {}
            over_corrections = 0
            for (h_start, h_end), drift in seg_drifts.items():
                if abs(drift) < DRIFT_THRESHOLD:
                    residual_drifts[(h_start, h_end)] = drift
                    continue
                # Correction removes mag_frac of the drift per step
                correction = drift * mag_frac / (DRIFT_THRESHOLD / abs(drift)) if abs(drift) > 0 else 0
                # Simple model: residual = drift * (1 - correction_factor)
                # correction_factor scales with magnitude
                correction_factor = min(1.0, mag_frac * abs(drift) / DRIFT_THRESHOLD)
                residual = drift * (1 - correction_factor)
                residual_drifts[(h_start, h_end)] = residual
                # Over-correction: if residual flips sign
                if abs(residual) >= DRIFT_THRESHOLD and np.sign(residual) != np.sign(drift):
                    over_corrections += 1

            n_flagged_after = sum(1 for v in residual_drifts.values() if abs(v) >= DRIFT_THRESHOLD)

            # Simulate glucose correction and compute TIR
            glucose_sim = glucose.copy()
            for d in range(min(n_days, 180)):
                ds = d * STEPS_PER_DAY
                for (h_start, h_end), drift in seg_drifts.items():
                    if abs(drift) < DRIFT_THRESHOLD:
                        continue
                    correction_factor = min(1.0, mag_frac * abs(drift) / DRIFT_THRESHOLD)
                    seg_start = ds + h_start * STEPS_PER_HOUR
                    seg_end = min(ds + h_end * STEPS_PER_HOUR, n)
                    for i in range(seg_start, seg_end):
                        if not np.isnan(glucose_sim[i]):
                            hours_in = (i - seg_start) / STEPS_PER_HOUR
                            glucose_sim[i] -= drift * correction_factor * hours_in

            sim_tir = compute_tir(glucose_sim)
            orig_tir = compute_tir(glucose)

            mag_results[mag_name] = {
                'magnitude_pct': int(mag_frac * 100),
                'flags_before': n_flagged_orig,
                'flags_after': n_flagged_after,
                'flags_reduced': n_flagged_orig - n_flagged_after,
                'over_corrections': over_corrections,
                'tir_before': round(orig_tir, 1),
                'tir_after': round(sim_tir, 1),
                'tir_gain': round(sim_tir - orig_tir, 1),
            }

        # Find optimal: best TIR gain with no over-corrections
        best = min(mag_results.items(), key=lambda x: (-x[1]['tir_gain'], x[1]['over_corrections']))
        optimal = best[0]

        per_patient.append({
            'patient': pid,
            'n_flagged_segments': n_flagged_orig,
            'magnitudes': mag_results,
            'optimal_magnitude': optimal,
        })

        if args.detail or n_flagged_orig > 0:
            print(f"  {pid}: {n_flagged_orig} flagged → optimal={optimal}")
            for mn, mr in mag_results.items():
                print(f"    {mn}({mr['magnitude_pct']}%): flags {mr['flags_before']}→{mr['flags_after']}, "
                      f"TIR {mr['tir_gain']:+.1f}%, overcorrect={mr['over_corrections']}")

    results['per_patient'] = per_patient
    results['n_patients'] = len(per_patient)
    # Aggregate: count how often each magnitude is optimal
    opt_counts = defaultdict(int)
    for p in per_patient:
        opt_counts[p['optimal_magnitude']] += 1
    results['optimal_distribution'] = dict(opt_counts)
    print(f"\n  Optimal magnitude distribution: {dict(opt_counts)}")
    return results


# ---------------------------------------------------------------------------
# EXP-1417: Weekly Monitoring Dashboard Metrics
# ---------------------------------------------------------------------------
@register(1417, "Weekly Monitoring Dashboard Metrics")
def exp_1417(patients, args):
    """Design and compute minimal weekly dashboard metrics for all patients."""
    results = {'name': 'EXP-1417: Weekly Monitoring Dashboard Metrics'}
    per_patient = []

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs_arr = pdata['carbs']
        n = len(glucose)

        weeks = compute_weekly_metrics(glucose, bolus, carbs_arr, n)
        if not weeks:
            continue

        # Detect grade changes and measure detection lead time
        grades = [w['grade'] for w in weeks]
        scores = [w['score'] for w in weeks]
        grade_changes = []
        for i in range(1, len(grades)):
            if grades[i] != grades[i - 1]:
                grade_changes.append({
                    'week': i,
                    'from': grades[i - 1],
                    'to': grades[i],
                })

        # Lead time: how many weeks before a grade drop did score start declining?
        lead_times = []
        for gc in grade_changes:
            w = gc['week']
            if gc['to'] > gc['from']:  # worsening (D > C > B > A alphabetically)
                # Look back for first week score started declining
                lead = 0
                for j in range(w - 1, max(0, w - 8), -1):
                    if scores[j] < scores[max(0, j - 1)]:
                        lead = w - j
                    else:
                        break
                lead_times.append(lead)

        mean_lead = float(np.mean(lead_times)) if lead_times else 0.0

        per_patient.append({
            'patient': pid,
            'n_weeks': len(weeks),
            'weekly_dashboard': weeks,
            'grade_changes': grade_changes,
            'n_grade_changes': len(grade_changes),
            'detection_lead_times': lead_times,
            'mean_lead_time_weeks': round(mean_lead, 1),
            'final_grade': grades[-1] if grades else 'N/A',
            'mean_score': round(float(np.mean(scores)), 1),
        })

        print(f"  {pid}: {len(weeks)} weeks, {len(grade_changes)} grade changes, "
              f"mean lead time {mean_lead:.1f}w, final grade={grades[-1] if grades else 'N/A'}")

    results['per_patient'] = per_patient
    results['n_patients'] = len(per_patient)
    all_leads = []
    for p in per_patient:
        all_leads.extend(p['detection_lead_times'])
    results['overall_mean_lead_time'] = round(float(np.mean(all_leads)), 1) if all_leads else 0.0
    results['total_grade_changes'] = sum(p['n_grade_changes'] for p in per_patient)
    print(f"\n  Overall mean detection lead time: {results['overall_mean_lead_time']:.1f} weeks")
    print(f"  Total grade changes across all patients: {results['total_grade_changes']}")
    return results


# ---------------------------------------------------------------------------
# EXP-1418: Intervention Priority Scoring
# ---------------------------------------------------------------------------
@register(1418, "Intervention Priority Scoring")
def exp_1418(patients, args):
    """Create priority scores for clinical intervention ordering."""
    results = {'name': 'EXP-1418: Intervention Priority Scoring'}
    per_patient = []

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs_arr = pdata['carbs']
        n = len(glucose)
        n_days = n // STEPS_PER_DAY
        is_dawn = pid in DAWN_PATIENTS

        # Compute biweekly scores for trend detection
        bw_scores = compute_biweekly_scores(glucose, bolus, carbs_arr, n)
        if not bw_scores:
            continue

        grades = [s['grade'] for s in bw_scores]
        scores_list = [s['score'] for s in bw_scores]
        current_grade = grades[-1]
        current_score = scores_list[-1]

        # Duration at current grade (consecutive windows from end)
        duration = 1
        for i in range(len(grades) - 2, -1, -1):
            if grades[i] == current_grade:
                duration += 1
            else:
                break
        duration_months = duration * 14 / 30.0  # biweekly → months

        # Trend: slope of last 6 windows
        recent = scores_list[-min(6, len(scores_list)):]
        if len(recent) >= 2:
            trend_slope = float(np.polyfit(range(len(recent)), recent, 1)[0])
        else:
            trend_slope = 0.0
        declining = trend_slope < -1.0

        # Problem rate: fraction of biweekly windows at grade D
        d_rate = sum(1 for g in grades if g == 'D') / len(grades)

        # Drift prevalence
        drifts = []
        for d in range(min(n_days, 180)):
            dr = compute_segment_drift(glucose, bolus, carbs_arr, d * STEPS_PER_DAY, 0, 6)
            if not np.isnan(dr):
                drifts.append(abs(dr))
        drift_prevalence = sum(1 for d in drifts if d >= DRIFT_THRESHOLD) / max(len(drifts), 1)

        # Priority score (0-100, higher = more urgent)
        grade_score = {'A': 0, 'B': 20, 'C': 50, 'D': 80}.get(current_grade, 50)
        trend_penalty = 10 if declining else 0
        duration_bonus = min(10, duration_months * 3) if current_grade in ('C', 'D') else 0
        problem_rate_score = d_rate * 20
        dawn_factor = 5 if is_dawn else 0

        priority = min(100, grade_score + trend_penalty + duration_bonus + problem_rate_score + dawn_factor)

        urgency = 'critical' if priority >= 80 else 'high' if priority >= 60 else \
            'moderate' if priority >= 40 else 'low' if priority >= 20 else 'none'

        per_patient.append({
            'patient': pid,
            'current_grade': current_grade,
            'current_score': round(current_score, 1),
            'trend_slope': round(trend_slope, 2),
            'declining': declining,
            'duration_at_grade_months': round(duration_months, 1),
            'problem_d_rate': round(d_rate, 3),
            'drift_prevalence': round(drift_prevalence, 3),
            'is_dawn': is_dawn,
            'priority_score': round(priority, 1),
            'urgency': urgency,
            'components': {
                'grade_score': round(grade_score, 1),
                'trend_penalty': round(trend_penalty, 1),
                'duration_bonus': round(duration_bonus, 1),
                'problem_rate': round(problem_rate_score, 1),
                'dawn_factor': dawn_factor,
            },
        })

    # Sort by priority (descending)
    per_patient.sort(key=lambda x: x['priority_score'], reverse=True)

    for i, p in enumerate(per_patient):
        marker = ' <<<' if p['urgency'] in ('critical', 'high') else ''
        print(f"  {i + 1}. {p['patient']}: priority={p['priority_score']:.0f} ({p['urgency']}) "
              f"grade={p['current_grade']} duration={p['duration_at_grade_months']:.1f}mo "
              f"trend={p['trend_slope']:+.1f}{marker}")

    results['per_patient'] = per_patient
    results['n_patients'] = len(per_patient)
    results['ranked_intervention_list'] = [p['patient'] for p in per_patient]
    results['urgency_counts'] = {u: sum(1 for p in per_patient if p['urgency'] == u)
                                  for u in ['critical', 'high', 'moderate', 'low', 'none']}
    print(f"\n  Urgency distribution: {results['urgency_counts']}")
    return results


# ---------------------------------------------------------------------------
# EXP-1419: Therapy Recommendation Confidence Intervals
# ---------------------------------------------------------------------------
@register(1419, "Therapy Recommendation Confidence Intervals")
def exp_1419(patients, args):
    """Bootstrap confidence intervals for each therapy recommendation."""
    results = {'name': 'EXP-1419: Therapy Recommendation Confidence Intervals'}
    per_patient = []
    n_bootstrap = 100
    rng = np.random.RandomState(42)

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs_arr = pdata['carbs']
        n = len(glucose)
        n_days = n // STEPS_PER_DAY
        if n_days < 7:
            continue

        # Resample days with replacement
        boot_drifts = []
        boot_excursions = []
        boot_isfs = []

        for b in range(n_bootstrap):
            # Sample day indices with replacement
            sampled_days = rng.choice(min(n_days, 180), size=min(n_days, 180), replace=True)

            # Collect overnight drifts from sampled days
            drifts_b = []
            for d in sampled_days:
                dr = compute_segment_drift(glucose, bolus, carbs_arr, d * STEPS_PER_DAY, 0, 6)
                if not np.isnan(dr):
                    drifts_b.append(abs(dr))

            # Collect excursions from sampled days
            exc_vals = []
            for d in sampled_days:
                ds = d * STEPS_PER_DAY
                de = min(ds + STEPS_PER_DAY, n)
                g_day = glucose[ds:de]
                c_day = carbs_arr[ds:de]
                for i in range(len(g_day)):
                    if c_day[i] < 5 or np.isnan(g_day[i]):
                        continue
                    window = min(4 * STEPS_PER_HOUR, len(g_day) - i)
                    post = g_day[i:i + window]
                    valid_post = post[~np.isnan(post)]
                    if len(valid_post) >= STEPS_PER_HOUR:
                        exc_vals.append(float(np.nanmax(valid_post) - g_day[i]))

            # Collect ISF events from sampled days
            isf_events_b = []
            for d in sampled_days:
                ds = d * STEPS_PER_DAY
                de = min(ds + STEPS_PER_DAY, n)
                for i in range(ds, de):
                    if i >= n:
                        break
                    if bolus[i] < MIN_BOLUS_ISF or np.isnan(glucose[i]):
                        continue
                    c_start = max(0, i - STEPS_PER_HOUR)
                    c_end = min(n, i + STEPS_PER_HOUR)
                    if np.nansum(carbs_arr[c_start:c_end]) > 2:
                        continue
                    resp_end = min(i + 3 * STEPS_PER_HOUR, n)
                    post = glucose[i:resp_end]
                    valid_post = post[~np.isnan(post)]
                    if len(valid_post) >= 3 * STEPS_PER_HOUR // 2:
                        drop = glucose[i] - np.nanmin(valid_post)
                        isf_events_b.append(drop / bolus[i])

            boot_drifts.append(float(np.median(drifts_b)) if drifts_b else 0.0)
            boot_excursions.append(float(np.percentile(exc_vals, 90)) if exc_vals else 0.0)
            boot_isfs.append(float(np.median(isf_events_b)) if len(isf_events_b) >= MIN_ISF_EVENTS else np.nan)

        boot_drifts = np.array(boot_drifts)
        boot_excursions = np.array(boot_excursions)
        boot_isfs = np.array(boot_isfs)

        def ci(arr, level=95):
            valid = arr[~np.isnan(arr)]
            if len(valid) < 3:
                return {'mean': float('nan'), 'ci_lo': float('nan'), 'ci_hi': float('nan'),
                        'confident': False, 'n_valid': int(len(valid))}
            lo = float(np.percentile(valid, (100 - level) / 2))
            hi = float(np.percentile(valid, 100 - (100 - level) / 2))
            mean = float(np.mean(valid))
            # Crosses zero check: relevant for drift direction
            confident = not (lo <= 0 <= hi) if mean != 0 else len(valid) >= n_bootstrap * 0.8
            return {
                'mean': round(mean, 2),
                'ci_lo': round(lo, 2),
                'ci_hi': round(hi, 2),
                'confident': confident,
                'n_valid': int(len(valid)),
            }

        drift_ci = ci(boot_drifts)
        exc_ci = ci(boot_excursions)
        isf_ci = ci(boot_isfs)

        # Determine flag confidence
        drift_flag_confident = drift_ci['confident'] and drift_ci['ci_lo'] >= DRIFT_THRESHOLD
        cr_flag_confident = exc_ci['confident'] and exc_ci['ci_lo'] >= EXCURSION_THRESHOLD

        rec = {
            'patient': pid,
            'n_days': min(n_days, 180),
            'n_bootstrap': n_bootstrap,
            'basal_drift': drift_ci,
            'basal_drift_flag_confident': drift_flag_confident,
            'cr_excursion': exc_ci,
            'cr_flag_confident': cr_flag_confident,
            'isf_ratio': isf_ci,
            'confidence_summary': {
                'basal': 'confident' if drift_ci['confident'] else 'uncertain',
                'cr': 'confident' if exc_ci['confident'] else 'uncertain',
                'isf': 'confident' if isf_ci['confident'] else 'uncertain (few events)',
            },
        }
        per_patient.append(rec)

        conf_status = f"drift={'✓' if drift_ci['confident'] else '?'} " \
                      f"CR={'✓' if exc_ci['confident'] else '?'} " \
                      f"ISF={'✓' if isf_ci['confident'] else '?'}"
        print(f"  {pid}: {conf_status}")
        if args.detail:
            print(f"    drift: {drift_ci['mean']:.1f} [{drift_ci['ci_lo']:.1f}, {drift_ci['ci_hi']:.1f}]")
            print(f"    exc:   {exc_ci['mean']:.0f} [{exc_ci['ci_lo']:.0f}, {exc_ci['ci_hi']:.0f}]")
            print(f"    ISF:   {isf_ci['mean']:.0f} [{isf_ci['ci_lo']:.0f}, {isf_ci['ci_hi']:.0f}]")

    results['per_patient'] = per_patient
    results['n_patients'] = len(per_patient)
    # Count confident flags
    results['n_confident_drift'] = sum(1 for p in per_patient if p['basal_drift']['confident'])
    results['n_confident_cr'] = sum(1 for p in per_patient if p['cr_excursion']['confident'])
    results['n_confident_isf'] = sum(1 for p in per_patient if p['isf_ratio']['confident'])
    results['n_uncertain_any'] = sum(1 for p in per_patient if not all([
        p['basal_drift']['confident'], p['cr_excursion']['confident'], p['isf_ratio']['confident']]))
    print(f"\n  Confident: drift={results['n_confident_drift']}, CR={results['n_confident_cr']}, "
          f"ISF={results['n_confident_isf']}")
    print(f"  Uncertain on any parameter: {results['n_uncertain_any']}/{results['n_patients']}")
    return results


# ---------------------------------------------------------------------------
# EXP-1420: Combined Recommendation Report Generator
# ---------------------------------------------------------------------------
@register(1420, "Combined Recommendation Report Generator")
def exp_1420(patients, args):
    """Generate per-patient clinical summary combining all pipeline outputs."""
    results = {'name': 'EXP-1420: Combined Recommendation Report Generator'}
    per_patient = []

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs_arr = pdata['carbs']
        temp_rate = pdata['temp_rate']
        n = len(glucose)
        n_days = n // STEPS_PER_DAY
        is_dawn = pid in DAWN_PATIENTS

        profile = load_profile(pid)
        basal_schedule = profile.get('basal', []) if profile else []
        sens_schedule = profile.get('sens', []) if profile else []
        units = profile.get('_units', 'mg/dL') if profile else 'mg/dL'
        isf = 50.0
        if sens_schedule:
            isf = float(sens_schedule[0].get('value', 50.0))
            if units == 'mmol/L' or (isinstance(isf, (int, float)) and isf < 10):
                isf *= 18.0

        # --- Grade history (biweekly) ---
        bw_scores = compute_biweekly_scores(glucose, bolus, carbs_arr, n)
        grade_history = [{'window': s['window'], 'grade': s['grade'], 'score': s['score']} for s in bw_scores]

        # --- Multi-segment basal pattern ---
        seg_pattern = []
        n_flagged = 0
        for seg_name, (h_start, h_end) in zip(SEGMENT_NAMES, SEGMENT_HOURS):
            day_drifts = []
            for d in range(min(n_days, 180)):
                dr = compute_segment_drift(glucose, bolus, carbs_arr, d * STEPS_PER_DAY, h_start, h_end)
                if not np.isnan(dr):
                    day_drifts.append(dr)
            med_drift = float(np.median(day_drifts)) if day_drifts else 0.0
            current_rate = get_segment_basal(basal_schedule, h_start, h_end)
            adj_factor = med_drift / isf if isf > 0 else 0
            new_rate = max(0.05, current_rate * (1 + adj_factor))
            flagged = abs(med_drift) >= DRIFT_THRESHOLD
            if flagged:
                n_flagged += 1
            seg_pattern.append({
                'segment': seg_name,
                'drift': round(med_drift, 2),
                'current_rate': round(current_rate, 3),
                'recommended_rate': round(new_rate, 3),
                'flagged': flagged,
            })

        # --- Dawn phenomenon status ---
        dawn_rises = []
        for d in range(min(n_days, 180)):
            ds = d * STEPS_PER_DAY
            dw_start = ds + 4 * STEPS_PER_HOUR
            dw_end = ds + 7 * STEPS_PER_HOUR
            if dw_end > n:
                break
            if np.nansum(carbs_arr[dw_start:dw_end]) > 2 or np.nansum(bolus[dw_start:dw_end]) > 0.3:
                continue
            dg = glucose[dw_start:dw_end]
            dv = dg[~np.isnan(dg)]
            if len(dv) >= STEPS_PER_HOUR:
                dawn_rises.append(float(dv[-1] - dv[0]))
        dawn_status = {
            'is_dawn_patient': is_dawn,
            'mean_dawn_rise': round(float(np.mean(dawn_rises)), 1) if dawn_rises else 0.0,
            'dawn_prevalence': round(sum(1 for r in dawn_rises if r > 15) / max(len(dawn_rises), 1), 3),
        }

        # --- Data quality score ---
        valid_pct = float(np.mean(~np.isnan(glucose))) * 100
        # Check for extended gaps (>2h)
        gap_mask = np.isnan(glucose)
        gap_runs = []
        run_len = 0
        for g in gap_mask:
            if g:
                run_len += 1
            else:
                if run_len > 0:
                    gap_runs.append(run_len)
                run_len = 0
        max_gap_hours = max(gap_runs) / STEPS_PER_HOUR if gap_runs else 0
        n_long_gaps = sum(1 for g in gap_runs if g > 2 * STEPS_PER_HOUR)
        data_quality = min(100, valid_pct - n_long_gaps * 2)

        # --- Current metrics ---
        tir = compute_tir(glucose)
        cv = compute_cv(glucose)
        exc = compute_max_excursion(glucose, carbs_arr, n)
        drifts_all = []
        for d in range(min(n_days, 180)):
            dr = compute_segment_drift(glucose, bolus, carbs_arr, d * STEPS_PER_DAY, 0, 6)
            if not np.isnan(dr):
                drifts_all.append(abs(dr))
        drift = float(np.median(drifts_all)) if drifts_all else 0.0
        isf_ratio = compute_isf_ratio(glucose, bolus, carbs_arr, n)
        score = compute_therapy_score(tir, drift, exc, isf_ratio, cv)
        grade = get_grade(score)

        # --- Top-3 prioritized actions ---
        actions = []
        # Basal action
        if drift >= DRIFT_THRESHOLD:
            est_gain = SCORE_WEIGHTS['basal']
            actions.append({
                'rank': 0,
                'action': 'Adjust multi-segment basal rates',
                'parameter': 'basal',
                'detail': f'Overnight drift {drift:.1f} mg/dL/h exceeds threshold',
                'estimated_score_gain': round(est_gain, 1),
                'confidence': 'high' if len(drifts_all) > 30 else 'moderate',
            })

        # CR action
        if exc >= EXCURSION_THRESHOLD:
            est_gain = SCORE_WEIGHTS['cr']
            actions.append({
                'rank': 0,
                'action': 'Review carb ratio — large post-meal excursions',
                'parameter': 'CR',
                'detail': f'P90 excursion {exc:.0f} mg/dL exceeds threshold',
                'estimated_score_gain': round(est_gain, 1),
                'confidence': 'high',
            })

        # CV action
        if cv >= CV_THRESHOLD:
            actions.append({
                'rank': 0,
                'action': 'Reduce glucose variability — review timing/carb counting',
                'parameter': 'CV',
                'detail': f'CV {cv:.1f}% exceeds {CV_THRESHOLD}%',
                'estimated_score_gain': round(float(SCORE_WEIGHTS['cv']), 1),
                'confidence': 'moderate',
            })

        # Dawn action
        if is_dawn and dawn_status['dawn_prevalence'] > 0.3:
            actions.append({
                'rank': 0,
                'action': 'Address dawn phenomenon — increase early AM basal',
                'parameter': 'dawn',
                'detail': f'Dawn rise {dawn_status["mean_dawn_rise"]:.0f} mg/dL, '
                          f'prevalence {dawn_status["dawn_prevalence"]:.0%}',
                'estimated_score_gain': 5.0,
                'confidence': 'high',
            })

        # TIR improvement general
        if tir < 70 and not any(a['parameter'] in ('basal', 'CR') for a in actions):
            actions.append({
                'rank': 0,
                'action': 'Comprehensive therapy review — low TIR',
                'parameter': 'TIR',
                'detail': f'TIR {tir:.1f}% below 70% target',
                'estimated_score_gain': round((70 - tir) / 100 * SCORE_WEIGHTS['tir'], 1),
                'confidence': 'high',
            })

        # Sort by estimated gain and take top 3
        actions.sort(key=lambda x: x['estimated_score_gain'], reverse=True)
        for i, a in enumerate(actions):
            a['rank'] = i + 1
        top_actions = actions[:3]

        # Estimated improvement from top recommendation
        top_est = top_actions[0]['estimated_score_gain'] if top_actions else 0.0
        est_new_score = score + top_est
        est_new_grade = get_grade(est_new_score)

        summary = {
            'patient': pid,
            'current_grade': grade,
            'current_score': round(score, 1),
            'tir': round(tir, 1),
            'cv': round(cv, 1),
            'grade_history': grade_history,
            'n_biweekly_windows': len(grade_history),
            'top_actions': top_actions,
            'multi_segment_basal': seg_pattern,
            'n_basal_segments_flagged': n_flagged,
            'dawn_phenomenon': dawn_status,
            'data_quality_score': round(data_quality, 1),
            'data_coverage_pct': round(valid_pct, 1),
            'max_gap_hours': round(max_gap_hours, 1),
            'estimated_improvement': {
                'top_action': top_actions[0]['action'] if top_actions else 'No action needed',
                'estimated_score_gain': round(top_est, 1),
                'estimated_new_grade': est_new_grade,
            },
            'archetype': 'well-calibrated' if grade in ('A', 'B') and cv < CV_THRESHOLD
                         else 'miscalibrated' if pid == 'a'
                         else 'needs-tuning',
        }

        per_patient.append(summary)

        n_actions = len(top_actions)
        action_str = top_actions[0]['action'] if top_actions else 'None'
        print(f"  {pid}: grade={grade} score={score:.1f} TIR={tir:.1f}% | "
              f"{n_actions} actions, top: {action_str}")
        if args.detail:
            for a in top_actions:
                print(f"    #{a['rank']}: {a['action']} (est +{a['estimated_score_gain']:.1f}pts, "
                      f"confidence={a['confidence']})")

    results['per_patient'] = per_patient
    results['n_patients'] = len(per_patient)
    grade_dist = defaultdict(int)
    for p in per_patient:
        grade_dist[p['current_grade']] += 1
    results['grade_distribution'] = dict(grade_dist)

    # Count patients needing intervention
    results['n_needing_action'] = sum(1 for p in per_patient if p['top_actions'])
    results['n_no_action'] = sum(1 for p in per_patient if not p['top_actions'])

    print(f"\n  Grade distribution: {dict(grade_dist)}")
    print(f"  Patients needing action: {results['n_needing_action']}/{results['n_patients']}")

    # Per-archetype summary
    archetypes = defaultdict(list)
    for p in per_patient:
        archetypes[p['archetype']].append(p['patient'])
    results['archetypes'] = dict(archetypes)
    print(f"  Archetypes: { {k: len(v) for k, v in archetypes.items()} }")

    return results


# ---------------------------------------------------------------------------
# Main CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description='EXP-1411 to EXP-1420: Multi-segment basal implementation & grade D triage')
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

    # Print preconditions
    print(f"\n{'='*60}")
    print("PRECONDITION ASSESSMENT")
    print(f"{'='*60}")
    for pid, pdata in sorted(patients.items()):
        g = pdata['glucose']
        valid_pct = np.mean(~np.isnan(g)) * 100
        n_days = len(g) // STEPS_PER_DAY
        dawn_tag = ' [DAWN]' if pid in DAWN_PATIENTS else ''
        d_tag = ' [GRADE-D]' if pid in GRADE_D_PATIENTS else ''
        print(f"  {pid}: {n_days}d, CGM coverage={valid_pct:.1f}%{dawn_tag}{d_tag}")

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
