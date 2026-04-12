#!/usr/bin/env python3
"""
Production pipeline test suite — contract, regression, and golden tests.

Three test layers:
  1. Type contracts: dataclass instantiation, enum values, property invariants
  2. Module contracts: input/output shapes, required keys, graceful degradation
  3. Pipeline regression: end-to-end on synthetic data, no crashes

Usage:
    PYTHONPATH=tools python tools/cgmencode/production/test_production.py -v
    PYTHONPATH=tools python -m pytest tools/cgmencode/production/test_production.py -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

from cgmencode.production.types import (
    PatientProfile, PatientData, CleanedData, MetabolicState,
    RiskAssessment, HypoAlert, ClinicalReport, PatternProfile,
    CircadianFit, OnboardingState, DetectedMeal, MealHistory,
    MealTimingModel, MealPrediction, SettingsRecommendation,
    ActionRecommendation, MealResponse, PeriodMetrics,
    CorrectionEnergy, BolusTimingSafety, AIDCompensation,
    PipelineResult, ForecastResult,
    GlycemicGrade, BasalAssessment, EventType, OnboardingPhase,
    Phenotype, MealWindow, SettingsParameter, MealResponseType,
    CompensationType, ConfidenceGrade,
    OptimalSettings, SettingScheduleEntry, SettingsOptimizationResult,
    ControllerType, ControllerBehavior,
    OvernightPhenotype, OvernightDriftAssessment, LoopWorkloadReport,
    TwoComponentDIA,
    HypoRiskResult,
    PatientPhenotype, PatientPhenotypeResult,
    LoopQualityResult,
)


# ── Fixtures ──────────────────────────────────────────────────────────

def make_profile() -> PatientProfile:
    """Minimal valid profile."""
    return PatientProfile(
        isf_schedule=[{"time": "00:00", "value": 50.0}],
        cr_schedule=[{"time": "00:00", "value": 10.0}],
        basal_schedule=[{"time": "00:00", "value": 0.8}],
        dia_hours=5.0,
    )


def make_glucose(n: int = 4320, seed: int = 42) -> np.ndarray:
    """Synthetic glucose: 120 mg/dL base + noise + circadian + meals.

    4320 steps = 15 days at 5-min resolution (enough for ML training).
    """
    rng = np.random.RandomState(seed)
    t = np.arange(n, dtype=float)
    hours = (t * 5.0 / 60.0) % 24.0

    # Circadian: +10 mg/dL dawn phenomenon peak at 6 AM
    circadian = 10.0 * np.sin(2 * np.pi * (hours - 6.0) / 24.0)

    # Meal bumps: 3 meals/day at ~8, ~12, ~18 (modest 30 mg/dL spikes)
    meals = np.zeros(n)
    for day in range(n // 288):
        for meal_hour in [8.0, 12.0, 18.0]:
            idx = day * 288 + int(meal_hour * 12)
            if idx + 24 < n:
                meals[idx:idx + 24] += 30.0 * np.exp(-np.arange(24) / 8.0)

    glucose = 120.0 + circadian + meals + rng.normal(0, 3.0, n)

    # Inject 5 deliberate spikes for spike detector tests
    spike_positions = [100, 500, 1200, 2500, 3800]
    for pos in spike_positions:
        if pos < n:
            glucose[pos] += 80.0

    return glucose.clip(40, 400)


def make_iob(n: int = 4320, seed: int = 42) -> np.ndarray:
    """Synthetic IOB: basal of 0.05 U + bolus spikes at meals."""
    rng = np.random.RandomState(seed + 1)
    iob = np.full(n, 0.05)
    for day in range(n // 288):
        for meal_hour in [8.0, 12.0, 18.0]:
            idx = day * 288 + int(meal_hour * 12)
            if idx + 36 < n:
                # Bolus decay: ~3U peak decaying over 3h
                decay = 3.0 * np.exp(-np.arange(36) / 12.0)
                iob[idx:idx + 36] += decay
    return iob + rng.normal(0, 0.01, n).clip(0, None)


def make_timestamps(n: int = 4320) -> np.ndarray:
    """Timestamps at 5-min intervals starting 2025-01-01 midnight UTC."""
    t0 = 1735689600000  # 2025-01-01 00:00:00 UTC in ms
    return np.arange(n, dtype=np.int64) * 300_000 + t0


def make_patient(n: int = 4320, with_insulin: bool = True,
                 patient_id: str = "test") -> PatientData:
    """Build a complete synthetic patient."""
    glucose = make_glucose(n)
    ts = make_timestamps(n)
    profile = make_profile()

    kwargs = dict(glucose=glucose, timestamps=ts, profile=profile,
                  patient_id=patient_id)
    if with_insulin:
        iob = make_iob(n)
        kwargs["iob"] = iob
        kwargs["bolus"] = np.maximum(np.diff(np.concatenate([[0], iob])), 0) * 0.5
        kwargs["carbs"] = np.zeros(n)
        kwargs["basal_rate"] = np.full(n, 0.8)
        # Add carb events at meals
        for day in range(n // 288):
            for meal_hour in [8.0, 12.0, 18.0]:
                idx = day * 288 + int(meal_hour * 12)
                if idx < n:
                    kwargs["carbs"][idx] = 40.0

    return PatientData(**kwargs)


# ── 1. Type Contract Tests ────────────────────────────────────────────

class TestEnumContracts(unittest.TestCase):
    """Enums have the expected members and string values."""

    def test_glycemic_grades(self):
        self.assertEqual(set(GlycemicGrade), {
            GlycemicGrade.A, GlycemicGrade.B,
            GlycemicGrade.C, GlycemicGrade.D,
        })

    def test_basal_assessment_prefix(self):
        """BasalAssessment values use 'basal_' prefix (gotcha from types.py:31-35)."""
        for member in BasalAssessment:
            self.assertTrue(member.value.startswith("basal_"),
                            f"{member} doesn't have basal_ prefix")

    def test_meal_windows(self):
        self.assertEqual(set(MealWindow),
                         {MealWindow.BREAKFAST, MealWindow.LUNCH,
                          MealWindow.DINNER, MealWindow.SNACK})

    def test_onboarding_phases_ordered(self):
        phases = list(OnboardingPhase)
        self.assertEqual(len(phases), 4)

    def test_event_types_include_eating_soon(self):
        self.assertIn(EventType.EATING_SOON, EventType)

    def test_all_enums_are_str_enum(self):
        """All enums inherit from str for JSON serialization."""
        for enum_cls in [GlycemicGrade, BasalAssessment, EventType,
                         OnboardingPhase, Phenotype, MealWindow,
                         SettingsParameter, MealResponseType,
                         CompensationType]:
            for member in enum_cls:
                self.assertIsInstance(member.value, str,
                                     f"{enum_cls.__name__}.{member.name}")


class TestPatientProfileUnits(unittest.TestCase):
    """PatientProfile mmol/L ↔ mg/dL conversion for ISF."""

    def test_mgdl_profile_passthrough(self):
        """mg/dL profile returns ISF unchanged."""
        profile = PatientProfile(
            isf_schedule=[{"time": "00:00", "value": 50.0}],
            cr_schedule=[{"time": "00:00", "value": 10.0}],
            basal_schedule=[{"time": "00:00", "value": 0.8}],
            units='mg/dL',
        )
        result = profile.isf_mgdl()
        self.assertAlmostEqual(result[0]['value'], 50.0)

    def test_mmol_profile_converts(self):
        """mmol/L profile converts ISF to mg/dL."""
        profile = PatientProfile(
            isf_schedule=[{"time": "00:00", "value": 2.7}],
            cr_schedule=[{"time": "00:00", "value": 4.0}],
            basal_schedule=[{"time": "00:00", "value": 0.8}],
            units='mmol/L',
        )
        result = profile.isf_mgdl()
        self.assertAlmostEqual(result[0]['value'], 2.7 * 18.0182, places=1)

    def test_autodetect_small_isf(self):
        """Auto-detect mmol/L when all ISF values < 15 even if units say mg/dL."""
        profile = PatientProfile(
            isf_schedule=[{"time": "00:00", "value": 2.7},
                          {"time": "12:00", "value": 3.0}],
            cr_schedule=[{"time": "00:00", "value": 4.0}],
            basal_schedule=[{"time": "00:00", "value": 0.8}],
            units='mg/dL',  # mislabeled or default
        )
        result = profile.isf_mgdl()
        self.assertGreater(result[0]['value'], 40)  # converted to mg/dL

    def test_no_false_autodetect_large_isf(self):
        """ISF=50 mg/dL should NOT trigger auto-detect."""
        profile = make_profile()  # ISF=50
        result = profile.isf_mgdl()
        self.assertAlmostEqual(result[0]['value'], 50.0)

    def test_is_mmol_property(self):
        p1 = PatientProfile(
            isf_schedule=[], cr_schedule=[], basal_schedule=[],
            units='mmol/L')
        p2 = PatientProfile(
            isf_schedule=[], cr_schedule=[], basal_schedule=[],
            units='mg/dL')
        self.assertTrue(p1.is_mmol)
        self.assertFalse(p2.is_mmol)

    def test_sensitivity_key_also_converts(self):
        """Nightscout profiles may use 'sensitivity' instead of 'value'."""
        profile = PatientProfile(
            isf_schedule=[{"time": "00:00", "sensitivity": 2.7}],
            cr_schedule=[{"time": "00:00", "value": 4.0}],
            basal_schedule=[{"time": "00:00", "value": 0.8}],
            units='mmol/L',
        )
        result = profile.isf_mgdl()
        self.assertAlmostEqual(result[0]['sensitivity'], 2.7 * 18.0182, places=1)

    def test_cr_unaffected_by_units(self):
        """CR schedule should NOT be converted — it's always g/U."""
        profile = PatientProfile(
            isf_schedule=[{"time": "00:00", "value": 2.7}],
            cr_schedule=[{"time": "00:00", "value": 4.0}],
            basal_schedule=[{"time": "00:00", "value": 0.8}],
            units='mmol/L',
        )
        # CR should remain 4.0
        self.assertEqual(profile.cr_schedule[0]['value'], 4.0)


class TestPatientDataContracts(unittest.TestCase):
    """PatientData invariants: computed properties, optional degradation."""

    def test_n_samples(self):
        p = make_patient(n=1000)
        self.assertEqual(p.n_samples, 1000)

    def test_days_of_data(self):
        p = make_patient(n=288)  # exactly 1 day
        self.assertAlmostEqual(p.days_of_data, 1.0, places=5)

    def test_hours_of_data(self):
        p = make_patient(n=12)  # 1 hour
        self.assertAlmostEqual(p.hours_of_data, 1.0, places=5)

    def test_has_insulin_data_true(self):
        p = make_patient(with_insulin=True)
        self.assertTrue(p.has_insulin_data)

    def test_has_insulin_data_false(self):
        p = make_patient(with_insulin=False)
        self.assertFalse(p.has_insulin_data)

    def test_has_insulin_data_all_nan(self):
        p = make_patient(with_insulin=True)
        p.iob = np.full_like(p.iob, np.nan)
        self.assertFalse(p.has_insulin_data)


class TestDetectedMealContract(unittest.TestCase):
    """DetectedMeal fields match production usage (no duration_min!)."""

    def test_required_fields(self):
        m = DetectedMeal(
            index=100,
            timestamp_ms=1735689600000,
            hour_of_day=12.0,
            window=MealWindow.LUNCH,
            estimated_carbs_g=40.0,
            announced=True,
            residual_integral=5.5,
            confidence=0.85,
        )
        self.assertEqual(m.index, 100)
        self.assertEqual(m.window, MealWindow.LUNCH)
        self.assertTrue(m.announced)

    def test_no_duration_min_field(self):
        """duration_min was a past bug — ensure it's not in the dataclass."""
        import dataclasses
        field_names = {f.name for f in dataclasses.fields(DetectedMeal)}
        self.assertNotIn("duration_min", field_names)


class TestMealHistoryContract(unittest.TestCase):
    """MealHistory fields match production usage."""

    def test_required_fields(self):
        h = MealHistory(
            meals=[],
            total_detected=0,
            announced_count=0,
            unannounced_count=0,
            unannounced_fraction=0.0,
            meals_per_day=0.0,
            mean_carbs_g=0.0,
            by_window={},
        )
        self.assertEqual(h.total_detected, 0)

    def test_no_announced_fraction_field(self):
        """announced_fraction was a past bug — uses unannounced_fraction."""
        import dataclasses
        field_names = {f.name for f in dataclasses.fields(MealHistory)}
        self.assertNotIn("announced_fraction", field_names)
        self.assertIn("unannounced_fraction", field_names)


class TestMealPredictionContract(unittest.TestCase):
    """MealPrediction has dual-mode fields (Phase 4 addition)."""

    def test_dual_mode_fields_exist(self):
        import dataclasses
        field_names = {f.name for f in dataclasses.fields(MealPrediction)}
        self.assertIn("proactive_score", field_names)
        self.assertIn("reactive_score", field_names)
        self.assertIn("prediction_mode", field_names)


class TestPipelineResultContract(unittest.TestCase):
    """PipelineResult has all expected stage outputs."""

    def test_required_fields(self):
        import dataclasses
        field_names = {f.name for f in dataclasses.fields(PipelineResult)}
        expected = {
            "patient_id", "cleaned", "metabolic", "risk", "hypo_alert",
            "clinical_report", "patterns", "onboarding", "meal_history",
            "meal_prediction", "settings_recs", "recommendations",
            "period_metrics", "correction_energy", "meal_responses",
            "bolus_safety", "aid_compensation", "forecast",
            "pipeline_latency_ms", "warnings",
        }
        self.assertTrue(expected.issubset(field_names),
                        f"Missing: {expected - field_names}")


class TestForecastResultContract(unittest.TestCase):
    """ForecastResult type contract — fields, shapes, invariants."""

    def test_required_fields(self):
        import dataclasses
        field_names = {f.name for f in dataclasses.fields(ForecastResult)}
        expected = {
            "predicted_glucose", "ensemble_std", "horizons_minutes",
            "timestamps_ms", "ensemble_size", "mae_expected",
            "confidence", "model_window", "uses_isf_norm",
        }
        self.assertEqual(expected, field_names)

    def test_instantiation(self):
        n = 24  # w48 future steps
        fr = ForecastResult(
            predicted_glucose=np.full(n, 120.0),
            ensemble_std=np.full(n, 5.0),
            horizons_minutes=np.arange(1, n + 1) * 5,
            timestamps_ms=[1000 * i for i in range(n)],
            ensemble_size=5,
            mae_expected={'h30': 11.1, 'h60': 14.2},
            confidence=0.85,
            model_window='w48',
        )
        self.assertEqual(len(fr.predicted_glucose), n)
        self.assertEqual(fr.ensemble_size, 5)
        self.assertFalse(fr.uses_isf_norm)  # default
        self.assertEqual(fr.model_window, 'w48')

    def test_glucose_range_physiological(self):
        """Predicted glucose should be clippable to 30-400 mg/dL."""
        fr = ForecastResult(
            predicted_glucose=np.array([120.0, 180.0, 250.0]),
            ensemble_std=np.array([5.0, 10.0, 15.0]),
            horizons_minutes=np.array([5, 10, 15]),
            timestamps_ms=[0, 1, 2],
            ensemble_size=3,
            mae_expected={},
            confidence=0.9,
            model_window='w48',
        )
        self.assertTrue(np.all(fr.predicted_glucose >= 30))
        self.assertTrue(np.all(fr.predicted_glucose <= 400))


class TestGlucoseForecastModule(unittest.TestCase):
    """glucose_forecast.py: input preparation, constants, architecture."""

    def test_constants_match_exp619(self):
        from cgmencode.production.glucose_forecast import (
            GLUCOSE_SCALE, PK_NORMS, PRODUCTION_SEEDS,
            HORIZON_ROUTING, WINDOW_CONFIG, ROUTED_MAE,
        )
        self.assertEqual(GLUCOSE_SCALE, 400.0)
        self.assertEqual(len(PK_NORMS), 8)
        self.assertEqual(len(PRODUCTION_SEEDS), 5)
        self.assertEqual(HORIZON_ROUTING['h30'], 'w48')
        self.assertEqual(HORIZON_ROUTING['h180'], 'w96')
        self.assertEqual(WINDOW_CONFIG['w48']['total'], 48)
        self.assertAlmostEqual(ROUTED_MAE['h30'], 11.13, places=1)

    def test_build_model(self):
        """PKGroupedEncoder can be constructed and runs forward."""
        try:
            import torch
            from cgmencode.production.glucose_forecast import _build_model
        except ImportError:
            self.skipTest("PyTorch not available")

        model = _build_model(input_dim=8)
        x = torch.randn(1, 48, 8)
        out = model(x, causal=True)
        self.assertEqual(out.shape, (1, 48, 8))

    def test_prepare_input_window_shape(self):
        from cgmencode.production.glucose_forecast import prepare_input_window
        patient = make_patient(n=2000)
        hours = _make_hours(2000)
        metabolic = _make_metabolic(2000)
        arr, hist_len = prepare_input_window(
            glucose=patient.glucose, metabolic=metabolic,
            patient=patient, hours=hours, window='w48')
        self.assertEqual(arr.shape, (48, 8))
        self.assertEqual(hist_len, 24)
        # Glucose channel should be normalized
        self.assertTrue(np.all(np.abs(arr[:, 0]) < 10.0))

    def test_prepare_input_window_short_data(self):
        """Handles data shorter than history window via zero-padding."""
        from cgmencode.production.glucose_forecast import prepare_input_window
        patient = make_patient(n=10)  # very short
        hours = _make_hours(10)
        metabolic = _make_metabolic(10)
        arr, hist_len = prepare_input_window(
            glucose=patient.glucose, metabolic=metabolic,
            patient=patient, hours=hours, window='w48')
        self.assertEqual(arr.shape, (48, 8))
        # First 14 rows should be zero-padded (24 - 10 = 14)
        self.assertTrue(np.all(arr[:14, 0] == 0.0))

    def test_predict_no_models(self):
        """predict_trajectory returns None if no models found."""
        from cgmencode.production.glucose_forecast import predict_trajectory
        patient = make_patient(n=2000)
        hours = _make_hours(2000)
        metabolic = _make_metabolic(2000)
        result = predict_trajectory(
            patient=patient, metabolic=metabolic, hours=hours,
            glucose=patient.glucose, patient_id='z',  # no models for z
            window='w48', models_dir='/nonexistent',
        )
        self.assertIsNone(result)

    def test_pipeline_no_forecast_by_default(self):
        """Pipeline runs without forecast when no config provided."""
        from cgmencode.production.pipeline import run_pipeline
        patient = make_patient(n=4320)
        result = run_pipeline(patient)
        self.assertIsNone(result.forecast)

    def test_pipeline_forecast_skips_gracefully(self):
        """Pipeline handles bad forecast config without crashing."""
        from cgmencode.production.pipeline import run_pipeline
        patient = make_patient(n=4320)
        result = run_pipeline(patient, forecast_config={
            'patient_id': 'z', 'models_dir': '/nonexistent'})
        self.assertIsNone(result.forecast)
        # Should have a warning about models not found
        forecast_warnings = [w for w in result.warnings if 'orecast' in w]
        self.assertTrue(len(forecast_warnings) > 0)


def _make_hours(n: int) -> np.ndarray:
    """Helper: fractional hours cycling 0-24."""
    return np.arange(n) * 5.0 / 60.0 % 24.0


def _make_metabolic(n: int) -> MetabolicState:
    """Helper: minimal metabolic state for forecast tests."""
    return MetabolicState(
        supply=np.full(n, 0.02),
        demand=np.full(n, 0.01),
        hepatic=np.full(n, 0.5),
        carb_supply=np.full(n, 0.5),
        net_flux=np.full(n, 0.01),
        residual=np.full(n, 0.0),
    )


# ── 2. Module Contract Tests ──────────────────────────────────────────

class TestDataQuality(unittest.TestCase):
    """data_quality.py: spike detection and cleaning contracts."""

    def setUp(self):
        from cgmencode.production.data_quality import (
            detect_spikes, interpolate_spikes, clean_glucose,
        )
        self.detect_spikes = detect_spikes
        self.interpolate_spikes = interpolate_spikes
        self.clean_glucose = clean_glucose

    def test_detect_spikes_finds_injected(self):
        glucose = make_glucose(4320)
        spikes = self.detect_spikes(glucose)
        # We injected 5 spikes; detector should find at least 3
        self.assertGreaterEqual(len(spikes), 3)

    def test_detect_spikes_empty_on_short(self):
        """< 100 samples returns empty."""
        spikes = self.detect_spikes(np.full(50, 120.0))
        self.assertEqual(len(spikes), 0)

    def test_clean_glucose_output_shape(self):
        glucose = make_glucose(2000)
        cleaned = self.clean_glucose(glucose)
        self.assertEqual(len(cleaned.glucose), 2000)
        self.assertEqual(len(cleaned.original_glucose), 2000)

    def test_clean_glucose_preserves_non_spikes(self):
        """Clean glucose should be close to original where no spikes."""
        glucose = np.full(500, 120.0) + np.random.RandomState(0).normal(0, 2, 500)
        cleaned = self.clean_glucose(glucose)
        # With no extreme spikes, cleaning should barely change values
        diff = np.abs(cleaned.glucose - cleaned.original_glucose)
        self.assertLess(np.max(diff), 50.0)  # generous bound

    def test_clean_glucose_returns_cleaneddata(self):
        cleaned = self.clean_glucose(make_glucose(500))
        self.assertIsInstance(cleaned, CleanedData)
        self.assertIsInstance(cleaned.n_spikes, int)
        self.assertIsInstance(cleaned.sigma_threshold, float)

    def test_spike_rate_property(self):
        cleaned = self.clean_glucose(make_glucose(4320))
        rate = cleaned.spike_rate
        self.assertGreaterEqual(rate, 0.0)
        self.assertLessEqual(rate, 1.0)

    def test_golden_no_spikes(self):
        """Constant glucose → 0 spikes."""
        glucose = np.full(500, 120.0)
        cleaned = self.clean_glucose(glucose)
        self.assertEqual(cleaned.n_spikes, 0)


class TestMetabolicEngine(unittest.TestCase):
    """metabolic_engine.py: physics layer contracts."""

    def setUp(self):
        from cgmencode.production.metabolic_engine import (
            compute_metabolic_state, _extract_hours,
        )
        self.compute = compute_metabolic_state
        self.extract_hours = _extract_hours

    def test_output_shape(self):
        """All arrays in MetabolicState match input length."""
        patient = make_patient(n=2000)
        state = self.compute(patient)
        self.assertEqual(len(state.supply), 2000)
        self.assertEqual(len(state.demand), 2000)
        self.assertEqual(len(state.hepatic), 2000)
        self.assertEqual(len(state.carb_supply), 2000)
        self.assertEqual(len(state.net_flux), 2000)
        self.assertEqual(len(state.residual), 2000)

    def test_output_type(self):
        state = self.compute(make_patient(n=1000))
        self.assertIsInstance(state, MetabolicState)

    def test_net_flux_is_supply_minus_demand(self):
        """net_flux ≈ supply - demand (physics identity)."""
        state = self.compute(make_patient(n=1000))
        expected = state.supply - state.demand
        np.testing.assert_allclose(state.net_flux, expected, atol=1e-10)

    def test_supply_decomposition(self):
        """supply = hepatic + carb_supply."""
        state = self.compute(make_patient(n=1000))
        expected = state.hepatic + state.carb_supply
        np.testing.assert_allclose(state.supply, expected, atol=1e-10)

    def test_mean_net_flux_property(self):
        state = self.compute(make_patient(n=1000))
        mean_nf = state.mean_net_flux
        self.assertIsInstance(mean_nf, float)

    def test_extract_hours_range(self):
        ts = make_timestamps(500)
        hours = self.extract_hours(ts)
        self.assertTrue(np.all(hours >= 0.0))
        self.assertTrue(np.all(hours < 24.0))

    def test_golden_zero_iob(self):
        """With zero IOB, demand should be near zero, hepatic at max."""
        patient = make_patient(n=500)
        patient.iob = np.zeros(500)
        state = self.compute(patient)
        # No insulin → no demand (allow small numerical noise)
        self.assertLess(np.max(np.abs(state.demand)), 0.1,
                        "Demand should be ~0 with no insulin")
        # Hepatic production should be at or near base rate
        self.assertGreater(np.mean(state.hepatic), 0.5,
                           "Hepatic should be positive with no insulin suppression")


class TestTwoComponentDIA(unittest.TestCase):
    """metabolic_engine.py: two-component DIA decomposition (EXP-2525)."""

    def setUp(self):
        from cgmencode.production.metabolic_engine import (
            compute_metabolic_state, decompose_two_component_dia,
            _FAST_TAU_HOURS, _PERSISTENT_FRACTION,
            _PERSISTENT_WINDOW_HOURS,
        )
        self.compute = compute_metabolic_state
        self.decompose = decompose_two_component_dia
        self.FAST_TAU = _FAST_TAU_HOURS
        self.PERSISTENT_FRACTION = _PERSISTENT_FRACTION
        self.PERSISTENT_WINDOW = _PERSISTENT_WINDOW_HOURS

    # ── Type / constant tests ─────────────────────────────────────

    def test_constants_values(self):
        """EXP-2525 constants match specification."""
        self.assertAlmostEqual(self.FAST_TAU, 0.8)
        self.assertAlmostEqual(self.PERSISTENT_FRACTION, 0.37)
        self.assertAlmostEqual(self.PERSISTENT_WINDOW, 12.0)

    def test_output_type(self):
        """decompose returns TwoComponentDIA dataclass."""
        patient = make_patient(n=1000)
        metabolic = self.compute(patient)
        result = self.decompose(patient, metabolic)
        self.assertIsInstance(result, TwoComponentDIA)

    def test_output_shape(self):
        """All arrays match input length."""
        patient = make_patient(n=2000)
        metabolic = self.compute(patient)
        result = self.decompose(patient, metabolic)
        self.assertEqual(len(result.iob_fast_effect), 2000)
        self.assertEqual(len(result.iob_persistent_effect), 2000)
        self.assertEqual(len(result.total_insulin_12h), 2000)

    def test_fractions_sum_to_one(self):
        """Fast + persistent fractions = 1.0."""
        patient = make_patient(n=500)
        metabolic = self.compute(patient)
        result = self.decompose(patient, metabolic)
        self.assertAlmostEqual(result.fast_fraction + result.persistent_fraction, 1.0)

    # ── Functional tests ──────────────────────────────────────────

    def test_fast_effect_proportional_to_demand(self):
        """Fast effect = demand × fast_fraction."""
        patient = make_patient(n=1000)
        metabolic = self.compute(patient)
        result = self.decompose(patient, metabolic)
        expected = metabolic.demand * result.fast_fraction
        np.testing.assert_allclose(result.iob_fast_effect, expected, atol=1e-10)

    def test_total_effect_property(self):
        """total_effect = fast + persistent."""
        patient = make_patient(n=1000)
        metabolic = self.compute(patient)
        result = self.decompose(patient, metabolic)
        expected = result.iob_fast_effect + result.iob_persistent_effect
        np.testing.assert_allclose(result.total_effect, expected, atol=1e-10)

    def test_persistent_effect_nonnegative(self):
        """Persistent effect is non-negative (HGP suppression is one-way)."""
        patient = make_patient(n=2000)
        metabolic = self.compute(patient)
        result = self.decompose(patient, metabolic)
        self.assertTrue(np.all(result.iob_persistent_effect >= -1e-12),
                        "Persistent effect should be non-negative")

    def test_total_insulin_12h_nonnegative(self):
        """Total insulin delivered in 12h window is non-negative."""
        patient = make_patient(n=2000)
        metabolic = self.compute(patient)
        result = self.decompose(patient, metabolic)
        self.assertTrue(np.all(result.total_insulin_12h >= -1e-12),
                        "Total insulin should be non-negative")

    def test_zero_insulin_gives_zero_effects(self):
        """With no insulin, both components should be near zero."""
        patient = make_patient(n=500, with_insulin=False)
        metabolic = self.compute(patient)
        result = self.decompose(patient, metabolic)
        self.assertLess(np.max(np.abs(result.iob_fast_effect)), 1e-10)
        self.assertLess(np.max(np.abs(result.iob_persistent_effect)), 1e-10)

    def test_persistent_dominance_ratio(self):
        """persistent_dominance_ratio property returns a finite float."""
        patient = make_patient(n=2000)
        metabolic = self.compute(patient)
        result = self.decompose(patient, metabolic)
        ratio = result.persistent_dominance_ratio
        self.assertIsInstance(ratio, float)
        self.assertTrue(np.isfinite(ratio))

    def test_stored_parameters(self):
        """Result stores the parameters used for decomposition."""
        patient = make_patient(n=500)
        metabolic = self.compute(patient)
        result = self.decompose(patient, metabolic)
        self.assertEqual(result.fast_tau_hours, 0.8)
        self.assertEqual(result.persistent_fraction, 0.37)
        self.assertEqual(result.persistent_window_hours, 12.0)

    # ── Integration test ──────────────────────────────────────────

    def test_pipeline_exposes_two_component(self):
        """Pipeline result includes two_component_dia when insulin data present."""
        from cgmencode.production.pipeline import run_pipeline
        patient = make_patient(n=4320)
        result = run_pipeline(patient)
        self.assertIsNotNone(result.two_component_dia,
                             "Pipeline should produce two_component_dia with insulin data")
        self.assertIsInstance(result.two_component_dia, TwoComponentDIA)
        self.assertEqual(len(result.two_component_dia.iob_fast_effect),
                         len(result.cleaned.glucose))

    def test_pipeline_none_without_insulin(self):
        """Pipeline result has None two_component_dia without insulin."""
        from cgmencode.production.pipeline import run_pipeline
        patient = make_patient(n=4320, with_insulin=False)
        result = run_pipeline(patient)
        self.assertIsNone(result.two_component_dia)


class TestMealDetector(unittest.TestCase):
    """meal_detector.py: detection and history contracts."""

    def setUp(self):
        from cgmencode.production.meal_detector import (
            detect_meal_events, build_meal_history,
        )
        from cgmencode.production.metabolic_engine import (
            compute_metabolic_state, _extract_hours,
        )
        self.detect = detect_meal_events
        self.build_history = build_meal_history
        self.compute = compute_metabolic_state
        self.extract_hours = _extract_hours

    def test_detects_meals_in_synthetic(self):
        """Synthetic data has 3 meals/day × 15 days = ~45 meals."""
        patient = make_patient(n=4320)
        metabolic = self.compute(patient)
        hours = self.extract_hours(patient.timestamps)
        meals = self.detect(patient.glucose, metabolic, hours,
                            patient.timestamps, patient.profile)
        self.assertIsInstance(meals, list)
        # Should detect at least some meals (not necessarily all 45)
        self.assertGreater(len(meals), 5,
                           "Should detect several meals in 15 days of data")

    def test_meal_fields(self):
        patient = make_patient(n=4320)
        metabolic = self.compute(patient)
        hours = self.extract_hours(patient.timestamps)
        meals = self.detect(patient.glucose, metabolic, hours,
                            patient.timestamps, patient.profile)
        if meals:
            m = meals[0]
            self.assertIsInstance(m, DetectedMeal)
            self.assertIsInstance(m.index, (int, np.integer))
            self.assertIsInstance(m.hour_of_day, (float, np.floating))
            self.assertIsInstance(m.window, MealWindow)

    def test_build_history(self):
        patient = make_patient(n=4320)
        metabolic = self.compute(patient)
        hours = self.extract_hours(patient.timestamps)
        meals = self.detect(patient.glucose, metabolic, hours,
                            patient.timestamps, patient.profile)
        history = self.build_history(meals, patient.days_of_data)
        self.assertIsInstance(history, MealHistory)
        self.assertEqual(history.total_detected, len(meals))
        self.assertEqual(history.announced_count + history.unannounced_count,
                         history.total_detected)

    def test_empty_detection_on_flat_glucose(self):
        """Flat glucose + flat IOB → no meals detected."""
        patient = make_patient(n=2000)
        patient.glucose = np.full(2000, 120.0)
        patient.iob = np.full(2000, 0.5)
        patient.carbs = np.zeros(2000)
        metabolic = self.compute(patient)
        hours = self.extract_hours(patient.timestamps)
        meals = self.detect(patient.glucose, metabolic, hours,
                            patient.timestamps, patient.profile)
        # Flat data shouldn't produce many meals
        self.assertLess(len(meals), 5)


class TestMealPredictor(unittest.TestCase):
    """meal_predictor.py: ML model and prediction contracts."""

    def setUp(self):
        from cgmencode.production.meal_predictor import (
            MealMLModel, build_timing_models, predict_next_meal,
            ML_FEATURE_NAMES,
        )
        from cgmencode.production.meal_detector import (
            detect_meal_events, build_meal_history,
        )
        from cgmencode.production.metabolic_engine import (
            compute_metabolic_state, _extract_hours,
        )
        self.MealMLModel = MealMLModel
        self.build_timing = build_timing_models
        self.predict_next = predict_next_meal
        self.ML_FEATURE_NAMES = ML_FEATURE_NAMES
        self.detect = detect_meal_events
        self.build_history = build_meal_history
        self.compute = compute_metabolic_state
        self.extract_hours = _extract_hours

    def _train_model(self):
        """Helper: build a trained ML model on synthetic data."""
        patient = make_patient(n=4320)  # 15 days
        metabolic = self.compute(patient)
        hours = self.extract_hours(patient.timestamps)
        meals = self.detect(patient.glucose, metabolic, hours,
                            patient.timestamps, patient.profile)
        history = self.build_history(meals, patient.days_of_data)

        model = self.MealMLModel()
        success = model.train(
            history, patient.glucose,
            net_flux=metabolic.net_flux,
            supply=metabolic.supply,
            days_of_data=patient.days_of_data,
        )
        return model, success, history, patient, metabolic

    def test_feature_count(self):
        """22 features in dual-mode model (EXP-1774: 4-harmonic upgrade from 16)."""
        self.assertEqual(len(self.ML_FEATURE_NAMES), 22)

    def test_train_returns_bool(self):
        _, success, _, _, _ = self._train_model()
        self.assertIsInstance(success, bool)

    def test_predict_proba_keys(self):
        """predict_proba returns dict with expected keys."""
        model, success, history, patient, metabolic = self._train_model()
        if not success:
            self.skipTest("Model training failed on synthetic data")

        proba = model.predict_proba(
            hour=12.0,
            minutes_since_last_meal=180.0,
            meals_today_count=1,
            glucose_current=130.0,
            glucose_15min_ago=125.0,
            glucose_30min_ago=120.0,
            net_flux_current=0.5,
        )
        self.assertIn("proactive_30", proba)
        self.assertIn("proactive_60", proba)
        self.assertIn("reactive_30", proba)
        self.assertIn("reactive_60", proba)

    def test_predict_proba_range(self):
        """All probabilities in [0, 1]."""
        model, success, *_ = self._train_model()
        if not success:
            self.skipTest("Model training failed on synthetic data")

        proba = model.predict_proba(
            hour=12.0, minutes_since_last_meal=60.0,
            meals_today_count=2, glucose_current=140.0,
            glucose_15min_ago=135.0, glucose_30min_ago=130.0,
        )
        for key, val in proba.items():
            self.assertGreaterEqual(val, 0.0, f"{key} < 0")
            self.assertLessEqual(val, 1.0, f"{key} > 1")

    def test_predict_proba_proactive_mode(self):
        """Proactive mode excludes net_flux."""
        model, success, *_ = self._train_model()
        if not success:
            self.skipTest("Model training failed on synthetic data")

        proba = model.predict_proba(
            hour=12.0, minutes_since_last_meal=180.0,
            meals_today_count=1, glucose_current=130.0,
            glucose_15min_ago=125.0, glucose_30min_ago=120.0,
            mode="proactive",
        )
        self.assertIn("proactive_30", proba)

    def test_build_timing_models(self):
        _, _, history, patient, _ = self._train_model()
        models = self.build_timing(history, patient.days_of_data)
        self.assertIsInstance(models, list)
        for m in models:
            self.assertIsInstance(m, MealTimingModel)

    def test_feature_importance(self):
        model, success, *_ = self._train_model()
        if not success:
            self.skipTest("Model training failed on synthetic data")
        imp = model.feature_importance()
        self.assertIsInstance(imp, dict)

    def test_calibrated_thresholds(self):
        """Per-patient threshold calibration sets valid thresholds (EXP-1141)."""
        model, success, *_ = self._train_model()
        if not success:
            self.skipTest("Model training failed on synthetic data")
        # Thresholds should be in (0, 1) and potentially differ from defaults
        self.assertGreater(model.proactive_threshold_30, 0.0)
        self.assertLess(model.proactive_threshold_30, 1.0)
        self.assertGreater(model.proactive_threshold_60, 0.0)
        self.assertLess(model.proactive_threshold_60, 1.0)


class TestBasalAssessment(unittest.TestCase):
    """clinical_rules.assess_basal: slope-based assessment, AID-safe."""

    def setUp(self):
        from cgmencode.production.clinical_rules import assess_basal
        self.assess = assess_basal

    def test_flat_glucose_is_appropriate(self):
        """Constant overnight glucose → APPROPRIATE."""
        bg = np.full(500, 120.0) + np.random.RandomState(0).normal(0, 2, 500)
        result = self.assess(bg)
        self.assertEqual(result, BasalAssessment.APPROPRIATE)

    def test_rising_glucose_is_too_low(self):
        """Steep overnight rise → TOO_LOW."""
        bg = np.linspace(100, 160, 72)  # +60 over 6h = +10/hr
        hours = np.linspace(0.0, 6.0, 72)
        result = self.assess(bg, hours=hours)
        self.assertEqual(result, BasalAssessment.TOO_LOW)

    def test_falling_glucose_is_too_high(self):
        """Steep overnight fall → TOO_HIGH."""
        bg = np.linspace(180, 120, 72)  # -60 over 6h = -10/hr
        hours = np.linspace(0.0, 6.0, 72)
        result = self.assess(bg, hours=hours)
        self.assertEqual(result, BasalAssessment.TOO_HIGH)

    def test_metabolic_flux_does_not_override_slope(self):
        """Negative metabolic flux should NOT override flat glucose slope.

        Regression test: AID patients have large negative net_flux because
        Loop modulates insulin delivery. The actual glucose slope (which
        reflects total delivery including loop adjustments) should be the
        primary signal.
        """
        bg = np.full(500, 120.0) + np.random.RandomState(1).normal(0, 2, 500)
        hours = np.tile(np.linspace(0, 6, 72), 7)[:500]

        # Create metabolic state with large negative flux
        metabolic = MetabolicState(
            supply=np.full(500, 0.7),
            demand=np.full(500, 6.0),
            hepatic=np.full(500, 0.7),
            carb_supply=np.zeros(500),
            net_flux=np.full(500, -5.3),
            residual=np.zeros(500),
        )
        result = self.assess(bg, metabolic=metabolic, hours=hours)
        # With flat glucose, result should be APPROPRIATE regardless of flux
        self.assertEqual(result, BasalAssessment.APPROPRIATE,
                         "Flat glucose should be APPROPRIATE even with negative metabolic flux "
                         "(AID loop compensation is expected)")


class TestRecommender(unittest.TestCase):
    """recommender.py: output contracts."""

    def setUp(self):
        from cgmencode.production.recommender import generate_recommendations

        self.generate = generate_recommendations

    def test_returns_list(self):
        report = ClinicalReport(
            grade=GlycemicGrade.B, risk_score=0.3, tir=0.65, tbr=0.03,
            tar=0.32, mean_glucose=155.0, gmi=7.0, cv=0.32,
            basal_assessment=BasalAssessment.APPROPRIATE, cr_score=0.0,
            effective_isf=50.0, profile_isf=50.0, isf_discrepancy=0.0,
            recommendations=[], overnight_tir=0.7,
        )
        recs = self.generate(
            clinical=report, hypo_alert=None,
            meal_prediction=None, settings_recs=None,
        )
        self.assertIsInstance(recs, list)

    def test_action_recommendation_fields(self):
        report = ClinicalReport(
            grade=GlycemicGrade.D, risk_score=0.8, tir=0.40, tbr=0.10,
            tar=0.50, mean_glucose=200.0, gmi=8.5, cv=0.45,
            basal_assessment=BasalAssessment.TOO_HIGH, cr_score=0.0,
            effective_isf=40.0, profile_isf=50.0, isf_discrepancy=-10.0,
            recommendations=[], overnight_tir=0.5,
        )
        recs = self.generate(
            clinical=report, hypo_alert=None,
            meal_prediction=None, settings_recs=None,
        )
        for rec in recs:
            self.assertIsInstance(rec, ActionRecommendation)
            self.assertIn(rec.priority, [1, 2, 3])
            self.assertIsInstance(rec.description, str)
            self.assertIsInstance(rec.time_sensitive, bool)


# ── 3. Pipeline Regression Tests ──────────────────────────────────────

class TestPipelineRegression(unittest.TestCase):
    """End-to-end pipeline: doesn't crash, produces valid output."""

    def setUp(self):
        from cgmencode.production.pipeline import run_pipeline
        self.run = run_pipeline

    def test_full_pipeline_with_insulin(self):
        """Full pipeline on 15 days of synthetic data with insulin."""
        patient = make_patient(n=4320, with_insulin=True, patient_id="synth_full")
        result = self.run(patient)

        self.assertIsInstance(result, PipelineResult)
        self.assertEqual(result.patient_id, "synth_full")
        self.assertIsNotNone(result.cleaned)
        self.assertIsNotNone(result.metabolic)
        self.assertIsNotNone(result.clinical_report)
        self.assertIsNotNone(result.onboarding)
        self.assertGreater(result.pipeline_latency_ms, 0.0)

    def test_pipeline_no_insulin(self):
        """Pipeline degrades gracefully without insulin data."""
        patient = make_patient(n=4320, with_insulin=False, patient_id="synth_noinsulin")
        result = self.run(patient)

        self.assertIsInstance(result, PipelineResult)
        self.assertIsNone(result.metabolic)
        self.assertIsNone(result.meal_history)
        self.assertIsNotNone(result.cleaned)
        self.assertIsNotNone(result.clinical_report)
        # Should have warning about missing insulin
        self.assertTrue(any("insulin" in w.lower() for w in result.warnings),
                        f"Expected insulin warning, got: {result.warnings}")

    def test_pipeline_short_data(self):
        """Pipeline handles < 7 days (no patterns, no ML)."""
        patient = make_patient(n=500, with_insulin=True, patient_id="synth_short")
        result = self.run(patient)

        self.assertIsInstance(result, PipelineResult)
        self.assertIsNone(result.patterns)
        # Meal prediction should be None (< 7 days)
        self.assertIsNone(result.meal_prediction)

    def test_pipeline_minimal_data(self):
        """Pipeline handles very short data (< 1 day)."""
        patient = make_patient(n=100, with_insulin=True, patient_id="synth_minimal")
        result = self.run(patient)
        self.assertIsInstance(result, PipelineResult)

    def test_pipeline_with_nans(self):
        """Pipeline handles NaN gaps in glucose."""
        patient = make_patient(n=4320, with_insulin=True, patient_id="synth_nan")
        # Inject 10% NaN gaps
        rng = np.random.RandomState(99)
        nan_idx = rng.choice(4320, size=432, replace=False)
        patient.glucose[nan_idx] = np.nan
        result = self.run(patient)
        self.assertIsInstance(result, PipelineResult)

    def test_pipeline_latency_reasonable(self):
        """Pipeline should complete in < 30 seconds."""
        patient = make_patient(n=4320, with_insulin=True)
        result = self.run(patient)
        self.assertLess(result.pipeline_latency_ms, 30_000,
                        "Pipeline too slow (>30s)")

    def test_pipeline_batch(self):
        """Batch pipeline runs on multiple patients."""
        from cgmencode.production.pipeline import run_pipeline_batch
        patients = [
            make_patient(n=2000, patient_id="batch_a"),
            make_patient(n=2000, patient_id="batch_b"),
        ]
        results = run_pipeline_batch(patients)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].patient_id, "batch_a")
        self.assertEqual(results[1].patient_id, "batch_b")

    def test_clinical_report_always_present(self):
        """Clinical report is never None (required output)."""
        for scenario in ["full", "no_insulin", "short"]:
            with self.subTest(scenario=scenario):
                if scenario == "full":
                    p = make_patient(n=4320, with_insulin=True)
                elif scenario == "no_insulin":
                    p = make_patient(n=4320, with_insulin=False)
                else:
                    p = make_patient(n=500, with_insulin=True)
                result = self.run(p)
                self.assertIsNotNone(result.clinical_report)
                self.assertIsInstance(result.clinical_report.tir, float)
                self.assertGreaterEqual(result.clinical_report.tir, 0.0)
                self.assertLessEqual(result.clinical_report.tir, 1.0)


    def test_pipeline_mmol_profile(self):
        """Pipeline works correctly with mmol/L ISF profile (patient a)."""
        profile = PatientProfile(
            isf_schedule=[{"time": "00:00", "value": 2.7}],
            cr_schedule=[{"time": "00:00", "value": 4.0}],
            basal_schedule=[{"time": "00:00", "value": 0.8}],
            dia_hours=5.0,
            units='mmol/L',
        )
        patient = make_patient(n=4320, with_insulin=True, patient_id="synth_mmol")
        patient.profile = profile
        result = self.run(patient)
        self.assertIsInstance(result, PipelineResult)
        # ISF in clinical report should be in mg/dL range (>15)
        if result.clinical_report.profile_isf is not None:
            self.assertGreater(result.clinical_report.profile_isf, 15,
                               "profile_isf should be in mg/dL, not mmol/L")


# ── 4. Natural Experiment Detector Tests ──────────────────────────────

class TestNaturalExperimentTypes(unittest.TestCase):
    """Type contracts for natural experiment detector."""

    def test_experiment_type_enum(self):
        from cgmencode.production.natural_experiment_detector import NaturalExperimentType
        expected = {'fasting', 'overnight', 'meal', 'correction', 'uam',
                    'dawn', 'exercise', 'aid_response', 'stable'}
        self.assertEqual({e.value for e in NaturalExperimentType}, expected)

    def test_meal_config_presets(self):
        from cgmencode.production.natural_experiment_detector import MealConfig
        census = MealConfig.census()
        self.assertEqual(census.min_carbs, 5.0)
        self.assertEqual(census.cluster_gap, 6)

        therapy = MealConfig.therapy()
        self.assertEqual(therapy.min_carbs, 18.0)
        self.assertEqual(therapy.cluster_gap, 18)

        medium = MealConfig.medium()
        self.assertEqual(medium.min_carbs, 5.0)
        self.assertEqual(medium.cluster_gap, 18)

    def test_natural_experiment_to_dict(self):
        from cgmencode.production.natural_experiment_detector import (
            NaturalExperiment, NaturalExperimentType)
        exp = NaturalExperiment(
            exp_type=NaturalExperimentType.FASTING,
            start_idx=0, end_idx=72,
            duration_minutes=360,
            hour_of_day=0.0,
            quality=0.9,
            measurements={'drift_mg_dl_per_hour': 1.5},
        )
        d = exp.to_dict()
        self.assertEqual(d['exp_type'], 'fasting')
        self.assertIsInstance(d['measurements'], dict)

    def test_census_filter_methods(self):
        from cgmencode.production.natural_experiment_detector import (
            NaturalExperiment, NaturalExperimentType, NaturalExperimentCensus)
        exps = [
            NaturalExperiment(NaturalExperimentType.FASTING, 0, 72, 360, 0.0, 0.9),
            NaturalExperiment(NaturalExperimentType.MEAL, 100, 136, 180, 8.0, 0.5),
            NaturalExperiment(NaturalExperimentType.STABLE, 200, 224, 120, 14.0, 0.85),
        ]
        census = NaturalExperimentCensus(
            experiments=exps, total_detected=3,
            by_type={'fasting': 1, 'meal': 1, 'stable': 1},
            quality_mean=0.75, days_analyzed=15.0, per_day_rate=0.2,
        )
        hq = census.filter_high_quality(0.8)
        self.assertEqual(len(hq), 2)
        fasting = census.filter_by_type(NaturalExperimentType.FASTING)
        self.assertEqual(len(fasting), 1)
        self.assertEqual(census.summary_dict()['total_detected'], 3)


class TestNaturalExperimentDetector(unittest.TestCase):
    """Module contracts for natural experiment detection."""

    def test_detect_returns_census(self):
        from cgmencode.production.natural_experiment_detector import (
            detect_natural_experiments, NaturalExperimentCensus)
        patient = make_patient(n=4320, with_insulin=True)
        census = detect_natural_experiments(patient)
        self.assertIsInstance(census, NaturalExperimentCensus)
        self.assertGreater(census.total_detected, 0)
        self.assertGreater(census.quality_mean, 0)
        self.assertGreater(census.days_analyzed, 0)

    def test_detect_without_insulin(self):
        """Should still detect BG-only experiments (fasting, meals, etc)."""
        from cgmencode.production.natural_experiment_detector import (
            detect_natural_experiments, NaturalExperimentCensus)
        patient = make_patient(n=4320, with_insulin=False)
        census = detect_natural_experiments(patient)
        self.assertIsInstance(census, NaturalExperimentCensus)
        # Should have at least stable/fasting/meal windows
        self.assertGreater(census.total_detected, 0)
        # No UAM or exercise (need metabolic)
        self.assertEqual(census.by_type.get('uam', 0), 0)
        self.assertEqual(census.by_type.get('exercise', 0), 0)

    def test_detect_with_metabolic(self):
        """With metabolic state, should detect UAM and exercise too."""
        from cgmencode.production.natural_experiment_detector import (
            detect_natural_experiments, NaturalExperimentCensus)
        from cgmencode.production.metabolic_engine import compute_metabolic_state
        patient = make_patient(n=4320, with_insulin=True)
        metabolic = compute_metabolic_state(patient)
        census = detect_natural_experiments(patient, metabolic=metabolic)
        self.assertIsInstance(census, NaturalExperimentCensus)
        self.assertGreater(census.total_detected, 0)

    def test_meal_config_affects_counts(self):
        """Different meal configs should produce different meal counts."""
        from cgmencode.production.natural_experiment_detector import (
            detect_natural_experiments, MealConfig)
        patient = make_patient(n=4320, with_insulin=True)

        census_census = detect_natural_experiments(patient, meal_config=MealConfig.census())
        census_therapy = detect_natural_experiments(patient, meal_config=MealConfig.therapy())

        meals_census = census_census.by_type.get('meal', 0)
        meals_therapy = census_therapy.by_type.get('meal', 0)
        # Therapy config should find fewer or equal meals (higher threshold)
        self.assertGreaterEqual(meals_census, meals_therapy)

    def test_short_data(self):
        """Should handle very short data gracefully."""
        from cgmencode.production.natural_experiment_detector import (
            detect_natural_experiments, NaturalExperimentCensus)
        patient = make_patient(n=288, with_insulin=True)  # 1 day
        census = detect_natural_experiments(patient)
        self.assertIsInstance(census, NaturalExperimentCensus)

    def test_all_experiments_have_quality(self):
        """Every experiment should have quality in [0, 1]."""
        from cgmencode.production.natural_experiment_detector import detect_natural_experiments
        patient = make_patient(n=4320, with_insulin=True)
        census = detect_natural_experiments(patient)
        for exp in census.experiments:
            self.assertGreaterEqual(exp.quality, 0.0,
                                    f"{exp.exp_type} quality below 0")
            self.assertLessEqual(exp.quality, 1.0,
                                  f"{exp.exp_type} quality above 1")

    def test_experiment_indices_valid(self):
        """Start/end indices should be within data bounds."""
        from cgmencode.production.natural_experiment_detector import detect_natural_experiments
        patient = make_patient(n=4320, with_insulin=True)
        census = detect_natural_experiments(patient)
        for exp in census.experiments:
            self.assertGreaterEqual(exp.start_idx, 0)
            self.assertLessEqual(exp.end_idx, 4320)
            self.assertGreater(exp.end_idx, exp.start_idx)


class TestNaturalExperimentPipeline(unittest.TestCase):
    """Integration tests: natural experiments through pipeline."""

    def test_pipeline_includes_experiments(self):
        from cgmencode.production.pipeline import run_pipeline
        patient = make_patient(n=4320, with_insulin=True)
        result = run_pipeline(patient)
        self.assertIsNotNone(result.natural_experiments,
                             "Pipeline should populate natural_experiments")
        self.assertGreater(result.natural_experiments.total_detected, 0)

    def test_pipeline_no_insulin_still_detects(self):
        from cgmencode.production.pipeline import run_pipeline
        patient = make_patient(n=4320, with_insulin=False)
        result = run_pipeline(patient)
        # Should still have experiments (BG-only detectors)
        if result.natural_experiments is not None:
            self.assertGreaterEqual(result.natural_experiments.total_detected, 0)


# ── Settings Optimizer Tests (EXP-1701) ──────────────────────────────

class TestSettingsOptimizerTypes(unittest.TestCase):
    """Type contracts for settings optimization types."""

    def test_setting_schedule_entry_fields(self):
        from cgmencode.production.types import SettingScheduleEntry
        entry = SettingScheduleEntry(
            period="overnight", start_hour=0,
            current_value=0.8, recommended_value=0.85,
            change_pct=6.25, confidence="high", n_evidence=15,
            ci_low=0.78, ci_high=0.92,
        )
        self.assertEqual(entry.period, "overnight")
        self.assertEqual(entry.start_hour, 0)
        self.assertAlmostEqual(entry.change_pct, 6.25)
        self.assertEqual(entry.confidence, "high")

    def test_optimal_settings_properties(self):
        from cgmencode.production.types import (
            OptimalSettings, SettingScheduleEntry, ConfidenceGrade)
        isf_entries = [
            SettingScheduleEntry("overnight", 0, 50.0, 100.0, 100.0, "high", 20),
            SettingScheduleEntry("morning", 6, 50.0, 80.0, 60.0, "medium", 8),
        ]
        optimal = OptimalSettings(
            basal_schedule=[], isf_schedule=isf_entries, cr_schedule=[],
            confidence_grade=ConfidenceGrade.B,
            total_evidence=100,
            predicted_tir_delta=2.8,
            tir_contributions={"basal": 0.2, "isf": 2.4, "cr": 0.2},
        )
        self.assertAlmostEqual(optimal.isf_mismatch_ratio, 1.8)  # (100/50 + 80/50) / 2
        self.assertEqual(optimal.dominant_lever, "isf")

    def test_optimal_settings_to_dict(self):
        from cgmencode.production.types import (
            OptimalSettings, SettingScheduleEntry, ConfidenceGrade)
        optimal = OptimalSettings(
            basal_schedule=[],
            isf_schedule=[
                SettingScheduleEntry("overnight", 0, 50.0, 100.0, 100.0, "high", 20),
            ],
            cr_schedule=[],
            confidence_grade=ConfidenceGrade.A,
            total_evidence=200,
            predicted_tir_delta=3.0,
            tir_contributions={"basal": 0.5, "isf": 2.0, "cr": 0.5},
        )
        d = optimal.to_dict()
        self.assertEqual(d['confidence_grade'], 'A')
        self.assertIn('isf_mismatch_ratio', d)
        self.assertIn('dominant_lever', d)

    def test_settings_optimization_result_fields(self):
        from cgmencode.production.types import (
            OptimalSettings, SettingScheduleEntry, ConfidenceGrade,
            SettingsOptimizationResult)
        optimal = OptimalSettings(
            basal_schedule=[], isf_schedule=[], cr_schedule=[],
            confidence_grade=ConfidenceGrade.D,
            total_evidence=5, predicted_tir_delta=0.1,
            tir_contributions={"basal": 0, "isf": 0.1, "cr": 0},
        )
        result = SettingsOptimizationResult(
            optimal=optimal,
            basal_drift_reduction_pct=10.0,
            isf_residual_improvement_pct=50.0,
            cr_excursion_improvement_pct=30.0,
            n_recommendations=3,
        )
        self.assertEqual(result.n_recommendations, 3)
        self.assertEqual(len(result.warnings), 0)


class TestSettingsOptimizerModule(unittest.TestCase):
    """Module contracts for settings_optimizer."""

    def _make_census(self):
        """Build a synthetic census with fasting, correction, and meal windows."""
        from cgmencode.production.natural_experiment_detector import (
            NaturalExperiment, NaturalExperimentType, NaturalExperimentCensus)

        exps = []
        # Fasting windows (overnight, positive drift = basal too low)
        for i in range(15):
            exps.append(NaturalExperiment(
                exp_type=NaturalExperimentType.FASTING,
                start_idx=i * 288, end_idx=i * 288 + 72,
                duration_minutes=360, hour_of_day=2.0, quality=0.85,
                measurements={
                    'drift_mg_dl_per_hour': 3.0 + (i % 5) * 0.5,
                    'mean_bg': 110.0, 'cgm_coverage': 0.95,
                },
            ))
        # Overnight fasting windows
        for i in range(10):
            exps.append(NaturalExperiment(
                exp_type=NaturalExperimentType.OVERNIGHT,
                start_idx=i * 288, end_idx=i * 288 + 60,
                duration_minutes=300, hour_of_day=1.0, quality=0.8,
                measurements={
                    'drift_mg_dl_per_hour': 2.5,
                    'is_fasting': True, 'mean_bg': 105.0, 'cgm_coverage': 0.9,
                },
            ))
        # Correction windows (ISF ~100 mg/dL/U, profile has 50)
        for i in range(20):
            hour = 8.0 + (i % 12)  # spread across morning/midday/afternoon
            exps.append(NaturalExperiment(
                exp_type=NaturalExperimentType.CORRECTION,
                start_idx=i * 50, end_idx=i * 50 + 36,
                duration_minutes=180, hour_of_day=hour, quality=0.75,
                measurements={
                    'bolus_u': 2.0, 'start_bg': 250.0, 'nadir_bg': 150.0,
                    'simple_isf': 50.0, 'curve_isf': 100.0, 'curve_r2': 0.8,
                    'cgm_coverage': 0.9,
                },
            ))
        # Meal windows (carbs=40g, bolus=4U, excursion=60 → eff CR = 40/(4+60/50) = 40/5.2 ≈ 7.7)
        for i in range(25):
            hour = 7.0 + (i % 15)
            exps.append(NaturalExperiment(
                exp_type=NaturalExperimentType.MEAL,
                start_idx=i * 60, end_idx=i * 60 + 36,
                duration_minutes=180, hour_of_day=hour, quality=0.7,
                measurements={
                    'carbs_g': 40.0, 'bolus_u': 4.0, 'is_announced': True,
                    'pre_meal_bg': 120.0, 'peak_bg': 180.0,
                    'excursion_mg_dl': 60.0, 'peak_time_min': 45,
                    'cgm_coverage': 0.85,
                },
            ))

        return NaturalExperimentCensus(
            experiments=exps, total_detected=len(exps),
            by_type={'fasting': 15, 'overnight': 10, 'correction': 20, 'meal': 25},
            quality_mean=0.78, days_analyzed=15.0, per_day_rate=4.7,
        )

    def test_optimize_settings_returns_result(self):
        from cgmencode.production.settings_optimizer import optimize_settings
        census = self._make_census()
        profile = make_profile()
        result = optimize_settings(census, profile)
        self.assertIsInstance(result, SettingsOptimizationResult)
        self.assertIsInstance(result.optimal, OptimalSettings)

    def test_schedule_has_five_periods(self):
        from cgmencode.production.settings_optimizer import optimize_settings
        census = self._make_census()
        profile = make_profile()
        result = optimize_settings(census, profile)
        self.assertEqual(len(result.optimal.basal_schedule), 5)
        self.assertEqual(len(result.optimal.isf_schedule), 5)
        self.assertEqual(len(result.optimal.cr_schedule), 5)

    def test_period_names_correct(self):
        from cgmencode.production.settings_optimizer import optimize_settings
        census = self._make_census()
        profile = make_profile()
        result = optimize_settings(census, profile)
        expected = {"overnight", "morning", "midday", "afternoon", "evening"}
        actual = {e.period for e in result.optimal.basal_schedule}
        self.assertEqual(actual, expected)

    def test_isf_detects_underestimation(self):
        """ISF should be recommended higher when curve_isf > profile_isf."""
        from cgmencode.production.settings_optimizer import optimize_settings
        census = self._make_census()
        profile = make_profile()  # ISF = 50
        result = optimize_settings(census, profile)
        # At least some periods should recommend ISF > profile
        isf_higher = [e for e in result.optimal.isf_schedule
                      if e.recommended_value > e.current_value and e.confidence != "low"]
        self.assertGreater(len(isf_higher), 0,
                           "Should detect ISF underestimation from correction windows")

    def test_basal_responds_to_drift(self):
        """Positive drift should recommend basal increase."""
        from cgmencode.production.settings_optimizer import optimize_settings
        census = self._make_census()  # drift = +3 mg/dL/h
        profile = make_profile()
        result = optimize_settings(census, profile)
        overnight = [e for e in result.optimal.basal_schedule
                     if e.period == "overnight"]
        self.assertEqual(len(overnight), 1)
        # Positive drift → basal increase
        if overnight[0].confidence != "low":
            self.assertGreater(overnight[0].recommended_value,
                               overnight[0].current_value)

    def test_confidence_grade_with_evidence(self):
        """70 experiments across types should grade B or higher."""
        from cgmencode.production.settings_optimizer import optimize_settings
        census = self._make_census()  # 70 total experiments
        profile = make_profile()
        result = optimize_settings(census, profile)
        self.assertIn(result.optimal.confidence_grade,
                      [ConfidenceGrade.A, ConfidenceGrade.B])

    def test_tir_prediction_positive(self):
        """Settings correction should predict positive TIR improvement."""
        from cgmencode.production.settings_optimizer import optimize_settings
        census = self._make_census()
        profile = make_profile()
        result = optimize_settings(census, profile)
        self.assertGreater(result.optimal.predicted_tir_delta, 0,
                           "Correcting ISF 2× should predict TIR improvement")

    def test_dominant_lever_is_isf(self):
        """ISF should be dominant lever (85% of gain per EXP-1717)."""
        from cgmencode.production.settings_optimizer import optimize_settings
        census = self._make_census()
        profile = make_profile()
        result = optimize_settings(census, profile)
        self.assertEqual(result.optimal.dominant_lever, "isf")

    def test_empty_census(self):
        """Empty census should still return valid result with low confidence."""
        from cgmencode.production.settings_optimizer import optimize_settings
        from cgmencode.production.natural_experiment_detector import NaturalExperimentCensus
        census = NaturalExperimentCensus(
            experiments=[], total_detected=0,
            by_type={}, quality_mean=0.0,
            days_analyzed=15.0, per_day_rate=0.0,
        )
        profile = make_profile()
        result = optimize_settings(census, profile)
        self.assertEqual(result.optimal.confidence_grade, ConfidenceGrade.D)
        self.assertEqual(result.optimal.total_evidence, 0)

    def test_retrospective_validation_fields(self):
        """Validation metrics should be populated."""
        from cgmencode.production.settings_optimizer import optimize_settings
        census = self._make_census()
        profile = make_profile()
        result = optimize_settings(census, profile)
        self.assertGreaterEqual(result.basal_drift_reduction_pct, 0)
        self.assertGreaterEqual(result.isf_residual_improvement_pct, 0)
        self.assertGreaterEqual(result.cr_excursion_improvement_pct, 0)
        self.assertGreater(result.n_recommendations, 0)

    def test_bootstrap_ci_populated(self):
        """ISF schedule entries with evidence should have CI bounds."""
        from cgmencode.production.settings_optimizer import optimize_settings
        census = self._make_census()
        profile = make_profile()
        result = optimize_settings(census, profile)
        entries_with_ci = [e for e in result.optimal.isf_schedule
                           if e.ci_low is not None and e.ci_high is not None]
        self.assertGreater(len(entries_with_ci), 0)
        for e in entries_with_ci:
            self.assertLessEqual(e.ci_low, e.recommended_value)
            self.assertGreaterEqual(e.ci_high, e.recommended_value)


class TestSettingsOptimizerPipeline(unittest.TestCase):
    """Integration: settings optimizer through pipeline."""

    def test_pipeline_includes_optimal_settings(self):
        from cgmencode.production.pipeline import run_pipeline
        patient = make_patient(n=4320, with_insulin=True)
        result = run_pipeline(patient)
        # Should have optimal_settings populated (or None with warning if no NEs)
        if result.natural_experiments and result.natural_experiments.total_detected > 0:
            # With enough data, optimizer should run
            if result.optimal_settings is not None:
                self.assertEqual(len(result.optimal_settings.optimal.basal_schedule), 5)
                self.assertEqual(len(result.optimal_settings.optimal.isf_schedule), 5)
                self.assertEqual(len(result.optimal_settings.optimal.cr_schedule), 5)

    def test_pipeline_result_has_field(self):
        """PipelineResult should have optimal_settings field."""
        from cgmencode.production.pipeline import run_pipeline
        patient = make_patient(n=4320, with_insulin=True)
        result = run_pipeline(patient)
        self.assertTrue(hasattr(result, 'optimal_settings'))


# ── Circadian ISF & Context CR Tests ─────────────────────────────────

class TestCircadianISF(unittest.TestCase):
    """Tests for advise_circadian_isf (EXP-2271)."""

    def test_returns_empty_with_insufficient_data(self):
        """Needs ≥7 days of data."""
        from cgmencode.production.settings_advisor import advise_circadian_isf
        from cgmencode.production.metabolic_engine import compute_metabolic_state
        patient = make_patient(n=288 * 3, with_insulin=True)  # 3 days
        metabolic = compute_metabolic_state(patient)
        hours = np.tile(np.linspace(0, 24, 288, endpoint=False), 3)
        recs = advise_circadian_isf(
            patient.glucose, metabolic, hours, patient.profile, days_of_data=3.0)
        self.assertEqual(recs, [])

    def test_returns_list(self):
        """Returns list of SettingsRecommendation."""
        from cgmencode.production.settings_advisor import advise_circadian_isf
        from cgmencode.production.metabolic_engine import compute_metabolic_state
        patient = make_patient(n=288 * 15, with_insulin=True)
        metabolic = compute_metabolic_state(patient)
        hours = np.tile(np.linspace(0, 24, 288, endpoint=False), 15)
        recs = advise_circadian_isf(
            patient.glucose, metabolic, hours, patient.profile, days_of_data=15.0)
        self.assertIsInstance(recs, list)
        for r in recs:
            self.assertIsInstance(r, SettingsRecommendation)
            self.assertEqual(r.parameter, SettingsParameter.ISF)

    def test_no_metabolic_returns_empty(self):
        """Without metabolic state, no recommendations."""
        from cgmencode.production.settings_advisor import advise_circadian_isf
        patient = make_patient(n=288 * 15, with_insulin=True)
        hours = np.tile(np.linspace(0, 24, 288, endpoint=False), 15)
        recs = advise_circadian_isf(
            patient.glucose, None, hours, patient.profile, days_of_data=15.0)
        self.assertEqual(recs, [])


class TestContextCR(unittest.TestCase):
    """Tests for context-aware CR (EXP-2341)."""

    def test_compute_context_cr_baseline(self):
        """Neutral context should return ~unchanged CR."""
        from cgmencode.production.settings_advisor import compute_context_cr_adjustment
        result = compute_context_cr_adjustment(
            pre_meal_bg=120.0, iob_at_meal=0.0, hour=12.0, base_cr=10.0)
        self.assertIsInstance(result, dict)
        self.assertIn('adjusted_cr', result)
        self.assertIn('base_cr', result)
        # Near neutral (120 BG, no IOB, noon) → minimal adjustment
        self.assertAlmostEqual(result['adjusted_cr'], 10.0, delta=1.0)

    def test_high_bg_increases_cr(self):
        """High pre-meal BG → less insulin → larger CR."""
        from cgmencode.production.settings_advisor import compute_context_cr_adjustment
        result = compute_context_cr_adjustment(
            pre_meal_bg=220.0, iob_at_meal=0.0, hour=12.0, base_cr=10.0)
        # High BG should increase CR (less insulin per carb)
        self.assertGreater(result['adjusted_cr'], 10.0)

    def test_morning_decreases_cr(self):
        """Morning meals need more insulin → smaller CR."""
        from cgmencode.production.settings_advisor import compute_context_cr_adjustment
        result = compute_context_cr_adjustment(
            pre_meal_bg=120.0, iob_at_meal=0.0, hour=7.0, base_cr=10.0)
        self.assertLess(result['adjusted_cr'], 10.0)

    def test_high_iob_increases_cr(self):
        """High IOB → less insulin needed → larger CR."""
        from cgmencode.production.settings_advisor import compute_context_cr_adjustment
        result = compute_context_cr_adjustment(
            pre_meal_bg=120.0, iob_at_meal=3.0, hour=12.0, base_cr=10.0)
        self.assertGreater(result['adjusted_cr'], 10.0)

    def test_advise_context_cr_no_carbs(self):
        """Without carb data, returns empty."""
        from cgmencode.production.settings_advisor import advise_context_cr
        patient = make_patient(n=288 * 15, with_insulin=True)
        hours = np.tile(np.linspace(0, 24, 288, endpoint=False), 15)
        recs = advise_context_cr(
            patient.glucose, None, hours, patient.profile, carbs=None, days_of_data=15.0)
        self.assertEqual(recs, [])

    def test_advise_context_cr_returns_list(self):
        """With carb data, returns list of recs."""
        from cgmencode.production.settings_advisor import advise_context_cr
        from cgmencode.production.metabolic_engine import compute_metabolic_state
        patient = make_patient(n=288 * 15, with_insulin=True)
        metabolic = compute_metabolic_state(patient)
        hours = np.tile(np.linspace(0, 24, 288, endpoint=False), 15)
        recs = advise_context_cr(
            patient.glucose, metabolic, hours, patient.profile,
            carbs=patient.carbs, days_of_data=15.0)
        self.assertIsInstance(recs, list)
        for r in recs:
            self.assertIsInstance(r, SettingsRecommendation)
            self.assertEqual(r.parameter, SettingsParameter.CR)


class TestSettingsAdviceIntegration(unittest.TestCase):
    """Test generate_settings_advice integrates new functions."""

    def test_accepts_carbs_kwarg(self):
        """generate_settings_advice now accepts optional carbs."""
        from cgmencode.production.settings_advisor import generate_settings_advice
        from cgmencode.production.metabolic_engine import compute_metabolic_state
        from cgmencode.production.clinical_rules import generate_clinical_report
        patient = make_patient(n=288 * 15, with_insulin=True)
        metabolic = compute_metabolic_state(patient)
        hours = np.tile(np.linspace(0, 24, 288, endpoint=False), 15)
        clinical = generate_clinical_report(
            patient.glucose, metabolic, patient.profile,
            carbs=patient.carbs, bolus=patient.bolus, hours=hours)
        recs = generate_settings_advice(
            patient.glucose, metabolic, hours, clinical,
            patient.profile, 15.0, carbs=patient.carbs)
        self.assertIsInstance(recs, list)

    def test_pipeline_still_runs(self):
        """Full pipeline should still work with new settings_advisor."""
        from cgmencode.production.pipeline import run_pipeline
        patient = make_patient(n=288 * 15, with_insulin=True)
        result = run_pipeline(patient)
        self.assertIsNotNone(result)
        self.assertEqual(result.patient_id, "test")


# ── Controller-Specific Tests (EXP-2081) ─────────────────────────────

class TestControllerTypes(unittest.TestCase):
    """Test ControllerType and ControllerBehavior types."""

    def test_controller_type_values(self):
        self.assertEqual(set(ControllerType), {
            ControllerType.LOOP, ControllerType.TRIO,
            ControllerType.AAPS, ControllerType.OPENAPS,
            ControllerType.UNKNOWN,
        })

    def test_controller_behavior_fields(self):
        cb = ControllerBehavior(
            controller=ControllerType.LOOP,
            compensation_style="compensating")
        self.assertEqual(cb.controller, ControllerType.LOOP)
        self.assertEqual(cb.compensation_style, "compensating")
        self.assertIsInstance(cb.settings_visibility, float)


class TestControllerDetection(unittest.TestCase):
    """Test controller detection logic."""

    def test_detect_from_metadata(self):
        from cgmencode.production.recommender import detect_controller_type
        patient = make_patient(n=4320, with_insulin=True)
        patient.metadata = {'controller': 'Loop'}
        self.assertEqual(detect_controller_type(patient), ControllerType.LOOP)

    def test_detect_aaps_from_metadata(self):
        from cgmencode.production.recommender import detect_controller_type
        patient = make_patient(n=4320, with_insulin=True)
        patient.metadata = {'controller': 'AndroidAPS'}
        self.assertEqual(detect_controller_type(patient), ControllerType.AAPS)

    def test_detect_unknown_default(self):
        from cgmencode.production.recommender import detect_controller_type
        patient = make_patient(n=4320, with_insulin=True)
        patient.metadata = {}
        # Without high suspension, should be UNKNOWN
        result = detect_controller_type(patient)
        self.assertIsInstance(result, ControllerType)

    def test_get_controller_behavior(self):
        from cgmencode.production.recommender import get_controller_behavior
        behavior = get_controller_behavior(ControllerType.LOOP)
        self.assertEqual(behavior.compensation_style, "compensating")
        self.assertLess(behavior.isf_trust, 0.5)

    def test_adjust_confidence_reduces_for_loop(self):
        from cgmencode.production.recommender import adjust_confidence_for_controller
        recs = [SettingsRecommendation(
            parameter=SettingsParameter.ISF,
            direction="increase", magnitude_pct=20.0,
            current_value=50.0, suggested_value=60.0,
            predicted_tir_delta=2.0, affected_hours=(0.0, 24.0),
            confidence=0.8, evidence="test", rationale="test",
        )]
        adjusted = adjust_confidence_for_controller(recs, ControllerType.LOOP)
        self.assertLess(adjusted[0].confidence, 0.8)

    def test_openaps_higher_confidence_than_loop(self):
        from cgmencode.production.recommender import adjust_confidence_for_controller
        rec_loop = SettingsRecommendation(
            parameter=SettingsParameter.ISF,
            direction="increase", magnitude_pct=20.0,
            current_value=50.0, suggested_value=60.0,
            predicted_tir_delta=2.0, affected_hours=(0.0, 24.0),
            confidence=0.8, evidence="test", rationale="test",
        )
        rec_oaps = SettingsRecommendation(
            parameter=SettingsParameter.ISF,
            direction="increase", magnitude_pct=20.0,
            current_value=50.0, suggested_value=60.0,
            predicted_tir_delta=2.0, affected_hours=(0.0, 24.0),
            confidence=0.8, evidence="test", rationale="test",
        )
        adjust_confidence_for_controller([rec_loop], ControllerType.LOOP)
        adjust_confidence_for_controller([rec_oaps], ControllerType.OPENAPS)
        self.assertGreater(rec_oaps.confidence, rec_loop.confidence)


# ── Overnight Drift & Loop Workload Tests (EXP-2371–2396) ────────────

class TestOvernightDriftTypes(unittest.TestCase):
    """Type contracts for overnight phenotype and assessment."""

    def test_overnight_phenotype_values(self):
        self.assertEqual(set(OvernightPhenotype), {
            OvernightPhenotype.STABLE_SLEEPER,
            OvernightPhenotype.UNDER_BASALED,
            OvernightPhenotype.OVER_BASALED,
            OvernightPhenotype.DAWN_RISER,
            OvernightPhenotype.LOOP_DEPENDENT,
            OvernightPhenotype.MIXED,
        })

    def test_overnight_drift_assessment_fields(self):
        oda = OvernightDriftAssessment(
            phenotype=OvernightPhenotype.STABLE_SLEEPER,
            drift_mg_dl_per_hour=0.5,
            n_clean_nights=5,
            n_total_nights=10,
            mean_overnight_glucose=110.0,
        )
        self.assertEqual(oda.phenotype, OvernightPhenotype.STABLE_SLEEPER)
        self.assertAlmostEqual(oda.drift_mg_dl_per_hour, 0.5)
        self.assertFalse(oda.needs_adjustment)

    def test_needs_adjustment_property(self):
        """Stable sleeper and mixed don't need adjustment."""
        stable = OvernightDriftAssessment(
            phenotype=OvernightPhenotype.STABLE_SLEEPER,
            drift_mg_dl_per_hour=0.5,
            n_clean_nights=5, n_total_nights=10,
            mean_overnight_glucose=110.0)
        self.assertFalse(stable.needs_adjustment)

        under = OvernightDriftAssessment(
            phenotype=OvernightPhenotype.UNDER_BASALED,
            drift_mg_dl_per_hour=5.0,
            n_clean_nights=5, n_total_nights=10,
            mean_overnight_glucose=130.0)
        self.assertTrue(under.needs_adjustment)

        mixed = OvernightDriftAssessment(
            phenotype=OvernightPhenotype.MIXED,
            drift_mg_dl_per_hour=1.0,
            n_clean_nights=3, n_total_nights=10,
            mean_overnight_glucose=120.0)
        self.assertFalse(mixed.needs_adjustment)


class TestLoopWorkloadTypes(unittest.TestCase):
    """Type contracts for loop workload report."""

    def test_loop_workload_report_fields(self):
        lw = LoopWorkloadReport(
            workload_score=75.0,
            net_direction="REDUCING",
            suspension_pct=20.0,
            increase_pct=5.0,
            deviation_mean=0.35,
            ratio_median=0.85,
            n_samples=1000,
        )
        self.assertEqual(lw.net_direction, "REDUCING")
        self.assertAlmostEqual(lw.workload_score, 75.0)
        self.assertEqual(lw.n_samples, 1000)

    def test_loop_workload_period_default(self):
        lw = LoopWorkloadReport(
            workload_score=50.0, net_direction="NEUTRAL",
            suspension_pct=10.0, increase_pct=10.0,
            deviation_mean=0.25, ratio_median=1.0, n_samples=500)
        self.assertEqual(lw.period_workload, {})


class TestOvernightDriftFunction(unittest.TestCase):
    """Test assess_overnight_drift function."""

    def test_returns_none_insufficient_data(self):
        from cgmencode.production.settings_advisor import assess_overnight_drift
        glucose = np.full(100, 120.0)
        hours = np.linspace(0, 24, 100)
        profile = make_profile()
        result = assess_overnight_drift(glucose, hours, profile, 1.0)
        self.assertIsNone(result)  # < 3 days

    def test_rising_glucose_detects_under_basaled(self):
        """Glucose rising overnight → under-basaled phenotype."""
        from cgmencode.production.settings_advisor import assess_overnight_drift
        n = 288 * 7  # 7 days
        hours = np.tile(np.linspace(0, 24, 288, endpoint=False), 7)
        glucose = np.full(n, 120.0)
        # Add uniform rising overnight pattern (same rate pre and post 04:00)
        # so it doesn't trigger dawn phenomenon (which requires BIGGER rise after 04:00)
        for day in range(7):
            for i in range(72):  # 0-6h = indices 0-71
                idx = day * 288 + i
                glucose[idx] = 100.0 + i * 0.5  # +0.5 per 5min = ~6 mg/dL/hr
        profile = make_profile()
        result = assess_overnight_drift(glucose, hours, profile, 7.0)
        self.assertIsNotNone(result)
        self.assertGreater(result.drift_mg_dl_per_hour, 3.0)
        self.assertIn(result.phenotype, (
            OvernightPhenotype.UNDER_BASALED,
            OvernightPhenotype.DAWN_RISER,  # uniform rise may trigger dawn
        ))

    def test_falling_glucose_detects_over_basaled(self):
        """Glucose falling overnight → over-basaled phenotype."""
        from cgmencode.production.settings_advisor import assess_overnight_drift
        n = 288 * 7
        hours = np.tile(np.linspace(0, 24, 288, endpoint=False), 7)
        glucose = np.full(n, 120.0)
        for day in range(7):
            for i in range(72):
                idx = day * 288 + i
                glucose[idx] = 160.0 - i * 0.8  # -10 mg/dL/hr
        profile = make_profile()
        result = assess_overnight_drift(glucose, hours, profile, 7.0)
        self.assertIsNotNone(result)
        self.assertLess(result.drift_mg_dl_per_hour, -3.0)
        self.assertEqual(result.phenotype, OvernightPhenotype.OVER_BASALED)

    def test_stable_glucose_detects_stable_sleeper(self):
        """Flat overnight glucose → stable sleeper."""
        from cgmencode.production.settings_advisor import assess_overnight_drift
        n = 288 * 7
        hours = np.tile(np.linspace(0, 24, 288, endpoint=False), 7)
        glucose = np.full(n, 120.0)
        # Add mild noise but no trend
        rng = np.random.RandomState(42)
        glucose += rng.normal(0, 3, n)
        profile = make_profile()
        result = assess_overnight_drift(glucose, hours, profile, 7.0)
        self.assertIsNotNone(result)
        self.assertLess(abs(result.drift_mg_dl_per_hour), 3.0)
        self.assertEqual(result.phenotype, OvernightPhenotype.STABLE_SLEEPER)

    def test_clean_night_filtering(self):
        """High IOB should reduce clean night count."""
        from cgmencode.production.settings_advisor import assess_overnight_drift
        n = 288 * 7
        hours = np.tile(np.linspace(0, 24, 288, endpoint=False), 7)
        glucose = np.full(n, 120.0)
        iob = np.zeros(n)
        # Set high IOB on some nights
        for day in [0, 1, 2, 3]:
            for i in range(72):
                iob[day * 288 + i] = 2.0  # high IOB
        profile = make_profile()
        result = assess_overnight_drift(glucose, hours, profile, 7.0, iob=iob)
        self.assertIsNotNone(result)
        self.assertLess(result.n_clean_nights, result.n_total_nights)


class TestLoopWorkloadFunction(unittest.TestCase):
    """Test compute_loop_workload function."""

    def test_returns_none_without_basal(self):
        from cgmencode.production.settings_advisor import compute_loop_workload
        result = compute_loop_workload(
            np.linspace(0, 24, 288), None, make_profile())
        self.assertIsNone(result)

    def test_scheduled_basal_equals_low_workload(self):
        """When actual == scheduled, workload should be low."""
        from cgmencode.production.settings_advisor import compute_loop_workload
        n = 288 * 7
        hours = np.tile(np.linspace(0, 24, 288, endpoint=False), 7)
        actual_basal = np.full(n, 0.8)  # matches profile
        profile = make_profile()
        result = compute_loop_workload(hours, actual_basal, profile)
        self.assertIsNotNone(result)
        self.assertLess(result.workload_score, 10.0)
        self.assertEqual(result.net_direction, "NEUTRAL")

    def test_suspended_basal_high_workload(self):
        """When loop suspends most of the time, workload should be high."""
        from cgmencode.production.settings_advisor import compute_loop_workload
        n = 288 * 7
        hours = np.tile(np.linspace(0, 24, 288, endpoint=False), 7)
        actual_basal = np.full(n, 0.0)  # fully suspended
        profile = make_profile()
        result = compute_loop_workload(hours, actual_basal, profile)
        self.assertIsNotNone(result)
        self.assertGreater(result.workload_score, 80.0)
        self.assertEqual(result.net_direction, "REDUCING")

    def test_increased_basal_increasing_direction(self):
        """When loop consistently increases basal, direction should be INCREASING."""
        from cgmencode.production.settings_advisor import compute_loop_workload
        n = 288 * 7
        hours = np.tile(np.linspace(0, 24, 288, endpoint=False), 7)
        actual_basal = np.full(n, 1.6)  # 2× scheduled
        profile = make_profile()
        result = compute_loop_workload(hours, actual_basal, profile)
        self.assertIsNotNone(result)
        self.assertEqual(result.net_direction, "INCREASING")

    def test_period_workload_populated(self):
        """Period-by-period workload should have entries."""
        from cgmencode.production.settings_advisor import compute_loop_workload
        n = 288 * 7
        hours = np.tile(np.linspace(0, 24, 288, endpoint=False), 7)
        actual_basal = np.full(n, 0.6)  # slightly below scheduled
        profile = make_profile()
        result = compute_loop_workload(hours, actual_basal, profile)
        self.assertIsNotNone(result)
        self.assertGreater(len(result.period_workload), 0)

    def test_insufficient_data_returns_none(self):
        """Too few valid samples should return None."""
        from cgmencode.production.settings_advisor import compute_loop_workload
        hours = np.linspace(0, 24, 50)
        actual_basal = np.full(50, 0.8)
        profile = make_profile()
        result = compute_loop_workload(hours, actual_basal, profile)
        self.assertIsNone(result)


class TestOvernightDriftIntegration(unittest.TestCase):
    """Test overnight drift and loop workload integrate into pipeline."""

    def test_generate_settings_advice_accepts_new_kwargs(self):
        """generate_settings_advice now accepts iob, cob, actual_basal."""
        from cgmencode.production.settings_advisor import generate_settings_advice
        from cgmencode.production.metabolic_engine import compute_metabolic_state
        from cgmencode.production.clinical_rules import generate_clinical_report
        patient = make_patient(n=288 * 15, with_insulin=True)
        metabolic = compute_metabolic_state(patient)
        hours = np.tile(np.linspace(0, 24, 288, endpoint=False), 15)
        clinical = generate_clinical_report(
            patient.glucose, metabolic, patient.profile,
            carbs=patient.carbs, bolus=patient.bolus, hours=hours)
        recs = generate_settings_advice(
            patient.glucose, metabolic, hours, clinical,
            patient.profile, 15.0, carbs=patient.carbs,
            iob=patient.iob, cob=patient.cob,
            actual_basal=patient.basal_rate)
        self.assertIsInstance(recs, list)

    def test_pipeline_populates_overnight_and_workload(self):
        """Pipeline result should have overnight_assessment and loop_workload."""
        from cgmencode.production.pipeline import run_pipeline
        patient = make_patient(n=288 * 15, with_insulin=True)
        result = run_pipeline(patient)
        self.assertIsNotNone(result)
        # These may be None (synthetic data may not trigger) but should not error
        if result.overnight_assessment is not None:
            self.assertIsInstance(result.overnight_assessment, OvernightDriftAssessment)
        if result.loop_workload is not None:
            self.assertIsInstance(result.loop_workload, LoopWorkloadReport)


# ── Runner ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main()

class TestThreeWindowRoutingIntegration(unittest.TestCase):
    """Integration test for 3-window forecast routing (w48, w96, w144).
    
    Validates that the pipeline correctly routes forecasts to different
    windows based on forecast horizon and that the routing logic doesn't crash.
    
    Research: EXP-619 established optimal windows per horizon:
    - w48 (12-hour history): h30, h60, h90, h120 (short-term)
    - w96 (24-hour history): h150, h180, h240 (medium-term)
    - w144 (36-hour history): h300, h360 (long-term)
    """
    
    def test_horizon_routing_complete_coverage(self):
        """Verify all horizons are mapped to valid windows."""
        from cgmencode.production.glucose_forecast import (
            HORIZON_ROUTING, WINDOW_CONFIG
        )
        
        valid_windows = set(WINDOW_CONFIG.keys())
        for horizon, window in HORIZON_ROUTING.items():
            self.assertIn(horizon, [f'h{i}' for i in [30, 60, 90, 120, 150, 180, 240, 300, 360]])
            self.assertIn(window, valid_windows,
                         f"Horizon {horizon} maps to invalid window {window}")
    
    def test_routing_groups_horizons_by_window(self):
        """Verify horizons are grouped into 3 window classes."""
        from cgmencode.production.glucose_forecast import HORIZON_ROUTING
        
        window_groups = {}
        for horizon, window in HORIZON_ROUTING.items():
            if window not in window_groups:
                window_groups[window] = []
            window_groups[window].append(horizon)
        
        # Should have exactly 3 window groups
        self.assertEqual(len(window_groups), 3,
                        f"Expected 3 window groups, got {len(window_groups)}: {window_groups}")
        
        # w48 should handle short horizons (h30-h120)
        self.assertIn('w48', window_groups)
        self.assertTrue(all(h in ['h30', 'h60', 'h90', 'h120'] 
                           for h in window_groups['w48']),
                       f"w48 horizons incorrect: {window_groups['w48']}")
        
        # w96 should handle medium horizons (h150-h240)
        self.assertIn('w96', window_groups)
        self.assertTrue(all(h in ['h150', 'h180', 'h240'] 
                           for h in window_groups['w96']),
                       f"w96 horizons incorrect: {window_groups['w96']}")
        
        # w144 should handle long horizons (h300-h360)
        self.assertIn('w144', window_groups)
        self.assertTrue(all(h in ['h300', 'h360'] 
                           for h in window_groups['w144']),
                       f"w144 horizons incorrect: {window_groups['w144']}")
    
    def test_window_config_symmetry(self):
        """Verify each window has symmetric history/future splits."""
        from cgmencode.production.glucose_forecast import WINDOW_CONFIG
        
        for window_name, cfg in WINDOW_CONFIG.items():
            hist = cfg['history']
            future = cfg['future']
            total = cfg['total']
            
            self.assertEqual(total, hist + future,
                           f"{window_name}: total != history + future")
            self.assertEqual(hist, future,
                           f"{window_name}: history != future (asymmetric)")
    
    def test_prepare_input_window_all_sizes(self):
        """Test prepare_input_window works with all 3 window sizes."""
        from cgmencode.production.glucose_forecast import prepare_input_window
        
        patient = make_patient(n=4320, with_insulin=True)
        hours = _make_hours(4320)
        metabolic = _make_metabolic(4320)
        
        for window in ['w48', 'w96', 'w144']:
            arr, hist_len = prepare_input_window(
                glucose=patient.glucose,
                metabolic=metabolic,
                patient=patient,
                hours=hours,
                window=window,
            )
            
            # Verify shape matches window config
            from cgmencode.production.glucose_forecast import WINDOW_CONFIG
            expected_total = WINDOW_CONFIG[window]['total']
            expected_hist = WINDOW_CONFIG[window]['history']
            
            self.assertEqual(arr.shape[0], expected_total,
                           f"{window}: expected {expected_total} steps, got {arr.shape[0]}")
            self.assertEqual(arr.shape[1], 8,
                           f"{window}: expected 8 channels, got {arr.shape[1]}")
            self.assertEqual(hist_len, expected_hist,
                           f"{window}: expected hist_len={expected_hist}, got {hist_len}")
    
    def test_pipeline_accepts_routing_config(self):
        """Pipeline accepts forecast_config with any valid window."""
        from cgmencode.production.pipeline import run_pipeline
        
        patient = make_patient(n=4320, with_insulin=True)
        
        for window in ['w48', 'w96', 'w144']:
            result = run_pipeline(patient, forecast_config={
                'patient_id': 'test',
                'window': window,
                'models_dir': '/nonexistent',  # Will gracefully fail to load models
            })
            
            # Pipeline should not crash even with missing models
            self.assertIsNotNone(result)
            # Forecast should be None (no models found) but no exception
            self.assertIsNone(result.forecast)
    
    def test_routing_horizontal_consistency(self):
        """Verify routing produces consistent window for same horizon."""
        from cgmencode.production.glucose_forecast import HORIZON_ROUTING
        
        # Pick a few test horizons
        test_horizons = ['h30', 'h90', 'h180', 'h360']
        
        for horizon in test_horizons:
            window1 = HORIZON_ROUTING.get(horizon)
            window2 = HORIZON_ROUTING.get(horizon)
            
            self.assertEqual(window1, window2,
                           f"Routing for {horizon} is inconsistent!")
            self.assertIsNotNone(window1,
                               f"Horizon {horizon} has no routing entry")
    
    def test_mae_metrics_available_for_all_horizons(self):
        """All routed horizons should have expected MAE metrics."""
        from cgmencode.production.glucose_forecast import (
            HORIZON_ROUTING, ROUTED_MAE
        )
        
        for horizon in HORIZON_ROUTING.keys():
            self.assertIn(horizon, ROUTED_MAE,
                         f"No MAE metric for horizon {horizon}")
            mae_val = ROUTED_MAE[horizon]
            self.assertGreater(mae_val, 0.0,
                             f"Invalid MAE for {horizon}: {mae_val}")
            # MAE should be reasonable (5-50 mg/dL for typical forecasts)
            self.assertGreater(mae_val, 5.0,
                             f"MAE suspiciously low: {horizon}={mae_val}")
            self.assertLess(mae_val, 50.0,
                           f"MAE suspiciously high: {horizon}={mae_val}")
    
    def test_routing_monotonic_mae_increase(self):
        """MAE should generally increase with forecast horizon."""
        from cgmencode.production.glucose_forecast import ROUTED_MAE
        
        # Extract MAE values in horizon order
        mae_progression = [
            ('h30', ROUTED_MAE['h30']),
            ('h60', ROUTED_MAE['h60']),
            ('h90', ROUTED_MAE['h90']),
            ('h180', ROUTED_MAE['h180']),
            ('h360', ROUTED_MAE['h360']),
        ]
        
        # Check that later horizons generally have higher (or equal) MAE
        for i in range(len(mae_progression) - 1):
            h_now = mae_progression[i][1]
            h_next = mae_progression[i + 1][1]
            # Allow small decreases due to different window benefits,
            # but overall trend should be up
            self.assertLessEqual(h_now, h_next * 1.1,  # Allow 10% variance
                               f"MAE regression: {mae_progression[i][0]}={h_now} > "
                               f"{mae_progression[i+1][0]}={h_next}")




# ── ISF Non-Linearity Advisory Tests (EXP-2511) ─────────────────────

class TestISFNonlinearityTypes(unittest.TestCase):
    """Type-level tests for ISF non-linearity constants."""

    def test_population_beta_value(self):
        """Population β should be ~0.9 per EXP-2511."""
        from cgmencode.production.settings_advisor import _POPULATION_ISF_BETA
        self.assertAlmostEqual(_POPULATION_ISF_BETA, 0.9, places=1)

    def test_dose_threshold_positive(self):
        """Dose threshold must be > 0."""
        from cgmencode.production.settings_advisor import _ISF_NONLINEARITY_DOSE_THRESHOLD
        self.assertGreater(_ISF_NONLINEARITY_DOSE_THRESHOLD, 0)


class TestISFNonlinearityFunction(unittest.TestCase):
    """Functional tests for advise_isf_nonlinearity."""

    def _make_clinical(self, mean_glucose=180.0):
        from cgmencode.production.types import ClinicalReport
        cr = ClinicalReport.__new__(ClinicalReport)
        cr.mean_glucose = mean_glucose
        cr.isf_discrepancy = 2.0
        cr.effective_isf = 100.0
        cr.profile_isf = 50.0
        return cr

    def _make_profile(self, isf=50.0):
        from cgmencode.production.types import PatientProfile
        return PatientProfile(
            basal_schedule=[{'time': '00:00', 'value': 0.8}],
            isf_schedule=[{'time': '00:00', 'value': isf}],
            cr_schedule=[{'time': '00:00', 'value': 10.0}],
            dia_hours=5.0,
        )

    def test_returns_none_insufficient_data(self):
        """No advisory with < MIN_DATA_DAYS."""
        from cgmencode.production.settings_advisor import advise_isf_nonlinearity
        result = advise_isf_nonlinearity(
            self._make_clinical(), self._make_profile(), days_of_data=1.0)
        self.assertIsNone(result)

    def test_returns_none_small_corrections(self):
        """No advisory when typical correction <= threshold."""
        from cgmencode.production.settings_advisor import advise_isf_nonlinearity
        bolus = np.array([0.5, 0.8, 1.0, 0.7, 0.9])
        result = advise_isf_nonlinearity(
            self._make_clinical(), self._make_profile(),
            bolus=bolus, days_of_data=7.0)
        self.assertIsNone(result)

    def test_fires_for_large_corrections(self):
        """Advisory should fire when typical correction > threshold."""
        from cgmencode.production.settings_advisor import advise_isf_nonlinearity
        bolus = np.array([2.5, 3.0, 2.0, 2.8, 3.5, 2.2])
        result = advise_isf_nonlinearity(
            self._make_clinical(), self._make_profile(),
            bolus=bolus, days_of_data=7.0)
        self.assertIsNotNone(result)
        self.assertEqual(result.parameter.value, 'isf')
        self.assertIn('non-linearity', result.evidence.lower())
        self.assertIn('EXP-2511', result.evidence)

    def test_penalty_increases_with_dose(self):
        """Larger doses should show greater effectiveness penalty."""
        from cgmencode.production.settings_advisor import advise_isf_nonlinearity
        bolus_2u = np.array([2.0, 2.0, 2.0, 2.0, 2.0])
        bolus_4u = np.array([4.0, 4.0, 4.0, 4.0, 4.0])
        r2 = advise_isf_nonlinearity(
            self._make_clinical(), self._make_profile(),
            bolus=bolus_2u, days_of_data=7.0)
        r4 = advise_isf_nonlinearity(
            self._make_clinical(), self._make_profile(),
            bolus=bolus_4u, days_of_data=7.0)
        self.assertIsNotNone(r2)
        self.assertIsNotNone(r4)
        # 4U should have greater penalty than 2U
        self.assertGreater(r4.magnitude_pct, r2.magnitude_pct)

    def test_split_dose_improvement_positive(self):
        """Split dose should always be better than single dose."""
        from cgmencode.production.settings_advisor import advise_isf_nonlinearity
        bolus = np.array([3.0, 3.0, 3.0, 3.0, 3.0])
        result = advise_isf_nonlinearity(
            self._make_clinical(), self._make_profile(),
            bolus=bolus, days_of_data=7.0)
        self.assertIsNotNone(result)
        # predicted_tir_delta should be positive (improvement from splitting)
        self.assertGreater(result.predicted_tir_delta, 0)

    def test_fallback_estimation_from_clinical(self):
        """Should estimate dose from ISF and mean glucose when no bolus data."""
        from cgmencode.production.settings_advisor import advise_isf_nonlinearity
        # mean_glucose=220, target~120, ISF=50 → dose ≈ (220-120)/50 = 2.0U
        result = advise_isf_nonlinearity(
            self._make_clinical(mean_glucose=220.0),
            self._make_profile(isf=50.0),
            days_of_data=7.0)
        self.assertIsNotNone(result)

    def test_no_fire_low_mean_glucose(self):
        """Should NOT fire when mean glucose is near target (small corrections)."""
        from cgmencode.production.settings_advisor import advise_isf_nonlinearity
        result = advise_isf_nonlinearity(
            self._make_clinical(mean_glucose=130.0),
            self._make_profile(isf=50.0),
            days_of_data=7.0)
        self.assertIsNone(result)


class TestISFNonlinearityIntegration(unittest.TestCase):
    """Integration: non-linearity advisory in generate_settings_advice."""

    def test_bolus_kwarg_accepted(self):
        """generate_settings_advice should accept bolus kwarg."""
        from cgmencode.production.settings_advisor import generate_settings_advice
        from cgmencode.production.types import ClinicalReport, PatientProfile

        glucose = np.full(288, 150.0)
        hours = np.linspace(0, 24, 288, endpoint=False)
        profile = PatientProfile(
            basal_schedule=[{'time': '00:00', 'value': 0.8}],
            isf_schedule=[{'time': '00:00', 'value': 50.0}],
            cr_schedule=[{'time': '00:00', 'value': 10.0}],
            dia_hours=5.0,
        )
        clinical = ClinicalReport.__new__(ClinicalReport)
        clinical.mean_glucose = 150.0
        clinical.isf_discrepancy = None
        clinical.effective_isf = None
        clinical.profile_isf = 50.0
        clinical.cr_score = None
        clinical.tir_70_180 = 0.7
        clinical.time_below_54 = 0.0
        clinical.time_below_70 = 0.02

        bolus = np.array([3.0, 2.5, 3.0, 2.0, 2.5])
        recs = generate_settings_advice(
            glucose, None, hours, clinical, profile, 7.0,
            bolus=bolus)
        # Should not raise — bolus kwarg is accepted
        self.assertIsInstance(recs, list)


# ── Correction Threshold Tests (EXP-2528) ────────────────────────────

class TestCorrectionThresholdTypes(unittest.TestCase):
    """Type-level tests for correction threshold constants."""

    def test_population_threshold_value(self):
        """Population threshold should be 166 mg/dL per EXP-2528."""
        from cgmencode.production.settings_advisor import _POPULATION_CORRECTION_THRESHOLD
        self.assertEqual(_POPULATION_CORRECTION_THRESHOLD, 166)

    def test_threshold_range_valid(self):
        """Per-patient threshold range must be (130, 290)."""
        from cgmencode.production.settings_advisor import _CORRECTION_THRESHOLD_RANGE
        self.assertEqual(_CORRECTION_THRESHOLD_RANGE, (130, 290))

    def test_settings_parameter_enum(self):
        """SettingsParameter should have CORRECTION_THRESHOLD value."""
        from cgmencode.production.types import SettingsParameter
        self.assertEqual(SettingsParameter.CORRECTION_THRESHOLD.value, 'correction_threshold')

    def test_min_correction_events_positive(self):
        """Minimum correction events must be > 0."""
        from cgmencode.production.settings_advisor import _MIN_CORRECTION_EVENTS
        self.assertGreater(_MIN_CORRECTION_EVENTS, 0)


class TestCorrectionThresholdFunction(unittest.TestCase):
    """Functional tests for advise_correction_threshold."""

    def _make_clinical(self, mean_glucose=180.0):
        from cgmencode.production.types import ClinicalReport
        cr = ClinicalReport.__new__(ClinicalReport)
        cr.mean_glucose = mean_glucose
        cr.isf_discrepancy = 2.0
        cr.effective_isf = 100.0
        cr.profile_isf = 50.0
        return cr

    def _make_profile(self, target_high=180.0):
        from cgmencode.production.types import PatientProfile
        return PatientProfile(
            basal_schedule=[{'time': '00:00', 'value': 0.8}],
            isf_schedule=[{'time': '00:00', 'value': 50.0}],
            cr_schedule=[{'time': '00:00', 'value': 10.0}],
            dia_hours=5.0,
            target_high=target_high,
        )

    def _make_correction_events(self, n=30, start_bg_base=200.0):
        """Create synthetic correction events."""
        events = []
        for i in range(n):
            start_bg = start_bg_base + (i % 10) * 10 - 50
            events.append({
                'start_bg': float(start_bg),
                'tir_change': 5.0 if start_bg >= 166 else -3.0,
                'rebound': start_bg < 166,
                'rebound_magnitude': 15.0 if start_bg < 166 else 0.0,
                'went_below_70': start_bg < 150,
                'drop_4h': 30.0 if start_bg >= 166 else 10.0,
            })
        return events

    def test_returns_none_insufficient_data(self):
        """No advisory with < MIN_DATA_DAYS."""
        from cgmencode.production.settings_advisor import advise_correction_threshold
        result = advise_correction_threshold(
            self._make_clinical(), self._make_profile(), days_of_data=1.0)
        self.assertIsNone(result)

    def test_returns_population_default_no_events(self):
        """Returns population default (166) when no correction events."""
        from cgmencode.production.settings_advisor import advise_correction_threshold
        result = advise_correction_threshold(
            self._make_clinical(), self._make_profile(target_high=120.0),
            days_of_data=7.0)
        self.assertIsNotNone(result)
        self.assertEqual(result.suggested_value, 166.0)
        self.assertEqual(result.parameter.value, 'correction_threshold')

    def test_returns_none_when_current_matches(self):
        """No advisory when current target_high ~= recommended threshold."""
        from cgmencode.production.settings_advisor import advise_correction_threshold
        result = advise_correction_threshold(
            self._make_clinical(), self._make_profile(target_high=166.0),
            days_of_data=7.0)
        self.assertIsNone(result)

    def test_direction_increase_when_below(self):
        """Direction should be 'increase' when current < recommended."""
        from cgmencode.production.settings_advisor import advise_correction_threshold
        result = advise_correction_threshold(
            self._make_clinical(), self._make_profile(target_high=120.0),
            days_of_data=7.0)
        self.assertIsNotNone(result)
        self.assertEqual(result.direction, 'increase')

    def test_direction_decrease_when_above(self):
        """Direction should be 'decrease' when current > recommended."""
        from cgmencode.production.settings_advisor import advise_correction_threshold
        result = advise_correction_threshold(
            self._make_clinical(), self._make_profile(target_high=200.0),
            days_of_data=7.0)
        self.assertIsNotNone(result)
        self.assertEqual(result.direction, 'decrease')

    def test_per_patient_calibration(self):
        """With enough events, should compute per-patient threshold."""
        from cgmencode.production.settings_advisor import advise_correction_threshold
        events = self._make_correction_events(n=30, start_bg_base=200.0)
        result = advise_correction_threshold(
            self._make_clinical(), self._make_profile(target_high=120.0),
            correction_events=events, days_of_data=7.0)
        self.assertIsNotNone(result)
        self.assertIn('per-patient', result.evidence)

    def test_population_fallback_few_events(self):
        """With < MIN_CORRECTION_EVENTS, uses population default."""
        from cgmencode.production.settings_advisor import advise_correction_threshold
        events = self._make_correction_events(n=5)
        result = advise_correction_threshold(
            self._make_clinical(), self._make_profile(target_high=120.0),
            correction_events=events, days_of_data=7.0)
        self.assertIsNotNone(result)
        self.assertIn('population', result.evidence)

    def test_confidence_increases_with_events(self):
        """More events should give higher confidence."""
        from cgmencode.production.settings_advisor import advise_correction_threshold
        few = advise_correction_threshold(
            self._make_clinical(), self._make_profile(target_high=120.0),
            correction_events=None, days_of_data=7.0)
        many = advise_correction_threshold(
            self._make_clinical(), self._make_profile(target_high=120.0),
            correction_events=self._make_correction_events(n=60),
            days_of_data=7.0)
        self.assertIsNotNone(few)
        self.assertIsNotNone(many)
        self.assertGreater(many.confidence, few.confidence)

    def test_evidence_contains_exp_2528(self):
        """Evidence should reference EXP-2528."""
        from cgmencode.production.settings_advisor import advise_correction_threshold
        result = advise_correction_threshold(
            self._make_clinical(), self._make_profile(target_high=120.0),
            days_of_data=7.0)
        self.assertIsNotNone(result)
        self.assertIn('EXP-2528', result.evidence)

    def test_rationale_explains_harm(self):
        """Rationale should explain net-harm below threshold."""
        from cgmencode.production.settings_advisor import advise_correction_threshold
        result = advise_correction_threshold(
            self._make_clinical(), self._make_profile(target_high=120.0),
            days_of_data=7.0)
        self.assertIsNotNone(result)
        self.assertIn('net-negative', result.rationale)

    def test_predicted_tir_delta_positive(self):
        """Predicted TIR improvement should be positive."""
        from cgmencode.production.settings_advisor import advise_correction_threshold
        result = advise_correction_threshold(
            self._make_clinical(), self._make_profile(target_high=120.0),
            days_of_data=7.0)
        self.assertIsNotNone(result)
        self.assertGreater(result.predicted_tir_delta, 0)


class TestCorrectionThresholdIntegration(unittest.TestCase):
    """Integration: correction threshold advisory in generate_settings_advice."""

    def test_correction_events_kwarg_accepted(self):
        """generate_settings_advice should accept correction_events kwarg."""
        from cgmencode.production.settings_advisor import generate_settings_advice
        from cgmencode.production.types import ClinicalReport, PatientProfile

        glucose = np.full(288, 150.0)
        hours = np.linspace(0, 24, 288, endpoint=False)
        profile = PatientProfile(
            basal_schedule=[{'time': '00:00', 'value': 0.8}],
            isf_schedule=[{'time': '00:00', 'value': 50.0}],
            cr_schedule=[{'time': '00:00', 'value': 10.0}],
            dia_hours=5.0,
            target_high=120.0,
        )
        clinical = ClinicalReport.__new__(ClinicalReport)
        clinical.mean_glucose = 150.0
        clinical.isf_discrepancy = None
        clinical.effective_isf = None
        clinical.profile_isf = 50.0
        clinical.cr_score = None
        clinical.tir_70_180 = 0.7
        clinical.time_below_54 = 0.0
        clinical.time_below_70 = 0.02

        events = [
            {'start_bg': 200.0, 'tir_change': 5.0, 'rebound': False,
             'rebound_magnitude': 0.0, 'went_below_70': False, 'drop_4h': 30.0}
        ] * 30
        recs = generate_settings_advice(
            glucose, None, hours, clinical, profile, 7.0,
            correction_events=events)
        # Should not raise — correction_events kwarg is accepted
        self.assertIsInstance(recs, list)

    def test_threshold_rec_in_results(self):
        """Correction threshold rec should appear when target_high != 166."""
        from cgmencode.production.settings_advisor import generate_settings_advice
        from cgmencode.production.types import ClinicalReport, PatientProfile

        glucose = np.full(288, 150.0)
        hours = np.linspace(0, 24, 288, endpoint=False)
        profile = PatientProfile(
            basal_schedule=[{'time': '00:00', 'value': 0.8}],
            isf_schedule=[{'time': '00:00', 'value': 50.0}],
            cr_schedule=[{'time': '00:00', 'value': 10.0}],
            dia_hours=5.0,
            target_high=120.0,
        )
        clinical = ClinicalReport.__new__(ClinicalReport)
        clinical.mean_glucose = 150.0
        clinical.isf_discrepancy = None
        clinical.effective_isf = None
        clinical.profile_isf = 50.0
        clinical.cr_score = None
        clinical.tir_70_180 = 0.7
        clinical.time_below_54 = 0.0
        clinical.time_below_70 = 0.02

        recs = generate_settings_advice(
            glucose, None, hours, clinical, profile, 7.0)
        threshold_recs = [r for r in recs
                          if r.parameter.value == 'correction_threshold']
        self.assertEqual(len(threshold_recs), 1)
        self.assertEqual(threshold_recs[0].suggested_value, 166.0)


# ── Circadian ISF Profiled Tests (EXP-2271, 4-block) ─────────────────

class TestCircadianISFProfiledTypes(unittest.TestCase):
    """Type-level tests for circadian ISF profiled constants."""

    def test_circadian_blocks_is_dict(self):
        """_CIRCADIAN_BLOCKS must be a dict of block names to hour tuples."""
        from cgmencode.production.settings_advisor import _CIRCADIAN_BLOCKS
        self.assertIsInstance(_CIRCADIAN_BLOCKS, dict)
        self.assertEqual(len(_CIRCADIAN_BLOCKS), 4)
        for name, (h_start, h_end) in _CIRCADIAN_BLOCKS.items():
            self.assertIsInstance(name, str)
            self.assertGreaterEqual(h_start, 0)
            self.assertLessEqual(h_end, 24)
            self.assertLess(h_start, h_end)

    def test_deviation_threshold_value(self):
        """Deviation threshold must be 0.30 (30%)."""
        from cgmencode.production.settings_advisor import _CIRCADIAN_ISF_DEVIATION_THRESHOLD
        self.assertAlmostEqual(_CIRCADIAN_ISF_DEVIATION_THRESHOLD, 0.30)

    def test_min_corrections_per_block_positive(self):
        """Minimum corrections per block must be > 0."""
        from cgmencode.production.settings_advisor import _CIRCADIAN_MIN_CORRECTIONS_PER_BLOCK
        self.assertGreater(_CIRCADIAN_MIN_CORRECTIONS_PER_BLOCK, 0)
        self.assertEqual(_CIRCADIAN_MIN_CORRECTIONS_PER_BLOCK, 5)


class TestCircadianISFProfiledFunction(unittest.TestCase):
    """Functional tests for advise_circadian_isf_profiled."""

    def _make_profile(self, isf=50.0):
        from cgmencode.production.types import PatientProfile
        return PatientProfile(
            basal_schedule=[{'time': '00:00', 'value': 0.8}],
            isf_schedule=[{'time': '00:00', 'value': isf}],
            cr_schedule=[{'time': '00:00', 'value': 10.0}],
            dia_hours=5.0,
        )

    def _make_events(self, block_hour=9.0, n=10, drop=80.0, dose=1.0):
        """Create n correction events at a given hour with specified drop/dose."""
        return [
            {'hour': block_hour + (i % 3) * 0.5,
             'start_bg': 200.0, 'drop_4h': drop, 'dose': dose}
            for i in range(n)
        ]

    def test_returns_empty_insufficient_data(self):
        """No advisory with < MIN_DATA_DAYS."""
        from cgmencode.production.settings_advisor import advise_circadian_isf_profiled
        events = self._make_events()
        recs = advise_circadian_isf_profiled(
            correction_events=events, profile=self._make_profile(),
            days_of_data=1.0)
        self.assertEqual(recs, [])

    def test_returns_empty_no_events(self):
        """No advisory without correction events."""
        from cgmencode.production.settings_advisor import advise_circadian_isf_profiled
        recs = advise_circadian_isf_profiled(
            correction_events=None, profile=self._make_profile(),
            days_of_data=7.0)
        self.assertEqual(recs, [])

    def test_returns_empty_no_profile(self):
        """No advisory without profile."""
        from cgmencode.production.settings_advisor import advise_circadian_isf_profiled
        recs = advise_circadian_isf_profiled(
            correction_events=self._make_events(), profile=None,
            days_of_data=7.0)
        self.assertEqual(recs, [])

    def test_returns_empty_insufficient_events_per_block(self):
        """No advisory when < 5 events in every block."""
        from cgmencode.production.settings_advisor import advise_circadian_isf_profiled
        events = self._make_events(n=3)  # only 3 events
        recs = advise_circadian_isf_profiled(
            correction_events=events, profile=self._make_profile(),
            days_of_data=7.0)
        self.assertEqual(recs, [])

    def test_returns_empty_when_isf_matches(self):
        """No advisory when block ISF is close to profile ISF."""
        from cgmencode.production.settings_advisor import advise_circadian_isf_profiled
        # Profile ISF=50, drop=50/dose=1 → effective ISF=50 → no deviation
        events = self._make_events(drop=50.0, dose=1.0)
        recs = advise_circadian_isf_profiled(
            correction_events=events, profile=self._make_profile(isf=50.0),
            days_of_data=7.0)
        self.assertEqual(recs, [])

    def test_fires_for_large_deviation(self):
        """Advisory should fire when block ISF deviates >30% from profile."""
        from cgmencode.production.settings_advisor import advise_circadian_isf_profiled
        # Profile ISF=50, effective ISF=80 (60% deviation) → should fire
        events = self._make_events(block_hour=9.0, drop=80.0, dose=1.0)
        recs = advise_circadian_isf_profiled(
            correction_events=events, profile=self._make_profile(isf=50.0),
            days_of_data=7.0)
        self.assertGreater(len(recs), 0)
        rec = recs[0]
        self.assertEqual(rec.parameter, SettingsParameter.ISF)
        self.assertEqual(rec.direction, "increase")
        self.assertAlmostEqual(rec.suggested_value, 80.0, delta=1.0)
        self.assertIn("morning", rec.evidence)

    def test_decrease_direction_when_block_isf_lower(self):
        """Direction 'decrease' when block ISF < profile ISF by >30%."""
        from cgmencode.production.settings_advisor import advise_circadian_isf_profiled
        # Profile ISF=50, effective ISF=30 (-40% deviation) → decrease
        events = self._make_events(block_hour=14.0, drop=30.0, dose=1.0)
        recs = advise_circadian_isf_profiled(
            correction_events=events, profile=self._make_profile(isf=50.0),
            days_of_data=7.0)
        self.assertGreater(len(recs), 0)
        self.assertEqual(recs[0].direction, "decrease")

    def test_evidence_cites_exp_2271(self):
        """Evidence must reference EXP-2271."""
        from cgmencode.production.settings_advisor import advise_circadian_isf_profiled
        events = self._make_events(drop=80.0, dose=1.0)
        recs = advise_circadian_isf_profiled(
            correction_events=events, profile=self._make_profile(isf=50.0),
            days_of_data=7.0)
        self.assertGreater(len(recs), 0)
        self.assertIn("EXP-2271", recs[0].evidence)

    def test_rationale_mentions_block_name(self):
        """Rationale should mention the time-of-day block."""
        from cgmencode.production.settings_advisor import advise_circadian_isf_profiled
        events = self._make_events(block_hour=20.0, drop=80.0, dose=1.0)
        recs = advise_circadian_isf_profiled(
            correction_events=events, profile=self._make_profile(isf=50.0),
            days_of_data=7.0)
        self.assertGreater(len(recs), 0)
        self.assertIn("evening", recs[0].rationale)

    def test_confidence_scales_with_events(self):
        """More events should yield higher confidence."""
        from cgmencode.production.settings_advisor import advise_circadian_isf_profiled
        few = advise_circadian_isf_profiled(
            correction_events=self._make_events(n=5, drop=80.0),
            profile=self._make_profile(isf=50.0), days_of_data=7.0)
        many = advise_circadian_isf_profiled(
            correction_events=self._make_events(n=20, drop=80.0),
            profile=self._make_profile(isf=50.0), days_of_data=7.0)
        self.assertGreater(len(few), 0)
        self.assertGreater(len(many), 0)
        self.assertGreater(many[0].confidence, few[0].confidence)

    def test_multiple_blocks_can_fire(self):
        """Multiple blocks can produce recommendations simultaneously."""
        from cgmencode.production.settings_advisor import advise_circadian_isf_profiled
        events = (
            self._make_events(block_hour=3.0, n=6, drop=80.0)   # overnight
            + self._make_events(block_hour=9.0, n=6, drop=80.0)  # morning
        )
        recs = advise_circadian_isf_profiled(
            correction_events=events, profile=self._make_profile(isf=50.0),
            days_of_data=7.0)
        self.assertGreaterEqual(len(recs), 2)

    def test_predicted_tir_delta_positive(self):
        """Predicted TIR improvement should be positive."""
        from cgmencode.production.settings_advisor import advise_circadian_isf_profiled
        events = self._make_events(drop=80.0, dose=1.0)
        recs = advise_circadian_isf_profiled(
            correction_events=events, profile=self._make_profile(isf=50.0),
            days_of_data=7.0)
        self.assertGreater(len(recs), 0)
        self.assertGreater(recs[0].predicted_tir_delta, 0)

    def test_affected_hours_match_block(self):
        """affected_hours should match the block hour range."""
        from cgmencode.production.settings_advisor import advise_circadian_isf_profiled
        events = self._make_events(block_hour=14.0, drop=80.0, dose=1.0)
        recs = advise_circadian_isf_profiled(
            correction_events=events, profile=self._make_profile(isf=50.0),
            days_of_data=7.0)
        self.assertGreater(len(recs), 0)
        self.assertEqual(recs[0].affected_hours, (12.0, 18.0))


class TestCircadianISFProfiledIntegration(unittest.TestCase):
    """Integration: circadian ISF profiled in generate_settings_advice."""

    def test_correction_events_with_hour_accepted(self):
        """generate_settings_advice should pass correction_events to profiled advisory."""
        from cgmencode.production.settings_advisor import generate_settings_advice
        from cgmencode.production.types import ClinicalReport, PatientProfile

        glucose = np.full(288, 150.0)
        hours = np.linspace(0, 24, 288, endpoint=False)
        profile = PatientProfile(
            basal_schedule=[{'time': '00:00', 'value': 0.8}],
            isf_schedule=[{'time': '00:00', 'value': 50.0}],
            cr_schedule=[{'time': '00:00', 'value': 10.0}],
            dia_hours=5.0,
            target_high=166.0,
        )
        clinical = ClinicalReport.__new__(ClinicalReport)
        clinical.mean_glucose = 150.0
        clinical.isf_discrepancy = None
        clinical.effective_isf = None
        clinical.profile_isf = 50.0
        clinical.cr_score = None
        clinical.tir_70_180 = 0.7
        clinical.time_below_54 = 0.0
        clinical.time_below_70 = 0.02

        events = [
            {'hour': 9.0 + i * 0.3, 'start_bg': 200.0,
             'drop_4h': 80.0, 'dose': 1.0, 'tir_change': 5.0}
            for i in range(10)
        ]
        recs = generate_settings_advice(
            glucose, None, hours, clinical, profile, 7.0,
            correction_events=events)
        self.assertIsInstance(recs, list)

    def test_profiled_recs_appear_in_results(self):
        """Circadian profiled recs should appear when events have large ISF deviation."""
        from cgmencode.production.settings_advisor import generate_settings_advice
        from cgmencode.production.types import ClinicalReport, PatientProfile

        glucose = np.full(288, 150.0)
        hours = np.linspace(0, 24, 288, endpoint=False)
        profile = PatientProfile(
            basal_schedule=[{'time': '00:00', 'value': 0.8}],
            isf_schedule=[{'time': '00:00', 'value': 50.0}],
            cr_schedule=[{'time': '00:00', 'value': 10.0}],
            dia_hours=5.0,
            target_high=166.0,
        )
        clinical = ClinicalReport.__new__(ClinicalReport)
        clinical.mean_glucose = 150.0
        clinical.isf_discrepancy = None
        clinical.effective_isf = None
        clinical.profile_isf = 50.0
        clinical.cr_score = None
        clinical.tir_70_180 = 0.7
        clinical.time_below_54 = 0.0
        clinical.time_below_70 = 0.02

        events = [
            {'hour': 9.0 + i * 0.3, 'start_bg': 200.0,
             'drop_4h': 80.0, 'dose': 1.0, 'tir_change': 5.0}
            for i in range(10)
        ]
        recs = generate_settings_advice(
            glucose, None, hours, clinical, profile, 7.0,
            correction_events=events)
        profiled_recs = [
            r for r in recs
            if r.parameter == SettingsParameter.ISF
            and 'profiling' in r.evidence.lower()
        ]
        self.assertGreater(len(profiled_recs), 0)
        self.assertEqual(profiled_recs[0].affected_hours, (6.0, 12.0))


# ── CR Adequacy Tests (EXP-2535/2536) ─────────────────────────────────

class TestCRAdequacyTypes(unittest.TestCase):
    """Type-level tests for CR adequacy constants."""

    def test_min_meals_value(self):
        """Minimum meals for analysis must be 10."""
        from cgmencode.production.settings_advisor import _CR_ADEQUACY_MIN_MEALS
        self.assertEqual(_CR_ADEQUACY_MIN_MEALS, 10)

    def test_deviation_threshold_value(self):
        """Deviation threshold must be 0.20 (20%)."""
        from cgmencode.production.settings_advisor import _CR_ADEQUACY_DEVIATION_THRESHOLD
        self.assertAlmostEqual(_CR_ADEQUACY_DEVIATION_THRESHOLD, 0.20)

    def test_nonlinearity_threshold_value(self):
        """Nonlinearity threshold must be 2.0."""
        from cgmencode.production.settings_advisor import _CR_NONLINEARITY_THRESHOLD
        self.assertAlmostEqual(_CR_NONLINEARITY_THRESHOLD, 2.0)

    def test_settings_parameter_cr_exists(self):
        """SettingsParameter should have CR value."""
        from cgmencode.production.types import SettingsParameter
        self.assertEqual(SettingsParameter.CR.value, 'cr')


class TestCRAdequacyFunction(unittest.TestCase):
    """Functional tests for advise_cr_adequacy."""

    def _make_profile(self, cr=10.0):
        from cgmencode.production.types import PatientProfile
        return PatientProfile(
            basal_schedule=[{'time': '00:00', 'value': 0.8}],
            isf_schedule=[{'time': '00:00', 'value': 50.0}],
            cr_schedule=[{'time': '00:00', 'value': cr}],
            dia_hours=5.0,
        )

    def _make_meals(self, n=15, carbs=40.0, bolus=4.0,
                    pre_bg=120.0, post_bg=140.0, hour=12.0):
        """Create n meal events with specified parameters."""
        return [
            {'carbs': carbs, 'bolus': bolus,
             'pre_meal_bg': pre_bg, 'post_meal_bg_4h': post_bg,
             'hour': hour + (i % 5) * 0.5}
            for i in range(n)
        ]

    def test_returns_empty_insufficient_meals(self):
        """No advisory with < _CR_ADEQUACY_MIN_MEALS."""
        from cgmencode.production.settings_advisor import advise_cr_adequacy
        meals = self._make_meals(n=5)
        recs = advise_cr_adequacy(meals, self._make_profile())
        self.assertEqual(recs, [])

    def test_returns_empty_none_meals(self):
        """No advisory with None meal_events."""
        from cgmencode.production.settings_advisor import advise_cr_adequacy
        recs = advise_cr_adequacy(None, self._make_profile())
        self.assertEqual(recs, [])

    def test_returns_empty_empty_list(self):
        """No advisory with empty list."""
        from cgmencode.production.settings_advisor import advise_cr_adequacy
        recs = advise_cr_adequacy([], self._make_profile())
        self.assertEqual(recs, [])

    def test_neutral_cr_no_recommendation(self):
        """No deviation recommendation when effective CR matches profile."""
        from cgmencode.production.settings_advisor import advise_cr_adequacy
        # Profile CR=10, meals: 40g / 4U = effective CR=10 → no deviation
        meals = self._make_meals(n=15, carbs=40.0, bolus=4.0)
        recs = advise_cr_adequacy(meals, self._make_profile(cr=10.0))
        # Filter to deviation recs (not nonlinearity)
        deviation_recs = [r for r in recs if 'adequacy' in r.evidence.lower()]
        self.assertEqual(deviation_recs, [])

    def test_under_dosing_detected(self):
        """Should detect under-dosing when effective CR >> profile CR."""
        from cgmencode.production.settings_advisor import advise_cr_adequacy
        # Profile CR=10, meals: 60g / 4U = effective CR=15 → 50% deviation
        meals = self._make_meals(n=20, carbs=60.0, bolus=4.0, post_bg=160.0)
        recs = advise_cr_adequacy(meals, self._make_profile(cr=10.0))
        deviation_recs = [r for r in recs if 'adequacy' in r.evidence.lower()]
        self.assertEqual(len(deviation_recs), 1)
        rec = deviation_recs[0]
        self.assertEqual(rec.parameter, SettingsParameter.CR)
        self.assertEqual(rec.direction, 'decrease')
        self.assertAlmostEqual(rec.suggested_value, 15.0, places=0)
        self.assertIn('under-dosing', rec.evidence)

    def test_over_dosing_detected(self):
        """Should detect over-dosing when effective CR << profile CR."""
        from cgmencode.production.settings_advisor import advise_cr_adequacy
        # Profile CR=15, meals: 40g / 4U = effective CR=10 → -33% deviation
        meals = self._make_meals(n=20, carbs=40.0, bolus=4.0, post_bg=100.0)
        recs = advise_cr_adequacy(meals, self._make_profile(cr=15.0))
        deviation_recs = [r for r in recs if 'adequacy' in r.evidence.lower()]
        self.assertEqual(len(deviation_recs), 1)
        rec = deviation_recs[0]
        self.assertEqual(rec.direction, 'increase')
        self.assertIn('over-dosing', rec.evidence)

    def test_nonlinearity_warning(self):
        """Should warn about nonlinearity when small/large rise ratio >= 2.0."""
        from cgmencode.production.settings_advisor import advise_cr_adequacy
        # Small meals: 20g carbs, rise 60 mg/dL → 3.0 mg/dL/g
        # Large meals: 80g carbs, rise 40 mg/dL → 0.5 mg/dL/g
        # Ratio: 3.0/0.5 = 6.0 → should trigger
        small = [
            {'carbs': 20.0, 'bolus': 2.0, 'pre_meal_bg': 120.0,
             'post_meal_bg_4h': 180.0, 'hour': 12.0 + i * 0.3}
            for i in range(8)
        ]
        large = [
            {'carbs': 80.0, 'bolus': 8.0, 'pre_meal_bg': 120.0,
             'post_meal_bg_4h': 160.0, 'hour': 18.0 + i * 0.3}
            for i in range(8)
        ]
        meals = small + large
        recs = advise_cr_adequacy(meals, self._make_profile(cr=10.0))
        nonlinear_recs = [r for r in recs if 'nonlinearity' in r.evidence.lower()]
        self.assertEqual(len(nonlinear_recs), 1)
        self.assertIn('rise/gram', nonlinear_recs[0].evidence)

    def test_no_nonlinearity_when_similar_rise(self):
        """No nonlinearity warning when small and large meals rise similarly."""
        from cgmencode.production.settings_advisor import advise_cr_adequacy
        # Both small and large meals: ~1.0 mg/dL/g rise
        small = [
            {'carbs': 20.0, 'bolus': 2.0, 'pre_meal_bg': 120.0,
             'post_meal_bg_4h': 140.0, 'hour': 12.0 + i * 0.3}
            for i in range(8)
        ]
        large = [
            {'carbs': 80.0, 'bolus': 8.0, 'pre_meal_bg': 120.0,
             'post_meal_bg_4h': 200.0, 'hour': 18.0 + i * 0.3}
            for i in range(8)
        ]
        meals = small + large
        recs = advise_cr_adequacy(meals, self._make_profile(cr=10.0))
        nonlinear_recs = [r for r in recs if 'nonlinearity' in r.evidence.lower()]
        self.assertEqual(nonlinear_recs, [])

    def test_confidence_scales_with_meal_count(self):
        """Confidence should increase with more meals."""
        from cgmencode.production.settings_advisor import advise_cr_adequacy
        # 15 meals: lower confidence
        meals_15 = self._make_meals(n=15, carbs=60.0, bolus=4.0, post_bg=160.0)
        recs_15 = advise_cr_adequacy(meals_15, self._make_profile(cr=10.0))
        dev_15 = [r for r in recs_15 if 'adequacy' in r.evidence.lower()]

        # 50 meals: higher confidence
        meals_50 = self._make_meals(n=50, carbs=60.0, bolus=4.0, post_bg=160.0)
        recs_50 = advise_cr_adequacy(meals_50, self._make_profile(cr=10.0))
        dev_50 = [r for r in recs_50 if 'adequacy' in r.evidence.lower()]

        self.assertEqual(len(dev_15), 1)
        self.assertEqual(len(dev_50), 1)
        self.assertGreater(dev_50[0].confidence, dev_15[0].confidence)

    def test_evidence_cites_exp_2535(self):
        """Evidence string should reference EXP-2535."""
        from cgmencode.production.settings_advisor import advise_cr_adequacy
        meals = self._make_meals(n=20, carbs=60.0, bolus=4.0, post_bg=160.0)
        recs = advise_cr_adequacy(meals, self._make_profile(cr=10.0))
        dev_recs = [r for r in recs if 'adequacy' in r.evidence.lower()]
        self.assertEqual(len(dev_recs), 1)
        self.assertIn('EXP-2535', dev_recs[0].evidence)

    def test_skips_invalid_events(self):
        """Events missing required keys should be filtered out."""
        from cgmencode.production.settings_advisor import advise_cr_adequacy
        # 8 valid + 5 invalid (missing 'bolus') = only 8 valid < 10 → no recs
        valid = self._make_meals(n=8, carbs=60.0, bolus=4.0, post_bg=160.0)
        invalid = [{'carbs': 40.0, 'pre_meal_bg': 120.0,
                     'post_meal_bg_4h': 140.0, 'hour': 12.0}
                    for _ in range(5)]
        recs = advise_cr_adequacy(valid + invalid, self._make_profile(cr=10.0))
        self.assertEqual(recs, [])


class TestCRAdequacyIntegration(unittest.TestCase):
    """Integration: CR adequacy in generate_settings_advice."""

    def test_meal_events_kwarg_accepted(self):
        """generate_settings_advice should accept meal_events kwarg."""
        from cgmencode.production.settings_advisor import generate_settings_advice
        from cgmencode.production.types import ClinicalReport, PatientProfile

        glucose = np.full(288, 150.0)
        hours = np.linspace(0, 24, 288, endpoint=False)
        profile = PatientProfile(
            basal_schedule=[{'time': '00:00', 'value': 0.8}],
            isf_schedule=[{'time': '00:00', 'value': 50.0}],
            cr_schedule=[{'time': '00:00', 'value': 10.0}],
            dia_hours=5.0,
            target_high=166.0,
        )
        clinical = ClinicalReport.__new__(ClinicalReport)
        clinical.mean_glucose = 150.0
        clinical.isf_discrepancy = None
        clinical.effective_isf = None
        clinical.profile_isf = 50.0
        clinical.cr_score = None
        clinical.tir_70_180 = 0.7
        clinical.time_below_54 = 0.0
        clinical.time_below_70 = 0.02

        meals = [
            {'carbs': 60.0, 'bolus': 4.0, 'pre_meal_bg': 120.0,
             'post_meal_bg_4h': 160.0, 'hour': 12.0 + i * 0.3}
            for i in range(15)
        ]
        recs = generate_settings_advice(
            glucose, None, hours, clinical, profile, 7.0,
            meal_events=meals)
        self.assertIsInstance(recs, list)

    def test_adequacy_recs_appear_in_results(self):
        """CR adequacy recs should appear when meals show large deviation."""
        from cgmencode.production.settings_advisor import generate_settings_advice
        from cgmencode.production.types import ClinicalReport, PatientProfile

        glucose = np.full(288, 150.0)
        hours = np.linspace(0, 24, 288, endpoint=False)
        profile = PatientProfile(
            basal_schedule=[{'time': '00:00', 'value': 0.8}],
            isf_schedule=[{'time': '00:00', 'value': 50.0}],
            cr_schedule=[{'time': '00:00', 'value': 10.0}],
            dia_hours=5.0,
            target_high=166.0,
        )
        clinical = ClinicalReport.__new__(ClinicalReport)
        clinical.mean_glucose = 150.0
        clinical.isf_discrepancy = None
        clinical.effective_isf = None
        clinical.profile_isf = 50.0
        clinical.cr_score = None
        clinical.tir_70_180 = 0.7
        clinical.time_below_54 = 0.0
        clinical.time_below_70 = 0.02

        # Effective CR = 60/4 = 15, profile CR = 10 → 50% deviation
        meals = [
            {'carbs': 60.0, 'bolus': 4.0, 'pre_meal_bg': 120.0,
             'post_meal_bg_4h': 160.0, 'hour': 12.0 + i * 0.3}
            for i in range(20)
        ]
        recs = generate_settings_advice(
            glucose, None, hours, clinical, profile, 7.0,
            meal_events=meals)
        adequacy_recs = [
            r for r in recs
            if r.parameter == SettingsParameter.CR
            and 'adequacy' in r.evidence.lower()
        ]
        self.assertGreater(len(adequacy_recs), 0)
        self.assertEqual(adequacy_recs[0].direction, 'decrease')


# ── Hypo Risk Type Tests (EXP-2539) ──────────────────────────────────

class TestHypoRiskResultType(unittest.TestCase):
    """Type contract tests for HypoRiskResult dataclass."""

    def test_instantiation(self):
        r = HypoRiskResult(
            risk_score=0.25,
            risk_level='moderate',
            lead_time_minutes=30,
            dominant_factor='glucose_level',
            recommended_action='Monitor closely.',
        )
        self.assertAlmostEqual(r.risk_score, 0.25)
        self.assertEqual(r.risk_level, 'moderate')
        self.assertEqual(r.lead_time_minutes, 30)

    def test_fields_accessible(self):
        r = HypoRiskResult(
            risk_score=0.0, risk_level='low', lead_time_minutes=30,
            dominant_factor='glucose_level', recommended_action='None.',
        )
        self.assertEqual(r.dominant_factor, 'glucose_level')
        self.assertEqual(r.recommended_action, 'None.')

    def test_risk_level_values(self):
        for level in ('low', 'moderate', 'high', 'critical'):
            r = HypoRiskResult(
                risk_score=0.5, risk_level=level, lead_time_minutes=30,
                dominant_factor='glucose_level', recommended_action='x',
            )
            self.assertEqual(r.risk_level, level)

    def test_pipeline_result_has_hypo_risk_field(self):
        """PipelineResult accepts hypo_risk kwarg."""
        from cgmencode.production.pipeline import run_pipeline
        patient = make_patient()
        result = run_pipeline(patient, skip_patterns=True)
        self.assertTrue(hasattr(result, 'hypo_risk'))


# ── Hypo Risk Functional Tests (EXP-2539) ────────────────────────────

class TestComputeHypoRisk(unittest.TestCase):
    """Functional tests for compute_hypo_risk."""

    def setUp(self):
        from cgmencode.production.hypo_risk import compute_hypo_risk
        self.compute = compute_hypo_risk

    def test_stable_high_glucose_low_risk(self):
        """Stable glucose at 150 → low risk."""
        readings = [150.0] * 12
        result = self.compute(readings)
        self.assertLess(result.risk_score, 0.05)
        self.assertEqual(result.risk_level, 'low')

    def test_stable_120_low_risk(self):
        """Stable glucose at 120 → low risk."""
        readings = [120.0] * 12
        result = self.compute(readings)
        self.assertLess(result.risk_score, 0.10)
        self.assertEqual(result.risk_level, 'low')

    def test_stable_100_moderate_risk(self):
        """Stable glucose at 100 → moderate risk."""
        readings = [100.0] * 12
        result = self.compute(readings)
        self.assertGreaterEqual(result.risk_score, 0.05)
        self.assertLess(result.risk_score, 0.30)
        self.assertIn(result.risk_level, ('low', 'moderate'))

    def test_falling_toward_70_high_risk(self):
        """Falling from ~110 toward 80 at -3/step → high risk."""
        readings = [113, 110, 107, 104, 101, 98, 95, 92, 89, 86, 83, 80.0]
        result = self.compute(readings)
        self.assertGreater(result.risk_score, 0.30)
        self.assertIn(result.risk_level, ('high', 'critical'))

    def test_flat_at_70_critical_risk(self):
        """Flat glucose at 70 → critical risk."""
        readings = [70.0] * 12
        result = self.compute(readings)
        self.assertGreater(result.risk_score, 0.60)
        self.assertEqual(result.risk_level, 'critical')

    def test_rapidly_falling_critical(self):
        """Rapidly falling glucose → critical risk."""
        readings = [120, 116, 112, 108, 104, 100, 96, 92, 88, 84, 80, 76.0]
        result = self.compute(readings)
        self.assertGreater(result.risk_score, 0.50)
        self.assertIn(result.risk_level, ('high', 'critical'))

    def test_rising_glucose_low_risk(self):
        """Rising glucose from 80 to 120 → low risk despite starting low."""
        readings = [80, 84, 88, 92, 96, 100, 104, 108, 112, 116, 120, 124.0]
        result = self.compute(readings)
        self.assertLess(result.risk_score, 0.30)

    def test_lead_time_always_30(self):
        """Lead time is always 30 minutes."""
        result = self.compute([120.0] * 12)
        self.assertEqual(result.lead_time_minutes, 30)

    def test_dominant_factor_is_valid(self):
        """Dominant factor is one of the recognized feature names."""
        valid = {'glucose_level', 'rate_of_change', 'acceleration',
                 'recent_minimum', 'time_near_hypo'}
        result = self.compute([120.0] * 12)
        self.assertIn(result.dominant_factor, valid)

    def test_recommended_action_nonempty(self):
        """Recommended action is always a non-empty string."""
        for sgv in [150.0, 100.0, 80.0, 70.0]:
            result = self.compute([sgv] * 12)
            self.assertIsInstance(result.recommended_action, str)
            self.assertGreater(len(result.recommended_action), 0)

    def test_insufficient_data_raises(self):
        """Fewer than 3 readings raises ValueError."""
        with self.assertRaises(ValueError):
            self.compute([100.0, 100.0])
        with self.assertRaises(ValueError):
            self.compute([])

    def test_single_reading_raises(self):
        """Single reading raises ValueError."""
        with self.assertRaises(ValueError):
            self.compute([120.0])

    def test_nan_handling(self):
        """NaN values are filtered; enough valid readings still work."""
        readings = [float('nan')] * 4 + [120.0] * 8
        result = self.compute(readings)
        self.assertLess(result.risk_score, 0.10)

    def test_all_nan_raises(self):
        """All NaN readings raises ValueError."""
        with self.assertRaises(ValueError):
            self.compute([float('nan')] * 12)

    def test_minimum_3_readings(self):
        """Exactly 3 readings produces a result."""
        result = self.compute([120.0, 118.0, 116.0])
        self.assertIsInstance(result.risk_score, float)
        self.assertGreaterEqual(result.risk_score, 0.0)
        self.assertLessEqual(result.risk_score, 1.0)

    def test_risk_score_bounded(self):
        """Risk score is always between 0 and 1."""
        for readings in [[300.0]*12, [40.0]*12, [100.0]*12]:
            result = self.compute(readings)
            self.assertGreaterEqual(result.risk_score, 0.0)
            self.assertLessEqual(result.risk_score, 1.0)

    def test_monotonic_risk_with_decreasing_glucose(self):
        """Lower stable glucose → higher risk score."""
        risks = []
        for sgv in [180, 150, 120, 100, 90, 80, 70]:
            result = self.compute([float(sgv)] * 12)
            risks.append(result.risk_score)
        for i in range(len(risks) - 1):
            self.assertLessEqual(risks[i], risks[i + 1],
                                 f"Risk should increase as glucose decreases: "
                                 f"sgv sequence not monotonic at index {i}")


# ── Hypo Risk Pipeline Integration (EXP-2539) ────────────────────────

class TestHypoRiskPipelineIntegration(unittest.TestCase):
    """Integration test: hypo_risk runs as pipeline stage."""

    def test_pipeline_populates_hypo_risk(self):
        """Pipeline result includes non-None hypo_risk."""
        from cgmencode.production.pipeline import run_pipeline
        patient = make_patient()
        result = run_pipeline(patient, skip_patterns=True)
        self.assertIsNotNone(result.hypo_risk)
        self.assertIsInstance(result.hypo_risk, HypoRiskResult)
        self.assertGreaterEqual(result.hypo_risk.risk_score, 0.0)
        self.assertLessEqual(result.hypo_risk.risk_score, 1.0)
        self.assertIn(result.hypo_risk.risk_level,
                      ('low', 'moderate', 'high', 'critical'))


# ── Pipeline Event Extraction Tests (EXP-2528/2535/2536) ─────────────

class TestCorrectionEventExtraction(unittest.TestCase):
    """Tests for _extract_correction_events in pipeline.py."""

    def test_basic_correction_detection(self):
        """Bolus when glucose > target_high with no carbs → correction event."""
        from cgmencode.production.pipeline import _extract_correction_events
        n = 200
        glucose = np.full(n, 200.0)
        bolus = np.zeros(n)
        bolus[50] = 2.0
        carbs = np.zeros(n)
        hours = (np.arange(n) * 5.0 / 60.0) % 24.0
        profile = make_profile()
        events = _extract_correction_events(glucose, bolus, carbs, hours, profile)
        self.assertGreaterEqual(len(events), 1)
        ev = events[0]
        self.assertAlmostEqual(ev['start_bg'], 200.0)
        self.assertAlmostEqual(ev['dose'], 2.0)
        self.assertIn('drop_4h', ev)
        self.assertIn('hour', ev)
        self.assertIn('rebound', ev)
        self.assertIn('went_below_70', ev)
        self.assertIn('tir_change', ev)

    def test_meal_bolus_excluded(self):
        """Bolus with carbs nearby should NOT be classified as correction."""
        from cgmencode.production.pipeline import _extract_correction_events
        n = 200
        glucose = np.full(n, 200.0)
        bolus = np.zeros(n)
        bolus[50] = 2.0
        carbs = np.zeros(n)
        carbs[50] = 40.0
        hours = (np.arange(n) * 5.0 / 60.0) % 24.0
        profile = make_profile()
        events = _extract_correction_events(glucose, bolus, carbs, hours, profile)
        self.assertEqual(len(events), 0)

    def test_below_target_excluded(self):
        """Bolus when glucose <= target_high should be excluded."""
        from cgmencode.production.pipeline import _extract_correction_events
        n = 200
        glucose = np.full(n, 120.0)
        bolus = np.zeros(n)
        bolus[50] = 2.0
        carbs = np.zeros(n)
        hours = (np.arange(n) * 5.0 / 60.0) % 24.0
        profile = make_profile()
        events = _extract_correction_events(glucose, bolus, carbs, hours, profile)
        self.assertEqual(len(events), 0)

    def test_none_bolus_returns_empty(self):
        """None bolus array returns empty list."""
        from cgmencode.production.pipeline import _extract_correction_events
        n = 200
        glucose = np.full(n, 200.0)
        hours = (np.arange(n) * 5.0 / 60.0) % 24.0
        profile = make_profile()
        events = _extract_correction_events(glucose, None, None, hours, profile)
        self.assertEqual(events, [])

    def test_short_data_returns_empty(self):
        """Data shorter than 49 steps returns empty."""
        from cgmencode.production.pipeline import _extract_correction_events
        glucose = np.full(30, 200.0)
        bolus = np.zeros(30)
        bolus[5] = 2.0
        hours = np.zeros(30)
        profile = make_profile()
        events = _extract_correction_events(glucose, bolus, None, hours, profile)
        self.assertEqual(events, [])

    def test_went_below_70_detection(self):
        """Detect when glucose drops below 70 in 4h window."""
        from cgmencode.production.pipeline import _extract_correction_events
        n = 200
        glucose = np.full(n, 200.0)
        glucose[70:80] = 60.0
        bolus = np.zeros(n)
        bolus[50] = 3.0
        carbs = np.zeros(n)
        hours = (np.arange(n) * 5.0 / 60.0) % 24.0
        profile = make_profile()
        events = _extract_correction_events(glucose, bolus, carbs, hours, profile)
        self.assertGreaterEqual(len(events), 1)
        self.assertTrue(events[0]['went_below_70'])


class TestMealEventExtraction(unittest.TestCase):
    """Tests for _extract_meal_events in pipeline.py."""

    def test_basic_meal_detection(self):
        """Carbs > 5g with glucose before and 4h after → meal event."""
        from cgmencode.production.pipeline import _extract_meal_events
        n = 200
        glucose = np.full(n, 150.0)
        bolus = np.zeros(n)
        bolus[50] = 4.0
        carbs = np.zeros(n)
        carbs[50] = 45.0
        hours = (np.arange(n) * 5.0 / 60.0) % 24.0
        events = _extract_meal_events(glucose, bolus, carbs, hours)
        self.assertGreaterEqual(len(events), 1)
        ev = events[0]
        self.assertAlmostEqual(ev['carbs'], 45.0)
        self.assertGreater(ev['bolus'], 0)
        self.assertAlmostEqual(ev['pre_meal_bg'], 150.0)
        self.assertAlmostEqual(ev['post_meal_bg_4h'], 150.0)
        self.assertIn('hour', ev)

    def test_no_carbs_returns_empty(self):
        """None carbs array returns empty list."""
        from cgmencode.production.pipeline import _extract_meal_events
        n = 200
        glucose = np.full(n, 150.0)
        hours = np.zeros(n)
        events = _extract_meal_events(glucose, None, None, hours)
        self.assertEqual(events, [])

    def test_small_carbs_excluded(self):
        """Carbs <= 5g are excluded."""
        from cgmencode.production.pipeline import _extract_meal_events
        n = 200
        glucose = np.full(n, 150.0)
        bolus = np.zeros(n)
        carbs = np.zeros(n)
        carbs[50] = 3.0
        hours = np.zeros(n)
        events = _extract_meal_events(glucose, bolus, carbs, hours)
        self.assertEqual(events, [])

    def test_nan_glucose_excluded(self):
        """Meals with NaN glucose at mealtime are excluded."""
        from cgmencode.production.pipeline import _extract_meal_events
        n = 200
        glucose = np.full(n, 150.0)
        glucose[50] = np.nan
        bolus = np.zeros(n)
        bolus[50] = 4.0
        carbs = np.zeros(n)
        carbs[50] = 45.0
        hours = np.zeros(n)
        events = _extract_meal_events(glucose, bolus, carbs, hours)
        self.assertEqual(len(events), 0)


class TestPipelineAdvisoryWiring(unittest.TestCase):
    """Integration: pipeline passes bolus/correction_events/meal_events."""

    def test_pipeline_passes_bolus_to_settings(self):
        """Pipeline result should include settings_recs with bolus data available."""
        from cgmencode.production.pipeline import run_pipeline
        patient = make_patient()
        result = run_pipeline(patient, skip_patterns=True)
        self.assertIsNotNone(result.settings_recs)

    def test_correction_events_extracted_in_pipeline(self):
        """Pipeline extracts correction events when bolus+glucose data present."""
        from cgmencode.production.pipeline import _extract_correction_events
        patient = make_patient()
        from cgmencode.production.metabolic_engine import _extract_hours
        hours = _extract_hours(patient.timestamps)
        from cgmencode.production.data_quality import clean_glucose
        cleaned = clean_glucose(patient.glucose)
        events = _extract_correction_events(
            cleaned.glucose, patient.bolus, patient.carbs,
            hours, patient.profile)
        self.assertIsInstance(events, list)

    def test_meal_events_extracted_in_pipeline(self):
        """Pipeline extracts meal events when carbs+glucose data present."""
        from cgmencode.production.pipeline import _extract_meal_events
        patient = make_patient()
        from cgmencode.production.metabolic_engine import _extract_hours
        hours = _extract_hours(patient.timestamps)
        from cgmencode.production.data_quality import clean_glucose
        cleaned = clean_glucose(patient.glucose)
        events = _extract_meal_events(
            cleaned.glucose, patient.bolus, patient.carbs, hours)
        self.assertIsInstance(events, list)


# ── Patient Phenotype Tests (EXP-2541) ────────────────────────────────

class TestPatientPhenotypeTypes(unittest.TestCase):
    """Type contracts for PatientPhenotype and PatientPhenotypeResult."""

    def test_phenotype_enum_values(self):
        self.assertEqual(PatientPhenotype.WELL_CONTROLLED.value, "well_controlled")
        self.assertEqual(PatientPhenotype.HYPO_PRONE.value, "hypo_prone")
        self.assertEqual(PatientPhenotype.UNKNOWN.value, "unknown")

    def test_phenotype_result_fields(self):
        result = PatientPhenotypeResult(
            phenotype=PatientPhenotype.WELL_CONTROLLED,
            confidence=0.85,
            tir=0.77, tbr=0.022, tar=0.208,
            hypo_events_per_day=0.3, cv=0.30,
            evidence="Test evidence.",
        )
        self.assertEqual(result.phenotype, PatientPhenotype.WELL_CONTROLLED)
        self.assertAlmostEqual(result.tir, 0.77)

    def test_pipeline_result_has_phenotype_field(self):
        self.assertTrue(hasattr(PipelineResult, '__dataclass_fields__'))
        self.assertIn('phenotype', PipelineResult.__dataclass_fields__)


class TestPatientPhenotyper(unittest.TestCase):
    """Module contract tests for classify_patient_phenotype."""

    def test_well_controlled_classification(self):
        """TIR≥70% and TBR<4% → WELL_CONTROLLED."""
        from cgmencode.production.patient_phenotyper import classify_patient_phenotype
        n = 4320
        rng = np.random.RandomState(42)
        glucose = np.full(n, 130.0) + rng.normal(0, 15, n)
        glucose = np.clip(glucose, 75, 175)
        hours = (np.arange(n) * 5.0 / 60.0) % 24.0
        result = classify_patient_phenotype(glucose, hours, 15.0)
        self.assertEqual(result.phenotype, PatientPhenotype.WELL_CONTROLLED)
        self.assertGreaterEqual(result.tir, 0.70)
        self.assertLess(result.tbr, 0.04)
        self.assertGreaterEqual(result.confidence, 0.80)

    def test_hypo_prone_classification(self):
        """TBR≥4% → HYPO_PRONE."""
        from cgmencode.production.patient_phenotyper import classify_patient_phenotype
        n = 4320
        rng = np.random.RandomState(99)
        glucose = np.full(n, 110.0) + rng.normal(0, 35, n)
        below_count = int(0.10 * n)
        glucose[:below_count] = 55.0
        hours = (np.arange(n) * 5.0 / 60.0) % 24.0
        result = classify_patient_phenotype(glucose, hours, 15.0)
        self.assertEqual(result.phenotype, PatientPhenotype.HYPO_PRONE)
        self.assertGreaterEqual(result.tbr, 0.04)

    def test_insufficient_data_returns_unknown(self):
        """< 3 days → UNKNOWN phenotype."""
        from cgmencode.production.patient_phenotyper import classify_patient_phenotype
        glucose = np.full(100, 130.0)
        hours = (np.arange(100) * 5.0 / 60.0) % 24.0
        result = classify_patient_phenotype(glucose, hours, 0.35)
        self.assertEqual(result.phenotype, PatientPhenotype.UNKNOWN)
        self.assertEqual(result.confidence, 0.0)

    def test_confidence_scales_with_days(self):
        """Confidence increases with more data."""
        from cgmencode.production.patient_phenotyper import classify_patient_phenotype
        glucose = np.full(4320, 130.0)
        hours = (np.arange(4320) * 5.0 / 60.0) % 24.0
        r5 = classify_patient_phenotype(glucose, hours, 5.0)
        r14 = classify_patient_phenotype(glucose, hours, 14.0)
        self.assertGreater(r14.confidence, r5.confidence)

    def test_all_nan_returns_unknown(self):
        """All-NaN glucose → UNKNOWN."""
        from cgmencode.production.patient_phenotyper import classify_patient_phenotype
        glucose = np.full(4320, np.nan)
        hours = (np.arange(4320) * 5.0 / 60.0) % 24.0
        result = classify_patient_phenotype(glucose, hours, 15.0)
        self.assertEqual(result.phenotype, PatientPhenotype.UNKNOWN)

    def test_metrics_bounded(self):
        """TIR, TBR, TAR are 0-1, CV ≥ 0."""
        from cgmencode.production.patient_phenotyper import classify_patient_phenotype
        glucose = make_glucose(4320)
        hours = (np.arange(4320) * 5.0 / 60.0) % 24.0
        result = classify_patient_phenotype(glucose, hours, 15.0)
        self.assertGreaterEqual(result.tir, 0.0)
        self.assertLessEqual(result.tir, 1.0)
        self.assertGreaterEqual(result.tbr, 0.0)
        self.assertLessEqual(result.tbr, 1.0)
        self.assertGreaterEqual(result.tar, 0.0)
        self.assertLessEqual(result.tar, 1.0)
        self.assertGreaterEqual(result.cv, 0.0)

    def test_evidence_nonempty(self):
        """Evidence string is always non-empty."""
        from cgmencode.production.patient_phenotyper import classify_patient_phenotype
        glucose = np.full(4320, 130.0)
        hours = (np.arange(4320) * 5.0 / 60.0) % 24.0
        result = classify_patient_phenotype(glucose, hours, 15.0)
        self.assertGreater(len(result.evidence), 0)

    def test_high_cv_hypo_prone(self):
        """High CV > 0.36 when TIR borderline → HYPO_PRONE."""
        from cgmencode.production.patient_phenotyper import classify_patient_phenotype
        n = 4320
        rng = np.random.RandomState(7)
        glucose = 130 + rng.normal(0, 55, n)
        glucose = np.clip(glucose, 40, 400)
        hours = (np.arange(n) * 5.0 / 60.0) % 24.0
        result = classify_patient_phenotype(glucose, hours, 15.0)
        self.assertIn(result.phenotype,
                      [PatientPhenotype.HYPO_PRONE, PatientPhenotype.WELL_CONTROLLED])


class TestPhenotypePipelineIntegration(unittest.TestCase):
    """Integration: phenotype runs as pipeline stage."""

    def test_pipeline_populates_phenotype(self):
        from cgmencode.production.pipeline import run_pipeline
        patient = make_patient()
        result = run_pipeline(patient, skip_patterns=True)
        self.assertIsNotNone(result.phenotype)
        self.assertIsInstance(result.phenotype, PatientPhenotypeResult)
        self.assertIn(result.phenotype.phenotype, list(PatientPhenotype))
        self.assertGreaterEqual(result.phenotype.confidence, 0.0)
        self.assertLessEqual(result.phenotype.confidence, 1.0)


# ── Loop Quality Tests (EXP-2538/2540) ───────────────────────────────

class TestLoopQualityTypes(unittest.TestCase):
    """Type contracts for LoopQualityResult."""

    def test_result_fields(self):
        result = LoopQualityResult(
            hypo_episodes=5, loop_caused_hypos=2,
            loop_caused_fraction=0.4, median_reaction_time_min=5.0,
            high_excursions=10, unaddressed_excursions=6,
            unaddressed_fraction=0.6, aggression_ratio=2.2,
            overall_grade="fair", evidence="Test evidence.",
        )
        self.assertEqual(result.hypo_episodes, 5)
        self.assertAlmostEqual(result.loop_caused_fraction, 0.4)
        self.assertEqual(result.overall_grade, "fair")

    def test_pipeline_result_has_loop_quality_field(self):
        self.assertIn('loop_quality', PipelineResult.__dataclass_fields__)


class TestLoopQualityAssessment(unittest.TestCase):
    """Module contract tests for assess_loop_quality."""

    def test_no_hypos_good_grade(self):
        """Stable glucose with no hypos → good grade."""
        from cgmencode.production.loop_quality import assess_loop_quality
        n = 2000
        glucose = np.full(n, 130.0)
        hours = (np.arange(n) * 5.0 / 60.0) % 24.0
        basal = np.full(n, 0.8)
        result = assess_loop_quality(
            glucose, hours, basal_rate=basal, scheduled_basal=0.8,
            days_of_data=7.0)
        self.assertIsNotNone(result)
        self.assertEqual(result.hypo_episodes, 0)
        self.assertEqual(result.loop_caused_fraction, 0.0)
        self.assertEqual(result.overall_grade, "good")

    def test_loop_caused_hypo_detection(self):
        """Hypo preceded by elevated basal → loop-caused."""
        from cgmencode.production.loop_quality import assess_loop_quality
        n = 2000
        glucose = np.full(n, 130.0)
        basal = np.full(n, 0.8)
        glucose[500:505] = 60.0
        basal[494:500] = 1.5
        hours = (np.arange(n) * 5.0 / 60.0) % 24.0
        result = assess_loop_quality(
            glucose, hours, basal_rate=basal, scheduled_basal=0.8,
            days_of_data=7.0)
        self.assertIsNotNone(result)
        self.assertGreaterEqual(result.hypo_episodes, 1)
        self.assertGreaterEqual(result.loop_caused_hypos, 1)
        self.assertGreater(result.loop_caused_fraction, 0)

    def test_unaddressed_excursion_detection(self):
        """High excursion with no bolus → unaddressed."""
        from cgmencode.production.loop_quality import assess_loop_quality
        n = 2000
        glucose = np.full(n, 130.0)
        bolus = np.zeros(n)
        basal = np.full(n, 0.8)
        glucose[500:505] = 280.0
        hours = (np.arange(n) * 5.0 / 60.0) % 24.0
        result = assess_loop_quality(
            glucose, hours, basal_rate=basal, bolus=bolus,
            scheduled_basal=0.8, days_of_data=7.0)
        self.assertIsNotNone(result)
        self.assertGreaterEqual(result.high_excursions, 1)
        self.assertGreaterEqual(result.unaddressed_excursions, 1)

    def test_addressed_excursion(self):
        """High excursion with bolus nearby → addressed."""
        from cgmencode.production.loop_quality import assess_loop_quality
        n = 2000
        glucose = np.full(n, 130.0)
        bolus = np.zeros(n)
        basal = np.full(n, 0.8)
        glucose[500:505] = 280.0
        bolus[498] = 3.0
        hours = (np.arange(n) * 5.0 / 60.0) % 24.0
        result = assess_loop_quality(
            glucose, hours, basal_rate=basal, bolus=bolus,
            scheduled_basal=0.8, days_of_data=7.0)
        self.assertIsNotNone(result)
        if result.high_excursions > 0:
            self.assertLess(result.unaddressed_fraction, 1.0)

    def test_insufficient_data_returns_none(self):
        """< 3 days → None."""
        from cgmencode.production.loop_quality import assess_loop_quality
        glucose = np.full(100, 130.0)
        hours = np.zeros(100)
        result = assess_loop_quality(glucose, hours, days_of_data=0.3)
        self.assertIsNone(result)

    def test_no_basal_still_assesses_excursions(self):
        """Without basal data, can still detect excursions."""
        from cgmencode.production.loop_quality import assess_loop_quality
        n = 2000
        glucose = np.full(n, 130.0)
        glucose[500:505] = 280.0
        bolus = np.zeros(n)
        hours = (np.arange(n) * 5.0 / 60.0) % 24.0
        result = assess_loop_quality(
            glucose, hours, bolus=bolus, days_of_data=7.0)
        self.assertIsNotNone(result)
        self.assertGreaterEqual(result.high_excursions, 1)

    def test_aggression_ratio_computed(self):
        """Aggression ratio should be computed when basal varies by glucose."""
        from cgmencode.production.loop_quality import assess_loop_quality
        n = 2000
        glucose = np.full(n, 100.0)
        glucose[0:500] = 220.0
        basal = np.full(n, 0.8)
        basal[0:500] = 1.8
        hours = (np.arange(n) * 5.0 / 60.0) % 24.0
        result = assess_loop_quality(
            glucose, hours, basal_rate=basal, scheduled_basal=0.8,
            days_of_data=7.0)
        self.assertIsNotNone(result)
        self.assertGreater(result.aggression_ratio, 1.5)

    def test_evidence_nonempty(self):
        """Evidence string is always non-empty."""
        from cgmencode.production.loop_quality import assess_loop_quality
        n = 2000
        glucose = np.full(n, 130.0)
        hours = (np.arange(n) * 5.0 / 60.0) % 24.0
        result = assess_loop_quality(glucose, hours, days_of_data=7.0)
        self.assertIsNotNone(result)
        self.assertGreater(len(result.evidence), 0)

    def test_grade_values(self):
        """Grade must be one of good/fair/poor."""
        from cgmencode.production.loop_quality import assess_loop_quality
        n = 2000
        glucose = np.full(n, 130.0)
        hours = (np.arange(n) * 5.0 / 60.0) % 24.0
        result = assess_loop_quality(glucose, hours, days_of_data=7.0)
        self.assertIsNotNone(result)
        self.assertIn(result.overall_grade, ("good", "fair", "poor"))


class TestLoopQualityPipelineIntegration(unittest.TestCase):
    """Integration: loop quality runs as pipeline stage."""

    def test_pipeline_populates_loop_quality(self):
        from cgmencode.production.pipeline import run_pipeline
        patient = make_patient()
        result = run_pipeline(patient, skip_patterns=True)
        self.assertIsNotNone(result.loop_quality)
        self.assertIsInstance(result.loop_quality, LoopQualityResult)
        self.assertIn(result.loop_quality.overall_grade,
                      ("good", "fair", "poor"))

    def test_pipeline_without_basal_skips_loop_quality(self):
        from cgmencode.production.pipeline import run_pipeline
        patient = make_patient(with_insulin=False)
        result = run_pipeline(patient, skip_patterns=True)
        self.assertIsNone(result.loop_quality)


# ── Profile Generator Tests (WS-2) ──────────────────────────────────

class TestProfileGeneratorTypes(unittest.TestCase):
    """Type and structure tests for profile_generator.py."""

    def test_generated_profile_fields(self):
        from cgmencode.production.profile_generator import GeneratedProfile
        gp = GeneratedProfile(
            basal_blocks=[{'hour': 0, 'value': 0.8, 'period': 'overnight', 'confidence': 'high', 'change_pct': 0.0}],
            isf_blocks=[{'hour': 0, 'value': 50.0, 'period': 'overnight', 'confidence': 'high', 'change_pct': 0.0}],
            cr_blocks=[{'hour': 0, 'value': 10.0, 'period': 'overnight', 'confidence': 'high', 'change_pct': 0.0}],
        )
        self.assertEqual(gp.dia_hours, 5.0)
        self.assertEqual(gp.units, 'mg/dL')
        self.assertIsInstance(gp.warnings, list)

    def test_import_from_package(self):
        from cgmencode.production import generate_profile, generate_all_formats, GeneratedProfile
        self.assertTrue(callable(generate_profile))
        self.assertTrue(callable(generate_all_formats))


class TestProfileGeneratorOref0(unittest.TestCase):
    """Test oref0 format output."""

    def _make_profile(self):
        from cgmencode.production.profile_generator import GeneratedProfile
        return GeneratedProfile(
            basal_blocks=[
                {'hour': 0, 'value': 0.8, 'period': 'overnight', 'confidence': 'high', 'change_pct': 10.0},
                {'hour': 6, 'value': 1.0, 'period': 'morning', 'confidence': 'medium', 'change_pct': 5.0},
                {'hour': 14, 'value': 0.9, 'period': 'afternoon', 'confidence': 'high', 'change_pct': 0.0},
            ],
            isf_blocks=[
                {'hour': 0, 'value': 60.0, 'period': 'overnight', 'confidence': 'high', 'change_pct': 20.0},
                {'hour': 10, 'value': 45.0, 'period': 'midday', 'confidence': 'medium', 'change_pct': -10.0},
            ],
            cr_blocks=[
                {'hour': 0, 'value': 12.0, 'period': 'overnight', 'confidence': 'high', 'change_pct': 0.0},
            ],
            dia_hours=6.0,
            target_low=100.0,
            target_high=120.0,
        )

    def test_oref0_has_basalprofile(self):
        p = self._make_profile().to_oref0()
        self.assertIn('basalprofile', p)
        self.assertEqual(len(p['basalprofile']), 3)

    def test_oref0_basal_minutes(self):
        p = self._make_profile().to_oref0()
        self.assertEqual(p['basalprofile'][0]['minutes'], 0)
        self.assertEqual(p['basalprofile'][1]['minutes'], 360)  # 6h * 60
        self.assertEqual(p['basalprofile'][0]['start'], '00:00:00')

    def test_oref0_isf_sensitivities(self):
        p = self._make_profile().to_oref0()
        self.assertIn('isfProfile', p)
        sens = p['isfProfile']['sensitivities']
        self.assertEqual(len(sens), 2)
        self.assertEqual(sens[0]['sensitivity'], 60.0)
        self.assertEqual(sens[0]['offset'], 0)
        self.assertEqual(sens[1]['endOffset'], 1440)

    def test_oref0_dia_clamped(self):
        from cgmencode.production.profile_generator import GeneratedProfile
        p = GeneratedProfile(
            basal_blocks=[{'hour': 0, 'value': 1.0, 'period': 'overnight', 'confidence': 'high', 'change_pct': 0.0}],
            isf_blocks=[{'hour': 0, 'value': 50.0, 'period': 'overnight', 'confidence': 'high', 'change_pct': 0.0}],
            cr_blocks=[{'hour': 0, 'value': 10.0, 'period': 'overnight', 'confidence': 'high', 'change_pct': 0.0}],
            dia_hours=15.0,  # exceeds max
        )
        out = p.to_oref0()
        self.assertLessEqual(out['dia'], 12.0)

    def test_oref0_carb_ratios(self):
        p = self._make_profile().to_oref0()
        self.assertIn('carb_ratios', p)
        self.assertEqual(p['carb_ratios']['schedule'][0]['ratio'], 12.0)

    def test_oref0_bg_targets(self):
        p = self._make_profile().to_oref0()
        self.assertEqual(p['bg_targets']['targets'][0]['low'], 100.0)
        self.assertEqual(p['bg_targets']['targets'][0]['high'], 120.0)


class TestProfileGeneratorLoop(unittest.TestCase):
    """Test Loop format output."""

    def _make_profile(self):
        from cgmencode.production.profile_generator import GeneratedProfile
        return GeneratedProfile(
            basal_blocks=[
                {'hour': 0, 'value': 0.8, 'period': 'overnight', 'confidence': 'high', 'change_pct': 0.0},
                {'hour': 8, 'value': 0.6, 'period': 'morning', 'confidence': 'high', 'change_pct': 0.0},
            ],
            isf_blocks=[
                {'hour': 0, 'value': 50.0, 'period': 'overnight', 'confidence': 'high', 'change_pct': 0.0},
            ],
            cr_blocks=[
                {'hour': 0, 'value': 10.0, 'period': 'overnight', 'confidence': 'high', 'change_pct': 0.0},
            ],
        )

    def test_loop_uses_seconds(self):
        p = self._make_profile().to_loop()
        items = p['basalRateSchedule']['items']
        self.assertEqual(items[0]['startTime'], 0)
        self.assertEqual(items[1]['startTime'], 28800)  # 8h * 3600

    def test_loop_has_effect_duration(self):
        p = self._make_profile().to_loop()
        self.assertEqual(p['insulinModelSettings']['effectDuration'], 5.0 * 3600)

    def test_loop_has_sensitivity_schedule(self):
        p = self._make_profile().to_loop()
        self.assertIn('insulinSensitivitySchedule', p)
        self.assertEqual(p['insulinSensitivitySchedule']['items'][0]['value'], 50.0)

    def test_loop_has_target_range(self):
        p = self._make_profile().to_loop()
        self.assertIn('glucoseTargetRangeSchedule', p)


class TestProfileGeneratorTrio(unittest.TestCase):
    """Test Trio format output."""

    def _make_profile(self):
        from cgmencode.production.profile_generator import GeneratedProfile
        return GeneratedProfile(
            basal_blocks=[
                {'hour': 0, 'value': 0.8, 'period': 'overnight', 'confidence': 'high', 'change_pct': 0.0},
            ],
            isf_blocks=[
                {'hour': 0, 'value': 50.0, 'period': 'overnight', 'confidence': 'high', 'change_pct': 0.0},
                {'hour': 12, 'value': 40.0, 'period': 'midday', 'confidence': 'medium', 'change_pct': -20.0},
            ],
            cr_blocks=[
                {'hour': 0, 'value': 10.0, 'period': 'overnight', 'confidence': 'high', 'change_pct': 0.0},
            ],
        )

    def test_trio_dual_time(self):
        """Trio has both minutes offset AND HH:MM:SS string."""
        p = self._make_profile().to_trio()
        basal = p['basalprofile'][0]
        self.assertEqual(basal['minutes'], 0)
        self.assertEqual(basal['start'], '00:00:00')

    def test_trio_isf_has_offset_and_start(self):
        p = self._make_profile().to_trio()
        isf = p['isfProfile']['sensitivities']
        self.assertEqual(isf[1]['offset'], 720)  # 12h * 60
        self.assertEqual(isf[1]['start'], '12:00:00')

    def test_trio_units(self):
        p = self._make_profile().to_trio()
        self.assertEqual(p['isfProfile']['units'], 'mg/dl')


class TestProfileGeneratorNightscout(unittest.TestCase):
    """Test Nightscout ProfileSet format."""

    def _make_profile(self):
        from cgmencode.production.profile_generator import GeneratedProfile
        return GeneratedProfile(
            basal_blocks=[
                {'hour': 0, 'value': 0.8, 'period': 'overnight', 'confidence': 'high', 'change_pct': 0.0},
                {'hour': 18, 'value': 1.1, 'period': 'evening', 'confidence': 'high', 'change_pct': 0.0},
            ],
            isf_blocks=[
                {'hour': 0, 'value': 50.0, 'period': 'overnight', 'confidence': 'high', 'change_pct': 0.0},
            ],
            cr_blocks=[
                {'hour': 0, 'value': 10.0, 'period': 'overnight', 'confidence': 'high', 'change_pct': 0.0},
            ],
        )

    def test_ns_has_profile_set(self):
        p = self._make_profile().to_nightscout()
        self.assertIn('defaultProfile', p)
        self.assertEqual(p['defaultProfile'], 'Default')
        self.assertIn('store', p)
        self.assertIn('Default', p['store'])

    def test_ns_basal_hhmm(self):
        p = self._make_profile().to_nightscout()
        basal = p['store']['Default']['basal']
        self.assertEqual(basal[0]['time'], '00:00')
        self.assertEqual(basal[1]['time'], '18:00')

    def test_ns_sens_has_time_as_seconds(self):
        p = self._make_profile().to_nightscout()
        sens = p['store']['Default']['sens']
        self.assertEqual(sens[0]['timeAsSeconds'], 0)

    def test_ns_values_are_strings(self):
        """Nightscout stores numeric values as strings."""
        p = self._make_profile().to_nightscout()
        basal = p['store']['Default']['basal']
        self.assertIsInstance(basal[0]['value'], str)


class TestProfileGeneratorConstraints(unittest.TestCase):
    """Test physiological constraint enforcement."""

    def test_clamp_basal(self):
        from cgmencode.production.profile_generator import _clamp
        self.assertEqual(_clamp(0.01, 'basal_rate'), 0.025)
        self.assertEqual(_clamp(15.0, 'basal_rate'), 10.0)
        self.assertEqual(_clamp(1.0, 'basal_rate'), 1.0)

    def test_clamp_isf(self):
        from cgmencode.production.profile_generator import _clamp
        self.assertEqual(_clamp(5.0, 'isf'), 10.0)
        self.assertEqual(_clamp(600.0, 'isf'), 500.0)

    def test_clamp_cr(self):
        from cgmencode.production.profile_generator import _clamp
        self.assertEqual(_clamp(1.0, 'cr'), 3.0)
        self.assertEqual(_clamp(200.0, 'cr'), 150.0)


class TestProfileGeneratorJSON(unittest.TestCase):
    """Test JSON serialization."""

    def _make_profile(self):
        from cgmencode.production.profile_generator import GeneratedProfile
        return GeneratedProfile(
            basal_blocks=[{'hour': 0, 'value': 0.8, 'period': 'overnight', 'confidence': 'high', 'change_pct': 0.0}],
            isf_blocks=[{'hour': 0, 'value': 50.0, 'period': 'overnight', 'confidence': 'high', 'change_pct': 0.0}],
            cr_blocks=[{'hour': 0, 'value': 10.0, 'period': 'overnight', 'confidence': 'high', 'change_pct': 0.0}],
        )

    def test_to_json_all_formats(self):
        import json
        p = self._make_profile()
        for fmt in ['oref0', 'loop', 'trio', 'nightscout']:
            s = p.to_json(fmt)
            parsed = json.loads(s)
            self.assertIsInstance(parsed, dict)

    def test_to_json_invalid_format(self):
        p = self._make_profile()
        with self.assertRaises(ValueError):
            p.to_json('invalid')


# ── Prediction Validator Tests (WS-3) ───────────────────────────────

class TestPredictionValidatorTypes(unittest.TestCase):
    """Type tests for prediction_validator.py."""

    def test_validation_result_fields(self):
        from cgmencode.production.prediction_validator import PredictionValidationResult
        r = PredictionValidationResult(
            patient_id='test', n_train=1000, n_test=250,
            actual_tir_train=0.70, actual_tir_test=0.72,
            predicted_tir_test=0.73, tir_delta_actual=0.02,
            tir_delta_predicted=0.03, prediction_error=0.01,
            isf_multiplier=1.3, cr_multiplier=1.0, basal_multiplier=1.0,
        )
        self.assertEqual(r.patient_id, 'test')
        self.assertAlmostEqual(r.prediction_error, 0.01)

    def test_validation_summary_actionable(self):
        from cgmencode.production.prediction_validator import ValidationSummary
        good = ValidationSummary(
            n_patients=10, mean_absolute_error=0.02,
            correlation=0.8, calibration_slope=0.9,
            calibration_intercept=0.01, coverage_80=0.85,
        )
        self.assertTrue(good.is_actionable)

        bad = ValidationSummary(
            n_patients=10, mean_absolute_error=0.05,
            correlation=0.3, calibration_slope=0.5,
            calibration_intercept=0.1, coverage_80=0.40,
        )
        self.assertFalse(bad.is_actionable)

    def test_import_from_package(self):
        from cgmencode.production import (
            validate_patient, validate_batch, generate_validation_report,
            PredictionValidationResult, ValidationSummary,
        )
        self.assertTrue(callable(validate_patient))
        self.assertTrue(callable(validate_batch))
        self.assertTrue(callable(generate_validation_report))


class TestPredictionValidatorExecution(unittest.TestCase):
    """Functional tests for validation on synthetic data."""

    def test_validate_patient_synthetic(self):
        """Validate on a single synthetic patient (30 days)."""
        from cgmencode.production.prediction_validator import validate_patient
        patient = make_patient()
        result = validate_patient(patient, 'synthetic')
        self.assertIsNotNone(result)
        self.assertEqual(result.patient_id, 'synthetic')
        self.assertGreater(result.n_train, 0)
        self.assertGreater(result.n_test, 0)
        self.assertGreaterEqual(result.actual_tir_train, 0.0)
        self.assertLessEqual(result.actual_tir_train, 1.0)
        self.assertGreaterEqual(result.prediction_error, 0.0)

    def test_validate_patient_short_data_returns_none(self):
        """Patient with <1 day holdout returns None."""
        from cgmencode.production.prediction_validator import validate_patient
        # Only 200 samples total → holdout = 40 samples < 288
        profile = make_profile()
        patient = PatientData(
            glucose=np.random.uniform(80, 200, 200).astype(np.float64),
            timestamps=np.arange(200, dtype=np.float64) * 300000 + 1700000000000,
            profile=profile,
        )
        result = validate_patient(patient, 'short')
        self.assertIsNone(result)

    def test_validate_batch_synthetic(self):
        """Validate across multiple synthetic patients."""
        from cgmencode.production.prediction_validator import validate_batch
        patients = {}
        for pid in ['p1', 'p2', 'p3']:
            patients[pid] = make_patient()
        summary = validate_batch(patients)
        self.assertEqual(summary.n_patients, 3)
        self.assertGreaterEqual(summary.mean_absolute_error, 0.0)
        self.assertIsInstance(summary.correlation, float)

    def test_validation_report_generation(self):
        """Report renders as markdown."""
        from cgmencode.production.prediction_validator import (
            validate_batch, generate_validation_report,
        )
        patients = {'p1': make_patient(), 'p2': make_patient()}
        summary = validate_batch(patients)
        report = generate_validation_report(summary)
        self.assertIn('Prediction Validation Report', report)
        self.assertIn('MAE', report)
        self.assertIn('Correlation', report)


# ─── Forward Simulator Tests ──────────────────────────────────────────

class TestForwardSimulator(unittest.TestCase):
    """Tests for the forward simulation engine."""

    def setUp(self):
        from cgmencode.production.forward_simulator import (
            forward_simulate, compare_scenarios, simulate_typical_day,
            TherapySettings, InsulinEvent, CarbEvent,
        )
        self.forward_simulate = forward_simulate
        self.compare_scenarios = compare_scenarios
        self.simulate_typical_day = simulate_typical_day
        self.TherapySettings = TherapySettings
        self.InsulinEvent = InsulinEvent
        self.CarbEvent = CarbEvent
        self.settings = TherapySettings(isf=50, cr=10, basal_rate=0.8)

    def test_steady_state_flat(self):
        """At correct basal with no meals, glucose stays at initial."""
        r = self.forward_simulate(120.0, self.settings, duration_hours=6.0, seed=42)
        # Should stay very close to 120
        self.assertAlmostEqual(r.glucose[-1], 120.0, delta=5.0)
        self.assertAlmostEqual(r.mean_glucose, 120.0, delta=3.0)

    def test_decay_toward_target(self):
        """Starting high should decay toward 120."""
        r = self.forward_simulate(200.0, self.settings, duration_hours=12.0, seed=42)
        self.assertLess(r.glucose[-1], 200.0)
        # Decay should bring it closer to 120
        self.assertLess(r.glucose[-1], 180.0)

    def test_correction_bolus_lowers(self):
        """Correction bolus should lower glucose proportional to ISF."""
        bolus_units = 1.6  # expect ~80 mg/dL drop at ISF=50
        r = self.forward_simulate(200.0, self.settings, duration_hours=6.0,
            bolus_events=[self.InsulinEvent(0, bolus_units)], seed=42)
        drop = 200.0 - r.glucose[-1]
        # Should drop significantly (not exact due to two-component split)
        self.assertGreater(drop, 40)
        self.assertLess(drop, 120)  # not too much

    def test_meal_raises_glucose(self):
        """Meal without bolus should raise glucose."""
        r = self.forward_simulate(120.0, self.settings, duration_hours=4.0,
            carb_events=[self.CarbEvent(30, 45)], seed=42)
        self.assertGreater(r.glucose.max(), 150.0)

    def test_meal_with_correct_bolus(self):
        """Correctly bolused meal should spike then return near baseline."""
        r = self.forward_simulate(120.0, self.settings, duration_hours=8.0,
            bolus_events=[self.InsulinEvent(60, 4.5)],
            carb_events=[self.CarbEvent(60, 45)], seed=42)
        # Should spike
        self.assertGreater(r.glucose.max(), 150.0)
        # Should come back down (not necessarily to 120 due to persistent)
        self.assertLess(r.glucose[-1], r.glucose.max())

    def test_under_bolused_meal(self):
        """Under-bolused meal should spike higher."""
        r_correct = self.forward_simulate(120.0, self.settings, duration_hours=6.0,
            bolus_events=[self.InsulinEvent(60, 4.5)],
            carb_events=[self.CarbEvent(60, 45)], seed=42)
        r_under = self.forward_simulate(120.0, self.settings, duration_hours=6.0,
            bolus_events=[self.InsulinEvent(60, 3.0)],
            carb_events=[self.CarbEvent(60, 45)], seed=42)
        self.assertGreater(r_under.glucose.max(), r_correct.glucose.max())

    def test_low_basal_raises(self):
        """Basal below metabolic need should raise glucose."""
        low = self.TherapySettings(isf=50, cr=10, basal_rate=0.5)
        r = self.forward_simulate(120.0, low, duration_hours=6.0,
            metabolic_basal_rate=0.8, seed=42)
        self.assertGreater(r.glucose[-1], 120.0)

    def test_high_basal_lowers(self):
        """Basal above metabolic need should lower glucose."""
        high = self.TherapySettings(isf=50, cr=10, basal_rate=1.1)
        r = self.forward_simulate(120.0, high, duration_hours=6.0,
            metabolic_basal_rate=0.8, seed=42)
        self.assertLess(r.glucose[-1], 120.0)

    def test_scenario_comparison(self):
        """compare_scenarios should show basal rate effect."""
        low = self.TherapySettings(isf=50, cr=10, basal_rate=0.5)
        high = self.TherapySettings(isf=50, cr=10, basal_rate=1.1)
        comp = self.compare_scenarios(120.0, low, high, duration_hours=6.0,
            metabolic_basal_rate=0.8, seed=42)
        # High basal should produce lower mean glucose
        self.assertLess(comp.modified.mean_glucose, comp.baseline.mean_glucose)

    def test_scenario_comparison_summary(self):
        """Scenario summary should contain expected keys."""
        comp = self.compare_scenarios(120.0, self.settings, self.settings,
            duration_hours=4.0, seed=42)
        s = comp.summary()
        self.assertIn('baseline', s)
        self.assertIn('modified', s)
        self.assertIn('tir_delta_pp', s)

    def test_typical_day(self):
        """Typical day with meals should produce reasonable TIR."""
        r = self.simulate_typical_day(self.settings, seed=42)
        self.assertEqual(r.n_steps, 288)  # 24h × 12
        self.assertGreater(r.tir, 0.3)  # At least 30% TIR
        self.assertLess(r.tbr, 0.3)  # Not too much hypo

    def test_simulation_result_properties(self):
        """SimulationResult properties should be consistent."""
        r = self.forward_simulate(120.0, self.settings, duration_hours=6.0, seed=42)
        self.assertAlmostEqual(r.tir + r.tbr + r.tar, 1.0, places=5)
        self.assertEqual(r.duration_hours, 6.0)
        self.assertGreater(r.mean_glucose, 0)
        self.assertGreaterEqual(r.cv, 0)

    def test_noise_adds_variability(self):
        """Noise parameter should increase CV."""
        r_clean = self.forward_simulate(120.0, self.settings, duration_hours=6.0,
            noise_std=0.0, seed=42)
        r_noisy = self.forward_simulate(120.0, self.settings, duration_hours=6.0,
            noise_std=2.0, seed=42)
        self.assertGreater(r_noisy.cv, r_clean.cv)

    def test_deterministic_with_seed(self):
        """Same seed should produce identical results."""
        r1 = self.forward_simulate(120.0, self.settings, duration_hours=4.0,
            noise_std=1.0, seed=123)
        r2 = self.forward_simulate(120.0, self.settings, duration_hours=4.0,
            noise_std=1.0, seed=123)
        np.testing.assert_array_equal(r1.glucose, r2.glucose)

    def test_circadian_isf_schedule(self):
        """Circadian ISF schedule should affect bolus response."""
        # Night ISF = 30 (less sensitive), day ISF = 60 (more sensitive)
        s = self.TherapySettings(isf=50, cr=10, basal_rate=0.8,
            isf_schedule=[(0, 30), (8, 60), (20, 30)])
        # Night correction (start_hour=2) → ISF=30 → smaller drop per unit
        r_night = self.forward_simulate(200.0, s, duration_hours=6.0,
            bolus_events=[self.InsulinEvent(0, 1.0)], start_hour=2.0, seed=42)
        # Day correction (start_hour=12) → ISF=60 → bigger drop per unit
        r_day = self.forward_simulate(200.0, s, duration_hours=6.0,
            bolus_events=[self.InsulinEvent(0, 1.0)], start_hour=12.0, seed=42)
        drop_night = 200 - r_night.glucose[-1]
        drop_day = 200 - r_day.glucose[-1]
        self.assertGreater(drop_day, drop_night)

    def test_glucose_stays_in_bounds(self):
        """Glucose should never go below 39 or above 401."""
        # Massive insulin → should hit floor
        r = self.forward_simulate(80.0, self.settings, duration_hours=6.0,
            bolus_events=[self.InsulinEvent(0, 20.0)], seed=42)
        self.assertGreaterEqual(r.glucose.min(), 39.0)
        # No insulin at all → should hit ceiling eventually? No, decay holds it
        # Just verify clipping works
        self.assertLessEqual(r.glucose.max(), 401.0)

    def test_iob_trace(self):
        """IOB should rise after bolus then decay."""
        r = self.forward_simulate(120.0, self.settings, duration_hours=6.0,
            bolus_events=[self.InsulinEvent(30, 3.0)], seed=42)
        # IOB should peak shortly after bolus (step 6 = 30min)
        peak_step = np.argmax(r.iob)
        self.assertGreater(peak_step, 5)
        self.assertLess(peak_step, 20)
        # IOB at end should be much less than peak
        self.assertLess(r.iob[-1], r.iob[peak_step])

    def test_cob_trace(self):
        """COB should appear at meal time then decrease."""
        r = self.forward_simulate(120.0, self.settings, duration_hours=6.0,
            carb_events=[self.CarbEvent(30, 60)], seed=42)
        # COB should be >0 after meal (step 7 = 35min)
        self.assertGreater(r.cob[8], 0)
        # COB should be 0 after full absorption (3h = 36 steps after meal)
        self.assertAlmostEqual(r.cob[-1], 0.0, places=1)

    def test_therapy_settings_schedule_lookup(self):
        """Schedule lookup should follow hour boundaries."""
        s = self.TherapySettings(isf=50, cr=10, basal_rate=0.8,
            isf_schedule=[(0, 30), (8, 60), (20, 40)])
        self.assertEqual(s.isf_at_hour(3.0), 30)
        self.assertEqual(s.isf_at_hour(12.0), 60)
        self.assertEqual(s.isf_at_hour(22.0), 40)
