"""Helper: load EXP-2864 post-high-envelope bootstrap into AuditionInputs."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
DEFAULT_POST_HIGH_BOOTSTRAP_PARQUET = (
    _REPO / "externals" / "experiments" / "exp-2864_bootstrap_post_high.parquet"
)


@dataclass(frozen=True)
class PostHighBootstrapFacts:
    p_post_high_envelope: Optional[float]


class PostHighFactsLoader:
    """Lookup of EXP-2864 P(post-high envelope > 25 mg/dL) by patient_id."""

    def __init__(
        self,
        bootstrap_path: Path = DEFAULT_POST_HIGH_BOOTSTRAP_PARQUET,
    ) -> None:
        self._path = Path(bootstrap_path)
        self._index: Optional[dict[str, PostHighBootstrapFacts]] = None

    def _load(self) -> dict[str, PostHighBootstrapFacts]:
        idx: dict[str, PostHighBootstrapFacts] = {}
        if not self._path.exists():
            return idx
        df = pd.read_parquet(self._path)
        if "patient_id" not in df.columns or "p_post_high_envelope" not in df.columns:
            return idx
        for _, r in df.iterrows():
            idx[str(r["patient_id"])] = PostHighBootstrapFacts(
                p_post_high_envelope=float(r["p_post_high_envelope"])
            )
        return idx

    def lookup(self, patient_id: str) -> PostHighBootstrapFacts:
        if self._index is None:
            self._index = self._load()
        return self._index.get(
            str(patient_id),
            PostHighBootstrapFacts(None),
        )

    def known_patients(self) -> list[str]:
        if self._index is None:
            self._index = self._load()
        return sorted(self._index.keys())


def _smoke() -> None:  # pragma: no cover
    loader = PostHighFactsLoader()
    pids = loader.known_patients()
    print(f"loaded {len(pids)} patients from {loader._path}")
    if pids:
        print(pids[0], loader.lookup(pids[0]))


if __name__ == "__main__":
    _smoke()
