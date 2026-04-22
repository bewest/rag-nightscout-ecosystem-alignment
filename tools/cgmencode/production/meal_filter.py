"""Carb-event quality filter conventions.

Per EXP-2866 audit (2026-04-22): 30% of cohort carb events are <5g
(likely treat-of-low or detector noise) and only 11.4% are >=50g.
Future experiments grouping carb events as "meals" must apply
size-floor filters to avoid contamination.

Conventions:
* `REAL_CARB_EVENT_THRESHOLD_G = 5.0` — minimum to count as a carb
  event at all (excludes tiny treat-of-low / fragments).
* `REAL_MEAL_FLOOR_G = 10.0` — minimum to count as a "meal" for
  meal-vs-snack analyses.
* `SUBSTANTIAL_MEAL_G = 30.0` — minimum to count as a substantial
  (planned) meal for absorption / size-dependence analyses.

Use:

    from tools.cgmencode.production.meal_filter import (
        is_real_carb_event, is_real_meal, is_substantial_meal,
    )
"""
from __future__ import annotations

REAL_CARB_EVENT_THRESHOLD_G = 5.0
REAL_MEAL_FLOOR_G = 10.0
SUBSTANTIAL_MEAL_G = 30.0


def is_real_carb_event(carbs_g: float) -> bool:
    """True if event is plausibly a carb intake, not a treat-of-low fragment."""
    return carbs_g is not None and carbs_g >= REAL_CARB_EVENT_THRESHOLD_G


def is_real_meal(carbs_g: float) -> bool:
    """True if event is plausibly a meal (vs a snack or correction)."""
    return carbs_g is not None and carbs_g >= REAL_MEAL_FLOOR_G


def is_substantial_meal(carbs_g: float) -> bool:
    """True if event is plausibly a substantial planned meal."""
    return carbs_g is not None and carbs_g >= SUBSTANTIAL_MEAL_G
