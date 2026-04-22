"""Tests for PostHighFactsLoader (EXP-2864)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from tools.cgmencode.production.post_high_facts_loader import (
    PostHighFactsLoader,
    PostHighBootstrapFacts,
)


def _write(tmp_path: Path) -> Path:
    p = tmp_path / "ph.parquet"
    pd.DataFrame(
        [
            {"patient_id": "a", "p_post_high_envelope": 0.95},
            {"patient_id": "b", "p_post_high_envelope": 0.42},
            {"patient_id": "c", "p_post_high_envelope": 0.05},
        ]
    ).to_parquet(p)
    return p


def test_lookup_returns_facts(tmp_path):
    loader = PostHighFactsLoader(_write(tmp_path))
    f = loader.lookup("a")
    assert f.p_post_high_envelope == pytest.approx(0.95)


def test_lookup_unknown_returns_none(tmp_path):
    loader = PostHighFactsLoader(_write(tmp_path))
    assert loader.lookup("zzz") == PostHighBootstrapFacts(None)


def test_missing_file_returns_empty(tmp_path):
    loader = PostHighFactsLoader(tmp_path / "missing.parquet")
    assert loader.known_patients() == []
    assert loader.lookup("a").p_post_high_envelope is None


def test_known_patients_sorted(tmp_path):
    loader = PostHighFactsLoader(_write(tmp_path))
    assert loader.known_patients() == ["a", "b", "c"]
