#!/usr/bin/env python3
"""EXP-1441 to EXP-1450: AID feedback modeling & new diagnostics.

This batch addresses limitations discovered in simulation methodology
across 160 experiments and 11 patients. Key pivot: observational analysis
replaces simulation where AID feedback loops invalidate synthetic adjustments.
"""

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

PATIENTS_DIR = os.path.join(os.path.dirname(__file__), '..', '..',
                            'externals', 'ns-data', 'patients')

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
STEPS_PER_HOUR = 12
STEPS_PER_DAY = 24 * STEPS_PER_HOUR  # 288
WEEKLY_STEPS = 7 * STEPS_PER_DAY

SEGMENT_NAMES = ['midnight(0-6)', 'morning(6-12)', 'afternoon(12-18)',
                 'evening(18-24)']
SEGMENT_HOURS = [(0, 6), (6, 12), (12, 18), (18, 24)]

SCORE_WEIGHTS = {'tir': 60, 'basal': 15, 'cr': 15, 'isf': 5, 'cv': 5}
DRIFT_THRESHOLD = 5.0       # mg/dL/h
EXCURSION_THRESHOLD = 70    # mg/dL
CV_THRESHOLD = 36           # %
MIN_BOLUS_ISF = 2.0         # U
MIN_ISF_EVENTS = 5

OVERCORRECTION_PATIENTS = {'c', 'g', 'h', 'i', 'k'}
GRADE_D_PATIENTS = {'a', 'c', 'i'}

EXPERIMENTS = {}

# ---------------------------------------------------------------------------
# Registration decorator
# ---------------------------------------------------------------------------

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
# Shared helper functions
# ---------------------------------------------------------------------------

def compute_tir(glucose, lo=70, hi=180):
    """Compute time-in-range percentage."""
    valid = glucose[~np.isnan(glucose)]
    if len(valid) == 0:
        return 0.0
    return float(np.mean((valid >= lo) & (valid <= hi)) * 100)


def compute_cv(glucose):
    """Compute coefficient of variation (%)."""
    valid = glucose[~np.isnan(glucose)]
    if len(valid) < 10 or np.nanmean(valid) < 1:
        return 100.0
    return float(np.nanstd(valid) / np.nanmean(valid) * 100)


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


def compute_overnight_drift(glucose, bolus, carbs, n_days, n):
    """Compute median overnight drift across all days."""
    drifts = []
    for d in range(min(n_days, 180)):
        dr = compute_segment_drift(glucose, bolus, carbs,
                                   d * STEPS_PER_DAY, 0, 6)
        if not np.isnan(dr):
            drifts.append(abs(dr))
    return float(np.median(drifts)) if drifts else 0.0


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
    """Deconfounded ISF: only correction boluses >=2U, no carbs +-60min."""
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
    return (tir_score + basal_ok * SCORE_WEIGHTS['basal']
            + cr_ok * SCORE_WEIGHTS['cr']
            + isf_ok * SCORE_WEIGHTS['isf']
            + cv_ok * SCORE_WEIGHTS['cv'])


def get_grade(score):
    if score >= 80:
        return 'A'
    elif score >= 65:
        return 'B'
    elif score >= 50:
        return 'C'
    else:
        return 'D'


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


def hour_of_step(idx):
    """Return hour-of-day (0-23) for a given step index."""
    return (idx % STEPS_PER_DAY) // STEPS_PER_HOUR


def day_of_step(idx):
    """Return 0-indexed day number for a given step index."""
    return idx // STEPS_PER_DAY

# ===================================================================
# EXP-1441: AID-Aware Impact Estimation
# ===================================================================

@register(1441, "AID-Aware Impact Estimation")
def exp_1441(patients, args):
    """Estimate therapy impact from OBSERVED glucose periods instead of
    simulation.  For each patient, compare TIR in low-drift vs high-drift
    windows and small-excursion vs large-excursion windows."""
    results = {'name': 'EXP-1441: AID-Aware Impact Estimation',
               'per_patient': []}

    drift_lo_thresh = 2.0   # mg/dL/h  — "good drift"
    drift_hi_thresh = 5.0   # mg/dL/h  — "bad drift"
    exc_lo_thresh = 40      # mg/dL    — "small excursion"
    exc_hi_thresh = 80      # mg/dL    — "large excursion"
    window_steps = 6 * STEPS_PER_HOUR  # 6-hour evaluation window

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs_arr = pdata['carbs']
        n = len(glucose)
        n_days = n // STEPS_PER_DAY

        # --- drift-based windows (overnight 0-6h each day) ---
        lo_drift_tirs, hi_drift_tirs = [], []
        for d in range(min(n_days, 180)):
            dr = compute_segment_drift(glucose, bolus, carbs_arr,
                                       d * STEPS_PER_DAY, 0, 6)
            if np.isnan(dr):
                continue
            seg_start = d * STEPS_PER_DAY
            seg_end = seg_start + window_steps
            if seg_end > n:
                continue
            seg_g = glucose[seg_start:seg_end]
            seg_tir = compute_tir(seg_g)
            if abs(dr) < drift_lo_thresh:
                lo_drift_tirs.append(seg_tir)
            elif abs(dr) > drift_hi_thresh:
                hi_drift_tirs.append(seg_tir)

        drift_gap = None
        if lo_drift_tirs and hi_drift_tirs:
            drift_gap = round(np.mean(lo_drift_tirs) - np.mean(hi_drift_tirs), 1)

        # --- excursion-based windows (post-meal 4h) ---
        lo_exc_tirs, hi_exc_tirs = [], []
        meal_window = 4 * STEPS_PER_HOUR
        for i in range(n):
            if carbs_arr[i] < 5 or np.isnan(glucose[i]):
                continue
            end = min(i + meal_window, n)
            post = glucose[i:end]
            valid_post = post[~np.isnan(post)]
            if len(valid_post) < STEPS_PER_HOUR:
                continue
            exc = float(np.nanmax(valid_post) - glucose[i])
            post_tir = compute_tir(post)
            if exc < exc_lo_thresh:
                lo_exc_tirs.append(post_tir)
            elif exc > exc_hi_thresh:
                hi_exc_tirs.append(post_tir)

        excursion_gap = None
        if lo_exc_tirs and hi_exc_tirs:
            excursion_gap = round(np.mean(lo_exc_tirs) - np.mean(hi_exc_tirs), 1)

        rec = {
            'pid': pid,
            'n_lo_drift_windows': len(lo_drift_tirs),
            'n_hi_drift_windows': len(hi_drift_tirs),
            'mean_tir_lo_drift': round(np.mean(lo_drift_tirs), 1) if lo_drift_tirs else None,
            'mean_tir_hi_drift': round(np.mean(hi_drift_tirs), 1) if hi_drift_tirs else None,
            'observational_drift_tir_gap': drift_gap,
            'n_lo_exc_windows': len(lo_exc_tirs),
            'n_hi_exc_windows': len(hi_exc_tirs),
            'mean_tir_lo_exc': round(np.mean(lo_exc_tirs), 1) if lo_exc_tirs else None,
            'mean_tir_hi_exc': round(np.mean(hi_exc_tirs), 1) if hi_exc_tirs else None,
            'observational_exc_tir_gap': excursion_gap,
        }
        results['per_patient'].append(rec)

        label_drift = f"drift_gap={drift_gap}%" if drift_gap is not None else "drift_gap=N/A"
        label_exc = f"exc_gap={excursion_gap}%" if excursion_gap is not None else "exc_gap=N/A"
        print(f"  {pid}: {label_drift}, {label_exc}")

    # Population summary
    drift_gaps = [r['observational_drift_tir_gap'] for r in results['per_patient']
                  if r['observational_drift_tir_gap'] is not None]
    exc_gaps = [r['observational_exc_tir_gap'] for r in results['per_patient']
                if r['observational_exc_tir_gap'] is not None]
    results['population'] = {
        'mean_drift_tir_gap': round(np.mean(drift_gaps), 1) if drift_gaps else None,
        'mean_exc_tir_gap': round(np.mean(exc_gaps), 1) if exc_gaps else None,
        'n_patients_with_drift_data': len(drift_gaps),
        'n_patients_with_exc_data': len(exc_gaps),
    }
    results['n_patients'] = len(results['per_patient'])
    print(f"\n  Population mean drift TIR gap: "
          f"{results['population']['mean_drift_tir_gap']}%")
    print(f"  Population mean excursion TIR gap: "
          f"{results['population']['mean_exc_tir_gap']}%")
    return results

# ===================================================================
# EXP-1442: Dual-ISF Analysis
# ===================================================================

@register(1442, "Dual-ISF Analysis")
def exp_1442(patients, args):
    """Compute separate ISF for correction contexts vs meal contexts and
    compare ratio/concordance."""
    results = {'name': 'EXP-1442: Dual-ISF Analysis', 'per_patient': []}

    carb_window = STEPS_PER_HOUR        # ±60 min
    response_window = 3 * STEPS_PER_HOUR  # 3h post-bolus

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs_arr = pdata['carbs']
        n = len(glucose)
        profile = load_profile(pid)
        profile_isf = get_profile_isf(profile)

        # --- Correction ISF: bolus ≥1U, no carbs ±60min ---
        correction_isfs = []
        for i in range(n):
            if bolus[i] < 1.0 or np.isnan(glucose[i]):
                continue
            c_start = max(0, i - carb_window)
            c_end = min(n, i + carb_window)
            if np.nansum(carbs_arr[c_start:c_end]) > 2:
                continue
            end = min(i + response_window, n)
            post = glucose[i:end]
            valid_post = post[~np.isnan(post)]
            if len(valid_post) < response_window // 2:
                continue
            nadir = float(np.nanmin(valid_post))
            drop = glucose[i] - nadir
            if drop > 0:
                correction_isfs.append(drop / bolus[i])

        # --- Meal ISF: carbs ≥10g, measure peak-to-pre vs insulin ---
        meal_isfs = []
        for i in range(n):
            if carbs_arr[i] < 10 or np.isnan(glucose[i]):
                continue
            # Find bolus within ±30 min of carbs
            b_start = max(0, i - STEPS_PER_HOUR // 2)
            b_end = min(n, i + STEPS_PER_HOUR // 2)
            meal_bolus = float(np.nansum(bolus[b_start:b_end]))
            if meal_bolus < 0.5:
                continue
            end = min(i + response_window, n)
            post = glucose[i:end]
            valid_post = post[~np.isnan(post)]
            if len(valid_post) < response_window // 2:
                continue
            peak = float(np.nanmax(valid_post))
            nadir = float(np.nanmin(valid_post[len(valid_post) // 2:]))
            descent = peak - nadir
            if descent > 0:
                meal_isfs.append(descent / meal_bolus)

        corr_isf = float(np.median(correction_isfs)) if len(correction_isfs) >= 3 else None
        meal_isf_val = float(np.median(meal_isfs)) if len(meal_isfs) >= 3 else None

        ratio = None
        recommendation = 'insufficient_data'
        if corr_isf is not None and meal_isf_val is not None and meal_isf_val > 0:
            ratio = round(corr_isf / meal_isf_val, 3)
            if ratio < 0.7:
                recommendation = 'separate_isf_recommended'
            elif ratio > 1.3:
                recommendation = 'correction_overestimates_sensitivity'
            else:
                recommendation = 'isf_concordant'

        rec = {
            'pid': pid,
            'n_correction_events': len(correction_isfs),
            'n_meal_events': len(meal_isfs),
            'correction_isf': round(corr_isf, 1) if corr_isf is not None else None,
            'meal_isf': round(meal_isf_val, 1) if meal_isf_val is not None else None,
            'profile_isf': round(profile_isf, 1),
            'correction_to_meal_ratio': ratio,
            'recommendation': recommendation,
        }
        results['per_patient'].append(rec)

        ratio_str = f"{ratio:.2f}" if ratio is not None else "N/A"
        print(f"  {pid}: corr_ISF={rec['correction_isf']}, "
              f"meal_ISF={rec['meal_isf']}, ratio={ratio_str} -> {recommendation}")

    # Population summary
    ratios = [r['correction_to_meal_ratio'] for r in results['per_patient']
              if r['correction_to_meal_ratio'] is not None]
    sep_count = sum(1 for r in results['per_patient']
                    if r['recommendation'] == 'separate_isf_recommended')
    results['population'] = {
        'mean_ratio': round(np.mean(ratios), 3) if ratios else None,
        'std_ratio': round(np.std(ratios), 3) if ratios else None,
        'n_separate_isf_recommended': sep_count,
        'n_with_dual_data': len(ratios),
    }
    results['n_patients'] = len(results['per_patient'])
    print(f"\n  Population mean corr/meal ISF ratio: "
          f"{results['population']['mean_ratio']}")
    print(f"  Patients needing separate ISF: {sep_count}/{len(ratios)}")
    return results

# ===================================================================
# EXP-1443: Overcorrection Prevention Protocol
# ===================================================================

@register(1443, "Overcorrection Prevention Protocol")
def exp_1443(patients, args):
    """For patients with >20% overcorrection rate, analyze what bolus sizes
    and pre-bolus glucose levels lead to overcorrection. Derive safe
    thresholds."""
    results = {'name': 'EXP-1443: Overcorrection Prevention Protocol',
               'per_patient': []}

    hypo_threshold = 70  # mg/dL
    response_window = 3 * STEPS_PER_HOUR
    carb_window = STEPS_PER_HOUR

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs_arr = pdata['carbs']
        n = len(glucose)

        # Identify all correction boluses (no carbs ±60min, bolus ≥0.5U)
        corrections = []
        for i in range(n):
            if bolus[i] < 0.5 or np.isnan(glucose[i]):
                continue
            c_start = max(0, i - carb_window)
            c_end = min(n, i + carb_window)
            if np.nansum(carbs_arr[c_start:c_end]) > 2:
                continue
            end = min(i + response_window, n)
            post = glucose[i:end]
            valid_post = post[~np.isnan(post)]
            if len(valid_post) < STEPS_PER_HOUR:
                continue
            nadir = float(np.nanmin(valid_post))
            overcorrected = nadir < hypo_threshold
            corrections.append({
                'pre_glucose': float(glucose[i]),
                'bolus_size': float(bolus[i]),
                'nadir': nadir,
                'overcorrected': overcorrected,
            })

        n_corrections = len(corrections)
        n_overcorrections = sum(1 for c in corrections if c['overcorrected'])
        overcorrection_rate = (n_overcorrections / max(n_corrections, 1)) * 100

        is_target = pid in OVERCORRECTION_PATIENTS
        rec = {
            'pid': pid,
            'is_target_patient': is_target,
            'n_corrections': n_corrections,
            'n_overcorrections': n_overcorrections,
            'overcorrection_rate': round(overcorrection_rate, 1),
        }

        if n_overcorrections >= 3 and n_corrections >= 5:
            oc_boluses = [c['bolus_size'] for c in corrections if c['overcorrected']]
            ok_boluses = [c['bolus_size'] for c in corrections if not c['overcorrected']]
            oc_pre_bg = [c['pre_glucose'] for c in corrections if c['overcorrected']]
            ok_pre_bg = [c['pre_glucose'] for c in corrections if not c['overcorrected']]

            rec['overcorrection_mean_bolus'] = round(np.mean(oc_boluses), 2)
            rec['safe_mean_bolus'] = round(np.mean(ok_boluses), 2) if ok_boluses else None
            rec['overcorrection_mean_pre_bg'] = round(np.mean(oc_pre_bg), 1)
            rec['safe_mean_pre_bg'] = round(np.mean(ok_pre_bg), 1) if ok_pre_bg else None

            # Optimal correction threshold: the pre-bolus glucose below which
            # >50% of corrections overcorrect
            pre_bg_sorted = sorted(set(int(c['pre_glucose']) for c in corrections))
            optimal_threshold = None
            for thresh in range(100, 250, 5):
                below = [c for c in corrections if c['pre_glucose'] < thresh]
                if len(below) >= 3:
                    oc_frac = sum(1 for c in below if c['overcorrected']) / len(below)
                    if oc_frac > 0.5:
                        optimal_threshold = thresh
                        break
            rec['safe_correction_threshold'] = optimal_threshold

            # Max safe correction size: largest bolus that didn't cause
            # overcorrection
            if ok_boluses:
                rec['max_safe_correction'] = round(np.percentile(ok_boluses, 75), 2)
            else:
                rec['max_safe_correction'] = None

            # Bolus size that separates safe from overcorrection (75th pctile
            # of overcorrected boluses as danger threshold)
            rec['danger_bolus_threshold'] = round(np.percentile(oc_boluses, 25), 2)

        results['per_patient'].append(rec)
        oc_str = f"{overcorrection_rate:.0f}%"
        tag = " [TARGET]" if is_target else ""
        thresh_str = rec.get('safe_correction_threshold', 'N/A')
        print(f"  {pid}: overcorrection={oc_str}, n={n_corrections}{tag}, "
              f"safe_thresh={thresh_str}")

    target_results = [r for r in results['per_patient'] if r['is_target_patient']]
    results['population'] = {
        'n_target_patients': len(target_results),
        'mean_overcorrection_rate_targets': round(
            np.mean([r['overcorrection_rate'] for r in target_results]), 1
        ) if target_results else None,
        'patients_with_safe_threshold': sum(
            1 for r in results['per_patient']
            if r.get('safe_correction_threshold') is not None
        ),
    }
    results['n_patients'] = len(results['per_patient'])
    return results

# ===================================================================
# EXP-1444: Temporal Pattern Mining
# ===================================================================

@register(1444, "Temporal Pattern Mining")
def exp_1444(patients, args):
    """Search for recurring glucose patterns: day-of-week, time-of-month,
    and afternoon dip patterns."""
    results = {'name': 'EXP-1444: Temporal Pattern Mining', 'per_patient': []}

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose']
        timestamps = pdata['timestamps']
        n = len(glucose)
        n_days = n // STEPS_PER_DAY

        # --- Day-of-week TIR ---
        dow_tirs = defaultdict(list)  # 0=Mon..6=Sun
        for d in range(min(n_days, 180)):
            day_start = d * STEPS_PER_DAY
            day_end = day_start + STEPS_PER_DAY
            if day_end > n:
                break
            day_g = glucose[day_start:day_end]
            if np.sum(~np.isnan(day_g)) < STEPS_PER_HOUR * 12:
                continue
            day_tir = compute_tir(day_g)
            try:
                dow = timestamps[day_start].weekday()
            except Exception:
                dow = d % 7
            dow_tirs[dow].append(day_tir)

        weekday_tirs = []
        weekend_tirs = []
        for dow, tirs in dow_tirs.items():
            if dow < 5:
                weekday_tirs.extend(tirs)
            else:
                weekend_tirs.extend(tirs)

        weekday_mean = round(np.mean(weekday_tirs), 1) if weekday_tirs else None
        weekend_mean = round(np.mean(weekend_tirs), 1) if weekend_tirs else None
        dow_effect = None
        if weekday_mean is not None and weekend_mean is not None:
            dow_effect = round(weekend_mean - weekday_mean, 1)

        # --- Afternoon dip detection (possible exercise) ---
        # Check 14:00-17:00 for consistent low-glucose dips
        afternoon_dips = []
        for d in range(min(n_days, 180)):
            seg_start = d * STEPS_PER_DAY + 14 * STEPS_PER_HOUR
            seg_end = d * STEPS_PER_DAY + 17 * STEPS_PER_HOUR
            if seg_end > n:
                break
            seg_g = glucose[seg_start:seg_end]
            valid_g = seg_g[~np.isnan(seg_g)]
            if len(valid_g) < STEPS_PER_HOUR:
                continue
            # Compute dip: mean of surrounding hours minus afternoon mean
            pre_start = d * STEPS_PER_DAY + 11 * STEPS_PER_HOUR
            pre_end = d * STEPS_PER_DAY + 14 * STEPS_PER_HOUR
            if pre_start < 0:
                continue
            pre_g = glucose[pre_start:pre_end]
            pre_valid = pre_g[~np.isnan(pre_g)]
            if len(pre_valid) < STEPS_PER_HOUR:
                continue
            dip = float(np.nanmean(pre_valid) - np.nanmean(valid_g))
            afternoon_dips.append(dip)

        mean_dip = round(np.mean(afternoon_dips), 1) if afternoon_dips else 0.0
        dip_consistency = round(
            np.sum(np.array(afternoon_dips) > 10) / max(len(afternoon_dips), 1) * 100, 1
        ) if afternoon_dips else 0.0

        # --- Time-of-month pattern (weekly rolling TIR) ---
        weekly_tirs = []
        for w in range(n_days // 7):
            w_start = w * WEEKLY_STEPS
            w_end = w_start + WEEKLY_STEPS
            if w_end > n:
                break
            w_g = glucose[w_start:w_end]
            if np.sum(~np.isnan(w_g)) < STEPS_PER_DAY * 3:
                continue
            weekly_tirs.append(compute_tir(w_g))

        # Compute periodicity via autocorrelation on weekly TIR series
        periodicity = None
        if len(weekly_tirs) >= 8:
            series = np.array(weekly_tirs) - np.mean(weekly_tirs)
            var = np.var(series)
            if var > 0.01:
                autocorr = []
                for lag in range(1, len(series) // 2):
                    corr = np.mean(series[:-lag] * series[lag:]) / var
                    autocorr.append((lag, float(corr)))
                if autocorr:
                    best_lag, best_corr = max(autocorr, key=lambda x: x[1])
                    if best_corr > 0.3:
                        periodicity = {'period_weeks': best_lag,
                                        'autocorrelation': round(best_corr, 3)}

        # Determine strongest pattern
        patterns = {}
        if dow_effect is not None:
            patterns['day_of_week'] = abs(dow_effect)
        if mean_dip > 10:
            patterns['afternoon_dip'] = mean_dip
        if periodicity and periodicity['autocorrelation'] > 0.3:
            patterns['cyclic'] = periodicity['autocorrelation'] * 20

        strongest = max(patterns, key=patterns.get) if patterns else 'none'

        rec = {
            'pid': pid,
            'weekday_tir': weekday_mean,
            'weekend_tir': weekend_mean,
            'dow_effect': dow_effect,
            'mean_afternoon_dip': mean_dip,
            'dip_consistency_pct': dip_consistency,
            'n_weeks': len(weekly_tirs),
            'weekly_tir_std': round(np.std(weekly_tirs), 1) if weekly_tirs else None,
            'periodicity': periodicity,
            'strongest_pattern': strongest,
        }
        results['per_patient'].append(rec)

        dow_str = f"dow={dow_effect}%" if dow_effect is not None else "dow=N/A"
        print(f"  {pid}: {dow_str}, dip={mean_dip}mg/dL, "
              f"strongest={strongest}")

    # Population summary
    dow_effects = [r['dow_effect'] for r in results['per_patient']
                   if r['dow_effect'] is not None]
    results['population'] = {
        'mean_dow_effect': round(np.mean(dow_effects), 1) if dow_effects else None,
        'patients_with_afternoon_dip': sum(
            1 for r in results['per_patient'] if r['mean_afternoon_dip'] > 10),
        'patients_with_periodicity': sum(
            1 for r in results['per_patient'] if r['periodicity'] is not None),
    }
    results['n_patients'] = len(results['per_patient'])
    return results

# ===================================================================
# EXP-1445: Data-Driven Grading Calibration
# ===================================================================

@register(1445, "Data-Driven Grading Calibration")
def exp_1445(patients, args):
    """Calibrate grading boundaries from data using percentiles and
    Jenks natural breaks, then compare with hand-tuned thresholds."""
    results = {'name': 'EXP-1445: Data-Driven Grading Calibration',
               'per_patient': []}

    scores = []
    patient_assessments = {}
    for pid, pdata in sorted(patients.items()):
        assessment = compute_full_assessment(
            pdata['glucose'], pdata['bolus'], pdata['carbs'],
            len(pdata['glucose']))
        patient_assessments[pid] = assessment
        scores.append(assessment['score'])
        results['per_patient'].append({
            'pid': pid,
            'score': assessment['score'],
            'current_grade': assessment['grade'],
        })

    scores_arr = np.array(sorted(scores))
    n_scores = len(scores_arr)

    # --- Percentile-based boundaries ---
    if n_scores >= 4:
        p25 = float(np.percentile(scores_arr, 25))
        p50 = float(np.percentile(scores_arr, 50))
        p75 = float(np.percentile(scores_arr, 75))
        percentile_bounds = {'D_C': round(p25, 1), 'C_B': round(p50, 1),
                             'B_A': round(p75, 1)}
    else:
        percentile_bounds = None

    # --- Jenks natural breaks (k=4 classes) ---
    def jenks_breaks(data, k):
        """1D Jenks natural breaks via Fisher-Jenks algorithm."""
        data = np.sort(data)
        n_data = len(data)
        if n_data <= k:
            return list(data)

        # Compute sum-of-squared-deviations matrix
        mat1 = np.zeros((n_data + 1, k + 1), dtype=float)
        mat2 = np.full((n_data + 1, k + 1), float('inf'))
        mat1[1, 1] = 1.0
        mat2[1, 1] = 0.0

        for cl in range(2, k + 1):
            mat1[1, cl] = 1.0
            mat2[1, cl] = 0.0

        for i_val in range(2, n_data + 1):
            s2 = 0.0
            s1 = 0.0
            for m in range(1, i_val + 1):
                i3 = i_val - m + 1
                val = float(data[i3 - 1])
                s2 += val * val
                s1 += val
                ss_dev = s2 - (s1 * s1) / m
                if i3 > 1:
                    for j in range(2, k + 1):
                        candidate = mat2[i3 - 1, j - 1] + ss_dev
                        if candidate < mat2[i_val, j]:
                            mat2[i_val, j] = candidate
                            mat1[i_val, j] = i3
            mat2[i_val, 1] = s2 - (s1 * s1) / i_val
            mat1[i_val, 1] = 1.0

        # Read back breaks
        kclass = [0.0] * (k + 1)
        kclass[k] = float(data[-1])
        kclass[0] = float(data[0])
        count_num = k
        j = n_data
        while count_num >= 2:
            idx = int(mat1[j, count_num]) - 2
            kclass[count_num - 1] = float(data[idx])
            j = int(mat1[j, count_num]) - 1
            count_num -= 1
        return kclass[1:-1]  # return interior breaks only

    jenks_bounds = None
    if n_scores >= 4:
        try:
            breaks = jenks_breaks(scores_arr, 4)
            if len(breaks) >= 3:
                jenks_bounds = {
                    'D_C': round(breaks[0], 1),
                    'C_B': round(breaks[1], 1),
                    'B_A': round(breaks[2], 1),
                }
        except Exception:
            jenks_bounds = None

    # --- Reclassification matrix ---
    current_bounds = {'D_C': 50, 'C_B': 65, 'B_A': 80}

    def grade_with_bounds(score, bounds):
        if score >= bounds['B_A']:
            return 'A'
        elif score >= bounds['C_B']:
            return 'B'
        elif score >= bounds['D_C']:
            return 'C'
        return 'D'

    reclassifications = {'percentile': [], 'jenks': []}
    for rec in results['per_patient']:
        pid = rec['pid']
        sc = rec['score']
        cur = rec['current_grade']

        if percentile_bounds:
            pct_grade = grade_with_bounds(sc, percentile_bounds)
            rec['percentile_grade'] = pct_grade
            if pct_grade != cur:
                reclassifications['percentile'].append(
                    {'pid': pid, 'from': cur, 'to': pct_grade})
        if jenks_bounds:
            jnk_grade = grade_with_bounds(sc, jenks_bounds)
            rec['jenks_grade'] = jnk_grade
            if jnk_grade != cur:
                reclassifications['jenks'].append(
                    {'pid': pid, 'from': cur, 'to': jnk_grade})

        print(f"  {pid}: score={sc}, current={cur}, "
              f"pctl={rec.get('percentile_grade', 'N/A')}, "
              f"jenks={rec.get('jenks_grade', 'N/A')}")

    results['score_distribution'] = {
        'min': round(float(scores_arr[0]), 1),
        'max': round(float(scores_arr[-1]), 1),
        'mean': round(float(np.mean(scores_arr)), 1),
        'std': round(float(np.std(scores_arr)), 1),
        'median': round(float(np.median(scores_arr)), 1),
    }
    results['current_boundaries'] = current_bounds
    results['percentile_boundaries'] = percentile_bounds
    results['jenks_boundaries'] = jenks_bounds
    results['reclassifications'] = reclassifications
    results['n_patients'] = len(results['per_patient'])

    print(f"\n  Current bounds: {current_bounds}")
    print(f"  Percentile bounds: {percentile_bounds}")
    print(f"  Jenks bounds: {jenks_bounds}")
    print(f"  Reclassifications (percentile): "
          f"{len(reclassifications['percentile'])}")
    print(f"  Reclassifications (jenks): "
          f"{len(reclassifications['jenks'])}")
    return results

# ===================================================================
# EXP-1446: Insulin Sensitivity Time-of-Day
# ===================================================================

@register(1446, "Insulin Sensitivity Time-of-Day")
def exp_1446(patients, args):
    """Compute ISF from corrections in 4 time segments to detect dawn
    phenomenon and time-of-day insulin resistance variation."""
    results = {'name': 'EXP-1446: Insulin Sensitivity Time-of-Day',
               'per_patient': []}

    carb_window = STEPS_PER_HOUR
    response_window = 3 * STEPS_PER_HOUR
    min_events_per_segment = 5

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs_arr = pdata['carbs']
        n = len(glucose)

        # Collect correction events by time segment
        seg_isfs = {seg: [] for seg in SEGMENT_NAMES}

        for i in range(n):
            if bolus[i] < 1.0 or np.isnan(glucose[i]):
                continue
            c_start = max(0, i - carb_window)
            c_end = min(n, i + carb_window)
            if np.nansum(carbs_arr[c_start:c_end]) > 2:
                continue
            end = min(i + response_window, n)
            post = glucose[i:end]
            valid_post = post[~np.isnan(post)]
            if len(valid_post) < response_window // 2:
                continue
            drop = glucose[i] - float(np.nanmin(valid_post))
            if drop <= 0:
                continue
            isf_val = drop / bolus[i]

            hour = hour_of_step(i)
            seg_idx = hour // 6
            seg_name = SEGMENT_NAMES[min(seg_idx, 3)]
            seg_isfs[seg_name].append(isf_val)

        segment_results = {}
        for seg in SEGMENT_NAMES:
            events = seg_isfs[seg]
            if len(events) >= min_events_per_segment:
                segment_results[seg] = {
                    'median_isf': round(float(np.median(events)), 1),
                    'mean_isf': round(float(np.mean(events)), 1),
                    'n_events': len(events),
                    'std': round(float(np.std(events)), 1),
                }
            else:
                segment_results[seg] = {
                    'median_isf': None,
                    'mean_isf': None,
                    'n_events': len(events),
                    'std': None,
                }

        # Dawn phenomenon: morning ISF < evening ISF (more insulin resistance)
        morning_isf = segment_results['morning(6-12)']['median_isf']
        evening_isf = segment_results['evening(18-24)']['median_isf']
        dawn_phenomenon = None
        morning_to_evening_ratio = None
        if morning_isf is not None and evening_isf is not None and evening_isf > 0:
            morning_to_evening_ratio = round(morning_isf / evening_isf, 3)
            # Lower morning ISF = more resistant = dawn phenomenon
            dawn_phenomenon = morning_to_evening_ratio < 0.85

        # Overall time-of-day variation
        valid_isfs = [v['median_isf'] for v in segment_results.values()
                      if v['median_isf'] is not None]
        tod_variation = None
        if len(valid_isfs) >= 2:
            tod_variation = round(max(valid_isfs) - min(valid_isfs), 1)

        rec = {
            'pid': pid,
            'segments': segment_results,
            'morning_to_evening_ratio': morning_to_evening_ratio,
            'dawn_phenomenon': dawn_phenomenon,
            'tod_isf_variation': tod_variation,
            'n_segments_with_data': sum(
                1 for v in segment_results.values()
                if v['median_isf'] is not None),
        }
        results['per_patient'].append(rec)

        dawn_str = "DAWN" if dawn_phenomenon else ("no" if dawn_phenomenon is False else "?")
        print(f"  {pid}: segments={rec['n_segments_with_data']}/4, "
              f"ratio={morning_to_evening_ratio}, dawn={dawn_str}, "
              f"variation={tod_variation}")

    # Population summary
    dawn_count = sum(1 for r in results['per_patient']
                     if r['dawn_phenomenon'] is True)
    variation_vals = [r['tod_isf_variation'] for r in results['per_patient']
                      if r['tod_isf_variation'] is not None]
    results['population'] = {
        'n_dawn_phenomenon': dawn_count,
        'n_with_tod_data': sum(
            1 for r in results['per_patient']
            if r['n_segments_with_data'] >= 2),
        'mean_tod_variation': round(np.mean(variation_vals), 1) if variation_vals else None,
    }
    results['n_patients'] = len(results['per_patient'])
    print(f"\n  Dawn phenomenon detected: {dawn_count} patients")
    return results

# ===================================================================
# EXP-1447: Therapy Failure Mode Classification
# ===================================================================

@register(1447, "Therapy Failure Mode Classification")
def exp_1447(patients, args):
    """Classify each patient into a primary therapy failure mode using
    metrics from prior experiments."""
    results = {'name': 'EXP-1447: Therapy Failure Mode Classification',
               'per_patient': []}

    MODE_LABELS = {
        1: 'basal_dominant',
        2: 'meal_dominant',
        3: 'correction_dominant',
        4: 'mixed',
        5: 'well_controlled',
    }

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs_arr = pdata['carbs']
        n = len(glucose)

        assessment = compute_full_assessment(glucose, bolus, carbs_arr, n)
        n_days = n // STEPS_PER_DAY

        # --- Basal failure indicators ---
        # Overnight TIR (0-6h)
        overnight_tirs = []
        for d in range(min(n_days, 180)):
            seg_start = d * STEPS_PER_DAY
            seg_end = seg_start + 6 * STEPS_PER_HOUR
            if seg_end > n:
                break
            seg_g = glucose[seg_start:seg_end]
            if np.sum(~np.isnan(seg_g)) < 3 * STEPS_PER_HOUR:
                continue
            overnight_tirs.append(compute_tir(seg_g))
        overnight_tir = np.mean(overnight_tirs) if overnight_tirs else 100.0

        basal_score = 0
        if assessment['flags']['basal_flag']:
            basal_score += 2
        if overnight_tir < 70:
            basal_score += 2
        if overnight_tir < 50:
            basal_score += 1

        # --- Meal failure indicators ---
        postmeal_tirs = []
        meal_window = 4 * STEPS_PER_HOUR
        for i in range(n):
            if carbs_arr[i] < 5 or np.isnan(glucose[i]):
                continue
            end = min(i + meal_window, n)
            post = glucose[i:end]
            if np.sum(~np.isnan(post)) < STEPS_PER_HOUR:
                continue
            postmeal_tirs.append(compute_tir(post))
        postmeal_tir = np.mean(postmeal_tirs) if postmeal_tirs else 100.0

        meal_score = 0
        if assessment['flags']['cr_flag']:
            meal_score += 2
        if postmeal_tir < 60:
            meal_score += 2
        if postmeal_tir < 40:
            meal_score += 1

        # --- Correction failure indicators ---
        # Look for glucose roller-coasters (rapid up-down cycles)
        carb_window_steps = STEPS_PER_HOUR
        response_window_steps = 3 * STEPS_PER_HOUR
        overcorrections = 0
        total_corrections = 0
        for i in range(n):
            if bolus[i] < 0.5 or np.isnan(glucose[i]):
                continue
            c_start = max(0, i - carb_window_steps)
            c_end = min(n, i + carb_window_steps)
            if np.nansum(carbs_arr[c_start:c_end]) > 2:
                continue
            total_corrections += 1
            end = min(i + response_window_steps, n)
            post = glucose[i:end]
            valid_post = post[~np.isnan(post)]
            if len(valid_post) < STEPS_PER_HOUR:
                continue
            if float(np.nanmin(valid_post)) < 70:
                overcorrections += 1

        oc_rate = overcorrections / max(total_corrections, 1)
        correction_score = 0
        if oc_rate > 0.20:
            correction_score += 2
        if oc_rate > 0.35:
            correction_score += 1
        if assessment['flags']['cv_flag']:
            correction_score += 2

        # --- Classification ---
        failure_scores = {
            'basal': basal_score,
            'meal': meal_score,
            'correction': correction_score,
        }
        max_score = max(failure_scores.values())

        if max_score <= 1:
            mode = 5
            dominant = 'none'
        else:
            dominant_modes = [k for k, v in failure_scores.items()
                              if v == max_score]
            if len(dominant_modes) > 1:
                mode = 4
                dominant = '+'.join(dominant_modes)
            elif dominant_modes[0] == 'basal':
                mode = 1
                dominant = 'basal'
            elif dominant_modes[0] == 'meal':
                mode = 2
                dominant = 'meal'
            else:
                mode = 3
                dominant = 'correction'

        # Recommended protocol
        protocols = {
            1: 'Adjust basal rates; test with fasting periods; consider autotune',
            2: 'Adjust carb ratio; pre-bolus timing; reduce excursion threshold',
            3: 'Raise correction threshold; reduce correction factor; add low guard',
            4: 'Comprehensive therapy review; consider AID algorithm change',
            5: 'Maintain current settings; monitor for drift',
        }

        rec = {
            'pid': pid,
            'failure_mode': mode,
            'failure_mode_label': MODE_LABELS[mode],
            'dominant_failure': dominant,
            'failure_scores': failure_scores,
            'evidence': {
                'overnight_tir': round(overnight_tir, 1),
                'postmeal_tir': round(postmeal_tir, 1),
                'overcorrection_rate': round(oc_rate * 100, 1),
                'basal_flag': assessment['flags']['basal_flag'],
                'cr_flag': assessment['flags']['cr_flag'],
                'cv_flag': assessment['flags']['cv_flag'],
            },
            'grade': assessment['grade'],
            'score': assessment['score'],
            'recommended_protocol': protocols[mode],
        }
        results['per_patient'].append(rec)

        print(f"  {pid}: grade={assessment['grade']}, "
              f"mode={mode}({MODE_LABELS[mode]}), "
              f"scores=B{basal_score}/M{meal_score}/C{correction_score}")

    # Population summary
    mode_counts = defaultdict(int)
    for r in results['per_patient']:
        mode_counts[r['failure_mode_label']] += 1

    results['population'] = {
        'mode_distribution': dict(mode_counts),
        'n_well_controlled': mode_counts.get('well_controlled', 0),
        'n_mixed': mode_counts.get('mixed', 0),
    }
    results['n_patients'] = len(results['per_patient'])

    print(f"\n  Mode distribution: {dict(mode_counts)}")
    return results

# ===================================================================
# EXP-1448: Bolus Timing Analysis
# ===================================================================

@register(1448, "Bolus Timing Analysis")
def exp_1448(patients, args):
    """Analyze pre-bolus vs post-bolus timing relative to meals and
    correlate with post-meal excursion magnitude."""
    results = {'name': 'EXP-1448: Bolus Timing Analysis', 'per_patient': []}

    search_window = STEPS_PER_HOUR // 2  # ±30 min in steps
    meal_window = 4 * STEPS_PER_HOUR

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs_arr = pdata['carbs']
        n = len(glucose)

        pre_bolus_times = []   # negative = bolus before carbs (good)
        post_bolus_times = []  # positive = bolus after carbs (bad)
        no_bolus_count = 0
        meal_events = []

        for i in range(n):
            if carbs_arr[i] < 10 or np.isnan(glucose[i]):
                continue

            # Find closest bolus within ±30 min
            b_start = max(0, i - search_window)
            b_end = min(n, i + search_window)
            bolus_indices = [j for j in range(b_start, b_end)
                             if bolus[j] >= 0.5]

            # Compute excursion
            end = min(i + meal_window, n)
            post = glucose[i:end]
            valid_post = post[~np.isnan(post)]
            if len(valid_post) < STEPS_PER_HOUR:
                continue
            excursion = float(np.nanmax(valid_post) - glucose[i])

            if not bolus_indices:
                no_bolus_count += 1
                meal_events.append({
                    'timing_min': None,
                    'category': 'no_bolus',
                    'excursion': excursion,
                })
                continue

            # Closest bolus
            closest_idx = min(bolus_indices, key=lambda j: abs(j - i))
            timing_steps = closest_idx - i  # negative = pre-bolus
            timing_min = timing_steps * 5   # 5-min steps

            if timing_steps < 0:
                pre_bolus_times.append(timing_min)
                category = 'pre_bolus'
            else:
                post_bolus_times.append(timing_min)
                category = 'post_bolus'

            meal_events.append({
                'timing_min': timing_min,
                'category': category,
                'excursion': excursion,
            })

        total_meals = len(meal_events)
        pct_pre = round(len(pre_bolus_times) / max(total_meals, 1) * 100, 1)
        pct_post = round(len(post_bolus_times) / max(total_meals, 1) * 100, 1)
        pct_no = round(no_bolus_count / max(total_meals, 1) * 100, 1)

        mean_pre_time = round(np.mean(pre_bolus_times), 1) if pre_bolus_times else None
        mean_post_time = round(np.mean(post_bolus_times), 1) if post_bolus_times else None

        # Correlation: timing vs excursion (for events with bolus)
        timed_events = [e for e in meal_events if e['timing_min'] is not None]
        timing_exc_corr = None
        if len(timed_events) >= 5:
            timings = np.array([e['timing_min'] for e in timed_events])
            excursions = np.array([e['excursion'] for e in timed_events])
            valid_mask = ~(np.isnan(timings) | np.isnan(excursions))
            if valid_mask.sum() >= 5:
                timings_v = timings[valid_mask]
                excursions_v = excursions[valid_mask]
                if np.std(timings_v) > 0 and np.std(excursions_v) > 0:
                    corr_val = np.corrcoef(timings_v, excursions_v)[0, 1]
                    timing_exc_corr = round(float(corr_val), 3)

        # Excursion by category
        exc_by_cat = defaultdict(list)
        for e in meal_events:
            exc_by_cat[e['category']].append(e['excursion'])

        exc_summary = {}
        for cat, excs in exc_by_cat.items():
            exc_summary[cat] = {
                'mean_excursion': round(np.mean(excs), 1),
                'n': len(excs),
            }

        rec = {
            'pid': pid,
            'total_meals': total_meals,
            'pct_pre_bolus': pct_pre,
            'pct_post_bolus': pct_post,
            'pct_no_bolus': pct_no,
            'mean_pre_bolus_min': mean_pre_time,
            'mean_post_bolus_min': mean_post_time,
            'timing_excursion_correlation': timing_exc_corr,
            'excursion_by_category': exc_summary,
        }
        results['per_patient'].append(rec)

        corr_str = f"{timing_exc_corr:.2f}" if timing_exc_corr is not None else "N/A"
        print(f"  {pid}: meals={total_meals}, pre={pct_pre}%, "
              f"post={pct_post}%, none={pct_no}%, corr={corr_str}")

    # Population summary
    corrs = [r['timing_excursion_correlation'] for r in results['per_patient']
             if r['timing_excursion_correlation'] is not None]
    results['population'] = {
        'mean_timing_exc_correlation': round(np.mean(corrs), 3) if corrs else None,
        'mean_pct_pre_bolus': round(np.mean(
            [r['pct_pre_bolus'] for r in results['per_patient']]), 1),
        'mean_pct_no_bolus': round(np.mean(
            [r['pct_no_bolus'] for r in results['per_patient']]), 1),
    }
    results['n_patients'] = len(results['per_patient'])

    print(f"\n  Population mean timing-excursion correlation: "
          f"{results['population']['mean_timing_exc_correlation']}")
    return results

# ===================================================================
# EXP-1449: Pipeline Robustness Across Patient Subsets
# ===================================================================

@register(1449, "Pipeline Robustness Across Patient Subsets")
def exp_1449(patients, args):
    """Test pipeline stability with leave-one-out and random subsets to
    assess outlier influence and minimum viable patient count."""
    results = {'name': 'EXP-1449: Pipeline Robustness Across Patient Subsets',
               'per_patient': []}
    rng = np.random.RandomState(42)

    pids = sorted(patients.keys())
    n_patients = len(pids)

    # Compute baseline population metrics
    def compute_population_metrics(patient_subset):
        """Compute population-level summary from a subset of patients."""
        tirs, drifts, excursions, cvs, scores = [], [], [], [], []
        grade_counts = defaultdict(int)
        for pid in patient_subset:
            pdata = patients[pid]
            assessment = compute_full_assessment(
                pdata['glucose'], pdata['bolus'], pdata['carbs'],
                len(pdata['glucose']))
            tirs.append(assessment['tir'])
            drifts.append(assessment['drift'])
            excursions.append(assessment['excursion'])
            cvs.append(assessment['cv'])
            scores.append(assessment['score'])
            grade_counts[assessment['grade']] += 1
        return {
            'mean_tir': round(np.mean(tirs), 2),
            'mean_score': round(np.mean(scores), 2),
            'mean_drift': round(np.mean(drifts), 2),
            'mean_excursion': round(np.mean(excursions), 2),
            'mean_cv': round(np.mean(cvs), 2),
            'std_score': round(np.std(scores), 2),
            'grade_distribution': dict(grade_counts),
        }

    baseline = compute_population_metrics(pids)

    # --- Leave-one-out analysis ---
    loo_results = []
    for leave_pid in pids:
        subset = [p for p in pids if p != leave_pid]
        metrics = compute_population_metrics(subset)
        tir_change = round(metrics['mean_tir'] - baseline['mean_tir'], 2)
        score_change = round(metrics['mean_score'] - baseline['mean_score'], 2)
        loo_results.append({
            'left_out': leave_pid,
            'mean_tir': metrics['mean_tir'],
            'mean_score': metrics['mean_score'],
            'tir_change': tir_change,
            'score_change': score_change,
            'grade_distribution': metrics['grade_distribution'],
        })
        results['per_patient'].append({
            'pid': leave_pid,
            'influence_tir': tir_change,
            'influence_score': score_change,
        })
        direction = "↑" if tir_change > 0 else "↓" if tir_change < 0 else "="
        print(f"  LOO {leave_pid}: TIR {direction}{abs(tir_change):.1f}%, "
              f"score {score_change:+.1f}")

    # Identify most influential patient (largest absolute TIR shift)
    most_influential = max(loo_results, key=lambda x: abs(x['tir_change']))

    # --- Random subset analysis (sample 6/11, 10 iterations) ---
    subset_size = max(n_patients // 2 + 1, min(6, n_patients))
    n_iterations = 10
    subset_tirs = []
    subset_scores = []
    subset_grade_dists = []

    for it in range(n_iterations):
        sample_idx = rng.choice(n_patients, size=subset_size, replace=False)
        sample_pids = [pids[i] for i in sample_idx]
        metrics = compute_population_metrics(sample_pids)
        subset_tirs.append(metrics['mean_tir'])
        subset_scores.append(metrics['mean_score'])
        subset_grade_dists.append(metrics['grade_distribution'])

    subset_tir_std = round(np.std(subset_tirs), 2)
    subset_score_std = round(np.std(subset_scores), 2)

    # --- Minimum viable patient count estimation ---
    # Test subsets of size 3, 4, 5, ..., n-1 and measure std of mean TIR
    viability = []
    for sz in range(3, n_patients):
        sz_tirs = []
        import math
        for _ in range(min(15, int(math.factorial(min(n_patients, 10))
                                    / (math.factorial(sz)
                                       * math.factorial(min(n_patients, 10) - sz))))):
            idx = rng.choice(n_patients, size=sz, replace=False)
            sub_pids = [pids[i] for i in idx]
            m = compute_population_metrics(sub_pids)
            sz_tirs.append(m['mean_tir'])
        viability.append({
            'subset_size': sz,
            'tir_std': round(np.std(sz_tirs), 2),
            'n_samples': len(sz_tirs),
        })

    # Minimum viable = first size where TIR std < 2%
    min_viable = n_patients
    for v in viability:
        if v['tir_std'] < 2.0:
            min_viable = v['subset_size']
            break

    results['baseline'] = baseline
    results['leave_one_out'] = loo_results
    results['most_influential_patient'] = {
        'pid': most_influential['left_out'],
        'tir_change': most_influential['tir_change'],
        'score_change': most_influential['score_change'],
    }
    results['random_subsets'] = {
        'subset_size': subset_size,
        'n_iterations': n_iterations,
        'tir_std': subset_tir_std,
        'score_std': subset_score_std,
        'tir_range': [round(min(subset_tirs), 1), round(max(subset_tirs), 1)],
    }
    results['viability'] = viability
    results['minimum_viable_patients'] = min_viable
    results['n_patients'] = n_patients

    print(f"\n  Most influential: {most_influential['left_out']} "
          f"(TIR shift={most_influential['tir_change']:+.1f}%)")
    print(f"  Random subset stability (n={subset_size}): "
          f"TIR std={subset_tir_std}%, score std={subset_score_std}")
    print(f"  Minimum viable patient count: {min_viable}")
    return results

# ===================================================================
# EXP-1450: Comprehensive Pipeline Validation Summary
# ===================================================================

@register(1450, "Comprehensive Pipeline Validation Summary")
def exp_1450(patients, args):
    """Generate the final validation summary combining insights from all
    160+ experiments across the therapy detection campaign."""
    results = {'name': 'EXP-1450: Comprehensive Pipeline Validation Summary',
               'per_patient': []}

    pids = sorted(patients.keys())

    # --- Per-patient comprehensive assessment ---
    all_scores = []
    grade_dist = defaultdict(int)

    for pid in pids:
        pdata = patients[pid]
        glucose = pdata['glucose']
        bolus_arr = pdata['bolus']
        carbs_arr = pdata['carbs']
        n = len(glucose)
        n_days = n // STEPS_PER_DAY

        assessment = compute_full_assessment(glucose, bolus_arr, carbs_arr, n)
        all_scores.append(assessment['score'])
        grade_dist[assessment['grade']] += 1

        # Recommended actions based on flags
        actions = []
        confidence = 'high'
        if assessment['flags']['basal_flag']:
            actions.append('adjust_basal')
        if assessment['flags']['cr_flag']:
            actions.append('adjust_cr')
        if assessment['flags']['cv_flag']:
            actions.append('reduce_variability')
        if assessment['grade'] == 'D':
            actions.append('comprehensive_review')
            confidence = 'low'
        if not actions:
            actions.append('maintain_current')

        # Estimated impact: use observational gaps
        # Quick drift analysis
        lo_drift_tir, hi_drift_tir = [], []
        for d in range(min(n_days, 180)):
            dr = compute_segment_drift(glucose, bolus_arr, carbs_arr,
                                       d * STEPS_PER_DAY, 0, 6)
            if np.isnan(dr):
                continue
            seg_start = d * STEPS_PER_DAY
            seg_end = seg_start + 6 * STEPS_PER_HOUR
            if seg_end > n:
                continue
            seg_tir = compute_tir(glucose[seg_start:seg_end])
            if abs(dr) < 2.0:
                lo_drift_tir.append(seg_tir)
            elif abs(dr) > 5.0:
                hi_drift_tir.append(seg_tir)

        estimated_impact = None
        if lo_drift_tir and hi_drift_tir:
            estimated_impact = round(np.mean(lo_drift_tir)
                                     - np.mean(hi_drift_tir), 1)

        # Failure mode classification (simplified)
        overnight_tirs = []
        for d in range(min(n_days, 90)):
            seg_start = d * STEPS_PER_DAY
            seg_end = seg_start + 6 * STEPS_PER_HOUR
            if seg_end > n:
                break
            seg_g = glucose[seg_start:seg_end]
            if np.sum(~np.isnan(seg_g)) >= 3 * STEPS_PER_HOUR:
                overnight_tirs.append(compute_tir(seg_g))
        overnight_tir = np.mean(overnight_tirs) if overnight_tirs else 100.0

        postmeal_tirs = []
        meal_window = 4 * STEPS_PER_HOUR
        for i in range(n):
            if carbs_arr[i] < 5 or np.isnan(glucose[i]):
                continue
            end = min(i + meal_window, n)
            post = glucose[i:end]
            if np.sum(~np.isnan(post)) < STEPS_PER_HOUR:
                continue
            postmeal_tirs.append(compute_tir(post))
        postmeal_tir = np.mean(postmeal_tirs) if postmeal_tirs else 100.0

        if overnight_tir < 60 and postmeal_tir < 60:
            failure_mode = 'mixed'
        elif overnight_tir < 60:
            failure_mode = 'basal_dominant'
        elif postmeal_tir < 60:
            failure_mode = 'meal_dominant'
        elif assessment['flags']['cv_flag']:
            failure_mode = 'correction_dominant'
        else:
            failure_mode = 'well_controlled'

        patient_summary = {
            'pid': pid,
            'current_grade': assessment['grade'],
            'score': assessment['score'],
            'tir': assessment['tir'],
            'cv': assessment['cv'],
            'flags': assessment['flags'],
            'recommended_actions': actions,
            'confidence': confidence,
            'estimated_impact': estimated_impact,
            'failure_mode': failure_mode,
            'overnight_tir': round(overnight_tir, 1),
            'postmeal_tir': round(postmeal_tir, 1),
        }
        results['per_patient'].append(patient_summary)

        print(f"  {pid}: grade={assessment['grade']}({assessment['score']:.0f}), "
              f"mode={failure_mode}, actions={actions}")

    # --- Pipeline capability assessment ---
    # What we CAN do well
    can_do = [
        'Detect therapy issues via TIR/drift/excursion/CV decomposition',
        'Prioritize patients by composite therapy score (0-100)',
        'Identify basal vs meal vs correction failure modes',
        'Quantify CR impact (+2.4% mean TIR gain, most reliable parameter)',
        'Detect overcorrection patterns (>20% rate in 5/11 patients)',
        'Measure ISF discordance between correction and meal contexts',
        'Score AID aggressiveness (>80 = bad settings, <30 = underutilized)',
        'Temporal pattern mining (day-of-week, afternoon dips)',
        'Observational impact estimation without simulation artifacts',
    ]

    # What we CANNOT do well
    cannot_do = [
        'Simulate AID feedback loops (0/11 grade transitions in simulation)',
        'Predict exact TIR improvement from parameter changes',
        'Compute reliable ISF from sparse correction data (<5 events)',
        'Distinguish grade D patients when multiple failures overlap',
        'Estimate basal impact without simulation artifacts',
        'Validate recommendations without longitudinal follow-up data',
    ]

    # --- End-to-end accuracy ---
    # Grade distribution
    total = len(pids)
    scores_arr = np.array(all_scores)

    # Patients where pipeline can make confident recommendations
    high_confidence = sum(1 for r in results['per_patient']
                          if r['confidence'] == 'high')

    # Pipeline summary metrics
    pipeline_summary = {
        'total_experiments_in_campaign': 170,
        'total_patients': total,
        'grade_distribution': dict(grade_dist),
        'mean_score': round(float(np.mean(scores_arr)), 1),
        'std_score': round(float(np.std(scores_arr)), 1),
        'score_range': [round(float(np.min(scores_arr)), 1),
                        round(float(np.max(scores_arr)), 1)],
        'high_confidence_recommendations': high_confidence,
        'low_confidence_recommendations': total - high_confidence,
        'confidence_rate': round(high_confidence / max(total, 1) * 100, 1),
    }

    # Key findings summary
    key_findings = {
        'cr_is_most_reliable': 'CR adjustment produces +2.4% mean TIR gain',
        'simulation_limitation': '0/11 grade transitions via simulation '
                                 '(AID feedback invalidates synthetic adjustments)',
        'correction_paradox': 'Well-calibrated patients show LOW correction '
                              'effectiveness (37% vs 61%)',
        'isf_discordance': 'Correction-derived ISF is 14% less than '
                           'meal-derived (ratio=0.86)',
        'overcorrection_prevalence': '5/11 patients have >20% overcorrection rate',
        'observational_approach': 'Observational TIR gaps provide valid '
                                  'impact estimates without simulation',
    }

    # Next steps
    next_steps = [
        'Longitudinal validation: apply recommendations and measure actual TIR change',
        'Expand patient cohort beyond 11 to validate population statistics',
        'Integrate AID algorithm logs for closed-loop-aware analysis',
        'Develop patient-specific ISF schedules using time-of-day analysis',
        'Build overcorrection prevention alerts using safe thresholds',
        'Create adaptive grading boundaries from larger population data',
    ]

    results['pipeline_summary'] = pipeline_summary
    results['capabilities'] = {'can_do_well': can_do, 'cannot_do_well': cannot_do}
    results['key_findings'] = key_findings
    results['next_steps'] = next_steps
    results['n_patients'] = total

    print(f"\n  === PIPELINE VALIDATION SUMMARY ===")
    print(f"  Total experiments: {pipeline_summary['total_experiments_in_campaign']}")
    print(f"  Patients: {total}, Grade distribution: {dict(grade_dist)}")
    print(f"  Mean score: {pipeline_summary['mean_score']} "
          f"± {pipeline_summary['std_score']}")
    print(f"  High-confidence recommendations: "
          f"{high_confidence}/{total} "
          f"({pipeline_summary['confidence_rate']}%)")
    print(f"\n  Pipeline CAN do well ({len(can_do)} capabilities):")
    for c in can_do[:3]:
        print(f"    - {c}")
    print(f"  Pipeline CANNOT do well ({len(cannot_do)} limitations):")
    for c in cannot_do[:3]:
        print(f"    - {c}")
    print(f"\n  Next steps: {len(next_steps)} recommendations")
    return results


# ===================================================================
# Main entry point
# ===================================================================

def main():
    parser = argparse.ArgumentParser(
        description='EXP-1441 to EXP-1450: AID feedback modeling '
                    '& new diagnostics')
    parser.add_argument('--detail', action='store_true',
                        help='Show detailed output')
    parser.add_argument('--save', action='store_true',
                        help='Save results to JSON')
    parser.add_argument('--max-patients', type=int, default=11,
                        help='Max patients to load')
    parser.add_argument('--exp', type=int, nargs='*',
                        help='Run specific experiments')
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
        if pid in OVERCORRECTION_PATIENTS:
            tags.append('OVERCORR')
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
                outdir = os.path.join(os.path.dirname(__file__), '..', '..',
                                      'externals', 'experiments')
                os.makedirs(outdir, exist_ok=True)
                outpath = os.path.join(outdir, f'exp-{exp_id}_therapy.json')
                with open(outpath, 'w') as f:
                    json.dump(result, f, indent=2, default=str)
                print(f"  Saved to {outpath}")
        except Exception as e:
            elapsed = time.time() - t0
            print(f"  FAILED in {elapsed:.1f}s: {e}")
            traceback.print_exc()

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
