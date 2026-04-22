from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from tools.cgmencode.production.basal_mismatch_facts_loader import (
    BasalMismatchFactsLoader,
)


def test_loader_returns_none_for_unknown_patient(tmp_path: Path):
    loader = BasalMismatchFactsLoader(bootstrap_path=tmp_path / "missing.parquet")
    facts = loader.lookup("nobody")
    assert facts.p_basal_mismatch is None
    assert facts.median_recommended_mult is None


def test_loader_reads_parquet(tmp_path: Path):
    p = tmp_path / "exp-2865_per_patient_summary.parquet"
    pd.DataFrame(
        {
            "patient_id": ["a", "b"],
            "n_tod": [4, 1],
            "any_high_mismatch": [4, 1],
            "max_mismatch_p": [1.0, 0.95],
            "median_recommended_mult": [2.9, 0.32],
            "spread_recommended_mult": [1.5, 0.0],
        }
    ).to_parquet(p)
    loader = BasalMismatchFactsLoader(bootstrap_path=p)
    a = loader.lookup("a")
    assert a.p_basal_mismatch == pytest.approx(1.0)
    assert a.median_recommended_mult == pytest.approx(2.9)
    b = loader.lookup("b")
    assert b.p_basal_mismatch == pytest.approx(0.95)
    assert sorted(loader.known_patients()) == ["a", "b"]


def test_loader_handles_missing_columns(tmp_path: Path):
    p = tmp_path / "bad.parquet"
    pd.DataFrame({"patient_id": ["a"], "wrong_col": [1.0]}).to_parquet(p)
    loader = BasalMismatchFactsLoader(bootstrap_path=p)
    assert loader.lookup("a").p_basal_mismatch is None


def test_loader_default_path_loads_real_artifact():
    """Smoke test against the committed EXP-2865 artifact (if present)."""
    loader = BasalMismatchFactsLoader()
    pids = loader.known_patients()
    if not pids:
        pytest.skip("EXP-2865 artifact not present")
    facts = loader.lookup(pids[0])
    assert facts.p_basal_mismatch is not None
    assert 0.0 <= facts.p_basal_mismatch <= 1.0
