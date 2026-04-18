"""Physics simulation for counterfactual TIR prediction (EXP-2551)."""

from __future__ import annotations
from typing import List, Optional
import numpy as np
from ..types import PatientProfile, SettingsParameter, SettingsRecommendation
from ..metabolic_engine import _FAST_TAU_HOURS, _PERSISTENT_FRACTION


__all__ = [
    'DECAY_RATE',
    'DECAY_TARGET',
    'HIGH_CONFIDENCE_DAYS',
    'MIN_DATA_DAYS',
    'PERIODS',
    'SIMULATION_STEPS',
    '_FAST_FRACTION',
    '_FAST_TAU_STEPS',
    '_PERSISTENT_TAU_STEPS',
    '_POWER_LAW_BETA',
    'simulate_tir_with_settings',
]


# Physics simulation parameters
SIMULATION_STEPS = 288    # 1 day of 5-min intervals
DECAY_TARGET = 120.0      # mg/dL equilibrium
DECAY_RATE = 0.005        # per 5-min step

# Two-component DIA simulation (validated EXP-2551)
_FAST_TAU_STEPS = int(_FAST_TAU_HOURS * 12)        # 0.8h × 12 = ~10 steps
_PERSISTENT_TAU_STEPS = int(12.0 * 12)              # 12h × 12 = 144 steps
_FAST_FRACTION = 1.0 - _PERSISTENT_FRACTION          # 0.63
_POWER_LAW_BETA = 0.9                                # from EXP-2511

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
    """Simulate TIR under modified settings using two-component DIA model.

    Uses a perturbation approach rather than full forward simulation to
    avoid error accumulation over long time series. The settings change
    creates a per-step delta that propagates through two decay channels:

    1. Fast component (63%): τ=0.8h — captures immediate insulin action
    2. Persistent component (37%): τ=12h — captures IOB underestimation
       and loop basal compensation (validated EXP-2525/2534)

    Power-law ISF dampening (β=0.9 from EXP-2511) prevents overestimating
    large ISF corrections. Without this, the persistent tail overamplifies
    perturbations (Model B MAE=3.23pp vs Model C MAE=0.30pp in EXP-2551).

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

    # Two-component decay factors
    fast_decay = np.exp(-1.0 / max(_FAST_TAU_STEPS, 1))
    persistent_decay = np.exp(-1.0 / _PERSISTENT_TAU_STEPS)

    # Power-law ISF dampening: effective_mult = mult^(1 - β)
    if isf_multiplier > 0:
        effective_isf_mult = isf_multiplier ** (1.0 - _POWER_LAW_BETA)
    else:
        effective_isf_mult = 1.0

    delta_fast = np.zeros(N)
    delta_persistent = np.zeros(N)

    for t in range(1, N):
        delta_fast[t] = delta_fast[t - 1] * fast_decay
        delta_persistent[t] = delta_persistent[t - 1] * persistent_decay

        if mask[t]:
            s = float(supply[t - 1]) if np.isfinite(supply[t - 1]) else 0.0
            d = float(demand[t - 1]) if np.isfinite(demand[t - 1]) else 0.0

            # ISF change with power-law dampening
            demand_delta = d * (effective_isf_mult * basal_multiplier - 1.0)
            # CR change: higher CR → less glucose rise per carb
            supply_delta = s * (1.0 / max(cr_multiplier, 0.1) - 1.0)
            # Net perturbation split into two channels
            step_pert = supply_delta - demand_delta
            delta_fast[t] += step_pert * _FAST_FRACTION
            delta_persistent[t] += step_pert * _PERSISTENT_FRACTION

    # Combined perturbation
    delta = delta_fast + delta_persistent

    # Apply perturbation to actual glucose
    sim_bg = np.clip(bg + delta, 40.0, 400.0)

    # Compute TIR for both
    valid_orig = bg[np.isfinite(bg)]
    valid_sim = sim_bg[np.isfinite(sim_bg)]

    tir_current = float(np.mean((valid_orig >= 70) & (valid_orig <= 180)))
    tir_simulated = float(np.mean((valid_sim >= 70) & (valid_sim <= 180)))

    return tir_current, tir_simulated


