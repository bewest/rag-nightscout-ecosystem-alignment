"""Unit tests for isf_action_label_benchmark.py."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tools.cgmencode.production.isf_action_label_benchmark import (
    advisor_isf_label,
    benchmark_cohort_isf_labels,
    facts_loader_isf_label,
    summarize_isf_label_benchmark,
)
from tools.cgmencode.production.basal_action_label_benchmark import build_patient_profile


def _correction_event_grid(
    days: float, obs_isf: float, sched_isf: float = 50.0,
    patient_id: str = "p1", n_events: int = 30,
) -> pd.DataFrame:
    """A synthetic grid with clean 5-min baseline glucose plus a set of
    correction-bolus events spaced evenly through the window, each
    dropping glucose by ``obs_isf`` mg/dL per unit bolused -- so the
    observed ISF is controllable and known."""
    n = int(days * 24 * 60 / 5)
    time = pd.date_range("2026-01-05", periods=n, freq="5min", tz="UTC")
    glucose = np.full(n, 120.0)
    bolus = np.zeros(n)
    carbs = np.zeros(n)
    iob = np.zeros(n)

    # Space correction events evenly, each a 2U dose at glucose=220,
    # producing an actual drop of obs_isf * 2 over the following 3h.
    spacing = max(1, (n - 400) // max(1, n_events))
    dose = 2.0
    for k in range(n_events):
        i = 100 + k * spacing
        if i + 40 >= n:
            break
        glucose[i] = 220.0
        bolus[i] = dose
        drop = obs_isf * dose
        # Linear glucose decay over the next 36 steps (3h), then flat.
        for j in range(1, 37):
            idx = i + j
            if idx < n:
                glucose[idx] = 220.0 - drop * (j / 36.0)
        for j in range(37, min(60, n - i)):
            glucose[i + j] = 220.0 - drop

    return pd.DataFrame({
        "patient_id": patient_id,
        "time": time,
        "glucose": glucose,
        "bolus": bolus,
        "bolus_smb": np.zeros(n),
        "carbs": carbs,
        "iob": iob,
        "scheduled_isf": np.full(n, sched_isf),
        "scheduled_cr": np.full(n, 10.0),
        "scheduled_basal_rate": np.full(n, 0.8),
    })


def test_facts_loader_isf_label_detects_under_correction():
    # obs_isf << sched_isf -> each unit does much less work than expected
    # -> under-correction -> "decrease" (dose more aggressively).
    df = _correction_event_grid(days=14.0, obs_isf=20.0, sched_isf=50.0)
    label = facts_loader_isf_label(df)
    assert label.direction == "decrease"


def test_facts_loader_isf_label_detects_over_correction():
    # obs_isf >> sched_isf -> corrections work much harder than expected
    # -> over-correction -> "increase" (dose less aggressively).
    df = _correction_event_grid(days=14.0, obs_isf=90.0, sched_isf=50.0)
    label = facts_loader_isf_label(df)
    assert label.direction == "increase"


def test_facts_loader_isf_label_insufficient_events_returns_none():
    df = _correction_event_grid(days=14.0, obs_isf=50.0, n_events=2)
    label = facts_loader_isf_label(df)
    assert label.direction is None


def test_advisor_isf_label_insufficient_days_returns_none():
    df = _correction_event_grid(days=1.0, obs_isf=50.0, n_events=5)
    profile = build_patient_profile(df)
    label = advisor_isf_label(df, profile)
    assert label.direction is None


def test_advisor_isf_label_runs_on_sufficient_data():
    df = _correction_event_grid(days=14.0, obs_isf=90.0, sched_isf=50.0, n_events=30)
    profile = build_patient_profile(df)
    label = advisor_isf_label(df, profile)
    # Direction may be None/none if the counter-regulation model doesn't
    # clear its own internal threshold, but it must not error and must
    # return one of the expected values.
    assert label.direction in (None, "none", "increase", "decrease")


def test_summarize_isf_label_benchmark_empty():
    assert summarize_isf_label_benchmark(pd.DataFrame())["n_windows"] == 0


def test_summarize_isf_label_benchmark_coverage_and_agreement():
    df = pd.DataFrame([
        {"patient_id": "a", "window_index": 0, "facts_direction": "increase", "advisor_direction": "increase"},
        {"patient_id": "a", "window_index": 1, "facts_direction": "decrease", "advisor_direction": "decrease"},
        {"patient_id": "a", "window_index": 2, "facts_direction": None, "advisor_direction": "none"},
    ])
    summary = summarize_isf_label_benchmark(df)
    assert summary["n_windows"] == 3
    assert summary["coverage_facts_loader"] == pytest.approx(2 / 3)
    assert summary["coverage_direct_advisor"] == pytest.approx(1.0)
    assert summary["agreement_where_both_covered"] == pytest.approx(1.0)


def test_benchmark_cohort_isf_labels_end_to_end(tmp_path):
    df_a = _correction_event_grid(days=30.0, obs_isf=20.0, sched_isf=50.0, patient_id="a", n_events=40)
    df_b = _correction_event_grid(days=30.0, obs_isf=90.0, sched_isf=50.0, patient_id="b", n_events=40)
    combined = pd.concat([df_a, df_b], ignore_index=True)
    grid_path = tmp_path / "grid.parquet"
    combined.to_parquet(grid_path)

    results = benchmark_cohort_isf_labels(tmp_path, window_days=14.0, min_windows=1)
    assert not results.empty
    assert set(results["patient_id"].unique()) == {"a", "b"}
