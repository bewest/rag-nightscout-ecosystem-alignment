"""Tests for WearFactsLoader."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from tools.cgmencode.production.wear_facts_loader import (
    WearBootstrapFacts,
    WearFactsLoader,
)


def _write_artifact(tmp_path: Path) -> Path:
    df = pd.DataFrame([
        {"patient_id": "a", "p_site_degradation": 0.95},
        {"patient_id": "b", "p_site_degradation": 0.5},
        {"patient_id": "c", "p_site_degradation": 0.05},
    ])
    p = tmp_path / "wear.parquet"
    df.to_parquet(p, index=False)
    return p


def test_loader_returns_none_for_unknown(tmp_path):
    p = _write_artifact(tmp_path)
    loader = WearFactsLoader(bootstrap_path=p)
    assert loader.lookup("zzz") == WearBootstrapFacts(None)


def test_loader_returns_facts_for_known(tmp_path):
    p = _write_artifact(tmp_path)
    loader = WearFactsLoader(bootstrap_path=p)
    assert loader.lookup("a").p_site_degradation == pytest.approx(0.95)
    assert loader.lookup("c").p_site_degradation == pytest.approx(0.05)


def test_known_patients(tmp_path):
    p = _write_artifact(tmp_path)
    loader = WearFactsLoader(bootstrap_path=p)
    assert loader.known_patients() == ["a", "b", "c"]


def test_missing_artifact_yields_empty(tmp_path):
    loader = WearFactsLoader(bootstrap_path=tmp_path / "missing.parquet")
    assert loader.known_patients() == []
