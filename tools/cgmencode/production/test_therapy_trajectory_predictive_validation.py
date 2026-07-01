"""Unit tests for therapy_trajectory_predictive_validation.py."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

sklearn = pytest.importorskip("sklearn")

from tools.cgmencode.production.therapy_trajectory_predictive_validation import (
    BASELINE_FEATURES,
    add_controller_lineage,
    compare_feature_sets,
    controller_stratified_summary,
    evaluate_feature_set,
    prepare_binary_dataset,
)
from tools.cgmencode.production.controller_dynamics_facts_loader import (
    ControllerDynamicsFactsLoader,
)


def _synthetic_dataset(n_patients: int = 10, n_turns: int = 20, seed: int = 0) -> pd.DataFrame:
    """A dataset where a physiology feature is genuinely predictive and
    the glycemic-only baseline features are not, so the test can assert
    the comparison actually detects the added signal."""
    rng = np.random.default_rng(seed)
    rows = []
    for p in range(n_patients):
        patient_id = f"p{p}"
        # A random per-patient effect keeps the "baseline" glycemic features
        # uninformative about the label on their own (label depends on the
        # physiology feature, not on current TIR).
        for t in range(n_turns):
            physiology_signal = rng.normal(0, 1)
            resolved = physiology_signal > 0
            rows.append({
                "patient_id": patient_id,
                "data_completeness": 0.9,
                "tir": rng.normal(65, 5),   # uninformative noise
                "tbr_l1": rng.normal(2, 1),
                "tbr_l2": rng.normal(0.5, 0.3),
                "tar_l1": rng.normal(10, 3),
                "cv": rng.normal(35, 5),
                "weekend_day_fraction": 0.3,
                "meal_count": 5,
                "bolus_active_row_count": 5,
                "smb_active_row_count": 0,
                "override_active_fraction": 0.0,
                "exercise_active_fraction": 0.0,
                "suspension_active_fraction": 0.0,
                "mean_hepatic_production": physiology_signal,  # the real signal
                "mean_carb_supply": 0.0,
                "mean_insulin_demand": 0.0,
                "mean_net_flux": 0.0,
                "saturation_wall_pct": 0.0,
                "carbs_48h_g": 50.0,
                "mean_cage_hours": 24.0,
                "mean_sage_hours": 24.0,
                "state": "improving" if resolved else "worsening",
            })
    return pd.DataFrame(rows)


def test_prepare_binary_dataset_drops_unknown_and_unreliable():
    df = pd.DataFrame([
        {"patient_id": "a", "data_completeness": 0.9, "state": "improving"},
        {"patient_id": "a", "data_completeness": 0.9, "state": "unknown"},
        {"patient_id": "a", "data_completeness": 0.2, "state": "worsening"},
        {"patient_id": "a", "data_completeness": 0.9, "state": "worsening"},
    ])
    out = prepare_binary_dataset(df)
    assert len(out) == 2
    assert set(out["state"]) == {"improving", "worsening"}
    assert out["resolved_like"].tolist() == [1, 0]


def test_evaluate_feature_set_detects_real_signal():
    df = _synthetic_dataset()
    dataset = prepare_binary_dataset(df)
    result = evaluate_feature_set(
        dataset, ["mean_hepatic_production"], "physiology_only",
    )
    assert result.auc_pooled is not None
    # The synthetic label is a near-deterministic function of this feature,
    # so leave-patient-out AUC should be high.
    assert result.auc_pooled > 0.85


def test_evaluate_feature_set_baseline_is_near_chance_on_synthetic_noise():
    df = _synthetic_dataset()
    dataset = prepare_binary_dataset(df)
    result = evaluate_feature_set(dataset, BASELINE_FEATURES, "baseline_glycemic_only")
    assert result.auc_pooled is not None
    # Baseline features are pure noise relative to the label by construction.
    assert 0.3 < result.auc_pooled < 0.7


def test_compare_feature_sets_shows_physiology_improves_auc():
    df = _synthetic_dataset()
    summary = compare_feature_sets(df)
    assert summary["baseline"]["auc_pooled"] is not None
    assert summary["full"]["auc_pooled"] is not None
    assert summary["delta_auc_from_physiology_features"] > 0.2
    assert summary["top_physiology_features_by_importance"][0][0] == "mean_hepatic_production"


def test_evaluate_feature_set_handles_single_class_gracefully():
    df = _synthetic_dataset(n_patients=3, n_turns=5)
    dataset = prepare_binary_dataset(df)
    dataset = dataset.assign(resolved_like=0)  # force degenerate single-class label
    result = evaluate_feature_set(dataset, BASELINE_FEATURES, "degenerate")
    assert result.auc_pooled is None


def _fake_loader(tmp_path, mapping: dict[str, str]) -> ControllerDynamicsFactsLoader:
    import json
    path = tmp_path / "controller_decomp.json"
    path.write_text(json.dumps({
        "per_patient": {pid: {"controller": ctrl} for pid, ctrl in mapping.items()}
    }))
    return ControllerDynamicsFactsLoader(decomposition_path=path)


def test_add_controller_lineage_maps_known_and_unknown(tmp_path):
    df = pd.DataFrame({"patient_id": ["a", "b", "z"]})
    loader = _fake_loader(tmp_path, {"a": "loop", "b": "trio_openaps"})
    out = add_controller_lineage(df, loader=loader)
    assert out.loc[out["patient_id"] == "a", "controller_type"].iloc[0] == "loop"
    assert out.loc[out["patient_id"] == "b", "controller_type"].iloc[0] == "trio_openaps"
    assert out.loc[out["patient_id"] == "z", "controller_type"].iloc[0] is None


def test_controller_stratified_summary_reports_population_and_within_patient_views(tmp_path):
    df = _synthetic_dataset(n_patients=6, n_turns=15)
    # Assign alternating controller lineage across the 6 synthetic patients.
    mapping = {f"p{i}": ("loop" if i % 2 == 0 else "trio_openaps") for i in range(6)}
    loader = _fake_loader(tmp_path, mapping)

    summary = controller_stratified_summary(df, loader=loader)

    assert summary["n_patients_with_known_controller"] == 6
    assert set(summary["mean_tir_by_controller"].keys()) == {"loop", "trio_openaps"}
    # Controller identity is patient-level-constant, so under leave-patient-out
    # validation it should add little to no within-patient predictive lift,
    # even though the synthetic label has nothing to do with controller type.
    assert abs(summary["controller_identity_within_patient_lift"]) < 0.15


def test_controller_stratified_summary_handles_no_known_controllers():
    df = _synthetic_dataset(n_patients=3, n_turns=5)
    summary = controller_stratified_summary(df)
    assert summary["n_patients_with_known_controller"] == 0
