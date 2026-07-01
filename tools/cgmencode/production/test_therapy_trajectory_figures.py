"""Unit tests for therapy_trajectory_figures.py.

Only checks that figure generation runs without error and returns
well-formed output on small synthetic frames — not pixel content.
"""
from __future__ import annotations

import base64

import pandas as pd
import pytest

from tools.cgmencode.production.therapy_trajectory_figures import (
    auc_comparison_figure,
    build_trajectory_figures,
    controller_tir_figure,
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


def test_auc_comparison_figure_smoke():
    summary = {
        "baseline": {"auc_pooled": 0.638}, "full": {"auc_pooled": 0.615},
        "n_samples": 1347, "n_groups": 28, "delta_auc_from_physiology_features": -0.022,
    }
    fig = auc_comparison_figure(summary)
    assert fig is not None
    assert base64.b64decode(fig.png_base64)
    assert "not yet" in fig.caption


def test_auc_comparison_figure_with_refined_bar():
    summary = {
        "baseline": {"auc_pooled": 0.638}, "full": {"auc_pooled": 0.615},
        "refined": {"auc_pooled": 0.612},
        "n_samples": 1347, "n_groups": 28,
        "delta_auc_from_physiology_features": -0.022,
        "delta_auc_refined_vs_baseline": -0.025,
    }
    fig = auc_comparison_figure(summary)
    assert fig is not None
    assert base64.b64decode(fig.png_base64)
    assert "recency/momentum" in fig.caption


def test_auc_comparison_figure_missing_data():
    assert auc_comparison_figure({}) is None


def test_controller_tir_figure_smoke():
    summary = {
        "mean_tir_by_controller": {"loop": 63.6, "trio_openaps": 81.0},
        "n_patients_with_known_controller": 21,
        "controller_identity_within_patient_lift": 0.005,
    }
    fig = controller_tir_figure(summary)
    assert fig is not None
    assert base64.b64decode(fig.png_base64)


def test_controller_tir_figure_missing_data():
    assert controller_tir_figure({}) is None


def test_build_trajectory_figures_returns_expected_count():
    df = _synthetic_turns(n_patients=3)
    figures = build_trajectory_figures(df, max_timelines=2)
    # 4 cohort-level figures + up to max_timelines per-patient timelines
    assert len(figures) == 4 + 2


def test_build_trajectory_figures_includes_validation_figures_when_provided():
    df = _synthetic_turns(n_patients=3)
    validation_summary = {
        "baseline": {"auc_pooled": 0.6}, "full": {"auc_pooled": 0.58},
        "n_samples": 100, "n_groups": 3, "delta_auc_from_physiology_features": -0.02,
    }
    controller_summary = {
        "mean_tir_by_controller": {"loop": 60.0, "trio_openaps": 75.0},
        "n_patients_with_known_controller": 3,
        "controller_identity_within_patient_lift": 0.01,
    }
    figures = build_trajectory_figures(
        df, max_timelines=1,
        validation_summary=validation_summary, controller_summary=controller_summary,
    )
    # 4 cohort-level + 2 validation figures + 1 timeline
    assert len(figures) == 4 + 2 + 1
