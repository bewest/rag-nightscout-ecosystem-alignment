#!/usr/bin/env python3
"""Integration tests — call run_pipeline. Target: <180s.

These run the full 11-stage production pipeline on synthetic data.
Use test_unit.py for fast iteration during development.

Usage:
    pytest tools/cgmencode/production/test_integration.py -q
    pytest -m integration -q
"""
import pytest

# Re-export all integration test classes from the monolith.
from cgmencode.production.test_production import (  # noqa: F401
    # Forecast
    TestGlucoseForecastModule,
    TestTwoComponentDIA,
    # Pipeline regression
    TestPipelineRegression,
    # Natural experiment pipeline
    TestNaturalExperimentPipeline,
    # Settings optimizer pipeline
    TestSettingsOptimizerPipeline,
    # Settings advice integration
    TestSettingsAdviceIntegration,
    # Overnight drift integration
    TestOvernightDriftIntegration,
    # Three-window routing
    TestThreeWindowRoutingIntegration,
    # Hypo risk pipeline
    TestHypoRiskResultType,
    TestHypoRiskPipelineIntegration,
    # Advisory wiring
    TestPipelineAdvisoryWiring,
    # Phenotype pipeline
    TestPhenotypePipelineIntegration,
    # Loop quality pipeline
    TestLoopQualityPipelineIntegration,
)

# Apply integration marker to all tests in this module
pytestmark = pytest.mark.integration
