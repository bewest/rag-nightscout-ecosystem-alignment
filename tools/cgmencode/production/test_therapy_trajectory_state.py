"""Unit tests for therapy_trajectory_state.py.

Uses small synthetic grids (not the real, git-ignored ns-parquet cohort)
so these tests are fast and reproducible in any clone.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tools.cgmencode.production.therapy_trajectory_state import (
    DEFAULT_TURN_HOURS,
    TrajectoryState,
    TurnFeatures,
    build_patient_trajectory,
    compute_turn_features,
    label_turn_outcome,
    segment_into_turns,
)
from tools.cgmencode.production.wear_facts_loader import WearFactsLoader


def _synthetic_grid(patient_id: str = "p1", days: float = 9.0,
                     glucose_value: float = 120.0, start: str = "2026-01-05") -> pd.DataFrame:
    """A uniform 5-min-cadence grid with a controllable glucose level.

    Start date defaults to a Monday so weekday/weekend arithmetic in
    tests is easy to reason about.
    """
    n = int(days * 24 * 60 / 5)
    time = pd.date_range(start=start, periods=n, freq="5min", tz="UTC")
    rng = np.random.default_rng(0)
    return pd.DataFrame({
        "patient_id": patient_id,
        "time": time,
        "glucose": np.full(n, glucose_value) + rng.normal(0, 1e-6, n),
        "iob": np.full(n, 1.0),
        "cob": np.zeros(n),
        "bolus": np.zeros(n),
        "bolus_smb": np.zeros(n),
        "carbs": np.zeros(n),
        "override_active": np.zeros(n),
        "exercise_active": np.zeros(n),
        "suspension_time_min": np.zeros(n),
        "cage_hours": np.linspace(0, days * 24, n),
        "sage_hours": np.linspace(0, days * 24, n),
        "scheduled_isf": np.full(n, 50.0),
        "scheduled_cr": np.full(n, 10.0),
        "scheduled_basal_rate": np.full(n, 0.8),
        "actual_basal_rate": np.full(n, 0.8),
    })


# ── segment_into_turns ────────────────────────────────────────────────

def test_segment_into_turns_tiles_sequentially():
    df = _synthetic_grid(days=9.0)
    turns = segment_into_turns(df, turn_hours=72.0)
    assert len(turns) == 3
    for i, (start, end) in enumerate(turns):
        assert end - start == pd.Timedelta(hours=72)
        if i > 0:
            assert start == turns[i - 1][1]


def test_segment_into_turns_drops_trailing_partial_window():
    df = _synthetic_grid(days=8.0)  # not an exact multiple of 72h
    turns = segment_into_turns(df, turn_hours=72.0)
    assert len(turns) == 2  # 2*72h = 144h fits in 8*24=192h; a 3rd would need 216h


def test_segment_into_turns_empty_df():
    df = _synthetic_grid(days=9.0).iloc[0:0]
    assert segment_into_turns(df, turn_hours=72.0) == []


# ── compute_turn_features ────────────────────────────────────────────

def test_compute_turn_features_perfect_tir_and_completeness():
    df = _synthetic_grid(days=3.0, glucose_value=100.0)
    turns = segment_into_turns(df, turn_hours=72.0)
    (start, end) = turns[0]
    window_df = df[(df["time"] >= start) & (df["time"] < end)]
    feats = compute_turn_features("p1", 0, start, end, window_df, turn_hours=72.0)
    assert feats.data_completeness == pytest.approx(1.0)
    assert feats.tir == pytest.approx(100.0)
    assert feats.meets_ada_tir
    assert feats.meets_ada_tbr
    assert feats.is_reliable
    # No profile/metabolic context passed -> physiology fields degrade cleanly
    assert feats.physiology_available is False
    assert feats.mean_net_flux == 0.0
    # iob is present and glucose never exceeds 180, so saturation detection
    # runs and correctly finds no high-glucose episodes (level "none"),
    # rather than "insufficient_data" (which only applies when iob is absent
    # or the window is too short for the detector).
    assert feats.saturation_level == "none"


def test_compute_turn_features_low_completeness_flags_unreliable():
    df = _synthetic_grid(days=3.0, glucose_value=100.0)
    turns = segment_into_turns(df, turn_hours=72.0)
    (start, end) = turns[0]
    window_df = df[(df["time"] >= start) & (df["time"] < end)].copy()
    # Drop 80% of readings to simulate a sensor gap.
    window_df.loc[window_df.index[: int(len(window_df) * 0.8)], "glucose"] = np.nan
    feats = compute_turn_features("p1", 0, start, end, window_df, turn_hours=72.0)
    assert feats.data_completeness < 0.5
    assert not feats.is_reliable


def test_compute_turn_features_weekend_fraction():
    # 2026-01-05 is a Monday; a 72h window from Friday should include the weekend.
    df = _synthetic_grid(days=9.0, start="2026-01-02")  # Friday start
    turns = segment_into_turns(df, turn_hours=72.0)
    (start, end) = turns[0]
    window_df = df[(df["time"] >= start) & (df["time"] < end)]
    feats = compute_turn_features("p1", 0, start, end, window_df, turn_hours=72.0)
    assert feats.weekend_day_fraction > 0.0


def test_compute_turn_features_meal_and_activity_counts():
    df = _synthetic_grid(days=3.0)
    df.loc[df.index[10], "carbs"] = 40.0
    df.loc[df.index[20], "carbs"] = 15.0
    df.loc[df.index[30], "bolus"] = 3.0
    df.loc[df.index[5:15], "override_active"] = 1.0
    turns = segment_into_turns(df, turn_hours=72.0)
    (start, end) = turns[0]
    window_df = df[(df["time"] >= start) & (df["time"] < end)]
    feats = compute_turn_features("p1", 0, start, end, window_df, turn_hours=72.0)
    assert feats.meal_count == 2
    assert feats.bolus_active_row_count == 1
    assert feats.override_active_fraction == pytest.approx(10 / len(window_df))


def test_compute_turn_features_within_turn_momentum():
    """Glucose that starts low (out of range) and rises into range over the
    turn should show a positive within-turn TIR trend and higher last-24h
    TIR than the whole-turn mean would suggest."""
    df = _synthetic_grid(days=3.0, glucose_value=100.0)
    n = len(df)
    # First half out of range (40 mg/dL), second half in range (100 mg/dL).
    df.loc[df.index[: n // 2], "glucose"] = 40.0
    df.loc[df.index[n // 2:], "glucose"] = 100.0
    turns = segment_into_turns(df, turn_hours=72.0)
    (start, end) = turns[0]
    window_df = df[(df["time"] >= start) & (df["time"] < end)]
    feats = compute_turn_features("p1", 0, start, end, window_df, turn_hours=72.0)
    assert feats.first_half_tir == pytest.approx(0.0)
    assert feats.second_half_tir == pytest.approx(100.0)
    assert feats.tir_within_turn_trend == pytest.approx(100.0)
    # Last 24h falls entirely within the in-range second half.
    assert feats.last24h_tir == pytest.approx(100.0)


def test_compute_turn_features_saturation_episode_fields_present():
    df = _synthetic_grid(days=3.0, glucose_value=100.0)
    turns = segment_into_turns(df, turn_hours=72.0)
    (start, end) = turns[0]
    window_df = df[(df["time"] >= start) & (df["time"] < end)]
    feats = compute_turn_features("p1", 0, start, end, window_df, turn_hours=72.0)
    # Flat, in-range glucose -> no high-glucose episodes at all.
    assert feats.n_wall_episodes == 0
    assert feats.n_high_glucose_episodes == 0
    assert feats.excess_insulin_u == 0.0


# ── label_turn_outcome ────────────────────────────────────────────────

def _feat(tir=70.0, tbr_l1=1.0, tbr_l2=0.0, completeness=1.0) -> TurnFeatures:
    return TurnFeatures(
        patient_id="p1", turn_index=0,
        start=pd.Timestamp("2026-01-01", tz="UTC"),
        end=pd.Timestamp("2026-01-04", tz="UTC"),
        n_readings=100, expected_readings=100, data_completeness=completeness,
        tir=tir, tbr_l1=tbr_l1, tbr_l2=tbr_l2, tar_l1=0.0, tar_l2=0.0,
        cv=30.0, mean_glucose=140.0, overnight_tir=70.0,
        weekend_day_fraction=0.3, meal_count=5, bolus_active_row_count=5,
        smb_active_row_count=0, override_active_fraction=0.0,
        exercise_active_fraction=0.0, suspension_active_fraction=0.0,
    )


def test_label_unknown_when_no_followup():
    assert label_turn_outcome(_feat(), None).state == TrajectoryState.UNKNOWN


def test_label_unknown_when_unreliable_data():
    current = _feat(completeness=0.2)
    nxt = _feat()
    assert label_turn_outcome(current, nxt).state == TrajectoryState.UNKNOWN


def test_label_improving_on_large_tir_gain():
    current = _feat(tir=60.0)
    nxt = _feat(tir=70.0)  # +10pp, above the 5pp threshold
    assert label_turn_outcome(current, nxt).state == TrajectoryState.IMPROVING


def test_label_worsening_on_large_tir_drop():
    current = _feat(tir=75.0)
    nxt = _feat(tir=65.0)  # -10pp
    assert label_turn_outcome(current, nxt).state == TrajectoryState.WORSENING


def test_label_stable_good_when_flat_and_at_target():
    current = _feat(tir=72.0)
    nxt = _feat(tir=71.0)  # within +/-5pp, at/above ADA target (70)
    assert label_turn_outcome(current, nxt).state == TrajectoryState.STABLE_GOOD


def test_label_stable_poor_when_flat_and_below_target():
    current = _feat(tir=55.0)
    nxt = _feat(tir=57.0)  # within +/-5pp, below ADA target
    assert label_turn_outcome(current, nxt).state == TrajectoryState.STABLE_POOR


def test_label_safety_breach_dominates_tir_improvement():
    """A next turn that breaches ADA hypo safety is WORSENING even if TIR
    nominally improved — safety takes priority over the TIR delta."""
    current = _feat(tir=50.0)
    nxt = _feat(tir=80.0, tbr_l2=2.0)  # TIR way up, but TBR<54 breaches safety
    label = label_turn_outcome(current, nxt)
    assert label.state == TrajectoryState.WORSENING
    assert "safety" in label.reason


# ── build_patient_trajectory (integration across the full harness) ───

def test_build_patient_trajectory_end_to_end(tmp_path):
    df = _synthetic_grid(days=9.0, glucose_value=100.0)
    grid_path = tmp_path / "grid.parquet"
    df.to_parquet(grid_path)

    empty_loader = WearFactsLoader(bootstrap_path=tmp_path / "does_not_exist.parquet")
    records = build_patient_trajectory(
        tmp_path, "p1", turn_hours=72.0, wear_facts_loader=empty_loader,
    )

    assert len(records) == 3
    # Physiology context should be available since scheduled_isf/cr/basal_rate
    # and glucose are all present in the synthetic grid.
    assert all(r["physiology_available"] for r in records)
    # Perfectly flat, in-range glucose across all turns -> stable_good, except
    # the last turn which has no follow-up.
    assert [r["state"] for r in records] == ["stable_good", "stable_good", "unknown"]
    # site_degradation_p should be None (no bootstrap file for this patient).
    assert all(r["site_degradation_p"] is None for r in records)
    # New recency/momentum/episode-level fields should be present and, for
    # perfectly flat in-range glucose, show no within-turn momentum.
    for r in records:
        assert r["tir_within_turn_trend"] == pytest.approx(0.0)
        assert r["last24h_tir"] == pytest.approx(100.0)
        assert r["n_wall_episodes"] == 0


def test_build_patient_trajectory_degrades_without_profile_columns(tmp_path):
    df = _synthetic_grid(days=9.0, glucose_value=100.0).drop(
        columns=["scheduled_isf", "scheduled_cr", "scheduled_basal_rate"]
    )
    grid_path = tmp_path / "grid.parquet"
    df.to_parquet(grid_path)

    records = build_patient_trajectory(tmp_path, "p1", turn_hours=72.0)
    assert len(records) == 3
    assert all(not r["physiology_available"] for r in records)
    assert all(r["mean_net_flux"] == 0.0 for r in records)
