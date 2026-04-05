"""
validation_framework.py — Rigorous validation infrastructure for auto-research.

Provides reusable building blocks so that experiment functions get
multi-seed replication, temporal hold-out, confidence intervals, and
leave-one-out validation *ergonomically* — without reimplementing
evaluation logic in each experiment.

Usage:
    from tools.cgmencode.validation_framework import (
        MultiSeedRunner, TemporalSplitter, StratifiedTemporalSplitter,
        BootstrapCI, LOOValidator, ValidationReport,
    )

    # Multi-seed with confidence intervals
    runner = MultiSeedRunner(seeds=[42, 123, 456])
    report = runner.run(train_fn, eval_fn, data)

    # 3-way temporal split
    splitter = TemporalSplitter(fractions=(0.6, 0.2, 0.2))
    train, val, test = splitter.split(windows)

    # Bootstrap CI for any metric
    ci = BootstrapCI.compute(y_true, y_pred, metric_fn)
"""

import json
import os
import time
import random
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np

# Standard seed set matching EXP-302 convention
STANDARD_SEEDS = [42, 123, 456, 789, 1337]


# ── Bootstrap Confidence Intervals ──────────────────────────────────────

class BootstrapCI:
    """Non-parametric bootstrap confidence intervals for any metric."""

    @staticmethod
    def compute(y_true: np.ndarray, y_pred: np.ndarray,
                metric_fn: Callable[[np.ndarray, np.ndarray], float],
                n_bootstrap: int = 1000, ci: float = 0.95,
                seed: int = 42) -> Dict[str, float]:
        """Compute bootstrap CI for a metric function.

        Args:
            y_true: Ground truth labels/values.
            y_pred: Predicted labels/values.
            metric_fn: f(y_true, y_pred) -> float.
            n_bootstrap: Number of bootstrap samples.
            ci: Confidence level (default 0.95 = 95% CI).
            seed: Random seed for reproducibility.

        Returns:
            Dict with mean, std, ci_lower, ci_upper, point_estimate.
        """
        rng = np.random.RandomState(seed)
        n = len(y_true)
        if n == 0:
            return {
                'point_estimate': float('nan'),
                'mean': float('nan'), 'std': float('nan'),
                'ci_lower': float('nan'), 'ci_upper': float('nan'),
                'ci_level': ci, 'n_bootstrap': n_bootstrap,
            }
        point_estimate = float(metric_fn(y_true, y_pred))

        bootstraps = np.empty(n_bootstrap)
        for i in range(n_bootstrap):
            idx = rng.choice(n, n, replace=True)
            try:
                bootstraps[i] = metric_fn(y_true[idx], y_pred[idx])
            except (ValueError, ZeroDivisionError):
                bootstraps[i] = np.nan

        valid = bootstraps[~np.isnan(bootstraps)]
        if len(valid) == 0:
            return {
                'point_estimate': point_estimate,
                'mean': point_estimate, 'std': float('nan'),
                'ci_lower': float('nan'), 'ci_upper': float('nan'),
                'ci_level': ci, 'n_bootstrap': n_bootstrap,
            }

        alpha = (1 - ci) / 2
        return {
            'point_estimate': point_estimate,
            'mean': float(np.mean(valid)),
            'std': float(np.std(valid)),
            'ci_lower': float(np.percentile(valid, alpha * 100)),
            'ci_upper': float(np.percentile(valid, (1 - alpha) * 100)),
            'ci_level': ci,
            'n_bootstrap': n_bootstrap,
        }

    @staticmethod
    def from_seed_values(values: Sequence[float],
                         ci: float = 0.95) -> Dict[str, float]:
        """Compute CI from a list of per-seed metric values.

        Useful when you have e.g. 5 F1 scores from 5 seeds.
        Uses t-distribution CI for small samples.
        """
        arr = np.array(values, dtype=float)
        n = len(arr)
        mean = float(np.mean(arr))
        std = float(np.std(arr, ddof=1)) if n > 1 else 0.0

        if n > 1:
            from scipy import stats
            t_crit = stats.t.ppf((1 + ci) / 2, df=n - 1)
            margin = t_crit * std / np.sqrt(n)
        else:
            margin = 0.0

        return {
            'mean': mean,
            'std': std,
            'ci_lower': mean - margin,
            'ci_upper': mean + margin,
            'ci_level': ci,
            'n_seeds': n,
            'values': [float(v) for v in arr],
        }


# ── Temporal Splitting ──────────────────────────────────────────────────

@dataclass
class SplitResult:
    """Result of a data split operation, with full metadata."""
    train: np.ndarray
    val: np.ndarray
    test: Optional[np.ndarray] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def has_test(self) -> bool:
        return self.test is not None

    def summary(self) -> Dict[str, Any]:
        result = {
            'n_train': len(self.train),
            'n_val': len(self.val),
            'split_strategy': self.metadata.get('strategy', 'unknown'),
            'split_fractions': self.metadata.get('fractions', []),
        }
        if self.has_test:
            result['n_test'] = len(self.test)
        return result


class TemporalSplitter:
    """Chronological train/val/test split preserving temporal order.

    Per-patient windows are split chronologically (first N% train,
    next M% val, last K% test), then training set is shuffled to
    mix patients for batch diversity.
    """

    def __init__(self, fractions: Tuple[float, ...] = (0.6, 0.2, 0.2),
                 shuffle_seed: int = 42):
        assert abs(sum(fractions) - 1.0) < 1e-6, f"Fractions must sum to 1.0, got {sum(fractions)}"
        assert len(fractions) in (2, 3), "Provide 2 (train/val) or 3 (train/val/test) fractions"
        self.fractions = fractions
        self.shuffle_seed = shuffle_seed

    def split(self, per_patient_windows: List[List[np.ndarray]]) -> SplitResult:
        """Split per-patient window lists chronologically.

        Args:
            per_patient_windows: List of lists, where each inner list
                contains chronologically-ordered windows for one patient.

        Returns:
            SplitResult with train, val, and optionally test arrays.
        """
        train_all, val_all, test_all = [], [], []

        for patient_windows in per_patient_windows:
            n = len(patient_windows)
            if n == 0:
                continue

            if len(self.fractions) == 3:
                i1 = int(n * self.fractions[0])
                i2 = int(n * (self.fractions[0] + self.fractions[1]))
                train_all.extend(patient_windows[:i1])
                val_all.extend(patient_windows[i1:i2])
                test_all.extend(patient_windows[i2:])
            else:
                i1 = int(n * self.fractions[0])
                train_all.extend(patient_windows[:i1])
                val_all.extend(patient_windows[i1:])

        # Shuffle training for batch diversity
        rng = np.random.RandomState(self.shuffle_seed)
        rng.shuffle(train_all)

        train_np = np.array(train_all, dtype=np.float32) if train_all else np.empty((0,))
        val_np = np.array(val_all, dtype=np.float32) if val_all else np.empty((0,))
        test_np = np.array(test_all, dtype=np.float32) if test_all else None

        if len(self.fractions) == 2:
            test_np = None

        return SplitResult(
            train=train_np, val=val_np, test=test_np,
            metadata={
                'strategy': 'temporal',
                'fractions': list(self.fractions),
                'n_patients': len(per_patient_windows),
                'shuffle_seed': self.shuffle_seed,
            },
        )

    def split_array(self, windows: np.ndarray) -> SplitResult:
        """Split a single pre-ordered array chronologically.

        Simpler interface when windows are already in temporal order
        from a single patient or pre-concatenated.
        """
        n = len(windows)
        if len(self.fractions) == 3:
            i1 = int(n * self.fractions[0])
            i2 = int(n * (self.fractions[0] + self.fractions[1]))
            return SplitResult(
                train=windows[:i1], val=windows[i1:i2], test=windows[i2:],
                metadata={'strategy': 'temporal', 'fractions': list(self.fractions)},
            )
        else:
            i1 = int(n * self.fractions[0])
            return SplitResult(
                train=windows[:i1], val=windows[i1:],
                metadata={'strategy': 'temporal', 'fractions': list(self.fractions)},
            )


class StratifiedTemporalSplitter:
    """Temporal split that preserves class distribution in each subset.

    Critical for imbalanced tasks like hypo detection (6.4% positive).
    Splits each class independently and recombines.
    """

    def __init__(self, fractions: Tuple[float, ...] = (0.6, 0.2, 0.2),
                 shuffle_seed: int = 42):
        assert abs(sum(fractions) - 1.0) < 1e-6
        self.fractions = fractions
        self.shuffle_seed = shuffle_seed

    def split(self, windows: np.ndarray, labels: np.ndarray) -> SplitResult:
        """Split preserving class distribution.

        Windows must be in temporal order. Each class is split
        independently at the same fractions, then recombined.

        Args:
            windows: Array of shape (N, T, C) in temporal order.
            labels: Array of shape (N,) with class labels.

        Returns:
            SplitResult with balanced class distribution in each split.
        """
        unique_classes = np.unique(labels)
        train_idx, val_idx, test_idx = [], [], []

        for cls in unique_classes:
            cls_mask = labels == cls
            cls_indices = np.where(cls_mask)[0]  # already in temporal order
            n_cls = len(cls_indices)

            if len(self.fractions) == 3:
                i1 = int(n_cls * self.fractions[0])
                i2 = int(n_cls * (self.fractions[0] + self.fractions[1]))
                train_idx.extend(cls_indices[:i1])
                val_idx.extend(cls_indices[i1:i2])
                test_idx.extend(cls_indices[i2:])
            else:
                i1 = int(n_cls * self.fractions[0])
                train_idx.extend(cls_indices[:i1])
                val_idx.extend(cls_indices[i1:])

        # Shuffle training for batch diversity
        rng = np.random.RandomState(self.shuffle_seed)
        train_idx = np.array(train_idx)
        rng.shuffle(train_idx)
        val_idx = np.array(val_idx)
        test_idx = np.array(test_idx) if test_idx else None

        train_labels = labels[train_idx]
        val_labels = labels[val_idx]

        prevalence_info = {
            'train_prevalence': {},
            'val_prevalence': {},
        }
        for cls in unique_classes:
            c = int(cls)
            prevalence_info['train_prevalence'][c] = float((train_labels == cls).mean())
            prevalence_info['val_prevalence'][c] = float((val_labels == cls).mean())

        test_np = windows[test_idx] if test_idx is not None and len(test_idx) > 0 else None
        test_labels_np = labels[test_idx] if test_idx is not None and len(test_idx) > 0 else None

        if test_np is not None:
            for cls in unique_classes:
                c = int(cls)
                prevalence_info['test_prevalence'] = prevalence_info.get('test_prevalence', {})
                prevalence_info['test_prevalence'][c] = float((labels[test_idx] == cls).mean())

        result = SplitResult(
            train=windows[train_idx], val=windows[val_idx], test=test_np,
            metadata={
                'strategy': 'stratified_temporal',
                'fractions': list(self.fractions),
                'n_classes': len(unique_classes),
                'shuffle_seed': self.shuffle_seed,
                **prevalence_info,
            },
        )
        # Attach labels for downstream use
        result.train_labels = train_labels
        result.val_labels = val_labels
        result.test_labels = test_labels_np
        return result


# ── Multi-Seed Runner ───────────────────────────────────────────────────

@dataclass
class SeedResult:
    """Metrics from a single seed run."""
    seed: int
    metrics: Dict[str, float]
    model_path: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


class MultiSeedRunner:
    """Run any training function across multiple seeds, aggregate metrics.

    Usage:
        runner = MultiSeedRunner(seeds=[42, 123, 456])

        def train_fn(seed):
            set_seed(seed)
            model = train(...)
            return {'f1': 0.93, 'auc': 0.96}

        report = runner.run(train_fn)
        print(report.summary)  # mean ± std, 95% CI for each metric
    """

    def __init__(self, seeds: Optional[List[int]] = None):
        self.seeds = seeds or STANDARD_SEEDS

    def run(self, train_eval_fn: Callable[[int], Dict[str, float]],
            verbose: bool = True) -> 'MultiSeedReport':
        """Run train_eval_fn for each seed, aggregate results.

        Args:
            train_eval_fn: Function that takes a seed (int) and returns
                a dict of metric_name -> metric_value. The function is
                responsible for calling set_seed(seed) internally.
            verbose: Print per-seed results.

        Returns:
            MultiSeedReport with per-seed and aggregated results.
        """
        seed_results = []

        for i, seed in enumerate(self.seeds):
            if verbose:
                print(f"  Seed {seed} ({i+1}/{len(self.seeds)})...")

            t0 = time.time()
            try:
                metrics = train_eval_fn(seed)
            except Exception as e:
                elapsed = time.time() - t0
                if verbose:
                    print(f"    → ERROR: {e} ({elapsed:.1f}s)")
                metrics = {'error': str(e)}
            else:
                elapsed = time.time() - t0

            result = SeedResult(seed=seed, metrics=metrics,
                                extra={'elapsed_seconds': round(elapsed, 1)})
            seed_results.append(result)

            if verbose:
                metric_str = ', '.join(f'{k}={v:.4f}' for k, v in metrics.items()
                                       if isinstance(v, (int, float)))
                print(f"    → {metric_str} ({elapsed:.1f}s)")

        return MultiSeedReport(seeds=self.seeds, seed_results=seed_results)


class MultiSeedReport:
    """Aggregated results from multi-seed evaluation."""

    def __init__(self, seeds: List[int], seed_results: List[SeedResult]):
        self.seeds = seeds
        self.seed_results = seed_results
        self._aggregate = None

    @property
    def metric_names(self) -> List[str]:
        """All metric names that appear across seeds."""
        names = set()
        for sr in self.seed_results:
            for k, v in sr.metrics.items():
                if isinstance(v, (int, float)):
                    names.add(k)
        return sorted(names)

    def aggregate(self, ci: float = 0.95) -> Dict[str, Dict[str, float]]:
        """Compute mean ± std and CI for each metric across seeds.

        Returns:
            Dict of metric_name -> {mean, std, ci_lower, ci_upper, values}.
        """
        if self._aggregate is not None:
            return self._aggregate

        result = {}
        for name in self.metric_names:
            values = []
            for sr in self.seed_results:
                v = sr.metrics.get(name)
                if isinstance(v, (int, float)) and not np.isnan(v):
                    values.append(float(v))

            if values:
                result[name] = BootstrapCI.from_seed_values(values, ci=ci)

        self._aggregate = result
        return result

    @property
    def summary(self) -> Dict[str, str]:
        """Human-readable summary: metric = mean ± std [ci_lower, ci_upper]."""
        agg = self.aggregate()
        lines = {}
        for name, stats in agg.items():
            lines[name] = (f"{stats['mean']:.4f} ± {stats['std']:.4f} "
                           f"[{stats['ci_lower']:.4f}, {stats['ci_upper']:.4f}]")
        return lines

    def to_dict(self) -> Dict[str, Any]:
        """Full serializable dict for JSON output."""
        return {
            'seeds': self.seeds,
            'n_seeds': len(self.seeds),
            'per_seed': [
                {'seed': sr.seed, 'metrics': sr.metrics, **sr.extra}
                for sr in self.seed_results
            ],
            'aggregate': self.aggregate(),
        }


# ── Leave-One-Out Validator ─────────────────────────────────────────────

class LOOValidator:
    """Generic leave-one-patient-out cross-validation.

    Usage:
        loo = LOOValidator(patient_ids=['a', 'b', ..., 'k'])

        def train_fn(train_data):
            model = train(...)
            return model

        def eval_fn(model, test_data):
            return {'f1': ..., 'auc': ...}

        report = loo.run(patient_data, train_fn, eval_fn)
    """

    def __init__(self, patient_ids: Optional[List[str]] = None):
        self.patient_ids = patient_ids

    def run(self, patient_data: Dict[str, Any],
            train_fn: Callable[[Dict[str, Any]], Any],
            eval_fn: Callable[[Any, Any], Dict[str, float]],
            verbose: bool = True) -> 'LOOReport':
        """Run leave-one-out cross-validation.

        Args:
            patient_data: Dict of patient_id -> data (any format the
                train_fn and eval_fn expect).
            train_fn: f(train_data_dict) -> model. Receives a dict with
                N-1 patients' data.
            eval_fn: f(model, held_out_data) -> metrics dict.
            verbose: Print per-fold results.

        Returns:
            LOOReport with per-patient and aggregate metrics.
        """
        pids = self.patient_ids or sorted(patient_data.keys())
        fold_results = []

        for i, held_out in enumerate(pids):
            if verbose:
                print(f"  LOO fold {i+1}/{len(pids)}: holding out '{held_out}'")

            train_subset = {pid: patient_data[pid]
                            for pid in pids if pid != held_out}
            test_subset = patient_data[held_out]

            t0 = time.time()
            try:
                model = train_fn(train_subset)
                metrics = eval_fn(model, test_subset)
            except Exception as e:
                if verbose:
                    print(f"    ERROR: {e}")
                metrics = {'error': str(e)}
            elapsed = time.time() - t0

            fold_results.append({
                'held_out': held_out,
                'metrics': metrics,
                'elapsed_seconds': round(elapsed, 1),
            })

            if verbose and 'error' not in metrics:
                metric_str = ', '.join(f'{k}={v:.4f}' for k, v in metrics.items()
                                       if isinstance(v, (int, float)))
                print(f"    → {metric_str} ({elapsed:.1f}s)")

        return LOOReport(patient_ids=pids, fold_results=fold_results)


class LOOReport:
    """Results from leave-one-patient-out evaluation."""

    def __init__(self, patient_ids: List[str],
                 fold_results: List[Dict[str, Any]]):
        self.patient_ids = patient_ids
        self.fold_results = fold_results

    def aggregate(self, ci: float = 0.95) -> Dict[str, Dict[str, float]]:
        """Aggregate per-fold metrics into mean ± std and CI."""
        metric_values = defaultdict(list)
        for fold in self.fold_results:
            for k, v in fold['metrics'].items():
                if isinstance(v, (int, float)) and not np.isnan(v):
                    metric_values[k].append(float(v))

        result = {}
        for name, values in metric_values.items():
            result[name] = BootstrapCI.from_seed_values(values, ci=ci)
        return result

    def degradation(self, baseline_metrics: Dict[str, float]) -> Dict[str, float]:
        """Compute LOO degradation vs baseline (e.g., full-data training).

        Returns dict of metric_name -> (loo_mean - baseline) / baseline.
        """
        agg = self.aggregate()
        degrad = {}
        for name, stats in agg.items():
            if name in baseline_metrics and baseline_metrics[name] != 0:
                delta = stats['mean'] - baseline_metrics[name]
                degrad[name] = {
                    'absolute': round(delta, 4),
                    'relative_pct': round(100 * delta / abs(baseline_metrics[name]), 2),
                    'loo_mean': stats['mean'],
                    'baseline': baseline_metrics[name],
                }
        return degrad

    def to_dict(self) -> Dict[str, Any]:
        """Full serializable dict."""
        return {
            'n_patients': len(self.patient_ids),
            'patient_ids': self.patient_ids,
            'per_patient': self.fold_results,
            'aggregate': self.aggregate(),
        }


# ── Validation Report ───────────────────────────────────────────────────

class _NumpyEncoder(json.JSONEncoder):
    """JSON encoder that handles numpy types."""
    def default(self, obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, np.bool_):
            return bool(obj)
        return super().default(obj)


class ValidationReport:
    """Standardized experiment result with full validation metadata.

    Wraps experiment results with reproducibility information so that
    every JSON output includes seed, split strategy, and CIs.
    """

    def __init__(self, experiment_id: str, objective: str):
        """
        Args:
            experiment_id: e.g. 'EXP-313'
            objective: one of 'forecast', 'classification', 'retrieval', 'drift'
        """
        self.experiment_id = experiment_id
        self.objective = objective
        self.timestamp = time.strftime('%Y-%m-%dT%H:%M:%SZ')
        self.t0 = time.time()
        self._data = {
            'experiment': experiment_id,
            'objective': objective,
            'timestamp': self.timestamp,
            'validation_metadata': {
                'framework_version': '1.0',
            },
        }
        self._multi_seed = None
        self._loo = None
        self._split = None
        self._bootstrap = {}

    def set_split(self, split_result: SplitResult):
        """Record data split metadata."""
        self._split = split_result
        self._data['validation_metadata']['split'] = split_result.summary()

    def set_multi_seed(self, report: MultiSeedReport):
        """Record multi-seed results."""
        self._multi_seed = report
        self._data['multi_seed'] = report.to_dict()
        self._data['validation_metadata']['seeds'] = report.seeds
        self._data['validation_metadata']['n_seeds'] = len(report.seeds)

    def set_loo(self, report: LOOReport,
                baseline: Optional[Dict[str, float]] = None):
        """Record LOO results."""
        self._loo = report
        self._data['loo'] = report.to_dict()
        if baseline:
            self._data['loo']['degradation'] = report.degradation(baseline)
        self._data['validation_metadata']['loo_n_patients'] = len(report.patient_ids)

    def add_bootstrap(self, metric_name: str, ci_result: Dict[str, float]):
        """Record bootstrap CI for a specific metric."""
        self._bootstrap[metric_name] = ci_result
        if 'bootstrap_ci' not in self._data:
            self._data['bootstrap_ci'] = {}
        self._data['bootstrap_ci'][metric_name] = ci_result

    def add_result(self, key: str, value: Any):
        """Add arbitrary result data."""
        self._data[key] = value

    def finalize(self) -> Dict[str, Any]:
        """Finalize and return the complete result dict."""
        self._data['elapsed_seconds'] = round(time.time() - self.t0, 1)
        return self._data

    def save(self, path: str) -> Dict[str, Any]:
        """Save finalized results to JSON."""
        result = self.finalize()
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        with open(path, 'w') as f:
            json.dump(result, f, indent=2, cls=_NumpyEncoder)
        print(f"  Validated results → {path}")
        return result
