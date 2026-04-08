#!/usr/bin/env python3
"""EXP-1461 to EXP-1470: Practical Implementation & Edge Cases.

This batch validates the therapy detection pipeline under real-world
deployment conditions.  It covers sparse data robustness, pump mode
transitions, CGM noise tolerance, seasonal patterns, aggregation
strategies, calibration artifacts, recommendation conflicts, dose
rounding constraints, patient communication summaries, and end-to-end
integration testing.
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

# Grade boundaries  (score -> letter)
GRADE_D_CEIL = 50
GRADE_C_CEIL = 65
GRADE_B_CEIL = 80

# Score composition weights
SCORE_WEIGHTS = {'tir': 60, 'basal': 15, 'cr': 15, 'isf': 5, 'cv': 5}
DRIFT_THRESHOLD = 5.0       # mg/dL/h
EXCURSION_THRESHOLD = 70    # mg/dL  (90-th %ile post-meal rise)
CV_THRESHOLD = 36           # %
MIN_BOLUS_ISF = 2.0         # U -- minimum correction bolus for ISF calc
MIN_ISF_EVENTS = 5

CONSERVATIVE_BASAL_PCT = 10     # +/-10 %
CR_ADJUST_STANDARD = 30        # -30 %
CR_ADJUST_GRADE_D = 50         # -50 %
ISF_ADJUST_PCT = 10            # +/-10 %
DIA_DEFAULT = 6.0              # hours

N_BOOTSTRAP = 1000
RNG_SEED = 42

# Degradation levels for EXP-1461
DEGRADATION_LEVELS = [0.10, 0.20, 0.30, 0.50]

# Noise parameters for EXP-1463
GAUSSIAN_SIGMAS = [5, 10, 15]

# Pump limits for EXP-1468
PUMP_DOSE_STEP = 0.05        # U (minimum increment)
PUMP_MIN_BASAL = 0.05        # U/h
PUMP_MAX_BASAL = 5.0         # U/h
PUMP_MAX_BOLUS = 25.0        # U

EXPERIMENTS = {}


# ---------------------------------------------------------------------------
# Experiment registration
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


# ---------------------------------------------------------------------------
# Helper functions -- glucose metrics
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
    """Map numeric score -> letter grade."""
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


# ---------------------------------------------------------------------------
# Helper functions -- time utilities
# ---------------------------------------------------------------------------

def hour_of_step(idx):
    """Return hour-of-day (0-23) for a given step index."""
    return (idx % STEPS_PER_DAY) // STEPS_PER_HOUR


def day_of_step(idx):
    """Return 0-indexed day number for a given step index."""
    return idx // STEPS_PER_DAY


# ---------------------------------------------------------------------------
# Helper functions -- drift & excursion
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Helper functions -- ISF & therapy scoring
# ---------------------------------------------------------------------------

def compute_isf_ratio(glucose, bolus, carbs, n):
    """Deconfounded ISF from correction boluses >= 2 U with no nearby carbs."""
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


# ---------------------------------------------------------------------------
# Helper functions -- time-of-day TIR
# ---------------------------------------------------------------------------

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
    """TIR restricted to 4 h post-meal windows (>= 5 g carbs)."""
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


# ---------------------------------------------------------------------------
# Helper functions -- failure mode classification
# ---------------------------------------------------------------------------

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
    """5-way failure-mode classification.

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
        'mixed': 'basal',
    }.get(mode, 'basal')


# ---------------------------------------------------------------------------
# Helper functions -- statistical utilities
# ---------------------------------------------------------------------------

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
    nn = len(x)
    return float(1 - 6 * np.sum(d ** 2) / (nn * (nn ** 2 - 1)))


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


# ---------------------------------------------------------------------------
# Helper functions -- recommendation generation
# ---------------------------------------------------------------------------

def generate_recommendations(assessment):
    """Generate therapy parameter recommendations from an assessment dict.

    Returns a list of recommendation dicts with keys:
        parameter, direction, magnitude_pct, rationale
    """
    recs = []
    flags = assessment.get('flags', {})
    grade = assessment.get('grade', 'B')

    if flags.get('basal_flag', False):
        drift = assessment.get('drift', 0.0)
        direction = 'increase' if drift > 0 else 'decrease'
        recs.append({
            'parameter': 'basal',
            'direction': direction,
            'magnitude_pct': CONSERVATIVE_BASAL_PCT,
            'rationale': f'overnight drift {drift:+.1f} mg/dL/h',
        })

    if flags.get('cr_flag', False):
        adj = CR_ADJUST_GRADE_D if grade == 'D' else CR_ADJUST_STANDARD
        recs.append({
            'parameter': 'cr',
            'direction': 'decrease',
            'magnitude_pct': adj,
            'rationale': (f'postmeal excursion '
                          f'{assessment.get("excursion", 0):.0f} mg/dL'),
        })

    if flags.get('cv_flag', False):
        recs.append({
            'parameter': 'isf',
            'direction': 'increase',
            'magnitude_pct': ISF_ADJUST_PCT,
            'rationale': f'CV {assessment.get("cv", 0):.1f}% > {CV_THRESHOLD}%',
        })

    return recs


def round_to_step(value, step=PUMP_DOSE_STEP):
    """Round a value to the nearest step increment."""
    if step <= 0:
        return value
    return round(round(value / step) * step, 4)


def classify_urgency(grade, tir, cv):
    """Classify clinical urgency from grade, TIR, and CV."""
    if grade == 'D' or tir < 40:
        return 'immediate'
    if grade == 'C' or tir < 55:
        return 'soon'
    if grade == 'B':
        return 'routine'
    return 'monitoring-only'


# ===================================================================
# EXP-1461: Sparse Data Robustness
# ===================================================================

@register(1461, "Sparse Data Robustness")
def exp_1461(patients, args):
    """Test pipeline performance under degraded data conditions.

    Artificially drops 10%, 20%, 30%, 50% of CGM readings and measures
    grade stability, flag agreement, and recommendation deviation.
    """
    results = {'name': 'EXP-1461: Sparse Data Robustness',
               'per_patient': []}

    rng = np.random.RandomState(RNG_SEED)

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose'].copy()
        bolus = pdata['bolus']
        carbs_arr = pdata['carbs']
        n = len(glucose)

        # Full-data baseline
        baseline = compute_full_assessment(glucose, bolus, carbs_arr, n)
        baseline_grade = baseline['grade']
        baseline_flags = baseline['flags']
        baseline_recs = generate_recommendations(baseline)

        grades = {'100': baseline_grade}
        flag_agreements = {}
        rec_deviations = {}
        min_reliable = 100

        for drop_frac in DEGRADATION_LEVELS:
            degraded = glucose.copy()
            valid_mask = ~np.isnan(degraded)
            valid_indices = np.where(valid_mask)[0]
            n_drop = int(len(valid_indices) * drop_frac)
            if n_drop > 0:
                drop_idx = rng.choice(valid_indices, size=n_drop,
                                      replace=False)
                degraded[drop_idx] = np.nan

            pct_label = int((1 - drop_frac) * 100)
            deg_assess = compute_full_assessment(
                degraded, bolus, carbs_arr, n)
            grades[str(pct_label)] = deg_assess['grade']

            # Flag agreement: fraction of flags that match baseline
            deg_flags = deg_assess['flags']
            n_flags = len(baseline_flags)
            agree = sum(1 for k in baseline_flags
                        if baseline_flags[k] == deg_flags.get(k,
                                                              not baseline_flags[k]))
            flag_agreements[str(pct_label)] = (
                round(agree / max(n_flags, 1), 2))

            # Recommendation deviation: difference in scores
            deg_recs = generate_recommendations(deg_assess)
            baseline_params = {r['parameter'] for r in baseline_recs}
            deg_params = {r['parameter'] for r in deg_recs}
            symmetric_diff = len(baseline_params ^ deg_params)
            rec_deviations[str(pct_label)] = symmetric_diff

            # Check reliability: grade changed or flag agreement < 67%
            if (deg_assess['grade'] != baseline_grade
                    or flag_agreements[str(pct_label)] < 0.67):
                min_reliable = min(min_reliable, pct_label + int(
                    drop_frac * 100))

        rec = {
            'pid': pid,
            'grade_at_100pct': grades.get('100', baseline_grade),
            'grade_at_90pct': grades.get('90', 'N/A'),
            'grade_at_80pct': grades.get('80', 'N/A'),
            'grade_at_70pct': grades.get('70', 'N/A'),
            'grade_at_50pct': grades.get('50', 'N/A'),
            'flag_agreement_90': flag_agreements.get('90', 0.0),
            'flag_agreement_80': flag_agreements.get('80', 0.0),
            'flag_agreement_70': flag_agreements.get('70', 0.0),
            'flag_agreement_50': flag_agreements.get('50', 0.0),
            'min_reliable_coverage': min_reliable,
        }
        results['per_patient'].append(rec)

        if args.detail:
            print(f"  {pid}: grades={grades}  "
                  f"flag_agree={flag_agreements}  "
                  f"min_reliable={min_reliable}%")

    results['n_patients'] = len(results['per_patient'])
    # Summary
    coverages = [r['min_reliable_coverage']
                 for r in results['per_patient']]
    grade_stable_50 = sum(
        1 for r in results['per_patient']
        if r['grade_at_100pct'] == r['grade_at_50pct'])
    results['summary'] = {
        'mean_min_reliable_coverage': _safe_round(
            np.mean(coverages), 1) if coverages else None,
        'patients_stable_at_50pct': grade_stable_50,
        'patients_total': len(results['per_patient']),
    }
    return results


# ===================================================================
# EXP-1462: Pump Mode Transition Detection
# ===================================================================

@register(1462, "Pump Mode Transition Detection")
def exp_1462(patients, args):
    """Detect transitions between pump modes from temp_rate patterns.

    Classifies each hour as high-activity, moderate, low-activity, or
    suspended based on temp_rate change frequency and values.
    """
    results = {'name': 'EXP-1462: Pump Mode Transition Detection',
               'per_patient': []}

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose']
        temp_rate = pdata['temp_rate']
        n = len(glucose)
        n_hours = n // STEPS_PER_HOUR

        mode_counts = defaultdict(int)
        tir_by_mode = defaultdict(list)
        prev_mode = None
        transitions = 0

        for h in range(n_hours):
            h_start = h * STEPS_PER_HOUR
            h_end = min(h_start + STEPS_PER_HOUR, n)
            seg_rate = temp_rate[h_start:h_end]
            seg_glucose = glucose[h_start:h_end]

            # Count temp_rate changes in this hour
            rate_changes = 0
            for i in range(1, len(seg_rate)):
                if abs(seg_rate[i] - seg_rate[i - 1]) > 0.01:
                    rate_changes += 1

            # Check for suspension (near-zero rate for most of hour)
            near_zero = np.sum(np.abs(seg_rate) < 0.01)
            pct_zero = near_zero / max(len(seg_rate), 1)

            # 30 min = 6 steps out of 12
            if pct_zero > 0.5 and np.nanmean(np.abs(seg_rate)) < 0.05:
                mode = 'suspended'
            elif rate_changes > 2:
                mode = 'high_activity'
            elif rate_changes >= 1:
                mode = 'moderate'
            else:
                mode = 'low_activity'

            mode_counts[mode] += 1
            seg_tir = compute_tir(seg_glucose)
            tir_by_mode[mode].append(seg_tir)

            if prev_mode is not None and mode != prev_mode:
                transitions += 1
            prev_mode = mode

        total_hours = max(sum(mode_counts.values()), 1)
        n_weeks = max(n_hours / (24 * 7), 1)

        # Compute mean TIR per mode
        tir_means = {}
        for mode_name in ['high_activity', 'moderate', 'low_activity',
                          'suspended']:
            vals = tir_by_mode.get(mode_name, [])
            tir_means[mode_name] = (
                _safe_round(np.mean(vals), 1) if vals else None)

        # Dominant mode
        dominant = max(mode_counts, key=mode_counts.get) if mode_counts else 'unknown'

        rec = {
            'pid': pid,
            'pct_high_activity': _safe_round(
                mode_counts.get('high_activity', 0) / total_hours * 100, 1),
            'pct_moderate': _safe_round(
                mode_counts.get('moderate', 0) / total_hours * 100, 1),
            'pct_low_activity': _safe_round(
                mode_counts.get('low_activity', 0) / total_hours * 100, 1),
            'pct_suspended': _safe_round(
                mode_counts.get('suspended', 0) / total_hours * 100, 1),
            'tir_by_mode': tir_means,
            'mode_transitions_per_week': _safe_round(
                transitions / n_weeks, 1),
            'dominant_mode': dominant,
        }
        results['per_patient'].append(rec)

        if args.detail:
            print(f"  {pid}: dominant={dominant}  "
                  f"hi={rec['pct_high_activity']}%  "
                  f"mod={rec['pct_moderate']}%  "
                  f"lo={rec['pct_low_activity']}%  "
                  f"susp={rec['pct_suspended']}%  "
                  f"trans/wk={rec['mode_transitions_per_week']}")

    results['n_patients'] = len(results['per_patient'])
    modes = [r['dominant_mode'] for r in results['per_patient']]
    results['summary'] = {
        'dominant_mode_distribution': dict(
            zip(*np.unique(modes, return_counts=True))),
        'mean_transitions_per_week': _safe_round(np.mean([
            r['mode_transitions_per_week']
            for r in results['per_patient']
            if r['mode_transitions_per_week'] is not None]), 1),
    }
    return results


# ===================================================================
# EXP-1463: Real-World Noise Robustness
# ===================================================================

@register(1463, "Real-World Noise Robustness")
def exp_1463(patients, args):
    """Test recommendation stability against synthetic CGM noise patterns.

    Adds Gaussian noise, spike artifacts, and compression low artifacts,
    then measures how recommendations deviate from clean data.
    """
    results = {'name': 'EXP-1463: Real-World Noise Robustness',
               'per_patient': []}

    rng = np.random.RandomState(RNG_SEED)

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose'].copy()
        bolus = pdata['bolus']
        carbs_arr = pdata['carbs']
        n = len(glucose)

        # Clean baseline
        clean = compute_full_assessment(glucose, bolus, carbs_arr, n)
        clean_grade = clean['grade']
        clean_score = clean['score']

        noise_results = {}

        # Gaussian noise at various sigma levels
        for sigma in GAUSSIAN_SIGMAS:
            noisy = glucose.copy()
            valid_mask = ~np.isnan(noisy)
            noise = rng.normal(0, sigma, size=n)
            noisy[valid_mask] += noise[valid_mask]
            noisy = np.clip(noisy, 20, 500)
            assess = compute_full_assessment(noisy, bolus, carbs_arr, n)
            noise_results[f'gauss{sigma}'] = {
                'grade': assess['grade'],
                'score_delta': _safe_round(assess['score'] - clean_score, 1),
            }

        # Spike artifacts: random +/-50 mg/dL on 1% of readings
        spiked = glucose.copy()
        valid_mask = ~np.isnan(spiked)
        valid_idx = np.where(valid_mask)[0]
        n_spikes = max(1, int(len(valid_idx) * 0.01))
        spike_idx = rng.choice(valid_idx, size=n_spikes, replace=False)
        spike_dirs = rng.choice([-50, 50], size=n_spikes)
        spiked[spike_idx] += spike_dirs
        spiked = np.clip(spiked, 20, 500)
        spike_assess = compute_full_assessment(
            spiked, bolus, carbs_arr, n)
        noise_results['spike'] = {
            'grade': spike_assess['grade'],
            'score_delta': _safe_round(
                spike_assess['score'] - clean_score, 1),
        }

        # Compression lows: random dips to 40-55 on 0.5% of readings
        compressed = glucose.copy()
        valid_idx = np.where(~np.isnan(compressed))[0]
        n_compress = max(1, int(len(valid_idx) * 0.005))
        comp_idx = rng.choice(valid_idx, size=n_compress, replace=False)
        compressed[comp_idx] = rng.uniform(40, 55, size=n_compress)
        comp_assess = compute_full_assessment(
            compressed, bolus, carbs_arr, n)
        noise_results['compression'] = {
            'grade': comp_assess['grade'],
            'score_delta': _safe_round(
                comp_assess['score'] - clean_score, 1),
        }

        # Most sensitive parameter: which noise type caused largest deviation
        deltas = {k: abs(v['score_delta'] or 0)
                  for k, v in noise_results.items()}
        most_sensitive = max(deltas, key=deltas.get) if deltas else 'none'

        # Noise tolerance: highest noise level where grade is preserved
        tolerance = 'high'
        for sigma in reversed(GAUSSIAN_SIGMAS):
            if noise_results[f'gauss{sigma}']['grade'] != clean_grade:
                tolerance = f'below_sigma_{sigma}'
                break

        rec = {
            'pid': pid,
            'clean_grade': clean_grade,
            'gauss5_grade': noise_results.get('gauss5', {}).get(
                'grade', 'N/A'),
            'gauss10_grade': noise_results.get('gauss10', {}).get(
                'grade', 'N/A'),
            'gauss15_grade': noise_results.get('gauss15', {}).get(
                'grade', 'N/A'),
            'spike_grade': noise_results.get('spike', {}).get(
                'grade', 'N/A'),
            'compression_grade': noise_results.get('compression', {}).get(
                'grade', 'N/A'),
            'most_sensitive_param': most_sensitive,
            'noise_tolerance': tolerance,
        }
        results['per_patient'].append(rec)

        if args.detail:
            print(f"  {pid}: clean={clean_grade}  "
                  f"g5={rec['gauss5_grade']}  "
                  f"g10={rec['gauss10_grade']}  "
                  f"g15={rec['gauss15_grade']}  "
                  f"spike={rec['spike_grade']}  "
                  f"comp={rec['compression_grade']}  "
                  f"sensitive={most_sensitive}  "
                  f"tol={tolerance}")

    results['n_patients'] = len(results['per_patient'])
    grade_preserved_g15 = sum(
        1 for r in results['per_patient']
        if r['clean_grade'] == r['gauss15_grade'])
    results['summary'] = {
        'grade_preserved_at_sigma15': grade_preserved_g15,
        'patients_total': len(results['per_patient']),
        'most_common_sensitivity': _mode_str([
            r['most_sensitive_param'] for r in results['per_patient']]),
    }
    return results


def _mode_str(values):
    """Return the most common string in a list."""
    if not values:
        return 'none'
    counts = defaultdict(int)
    for v in values:
        counts[v] += 1
    return max(counts, key=counts.get)


# ===================================================================
# EXP-1464: Seasonal and Monthly Pattern Analysis
# ===================================================================

@register(1464, "Seasonal and Monthly Pattern Analysis")
def exp_1464(patients, args):
    """Look for seasonal/monthly patterns in therapy metrics.

    Computes monthly TIR, CV, overnight drift, postmeal excursion, then
    tests for trend (linear regression) and seasonality (autocorrelation
    at lag 4 weeks).
    """
    results = {'name': 'EXP-1464: Seasonal and Monthly Pattern Analysis',
               'per_patient': []}

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs_arr = pdata['carbs']
        n = len(glucose)
        n_days = n // STEPS_PER_DAY

        # Split into ~30-day months
        month_steps = 30 * STEPS_PER_DAY
        n_months = max(n // month_steps, 1)

        monthly_tir = []
        monthly_cv = []
        monthly_drift = []
        monthly_exc = []

        for m in range(n_months):
            m_start = m * month_steps
            m_end = min(m_start + month_steps, n)
            seg_g = glucose[m_start:m_end]
            seg_b = bolus[m_start:m_end]
            seg_c = carbs_arr[m_start:m_end]
            seg_n = len(seg_g)

            if np.sum(~np.isnan(seg_g)) < STEPS_PER_DAY:
                monthly_tir.append(np.nan)
                monthly_cv.append(np.nan)
                monthly_drift.append(np.nan)
                monthly_exc.append(np.nan)
                continue

            monthly_tir.append(compute_tir(seg_g))
            monthly_cv.append(compute_cv(seg_g))

            seg_days = max(seg_n // STEPS_PER_DAY, 1)
            monthly_drift.append(
                compute_overnight_drift(seg_g, seg_b, seg_c, seg_days, seg_n))
            monthly_exc.append(
                compute_max_excursion(seg_g, seg_c, seg_n))

        monthly_tir_arr = np.array(monthly_tir, dtype=float)

        # Linear trend on monthly TIR
        slope, t_stat, direction = _linear_trend(monthly_tir)
        p_proxy = 2.0 / (1.0 + t_stat) if t_stat > 0 else 1.0

        # Seasonality: autocorrelation at lag 1 (approx 4 weeks)
        has_seasonality = False
        valid_tirs = monthly_tir_arr[~np.isnan(monthly_tir_arr)]
        if len(valid_tirs) >= 4:
            mean_t = np.mean(valid_tirs)
            demeaned = valid_tirs - mean_t
            var_t = np.sum(demeaned ** 2)
            if var_t > 1e-6:
                autocorr = float(
                    np.sum(demeaned[:-1] * demeaned[1:]) / var_t)
                has_seasonality = abs(autocorr) > 0.3
            else:
                autocorr = 0.0
        else:
            autocorr = 0.0

        # Outlier months (> 1 SD from patient mean)
        if len(valid_tirs) >= 2:
            tir_mean = np.mean(valid_tirs)
            tir_std = np.std(valid_tirs)
            if tir_std > 0:
                n_outliers = int(np.sum(
                    np.abs(valid_tirs - tir_mean) > tir_std))
            else:
                n_outliers = 0
            best_tir = _safe_round(float(np.nanmax(valid_tirs)), 1)
            worst_tir = _safe_round(float(np.nanmin(valid_tirs)), 1)
            tir_range = _safe_round(best_tir - worst_tir, 1)
        else:
            n_outliers = 0
            best_tir = _safe_round(valid_tirs[0], 1) if len(
                valid_tirs) > 0 else 0.0
            worst_tir = best_tir
            tir_range = 0.0

        rec = {
            'pid': pid,
            'monthly_tir_trend_slope': _safe_round(slope, 4),
            'monthly_tir_trend_p': _safe_round(p_proxy, 4),
            'has_seasonality': has_seasonality,
            'n_outlier_months': n_outliers,
            'best_month_tir': best_tir,
            'worst_month_tir': worst_tir,
            'tir_range': tir_range,
            'n_months': n_months,
        }
        results['per_patient'].append(rec)

        if args.detail:
            print(f"  {pid}: trend={slope:+.4f}(p~{p_proxy:.3f})  "
                  f"seasonal={has_seasonality}  "
                  f"outliers={n_outliers}/{n_months}  "
                  f"TIR range=[{worst_tir},{best_tir}]")

    results['n_patients'] = len(results['per_patient'])
    has_trend = sum(1 for r in results['per_patient']
                    if r['monthly_tir_trend_p'] < 0.1)
    has_season = sum(1 for r in results['per_patient']
                     if r['has_seasonality'])
    results['summary'] = {
        'patients_with_trend': has_trend,
        'patients_with_seasonality': has_season,
        'mean_tir_range': _safe_round(np.mean([
            r['tir_range'] for r in results['per_patient']
            if r['tir_range'] is not None]), 1),
    }
    return results


# ===================================================================
# EXP-1465: Multi-Day Aggregation Strategy Comparison
# ===================================================================

@register(1465, "Multi-Day Aggregation Strategy Comparison")
def exp_1465(patients, args):
    """Compare aggregation strategies for computing therapy metrics.

    Evaluates daily, weekly, biweekly, monthly, and rolling 7-day windows
    to find which produces the most stable recommendations.
    """
    results = {'name': 'EXP-1465: Multi-Day Aggregation Strategy Comparison',
               'per_patient': []}

    agg_configs = {
        'daily': STEPS_PER_DAY,
        'weekly': WEEKLY_STEPS,
        'biweekly': 14 * STEPS_PER_DAY,
        'monthly': 30 * STEPS_PER_DAY,
    }

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs_arr = pdata['carbs']
        n = len(glucose)

        rec_stds = {}

        for agg_name, window_size in agg_configs.items():
            scores = []
            n_windows = max(n // window_size, 1)
            for w in range(n_windows):
                w_start = w * window_size
                w_end = min(w_start + window_size, n)
                seg_g = glucose[w_start:w_end]
                seg_b = bolus[w_start:w_end]
                seg_c = carbs_arr[w_start:w_end]
                seg_n = len(seg_g)
                valid = np.sum(~np.isnan(seg_g))
                if valid < STEPS_PER_HOUR * 2:
                    continue
                assess = compute_full_assessment(
                    seg_g, seg_b, seg_c, seg_n)
                scores.append(assess['score'])
            if len(scores) >= 2:
                rec_stds[agg_name] = _safe_round(float(np.std(scores)), 2)
            else:
                rec_stds[agg_name] = None

        # Rolling 7-day
        rolling_scores = []
        roll_step = STEPS_PER_DAY  # advance by 1 day
        roll_window = WEEKLY_STEPS
        for start in range(0, max(n - roll_window, 1), roll_step):
            end = min(start + roll_window, n)
            seg_g = glucose[start:end]
            seg_b = bolus[start:end]
            seg_c = carbs_arr[start:end]
            seg_n = len(seg_g)
            valid = np.sum(~np.isnan(seg_g))
            if valid < STEPS_PER_HOUR * 6:
                continue
            assess = compute_full_assessment(seg_g, seg_b, seg_c, seg_n)
            rolling_scores.append(assess['score'])
        if len(rolling_scores) >= 2:
            rec_stds['rolling7'] = _safe_round(
                float(np.std(rolling_scores)), 2)
        else:
            rec_stds['rolling7'] = None

        # Find most/least stable
        valid_stds = {k: v for k, v in rec_stds.items() if v is not None}
        if valid_stds:
            most_stable = min(valid_stds, key=valid_stds.get)
            least_stable = max(valid_stds, key=valid_stds.get)
        else:
            most_stable = 'unknown'
            least_stable = 'unknown'

        rec = {
            'pid': pid,
            'daily_rec_std': rec_stds.get('daily'),
            'weekly_rec_std': rec_stds.get('weekly'),
            'biweekly_rec_std': rec_stds.get('biweekly'),
            'monthly_rec_std': rec_stds.get('monthly'),
            'rolling7_rec_std': rec_stds.get('rolling7'),
            'most_stable_agg': most_stable,
            'least_stable_agg': least_stable,
        }
        results['per_patient'].append(rec)

        if args.detail:
            std_str = '  '.join(
                f"{k}={v}" for k, v in rec_stds.items())
            print(f"  {pid}: {std_str}  "
                  f"best={most_stable}  worst={least_stable}")

    results['n_patients'] = len(results['per_patient'])
    best_counts = defaultdict(int)
    for r in results['per_patient']:
        best_counts[r['most_stable_agg']] += 1
    results['summary'] = {
        'most_stable_winner': max(best_counts, key=best_counts.get)
                              if best_counts else 'unknown',
        'most_stable_distribution': dict(best_counts),
    }
    return results


# ===================================================================
# EXP-1466: CGM Calibration Artifact Detection
# ===================================================================

@register(1466, "CGM Calibration Artifact Detection")
def exp_1466(patients, args):
    """Detect CGM calibration artifacts that could bias recommendations.

    Identifies level shifts, compression artifacts, and sensor warmup
    periods, then measures their impact on TIR.
    """
    results = {'name': 'EXP-1466: CGM Calibration Artifact Detection',
               'per_patient': []}

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose'].copy()
        bolus = pdata['bolus']
        carbs_arr = pdata['carbs']
        iob = pdata['iob']
        n = len(glucose)

        artifact_mask = np.zeros(n, dtype=bool)

        # --- Level shifts: >30 mg/dL jump not explained by insulin/carbs ---
        n_level_shifts = 0
        for i in range(1, n):
            if np.isnan(glucose[i]) or np.isnan(glucose[i - 1]):
                continue
            jump = abs(glucose[i] - glucose[i - 1])
            if jump <= 30:
                continue
            # Check for insulin/carb explanation in surrounding window
            lookback = min(i, 6)
            lookahead = min(n - i, 6)
            window_bolus = np.nansum(bolus[i - lookback:i + lookahead])
            window_carbs = np.nansum(carbs_arr[i - lookback:i + lookahead])
            window_iob = np.nanmean(iob[i - lookback:i + lookahead])
            if window_bolus > 0.5 or window_carbs > 5 or window_iob > 1.0:
                continue
            n_level_shifts += 1
            artifact_mask[i] = True

        # --- Compression: same value for >30 min (6+ consecutive steps) ---
        n_compression_events = 0
        i = 0
        while i < n - 1:
            if np.isnan(glucose[i]):
                i += 1
                continue
            run_len = 1
            while (i + run_len < n
                   and not np.isnan(glucose[i + run_len])
                   and abs(glucose[i + run_len] - glucose[i]) < 0.5):
                run_len += 1
            if run_len >= 6:
                n_compression_events += 1
                artifact_mask[i:i + run_len] = True
            i += run_len

        # --- Sensor warmup: first 2 hours after gaps > 2 hours ---
        n_warmup_periods = 0
        gap_threshold = 2 * STEPS_PER_HOUR  # 2 hours = 24 steps
        warmup_steps = 2 * STEPS_PER_HOUR   # 2 hours
        i = 0
        while i < n:
            if np.isnan(glucose[i]):
                gap_start = i
                while i < n and np.isnan(glucose[i]):
                    i += 1
                gap_len = i - gap_start
                if gap_len >= gap_threshold and i < n:
                    n_warmup_periods += 1
                    warmup_end = min(i + warmup_steps, n)
                    artifact_mask[i:warmup_end] = True
            else:
                i += 1

        # Impact on TIR
        pct_artifact = _safe_round(
            float(np.sum(artifact_mask)) / max(n, 1) * 100, 2)

        tir_with = compute_tir(glucose)
        clean_glucose = glucose.copy()
        clean_glucose[artifact_mask] = np.nan
        tir_without = compute_tir(clean_glucose)

        rec = {
            'pid': pid,
            'n_level_shifts': n_level_shifts,
            'n_compression_events': n_compression_events,
            'n_warmup_periods': n_warmup_periods,
            'pct_artifact_affected': pct_artifact,
            'tir_without_artifacts': _safe_round(tir_without, 1),
            'tir_with_artifacts': _safe_round(tir_with, 1),
            'tir_bias': _safe_round(tir_with - tir_without, 2),
        }
        results['per_patient'].append(rec)

        if args.detail:
            print(f"  {pid}: shifts={n_level_shifts}  "
                  f"compress={n_compression_events}  "
                  f"warmup={n_warmup_periods}  "
                  f"artifact%={pct_artifact}  "
                  f"TIR bias={rec['tir_bias']:+.2f}")

    results['n_patients'] = len(results['per_patient'])
    results['summary'] = {
        'mean_artifact_pct': _safe_round(np.mean([
            r['pct_artifact_affected']
            for r in results['per_patient']
            if r['pct_artifact_affected'] is not None]), 2),
        'mean_tir_bias': _safe_round(np.mean([
            r['tir_bias'] for r in results['per_patient']
            if r['tir_bias'] is not None]), 2),
        'total_level_shifts': sum(
            r['n_level_shifts'] for r in results['per_patient']),
        'total_compression_events': sum(
            r['n_compression_events'] for r in results['per_patient']),
    }
    return results


# ===================================================================
# EXP-1467: Recommendation Conflict Resolution
# ===================================================================

@register(1467, "Recommendation Conflict Resolution")
def exp_1467(patients, args):
    """Detect and resolve conflicting therapy recommendations.

    When multiple parameters need adjustment, identifies contradictory
    recommendations (e.g., basal up + ISF down) and applies resolution
    rules.
    """
    results = {'name': 'EXP-1467: Recommendation Conflict Resolution',
               'per_patient': []}

    # Conflict definitions:
    # basal increase + ISF decrease = contradictory (both increase insulin
    #   effect but via different axes)
    # CR decrease + ISF decrease = amplifying (both push insulin up)
    CONFLICT_RULES = [
        {
            'name': 'basal_up_isf_down',
            'params': ('basal', 'isf'),
            'dirs': ('increase', 'decrease'),
            'resolution': 'prioritize_basal',
            'type': 'contradictory',
        },
        {
            'name': 'basal_down_isf_up',
            'params': ('basal', 'isf'),
            'dirs': ('decrease', 'increase'),
            'resolution': 'prioritize_basal',
            'type': 'contradictory',
        },
        {
            'name': 'cr_down_isf_down',
            'params': ('cr', 'isf'),
            'dirs': ('decrease', 'decrease'),
            'resolution': 'cap_total_increase',
            'type': 'amplifying',
        },
    ]

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs_arr = pdata['carbs']
        n = len(glucose)

        assessment = compute_full_assessment(glucose, bolus, carbs_arr, n)
        recs = generate_recommendations(assessment)
        n_recs = len(recs)

        # Build lookup of recommendations by parameter
        rec_by_param = {}
        for r in recs:
            rec_by_param[r['parameter']] = r

        # Detect conflicts
        conflicts = []
        for rule in CONFLICT_RULES:
            p1, p2 = rule['params']
            d1, d2 = rule['dirs']
            if (p1 in rec_by_param and p2 in rec_by_param
                    and rec_by_param[p1]['direction'] == d1
                    and rec_by_param[p2]['direction'] == d2):
                conflicts.append({
                    'rule': rule['name'],
                    'type': rule['type'],
                    'resolution': rule['resolution'],
                })

        n_conflicts = len(conflicts)
        conflict_types = list(set(c['type'] for c in conflicts))

        # Apply conflict resolution
        resolved_actions = []
        dropped_params = set()

        for conflict in conflicts:
            rule_name = conflict['rule']
            resolution = conflict['resolution']

            if resolution == 'prioritize_basal':
                # Keep basal, drop the conflicting ISF recommendation
                dropped_params.add('isf')
                resolved_actions.append(
                    f"{rule_name}: keep basal, drop isf")
            elif resolution == 'cap_total_increase':
                # Keep both but reduce magnitudes by 50%
                resolved_actions.append(
                    f"{rule_name}: reduce both magnitudes by 50%")

        # Final resolved recommendation set
        strategy = 'no_conflicts'
        if n_conflicts > 0:
            if any(c['type'] == 'contradictory' for c in conflicts):
                strategy = 'prioritize_independent'
            else:
                strategy = 'cap_amplifying'

        rec = {
            'pid': pid,
            'n_recommendations': n_recs,
            'n_conflicts': n_conflicts,
            'conflict_types': conflict_types if conflict_types else ['none'],
            'resolution_strategy': strategy,
            'resolved_actions': (resolved_actions
                                 if resolved_actions else ['none']),
        }
        results['per_patient'].append(rec)

        if args.detail:
            print(f"  {pid}: recs={n_recs}  conflicts={n_conflicts}  "
                  f"types={conflict_types}  strategy={strategy}")

    results['n_patients'] = len(results['per_patient'])
    total_conflicts = sum(r['n_conflicts'] for r in results['per_patient'])
    patients_with_conflicts = sum(
        1 for r in results['per_patient'] if r['n_conflicts'] > 0)
    results['summary'] = {
        'total_conflicts': total_conflicts,
        'patients_with_conflicts': patients_with_conflicts,
        'conflict_rate': _safe_round(
            patients_with_conflicts / max(len(results['per_patient']), 1)
            * 100, 1),
    }
    return results


# ===================================================================
# EXP-1468: Dose Rounding and Practical Constraints
# ===================================================================

@register(1468, "Dose Rounding and Practical Constraints")
def exp_1468(patients, args):
    """Account for real-world pump constraints on recommendations.

    Applies dose rounding (0.05U steps), minimum basal (0.05 U/h),
    max basal (5 U/h), and max bolus (25 U) limits, then measures
    how much rounding affects expected impact.
    """
    results = {'name': 'EXP-1468: Dose Rounding and Practical Constraints',
               'per_patient': []}

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs_arr = pdata['carbs']
        temp_rate = pdata['temp_rate']
        n = len(glucose)

        assessment = compute_full_assessment(glucose, bolus, carbs_arr, n)
        recs = generate_recommendations(assessment)

        # Estimate current basal from median temp_rate
        valid_rates = temp_rate[~np.isnan(temp_rate)]
        valid_rates = valid_rates[valid_rates > 0]
        current_basal = float(np.median(valid_rates)) if len(
            valid_rates) > 0 else 1.0

        # Estimate current CR and ISF from DIA and population defaults
        current_cr = 10.0   # g/U (population default)
        current_isf = 50.0  # mg/dL/U (population default)

        # Compute ideal and rounded changes
        ideal_basal_change = 0.0
        rounded_basal_change = 0.0
        ideal_cr_change = 0.0
        practical_cr_change = 0.0
        ideal_isf_change = 0.0
        practical_isf_change = 0.0

        for r in recs:
            param = r['parameter']
            direction = r['direction']
            mag_pct = r['magnitude_pct']
            sign = 1.0 if direction == 'increase' else -1.0

            if param == 'basal':
                ideal = current_basal * (mag_pct / 100.0) * sign
                ideal_basal_change = ideal
                new_basal = current_basal + ideal
                new_basal = np.clip(new_basal, PUMP_MIN_BASAL, PUMP_MAX_BASAL)
                new_basal = round_to_step(new_basal)
                rounded_basal_change = new_basal - current_basal

            elif param == 'cr':
                ideal = current_cr * (mag_pct / 100.0) * sign
                ideal_cr_change = ideal
                new_cr = current_cr + ideal
                new_cr = max(1.0, new_cr)
                new_cr = round(new_cr)  # CR rounded to nearest integer
                practical_cr_change = new_cr - current_cr

            elif param == 'isf':
                ideal = current_isf * (mag_pct / 100.0) * sign
                ideal_isf_change = ideal
                new_isf = current_isf + ideal
                new_isf = max(1.0, new_isf)
                new_isf = round(new_isf)  # ISF rounded to nearest integer
                practical_isf_change = new_isf - current_isf

        # Rounding loss for basal
        if abs(ideal_basal_change) > 1e-6:
            rounding_loss = abs(
                1.0 - abs(rounded_basal_change) / abs(ideal_basal_change)
            ) * 100
        else:
            rounding_loss = 0.0

        # Total rounding impact across all parameters
        total_ideal = (abs(ideal_basal_change)
                       + abs(ideal_cr_change)
                       + abs(ideal_isf_change))
        total_practical = (abs(rounded_basal_change)
                           + abs(practical_cr_change)
                           + abs(practical_isf_change))
        if total_ideal > 1e-6:
            total_rounding_impact = abs(
                1.0 - total_practical / total_ideal) * 100
        else:
            total_rounding_impact = 0.0

        rec = {
            'pid': pid,
            'ideal_basal_change': _safe_round(ideal_basal_change, 4),
            'rounded_basal_change': _safe_round(rounded_basal_change, 4),
            'rounding_loss_pct': _safe_round(rounding_loss, 1),
            'ideal_cr_change': _safe_round(ideal_cr_change, 1),
            'practical_cr_change': _safe_round(practical_cr_change, 1),
            'ideal_isf_change': _safe_round(ideal_isf_change, 1),
            'practical_isf_change': _safe_round(practical_isf_change, 1),
            'total_rounding_impact': _safe_round(total_rounding_impact, 1),
        }
        results['per_patient'].append(rec)

        if args.detail:
            print(f"  {pid}: basal ideal={ideal_basal_change:+.4f} "
                  f"rounded={rounded_basal_change:+.4f} "
                  f"loss={rounding_loss:.1f}%  "
                  f"cr ideal={ideal_cr_change:+.1f} "
                  f"practical={practical_cr_change:+.1f}  "
                  f"isf ideal={ideal_isf_change:+.1f} "
                  f"practical={practical_isf_change:+.1f}  "
                  f"total_impact={total_rounding_impact:.1f}%")

    results['n_patients'] = len(results['per_patient'])
    losses = [r['rounding_loss_pct'] for r in results['per_patient']
              if r['rounding_loss_pct'] is not None]
    impacts = [r['total_rounding_impact'] for r in results['per_patient']
               if r['total_rounding_impact'] is not None]
    results['summary'] = {
        'mean_basal_rounding_loss': _safe_round(
            np.mean(losses), 1) if losses else 0.0,
        'mean_total_rounding_impact': _safe_round(
            np.mean(impacts), 1) if impacts else 0.0,
        'max_total_rounding_impact': _safe_round(
            max(impacts), 1) if impacts else 0.0,
    }
    return results


# ===================================================================
# EXP-1469: Patient Communication Summary Generation
# ===================================================================

@register(1469, "Patient Communication Summary Generation")
def exp_1469(patients, args):
    """Generate human-readable therapy summaries for each patient.

    Produces structured summaries with status, priority, recommended
    action, expected benefit, confidence, and urgency classification.
    """
    results = {'name': 'EXP-1469: Patient Communication Summary Generation',
               'per_patient': []}

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs_arr = pdata['carbs']
        n = len(glucose)

        assessment = compute_full_assessment(glucose, bolus, carbs_arr, n)
        tir = assessment['tir']
        cv = assessment['cv']
        grade = assessment['grade']
        score = assessment['score']
        flags = assessment['flags']

        recs = generate_recommendations(assessment)
        overnight_t = compute_overnight_tir(glucose, n)
        postmeal_t = compute_postmeal_tir(glucose, carbs_arr, n)

        # Status summary
        if grade == 'A':
            status = 'well_controlled'
        elif grade == 'B':
            status = 'adequately_controlled'
        elif grade == 'C':
            status = 'needs_improvement'
        else:
            status = 'requires_attention'

        # Top priority
        if not recs:
            top_priority = 'maintenance'
            recommended_action = 'Continue current therapy'
            expected_benefit = 0.0
        else:
            # Prioritize: basal > cr > isf
            priority_order = {'basal': 0, 'cr': 1, 'isf': 2}
            sorted_recs = sorted(
                recs, key=lambda r: priority_order.get(r['parameter'], 9))
            top_rec = sorted_recs[0]
            top_priority = top_rec['parameter']
            direction = top_rec['direction']
            mag = top_rec['magnitude_pct']
            recommended_action = (
                f"{direction.capitalize()} {top_priority} by {mag}%")

            # Estimate expected TIR benefit (conservative: 30% of gap-to-target)
            tir_gap = max(0, 80 - tir)  # target 80% TIR
            expected_benefit = _safe_round(tir_gap * 0.3, 1)

        # Confidence based on data coverage and grade stability
        valid_pct = float(
            np.sum(~np.isnan(glucose)) / max(n, 1) * 100)
        if valid_pct >= 90 and n >= 14 * STEPS_PER_DAY:
            confidence = 'high'
        elif valid_pct >= 70 and n >= 7 * STEPS_PER_DAY:
            confidence = 'moderate'
        else:
            confidence = 'low'

        # Urgency
        urgency = classify_urgency(grade, tir, cv)

        # Plain language summary
        plain_parts = []
        plain_parts.append(
            f"Current TIR is {tir:.0f}% (grade {grade}).")
        if recs:
            plain_parts.append(
                f"The top recommendation is to {recommended_action.lower()}.")
            if expected_benefit and expected_benefit > 0:
                plain_parts.append(
                    f"This may improve TIR by ~{expected_benefit:.0f}%.")
        else:
            plain_parts.append("No therapy changes recommended at this time.")
        plain_summary = ' '.join(plain_parts)

        rec = {
            'pid': pid,
            'status_summary': status,
            'top_priority': top_priority,
            'recommended_action': recommended_action,
            'expected_benefit_tir': expected_benefit,
            'confidence': confidence,
            'urgency': urgency,
            'plain_language_summary': plain_summary,
        }
        results['per_patient'].append(rec)

        if args.detail:
            print(f"  {pid}: [{urgency}] {status} | "
                  f"priority={top_priority} | "
                  f"action={recommended_action} | "
                  f"benefit=+{expected_benefit}% TIR | "
                  f"confidence={confidence}")
            if args.detail:
                print(f"    Summary: {plain_summary}")

    results['n_patients'] = len(results['per_patient'])
    urgency_dist = defaultdict(int)
    for r in results['per_patient']:
        urgency_dist[r['urgency']] += 1
    results['summary'] = {
        'urgency_distribution': dict(urgency_dist),
        'patients_needing_action': sum(
            1 for r in results['per_patient']
            if r['top_priority'] != 'maintenance'),
        'mean_expected_benefit': _safe_round(np.mean([
            r['expected_benefit_tir'] for r in results['per_patient']
            if r['expected_benefit_tir'] is not None]), 1),
    }
    return results


# ===================================================================
# EXP-1470: End-to-End Integration Test Suite
# ===================================================================

@register(1470, "End-to-End Integration Test Suite")
def exp_1470(patients, args):
    """Run comprehensive integration tests validating all pipeline
    components work together consistently.

    Tests: preconditions, classification, detection, recommendation,
    scoring, and triage -- then checks for internal inconsistencies.
    """
    results = {'name': 'EXP-1470: End-to-End Integration Test Suite',
               'per_patient': []}

    for pid, pdata in sorted(patients.items()):
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs_arr = pdata['carbs']
        n = len(glucose)
        t0 = time.time()

        inconsistencies = []

        # --- Stage 1: Preconditions ---
        valid_pct = float(
            np.sum(~np.isnan(glucose)) / max(n, 1) * 100)
        n_days = n // STEPS_PER_DAY
        preconditions_pass = valid_pct >= 50 and n_days >= 3

        # --- Stage 2: Full assessment (classification + detection) ---
        assessment = compute_full_assessment(glucose, bolus, carbs_arr, n)
        tir = assessment['tir']
        cv = assessment['cv']
        score = assessment['score']
        grade = assessment['grade']
        flags = assessment['flags']

        # --- Stage 3: Classification consistency ---
        # Grade must match score thresholds
        expected_grade = compute_grade(score)
        classification_consistent = (grade == expected_grade)
        if not classification_consistent:
            inconsistencies.append(
                f"grade={grade} but score={score} -> {expected_grade}")

        # --- Stage 4: Detection consistency ---
        # Flags must match thresholds
        drift = assessment['drift']
        exc = assessment['excursion']

        detection_consistent = True
        if flags['basal_flag'] != (abs(drift) >= DRIFT_THRESHOLD):
            detection_consistent = False
            inconsistencies.append(
                f"basal_flag={flags['basal_flag']} but drift={drift}")
        if flags['cr_flag'] != (exc >= EXCURSION_THRESHOLD):
            detection_consistent = False
            inconsistencies.append(
                f"cr_flag={flags['cr_flag']} but excursion={exc}")
        if flags['cv_flag'] != (cv >= CV_THRESHOLD):
            detection_consistent = False
            inconsistencies.append(
                f"cv_flag={flags['cv_flag']} but cv={cv}")

        # --- Stage 5: Recommendation consistency ---
        recs = generate_recommendations(assessment)
        recommendation_consistent = True
        for r in recs:
            param = r['parameter']
            if param == 'basal' and not flags.get('basal_flag', False):
                recommendation_consistent = False
                inconsistencies.append(
                    f"basal rec without basal_flag")
            if param == 'cr' and not flags.get('cr_flag', False):
                recommendation_consistent = False
                inconsistencies.append(
                    f"cr rec without cr_flag")
            if param == 'isf' and not flags.get('cv_flag', False):
                recommendation_consistent = False
                inconsistencies.append(
                    f"isf rec without cv_flag")

        # --- Stage 6: Scoring consistency ---
        # Re-derive score independently and compare
        rescore = compute_therapy_score(
            tir, drift, exc, assessment['isf_ratio'], cv)
        scoring_consistent = abs(rescore - score) < 0.1
        if not scoring_consistent:
            inconsistencies.append(
                f"score={score} but recomputed={rescore}")

        # --- Stage 7: Triage consistency ---
        urgency = classify_urgency(grade, tir, cv)
        triage_ok = True
        if grade == 'D' and urgency not in ('immediate', 'soon'):
            triage_ok = False
            inconsistencies.append(
                f"grade=D but urgency={urgency}")
        if grade == 'A' and urgency == 'immediate':
            triage_ok = False
            inconsistencies.append(
                f"grade=A but urgency=immediate")

        elapsed_ms = round((time.time() - t0) * 1000, 1)

        rec = {
            'pid': pid,
            'preconditions_pass': preconditions_pass,
            'classification_consistent': classification_consistent,
            'detection_consistent': detection_consistent,
            'recommendation_consistent': recommendation_consistent,
            'scoring_consistent': scoring_consistent,
            'n_inconsistencies': len(inconsistencies),
            'inconsistency_details': (inconsistencies
                                      if inconsistencies else []),
            'pipeline_time_ms': elapsed_ms,
        }
        results['per_patient'].append(rec)

        if args.detail:
            status = 'PASS' if len(inconsistencies) == 0 else 'WARN'
            print(f"  {pid}: [{status}] {elapsed_ms}ms  "
                  f"pre={preconditions_pass}  "
                  f"class={classification_consistent}  "
                  f"detect={detection_consistent}  "
                  f"rec={recommendation_consistent}  "
                  f"score={scoring_consistent}  "
                  f"issues={len(inconsistencies)}")
            for detail in inconsistencies:
                print(f"    -> {detail}")

    results['n_patients'] = len(results['per_patient'])
    all_pass = sum(
        1 for r in results['per_patient']
        if r['n_inconsistencies'] == 0)
    total_issues = sum(
        r['n_inconsistencies'] for r in results['per_patient'])
    mean_time = np.mean([
        r['pipeline_time_ms'] for r in results['per_patient']])
    results['summary'] = {
        'patients_all_pass': all_pass,
        'patients_with_issues': (len(results['per_patient']) - all_pass),
        'total_inconsistencies': total_issues,
        'mean_pipeline_time_ms': _safe_round(mean_time, 1),
        'max_pipeline_time_ms': _safe_round(max(
            r['pipeline_time_ms'] for r in results['per_patient']), 1),
    }
    return results


# ===================================================================
# Main entry point
# ===================================================================

def main():
    parser = argparse.ArgumentParser(
        description='EXP-1461 to EXP-1470: Practical Implementation '
                    '& Edge Cases')
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
