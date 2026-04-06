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


# ─── Clinical Forecast Accuracy Metrics ───


def clarke_zone(ref_mgdl: float, pred_mgdl: float) -> str:
    """Clarke Error Grid zone classification.

    Args:
        ref_mgdl: Reference (actual) glucose in mg/dL
        pred_mgdl: Predicted glucose in mg/dL

    Returns:
        Zone letter: 'A' (accurate), 'B' (benign), 'C', 'D', or 'E' (dangerous)
    """
    if ref_mgdl <= 70 and pred_mgdl <= 70:
        return 'A'
    if ref_mgdl >= 180 and pred_mgdl >= 180:
        return 'A'
    if ref_mgdl > 0:
        pct_err = abs(pred_mgdl - ref_mgdl) / ref_mgdl
        if pct_err <= 0.20:
            return 'A'
        if pct_err <= 0.40:
            return 'B'
    if ref_mgdl <= 70 and pred_mgdl >= 180:
        return 'E'
    if ref_mgdl >= 180 and pred_mgdl <= 70:
        return 'E'
    if pred_mgdl > ref_mgdl + 110:
        return 'D'
    if pred_mgdl < ref_mgdl - 110:
        return 'D'
    return 'C'


def compute_mard(y_true_mgdl: np.ndarray, y_pred_mgdl: np.ndarray,
                 min_ref: float = 40.0) -> float:
    """Mean Absolute Relative Difference (MARD).

    Industry-standard CGM accuracy metric. Excludes samples where reference
    is below min_ref to avoid division instability.

    Args:
        y_true_mgdl: Reference glucose values in mg/dL
        y_pred_mgdl: Predicted glucose values in mg/dL
        min_ref: Minimum reference value to include (default 40 mg/dL)

    Returns:
        MARD as fraction (0.10 = 10%). Multiply by 100 for percentage.
    """
    mask = y_true_mgdl >= min_ref
    if mask.sum() == 0:
        return float('nan')
    ref = y_true_mgdl[mask]
    pred = y_pred_mgdl[mask]
    return float(np.mean(np.abs(pred - ref) / ref))


def compute_clarke_zones(y_true_mgdl: np.ndarray,
                         y_pred_mgdl: np.ndarray) -> dict:
    """Clarke Error Grid zone distribution.

    Args:
        y_true_mgdl: Reference glucose values in mg/dL
        y_pred_mgdl: Predicted glucose values in mg/dL

    Returns:
        dict with zone counts, percentages, and clinical pass/fail
    """
    zones = {'A': 0, 'B': 0, 'C': 0, 'D': 0, 'E': 0}
    for ref, pred in zip(y_true_mgdl.flat, y_pred_mgdl.flat):
        if np.isnan(ref) or np.isnan(pred):
            continue
        zones[clarke_zone(float(ref), float(pred))] += 1

    total = sum(zones.values())
    if total == 0:
        return {'n_samples': 0}

    pcts = {f'zone_{z}_pct': zones[z] / total for z in 'ABCDE'}
    pcts['zone_AB_pct'] = (zones['A'] + zones['B']) / total
    pcts['zone_CDE_pct'] = (zones['C'] + zones['D'] + zones['E']) / total
    pcts['clinically_acceptable'] = pcts['zone_AB_pct'] >= 0.95
    pcts['n_samples'] = total
    pcts.update({f'zone_{z}_count': zones[z] for z in 'ABCDE'})
    return pcts


def compute_iso15197(y_true_mgdl: np.ndarray,
                     y_pred_mgdl: np.ndarray) -> dict:
    """ISO 15197:2013 accuracy assessment.

    For BG < 100 mg/dL: within ±15 mg/dL
    For BG ≥ 100 mg/dL: within ±15%

    Args:
        y_true_mgdl: Reference glucose in mg/dL
        y_pred_mgdl: Predicted glucose in mg/dL

    Returns:
        dict with pass_rate, pass_flag (≥95%), counts by range
    """
    low_mask = y_true_mgdl < 100
    high_mask = y_true_mgdl >= 100
    errors = np.abs(y_pred_mgdl - y_true_mgdl)

    low_pass = np.sum(errors[low_mask] <= 15) if low_mask.any() else 0
    low_total = int(low_mask.sum())
    high_pass = np.sum(errors[high_mask] <= 0.15 * y_true_mgdl[high_mask]) if high_mask.any() else 0
    high_total = int(high_mask.sum())

    total_pass = int(low_pass + high_pass)
    total = low_total + high_total
    rate = total_pass / total if total > 0 else 0.0

    return {
        'iso15197_pass_rate': float(rate),
        'iso15197_pass': rate >= 0.95,
        'n_below_100': low_total,
        'n_above_100': high_total,
        'pass_below_100': int(low_pass),
        'pass_above_100': int(high_pass),
    }


def compute_trend_accuracy(y_true_mgdl: np.ndarray,
                           y_pred_mgdl: np.ndarray,
                           threshold_mgdl: float = 1.0) -> dict:
    """Trend direction accuracy: does prediction agree with actual direction?

    Classifies each sample pair as rising, falling, or flat and checks agreement.

    Args:
        y_true_mgdl: (N, T) reference glucose trajectories in mg/dL
        y_pred_mgdl: (N, T) predicted glucose trajectories in mg/dL
        threshold_mgdl: Change below this is 'flat' (per 5-min step)

    Returns:
        dict with direction_accuracy, per-direction precision
    """
    if y_true_mgdl.ndim == 1 or y_true_mgdl.shape[-1] < 2:
        return {'direction_accuracy': float('nan'), 'note': 'need sequential predictions'}

    # Use last - first as overall trend
    true_delta = y_true_mgdl[:, -1] - y_true_mgdl[:, 0]
    pred_delta = y_pred_mgdl[:, -1] - y_pred_mgdl[:, 0]

    def classify(delta):
        return np.where(delta > threshold_mgdl, 1,
                        np.where(delta < -threshold_mgdl, -1, 0))

    true_dir = classify(true_delta)
    pred_dir = classify(pred_delta)
    match = (true_dir == pred_dir)

    result = {
        'direction_accuracy': float(match.mean()),
        'n_rising': int((true_dir == 1).sum()),
        'n_falling': int((true_dir == -1).sum()),
        'n_flat': int((true_dir == 0).sum()),
    }

    for label, val in [('rising', 1), ('falling', -1), ('flat', 0)]:
        mask = true_dir == val
        if mask.any():
            result[f'{label}_accuracy'] = float(match[mask].mean())

    return result


def compute_clinical_forecast_metrics(y_true: np.ndarray,
                                      y_pred: np.ndarray,
                                      glucose_scale: float = 400.0,
                                      persistence: Optional[np.ndarray] = None,
                                      ) -> dict:
    """Comprehensive clinical forecast metrics — superset of compute_forecasting_metrics.

    Computes MAE, RMSE, MARD, bias, Clarke zones, ISO 15197, and trend accuracy.

    Args:
        y_true: (N,) or (N, T) true glucose (normalized, 0-1 scale)
        y_pred: (N,) or (N, T) predicted glucose (normalized)
        glucose_scale: Denormalization factor (default 400.0 mg/dL)
        persistence: Optional persistence baseline (normalized)

    Returns:
        dict with all clinical metrics
    """
    y_true_mgdl = y_true * glucose_scale
    y_pred_mgdl = y_pred * glucose_scale

    yt = y_true_mgdl.flatten()
    yp = y_pred_mgdl.flatten()

    # Absolute metrics
    errors = yp - yt
    abs_errors = np.abs(errors)
    mae = float(np.mean(abs_errors))
    rmse = float(np.sqrt(np.mean(errors ** 2)))

    result = {
        'mae_mgdl': mae,
        'rmse_mgdl': rmse,
        'bias_mgdl': float(np.mean(errors)),
        'median_ae_mgdl': float(np.median(abs_errors)),
        'mard': compute_mard(yt, yp),
        'mard_pct': compute_mard(yt, yp) * 100,
    }

    # Clarke zones
    result['clarke'] = compute_clarke_zones(yt, yp)

    # ISO 15197
    result['iso15197'] = compute_iso15197(yt, yp)

    # Trend accuracy (only if sequential)
    if y_true_mgdl.ndim == 2 and y_true_mgdl.shape[-1] >= 2:
        result['trend'] = compute_trend_accuracy(y_true_mgdl, y_pred_mgdl)

    # Persistence comparison
    if persistence is not None:
        p_mgdl = persistence.flatten() * glucose_scale
        p_mae = float(np.mean(np.abs(yt - p_mgdl)))
        result['persistence_mae_mgdl'] = p_mae
        result['persistence_mard'] = compute_mard(yt, p_mgdl)
        if p_mae > 0:
            result['improvement_pct'] = (1 - mae / p_mae) * 100

    # Range-stratified MARD (clinically important)
    for label, lo, hi in [('hypo', 40, 70), ('euglycemic', 70, 180), ('hyper', 180, 400)]:
        mask = (yt >= lo) & (yt < hi)
        if mask.sum() > 0:
            result[f'mard_{label}'] = compute_mard(yt[mask], yp[mask])
            result[f'mae_{label}_mgdl'] = float(np.mean(np.abs(yt[mask] - yp[mask])))
            result[f'n_{label}'] = int(mask.sum())

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


# ── ISF Drift Metrics ──────────────────────────────────────────────────

def compute_drift_metrics(predicted_ratios: np.ndarray,
                          actual_ratios: np.ndarray,
                          predicted_states: Optional[np.ndarray] = None,
                          actual_states: Optional[np.ndarray] = None,
                          ) -> Dict:
    """ISF drift detection accuracy metrics.

    Args:
        predicted_ratios: (N,) predicted autosens ratios [0.7-1.2]
        actual_ratios: (N,) ground truth ratios from oref0-style computation
        predicted_states: (N,) optional predicted drift state labels
            (0=stable, 1=sensitivity, 2=resistance)
        actual_states: (N,) optional ground truth state labels

    Returns:
        dict with ratio_mae, ratio_rmse, state_accuracy, state_f1_per_class,
        shift_lead_time_steps (if state transitions detected)
    """
    valid = ~(np.isnan(predicted_ratios) | np.isnan(actual_ratios))
    pr = predicted_ratios[valid]
    ar = actual_ratios[valid]

    ratio_mae = float(np.mean(np.abs(pr - ar))) if len(pr) > 0 else float('nan')
    ratio_rmse = float(np.sqrt(np.mean((pr - ar) ** 2))) if len(pr) > 0 else float('nan')

    result = {
        'ratio_mae': ratio_mae,
        'ratio_rmse': ratio_rmse,
        'n_valid': int(valid.sum()),
    }

    if predicted_states is not None and actual_states is not None:
        ps = predicted_states[valid]
        acts = actual_states[valid]
        result['state_accuracy'] = float(np.mean(ps == acts)) if len(ps) > 0 else 0.0

        # Per-class F1
        state_names = ['stable', 'sensitivity', 'resistance']
        per_class = {}
        for c, name in enumerate(state_names):
            tp = np.sum((ps == c) & (acts == c))
            fp = np.sum((ps == c) & (acts != c))
            fn = np.sum((ps != c) & (acts == c))
            if tp + fp + fn == 0:
                continue
            prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
            per_class[name] = {'precision': prec, 'recall': rec, 'f1': f1}
        result['per_class'] = per_class

        # Shift lead time: how many steps before actual transition
        # does predicted transition occur?
        lead_times = []
        for t in range(1, len(acts)):
            if acts[t] != acts[t - 1] and acts[t] != 0:  # actual shift from stable
                # Find earliest predicted shift before this point
                for s in range(max(0, t - 60), t):  # look back up to 5 hours
                    if ps[s] == acts[t]:
                        lead_times.append(t - s)
                        break
        if lead_times:
            result['shift_lead_time_steps'] = float(np.mean(lead_times))
            result['shift_lead_time_min'] = float(np.mean(lead_times)) * 5.0
        else:
            result['shift_lead_time_steps'] = 0.0
            result['shift_lead_time_min'] = 0.0

    return result


def compute_uam_metrics(y_true_uam: np.ndarray, y_pred_uam: np.ndarray,
                        lead_times_min: Optional[np.ndarray] = None,
                        threshold: float = 0.5) -> Dict:
    """Unannounced Meal (UAM) detection metrics.

    Args:
        y_true_uam: (N,) binary (1 = UAM occurred)
        y_pred_uam: (N,) predicted probabilities
        lead_times_min: (N,) optional lead time in minutes for each detection
        threshold: classification threshold

    Returns:
        dict with recall, precision, f1, false_alarm_rate, mean_lead_time_min
    """
    y_pred_binary = (y_pred_uam >= threshold).astype(int)
    y_true_binary = y_true_uam.astype(int)

    tp = int(np.sum((y_pred_binary == 1) & (y_true_binary == 1)))
    fp = int(np.sum((y_pred_binary == 1) & (y_true_binary == 0)))
    fn = int(np.sum((y_pred_binary == 0) & (y_true_binary == 1)))
    tn = int(np.sum((y_pred_binary == 0) & (y_true_binary == 0)))

    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    false_alarm_rate = fp / (fp + tn) if (fp + tn) > 0 else 0.0

    result = {
        'recall': recall,
        'precision': precision,
        'f1': f1,
        'false_alarm_rate': false_alarm_rate,
        'n_uam_events': tp + fn,
        'n_total': tp + fp + fn + tn,
    }

    if lead_times_min is not None:
        detected = (y_pred_binary == 1) & (y_true_binary == 1)
        if detected.sum() > 0:
            result['mean_lead_time_min'] = float(np.mean(lead_times_min[detected]))
            result['actionable_rate_30min'] = float(np.mean(lead_times_min[detected] >= 30))
        else:
            result['mean_lead_time_min'] = 0.0
            result['actionable_rate_30min'] = 0.0

    return result


def compute_meal_absorption_metrics(expected_cob: np.ndarray,
                                    actual_glucose_delta: np.ndarray,
                                    cr_nominal: float = 10.0) -> Dict:
    """Meal absorption tracking — expected vs actual glucose response.

    Args:
        expected_cob: (N,) expected COB decay (from CR and meal size)
        actual_glucose_delta: (N,) actual glucose change over same period
        cr_nominal: nominal carb ratio (g/U)

    Returns:
        dict with absorption_deviation, cr_mismatch_rate, mean_deviation_pct
    """
    valid = ~(np.isnan(expected_cob) | np.isnan(actual_glucose_delta))
    ec = expected_cob[valid]
    ag = actual_glucose_delta[valid]

    if len(ec) == 0:
        return {'absorption_deviation': float('nan'), 'cr_mismatch_rate': 0.0, 'n_valid': 0}

    # Expected glucose impact from COB: glucose_delta ≈ COB / CR × ISF
    # Deviation = actual - expected direction
    deviation = ag - ec
    mean_deviation = float(np.mean(np.abs(deviation)))

    # CR mismatch: absorption significantly faster or slower than expected
    # Threshold: >30% deviation from expected
    mismatch = np.abs(deviation) > 0.3 * (np.abs(ec) + 1e-6)
    cr_mismatch_rate = float(np.mean(mismatch))

    return {
        'absorption_deviation': mean_deviation,
        'cr_mismatch_rate': cr_mismatch_rate,
        'mean_deviation_pct': float(np.mean(np.abs(deviation) / (np.abs(ec) + 1e-6))) * 100,
        'n_valid': int(valid.sum()),
    }
