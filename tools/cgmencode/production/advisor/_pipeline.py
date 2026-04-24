"""Advisory wiring, consolidation, deduplication, safety clamp, and confidence tiers."""

from __future__ import annotations
from typing import List, Optional, Tuple
import numpy as np
from ..types import (
    ClinicalReport, MetabolicState, OptimizationPhase,
    PatientProfile, SettingsParameter, SettingsRecommendation,
    PeriodMetrics, PatternProfile,
)
from ._simulation import simulate_tir_with_settings, PERIODS, MIN_DATA_DAYS, HIGH_CONFIDENCE_DAYS
from ._isf_advisors import (
    advise_isf, advise_isf_nonlinearity, advise_isf_segmented,
    advise_forward_sim_optimization, advise_correction_isf,
    advise_correction_denominator_isf,  # Wave-12: multi-factor deconfounding
    advise_circadian_isf, advise_circadian_isf_profiled,
    advise_override_isf, advise_patience_mode,
    advise_isf_dual_phase, advise_response_curve_isf,
    advise_sc_ceiling, advise_dose_response_isf,
)
from ._cr_advisors import (
    advise_cr, advise_effective_cr, advise_cr_adequacy, advise_context_cr,
)
from ._basal_advisors import (
    advise_basal, advise_overnight_basal_quadrant,
    advise_loop_workload, assess_overnight_drift,
    advise_carb_context_overnight,
)


__all__ = [
    'MAX_SAFE_MAGNITUDE_PCT',
    '_CONFIDENCE_TIERS',
    '_CORRECTION_THRESHOLD_RANGE',
    '_CV_THRESHOLD',
    '_HIGH_CONFIDENCE_EVENTS',
    '_HYPO_PENALTY_MGDL',
    '_MIN_CORRECTION_EVENTS',
    '_POPULATION_CORRECTION_THRESHOLD',
    '_compute_patient_threshold',
    '_consolidate_recommendations',
    '_deduplicate_same_direction',
    'advise_correction_threshold',
    'analyze_periods',
    'apply_confidence_tier_to_recommendations',
    'apply_safety_clamp',
    'compute_advisory_confidence_tier',
    'compute_settings_quality_score',
    'determine_optimization_phase',
    'generate_settings_advice',
    'prioritize_recommendations',
]


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


def _consolidate_recommendations(
    recs: List[SettingsRecommendation],
) -> List[SettingsRecommendation]:
    """Resolve contradictory recommendations for the same parameter.

    When multiple advisories recommend opposite directions for the same
    parameter in overlapping time windows, keep only the direction with
    higher total weighted score (confidence × |predicted_tir_delta|).

    EXP-2597 found 15 contradictions across 7/9 patients, primarily ISF
    advisories (sim-based says decrease, correction-based says increase).
    """
    from collections import defaultdict

    # Group by parameter
    groups: dict = defaultdict(list)
    for r in recs:
        p = r.parameter.value if hasattr(r.parameter, 'value') else str(r.parameter)
        groups[p].append(r)

    consolidated = []
    for param, param_recs in groups.items():
        if len(param_recs) <= 1:
            consolidated.extend(param_recs)
            continue

        # Check for directional conflicts
        directions = set(r.direction for r in param_recs)
        if len(directions) <= 1:
            consolidated.extend(param_recs)
            continue

        # Conflict exists — compute weighted score per direction
        dir_scores: dict = defaultdict(float)
        dir_recs: dict = defaultdict(list)
        for r in param_recs:
            score = r.confidence * abs(r.predicted_tir_delta)
            dir_scores[r.direction] += score
            dir_recs[r.direction].append(r)

        # Keep only the winning direction
        winning_dir = max(dir_scores, key=dir_scores.get)
        consolidated.extend(dir_recs[winning_dir])

    return consolidated


def _deduplicate_same_direction(
    recs: List[SettingsRecommendation],
) -> List[SettingsRecommendation]:
    """Merge same-parameter same-direction advisories into one.

    EXP-2627: Per-block CR/ISF advisories fire 3-5 times per patient.
    Merging reduces advisory count by 52% (6.8→3.2) without losing
    information. Direction agreement is 100% within groups.

    Strategy:
    - confidence-weighted average magnitude
    - sum of predicted_tir_delta (blocks contribute independently)
    - max confidence from group
    - annotated with source count and magnitude range
    """
    from collections import defaultdict

    groups: dict = defaultdict(list)
    for r in recs:
        p = r.parameter.value if hasattr(r.parameter, 'value') else str(r.parameter)
        key = (p, r.direction)
        groups[key].append(r)

    deduped = []
    for (param, direction), group in groups.items():
        if len(group) == 1:
            deduped.append(group[0])
            continue

        weights = np.array([r.confidence for r in group])
        mags = np.array([r.magnitude_pct for r in group])
        avg_mag = float(np.average(mags, weights=weights)) if weights.sum() > 0 else float(np.mean(mags))

        total_delta = sum(r.predicted_tir_delta for r in group)
        max_conf = max(r.confidence for r in group)

        all_hours = [(r.affected_hours[0], r.affected_hours[1]) for r in group]
        min_h = min(h[0] for h in all_hours)
        max_h = max(h[1] for h in all_hours)

        mag_range = f"{min(mags):.0f}-{max(mags):.0f}%"
        merged = SettingsRecommendation(
            parameter=group[0].parameter,
            direction=direction,
            magnitude_pct=round(avg_mag, 1),
            current_value=group[0].current_value,
            suggested_value=group[0].suggested_value,
            predicted_tir_delta=round(total_delta, 1),
            affected_hours=(min_h, max_h),
            confidence=max_conf,
            evidence=(f"Consolidated from {len(group)} time-block advisories "
                      f"(range: {mag_range}). "
                      + group[0].evidence.split('.')[0] + '.'),
            rationale=group[0].rationale,
        )
        deduped.append(merged)

    return deduped


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
                             override_active: Optional[np.ndarray] = None,
                             dual_phase_isf: Optional['DualPhaseISF'] = None,
                             patterns: Optional['PatternProfile'] = None,
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
    - Override ISF split detection (EXP-2621)
    - Advisory confidence tier (EXP-2622)
    - Carb context overnight (EXP-2627/2628)
    - Response-curve ISF (EXP-1301)
    - SC suppression ceiling (EXP-2656/2667)
    - Dose-response ISF curves (EXP-2636/2640)

    ISF Advisory Decision Tree
    ==========================
    Multiple ISF advisories fire simultaneously and are resolved by the
    consolidation pipeline (_consolidate → _deduplicate → tier → clamp).

    ACTIONABLE advisories (may change settings):
      advise_isf           - Primary ISF from clinical report (EXP-747).
                             Fires always. Uses observed ISF vs profile.
      advise_correction_isf - ISF from correction-only boluses (EXP-2579).
                             Fires when bolus+carbs+iob available. Bootstrap CI.
      advise_forward_sim   - Joint ISF×CR from forward simulation (EXP-2562).
                             Fires when bolus+carbs+iob available. Highest TIR impact.
      advise_circadian_isf - Day/night ISF split (EXP-2271). Fires always.
                             Recommends 2-zone schedule when variation >50%.
      advise_circadian_isf_profiled - 4-block ISF profile (EXP-2271).
                             Fires always. Finer-grained than 2-zone.
      advise_override_isf  - Exercise/stress ISF split (EXP-2621).
                             Fires when override_active flag available.
      advise_dose_response_isf - Dose-dependent ISF curve (EXP-2640).
                             Fires when bolus available. Actionable only when
                             profile ratio diverges >30%.

    INFORMATIONAL advisories (direction="informational", no setting change):
      advise_isf_nonlinearity   - Power-law ISF warning (EXP-2511).
      advise_isf_dual_phase     - Demand vs apparent ISF (EXP-2651).
      advise_response_curve_isf - Response-curve ISF + tau (EXP-1301).
      advise_sc_ceiling         - SC suppression ceiling (EXP-2656).

    Conflict resolution:
      1. _consolidate_recommendations: Same parameter, opposite directions →
         keep direction with higher weighted score (confidence × |delta|).
      2. _deduplicate_same_direction: Same parameter, same direction →
         merge into one (confidence-weighted avg magnitude, summed delta).
      3. apply_confidence_tier: Grade A/B/C/D based on days_of_data.
      4. apply_safety_clamp: Cap magnitude at safe limits.

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
        override_active: (N,) optional binary override active flag for
            override ISF split analysis (EXP-2621).

    Returns:
        List of SettingsRecommendation, sorted by predicted_tir_delta descending.
    """
    recs = []

    # Use pre-computed demand-phase ISF if provided, otherwise compute
    # (avoids redundant computation when called from pipeline)
    if dual_phase_isf is None and bolus is not None:
        try:
            from cgmencode.production.clinical_rules import compute_demand_isf
            dual_phase_isf = compute_demand_isf(glucose, bolus, profile,
                                                carbs=carbs)
        except Exception:
            pass  # graceful fallback — advise_isf will use informational mode

    # Basal assessment (requires metabolic state)
    if metabolic is not None:
        basal_rec = advise_basal(glucose, metabolic, hours, clinical, profile, days_of_data)
        if basal_rec:
            recs.append(basal_rec)

        cr_rec = advise_cr(glucose, metabolic, hours, clinical, profile, days_of_data)
        if cr_rec:
            recs.append(cr_rec)

    # ISF assessment — targets demand-phase ISF when available (EXP-2651)
    isf_rec = advise_isf(clinical, profile, days_of_data,
                         dual_phase=dual_phase_isf)
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

    # ISF segmentation from pattern analysis (EXP-765)
    if patterns is not None:
        isf_seg_recs = advise_isf_segmented(
            glucose, metabolic, hours, clinical, profile, patterns,
            days_of_data)
        recs.extend(isf_seg_recs)

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

    # Multi-factor deconfounded ISF (Wave-12, EXP-2741: 67% gap closure)
    # Filters to corrections only; removes basal/EGP/meal confounds
    corr_denom_isf = advise_correction_denominator_isf(
        clinical, profile, days_of_data=days_of_data)
    if corr_denom_isf:
        recs.append(corr_denom_isf)

    # Effective CR from meal response (EXP-2609/2610)
    if bolus is not None and carbs is not None:
        eff_cr_recs = advise_effective_cr(
            glucose, hours, profile,
            bolus=bolus, carbs=carbs,
            days_of_data=days_of_data)
        recs.extend(eff_cr_recs)

    # Overnight basal quadrant analysis (EXP-2589)
    if actual_basal is not None:
        quadrant_recs = advise_overnight_basal_quadrant(
            glucose, hours, profile,
            actual_basal=actual_basal,
            days_of_data=days_of_data)
        recs.extend(quadrant_recs)

    # Loop workload basal analysis (EXP-2593)
    if actual_basal is not None:
        workload_recs = advise_loop_workload(
            glucose, hours, profile,
            actual_basal=actual_basal,
            days_of_data=days_of_data)
        recs.extend(workload_recs)

    # Override ISF split detection (EXP-2621)
    if (override_active is not None and bolus is not None
            and carbs is not None):
        override_recs = advise_override_isf(
            glucose, hours, profile,
            bolus=bolus, carbs=carbs,
            override_active=override_active,
            days_of_data=days_of_data)
        recs.extend(override_recs)

    # Dual-phase ISF advisory (EXP-2651) — demand vs apparent ISF
    if dual_phase_isf is not None:
        dp_rec = advise_isf_dual_phase(dual_phase_isf, days_of_data)
        if dp_rec:
            recs.append(dp_rec)

    # Patience mode advisory (EXP-2662) — cap SMBs during wall episodes
    if iob is not None:
        try:
            from cgmencode.production.clinical_rules import detect_insulin_saturation
            sat = detect_insulin_saturation(glucose, iob)
            patience_rec = advise_patience_mode(sat, days_of_data)
            if patience_rec:
                recs.append(patience_rec)
            # SC ceiling advisory (EXP-2656/2667) — uses saturation result
            ceiling_rec = advise_sc_ceiling(
                glucose, iob, profile, days_of_data,
                saturation=sat)
            if ceiling_rec:
                recs.append(ceiling_rec)
        except Exception:
            pass  # graceful fallback — saturation detection is optional

    # Carb context overnight advisory (EXP-2627/2628)
    if carbs is not None:
        carb_ctx_rec = advise_carb_context_overnight(
            glucose, hours, carbs, profile, days_of_data,
            iob=iob, cob=cob)
        if carb_ctx_rec:
            recs.append(carb_ctx_rec)

    # Response-curve ISF advisory (EXP-1301)
    if bolus is not None:
        rc_rec = advise_response_curve_isf(
            glucose, hours, profile,
            bolus=bolus, basal_rate=actual_basal,
            days_of_data=days_of_data)
        if rc_rec:
            recs.append(rc_rec)

    # Dose-response ISF advisory (EXP-2636/2640)
    if bolus is not None:
        dr_rec = advise_dose_response_isf(
            glucose, hours, profile,
            bolus=bolus, carbs=carbs,
            days_of_data=days_of_data)
        if dr_rec:
            recs.append(dr_rec)

    # Overnight drift assessment (EXP-2371–2378, EXP-2622 48h carbs)
    overnight = assess_overnight_drift(
        glucose, hours, profile, days_of_data,
        iob=iob, cob=cob, actual_basal=actual_basal, carbs=carbs)
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

    # Consolidate contradictory recommendations (EXP-2597)
    # Multiple advisories can produce opposite directions for the same
    # parameter. Group by parameter and resolve conflicts by keeping
    # the higher weighted-score (confidence × |delta|) direction.
    recs = _consolidate_recommendations(recs)

    # Deduplicate same-parameter same-direction advisories (EXP-2627)
    recs = _deduplicate_same_direction(recs)

    # Apply confidence tier based on data days (EXP-2622)
    recs = apply_confidence_tier_to_recommendations(recs, days_of_data)

    # Apply safety clamp (EXP-2626)
    recs = apply_safety_clamp(recs)

    # Sort by predicted impact
    recs.sort(key=lambda r: abs(r.predicted_tir_delta), reverse=True)
    return recs


# ── Optimization Sequence (EXP-1765) ─────────────────────────────────

# CV threshold that determines optimization phase
_CV_THRESHOLD = 28.0  # %


def determine_optimization_phase(glucose: np.ndarray) -> OptimizationPhase:
    """Determine which optimization phase a patient needs (EXP-1765).

    Three-phase sequence (order matters — 6/11 patients harmed by wrong order):
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


# ── Settings Quality Score (EXP-2600) ────────────────────────────────

def compute_settings_quality_score(
    recs: List[SettingsRecommendation],
) -> float:
    """Compute composite Settings Quality Score (SQS) from recommendations.

    SQS = 100 - Σ(magnitude_pct × confidence × weight × 0.15) for all recs.
    Higher score (0-100) = better settings alignment with metabolic needs.

    Parameter weights (EXP-2613):
      ISF: 2.0× (most impactful for TIR outcomes)
      CR:  1.0× (less direct impact)
      Basal: 1.5× (moderate impact)
      Other: 1.0× (default)

    EXP-2600: Original formula r=0.833. EXP-2606: magnitude basis r=0.726.
    EXP-2613: Weighted formula r=0.603 (best of 6 candidates after effective
    CR addition). ISF weighting 2× improves discrimination because ISF
    changes have more direct impact on glycemic variability.

    Args:
        recs: consolidated recommendations from generate_settings_advice().

    Returns:
        SQS as float in [0, 100].
    """
    _PARAM_WEIGHTS = {
        SettingsParameter.ISF: 2.0,
        SettingsParameter.CR: 1.0,
        SettingsParameter.BASAL_RATE: 1.5,
    }
    total = sum(
        r.magnitude_pct * r.confidence * 0.15 * _PARAM_WEIGHTS.get(r.parameter, 1.0)
        for r in recs
    )
    return max(0.0, min(100.0, 100.0 - total))


# ── Advisory Confidence Tier (EXP-2622) ──────────────────────────────

# EXP-2622: CR stable by 21d (67%), ISF by 14-30d, direction by 7d (87%).
# Confidence tiers based on data days:
#   DIRECTION (7d): direction-only advisory (87% correct)
#   PRELIMINARY (14d): magnitude advisory with uncertainty
#   STABLE (21d): stable CR advisory
#   FULL (30d+): stable ISF+CR advisory

_CONFIDENCE_TIERS = {
    'direction_only': 7,
    'preliminary': 14,
    'stable_cr': 21,
    'full': 30,
}


def compute_advisory_confidence_tier(days_of_data: float) -> str:
    """Return confidence tier based on days of available data.

    EXP-2622 validated convergence rates:
      - 7 days: ISF direction correct 87.5% of the time
      - 14 days: ISF magnitude within 10% for 58% of patients
      - 21 days: CR magnitude within 10% for 67% of patients
      - 30+ days: Both ISF and CR stable for majority of patients

    Args:
        days_of_data: total days of glucose+insulin data available.

    Returns:
        Tier name: 'insufficient', 'direction_only', 'preliminary',
        'stable_cr', or 'full'.
    """
    if days_of_data < 7:
        return 'insufficient'
    if days_of_data < 14:
        return 'direction_only'
    if days_of_data < 21:
        return 'preliminary'
    if days_of_data < 30:
        return 'stable_cr'
    return 'full'


def apply_confidence_tier_to_recommendations(
    recs: List[SettingsRecommendation],
    days_of_data: float,
) -> List[SettingsRecommendation]:
    """Adjust recommendation confidence based on data availability tier.

    EXP-2622: With fewer days of data, ISF and CR estimates are less
    stable. This applies a confidence penalty:
      - direction_only (7-14d): confidence × 0.5, keep direction only
      - preliminary (14-21d): confidence × 0.7
      - stable_cr (21-30d): ISF confidence × 0.8, CR unchanged
      - full (30d+): no penalty

    Args:
        recs: list of recommendations from generate_settings_advice().
        days_of_data: total days of data available.

    Returns:
        Modified list with adjusted confidence values.
    """
    tier = compute_advisory_confidence_tier(days_of_data)

    if tier == 'full':
        return recs

    for rec in recs:
        if tier == 'direction_only':
            rec.confidence = round(rec.confidence * 0.5, 2)
            rec.evidence += " [LOW DATA: direction-only advisory, <14 days]"
        elif tier == 'preliminary':
            rec.confidence = round(rec.confidence * 0.7, 2)
            rec.evidence += " [PRELIMINARY: 14-21 days of data]"
        elif tier == 'stable_cr':
            if rec.parameter == SettingsParameter.ISF:
                rec.confidence = round(rec.confidence * 0.8, 2)
                rec.evidence += " [ISF may still be converging, <30 days]"

    return recs


# ── Safety Clamp (EXP-2626) ──────────────────────────────────────────

# EXP-2626: 36% of advisories exceed 25% magnitude. 7/10 extreme
# advisories (>50%) come from ISF-related advisors. Clinical best
# practice limits settings changes to 10-15% per adjustment cycle.
# Clamping at 25% preserves ranking for 15/16 patients.
MAX_SAFE_MAGNITUDE_PCT = 25.0


def apply_safety_clamp(
    recs: List[SettingsRecommendation],
    max_magnitude_pct: float = MAX_SAFE_MAGNITUDE_PCT,
) -> List[SettingsRecommendation]:
    """Clamp advisory magnitudes to a clinically safe maximum.

    EXP-2626: Large single-step settings changes (>25%) are clinically
    risky. This function caps magnitude_pct at max_magnitude_pct while
    preserving direction and ranking. Clamped advisories are annotated
    so the user knows the full magnitude was larger.

    Args:
        recs: list of recommendations from generate_settings_advice().
        max_magnitude_pct: maximum allowed magnitude (default 25%).

    Returns:
        Modified list with clamped magnitude values.
    """
    for rec in recs:
        if rec.magnitude_pct > max_magnitude_pct:
            original = rec.magnitude_pct
            rec.magnitude_pct = max_magnitude_pct
            rec.evidence += (
                f" [CLAMPED from {original:.0f}% to {max_magnitude_pct:.0f}%"
                f" — stage over multiple adjustment cycles]"
            )

    return recs


