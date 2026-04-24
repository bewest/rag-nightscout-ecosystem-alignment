"""Tests for ControllerDynamicsFactsLoader (Wave-13 / EXP-2753)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.cgmencode.production.controller_dynamics_facts_loader import (
    ControllerDynamicsFacts,
    ControllerDynamicsFactsLoader,
)


def _write_artifact(tmp_path: Path) -> Path:
    blob = {
        "experiment": "EXP-2753",
        "per_patient": {
            "a": {
                "patient_id": "a",
                "controller": "loop",
                "n_events": 82,
                "mean_correction_fraction": 0.4958,
                "mean_smb_fraction": 0.0,
                "mean_excess_basal_fraction": 0.5042,
                "mean_controller_fraction_of_excess": 0.4994,
                "corr_denom_gap_closure": 0.7558,
                "isf_correction_denom_median": 41.63,
                "isf_profile_median": 48.64,
            },
            "trio_pt": {
                "patient_id": "trio_pt",
                "controller": "trio_openaps",
                "n_events": 130,
                "mean_correction_fraction": 0.32,
                "mean_smb_fraction": 0.65,
                "mean_excess_basal_fraction": 0.03,
                "mean_controller_fraction_of_excess": 0.68,
                "corr_denom_gap_closure": -1.5,
                # NaN robustness (JSON encodes as null):
                "isf_correction_denom_median": None,
                "isf_profile_median": 50.0,
            },
            "messy_row": "not-a-dict-should-be-skipped",
        },
    }
    p = tmp_path / "exp-2753.json"
    p.write_text(json.dumps(blob))
    return p


def test_loader_returns_empty_for_unknown(tmp_path):
    p = _write_artifact(tmp_path)
    loader = ControllerDynamicsFactsLoader(decomposition_path=p)
    assert loader.lookup("zzz") == ControllerDynamicsFacts()


def test_loader_returns_facts_for_known(tmp_path):
    p = _write_artifact(tmp_path)
    loader = ControllerDynamicsFactsLoader(decomposition_path=p)
    facts = loader.lookup("a")
    assert facts.controller_type == "loop"
    assert facts.n_events == 82
    assert facts.mean_correction_fraction == pytest.approx(0.4958)
    assert facts.mean_smb_fraction == pytest.approx(0.0)
    assert facts.mean_excess_basal_fraction == pytest.approx(0.5042)
    assert facts.corr_denom_gap_closure == pytest.approx(0.7558)
    assert facts.isf_corr_denom_median == pytest.approx(41.63)
    assert facts.isf_profile_median == pytest.approx(48.64)


def test_loader_handles_null_fields(tmp_path):
    p = _write_artifact(tmp_path)
    loader = ControllerDynamicsFactsLoader(decomposition_path=p)
    facts = loader.lookup("trio_pt")
    assert facts.controller_type == "trio_openaps"
    assert facts.isf_corr_denom_median is None
    assert facts.isf_profile_median == pytest.approx(50.0)


def test_loader_skips_malformed_rows(tmp_path):
    p = _write_artifact(tmp_path)
    loader = ControllerDynamicsFactsLoader(decomposition_path=p)
    pids = loader.known_patients()
    assert "messy_row" not in pids
    assert pids == ["a", "trio_pt"]


def test_missing_artifact_yields_empty_index(tmp_path):
    loader = ControllerDynamicsFactsLoader(
        decomposition_path=tmp_path / "missing.json"
    )
    assert loader.known_patients() == []
    assert loader.lookup("a") == ControllerDynamicsFacts()


def test_corrupt_artifact_yields_empty_index(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json at all")
    loader = ControllerDynamicsFactsLoader(decomposition_path=p)
    assert loader.known_patients() == []


def test_real_artifact_loads_if_present():
    """Smoke test against the real EXP-2753 artifact, if it exists."""
    loader = ControllerDynamicsFactsLoader()
    pids = loader.known_patients()
    if not pids:
        pytest.skip("EXP-2753 artifact not present in this checkout")
    # Spot-check first patient has at least controller_type populated.
    f = loader.lookup(pids[0])
    assert f.controller_type in {"loop", "trio_openaps"}
    # Population finding: total fractions should sum to ≈1 (within slack).
    if (
        f.mean_correction_fraction is not None
        and f.mean_smb_fraction is not None
        and f.mean_excess_basal_fraction is not None
    ):
        total = (
            f.mean_correction_fraction
            + f.mean_smb_fraction
            + f.mean_excess_basal_fraction
        )
        assert 0.5 <= total <= 1.5  # loose bound; suspension_offset can shift
