"""
production/ — Deployable inference modules for CGM analytics.

Wraps proven research algorithms (EXP-681–875) into composable modules
with typed contracts, missing-data handling, and benchmark validation.

Usage:
    from tools.cgmencode.production import run_pipeline, PatientData, PatientProfile

    profile = PatientProfile(
        isf_schedule=[{'time': '00:00', 'value': 50}],
        cr_schedule=[{'time': '00:00', 'value': 10}],
        basal_schedule=[{'time': '00:00', 'value': 0.8}],
    )
    patient = PatientData(glucose=bg_array, timestamps=ts_array, profile=profile)
    result = run_pipeline(patient)
    print(result.clinical_report.grade)      # 'A'
    print(result.risk.hypo_2h_probability)   # 0.12
"""

from .types import (
    PatientData, PatientProfile, CleanedData, MetabolicState,
    RiskAssessment, ClinicalReport, PatternProfile, CircadianFit,
    HypoAlert, PipelineResult, OnboardingState,
    DetectedMeal, MealHistory, MealTimingModel, MealPrediction,
    SettingsRecommendation, ActionRecommendation,
    MealResponse, MealResponseType, PeriodMetrics, CorrectionEnergy,
    BolusTimingSafety, AIDCompensation, CompensationType,
    GlycemicGrade, BasalAssessment, EventType, OnboardingPhase, Phenotype,
    MealWindow, SettingsParameter,
    OptimalSettings, SettingScheduleEntry, SettingsOptimizationResult,
    PatientPhenotype, PatientPhenotypeResult,
)
from .data_quality import clean_glucose, detect_spikes, interpolate_spikes
from .metabolic_engine import compute_metabolic_state
from .event_detector import classify_risk_simple, build_features
from .hypo_predictor import predict_hypo, calibrate_threshold
from .clinical_rules import (
    generate_clinical_report, compute_correction_energy,
    assess_correction_timing, assess_aid_compensation,
)
from .pattern_analyzer import analyze_patterns, fit_circadian
from .patient_onboarding import get_onboarding_state, POPULATION_DEFAULTS
from .meal_detector import detect_meal_events, build_meal_history, classify_all_meal_responses
from .meal_predictor import build_timing_models, predict_next_meal
from .settings_advisor import generate_settings_advice, analyze_periods, advise_isf_segmented
from .recommender import generate_recommendations
from .natural_experiment_detector import (
    detect_natural_experiments, NaturalExperiment, NaturalExperimentCensus,
    NaturalExperimentType, MealConfig,
)
from .settings_optimizer import optimize_settings
from .profile_generator import generate_profile, generate_all_formats, GeneratedProfile
from .patient_phenotyper import classify_patient_phenotype
from .pipeline import run_pipeline, run_pipeline_batch
from .validators import run_validation

__all__ = [
    # Types
    'PatientData', 'PatientProfile', 'CleanedData', 'MetabolicState',
    'RiskAssessment', 'ClinicalReport', 'PatternProfile', 'CircadianFit',
    'HypoAlert', 'PipelineResult', 'OnboardingState',
    'DetectedMeal', 'MealHistory', 'MealTimingModel', 'MealPrediction',
    'SettingsRecommendation', 'ActionRecommendation',
    'MealResponse', 'MealResponseType', 'PeriodMetrics', 'CorrectionEnergy',
    'BolusTimingSafety', 'AIDCompensation', 'CompensationType',
    'GlycemicGrade', 'BasalAssessment', 'EventType', 'OnboardingPhase', 'Phenotype',
    'MealWindow', 'SettingsParameter',
    # Patient phenotyping (EXP-2541)
    'PatientPhenotype', 'PatientPhenotypeResult', 'classify_patient_phenotype',
    # Pipeline
    'run_pipeline', 'run_pipeline_batch',
    # Individual modules
    'clean_glucose', 'detect_spikes', 'interpolate_spikes',
    'compute_metabolic_state',
    'classify_risk_simple', 'build_features',
    'predict_hypo', 'calibrate_threshold',
    'generate_clinical_report', 'compute_correction_energy',
    'assess_correction_timing', 'assess_aid_compensation',
    'analyze_patterns', 'fit_circadian',
    'get_onboarding_state', 'POPULATION_DEFAULTS',
    'detect_meal_events', 'build_meal_history', 'classify_all_meal_responses',
    'build_timing_models', 'predict_next_meal',
    'generate_settings_advice', 'analyze_periods', 'advise_isf_segmented',
    'generate_recommendations',
    # Natural Experiments
    'detect_natural_experiments', 'NaturalExperiment', 'NaturalExperimentCensus',
    'NaturalExperimentType', 'MealConfig',
    # Settings Optimization (EXP-1701)
    'optimize_settings',
    'OptimalSettings', 'SettingScheduleEntry', 'SettingsOptimizationResult',
    # Profile Generation (WS-2)
    'generate_profile', 'generate_all_formats', 'GeneratedProfile',
    # Validation
    'run_validation',
]
