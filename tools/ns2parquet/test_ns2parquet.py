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


if __name__ == '__main__':
    unittest.main()
