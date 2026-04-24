"""Tests for meal_reconciliation module (patient-C audit follow-up)."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from tools.cgmencode.production.meal_reconciliation import (
    DAYPARTS,
    MealLoggingQC,
    PHANTOM_LOGGER_RATIO,
    UNDER_LOGGER_RATIO,
    reconcile_meal_logging,
)

pytestmark = pytest.mark.unit


def _ms(year, month, day, hour) -> int:
    return int(datetime(year, month, day, hour, tzinfo=timezone.utc).timestamp() * 1000)


def _inferred(t_ms: int) -> SimpleNamespace:
    return SimpleNamespace(timestamp_ms=t_ms)


# ── basic structure ───────────────────────────────────────────────


def test_dayparts_cover_24h():
    """Every hour 0..23 must map to exactly one daypart."""
    from tools.cgmencode.production.meal_reconciliation import _daypart
    seen = {h: _daypart(h) for h in range(24)}
    assert set(seen.values()) <= {n for n, _, _ in DAYPARTS}
    # No hour returns None
    assert all(v is not None for v in seen.values())


def test_insufficient_data_zero_days():
    qc = reconcile_meal_logging([], [], days_of_data=0.0)
    assert qc.flag == "insufficient_data"
    assert qc.ratio is None


def test_insufficient_data_no_inferred():
    qc = reconcile_meal_logging(
        [(_ms(2026, 1, 1, 12), 30)],
        [],
        days_of_data=10.0,
    )
    assert qc.flag == "insufficient_data"
    assert qc.ratio is None
    assert qc.n_logged == 1


# ── logging-quality flag ──────────────────────────────────────────


def test_well_aligned_ratio():
    days = 10.0
    logged = [(_ms(2026, 1, 1, 12), 30)] * 20      # 2/day
    inferred = [_inferred(_ms(2026, 1, 1, 12))] * 20
    qc = reconcile_meal_logging(logged, inferred, days_of_data=days)
    assert qc.flag == "well_aligned"
    assert qc.ratio == pytest.approx(1.0)


def test_under_logger_ratio():
    days = 10.0
    logged = [(_ms(2026, 1, 1, 12), 30)] * 5       # 0.5/day
    inferred = [_inferred(_ms(2026, 1, 1, 12))] * 30  # 3/day → ratio 0.17
    qc = reconcile_meal_logging(logged, inferred, days_of_data=days)
    assert qc.flag == "under_logger"
    assert qc.is_under_logger
    assert qc.ratio < UNDER_LOGGER_RATIO


def test_phantom_logger_ratio():
    days = 10.0
    logged = [(_ms(2026, 1, 1, 12), 30)] * 60      # 6/day
    inferred = [_inferred(_ms(2026, 1, 1, 12))] * 10  # 1/day → ratio 6.0
    qc = reconcile_meal_logging(logged, inferred, days_of_data=days)
    assert qc.flag == "phantom_logger"
    assert qc.is_phantom_logger
    assert qc.ratio > PHANTOM_LOGGER_RATIO


# ── size filter ───────────────────────────────────────────────────


def test_logged_size_filter_applies():
    """Logged events below `min_carbs_g` are excluded from rate."""
    days = 10.0
    logged = [
        (_ms(2026, 1, 1, 12), 5),    # excluded (< 10g default)
        (_ms(2026, 1, 1, 13), 15),   # counted
    ]
    inferred = [_inferred(_ms(2026, 1, 1, 12))]
    qc = reconcile_meal_logging(logged, inferred, days_of_data=days)
    assert qc.n_logged == 1
    assert qc.logged_per_day == pytest.approx(0.1)


def test_min_carbs_override():
    days = 10.0
    logged = [(_ms(2026, 1, 1, 12), 25)]
    inferred = [_inferred(_ms(2026, 1, 1, 12))]
    qc = reconcile_meal_logging(
        logged, inferred, days_of_data=days, min_carbs_g=30.0
    )
    assert qc.n_logged == 0


# ── daypart breakdown ─────────────────────────────────────────────


def test_daypart_bucketing():
    days = 1.0
    logged = [
        (_ms(2026, 1, 1, 7),  20),   # breakfast
        (_ms(2026, 1, 1, 12), 25),   # lunch
        (_ms(2026, 1, 1, 18), 35),   # dinner
        (_ms(2026, 1, 1, 23), 12),   # overnight
        (_ms(2026, 1, 2, 3),  10),   # overnight (early morning)
    ]
    inferred = [_inferred(_ms(2026, 1, 1, 18))] * 5
    qc = reconcile_meal_logging(logged, inferred, days_of_data=days)
    by = {d.daypart: d for d in qc.by_daypart}
    assert by["breakfast"].logged_per_day == pytest.approx(1.0)
    assert by["lunch"].logged_per_day == pytest.approx(1.0)
    assert by["dinner"].logged_per_day == pytest.approx(1.0)
    assert by["overnight"].logged_per_day == pytest.approx(2.0)
    # Inferred all in dinner
    assert by["dinner"].inferred_per_day == pytest.approx(5.0)
    assert by["dinner"].ratio == pytest.approx(1/5)


def test_inferred_without_timestamp_counted_in_total_only():
    """Inferred meals lacking timestamps still count toward overall rate."""
    days = 10.0
    logged = [(_ms(2026, 1, 1, 12), 20)] * 10
    inferred = [SimpleNamespace()] * 10  # no timestamp_ms / t_ms
    qc = reconcile_meal_logging(logged, inferred, days_of_data=days)
    assert qc.n_inferred == 10
    assert qc.inferred_per_day == pytest.approx(1.0)
    # by_daypart all zero for inferred
    assert all(d.inferred_per_day == 0.0 for d in qc.by_daypart)


def test_t_ms_attribute_also_supported():
    days = 1.0
    inferred = [SimpleNamespace(t_ms=_ms(2026, 1, 1, 12))]
    qc = reconcile_meal_logging([], inferred, days_of_data=days)
    by = {d.daypart: d for d in qc.by_daypart}
    assert by["lunch"].inferred_per_day == pytest.approx(1.0)


# ── flag accessors ────────────────────────────────────────────────


def test_flag_accessors_consistent():
    qc = MealLoggingQC(
        logged_per_day=1.0, inferred_per_day=4.0, ratio=0.25,
        flag="under_logger", n_logged=10, n_inferred=40, days_of_data=10.0,
    )
    assert qc.is_under_logger
    assert not qc.is_phantom_logger
