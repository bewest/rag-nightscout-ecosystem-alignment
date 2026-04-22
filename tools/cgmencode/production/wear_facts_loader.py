"""Helper: load EXP-2863 wear-degradation bootstrap into AuditionInputs."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
DEFAULT_WEAR_BOOTSTRAP_PARQUET = (
    _REPO / "externals" / "experiments" / "exp-2863_bootstrap_wear.parquet"
)


@dataclass(frozen=True)
class WearBootstrapFacts:
    p_site_degradation: Optional[float]


class WearFactsLoader:
    """Lookup of EXP-2863 P(site_degradation) by patient_id."""

    def __init__(
        self,
        bootstrap_path: Path = DEFAULT_WEAR_BOOTSTRAP_PARQUET,
    ) -> None:
        self._path = Path(bootstrap_path)
        self._index: Optional[dict[str, WearBootstrapFacts]] = None

    def _load(self) -> dict[str, WearBootstrapFacts]:
        idx: dict[str, WearBootstrapFacts] = {}
        if not self._path.exists():
            return idx
        df = pd.read_parquet(self._path)
        if "patient_id" not in df.columns or "p_site_degradation" not in df.columns:
            return idx
        for _, r in df.iterrows():
            idx[str(r["patient_id"])] = WearBootstrapFacts(
                p_site_degradation=float(r["p_site_degradation"])
            )
        return idx

    def lookup(self, patient_id: str) -> WearBootstrapFacts:
        if self._index is None:
            self._index = self._load()
        return self._index.get(
            str(patient_id),
            WearBootstrapFacts(None),
        )

    def known_patients(self) -> list[str]:
        if self._index is None:
            self._index = self._load()
        return sorted(self._index.keys())


def _smoke() -> None:  # pragma: no cover
    loader = WearFactsLoader()
    pids = loader.known_patients()
    print(f"loaded {len(pids)} patients from {loader._path}")
    if pids:
        print(pids[0], loader.lookup(pids[0]))


if __name__ == "__main__":
    _smoke()
