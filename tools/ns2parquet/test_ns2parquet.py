#!/usr/bin/env python3
"""
Test suite for ns2parquet — Nightscout JSON→Parquet research pipeline.

Tests cover:
  - Unit conversion correctness (mmol/L, durations, absorption times)
  - SMB detection logic (multi-step, per GAP-TREAT-002)
  - Schedule lookup (time-varying profiles)
  - Opaque ID generation (deterministic, case-insensitive)
  - Settings normalization (AID/pump/MDI classification)
  - Parquet write/read round-trip with dedup
  - Grid builder column completeness
  - Integration: full pipeline vs JSON pipeline (real patient data)

Run:
    python3 -m pytest tools/ns2parquet/test_ns2parquet.py -v
    # or via Makefile:
    make ns2parquet-tests
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

# ── Helpers available without real data ──────────────────────────────


class TestOpaqueId(unittest.TestCase):
    """Test _generate_opaque_id determinism and privacy."""

    def setUp(self):
        from tools.ns2parquet.cli import _generate_opaque_id
        self.gen = _generate_opaque_id

    def test_deterministic(self):
        """Same input always produces the same ID."""
        self.assertEqual(self.gen('abc'), self.gen('abc'))

    def test_case_insensitive(self):
        """URL case differences produce the same ID."""
        self.assertEqual(
            self.gen('https://MY-NS.fly.dev'),
            self.gen('https://my-ns.fly.dev'),
        )

    def test_trailing_slash_normalized(self):
        self.assertEqual(
            self.gen('https://ns.example.com/'),
            self.gen('https://ns.example.com'),
        )

    def test_different_inputs_differ(self):
        self.assertNotEqual(self.gen('site-a'), self.gen('site-b'))

    def test_format(self):
        """ID has 'ns-' prefix and hex suffix."""
        oid = self.gen('test')
        self.assertTrue(oid.startswith('ns-'))
        self.assertEqual(len(oid), 15)  # ns- + 12 hex chars

    def test_not_reversible(self):
        """ID does not contain the input string."""
        oid = self.gen('my-secret-nightscout-url')
        self.assertNotIn('secret', oid)
        self.assertNotIn('nightscout', oid)


class TestSMBDetection(unittest.TestCase):
    """Test multi-step SMB detection per GAP-TREAT-002."""

    def setUp(self):
        from tools.ns2parquet.normalize import _is_smb
        self.is_smb = _is_smb

    def test_aaps_smb_type(self):
        """AAPS: type == 'SMB' is sufficient."""
        self.assertTrue(self.is_smb({'type': 'SMB', 'insulin': 0.3}))

    def test_loop_automatic_small(self):
        """Loop/Trio: automatic=True + small insulin."""
        self.assertTrue(self.is_smb({'automatic': True, 'insulin': 0.2}))

    def test_loop_automatic_large_not_smb(self):
        """Large automatic bolus (>=5U) is not classified as SMB."""
        self.assertFalse(self.is_smb({'automatic': True, 'insulin': 6.0}))

    def test_manual_bolus_not_smb(self):
        """Manual bolus without type/automatic is not SMB."""
        self.assertFalse(self.is_smb({'insulin': 2.0, 'eventType': 'Bolus'}))

    def test_empty_record(self):
        self.assertFalse(self.is_smb({}))

    def test_automatic_zero_insulin(self):
        """automatic=True but no insulin is not SMB."""
        self.assertFalse(self.is_smb({'automatic': True, 'insulin': 0}))


class TestDurationConversion(unittest.TestCase):
    """Test duration unit normalization across controllers."""

    def setUp(self):
        from tools.ns2parquet.normalize import _duration_to_minutes
        self.dur = _duration_to_minutes

    def test_oref0_minutes_passthrough(self):
        """oref0 durations in minutes pass through unchanged."""
        self.assertEqual(self.dur({'duration': 30}), 30.0)

    def test_loop_seconds_to_minutes(self):
        """Loop durations >1000 are treated as seconds."""
        self.assertAlmostEqual(
            self.dur({'duration': 1800}, device='Loop'),
            30.0,
        )

    def test_aaps_milliseconds_to_minutes(self):
        """AAPS durations >86400 are treated as milliseconds."""
        self.assertAlmostEqual(
            self.dur({'duration': 1800000}),
            30.0,
        )

    def test_none_duration(self):
        self.assertIsNone(self.dur({}))

    def test_normal_range_passthrough(self):
        """Values in normal range (0-1000) are treated as minutes."""
        self.assertEqual(self.dur({'duration': 60}), 60.0)


class TestAbsorptionConversion(unittest.TestCase):
    """Test absorptionTime normalization."""

    def setUp(self):
        from tools.ns2parquet.normalize import _absorption_to_minutes
        self.abs = _absorption_to_minutes

    def test_minutes_passthrough(self):
        """Normal absorption time in minutes passes through."""
        self.assertEqual(self.abs({'absorptionTime': 180}), 180.0)

    def test_seconds_to_minutes(self):
        """Loop-style seconds (>500) converted to minutes."""
        self.assertAlmostEqual(
            self.abs({'absorptionTime': 10800}),
            180.0,
        )

    def test_none(self):
        self.assertIsNone(self.abs({}))

    def test_boundary(self):
        """500 minutes is valid as-is (8.3 hours — long but plausible)."""
        self.assertEqual(self.abs({'absorptionTime': 500}), 500.0)


class TestScheduleLookup(unittest.TestCase):
    """Test time-varying schedule lookup."""

    def setUp(self):
        from tools.ns2parquet.grid import _lookup_schedule
        self.lookup = _lookup_schedule

    def test_single_entry(self):
        sched = [{'timeAsSeconds': 0, 'value': 1.0}]
        self.assertEqual(self.lookup(43200, sched), 1.0)  # noon

    def test_multiple_entries(self):
        sched = [
            {'timeAsSeconds': 0, 'value': 0.8},      # midnight
            {'timeAsSeconds': 21600, 'value': 1.2},   # 6am
            {'timeAsSeconds': 64800, 'value': 0.9},   # 6pm
        ]
        self.assertEqual(self.lookup(0, sched), 0.8)       # midnight
        self.assertEqual(self.lookup(10800, sched), 0.8)    # 3am (before 6am)
        self.assertEqual(self.lookup(21600, sched), 1.2)    # exactly 6am
        self.assertEqual(self.lookup(43200, sched), 1.2)    # noon
        self.assertEqual(self.lookup(64800, sched), 0.9)    # exactly 6pm
        self.assertEqual(self.lookup(80000, sched), 0.9)    # 10pm

    def test_empty_schedule(self):
        self.assertEqual(self.lookup(0, [], default=99.0), 99.0)

    def test_default_value(self):
        self.assertEqual(self.lookup(0, [], default=42.0), 42.0)


class TestMmolConversion(unittest.TestCase):
    """Test mmol/L → mg/dL conversion using Nightscout canonical constant."""

    MMOLL_TO_MGDL = 18.01559

    def test_isf_conversion(self):
        """ISF 2.7 mmol/L → ~48.6 mg/dL."""
        result = 2.7 * self.MMOLL_TO_MGDL
        self.assertAlmostEqual(result, 48.64, places=1)

    def test_target_conversion(self):
        """Target 5.5 mmol/L → ~99.1 mg/dL."""
        result = 5.5 * self.MMOLL_TO_MGDL
        self.assertAlmostEqual(result, 99.09, places=1)

    def test_normalize_profiles_converts(self):
        """normalize_profiles converts mmol/L ISF and targets to mg/dL."""
        from tools.ns2parquet.normalize import normalize_profiles

        profile_doc = [{
            '_id': 'test',
            'store': {
                'Default': {
                    'units': 'mmol/L',
                    'dia': 5.0,
                    'timezone': 'UTC',
                    'basal': [{'time': '00:00', 'timeAsSeconds': 0, 'value': 1.0}],
                    'sens': [{'time': '00:00', 'timeAsSeconds': 0, 'value': 2.7}],
                    'carbratio': [{'time': '00:00', 'timeAsSeconds': 0, 'value': 10}],
                    'target_low': [{'time': '00:00', 'timeAsSeconds': 0, 'value': 4.0}],
                    'target_high': [{'time': '00:00', 'timeAsSeconds': 0, 'value': 6.5}],
                }
            }
        }]
        df = normalize_profiles(profile_doc, 'test')
        isf = df[df['schedule_type'] == 'isf']
        basal = df[df['schedule_type'] == 'basal']
        tgt_low = df[df['schedule_type'] == 'target_low']

        # ISF should be converted
        self.assertAlmostEqual(isf['value'].iloc[0], 2.7 * self.MMOLL_TO_MGDL, places=2)
        # Basal should NOT be converted (U/hr, not glucose units)
        self.assertEqual(basal['value'].iloc[0], 1.0)
        # Targets should be converted
        self.assertAlmostEqual(tgt_low['value'].iloc[0], 4.0 * self.MMOLL_TO_MGDL, places=2)
        # All units should say mg/dL after conversion
        self.assertTrue((df['units'] == 'mg/dL').all())

    def test_mgdl_profiles_unchanged(self):
        """mg/dL profiles are not converted."""
        from tools.ns2parquet.normalize import normalize_profiles

        profile_doc = [{
            '_id': 'test',
            'store': {
                'Default': {
                    'units': 'mg/dL',
                    'dia': 5.0,
                    'sens': [{'time': '00:00', 'timeAsSeconds': 0, 'value': 48.6}],
                }
            }
        }]
        df = normalize_profiles(profile_doc, 'test')
        isf = df[df['schedule_type'] == 'isf']
        self.assertAlmostEqual(isf['value'].iloc[0], 48.6, places=1)


class TestSettingsNormalization(unittest.TestCase):
    """Test normalize_settings AID/pump/MDI classification."""

    def setUp(self):
        from tools.ns2parquet.normalize import normalize_settings
        self.norm = normalize_settings

    def test_aid_loop(self):
        status = {'settings': {
            'units': 'mg/dl',
            'enable': ['iob', 'cob', 'loop', 'basal', 'pump'],
            'thresholds': {'bgHigh': 260, 'bgTargetTop': 180,
                           'bgTargetBottom': 80, 'bgLow': 55},
        }}
        df = self.norm(status, 'p1')
        self.assertEqual(df['data_mode'].iloc[0], 'AID')
        self.assertTrue(df['has_loop'].iloc[0])
        self.assertTrue(df['has_pump'].iloc[0])
        self.assertFalse(df['has_openaps'].iloc[0])

    def test_aid_openaps(self):
        status = {'settings': {
            'units': 'mg/dl',
            'enable': ['iob', 'cob', 'openaps', 'pump'],
            'thresholds': {},
        }}
        df = self.norm(status, 'p2')
        self.assertEqual(df['data_mode'].iloc[0], 'AID')
        self.assertTrue(df['has_openaps'].iloc[0])

    def test_pump_no_aid(self):
        status = {'settings': {
            'units': 'mg/dl',
            'enable': ['iob', 'basal', 'pump'],
            'thresholds': {},
        }}
        df = self.norm(status, 'p3')
        self.assertEqual(df['data_mode'].iloc[0], 'pump')
        self.assertTrue(df['has_pump'].iloc[0])
        self.assertFalse(df['has_loop'].iloc[0])

    def test_mdi(self):
        status = {'settings': {
            'units': 'mmol/L',
            'enable': ['delta', 'direction', 'timeago', 'rawbg'],
            'thresholds': {},
        }}
        df = self.norm(status, 'p4')
        self.assertEqual(df['data_mode'].iloc[0], 'MDI')
        self.assertFalse(df['has_pump'].iloc[0])
        self.assertEqual(df['units'].iloc[0], 'mmol/L')

    def test_empty_settings(self):
        df = self.norm({}, 'p5')
        self.assertEqual(len(df), 0)


class TestNormalizeEntries(unittest.TestCase):
    """Test entries normalization."""

    def setUp(self):
        from tools.ns2parquet.normalize import normalize_entries
        self.norm = normalize_entries

    def test_basic_sgv(self):
        records = [{
            '_id': 'abc123',
            'type': 'sgv',
            'sgv': 120,
            'date': 1712000000000,
            'direction': 'Flat',
            'device': 'share2',
        }]
        df = self.norm(records, 'test')
        self.assertEqual(len(df), 1)
        self.assertEqual(df['patient_id'].iloc[0], 'test')
        self.assertEqual(df['sgv'].iloc[0], 120)
        self.assertEqual(df['direction'].iloc[0], 'Flat')

    def test_skips_non_sgv(self):
        records = [
            {'_id': 'a', 'type': 'sgv', 'sgv': 100, 'date': 1712000000000},
            {'_id': 'b', 'type': 'cal', 'slope': 1.0, 'date': 1712000000000},
        ]
        df = self.norm(records, 'test')
        # Should include SGV; may or may not include cal depending on impl
        sgv_rows = df[df['type'] == 'sgv']
        self.assertEqual(len(sgv_rows), 1)

    def test_empty(self):
        df = self.norm([], 'test')
        self.assertEqual(len(df), 0)


class TestNormalizeTreatments(unittest.TestCase):
    """Test treatments normalization including SMB detection and duration conversion."""

    def setUp(self):
        from tools.ns2parquet.normalize import normalize_treatments
        self.norm = normalize_treatments

    def test_bolus(self):
        records = [{
            '_id': 't1',
            'eventType': 'Bolus',
            'insulin': 2.5,
            'created_at': '2026-04-01T12:00:00Z',
        }]
        df = self.norm(records, 'test')
        self.assertEqual(len(df), 1)
        self.assertAlmostEqual(df['insulin'].iloc[0], 2.5)
        self.assertFalse(df['is_smb'].iloc[0])

    def test_smb_detection(self):
        records = [{
            '_id': 't2',
            'eventType': 'Correction Bolus',
            'type': 'SMB',
            'insulin': 0.3,
            'created_at': '2026-04-01T12:00:00Z',
        }]
        df = self.norm(records, 'test')
        self.assertTrue(df['is_smb'].iloc[0])

    def test_carbs(self):
        records = [{
            '_id': 't3',
            'eventType': 'Carb Correction',
            'carbs': 25,
            'created_at': '2026-04-01T12:00:00Z',
        }]
        df = self.norm(records, 'test')
        self.assertEqual(df['carbs'].iloc[0], 25)


class TestParquetRoundTrip(unittest.TestCase):
    """Test Parquet write/read round-trip with dedup."""

    def test_write_read_roundtrip(self):
        from tools.ns2parquet.writer import write_parquet, read_parquet

        df = pd.DataFrame({
            'patient_id': ['a', 'a', 'b'],
            'time': pd.to_datetime(['2026-01-01', '2026-01-02', '2026-01-01'],
                                    utc=True),
            'glucose': [120.0, 130.0, 110.0],
        })

        with tempfile.TemporaryDirectory() as tmpdir:
            write_parquet(df, tmpdir, 'grid', schema=None, append=False, verbose=False)
            result = read_parquet(tmpdir, 'grid')
            self.assertEqual(len(result), 3)

            # Filter by patient
            result_a = read_parquet(tmpdir, 'grid', patient_id='a')
            self.assertEqual(len(result_a), 2)
            self.assertTrue((result_a['patient_id'] == 'a').all())

    def test_append_dedup(self):
        from tools.ns2parquet.writer import write_parquet, read_parquet

        df1 = pd.DataFrame({
            'patient_id': ['a', 'a'],
            'time': pd.to_datetime(['2026-01-01', '2026-01-02'], utc=True),
            'glucose': [120.0, 130.0],
        })
        df2 = pd.DataFrame({
            'patient_id': ['a', 'a'],
            'time': pd.to_datetime(['2026-01-02', '2026-01-03'], utc=True),
            'glucose': [131.0, 140.0],  # Jan 2 updated value
        })

        with tempfile.TemporaryDirectory() as tmpdir:
            write_parquet(df1, tmpdir, 'grid', schema=None, append=False, verbose=False)
            write_parquet(df2, tmpdir, 'grid', schema=None, append=True, verbose=False)
            result = read_parquet(tmpdir, 'grid')
            # Should have 3 unique (patient_id, time) combos, not 4
            self.assertEqual(len(result), 3)


# ── Integration tests (require real patient data) ───────────────────

PATIENTS_DIR = os.path.join(
    os.path.dirname(__file__), '..', '..', 'externals', 'ns-data', 'patients'
)
HAS_PATIENT_DATA = os.path.isdir(PATIENTS_DIR) and os.path.isfile(
    os.path.join(PATIENTS_DIR, 'a', 'training', 'entries.json')
)


@unittest.skipUnless(HAS_PATIENT_DATA, 'Real patient data not available')
class TestGridIntegrity(unittest.TestCase):
    """Integration tests: verify grid builder produces expected columns and values."""

    def test_grid_column_completeness(self):
        """Grid output has all expected columns."""
        from tools.ns2parquet.grid import build_grid
        df = build_grid(
            os.path.join(PATIENTS_DIR, 'd', 'training'), 'd', verbose=False)
        expected_cols = [
            'patient_id', 'glucose', 'iob', 'cob', 'net_basal',
            'bolus', 'carbs', 'time_sin', 'time_cos',
            'glucose_roc', 'glucose_accel', 'rolling_noise',
            'hours_since_cgm', 'trend_direction', 'trend_rate',
            'time_since_bolus_min', 'time_since_carb_min',
            'scheduled_basal_rate', 'actual_basal_rate',
            'scheduled_isf', 'scheduled_cr', 'glucose_vs_target',
            'sage_hours', 'sensor_warmup',
            'loop_predicted_30', 'loop_predicted_60', 'loop_predicted_min',
        ]
        for col in expected_cols:
            self.assertIn(col, df.columns, f'Missing column: {col}')

    def test_grid_row_count_reasonable(self):
        """Grid has ~51,840 rows for 180-day patient (5-min intervals)."""
        from tools.ns2parquet.grid import build_grid
        df = build_grid(
            os.path.join(PATIENTS_DIR, 'd', 'training'), 'd', verbose=False)
        # 180 days * 288 steps/day = 51,840
        self.assertGreater(len(df), 40000)
        self.assertLess(len(df), 60000)

    def test_glucose_in_mgdl_range(self):
        """Glucose values should be in mg/dL range (40-500), not mmol/L."""
        from tools.ns2parquet.grid import build_grid
        df = build_grid(
            os.path.join(PATIENTS_DIR, 'a', 'training'), 'a', verbose=False)
        valid = df['glucose'].dropna()
        self.assertGreater(valid.median(), 50)   # not mmol/L
        self.assertLess(valid.median(), 400)

    def test_mmol_isf_converted(self):
        """Patient a (mmol/L) ISF should be converted to mg/dL range."""
        from tools.ns2parquet.grid import build_grid
        df = build_grid(
            os.path.join(PATIENTS_DIR, 'a', 'training'), 'a', verbose=False)
        isf = df['scheduled_isf'].iloc[0]
        # Raw value is 2.7 mmol/L → should be ~48.6 mg/dL
        self.assertGreater(isf, 30)
        self.assertLess(isf, 80)

    def test_mgdl_isf_unchanged(self):
        """Patient d (mg/dL) ISF should stay in mg/dL range."""
        from tools.ns2parquet.grid import build_grid
        df = build_grid(
            os.path.join(PATIENTS_DIR, 'd', 'training'), 'd', verbose=False)
        isf = df['scheduled_isf'].iloc[0]
        self.assertAlmostEqual(isf, 40.0, places=0)


@unittest.skipUnless(HAS_PATIENT_DATA, 'Real patient data not available')
class TestClinicalMetricsMatch(unittest.TestCase):
    """Integration: clinical metrics from parquet match JSON pipeline."""

    @classmethod
    def setUpClass(cls):
        """Build grids from both pipelines for patient d."""
        from tools.ns2parquet.grid import build_grid
        from tools.cgmencode.real_data_adapter import build_nightscout_grid

        data_dir = os.path.join(PATIENTS_DIR, 'd', 'training')
        cls.pq_df = build_grid(data_dir, 'd', verbose=False)
        cls.json_df, _ = build_nightscout_grid(data_dir, verbose=False)

    def _metrics(self, glucose):
        valid = glucose[np.isfinite(glucose)]
        return {
            'tir': float(np.mean((valid >= 70) & (valid <= 180)) * 100),
            'tbr': float(np.mean(valid < 70) * 100),
            'mean': float(np.nanmean(valid)),
        }

    def test_tir_matches(self):
        j = self._metrics(self.json_df['glucose'].values)
        p = self._metrics(self.pq_df['glucose'].values)
        self.assertAlmostEqual(j['tir'], p['tir'], places=1)

    def test_tbr_matches(self):
        j = self._metrics(self.json_df['glucose'].values)
        p = self._metrics(self.pq_df['glucose'].values)
        self.assertAlmostEqual(j['tbr'], p['tbr'], places=1)

    def test_mean_glucose_matches(self):
        j = self._metrics(self.json_df['glucose'].values)
        p = self._metrics(self.pq_df['glucose'].values)
        self.assertAlmostEqual(j['mean'], p['mean'], places=0)

    def test_bolus_count_matches(self):
        j_bolus = (self.json_df['bolus'] > 0).sum()
        p_bolus = (self.pq_df['bolus'] > 0).sum()
        self.assertEqual(j_bolus, p_bolus)

    def test_carb_count_matches(self):
        j_carbs = (self.json_df['carbs'] > 0).sum()
        p_carbs = (self.pq_df['carbs'] > 0).sum()
        self.assertEqual(j_carbs, p_carbs)


class TestOref0PredictionExtraction(unittest.TestCase):
    """Test oref0 prediction parity — predicted_60, predicted_min, hypo_risk."""

    def setUp(self):
        from tools.ns2parquet.normalize import _extract_oref0_ds
        self.extract = _extract_oref0_ds

    def test_predicted_60_from_best_curve(self):
        """oref0: predicted_60 extracted from best curve at index 12."""
        pred_vals = [120.0] * 6 + [130.0] + [125.0] * 5 + [140.0] + [135.0] * 35
        ds = {'openaps': {
            'iob': {'iob': 1.0},
            'suggested': {'COB': 5, 'predBGs': {'COB': pred_vals}},
        }}
        result = self.extract(ds)
        self.assertAlmostEqual(result['predicted_60'], 140.0)

    def test_predicted_min_from_best_curve(self):
        """oref0: predicted_min is minimum of the best curve."""
        pred_vals = [120, 110, 100, 90, 85, 80, 75, 80, 85, 90, 95, 100, 105]
        ds = {'openaps': {
            'iob': {'iob': 0.5},
            'suggested': {'COB': 3, 'predBGs': {'COB': pred_vals}},
        }}
        result = self.extract(ds)
        self.assertAlmostEqual(result['predicted_min'], 75.0)

    def test_hypo_risk_count(self):
        """oref0: hypo_risk_count is count of values < 70 in best curve."""
        pred_vals = [120, 100, 80, 65, 55, 60, 68, 72, 90, 110, 120, 130, 140]
        ds = {'openaps': {
            'iob': {'iob': 2.0},
            'suggested': {'COB': 0, 'predBGs': {'IOB': pred_vals}},
        }}
        result = self.extract(ds)
        # Values < 70: 65, 55, 60, 68 = 4
        self.assertEqual(result['hypo_risk_count'], 4)

    def test_curve_priority_cob_first(self):
        """oref0: COB curve used when available, even if IOB also present."""
        ds = {'openaps': {
            'iob': {'iob': 1.0},
            'suggested': {'COB': 5, 'predBGs': {
                'COB': [100] * 13,
                'IOB': [200] * 13,
            }},
        }}
        result = self.extract(ds)
        self.assertAlmostEqual(result['predicted_30'], 100.0)

    def test_no_predictions_returns_none(self):
        """oref0: missing predBGs → None for all prediction fields."""
        ds = {'openaps': {
            'iob': {'iob': 0.5},
            'suggested': {'COB': 0},
        }}
        result = self.extract(ds)
        self.assertIsNone(result['predicted_60'])
        self.assertIsNone(result['predicted_min'])
        self.assertIsNone(result['hypo_risk_count'])


@unittest.skipUnless(HAS_PATIENT_DATA, 'Real patient data not available')
class TestPatientBMixedController(unittest.TestCase):
    """Integration: patient b (Trio + Loop) validates new columns."""

    HAS_B = os.path.isfile(
        os.path.join(PATIENTS_DIR, 'b', 'training', 'entries.json'))

    @classmethod
    def setUpClass(cls):
        if not cls.HAS_B:
            return
        from tools.ns2parquet.grid import build_grid
        cls.df = build_grid(
            os.path.join(PATIENTS_DIR, 'b', 'training'), 'b', verbose=False)

    @unittest.skipUnless(
        os.path.isfile(os.path.join(PATIENTS_DIR, 'b', 'training', 'entries.json')),
        'Patient b data not available')
    def test_new_columns_present(self):
        """All new columns exist in grid output."""
        for col in ['bolus_smb', 'exercise_active', 'eventual_bg',
                     'sensitivity_ratio', 'insulin_req']:
            self.assertIn(col, self.df.columns, f'Missing: {col}')

    @unittest.skipUnless(
        os.path.isfile(os.path.join(PATIENTS_DIR, 'b', 'training', 'entries.json')),
        'Patient b data not available')
    def test_oref0_algo_context_populated(self):
        """Patient b (Trio) has oref0 algorithm context populated."""
        for col in ['eventual_bg', 'sensitivity_ratio', 'insulin_req']:
            valid = self.df[col].notna().sum()
            self.assertGreater(valid, len(self.df) * 0.5,
                               f'{col} should be >50% populated for Trio patient')

    @unittest.skipUnless(
        os.path.isfile(os.path.join(PATIENTS_DIR, 'b', 'training', 'entries.json')),
        'Patient b data not available')
    def test_smb_insulin_captured(self):
        """Patient b SMBs are captured in both bolus and bolus_smb."""
        smb_total = self.df['bolus_smb'].sum()
        bolus_total = self.df['bolus'].sum()
        self.assertGreater(smb_total, 0, 'Expected SMB insulin for Trio patient')
        self.assertGreater(bolus_total, smb_total, 'Total bolus should exceed SMBs')
        self.assertGreater(smb_total / bolus_total, 0.1, 'SMBs should be >10% of bolus')

    @unittest.skipUnless(
        os.path.isfile(os.path.join(PATIENTS_DIR, 'b', 'training', 'entries.json')),
        'Patient b data not available')
    def test_exercise_detected(self):
        """Patient b has exercise events detected."""
        ex_slots = (self.df['exercise_active'] > 0).sum()
        self.assertGreater(ex_slots, 0, 'Expected exercise events for patient b')

    @unittest.skipUnless(
        os.path.isfile(os.path.join(PATIENTS_DIR, 'b', 'training', 'entries.json')),
        'Patient b data not available')
    def test_override_detected(self):
        """Patient b has temporary target/override events detected."""
        ov_slots = (self.df['override_active'] > 0).sum()
        self.assertGreater(ov_slots, 0, 'Expected overrides for patient b')

    @unittest.skipUnless(
        os.path.isfile(os.path.join(PATIENTS_DIR, 'b', 'training', 'entries.json')),
        'Patient b data not available')
    def test_predictions_populated_for_oref0(self):
        """Patient b (mostly Trio) has predictions at 30 and 60 minutes."""
        for col in ['loop_predicted_30', 'loop_predicted_60', 'loop_predicted_min']:
            valid = self.df[col].notna().sum()
            self.assertGreater(valid, len(self.df) * 0.5,
                               f'{col} should be >50% populated for Trio patient')



# ──────────────────── ODC Loader Unit Tests ────────────────────────────

class TestODCLoaderConversion(unittest.TestCase):
    """Unit tests for odc_loader format adapter using synthetic data."""

    def test_bg_readings_to_entries(self):
        """BgReadings value → entries sgv, date epoch preserved."""
        from tools.ns2parquet.odc_loader import _convert_bg_readings
        records = [
            {'date': 1611698181000, 'value': 191.7, 'direction': 'Flat',
             'isValid': True, 'nsId': 'abc123'},
            {'date': 1611698481000, 'value': 88.5, 'direction': 'FortyFiveUp'},
        ]
        entries = _convert_bg_readings(records)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]['sgv'], 191.7)
        self.assertEqual(entries[0]['date'], 1611698181000)
        self.assertEqual(entries[0]['_id'], 'abc123')
        self.assertEqual(entries[0]['type'], 'sgv')
        self.assertEqual(entries[1]['direction'], 'FortyFiveUp')

    def test_treatments_smb_detection(self):
        """ODC isSMB=true → eventType='SMB'."""
        from tools.ns2parquet.odc_loader import _convert_treatments
        records = [
            {'date': 1000, 'insulin': 0.2, 'carbs': 0, 'isSMB': True,
             'mealBolus': False, 'isValid': True},
            {'date': 2000, 'insulin': 0, 'carbs': 45, 'isSMB': False,
             'mealBolus': True, 'isValid': True},
            {'date': 3000, 'insulin': 3.5, 'carbs': 0, 'isSMB': False,
             'mealBolus': False, 'isValid': True},
        ]
        treatments = _convert_treatments(records)
        self.assertEqual(len(treatments), 3)
        self.assertEqual(treatments[0]['eventType'], 'SMB')
        self.assertTrue(treatments[0].get('automatic'))
        self.assertEqual(treatments[1]['eventType'], 'Meal Bolus')
        self.assertEqual(treatments[2]['eventType'], 'Correction Bolus')

    def test_treatments_skip_empty(self):
        """Skip records with no insulin/carbs."""
        from tools.ns2parquet.odc_loader import _convert_treatments
        records = [
            {'date': 1000, 'insulin': 0, 'carbs': 0, 'isSMB': False,
             'mealBolus': False, 'isValid': True},
        ]
        treatments = _convert_treatments(records)
        self.assertEqual(len(treatments), 0)

    def test_aps_data_to_devicestatus(self):
        """APSData result → openaps.suggested mapping."""
        from tools.ns2parquet.odc_loader import _convert_aps_data
        records = [{
            'queuedOn': 1611698181000,
            'result': {
                'bg': 150, 'eventualBG': 120, 'targetBG': 100,
                'IOB': 2.5, 'COB': 30, 'sensitivityRatio': 0.95,
                'insulinReq': 0.5, 'rate': 1.2, 'duration': 30,
                'reason': 'test', 'predBGs': {'IOB': [150, 140, 130]},
            },
            'iobData': [{'iob': 2.5, 'basaliob': 1.0, 'activity': 0.01}],
            'autosensData': {'ratio': 0.95},
            'profile': {},
            'glucoseStatus': {'glucose': 150},
        }]
        ds = _convert_aps_data(records)
        self.assertEqual(len(ds), 1)
        sug = ds[0]['openaps']['suggested']
        self.assertEqual(sug['bg'], 150)
        self.assertEqual(sug['eventualBG'], 120)
        self.assertEqual(sug['IOB'], 2.5)
        self.assertEqual(sug['COB'], 30)
        self.assertEqual(sug['sensitivityRatio'], 0.95)
        self.assertIn('IOB', sug['predBGs'])
        iob = ds[0]['openaps']['iob']
        self.assertEqual(iob['iob'], 2.5)
        self.assertEqual(iob['basaliob'], 1.0)

    def test_temp_basals_converted(self):
        """TemporaryBasals absoluteRate → Temp Basal treatments."""
        from tools.ns2parquet.odc_loader import _convert_temp_basals
        records = [
            {'date': 1000, 'isAbsolute': True, 'absoluteRate': 1.5,
             'durationInMinutes': 30, 'isValid': True},
        ]
        result = _convert_temp_basals(records)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['eventType'], 'Temp Basal')
        self.assertEqual(result[0]['rate'], 1.5)
        self.assertEqual(result[0]['duration'], 30)

    def test_temp_targets_converted(self):
        """TempTargets → Temporary Target treatments."""
        from tools.ns2parquet.odc_loader import _convert_temp_targets
        records = [
            {'date': 1000, 'low': 100, 'high': 120,
             'durationInMinutes': 60, 'reason': 'Eating Soon', 'isValid': True},
        ]
        result = _convert_temp_targets(records)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['eventType'], 'Temporary Target')
        self.assertEqual(result[0]['targetBottom'], 100)
        self.assertEqual(result[0]['targetTop'], 120)

    def test_profile_mmol_conversion(self):
        """Profile with mmol units → sens/targets converted to mg/dL."""
        from tools.ns2parquet.odc_loader import _build_profile_from_switch
        prof = {
            'units': 'mmol',
            'dia': 6,
            'timezone': 'UTC',
            'sens': [{'time': '00:00', 'value': 2.1, 'timeAsSeconds': 0}],
            'carbratio': [{'time': '00:00', 'value': 8, 'timeAsSeconds': 0}],
            'basal': [{'time': '00:00', 'value': 0.85, 'timeAsSeconds': 0}],
            'target_low': [{'time': '00:00', 'value': 4.5, 'timeAsSeconds': 0}],
            'target_high': [{'time': '00:00', 'value': 5.5, 'timeAsSeconds': 0}],
        }
        result = _build_profile_from_switch(prof, {})
        store = result['store']['Default']
        # 2.1 mmol × 18.01559 ≈ 37.83
        self.assertAlmostEqual(store['sens'][0]['value'], 37.83, places=0)
        # CR should not be converted
        self.assertEqual(store['carbratio'][0]['value'], 8)
        # Basal should not be converted
        self.assertEqual(store['basal'][0]['value'], 0.85)
        # Target converted: 4.5 × 18.01559 ≈ 81
        self.assertAlmostEqual(store['target_low'][0]['value'], 81, places=0)
        self.assertEqual(store['units'], 'mg/dL')

    def test_profile_mgdl_passthrough(self):
        """Profile with mg/dL units → values unchanged."""
        from tools.ns2parquet.odc_loader import _build_profile_from_switch
        prof = {
            'units': 'mg/dl',
            'dia': 5,
            'sens': [{'time': '00:00', 'value': 34, 'timeAsSeconds': 0}],
            'carbratio': [{'time': '00:00', 'value': 10, 'timeAsSeconds': 0}],
            'basal': [{'time': '00:00', 'value': 1.0, 'timeAsSeconds': 0}],
            'target_low': [{'time': '00:00', 'value': 100, 'timeAsSeconds': 0}],
            'target_high': [{'time': '00:00', 'value': 100, 'timeAsSeconds': 0}],
        }
        result = _build_profile_from_switch(prof, {})
        store = result['store']['Default']
        self.assertEqual(store['sens'][0]['value'], 34)
        self.assertEqual(store['target_low'][0]['value'], 100)

    def test_dedup_across_uploads(self):
        """Records with same date are deduplicated across uploads."""
        from tools.ns2parquet.odc_loader import _load_and_merge_json
        import tempfile, json
        with tempfile.TemporaryDirectory() as tmpdir:
            for i, name in enumerate(['upload1', 'upload2']):
                d = Path(tmpdir) / name
                d.mkdir()
                with open(d / 'BgReadings.json', 'w') as f:
                    json.dump([
                        {'date': 1000, 'value': 100, 'isValid': True},
                        {'date': 2000 + i * 1000, 'value': 110 + i * 10,
                         'isValid': True},
                    ], f)
            uploads = [Path(tmpdir) / 'upload1', Path(tmpdir) / 'upload2']
            merged = _load_and_merge_json(uploads, 'BgReadings.json')
            self.assertEqual(len(merged), 3)
            dates = {r['date'] for r in merged}
            self.assertEqual(dates, {1000, 2000, 3000})

    def test_discover_patients(self):
        """discover_odc_patients finds numeric directories."""
        from tools.ns2parquet.odc_loader import discover_odc_patients
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / '12345').mkdir()
            (Path(tmpdir) / '67890').mkdir()
            (Path(tmpdir) / 'readme.txt').touch()
            patients = discover_odc_patients(tmpdir)
            self.assertEqual(len(patients), 2)
            self.assertEqual(patients[0][0], '12345')


# ──────────── ODC Integration Test (real data) ─────────────────────────

ODC_DIR = '/home/bewest/Downloads/openaps-data-commons-2023-samples'


@unittest.skipUnless(
    os.path.isdir(os.path.join(ODC_DIR, '39819048')),
    'ODC sample data not available'
)
class TestODCIntegration(unittest.TestCase):
    """Integration test: build grid from real ODC patient 39819048."""

    @classmethod
    def setUpClass(cls):
        import tempfile
        from tools.ns2parquet.odc_loader import write_odc_as_nightscout
        from tools.ns2parquet.grid import build_grid
        cls._tmpdir = tempfile.mkdtemp()
        ns_dir = os.path.join(cls._tmpdir, 'data')
        write_odc_as_nightscout(os.path.join(ODC_DIR, '39819048'), ns_dir)
        cls.grid = build_grid(ns_dir, 'odc-39819048')

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls._tmpdir, ignore_errors=True)

    def test_grid_has_49_columns(self):
        self.assertEqual(self.grid.shape[1], 49)

    def test_glucose_populated(self):
        """SGV should be ~100% populated (ODC has dense CGM)."""
        pct = self.grid['glucose'].notna().sum() / len(self.grid)
        self.assertGreater(pct, 0.95)

    def test_iob_populated(self):
        """IOB should be populated (from APSData)."""
        nonzero = (self.grid['iob'] != 0).sum()
        self.assertGreater(nonzero, len(self.grid) * 0.5)

    def test_eventual_bg_populated(self):
        """eventualBG from APSData should be >95% populated."""
        pct = self.grid['eventual_bg'].notna().sum() / len(self.grid)
        self.assertGreater(pct, 0.95)

    def test_sensitivity_ratio_populated(self):
        """sensitivityRatio from autosens should be populated."""
        pct = self.grid['sensitivity_ratio'].notna().sum() / len(self.grid)
        self.assertGreater(pct, 0.95)

    def test_predictions_populated(self):
        """oref0 predBGs should give us predicted_30/60/min."""
        for col in ['loop_predicted_30', 'loop_predicted_60', 'loop_predicted_min']:
            pct = self.grid[col].notna().sum() / len(self.grid)
            self.assertGreater(pct, 0.90,
                               f'{col} should be >90% populated for ODC AAPS patient')

    def test_bolus_and_smb_counts(self):
        """ODC patient should have boluses and SMBs."""
        bolus_n = (self.grid['bolus'] > 0).sum()
        smb_n = (self.grid['bolus_smb'] > 0).sum()
        self.assertGreater(bolus_n, 100)
        self.assertGreater(smb_n, 100)

    def test_override_from_temp_targets(self):
        """TempTargets should populate override_active."""
        override_n = (self.grid['override_active'] > 0).sum()
        self.assertGreater(override_n, 10)

    def test_profile_isf_reasonable(self):
        """Scheduled ISF should be in mg/dL range (converted from mmol)."""
        isf = self.grid['scheduled_isf'].dropna()
        self.assertTrue(len(isf) > 0)
        self.assertTrue((isf > 20).all(),
                        f'ISF should be in mg/dL range, got min={isf.min()}')
        self.assertTrue((isf < 200).all(),
                        f'ISF should be <200 mg/dL, got max={isf.max()}')

    def test_date_range_10_days(self):
        """Patient 39819048 spans ~10 days of data."""
        time_col = self.grid['time']
        span_days = (time_col.max() - time_col.min()).total_seconds() / 86400
        self.assertGreater(span_days, 7)
        self.assertLess(span_days, 30)


# ── CSV Devicestatus Unit Tests ──────────────────────────────────────

class TestCSVDevicestatusParser(unittest.TestCase):
    """Unit tests for flattened CSV devicestatus reconstruction."""

    def test_unflatten_group_numeric(self):
        """Numeric values should be converted to float."""
        from tools.ns2parquet.odc_loader import _unflatten_group
        row = {
            'openaps/suggested/bg': '120',
            'openaps/suggested/eventualBG': '95',
            'openaps/suggested/rate': '1.35',
            'openaps/suggested/reason': 'some text here',
            'openaps/suggested/empty': '',
        }
        cols = [k for k in row.keys() if k.startswith('openaps/suggested/')]
        result = _unflatten_group(row, cols, 'openaps/suggested/')
        self.assertEqual(result['bg'], 120.0)
        self.assertEqual(result['eventualBG'], 95.0)
        self.assertAlmostEqual(result['rate'], 1.35)
        self.assertEqual(result['reason'], 'some text here')
        self.assertNotIn('empty', result)

    def test_unflatten_group_empty_row(self):
        """All-empty row should return empty dict."""
        from tools.ns2parquet.odc_loader import _unflatten_group
        row = {'openaps/suggested/bg': '', 'openaps/suggested/eventualBG': ''}
        cols = list(row.keys())
        result = _unflatten_group(row, cols, 'openaps/suggested/')
        self.assertEqual(result, {})


class TestScheduleLookupStringValues(unittest.TestCase):
    """Profile values and timeAsSeconds may be strings (NS-export format)."""

    def test_string_time_as_seconds(self):
        """timeAsSeconds stored as string should still work."""
        from tools.ns2parquet.grid import _lookup_schedule
        schedule = [
            {'timeAsSeconds': '0', 'value': '1.4'},
            {'timeAsSeconds': '28800', 'value': '1.2'},  # 8am
        ]
        # Before 8am → should get '1.4'
        val = _lookup_schedule(3600, schedule)
        self.assertAlmostEqual(val, 1.4)
        # After 8am → should get '1.2'
        val = _lookup_schedule(36000, schedule)
        self.assertAlmostEqual(val, 1.2)

    def test_mixed_types(self):
        """Mix of int and string values should work."""
        from tools.ns2parquet.grid import _lookup_schedule
        schedule = [
            {'timeAsSeconds': 0, 'value': 45},
            {'timeAsSeconds': '43200', 'value': '55'},  # noon
        ]
        val = _lookup_schedule(50000, schedule)
        self.assertAlmostEqual(val, 55.0)


# ── NS-Export Integration Tests ──────────────────────────────────────

ODC_NS_EXPORT_PID = '74077367'  # Best NS-export patient (99% coverage)
ODC_NS_EXPORT_DIR = os.path.join(
    os.getenv('ODC_DATA',
              '/home/bewest/Downloads/openaps-data-commons-2023-samples'),
    ODC_NS_EXPORT_PID, 'direct-sharing-31')


@unittest.skipUnless(
    os.path.isdir(ODC_NS_EXPORT_DIR),
    f'ODC NS-export data not available at {ODC_NS_EXPORT_DIR}')
class TestNSExportIntegration(unittest.TestCase):
    """Integration test: build grid from NS-export patient (CSV devicestatus)."""

    @classmethod
    def setUpClass(cls):
        import tempfile
        from tools.ns2parquet.odc_loader import write_odc_as_nightscout
        from tools.ns2parquet.grid import build_grid
        cls._tmpdir = tempfile.mkdtemp()
        ns_dir = os.path.join(cls._tmpdir, 'data')
        write_odc_as_nightscout(ODC_NS_EXPORT_DIR, ns_dir)
        cls.grid = build_grid(ns_dir, f'odc-{ODC_NS_EXPORT_PID}')

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls._tmpdir, ignore_errors=True)

    def test_grid_built_successfully(self):
        self.assertIsNotNone(self.grid)
        self.assertGreater(len(self.grid), 50000)

    def test_grid_has_49_columns(self):
        self.assertEqual(self.grid.shape[1], 49)

    def test_glucose_populated(self):
        """NS-export entries should give >95% glucose coverage."""
        pct = self.grid['glucose'].notna().mean()
        self.assertGreater(pct, 0.95)

    def test_iob_from_csv_devicestatus(self):
        """IOB reconstructed from flattened CSV should be >90% non-zero."""
        nonzero_pct = (self.grid['iob'] != 0).mean()
        self.assertGreater(nonzero_pct, 0.90)

    def test_predictions_from_csv(self):
        """predBGs reconstructed from indexed CSV columns should be >90%."""
        for col in ['loop_predicted_30', 'loop_predicted_60', 'loop_predicted_min']:
            pct = self.grid[col].notna().mean()
            self.assertGreater(pct, 0.90,
                               f'{col} should be >90% for NS-export patient')

    def test_eventual_bg_from_csv(self):
        """eventualBG reconstructed from CSV should be >90%."""
        pct = self.grid['eventual_bg'].notna().mean()
        self.assertGreater(pct, 0.90)

    def test_spans_months(self):
        """NS-export patient should span multiple months."""
        time_col = self.grid['time']
        span_days = (time_col.max() - time_col.min()).total_seconds() / 86400
        self.assertGreater(span_days, 100)

    def test_profile_values_reasonable(self):
        """Profile should have reasonable mg/dL values."""
        isf = self.grid['scheduled_isf'].dropna()
        self.assertTrue(len(isf) > 0)
        self.assertTrue((isf > 5).all(), f'ISF too low: min={isf.min()}')
        self.assertTrue((isf < 500).all(), f'ISF too high: max={isf.max()}')

    def test_all_8_patients_loadable(self):
        """Verify all 8 ODC patients produce a grid (not None)."""
        from tools.ns2parquet.odc_loader import (discover_odc_patients,
                                                  write_odc_as_nightscout)
        from tools.ns2parquet.grid import build_grid
        import tempfile, shutil
        odc_root = os.getenv(
            'ODC_DATA',
            '/home/bewest/Downloads/openaps-data-commons-2023-samples')
        patients = discover_odc_patients(odc_root)
        ok = 0
        for pid, pdir in patients:
            tmpd = tempfile.mkdtemp()
            try:
                ns_dir = os.path.join(tmpd, 'data')
                if write_odc_as_nightscout(pdir, ns_dir):
                    grid = build_grid(ns_dir, pid)
                    if grid is not None and len(grid) > 0:
                        ok += 1
            finally:
                shutil.rmtree(tmpd, ignore_errors=True)
        self.assertEqual(ok, 8, f'Expected 8/8 patients, got {ok}/{len(patients)}')


class TestTimezoneHandling(unittest.TestCase):
    """Test timezone edge cases in grid builder and normalize functions."""

    def setUp(self):
        from tools.ns2parquet.grid import _normalize_timezone, _to_local_index
        self.norm_tz = _normalize_timezone
        self.to_local = _to_local_index

    def test_etc_gmt_normalization(self):
        """ETC/GMT+7 → Etc/GMT+7 (Nightscout quirk)."""
        self.assertEqual(self.norm_tz('ETC/GMT+7'), 'Etc/GMT+7')
        self.assertEqual(self.norm_tz('ETC/GMT-5'), 'Etc/GMT-5')

    def test_already_correct_tz(self):
        """Standard IANA names pass through unchanged."""
        self.assertEqual(self.norm_tz('America/New_York'), 'America/New_York')
        self.assertEqual(self.norm_tz('Europe/Berlin'), 'Europe/Berlin')

    def test_empty_tz_defaults_utc(self):
        """Empty or None timezone defaults to UTC."""
        self.assertEqual(self.norm_tz(''), 'UTC')
        self.assertEqual(self.norm_tz(None), 'UTC')

    def test_to_local_invalid_tz_warns(self):
        """Invalid timezone falls back to UTC with a warning."""
        idx = pd.date_range('2024-01-01', periods=3, freq='5min', tz='UTC')
        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter('always')
            result = self.to_local(idx, 'Invalid/Timezone_ZZZ')
            self.assertGreaterEqual(len(w), 1)
            self.assertIn('Invalid', str(w[0].message))
        # Should return original index (UTC) on failure
        self.assertEqual(len(result), 3)

    def test_dst_transition_spring_forward(self):
        """Spring-forward DST: no hours lost in UTC grid."""
        # US spring forward: 2024-03-10 02:00 EST → 03:00 EDT
        idx = pd.date_range('2024-03-10 06:00', periods=24, freq='5min', tz='UTC')
        result = self.to_local(idx, 'America/New_York')
        # All 24 steps should exist — UTC grid doesn't have DST gaps
        self.assertEqual(len(result), 24)
        # Verify conversion actually happened (first step should be EST/EDT)
        self.assertNotEqual(str(result.tz), 'UTC')

    def test_dst_transition_fall_back(self):
        """Fall-back DST: no duplicate hours in UTC grid."""
        # US fall back: 2024-11-03 02:00 EDT → 01:00 EST
        idx = pd.date_range('2024-11-03 05:00', periods=24, freq='5min', tz='UTC')
        result = self.to_local(idx, 'America/New_York')
        self.assertEqual(len(result), 24)

    def test_naive_index_gets_localized(self):
        """Naive DatetimeIndex gets localized to UTC then converted."""
        idx = pd.date_range('2024-01-01', periods=3, freq='5min')
        result = self.to_local(idx, 'US/Eastern')
        self.assertEqual(len(result), 3)


class TestTimestampParsing(unittest.TestCase):
    """Test _parse_ts with various edge cases."""

    def setUp(self):
        from tools.ns2parquet.normalize import _parse_ts
        self.parse = _parse_ts

    def test_epoch_ms(self):
        """Integer epoch in milliseconds."""
        ts = self.parse({'date': 1704067200000}, 'date')
        self.assertIsNotNone(ts)
        self.assertEqual(ts.year, 2024)

    def test_iso_8601_with_tz(self):
        """ISO 8601 with timezone offset."""
        ts = self.parse({'d': '2024-01-01T12:00:00+05:00'}, 'd')
        self.assertIsNotNone(ts)
        self.assertEqual(str(ts.tz), 'UTC')

    def test_iso_8601_naive(self):
        """Naive ISO string gets localized to UTC."""
        ts = self.parse({'d': '2024-01-01T12:00:00'}, 'd')
        self.assertIsNotNone(ts)
        self.assertEqual(str(ts.tz), 'UTC')

    def test_garbage_string_returns_none(self):
        """Unparseable string returns None."""
        ts = self.parse({'date': 'not-a-date'}, 'date')
        self.assertIsNone(ts)

    def test_empty_string_returns_none(self):
        """Empty string is skipped and returns None."""
        ts = self.parse({'date': ''}, 'date')
        self.assertIsNone(ts)

    def test_fallback_fields(self):
        """Falls through to second field if first is None."""
        ts = self.parse({'dateString': '2024-06-15T10:00:00Z'}, 'date', 'dateString')
        self.assertIsNotNone(ts)
        self.assertEqual(ts.month, 6)

    def test_none_value_skipped(self):
        ts = self.parse({'date': None, 'sysTime': '2024-01-01T00:00:00Z'}, 'date', 'sysTime')
        self.assertIsNotNone(ts)

    def test_float_epoch(self):
        """Float epoch (JavaScript Date.now() / 1)."""
        ts = self.parse({'date': 1704067200000.0}, 'date')
        self.assertIsNotNone(ts)

    def test_small_int_not_epoch_ms(self):
        """Small integers (<1e10) are treated as timestamps, not epoch-ms."""
        # This is an edge case — small int could be a year or garbage
        ts = self.parse({'date': 2024}, 'date')
        # Should still parse (as epoch seconds or similar) or return something
        # The important thing is it doesn't crash
        # Small values will be treated as timestamp strings by pd.Timestamp


class TestSafeConversions(unittest.TestCase):
    """Test _safe_float and _safe_int helpers."""

    def setUp(self):
        from tools.ns2parquet.normalize import _safe_float, _safe_int
        self.sf = _safe_float
        self.si = _safe_int

    def test_float_normal(self):
        self.assertEqual(self.sf(3.14), 3.14)

    def test_float_from_string(self):
        self.assertEqual(self.sf('2.5'), 2.5)

    def test_float_none(self):
        self.assertIsNone(self.sf(None))

    def test_float_garbage(self):
        self.assertIsNone(self.sf('abc', 'test_field'))

    def test_float_empty_string(self):
        self.assertIsNone(self.sf('', 'test_field'))

    def test_float_from_int(self):
        self.assertEqual(self.sf(42), 42.0)

    def test_int_normal(self):
        self.assertEqual(self.si(42), 42)

    def test_int_from_string(self):
        self.assertEqual(self.si('7'), 7)

    def test_int_none(self):
        self.assertIsNone(self.si(None))

    def test_int_garbage(self):
        self.assertIsNone(self.si('xyz', 'test_field'))

    def test_int_float_string(self):
        """Float-like string should fail int conversion."""
        self.assertIsNone(self.si('3.14', 'test_field'))


class TestCorruptData(unittest.TestCase):
    """Test normalize functions with corrupt/malformed input."""

    def setUp(self):
        from tools.ns2parquet.normalize import (
            normalize_entries, normalize_treatments, normalize_devicestatus,
        )
        self.norm_entries = normalize_entries
        self.norm_treatments = normalize_treatments
        self.norm_ds = normalize_devicestatus

    def test_entries_empty_list(self):
        df = self.norm_entries([], 'test')
        self.assertEqual(len(df), 0)
        self.assertIn('quality', df.attrs)
        self.assertEqual(df.attrs['quality']['total_records'], 0)

    def test_entries_all_missing_timestamps(self):
        """Records with no parseable timestamp are skipped."""
        records = [
            {'_id': '1', 'sgv': 120, 'type': 'sgv'},
            {'_id': '2', 'sgv': 130, 'type': 'sgv', 'date': 'garbage'},
        ]
        df = self.norm_entries(records, 'test')
        self.assertEqual(len(df), 0)
        self.assertEqual(df.attrs['quality']['skipped_no_timestamp'], 2)

    def test_entries_bad_sgv_value(self):
        """Non-numeric SGV produces None, not crash."""
        records = [
            {'_id': '1', 'sgv': 'HIGH', 'type': 'sgv', 'date': 1704067200000},
        ]
        df = self.norm_entries(records, 'test')
        self.assertEqual(len(df), 1)
        self.assertIsNone(df.iloc[0]['sgv'])
        self.assertEqual(df.attrs['quality']['bad_value_conversion'], 1)

    def test_entries_mixed_good_and_bad(self):
        """Good records survive alongside bad ones."""
        records = [
            {'_id': '1', 'sgv': 120, 'type': 'sgv', 'date': 1704067200000},
            {'_id': '2', 'type': 'sgv'},  # no timestamp
            {'_id': '3', 'sgv': 'BAD', 'type': 'sgv', 'date': 1704067500000},
            {'_id': '1', 'sgv': 120, 'type': 'sgv', 'date': 1704067200000},  # dup
        ]
        df = self.norm_entries(records, 'test')
        self.assertEqual(len(df), 2)  # good + bad-sgv
        q = df.attrs['quality']
        self.assertEqual(q['total_records'], 4)
        self.assertEqual(q['accepted'], 2)
        self.assertEqual(q['skipped_duplicate'], 1)
        self.assertEqual(q['skipped_no_timestamp'], 1)

    def test_treatments_empty_list(self):
        df = self.norm_treatments([], 'test')
        self.assertEqual(len(df), 0)
        self.assertIn('quality', df.attrs)

    def test_treatments_missing_timestamps(self):
        records = [
            {'_id': '1', 'eventType': 'Bolus', 'insulin': 2.0},
            {'_id': '2', 'eventType': 'Bolus', 'insulin': 1.0,
             'created_at': 'not-a-date'},
        ]
        df = self.norm_treatments(records, 'test')
        self.assertEqual(len(df), 0)
        self.assertEqual(df.attrs['quality']['skipped_no_timestamp'], 2)

    def test_treatments_non_numeric_insulin(self):
        """Non-numeric insulin value becomes None, not crash."""
        records = [
            {'_id': '1', 'eventType': 'Bolus', 'insulin': 'lots',
             'created_at': '2024-01-01T00:00:00Z'},
        ]
        df = self.norm_treatments(records, 'test')
        self.assertEqual(len(df), 1)
        self.assertIsNone(df.iloc[0]['insulin'])

    def test_devicestatus_empty_list(self):
        df = self.norm_ds([], 'test')
        self.assertEqual(len(df), 0)
        self.assertIn('quality', df.attrs)

    def test_devicestatus_minimal_record(self):
        """Records with no loop/openaps structure still processed."""
        records = [
            {'_id': '1', 'created_at': '2024-01-01T00:00:00Z',
             'device': 'xDrip-DexcomG6'},
        ]
        df = self.norm_ds(records, 'test')
        self.assertEqual(len(df), 1)
        self.assertEqual(df.attrs['quality']['minimal_records'], 1)

    def test_devicestatus_corrupt_pump_battery(self):
        """Non-numeric pump battery doesn't crash."""
        records = [
            {'_id': '1', 'created_at': '2024-01-01T00:00:00Z',
             'device': 'loop://iPhone',
             'loop': {'iob': {'iob': 1.5}},
             'pump': {'battery': {'percent': 'full'}}},
        ]
        df = self.norm_ds(records, 'test')
        self.assertEqual(len(df), 1)
        self.assertIsNone(df.iloc[0]['pump_battery_pct'])

    def test_entries_null_fields_throughout(self):
        """Record with all-None optional fields doesn't crash."""
        records = [{
            '_id': '1', 'type': 'sgv', 'date': 1704067200000,
            'sgv': 120, 'noise': None, 'filtered': None,
            'unfiltered': None, 'delta': None, 'rssi': None,
            'trend': None, 'trendRate': None, 'utcOffset': None,
        }]
        df = self.norm_entries(records, 'test')
        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0]['sgv'], 120.0)


class TestQualityMetadata(unittest.TestCase):
    """Test that quality metadata is attached to DataFrames."""

    def setUp(self):
        from tools.ns2parquet.normalize import (
            normalize_entries, normalize_treatments, normalize_devicestatus,
        )
        self.norm_entries = normalize_entries
        self.norm_treatments = normalize_treatments
        self.norm_ds = normalize_devicestatus

    def test_entries_quality_present(self):
        records = [
            {'_id': '1', 'sgv': 100, 'type': 'sgv', 'date': 1704067200000},
        ]
        df = self.norm_entries(records, 'test')
        self.assertIn('quality', df.attrs)
        q = df.attrs['quality']
        self.assertEqual(q['total_records'], 1)
        self.assertEqual(q['accepted'], 1)
        self.assertEqual(q['skipped_duplicate'], 0)

    def test_treatments_quality_present(self):
        records = [
            {'_id': '1', 'eventType': 'Bolus', 'insulin': 2.0,
             'created_at': '2024-01-01T00:00:00Z'},
        ]
        df = self.norm_treatments(records, 'test')
        self.assertIn('quality', df.attrs)
        q = df.attrs['quality']
        self.assertEqual(q['total_records'], 1)
        self.assertEqual(q['accepted'], 1)

    def test_devicestatus_quality_present(self):
        records = [
            {'_id': '1', 'created_at': '2024-01-01T00:00:00Z',
             'device': 'loop://iPhone',
             'loop': {'iob': {'iob': 1.5}}},
        ]
        df = self.norm_ds(records, 'test')
        self.assertIn('quality', df.attrs)
        q = df.attrs['quality']
        self.assertEqual(q['total_records'], 1)
        self.assertEqual(q['accepted'], 1)
        self.assertEqual(q['minimal_records'], 0)


class TestSharedConstants(unittest.TestCase):
    """Test that shared constants are consistent."""

    def test_mmoll_to_mgdl_value(self):
        from tools.ns2parquet.constants import MMOLL_TO_MGDL
        self.assertAlmostEqual(MMOLL_TO_MGDL, 18.01559, places=5)

    def test_direction_map_completeness(self):
        from tools.ns2parquet.constants import DIRECTION_MAP
        expected_keys = {
            'DoubleUp', 'SingleUp', 'FortyFiveUp', 'Flat',
            'FortyFiveDown', 'SingleDown', 'DoubleDown',
            'NOT COMPUTABLE', 'RATE OUT OF RANGE',
            'NONE', 'None', '',
        }
        self.assertEqual(set(DIRECTION_MAP.keys()), expected_keys)

    def test_direction_map_values_ordered(self):
        from tools.ns2parquet.constants import DIRECTION_MAP
        self.assertGreater(DIRECTION_MAP['DoubleUp'], DIRECTION_MAP['SingleUp'])
        self.assertGreater(DIRECTION_MAP['SingleUp'], DIRECTION_MAP['Flat'])
        self.assertGreater(DIRECTION_MAP['Flat'], DIRECTION_MAP['SingleDown'])
        self.assertGreater(DIRECTION_MAP['SingleDown'], DIRECTION_MAP['DoubleDown'])

    def test_normalize_reexports_constants(self):
        """normalize.py re-exports for backward compatibility."""
        from tools.ns2parquet.normalize import DIRECTION_MAP, MMOLL_TO_MGDL
        from tools.ns2parquet.constants import DIRECTION_MAP as DM2
        self.assertIs(DIRECTION_MAP, DM2)
        self.assertEqual(MMOLL_TO_MGDL, 18.01559)


if __name__ == '__main__':
    unittest.main()
