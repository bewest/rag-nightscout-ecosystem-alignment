"""
meal_predictor.py — Predict upcoming meals from historical timing patterns.

Novel capability: analyzes 2+ weeks of detected meal timing to learn
per-window (breakfast/lunch/dinner) phase and frequency, then predicts
when the next meal will occur.

Clinical use case: recommend "eating soon" override 30-60 minutes before
predicted meal to allow pre-bolus insulin delivery, improving TIR.

Three prediction modes:
  1. **Gaussian** (cold start, <14 days): per-window N(μ_hour, σ_hour)
  2. **Proactive** (≥14 days, 15-feat union): AUC=0.846 without net_flux,
     ~17min lead time. Uses time + glucose + pre-meal window features.
  3. **Reactive** (≥14 days, 16-feat union+flux): AUC=0.942 with net_flux,
     confirms meals in progress within ~5min.

Dual-mode strategy (EXP-1121–1129):
  - Proactive model fires eating-soon 15-60 min before predicted meal
  - Reactive model confirms/cancels once meal flux detected
  - Combined gives best precision + lead time tradeoff

Algorithm:
  1. Build 16-feature vector: time (6) + instant glucose (3) +
     pre-meal window (6) + net_flux (1)
  2. Proactive: predict on features [0:15] (no net_flux), AUC=0.846
  3. Reactive: predict on features [0:16] (with net_flux), AUC=0.942
  4. Recommend eating_soon if proactive ≥ threshold and 15-60 min window
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
PROACTIVE_THRESHOLD_30 = 0.15  # Proactive: high sensitivity for eating-soon
PROACTIVE_THRESHOLD_60 = 0.12  # Proactive: lower bar for 60min window
REACTIVE_THRESHOLD = 0.76     # Reactive: high precision confirmation (EXP-1112)
ALERT_SUPPRESSION_MIN = 120.0  # Minimum minutes between eating-soon alerts
STEPS_PER_DAY = 288          # 5-min intervals per day
GLUCOSE_SCALE = 400.0        # Glucose normalization divisor

# 16-feature union model (EXP-1129)
ML_FEATURE_NAMES = [
    # Time features (6)
    'hour_sin', 'hour_cos', 'min_since_meal', 'meals_today',
    'dow', 'hist_meal_prob',
    # Instantaneous glucose (3)
    'gluc_trend_15', 'gluc_trend_30', 'glucose',
    # Pre-meal window features (6) — EXP-1125 breakthrough
    'window_gluc_mean', 'window_gluc_std', 'window_gluc_slope',
    'window_flatness', 'fasting_duration', 'iob_proxy',
    # Reactive (1)
    'net_flux',
]

# Feature index groups
_TIME_IDX = list(range(0, 6))
_GLUCOSE_IDX = list(range(6, 9))
_WINDOW_IDX = list(range(9, 15))
_PROACTIVE_IDX = list(range(0, 15))   # all except net_flux
_REACTIVE_IDX = list(range(0, 16))    # all features


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
    """Dual-mode gradient boosting model for meal timing prediction.

    16-feature union model (EXP-1129):
      - Proactive (15 features, no net_flux): AUC=0.846, ~17min lead
      - Reactive (16 features, with net_flux): AUC=0.942, ~5min lead

    Proactive mode fires eating-soon alerts 15-60 min ahead.
    Reactive mode confirms once meal flux is detected.
    """

    def __init__(self):
        self.clf_proactive_30 = None   # P(meal in 30 min) without net_flux
        self.clf_proactive_60 = None   # P(meal in 60 min) without net_flux
        self.clf_reactive_30 = None    # P(meal in 30 min) with net_flux
        self.clf_reactive_60 = None    # P(meal in 60 min) with net_flux
        self.hour_hist = np.zeros(24)
        self.trained = False
        self.n_meals = 0
        self.last_alert_step = -9999   # for alert suppression
        # Per-patient calibrated thresholds (EXP-1141)
        self.proactive_threshold_30 = PROACTIVE_THRESHOLD_30
        self.proactive_threshold_60 = PROACTIVE_THRESHOLD_60

    def train(self, meal_history: MealHistory,
              glucose: np.ndarray,
              net_flux: Optional[np.ndarray] = None,
              supply: Optional[np.ndarray] = None,
              days_of_data: float = 0.0) -> bool:
        """Train dual-mode meal prediction models.

        Args:
            meal_history: detected meals from meal_detector.
            glucose: (N,) glucose array at 5-min intervals.
            net_flux: (N,) metabolic net flux. Optional.
            supply: (N,) insulin supply signal for IOB proxy. Optional.
            days_of_data: total days of data.

        Returns:
            True if training succeeded.
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
        if supply is None:
            supply = np.zeros(N)

        meal_steps = sorted(set(m.index for m in meals))
        self.n_meals = len(meal_steps)

        # Next-meal distance for labels
        next_meal_dist = np.full(N, 9999, dtype=np.float32)
        for ms in reversed(meal_steps):
            for i in range(max(0, ms - STEPS_PER_DAY), ms):
                dist = (ms - i) * 5
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

        # Hour histogram from training portion
        split = int(N * 0.8)
        self.hour_hist = np.zeros(24)
        for m in meals:
            if m.index < split:
                h = int(m.hour_of_day) % 24
                self.hour_hist[h] += 1
        if self.hour_hist.sum() > 0:
            self.hour_hist = self.hour_hist / self.hour_hist.sum()

        # Build 16-feature matrix
        features = self._build_features(
            N, glucose, net_flux, supply, prev_meal_dist, meals_today)
        features = np.nan_to_num(features, nan=0.0, posinf=0.0, neginf=0.0)

        label_30 = (next_meal_dist <= 30).astype(int)
        label_60 = (next_meal_dist <= 60).astype(int)

        X_train = features[:split]
        y30 = label_30[:split]
        y60 = label_60[:split]

        if y30.sum() < 10 or y60.sum() < 10:
            return False

        gbt_params = dict(n_estimators=100, max_depth=4, learning_rate=0.1,
                          subsample=0.8, random_state=42)

        # Proactive models (15 features, no net_flux)
        X_pro = X_train[:, _PROACTIVE_IDX]
        self.clf_proactive_30 = GradientBoostingClassifier(**gbt_params)
        self.clf_proactive_30.fit(X_pro, y30)
        self.clf_proactive_60 = GradientBoostingClassifier(**gbt_params)
        self.clf_proactive_60.fit(X_pro, y60)

        # Reactive models (all 16 features)
        self.clf_reactive_30 = GradientBoostingClassifier(**gbt_params)
        self.clf_reactive_30.fit(X_train, y30)
        self.clf_reactive_60 = GradientBoostingClassifier(**gbt_params)
        self.clf_reactive_60.fit(X_train, y60)

        # Per-patient threshold calibration (EXP-1141)
        self._calibrate_thresholds(X_train, y30, y60)

        self.trained = True
        return True

    def _calibrate_thresholds(self, X_train: np.ndarray,
                              y30: np.ndarray, y60: np.ndarray,
                              target_max_alerts_per_day: float = 5.0,
                              ) -> None:
        """Sweep thresholds on training data to find per-patient optimum.

        Strategy from EXP-1141: find lowest threshold that yields
        ≤ target_max_alerts_per_day. If no threshold achieves this,
        pick the threshold with highest PPV.

        Args:
            X_train: training feature matrix.
            y30: 30-min labels.
            y60: 60-min labels.
            target_max_alerts_per_day: max acceptable alerts/day.
        """
        n_steps = len(X_train)
        n_days = max(n_steps / STEPS_PER_DAY, 1.0)
        X_pro = X_train[:, _PROACTIVE_IDX]

        for horizon, y_true, attr in [
            (30, y30, 'proactive_threshold_30'),
            (60, y60, 'proactive_threshold_60'),
        ]:
            clf = (self.clf_proactive_30 if horizon == 30
                   else self.clf_proactive_60)
            scores = clf.predict_proba(X_pro)[:, 1]

            best_thresh = getattr(self, attr)  # fallback to default
            best_ppv = 0.0

            for thresh_int in range(5, 96, 5):
                thresh = thresh_int / 100.0
                alerts = scores >= thresh
                n_alerts = int(alerts.sum())
                alerts_per_day = n_alerts / n_days

                if n_alerts == 0:
                    continue

                tp = int((alerts & (y_true == 1)).sum())
                ppv = tp / n_alerts

                # Pick lowest threshold with ≤ target alerts/day
                if alerts_per_day <= target_max_alerts_per_day:
                    if ppv > best_ppv or (ppv == best_ppv
                                          and thresh < best_thresh):
                        best_thresh = thresh
                        best_ppv = ppv
                    break  # lowest threshold that satisfies constraint

            # If nothing met the constraint, use highest-PPV threshold
            if best_ppv == 0.0:
                for thresh_int in range(95, 4, -5):
                    thresh = thresh_int / 100.0
                    alerts = scores >= thresh
                    n_alerts = int(alerts.sum())
                    if n_alerts == 0:
                        continue
                    tp = int((alerts & (y_true == 1)).sum())
                    ppv = tp / n_alerts
                    if ppv > best_ppv:
                        best_ppv = ppv
                        best_thresh = thresh

            setattr(self, attr, best_thresh)

    def _build_features(self, N: int, glucose: np.ndarray,
                        net_flux: np.ndarray, supply: np.ndarray,
                        prev_meal_dist: np.ndarray,
                        meals_today: np.ndarray) -> np.ndarray:
        """Build 16-feature matrix for all timesteps."""
        features = np.zeros((N, 16))
        for i in range(N):
            hour = (i % STEPS_PER_DAY) * 5.0 / 60.0

            # Time features (6)
            features[i, 0] = np.sin(2 * np.pi * hour / 24)
            features[i, 1] = np.cos(2 * np.pi * hour / 24)
            features[i, 2] = prev_meal_dist[i]
            features[i, 3] = meals_today[i]
            features[i, 4] = (i // STEPS_PER_DAY) % 7
            features[i, 5] = self.hour_hist[int(hour) % 24]

            # Instantaneous glucose (3)
            if i >= 3:
                features[i, 6] = glucose[i] - glucose[i - 3]  # trend_15
            if i >= 6:
                features[i, 7] = glucose[i] - glucose[i - 6]  # trend_30
            features[i, 8] = glucose[i] / GLUCOSE_SCALE

            # Pre-meal window features (6) — 60 min lookback
            window_start = max(0, i - 12)
            gluc_window = np.nan_to_num(
                glucose[window_start:i + 1], nan=0.0)
            if len(gluc_window) >= 3:
                features[i, 9] = np.mean(gluc_window) / GLUCOSE_SCALE
                features[i, 10] = np.std(gluc_window)
                try:
                    coeffs = np.polyfit(
                        np.arange(len(gluc_window)), gluc_window, 1)
                    features[i, 11] = (coeffs[0]
                                       if np.isfinite(coeffs[0]) else 0.0)
                except (np.linalg.LinAlgError, ValueError):
                    features[i, 11] = 0.0
                std_val = max(features[i, 10], 0.1)
                features[i, 12] = min(1.0 / std_val, 100.0)  # flatness

                # Fasting duration
                mean_g = np.mean(np.nan_to_num(
                    glucose[max(0, i - STEPS_PER_DAY):i + 1], nan=0.0))
                fasting = 0
                for j in range(i, max(0, i - STEPS_PER_DAY), -1):
                    if not np.isnan(glucose[j]) and glucose[j] > mean_g + 15:
                        break
                    fasting += 1
                features[i, 13] = fasting * 5.0 / 60.0  # hours

                # IOB proxy: sum of supply in window
                sup_window = supply[window_start:i + 1]
                features[i, 14] = np.sum(
                    np.nan_to_num(sup_window, nan=0.0))

            # Net flux (reactive feature)
            features[i, 15] = net_flux[i] if i < len(net_flux) else 0

        return features

    def predict_proba(self, hour: float,
                      minutes_since_last_meal: float,
                      meals_today_count: int,
                      glucose_current: float,
                      glucose_15min_ago: float,
                      glucose_30min_ago: float,
                      net_flux_current: float = 0.0,
                      day_index: int = 0,
                      glucose_window: Optional[np.ndarray] = None,
                      supply_window: Optional[np.ndarray] = None,
                      fasting_hours: float = 0.0,
                      mode: str = 'dual',
                      ) -> Dict[str, float]:
        """Predict meal probability in proactive and/or reactive modes.

        Args:
            hour: current fractional hour (0-24).
            minutes_since_last_meal: minutes since last detected meal.
            meals_today_count: meals so far today.
            glucose_current: current glucose (mg/dL).
            glucose_15min_ago: glucose 15 min ago.
            glucose_30min_ago: glucose 30 min ago.
            net_flux_current: metabolic net flux at current step.
            day_index: day index for day-of-week feature.
            glucose_window: last 13 glucose readings (60 min) for window
                features. If None, uses instant glucose as proxy.
            supply_window: last 13 supply readings for IOB proxy.
            fasting_hours: hours since glucose was elevated.
            mode: 'proactive', 'reactive', or 'dual' (both).

        Returns:
            Dict with keys: proactive_30, proactive_60, reactive_30,
            reactive_60 (depending on mode).
        """
        if not self.trained:
            return {'proactive_30': 0.0, 'proactive_60': 0.0,
                    'reactive_30': 0.0, 'reactive_60': 0.0}

        # Build window features
        if glucose_window is not None and len(glucose_window) >= 3:
            gw = np.nan_to_num(glucose_window, nan=0.0)
            w_mean = np.mean(gw) / GLUCOSE_SCALE
            w_std = np.std(gw)
            try:
                coeffs = np.polyfit(np.arange(len(gw)), gw, 1)
                w_slope = coeffs[0] if np.isfinite(coeffs[0]) else 0.0
            except (np.linalg.LinAlgError, ValueError):
                w_slope = 0.0
            w_flat = min(1.0 / max(w_std, 0.1), 100.0)
        else:
            w_mean = glucose_current / GLUCOSE_SCALE
            w_std = 0.0
            w_slope = 0.0
            w_flat = 100.0

        iob_proxy = 0.0
        if supply_window is not None:
            iob_proxy = float(np.sum(
                np.nan_to_num(supply_window, nan=0.0)))

        h_idx = int(hour) % 24

        # Full 16-feature vector
        feat = np.array([[
            np.sin(2 * np.pi * hour / 24),    # 0
            np.cos(2 * np.pi * hour / 24),     # 1
            minutes_since_last_meal,           # 2
            meals_today_count,                 # 3
            day_index % 7,                     # 4
            self.hour_hist[h_idx],             # 5
            glucose_current - glucose_15min_ago,   # 6
            glucose_current - glucose_30min_ago,   # 7
            glucose_current / GLUCOSE_SCALE,       # 8
            w_mean,                            # 9
            w_std,                             # 10
            w_slope,                           # 11
            w_flat,                            # 12
            fasting_hours,                     # 13
            iob_proxy,                         # 14
            net_flux_current,                  # 15
        ]])
        feat = np.nan_to_num(feat, nan=0.0, posinf=0.0, neginf=0.0)

        result = {}
        if mode in ('proactive', 'dual'):
            feat_pro = feat[:, _PROACTIVE_IDX]
            result['proactive_30'] = float(
                self.clf_proactive_30.predict_proba(feat_pro)[0, 1])
            result['proactive_60'] = float(
                self.clf_proactive_60.predict_proba(feat_pro)[0, 1])

        if mode in ('reactive', 'dual'):
            result['reactive_30'] = float(
                self.clf_reactive_30.predict_proba(feat)[0, 1])
            result['reactive_60'] = float(
                self.clf_reactive_60.predict_proba(feat)[0, 1])

        return result

    def feature_importance(self) -> Dict[str, Dict[str, float]]:
        """Return feature importances for both proactive and reactive."""
        if not self.trained:
            return {}
        pro_names = [ML_FEATURE_NAMES[i] for i in _PROACTIVE_IDX]
        return {
            'proactive': dict(zip(
                pro_names,
                [float(x) for x in self.clf_proactive_30.feature_importances_])),
            'reactive': dict(zip(
                ML_FEATURE_NAMES,
                [float(x) for x in self.clf_reactive_30.feature_importances_])),
        }


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
                      glucose_window: Optional[np.ndarray] = None,
                      supply_window: Optional[np.ndarray] = None,
                      fasting_hours: float = 0.0,
                      current_step: int = 0,
                      ) -> Optional[MealPrediction]:
    """Predict when the next meal will occur with dual-mode ML.

    Dual-mode strategy (EXP-1121–1129):
      - Proactive model (AUC=0.846): predicts without net_flux, ~17min lead
      - Reactive model (AUC=0.942): confirms with net_flux, ~5min lead
      - Eating-soon recommended when proactive fires within 15-60 min window

    Falls back to Gaussian timing for cold start (<14 days).

    Args:
        timing_models: per-window models from build_timing_models.
        current_hour: current fractional hour of day (0-24).
        meal_history: for estimated carb sizes.
        ml_model: trained MealMLModel (optional).
        glucose_current: current glucose (mg/dL).
        glucose_15min_ago: glucose 15 min ago.
        glucose_30min_ago: glucose 30 min ago.
        minutes_since_last_meal: time since last detected meal.
        meals_today_count: meals so far today.
        net_flux_current: current metabolic net flux.
        day_index: day index for day-of-week feature.
        glucose_window: last 13 glucose readings (60 min) for window features.
        supply_window: last 13 supply readings for IOB proxy.
        fasting_hours: hours since glucose was elevated.
        current_step: current timestep index for alert suppression.

    Returns:
        MealPrediction or None if no reliable prediction can be made.
    """
    if not timing_models:
        return None

    # ML prediction (dual-mode)
    ml_scores = {}
    proactive_recommend = False
    reactive_confirm = False
    prediction_mode = 'gaussian'

    if ml_model is not None and ml_model.trained:
        ml_scores = ml_model.predict_proba(
            hour=current_hour,
            minutes_since_last_meal=minutes_since_last_meal,
            meals_today_count=meals_today_count,
            glucose_current=glucose_current,
            glucose_15min_ago=glucose_15min_ago,
            glucose_30min_ago=glucose_30min_ago,
            net_flux_current=net_flux_current,
            day_index=day_index,
            glucose_window=glucose_window,
            supply_window=supply_window,
            fasting_hours=fasting_hours,
            mode='dual',
        )

        # Check alert suppression
        steps_since_alert = current_step - ml_model.last_alert_step
        suppressed = (steps_since_alert * 5) < ALERT_SUPPRESSION_MIN

        p_pro_30 = ml_scores.get('proactive_30', 0.0)
        p_pro_60 = ml_scores.get('proactive_60', 0.0)
        p_react_30 = ml_scores.get('reactive_30', 0.0)

        # Use per-patient calibrated thresholds (EXP-1141)
        thresh_30 = ml_model.proactive_threshold_30
        thresh_60 = ml_model.proactive_threshold_60

        proactive_recommend = (
            (p_pro_30 >= thresh_30
             or p_pro_60 >= thresh_60)
            and not suppressed
        )
        reactive_confirm = p_react_30 >= REACTIVE_THRESHOLD

        if proactive_recommend and reactive_confirm:
            prediction_mode = 'dual'
        elif proactive_recommend:
            prediction_mode = 'proactive'
        elif reactive_confirm:
            prediction_mode = 'reactive'
        else:
            prediction_mode = 'ml_inactive'

    best_prediction = None
    best_minutes_until = float('inf')

    for model in timing_models:
        hours_until = model.mean_hour - current_hour
        if hours_until < -0.5:
            hours_until += 24.0
        minutes_until = hours_until * 60.0

        if minutes_until > 360.0 or minutes_until < -15.0:
            continue

        # Confidence blending
        regularity_conf = max(0, 1.0 - model.std_hour / 2.0)
        frequency_conf = min(1.0, model.frequency_per_day / 0.8)
        proximity_conf = max(0, 1.0 - abs(minutes_until) / 360.0)
        gaussian_conf = (regularity_conf * 0.4
                         + frequency_conf * 0.4
                         + proximity_conf * 0.2)

        p_pro_30 = ml_scores.get('proactive_30', 0.0)
        p_pro_60 = ml_scores.get('proactive_60', 0.0)
        p_react_30 = ml_scores.get('reactive_30', 0.0)

        if ml_model is not None and ml_model.trained:
            ml_conf = max(p_pro_30, p_pro_60)
            confidence = 0.7 * ml_conf + 0.3 * gaussian_conf
        else:
            confidence = gaussian_conf

        # Eating-soon recommendation
        in_window = EATING_SOON_LATE < minutes_until <= EATING_SOON_EARLY
        if ml_model is not None and ml_model.trained:
            recommend = proactive_recommend and in_window
        else:
            recommend = in_window and confidence > 0.3

        # Track alert for suppression
        if recommend and ml_model is not None:
            ml_model.last_alert_step = current_step

        # Estimated meal size
        window_meals = [m for m in meal_history.meals if m.window == model.window]
        est_carbs = (float(np.mean([m.estimated_carbs_g for m in window_meals]))
                     if window_meals else 30.0)

        if minutes_until < best_minutes_until and minutes_until > 0:
            best_minutes_until = minutes_until

            if ml_model is not None and ml_model.trained:
                rationale = (
                    f"{model.window.value.capitalize()} typically at "
                    f"{model.mean_hour:.1f}h (±{model.std_hour:.1f}h). "
                    f"Proactive: P(30m)={p_pro_30:.0%}, P(60m)={p_pro_60:.0%}. "
                    f"Reactive: P(30m)={p_react_30:.0%}. "
                    f"Mode: {prediction_mode}. "
                    f"{'Recommend eating-soon override.' if recommend else ''}"
                )
            else:
                rationale = (
                    f"{model.window.value.capitalize()} typically at "
                    f"{model.mean_hour:.1f}h (±{model.std_hour:.1f}h), "
                    f"occurs {model.frequency_per_day:.1f}×/day. "
                    f"{'Recommend eating-soon override.' if recommend else ''}"
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
                proactive_score=max(p_pro_30, p_pro_60),
                reactive_score=p_react_30,
                prediction_mode=prediction_mode,
            )

    return best_prediction
