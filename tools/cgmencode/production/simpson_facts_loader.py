"""Helper: load Simpson research artifacts into AuditionInputs.

Reads EXP-2853 (Simpson decomposition) and EXP-2856 (rolling
stability) parquet outputs and exposes them as a per-patient lookup
that production audition code can use to populate
`AuditionInputs.simpson_paradox` and `simpson_stability_frac`
without re-computing.

The artifacts are gitignored research outputs; this loader is the
production-side bridge.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

# Default artifact paths; callers can override.
_REPO = Path(__file__).resolve().parents[3]
DEFAULT_SIMPSON_PARQUET = (
    _REPO / "externals" / "experiments" / "exp-2853_simpson_decomposition.parquet"
)
DEFAULT_STABILITY_PARQUET = (
    _REPO / "externals" / "experiments" / "exp-2856_per_patient_stability.parquet"
)


@dataclass(frozen=True)
class SimpsonAuditionFacts:
    """Per-patient Simpson facts ready for AuditionInputs."""
    simpson_paradox: Optional[bool]
    simpson_stability_frac: Optional[float]


class SimpsonFactsLoader:
    """Lookup of Simpson facts by patient_id.

    Lazy-loads parquet artifacts on first use. Returns
    `SimpsonAuditionFacts(None, None)` for unknown patients so callers
    can pass through to the existing phenotype-proxy fallback.
    """

    def __init__(
        self,
        simpson_path: Path = DEFAULT_SIMPSON_PARQUET,
        stability_path: Path = DEFAULT_STABILITY_PARQUET,
    ) -> None:
        self._simpson_path = Path(simpson_path)
        self._stability_path = Path(stability_path)
        self._index: Optional[dict[str, SimpsonAuditionFacts]] = None

    def _load(self) -> dict[str, SimpsonAuditionFacts]:
        idx: dict[str, SimpsonAuditionFacts] = {}
        # Simpson flag (EXP-2853)
        flag_by_pid: dict[str, bool] = {}
        if self._simpson_path.exists():
            df = pd.read_parquet(self._simpson_path)
            if "patient_id" in df.columns and "simpson_paradox" in df.columns:
                for _, r in df.iterrows():
                    flag_by_pid[str(r["patient_id"])] = bool(r["simpson_paradox"])
        # Stability (EXP-2856)
        stab_by_pid: dict[str, float] = {}
        if self._stability_path.exists():
            df = pd.read_parquet(self._stability_path)
            if (
                "patient_id" in df.columns
                and "frac_agree_with_overall" in df.columns
            ):
                for _, r in df.iterrows():
                    stab_by_pid[str(r["patient_id"])] = float(
                        r["frac_agree_with_overall"]
                    )
        all_pids = set(flag_by_pid) | set(stab_by_pid)
        for pid in all_pids:
            idx[pid] = SimpsonAuditionFacts(
                simpson_paradox=flag_by_pid.get(pid),
                simpson_stability_frac=stab_by_pid.get(pid),
            )
        return idx

    def get(self, patient_id: str) -> SimpsonAuditionFacts:
        if self._index is None:
            self._index = self._load()
        return self._index.get(
            str(patient_id), SimpsonAuditionFacts(None, None)
        )

    @property
    def n_patients(self) -> int:
        if self._index is None:
            self._index = self._load()
        return len(self._index)


__all__ = ["SimpsonAuditionFacts", "SimpsonFactsLoader"]
