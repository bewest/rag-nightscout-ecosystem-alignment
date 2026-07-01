"""cr_action_label_benchmark.py — validating the single existing CR
action-needed label source (increase/decrease/none) per decision window.

Third domain in the action-space label pivot (see
docs/60-research/state-aware-harness-parallels-2026-07-01.md §7). Unlike
basal (two independent sources: EXP-2865/2869 facts-loader vs EXP-2589
direct advisor) and ISF (EXP-2861 facts-loader vs EXP-2579/2585 direct
advisor), **no CR-equivalent facts-loader exists in this codebase** --
there is only one meal-response-window-based advisor
(``advise_effective_cr``, EXP-2609). ``advise_cr_adequacy`` (EXP-2535/
2536) exists too, but it takes pre-extracted meal-event dicts rather
than raw arrays, requiring the meal-detection pipeline to be run first;
that additional plumbing is out of scope here and is recorded as a
follow-up rather than silently skipped.

This asymmetry is itself worth recording: CR assessment currently rests
on a single evidence path in this codebase, unlike basal/ISF's two
independently-computed cross-checks. Without a second source, this
module can only report coverage and persistence (temporal stability),
not agreement -- there is nothing to agree or disagree with yet.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .advisor._cr_advisors import advise_effective_cr
from .basal_action_label_benchmark import build_patient_profile
from .therapy_trajectory_state import load_patient_grid, segment_into_turns
from .types import PatientProfile

DEFAULT_WINDOW_DAYS = 14.0
MIN_WINDOW_DAYS_FOR_ADVISOR = 3.0


@dataclass
class CrActionLabel:
    method: str
    direction: str | None
    confidence: float | None
    raw: dict[str, Any] | None = None


def advisor_cr_label(window_df: pd.DataFrame, profile: PatientProfile) -> CrActionLabel:
    """Direction/confidence from meal-response-based effective CR (EXP-2609)."""
    if "time" not in window_df or window_df.empty:
        return CrActionLabel(method="direct_advisor", direction=None, confidence=None)

    days_of_data = (window_df["time"].max() - window_df["time"].min()).total_seconds() / 86400
    if days_of_data < MIN_WINDOW_DAYS_FOR_ADVISOR:
        return CrActionLabel(method="direct_advisor", direction=None, confidence=None)

    glucose = window_df["glucose"].to_numpy(dtype=float)
    hours = window_df["time"].dt.hour.to_numpy(dtype=float)
    bolus = window_df["bolus"].to_numpy(dtype=float) if "bolus" in window_df else None
    carbs = window_df["carbs"].to_numpy(dtype=float) if "carbs" in window_df else None

    recs = advise_effective_cr(
        glucose, hours, profile, bolus=bolus, carbs=carbs, days_of_data=days_of_data,
    )
    if not recs:
        return CrActionLabel(method="direct_advisor", direction="none", confidence=None)

    rec = recs[0]
    return CrActionLabel(
        method="direct_advisor", direction=rec.direction, confidence=rec.confidence,
        raw={"rationale": rec.rationale},
    )


def benchmark_patient_cr_labels(
    parquet_dir: Path | str,
    patient_id: str,
    window_days: float = DEFAULT_WINDOW_DAYS,
) -> list[dict[str, Any]]:
    df = load_patient_grid(parquet_dir, patient_id)
    profile = build_patient_profile(df)
    boundaries = segment_into_turns(df, turn_hours=window_days * 24.0)

    windows: list[dict[str, Any]] = []
    for idx, (start, end) in enumerate(boundaries):
        window_df = df[(df["time"] >= start) & (df["time"] < end)]
        advisor = (
            advisor_cr_label(window_df, profile) if profile is not None
            else CrActionLabel(method="direct_advisor", direction=None, confidence=None)
        )
        windows.append({
            "patient_id": patient_id,
            "window_index": idx,
            "start": start,
            "end": end,
            "window_days": window_days,
            "advisor_direction": advisor.direction,
            "advisor_confidence": advisor.confidence,
        })
    return windows


def benchmark_cohort_cr_labels(
    parquet_dir: Path | str,
    patient_ids: list[str] | None = None,
    window_days: float = DEFAULT_WINDOW_DAYS,
    min_windows: int = 2,
) -> pd.DataFrame:
    grid_path = Path(parquet_dir) / "grid.parquet"
    df_all = pd.read_parquet(grid_path, columns=["patient_id"])
    available = sorted(df_all["patient_id"].unique())
    ids = patient_ids if patient_ids is not None else available

    all_windows: list[dict[str, Any]] = []
    for patient_id in ids:
        if patient_id not in available:
            continue
        windows = benchmark_patient_cr_labels(parquet_dir, patient_id, window_days=window_days)
        if len(windows) < min_windows:
            continue
        all_windows.extend(windows)
    return pd.DataFrame.from_records(all_windows)


def _persistence_rate(df: pd.DataFrame, direction_col: str) -> float | None:
    rows = []
    for patient_id, g in df.sort_values("window_index").groupby("patient_id"):
        directions = g[direction_col].tolist()
        for i in range(len(directions) - 1):
            current, nxt = directions[i], directions[i + 1]
            if current in (None, "none") or nxt is None:
                continue
            rows.append(current == nxt)
    if not rows:
        return None
    return float(np.mean(rows))


def summarize_cr_label_benchmark(df: pd.DataFrame) -> dict[str, Any]:
    """Coverage and persistence for the single available CR label source.

    No ``agreement`` field: unlike basal/ISF, there is no second
    independently-computed label to agree or disagree with (see module
    docstring).
    """
    if df.empty:
        return {"n_windows": 0}

    advisor_covered = df["advisor_direction"].notna()
    return {
        "n_windows": len(df),
        "n_patients": int(df["patient_id"].nunique()),
        "coverage_direct_advisor": float(advisor_covered.mean()),
        "advisor_direction_counts": df["advisor_direction"].value_counts(dropna=False).to_dict(),
        "persistence_direct_advisor": _persistence_rate(df, "advisor_direction"),
        "note": (
            "No CR-equivalent facts-loader exists in this codebase, so only "
            "coverage and persistence are reported for the single available "
            "method (advise_effective_cr, EXP-2609); see module docstring."
        ),
    }
