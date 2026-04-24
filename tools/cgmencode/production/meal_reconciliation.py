"""Meal logging-quality reconciliation (patient-C audit follow-up).

Compares **logged carb events** against **glucose-rise inferred meals**
(`meal_detector.detect_meal_events`) to produce a per-patient logging
quality flag plus a per-daypart breakdown. This complements
`meal_filter.is_real_meal` which only judges single events.

Use:

    from tools.cgmencode.production.meal_reconciliation import (
        reconcile_meal_logging,
    )
    qc = reconcile_meal_logging(
        logged_events=[(t_ms, carbs_g), ...],
        inferred_meals=[m for m in detect_meal_events(...)],
        days_of_data=180.0,
    )
    if qc.is_under_logger:
        # widen confidence intervals on meal-response stats
        ...

Flag thresholds (chosen from patient-A vs patient-C cohort sweep):

* `under_logger`     : logged_rate / inferred_rate < 0.5
* `phantom_logger`   : logged_rate / inferred_rate > 2.0
* `well_aligned`     : 0.5 ≤ ratio ≤ 2.0

Daypart bins are conventional and match patient-C report:
breakfast 05–11, lunch 11–15, dinner 15–22, overnight 22–05.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, List, Optional, Sequence, Tuple

from .meal_filter import REAL_MEAL_FLOOR_G

# ── constants ──────────────────────────────────────────────────────

UNDER_LOGGER_RATIO = 0.5
PHANTOM_LOGGER_RATIO = 2.0

DAYPARTS: Tuple[Tuple[str, int, int], ...] = (
    ("breakfast", 5, 11),
    ("lunch",     11, 15),
    ("dinner",    15, 22),
    ("overnight", 22, 29),  # 22..23, 0..4 (handled via mod 24)
)


def _daypart(hour: int) -> str:
    for name, lo, hi in DAYPARTS:
        if name == "overnight":
            if hour >= 22 or hour < 5:
                return name
        elif lo <= hour < hi:
            return name
    return "overnight"


# ── dataclasses ────────────────────────────────────────────────────


@dataclass(frozen=True)
class DaypartCounts:
    """Logged + inferred meal counts for a single daypart."""

    daypart: str
    logged_per_day: float
    inferred_per_day: float

    @property
    def ratio(self) -> Optional[float]:
        if self.inferred_per_day <= 0:
            return None
        return self.logged_per_day / self.inferred_per_day


@dataclass(frozen=True)
class MealLoggingQC:
    """Per-patient meal-logging quality summary.

    ``ratio`` is ``logged_per_day / inferred_per_day``. None if
    `inferred_per_day` is 0 (insufficient data).
    """

    logged_per_day: float
    inferred_per_day: float
    ratio: Optional[float]
    flag: str  # "under_logger" | "phantom_logger" | "well_aligned" | "insufficient_data"
    by_daypart: Tuple[DaypartCounts, ...] = field(default_factory=tuple)
    n_logged: int = 0
    n_inferred: int = 0
    days_of_data: float = 0.0

    @property
    def is_under_logger(self) -> bool:
        return self.flag == "under_logger"

    @property
    def is_phantom_logger(self) -> bool:
        return self.flag == "phantom_logger"


# ── core ───────────────────────────────────────────────────────────


def _hour_from_ms(t_ms: int, tz_offset_hours: float = 0.0,
                  tz: Optional[str] = None) -> int:
    """Hour-of-day from a Unix-ms timestamp.

    Prefer ``tz`` (IANA name, DST-aware via pandas tz_convert) over
    the legacy ``tz_offset_hours`` argument. ``tz_offset_hours`` is
    retained for back-compat and acts only when ``tz`` is None or
    the conversion fails.
    """
    if tz and tz != 'UTC':
        try:
            import pandas as pd
            ts = pd.Timestamp(int(t_ms), unit='ms', tz='UTC').tz_convert(tz)
            return int(ts.hour)
        except Exception:
            pass
    shifted = t_ms / 1000.0 + tz_offset_hours * 3600.0
    return datetime.fromtimestamp(shifted, tz=timezone.utc).hour


def reconcile_meal_logging(
    logged_events: Sequence[Tuple[int, float]],
    inferred_meals: Iterable,
    days_of_data: float,
    min_carbs_g: float = REAL_MEAL_FLOOR_G,
    tz_offset_hours: float = 0.0,
    tz: Optional[str] = None,
) -> MealLoggingQC:
    """Compare logged vs inferred meal rates and flag the patient.

    Parameters
    ----------
    logged_events
        Sequence of ``(timestamp_ms, carbs_g)`` tuples.
    inferred_meals
        Iterable of detector outputs. Each item must expose either a
        ``timestamp_ms`` attribute or be a ``(timestamp_ms, ...)`` tuple
        or have ``.index`` + a separate hours array (we accept any item
        with a ``timestamp_ms`` attribute; otherwise we use ``.t_ms``).
    days_of_data
        Patient observation window in days (use ``patient.days_of_data``).
    min_carbs_g
        Logged events smaller than this are excluded (default
        ``REAL_MEAL_FLOOR_G = 10`` g).
    """
    if days_of_data <= 0:
        return MealLoggingQC(
            logged_per_day=0.0,
            inferred_per_day=0.0,
            ratio=None,
            flag="insufficient_data",
            by_daypart=(),
            n_logged=0,
            n_inferred=0,
            days_of_data=days_of_data,
        )

    # Filter & bucket logged events
    logged_filtered: List[Tuple[int, float]] = [
        (t, c) for t, c in logged_events
        if c is not None and c >= min_carbs_g
    ]
    logged_buckets: dict = {n: 0 for n, _, _ in DAYPARTS}
    for t_ms, _ in logged_filtered:
        logged_buckets[_daypart(_hour_from_ms(int(t_ms), tz_offset_hours, tz))] += 1

    # Bucket inferred meals
    inferred_buckets: dict = {n: 0 for n, _, _ in DAYPARTS}
    n_inferred = 0
    for m in inferred_meals:
        n_inferred += 1
        t_ms = getattr(m, "timestamp_ms", None) or getattr(m, "t_ms", None)
        if t_ms is None:
            # Fallback: skip — daypart breakdown will be undercounted but
            # totals stay correct.
            continue
        inferred_buckets[_daypart(_hour_from_ms(int(t_ms), tz_offset_hours, tz))] += 1

    by_daypart = tuple(
        DaypartCounts(
            daypart=name,
            logged_per_day=logged_buckets[name] / days_of_data,
            inferred_per_day=inferred_buckets[name] / days_of_data,
        )
        for name, _, _ in DAYPARTS
    )

    n_logged = len(logged_filtered)
    logged_per_day = n_logged / days_of_data
    inferred_per_day = n_inferred / days_of_data

    if inferred_per_day <= 0:
        flag = "insufficient_data"
        ratio: Optional[float] = None
    else:
        ratio = logged_per_day / inferred_per_day
        if ratio < UNDER_LOGGER_RATIO:
            flag = "under_logger"
        elif ratio > PHANTOM_LOGGER_RATIO:
            flag = "phantom_logger"
        else:
            flag = "well_aligned"

    return MealLoggingQC(
        logged_per_day=logged_per_day,
        inferred_per_day=inferred_per_day,
        ratio=ratio,
        flag=flag,
        by_daypart=by_daypart,
        n_logged=n_logged,
        n_inferred=n_inferred,
        days_of_data=days_of_data,
    )
