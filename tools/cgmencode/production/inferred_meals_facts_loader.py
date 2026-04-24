"""Inferred-meals fact loader.

Exposes per-patient detected-meal events (timestamp, estimated grams,
window, archetype, announced flag) so downstream consumers can union
them with logged carbs and avoid trusting unreliable user logs as
ground truth.

Pattern mirrors `isf_gap_facts_loader` / `basal_mismatch_facts_loader`:
frozen dataclass + Loader.lookup(patient_id) returning empty facts for
unknown patients, plus `compute_for(patient_id, grid_df)` for ad-hoc
computation. Cached as
`externals/experiments/inferred_meals_<patient>.parquet`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
DEFAULT_CACHE_DIR = _REPO / "externals" / "experiments"


@dataclass(frozen=True)
class InferredMealsFacts:
    """Per-patient inferred meals.

    `events` columns: timestamp_ms (int), index (int), hour_of_day (float),
    window (str), estimated_carbs_g (float), announced (bool),
    archetype (Optional[str]).
    """
    events: pd.DataFrame = field(
        default_factory=lambda: pd.DataFrame(
            columns=[
                "timestamp_ms", "index", "hour_of_day", "window",
                "estimated_carbs_g", "announced", "archetype",
            ]
        )
    )

    @property
    def n_events(self) -> int:
        return int(len(self.events))

    @property
    def empty(self) -> bool:
        return self.n_events == 0

    def events_in_window(self, t0_ms: int, t1_ms: int) -> pd.DataFrame:
        if self.empty:
            return self.events
        ev = self.events
        return ev[(ev["timestamp_ms"] >= t0_ms) & (ev["timestamp_ms"] < t1_ms)]

    def has_meal_in(self, t0_ms: int, t1_ms: int,
                    min_carbs_g: float = 5.0) -> bool:
        if self.empty:
            return False
        return bool((self.events_in_window(t0_ms, t1_ms)
                     ["estimated_carbs_g"] >= min_carbs_g).any())


class InferredMealsLoader:
    """Lookup of inferred-meal events by patient_id, with on-demand
    computation via `compute_for`."""

    def __init__(self, cache_dir: Path = DEFAULT_CACHE_DIR) -> None:
        self._cache_dir = Path(cache_dir)
        self._index: dict[str, InferredMealsFacts] = {}

    def _cache_path(self, patient_id: str) -> Path:
        safe = str(patient_id).replace("/", "_")
        return self._cache_dir / f"inferred_meals_{safe}.parquet"

    def _load_from_cache(self, patient_id: str) -> Optional[InferredMealsFacts]:
        path = self._cache_path(patient_id)
        if not path.exists():
            return None
        try:
            df = pd.read_parquet(path)
        except Exception:
            return None
        return InferredMealsFacts(events=df)

    def lookup(self, patient_id: str) -> InferredMealsFacts:
        pid = str(patient_id)
        if pid in self._index:
            return self._index[pid]
        cached = self._load_from_cache(pid)
        if cached is not None:
            self._index[pid] = cached
            return cached
        empty = InferredMealsFacts()
        self._index[pid] = empty
        return empty

    def known_patients(self) -> list[str]:
        if not self._cache_dir.exists():
            return []
        out = []
        for p in self._cache_dir.glob("inferred_meals_*.parquet"):
            out.append(p.stem.replace("inferred_meals_", ""))
        return sorted(out)

    def compute_for(
        self,
        patient_id: str,
        grid_df: pd.DataFrame,
        *,
        profile=None,
        cache: bool = True,
    ) -> InferredMealsFacts:
        """Run the production meal detector on a patient grid and cache."""
        from tools.cgmencode.production.types import (
            PatientData, PatientProfile,
        )
        from tools.cgmencode.production.metabolic_engine import (
            compute_metabolic_state, _extract_hours,
        )
        from tools.cgmencode.production.data_quality import clean_glucose
        from tools.cgmencode.production.meal_detector import (
            detect_meal_events, classify_meal_archetypes,
        )

        if profile is None:
            isf = float(grid_df["scheduled_isf"].dropna().median()) \
                if "scheduled_isf" in grid_df else 50.0
            cr = float(grid_df["scheduled_cr"].dropna().median()) \
                if "scheduled_cr" in grid_df else 10.0
            basal = float(grid_df["scheduled_basal_rate"].dropna().median()) \
                if "scheduled_basal_rate" in grid_df else 0.6
            profile = PatientProfile(
                isf_schedule=[{"time": "00:00", "value": isf}],
                cr_schedule=[{"time": "00:00", "value": cr}],
                basal_schedule=[{"time": "00:00", "value": basal}],
                dia_hours=5.0,
                timezone="UTC",
            )

        ts_ms = grid_df["time"].astype("int64").to_numpy()
        patient = PatientData(
            glucose=grid_df["glucose"].to_numpy(dtype=float),
            timestamps=ts_ms,
            profile=profile,
            iob=grid_df.get("iob", pd.Series(dtype=float)).to_numpy(dtype=float)
                if "iob" in grid_df else None,
            cob=grid_df.get("cob", pd.Series(dtype=float)).to_numpy(dtype=float)
                if "cob" in grid_df else None,
            bolus=grid_df.get("bolus", pd.Series(dtype=float)).to_numpy(dtype=float)
                if "bolus" in grid_df else None,
            carbs=grid_df.get("carbs", pd.Series(dtype=float)).to_numpy(dtype=float)
                if "carbs" in grid_df else None,
            basal_rate=grid_df.get("actual_basal_rate",
                                   pd.Series(dtype=float)).to_numpy(dtype=float)
                if "actual_basal_rate" in grid_df else None,
            patient_id=str(patient_id),
        )
        cleaned = clean_glucose(
            patient.glucose,
            bolus=patient.bolus,
            carbs=patient.carbs,
        )
        metabolic = compute_metabolic_state(patient)
        hours = _extract_hours(patient.timestamps, profile.timezone)
        meals = detect_meal_events(
            cleaned.glucose, metabolic, hours, ts_ms, profile,
        )
        try:
            meals = classify_meal_archetypes(cleaned.glucose, meals)
        except Exception:
            pass
        rows = []
        for m in meals:
            rows.append({
                "timestamp_ms": int(m.timestamp_ms),
                "index": int(m.index),
                "hour_of_day": float(m.hour_of_day),
                "window": m.window.value if hasattr(m.window, "value") else str(m.window),
                "estimated_carbs_g": float(m.estimated_carbs_g),
                "announced": bool(m.announced),
                "archetype": (m.archetype.value
                              if m.archetype is not None
                              and hasattr(m.archetype, "value")
                              else None),
            })
        df = pd.DataFrame(rows, columns=[
            "timestamp_ms", "index", "hour_of_day", "window",
            "estimated_carbs_g", "announced", "archetype",
        ])
        facts = InferredMealsFacts(events=df)
        if cache:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            df.to_parquet(self._cache_path(patient_id), index=False)
            self._index[str(patient_id)] = facts
        return facts


def _smoke() -> None:  # pragma: no cover
    loader = InferredMealsLoader()
    pids = loader.known_patients()
    print(f"loaded {len(pids)} patients from {loader._cache_dir}")
    if pids:
        f = loader.lookup(pids[0])
        print(pids[0], f.n_events, "events; head:")
        print(f.events.head())


if __name__ == "__main__":
    _smoke()
