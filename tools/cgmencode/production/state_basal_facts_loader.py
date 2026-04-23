"""Helper: load EXP-2811 per-state basal-drift facts.

Per EXP-2811 (ISF-basal decoupling via metabolic state), only ~10/28
patients show significant basal-need variation across 48h state
clusters; with a ≥30-sample floor, only 4/22 have multi-state data.
This loader exposes whatever state-resolved data IS available; it is
informational, NOT an audition flag.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
DEFAULT_STATE_BASAL_PARQUET = (
    _REPO / "externals" / "experiments" / "exp-2811_per_state_extractions.parquet"
)

MIN_BASAL_N = 20  # relaxed from 30 to include patient c's state 0


@dataclass(frozen=True)
class StateBasalFacts:
    per_state_basal_drift: Dict[int, float]       # state -> basal_drift
    per_state_basal_n: Dict[int, int]             # state -> sample count
    basal_drift_range: Optional[float]            # max - min across states
    has_multi_state: bool                         # True if >=2 states with MIN_BASAL_N


class StateBasalFactsLoader:
    """Per-patient lookup of state-conditioned basal_drift."""

    def __init__(
        self,
        parquet_path: Path = DEFAULT_STATE_BASAL_PARQUET,
    ) -> None:
        self._path = Path(parquet_path)
        self._index: Optional[dict[str, StateBasalFacts]] = None

    def _load(self) -> dict[str, StateBasalFacts]:
        idx: dict[str, StateBasalFacts] = {}
        if not self._path.exists():
            return idx
        df = pd.read_parquet(self._path)
        need = {"patient_id", "state", "basal_drift", "basal_n"}
        if not need.issubset(df.columns):
            return idx
        for pid, g in df.groupby("patient_id"):
            per_drift: Dict[int, float] = {}
            per_n: Dict[int, int] = {}
            for _, r in g.iterrows():
                n = int(r["basal_n"]) if pd.notna(r["basal_n"]) else 0
                if n < MIN_BASAL_N:
                    continue
                d = r["basal_drift"]
                if pd.isna(d):
                    continue
                per_drift[int(r["state"])] = float(d)
                per_n[int(r["state"])] = n
            if per_drift:
                rng = (
                    max(per_drift.values()) - min(per_drift.values())
                    if len(per_drift) >= 2
                    else None
                )
                idx[str(pid)] = StateBasalFacts(
                    per_state_basal_drift=per_drift,
                    per_state_basal_n=per_n,
                    basal_drift_range=rng,
                    has_multi_state=len(per_drift) >= 2,
                )
        return idx

    def lookup(self, patient_id: str) -> StateBasalFacts:
        if self._index is None:
            self._index = self._load()
        return self._index.get(
            str(patient_id),
            StateBasalFacts({}, {}, None, False),
        )

    def known_patients(self) -> list[str]:
        if self._index is None:
            self._index = self._load()
        return sorted(self._index.keys())


def _smoke() -> None:  # pragma: no cover
    L = StateBasalFactsLoader()
    for pid in L.known_patients()[:5]:
        print(pid, L.lookup(pid))


if __name__ == "__main__":
    _smoke()
