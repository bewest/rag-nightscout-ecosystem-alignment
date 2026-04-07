"""
meal_predictor.py — Predict upcoming meals from historical timing patterns.

Novel capability: analyzes 2+ weeks of detected meal timing to learn
per-window (breakfast/lunch/dinner) phase and frequency, then predicts
when the next meal will occur.

Clinical use case: recommend "eating soon" override 30-60 minutes before
predicted meal to allow pre-bolus insulin delivery, improving TIR.

Algorithm:
  1. Extract meal timing history per window (breakfast/lunch/dinner)
  2. Fit per-window Gaussian: N(μ_hour, σ_hour) for meal time distribution
  3. Compute frequency: meals per day per window
  4. Predict next meal: compare current time to upcoming window means
  5. Recommend eating_soon if within 30-60 min of predicted meal
"""

from __future__ import annotations

from typing import List, Optional

import numpy as np

from .types import (
    MealHistory, MealPrediction, MealTimingModel, MealWindow,
)


# Recommendation window (minutes before predicted meal to suggest eating_soon)
EATING_SOON_EARLY = 60.0     # Start recommending 60 min before
EATING_SOON_LATE = 15.0      # Stop recommending 15 min before (too late)
MIN_MEALS_FOR_MODEL = 3      # Minimum meals in a window to build timing model
MIN_DAYS_FOR_PREDICTION = 7  # Minimum days of data for predictions
MIN_FREQUENCY = 0.3          # Must occur ≥30% of days to predict


def build_timing_models(meal_history: MealHistory,
                        days_of_data: float) -> List[MealTimingModel]:
    """Build per-window timing models from detected meal history.

    For each meal window (breakfast/lunch/dinner), computes:
    - Mean hour of occurrence
    - Standard deviation (timing regularity)
    - Frequency (how many days per week this meal occurs)

    Args:
        meal_history: MealHistory from meal_detector.
        days_of_data: total days of data coverage.

    Returns:
        List of MealTimingModel, one per window with sufficient data.
    """
    models = []

    for window in [MealWindow.BREAKFAST, MealWindow.LUNCH, MealWindow.DINNER]:
        window_meals = [m for m in meal_history.meals if m.window == window]

        if len(window_meals) < MIN_MEALS_FOR_MODEL:
            continue

        hours = np.array([m.hour_of_day for m in window_meals])
        frequency = len(window_meals) / max(days_of_data, 0.1)

        # Only model if meal occurs frequently enough
        if frequency < MIN_FREQUENCY:
            continue

        models.append(MealTimingModel(
            window=window,
            mean_hour=float(np.mean(hours)),
            std_hour=float(np.std(hours)) if len(hours) > 1 else 1.0,
            frequency_per_day=frequency,
            days_observed=int(days_of_data),
            last_observed_hour=float(hours[-1]) if len(hours) > 0 else None,
        ))

    return models


def predict_next_meal(timing_models: List[MealTimingModel],
                      current_hour: float,
                      meal_history: MealHistory) -> Optional[MealPrediction]:
    """Predict when the next meal will occur.

    Compares current time to each window's mean timing. Selects the
    nearest upcoming meal that the patient eats regularly.

    The key insight: meal timing is highly regular for most patients.
    If someone eats breakfast at 7:30 ± 0.5h every day, we can
    predict it with high confidence and recommend eating_soon at 6:30-7:00.

    Args:
        timing_models: per-window models from build_timing_models.
        current_hour: current fractional hour of day (0-24).
        meal_history: for estimated carb sizes.

    Returns:
        MealPrediction or None if no reliable prediction can be made.
    """
    if not timing_models:
        return None

    best_prediction = None
    best_minutes_until = float('inf')

    for model in timing_models:
        # Minutes until this meal's mean time
        hours_until = model.mean_hour - current_hour
        if hours_until < -0.5:  # Meal already passed today
            hours_until += 24.0  # Next occurrence tomorrow
        minutes_until = hours_until * 60.0

        # Skip if meal is too far away (>6 hours) or already happening
        if minutes_until > 360.0 or minutes_until < -15.0:
            continue

        # Confidence based on:
        # 1. Timing regularity (low std = high confidence)
        # 2. Frequency (daily meals more predictable)
        # 3. Proximity (closer predictions more confident)
        regularity_conf = max(0, 1.0 - model.std_hour / 2.0)  # σ<1h → high
        frequency_conf = min(1.0, model.frequency_per_day / 0.8)  # daily → 1.0
        proximity_conf = max(0, 1.0 - abs(minutes_until) / 360.0)
        confidence = regularity_conf * 0.4 + frequency_conf * 0.4 + proximity_conf * 0.2

        # Should we recommend eating_soon?
        recommend = (EATING_SOON_LATE < minutes_until <= EATING_SOON_EARLY
                     and confidence > 0.3)

        # Estimated meal size from history
        window_meals = [m for m in meal_history.meals if m.window == model.window]
        est_carbs = float(np.mean([m.estimated_carbs_g for m in window_meals])) if window_meals else 30.0

        if minutes_until < best_minutes_until and minutes_until > 0:
            best_minutes_until = minutes_until
            rationale = (
                f"{model.window.value.capitalize()} typically at "
                f"{model.mean_hour:.1f}h (±{model.std_hour:.1f}h), "
                f"occurs {model.frequency_per_day:.1f}×/day. "
                f"{'Recommend pre-bolus now.' if recommend else ''}"
            )
            best_prediction = MealPrediction(
                predicted_window=model.window,
                predicted_hour=model.mean_hour,
                minutes_until=minutes_until,
                confidence=confidence,
                recommend_eating_soon=recommend,
                estimated_carbs_g=est_carbs,
                timing_models=timing_models,
                rationale=rationale,
            )

    return best_prediction
