"""EXP-2992: Add `algorithm_mode` column to cohort summary parquets.

Following EXP-2986's discovery that platform != algorithm (ODC AAPS
patients in the cohort run oref0, not oref1), this script derives an
`algorithm_mode` column from `controller` + `lineage` + grid evidence
and re-emits the affected per-patient summary parquets.

Derivation rules (per task spec):
  controller=AAPS  + lineage=oref1*           -> "AAPS-oref1"
  controller=AAPS  + lineage=oref0*           -> "AAPS-oref0"
  controller=Trio                             -> "Trio-oref1"
  controller=Loop  + autobolus_on=True        -> "Loop-AB-ON"
  controller=Loop  + autobolus_on=False       -> "Loop-AB-OFF"
  otherwise (insufficient_data, unknown)      -> "unknown"

`autobolus_on` is inferred from grid evidence: a patient is AB-ON if
their `bolus_smb` is non-zero in any cell during the cohort window.
This matches the operational definition used throughout EXP-29xx
(Loop_AB_ON peers c, d, e, g, i and Loop_AB_OFF a, f).

Idempotent. Safe to re-run. Adds `algorithm_mode` if missing or
overwrites an existing one to keep the rule canonical.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent.parent
EXP_DIR = REPO / "externals" / "experiments"
GRID = REPO / "externals" / "ns-parquet" / "training" / "grid.parquet"

TARGETS = [
    "exp-2891_simpson_dose_response.parquet",
    "exp-2886_phenotype.parquet",
    "exp-2889_counterfactual_replay.parquet",
    "exp-2895_tod_lineage.parquet",
]


def loop_ab_on_set() -> set[str]:
    g = pd.read_parquet(GRID, columns=["patient_id", "bolus_smb"])
    smb_per_patient = g.groupby("patient_id").bolus_smb.sum()
    return set(smb_per_patient[smb_per_patient > 0].index.astype(str).tolist())


def derive(row: pd.Series, ab_on: set[str]) -> str:
    ctl = str(row.get("controller", "") or "").strip()
    lin = str(row.get("lineage", "") or "").strip().lower()
    pid = str(row.get("patient_id", "") or "").strip()

    if ctl == "AAPS":
        if "oref1" in lin:
            return "AAPS-oref1"
        if "oref0" in lin:
            return "AAPS-oref0"
        return "AAPS-unknown"
    if ctl == "Trio":
        return "Trio-oref1"
    if ctl == "Loop":
        return "Loop-AB-ON" if pid in ab_on else "Loop-AB-OFF"
    return "unknown"


def main() -> None:
    ab_on = loop_ab_on_set()
    print(f"Loop AB-ON patient set (any non-zero bolus_smb): {sorted(ab_on)}")

    for fname in TARGETS:
        p = EXP_DIR / fname
        if not p.exists():
            print(f"SKIP {fname} (missing)")
            continue
        df = pd.read_parquet(p)
        if "patient_id" not in df.columns or "controller" not in df.columns:
            print(f"SKIP {fname} (missing patient_id/controller)")
            continue
        df["algorithm_mode"] = df.apply(lambda r: derive(r, ab_on), axis=1)
        df.to_parquet(p, index=False)
        counts = df["algorithm_mode"].value_counts().to_dict()
        print(f"WROTE {fname}: algorithm_mode counts = {counts}")


if __name__ == "__main__":
    main()
