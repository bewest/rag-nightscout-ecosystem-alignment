"""Helper: load EXP-2753 controller-decomposition facts into AuditionInputs.

Wave-13 (EXP-2753) decomposes correction-event insulin into four channels
and attributes the observed BG drop to each, using established coefficients
(BOLUS=-129.2, SMB=-123.6, EXCESS_BASAL=-130.5 mg/dL/U):

    correction_fraction      — user bolus contribution to BG-lowering
    smb_fraction             — controller SMB contribution
    excess_basal_fraction    — controller temp-basal-excess contribution
    suspension_offset_frac   — basal-suspension correction term

Population result (n=21 patients, 2,801 events):
    user bolus:           35.3 %
    controller SMBs:      58.8 %
    excess basal:          5.9 %
    Controller total ≈   64.7 %  ── two thirds of the BG drop is automated.

Per the Wave-13 SAFETY MARGIN DOCTRINE (clinical_rules.py header) and
EXP-2738, these facts are EXPLANATORY — they tell a clinician *why*
naively replacing profile ISF with observed correction-denominator ISF
is unsafe.  They are NOT a recommendation to subtract the controller's
contribution; EXP-2753 H2 explicitly showed controller-subtracted ISF
is WORSE than correction-denominator ISF (median gap closure −455 %).

Loader contract mirrors IsfGapFactsLoader / BasalMismatchFactsLoader:
returns ControllerDynamicsFacts(...all None) for unknown patients so
callers can fall back gracefully.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

_REPO = Path(__file__).resolve().parents[3]
DEFAULT_CONTROLLER_DECOMP_JSON = (
    _REPO / "externals" / "experiments" / "exp-2753_controller_decomposition.json"
)


@dataclass(frozen=True)
class ControllerDynamicsFacts:
    """Per-patient summary of controller vs user contribution to corrections.

    All fractions are of the EXCESS-INSULIN BG-lowering effect during
    correction events (i.e. EGP-balanced scheduled basal already netted out).
    """

    controller_type: Optional[str] = None              # "loop" | "trio_openaps" | None
    n_events: Optional[int] = None
    mean_correction_fraction: Optional[float] = None   # user bolus share
    mean_smb_fraction: Optional[float] = None          # controller SMB share
    mean_excess_basal_fraction: Optional[float] = None # controller temp-basal share
    mean_controller_fraction_of_excess: Optional[float] = None  # SMB+excess basal
    corr_denom_gap_closure: Optional[float] = None     # Wave-12 EXP-2741 efficacy
    isf_corr_denom_median: Optional[float] = None      # mg/dL/U (correction-denom)
    isf_profile_median: Optional[float] = None         # mg/dL/U (profile)


class ControllerDynamicsFactsLoader:
    """Lookup of EXP-2753 controller-decomposition facts by patient_id."""

    def __init__(
        self,
        decomposition_path: Path = DEFAULT_CONTROLLER_DECOMP_JSON,
    ) -> None:
        self._path = Path(decomposition_path)
        self._index: Optional[dict[str, ControllerDynamicsFacts]] = None

    def _load(self) -> dict[str, ControllerDynamicsFacts]:
        idx: dict[str, ControllerDynamicsFacts] = {}
        if not self._path.exists():
            return idx
        try:
            blob = json.loads(self._path.read_text())
        except (json.JSONDecodeError, OSError):
            return idx
        per_patient = blob.get("per_patient") or {}
        if not isinstance(per_patient, dict):
            return idx
        for pid, row in per_patient.items():
            if not isinstance(row, dict):
                continue
            idx[str(pid)] = ControllerDynamicsFacts(
                controller_type=_str_or_none(row.get("controller")),
                n_events=_int_or_none(row.get("n_events")),
                mean_correction_fraction=_float_or_none(row.get("mean_correction_fraction")),
                mean_smb_fraction=_float_or_none(row.get("mean_smb_fraction")),
                mean_excess_basal_fraction=_float_or_none(row.get("mean_excess_basal_fraction")),
                mean_controller_fraction_of_excess=_float_or_none(
                    row.get("mean_controller_fraction_of_excess")
                ),
                corr_denom_gap_closure=_float_or_none(row.get("corr_denom_gap_closure")),
                isf_corr_denom_median=_float_or_none(row.get("isf_correction_denom_median")),
                isf_profile_median=_float_or_none(row.get("isf_profile_median")),
            )
        return idx

    def lookup(self, patient_id: str) -> ControllerDynamicsFacts:
        if self._index is None:
            self._index = self._load()
        return self._index.get(str(patient_id), ControllerDynamicsFacts())

    def known_patients(self) -> list[str]:
        if self._index is None:
            self._index = self._load()
        return sorted(self._index.keys())

    def compute_for(
        self, patient_id: str, grid_df, *, cache: bool = True
    ) -> ControllerDynamicsFacts:
        """Compute controller decomposition on demand from a single patient's grid.

        Reuses `analyze_patient` from EXP-2753.
        """
        from tools.cgmencode.production._per_patient_compute import (
            compute_controller_decomposition,
        )
        row = compute_controller_decomposition(grid_df, str(patient_id))
        if row is None:
            facts = ControllerDynamicsFacts()
        else:
            facts = ControllerDynamicsFacts(
                controller_type=_str_or_none(row.get("controller")),
                n_events=_int_or_none(row.get("n_events")),
                mean_correction_fraction=_float_or_none(
                    row.get("mean_correction_fraction")),
                mean_smb_fraction=_float_or_none(row.get("mean_smb_fraction")),
                mean_excess_basal_fraction=_float_or_none(
                    row.get("mean_excess_basal_fraction")),
                mean_controller_fraction_of_excess=_float_or_none(
                    row.get("mean_controller_fraction_of_excess")),
                corr_denom_gap_closure=_float_or_none(
                    row.get("corr_denom_gap_closure")),
                isf_corr_denom_median=_float_or_none(
                    row.get("isf_correction_denom_median")),
                isf_profile_median=_float_or_none(row.get("isf_profile_median")),
            )
        if cache:
            if self._index is None:
                self._index = self._load()
            self._index[str(patient_id)] = facts
        return facts


def _float_or_none(v) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    # Bootstrap artifacts can emit NaN; reject so downstream sees None.
    return f if f == f else None  # NaN check


def _int_or_none(v) -> Optional[int]:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _str_or_none(v) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _smoke() -> None:  # pragma: no cover
    loader = ControllerDynamicsFactsLoader()
    pids = loader.known_patients()
    print(f"loaded {len(pids)} patients from {loader._path}")
    if pids:
        print(pids[0], loader.lookup(pids[0]))


if __name__ == "__main__":
    _smoke()
