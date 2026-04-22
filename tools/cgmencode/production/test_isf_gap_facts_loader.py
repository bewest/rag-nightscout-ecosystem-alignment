"""Tests for IsfGapFactsLoader."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from tools.cgmencode.production.isf_gap_facts_loader import (
    IsfGapBootstrapFacts,
    IsfGapFactsLoader,
)


def _write_artifact(tmp_path: Path) -> Path:
    boot = pd.DataFrame([
        {"patient_id": "a", "p_under_correction": 0.95, "p_over_correction": 0.0},
        {"patient_id": "b", "p_under_correction": 0.4, "p_over_correction": 0.05},
        {"patient_id": "c", "p_under_correction": 0.0, "p_over_correction": 0.92},
    ])
    p = tmp_path / "boot.parquet"
    boot.to_parquet(p, index=False)
    return p


def test_loader_returns_none_for_unknown(tmp_path):
    p = _write_artifact(tmp_path)
    loader = IsfGapFactsLoader(bootstrap_path=p)
    facts = loader.lookup("zzz")
    assert facts == IsfGapBootstrapFacts(None, None)


def test_loader_returns_facts_for_known(tmp_path):
    p = _write_artifact(tmp_path)
    loader = IsfGapFactsLoader(bootstrap_path=p)
    facts_a = loader.lookup("a")
    assert facts_a.p_isf_under_correction == pytest.approx(0.95)
    assert facts_a.p_isf_over_correction == pytest.approx(0.0)
    facts_c = loader.lookup("c")
    assert facts_c.p_isf_over_correction == pytest.approx(0.92)


def test_loader_known_patients_listed(tmp_path):
    p = _write_artifact(tmp_path)
    loader = IsfGapFactsLoader(bootstrap_path=p)
    assert loader.known_patients() == ["a", "b", "c"]


def test_missing_artifact_yields_empty_index(tmp_path):
    loader = IsfGapFactsLoader(bootstrap_path=tmp_path / "missing.parquet")
    assert loader.known_patients() == []
    assert loader.lookup("a") == IsfGapBootstrapFacts(None, None)
