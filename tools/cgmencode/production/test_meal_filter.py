"""Tests for meal_filter conventions (EXP-2866 follow-up)."""
from __future__ import annotations

import pytest

from tools.cgmencode.production.meal_filter import (
    REAL_CARB_EVENT_THRESHOLD_G,
    REAL_MEAL_FLOOR_G,
    SUBSTANTIAL_MEAL_G,
    TREAT_OF_LOW_GLUCOSE_FLOOR_MGDL,
    is_real_carb_event,
    is_real_meal,
    is_substantial_meal,
)

pytestmark = pytest.mark.unit


def test_thresholds_are_documented_values():
    assert REAL_CARB_EVENT_THRESHOLD_G == 5.0
    assert REAL_MEAL_FLOOR_G == 10.0
    assert SUBSTANTIAL_MEAL_G == 30.0
    assert TREAT_OF_LOW_GLUCOSE_FLOOR_MGDL == 80.0


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


# ── Treat-of-low filter (patient C audit, 2026-04-23) ─────────────


def test_prior_glucose_none_is_pass_through():
    """None means unknown — must not silently filter."""
    assert is_real_meal(20.0, prior_glucose_30min_min=None)
    assert is_real_carb_event(10.0, prior_glucose_30min_min=None)
    assert is_substantial_meal(40.0, prior_glucose_30min_min=None)


def test_treat_of_low_blocks_meal():
    # 20g carbs eaten while glucose was 65 → treat-of-low
    assert not is_real_meal(20.0, prior_glucose_30min_min=65.0)
    assert not is_real_carb_event(20.0, prior_glucose_30min_min=65.0)
    assert not is_substantial_meal(40.0, prior_glucose_30min_min=65.0)


def test_treat_of_low_borderline_at_80():
    assert is_real_meal(20.0, prior_glucose_30min_min=80.0)
    assert not is_real_meal(20.0, prior_glucose_30min_min=79.99)


def test_size_filter_still_applies_with_prior_glucose():
    """Prior glucose can't rescue a tiny event."""
    assert not is_real_meal(4.0, prior_glucose_30min_min=120.0)
    assert not is_substantial_meal(15.0, prior_glucose_30min_min=120.0)


def test_backward_compat_signature_unchanged_for_size_only():
    """Existing single-arg callers must keep working unchanged."""
    assert is_real_meal(20.0)
    assert is_real_carb_event(5.0)
    assert is_substantial_meal(30.0)
