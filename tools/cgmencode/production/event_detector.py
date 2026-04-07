"""
event_detector.py — XGBoost risk classification and event detection.

Research basis: EXP-682 (adaptive spike thresholds), EXP-685 (AID-aware rules),
               EXP-692 (hypo prediction), event_classifier.py (XGBoost training)

SOTA metrics (validated):
  - 2h HIGH AUC: 0.907 (combined_43 feature set)
  - 2h HYPO AUC: 0.860
  - Weighted F1: 0.710

Feature set (43 features = combined_43):
  - BG statistics: current, Δ5, Δ15, Δ30, mean/std at 30/60/120 windows
  - Metabolic flux: supply, demand, net, ratio, product, hepatic
  - Insulin: IOB, recent bolus, basal deviation
  - Carbs: COB, recent carbs, time since meal
  - Temporal: hour sin/cos, time since last event
  - Physics: residual magnitude, flux imbalance
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

import numpy as np

from .types import EventType, MetabolicState, RiskAssessment


# XGBoost optimal parameters (from event_classifier.py research)
DEFAULT_XGB_PARAMS = {
    'n_estimators': 300,
    'max_depth': 6,
    'learning_rate': 0.03,
    'objective': 'multi:softprob',
    'tree_method': 'hist',
    'eval_metric': 'mlogloss',
    'use_label_encoder': False,
}

# Feature names for the combined_43 set
FEATURE_NAMES = [
    'bg_current', 'bg_delta_5', 'bg_delta_15', 'bg_delta_30',
    'bg_mean_30', 'bg_std_30', 'bg_mean_60', 'bg_std_60',
    'bg_mean_120', 'bg_std_120', 'bg_min_60', 'bg_max_60',
    'bg_min_120', 'bg_max_120', 'bg_range_60',
    'iob_current', 'bolus_recent_30', 'bolus_recent_60',
    'basal_deviation', 'cob_current', 'carbs_recent_30',
    'carbs_recent_60', 'time_since_meal',
    'supply', 'demand', 'net_flux', 'ratio', 'product', 'hepatic',
    'residual_mag', 'flux_imbalance',
    'hour_sin', 'hour_cos',
    'bg_acceleration', 'bg_jerk',
    'supply_demand_cross', 'residual_trend_30',
    'iob_x_bg', 'cob_x_bg', 'net_flux_x_delta',
    'tir_recent_60', 'tbr_recent_60', 'tar_recent_60',
]


def build_features(glucose: np.ndarray,
                   metabolic: Optional[MetabolicState],
                   iob: Optional[np.ndarray] = None,
                   cob: Optional[np.ndarray] = None,
                   bolus: Optional[np.ndarray] = None,
                   carbs: Optional[np.ndarray] = None,
                   basal_rate: Optional[np.ndarray] = None,
                   hours: Optional[np.ndarray] = None,
                   ) -> np.ndarray:
    """Build combined_43 feature array for event detection.

    Computes rolling statistics and metabolic features at each timepoint.
    Missing inputs are zero-filled (graceful degradation).

    Args:
        glucose: (N,) cleaned glucose values (mg/dL).
        metabolic: MetabolicState from metabolic_engine (optional).
        iob, cob, bolus, carbs, basal_rate: (N,) arrays (optional).
        hours: (N,) fractional hour of day.

    Returns:
        (N, 43) feature array.
    """
    N = len(glucose)
    bg = np.nan_to_num(glucose.astype(np.float64), nan=120.0)
    feat = np.zeros((N, 43), dtype=np.float32)

    # Zero-fill optional inputs
    _iob = np.nan_to_num(iob, nan=0.0) if iob is not None else np.zeros(N)
    _cob = np.nan_to_num(cob, nan=0.0) if cob is not None else np.zeros(N)
    _bolus = np.nan_to_num(bolus, nan=0.0) if bolus is not None else np.zeros(N)
    _carbs = np.nan_to_num(carbs, nan=0.0) if carbs is not None else np.zeros(N)
    _basal = np.nan_to_num(basal_rate, nan=0.0) if basal_rate is not None else np.zeros(N)
    _hours = hours if hours is not None else np.zeros(N)

    # ── BG statistics ─────────────────────────────────────────────
    feat[:, 0] = bg  # current
    feat[1:, 1] = bg[1:] - bg[:-1]                           # Δ5
    feat[3:, 2] = bg[3:] - bg[:-3]                           # Δ15
    feat[6:, 3] = bg[6:] - bg[:-6]                           # Δ30

    for i in range(N):
        w30 = bg[max(0, i-6):i+1]
        w60 = bg[max(0, i-12):i+1]
        w120 = bg[max(0, i-24):i+1]
        feat[i, 4] = np.mean(w30)                            # mean_30
        feat[i, 5] = np.std(w30) if len(w30) > 1 else 0      # std_30
        feat[i, 6] = np.mean(w60)                            # mean_60
        feat[i, 7] = np.std(w60) if len(w60) > 1 else 0      # std_60
        feat[i, 8] = np.mean(w120)                           # mean_120
        feat[i, 9] = np.std(w120) if len(w120) > 1 else 0    # std_120
        feat[i, 10] = np.min(w60)                            # min_60
        feat[i, 11] = np.max(w60)                            # max_60
        feat[i, 12] = np.min(w120)                           # min_120
        feat[i, 13] = np.max(w120)                           # max_120
        feat[i, 14] = np.max(w60) - np.min(w60)              # range_60

    # ── Insulin / Carb features ───────────────────────────────────
    feat[:, 15] = _iob
    for i in range(N):
        feat[i, 16] = np.sum(_bolus[max(0, i-6):i+1])        # bolus_recent_30
        feat[i, 17] = np.sum(_bolus[max(0, i-12):i+1])       # bolus_recent_60
    median_basal = np.median(_basal[_basal > 0]) if np.any(_basal > 0) else 0.8
    feat[:, 18] = _basal - median_basal                       # basal_deviation
    feat[:, 19] = _cob
    for i in range(N):
        feat[i, 20] = np.sum(_carbs[max(0, i-6):i+1])        # carbs_recent_30
        feat[i, 21] = np.sum(_carbs[max(0, i-12):i+1])       # carbs_recent_60
    # Time since last meal (in 5-min steps)
    last_meal = -1
    for i in range(N):
        if _carbs[i] > 0:
            last_meal = i
        feat[i, 22] = (i - last_meal) if last_meal >= 0 else 999

    # ── Metabolic flux features ───────────────────────────────────
    if metabolic is not None:
        feat[:, 23] = metabolic.supply
        feat[:, 24] = metabolic.demand
        feat[:, 25] = metabolic.net_flux
        eps = 1e-8
        feat[:, 26] = metabolic.supply / (metabolic.demand + eps)  # ratio
        feat[:, 27] = metabolic.supply * metabolic.demand          # product
        feat[:, 28] = metabolic.hepatic
        feat[:, 29] = np.abs(metabolic.residual)                   # residual_mag
        feat[:, 30] = metabolic.supply - metabolic.demand - metabolic.hepatic  # flux_imbalance

    # ── Temporal features ─────────────────────────────────────────
    feat[:, 31] = np.sin(2.0 * np.pi * _hours / 24.0)  # hour_sin
    feat[:, 32] = np.cos(2.0 * np.pi * _hours / 24.0)  # hour_cos

    # ── Derived features ──────────────────────────────────────────
    # Acceleration (2nd derivative of BG)
    feat[2:, 33] = feat[2:, 1] - feat[1:-1, 1]           # bg_acceleration
    feat[3:, 34] = feat[3:, 33] - feat[2:-1, 33]         # bg_jerk

    # Cross features
    if metabolic is not None:
        feat[:, 35] = metabolic.supply * metabolic.demand  # supply_demand_cross
        for i in range(N):
            w = metabolic.residual[max(0, i-6):i+1]
            feat[i, 36] = np.mean(w) if len(w) > 0 else 0  # residual_trend_30

    feat[:, 37] = _iob * bg / 10000.0                     # iob_x_bg
    feat[:, 38] = _cob * bg / 10000.0                     # cob_x_bg
    feat[:, 39] = feat[:, 25] * feat[:, 1]                # net_flux_x_delta

    # TIR metrics in recent window
    for i in range(N):
        w = bg[max(0, i-12):i+1]
        if len(w) > 0:
            feat[i, 40] = np.mean((w >= 70) & (w <= 180))  # tir_recent_60
            feat[i, 41] = np.mean(w < 70)                  # tbr_recent_60
            feat[i, 42] = np.mean(w > 180)                 # tar_recent_60

    return feat


def classify_risk_simple(glucose: np.ndarray,
                         metabolic: Optional[MetabolicState] = None,
                         ) -> RiskAssessment:
    """Rule-based risk classification (no XGBoost required).

    Uses simple thresholds on current BG, trend, and metabolic state.
    This is the fallback when XGBoost is not available or for cold-start
    patients without enough data for ML.

    Args:
        glucose: (N,) cleaned glucose, last element is most recent.
        metabolic: optional metabolic state for flux-enhanced prediction.

    Returns:
        RiskAssessment with estimated probabilities.
    """
    bg = glucose[-1] if len(glucose) > 0 else 120.0
    trend = (glucose[-1] - glucose[-7]) if len(glucose) > 6 else 0.0  # 30-min trend

    # Simple probability estimates based on current state + trend
    # Extrapolate 2h: bg + trend * 4 (30min trend × 4 = 2h)
    projected_2h = bg + trend * 4.0

    # Sigmoid-like probability mapping
    high_prob = 1.0 / (1.0 + np.exp(-(projected_2h - 200.0) / 30.0))
    hypo_prob = 1.0 / (1.0 + np.exp((projected_2h - 60.0) / 15.0))

    # Boost with metabolic signal if available
    if metabolic is not None:
        recent_net = np.mean(metabolic.net_flux[-6:]) if len(metabolic.net_flux) > 6 else 0.0
        if recent_net > 2.0:
            high_prob = min(high_prob * 1.3, 0.99)
        if recent_net < -2.0:
            hypo_prob = min(hypo_prob * 1.3, 0.99)

    return RiskAssessment(
        high_2h_probability=float(np.clip(high_prob, 0, 1)),
        hypo_2h_probability=float(np.clip(hypo_prob, 0, 1)),
        current_event=EventType.NONE,
        event_probabilities={'none': 1.0 - high_prob - hypo_prob,
                             'high': high_prob, 'hypo': hypo_prob},
        features_used=43 if metabolic is not None else 15,
    )
