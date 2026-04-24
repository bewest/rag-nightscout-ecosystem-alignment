"""fasting_helpers.py — shared utilities for masking inferred meals
in experiment fasting / equilibrium analyses.

Many experiments (EXP-2739, EXP-2740, EXP-2724, EXP-2841, ...) define
a "fasting" mask using rolling sums of *logged* carbs. Patients who
under-log carbs (live-recent: 2 logged vs 176 inferred over 60 days)
contaminate the fasting estimate with unmodeled meal absorption,
biasing EGP, basal, and ISF estimates.

This module wraps the production InferredMealsLoader so an experiment
can take any per-patient fasting mask and AND-out grid rows that fall
within the pre/post window of an inferred meal — using the same
PRE_MEAL_STEPS=24 (2 h), POST_MEAL_STEPS=48 (4 h) convention as the
clinical advisors.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from .inferred_meals_facts_loader import InferredMealsLoader

# Match clinical_rules.assess_basal / advisor masks
PRE_MEAL_STEPS = 24    # 2 h backward (covers multi-part meals)
POST_MEAL_STEPS = 48   # 4 h forward (absorption tail)


def apply_inferred_meal_exclusion(
    mask: np.ndarray,
    pdf: pd.DataFrame,
    patient_id: str,
    *,
    pre_steps: int = PRE_MEAL_STEPS,
    post_steps: int = POST_MEAL_STEPS,
    min_carbs_g: float = 5.0,
    loader: Optional[InferredMealsLoader] = None,
) -> np.ndarray:
    """Return a copy of `mask` with grid rows near inferred meals zeroed.

    Args:
        mask: (N,) boolean fasting mask aligned with `pdf` rows.
        pdf:  per-patient grid DataFrame with a "time" column (UTC).
        patient_id: patient identifier passed to InferredMealsLoader.
        pre_steps:  rows before each meal center to exclude (default 24 = 2 h).
        post_steps: rows after each meal center to exclude (default 48 = 4 h).
        min_carbs_g: only meals ≥ this size cause exclusion.
        loader: optional pre-built loader (avoid re-instantiation).

    Returns:
        A new boolean array. If no inferred meals exist or the loader
        cannot resolve the patient, returns `mask.copy()` unchanged.
    """
    if loader is None:
        loader = InferredMealsLoader()
    facts = loader.lookup(patient_id)
    events = getattr(facts, "events", None)
    if events is None or len(events) == 0:
        return np.asarray(mask, dtype=bool).copy()

    big = events[events["estimated_carbs_g"] >= min_carbs_g]
    if big.empty:
        return np.asarray(mask, dtype=bool).copy()

    grid_ts = pd.to_datetime(pdf["time"], utc=True).to_numpy()
    meal_ts = pd.to_datetime(big["timestamp_ms"], unit="ms", utc=True).to_numpy()

    n = len(pdf)
    excl = np.zeros(n, dtype=bool)
    idx = np.searchsorted(grid_ts, meal_ts)
    idx = np.clip(idx, 0, n - 1)
    for i in idx:
        s = max(0, int(i) - pre_steps)
        e = min(n, int(i) + post_steps)
        excl[s:e] = True

    out = np.asarray(mask, dtype=bool).copy()
    out &= ~excl
    return out


def inferred_meal_indices_for(
    pdf: pd.DataFrame,
    patient_id: str,
    *,
    min_carbs_g: float = 5.0,
    loader: Optional[InferredMealsLoader] = None,
) -> np.ndarray:
    """Return integer grid indices nearest to each inferred meal center."""
    if loader is None:
        loader = InferredMealsLoader()
    facts = loader.lookup(patient_id)
    events = getattr(facts, "events", None)
    if events is None or len(events) == 0:
        return np.array([], dtype=np.int64)
    big = events[events["estimated_carbs_g"] >= min_carbs_g]
    if big.empty:
        return np.array([], dtype=np.int64)
    grid_ts = pd.to_datetime(pdf["time"], utc=True).to_numpy()
    meal_ts = pd.to_datetime(big["timestamp_ms"], unit="ms", utc=True).to_numpy()
    idx = np.searchsorted(grid_ts, meal_ts)
    return np.clip(idx, 0, len(pdf) - 1).astype(np.int64)
