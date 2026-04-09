"""
natural_experiment_detector.py — Detect natural experiments in CGM/AID data.

Research basis: EXP-1551 (census, 50,810 windows across 11 patients),
EXP-1559 (meal sensitivity: 3 configs, quality 0.923–0.979).

Natural experiments are windows where real-world patient data naturally
mimics controlled clinical tests:
  - Fasting basal tests (no food/bolus for ≥3h)
  - Glucose tolerance tests (meals with post-prandial observation)
  - Correction response tests (isolated correction boluses)
  - UAM episodes (unexplained glucose rises from physics residual)
  - Dawn phenomenon windows (fasting 4–8 AM glucose acceleration)
  - Exercise windows (sustained BG drops without bolus)
  - AID response windows (temp basal deviations from schedule)
  - Stable reference periods (flat glucose, low variability)

Population findings (EXP-1551, 11 patients × 180 days):
  Total: 50,810 natural experiments
  UAM: 39%, AID Response: 19%, Correction: 15%, Stable: 9%,
  Meal: 8%, Dawn: 3%, Overnight: 3%, Exercise: 2%, Fasting: 1%
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Dict, List, Optional

import numpy as np

from .types import MetabolicState, PatientData


# ── Constants (calibrated from EXP-1551, EXP-1320, EXP-1559) ─────────

STEP_MINUTES = 5
STEPS_PER_HOUR = 12
STEPS_PER_DAY = 288

# Fasting windows
FASTING_MIN_STEPS = 36       # 3 hours
FASTING_CARB_THRESH = 1.0    # g — effectively zero
FASTING_BOLUS_THRESH = 0.1   # U — allow micro-SMB

# Overnight windows
OVERNIGHT_START_HOUR = 0
OVERNIGHT_END_HOUR = 6

# Dawn phenomenon
DAWN_EFFECT_THRESH = 3.0     # mg/dL/h acceleration to detect dawn

# Correction windows
CORRECTION_MIN_BOLUS = 0.5   # U
CORRECTION_CARB_WINDOW = 6   # ±30 min carb-free
CORRECTION_BG_THRESH = 150   # mg/dL starting BG
CORRECTION_OBSERVE_STEPS = 96  # 8h observation

# Meal windows (configurable via MealConfig)
DEFAULT_MEAL_MIN_CARBS = 5.0    # g
DEFAULT_MEAL_CLUSTER_GAP = 6    # steps (30 min)
MEAL_OBSERVE_STEPS = 36         # 3h post-meal

# UAM (EXP-1320 universal threshold)
UAM_RESIDUAL_THRESH = 1.0    # mg/dL per 5-min
UAM_MIN_DURATION = 3          # steps (15 min)

# Exercise
EXERCISE_DEMAND_THRESH = 2.0  # residual threshold
EXERCISE_MIN_STEPS = 6        # 30 min

# AID response
AID_HIGH_TEMP_THRESH = 0.3   # U/hr above scheduled
AID_LOW_TEMP_THRESH = -0.2   # U/hr below scheduled

# Stable windows
STABLE_MAX_CV = 5.0           # % glucose CV
STABLE_MIN_STEPS = 24         # 2h


# ── Enums ─────────────────────────────────────────────────────────────

class NaturalExperimentType(str, Enum):
    """Types of natural experiments detectable in CGM/AID data."""
    FASTING = "fasting"
    OVERNIGHT = "overnight"
    MEAL = "meal"
    CORRECTION = "correction"
    UAM = "uam"
    DAWN = "dawn"
    EXERCISE = "exercise"
    AID_RESPONSE = "aid_response"
    STABLE = "stable"


# ── Data Classes ──────────────────────────────────────────────────────

@dataclass
class MealConfig:
    """Configuration for meal detection sensitivity.

    Three standard configurations from EXP-1559:
      Census:  min_carbs=5,  cluster_gap=6  (4,072 meals, quality 0.923)
      Medium:  min_carbs=5,  cluster_gap=18 (3,272 meals, quality 0.973)
      Therapy: min_carbs=18, cluster_gap=18 (2,632 meals, quality 0.979)
    """
    min_carbs: float = DEFAULT_MEAL_MIN_CARBS
    cluster_gap: int = DEFAULT_MEAL_CLUSTER_GAP

    @classmethod
    def census(cls) -> MealConfig:
        return cls(min_carbs=5.0, cluster_gap=6)

    @classmethod
    def medium(cls) -> MealConfig:
        return cls(min_carbs=5.0, cluster_gap=18)

    @classmethod
    def therapy(cls) -> MealConfig:
        return cls(min_carbs=18.0, cluster_gap=18)


@dataclass
class NaturalExperiment:
    """A single detected natural experiment window."""
    exp_type: NaturalExperimentType
    start_idx: int
    end_idx: int
    duration_minutes: int
    hour_of_day: float
    quality: float                  # 0–1 cleanliness score
    measurements: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d['exp_type'] = self.exp_type.value
        return d


@dataclass
class NaturalExperimentCensus:
    """Complete census of natural experiments from a patient dataset.

    Research basis: EXP-1551 population census across 11 patients × 180 days.
    """
    experiments: List[NaturalExperiment]
    total_detected: int
    by_type: Dict[str, int]
    quality_mean: float
    days_analyzed: float
    per_day_rate: float             # experiments/day
    meal_config: Optional[MealConfig] = None

    def filter_by_type(self, exp_type: NaturalExperimentType,
                       min_quality: float = 0.0) -> List[NaturalExperiment]:
        return [e for e in self.experiments
                if e.exp_type == exp_type and e.quality >= min_quality]

    def filter_high_quality(self, min_quality: float = 0.7) -> List[NaturalExperiment]:
        return [e for e in self.experiments if e.quality >= min_quality]

    def summary_dict(self) -> dict:
        return {
            'total_detected': self.total_detected,
            'days_analyzed': round(self.days_analyzed, 1),
            'per_day_rate': round(self.per_day_rate, 1),
            'quality_mean': round(self.quality_mean, 3),
            'by_type': self.by_type,
        }


# ── Shared Helpers ────────────────────────────────────────────────────

def _extract_runs(mask: np.ndarray, min_length: int = 1) -> List[tuple]:
    """Extract contiguous True runs from a boolean mask."""
    runs = []
    in_run = False
    start = 0
    N = len(mask)
    for i in range(N):
        if mask[i] and not in_run:
            start = i
            in_run = True
        elif not mask[i] and in_run:
            if i - start >= min_length:
                runs.append((start, i))
            in_run = False
    if in_run and N - start >= min_length:
        runs.append((start, N))
    return runs


def _cluster_events(indices: np.ndarray, gap: int = 6) -> List[List[int]]:
    """Cluster event indices within `gap` steps of each other."""
    if len(indices) == 0:
        return []
    clusters = [[int(indices[0])]]
    for idx in indices[1:]:
        if int(idx) - clusters[-1][-1] <= gap:
            clusters[-1].append(int(idx))
        else:
            clusters.append([int(idx)])
    return clusters


def _safe_nanmean(arr: np.ndarray) -> float:
    valid = arr[~np.isnan(arr)]
    return float(np.mean(valid)) if len(valid) > 0 else float('nan')


def _safe_nanstd(arr: np.ndarray) -> float:
    valid = arr[~np.isnan(arr)]
    return float(np.std(valid)) if len(valid) > 1 else float('nan')


def _cgm_coverage(bg_segment: np.ndarray) -> float:
    return float(np.sum(~np.isnan(bg_segment))) / max(len(bg_segment), 1)


def _linear_drift(bg_segment: np.ndarray) -> float:
    """Drift in mg/dL per hour via linear regression."""
    valid = ~np.isnan(bg_segment)
    if np.sum(valid) < 6:
        return float('nan')
    y = bg_segment[valid]
    x = np.arange(len(bg_segment))[valid] * (STEP_MINUTES / 60.0)
    if len(x) < 2:
        return float('nan')
    slope = np.polyfit(x, y, 1)[0]
    return float(slope)


def _exp_decay_fit(bg_segment: np.ndarray, bolus_size: float):
    """Fit BG(t) = BG_start - amplitude × (1 - exp(-t/τ)).
    Returns (amplitude, tau, r2, isf_estimate) or None."""
    valid = ~np.isnan(bg_segment)
    if np.sum(valid) < 6:
        return None
    y = bg_segment[valid]
    t = np.arange(len(bg_segment))[valid] * (STEP_MINUTES / 60.0)
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


def _hour_from_timestamps(timestamps: np.ndarray, idx: int) -> float:
    """Fractional hour of day from Unix-ms timestamp."""
    ts_sec = timestamps[idx] / 1000.0
    hour = (ts_sec % 86400) / 3600.0
    return round(hour, 2)


# ── Individual Detectors ──────────────────────────────────────────────

def _detect_fasting(glucose: np.ndarray, bolus: np.ndarray,
                    carbs: np.ndarray, timestamps: np.ndarray) -> List[NaturalExperiment]:
    """Detect fasting basal test windows (≥3h no food/bolus)."""
    N = len(glucose)
    experiments = []

    carb_activity = np.zeros(N)
    bolus_activity = np.zeros(N)
    for i in range(N):
        lo = max(0, i - FASTING_MIN_STEPS)
        carb_activity[i] = np.nansum(carbs[lo:i + 1])
        bolus_activity[i] = np.nansum(bolus[lo:i + 1])

    is_fasting = ((carb_activity < FASTING_CARB_THRESH) &
                  (bolus_activity < FASTING_BOLUS_THRESH))
    runs = _extract_runs(is_fasting, min_length=FASTING_MIN_STEPS)

    for start, end in runs:
        seg = glucose[start:end]
        coverage = _cgm_coverage(seg)
        if coverage < 0.7:
            continue
        drift = _linear_drift(seg)
        duration = (end - start) * STEP_MINUTES
        q_duration = min(duration / 360.0, 1.0)
        q_stability = max(0, 1.0 - abs(drift) / 20.0) if not math.isnan(drift) else 0
        quality = 0.4 * q_duration + 0.3 * coverage + 0.3 * q_stability

        experiments.append(NaturalExperiment(
            exp_type=NaturalExperimentType.FASTING,
            start_idx=start, end_idx=end,
            duration_minutes=duration,
            hour_of_day=_hour_from_timestamps(timestamps, start),
            quality=round(quality, 3),
            measurements={
                'drift_mg_dl_per_hour': round(drift, 3) if not math.isnan(drift) else None,
                'mean_bg': round(_safe_nanmean(seg), 1),
                'bg_cv': round(100 * _safe_nanstd(seg) / max(_safe_nanmean(seg), 1), 2),
                'cgm_coverage': round(coverage, 3),
            }
        ))
    return experiments


def _detect_overnight(glucose: np.ndarray, bolus: np.ndarray,
                      carbs: np.ndarray, hours: np.ndarray,
                      timestamps: np.ndarray) -> List[NaturalExperiment]:
    """Detect overnight basal test windows (midnight to 6 AM)."""
    N = len(glucose)
    experiments = []
    is_overnight = (hours >= OVERNIGHT_START_HOUR) & (hours < OVERNIGHT_END_HOUR)
    runs = _extract_runs(is_overnight, min_length=STEPS_PER_HOUR)

    for start, end in runs:
        seg = glucose[start:end]
        coverage = _cgm_coverage(seg)
        if coverage < 0.7:
            continue
        carb_sum = np.nansum(carbs[start:end])
        bolus_sum = np.nansum(bolus[start:end])
        is_fasting = carb_sum < FASTING_CARB_THRESH and bolus_sum < FASTING_BOLUS_THRESH
        drift = _linear_drift(seg)
        duration = (end - start) * STEP_MINUTES
        quality = (0.4 * (1.0 if is_fasting else 0.3) +
                   0.3 * coverage +
                   0.3 * min(duration / 300, 1.0))
        experiments.append(NaturalExperiment(
            exp_type=NaturalExperimentType.OVERNIGHT,
            start_idx=start, end_idx=end,
            duration_minutes=duration,
            hour_of_day=_hour_from_timestamps(timestamps, start),
            quality=round(quality, 3),
            measurements={
                'drift_mg_dl_per_hour': round(drift, 3) if not math.isnan(drift) else None,
                'is_fasting': is_fasting,
                'mean_bg': round(_safe_nanmean(seg), 1),
                'cgm_coverage': round(coverage, 3),
            }
        ))
    return experiments


def _detect_meals(glucose: np.ndarray, bolus: np.ndarray,
                  carbs: np.ndarray, timestamps: np.ndarray,
                  meal_config: MealConfig) -> List[NaturalExperiment]:
    """Detect glucose tolerance test windows (meals with observation)."""
    N = len(glucose)
    experiments = []

    carb_events = np.where(carbs >= meal_config.min_carbs)[0]
    if len(carb_events) == 0:
        return experiments

    clusters = _cluster_events(carb_events, gap=meal_config.cluster_gap)

    for cluster in clusters:
        meal_idx = cluster[0]
        total_carbs = float(np.nansum(carbs[cluster]))
        end_idx = min(meal_idx + MEAL_OBSERVE_STEPS, N)
        if end_idx - meal_idx < 12:
            continue

        pre_start = max(0, meal_idx - 6)
        pre_bg = _safe_nanmean(glucose[pre_start:meal_idx])
        post_bg = glucose[meal_idx:end_idx]
        coverage = _cgm_coverage(post_bg)
        if coverage < 0.6:
            continue

        valid_post = post_bg.copy()
        valid_post[np.isnan(valid_post)] = pre_bg
        peak_idx_rel = int(np.argmax(valid_post))
        peak_bg = float(valid_post[peak_idx_rel])
        excursion = peak_bg - pre_bg if not math.isnan(pre_bg) else float('nan')
        peak_time_min = peak_idx_rel * STEP_MINUTES

        bolus_window = bolus[max(0, meal_idx - 3):min(N, meal_idx + 3)]
        meal_bolus = float(np.nansum(bolus_window))
        is_announced = meal_bolus > 0.1

        q_isolated = 1.0
        for c2 in clusters:
            if c2[0] != meal_idx and abs(c2[0] - meal_idx) < 24:
                q_isolated = 0.5
                break
        quality = 0.4 * coverage + 0.3 * q_isolated + 0.3 * (1.0 if is_announced else 0.6)

        experiments.append(NaturalExperiment(
            exp_type=NaturalExperimentType.MEAL,
            start_idx=meal_idx, end_idx=end_idx,
            duration_minutes=(end_idx - meal_idx) * STEP_MINUTES,
            hour_of_day=_hour_from_timestamps(timestamps, meal_idx),
            quality=round(quality, 3),
            measurements={
                'carbs_g': round(total_carbs, 1),
                'bolus_u': round(meal_bolus, 2),
                'is_announced': is_announced,
                'pre_meal_bg': round(pre_bg, 1) if not math.isnan(pre_bg) else None,
                'peak_bg': round(peak_bg, 1),
                'excursion_mg_dl': round(excursion, 1) if not math.isnan(excursion) else None,
                'peak_time_min': peak_time_min,
                'cgm_coverage': round(coverage, 3),
            }
        ))
    return experiments


def _detect_corrections(glucose: np.ndarray, bolus: np.ndarray,
                        carbs: np.ndarray,
                        timestamps: np.ndarray) -> List[NaturalExperiment]:
    """Detect correction bolus response windows."""
    N = len(glucose)
    experiments = []
    bolus_events = np.where(bolus >= CORRECTION_MIN_BOLUS)[0]

    for bi in bolus_events:
        lo = max(0, bi - CORRECTION_CARB_WINDOW)
        hi = min(N, bi + CORRECTION_CARB_WINDOW)
        if np.nansum(carbs[lo:hi]) > FASTING_CARB_THRESH:
            continue

        start_bg = glucose[bi] if not np.isnan(glucose[bi]) else _safe_nanmean(glucose[max(0, bi - 3):bi + 1])
        if math.isnan(start_bg) or start_bg < CORRECTION_BG_THRESH:
            continue

        obs_end = min(bi + CORRECTION_OBSERVE_STEPS, N)
        seg = glucose[bi:obs_end]
        coverage = _cgm_coverage(seg)
        if coverage < 0.6:
            continue

        bolus_size = float(bolus[bi])
        fit_result = _exp_decay_fit(seg, bolus_size)
        amplitude, tau, r2, isf_est = fit_result if fit_result else (None, None, None, None)

        valid_seg = seg[~np.isnan(seg)]
        nadir = float(np.min(valid_seg)) if len(valid_seg) > 6 else None
        simple_isf = (start_bg - nadir) / bolus_size if nadir is not None else None

        other_bolus = np.nansum(bolus[min(N, bi + 1):min(N, bi + 36)])
        q_isolated = 1.0 if other_bolus < 0.1 else 0.4
        q_fit = min(max(r2, 0), 1.0) if r2 is not None else 0.3
        quality = 0.3 * q_isolated + 0.3 * coverage + 0.4 * q_fit

        experiments.append(NaturalExperiment(
            exp_type=NaturalExperimentType.CORRECTION,
            start_idx=bi, end_idx=obs_end,
            duration_minutes=(obs_end - bi) * STEP_MINUTES,
            hour_of_day=_hour_from_timestamps(timestamps, bi),
            quality=round(quality, 3),
            measurements={
                'bolus_u': round(bolus_size, 2),
                'start_bg': round(start_bg, 1),
                'nadir_bg': round(nadir, 1) if nadir else None,
                'simple_isf': round(simple_isf, 1) if simple_isf else None,
                'curve_r2': round(r2, 3) if r2 else None,
                'curve_isf': round(isf_est, 1) if isf_est else None,
                'cgm_coverage': round(coverage, 3),
            }
        ))
    return experiments


def _detect_uam(glucose: np.ndarray, carbs: np.ndarray,
                net_flux: np.ndarray,
                timestamps: np.ndarray) -> List[NaturalExperiment]:
    """Detect unannounced meal (UAM) windows from physics residuals."""
    N = min(len(glucose), len(net_flux))
    experiments = []

    actual_dbg = np.zeros(N)
    actual_dbg[1:] = np.diff(glucose[:N])
    actual_dbg[np.isnan(actual_dbg)] = 0
    residual = actual_dbg - net_flux[:N]

    carb_free = np.ones(N, dtype=bool)
    carb_indices = np.where(carbs[:N] > FASTING_CARB_THRESH)[0]
    for ci in carb_indices:
        lo = max(0, ci - STEPS_PER_HOUR)
        hi = min(N, ci + STEPS_PER_HOUR)
        carb_free[lo:hi] = False

    is_uam = (residual > UAM_RESIDUAL_THRESH) & carb_free
    runs = _extract_runs(is_uam, min_length=UAM_MIN_DURATION)

    for start, end in runs:
        seg_bg = glucose[start:end]
        seg_res = residual[start:end]
        coverage = _cgm_coverage(seg_bg)
        if coverage < 0.5:
            continue
        duration = (end - start) * STEP_MINUTES
        peak_res = float(np.max(seg_res))
        mean_res = float(np.mean(seg_res))
        bg_rise = float(np.nanmax(seg_bg) - np.nanmin(seg_bg)) if np.any(~np.isnan(seg_bg)) else 0

        hour = _hour_from_timestamps(timestamps, start)
        if 4 <= hour < 8 and mean_res < 3.0:
            subtype = 'hepatic'
        elif peak_res > 5.0 and duration < 30:
            subtype = 'artifact'
        elif mean_res < 1.5 and duration > 60:
            subtype = 'slow_absorption'
        else:
            subtype = 'meal'

        q_duration = min(duration / 120.0, 1.0)
        q_signal = min(mean_res / 3.0, 1.0)
        quality = 0.3 * q_duration + 0.4 * q_signal + 0.3 * coverage

        experiments.append(NaturalExperiment(
            exp_type=NaturalExperimentType.UAM,
            start_idx=start, end_idx=end,
            duration_minutes=duration,
            hour_of_day=hour,
            quality=round(quality, 3),
            measurements={
                'subtype': subtype,
                'peak_residual': round(peak_res, 2),
                'mean_residual': round(mean_res, 2),
                'bg_rise_mg_dl': round(bg_rise, 1),
                'cgm_coverage': round(coverage, 3),
            }
        ))
    return experiments


def _detect_dawn(glucose: np.ndarray, carbs: np.ndarray,
                 bolus: np.ndarray, hours: np.ndarray,
                 timestamps: np.ndarray) -> List[NaturalExperiment]:
    """Detect dawn phenomenon windows (4–8 AM glucose acceleration)."""
    N = len(glucose)
    experiments = []

    # Per-day detection comparing pre-dawn (0–4) vs dawn (4–8)
    day_boundaries = np.where(np.diff(hours) < -20)[0] + 1
    day_starts = np.concatenate([[0], day_boundaries])
    day_ends = np.concatenate([day_boundaries, [N]])

    for ds, de in zip(day_starts, day_ends):
        seg_hours = hours[ds:de]
        seg_bg = glucose[ds:de]

        pre_mask = (seg_hours >= 0) & (seg_hours < 4)
        dawn_mask = (seg_hours >= 4) & (seg_hours < 8)

        pre_idx = np.where(pre_mask)[0]
        dawn_idx = np.where(dawn_mask)[0]
        if len(pre_idx) < 12 or len(dawn_idx) < 12:
            continue

        carb_sum = np.nansum(carbs[ds + pre_idx[0]:ds + dawn_idx[-1] + 1])
        bolus_sum = np.nansum(bolus[ds + pre_idx[0]:ds + dawn_idx[-1] + 1])
        is_fasting = carb_sum < FASTING_CARB_THRESH and bolus_sum < FASTING_BOLUS_THRESH

        pre_drift = _linear_drift(seg_bg[pre_idx])
        dawn_drift = _linear_drift(seg_bg[dawn_idx])
        if math.isnan(pre_drift) or math.isnan(dawn_drift):
            continue

        dawn_effect = dawn_drift - pre_drift
        start = ds + pre_idx[0]
        end = ds + dawn_idx[-1]

        quality = 0.5 * (1.0 if is_fasting else 0.3) + 0.5 * _cgm_coverage(glucose[start:end + 1])

        experiments.append(NaturalExperiment(
            exp_type=NaturalExperimentType.DAWN,
            start_idx=start, end_idx=end,
            duration_minutes=(end - start) * STEP_MINUTES,
            hour_of_day=_hour_from_timestamps(timestamps, start),
            quality=round(quality, 3),
            measurements={
                'is_fasting': is_fasting,
                'dawn_effect_mg_dl_hr': round(dawn_effect, 2),
                'dawn_detected': dawn_effect > DAWN_EFFECT_THRESH,
                'pre_dawn_mean_bg': round(_safe_nanmean(seg_bg[pre_idx]), 1),
                'dawn_mean_bg': round(_safe_nanmean(seg_bg[dawn_idx]), 1),
                'cgm_coverage': round(_cgm_coverage(glucose[start:end + 1]), 3),
            }
        ))
    return experiments


def _detect_exercise(glucose: np.ndarray, bolus: np.ndarray,
                     net_flux: np.ndarray,
                     timestamps: np.ndarray) -> List[NaturalExperiment]:
    """Detect exercise windows from sustained BG drops without bolus."""
    N = min(len(glucose), len(net_flux))
    experiments = []

    actual_dbg = np.zeros(N)
    actual_dbg[1:] = np.diff(glucose[:N])
    actual_dbg[np.isnan(actual_dbg)] = 0
    residual = actual_dbg - net_flux[:N]

    bolus_free = np.ones(N, dtype=bool)
    bolus_indices = np.where(bolus[:N] > CORRECTION_MIN_BOLUS)[0]
    for bi in bolus_indices:
        lo = max(0, bi - STEPS_PER_HOUR * 2)
        hi = min(N, bi + STEPS_PER_HOUR)
        bolus_free[lo:hi] = False

    is_exercise = (residual < -EXERCISE_DEMAND_THRESH) & bolus_free
    runs = _extract_runs(is_exercise, min_length=EXERCISE_MIN_STEPS)

    for start, end in runs:
        seg_bg = glucose[start:end]
        seg_res = residual[start:end]
        coverage = _cgm_coverage(seg_bg)
        if coverage < 0.5:
            continue
        duration = (end - start) * STEP_MINUTES
        mean_res = float(np.mean(seg_res))
        bg_drop = float(np.nanmax(seg_bg) - np.nanmin(seg_bg)) if np.any(~np.isnan(seg_bg)) else 0

        quality = (0.3 * min(duration / 90.0, 1.0) +
                   0.4 * min(abs(mean_res) / 4.0, 1.0) +
                   0.3 * coverage)

        experiments.append(NaturalExperiment(
            exp_type=NaturalExperimentType.EXERCISE,
            start_idx=start, end_idx=end,
            duration_minutes=duration,
            hour_of_day=_hour_from_timestamps(timestamps, start),
            quality=round(quality, 3),
            measurements={
                'mean_residual': round(mean_res, 2),
                'bg_drop_mg_dl': round(bg_drop, 1),
                'cgm_coverage': round(coverage, 3),
            }
        ))
    return experiments


def _detect_aid_response(glucose: np.ndarray, basal_rate: np.ndarray,
                         timestamps: np.ndarray,
                         profile_basal: float) -> List[NaturalExperiment]:
    """Detect AID algorithm response windows from temp basal deviations."""
    N = len(glucose)
    experiments = []
    if basal_rate is None:
        return experiments

    net_basal = basal_rate[:N] - profile_basal

    # High temp (loop increasing delivery)
    for subtype, mask in [('high_temp', net_basal > AID_HIGH_TEMP_THRESH),
                          ('low_temp', net_basal < AID_LOW_TEMP_THRESH)]:
        runs = _extract_runs(mask, min_length=6)
        for start, end in runs:
            seg_bg = glucose[start:end]
            coverage = _cgm_coverage(seg_bg)
            if coverage < 0.5:
                continue
            seg_nb = net_basal[start:end]
            duration = (end - start) * STEP_MINUTES
            quality = 0.5 * coverage + 0.5 * min(duration / 120, 1.0)
            experiments.append(NaturalExperiment(
                exp_type=NaturalExperimentType.AID_RESPONSE,
                start_idx=start, end_idx=end,
                duration_minutes=duration,
                hour_of_day=_hour_from_timestamps(timestamps, start),
                quality=round(quality, 3),
                measurements={
                    'subtype': subtype,
                    'mean_net_basal': round(float(np.mean(seg_nb)), 3),
                    'mean_bg': round(_safe_nanmean(seg_bg), 1),
                    'bg_change': round(float(np.nanmean(seg_bg[-6:]) - np.nanmean(seg_bg[:6])), 1)
                                 if len(seg_bg) >= 12 else None,
                    'cgm_coverage': round(coverage, 3),
                }
            ))
    return experiments


def _detect_stable(glucose: np.ndarray, bolus: np.ndarray,
                   carbs: np.ndarray,
                   timestamps: np.ndarray) -> List[NaturalExperiment]:
    """Detect stable/flat glucose reference windows."""
    N = len(glucose)
    experiments = []

    for start in range(0, N - STABLE_MIN_STEPS, STEPS_PER_HOUR):
        end = start + STABLE_MIN_STEPS
        seg = glucose[start:end]
        coverage = _cgm_coverage(seg)
        if coverage < 0.8:
            continue
        valid = seg[~np.isnan(seg)]
        if len(valid) < 12:
            continue
        mean_bg = float(np.mean(valid))
        std_bg = float(np.std(valid))
        cv = 100 * std_bg / max(mean_bg, 1)
        if cv > STABLE_MAX_CV:
            continue

        carb_sum = float(np.nansum(carbs[start:end]))
        bolus_sum = float(np.nansum(bolus[start:end]))
        quality_cv = max(0, 1.0 - cv / STABLE_MAX_CV)
        quality_quiet = 1.0 if (carb_sum < 1 and bolus_sum < 0.1) else 0.5
        quality = 0.4 * quality_cv + 0.3 * coverage + 0.3 * quality_quiet

        experiments.append(NaturalExperiment(
            exp_type=NaturalExperimentType.STABLE,
            start_idx=start, end_idx=end,
            duration_minutes=STABLE_MIN_STEPS * STEP_MINUTES,
            hour_of_day=_hour_from_timestamps(timestamps, start),
            quality=round(quality, 3),
            measurements={
                'mean_bg': round(mean_bg, 1),
                'cv_pct': round(cv, 2),
                'cgm_coverage': round(coverage, 3),
            }
        ))
    return experiments


# ── Main Public API ───────────────────────────────────────────────────

def detect_natural_experiments(
    patient: PatientData,
    metabolic: Optional[MetabolicState] = None,
    meal_config: Optional[MealConfig] = None,
) -> NaturalExperimentCensus:
    """Run all natural experiment detectors on a single patient.

    This is the primary public API. Handles missing data gracefully:
    detectors that require metabolic state (UAM, exercise) are skipped
    if metabolic is None.

    Args:
        patient: PatientData with at minimum glucose + timestamps.
        metabolic: Optional MetabolicState for physics-based detectors.
        meal_config: Optional MealConfig for meal detection sensitivity.

    Returns:
        NaturalExperimentCensus with all detected experiments.
    """
    glucose = patient.glucose
    timestamps = patient.timestamps
    N = len(glucose)

    bolus = patient.bolus if patient.bolus is not None else np.zeros(N)
    carbs = patient.carbs if patient.carbs is not None else np.zeros(N)
    basal_rate = patient.basal_rate if patient.basal_rate is not None else None

    # Ensure NaN-safe
    bolus = np.nan_to_num(bolus.astype(np.float64), nan=0.0)
    carbs = np.nan_to_num(carbs.astype(np.float64), nan=0.0)

    hours = ((timestamps / 1000.0) % 86400) / 3600.0
    mc = meal_config or MealConfig()

    experiments: List[NaturalExperiment] = []

    # BG-only detectors (always available)
    experiments.extend(_detect_fasting(glucose, bolus, carbs, timestamps))
    experiments.extend(_detect_overnight(glucose, bolus, carbs, hours, timestamps))
    experiments.extend(_detect_meals(glucose, bolus, carbs, timestamps, mc))
    experiments.extend(_detect_corrections(glucose, bolus, carbs, timestamps))
    experiments.extend(_detect_stable(glucose, bolus, carbs, timestamps))

    # Dawn detection (needs only hours)
    experiments.extend(_detect_dawn(glucose, carbs, bolus, hours, timestamps))

    # Physics-based detectors (need metabolic state)
    if metabolic is not None:
        net_flux = metabolic.net_flux if hasattr(metabolic, 'net_flux') else None
        if net_flux is not None and len(net_flux) > 0:
            experiments.extend(_detect_uam(glucose, carbs, net_flux, timestamps))
            experiments.extend(_detect_exercise(glucose, bolus, net_flux, timestamps))

    # AID response (needs basal_rate)
    if basal_rate is not None:
        profile_basal = patient.profile.basal_schedule[0].get('value', 0.8) if patient.profile else 0.8
        experiments.extend(_detect_aid_response(glucose, basal_rate, timestamps, profile_basal))

    # Build census
    by_type = {}
    for e in experiments:
        key = e.exp_type.value
        by_type[key] = by_type.get(key, 0) + 1

    qualities = [e.quality for e in experiments]
    days = patient.days_of_data

    return NaturalExperimentCensus(
        experiments=experiments,
        total_detected=len(experiments),
        by_type=by_type,
        quality_mean=round(float(np.mean(qualities)), 3) if qualities else 0.0,
        days_analyzed=round(days, 1),
        per_day_rate=round(len(experiments) / max(days, 0.01), 1),
        meal_config=mc,
    )
