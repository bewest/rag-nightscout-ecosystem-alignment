"""Unit tests for therapy_trajectory_figures.py.

Only checks that figure generation runs without error and returns
well-formed output on small synthetic frames — not pixel content.
"""
from __future__ import annotations

import base64

import pandas as pd
import pytest

from tools.cgmencode.production.therapy_trajectory_figures import (
    build_trajectory_figures,
    mean_tir_by_state_figure,
    patient_timeline_figure,
    saturation_by_state_figure,
    state_distribution_figure,
    weekend_fraction_vs_tir_figure,
)

matplotlib = pytest.importorskip("matplotlib")


def _synthetic_turns(n_patients: int = 2, n_turns: int = 6) -> pd.DataFrame:
    rows = []
    states = ["improving", "stable_good", "stable_poor", "worsening", "unknown"]
    for p in range(n_patients):
        patient_id = f"p{p}"
        for t in range(n_turns):
            start = pd.Timestamp("2026-01-01", tz="UTC") + pd.Timedelta(hours=72 * t)
            rows.append({
                "patient_id": patient_id,
                "turn_index": t,
                "start": start,
                "end": start + pd.Timedelta(hours=72),
                "data_completeness": 0.9,
                "tir": 50.0 + 3 * t + 5 * p,
                "tbr_l1": 2.0,
                "tbr_l2": 0.5,
                "weekend_day_fraction": (t % 3) / 3.0,
                "saturation_wall_pct": 10.0 * (t % 4),
                "state": states[t % len(states)],
            })
    return pd.DataFrame(rows)


def test_state_distribution_figure_smoke():
    df = _synthetic_turns()
    fig = state_distribution_figure(df)
    assert fig is not None
    assert base64.b64decode(fig.png_base64)  # decodes without error


def test_state_distribution_figure_empty_df():
    assert state_distribution_figure(pd.DataFrame()) is None


def test_mean_tir_by_state_figure_smoke():
    df = _synthetic_turns()
    fig = mean_tir_by_state_figure(df)
    assert fig is not None
    assert base64.b64decode(fig.png_base64)


def test_saturation_by_state_figure_smoke():
    df = _synthetic_turns()
    fig = saturation_by_state_figure(df)
    assert fig is not None
    assert base64.b64decode(fig.png_base64)


def test_weekend_fraction_vs_tir_figure_smoke():
    df = _synthetic_turns()
    fig = weekend_fraction_vs_tir_figure(df)
    assert fig is not None
    assert base64.b64decode(fig.png_base64)


def test_weekend_fraction_vs_tir_figure_insufficient_variation():
    df = _synthetic_turns()
    df["weekend_day_fraction"] = 0.5  # no variation -> figure should be skipped
    assert weekend_fraction_vs_tir_figure(df) is None


def test_patient_timeline_figure_smoke():
    df = _synthetic_turns()
    fig = patient_timeline_figure(df, "p0")
    assert fig is not None
    assert "p0" in fig.title
    assert base64.b64decode(fig.png_base64)


def test_patient_timeline_figure_unknown_patient():
    df = _synthetic_turns()
    assert patient_timeline_figure(df, "does-not-exist") is None


def test_build_trajectory_figures_returns_expected_count():
    df = _synthetic_turns(n_patients=3)
    figures = build_trajectory_figures(df, max_timelines=2)
    # 4 cohort-level figures + up to max_timelines per-patient timelines
    assert len(figures) == 4 + 2
