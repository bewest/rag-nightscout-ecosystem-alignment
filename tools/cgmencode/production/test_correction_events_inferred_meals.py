"""Regression tests for inferred-meal adoption in correction-event extraction.

Pins behavior added in P1.2 of the Apr-26 autoresearch push:
``_extract_correction_events`` now accepts ``inferred_meals=`` and excludes
events whose ±1 h window contains an inferred meal of ≥5 g. Without this,
heavy under-loggers had post-meal boluses mis-classified as fasting
corrections, deflating ISF estimates by 20-45 % (EXP-2739).

Tests assert *direction and group difference*, not magnitude pinned to a
brittle constant (per the rubber-duck critique on the autoresearch plan).
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from tools.cgmencode.production.pipeline import _extract_correction_events


@dataclass
class _DummyProfile:
    target_high: float = 180.0


@dataclass
class _DummyMeal:
    index: int
    estimated_carbs_g: float


def _build_grid(n_steps: int = 600,
                bolus_at: tuple = (60, 180, 300, 420),
                start_bg: float = 220.0,
                end_bg: float = 130.0) -> tuple:
    """Returns (glucose, bolus, carbs, hours).

    Glucose is a saw-tooth — high at each bolus, decaying to ``end_bg``
    by 4 h post-bolus — so each bolus qualifies as a correction event
    (BG > 180 at dose, drops by 90 mg/dL over 4 h, no logged carbs).
    """
    glucose = np.full(n_steps, end_bg, dtype=float)
    bolus = np.full(n_steps, np.nan, dtype=float)
    carbs = np.zeros(n_steps, dtype=float)
    hours = np.linspace(0, 24 * (n_steps / 288), n_steps)

    for i in bolus_at:
        bolus[i] = 1.0
        # ramp glucose down from start_bg at i to end_bg at i+48
        for k in range(min(48, n_steps - i)):
            glucose[i + k] = start_bg - (start_bg - end_bg) * (k / 48.0)

    return glucose, bolus, carbs, hours


def test_inferred_meals_kwarg_accepted_with_none():
    """Back-compat: passing inferred_meals=None matches no-kwarg behavior."""
    glucose, bolus, carbs, hours = _build_grid()
    profile = _DummyProfile()

    events_no_kw = _extract_correction_events(
        glucose, bolus, carbs, hours, profile)
    events_kw_none = _extract_correction_events(
        glucose, bolus, carbs, hours, profile, inferred_meals=None)
    events_kw_empty = _extract_correction_events(
        glucose, bolus, carbs, hours, profile, inferred_meals=[])

    assert len(events_no_kw) == len(events_kw_none) == len(events_kw_empty)
    assert len(events_no_kw) >= 3, (
        f"sanity: should detect ≥3 corrections, got {len(events_no_kw)}")


def test_inferred_meal_excludes_overlapping_correction():
    """An inferred meal within ±1 h of a bolus should suppress that
    correction event (mirrors EXP-2739 under-logger fix)."""
    glucose, bolus, carbs, hours = _build_grid(bolus_at=(60, 180, 300, 420))
    profile = _DummyProfile()

    baseline = _extract_correction_events(glucose, bolus, carbs, hours, profile)
    n_baseline = len(baseline)

    # Inferred meals within ±12 steps of bolus indices 60 and 180; 300 and
    # 420 are unaffected.
    meals = [
        _DummyMeal(index=58, estimated_carbs_g=40.0),   # adjacent to 60
        _DummyMeal(index=190, estimated_carbs_g=25.0),  # within 12 of 180
    ]
    filtered = _extract_correction_events(
        glucose, bolus, carbs, hours, profile, inferred_meals=meals)

    # Direction: filtered set is strictly smaller, by at most 2.
    assert len(filtered) < n_baseline, (
        f"inferred meals should suppress events: baseline={n_baseline}, "
        f"filtered={len(filtered)}")
    assert n_baseline - len(filtered) == 2, (
        f"expected exactly 2 events suppressed, got "
        f"{n_baseline - len(filtered)}")


def test_inferred_meal_below_threshold_does_not_suppress():
    """Sub-threshold inferred meals (<5 g) must not suppress corrections."""
    glucose, bolus, carbs, hours = _build_grid(bolus_at=(60, 180))
    profile = _DummyProfile()
    baseline = _extract_correction_events(glucose, bolus, carbs, hours, profile)
    tiny_meals = [_DummyMeal(index=58, estimated_carbs_g=2.0)]

    out = _extract_correction_events(
        glucose, bolus, carbs, hours, profile, inferred_meals=tiny_meals)
    assert len(out) == len(baseline)


def test_inferred_meal_outside_window_does_not_suppress():
    """An inferred meal >1 h from any bolus must not suppress."""
    glucose, bolus, carbs, hours = _build_grid(bolus_at=(60, 300))
    profile = _DummyProfile()
    baseline = _extract_correction_events(glucose, bolus, carbs, hours, profile)
    far_meal = [_DummyMeal(index=180, estimated_carbs_g=50.0)]  # >12 from 60 and 300

    out = _extract_correction_events(
        glucose, bolus, carbs, hours, profile, inferred_meals=far_meal)
    assert len(out) == len(baseline)


def test_under_logger_group_shift_directional():
    """*Group-comparison* test (per rubber-duck guidance): heavy
    under-logger should retain *fewer* fasting-correction events than
    well-aligned logger; without inferred-meal exclusion, the heavy
    under-logger would retain *more* spurious events. Assert direction,
    not magnitude pinned to a constant."""
    glucose, bolus, carbs, hours = _build_grid(
        bolus_at=tuple(range(60, 540, 60)))  # 8 boluses
    profile = _DummyProfile()

    # Well-aligned logger: every bolus has a logged carb pairing → all
    # boluses excluded as meal-related already, so adding inferred meals
    # has no further effect.
    aligned_carbs = carbs.copy()
    for i in (60, 120, 180, 240, 300, 360, 420, 480):
        aligned_carbs[i] = 30.0
    aligned_with_inferred = _extract_correction_events(
        glucose, bolus, aligned_carbs, hours, profile,
        inferred_meals=[_DummyMeal(i, 30.0) for i in
                        (60, 120, 180, 240, 300, 360, 420, 480)])
    aligned_without = _extract_correction_events(
        glucose, bolus, aligned_carbs, hours, profile)
    assert len(aligned_with_inferred) == len(aligned_without), (
        "well-aligned logger: inferred-meal flag should have no effect")

    # Under-logger: zero logged carbs, but detector inferred a meal at
    # half of those bolus times.
    under_logger_inferred = [
        _DummyMeal(i, 35.0) for i in (60, 180, 300, 420)
    ]
    under_with = _extract_correction_events(
        glucose, bolus, carbs, hours, profile,
        inferred_meals=under_logger_inferred)
    under_without = _extract_correction_events(
        glucose, bolus, carbs, hours, profile)
    assert len(under_with) < len(under_without), (
        "heavy under-logger: inferred meals must suppress some events")
    assert len(under_with) == len(under_without) - 4


if __name__ == "__main__":
    test_inferred_meals_kwarg_accepted_with_none()
    test_inferred_meal_excludes_overlapping_correction()
    test_inferred_meal_below_threshold_does_not_suppress()
    test_inferred_meal_outside_window_does_not_suppress()
    test_under_logger_group_shift_directional()
    print("OK: all inferred-meal correction-event regression tests pass.")
