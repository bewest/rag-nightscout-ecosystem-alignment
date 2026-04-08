#!/usr/bin/env python3
"""Production Therapy Detection & Recommendation Pipeline (v10).

Consolidated from 230 experiments (EXP-1281–1510) into a single production
module. Provides:

  1. TherapyAssessment — per-patient therapy detection and scoring
  2. TherapyRecommendation — actionable setting change recommendations
  3. PatientReport — individual therapy report for users/patients
  4. CohortReport — clinician-facing cohort summary

Usage:
    from cgmencode.production_therapy import TherapyPipeline

    pipeline = TherapyPipeline()
    pipeline.load_patients('/path/to/patients')
    report = pipeline.patient_report('patient_a')
    print(report.text_summary())
    report.save_pdf('patient_a_therapy_report.pdf')

    cohort = pipeline.cohort_report()
    print(cohort.text_summary())
"""

from __future__ import annotations

import json
import math
import os
import textwrap
import warnings
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy import stats

# ---------------------------------------------------------------------------
# Try importing the data loader; graceful fallback for standalone use
# ---------------------------------------------------------------------------
try:
    from cgmencode.exp_metabolic_flux import load_patients as _load_patients
except ImportError:
    _load_patients = None

# ═══════════════════════════════════════════════════════════════════════════
# Constants (validated across 230 experiments)
# ═══════════════════════════════════════════════════════════════════════════

STEPS_PER_HOUR = 12
STEPS_PER_DAY = 24 * STEPS_PER_HOUR  # 288

# ADA time-in-range thresholds (mg/dL)
TIR_LO = 70
TIR_HI = 180
TBR_L1_LO = 54   # severe hypo boundary
TBR_L1_HI = 69
TAR_L1_LO = 181
TAR_L1_HI = 250
TAR_L2_LO = 251

# ADA targets (%)
ADA_TIR_TARGET = 70.0
ADA_TBR_L1_TARGET = 4.0
ADA_TBR_L2_TARGET = 1.0
ADA_TAR_L1_TARGET = 25.0
ADA_TAR_L2_TARGET = 5.0
ADA_CV_TARGET = 36.0

# v10 scoring
GRADE_BOUNDARIES = {'D': 0, 'C': 50, 'B': 65, 'A': 80}
V10_WEIGHTS = {'tir': 0.5, 'cv': 0.2, 'overnight': 0.1, 'safety': 0.2}

# Therapy detection thresholds (validated EXP-1381–1400)
DRIFT_THRESHOLD = 5.0        # mg/dL/h — overnight basal flag
EXCURSION_THRESHOLD = 70.0   # mg/dL — 90th %ile post-meal rise
CV_THRESHOLD = 36.0          # % coefficient of variation
MIN_BOLUS_ISF = 2.0          # U — minimum correction bolus for ISF calc
MIN_ISF_EVENTS = 5           # minimum correction events for ISF estimate

# Recommendation magnitudes (validated EXP-1431–1440)
BASAL_ADJUST_PCT = 10
CR_ADJUST_STANDARD = 30
CR_ADJUST_GRADE_D = 50
ISF_ADJUST_PCT = 10

# Hypo detection
HYPO_THRESHOLD = 70
SEVERE_HYPO_THRESHOLD = 54
HYPO_MIN_CONSECUTIVE = 3     # 15 min at 5-min resolution

# Minimum data requirements (validated EXP-1453)
MIN_DAYS_TRIAGE = 14
MIN_DAYS_FULL = 90
MIN_CGM_COVERAGE = 0.80
MIN_INSULIN_COVERAGE = 0.70

# DIA (validated EXP-1331)
DIA_HOURS = 6.0
DIA_STEPS = int(DIA_HOURS * STEPS_PER_HOUR)


# ═══════════════════════════════════════════════════════════════════════════
# Enums and data classes
# ═══════════════════════════════════════════════════════════════════════════

class Grade(str, Enum):
    A = 'A'
    B = 'B'
    C = 'C'
    D = 'D'

    @classmethod
    def from_score(cls, score: float) -> 'Grade':
        if score >= 80:
            return cls.A
        if score >= 65:
            return cls.B
        if score >= 50:
            return cls.C
        return cls.D


class SafetyTier(str, Enum):
    LOW = 'low'
    MODERATE = 'moderate'
    HIGH = 'high'
    CRITICAL = 'critical'

    @classmethod
    def from_tbr(cls, tbr_pct: float) -> 'SafetyTier':
        if tbr_pct >= 8.0:
            return cls.CRITICAL
        if tbr_pct >= 4.0:
            return cls.HIGH
        if tbr_pct >= 2.0:
            return cls.MODERATE
        return cls.LOW


class HypoCause(str, Enum):
    FASTING = 'fasting'       # basal too high
    POST_MEAL = 'post_meal'   # CR too aggressive
    AID_INDUCED = 'aid_induced'
    UNKNOWN = 'unknown'


@dataclass
class TimeInRanges:
    """ADA-standard time-in-range breakdown."""
    tir: float          # 70–180 mg/dL (%)
    tbr_l1: float       # 54–69 mg/dL (%)
    tbr_l2: float       # <54 mg/dL (%)
    tar_l1: float       # 181–250 mg/dL (%)
    tar_l2: float       # >250 mg/dL (%)
    cv: float           # coefficient of variation (%)
    mean_glucose: float # mg/dL
    overnight_tir: float  # 00:00–06:00 TIR (%)

    @property
    def total_tbr(self) -> float:
        return self.tbr_l1 + self.tbr_l2

    @property
    def total_tar(self) -> float:
        return self.tar_l1 + self.tar_l2

    @property
    def estimated_a1c(self) -> float:
        """eA1C via ADAG formula."""
        return (self.mean_glucose + 46.7) / 28.7

    @property
    def meets_ada_tir(self) -> bool:
        return self.tir >= ADA_TIR_TARGET

    @property
    def meets_ada_tbr(self) -> bool:
        return self.tbr_l1 < ADA_TBR_L1_TARGET and self.tbr_l2 < ADA_TBR_L2_TARGET

    @property
    def meets_ada_tar(self) -> bool:
        return self.tar_l1 < ADA_TAR_L1_TARGET and self.tar_l2 < ADA_TAR_L2_TARGET

    @property
    def meets_ada_cv(self) -> bool:
        return self.cv < ADA_CV_TARGET

    @property
    def ada_targets_met(self) -> int:
        return sum([self.meets_ada_tir, self.meets_ada_tbr,
                    self.meets_ada_tar, self.meets_ada_cv])

    @property
    def ada_status(self) -> str:
        met = self.ada_targets_met
        if met == 4:
            return 'meets_all_targets'
        if met >= 3:
            return 'partially_meets'
        if met >= 2:
            return 'below_targets'
        return 'significantly_below'


@dataclass
class TherapyFlags:
    """Detected therapy miscalibration flags."""
    basal_flag: bool = False
    cr_flag: bool = False
    isf_flag: bool = False
    cv_flag: bool = False
    tbr_flag: bool = False

    @property
    def n_flags(self) -> int:
        return sum([self.basal_flag, self.cr_flag, self.isf_flag,
                    self.cv_flag, self.tbr_flag])

    @property
    def has_safety_issue(self) -> bool:
        return self.tbr_flag


@dataclass
class HypoEpisode:
    """A detected hypoglycemic episode."""
    start_idx: int
    end_idx: int
    duration_steps: int
    nadir_mg_dl: float
    cause: HypoCause = HypoCause.UNKNOWN

    @property
    def duration_minutes(self) -> float:
        return self.duration_steps * 5.0

    @property
    def is_severe(self) -> bool:
        return self.nadir_mg_dl < SEVERE_HYPO_THRESHOLD


@dataclass
class Recommendation:
    """A specific therapy setting recommendation."""
    parameter: str          # 'basal', 'cr', 'isf'
    direction: str          # 'increase', 'decrease', 'maintain'
    magnitude_pct: float    # percentage change
    rationale: str
    priority: int = 1       # 1=highest
    confidence: float = 0.0

    @property
    def action_text(self) -> str:
        if self.direction == 'maintain':
            return f"Keep {self.parameter} unchanged"
        verb = 'Increase' if self.direction == 'increase' else 'Decrease'
        return f"{verb} {self.parameter} by {self.magnitude_pct:.0f}%"


@dataclass
class Preconditions:
    """Data quality precondition assessment."""
    cgm_coverage: float     # fraction
    insulin_coverage: float # fraction
    n_days: int
    n_meals: int
    n_corrections: int
    sufficient_for_triage: bool = False
    sufficient_for_full: bool = False
    issues: List[str] = field(default_factory=list)

    def check(self) -> 'Preconditions':
        self.issues = []
        if self.cgm_coverage < MIN_CGM_COVERAGE:
            self.issues.append(
                f"CGM coverage {self.cgm_coverage:.0%} < {MIN_CGM_COVERAGE:.0%} required")
        if self.insulin_coverage < MIN_INSULIN_COVERAGE:
            self.issues.append(
                f"Insulin coverage {self.insulin_coverage:.0%} < {MIN_INSULIN_COVERAGE:.0%} required")
        if self.n_days < MIN_DAYS_TRIAGE:
            self.issues.append(
                f"Only {self.n_days} days of data (need ≥{MIN_DAYS_TRIAGE} for triage)")
        self.sufficient_for_triage = (
            self.cgm_coverage >= MIN_CGM_COVERAGE
            and self.n_days >= MIN_DAYS_TRIAGE
        )
        self.sufficient_for_full = (
            self.sufficient_for_triage
            and self.n_days >= MIN_DAYS_FULL
            and self.insulin_coverage >= MIN_INSULIN_COVERAGE
        )
        return self


@dataclass
class TherapyAssessment:
    """Complete therapy assessment for a single patient."""
    patient_id: str
    preconditions: Preconditions
    time_in_ranges: TimeInRanges
    flags: TherapyFlags
    v10_score: float
    grade: Grade
    safety_score: float
    safety_tier: SafetyTier
    overnight_drift: float       # mg/dL/h
    max_excursion: float         # mg/dL (P90 post-meal)
    isf_ratio: float             # effective/profile
    overcorrection_rate: float   # %
    hypo_episodes: List[HypoEpisode] = field(default_factory=list)
    recommendations: List[Recommendation] = field(default_factory=list)

    @property
    def n_hypo_episodes(self) -> int:
        return len(self.hypo_episodes)

    @property
    def n_severe_hypos(self) -> int:
        return sum(1 for ep in self.hypo_episodes if ep.is_severe)

    @property
    def hypo_rate_per_day(self) -> float:
        days = max(self.preconditions.n_days, 1)
        return self.n_hypo_episodes / days

    @property
    def primary_hypo_cause(self) -> str:
        if not self.hypo_episodes:
            return 'none'
        causes = [ep.cause for ep in self.hypo_episodes]
        fasting = causes.count(HypoCause.FASTING)
        post_meal = causes.count(HypoCause.POST_MEAL)
        total = len(causes)
        if fasting / max(total, 1) > 0.6:
            return 'basal_too_high'
        if post_meal / max(total, 1) > 0.6:
            return 'cr_too_aggressive'
        return 'mixed'

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to JSON-safe dict."""
        return {
            'patient_id': self.patient_id,
            'grade': self.grade.value,
            'v10_score': round(self.v10_score, 1),
            'safety_tier': self.safety_tier.value,
            'safety_score': round(self.safety_score, 1),
            'time_in_ranges': {
                'tir': round(self.time_in_ranges.tir, 1),
                'tbr_l1': round(self.time_in_ranges.tbr_l1, 2),
                'tbr_l2': round(self.time_in_ranges.tbr_l2, 2),
                'tar_l1': round(self.time_in_ranges.tar_l1, 1),
                'tar_l2': round(self.time_in_ranges.tar_l2, 1),
                'cv': round(self.time_in_ranges.cv, 1),
                'mean_glucose': round(self.time_in_ranges.mean_glucose, 1),
                'estimated_a1c': round(self.time_in_ranges.estimated_a1c, 2),
                'ada_status': self.time_in_ranges.ada_status,
            },
            'flags': {
                'basal': self.flags.basal_flag,
                'cr': self.flags.cr_flag,
                'isf': self.flags.isf_flag,
                'cv': self.flags.cv_flag,
                'tbr': self.flags.tbr_flag,
            },
            'overnight_drift': round(self.overnight_drift, 2),
            'max_excursion': round(self.max_excursion, 1),
            'isf_ratio': round(self.isf_ratio, 2),
            'hypo_summary': {
                'total_episodes': self.n_hypo_episodes,
                'severe_episodes': self.n_severe_hypos,
                'rate_per_day': round(self.hypo_rate_per_day, 2),
                'primary_cause': self.primary_hypo_cause,
            },
            'recommendations': [
                {'action': r.action_text, 'rationale': r.rationale,
                 'priority': r.priority}
                for r in self.recommendations
            ],
            'preconditions': {
                'cgm_coverage': round(self.preconditions.cgm_coverage, 3),
                'n_days': self.preconditions.n_days,
                'sufficient_for_triage': self.preconditions.sufficient_for_triage,
                'sufficient_for_full': self.preconditions.sufficient_for_full,
                'issues': self.preconditions.issues,
            },
        }


# ═══════════════════════════════════════════════════════════════════════════
# Core computation functions
# ═══════════════════════════════════════════════════════════════════════════

def _safe(val: float) -> float:
    """Coerce NaN/Inf to 0."""
    if val is None or not np.isfinite(val):
        return 0.0
    return float(val)


def compute_time_in_ranges(glucose: np.ndarray) -> TimeInRanges:
    """Compute full ADA time-in-range breakdown from glucose array."""
    valid = glucose[~np.isnan(glucose)]
    n = len(valid)
    if n == 0:
        return TimeInRanges(0, 0, 0, 0, 0, 100, 0, 0)

    tir = float(np.mean((valid >= TIR_LO) & (valid <= TIR_HI)) * 100)
    tbr_l1 = float(np.mean((valid >= TBR_L1_LO) & (valid <= TBR_L1_HI)) * 100)
    tbr_l2 = float(np.mean(valid < TBR_L1_LO) * 100)
    tar_l1 = float(np.mean((valid >= TAR_L1_LO) & (valid <= TAR_L1_HI)) * 100)
    tar_l2 = float(np.mean(valid > TAR_L1_HI) * 100)
    cv = float(np.std(valid) / max(np.mean(valid), 1) * 100)
    mean_g = float(np.mean(valid))

    # Overnight TIR (00:00–06:00)
    total_steps = len(glucose)
    overnight_tirs = []
    n_days = total_steps // STEPS_PER_DAY
    for d in range(min(n_days, 365)):
        s = d * STEPS_PER_DAY
        e = s + 6 * STEPS_PER_HOUR
        if e > total_steps:
            break
        seg = glucose[s:e]
        seg_valid = seg[~np.isnan(seg)]
        if len(seg_valid) >= STEPS_PER_HOUR:
            overnight_tirs.append(
                float(np.mean((seg_valid >= TIR_LO) & (seg_valid <= TIR_HI)) * 100))
    overnight_tir = float(np.mean(overnight_tirs)) if overnight_tirs else 0.0

    return TimeInRanges(
        tir=_safe(tir), tbr_l1=_safe(tbr_l1), tbr_l2=_safe(tbr_l2),
        tar_l1=_safe(tar_l1), tar_l2=_safe(tar_l2),
        cv=_safe(cv), mean_glucose=_safe(mean_g),
        overnight_tir=_safe(overnight_tir),
    )


def compute_safety_score(tbr_l1: float, tbr_l2: float,
                         overcorrection_rate: float) -> float:
    """Safety score (0–100): penalizes TBR and overcorrection."""
    penalty = tbr_l1 * 10.0 + tbr_l2 * 50.0 + overcorrection_rate
    return max(0.0, min(100.0, 100.0 - penalty))


def compute_v10_score(tir: float, cv: float, overnight_tir: float,
                      safety_score: float) -> float:
    """v10 composite score (0–100)."""
    score = (tir * V10_WEIGHTS['tir']
             + max(0, 100 - cv * 2) * V10_WEIGHTS['cv']
             + overnight_tir * V10_WEIGHTS['overnight']
             + safety_score * V10_WEIGHTS['safety'])
    return max(0.0, min(100.0, score))


def compute_overnight_drift(glucose: np.ndarray, bolus: np.ndarray,
                            carbs: np.ndarray) -> float:
    """Median absolute overnight (00:00–06:00) glucose drift in mg/dL/h."""
    n = len(glucose)
    n_days = n // STEPS_PER_DAY
    drifts = []

    for d in range(min(n_days, 365)):
        seg_start = d * STEPS_PER_DAY
        seg_end = seg_start + 6 * STEPS_PER_HOUR
        if seg_end > n:
            break

        seg_g = glucose[seg_start:seg_end]
        seg_valid = ~np.isnan(seg_g)
        if seg_valid.sum() < STEPS_PER_HOUR:
            continue

        # Skip nights with significant bolus/carb activity
        lookback = 4 * STEPS_PER_HOUR
        check_start = max(0, seg_start - lookback)
        if np.nansum(bolus[check_start:seg_end]) > 0.3:
            continue
        if np.nansum(carbs[check_start:seg_end]) > 2.0:
            continue

        valid_idx = np.where(seg_valid)[0]
        valid_bg = seg_g[valid_idx]
        hours = valid_idx / STEPS_PER_HOUR
        if len(valid_idx) < 3:
            continue

        slope = np.polyfit(hours, valid_bg, 1)[0]
        drifts.append(abs(float(slope)))

    return float(np.median(drifts)) if drifts else 0.0


def compute_max_excursion(glucose: np.ndarray, carbs: np.ndarray) -> float:
    """90th percentile post-meal glucose excursion (mg/dL)."""
    n = len(glucose)
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
        excursions.append(float(np.nanmax(valid_post) - glucose[i]))

    if not excursions:
        return 0.0
    return float(np.percentile(excursions, 90))


def compute_isf_ratio(glucose: np.ndarray, bolus: np.ndarray,
                      carbs: np.ndarray) -> float:
    """Deconfounded ISF from correction boluses ≥2U with no nearby carbs."""
    n = len(glucose)
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
        if bolus[i] > 0:
            events.append(drop / bolus[i])

    if len(events) < MIN_ISF_EVENTS:
        return 1.0
    return float(np.median(events))


def compute_overcorrection_rate(glucose: np.ndarray, bolus: np.ndarray,
                                carbs: np.ndarray) -> float:
    """% of correction boluses followed by hypo (<70)."""
    n = len(glucose)
    events = 0
    hypos = 0

    for i in range(n):
        if bolus[i] < MIN_BOLUS_ISF or np.isnan(glucose[i]):
            continue
        c_start = max(0, i - STEPS_PER_HOUR)
        c_end = min(n, i + STEPS_PER_HOUR)
        if np.nansum(carbs[c_start:c_end]) > 2:
            continue
        events += 1
        end = min(i + 4 * STEPS_PER_HOUR, n)
        post = glucose[i:end]
        valid_post = post[~np.isnan(post)]
        if len(valid_post) > 0 and np.nanmin(valid_post) < TIR_LO:
            hypos += 1

    return float(hypos / max(events, 1) * 100)


def detect_hypo_episodes(glucose: np.ndarray, carbs: np.ndarray,
                         temp_rate: np.ndarray) -> List[HypoEpisode]:
    """Detect and classify hypoglycemic episodes."""
    n = len(glucose)
    episodes = []
    meal_times = set(np.where(carbs > 5)[0])
    meal_window = 4 * STEPS_PER_HOUR
    i = 0

    while i < n:
        if np.isnan(glucose[i]) or glucose[i] >= HYPO_THRESHOLD:
            i += 1
            continue

        start = i
        nadir = glucose[i]
        nadir_idx = i
        count = 1
        j = i + 1
        while j < n:
            if np.isnan(glucose[j]):
                j += 1
                continue
            if glucose[j] < HYPO_THRESHOLD:
                count += 1
                if glucose[j] < nadir:
                    nadir = glucose[j]
                    nadir_idx = j
                j += 1
            else:
                break
        end = j

        if count >= HYPO_MIN_CONSECUTIVE:
            # Classify cause
            cause = HypoCause.UNKNOWN
            is_post_meal = any(
                0 < (start - mt) <= meal_window
                for mt in meal_times if mt < start
            )
            # Check AID-induced (elevated temp rate before episode)
            pre_start = max(0, start - 2 * STEPS_PER_HOUR)
            pre_temp = temp_rate[pre_start:start]
            aid_elevated = (len(pre_temp) > 0
                            and np.nanmean(pre_temp) > 0.5)

            if aid_elevated:
                cause = HypoCause.AID_INDUCED
            elif is_post_meal:
                cause = HypoCause.POST_MEAL
            else:
                cause = HypoCause.FASTING

            episodes.append(HypoEpisode(
                start_idx=start, end_idx=end,
                duration_steps=end - start,
                nadir_mg_dl=float(nadir),
                cause=cause,
            ))
        i = j

    return episodes


def assess_preconditions(glucose: np.ndarray, bolus: np.ndarray,
                         carbs: np.ndarray, iob: np.ndarray) -> Preconditions:
    """Assess data quality preconditions."""
    n = len(glucose)
    cgm_coverage = float(np.sum(~np.isnan(glucose)) / max(n, 1))
    n_days = n // STEPS_PER_DAY

    # Insulin coverage: fraction of steps with any insulin signal
    has_insulin = ((~np.isnan(bolus) & (bolus > 0))
                   | (~np.isnan(iob) & (iob > 0)))
    insulin_coverage = float(np.sum(has_insulin) / max(n, 1))

    # Count meals and corrections
    n_meals = int(np.sum(carbs > 5))
    n_corrections = int(np.sum(bolus >= MIN_BOLUS_ISF))

    return Preconditions(
        cgm_coverage=cgm_coverage,
        insulin_coverage=insulin_coverage,
        n_days=n_days,
        n_meals=n_meals,
        n_corrections=n_corrections,
    ).check()


# ═══════════════════════════════════════════════════════════════════════════
# Recommendation engine
# ═══════════════════════════════════════════════════════════════════════════

def generate_recommendations(flags: TherapyFlags, grade: Grade,
                             overnight_drift: float, max_excursion: float,
                             cv: float, total_tbr: float,
                             safety_tier: SafetyTier) -> List[Recommendation]:
    """Generate prioritized therapy recommendations with safety-first protocol.

    Fix order (validated EXP-1479): basal → CR → ISF
    Safety override (validated EXP-1496): TBR>4% → reduce aggressiveness first
    """
    recs = []
    priority = 1

    # Safety-first: if TBR exceeds ADA target, override all other recs
    if total_tbr >= ADA_TBR_L1_TARGET:
        tbr_excess = total_tbr - ADA_TBR_L1_TARGET
        recs.append(Recommendation(
            parameter='aggressiveness',
            direction='decrease',
            magnitude_pct=min(20, tbr_excess * 5),
            rationale=(f"TBR {total_tbr:.1f}% exceeds ADA 4% target — "
                       f"reduce AID aggressiveness before other changes"),
            priority=priority,
            confidence=0.9,
        ))
        priority += 1

    # 1. Basal (from overnight drift)
    if flags.basal_flag:
        recs.append(Recommendation(
            parameter='basal',
            direction='decrease' if overnight_drift > 0 else 'increase',
            magnitude_pct=BASAL_ADJUST_PCT,
            rationale=f"Overnight drift {overnight_drift:+.1f} mg/dL/h",
            priority=priority,
            confidence=0.85,
        ))
        priority += 1

    # 2. CR (from post-meal excursions)
    if flags.cr_flag:
        adj = CR_ADJUST_GRADE_D if grade == Grade.D else CR_ADJUST_STANDARD
        recs.append(Recommendation(
            parameter='cr',
            direction='decrease',
            magnitude_pct=adj,
            rationale=f"Post-meal excursion P90={max_excursion:.0f} mg/dL",
            priority=priority,
            confidence=0.9,
        ))
        priority += 1

    # 3. ISF (from overcorrection / CV)
    if flags.cv_flag or flags.isf_flag:
        # Safety gate: don't decrease ISF if TBR already high
        direction = 'increase'
        if total_tbr >= ADA_TBR_L1_TARGET and direction == 'decrease':
            direction = 'increase'  # override
        recs.append(Recommendation(
            parameter='isf',
            direction=direction,
            magnitude_pct=ISF_ADJUST_PCT,
            rationale=f"CV {cv:.1f}% {'>' if cv > CV_THRESHOLD else '<'} {CV_THRESHOLD}%",
            priority=priority,
            confidence=0.7,
        ))
        priority += 1

    if not recs:
        recs.append(Recommendation(
            parameter='all',
            direction='maintain',
            magnitude_pct=0,
            rationale="All settings within acceptable ranges",
            priority=1,
            confidence=0.9,
        ))

    return recs


# ═══════════════════════════════════════════════════════════════════════════
# Main pipeline
# ═══════════════════════════════════════════════════════════════════════════

class TherapyPipeline:
    """Production therapy detection and recommendation pipeline (v10)."""

    def __init__(self):
        self._patients: Dict[str, Dict[str, np.ndarray]] = {}
        self._assessments: Dict[str, TherapyAssessment] = {}

    def load_patients(self, patients_dir: str,
                      max_patients: int = 50) -> List[str]:
        """Load patient data from Nightscout JSON exports."""
        if _load_patients is None:
            raise ImportError(
                "cgmencode.exp_metabolic_flux not available. "
                "Set PYTHONPATH to include tools/")

        raw = _load_patients(patients_dir, max_patients=max_patients)
        loaded = []
        for p in raw:
            pid = p['name']
            df = p['df']
            glucose = df['glucose'].values
            if np.sum(~np.isnan(glucose)) < 1000:
                continue
            self._patients[pid] = {
                'glucose': glucose,
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
            loaded.append(pid)
        return sorted(loaded)

    def load_arrays(self, patient_id: str, glucose: np.ndarray,
                    bolus: np.ndarray, carbs: np.ndarray,
                    temp_rate: Optional[np.ndarray] = None,
                    iob: Optional[np.ndarray] = None,
                    cob: Optional[np.ndarray] = None) -> None:
        """Load pre-processed arrays for a single patient."""
        n = len(glucose)
        self._patients[patient_id] = {
            'glucose': glucose,
            'bolus': bolus,
            'carbs': carbs,
            'temp_rate': temp_rate if temp_rate is not None else np.zeros(n),
            'iob': iob if iob is not None else np.zeros(n),
            'cob': cob if cob is not None else np.zeros(n),
        }

    def assess(self, patient_id: str) -> TherapyAssessment:
        """Run full v10 therapy assessment for a patient."""
        if patient_id not in self._patients:
            raise KeyError(f"Patient '{patient_id}' not loaded")

        p = self._patients[patient_id]
        glucose = p['glucose']
        bolus = p['bolus']
        carbs = p['carbs']
        temp_rate = p['temp_rate']
        iob = p['iob']
        n = len(glucose)

        # 1. Preconditions
        preconditions = assess_preconditions(glucose, bolus, carbs, iob)

        # 2. Time-in-ranges
        tir_data = compute_time_in_ranges(glucose)

        # 3. Detection metrics
        drift = compute_overnight_drift(glucose, bolus, carbs)
        excursion = compute_max_excursion(glucose, carbs)
        isf_ratio = compute_isf_ratio(glucose, bolus, carbs)
        overcorr = compute_overcorrection_rate(glucose, bolus, carbs)

        # 4. Flags
        flags = TherapyFlags(
            basal_flag=abs(drift) >= DRIFT_THRESHOLD,
            cr_flag=excursion >= EXCURSION_THRESHOLD,
            cv_flag=tir_data.cv >= CV_THRESHOLD,
            tbr_flag=tir_data.total_tbr >= ADA_TBR_L1_TARGET,
        )

        # 5. Safety & scoring
        safety = compute_safety_score(tir_data.tbr_l1, tir_data.tbr_l2, overcorr)
        v10 = compute_v10_score(tir_data.tir, tir_data.cv,
                                tir_data.overnight_tir, safety)
        grade = Grade.from_score(v10)
        safety_tier = SafetyTier.from_tbr(tir_data.total_tbr)

        # 6. Hypo episodes
        hypos = detect_hypo_episodes(glucose, carbs, temp_rate)

        # 7. Recommendations
        recs = generate_recommendations(
            flags, grade, drift, excursion, tir_data.cv,
            tir_data.total_tbr, safety_tier)

        assessment = TherapyAssessment(
            patient_id=patient_id,
            preconditions=preconditions,
            time_in_ranges=tir_data,
            flags=flags,
            v10_score=v10,
            grade=grade,
            safety_score=safety,
            safety_tier=safety_tier,
            overnight_drift=drift,
            max_excursion=excursion,
            isf_ratio=isf_ratio,
            overcorrection_rate=overcorr,
            hypo_episodes=hypos,
            recommendations=recs,
        )
        self._assessments[patient_id] = assessment
        return assessment

    def assess_all(self) -> Dict[str, TherapyAssessment]:
        """Assess all loaded patients."""
        for pid in sorted(self._patients):
            self.assess(pid)
        return dict(self._assessments)

    # ───────────────────────────────────────────────────────────────────
    # Report generation
    # ───────────────────────────────────────────────────────────────────

    def patient_report(self, patient_id: str) -> 'PatientReport':
        """Generate a patient-facing therapy report."""
        if patient_id not in self._assessments:
            self.assess(patient_id)
        return PatientReport(self._assessments[patient_id])

    def cohort_report(self) -> 'CohortReport':
        """Generate a clinician-facing cohort summary."""
        if not self._assessments:
            self.assess_all()
        return CohortReport(list(self._assessments.values()))


# ═══════════════════════════════════════════════════════════════════════════
# Report classes
# ═══════════════════════════════════════════════════════════════════════════

class PatientReport:
    """Individual patient therapy settings report.

    Designed for patients and their clinicians to review together.
    Includes: current status, identified issues, specific recommendations,
    and safety alerts.
    """

    def __init__(self, assessment: TherapyAssessment):
        self.a = assessment

    def text_summary(self) -> str:
        """Generate human-readable text report."""
        a = self.a
        tir = a.time_in_ranges

        lines = []
        lines.append("=" * 70)
        lines.append(f"  THERAPY SETTINGS REPORT — Patient {a.patient_id}")
        lines.append(f"  Pipeline v10 | {a.preconditions.n_days} days analyzed")
        lines.append("=" * 70)
        lines.append("")

        # Overall grade
        grade_desc = {
            Grade.A: "Excellent — settings well-calibrated",
            Grade.B: "Good — minor adjustments may help",
            Grade.C: "Fair — several settings need attention",
            Grade.D: "Needs improvement — significant miscalibration detected",
        }
        lines.append(f"  OVERALL GRADE:  {a.grade.value}  (score: {a.v10_score:.0f}/100)")
        lines.append(f"  {grade_desc[a.grade]}")
        lines.append("")

        # Safety alert
        if a.safety_tier in (SafetyTier.HIGH, SafetyTier.CRITICAL):
            lines.append("  ⚠️  SAFETY ALERT  ⚠️")
            lines.append(f"  Hypoglycemia risk: {a.safety_tier.value.upper()}")
            lines.append(f"  Time below 70 mg/dL: {tir.total_tbr:.1f}% "
                         f"(ADA target: <4%)")
            if a.n_hypo_episodes > 0:
                lines.append(f"  Hypo episodes: {a.n_hypo_episodes} "
                             f"({a.hypo_rate_per_day:.1f}/day), "
                             f"{a.n_severe_hypos} severe (<54 mg/dL)")
            lines.append("")

        # Time-in-Range summary
        lines.append("  TIME-IN-RANGE ANALYSIS")
        lines.append("  " + "─" * 50)

        def _ada_check(val, target, op='>='):
            if op == '>=':
                return '✅' if val >= target else '❌'
            return '✅' if val < target else '❌'

        lines.append(f"  {_ada_check(tir.tir, 70)} Time in Range (70-180):  "
                     f"{tir.tir:.1f}%  (target: ≥70%)")
        lines.append(f"  {_ada_check(tir.total_tbr, 4, '<')} Time Below Range (<70):  "
                     f"{tir.total_tbr:.1f}%  (target: <4%)")
        lines.append(f"    └─ Level 1 (54-69):  {tir.tbr_l1:.1f}%  "
                     f"(target: <4%)")
        lines.append(f"    └─ Level 2 (<54):    {tir.tbr_l2:.1f}%  "
                     f"(target: <1%)")
        lines.append(f"  {_ada_check(tir.total_tar, 30, '<')} Time Above Range (>180):  "
                     f"{tir.total_tar:.1f}%  (target: <30%)")
        lines.append(f"  {_ada_check(tir.cv, 36, '<')} Glucose Variability (CV):  "
                     f"{tir.cv:.1f}%  (target: <36%)")
        lines.append(f"  Estimated A1C:  {tir.estimated_a1c:.1f}%")
        lines.append(f"  Overnight TIR:  {tir.overnight_tir:.1f}%")
        lines.append(f"  ADA Status:     {tir.ada_status.replace('_', ' ').title()}")
        lines.append("")

        # Detected issues
        lines.append("  DETECTED ISSUES")
        lines.append("  " + "─" * 50)
        if a.flags.n_flags == 0:
            lines.append("  ✅ No significant issues detected")
        else:
            if a.flags.basal_flag:
                direction = "rising" if a.overnight_drift > 0 else "falling"
                lines.append(f"  🔴 Basal Rate: Overnight glucose {direction} "
                             f"at {abs(a.overnight_drift):.1f} mg/dL/h")
                lines.append(f"     → Suggests basal rate is too "
                             f"{'low' if a.overnight_drift > 0 else 'high'}")
            if a.flags.cr_flag:
                lines.append(f"  🔴 Carb Ratio: Post-meal spikes averaging "
                             f"{a.max_excursion:.0f} mg/dL (90th percentile)")
                lines.append(f"     → Suggests carb ratio needs adjustment")
            if a.flags.cv_flag:
                lines.append(f"  🟡 Variability: CV={a.time_in_ranges.cv:.1f}% "
                             f"exceeds {CV_THRESHOLD}% target")
            if a.flags.tbr_flag:
                lines.append(f"  🔴 Hypoglycemia: TBR={tir.total_tbr:.1f}% "
                             f"exceeds ADA 4% safety threshold")
        lines.append("")

        # Hypo analysis
        if a.n_hypo_episodes > 0:
            lines.append("  HYPOGLYCEMIA ANALYSIS")
            lines.append("  " + "─" * 50)
            cause_counts = {}
            for ep in a.hypo_episodes:
                cause_counts[ep.cause] = cause_counts.get(ep.cause, 0) + 1
            for cause, count in sorted(cause_counts.items(),
                                       key=lambda x: -x[1]):
                pct = count / a.n_hypo_episodes * 100
                cause_label = {
                    HypoCause.FASTING: "Fasting (basal issue)",
                    HypoCause.POST_MEAL: "Post-meal (CR issue)",
                    HypoCause.AID_INDUCED: "AID-induced (algorithm too aggressive)",
                    HypoCause.UNKNOWN: "Unknown cause",
                }[cause]
                lines.append(f"  {count:3d} ({pct:4.0f}%)  {cause_label}")
            lines.append("")

        # Recommendations
        lines.append("  RECOMMENDATIONS (in priority order)")
        lines.append("  " + "─" * 50)
        for i, rec in enumerate(a.recommendations, 1):
            lines.append(f"  {i}. {rec.action_text}")
            lines.append(f"     Rationale: {rec.rationale}")
            lines.append(f"     Confidence: {rec.confidence:.0%}")
            lines.append("")

        # Data quality
        pc = a.preconditions
        lines.append("  DATA QUALITY")
        lines.append("  " + "─" * 50)
        lines.append(f"  CGM coverage:    {pc.cgm_coverage:.0%}")
        lines.append(f"  Days analyzed:   {pc.n_days}")
        lines.append(f"  Meals detected:  {pc.n_meals}")
        lines.append(f"  Corrections:     {pc.n_corrections}")
        quality = ("Full analysis" if pc.sufficient_for_full
                   else "Triage only" if pc.sufficient_for_triage
                   else "Insufficient data")
        lines.append(f"  Analysis level:  {quality}")
        if pc.issues:
            for issue in pc.issues:
                lines.append(f"  ⚠️  {issue}")
        lines.append("")
        lines.append("  Note: This report is for informational purposes.")
        lines.append("  Discuss any changes with your healthcare provider.")
        lines.append("=" * 70)

        return "\n".join(lines)

    def to_json(self) -> str:
        """Serialize report to JSON."""
        return json.dumps(self.a.to_dict(), indent=2)

    def save(self, path: str) -> None:
        """Save report to file (text or JSON based on extension)."""
        path = str(path)
        if path.endswith('.json'):
            content = self.to_json()
        else:
            content = self.text_summary()
        with open(path, 'w') as f:
            f.write(content)


class CohortReport:
    """Clinician-facing cohort summary report.

    Designed for endocrinologists reviewing a panel of patients.
    Includes: cohort overview, risk stratification, population trends,
    and per-patient action summaries.
    """

    def __init__(self, assessments: List[TherapyAssessment]):
        self.assessments = sorted(assessments, key=lambda a: a.v10_score)

    def text_summary(self) -> str:
        """Generate clinician-facing cohort summary."""
        aa = self.assessments
        n = len(aa)
        if n == 0:
            return "No patients assessed."

        lines = []
        lines.append("=" * 78)
        lines.append("  THERAPY COHORT SUMMARY — Clinician Report")
        lines.append(f"  {n} patients | Pipeline v10")
        lines.append("=" * 78)
        lines.append("")

        # Grade distribution
        grade_dist = {g: 0 for g in Grade}
        for a in aa:
            grade_dist[a.grade] += 1
        lines.append("  GRADE DISTRIBUTION")
        lines.append("  " + "─" * 60)
        for g in [Grade.A, Grade.B, Grade.C, Grade.D]:
            count = grade_dist[g]
            bar = "█" * (count * 4)
            lines.append(f"  {g.value}: {count:2d}  {bar}")
        lines.append("")

        # Safety tiers
        tier_dist = {}
        for a in aa:
            tier_dist[a.safety_tier] = tier_dist.get(a.safety_tier, 0) + 1
        lines.append("  SAFETY RISK STRATIFICATION")
        lines.append("  " + "─" * 60)
        for tier in [SafetyTier.CRITICAL, SafetyTier.HIGH,
                     SafetyTier.MODERATE, SafetyTier.LOW]:
            count = tier_dist.get(tier, 0)
            emoji = {'critical': '🔴', 'high': '🟠',
                     'moderate': '🟡', 'low': '🟢'}[tier.value]
            lines.append(f"  {emoji} {tier.value.upper():10s}: {count}")
        lines.append("")

        # Population metrics
        tirs = [a.time_in_ranges.tir for a in aa]
        tbrs = [a.time_in_ranges.total_tbr for a in aa]
        cvs = [a.time_in_ranges.cv for a in aa]
        a1cs = [a.time_in_ranges.estimated_a1c for a in aa]
        lines.append("  POPULATION METRICS")
        lines.append("  " + "─" * 60)
        lines.append(f"  TIR:    {np.mean(tirs):.1f}% ± {np.std(tirs):.1f}%  "
                     f"(range: {np.min(tirs):.1f}–{np.max(tirs):.1f}%)")
        lines.append(f"  TBR:    {np.mean(tbrs):.1f}% ± {np.std(tbrs):.1f}%  "
                     f"(range: {np.min(tbrs):.1f}–{np.max(tbrs):.1f}%)")
        lines.append(f"  CV:     {np.mean(cvs):.1f}% ± {np.std(cvs):.1f}%  "
                     f"(range: {np.min(cvs):.1f}–{np.max(cvs):.1f}%)")
        lines.append(f"  eA1C:   {np.mean(a1cs):.1f}% ± {np.std(a1cs):.1f}%  "
                     f"(range: {np.min(a1cs):.1f}–{np.max(a1cs):.1f}%)")
        ada_met = sum(1 for a in aa
                      if a.time_in_ranges.ada_status == 'meets_all_targets')
        lines.append(f"  ADA:    {ada_met}/{n} ({ada_met/n:.0%}) meet all targets")
        lines.append("")

        # Common issues
        flag_counts = {'basal': 0, 'cr': 0, 'isf': 0, 'cv': 0, 'tbr': 0}
        for a in aa:
            if a.flags.basal_flag: flag_counts['basal'] += 1
            if a.flags.cr_flag: flag_counts['cr'] += 1
            if a.flags.isf_flag: flag_counts['isf'] += 1
            if a.flags.cv_flag: flag_counts['cv'] += 1
            if a.flags.tbr_flag: flag_counts['tbr'] += 1
        lines.append("  MOST COMMON ISSUES (across cohort)")
        lines.append("  " + "─" * 60)
        for flag, count in sorted(flag_counts.items(), key=lambda x: -x[1]):
            if count > 0:
                label = {'basal': 'Basal rate miscalibration',
                         'cr': 'Carb ratio too aggressive',
                         'isf': 'ISF mismatch',
                         'cv': 'High glucose variability',
                         'tbr': 'Excessive hypoglycemia (TBR>4%)'}[flag]
                lines.append(f"  {count:2d}/{n} ({count/n:.0%})  {label}")
        lines.append("")

        # Per-patient action table
        lines.append("  PATIENT ACTION SUMMARY (sorted by severity)")
        lines.append("  " + "─" * 60)
        lines.append(f"  {'ID':>4s}  {'Grade':>5s}  {'Score':>5s}  {'TIR%':>5s}  "
                     f"{'TBR%':>5s}  {'Safety':>8s}  {'Top Action':<30s}")
        lines.append("  " + "─" * 60)
        for a in aa:
            top_action = (a.recommendations[0].action_text
                          if a.recommendations else "None")[:30]
            lines.append(
                f"  {a.patient_id:>4s}  {a.grade.value:>5s}  "
                f"{a.v10_score:5.1f}  {a.time_in_ranges.tir:5.1f}  "
                f"{a.time_in_ranges.total_tbr:5.1f}  "
                f"{a.safety_tier.value:>8s}  {top_action:<30s}")
        lines.append("")

        # Urgent action items
        urgent = [a for a in aa if a.safety_tier in
                  (SafetyTier.CRITICAL, SafetyTier.HIGH)]
        if urgent:
            lines.append("  ⚠️  URGENT ACTIONS REQUIRED")
            lines.append("  " + "─" * 60)
            for a in urgent:
                lines.append(f"  Patient {a.patient_id}: "
                             f"{a.safety_tier.value.upper()} risk "
                             f"(TBR={a.time_in_ranges.total_tbr:.1f}%)")
                for rec in a.recommendations[:2]:
                    lines.append(f"    → {rec.action_text}")
            lines.append("")

        lines.append("  Generated by Therapy Pipeline v10")
        lines.append("  Validated across 230 experiments (EXP-1281–1510)")
        lines.append("=" * 78)

        return "\n".join(lines)

    def to_json(self) -> str:
        """Serialize cohort report to JSON."""
        data = {
            'n_patients': len(self.assessments),
            'grade_distribution': {},
            'population_metrics': {},
            'patients': [],
        }
        for a in self.assessments:
            g = a.grade.value
            data['grade_distribution'][g] = data['grade_distribution'].get(g, 0) + 1
            data['patients'].append(a.to_dict())

        tirs = [a.time_in_ranges.tir for a in self.assessments]
        data['population_metrics'] = {
            'mean_tir': round(float(np.mean(tirs)), 1),
            'mean_tbr': round(float(np.mean([a.time_in_ranges.total_tbr
                                              for a in self.assessments])), 1),
            'mean_cv': round(float(np.mean([a.time_in_ranges.cv
                                             for a in self.assessments])), 1),
            'mean_a1c': round(float(np.mean([a.time_in_ranges.estimated_a1c
                                              for a in self.assessments])), 2),
        }
        return json.dumps(data, indent=2)

    def save(self, path: str) -> None:
        """Save cohort report to file."""
        path = str(path)
        if path.endswith('.json'):
            content = self.to_json()
        else:
            content = self.text_summary()
        with open(path, 'w') as f:
            f.write(content)


# ═══════════════════════════════════════════════════════════════════════════
# CLI entry point
# ═══════════════════════════════════════════════════════════════════════════

def main():
    """CLI for running therapy pipeline and generating reports."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Therapy Detection Pipeline v10 — '
                    'Analyze AID therapy settings from CGM+insulin data')
    parser.add_argument('patients_dir', nargs='?',
                        default=os.path.join(os.path.dirname(__file__),
                                             '..', '..', 'externals',
                                             'ns-data', 'patients'),
                        help='Path to patient data directory')
    parser.add_argument('--max-patients', type=int, default=50)
    parser.add_argument('--patient', type=str,
                        help='Generate report for specific patient')
    parser.add_argument('--cohort', action='store_true',
                        help='Generate cohort summary')
    parser.add_argument('--json', action='store_true',
                        help='Output JSON instead of text')
    parser.add_argument('--save', type=str,
                        help='Save report to file')
    args = parser.parse_args()

    pipeline = TherapyPipeline()
    patients = pipeline.load_patients(args.patients_dir, args.max_patients)
    print(f"Loaded {len(patients)} patients: {', '.join(patients)}")

    if args.patient:
        report = pipeline.patient_report(args.patient)
        output = report.to_json() if args.json else report.text_summary()
        print(output)
        if args.save:
            report.save(args.save)
    elif args.cohort:
        report = pipeline.cohort_report()
        output = report.to_json() if args.json else report.text_summary()
        print(output)
        if args.save:
            report.save(args.save)
    else:
        # Default: assess all, print cohort summary
        pipeline.assess_all()
        report = pipeline.cohort_report()
        print(report.text_summary())


if __name__ == '__main__':
    main()
