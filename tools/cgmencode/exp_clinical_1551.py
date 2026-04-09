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

_CACHED_EXPERIMENTS = None


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

def main():
    parser = argparse.ArgumentParser(description='EXP-1551-1559: Natural Experiment Census')
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

    # Save combined results
    combined_path = RESULTS_DIR / 'exp-1551_natural_experiments_combined.json'
    save_combined = {}
    skip_large = {'all_experiments', 'meal_records'}
    for k, v in all_results.items():
        save_combined[k] = {kk: vv for kk, vv in v.items() if kk not in skip_large}
    with open(str(combined_path), 'w') as f:
        json.dump(save_combined, f, indent=2, default=str)
    print(f"\nCombined results → {combined_path}")


if __name__ == '__main__':
    main()
