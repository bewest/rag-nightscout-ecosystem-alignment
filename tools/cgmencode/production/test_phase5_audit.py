"""Tests for the GAP-RECO-001 / GAP-CTRL-001 / GAP-ADVR-001 fixes
plus per-patient compute_for entry points and renderer regression.

These tests are the audit pass that follows the live-recent narrative
work (see plan.md Phase 5). They are deliberately small, fast, and
fixture-based so the inner-loop suite stays under 30s.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


# ──────────────────────────────────────────────────────────────────────
# GAP-RECO-001: recommender conflict resolution
# ──────────────────────────────────────────────────────────────────────


def _mk_settings_rec(direction="increase", magnitude_pct=20.0):
    from tools.cgmencode.production.types import (
        SettingsRecommendation, SettingsParameter,
    )
    return SettingsRecommendation(
        parameter=SettingsParameter.BASAL_RATE,
        direction=direction,
        magnitude_pct=magnitude_pct,
        current_value=1.7,
        suggested_value=2.04,
        predicted_tir_delta=1.4,
        affected_hours=(0.0, 6.0),
        confidence=0.6,
        evidence="overnight quadrant analysis",
        rationale="Increase overnight basal by 20%.",
    )


class _OvernightStub:
    def __init__(self, pct, conf=0.5):
        self.suggested_basal_change_pct = pct
        self.confidence = conf


def test_conflict_resolution_flags_opposite_sign_basal():
    """A +20% basal rec must be demoted when overnight model says -7.4%."""
    from tools.cgmencode.production.recommender import _apply_conflict_resolution
    sr = _mk_settings_rec(direction="increase", magnitude_pct=20.0)
    out = _apply_conflict_resolution([sr], _OvernightStub(pct=-7.4))
    warning = getattr(out[0], "_conflict_warning", "")
    assert warning, "expected conflict warning to be set"
    assert "-7.4" in warning


def test_conflict_resolution_does_not_flag_same_direction():
    from tools.cgmencode.production.recommender import _apply_conflict_resolution
    sr = _mk_settings_rec(direction="decrease", magnitude_pct=10.0)
    out = _apply_conflict_resolution([sr], _OvernightStub(pct=-7.4))
    assert not getattr(out[0], "_conflict_warning", ""), (
        "decreases should agree with overnight model -7.4")


def test_conflict_resolution_no_overnight_data_is_noop():
    from tools.cgmencode.production.recommender import _apply_conflict_resolution
    sr = _mk_settings_rec()
    out = _apply_conflict_resolution([sr], None)
    assert not getattr(out[0], "_conflict_warning", "")


def test_generate_recommendations_demotes_conflicting_basal_rec():
    """End-to-end: recommender priority must drop to 3 on conflict."""
    from tools.cgmencode.production.recommender import generate_recommendations
    from tools.cgmencode.production.types import ClinicalReport
    clinical = ClinicalReport.__new__(ClinicalReport)
    clinical.recommendations = []
    sr = _mk_settings_rec()
    recs = generate_recommendations(
        clinical=clinical, hypo_alert=None, meal_prediction=None,
        settings_recs=[sr],
        overnight_assessment=_OvernightStub(pct=-7.4),
    )
    basal_rec = next(r for r in recs if "basal" in r.action_type)
    assert basal_rec.priority == 3
    assert "Conflicts with overnight" in basal_rec.description


# ──────────────────────────────────────────────────────────────────────
# GAP-CTRL-001: controller detection — Loop autobolus-OFF vs AAPS
# ──────────────────────────────────────────────────────────────────────


def _mk_patient(suspension_frac, small_bolus_frac, n=2880):
    from tools.cgmencode.production.types import PatientData, PatientProfile
    rng = np.random.default_rng(42)
    glucose = np.full(n, 150.0)
    timestamps = (np.arange(n) * 5 * 60 * 1000).astype(np.int64)
    basal_rate = np.where(rng.random(n) < suspension_frac, 0.0, 0.8)
    n_bolus = 200
    bolus = np.zeros(n)
    bolus_indices = rng.choice(n, n_bolus, replace=False)
    n_small = int(small_bolus_frac * n_bolus)
    bolus[bolus_indices[:n_small]] = 0.15  # SMB-sized
    bolus[bolus_indices[n_small:]] = 4.0  # user-sized
    profile = PatientProfile(
        isf_schedule=[{"time": "00:00", "value": 50}],
        cr_schedule=[{"time": "00:00", "value": 10}],
        basal_schedule=[{"time": "00:00", "value": 0.8}],
        dia_hours=5.0,
    )
    return PatientData(
        glucose=glucose, timestamps=timestamps, profile=profile,
        bolus=bolus, basal_rate=basal_rate,
    )


def test_controller_detect_loop_autobolus_off_vs_aaps():
    """High suspension + low SMB cadence → Loop, not AAPS."""
    from tools.cgmencode.production.recommender import detect_controller_type
    from tools.cgmencode.production.types import ControllerType
    # Loop autobolus-OFF: ~30% suspension, mostly large user boluses
    loop_off = _mk_patient(suspension_frac=0.30, small_bolus_frac=0.10)
    assert detect_controller_type(loop_off) == ControllerType.LOOP, (
        "Loop autobolus-OFF must not be misclassified as AAPS")
    # AAPS: ~25% suspension, mostly small SMBs
    aaps = _mk_patient(suspension_frac=0.25, small_bolus_frac=0.80)
    assert detect_controller_type(aaps) == ControllerType.AAPS


# ──────────────────────────────────────────────────────────────────────
# GAP-ADVR-001: ISF non-linearity advisor — predicted_tir_delta cap
# ──────────────────────────────────────────────────────────────────────


def test_isf_nonlinearity_predicted_delta_capped():
    """predicted_tir_delta must not exceed 3.0 pp regardless of dose."""
    from tools.cgmencode.production.advisor._isf_advisors import (
        advise_isf_nonlinearity,
    )
    from tools.cgmencode.production.types import ClinicalReport, PatientProfile
    profile = PatientProfile(
        isf_schedule=[{"time": "00:00", "value": 40}],
        cr_schedule=[{"time": "00:00", "value": 10}],
        basal_schedule=[{"time": "00:00", "value": 0.8}],
        dia_hours=5.0,
    )
    clinical = ClinicalReport.__new__(ClinicalReport)
    clinical.mean_glucose = 200.0
    clinical.tir_70_180 = 0.6
    clinical.time_below_70 = 0.03
    clinical.time_below_54 = 0.0
    bolus = np.array([5.0] * 12)  # very large doses, many events
    rec = advise_isf_nonlinearity(
        clinical, profile, bolus=bolus, days_of_data=14.0)
    assert rec is not None
    assert rec.predicted_tir_delta <= 3.0, (
        f"got {rec.predicted_tir_delta} — must be capped at 3.0 pp")


# ──────────────────────────────────────────────────────────────────────
# Renderer regression: predicted_tir_delta is NOT double-scaled
# ──────────────────────────────────────────────────────────────────────


def test_renderer_does_not_double_scale_tir_delta(tmp_path: Path):
    from tools.cgmencode.analyze_patient import _render_markdown_report
    from types import SimpleNamespace

    # Minimal payload + result stand-ins
    payload = {
        "patient_id": "test",
        "generated_at_utc": "2026-04-24T00:00:00+00:00",
        "parquet_dir": str(tmp_path),
        "profile_timezone": "UTC",
        "days_of_data": 30.0,
        "glycemic_summary": {
            "mean_mgdl": 150.0, "ea1c_gmi_pct": 6.8,
            "tir_70_180": 0.7, "tbr_lt70": 0.02, "tbr_lt54": 0.0,
            "tar_gt180": 0.28, "tar_gt250": 0.05,
            "cv_pct": 35.0, "n_readings": 8640,
        },
        "per_patient_egp": {
            "method": "test", "patient_glucose_roc_lowiob_mgdl_per_5min": 0.0,
            "population_egp_mgdl_per_5min": 1.5,
            "controller_equilib_basal_multiplier": 1.0,
            "n_deep_fasting_rows": 100, "n_equilib_rows": 50,
        },
        "meal_smell_test": {},
        "facts_loaders": {},
    }
    rec = SimpleNamespace(
        action_type="adjust_isf", priority=2,
        description="test rationale",
        predicted_tir_delta=2.6,  # already in pp
        settings_rec=None,
    )
    result = SimpleNamespace(recommendations=[rec], meal_logging_qc=None)

    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "plots").mkdir()
    _render_markdown_report(out_dir, "test", payload, result, df=None)

    md = (out_dir / "clinical-report.md").read_text()
    assert "+2.6 pp" in md, f"expected '+2.6 pp', got: {md!r}"
    assert "+260" not in md, "double-scaling regression — must not multiply by 100"


# ──────────────────────────────────────────────────────────────────────
# compute_for: per-patient on-demand fact computation
# ──────────────────────────────────────────────────────────────────────


def _mk_grid_df(n=288 * 30, patient_id="ptest"):
    """Build a minimal grid.parquet-shaped DataFrame for one patient."""
    rng = np.random.default_rng(0)
    times = pd.date_range("2025-01-01", periods=n, freq="5min")
    df = pd.DataFrame({
        "patient_id": patient_id,
        "time": times,
        "glucose": 150.0 + 30 * np.sin(np.arange(n) / 50)
                    + rng.normal(0, 10, n),
        "iob": np.abs(rng.normal(2, 0.5, n)),
        "cob": np.abs(rng.normal(10, 5, n)),
        "bolus": np.where(rng.random(n) < 0.02, 4.0, 0.0),
        "bolus_smb": np.where(rng.random(n) < 0.05, 0.15, 0.0),
        "carbs": np.where(rng.random(n) < 0.01, 30.0, 0.0),
        "actual_basal_rate": np.where(rng.random(n) < 0.3, 0.0, 0.8),
        "scheduled_basal_rate": 0.8,
        "scheduled_isf": 50.0,
        "scheduled_cr": 10.0,
    })
    return df


def test_basal_mismatch_compute_for_returns_facts():
    from tools.cgmencode.production.basal_mismatch_facts_loader import (
        BasalMismatchFactsLoader,
    )
    loader = BasalMismatchFactsLoader()
    df = _mk_grid_df()
    facts = loader.compute_for("ptest", df, cache=False)
    assert facts is not None
    # at minimum the dataclass shape is intact
    assert hasattr(facts, "p_basal_mismatch")
    assert hasattr(facts, "median_recommended_mult")


def test_phenotype_compute_for_returns_facts():
    from tools.cgmencode.production.phenotype_facts_loader import (
        PhenotypeFactsLoader,
    )
    loader = PhenotypeFactsLoader()
    df = _mk_grid_df()
    facts = loader.compute_for("ptest", df, cache=False)
    assert facts is not None


def test_recovery_compute_for_returns_facts():
    from tools.cgmencode.production.recovery_facts_loader import (
        RecoveryFactsLoader,
    )
    loader = RecoveryFactsLoader()
    df = _mk_grid_df()
    facts = loader.compute_for("ptest", df, cache=False)
    assert facts is not None


def test_isf_gap_compute_for_returns_facts():
    from tools.cgmencode.production.isf_gap_facts_loader import (
        IsfGapFactsLoader,
    )
    loader = IsfGapFactsLoader()
    df = _mk_grid_df()
    facts = loader.compute_for("ptest", df, cache=False)
    assert facts is not None


def test_controller_dynamics_compute_for_returns_facts():
    from tools.cgmencode.production.controller_dynamics_facts_loader import (
        ControllerDynamicsFactsLoader,
    )
    loader = ControllerDynamicsFactsLoader()
    df = _mk_grid_df()
    facts = loader.compute_for("ptest", df, cache=False)
    assert facts is not None


# ──────────────────────────────────────────────────────────────────────
# Compression-low detection (Phase 4 wiring)
# ──────────────────────────────────────────────────────────────────────


def test_detect_compression_lows_flags_sharp_drop_and_recovery():
    from tools.cgmencode.production.data_quality import detect_compression_lows
    n = 288  # one day
    glucose = np.full(n, 120.0)
    # Sharp drop from 120 → 50 in <=3 steps, sustained, sharp recovery
    glucose[98:101] = [110.0, 80.0, 50.0]
    glucose[101:107] = [45.0, 45.0, 48.0, 60.0, 90.0, 115.0]
    bolus = np.zeros(n)
    carbs = np.zeros(n)
    indices = detect_compression_lows(glucose, bolus=bolus, carbs=carbs)
    assert any(100 <= int(i) <= 104 for i in indices), (
        f"expected compression flag in 100..104, got {indices}")


def test_detect_compression_lows_does_not_flag_treated_low():
    """A real low followed by carbs should NOT be flagged as compression."""
    from tools.cgmencode.production.data_quality import detect_compression_lows
    n = 288
    glucose = np.full(n, 120.0)
    # Gradual descent then carb-rescue recovery
    glucose[80:120] = np.linspace(120, 55, 40)
    glucose[120:140] = np.linspace(55, 120, 20)
    bolus = np.zeros(n)
    carbs = np.zeros(n)
    carbs[118] = 16.0  # treat-of-low
    indices = detect_compression_lows(glucose, bolus=bolus, carbs=carbs)
    # Should not flag the treated-low region as compression
    assert not any(80 <= int(i) <= 140 for i in indices), (
        f"treated low must not be flagged as compression, got {indices}")
