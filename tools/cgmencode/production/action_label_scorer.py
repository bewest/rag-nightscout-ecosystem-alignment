"""action_label_scorer.py — unified, research-stage action-label scorer.

Packages the per-domain findings from the basal/ISF/CR action-label
benchmarks (`basal_action_label_benchmark.py`, `isf_action_label_benchmark.py`,
`cr_action_label_benchmark.py`; see
docs/60-research/state-aware-harness-parallels-2026-07-01.md §7) into one
function that scores a patient's *current* (most recent complete window)
action-needed state per domain, using each domain's empirically preferred
method and evidence-window length:

  * **basal** -- direct-advisor (`advise_overnight_basal_quadrant`) as the
    primary method (100% coverage, higher persistence); facts-loader
    (`compute_basal_mismatch`) direction is surfaced too, when available,
    as a corroboration signal rather than a second vote.
  * **isf** -- facts-loader (`compute_isf_gap_bootstrap`) as the primary
    method, since it was dramatically more temporally stable (86.0% vs
    61.0% persistence) despite lower coverage; direct-advisor
    (`advise_correction_isf`) is surfaced as a fallback/corroboration
    when the facts-loader has no signal for this window.
  * **cr** -- direct-advisor (`advise_effective_cr`), the only method
    available for this domain, using the longer 30-day window that
    showed better persistence than 14 days.

This is explicitly a **research-stage artifact** (per the MLflow
promotion ladder in
docs/60-research/mlflow-experience-report-2026-06-27.md): it is NOT
wired into `ClinicalDecisionPolicy` or `ClinicalDecisionReport`, and
should not be treated as a validated recommendation source without
further clinical review. Its purpose is to make the benchmarked methods
callable as one coherent unit for future evaluation, not to change any
production recommendation today.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .basal_action_label_benchmark import (
    advisor_basal_label,
    build_patient_profile,
    facts_loader_basal_label,
)
from .cr_action_label_benchmark import advisor_cr_label
from .isf_action_label_benchmark import advisor_isf_label, facts_loader_isf_label
from .therapy_trajectory_state import load_patient_grid, segment_into_turns

PROMOTION_STAGE = "research"  # per the MLflow promotion ladder; not yet
                               # "candidate" or beyond.

# Empirically preferred evidence-window length per domain (§7.6).
BASAL_WINDOW_DAYS = 14.0
ISF_WINDOW_DAYS = 14.0
CR_WINDOW_DAYS = 30.0


@dataclass
class DomainActionScore:
    domain: str                    # "basal" | "isf" | "cr"
    primary_method: str
    direction: str | None          # "increase" | "decrease" | "none" | None
    confidence: float | None
    corroborating_method: str | None = None
    corroborating_direction: str | None = None
    agrees_with_primary: bool | None = None


def _latest_window(df: pd.DataFrame, window_days: float) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    boundaries = segment_into_turns(df, turn_hours=window_days * 24.0)
    return boundaries[-1] if boundaries else None


def score_basal_action(parquet_dir: Path | str, patient_id: str) -> DomainActionScore:
    df = load_patient_grid(parquet_dir, patient_id)
    profile = build_patient_profile(df)
    window = _latest_window(df, BASAL_WINDOW_DAYS)
    if window is None:
        return DomainActionScore("basal", "direct_advisor", None, None)

    start, end = window
    window_df = df[(df["time"] >= start) & (df["time"] < end)]
    primary = advisor_basal_label(window_df, profile) if profile is not None else None
    corroborating = facts_loader_basal_label(window_df)

    primary_direction = primary.direction if primary else None
    primary_confidence = primary.confidence if primary else None
    return DomainActionScore(
        domain="basal", primary_method="direct_advisor",
        direction=primary_direction, confidence=primary_confidence,
        corroborating_method="facts_loader",
        corroborating_direction=corroborating.direction,
        agrees_with_primary=(
            corroborating.direction == primary_direction
            if corroborating.direction is not None and primary_direction is not None
            else None
        ),
    )


def score_isf_action(parquet_dir: Path | str, patient_id: str) -> DomainActionScore:
    df = load_patient_grid(parquet_dir, patient_id)
    profile = build_patient_profile(df)
    window = _latest_window(df, ISF_WINDOW_DAYS)
    if window is None:
        return DomainActionScore("isf", "facts_loader", None, None)

    start, end = window
    window_df = df[(df["time"] >= start) & (df["time"] < end)]
    primary = facts_loader_isf_label(window_df)
    corroborating = (
        advisor_isf_label(window_df, profile) if profile is not None else None
    )

    direction = primary.direction
    confidence = primary.confidence
    corroborating_direction = corroborating.direction if corroborating else None
    # Facts-loader is primary but has lower coverage than the advisor; if
    # it has no signal for this window, fall back to the advisor rather
    # than reporting nothing.
    used_fallback = direction is None and corroborating_direction is not None
    if used_fallback:
        direction = corroborating_direction
        confidence = corroborating.confidence if corroborating else None

    return DomainActionScore(
        domain="isf",
        primary_method="direct_advisor (fallback)" if used_fallback else "facts_loader",
        direction=direction, confidence=confidence,
        corroborating_method="direct_advisor" if not used_fallback else "facts_loader",
        corroborating_direction=corroborating_direction if not used_fallback else primary.direction,
        agrees_with_primary=(
            None if used_fallback else (
                corroborating_direction == direction
                if corroborating_direction is not None and direction is not None
                else None
            )
        ),
    )


def score_cr_action(parquet_dir: Path | str, patient_id: str) -> DomainActionScore:
    df = load_patient_grid(parquet_dir, patient_id)
    profile = build_patient_profile(df)
    window = _latest_window(df, CR_WINDOW_DAYS)
    if window is None:
        return DomainActionScore("cr", "direct_advisor", None, None)

    start, end = window
    window_df = df[(df["time"] >= start) & (df["time"] < end)]
    primary = advisor_cr_label(window_df, profile) if profile is not None else None

    return DomainActionScore(
        domain="cr", primary_method="direct_advisor",
        direction=primary.direction if primary else None,
        confidence=primary.confidence if primary else None,
        # No second CR method exists yet (§7.5) -- no corroboration to report.
    )


def score_patient_actions(parquet_dir: Path | str, patient_id: str) -> dict[str, Any]:
    """Score all three domains for a patient's most recent complete window.

    Returns a plain dict (not wired into any production recommendation
    path) tagged with ``promotion_stage`` so callers/loggers can see this
    is research-stage evidence, not a validated recommendation.
    """
    basal = score_basal_action(parquet_dir, patient_id)
    isf = score_isf_action(parquet_dir, patient_id)
    cr = score_cr_action(parquet_dir, patient_id)

    def _as_dict(score: DomainActionScore) -> dict[str, Any]:
        return {
            "domain": score.domain,
            "primary_method": score.primary_method,
            "direction": score.direction,
            "confidence": score.confidence,
            "corroborating_method": score.corroborating_method,
            "corroborating_direction": score.corroborating_direction,
            "agrees_with_primary": score.agrees_with_primary,
        }

    return {
        "patient_id": patient_id,
        "promotion_stage": PROMOTION_STAGE,
        "basal": _as_dict(basal),
        "isf": _as_dict(isf),
        "cr": _as_dict(cr),
    }
