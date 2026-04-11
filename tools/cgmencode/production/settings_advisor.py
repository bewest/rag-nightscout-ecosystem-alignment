"""
settings_advisor.py — Counterfactual TIR prediction for therapy changes.

Research basis: EXP-693 (basal assessment), EXP-694 (CR effectiveness),
               EXP-747 (ISF discrepancy 2.91×), EXP-574/575 (counterfactual ISF/CR),
               EXP-2271 (circadian ISF 4.6-9×, 2-zone captures 61-90%),
               EXP-2341 (context-aware CR: pre-BG + time + IOB, R²+0.28)

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
    BasalAssessment, ClinicalReport, MetabolicState, OptimizationPhase,
    OvernightDriftAssessment, OvernightPhenotype, LoopWorkloadReport,
    PatientProfile, SettingsParameter, SettingsRecommendation,
    PeriodMetrics, PatternProfile,
)


# Physics simulation parameters
SIMULATION_STEPS = 288    # 1 day of 5-min intervals
DECAY_TARGET = 120.0      # mg/dL equilibrium
DECAY_RATE = 0.005        # per 5-min step

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
    """Simulate TIR under modified settings using perturbation model.

    Uses a perturbation approach rather than full forward simulation to
    avoid error accumulation over long time series. The key insight is
    that changing a setting creates a per-step delta on glucose; we
    apply that delta to the ACTUAL glucose trace with exponential decay
    to account for the body's homeostatic response.

    For ISF changes: the insulin effect per step changes by (isf_mult - 1)
    For CR changes: carb absorption changes by (1/cr_mult - 1)
    For basal changes: basal insulin effect changes by (basal_mult - 1)

    The perturbation decays with a half-life of ~2 hours (24 steps)
    reflecting renal clearance and hepatic glucose production feedback.

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

    # Perturbation model: compute cumulative delta from settings change.
    # Each timestep where mask applies gets a perturbation from the
    # difference in metabolic flux. The perturbation decays exponentially
    # with half-life ~2h (homeostatic feedback).
    DECAY_HALF_LIFE_STEPS = 24  # 2 hours at 5-min intervals
    decay_factor = np.exp(-np.log(2) / DECAY_HALF_LIFE_STEPS)

    delta = np.zeros(N)
    for t in range(1, N):
        # Carry forward decayed perturbation
        delta[t] = delta[t - 1] * decay_factor

        if mask[t]:
            s = float(supply[t - 1]) if np.isfinite(supply[t - 1]) else 0.0
            d = float(demand[t - 1]) if np.isfinite(demand[t - 1]) else 0.0

            # ISF change: more sensitive → each unit of demand drops BG more
            demand_delta = d * (isf_multiplier * basal_multiplier - 1.0)
            # CR change: higher CR → less glucose rise per carb
            supply_delta = s * (1.0 / max(cr_multiplier, 0.1) - 1.0)
            # Net perturbation: supply goes up, demand goes up → BG goes down
            delta[t] += supply_delta - demand_delta

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
    - Context-aware CR by time of day (EXP-2341)
    - Overnight drift basal assessment (EXP-2371–2378)

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

    # Circadian ISF: 2-zone day/night split (EXP-2271)
    circadian_isf_recs = advise_circadian_isf(
        glucose, metabolic, hours, profile, days_of_data)
    recs.extend(circadian_isf_recs)

    # Context-aware CR by time of day (EXP-2341)
    if carbs is not None:
        context_cr_recs = advise_context_cr(
            glucose, metabolic, hours, profile, carbs, days_of_data)
        recs.extend(context_cr_recs)

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
