"""
meal_detector.py — Physics-based meal detection from metabolic flux residuals.

Research basis: EXP-748 (unannounced meal detection, 46.5% of glucose rises),
               EXP-753 (meal sizing via residual integral),
               EXP-762 (relaxed detection, 23.4% truly unannounced)

Algorithm:
  1. Compute positive residual bursts (BG rising faster than physics predicts)
  2. Cluster bursts into meal events (30-min merge window)
  3. Classify each as announced/unannounced by checking carb_supply
  4. Estimate meal size from residual integral × CR/ISF conversion
  5. Assign to meal window (breakfast/lunch/dinner/snack)

Key findings:
  - 2σ threshold on rolling 30-min positive residual sum → F1=0.939 reactive
  - Residual integral correlates with carb grams (via CR/ISF conversion)
  - Meal windows: breakfast 05-10h, lunch 10-14h, dinner 17-21h
"""

from __future__ import annotations

from typing import List, Optional

import numpy as np

from .types import (
    DetectedMeal, MealArchetype, MealHistory, MealResponse, MealResponseType,
    MealWindow, MetabolicState, PatientProfile,
)


# Detection parameters (validated in EXP-748, EXP-762)
DEFAULT_SIGMA_MULT = 2.0    # 2σ threshold for burst detection
ROLLING_WINDOW = 6          # 30 min (6 × 5-min steps)
MERGE_GAP = 12              # Merge bursts within 60 min into one event
MIN_CARB_SUPPLY = 0.5       # Threshold to call a meal "announced"

# Meal window boundaries (from exp_autoresearch_681.py:264-266)
MEAL_WINDOWS = {
    MealWindow.BREAKFAST: (5.0, 10.0),
    MealWindow.LUNCH: (10.0, 14.0),
    MealWindow.DINNER: (17.0, 21.0),
}


def _classify_meal_window(hour: float) -> MealWindow:
    """Classify hour of day into meal window."""
    for window, (start, end) in MEAL_WINDOWS.items():
        if start <= hour < end:
            return window
    return MealWindow.SNACK


def detect_meal_events(glucose: np.ndarray,
                       metabolic: MetabolicState,
                       hours: np.ndarray,
                       timestamps: np.ndarray,
                       profile: PatientProfile,
                       sigma_mult: float = DEFAULT_SIGMA_MULT,
                       ) -> List[DetectedMeal]:
    """Detect meals from physics residual bursts.

    Adapts EXP-748 algorithm: large positive residuals indicate
    glucose rising faster than the supply-demand model predicts,
    which signals unmodeled carb absorption (= meal).

    Args:
        glucose: (N,) cleaned glucose values.
        metabolic: MetabolicState with residual array.
        hours: (N,) fractional hour of day.
        timestamps: (N,) Unix timestamps (ms).
        profile: PatientProfile for ISF/CR conversion.
        sigma_mult: burst threshold multiplier (default 2.0).

    Returns:
        List of DetectedMeal objects.
    """
    residuals = metabolic.residual
    carb_supply = metabolic.carb_supply
    N = len(residuals)

    if N < 100:
        return []

    # ── Step 1: Detect positive residual bursts ───────────────────
    resid_std = np.nanstd(residuals[np.isfinite(residuals)])
    if resid_std < 1e-6:
        return []

    threshold = sigma_mult * resid_std

    # Rolling sum of positive residuals (30-min window)
    resid_pos = np.maximum(np.nan_to_num(residuals, nan=0.0), 0.0)
    rolling_pos = np.convolve(resid_pos, np.ones(ROLLING_WINDOW), mode='same')
    burst_threshold = threshold * ROLLING_WINDOW * 0.5

    burst_indices = np.where(rolling_pos > burst_threshold)[0]

    if len(burst_indices) == 0:
        return []

    # ── Step 2: Cluster bursts into events ────────────────────────
    events = []  # list of (start_idx, end_idx)
    current_start = burst_indices[0]
    current_end = burst_indices[0]

    for i in range(1, len(burst_indices)):
        if burst_indices[i] - current_end <= MERGE_GAP:
            current_end = burst_indices[i]
        else:
            events.append((current_start, current_end))
            current_start = burst_indices[i]
            current_end = burst_indices[i]
    events.append((current_start, current_end))

    # ── Step 3: Classify and size each event ──────────────────────
    isf = _median_value(profile.isf_mgdl(), 'value', 'sensitivity', default=50.0)
    cr = _median_value(profile.cr_schedule, 'value', 'carbratio', default=10.0)

    meals = []
    for ev_start, ev_end in events:
        # Check if announced (carb_supply active near event)
        lookback = 6   # 30 min before
        lookahead = 12  # 60 min after
        cs_start = max(0, ev_start - lookback)
        cs_end = min(N, ev_end + lookahead)
        cs_total = float(np.sum(carb_supply[cs_start:cs_end]))
        announced = cs_total > MIN_CARB_SUPPLY

        # Estimate meal size from residual integral
        r_start = ev_start
        r_end = min(N, ev_end + 36)  # 3h absorption window
        resid_integral = float(np.sum(residuals[r_start:r_end]))
        estimated_carbs = abs(resid_integral) * cr / max(isf, 1.0)

        # Confidence based on burst magnitude relative to threshold
        peak_burst = float(np.max(rolling_pos[ev_start:ev_end + 1]))
        confidence = min(1.0, peak_burst / (burst_threshold * 3.0))

        # Event center for timing
        center = (ev_start + ev_end) // 2
        if center >= N:
            center = N - 1

        meals.append(DetectedMeal(
            index=center,
            timestamp_ms=float(timestamps[center]) if center < len(timestamps) else 0.0,
            window=_classify_meal_window(float(hours[center])),
            estimated_carbs_g=max(0, estimated_carbs),
            announced=announced,
            residual_integral=resid_integral,
            confidence=confidence,
            hour_of_day=float(hours[center]),
        ))

    return meals


def build_meal_history(meals: List[DetectedMeal],
                       days_of_data: float) -> MealHistory:
    """Aggregate detected meals into summary statistics.

    Args:
        meals: list of DetectedMeal from detect_meal_events.
        days_of_data: total days covered.

    Returns:
        MealHistory with counts, rates, and per-window breakdown.
    """
    total = len(meals)
    announced = sum(1 for m in meals if m.announced)
    unannounced = total - announced

    by_window = {}
    for w in MealWindow:
        by_window[w.value] = sum(1 for m in meals if m.window == w)

    carbs = [m.estimated_carbs_g for m in meals if m.estimated_carbs_g > 0]

    return MealHistory(
        meals=meals,
        total_detected=total,
        announced_count=announced,
        unannounced_count=unannounced,
        unannounced_fraction=unannounced / total if total > 0 else 0.0,
        meals_per_day=total / max(days_of_data, 0.1),
        mean_carbs_g=float(np.mean(carbs)) if carbs else 0.0,
        by_window=by_window,
    )


def _median_value(schedule: list, *keys, default: float = 50.0) -> float:
    """Extract median value from schedule, trying multiple key names."""
    if not schedule:
        return default
    values = []
    for entry in schedule:
        for k in keys:
            v = entry.get(k)
            if v is not None:
                values.append(float(v))
                break
    return float(np.median(values)) if values else default


def classify_meal_response(glucose: np.ndarray,
                           meal: DetectedMeal,
                           metabolic: MetabolicState,
                           ) -> Optional[MealResponse]:
    """Classify postprandial glucose response for a detected meal (EXP-514).

    Analyzes the 3h window after meal detection to classify response:
    - FLAT: excursion <20 mg/dL (AID suppresses)
    - FAST: peak <60min, tail_ratio <0.2
    - BIPHASIC: second peak detected after initial recovery
    - SLOW: peak >90min or tail_ratio >0.4
    - MODERATE: standard absorption (none of above)

    Population distribution: Flat 50%, Biphasic 41%, Fast 5%, Slow 2%, Moderate 1%.

    Args:
        glucose: (N,) full glucose array.
        meal: DetectedMeal with index.
        metabolic: MetabolicState for demand analysis.

    Returns:
        MealResponse or None if insufficient post-meal data.
    """
    idx = meal.index
    N = len(glucose)
    post_end = min(idx + 36, N)  # 3h post-meal
    late_end = min(idx + 60, N)  # 5h for tail analysis

    if post_end - idx < 12:  # need at least 1h post-meal
        return None

    window = glucose[idx:post_end]
    valid = window[np.isfinite(window)]
    if len(valid) < 6:
        return None

    baseline = float(valid[0])
    peak = float(np.max(valid))
    excursion = peak - baseline
    peak_offset = int(np.argmax(valid))
    peak_time_min = peak_offset * 5.0

    # Tail ratio: late demand (2-5h) / early demand (0-2h)
    early_end = min(idx + 24, N)  # 2h
    early_demand = float(np.sum(np.abs(metabolic.demand[idx:early_end])))
    late_demand = float(np.sum(np.abs(metabolic.demand[early_end:late_end]))) if late_end > early_end else 0.0
    tail_ratio = late_demand / max(early_demand, 0.01)

    # Second peak detection: is there a demand spike after 2h?
    has_second_peak = False
    if late_end - early_end > 6:
        late_resid = metabolic.residual[early_end:late_end]
        late_valid = late_resid[np.isfinite(late_resid)]
        if len(late_valid) > 3:
            late_std = float(np.std(late_valid))
            late_max = float(np.max(late_valid))
            has_second_peak = late_max > late_std * 2.0

    # Classification per EXP-514 thresholds
    if excursion < 20:
        rtype = MealResponseType.FLAT
        confidence = 0.9
    elif peak_time_min < 60 and tail_ratio < 0.2:
        rtype = MealResponseType.FAST
        confidence = 0.8
    elif has_second_peak:
        rtype = MealResponseType.BIPHASIC
        confidence = 0.75
    elif peak_time_min > 90 or tail_ratio > 0.4:
        rtype = MealResponseType.SLOW
        confidence = 0.7
    else:
        rtype = MealResponseType.MODERATE
        confidence = 0.65

    return MealResponse(
        response_type=rtype,
        excursion_mg_dl=excursion,
        peak_time_min=peak_time_min,
        tail_ratio=tail_ratio,
        has_second_peak=has_second_peak,
        confidence=confidence,
    )


def classify_all_meal_responses(glucose: np.ndarray,
                                meals: List[DetectedMeal],
                                metabolic: MetabolicState,
                                ) -> List[MealResponse]:
    """Classify all detected meals' postprandial responses.

    Args:
        glucose: (N,) full glucose array.
        meals: list of DetectedMeal.
        metabolic: MetabolicState.

    Returns:
        List of MealResponse (may be shorter than meals if some lack data).
    """
    responses = []
    for meal in meals:
        resp = classify_meal_response(glucose, meal, metabolic)
        if resp is not None:
            responses.append(resp)
    return responses


def classify_meal_archetypes(glucose: np.ndarray,
                             meals: List[DetectedMeal],
                             ) -> List[DetectedMeal]:
    """Assign meal archetype (controlled_rise vs high_excursion) to each meal.

    Research basis: EXP-1591–1598.
    - 5,369 meals → 2 robust archetypes via k-means on [excursion, peak_time, recovery]
    - Timing explains 9× more variance than dose
    - Clusters transfer perfectly across patients (ARI=0.976)
    - Controlled_rise: 53% of meals, excursion < 60 mg/dL, faster recovery
    - High_excursion: 47% of meals, excursion ≥ 60 mg/dL, slower recovery

    Uses simple threshold (no ML needed — EXP-1597 shows ARI=0.976 transferability):
    - excursion < 60 mg/dL → CONTROLLED_RISE
    - excursion ≥ 60 mg/dL → HIGH_EXCURSION

    Args:
        glucose: (N,) glucose values.
        meals: list of DetectedMeal (mutated in place with archetype field).

    Returns:
        Same list of DetectedMeal with archetype assigned.
    """
    N = len(glucose)

    for meal in meals:
        idx = meal.index
        # 2h post-meal window (24 steps)
        post_end = min(idx + 24, N)
        if post_end - idx < 6:
            meal.archetype = MealArchetype.CONTROLLED_RISE
            continue

        window = glucose[idx:post_end]
        valid = window[np.isfinite(window)]
        if len(valid) < 3:
            meal.archetype = MealArchetype.CONTROLLED_RISE
            continue

        pre_bg = float(valid[0])
        peak = float(np.max(valid))
        excursion = peak - pre_bg

        if excursion >= 60.0:
            meal.archetype = MealArchetype.HIGH_EXCURSION
        else:
            meal.archetype = MealArchetype.CONTROLLED_RISE

    return meals
