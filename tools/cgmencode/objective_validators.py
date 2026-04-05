"""
objective_validators.py — Objective-specific validation for CGM/AID experiments.

Each validator knows the correct metrics, stratification strategy, and
reporting format for its objective type. They compose with the core
validation_framework.py building blocks.

Usage:
    from tools.cgmencode.objective_validators import (
        ForecastValidator, ClassificationValidator,
        RetrievalValidator, DriftValidator,
    )

    # Classification with full rigor
    cv = ClassificationValidator(task_name='uam', positive_label=1)
    metrics = cv.evaluate(y_true, y_pred, y_prob)
    # → {'f1_positive': 0.939, 'f1_macro': 0.95, 'auc_roc': 0.97,
    #    'auprc': 0.95, 'ece': 0.01, 'optimal_threshold': 0.42, ...}
"""

import warnings
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .validation_framework import BootstrapCI

# numpy 2.x renamed trapz → trapezoid
_trapz = getattr(np, 'trapezoid', None) or np.trapz


# ── Helpers ─────────────────────────────────────────────────────────────

def _safe_f1(y_true, y_pred, pos_label=1):
    """F1 for a specific positive class, safe against zero-division."""
    tp = int(((y_pred == pos_label) & (y_true == pos_label)).sum())
    fp = int(((y_pred == pos_label) & (y_true != pos_label)).sum())
    fn = int(((y_pred != pos_label) & (y_true == pos_label)).sum())
    prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
    return f1


def _safe_macro_f1(y_true, y_pred):
    """Macro-averaged F1 across all classes."""
    classes = np.unique(np.concatenate([y_true, y_pred]))
    f1s = [_safe_f1(y_true, y_pred, pos_label=c) for c in classes]
    return float(np.mean(f1s)) if f1s else 0.0


def _auc_roc(y_true, y_prob, pos_label=1):
    """AUC-ROC using trapezoidal rule. No sklearn dependency."""
    # Binary: isolate positive class probability
    if y_prob.ndim == 2:
        scores = y_prob[:, pos_label]
    else:
        scores = y_prob

    pos = y_true == pos_label
    neg = ~pos
    n_pos, n_neg = pos.sum(), neg.sum()
    if n_pos == 0 or n_neg == 0:
        return float('nan')

    # Sort by descending score
    order = np.argsort(-scores)
    y_sorted = pos[order]

    tpr_points = np.cumsum(y_sorted) / n_pos
    fpr_points = np.cumsum(~y_sorted) / n_neg

    # Prepend (0, 0)
    tpr_points = np.concatenate([[0], tpr_points])
    fpr_points = np.concatenate([[0], fpr_points])

    return float(_trapz(tpr_points, fpr_points))


def _auprc(y_true, y_prob, pos_label=1):
    """Area under Precision-Recall Curve. Better than AUC for imbalanced data."""
    if y_prob.ndim == 2:
        scores = y_prob[:, pos_label]
    else:
        scores = y_prob

    pos = y_true == pos_label
    n_pos = pos.sum()
    if n_pos == 0:
        return float('nan')

    order = np.argsort(-scores)
    y_sorted = pos[order]

    tp_cumsum = np.cumsum(y_sorted)
    precision = tp_cumsum / np.arange(1, len(y_sorted) + 1)
    recall = tp_cumsum / n_pos

    # Prepend (recall=0, precision=1)
    precision = np.concatenate([[1.0], precision])
    recall = np.concatenate([[0.0], recall])

    return float(_trapz(precision, recall))


def _expected_calibration_error(y_true, y_prob, n_bins: int = 10,
                                 pos_label: int = 1) -> float:
    """Expected Calibration Error (ECE)."""
    if y_prob.ndim == 2:
        probs = y_prob[:, pos_label]
    else:
        probs = y_prob

    labels = (y_true == pos_label).astype(float)
    bin_edges = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    for lo, hi in zip(bin_edges[:-1], bin_edges[1:]):
        mask = (probs >= lo) & (probs < hi)
        if mask.sum() == 0:
            continue
        avg_conf = probs[mask].mean()
        avg_acc = labels[mask].mean()
        ece += mask.sum() * abs(avg_conf - avg_acc)
    return float(ece / len(probs)) if len(probs) > 0 else 0.0


def _optimal_threshold(y_true, y_prob, pos_label=1,
                        metric='f1', n_thresholds=100):
    """Find optimal classification threshold by grid search on metric."""
    if y_prob.ndim == 2:
        scores = y_prob[:, pos_label]
    else:
        scores = y_prob

    best_thresh, best_val = 0.5, 0.0
    for thresh in np.linspace(0.01, 0.99, n_thresholds):
        preds = (scores >= thresh).astype(int)
        if metric == 'f1':
            val = _safe_f1(y_true, preds, pos_label=1)
        else:
            val = float((y_true == preds).mean())
        if val > best_val:
            best_val = val
            best_thresh = float(thresh)

    return best_thresh, best_val


# ── Forecast Validator ──────────────────────────────────────────────────

class ForecastValidator:
    """Validation metrics for glucose forecasting.

    Computes MAE, RMSE, per-zone MAE (hypo/target/hyper), Clarke Error
    Grid percentages, and verification gap.
    """

    # Glucose zones in mg/dL (after denormalization)
    ZONE_HYPO = (0, 70)
    ZONE_TARGET = (70, 180)
    ZONE_HYPER = (180, 400)

    def __init__(self, glucose_scale: float = 400.0):
        """Args: glucose_scale — normalization factor for glucose channel."""
        self.glucose_scale = glucose_scale

    def evaluate(self, y_true: np.ndarray, y_pred: np.ndarray,
                 denormalize: bool = True,
                 bootstrap: bool = True) -> Dict[str, Any]:
        """Compute all forecasting metrics.

        Args:
            y_true: Ground truth glucose values.
            y_pred: Predicted glucose values.
            denormalize: If True, multiply by glucose_scale to get mg/dL.
            bootstrap: If True, include 95% CIs.

        Returns:
            Dict with mae, rmse, zone_mae, clarke_pct, and optionally CIs.
        """
        if denormalize:
            y_true = y_true * self.glucose_scale
            y_pred = y_pred * self.glucose_scale

        abs_err = np.abs(y_true - y_pred)
        mae = float(np.mean(abs_err))
        rmse = float(np.sqrt(np.mean((y_true - y_pred) ** 2)))

        # Per-zone MAE
        zones = {}
        for name, (lo, hi) in [('hypo', self.ZONE_HYPO),
                                ('target', self.ZONE_TARGET),
                                ('hyper', self.ZONE_HYPER)]:
            mask = (y_true >= lo) & (y_true < hi)
            if mask.sum() > 0:
                zones[name] = {
                    'mae': float(np.mean(abs_err[mask])),
                    'n_samples': int(mask.sum()),
                    'pct_of_total': float(mask.mean()),
                }
            else:
                zones[name] = {'mae': float('nan'), 'n_samples': 0, 'pct_of_total': 0.0}

        # Clarke Error Grid zones A+B
        clarke = self._clarke_zones(y_true, y_pred)

        result = {
            'mae': mae,
            'rmse': rmse,
            'zone_mae': zones,
            'clarke_pct': clarke,
            'n_samples': len(y_true),
            'metric_type': 'mg/dL' if denormalize else 'normalized',
        }

        if bootstrap:
            mae_ci = BootstrapCI.compute(
                y_true, y_pred,
                lambda yt, yp: float(np.mean(np.abs(yt - yp))))
            result['mae_ci'] = mae_ci

        return result

    def verification_gap(self, train_metrics: Dict[str, float],
                         val_metrics: Dict[str, float]) -> Dict[str, float]:
        """Compute gap between training and validation metrics."""
        gap = {}
        for key in ['mae', 'rmse']:
            if key in train_metrics and key in val_metrics:
                diff = val_metrics[key] - train_metrics[key]
                pct = 100 * diff / abs(train_metrics[key]) if train_metrics[key] != 0 else 0.0
                gap[key] = {
                    'absolute': round(diff, 2),
                    'relative_pct': round(pct, 1),
                    'interpretation': 'overfitting' if diff > 0 else 'underfitting',
                }
        return gap

    @staticmethod
    def _clarke_zones(y_true, y_pred):
        """Simplified Clarke Error Grid zone classification."""
        n = len(y_true)
        if n == 0:
            return {'A': 0, 'B': 0, 'C': 0, 'D': 0, 'E': 0}

        abs_diff = np.abs(y_true - y_pred)

        # Zone A: within 20% or both <70
        zone_a = ((abs_diff <= 0.2 * y_true) |
                  ((y_true < 70) & (y_pred < 70)))

        # Zone B: outside 20% but not clinically dangerous
        zone_b = (~zone_a) & (abs_diff <= 0.4 * np.maximum(y_true, 1))

        # Everything else is C/D/E (simplified)
        zone_other = ~(zone_a | zone_b)

        return {
            'A': round(float(zone_a.mean()) * 100, 1),
            'B': round(float(zone_b.mean()) * 100, 1),
            'A+B': round(float((zone_a | zone_b).mean()) * 100, 1),
            'other': round(float(zone_other.mean()) * 100, 1),
        }


# ── Classification Validator ────────────────────────────────────────────

class ClassificationValidator:
    """Validation metrics for event detection (UAM, hypo, override).

    Computes positive-class F1, macro F1, AUC-ROC, AUPRC, ECE,
    optimal threshold, and per-class breakdown. All metrics explicitly
    labeled with their type to avoid ambiguity.
    """

    def __init__(self, task_name: str = 'binary',
                 positive_label: int = 1,
                 is_imbalanced: bool = False):
        """
        Args:
            task_name: Name for reporting (e.g., 'uam', 'hypo', 'override').
            positive_label: Which class is "positive" for F1/AUC.
            is_imbalanced: If True, add AUPRC and stratification warnings.
        """
        self.task_name = task_name
        self.positive_label = positive_label
        self.is_imbalanced = is_imbalanced

    def evaluate(self, y_true: np.ndarray,
                 y_pred: np.ndarray,
                 y_prob: Optional[np.ndarray] = None,
                 bootstrap: bool = True) -> Dict[str, Any]:
        """Compute all classification metrics.

        Args:
            y_true: Ground truth labels (int array).
            y_pred: Predicted labels (int array, post-threshold).
            y_prob: Predicted probabilities (optional, for AUC/AUPRC/ECE).
            bootstrap: If True, include 95% CIs for key metrics.

        Returns:
            Dict with all metrics, explicitly labeled by type.
        """
        pos = self.positive_label

        # Core metrics
        f1_pos = _safe_f1(y_true, y_pred, pos_label=pos)
        f1_macro = _safe_macro_f1(y_true, y_pred)

        tp = int(((y_pred == pos) & (y_true == pos)).sum())
        fp = int(((y_pred == pos) & (y_true != pos)).sum())
        fn = int(((y_pred != pos) & (y_true == pos)).sum())
        tn = int(((y_pred != pos) & (y_true != pos)).sum())
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        specificity = tn / (tn + fp) if (tn + fp) > 0 else 0.0
        accuracy = (tp + tn) / (tp + fp + fn + tn) if (tp + fp + fn + tn) > 0 else 0.0

        prevalence = float((y_true == pos).mean())

        result = {
            'task_name': self.task_name,
            'f1_positive': round(f1_pos, 4),
            'f1_macro': round(f1_macro, 4),
            'precision': round(precision, 4),
            'recall': round(recall, 4),
            'specificity': round(specificity, 4),
            'accuracy': round(accuracy, 4),
            'confusion_matrix': {'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn},
            'prevalence': round(prevalence, 4),
            'n_samples': len(y_true),
            'n_positive': int((y_true == pos).sum()),
            'metric_types': {
                'f1_positive': f'positive-class (label={pos}) F1',
                'f1_macro': 'macro-averaged F1 across all classes',
            },
        }

        # Probability-based metrics
        if y_prob is not None:
            auc = _auc_roc(y_true, y_prob, pos_label=pos)
            result['auc_roc'] = round(auc, 4) if not np.isnan(auc) else None

            if self.is_imbalanced:
                auprc = _auprc(y_true, y_prob, pos_label=pos)
                result['auprc'] = round(auprc, 4) if not np.isnan(auprc) else None

            ece = _expected_calibration_error(y_true, y_prob, pos_label=pos)
            result['ece'] = round(ece, 4)

            # Optimal threshold
            opt_thresh, opt_f1 = _optimal_threshold(y_true, y_prob, pos_label=pos)
            result['optimal_threshold'] = round(opt_thresh, 4)
            result['f1_at_optimal_threshold'] = round(opt_f1, 4)

        # Imbalance warning
        if self.is_imbalanced and prevalence < 0.10:
            result['imbalance_warning'] = (
                f'Positive class prevalence={prevalence:.1%}. '
                f'Use AUPRC and stratified splits for reliable evaluation.'
            )

        # Bootstrap CIs
        if bootstrap:
            f1_ci = BootstrapCI.compute(
                y_true, y_pred,
                lambda yt, yp: _safe_f1(yt, yp, pos_label=pos))
            result['f1_positive_ci'] = f1_ci

            if y_prob is not None:
                auc_ci = BootstrapCI.compute(
                    y_true, y_prob if y_prob.ndim == 1 else y_prob[:, pos],
                    lambda yt, yp: _auc_roc(yt, yp, pos_label=1)
                    if yt.ndim == 1 and yp.ndim == 1 else float('nan'))
                result['auc_roc_ci'] = auc_ci

        return result

    def evaluate_calibration(self, y_true: np.ndarray,
                              y_prob: np.ndarray,
                              n_bins: int = 10) -> Dict[str, Any]:
        """Detailed calibration analysis (reliability diagram data).

        Returns bin-level calibration data for plotting reliability diagrams.
        """
        pos = self.positive_label
        if y_prob.ndim == 2:
            probs = y_prob[:, pos]
        else:
            probs = y_prob

        labels = (y_true == pos).astype(float)
        bin_edges = np.linspace(0, 1, n_bins + 1)
        bins = []

        for lo, hi in zip(bin_edges[:-1], bin_edges[1:]):
            mask = (probs >= lo) & (probs < hi)
            count = int(mask.sum())
            if count > 0:
                bins.append({
                    'bin_lower': round(float(lo), 3),
                    'bin_upper': round(float(hi), 3),
                    'avg_predicted_prob': round(float(probs[mask].mean()), 4),
                    'avg_true_freq': round(float(labels[mask].mean()), 4),
                    'count': count,
                })

        ece = _expected_calibration_error(y_true, y_prob, n_bins=n_bins,
                                           pos_label=pos)
        return {
            'ece': round(ece, 4),
            'n_bins': n_bins,
            'calibration_bins': bins,
        }


# ── Retrieval Validator ─────────────────────────────────────────────────

class RetrievalValidator:
    """Validation metrics for pattern retrieval / embedding quality.

    Computes Silhouette (primary), ARI, class-balanced R@K, and
    per-cluster quality. Addresses R@K saturation by using class-balanced
    sampling.
    """

    def evaluate(self, embeddings: np.ndarray, labels: np.ndarray,
                 k_values: Sequence[int] = (1, 5, 10),
                 bootstrap: bool = True) -> Dict[str, Any]:
        """Compute all retrieval/embedding metrics.

        Args:
            embeddings: Array of shape (N, D) — embedding vectors.
            labels: Array of shape (N,) — cluster/pattern labels.
            k_values: R@K values to compute.
            bootstrap: If True, include CIs.

        Returns:
            Dict with silhouette, ARI, recall@K, per-cluster breakdown.
        """
        from scipy.spatial.distance import cdist

        n_samples = len(embeddings)
        unique_labels = np.unique(labels)
        n_clusters = len(unique_labels)

        result = {
            'n_samples': n_samples,
            'n_clusters': n_clusters,
            'label_distribution': {
                str(int(l)): int((labels == l).sum()) for l in unique_labels
            },
        }

        # Silhouette score (sklearn-free implementation)
        sil = self._silhouette(embeddings, labels)
        result['silhouette'] = round(sil, 4)

        # Per-cluster silhouette
        per_cluster_sil = {}
        for lbl in unique_labels:
            mask = labels == lbl
            if mask.sum() > 1:
                cluster_sil = self._silhouette_samples(embeddings, labels, mask)
                per_cluster_sil[str(int(lbl))] = round(float(np.mean(cluster_sil)), 4)
        result['per_cluster_silhouette'] = per_cluster_sil

        # Class-balanced Recall@K (addresses saturation)
        dists = cdist(embeddings, embeddings, metric='euclidean')
        for k in k_values:
            rak = self._class_balanced_recall_at_k(dists, labels, k)
            result[f'recall_at_{k}'] = round(rak, 4)

            rak_standard = self._recall_at_k(dists, labels, k)
            result[f'recall_at_{k}_standard'] = round(rak_standard, 4)

        # ARI (Adjusted Rand Index) vs k-means
        ari = self._ari_vs_kmeans(embeddings, labels, n_clusters)
        result['ari'] = round(ari, 4)

        # Bootstrap CI for silhouette
        if bootstrap and n_samples > 50:
            sil_ci = BootstrapCI.compute(
                embeddings, labels,
                lambda e, l: self._silhouette(e, l),
                n_bootstrap=200)
            result['silhouette_ci'] = sil_ci

        return result

    @staticmethod
    def _silhouette(embeddings, labels):
        """Compute mean silhouette score."""
        from scipy.spatial.distance import cdist

        unique = np.unique(labels)
        if len(unique) < 2:
            return 0.0

        dists = cdist(embeddings, embeddings, metric='euclidean')
        n = len(embeddings)
        sils = np.zeros(n)

        for i in range(n):
            same = labels == labels[i]
            same[i] = False
            if same.sum() == 0:
                sils[i] = 0.0
                continue

            a_i = dists[i, same].mean()

            b_i = float('inf')
            for lbl in unique:
                if lbl == labels[i]:
                    continue
                other = labels == lbl
                if other.sum() > 0:
                    b_i = min(b_i, dists[i, other].mean())

            sils[i] = (b_i - a_i) / max(a_i, b_i) if max(a_i, b_i) > 0 else 0.0

        return float(np.mean(sils))

    @staticmethod
    def _silhouette_samples(embeddings, labels, mask):
        """Silhouette for a subset of samples (e.g., one cluster)."""
        from scipy.spatial.distance import cdist

        unique = np.unique(labels)
        dists = cdist(embeddings, embeddings, metric='euclidean')
        indices = np.where(mask)[0]
        sils = np.zeros(len(indices))

        for j, i in enumerate(indices):
            same = labels == labels[i]
            same[i] = False
            if same.sum() == 0:
                sils[j] = 0.0
                continue
            a_i = dists[i, same].mean()
            b_i = float('inf')
            for lbl in unique:
                if lbl == labels[i]:
                    continue
                other = labels == lbl
                if other.sum() > 0:
                    b_i = min(b_i, dists[i, other].mean())
            sils[j] = (b_i - a_i) / max(a_i, b_i) if max(a_i, b_i) > 0 else 0.0

        return sils

    @staticmethod
    def _recall_at_k(dist_matrix, labels, k):
        """Standard Recall@K."""
        n = len(labels)
        hits = 0
        for i in range(n):
            neighbors = np.argsort(dist_matrix[i])
            neighbors = neighbors[neighbors != i][:k]
            hits += int((labels[neighbors] == labels[i]).any())
        return hits / n

    @staticmethod
    def _class_balanced_recall_at_k(dist_matrix, labels, k):
        """Class-balanced R@K: average R@K per class.

        Prevents majority-class saturation by giving equal weight
        to each class regardless of size.
        """
        unique = np.unique(labels)
        per_class_rak = []

        for cls in unique:
            cls_mask = labels == cls
            cls_indices = np.where(cls_mask)[0]
            if len(cls_indices) == 0:
                continue

            hits = 0
            for i in cls_indices:
                neighbors = np.argsort(dist_matrix[i])
                neighbors = neighbors[neighbors != i][:k]
                hits += int((labels[neighbors] == labels[i]).any())
            per_class_rak.append(hits / len(cls_indices))

        return float(np.mean(per_class_rak)) if per_class_rak else 0.0

    @staticmethod
    def _ari_vs_kmeans(embeddings, labels, n_clusters):
        """Adjusted Rand Index: k-means clusters vs ground truth labels."""
        try:
            from scipy.cluster.vq import kmeans2
            _, km_labels = kmeans2(embeddings, n_clusters, minit='points')
        except Exception:
            return float('nan')

        # ARI computation
        n = len(labels)
        contingency = defaultdict(int)
        for i in range(n):
            contingency[(int(labels[i]), int(km_labels[i]))] += 1

        # Row and column sums
        a_sums = defaultdict(int)
        b_sums = defaultdict(int)
        for (a, b), count in contingency.items():
            a_sums[a] += count
            b_sums[b] += count

        def comb2(x):
            return x * (x - 1) / 2

        index = sum(comb2(v) for v in contingency.values())
        sum_a = sum(comb2(v) for v in a_sums.values())
        sum_b = sum(comb2(v) for v in b_sums.values())
        n_comb = comb2(n)

        expected = sum_a * sum_b / n_comb if n_comb > 0 else 0
        max_index = (sum_a + sum_b) / 2
        denom = max_index - expected

        if denom == 0:
            return 0.0 if index == expected else 1.0
        return float((index - expected) / denom)


# ── Drift Validator ─────────────────────────────────────────────────────

class DriftValidator:
    """Validation metrics for ISF drift tracking.

    Computes per-patient Spearman correlation, significance testing,
    OLS slope with CI, false alarm rate, and detection latency.
    """

    def evaluate_per_patient(self, timestamps: np.ndarray,
                              isf_values: np.ndarray,
                              patient_id: str = 'unknown') -> Dict[str, Any]:
        """Evaluate drift detection for a single patient.

        Args:
            timestamps: Array of time indices (ordinal or numeric).
            isf_values: Array of ISF_effective values.
            patient_id: Patient identifier.

        Returns:
            Dict with Spearman ρ, p-value, OLS slope ± CI, trend direction.
        """
        from scipy import stats

        n = len(isf_values)
        valid = ~np.isnan(isf_values)
        timestamps = timestamps[valid]
        isf_values = isf_values[valid]
        n_valid = len(isf_values)

        if n_valid < 5:
            return {
                'patient_id': patient_id,
                'n_samples': n_valid,
                'error': 'insufficient data',
            }

        # Spearman rank correlation
        rho, p_value = stats.spearmanr(timestamps, isf_values)

        # OLS slope with confidence interval
        slope, intercept, r_value, p_ols, std_err = stats.linregress(
            timestamps.astype(float), isf_values)

        # 95% CI for slope
        t_crit = stats.t.ppf(0.975, df=n_valid - 2)
        slope_ci_lower = slope - t_crit * std_err
        slope_ci_upper = slope + t_crit * std_err

        # Variance metrics
        isf_std = float(np.std(isf_values))
        isf_cv = isf_std / abs(np.mean(isf_values)) if np.mean(isf_values) != 0 else 0.0

        return {
            'patient_id': patient_id,
            'n_samples': n_valid,
            'spearman_rho': round(float(rho), 4),
            'spearman_p': float(p_value),
            'significant_p05': bool(p_value < 0.05),
            'ols_slope': round(float(slope), 4),
            'ols_slope_ci': [round(float(slope_ci_lower), 4),
                             round(float(slope_ci_upper), 4)],
            'ols_r_squared': round(float(r_value ** 2), 4),
            'isf_std': round(isf_std, 2),
            'isf_cv': round(float(isf_cv), 4),
            'trend': 'increasing' if slope > 0 else 'decreasing',
        }

    def aggregate(self, patient_results: List[Dict[str, Any]],
                  outcome_values: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        """Aggregate per-patient drift results.

        Args:
            patient_results: List of per-patient evaluate_per_patient() results.
            outcome_values: Optional dict of patient_id -> outcome metric (e.g., TIR)
                for correlation with drift magnitude.

        Returns:
            Summary with significance count, mean |ρ|, and outcome correlation.
        """
        valid = [r for r in patient_results if 'error' not in r]
        n_patients = len(valid)

        if n_patients == 0:
            return {'error': 'no valid patients'}

        sig_count = sum(1 for r in valid if r['significant_p05'])
        rhos = [abs(r['spearman_rho']) for r in valid]

        result = {
            'n_patients': n_patients,
            'n_significant': sig_count,
            'significance_rate': round(sig_count / n_patients, 3),
            'mean_abs_rho': round(float(np.mean(rhos)), 4),
            'median_abs_rho': round(float(np.median(rhos)), 4),
        }

        # Outcome correlation (e.g., drift magnitude vs TIR)
        if outcome_values:
            drift_mags = []
            outcomes = []
            for r in valid:
                pid = r['patient_id']
                if pid in outcome_values:
                    drift_mags.append(abs(r['ols_slope']))
                    outcomes.append(outcome_values[pid])

            if len(drift_mags) >= 3:
                from scipy import stats
                corr, p = stats.spearmanr(drift_mags, outcomes)
                result['outcome_correlation'] = {
                    'spearman_rho': round(float(corr), 4),
                    'p_value': float(p),
                    'n_pairs': len(drift_mags),
                }

        return result

    def false_alarm_analysis(self, detections: np.ndarray,
                              ground_truth: np.ndarray) -> Dict[str, float]:
        """Evaluate false alarm rate for drift detection signals.

        Args:
            detections: Boolean array — True where drift was flagged.
            ground_truth: Boolean array — True where drift actually exists.

        Returns:
            Dict with FAR, sensitivity, specificity, latency stats.
        """
        tp = int((detections & ground_truth).sum())
        fp = int((detections & ~ground_truth).sum())
        fn = int((~detections & ground_truth).sum())
        tn = int((~detections & ~ground_truth).sum())

        far = fp / (fp + tn) if (fp + tn) > 0 else 0.0
        sensitivity = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        specificity = tn / (tn + fp) if (tn + fp) > 0 else 0.0

        return {
            'false_alarm_rate': round(far, 4),
            'sensitivity': round(sensitivity, 4),
            'specificity': round(specificity, 4),
            'confusion': {'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn},
        }
