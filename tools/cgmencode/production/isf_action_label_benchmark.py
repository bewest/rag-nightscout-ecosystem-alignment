"""isf_action_label_benchmark.py — comparing two ways to derive an ISF
action-needed label (increase/decrease/none) per decision window.

Second domain in the action-space label pivot (see
docs/60-research/state-aware-harness-parallels-2026-07-01.md §7.2-§7.3
for the basal precedent this mirrors). Two label sources already exist
in this codebase for "does ISF need to change":

  * **facts-loader style** (``compute_isf_gap_bootstrap``, EXP-2861):
    bootstraps the raw observed-vs-scheduled ISF gap directly from
    correction events (bolus >= 0.5U, glucose >= 180, no recent carbs),
    with an asymmetric under/over-correction band.
  * **direct advisor** (``advise_correction_isf``, EXP-2579/2582/2585/2588):
    fits a counter-regulation model (partially correcting for AID
    controller compensation) to a similar but not identical correction-
    event definition (bolus >= 0.5U, glucose >= 150), then calibrates an
    ISF multiplier from it.

Both operate on correction events rather than a fixed calendar window,
so -- unlike basal, which needed several *clean overnight/fasting*
segments -- what matters here is accumulating enough correction events
(each method's own minimum event count, 20 for both), which can take
longer or shorter than 14 days depending on how often a patient
corrects. This module benchmarks both at two window lengths (14 and 30
days) to check whether the evidence window itself should differ from
the basal domain's, per the observation that different signals may
need different time horizons.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ._per_patient_compute import compute_isf_gap_bootstrap
from .advisor._isf_advisors import advise_correction_isf
from .basal_action_label_benchmark import build_patient_profile
from .therapy_trajectory_state import load_patient_grid, segment_into_turns
from .types import PatientProfile

DEFAULT_WINDOW_DAYS = 14.0
MIN_WINDOW_DAYS_FOR_ADVISOR = 3.0


@dataclass
class IsfActionLabel:
    method: str
    direction: str | None
    confidence: float | None
    raw: dict[str, Any] | None = None


def facts_loader_isf_label(window_df: pd.DataFrame) -> IsfActionLabel:
    """Direction/confidence from the raw observed-vs-scheduled ISF gap
    bootstrap (EXP-2861)."""
    result = compute_isf_gap_bootstrap(window_df)
    if result is None or result.get("_insufficient"):
        return IsfActionLabel(method="facts_loader", direction=None, confidence=None, raw=result)

    p_under = result.get("p_under_correction")
    p_over = result.get("p_over_correction")
    if p_under is None or p_over is None:
        return IsfActionLabel(method="facts_loader", direction=None, confidence=None, raw=result)

    # Under-correction (gap < -10%: each unit did less work than expected)
    # -> ISF number should decrease to dose more aggressively. Over-
    # correction (gap > +30%) -> ISF should increase. Whichever band the
    # bootstrap distribution favors more strongly wins; if neither band
    # dominates, "none".
    if p_under > 0.5 and p_under >= p_over:
        direction, confidence = "decrease", p_under
    elif p_over > 0.5 and p_over > p_under:
        direction, confidence = "increase", p_over
    else:
        direction, confidence = "none", max(p_under, p_over)
    return IsfActionLabel(method="facts_loader", direction=direction, confidence=confidence, raw=result)


def advisor_isf_label(window_df: pd.DataFrame, profile: PatientProfile) -> IsfActionLabel:
    """Direction/confidence from the counter-regulation-corrected
    correction-ISF advisor (EXP-2579/2582/2585/2588)."""
    if "time" not in window_df or window_df.empty:
        return IsfActionLabel(method="direct_advisor", direction=None, confidence=None)

    days_of_data = (window_df["time"].max() - window_df["time"].min()).total_seconds() / 86400
    if days_of_data < MIN_WINDOW_DAYS_FOR_ADVISOR:
        return IsfActionLabel(method="direct_advisor", direction=None, confidence=None)

    glucose = window_df["glucose"].to_numpy(dtype=float)
    hours = window_df["time"].dt.hour.to_numpy(dtype=float)
    bolus = window_df["bolus"].to_numpy(dtype=float) if "bolus" in window_df else None
    carbs = window_df["carbs"].to_numpy(dtype=float) if "carbs" in window_df else None
    iob = window_df["iob"].to_numpy(dtype=float) if "iob" in window_df else None

    recs = advise_correction_isf(
        glucose, hours, profile, bolus=bolus, carbs=carbs, iob=iob, days_of_data=days_of_data,
    )
    if not recs:
        return IsfActionLabel(method="direct_advisor", direction="none", confidence=None)

    rec = recs[0]
    return IsfActionLabel(
        method="direct_advisor", direction=rec.direction, confidence=rec.confidence,
        raw={"rationale": rec.rationale},
    )


def benchmark_patient_isf_labels(
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
        facts = facts_loader_isf_label(window_df)
        advisor = (
            advisor_isf_label(window_df, profile) if profile is not None
            else IsfActionLabel(method="direct_advisor", direction=None, confidence=None)
        )
        windows.append({
            "patient_id": patient_id,
            "window_index": idx,
            "start": start,
            "end": end,
            "window_days": window_days,
            "facts_direction": facts.direction,
            "facts_confidence": facts.confidence,
            "advisor_direction": advisor.direction,
            "advisor_confidence": advisor.confidence,
        })
    return windows


def benchmark_cohort_isf_labels(
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
        windows = benchmark_patient_isf_labels(parquet_dir, patient_id, window_days=window_days)
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


def summarize_isf_label_benchmark(df: pd.DataFrame) -> dict[str, Any]:
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
