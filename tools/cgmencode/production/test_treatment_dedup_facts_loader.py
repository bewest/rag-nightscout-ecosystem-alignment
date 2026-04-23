"""Unit tests for TreatmentDedupFactsLoader.

Tests graceful degradation, default strategy, and JSON parsing.
"""
import pytest
import json
from pathlib import Path
import pandas as pd
import tempfile

from tools.cgmencode.production.treatment_dedup_facts_loader import (
    TreatmentDedupFactsLoader,
    TreatmentDedupFacts,
    DEFAULT_DEDUP_WINDOW_SEC,
    DEFAULT_TIE_BREAKER_PRIORITY,
)


@pytest.fixture
def temp_dedup_parquet():
    """Create temporary dedup strategy parquet."""
    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
        df = pd.DataFrame({
            "patient_id": ["ns-8b3c1b50793c", "ns-8f3527d1ee40"],
            "dedup_window_sec": [60, 120],
            "tie_breaker_priority": [
                json.dumps(["AAPS", "xDripPlus", "Loop"]),
                json.dumps(["Trio", "Loop", "AAPS"]),
            ],
            "use_sync_id": [True, False],
            "sync_id_field": [
                "interfaceIDs.nightscoutId",
                "identifier",
            ],
            "event_type_confidence": [
                json.dumps({"bolus": 0.95, "meal": 0.85}),
                json.dumps({"bolus": 0.90, "meal": 0.80}),
            ],
            "confidence": [0.92, 0.75],
        })
        df.to_parquet(f.name)
        yield Path(f.name)
        Path(f.name).unlink()


def test_load_and_lookup(temp_dedup_parquet):
    """Test loading and looking up dedup strategies."""
    loader = TreatmentDedupFactsLoader(strategy_path=temp_dedup_parquet)
    
    # Patient 1: custom strategy
    strategy1 = loader.lookup("ns-8b3c1b50793c")
    assert strategy1.dedup_window_sec == 60
    assert strategy1.tie_breaker_priority == ["AAPS", "xDripPlus", "Loop"]
    assert strategy1.use_sync_id is True
    assert strategy1.confidence == 0.92
    
    # Patient 2: different strategy
    strategy2 = loader.lookup("ns-8f3527d1ee40")
    assert strategy2.dedup_window_sec == 120
    assert strategy2.tie_breaker_priority == ["Trio", "Loop", "AAPS"]
    assert strategy2.use_sync_id is False
    assert strategy2.confidence == 0.75


def test_unknown_patient_gets_defaults(temp_dedup_parquet):
    """Test unknown patients get conservative defaults."""
    loader = TreatmentDedupFactsLoader(strategy_path=temp_dedup_parquet)
    
    strategy = loader.lookup("unknown-patient")
    assert strategy.dedup_window_sec == DEFAULT_DEDUP_WINDOW_SEC
    assert strategy.tie_breaker_priority == DEFAULT_TIE_BREAKER_PRIORITY
    assert strategy.use_sync_id is True
    assert strategy.confidence is None  # No prior analysis


def test_missing_file_graceful():
    """Test loader handles missing file gracefully."""
    loader = TreatmentDedupFactsLoader(
        strategy_path=Path("/nonexistent/dedup.parquet")
    )
    
    # Should not raise
    strategy = loader.lookup("any_patient")
    assert strategy.dedup_window_sec == DEFAULT_DEDUP_WINDOW_SEC
    assert loader.n_patients_analyzed() == 0


def test_json_parse_error_fallback(temp_dedup_parquet):
    """Test loader falls back to defaults if JSON parsing fails."""
    # Create parquet with invalid JSON
    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
        df = pd.DataFrame({
            "patient_id": ["p1"],
            "dedup_window_sec": [60],
            "tie_breaker_priority": ["not valid json"],
            "use_sync_id": [True],
            "sync_id_field": ["interfaceIDs.nightscoutId"],
            "event_type_confidence": ["not json"],
            "confidence": [0.9],
        })
        df.to_parquet(f.name)
        
        loader = TreatmentDedupFactsLoader(strategy_path=Path(f.name))
        strategy = loader.lookup("p1")
        
        # Should use defaults for unparseable fields
        assert strategy.tie_breaker_priority == DEFAULT_TIE_BREAKER_PRIORITY
        assert strategy.dedup_window_sec == 60  # This field was valid
        
        Path(f.name).unlink()


def test_caching(temp_dedup_parquet):
    """Test lazy loading and caching."""
    loader = TreatmentDedupFactsLoader(strategy_path=temp_dedup_parquet)
    
    # First access: loads from disk
    strategy1 = loader.lookup("ns-8b3c1b50793c")
    
    # Second access: uses cached _index
    strategy2 = loader.lookup("ns-8b3c1b50793c")
    assert strategy1 == strategy2
    
    assert loader.n_patients_analyzed() == 2


def test_known_patients(temp_dedup_parquet):
    """Test known_patients list."""
    loader = TreatmentDedupFactsLoader(strategy_path=temp_dedup_parquet)
    
    pids = loader.known_patients()
    assert len(pids) == 2
    assert "ns-8b3c1b50793c" in pids
    assert "ns-8f3527d1ee40" in pids


def test_event_type_confidence_parsing():
    """Test event_type_confidence dict is properly parsed."""
    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
        df = pd.DataFrame({
            "patient_id": ["p1"],
            "dedup_window_sec": [60],
            "tie_breaker_priority": [json.dumps(["AAPS"])],
            "use_sync_id": [True],
            "sync_id_field": ["interfaceIDs.nightscoutId"],
            "event_type_confidence": [
                json.dumps({
                    "bolus": 0.95,
                    "meal": 0.85,
                    "tempbasal": 0.70,
                })
            ],
            "confidence": [0.9],
        })
        df.to_parquet(f.name)
        
        loader = TreatmentDedupFactsLoader(strategy_path=Path(f.name))
        strategy = loader.lookup("p1")
        
        assert strategy.event_type_confidence['bolus'] == 0.95
        assert strategy.event_type_confidence['meal'] == 0.85
        assert strategy.event_type_confidence['tempbasal'] == 0.70
        
        Path(f.name).unlink()


def test_dataclass_post_init_defaults():
    """Test TreatmentDedupFacts post_init sets defaults."""
    facts = TreatmentDedupFacts()
    
    # Should have initialized defaults
    assert facts.dedup_window_sec == DEFAULT_DEDUP_WINDOW_SEC
    assert facts.tie_breaker_priority == DEFAULT_TIE_BREAKER_PRIORITY
    assert facts.event_type_confidence is not None
    assert 'bolus' in facts.event_type_confidence
    assert facts.event_type_confidence['bolus'] == 0.95
