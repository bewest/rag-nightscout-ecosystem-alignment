"""Hybrid meal-support features for inferred meals.

This is an experimental production utility promoted from EXP-3446. It does not
replace the residual meal detector. It annotates detected meals with supporting
short-horizon, medium-horizon, and controller-context evidence so downstream
CR support can gate on evidence quality.
"""

from __future__ import annotations

from typing import Iterable

import numpy as np

from .types import DetectedMeal, MetabolicState

TRIGGER_WINDOW = 24
WINDOW_30M = 6
WINDOW_60M = 12
WINDOW_6H = 72
WINDOW_12H = 144


def _window(arr: np.ndarray, end: int, size: int) -> np.ndarray:
    lo = max(0, end - size)
    return arr[lo:end]


def _z_like(value: float, arr: np.ndarray) -> float:
    valid = arr[np.isfinite(arr)]
    if len(valid) < 2:
        return 0.0
    std = float(np.std(valid))
    if std < 1e-8:
        return 0.0
    return float((value - float(np.mean(valid))) / std)


def hybrid_support_at(
    index: int,
    *,
    glucose: np.ndarray,
    metabolic: MetabolicState,
    bolus: np.ndarray | None = None,
    iob: np.ndarray | None = None,
    basal_rate: np.ndarray | None = None,
) -> dict[str, float | bool | str]:
    """Compute hybrid meal-support evidence at one detected-meal index."""
    n = len(glucose)
    idx = max(1, min(int(index), n - 1))
    bolus_arr = np.nan_to_num(bolus, nan=0.0) if bolus is not None else np.zeros(n)
    iob_arr = np.nan_to_num(iob, nan=0.0) if iob is not None else np.zeros(n)
    basal_arr = np.nan_to_num(basal_rate, nan=0.0) if basal_rate is not None else np.zeros(n)

    throughput = np.maximum(np.nan_to_num(metabolic.supply) * np.nan_to_num(metabolic.demand), 0.0)
    balance = np.nan_to_num(metabolic.supply / (metabolic.demand + 1e-8), nan=1.0)
    glucose_arr = np.nan_to_num(glucose, nan=120.0)

    rise_30m = float(glucose_arr[idx] - glucose_arr[max(0, idx - WINDOW_30M)])
    rise_60m = float(glucose_arr[idx] - glucose_arr[max(0, idx - WINDOW_60M)])
    rise_2h = float(glucose_arr[idx] - glucose_arr[max(0, idx - TRIGGER_WINDOW)])
    throughput_6h = float(np.mean(_window(throughput, idx, WINDOW_6H)))
    throughput_12h = float(np.mean(_window(throughput, idx, WINDOW_12H)))
    balance_6h = float(np.mean(_window(balance, idx, WINDOW_6H)))
    recent_bolus_2h = float(np.sum(_window(bolus_arr, idx, TRIGGER_WINDOW)))
    net_basal_abs_2h = float(np.mean(np.abs(_window(basal_arr, idx, TRIGGER_WINDOW))))

    trigger_score = max(0.0, _z_like(rise_2h, np.diff(glucose_arr, prepend=glucose_arr[0])))
    throughput_score = max(0.0, _z_like(np.log1p(throughput_12h), np.log1p(throughput)))
    controller_penalty = max(0.0, _z_like(recent_bolus_2h, bolus_arr))
    hybrid_score = 0.45 * trigger_score + 0.45 * throughput_score - 0.20 * controller_penalty
    support_level = 'strong' if hybrid_score >= 1.0 else 'moderate' if hybrid_score >= 0.4 else 'weak'

    return {
        'hybrid_score': round(float(hybrid_score), 3),
        'support_level': support_level,
        'rise_30m': rise_30m,
        'rise_60m': rise_60m,
        'rise_2h': rise_2h,
        'throughput_mean_6h': throughput_6h,
        'throughput_mean_12h': throughput_12h,
        'balance_mean_6h': balance_6h,
        'recent_bolus_2h': recent_bolus_2h,
        'iob_current': float(iob_arr[idx]),
        'net_basal_abs_2h': net_basal_abs_2h,
        'experimental': True,
    }


def annotate_meals_with_hybrid_support(
    meals: Iterable[DetectedMeal],
    *,
    glucose: np.ndarray,
    metabolic: MetabolicState,
    bolus: np.ndarray | None = None,
    iob: np.ndarray | None = None,
    basal_rate: np.ndarray | None = None,
) -> list[DetectedMeal]:
    """Attach EXP-3446 hybrid support metadata to detected meals."""
    out = list(meals)
    for meal in out:
        meal.metadata['hybrid_meal_support'] = hybrid_support_at(
            meal.index,
            glucose=glucose,
            metabolic=metabolic,
            bolus=bolus,
            iob=iob,
            basal_rate=basal_rate,
        )
    return out
