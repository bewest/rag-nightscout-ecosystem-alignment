"""Unit tests for basal_action_label_benchmark.py."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tools.cgmencode.production.basal_action_label_benchmark import (
    advisor_basal_label,
    benchmark_cohort_basal_labels,
    build_patient_profile,
    facts_loader_basal_label,
    summarize_basal_label_benchmark,
)


def _fasting_equilibrium_grid(
    days: float, actual_mult: float = 1.0, patient_id: str = "p1",
) -> pd.DataFrame:
    """A synthetic grid where every row is in "clean fasting equilibrium"
    (no meals/exercise/overrides, flat glucose) so compute_basal_mismatch
    has rows to work with, with actual basal a controllable multiple of
    scheduled basal."""
    n = int(days * 24 * 60 / 5)
    time = pd.date_range("2026-01-05", periods=n, freq="5min", tz="UTC")  # Monday
    scheduled = 0.8
    return pd.DataFrame({
        "patient_id": patient_id,
        "time": time,
        "glucose": np.full(n, 110.0),
        "glucose_roc": np.zeros(n),
        "cob": np.zeros(n),
        "carbs": np.zeros(n),
        "time_since_bolus_min": np.full(n, 1e6),
        "exercise_active": np.zeros(n, dtype=bool),
        "override_active": np.zeros(n, dtype=bool),
        "actual_basal_rate": np.full(n, scheduled * actual_mult),
        "scheduled_basal_rate": np.full(n, scheduled),
        "scheduled_isf": np.full(n, 50.0),
        "scheduled_cr": np.full(n, 10.0),
    })


def test_facts_loader_basal_label_detects_increase():
    # Actual basal running 50% above scheduled at fasting equilibrium ->
    # scheduled basal is too low -> "increase".
    df = _fasting_equilibrium_grid(days=14.0, actual_mult=1.5)
    label = facts_loader_basal_label(df)
    assert label.direction == "increase"
    assert label.confidence is not None


def test_facts_loader_basal_label_detects_decrease():
    df = _fasting_equilibrium_grid(days=14.0, actual_mult=0.5)
    label = facts_loader_basal_label(df)
    assert label.direction == "decrease"


def test_facts_loader_basal_label_none_when_matched():
    df = _fasting_equilibrium_grid(days=14.0, actual_mult=1.0)
    label = facts_loader_basal_label(df)
    assert label.direction == "none"


def test_facts_loader_basal_label_missing_columns_returns_none_direction():
    df = pd.DataFrame({"time": pd.date_range("2026-01-01", periods=10, freq="5min", tz="UTC")})
    label = facts_loader_basal_label(df)
    assert label.direction is None
    assert label.confidence is None


def test_build_patient_profile_missing_columns():
    df = pd.DataFrame({"time": pd.date_range("2026-01-01", periods=10, freq="5min", tz="UTC")})
    assert build_patient_profile(df) is None


def test_build_patient_profile_success():
    df = _fasting_equilibrium_grid(days=3.0)
    profile = build_patient_profile(df)
    assert profile is not None
    assert profile.basal_schedule[0]["value"] == pytest.approx(0.8)


def test_advisor_basal_label_insufficient_days_returns_none():
    df = _fasting_equilibrium_grid(days=1.0)
    profile = build_patient_profile(df)
    label = advisor_basal_label(df, profile)
    assert label.direction is None


def test_advisor_basal_label_flat_data_returns_none_or_no_signal():
    # Perfectly flat overnight glucose slope + matched basal -> advisor
    # should not flag a directional change (either "none" from an empty
    # recommendation list, or no strong quadrant match).
    df = _fasting_equilibrium_grid(days=14.0, actual_mult=1.0)
    profile = build_patient_profile(df)
    label = advisor_basal_label(df, profile)
    assert label.direction in (None, "none")


def test_summarize_basal_label_benchmark_empty():
    assert summarize_basal_label_benchmark(pd.DataFrame())["n_windows"] == 0


def test_summarize_basal_label_benchmark_coverage_and_agreement():
    df = pd.DataFrame([
        {"patient_id": "a", "window_index": 0, "facts_direction": "increase", "advisor_direction": "increase"},
        {"patient_id": "a", "window_index": 1, "facts_direction": "increase", "advisor_direction": "decrease"},
        {"patient_id": "a", "window_index": 2, "facts_direction": None, "advisor_direction": "none"},
    ])
    summary = summarize_basal_label_benchmark(df)
    assert summary["n_windows"] == 3
    assert summary["coverage_facts_loader"] == pytest.approx(2 / 3)
    assert summary["coverage_direct_advisor"] == pytest.approx(1.0)
    assert summary["n_both_covered"] == 2
    assert summary["agreement_where_both_covered"] == pytest.approx(0.5)


def test_summarize_basal_label_benchmark_persistence():
    # Same direction repeated across consecutive windows for patient 'a'
    # (persistent signal) vs alternating for patient 'b' (noisy signal).
    df = pd.DataFrame([
        {"patient_id": "a", "window_index": 0, "facts_direction": "increase", "advisor_direction": None},
        {"patient_id": "a", "window_index": 1, "facts_direction": "increase", "advisor_direction": None},
        {"patient_id": "a", "window_index": 2, "facts_direction": "increase", "advisor_direction": None},
        {"patient_id": "b", "window_index": 0, "facts_direction": "increase", "advisor_direction": None},
        {"patient_id": "b", "window_index": 1, "facts_direction": "decrease", "advisor_direction": None},
    ])
    summary = summarize_basal_label_benchmark(df)
    # 3 consecutive-pair checks total (a:0->1, a:1->2, b:0->1); 2 agree, 1 disagrees.
    assert summary["persistence_facts_loader"] == pytest.approx(2 / 3)


def test_benchmark_cohort_basal_labels_end_to_end(tmp_path):
    df_a = _fasting_equilibrium_grid(days=30.0, actual_mult=1.4, patient_id="a")
    df_b = _fasting_equilibrium_grid(days=30.0, actual_mult=0.6, patient_id="b")
    combined = pd.concat([df_a, df_b], ignore_index=True)
    grid_path = tmp_path / "grid.parquet"
    combined.to_parquet(grid_path)

    results = benchmark_cohort_basal_labels(tmp_path, window_days=14.0, min_windows=1)
    assert not results.empty
    assert set(results["patient_id"].unique()) == {"a", "b"}
    a_directions = set(results.loc[results.patient_id == "a", "facts_direction"])
    b_directions = set(results.loc[results.patient_id == "b", "facts_direction"])
    assert a_directions <= {"increase"}
    assert b_directions <= {"decrease"}
