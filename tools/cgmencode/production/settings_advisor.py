"""
settings_advisor.py — Counterfactual TIR prediction for therapy changes.

Research basis: EXP-693 (basal assessment), EXP-694 (CR effectiveness),
               EXP-747 (ISF discrepancy 2.91×), EXP-574/575 (counterfactual ISF/CR),
               EXP-2271 (circadian ISF 4.6-9×, 2-zone captures 61-90%),
               EXP-2341 (context-aware CR: pre-BG + time + IOB, R²+0.28),
               EXP-2551 (two-component DIA + power-law ISF: MAE 0.30pp, r=0.933)

Key innovation: uses the physics model to simulate "what if we changed
this setting?" and predicts the TIR improvement that would result.

The clinical prediction loop:
  1. Detect settings mismatch (basal drift, ISF discrepancy, poor CR score)
  2. Simulate glucose trajectory with adjusted settings
  3. Predict TIR delta (improvement in time-in-range)
  4. State which time segments would improve and by how much

Simulation model (validated in EXP-2551):
  - Two-component DIA: fast decay (τ=0.8h, 63%) + persistent tail (τ=12h, 37%)
  - Power-law ISF: effective_mult = mult^(1 - β), β=0.9
  - Combined model: MAE=0.30pp, r=0.933 (vs 2.10pp/0.129 for single-decay)

This enables confirmable predictions:
  "Increasing basal by 15% between 00:00-06:00 should improve overnight
   TIR from 62% to ~74%, confirmable within 1 week."
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np

from .types import (
    BasalAssessment, ClinicalReport, MetabolicState, OptimizationPhase,
    OvernightDriftAssessment, OvernightPhenotype, LoopWorkloadReport,
    PatientProfile, SettingsParameter, SettingsRecommendation,
    PeriodMetrics, PatternProfile,
)
from .metabolic_engine import _FAST_TAU_HOURS, _PERSISTENT_FRACTION
from .forward_simulator import (
    forward_simulate as _fwd_simulate,
    TherapySettings as _TherapySettings,
    InsulinEvent as _InsulinEvent,
    CarbEvent as _CarbEvent,
)


# Physics simulation parameters
SIMULATION_STEPS = 288    # 1 day of 5-min intervals
DECAY_TARGET = 120.0      # mg/dL equilibrium
DECAY_RATE = 0.005        # per 5-min step

# Two-component DIA simulation (validated EXP-2551)
_FAST_TAU_STEPS = int(_FAST_TAU_HOURS * 12)        # 0.8h × 12 = ~10 steps
_PERSISTENT_TAU_STEPS = int(12.0 * 12)              # 12h × 12 = 144 steps
_FAST_FRACTION = 1.0 - _PERSISTENT_FRACTION          # 0.63
_POWER_LAW_BETA = 0.9                                # from EXP-2511

# Confidence thresholds
MIN_DATA_DAYS = 3.0       # Minimum data for any recommendation
HIGH_CONFIDENCE_DAYS = 14.0  # Full confidence threshold

# Period definitions for period-by-period analysis
PERIODS = [
    ("fasting",   0.0,  7.0),
    ("morning",   7.0, 12.0),
    ("afternoon", 12.0, 17.0),
    ("evening",  17.0, 24.0),
]


def simulate_tir_with_settings(glucose: np.ndarray,
                               metabolic: MetabolicState,
                               hours: np.ndarray,
                               isf_multiplier: float = 1.0,
                               cr_multiplier: float = 1.0,
                               basal_multiplier: float = 1.0,
                               hour_range: Optional[Tuple[float, float]] = None,
                               ) -> Tuple[float, float]:
    """Simulate TIR under modified settings using two-component DIA model.

    Uses a perturbation approach rather than full forward simulation to
    avoid error accumulation over long time series. The settings change
    creates a per-step delta that propagates through two decay channels:

    1. Fast component (63%): τ=0.8h — captures immediate insulin action
    2. Persistent component (37%): τ=12h — captures IOB underestimation
       and loop basal compensation (validated EXP-2525/2534)

    Power-law ISF dampening (β=0.9 from EXP-2511) prevents overestimating
    large ISF corrections. Without this, the persistent tail overamplifies
    perturbations (Model B MAE=3.23pp vs Model C MAE=0.30pp in EXP-2551).

    Args:
        glucose: (N,) current glucose trajectory.
        metabolic: current MetabolicState.
        hours: (N,) fractional hours.
        isf_multiplier: scale ISF by this factor (>1 = more sensitive).
        cr_multiplier: scale CR by this factor (>1 = less carb impact).
        basal_multiplier: scale basal demand (>1 = more insulin).
        hour_range: if set, only modify settings in this time window.

    Returns:
        (tir_current, tir_simulated) — both as fractions 0-1.
    """
    N = len(glucose)
    bg = np.nan_to_num(glucose.astype(np.float64), nan=120.0)
    supply = metabolic.supply
    demand = metabolic.demand

    # Hour mask for targeted changes
    if hour_range is not None:
        h_start, h_end = hour_range
        if h_start <= h_end:
            mask = (hours >= h_start) & (hours < h_end)
        else:  # wraps midnight (e.g., 22:00-06:00)
            mask = (hours >= h_start) | (hours < h_end)
    else:
        mask = np.ones(N, dtype=bool)

    # Two-component decay factors
    fast_decay = np.exp(-1.0 / max(_FAST_TAU_STEPS, 1))
    persistent_decay = np.exp(-1.0 / _PERSISTENT_TAU_STEPS)

    # Power-law ISF dampening: effective_mult = mult^(1 - β)
    if isf_multiplier > 0:
        effective_isf_mult = isf_multiplier ** (1.0 - _POWER_LAW_BETA)
    else:
        effective_isf_mult = 1.0

    delta_fast = np.zeros(N)
    delta_persistent = np.zeros(N)

    for t in range(1, N):
        delta_fast[t] = delta_fast[t - 1] * fast_decay
        delta_persistent[t] = delta_persistent[t - 1] * persistent_decay

        if mask[t]:
            s = float(supply[t - 1]) if np.isfinite(supply[t - 1]) else 0.0
            d = float(demand[t - 1]) if np.isfinite(demand[t - 1]) else 0.0

            # ISF change with power-law dampening
            demand_delta = d * (effective_isf_mult * basal_multiplier - 1.0)
            # CR change: higher CR → less glucose rise per carb
            supply_delta = s * (1.0 / max(cr_multiplier, 0.1) - 1.0)
            # Net perturbation split into two channels
            step_pert = supply_delta - demand_delta
            delta_fast[t] += step_pert * _FAST_FRACTION
            delta_persistent[t] += step_pert * _PERSISTENT_FRACTION

    # Combined perturbation
    delta = delta_fast + delta_persistent

    # Apply perturbation to actual glucose
    sim_bg = np.clip(bg + delta, 40.0, 400.0)

    # Compute TIR for both
    valid_orig = bg[np.isfinite(bg)]
    valid_sim = sim_bg[np.isfinite(sim_bg)]

    tir_current = float(np.mean((valid_orig >= 70) & (valid_orig <= 180)))
    tir_simulated = float(np.mean((valid_sim >= 70) & (valid_sim <= 180)))

    return tir_current, tir_simulated


def advise_basal(glucose: np.ndarray,
                 metabolic: MetabolicState,
                 hours: np.ndarray,
                 clinical: ClinicalReport,
                 profile: PatientProfile,
                 days_of_data: float) -> Optional[SettingsRecommendation]:
    """Generate basal rate recommendation with predicted TIR impact.

    Uses overnight (00:00-06:00) glucose drift to assess basal adequacy,
    then simulates TIR with adjusted basal.

    Args:
        glucose: (N,) cleaned glucose.
        metabolic: MetabolicState from metabolic engine.
        hours: (N,) fractional hours.
        clinical: ClinicalReport with basal_assessment.
        profile: current therapy profile.
        days_of_data: data coverage for confidence.

    Returns:
        SettingsRecommendation or None if basal is appropriate.
    """
    if clinical.basal_assessment == BasalAssessment.APPROPRIATE:
        return None

    if days_of_data < MIN_DATA_DAYS:
        return None

    # Determine direction and magnitude
    if clinical.basal_assessment == BasalAssessment.TOO_LOW:
        direction = "increase"
        # Try 10%, 15%, 20% increases
        best_delta = 0.0
        best_mult = 1.0
        for pct in [0.10, 0.15, 0.20]:
            mult = 1.0 + pct
            tir_now, tir_sim = simulate_tir_with_settings(
                glucose, metabolic, hours,
                basal_multiplier=mult, hour_range=(0.0, 6.0))
            delta = tir_sim - tir_now
            if delta > best_delta:
                best_delta = delta
                best_mult = mult
        magnitude = (best_mult - 1.0) * 100
    elif clinical.basal_assessment == BasalAssessment.TOO_HIGH:
        direction = "decrease"
        best_delta = 0.0
        best_mult = 1.0
        for pct in [0.10, 0.15, 0.20]:
            mult = 1.0 - pct
            tir_now, tir_sim = simulate_tir_with_settings(
                glucose, metabolic, hours,
                basal_multiplier=mult, hour_range=(0.0, 6.0))
            delta = tir_sim - tir_now
            if delta > best_delta:
                best_delta = delta
                best_mult = mult
        magnitude = (1.0 - best_mult) * 100
    else:  # SLIGHTLY_HIGH
        direction = "decrease"
        magnitude = 10.0
        best_mult = 0.90
        tir_now, tir_sim = simulate_tir_with_settings(
            glucose, metabolic, hours,
            basal_multiplier=best_mult, hour_range=(0.0, 6.0))
        best_delta = tir_sim - tir_now

    # Get current basal value
    basal_vals = [e.get('value', e.get('rate', 0.8)) for e in profile.basal_schedule]
    current_basal = float(np.median([float(v) for v in basal_vals])) if basal_vals else 0.8
    suggested = current_basal * best_mult

    confidence = min(1.0, days_of_data / HIGH_CONFIDENCE_DAYS) * 0.8
    # Boost confidence if change is well-supported
    if abs(best_delta) > 0.05:
        confidence = min(confidence + 0.15, 0.95)

    overnight_tir = clinical.overnight_tir or 0.5

    return SettingsRecommendation(
        parameter=SettingsParameter.BASAL_RATE,
        direction=direction,
        magnitude_pct=magnitude,
        current_value=current_basal,
        suggested_value=round(suggested, 2),
        predicted_tir_delta=round(best_delta * 100, 1),  # percentage points
        affected_hours=(0.0, 6.0),
        confidence=confidence,
        evidence=(f"Overnight TIR currently {overnight_tir*100:.0f}%. "
                  f"Basal assessed as {clinical.basal_assessment.value}. "
                  f"Simulation predicts {best_delta*100:+.1f}pp TIR improvement."),
        rationale=(f"{direction.capitalize()} basal by {magnitude:.0f}% "
                   f"(from {current_basal:.2f} to {suggested:.2f} U/hr) "
                   f"between 00:00-06:00. Predicted to improve overnight "
                   f"TIR by {best_delta*100:+.1f} percentage points. "
                   f"Confirmable within 1 week of data."),
    )


def advise_cr(glucose: np.ndarray,
              metabolic: MetabolicState,
              hours: np.ndarray,
              clinical: ClinicalReport,
              profile: PatientProfile,
              days_of_data: float) -> Optional[SettingsRecommendation]:
    """Generate CR recommendation with predicted TIR impact.

    Uses CR effectiveness score and post-meal excursion analysis.
    """
    if days_of_data < MIN_DATA_DAYS:
        return None

    if clinical.cr_score >= 40:  # Acceptable CR
        return None

    cr_vals = [e.get('value', e.get('carbratio', 10)) for e in profile.cr_schedule]
    current_cr = float(np.median([float(v) for v in cr_vals])) if cr_vals else 10.0

    # Low CR score = post-meal spikes too high → decrease CR (more insulin per carb)
    direction = "decrease"

    best_delta = 0.0
    best_mult = 1.0
    for pct in [0.10, 0.15, 0.20]:
        mult = 1.0 - pct  # Lower CR = more aggressive dosing
        tir_now, tir_sim = simulate_tir_with_settings(
            glucose, metabolic, hours,
            cr_multiplier=mult, hour_range=(5.0, 21.0))  # Meal hours
        delta = tir_sim - tir_now
        if delta > best_delta:
            best_delta = delta
            best_mult = mult

    magnitude = (1.0 - best_mult) * 100
    if magnitude < 1.0:  # No meaningful change found
        return None
    suggested = current_cr * best_mult
    confidence = min(1.0, days_of_data / HIGH_CONFIDENCE_DAYS) * 0.7

    return SettingsRecommendation(
        parameter=SettingsParameter.CR,
        direction=direction,
        magnitude_pct=magnitude,
        current_value=current_cr,
        suggested_value=round(suggested, 1),
        predicted_tir_delta=round(best_delta * 100, 1),
        affected_hours=(5.0, 21.0),
        confidence=confidence,
        evidence=(f"CR effectiveness score is {clinical.cr_score:.0f}/100 (poor). "
                  f"Post-meal excursions indicate under-dosing."),
        rationale=(f"Decrease carb ratio by {magnitude:.0f}% "
                   f"(from {current_cr:.1f} to {suggested:.1f} g/U). "
                   f"Should reduce post-meal excursions. "
                   f"Predicted TIR improvement: {best_delta*100:+.1f}pp. "
                   f"Confirmable within 2 weeks."),
    )


def advise_isf(clinical: ClinicalReport,
               profile: PatientProfile,
               days_of_data: float) -> Optional[SettingsRecommendation]:
    """Generate ISF recommendation based on discrepancy analysis.

    Research finding: effective ISF is 2.91× profile ISF on average (EXP-747).
    Large discrepancies indicate the AID is compensating for wrong settings.
    """
    if days_of_data < MIN_DATA_DAYS:
        return None

    if clinical.isf_discrepancy is None or clinical.isf_discrepancy < 1.5:
        return None  # Discrepancy not significant

    isf_vals = [e.get('value', e.get('sensitivity', 50)) for e in profile.isf_mgdl()]
    current_isf = float(np.median([float(v) for v in isf_vals])) if isf_vals else 50.0
    effective = clinical.effective_isf or current_isf

    # Conservative recommendation: move ISF toward effective ISF by 25%
    gap = effective - current_isf
    adjustment_pct = 25.0
    suggested = current_isf + gap * (adjustment_pct / 100.0)

    # Predicted TIR impact: reducing AID compensation should smooth control
    # Conservative estimate: each 10% ISF correction → ~2pp TIR gain
    predicted_delta = min(5.0, abs(gap / current_isf) * 20.0)

    confidence = min(0.7, days_of_data / HIGH_CONFIDENCE_DAYS)

    return SettingsRecommendation(
        parameter=SettingsParameter.ISF,
        direction="increase" if gap > 0 else "decrease",
        magnitude_pct=adjustment_pct,
        current_value=current_isf,
        suggested_value=round(suggested, 0),
        predicted_tir_delta=round(predicted_delta, 1),
        affected_hours=(0.0, 24.0),
        confidence=confidence,
        evidence=(f"Effective ISF is {clinical.isf_discrepancy:.1f}× profile ISF "
                  f"({effective:.0f} vs {current_isf:.0f} mg/dL/U). "
                  f"AID compensating for settings mismatch."),
        rationale=(f"Adjust ISF by {adjustment_pct:.0f}% toward observed effective "
                   f"value (from {current_isf:.0f} to {suggested:.0f} mg/dL/U). "
                   f"This reduces AID over-compensation and may smooth control. "
                   f"Predicted TIR improvement: +{predicted_delta:.1f}pp. "
                   f"Confirmable within 2 weeks of stable use."),
    )


# ── ISF Non-Linearity Advisory (EXP-2511–2518) ──────────────────────

# Population power-law exponent: ISF(dose) = ISF_base × dose^(-β)
# β = 0.899 means a 2U correction is 46% less effective per unit than 1U.
# 17/17 patients show improved prediction with power-law ISF (+53% MAE).
_POPULATION_ISF_BETA = 0.9
_ISF_NONLINEARITY_DOSE_THRESHOLD = 1.5  # warn when typical correction > this


def advise_isf_nonlinearity(
    clinical: ClinicalReport,
    profile: PatientProfile,
    bolus: Optional[np.ndarray] = None,
    days_of_data: float = 0.0,
) -> Optional[SettingsRecommendation]:
    """Generate advisory when correction doses show diminishing returns.

    Research: EXP-2511–2518. ISF follows power-law ISF(dose) = ISF_base × dose^(-β)
    with population β = 0.9. This means larger corrections are progressively less
    effective per unit of insulin. A 2U correction achieves only ~1.07× the glucose
    drop of a 1U correction (2^0.1 ≈ 1.07), not 2×.

    The advisory fires when:
    - There is enough data (>= MIN_DATA_DAYS)
    - The patient's typical correction dose exceeds 1.5U

    If no bolus data is available, falls back to estimating typical correction
    from ISF and glucose excursion patterns.
    """
    if days_of_data < MIN_DATA_DAYS:
        return None

    # Estimate typical correction dose
    typical_dose = _estimate_typical_correction_dose(
        clinical, profile, bolus)

    if typical_dose is None or typical_dose <= _ISF_NONLINEARITY_DOSE_THRESHOLD:
        return None

    beta = _POPULATION_ISF_BETA

    # Compute the effectiveness penalty
    # At dose=1, ISF = ISF_base. At dose=d, ISF = ISF_base * d^(-β)
    # Per-unit effectiveness at dose d relative to 1U: d^(-β)
    effectiveness_at_typical = typical_dose ** (-beta)
    penalty_pct = (1.0 - effectiveness_at_typical) * 100.0

    # What split-dose would achieve: 2 × half-dose corrections
    half_dose = typical_dose / 2.0
    # Total drop single: ISF_base * typical^(1-β)
    # Total drop split:  2 * ISF_base * half^(1-β)
    # Ratio: 2 * (half/typical)^(1-β) = 2 * 0.5^(1-β)
    split_ratio = 2.0 * (0.5 ** (1.0 - beta))
    split_improvement_pct = (split_ratio - 1.0) * 100.0

    isf_vals = [e.get('value', e.get('sensitivity', 50))
                for e in profile.isf_mgdl()]
    current_isf = (float(np.median([float(v) for v in isf_vals]))
                   if isf_vals else 50.0)

    # ISF at the typical dose vs at 1U
    isf_at_1u = current_isf  # profile ISF is calibrated at ~1U scale
    isf_at_typical = isf_at_1u * effectiveness_at_typical

    return SettingsRecommendation(
        parameter=SettingsParameter.ISF,
        direction="decrease",
        magnitude_pct=round(penalty_pct, 0),
        current_value=current_isf,
        suggested_value=round(isf_at_typical, 0),
        predicted_tir_delta=round(split_improvement_pct * 0.3, 1),
        affected_hours=(0.0, 24.0),
        confidence=min(0.6, days_of_data / HIGH_CONFIDENCE_DAYS),
        evidence=(
            f"ISF non-linearity (EXP-2511): typical correction dose "
            f"{typical_dose:.1f}U is {penalty_pct:.0f}% less effective "
            f"per unit than 1U (power-law β={beta}). "
            f"Splitting into 2×{half_dose:.1f}U would be "
            f"~{split_improvement_pct:.0f}% more effective total."
        ),
        rationale=(
            f"Correction doses above {_ISF_NONLINEARITY_DOSE_THRESHOLD}U "
            f"show diminishing returns. At {typical_dose:.1f}U, each unit "
            f"achieves only {isf_at_typical:.0f} mg/dL drop vs "
            f"{isf_at_1u:.0f} mg/dL at 1U. Consider: (1) splitting large "
            f"corrections into smaller doses spaced 30+ min apart, "
            f"(2) using ISF={isf_at_typical:.0f} for doses ≥{typical_dose:.0f}U. "
            f"This is a pharmacokinetic property (β={beta}), not circadian."
        ),
    )


def _estimate_typical_correction_dose(
    clinical: ClinicalReport,
    profile: PatientProfile,
    bolus: Optional[np.ndarray] = None,
) -> Optional[float]:
    """Estimate the typical correction bolus dose for this patient.

    Uses bolus data if available, otherwise estimates from ISF and
    typical glucose excursions above target.
    """
    if bolus is not None:
        # Filter to correction-sized boluses (> 0.3U, < 10U)
        corrections = bolus[(bolus > 0.3) & (bolus < 10.0)]
        if len(corrections) >= 5:
            return float(np.median(corrections))

    # Fallback: estimate from ISF and typical high-glucose excursion
    isf_vals = [e.get('value', e.get('sensitivity', 50))
                for e in profile.isf_mgdl()]
    if not isf_vals:
        return None

    current_isf = float(np.median([float(v) for v in isf_vals]))
    if current_isf <= 0:
        return None

    # Typical correction: (mean glucose - target) / ISF
    target = profile.target_range[1] if hasattr(profile, 'target_range') else 120.0
    mean_glucose = getattr(clinical, 'mean_glucose', None)
    if mean_glucose is None:
        return None

    excursion = max(0.0, mean_glucose - target)
    if excursion < 10.0:
        return None

    return excursion / current_isf


# ── Correction Threshold Advisory (EXP-2528) ─────────────────────────

# Population optimal correction threshold: corrections below this BG
# level produce net harm (rebound + hypo risk exceeds glucose-lowering
# benefit). Per-patient thresholds range 130-290 mg/dL.
_POPULATION_CORRECTION_THRESHOLD = 166  # mg/dL (EXP-2528 population median)
_CORRECTION_THRESHOLD_RANGE = (130, 290)  # observed per-patient range

# Net benefit scoring from EXP-2528a:
#   net_benefit = drop_4h - rebound_penalty - hypo_penalty
# Hypo penalty: 50 mg/dL equivalent per hypo event (3× glucose excursion weight)
_HYPO_PENALTY_MGDL = 50
_MIN_CORRECTION_EVENTS = 10   # minimum events for per-patient calibration
_HIGH_CONFIDENCE_EVENTS = 50  # full-confidence event count


def advise_correction_threshold(
    clinical: ClinicalReport,
    profile: PatientProfile,
    correction_events: Optional[List[dict]] = None,
    days_of_data: float = 0.0,
) -> Optional[SettingsRecommendation]:
    """Generate advisory for optimal correction threshold (EXP-2528).

    Research: EXP-2528. Corrections below a patient-specific BG threshold
    produce net harm: glucose rebounds and hypo risk exceed the glucose-
    lowering benefit. Population median threshold is 166 mg/dL; per-patient
    values range 130-290 mg/dL.

    When correction_events are provided (list of dicts with keys 'start_bg',
    'tir_change', 'rebound', 'rebound_magnitude', 'went_below_70'), the
    function computes a per-patient optimal threshold by scanning BG bins
    for the net-benefit zero-crossing.

    Falls back to population default (166 mg/dL) when insufficient data.

    Args:
        clinical: ClinicalReport from clinical_rules.
        profile: PatientProfile with current target_high.
        correction_events: optional list of correction event dicts from
            find_corrections() or equivalent.  Each dict must contain at
            minimum: 'start_bg' (float), 'tir_change' (float).
            Also used if present: 'rebound' (bool), 'rebound_magnitude'
            (float), 'went_below_70' (bool), 'drop_4h' (float).
        days_of_data: number of days of available data.

    Returns:
        SettingsRecommendation with parameter=CORRECTION_THRESHOLD, or
        None if insufficient data.
    """
    if days_of_data < MIN_DATA_DAYS:
        return None

    current_target_high = profile.target_high

    # Try per-patient calibration if enough correction events
    patient_threshold = None
    n_events = 0
    if correction_events is not None:
        n_events = len(correction_events)

    if n_events >= _MIN_CORRECTION_EVENTS:
        patient_threshold = _compute_patient_threshold(correction_events)

    if patient_threshold is not None:
        recommended = patient_threshold
        source = "per-patient"
    else:
        recommended = float(_POPULATION_CORRECTION_THRESHOLD)
        source = "population"

    # Confidence: based on event count and data days
    if n_events >= _HIGH_CONFIDENCE_EVENTS:
        confidence = min(0.9, days_of_data / HIGH_CONFIDENCE_DAYS)
    elif n_events >= _MIN_CORRECTION_EVENTS:
        confidence = min(0.7, days_of_data / HIGH_CONFIDENCE_DAYS)
    else:
        confidence = min(0.4, days_of_data / HIGH_CONFIDENCE_DAYS)

    # Only recommend if threshold differs meaningfully from current target_high
    gap = recommended - current_target_high
    if abs(gap) < 5.0:
        return None

    direction = "increase" if gap > 0 else "decrease"
    magnitude_pct = abs(gap) / max(current_target_high, 1.0) * 100.0

    # Predicted TIR delta: corrections below threshold hurt TIR
    # Conservative estimate: 0.1pp per 10 mg/dL of threshold adjustment
    predicted_delta = round(abs(gap) / 10.0 * 0.1, 1)

    return SettingsRecommendation(
        parameter=SettingsParameter.CORRECTION_THRESHOLD,
        direction=direction,
        magnitude_pct=round(magnitude_pct, 0),
        current_value=current_target_high,
        suggested_value=round(recommended, 0),
        predicted_tir_delta=predicted_delta,
        affected_hours=(0.0, 24.0),
        confidence=confidence,
        evidence=(
            f"Correction threshold analysis (EXP-2528): {source} optimal "
            f"threshold is {recommended:.0f} mg/dL. "
            f"Corrections below this level produce net harm "
            f"(rebound + hypo risk > benefit). "
            f"Based on {n_events} correction events."
        ),
        rationale=(
            f"{direction.capitalize()} correction threshold from "
            f"{current_target_high:.0f} to {recommended:.0f} mg/dL. "
            f"Corrections below {recommended:.0f} mg/dL show net-negative "
            f"outcomes: glucose rebounds and hypo risk exceed the "
            f"glucose-lowering benefit. "
            f"Per-patient thresholds range "
            f"{_CORRECTION_THRESHOLD_RANGE[0]}-"
            f"{_CORRECTION_THRESHOLD_RANGE[1]} mg/dL. "
            f"Predicted TIR improvement: +{predicted_delta}pp."
        ),
    )


def _compute_patient_threshold(
    events: List[dict],
) -> Optional[float]:
    """Compute per-patient optimal correction threshold from event data.

    Scans BG bins from 130-290 mg/dL in 10 mg/dL steps. For each bin,
    computes mean TIR change for corrections starting at or above that BG.
    The threshold is the lowest BG where mean TIR change becomes positive.

    Returns None if no clear threshold can be determined.
    """
    start_bgs = np.array([e['start_bg'] for e in events], dtype=np.float64)
    tir_changes = np.array([e['tir_change'] for e in events], dtype=np.float64)

    best_threshold = None
    best_score = -999.0

    for threshold in range(130, 300, 10):
        mask = start_bgs >= threshold
        if np.sum(mask) < _MIN_CORRECTION_EVENTS:
            continue
        score = float(np.mean(tir_changes[mask]))
        if score > best_score:
            best_score = score
            best_threshold = float(threshold)

    if best_threshold is None:
        return None

    # Clamp to observed population range
    best_threshold = float(np.clip(
        best_threshold,
        _CORRECTION_THRESHOLD_RANGE[0],
        _CORRECTION_THRESHOLD_RANGE[1],
    ))

    return best_threshold


def analyze_periods(glucose: np.ndarray,
                    metabolic: Optional[MetabolicState],
                    hours: np.ndarray,
                    clinical: ClinicalReport,
                    profile: PatientProfile,
                    days_of_data: float,
                    ) -> List[PeriodMetrics]:
    """Analyze glycemic control and basal adequacy for each time-of-day period.

    Decomposes the day into 4 periods and runs independent assessment for each:
    fasting (00-07), morning (07-12), afternoon (12-17), evening (17-24).

    Uses simulate_tir_with_settings() per-period to find optimal basal adjustments.

    Args:
        glucose: (N,) cleaned glucose.
        metabolic: MetabolicState (needed for simulation).
        hours: (N,) fractional hours.
        clinical: ClinicalReport for context.
        profile: current therapy profile.
        days_of_data: data coverage.

    Returns:
        List of PeriodMetrics, one per period.
    """
    from .clinical_rules import assess_glycemic_control, assess_basal

    periods = []
    basal_vals = [e.get('value', e.get('rate', 0.8)) for e in profile.basal_schedule]
    current_basal = float(np.median([float(v) for v in basal_vals])) if basal_vals else 0.8

    for name, h_start, h_end in PERIODS:
        if h_start < h_end:
            mask = (hours >= h_start) & (hours < h_end)
        else:
            mask = (hours >= h_start) | (hours < h_end)

        period_bg = glucose[mask]
        valid = period_bg[np.isfinite(period_bg)]
        if len(valid) < 12:
            continue

        metrics = assess_glycemic_control(valid)

        # Per-period basal assessment — use BG-only analysis (slope-based)
        # Note: metabolic flux mask would need full-length arrays, so we use
        # the simpler slope-based method for per-period assessment
        basal_assess = assess_basal(period_bg) if len(valid) >= 24 else None

        # Per-period recommendation via simulation
        rec = None
        if (metabolic is not None and days_of_data >= MIN_DATA_DAYS
                and basal_assess and basal_assess != BasalAssessment.APPROPRIATE):
            direction = "increase" if basal_assess in (BasalAssessment.TOO_LOW,) else "decrease"
            best_delta, best_mult = 0.0, 1.0
            for pct in [0.10, 0.15, 0.20]:
                mult = (1.0 + pct) if direction == "increase" else (1.0 - pct)
                tir_now, tir_sim = simulate_tir_with_settings(
                    glucose, metabolic, hours,
                    basal_multiplier=mult, hour_range=(h_start, h_end))
                delta = tir_sim - tir_now
                if delta > best_delta:
                    best_delta = delta
                    best_mult = mult

            if best_delta > 0.005:
                magnitude = abs(best_mult - 1.0) * 100
                suggested = current_basal * best_mult
                confidence = min(1.0, days_of_data / HIGH_CONFIDENCE_DAYS) * 0.75
                rec = SettingsRecommendation(
                    parameter=SettingsParameter.BASAL_RATE,
                    direction=direction,
                    magnitude_pct=magnitude,
                    current_value=current_basal,
                    suggested_value=round(suggested, 2),
                    predicted_tir_delta=round(best_delta * 100, 1),
                    affected_hours=(h_start, h_end),
                    confidence=confidence,
                    evidence=f"Period {name} ({h_start:.0f}:00-{h_end:.0f}:00): "
                             f"TIR={metrics['tir']*100:.0f}%, basal {basal_assess.value}.",
                    rationale=f"{direction.capitalize()} basal by {magnitude:.0f}% "
                              f"during {name} period ({h_start:.0f}:00-{h_end:.0f}:00). "
                              f"Predicted +{best_delta*100:.1f}pp TIR improvement.",
                )

        periods.append(PeriodMetrics(
            name=name,
            hour_start=h_start,
            hour_end=h_end,
            tir=metrics['tir'],
            tbr=metrics['tbr'],
            tar=metrics['tar'],
            mean_glucose=metrics['mean_glucose'],
            basal_assessment=basal_assess,
            recommendation=rec,
        ))

    return periods


def advise_isf_segmented(glucose: np.ndarray,
                         metabolic: Optional[MetabolicState],
                         hours: np.ndarray,
                         clinical: ClinicalReport,
                         profile: PatientProfile,
                         patterns: Optional[PatternProfile],
                         days_of_data: float,
                         ) -> List[SettingsRecommendation]:
    """Recommend time-segmented ISF when circadian variation is significant.

    Research: ISF varies 29.7% mean across time of day (EXP-765).
    When variation >50%, recommend 2-4 ISF segments for better control.

    Args:
        glucose, metabolic, hours: standard pipeline data.
        clinical: ClinicalReport with effective ISF.
        profile: current therapy profile.
        patterns: PatternProfile with isf_by_hour.
        days_of_data: data coverage.

    Returns:
        List of ISF SettingsRecommendations for time segments.
    """
    if patterns is None or patterns.isf_by_hour is None:
        return []
    if days_of_data < 7.0:
        return []
    if patterns.isf_variation_pct < 50.0:
        return []

    isf_by_hour = patterns.isf_by_hour
    isf_vals = [e.get('value', e.get('sensitivity', 50)) for e in profile.isf_mgdl()]
    current_isf = float(np.median([float(v) for v in isf_vals])) if isf_vals else 50.0

    recs = []
    # Group hours into segments where ISF is consistently above/below mean
    for name, h_start, h_end in PERIODS:
        h_range = range(int(h_start), int(h_end) if h_end <= 24 else 24)
        if not h_range:
            continue
        period_isf_mult = float(np.mean([isf_by_hour[h % 24] for h in h_range]))

        # Only recommend if this period's ISF differs >20% from average
        if abs(period_isf_mult - 1.0) < 0.20:
            continue

        suggested_isf = current_isf * period_isf_mult
        direction = "increase" if period_isf_mult > 1.0 else "decrease"
        magnitude = abs(period_isf_mult - 1.0) * 100

        # Simulate TIR impact
        if metabolic is not None:
            tir_now, tir_sim = simulate_tir_with_settings(
                glucose, metabolic, hours,
                isf_multiplier=period_isf_mult,
                hour_range=(h_start, h_end))
            predicted_delta = round((tir_sim - tir_now) * 100, 1)
        else:
            predicted_delta = round(magnitude * 0.1, 1)  # conservative estimate

        confidence = min(0.7, days_of_data / HIGH_CONFIDENCE_DAYS)

        recs.append(SettingsRecommendation(
            parameter=SettingsParameter.ISF,
            direction=direction,
            magnitude_pct=round(magnitude, 0),
            current_value=current_isf,
            suggested_value=round(suggested_isf, 0),
            predicted_tir_delta=predicted_delta,
            affected_hours=(h_start, h_end),
            confidence=confidence,
            evidence=f"ISF variation is {patterns.isf_variation_pct:.0f}% across day (EXP-765). "
                     f"Period {name}: ISF multiplier {period_isf_mult:.2f}×.",
            rationale=f"{direction.capitalize()} ISF by {magnitude:.0f}% during {name} "
                      f"({h_start:.0f}:00-{h_end:.0f}:00) from {current_isf:.0f} to "
                      f"{suggested_isf:.0f} mg/dL/U. Based on observed circadian ISF variation.",
        ))

    return recs


# ── Forward Sim Joint ISF×CR Optimization (EXP-2562/2567/2568) ────────

# Grid parameters for joint optimization
_JOINT_ISF_GRID = [0.5, 0.7, 0.9, 1.0, 1.1, 1.3, 1.5]
_JOINT_CR_GRID = [1.0, 1.4, 1.8, 2.0, 2.2, 2.5, 3.0]
_MIN_MEAL_WINDOWS = 10
_MEAL_CARB_THRESHOLD = 10.0   # grams
_MEAL_BOLUS_THRESHOLD = 0.1   # units
_SIM_DURATION_HOURS = 4.0
_SIM_WINDOW_STEPS = 48        # 4h × 12 steps/h
# EXP-2572: sim overshoots correction drops by ~22% (actual/sim = 0.78).
# Dampen ISF recommendations toward 1.0 by this factor.
_ISF_BIAS_DAMPENING = 0.78


def _extract_meal_windows_from_arrays(
    glucose: np.ndarray,
    hours: np.ndarray,
    bolus: np.ndarray,
    carbs: np.ndarray,
    iob: np.ndarray,
    profile: PatientProfile,
    max_windows: int = 50,
) -> list:
    """Extract meal windows from time-aligned arrays for forward sim.

    Finds points where carbs > threshold and bolus > threshold, then
    extracts 4-hour windows of glucose data for simulation comparison.
    """
    N = len(glucose)
    meal_mask = (carbs > _MEAL_CARB_THRESHOLD) & (bolus > _MEAL_BOLUS_THRESHOLD)
    meal_indices = np.where(meal_mask)[0]

    # Extract profile values (median across schedule entries)
    isf_vals = [e.get('value', e.get('sensitivity', 50))
                for e in profile.isf_mgdl()]
    cr_vals = [e.get('value', e.get('carbratio', 10))
               for e in profile.cr_schedule]
    basal_vals = [e.get('value', e.get('rate', 0.8))
                  for e in profile.basal_schedule]
    median_isf = float(np.median([float(v) for v in isf_vals])) if isf_vals else 50.0
    median_cr = float(np.median([float(v) for v in cr_vals])) if cr_vals else 10.0
    median_basal = float(np.median([float(v) for v in basal_vals])) if basal_vals else 0.8

    windows = []
    for idx in meal_indices:
        if idx + _SIM_WINDOW_STEPS >= N:
            continue
        window_glucose = glucose[idx:idx + _SIM_WINDOW_STEPS]
        if np.sum(np.isnan(window_glucose)) > 5:
            continue
        if np.isnan(glucose[idx]):
            continue

        windows.append({
            'g': float(glucose[idx]),
            'b': float(bolus[idx]),
            'c': float(carbs[idx]),
            'iob': float(iob[idx]) if not np.isnan(iob[idx]) else 0.0,
            'h': float(hours[idx]),
            'isf': median_isf,
            'cr': median_cr,
            'basal': median_basal,
        })
        if len(windows) >= max_windows:
            break

    return windows


def _evaluate_joint_settings(windows: list, isf_mult: float, cr_mult: float) -> Optional[float]:
    """Evaluate a single ISF×CR multiplier pair across meal windows.

    Returns mean TIR (70-180 mg/dL) as a fraction, or None if evaluation fails.
    """
    tirs = []
    for w in windows:
        try:
            s = _TherapySettings(
                isf=w['isf'] * isf_mult,
                cr=w['cr'] * cr_mult,
                basal_rate=w['basal'],
                dia_hours=5.0,
            )
            r = _fwd_simulate(
                initial_glucose=w['g'], settings=s,
                duration_hours=_SIM_DURATION_HOURS,
                start_hour=w['h'],
                bolus_events=[_InsulinEvent(0, w['b'])],
                carb_events=[_CarbEvent(0, w['c'])],
                initial_iob=w['iob'],
                noise_std=0, seed=42,
            )
            gluc = np.array(r.glucose)
            tirs.append(float(np.mean((gluc >= 70) & (gluc <= 180))))
        except Exception:
            pass
    return float(np.mean(tirs)) if tirs else None


def advise_forward_sim_optimization(
    glucose: np.ndarray,
    hours: np.ndarray,
    profile: PatientProfile,
    bolus: Optional[np.ndarray] = None,
    carbs: Optional[np.ndarray] = None,
    iob: Optional[np.ndarray] = None,
    days_of_data: float = 0.0,
) -> List[SettingsRecommendation]:
    """Generate ISF/CR recommendations using forward sim joint optimization.

    Research basis:
      - EXP-2562: Forward sim counterfactuals validated (ISF+20%→+2.1pp TIR)
      - EXP-2567: CR optimal ~2× profile (mean 2.10, median 2.00)
      - EXP-2568: Joint ISF×CR adds +8.9pp synergy vs single-axis
      - EXP-2569: Validated for DIRECTION only, NOT magnitude predictions

    Extracts meal windows from patient data, runs 7×7 joint ISF×CR grid
    search using the forward simulator, and generates directional
    recommendations for settings adjustments.

    NOTE: predicted_tir_delta values are DIRECTIONAL INDICATORS, not
    calibrated magnitude predictions. The forward sim cannot predict
    absolute TIR improvement (EXP-2569: MAE=0.409).

    Args:
        glucose: (N,) cleaned glucose at 5-min intervals.
        hours: (N,) fractional hours.
        profile: current therapy profile with ISF, CR, basal.
        bolus: (N,) bolus insulin per step.
        carbs: (N,) carb intake per step.
        iob: (N,) insulin on board per step.
        days_of_data: data coverage in days.

    Returns:
        List of SettingsRecommendation (0-2 items: ISF and/or CR).
    """
    if bolus is None or carbs is None or iob is None:
        return []
    if days_of_data < MIN_DATA_DAYS:
        return []

    windows = _extract_meal_windows_from_arrays(
        glucose, hours, bolus, carbs, iob, profile
    )
    if len(windows) < _MIN_MEAL_WINDOWS:
        return []

    # Run joint grid search
    best_tir = -1.0
    best_isf, best_cr = 1.0, 1.0
    baseline_tir = _evaluate_joint_settings(windows, 1.0, 1.0)
    if baseline_tir is None:
        return []

    for isf_m in _JOINT_ISF_GRID:
        for cr_m in _JOINT_CR_GRID:
            tir = _evaluate_joint_settings(windows, isf_m, cr_m)
            if tir is not None and tir > best_tir:
                best_tir = tir
                best_isf = isf_m
                best_cr = cr_m

    recs = []
    confidence = min(1.0, days_of_data / HIGH_CONFIDENCE_DAYS) * min(1.0, len(windows) / 30)

    # ISF recommendation (if optimal differs from current)
    if abs(best_isf - 1.0) > 0.05:
        # EXP-2572: dampen ISF deviation to account for 22% sim overestimation
        dampened_isf = 1.0 + (best_isf - 1.0) * _ISF_BIAS_DAMPENING
        isf_vals = [e.get('value', e.get('sensitivity', 50))
                    for e in profile.isf_mgdl()]
        current_isf = float(np.median([float(v) for v in isf_vals])) if isf_vals else 50.0
        suggested_isf = current_isf * dampened_isf
        direction = "decrease" if dampened_isf < 1.0 else "increase"
        magnitude = abs(dampened_isf - 1.0) * 100

        # Directional delta — NOT a calibrated prediction
        isf_only_tir = _evaluate_joint_settings(windows, best_isf, 1.0)
        isf_delta = ((isf_only_tir or baseline_tir) - baseline_tir) * 100

        recs.append(SettingsRecommendation(
            parameter=SettingsParameter.ISF,
            direction=direction,
            magnitude_pct=round(magnitude, 0),
            current_value=current_isf,
            suggested_value=round(suggested_isf, 1),
            predicted_tir_delta=round(isf_delta, 1),
            affected_hours=(0.0, 24.0),
            confidence=round(confidence, 2),
            evidence=(
                f"Forward sim joint optimization (EXP-2568): optimal ISF "
                f"multiplier {best_isf:.1f}× (dampened to {dampened_isf:.2f}× "
                f"per EXP-2572 bias correction) across {len(windows)} meal "
                f"windows. Joint optimal: ISF×{best_isf}, CR×{best_cr}."
            ),
            rationale=(
                f"{direction.capitalize()} ISF by {magnitude:.0f}% "
                f"(from {current_isf:.0f} to {suggested_isf:.0f} mg/dL/U). "
                f"Forward sim analysis of meal responses suggests corrections "
                f"are {'too aggressive' if dampened_isf < 1.0 else 'too weak'} "
                f"at current settings. Recommendation dampened for sim bias."
            ),
        ))

    # CR recommendation (if optimal differs from current)
    if abs(best_cr - 1.0) > 0.05:
        cr_vals = [e.get('value', e.get('carbratio', 10))
                   for e in profile.cr_schedule]
        current_cr = float(np.median([float(v) for v in cr_vals])) if cr_vals else 10.0
        suggested_cr = current_cr * best_cr
        direction = "increase" if best_cr > 1.0 else "decrease"
        magnitude = abs(best_cr - 1.0) * 100

        cr_only_tir = _evaluate_joint_settings(windows, 1.0, best_cr)
        cr_delta = ((cr_only_tir or baseline_tir) - baseline_tir) * 100

        recs.append(SettingsRecommendation(
            parameter=SettingsParameter.CR,
            direction=direction,
            magnitude_pct=round(magnitude, 0),
            current_value=current_cr,
            suggested_value=round(suggested_cr, 1),
            predicted_tir_delta=round(cr_delta, 1),
            affected_hours=(0.0, 24.0),
            confidence=round(confidence, 2),
            evidence=(
                f"Forward sim joint optimization (EXP-2568): optimal CR "
                f"multiplier {best_cr:.1f}× across {len(windows)} meal "
                f"windows. Joint optimal: ISF×{best_isf}, CR×{best_cr}. "
                f"Population finding: effective CR ≈ 2× profile CR (EXP-2567)."
            ),
            rationale=(
                f"{direction.capitalize()} CR by {magnitude:.0f}% "
                f"(from {current_cr:.0f} to {suggested_cr:.0f} g/U). "
                f"Forward sim analysis suggests meal boluses are "
                f"{'too large' if best_cr > 1.0 else 'too small'} "
                f"relative to actual glucose response."
            ),
        ))

    return recs


# ── Correction-Based ISF Calibration (EXP-2579/2582/2585) ─────────────

# Counter-regulation model parameters
_CR_K_GRID = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 7.0]
_CORR_ISF_GRID = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.5, 2.0]
_CORR_SIM_HOURS = 2.0
_CORR_SIM_STEPS = int(_CORR_SIM_HOURS * 12)
_MIN_CORR_BOLUS = 0.5       # minimum bolus (U) to qualify as correction
_MIN_CORR_GLUCOSE = 150.0   # minimum glucose (mg/dL) for correction
_MAX_CORR_CARBS = 1.0       # maximum carbs (g) — no meals
_MIN_CORRECTIONS = 20       # minimum corrections for reliable calibration
_POPULATION_K = 1.5         # fallback when < MIN_CORRECTIONS


def _extract_correction_windows(
    glucose: np.ndarray,
    hours: np.ndarray,
    bolus: np.ndarray,
    carbs: np.ndarray,
    iob: np.ndarray,
    profile: PatientProfile,
    max_windows: int = 200,
) -> list:
    """Extract correction bolus events with 2h glucose follow-up.

    Corrections are boluses ≥0.5U at glucose ≥150 with <1g carbs.
    """
    isf_vals = [e.get('value', e.get('sensitivity', 50))
                for e in profile.isf_mgdl()]
    cr_vals = [e.get('value', e.get('carbratio', 10))
               for e in profile.cr_schedule]
    basal_vals = [e.get('value', e.get('rate', 0.8))
                  for e in profile.basal_schedule]
    median_isf = float(np.median([float(v) for v in isf_vals])) if isf_vals else 50.0
    median_cr = float(np.median([float(v) for v in cr_vals])) if cr_vals else 10.0
    median_basal = float(np.median([float(v) for v in basal_vals])) if basal_vals else 0.8

    N = len(glucose)
    windows = []
    for i in range(N - _CORR_SIM_STEPS):
        if bolus[i] < _MIN_CORR_BOLUS or glucose[i] < _MIN_CORR_GLUCOSE:
            continue
        if carbs[i] > _MAX_CORR_CARBS:
            continue
        if np.isnan(glucose[i]):
            continue
        wg = glucose[i : i + _CORR_SIM_STEPS]
        valid_count = np.sum(~np.isnan(wg))
        if valid_count < _CORR_SIM_STEPS * 0.6:
            continue
        actual_end = float(np.nanmean(wg[-3:]))
        if np.isnan(actual_end):
            continue
        actual_drop = actual_end - float(glucose[i])

        windows.append({
            'g': float(glucose[i]),
            'b': float(bolus[i]),
            'iob': float(iob[i]) if not np.isnan(iob[i]) else 0.0,
            'h': float(hours[i]),
            'isf': median_isf,
            'cr': median_cr,
            'basal': median_basal,
            'actual_drop': actual_drop,
        })
        if len(windows) >= max_windows:
            break

    return windows


def _calibrate_counter_reg_k(windows: list) -> float:
    """Find optimal counter-regulation k from correction windows.

    Sweeps k values and finds the one where actual/sim drop ratio ≈ 1.0.

    Research basis: EXP-2582 (per-patient k calibration).
    """
    if len(windows) < _MIN_CORRECTIONS:
        return _POPULATION_K

    best_k = _POPULATION_K
    best_dist = float('inf')

    for k in _CR_K_GRID:
        ratios = []
        for w in windows:
            try:
                s = _TherapySettings(
                    isf=w['isf'], cr=w['cr'],
                    basal_rate=w['basal'], dia_hours=5.0,
                )
                r = _fwd_simulate(
                    initial_glucose=w['g'], settings=s,
                    duration_hours=_CORR_SIM_HOURS, start_hour=w['h'],
                    bolus_events=[_InsulinEvent(0, w['b'])],
                    carb_events=[], initial_iob=w['iob'],
                    noise_std=0, seed=42, counter_reg_k=k,
                )
                sim_drop = r.glucose[-1] - w['g']
                if abs(sim_drop) > 1.0:
                    ratios.append(w['actual_drop'] / sim_drop)
            except Exception:
                pass

        if len(ratios) >= 10:
            mean_ratio = float(np.mean(ratios))
            dist = abs(mean_ratio - 1.0)
            if dist < best_dist:
                best_dist = dist
                best_k = k

    return best_k


def _calibrate_correction_isf(windows: list, k: float) -> Optional[float]:
    """Find optimal ISF multiplier from corrections with calibrated k.

    Returns ISF multiplier that minimizes MAE between sim and actual drops.

    Research basis: EXP-2585 (correction-based ISF calibration).
    """
    if len(windows) < _MIN_CORRECTIONS:
        return None

    best_mult = 1.0
    best_mae = float('inf')

    for isf_m in _CORR_ISF_GRID:
        errors = []
        for w in windows:
            try:
                s = _TherapySettings(
                    isf=w['isf'] * isf_m, cr=w['cr'],
                    basal_rate=w['basal'], dia_hours=5.0,
                )
                r = _fwd_simulate(
                    initial_glucose=w['g'], settings=s,
                    duration_hours=_CORR_SIM_HOURS, start_hour=w['h'],
                    bolus_events=[_InsulinEvent(0, w['b'])],
                    carb_events=[], initial_iob=w['iob'],
                    noise_std=0, seed=42, counter_reg_k=k,
                )
                sim_drop = r.glucose[-1] - w['g']
                errors.append(abs(w['actual_drop'] - sim_drop))
            except Exception:
                pass

        if errors:
            mae = float(np.mean(errors))
            if mae < best_mae:
                best_mae = mae
                best_mult = isf_m

    return best_mult


def advise_correction_isf(
    glucose: np.ndarray,
    hours: np.ndarray,
    profile: PatientProfile,
    bolus: Optional[np.ndarray] = None,
    carbs: Optional[np.ndarray] = None,
    iob: Optional[np.ndarray] = None,
    days_of_data: float = 0.0,
) -> List[SettingsRecommendation]:
    """Generate ISF recommendation from correction bolus analysis.

    Research basis:
      - EXP-2579: Counter-regulation model reduces 2.5× overestimation
      - EXP-2582: Per-patient k calibration (10/11 in-range)
      - EXP-2585: Correction ISF differs from meal ISF (+0.34 higher)
      - EXP-2585: Per-patient correction-optimal beats 0.78 dampened (11/12)

    Uses a two-step calibration:
      1. Calibrate counter-regulation k from correction events
      2. With calibrated k, find optimal ISF multiplier

    This provides a correction-specific ISF recommendation that complements
    the meal-based ISF from advise_forward_sim_optimization().

    Args:
        glucose: (N,) cleaned glucose at 5-min intervals.
        hours: (N,) fractional hours.
        profile: current therapy profile.
        bolus: (N,) bolus insulin per step.
        carbs: (N,) carb intake per step.
        iob: (N,) insulin on board per step.
        days_of_data: data coverage in days.

    Returns:
        List of SettingsRecommendation (0-1 items).
    """
    if bolus is None or carbs is None or iob is None:
        return []
    if days_of_data < MIN_DATA_DAYS:
        return []

    windows = _extract_correction_windows(
        glucose, hours, bolus, carbs, iob, profile
    )
    if len(windows) < _MIN_CORRECTIONS:
        return []

    # Step 1: Calibrate counter-reg k
    k = _calibrate_counter_reg_k(windows)

    # Step 2: Find optimal ISF multiplier with calibrated k
    isf_mult = _calibrate_correction_isf(windows, k)
    if isf_mult is None or abs(isf_mult - 1.0) < 0.05:
        return []

    # Build recommendation
    isf_vals = [e.get('value', e.get('sensitivity', 50))
                for e in profile.isf_mgdl()]
    current_isf = float(np.median([float(v) for v in isf_vals])) if isf_vals else 50.0
    suggested_isf = current_isf * isf_mult
    direction = "decrease" if isf_mult < 1.0 else "increase"
    magnitude = abs(isf_mult - 1.0) * 100
    confidence = min(1.0, days_of_data / HIGH_CONFIDENCE_DAYS) * min(1.0, len(windows) / 50)

    # Estimate TIR delta (directional only)
    tir_delta = magnitude * 0.05  # conservative estimate

    return [SettingsRecommendation(
        parameter=SettingsParameter.ISF,
        direction=direction,
        magnitude_pct=round(magnitude, 0),
        current_value=current_isf,
        suggested_value=round(suggested_isf, 1),
        predicted_tir_delta=round(tir_delta, 1),
        affected_hours=(0.0, 24.0),
        confidence=round(confidence, 2),
        evidence=(
            f"Correction-based ISF calibration (EXP-2585): optimal ISF "
            f"multiplier {isf_mult:.1f}× from {len(windows)} correction events. "
            f"Counter-regulation k={k:.1f} (auto-calibrated from corrections). "
            f"Correction-specific; may differ from meal-based ISF."
        ),
        rationale=(
            f"{direction.capitalize()} ISF by {magnitude:.0f}% "
            f"(from {current_isf:.0f} to {suggested_isf:.0f} mg/dL/U). "
            f"Analysis of {len(windows)} correction boluses shows the current ISF "
            f"{'over' if isf_mult < 1.0 else 'under'}estimates correction effect. "
            f"This recommendation is based on how corrections actually work, "
            f"accounting for counter-regulatory physiology (glucagon/HGP)."
        ),
    )]


def generate_settings_advice(glucose: np.ndarray,
                             metabolic: Optional[MetabolicState],
                             hours: np.ndarray,
                             clinical: ClinicalReport,
                             profile: PatientProfile,
                             days_of_data: float,
                             carbs: Optional[np.ndarray] = None,
                             bolus: Optional[np.ndarray] = None,
                             iob: Optional[np.ndarray] = None,
                             cob: Optional[np.ndarray] = None,
                             actual_basal: Optional[np.ndarray] = None,
                             correction_events: Optional[List[dict]] = None,
                             meal_events: Optional[List[dict]] = None,
                             ) -> List[SettingsRecommendation]:
    """Generate all applicable settings recommendations.

    This is the primary API. Returns a list of recommendations
    sorted by predicted TIR impact (highest first).

    Integrates:
    - Basal assessment (EXP-693)
    - CR effectiveness (EXP-694)
    - ISF discrepancy (EXP-747)
    - ISF non-linearity warning (EXP-2511–2518)
    - Circadian ISF 2-zone (EXP-2271)
    - Circadian ISF profiled 4-block (EXP-2271)
    - Context-aware CR by time of day (EXP-2341)
    - Overnight drift basal assessment (EXP-2371–2378)
    - Correction threshold (EXP-2528)
    - CR adequacy analysis (EXP-2535/2536)
    - Forward sim joint ISF×CR optimization (EXP-2562/2567/2568)
    - Correction-based ISF calibration (EXP-2579/2582/2585)

    Args:
        glucose: (N,) cleaned glucose.
        metabolic: MetabolicState (required for basal/CR simulation).
        hours: (N,) fractional hours.
        clinical: ClinicalReport from clinical_rules.
        profile: current therapy profile.
        days_of_data: data coverage.
        carbs: (N,) optional carb data for context-aware CR.
        bolus: (N,) optional bolus data for ISF non-linearity assessment.
        iob: (N,) optional IOB for overnight clean-night filtering.
        cob: (N,) optional COB for overnight clean-night filtering.
        actual_basal: (N,) optional actual basal rate for loop workload.
        correction_events: optional list of correction event dicts for
            correction threshold analysis (EXP-2528).
        meal_events: optional list of meal event dicts for CR adequacy
            analysis (EXP-2535/2536). Each dict: carbs, bolus, pre_meal_bg,
            post_meal_bg_4h, hour.

    Returns:
        List of SettingsRecommendation, sorted by predicted_tir_delta descending.
    """
    recs = []

    # Basal assessment (requires metabolic state)
    if metabolic is not None:
        basal_rec = advise_basal(glucose, metabolic, hours, clinical, profile, days_of_data)
        if basal_rec:
            recs.append(basal_rec)

        cr_rec = advise_cr(glucose, metabolic, hours, clinical, profile, days_of_data)
        if cr_rec:
            recs.append(cr_rec)

    # ISF assessment (doesn't need metabolic, just clinical report)
    isf_rec = advise_isf(clinical, profile, days_of_data)
    if isf_rec:
        recs.append(isf_rec)

    # ISF non-linearity advisory (EXP-2511–2518)
    nonlinear_rec = advise_isf_nonlinearity(
        clinical, profile, bolus=bolus, days_of_data=days_of_data)
    if nonlinear_rec:
        recs.append(nonlinear_rec)

    # Correction threshold advisory (EXP-2528)
    threshold_rec = advise_correction_threshold(
        clinical, profile, correction_events=correction_events,
        days_of_data=days_of_data)
    if threshold_rec:
        recs.append(threshold_rec)

    # Circadian ISF: 2-zone day/night split (EXP-2271)
    circadian_isf_recs = advise_circadian_isf(
        glucose, metabolic, hours, profile, days_of_data)
    recs.extend(circadian_isf_recs)

    # Circadian ISF profiled: 4-block correction-response method (EXP-2271)
    circadian_profiled_recs = advise_circadian_isf_profiled(
        correction_events=correction_events, profile=profile,
        days_of_data=days_of_data)
    recs.extend(circadian_profiled_recs)

    # Context-aware CR by time of day (EXP-2341)
    if carbs is not None:
        context_cr_recs = advise_context_cr(
            glucose, metabolic, hours, profile, carbs, days_of_data)
        recs.extend(context_cr_recs)

    # CR adequacy analysis (EXP-2535/2536)
    if meal_events is not None:
        adequacy_recs = advise_cr_adequacy(meal_events, profile)
        recs.extend(adequacy_recs)

    # Forward sim joint ISF×CR optimization (EXP-2562/2567/2568)
    if bolus is not None and carbs is not None and iob is not None:
        fwd_recs = advise_forward_sim_optimization(
            glucose, hours, profile,
            bolus=bolus, carbs=carbs, iob=iob,
            days_of_data=days_of_data)
        recs.extend(fwd_recs)

    # Correction-based ISF calibration (EXP-2579/2582/2585)
    if bolus is not None and carbs is not None and iob is not None:
        corr_isf_recs = advise_correction_isf(
            glucose, hours, profile,
            bolus=bolus, carbs=carbs, iob=iob,
            days_of_data=days_of_data)
        recs.extend(corr_isf_recs)

    # Overnight drift assessment (EXP-2371–2378)
    overnight = assess_overnight_drift(
        glucose, hours, profile, days_of_data,
        iob=iob, cob=cob, actual_basal=actual_basal)
    if overnight is not None and overnight.needs_adjustment:
        drift_direction = "increase" if overnight.drift_mg_dl_per_hour > 0 else "decrease"
        basal_vals = [e.get('value', e.get('rate', 0.8))
                      for e in profile.basal_schedule]
        current_basal = float(np.median([float(v) for v in basal_vals])) if basal_vals else 0.8
        magnitude = abs(overnight.suggested_basal_change_pct)
        suggested = current_basal * (1.0 + overnight.suggested_basal_change_pct / 100.0)

        # Simulate TIR impact if we have metabolic state
        predicted_delta = round(magnitude * 0.05, 1)  # conservative default
        if metabolic is not None and magnitude > 0:
            mult = 1.0 + overnight.suggested_basal_change_pct / 100.0
            tir_now, tir_sim = simulate_tir_with_settings(
                glucose, metabolic, hours,
                basal_multiplier=mult,
                hour_range=(_OVERNIGHT_START, _OVERNIGHT_END))
            predicted_delta = round((tir_sim - tir_now) * 100, 1)

        phenotype_str = overnight.phenotype.value.replace('_', ' ')
        dawn_note = ""
        if overnight.has_dawn_phenomenon:
            dawn_note = (f" Dawn phenomenon detected "
                         f"(+{overnight.dawn_rise_mg_dl:.0f} mg/dL after 04:00).")

        recs.append(SettingsRecommendation(
            parameter=SettingsParameter.BASAL_RATE,
            direction=drift_direction,
            magnitude_pct=round(magnitude, 0),
            current_value=current_basal,
            suggested_value=round(suggested, 2),
            predicted_tir_delta=predicted_delta,
            affected_hours=(_OVERNIGHT_START, _OVERNIGHT_END),
            confidence=overnight.confidence,
            evidence=(f"Overnight drift analysis (EXP-2371): {overnight.n_clean_nights} "
                      f"clean nights, mean drift {overnight.drift_mg_dl_per_hour:+.1f} "
                      f"mg/dL/hr. Phenotype: {phenotype_str}.{dawn_note}"),
            rationale=(f"{drift_direction.capitalize()} overnight basal by "
                       f"{magnitude:.0f}% (from {current_basal:.2f} to {suggested:.2f} "
                       f"U/hr) between 00:00-06:00. Glucose drifts "
                       f"{overnight.drift_mg_dl_per_hour:+.1f} mg/dL/hr overnight."),
        ))

    # Sort by predicted impact
    recs.sort(key=lambda r: abs(r.predicted_tir_delta), reverse=True)
    return recs


# ── Circadian ISF: 2-Zone Recommendation (EXP-2271) ─────────────────

# EXP-2271: 2-zone (day/night) captures 61-90% of circadian ISF benefit.
# ISF varies 4.6-9× within a day. Simple day/night split is optimal for
# most patients and avoids the complexity of 4+ segment schedules.
DAY_ZONE = (7.0, 22.0)
NIGHT_ZONE_START = 22.0
NIGHT_ZONE_END = 7.0


def advise_circadian_isf(glucose: np.ndarray,
                         metabolic: Optional[MetabolicState],
                         hours: np.ndarray,
                         profile: PatientProfile,
                         days_of_data: float,
                         ) -> List[SettingsRecommendation]:
    """Recommend 2-zone (day/night) ISF split based on circadian variation.

    Research: EXP-2271 shows ISF varies 4.6-9× across the day. A simple
    2-zone split captures 61-90% of the benefit of fully time-varying ISF.
    Insulin is typically MORE effective at night (lower cortisol/GH).

    The approach:
    1. Compute effective ISF for day vs night periods
    2. If ratio >1.3×, recommend splitting the ISF schedule
    3. Simulate TIR impact of the split

    Args:
        glucose: (N,) cleaned glucose.
        metabolic: MetabolicState for simulation.
        hours: (N,) fractional hours.
        profile: current therapy profile.
        days_of_data: minimum 7 days required.

    Returns:
        List of SettingsRecommendation (0-2 recs: day ISF + night ISF).
    """
    if days_of_data < 7.0 or metabolic is None:
        return []

    isf_vals = [e.get('value', e.get('sensitivity', 50)) for e in profile.isf_mgdl()]
    current_isf = float(np.median([float(v) for v in isf_vals])) if isf_vals else 50.0

    bg = np.nan_to_num(glucose.astype(np.float64), nan=120.0)

    # Compute effective ISF for day vs night via correction response
    day_mask = (hours >= DAY_ZONE[0]) & (hours < DAY_ZONE[1])
    night_mask = ~day_mask

    # Use residual-based ISF estimation: large negative residuals during
    # corrections indicate higher effective ISF
    residual = metabolic.residual
    demand = metabolic.demand

    # During high-demand periods (corrections), measure glucose response
    high_demand = demand > np.percentile(demand[demand > 0], 75) if np.any(demand > 0) else np.zeros(len(demand), dtype=bool)

    day_response = residual[day_mask & high_demand]
    night_response = residual[night_mask & high_demand]

    if len(day_response) < 20 or len(night_response) < 20:
        return []

    day_effect = float(np.abs(np.mean(day_response)))
    night_effect = float(np.abs(np.mean(night_response)))

    if day_effect < 0.01 or night_effect < 0.01:
        return []

    ratio = night_effect / day_effect

    # Only recommend split if day/night differ by >30%
    if abs(ratio - 1.0) < 0.30:
        return []

    recs = []

    # Night ISF recommendation
    if ratio > 1.0:
        # Night insulin is more effective → increase night ISF
        night_isf = current_isf * ratio
        night_magnitude = (ratio - 1.0) * 100

        tir_now, tir_sim = simulate_tir_with_settings(
            glucose, metabolic, hours,
            isf_multiplier=ratio,
            hour_range=(NIGHT_ZONE_START, NIGHT_ZONE_END))
        night_delta = round((tir_sim - tir_now) * 100, 1)

        recs.append(SettingsRecommendation(
            parameter=SettingsParameter.ISF,
            direction="increase",
            magnitude_pct=round(night_magnitude, 0),
            current_value=current_isf,
            suggested_value=round(night_isf, 0),
            predicted_tir_delta=night_delta,
            affected_hours=(NIGHT_ZONE_START, NIGHT_ZONE_END),
            confidence=min(0.7, days_of_data / HIGH_CONFIDENCE_DAYS),
            evidence=(f"Circadian ISF analysis (EXP-2271): night insulin is "
                      f"{ratio:.1f}× more effective than day. "
                      f"2-zone split captures 61-90% of benefit."),
            rationale=(f"Increase ISF from {current_isf:.0f} to {night_isf:.0f} "
                       f"mg/dL/U during nighttime (22:00-07:00). "
                       f"Insulin works more effectively at night due to lower "
                       f"cortisol and growth hormone levels."),
        ))
    else:
        # Day insulin is more effective → increase day ISF
        day_ratio = 1.0 / ratio
        day_isf = current_isf * day_ratio
        day_magnitude = (day_ratio - 1.0) * 100

        tir_now, tir_sim = simulate_tir_with_settings(
            glucose, metabolic, hours,
            isf_multiplier=day_ratio,
            hour_range=DAY_ZONE)
        day_delta = round((tir_sim - tir_now) * 100, 1)

        recs.append(SettingsRecommendation(
            parameter=SettingsParameter.ISF,
            direction="increase",
            magnitude_pct=round(day_magnitude, 0),
            current_value=current_isf,
            suggested_value=round(day_isf, 0),
            predicted_tir_delta=day_delta,
            affected_hours=DAY_ZONE,
            confidence=min(0.7, days_of_data / HIGH_CONFIDENCE_DAYS),
            evidence=(f"Circadian ISF analysis (EXP-2271): day insulin is "
                      f"{day_ratio:.1f}× more effective than night."),
            rationale=(f"Increase ISF from {current_isf:.0f} to {day_isf:.0f} "
                       f"mg/dL/U during daytime (07:00-22:00)."),
        ))

    return recs


# ── Circadian ISF Profiled: 4-Block Correction-Response (EXP-2271) ────

# EXP-2271: ISF varies 4.6-9× by time of day. This advisory uses actual
# correction events grouped into 4 time-of-day blocks to compute empirical
# per-block ISF via the response-curve method (BG drop per unit insulin).
# Complements advise_circadian_isf (2-zone residual-based) by using direct
# correction outcomes rather than metabolic residuals.

_CIRCADIAN_BLOCKS = {
    "overnight": (0, 6),
    "morning": (6, 12),
    "afternoon": (12, 18),
    "evening": (18, 24),
}
_CIRCADIAN_ISF_DEVIATION_THRESHOLD = 0.30   # 30% deviation triggers advisory
_CIRCADIAN_MIN_CORRECTIONS_PER_BLOCK = 5    # minimum events per block


def advise_circadian_isf_profiled(
    correction_events: Optional[List[dict]] = None,
    profile: Optional[PatientProfile] = None,
    days_of_data: float = 0.0,
) -> List[SettingsRecommendation]:
    """Recommend time-of-day ISF adjustments from correction event outcomes.

    Research: EXP-2271 shows ISF varies 4.6-9× across the day. This function
    uses empirical correction-response data (BG drop per unit insulin) grouped
    into 4 time-of-day blocks to detect blocks where the profile ISF is
    significantly wrong.

    Complements advise_circadian_isf() (2-zone residual method) by using
    direct correction outcomes. The two approaches may produce overlapping
    recommendations; downstream consumers should deduplicate.

    Each correction event dict must contain:
        'hour': fractional hour (0-24) when correction was given
        'drop_4h': BG drop over 4 hours (mg/dL, positive = drop)
        'dose': insulin dose (Units, > 0)

    Args:
        correction_events: list of correction event dicts.
        profile: PatientProfile for current ISF.
        days_of_data: data coverage (minimum 3 days).

    Returns:
        List of SettingsRecommendation for blocks with >30% ISF deviation.
    """
    if days_of_data < MIN_DATA_DAYS:
        return []
    if not correction_events or profile is None:
        return []

    isf_vals = [e.get('value', e.get('sensitivity', 50))
                for e in profile.isf_mgdl()]
    current_isf = (float(np.median([float(v) for v in isf_vals]))
                   if isf_vals else 50.0)

    recs: List[SettingsRecommendation] = []

    for block_name, (h_start, h_end) in _CIRCADIAN_BLOCKS.items():
        # Filter events to this block
        block_events = [
            e for e in correction_events
            if 'hour' in e and 'drop_4h' in e and 'dose' in e
            and h_start <= e['hour'] < h_end
            and e['dose'] > 0
        ]

        if len(block_events) < _CIRCADIAN_MIN_CORRECTIONS_PER_BLOCK:
            continue

        # Compute effective ISF per event: BG drop / dose
        effective_isfs = [e['drop_4h'] / e['dose'] for e in block_events]
        block_isf = float(np.median(effective_isfs))

        if block_isf <= 0 or current_isf <= 0:
            continue

        # Deviation from profile ISF
        deviation = (block_isf - current_isf) / current_isf

        if abs(deviation) < _CIRCADIAN_ISF_DEVIATION_THRESHOLD:
            continue

        direction = "increase" if deviation > 0 else "decrease"
        magnitude = abs(deviation) * 100.0
        suggested = round(block_isf, 0)

        # Confidence: scales with event count, capped by data days
        n = len(block_events)
        event_factor = min(1.0, n / 20.0)
        day_factor = min(1.0, days_of_data / HIGH_CONFIDENCE_DAYS)
        confidence = round(event_factor * day_factor * 0.75, 2)

        # Predicted TIR delta: conservative 0.1pp per 10% ISF correction
        predicted_delta = round(magnitude * 0.01, 1)

        recs.append(SettingsRecommendation(
            parameter=SettingsParameter.ISF,
            direction=direction,
            magnitude_pct=round(magnitude, 0),
            current_value=current_isf,
            suggested_value=suggested,
            predicted_tir_delta=predicted_delta,
            affected_hours=(float(h_start), float(h_end)),
            confidence=confidence,
            evidence=(
                f"Circadian ISF profiling (EXP-2271): {block_name} block "
                f"({h_start:02d}:00-{h_end:02d}:00) effective ISF is "
                f"{block_isf:.0f} mg/dL/U vs profile {current_isf:.0f} "
                f"({deviation:+.0%} deviation) from {n} correction events."
            ),
            rationale=(
                f"{direction.capitalize()} ISF from {current_isf:.0f} to "
                f"{suggested:.0f} mg/dL/U during {block_name} "
                f"({h_start:02d}:00-{h_end:02d}:00). ISF varies 4.6-9× "
                f"by time of day (EXP-2271). Observed {n} corrections in "
                f"this block with median effective ISF {block_isf:.0f} "
                f"mg/dL/U. Predicted TIR improvement: "
                f"+{predicted_delta}pp."
            ),
        ))

    return recs


# ── CR Adequacy Analysis (EXP-2535/2536) ──────────────────────────────

# EXP-2535: Effective CR = 1.47× profile CR (systematic under-dosing).
# CR nonlinearity: BG rise/gram decreases with meal size (5.50→0.59).
# Post-meal TIR drops ~11pp. 4h mean delta = +1.8 mg/dL.
# EXP-2536: CR and ISF vary independently (r=0.17). Patients under-bolused
# at all time blocks. Breakfast CR is tightest (already compensated).

_CR_ADEQUACY_MIN_MEALS = 10       # minimum meals for analysis
_CR_ADEQUACY_DEVIATION_THRESHOLD = 0.20  # 20% deviation triggers recommendation
_CR_NONLINEARITY_THRESHOLD = 2.0  # BG rise ratio between small and large meals


def advise_cr_adequacy(
    meal_events: List[dict],
    profile: PatientProfile,
) -> List[SettingsRecommendation]:
    """Analyse CR adequacy from meal-level bolus and outcome data (EXP-2535/2536).

    Complements advise_cr() (simulation-based) by using actual meal events to
    detect systematic under/over-dosing and meal-size nonlinearity.

    EXP-2535 found effective CR = 1.47× profile CR across the population,
    indicating widespread under-dosing. EXP-2536 confirmed CR and ISF vary
    independently (r=0.17) and that patients under-bolus at all time blocks.

    Each meal_event dict must contain:
        'carbs': grams of carbs (> 0)
        'bolus': insulin dose (Units, > 0)
        'pre_meal_bg': glucose before meal (mg/dL)
        'post_meal_bg_4h': glucose 4h after meal (mg/dL)
        'hour': fractional hour of day (0-24)

    Args:
        meal_events: list of meal event dicts.
        profile: PatientProfile with current CR schedule.

    Returns:
        List of SettingsRecommendation (0-2: adequacy rec + nonlinearity warning).
    """
    if not meal_events or len(meal_events) < _CR_ADEQUACY_MIN_MEALS:
        return []

    # Filter to valid events
    valid = [
        e for e in meal_events
        if all(k in e for k in ('carbs', 'bolus', 'pre_meal_bg',
                                'post_meal_bg_4h', 'hour'))
        and e['carbs'] > 0 and e['bolus'] > 0
    ]

    if len(valid) < _CR_ADEQUACY_MIN_MEALS:
        return []

    cr_vals = [e.get('value', e.get('carbratio', 10)) for e in profile.cr_schedule]
    profile_cr = float(np.median([float(v) for v in cr_vals])) if cr_vals else 10.0

    # Compute effective CR per event: carbs / bolus
    effective_crs = np.array([e['carbs'] / e['bolus'] for e in valid])
    mean_effective_cr = float(np.mean(effective_crs))

    recs: List[SettingsRecommendation] = []

    # ── Systematic deviation check ────────────────────────────────
    if profile_cr > 0:
        deviation = (mean_effective_cr - profile_cr) / profile_cr
    else:
        deviation = 0.0

    if abs(deviation) >= _CR_ADEQUACY_DEVIATION_THRESHOLD:
        # Determine direction of dosing error
        if deviation > 0:
            # Effective CR > profile CR → patients use more carbs per unit
            # → they are under-dosing (giving less insulin than profile says)
            direction = "decrease"
            dosing_pattern = "under-dosing"
        else:
            direction = "increase"
            dosing_pattern = "over-dosing"

        magnitude_pct = abs(deviation) * 100.0

        # Confidence scales with meal count
        n = len(valid)
        confidence = min(0.85, 0.3 + 0.55 * min(1.0, n / 50.0))

        # Predicted TIR delta: ~11pp post-meal TIR drop is recoverable
        # proportionally to how much of the deviation we correct
        predicted_delta = round(min(5.0, magnitude_pct * 0.1), 1)

        # Compute 4h BG deltas for evidence
        deltas = [e['post_meal_bg_4h'] - e['pre_meal_bg'] for e in valid]
        mean_delta = float(np.mean(deltas))

        recs.append(SettingsRecommendation(
            parameter=SettingsParameter.CR,
            direction=direction,
            magnitude_pct=round(magnitude_pct, 0),
            current_value=profile_cr,
            suggested_value=round(mean_effective_cr, 1),
            predicted_tir_delta=predicted_delta,
            affected_hours=(5.0, 21.0),
            confidence=confidence,
            evidence=(
                f"CR adequacy analysis (EXP-2535): effective CR is "
                f"{mean_effective_cr:.1f} g/U vs profile {profile_cr:.1f} g/U "
                f"({deviation:+.0%} deviation) from {n} meals. "
                f"Mean 4h BG delta: {mean_delta:+.1f} mg/dL. "
                f"Systematic {dosing_pattern} detected."
            ),
            rationale=(
                f"{direction.capitalize()} CR from {profile_cr:.1f} to "
                f"{mean_effective_cr:.1f} g/U to match observed dosing. "
                f"EXP-2535 found effective CR = 1.47× profile CR population-"
                f"wide. This patient shows {deviation:+.0%} deviation "
                f"({dosing_pattern}). Predicted TIR improvement: "
                f"+{predicted_delta}pp."
            ),
        ))

    # ── Meal-size nonlinearity check ──────────────────────────────
    # Split meals into small (<30g) and large (>60g) categories
    small_meals = [e for e in valid if e['carbs'] <= 30]
    large_meals = [e for e in valid if e['carbs'] >= 60]

    if len(small_meals) >= 5 and len(large_meals) >= 5:
        small_rise = float(np.mean([
            (e['post_meal_bg_4h'] - e['pre_meal_bg']) / e['carbs']
            for e in small_meals
        ]))
        large_rise = float(np.mean([
            (e['post_meal_bg_4h'] - e['pre_meal_bg']) / e['carbs']
            for e in large_meals
        ]))

        # Only check ratio when small meals actually show a positive rise
        if small_rise > 0 and large_rise >= 0:
            nonlinearity_ratio = small_rise / max(large_rise, 0.01)

            if nonlinearity_ratio >= _CR_NONLINEARITY_THRESHOLD:
                n_small = len(small_meals)
                n_large = len(large_meals)
                confidence = min(0.70, 0.2 + 0.5 * min(
                    1.0, (n_small + n_large) / 40.0))

                recs.append(SettingsRecommendation(
                    parameter=SettingsParameter.CR,
                    direction="decrease",
                    magnitude_pct=0.0,
                    current_value=profile_cr,
                    suggested_value=profile_cr,
                    predicted_tir_delta=round(min(3.0, nonlinearity_ratio * 0.5), 1),
                    affected_hours=(5.0, 21.0),
                    confidence=confidence,
                    evidence=(
                        f"CR nonlinearity (EXP-2535): BG rise/gram is "
                        f"{small_rise:.2f} mg/dL/g for small meals (≤30g, "
                        f"n={n_small}) vs {large_rise:.2f} mg/dL/g for large "
                        f"meals (≥60g, n={n_large}). Ratio: "
                        f"{nonlinearity_ratio:.1f}×."
                    ),
                    rationale=(
                        f"Meal-size nonlinearity detected: small meals produce "
                        f"{nonlinearity_ratio:.1f}× more BG rise per gram than "
                        f"large meals. A fixed CR under-doses small meals and "
                        f"may over-dose large meals. Consider meal-size-aware "
                        f"dosing or pre-bolus timing adjustments for small meals."
                    ),
                ))

    return recs


# ── Context-Aware CR (EXP-2341) ──────────────────────────────────────

# EXP-2341: Carbs explain <16% of glucose rise. Pre-meal BG is NEGATIVELY
# correlated with rise (r=-0.33 to -0.69). Multi-factor model R²=0.14-0.54
# (avg +0.277 over carbs-only).
#
# Factors: pre-meal BG, time of day, IOB at meal time
# Pre-meal BG effect: higher starting BG → smaller rise (regression to mean
# + stronger insulin response at higher BG levels)

# Coefficients from EXP-2341 population model
_CR_PRE_BG_COEFF = -0.15     # mg/dL rise per mg/dL pre-BG above 120
_CR_IOB_COEFF = -5.0          # mg/dL rise per Unit IOB at meal time
_CR_MORNING_BOOST = 1.20      # 20% more insulin needed at breakfast
_CR_EVENING_DAMPEN = 0.90     # 10% less insulin needed at dinner


def compute_context_cr_adjustment(pre_meal_bg: float,
                                  iob_at_meal: float,
                                  hour: float,
                                  base_cr: float,
                                  ) -> dict:
    """Compute context-aware CR adjustment for a specific meal context.

    Research (EXP-2341): Pre-meal BG is negatively correlated with
    post-meal rise. Higher starting BG means the same carbs produce
    a SMALLER glucose excursion. IOB at meal time also reduces rise.

    This function adjusts the base CR for the current context:
    - High pre-meal BG → less insulin needed (larger CR)
    - High IOB → less insulin needed (larger CR)
    - Morning → more insulin needed (smaller CR)

    Args:
        pre_meal_bg: current glucose before meal (mg/dL).
        iob_at_meal: current IOB (Units).
        hour: fractional hour of day.
        base_cr: base carb ratio from profile (g/U).

    Returns:
        Dict with 'adjusted_cr', 'adjustment_pct', 'factors' explaining
        each component of the adjustment.
    """
    factors = {}
    total_multiplier = 1.0

    # Pre-meal BG adjustment: higher BG → less insulin
    bg_delta = pre_meal_bg - 120.0
    if abs(bg_delta) > 10:
        bg_effect = _CR_PRE_BG_COEFF * bg_delta / 50.0  # normalized
        bg_mult = 1.0 - bg_effect
        bg_mult = max(0.7, min(1.3, bg_mult))
        total_multiplier *= bg_mult
        factors['pre_meal_bg'] = {
            'value': pre_meal_bg,
            'effect': f"{'less' if bg_mult > 1 else 'more'} insulin needed",
            'multiplier': round(bg_mult, 2),
        }

    # IOB adjustment: high IOB → less insulin needed
    if iob_at_meal > 0.5:
        iob_mult = max(0.7, 1.0 + iob_at_meal * 0.05)
        total_multiplier *= iob_mult
        factors['iob'] = {
            'value': iob_at_meal,
            'effect': f"{'less' if iob_mult > 1 else 'more'} insulin needed",
            'multiplier': round(iob_mult, 2),
        }

    # Time-of-day adjustment: morning more aggressive, evening less
    if 5.0 <= hour < 10.0:
        tod_mult = 1.0 / _CR_MORNING_BOOST  # smaller CR = more insulin
        total_multiplier *= tod_mult
        factors['time_of_day'] = {
            'period': 'morning',
            'effect': 'dawn phenomenon — more insulin needed',
            'multiplier': round(tod_mult, 2),
        }
    elif 17.0 <= hour < 21.0:
        tod_mult = 1.0 / _CR_EVENING_DAMPEN  # larger CR = less insulin
        total_multiplier *= tod_mult
        factors['time_of_day'] = {
            'period': 'evening',
            'effect': 'better insulin sensitivity — less insulin needed',
            'multiplier': round(tod_mult, 2),
        }

    adjusted_cr = base_cr * total_multiplier
    adjustment_pct = (total_multiplier - 1.0) * 100

    return {
        'adjusted_cr': round(adjusted_cr, 1),
        'base_cr': base_cr,
        'adjustment_pct': round(adjustment_pct, 1),
        'total_multiplier': round(total_multiplier, 2),
        'factors': factors,
        'interpretation': (
            f"Context-adjusted CR: {adjusted_cr:.1f} g/U "
            f"(base {base_cr:.1f}, {adjustment_pct:+.0f}%). "
            f"Pre-BG {pre_meal_bg:.0f}, IOB {iob_at_meal:.1f}U, "
            f"hour {hour:.0f}."
        ),
    }


def advise_context_cr(glucose: np.ndarray,
                      metabolic: Optional[MetabolicState],
                      hours: np.ndarray,
                      profile: PatientProfile,
                      carbs: Optional[np.ndarray] = None,
                      days_of_data: float = 0.0,
                      ) -> List[SettingsRecommendation]:
    """Recommend time-of-day CR adjustments based on context analysis.

    Research (EXP-2341): Multi-factor CR model improves R² by +0.28
    vs carbs-only. Key finding: 47-80% of meals are under-bolused
    for 8/11 patients. Morning meals need ~20% more insulin.

    Args:
        glucose: (N,) cleaned glucose.
        metabolic: MetabolicState for meal response analysis.
        hours: (N,) fractional hours.
        profile: current therapy profile.
        carbs: (N,) optional carb data for meal detection.
        days_of_data: minimum 7 days required.

    Returns:
        List of CR SettingsRecommendations by time period.
    """
    if days_of_data < 7.0 or carbs is None:
        return []

    cr_vals = [e.get('value', e.get('carbratio', 10)) for e in profile.cr_schedule]
    current_cr = float(np.median([float(v) for v in cr_vals])) if cr_vals else 10.0

    bg = np.nan_to_num(glucose.astype(np.float64), nan=120.0)
    c = np.nan_to_num(carbs.astype(np.float64), nan=0.0)

    recs = []

    # Analyze meal response by time of day
    for name, h_start, h_end in PERIODS:
        if name == "fasting":
            continue  # No meals during fasting

        mask = (hours >= h_start) & (hours < h_end)
        # Find meals in this period: carbs > 5g
        meal_indices = np.where(mask & (c > 5))[0]
        if len(meal_indices) < 5:
            continue

        # Compute post-meal excursions (2h window)
        excursions = []
        for idx in meal_indices:
            if idx + 24 >= len(bg):
                continue
            pre_bg = float(bg[idx])
            post_window = bg[idx:idx+24]
            peak = float(np.max(post_window))
            excursion = peak - pre_bg
            excursions.append(excursion)

        if not excursions:
            continue

        mean_excursion = float(np.mean(excursions))
        # Excessive excursion: >60 mg/dL mean suggests under-bolusing
        if mean_excursion < 40:
            continue

        # Recommend CR decrease (more aggressive) for this period
        # Scale by excursion severity
        cr_reduction = min(0.25, (mean_excursion - 40) / 200)
        suggested_cr = current_cr * (1.0 - cr_reduction)
        magnitude = cr_reduction * 100

        # Simulate impact
        if metabolic is not None:
            tir_now, tir_sim = simulate_tir_with_settings(
                glucose, metabolic, hours,
                cr_multiplier=(1.0 - cr_reduction),
                hour_range=(h_start, h_end))
            predicted_delta = round((tir_sim - tir_now) * 100, 1)
        else:
            predicted_delta = round(magnitude * 0.1, 1)

        recs.append(SettingsRecommendation(
            parameter=SettingsParameter.CR,
            direction="decrease",
            magnitude_pct=round(magnitude, 0),
            current_value=current_cr,
            suggested_value=round(suggested_cr, 1),
            predicted_tir_delta=predicted_delta,
            affected_hours=(h_start, h_end),
            confidence=min(0.65, days_of_data / HIGH_CONFIDENCE_DAYS),
            evidence=(f"Context-aware CR analysis (EXP-2341): {name} meals "
                      f"show mean excursion {mean_excursion:.0f} mg/dL from "
                      f"{len(meal_indices)} meals. Pre-meal BG negatively "
                      f"correlated with rise (carbs explain <16% of variance)."),
            rationale=(f"Decrease {name} CR from {current_cr:.1f} to "
                       f"{suggested_cr:.1f} g/U ({magnitude:.0f}% more insulin). "
                       f"Mean post-meal excursion is {mean_excursion:.0f} mg/dL."),
        ))

    return recs


# ── Overnight Drift Assessment (EXP-2371–2378) ───────────────────────

# Clean-night thresholds from EXP-2375: residual dinner bolus cleared
_CLEAN_NIGHT_IOB_MAX = 0.5    # Units
_CLEAN_NIGHT_COB_MAX = 5.0    # grams
_CLEAN_NIGHT_GAP_MAX = 30.0   # minutes (max gap in glucose data)
_OVERNIGHT_START = 0.0
_OVERNIGHT_END = 6.0
_DAWN_CUTOFF = 4.0            # hour when dawn phenomenon typically begins
_MIN_CLEAN_NIGHTS = 3         # minimum clean nights for assessment

# Drift thresholds (mg/dL/hr) from EXP-2372
_DRIFT_STABLE_THRESHOLD = 3.0    # ±3 mg/dL/hr = stable
_DRIFT_MODERATE_THRESHOLD = 8.0  # ±8 mg/dL/hr = moderate mismatch
_DAWN_RISE_THRESHOLD = 15.0      # mg/dL rise after 04:00 = dawn phenomenon

# Loop suspension threshold from EXP-2373
_LOOP_DEPENDENT_SUSPENSION = 40.0  # >40% suspension = loop-dependent


def assess_overnight_drift(
        glucose: np.ndarray,
        hours: np.ndarray,
        profile: PatientProfile,
        days_of_data: float,
        iob: np.ndarray = None,
        cob: np.ndarray = None,
        actual_basal: np.ndarray = None,
        ) -> Optional[OvernightDriftAssessment]:
    """Assess basal adequacy from overnight glucose drift (EXP-2371–2378).

    Uses clean overnight windows (00:00–06:00) where IOB and COB are minimal
    to measure glucose drift rate — the most reliable indicator of basal
    rate adequacy.

    Clean-night filtering is critical: residual dinner bolus IOB and late
    snack COB confound overnight glucose trends. Only nights with IOB < 0.5U
    and COB < 5g are used (EXP-2375).

    Args:
        glucose: (N,) cleaned glucose values (mg/dL).
        hours: (N,) fractional hours (0-24).
        profile: patient therapy profile for scheduled basal.
        days_of_data: total data coverage.
        iob: (N,) optional IOB for clean-night filtering.
        cob: (N,) optional COB for clean-night filtering.
        actual_basal: (N,) optional actual basal rate for loop activity.

    Returns:
        OvernightDriftAssessment or None if insufficient data.
    """
    if days_of_data < MIN_DATA_DAYS:
        return None

    bg = np.nan_to_num(glucose.astype(np.float64), nan=np.nan)
    overnight_mask = (hours >= _OVERNIGHT_START) & (hours < _OVERNIGHT_END)

    if np.sum(overnight_mask) < 12:  # need at least 1 hour
        return None

    # Identify individual overnight segments by looking for time resets
    overnight_idx = np.where(overnight_mask)[0]
    if len(overnight_idx) == 0:
        return None

    # Split into separate nights: gap > 2 hours between consecutive indices
    gaps = np.diff(overnight_idx)
    night_breaks = np.where(gaps > 24)[0]  # >2 hours gap = new night
    night_starts = [0] + (night_breaks + 1).tolist()
    night_ends = (night_breaks + 1).tolist() + [len(overnight_idx)]

    segments = []
    for s, e in zip(night_starts, night_ends):
        idx = overnight_idx[s:e]
        if len(idx) < 12:
            continue
        seg_glucose = bg[idx]
        if np.sum(np.isfinite(seg_glucose)) < 12:
            continue
        segments.append(idx)

    n_total_nights = len(segments)
    if n_total_nights == 0:
        return None

    # Filter to clean nights (IOB < 0.5, COB < 5)
    clean_segments = []
    for idx in segments:
        is_clean = True
        if iob is not None:
            seg_iob = iob[idx]
            if np.any(np.isfinite(seg_iob)) and np.nanmax(seg_iob) > _CLEAN_NIGHT_IOB_MAX:
                is_clean = False
        if cob is not None:
            seg_cob = cob[idx]
            if np.any(np.isfinite(seg_cob)) and np.nanmax(seg_cob) > _CLEAN_NIGHT_COB_MAX:
                is_clean = False
        if is_clean:
            clean_segments.append(idx)

    # If too few clean nights, fall back to all nights with reduced confidence
    use_clean = len(clean_segments) >= _MIN_CLEAN_NIGHTS
    analysis_segments = clean_segments if use_clean else segments
    n_clean = len(clean_segments)

    if len(analysis_segments) < 2:
        return None

    # Compute drift for each segment
    drifts = []
    dawn_rises = []
    overnight_means = []

    for idx in analysis_segments:
        seg_bg = bg[idx]
        seg_hours = hours[idx]
        valid = np.isfinite(seg_bg)
        if valid.sum() < 6:
            continue

        # Linear drift: slope of glucose over time
        t = seg_hours[valid]
        g = seg_bg[valid]
        if len(t) < 6:
            continue

        # Duration in hours
        duration = float(t[-1] - t[0])
        if duration < 1.0:
            continue

        # Simple linear regression for drift rate
        slope = float(np.polyfit(t, g, 1)[0])
        drifts.append(slope)
        overnight_means.append(float(np.mean(g)))

        # Dawn phenomenon: compare pre-04:00 vs post-04:00
        pre_dawn = g[t < _DAWN_CUTOFF]
        post_dawn = g[t >= _DAWN_CUTOFF]
        if len(pre_dawn) >= 3 and len(post_dawn) >= 3:
            dawn_rise = float(np.mean(post_dawn) - np.mean(pre_dawn))
            dawn_rises.append(dawn_rise)

    if not drifts:
        return None

    mean_drift = float(np.mean(drifts))
    mean_glucose = float(np.mean(overnight_means))
    mean_dawn_rise = float(np.mean(dawn_rises)) if dawn_rises else 0.0
    has_dawn = mean_dawn_rise > _DAWN_RISE_THRESHOLD

    # Loop suspension analysis
    suspension_pct = 0.0
    if actual_basal is not None:
        basal_vals = [e.get('value', e.get('rate', 0.8))
                      for e in profile.basal_schedule]
        sched_basal = float(np.median([float(v) for v in basal_vals])) if basal_vals else 0.8

        on_indices = np.concatenate(analysis_segments)
        ab = actual_basal[on_indices]
        valid_ab = np.isfinite(ab) & (ab < 50)
        if np.sum(valid_ab) > 10 and sched_basal > 0.01:
            ratio = ab[valid_ab] / sched_basal
            suspension_pct = float(100 * np.mean(ratio < 0.1))

    # Classify phenotype
    drift_abs = abs(mean_drift)
    if suspension_pct > _LOOP_DEPENDENT_SUSPENSION:
        phenotype = OvernightPhenotype.LOOP_DEPENDENT
    elif drift_abs <= _DRIFT_STABLE_THRESHOLD and not has_dawn:
        phenotype = OvernightPhenotype.STABLE_SLEEPER
    elif mean_drift > _DRIFT_STABLE_THRESHOLD and has_dawn:
        phenotype = OvernightPhenotype.DAWN_RISER
    elif mean_drift > _DRIFT_STABLE_THRESHOLD:
        phenotype = OvernightPhenotype.UNDER_BASALED
    elif mean_drift < -_DRIFT_STABLE_THRESHOLD:
        phenotype = OvernightPhenotype.OVER_BASALED
    else:
        # Check consistency: if drift varies a lot, it's mixed
        if len(drifts) >= 3 and float(np.std(drifts)) > 2 * drift_abs:
            phenotype = OvernightPhenotype.MIXED
        else:
            phenotype = OvernightPhenotype.STABLE_SLEEPER

    # Suggest basal change: aim to zero out drift
    # ~0.1 U/hr basal change → ~10 mg/dL/hr glucose effect (rough ISF-based estimate)
    basal_vals = [e.get('value', e.get('rate', 0.8))
                  for e in profile.basal_schedule]
    current_basal = float(np.median([float(v) for v in basal_vals])) if basal_vals else 0.8
    isf_vals = [e.get('value', e.get('sensitivity', 50))
                for e in profile.isf_mgdl()]
    current_isf = float(np.median([float(v) for v in isf_vals])) if isf_vals else 50.0

    # Each 0.1 U/hr change in basal → ISF/10 mg/dL/hr glucose change
    if current_isf > 0 and current_basal > 0.01:
        basal_change_per_drift = 0.1 / (current_isf / 10.0)
        needed_change = mean_drift * basal_change_per_drift
        suggested_change_pct = (needed_change / current_basal) * 100
        # Cap at ±25%
        suggested_change_pct = float(np.clip(suggested_change_pct, -25, 25))
    else:
        suggested_change_pct = 0.0

    # Confidence based on clean nights and consistency
    if use_clean:
        base_conf = min(1.0, n_clean / 10.0)
    else:
        base_conf = min(0.5, len(analysis_segments) / 10.0)
    drift_consistency = 1.0 - min(1.0, float(np.std(drifts)) / max(drift_abs, 1.0))
    confidence = float(base_conf * 0.7 + drift_consistency * 0.3)

    return OvernightDriftAssessment(
        phenotype=phenotype,
        drift_mg_dl_per_hour=round(mean_drift, 2),
        n_clean_nights=n_clean,
        n_total_nights=n_total_nights,
        mean_overnight_glucose=round(mean_glucose, 1),
        dawn_rise_mg_dl=round(mean_dawn_rise, 1),
        has_dawn_phenomenon=has_dawn,
        loop_suspension_pct=round(suspension_pct, 1),
        suggested_basal_change_pct=round(suggested_change_pct, 1),
        confidence=round(confidence, 2),
    )


# ── Loop Workload Assessment (EXP-2391–2396) ─────────────────────────

_WORKLOAD_PERIODS = {
    "overnight": (0.0, 6.0),
    "morning": (6.0, 12.0),
    "afternoon": (12.0, 18.0),
    "evening": (18.0, 24.0),
}

# Normalization: percentile-based (research finding: 0.5 threshold too aggressive)
_WORKLOAD_NORM_FACTOR = 0.7  # deviation of 0.7 = 100% workload


def compute_loop_workload(
        hours: np.ndarray,
        actual_basal: np.ndarray,
        profile: PatientProfile,
        ) -> Optional[LoopWorkloadReport]:
    """Compute loop workload metrics as settings adequacy indicator (EXP-2391–2396).

    Loop workload measures how much the AID loop deviates from scheduled basal
    rates. High workload means the loop is working hard to compensate for
    incorrect settings. Key research finding: workload vs TIR has r=-0.165
    (no correlation), confirming that the loop compensates effectively but at
    the cost of increased risk and reduced margin.

    Args:
        hours: (N,) fractional hours (0-24).
        actual_basal: (N,) actual basal rate delivered (U/hr).
        profile: patient profile with scheduled basal rates.

    Returns:
        LoopWorkloadReport or None if insufficient basal data.
    """
    if actual_basal is None:
        return None

    ab = np.asarray(actual_basal, dtype=np.float64)
    basal_vals = [e.get('value', e.get('rate', 0.8)) for e in profile.basal_schedule]
    sched_basal = float(np.median([float(v) for v in basal_vals])) if basal_vals else 0.8

    if sched_basal < 0.01:
        return None

    valid = np.isfinite(ab) & (ab < 50)  # filter implausible ODC values
    if np.sum(valid) < 100:
        return None

    ratio = ab[valid] / sched_basal
    h_valid = hours[valid]

    # Core metrics
    suspension_pct = float(100 * np.mean(ratio < 0.1))
    increase_pct = float(100 * np.mean(ratio > 1.5))
    deviation_mean = float(np.mean(np.abs(ratio - 1.0)))
    ratio_median = float(np.median(ratio))

    # Directional workload
    reduction_workload = float(np.mean(np.maximum(0, 1 - ratio)))
    increase_workload = float(np.mean(np.maximum(0, ratio - 1)))
    if abs(reduction_workload - increase_workload) < 0.02:
        net_direction = "NEUTRAL"
    elif reduction_workload > increase_workload:
        net_direction = "REDUCING"
    else:
        net_direction = "INCREASING"

    # Workload score (percentile-normalized)
    workload_score = min(100, float(100 * deviation_mean / _WORKLOAD_NORM_FACTOR))

    # Period-by-period workload
    period_workload = {}
    for name, (h_start, h_end) in _WORKLOAD_PERIODS.items():
        mask = (h_valid >= h_start) & (h_valid < h_end)
        if np.sum(mask) >= 10:
            period_dev = float(np.mean(np.abs(ratio[mask] - 1.0)))
            period_workload[name] = round(
                min(100, 100 * period_dev / _WORKLOAD_NORM_FACTOR), 1)

    # Interpretation
    if workload_score > 80:
        severity = "very high"
    elif workload_score > 50:
        severity = "high"
    elif workload_score > 25:
        severity = "moderate"
    else:
        severity = "low"

    interpretation = (
        f"Loop workload is {severity} ({workload_score:.0f}/100). "
        f"The loop is predominantly {net_direction} basal "
        f"(median ratio: {ratio_median:.2f}× scheduled). "
        f"Basal suspended {suspension_pct:.0f}% of the time, "
        f"increased >150% for {increase_pct:.0f}% of the time."
    )

    return LoopWorkloadReport(
        workload_score=round(workload_score, 1),
        net_direction=net_direction,
        suspension_pct=round(suspension_pct, 1),
        increase_pct=round(increase_pct, 1),
        deviation_mean=round(deviation_mean, 3),
        ratio_median=round(ratio_median, 2),
        n_samples=int(np.sum(valid)),
        period_workload=period_workload,
        interpretation=interpretation,
    )


# ── Optimization Sequence (EXP-1765) ─────────────────────────────────

# CV threshold that determines optimization phase
_CV_THRESHOLD = 28.0  # %


def determine_optimization_phase(glucose: np.ndarray) -> OptimizationPhase:
    """Determine which optimization phase a patient needs (EXP-1765).

    Three-phase sequence (order matters — 7/11 patients harmed by wrong order):
    1. REDUCE_VARIABILITY (CV > 28%): break cascades, reduce overnight swings
    2. CENTER (CV ≤ 28%): adjust ISF, CR, basal rates to center glucose
    3. PERSONALIZE: per-patient tuning of all parameters

    Research finding: 9/11 patients need variability reduction BEFORE centering.
    Cross-patient models always fail (LOPO R² = -0.01). Combined ceiling: +17.6% TIR.

    Args:
        glucose: (N,) glucose values (mg/dL).

    Returns:
        OptimizationPhase indicating what to focus on.
    """
    valid = glucose[np.isfinite(glucose)]
    if len(valid) < 288:  # < 1 day
        return OptimizationPhase.REDUCE_VARIABILITY

    cv = float(np.std(valid) / np.mean(valid) * 100.0)
    tir = float(np.mean((valid >= 70) & (valid <= 180)))

    if cv > _CV_THRESHOLD:
        return OptimizationPhase.REDUCE_VARIABILITY
    elif tir < 0.70:
        return OptimizationPhase.CENTER
    else:
        return OptimizationPhase.PERSONALIZE


def prioritize_recommendations(recs: List[SettingsRecommendation],
                               phase: OptimizationPhase,
                               ) -> List[SettingsRecommendation]:
    """Re-order recommendations based on optimization phase (EXP-1765).

    In REDUCE_VARIABILITY phase, prioritize basal adjustments and cascade-
    breaking changes. In CENTER phase, prioritize ISF and CR. In PERSONALIZE,
    keep impact-sorted order.

    Args:
        recs: existing recommendations sorted by predicted TIR delta.
        phase: current optimization phase.

    Returns:
        Re-prioritized recommendations list.
    """
    if not recs or phase == OptimizationPhase.PERSONALIZE:
        return recs

    phase_priority = {
        OptimizationPhase.REDUCE_VARIABILITY: {
            SettingsParameter.BASAL: 0,
            SettingsParameter.ISF: 2,
            SettingsParameter.CR: 1,
        },
        OptimizationPhase.CENTER: {
            SettingsParameter.ISF: 0,
            SettingsParameter.CR: 1,
            SettingsParameter.BASAL: 2,
        },
    }
    priority_map = phase_priority.get(phase, {})

    def sort_key(rec: SettingsRecommendation) -> Tuple[int, float]:
        p = priority_map.get(rec.parameter, 99)
        return (p, -abs(rec.predicted_tir_delta))

    return sorted(recs, key=sort_key)
