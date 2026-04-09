#!/usr/bin/env python3
"""EXP-1551 to EXP-1558: Natural Experiment Census & Characterization.

Hypothesis: Real-world CGM/AID data contains thousands of "natural
experiments" — windows that mimic controlled clinical tests (fasting
basal tests, glucose tolerance tests, correction response tests, etc.)
These occur naturally when patients eat, sleep, exercise, or simply
exist with their AID system. By detecting, classifying, and characterizing
these windows, we can extract clinically meaningful parameters without
requiring patients to perform formal tests.

Builds on:
  - EXP-1281–1510: Therapy detection campaign (230 experiments)
  - EXP-1531–1538: Fidelity assessment (RMSE/CE grading)
  - EXP-1301: Response-curve ISF (R²=0.805 exponential fit)
  - EXP-1309: UAM augmentation (R² -0.508→+0.351)
  - EXP-1313: UAM classification (82% meal, 8% hepatic, 7% artifact)
  - EXP-1333: Overnight basal titration (drift-based)
  - EXP-1361: Meal peak detection & template analysis (3,074 meals)

Experiments:
  EXP-1551: Natural Experiment Census
             Single-pass detection of 8 window types per patient.
             Yield: count, duration, quality per type per patient.
  EXP-1552: Distribution Characterization
             Time-of-day, day-of-week, duration distributions per type.
  EXP-1553: Window Quality Grading
             Cleanliness score (confounders, CGM coverage, signal strength).
  EXP-1554: Cross-Experiment Correlations
             Does ISF from corrections predict meal overcorrection?
             Does overnight drift correlate with daytime UAM frequency?
  EXP-1555: Minimum Data Requirements
             Bootstrap subsampling: days needed per type for stable estimates.
  EXP-1556: Patient Archetype by Experiment Yield
             Cluster patients by their natural experiment profile.
  EXP-1557: Template Extraction
             Canonical glucose trajectory per window type (population + per-patient).
  EXP-1558: Production Integration Summary
             Consolidate into NaturalExperimentDetector specification.

Usage:
    python tools/cgmencode/exp_clinical_1551.py --exp 0        # run all
    python tools/cgmencode/exp_clinical_1551.py --exp 1551     # single
    python tools/cgmencode/exp_clinical_1551.py --max-patients 3 --exp 1551  # quick test
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
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from cgmencode.exp_metabolic_flux import load_patients as _load_patients
from cgmencode.exp_metabolic_flux import _extract_isf_scalar
from cgmencode.exp_metabolic_441 import compute_supply_demand

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PATIENTS_DIR = os.path.join(os.path.dirname(__file__), '..', '..',
                            'externals', 'ns-data', 'patients')
RESULTS_DIR = (Path(__file__).resolve().parent.parent.parent
               / 'externals' / 'experiments')
VIZ_DIR = (Path(__file__).resolve().parent.parent.parent
           / 'visualizations' / 'natural-experiments')

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
STEPS_PER_HOUR = 12          # 5-min intervals
STEPS_PER_DAY = 288
STEP_MINUTES = 5

# Window type thresholds (calibrated from prior experiments)
FASTING_MIN_STEPS = 36       # 3 hours with no carbs/bolus
FASTING_CARB_THRESH = 1.0    # g — effectively zero
FASTING_BOLUS_THRESH = 0.1   # U — effectively zero (allow micro-SMB)
OVERNIGHT_START_HOUR = 0     # midnight
OVERNIGHT_END_HOUR = 6       # 6 AM
DAWN_START_HOUR = 4          # dawn window start
DAWN_END_HOUR = 8            # dawn window end
CORRECTION_MIN_BOLUS = 0.5   # U — minimum bolus to count as correction
CORRECTION_CARB_WINDOW = 6   # steps (30 min) — no carbs nearby
CORRECTION_BG_THRESH = 150   # mg/dL — must start from elevated BG
CORRECTION_OBSERVE_STEPS = 96  # 8 hours observation after correction
MEAL_CARB_THRESH = 5.0       # g — minimum carbs to be a meal
MEAL_OBSERVE_STEPS = 36      # 3 hours post-meal observation
UAM_RESIDUAL_THRESH = 1.0    # mg/dL per 5-min (from EXP-1320 universal)
UAM_MIN_DURATION = 3         # steps (15 min minimum UAM run)
EXERCISE_DEMAND_P90_THRESH = 2.0  # supply-demand residual threshold
EXERCISE_BG_DROP_RATE = -1.5  # mg/dL per 5-min sustained drop
STABLE_MAX_GLUCOSE_CV = 5.0  # % — very flat glucose
STABLE_MIN_DURATION = 24     # 2 hours minimum stable period

EXPERIMENTS = {}


def register(exp_id, title):
    """Register experiment function."""
    def decorator(fn):
        EXPERIMENTS[exp_id] = (title, fn)
        return fn
    return decorator


# ---------------------------------------------------------------------------
# Data classes for natural experiment windows
# ---------------------------------------------------------------------------

@dataclass
class NaturalExperiment:
    """A single detected natural experiment window."""
    exp_type: str           # fasting|meal|correction|uam|dawn|exercise|aid_response|stable
    patient: str
    start_idx: int
    end_idx: int
    start_time: str         # ISO timestamp
    end_time: str
    duration_minutes: int
    hour_of_day: float      # fractional hour at start
    day_of_week: int        # 0=Monday
    quality: float          # 0-1 cleanliness score
    # Type-specific measurements
    measurements: Dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def load_patients(max_patients=11, patients_dir=None):
    return _load_patients(patients_dir or PATIENTS_DIR, max_patients=max_patients)


def _bg(df):
    col = 'glucose' if 'glucose' in df.columns else 'sgv'
    return np.asarray(df[col], dtype=np.float64)


def _safe_nanmean(arr):
    valid = arr[~np.isnan(arr)]
    return float(np.mean(valid)) if len(valid) > 0 else float('nan')


def _safe_nanstd(arr):
    valid = arr[~np.isnan(arr)]
    return float(np.std(valid)) if len(valid) > 1 else float('nan')


def _cgm_coverage(bg_segment):
    return float(np.sum(~np.isnan(bg_segment))) / max(len(bg_segment), 1)


def _linear_drift(bg_segment):
    """Compute drift in mg/dL per hour via linear regression."""
    valid = ~np.isnan(bg_segment)
    if np.sum(valid) < 6:
        return float('nan')
    y = bg_segment[valid]
    x = np.arange(len(bg_segment))[valid] * (STEP_MINUTES / 60.0)  # hours
    if len(x) < 2:
        return float('nan')
    slope = np.polyfit(x, y, 1)[0]
    return float(slope)


def _exp_decay_fit(bg_segment, bolus_size):
    """Fit BG(t) = BG_start - amplitude * (1 - exp(-t/tau)).
    Returns (amplitude, tau, r2, isf_estimate)."""
    valid = ~np.isnan(bg_segment)
    if np.sum(valid) < 6:
        return None
    y = bg_segment[valid]
    t = np.arange(len(bg_segment))[valid] * (STEP_MINUTES / 60.0)  # hours
    bg_start = y[0]

    best_r2, best_params = -999, None
    for tau_try in [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]:
        pred = bg_start - (bg_start - y[-1]) * (1 - np.exp(-t / tau_try))
        ss_res = np.sum((y - pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r2 = 1 - ss_res / max(ss_tot, 1e-10)
        if r2 > best_r2:
            amplitude = bg_start - y[-1]
            best_r2 = r2
            best_params = (float(amplitude), float(tau_try), float(r2),
                           float(amplitude / max(bolus_size, 0.01)))
    return best_params


# ---------------------------------------------------------------------------
# DETECTORS: Each returns a list of NaturalExperiment
# ---------------------------------------------------------------------------

def detect_fasting_windows(patient_name, df, bg, bolus, carbs):
    """Detect fasting basal test windows: extended periods with no food/bolus."""
    N = len(bg)
    experiments = []

    # Build cumulative carb/bolus activity with lookback
    carb_activity = np.zeros(N)
    bolus_activity = np.zeros(N)
    for i in range(N):
        # Sum carbs and bolus in preceding 36 steps (3h)
        lo = max(0, i - FASTING_MIN_STEPS)
        carb_activity[i] = np.nansum(carbs[lo:i + 1])
        bolus_activity[i] = np.nansum(bolus[lo:i + 1])

    # Find runs where both are below threshold
    is_fasting = ((carb_activity < FASTING_CARB_THRESH) &
                  (bolus_activity < FASTING_BOLUS_THRESH))

    # Extract contiguous fasting runs
    runs = _extract_runs(is_fasting, min_length=FASTING_MIN_STEPS)

    for start, end in runs:
        seg = bg[start:end]
        coverage = _cgm_coverage(seg)
        if coverage < 0.7:
            continue
        drift = _linear_drift(seg)
        duration = (end - start) * STEP_MINUTES

        # Quality: longer + better coverage + less drift = higher quality
        q_duration = min(duration / 360.0, 1.0)  # max quality at 6h
        q_coverage = coverage
        q_stability = max(0, 1.0 - abs(drift) / 20.0) if not math.isnan(drift) else 0
        quality = 0.4 * q_duration + 0.3 * q_coverage + 0.3 * q_stability

        hour = _hour_of_day(df, start)
        dow = _day_of_week(df, start)

        experiments.append(NaturalExperiment(
            exp_type='fasting',
            patient=patient_name,
            start_idx=start, end_idx=end,
            start_time=str(df.index[start]),
            end_time=str(df.index[min(end, N - 1)]),
            duration_minutes=duration,
            hour_of_day=hour,
            day_of_week=dow,
            quality=round(quality, 3),
            measurements={
                'drift_mg_dl_per_hour': round(drift, 3) if not math.isnan(drift) else None,
                'mean_bg': round(_safe_nanmean(seg), 1),
                'bg_cv': round(100 * _safe_nanstd(seg) / max(_safe_nanmean(seg), 1), 2),
                'cgm_coverage': round(coverage, 3),
            }
        ))
    return experiments


def detect_overnight_windows(patient_name, df, bg, bolus, carbs):
    """Detect overnight basal test windows (midnight to 6 AM, fasting)."""
    N = len(bg)
    experiments = []
    hours = _hours_array(df)

    # Find overnight periods
    is_overnight = (hours >= OVERNIGHT_START_HOUR) & (hours < OVERNIGHT_END_HOUR)
    runs = _extract_runs(is_overnight, min_length=STEPS_PER_HOUR)  # at least 1h

    for start, end in runs:
        seg = bg[start:end]
        coverage = _cgm_coverage(seg)
        if coverage < 0.7:
            continue

        # Check if truly fasting during this window
        carb_sum = np.nansum(carbs[start:end])
        bolus_sum = np.nansum(bolus[start:end])
        is_fasting = carb_sum < FASTING_CARB_THRESH and bolus_sum < FASTING_BOLUS_THRESH

        drift = _linear_drift(seg)
        duration = (end - start) * STEP_MINUTES

        quality_fasting = 1.0 if is_fasting else 0.3
        quality_coverage = coverage
        quality_duration = min(duration / 300, 1.0)
        quality = 0.4 * quality_fasting + 0.3 * quality_coverage + 0.3 * quality_duration

        hour = _hour_of_day(df, start)
        dow = _day_of_week(df, start)

        experiments.append(NaturalExperiment(
            exp_type='overnight',
            patient=patient_name,
            start_idx=start, end_idx=end,
            start_time=str(df.index[start]),
            end_time=str(df.index[min(end, N - 1)]),
            duration_minutes=duration,
            hour_of_day=hour,
            day_of_week=dow,
            quality=round(quality, 3),
            measurements={
                'drift_mg_dl_per_hour': round(drift, 3) if not math.isnan(drift) else None,
                'is_fasting': is_fasting,
                'carbs_in_window': round(float(carb_sum), 1),
                'bolus_in_window': round(float(bolus_sum), 2),
                'mean_bg': round(_safe_nanmean(seg), 1),
                'min_bg': round(float(np.nanmin(seg)), 1) if np.any(~np.isnan(seg)) else None,
                'max_bg': round(float(np.nanmax(seg)), 1) if np.any(~np.isnan(seg)) else None,
                'cgm_coverage': round(coverage, 3),
            }
        ))
    return experiments


def detect_meal_windows(patient_name, df, bg, bolus, carbs, sd,
                        min_carbs=None, cluster_gap=None):
    """Detect glucose tolerance test windows: meals with post-prandial observation.

    Args:
        min_carbs: Minimum carb entry to trigger a meal (default: MEAL_CARB_THRESH=5g).
        cluster_gap: Steps within which carb entries merge into one meal
                     (default: 6 steps = 30 min). Use 18 for 90-min hysteresis.
    """
    N = len(bg)
    experiments = []
    _min_carbs = min_carbs if min_carbs is not None else MEAL_CARB_THRESH
    _cluster_gap = cluster_gap if cluster_gap is not None else 6

    # Find carb events
    carb_events = np.where(carbs >= _min_carbs)[0]
    if len(carb_events) == 0:
        return experiments

    # Cluster events within specified gap
    clusters = _cluster_events(carb_events, gap=_cluster_gap)

    for cluster in clusters:
        meal_idx = cluster[0]  # first event in cluster
        total_carbs = float(np.nansum(carbs[cluster]))
        end_idx = min(meal_idx + MEAL_OBSERVE_STEPS, N)

        if end_idx - meal_idx < 12:  # need at least 1h observation
            continue

        # Pre-meal baseline (30 min before)
        pre_start = max(0, meal_idx - 6)
        pre_bg = _safe_nanmean(bg[pre_start:meal_idx])

        # Post-meal trajectory
        post_bg = bg[meal_idx:end_idx]
        coverage = _cgm_coverage(post_bg)
        if coverage < 0.6:
            continue

        # Peak detection
        valid_post = post_bg.copy()
        valid_post[np.isnan(valid_post)] = pre_bg  # fill for peak detection
        peak_idx_rel = np.argmax(valid_post)
        peak_bg = float(valid_post[peak_idx_rel])
        excursion = peak_bg - pre_bg if not math.isnan(pre_bg) else float('nan')
        peak_time_min = peak_idx_rel * STEP_MINUTES

        # Recovery: BG at 2h and 3h post-meal
        bg_2h = float(valid_post[min(24, len(valid_post) - 1)])
        bg_3h = float(valid_post[min(36, len(valid_post) - 1)]) if len(valid_post) > 36 else None

        # Bolus within ±15 min of meal
        bolus_window = bolus[max(0, meal_idx - 3):min(N, meal_idx + 3)]
        meal_bolus = float(np.nansum(bolus_window))
        is_announced = meal_bolus > 0.1

        # Quality
        q_coverage = coverage
        q_isolated = 1.0  # reduce if another meal within 2h
        for c2 in clusters:
            if c2[0] != meal_idx and abs(c2[0] - meal_idx) < 24:
                q_isolated = 0.5
                break
        quality = 0.4 * q_coverage + 0.3 * q_isolated + 0.3 * (1.0 if is_announced else 0.6)

        hour = _hour_of_day(df, meal_idx)
        dow = _day_of_week(df, meal_idx)
        meal_window = _classify_meal_time(hour)

        experiments.append(NaturalExperiment(
            exp_type='meal',
            patient=patient_name,
            start_idx=meal_idx, end_idx=end_idx,
            start_time=str(df.index[meal_idx]),
            end_time=str(df.index[min(end_idx, N - 1)]),
            duration_minutes=(end_idx - meal_idx) * STEP_MINUTES,
            hour_of_day=hour,
            day_of_week=dow,
            quality=round(quality, 3),
            measurements={
                'carbs_g': round(total_carbs, 1),
                'bolus_u': round(meal_bolus, 2),
                'is_announced': is_announced,
                'meal_window': meal_window,
                'pre_meal_bg': round(pre_bg, 1) if not math.isnan(pre_bg) else None,
                'peak_bg': round(peak_bg, 1),
                'excursion_mg_dl': round(excursion, 1) if not math.isnan(excursion) else None,
                'peak_time_min': peak_time_min,
                'bg_2h': round(bg_2h, 1),
                'bg_3h': round(bg_3h, 1) if bg_3h else None,
                'cgm_coverage': round(coverage, 3),
            }
        ))
    return experiments


def detect_correction_windows(patient_name, df, bg, bolus, carbs):
    """Detect correction bolus windows: isolated boluses from elevated BG."""
    N = len(bg)
    experiments = []

    bolus_events = np.where(bolus >= CORRECTION_MIN_BOLUS)[0]

    for bi in bolus_events:
        # Check no carbs within ±30 min
        carb_window_lo = max(0, bi - CORRECTION_CARB_WINDOW)
        carb_window_hi = min(N, bi + CORRECTION_CARB_WINDOW)
        if np.nansum(carbs[carb_window_lo:carb_window_hi]) > FASTING_CARB_THRESH:
            continue

        # Check starting BG is elevated
        start_bg = bg[bi] if not np.isnan(bg[bi]) else _safe_nanmean(bg[max(0, bi - 3):bi + 1])
        if math.isnan(start_bg) or start_bg < CORRECTION_BG_THRESH:
            continue

        # Observation window
        obs_end = min(bi + CORRECTION_OBSERVE_STEPS, N)
        seg = bg[bi:obs_end]
        coverage = _cgm_coverage(seg)
        if coverage < 0.6:
            continue

        bolus_size = float(bolus[bi])

        # Try exponential decay fit
        fit_result = _exp_decay_fit(seg, bolus_size)
        amplitude, tau, r2, isf_est = fit_result if fit_result else (None, None, None, None)

        # Simple ISF: total BG drop / bolus
        valid_seg = seg[~np.isnan(seg)]
        if len(valid_seg) > 6:
            nadir = float(np.min(valid_seg))
            simple_isf = (start_bg - nadir) / bolus_size
        else:
            nadir, simple_isf = None, None

        # Quality: isolated (no other boluses nearby), good fit, adequate coverage
        other_bolus = np.nansum(bolus[min(N, bi + 1):min(N, bi + 36)])  # 3h after
        q_isolated = 1.0 if other_bolus < 0.1 else 0.4
        q_coverage = coverage
        q_fit = min(max(r2, 0), 1.0) if r2 is not None else 0.3
        quality = 0.3 * q_isolated + 0.3 * q_coverage + 0.4 * q_fit

        hour = _hour_of_day(df, bi)
        dow = _day_of_week(df, bi)

        experiments.append(NaturalExperiment(
            exp_type='correction',
            patient=patient_name,
            start_idx=bi, end_idx=obs_end,
            start_time=str(df.index[bi]),
            end_time=str(df.index[min(obs_end, N - 1)]),
            duration_minutes=(obs_end - bi) * STEP_MINUTES,
            hour_of_day=hour,
            day_of_week=dow,
            quality=round(quality, 3),
            measurements={
                'bolus_u': round(bolus_size, 2),
                'start_bg': round(start_bg, 1),
                'nadir_bg': round(nadir, 1) if nadir else None,
                'simple_isf': round(simple_isf, 1) if simple_isf else None,
                'curve_amplitude': round(amplitude, 1) if amplitude else None,
                'curve_tau_hours': round(tau, 2) if tau else None,
                'curve_r2': round(r2, 3) if r2 else None,
                'curve_isf': round(isf_est, 1) if isf_est else None,
                'cgm_coverage': round(coverage, 3),
            }
        ))
    return experiments


def detect_uam_windows(patient_name, df, bg, carbs, sd):
    """Detect unannounced meal (UAM) windows from physics residual bursts."""
    N = min(len(bg), len(sd['net']))
    experiments = []

    actual_dbg = np.zeros(N)
    actual_dbg[1:] = np.diff(bg[:N])
    actual_dbg[np.isnan(actual_dbg)] = 0

    net_flux = sd['net'][:N]
    residual = actual_dbg - net_flux

    # UAM = positive residual (glucose rising faster than predicted) with no carbs
    # Build carb-free mask: no carbs within ±1h
    carb_free = np.ones(N, dtype=bool)
    carb_indices = np.where(carbs[:N] > FASTING_CARB_THRESH)[0]
    for ci in carb_indices:
        lo = max(0, ci - STEPS_PER_HOUR)
        hi = min(N, ci + STEPS_PER_HOUR)
        carb_free[lo:hi] = False

    is_uam = (residual > UAM_RESIDUAL_THRESH) & carb_free
    runs = _extract_runs(is_uam, min_length=UAM_MIN_DURATION)

    for start, end in runs:
        seg_bg = bg[start:end]
        seg_residual = residual[start:end]
        coverage = _cgm_coverage(seg_bg)
        if coverage < 0.5:
            continue

        duration = (end - start) * STEP_MINUTES
        peak_residual = float(np.max(seg_residual))
        mean_residual = float(np.mean(seg_residual))
        total_residual = float(np.sum(seg_residual))
        bg_rise = float(np.nanmax(seg_bg) - np.nanmin(seg_bg)) if np.any(~np.isnan(seg_bg)) else 0

        # Classify UAM subtype (from EXP-1313 categories)
        hour = _hour_of_day(df, start)
        if 4 <= hour < 8 and mean_residual < 3.0:
            subtype = 'hepatic'  # dawn/hepatic glucose output
        elif peak_residual > 5.0 and duration < 30:
            subtype = 'artifact'  # sensor spike
        elif mean_residual < 1.5 and duration > 60:
            subtype = 'slow_absorption'  # fat/protein tail
        else:
            subtype = 'meal'  # unannounced meal (most common)

        # Quality
        q_duration = min(duration / 120.0, 1.0)
        q_signal = min(mean_residual / 3.0, 1.0)
        q_coverage = coverage
        quality = 0.3 * q_duration + 0.4 * q_signal + 0.3 * q_coverage

        dow = _day_of_week(df, start)

        experiments.append(NaturalExperiment(
            exp_type='uam',
            patient=patient_name,
            start_idx=start, end_idx=end,
            start_time=str(df.index[start]),
            end_time=str(df.index[min(end, N - 1)]),
            duration_minutes=duration,
            hour_of_day=hour,
            day_of_week=dow,
            quality=round(quality, 3),
            measurements={
                'subtype': subtype,
                'peak_residual': round(peak_residual, 2),
                'mean_residual': round(mean_residual, 2),
                'total_residual_integral': round(total_residual, 1),
                'bg_rise_mg_dl': round(bg_rise, 1),
                'duration_min': duration,
                'cgm_coverage': round(coverage, 3),
            }
        ))
    return experiments


def detect_dawn_windows(patient_name, df, bg, carbs, bolus):
    """Detect dawn phenomenon windows (4-8 AM glucose rise during fasting)."""
    N = len(bg)
    experiments = []
    hours = _hours_array(df)

    # Find pre-dawn (0-4 AM) and dawn (4-8 AM) segments per night
    dates = _unique_dates(df)

    for date in dates:
        # Pre-dawn: 0-4 AM
        pre_mask = (hours >= 0) & (hours < 4) & (_dates_array(df) == date)
        pre_indices = np.where(pre_mask)[0]
        # Dawn: 4-8 AM
        dawn_mask = (hours >= 4) & (hours < 8) & (_dates_array(df) == date)
        dawn_indices = np.where(dawn_mask)[0]

        if len(pre_indices) < 12 or len(dawn_indices) < 12:
            continue

        # Check fasting
        carb_sum = np.nansum(carbs[pre_indices[0]:dawn_indices[-1] + 1])
        bolus_sum = np.nansum(bolus[pre_indices[0]:dawn_indices[-1] + 1])
        is_fasting = carb_sum < FASTING_CARB_THRESH and bolus_sum < FASTING_BOLUS_THRESH

        pre_bg = bg[pre_indices]
        dawn_bg = bg[dawn_indices]

        pre_drift = _linear_drift(pre_bg)
        dawn_drift = _linear_drift(dawn_bg)

        if math.isnan(pre_drift) or math.isnan(dawn_drift):
            continue

        dawn_effect = dawn_drift - pre_drift  # positive = dawn rise
        dawn_detected = dawn_effect > 3.0  # >3 mg/dL/h acceleration

        start = pre_indices[0]
        end = dawn_indices[-1]
        seg = bg[start:end + 1]
        coverage = _cgm_coverage(seg)

        quality_fasting = 1.0 if is_fasting else 0.3
        quality_coverage = coverage
        quality = 0.5 * quality_fasting + 0.5 * quality_coverage

        experiments.append(NaturalExperiment(
            exp_type='dawn',
            patient=patient_name,
            start_idx=start, end_idx=end,
            start_time=str(df.index[start]),
            end_time=str(df.index[min(end, N - 1)]),
            duration_minutes=(end - start) * STEP_MINUTES,
            hour_of_day=_hour_of_day(df, start),
            day_of_week=_day_of_week(df, start),
            quality=round(quality, 3),
            measurements={
                'is_fasting': is_fasting,
                'pre_dawn_drift': round(pre_drift, 2),
                'dawn_drift': round(dawn_drift, 2),
                'dawn_effect_mg_dl_hr': round(dawn_effect, 2),
                'dawn_detected': dawn_detected,
                'pre_dawn_mean_bg': round(_safe_nanmean(pre_bg), 1),
                'dawn_mean_bg': round(_safe_nanmean(dawn_bg), 1),
                'cgm_coverage': round(coverage, 3),
            }
        ))
    return experiments


def detect_exercise_windows(patient_name, df, bg, bolus, carbs, sd):
    """Detect exercise windows from sustained BG drops + negative residuals."""
    N = min(len(bg), len(sd['net']))
    experiments = []

    actual_dbg = np.zeros(N)
    actual_dbg[1:] = np.diff(bg[:N])
    actual_dbg[np.isnan(actual_dbg)] = 0

    net_flux = sd['net'][:N]
    residual = actual_dbg - net_flux

    # Exercise signature: negative residual (BG falling faster than predicted)
    # with no recent bolus (rules out correction response)
    bolus_free = np.ones(N, dtype=bool)
    bolus_indices = np.where(bolus[:N] > CORRECTION_MIN_BOLUS)[0]
    for bi in bolus_indices:
        lo = max(0, bi - STEPS_PER_HOUR * 2)  # 2h before
        hi = min(N, bi + STEPS_PER_HOUR)       # 1h after
        bolus_free[lo:hi] = False

    is_exercise = (residual < -EXERCISE_DEMAND_P90_THRESH) & bolus_free
    runs = _extract_runs(is_exercise, min_length=6)  # at least 30 min

    for start, end in runs:
        seg_bg = bg[start:end]
        seg_residual = residual[start:end]
        coverage = _cgm_coverage(seg_bg)
        if coverage < 0.5:
            continue

        duration = (end - start) * STEP_MINUTES
        mean_residual = float(np.mean(seg_residual))
        bg_drop = float(np.nanmax(seg_bg) - np.nanmin(seg_bg)) if np.any(~np.isnan(seg_bg)) else 0
        start_bg_val = bg[start] if not np.isnan(bg[start]) else _safe_nanmean(seg_bg)

        # Post-exercise sensitivity: check 2h after for continued low demand
        post_start = end
        post_end = min(N, end + 24)  # 2h post
        if post_end > post_start:
            post_bg = bg[post_start:post_end]
            post_drift = _linear_drift(post_bg)
        else:
            post_drift = float('nan')

        quality_duration = min(duration / 90.0, 1.0)
        quality_signal = min(abs(mean_residual) / 4.0, 1.0)
        quality_coverage = coverage
        quality = 0.3 * quality_duration + 0.4 * quality_signal + 0.3 * quality_coverage

        hour = _hour_of_day(df, start)
        dow = _day_of_week(df, start)

        experiments.append(NaturalExperiment(
            exp_type='exercise',
            patient=patient_name,
            start_idx=start, end_idx=end,
            start_time=str(df.index[start]),
            end_time=str(df.index[min(end, N - 1)]),
            duration_minutes=duration,
            hour_of_day=hour,
            day_of_week=dow,
            quality=round(quality, 3),
            measurements={
                'mean_residual': round(mean_residual, 2),
                'bg_drop_mg_dl': round(bg_drop, 1),
                'start_bg': round(start_bg_val, 1) if not math.isnan(start_bg_val) else None,
                'post_exercise_drift': round(post_drift, 2) if not math.isnan(post_drift) else None,
                'cgm_coverage': round(coverage, 3),
            }
        ))
    return experiments


def detect_aid_response_windows(patient_name, df, bg):
    """Detect AID algorithm response windows from temp basal deviations."""
    N = len(bg)
    experiments = []

    if 'net_basal' not in df.columns:
        return experiments

    net_basal = np.nan_to_num(df['net_basal'].values.astype(np.float64), nan=0.0)[:N]

    # High temp basal (loop increasing delivery) — aggressive correction
    high_temp = net_basal > 0.3  # >0.3 U/hr above scheduled
    runs = _extract_runs(high_temp, min_length=6)  # at least 30 min
    for start, end in runs:
        seg_bg = bg[start:end]
        coverage = _cgm_coverage(seg_bg)
        if coverage < 0.5:
            continue

        experiments.append(_make_aid_experiment(
            patient_name, df, bg, net_basal, start, end, 'high_temp', coverage))

    # Suspension or low temp (loop reducing delivery) — prevent hypo
    low_temp = net_basal < -0.2  # >0.2 U/hr below scheduled
    runs = _extract_runs(low_temp, min_length=6)
    for start, end in runs:
        seg_bg = bg[start:end]
        coverage = _cgm_coverage(seg_bg)
        if coverage < 0.5:
            continue

        experiments.append(_make_aid_experiment(
            patient_name, df, bg, net_basal, start, end, 'low_temp', coverage))

    return experiments


def _make_aid_experiment(patient_name, df, bg, net_basal, start, end, subtype, coverage):
    N = len(bg)
    seg_bg = bg[start:end]
    seg_nb = net_basal[start:end]
    duration = (end - start) * STEP_MINUTES

    quality = 0.5 * coverage + 0.5 * min(duration / 120, 1.0)

    return NaturalExperiment(
        exp_type='aid_response',
        patient=patient_name,
        start_idx=start, end_idx=end,
        start_time=str(df.index[start]),
        end_time=str(df.index[min(end, N - 1)]),
        duration_minutes=duration,
        hour_of_day=_hour_of_day(df, start),
        day_of_week=_day_of_week(df, start),
        quality=round(quality, 3),
        measurements={
            'subtype': subtype,
            'mean_net_basal': round(float(np.mean(seg_nb)), 3),
            'max_net_basal': round(float(np.max(seg_nb)), 3),
            'min_net_basal': round(float(np.min(seg_nb)), 3),
            'mean_bg': round(_safe_nanmean(seg_bg), 1),
            'bg_change': round(float(np.nanmean(seg_bg[-6:]) - np.nanmean(seg_bg[:6])), 1)
                         if len(seg_bg) >= 12 else None,
            'cgm_coverage': round(coverage, 3),
        }
    )


def detect_stable_windows(patient_name, df, bg, bolus, carbs):
    """Detect stable/flat glucose windows (reference periods)."""
    N = len(bg)
    experiments = []

    # Sliding window: 2h (24 steps)
    for start in range(0, N - STABLE_MIN_DURATION, STEPS_PER_HOUR):
        end = start + STABLE_MIN_DURATION
        seg = bg[start:end]
        coverage = _cgm_coverage(seg)
        if coverage < 0.8:
            continue

        valid = seg[~np.isnan(seg)]
        if len(valid) < 12:
            continue

        mean_bg = float(np.mean(valid))
        std_bg = float(np.std(valid))
        cv = 100 * std_bg / max(mean_bg, 1)

        if cv > STABLE_MAX_GLUCOSE_CV:
            continue

        # Check truly quiet: minimal carbs and bolus
        carb_sum = float(np.nansum(carbs[start:end]))
        bolus_sum = float(np.nansum(bolus[start:end]))

        quality_cv = max(0, 1.0 - cv / STABLE_MAX_GLUCOSE_CV)
        quality_coverage = coverage
        quality_quiet = 1.0 if (carb_sum < 1 and bolus_sum < 0.1) else 0.5
        quality = 0.4 * quality_cv + 0.3 * quality_coverage + 0.3 * quality_quiet

        hour = _hour_of_day(df, start)
        dow = _day_of_week(df, start)

        experiments.append(NaturalExperiment(
            exp_type='stable',
            patient=patient_name,
            start_idx=start, end_idx=end,
            start_time=str(df.index[start]),
            end_time=str(df.index[min(end, N - 1)]),
            duration_minutes=STABLE_MIN_DURATION * STEP_MINUTES,
            hour_of_day=hour,
            day_of_week=dow,
            quality=round(quality, 3),
            measurements={
                'mean_bg': round(mean_bg, 1),
                'std_bg': round(std_bg, 2),
                'cv_pct': round(cv, 2),
                'carbs_in_window': round(carb_sum, 1),
                'bolus_in_window': round(bolus_sum, 2),
                'cgm_coverage': round(coverage, 3),
            }
        ))

    return experiments


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def _extract_runs(mask, min_length=1):
    """Extract contiguous True runs from a boolean mask."""
    runs = []
    in_run = False
    start = 0
    for i in range(len(mask)):
        if mask[i] and not in_run:
            start = i
            in_run = True
        elif not mask[i] and in_run:
            if i - start >= min_length:
                runs.append((start, i))
            in_run = False
    if in_run and len(mask) - start >= min_length:
        runs.append((start, len(mask)))
    return runs


def _cluster_events(indices, gap=6):
    """Cluster event indices within `gap` steps of each other."""
    if len(indices) == 0:
        return []
    clusters = [[indices[0]]]
    for idx in indices[1:]:
        if idx - clusters[-1][-1] <= gap:
            clusters[-1].append(idx)
        else:
            clusters.append([idx])
    return clusters


def _hours_array(df):
    """Get hour-of-day array respecting patient timezone."""
    tz = df.attrs.get('patient_tz', 'UTC')
    try:
        local = df.index.tz_convert(tz)
    except Exception:
        local = df.index
    return local.hour + local.minute / 60.0


def _dates_array(df):
    """Get date array."""
    tz = df.attrs.get('patient_tz', 'UTC')
    try:
        local = df.index.tz_convert(tz)
    except Exception:
        local = df.index
    return local.date


def _unique_dates(df):
    """Get unique dates in patient-local time."""
    dates = _dates_array(df)
    return sorted(set(dates))


def _hour_of_day(df, idx):
    tz = df.attrs.get('patient_tz', 'UTC')
    try:
        t = df.index[idx].tz_convert(tz)
    except Exception:
        t = df.index[idx]
    return round(t.hour + t.minute / 60.0, 2)


def _day_of_week(df, idx):
    tz = df.attrs.get('patient_tz', 'UTC')
    try:
        t = df.index[idx].tz_convert(tz)
    except Exception:
        t = df.index[idx]
    return t.weekday()


def _classify_meal_time(hour):
    if 5 <= hour < 10:
        return 'breakfast'
    elif 10 <= hour < 14:
        return 'lunch'
    elif 17 <= hour < 21:
        return 'dinner'
    else:
        return 'snack'


# ---------------------------------------------------------------------------
# EXPERIMENTS
# ---------------------------------------------------------------------------

@register(1551, 'Natural Experiment Census')
def exp_1551_census(patients):
    """Single-pass detection of all 8 window types per patient."""
    all_experiments = []
    per_patient = {}

    for pat in patients:
        name = pat['name']
        df = pat['df']
        bg = _bg(df)
        bolus = np.nan_to_num(df['bolus'].values.astype(np.float64), nan=0.0)
        carbs_arr = np.nan_to_num(df['carbs'].values.astype(np.float64), nan=0.0)
        sd = compute_supply_demand(df, pat['pk'])

        print(f"\n  Patient {name} ({len(df)} steps, {len(df)/STEPS_PER_DAY:.0f} days):")

        # Run all 8 detectors
        detectors = [
            ('fasting',      lambda: detect_fasting_windows(name, df, bg, bolus, carbs_arr)),
            ('overnight',    lambda: detect_overnight_windows(name, df, bg, bolus, carbs_arr)),
            ('meal',         lambda: detect_meal_windows(name, df, bg, bolus, carbs_arr, sd)),
            ('correction',   lambda: detect_correction_windows(name, df, bg, bolus, carbs_arr)),
            ('uam',          lambda: detect_uam_windows(name, df, bg, carbs_arr, sd)),
            ('dawn',         lambda: detect_dawn_windows(name, df, bg, carbs_arr, bolus)),
            ('exercise',     lambda: detect_exercise_windows(name, df, bg, bolus, carbs_arr, sd)),
            ('aid_response', lambda: detect_aid_response_windows(name, df, bg)),
            ('stable',       lambda: detect_stable_windows(name, df, bg, bolus, carbs_arr)),
        ]

        patient_exps = {}
        for dtype, detector in detectors:
            t0 = time.time()
            found = detector()
            elapsed = time.time() - t0
            patient_exps[dtype] = found
            all_experiments.extend(found)
            n_days = len(df) / STEPS_PER_DAY
            rate = len(found) / max(n_days, 1)
            print(f"    {dtype:15s}: {len(found):5d} windows  ({rate:.1f}/day)  [{elapsed:.1f}s]")

        per_patient[name] = {
            dtype: {
                'count': len(exps),
                'per_day': round(len(exps) / max(len(df) / STEPS_PER_DAY, 1), 2),
                'mean_quality': round(np.mean([e.quality for e in exps]), 3) if exps else None,
                'mean_duration_min': round(np.mean([e.duration_minutes for e in exps]), 1) if exps else None,
            }
            for dtype, exps in patient_exps.items()
        }

    # Population summary
    type_counts = defaultdict(int)
    type_qualities = defaultdict(list)
    type_durations = defaultdict(list)
    for exp in all_experiments:
        type_counts[exp.exp_type] += 1
        type_qualities[exp.exp_type].append(exp.quality)
        type_durations[exp.exp_type].append(exp.duration_minutes)

    population = {}
    for etype in sorted(type_counts.keys()):
        population[etype] = {
            'total_count': type_counts[etype],
            'mean_quality': round(np.mean(type_qualities[etype]), 3),
            'std_quality': round(np.std(type_qualities[etype]), 3),
            'mean_duration_min': round(np.mean(type_durations[etype]), 1),
            'median_duration_min': round(float(np.median(type_durations[etype])), 1),
        }

    return {
        'experiment': 'EXP-1551',
        'title': 'Natural Experiment Census',
        'total_experiments_detected': len(all_experiments),
        'n_patients': len(patients),
        'population_summary': population,
        'per_patient': per_patient,
        # Store serializable experiment data for downstream use
        'all_experiments': [asdict(e) for e in all_experiments],
    }


@register(1552, 'Distribution Characterization')
def exp_1552_distributions(patients):
    """Time-of-day, day-of-week, and duration distributions per type."""
    # Re-run census to get experiments (or load from prior)
    census = exp_1551_census.__wrapped__(patients) if hasattr(exp_1551_census, '__wrapped__') else None

    # Fallback: run detectors directly
    all_experiments = _run_all_detectors(patients)

    # Characterize distributions
    distributions = {}
    for etype in ['fasting', 'overnight', 'meal', 'correction', 'uam',
                  'dawn', 'exercise', 'aid_response', 'stable']:
        subset = [e for e in all_experiments if e.exp_type == etype]
        if not subset:
            distributions[etype] = {'count': 0}
            continue

        hours = [e.hour_of_day for e in subset]
        dows = [e.day_of_week for e in subset]
        durations = [e.duration_minutes for e in subset]
        qualities = [e.quality for e in subset]

        # Hour-of-day histogram (24 bins)
        hour_hist, _ = np.histogram(hours, bins=24, range=(0, 24))

        # Day-of-week histogram
        dow_hist, _ = np.histogram(dows, bins=7, range=(0, 7))

        # Duration percentiles
        dur_arr = np.array(durations)

        distributions[etype] = {
            'count': len(subset),
            'hour_of_day_histogram': hour_hist.tolist(),
            'day_of_week_histogram': dow_hist.tolist(),
            'duration_percentiles': {
                'p10': round(float(np.percentile(dur_arr, 10)), 1),
                'p25': round(float(np.percentile(dur_arr, 25)), 1),
                'p50': round(float(np.percentile(dur_arr, 50)), 1),
                'p75': round(float(np.percentile(dur_arr, 75)), 1),
                'p90': round(float(np.percentile(dur_arr, 90)), 1),
            },
            'quality_mean': round(float(np.mean(qualities)), 3),
            'quality_std': round(float(np.std(qualities)), 3),
        }

    return {
        'experiment': 'EXP-1552',
        'title': 'Distribution Characterization',
        'distributions': distributions,
    }


@register(1553, 'Window Quality Grading')
def exp_1553_quality(patients):
    """Grade windows by cleanliness: confounders, coverage, signal strength."""
    all_experiments = _run_all_detectors(patients)

    quality_analysis = {}
    for etype in ['fasting', 'overnight', 'meal', 'correction', 'uam',
                  'dawn', 'exercise', 'aid_response', 'stable']:
        subset = [e for e in all_experiments if e.exp_type == etype]
        if not subset:
            quality_analysis[etype] = {'count': 0}
            continue

        qualities = np.array([e.quality for e in subset])

        # Grade distribution
        excellent = int(np.sum(qualities >= 0.8))
        good = int(np.sum((qualities >= 0.6) & (qualities < 0.8)))
        acceptable = int(np.sum((qualities >= 0.4) & (qualities < 0.6)))
        poor = int(np.sum(qualities < 0.4))

        quality_analysis[etype] = {
            'count': len(subset),
            'grades': {
                'excellent': excellent,
                'good': good,
                'acceptable': acceptable,
                'poor': poor,
            },
            'grade_pcts': {
                'excellent': round(100 * excellent / len(subset), 1),
                'good': round(100 * good / len(subset), 1),
                'acceptable': round(100 * acceptable / len(subset), 1),
                'poor': round(100 * poor / len(subset), 1),
            },
            'mean_quality': round(float(np.mean(qualities)), 3),
        }

    return {
        'experiment': 'EXP-1553',
        'title': 'Window Quality Grading',
        'quality_analysis': quality_analysis,
    }


@register(1554, 'Cross-Experiment Correlations')
def exp_1554_correlations(patients):
    """Do parameters estimated from one window type predict another?"""
    all_experiments = _run_all_detectors(patients)

    # Per-patient aggregation
    patient_metrics = {}
    for pat in patients:
        name = pat['name']
        pat_exps = [e for e in all_experiments if e.patient == name]

        # Overnight drift
        overnight = [e for e in pat_exps if e.exp_type == 'overnight'
                     and e.measurements.get('is_fasting')]
        overnight_drift = _safe_nanmean(np.array([
            e.measurements['drift_mg_dl_per_hour'] for e in overnight
            if e.measurements.get('drift_mg_dl_per_hour') is not None]))

        # Correction ISF
        corrections = [e for e in pat_exps if e.exp_type == 'correction'
                       and e.measurements.get('curve_isf') is not None]
        mean_isf = _safe_nanmean(np.array([
            e.measurements['curve_isf'] for e in corrections]))

        # Meal excursion
        meals = [e for e in pat_exps if e.exp_type == 'meal'
                 and e.measurements.get('excursion_mg_dl') is not None]
        mean_excursion = _safe_nanmean(np.array([
            e.measurements['excursion_mg_dl'] for e in meals]))

        # UAM frequency
        uam = [e for e in pat_exps if e.exp_type == 'uam']
        n_days = len(pat['df']) / STEPS_PER_DAY
        uam_per_day = len(uam) / max(n_days, 1)

        # Exercise frequency
        exercise = [e for e in pat_exps if e.exp_type == 'exercise']
        exercise_per_day = len(exercise) / max(n_days, 1)

        # Dawn effect
        dawn = [e for e in pat_exps if e.exp_type == 'dawn'
                and e.measurements.get('dawn_effect_mg_dl_hr') is not None]
        mean_dawn = _safe_nanmean(np.array([
            e.measurements['dawn_effect_mg_dl_hr'] for e in dawn]))

        patient_metrics[name] = {
            'overnight_drift': round(overnight_drift, 2) if not math.isnan(overnight_drift) else None,
            'mean_isf': round(mean_isf, 1) if not math.isnan(mean_isf) else None,
            'mean_excursion': round(mean_excursion, 1) if not math.isnan(mean_excursion) else None,
            'uam_per_day': round(uam_per_day, 1),
            'exercise_per_day': round(exercise_per_day, 1),
            'mean_dawn_effect': round(mean_dawn, 2) if not math.isnan(mean_dawn) else None,
            'n_corrections': len(corrections),
            'n_meals': len(meals),
            'n_overnight': len(overnight),
        }

    # Compute cross-correlations
    metrics_keys = ['overnight_drift', 'mean_isf', 'mean_excursion',
                    'uam_per_day', 'exercise_per_day', 'mean_dawn_effect']
    corr_matrix = {}
    for k1 in metrics_keys:
        for k2 in metrics_keys:
            v1 = [patient_metrics[p].get(k1) for p in patient_metrics]
            v2 = [patient_metrics[p].get(k2) for p in patient_metrics]
            pairs = [(a, b) for a, b in zip(v1, v2)
                     if a is not None and b is not None]
            if len(pairs) >= 3:
                a_arr = np.array([p[0] for p in pairs])
                b_arr = np.array([p[1] for p in pairs])
                if np.std(a_arr) > 0 and np.std(b_arr) > 0:
                    r = float(np.corrcoef(a_arr, b_arr)[0, 1])
                    corr_matrix[f'{k1}_vs_{k2}'] = round(r, 3)

    return {
        'experiment': 'EXP-1554',
        'title': 'Cross-Experiment Correlations',
        'patient_metrics': patient_metrics,
        'correlation_matrix': corr_matrix,
    }


@register(1555, 'Minimum Data Requirements')
def exp_1555_min_data(patients):
    """Bootstrap subsampling: how many days needed per type for stable estimates?"""
    all_experiments = _run_all_detectors(patients)

    # For each patient × type, subsample days and measure estimate stability
    stability = {}
    day_targets = [7, 14, 30, 60, 90, 120, 150, 180]

    for pat in patients:
        name = pat['name']
        n_days = int(len(pat['df']) / STEPS_PER_DAY)
        pat_exps = [e for e in all_experiments if e.patient == name]

        patient_stability = {}
        for etype in ['fasting', 'overnight', 'meal', 'correction', 'uam']:
            type_exps = [e for e in pat_exps if e.exp_type == etype]
            if len(type_exps) < 5:
                continue

            # Assign each experiment to a day
            exp_days = {}
            for e in type_exps:
                day = e.start_idx // STEPS_PER_DAY
                exp_days.setdefault(day, []).append(e)

            all_days = sorted(exp_days.keys())
            if len(all_days) < 7:
                continue

            # Bootstrap: for each day count, sample 20 times
            results_by_days = {}
            for n_target in day_targets:
                if n_target > len(all_days):
                    break
                estimates = []
                for _ in range(20):
                    sampled = np.random.choice(all_days, size=n_target, replace=False)
                    sampled_exps = []
                    for d in sampled:
                        sampled_exps.extend(exp_days.get(d, []))

                    # Compute key metric for this subsample
                    if etype == 'overnight' and sampled_exps:
                        vals = [e.measurements.get('drift_mg_dl_per_hour')
                                for e in sampled_exps
                                if e.measurements.get('drift_mg_dl_per_hour') is not None]
                        if vals:
                            estimates.append(np.mean(vals))
                    elif etype == 'correction' and sampled_exps:
                        vals = [e.measurements.get('curve_isf')
                                for e in sampled_exps
                                if e.measurements.get('curve_isf') is not None]
                        if vals:
                            estimates.append(np.mean(vals))
                    elif etype == 'meal' and sampled_exps:
                        vals = [e.measurements.get('excursion_mg_dl')
                                for e in sampled_exps
                                if e.measurements.get('excursion_mg_dl') is not None]
                        if vals:
                            estimates.append(np.mean(vals))
                    elif sampled_exps:
                        estimates.append(len(sampled_exps) / n_target)

                if len(estimates) >= 5:
                    results_by_days[n_target] = {
                        'mean': round(float(np.mean(estimates)), 3),
                        'std': round(float(np.std(estimates)), 3),
                        'cv': round(100 * float(np.std(estimates)) / max(abs(np.mean(estimates)), 0.01), 1),
                    }

            if results_by_days:
                # Find minimum days for CV < 10%
                min_days_stable = None
                for nd in sorted(results_by_days.keys()):
                    if results_by_days[nd]['cv'] < 10:
                        min_days_stable = nd
                        break

                patient_stability[etype] = {
                    'by_days': results_by_days,
                    'min_days_for_cv10': min_days_stable,
                }

        stability[name] = patient_stability

    # Population summary: median min_days per type
    pop_min_days = {}
    for etype in ['fasting', 'overnight', 'meal', 'correction', 'uam']:
        min_days_list = [stability[p][etype]['min_days_for_cv10']
                         for p in stability if etype in stability[p]
                         and stability[p][etype].get('min_days_for_cv10') is not None]
        if min_days_list:
            pop_min_days[etype] = {
                'median': int(np.median(min_days_list)),
                'range': [int(min(min_days_list)), int(max(min_days_list))],
                'n_patients': len(min_days_list),
            }

    return {
        'experiment': 'EXP-1555',
        'title': 'Minimum Data Requirements',
        'per_patient_stability': stability,
        'population_min_days': pop_min_days,
    }


@register(1556, 'Patient Archetype by Experiment Yield')
def exp_1556_archetypes(patients):
    """Cluster patients by their natural experiment profile."""
    all_experiments = _run_all_detectors(patients)

    # Build feature matrix: per_day rate for each type
    etypes = ['fasting', 'overnight', 'meal', 'correction', 'uam',
              'dawn', 'exercise', 'aid_response', 'stable']
    feature_matrix = []
    patient_names = []

    for pat in patients:
        name = pat['name']
        pat_exps = [e for e in all_experiments if e.patient == name]
        n_days = max(len(pat['df']) / STEPS_PER_DAY, 1)

        features = []
        for etype in etypes:
            rate = len([e for e in pat_exps if e.exp_type == etype]) / n_days
            features.append(rate)
        feature_matrix.append(features)
        patient_names.append(name)

    X = np.array(feature_matrix)

    # Normalize columns (z-score)
    means = X.mean(axis=0)
    stds = X.std(axis=0)
    stds[stds == 0] = 1
    X_norm = (X - means) / stds

    # Simple k-means with k=3 (well-calibrated, needs-tuning, miscalibrated)
    # Implement manually to avoid sklearn dependency
    k = min(3, len(patients))
    labels = _simple_kmeans(X_norm, k, max_iter=50)

    # Characterize clusters
    clusters = {}
    for ci in range(k):
        members = [patient_names[i] for i in range(len(labels)) if labels[i] == ci]
        if not members:
            continue
        cluster_X = X[labels == ci]
        profile = {etype: round(float(np.mean(cluster_X[:, j])), 2)
                   for j, etype in enumerate(etypes)}
        clusters[f'cluster_{ci}'] = {
            'members': members,
            'n': len(members),
            'mean_rates_per_day': profile,
        }

    # Per-patient feature table
    patient_profiles = {}
    for i, name in enumerate(patient_names):
        patient_profiles[name] = {
            'cluster': int(labels[i]),
            'rates_per_day': {etype: round(X[i, j], 2) for j, etype in enumerate(etypes)},
        }

    return {
        'experiment': 'EXP-1556',
        'title': 'Patient Archetype by Experiment Yield',
        'clusters': clusters,
        'patient_profiles': patient_profiles,
    }


@register(1557, 'Template Extraction')
def exp_1557_templates(patients):
    """Extract canonical glucose trajectory per window type."""
    all_experiments = _run_all_detectors(patients)

    templates = {}
    for etype in ['meal', 'correction', 'fasting', 'overnight', 'uam']:
        subset = [e for e in all_experiments if e.exp_type == etype and e.quality >= 0.5]
        if len(subset) < 10:
            templates[etype] = {'n': len(subset), 'note': 'insufficient high-quality windows'}
            continue

        # Extract aligned glucose trajectories
        max_len = 36  # 3 hours standardized
        if etype == 'correction':
            max_len = 48  # 4 hours for corrections
        elif etype in ('fasting', 'overnight'):
            max_len = 72  # 6 hours for fasting

        trajectories = []
        for exp in subset:
            pat = next((p for p in patients if p['name'] == exp.patient), None)
            if pat is None:
                continue
            bg = _bg(pat['df'])
            seg = bg[exp.start_idx:min(exp.end_idx, exp.start_idx + max_len)]
            if len(seg) < 6 or _cgm_coverage(seg) < 0.6:
                continue

            # Baseline-subtract
            baseline = np.nanmean(seg[:3]) if np.any(~np.isnan(seg[:3])) else np.nanmean(seg)
            if np.isnan(baseline):
                continue
            normalized = seg - baseline

            # Pad or truncate to max_len
            padded = np.full(max_len, np.nan)
            padded[:len(normalized)] = normalized
            trajectories.append(padded)

        if len(trajectories) < 5:
            templates[etype] = {'n': len(trajectories), 'note': 'insufficient valid trajectories'}
            continue

        traj_arr = np.array(trajectories)

        # Compute percentile bands
        with np.errstate(all='ignore'):
            median_traj = np.nanmedian(traj_arr, axis=0)
            p25_traj = np.nanpercentile(traj_arr, 25, axis=0)
            p75_traj = np.nanpercentile(traj_arr, 75, axis=0)
            mean_traj = np.nanmean(traj_arr, axis=0)

        templates[etype] = {
            'n': len(trajectories),
            'max_len_steps': max_len,
            'time_axis_min': list(range(0, max_len * STEP_MINUTES, STEP_MINUTES)),
            'median': [round(v, 2) if not np.isnan(v) else None for v in median_traj],
            'p25': [round(v, 2) if not np.isnan(v) else None for v in p25_traj],
            'p75': [round(v, 2) if not np.isnan(v) else None for v in p75_traj],
            'mean': [round(v, 2) if not np.isnan(v) else None for v in mean_traj],
        }

    return {
        'experiment': 'EXP-1557',
        'title': 'Template Extraction',
        'templates': templates,
    }


@register(1558, 'Production Integration Summary')
def exp_1558_production(patients):
    """Consolidate findings into NaturalExperimentDetector specification."""
    all_experiments = _run_all_detectors(patients)

    # Performance profiling per detector
    perf = {}
    for pat in patients[:1]:  # profile on first patient
        name = pat['name']
        df = pat['df']
        bg = _bg(df)
        bolus = np.nan_to_num(df['bolus'].values.astype(np.float64), nan=0.0)
        carbs_arr = np.nan_to_num(df['carbs'].values.astype(np.float64), nan=0.0)
        sd = compute_supply_demand(df, pat['pk'])

        for dtype, detector in [
            ('fasting',      lambda: detect_fasting_windows(name, df, bg, bolus, carbs_arr)),
            ('overnight',    lambda: detect_overnight_windows(name, df, bg, bolus, carbs_arr)),
            ('meal',         lambda: detect_meal_windows(name, df, bg, bolus, carbs_arr, sd)),
            ('correction',   lambda: detect_correction_windows(name, df, bg, bolus, carbs_arr)),
            ('uam',          lambda: detect_uam_windows(name, df, bg, carbs_arr, sd)),
            ('dawn',         lambda: detect_dawn_windows(name, df, bg, carbs_arr, bolus)),
            ('exercise',     lambda: detect_exercise_windows(name, df, bg, bolus, carbs_arr, sd)),
            ('aid_response', lambda: detect_aid_response_windows(name, df, bg)),
            ('stable',       lambda: detect_stable_windows(name, df, bg, bolus, carbs_arr)),
        ]:
            t0 = time.time()
            result = detector()
            elapsed = time.time() - t0
            perf[dtype] = {
                'time_seconds': round(elapsed, 3),
                'n_detected': len(result),
            }

    # Yield summary
    total = len(all_experiments)
    type_counts = defaultdict(int)
    for e in all_experiments:
        type_counts[e.exp_type] += 1

    return {
        'experiment': 'EXP-1558',
        'title': 'Production Integration Summary',
        'total_natural_experiments': total,
        'type_distribution': dict(type_counts),
        'detector_performance': perf,
        'production_spec': {
            'class_name': 'NaturalExperimentDetector',
            'input': 'PatientData (glucose, bolus, carbs, net_basal, supply_demand)',
            'output': 'List[NaturalExperiment] with type, quality, measurements',
            'detectors': list(perf.keys()),
            'estimated_runtime_per_patient_ms': round(sum(
                p['time_seconds'] for p in perf.values()) * 1000, 1),
        },
    }


@register(1559, 'Meal Detection Sensitivity')
def exp_1559_meal_sensitivity(patients):
    """Compare meal detection under 3 threshold configurations.

    Configs:
      A – Comprehensive census  : ≥5g carbs, 30-min clustering gap (current default)
      B – Medium hysteresis     : ≥5g carbs, 90-min clustering gap
      C – Therapy assessment    : ≥18g carbs, 90-min clustering gap
    """
    CONFIGS = {
        'A_census_5g_30m':   {'min_carbs': 5.0,  'cluster_gap': 6},
        'B_medium_5g_90m':   {'min_carbs': 5.0,  'cluster_gap': 18},
        'C_therapy_18g_90m': {'min_carbs': 18.0, 'cluster_gap': 18},
    }

    config_results = {}
    for cfg_name, cfg in CONFIGS.items():
        per_patient = {}
        all_meals = []
        for pat in patients:
            name = pat['name']
            df = pat['df']
            bg = _bg(df)
            bolus = np.nan_to_num(df['bolus'].values.astype(np.float64), nan=0.0)
            carbs_arr = np.nan_to_num(df['carbs'].values.astype(np.float64), nan=0.0)
            sd = compute_supply_demand(df, pat['pk'])
            days = len(df) / STEPS_PER_DAY

            meals = detect_meal_windows(name, df, bg, bolus, carbs_arr, sd,
                                        min_carbs=cfg['min_carbs'],
                                        cluster_gap=cfg['cluster_gap'])
            all_meals.extend(meals)

            # Per-patient summary
            carbs_list = [m.measurements['carbs_g'] for m in meals]
            excursions = [m.measurements['excursion_mg_dl'] for m in meals
                          if m.measurements.get('excursion_mg_dl') is not None]
            qualities = [m.quality for m in meals]
            peak_times = [m.measurements['peak_time_min'] for m in meals]
            announced = sum(1 for m in meals if m.measurements.get('is_announced'))

            per_patient[name] = {
                'count': len(meals),
                'per_day': round(len(meals) / days, 2) if days > 0 else 0,
                'mean_carbs_g': round(float(np.mean(carbs_list)), 1) if carbs_list else 0,
                'median_carbs_g': round(float(np.median(carbs_list)), 1) if carbs_list else 0,
                'mean_excursion': round(float(np.mean(excursions)), 1) if excursions else 0,
                'median_excursion': round(float(np.median(excursions)), 1) if excursions else 0,
                'mean_quality': round(float(np.mean(qualities)), 3) if qualities else 0,
                'mean_peak_time_min': round(float(np.mean(peak_times)), 1) if peak_times else 0,
                'pct_announced': round(100 * announced / len(meals), 1) if meals else 0,
            }

        # Population summary
        all_carbs = [m.measurements['carbs_g'] for m in all_meals]
        all_exc = [m.measurements['excursion_mg_dl'] for m in all_meals
                    if m.measurements.get('excursion_mg_dl') is not None]
        all_q = [m.quality for m in all_meals]
        all_pt = [m.measurements['peak_time_min'] for m in all_meals]
        all_announced = sum(1 for m in all_meals if m.measurements.get('is_announced'))

        # Quality grade distribution
        grades = {'excellent': 0, 'good': 0, 'acceptable': 0, 'poor': 0}
        for q in all_q:
            if q >= 0.80:
                grades['excellent'] += 1
            elif q >= 0.60:
                grades['good'] += 1
            elif q >= 0.40:
                grades['acceptable'] += 1
            else:
                grades['poor'] += 1

        # Excursion distribution by carb range
        excursion_by_carb_range = {}
        for m in all_meals:
            cg = m.measurements['carbs_g']
            exc = m.measurements.get('excursion_mg_dl')
            if exc is None:
                continue
            if cg < 10:
                rng = '<10g'
            elif cg < 20:
                rng = '10-19g'
            elif cg < 30:
                rng = '20-29g'
            elif cg < 50:
                rng = '30-49g'
            else:
                rng = '≥50g'
            excursion_by_carb_range.setdefault(rng, []).append(exc)

        exc_summary = {}
        for rng, vals in sorted(excursion_by_carb_range.items()):
            exc_summary[rng] = {
                'n': len(vals),
                'mean': round(float(np.mean(vals)), 1),
                'median': round(float(np.median(vals)), 1),
                'p25': round(float(np.percentile(vals, 25)), 1),
                'p75': round(float(np.percentile(vals, 75)), 1),
            }

        # Time-of-day distribution (24 bins)
        hour_hist = [0] * 24
        for m in all_meals:
            hour_hist[int(m.hour_of_day) % 24] += 1

        config_results[cfg_name] = {
            'config': cfg,
            'total_meals': len(all_meals),
            'per_patient': per_patient,
            'population': {
                'mean_carbs_g': round(float(np.mean(all_carbs)), 1) if all_carbs else 0,
                'median_carbs_g': round(float(np.median(all_carbs)), 1) if all_carbs else 0,
                'mean_excursion': round(float(np.mean(all_exc)), 1) if all_exc else 0,
                'median_excursion': round(float(np.median(all_exc)), 1) if all_exc else 0,
                'mean_quality': round(float(np.mean(all_q)), 3) if all_q else 0,
                'mean_peak_time_min': round(float(np.mean(all_pt)), 1) if all_pt else 0,
                'pct_announced': round(100 * all_announced / len(all_meals), 1) if all_meals else 0,
                'quality_grades': grades,
                'grade_pcts': {k: round(100 * v / len(all_meals), 1) if all_meals else 0
                               for k, v in grades.items()},
            },
            'excursion_by_carb_range': exc_summary,
            'hour_of_day_histogram': hour_hist,
        }

    # Comparison delta table
    baseline = config_results['A_census_5g_30m']
    deltas = {}
    for cfg_name in ['B_medium_5g_90m', 'C_therapy_18g_90m']:
        cfg_r = config_results[cfg_name]
        deltas[cfg_name] = {
            'total_meals_delta': cfg_r['total_meals'] - baseline['total_meals'],
            'total_meals_pct_change': round(
                100 * (cfg_r['total_meals'] - baseline['total_meals']) / baseline['total_meals'], 1
            ) if baseline['total_meals'] > 0 else 0,
            'quality_delta': round(
                cfg_r['population']['mean_quality'] - baseline['population']['mean_quality'], 3),
            'excursion_delta': round(
                cfg_r['population']['mean_excursion'] - baseline['population']['mean_excursion'], 1),
            'carbs_g_delta': round(
                cfg_r['population']['mean_carbs_g'] - baseline['population']['mean_carbs_g'], 1),
            'per_patient_deltas': {
                pat: {
                    'count_delta': cfg_r['per_patient'][pat]['count'] - baseline['per_patient'][pat]['count'],
                    'quality_delta': round(
                        cfg_r['per_patient'][pat]['mean_quality'] - baseline['per_patient'][pat]['mean_quality'], 3),
                }
                for pat in baseline['per_patient']
            },
        }

    return {
        'experiment': 'EXP-1559',
        'title': 'Meal Detection Sensitivity',
        'configs': config_results,
        'deltas_vs_baseline': deltas,
    }


@register(1561, 'Meal Response Metabolic Characterization')
def exp_1561_meal_metabolic(patients):
    """Compare carb ranges by ISF-normalized excursion and supply×demand spectral power.

    Extends EXP-1559's excursion-by-carb-range with two new dimensions:

    1. ISF-Normalized Excursion = excursion_mg_dl / patient_ISF
       Dimensionless: "how many correction-units is this excursion?"
       Enables cross-patient comparison regardless of insulin sensitivity.

    2. Supply×Demand Spectral Power = Σ(supply[t] × demand[t])² over meal window
       Captures metabolic interaction intensity: how much push-pull between
       insulin and carbs during the meal. High = active AID response.
       Normalized to per-hour for duration-invariant comparison.

    Uses therapy config (≥18g / 90min) for highest-quality meals.
    """
    CARB_RANGES = [
        ('<10g',    0,   10),
        ('10-19g', 10,   20),
        ('20-29g', 20,   30),
        ('30-49g', 30,   50),
        ('≥50g',   50, 9999),
    ]

    # Collect per-meal metabolic measurements
    meal_records = []  # list of dicts

    for pat in patients:
        name = pat['name']
        df = pat['df']
        bg = _bg(df)
        N = len(bg)
        bolus = np.nan_to_num(df['bolus'].values.astype(np.float64), nan=0.0)
        carbs_arr = np.nan_to_num(df['carbs'].values.astype(np.float64), nan=0.0)
        sd = compute_supply_demand(df, pat['pk'])

        # ISF in mg/dL (handles mmol/L auto-detection)
        isf = _extract_isf_scalar(df)

        # Detect meals with therapy config (high-quality)
        meals = detect_meal_windows(name, df, bg, bolus, carbs_arr, sd,
                                    min_carbs=18.0, cluster_gap=18)

        supply = sd['supply']
        demand = sd['demand']

        for m in meals:
            exc = m.measurements.get('excursion_mg_dl')
            if exc is None or math.isnan(exc):
                continue
            carbs_g = m.measurements['carbs_g']

            # ISF-normalized excursion (dimensionless: correction-equivalents)
            isf_norm_exc = exc / isf if isf > 0 else float('nan')

            # Supply×demand spectral power over meal window
            s_start = m.start_idx
            s_end = min(m.end_idx, N)
            if s_end - s_start < 6:  # need ≥30 min
                continue

            win_supply = supply[s_start:s_end]
            win_demand = demand[s_start:s_end]

            # Element-wise product: metabolic interaction signal
            interaction = win_supply * win_demand

            # Spectral power = sum of squared FFT coefficients (Parseval's)
            # Excludes DC (mean) component to capture dynamics, not baseline
            fft_coeffs = np.fft.rfft(interaction)
            # Drop DC component (index 0)
            spectral_power = float(np.sum(np.abs(fft_coeffs[1:]) ** 2))

            # Normalize to per-hour for duration invariance
            duration_hours = (s_end - s_start) * STEP_MINUTES / 60.0
            spectral_power_per_hour = spectral_power / max(duration_hours, 0.5)

            # Also compute signal energy (simpler metric) and mean interaction
            signal_energy = float(np.sum(interaction ** 2))
            mean_interaction = float(np.mean(interaction))
            interaction_cv = float(np.std(interaction) / max(abs(mean_interaction), 1e-6) * 100)

            # Net flux metrics during meal window
            net = sd['net'][s_start:s_end]
            net_mean = float(np.nanmean(net))
            net_std = float(np.nanstd(net))

            # Classify carb range
            carb_range = None
            for label, lo, hi in CARB_RANGES:
                if lo <= carbs_g < hi:
                    carb_range = label
                    break

            meal_records.append({
                'patient': name,
                'isf_mgdl': round(isf, 1),
                'carbs_g': carbs_g,
                'carb_range': carb_range,
                'excursion_mg_dl': round(exc, 1),
                'isf_norm_excursion': round(isf_norm_exc, 3),
                'spectral_power_per_hour': round(spectral_power_per_hour, 2),
                'signal_energy': round(signal_energy, 2),
                'mean_interaction': round(mean_interaction, 3),
                'interaction_cv_pct': round(interaction_cv, 1),
                'net_flux_mean': round(net_mean, 3),
                'net_flux_std': round(net_std, 3),
                'quality': m.quality,
                'peak_time_min': m.measurements['peak_time_min'],
                'bolus_u': m.measurements['bolus_u'],
                'is_announced': m.measurements.get('is_announced', False),
                'hour_of_day': m.hour_of_day,
                'day_of_week': m.day_of_week,
                'duration_hours': round(duration_hours, 2),
            })

    print(f"\n  Total meal records with metabolic data: {len(meal_records)}")

    # Per-patient ISF summary
    per_patient_isf = {}
    for pat in patients:
        name = pat['name']
        isf = _extract_isf_scalar(pat['df'])
        pat_meals = [r for r in meal_records if r['patient'] == name]
        per_patient_isf[name] = {
            'isf_mgdl': round(isf, 1),
            'n_meals': len(pat_meals),
            'mean_raw_excursion': round(float(np.mean([r['excursion_mg_dl'] for r in pat_meals])), 1) if pat_meals else None,
            'mean_isf_norm_excursion': round(float(np.mean([r['isf_norm_excursion'] for r in pat_meals])), 3) if pat_meals else None,
            'mean_spectral_power': round(float(np.mean([r['spectral_power_per_hour'] for r in pat_meals])), 2) if pat_meals else None,
        }

    # Summary by carb range
    range_labels = [r[0] for r in CARB_RANGES]
    by_carb_range = {}
    for label in range_labels:
        subset = [r for r in meal_records if r['carb_range'] == label]
        if not subset:
            by_carb_range[label] = {'n': 0}
            continue

        raw_exc = [r['excursion_mg_dl'] for r in subset]
        isf_exc = [r['isf_norm_excursion'] for r in subset]
        spec_pow = [r['spectral_power_per_hour'] for r in subset]
        sig_eng = [r['signal_energy'] for r in subset]
        mean_int = [r['mean_interaction'] for r in subset]
        net_mean = [r['net_flux_mean'] for r in subset]

        by_carb_range[label] = {
            'n': len(subset),
            # Raw excursion
            'raw_excursion_mean': round(float(np.mean(raw_exc)), 1),
            'raw_excursion_median': round(float(np.median(raw_exc)), 1),
            'raw_excursion_p25': round(float(np.percentile(raw_exc, 25)), 1),
            'raw_excursion_p75': round(float(np.percentile(raw_exc, 75)), 1),
            # ISF-normalized excursion
            'isf_norm_mean': round(float(np.mean(isf_exc)), 3),
            'isf_norm_median': round(float(np.median(isf_exc)), 3),
            'isf_norm_p25': round(float(np.percentile(isf_exc, 25)), 3),
            'isf_norm_p75': round(float(np.percentile(isf_exc, 75)), 3),
            # Supply×demand spectral power
            'spectral_power_mean': round(float(np.mean(spec_pow)), 2),
            'spectral_power_median': round(float(np.median(spec_pow)), 2),
            'spectral_power_p25': round(float(np.percentile(spec_pow, 25)), 2),
            'spectral_power_p75': round(float(np.percentile(spec_pow, 75)), 2),
            # Signal energy
            'signal_energy_mean': round(float(np.mean(sig_eng)), 2),
            'signal_energy_median': round(float(np.median(sig_eng)), 2),
            # Mean interaction
            'mean_interaction_mean': round(float(np.mean(mean_int)), 3),
            # Net flux
            'net_flux_mean': round(float(np.mean(net_mean)), 3),
        }

    # Cross-metric correlations (Pearson)
    if len(meal_records) >= 10:
        carbs_arr_corr = np.array([r['carbs_g'] for r in meal_records])
        raw_exc_arr = np.array([r['excursion_mg_dl'] for r in meal_records])
        isf_norm_arr = np.array([r['isf_norm_excursion'] for r in meal_records])
        spec_arr = np.array([r['spectral_power_per_hour'] for r in meal_records])
        energy_arr = np.array([r['signal_energy'] for r in meal_records])

        def _pearson(a, b):
            mask = np.isfinite(a) & np.isfinite(b)
            if mask.sum() < 5:
                return None
            a2, b2 = a[mask], b[mask]
            return round(float(np.corrcoef(a2, b2)[0, 1]), 3)

        correlations = {
            'carbs_vs_raw_excursion': _pearson(carbs_arr_corr, raw_exc_arr),
            'carbs_vs_isf_norm_excursion': _pearson(carbs_arr_corr, isf_norm_arr),
            'carbs_vs_spectral_power': _pearson(carbs_arr_corr, spec_arr),
            'raw_excursion_vs_isf_norm': _pearson(raw_exc_arr, isf_norm_arr),
            'raw_excursion_vs_spectral_power': _pearson(raw_exc_arr, spec_arr),
            'isf_norm_vs_spectral_power': _pearson(isf_norm_arr, spec_arr),
            'spectral_power_vs_signal_energy': _pearson(spec_arr, energy_arr),
        }
    else:
        correlations = {}

    # Announced vs unannounced comparison
    announced = [r for r in meal_records if r['is_announced']]
    unannounced = [r for r in meal_records if not r['is_announced']]

    announcement_comparison = {}
    for label, subset in [('announced', announced), ('unannounced', unannounced)]:
        if not subset:
            announcement_comparison[label] = {'n': 0}
            continue
        announcement_comparison[label] = {
            'n': len(subset),
            'mean_raw_excursion': round(float(np.mean([r['excursion_mg_dl'] for r in subset])), 1),
            'mean_isf_norm_excursion': round(float(np.mean([r['isf_norm_excursion'] for r in subset])), 3),
            'mean_spectral_power': round(float(np.mean([r['spectral_power_per_hour'] for r in subset])), 2),
        }

    return {
        'experiment': 'EXP-1561',
        'title': 'Meal Response Metabolic Characterization',
        'n_meals': len(meal_records),
        'n_patients': len(patients),
        'config': 'therapy (≥18g / 90min)',
        'per_patient_isf': per_patient_isf,
        'by_carb_range': by_carb_range,
        'correlations': correlations,
        'announcement_comparison': announcement_comparison,
        'meal_records': meal_records,
    }


# ---------------------------------------------------------------------------
# Shared helpers for multi-config metabolic analysis (EXP-1563)
# ---------------------------------------------------------------------------

def _metabolic_by_carb_range(meal_records):
    """Compute ISF-norm, spectral power, and other metrics grouped by carb range."""
    CARB_RANGES = [
        ('<10g',    0,   10),
        ('10-19g', 10,   20),
        ('20-29g', 20,   30),
        ('30-49g', 30,   50),
        ('≥50g',   50, 9999),
    ]
    by_range = {}
    for label, lo, hi in CARB_RANGES:
        subset = [r for r in meal_records if r['carb_range'] == label]
        if not subset:
            by_range[label] = {'n': 0}
            continue

        raw_exc = [r['excursion_mg_dl'] for r in subset]
        isf_exc = [r['isf_norm_excursion'] for r in subset]
        spec_pow = [r['spectral_power_per_hour'] for r in subset]
        mean_int = [r['mean_interaction'] for r in subset]
        net_mean = [r['net_flux_mean'] for r in subset]

        by_range[label] = {
            'n': len(subset),
            'raw_excursion_mean': round(float(np.mean(raw_exc)), 1),
            'raw_excursion_median': round(float(np.median(raw_exc)), 1),
            'raw_excursion_p25': round(float(np.percentile(raw_exc, 25)), 1),
            'raw_excursion_p75': round(float(np.percentile(raw_exc, 75)), 1),
            'isf_norm_mean': round(float(np.mean(isf_exc)), 3),
            'isf_norm_median': round(float(np.median(isf_exc)), 3),
            'isf_norm_p25': round(float(np.percentile(isf_exc, 25)), 3),
            'isf_norm_p75': round(float(np.percentile(isf_exc, 75)), 3),
            'spectral_power_mean': round(float(np.mean(spec_pow)), 2),
            'spectral_power_median': round(float(np.median(spec_pow)), 2),
            'spectral_power_p25': round(float(np.percentile(spec_pow, 25)), 2),
            'spectral_power_p75': round(float(np.percentile(spec_pow, 75)), 2),
            'mean_interaction_mean': round(float(np.mean(mean_int)), 3),
            'net_flux_mean': round(float(np.mean(net_mean)), 3),
        }
    return by_range


def _collect_meal_metabolic_records(patients, min_carbs, cluster_gap):
    """Detect meals with given config and collect metabolic measurements."""
    CARB_RANGES = [
        ('<10g',    0,   10),
        ('10-19g', 10,   20),
        ('20-29g', 20,   30),
        ('30-49g', 30,   50),
        ('≥50g',   50, 9999),
    ]
    records = []
    for pat in patients:
        name = pat['name']
        df = pat['df']
        bg = _bg(df)
        N = len(bg)
        bolus = np.nan_to_num(df['bolus'].values.astype(np.float64), nan=0.0)
        carbs_arr = np.nan_to_num(df['carbs'].values.astype(np.float64), nan=0.0)
        sd = compute_supply_demand(df, pat['pk'])
        isf = _extract_isf_scalar(df)

        meals = detect_meal_windows(name, df, bg, bolus, carbs_arr, sd,
                                    min_carbs=min_carbs, cluster_gap=cluster_gap)
        supply = sd['supply']
        demand = sd['demand']

        for m in meals:
            exc = m.measurements.get('excursion_mg_dl')
            if exc is None or math.isnan(exc):
                continue
            carbs_g = m.measurements['carbs_g']
            isf_norm_exc = exc / isf if isf > 0 else float('nan')

            s_start = m.start_idx
            s_end = min(m.end_idx, N)
            if s_end - s_start < 6:
                continue

            win_supply = supply[s_start:s_end]
            win_demand = demand[s_start:s_end]
            interaction = win_supply * win_demand

            fft_coeffs = np.fft.rfft(interaction)
            spectral_power = float(np.sum(np.abs(fft_coeffs[1:]) ** 2))
            duration_hours = (s_end - s_start) * STEP_MINUTES / 60.0
            spectral_power_per_hour = spectral_power / max(duration_hours, 0.5)

            mean_interaction = float(np.mean(interaction))
            net = sd['net'][s_start:s_end]
            net_mean = float(np.nanmean(net))

            carb_range = None
            for label, lo, hi in CARB_RANGES:
                if lo <= carbs_g < hi:
                    carb_range = label
                    break

            records.append({
                'patient': name,
                'isf_mgdl': round(isf, 1),
                'carbs_g': carbs_g,
                'carb_range': carb_range,
                'excursion_mg_dl': round(exc, 1),
                'isf_norm_excursion': round(isf_norm_exc, 3),
                'spectral_power_per_hour': round(spectral_power_per_hour, 2),
                'mean_interaction': round(mean_interaction, 3),
                'net_flux_mean': round(net_mean, 3),
                'quality': m.quality,
                'peak_time_min': m.measurements['peak_time_min'],
                'bolus_u': m.measurements['bolus_u'],
                'is_announced': m.measurements.get('is_announced', False),
                'hour_of_day': m.hour_of_day,
                'day_of_week': m.day_of_week,
                'duration_hours': round(duration_hours, 2),
            })
    return records


# Canonical mealtime zones for periodicity analysis
MEALTIME_ZONES = {
    'breakfast': (6, 10),    # 6:00–10:00
    'lunch':     (11, 14),   # 11:00–14:00
    'dinner':    (17, 21),   # 17:00–21:00
}


def _mealtime_periodicity(records, patients):
    """Analyze meal periodicity within canonical mealtime zones.

    Returns metrics per zone measuring how concentrated/regular meals are:
    - zone_fraction: % of meals that fall in any mealtime zone
    - zone_counts: meals per zone
    - per_patient_regularity: std of meal hour within each zone (lower = more regular)
    - zone_entropy: Shannon entropy of 24-bin hourly histogram (lower = more periodic)
    - peak_to_mean: ratio of peak hourly bin to mean (higher = more concentrated)
    """
    if not records:
        return {}

    hours = [r['hour_of_day'] for r in records]

    # 24-bin hourly histogram
    hist = np.zeros(24)
    for h in hours:
        hist[int(h) % 24] += 1
    hist_norm = hist / max(hist.sum(), 1)

    # Shannon entropy (lower = more periodic/concentrated)
    entropy = 0.0
    for p in hist_norm:
        if p > 0:
            entropy -= p * np.log2(p)
    max_entropy = np.log2(24)  # uniform distribution

    # Peak-to-mean ratio
    peak_to_mean = float(hist.max() / max(hist.mean(), 1))

    # Zone analysis
    zone_stats = {}
    in_any_zone = 0
    for zone_name, (start_h, end_h) in MEALTIME_ZONES.items():
        zone_meals = [r for r in records if start_h <= r['hour_of_day'] < end_h]
        in_any_zone += len(zone_meals)

        zone_hours = [r['hour_of_day'] for r in zone_meals]

        # Per-patient regularity: mean of per-patient std within zone
        patient_stds = []
        pat_names = sorted(set(r['patient'] for r in records))
        for pat in pat_names:
            pat_hours = [r['hour_of_day'] for r in zone_meals if r['patient'] == pat]
            if len(pat_hours) >= 3:
                patient_stds.append(float(np.std(pat_hours)))

        zone_stats[zone_name] = {
            'n_meals': len(zone_meals),
            'pct_of_total': round(100 * len(zone_meals) / len(records), 1),
            'mean_hour': round(float(np.mean(zone_hours)), 2) if zone_hours else None,
            'std_hour': round(float(np.std(zone_hours)), 2) if len(zone_hours) >= 2 else None,
            'per_patient_mean_std': round(float(np.mean(patient_stds)), 2) if patient_stds else None,
            'mean_isf_norm': round(float(np.mean(
                [r['isf_norm_excursion'] for r in zone_meals])), 3) if zone_meals else None,
            'mean_spectral_power': round(float(np.mean(
                [r['spectral_power_per_hour'] for r in zone_meals])), 2) if zone_meals else None,
        }

    return {
        'total_meals': len(records),
        'in_mealtime_zones': in_any_zone,
        'zone_fraction_pct': round(100 * in_any_zone / len(records), 1),
        'entropy_bits': round(entropy, 3),
        'max_entropy_bits': round(max_entropy, 3),
        'normalized_entropy': round(entropy / max_entropy, 3),  # 0=perfect periodicity, 1=uniform
        'peak_to_mean_ratio': round(peak_to_mean, 2),
        'hour_histogram': [int(x) for x in hist],
        'zones': zone_stats,
    }


def _compute_personal_regularity(hours):
    """Compute meal clock regularity from an array of meal hours.

    Returns dict with n_peaks, weighted_std, normalized_entropy, personal_peaks,
    hour_histogram.  Reusable across EXP-1567 and EXP-1569.
    """
    from scipy.ndimage import uniform_filter1d
    hours = np.asarray(hours, dtype=float)
    n = len(hours)
    if n == 0:
        return {'n_peaks': 0, 'weighted_std': float('nan'),
                'normalized_entropy': float('nan'), 'personal_peaks': [],
                'hour_histogram': [0]*24}

    hist = np.zeros(24)
    for h in hours:
        hist[int(h) % 24] += 1
    hist_norm = hist / max(hist.sum(), 1)
    entropy = -sum(p * np.log2(p) for p in hist_norm if p > 0)
    norm_entropy = entropy / np.log2(24)

    smoothed = uniform_filter1d(np.concatenate([hist, hist, hist]),
                                size=4, mode='wrap')[24:48]
    peaks = []
    for i in range(24):
        left = smoothed[(i - 1) % 24]
        right = smoothed[(i + 1) % 24]
        if smoothed[i] > left and smoothed[i] > right and smoothed[i] >= 2:
            peaks.append(i)

    peak_clusters = {}
    if peaks:
        for h in hours:
            dists = [min(abs(h - p), 24 - abs(h - p)) for p in peaks]
            nearest = peaks[int(np.argmin(dists))]
            peak_clusters.setdefault(nearest, []).append(float(h))

    personal_peaks = []
    for pk in sorted(peak_clusters.keys()):
        ch = peak_clusters[pk]
        m = float(np.mean(ch))
        personal_peaks.append({
            'peak_hour': pk,
            'n_meals': len(ch),
            'mean_hour': round(m, 2),
            'std_hour': round(float(np.std(ch)), 2),
            'within_3hr_pct': round(100 * sum(
                1 for h in ch if min(abs(h - m), 24 - abs(h - m)) <= 1.5
            ) / len(ch), 1),
        })

    if personal_peaks:
        weighted_std = sum(p['std_hour'] * p['n_meals'] for p in personal_peaks) / n
    else:
        weighted_std = float(np.std(hours))

    return {
        'n_peaks': len(peaks),
        'weighted_std': round(weighted_std, 3),
        'normalized_entropy': round(norm_entropy, 3),
        'personal_peaks': personal_peaks,
        'hour_histogram': [int(x) for x in hist],
    }


@register(1563, 'Multi-Config Metabolic Characterization')
def exp_1563_multi_config_metabolic(patients):
    """Compare ISF-normalized excursion, spectral power, and meal periodicity
    across 3 detection configs.

    Extends EXP-1561 (therapy-only) to all 3 configs from EXP-1559:
      A – ≥5g / 30min  (census, includes micro-meals)
      B – ≥5g / 90min  (medium, longer hysteresis)
      C – ≥18g / 90min (therapy, high-quality only)

    Additional question: Does stricter detection increase meal periodicity
    within canonical mealtime zones (breakfast, lunch, dinner)?
    """
    CONFIGS = {
        'A_census_5g_30m':   {'min_carbs': 5.0,  'cluster_gap': 6},
        'B_medium_5g_90m':   {'min_carbs': 5.0,  'cluster_gap': 18},
        'C_therapy_18g_90m': {'min_carbs': 18.0, 'cluster_gap': 18},
    }

    config_results = {}
    for cfg_name, cfg in CONFIGS.items():
        print(f"\n  Config {cfg_name}:")
        records = _collect_meal_metabolic_records(
            patients, cfg['min_carbs'], cfg['cluster_gap'])
        by_range = _metabolic_by_carb_range(records)
        periodicity = _mealtime_periodicity(records, patients)

        # Population summary
        if records:
            pop_raw = [r['excursion_mg_dl'] for r in records]
            pop_isf = [r['isf_norm_excursion'] for r in records]
            pop_spec = [r['spectral_power_per_hour'] for r in records]
            pop_net = [r['net_flux_mean'] for r in records]
            population = {
                'mean_raw_excursion': round(float(np.mean(pop_raw)), 1),
                'median_raw_excursion': round(float(np.median(pop_raw)), 1),
                'mean_isf_norm': round(float(np.mean(pop_isf)), 3),
                'median_isf_norm': round(float(np.median(pop_isf)), 3),
                'mean_spectral_power': round(float(np.mean(pop_spec)), 2),
                'median_spectral_power': round(float(np.median(pop_spec)), 2),
                'mean_net_flux': round(float(np.mean(pop_net)), 3),
            }
        else:
            population = {}

        config_results[cfg_name] = {
            'config': cfg,
            'n_meals': len(records),
            'by_carb_range': by_range,
            'population': population,
            'periodicity': periodicity,
            'records': records,  # keep for viz
        }
        ent = periodicity.get('normalized_entropy', 'N/A')
        zf = periodicity.get('zone_fraction_pct', 'N/A')
        print(f"    {len(records)} meals, median ISF-norm={population.get('median_isf_norm', 'N/A')}, "
              f"entropy={ent}, zone%={zf}")

    # Config comparison delta table
    baseline = config_results['A_census_5g_30m']
    deltas = {}
    for cfg_name in ['B_medium_5g_90m', 'C_therapy_18g_90m']:
        cfg_r = config_results[cfg_name]
        bp = baseline.get('population', {})
        cp = cfg_r.get('population', {})
        bper = baseline.get('periodicity', {})
        cper = cfg_r.get('periodicity', {})
        if bp and cp:
            deltas[cfg_name] = {
                'n_meals_delta': cfg_r['n_meals'] - baseline['n_meals'],
                'isf_norm_delta': round(
                    cp.get('median_isf_norm', 0) - bp.get('median_isf_norm', 0), 3),
                'spectral_delta_pct': round(
                    100 * (cp.get('median_spectral_power', 0) - bp.get('median_spectral_power', 0))
                    / max(bp.get('median_spectral_power', 1), 1), 1),
                'entropy_delta': round(
                    cper.get('normalized_entropy', 0) - bper.get('normalized_entropy', 0), 3),
                'zone_fraction_delta': round(
                    cper.get('zone_fraction_pct', 0) - bper.get('zone_fraction_pct', 0), 1),
            }

    # Small-meal characterization (5-18g only, present in A/B but not C)
    small_meals_a = [r for r in config_results['A_census_5g_30m']['records']
                     if r['carbs_g'] < 18]
    large_meals_a = [r for r in config_results['A_census_5g_30m']['records']
                     if r['carbs_g'] >= 18]
    small_vs_large = {}
    for label, subset in [('small_5_to_18g', small_meals_a), ('large_18g_plus', large_meals_a)]:
        if not subset:
            small_vs_large[label] = {'n': 0}
            continue
        small_vs_large[label] = {
            'n': len(subset),
            'median_raw_excursion': round(float(np.median([r['excursion_mg_dl'] for r in subset])), 1),
            'median_isf_norm': round(float(np.median([r['isf_norm_excursion'] for r in subset])), 3),
            'median_spectral_power': round(float(np.median([r['spectral_power_per_hour'] for r in subset])), 2),
            'mean_net_flux': round(float(np.mean([r['net_flux_mean'] for r in subset])), 3),
            'pct_announced': round(100 * sum(1 for r in subset if r['is_announced']) / len(subset), 1),
        }

    # Strip records from output (too large for JSON)
    save_configs = {}
    for cn, cv in config_results.items():
        save_configs[cn] = {k: v for k, v in cv.items() if k != 'records'}

    return {
        'experiment': 'EXP-1563',
        'title': 'Multi-Config Metabolic Characterization',
        'n_patients': len(patients),
        'configs': save_configs,
        'deltas_vs_baseline': deltas,
        'small_vs_large_meals': small_vs_large,
        '_config_records': config_results,  # internal, for viz
    }


def _weekday_weekend_periodicity(records):
    """Compute periodicity metrics separately for weekdays vs weekends.

    Returns dict with 'weekday', 'weekend', and 'comparison' sub-dicts.
    day_of_week: 0=Monday … 6=Sunday.
    """
    if not records:
        return {}

    weekday_records = [r for r in records if r.get('day_of_week', 0) < 5]
    weekend_records = [r for r in records if r.get('day_of_week', 0) >= 5]

    results = {}
    for label, subset in [('weekday', weekday_records), ('weekend', weekend_records)]:
        if not subset:
            results[label] = {'n': 0}
            continue

        hours = [r['hour_of_day'] for r in subset]
        hist = np.zeros(24)
        for h in hours:
            hist[int(h) % 24] += 1
        hist_norm = hist / max(hist.sum(), 1)

        entropy = 0.0
        for p in hist_norm:
            if p > 0:
                entropy -= p * np.log2(p)
        max_entropy = np.log2(24)

        peak_hour = int(np.argmax(hist))
        peak_to_mean = float(hist.max() / max(hist.mean(), 1))

        # Zone analysis
        in_zone = 0
        zone_detail = {}
        for zone_name, (s, e) in MEALTIME_ZONES.items():
            zone_meals = [r for r in subset if s <= r['hour_of_day'] < e]
            in_zone += len(zone_meals)
            zone_hours = [r['hour_of_day'] for r in zone_meals]
            zone_detail[zone_name] = {
                'n': len(zone_meals),
                'mean_hour': round(float(np.mean(zone_hours)), 2) if zone_hours else None,
                'std_hour': round(float(np.std(zone_hours)), 2) if len(zone_hours) >= 2 else None,
            }

        # Metabolic metrics
        isf_norms = [r['isf_norm_excursion'] for r in subset if np.isfinite(r['isf_norm_excursion'])]
        spectral = [r['spectral_power_per_hour'] for r in subset if np.isfinite(r['spectral_power_per_hour'])]

        results[label] = {
            'n': len(subset),
            'entropy': round(entropy, 3),
            'normalized_entropy': round(entropy / max_entropy, 3),
            'peak_hour': peak_hour,
            'peak_to_mean': round(peak_to_mean, 2),
            'zone_fraction_pct': round(100 * in_zone / len(subset), 1),
            'zones': zone_detail,
            'hour_histogram': [int(x) for x in hist],
            'mean_isf_norm': round(float(np.mean(isf_norms)), 3) if isf_norms else None,
            'mean_spectral': round(float(np.mean(spectral)), 2) if spectral else None,
            'median_hour': round(float(np.median(hours)), 1),
        }

    # Comparison
    wd = results.get('weekday', {})
    we = results.get('weekend', {})
    if wd.get('n', 0) > 0 and we.get('n', 0) > 0:
        results['comparison'] = {
            'entropy_delta': round(we.get('normalized_entropy', 0) - wd.get('normalized_entropy', 0), 3),
            'zone_fraction_delta': round(we.get('zone_fraction_pct', 0) - wd.get('zone_fraction_pct', 0), 1),
            'peak_hour_shift': we.get('peak_hour', 0) - wd.get('peak_hour', 0),
            'median_hour_shift': round(we.get('median_hour', 0) - wd.get('median_hour', 0), 1),
            'meals_per_day_weekday': round(wd['n'] / 5, 1),  # normalized to days in week
            'meals_per_day_weekend': round(we['n'] / 2, 1),
        }

    return results


def _per_patient_dow_analysis(records):
    """Per-patient weekday vs weekend breakdown."""
    pat_names = sorted(set(r['patient'] for r in records))
    per_patient = {}
    for pat in pat_names:
        pat_records = [r for r in records if r['patient'] == pat]
        wd = [r for r in pat_records if r.get('day_of_week', 0) < 5]
        we = [r for r in pat_records if r.get('day_of_week', 0) >= 5]

        wd_hours = [r['hour_of_day'] for r in wd]
        we_hours = [r['hour_of_day'] for r in we]

        per_patient[pat] = {
            'n_weekday': len(wd),
            'n_weekend': len(we),
            'weekday_mean_hour': round(float(np.mean(wd_hours)), 1) if wd_hours else None,
            'weekend_mean_hour': round(float(np.mean(we_hours)), 1) if we_hours else None,
            'hour_shift': round(float(np.mean(we_hours)) - float(np.mean(wd_hours)), 1)
                if wd_hours and we_hours else None,
            'weekday_std_hour': round(float(np.std(wd_hours)), 2) if len(wd_hours) >= 2 else None,
            'weekend_std_hour': round(float(np.std(we_hours)), 2) if len(we_hours) >= 2 else None,
        }

        # ISF-norm comparison
        wd_isf = [r['isf_norm_excursion'] for r in wd if np.isfinite(r['isf_norm_excursion'])]
        we_isf = [r['isf_norm_excursion'] for r in we if np.isfinite(r['isf_norm_excursion'])]
        if wd_isf and we_isf:
            per_patient[pat]['weekday_isf_norm'] = round(float(np.mean(wd_isf)), 3)
            per_patient[pat]['weekend_isf_norm'] = round(float(np.mean(we_isf)), 3)
            per_patient[pat]['isf_norm_delta'] = round(float(np.mean(we_isf)) - float(np.mean(wd_isf)), 3)

    return per_patient


@register(1565, 'Weekday vs Weekend Meal Periodicity')
def exp_1565_weekday_weekend_periodicity(patients):
    """Test hypothesis: meal timing is bimodal (weekday vs weekend) with
    different periodicity, meal timing shifts, and metabolic profiles.

    Hypothesis: Weekend meals are later, less periodic (higher entropy),
    and may have different ISF-norm / spectral power characteristics
    (less structured eating, more snacking, different activity levels).
    """
    # Use therapy config for cleanest signal
    records = _collect_meal_metabolic_records(patients, min_carbs=18.0, cluster_gap=18)
    print(f"  {len(records)} meals (therapy config)")

    # Check day_of_week coverage
    dow_counts = [0] * 7
    for r in records:
        dow_counts[r.get('day_of_week', 0)] += 1
    dow_labels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    print(f"  DOW distribution: {dict(zip(dow_labels, dow_counts))}")

    # Population-level weekday vs weekend
    pop_analysis = _weekday_weekend_periodicity(records)

    # Per-patient analysis
    per_patient = _per_patient_dow_analysis(records)

    # Per-config comparison (all 3 configs)
    config_dow = {}
    CONFIGS = {
        'A_census_5g_30m':   {'min_carbs': 5.0,  'cluster_gap': 6},
        'B_medium_5g_90m':   {'min_carbs': 5.0,  'cluster_gap': 18},
        'C_therapy_18g_90m': {'min_carbs': 18.0, 'cluster_gap': 18},
    }
    for cfg_name, cfg in CONFIGS.items():
        cfg_records = _collect_meal_metabolic_records(
            patients, cfg['min_carbs'], cfg['cluster_gap'])
        config_dow[cfg_name] = _weekday_weekend_periodicity(cfg_records)
        wd = config_dow[cfg_name].get('weekday', {})
        we = config_dow[cfg_name].get('weekend', {})
        print(f"  {cfg_name}: WD entropy={wd.get('normalized_entropy', 'N/A')}, "
              f"WE entropy={we.get('normalized_entropy', 'N/A')}, "
              f"WD zone%={wd.get('zone_fraction_pct', 'N/A')}, "
              f"WE zone%={we.get('zone_fraction_pct', 'N/A')}")

    # Mealtime zone shift analysis
    zone_shifts = {}
    for zone_name in MEALTIME_ZONES:
        wd_zone = pop_analysis.get('weekday', {}).get('zones', {}).get(zone_name, {})
        we_zone = pop_analysis.get('weekend', {}).get('zones', {}).get(zone_name, {})
        if wd_zone.get('mean_hour') is not None and we_zone.get('mean_hour') is not None:
            zone_shifts[zone_name] = {
                'weekday_mean_hour': wd_zone['mean_hour'],
                'weekend_mean_hour': we_zone['mean_hour'],
                'shift_minutes': round((we_zone['mean_hour'] - wd_zone['mean_hour']) * 60, 0),
                'weekday_std': wd_zone.get('std_hour'),
                'weekend_std': we_zone.get('std_hour'),
            }

    # Day-of-week meal rate (per day, normalized by number of each DOW in dataset)
    # Approximate: ~26 weeks of data → ~26 of each DOW
    total_days = sum(len(p['df']) for p in patients) / (288 * len(patients))  # rough days
    weeks = total_days / 7
    dow_rate = {}
    for i, label in enumerate(dow_labels):
        dow_rate[label] = round(dow_counts[i] / max(weeks, 1), 2)

    return {
        'experiment': 'EXP-1565',
        'title': 'Weekday vs Weekend Meal Periodicity',
        'n_patients': len(patients),
        'n_meals': len(records),
        'dow_distribution': dict(zip(dow_labels, dow_counts)),
        'dow_meals_per_week': dow_rate,
        'population': pop_analysis,
        'per_patient': per_patient,
        'zone_shifts': zone_shifts,
        'config_comparison': {k: {kk: vv for kk, vv in v.items()}
                              for k, v in config_dow.items()},
        '_records': records,  # internal, for viz
    }


@register(1567, 'Within-Patient Meal Clock Regularity')
def exp_1567_within_patient_periodicity(patients):
    """Measure per-patient meal timing regularity: does each individual eat at
    consistent personal times?

    For each patient, identifies their personal "meal clock" — the typical
    hour they eat in each mealtime zone — and measures how tightly they
    adhere to it (std of hour). Also detects per-patient peaks via KDE
    and measures whether weekday/weekend regularity differs.

    Key question: Are individual patients periodic within ~2hr windows,
    even though population-level timing looks spread out?
    """
    records = _collect_meal_metabolic_records(patients, min_carbs=18.0, cluster_gap=18)
    print(f"  {len(records)} meals (therapy config)")

    pat_names = sorted(set(r['patient'] for r in records))
    per_patient = {}

    for pat in pat_names:
        pat_recs = [r for r in records if r['patient'] == pat]
        hours = np.array([r['hour_of_day'] for r in pat_recs])
        n_meals = len(pat_recs)

        reg = _compute_personal_regularity(hours)
        norm_entropy = reg['normalized_entropy']
        personal_peaks = reg['personal_peaks']
        weighted_std = reg['weighted_std']
        hist = reg['hour_histogram']

        # Per-zone analysis
        zone_regularity = {}
        for zone_name, (s, e) in MEALTIME_ZONES.items():
            zone_hours = [r['hour_of_day'] for r in pat_recs if s <= r['hour_of_day'] < e]
            if len(zone_hours) >= 3:
                zone_regularity[zone_name] = {
                    'n': len(zone_hours),
                    'mean_hour': round(float(np.mean(zone_hours)), 2),
                    'std_hour': round(float(np.std(zone_hours)), 2),
                    'within_3hr_pct': round(100 * sum(
                        1 for h in zone_hours if abs(h - np.mean(zone_hours)) <= 1.5
                    ) / len(zone_hours), 1),
                }
            else:
                zone_regularity[zone_name] = {'n': len(zone_hours)}

        # Weekday vs weekend regularity
        wd_hours = [r['hour_of_day'] for r in pat_recs if r.get('day_of_week', 0) < 5]
        we_hours = [r['hour_of_day'] for r in pat_recs if r.get('day_of_week', 0) >= 5]

        wd_regularity = {}
        we_regularity = {}
        for zone_name, (s, e) in MEALTIME_ZONES.items():
            wd_z = [h for h in wd_hours if s <= h < e]
            we_z = [h for h in we_hours if s <= h < e]
            if len(wd_z) >= 3:
                wd_regularity[zone_name] = {
                    'n': len(wd_z),
                    'mean_hour': round(float(np.mean(wd_z)), 2),
                    'std_hour': round(float(np.std(wd_z)), 2),
                }
            if len(we_z) >= 3:
                we_regularity[zone_name] = {
                    'n': len(we_z),
                    'mean_hour': round(float(np.mean(we_z)), 2),
                    'std_hour': round(float(np.std(we_z)), 2),
                }

        per_patient[pat] = {
            'n_meals': n_meals,
            'normalized_entropy': round(norm_entropy, 3),
            'n_personal_peaks': len(personal_peaks),
            'personal_peaks': personal_peaks,
            'weighted_mean_std': round(weighted_std, 2),
            'zone_regularity': zone_regularity,
            'weekday_zones': wd_regularity,
            'weekend_zones': we_regularity,
            'hour_histogram': [int(x) for x in hist],
        }

        print(f"    {pat}: {n_meals} meals, {len(personal_peaks)} peaks, "
              f"weighted_std={weighted_std:.2f}h, entropy={norm_entropy:.3f}")

    # Population summary: how much do patients differ?
    all_stds = [pp['weighted_mean_std'] for pp in per_patient.values()]
    all_entropies = [pp['normalized_entropy'] for pp in per_patient.values()]
    all_n_peaks = [pp['n_personal_peaks'] for pp in per_patient.values()]

    # Per-zone inter-patient variation
    zone_variation = {}
    for zone_name in MEALTIME_ZONES:
        zone_means = []
        zone_stds = []
        for pat, pp in per_patient.items():
            zr = pp['zone_regularity'].get(zone_name, {})
            if zr.get('n', 0) >= 3:
                zone_means.append(zr['mean_hour'])
                zone_stds.append(zr['std_hour'])
        if zone_means:
            zone_variation[zone_name] = {
                'n_patients_with_data': len(zone_means),
                'inter_patient_std_of_mean_hour': round(float(np.std(zone_means)), 2),
                'mean_within_patient_std': round(float(np.mean(zone_stds)), 2),
                'range_of_mean_hours': f"{min(zone_means):.1f}-{max(zone_means):.1f}",
            }

    # Weekday vs weekend regularity comparison across patients
    wd_we_comparison = []
    for pat in pat_names:
        pp = per_patient[pat]
        for zone_name in MEALTIME_ZONES:
            wd_z = pp['weekday_zones'].get(zone_name, {})
            we_z = pp['weekend_zones'].get(zone_name, {})
            if wd_z.get('n', 0) >= 3 and we_z.get('n', 0) >= 3:
                wd_we_comparison.append({
                    'patient': pat,
                    'zone': zone_name,
                    'wd_std': wd_z['std_hour'],
                    'we_std': we_z['std_hour'],
                    'std_delta': round(we_z['std_hour'] - wd_z['std_hour'], 2),
                    'wd_mean': wd_z['mean_hour'],
                    'we_mean': we_z['mean_hour'],
                    'mean_shift': round(we_z['mean_hour'] - wd_z['mean_hour'], 2),
                })

    # Fraction of patients where weekends are LESS regular (higher std)
    if wd_we_comparison:
        weekend_less_regular = sum(1 for x in wd_we_comparison if x['std_delta'] > 0)
        pct_less_regular = round(100 * weekend_less_regular / len(wd_we_comparison), 1)
    else:
        pct_less_regular = None

    return {
        'experiment': 'EXP-1567',
        'title': 'Within-Patient Meal Clock Regularity',
        'n_patients': len(patients),
        'n_meals': len(records),
        'per_patient': per_patient,
        'population_summary': {
            'mean_weighted_std': round(float(np.mean(all_stds)), 2),
            'std_weighted_std': round(float(np.std(all_stds)), 2),
            'range_weighted_std': f"{min(all_stds):.2f}-{max(all_stds):.2f}",
            'mean_entropy': round(float(np.mean(all_entropies)), 3),
            'mean_n_peaks': round(float(np.mean(all_n_peaks)), 1),
        },
        'zone_variation': zone_variation,
        'wd_we_regularity_comparison': wd_we_comparison,
        'pct_weekend_less_regular': pct_less_regular,
    }


@register(1569, 'Detection Sensitivity Benchmark')
def exp_1569_detection_benchmark(patients):
    """Systematic sweep of meal detection parameters to benchmark their effect
    on meals/day, size distribution, within-patient regularity, and metabolic
    signal quality.

    Grid: 9 min_carb_g × 8 hysteresis_min = 72 configs × 11 patients.

    Hypotheses:
      H1: Regularity (weighted_std) monotonically decreases with strictness
      H2: Diminishing returns — a knee in regularity-vs-count
      H3: Clock-like patients are threshold-robust
      H4: Hysteresis merges (conserves carbs); min_carb filters (drops carbs)
      H5: meals/day × mean_size approx conserved under hysteresis
    """
    MIN_CARB_VALUES = [0, 3, 5, 10, 15, 18, 25, 30, 40]
    HYSTERESIS_VALUES = [15, 30, 45, 60, 90, 120, 150, 180]  # minutes

    grid = []
    total = len(MIN_CARB_VALUES) * len(HYSTERESIS_VALUES)
    done = 0
    for mc in MIN_CARB_VALUES:
        for hyst in HYSTERESIS_VALUES:
            cluster_gap = max(1, hyst // 5)  # convert minutes to 5-min steps
            done += 1
            if done % 12 == 0 or done == 1:
                print(f"    Config {done}/{total}: min_carb={mc}g, hysteresis={hyst}min")

            records = _collect_meal_metabolic_records(
                patients, min_carbs=float(mc), cluster_gap=cluster_gap)

            n_meals = len(records)
            days_total = sum(len(p['df']) / STEPS_PER_DAY for p in patients)

            # Size distribution
            carbs_list = [r['carbs_g'] for r in records]
            if carbs_list:
                carbs_arr = np.array(carbs_list)
                size_stats = {
                    'mean': round(float(np.mean(carbs_arr)), 1),
                    'median': round(float(np.median(carbs_arr)), 1),
                    'p25': round(float(np.percentile(carbs_arr, 25)), 1),
                    'p75': round(float(np.percentile(carbs_arr, 75)), 1),
                    'total_carbs_per_day': round(float(np.sum(carbs_arr)) / days_total, 1),
                }
            else:
                size_stats = {'mean': 0, 'median': 0, 'p25': 0, 'p75': 0,
                              'total_carbs_per_day': 0}

            # Per-patient regularity using shared helper
            pat_names = sorted(set(r['patient'] for r in records))
            pat_regularity = {}
            pat_meals_per_day = {}
            for pat in pat_names:
                pat_recs = [r for r in records if r['patient'] == pat]
                pat_days = len([p for p in patients if p['name'] == pat][0]['df']) / STEPS_PER_DAY
                hours = np.array([r['hour_of_day'] for r in pat_recs])
                reg = _compute_personal_regularity(hours)
                pat_regularity[pat] = {
                    'n_meals': len(pat_recs),
                    'meals_per_day': round(len(pat_recs) / pat_days, 2),
                    'weighted_std': reg['weighted_std'],
                    'n_peaks': reg['n_peaks'],
                    'normalized_entropy': reg['normalized_entropy'],
                }
                pat_meals_per_day[pat] = len(pat_recs) / pat_days

            # Population regularity (all meals pooled)
            all_hours = np.array([r['hour_of_day'] for r in records])
            pop_reg = _compute_personal_regularity(all_hours) if n_meals > 0 else {
                'weighted_std': float('nan'), 'normalized_entropy': float('nan'), 'n_peaks': 0}

            # Population periodicity (zone-based)
            periodicity = _mealtime_periodicity(records, patients) if n_meals > 0 else {}

            # Metabolic quality
            if records:
                isf_norms = [r['isf_norm_excursion'] for r in records]
                spec_powers = [r['spectral_power_per_hour'] for r in records]
                metabolic = {
                    'mean_isf_norm': round(float(np.mean(isf_norms)), 3),
                    'median_isf_norm': round(float(np.median(isf_norms)), 3),
                    'mean_spectral_power': round(float(np.mean(spec_powers)), 2),
                }
            else:
                metabolic = {'mean_isf_norm': 0, 'median_isf_norm': 0,
                             'mean_spectral_power': 0}

            # Per-patient weighted_std list for robustness analysis
            pat_stds = [v['weighted_std'] for v in pat_regularity.values()
                        if not np.isnan(v['weighted_std'])]

            grid.append({
                'min_carb_g': mc,
                'hysteresis_min': hyst,
                'cluster_gap': cluster_gap,
                'n_meals': n_meals,
                'meals_per_day': round(n_meals / days_total, 2),
                'size': size_stats,
                'pop_weighted_std': pop_reg['weighted_std'],
                'pop_entropy': pop_reg['normalized_entropy'],
                'pop_n_peaks': pop_reg['n_peaks'],
                'zone_fraction_pct': periodicity.get('zone_fraction_pct', 0),
                'metabolic': metabolic,
                'mean_patient_std': round(float(np.mean(pat_stds)), 3) if pat_stds else float('nan'),
                'std_patient_std': round(float(np.std(pat_stds)), 3) if pat_stds else float('nan'),
                'per_patient': pat_regularity,
            })

    # Hypothesis testing summaries
    # H1: Regularity vs strictness — compute Spearman correlation
    from scipy.stats import spearmanr
    strictness = [g['min_carb_g'] + g['hysteresis_min'] / 10 for g in grid]
    reg_vals = [g['mean_patient_std'] for g in grid]
    valid = [(s, r) for s, r in zip(strictness, reg_vals) if not np.isnan(r)]
    if len(valid) >= 3:
        s_arr, r_arr = zip(*valid)
        h1_rho, h1_p = spearmanr(s_arr, r_arr)
    else:
        h1_rho, h1_p = float('nan'), float('nan')

    # H2: Find knee — largest drop in mean_patient_std per unit meals_per_day lost
    sorted_by_mpd = sorted([g for g in grid if not np.isnan(g['mean_patient_std'])],
                           key=lambda g: -g['meals_per_day'])
    knee_idx = None
    best_ratio = 0
    for i in range(1, len(sorted_by_mpd)):
        d_std = sorted_by_mpd[i-1]['mean_patient_std'] - sorted_by_mpd[i]['mean_patient_std']
        d_mpd = sorted_by_mpd[i-1]['meals_per_day'] - sorted_by_mpd[i]['meals_per_day']
        if d_mpd > 0 and d_std > 0:
            ratio = d_std / d_mpd
            if ratio > best_ratio:
                best_ratio = ratio
                knee_idx = i

    knee_config = None
    if knee_idx is not None:
        k = sorted_by_mpd[knee_idx]
        knee_config = {
            'min_carb_g': k['min_carb_g'],
            'hysteresis_min': k['hysteresis_min'],
            'meals_per_day': k['meals_per_day'],
            'mean_patient_std': k['mean_patient_std'],
            'efficiency_ratio': round(best_ratio, 4),
        }

    # H3: Per-patient robustness — std of each patient's std across all configs
    all_pats = sorted(set(p for g in grid for p in g['per_patient']))
    pat_robustness = {}
    for pat in all_pats:
        stds_across = [g['per_patient'][pat]['weighted_std']
                       for g in grid if pat in g['per_patient']
                       and not np.isnan(g['per_patient'][pat]['weighted_std'])]
        if stds_across:
            pat_robustness[pat] = {
                'mean_std': round(float(np.mean(stds_across)), 3),
                'std_of_std': round(float(np.std(stds_across)), 3),
                'range': f"{min(stds_across):.2f}-{max(stds_across):.2f}",
                'n_configs': len(stds_across),
            }

    # H4/H5: Carbs conservation — compare total_carbs_per_day across hysteresis at fixed min_carb
    carb_conservation = {}
    for mc in MIN_CARB_VALUES:
        mc_configs = [g for g in grid if g['min_carb_g'] == mc]
        cpd = [g['size']['total_carbs_per_day'] for g in mc_configs]
        if cpd:
            carb_conservation[str(mc)] = {
                'mean_cpd': round(float(np.mean(cpd)), 1),
                'std_cpd': round(float(np.std(cpd)), 1),
                'range': f"{min(cpd):.1f}-{max(cpd):.1f}",
                'cv_pct': round(100 * float(np.std(cpd)) / max(float(np.mean(cpd)), 0.01), 1),
            }

    print(f"\n  Sweep complete: {len(grid)} configs")
    print(f"  H1 regularity-strictness: rho={h1_rho:.3f}, p={h1_p:.4f}")
    if knee_config:
        print(f"  H2 knee: min_carb={knee_config['min_carb_g']}g, "
              f"hyst={knee_config['hysteresis_min']}min, "
              f"mpd={knee_config['meals_per_day']}, std={knee_config['mean_patient_std']}")
    print(f"  H3 robustness (std_of_std): "
          + ", ".join(f"{p}={v['std_of_std']}" for p, v in sorted(pat_robustness.items())))

    return {
        'experiment': 'EXP-1569',
        'title': 'Detection Sensitivity Benchmark',
        'min_carb_values': MIN_CARB_VALUES,
        'hysteresis_values': HYSTERESIS_VALUES,
        'n_configs': len(grid),
        'n_patients': len(patients),
        '_grid': grid,  # stripped before JSON save
        'hypothesis_tests': {
            'H1_regularity_vs_strictness': {
                'spearman_rho': round(h1_rho, 4) if not np.isnan(h1_rho) else None,
                'p_value': round(h1_p, 6) if not np.isnan(h1_p) else None,
                'direction': 'negative' if h1_rho < 0 else 'positive',
                'interpretation': 'Stricter detection → lower weighted_std (more regular)'
                                  if h1_rho < 0 else 'No clear monotonic relationship',
            },
            'H2_knee_config': knee_config,
            'H3_patient_robustness': pat_robustness,
            'H4_H5_carb_conservation': carb_conservation,
        },
        'grid_summary': [{
            'min_carb_g': g['min_carb_g'],
            'hysteresis_min': g['hysteresis_min'],
            'n_meals': g['n_meals'],
            'meals_per_day': g['meals_per_day'],
            'mean_carbs': g['size']['mean'],
            'median_carbs': g['size']['median'],
            'total_carbs_per_day': g['size']['total_carbs_per_day'],
            'mean_patient_std': g['mean_patient_std'],
            'pop_entropy': g['pop_entropy'],
            'zone_fraction_pct': g['zone_fraction_pct'],
            'mean_isf_norm': g['metabolic']['mean_isf_norm'],
            'mean_spectral_power': g['metabolic']['mean_spectral_power'],
        } for g in grid],
    }


_CACHED_EXPERIMENTS = None



@register(1571, 'Robustness Archetype Characterization')
def exp_1571_robustness_archetypes(patients):
    """Characterize the distribution of meal-clock robustness across patients.

    Robustness = σσ (std of weighted_std across 72 detection configs from EXP-1569).
    Low σσ means a patient's measured regularity is stable regardless of detection
    parameters.  High σσ means regularity is an artifact of the config chosen.

    This experiment:
      1. Runs the EXP-1569 sweep (or reuses cached data)
      2. Computes archetype tiers from σσ distribution
      3. Correlates robustness with n_peaks, meals/day, zone regularity, metabolic metrics
      4. Characterizes each tier: what makes a patient robust?
      5. Builds per-patient stability curves (regularity vs config strictness)
    """
    from scipy.stats import spearmanr

    # Run the 1569 sweep to get the grid
    _, exp_1569_fn = EXPERIMENTS[1569]
    result_1569 = exp_1569_fn(patients)
    grid = result_1569['_grid']
    h3 = result_1569['hypothesis_tests']['H3_patient_robustness']

    # Also run 1567 for per-patient zone regularity
    _, exp_1567_fn = EXPERIMENTS[1567]
    result_1567 = exp_1567_fn(patients)
    pp_1567 = result_1567['per_patient']

    all_pats = sorted(h3.keys())

    # --- Tier classification ---
    # Use natural breaks: robust < 0.6, moderate 0.6-1.0, sensitive >= 1.0
    TIERS = {'robust': (0, 0.6), 'moderate': (0.6, 1.0), 'sensitive': (1.0, float('inf'))}
    tier_members = {t: [] for t in TIERS}
    pat_tier = {}
    for pat in all_pats:
        ss = h3[pat]['std_of_std']
        for tier_name, (lo, hi) in TIERS.items():
            if lo <= ss < hi:
                tier_members[tier_name].append(pat)
                pat_tier[pat] = tier_name
                break

    # --- Per-patient profile ---
    # Gather traits for correlation analysis
    traits = {}
    for pat in all_pats:
        rob = h3[pat]
        pp = pp_1567.get(pat, {})
        # Therapy config metrics from grid
        therapy_g = [g for g in grid if g['min_carb_g'] == 18 and g['hysteresis_min'] == 90
                     and pat in g['per_patient']]
        t_mpd = therapy_g[0]['per_patient'][pat]['meals_per_day'] if therapy_g else 0

        # Census config metrics
        census_g = [g for g in grid if g['min_carb_g'] == 5 and g['hysteresis_min'] == 30
                    and pat in g['per_patient']]
        c_mpd = census_g[0]['per_patient'][pat]['meals_per_day'] if census_g else 0

        # Zone coverage: how many zones have ≥3 meals?
        zr = pp.get('zone_regularity', {})
        zones_covered = sum(1 for z in zr.values() if z.get('n', 0) >= 3)

        # Mean within-zone std
        zone_stds = [z['std_hour'] for z in zr.values() if z.get('std_hour') is not None]
        mean_zone_std = float(np.mean(zone_stds)) if zone_stds else float('nan')

        traits[pat] = {
            'tier': pat_tier[pat],
            'sigma_sigma': rob['std_of_std'],
            'mean_std': rob['mean_std'],
            'range': rob['range'],
            'n_peaks': pp.get('n_personal_peaks', 0),
            'normalized_entropy': pp.get('normalized_entropy', float('nan')),
            'therapy_mpd': t_mpd,
            'census_mpd': c_mpd,
            'mpd_ratio': round(t_mpd / max(c_mpd, 0.01), 2),
            'zones_covered': zones_covered,
            'mean_zone_std': round(mean_zone_std, 3) if not np.isnan(mean_zone_std) else None,
            'n_meals_therapy': pp.get('n_meals', 0),
        }

    # --- Correlation matrix ---
    numeric_keys = ['sigma_sigma', 'mean_std', 'n_peaks', 'therapy_mpd',
                    'census_mpd', 'zones_covered', 'normalized_entropy']
    correlations = {}
    for key in numeric_keys:
        if key == 'sigma_sigma':
            continue
        vals = [(traits[p]['sigma_sigma'], traits[p][key]) for p in all_pats
                if not np.isnan(traits[p].get(key, float('nan')))]
        if len(vals) >= 4:
            ss_arr, v_arr = zip(*vals)
            rho, pval = spearmanr(ss_arr, v_arr)
            correlations[key] = {
                'spearman_rho': round(rho, 3),
                'p_value': round(pval, 4),
                'significant': pval < 0.05,
            }

    # --- Stability curves: per-patient regularity vs aggregate strictness ---
    # For each patient, extract (strictness, weighted_std) across all 72 configs
    stability_curves = {}
    for pat in all_pats:
        curve = []
        for g in grid:
            if pat in g['per_patient']:
                pp = g['per_patient'][pat]
                strictness = g['min_carb_g'] + g['hysteresis_min'] / 10.0
                curve.append({
                    'min_carb_g': g['min_carb_g'],
                    'hysteresis_min': g['hysteresis_min'],
                    'strictness': round(strictness, 1),
                    'weighted_std': pp['weighted_std'],
                    'meals_per_day': pp['meals_per_day'],
                    'n_peaks': pp['n_peaks'],
                })
        stability_curves[pat] = sorted(curve, key=lambda x: x['strictness'])

    # --- Tier summaries ---
    tier_summaries = {}
    for tier_name, members in tier_members.items():
        if not members:
            tier_summaries[tier_name] = {'n': 0}
            continue
        tier_traits = [traits[p] for p in members]
        tier_summaries[tier_name] = {
            'n': len(members),
            'members': members,
            'mean_sigma_sigma': round(float(np.mean([t['sigma_sigma'] for t in tier_traits])), 3),
            'mean_n_peaks': round(float(np.mean([t['n_peaks'] for t in tier_traits])), 1),
            'mean_therapy_mpd': round(float(np.mean([t['therapy_mpd'] for t in tier_traits])), 2),
            'mean_zones_covered': round(float(np.mean([t['zones_covered'] for t in tier_traits])), 1),
            'mean_mean_std': round(float(np.mean([t['mean_std'] for t in tier_traits])), 2),
        }

    # Print summary
    print(f"\n  Robustness Tiers:")
    for tier_name, ts in tier_summaries.items():
        if ts['n'] > 0:
            print(f"    {tier_name.upper()} (n={ts['n']}): σσ={ts['mean_sigma_sigma']:.3f}, "
                  f"peaks={ts['mean_n_peaks']:.1f}, mpd={ts['mean_therapy_mpd']:.2f}, "
                  f"zones={ts['mean_zones_covered']:.1f}")
    print(f"\n  Key correlations with σσ:")
    for key, c in sorted(correlations.items(), key=lambda x: abs(x[1]['spearman_rho']), reverse=True):
        sig = '***' if c['p_value'] < 0.01 else '**' if c['p_value'] < 0.05 else ''
        print(f"    {key:25s}: ρ={c['spearman_rho']:+.3f}, p={c['p_value']:.4f} {sig}")

    return {
        'experiment': 'EXP-1571',
        'title': 'Robustness Archetype Characterization',
        'n_patients': len(all_pats),
        'tier_thresholds': {t: {'lo': lo, 'hi': hi} for t, (lo, hi) in TIERS.items()},
        'tier_summaries': tier_summaries,
        'per_patient': traits,
        'correlations_with_sigma_sigma': correlations,
        '_stability_curves': stability_curves,  # stripped before save
    }


def _run_all_detectors(patients):
    global _CACHED_EXPERIMENTS
    if _CACHED_EXPERIMENTS is not None:
        return _CACHED_EXPERIMENTS

    all_experiments = []
    for pat in patients:
        name = pat['name']
        df = pat['df']
        bg = _bg(df)
        bolus = np.nan_to_num(df['bolus'].values.astype(np.float64), nan=0.0)
        carbs_arr = np.nan_to_num(df['carbs'].values.astype(np.float64), nan=0.0)
        sd = compute_supply_demand(df, pat['pk'])

        all_experiments.extend(detect_fasting_windows(name, df, bg, bolus, carbs_arr))
        all_experiments.extend(detect_overnight_windows(name, df, bg, bolus, carbs_arr))
        all_experiments.extend(detect_meal_windows(name, df, bg, bolus, carbs_arr, sd))
        all_experiments.extend(detect_correction_windows(name, df, bg, bolus, carbs_arr))
        all_experiments.extend(detect_uam_windows(name, df, bg, carbs_arr, sd))
        all_experiments.extend(detect_dawn_windows(name, df, bg, carbs_arr, bolus))
        all_experiments.extend(detect_exercise_windows(name, df, bg, bolus, carbs_arr, sd))
        all_experiments.extend(detect_aid_response_windows(name, df, bg))
        all_experiments.extend(detect_stable_windows(name, df, bg, bolus, carbs_arr))

    _CACHED_EXPERIMENTS = all_experiments
    return all_experiments


def _simple_kmeans(X, k, max_iter=50):
    """Minimal k-means without sklearn."""
    n = len(X)
    # Initialize with first k points spread evenly
    indices = np.linspace(0, n - 1, k, dtype=int)
    centers = X[indices].copy()
    labels = np.zeros(n, dtype=int)

    for _ in range(max_iter):
        # Assign
        for i in range(n):
            dists = [np.sum((X[i] - centers[j]) ** 2) for j in range(k)]
            labels[i] = np.argmin(dists)
        # Update
        new_centers = np.zeros_like(centers)
        for j in range(k):
            members = X[labels == j]
            if len(members) > 0:
                new_centers[j] = members.mean(axis=0)
            else:
                new_centers[j] = centers[j]
        if np.allclose(centers, new_centers):
            break
        centers = new_centers
    return labels


# ---------------------------------------------------------------------------
# Visualization
# ---------------------------------------------------------------------------

def generate_visualizations(results, patients):
    """Generate all figures for the report."""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import matplotlib.gridspec as gridspec
    except ImportError:
        print("  matplotlib not available — skipping visualizations")
        return

    os.makedirs(str(VIZ_DIR), exist_ok=True)

    # Load all experiments for viz
    all_experiments = _run_all_detectors(patients)

    # ── Fig 1: Census bar chart (type × patient heatmap) ──
    _viz_census_heatmap(all_experiments, patients, plt)

    # ── Fig 2: Time-of-day distributions ──
    _viz_time_of_day(all_experiments, plt)

    # ── Fig 3: Duration distributions ──
    _viz_duration_distributions(all_experiments, plt)

    # ── Fig 4: Quality distribution ──
    _viz_quality_distributions(all_experiments, plt)

    # ── Fig 5: Cross-correlation matrix ──
    if 1554 in results:
        _viz_correlations(results[1554], plt)

    # ── Fig 6: Templates ──
    if 1557 in results:
        _viz_templates(results[1557], plt)

    # ── Fig 7: Patient archetype radar ──
    if 1556 in results:
        _viz_archetypes(results[1556], plt)

    print(f"\n  Visualizations saved to {VIZ_DIR}")


def _viz_census_heatmap(all_experiments, patients, plt):
    etypes = ['fasting', 'overnight', 'meal', 'correction', 'uam',
              'dawn', 'exercise', 'aid_response', 'stable']
    pnames = [p['name'] for p in patients]

    matrix = np.zeros((len(pnames), len(etypes)))
    for e in all_experiments:
        pi = pnames.index(e.patient) if e.patient in pnames else -1
        ti = etypes.index(e.exp_type) if e.exp_type in etypes else -1
        if pi >= 0 and ti >= 0:
            n_days = max(len(patients[pi]['df']) / STEPS_PER_DAY, 1)
            matrix[pi, ti] += 1.0 / n_days  # per-day rate

    fig, ax = plt.subplots(figsize=(12, 6))
    im = ax.imshow(matrix, aspect='auto', cmap='YlOrRd')
    ax.set_xticks(range(len(etypes)))
    ax.set_xticklabels(etypes, rotation=45, ha='right')
    ax.set_yticks(range(len(pnames)))
    ax.set_yticklabels(pnames)
    ax.set_xlabel('Natural Experiment Type')
    ax.set_ylabel('Patient')
    ax.set_title('Natural Experiment Yield (events/day)')
    plt.colorbar(im, ax=ax, label='Events/day')

    # Annotate cells
    for i in range(len(pnames)):
        for j in range(len(etypes)):
            val = matrix[i, j]
            color = 'white' if val > matrix.max() * 0.6 else 'black'
            ax.text(j, i, f'{val:.1f}', ha='center', va='center',
                    fontsize=7, color=color)

    plt.tight_layout()
    plt.savefig(str(VIZ_DIR / 'fig1_census_heatmap.png'), dpi=150)
    plt.close()
    print("    ✓ fig1_census_heatmap.png")


def _viz_time_of_day(all_experiments, plt):
    etypes = ['fasting', 'meal', 'correction', 'uam', 'exercise', 'stable']
    fig, axes = plt.subplots(2, 3, figsize=(15, 8))
    axes = axes.ravel()

    for i, etype in enumerate(etypes):
        subset = [e for e in all_experiments if e.exp_type == etype]
        if not subset:
            axes[i].set_title(f'{etype} (n=0)')
            continue
        hours = [e.hour_of_day for e in subset]
        axes[i].hist(hours, bins=48, range=(0, 24), alpha=0.7, color='steelblue',
                     edgecolor='white', linewidth=0.3)
        axes[i].set_title(f'{etype} (n={len(subset)})')
        axes[i].set_xlabel('Hour of Day')
        axes[i].set_ylabel('Count')
        axes[i].set_xlim(0, 24)
        axes[i].axvspan(0, 6, alpha=0.1, color='navy', label='Overnight')
        axes[i].axvspan(6, 9, alpha=0.1, color='orange', label='Morning')

    plt.suptitle('Natural Experiment Time-of-Day Distributions', fontsize=14)
    plt.tight_layout()
    plt.savefig(str(VIZ_DIR / 'fig2_time_of_day.png'), dpi=150)
    plt.close()
    print("    ✓ fig2_time_of_day.png")


def _viz_duration_distributions(all_experiments, plt):
    etypes = ['fasting', 'overnight', 'meal', 'correction', 'uam',
              'exercise', 'aid_response', 'stable']
    fig, axes = plt.subplots(2, 4, figsize=(16, 8))
    axes = axes.ravel()

    for i, etype in enumerate(etypes):
        subset = [e for e in all_experiments if e.exp_type == etype]
        if not subset:
            axes[i].set_title(f'{etype} (n=0)')
            continue
        durations = [e.duration_minutes for e in subset]
        axes[i].hist(durations, bins=30, alpha=0.7, color='coral',
                     edgecolor='white', linewidth=0.3)
        axes[i].axvline(np.median(durations), color='red', ls='--',
                        label=f'median={np.median(durations):.0f}m')
        axes[i].set_title(f'{etype} (n={len(subset)})')
        axes[i].set_xlabel('Duration (min)')
        axes[i].legend(fontsize=8)

    plt.suptitle('Natural Experiment Duration Distributions', fontsize=14)
    plt.tight_layout()
    plt.savefig(str(VIZ_DIR / 'fig3_duration_distributions.png'), dpi=150)
    plt.close()
    print("    ✓ fig3_duration_distributions.png")


def _viz_quality_distributions(all_experiments, plt):
    etypes = ['fasting', 'overnight', 'meal', 'correction', 'uam',
              'dawn', 'exercise', 'aid_response', 'stable']
    fig, ax = plt.subplots(figsize=(10, 6))

    data = []
    labels = []
    for etype in etypes:
        subset = [e.quality for e in all_experiments if e.exp_type == etype]
        if subset:
            data.append(subset)
            labels.append(f'{etype}\n(n={len(subset)})')

    bp = ax.boxplot(data, labels=labels, patch_artist=True)
    colors = ['#4C72B0', '#55A868', '#C44E52', '#8172B2', '#CCB974',
              '#64B5CD', '#DD8452', '#A1C9F4', '#8DE5A1']
    for patch, color in zip(bp['boxes'], colors[:len(data)]):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)

    ax.axhline(0.6, color='green', ls='--', alpha=0.5, label='Good threshold')
    ax.axhline(0.4, color='orange', ls='--', alpha=0.5, label='Acceptable threshold')
    ax.set_ylabel('Quality Score')
    ax.set_title('Window Quality Distribution by Type')
    ax.legend()
    plt.tight_layout()
    plt.savefig(str(VIZ_DIR / 'fig4_quality_distributions.png'), dpi=150)
    plt.close()
    print("    ✓ fig4_quality_distributions.png")


def _viz_correlations(result, plt):
    corr = result.get('correlation_matrix', {})
    metrics = ['overnight_drift', 'mean_isf', 'mean_excursion',
               'uam_per_day', 'exercise_per_day', 'mean_dawn_effect']
    n = len(metrics)
    mat = np.zeros((n, n))
    for i, k1 in enumerate(metrics):
        for j, k2 in enumerate(metrics):
            key = f'{k1}_vs_{k2}'
            mat[i, j] = corr.get(key, 0)

    fig, ax = plt.subplots(figsize=(8, 7))
    im = ax.imshow(mat, cmap='RdBu_r', vmin=-1, vmax=1)
    short_labels = ['ON drift', 'ISF', 'Excursion', 'UAM/day', 'Exercise/day', 'Dawn']
    ax.set_xticks(range(n))
    ax.set_xticklabels(short_labels, rotation=45, ha='right')
    ax.set_yticks(range(n))
    ax.set_yticklabels(short_labels)
    for i in range(n):
        for j in range(n):
            ax.text(j, i, f'{mat[i,j]:.2f}', ha='center', va='center', fontsize=9)
    plt.colorbar(im, ax=ax, label='Pearson r')
    ax.set_title('Cross-Experiment Metric Correlations (n=11 patients)')
    plt.tight_layout()
    plt.savefig(str(VIZ_DIR / 'fig5_cross_correlations.png'), dpi=150)
    plt.close()
    print("    ✓ fig5_cross_correlations.png")


def _viz_templates(result, plt):
    templates = result.get('templates', {})
    etypes = [k for k in ['meal', 'correction', 'fasting', 'uam', 'overnight']
              if k in templates and templates[k].get('median')]

    fig, axes = plt.subplots(1, len(etypes), figsize=(5 * len(etypes), 5))
    if len(etypes) == 1:
        axes = [axes]

    for i, etype in enumerate(etypes):
        t = templates[etype]
        time_min = t['time_axis_min']
        median = np.array([v if v is not None else np.nan for v in t['median']])
        p25 = np.array([v if v is not None else np.nan for v in t['p25']])
        p75 = np.array([v if v is not None else np.nan for v in t['p75']])

        axes[i].plot(time_min, median, 'b-', lw=2, label='Median')
        axes[i].fill_between(time_min, p25, p75, alpha=0.2, color='blue', label='IQR')
        axes[i].axhline(0, color='gray', ls='--', alpha=0.5)
        axes[i].set_title(f'{etype} (n={t["n"]})')
        axes[i].set_xlabel('Time (min)')
        axes[i].set_ylabel('ΔGlucose (mg/dL)')
        axes[i].legend(fontsize=8)

    plt.suptitle('Canonical Glucose Templates by Natural Experiment Type', fontsize=14)
    plt.tight_layout()
    plt.savefig(str(VIZ_DIR / 'fig6_templates.png'), dpi=150)
    plt.close()
    print("    ✓ fig6_templates.png")


def _viz_archetypes(result, plt):
    profiles = result.get('patient_profiles', {})
    etypes = ['fasting', 'overnight', 'meal', 'correction', 'uam',
              'dawn', 'exercise', 'aid_response', 'stable']

    fig, ax = plt.subplots(figsize=(12, 6))
    pnames = sorted(profiles.keys())
    n_types = len(etypes)
    x = np.arange(len(pnames))
    width = 0.8 / n_types

    colors = ['#4C72B0', '#55A868', '#C44E52', '#8172B2', '#CCB974',
              '#64B5CD', '#DD8452', '#A1C9F4', '#8DE5A1']
    for j, etype in enumerate(etypes):
        vals = [profiles[p]['rates_per_day'].get(etype, 0) for p in pnames]
        ax.bar(x + j * width, vals, width, label=etype, color=colors[j % len(colors)],
               alpha=0.8)

    ax.set_xticks(x + width * n_types / 2)
    ax.set_xticklabels(pnames)
    ax.set_xlabel('Patient')
    ax.set_ylabel('Events/Day')
    ax.set_title('Natural Experiment Yield Profile by Patient')
    ax.legend(loc='upper left', fontsize=7, ncol=3)
    plt.tight_layout()
    plt.savefig(str(VIZ_DIR / 'fig7_patient_profiles.png'), dpi=150)
    plt.close()
    print("    ✓ fig7_patient_profiles.png")


def generate_sensitivity_visualizations(results):
    """Generate visualizations for EXP-1559 meal detection sensitivity."""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        print("  matplotlib not available — skipping sensitivity visualizations")
        return

    if 1559 not in results:
        return

    d = results[1559]
    configs = d['configs']
    cfg_names = list(configs.keys())
    cfg_labels = ['≥5g / 30min', '≥5g / 90min', '≥18g / 90min']
    colors = ['#4C72B0', '#55A868', '#C44E52']

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle('EXP-1559: Meal Detection Sensitivity Analysis', fontsize=14, fontweight='bold')

    # --- Panel A: Meal counts per patient ---
    ax = axes[0, 0]
    pnames = sorted(configs[cfg_names[0]]['per_patient'].keys())
    x = np.arange(len(pnames))
    width = 0.25
    for j, (cn, lbl) in enumerate(zip(cfg_names, cfg_labels)):
        counts = [configs[cn]['per_patient'][p]['per_day'] for p in pnames]
        ax.bar(x + j * width, counts, width, label=lbl, color=colors[j], alpha=0.85)
    ax.set_xticks(x + width)
    ax.set_xticklabels(pnames)
    ax.set_xlabel('Patient')
    ax.set_ylabel('Meals / Day')
    ax.set_title('A) Daily Meal Rate by Config')
    ax.legend(fontsize=8)

    # --- Panel B: Quality comparison ---
    ax = axes[0, 1]
    qual_data = []
    for cn in cfg_names:
        qual_data.append(configs[cn]['population']['mean_quality'])
    bars = ax.bar(cfg_labels, qual_data, color=colors, alpha=0.85)
    ax.set_ylabel('Mean Quality Score')
    ax.set_title('B) Population Quality by Config')
    ax.set_ylim(0.8, 1.0)
    for bar, val in zip(bars, qual_data):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.003,
                f'{val:.3f}', ha='center', fontsize=10)

    # Grade breakdown stacked
    ax2 = ax.twinx()
    grade_order = ['excellent', 'good', 'acceptable', 'poor']
    grade_colors = ['#2ca02c', '#ffbb78', '#ff7f0e', '#d62728']
    bottom = np.zeros(3)
    for gi, grade in enumerate(grade_order):
        vals = [configs[cn]['population']['grade_pcts'].get(grade, 0) for cn in cfg_names]
        ax2.bar(cfg_labels, vals, bottom=bottom, color=grade_colors[gi], alpha=0.3,
                width=0.3, label=grade)
        bottom += np.array(vals)
    ax2.set_ylabel('Grade %')
    ax2.set_ylim(0, 110)
    ax2.legend(fontsize=7, loc='upper right')

    # --- Panel C: Excursion by carb range ---
    ax = axes[1, 0]
    carb_ranges = ['<10g', '10-19g', '20-29g', '30-49g', '≥50g']
    for j, (cn, lbl) in enumerate(zip(cfg_names, cfg_labels)):
        exc_data = configs[cn].get('excursion_by_carb_range', {})
        medians = []
        xpos = []
        for ri, rng in enumerate(carb_ranges):
            if rng in exc_data:
                medians.append(exc_data[rng]['median'])
                xpos.append(ri)
        if medians:
            ax.plot(xpos, medians, 'o-', color=colors[j], label=lbl, markersize=6)
    ax.set_xticks(range(len(carb_ranges)))
    ax.set_xticklabels(carb_ranges, fontsize=9)
    ax.set_xlabel('Carb Range')
    ax.set_ylabel('Median Excursion (mg/dL)')
    ax.set_title('C) Excursion by Carb Range')
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    # --- Panel D: Population summary table ---
    ax = axes[1, 1]
    ax.axis('off')
    rows = []
    row_labels = ['Total Meals', 'Meals/Day (pop)', 'Mean Carbs (g)',
                  'Mean Excursion', 'Mean Quality', '% Announced',
                  'Mean Peak Time']
    for cn in cfg_names:
        c = configs[cn]
        p = c['population']
        total_days = sum(len(pat['df']) for pat in []) if False else 0  # placeholder
        rows_data = [
            f"{c['total_meals']:,}",
            f"{p['mean_carbs_g']:.0f}",  # use carbs as proxy
            f"{p['mean_carbs_g']:.1f}",
            f"{p['mean_excursion']:.1f}",
            f"{p['mean_quality']:.3f}",
            f"{p['pct_announced']:.0f}%",
            f"{p['mean_peak_time_min']:.0f} min",
        ]
        rows.append(rows_data)

    table_data = list(zip(*rows))  # transpose
    table = ax.table(cellText=table_data, rowLabels=row_labels,
                     colLabels=cfg_labels, loc='center', cellLoc='center')
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1, 1.4)
    ax.set_title('D) Configuration Comparison', pad=20)

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plt.savefig(str(VIZ_DIR / 'fig8_meal_sensitivity.png'), dpi=150)
    plt.close()
    print("    ✓ fig8_meal_sensitivity.png")


def generate_metabolic_visualizations(results):
    """Generate visualizations for EXP-1561 metabolic characterization."""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        print("  matplotlib not available — skipping metabolic visualizations")
        return

    if 1561 not in results:
        return

    d = results[1561]
    by_range = d['by_carb_range']
    records = d['meal_records']
    correlations = d.get('correlations', {})
    per_patient = d.get('per_patient_isf', {})

    carb_ranges = ['<10g', '10-19g', '20-29g', '30-49g', '≥50g']
    os.makedirs(str(VIZ_DIR), exist_ok=True)

    # ── Figure 9: Three-panel carb range comparison ──────────────────
    fig, axes = plt.subplots(1, 3, figsize=(16, 5.5))
    fig.suptitle('EXP-1561: Meal Response by Carb Range — Raw vs ISF-Normalized vs Spectral',
                 fontsize=13, fontweight='bold')

    valid_ranges = [r for r in carb_ranges if by_range.get(r, {}).get('n', 0) > 0]
    x = np.arange(len(valid_ranges))

    # Panel A: Raw excursion (baseline)
    ax = axes[0]
    medians = [by_range[r]['raw_excursion_median'] for r in valid_ranges]
    p25 = [by_range[r]['raw_excursion_p25'] for r in valid_ranges]
    p75 = [by_range[r]['raw_excursion_p75'] for r in valid_ranges]
    yerr_lo = [m - lo for m, lo in zip(medians, p25)]
    yerr_hi = [hi - m for m, hi in zip(medians, p75)]
    ax.bar(x, medians, color='#4C72B0', alpha=0.85)
    ax.errorbar(x, medians, yerr=[yerr_lo, yerr_hi], fmt='none', ecolor='black',
                capsize=4, capthick=1.2)
    ns = [by_range[r]['n'] for r in valid_ranges]
    for i, n in enumerate(ns):
        ax.text(i, medians[i] + yerr_hi[i] + 2, f'n={n}', ha='center', fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels(valid_ranges, fontsize=9)
    ax.set_xlabel('Carb Range')
    ax.set_ylabel('Median Excursion (mg/dL)')
    ax.set_title('A) Raw Excursion')
    ax.grid(axis='y', alpha=0.3)

    # Panel B: ISF-normalized excursion
    ax = axes[1]
    isf_med = [by_range[r]['isf_norm_median'] for r in valid_ranges]
    isf_p25 = [by_range[r]['isf_norm_p25'] for r in valid_ranges]
    isf_p75 = [by_range[r]['isf_norm_p75'] for r in valid_ranges]
    yerr_lo = [m - lo for m, lo in zip(isf_med, isf_p25)]
    yerr_hi = [hi - m for m, hi in zip(isf_med, isf_p75)]
    ax.bar(x, isf_med, color='#55A868', alpha=0.85)
    ax.errorbar(x, isf_med, yerr=[yerr_lo, yerr_hi], fmt='none', ecolor='black',
                capsize=4, capthick=1.2)
    ax.set_xticks(x)
    ax.set_xticklabels(valid_ranges, fontsize=9)
    ax.set_xlabel('Carb Range')
    ax.set_ylabel('Median ISF-Normalized Excursion\n(correction-equivalents)')
    ax.set_title('B) ISF-Normalized Excursion')
    ax.grid(axis='y', alpha=0.3)

    # Panel C: Supply×demand spectral power
    ax = axes[2]
    spec_med = [by_range[r]['spectral_power_median'] for r in valid_ranges]
    spec_p25 = [by_range[r]['spectral_power_p25'] for r in valid_ranges]
    spec_p75 = [by_range[r]['spectral_power_p75'] for r in valid_ranges]
    yerr_lo = [m - lo for m, lo in zip(spec_med, spec_p25)]
    yerr_hi = [hi - m for m, hi in zip(spec_med, spec_p75)]
    ax.bar(x, spec_med, color='#C44E52', alpha=0.85)
    ax.errorbar(x, spec_med, yerr=[yerr_lo, yerr_hi], fmt='none', ecolor='black',
                capsize=4, capthick=1.2)
    ax.set_xticks(x)
    ax.set_xticklabels(valid_ranges, fontsize=9)
    ax.set_xlabel('Carb Range')
    ax.set_ylabel('Median Spectral Power / Hour\n(supply×demand FFT²)')
    ax.set_title('C) Supply×Demand Spectral Power')
    ax.grid(axis='y', alpha=0.3)

    plt.tight_layout(rect=[0, 0, 1, 0.93])
    plt.savefig(str(VIZ_DIR / 'fig9_metabolic_carb_range.png'), dpi=150)
    plt.close()
    print("    ✓ fig9_metabolic_carb_range.png")

    # ── Figure 10: Per-patient ISF normalization effect ──────────────
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))
    fig.suptitle('EXP-1561: ISF Normalization Effect Across Patients',
                 fontsize=13, fontweight='bold')

    pnames = sorted([p for p in per_patient if per_patient[p]['n_meals'] > 0])
    if pnames:
        x = np.arange(len(pnames))
        width = 0.35

        # Panel A: Raw vs ISF-normalized excursion per patient
        ax = axes[0]
        raw_vals = [per_patient[p].get('mean_raw_excursion') or 0 for p in pnames]
        isf_vals_scaled = []
        for p in pnames:
            isf_norm = per_patient[p].get('mean_isf_norm_excursion')
            isf_mgdl = per_patient[p].get('isf_mgdl', 50)
            if isf_norm is not None:
                # Scale back for visual comparison: show as mg/dL equivalent at median ISF
                isf_vals_scaled.append(isf_norm)
            else:
                isf_vals_scaled.append(0)

        ax.bar(x - width / 2, raw_vals, width, label='Raw (mg/dL)', color='#4C72B0', alpha=0.85)
        # Use twin axis for ISF-normalized since units differ
        ax2 = ax.twinx()
        ax2.bar(x + width / 2, isf_vals_scaled, width, label='ISF-Normalized', color='#55A868', alpha=0.85)
        ax.set_xticks(x)
        ax.set_xticklabels(pnames)
        ax.set_xlabel('Patient')
        ax.set_ylabel('Mean Raw Excursion (mg/dL)', color='#4C72B0')
        ax2.set_ylabel('Mean ISF-Normalized (U equiv)', color='#55A868')
        ax.set_title('A) Patient Excursion: Raw vs ISF-Normalized')
        # Combined legend
        lines1, labels1 = ax.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax.legend(lines1 + lines2, labels1 + labels2, fontsize=8, loc='upper right')

        # Panel B: ISF values annotated
        ax = axes[1]
        isf_values = [per_patient[p]['isf_mgdl'] for p in pnames]
        spec_values = [per_patient[p].get('mean_spectral_power') or 0 for p in pnames]

        ax.bar(x - width / 2, isf_values, width, label='Profile ISF (mg/dL/U)',
               color='#ffbb78', alpha=0.85)
        ax3 = ax.twinx()
        ax3.bar(x + width / 2, spec_values, width, label='Mean Spectral Power/hr',
                color='#C44E52', alpha=0.85)
        ax.set_xticks(x)
        ax.set_xticklabels(pnames)
        ax.set_xlabel('Patient')
        ax.set_ylabel('Profile ISF (mg/dL/U)', color='#ffbb78')
        ax3.set_ylabel('Mean Spectral Power/hr', color='#C44E52')
        ax.set_title('B) Patient ISF vs Metabolic Activity')
        lines1, labels1 = ax.get_legend_handles_labels()
        lines2, labels2 = ax3.get_legend_handles_labels()
        ax.legend(lines1 + lines2, labels1 + labels2, fontsize=8, loc='upper right')

    plt.tight_layout(rect=[0, 0, 1, 0.93])
    plt.savefig(str(VIZ_DIR / 'fig10_isf_normalization.png'), dpi=150)
    plt.close()
    print("    ✓ fig10_isf_normalization.png")

    # ── Figure 11: Scatter correlation plots ─────────────────────────
    if len(records) >= 10:
        fig, axes = plt.subplots(1, 3, figsize=(16, 5))
        fig.suptitle('EXP-1561: Cross-Metric Correlations',
                     fontsize=13, fontweight='bold')

        carbs_a = np.array([r['carbs_g'] for r in records])
        raw_exc_a = np.array([r['excursion_mg_dl'] for r in records])
        isf_norm_a = np.array([r['isf_norm_excursion'] for r in records])
        spec_a = np.array([r['spectral_power_per_hour'] for r in records])

        # Color by patient
        patient_names = sorted(set(r['patient'] for r in records))
        cmap = plt.cm.get_cmap('tab10', len(patient_names))
        pat_colors = {p: cmap(i) for i, p in enumerate(patient_names)}
        colors = [pat_colors[r['patient']] for r in records]

        # Panel A: Carbs vs ISF-normalized excursion
        ax = axes[0]
        ax.scatter(carbs_a, isf_norm_a, c=colors, alpha=0.4, s=15, edgecolors='none')
        r_val = correlations.get('carbs_vs_isf_norm_excursion')
        ax.set_xlabel('Carbs (g)')
        ax.set_ylabel('ISF-Normalized Excursion')
        ax.set_title(f'A) Carbs vs ISF-Norm Exc (r={r_val})')
        ax.grid(alpha=0.3)

        # Panel B: Carbs vs spectral power
        ax = axes[1]
        ax.scatter(carbs_a, spec_a, c=colors, alpha=0.4, s=15, edgecolors='none')
        r_val = correlations.get('carbs_vs_spectral_power')
        ax.set_xlabel('Carbs (g)')
        ax.set_ylabel('Spectral Power / Hour')
        ax.set_title(f'B) Carbs vs Spectral Power (r={r_val})')
        ax.grid(alpha=0.3)

        # Panel C: ISF-norm excursion vs spectral power
        ax = axes[2]
        ax.scatter(isf_norm_a, spec_a, c=colors, alpha=0.4, s=15, edgecolors='none')
        r_val = correlations.get('isf_norm_vs_spectral_power')
        ax.set_xlabel('ISF-Normalized Excursion')
        ax.set_ylabel('Spectral Power / Hour')
        ax.set_title(f'C) ISF-Norm Exc vs Spectral (r={r_val})')
        ax.grid(alpha=0.3)

        # Add patient legend
        import matplotlib.patches as mpatches
        legend_patches = [mpatches.Patch(color=pat_colors[p], label=p)
                          for p in patient_names]
        fig.legend(handles=legend_patches, loc='lower center',
                   ncol=min(len(patient_names), 6), fontsize=8,
                   bbox_to_anchor=(0.5, -0.02))

        plt.tight_layout(rect=[0, 0.05, 1, 0.93])
        plt.savefig(str(VIZ_DIR / 'fig11_metabolic_correlations.png'), dpi=150)
        plt.close()
        print("    ✓ fig11_metabolic_correlations.png")

    # ── Figure 12: Box/violin distributions by carb range ────────────
    # Group raw records by carb range for distribution plots
    carb_ranges_ordered = ['10-19g', '20-29g', '30-49g', '≥50g']
    grouped = {r: [] for r in carb_ranges_ordered}
    for rec in records:
        cr = rec.get('carb_range')
        if cr in grouped:
            grouped[cr].append(rec)

    # Only plot ranges with data
    plot_ranges = [r for r in carb_ranges_ordered if len(grouped[r]) >= 3]
    if not plot_ranges:
        return

    fig, axes = plt.subplots(2, 3, figsize=(18, 11))
    fig.suptitle('EXP-1561: Meal Metabolic Distributions by Carb Range',
                 fontsize=14, fontweight='bold')

    metrics = [
        ('excursion_mg_dl',       'Raw Excursion (mg/dL)',              '#4C72B0'),
        ('isf_norm_excursion',    'ISF-Normalized Excursion (U equiv)', '#55A868'),
        ('spectral_power_per_hour', 'Spectral Power / Hour',           '#C44E52'),
        ('mean_interaction',      'Mean Supply×Demand',                '#8172B2'),
        ('net_flux_mean',         'Mean Net Flux (mg/dL/5min)',        '#CCB974'),
        ('peak_time_min',         'Time to Peak (min)',                '#64B5CD'),
    ]

    for ax_idx, (key, label, color) in enumerate(metrics):
        ax = axes[ax_idx // 3, ax_idx % 3]
        box_data = []
        box_labels = []
        for rng in plot_ranges:
            vals = [r[key] for r in grouped[rng]
                    if r.get(key) is not None and np.isfinite(r[key])]
            if vals:
                box_data.append(vals)
                box_labels.append(f'{rng}\n(n={len(vals)})')
            else:
                box_data.append([0])
                box_labels.append(f'{rng}\n(n=0)')

        bp = ax.boxplot(box_data, tick_labels=box_labels, patch_artist=True,
                        showfliers=False, widths=0.6)
        for patch in bp['boxes']:
            patch.set_facecolor(color)
            patch.set_alpha(0.6)
        for median_line in bp['medians']:
            median_line.set_color('black')
            median_line.set_linewidth(2)

        # Overlay individual points (jittered)
        for i, vals in enumerate(box_data):
            jitter = np.random.normal(0, 0.05, size=len(vals))
            ax.scatter(np.full(len(vals), i + 1) + jitter, vals,
                       alpha=0.15, s=8, color=color, edgecolors='none')

        ax.set_ylabel(label, fontsize=9)
        ax.set_xlabel('Carb Range')
        ax.set_title(f'{chr(65 + ax_idx)}) {label.split("(")[0].strip()}')
        ax.grid(axis='y', alpha=0.3)

        # Log scale for spectral power (spans orders of magnitude)
        if 'spectral' in key.lower() or 'interaction' in key.lower():
            ax.set_yscale('log')

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plt.savefig(str(VIZ_DIR / 'fig12_carb_range_distributions.png'), dpi=150)
    plt.close()
    print("    ✓ fig12_carb_range_distributions.png")

    # ── Figure 13: Patient × Carb Range heatmaps ────────────────────
    patient_names = sorted(set(r['patient'] for r in records))
    if len(patient_names) < 2:
        return

    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    fig.suptitle('EXP-1561: Patient × Carb Range Heatmaps',
                 fontsize=13, fontweight='bold')

    hm_metrics = [
        ('isf_norm_excursion',      'ISF-Normalized Excursion', 'YlOrRd'),
        ('spectral_power_per_hour', 'Log₁₀ Spectral Power/hr', 'YlOrRd'),
        ('excursion_mg_dl',         'Raw Excursion (mg/dL)',    'YlOrRd'),
    ]

    for ax_idx, (key, label, cmap_name) in enumerate(hm_metrics):
        ax = axes[ax_idx]
        matrix = np.full((len(patient_names), len(plot_ranges)), np.nan)

        for pi, pat in enumerate(patient_names):
            for ri, rng in enumerate(plot_ranges):
                vals = [r[key] for r in records
                        if r['patient'] == pat and r['carb_range'] == rng
                        and r.get(key) is not None and np.isfinite(r[key])]
                if vals:
                    v = float(np.median(vals))
                    if 'spectral' in key:
                        v = np.log10(max(v, 1))  # log scale
                    matrix[pi, ri] = v

        im = ax.imshow(matrix, aspect='auto', cmap=cmap_name, interpolation='nearest')
        ax.set_xticks(range(len(plot_ranges)))
        ax.set_xticklabels(plot_ranges, fontsize=9)
        ax.set_yticks(range(len(patient_names)))
        ax.set_yticklabels(patient_names, fontsize=9)
        ax.set_xlabel('Carb Range')
        ax.set_ylabel('Patient')
        ax.set_title(f'{chr(65 + ax_idx)}) {label}')

        # Annotate cells
        for pi in range(len(patient_names)):
            for ri in range(len(plot_ranges)):
                val = matrix[pi, ri]
                if not np.isnan(val):
                    fmt = f'{val:.2f}' if 'isf_norm' in key or 'spectral' in key else f'{val:.0f}'
                    color = 'white' if val > np.nanpercentile(matrix, 70) else 'black'
                    ax.text(ri, pi, fmt, ha='center', va='center',
                            fontsize=7, color=color)

        plt.colorbar(im, ax=ax, shrink=0.8)

    plt.tight_layout(rect=[0, 0, 1, 0.93])
    plt.savefig(str(VIZ_DIR / 'fig13_patient_carb_heatmap.png'), dpi=150)
    plt.close()
    print("    ✓ fig13_patient_carb_heatmap.png")

    # ── Figure 14: Announced vs Unannounced by carb range ────────────
    fig, axes = plt.subplots(1, 3, figsize=(16, 5.5))
    fig.suptitle('EXP-1561: Announced vs Unannounced Meals by Carb Range',
                 fontsize=13, fontweight='bold')

    ann_metrics = [
        ('excursion_mg_dl',         'Raw Excursion (mg/dL)'),
        ('isf_norm_excursion',      'ISF-Normalized Excursion'),
        ('spectral_power_per_hour', 'Spectral Power / Hour'),
    ]

    for ax_idx, (key, label) in enumerate(ann_metrics):
        ax = axes[ax_idx]
        x = np.arange(len(plot_ranges))
        width = 0.35

        for gi, (grp_label, grp_color) in enumerate([
            ('Announced', '#4C72B0'), ('Unannounced', '#C44E52')
        ]):
            is_ann = (grp_label == 'Announced')
            medians = []
            for rng in plot_ranges:
                vals = [r[key] for r in grouped[rng]
                        if r.get('is_announced') == is_ann
                        and r.get(key) is not None and np.isfinite(r[key])]
                medians.append(float(np.median(vals)) if vals else 0)
            ax.bar(x + gi * width, medians, width, label=grp_label,
                   color=grp_color, alpha=0.85)

        ax.set_xticks(x + width / 2)
        ax.set_xticklabels(plot_ranges, fontsize=9)
        ax.set_xlabel('Carb Range')
        ax.set_ylabel(label)
        ax.set_title(f'{chr(65 + ax_idx)}) {label.split("(")[0].strip()}')
        ax.legend(fontsize=8)
        ax.grid(axis='y', alpha=0.3)

        if 'spectral' in key:
            ax.set_yscale('log')

    plt.tight_layout(rect=[0, 0, 1, 0.93])
    plt.savefig(str(VIZ_DIR / 'fig14_announced_vs_unannounced.png'), dpi=150)
    plt.close()
    print("    ✓ fig14_announced_vs_unannounced.png")


def generate_multiconfig_visualizations(results):
    """Generate EXP-1563 multi-config comparison + periodicity figures."""
    if 1563 not in results:
        return

    r = results[1563]
    config_records = r.get('_config_records', {})
    if not config_records:
        print("  ⚠ No _config_records for multi-config viz")
        return

    os.makedirs(str(VIZ_DIR), exist_ok=True)

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    cfg_names = list(config_records.keys())
    cfg_labels = {
        'A_census_5g_30m': '≥5g / 30min',
        'B_medium_5g_90m': '≥5g / 90min',
        'C_therapy_18g_90m': '≥18g / 90min',
    }
    CARB_RANGE_ORDER = ['<10g', '10-19g', '20-29g', '30-49g', '≥50g']

    # ── Figure 15: Multi-config metric comparison (3×3 bar grid) ─────
    metrics = [
        ('isf_norm_mean',      'ISF-Norm Excursion'),
        ('spectral_power_mean', 'Spectral Power/hr'),
        ('net_flux_mean',       'Net Flux Mean'),
    ]

    fig, axes = plt.subplots(1, 3, figsize=(18, 5.5))
    fig.suptitle('EXP-1563: Metabolic Metrics by Carb Range × Detection Config',
                 fontsize=13, fontweight='bold')

    colors = ['#4C72B0', '#55A868', '#C44E52']

    for ax_idx, (metric_key, metric_label) in enumerate(metrics):
        ax = axes[ax_idx]
        x = np.arange(len(CARB_RANGE_ORDER))
        n_cfgs = len(cfg_names)
        width = 0.8 / n_cfgs

        for ci, cfg_name in enumerate(cfg_names):
            by_range = config_records[cfg_name].get('by_carb_range', {})
            vals = []
            for rng in CARB_RANGE_ORDER:
                rd = by_range.get(rng, {})
                vals.append(rd.get(metric_key, 0) if rd.get('n', 0) > 0 else 0)
            ax.bar(x + ci * width, vals, width, label=cfg_labels.get(cfg_name, cfg_name),
                   color=colors[ci], alpha=0.85)

        ax.set_xticks(x + width * (n_cfgs - 1) / 2)
        ax.set_xticklabels(CARB_RANGE_ORDER, fontsize=9)
        ax.set_xlabel('Carb Range')
        ax.set_ylabel(metric_label)
        ax.set_title(f'{chr(65 + ax_idx)}) {metric_label}')
        ax.legend(fontsize=7, loc='upper left')
        ax.grid(axis='y', alpha=0.3)

        if 'spectral' in metric_key:
            ax.set_yscale('log')

    plt.tight_layout(rect=[0, 0, 1, 0.93])
    plt.savefig(str(VIZ_DIR / 'fig15_multiconfig_metrics.png'), dpi=150)
    plt.close()
    print("    ✓ fig15_multiconfig_metrics.png")

    # ── Figure 16: Multi-config box plots (ISF-norm and spectral) ────
    fig, axes = plt.subplots(2, 3, figsize=(18, 10))
    fig.suptitle('EXP-1563: Metric Distributions by Config × Carb Range',
                 fontsize=13, fontweight='bold')

    for row_idx, (metric_key, metric_label) in enumerate([
        ('isf_norm_excursion', 'ISF-Norm Excursion'),
        ('spectral_power_per_hour', 'Spectral Power/hr'),
    ]):
        for col_idx, cfg_name in enumerate(cfg_names):
            ax = axes[row_idx, col_idx]
            records = config_records[cfg_name]['records']

            box_data = []
            box_labels = []
            for rng in CARB_RANGE_ORDER:
                vals = [r[metric_key] for r in records
                        if r['carb_range'] == rng and np.isfinite(r[metric_key])]
                if vals:
                    box_data.append(vals)
                    box_labels.append(rng)

            if box_data:
                bp = ax.boxplot(box_data, tick_labels=box_labels, patch_artist=True,
                                showfliers=False)
                for patch, c in zip(bp['boxes'],
                                    [colors[col_idx]] * len(box_data)):
                    patch.set_facecolor(c)
                    patch.set_alpha(0.4)

            ax.set_xlabel('Carb Range')
            ax.set_ylabel(metric_label)
            lbl = cfg_labels.get(cfg_name, cfg_name)
            ax.set_title(f'{lbl}  (n={config_records[cfg_name]["n_meals"]})')
            ax.grid(axis='y', alpha=0.3)
            if 'spectral' in metric_key:
                ax.set_yscale('log')

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plt.savefig(str(VIZ_DIR / 'fig16_multiconfig_boxplots.png'), dpi=150)
    plt.close()
    print("    ✓ fig16_multiconfig_boxplots.png")

    # ── Figure 17: Meal periodicity — hourly histograms by config ────
    fig, axes = plt.subplots(1, 3, figsize=(18, 5.5))
    fig.suptitle('EXP-1563: Meal Time-of-Day Distribution by Detection Config',
                 fontsize=13, fontweight='bold')

    for ax_idx, cfg_name in enumerate(cfg_names):
        ax = axes[ax_idx]
        periodicity = config_records[cfg_name].get('periodicity', {})
        hist = periodicity.get('hour_histogram', [0] * 24)

        ax.bar(range(24), hist, color=colors[ax_idx], alpha=0.7, edgecolor='black',
               linewidth=0.5)

        # Shade mealtime zones
        for zone_name, (start_h, end_h) in MEALTIME_ZONES.items():
            ax.axvspan(start_h - 0.5, end_h - 0.5, alpha=0.1, color='gold',
                       label=zone_name if ax_idx == 0 else None)
            ax.text((start_h + end_h) / 2, ax.get_ylim()[1] * 0.85 if hist else 1,
                    zone_name.capitalize(), ha='center', fontsize=8, style='italic',
                    color='#8B6914')

        lbl = cfg_labels.get(cfg_name, cfg_name)
        ent = periodicity.get('normalized_entropy', 0)
        zf = periodicity.get('zone_fraction_pct', 0)
        ax.set_title(f'{lbl}\nEntropy={ent:.3f}, Zone%={zf:.1f}%')
        ax.set_xlabel('Hour of Day')
        ax.set_ylabel('Meal Count')
        ax.set_xticks(range(0, 24, 3))
        ax.grid(axis='y', alpha=0.3)

    plt.tight_layout(rect=[0, 0, 1, 0.93])
    plt.savefig(str(VIZ_DIR / 'fig17_meal_periodicity.png'), dpi=150)
    plt.close()
    print("    ✓ fig17_meal_periodicity.png")

    # ── Figure 18: Periodicity — per-patient mealtime regularity ─────
    # For each config, scatter per-patient std-of-hour within each zone
    fig, axes = plt.subplots(1, 3, figsize=(18, 5.5))
    fig.suptitle('EXP-1563: Per-Patient Mealtime Regularity by Zone × Config',
                 fontsize=13, fontweight='bold')

    zone_names = list(MEALTIME_ZONES.keys())
    zone_colors = {'breakfast': '#FF9F1C', 'lunch': '#2EC4B6', 'dinner': '#E71D36'}

    for ax_idx, cfg_name in enumerate(cfg_names):
        ax = axes[ax_idx]
        records = config_records[cfg_name]['records']
        pat_names = sorted(set(r['patient'] for r in records))

        for zone_name, (start_h, end_h) in MEALTIME_ZONES.items():
            stds = []
            counts = []
            pat_labels = []
            for pat in pat_names:
                pat_hours = [r['hour_of_day'] for r in records
                             if r['patient'] == pat and start_h <= r['hour_of_day'] < end_h]
                if len(pat_hours) >= 3:
                    stds.append(float(np.std(pat_hours)))
                    counts.append(len(pat_hours))
                    pat_labels.append(pat)

            if stds:
                ax.scatter(counts, stds, label=zone_name.capitalize(),
                           color=zone_colors[zone_name], alpha=0.7, s=50, edgecolors='black',
                           linewidth=0.5)
                for i, pl in enumerate(pat_labels):
                    ax.annotate(pl, (counts[i], stds[i]), fontsize=6,
                                textcoords='offset points', xytext=(3, 3))

        lbl = cfg_labels.get(cfg_name, cfg_name)
        ax.set_title(f'{lbl}')
        ax.set_xlabel('# Meals in Zone')
        ax.set_ylabel('Std(Hour) within Zone')
        ax.legend(fontsize=8)
        ax.grid(alpha=0.3)

    plt.tight_layout(rect=[0, 0, 1, 0.93])
    plt.savefig(str(VIZ_DIR / 'fig18_mealtime_regularity.png'), dpi=150)
    plt.close()
    print("    ✓ fig18_mealtime_regularity.png")

    # ── Figure 19: Small vs large meal metabolic profile ─────────────
    small_vs_large = r.get('small_vs_large_meals', {})
    if small_vs_large.get('small_5_to_18g', {}).get('n', 0) > 0:
        fig, axes = plt.subplots(1, 3, figsize=(15, 5))
        fig.suptitle('EXP-1563: Small (5-18g) vs Large (≥18g) Meal Metabolic Profile',
                     fontsize=13, fontweight='bold')

        sm = small_vs_large['small_5_to_18g']
        lg = small_vs_large.get('large_18g_plus', {'n': 0})
        chart_metrics = [
            ('median_raw_excursion', 'Raw Excursion (mg/dL)'),
            ('median_isf_norm', 'ISF-Norm Excursion'),
            ('median_spectral_power', 'Spectral Power/hr'),
        ]

        for ax_idx, (mk, mlabel) in enumerate(chart_metrics):
            ax = axes[ax_idx]
            vals = [sm.get(mk, 0), lg.get(mk, 0)]
            bars = ax.bar(['Small\n5-18g', 'Large\n≥18g'], vals,
                          color=['#55A868', '#C44E52'], alpha=0.8, edgecolor='black')
            for b, v in zip(bars, vals):
                ax.text(b.get_x() + b.get_width() / 2, b.get_height(),
                        f'{v:.1f}' if v > 1 else f'{v:.3f}',
                        ha='center', va='bottom', fontsize=10, fontweight='bold')
            ax.set_ylabel(mlabel)
            ax.set_title(f'{chr(65 + ax_idx)}) {mlabel.split("(")[0].strip()}')
            ax.grid(axis='y', alpha=0.3)
            n_sm = sm.get('n', 0)
            n_lg = lg.get('n', 0)
            ax.set_xlabel(f'n={n_sm} / n={n_lg}')
            if 'spectral' in mk.lower():
                ax.set_yscale('log')

        plt.tight_layout(rect=[0, 0, 1, 0.93])
        plt.savefig(str(VIZ_DIR / 'fig19_small_vs_large_meals.png'), dpi=150)
        plt.close()
        print("    ✓ fig19_small_vs_large_meals.png")
    else:
        print("    ⚠ No small meals (5-18g) found — skipping fig19")

    # ── Figure 20: Periodicity summary — entropy + zone fraction ─────
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle('EXP-1563: Does Stricter Detection Increase Meal Periodicity?',
                 fontsize=13, fontweight='bold')

    cfg_x = [cfg_labels.get(cn, cn) for cn in cfg_names]
    entropies = [config_records[cn].get('periodicity', {}).get('normalized_entropy', 0)
                 for cn in cfg_names]
    zone_fracs = [config_records[cn].get('periodicity', {}).get('zone_fraction_pct', 0)
                  for cn in cfg_names]

    ax = axes[0]
    bars = ax.bar(cfg_x, entropies, color=colors, alpha=0.8, edgecolor='black')
    for b, v in zip(bars, entropies):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height(),
                f'{v:.3f}', ha='center', va='bottom', fontsize=11, fontweight='bold')
    ax.set_ylabel('Normalized Entropy (0=periodic, 1=uniform)')
    ax.set_title('A) Temporal Concentration')
    ax.set_ylim(0, 1)
    ax.grid(axis='y', alpha=0.3)
    ax.axhline(y=1.0, color='gray', linestyle='--', alpha=0.5, label='Uniform')
    ax.legend(fontsize=8)

    ax = axes[1]
    bars = ax.bar(cfg_x, zone_fracs, color=colors, alpha=0.8, edgecolor='black')
    for b, v in zip(bars, zone_fracs):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height(),
                f'{v:.1f}%', ha='center', va='bottom', fontsize=11, fontweight='bold')
    ax.set_ylabel('% Meals in Mealtime Zones')
    ax.set_title('B) Mealtime Zone Concentration')
    ax.set_ylim(0, 100)
    ax.grid(axis='y', alpha=0.3)

    plt.tight_layout(rect=[0, 0, 1, 0.93])
    plt.savefig(str(VIZ_DIR / 'fig20_periodicity_summary.png'), dpi=150)
    plt.close()
    print("    ✓ fig20_periodicity_summary.png")


def generate_weekday_weekend_visualizations(results):
    """Generate EXP-1565 weekday vs weekend periodicity figures."""
    if 1565 not in results:
        return

    r = results[1565]
    records = r.get('_records', [])
    if not records:
        print("  ⚠ No _records for weekday/weekend viz")
        return

    os.makedirs(str(VIZ_DIR), exist_ok=True)

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    DOW_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    WD_COLOR = '#4C72B0'
    WE_COLOR = '#C44E52'

    weekday_recs = [rec for rec in records if rec.get('day_of_week', 0) < 5]
    weekend_recs = [rec for rec in records if rec.get('day_of_week', 0) >= 5]

    pop = r.get('population', {})
    wd_hist = pop.get('weekday', {}).get('hour_histogram', [0] * 24)
    we_hist = pop.get('weekend', {}).get('hour_histogram', [0] * 24)

    # ── Figure 21: Weekday vs Weekend hourly histograms ──────────────
    fig, axes = plt.subplots(1, 3, figsize=(18, 5.5))
    fig.suptitle('EXP-1565: Weekday vs Weekend Meal Timing',
                 fontsize=13, fontweight='bold')

    # Panel A: Overlay histograms (normalized)
    ax = axes[0]
    hours = np.arange(24)
    wd_norm = np.array(wd_hist, dtype=float) / max(sum(wd_hist), 1)
    we_norm = np.array(we_hist, dtype=float) / max(sum(we_hist), 1)
    ax.bar(hours - 0.2, wd_norm, 0.4, label=f'Weekday (n={len(weekday_recs)})',
           color=WD_COLOR, alpha=0.7)
    ax.bar(hours + 0.2, we_norm, 0.4, label=f'Weekend (n={len(weekend_recs)})',
           color=WE_COLOR, alpha=0.7)
    for zone_name, (s, e) in MEALTIME_ZONES.items():
        ax.axvspan(s - 0.5, e - 0.5, alpha=0.08, color='gold')
        ax.text((s + e) / 2, ax.get_ylim()[1] * 0.9 if max(wd_norm) > 0 else 0.1,
                zone_name.capitalize(), ha='center', fontsize=7, style='italic',
                color='#8B6914')
    ax.set_xlabel('Hour of Day')
    ax.set_ylabel('Fraction of Meals')
    ax.set_title('A) Normalized Hourly Distribution')
    ax.set_xticks(range(0, 24, 3))
    ax.legend(fontsize=8)
    ax.grid(axis='y', alpha=0.3)

    # Panel B: Difference (weekend - weekday)
    ax = axes[1]
    diff = we_norm - wd_norm
    colors_diff = [WE_COLOR if d > 0 else WD_COLOR for d in diff]
    ax.bar(hours, diff, color=colors_diff, alpha=0.7, edgecolor='black', linewidth=0.3)
    ax.axhline(y=0, color='black', linewidth=0.8)
    for zone_name, (s, e) in MEALTIME_ZONES.items():
        ax.axvspan(s - 0.5, e - 0.5, alpha=0.08, color='gold')
    ax.set_xlabel('Hour of Day')
    ax.set_ylabel('Δ Fraction (Weekend − Weekday)')
    ax.set_title('B) Weekend Shift Pattern')
    ax.set_xticks(range(0, 24, 3))
    ax.grid(axis='y', alpha=0.3)

    # Panel C: DOW meal rate
    ax = axes[2]
    dow_dist = r.get('dow_distribution', {})
    dow_counts = [dow_dist.get(d, 0) for d in DOW_LABELS]
    bar_colors = [WD_COLOR] * 5 + [WE_COLOR] * 2
    ax.bar(DOW_LABELS, dow_counts, color=bar_colors, alpha=0.8, edgecolor='black',
           linewidth=0.5)
    ax.set_xlabel('Day of Week')
    ax.set_ylabel('Total Meals')
    ax.set_title('C) Meals by Day of Week')
    ax.grid(axis='y', alpha=0.3)
    mean_wd = np.mean(dow_counts[:5]) if dow_counts[:5] else 0
    mean_we = np.mean(dow_counts[5:]) if dow_counts[5:] else 0
    ax.axhline(y=mean_wd, color=WD_COLOR, linestyle='--', alpha=0.5, label=f'WD mean={mean_wd:.0f}')
    ax.axhline(y=mean_we, color=WE_COLOR, linestyle='--', alpha=0.5, label=f'WE mean={mean_we:.0f}')
    ax.legend(fontsize=8)

    plt.tight_layout(rect=[0, 0, 1, 0.93])
    plt.savefig(str(VIZ_DIR / 'fig21_weekday_weekend_timing.png'), dpi=150)
    plt.close()
    print("    ✓ fig21_weekday_weekend_timing.png")

    # ── Figure 22: Per-patient weekday vs weekend comparison ─────────
    per_patient = r.get('per_patient', {})
    pat_names = sorted(per_patient.keys())

    fig, axes = plt.subplots(1, 3, figsize=(18, 5.5))
    fig.suptitle('EXP-1565: Per-Patient Weekday vs Weekend Meal Patterns',
                 fontsize=13, fontweight='bold')

    # Panel A: Hour shift per patient
    ax = axes[0]
    shifts = [per_patient[p].get('hour_shift', 0) or 0 for p in pat_names]
    bar_colors_shift = [WE_COLOR if s > 0 else WD_COLOR for s in shifts]
    ax.barh(pat_names, shifts, color=bar_colors_shift, alpha=0.8, edgecolor='black',
            linewidth=0.5)
    ax.axvline(x=0, color='black', linewidth=0.8)
    ax.set_xlabel('Mean Hour Shift (Weekend − Weekday)')
    ax.set_title('A) Meal Timing Shift (hours)')
    ax.grid(axis='x', alpha=0.3)
    for i, (p, s) in enumerate(zip(pat_names, shifts)):
        ax.text(s + (0.05 if s >= 0 else -0.05), i,
                f'{s:+.1f}h', va='center', ha='left' if s >= 0 else 'right',
                fontsize=8)

    # Panel B: ISF-norm delta
    ax = axes[1]
    isf_deltas = [per_patient[p].get('isf_norm_delta', 0) or 0 for p in pat_names]
    bar_colors_isf = [WE_COLOR if d > 0 else WD_COLOR for d in isf_deltas]
    ax.barh(pat_names, isf_deltas, color=bar_colors_isf, alpha=0.8, edgecolor='black',
            linewidth=0.5)
    ax.axvline(x=0, color='black', linewidth=0.8)
    ax.set_xlabel('ΔISF-Norm Excursion (Weekend − Weekday)')
    ax.set_title('B) Excursion Severity Shift')
    ax.grid(axis='x', alpha=0.3)
    for i, (p, d) in enumerate(zip(pat_names, isf_deltas)):
        ax.text(d + (0.02 if d >= 0 else -0.02), i,
                f'{d:+.3f}', va='center', ha='left' if d >= 0 else 'right',
                fontsize=8)

    # Panel C: Meal count weekday vs weekend
    ax = axes[2]
    y_pos = np.arange(len(pat_names))
    wd_counts_pp = [per_patient[p].get('n_weekday', 0) for p in pat_names]
    we_counts_pp = [per_patient[p].get('n_weekend', 0) for p in pat_names]
    ax.barh(y_pos - 0.2, wd_counts_pp, 0.35, label='Weekday', color=WD_COLOR, alpha=0.8)
    ax.barh(y_pos + 0.2, we_counts_pp, 0.35, label='Weekend', color=WE_COLOR, alpha=0.8)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(pat_names)
    ax.set_xlabel('Meal Count')
    ax.set_title('C) Meal Volume')
    ax.legend(fontsize=8)
    ax.grid(axis='x', alpha=0.3)

    plt.tight_layout(rect=[0, 0, 1, 0.93])
    plt.savefig(str(VIZ_DIR / 'fig22_per_patient_weekday_weekend.png'), dpi=150)
    plt.close()
    print("    ✓ fig22_per_patient_weekday_weekend.png")

    # ── Figure 23: Mealtime zone shift detail ────────────────────────
    zone_shifts = r.get('zone_shifts', {})
    if zone_shifts:
        fig, axes = plt.subplots(1, 3, figsize=(16, 5))
        fig.suptitle('EXP-1565: Mealtime Zone Timing Shifts (Weekend vs Weekday)',
                     fontsize=13, fontweight='bold')

        zone_names = list(zone_shifts.keys())
        zone_colors = {'breakfast': '#FF9F1C', 'lunch': '#2EC4B6', 'dinner': '#E71D36'}

        # Panel A: Mean hour comparison
        ax = axes[0]
        x = np.arange(len(zone_names))
        wd_means = [zone_shifts[z]['weekday_mean_hour'] for z in zone_names]
        we_means = [zone_shifts[z]['weekend_mean_hour'] for z in zone_names]
        ax.bar(x - 0.2, wd_means, 0.35, label='Weekday', color=WD_COLOR, alpha=0.8)
        ax.bar(x + 0.2, we_means, 0.35, label='Weekend', color=WE_COLOR, alpha=0.8)
        ax.set_xticks(x)
        ax.set_xticklabels([z.capitalize() for z in zone_names])
        ax.set_ylabel('Mean Hour')
        ax.set_title('A) Mean Meal Time by Zone')
        ax.legend(fontsize=8)
        ax.grid(axis='y', alpha=0.3)
        for i, z in enumerate(zone_names):
            shift = zone_shifts[z]['shift_minutes']
            ax.text(i, max(wd_means[i], we_means[i]) + 0.1,
                    f'{shift:+.0f}min', ha='center', fontsize=9, fontweight='bold')

        # Panel B: Shift in minutes
        ax = axes[1]
        shifts_min = [zone_shifts[z]['shift_minutes'] for z in zone_names]
        bar_c = [zone_colors.get(z, 'gray') for z in zone_names]
        bars = ax.bar([z.capitalize() for z in zone_names], shifts_min,
                      color=bar_c, alpha=0.8, edgecolor='black')
        ax.axhline(y=0, color='black', linewidth=0.8)
        ax.set_ylabel('Shift (minutes)')
        ax.set_title('B) Weekend Timing Shift')
        ax.grid(axis='y', alpha=0.3)
        for b, v in zip(bars, shifts_min):
            ax.text(b.get_x() + b.get_width() / 2, v,
                    f'{v:+.0f}m', ha='center',
                    va='bottom' if v >= 0 else 'top',
                    fontsize=11, fontweight='bold')

        # Panel C: Std comparison (regularity)
        ax = axes[2]
        wd_stds = [zone_shifts[z].get('weekday_std', 0) or 0 for z in zone_names]
        we_stds = [zone_shifts[z].get('weekend_std', 0) or 0 for z in zone_names]
        ax.bar(x - 0.2, wd_stds, 0.35, label='Weekday', color=WD_COLOR, alpha=0.8)
        ax.bar(x + 0.2, we_stds, 0.35, label='Weekend', color=WE_COLOR, alpha=0.8)
        ax.set_xticks(x)
        ax.set_xticklabels([z.capitalize() for z in zone_names])
        ax.set_ylabel('Std(Hour)')
        ax.set_title('C) Timing Regularity (lower=more regular)')
        ax.legend(fontsize=8)
        ax.grid(axis='y', alpha=0.3)

        plt.tight_layout(rect=[0, 0, 1, 0.93])
        plt.savefig(str(VIZ_DIR / 'fig23_zone_shift_detail.png'), dpi=150)
        plt.close()
        print("    ✓ fig23_zone_shift_detail.png")

    # ── Figure 24: Weekday vs weekend metabolic comparison ───────────
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    fig.suptitle('EXP-1565: Weekday vs Weekend Metabolic Profile',
                 fontsize=13, fontweight='bold')

    wd_isf = [rec['isf_norm_excursion'] for rec in weekday_recs
              if np.isfinite(rec['isf_norm_excursion'])]
    we_isf = [rec['isf_norm_excursion'] for rec in weekend_recs
              if np.isfinite(rec['isf_norm_excursion'])]
    wd_spec = [rec['spectral_power_per_hour'] for rec in weekday_recs
               if np.isfinite(rec['spectral_power_per_hour'])]
    we_spec = [rec['spectral_power_per_hour'] for rec in weekend_recs
               if np.isfinite(rec['spectral_power_per_hour'])]
    wd_net = [rec['net_flux_mean'] for rec in weekday_recs
              if np.isfinite(rec['net_flux_mean'])]
    we_net = [rec['net_flux_mean'] for rec in weekend_recs
              if np.isfinite(rec['net_flux_mean'])]

    # Panel A: ISF-norm box
    ax = axes[0]
    if wd_isf and we_isf:
        bp = ax.boxplot([wd_isf, we_isf], tick_labels=['Weekday', 'Weekend'],
                        patch_artist=True, showfliers=False)
        bp['boxes'][0].set_facecolor(WD_COLOR)
        bp['boxes'][0].set_alpha(0.4)
        bp['boxes'][1].set_facecolor(WE_COLOR)
        bp['boxes'][1].set_alpha(0.4)
    ax.set_ylabel('ISF-Norm Excursion')
    ax.set_title('A) ISF-Normalized Excursion')
    ax.grid(axis='y', alpha=0.3)

    # Panel B: Spectral power box
    ax = axes[1]
    if wd_spec and we_spec:
        bp = ax.boxplot([wd_spec, we_spec], tick_labels=['Weekday', 'Weekend'],
                        patch_artist=True, showfliers=False)
        bp['boxes'][0].set_facecolor(WD_COLOR)
        bp['boxes'][0].set_alpha(0.4)
        bp['boxes'][1].set_facecolor(WE_COLOR)
        bp['boxes'][1].set_alpha(0.4)
        ax.set_yscale('log')
    ax.set_ylabel('Spectral Power / Hour')
    ax.set_title('B) Supply×Demand Spectral Power')
    ax.grid(axis='y', alpha=0.3)

    # Panel C: Net flux box
    ax = axes[2]
    if wd_net and we_net:
        bp = ax.boxplot([wd_net, we_net], tick_labels=['Weekday', 'Weekend'],
                        patch_artist=True, showfliers=False)
        bp['boxes'][0].set_facecolor(WD_COLOR)
        bp['boxes'][0].set_alpha(0.4)
        bp['boxes'][1].set_facecolor(WE_COLOR)
        bp['boxes'][1].set_alpha(0.4)
    ax.set_ylabel('Net Flux Mean')
    ax.set_title('C) Net Flux (>0 = carb-dominant)')
    ax.grid(axis='y', alpha=0.3)

    plt.tight_layout(rect=[0, 0, 1, 0.93])
    plt.savefig(str(VIZ_DIR / 'fig24_weekday_weekend_metabolic.png'), dpi=150)
    plt.close()
    print("    ✓ fig24_weekday_weekend_metabolic.png")


def generate_within_patient_visualizations(results):
    """Generate EXP-1567 within-patient meal clock regularity figures."""
    if 1567 not in results:
        return

    r = results[1567]
    per_patient = r.get('per_patient', {})
    if not per_patient:
        return

    os.makedirs(str(VIZ_DIR), exist_ok=True)

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from scipy.ndimage import uniform_filter1d

    pat_names = sorted(per_patient.keys())
    n_pats = len(pat_names)

    # ── Figure 25: Per-patient hourly histograms (small multiples) ───
    cols = 4
    rows = (n_pats + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(16, 3.5 * rows))
    fig.suptitle('EXP-1567: Per-Patient Meal Timing (Personal Meal Clocks)',
                 fontsize=14, fontweight='bold')
    if rows == 1:
        axes = axes.reshape(1, -1)

    cmap = matplotlib.colormaps['tab10']
    for idx, pat in enumerate(pat_names):
        ax = axes[idx // cols, idx % cols]
        pp = per_patient[pat]
        hist = np.array(pp['hour_histogram'], dtype=float)
        smoothed = uniform_filter1d(np.concatenate([hist, hist, hist]),
                                    size=4, mode='wrap')[24:48]

        ax.bar(range(24), hist, color=cmap(idx % 10), alpha=0.5, edgecolor='none')
        ax.plot(range(24), smoothed, color=cmap(idx % 10), linewidth=2)

        # Mark personal peaks
        for peak in pp.get('personal_peaks', []):
            ph = peak['peak_hour']
            ax.axvline(x=ph, color='red', linestyle='--', alpha=0.6, linewidth=1)
            ax.text(ph, ax.get_ylim()[1] * 0.9 if hist.max() > 0 else 1,
                    f"{peak['mean_hour']:.1f}h\n±{peak['std_hour']:.1f}",
                    fontsize=6, ha='center', color='red')

        # Shade mealtime zones
        for zone_name, (s, e) in MEALTIME_ZONES.items():
            ax.axvspan(s - 0.5, e - 0.5, alpha=0.06, color='gold')

        ent = pp['normalized_entropy']
        ws = pp['weighted_mean_std']
        ax.set_title(f'{pat}  (n={pp["n_meals"]}, std={ws:.1f}h, H={ent:.2f})',
                     fontsize=9)
        ax.set_xlim(-0.5, 23.5)
        ax.set_xticks(range(0, 24, 6))
        ax.tick_params(labelsize=7)
        if idx // cols == rows - 1:
            ax.set_xlabel('Hour', fontsize=8)

    # Hide empty subplots
    for idx in range(n_pats, rows * cols):
        axes[idx // cols, idx % cols].set_visible(False)

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plt.savefig(str(VIZ_DIR / 'fig25_personal_meal_clocks.png'), dpi=150)
    plt.close()
    print("    ✓ fig25_personal_meal_clocks.png")

    # ── Figure 26: Inter-patient variation summary ───────────────────
    fig, axes = plt.subplots(1, 3, figsize=(17, 5.5))
    fig.suptitle('EXP-1567: Inter-Patient Variation in Meal Regularity',
                 fontsize=13, fontweight='bold')

    # Panel A: Weighted std per patient (clock tightness)
    ax = axes[0]
    stds = [per_patient[p]['weighted_mean_std'] for p in pat_names]
    colors_a = [cmap(i % 10) for i in range(n_pats)]
    bars = ax.barh(pat_names, stds, color=colors_a, alpha=0.8, edgecolor='black',
                   linewidth=0.5)
    ax.axvline(x=np.mean(stds), color='black', linestyle='--', alpha=0.5,
               label=f'Mean={np.mean(stds):.2f}h')
    ax.set_xlabel('Weighted Mean Std(Hour)')
    ax.set_title('A) Meal Clock Tightness\n(lower = more regular)')
    ax.legend(fontsize=8)
    ax.grid(axis='x', alpha=0.3)
    for b, v in zip(bars, stds):
        ax.text(v + 0.02, b.get_y() + b.get_height() / 2,
                f'{v:.2f}h', va='center', fontsize=8)

    # Panel B: Per-zone within-patient std
    ax = axes[1]
    zone_colors = {'breakfast': '#FF9F1C', 'lunch': '#2EC4B6', 'dinner': '#E71D36'}
    x = np.arange(n_pats)
    width = 0.25
    for zi, zone_name in enumerate(MEALTIME_ZONES):
        zone_stds = []
        for pat in pat_names:
            zr = per_patient[pat]['zone_regularity'].get(zone_name, {})
            zone_stds.append(zr.get('std_hour', float('nan')))
        ax.bar(x + zi * width, zone_stds, width, label=zone_name.capitalize(),
               color=zone_colors[zone_name], alpha=0.8)

    ax.set_xticks(x + width)
    ax.set_xticklabels(pat_names, fontsize=9)
    ax.set_ylabel('Std(Hour) within Zone')
    ax.set_title('B) Within-Zone Regularity by Patient')
    ax.legend(fontsize=8)
    ax.grid(axis='y', alpha=0.3)

    # Panel C: Within_3hr_pct per zone per patient (heatmap)
    ax = axes[2]
    matrix = np.full((n_pats, 3), np.nan)
    zone_list = list(MEALTIME_ZONES.keys())
    for pi, pat in enumerate(pat_names):
        for zi, zone_name in enumerate(zone_list):
            zr = per_patient[pat]['zone_regularity'].get(zone_name, {})
            val = zr.get('within_3hr_pct')
            if val is not None:
                matrix[pi, zi] = val

    im = ax.imshow(matrix, aspect='auto', cmap='RdYlGn', vmin=40, vmax=100)
    ax.set_xticks(range(3))
    ax.set_xticklabels([z.capitalize() for z in zone_list])
    ax.set_yticks(range(n_pats))
    ax.set_yticklabels(pat_names)
    ax.set_title('C) % Meals Within ±1.5h of Mean')
    for pi in range(n_pats):
        for zi in range(3):
            val = matrix[pi, zi]
            if not np.isnan(val):
                color = 'white' if val < 60 else 'black'
                ax.text(zi, pi, f'{val:.0f}%', ha='center', va='center',
                        fontsize=8, color=color)
    plt.colorbar(im, ax=ax, shrink=0.8)

    plt.tight_layout(rect=[0, 0, 1, 0.93])
    plt.savefig(str(VIZ_DIR / 'fig26_interpatient_variation.png'), dpi=150)
    plt.close()
    print("    ✓ fig26_interpatient_variation.png")

    # ── Figure 27: Weekday vs weekend regularity per patient/zone ────
    wd_we = r.get('wd_we_regularity_comparison', [])
    if wd_we:
        fig, axes = plt.subplots(1, 3, figsize=(17, 5.5))
        fig.suptitle('EXP-1567: Weekday vs Weekend Regularity (Per Patient × Zone)',
                     fontsize=13, fontweight='bold')

        # Panel A: Scatter of WD std vs WE std
        ax = axes[0]
        for zone_name in zone_list:
            zone_pts = [x for x in wd_we if x['zone'] == zone_name]
            if zone_pts:
                wd_s = [x['wd_std'] for x in zone_pts]
                we_s = [x['we_std'] for x in zone_pts]
                ax.scatter(wd_s, we_s, label=zone_name.capitalize(),
                           color=zone_colors[zone_name], s=60, alpha=0.7,
                           edgecolors='black', linewidth=0.5)
                for x_pt in zone_pts:
                    ax.annotate(x_pt['patient'], (x_pt['wd_std'], x_pt['we_std']),
                                fontsize=6, textcoords='offset points', xytext=(3, 3))
        max_val = max(max(x['wd_std'] for x in wd_we), max(x['we_std'] for x in wd_we)) * 1.1
        ax.plot([0, max_val], [0, max_val], 'k--', alpha=0.3, label='Equal')
        ax.set_xlabel('Weekday Std(Hour)')
        ax.set_ylabel('Weekend Std(Hour)')
        ax.set_title('A) Regularity: WD vs WE\n(above line = less regular on weekends)')
        ax.legend(fontsize=7)
        ax.grid(alpha=0.3)

        # Panel B: Std delta bars per patient (grouped by zone)
        ax = axes[1]
        zone_data = {z: [] for z in zone_list}
        zone_pats = {z: [] for z in zone_list}
        for x_pt in wd_we:
            zone_data[x_pt['zone']].append(x_pt['std_delta'])
            zone_pats[x_pt['zone']].append(x_pt['patient'])

        y_pos = 0
        y_ticks = []
        y_labels = []
        for zone_name in zone_list:
            deltas = zone_data[zone_name]
            pats = zone_pats[zone_name]
            for i, (d, p) in enumerate(zip(deltas, pats)):
                color = '#C44E52' if d > 0 else '#4C72B0'
                ax.barh(y_pos, d, color=color, alpha=0.7, height=0.7)
                ax.text(d + (0.02 if d >= 0 else -0.02), y_pos,
                        f'{p}', va='center', ha='left' if d >= 0 else 'right',
                        fontsize=7)
                y_pos += 1
            # Zone separator
            if zone_name != zone_list[-1]:
                ax.axhline(y=y_pos - 0.5, color='gray', linestyle='-', alpha=0.3)
            y_ticks.append(y_pos - len(deltas) / 2 - 0.5)
            y_labels.append(zone_name.capitalize())
            y_pos += 0.5

        ax.axvline(x=0, color='black', linewidth=0.8)
        ax.set_xlabel('ΔStd(Hour) (Weekend − Weekday)')
        ax.set_title('B) Regularity Change\n(>0 = less regular on weekends)')
        ax.grid(axis='x', alpha=0.3)

        # Panel C: Mean hour shift bars per patient/zone
        ax = axes[2]
        y_pos = 0
        for zone_name in zone_list:
            shifts = [x['mean_shift'] for x in wd_we if x['zone'] == zone_name]
            pats_z = [x['patient'] for x in wd_we if x['zone'] == zone_name]
            for i, (s, p) in enumerate(zip(shifts, pats_z)):
                color = '#C44E52' if s > 0 else '#4C72B0'
                ax.barh(y_pos, s * 60, color=color, alpha=0.7, height=0.7)
                ax.text(s * 60 + (1 if s >= 0 else -1), y_pos,
                        f'{p}', va='center', ha='left' if s >= 0 else 'right',
                        fontsize=7)
                y_pos += 1
            if zone_name != zone_list[-1]:
                ax.axhline(y=y_pos - 0.5, color='gray', linestyle='-', alpha=0.3)
            y_pos += 0.5

        ax.axvline(x=0, color='black', linewidth=0.8)
        ax.set_xlabel('Meal Time Shift (minutes, Weekend − Weekday)')
        ax.set_title('C) Per-Patient Timing Shift\n(>0 = later on weekends)')
        ax.grid(axis='x', alpha=0.3)

        plt.tight_layout(rect=[0, 0, 1, 0.93])
        plt.savefig(str(VIZ_DIR / 'fig27_wd_we_regularity.png'), dpi=150)
        plt.close()
        print("    ✓ fig27_wd_we_regularity.png")


def generate_benchmark_visualizations(results):
    """Generate fig28-33 for EXP-1569 detection sensitivity benchmark."""
    if 1569 not in results or '_grid' not in results[1569]:
        return

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    d = results[1569]
    grid = d['_grid']
    mc_vals = d['min_carb_values']
    hyst_vals = d['hysteresis_values']

    # Build 2D arrays for heatmaps
    mc_idx = {v: i for i, v in enumerate(mc_vals)}
    hy_idx = {v: i for i, v in enumerate(hyst_vals)}
    mpd_map = np.full((len(mc_vals), len(hyst_vals)), np.nan)
    std_map = np.full((len(mc_vals), len(hyst_vals)), np.nan)
    ent_map = np.full((len(mc_vals), len(hyst_vals)), np.nan)
    zf_map = np.full((len(mc_vals), len(hyst_vals)), np.nan)
    cpd_map = np.full((len(mc_vals), len(hyst_vals)), np.nan)
    isf_map = np.full((len(mc_vals), len(hyst_vals)), np.nan)

    for g in grid:
        r, c = mc_idx[g['min_carb_g']], hy_idx[g['hysteresis_min']]
        mpd_map[r, c] = g['meals_per_day']
        std_map[r, c] = g['mean_patient_std'] if not np.isnan(g['mean_patient_std']) else np.nan
        ent_map[r, c] = g['pop_entropy'] if not np.isnan(g['pop_entropy']) else np.nan
        zf_map[r, c] = g['zone_fraction_pct']
        cpd_map[r, c] = g['size']['total_carbs_per_day']
        isf_map[r, c] = g['metabolic']['mean_isf_norm']

    mc_labels = [str(v) for v in mc_vals]
    hy_labels = [str(v) for v in hyst_vals]

    # --- fig28: Meals/day heatmap ---
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    fig.suptitle('EXP-1569: Detection Parameter Sweep — Count & Structure', fontsize=14)

    im0 = axes[0].imshow(mpd_map, aspect='auto', cmap='YlOrRd')
    axes[0].set_xticks(range(len(hy_labels)))
    axes[0].set_xticklabels(hy_labels)
    axes[0].set_yticks(range(len(mc_labels)))
    axes[0].set_yticklabels(mc_labels)
    axes[0].set_xlabel('Hysteresis (min)')
    axes[0].set_ylabel('Min Carbs (g)')
    axes[0].set_title('A) Meals per Day')
    for i in range(len(mc_vals)):
        for j in range(len(hyst_vals)):
            v = mpd_map[i, j]
            if not np.isnan(v):
                axes[0].text(j, i, f'{v:.1f}', ha='center', va='center', fontsize=6)
    plt.colorbar(im0, ax=axes[0], shrink=0.8)

    im1 = axes[1].imshow(zf_map, aspect='auto', cmap='YlGn')
    axes[1].set_xticks(range(len(hy_labels)))
    axes[1].set_xticklabels(hy_labels)
    axes[1].set_yticks(range(len(mc_labels)))
    axes[1].set_yticklabels(mc_labels)
    axes[1].set_xlabel('Hysteresis (min)')
    axes[1].set_ylabel('Min Carbs (g)')
    axes[1].set_title('B) Zone Fraction (%)')
    for i in range(len(mc_vals)):
        for j in range(len(hyst_vals)):
            v = zf_map[i, j]
            if not np.isnan(v):
                axes[1].text(j, i, f'{v:.0f}', ha='center', va='center', fontsize=6)
    plt.colorbar(im1, ax=axes[1], shrink=0.8)

    im2 = axes[2].imshow(cpd_map, aspect='auto', cmap='Blues')
    axes[2].set_xticks(range(len(hy_labels)))
    axes[2].set_xticklabels(hy_labels)
    axes[2].set_yticks(range(len(mc_labels)))
    axes[2].set_yticklabels(mc_labels)
    axes[2].set_xlabel('Hysteresis (min)')
    axes[2].set_ylabel('Min Carbs (g)')
    axes[2].set_title('C) Total Carbs/Day')
    for i in range(len(mc_vals)):
        for j in range(len(hyst_vals)):
            v = cpd_map[i, j]
            if not np.isnan(v):
                axes[2].text(j, i, f'{v:.0f}', ha='center', va='center', fontsize=6)
    plt.colorbar(im2, ax=axes[2], shrink=0.8)

    plt.tight_layout(rect=[0, 0, 1, 0.93])
    plt.savefig(str(VIZ_DIR / 'fig28_benchmark_count_structure.png'), dpi=150)
    plt.close()
    print("    ✓ fig28_benchmark_count_structure.png")

    # --- fig29: Regularity heatmaps ---
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    fig.suptitle('EXP-1569: Detection Parameter Sweep — Regularity Metrics', fontsize=14)

    im0 = axes[0].imshow(std_map, aspect='auto', cmap='RdYlGn_r')
    axes[0].set_xticks(range(len(hy_labels)))
    axes[0].set_xticklabels(hy_labels)
    axes[0].set_yticks(range(len(mc_labels)))
    axes[0].set_yticklabels(mc_labels)
    axes[0].set_xlabel('Hysteresis (min)')
    axes[0].set_ylabel('Min Carbs (g)')
    axes[0].set_title('A) Mean Patient Weighted Std (h)\n(lower = more regular)')
    for i in range(len(mc_vals)):
        for j in range(len(hyst_vals)):
            v = std_map[i, j]
            if not np.isnan(v):
                axes[0].text(j, i, f'{v:.1f}', ha='center', va='center', fontsize=6)
    plt.colorbar(im0, ax=axes[0], shrink=0.8)

    im1 = axes[1].imshow(ent_map, aspect='auto', cmap='RdYlGn_r')
    axes[1].set_xticks(range(len(hy_labels)))
    axes[1].set_xticklabels(hy_labels)
    axes[1].set_yticks(range(len(mc_labels)))
    axes[1].set_yticklabels(mc_labels)
    axes[1].set_xlabel('Hysteresis (min)')
    axes[1].set_ylabel('Min Carbs (g)')
    axes[1].set_title('B) Population Entropy\n(lower = more periodic)')
    for i in range(len(mc_vals)):
        for j in range(len(hyst_vals)):
            v = ent_map[i, j]
            if not np.isnan(v):
                axes[1].text(j, i, f'{v:.2f}', ha='center', va='center', fontsize=6)
    plt.colorbar(im1, ax=axes[1], shrink=0.8)

    im2 = axes[2].imshow(isf_map, aspect='auto', cmap='YlOrRd')
    axes[2].set_xticks(range(len(hy_labels)))
    axes[2].set_xticklabels(hy_labels)
    axes[2].set_yticks(range(len(mc_labels)))
    axes[2].set_yticklabels(mc_labels)
    axes[2].set_xlabel('Hysteresis (min)')
    axes[2].set_ylabel('Min Carbs (g)')
    axes[2].set_title('C) Mean ISF-Norm Excursion')
    for i in range(len(mc_vals)):
        for j in range(len(hyst_vals)):
            v = isf_map[i, j]
            if not np.isnan(v):
                axes[2].text(j, i, f'{v:.2f}', ha='center', va='center', fontsize=6)
    plt.colorbar(im2, ax=axes[2], shrink=0.8)

    plt.tight_layout(rect=[0, 0, 1, 0.93])
    plt.savefig(str(VIZ_DIR / 'fig29_benchmark_regularity.png'), dpi=150)
    plt.close()
    print("    ✓ fig29_benchmark_regularity.png")

    # --- fig30: Regularity vs meals/day "knee" curve ---
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle('EXP-1569: Regularity vs Detection Sensitivity', fontsize=14)

    mpd_arr = [g['meals_per_day'] for g in grid]
    std_arr = [g['mean_patient_std'] for g in grid]
    colors_mc = [g['min_carb_g'] for g in grid]

    sc = axes[0].scatter(mpd_arr, std_arr, c=colors_mc, cmap='viridis',
                         s=40, alpha=0.7, edgecolors='k', linewidths=0.3)
    axes[0].set_xlabel('Meals per Day')
    axes[0].set_ylabel('Mean Patient Weighted Std (h)')
    axes[0].set_title('A) Regularity vs Count\n(each point = one config)')
    axes[0].grid(alpha=0.3)
    cb = plt.colorbar(sc, ax=axes[0])
    cb.set_label('Min Carbs (g)')

    # Mark the 3 canonical configs
    canonical = {'A': (5, 30), 'B': (5, 90), 'C': (18, 90)}
    for label, (mc, hy) in canonical.items():
        match = [g for g in grid if g['min_carb_g'] == mc and g['hysteresis_min'] == hy]
        if match:
            g = match[0]
            axes[0].annotate(label, (g['meals_per_day'], g['mean_patient_std']),
                             fontsize=11, fontweight='bold', color='red',
                             textcoords='offset points', xytext=(8, 4))

    # Knee annotation
    knee = d['hypothesis_tests'].get('H2_knee_config')
    if knee:
        axes[0].axhline(knee['mean_patient_std'], color='red', ls='--', alpha=0.4)
        axes[0].axvline(knee['meals_per_day'], color='red', ls='--', alpha=0.4)

    # Right panel: color by hysteresis
    colors_hy = [g['hysteresis_min'] for g in grid]
    sc2 = axes[1].scatter(mpd_arr, std_arr, c=colors_hy, cmap='plasma',
                          s=40, alpha=0.7, edgecolors='k', linewidths=0.3)
    axes[1].set_xlabel('Meals per Day')
    axes[1].set_ylabel('Mean Patient Weighted Std (h)')
    axes[1].set_title('B) Same data, colored by hysteresis')
    axes[1].grid(alpha=0.3)
    cb2 = plt.colorbar(sc2, ax=axes[1])
    cb2.set_label('Hysteresis (min)')

    plt.tight_layout(rect=[0, 0, 1, 0.93])
    plt.savefig(str(VIZ_DIR / 'fig30_benchmark_knee.png'), dpi=150)
    plt.close()
    print("    ✓ fig30_benchmark_knee.png")

    # --- fig31: Per-patient regularity trajectories ---
    all_pats = sorted(set(p for g in grid for p in g['per_patient']))
    n_pats = len(all_pats)
    cols = 4
    rows = (n_pats + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(16, 3.5 * rows))
    fig.suptitle('EXP-1569: Per-Patient Regularity Across Configs', fontsize=14)
    axes_flat = axes.flatten() if n_pats > 1 else [axes]

    for idx, pat in enumerate(all_pats):
        ax = axes_flat[idx]
        # Group by min_carb, plot std vs hysteresis
        for mc in mc_vals:
            mc_grid = sorted([g for g in grid if g['min_carb_g'] == mc
                              and pat in g['per_patient']],
                             key=lambda g: g['hysteresis_min'])
            if not mc_grid:
                continue
            xs = [g['hysteresis_min'] for g in mc_grid]
            ys = [g['per_patient'][pat]['weighted_std'] for g in mc_grid]
            ax.plot(xs, ys, marker='.', markersize=4, label=f'{mc}g', alpha=0.7)
        ax.set_title(f'Patient {pat}', fontsize=10)
        ax.set_xlabel('Hysteresis (min)', fontsize=8)
        ax.set_ylabel('Weighted Std (h)', fontsize=8)
        ax.tick_params(labelsize=7)
        ax.grid(alpha=0.3)
        if idx == 0:
            ax.legend(fontsize=6, ncol=3, title='min_carb', title_fontsize=6)

    for idx in range(len(all_pats), len(axes_flat)):
        axes_flat[idx].set_visible(False)

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plt.savefig(str(VIZ_DIR / 'fig31_benchmark_per_patient.png'), dpi=150)
    plt.close()
    print("    ✓ fig31_benchmark_per_patient.png")

    # --- fig32: Meal size distributions for selected configs ---
    selected = [
        ('0g/15m', 0, 15), ('5g/30m (A)', 5, 30), ('5g/90m (B)', 5, 90),
        ('18g/90m (C)', 18, 90), ('30g/90m', 30, 90), ('40g/180m', 40, 180),
    ]
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle('EXP-1569: Meal Size Distributions by Config', fontsize=14)

    box_data = []
    box_labels = []
    for label, mc, hy in selected:
        match = [g for g in grid if g['min_carb_g'] == mc and g['hysteresis_min'] == hy]
        if match:
            g = match[0]
            carbs = [r['carbs_g'] for pat in g['per_patient']
                     for r in [rr for rr in [{'carbs_g': g['size']['mean']}]]]
            box_data.append([g['size']['p25'], g['size']['median'],
                            g['size']['mean'], g['size']['p75']])
            box_labels.append(f"{label}\n(n={g['n_meals']})")

    # Bar chart of median & mean
    x = np.arange(len(box_labels))
    medians = [bd[1] for bd in box_data]
    means = [bd[2] for bd in box_data]
    p25s = [bd[0] for bd in box_data]
    p75s = [bd[3] for bd in box_data]

    axes[0].bar(x - 0.15, medians, 0.3, label='Median', color='steelblue')
    axes[0].bar(x + 0.15, means, 0.3, label='Mean', color='coral')
    axes[0].errorbar(x - 0.15, medians, yerr=[np.array(medians) - np.array(p25s),
                     np.array(p75s) - np.array(medians)],
                     fmt='none', color='black', capsize=3)
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(box_labels, fontsize=8)
    axes[0].set_ylabel('Carbs (g)')
    axes[0].set_title('A) Meal Size Summary')
    axes[0].legend()
    axes[0].grid(axis='y', alpha=0.3)

    # Total carbs/day across configs
    cpd_by_mc = {}
    for g in grid:
        cpd_by_mc.setdefault(g['min_carb_g'], []).append(
            (g['hysteresis_min'], g['size']['total_carbs_per_day']))
    for mc in sorted(cpd_by_mc.keys()):
        pts = sorted(cpd_by_mc[mc])
        axes[1].plot([p[0] for p in pts], [p[1] for p in pts],
                     marker='o', markersize=4, label=f'{mc}g')
    axes[1].set_xlabel('Hysteresis (min)')
    axes[1].set_ylabel('Total Carbs per Day (g)')
    axes[1].set_title('B) Carb Conservation Test (H5)')
    axes[1].legend(fontsize=7, ncol=3, title='min_carb')
    axes[1].grid(alpha=0.3)

    plt.tight_layout(rect=[0, 0, 1, 0.93])
    plt.savefig(str(VIZ_DIR / 'fig32_benchmark_size.png'), dpi=150)
    plt.close()
    print("    ✓ fig32_benchmark_size.png")

    # --- fig33: Patient robustness ranking ---
    h3 = d['hypothesis_tests'].get('H3_patient_robustness', {})
    if h3:
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))
        fig.suptitle('EXP-1569: Patient Threshold Robustness (H3)', fontsize=14)

        pats = sorted(h3.keys())
        mean_stds = [h3[p]['mean_std'] for p in pats]
        std_of_stds = [h3[p]['std_of_std'] for p in pats]

        axes[0].barh(pats, mean_stds, xerr=std_of_stds, color='steelblue',
                     edgecolor='black', capsize=3)
        axes[0].set_xlabel('Mean Weighted Std Across Configs (h)')
        axes[0].set_title('A) Mean Regularity ± Variability')
        axes[0].grid(axis='x', alpha=0.3)

        axes[1].barh(pats, std_of_stds, color='coral', edgecolor='black')
        axes[1].set_xlabel('Std of Weighted Std Across Configs (h)')
        axes[1].set_title('B) Threshold Sensitivity\n(lower = more robust)')
        axes[1].grid(axis='x', alpha=0.3)

        plt.tight_layout(rect=[0, 0, 1, 0.93])
        plt.savefig(str(VIZ_DIR / 'fig33_benchmark_robustness.png'), dpi=150)
        plt.close()
        print("    ✓ fig33_benchmark_robustness.png")


def generate_archetype_visualizations(results):
    """Generate fig34-36 for EXP-1571 robustness archetype characterization."""
    if 1571 not in results or 'per_patient' not in results[1571]:
        return

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    d = results[1571]
    traits = d['per_patient']
    tiers = d['tier_summaries']
    curves = d.get('_stability_curves', {})
    corrs = d.get('correlations_with_sigma_sigma', {})

    pats = sorted(traits.keys())
    tier_colors = {'robust': '#2ecc71', 'moderate': '#f39c12', 'sensitive': '#e74c3c'}

    # --- fig34: Robustness distribution + correlation scatter ---
    fig, axes = plt.subplots(1, 3, figsize=(18, 5.5))
    fig.suptitle('EXP-1571: Meal-Clock Robustness Archetypes', fontsize=14)

    # A) σσ distribution with tier boundaries
    ss_vals = [traits[p]['sigma_sigma'] for p in pats]
    colors = [tier_colors[traits[p]['tier']] for p in pats]
    axes[0].barh(pats, ss_vals, color=colors, edgecolor='black', linewidth=0.5)
    axes[0].axvline(0.6, color='orange', ls='--', alpha=0.7, label='Robust/Moderate')
    axes[0].axvline(1.0, color='red', ls='--', alpha=0.7, label='Moderate/Sensitive')
    axes[0].set_xlabel('σσ (Std of Weighted Std Across 72 Configs)')
    axes[0].set_title('A) Robustness Distribution\n(lower = more robust)')
    axes[0].legend(fontsize=7)
    axes[0].grid(axis='x', alpha=0.3)

    # B) σσ vs n_peaks (strongest correlate)
    n_peaks = [traits[p]['n_peaks'] for p in pats]
    for p in pats:
        axes[1].scatter(traits[p]['n_peaks'], traits[p]['sigma_sigma'],
                       c=tier_colors[traits[p]['tier']], s=80, edgecolors='black',
                       linewidths=0.5, zorder=3)
        axes[1].annotate(p, (traits[p]['n_peaks'], traits[p]['sigma_sigma']),
                        fontsize=8, textcoords='offset points', xytext=(5, 3))
    rho = corrs.get('n_peaks', {}).get('spearman_rho', '?')
    pval = corrs.get('n_peaks', {}).get('p_value', '?')
    axes[1].set_xlabel('Number of Personal Meal Peaks')
    axes[1].set_ylabel('σσ (Robustness)')
    axes[1].set_title(f'B) σσ vs Meal Peaks\n(ρ={rho}, p={pval})')
    axes[1].grid(alpha=0.3)

    # C) σσ vs mean_std (regularity vs robustness 2D)
    for p in pats:
        axes[2].scatter(traits[p]['mean_std'], traits[p]['sigma_sigma'],
                       c=tier_colors[traits[p]['tier']], s=80, edgecolors='black',
                       linewidths=0.5, zorder=3)
        axes[2].annotate(p, (traits[p]['mean_std'], traits[p]['sigma_sigma']),
                        fontsize=8, textcoords='offset points', xytext=(5, 3))
    # Quadrant labels
    axes[2].axhline(0.6, color='gray', ls=':', alpha=0.5)
    axes[2].axvline(3.0, color='gray', ls=':', alpha=0.5)
    axes[2].text(1.5, 0.2, 'Regular &\nRobust', ha='center', fontsize=7, color='green', alpha=0.7)
    axes[2].text(5.0, 0.2, 'Irregular but\nConsistent', ha='center', fontsize=7, color='orange', alpha=0.7)
    axes[2].text(1.5, 1.8, 'Regular but\nFragile', ha='center', fontsize=7, color='orange', alpha=0.7)
    axes[2].text(5.0, 1.8, 'Irregular &\nUnstable', ha='center', fontsize=7, color='red', alpha=0.7)
    axes[2].set_xlabel('Mean Weighted Std (h) — Regularity')
    axes[2].set_ylabel('σσ — Robustness')
    axes[2].set_title('C) Regularity × Robustness Quadrants')
    axes[2].grid(alpha=0.3)

    plt.tight_layout(rect=[0, 0, 1, 0.93])
    plt.savefig(str(VIZ_DIR / 'fig34_archetype_distribution.png'), dpi=150)
    plt.close()
    print("    ✓ fig34_archetype_distribution.png")

    # --- fig35: Stability curves (per-patient regularity vs strictness) ---
    if curves:
        fig, axes = plt.subplots(3, 4, figsize=(18, 12))
        fig.suptitle('EXP-1571: Per-Patient Stability Curves\n'
                     '(Weighted Std vs Detection Strictness)', fontsize=14)
        axes_flat = axes.flatten()

        for idx, pat in enumerate(sorted(curves.keys())):
            ax = axes_flat[idx]
            curve = curves[pat]
            if not curve:
                ax.set_visible(False)
                continue

            xs = [c['strictness'] for c in curve]
            ys = [c['weighted_std'] for c in curve]
            tier = traits[pat]['tier']
            ax.plot(xs, ys, 'o-', color=tier_colors[tier], markersize=3, alpha=0.7)
            ax.fill_between(xs, ys, alpha=0.15, color=tier_colors[tier])
            ax.set_title(f'{pat} ({tier}, σσ={traits[pat]["sigma_sigma"]:.2f})',
                        fontsize=9, color=tier_colors[tier])
            ax.set_xlabel('Strictness', fontsize=7)
            ax.set_ylabel('Weighted Std (h)', fontsize=7)
            ax.tick_params(labelsize=7)
            ax.set_ylim(bottom=0)
            ax.grid(alpha=0.3)

        # Hide unused subplot
        for idx in range(len(curves), len(axes_flat)):
            axes_flat[idx].set_visible(False)

        plt.tight_layout(rect=[0, 0, 1, 0.94])
        plt.savefig(str(VIZ_DIR / 'fig35_stability_curves.png'), dpi=150)
        plt.close()
        print("    ✓ fig35_stability_curves.png")

    # --- fig36: Tier comparison radar/bar chart ---
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle('EXP-1571: Robustness Tier Profiles', fontsize=14)

    tier_names = ['robust', 'moderate', 'sensitive']
    tier_data = {t: tiers.get(t, {}) for t in tier_names}
    x = np.arange(len(tier_names))

    # A) Tier comparison bars
    metrics = [
        ('mean_sigma_sigma', 'Mean σσ', 'steelblue'),
        ('mean_n_peaks', 'Mean Peaks', 'coral'),
        ('mean_therapy_mpd', 'Mean MPD', 'green'),
        ('mean_zones_covered', 'Mean Zones', 'purple'),
    ]
    width = 0.18
    for mi, (key, label, color) in enumerate(metrics):
        vals = [tier_data[t].get(key, 0) for t in tier_names]
        axes[0].bar(x + mi * width - 0.27, vals, width, label=label, color=color, alpha=0.8)

    axes[0].set_xticks(x)
    xl = []
    for t in tier_names:
        n = tier_data[t].get('n', 0)
        members = tier_data[t].get('members', [])
        xl.append(f'{t.capitalize()}\n(n={n}: {",".join(members)})')
    axes[0].set_xticklabels(xl, fontsize=8)
    axes[0].set_ylabel('Value')
    axes[0].set_title('A) Tier Metric Comparison')
    axes[0].legend(fontsize=8)
    axes[0].grid(axis='y', alpha=0.3)

    # B) Correlation waterfall
    sorted_corrs = sorted(corrs.items(), key=lambda x: abs(x[1]['spearman_rho']), reverse=True)
    corr_names = [c[0].replace('_', '\n') for c in sorted_corrs]
    corr_vals = [c[1]['spearman_rho'] for c in sorted_corrs]
    corr_sig = [c[1]['p_value'] < 0.05 for c in sorted_corrs]
    bar_colors = ['darkgreen' if (v < 0 and s) else 'darkred' if (v > 0 and s)
                  else 'gray' for v, s in zip(corr_vals, corr_sig)]

    axes[1].barh(range(len(corr_names)), corr_vals, color=bar_colors, edgecolor='black',
                 linewidth=0.5)
    axes[1].set_yticks(range(len(corr_names)))
    axes[1].set_yticklabels(corr_names, fontsize=8)
    axes[1].set_xlabel('Spearman ρ with σσ')
    axes[1].set_title('B) What Predicts Robustness?\n(green=protective, red=harmful)')
    axes[1].axvline(0, color='black', linewidth=0.5)
    axes[1].grid(axis='x', alpha=0.3)

    plt.tight_layout(rect=[0, 0, 1, 0.93])
    plt.savefig(str(VIZ_DIR / 'fig36_tier_profiles.png'), dpi=150)
    plt.close()
    print("    ✓ fig36_tier_profiles.png")


def main():
    parser = argparse.ArgumentParser(description='EXP-1551-1571: Natural Experiment Census')
    parser.add_argument('--exp', type=int, default=0, help='Run single experiment (0=all)')
    parser.add_argument('--max-patients', type=int, default=11)
    parser.add_argument('--patients-dir', type=str, default=None)
    parser.add_argument('--no-viz', action='store_true', help='Skip visualizations')
    args = parser.parse_args()

    _patients_dir = args.patients_dir

    print(f"\n{'='*70}")
    print(f"EXP-1551-1559: Natural Experiment Census & Characterization")
    print(f"{'='*70}\n")

    patients = load_patients(args.max_patients, _patients_dir)
    print(f"Loaded {len(patients)} patients\n")

    os.makedirs(str(RESULTS_DIR), exist_ok=True)
    all_results = {}

    if args.exp == 0:
        run_ids = sorted(EXPERIMENTS.keys())
    else:
        run_ids = [args.exp]

    for exp_id in run_ids:
        if exp_id not in EXPERIMENTS:
            print(f"  Unknown experiment: {exp_id}")
            continue
        title, fn = EXPERIMENTS[exp_id]
        print(f"\n{'─'*60}")
        print(f"EXP-{exp_id}: {title}")
        print(f"{'─'*60}")

        # Reset cache between experiments so 1551 populates it
        global _CACHED_EXPERIMENTS
        if exp_id == 1551:
            _CACHED_EXPERIMENTS = None

        t0 = time.time()
        try:
            result = fn(patients)
            elapsed = time.time() - t0
            result['elapsed_seconds'] = round(elapsed, 1)
            all_results[exp_id] = result

            out_path = RESULTS_DIR / f'exp-{exp_id}_natural_experiments.json'
            with open(str(out_path), 'w') as f:
                # For 1551, skip all_experiments (too large) — save summary only
                # For 1561, skip meal_records (large per-meal detail)
                skip_keys = set()
                if exp_id == 1551:
                    skip_keys.add('all_experiments')
                if exp_id == 1561:
                    skip_keys.add('meal_records')
                if exp_id == 1563:
                    skip_keys.add('_config_records')
                if exp_id == 1565:
                    skip_keys.add('_records')
                if exp_id == 1569:
                    skip_keys.add('_grid')
                if exp_id == 1571:
                    skip_keys.add('_stability_curves')
                save_result = {k: v for k, v in result.items() if k not in skip_keys}
                json.dump(save_result, f, indent=2, default=str)
            print(f"  ✓ Saved → {out_path}  ({elapsed:.1f}s)")
        except Exception as e:
            print(f"  ✗ FAILED: {e}")
            traceback.print_exc()
            all_results[exp_id] = {'error': str(e)}

    # Visualizations
    if not args.no_viz and len(all_results) > 0:
        print(f"\n{'─'*60}")
        print("Generating visualizations...")
        print(f"{'─'*60}")
        try:
            generate_visualizations(all_results, patients)
        except Exception as e:
            print(f"  Visualization error: {e}")
            traceback.print_exc()
        try:
            generate_sensitivity_visualizations(all_results)
        except Exception as e:
            print(f"  Sensitivity visualization error: {e}")
            traceback.print_exc()
        try:
            generate_metabolic_visualizations(all_results)
        except Exception as e:
            print(f"  Metabolic visualization error: {e}")
            traceback.print_exc()
        try:
            generate_multiconfig_visualizations(all_results)
        except Exception as e:
            print(f"  Multi-config visualization error: {e}")
            traceback.print_exc()
        try:
            generate_weekday_weekend_visualizations(all_results)
        except Exception as e:
            print(f"  Weekday/weekend visualization error: {e}")
            traceback.print_exc()
        try:
            generate_within_patient_visualizations(all_results)
        except Exception as e:
            print(f"  Within-patient visualization error: {e}")
            traceback.print_exc()
        try:
            generate_benchmark_visualizations(all_results)
        except Exception as e:
            print(f"  Benchmark visualization error: {e}")
            traceback.print_exc()
        try:
            generate_archetype_visualizations(all_results)
        except Exception as e:
            print(f"  Archetype visualization error: {e}")
            traceback.print_exc()

    # Summary
    print(f"\n{'='*70}")
    print(f"SUMMARY: {len(all_results)}/{len(run_ids)} experiments completed")
    print(f"{'='*70}")

    if 1551 in all_results and 'population_summary' in all_results[1551]:
        pop = all_results[1551]['population_summary']
        total = all_results[1551].get('total_experiments_detected', 0)
        print(f"\n  Total natural experiments detected: {total:,}")
        print(f"\n  {'Type':15s} {'Count':>7s} {'Quality':>8s} {'Med Duration':>12s}")
        print(f"  {'─'*45}")
        for etype, stats in sorted(pop.items()):
            print(f"  {etype:15s} {stats['total_count']:7,d} "
                  f"{stats['mean_quality']:8.3f} "
                  f"{stats['median_duration_min']:10.0f}m")

    if 1559 in all_results and 'configs' in all_results[1559]:
        print(f"\n  Meal Detection Sensitivity (EXP-1559):")
        print(f"  {'Config':25s} {'Meals':>7s} {'Quality':>8s} {'Carbs(g)':>9s} {'Excursion':>10s}")
        print(f"  {'─'*62}")
        for cfg_name, cfg_data in all_results[1559]['configs'].items():
            p = cfg_data['population']
            print(f"  {cfg_name:25s} {cfg_data['total_meals']:7,d} "
                  f"{p['mean_quality']:8.3f} "
                  f"{p['mean_carbs_g']:9.1f} "
                  f"{p['mean_excursion']:10.1f}")

    if 1561 in all_results and 'by_carb_range' in all_results[1561]:
        print(f"\n  Meal Metabolic Characterization (EXP-1561):")
        print(f"  {'Carb Range':10s} {'n':>5s} {'RawExc':>8s} {'ISFNorm':>8s} {'SpecPow':>10s}")
        print(f"  {'─'*45}")
        for rng, stats in all_results[1561]['by_carb_range'].items():
            if stats.get('n', 0) == 0:
                continue
            print(f"  {rng:10s} {stats['n']:5d} "
                  f"{stats['raw_excursion_median']:8.1f} "
                  f"{stats['isf_norm_median']:8.3f} "
                  f"{stats['spectral_power_median']:10.1f}")
        corr = all_results[1561].get('correlations', {})
        if corr:
            print(f"\n  Correlations:")
            for key, val in corr.items():
                if val is not None:
                    print(f"    {key}: r={val}")

    if 1563 in all_results and 'configs' in all_results[1563]:
        print(f"\n  Multi-Config Metabolic Characterization (EXP-1563):")
        print(f"  {'Config':25s} {'Meals':>7s} {'ISFNorm':>8s} {'SpecPow':>10s} {'Entropy':>8s} {'Zone%':>7s}")
        print(f"  {'─'*68}")
        for cfg_name, cfg_data in all_results[1563]['configs'].items():
            p = cfg_data.get('population', {})
            per = cfg_data.get('periodicity', {})
            print(f"  {cfg_name:25s} {cfg_data['n_meals']:7,d} "
                  f"{p.get('median_isf_norm', 0):8.3f} "
                  f"{p.get('median_spectral_power', 0):10.1f} "
                  f"{per.get('normalized_entropy', 0):8.3f} "
                  f"{per.get('zone_fraction_pct', 0):7.1f}")
        deltas = all_results[1563].get('deltas_vs_baseline', {})
        if deltas:
            print(f"\n  Deltas vs baseline (A_census):")
            for cfg_name, d in deltas.items():
                print(f"    {cfg_name}: meals={d['n_meals_delta']:+d}, "
                      f"ISF-norm={d['isf_norm_delta']:+.3f}, "
                      f"spectral={d['spectral_delta_pct']:+.1f}%, "
                      f"entropy={d.get('entropy_delta', 0):+.3f}, "
                      f"zone%={d.get('zone_fraction_delta', 0):+.1f}")
        svl = all_results[1563].get('small_vs_large_meals', {})
        if svl:
            print(f"\n  Small vs Large Meals:")
            for label, data in svl.items():
                if data.get('n', 0) > 0:
                    print(f"    {label}: n={data['n']}, "
                          f"rawExc={data['median_raw_excursion']:.1f}, "
                          f"ISFnorm={data['median_isf_norm']:.3f}, "
                          f"spectral={data['median_spectral_power']:.1f}, "
                          f"ann%={data['pct_announced']:.1f}")

    if 1565 in all_results and 'population' in all_results[1565]:
        pop = all_results[1565]['population']
        wd = pop.get('weekday', {})
        we = pop.get('weekend', {})
        print(f"\n  Weekday vs Weekend Periodicity (EXP-1565):")
        print(f"  {'':15s} {'Weekday':>10s} {'Weekend':>10s} {'Delta':>10s}")
        print(f"  {'─'*48}")
        print(f"  {'Meals':15s} {wd.get('n', 0):10d} {we.get('n', 0):10d} "
              f"{'':>10s}")
        print(f"  {'Entropy':15s} {wd.get('normalized_entropy', 0):10.3f} "
              f"{we.get('normalized_entropy', 0):10.3f} "
              f"{we.get('normalized_entropy', 0) - wd.get('normalized_entropy', 0):+10.3f}")
        print(f"  {'Zone%':15s} {wd.get('zone_fraction_pct', 0):10.1f} "
              f"{we.get('zone_fraction_pct', 0):10.1f} "
              f"{we.get('zone_fraction_pct', 0) - wd.get('zone_fraction_pct', 0):+10.1f}")
        print(f"  {'Peak Hour':15s} {wd.get('peak_hour', 0):10d} "
              f"{we.get('peak_hour', 0):10d} "
              f"{we.get('peak_hour', 0) - wd.get('peak_hour', 0):+10d}")
        print(f"  {'ISF-Norm':15s} {wd.get('mean_isf_norm', 0):10.3f} "
              f"{we.get('mean_isf_norm', 0):10.3f} "
              f"{(we.get('mean_isf_norm', 0) or 0) - (wd.get('mean_isf_norm', 0) or 0):+10.3f}")
        zs = all_results[1565].get('zone_shifts', {})
        if zs:
            print(f"\n  Mealtime Zone Shifts (weekend - weekday):")
            for zone_name, zd in zs.items():
                print(f"    {zone_name.capitalize():12s}: {zd['shift_minutes']:+.0f} min "
                      f"(WD={zd['weekday_mean_hour']:.1f}h, WE={zd['weekend_mean_hour']:.1f}h)")

    if 1567 in all_results and 'per_patient' in all_results[1567]:
        pp = all_results[1567]['per_patient']
        ps = all_results[1567].get('population_summary', {})
        print(f"\n  Within-Patient Meal Clock Regularity (EXP-1567):")
        print(f"  Population: mean_std={ps.get('mean_weighted_std', '?')}h, "
              f"range={ps.get('range_weighted_std', '?')}")
        print(f"  {'Patient':>8s} {'Meals':>6s} {'Peaks':>6s} {'Std(h)':>7s} {'Entropy':>8s}")
        print(f"  {'─'*40}")
        for pat in sorted(pp.keys()):
            p = pp[pat]
            print(f"  {pat:>8s} {p['n_meals']:6d} {p['n_personal_peaks']:6d} "
                  f"{p['weighted_mean_std']:7.2f} {p['normalized_entropy']:8.3f}")
        zv = all_results[1567].get('zone_variation', {})
        if zv:
            print(f"\n  Zone Variation (inter-patient):")
            for zone_name, zd in zv.items():
                print(f"    {zone_name.capitalize():12s}: inter-pat std={zd['inter_patient_std_of_mean_hour']:.2f}h, "
                      f"mean within-pat std={zd['mean_within_patient_std']:.2f}h, "
                      f"range={zd['range_of_mean_hours']}")
        pct_lr = all_results[1567].get('pct_weekend_less_regular')
        if pct_lr is not None:
            print(f"\n  Weekend less regular: {pct_lr:.1f}% of patient×zone pairs")

    if 1569 in all_results and 'hypothesis_tests' in all_results[1569]:
        ht = all_results[1569]['hypothesis_tests']
        gs = all_results[1569].get('grid_summary', [])
        print(f"\n  Detection Sensitivity Benchmark (EXP-1569):")
        print(f"  {all_results[1569].get('n_configs', 0)} configs swept")
        h1 = ht.get('H1_regularity_vs_strictness', {})
        print(f"  H1 regularity~strictness: rho={h1.get('spearman_rho')}, p={h1.get('p_value')}")
        knee = ht.get('H2_knee_config')
        if knee:
            print(f"  H2 knee: {knee['min_carb_g']}g/{knee['hysteresis_min']}min "
                  f"(mpd={knee['meals_per_day']}, std={knee['mean_patient_std']}h)")
        h3 = ht.get('H3_patient_robustness', {})
        if h3:
            robust = sorted(h3.items(), key=lambda x: x[1]['std_of_std'])
            print(f"  H3 most robust: {robust[0][0]} (σσ={robust[0][1]['std_of_std']}), "
                  f"least: {robust[-1][0]} (σσ={robust[-1][1]['std_of_std']})")
        h45 = ht.get('H4_H5_carb_conservation', {})
        if h45:
            cv_0 = h45.get('0', {}).get('cv_pct', '?')
            cv_18 = h45.get('18', {}).get('cv_pct', '?')
            print(f"  H5 carb conservation CV: min_carb=0g → {cv_0}%, "
                  f"min_carb=18g → {cv_18}%")

    if 1571 in all_results and 'per_patient' in all_results[1571]:
        print(f"\n  Robustness Archetypes (EXP-1571):")
        d = all_results[1571]
        traits = d['per_patient']
        tier_list = {'robust': [], 'moderate': [], 'sensitive': []}
        for p, t in sorted(traits.items()):
            tier_list[t['tier']].append(p)
        for tier in ['robust', 'moderate', 'sensitive']:
            members = tier_list[tier]
            print(f"    {tier.capitalize():10s} (n={len(members)}): {', '.join(members)}")
        corrs = d.get('correlations_with_sigma_sigma', {})
        print(f"  Top correlates of σσ:")
        sorted_c = sorted(corrs.items(), key=lambda x: abs(x[1].get('spearman_rho', 0)), reverse=True)
        for name, c in sorted_c[:3]:
            print(f"    {name}: ρ={c.get('spearman_rho', '?'):.3f}, p={c.get('p_value', '?'):.4f}")

    # Save combined results
    combined_path = RESULTS_DIR / 'exp-1551_natural_experiments_combined.json'
    save_combined = {}
    skip_large = {'all_experiments', 'meal_records', '_config_records', '_records', '_grid', '_stability_curves'}
    for k, v in all_results.items():
        save_combined[k] = {kk: vv for kk, vv in v.items() if kk not in skip_large}
    with open(str(combined_path), 'w') as f:
        json.dump(save_combined, f, indent=2, default=str)
    print(f"\nCombined results → {combined_path}")


if __name__ == '__main__':
    main()
