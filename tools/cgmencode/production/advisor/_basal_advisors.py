"""Basal rate, overnight drift, and loop workload advisory functions."""

from __future__ import annotations
from typing import List, Optional, Tuple
import numpy as np
from ..types import (
    BasalAssessment, ClinicalReport, MetabolicState,
    OvernightDriftAssessment, OvernightPhenotype, LoopWorkloadReport,
    PatientProfile, SettingsParameter, SettingsRecommendation,
    PeriodMetrics,
)
from ._simulation import simulate_tir_with_settings, MIN_DATA_DAYS, HIGH_CONFIDENCE_DAYS, PER_ADVISOR_TIR_DELTA_CAP_PP


__all__ = [
    '_CLEAN_NIGHT_COB_MAX',
    '_CLEAN_NIGHT_GAP_MAX',
    '_CLEAN_NIGHT_IOB_MAX',
    '_DAWN_CUTOFF',
    '_DAWN_RISE_THRESHOLD',
    '_DRIFT_MODERATE_THRESHOLD',
    '_DRIFT_STABLE_THRESHOLD',
    '_GLYCOGEN_DECAY',
    '_GLYCOGEN_TAU_STEPS',
    '_HIGH_GLYCOGEN_THRESHOLD',
    '_LOOP_DEPENDENT_SUSPENSION',
    '_LOW_GLYCOGEN_THRESHOLD',
    '_MIN_CLEAN_NIGHTS',
    '_MIN_OVERNIGHT_POINTS',
    '_NET_BASAL_THRESHOLD',
    '_OVERNIGHT_END',
    '_OVERNIGHT_QUADRANT_END',
    '_OVERNIGHT_QUADRANT_START',
    '_OVERNIGHT_START',
    '_SLOPE_FLAT_THRESHOLD',
    '_WORKLOAD_NORM_FACTOR',
    '_WORKLOAD_PERIODS',
    'advise_basal',
    'advise_carb_context_overnight',
    'advise_loop_workload',
    'advise_overnight_basal_quadrant',
    'assess_overnight_drift',
    'compute_loop_workload',
]


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
        predicted_tir_delta=round(min(PER_ADVISOR_TIR_DELTA_CAP_PP, best_delta * 100), 1),  # percentage points
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


# ── Overnight Basal Quadrant Analysis (EXP-2589) ────────────────────
#
# In closed-loop systems, glucose drift alone is insufficient for basal
# assessment because the loop actively modifies basal delivery. The
# quadrant analysis combines glucose slope with net basal (actual -
# scheduled) to distinguish basal inadequacy from dawn phenomenon:
#
# | Glucose  | Net Basal | Assessment              |
# |----------|-----------|-------------------------|
# | Rising   | Positive  | BASAL TOO LOW           |
# | Rising   | Negative  | DAWN PHENOMENON         |
# | Flat     | Positive  | BASAL SLIGHTLY LOW      |
# | Flat     | Negative  | BASAL SLIGHTLY HIGH     |
# | Falling  | Negative  | BASAL TOO HIGH          |
# | Falling  | Positive  | OVERCORRECTION          |

_OVERNIGHT_QUADRANT_START = 0.0
_OVERNIGHT_QUADRANT_END = 6.0
_SLOPE_FLAT_THRESHOLD = 3.0  # mg/dL/h — within ±3 is "flat"
_NET_BASAL_THRESHOLD = 0.1   # U/h — within ±0.1 is "neutral"
_MIN_OVERNIGHT_POINTS = 36   # 3 hours of 5-min data


def advise_overnight_basal_quadrant(
    glucose: np.ndarray,
    hours: np.ndarray,
    profile: "PatientProfile",
    actual_basal: Optional[np.ndarray] = None,
    days_of_data: float = 7.0,
    inferred_meal_indices: Optional[np.ndarray] = None,
) -> List[SettingsRecommendation]:
    """Assess overnight basal using quadrant analysis (EXP-2589).

    Requires actual_basal data (from loop telemetry). Without it, falls
    back to glucose-only assessment (less reliable for closed-loop).

    Returns at most one recommendation for overnight basal rate.
    """
    if actual_basal is None:
        return []

    if days_of_data < 3:
        return []

    # Build post-meal exclusion mask (4h after each inferred meal)
    POST_MEAL_STEPS = 48
    post_meal_mask = np.zeros(len(glucose), dtype=bool)
    if inferred_meal_indices is not None and len(inferred_meal_indices):
        for idx in inferred_meal_indices:
            i = int(idx)
            if i < 0 or i >= len(glucose):
                continue
            post_meal_mask[i:min(len(glucose), i + POST_MEAL_STEPS)] = True

    # Extract overnight windows (00-06)
    night_mask = (hours < _OVERNIGHT_QUADRANT_END) & (~post_meal_mask)
    g_night = glucose[night_mask]
    h_night = hours[night_mask]
    ab_night = actual_basal[night_mask]

    # Get scheduled basal
    basal_vals = [e.get("value", e.get("rate", 0.8))
                  for e in profile.basal_schedule]
    sched_basal = float(np.median([float(v) for v in basal_vals])) if basal_vals else 0.8

    # Filter to valid glucose readings
    valid = ~np.isnan(g_night) & ~np.isnan(ab_night)
    if valid.sum() < _MIN_OVERNIGHT_POINTS:
        return []

    g_valid = g_night[valid]
    h_valid = h_night[valid]
    ab_valid = ab_night[valid]

    # Glucose slope via linear regression
    slope, _ = np.polyfit(h_valid, g_valid, 1)

    # Net basal: actual - scheduled
    net_basal = float(np.mean(ab_valid) - sched_basal)

    # Suspension fraction
    suspend_frac = float((ab_valid < 0.05).mean())

    # Quadrant classification
    if slope > _SLOPE_FLAT_THRESHOLD and net_basal > _NET_BASAL_THRESHOLD:
        quadrant = "rising_adding"
        assessment = "BASAL TOO LOW"
        direction = "increase"
        # Suggest increasing by the ratio of loop compensation
        pct_increase = min(50.0, abs(net_basal / sched_basal) * 100) if sched_basal > 0 else 10.0
        confidence = 0.75
    elif slope > _SLOPE_FLAT_THRESHOLD and net_basal < -_NET_BASAL_THRESHOLD:
        quadrant = "rising_cutting"
        assessment = "DAWN PHENOMENON"
        # Dawn phenomenon: loop can't help. Recommend modest basal increase
        # specifically for 03-06 window.
        direction = "increase"
        pct_increase = min(30.0, slope * 2.0)  # proportional to rise rate
        confidence = 0.50  # lower confidence — dawn is complex
    elif slope < -_SLOPE_FLAT_THRESHOLD and net_basal < -_NET_BASAL_THRESHOLD:
        quadrant = "falling_cutting"
        assessment = "BASAL TOO HIGH"
        direction = "decrease"
        pct_increase = min(40.0, abs(net_basal / sched_basal) * 100) if sched_basal > 0 else 10.0
        confidence = 0.75
    elif slope < -_SLOPE_FLAT_THRESHOLD and net_basal > _NET_BASAL_THRESHOLD:
        quadrant = "falling_adding"
        assessment = "OVERCORRECTION"
        # Loop adding but glucose still falling — likely residual from correction
        return []  # Not a basal issue
    elif abs(slope) <= _SLOPE_FLAT_THRESHOLD and net_basal > _NET_BASAL_THRESHOLD:
        quadrant = "flat_adding"
        assessment = "BASAL SLIGHTLY LOW"
        direction = "increase"
        pct_increase = min(20.0, abs(net_basal / sched_basal) * 50) if sched_basal > 0 else 5.0
        confidence = 0.60
    elif abs(slope) <= _SLOPE_FLAT_THRESHOLD and net_basal < -_NET_BASAL_THRESHOLD:
        quadrant = "flat_cutting"
        assessment = "BASAL SLIGHTLY HIGH"
        direction = "decrease"
        pct_increase = min(20.0, abs(net_basal / sched_basal) * 50) if sched_basal > 0 else 5.0
        confidence = 0.55
    else:
        # Flat glucose + neutral net basal = adequate
        return []

    suggested = sched_basal * (1.0 + pct_increase / 100.0) if direction == "increase" else \
                sched_basal * (1.0 - pct_increase / 100.0)
    suggested = round(max(0.05, suggested), 2)

    dawn_note = ""
    if quadrant == "rising_cutting":
        dawn_note = (f" Dawn phenomenon detected: glucose rises {slope:+.1f} mg/dL/h "
                     f"despite loop suspension ({suspend_frac:.0%} of overnight). "
                     f"Consider increasing 03-06 basal specifically.")

    return [SettingsRecommendation(
        parameter=SettingsParameter.BASAL_RATE,
        direction=direction,
        magnitude_pct=round(pct_increase, 0),
        current_value=sched_basal,
        suggested_value=suggested,
        predicted_tir_delta=round(min(PER_ADVISOR_TIR_DELTA_CAP_PP, pct_increase * 0.05), 1),  # conservative
        affected_hours=(_OVERNIGHT_QUADRANT_START, _OVERNIGHT_QUADRANT_END),
        confidence=round(confidence, 2),
        evidence=(
            f"Overnight quadrant analysis (EXP-2589): {assessment}. "
            f"Glucose slope {slope:+.1f} mg/dL/h, net basal {net_basal:+.2f} U/h, "
            f"suspension {suspend_frac:.0%}. Quadrant: {quadrant}.{dawn_note}"
        ),
        rationale=(
            f"{direction.capitalize()} overnight basal by {pct_increase:.0f}% "
            f"(from {sched_basal:.2f} to {suggested:.2f} U/hr). "
            f"In closed-loop, combining glucose direction with loop compensation "
            f"direction provides more reliable basal assessment than glucose alone."
        ),
    )]


def advise_loop_workload(
    glucose: np.ndarray,
    hours: np.ndarray,
    profile: "PatientProfile",
    actual_basal: Optional[np.ndarray] = None,
    days_of_data: float = 7.0,
    inferred_meal_indices: Optional[np.ndarray] = None,
) -> List[SettingsRecommendation]:
    """Assess basal adequacy from full-day loop workload analysis (EXP-2593).

    Uses the AID loop's own behavior (actual vs scheduled basal) across
    all hours to detect systematic basal mismatch. This complements the
    overnight-only quadrant analysis with a whole-day view.

    Key finding from EXP-2593: 9/12 patients have scheduled basal too
    high (loop consistently cuts). Directional bias is the primary signal.

    Returns at most one recommendation.
    """
    if actual_basal is None:
        return []

    if days_of_data < 3:
        return []

    # Get scheduled basal
    basal_vals = [e.get("value", e.get("rate", 0.8))
                  for e in profile.basal_schedule]
    sched_basal = float(np.median([float(v) for v in basal_vals])) if basal_vals else 0.8

    if sched_basal <= 0:
        return []

    # Build post-meal exclusion mask (4h after each inferred meal).
    # Meal-driven loop additions otherwise inflate the directional bias
    # toward "basal too low" when the patient simply doesn't log carbs.
    POST_MEAL_STEPS = 48
    post_meal = np.zeros(len(glucose), dtype=bool)
    if inferred_meal_indices is not None and len(inferred_meal_indices):
        for idx in inferred_meal_indices:
            i = int(idx)
            if i < 0 or i >= len(glucose):
                continue
            post_meal[i:min(len(glucose), i + POST_MEAL_STEPS)] = True

    # Filter to valid points (both glucose and actual_basal present, no recent meal)
    valid = (~np.isnan(glucose) & ~np.isnan(actual_basal)
             & (actual_basal >= 0) & (~post_meal))
    if valid.sum() < 200:
        return []

    actual = actual_basal[valid]
    g = glucose[valid]

    # Core workload metrics
    net = actual - sched_basal
    directional_bias = float(np.mean(net / sched_basal))
    suspension_frac = float(np.mean(actual < 0.01))
    adding_frac = float(np.mean(net > 0.05))
    cutting_frac = float(np.mean(net < -0.05))

    # TIR for context
    tir = float(np.mean((g >= 70) & (g <= 180)))

    # Classification: combine bias direction with TIR
    # Strong bias (>0.1 in magnitude) + poor TIR → settings need change
    # Strong bias + good TIR → loop compensating, change optional
    _BIAS_THRESHOLD = 0.2  # 20% deviation from scheduled
    _TIR_OK = 0.70  # 70% TIR considered acceptable

    if abs(directional_bias) < _BIAS_THRESHOLD:
        return []  # Basal adequately matched

    if directional_bias > _BIAS_THRESHOLD:
        # Loop consistently ADDS → basal too low
        direction = "increase"
        pct = min(40.0, abs(directional_bias) * 50)
        confidence = 0.70 if tir < _TIR_OK else 0.50
        assessment = "BASAL TOO LOW"
        note = (f"Loop adds insulin {adding_frac:.0%} of the time "
                f"(directional bias: +{directional_bias:.0%}).")
    else:
        # Loop consistently CUTS → basal too high
        direction = "decrease"
        pct = min(40.0, abs(directional_bias) * 50)
        confidence = 0.65 if tir < _TIR_OK else 0.45
        assessment = "BASAL TOO HIGH"
        note = (f"Loop cuts insulin {cutting_frac:.0%} of the time, "
                f"suspends {suspension_frac:.0%} "
                f"(directional bias: {directional_bias:+.0%}).")

    # Lower confidence if TIR is already good (loop is compensating fine)
    if tir >= _TIR_OK:
        note += (f" TIR is already {tir:.0%} — the loop is compensating "
                 f"successfully. Adjustment optional but would reduce loop workload.")

    suggested = sched_basal * (1.0 + pct / 100.0) if direction == "increase" else \
                sched_basal * (1.0 - pct / 100.0)
    suggested = round(max(0.05, suggested), 2)
    predicted_delta = round(pct * 0.03, 1) if tir < _TIR_OK else round(pct * 0.01, 1)

    return [SettingsRecommendation(
        parameter=SettingsParameter.BASAL_RATE,
        direction=direction,
        magnitude_pct=round(pct, 0),
        current_value=sched_basal,
        suggested_value=suggested,
        predicted_tir_delta=predicted_delta,
        affected_hours=(0, 24),
        confidence=round(confidence, 2),
        evidence=(
            f"Loop workload analysis (EXP-2593): {assessment}. {note} "
            f"Analysis based on {valid.sum()} samples over {days_of_data:.0f} days."
        ),
        rationale=(
            f"{direction.capitalize()} basal by {pct:.0f}% "
            f"(from {sched_basal:.2f} to {suggested:.2f} U/hr) across all hours. "
            f"The AID loop's systematic {direction.replace('increase','adding').replace('decrease','cutting')} "
            f"indicates scheduled basal {'understates' if direction == 'increase' else 'overstates'} "
            f"metabolic need."
        ),
    )]


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
        carbs: np.ndarray = None,
        inferred_meal_indices: Optional[np.ndarray] = None,
        ) -> Optional[OvernightDriftAssessment]:
    """Assess basal adequacy from overnight glucose drift (EXP-2371–2378).

    Uses clean overnight windows (00:00–06:00) where IOB and COB are minimal
    to measure glucose drift rate — the most reliable indicator of basal
    rate adequacy.

    Clean-night filtering is critical: residual dinner bolus IOB and late
    snack COB confound overnight glucose trends. Only nights with IOB < 0.5U
    and COB < 5g are used (EXP-2375).

    48h carb history integration (EXP-2622/2627):
    Preceding carb load modulates overnight drift via hepatic glycogen
    loading. Low 48h carbs → glycogen depletion → rising overnight BG
    (r=-0.303, +57% over 24h window). When drift co-occurs with low
    preceding carbs, the cause may be glycogen rather than basal rate.

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

    # Filter to clean nights (IOB < 0.5, COB < 5, no recent inferred meal)
    POST_MEAL_STEPS = 48  # 4 h
    inferred_post_meal = None
    if inferred_meal_indices is not None and len(inferred_meal_indices):
        inferred_post_meal = np.zeros(len(glucose), dtype=bool)
        for idx in inferred_meal_indices:
            i = int(idx)
            if i < 0 or i >= len(glucose):
                continue
            inferred_post_meal[i:min(len(glucose), i + POST_MEAL_STEPS)] = True

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
        if inferred_post_meal is not None:
            if np.any(inferred_post_meal[idx]):
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

    # 48h carb history — glycogen proxy (EXP-2622/2627)
    # τ=24h exponential accumulator; r=-0.303 with overnight drift
    carbs_48h_g = 0.0
    glycogen_note = ''
    if carbs is not None:
        carb_vals = np.nan_to_num(carbs, nan=0.0)
        # Sum carbs in 48h rolling windows preceding each overnight segment
        # Each step is 5 min; 48h = 576 steps
        _48H_STEPS = 576
        per_night_carbs = []
        for idx in analysis_segments:
            seg_start = idx[0] if len(idx) > 0 else 0
            lookback_start = max(0, seg_start - _48H_STEPS)
            # Sum grams in 48h before this overnight
            preceding = float(np.sum(carb_vals[lookback_start:seg_start]))
            per_night_carbs.append(preceding)

        if per_night_carbs:
            carbs_48h_g = float(np.mean(per_night_carbs))

            # Interpret glycogen effect on drift
            _LOW_CARB_48H = 100.0   # grams — below this, glycogen may be depleted
            _HIGH_CARB_48H = 300.0  # grams — above this, glycogen is well-loaded
            if carbs_48h_g < _LOW_CARB_48H and mean_drift > _DRIFT_STABLE_THRESHOLD:
                glycogen_note = (
                    f"Low preceding carbs ({carbs_48h_g:.0f}g/48h) may "
                    f"contribute to rising overnight BG via glycogen "
                    f"depletion (EXP-2622: r=-0.303). Consider whether "
                    f"drift is dietary rather than basal rate.")
                # Reduce confidence — drift may be glycogen, not basal
                confidence *= 0.7
            elif carbs_48h_g > _HIGH_CARB_48H and mean_drift < -_DRIFT_STABLE_THRESHOLD:
                glycogen_note = (
                    f"High preceding carbs ({carbs_48h_g:.0f}g/48h) with "
                    f"falling overnight BG — glycogen-loaded hepatic output "
                    f"is lower than typical. Drift may normalize with "
                    f"consistent carb intake.")
                confidence *= 0.8

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
        carbs_48h_g=round(carbs_48h_g, 0),
        glycogen_note=glycogen_note,
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


# ── Carb Context Overnight Advisory (EXP-2627/2628) ──────────────────

# 48h carb history modulates overnight drift via hepatic glycogen loading.
# Exponential accumulator (τ=24h) correlates r=-0.303 with overnight drift.
# This advisory exposes the glycogen proxy as a standalone diagnostic.

_GLYCOGEN_TAU_STEPS = 288     # τ=24h × 12 steps/hr
_GLYCOGEN_DECAY = 1.0 - 1.0 / max(_GLYCOGEN_TAU_STEPS, 1)
_LOW_GLYCOGEN_THRESHOLD = 100.0   # grams/48h — risk of glycogen depletion
_HIGH_GLYCOGEN_THRESHOLD = 300.0  # grams/48h — well-loaded


def advise_carb_context_overnight(
    glucose: np.ndarray,
    hours: np.ndarray,
    carbs: Optional[np.ndarray],
    profile: PatientProfile,
    days_of_data: float,
    iob: Optional[np.ndarray] = None,
    cob: Optional[np.ndarray] = None,
) -> Optional[SettingsRecommendation]:
    """Warn when low 48h carb intake explains overnight glucose drift (EXP-2627/2628).

    Hepatic glycogen depletion from low carb intake causes rising overnight
    glucose independent of basal rate settings. This advisory prevents
    unnecessary basal increases by identifying glycogen-related drift.

    Research findings:
    - 48h carb window: r=-0.303 with overnight drift (57% stronger than 24h)
    - Exponential accumulator tau=24h: r=-0.28 (glycogen timescale)
    - Low carbs (<100g/48h) + rising overnight BG -> likely glycogen, not basal
    - High carbs (>300g/48h) + falling overnight BG -> glycogen-loaded EGP
    """
    if carbs is None or days_of_data < MIN_DATA_DAYS:
        return None

    carb_vals = np.nan_to_num(carbs, nan=0.0)
    bg = np.nan_to_num(glucose.astype(np.float64), nan=120.0)

    # Compute exponential glycogen accumulator (tau=24h)
    accum = np.zeros(len(carb_vals))
    for i in range(1, len(carb_vals)):
        accum[i] = accum[i - 1] * _GLYCOGEN_DECAY + carb_vals[i]

    # Extract overnight segments (00:00-06:00) and their glycogen state
    overnight_drifts = []
    overnight_glycogen = []
    _48H_STEPS = 576

    steps_per_day = 288
    n_days = len(glucose) // steps_per_day

    for day in range(n_days):
        day_start = day * steps_per_day
        night_start = day_start
        night_end = min(day_start + 72, len(glucose))

        if night_end - night_start < 36:
            continue

        night_bg = bg[night_start:night_end]
        valid = np.isfinite(night_bg) & (night_bg > 30)
        if np.sum(valid) < 20:
            continue

        if iob is not None:
            night_iob = iob[night_start:night_end]
            if np.nanmean(night_iob) > 0.5:
                continue
        if cob is not None:
            night_cob = cob[night_start:night_end]
            if np.nanmean(night_cob) > 5.0:
                continue

        t_hrs = np.arange(np.sum(valid)) * (5.0 / 60.0)
        if len(t_hrs) < 10:
            continue
        slope, _ = np.polyfit(t_hrs, night_bg[valid], 1)
        overnight_drifts.append(slope)

        lookback_start = max(0, night_start - _48H_STEPS)
        preceding_carbs = float(np.sum(carb_vals[lookback_start:night_start]))
        overnight_glycogen.append(preceding_carbs)

    if len(overnight_drifts) < 3:
        return None

    mean_drift = float(np.mean(overnight_drifts))
    mean_carbs_48h = float(np.mean(overnight_glycogen))

    is_low_carb_rising = (mean_carbs_48h < _LOW_GLYCOGEN_THRESHOLD and
                          mean_drift > 2.0)
    is_high_carb_falling = (mean_carbs_48h > _HIGH_GLYCOGEN_THRESHOLD and
                            mean_drift < -2.0)

    if not is_low_carb_rising and not is_high_carb_falling:
        return None

    confidence = min(0.6, days_of_data / HIGH_CONFIDENCE_DAYS)

    if is_low_carb_rising:
        return SettingsRecommendation(
            parameter=SettingsParameter.BASAL_RATE,
            direction="informational",
            magnitude_pct=0.0,
            current_value=0.0,
            suggested_value=0.0,
            predicted_tir_delta=0.0,
            affected_hours=(0.0, 6.0),
            confidence=confidence,
            evidence=(f"48h carb context (EXP-2627): mean {mean_carbs_48h:.0f}g/48h "
                      f"preceding {len(overnight_drifts)} clean nights. "
                      f"Overnight drift {mean_drift:+.1f} mg/dL/hr. "
                      f"Low carbs correlate with rising BG (r=-0.303)."),
            rationale=(f"Low carb intake ({mean_carbs_48h:.0f}g/48h) likely "
                       f"causes rising overnight glucose via glycogen depletion "
                       f"(EXP-2628: tau=24h exponential accumulator). Consider "
                       f"whether drift is dietary before adjusting basal rate."),
        )
    else:
        return SettingsRecommendation(
            parameter=SettingsParameter.BASAL_RATE,
            direction="informational",
            magnitude_pct=0.0,
            current_value=0.0,
            suggested_value=0.0,
            predicted_tir_delta=0.0,
            affected_hours=(0.0, 6.0),
            confidence=confidence,
            evidence=(f"48h carb context (EXP-2627): mean {mean_carbs_48h:.0f}g/48h "
                      f"preceding {len(overnight_drifts)} clean nights. "
                      f"Overnight drift {mean_drift:+.1f} mg/dL/hr."),
            rationale=(f"High carb intake ({mean_carbs_48h:.0f}g/48h) with "
                       f"falling overnight glucose -- glycogen-loaded hepatic "
                       f"output reduces overnight BG. Drift may normalize "
                       f"with consistent carb intake."),
        )


