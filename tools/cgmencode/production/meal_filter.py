"""Carb-event quality filter conventions.

Per EXP-2866 audit (2026-04-22): 30% of cohort carb events are <5g
(likely treat-of-low or detector noise) and only 11.4% are >=50g.
Future experiments grouping carb events as "meals" must apply
size-floor filters to avoid contamination.

Per patient C ground-truth audit (2026-04-23): for elevated-TBR
patients, 7.7% of >=10g logged events follow a 30-min glucose
minimum < 80 mg/dL — these are treat-of-low events mis-classified
as meals. Use the optional `prior_glucose_30min_min` argument on
`is_real_meal` / `is_substantial_meal` to suppress them.

Conventions:
* `REAL_CARB_EVENT_THRESHOLD_G = 5.0` — minimum to count as a carb
  event at all (excludes tiny treat-of-low / fragments).
* `REAL_MEAL_FLOOR_G = 10.0` — minimum to count as a "meal" for
  meal-vs-snack analyses.
* `SUBSTANTIAL_MEAL_G = 30.0` — minimum to count as a substantial
  (planned) meal for absorption / size-dependence analyses.
* `TREAT_OF_LOW_GLUCOSE_FLOOR_MGDL = 80.0` — if the prior 30-min
  glucose minimum is below this and the event is small, it's
  almost certainly a hypo treatment, not food.

Use:

    from tools.cgmencode.production.meal_filter import (
        is_real_carb_event, is_real_meal, is_substantial_meal,
    )

    # Basic size filter (backward compatible)
    if is_real_meal(carbs_g):
        ...

    # Treat-of-low aware (recommended for meal-response analyses)
    if is_real_meal(carbs_g, prior_glucose_30min_min=g_min_prior):
        ...
"""
from __future__ import annotations

from typing import Optional

REAL_CARB_EVENT_THRESHOLD_G = 5.0
REAL_MEAL_FLOOR_G = 10.0
SUBSTANTIAL_MEAL_G = 30.0
TREAT_OF_LOW_GLUCOSE_FLOOR_MGDL = 80.0


def _passes_treat_of_low(prior_glucose_30min_min: Optional[float]) -> bool:
    """True if prior-window glucose is consistent with a meal (not a hypo treat).

    None means "unknown" → conservatively pass-through (do not filter).
    """
    if prior_glucose_30min_min is None:
        return True
    return prior_glucose_30min_min >= TREAT_OF_LOW_GLUCOSE_FLOOR_MGDL


def is_real_carb_event(
    carbs_g: float,
    prior_glucose_30min_min: Optional[float] = None,
) -> bool:
    """True if event is plausibly a carb intake, not a treat-of-low fragment.

    With ``prior_glucose_30min_min`` provided, also rejects events that
    follow a sub-80 mg/dL window (treat-of-low events).
    """
    if carbs_g is None or carbs_g < REAL_CARB_EVENT_THRESHOLD_G:
        return False
    return _passes_treat_of_low(prior_glucose_30min_min)


def is_real_meal(
    carbs_g: float,
    prior_glucose_30min_min: Optional[float] = None,
) -> bool:
    """True if event is plausibly a meal (vs a snack or correction).

    With ``prior_glucose_30min_min`` provided, also rejects events that
    follow a sub-80 mg/dL window (treat-of-low events).
    """
    if carbs_g is None or carbs_g < REAL_MEAL_FLOOR_G:
        return False
    return _passes_treat_of_low(prior_glucose_30min_min)


def is_substantial_meal(
    carbs_g: float,
    prior_glucose_30min_min: Optional[float] = None,
) -> bool:
    """True if event is plausibly a substantial planned meal.

    With ``prior_glucose_30min_min`` provided, also rejects events that
    follow a sub-80 mg/dL window (treat-of-low events).
    """
    if carbs_g is None or carbs_g < SUBSTANTIAL_MEAL_G:
        return False
    return _passes_treat_of_low(prior_glucose_30min_min)
