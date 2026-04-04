"""Unified Metrics Dashboard — cross-pipeline evaluation.

Provides a single entry point for evaluating all pipeline capabilities:
forecasting accuracy, pattern embedding quality, lead-time prediction,
override recommendation, and safety metrics.

Usage:
    from tools.cgmencode.metrics import compute_all_metrics, format_dashboard
"""
from typing import Dict, Optional

import numpy as np


def compute_forecasting_metrics(y_true: np.ndarray, y_pred: np.ndarray,
                                persistence: Optional[np.ndarray] = None,
                                glucose_scale: float = 400.0) -> Dict:
    """Standard forecasting metrics.

    Args:
        y_true: (N,) or (N, T) true glucose (normalized)
        y_pred: (N,) or (N, T) predicted glucose (normalized)
        persistence: optional (N,) or (N, T) persistence baseline
        glucose_scale: denormalization factor

    Returns:
        dict with MAE, RMSE, persistence_improvement_pct
    """
    y_true_mgdl = y_true.flatten() * glucose_scale
    y_pred_mgdl = y_pred.flatten() * glucose_scale

    mae = float(np.mean(np.abs(y_true_mgdl - y_pred_mgdl)))
    rmse = float(np.sqrt(np.mean((y_true_mgdl - y_pred_mgdl) ** 2)))

    result = {'mae_mgdl': mae, 'rmse_mgdl': rmse}

    if persistence is not None:
        p_mgdl = persistence.flatten() * glucose_scale
        p_mae = float(np.mean(np.abs(y_true_mgdl - p_mgdl)))
        result['persistence_mae_mgdl'] = p_mae
        if p_mae > 0:
            result['persistence_improvement_pct'] = (1 - mae / p_mae) * 100
        else:
            result['persistence_improvement_pct'] = 0.0

    return result


def compute_embedding_metrics(embeddings: np.ndarray,
                              labels: list,
                              k: int = 5) -> Dict:
    """Pattern embedding quality metrics.

    Args:
        embeddings: (N, embed_dim) L2-normalized
        labels: list of N label lists from classify_window()

    Returns:
        dict with recall_at_k, cluster_purity, silhouette
    """
    from .pattern_embedding import (
        retrieval_recall_at_k, cluster_purity, silhouette_score_safe,
    )

    return {
        f'recall_at_{k}': retrieval_recall_at_k(embeddings, labels, k=k),
        'cluster_purity': cluster_purity(embeddings, labels),
        'silhouette_score': silhouette_score_safe(embeddings, labels),
    }


def compute_segmentation_metrics(y_true: np.ndarray,
                                 y_pred: np.ndarray) -> Dict:
    """Episode segmentation metrics.

    Args:
        y_true: (N, T) true per-timestep labels
        y_pred: (N, T) predicted per-timestep labels

    Returns:
        dict with segment_f1, per_class_f1, accuracy
    """
    from .pattern_retrieval import _segment_f1, EPISODE_LABELS

    yt = y_true.flatten()
    yp = y_pred.flatten()

    accuracy = float(np.mean(yt == yp))
    segment_f1 = _segment_f1(y_true, y_pred)

    # Per-class F1
    per_class = {}
    for c, name in enumerate(EPISODE_LABELS):
        tp = np.sum((yp == c) & (yt == c))
        fp = np.sum((yp == c) & (yt != c))
        fn = np.sum((yp != c) & (yt == c))
        if tp + fp + fn == 0:
            continue
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
        per_class[name] = {'precision': prec, 'recall': rec, 'f1': f1}

    return {
        'segment_f1_macro': segment_f1,
        'accuracy': accuracy,
        'per_class': per_class,
    }


def compute_lead_time_metrics(predictions: list) -> Dict:
    """Lead-time prediction quality.

    Args:
        predictions: list of dicts with 'predicted' and 'actual' lead times (minutes)

    Returns:
        dict with lead_time_mae_min, actionable_rate_30min, coverage
    """
    valid = [p for p in predictions
             if not np.isnan(p.get('predicted', float('nan')))
             and not np.isnan(p.get('actual', float('nan')))]

    if not valid:
        return {
            'lead_time_mae_min': float('nan'),
            'actionable_rate_30min': 0.0,
            'coverage': 0.0,
            'n_predictions': len(predictions),
            'n_valid': 0,
        }

    errors = [abs(p['predicted'] - p['actual']) for p in valid]
    actionable = sum(1 for p in valid if p['predicted'] >= 30) / len(valid)

    return {
        'lead_time_mae_min': float(np.mean(errors)),
        'actionable_rate_30min': actionable,
        'coverage': len(valid) / len(predictions) if predictions else 0.0,
        'n_predictions': len(predictions),
        'n_valid': len(valid),
    }


def compute_override_metrics(recommendations: list) -> Dict:
    """Override recommendation quality.

    Args:
        recommendations: list of dicts with 'predicted_tir_delta',
                         'actual_tir_delta', 'blocked'

    Returns:
        dict with tir_delta, hypo_safety_rate, precision_at_1, coverage
    """
    active = [r for r in recommendations if not r.get('blocked', False)]
    blocked = len(recommendations) - len(active)

    if not active:
        return {
            'mean_tir_delta': 0.0,
            'hypo_safety_rate': 1.0,
            'precision_at_1': 0.0,
            'recommendation_coverage': 0.0,
            'n_total': len(recommendations),
            'n_blocked': blocked,
        }

    actual = [r['actual_tir_delta'] for r in active]
    precision = sum(1 for a in actual if a > 0) / len(active)
    safe = sum(1 for a in actual if a >= -0.05) / len(active)

    return {
        'mean_tir_delta': float(np.mean(actual)),
        'hypo_safety_rate': safe,
        'precision_at_1': precision,
        'recommendation_coverage': len(active) / len(recommendations),
        'n_total': len(recommendations),
        'n_blocked': blocked,
    }


def compute_safety_metrics(y_true_hypo: np.ndarray,
                           y_pred_hypo: np.ndarray,
                           threshold: float = 0.5) -> Dict:
    """Hypo safety metrics.

    Args:
        y_true_hypo: (N,) binary true labels (1 = hypo occurred)
        y_pred_hypo: (N,) predicted probabilities
        threshold: classification threshold

    Returns:
        dict with sensitivity, specificity, false_alarm_rate
    """
    y_pred_binary = (y_pred_hypo >= threshold).astype(int)
    y_true_binary = y_true_hypo.astype(int)

    tp = np.sum((y_pred_binary == 1) & (y_true_binary == 1))
    tn = np.sum((y_pred_binary == 0) & (y_true_binary == 0))
    fp = np.sum((y_pred_binary == 1) & (y_true_binary == 0))
    fn = np.sum((y_pred_binary == 0) & (y_true_binary == 1))

    sensitivity = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    specificity = tn / (tn + fp) if (tn + fp) > 0 else 0.0
    false_alarm_rate = fp / (fp + tn) if (fp + tn) > 0 else 0.0

    return {
        'sensitivity': sensitivity,
        'specificity': specificity,
        'false_alarm_rate': false_alarm_rate,
        'sensitivity_target_met': sensitivity >= 0.95,
        'n_hypo_events': int(tp + fn),
        'n_total': int(tp + tn + fp + fn),
    }


def format_dashboard(metrics: Dict) -> str:
    """Format metrics into a readable dashboard string.

    Args:
        metrics: dict with pipeline names as keys, metric dicts as values

    Returns:
        Formatted multi-line string
    """
    lines = []
    lines.append("=" * 60)
    lines.append("  UNIFIED METRICS DASHBOARD")
    lines.append("=" * 60)

    for pipeline, m in metrics.items():
        lines.append(f"\n── {pipeline.upper()} ──")
        for k, v in m.items():
            if isinstance(v, dict):
                lines.append(f"  {k}:")
                for k2, v2 in v.items():
                    lines.append(f"    {k2}: {_fmt(v2)}")
            else:
                lines.append(f"  {k}: {_fmt(v)}")

    lines.append("\n" + "=" * 60)
    return "\n".join(lines)


def _fmt(v) -> str:
    """Format a metric value."""
    if isinstance(v, float):
        if abs(v) < 1:
            return f"{v:.4f}"
        return f"{v:.2f}"
    if isinstance(v, bool):
        return "✅" if v else "❌"
    return str(v)
