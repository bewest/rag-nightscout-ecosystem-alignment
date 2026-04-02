"""event_classifier.py — XGBoost-based event detection for agentic delivery.

Trains a gradient-boosted classifier on tabular features extracted from
pre-event windows to predict upcoming meals, exercise, sleep, etc.

Per the ML composition architecture (§2.3): start with trees (fast, interpretable).
Only escalate to TCN/Transformer if trees plateau.

Usage:
    python3 -m tools.cgmencode.event_classifier \
        --patients-dir externals/ns-data/patients \
        --output externals/experiments/event_classifier.json

Requires: xgboost (optional dependency).
"""
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from .label_events import EXTENDED_LABEL_MAP


# Reverse label map for reporting
LABEL_NAMES = {v: k for k, v in EXTENDED_LABEL_MAP.items()}

# Default XGBoost hyperparameters (tuned for imbalanced event data)
DEFAULT_XGB_PARAMS = {
    'max_depth': 6,
    'learning_rate': 0.1,
    'n_estimators': 200,
    'objective': 'multi:softprob',
    'num_class': len(EXTENDED_LABEL_MAP),
    'eval_metric': 'mlogloss',
    'tree_method': 'hist',
    'subsample': 0.8,
    'colsample_bytree': 0.8,
    'min_child_weight': 3,
    'random_state': 42,
}


def train_event_classifier(tabular, labels, feature_names=None,
                           val_fraction=0.2, xgb_params=None):
    """Train an XGBoost multi-class event classifier.

    Args:
        tabular: (N, F) feature array
        labels: (N,) label array (EXTENDED_LABEL_MAP values)
        feature_names: list of feature name strings
        val_fraction: fraction held out for validation
        xgb_params: override XGBoost parameters

    Returns:
        dict with model, metrics, feature importance
    """
    try:
        import xgboost as xgb
    except ImportError:
        raise ImportError(
            "xgboost is required for event_classifier. "
            "Install with: pip install xgboost"
        )

    params = {**DEFAULT_XGB_PARAMS, **(xgb_params or {})}

    # Train/val split (stratified by label)
    n = len(labels)
    rng = np.random.RandomState(42)
    indices = rng.permutation(n)
    n_val = max(1, int(n * val_fraction))
    val_idx = indices[:n_val]
    train_idx = indices[n_val:]

    X_train, y_train = tabular[train_idx], labels[train_idx]
    X_val, y_val = tabular[val_idx], labels[val_idx]

    # Handle class imbalance with sample weights
    class_counts = np.bincount(y_train.astype(int),
                               minlength=params.get('num_class', 9))
    class_weights = np.where(class_counts > 0, n / (len(class_counts) * class_counts), 1.0)
    sample_weights = class_weights[y_train.astype(int)]

    model = xgb.XGBClassifier(**params)
    model.fit(
        X_train, y_train,
        sample_weight=sample_weights,
        eval_set=[(X_val, y_val)],
        verbose=False,
    )

    # Evaluate
    val_probs = model.predict_proba(X_val)
    val_preds = model.predict(X_val)

    metrics = compute_per_class_metrics(y_val, val_preds, val_probs)

    # Feature importance
    importance = {}
    if feature_names and hasattr(model, 'feature_importances_'):
        for name, imp in zip(feature_names, model.feature_importances_):
            importance[name] = round(float(imp), 4)
        importance = dict(sorted(importance.items(), key=lambda x: -x[1]))

    return {
        'model': model,
        'metrics': metrics,
        'feature_importance': importance,
        'n_train': len(train_idx),
        'n_val': len(val_idx),
        'class_distribution': {LABEL_NAMES.get(i, str(i)): int(c)
                               for i, c in enumerate(class_counts)},
    }


def compute_per_class_metrics(y_true, y_pred, y_probs=None):
    """Compute precision, recall, F1 per event class.

    Args:
        y_true: ground truth labels
        y_pred: predicted labels
        y_probs: predicted probabilities (N, num_classes)

    Returns:
        dict with per-class and overall metrics
    """
    classes = sorted(set(y_true.astype(int)) | set(y_pred.astype(int)))
    per_class = {}

    for cls in classes:
        tp = int(np.sum((y_pred == cls) & (y_true == cls)))
        fp = int(np.sum((y_pred == cls) & (y_true != cls)))
        fn = int(np.sum((y_pred != cls) & (y_true == cls)))

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

        name = LABEL_NAMES.get(cls, str(cls))
        per_class[name] = {
            'precision': round(precision, 4),
            'recall': round(recall, 4),
            'f1': round(f1, 4),
            'support': tp + fn,
        }

    # Overall accuracy
    accuracy = float(np.mean(y_true == y_pred))

    # Macro-average F1 (excluding 'none' class for event-focused scoring)
    event_f1s = [m['f1'] for name, m in per_class.items()
                 if name != 'none' and m['support'] > 0]
    macro_f1 = float(np.mean(event_f1s)) if event_f1s else 0.0

    # AUROC per class (if probabilities available)
    auroc = {}
    if y_probs is not None:
        for cls in classes:
            name = LABEL_NAMES.get(cls, str(cls))
            binary_true = (y_true == cls).astype(float)
            if binary_true.sum() == 0 or binary_true.sum() == len(binary_true):
                continue
            if cls < y_probs.shape[1]:
                cls_probs = y_probs[:, cls]
                # Manual AUROC (no sklearn dependency)
                auroc[name] = round(_manual_auroc(binary_true, cls_probs), 4)

    return {
        'per_class': per_class,
        'accuracy': round(accuracy, 4),
        'macro_f1_events': round(macro_f1, 4),
        'auroc': auroc,
    }


def _manual_auroc(y_true, y_scores):
    """Compute AUROC without sklearn using the Wilcoxon-Mann-Whitney statistic."""
    desc_indices = np.argsort(-y_scores)
    y_sorted = y_true[desc_indices]
    n_pos = int(y_sorted.sum())
    n_neg = len(y_sorted) - n_pos
    if n_pos == 0 or n_neg == 0:
        return 0.5
    # Count: for each positive, how many negatives are ranked below it
    auc_sum = 0.0
    neg_so_far = 0
    for val in reversed(y_sorted):
        if val == 0:
            neg_so_far += 1
        else:
            auc_sum += neg_so_far
    return float(auc_sum / (n_pos * n_neg))


def predict_events(model, tabular, threshold=0.3):
    """Run event prediction and return suggestions above threshold.

    Args:
        model: trained XGBClassifier
        tabular: (N, F) feature array
        threshold: minimum probability to suggest an event

    Returns:
        list of dicts with event_type, probability, features
    """
    probs = model.predict_proba(tabular)
    suggestions = []

    for i in range(len(tabular)):
        for cls_idx in range(1, probs.shape[1]):  # skip class 0 (none)
            if probs[i, cls_idx] >= threshold:
                name = LABEL_NAMES.get(cls_idx, f'class_{cls_idx}')
                suggestions.append({
                    'index': i,
                    'event_type': name,
                    'probability': round(float(probs[i, cls_idx]), 4),
                    'top_class': LABEL_NAMES.get(int(np.argmax(probs[i])), 'unknown'),
                })

    return suggestions


def score_override_candidates(model, tabular, metadata,
                              event_type_filter=None, min_prob=0.3):
    """Score candidate overrides for each predicted event.

    For each window where an event is detected, suggests an appropriate
    override with estimated parameters.

    Args:
        model: trained XGBClassifier
        tabular: feature array
        metadata: list of window metadata dicts
        event_type_filter: optional list of event types to consider
        min_prob: minimum probability threshold

    Returns:
        list of override suggestion dicts
    """
    OVERRIDE_SUGGESTIONS = {
        'meal': {'override_type': 'eating_soon', 'insulin_needs_scale': 1.0,
                 'duration_min': 60, 'reason': 'Predicted meal approaching'},
        'eating_soon': {'override_type': 'eating_soon', 'insulin_needs_scale': 1.0,
                        'duration_min': 60, 'reason': 'Eating Soon pattern detected'},
        'exercise': {'override_type': 'exercise', 'insulin_needs_scale': 0.5,
                     'duration_min': 120, 'reason': 'Exercise pattern detected'},
        'sleep': {'override_type': 'sleep', 'insulin_needs_scale': 1.0,
                  'duration_min': 480, 'reason': 'Sleep pattern detected'},
        'sick': {'override_type': 'sick', 'insulin_needs_scale': 1.3,
                 'duration_min': 720, 'reason': 'Illness pattern detected'},
    }

    predictions = predict_events(model, tabular, threshold=min_prob)
    overrides = []

    for pred in predictions:
        etype = pred['event_type']
        if event_type_filter and etype not in event_type_filter:
            continue

        template = OVERRIDE_SUGGESTIONS.get(etype)
        if not template:
            continue

        meta = metadata[pred['index']] if pred['index'] < len(metadata) else {}
        overrides.append({
            **template,
            'confidence': pred['probability'],
            'predicted_event': etype,
            'timestamp': meta.get('timestamp', ''),
            'lead_time_min': meta.get('lead_time_min', 0),
        })

    return overrides
