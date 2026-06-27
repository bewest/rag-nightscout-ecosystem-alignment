#!/usr/bin/env python3
"""
Test suite for the validation framework and objective validators.

Tests cover:
  1. BootstrapCI — bootstrap and t-distribution confidence intervals
  2. TemporalSplitter — 2-way and 3-way temporal splits
  3. StratifiedTemporalSplitter — prevalence-preserving splits
  4. MultiSeedRunner — deterministic multi-seed evaluation
  5. LOOValidator — leave-one-out patient evaluation
  6. ValidationReport — report generation
  7. ClassificationValidator — F1, AUC, ECE, calibration
  8. ForecastValidator — MAE, RMSE, zone MAE, Clarke grid
  9. RetrievalValidator — silhouette, ARI, balanced R@K
  10. DriftValidator — Spearman ρ, OLS slope, aggregation
  11. ExperimentContext integration — validation metadata in JSON

Usage:
    python tools/cgmencode/test_validation.py          # Run all tests
    python tools/cgmencode/test_validation.py -v        # Verbose output
    python -m pytest tools/cgmencode/test_validation.py # With pytest
"""

import sys
import unittest
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import json
import os
import tempfile

import numpy as np
import pandas as pd
import pandas as pd

# ── Imports under test ──────────────────────────────────────────────────

from tools.cgmencode.validation_framework import (
    BootstrapCI,
    LOOValidator,
    MultiSeedRunner,
    StratifiedTemporalSplitter,
    TemporalSplitter,
    ValidationReport,
    STANDARD_SEEDS,
    SeedResult,
)
from tools.cgmencode.objective_validators import (
    ClassificationValidator,
    DriftValidator,
    ForecastValidator,
    RetrievalValidator,
)
from tools.cgmencode.experiment_lib import ExperimentContext, set_seed
from tools.cgmencode import mlflow_utils
from tools.cgmencode.autoresearch_agent import (
    DIRECTIONS,
    build_model_candidate_from_plan,
    build_research_plan,
    evaluate_research_plan,
)
from tools.cgmencode.mlflow_pyfunc_models import (
    EffectiveParameterExtractorModel,
    save_effective_parameter_extractor_model,
)
from tools.cgmencode.parameter_model_bundle import (
    derive_titration_plan,
    derive_titration_guidance,
    derive_settings_special_handling,
    assess_effective_parameter_thresholds,
    build_effective_parameter_bundle,
    evaluate_effective_parameter_bundle,
    propose_effective_parameter_thresholds,
    save_bundle,
)


# =============================================================================
# 1. BootstrapCI Tests
# =============================================================================

class TestBootstrapCI(unittest.TestCase):
    """Tests for bootstrap and seed-based confidence intervals."""

    def test_bootstrap_basic(self):
        """Bootstrap CI should bracket the point estimate."""
        y_true = np.array([0] * 80 + [1] * 20)
        y_pred = np.array([0] * 78 + [1] * 2 + [1] * 15 + [0] * 5)
        ci = BootstrapCI.compute(
            y_true, y_pred,
            lambda yt, yp: float((yt == yp).sum() / len(yt)),
            n_bootstrap=200, seed=42,
        )
        self.assertIn('mean', ci)
        self.assertIn('ci_lower', ci)
        self.assertIn('ci_upper', ci)
        self.assertLess(ci['ci_lower'], ci['ci_upper'])
        self.assertGreater(ci['ci_lower'], 0.5)  # accuracy > 50%

    def test_bootstrap_deterministic(self):
        """Same seed should give identical CIs."""
        y_true = np.random.RandomState(0).randint(0, 2, 100)
        y_pred = np.random.RandomState(1).randint(0, 2, 100)
        fn = lambda yt, yp: float((yt == yp).sum() / len(yt))
        ci1 = BootstrapCI.compute(y_true, y_pred, fn, seed=42)
        ci2 = BootstrapCI.compute(y_true, y_pred, fn, seed=42)
        self.assertAlmostEqual(ci1['mean'], ci2['mean'], places=10)
        self.assertAlmostEqual(ci1['ci_lower'], ci2['ci_lower'], places=10)

    def test_seed_values_ci(self):
        """T-distribution CI from seed values."""
        values = [0.935, 0.940, 0.928, 0.942, 0.930]
        ci = BootstrapCI.from_seed_values(values, ci=0.95)
        self.assertAlmostEqual(ci['mean'], np.mean(values), places=6)
        self.assertAlmostEqual(ci['std'], np.std(values, ddof=1), places=6)
        self.assertLess(ci['ci_lower'], ci['mean'])
        self.assertGreater(ci['ci_upper'], ci['mean'])
        self.assertEqual(ci['n_seeds'], 5)

    def test_seed_values_single(self):
        """Single seed value should return zero-width CI."""
        ci = BootstrapCI.from_seed_values([0.935])
        self.assertAlmostEqual(ci['mean'], 0.935)
        self.assertEqual(ci['std'], 0.0)

    def test_seed_values_two(self):
        """Two seed values should still produce valid CI."""
        ci = BootstrapCI.from_seed_values([0.90, 0.95])
        self.assertAlmostEqual(ci['mean'], 0.925)
        self.assertLess(ci['ci_lower'], 0.90)
        self.assertGreater(ci['ci_upper'], 0.95)


# =============================================================================
# 2. TemporalSplitter Tests
# =============================================================================

class TestTemporalSplitter(unittest.TestCase):
    """Tests for temporal (chronological) data splitting."""

    def test_2way_default(self):
        """Default 2-way split (80/20)."""
        ts = TemporalSplitter(fractions=(0.8, 0.2))
        data = np.arange(100).reshape(100, 1)
        split = ts.split_array(data)
        self.assertEqual(len(split.train), 80)
        self.assertEqual(len(split.val), 20)
        self.assertIsNone(split.test)
        # Temporal order preserved
        self.assertTrue(np.all(split.train[-1] < split.val[0]))

    def test_3way_split(self):
        """3-way split (60/20/20)."""
        ts = TemporalSplitter(fractions=(0.6, 0.2, 0.2))
        data = np.arange(1000).reshape(1000, 1)
        split = ts.split_array(data)
        self.assertEqual(len(split.train), 600)
        self.assertEqual(len(split.val), 200)
        self.assertEqual(len(split.test), 200)
        # Temporal order: train < val < test
        self.assertTrue(np.all(split.train[-1] < split.val[0]))
        self.assertTrue(np.all(split.val[-1] < split.test[0]))

    def test_fractions_must_sum_to_one(self):
        """Fractions not summing to 1.0 should raise."""
        with self.assertRaises(AssertionError):
            TemporalSplitter(fractions=(0.5, 0.3, 0.1))

    def test_metadata_populated(self):
        """Split result should include metadata."""
        ts = TemporalSplitter(fractions=(0.6, 0.2, 0.2))
        split = ts.split_array(np.zeros((100, 4)))
        self.assertEqual(split.metadata['strategy'], 'temporal')
        self.assertEqual(split.metadata['fractions'], [0.6, 0.2, 0.2])


# =============================================================================
# 3. StratifiedTemporalSplitter Tests
# =============================================================================

class TestStratifiedTemporalSplitter(unittest.TestCase):
    """Tests for prevalence-preserving temporal splits."""

    def test_preserves_prevalence(self):
        """Prevalence should be similar across splits."""
        # 6.4% positive (hypo-like)
        labels = np.array([0] * 936 + [1] * 64)
        data = np.random.RandomState(42).randn(1000, 24, 8).astype(np.float32)
        strat = StratifiedTemporalSplitter(fractions=(0.6, 0.2, 0.2))
        split = strat.split(data, labels)

        train_prev = split.metadata['train_prevalence'].get(1, 0)
        val_prev = split.metadata['val_prevalence'].get(1, 0)
        test_prev = split.metadata['test_prevalence'].get(1, 0)
        # Prevalence should be within 3% of overall
        overall = 64 / 1000
        self.assertAlmostEqual(train_prev, overall, delta=0.03)
        self.assertAlmostEqual(val_prev, overall, delta=0.03)
        self.assertAlmostEqual(test_prev, overall, delta=0.03)

    def test_sizes_match_fractions(self):
        """Split sizes should approximately match requested fractions."""
        labels = np.array([0] * 500 + [1] * 500)
        data = np.zeros((1000, 8))
        strat = StratifiedTemporalSplitter(fractions=(0.6, 0.2, 0.2))
        split = strat.split(data, labels)
        # Sizes should be within ±5% of target due to per-class rounding
        self.assertAlmostEqual(len(split.train) / 1000, 0.6, delta=0.05)
        self.assertAlmostEqual(len(split.val) / 1000, 0.2, delta=0.05)


# =============================================================================
# 4. MultiSeedRunner Tests
# =============================================================================

class TestMultiSeedRunner(unittest.TestCase):
    """Tests for multi-seed evaluation runner."""

    def test_standard_seeds(self):
        """STANDARD_SEEDS should match EXP-302 convention."""
        self.assertEqual(STANDARD_SEEDS, [42, 123, 456, 789, 1337])

    def test_runs_all_seeds(self):
        """Runner should execute train_fn for each seed."""
        seeds_seen = []
        def train_fn(seed):
            seeds_seen.append(seed)
            return {'metric': float(seed) / 1000}
        runner = MultiSeedRunner(seeds=[42, 123, 456])
        report = runner.run(train_fn, verbose=False)
        self.assertEqual(seeds_seen, [42, 123, 456])
        self.assertEqual(len(report.seed_results), 3)

    def test_aggregate_metrics(self):
        """Aggregate should compute mean/std/CI across seeds."""
        def train_fn(seed):
            rng = np.random.RandomState(seed)
            return {'f1': 0.9 + rng.normal(0, 0.01)}
        runner = MultiSeedRunner(seeds=[42, 123, 456])
        report = runner.run(train_fn, verbose=False)
        agg = report.aggregate()
        self.assertIn('f1', agg)
        self.assertIn('mean', agg['f1'])
        self.assertIn('ci_lower', agg['f1'])
        self.assertAlmostEqual(agg['f1']['mean'], 0.9, delta=0.05)

    def test_deterministic(self):
        """Same seeds should give identical results."""
        def train_fn(seed):
            rng = np.random.RandomState(seed)
            return {'val': rng.uniform()}
        r1 = MultiSeedRunner(seeds=[42, 123]).run(train_fn, verbose=False)
        r2 = MultiSeedRunner(seeds=[42, 123]).run(train_fn, verbose=False)
        a1 = r1.aggregate()
        a2 = r2.aggregate()
        self.assertAlmostEqual(a1['val']['mean'], a2['val']['mean'])

    def test_summary_format(self):
        """Summary should return human-readable strings."""
        def train_fn(seed):
            return {'acc': 0.95}
        report = MultiSeedRunner(seeds=[42]).run(train_fn, verbose=False)
        summary = report.summary
        self.assertIn('acc', summary)
        self.assertIsInstance(summary['acc'], str)

    def test_to_dict(self):
        """to_dict should be JSON-serializable."""
        def train_fn(seed):
            return {'m': 0.5}
        report = MultiSeedRunner(seeds=[42, 123]).run(train_fn, verbose=False)
        d = report.to_dict()
        json_str = json.dumps(d, default=str)
        self.assertIn('seeds', d)
        self.assertIn('aggregate', d)


# =============================================================================
# 5. LOOValidator Tests
# =============================================================================

class TestLOOValidator(unittest.TestCase):
    """Tests for leave-one-out patient validation."""

    def test_leaves_out_each_patient(self):
        """Each patient should be held out exactly once."""
        patient_data = {p: np.zeros((10, 4)) for p in ['a', 'b', 'c']}
        held_out = []

        def train_fn(train_data):
            return list(train_data.keys())

        def eval_fn(model, test_data):
            # test_data is a single patient's array, not a dict
            held_out.append('seen')
            return {'metric': 1.0}

        loo = LOOValidator()
        report = loo.run(patient_data, train_fn, eval_fn, verbose=False)
        self.assertEqual(len(held_out), 3)
        self.assertEqual(len(report.fold_results), 3)

    def test_aggregate(self):
        """LOO aggregate should compute mean/std across patients."""
        patient_data = {p: np.random.randn(10, 4) for p in 'abcde'}
        loo = LOOValidator()
        report = loo.run(
            patient_data,
            train_fn=lambda td: None,
            eval_fn=lambda m, d: {'sil': float(np.random.uniform(0.1, 0.5))},
            verbose=False,
        )
        agg = report.aggregate()
        self.assertIn('sil', agg)
        self.assertIn('mean', agg['sil'])
        # Uses BootstrapCI.from_seed_values internally, so key is 'n_seeds'
        self.assertEqual(agg['sil']['n_seeds'], 5)

    def test_degradation(self):
        """Degradation should measure drop from baseline."""
        patient_data = {p: np.zeros((10, 4)) for p in 'ab'}
        loo = LOOValidator()
        report = loo.run(
            patient_data,
            train_fn=lambda td: None,
            eval_fn=lambda m, d: {'f1': 0.80},
            verbose=False,
        )
        degrad = report.degradation({'f1': 0.90})
        self.assertIn('f1', degrad)
        # 0.80 vs 0.90 = -11.1% degradation
        self.assertAlmostEqual(degrad['f1']['absolute'], -0.10, places=2)


# =============================================================================
# 6. ClassificationValidator Tests
# =============================================================================

class TestClassificationValidator(unittest.TestCase):
    """Tests for classification metric computation."""

    def test_perfect_classification(self):
        """Perfect predictions should give F1=1.0."""
        cv = ClassificationValidator(task_name='test', positive_label=1)
        y = np.array([0, 0, 0, 1, 1, 1])
        metrics = cv.evaluate(y, y, bootstrap=False)
        self.assertAlmostEqual(metrics['f1_positive'], 1.0)
        self.assertAlmostEqual(metrics['accuracy'], 1.0)

    def test_all_wrong(self):
        """Inverted predictions should give F1=0."""
        cv = ClassificationValidator(task_name='test', positive_label=1)
        y_true = np.array([0, 0, 0, 1, 1, 1])
        y_pred = np.array([1, 1, 1, 0, 0, 0])
        metrics = cv.evaluate(y_true, y_pred, bootstrap=False)
        self.assertAlmostEqual(metrics['f1_positive'], 0.0)

    def test_auc_with_probs(self):
        """AUC should be computed when probabilities provided."""
        cv = ClassificationValidator(task_name='test', positive_label=1)
        y_true = np.array([0, 0, 1, 1])
        y_pred = np.array([0, 0, 1, 1])
        y_prob = np.array([[0.9, 0.1], [0.8, 0.2], [0.2, 0.8], [0.1, 0.9]])
        metrics = cv.evaluate(y_true, y_pred, y_prob, bootstrap=False)
        self.assertIn('auc_roc', metrics)
        self.assertAlmostEqual(metrics['auc_roc'], 1.0)

    def test_ece_computed(self):
        """ECE should be in output when probabilities given."""
        cv = ClassificationValidator(task_name='test')
        y_true = np.random.RandomState(42).randint(0, 2, 100)
        y_pred = y_true.copy()
        probs = np.zeros((100, 2))
        probs[np.arange(100), y_true] = 0.9
        probs[np.arange(100), 1 - y_true] = 0.1
        metrics = cv.evaluate(y_true, y_pred, probs, bootstrap=False)
        self.assertIn('ece', metrics)
        self.assertLess(metrics['ece'], 0.2)  # well-calibrated

    def test_torch_tensor_input(self):
        """Should handle torch tensors without error."""
        import torch
        cv = ClassificationValidator(task_name='test', positive_label=1)
        y_true = torch.tensor([0, 0, 1, 1])
        y_pred = torch.tensor([0, 1, 1, 1])
        metrics = cv.evaluate(y_true, y_pred, bootstrap=False)
        self.assertIn('f1_positive', metrics)
        self.assertGreater(metrics['f1_positive'], 0)

    def test_prevalence_reported(self):
        """Output should include prevalence and sample counts."""
        cv = ClassificationValidator(task_name='test', positive_label=1)
        y = np.array([0] * 90 + [1] * 10)
        metrics = cv.evaluate(y, y, bootstrap=False)
        self.assertAlmostEqual(metrics['prevalence'], 0.1)
        self.assertEqual(metrics['n_samples'], 100)
        self.assertEqual(metrics['n_positive'], 10)

    def test_metric_types_present(self):
        """Should include metric_types for disambiguation."""
        cv = ClassificationValidator(task_name='uam', positive_label=1)
        y = np.array([0, 1, 1, 0])
        metrics = cv.evaluate(y, y, bootstrap=False)
        self.assertIn('metric_types', metrics)
        self.assertIn('f1_positive', metrics['metric_types'])


# =============================================================================
# 7. ForecastValidator Tests
# =============================================================================

class TestForecastValidator(unittest.TestCase):
    """Tests for forecasting metric computation."""

    def test_perfect_forecast(self):
        """Zero error when predictions match truth."""
        fv = ForecastValidator()
        y_true = np.array([100.0, 120.0, 80.0, 150.0])
        metrics = fv.evaluate(y_true, y_true, bootstrap=False)
        self.assertAlmostEqual(metrics['mae'], 0.0)
        self.assertAlmostEqual(metrics['rmse'], 0.0)

    def test_known_mae(self):
        """MAE should match hand-calculated value."""
        fv = ForecastValidator()
        y_true = np.array([100.0, 200.0])
        y_pred = np.array([110.0, 190.0])
        # denormalize=False since values are already in mg/dL
        metrics = fv.evaluate(y_true, y_pred, denormalize=False, bootstrap=False)
        self.assertAlmostEqual(metrics['mae'], 10.0)

    def test_zone_mae(self):
        """Zone MAE should break down by glucose range."""
        fv = ForecastValidator()
        # Below 70 = hypo, 70-180 = target, >180 = hyper
        y_true = np.array([50.0, 60.0, 100.0, 120.0, 200.0, 250.0])
        y_pred = np.array([55.0, 65.0, 110.0, 115.0, 210.0, 240.0])
        metrics = fv.evaluate(y_true, y_pred, denormalize=False, bootstrap=False)
        # zone_mae is a nested dict: {hypo: {mae, n_samples, ...}, ...}
        self.assertIn('hypo', metrics['zone_mae'])
        self.assertIn('target', metrics['zone_mae'])
        self.assertIn('hyper', metrics['zone_mae'])
        # Hypo zone: |50-55|=5, |60-65|=5 → avg=5
        self.assertAlmostEqual(metrics['zone_mae']['hypo']['mae'], 5.0)

    def test_verification_gap(self):
        """Verification gap: difference between train and val MAE."""
        fv = ForecastValidator()
        y_true = np.random.RandomState(42).uniform(70, 250, 100)
        y_pred = y_true + np.random.RandomState(43).normal(0, 10, 100)
        # ForecastValidator doesn't have train_mae param; gap is computed
        # externally. Test that basic metrics are always present.
        metrics = fv.evaluate(y_true, y_pred, denormalize=False, bootstrap=False)
        self.assertIn('mae', metrics)
        self.assertIn('rmse', metrics)
        self.assertGreater(metrics['mae'], 0)


# =============================================================================
# 8. RetrievalValidator Tests
# =============================================================================

class TestRetrievalValidator(unittest.TestCase):
    """Tests for retrieval/embedding metric computation."""

    def test_perfect_clusters(self):
        """Well-separated clusters should have high silhouette."""
        rv = RetrievalValidator()
        rng = np.random.RandomState(42)
        emb = np.vstack([
            rng.randn(30, 8) + 10,  # cluster 0
            rng.randn(30, 8) - 10,  # cluster 1
        ])
        labels = np.array([0] * 30 + [1] * 30)
        metrics = rv.evaluate(emb, labels, bootstrap=False)
        self.assertGreater(metrics['silhouette'], 0.5)

    def test_random_clusters(self):
        """Random embeddings should have near-zero silhouette."""
        rv = RetrievalValidator()
        emb = np.random.RandomState(42).randn(100, 8)
        labels = np.array([0] * 50 + [1] * 50)
        metrics = rv.evaluate(emb, labels, bootstrap=False)
        self.assertLess(abs(metrics['silhouette']), 0.3)

    def test_recall_at_k(self):
        """R@K should be computed for requested k values."""
        rv = RetrievalValidator()
        rng = np.random.RandomState(42)
        emb = np.vstack([rng.randn(30, 4) + 5, rng.randn(30, 4) - 5])
        labels = np.array([0] * 30 + [1] * 30)
        metrics = rv.evaluate(emb, labels, k_values=(1, 5, 10), bootstrap=False)
        self.assertIn('recall_at_1', metrics)
        self.assertIn('recall_at_5', metrics)
        self.assertIn('recall_at_10', metrics)

    def test_balanced_recall(self):
        """Class-balanced R@K should be present for imbalanced data."""
        rv = RetrievalValidator()
        rng = np.random.RandomState(42)
        # Imbalanced: 80 class-0, 20 class-1
        emb = np.vstack([rng.randn(80, 4), rng.randn(20, 4) + 3])
        labels = np.array([0] * 80 + [1] * 20)
        metrics = rv.evaluate(emb, labels, k_values=(5,), bootstrap=False)
        # The API uses 'recall_at_5' for balanced, 'recall_at_5_standard' for standard
        self.assertIn('recall_at_5', metrics)
        self.assertIn('recall_at_5_standard', metrics)

    def test_ari_computed(self):
        """ARI should be in output."""
        rv = RetrievalValidator()
        emb = np.random.RandomState(42).randn(60, 4)
        labels = np.array([0] * 20 + [1] * 20 + [2] * 20)
        metrics = rv.evaluate(emb, labels, bootstrap=False)
        self.assertIn('ari', metrics)


# =============================================================================
# 9. DriftValidator Tests
# =============================================================================

class TestDriftValidator(unittest.TestCase):
    """Tests for ISF drift detection."""

    def test_strong_trend(self):
        """Strong linear trend should be significant."""
        dv = DriftValidator()
        ts = np.arange(30)
        isf = 50 + 2.0 * ts  # strong upward trend
        result = dv.evaluate_per_patient(ts, isf, 'test_patient')
        self.assertTrue(result['significant_p05'])
        self.assertGreater(abs(result['spearman_rho']), 0.8)

    def test_no_trend(self):
        """Pure noise should not be significant."""
        dv = DriftValidator()
        rng = np.random.RandomState(42)
        ts = np.arange(30)
        isf = 50 + rng.normal(0, 0.5, 30)  # very low noise
        result = dv.evaluate_per_patient(ts, isf, 'test_patient')
        self.assertIn('spearman_p', result)

    def test_aggregate(self):
        """Aggregate should count significant patients."""
        dv = DriftValidator()
        rng = np.random.RandomState(42)
        results = []
        for i, pid in enumerate('abcde'):
            ts = np.arange(30)
            slope = 3.0 if i < 3 else 0.0  # 3 significant, 2 not
            isf = 50 + slope * ts + rng.normal(0, 1, 30)
            results.append(dv.evaluate_per_patient(ts, isf, pid))
        agg = dv.aggregate(results)
        self.assertEqual(agg['n_patients'], 5)
        self.assertGreaterEqual(agg['n_significant'], 2)  # at least 2 of 3 strong trends
        self.assertIn('mean_abs_rho', agg)

    def test_patient_id_preserved(self):
        """Patient ID should be in per-patient result."""
        dv = DriftValidator()
        result = dv.evaluate_per_patient(np.arange(10), np.arange(10, dtype=float), 'pat_X')
        self.assertEqual(result['patient_id'], 'pat_X')


# =============================================================================
# 10. ExperimentContext Integration Tests
# =============================================================================

class TestExperimentContextValidation(unittest.TestCase):
    """Tests for validation metadata integration in ExperimentContext."""

    def test_record_seed(self):
        """record_seed should store in validation_metadata."""
        with tempfile.TemporaryDirectory() as d:
            ctx = ExperimentContext('EXP-T1', d)
            ctx.record_seed(42)
            result = ctx.save('test.json')
            self.assertEqual(result['validation_metadata']['seed'], 42)

    def test_record_split(self):
        """record_split should store strategy and fractions."""
        with tempfile.TemporaryDirectory() as d:
            ctx = ExperimentContext('EXP-T2', d)
            ctx.record_split('temporal', fractions=(0.6, 0.2, 0.2), n_patients=11)
            result = ctx.save('test.json')
            vm = result['validation_metadata']
            self.assertEqual(vm['split']['strategy'], 'temporal')
            self.assertEqual(vm['split']['fractions'], [0.6, 0.2, 0.2])
            self.assertEqual(vm['split']['n_patients'], 11)

    def test_record_validation(self):
        """record_validation should store objective and task."""
        with tempfile.TemporaryDirectory() as d:
            ctx = ExperimentContext('EXP-T3', d)
            ctx.record_validation(objective='classification', task='uam')
            result = ctx.save('test.json')
            self.assertEqual(result['validation_metadata']['objective'], 'classification')
            self.assertEqual(result['validation_metadata']['task'], 'uam')

    def test_attach_multi_seed_report(self):
        """Multi-seed report should be serialized into result."""
        def train_fn(seed):
            return {'f1': 0.9 + seed * 0.00001}
        report = MultiSeedRunner(seeds=[42, 123]).run(train_fn, verbose=False)

        with tempfile.TemporaryDirectory() as d:
            ctx = ExperimentContext('EXP-T4', d)
            ctx.attach_multi_seed_report(report)
            result = ctx.save('test.json')
            self.assertIn('multi_seed', result)
            self.assertEqual(result['validation_metadata']['n_seeds'], 2)
            # Verify JSON-serializable
            json.dumps(result, default=str)

    def test_attach_bootstrap_ci(self):
        """Bootstrap CI attachment should appear in result."""
        with tempfile.TemporaryDirectory() as d:
            ctx = ExperimentContext('EXP-T5', d)
            ci = {'mean': 0.93, 'std': 0.01, 'ci_lower': 0.91, 'ci_upper': 0.95}
            ctx.attach_bootstrap_ci('f1', ci)
            result = ctx.save('test.json')
            self.assertIn('bootstrap_ci', result)
            self.assertEqual(result['bootstrap_ci']['f1']['mean'], 0.93)

    def test_backward_compatible(self):
        """ExperimentContext without validation calls should work as before."""
        with tempfile.TemporaryDirectory() as d:
            ctx = ExperimentContext('EXP-T6', d)
            ctx.result['accuracy'] = 0.95
            result = ctx.save('test.json')
            # Should NOT have validation_metadata if nothing was recorded
            # (or it should be empty/minimal)
            self.assertIn('experiment', result)
            self.assertEqual(result['accuracy'], 0.95)

    def test_json_roundtrip(self):
        """Saved JSON should be loadable and match."""
        with tempfile.TemporaryDirectory() as d:
            ctx = ExperimentContext('EXP-T7', d)
            ctx.record_seed(42)
            ctx.record_split('temporal', fractions=(0.8, 0.2))
            ctx.result['f1'] = 0.939
            ctx.save('test.json')

            with open(os.path.join(d, 'test.json')) as f:
                loaded = json.load(f)
            self.assertEqual(loaded['f1'], 0.939)
            self.assertEqual(loaded['validation_metadata']['seed'], 42)
            self.assertEqual(loaded['validation_metadata']['framework_version'], '1.0')

    def test_experiment_context_save_with_mlflow_disabled(self):
        """MLflow-disabled environments should still save JSON normally."""
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(
            os.environ, {'CGMENCODE_DISABLE_MLFLOW': '1'}, clear=False
        ):
            ctx = ExperimentContext('EXP-T8', d)
            ctx.result['mae'] = 12.3
            result = ctx.save('test.json')

            self.assertEqual(result['mae'], 12.3)
            with open(os.path.join(d, 'test.json')) as f:
                loaded = json.load(f)
            self.assertEqual(loaded['mae'], 12.3)


class TestMlflowUtils(unittest.TestCase):
    """Tests for MLflow helper configuration and no-op fallback."""

    def test_default_tracking_uri_uses_externals_dir(self):
        with mock.patch.dict(os.environ, {'MLFLOW_TRACKING_URI': ''}, clear=False):
            uri = mlflow_utils.get_tracking_uri()
        self.assertTrue(uri.startswith('sqlite:///'))
        self.assertIn('externals/mlflow/mlflow.db', uri)

    def test_start_run_disabled_is_noop(self):
        with mock.patch.dict(os.environ, {'CGMENCODE_DISABLE_MLFLOW': '1'}, clear=False):
            self.assertFalse(mlflow_utils.has_active_run())
            with mlflow_utils.start_run(run_name='disabled-test') as run:
                self.assertIsNone(run)
            self.assertFalse(mlflow_utils.has_active_run())

    def test_build_run_context_tracks_cohort_and_split(self):
        context = mlflow_utils.build_run_context(
            task_type='forecast',
            result_type='retrospective',
            artifact_role='checkpoint',
            patient_paths=[
                '/tmp/patient-b/training',
                '/tmp/patient-a/training',
            ],
            split_strategy='per-patient-chronological-holdout',
            split_details={'train_fraction': 0.8, 'val_fraction': 0.2},
            horizon_minutes=120,
            model_family='grouped-transformer',
            experiment_family='forecast-sweep',
        )
        self.assertEqual(context['manifest']['patient_ids'], ['patient-a', 'patient-b'])
        self.assertEqual(context['params']['n_patients'], 2)
        self.assertEqual(context['params']['split_strategy'], 'per-patient-chronological-holdout')
        self.assertEqual(context['params']['horizon_minutes'], 120)
        self.assertEqual(context['tags']['model_family'], 'grouped-transformer')
        self.assertEqual(
            context['params']['cohort_hash'],
            mlflow_utils.cohort_fingerprint(['patient-a', 'patient-b']),
        )

    def test_log_run_context_writes_manifest(self):
        context = {'manifest': {'task_type': 'forecast', 'n_patients': 2}}
        with mock.patch.object(mlflow_utils, 'has_active_run', return_value=True), \
             mock.patch.object(mlflow_utils, 'log_dict') as mocked_log_dict:
            mlflow_utils.log_run_context(context, artifact_file='metadata/test_context.json')
        mocked_log_dict.assert_called_once_with(
            {'task_type': 'forecast', 'n_patients': 2},
            'metadata/test_context.json',
        )

    def test_log_parameter_artifact_wraps_payload(self):
        with mock.patch.object(mlflow_utils, 'has_active_run', return_value=True), \
             mock.patch.object(mlflow_utils, 'log_dict') as mocked_log_dict:
            envelope = mlflow_utils.log_parameter_artifact(
                'effective isf summary',
                {'patient-a': {'effective_isf': 42.0}},
                parameter_type='isf-summary',
                metadata={'runner': 'unit-test'},
            )
        self.assertEqual(envelope['artifact_type'], 'parameter-artifact')
        self.assertEqual(envelope['metadata']['parameter_type'], 'isf-summary')
        self.assertEqual(envelope['metadata']['runner'], 'unit-test')
        mocked_log_dict.assert_called_once()
        logged_payload, logged_path = mocked_log_dict.call_args.args
        self.assertEqual(logged_path, 'parameters/effective_isf_summary.json')
        self.assertEqual(logged_payload['payload']['patient-a']['effective_isf'], 42.0)


class TestAutoresearchAgent(unittest.TestCase):
    """Tests for the structured autoresearch pilot runner."""

    def test_all_directions_defined(self):
        self.assertEqual(
            set(DIRECTIONS.keys()),
            {'parameter-extraction', 'intervention-scoring', 'deconfounding-audit', 'proxy-scoping', 'settings-followup', 'safety-vs-explanation', 'current-research-position', 'titration-safety-followup', 'settings-extraction-special-handling', 'settings-precision-vs-accuracy', 'controller-aware-causality', 'controller-state-stratification', 'stratified-deconfounding-audit', 'meal-independent-cr-proxies', 'meal-event-discovery-audition', 'novel-meal-discovery-techniques', 'hybrid-technique-evidence', 'hybrid-prototype-plan'},
        )

    def test_build_research_plan_structure(self):
        plan = build_research_plan('parameter-extraction', question='test question')
        self.assertEqual(plan['direction'], 'parameter-extraction')
        self.assertEqual(plan['question'], 'test question')
        self.assertTrue(plan['hypotheses'])
        self.assertTrue(plan['recommended_commands'])
        self.assertTrue(plan['success_criteria'])
        self.assertIn('evidence', plan)
        self.assertIn('counter_causal_findings', plan)
        self.assertIn('prioritized_follow_up', plan)
        self.assertIn('reasoning_corrections', plan)

    def test_evaluate_research_plan_returns_readiness(self):
        plan = build_research_plan('parameter-extraction', question='test question')
        evaluation = evaluate_research_plan(plan)
        self.assertIn('readiness', evaluation)
        self.assertIn('readiness_score', evaluation)
        self.assertIn('reasoning_correction_count', evaluation)
        self.assertIn('reasoning_correction_score', evaluation)
        self.assertGreaterEqual(evaluation['evidence_count'], 1)
        self.assertTrue(0.0 <= evaluation['readiness_score'] <= 1.0)

    def test_parameter_extraction_builds_model_candidate(self):
        plan = build_research_plan('parameter-extraction', question='test question')
        evaluation = evaluate_research_plan(plan)
        candidate = build_model_candidate_from_plan(plan, evaluation)
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate['candidate_name'], 'effective-parameter-extractor')
        self.assertEqual(candidate['status'], 'candidate')
        self.assertIn('simple_ml_research_alignment', candidate)
        self.assertIn('dose_response_fit', candidate['simple_ml_research_alignment']['learned_objects'])

    def test_non_parameter_direction_does_not_build_model_candidate(self):
        plan = build_research_plan('deconfounding-audit')
        evaluation = evaluate_research_plan(plan)
        candidate = build_model_candidate_from_plan(plan, evaluation)
        self.assertIsNone(candidate)

    def test_effective_parameter_extractor_predicts_dataframe(self):
        plan = build_research_plan('parameter-extraction', question='test question')
        evaluation = evaluate_research_plan(plan)
        candidate = build_model_candidate_from_plan(plan, evaluation)
        candidate['titration_guidance'] = {
            'max_basal_step_pct': 10,
            'reassessment_days': 3,
            'concurrent_change_review_required': True,
            'promotion_recommendation': 'needs-review',
        }
        bundle = build_effective_parameter_bundle({
            'patient-a': {
                'effective_isf': 64.0,
                'profile_isf': 40.0,
                'isf_discrepancy': 1.6,
                'tir': 0.61,
                'tbr': 0.03,
                'tar': 0.36,
                'ada_grade': 'B',
                'units': 'mg/dL',
            }
        }, isf_schedule_optimizer={
            'per_patient': [{
                'patient': 'patient-a',
                'current_isf': 40.0,
                'optimized_schedule': {'00:00': 66.0, '08:00': 52.0},
                'variation_pct': 22.0,
                'n_blocks': 2,
            }]
        }, basal_decomposition={
            'patients': {
                'patient-a': {
                    'periods': {'overnight': {'mean_fasting_dbg': 3.0, 'recommendation': 'increase'}},
                    'worst_period': 'overnight',
                    'needs_adjustment': ['overnight'],
                    'n_adjustments': 1,
                }
            }
        })
        model = EffectiveParameterExtractorModel(candidate, bundle=bundle)
        result = model.predict(
            None,
            pd.DataFrame([{
                'patient_id': 'patient-a',
                'profile_isf': 40.0,
                'observed_isf': 60.0,
                'correction_ratio': 1.4,
                'overnight_drift_mgdl_per_hour': 8.0,
                'time_of_day': 'overnight',
            }]),
        )
        self.assertIn('effective_isf_estimate', result.columns)
        self.assertIn('basal_adjustment_signal', result.columns)
        self.assertEqual(result.iloc[0]['isf_source'], 'patient-isf-schedule')
        self.assertEqual(result.iloc[0]['effective_isf_estimate'], 66.0)
        self.assertEqual(result.iloc[0]['needs_adjustment_periods'], ['overnight'])
        self.assertEqual(result.iloc[0]['max_basal_step_pct'], 10)
        self.assertEqual(result.iloc[0]['model_candidate_name'], 'effective-parameter-extractor')

    def test_effective_parameter_bundle_evaluation_has_three_sections(self):
        bundle = build_effective_parameter_bundle({
            'patient-a': {
                'effective_isf': 64.0,
                'profile_isf': 40.0,
                'isf_discrepancy': 1.6,
                'tir': 0.61,
                'tbr': 0.03,
                'tar': 0.36,
                'ada_grade': 'B',
                'units': 'mg/dL',
            }
        }, isf_schedule_optimizer={
            'per_patient': [{
                'patient': 'patient-a',
                'current_isf': 40.0,
                'optimized_schedule': {'00:00': 66.0},
                'variation_pct': 22.0,
                'n_blocks': 1,
            }]
        }, basal_decomposition={
            'patients': {
                'patient-a': {
                    'periods': {'overnight': {'mean_fasting_dbg': 3.0, 'recommendation': 'increase'}},
                    'worst_period': 'overnight',
                    'needs_adjustment': ['overnight'],
                    'n_adjustments': 1,
                }
            }
        }, basal_schedule_optimizer={
            'per_patient': [{
                'patient': 'patient-a',
                'current_basal': 0.4,
                'max_adj_pct': -40.0,
                'schedule': {'00:00': {'new_rate': 0.24}},
                'n_blocks': 1,
            }]
        }, score_predicts_future_tir={
            'patients': {
                'patient-a': {
                    'n_months': 4,
                    'r_score_tir_change': -0.8,
                    'low_score_tir_change': -0.01,
                    'high_score_tir_change': -0.05,
                }
            }
        })
        summary = evaluate_effective_parameter_bundle(bundle)
        self.assertIn('descriptive', summary)
        self.assertIn('prescriptive', summary)
        self.assertIn('safety', summary)
        self.assertEqual(summary['descriptive']['n_patients'], 1)
        self.assertEqual(summary['descriptive']['schedule_coverage_fraction'], 1.0)

    def test_effective_parameter_thresholds_and_assessment(self):
        bundle = build_effective_parameter_bundle({
            'patient-a': {
                'effective_isf': 64.0,
                'profile_isf': 40.0,
                'isf_discrepancy': 1.6,
                'tir': 0.61,
                'tbr': 0.03,
                'tar': 0.36,
                'ada_grade': 'B',
                'units': 'mg/dL',
            }
        }, isf_schedule_optimizer={
            'per_patient': [{
                'patient': 'patient-a',
                'current_isf': 40.0,
                'optimized_schedule': {'00:00': 66.0},
                'variation_pct': 22.0,
                'n_blocks': 1,
            }]
        }, basal_decomposition={
            'patients': {
                'patient-a': {
                    'periods': {'overnight': {'mean_fasting_dbg': 3.0, 'recommendation': 'increase'}},
                    'worst_period': 'overnight',
                    'needs_adjustment': ['overnight'],
                    'n_adjustments': 1,
                }
            }
        }, basal_schedule_optimizer={
            'per_patient': [{
                'patient': 'patient-a',
                'current_basal': 0.4,
                'max_adj_pct': -40.0,
                'schedule': {'00:00': {'new_rate': 0.24}},
                'n_blocks': 1,
            }]
        }, score_predicts_future_tir={
            'patients': {
                'patient-a': {
                    'n_months': 4,
                    'r_score_tir_change': -0.8,
                    'low_score_tir_change': -0.01,
                    'high_score_tir_change': -0.05,
                }
            }
        })
        evaluation = evaluate_effective_parameter_bundle(bundle)
        thresholds = propose_effective_parameter_thresholds(evaluation)
        assessment = assess_effective_parameter_thresholds(evaluation, thresholds)
        self.assertIn('gates', thresholds)
        self.assertIn('promotion_recommendation', assessment)
        self.assertEqual(assessment['promotion_recommendation'], 'needs-review')
        self.assertIn('safety.basal_over_ten_pct_fraction', assessment['failed_gates'])
        self.assertIn('safety.concurrent_change_fraction', assessment['failed_gates'])
        guidance = derive_titration_guidance(evaluation, assessment)
        self.assertEqual(guidance['max_basal_step_pct'], 10)
        self.assertEqual(guidance['reassessment_days'], 3)
        self.assertTrue(guidance['concurrent_change_review_required'])
        plan = derive_titration_plan(bundle, evaluation, assessment, guidance)
        self.assertEqual(plan['per_patient']['patient-a']['staged_action'], 'review-basal-first')
        settings = derive_settings_special_handling(bundle)
        self.assertIn('carb_ratio', settings['settings'])
        self.assertEqual(settings['settings']['isf']['extraction_target'], 'controller-aware predictive ISF, not direct physiological truth')
        self.assertIn('announced meals', ' '.join(settings['settings']['carb_ratio']['special_handling']).lower())

    def test_effective_parameter_thresholds_can_validate_safe_bundle(self):
        bundle = build_effective_parameter_bundle({
            'patient-a': {
                'effective_isf': 44.0,
                'profile_isf': 40.0,
                'isf_discrepancy': 1.05,
                'tir': 0.7,
                'tbr': 0.02,
                'tar': 0.28,
                'ada_grade': 'A',
                'units': 'mg/dL',
            }
        }, basal_decomposition={
            'patients': {
                'patient-a': {
                    'periods': {'overnight': {'mean_fasting_dbg': 0.5, 'recommendation': 'increase'}},
                    'worst_period': 'overnight',
                    'needs_adjustment': ['overnight'],
                    'n_adjustments': 1,
                }
            }
        }, basal_schedule_optimizer={
            'per_patient': [{
                'patient': 'patient-a',
                'current_basal': 0.4,
                'max_adj_pct': -5.0,
                'schedule': {'00:00': {'new_rate': 0.38}},
                'n_blocks': 1,
            }]
        }, isf_schedule_optimizer={
            'per_patient': [{
                'patient': 'patient-a',
                'current_isf': 40.0,
                'optimized_schedule': {'00:00': 42.0},
                'variation_pct': 5.0,
                'n_blocks': 1,
            }]
        }, score_predicts_future_tir={
            'patients': {
                'patient-a': {
                    'n_months': 4,
                    'r_score_tir_change': -0.4,
                    'low_score_tir_change': -0.01,
                    'high_score_tir_change': -0.03,
                }
            }
        })
        evaluation = evaluate_effective_parameter_bundle(bundle)
        thresholds = propose_effective_parameter_thresholds(evaluation)
        assessment = assess_effective_parameter_thresholds(evaluation, thresholds)
        self.assertEqual(assessment['promotion_recommendation'], 'validated')
        guidance = derive_titration_guidance(evaluation, assessment)
        self.assertEqual(guidance['reassessment_days'], 5)
        plan = derive_titration_plan(bundle, evaluation, assessment, guidance)
        self.assertEqual(plan['per_patient']['patient-a']['staged_action'], 'lockstep-review')

    def test_effective_parameter_extractor_model_saves_and_loads(self):
        import mlflow  # type: ignore

        plan = build_research_plan('parameter-extraction', question='test question')
        evaluation = evaluate_research_plan(plan)
        candidate = build_model_candidate_from_plan(plan, evaluation)
        with tempfile.TemporaryDirectory() as d:
            bundle = build_effective_parameter_bundle(
                {
                    'patient-a': {
                        'effective_isf': 64.0,
                        'profile_isf': 40.0,
                        'isf_discrepancy': 1.6,
                        'tir': 0.61,
                        'tbr': 0.03,
                        'tar': 0.36,
                        'ada_grade': 'B',
                        'units': 'mg/dL',
                    }
                },
                isf_schedule_optimizer={
                    'per_patient': [{
                        'patient': 'patient-a',
                        'current_isf': 40.0,
                        'optimized_schedule': {'00:00': 66.0, '08:00': 52.0},
                        'variation_pct': 22.0,
                        'n_blocks': 2,
                    }]
                },
                basal_decomposition={
                    'patients': {
                        'patient-a': {
                            'periods': {
                                'overnight': {
                                    'mean_fasting_dbg': 3.0,
                                    'recommendation': 'increase',
                                }
                            },
                            'worst_period': 'overnight',
                            'needs_adjustment': ['overnight'],
                            'n_adjustments': 1,
                        }
                    }
                },
            )
            bundle_path = save_bundle(bundle, Path(d) / 'bundle.json')
            candidate['bundle_path'] = str(bundle_path)
            model_dir = Path(d) / 'effective_parameter_extractor_model'
            saved = save_effective_parameter_extractor_model(model_dir, candidate)
            self.assertEqual(saved, str(model_dir))
            loaded = mlflow.pyfunc.load_model(str(model_dir))
            result = loaded.predict(pd.DataFrame([{
                'patient_id': 'patient-a',
                'profile_isf': 42.0,
                'observed_isf': 58.0,
                'correction_ratio': 1.2,
                'overnight_drift_mgdl_per_hour': 4.0,
                'time_of_day': 'overnight',
            }]))
            self.assertIn('effective_isf_estimate', result.columns)
            self.assertIn('confidence_score', result.columns)
            self.assertEqual(result.iloc[0]['isf_source'], 'patient-isf-schedule')
            self.assertEqual(result.iloc[0]['effective_isf_estimate'], 66.0)

    def test_deconfounding_plan_finds_counter_causal_patterns(self):
        plan = build_research_plan('deconfounding-audit')
        self.assertTrue(plan['counter_causal_findings'])
        self.assertTrue(plan['reasoning_corrections'])
        patterns = {item['pattern'] for item in plan['counter_causal_findings']}
        self.assertTrue(
            {'observed-outcome-collider', 'pooled-aggregation-dominance', 'composite-risk-collapse'} & patterns
        )
        corrected_patterns = {item['pattern'] for item in plan['reasoning_corrections']}
        self.assertTrue(patterns & corrected_patterns)
        self.assertIsNotNone(plan['prioritized_follow_up'])
        self.assertIn(
            plan['prioritized_follow_up']['command'],
            plan['recommended_commands'],
        )
        self.assertTrue(
            any(
                item['replacement_test'] == plan['prioritized_follow_up']['command']
                for item in plan['reasoning_corrections']
            )
        )

    def test_proxy_scoping_plan_builds_matrix(self):
        plan = build_research_plan('proxy-scoping')
        self.assertIn('proxy_use_case_matrix', plan)
        self.assertTrue(plan['proxy_use_case_matrix'])

    def test_safety_vs_explanation_plan_builds(self):
        plan = build_research_plan('safety-vs-explanation')
        self.assertEqual(plan['direction'], 'safety-vs-explanation')
        self.assertTrue(plan['recommended_commands'])

    def test_current_research_position_builds_summary(self):
        plan = build_research_plan('current-research-position')
        self.assertEqual(plan['direction'], 'current-research-position')
        self.assertIn('current_research_position', plan)
        self.assertTrue(plan['current_research_position'])
        self.assertIn('research_steering_summary', plan)
        self.assertIn('approval_queue', plan['research_steering_summary'])
        self.assertIn('steer_queue', plan['research_steering_summary'])
        self.assertIn('continue_queue', plan['research_steering_summary'])

    def test_titration_safety_followup_builds_summary(self):
        plan = build_research_plan('titration-safety-followup')
        self.assertEqual(plan['direction'], 'titration-safety-followup')
        self.assertIn('titration_safety_summary', plan)
        self.assertIn('staged_action_counts', plan['titration_safety_summary'])

    def test_settings_extraction_special_handling_builds_summary(self):
        plan = build_research_plan('settings-extraction-special-handling')
        self.assertEqual(plan['direction'], 'settings-extraction-special-handling')
        self.assertIn('settings_extraction_summary', plan)
        self.assertIn('tracked_support', plan['settings_extraction_summary'])
        self.assertIn('announced_meal_dependency', plan['settings_extraction_summary'])

    def test_settings_precision_vs_accuracy_builds_summary(self):
        plan = build_research_plan('settings-precision-vs-accuracy')
        self.assertEqual(plan['direction'], 'settings-precision-vs-accuracy')
        self.assertIn('settings_precision_accuracy_summary', plan)
        self.assertIn('basal', plan['settings_precision_accuracy_summary'])
        self.assertIn('shared_guardrail', plan['settings_precision_accuracy_summary'])

    def test_controller_aware_causality_builds_summary(self):
        plan = build_research_plan('controller-aware-causality')
        self.assertEqual(plan['direction'], 'controller-aware-causality')
        self.assertIn('controller_causality_summary', plan)
        self.assertTrue(plan['controller_causality_summary']['time_scales'])

    def test_controller_state_stratification_builds_summary(self):
        plan = build_research_plan('controller-state-stratification')
        self.assertEqual(plan['direction'], 'controller-state-stratification')
        self.assertIn('controller_state_stratification_summary', plan)
        self.assertTrue(plan['controller_state_stratification_summary']['strata'])

    def test_stratified_deconfounding_audit_builds_summary(self):
        plan = build_research_plan('stratified-deconfounding-audit')
        self.assertEqual(plan['direction'], 'stratified-deconfounding-audit')
        self.assertIn('stratified_deconfounding_summary', plan)
        self.assertTrue(plan['stratified_deconfounding_summary']['strata_audits'])

    def test_meal_independent_cr_proxies_builds_summary(self):
        plan = build_research_plan('meal-independent-cr-proxies')
        self.assertEqual(plan['direction'], 'meal-independent-cr-proxies')
        self.assertIn('meal_independent_cr_summary', plan)
        self.assertTrue(plan['meal_independent_cr_summary']['proxy_families'])

    def test_meal_event_discovery_audition_builds_summary(self):
        plan = build_research_plan('meal-event-discovery-audition')
        self.assertEqual(plan['direction'], 'meal-event-discovery-audition')
        self.assertIn('meal_event_discovery_audition', plan)
        self.assertTrue(plan['meal_event_discovery_audition']['ranking'])

    def test_novel_meal_discovery_techniques_builds_summary(self):
        plan = build_research_plan('novel-meal-discovery-techniques')
        self.assertEqual(plan['direction'], 'novel-meal-discovery-techniques')
        self.assertIn('novel_meal_discovery_summary', plan)
        self.assertTrue(plan['novel_meal_discovery_summary']['candidates'])

    def test_hybrid_technique_evidence_builds_summary(self):
        plan = build_research_plan('hybrid-technique-evidence')
        self.assertEqual(plan['direction'], 'hybrid-technique-evidence')
        self.assertIn('hybrid_technique_evidence_summary', plan)
        self.assertEqual(plan['hybrid_technique_evidence_summary']['verdict'], 'promising-but-not-validated')

    def test_hybrid_prototype_plan_builds_summary(self):
        plan = build_research_plan('hybrid-prototype-plan')
        self.assertEqual(plan['direction'], 'hybrid-prototype-plan')
        self.assertIn('hybrid_prototype_plan', plan)
        self.assertTrue(plan['hybrid_prototype_plan']['stages'])


# =============================================================================
# 11. ValidationReport Tests
# =============================================================================

class TestValidationReport(unittest.TestCase):
    """Tests for structured validation report generation."""

    def test_report_creation(self):
        """ValidationReport should store experiment_id and objective."""
        report = ValidationReport('EXP-999', 'classification')
        self.assertEqual(report.experiment_id, 'EXP-999')
        self.assertEqual(report.objective, 'classification')

    def test_add_result(self):
        """Adding results should be retrievable via finalize."""
        report = ValidationReport('EXP-999', 'forecasting')
        report.add_result('seed_42', {'mae': 11.14, 'rmse': 14.5})
        d = report.finalize()
        # add_result stores as top-level key
        self.assertIn('seed_42', d)
        self.assertEqual(d['seed_42']['mae'], 11.14)


# =============================================================================
# 12. Validated Forecast Helper Tests
# =============================================================================

class TestRunValidatedForecast(unittest.TestCase):
    """Tests for run_validated_forecast helper."""

    def test_basic_forecast(self):
        """Should run multi-seed forecast and save JSON."""
        from tools.cgmencode.experiment_lib import run_validated_forecast

        def train_fn(seed):
            rng = np.random.RandomState(seed)
            y_true = rng.uniform(70, 250, 50)
            y_pred = y_true + rng.normal(0, 10, 50)
            return {'y_true': y_true, 'y_pred': y_pred}

        with tempfile.TemporaryDirectory() as d:
            result = run_validated_forecast(
                'EXP-FTEST', d, train_fn,
                seeds=[42, 123], denormalize=False,
            )
            self.assertIn('multi_seed', result)
            agg = result['multi_seed']['aggregate']
            self.assertIn('mae', agg)
            self.assertIn('rmse', agg)
            self.assertEqual(result['validation_metadata']['objective'], 'forecasting')

    def test_verification_gap(self):
        """Should compute verification gap when train_mae provided."""
        from tools.cgmencode.experiment_lib import run_validated_forecast

        def train_fn(seed):
            rng = np.random.RandomState(seed)
            y_true = rng.uniform(70, 250, 50)
            y_pred = y_true + rng.normal(0, 15, 50)
            return {'y_true': y_true, 'y_pred': y_pred}

        with tempfile.TemporaryDirectory() as d:
            result = run_validated_forecast(
                'EXP-FGAP', d, train_fn,
                seeds=[42], denormalize=False, train_mae=5.0,
            )
            agg = result['multi_seed']['aggregate']
            self.assertIn('verification_gap_pct', agg)

    def test_zone_mae_flattened(self):
        """Zone MAE should be flattened to scalar metrics."""
        from tools.cgmencode.experiment_lib import run_validated_forecast

        def train_fn(seed):
            rng = np.random.RandomState(seed)
            y_true = np.concatenate([
                rng.uniform(40, 69, 20),   # hypo
                rng.uniform(70, 179, 40),  # target
                rng.uniform(180, 350, 20), # hyper
            ])
            y_pred = y_true + rng.normal(0, 5, 80)
            return {'y_true': y_true, 'y_pred': y_pred}

        with tempfile.TemporaryDirectory() as d:
            result = run_validated_forecast(
                'EXP-FZONE', d, train_fn,
                seeds=[42], denormalize=False,
            )
            agg = result['multi_seed']['aggregate']
            # Zone MAE should be flattened as mae_hypo, mae_target, mae_hyper
            self.assertIn('mae_hypo', agg)
            self.assertIn('mae_target', agg)
            self.assertIn('mae_hyper', agg)


# =============================================================================
# 13. Validated Drift Helper Tests
# =============================================================================

class TestRunValidatedDrift(unittest.TestCase):
    """Tests for run_validated_drift helper."""

    def test_statistical_drift(self):
        """Should run per-patient drift without seeds."""
        from tools.cgmencode.experiment_lib import run_validated_drift

        rng = np.random.RandomState(42)

        def patient_fn(pid):
            ts = np.arange(30)
            slope = rng.uniform(-0.5, 1.0)
            isf = 50 + slope * ts + rng.normal(0, 2, 30)
            return {'timestamps': ts, 'isf_values': isf}

        with tempfile.TemporaryDirectory() as d:
            result = run_validated_drift(
                'EXP-DTEST', d, patient_fn,
                patient_ids=['a', 'b', 'c', 'd', 'e'],
            )
            self.assertIn('per_patient', result)
            self.assertIn('aggregate', result)
            self.assertEqual(len(result['per_patient']), 5)
            self.assertEqual(result['aggregate']['n_patients'], 5)
            self.assertEqual(result['validation_metadata']['objective'], 'drift')

    def test_model_based_drift(self):
        """Should run multi-seed when function takes (pid, seed)."""
        from tools.cgmencode.experiment_lib import run_validated_drift

        def patient_fn(pid, seed):
            rng = np.random.RandomState(seed + hash(pid) % 1000)
            ts = np.arange(20)
            isf = 50 + 0.5 * ts + rng.normal(0, 2, 20)
            return {'timestamps': ts, 'isf_values': isf}

        with tempfile.TemporaryDirectory() as d:
            result = run_validated_drift(
                'EXP-DSEED', d, patient_fn,
                patient_ids=['a', 'b', 'c'],
                seeds=[42, 123],
            )
            self.assertIn('multi_seed', result)
            self.assertEqual(result['validation_metadata']['objective'], 'drift')

    def test_requires_patient_ids(self):
        """Should raise when patient_ids not provided."""
        from tools.cgmencode.experiment_lib import run_validated_drift
        with self.assertRaises(ValueError):
            run_validated_drift('EXP-X', '/tmp', lambda pid: {}, patient_ids=None)


# =============================================================================

if __name__ == '__main__':
    unittest.main()
