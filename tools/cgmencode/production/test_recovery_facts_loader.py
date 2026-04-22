"""Tests for RecoveryFactsLoader."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from tools.cgmencode.production.recovery_facts_loader import (
    RecoveryBootstrapFacts,
    RecoveryFactsLoader,
)


def _write_artifact(tmp_path: Path) -> Path:
    df = pd.DataFrame([
        {"patient_id": "a", "p_low_recovery": 0.95},
        {"patient_id": "b", "p_low_recovery": 1.0},
        {"patient_id": "c", "p_low_recovery": 0.05},
    ])
    p = tmp_path / "rec.parquet"
    df.to_parquet(p, index=False)
    return p


def test_loader_returns_none_for_unknown(tmp_path):
    p = _write_artifact(tmp_path)
    loader = RecoveryFactsLoader(bootstrap_path=p)
    assert loader.lookup("zzz") == RecoveryBootstrapFacts(None)


def test_loader_returns_facts_for_known(tmp_path):
    p = _write_artifact(tmp_path)
    loader = RecoveryFactsLoader(bootstrap_path=p)
    assert loader.lookup("b").p_low_recovery == pytest.approx(1.0)
    assert loader.lookup("c").p_low_recovery == pytest.approx(0.05)


def test_known_patients(tmp_path):
    p = _write_artifact(tmp_path)
    loader = RecoveryFactsLoader(bootstrap_path=p)
    assert loader.known_patients() == ["a", "b", "c"]


def test_missing_artifact_yields_empty(tmp_path):
    loader = RecoveryFactsLoader(bootstrap_path=tmp_path / "missing.parquet")
    assert loader.known_patients() == []
