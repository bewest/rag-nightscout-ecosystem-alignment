"""Hypo early warning system based on glucose trajectory features.

Provides 30-minute hypo risk score (probability of glucose < 70 mg/dL
within 30 minutes) using logistic regression on trajectory features.

EXP-2539: GBM AUC=0.904, LogReg AUC=0.883. Uses LogReg for simplicity
and interpretability in production.

Feature importances from EXP-2539:
  - Glucose level: 81% (dominant)
  - Rate of change: 11%
  - Other trajectory features: 8%
"""

from __future__ import annotations

import math
from typing import List, Optional, Tuple

import numpy as np

from .types import HypoRiskResult


# ── Population-fitted logistic regression coefficients ────────────────
# Calibrated via least-squares fit on 5 clinical anchor points:
#   sgv=150 flat → 0.01, sgv=100 flat → 0.10, sgv=90 fall@-2 → 0.30,
#   sgv=80 fall@-3 → 0.70, sgv=70 fall@-2 → 0.90
#
# Features: [intercept, current_sgv, roc_15min, acceleration_30min,
#            min_glucose_30min, count_below_100_60min]

INTERCEPT = 2.3792
COEFF_SGV = -0.0234          # lower glucose → higher risk (dominant)
COEFF_ROC = -0.0865          # more negative ROC → higher risk
COEFF_ACCELERATION = -0.05   # accelerating descent → higher risk
COEFF_MIN30 = -0.0234        # lower recent minimum → higher risk
COEFF_BELOW100 = 0.2414      # more time near hypo range → higher risk

# Feature names for dominant-factor reporting
_FEATURE_NAMES = {
    'sgv': 'glucose_level',
    'roc': 'rate_of_change',
    'acc': 'acceleration',
    'min30': 'recent_minimum',
    'below100': 'time_near_hypo',
}

# Risk level thresholds
_RISK_THRESHOLDS = [
    (0.6, 'critical'),
    (0.3, 'high'),
    (0.1, 'moderate'),
    (0.0, 'low'),
]

# Recommended actions by risk level
_ACTIONS = {
    'low': 'No action needed — glucose trajectory is stable.',
    'moderate': 'Monitor glucose closely over the next 30 minutes.',
    'high': 'Consider fast-acting carbs (15g). Recheck in 15 minutes.',
    'critical': 'Treat impending hypo now: ingest 15–20g fast-acting carbs.',
}

# Minimum readings required for a reliable estimate
MIN_READINGS = 3


def _sigmoid(x: float) -> float:
    """Numerically stable logistic sigmoid."""
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    ez = math.exp(x)
    return ez / (1.0 + ez)


def _linear_slope(values: List[float]) -> float:
    """Slope of least-squares linear fit (units per step)."""
    n = len(values)
    if n < 2:
        return 0.0
    x = np.arange(n, dtype=float)
    y = np.array(values, dtype=float)
    x_mean = x.mean()
    y_mean = y.mean()
    denom = float(np.sum((x - x_mean) ** 2))
    if denom == 0:
        return 0.0
    return float(np.sum((x - x_mean) * (y - y_mean)) / denom)


def compute_features(sgv_history: List[float]) -> dict:
    """Extract trajectory features from glucose history.

    Args:
        sgv_history: Last 12 glucose readings (60 min at 5-min intervals,
                     most recent last). Fewer readings accepted with
                     degraded accuracy.

    Returns:
        Dict with keys: sgv, roc, acc, min30, below100
    """
    n = len(sgv_history)

    # Current glucose
    sgv = sgv_history[-1]

    # Rate of change: slope over last 3 readings (15 min)
    roc_window = sgv_history[-min(3, n):]
    roc = _linear_slope(roc_window)

    # Acceleration: change in rate over last 6 readings (30 min)
    acc = 0.0
    if n >= 6:
        first_half = sgv_history[-6:-3]
        second_half = sgv_history[-3:]
        roc_early = _linear_slope(first_half)
        roc_late = _linear_slope(second_half)
        acc = roc_late - roc_early
    elif n >= 4:
        mid = n // 2
        roc_early = _linear_slope(sgv_history[:mid])
        roc_late = _linear_slope(sgv_history[mid:])
        acc = roc_late - roc_early

    # Minimum glucose in last 30 min (last 6 readings)
    min30_window = sgv_history[-min(6, n):]
    min30 = min(min30_window)

    # Count of readings below 100 in last 60 min (all 12 readings)
    below100 = sum(1 for v in sgv_history if v < 100.0)

    return {
        'sgv': sgv,
        'roc': roc,
        'acc': acc,
        'min30': min30,
        'below100': below100,
    }


def _dominant_factor(features: dict) -> str:
    """Identify which feature contributes most to the risk score."""
    # Compute absolute contribution of each feature
    # (relative to a neutral baseline of sgv=120, flat, min30=120, below100=0)
    contributions = {
        'sgv': abs(COEFF_SGV * (features['sgv'] - 120.0)),
        'roc': abs(COEFF_ROC * features['roc']),
        'acc': abs(COEFF_ACCELERATION * features['acc']),
        'min30': abs(COEFF_MIN30 * (features['min30'] - 120.0)),
        'below100': abs(COEFF_BELOW100 * features['below100']),
    }
    top = max(contributions, key=contributions.get)
    return _FEATURE_NAMES[top]


def compute_hypo_risk(
    sgv_history: List[float],
    timestamps: Optional[List] = None,
) -> HypoRiskResult:
    """Compute 30-minute hypo risk from glucose trajectory.

    Args:
        sgv_history: Last 12 glucose readings (60 min at 5-min intervals,
                     most recent last). Minimum 3 readings required.
        timestamps: Optional list of timestamps (currently unused;
                    reserved for irregular-interval support).

    Returns:
        HypoRiskResult with risk_score, risk_level, and action guidance.

    Raises:
        ValueError: If fewer than MIN_READINGS glucose values provided
                    or if input contains only NaN values.
    """
    if not sgv_history or len(sgv_history) < MIN_READINGS:
        raise ValueError(
            f"Need at least {MIN_READINGS} glucose readings, "
            f"got {len(sgv_history) if sgv_history else 0}"
        )

    # Filter NaN values
    clean = [v for v in sgv_history if not math.isnan(v)]
    if len(clean) < MIN_READINGS:
        raise ValueError(
            f"Need at least {MIN_READINGS} non-NaN glucose readings, "
            f"got {len(clean)}"
        )

    features = compute_features(clean)

    # Logistic regression: logit = b0 + b1*sgv + b2*roc + ...
    logit = (
        INTERCEPT
        + COEFF_SGV * features['sgv']
        + COEFF_ROC * features['roc']
        + COEFF_ACCELERATION * features['acc']
        + COEFF_MIN30 * features['min30']
        + COEFF_BELOW100 * features['below100']
    )

    risk_score = _sigmoid(logit)

    # Classify risk level
    risk_level = 'low'
    for threshold, level in _RISK_THRESHOLDS:
        if risk_score >= threshold:
            risk_level = level
            break

    return HypoRiskResult(
        risk_score=risk_score,
        risk_level=risk_level,
        lead_time_minutes=30,
        dominant_factor=_dominant_factor(features),
        recommended_action=_ACTIONS[risk_level],
    )
