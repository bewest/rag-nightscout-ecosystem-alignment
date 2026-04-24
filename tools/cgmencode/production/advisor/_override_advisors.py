"""Loop-style override schedule recommender.

Where the existing `advise_override_isf` (EXP-2621) *detects* whether an
ISF mismatch occurs while a user-set override is active, this module
goes the other direction: given a patient's actual evening-meal +
late-night descent pattern, propose an override **schedule** the patient
can configure on their controller (Loop / Trio / AAPS).

Two patterns currently recognised:

  1. **dinner_alcohol_descent**: late-evening meal cluster (18:00-22:00)
     followed by a sustained descent into the early-morning window with
     the late-night minimum lower than the pre-meal baseline. This is
     the canonical alcohol/hepatic-suppression signature: late hepatic
     glucose output is blunted, so the same evening dose now over-treats
     the post-meal rise. The recommendation is a wider target + softer
     ISF + reduced basal during the dinner+overnight window.

  2. **postmeal_overshoot_then_correction**: same meal cluster but the
     late-night trajectory ends at HYPER. Recommend tighter target +
     more aggressive ISF for the dinner window only.

These are explicitly INFORMATIONAL: emitted as `ActionRecommendation`
items at priority 3 so they show up in the report's "consider" section
without competing with the safety-tier ISF/basal advisories.

References:
  - EXP-2621 (override-active ISF split)
  - EXP-2944 (post-meal IOB-age timing differences across designs)
  - clinical literature on alcohol-induced hepatic glucose suppression
"""

from __future__ import annotations
from typing import List, Optional
import numpy as np

from ..types import ActionRecommendation


__all__ = [
    'recommend_meal_override_schedule',
    '_DINNER_START_HOUR',
    '_DINNER_END_HOUR',
    '_OVERNIGHT_END_HOUR',
    '_MIN_DAYS',
    '_MIN_DROP_BELOW_BASELINE',
    '_MIN_OVERSHOOT_ABOVE_BASELINE',
]


# Window definitions
_DINNER_START_HOUR = 18.0
_DINNER_END_HOUR = 22.0
_OVERNIGHT_END_HOUR = 6.0  # next morning

# Detection thresholds
_MIN_DAYS = 7.0
_MIN_DROP_BELOW_BASELINE = 25.0   # mg/dL — trustworthy descent signature
_MIN_OVERSHOOT_ABOVE_BASELINE = 40.0  # mg/dL — clear overshoot

_STEPS_PER_HOUR = 12  # 5-min cadence


def _profile_value(profile, attr: str, default: float) -> float:
    """Pull a representative value from a PatientProfile schedule."""
    schedule = getattr(profile, attr, None)
    if not schedule:
        return default
    try:
        if callable(schedule):
            schedule = schedule()
    except TypeError:
        pass
    if not schedule:
        return default
    try:
        vals = [float(e.get('value', e.get('rate', default))) for e in schedule]
    except (AttributeError, TypeError):
        return default
    return float(np.median(vals)) if vals else default


def recommend_meal_override_schedule(
    glucose: np.ndarray,
    hours: np.ndarray,
    profile,
    *,
    days_of_data: float,
    has_alcohol_context: Optional[bool] = None,
) -> List[ActionRecommendation]:
    """Detect dinner-window descent/overshoot patterns and propose an override.

    Args:
        glucose: (N,) glucose mg/dL.
        hours: (N,) fractional hour-of-day (0-24).
        profile: PatientProfile (target/ISF/basal medians read for context).
        days_of_data: data coverage gate (returns [] below _MIN_DAYS).
        has_alcohol_context: optional caller hint. When True the descent
            recommendation's rationale explicitly cites alcohol-induced
            hepatic suppression; when False/None it's framed neutrally.

    Returns:
        0-1 ActionRecommendation. Returns [] when the pattern is below
        detection thresholds or coverage is insufficient.
    """
    if days_of_data < _MIN_DAYS:
        return []

    n = min(len(glucose), len(hours))
    if n < _STEPS_PER_HOUR * 24 * int(_MIN_DAYS):
        return []
    g = np.asarray(glucose[:n], dtype=float)
    h = np.asarray(hours[:n], dtype=float)

    finite = np.isfinite(g)
    if finite.sum() < 0.5 * n:
        return []

    dinner_mask = finite & (h >= _DINNER_START_HOUR) & (h < _DINNER_END_HOUR)
    early_mask = finite & ((h < _OVERNIGHT_END_HOUR) | (h >= _DINNER_END_HOUR))

    if dinner_mask.sum() < 12 or early_mask.sum() < 24:
        return []

    dinner_baseline = float(np.nanmedian(g[dinner_mask]))
    overnight_min = float(np.nanpercentile(g[early_mask], 5))
    overnight_max = float(np.nanpercentile(g[early_mask], 95))

    drop = dinner_baseline - overnight_min
    overshoot = overnight_max - dinner_baseline

    target = _profile_value(profile, 'target_schedule', 110.0)
    isf = _profile_value(profile, 'isf_schedule', 50.0)
    basal = _profile_value(profile, 'basal_schedule', 0.8)

    # Pattern 1: descent into the morning (alcohol/hepatic suppression)
    if drop >= _MIN_DROP_BELOW_BASELINE and drop > overshoot:
        new_target = round(target + 20.0, 0)
        new_isf = round(isf * 1.30, 1)       # softer
        new_basal = round(basal * 0.80, 2)   # reduced
        alcohol_phrase = (
            "alcohol-induced hepatic glucose suppression"
            if has_alcohol_context
            else "post-dinner hepatic suppression (e.g. alcohol or fat-loaded meals)"
        )
        return [ActionRecommendation(
            action_type="loop_override_recommendation",
            priority=3,
            description=(
                f"Consider configuring a controller override named "
                f"\"Dinner / Alcohol\" active {int(_DINNER_START_HOUR):02d}:00–"
                f"{int(_OVERNIGHT_END_HOUR):02d}:00 with target "
                f"{new_target:.0f} mg/dL, ISF ratio 1.30 "
                f"({isf:.0f} → {new_isf:.0f}), basal 0.80× "
                f"({basal:.2f} → {new_basal:.2f} U/h). Late-night nadir "
                f"({overnight_min:.0f} mg/dL) sits {drop:.0f} mg/dL below the "
                f"dinner baseline ({dinner_baseline:.0f} mg/dL) — typical of "
                f"{alcohol_phrase}. The current evening dose treats the "
                f"post-meal rise but compounds with the suppressed late EGP, "
                f"yielding overnight TBR risk. The override softens insulin "
                f"action across the suppression window."
            ),
            predicted_tir_delta=2.0,
            confidence=0.55,
            time_sensitive=False,
        )]

    # Pattern 2: post-dinner overshoot into late night
    if overshoot >= _MIN_OVERSHOOT_ABOVE_BASELINE and overshoot > drop:
        new_target = round(max(95.0, target - 10.0), 0)
        new_isf = round(isf * 0.85, 1)
        return [ActionRecommendation(
            action_type="loop_override_recommendation",
            priority=3,
            description=(
                f"Consider configuring a controller override named "
                f"\"Dinner Aggressive\" active {int(_DINNER_START_HOUR):02d}:00–"
                f"{int(_OVERNIGHT_END_HOUR):02d}:00 with target "
                f"{new_target:.0f} mg/dL and ISF ratio 0.85 "
                f"({isf:.0f} → {new_isf:.0f}). Late-night peak "
                f"({overnight_max:.0f} mg/dL) sits {overshoot:.0f} mg/dL above "
                f"the dinner baseline ({dinner_baseline:.0f} mg/dL), "
                f"indicating sustained post-dinner overshoot — current evening "
                f"settings under-cover the late absorption phase."
            ),
            predicted_tir_delta=1.5,
            confidence=0.50,
            time_sensitive=False,
        )]

    return []
