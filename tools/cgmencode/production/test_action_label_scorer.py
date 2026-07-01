"""Unit tests for action_label_scorer.py."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tools.cgmencode.production.action_label_scorer import (
    PROMOTION_STAGE,
    score_basal_action,
    score_cr_action,
    score_isf_action,
    score_patient_actions,
)


def _full_domain_grid(days: float, actual_mult: float = 1.2, patient_id: str = "p1") -> pd.DataFrame:
    """A synthetic grid with every column any of the three domain
    advisors/facts-loaders touch, so the scorer can run end-to-end
    without column-shape errors (unlike the single-domain fixtures used
    by the individual benchmark test files)."""
    n = int(days * 24 * 60 / 5)
    time = pd.date_range("2026-01-05", periods=n, freq="5min", tz="UTC")
    scheduled = 0.8
    return pd.DataFrame({
        "patient_id": patient_id,
        "time": time,
        "glucose": np.full(n, 110.0),
        "glucose_roc": np.zeros(n),
        "cob": np.zeros(n),
        "carbs": np.zeros(n),
        "bolus": np.zeros(n),
        "bolus_smb": np.zeros(n),
        "iob": np.zeros(n),
        "time_since_bolus_min": np.full(n, 1e6),
        "exercise_active": np.zeros(n, dtype=bool),
        "override_active": np.zeros(n, dtype=bool),
        "actual_basal_rate": np.full(n, scheduled * actual_mult),
        "scheduled_basal_rate": np.full(n, scheduled),
        "scheduled_isf": np.full(n, 50.0),
        "scheduled_cr": np.full(n, 10.0),
    })


def test_score_basal_action_end_to_end(tmp_path):
    df = _full_domain_grid(days=30.0, actual_mult=1.4, patient_id="p1")
    df.to_parquet(tmp_path / "grid.parquet")

    score = score_basal_action(tmp_path, "p1")
    assert score.domain == "basal"
    assert score.primary_method == "direct_advisor"
    # Actual basal running high vs scheduled -> some directional signal
    # expected from at least one of the two methods.
    assert score.direction is not None or score.corroborating_direction is not None


def test_score_isf_action_falls_back_when_facts_loader_has_no_signal(tmp_path):
    # A grid with too few correction events for the facts-loader bootstrap
    # (needs >=20 events) but enough for a plausible advisor read.
    df = _full_domain_grid(days=14.0, actual_mult=1.0, patient_id="p1")
    df.to_parquet(tmp_path / "grid.parquet")

    score = score_isf_action(tmp_path, "p1")
    assert score.domain == "isf"
    # No correction events at all in this fixture -> both methods should
    # report no signal, and the scorer should not crash.
    assert score.direction in (None, "none")


def test_score_cr_action_end_to_end(tmp_path):
    df = _full_domain_grid(days=30.0, actual_mult=1.0, patient_id="p1")
    df.to_parquet(tmp_path / "grid.parquet")

    score = score_cr_action(tmp_path, "p1")
    assert score.domain == "cr"
    assert score.primary_method == "direct_advisor"
    # No CR-equivalent second method exists.
    assert score.corroborating_method is None


def test_score_patient_actions_tags_research_stage(tmp_path):
    df = _full_domain_grid(days=30.0, actual_mult=1.2, patient_id="p1")
    df.to_parquet(tmp_path / "grid.parquet")

    result = score_patient_actions(tmp_path, "p1")
    assert result["promotion_stage"] == PROMOTION_STAGE == "research"
    assert set(result.keys()) >= {"patient_id", "promotion_stage", "basal", "isf", "cr"}
    for domain in ("basal", "isf", "cr"):
        assert result[domain]["domain"] == domain
