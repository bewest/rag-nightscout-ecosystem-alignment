from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from tools.cgmencode.production.state_basal_facts_loader import (
    StateBasalFactsLoader,
    MIN_BASAL_N,
)


def test_missing_file_yields_empty(tmp_path: Path):
    L = StateBasalFactsLoader(parquet_path=tmp_path / "nope.parquet")
    f = L.lookup("anyone")
    assert f.per_state_basal_drift == {}
    assert f.has_multi_state is False
    assert f.basal_drift_range is None


def test_filters_below_min_basal_n(tmp_path: Path):
    p = tmp_path / "s.parquet"
    pd.DataFrame({
        "patient_id": ["x", "x"],
        "state": [0, 1],
        "isf": [80, 90],
        "isf_n": [10, 10],
        "basal_drift": [1.0, 2.0],
        "basal_n": [MIN_BASAL_N - 1, MIN_BASAL_N - 1],
    }).to_parquet(p)
    L = StateBasalFactsLoader(parquet_path=p)
    assert L.lookup("x").per_state_basal_drift == {}


def test_single_state_returns_no_range(tmp_path: Path):
    p = tmp_path / "s.parquet"
    pd.DataFrame({
        "patient_id": ["x"],
        "state": [1],
        "isf": [80],
        "isf_n": [100],
        "basal_drift": [3.0],
        "basal_n": [100],
    }).to_parquet(p)
    L = StateBasalFactsLoader(parquet_path=p)
    f = L.lookup("x")
    assert f.per_state_basal_drift == {1: 3.0}
    assert f.basal_drift_range is None
    assert f.has_multi_state is False


def test_multi_state_computes_range(tmp_path: Path):
    p = tmp_path / "s.parquet"
    pd.DataFrame({
        "patient_id": ["x", "x"],
        "state": [0, 1],
        "isf": [80, 90],
        "isf_n": [100, 100],
        "basal_drift": [1.0, 3.5],
        "basal_n": [100, 100],
    }).to_parquet(p)
    L = StateBasalFactsLoader(parquet_path=p)
    f = L.lookup("x")
    assert f.per_state_basal_drift == {0: 1.0, 1: 3.5}
    assert f.basal_drift_range == pytest.approx(2.5)
    assert f.has_multi_state is True


def test_default_path_loads_real_artifact():
    L = StateBasalFactsLoader()
    pids = L.known_patients()
    if not pids:
        pytest.skip("EXP-2811 artifact not present")
    # At least one patient should be present
    assert L.lookup(pids[0]).per_state_basal_drift
