"""Helper: load EXP-2861 ISF-gap bootstrap artifact into AuditionInputs.

Parallel to SimpsonFactsLoader — exposes per-patient
P(under-correction) and P(over-correction) so production audition code
can populate `AuditionInputs.p_isf_under_correction` and
`p_isf_over_correction` without re-running the bootstrap.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
DEFAULT_ISF_BOOTSTRAP_PARQUET = (
    _REPO / "externals" / "experiments" / "exp-2861_bootstrap_isf_gap.parquet"
)


@dataclass(frozen=True)
class IsfGapBootstrapFacts:
    p_isf_under_correction: Optional[float]
    p_isf_over_correction: Optional[float]


class IsfGapFactsLoader:
    """Lookup of EXP-2861 bootstrap facts by patient_id.

    Returns IsfGapBootstrapFacts(None, None) for unknown patients so
    callers can fall back to the naive `isf_gap_pct` branch.
    """

    def __init__(
        self,
        bootstrap_path: Path = DEFAULT_ISF_BOOTSTRAP_PARQUET,
    ) -> None:
        self._bootstrap_path = Path(bootstrap_path)
        self._index: Optional[dict[str, IsfGapBootstrapFacts]] = None

    def _load(self) -> dict[str, IsfGapBootstrapFacts]:
        idx: dict[str, IsfGapBootstrapFacts] = {}
        if not self._bootstrap_path.exists():
            return idx
        df = pd.read_parquet(self._bootstrap_path)
        if "patient_id" not in df.columns:
            return idx
        for _, r in df.iterrows():
            pid = str(r["patient_id"])
            idx[pid] = IsfGapBootstrapFacts(
                p_isf_under_correction=(
                    float(r["p_under_correction"])
                    if "p_under_correction" in df.columns
                    else None
                ),
                p_isf_over_correction=(
                    float(r["p_over_correction"])
                    if "p_over_correction" in df.columns
                    else None
                ),
            )
        return idx

    def lookup(self, patient_id: str) -> IsfGapBootstrapFacts:
        if self._index is None:
            self._index = self._load()
        return self._index.get(
            str(patient_id),
            IsfGapBootstrapFacts(None, None),
        )

    def known_patients(self) -> list[str]:
        if self._index is None:
            self._index = self._load()
        return sorted(self._index.keys())

    def compute_for(
        self, patient_id: str, grid_df, *, cache: bool = True
    ) -> IsfGapBootstrapFacts:
        """Compute facts on demand for a patient not in the cohort cache."""
        from tools.cgmencode.production._per_patient_compute import (
            compute_isf_gap_bootstrap,
        )
        result = compute_isf_gap_bootstrap(grid_df)
        if result is None or result.get("_insufficient"):
            facts = IsfGapBootstrapFacts(None, None)
        else:
            facts = IsfGapBootstrapFacts(
                p_isf_under_correction=result.get("p_under_correction"),
                p_isf_over_correction=result.get("p_over_correction"),
            )
        if cache:
            if self._index is None:
                self._index = self._load()
            self._index[str(patient_id)] = facts
        return facts


def _smoke() -> None:  # pragma: no cover
    loader = IsfGapFactsLoader()
    pids = loader.known_patients()
    print(f"loaded {len(pids)} patients from {loader._bootstrap_path}")
    if pids:
        print(pids[0], loader.lookup(pids[0]))


if __name__ == "__main__":
    _smoke()
