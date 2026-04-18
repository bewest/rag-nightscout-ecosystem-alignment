#!/usr/bin/env python3
"""Unit tests — no run_pipeline calls. Target: <40s.

These test individual functions, type contracts, and module-level logic
without running the full 11-stage pipeline.

Usage:
    pytest tools/cgmencode/production/test_unit.py -q
    pytest -m unit -q
"""
import pytest

# Re-export all unit test classes from the monolith.
# This avoids duplicating 4000+ lines while enabling fast `pytest test_unit.py`.
from cgmencode.production.test_production import (  # noqa: F401
    # Type contracts
    TestEnumContracts,
    TestPatientProfileUnits,
    TestPatientDataContracts,
    TestDetectedMealContract,
    TestMealHistoryContract,
    TestMealPredictionContract,
    TestPipelineResultContract,
    TestForecastResultContract,
    # Module contracts
    TestDataQuality,
    TestMetabolicEngine,
    TestMealDetector,
    TestMealPredictor,
    TestBasalAssessment,
    TestRecommender,
    # Natural experiments
    TestNaturalExperimentTypes,
    TestNaturalExperimentDetector,
    # Settings optimizer
    TestSettingsOptimizerTypes,
    TestSettingsOptimizerModule,
    TestCircadianISF,
    TestContextCR,
    # Controller
    TestControllerTypes,
    TestControllerDetection,
    # Overnight drift / loop workload
    TestOvernightDriftTypes,
    TestLoopWorkloadTypes,
    TestOvernightDriftFunction,
    TestLoopWorkloadFunction,
    # ISF nonlinearity
    TestISFNonlinearityTypes,
    TestISFNonlinearityFunction,
    TestISFNonlinearityIntegration,
    # Correction threshold
    TestCorrectionThresholdTypes,
    TestCorrectionThresholdFunction,
    TestCorrectionThresholdIntegration,
    # Circadian ISF profiled
    TestCircadianISFProfiledTypes,
    TestCircadianISFProfiledFunction,
    TestCircadianISFProfiledIntegration,
    # CR adequacy
    TestCRAdequacyTypes,
    TestCRAdequacyFunction,
    TestCRAdequacyIntegration,
    # Hypo risk
    TestComputeHypoRisk,
    # Event extraction
    TestCorrectionEventExtraction,
    TestMealEventExtraction,
    # Phenotyping
    TestPatientPhenotypeTypes,
    TestPatientPhenotyper,
    # Loop quality
    TestLoopQualityTypes,
    TestLoopQualityAssessment,
    # Profile generator
    TestProfileGeneratorTypes,
    TestProfileGeneratorOref0,
    TestProfileGeneratorLoop,
    TestProfileGeneratorTrio,
    TestProfileGeneratorNightscout,
    TestProfileGeneratorConstraints,
    TestProfileGeneratorJSON,
    # Prediction validator
    TestPredictionValidatorTypes,
    TestPredictionValidatorExecution,
    # Forward simulator
    TestForwardSimulator,
    # Advisory functions (EXP-2621+)
    TestOverrideISFAdvisory,
    TestAdvisoryConfidenceTier,
    TestSafetyClamp,
    TestAdvisoryDeduplication,
    # Demand-phase ISF (EXP-2651)
    TestComputeDemandISF,
    TestDetectInsulinSaturation,
    TestAssessBasalCleanNight,
    TestAdviseISF,
    TestExcessInsulinCalculation,
    TestCleanNightFallback,
    # Recent additions
    TestOvernightDrift48hCarbs,
    TestStackingPrevention35h,
    TestAdvisePatienceMode,
    TestAdviseISFDualPhase,
    TestComputeApparentISFAlias,
    TestDualPhaseISFType,
    TestSaturationTypes,
)

# Apply unit marker to all tests in this module
pytestmark = pytest.mark.unit
