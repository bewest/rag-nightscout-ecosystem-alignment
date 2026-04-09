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
    """ADA consensus grade — used as safety floor only.

    Production note: FidelityGrade is the PRIMARY therapy quality metric.
    GlycemicGrade is retained as a safety baseline (EXP-1531: only 36%
    concordance between fidelity and ADA grading).
    """
    A = "A"  # TIR >= 70%, TBR < 4%
    B = "B"  # TIR >= 60%, TBR < 5%
    C = "C"  # TIR >= 50%
    D = "D"  # Below all thresholds


class FidelityGrade(str, Enum):
    """Physics-model fidelity grade (EXP-1531–1538).

    Measures how well therapy settings match the physics of glucose
    dynamics, independent of patient outcomes. A patient can have
    excellent fidelity (well-tuned settings) but choose to prioritize
    quality of life over tight control.

    Thresholds calibrated from 11-patient population:
      Excellent: RMSE ≤ 6 mg/dL AND correction_energy ≤ 600
      Good:      RMSE ≤ 9 AND CE ≤ 1000
      Acceptable: RMSE ≤ 11 AND CE ≤ 1600
      Poor:      Above all thresholds
    """
    EXCELLENT = "excellent"
    GOOD = "good"
    ACCEPTABLE = "acceptable"
    POOR = "poor"


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


class MealWindow(str, Enum):
    BREAKFAST = "breakfast"  # 05:00-10:00
    LUNCH = "lunch"          # 10:00-14:00
    DINNER = "dinner"        # 17:00-21:00
    SNACK = "snack"          # any other time


class SettingsParameter(str, Enum):
    BASAL_RATE = "basal_rate"
    ISF = "isf"
    CR = "cr"


class ConfidenceGrade(str, Enum):
    """Recommendation confidence grade based on bootstrap CI width (EXP-1621–1628).

    Research findings:
    - ISF: CI width 46% median (irreducible floor ~30%); grades calibrated to ISF scale
    - CR: CI width 5% (10× tighter); grades calibrated to CR scale
    - 8/10 patients LOO-robust

    Grade thresholds for ISF CI width:
      A: ≤ 30%   (narrow, highly confident)
      B: ≤ 46%   (population median)
      C: ≤ 60%   (wide, moderate confidence)
      D: > 60%   (very wide, low confidence)

    Grade thresholds for CR CI width:
      A: ≤ 5%    (narrow)
      B: ≤ 10%   (typical)
      C: ≤ 15%   (wide)
      D: > 15%   (very wide)
    """
    A = "A"  # High confidence
    B = "B"  # Moderate confidence
    C = "C"  # Low confidence
    D = "D"  # Very low confidence


class MealResponseType(str, Enum):
    """Postprandial glucose response classification (EXP-514)."""
    FLAT = "flat"           # AID suppresses excursion (<20 mg/dL)
    FAST = "fast"           # Quick absorbers, peak <60min, low tail
    BIPHASIC = "biphasic"   # Classic meal + second phase
    SLOW = "slow"           # Fat/protein, peak >90min or high tail
    MODERATE = "moderate"   # Standard absorption


class MealArchetype(str, Enum):
    """Meal-response cluster archetype (EXP-1591–1598).

    Research finding: 5,369 meals → 2 robust archetypes.
    Timing explains 9× more variance than dose.
    Clusters transfer perfectly across patients (ARI=0.976).
    """
    CONTROLLED_RISE = "controlled_rise"   # 53% of meals: modest excursion, good recovery
    HIGH_EXCURSION = "high_excursion"     # 47% of meals: large spike, slow return

class CompensationType(str, Enum):
    """AID compensation vs genuine under-insulinization (EXP-747)."""
    AID_COMPENSATING = "aid_compensating"         # high TAR + negative flux
    UNDER_INSULINIZED = "under_insulinized"       # high TAR + positive flux
    WELL_CONTROLLED = "well_controlled"           # good TIR
    OVER_INSULINIZED = "over_insulinized"         # high TBR + negative flux


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
    fidelity: Optional['FidelityAssessment'] = None  # physics-model fidelity


@dataclass
class FidelityAssessment:
    """Physics-model fidelity assessment (EXP-1531–1538).

    Measures how closely the physics supply-demand model predicts
    observed glucose changes. High fidelity = well-tuned settings.

    Key insight: fidelity correlates r=0.94 with RMSE but only
    r=-0.59 with TIR — fidelity measures settings quality,
    not outcomes.
    """
    fidelity_grade: FidelityGrade
    rmse: float                                # mg/dL prediction RMSE
    correction_energy: float                   # daily integral of |net_flux|
    r2: Optional[float] = None                 # R² (often negative due to UAM)
    conservation_integral: Optional[float] = None  # physics conservation check
    ada_grade: Optional[GlycemicGrade] = None  # ADA safety floor
    concordance: Optional[bool] = None         # True if fidelity matches ADA direction


# ── Pattern Analysis ──────────────────────────────────────────────────

@dataclass
class CircadianFit:
    """3-parameter circadian model: a·sin(2πh/24) + b·cos(2πh/24) + c.

    Legacy type — prefer HarmonicFit for production use.
    """
    a: float       # sin coefficient
    b: float       # cos coefficient
    c: float       # offset
    amplitude: float  # sqrt(a² + b²)
    phase_hours: float  # peak hour
    r2_improvement: Optional[float] = None  # R² gain from correction


@dataclass
class HarmonicFit:
    """Multi-frequency harmonic circadian model (EXP-1631–1638).

    Model: glucose(h) = offset + Σ_{k} A_k·sin(2πh/P_k + φ_k)
    Periods: [24, 12, 8, 6] hours.

    Research finding: 4-harmonic captures 96% of circadian variance
    (mean R²=0.959) vs 51% for single sinusoidal (EXP-1637).
    """
    amplitudes: List[float]        # [A_24, A_12, A_8, A_6]
    phases: List[float]            # [φ_24, φ_12, φ_8, φ_6] in hours
    offset: float                  # baseline glucose
    periods: List[float]           # [24, 12, 8, 6]
    r2: float                      # overall R² of harmonic fit
    r2_by_harmonic: Dict[str, float]  # {'24h': R², '12h': R², ...} cumulative
    dominant_amplitude: float      # max amplitude across harmonics
    dominant_period: float         # period with largest amplitude

    @property
    def n_harmonics(self) -> int:
        return len(self.periods)

    def predict(self, hours: np.ndarray) -> np.ndarray:
        """Predict glucose from harmonic model at given hours."""
        result = np.full(len(hours), self.offset)
        for amp, phase, period in zip(self.amplitudes, self.phases, self.periods):
            result += amp * np.sin(2.0 * np.pi * hours / period + phase * 2.0 * np.pi / period)
        return result


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
    harmonic: Optional[HarmonicFit] = None  # 4-harmonic model (preferred over circadian)


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


# ── Meal Detection & Prediction ───────────────────────────────────────

@dataclass
class DetectedMeal:
    """A single detected meal event from physics residual analysis."""
    index: int                           # index in glucose array
    timestamp_ms: float                  # Unix timestamp (ms)
    window: MealWindow                   # breakfast/lunch/dinner/snack
    estimated_carbs_g: float             # estimated carb grams from residual integral
    announced: bool                      # True if matching carb entry found
    residual_integral: float             # raw residual burst integral
    confidence: float                    # detection confidence (0-1)
    hour_of_day: float                   # fractional hour
    archetype: Optional[MealArchetype] = None  # cluster assignment (EXP-1591)


@dataclass
class MealHistory:
    """Aggregated meal detection results over a time period."""
    meals: List[DetectedMeal]
    total_detected: int
    announced_count: int
    unannounced_count: int
    unannounced_fraction: float          # EXP-748: ~46.5% of glucose rises
    meals_per_day: float
    mean_carbs_g: float                  # estimated mean meal size
    by_window: Dict[str, int]            # count per meal window


@dataclass
class MealTimingModel:
    """Learned meal timing pattern from 2+ weeks of data.

    For each meal window, stores the typical timing distribution
    (mean hour, std) and inter-meal interval statistics.
    """
    window: MealWindow
    mean_hour: float                     # average meal time (fractional hour)
    std_hour: float                      # timing variability
    frequency_per_day: float             # how often this meal occurs
    days_observed: int                   # data coverage
    last_observed_hour: Optional[float] = None


@dataclass
class MealPrediction:
    """Prediction of upcoming meal with eating-soon recommendation."""
    predicted_window: MealWindow
    predicted_hour: float                # expected meal time (fractional hour)
    minutes_until: float                 # minutes from now until predicted meal
    confidence: float                    # prediction confidence (0-1)
    recommend_eating_soon: bool          # True if 30-60 min before predicted meal
    estimated_carbs_g: float             # expected meal size from history
    timing_models: List[MealTimingModel]  # underlying per-window models
    rationale: str                       # human-readable explanation
    proactive_score: float = 0.0         # P(meal) from proactive model (no net_flux)
    reactive_score: float = 0.0          # P(meal) from reactive model (with net_flux)
    prediction_mode: str = 'gaussian'    # 'gaussian', 'proactive', 'reactive', 'dual'


# ── Settings Advisor ──────────────────────────────────────────────────

@dataclass
class SettingsRecommendation:
    """Recommendation to change a therapy setting, with predicted TIR impact."""
    parameter: SettingsParameter         # which setting to change
    direction: str                       # "increase" or "decrease"
    magnitude_pct: float                 # suggested change magnitude (%)
    current_value: float                 # current profile value
    suggested_value: float               # recommended new value
    predicted_tir_delta: float           # predicted TIR improvement (pp)
    affected_hours: Tuple[float, float]  # (start_hour, end_hour) most affected
    confidence: float                    # recommendation confidence (0-1)
    evidence: str                        # what data supports this
    rationale: str                       # human-readable explanation
    confidence_grade: Optional[ConfidenceGrade] = None  # bootstrap CI grade (EXP-1621)
    ci_width_pct: Optional[float] = None  # bootstrap CI width as %


@dataclass
class ActionRecommendation:
    """A prioritized action recommendation from the recommender engine."""
    action_type: str                     # "eating_soon", "adjust_basal", "adjust_cr", etc.
    priority: int                        # 1=highest (safety), 2=TIR, 3=convenience
    description: str                     # human-readable action
    predicted_tir_delta: float           # expected TIR improvement (pp)
    confidence: float                    # 0-1
    time_sensitive: bool                 # True if action has a deadline
    deadline_minutes: Optional[float] = None  # minutes until action should be taken
    meal_prediction: Optional[MealPrediction] = None
    settings_rec: Optional[SettingsRecommendation] = None


# ── Advanced Analytics ────────────────────────────────────────────────

@dataclass
class MealResponse:
    """Postprandial glucose response classification for a single meal (EXP-514)."""
    response_type: MealResponseType
    excursion_mg_dl: float            # peak - baseline (mg/dL)
    peak_time_min: float              # minutes to peak from meal start
    tail_ratio: float                 # late demand / early demand
    has_second_peak: bool             # biphasic indicator
    confidence: float                 # classification confidence


@dataclass
class PeriodMetrics:
    """Glycemic metrics for a specific time-of-day period."""
    name: str                         # "fasting", "morning", "afternoon", "evening"
    hour_start: float
    hour_end: float
    tir: float                        # time in range % for this period
    tbr: float
    tar: float
    mean_glucose: float
    basal_assessment: Optional[BasalAssessment] = None
    recommendation: Optional[SettingsRecommendation] = None


@dataclass
class CorrectionEnergy:
    """Daily metabolic correction effort (EXP-559: r=-0.35 with TIR)."""
    daily_scores: List[float]         # per-day correction energy
    mean_daily_score: float           # average across period
    smoothed_7d: Optional[List[float]] = None  # 7-day rolling average
    correlation_with_tir: Optional[float] = None  # r value
    interpretation: str = ""          # human-readable summary


@dataclass
class BolusTimingSafety:
    """Correction bolus spacing analysis for IOB stacking risk."""
    total_corrections: int            # number of correction boluses detected
    stacking_events: int              # corrections <4h apart
    stacking_fraction: float          # stacking_events / total_corrections
    min_interval_hours: Optional[float] = None  # shortest interval
    mean_interval_hours: Optional[float] = None
    safety_flag: bool = False         # True if stacking is concerning (>25%)
    interpretation: str = ""


@dataclass
class AIDCompensation:
    """AID compensation vs genuine under-insulinization analysis (EXP-747)."""
    compensation_type: CompensationType
    isf_ratio: Optional[float] = None       # effective/profile ISF
    mean_net_flux: float = 0.0              # signed average flux
    flux_polarity: str = "balanced"         # "negative", "positive", "balanced"
    tar: float = 0.0
    tbr: float = 0.0
    interpretation: str = ""


# ── Glucose Forecast ──────────────────────────────────────────────────

@dataclass
class ForecastResult:
    """Ensemble glucose forecast from PKGroupedEncoder (EXP-619).

    Research basis: 134K-param transformer, 5-seed ensemble, routed windows.
    Validated MAE: h30=11.1, h90=16.1, h180=18.5, h360=21.9 mg/dL.
    """
    predicted_glucose: np.ndarray       # (future_steps,) mean mg/dL
    ensemble_std: np.ndarray            # (future_steps,) std across seeds
    horizons_minutes: np.ndarray        # (future_steps,) [5, 10, ..., N*5]
    timestamps_ms: List[int]            # epoch ms for each forecast step
    ensemble_size: int                  # number of seed models loaded
    mae_expected: Dict[str, float]      # per-horizon validated MAE
    confidence: float                   # 0-1, inverse of ensemble spread
    model_window: str                   # e.g. 'w48', 'w96'
    uses_isf_norm: bool = False


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
    meal_history: Optional[MealHistory] = None       # detected meals
    meal_prediction: Optional[MealPrediction] = None  # next meal prediction
    settings_recs: Optional[List[SettingsRecommendation]] = None
    recommendations: Optional[List[ActionRecommendation]] = None
    # Advanced analytics (Phase 3)
    period_metrics: Optional[List[PeriodMetrics]] = None
    correction_energy: Optional[CorrectionEnergy] = None
    meal_responses: Optional[List[MealResponse]] = None
    bolus_safety: Optional[BolusTimingSafety] = None
    aid_compensation: Optional[AIDCompensation] = None
    forecast: Optional[ForecastResult] = None
    pipeline_latency_ms: float = 0.0
    warnings: List[str] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        """True if all pipeline stages ran successfully."""
        return (self.metabolic is not None and
                self.risk is not None and
                self.patterns is not None)
