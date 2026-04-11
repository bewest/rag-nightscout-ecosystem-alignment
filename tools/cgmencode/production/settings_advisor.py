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
                             ) -> List[SettingsRecommendation]:
    """Generate all applicable settings recommendations.

    This is the primary API. Returns a list of recommendations
    sorted by predicted TIR impact (highest first).

    Integrates:
    - Basal assessment (EXP-693)
    - CR effectiveness (EXP-694)
    - ISF discrepancy (EXP-747)
    - Circadian ISF 2-zone (EXP-2271)
    - Context-aware CR by time of day (EXP-2341)

    Args:
        glucose: (N,) cleaned glucose.
        metabolic: MetabolicState (required for basal/CR simulation).
        hours: (N,) fractional hours.
        clinical: ClinicalReport from clinical_rules.
        profile: current therapy profile.
        days_of_data: data coverage.
        carbs: (N,) optional carb data for context-aware CR.

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

    # Circadian ISF: 2-zone day/night split (EXP-2271)
    circadian_isf_recs = advise_circadian_isf(
        glucose, metabolic, hours, profile, days_of_data)
    recs.extend(circadian_isf_recs)

    # Context-aware CR by time of day (EXP-2341)
    if carbs is not None:
        context_cr_recs = advise_context_cr(
            glucose, metabolic, hours, profile, carbs, days_of_data)
        recs.extend(context_cr_recs)

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
