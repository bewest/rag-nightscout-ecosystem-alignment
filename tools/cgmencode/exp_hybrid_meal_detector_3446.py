#!/usr/bin/env python3
"""EXP-3446: Hybrid meal-like event detector.

High-fidelity prototype for meal-independent meal-like event discovery.

This experiment combines:
1. short-horizon rise / UAM-style trigger features
2. medium-horizon throughput + balance separation features
3. controller-context features (bolus, basal activity, IOB)
4. leave-one-patient-out evaluation for multiclass discrimination:
   meal vs correction vs stable

Announced carbs are used only as offline weak labels for evaluation. They are
not part of the deployed feature set.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cgmencode.exp_metabolic_441 import compute_supply_demand
from cgmencode.exp_metabolic_flux import load_patients

try:
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
except ImportError as exc:  # pragma: no cover
    raise SystemExit("scikit-learn is required for EXP-3446") from exc


ROOT = Path(__file__).resolve().parents[2]
PATIENTS_DIR = ROOT / 'externals' / 'ns-data' / 'patients'
RESULTS_DIR = ROOT / 'externals' / 'experiments'
OUT_JSON = RESULTS_DIR / 'exp3446_hybrid_meal_detector.json'

TRIGGER_WINDOW = 24      # 2h @ 5min
WINDOW_30M = 6
WINDOW_60M = 12
WINDOW_6H = 72
WINDOW_12H = 144
ANCHOR_STEP = 12         # 1h

LABELS = ['stable', 'correction', 'meal']
LABEL_TO_INT = {name: idx for idx, name in enumerate(LABELS)}

TRIGGER_FEATURES = [
    'rise_30m',
    'rise_60m',
    'rise_2h',
    'glucose_std_2h',
]
THROUGHPUT_FEATURES = [
    'throughput_mean_6h',
    'throughput_std_6h',
    'balance_mean_6h',
    'throughput_mean_12h',
    'throughput_std_12h',
    'balance_mean_12h',
]
HYBRID_FEATURES = TRIGGER_FEATURES + THROUGHPUT_FEATURES + [
    'recent_bolus_30m',
    'recent_bolus_2h',
    'iob_current',
    'net_basal_abs_2h',
    'hour_sin',
    'hour_cos',
]


def _window_mean(arr: np.ndarray, start: int, end: int) -> float:
    return float(np.mean(arr[start:end]))


def _window_std(arr: np.ndarray, start: int, end: int) -> float:
    return float(np.std(arr[start:end]))


def _window_sum(arr: np.ndarray, start: int, end: int) -> float:
    return float(np.sum(arr[start:end]))


def _label_window(carbs: np.ndarray, bolus: np.ndarray, start: int, end: int) -> str:
    has_meal = bool(np.any(carbs[start:end] > 5.0))
    has_correction = bool(np.any(bolus[start:end] > 0.3) and not has_meal)
    if has_meal:
        return 'meal'
    if has_correction:
        return 'correction'
    return 'stable'


def _build_examples(patient_name: str, df, supply_demand: dict[str, np.ndarray]) -> list[dict[str, float | int | str]]:
    glucose = np.nan_to_num(df['glucose'].values.astype(np.float64), nan=120.0)
    carbs = np.nan_to_num(df['carbs'].values.astype(np.float64), nan=0.0)
    bolus = np.nan_to_num(df['bolus'].values.astype(np.float64), nan=0.0)
    iob = np.nan_to_num(df['iob'].values.astype(np.float64), nan=0.0)
    if 'net_basal' in df.columns:
        net_basal = np.nan_to_num(df['net_basal'].values.astype(np.float64), nan=0.0)
    else:
        net_basal = np.zeros(len(df), dtype=np.float64)

    throughput = np.nan_to_num(supply_demand['product'], nan=0.0)
    balance = np.nan_to_num(supply_demand['ratio'], nan=1.0)

    examples: list[dict[str, float | int | str]] = []
    start_anchor = max(WINDOW_12H, TRIGGER_WINDOW)
    for end in range(start_anchor, len(df), ANCHOR_STEP):
        start_30m = end - WINDOW_30M
        start_60m = end - WINDOW_60M
        start_2h = end - TRIGGER_WINDOW
        start_6h = end - WINDOW_6H
        start_12h = end - WINDOW_12H

        label = _label_window(carbs, bolus, start_2h, end)
        hour = (end % 288) / 12.0

        examples.append({
            'patient': patient_name,
            'label': label,
            'rise_30m': float(glucose[end - 1] - glucose[start_30m]),
            'rise_60m': float(glucose[end - 1] - glucose[start_60m]),
            'rise_2h': float(glucose[end - 1] - glucose[start_2h]),
            'glucose_std_2h': _window_std(glucose, start_2h, end),
            'throughput_mean_6h': _window_mean(throughput, start_6h, end),
            'throughput_std_6h': _window_std(throughput, start_6h, end),
            'balance_mean_6h': _window_mean(balance, start_6h, end),
            'throughput_mean_12h': _window_mean(throughput, start_12h, end),
            'throughput_std_12h': _window_std(throughput, start_12h, end),
            'balance_mean_12h': _window_mean(balance, start_12h, end),
            'recent_bolus_30m': _window_sum(bolus, start_30m, end),
            'recent_bolus_2h': _window_sum(bolus, start_2h, end),
            'iob_current': float(iob[end - 1]),
            'net_basal_abs_2h': float(np.mean(np.abs(net_basal[start_2h:end]))),
            'hour_sin': float(np.sin(2.0 * np.pi * hour / 24.0)),
            'hour_cos': float(np.cos(2.0 * np.pi * hour / 24.0)),
        })
    return examples


def _make_xy(rows: list[dict[str, float | int | str]], features: list[str]) -> tuple[np.ndarray, np.ndarray]:
    x = np.array([[float(row[name]) for name in features] for row in rows], dtype=np.float64)
    y = np.array([LABEL_TO_INT[str(row['label'])] for row in rows], dtype=np.int64)
    return x, y


def _fit_model(x_train: np.ndarray, y_train: np.ndarray):
    model = Pipeline([
        ('scale', StandardScaler()),
        ('clf', LogisticRegression(
            max_iter=1000,
            class_weight='balanced',
            solver='lbfgs',
        )),
    ])
    model.fit(x_train, y_train)
    return model


def _evaluate_meal(y_true: np.ndarray, y_pred: np.ndarray, meal_prob: np.ndarray) -> dict[str, float]:
    meal_true = (y_true == LABEL_TO_INT['meal']).astype(np.int64)
    meal_pred = (y_pred == LABEL_TO_INT['meal']).astype(np.int64)
    return {
        'meal_f1': float(f1_score(meal_true, meal_pred, zero_division=0)),
        'meal_precision': float(precision_score(meal_true, meal_pred, zero_division=0)),
        'meal_recall': float(recall_score(meal_true, meal_pred, zero_division=0)),
        'macro_f1': float(f1_score(y_true, y_pred, average='macro', zero_division=0)),
        'meal_auc': float(roc_auc_score(meal_true, meal_prob)) if len(np.unique(meal_true)) > 1 else float('nan'),
    }


def run_experiment(quick: bool = False) -> dict:
    patients = load_patients(PATIENTS_DIR, max_patients=4 if quick else None, verbose=True)
    all_rows: list[dict[str, float | int | str]] = []
    for pat in patients:
        supply_demand = compute_supply_demand(pat['df'], pat['pk'])
        all_rows.extend(_build_examples(pat['name'], pat['df'], supply_demand))

    per_patient: dict[str, dict] = {}
    fold_metrics: dict[str, list[dict[str, float]]] = {'trigger': [], 'throughput': [], 'hybrid': []}

    for held_out in sorted({str(row['patient']) for row in all_rows}):
        train_rows = [row for row in all_rows if row['patient'] != held_out]
        test_rows = [row for row in all_rows if row['patient'] == held_out]
        if len(test_rows) < 20:
            continue

        patient_result = {}
        for name, features in (
            ('trigger', TRIGGER_FEATURES),
            ('throughput', THROUGHPUT_FEATURES),
            ('hybrid', HYBRID_FEATURES),
        ):
            x_train, y_train = _make_xy(train_rows, features)
            x_test, y_test = _make_xy(test_rows, features)
            model = _fit_model(x_train, y_train)
            y_pred = model.predict(x_test)
            probs = model.predict_proba(x_test)
            meal_prob = probs[:, LABEL_TO_INT['meal']]
            metrics = _evaluate_meal(y_test, y_pred, meal_prob)
            patient_result[name] = metrics
            fold_metrics[name].append(metrics)
        per_patient[held_out] = patient_result

    aggregate = {}
    for name, rows in fold_metrics.items():
        aggregate[name] = {
            'n_folds': len(rows),
            'mean_meal_f1': float(np.mean([row['meal_f1'] for row in rows])) if rows else float('nan'),
            'mean_meal_precision': float(np.mean([row['meal_precision'] for row in rows])) if rows else float('nan'),
            'mean_meal_recall': float(np.mean([row['meal_recall'] for row in rows])) if rows else float('nan'),
            'mean_macro_f1': float(np.mean([row['macro_f1'] for row in rows])) if rows else float('nan'),
            'mean_meal_auc': float(np.mean([row['meal_auc'] for row in rows])) if rows else float('nan'),
        }

    winner = max(
        ('trigger', 'throughput', 'hybrid'),
        key=lambda key: (aggregate[key]['mean_meal_f1'], aggregate[key]['mean_meal_precision']),
    )

    return {
        'experiment_id': 'EXP-3446',
        'title': 'Hybrid UAM + throughput/balance meal-like detector',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'evaluation': 'leave-one-patient-out',
        'n_examples': len(all_rows),
        'per_patient': per_patient,
        'aggregate': aggregate,
        'winner': winner,
        'winner_reason': 'Highest mean meal F1 with precision tie-break.',
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--quick', action='store_true')
    args = parser.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    results = run_experiment(quick=args.quick)
    OUT_JSON.write_text(json.dumps(results, indent=2, default=str), encoding='utf-8')
    print(f"Saved: {OUT_JSON}")
    for name, metrics in results['aggregate'].items():
        print(
            f"{name}: meal_f1={metrics['mean_meal_f1']:.3f} "
            f"precision={metrics['mean_meal_precision']:.3f} "
            f"recall={metrics['mean_meal_recall']:.3f} "
            f"auc={metrics['mean_meal_auc']:.3f}"
        )
    print(f"winner: {results['winner']}")


if __name__ == '__main__':
    main()
