#!/usr/bin/env python3
"""EXP-1481 to EXP-1490: Clinical Translation & Actionability.

This batch explores treatment-response phenotyping, empirical dose-response
curves, ISF circadian modelling, personalised target setting, carb counting
quality, AID parameter inference, therapy change impact prediction,
long-term outcome projection, clinical report generation, and validation
against ADA/AACE clinical guidelines.
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

# Meal time-of-day categories (hour ranges)
MEAL_BREAKFAST = (5, 10)
MEAL_LUNCH = (11, 14)
MEAL_DINNER = (17, 21)

# Bolus bin edges (units)
BOLUS_BIN_EDGES = [0, 1, 2, 4, 8, float('inf')]
BOLUS_BIN_LABELS = ['0-1U', '1-2U', '2-4U', '4-8U', '8+U']

# Insulin stacking
IOB_STACK_FACTOR = 2.0
DIA_STEPS = int(DIA_DEFAULT * STEPS_PER_HOUR)

# ISF estimation defaults
DEFAULT_ISF = 50.0      # mg/dL per unit
DEFAULT_CR = 10.0        # g carbs per unit

# ADA guideline thresholds
ADA_TIR_TARGET = 70.0
ADA_TIR_HIGH_RISK = 50.0
ADA_TBR_TARGET = 4.0         # % time below 70
ADA_TBR_SEVERE_TARGET = 1.0  # % time below 54
ADA_CV_TARGET = 36.0

# Clinical report urgency thresholds
URGENCY_IMMEDIATE_TIR = 40
URGENCY_SOON_TIR = 55

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
    se = np.sqrt(np.sum(residuals ** 2) / max(len(y) - 2, 1)) / np.sqrt(ss_xx)
    t_stat = abs(slope / se) if se > 1e-12 else 0.0
    if abs(slope) < 1e-6 or t_stat < 2.0:
        direction = 'stable'
    elif slope > 0:
        direction = 'increasing'
    else:
        direction = 'decreasing'
    return slope, t_stat, direction


def _normal_cdf(z):
    """Standard normal CDF via error function approximation."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2)))


# ---------------------------------------------------------------------------
# Helper functions -- recommendation generation
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
# Helper functions -- dose-response & circadian
# ---------------------------------------------------------------------------

def _bin_bolus(dose):
    """Return bin index (0-4) for a bolus dose."""
    for i in range(len(BOLUS_BIN_EDGES) - 1):
        if BOLUS_BIN_EDGES[i] <= dose < BOLUS_BIN_EDGES[i + 1]:
            return i
    return len(BOLUS_BIN_LABELS) - 1


def _linear_regression(x, y):
    """Simple OLS: y = slope*x + intercept.  Returns (slope, intercept, r2, residual_std)."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    mask = (~np.isnan(x)) & (~np.isnan(y))
    x, y = x[mask], y[mask]
    n = len(x)
    if n < 2:
        return 0.0, 0.0, 0.0, 0.0
    xm, ym = x.mean(), y.mean()
    ss_xx = np.sum((x - xm) ** 2)
    ss_xy = np.sum((x - xm) * (y - ym))
    if ss_xx < 1e-12:
        return 0.0, float(ym), 0.0, 0.0
    slope = float(ss_xy / ss_xx)
    intercept = float(ym - slope * xm)
    y_hat = slope * x + intercept
    ss_res = np.sum((y - y_hat) ** 2)
    ss_tot = np.sum((y - ym) ** 2)
    r2 = float(1 - ss_res / ss_tot) if ss_tot > 1e-12 else 0.0
    residual_std = float(np.sqrt(ss_res / max(n - 2, 1)))
    return slope, intercept, max(0.0, r2), residual_std


def _cosine_fit(hours, values):
    """Fit ISF(t) = A + B*cos(2*pi*(t - phi)/24).

    Uses grid search over phi (0-23) and analytical A, B for each.
    Returns (A, B, phi, r2).
    """
    h = np.asarray(hours, dtype=float)
    v = np.asarray(values, dtype=float)
    mask = (~np.isnan(h)) & (~np.isnan(v))
    h, v = h[mask], v[mask]
    n = len(h)
    if n < 3:
        m = float(np.mean(v)) if n > 0 else 0.0
        return m, 0.0, 0.0, 0.0

    best_r2 = -1.0
    best_params = (float(np.mean(v)), 0.0, 0.0)
    ss_tot = np.sum((v - np.mean(v)) ** 2)
    if ss_tot < 1e-12:
        return float(np.mean(v)), 0.0, 0.0, 0.0

    for phi_cand in range(24):
        cos_vals = np.cos(2 * np.pi * (h - phi_cand) / 24.0)
        # A + B*cos => design matrix [1, cos]
        X = np.column_stack([np.ones(n), cos_vals])
        XtX = X.T @ X
        det = XtX[0, 0] * XtX[1, 1] - XtX[0, 1] * XtX[1, 0]
        if abs(det) < 1e-12:
            continue
        XtY = X.T @ v
        inv = np.array([[XtX[1, 1], -XtX[0, 1]],
                         [-XtX[1, 0], XtX[0, 0]]]) / det
        beta = inv @ XtY
        A_cand, B_cand = float(beta[0]), float(beta[1])
        y_hat = A_cand + B_cand * cos_vals
        ss_res = np.sum((v - y_hat) ** 2)
        r2 = float(1 - ss_res / ss_tot)
        if r2 > best_r2:
            best_r2 = r2
            best_params = (A_cand, B_cand, float(phi_cand))

    A, B, phi = best_params
    return A, B, phi, max(0.0, best_r2)


def _sigmoid_adoption(t_days, half_life_days=14.0):
    """Sigmoid adoption curve: 0 at t=0, ~1 as t->inf, 0.5 at half_life."""
    return 1.0 / (1.0 + math.exp(-4.0 * (t_days - half_life_days) / half_life_days))


# ---------------------------------------------------------------------------
# Helper functions -- ADA guideline metrics
# ---------------------------------------------------------------------------

def _compute_tbr(glucose, threshold=70):
    """Compute time below range (%) at given threshold."""
    valid = glucose[~np.isnan(glucose)]
    if len(valid) == 0:
        return 0.0
    return float(np.mean(valid < threshold) * 100)


def _compute_tar(glucose, threshold=180):
    """Compute time above range (%) at given threshold."""
    valid = glucose[~np.isnan(glucose)]
    if len(valid) == 0:
        return 0.0
    return float(np.mean(valid > threshold) * 100)


def _compute_gmi(glucose):
    """Glucose Management Indicator (estimated A1C) from mean glucose."""
    valid = glucose[~np.isnan(glucose)]
    if len(valid) == 0:
        return 0.0
    mean_g = float(np.mean(valid))
    return round(3.31 + 0.02392 * mean_g, 1)


# ===================================================================
# EXP-1481: Treatment-Response Phenotyping
# ===================================================================

@register(1481, "Treatment-Response Phenotyping")
def exp_1481(patients, args):
    """Classify each patient into treatment-response phenotypes based on
    how they respond to insulin and carbs."""
    results = {'name': 'EXP-1481: Treatment-Response Phenotyping',
               'per_patient': []}
    np.random.seed(RNG_SEED)

    pids = sorted(patients.keys())
    phenotype_counts = defaultdict(int)

    for pid in pids:
        pdata = patients[pid]
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs = pdata['carbs']
        n = len(glucose)

        carb_window = 6  # ±30 min = 6 steps

        # --- Insulin response: bolus events with no carbs ±30 min ---
        insulin_drops = []
        insulin_doses = []
        for i in range(n):
            if bolus[i] <= 0 or np.isnan(glucose[i]):
                continue
            c_start = max(0, i - carb_window)
            c_end = min(n, i + carb_window + 1)
            if np.nansum(carbs[c_start:c_end]) > 2:
                continue
            end = min(i + 3 * STEPS_PER_HOUR, n)
            start_resp = min(i + STEPS_PER_HOUR, n)
            if end - start_resp < STEPS_PER_HOUR // 2:
                continue
            post = glucose[start_resp:end]
            valid_post = post[~np.isnan(post)]
            if len(valid_post) < 3:
                continue
            drop = glucose[i] - float(np.nanmin(valid_post))
            insulin_drops.append(drop)
            insulin_doses.append(bolus[i])

        n_insulin = len(insulin_drops)
        if n_insulin > 0 and np.sum(insulin_doses) > 0:
            per_unit_drops = [d / max(u, 0.1) for d, u in
                              zip(insulin_drops, insulin_doses)]
            insulin_response = float(np.median(per_unit_drops))
        else:
            insulin_response = 0.0

        # --- Carb response: carb events with glucose rise ---
        carb_rises = []
        carb_grams = []
        for i in range(n):
            if carbs[i] <= 0 or np.isnan(glucose[i]):
                continue
            end = min(i + 3 * STEPS_PER_HOUR, n)
            start_resp = min(i + STEPS_PER_HOUR, n)
            if end - start_resp < STEPS_PER_HOUR // 2:
                continue
            post = glucose[start_resp:end]
            valid_post = post[~np.isnan(post)]
            if len(valid_post) < 3:
                continue
            rise = float(np.nanmax(valid_post)) - glucose[i]
            if rise > 0:
                carb_rises.append(rise)
                carb_grams.append(carbs[i])

        n_carb = len(carb_rises)
        if n_carb > 0 and np.sum(carb_grams) > 0:
            per_gram_rises = [r / max(g, 1.0) for r, g in
                              zip(carb_rises, carb_grams)]
            carb_response = float(np.median(per_gram_rises))
        else:
            carb_response = 0.0

        # --- Correction response: bolus while glucose > 180 ---
        correction_drops = []
        for i in range(n):
            if bolus[i] <= 0 or np.isnan(glucose[i]):
                continue
            if glucose[i] <= TIR_HI:
                continue
            end = min(i + 3 * STEPS_PER_HOUR, n)
            start_resp = min(i + STEPS_PER_HOUR, n)
            if end - start_resp < STEPS_PER_HOUR // 2:
                continue
            post = glucose[start_resp:end]
            valid_post = post[~np.isnan(post)]
            if len(valid_post) < 3:
                continue
            drop = glucose[i] - float(np.nanmean(valid_post))
            correction_drops.append(drop)

        n_correction = len(correction_drops)
        correction_eff = (float(np.median(correction_drops))
                          if n_correction > 0 else 0.0)

        # --- Classify phenotype ---
        if n_insulin < 3 and n_carb < 3:
            phenotype = 'insufficient_data'
        elif insulin_response > 40:
            phenotype = 'insulin_sensitive'
        elif insulin_response < 15:
            phenotype = 'insulin_resistant'
        elif carb_response > 3.0:
            phenotype = 'carb_sensitive'
        else:
            phenotype = 'balanced'

        phenotype_counts[phenotype] += 1

        rec = {
            'pid': pid,
            'insulin_response_per_unit': _safe_round(insulin_response, 2),
            'carb_response_per_gram': _safe_round(carb_response, 3),
            'correction_effectiveness': _safe_round(correction_eff, 2),
            'phenotype': phenotype,
            'n_insulin_events': n_insulin,
            'n_carb_events': n_carb,
            'n_correction_events': n_correction,
        }
        results['per_patient'].append(rec)
        if args.detail:
            print(f"  {pid}: phenotype={phenotype} "
                  f"ins_resp={insulin_response:.1f}/U "
                  f"carb_resp={carb_response:.2f}/g "
                  f"corr_eff={correction_eff:.1f} "
                  f"[ins={n_insulin} carb={n_carb} corr={n_correction}]")

    results['n_patients'] = len(pids)
    results['phenotype_distribution'] = dict(phenotype_counts)
    return results


# ===================================================================
# EXP-1482: Empirical Dose-Response Curves
# ===================================================================

@register(1482, "Empirical Dose-Response Curves")
def exp_1482(patients, args):
    """Build empirical dose-response curves relating bolus size to glucose
    outcome for each patient."""
    results = {'name': 'EXP-1482: Empirical Dose-Response Curves',
               'per_patient': []}
    np.random.seed(RNG_SEED)

    pids = sorted(patients.keys())
    all_slopes = []

    for pid in pids:
        pdata = patients[pid]
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs = pdata['carbs']
        n = len(glucose)

        # Collect bolus events with response
        event_doses = []
        event_drops = []
        event_bins = defaultdict(list)

        carb_window = STEPS_PER_HOUR
        for i in range(n):
            if bolus[i] <= 0 or np.isnan(glucose[i]):
                continue
            c_start = max(0, i - carb_window)
            c_end = min(n, i + carb_window)
            if np.nansum(carbs[c_start:c_end]) > 2:
                continue
            # Nadir in 2-4h
            nadir_start = min(i + 2 * STEPS_PER_HOUR, n)
            nadir_end = min(i + 4 * STEPS_PER_HOUR, n)
            if nadir_end - nadir_start < STEPS_PER_HOUR:
                continue
            post_nadir = glucose[nadir_start:nadir_end]
            valid_nadir = post_nadir[~np.isnan(post_nadir)]
            if len(valid_nadir) < 3:
                continue
            # 3h glucose
            at_3h = min(i + 3 * STEPS_PER_HOUR, n - 1)
            if np.isnan(glucose[at_3h]):
                g_3h = float(np.nanmean(valid_nadir))
            else:
                g_3h = float(glucose[at_3h])

            drop = glucose[i] - float(np.nanmin(valid_nadir))
            dose = bolus[i]
            event_doses.append(dose)
            event_drops.append(drop)

            b = _bin_bolus(dose)
            event_bins[b].append({
                'dose': dose,
                'pre_glucose': float(glucose[i]),
                'nadir_glucose': float(np.nanmin(valid_nadir)),
                'glucose_3h': g_3h,
                'drop': drop,
            })

        # Per-bin statistics
        n_events_per_bin = {}
        for b_idx, label in enumerate(BOLUS_BIN_LABELS):
            evts = event_bins.get(b_idx, [])
            n_events_per_bin[label] = len(evts)

        # Fit linear model: drop = slope * dose + intercept
        slope, intercept, r2, res_std = _linear_regression(
            event_doses, event_drops)

        # Profile ISF estimate from existing assessments
        profile_isf = compute_isf_ratio(glucose, bolus, carbs, n)
        ratio = slope / profile_isf if abs(profile_isf) > 0.1 else 0.0

        all_slopes.append(slope)

        rec = {
            'pid': pid,
            'n_events_per_bin': n_events_per_bin,
            'empirical_isf_slope': _safe_round(slope, 2),
            'isf_r_squared': _safe_round(r2, 4),
            'residual_std': _safe_round(res_std, 2),
            'profile_isf': _safe_round(profile_isf, 2),
            'empirical_vs_profile_ratio': _safe_round(ratio, 3),
        }
        results['per_patient'].append(rec)
        if args.detail:
            total_events = sum(n_events_per_bin.values())
            print(f"  {pid}: slope={slope:.2f} R²={r2:.3f} "
                  f"res_std={res_std:.1f} ratio={ratio:.2f} "
                  f"n_events={total_events}")

    results['n_patients'] = len(pids)
    results['mean_empirical_isf'] = _safe_round(
        float(np.mean(all_slopes)) if all_slopes else 0.0, 2)
    return results


# ===================================================================
# EXP-1483: ISF Circadian Modeling
# ===================================================================

@register(1483, "ISF Circadian Modeling")
def exp_1483(patients, args):
    """Model ISF variation across the day using a sinusoidal fit."""
    results = {'name': 'EXP-1483: ISF Circadian Modeling',
               'per_patient': []}
    np.random.seed(RNG_SEED)

    pids = sorted(patients.keys())
    all_amplitudes = []

    for pid in pids:
        pdata = patients[pid]
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs = pdata['carbs']
        n = len(glucose)

        # Compute observed ISF for each bolus event
        event_hours = []
        event_isfs = []
        carb_window = STEPS_PER_HOUR
        response_window = 3 * STEPS_PER_HOUR

        for i in range(n):
            if bolus[i] < 0.5 or np.isnan(glucose[i]):
                continue
            c_start = max(0, i - carb_window)
            c_end = min(n, i + carb_window)
            if np.nansum(carbs[c_start:c_end]) > 2:
                continue
            end = min(i + response_window, n)
            post = glucose[i:end]
            valid_post = post[~np.isnan(post)]
            if len(valid_post) < response_window // 3:
                continue
            drop = glucose[i] - float(np.nanmin(valid_post))
            if bolus[i] > 0:
                observed_isf = drop / bolus[i]
            else:
                continue
            hour = hour_of_step(i)
            event_hours.append(float(hour))
            event_isfs.append(observed_isf)

        n_events = len(event_hours)
        if n_events < 3:
            rec = {
                'pid': pid,
                'mean_isf': 0.0,
                'amplitude': 0.0,
                'peak_hour': 0,
                'trough_hour': 12,
                'amplitude_pct': 0.0,
                'n_events': n_events,
                'fit_r_squared': 0.0,
            }
        else:
            A, B, phi, r2 = _cosine_fit(event_hours, event_isfs)
            amplitude_pct = abs(B) / abs(A) * 100 if abs(A) > 0.01 else 0.0
            peak_hour = int(phi) % 24
            trough_hour = (int(phi) + 12) % 24

            rec = {
                'pid': pid,
                'mean_isf': _safe_round(A, 2),
                'amplitude': _safe_round(abs(B), 2),
                'peak_hour': peak_hour,
                'trough_hour': trough_hour,
                'amplitude_pct': _safe_round(amplitude_pct, 1),
                'n_events': n_events,
                'fit_r_squared': _safe_round(r2, 4),
            }
            all_amplitudes.append(abs(B))

        results['per_patient'].append(rec)
        if args.detail:
            print(f"  {pid}: mean_isf={rec['mean_isf']} "
                  f"amp={rec['amplitude']} peak_h={rec['peak_hour']} "
                  f"trough_h={rec['trough_hour']} "
                  f"amp%={rec['amplitude_pct']} R²={rec['fit_r_squared']} "
                  f"n={rec['n_events']}")

    results['n_patients'] = len(pids)
    results['mean_amplitude'] = _safe_round(
        float(np.mean(all_amplitudes)) if all_amplitudes else 0.0, 2)
    results['significant_circadian_count'] = sum(
        1 for r in results['per_patient']
        if r['amplitude_pct'] > 20 and r['fit_r_squared'] > 0.1)
    return results


# ===================================================================
# EXP-1484: Personalized Target Setting
# ===================================================================

@register(1484, "Personalized Target Setting")
def exp_1484(patients, args):
    """Determine patient-specific glucose targets based on demonstrated
    capabilities."""
    results = {'name': 'EXP-1484: Personalized Target Setting',
               'per_patient': []}
    np.random.seed(RNG_SEED)

    pids = sorted(patients.keys())
    improvements = []

    for pid in pids:
        pdata = patients[pid]
        glucose = pdata['glucose']
        valid = glucose[~np.isnan(glucose)]

        if len(valid) < 100:
            rec = {
                'pid': pid,
                'mode_glucose': 0.0,
                'iqr_low': 70.0,
                'iqr_high': 180.0,
                'iqr_width': 110.0,
                'suggested_low': 70.0,
                'suggested_high': 180.0,
                'current_tir': 0.0,
                'personalized_tir': 0.0,
                'tir_improvement': 0.0,
            }
            results['per_patient'].append(rec)
            continue

        # Mode: glucose histogram, 10 mg/dL bins
        bin_edges = np.arange(40, 401, 10)
        counts, _ = np.histogram(valid, bins=bin_edges)
        mode_bin = int(np.argmax(counts))
        mode_glucose = float(bin_edges[mode_bin] + 5)  # bin center

        # Narrowest range containing 50% of readings
        sorted_g = np.sort(valid)
        half_n = len(sorted_g) // 2
        if half_n < 1:
            half_n = 1
        min_width = float('inf')
        best_low_idx = 0
        for start_idx in range(len(sorted_g) - half_n):
            width = sorted_g[start_idx + half_n - 1] - sorted_g[start_idx]
            if width < min_width:
                min_width = width
                best_low_idx = start_idx
        iqr_low = float(sorted_g[best_low_idx])
        iqr_high = float(sorted_g[best_low_idx + half_n - 1])
        iqr_width = iqr_high - iqr_low

        # Personalized targets
        p5 = float(np.percentile(valid, 5))
        p95 = float(np.percentile(valid, 95))
        suggested_low = max(TIR_LO, p5 + 10)
        suggested_high = min(300, p95 - 10)
        # Ensure suggested range makes sense
        if suggested_high <= suggested_low:
            suggested_low = TIR_LO
            suggested_high = TIR_HI

        current_tir = compute_tir(glucose)
        personalized_tir = compute_tir(glucose, lo=suggested_low,
                                       hi=suggested_high)
        tir_improvement = personalized_tir - current_tir
        improvements.append(tir_improvement)

        rec = {
            'pid': pid,
            'mode_glucose': _safe_round(mode_glucose, 1),
            'iqr_low': _safe_round(iqr_low, 1),
            'iqr_high': _safe_round(iqr_high, 1),
            'iqr_width': _safe_round(iqr_width, 1),
            'suggested_low': _safe_round(suggested_low, 1),
            'suggested_high': _safe_round(suggested_high, 1),
            'current_tir': _safe_round(current_tir, 1),
            'personalized_tir': _safe_round(personalized_tir, 1),
            'tir_improvement': _safe_round(tir_improvement, 1),
        }
        results['per_patient'].append(rec)
        if args.detail:
            print(f"  {pid}: mode={mode_glucose:.0f} "
                  f"iqr=[{iqr_low:.0f}-{iqr_high:.0f}] w={iqr_width:.0f} "
                  f"suggested=[{suggested_low:.0f}-{suggested_high:.0f}] "
                  f"TIR {current_tir:.1f}→{personalized_tir:.1f} "
                  f"(Δ{tir_improvement:+.1f})")

    results['n_patients'] = len(pids)
    results['mean_tir_improvement'] = _safe_round(
        float(np.mean(improvements)) if improvements else 0.0, 1)
    results['patients_with_narrow_iqr'] = sum(
        1 for r in results['per_patient'] if r['iqr_width'] < 60)
    return results


# ===================================================================
# EXP-1485: Carb Counting Quality Score
# ===================================================================

@register(1485, "Carb Counting Quality Score")
def exp_1485(patients, args):
    """Estimate carb counting accuracy by analysing post-meal glucose
    patterns."""
    results = {'name': 'EXP-1485: Carb Counting Quality Score',
               'per_patient': []}
    np.random.seed(RNG_SEED)

    pids = sorted(patients.keys())
    all_scores = []

    for pid in pids:
        pdata = patients[pid]
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs_arr = pdata['carbs']
        n = len(glucose)

        # Estimate patient's CR and ISF from data
        profile_isf = compute_isf_ratio(glucose, bolus, carbs_arr, n)
        if profile_isf < 1:
            profile_isf = DEFAULT_ISF

        # Estimate effective CR from bolus/carb pairs
        cr_values = []
        for i in range(n):
            if carbs_arr[i] > 5 and bolus[i] > 0.1:
                cr_values.append(carbs_arr[i] / bolus[i])
        effective_cr = float(np.median(cr_values)) if cr_values else DEFAULT_CR

        ratios = []
        n_undercounted = 0
        n_overcounted = 0

        for i in range(n):
            if carbs_arr[i] <= 5 or np.isnan(glucose[i]):
                continue
            # Expected rise: carbs / CR * ISF
            expected_rise = (carbs_arr[i] / max(effective_cr, 1.0)
                             * profile_isf)
            if expected_rise < 1:
                continue

            # Actual rise: max glucose in 3h - pre-meal
            end = min(i + 3 * STEPS_PER_HOUR, n)
            post = glucose[i:end]
            valid_post = post[~np.isnan(post)]
            if len(valid_post) < STEPS_PER_HOUR // 2:
                continue
            actual_rise = float(np.nanmax(valid_post)) - glucose[i]
            if actual_rise < 0:
                actual_rise = 0

            ratio = actual_rise / expected_rise
            ratios.append(ratio)

            if ratio > 1.5:
                n_undercounted += 1
            elif ratio < 0.5:
                n_overcounted += 1

        n_meals = len(ratios)
        if n_meals > 0:
            median_ratio = float(np.median(ratios))
            mean_ratio = float(np.mean(ratios))
            std_ratio = float(np.std(ratios))
            quality_score = max(0, 100 - abs(median_ratio - 1.0) * 100)

            if median_ratio > 1.3:
                counting_bias = 'undercounting'
            elif median_ratio < 0.7:
                counting_bias = 'overcounting'
            else:
                counting_bias = 'accurate'
        else:
            median_ratio = 0.0
            mean_ratio = 0.0
            std_ratio = 0.0
            quality_score = 0.0
            counting_bias = 'insufficient_data'

        all_scores.append(quality_score)

        rec = {
            'pid': pid,
            'n_meals': n_meals,
            'median_ratio': _safe_round(median_ratio, 3),
            'mean_ratio': _safe_round(mean_ratio, 3),
            'std_ratio': _safe_round(std_ratio, 3),
            'quality_score': _safe_round(quality_score, 1),
            'counting_bias': counting_bias,
            'n_undercounted': n_undercounted,
            'n_overcounted': n_overcounted,
        }
        results['per_patient'].append(rec)
        if args.detail:
            print(f"  {pid}: meals={n_meals} med_ratio={median_ratio:.2f} "
                  f"score={quality_score:.0f} bias={counting_bias} "
                  f"under={n_undercounted} over={n_overcounted}")

    results['n_patients'] = len(pids)
    results['mean_quality_score'] = _safe_round(
        float(np.mean(all_scores)) if all_scores else 0.0, 1)
    results['bias_distribution'] = {
        'undercounting': sum(1 for r in results['per_patient']
                             if r['counting_bias'] == 'undercounting'),
        'overcounting': sum(1 for r in results['per_patient']
                            if r['counting_bias'] == 'overcounting'),
        'accurate': sum(1 for r in results['per_patient']
                        if r['counting_bias'] == 'accurate'),
        'insufficient_data': sum(1 for r in results['per_patient']
                                 if r['counting_bias'] == 'insufficient_data'),
    }
    return results


# ===================================================================
# EXP-1486: AID Algorithm Parameter Inference
# ===================================================================

@register(1486, "AID Algorithm Parameter Inference")
def exp_1486(patients, args):
    """Infer the AID algorithm's effective parameters from observed
    behaviour."""
    results = {'name': 'EXP-1486: AID Algorithm Parameter Inference',
               'per_patient': []}
    np.random.seed(RNG_SEED)

    pids = sorted(patients.keys())
    all_targets = []

    for pid in pids:
        pdata = patients[pid]
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        temp_rate = pdata['temp_rate']
        iob = pdata['iob']
        n = len(glucose)

        # --- Effective target: median glucose during stable zero-bolus periods ---
        stable_glucose = []
        window = 2 * STEPS_PER_HOUR  # 2-hour windows
        for start in range(0, n - window, window):
            seg_bolus = bolus[start:start + window]
            seg_rate = temp_rate[start:start + window]
            seg_g = glucose[start:start + window]
            # Zero bolus in window
            if np.nansum(seg_bolus) > 0:
                continue
            # Stable temp rate: std < 0.1
            valid_rate = seg_rate[~np.isnan(seg_rate)]
            if len(valid_rate) < window // 2:
                continue
            if np.std(valid_rate) > 0.1:
                continue
            valid_g = seg_g[~np.isnan(seg_g)]
            if len(valid_g) >= window // 2:
                stable_glucose.extend(valid_g.tolist())

        effective_target = (float(np.median(stable_glucose))
                            if stable_glucose else 120.0)

        # --- Effective max IOB: 95th percentile ---
        valid_iob = iob[~np.isnan(iob)]
        if len(valid_iob) > 10:
            effective_max_iob = float(np.percentile(valid_iob, 95))
        else:
            effective_max_iob = 0.0

        # --- Correction aggressiveness: correlation (glucose - target) vs
        #     subsequent temp_rate change ---
        glucose_deviations = []
        rate_changes = []
        lookforward = STEPS_PER_HOUR  # 1 hour
        for i in range(n - lookforward):
            if np.isnan(glucose[i]) or np.isnan(temp_rate[i]):
                continue
            future_rates = temp_rate[i:i + lookforward]
            valid_future = future_rates[~np.isnan(future_rates)]
            if len(valid_future) < lookforward // 2:
                continue
            deviation = glucose[i] - effective_target
            rate_change = float(np.mean(valid_future)) - temp_rate[i]
            glucose_deviations.append(deviation)
            rate_changes.append(rate_change)

        if len(glucose_deviations) > 10:
            x = np.asarray(glucose_deviations)
            y = np.asarray(rate_changes)
            xm, ym = x.mean(), y.mean()
            ss_xy = np.sum((x - xm) * (y - ym))
            ss_xx = np.sum((x - xm) ** 2)
            ss_yy = np.sum((y - ym) ** 2)
            denom = math.sqrt(ss_xx * ss_yy) if ss_xx > 0 and ss_yy > 0 else 1
            corr_aggressiveness = float(ss_xy / denom)
        else:
            corr_aggressiveness = 0.0

        # --- Suspend threshold: glucose below which temp_rate → near zero ---
        low_glucose_rates = []
        for i in range(n):
            if np.isnan(glucose[i]) or np.isnan(temp_rate[i]):
                continue
            if glucose[i] < 100:
                low_glucose_rates.append((glucose[i], temp_rate[i]))

        suspend_threshold = 0.0
        if len(low_glucose_rates) > 5:
            sorted_lr = sorted(low_glucose_rates, key=lambda x: x[0])
            # Find glucose where rate drops below 10% of median rate
            median_rate = float(np.median([r for _, r in low_glucose_rates]))
            threshold_rate = max(median_rate * 0.1, 0.01)
            for g_val, r_val in sorted_lr:
                if r_val <= threshold_rate:
                    suspend_threshold = g_val
                    break
            if suspend_threshold == 0.0:
                suspend_threshold = float(sorted_lr[0][0])

        n_stable = len(stable_glucose) // (2 * STEPS_PER_HOUR) if stable_glucose else 0
        all_targets.append(effective_target)

        rec = {
            'pid': pid,
            'effective_target': _safe_round(effective_target, 1),
            'effective_max_iob': _safe_round(effective_max_iob, 2),
            'correction_aggressiveness': _safe_round(corr_aggressiveness, 4),
            'suspend_threshold': _safe_round(suspend_threshold, 1),
            'n_stable_periods': n_stable,
        }
        results['per_patient'].append(rec)
        if args.detail:
            print(f"  {pid}: target={effective_target:.1f} "
                  f"max_iob={effective_max_iob:.2f} "
                  f"aggr={corr_aggressiveness:.3f} "
                  f"suspend={suspend_threshold:.0f} "
                  f"stable_periods={n_stable}")

    results['n_patients'] = len(pids)
    results['mean_effective_target'] = _safe_round(
        float(np.mean(all_targets)) if all_targets else 0.0, 1)
    results['target_range'] = {
        'min': _safe_round(float(np.min(all_targets)) if all_targets else 0, 1),
        'max': _safe_round(float(np.max(all_targets)) if all_targets else 0, 1),
    }
    return results


# ===================================================================
# EXP-1487: Therapy Change Impact Prediction
# ===================================================================

@register(1487, "Therapy Change Impact Prediction")
def exp_1487(patients, args):
    """Predict the impact of specific therapy changes using historical
    observational data ('natural experiment' approach)."""
    results = {'name': 'EXP-1487: Therapy Change Impact Prediction',
               'per_patient': []}
    np.random.seed(RNG_SEED)

    pids = sorted(patients.keys())

    for pid in pids:
        pdata = patients[pid]
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs_arr = pdata['carbs']
        temp_rate = pdata['temp_rate']
        n = len(glucose)
        n_days = max(n // STEPS_PER_DAY, 1)

        # Baseline metrics
        baseline_tir = compute_tir(glucose)
        baseline_mean_rate = float(np.nanmean(temp_rate)) if np.any(
            ~np.isnan(temp_rate)) else 0.0

        # --- Scenario 1: Basal +10% ---
        # Find periods where actual temp_rate was ~10% above the patient's
        # median rate and compare TIR in those windows.
        median_rate = float(np.nanmedian(
            temp_rate[~np.isnan(temp_rate)])) if np.any(
            ~np.isnan(temp_rate)) else 0.0
        high_rate_threshold = median_rate * 1.05  # ≥5% above to capture ~10%
        high_rate_windows = []
        low_rate_windows = []
        window = 6 * STEPS_PER_HOUR  # 6-hour evaluation windows

        for start in range(0, n - window, window):
            seg_rate = temp_rate[start:start + window]
            seg_g = glucose[start:start + window]
            valid_rate = seg_rate[~np.isnan(seg_rate)]
            if len(valid_rate) < window // 2:
                continue
            mean_seg_rate = float(np.mean(valid_rate))
            if mean_seg_rate > high_rate_threshold and median_rate > 0.01:
                high_rate_windows.append(compute_tir(seg_g))
            else:
                low_rate_windows.append(compute_tir(seg_g))

        n_natural_basal_high = len(high_rate_windows)
        if n_natural_basal_high > 2 and low_rate_windows:
            basal_plus10_tir = float(np.mean(high_rate_windows))
        else:
            basal_plus10_tir = baseline_tir

        # --- Scenario 2: CR -30% (tighter CR) ---
        # Find meals where effective CR was lower than average
        meal_cr_values = []
        meal_cr_excursions = []
        for i in range(n):
            if carbs_arr[i] <= 5 or bolus[i] <= 0.1:
                continue
            if np.isnan(glucose[i]):
                continue
            cr_i = carbs_arr[i] / bolus[i]
            meal_cr_values.append(cr_i)
            end = min(i + 3 * STEPS_PER_HOUR, n)
            post = glucose[i:end]
            valid_post = post[~np.isnan(post)]
            exc = (float(np.nanmax(valid_post) - glucose[i])
                   if len(valid_post) > 3 else 0.0)
            meal_cr_excursions.append((cr_i, exc))

        n_natural_cr_low = 0
        cr_minus30_exc = 0.0
        if meal_cr_values:
            median_cr = float(np.median(meal_cr_values))
            cr_threshold = median_cr * 0.85
            low_cr_exc = [exc for cr, exc in meal_cr_excursions
                          if cr < cr_threshold]
            high_cr_exc = [exc for cr, exc in meal_cr_excursions
                           if cr >= cr_threshold]
            n_natural_cr_low = len(low_cr_exc)
            if n_natural_cr_low > 2:
                cr_minus30_exc = float(np.mean(low_cr_exc))
            elif high_cr_exc:
                cr_minus30_exc = float(np.mean(high_cr_exc))

        # --- Scenario 3: ISF +10% ---
        # Find corrections where effective ISF was higher
        isf_events = []
        carb_window = STEPS_PER_HOUR
        for i in range(n):
            if bolus[i] < MIN_BOLUS_ISF or np.isnan(glucose[i]):
                continue
            c_start = max(0, i - carb_window)
            c_end = min(n, i + carb_window)
            if np.nansum(carbs_arr[c_start:c_end]) > 2:
                continue
            end = min(i + 3 * STEPS_PER_HOUR, n)
            post = glucose[i:end]
            valid_post = post[~np.isnan(post)]
            if len(valid_post) < STEPS_PER_HOUR:
                continue
            drop = glucose[i] - float(np.nanmin(valid_post))
            eff_isf = drop / bolus[i] if bolus[i] > 0 else 0
            # Outcome: did glucose land in range?
            in_range = (float(np.nanmin(valid_post)) >= TIR_LO)
            isf_events.append((eff_isf, in_range))

        n_natural_isf_high = 0
        isf_plus10_corr = 0.0
        if isf_events:
            median_isf = float(np.median([e[0] for e in isf_events]))
            isf_threshold = median_isf * 1.05
            high_isf = [ir for isf, ir in isf_events if isf > isf_threshold]
            n_natural_isf_high = len(high_isf)
            if n_natural_isf_high > 0:
                isf_plus10_corr = float(np.mean(high_isf)) * 100
            else:
                isf_plus10_corr = (float(np.mean(
                    [ir for _, ir in isf_events])) * 100 if isf_events else 0)

        rec = {
            'pid': pid,
            'basal_plus10_tir_est': _safe_round(basal_plus10_tir, 1),
            'cr_minus30_exc_est': _safe_round(cr_minus30_exc, 1),
            'isf_plus10_corr_est': _safe_round(isf_plus10_corr, 1),
            'n_natural_basal_high': n_natural_basal_high,
            'n_natural_cr_low': n_natural_cr_low,
            'n_natural_isf_high': n_natural_isf_high,
        }
        results['per_patient'].append(rec)
        if args.detail:
            print(f"  {pid}: basal+10%_TIR={basal_plus10_tir:.1f} "
                  f"CR-30%_exc={cr_minus30_exc:.1f} "
                  f"ISF+10%_corr={isf_plus10_corr:.1f}% "
                  f"[nB={n_natural_basal_high} nC={n_natural_cr_low} "
                  f"nI={n_natural_isf_high}]")

    results['n_patients'] = len(pids)
    return results


# ===================================================================
# EXP-1488: Long-Term Outcome Projection
# ===================================================================

@register(1488, "Long-Term Outcome Projection")
def exp_1488(patients, args):
    """Project expected TIR changes over 3, 6, 12 months if
    recommendations are followed."""
    results = {'name': 'EXP-1488: Long-Term Outcome Projection',
               'per_patient': []}
    np.random.seed(RNG_SEED)

    pids = sorted(patients.keys())
    projected_improvements = []

    for pid in pids:
        pdata = patients[pid]
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs_arr = pdata['carbs']
        n = len(glucose)
        n_days = max(n // STEPS_PER_DAY, 1)

        current_tir = compute_tir(glucose)

        # --- Monthly TIR trend from existing data ---
        monthly_tirs = []
        days_per_month = 30
        steps_per_month = days_per_month * STEPS_PER_DAY
        for m_start in range(0, n, steps_per_month):
            m_end = min(m_start + steps_per_month, n)
            if m_end - m_start < 7 * STEPS_PER_DAY:
                break
            seg = glucose[m_start:m_end]
            monthly_tirs.append(compute_tir(seg))

        if len(monthly_tirs) >= 2:
            trend_rate, _, _ = _linear_trend(monthly_tirs)
        else:
            trend_rate = 0.0

        # --- Therapy fix impact estimate ---
        assessment = compute_full_assessment(glucose, bolus, carbs_arr, n)
        flags = assessment['flags']
        # Each fixable issue contributes an estimated TIR improvement
        therapy_impact = 0.0
        if flags.get('basal_flag', False):
            therapy_impact += 5.0  # Basal fix: ~5% TIR
        if flags.get('cr_flag', False):
            therapy_impact += 3.0  # CR fix: ~3% TIR
        if flags.get('cv_flag', False):
            therapy_impact += 2.0  # ISF/CV fix: ~2% TIR

        # Cap therapy impact at what's achievable
        max_achievable = 100 - current_tir
        therapy_impact = min(therapy_impact, max_achievable * 0.5)

        # --- Project forward ---
        # TIR(t) = current_tir + therapy_impact * adoption(t) + trend * t
        projected_3mo = min(100, max(0, current_tir
                                     + therapy_impact * _sigmoid_adoption(90)
                                     + trend_rate * 3))
        projected_6mo = min(100, max(0, current_tir
                                     + therapy_impact * _sigmoid_adoption(180)
                                     + trend_rate * 6))
        projected_12mo = min(100, max(0, current_tir
                                      + therapy_impact * _sigmoid_adoption(365)
                                      + trend_rate * 12))

        score_3 = compute_score(projected_3mo, assessment['cv'])
        score_6 = compute_score(projected_6mo, assessment['cv'])
        grade_3mo = compute_grade(score_3)
        grade_6mo = compute_grade(score_6)

        improvement = projected_12mo - current_tir
        projected_improvements.append(improvement)

        rec = {
            'pid': pid,
            'current_tir': _safe_round(current_tir, 1),
            'projected_3mo': _safe_round(projected_3mo, 1),
            'projected_6mo': _safe_round(projected_6mo, 1),
            'projected_12mo': _safe_round(projected_12mo, 1),
            'therapy_impact': _safe_round(therapy_impact, 1),
            'trend_rate': _safe_round(trend_rate, 3),
            'projected_grade_3mo': grade_3mo,
            'projected_grade_6mo': grade_6mo,
        }
        results['per_patient'].append(rec)
        if args.detail:
            print(f"  {pid}: TIR now={current_tir:.1f} "
                  f"→3mo={projected_3mo:.1f}({grade_3mo}) "
                  f"→6mo={projected_6mo:.1f}({grade_6mo}) "
                  f"→12mo={projected_12mo:.1f} "
                  f"impact={therapy_impact:.1f} trend={trend_rate:.3f}")

    results['n_patients'] = len(pids)
    results['mean_projected_improvement'] = _safe_round(
        float(np.mean(projected_improvements))
        if projected_improvements else 0.0, 1)
    results['patients_grade_upgrade_3mo'] = sum(
        1 for r in results['per_patient']
        if r['projected_grade_3mo'] > compute_grade(
            compute_score(r['current_tir'],
                          compute_cv(patients[r['pid']]['glucose']))))
    return results


# ===================================================================
# EXP-1489: Clinical Report Generation
# ===================================================================

@register(1489, "Clinical Report Generation")
def exp_1489(patients, args):
    """Generate a structured clinical report suitable for healthcare
    provider review for each patient."""
    results = {'name': 'EXP-1489: Clinical Report Generation',
               'per_patient': []}
    np.random.seed(RNG_SEED)

    pids = sorted(patients.keys())

    for pid in pids:
        pdata = patients[pid]
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs_arr = pdata['carbs']
        iob = pdata['iob']
        n = len(glucose)
        n_days = max(n // STEPS_PER_DAY, 1)

        # Core assessment
        assessment = compute_full_assessment(glucose, bolus, carbs_arr, n)
        tir = assessment['tir']
        cv = assessment['cv']
        grade = assessment['grade']
        score = assessment['score']

        # Additional metrics
        mean_g = float(np.nanmean(glucose[~np.isnan(glucose)]))
        gmi = _compute_gmi(glucose)
        tbr_70 = _compute_tbr(glucose, 70)
        tbr_54 = _compute_tbr(glucose, 54)
        tar_180 = _compute_tar(glucose, 180)
        tar_250 = _compute_tar(glucose, 250)
        overnight_tir = compute_overnight_tir(glucose, n)
        postmeal_tir = compute_postmeal_tir(glucose, carbs_arr, n)

        # --- Summary section ---
        if grade == 'A':
            status_text = 'Well-controlled diabetes management'
        elif grade == 'B':
            status_text = 'Adequate control with room for improvement'
        elif grade == 'C':
            status_text = 'Suboptimal control requiring attention'
        else:
            status_text = 'Poor control requiring immediate intervention'

        summary = {
            'status': status_text,
            'grade': grade,
            'score': _safe_round(score, 1),
            'tir': _safe_round(tir, 1),
            'mean_glucose': _safe_round(mean_g, 0),
            'gmi': gmi,
            'cv': _safe_round(cv, 1),
            'data_days': n_days,
            'key_concerns': [],
        }
        if tbr_70 > ADA_TBR_TARGET:
            summary['key_concerns'].append(
                f'Excessive hypoglycemia: {tbr_70:.1f}% below 70 mg/dL')
        if tar_250 > 5:
            summary['key_concerns'].append(
                f'Significant hyperglycemia: {tar_250:.1f}% above 250 mg/dL')
        if cv > CV_THRESHOLD:
            summary['key_concerns'].append(
                f'High glucose variability: CV={cv:.1f}%')
        if not summary['key_concerns']:
            summary['key_concerns'].append('No critical concerns identified')

        # --- Recommendations section ---
        recs = generate_recommendations(assessment)
        recommendations = []
        for idx, rec_item in enumerate(recs, 1):
            recommendations.append({
                'priority': idx,
                'parameter': rec_item['parameter'],
                'action': f"{rec_item['direction']} {rec_item['parameter']} "
                          f"by {rec_item['magnitude_pct']}%",
                'rationale': rec_item['rationale'],
                'confidence': 'high' if assessment['score'] < 60 else 'moderate',
                'expected_impact': f'+2-5% TIR improvement',
            })
        if not recommendations:
            recommendations.append({
                'priority': 1,
                'parameter': 'none',
                'action': 'Maintain current therapy settings',
                'rationale': 'All parameters within acceptable range',
                'confidence': 'high',
                'expected_impact': 'Stable TIR',
            })

        # --- Risk section ---
        overcorr = compute_overcorrection_rate(glucose, bolus, carbs_arr, n)
        # Hypo risk
        if tbr_70 > 8:
            hypo_risk = 'high'
        elif tbr_70 > ADA_TBR_TARGET:
            hypo_risk = 'moderate'
        else:
            hypo_risk = 'low'

        # Stacking risk from IOB patterns
        valid_iob = iob[~np.isnan(iob)]
        if len(valid_iob) > 10:
            iob_p95 = float(np.percentile(valid_iob, 95))
            iob_mean = float(np.mean(valid_iob))
            stacking_risk = ('high' if iob_p95 > IOB_STACK_FACTOR * iob_mean
                             and iob_mean > 0.5 else 'low')
        else:
            stacking_risk = 'unknown'

        overcorr_risk = ('high' if overcorr > 0.3
                         else 'moderate' if overcorr > 0.15
                         else 'low')

        risks = {
            'hypo_risk': hypo_risk,
            'stacking_risk': stacking_risk,
            'overcorrection_risk': overcorr_risk,
            'tbr_70': _safe_round(tbr_70, 1),
            'tbr_54': _safe_round(tbr_54, 1),
            'overcorrection_rate': _safe_round(overcorr * 100, 1),
        }

        # --- Monitoring plan ---
        urgency = classify_urgency(grade, tir, cv)
        if urgency == 'immediate':
            followup = '1-2 weeks'
            metrics = ['TIR', 'TBR', 'hypo events', 'basal rate']
        elif urgency == 'soon':
            followup = '2-4 weeks'
            metrics = ['TIR', 'CV', 'postmeal excursions']
        elif urgency == 'routine':
            followup = '4-8 weeks'
            metrics = ['TIR', 'A1C/GMI']
        else:
            followup = '3 months'
            metrics = ['TIR', 'A1C/GMI']

        monitoring_plan = {
            'urgency': urgency,
            'followup_interval': followup,
            'metrics_to_track': metrics,
            'next_review_focus': ('Address ' + recommendations[0]['parameter']
                                  if recommendations else 'General review'),
        }

        # Word count estimate
        report_text = json.dumps({
            'summary': summary,
            'recommendations': recommendations,
            'risks': risks,
            'monitoring_plan': monitoring_plan,
        }, indent=2)
        word_count = len(report_text.split())

        rec = {
            'pid': pid,
            'report_sections': {
                'summary': summary,
                'recommendations': recommendations,
                'risks': risks,
                'monitoring_plan': monitoring_plan,
            },
            'word_count': word_count,
            'clinical_urgency': urgency,
        }
        results['per_patient'].append(rec)
        if args.detail:
            print(f"  {pid}: grade={grade} urgency={urgency} "
                  f"concerns={len(summary['key_concerns'])} "
                  f"recs={len(recommendations)} "
                  f"hypo_risk={hypo_risk} words={word_count}")

    results['n_patients'] = len(pids)
    results['urgency_distribution'] = {
        'immediate': sum(1 for r in results['per_patient']
                         if r['clinical_urgency'] == 'immediate'),
        'soon': sum(1 for r in results['per_patient']
                    if r['clinical_urgency'] == 'soon'),
        'routine': sum(1 for r in results['per_patient']
                       if r['clinical_urgency'] == 'routine'),
        'monitoring-only': sum(1 for r in results['per_patient']
                               if r['clinical_urgency'] == 'monitoring-only'),
    }
    return results


# ===================================================================
# EXP-1490: Validation Against Clinical Guidelines
# ===================================================================

@register(1490, "Validation Against Clinical Guidelines")
def exp_1490(patients, args):
    """Compare pipeline recommendations against ADA/AACE clinical
    guidelines."""
    results = {'name': 'EXP-1490: Validation Against Clinical Guidelines',
               'per_patient': []}
    np.random.seed(RNG_SEED)

    pids = sorted(patients.keys())
    alignment_scores = []

    for pid in pids:
        pdata = patients[pid]
        glucose = pdata['glucose']
        bolus = pdata['bolus']
        carbs_arr = pdata['carbs']
        n = len(glucose)

        # Compute ADA metrics
        tir = compute_tir(glucose)
        tbr_70 = _compute_tbr(glucose, 70)
        tbr_54 = _compute_tbr(glucose, 54)
        tar_180 = _compute_tar(glucose, 180)
        cv = compute_cv(glucose)

        # ADA compliance checks
        meets_ada_tir = tir >= ADA_TIR_TARGET
        meets_ada_tbr = (tbr_70 < ADA_TBR_TARGET
                         and tbr_54 < ADA_TBR_SEVERE_TARGET)
        meets_ada_cv = cv < ADA_CV_TARGET

        # Overall ADA classification
        n_met = sum([meets_ada_tir, meets_ada_tbr, meets_ada_cv])
        if n_met == 3:
            ada_overall = 'meets_all_targets'
        elif n_met == 2:
            ada_overall = 'partially_meets'
        elif n_met == 1:
            ada_overall = 'below_targets'
        else:
            ada_overall = 'significantly_below'

        # High-risk patient check (elderly, hypoglycemia-prone)
        is_high_risk = tbr_54 > 1.0 or tbr_70 > 8.0
        if is_high_risk:
            high_risk_tir_ok = tir >= ADA_TIR_HIGH_RISK
        else:
            high_risk_tir_ok = True

        # Pipeline assessment
        assessment = compute_full_assessment(glucose, bolus, carbs_arr, n)
        pipeline_grade = assessment['grade']
        pipeline_score = assessment['score']

        # Guideline alignment
        discrepancies = []

        # Check if pipeline grade aligns with ADA status
        grade_map = {'A': 'meets_all_targets', 'B': 'partially_meets',
                     'C': 'below_targets', 'D': 'significantly_below'}
        expected_ada = grade_map.get(pipeline_grade, 'below_targets')

        if expected_ada != ada_overall:
            discrepancies.append(
                f'Grade {pipeline_grade} maps to {expected_ada} '
                f'but ADA status is {ada_overall}')

        if not meets_ada_tbr and 'hypo' not in str(assessment.get('flags', {})):
            discrepancies.append(
                'ADA flags excessive TBR but pipeline does not highlight hypo')

        if meets_ada_tir and pipeline_grade in ('C', 'D'):
            discrepancies.append(
                f'Meets ADA TIR target ({tir:.1f}%) but pipeline '
                f'grade is {pipeline_grade}')

        if not meets_ada_tir and pipeline_grade == 'A':
            discrepancies.append(
                f'Below ADA TIR target ({tir:.1f}%) but pipeline '
                f'grade is A')

        guideline_alignment = (1.0 - len(discrepancies) * 0.25)
        guideline_alignment = max(0.0, min(1.0, guideline_alignment))
        alignment_scores.append(guideline_alignment)

        rec = {
            'pid': pid,
            'meets_ada_tir': meets_ada_tir,
            'meets_ada_tbr': meets_ada_tbr,
            'meets_ada_cv': meets_ada_cv,
            'ada_overall': ada_overall,
            'pipeline_grade': pipeline_grade,
            'guideline_alignment': _safe_round(guideline_alignment, 2),
            'discrepancy_details': discrepancies if discrepancies else ['none'],
            'tir': _safe_round(tir, 1),
            'tbr_70': _safe_round(tbr_70, 1),
            'tbr_54': _safe_round(tbr_54, 1),
            'cv': _safe_round(cv, 1),
            'is_high_risk': is_high_risk,
            'high_risk_tir_ok': high_risk_tir_ok,
        }
        results['per_patient'].append(rec)
        if args.detail:
            disc_str = '; '.join(discrepancies) if discrepancies else 'aligned'
            print(f"  {pid}: ADA={ada_overall} "
                  f"pipeline={pipeline_grade} "
                  f"TIR={tir:.1f}% TBR={tbr_70:.1f}% CV={cv:.1f}% "
                  f"alignment={guideline_alignment:.2f} "
                  f"disc=[{disc_str}]")

    results['n_patients'] = len(pids)
    results['mean_alignment'] = _safe_round(
        float(np.mean(alignment_scores)) if alignment_scores else 0.0, 3)
    results['ada_compliance_summary'] = {
        'meets_all': sum(1 for r in results['per_patient']
                         if r['ada_overall'] == 'meets_all_targets'),
        'partially_meets': sum(1 for r in results['per_patient']
                               if r['ada_overall'] == 'partially_meets'),
        'below': sum(1 for r in results['per_patient']
                     if r['ada_overall'] == 'below_targets'),
        'significantly_below': sum(1 for r in results['per_patient']
                                   if r['ada_overall'] == 'significantly_below'),
    }
    results['discrepancy_count'] = sum(
        len(r['discrepancy_details'])
        for r in results['per_patient']
        if r['discrepancy_details'] != ['none'])
    return results


# ===================================================================
# Main entry point
# ===================================================================

def main():
    parser = argparse.ArgumentParser(
        description='EXP-1481 to EXP-1490: Clinical Translation '
                    '& Actionability')
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
