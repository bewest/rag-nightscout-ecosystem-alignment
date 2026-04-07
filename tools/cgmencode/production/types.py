"""
types.py — Shared data contracts for the production inference pipeline.

All modules communicate through these dataclasses. They define the
input/output boundaries and make the pipeline composable.

Design principles:
- Optional fields for graceful degradation (no IOB? still run what we can)
- NumPy arrays for numeric data (no pandas dependency in hot path)
- Metadata dicts for extensibility without breaking contracts
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

import numpy as np


# ── Enums ─────────────────────────────────────────────────────────────

class GlycemicGrade(str, Enum):
    A = "A"  # TIR >= 70%, TBR < 4%
    B = "B"  # TIR >= 60%, TBR < 5%
    C = "C"  # TIR >= 50%
    D = "D"  # Below all thresholds


class BasalAssessment(str, Enum):
    TOO_LOW = "basal_too_low"
    APPROPRIATE = "basal_appropriate"
    TOO_HIGH = "basal_too_high"
    SLIGHTLY_HIGH = "basal_slightly_high"


class EventType(str, Enum):
    NONE = "none"
    MEAL = "meal"
    CORRECTION_BOLUS = "correction_bolus"
    OVERRIDE = "override"
    EATING_SOON = "eating_soon"
    EXERCISE = "exercise"
    SLEEP = "sleep"
    SICK = "sick"


class OnboardingPhase(str, Enum):
    POPULATION_DEFAULTS = "population_defaults"   # Day 0-2
    EARLY_PERSONAL = "early_personal"             # Day 3-6
    WARM_START_PERSONAL = "warm_start_personal"   # Day 7+
    FULLY_CALIBRATED = "fully_calibrated"         # Day 14+


class Phenotype(str, Enum):
    MORNING_HIGH = "morning_high"
    NIGHT_HYPO = "night_hypo"
    STABLE = "stable"


# ── Input Data ────────────────────────────────────────────────────────

@dataclass
class PatientProfile:
    """Therapy settings from Nightscout profile.json."""
    isf_schedule: List[Dict]       # [{time: "00:00", value: 50}, ...]
    cr_schedule: List[Dict]        # [{time: "00:00", value: 10}, ...]
    basal_schedule: List[Dict]     # [{time: "00:00", value: 0.8}, ...]
    dia_hours: float = 5.0
    target_low: float = 70.0
    target_high: float = 180.0


@dataclass
class PatientData:
    """Raw patient data at 5-minute resolution.

    All arrays are aligned to the same time grid. Length N = number of
    5-minute intervals. Missing values are NaN.
    """
    glucose: np.ndarray             # (N,) mg/dL, raw CGM readings
    timestamps: np.ndarray          # (N,) Unix timestamps (ms)
    profile: PatientProfile

    # Optional — pipeline degrades gracefully without these
    iob: Optional[np.ndarray] = None          # (N,) Units insulin on board
    cob: Optional[np.ndarray] = None          # (N,) grams carbs on board
    bolus: Optional[np.ndarray] = None        # (N,) Units bolus per interval
    carbs: Optional[np.ndarray] = None        # (N,) grams carbs per interval
    basal_rate: Optional[np.ndarray] = None   # (N,) U/hr actual basal rate
    patient_id: str = "unknown"
    metadata: Dict = field(default_factory=dict)

    @property
    def n_samples(self) -> int:
        return len(self.glucose)

    @property
    def has_insulin_data(self) -> bool:
        return self.iob is not None and not np.all(np.isnan(self.iob))

    @property
    def hours_of_data(self) -> float:
        return self.n_samples * 5.0 / 60.0

    @property
    def days_of_data(self) -> float:
        return self.hours_of_data / 24.0


# ── Intermediate Results ──────────────────────────────────────────────

@dataclass
class CleanedData:
    """Spike-cleaned glucose with cleaning metadata."""
    glucose: np.ndarray          # (N,) cleaned glucose, mg/dL
    original_glucose: np.ndarray # (N,) raw glucose for comparison
    spike_indices: np.ndarray    # indices of detected spikes
    n_spikes: int
    sigma_threshold: float       # always 2.0 per research
    cleaning_r2_gain: Optional[float] = None  # R² improvement if measured

    @property
    def spike_rate(self) -> float:
        """Fraction of readings that were spikes."""
        n = len(self.original_glucose)
        return self.n_spikes / n if n > 0 else 0.0


@dataclass
class MetabolicState:
    """Supply-demand flux decomposition from physics engine."""
    supply: np.ndarray       # (N,) hepatic + carb absorption, mg/dL per 5min
    demand: np.ndarray       # (N,) insulin action, mg/dL per 5min
    hepatic: np.ndarray      # (N,) hepatic production alone
    carb_supply: np.ndarray  # (N,) carb absorption alone
    net_flux: np.ndarray     # (N,) supply - demand (signed)
    residual: np.ndarray     # (N,) actual BG change - predicted change

    @property
    def mean_net_flux(self) -> float:
        valid = np.isfinite(self.net_flux)
        return float(np.mean(self.net_flux[valid])) if valid.any() else 0.0


# ── Event & Risk Outputs ──────────────────────────────────────────────

@dataclass
class RiskAssessment:
    """Event detection and risk classification output."""
    high_2h_probability: float           # P(BG > 180 in 2h)
    hypo_2h_probability: float           # P(BG < 70 in 2h)
    current_event: EventType             # detected current event
    event_probabilities: Dict[str, float]  # per-event-type probabilities
    lead_time_minutes: Optional[float] = None  # estimated event lead time
    features_used: int = 43              # number of features in classifier


@dataclass
class HypoAlert:
    """Specialized hypoglycemia prediction output."""
    probability: float                 # P(hypo) at chosen horizon
    horizon_minutes: int               # prediction horizon (default 120)
    alert_threshold: float             # personalized threshold
    should_alert: bool                 # probability > threshold
    lead_time_estimate: Optional[float] = None  # minutes before hypo
    supply_demand_imbalance: Optional[float] = None  # flux signal
    confidence: Optional[float] = None  # prediction confidence


# ── Clinical Decision Support ─────────────────────────────────────────

@dataclass
class ClinicalReport:
    """Complete clinical decision support output."""
    grade: GlycemicGrade
    risk_score: float                          # 0-100 composite
    tir: float                                 # time in range %
    tbr: float                                 # time below range %
    tar: float                                 # time above range %
    mean_glucose: float                        # mg/dL
    gmi: float                                 # glucose management indicator (est. A1C)
    cv: float                                  # coefficient of variation %
    basal_assessment: BasalAssessment
    cr_score: float                            # 0-100 CR effectiveness
    effective_isf: Optional[float] = None      # actual ISF from data
    profile_isf: Optional[float] = None        # configured ISF
    isf_discrepancy: Optional[float] = None    # ratio effective/profile
    recommendations: List[str] = field(default_factory=list)
    overnight_tir: Optional[float] = None      # nighttime TIR for basal


# ── Pattern Analysis ──────────────────────────────────────────────────

@dataclass
class CircadianFit:
    """3-parameter circadian model: a·sin(2πh/24) + b·cos(2πh/24) + c."""
    a: float       # sin coefficient
    b: float       # cos coefficient
    c: float       # offset
    amplitude: float  # sqrt(a² + b²)
    phase_hours: float  # peak hour
    r2_improvement: Optional[float] = None  # R² gain from correction


@dataclass
class PatternProfile:
    """Temporal pattern analysis output."""
    circadian: CircadianFit
    changepoints: List[int]                # indices of detected changepoints
    n_changepoints: int
    isf_variation_pct: float               # % ISF varies across day
    isf_by_hour: Optional[np.ndarray] = None  # (24,) per-hour ISF estimates
    weekly_trend: str = "stable"           # "improving" / "declining" / "stable"
    phenotype: Phenotype = Phenotype.STABLE
    tir_first_half: Optional[float] = None
    tir_second_half: Optional[float] = None


# ── Patient Onboarding ────────────────────────────────────────────────

@dataclass
class OnboardingState:
    """Cold start / warm start calibration state."""
    phase: OnboardingPhase
    days_of_data: float
    model_r2: Optional[float] = None
    using_population_defaults: bool = True
    population_params: Optional[Dict] = None  # universal physics parameters
    personal_params: Optional[Dict] = None    # per-patient refinements
    ready_for_production: bool = False


# ── Complete Pipeline Result ──────────────────────────────────────────

@dataclass
class PipelineResult:
    """Complete output from a single pipeline run."""
    patient_id: str
    cleaned: CleanedData
    metabolic: Optional[MetabolicState]     # None if no insulin data
    risk: Optional[RiskAssessment]          # None if insufficient features
    hypo_alert: Optional[HypoAlert]
    clinical_report: ClinicalReport
    patterns: Optional[PatternProfile]      # None if < 2 weeks data
    onboarding: OnboardingState
    pipeline_latency_ms: float
    warnings: List[str] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        """True if all pipeline stages ran successfully."""
        return (self.metabolic is not None and
                self.risk is not None and
                self.patterns is not None)
