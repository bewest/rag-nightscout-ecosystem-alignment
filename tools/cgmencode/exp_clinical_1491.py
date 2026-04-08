#!/usr/bin/env python3
"""EXP-1491 to EXP-1500: TBR Integration & Safety Enhancement.

This batch addresses the finding from EXP-1490 that pipeline-ADA alignment
is only 64% because TBR (time-below-range) is not tracked.  It introduces
comprehensive ADA time-in-ranges analysis, a TBR-integrated v10 grading
formula, hypo risk stratification, AID-induced hypoglycemia detection,
nocturnal hypo patterns, TBR-aware ISF adjustment, safety-first protocol,
hypoglycemia recovery analysis, re-validation against ADA guidelines, and
a final v10 pipeline validation summary.
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

# ADA time-in-range thresholds (mg/dL)
TBR_L1_LO = 54
TBR_L1_HI = 69
TBR_L2_HI = 53      # severe hypo: <54
TAR_L1_LO = 181
TAR_L1_HI = 250
TAR_L2_LO = 251      # severe hyper: >250

# ADA targets (%)
ADA_TIR_TARGET = 70.0
ADA_TIR_HIGH_RISK = 50.0
ADA_TBR_L1_TARGET = 4.0       # <4% time 54-69
ADA_TBR_L2_TARGET = 1.0       # <1% time <54
ADA_TAR_L1_TARGET = 25.0      # <25% time 181-250
ADA_TAR_L2_TARGET = 5.0       # <5% time >250
ADA_CV_TARGET = 36.0

# Grade boundaries  (score -> letter)
GRADE_D_CEIL = 50
GRADE_C_CEIL = 65
GRADE_B_CEIL = 80

# Score composition weights (v9 – legacy)
SCORE_WEIGHTS = {'tir': 60, 'basal': 15, 'cr': 15, 'isf': 5, 'cv': 5}
DRIFT_THRESHOLD = 5.0       # mg/dL/h
EXCURSION_THRESHOLD = 70    # mg/dL  (90-th %ile post-meal rise)
CV_THRESHOLD = 36           # %
MIN_BOLUS_ISF = 2.0         # U -- minimum correction bolus for ISF calc
MIN_ISF_EVENTS = 5

CONSERVATIVE_BASAL_PCT = 10     # +/-10 %
CR_ADJUST_STANDARD = 30         # -30 %
CR_ADJUST_GRADE_D = 50          # -50 %
ISF_ADJUST_PCT = 10             # +/-10 %
DIA_DEFAULT = 6.0               # hours

N_BOOTSTRAP = 1000
RNG_SEED = 42

# Hypo episode detection
HYPO_THRESHOLD = 70             # mg/dL
SEVERE_HYPO_THRESHOLD = 54     # mg/dL
HYPO_MIN_DURATION_STEPS = 3    # 15 min = 3 consecutive 5-min readings

# Insulin stacking
IOB_STACK_FACTOR = 2.0
DIA_STEPS = int(DIA_DEFAULT * STEPS_PER_HOUR)

# ISF estimation defaults
DEFAULT_ISF = 50.0      # mg/dL per unit
DEFAULT_CR = 10.0        # g carbs per unit

# Basal reference (assumed)
DEFAULT_BASAL_RATE = 1.0  # U/h

# Clinical urgency thresholds
URGENCY_IMMEDIATE_TIR = 40
URGENCY_SOON_TIR = 55

# Meal time-of-day categories (hour ranges)
MEAL_BREAKFAST = (5, 10)
MEAL_LUNCH = (11, 14)
MEAL_DINNER = (17, 21)

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
    """Simplified composite score v9 (0-100)."""
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
# Helper functions -- TBR / TAR / safety (NEW for v10)
# ---------------------------------------------------------------------------

def compute_tbr(glucose, threshold=70):
    """Compute time below range (%) at given threshold."""
    if isinstance(glucose, np.ndarray):
        valid = glucose[~np.isnan(glucose)]
    else:
        valid = glucose.dropna().values
    if len(valid) == 0:
        return 0.0
    return float(np.mean(valid < threshold) * 100)


def compute_tar(glucose, threshold=180):
    """Compute time above range (%) at given threshold."""
    if isinstance(glucose, np.ndarray):
        valid = glucose[~np.isnan(glucose)]
    else:
        valid = glucose.dropna().values
    if len(valid) == 0:
        return 0.0
    return float(np.mean(valid > threshold) * 100)


def compute_safety_score(tbr_l1, tbr_l2, overcorrection_rate):
    """Safety score (0-100): penalises TBR and overcorrection."""
    penalty = tbr_l1 * 10.0 + tbr_l2 * 50.0 + overcorrection_rate
    return max(0.0, min(100.0, 100.0 - penalty))


def compute_v10_score(tir, cv, overnight_tir, safety_score):
    """v10 composite score with TBR-integrated safety (0-100)."""
    score = (tir * 0.5
             + max(0, 100 - cv * 2) * 0.2
             + overnight_tir * 0.1
             + safety_score * 0.2)
    return min(100.0, max(0.0, float(score)))


def compute_v10_grade(score):
    """Map v10 score to letter grade (same boundaries as v9)."""
    return compute_grade(score)


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
# Helper functions -- overnight metrics
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


def _extract_overnight_glucose(glucose, n):
    """Extract concatenated overnight (00:00-06:00) glucose array."""
    segments = []
    n_days = n // STEPS_PER_DAY
    for d in range(min(n_days, 180)):
        s = d * STEPS_PER_DAY
        e = s + 6 * STEPS_PER_HOUR
        if e > n:
            break
        segments.append(glucose[s:e])
    if not segments:
        return np.array([])
    return np.concatenate(segments)


# ---------------------------------------------------------------------------
# Helper functions -- drift & excursion (v9 compatibility)
# ---------------------------------------------------------------------------

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
# Helper functions -- ISF & therapy scoring (v9)
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
    """Compute therapy score 0-100 (v9)."""
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
    """Compute full therapy assessment for a patient data slice (v9)."""
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
# Helper functions -- overcorrection rate
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
    return float(hypos / events * 100)


# ---------------------------------------------------------------------------
# Helper functions -- hypo episode detection
# ---------------------------------------------------------------------------

def detect_hypo_episodes(glucose, threshold=HYPO_THRESHOLD,
                         min_consecutive=HYPO_MIN_DURATION_STEPS):
    """Detect hypoglycaemia episodes (consecutive readings below threshold).

    Returns list of dicts: {start, end, duration_steps, nadir, nadir_idx}.
    """
    n = len(glucose)
    episodes = []
    i = 0
    while i < n:
        if np.isnan(glucose[i]) or glucose[i] >= threshold:
            i += 1
            continue
        # Start of a potential episode
        start = i
        nadir = glucose[i]
        nadir_idx = i
        count = 1
        j = i + 1
        while j < n:
            if np.isnan(glucose[j]):
                j += 1
                continue
            if glucose[j] < threshold:
                count += 1
                if glucose[j] < nadir:
                    nadir = glucose[j]
                    nadir_idx = j
                j += 1
            else:
                break
        end = j
        if count >= min_consecutive:
            episodes.append({
                'start': start,
                'end': end,
                'duration_steps': end - start,
                'nadir': float(nadir),
                'nadir_idx': nadir_idx,
            })
        i = j
    return episodes


# ---------------------------------------------------------------------------
# Helper functions -- recommendation generation (v9 compat)
# ---------------------------------------------------------------------------

def generate_recommendations(assessment):
    """Generate therapy parameter recommendations from an assessment dict."""
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


def classify_urgency(grade, tir, cv):
    """Classify clinical urgency from grade, TIR, and CV."""
    if grade == 'D' or tir < URGENCY_IMMEDIATE_TIR:
        return 'immediate'
    if grade == 'C' or tir < URGENCY_SOON_TIR:
        return 'soon'
    if grade == 'B':
        return 'routine'
    return 'monitoring-only'


# ---------------------------------------------------------------------------
# Helper functions -- statistical utilities
# ---------------------------------------------------------------------------

def _safe_round(val, digits=2):
    """Round a value safely, handling None / NaN."""
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    return round(float(val), digits)


def _linear_trend(values):
    """Fit simple OLS slope over an evenly-spaced series."""
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
    se = (np.sqrt(np.sum(residuals ** 2) / max(len(y) - 2, 1))
          / np.sqrt(ss_xx))
    t_stat = abs(slope / se) if se > 1e-12 else 0.0
    if abs(slope) < 1e-6 or t_stat < 2.0:
        direction = 'stable'
    elif slope > 0:
        direction = 'increasing'
    else:
        direction = 'decreasing'
    return slope, t_stat, direction


# ===================================================================
# EXP-1491: Comprehensive Time-in-Ranges Analysis
# ===================================================================

@register(1491, "Comprehensive Time-in-Ranges Analysis")
def exp_1491(patients, args):
    """Compute all ADA-recommended time-in-range metrics for each patient,
    both overall and overnight (00:00-06:00), and compare against targets."""
    results = {'name': 'EXP-1491: Comprehensive Time-in-Ranges Analysis',
               'per_patient': []}
    np.random.seed(RNG_SEED)

    pids = sorted(patients.keys())
    ada_pass = 0

    for pid in pids:
        pdata = patients[pid]
        glucose = pdata['glucose']
        n = len(glucose)

        # Overall metrics
        tir = compute_tir(glucose)
        tbr_l1 = compute_tbr(glucose, TIR_LO) - compute_tbr(glucose, TBR_L1_LO)
        tbr_l1 = max(0.0, tbr_l1)
        tbr_l2 = compute_tbr(glucose, TBR_L1_LO)
        tar_l1 = compute_tar(glucose, TIR_HI) - compute_tar(glucose, TAR_L2_LO)
        tar_l1 = max(0.0, tar_l1)
        tar_l2 = compute_tar(glucose, TAR_L1_HI)
        cv = compute_cv(glucose)

        # Overnight metrics (00:00-06:00)
        overnight_g = _extract_overnight_glucose(glucose, n)
        if len(overnight_g) > 0:
            overnight_tir = compute_tir(overnight_g)
            overnight_tbr_l1 = max(
                0.0,
                compute_tbr(overnight_g, TIR_LO)
                - compute_tbr(overnight_g, TBR_L1_LO))
            overnight_tbr_l2 = compute_tbr(overnight_g, TBR_L1_LO)
        else:
            overnight_tir = 0.0
            overnight_tbr_l1 = 0.0
            overnight_tbr_l2 = 0.0

        # ADA compliance
        meets_tir = tir >= ADA_TIR_TARGET
        meets_tbr = (tbr_l1 + tbr_l2) < ADA_TBR_L1_TARGET and tbr_l2 < ADA_TBR_L2_TARGET
        meets_tar = tar_l2 < ADA_TAR_L2_TARGET
        meets_cv = cv < ADA_CV_TARGET

        n_met = sum([meets_tir, meets_tbr, meets_tar, meets_cv])
        if n_met == 4:
            ada_status = 'meets_all_targets'
            ada_pass += 1
        elif n_met >= 3:
            ada_status = 'partially_meets'
        elif n_met >= 2:
            ada_status = 'below_targets'
        else:
            ada_status = 'significantly_below'

        rec = {
            'pid': pid,
            'tir': _safe_round(tir, 1),
            'tbr_l1': _safe_round(tbr_l1, 2),
            'tbr_l2': _safe_round(tbr_l2, 2),
            'tar_l1': _safe_round(tar_l1, 1),
            'tar_l2': _safe_round(tar_l2, 1),
            'overnight_tir': _safe_round(overnight_tir, 1),
            'overnight_tbr_l1': _safe_round(overnight_tbr_l1, 2),
            'overnight_tbr_l2': _safe_round(overnight_tbr_l2, 2),
            'meets_tir': meets_tir,
            'meets_tbr': meets_tbr,
            'meets_tar': meets_tar,
            'meets_cv': meets_cv,
            'ada_status': ada_status,
        }
        results['per_patient'].append(rec)
        if args.detail:
            print(f"  {pid}: TIR={tir:.1f}% TBR_L1={tbr_l1:.2f}% "
                  f"TBR_L2={tbr_l2:.2f}% TAR_L1={tar_l1:.1f}% "
                  f"TAR_L2={tar_l2:.1f}% CV={cv:.1f}% "
                  f"overnight_TIR={overnight_tir:.1f}% "
                  f"ADA={ada_status}")

    results['n_patients'] = len(pids)
    results['ada_summary'] = {
        'meets_all': ada_pass,
        'pct_meets_all': _safe_round(ada_pass / max(len(pids), 1) * 100, 1),
    }
    return results


# ===================================================================
# EXP-1492: TBR-Integrated Grading (Pipeline v10)
# ===================================================================

@register(1492, "TBR-Integrated Grading (Pipeline v10)")
def exp_1492(patients, args):
    """Re-grade all patients using v10 formula that incorporates TBR via
    safety_score and compare against v9 grades."""
    results = {'name': 'EXP-1492: TBR-Integrated Grading (Pipeline v10)',
               'per_patient': []}
    np.random.seed(RNG_SEED)

    pids = sorted(patients.keys())
    n_changes = 0
    n_downgrades = 0
    n_upgrades = 0
    v9_scores = []
    v10_scores = []

    grade_order = {'A': 4, 'B': 3, 'C': 2, 'D': 1}

    for pid in pids:
        pdata = patients[pid]
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs_arr = pdata['carbs']
        n = len(glucose)

        tir = compute_tir(glucose)
        cv = compute_cv(glucose)
        overnight_tir = compute_overnight_tir(glucose, n)

        # v9 score
        v9_score = compute_score(tir, cv, overnight_tir)
        v9_grade = compute_grade(v9_score)
        v9_scores.append(v9_score)

        # Safety components for v10
        tbr_l1 = max(0.0,
                     compute_tbr(glucose, TIR_LO)
                     - compute_tbr(glucose, TBR_L1_LO))
        tbr_l2 = compute_tbr(glucose, TBR_L1_LO)
        overcorrection = compute_overcorrection_rate(glucose, bolus,
                                                     carbs_arr, n)
        safety = compute_safety_score(tbr_l1, tbr_l2, overcorrection)

        # v10 score
        v10_score_val = compute_v10_score(tir, cv, overnight_tir, safety)
        v10_grade = compute_v10_grade(v10_score_val)
        v10_scores.append(v10_score_val)

        # Direction of grade change
        grade_changed = v9_grade != v10_grade
        if grade_changed:
            n_changes += 1
            if grade_order[v10_grade] < grade_order[v9_grade]:
                direction = 'downgrade'
                n_downgrades += 1
            else:
                direction = 'upgrade'
                n_upgrades += 1
        else:
            direction = 'unchanged'

        rec = {
            'pid': pid,
            'v9_score': _safe_round(v9_score, 1),
            'v9_grade': v9_grade,
            'v10_score': _safe_round(v10_score_val, 1),
            'v10_grade': v10_grade,
            'safety_score': _safe_round(safety, 1),
            'grade_changed': grade_changed,
            'direction': direction,
        }
        results['per_patient'].append(rec)
        if args.detail:
            print(f"  {pid}: v9={v9_grade}({v9_score:.1f}) "
                  f"v10={v10_grade}({v10_score_val:.1f}) "
                  f"safety={safety:.1f} {direction}")

    results['n_patients'] = len(pids)
    results['population'] = {
        'n_grade_changes': n_changes,
        'n_downgrades': n_downgrades,
        'n_upgrades': n_upgrades,
        'mean_v9': _safe_round(float(np.mean(v9_scores))
                               if v9_scores else 0.0, 1),
        'mean_v10': _safe_round(float(np.mean(v10_scores))
                                if v10_scores else 0.0, 1),
    }
    return results


# ===================================================================
# EXP-1493: Hypo Risk Stratification
# ===================================================================

@register(1493, "Hypo Risk Stratification")
def exp_1493(patients, args):
    """Stratify patients into hypo risk tiers using multiple indicators:
    TBR, episode frequency, duration, severity, nocturnal rate, stacking."""
    results = {'name': 'EXP-1493: Hypo Risk Stratification',
               'per_patient': []}
    np.random.seed(RNG_SEED)

    pids = sorted(patients.keys())
    tier_counts = defaultdict(int)

    for pid in pids:
        pdata = patients[pid]
        glucose = pdata['glucose']
        iob = pdata['iob']
        bolus = pdata['bolus']
        n = len(glucose)
        n_days = max(n // STEPS_PER_DAY, 1)

        # TBR total (<70)
        tbr_total = compute_tbr(glucose, HYPO_THRESHOLD)

        # Hypo episodes (>= 15 min below 70)
        episodes = detect_hypo_episodes(glucose, HYPO_THRESHOLD,
                                        HYPO_MIN_DURATION_STEPS)
        n_episodes = len(episodes)
        hypo_freq_per_week = (n_episodes / max(n_days, 1)) * 7.0

        # Longest hypo
        if episodes:
            longest_steps = max(ep['duration_steps'] for ep in episodes)
            longest_hypo_min = longest_steps * 5
        else:
            longest_hypo_min = 0

        # Severe hypos (<54)
        severe_episodes = detect_hypo_episodes(glucose, SEVERE_HYPO_THRESHOLD,
                                               HYPO_MIN_DURATION_STEPS)
        n_severe = len(severe_episodes)

        # Nocturnal hypo rate (fraction of episodes during 00:00-06:00)
        nocturnal_count = 0
        for ep in episodes:
            ep_hour = hour_of_step(ep['start'])
            if ep_hour < 6:
                nocturnal_count += 1
        nocturnal_hypo_pct = (nocturnal_count / max(n_episodes, 1) * 100
                              if n_episodes > 0 else 0.0)

        # Insulin stacking rate: fraction of hypo episodes preceded by
        # IOB > IOB_STACK_FACTOR * median_iob within 2h
        valid_iob = iob[~np.isnan(iob)]
        median_iob = float(np.median(valid_iob)) if len(valid_iob) > 0 else 0.0
        stack_threshold = IOB_STACK_FACTOR * max(median_iob, 0.5)
        stacking_count = 0
        for ep in episodes:
            lookback = 2 * STEPS_PER_HOUR
            start = max(0, ep['start'] - lookback)
            prior_iob = iob[start:ep['start']]
            valid_prior = prior_iob[~np.isnan(prior_iob)]
            if len(valid_prior) > 0 and np.max(valid_prior) > stack_threshold:
                stacking_count += 1
        stacking_rate = (stacking_count / max(n_episodes, 1) * 100
                         if n_episodes > 0 else 0.0)

        # Risk tier classification
        risk_factors = []
        if tbr_total > 4:
            risk_factors.append('high_tbr')
        if n_severe > 0:
            risk_factors.append('severe_hypos')
        if nocturnal_hypo_pct > 30:
            risk_factors.append('nocturnal_hypos')
        if stacking_rate > 30:
            risk_factors.append('insulin_stacking')
        if hypo_freq_per_week > 7:
            risk_factors.append('frequent_hypos')

        if tbr_total > 8 and n_severe > 0:
            risk_tier = 'critical'
        elif tbr_total > 4 or (n_severe > 0 and hypo_freq_per_week > 3):
            risk_tier = 'high'
        elif (tbr_total > 2 or
              (n_severe > 0 and hypo_freq_per_week <= 3)):
            risk_tier = 'moderate'
        else:
            risk_tier = 'low'

        tier_counts[risk_tier] += 1

        rec = {
            'pid': pid,
            'tbr_total': _safe_round(tbr_total, 2),
            'hypo_episodes': n_episodes,
            'hypo_frequency_per_week': _safe_round(hypo_freq_per_week, 2),
            'longest_hypo_min': longest_hypo_min,
            'n_severe_hypos': n_severe,
            'nocturnal_hypo_pct': _safe_round(nocturnal_hypo_pct, 1),
            'risk_tier': risk_tier,
            'risk_factors': risk_factors if risk_factors else ['none'],
        }
        results['per_patient'].append(rec)
        if args.detail:
            print(f"  {pid}: TBR={tbr_total:.2f}% episodes={n_episodes} "
                  f"severe={n_severe} nocturnal={nocturnal_hypo_pct:.1f}% "
                  f"stacking={stacking_rate:.1f}% tier={risk_tier}")

    results['n_patients'] = len(pids)
    results['tier_distribution'] = dict(tier_counts)
    return results


# ===================================================================
# EXP-1494: AID-Induced Hypoglycemia Detection
# ===================================================================

@register(1494, "AID-Induced Hypoglycemia Detection")
def exp_1494(patients, args):
    """Distinguish between AID-induced hypos (preceded by high temp_rate)
    and manual-induced hypos (preceded by manual bolus)."""
    results = {'name': 'EXP-1494: AID-Induced Hypoglycemia Detection',
               'per_patient': []}
    np.random.seed(RNG_SEED)

    pids = sorted(patients.keys())

    for pid in pids:
        pdata = patients[pid]
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        temp_rate = pdata['temp_rate']
        n = len(glucose)

        episodes = detect_hypo_episodes(glucose, HYPO_THRESHOLD,
                                        HYPO_MIN_DURATION_STEPS)
        n_hypos = len(episodes)
        n_aid = 0
        n_manual = 0
        n_unclear = 0
        aid_temp_rates = []
        manual_boluses = []

        lookback = 2 * STEPS_PER_HOUR  # 2 h prior
        high_temp_threshold = DEFAULT_BASAL_RATE * 1.5  # >150% of basal

        for ep in episodes:
            start = max(0, ep['start'] - lookback)
            prior_temp = temp_rate[start:ep['start']]
            prior_bolus = bolus[start:ep['start']]

            valid_temp = prior_temp[~np.isnan(prior_temp)]
            valid_bolus = prior_bolus[~np.isnan(prior_bolus)]

            has_high_temp = (len(valid_temp) > 0
                             and np.max(valid_temp) > high_temp_threshold)
            has_manual_bolus = (len(valid_bolus) > 0
                                and np.max(valid_bolus) > 1.0)

            if has_high_temp and not has_manual_bolus:
                n_aid += 1
                aid_temp_rates.append(float(np.max(valid_temp)))
            elif has_manual_bolus and not has_high_temp:
                n_manual += 1
                manual_boluses.append(float(np.max(valid_bolus)))
            elif has_high_temp and has_manual_bolus:
                # Both present – classify as manual (user action takes
                # precedence in attribution)
                n_manual += 1
                manual_boluses.append(float(np.max(valid_bolus)))
            else:
                n_unclear += 1

        pct_aid = n_aid / max(n_hypos, 1) * 100 if n_hypos > 0 else 0.0
        mean_temp_aid = (float(np.mean(aid_temp_rates))
                         if aid_temp_rates else 0.0)
        mean_bolus_manual = (float(np.mean(manual_boluses))
                             if manual_boluses else 0.0)

        rec = {
            'pid': pid,
            'n_hypos': n_hypos,
            'n_aid_induced': n_aid,
            'n_manual_induced': n_manual,
            'n_unclear': n_unclear,
            'pct_aid_induced': _safe_round(pct_aid, 1),
            'mean_prior_temp_rate_aid': _safe_round(mean_temp_aid, 3),
            'mean_prior_bolus_manual': _safe_round(mean_bolus_manual, 2),
        }
        results['per_patient'].append(rec)
        if args.detail:
            print(f"  {pid}: hypos={n_hypos} aid={n_aid} "
                  f"manual={n_manual} unclear={n_unclear} "
                  f"pct_aid={pct_aid:.1f}%")

    results['n_patients'] = len(pids)
    results['population'] = {
        'total_hypos': sum(r['n_hypos'] for r in results['per_patient']),
        'total_aid': sum(r['n_aid_induced'] for r in results['per_patient']),
        'total_manual': sum(r['n_manual_induced']
                            for r in results['per_patient']),
        'total_unclear': sum(r['n_unclear'] for r in results['per_patient']),
    }
    return results


# ===================================================================
# EXP-1495: Nocturnal Hypoglycemia Patterns
# ===================================================================

@register(1495, "Nocturnal Hypoglycemia Patterns")
def exp_1495(patients, args):
    """Deep dive into overnight (00:00-06:00) hypoglycemia patterns: onset
    hour, bedtime IOB, dinner-to-hypo timing, stacking correlation."""
    results = {'name': 'EXP-1495: Nocturnal Hypoglycemia Patterns',
               'per_patient': []}
    np.random.seed(RNG_SEED)

    pids = sorted(patients.keys())

    for pid in pids:
        pdata = patients[pid]
        glucose = pdata['glucose']
        iob = pdata['iob']
        bolus = pdata['bolus']
        carbs_arr = pdata['carbs']
        n = len(glucose)
        n_days = max(n // STEPS_PER_DAY, 1)

        # Overnight glucose
        overnight_g = _extract_overnight_glucose(glucose, n)
        nocturnal_tbr = compute_tbr(overnight_g, HYPO_THRESHOLD) \
            if len(overnight_g) > 0 else 0.0

        # Nocturnal hypo episodes
        episodes = detect_hypo_episodes(glucose, HYPO_THRESHOLD,
                                        HYPO_MIN_DURATION_STEPS)
        nocturnal_episodes = []
        for ep in episodes:
            ep_hour = hour_of_step(ep['start'])
            if ep_hour < 6:
                nocturnal_episodes.append(ep)

        n_nocturnal = len(nocturnal_episodes)

        # Typical onset hour (mode of start hours)
        onset_hours = [hour_of_step(ep['start']) for ep in nocturnal_episodes]
        if onset_hours:
            counts = defaultdict(int)
            for h in onset_hours:
                counts[h] += 1
            typical_onset = max(counts, key=counts.get)
        else:
            typical_onset = None

        # Bedtime IOB (IOB at 22:00-23:00 each night)
        bedtime_iobs = []
        for d in range(min(n_days, 180)):
            bedtime_start = d * STEPS_PER_DAY + 22 * STEPS_PER_HOUR
            bedtime_end = d * STEPS_PER_DAY + 23 * STEPS_PER_HOUR
            if bedtime_end > n:
                break
            seg_iob = iob[bedtime_start:bedtime_end]
            valid_iob = seg_iob[~np.isnan(seg_iob)]
            if len(valid_iob) > 0:
                bedtime_iobs.append(float(np.mean(valid_iob)))
        bedtime_iob_mean = (float(np.mean(bedtime_iobs))
                            if bedtime_iobs else 0.0)

        # Preceded by stacking (IOB > 2U at bedtime before nocturnal hypo)
        stacking_preceding = 0
        for ep in nocturnal_episodes:
            ep_day = day_of_step(ep['start'])
            bedtime_start = ep_day * STEPS_PER_DAY + 22 * STEPS_PER_HOUR
            bedtime_end = ep_day * STEPS_PER_DAY + 23 * STEPS_PER_HOUR
            if bedtime_start < 0 or bedtime_end > n:
                continue
            seg_iob = iob[bedtime_start:bedtime_end]
            valid_iob = seg_iob[~np.isnan(seg_iob)]
            if len(valid_iob) > 0 and np.max(valid_iob) > 2.0:
                stacking_preceding += 1
        preceded_by_stacking_pct = (stacking_preceding / max(n_nocturnal, 1)
                                    * 100 if n_nocturnal > 0 else 0.0)

        # Dinner-to-hypo hours: time from last dinner bolus/carb to hypo start
        dinner_to_hypo_list = []
        for ep in nocturnal_episodes:
            ep_day = day_of_step(ep['start'])
            dinner_start = ep_day * STEPS_PER_DAY + MEAL_DINNER[0] * STEPS_PER_HOUR
            dinner_end = ep_day * STEPS_PER_DAY + MEAL_DINNER[1] * STEPS_PER_HOUR
            if dinner_start < 0 or dinner_end > n:
                continue
            # Find last carb or bolus event during dinner
            last_dinner_step = None
            for s in range(min(dinner_end, n) - 1, max(dinner_start, 0) - 1, -1):
                if s < n and (carbs_arr[s] > 0 or bolus[s] > 0):
                    last_dinner_step = s
                    break
            if last_dinner_step is not None:
                gap_hours = (ep['start'] - last_dinner_step) / STEPS_PER_HOUR
                if gap_hours > 0:
                    dinner_to_hypo_list.append(gap_hours)

        dinner_to_hypo_hours = (float(np.median(dinner_to_hypo_list))
                                if dinner_to_hypo_list else None)

        rec = {
            'pid': pid,
            'nocturnal_tbr': _safe_round(nocturnal_tbr, 2),
            'nocturnal_hypo_episodes': n_nocturnal,
            'typical_onset_hour': typical_onset,
            'bedtime_iob_mean': _safe_round(bedtime_iob_mean, 2),
            'preceded_by_stacking_pct': _safe_round(preceded_by_stacking_pct, 1),
            'dinner_to_hypo_hours': _safe_round(dinner_to_hypo_hours, 1),
        }
        results['per_patient'].append(rec)
        if args.detail:
            onset_str = f"{typical_onset}:00" if typical_onset is not None \
                else "N/A"
            d2h_str = (f"{dinner_to_hypo_hours:.1f}h"
                       if dinner_to_hypo_hours is not None else "N/A")
            print(f"  {pid}: noct_TBR={nocturnal_tbr:.2f}% "
                  f"episodes={n_nocturnal} onset={onset_str} "
                  f"bedtime_IOB={bedtime_iob_mean:.2f}U "
                  f"stacking={preceded_by_stacking_pct:.1f}% "
                  f"dinner→hypo={d2h_str}")

    results['n_patients'] = len(pids)
    results['population'] = {
        'total_nocturnal_episodes': sum(
            r['nocturnal_hypo_episodes'] for r in results['per_patient']),
        'mean_nocturnal_tbr': _safe_round(
            float(np.mean([r['nocturnal_tbr'] for r in results['per_patient']
                           if r['nocturnal_tbr'] is not None])), 2),
    }
    return results


# ===================================================================
# EXP-1496: TBR-Aware ISF Adjustment
# ===================================================================

@register(1496, "TBR-Aware ISF Adjustment")
def exp_1496(patients, args):
    """Check whether ISF adjustments would worsen TBR, and flag UNSAFE
    recommendations when TBR is already elevated."""
    results = {'name': 'EXP-1496: TBR-Aware ISF Adjustment',
               'per_patient': []}
    np.random.seed(RNG_SEED)

    pids = sorted(patients.keys())
    n_overrides = 0

    for pid in pids:
        pdata = patients[pid]
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs_arr = pdata['carbs']
        n = len(glucose)

        current_tbr = compute_tbr(glucose, HYPO_THRESHOLD)
        cv = compute_cv(glucose)

        # v9 assessment for standard ISF recommendation
        assessment = compute_full_assessment(glucose, bolus, carbs_arr, n)
        recs = generate_recommendations(assessment)

        # Find ISF recommendation if any
        isf_rec = None
        for r in recs:
            if r['parameter'] == 'isf':
                isf_rec = r
                break

        if isf_rec is None:
            # No ISF recommendation – derive one from CV
            if cv > CV_THRESHOLD:
                isf_recommendation = 'increase'
            elif cv < CV_THRESHOLD * 0.6:
                isf_recommendation = 'decrease'
            else:
                isf_recommendation = 'maintain'
        else:
            isf_recommendation = isf_rec['direction']

        # Safety check
        safety_override = False
        adjusted_recommendation = isf_recommendation
        reason = 'no_override_needed'

        if current_tbr > 4.0 and isf_recommendation == 'decrease':
            # Decreasing ISF (more aggressive) when TBR already high = UNSAFE
            safety_override = True
            adjusted_recommendation = 'increase'
            reason = f'TBR {current_tbr:.1f}% > 4%: ISF decrease UNSAFE'
            n_overrides += 1
        elif current_tbr > 4.0 and isf_recommendation == 'maintain':
            # TBR high, should increase ISF even if not recommended
            safety_override = True
            adjusted_recommendation = 'increase'
            reason = f'TBR {current_tbr:.1f}% > 4%: override to increase ISF'
            n_overrides += 1
        elif current_tbr < 2.0 and isf_recommendation == 'increase':
            # Low TBR, safe to proceed with increase
            reason = 'TBR low, safe to increase ISF'
        elif current_tbr < 2.0 and isf_recommendation == 'decrease':
            # Low TBR, decrease is acceptable
            reason = 'TBR low, decrease acceptable'

        tbr_safe = not (current_tbr > 4.0
                        and isf_recommendation in ('decrease', 'maintain'))

        rec = {
            'pid': pid,
            'current_tbr': _safe_round(current_tbr, 2),
            'isf_recommendation': isf_recommendation,
            'tbr_safe': tbr_safe,
            'adjusted_recommendation': adjusted_recommendation,
            'safety_override': safety_override,
            'reason': reason,
        }
        results['per_patient'].append(rec)
        if args.detail:
            override_str = " ** OVERRIDE **" if safety_override else ""
            print(f"  {pid}: TBR={current_tbr:.2f}% "
                  f"ISF_rec={isf_recommendation} "
                  f"adj={adjusted_recommendation} "
                  f"safe={tbr_safe}{override_str}")

    results['n_patients'] = len(pids)
    results['n_safety_overrides'] = n_overrides
    return results


# ===================================================================
# EXP-1497: Safety-First Protocol
# ===================================================================

@register(1497, "Safety-First Protocol")
def exp_1497(patients, args):
    """Design a safety-first recommendation protocol that prioritises hypo
    prevention before any other therapy changes."""
    results = {'name': 'EXP-1497: Safety-First Protocol',
               'per_patient': []}
    np.random.seed(RNG_SEED)

    pids = sorted(patients.keys())

    for pid in pids:
        pdata = patients[pid]
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs_arr = pdata['carbs']
        iob = pdata['iob']
        temp_rate = pdata['temp_rate']
        n = len(glucose)
        n_days = max(n // STEPS_PER_DAY, 1)

        tir = compute_tir(glucose)
        cv = compute_cv(glucose)
        overnight_tir = compute_overnight_tir(glucose, n)
        tbr_total = compute_tbr(glucose, HYPO_THRESHOLD)

        # Standard protocol: basal → CR → ISF
        assessment = compute_full_assessment(glucose, bolus, carbs_arr, n)
        standard_recs = generate_recommendations(assessment)
        standard_first = (standard_recs[0]['parameter']
                          if standard_recs else 'no_change')

        # Detect nocturnal hypos
        episodes = detect_hypo_episodes(glucose, HYPO_THRESHOLD,
                                        HYPO_MIN_DURATION_STEPS)
        nocturnal_episodes = [ep for ep in episodes
                              if hour_of_step(ep['start']) < 6]
        has_nocturnal = len(nocturnal_episodes) > 0

        # Detect stacking-related hypos
        valid_iob = iob[~np.isnan(iob)]
        median_iob = float(np.median(valid_iob)) if len(valid_iob) > 0 else 0.0
        stack_threshold = IOB_STACK_FACTOR * max(median_iob, 0.5)
        stacking_hypos = 0
        for ep in episodes:
            lookback = 2 * STEPS_PER_HOUR
            start = max(0, ep['start'] - lookback)
            prior_iob = iob[start:ep['start']]
            valid_prior = prior_iob[~np.isnan(prior_iob)]
            if len(valid_prior) > 0 and np.max(valid_prior) > stack_threshold:
                stacking_hypos += 1
        has_stacking = stacking_hypos > 0

        # Safety-first protocol
        safety_steps = []
        safety_overrides = []

        # Step 1: TBR check
        if tbr_total > 4.0:
            safety_steps.append('reduce_aggressiveness')
            safety_overrides.append(
                f'TBR {tbr_total:.1f}% > 4%: fix hypos first')

        # Step 2: Nocturnal hypos
        if has_nocturnal:
            safety_steps.append('reduce_overnight_basal_10pct')
            safety_overrides.append(
                f'{len(nocturnal_episodes)} nocturnal hypos: '
                f'reduce overnight basal by 10%')

        # Step 3: Stacking
        if has_stacking:
            safety_steps.append('add_stacking_alert')
            safety_overrides.append(
                f'{stacking_hypos} stacking-related hypos: add stacking alert')

        # Step 4: Standard protocol (only after safety addressed)
        if not safety_steps:
            safety_steps = ['standard_protocol']

        safety_first_action = safety_steps[0]

        # Estimate TIR impact (rough heuristic)
        # Standard: direct assessment-based change
        standard_tir_impact = 0.0
        if standard_recs:
            standard_tir_impact = 2.0  # Estimated +2% TIR per recommendation

        # Safety-first: fix hypos first may slightly reduce TIR short-term
        # but prevents dangerous lows
        safety_tir_impact = -1.0 if tbr_total > 4.0 else standard_tir_impact

        rec = {
            'pid': pid,
            'standard_first_action': standard_first,
            'safety_first_action': safety_first_action,
            'safety_overrides': (safety_overrides if safety_overrides
                                 else ['none']),
            'n_safety_steps': len(safety_overrides),
            'standard_tir_impact': _safe_round(standard_tir_impact, 1),
            'safety_tir_impact': _safe_round(safety_tir_impact, 1),
        }
        results['per_patient'].append(rec)
        if args.detail:
            n_ov = len(safety_overrides)
            print(f"  {pid}: standard_1st={standard_first} "
                  f"safety_1st={safety_first_action} "
                  f"overrides={n_ov} TBR={tbr_total:.2f}%")

    results['n_patients'] = len(pids)
    results['population'] = {
        'n_with_safety_overrides': sum(
            1 for r in results['per_patient']
            if r['safety_overrides'] != ['none']),
        'n_nocturnal_fixes': sum(
            1 for r in results['per_patient']
            if r['safety_first_action'] == 'reduce_overnight_basal_10pct'),
        'n_stacking_alerts': sum(
            1 for r in results['per_patient']
            if 'add_stacking_alert' in
            [s for s in (r.get('safety_overrides', [])
                         if isinstance(r.get('safety_overrides'), list)
                         else [])
             if 'stacking' in str(s)]),
    }
    return results


# ===================================================================
# EXP-1498: Hypoglycemia Recovery Analysis
# ===================================================================

@register(1498, "Hypoglycemia Recovery Analysis")
def exp_1498(patients, args):
    """Analyse how quickly patients recover from hypoglycaemia and what
    factors influence recovery time."""
    results = {'name': 'EXP-1498: Hypoglycemia Recovery Analysis',
               'per_patient': []}
    np.random.seed(RNG_SEED)

    pids = sorted(patients.keys())

    for pid in pids:
        pdata = patients[pid]
        glucose = pdata['glucose']
        carbs_arr = pdata['carbs']
        temp_rate = pdata['temp_rate']
        n = len(glucose)

        episodes = detect_hypo_episodes(glucose, HYPO_THRESHOLD,
                                        HYPO_MIN_DURATION_STEPS)
        n_episodes = len(episodes)

        recovery_times = []
        carb_treated = 0
        aid_suspended = 0
        nadirs = []
        fastest = None
        slowest = None

        for ep in episodes:
            nadir = ep['nadir']
            nadirs.append(nadir)

            # Recovery: time from nadir to first reading >= 70
            recovery_steps = 0
            recovered = False
            for j in range(ep['nadir_idx'] + 1, min(ep['nadir_idx']
                           + 6 * STEPS_PER_HOUR, n)):
                recovery_steps += 1
                if not np.isnan(glucose[j]) and glucose[j] >= HYPO_THRESHOLD:
                    recovered = True
                    break
            if recovered:
                recovery_min = recovery_steps * 5
                recovery_times.append(recovery_min)
                if fastest is None or recovery_min < fastest:
                    fastest = recovery_min
                if slowest is None or recovery_min > slowest:
                    slowest = recovery_min

            # Check if carbs were consumed during/after hypo (within 30 min)
            carb_window_start = ep['start']
            carb_window_end = min(ep['end'] + 6, n)  # +30 min after end
            seg_carbs = carbs_arr[carb_window_start:carb_window_end]
            if np.nansum(seg_carbs) > 0:
                carb_treated += 1

            # Check if temp_rate was reduced (AID suspend/reduce)
            # Compare temp_rate during hypo vs 1h before
            pre_start = max(0, ep['start'] - STEPS_PER_HOUR)
            pre_temp = temp_rate[pre_start:ep['start']]
            during_temp = temp_rate[ep['start']:ep['end']]
            valid_pre = pre_temp[~np.isnan(pre_temp)]
            valid_during = during_temp[~np.isnan(during_temp)]
            if (len(valid_pre) > 0 and len(valid_during) > 0
                    and np.mean(valid_during) < np.mean(valid_pre) * 0.5):
                aid_suspended += 1

        pct_carb_treated = (carb_treated / max(n_episodes, 1) * 100
                            if n_episodes > 0 else 0.0)
        pct_aid_suspended = (aid_suspended / max(n_episodes, 1) * 100
                             if n_episodes > 0 else 0.0)

        if recovery_times:
            median_recovery = float(np.median(recovery_times))
            std_recovery = float(np.std(recovery_times))
        else:
            median_recovery = 0.0
            std_recovery = 0.0

        # Recovery vs nadir depth correlation
        if len(recovery_times) >= 3 and len(nadirs) >= 3:
            # Align arrays: only use episodes that recovered
            aligned_nadirs = []
            aligned_recovery = []
            rt_idx = 0
            for ep_idx, ep in enumerate(episodes):
                nadir = ep['nadir']
                # Check if this episode had a recovery
                recovery_steps = 0
                recovered = False
                for j in range(ep['nadir_idx'] + 1, min(ep['nadir_idx']
                               + 6 * STEPS_PER_HOUR, n)):
                    recovery_steps += 1
                    if (not np.isnan(glucose[j])
                            and glucose[j] >= HYPO_THRESHOLD):
                        recovered = True
                        break
                if recovered:
                    aligned_nadirs.append(nadir)
                    aligned_recovery.append(recovery_steps * 5)

            if len(aligned_nadirs) >= 3:
                nadir_arr = np.array(aligned_nadirs)
                rec_arr = np.array(aligned_recovery)
                nadir_mean = np.mean(nadir_arr)
                rec_mean = np.mean(rec_arr)
                cov = np.sum((nadir_arr - nadir_mean)
                             * (rec_arr - rec_mean))
                var_n = np.sum((nadir_arr - nadir_mean) ** 2)
                var_r = np.sum((rec_arr - rec_mean) ** 2)
                denom = math.sqrt(var_n * var_r) if var_n * var_r > 0 else 1.0
                corr = float(cov / denom)
            else:
                corr = 0.0
        else:
            corr = 0.0

        rec = {
            'pid': pid,
            'n_hypo_episodes': n_episodes,
            'median_recovery_min': _safe_round(median_recovery, 1),
            'std_recovery_min': _safe_round(std_recovery, 1),
            'pct_carb_treated': _safe_round(pct_carb_treated, 1),
            'pct_aid_suspended': _safe_round(pct_aid_suspended, 1),
            'recovery_vs_nadir_correlation': _safe_round(corr, 3),
            'fastest_recovery': fastest,
            'slowest_recovery': slowest,
        }
        results['per_patient'].append(rec)
        if args.detail:
            print(f"  {pid}: episodes={n_episodes} "
                  f"median_recovery={median_recovery:.1f}min "
                  f"carb_treated={pct_carb_treated:.1f}% "
                  f"aid_suspend={pct_aid_suspended:.1f}% "
                  f"nadir_corr={corr:.3f}")

    results['n_patients'] = len(pids)
    results['population'] = {
        'mean_median_recovery': _safe_round(
            float(np.mean([r['median_recovery_min']
                           for r in results['per_patient']
                           if r['median_recovery_min'] is not None])), 1),
        'mean_carb_treated_pct': _safe_round(
            float(np.mean([r['pct_carb_treated']
                           for r in results['per_patient']
                           if r['pct_carb_treated'] is not None])), 1),
    }
    return results


# ===================================================================
# EXP-1499: Re-Validation Against ADA with TBR
# ===================================================================

@register(1499, "Re-Validation Against ADA with TBR")
def exp_1499(patients, args):
    """Re-run ADA guideline validation using v10 scoring that includes TBR.
    Measure alignment improvement vs v9."""
    results = {'name': 'EXP-1499: Re-Validation Against ADA with TBR',
               'per_patient': []}
    np.random.seed(RNG_SEED)

    pids = sorted(patients.keys())
    v9_alignments = []
    v10_alignments = []

    grade_to_ada = {'A': 'meets_all_targets', 'B': 'partially_meets',
                    'C': 'below_targets', 'D': 'significantly_below'}

    for pid in pids:
        pdata = patients[pid]
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs_arr = pdata['carbs']
        n = len(glucose)

        # ADA metrics
        tir = compute_tir(glucose)
        tbr_70 = compute_tbr(glucose, HYPO_THRESHOLD)
        tbr_54 = compute_tbr(glucose, SEVERE_HYPO_THRESHOLD)
        tar_250 = compute_tar(glucose, TAR_L1_HI)
        cv = compute_cv(glucose)

        # ADA classification
        meets_tir = tir >= ADA_TIR_TARGET
        meets_tbr = tbr_70 < ADA_TBR_L1_TARGET and tbr_54 < ADA_TBR_L2_TARGET
        meets_cv = cv < ADA_CV_TARGET
        n_met = sum([meets_tir, meets_tbr, meets_cv])
        if n_met == 3:
            ada_status = 'meets_all_targets'
        elif n_met == 2:
            ada_status = 'partially_meets'
        elif n_met == 1:
            ada_status = 'below_targets'
        else:
            ada_status = 'significantly_below'

        # v9 grade
        overnight_tir = compute_overnight_tir(glucose, n)
        v9_score = compute_score(tir, cv, overnight_tir)
        v9_grade = compute_grade(v9_score)

        # v10 grade
        tbr_l1 = max(0.0, tbr_70 - tbr_54)
        overcorrection = compute_overcorrection_rate(glucose, bolus,
                                                     carbs_arr, n)
        safety = compute_safety_score(tbr_l1, tbr_54, overcorrection)
        v10_score_val = compute_v10_score(tir, cv, overnight_tir, safety)
        v10_grade = compute_v10_grade(v10_score_val)

        # Alignment: does pipeline grade match ADA status?
        v9_expected = grade_to_ada.get(v9_grade, 'below_targets')
        v10_expected = grade_to_ada.get(v10_grade, 'below_targets')

        # v9 alignment score
        v9_discrepancies = []
        if v9_expected != ada_status:
            v9_discrepancies.append(
                f'v9 {v9_grade}->{v9_expected} != ADA {ada_status}')
        if not meets_tbr and v9_grade in ('A', 'B'):
            v9_discrepancies.append('v9 misses TBR concern')
        v9_alignment = max(0.0, 1.0 - len(v9_discrepancies) * 0.25)
        v9_alignments.append(v9_alignment)

        # v10 alignment score
        v10_discrepancies = []
        if v10_expected != ada_status:
            v10_discrepancies.append(
                f'v10 {v10_grade}->{v10_expected} != ADA {ada_status}')
        if not meets_tbr and v10_grade in ('A', 'B'):
            v10_discrepancies.append('v10 misses TBR concern')
        v10_alignment = max(0.0, 1.0 - len(v10_discrepancies) * 0.25)
        v10_alignments.append(v10_alignment)

        improvement = v10_alignment - v9_alignment

        rec = {
            'pid': pid,
            'v9_grade': v9_grade,
            'v10_grade': v10_grade,
            'ada_status': ada_status,
            'v9_alignment': _safe_round(v9_alignment, 2),
            'v10_alignment': _safe_round(v10_alignment, 2),
            'improvement': _safe_round(improvement, 2),
        }
        results['per_patient'].append(rec)
        if args.detail:
            imp_str = f"+{improvement:.2f}" if improvement >= 0 \
                else f"{improvement:.2f}"
            print(f"  {pid}: v9={v9_grade}(align={v9_alignment:.2f}) "
                  f"v10={v10_grade}(align={v10_alignment:.2f}) "
                  f"ADA={ada_status} imp={imp_str}")

    results['n_patients'] = len(pids)
    results['population'] = {
        'v9_mean_alignment': _safe_round(
            float(np.mean(v9_alignments)) if v9_alignments else 0.0, 3),
        'v10_mean_alignment': _safe_round(
            float(np.mean(v10_alignments)) if v10_alignments else 0.0, 3),
        'alignment_improvement': _safe_round(
            float(np.mean(v10_alignments) - np.mean(v9_alignments))
            if v9_alignments and v10_alignments else 0.0, 3),
    }
    return results


# ===================================================================
# EXP-1500: Comprehensive Pipeline v10 Validation Summary
# ===================================================================

@register(1500, "Comprehensive Pipeline v10 Validation Summary")
def exp_1500(patients, args):
    """Final validation of the complete pipeline v10 with TBR integration:
    preconditions -> TBR check -> classification -> detection -> safety check
    -> recommendation -> scoring -> triage."""
    results = {'name': 'EXP-1500: Comprehensive Pipeline v10 Validation Summary',
               'per_patient': []}
    np.random.seed(RNG_SEED)

    pids = sorted(patients.keys())
    alignment_scores = []
    override_count = 0
    exec_times = []
    deployment_ready = 0

    for pid in pids:
        pdata = patients[pid]
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs_arr = pdata['carbs']
        iob = pdata['iob']
        temp_rate = pdata['temp_rate']
        n = len(glucose)

        t_start = time.time()

        # --- Stage 1: Preconditions ---
        valid_pct = float(pdata['valid'].sum() / max(n, 1) * 100)
        n_days = max(n // STEPS_PER_DAY, 1)

        # --- Stage 2: TBR check ---
        tbr_total = compute_tbr(glucose, HYPO_THRESHOLD)
        tbr_l1 = max(0.0,
                     compute_tbr(glucose, TIR_LO)
                     - compute_tbr(glucose, TBR_L1_LO))
        tbr_l2 = compute_tbr(glucose, SEVERE_HYPO_THRESHOLD)
        tar_l2 = compute_tar(glucose, TAR_L1_HI)

        # --- Stage 3: Classification ---
        tir = compute_tir(glucose)
        cv = compute_cv(glucose)
        overnight_tir = compute_overnight_tir(glucose, n)

        # --- Stage 4: Detection (hypo episodes) ---
        episodes = detect_hypo_episodes(glucose, HYPO_THRESHOLD,
                                        HYPO_MIN_DURATION_STEPS)

        # --- Stage 5: Safety check ---
        overcorrection = compute_overcorrection_rate(glucose, bolus,
                                                     carbs_arr, n)
        safety = compute_safety_score(tbr_l1, tbr_l2, overcorrection)

        # Safety tier
        if tbr_total > 8 and len(detect_hypo_episodes(
                glucose, SEVERE_HYPO_THRESHOLD,
                HYPO_MIN_DURATION_STEPS)) > 0:
            safety_tier = 'critical'
        elif tbr_total > 4:
            safety_tier = 'high'
        elif tbr_total > 2:
            safety_tier = 'moderate'
        else:
            safety_tier = 'low'

        # --- Stage 6: Recommendation ---
        assessment = compute_full_assessment(glucose, bolus, carbs_arr, n)
        standard_recs = generate_recommendations(assessment)

        # Safety-first override
        safety_override = False
        if tbr_total > 4.0:
            safety_override = True
            override_count += 1
            top_rec = 'reduce_aggressiveness'
        elif len(episodes) > 0 and any(
                hour_of_step(ep['start']) < 6 for ep in episodes):
            safety_override = True
            override_count += 1
            top_rec = 'reduce_overnight_basal'
        elif standard_recs:
            top_rec = standard_recs[0]['parameter']
        else:
            top_rec = 'no_change'

        # --- Stage 7: Scoring ---
        v10_score_val = compute_v10_score(tir, cv, overnight_tir, safety)
        v10_grade = compute_v10_grade(v10_score_val)

        # --- Stage 8: Triage ---
        urgency = classify_urgency(v10_grade, tir, cv)

        # ADA alignment
        meets_tir = tir >= ADA_TIR_TARGET
        meets_tbr = tbr_total < ADA_TBR_L1_TARGET and tbr_l2 < ADA_TBR_L2_TARGET
        meets_cv = cv < ADA_CV_TARGET
        n_met = sum([meets_tir, meets_tbr, meets_cv])
        if n_met == 3:
            ada_status = 'meets_all_targets'
        elif n_met == 2:
            ada_status = 'partially_meets'
        elif n_met == 1:
            ada_status = 'below_targets'
        else:
            ada_status = 'significantly_below'

        grade_to_ada = {'A': 'meets_all_targets', 'B': 'partially_meets',
                        'C': 'below_targets', 'D': 'significantly_below'}
        v10_expected = grade_to_ada.get(v10_grade, 'below_targets')
        discrepancies = []
        if v10_expected != ada_status:
            discrepancies.append('grade_mismatch')
        if not meets_tbr and v10_grade in ('A', 'B'):
            discrepancies.append('tbr_not_flagged')
        ada_alignment = max(0.0, 1.0 - len(discrepancies) * 0.25)
        alignment_scores.append(ada_alignment)

        # Confidence estimate
        confidence = min(1.0, valid_pct / 100 * 0.5
                         + (1.0 if n_days >= 14 else n_days / 14.0) * 0.3
                         + (1.0 if not safety_override else 0.7) * 0.2)

        t_elapsed = time.time() - t_start
        execution_ms = t_elapsed * 1000
        exec_times.append(execution_ms)

        # Deployment readiness: high confidence + good alignment + not critical
        if (confidence >= 0.7 and ada_alignment >= 0.5
                and safety_tier != 'critical'):
            deployment_ready += 1

        rec = {
            'pid': pid,
            'v10_grade': v10_grade,
            'v10_score': _safe_round(v10_score_val, 1),
            'safety_tier': safety_tier,
            'top_recommendation': top_rec,
            'confidence': _safe_round(confidence, 2),
            'ada_alignment': _safe_round(ada_alignment, 2),
            'execution_ms': _safe_round(execution_ms, 1),
        }
        results['per_patient'].append(rec)
        if args.detail:
            print(f"  {pid}: v10={v10_grade}({v10_score_val:.1f}) "
                  f"safety={safety_tier} rec={top_rec} "
                  f"ADA_align={ada_alignment:.2f} "
                  f"conf={confidence:.2f} "
                  f"t={execution_ms:.1f}ms")

    results['n_patients'] = len(pids)
    results['population'] = {
        'mean_alignment_v10': _safe_round(
            float(np.mean(alignment_scores))
            if alignment_scores else 0.0, 3),
        'n_safety_overrides': override_count,
        'mean_execution_ms': _safe_round(
            float(np.mean(exec_times)) if exec_times else 0.0, 1),
        'deployment_ready_count': deployment_ready,
    }
    return results


# ===================================================================
# Main entry point
# ===================================================================

def main():
    parser = argparse.ArgumentParser(
        description='EXP-1491 to EXP-1500: TBR Integration '
                    '& Safety Enhancement')
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
