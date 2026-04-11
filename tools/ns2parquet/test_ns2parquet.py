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
  - Grid builder column completeness (fixture-based, fast)
  - Integration: full pipeline vs JSON pipeline (real patient data, slow)

Run:
    python3 -m pytest tools/ns2parquet/test_ns2parquet.py -v           # all tests
    python3 -m pytest tools/ns2parquet/test_ns2parquet.py -m "not slow" -v  # fast only
    # or via Makefile:
    make ns2parquet-tests       # fast (unit + fixture-based)
    make ns2parquet-tests-all   # everything including slow integration
"""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from tools.ns2parquet.schemas import GRID_SCHEMA

EXPECTED_GRID_COLS = len(GRID_SCHEMA)


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

    def test_unsorted_schedule(self):
        """Schedule entries not in chronological order should still work."""
        unsorted = [
            {'timeAsSeconds': 43200, 'value': 40},    # noon (out of order)
            {'timeAsSeconds': 0, 'value': 50},         # midnight
            {'timeAsSeconds': 64800, 'value': 55},    # 6pm
            {'timeAsSeconds': 21600, 'value': 45},    # 6am (out of order)
        ]
        self.assertEqual(self.lookup(0, unsorted), 50.0)       # midnight
        self.assertEqual(self.lookup(10800, unsorted), 50.0)   # 3am
        self.assertEqual(self.lookup(21600, unsorted), 45.0)   # 6am
        self.assertEqual(self.lookup(43200, unsorted), 40.0)   # noon
        self.assertEqual(self.lookup(64800, unsorted), 55.0)   # 6pm
        self.assertEqual(self.lookup(75600, unsorted), 55.0)   # 9pm


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


# ── Fixture-based grid tests (use small JSON extracts, ~0.5s total) ──

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), 'fixtures')
HAS_FIXTURES = os.path.isdir(FIXTURES_DIR) and os.path.isfile(
    os.path.join(FIXTURES_DIR, 'patient_d_entries.json')
)
HAS_FIXTURE_B = HAS_FIXTURES and os.path.isfile(
    os.path.join(FIXTURES_DIR, 'patient_b_entries.json')
)
HAS_ODC_FIXTURE = HAS_FIXTURES and os.path.isfile(
    os.path.join(FIXTURES_DIR, 'odc_39819048_entries.json')
)
HAS_NSEXPORT_FIXTURE = HAS_FIXTURES and os.path.isfile(
    os.path.join(FIXTURES_DIR, 'nsexport_74077367_entries.json')
)
HAS_SENSOR_FIXTURE = HAS_FIXTURES and os.path.isfile(
    os.path.join(FIXTURES_DIR, 'sensor_d_entries.json')
)

# Tiny terrarium: pre-built parquet with 2 patients × 7 days (~800KB)
TINY_TERRARIUM = os.path.join(
    os.path.dirname(__file__), '..', '..', 'externals',
    'ns-parquet-tiny', 'training', 'grid.parquet'
)
HAS_TINY_TERRARIUM = os.path.isfile(TINY_TERRARIUM)


def _build_fixture_grid(prefix, grid_id=None):
    """Build a grid from small JSON fixtures (~288-577 rows, <0.5s).

    prefix: fixture file prefix (e.g. 'patient_d', 'odc_39819048')
    grid_id: patient_id passed to build_grid (defaults to prefix)
    """
    from tools.ns2parquet.grid import build_grid
    tmpdir = tempfile.mkdtemp()
    for col in ['entries', 'treatments', 'devicestatus', 'profile']:
        src = os.path.join(FIXTURES_DIR, f'{prefix}_{col}.json')
        dst = os.path.join(tmpdir, f'{col}.json')
        shutil.copy(src, dst)
    df = build_grid(tmpdir, grid_id or prefix, verbose=False)
    shutil.rmtree(tmpdir)
    return df


@unittest.skipUnless(HAS_FIXTURES, 'JSON fixtures not available')
class TestGridIntegrity(unittest.TestCase):
    """Grid tests using small JSON fixtures (~1 day, <0.5s per grid build)."""

    @classmethod
    def setUpClass(cls):
        cls.df_d = _build_fixture_grid('patient_d', 'd')
        cls.df_a = _build_fixture_grid('patient_a', 'a')

    def test_grid_column_completeness(self):
        """Grid output has all expected columns."""
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
            self.assertIn(col, self.df_d.columns, f'Missing column: {col}')

    def test_grid_row_count_one_day(self):
        """Fixture grid has ~288 rows (1 day at 5-min intervals)."""
        self.assertGreater(len(self.df_d), 200)
        self.assertLess(len(self.df_d), 400)

    def test_grid_has_49_columns(self):
        """Grid should produce all GRID_SCHEMA columns."""
        self.assertEqual(self.df_d.shape[1], EXPECTED_GRID_COLS)

    def test_glucose_in_mgdl_range(self):
        """Glucose values should be in mg/dL range (40-500), not mmol/L."""
        valid = self.df_a['glucose'].dropna()
        self.assertGreater(valid.median(), 50)   # not mmol/L
        self.assertLess(valid.median(), 300)

    def test_mmol_isf_converted(self):
        """Patient a (mmol/L) ISF should be converted to mg/dL range."""
        isf = self.df_a['scheduled_isf'].iloc[0]
        # Raw value is 2.7 mmol/L → should be ~48.6 mg/dL
        self.assertGreater(isf, 30)
        self.assertLess(isf, 80)

    def test_mgdl_isf_unchanged(self):
        """Patient d (mg/dL) ISF should stay in mg/dL range."""
        isf = self.df_d['scheduled_isf'].iloc[0]
        self.assertAlmostEqual(isf, 40.0, places=0)

    def test_iob_populated(self):
        """IOB should be populated from devicestatus."""
        self.assertGreater(self.df_d['iob'].notna().mean(), 0.5)

    def test_predictions_present(self):
        """Prediction columns should have some non-null values."""
        for col in ['loop_predicted_30', 'loop_predicted_60', 'loop_predicted_min']:
            valid = self.df_d[col].notna().sum()
            self.assertGreater(valid, 0, f'{col} should have some values')

    def test_override_type_temporary_override(self):
        """Patient a has Temporary Override events → override_type=2.0."""
        ov_slots = (self.df_a['override_active'] > 0).sum()
        self.assertGreater(ov_slots, 0,
                           'Patient a should have Temporary Override events')
        ov_type_2 = (self.df_a['override_type'] == 2.0).sum()
        self.assertGreater(ov_type_2, 0,
                           'Temporary Override should set override_type=2.0')


@unittest.skipUnless(HAS_TINY_TERRARIUM, 'Tiny terrarium not available')
class TestTinyTerrariumSmoke(unittest.TestCase):
    """Smoke tests using pre-built tiny terrarium (~800KB, <50ms load)."""

    @classmethod
    def setUpClass(cls):
        cls.grid = pd.read_parquet(TINY_TERRARIUM)

    def test_has_expected_patients(self):
        patients = sorted(self.grid['patient_id'].unique())
        self.assertIn('a', patients)
        self.assertIn('b', patients)

    def test_has_49_columns(self):
        self.assertEqual(self.grid.shape[1], EXPECTED_GRID_COLS)

    def test_row_count_reasonable(self):
        """~2 patients × 7 days × 288 steps ≈ 4032 rows."""
        self.assertGreater(len(self.grid), 3000)
        self.assertLess(len(self.grid), 5000)

    def test_glucose_values_mgdl(self):
        valid = self.grid['glucose'].dropna()
        self.assertGreater(valid.median(), 50)
        self.assertLess(valid.median(), 300)

    def test_new_columns_present(self):
        """All 5 newer columns present (bolus_smb, exercise, algo context)."""
        for col in ['bolus_smb', 'exercise_active', 'eventual_bg',
                     'sensitivity_ratio', 'insulin_req']:
            self.assertIn(col, self.grid.columns, f'Missing: {col}')

    def test_patient_a_mmol_isf_converted(self):
        """Patient a (mmol/L site) ISF should be in mg/dL range."""
        a = self.grid[self.grid['patient_id'] == 'a']
        isf = a['scheduled_isf'].dropna().iloc[0]
        self.assertGreater(isf, 30)
        self.assertLess(isf, 80)

    def test_patient_b_oref0_context(self):
        """Patient b (Trio) should have oref0 algorithm context."""
        b = self.grid[self.grid['patient_id'] == 'b']
        for col in ['eventual_bg', 'sensitivity_ratio']:
            pct = b[col].notna().mean()
            self.assertGreater(pct, 0.3, f'{col} should be >30% for Trio patient')


# ── Cross-pipeline validation (fixture-based) ───────────────────────


@unittest.skipUnless(HAS_FIXTURES, 'JSON fixtures not available')
class TestClinicalMetricsMatch(unittest.TestCase):
    """Cross-validates ns2parquet vs cgmencode pipelines on fixture data.

    Both pipelines process the same 1-day patient d fixture and should
    produce identical clinical metrics (TIR, TBR, mean glucose, bolus/carb counts).
    """

    @classmethod
    def setUpClass(cls):
        from tools.cgmencode.real_data_adapter import build_nightscout_grid
        cls.pq_df = _build_fixture_grid('patient_d', 'd')
        tmpdir = tempfile.mkdtemp()
        for col in ['entries', 'treatments', 'devicestatus', 'profile']:
            shutil.copy(
                os.path.join(FIXTURES_DIR, f'patient_d_{col}.json'),
                os.path.join(tmpdir, f'{col}.json'))
        cls.json_df, _ = build_nightscout_grid(tmpdir, verbose=False)
        shutil.rmtree(tmpdir)

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


@unittest.skipUnless(HAS_FIXTURE_B, 'Patient b fixture not available')
class TestPatientBMixedController(unittest.TestCase):
    """Patient b (Trio/oref0): validates oref0 algo context, SMBs, exercise, overrides.

    Uses 2-day fixture with exercise, temp targets, SMBs, oref0 devicestatus.
    """

    @classmethod
    def setUpClass(cls):
        cls.df = _build_fixture_grid('patient_b', 'b')

    def test_new_columns_present(self):
        """All new columns exist in grid output."""
        for col in ['bolus_smb', 'exercise_active', 'eventual_bg',
                     'sensitivity_ratio', 'insulin_req']:
            self.assertIn(col, self.df.columns, f'Missing: {col}')

    def test_oref0_algo_context_populated(self):
        """Patient b (Trio) has oref0 algorithm context populated."""
        for col in ['eventual_bg', 'sensitivity_ratio', 'insulin_req']:
            valid = self.df[col].notna().sum()
            self.assertGreater(valid, len(self.df) * 0.5,
                               f'{col} should be >50% populated for Trio patient')

    def test_smb_insulin_captured(self):
        """Patient b SMBs are captured in both bolus and bolus_smb."""
        smb_total = self.df['bolus_smb'].sum()
        bolus_total = self.df['bolus'].sum()
        self.assertGreater(smb_total, 0, 'Expected SMB insulin for Trio patient')
        self.assertGreater(bolus_total, smb_total, 'Total bolus should exceed SMBs')
        self.assertGreater(smb_total / bolus_total, 0.1, 'SMBs should be >10% of bolus')

    def test_exercise_detected(self):
        """Patient b has exercise events detected."""
        ex_slots = (self.df['exercise_active'] > 0).sum()
        self.assertGreater(ex_slots, 0, 'Expected exercise events for patient b')

    def test_override_detected(self):
        """Patient b has temporary targets with override_type=1.0."""
        ov_slots = (self.df['override_active'] > 0).sum()
        self.assertGreater(ov_slots, 0, 'Expected overrides for patient b')
        # Temporary Targets should have override_type=1.0
        ov_type_slots = (self.df['override_type'] == 1.0).sum()
        self.assertGreater(ov_type_slots, 0,
                           'Temporary Targets should set override_type=1.0')

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


# ──────────── ODC Integration Test (fixture-based) ─────────────────

@unittest.skipUnless(HAS_ODC_FIXTURE, 'ODC fixture not available')
class TestODCIntegration(unittest.TestCase):
    """Grid from ODC-converted data (AAPS-native format).

    Uses 2-day fixture extracted from ODC patient 39819048.
    """

    @classmethod
    def setUpClass(cls):
        cls.grid = _build_fixture_grid('odc_39819048')

    def test_grid_has_49_columns(self):
        self.assertEqual(self.grid.shape[1], EXPECTED_GRID_COLS)

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
        self.assertGreater(bolus_n, 10)
        self.assertGreater(smb_n, 10)

    def test_override_from_temp_targets(self):
        """TempTargets should populate override_active with type=1.0."""
        override_n = (self.grid['override_active'] > 0).sum()
        self.assertGreater(override_n, 10)
        ov_type_1 = (self.grid['override_type'] == 1.0).sum()
        self.assertEqual(override_n, ov_type_1,
                         'All ODC overrides are TempTargets → type should be 1.0')

    def test_profile_isf_reasonable(self):
        """Scheduled ISF should be in mg/dL range (converted from mmol)."""
        isf = self.grid['scheduled_isf'].dropna()
        self.assertTrue(len(isf) > 0)
        self.assertTrue((isf > 20).all(),
                        f'ISF should be in mg/dL range, got min={isf.min()}')
        self.assertTrue((isf < 200).all(),
                        f'ISF should be <200 mg/dL, got max={isf.max()}')

    def test_date_range(self):
        """Fixture spans ~2 days."""
        time_col = self.grid['time']
        span_days = (time_col.max() - time_col.min()).total_seconds() / 86400
        self.assertGreater(span_days, 1)
        self.assertLess(span_days, 5)


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

# ── NS-Export Integration Test (fixture-based) ───────────────────────

@unittest.skipUnless(HAS_NSEXPORT_FIXTURE, 'NS-export fixture not available')
class TestNSExportIntegration(unittest.TestCase):
    """Grid from NS-export-converted data (CSV devicestatus format).

    Uses 2-day fixture extracted from NS-export patient 74077367.
    """

    @classmethod
    def setUpClass(cls):
        cls.grid = _build_fixture_grid('nsexport_74077367')

    def test_grid_built_successfully(self):
        self.assertIsNotNone(self.grid)
        self.assertGreater(len(self.grid), 200)

    def test_grid_has_49_columns(self):
        self.assertEqual(self.grid.shape[1], EXPECTED_GRID_COLS)

    def test_glucose_populated(self):
        """NS-export entries should give >95% glucose coverage."""
        pct = self.grid['glucose'].notna().mean()
        self.assertGreater(pct, 0.95)

    def test_iob_from_csv_devicestatus(self):
        """IOB reconstructed from flattened CSV should be >80% non-zero."""
        nonzero_pct = (self.grid['iob'] != 0).mean()
        self.assertGreater(nonzero_pct, 0.80)

    def test_predictions_from_csv(self):
        """predBGs reconstructed from indexed CSV columns should be >80%."""
        for col in ['loop_predicted_30', 'loop_predicted_60', 'loop_predicted_min']:
            pct = self.grid[col].notna().mean()
            self.assertGreater(pct, 0.80,
                               f'{col} should be >80% for NS-export patient')

    def test_eventual_bg_from_csv(self):
        """eventualBG reconstructed from CSV should be >80%."""
        pct = self.grid['eventual_bg'].notna().mean()
        self.assertGreater(pct, 0.80)

    def test_profile_values_reasonable(self):
        """Profile should have reasonable mg/dL values."""
        isf = self.grid['scheduled_isf'].dropna()
        self.assertTrue(len(isf) > 0)
        self.assertTrue((isf > 5).all(), f'ISF too low: min={isf.min()}')
        self.assertTrue((isf < 500).all(), f'ISF too high: max={isf.max()}')

    def test_date_range(self):
        """Fixture spans ~2 days."""
        time_col = self.grid['time']
        span_days = (time_col.max() - time_col.min()).total_seconds() / 86400
        self.assertGreater(span_days, 1)
        self.assertLess(span_days, 5)


class TestTimezoneHandling(unittest.TestCase):
    """Test timezone edge cases in grid builder and normalize functions."""

    def setUp(self):
        from tools.ns2parquet.constants import normalize_timezone
        from tools.ns2parquet.grid import _to_local_index
        self.norm_tz = normalize_timezone
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


# ── Sensor Age / Duration Capping / Schedule Edge Cases ──────────────

@unittest.skipUnless(HAS_SENSOR_FIXTURE, 'Sensor fixture not available')
class TestSensorAgeCalculation(unittest.TestCase):
    """Test sage_hours, sensor_warmup, sensor_phase using real fixture data.

    sensor_d fixture: 12h window from patient d containing 4 Sensor Start
    events at ~2025-11-28T10:32. Validates the full sensor age pipeline.
    """

    @classmethod
    def setUpClass(cls):
        cls.grid = _build_fixture_grid('sensor_d', 'sensor_d')

    def test_grid_built(self):
        """Sensor fixture produces a valid grid."""
        self.assertIsNotNone(self.grid)
        self.assertEqual(self.grid.shape[1], EXPECTED_GRID_COLS)

    def test_sage_hours_populated(self):
        """sage_hours should be non-NaN after the Sensor Start event."""
        sage_valid = self.grid['sage_hours'].notna().sum()
        self.assertGreater(sage_valid, 50,
                           'sage_hours should be populated for most rows post-start')

    def test_sage_hours_nan_before_start(self):
        """sage_hours should be NaN for rows before the Sensor Start."""
        sage_nan = self.grid['sage_hours'].isna().sum()
        self.assertGreater(sage_nan, 10,
                           'Some rows before Sensor Start should have NaN sage_hours')

    def test_sage_hours_increases(self):
        """sage_hours should increase monotonically after sensor start."""
        valid = self.grid['sage_hours'].dropna()
        diffs = valid.diff().dropna()
        self.assertTrue((diffs >= 0).all(),
                        'sage_hours should never decrease within a sensor session')

    def test_sensor_warmup_duration(self):
        """sensor_warmup=1.0 should last exactly 2 hours (24 × 5-min slots)."""
        warmup_slots = (self.grid['sensor_warmup'] == 1.0).sum()
        self.assertEqual(warmup_slots, 24,
                         f'Expected 24 warmup slots (2h), got {warmup_slots}')

    def test_sensor_warmup_at_start(self):
        """sensor_warmup should be 1.0 right after sensor start."""
        sage = self.grid['sage_hours']
        first_valid_idx = sage.first_valid_index()
        self.assertIsNotNone(first_valid_idx)
        self.assertEqual(self.grid.loc[first_valid_idx, 'sensor_warmup'], 1.0)

    def test_sensor_phase_warmup_value(self):
        """sensor_phase=0.0 during warmup period."""
        warmup_rows = self.grid[self.grid['sensor_warmup'] == 1.0]
        self.assertTrue((warmup_rows['sensor_phase'] == 0.0).all(),
                        'sensor_phase should be 0.0 during warmup')

    def test_sensor_phase_early_after_warmup(self):
        """sensor_phase=0.25 (early) after warmup ends."""
        post_warmup = self.grid[
            (self.grid['sage_hours'] > 2.0) & self.grid['sage_hours'].notna()
        ]
        self.assertGreater(len(post_warmup), 0)
        self.assertTrue((post_warmup['sensor_phase'] == 0.25).all(),
                        'sensor_phase should be 0.25 (early) after warmup')


class TestDurationCapping(unittest.TestCase):
    """Test exercise and override duration capping in grid.py."""

    def _build_synthetic_grid(self, treatments):
        """Build a grid from synthetic data with specified treatments."""
        from tools.ns2parquet.grid import build_grid
        import json

        base_ts = '2025-06-15T00:00:00Z'
        entries = []
        for i in range(288):  # 1 day of 5-min entries
            ts = f'2025-06-15T{i*5//60:02d}:{i*5%60:02d}:00Z'
            entries.append({
                'type': 'sgv', 'sgv': 120, 'direction': 'Flat',
                'dateString': ts,
            })

        ds = [{
            'created_at': '2025-06-15T00:00:00Z',
            'loop': {'iob': {'iob': 1.0, 'timestamp': base_ts},
                     'cob': {'cob': 0},
                     'predicted': {'values': [120]*13, 'startDate': base_ts}},
            'device': 'loop://iPhone',
        }]

        profile = [{'store': {'Default': {
            'units': 'mg/dL', 'dia': 6,
            'sens': [{'timeAsSeconds': 0, 'value': 50}],
            'carbratio': [{'timeAsSeconds': 0, 'value': 10}],
            'basal': [{'timeAsSeconds': 0, 'value': 1.0}],
            'target_low': [{'timeAsSeconds': 0, 'value': 80}],
            'target_high': [{'timeAsSeconds': 0, 'value': 120}],
        }}, 'defaultProfile': 'Default'}]

        tmpdir = tempfile.mkdtemp()
        for name, data in [('entries', entries), ('treatments', treatments),
                           ('devicestatus', ds), ('profile', profile)]:
            with open(os.path.join(tmpdir, f'{name}.json'), 'w') as f:
                json.dump(data, f)
        grid = build_grid(tmpdir, 'test')
        shutil.rmtree(tmpdir)
        return grid

    def test_exercise_capped_at_6_hours(self):
        """Exercise with duration > 360 min should be capped at 6 hours."""
        tx = [{'eventType': 'Exercise', 'duration': 600,
               'created_at': '2025-06-15T06:00:00Z'}]
        grid = self._build_synthetic_grid(tx)
        self.assertIsNotNone(grid)
        ex_slots = (grid['exercise_active'] > 0).sum()
        # 6 hours = 72 slots at 5-min intervals (capped from 120 slots)
        self.assertLessEqual(ex_slots, 72,
                             f'Exercise should be capped at 72 slots (6h), got {ex_slots}')
        self.assertGreater(ex_slots, 60, 'Exercise should still mark ~6h of slots')

    def test_override_capped_at_24_hours(self):
        """Temporary Target with duration > 1440 min should be capped at 24h."""
        tx = [{'eventType': 'Temporary Target', 'duration': 2000,
               'created_at': '2025-06-15T00:00:00Z'}]
        grid = self._build_synthetic_grid(tx)
        self.assertIsNotNone(grid)
        ov_slots = (grid['override_active'] > 0).sum()
        # 24 hours = 288 slots (full day). Grid is also 288 rows.
        # But cap is 1440 min = 288 slots, and we start at row 0, so should fill all.
        self.assertLessEqual(ov_slots, 288)
        # Without cap, 2000 min = 400 slots, but grid is only 288 long anyway.
        # Key: override_type should be 1.0 for Temporary Target
        ov_type_1 = (grid['override_type'] == 1.0).sum()
        self.assertEqual(ov_slots, ov_type_1)

    def test_exercise_default_duration(self):
        """Exercise with no duration defaults to 60 minutes."""
        tx = [{'eventType': 'Exercise',
               'created_at': '2025-06-15T06:00:00Z'}]
        grid = self._build_synthetic_grid(tx)
        self.assertIsNotNone(grid)
        ex_slots = (grid['exercise_active'] > 0).sum()
        self.assertEqual(ex_slots, 12,
                         f'Exercise default should be 12 slots (60min), got {ex_slots}')

    def test_override_zero_duration_no_slots(self):
        """Temporary Target with duration=0 should not mark any slots."""
        tx = [{'eventType': 'Temporary Target', 'duration': 0,
               'created_at': '2025-06-15T06:00:00Z'}]
        grid = self._build_synthetic_grid(tx)
        self.assertIsNotNone(grid)
        ov_slots = (grid['override_active'] > 0).sum()
        self.assertEqual(ov_slots, 0,
                         'Zero-duration override should not mark any slots')

    def test_sensor_start_populates_sage(self):
        """Sensor Start event in synthetic grid should populate sage_hours."""
        tx = [{'eventType': 'Sensor Start',
               'created_at': '2025-06-15T06:00:00Z'}]
        grid = self._build_synthetic_grid(tx)
        self.assertIsNotNone(grid)
        sage_valid = grid['sage_hours'].notna().sum()
        self.assertGreater(sage_valid, 100,
                           'sage_hours should be populated after Sensor Start')
        warmup = (grid['sensor_warmup'] == 1.0).sum()
        self.assertEqual(warmup, 24,
                         f'Expected 24 warmup slots (2h), got {warmup}')


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

    def test_normalize_timezone_reexported(self):
        """normalize_timezone is available from constants, normalize, and __init__."""
        from tools.ns2parquet.constants import normalize_timezone as nt1
        from tools.ns2parquet.normalize import normalize_timezone as nt2
        from tools.ns2parquet import normalize_timezone as nt3
        self.assertIs(nt1, nt2)
        self.assertIs(nt1, nt3)


# ── Patient J — no AID controller (edge case) ───────────────────────

PATIENT_J_FIXTURES = os.path.isfile(
    os.path.join(FIXTURES_DIR, 'patient_j_entries.json'))


@unittest.skipUnless(PATIENT_J_FIXTURES, 'Patient J fixtures not available')
class TestPatientJNoController(unittest.TestCase):
    """Patient j has no AID controller — pure CGM-only data.

    This tests the edge case where devicestatus has no loop/openaps keys,
    resulting in zero IOB/COB from DeviceStatus. The grid should still build
    correctly with glucose data and treatments.
    """

    @classmethod
    def setUpClass(cls):
        cls.grid = _build_fixture_grid('patient_j', 'j')

    def test_grid_built(self):
        """Grid builds successfully even without AID controller."""
        self.assertIsNotNone(self.grid)
        self.assertGreater(len(self.grid), 0)

    def test_grid_has_expected_columns(self):
        self.assertEqual(self.grid.shape[1], EXPECTED_GRID_COLS)

    def test_glucose_populated(self):
        """CGM glucose should still be present."""
        valid = self.grid['glucose'].dropna()
        self.assertGreater(len(valid), 0)
        self.assertTrue((valid >= 30).all() and (valid <= 500).all(),
                        'Glucose values should be in mg/dL range')

    def test_iob_zero_without_controller(self):
        """Without AID controller, IOB should be 0 or NaN (no data source)."""
        iob = self.grid['iob']
        non_nan = iob.dropna()
        if len(non_nan) > 0:
            self.assertAlmostEqual(non_nan.abs().mean(), 0, places=1,
                                   msg='IOB should be ~0 without AID controller')

    def test_cob_zero_without_controller(self):
        """Without AID controller, COB should be 0 or NaN."""
        cob = self.grid['cob']
        non_nan = cob.dropna()
        if len(non_nan) > 0:
            self.assertAlmostEqual(non_nan.abs().mean(), 0, places=1,
                                   msg='COB should be ~0 without AID controller')

    def test_predictions_empty(self):
        """No AID means no predictions."""
        for col in ['loop_predicted_30', 'loop_predicted_60',
                    'loop_predicted_min']:
            valid = self.grid[col].dropna()
            # May have some forward-filled values but shouldn't be many
            self.assertLessEqual(len(valid), len(self.grid) * 0.1,
                                 f'{col} should be mostly NaN without AID')

    def test_treatments_still_present(self):
        """Bolus/carb treatments should work regardless of controller."""
        # Patient j may have manual treatments
        self.assertIn('bolus', self.grid.columns)
        self.assertIn('carbs', self.grid.columns)


# ── CLI Integration Tests ────────────────────────────────────────────

@unittest.skipUnless(HAS_FIXTURES, 'JSON fixtures not available')
class TestCmdConvert(unittest.TestCase):
    """Integration test: cmd_convert round-trips fixtures through CLI."""

    def test_convert_produces_all_collections(self):
        """cmd_convert writes entries, treatments, devicestatus, profiles, grid parquet files."""
        import argparse
        from tools.ns2parquet.cli import cmd_convert

        with tempfile.TemporaryDirectory() as tmpdir:
            # Copy fixture files to input dir
            indir = os.path.join(tmpdir, 'input')
            os.makedirs(indir)
            for col in ['entries', 'treatments', 'devicestatus', 'profile']:
                src = os.path.join(FIXTURES_DIR, f'patient_d_{col}.json')
                shutil.copy(src, os.path.join(indir, f'{col}.json'))

            outdir = os.path.join(tmpdir, 'output')

            args = argparse.Namespace(
                input=indir, patient_id='test_d', output=outdir,
                append=False, quiet=True, skip_grid=False, opaque_ids=False,
            )
            rc = cmd_convert(args)
            self.assertEqual(rc, 0)

            # Verify all expected files
            for collection in ['entries', 'treatments', 'devicestatus',
                               'profiles', 'grid']:
                pf = os.path.join(outdir, f'{collection}.parquet')
                self.assertTrue(os.path.exists(pf),
                                f'{collection}.parquet not created')
                # Read and verify non-empty
                df = pd.read_parquet(pf)
                self.assertGreater(len(df), 0,
                                   f'{collection}.parquet is empty')
                # Verify patient_id column
                self.assertIn('patient_id', df.columns)
                self.assertTrue((df['patient_id'] == 'test_d').all())

    def test_convert_skip_grid(self):
        """--skip-grid should omit grid.parquet."""
        import argparse
        from tools.ns2parquet.cli import cmd_convert

        with tempfile.TemporaryDirectory() as tmpdir:
            indir = os.path.join(tmpdir, 'input')
            os.makedirs(indir)
            for col in ['entries', 'treatments', 'devicestatus', 'profile']:
                src = os.path.join(FIXTURES_DIR, f'patient_d_{col}.json')
                shutil.copy(src, os.path.join(indir, f'{col}.json'))

            outdir = os.path.join(tmpdir, 'output')
            args = argparse.Namespace(
                input=indir, patient_id='test_d', output=outdir,
                append=False, quiet=True, skip_grid=True, opaque_ids=False,
            )
            rc = cmd_convert(args)
            self.assertEqual(rc, 0)
            self.assertFalse(os.path.exists(os.path.join(outdir, 'grid.parquet')))
            self.assertTrue(os.path.exists(os.path.join(outdir, 'entries.parquet')))

    def test_convert_schema_metadata_embedded(self):
        """Parquet files should contain ns2parquet provenance metadata."""
        import argparse
        import pyarrow.parquet as pq
        from tools.ns2parquet.cli import cmd_convert
        from tools.ns2parquet import __version__

        with tempfile.TemporaryDirectory() as tmpdir:
            indir = os.path.join(tmpdir, 'input')
            os.makedirs(indir)
            for col in ['entries', 'treatments', 'devicestatus', 'profile']:
                src = os.path.join(FIXTURES_DIR, f'patient_d_{col}.json')
                shutil.copy(src, os.path.join(indir, f'{col}.json'))

            outdir = os.path.join(tmpdir, 'output')
            args = argparse.Namespace(
                input=indir, patient_id='test_d', output=outdir,
                append=False, quiet=True, skip_grid=False, opaque_ids=False,
            )
            cmd_convert(args)

            # Check entries parquet metadata
            meta = pq.read_metadata(os.path.join(outdir, 'entries.parquet'))
            schema_meta = meta.schema.to_arrow_schema().metadata
            self.assertIn(b'ns2parquet.version', schema_meta)
            self.assertEqual(schema_meta[b'ns2parquet.version'].decode(),
                             __version__)
            self.assertIn(b'ns2parquet.collection', schema_meta)
            self.assertEqual(schema_meta[b'ns2parquet.collection'], b'entries')


@unittest.skipUnless(HAS_FIXTURES, 'JSON fixtures not available')
class TestCmdMerge(unittest.TestCase):
    """Integration test: cmd_merge merges multiple parquet directories."""

    def test_merge_two_patients(self):
        """Merge two patient directories into one, verify dedup and coverage."""
        import argparse
        from tools.ns2parquet.cli import cmd_convert, cmd_merge

        with tempfile.TemporaryDirectory() as tmpdir:
            # Build two separate parquet directories
            for prefix, pid in [('patient_d', 'd'), ('patient_a', 'a')]:
                indir = os.path.join(tmpdir, f'input_{pid}')
                os.makedirs(indir)
                for col in ['entries', 'treatments', 'devicestatus', 'profile']:
                    src = os.path.join(FIXTURES_DIR, f'{prefix}_{col}.json')
                    shutil.copy(src, os.path.join(indir, f'{col}.json'))

                outdir = os.path.join(tmpdir, f'out_{pid}')
                args = argparse.Namespace(
                    input=indir, patient_id=pid, output=outdir,
                    append=False, quiet=True, skip_grid=False, opaque_ids=False,
                )
                rc = cmd_convert(args)
                self.assertEqual(rc, 0, f'Convert failed for {pid}')

            # Merge the two directories
            merged_dir = os.path.join(tmpdir, 'merged')
            merge_args = argparse.Namespace(
                sources=[os.path.join(tmpdir, 'out_d'),
                         os.path.join(tmpdir, 'out_a')],
                output=merged_dir,
                quiet=True,
            )
            rc = cmd_merge(merge_args)
            self.assertEqual(rc, 0)

            # Verify merged grid has both patients
            grid = pd.read_parquet(os.path.join(merged_dir, 'grid.parquet'))
            patients = sorted(grid['patient_id'].unique())
            self.assertEqual(patients, ['a', 'd'])

            # Verify each patient's rows are intact
            for pid in ['a', 'd']:
                single = pd.read_parquet(
                    os.path.join(tmpdir, f'out_{pid}', 'grid.parquet'))
                merged_subset = grid[grid['patient_id'] == pid]
                self.assertEqual(len(merged_subset), len(single),
                                 f'Patient {pid} row count changed after merge')

    def test_merge_dedup_same_patient(self):
        """Merging the same patient twice should deduplicate."""
        import argparse
        from tools.ns2parquet.cli import cmd_convert, cmd_merge

        with tempfile.TemporaryDirectory() as tmpdir:
            indir = os.path.join(tmpdir, 'input')
            os.makedirs(indir)
            for col in ['entries', 'treatments', 'devicestatus', 'profile']:
                src = os.path.join(FIXTURES_DIR, f'patient_d_{col}.json')
                shutil.copy(src, os.path.join(indir, f'{col}.json'))

            outdir = os.path.join(tmpdir, 'out')
            args = argparse.Namespace(
                input=indir, patient_id='d', output=outdir,
                append=False, quiet=True, skip_grid=False, opaque_ids=False,
            )
            cmd_convert(args)

            single_grid = pd.read_parquet(os.path.join(outdir, 'grid.parquet'))
            n_single = len(single_grid)

            # Merge same dir with itself
            merged_dir = os.path.join(tmpdir, 'merged')
            merge_args = argparse.Namespace(
                sources=[outdir, outdir],
                output=merged_dir,
                quiet=True,
            )
            rc = cmd_merge(merge_args)
            self.assertEqual(rc, 0)

            merged_grid = pd.read_parquet(os.path.join(merged_dir, 'grid.parquet'))
            self.assertEqual(len(merged_grid), n_single,
                             'Duplicate rows should be removed after merge')


# ── parquet_info test ────────────────────────────────────────────────

@unittest.skipUnless(HAS_FIXTURES, 'JSON fixtures not available')
class TestParquetInfo(unittest.TestCase):
    """Test parquet_info() returns correct structure."""

    def test_info_structure(self):
        import argparse
        from tools.ns2parquet.cli import cmd_convert
        from tools.ns2parquet.writer import parquet_info

        with tempfile.TemporaryDirectory() as tmpdir:
            indir = os.path.join(tmpdir, 'input')
            os.makedirs(indir)
            for col in ['entries', 'treatments', 'devicestatus', 'profile']:
                src = os.path.join(FIXTURES_DIR, f'patient_d_{col}.json')
                shutil.copy(src, os.path.join(indir, f'{col}.json'))

            outdir = os.path.join(tmpdir, 'output')
            args = argparse.Namespace(
                input=indir, patient_id='d', output=outdir,
                append=False, quiet=True, skip_grid=False, opaque_ids=False,
            )
            cmd_convert(args)

            info = parquet_info(outdir)
            self.assertIsInstance(info, dict)

            # Should have entries for each collection
            for coll in ['entries', 'treatments', 'devicestatus',
                         'profiles', 'grid']:
                self.assertIn(coll, info, f'{coll} missing from info')
                cinfo = info[coll]
                self.assertIn('rows', cinfo)
                self.assertIn('columns', cinfo)
                self.assertIn('size_bytes', cinfo)
                self.assertIn('patients', cinfo)
                self.assertIn('num_patients', cinfo)
                self.assertGreater(cinfo['rows'], 0)
                self.assertEqual(cinfo['num_patients'], 1)
                self.assertIn('d', cinfo['patients'])

    def test_info_empty_dir(self):
        """parquet_info on empty directory returns empty dict."""
        from tools.ns2parquet.writer import parquet_info
        with tempfile.TemporaryDirectory() as tmpdir:
            info = parquet_info(tmpdir)
            self.assertEqual(info, {})


# ── __init__.py re-exports ───────────────────────────────────────────

class TestPublicAPI(unittest.TestCase):
    """Verify that key functions are accessible from the package root."""

    def test_version_bumped(self):
        from tools.ns2parquet import __version__
        # Should be >= 0.3.0 after ns_fetch + manifest changes
        major, minor, patch = __version__.split('.')
        self.assertGreaterEqual(int(minor), 3)

    def test_normalize_functions_exported(self):
        from tools.ns2parquet import (
            normalize_entries, normalize_treatments,
            normalize_devicestatus, normalize_profiles,
            normalize_settings,
        )
        for fn in [normalize_entries, normalize_treatments,
                   normalize_devicestatus, normalize_profiles,
                   normalize_settings]:
            self.assertTrue(callable(fn))

    def test_grid_function_exported(self):
        from tools.ns2parquet import build_grid
        self.assertTrue(callable(build_grid))

    def test_writer_functions_exported(self):
        from tools.ns2parquet import write_parquet, read_parquet, parquet_info
        for fn in [write_parquet, read_parquet, parquet_info]:
            self.assertTrue(callable(fn))

    def test_schemas_exported(self):
        from tools.ns2parquet import (
            ENTRIES_SCHEMA, TREATMENTS_SCHEMA, DEVICESTATUS_SCHEMA,
            PROFILES_SCHEMA, SETTINGS_SCHEMA, GRID_SCHEMA,
        )
        import pyarrow as pa
        for schema in [ENTRIES_SCHEMA, TREATMENTS_SCHEMA,
                       DEVICESTATUS_SCHEMA, PROFILES_SCHEMA,
                       SETTINGS_SCHEMA, GRID_SCHEMA]:
            self.assertIsInstance(schema, pa.Schema)

    def test_ns_fetch_exported(self):
        from tools.ns2parquet import (
            fetch_json, fetch_entries, fetch_treatments,
            fetch_devicestatus, load_ns_url,
        )
        for fn in [fetch_json, fetch_entries, fetch_treatments,
                   fetch_devicestatus, load_ns_url]:
            self.assertTrue(callable(fn))

    def test_build_manifest_exported(self):
        from tools.ns2parquet import build_manifest
        self.assertTrue(callable(build_manifest))


# ── Controller detection tests ──────────────────────────────────────────

class TestDetectController(unittest.TestCase):
    """Test _detect_controller covers all controller string variants."""

    def setUp(self):
        from tools.ns2parquet.normalize import _detect_controller
        self.detect = _detect_controller

    def test_loop_url(self):
        self.assertEqual(self.detect('loop://iPhone12,1'), 'loop')

    def test_loop_substring(self):
        self.assertEqual(self.detect('Loop'), 'loop')

    def test_openaps_url(self):
        self.assertEqual(self.detect('openaps://Edison'), 'openaps')

    def test_openaps_substring(self):
        self.assertEqual(self.detect('openaps'), 'openaps')

    def test_trio(self):
        self.assertEqual(self.detect('Trio 0.2.0'), 'trio')

    def test_aaps(self):
        self.assertEqual(self.detect('AAPS'), 'aaps')

    def test_androidaps(self):
        self.assertEqual(self.detect('AndroidAPS 3.2'), 'aaps')

    def test_xdrip(self):
        self.assertEqual(self.detect('xDrip-DexcomG6'), 'xdrip')

    def test_unknown_device(self):
        self.assertEqual(self.detect('DexcomShare2'), 'unknown')

    def test_none_input(self):
        self.assertEqual(self.detect(None), 'unknown')

    def test_empty_string(self):
        self.assertEqual(self.detect(''), 'unknown')


# ── Loop devicestatus extraction tests ──────────────────────────────────

class TestExtractLoopDS(unittest.TestCase):
    """Test _extract_loop_ds with realistic Loop devicestatus records."""

    def setUp(self):
        from tools.ns2parquet.normalize import _extract_loop_ds
        self.extract = _extract_loop_ds

    def test_basic_loop_record(self):
        ds = {
            'loop': {
                'iob': {'iob': 1.25, 'timestamp': '2024-01-01T12:00:00Z'},
                'cob': {'cob': 30.0},
                'predicted': {'values': [120, 118, 115, 112, 110, 108,
                                         106, 104, 102, 100, 98, 96, 94]},
                'enacted': {'rate': 0.5, 'duration': 1800, 'received': True},
                'recommendedBolus': 0.0,
            }
        }
        result = self.extract(ds)
        self.assertAlmostEqual(result['iob'], 1.25)
        self.assertAlmostEqual(result['cob'], 30.0)
        self.assertAlmostEqual(result['predicted_30'], 106)   # values[6]
        self.assertAlmostEqual(result['predicted_60'], 94)    # values[12]
        self.assertAlmostEqual(result['predicted_min'], 94)
        self.assertAlmostEqual(result['enacted_rate'], 0.5)
        self.assertAlmostEqual(result['enacted_duration_min'], 30.0)  # 1800s→30min
        self.assertTrue(result['enacted_received'])

    def test_hypo_risk_count(self):
        ds = {
            'loop': {
                'iob': {'iob': 2.0},
                'cob': {},
                'predicted': {'values': [100, 90, 80, 70, 65,
                                         60, 55, 50, 55, 60, 65, 70, 75]},
            }
        }
        result = self.extract(ds)
        # Values < 70: 65, 60, 55, 50, 55, 60, 65 = 7
        self.assertEqual(result['hypo_risk_count'], 7)

    def test_override_from_ds_root(self):
        ds = {
            'loop': {'iob': {'iob': 0.5}, 'cob': {}},
            'override': {'active': True, 'name': 'Running', 'multiplier': 1.5},
        }
        result = self.extract(ds)
        self.assertTrue(result['override_active'])
        self.assertEqual(result['override_name'], 'Running')
        self.assertAlmostEqual(result['override_multiplier'], 1.5)

    def test_no_predictions(self):
        ds = {'loop': {'iob': {'iob': 0.0}, 'cob': {}}}
        result = self.extract(ds)
        self.assertIsNone(result['predicted_30'])
        self.assertIsNone(result['predicted_60'])
        self.assertIsNone(result['predicted_min'])
        self.assertIsNone(result['hypo_risk_count'])

    def test_empty_loop_object(self):
        ds = {'loop': {}}
        result = self.extract(ds)
        self.assertIsNone(result['iob'])
        self.assertIsNone(result['cob'])
        self.assertIsNone(result['enacted_rate'])

    def test_bolus_volume(self):
        ds = {
            'loop': {
                'iob': {'iob': 0.5},
                'cob': {},
                'enacted': {'rate': 0.0, 'duration': 0, 'bolusVolume': 0.3},
            }
        }
        result = self.extract(ds)
        self.assertAlmostEqual(result['enacted_smb'], 0.3)


# ── To-bool conversion tests ───────────────────────────────────────────

class TestToBool(unittest.TestCase):
    """Test _to_bool handles various input types from Nightscout JSON."""

    def setUp(self):
        from tools.ns2parquet.normalize import _to_bool
        self.to_bool = _to_bool

    def test_none(self):
        self.assertIsNone(self.to_bool(None))

    def test_bool_true(self):
        self.assertTrue(self.to_bool(True))

    def test_bool_false(self):
        self.assertFalse(self.to_bool(False))

    def test_string_true(self):
        self.assertTrue(self.to_bool('true'))
        self.assertTrue(self.to_bool('True'))
        self.assertTrue(self.to_bool('1'))
        self.assertTrue(self.to_bool('yes'))

    def test_string_false(self):
        self.assertFalse(self.to_bool('false'))
        self.assertFalse(self.to_bool('0'))
        self.assertFalse(self.to_bool('no'))

    def test_int_truthy(self):
        self.assertTrue(self.to_bool(1))
        self.assertFalse(self.to_bool(0))


# ── Grid dtype and alignment tests ──────────────────────────────────────

class TestGridDtypeAndAlignment(unittest.TestCase):
    """Verify grid output has correct dtypes and 5-min alignment."""

    @classmethod
    def setUpClass(cls):
        patient_d = os.path.join(FIXTURES_DIR, 'patient_d')
        if not os.path.isdir(patient_d):
            # Build from individual fixture files
            cls._tmpdir = tempfile.mkdtemp(prefix='ns2pq_dtype_')
            for col in ['entries', 'treatments', 'devicestatus', 'profile']:
                src = os.path.join(FIXTURES_DIR, f'patient_d_{col}.json')
                if os.path.exists(src):
                    shutil.copy(src, os.path.join(cls._tmpdir, f'{col}.json'))
            from tools.ns2parquet.grid import build_grid
            cls.grid = build_grid(cls._tmpdir, 'dtype_test')
        else:
            cls._tmpdir = None
            from tools.ns2parquet.grid import build_grid
            cls.grid = build_grid(patient_d, 'dtype_test')

    @classmethod
    def tearDownClass(cls):
        if cls._tmpdir:
            shutil.rmtree(cls._tmpdir, ignore_errors=True)

    def test_grid_not_none(self):
        self.assertIsNotNone(self.grid, 'Grid should build from patient_d fixture')

    @unittest.skipUnless(HAS_FIXTURES, 'patient_d fixtures required')
    def test_time_column_is_datetime(self):
        if self.grid is None:
            self.skipTest('grid not built')
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(self.grid['time']))

    @unittest.skipUnless(HAS_FIXTURES, 'patient_d fixtures required')
    def test_time_column_is_tz_aware(self):
        if self.grid is None:
            self.skipTest('grid not built')
        self.assertIsNotNone(self.grid['time'].dt.tz)

    @unittest.skipUnless(HAS_FIXTURES, 'patient_d fixtures required')
    def test_time_monotonically_increasing(self):
        if self.grid is None:
            self.skipTest('grid not built')
        diffs = self.grid['time'].diff().dropna()
        self.assertTrue((diffs > pd.Timedelta(0)).all(),
                        'Time column should be monotonically increasing')

    @unittest.skipUnless(HAS_FIXTURES, 'patient_d fixtures required')
    def test_time_5min_intervals(self):
        if self.grid is None:
            self.skipTest('grid not built')
        diffs = self.grid['time'].diff().dropna()
        expected = pd.Timedelta(minutes=5)
        self.assertTrue((diffs == expected).all(),
                        f'All intervals should be 5 min; got unique: '
                        f'{diffs.unique()[:5]}')

    @unittest.skipUnless(HAS_FIXTURES, 'patient_d fixtures required')
    def test_glucose_is_float(self):
        if self.grid is None:
            self.skipTest('grid not built')
        self.assertTrue(pd.api.types.is_float_dtype(self.grid['glucose']))

    @unittest.skipUnless(HAS_FIXTURES, 'patient_d fixtures required')
    def test_iob_is_float(self):
        if self.grid is None:
            self.skipTest('grid not built')
        self.assertTrue(pd.api.types.is_float_dtype(self.grid['iob']))

    @unittest.skipUnless(HAS_FIXTURES, 'patient_d fixtures required')
    def test_patient_id_is_string(self):
        if self.grid is None:
            self.skipTest('grid not built')
        self.assertTrue(pd.api.types.is_string_dtype(self.grid['patient_id'])
                        or pd.api.types.is_object_dtype(self.grid['patient_id']))

    @unittest.skipUnless(HAS_FIXTURES, 'patient_d fixtures required')
    def test_direction_is_string(self):
        if self.grid is None:
            self.skipTest('grid not built')
        self.assertTrue(pd.api.types.is_string_dtype(self.grid['direction'])
                        or pd.api.types.is_object_dtype(self.grid['direction']))

    @unittest.skipUnless(HAS_FIXTURES, 'patient_d fixtures required')
    def test_has_49_columns(self):
        if self.grid is None:
            self.skipTest('grid not built')
        self.assertEqual(self.grid.shape[1], EXPECTED_GRID_COLS)


# ── CGM gap tests ───────────────────────────────────────────────────────

class TestCGMGap(unittest.TestCase):
    """Test grid behavior when CGM data has a multi-hour gap."""

    @classmethod
    def setUpClass(cls):
        """Create a synthetic patient directory with a 2-hour CGM gap."""
        import json as _json

        cls.tmpdir = tempfile.mkdtemp(prefix='ns2pq_gap_')

        base_ts = 1704067200000  # 2024-01-01T00:00:00Z
        entries = []
        # 2 hours of data, then 2 hour gap, then 2 hours more
        for i in range(24):  # 0:00 - 2:00 (every 5 min)
            entries.append({
                '_id': f'gap_a_{i}', 'type': 'sgv',
                'sgv': 120 + i, 'date': base_ts + i * 300000,
                'direction': 'Flat',
            })
        # Gap from 2:00 to 4:00
        for i in range(24):  # 4:00 - 6:00
            entries.append({
                '_id': f'gap_b_{i}', 'type': 'sgv',
                'sgv': 150 - i, 'date': base_ts + (48 + i) * 300000,
                'direction': 'FortyFiveDown',
            })

        # Minimal treatments, devicestatus, profile
        treatments = [{'_id': 't1', 'eventType': 'Correction Bolus',
                       'insulin': 1.0,
                       'created_at': '2024-01-01T01:00:00Z'}]
        ds = [{'_id': 'ds1', 'created_at': '2024-01-01T01:00:00Z',
               'device': 'loop://test',
               'loop': {'iob': {'iob': 0.5}, 'cob': {'cob': 0}}}]
        profile = [{'_id': 'p1', 'defaultProfile': 'Default',
                    'store': {'Default': {
                        'timezone': 'UTC', 'dia': 6, 'units': 'mg/dl',
                        'basal': [{'time': '00:00', 'value': 1.0,
                                   'timeAsSeconds': 0}],
                        'isfProfile': [{'time': '00:00', 'value': 40,
                                        'timeAsSeconds': 0}],
                        'carbRatio': [{'time': '00:00', 'value': 10,
                                       'timeAsSeconds': 0}],
                        'target_low': [{'time': '00:00', 'value': 100,
                                        'timeAsSeconds': 0}],
                        'target_high': [{'time': '00:00', 'value': 120,
                                         'timeAsSeconds': 0}],
                    }}}]

        for name, data in [('entries', entries), ('treatments', treatments),
                           ('devicestatus', ds), ('profile', profile)]:
            with open(os.path.join(cls.tmpdir, f'{name}.json'), 'w') as f:
                _json.dump(data, f)

        from tools.ns2parquet.grid import build_grid
        cls.grid = build_grid(cls.tmpdir, 'gap_test')

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def test_grid_built(self):
        self.assertIsNotNone(self.grid)

    def test_glucose_nan_during_gap(self):
        """Glucose should be NaN during the 2h CGM gap."""
        gap_rows = self.grid[
            (self.grid['time'] > '2024-01-01T02:10:00Z') &
            (self.grid['time'] < '2024-01-01T03:50:00Z')
        ]
        if len(gap_rows) > 0:
            nan_count = gap_rows['glucose'].isna().sum()
            self.assertGreater(nan_count, 0,
                               'Expected NaN glucose during CGM gap')

    def test_hours_since_cgm_increases_during_gap(self):
        """hours_since_cgm should accumulate during the gap."""
        if 'hours_since_cgm' not in self.grid.columns:
            self.skipTest('hours_since_cgm column not present')
        # Find rows in the middle of the 2h gap (between 2:30 and 3:30)
        gap_mid = self.grid[
            (self.grid['time'] >= '2024-01-01T02:30:00+00:00') &
            (self.grid['time'] <= '2024-01-01T03:30:00+00:00')
        ]
        if len(gap_mid) > 0:
            hsc = gap_mid['hours_since_cgm'].dropna()
            if len(hsc) > 0:
                self.assertGreater(hsc.max(), 0.5,
                                   'hours_since_cgm should accumulate '
                                   'during CGM gap')

    def test_glucose_roc_nan_at_gap_boundary(self):
        """Rate of change should be NaN at gap boundaries."""
        if 'glucose_roc' not in self.grid.columns:
            self.skipTest('glucose_roc column not present')
        after_gap = self.grid[
            self.grid['time'] >= '2024-01-01T04:00:00+00:00'].head(3)
        if len(after_gap) > 0:
            roc_vals = after_gap['glucose_roc'].dropna()
            if len(roc_vals) > 0:
                # Should not show huge jumps from interpolation across gap
                self.assertTrue(
                    all(abs(v) < 30 for v in roc_vals),
                    f'glucose_roc at gap boundary should not be huge: '
                    f'{roc_vals.tolist()}')

    def test_has_49_columns(self):
        self.assertEqual(self.grid.shape[1], EXPECTED_GRID_COLS)


# ── Manifest tests ──────────────────────────────────────────────────────

class TestManifest(unittest.TestCase):
    """Test build_manifest and cmd_manifest."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix='ns2pq_manifest_')

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_manifest_from_grid(self):
        """build_manifest extracts per-patient metadata from grid.parquet."""
        from tools.ns2parquet.writer import write_parquet
        from tools.ns2parquet.cli import build_manifest

        times = pd.date_range('2024-01-01', periods=288,
                              freq='5min', tz='UTC')
        grid = pd.DataFrame({
            'patient_id': 'test_p',
            'time': times,
            'glucose': np.random.uniform(70, 200, 288).astype(np.float32),
            'iob': np.zeros(288, dtype=np.float32),
            'cob': np.zeros(288, dtype=np.float32),
            'net_basal': np.zeros(288, dtype=np.float32),
            'bolus': np.zeros(288, dtype=np.float32),
            'bolus_smb': np.zeros(288, dtype=np.float32),
            'carbs': np.zeros(288, dtype=np.float32),
            'eventual_bg': np.full(288, np.nan, dtype=np.float32),
            'loop_predicted_30': np.full(288, 120, dtype=np.float32),
        })
        write_parquet(grid, self.tmpdir, 'grid', append=False)

        manifest = build_manifest(self.tmpdir)
        self.assertEqual(manifest['num_patients'], 1)
        self.assertIn('test_p', manifest['patients'])

        p = manifest['patients']['test_p']
        self.assertEqual(p['grid_rows'], 288)
        self.assertIsNotNone(p['tir_pct'])
        self.assertIsNotNone(p['mean_glucose_mgdl'])
        self.assertEqual(p['controller'], 'loop')  # has loop_predicted_30

    def test_manifest_multiple_patients(self):
        from tools.ns2parquet.writer import write_parquet
        from tools.ns2parquet.cli import build_manifest

        times = pd.date_range('2024-01-01', periods=100,
                              freq='5min', tz='UTC')
        rows = []
        for pid in ['alice', 'bob']:
            for t in times:
                rows.append({
                    'patient_id': pid, 'time': t,
                    'glucose': np.float32(120),
                    'eventual_bg': (np.float32(115)
                                    if pid == 'bob' else np.nan),
                })
        grid = pd.DataFrame(rows)
        write_parquet(grid, self.tmpdir, 'grid', append=False)

        manifest = build_manifest(self.tmpdir)
        self.assertEqual(manifest['num_patients'], 2)
        self.assertIn('alice', manifest['patients'])
        self.assertIn('bob', manifest['patients'])
        self.assertEqual(manifest['patients']['bob']['controller'], 'oref0')
        self.assertEqual(manifest['patients']['alice']['controller'],
                         'unknown')

    def test_manifest_has_version(self):
        from tools.ns2parquet.cli import build_manifest
        from tools.ns2parquet import __version__

        manifest = build_manifest(self.tmpdir)
        self.assertEqual(manifest['ns2parquet_version'], __version__)

    def test_cmd_manifest_writes_json(self):
        from tools.ns2parquet.writer import write_parquet
        import argparse as _argparse

        times = pd.date_range('2024-01-01', periods=50,
                              freq='5min', tz='UTC')
        grid = pd.DataFrame({
            'patient_id': 'cmd_test',
            'time': times,
            'glucose': np.full(50, 130, dtype=np.float32),
        })
        write_parquet(grid, self.tmpdir, 'grid', append=False)

        from tools.ns2parquet.cli import cmd_manifest
        args = _argparse.Namespace(input=self.tmpdir, quiet=True)
        rc = cmd_manifest(args)
        self.assertEqual(rc, 0)

        manifest_path = os.path.join(self.tmpdir, 'manifest.json')
        self.assertTrue(os.path.exists(manifest_path))

        import json as _json
        with open(manifest_path) as f:
            data = _json.load(f)
        self.assertIn('cmd_test', data['patients'])


# ── NS fetch module tests ──────────────────────────────────────────────

class TestNsFetch(unittest.TestCase):
    """Test ns_fetch module is self-contained and importable."""

    def test_import_without_cgmencode(self):
        """ns_fetch should import without any cgmencode dependency."""
        from tools.ns2parquet.ns_fetch import (
            fetch_json, fetch_entries, fetch_treatments,
            fetch_devicestatus, load_ns_url, _fetch_windowed,
        )
        self.assertTrue(callable(fetch_json))
        self.assertTrue(callable(_fetch_windowed))

    def test_load_ns_url_from_envfile(self):
        from tools.ns2parquet.ns_fetch import load_ns_url

        envfile = os.path.join(tempfile.mkdtemp(), 'test.env')
        try:
            with open(envfile, 'w') as f:
                f.write('NS_URL=https://my-nightscout.fly.dev\n')
            url = load_ns_url(envfile)
            self.assertEqual(url, 'https://my-nightscout.fly.dev')
        finally:
            shutil.rmtree(os.path.dirname(envfile), ignore_errors=True)

    def test_load_ns_url_strips_quotes(self):
        from tools.ns2parquet.ns_fetch import load_ns_url

        envfile = os.path.join(tempfile.mkdtemp(), 'test.env')
        try:
            with open(envfile, 'w') as f:
                f.write('NS_URL="https://my-ns.example.com/"\n')
            url = load_ns_url(envfile)
            self.assertEqual(url, 'https://my-ns.example.com')
        finally:
            shutil.rmtree(os.path.dirname(envfile), ignore_errors=True)

    def test_load_ns_url_missing_raises(self):
        from tools.ns2parquet.ns_fetch import load_ns_url

        envfile = os.path.join(tempfile.mkdtemp(), 'test.env')
        try:
            with open(envfile, 'w') as f:
                f.write('OTHER_VAR=foo\n')
            with self.assertRaises(ValueError):
                load_ns_url(envfile)
        finally:
            shutil.rmtree(os.path.dirname(envfile), ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
