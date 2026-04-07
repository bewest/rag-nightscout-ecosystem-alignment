"""
settings_advisor.py — Counterfactual TIR prediction for therapy changes.

Research basis: EXP-693 (basal assessment), EXP-694 (CR effectiveness),
               EXP-747 (ISF discrepancy 2.91×), EXP-574/575 (counterfactual ISF/CR)

Key innovation: uses the physics model to simulate "what if we changed
this setting?" and predicts the TIR improvement that would result.

The clinical prediction loop:
  1. Detect settings mismatch (basal drift, ISF discrepancy, poor CR score)
  2. Simulate glucose trajectory with adjusted settings
  3. Predict TIR delta (improvement in time-in-range)
  4. State which time segments would improve and by how much

This enables confirmable predictions:
  "Increasing basal by 15% between 00:00-06:00 should improve overnight
   TIR from 62% to ~74%, confirmable within 1 week."
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np

from .types import (
    BasalAssessment, ClinicalReport, MetabolicState,
    PatientProfile, SettingsParameter, SettingsRecommendation,
)


# Physics simulation parameters
SIMULATION_STEPS = 288    # 1 day of 5-min intervals
DECAY_TARGET = 120.0      # mg/dL equilibrium
DECAY_RATE = 0.005        # per 5-min step

# Confidence thresholds
MIN_DATA_DAYS = 3.0       # Minimum data for any recommendation
HIGH_CONFIDENCE_DAYS = 14.0  # Full confidence threshold


def simulate_tir_with_settings(glucose: np.ndarray,
                               metabolic: MetabolicState,
                               hours: np.ndarray,
                               isf_multiplier: float = 1.0,
                               cr_multiplier: float = 1.0,
                               basal_multiplier: float = 1.0,
                               hour_range: Optional[Tuple[float, float]] = None,
                               ) -> Tuple[float, float]:
    """Simulate TIR under modified settings using physics forward model.

    Uses the metabolic flux decomposition to predict how glucose would
    behave if insulin delivery (demand) or carb sensitivity (supply)
    were different.

    Physics: dBG/dt ≈ supply/cr_mult - demand×isf_mult×basal_mult + decay

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

    # Simulate modified glucose trajectory
    sim_bg = np.zeros(N)
    sim_bg[0] = bg[0]

    for t in range(1, N):
        s = supply[t - 1]
        d = demand[t - 1]

        if mask[t]:
            # Apply modified settings
            # CR decrease → more insulin per carb → more demand
            effective_supply = s
            effective_demand = d * isf_multiplier * basal_multiplier / max(cr_multiplier, 0.1)
        else:
            effective_supply = s
            effective_demand = d

        decay = (DECAY_TARGET - sim_bg[t - 1]) * DECAY_RATE
        sim_bg[t] = sim_bg[t - 1] + effective_supply - effective_demand + decay
        # Clamp to physiological range
        sim_bg[t] = np.clip(sim_bg[t], 40.0, 400.0)

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

    isf_vals = [e.get('value', e.get('sensitivity', 50)) for e in profile.isf_schedule]
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


def generate_settings_advice(glucose: np.ndarray,
                             metabolic: Optional[MetabolicState],
                             hours: np.ndarray,
                             clinical: ClinicalReport,
                             profile: PatientProfile,
                             days_of_data: float,
                             ) -> List[SettingsRecommendation]:
    """Generate all applicable settings recommendations.

    This is the primary API. Returns a list of recommendations
    sorted by predicted TIR impact (highest first).

    Args:
        glucose: (N,) cleaned glucose.
        metabolic: MetabolicState (required for basal/CR simulation).
        hours: (N,) fractional hours.
        clinical: ClinicalReport from clinical_rules.
        profile: current therapy profile.
        days_of_data: data coverage.

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

    # Sort by predicted impact
    recs.sort(key=lambda r: abs(r.predicted_tir_delta), reverse=True)
    return recs
