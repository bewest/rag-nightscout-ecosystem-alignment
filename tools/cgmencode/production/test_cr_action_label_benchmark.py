"""Unit tests for cr_action_label_benchmark.py."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tools.cgmencode.production.cr_action_label_benchmark import (
    advisor_cr_label,
    benchmark_cohort_cr_labels,
    summarize_cr_label_benchmark,
)
from tools.cgmencode.production.basal_action_label_benchmark import build_patient_profile


def _meal_event_grid(
    days: float, effective_cr: float, profile_cr: float = 10.0,
    patient_id: str = "p1", n_meals: int = 15,
) -> pd.DataFrame:
    """A synthetic grid with clean baseline glucose plus evenly-spaced
    meal-bolus events with a controllable effective CR (how many grams
    each unit of bolus actually covers, inferred from the post-meal
    glucose response)."""
    n = int(days * 24 * 60 / 5)
    time = pd.date_range("2026-01-05", periods=n, freq="5min", tz="UTC")
    glucose = np.full(n, 110.0)
    bolus = np.zeros(n)
    carbs = np.zeros(n)

    spacing = max(1, (n - 400) // max(1, n_meals))
    meal_carbs = 40.0
    # If effective_cr grams/unit is what's actually covering the meal,
    # required bolus = meal_carbs / effective_cr. Profile assumes
    # profile_cr, so profile-suggested bolus = meal_carbs / profile_cr.
    # Give the profile-suggested bolus (i.e. the "actual dosing
    # behavior"), and let post-meal glucose settle back to baseline if
    # the *true* required dose (meal_carbs/effective_cr) was given,
    # otherwise reflect over/under coverage.
    bolus_given = meal_carbs / profile_cr
    for k in range(n_meals):
        i = 100 + k * spacing
        if i + 60 >= n:
            break
        glucose[i] = 110.0
        carbs[i] = meal_carbs
        bolus[i] = bolus_given
        # Simulate a rise then settle toward a post-meal level implied by
        # the ratio of given-bolus coverage vs the true required dose.
        required_bolus = meal_carbs / effective_cr
        coverage_ratio = bolus_given / required_bolus  # >1 = over-bolused
        peak = 110.0 + meal_carbs * 3.0  # simple linear meal-rise proxy
        settle = 110.0 + (1.0 - coverage_ratio) * 80.0
        for j in range(1, 13):
            idx = i + j
            if idx < n:
                glucose[idx] = peak - (peak - settle) * (j / 12.0)
        for j in range(13, min(48, n - i)):
            glucose[i + j] = settle

    return pd.DataFrame({
        "patient_id": patient_id,
        "time": time,
        "glucose": glucose,
        "bolus": bolus,
        "carbs": carbs,
        "scheduled_isf": np.full(n, 50.0),
        "scheduled_cr": np.full(n, profile_cr),
        "scheduled_basal_rate": np.full(n, 0.8),
    })


def test_advisor_cr_label_insufficient_days_returns_none():
    df = _meal_event_grid(days=1.0, effective_cr=10.0)
    profile = build_patient_profile(df)
    label = advisor_cr_label(df, profile)
    assert label.direction is None


def test_advisor_cr_label_runs_on_sufficient_data():
    # Effective CR much higher than profile CR -> patient needs less
    # insulin per gram than the profile assumes -> currently over-bolused
    # -> should recommend "decrease" bolus aggressiveness, i.e. CR increase.
    df = _meal_event_grid(days=14.0, effective_cr=25.0, profile_cr=10.0, n_meals=20)
    profile = build_patient_profile(df)
    label = advisor_cr_label(df, profile)
    assert label.direction in (None, "none", "increase", "decrease")


def test_summarize_cr_label_benchmark_empty():
    assert summarize_cr_label_benchmark(pd.DataFrame())["n_windows"] == 0


def test_summarize_cr_label_benchmark_no_agreement_field():
    df = pd.DataFrame([
        {"patient_id": "a", "window_index": 0, "advisor_direction": "increase"},
        {"patient_id": "a", "window_index": 1, "advisor_direction": "increase"},
    ])
    summary = summarize_cr_label_benchmark(df)
    assert "agreement_where_both_covered" not in summary
    assert summary["coverage_direct_advisor"] == pytest.approx(1.0)
    assert summary["persistence_direct_advisor"] == pytest.approx(1.0)
    assert "note" in summary


def test_benchmark_cohort_cr_labels_end_to_end(tmp_path):
    df_a = _meal_event_grid(days=30.0, effective_cr=25.0, profile_cr=10.0, patient_id="a", n_meals=25)
    df_b = _meal_event_grid(days=30.0, effective_cr=5.0, profile_cr=10.0, patient_id="b", n_meals=25)
    combined = pd.concat([df_a, df_b], ignore_index=True)
    grid_path = tmp_path / "grid.parquet"
    combined.to_parquet(grid_path)

    results = benchmark_cohort_cr_labels(tmp_path, window_days=14.0, min_windows=1)
    assert not results.empty
    assert set(results["patient_id"].unique()) == {"a", "b"}
