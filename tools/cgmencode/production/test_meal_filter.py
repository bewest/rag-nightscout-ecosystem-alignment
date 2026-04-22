"""Tests for meal_filter conventions (EXP-2866 follow-up)."""
from __future__ import annotations

from tools.cgmencode.production.meal_filter import (
    REAL_CARB_EVENT_THRESHOLD_G,
    REAL_MEAL_FLOOR_G,
    SUBSTANTIAL_MEAL_G,
    is_real_carb_event,
    is_real_meal,
    is_substantial_meal,
)


def test_thresholds_are_documented_values():
    assert REAL_CARB_EVENT_THRESHOLD_G == 5.0
    assert REAL_MEAL_FLOOR_G == 10.0
    assert SUBSTANTIAL_MEAL_G == 30.0


def test_is_real_carb_event_borderline():
    assert not is_real_carb_event(4.99)
    assert is_real_carb_event(5.0)
    assert is_real_carb_event(60)


def test_is_real_meal_borderline():
    assert not is_real_meal(9.99)
    assert is_real_meal(10.0)
    assert not is_real_meal(5.0)


def test_is_substantial_meal_borderline():
    assert not is_substantial_meal(29.99)
    assert is_substantial_meal(30.0)
    assert is_substantial_meal(60.0)


def test_none_or_zero_is_false():
    assert not is_real_carb_event(None)
    assert not is_real_carb_event(0)
    assert not is_real_meal(None)
    assert not is_substantial_meal(None)
