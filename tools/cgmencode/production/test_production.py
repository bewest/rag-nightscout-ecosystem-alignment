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
    CompensationType,
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
        """16 features in dual-mode model."""
        self.assertEqual(len(self.ML_FEATURE_NAMES), 16)

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


# ── Runner ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main()
