"""basal_action_label_benchmark.py — comparing two ways to derive a
basal action-needed label (increase/decrease/none) per decision window.

Motivated by a design question: instead of a generic glycemic
resolved/unresolved label (which tested null for predicting from
physiology features — see
docs/60-research/state-aware-harness-parallels-2026-07-01.md §6.4), the
"states" most useful for decision support are the actual recommender
action space: does basal need to change (increase/decrease/none), at
which time block, and with what confidence. Two label sources already
exist in this codebase for that question, and this module benchmarks
them against each other rather than assuming one is better:

  * **facts-loader style** (``compute_basal_mismatch``, EXP-2865/2869):
    uses the *controller's own actual-vs-scheduled basal ratio* during
    fasting-equilibrium windows (COB=0, no recent carbs/bolus/exercise/
    override, flat glucose ROC) as a revealed-preference signal, grouped
    into 4 time-of-day blocks (night/morning/afternoon/evening).
  * **direct advisor** (``advise_overnight_basal_quadrant``, EXP-2589):
    uses overnight (00-06h) glucose slope plus net actual-vs-scheduled
    basal to classify into a quadrant (rising/falling x adding/cutting),
    returning a ``SettingsRecommendation`` with direction, confidence,
    and affected hours directly.

Both can be computed on an arbitrary window (not just a whole patient
history), so both are evaluated on the same rolling decision-window
grain here -- 14 days by default, matching the existing
``ClinicalDecisionPolicy`` review cadence, since basal mismatch
detection needs several clean nights/fasting windows to accumulate
enough samples per time-of-day block (unlike the finer 72h turns used
for reading physiology emissions elsewhere in this package).

This is an observational (non-interventional) dataset: no one actually
acted on either method's flagged direction, so we cannot check "did the
recommended change work." Instead this module reports three honest,
computable comparisons:

  1. **Coverage** -- what fraction of windows produce a usable
     (non-None) direction from each method.
  2. **Agreement** -- among windows where both produce a label, how
     often do the directions match (concurrent validity).
  3. **Persistence** -- among windows with a non-"none" label, how
     often does the *same* method's label on the *next* window agree
     (temporal stability/reliability -- a noisy method should flip
     direction at roughly chance rate; a real, stable physiological
     signal should persist).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ._per_patient_compute import compute_basal_mismatch
from .advisor._basal_advisors import advise_overnight_basal_quadrant
from .therapy_trajectory_state import load_patient_grid, segment_into_turns
from .types import PatientProfile

DEFAULT_WINDOW_DAYS = 14.0
MISMATCH_DIRECTION_TOLERANCE = 0.10   # +/-10% band around mult=1.0 -> "none"
MIN_WINDOW_DAYS_FOR_ADVISOR = 3.0     # advise_overnight_basal_quadrant's own floor


@dataclass
class BasalActionLabel:
    method: str                    # "facts_loader" | "direct_advisor"
    direction: str | None          # "increase" | "decrease" | "none" | None (no signal)
    confidence: float | None
    affected_hours: tuple[float, float] | None = None
    raw: dict[str, Any] | None = None


def build_patient_profile(df: pd.DataFrame) -> PatientProfile | None:
    """Same schedule-median pattern used elsewhere in this package
    (``therapy_trajectory_state._build_patient_metabolic_state``)."""
    required = {"scheduled_isf", "scheduled_cr", "scheduled_basal_rate"}
    if not required.issubset(df.columns):
        return None
    isf_median = df["scheduled_isf"].median()
    cr_median = df["scheduled_cr"].median()
    basal_median = df["scheduled_basal_rate"].median()
    if pd.isna(isf_median) or pd.isna(cr_median) or pd.isna(basal_median):
        return None
    return PatientProfile(
        isf_schedule=[{"time": "00:00", "value": float(isf_median)}],
        cr_schedule=[{"time": "00:00", "value": float(cr_median)}],
        basal_schedule=[{"time": "00:00", "value": float(basal_median)}],
        dia_hours=5.0,
    )


def facts_loader_basal_label(window_df: pd.DataFrame) -> BasalActionLabel:
    """Direction/confidence from the controller's revealed-preference
    actual-vs-scheduled basal ratio (EXP-2865/2869)."""
    result = compute_basal_mismatch(window_df)
    if result is None:
        return BasalActionLabel(method="facts_loader", direction=None, confidence=None)

    mult = result["median_recommended_mult"]
    if mult > 1.0 + MISMATCH_DIRECTION_TOLERANCE:
        direction = "increase"
    elif mult < 1.0 - MISMATCH_DIRECTION_TOLERANCE:
        direction = "decrease"
    else:
        direction = "none"
    return BasalActionLabel(
        method="facts_loader", direction=direction,
        confidence=result["max_mismatch_p"], raw=result,
    )


def advisor_basal_label(window_df: pd.DataFrame, profile: PatientProfile) -> BasalActionLabel:
    """Direction/confidence/affected-hours from the overnight quadrant
    advisor (EXP-2589), run directly on this window's arrays."""
    if "time" not in window_df or window_df.empty:
        return BasalActionLabel(method="direct_advisor", direction=None, confidence=None)

    days_of_data = (window_df["time"].max() - window_df["time"].min()).total_seconds() / 86400
    if days_of_data < MIN_WINDOW_DAYS_FOR_ADVISOR:
        return BasalActionLabel(method="direct_advisor", direction=None, confidence=None)

    glucose = window_df["glucose"].to_numpy(dtype=float)
    hours = window_df["time"].dt.hour.to_numpy(dtype=float)
    actual_basal = (
        window_df["actual_basal_rate"].to_numpy(dtype=float)
        if "actual_basal_rate" in window_df else None
    )
    recs = advise_overnight_basal_quadrant(
        glucose, hours, profile, actual_basal=actual_basal, days_of_data=days_of_data,
    )
    if not recs:
        return BasalActionLabel(method="direct_advisor", direction="none", confidence=None)

    rec = recs[0]
    return BasalActionLabel(
        method="direct_advisor", direction=rec.direction, confidence=rec.confidence,
        affected_hours=tuple(rec.affected_hours), raw={"rationale": rec.rationale},
    )


def benchmark_patient_basal_labels(
    parquet_dir: Path | str,
    patient_id: str,
    window_days: float = DEFAULT_WINDOW_DAYS,
) -> list[dict[str, Any]]:
    """Compute both label sources for every rolling decision window of one
    patient's history, plus each method's label on the *next* window
    (for the persistence check)."""
    df = load_patient_grid(parquet_dir, patient_id)
    profile = build_patient_profile(df)
    boundaries = segment_into_turns(df, turn_hours=window_days * 24.0)

    windows: list[dict[str, Any]] = []
    for idx, (start, end) in enumerate(boundaries):
        window_df = df[(df["time"] >= start) & (df["time"] < end)]
        facts = facts_loader_basal_label(window_df)
        advisor = (
            advisor_basal_label(window_df, profile) if profile is not None
            else BasalActionLabel(method="direct_advisor", direction=None, confidence=None)
        )
        windows.append({
            "patient_id": patient_id,
            "window_index": idx,
            "start": start,
            "end": end,
            "facts_direction": facts.direction,
            "facts_confidence": facts.confidence,
            "advisor_direction": advisor.direction,
            "advisor_confidence": advisor.confidence,
        })
    return windows


def benchmark_cohort_basal_labels(
    parquet_dir: Path | str,
    patient_ids: list[str] | None = None,
    window_days: float = DEFAULT_WINDOW_DAYS,
    min_windows: int = 3,
) -> pd.DataFrame:
    """Run the per-patient benchmark across a cohort and concatenate."""
    grid_path = Path(parquet_dir) / "grid.parquet"
    df_all = pd.read_parquet(grid_path, columns=["patient_id"])
    available = sorted(df_all["patient_id"].unique())
    ids = patient_ids if patient_ids is not None else available

    all_windows: list[dict[str, Any]] = []
    for patient_id in ids:
        if patient_id not in available:
            continue
        windows = benchmark_patient_basal_labels(parquet_dir, patient_id, window_days=window_days)
        if len(windows) < min_windows:
            continue
        all_windows.extend(windows)
    return pd.DataFrame.from_records(all_windows)


def _persistence_rate(df: pd.DataFrame, direction_col: str) -> float | None:
    """Among windows with a non-'none'/non-None label, what fraction have
    the *same* method's label agree on the immediately following window
    for the same patient?"""
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


def summarize_basal_label_benchmark(df: pd.DataFrame) -> dict[str, Any]:
    """Coverage, agreement, and persistence for both label sources."""
    if df.empty:
        return {"n_windows": 0}

    n = len(df)
    facts_covered = df["facts_direction"].notna()
    advisor_covered = df["advisor_direction"].notna()
    both_covered = facts_covered & advisor_covered

    agreement = None
    if both_covered.any():
        agreement = float(
            (df.loc[both_covered, "facts_direction"] == df.loc[both_covered, "advisor_direction"]).mean()
        )

    return {
        "n_windows": n,
        "n_patients": int(df["patient_id"].nunique()),
        "coverage_facts_loader": float(facts_covered.mean()),
        "coverage_direct_advisor": float(advisor_covered.mean()),
        "n_both_covered": int(both_covered.sum()),
        "agreement_where_both_covered": agreement,
        "facts_loader_direction_counts": df["facts_direction"].value_counts(dropna=False).to_dict(),
        "advisor_direction_counts": df["advisor_direction"].value_counts(dropna=False).to_dict(),
        "persistence_facts_loader": _persistence_rate(df, "facts_direction"),
        "persistence_direct_advisor": _persistence_rate(df, "advisor_direction"),
    }
