"""Helper: load EXP-2862 recovery-fraction bootstrap into AuditionInputs.

Parallel to IsfGapFactsLoader / SimpsonFactsLoader.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
DEFAULT_RECOVERY_BOOTSTRAP_PARQUET = (
    _REPO / "externals" / "experiments" / "exp-2862_bootstrap_recovery.parquet"
)


@dataclass(frozen=True)
class RecoveryBootstrapFacts:
    p_low_recovery: Optional[float]


class RecoveryFactsLoader:
    """Lookup of EXP-2862 P(low recovery) by patient_id."""

    def __init__(
        self,
        bootstrap_path: Path = DEFAULT_RECOVERY_BOOTSTRAP_PARQUET,
    ) -> None:
        self._path = Path(bootstrap_path)
        self._index: Optional[dict[str, RecoveryBootstrapFacts]] = None

    def _load(self) -> dict[str, RecoveryBootstrapFacts]:
        idx: dict[str, RecoveryBootstrapFacts] = {}
        if not self._path.exists():
            return idx
        df = pd.read_parquet(self._path)
        if "patient_id" not in df.columns or "p_low_recovery" not in df.columns:
            return idx
        for _, r in df.iterrows():
            idx[str(r["patient_id"])] = RecoveryBootstrapFacts(
                p_low_recovery=float(r["p_low_recovery"])
            )
        return idx

    def lookup(self, patient_id: str) -> RecoveryBootstrapFacts:
        if self._index is None:
            self._index = self._load()
        return self._index.get(
            str(patient_id),
            RecoveryBootstrapFacts(None),
        )

    def known_patients(self) -> list[str]:
        if self._index is None:
            self._index = self._load()
        return sorted(self._index.keys())


def _smoke() -> None:  # pragma: no cover
    loader = RecoveryFactsLoader()
    pids = loader.known_patients()
    print(f"loaded {len(pids)} patients from {loader._path}")
    if pids:
        print(pids[0], loader.lookup(pids[0]))


if __name__ == "__main__":
    _smoke()
