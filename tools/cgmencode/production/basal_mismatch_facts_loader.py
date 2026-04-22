"""Helper: load EXP-2865 basal-mismatch bootstrap into AuditionInputs.

EXP-2865 produces per-(patient, TOD) bootstrap P(scheduled_basal_mult > 0.5)
in the fasting-equilibrium regime. The per-patient summary aggregates
max P across TOD buckets — a high max-P means at least one TOD block
shows confident basal mismatch.

Per the EXP-2865 report and the EXP-2738 safety memory, a high
max_mismatch_p is a TRIAGE signal, NOT a recommendation to lower basal
by the multiplier. The gap IS the EGP safety margin the controller
needs.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
# EXP-2869 replaces EXP-2865 artifact: uses real-carb gating
# (time_since_real_carb_min with >=5g reset) per EXP-2868 audit.
# Loader falls back to EXP-2865 if the corrected artifact is missing.
DEFAULT_BASAL_MISMATCH_PARQUET = (
    _REPO / "externals" / "experiments" / "exp-2869_per_patient_summary.parquet"
)
LEGACY_BASAL_MISMATCH_PARQUET = (
    _REPO / "externals" / "experiments" / "exp-2865_per_patient_summary.parquet"
)


@dataclass(frozen=True)
class BasalMismatchFacts:
    p_basal_mismatch: Optional[float]
    median_recommended_mult: Optional[float]


class BasalMismatchFactsLoader:
    """Lookup of EXP-2865 max-P(basal mismatch) by patient_id."""

    def __init__(
        self,
        bootstrap_path: Path = DEFAULT_BASAL_MISMATCH_PARQUET,
    ) -> None:
        self._path = Path(bootstrap_path)
        if not self._path.exists() and self._path == DEFAULT_BASAL_MISMATCH_PARQUET:
            # Fall back to legacy EXP-2865 artifact (naive carb gating)
            if LEGACY_BASAL_MISMATCH_PARQUET.exists():
                self._path = LEGACY_BASAL_MISMATCH_PARQUET
        self._index: Optional[dict[str, BasalMismatchFacts]] = None

    def _load(self) -> dict[str, BasalMismatchFacts]:
        idx: dict[str, BasalMismatchFacts] = {}
        if not self._path.exists():
            return idx
        df = pd.read_parquet(self._path)
        if "patient_id" not in df.columns or "max_mismatch_p" not in df.columns:
            return idx
        for _, r in df.iterrows():
            mult = r.get("median_recommended_mult")
            idx[str(r["patient_id"])] = BasalMismatchFacts(
                p_basal_mismatch=float(r["max_mismatch_p"]),
                median_recommended_mult=(
                    float(mult) if mult is not None and pd.notna(mult) else None
                ),
            )
        return idx

    def lookup(self, patient_id: str) -> BasalMismatchFacts:
        if self._index is None:
            self._index = self._load()
        return self._index.get(
            str(patient_id),
            BasalMismatchFacts(None, None),
        )

    def known_patients(self) -> list[str]:
        if self._index is None:
            self._index = self._load()
        return sorted(self._index.keys())


def _smoke() -> None:  # pragma: no cover
    loader = BasalMismatchFactsLoader()
    pids = loader.known_patients()
    print(f"loaded {len(pids)} patients from {loader._path}")
    if pids:
        print(pids[0], loader.lookup(pids[0]))


if __name__ == "__main__":
    _smoke()
