"""
meal_predictor.py — Predict upcoming meals from historical timing patterns.

Novel capability: analyzes 2+ weeks of detected meal timing to learn
per-window (breakfast/lunch/dinner) phase and frequency, then predicts
when the next meal will occur.

Clinical use case: recommend "eating soon" override 30-60 minutes before
predicted meal to allow pre-bolus insulin delivery, improving TIR.

Two prediction modes:
  1. **Gaussian** (cold start, <14 days): per-window N(μ_hour, σ_hour)
  2. **ML** (warm, ≥14 days): GradientBoosting on time + glucose + physics
     features — AUC=0.861 @30min across 11 patients (EXP-1106).

Algorithm (ML mode, EXP-1106):
  1. Build feature vector: hour sin/cos, time-since-last-meal, meals-today,
     glucose, 15/30-min glucose trend, metabolic net flux, hour histogram
  2. Predict P(meal in next 30/60 min) via gradient boosting
  3. Recommend eating_soon if P ≥ threshold and 15-60 min before predicted meal
  4. Personalized models win 10/11 patients (EXP-1109)
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np

from .types import (
    MealHistory, MealPrediction, MealTimingModel, MealWindow,
)


# Recommendation window (minutes before predicted meal to suggest eating_soon)
EATING_SOON_EARLY = 60.0     # Start recommending 60 min before
EATING_SOON_LATE = 15.0      # Stop recommending 15 min before (too late)
MIN_MEALS_FOR_MODEL = 3      # Minimum meals in a window to build timing model
MIN_DAYS_FOR_PREDICTION = 7  # Minimum days of data for predictions
MIN_DAYS_FOR_ML = 14         # Minimum days for ML model (EXP-1113)
MIN_FREQUENCY = 0.3          # Must occur ≥30% of days to predict
ML_THRESHOLD_30 = 0.30       # P(meal in 30min) threshold for alert
ML_THRESHOLD_60 = 0.25       # P(meal in 60min) threshold for alert
STEPS_PER_DAY = 288          # 5-min intervals per day

# Feature names matching EXP-1106
ML_FEATURE_NAMES = [
    'hour_sin', 'hour_cos', 'min_since_meal', 'meals_today',
    'dow', 'gluc_trend_15', 'gluc_trend_30', 'glucose',
    'net_flux', 'hist_meal_prob',
]


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


# ── ML Model Training (EXP-1106) ─────────────────────────────────────

class MealMLModel:
    """Gradient boosting model for meal timing prediction.

    Trained per-patient on physics-detected meal events (EXP-1106).
    AUC=0.861 @30min, personal wins 10/11 patients (EXP-1109).
    """

    def __init__(self):
        self.clf_30 = None   # P(meal in 30 min)
        self.clf_60 = None   # P(meal in 60 min)
        self.hour_hist = np.zeros(24)
        self.trained = False
        self.n_meals = 0
        self.train_auc_30 = 0.0

    def train(self, meal_history: MealHistory,
              glucose: np.ndarray,
              net_flux: Optional[np.ndarray] = None,
              days_of_data: float = 0.0) -> bool:
        """Train the meal prediction model on detected meal history.

        Args:
            meal_history: detected meals from meal_detector.
            glucose: (N,) glucose array at 5-min intervals.
            net_flux: (N,) metabolic net flux (supply - demand). Optional.
            days_of_data: total days of data.

        Returns:
            True if training succeeded, False if insufficient data.
        """
        try:
            from sklearn.ensemble import GradientBoostingClassifier
        except ImportError:
            return False

        meals = meal_history.meals
        if len(meals) < 20 or days_of_data < MIN_DAYS_FOR_ML:
            return False

        N = len(glucose)
        if net_flux is None:
            net_flux = np.zeros(N)

        # Build meal step lookup from DetectedMeal objects
        meal_steps = sorted(set(m.index for m in meals))
        self.n_meals = len(meal_steps)

        # Next-meal distance for every timestep
        next_meal_dist = np.full(N, 9999, dtype=np.float32)
        for ms in reversed(meal_steps):
            for i in range(max(0, ms - STEPS_PER_DAY), ms):
                dist = (ms - i) * 5  # minutes
                if dist < next_meal_dist[i]:
                    next_meal_dist[i] = dist

        # Previous meal distance
        prev_meal_dist = np.full(N, 9999, dtype=np.float32)
        for ms in meal_steps:
            for i in range(ms, min(N, ms + STEPS_PER_DAY)):
                dist = (i - ms) * 5
                if dist < prev_meal_dist[i]:
                    prev_meal_dist[i] = dist

        # Meals so far today
        meals_today = np.zeros(N)
        meal_set = set(meal_steps)
        current_day = -1
        count = 0
        for i in range(N):
            day = i // STEPS_PER_DAY
            if day != current_day:
                current_day = day
                count = 0
            if i in meal_set:
                count += 1
            meals_today[i] = count

        # Hour histogram from training portion (first 80%)
        split = int(N * 0.8)
        self.hour_hist = np.zeros(24)
        for m in meals:
            if m.index < split:
                h = int(m.hour_of_day) % 24
                self.hour_hist[h] += 1
        if self.hour_hist.sum() > 0:
            self.hour_hist = self.hour_hist / self.hour_hist.sum()

        # Feature matrix
        features = np.zeros((N, 10))
        for i in range(N):
            hour = (i % STEPS_PER_DAY) * 5.0 / 60.0
            features[i, 0] = np.sin(2 * np.pi * hour / 24)
            features[i, 1] = np.cos(2 * np.pi * hour / 24)
            features[i, 2] = prev_meal_dist[i]
            features[i, 3] = meals_today[i]
            features[i, 4] = (i // STEPS_PER_DAY) % 7
            if i >= 3:
                features[i, 5] = glucose[i] - glucose[i - 3]
            if i >= 6:
                features[i, 6] = glucose[i] - glucose[i - 6]
            features[i, 7] = glucose[i] / 400.0
            features[i, 8] = net_flux[i] if i < len(net_flux) else 0
            h_idx = int(hour) % 24
            features[i, 9] = self.hour_hist[h_idx]

        features = np.nan_to_num(features, nan=0.0, posinf=0.0, neginf=0.0)

        # Labels
        label_30 = (next_meal_dist <= 30).astype(int)
        label_60 = (next_meal_dist <= 60).astype(int)

        X_train = features[:split]
        y30_train = label_30[:split]
        y60_train = label_60[:split]

        if y30_train.sum() < 10 or y60_train.sum() < 10:
            return False

        # Train GBT classifiers (matching EXP-1106 hyperparameters)
        self.clf_30 = GradientBoostingClassifier(
            n_estimators=100, max_depth=4, learning_rate=0.1,
            subsample=0.8, random_state=42)
        self.clf_30.fit(X_train, y30_train)

        self.clf_60 = GradientBoostingClassifier(
            n_estimators=100, max_depth=4, learning_rate=0.1,
            subsample=0.8, random_state=42)
        self.clf_60.fit(X_train, y60_train)

        self.trained = True
        return True

    def predict_proba(self, hour: float,
                      minutes_since_last_meal: float,
                      meals_today_count: int,
                      glucose_current: float,
                      glucose_15min_ago: float,
                      glucose_30min_ago: float,
                      net_flux_current: float = 0.0,
                      day_index: int = 0) -> Tuple[float, float]:
        """Predict probability of meal in next 30 and 60 minutes.

        Args:
            hour: current fractional hour (0-24).
            minutes_since_last_meal: minutes since last detected meal.
            meals_today_count: number of meals so far today.
            glucose_current: current glucose (mg/dL).
            glucose_15min_ago: glucose 15 min ago (mg/dL).
            glucose_30min_ago: glucose 30 min ago (mg/dL).
            net_flux_current: metabolic net flux at current step.
            day_index: day index for day-of-week feature.

        Returns:
            (p_30min, p_60min) probabilities.
        """
        if not self.trained:
            return (0.0, 0.0)

        h_idx = int(hour) % 24
        features = np.array([[
            np.sin(2 * np.pi * hour / 24),
            np.cos(2 * np.pi * hour / 24),
            minutes_since_last_meal,
            meals_today_count,
            day_index % 7,
            glucose_current - glucose_15min_ago,
            glucose_current - glucose_30min_ago,
            glucose_current / 400.0,
            net_flux_current,
            self.hour_hist[h_idx],
        ]])

        features = np.nan_to_num(features, nan=0.0, posinf=0.0, neginf=0.0)

        p30 = float(self.clf_30.predict_proba(features)[0, 1])
        p60 = float(self.clf_60.predict_proba(features)[0, 1])
        return (p30, p60)

    def feature_importance(self) -> Dict[str, float]:
        """Return feature importances from the 30-min model."""
        if not self.trained:
            return {}
        return dict(zip(ML_FEATURE_NAMES,
                        [float(x) for x in self.clf_30.feature_importances_]))


# ── Prediction Functions ──────────────────────────────────────────────

def predict_next_meal(timing_models: List[MealTimingModel],
                      current_hour: float,
                      meal_history: MealHistory,
                      ml_model: Optional[MealMLModel] = None,
                      glucose_current: float = 0.0,
                      glucose_15min_ago: float = 0.0,
                      glucose_30min_ago: float = 0.0,
                      minutes_since_last_meal: float = 9999.0,
                      meals_today_count: int = 0,
                      net_flux_current: float = 0.0,
                      day_index: int = 0,
                      ) -> Optional[MealPrediction]:
    """Predict when the next meal will occur.

    Uses ML model if available (AUC=0.861), falls back to Gaussian.

    Args:
        timing_models: per-window models from build_timing_models.
        current_hour: current fractional hour of day (0-24).
        meal_history: for estimated carb sizes.
        ml_model: trained MealMLModel (optional, for ML prediction).
        glucose_current: current glucose (mg/dL).
        glucose_15min_ago: glucose 15 min ago.
        glucose_30min_ago: glucose 30 min ago.
        minutes_since_last_meal: time since last detected meal.
        meals_today_count: meals so far today.
        net_flux_current: current metabolic net flux.
        day_index: day index for day-of-week feature.

    Returns:
        MealPrediction or None if no reliable prediction can be made.
    """
    if not timing_models:
        return None

    # Try ML prediction first (EXP-1106: AUC=0.861)
    ml_confidence = 0.0
    ml_recommend = False
    if ml_model is not None and ml_model.trained:
        p30, p60 = ml_model.predict_proba(
            hour=current_hour,
            minutes_since_last_meal=minutes_since_last_meal,
            meals_today_count=meals_today_count,
            glucose_current=glucose_current,
            glucose_15min_ago=glucose_15min_ago,
            glucose_30min_ago=glucose_30min_ago,
            net_flux_current=net_flux_current,
            day_index=day_index,
        )
        ml_confidence = max(p30, p60)
        ml_recommend = p30 >= ML_THRESHOLD_30 or p60 >= ML_THRESHOLD_60

    best_prediction = None
    best_minutes_until = float('inf')

    for model in timing_models:
        # Minutes until this meal's mean time
        hours_until = model.mean_hour - current_hour
        if hours_until < -0.5:
            hours_until += 24.0
        minutes_until = hours_until * 60.0

        if minutes_until > 360.0 or minutes_until < -15.0:
            continue

        # Confidence: blend Gaussian and ML when available
        regularity_conf = max(0, 1.0 - model.std_hour / 2.0)
        frequency_conf = min(1.0, model.frequency_per_day / 0.8)
        proximity_conf = max(0, 1.0 - abs(minutes_until) / 360.0)
        gaussian_conf = (regularity_conf * 0.4
                         + frequency_conf * 0.4
                         + proximity_conf * 0.2)

        if ml_model is not None and ml_model.trained:
            # Blend: 70% ML, 30% Gaussian (ML is stronger per EXP-1118)
            confidence = 0.7 * ml_confidence + 0.3 * gaussian_conf
        else:
            confidence = gaussian_conf

        # Eating-soon recommendation
        in_window = EATING_SOON_LATE < minutes_until <= EATING_SOON_EARLY
        if ml_model is not None and ml_model.trained:
            recommend = ml_recommend and in_window
        else:
            recommend = in_window and confidence > 0.3

        # Estimated meal size from history
        window_meals = [m for m in meal_history.meals if m.window == model.window]
        est_carbs = (float(np.mean([m.estimated_carbs_g for m in window_meals]))
                     if window_meals else 30.0)

        if minutes_until < best_minutes_until and minutes_until > 0:
            best_minutes_until = minutes_until

            if ml_model is not None and ml_model.trained:
                rationale = (
                    f"{model.window.value.capitalize()} typically at "
                    f"{model.mean_hour:.1f}h (±{model.std_hour:.1f}h). "
                    f"ML: P(30min)={p30:.0%}, P(60min)={p60:.0%}. "
                    f"{'Recommend pre-bolus now.' if recommend else ''}"
                )
            else:
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
