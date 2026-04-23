"""Unit tests for PhenotypeFactsLoader.

Tests graceful degradation, caching, and merge semantics.
"""
import pytest
from pathlib import Path
import pandas as pd
import tempfile

from tools.cgmencode.production.phenotype_facts_loader import (
    PhenotypeFactsLoader,
    PhenotypeFacts,
)


@pytest.fixture
def temp_phenotype_parquet():
    """Create temporary phenotype parquet with sample data."""
    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
        df = pd.DataFrame({
            "patient_id": ["p1", "p2"],
            "stack_score": [1.5, 2.2],
            "brake_ratio": [0.08, 0.12],
            "counter_reg_intercept": [1.42, 1.56],
            "controller_lineage": ["Loop", "Trio"],
        })
        df.to_parquet(f.name)
        yield Path(f.name)
        Path(f.name).unlink()


@pytest.fixture
def temp_haaf_parquet():
    """Create temporary HAAF parquet."""
    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
        df = pd.DataFrame({
            "patient_id": ["p1", "p3"],
            "beta_nadir": [0.032, 0.045],
            "p_haaf": [0.02, 0.08],
        })
        df.to_parquet(f.name)
        yield Path(f.name)
        Path(f.name).unlink()


@pytest.fixture
def temp_evening_parquet():
    """Create temporary evening drivers parquet."""
    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
        df = pd.DataFrame({
            "patient_id": ["p2", "p3"],
            "evening_bolus_excess_4h": [2.1, 1.8],
            "evening_iob_at_descent": [0.8, 1.2],
        })
        df.to_parquet(f.name)
        yield Path(f.name)
        Path(f.name).unlink()


def test_load_merge_multiple_sources(temp_phenotype_parquet, temp_haaf_parquet, temp_evening_parquet):
    """Test merging of 3 independent parquets."""
    loader = PhenotypeFactsLoader(
        phenotype_path=temp_phenotype_parquet,
        haaf_path=temp_haaf_parquet,
        evening_drivers_path=temp_evening_parquet,
    )
    
    # p1: phenotype + HAAF
    facts_p1 = loader.lookup("p1")
    assert facts_p1.stack_score == 1.5
    assert facts_p1.brake_ratio == 0.08
    assert facts_p1.beta_nadir == 0.032
    assert facts_p1.p_haaf == 0.02
    assert facts_p1.evening_bolus_excess_4h is None  # Not in evening parquet
    
    # p2: phenotype + evening
    facts_p2 = loader.lookup("p2")
    assert facts_p2.stack_score == 2.2
    assert facts_p2.beta_nadir is None  # Not in HAAF parquet
    assert facts_p2.evening_bolus_excess_4h == 2.1
    
    # p3: HAAF + evening (no phenotype)
    facts_p3 = loader.lookup("p3")
    assert facts_p3.stack_score is None
    assert facts_p3.beta_nadir == 0.045
    assert facts_p3.evening_bolus_excess_4h == 1.8
    
    # unknown: all None
    facts_unknown = loader.lookup("p_unknown")
    assert facts_unknown.stack_score is None
    assert facts_unknown.brake_ratio is None
    assert facts_unknown.beta_nadir is None


def test_graceful_fallback_missing_sources():
    """Test loader handles missing files gracefully."""
    loader = PhenotypeFactsLoader(
        phenotype_path=Path("/nonexistent/phenotype.parquet"),
        haaf_path=Path("/nonexistent/haaf.parquet"),
        evening_drivers_path=Path("/nonexistent/evening.parquet"),
    )
    
    # Should not raise, return all-None
    facts = loader.lookup("any_patient")
    assert facts == PhenotypeFacts()  # All fields None
    assert loader.n_patients() == 0


def test_caching(temp_phenotype_parquet):
    """Test lazy loading and caching."""
    loader = PhenotypeFactsLoader(
        phenotype_path=temp_phenotype_parquet,
        haaf_path=Path("/nonexistent/haaf.parquet"),
        evening_drivers_path=Path("/nonexistent/evening.parquet"),
    )
    
    # First access: loads from disk
    facts1 = loader.lookup("p1")
    assert facts1.stack_score == 1.5
    
    # Second access: uses cached _index
    facts2 = loader.lookup("p1")
    assert facts2 is facts1  # Same object (cache hit)
    
    assert loader.n_patients() == 2  # p1, p2


def test_coverage_by_axis(temp_phenotype_parquet, temp_haaf_parquet, temp_evening_parquet):
    """Test coverage reporting."""
    loader = PhenotypeFactsLoader(
        phenotype_path=temp_phenotype_parquet,
        haaf_path=temp_haaf_parquet,
        evening_drivers_path=temp_evening_parquet,
    )
    
    coverage = loader.coverage_by_axis()
    
    # p1: phenotype (3) + HAAF (2) = 5 axes
    # p2: phenotype (3) + evening (2) = 5 axes
    # p3: HAAF (2) + evening (2) = 4 axes
    
    assert coverage['stack_score'] == 2  # p1, p2
    assert coverage['brake_ratio'] == 2
    assert coverage['counter_reg_intercept'] == 2
    assert coverage['beta_nadir'] == 2  # p1, p3
    assert coverage['p_haaf'] == 2
    assert coverage['evening_bolus_excess_4h'] == 2  # p2, p3
    assert coverage['evening_iob_at_descent'] == 2
    assert coverage['controller_lineage'] == 2


def test_known_patients(temp_phenotype_parquet):
    """Test known_patients list."""
    loader = PhenotypeFactsLoader(
        phenotype_path=temp_phenotype_parquet,
        haaf_path=Path("/nonexistent/haaf.parquet"),
        evening_drivers_path=Path("/nonexistent/evening.parquet"),
    )
    
    pids = loader.known_patients()
    assert pids == ["p1", "p2"]  # Sorted


def test_partial_nan_values(temp_phenotype_parquet):
    """Test handling of NaN values in parquet."""
    # Modify phenotype to have NaN
    df = pd.read_parquet(temp_phenotype_parquet)
    df.loc[0, 'stack_score'] = None  # p1 has NaN for stack_score
    
    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
        df.to_parquet(f.name)
        
        loader = PhenotypeFactsLoader(
            phenotype_path=Path(f.name),
            haaf_path=Path("/nonexistent/haaf.parquet"),
            evening_drivers_path=Path("/nonexistent/evening.parquet"),
        )
        
        facts_p1 = loader.lookup("p1")
        assert facts_p1.stack_score is None  # NaN converted to None
        assert facts_p1.brake_ratio == 0.08  # Other fields preserved
        
        Path(f.name).unlink()
