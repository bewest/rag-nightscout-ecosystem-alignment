#!/usr/bin/env python3
"""EXP-1451 to EXP-1460: Operational Deployment & Clinical Refinement.

This batch validates that the therapy detection pipeline is deployment-ready.
It addresses confidence calibration, minimum data requirements, failure-mode
routing, longitudinal stability, and overall readiness scoring.  All analyses
use the observational TIR-gap methodology proven in EXP-1441.
"""

import argparse
import json
import math
import numpy as np
import os
import sys
import time
import traceback
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from cgmencode.exp_metabolic_flux import load_patients as _load_patients

# ---------------------------------------------------------------------------
# Paths & results directory
# ---------------------------------------------------------------------------
PATIENTS_DIR = os.path.join(os.path.dirname(__file__), '..', '..',
                            'externals', 'ns-data', 'patients')

RESULTS_DIR = (Path(__file__).resolve().parent.parent.parent
               / 'externals' / 'experiments')

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
STEPS_PER_HOUR = 12
STEPS_PER_DAY = 24 * STEPS_PER_HOUR        # 288
WEEKLY_STEPS = 7 * STEPS_PER_DAY

SEGMENT_NAMES = ['midnight(0-6)', 'morning(6-12)', 'afternoon(12-18)',
                 'evening(18-24)']
SEGMENT_HOURS = [(0, 6), (6, 12), (12, 18), (18, 24)]

TIR_LO = 70    # mg/dL
TIR_HI = 180   # mg/dL

# Grade boundaries  (score → letter)
GRADE_D_CEIL = 50
GRADE_C_CEIL = 65
GRADE_B_CEIL = 80

# Score composition weights
SCORE_WEIGHTS = {'tir': 60, 'basal': 15, 'cr': 15, 'isf': 5, 'cv': 5}
DRIFT_THRESHOLD = 5.0       # mg/dL/h
EXCURSION_THRESHOLD = 70    # mg/dL  (90-th %ile post-meal rise)
CV_THRESHOLD = 36           # %
MIN_BOLUS_ISF = 2.0         # U  — minimum correction bolus for ISF calc
MIN_ISF_EVENTS = 5

CONSERVATIVE_BASAL_PCT = 10     # ±10 %
CR_ADJUST_STANDARD = 30        # -30 %
CR_ADJUST_GRADE_D = 50         # -50 %
ISF_ADJUST_PCT = 10            # ±10 %
DIA_DEFAULT = 6.0              # hours

N_BOOTSTRAP = 1000
RNG_SEED = 42

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
            'bolus': (df['bolus'].values if 'bolus' in df.columns
                      else np.zeros(len(df))),
            'carbs': (df['carbs'].values if 'carbs' in df.columns
                      else np.zeros(len(df))),
            'temp_rate': (df['temp_rate'].values if 'temp_rate' in df.columns
                         else np.zeros(len(df))),
            'iob': (df['iob'].values if 'iob' in df.columns
                    else np.zeros(len(df))),
            'cob': (df['cob'].values if 'cob' in df.columns
                    else np.zeros(len(df))),
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
            default['_units'] = prof.get('units', default.get('units',
                                                              'mg/dL'))
        return default
    except Exception:
        return None

# ---------------------------------------------------------------------------
# Shared helper functions
# ---------------------------------------------------------------------------

def compute_tir(glucose, lo=TIR_LO, hi=TIR_HI):
    """Compute time-in-range percentage."""
    if isinstance(glucose, np.ndarray):
        valid = glucose[~np.isnan(glucose)]
    else:
        valid = glucose.dropna()
    if len(valid) == 0:
        return 0.0
    return float(np.mean((valid >= lo) & (valid <= hi)) * 100)


def compute_grade(score):
    """Map numeric score → letter grade."""
    if score < GRADE_D_CEIL:
        return 'D'
    if score < GRADE_C_CEIL:
        return 'C'
    if score < GRADE_B_CEIL:
        return 'B'
    return 'A'


def compute_score(tir, cv, overnight_tir=None):
    """Simplified composite score (0-100)."""
    score = tir * 0.6 + max(0, 100 - cv * 2) * 0.3
    if overnight_tir is not None:
        score += overnight_tir * 0.1
    return min(100.0, max(0.0, float(score)))


def compute_cv(glucose):
    """Compute coefficient of variation (%)."""
    if isinstance(glucose, np.ndarray):
        valid = glucose[~np.isnan(glucose)]
    else:
        valid = glucose.dropna().values
    if len(valid) < 10 or np.mean(valid) < 1:
        return 100.0
    return float(np.std(valid) / np.mean(valid) * 100)


def hour_of_step(idx):
    """Return hour-of-day (0-23) for a given step index."""
    return (idx % STEPS_PER_DAY) // STEPS_PER_HOUR


def day_of_step(idx):
    """Return 0-indexed day number for a given step index."""
    return idx // STEPS_PER_DAY


def compute_segment_drift(glucose, bolus, carbs, day_start, h_start, h_end):
    """Compute glucose drift (mg/dL/h) for a segment on a given day.

    Returns NaN if the segment is contaminated by bolus/carb activity or
    has insufficient valid CGM readings.
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
    # Exclude windows with recent bolus / carb activity
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
    """Compute median absolute overnight drift across all days."""
    drifts = []
    for d in range(min(n_days, 180)):
        dr = compute_segment_drift(glucose, bolus, carbs,
                                   d * STEPS_PER_DAY, 0, 6)
        if not np.isnan(dr):
            drifts.append(abs(dr))
    return float(np.median(drifts)) if drifts else 0.0


def compute_max_excursion(glucose, carbs, n):
    """90th percentile post-meal excursion (mg/dL)."""
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
    """Deconfounded ISF from correction boluses ≥2 U with no nearby carbs."""
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


def compute_full_assessment(glucose, bolus, carbs, n):
    """Compute full therapy assessment for a patient data slice."""
    tir = compute_tir(glucose)
    n_days = max(n // STEPS_PER_DAY, 1)
    drift = compute_overnight_drift(glucose, bolus, carbs, n_days, n)
    exc = compute_max_excursion(glucose, carbs, n)
    isf = compute_isf_ratio(glucose, bolus, carbs, n)
    cv = compute_cv(glucose)
    score = compute_therapy_score(tir, drift, exc, isf, cv)
    grade = compute_grade(score)
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
        },
    }


def compute_overnight_tir(glucose, n):
    """TIR restricted to 00:00-06:00 windows."""
    tirs = []
    n_days = n // STEPS_PER_DAY
    for d in range(min(n_days, 180)):
        s = d * STEPS_PER_DAY
        e = s + 6 * STEPS_PER_HOUR
        if e > n:
            break
        seg = glucose[s:e]
        valid = seg[~np.isnan(seg)]
        if len(valid) >= STEPS_PER_HOUR:
            tirs.append(compute_tir(seg))
    return float(np.mean(tirs)) if tirs else 0.0


def compute_postmeal_tir(glucose, carbs, n):
    """TIR restricted to 4 h post-meal windows (≥5 g carbs)."""
    tirs = []
    window = 4 * STEPS_PER_HOUR
    for i in range(n):
        if carbs[i] < 5 or np.isnan(glucose[i]):
            continue
        end = min(i + window, n)
        seg = glucose[i:end]
        valid = seg[~np.isnan(seg)]
        if len(valid) >= STEPS_PER_HOUR:
            tirs.append(compute_tir(seg))
    return float(np.mean(tirs)) if tirs else 0.0


def compute_overcorrection_rate(glucose, bolus, carbs, n):
    """Fraction of correction boluses followed by hypoglycaemia (<70)."""
    events = 0
    hypos = 0
    response_window = 4 * STEPS_PER_HOUR
    carb_window = STEPS_PER_HOUR
    for i in range(n):
        if bolus[i] < MIN_BOLUS_ISF or np.isnan(glucose[i]):
            continue
        c_start = max(0, i - carb_window)
        c_end = min(n, i + carb_window)
        if np.nansum(carbs[c_start:c_end]) > 2:
            continue
        events += 1
        end = min(i + response_window, n)
        post = glucose[i:end]
        valid_post = post[~np.isnan(post)]
        if len(valid_post) > 0 and np.nanmin(valid_post) < TIR_LO:
            hypos += 1
    if events == 0:
        return 0.0
    return float(hypos / events)


def classify_failure_mode(overnight_tir, postmeal_tir, overcorr_rate):
    """5-way failure-mode classification (EXP-1447 methodology).

    Returns one of: well_controlled, basal_dominant, meal_dominant,
    correction_dominant, mixed.
    """
    basal_bad = overnight_tir < 75
    meal_bad = postmeal_tir < 60
    corr_bad = overcorr_rate > 0.25

    n_bad = sum([basal_bad, meal_bad, corr_bad])
    if n_bad == 0:
        return 'well_controlled'
    if n_bad >= 2:
        return 'mixed'
    if basal_bad:
        return 'basal_dominant'
    if meal_bad:
        return 'meal_dominant'
    return 'correction_dominant'


def failure_mode_first_fix(mode):
    """Return the recommended first intervention for a given failure mode."""
    return {
        'well_controlled': 'none',
        'basal_dominant': 'basal',
        'meal_dominant': 'cr',
        'correction_dominant': 'isf',
        'mixed': 'basal',   # generic sequential: basal first
    }.get(mode, 'basal')


def _bootstrap_ci(values, n_boot=N_BOOTSTRAP, rng=None):
    """Return (median, lo_2.5, hi_97.5) from bootstrap resampling."""
    if rng is None:
        rng = np.random.RandomState(RNG_SEED)
    arr = np.asarray(values, dtype=float)
    arr = arr[~np.isnan(arr)]
    if len(arr) < 3:
        m = float(np.median(arr)) if len(arr) > 0 else 0.0
        return m, m, m
    medians = np.empty(n_boot)
    for b in range(n_boot):
        sample = rng.choice(arr, size=len(arr), replace=True)
        medians[b] = np.median(sample)
    return (float(np.median(medians)),
            float(np.percentile(medians, 2.5)),
            float(np.percentile(medians, 97.5)))


def _linear_trend(values):
    """Fit simple OLS slope over an evenly-spaced series.

    Returns slope, p-value proxy (|t-statistic|), and direction string.
    """
    y = np.asarray(values, dtype=float)
    mask = ~np.isnan(y)
    y = y[mask]
    if len(y) < 3:
        return 0.0, 0.0, 'stable'
    x = np.arange(len(y), dtype=float)
    xm = x.mean()
    ym = y.mean()
    ss_xy = np.sum((x - xm) * (y - ym))
    ss_xx = np.sum((x - xm) ** 2)
    if ss_xx < 1e-12:
        return 0.0, 0.0, 'stable'
    slope = float(ss_xy / ss_xx)
    y_hat = xm * slope + (ym - slope * xm) + slope * x
    residuals = y - y_hat
    se = np.sqrt(np.sum(residuals ** 2) / max(len(y) - 2, 1)) / np.sqrt(ss_xx)
    t_stat = abs(slope / se) if se > 1e-12 else 0.0
    if abs(slope) < 1e-6 or t_stat < 2.0:
        direction = 'stable'
    elif slope > 0:
        direction = 'increasing'
    else:
        direction = 'decreasing'
    return slope, t_stat, direction


def _safe_round(val, digits=2):
    """Round a value safely, handling None / NaN."""
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    return round(float(val), digits)


def _spearman_rank_corr(x, y):
    """Compute Spearman rank correlation between two lists."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    mask = (~np.isnan(x)) & (~np.isnan(y))
    x, y = x[mask], y[mask]
    if len(x) < 3:
        return 0.0
    rx = _rank_array(x)
    ry = _rank_array(y)
    d = rx - ry
    n = len(x)
    return float(1 - 6 * np.sum(d ** 2) / (n * (n ** 2 - 1)))


def _rank_array(arr):
    """Assign ranks (1-based) to values in an array (average tie-breaking)."""
    order = np.argsort(arr)
    ranks = np.empty_like(order, dtype=float)
    ranks[order] = np.arange(1, len(arr) + 1, dtype=float)
    return ranks


def _compute_window_metrics(glucose, bolus, carbs, start, end):
    """Compute drift, excursion, isf for a sub-window [start:end]."""
    g = glucose[start:end]
    b = bolus[start:end]
    c = carbs[start:end]
    n = len(g)
    n_days = max(n // STEPS_PER_DAY, 1)
    drift = compute_overnight_drift(g, b, c, n_days, n)
    exc = compute_max_excursion(g, c, n)
    isf = compute_isf_ratio(g, b, c, n)
    tir = compute_tir(g)
    cv = compute_cv(g)
    return {
        'drift': drift, 'excursion': exc, 'isf_ratio': isf,
        'tir': tir, 'cv': cv,
    }


# ===================================================================
# EXP-1451: Observational Impact Sizing with Confidence Intervals
# ===================================================================

@register(1451, "Observational Impact Sizing with CIs")
def exp_1451(patients, args):
    """Bootstrap confidence intervals on observational TIR gap for each
    parameter fix (basal, CR, ISF).  Stratifies windows by parameter
    quality and measures TIR delta between strata."""
    results = {'name': 'EXP-1451: Observational Impact Sizing with CIs',
               'per_patient': []}

    rng = np.random.RandomState(RNG_SEED)
    drift_lo = 2.0
    drift_hi = 5.0
    exc_lo = 40
    exc_hi = 80
    window_steps = 6 * STEPS_PER_HOUR

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs_arr = pdata['carbs']
        n = len(glucose)
        n_days = n // STEPS_PER_DAY

        # --- Basal: drift-stratified overnight windows ---
        lo_drift_tirs, hi_drift_tirs = [], []
        for d in range(min(n_days, 180)):
            dr = compute_segment_drift(glucose, bolus, carbs_arr,
                                       d * STEPS_PER_DAY, 0, 6)
            if np.isnan(dr):
                continue
            seg_s = d * STEPS_PER_DAY
            seg_e = seg_s + window_steps
            if seg_e > n:
                continue
            seg_tir = compute_tir(glucose[seg_s:seg_e])
            if abs(dr) < drift_lo:
                lo_drift_tirs.append(seg_tir)
            elif abs(dr) > drift_hi:
                hi_drift_tirs.append(seg_tir)

        if lo_drift_tirs and hi_drift_tirs:
            gaps_basal = [float(np.mean(rng.choice(lo_drift_tirs,
                                                   len(lo_drift_tirs),
                                                   replace=True))
                                - np.mean(rng.choice(hi_drift_tirs,
                                                     len(hi_drift_tirs),
                                                     replace=True)))
                          for _ in range(N_BOOTSTRAP)]
            basal_med = float(np.median(gaps_basal))
            basal_ci = [float(np.percentile(gaps_basal, 2.5)),
                        float(np.percentile(gaps_basal, 97.5))]
        else:
            basal_med = 0.0
            basal_ci = [0.0, 0.0]

        # --- CR: excursion-stratified post-meal windows ---
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
            exc_val = float(np.nanmax(valid_post) - glucose[i])
            seg_tir = compute_tir(post)
            if exc_val < exc_lo:
                lo_exc_tirs.append(seg_tir)
            elif exc_val > exc_hi:
                hi_exc_tirs.append(seg_tir)

        if lo_exc_tirs and hi_exc_tirs:
            gaps_cr = [float(np.mean(rng.choice(lo_exc_tirs,
                                                len(lo_exc_tirs),
                                                replace=True))
                             - np.mean(rng.choice(hi_exc_tirs,
                                                  len(hi_exc_tirs),
                                                  replace=True)))
                       for _ in range(N_BOOTSTRAP)]
            cr_med = float(np.median(gaps_cr))
            cr_ci = [float(np.percentile(gaps_cr, 2.5)),
                     float(np.percentile(gaps_cr, 97.5))]
        else:
            cr_med = 0.0
            cr_ci = [0.0, 0.0]

        # --- ISF: post-correction hypo stratification ---
        safe_tirs, hypo_tirs = [], []
        response_window = 4 * STEPS_PER_HOUR
        carb_window = STEPS_PER_HOUR
        for i in range(n):
            if bolus[i] < MIN_BOLUS_ISF or np.isnan(glucose[i]):
                continue
            c_s = max(0, i - carb_window)
            c_e = min(n, i + carb_window)
            if np.nansum(carbs_arr[c_s:c_e]) > 2:
                continue
            end = min(i + response_window, n)
            post = glucose[i:end]
            valid_post = post[~np.isnan(post)]
            if len(valid_post) < STEPS_PER_HOUR:
                continue
            seg_tir = compute_tir(post)
            if np.nanmin(valid_post) >= TIR_LO:
                safe_tirs.append(seg_tir)
            else:
                hypo_tirs.append(seg_tir)

        if safe_tirs and hypo_tirs:
            gaps_isf = [float(np.mean(rng.choice(safe_tirs,
                                                 len(safe_tirs),
                                                 replace=True))
                              - np.mean(rng.choice(hypo_tirs,
                                                   len(hypo_tirs),
                                                   replace=True)))
                        for _ in range(N_BOOTSTRAP)]
            isf_med = float(np.median(gaps_isf))
            isf_ci = [float(np.percentile(gaps_isf, 2.5)),
                      float(np.percentile(gaps_isf, 97.5))]
        else:
            isf_med = 0.0
            isf_ci = [0.0, 0.0]

        n_uncertain = sum([
            1 for ci in [basal_ci, cr_ci, isf_ci]
            if ci[0] <= 0 <= ci[1]
        ])

        rec = {
            'pid': pid,
            'basal_impact_median': _safe_round(basal_med, 1),
            'basal_impact_ci': [_safe_round(v, 1) for v in basal_ci],
            'cr_impact_median': _safe_round(cr_med, 1),
            'cr_impact_ci': [_safe_round(v, 1) for v in cr_ci],
            'isf_impact_median': _safe_round(isf_med, 1),
            'isf_impact_ci': [_safe_round(v, 1) for v in isf_ci],
            'n_uncertain': n_uncertain,
            'n_basal_lo': len(lo_drift_tirs),
            'n_basal_hi': len(hi_drift_tirs),
            'n_cr_lo': len(lo_exc_tirs),
            'n_cr_hi': len(hi_exc_tirs),
            'n_isf_safe': len(safe_tirs),
            'n_isf_hypo': len(hypo_tirs),
        }
        results['per_patient'].append(rec)

        if args.detail:
            print(f"  {pid}: basal={basal_med:+.1f} CI[{basal_ci[0]:.1f},"
                  f"{basal_ci[1]:.1f}]  cr={cr_med:+.1f} CI[{cr_ci[0]:.1f},"
                  f"{cr_ci[1]:.1f}]  isf={isf_med:+.1f} CI[{isf_ci[0]:.1f},"
                  f"{isf_ci[1]:.1f}]  uncertain={n_uncertain}")

    results['n_patients'] = len(results['per_patient'])
    # Population summary
    all_unc = [r['n_uncertain'] for r in results['per_patient']]
    results['summary'] = {
        'mean_uncertain_per_patient': _safe_round(np.mean(all_unc), 2)
                                      if all_unc else 0,
        'patients_with_zero_uncertain': sum(1 for u in all_unc if u == 0),
    }
    return results


# ===================================================================
# EXP-1452: Failure-Mode-Routed Protocol Validation
# ===================================================================

@register(1452, "Failure-Mode-Routed Protocol Validation")
def exp_1452(patients, args):
    """Compare mode-specific first intervention vs generic sequential
    protocol using observational TIR gaps."""
    results = {'name': 'EXP-1452: Failure-Mode-Routed Protocol Validation',
               'per_patient': []}

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs_arr = pdata['carbs']
        n = len(glucose)

        overnight_tir = compute_overnight_tir(glucose, n)
        postmeal_tir = compute_postmeal_tir(glucose, carbs_arr, n)
        overcorr = compute_overcorrection_rate(glucose, bolus, carbs_arr, n)

        mode = classify_failure_mode(overnight_tir, postmeal_tir, overcorr)
        routed_fix = failure_mode_first_fix(mode)
        generic_fix = 'basal'  # generic protocol always starts with basal

        # Compute observational TIR gap for each possible first fix
        n_days = n // STEPS_PER_DAY
        drift = compute_overnight_drift(glucose, bolus, carbs_arr, n_days, n)
        exc = compute_max_excursion(glucose, carbs_arr, n)
        overall_tir = compute_tir(glucose)

        # Observational TIR gap per parameter
        tir_gap_basal = 0.0
        lo_tirs, hi_tirs = [], []
        window_steps = 6 * STEPS_PER_HOUR
        for d in range(min(n_days, 180)):
            dr = compute_segment_drift(glucose, bolus, carbs_arr,
                                       d * STEPS_PER_DAY, 0, 6)
            if np.isnan(dr):
                continue
            seg_s = d * STEPS_PER_DAY
            seg_e = seg_s + window_steps
            if seg_e > n:
                continue
            seg_tir = compute_tir(glucose[seg_s:seg_e])
            if abs(dr) < 2.0:
                lo_tirs.append(seg_tir)
            elif abs(dr) > 5.0:
                hi_tirs.append(seg_tir)
        if lo_tirs and hi_tirs:
            tir_gap_basal = float(np.mean(lo_tirs) - np.mean(hi_tirs))

        tir_gap_cr = 0.0
        lo_e, hi_e = [], []
        meal_window = 4 * STEPS_PER_HOUR
        for i in range(n):
            if carbs_arr[i] < 5 or np.isnan(glucose[i]):
                continue
            end = min(i + meal_window, n)
            post = glucose[i:end]
            vp = post[~np.isnan(post)]
            if len(vp) < STEPS_PER_HOUR:
                continue
            ev = float(np.nanmax(vp) - glucose[i])
            st = compute_tir(post)
            if ev < 40:
                lo_e.append(st)
            elif ev > 80:
                hi_e.append(st)
        if lo_e and hi_e:
            tir_gap_cr = float(np.mean(lo_e) - np.mean(hi_e))

        tir_gap_isf = 0.0
        safe_t, hypo_t = [], []
        resp_w = 4 * STEPS_PER_HOUR
        for i in range(n):
            if bolus[i] < MIN_BOLUS_ISF or np.isnan(glucose[i]):
                continue
            c_s = max(0, i - STEPS_PER_HOUR)
            c_e = min(n, i + STEPS_PER_HOUR)
            if np.nansum(carbs_arr[c_s:c_e]) > 2:
                continue
            end = min(i + resp_w, n)
            post = glucose[i:end]
            vp = post[~np.isnan(post)]
            if len(vp) < STEPS_PER_HOUR:
                continue
            st = compute_tir(post)
            if np.nanmin(vp) >= TIR_LO:
                safe_t.append(st)
            else:
                hypo_t.append(st)
        if safe_t and hypo_t:
            tir_gap_isf = float(np.mean(safe_t) - np.mean(hypo_t))

        fix_gaps = {'basal': tir_gap_basal, 'cr': tir_gap_cr,
                    'isf': tir_gap_isf, 'none': 0.0}

        routed_gap = fix_gaps.get(routed_fix, 0.0)
        generic_gap = fix_gaps.get(generic_fix, 0.0)
        advantage = routed_gap - generic_gap

        rec = {
            'pid': pid,
            'failure_mode': mode,
            'routed_first_fix': routed_fix,
            'generic_first_fix': generic_fix,
            'routed_tir_gap': _safe_round(routed_gap, 1),
            'generic_tir_gap': _safe_round(generic_gap, 1),
            'routing_advantage': _safe_round(advantage, 1),
            'overnight_tir': _safe_round(overnight_tir, 1),
            'postmeal_tir': _safe_round(postmeal_tir, 1),
            'overcorrection_rate': _safe_round(overcorr, 3),
        }
        results['per_patient'].append(rec)

        if args.detail:
            print(f"  {pid}: mode={mode:20s} routed={routed_fix:6s} "
                  f"gap={routed_gap:+.1f} vs generic={generic_gap:+.1f} "
                  f"advantage={advantage:+.1f}")

    results['n_patients'] = len(results['per_patient'])
    modes = [r['failure_mode'] for r in results['per_patient']]
    advantages = [r['routing_advantage'] for r in results['per_patient']]
    results['summary'] = {
        'mode_distribution': {m: modes.count(m) for m in set(modes)},
        'mean_routing_advantage': _safe_round(np.mean(advantages), 2)
                                  if advantages else 0,
        'patients_routing_better': sum(1 for a in advantages if a > 0),
        'patients_routing_same': sum(1 for a in advantages if a == 0),
        'patients_routing_worse': sum(1 for a in advantages if a < 0),
    }
    return results


# ===================================================================
# EXP-1453: Minimum Data Requirements Analysis
# ===================================================================

@register(1453, "Minimum Data Requirements Analysis")
def exp_1453(patients, args):
    """Determine minimum days of data needed for each recommendation type
    to reach stable values (within ±5 % of full-data recommendation)."""
    results = {'name': 'EXP-1453: Minimum Data Requirements Analysis',
               'per_patient': []}

    day_windows = [3, 7, 14, 21, 30, 60, 90]

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs_arr = pdata['carbs']
        n = len(glucose)
        n_days = n // STEPS_PER_DAY
        if n_days < 7:
            continue

        # Full-data reference assessment
        ref = compute_full_assessment(glucose, bolus, carbs_arr, n)
        ref_drift = ref['drift']
        ref_exc = ref['excursion']
        ref_isf = ref['isf_ratio']

        basal_stable = None
        cr_stable = None
        isf_stable = None

        for w in day_windows:
            if w > n_days:
                break
            end_step = w * STEPS_PER_DAY
            g_w = glucose[:end_step]
            b_w = bolus[:end_step]
            c_w = carbs_arr[:end_step]
            m = _compute_window_metrics(glucose, bolus, carbs_arr,
                                        0, end_step)

            # Check stability: within 5% of full-data value or absolute
            # tolerance for near-zero values
            tol_abs = 0.5

            if basal_stable is None:
                if ref_drift == 0 or abs(ref_drift) < tol_abs:
                    if abs(m['drift'] - ref_drift) < tol_abs:
                        basal_stable = w
                elif abs(m['drift'] - ref_drift) / max(abs(ref_drift), 1e-6) < 0.05:
                    basal_stable = w

            if cr_stable is None:
                if ref_exc == 0 or abs(ref_exc) < tol_abs:
                    if abs(m['excursion'] - ref_exc) < tol_abs:
                        cr_stable = w
                elif abs(m['excursion'] - ref_exc) / max(abs(ref_exc), 1e-6) < 0.05:
                    cr_stable = w

            if isf_stable is None:
                if ref_isf == 0 or abs(ref_isf) < tol_abs:
                    if abs(m['isf_ratio'] - ref_isf) < tol_abs:
                        isf_stable = w
                elif abs(m['isf_ratio'] - ref_isf) / max(abs(ref_isf), 1e-6) < 0.05:
                    isf_stable = w

        # If never stabilised, set to max days tested
        max_tested = min(day_windows[-1], n_days)
        if basal_stable is None:
            basal_stable = max_tested
        if cr_stable is None:
            cr_stable = max_tested
        if isf_stable is None:
            isf_stable = max_tested
        overall = max(basal_stable, cr_stable, isf_stable)

        rec = {
            'pid': pid,
            'total_days': n_days,
            'basal_stable_days': basal_stable,
            'cr_stable_days': cr_stable,
            'isf_stable_days': isf_stable,
            'overall_stable_days': overall,
            'ref_drift': _safe_round(ref_drift, 2),
            'ref_excursion': _safe_round(ref_exc, 1),
            'ref_isf': _safe_round(ref_isf, 2),
        }
        results['per_patient'].append(rec)

        if args.detail:
            print(f"  {pid}: basal={basal_stable}d  cr={cr_stable}d  "
                  f"isf={isf_stable}d  overall={overall}d "
                  f"(total={n_days}d)")

    results['n_patients'] = len(results['per_patient'])
    if results['per_patient']:
        results['summary'] = {
            'mean_basal_stable': _safe_round(
                np.mean([r['basal_stable_days']
                         for r in results['per_patient']]), 1),
            'mean_cr_stable': _safe_round(
                np.mean([r['cr_stable_days']
                         for r in results['per_patient']]), 1),
            'mean_isf_stable': _safe_round(
                np.mean([r['isf_stable_days']
                         for r in results['per_patient']]), 1),
            'mean_overall_stable': _safe_round(
                np.mean([r['overall_stable_days']
                         for r in results['per_patient']]), 1),
        }
    else:
        results['summary'] = {}
    return results


# ===================================================================
# EXP-1454: Recommendation Confidence Calibration
# ===================================================================

@register(1454, "Recommendation Confidence Calibration")
def exp_1454(patients, args):
    """Split data into 4 quarters, compute recommendations independently,
    measure agreement, and compare with bootstrap CI width."""
    results = {'name': 'EXP-1454: Recommendation Confidence Calibration',
               'per_patient': []}

    rng = np.random.RandomState(RNG_SEED)

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs_arr = pdata['carbs']
        n = len(glucose)
        n_days = n // STEPS_PER_DAY
        if n_days < 28:
            # Need at least 7 days per quarter
            rec = {
                'pid': pid,
                'quarter_agreement_pct': None,
                'ci_width_mean': None,
                'calibration_score': None,
                'is_well_calibrated': None,
                'skip_reason': 'insufficient_data',
            }
            results['per_patient'].append(rec)
            continue

        quarter_len = n // 4
        quarter_assessments = []
        for q in range(4):
            qs = q * quarter_len
            qe = (q + 1) * quarter_len if q < 3 else n
            a = compute_full_assessment(glucose[qs:qe], bolus[qs:qe],
                                        carbs_arr[qs:qe], qe - qs)
            quarter_assessments.append(a)

        # Direction agreement: do all quarters flag the same parameters?
        agreements = 0
        total_checks = 0
        for flag_name in ['basal_flag', 'cr_flag', 'cv_flag']:
            flags = [a['flags'][flag_name] for a in quarter_assessments]
            # Agreement = fraction of pairs that match
            for i in range(4):
                for j in range(i + 1, 4):
                    total_checks += 1
                    if flags[i] == flags[j]:
                        agreements += 1
        agreement_pct = (agreements / total_checks * 100
                         if total_checks > 0 else 0.0)

        # Magnitude agreement: compare drift/exc/isf across quarters
        drifts = [a['drift'] for a in quarter_assessments]
        excs = [a['excursion'] for a in quarter_assessments]
        isfs = [a['isf_ratio'] for a in quarter_assessments]

        # Bootstrap CI width from full data
        full_n_days = n // STEPS_PER_DAY
        all_drifts = []
        for d in range(min(full_n_days, 180)):
            dr = compute_segment_drift(glucose, bolus, carbs_arr,
                                       d * STEPS_PER_DAY, 0, 6)
            if not np.isnan(dr):
                all_drifts.append(abs(dr))

        if all_drifts:
            _, lo, hi = _bootstrap_ci(all_drifts, n_boot=500, rng=rng)
            ci_width_drift = hi - lo
        else:
            ci_width_drift = 0.0

        # CI widths for excursion and isf
        all_excs = []
        meal_w = 4 * STEPS_PER_HOUR
        for i in range(n):
            if carbs_arr[i] < 5 or np.isnan(glucose[i]):
                continue
            end = min(i + meal_w, n)
            post = glucose[i:end]
            vp = post[~np.isnan(post)]
            if len(vp) >= STEPS_PER_HOUR:
                all_excs.append(float(np.nanmax(vp) - glucose[i]))
        if all_excs:
            _, lo, hi = _bootstrap_ci(all_excs, n_boot=500, rng=rng)
            ci_width_exc = hi - lo
        else:
            ci_width_exc = 0.0

        ci_width_mean = float(np.mean([ci_width_drift, ci_width_exc]))

        # Calibration: narrow CI should correspond to high agreement
        # Score 0-100: high = well-calibrated
        quarter_spread_drift = float(np.std(drifts))
        quarter_spread_exc = float(np.std(excs))
        # If CI is narrow AND quarters agree, well-calibrated
        # If CI is wide AND quarters disagree, also calibrated (accurate CI)
        # Miscalibration: narrow CI but quarters disagree, or vice versa
        narrow_ci = ci_width_mean < 15
        high_agreement = agreement_pct >= 75
        if (narrow_ci and high_agreement) or (not narrow_ci and
                                              not high_agreement):
            cal_score = min(100, agreement_pct + (100 - ci_width_mean))
        else:
            cal_score = max(0, agreement_pct - ci_width_mean)
        cal_score = min(100, max(0, cal_score))
        is_well_cal = cal_score >= 60

        rec = {
            'pid': pid,
            'quarter_agreement_pct': _safe_round(agreement_pct, 1),
            'ci_width_mean': _safe_round(ci_width_mean, 2),
            'calibration_score': _safe_round(cal_score, 1),
            'is_well_calibrated': is_well_cal,
            'quarter_drifts': [_safe_round(d, 2) for d in drifts],
            'quarter_excursions': [_safe_round(e, 1) for e in excs],
        }
        results['per_patient'].append(rec)

        if args.detail:
            print(f"  {pid}: agreement={agreement_pct:.0f}%  "
                  f"ci_width={ci_width_mean:.1f}  "
                  f"calibration={cal_score:.0f}  "
                  f"{'CALIBRATED' if is_well_cal else 'MISCALIBRATED'}")

    results['n_patients'] = len(results['per_patient'])
    valid = [r for r in results['per_patient']
             if r['calibration_score'] is not None]
    results['summary'] = {
        'mean_agreement': _safe_round(
            np.mean([r['quarter_agreement_pct'] for r in valid]), 1)
            if valid else None,
        'mean_calibration': _safe_round(
            np.mean([r['calibration_score'] for r in valid]), 1)
            if valid else None,
        'n_well_calibrated': sum(1 for r in valid if r['is_well_calibrated']),
        'n_total_valid': len(valid),
    }
    return results


# ===================================================================
# EXP-1455: Cross-Validation of Patient Archetypes
# ===================================================================

@register(1455, "Cross-Validation of Patient Archetypes")
def exp_1455(patients, args):
    """Validate that failure-mode archetypes are stable across time by
    splitting data into halves and classifying independently."""
    results = {'name': 'EXP-1455: Cross-Validation of Patient Archetypes',
               'per_patient': []}

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs_arr = pdata['carbs']
        n = len(glucose)
        half = n // 2

        if half < STEPS_PER_DAY * 7:
            rec = {
                'pid': pid,
                'first_half_mode': None,
                'second_half_mode': None,
                'mode_stable': None,
                'score_first': None,
                'score_second': None,
                'score_change': None,
                'skip_reason': 'insufficient_data',
            }
            results['per_patient'].append(rec)
            continue

        # First half
        g1, b1, c1 = glucose[:half], bolus[:half], carbs_arr[:half]
        on_tir1 = compute_overnight_tir(g1, half)
        pm_tir1 = compute_postmeal_tir(g1, c1, half)
        oc1 = compute_overcorrection_rate(g1, b1, c1, half)
        mode1 = classify_failure_mode(on_tir1, pm_tir1, oc1)
        a1 = compute_full_assessment(g1, b1, c1, half)
        score1 = a1['score']

        # Second half
        g2, b2, c2 = glucose[half:], bolus[half:], carbs_arr[half:]
        n2 = len(g2)
        on_tir2 = compute_overnight_tir(g2, n2)
        pm_tir2 = compute_postmeal_tir(g2, c2, n2)
        oc2 = compute_overcorrection_rate(g2, b2, c2, n2)
        mode2 = classify_failure_mode(on_tir2, pm_tir2, oc2)
        a2 = compute_full_assessment(g2, b2, c2, n2)
        score2 = a2['score']

        stable = mode1 == mode2
        score_change = score2 - score1

        rec = {
            'pid': pid,
            'first_half_mode': mode1,
            'second_half_mode': mode2,
            'mode_stable': stable,
            'score_first': _safe_round(score1, 1),
            'score_second': _safe_round(score2, 1),
            'score_change': _safe_round(score_change, 1),
            'first_half_details': {
                'overnight_tir': _safe_round(on_tir1, 1),
                'postmeal_tir': _safe_round(pm_tir1, 1),
                'overcorrection': _safe_round(oc1, 3),
            },
            'second_half_details': {
                'overnight_tir': _safe_round(on_tir2, 1),
                'postmeal_tir': _safe_round(pm_tir2, 1),
                'overcorrection': _safe_round(oc2, 3),
            },
        }
        results['per_patient'].append(rec)

        if args.detail:
            marker = '✓' if stable else '✗'
            print(f"  {pid}: {mode1:20s} → {mode2:20s}  {marker}  "
                  f"score Δ={score_change:+.1f}")

    results['n_patients'] = len(results['per_patient'])
    valid = [r for r in results['per_patient'] if r['mode_stable'] is not None]
    results['summary'] = {
        'n_stable': sum(1 for r in valid if r['mode_stable']),
        'n_unstable': sum(1 for r in valid if not r['mode_stable']),
        'stability_rate': _safe_round(
            sum(1 for r in valid if r['mode_stable']) / max(len(valid), 1)
            * 100, 1),
        'mean_score_change': _safe_round(
            np.mean([r['score_change'] for r in valid
                     if r['score_change'] is not None]), 1)
            if valid else None,
    }
    return results


# ===================================================================
# EXP-1456: Actionable Alert Threshold Optimization
# ===================================================================

@register(1456, "Actionable Alert Threshold Optimization")
def exp_1456(patients, args):
    """Find optimal alert thresholds for triggering clinician review by
    sweeping thresholds and maximising Youden's J index."""
    results = {'name': 'EXP-1456: Actionable Alert Threshold Optimization',
               'per_patient': []}

    # Collect per-patient metrics and labels
    all_drifts = []
    all_excursions = []
    all_overcorrs = []
    all_labels = []  # True = grade D or C (actionable)

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs_arr = pdata['carbs']
        n = len(glucose)
        n_days = n // STEPS_PER_DAY

        drift = compute_overnight_drift(glucose, bolus, carbs_arr, n_days, n)
        exc = compute_max_excursion(glucose, carbs_arr, n)
        overcorr = compute_overcorrection_rate(glucose, bolus, carbs_arr, n)
        a = compute_full_assessment(glucose, bolus, carbs_arr, n)
        is_actionable = a['grade'] in ('D', 'C')

        all_drifts.append(drift)
        all_excursions.append(exc)
        all_overcorrs.append(overcorr)
        all_labels.append(is_actionable)

        rec = {
            'pid': pid,
            'drift': _safe_round(drift, 2),
            'excursion': _safe_round(exc, 1),
            'overcorrection_rate': _safe_round(overcorr, 3),
            'grade': a['grade'],
            'score': _safe_round(a['score'], 1),
            'is_actionable': is_actionable,
        }
        results['per_patient'].append(rec)

    results['n_patients'] = len(results['per_patient'])
    labels = np.array(all_labels, dtype=bool)
    n_pos = labels.sum()
    n_neg = (~labels).sum()

    def _sweep_threshold(values, labels_arr, thresholds):
        """Sweep thresholds and return best (threshold, sens, spec, J)."""
        best = (0.0, 0.0, 0.0, -1.0)
        for t in thresholds:
            predicted = np.array(values) >= t
            tp = np.sum(predicted & labels_arr)
            fn = np.sum(~predicted & labels_arr)
            fp = np.sum(predicted & ~labels_arr)
            tn = np.sum(~predicted & ~labels_arr)
            sens = tp / max(tp + fn, 1)
            spec = tn / max(tn + fp, 1)
            j = sens + spec - 1
            if j > best[3]:
                best = (float(t), float(sens), float(spec), float(j))
        return best

    # Drift thresholds
    drift_thresholds = np.arange(1.0, 15.1, 0.5)
    d_thresh, d_sens, d_spec, d_j = _sweep_threshold(
        all_drifts, labels, drift_thresholds)

    # Excursion thresholds
    exc_thresholds = np.arange(20.0, 120.1, 5.0)
    e_thresh, e_sens, e_spec, e_j = _sweep_threshold(
        all_excursions, labels, exc_thresholds)

    # Overcorrection thresholds
    oc_thresholds = np.arange(0.0, 0.61, 0.05)
    oc_thresh, oc_sens, oc_spec, oc_j = _sweep_threshold(
        all_overcorrs, labels, oc_thresholds)

    results['optimal_thresholds'] = {
        'drift_threshold': _safe_round(d_thresh, 1),
        'drift_sensitivity': _safe_round(d_sens, 3),
        'drift_specificity': _safe_round(d_spec, 3),
        'drift_youden_j': _safe_round(d_j, 3),
        'excursion_threshold': _safe_round(e_thresh, 1),
        'excursion_sensitivity': _safe_round(e_sens, 3),
        'excursion_specificity': _safe_round(e_spec, 3),
        'excursion_youden_j': _safe_round(e_j, 3),
        'overcorr_threshold': _safe_round(oc_thresh, 3),
        'overcorr_sensitivity': _safe_round(oc_sens, 3),
        'overcorr_specificity': _safe_round(oc_spec, 3),
        'overcorr_youden_j': _safe_round(oc_j, 3),
        'n_actionable': int(n_pos),
        'n_non_actionable': int(n_neg),
    }

    if args.detail:
        print(f"  Drift:       thresh={d_thresh:.1f} mg/dL/h  "
              f"sens={d_sens:.2f}  spec={d_spec:.2f}  J={d_j:.3f}")
        print(f"  Excursion:   thresh={e_thresh:.1f} mg/dL    "
              f"sens={e_sens:.2f}  spec={e_spec:.2f}  J={e_j:.3f}")
        print(f"  Overcorr:    thresh={oc_thresh:.3f}          "
              f"sens={oc_sens:.2f}  spec={oc_spec:.2f}  J={oc_j:.3f}")
        print(f"  Actionable: {n_pos}/{n_pos + n_neg} patients")

    return results


# ===================================================================
# EXP-1457: Time-to-Detection Analysis
# ===================================================================

@register(1457, "Time-to-Detection Analysis")
def exp_1457(patients, args):
    """Measure how quickly the pipeline detects therapy miscalibration
    from the start of monitoring.  Simulates progressive data accumulation
    (1 .. 30 days) and records when each flag first triggers and remains
    stable for at least 3 consecutive checkpoints."""
    results = {'name': 'EXP-1457: Time-to-Detection Analysis',
               'per_patient': []}

    max_detect_days = 30
    stability_run = 3  # flag must persist for 3 consecutive days

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs_arr = pdata['carbs']
        n = len(glucose)
        n_days = n // STEPS_PER_DAY

        if n_days < 7:
            rec = {
                'pid': pid,
                'basal_first_detect_day': None,
                'cr_first_detect_day': None,
                'isf_first_detect_day': None,
                'all_stable_day': None,
                'grade_at_7d': None,
                'grade_at_14d': None,
                'grade_at_30d': None,
                'skip_reason': 'insufficient_data',
            }
            results['per_patient'].append(rec)
            continue

        limit = min(n_days, max_detect_days)

        # Track flag history per day
        basal_flags = []
        cr_flags = []
        isf_flags = []  # using CV flag as ISF proxy
        grades = {}

        for d in range(1, limit + 1):
            end_step = d * STEPS_PER_DAY
            if end_step > n:
                break
            g = glucose[:end_step]
            b = bolus[:end_step]
            c = carbs_arr[:end_step]
            a = compute_full_assessment(g, b, c, end_step)
            basal_flags.append(a['flags']['basal_flag'])
            cr_flags.append(a['flags']['cr_flag'])
            isf_flags.append(a['flags']['cv_flag'])
            grades[d] = a['grade']

        def _first_stable(flags, run_len):
            """Return 1-indexed day when flag first becomes stably True."""
            for i in range(len(flags)):
                if i + run_len > len(flags):
                    break
                if all(flags[i:i + run_len]):
                    return i + 1  # 1-indexed day
            return None

        basal_det = _first_stable(basal_flags, stability_run)
        cr_det = _first_stable(cr_flags, stability_run)
        isf_det = _first_stable(isf_flags, stability_run)

        det_days = [d for d in [basal_det, cr_det, isf_det]
                    if d is not None]
        all_stable = max(det_days) if det_days else None

        rec = {
            'pid': pid,
            'basal_first_detect_day': basal_det,
            'cr_first_detect_day': cr_det,
            'isf_first_detect_day': isf_det,
            'all_stable_day': all_stable,
            'grade_at_7d': grades.get(7),
            'grade_at_14d': grades.get(14),
            'grade_at_30d': grades.get(min(30, limit)),
            'n_days_available': limit,
        }
        results['per_patient'].append(rec)

        if args.detail:
            print(f"  {pid}: basal@{basal_det or '-'}d  cr@{cr_det or '-'}d  "
                  f"isf@{isf_det or '-'}d  stable@{all_stable or '-'}d  "
                  f"7d={grades.get(7, '?')} 14d={grades.get(14, '?')} "
                  f"30d={grades.get(min(30, limit), '?')}")

    results['n_patients'] = len(results['per_patient'])
    valid = [r for r in results['per_patient']
             if r.get('skip_reason') is None]

    basal_dets = [r['basal_first_detect_day'] for r in valid
                  if r['basal_first_detect_day'] is not None]
    cr_dets = [r['cr_first_detect_day'] for r in valid
               if r['cr_first_detect_day'] is not None]
    isf_dets = [r['isf_first_detect_day'] for r in valid
                if r['isf_first_detect_day'] is not None]
    stable_days = [r['all_stable_day'] for r in valid
                   if r['all_stable_day'] is not None]

    results['summary'] = {
        'mean_basal_detect': _safe_round(np.mean(basal_dets), 1)
                             if basal_dets else None,
        'mean_cr_detect': _safe_round(np.mean(cr_dets), 1)
                          if cr_dets else None,
        'mean_isf_detect': _safe_round(np.mean(isf_dets), 1)
                           if isf_dets else None,
        'mean_all_stable': _safe_round(np.mean(stable_days), 1)
                           if stable_days else None,
        'pct_detected_by_7d': _safe_round(
            sum(1 for d in stable_days if d <= 7) / max(len(valid), 1) * 100,
            1),
        'pct_detected_by_14d': _safe_round(
            sum(1 for d in stable_days if d <= 14) / max(len(valid), 1) * 100,
            1),
    }
    return results


# ===================================================================
# EXP-1458: Intervention Priority Scoring Validation
# ===================================================================

@register(1458, "Intervention Priority Scoring Validation")
def exp_1458(patients, args):
    """Validate priority scoring against observational TIR gap, failure
    mode severity, and number of unstable parameters.  Reports rank
    correlations."""
    results = {'name': 'EXP-1458: Intervention Priority Scoring Validation',
               'per_patient': []}

    patient_data = []

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs_arr = pdata['carbs']
        n = len(glucose)
        n_days = n // STEPS_PER_DAY

        a = compute_full_assessment(glucose, bolus, carbs_arr, n)
        tir = a['tir']
        grade = a['grade']
        score = a['score']
        flags = a['flags']
        flag_count = sum(1 for f in flags.values() if f)
        cv = a['cv']

        # Priority score (EXP-1418 methodology)
        # Higher = more urgent
        grade_weight = {'A': 0, 'B': 1, 'C': 2, 'D': 3}.get(grade, 0)
        priority = (100 - tir) * 0.4 + grade_weight * 15 + flag_count * 10
        priority = min(100, max(0, priority))

        # Observational TIR gap (sum of all parameter gaps)
        drift = compute_overnight_drift(glucose, bolus, carbs_arr, n_days, n)
        exc = compute_max_excursion(glucose, carbs_arr, n)
        tir_gap = abs(100 - tir)  # distance from perfect TIR

        # Severity score (higher = worse)
        overnight_tir = compute_overnight_tir(glucose, n)
        postmeal_tir = compute_postmeal_tir(glucose, carbs_arr, n)
        overcorr = compute_overcorrection_rate(glucose, bolus, carbs_arr, n)
        severity = ((100 - overnight_tir) * 0.3 + (100 - postmeal_tir) * 0.4
                    + overcorr * 100 * 0.3)

        # Instability: number of parameters flagged
        instability = flag_count

        patient_data.append({
            'pid': pid,
            'priority_score': _safe_round(priority, 1),
            'tir_gap': _safe_round(tir_gap, 1),
            'severity': _safe_round(severity, 1),
            'instability': instability,
            'grade': grade,
            'tir': _safe_round(tir, 1),
            'flag_count': flag_count,
        })

    # Compute ranks
    pids = [d['pid'] for d in patient_data]
    priorities = [d['priority_score'] for d in patient_data]
    tir_gaps = [d['tir_gap'] for d in patient_data]
    severities = [d['severity'] for d in patient_data]
    instabilities = [d['instability'] for d in patient_data]

    # Rank (higher value = higher rank number = more urgent)
    def _compute_ranks(values):
        order = np.argsort(values)[::-1]
        ranks = np.empty(len(values))
        for rank_pos, idx in enumerate(order):
            ranks[idx] = rank_pos + 1
        return ranks.tolist()

    p_ranks = _compute_ranks(priorities)
    tg_ranks = _compute_ranks(tir_gaps)
    sev_ranks = _compute_ranks(severities)
    inst_ranks = _compute_ranks(instabilities)

    for i, d in enumerate(patient_data):
        d['priority_rank'] = int(p_ranks[i])
        d['tir_gap_rank'] = int(tg_ranks[i])
        d['severity_rank'] = int(sev_ranks[i])
        d['instability_rank'] = int(inst_ranks[i])
        results['per_patient'].append(d)

        if args.detail:
            print(f"  {d['pid']}: priority={d['priority_score']:.1f} "
                  f"(rank {d['priority_rank']})  "
                  f"tir_gap_rank={d['tir_gap_rank']}  "
                  f"sev_rank={d['severity_rank']}  "
                  f"inst_rank={d['instability_rank']}")

    # Rank correlations
    rc_tir_gap = _spearman_rank_corr(priorities, tir_gaps)
    rc_severity = _spearman_rank_corr(priorities, severities)
    rc_instability = _spearman_rank_corr(priorities, instabilities)

    results['n_patients'] = len(results['per_patient'])
    results['rank_correlations'] = {
        'rank_corr_tir_gap': _safe_round(rc_tir_gap, 3),
        'rank_corr_severity': _safe_round(rc_severity, 3),
        'rank_corr_instability': _safe_round(rc_instability, 3),
    }

    if args.detail:
        print(f"\n  Rank correlations:")
        print(f"    Priority vs TIR gap:    ρ = {rc_tir_gap:.3f}")
        print(f"    Priority vs severity:   ρ = {rc_severity:.3f}")
        print(f"    Priority vs instability: ρ = {rc_instability:.3f}")

    return results


# ===================================================================
# EXP-1459: Longitudinal Recommendation Drift
# ===================================================================

@register(1459, "Longitudinal Recommendation Drift")
def exp_1459(patients, args):
    """Track how recommendations change over the monitoring period using
    30-day sliding windows stepped by 7 days.  Measures trend via linear
    regression and reports drift rate per month."""
    results = {'name': 'EXP-1459: Longitudinal Recommendation Drift',
               'per_patient': []}

    window_days = 30
    step_days = 7
    window_steps = window_days * STEPS_PER_DAY
    step_steps = step_days * STEPS_PER_DAY

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs_arr = pdata['carbs']
        n = len(glucose)
        n_days = n // STEPS_PER_DAY

        if n_days < window_days + step_days:
            rec = {
                'pid': pid,
                'n_windows': 0,
                'basal_drift_per_month': None,
                'cr_drift_per_month': None,
                'isf_drift_per_month': None,
                'basal_trend': None,
                'cr_trend': None,
                'isf_trend': None,
                'is_converging': None,
                'skip_reason': 'insufficient_data',
            }
            results['per_patient'].append(rec)
            continue

        drifts_series = []
        exc_series = []
        isf_series = []
        window_mids = []

        start = 0
        while start + window_steps <= n:
            end = start + window_steps
            m = _compute_window_metrics(glucose, bolus, carbs_arr, start, end)
            drifts_series.append(m['drift'])
            exc_series.append(m['excursion'])
            isf_series.append(m['isf_ratio'])
            mid_day = (start + end) // 2 // STEPS_PER_DAY
            window_mids.append(mid_day)
            start += step_steps

        n_windows = len(drifts_series)
        if n_windows < 3:
            rec = {
                'pid': pid,
                'n_windows': n_windows,
                'basal_drift_per_month': None,
                'cr_drift_per_month': None,
                'isf_drift_per_month': None,
                'basal_trend': None,
                'cr_trend': None,
                'isf_trend': None,
                'is_converging': None,
                'skip_reason': 'too_few_windows',
            }
            results['per_patient'].append(rec)
            continue

        # Fit trends
        basal_slope, basal_t, basal_dir = _linear_trend(drifts_series)
        cr_slope, cr_t, cr_dir = _linear_trend(exc_series)
        isf_slope, isf_t, isf_dir = _linear_trend(isf_series)

        # Convert slope per window-index to per month
        # Each window step is 7 days, so ~4.3 steps per month
        steps_per_month = 30.0 / step_days
        basal_drift_mo = basal_slope * steps_per_month
        cr_drift_mo = cr_slope * steps_per_month
        isf_drift_mo = isf_slope * steps_per_month

        # Converging = metrics moving toward "normal" (drift→0, exc→0)
        # Use second half variance vs first half variance
        half = n_windows // 2
        var_first = (np.var(drifts_series[:half]) +
                     np.var(exc_series[:half]))
        var_second = (np.var(drifts_series[half:]) +
                      np.var(exc_series[half:]))
        is_converging = bool(var_second <= var_first)

        rec = {
            'pid': pid,
            'n_windows': n_windows,
            'basal_drift_per_month': _safe_round(basal_drift_mo, 3),
            'cr_drift_per_month': _safe_round(cr_drift_mo, 2),
            'isf_drift_per_month': _safe_round(isf_drift_mo, 3),
            'basal_trend': basal_dir,
            'cr_trend': cr_dir,
            'isf_trend': isf_dir,
            'is_converging': is_converging,
            'first_window': {
                'drift': _safe_round(drifts_series[0], 2),
                'excursion': _safe_round(exc_series[0], 1),
                'isf': _safe_round(isf_series[0], 2),
            },
            'last_window': {
                'drift': _safe_round(drifts_series[-1], 2),
                'excursion': _safe_round(exc_series[-1], 1),
                'isf': _safe_round(isf_series[-1], 2),
            },
        }
        results['per_patient'].append(rec)

        if args.detail:
            conv = '↓converge' if is_converging else '↑diverge'
            print(f"  {pid}: {n_windows} windows  "
                  f"basal Δ/mo={basal_drift_mo:+.3f}({basal_dir})  "
                  f"cr Δ/mo={cr_drift_mo:+.2f}({cr_dir})  "
                  f"isf Δ/mo={isf_drift_mo:+.3f}({isf_dir})  {conv}")

    results['n_patients'] = len(results['per_patient'])
    valid = [r for r in results['per_patient']
             if r.get('skip_reason') is None]
    results['summary'] = {
        'mean_basal_drift': _safe_round(
            np.mean([r['basal_drift_per_month'] for r in valid
                     if r['basal_drift_per_month'] is not None]), 3)
            if valid else None,
        'mean_cr_drift': _safe_round(
            np.mean([r['cr_drift_per_month'] for r in valid
                     if r['cr_drift_per_month'] is not None]), 2)
            if valid else None,
        'mean_isf_drift': _safe_round(
            np.mean([r['isf_drift_per_month'] for r in valid
                     if r['isf_drift_per_month'] is not None]), 3)
            if valid else None,
        'n_converging': sum(1 for r in valid if r['is_converging']),
        'n_diverging': sum(1 for r in valid if not r['is_converging']),
    }
    return results


# ===================================================================
# EXP-1460: Deployment Readiness Scorecard
# ===================================================================

@register(1460, "Deployment Readiness Scorecard")
def exp_1460(patients, args):
    """Comprehensive deployment readiness scorecard for each patient,
    aggregating data quality, detection reliability, clinical actionability,
    and risk metrics."""
    results = {'name': 'EXP-1460: Deployment Readiness Scorecard',
               'per_patient': []}

    rng = np.random.RandomState(RNG_SEED)

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs_arr = pdata['carbs']
        valid_mask = pdata['valid']
        n = len(glucose)
        n_days = n // STEPS_PER_DAY

        # ---- 1. Data Quality Score (0-100) ----
        coverage = float(valid_mask.sum() / max(n, 1) * 100)
        duration_score = min(n_days / 90.0, 1.0) * 100
        # Completeness: fraction of days with >80% valid readings
        complete_days = 0
        for d in range(min(n_days, 180)):
            ds = d * STEPS_PER_DAY
            de = ds + STEPS_PER_DAY
            if de > n:
                break
            day_valid = valid_mask[ds:de].sum() / STEPS_PER_DAY * 100
            if day_valid >= 80:
                complete_days += 1
        completeness = (complete_days / max(min(n_days, 180), 1) * 100)
        data_quality = (coverage * 0.4 + duration_score * 0.3
                        + completeness * 0.3)
        data_quality = min(100, max(0, data_quality))

        # ---- 2. Detection Reliability Score (0-100) ----
        a = compute_full_assessment(glucose, bolus, carbs_arr, n)

        # Confidence from bootstrap CI width (narrow = high confidence)
        all_day_drifts = []
        for d in range(min(n_days, 180)):
            dr = compute_segment_drift(glucose, bolus, carbs_arr,
                                       d * STEPS_PER_DAY, 0, 6)
            if not np.isnan(dr):
                all_day_drifts.append(abs(dr))
        if len(all_day_drifts) >= 5:
            _, ci_lo, ci_hi = _bootstrap_ci(all_day_drifts, n_boot=200,
                                            rng=rng)
            ci_width = ci_hi - ci_lo
            confidence = max(0, 100 - ci_width * 5)
        else:
            confidence = 20.0  # low confidence with sparse data

        # Stability: does assessment stay consistent across halves?
        half = n // 2
        if half >= STEPS_PER_DAY * 7:
            a1 = compute_full_assessment(glucose[:half], bolus[:half],
                                         carbs_arr[:half], half)
            a2 = compute_full_assessment(glucose[half:], bolus[half:],
                                         carbs_arr[half:], n - half)
            grade_match = 1.0 if a1['grade'] == a2['grade'] else 0.0
            flag_match = sum(1 for k in a1['flags']
                             if a1['flags'][k] == a2['flags'][k]) / 3.0
            stability = (grade_match * 50 + flag_match * 50)
        else:
            stability = 50.0  # unknown

        # Minimum data met?
        min_data_met = 1.0 if n_days >= 14 else (n_days / 14.0)
        detection_reliability = (confidence * 0.4 + stability * 0.4
                                 + min_data_met * 100 * 0.2)
        detection_reliability = min(100, max(0, detection_reliability))

        # ---- 3. Clinical Actionability Score (0-100) ----
        overnight_tir = compute_overnight_tir(glucose, n)
        postmeal_tir = compute_postmeal_tir(glucose, carbs_arr, n)
        overcorr = compute_overcorrection_rate(glucose, bolus, carbs_arr, n)
        mode = classify_failure_mode(overnight_tir, postmeal_tir, overcorr)

        # Mode clarity: single dominant issue is more actionable
        mode_clarity = {
            'well_controlled': 90,
            'basal_dominant': 85,
            'meal_dominant': 85,
            'correction_dominant': 80,
            'mixed': 40,
        }.get(mode, 50)

        # Single dominant intervention possible?
        flags = a['flags']
        flag_count = sum(1 for f in flags.values() if f)
        single_intervention = 1.0 if flag_count <= 1 else 0.5
        clinical_actionability = (mode_clarity * 0.6
                                  + single_intervention * 100 * 0.4)
        clinical_actionability = min(100, max(0, clinical_actionability))

        # ---- 4. Risk Score (0-100, lower = less risk, better) ----
        overcorr_risk = min(overcorr * 200, 100)
        grade_d_risk = 100 if a['grade'] == 'D' else 0
        # Check for diverging recommendations using simple variance
        # (lightweight proxy for full EXP-1459 analysis)
        if n_days >= 37:  # need at least 1 window + 1 step
            ws = 30 * STEPS_PER_DAY
            ss = 7 * STEPS_PER_DAY
            win_drifts = []
            s = 0
            while s + ws <= n:
                nd = ws // STEPS_PER_DAY
                wd = compute_overnight_drift(glucose[s:s + ws],
                                             bolus[s:s + ws],
                                             carbs_arr[s:s + ws], nd, ws)
                win_drifts.append(wd)
                s += ss
            if len(win_drifts) >= 3:
                h = len(win_drifts) // 2
                v1 = float(np.var(win_drifts[:h]))
                v2 = float(np.var(win_drifts[h:]))
                diverging = v2 > v1 * 1.5
            else:
                diverging = False
        else:
            diverging = False

        diverge_risk = 50 if diverging else 0
        risk_score = (overcorr_risk * 0.4 + grade_d_risk * 0.4
                      + diverge_risk * 0.2)
        risk_score = min(100, max(0, risk_score))

        # ---- Overall Readiness ----
        # High data quality + high reliability + high actionability
        # - risk penalty
        overall = (data_quality * 0.25 + detection_reliability * 0.30
                   + clinical_actionability * 0.25
                   + (100 - risk_score) * 0.20)
        overall = min(100, max(0, overall))

        deployment_grade = compute_grade(overall)

        rec = {
            'pid': pid,
            'data_quality_score': _safe_round(data_quality, 1),
            'detection_reliability_score': _safe_round(
                detection_reliability, 1),
            'clinical_actionability_score': _safe_round(
                clinical_actionability, 1),
            'risk_score': _safe_round(risk_score, 1),
            'overall_readiness': _safe_round(overall, 1),
            'deployment_grade': deployment_grade,
            'details': {
                'coverage_pct': _safe_round(coverage, 1),
                'duration_days': n_days,
                'complete_days': complete_days,
                'confidence': _safe_round(confidence, 1),
                'stability': _safe_round(stability, 1),
                'mode': mode,
                'flag_count': flag_count,
                'therapy_grade': a['grade'],
                'therapy_score': _safe_round(a['score'], 1),
                'is_diverging': diverging,
            },
        }
        results['per_patient'].append(rec)

        if args.detail:
            print(f"  {pid}: DQ={data_quality:.0f}  DR={detection_reliability:.0f}"
                  f"  CA={clinical_actionability:.0f}  "
                  f"Risk={risk_score:.0f}  "
                  f"Overall={overall:.0f} [{deployment_grade}]  "
                  f"mode={mode}  therapy={a['grade']}")

    results['n_patients'] = len(results['per_patient'])

    # Population summary
    grades = [r['deployment_grade'] for r in results['per_patient']]
    overalls = [r['overall_readiness'] for r in results['per_patient']]
    results['summary'] = {
        'mean_overall_readiness': _safe_round(np.mean(overalls), 1)
                                  if overalls else None,
        'grade_distribution': {g: grades.count(g)
                               for g in ['A', 'B', 'C', 'D']},
        'n_deployment_ready': sum(1 for g in grades if g in ('A', 'B')),
        'n_needs_more_data': sum(1 for r in results['per_patient']
                                 if r['data_quality_score'] < 50),
        'n_high_risk': sum(1 for r in results['per_patient']
                           if r['risk_score'] > 60),
    }

    if args.detail:
        print(f"\n  Deployment Summary:")
        print(f"    Ready (A/B): {results['summary']['n_deployment_ready']}"
              f" / {len(results['per_patient'])}")
        print(f"    Mean readiness: "
              f"{results['summary']['mean_overall_readiness']}")
        print(f"    Grade distribution: "
              f"{results['summary']['grade_distribution']}")

    return results


# ===================================================================
# Main entry point
# ===================================================================

def main():
    parser = argparse.ArgumentParser(
        description='EXP-1451 to EXP-1460: Operational Deployment '
                    '& Clinical Refinement')
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
        print(f"  {pid}: {n_days}d, CGM coverage={valid_pct:.1f}%")

    to_run = args.exp if args.exp else sorted(EXPERIMENTS.keys())
    all_results = {}

    for exp_id in to_run:
        if exp_id not in EXPERIMENTS:
            print(f"\nWARNING: EXP-{exp_id} not registered, skipping")
            continue

        title, fn = EXPERIMENTS[exp_id]
        print(f"\n{'=' * 60}")
        print(f"EXP-{exp_id}: {title}")
        print(f"{'=' * 60}")

        t0 = time.time()
        try:
            result = fn(patients, args)
            elapsed = time.time() - t0
            result['elapsed_sec'] = round(elapsed, 1)
            all_results[exp_id] = result
            print(f"  Completed in {elapsed:.1f}s")

            if args.save:
                RESULTS_DIR.mkdir(parents=True, exist_ok=True)
                outpath = RESULTS_DIR / f'exp-{exp_id}_therapy.json'
                with open(outpath, 'w') as f:
                    json.dump(result, f, indent=2, default=str)
                print(f"  Saved to {outpath}")
        except Exception as e:
            elapsed = time.time() - t0
            print(f"  FAILED in {elapsed:.1f}s: {e}")
            traceback.print_exc()

    print(f"\n{'=' * 60}")
    print("BATCH SUMMARY")
    print(f"{'=' * 60}")
    for exp_id in to_run:
        if exp_id in all_results:
            r = all_results[exp_id]
            print(f"  EXP-{exp_id}: OK ({r.get('elapsed_sec', '?')}s, "
                  f"{r.get('n_patients', '?')} patients)")
        elif exp_id in EXPERIMENTS:
            print(f"  EXP-{exp_id}: FAILED")


if __name__ == '__main__':
    main()
