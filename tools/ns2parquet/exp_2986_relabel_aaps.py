"""EXP-2986: Apply AAPS-relabel to derived cohort parquets in-place.

Background: ODC (OpenAPS Data Commons) data is AAPS-native (see
tools/ns2parquet/odc_loader.py), but historical pipeline steps
(exp_state_clustering_2810.py:73-79) hard-coded
patient_id startswith('odc-') -> 'OpenAPS' as the *controller* label,
which conflated platform (AAPS = Android app) with algorithm
(oref0 vs oref1).

Verification of the 3 ODC patients in this cohort
(odc-74077367, odc-86025410, odc-96254963) shows:
  - eventual_bg populated (oref-family algorithm)
  - algorithm_isf / algorithm_cr / algorithm_tdd / insulin_activity /
    bolus_iob ALL zero non-null (oref1-only columns absent)
  - bolus_smb == 0 across the entire grid (no SMBs ever fired)

These patients are running **AAPS-platform with oref0-algorithm**
(SMB/UAM/dynamic-ISF disabled or pre-oref1 AAPS version).

Therefore:
  - controller: 'OpenAPS' -> 'AAPS' (platform correction)
  - lineage:   keep 'oref0 (legacy)' (algorithm-correct)

This separates platform from algorithm and lets future experiments
do AAPS-vs-Trio platform isolation WITHIN oref1 (when AAPS oref1
patients are added) and AAPS-vs-historical-OpenAPS platform
isolation WITHIN oref0 (the current state).

Idempotent.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

EXP_DIR = Path("externals/experiments")
TARGETS = [
    "exp-2891_simpson_dose_response.parquet",
    "exp-2886_phenotype.parquet",
    "exp-2889_counterfactual_replay.parquet",
    "exp-2895_tod_lineage.parquet",
]


def relabel(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    if "patient_id" not in df.columns:
        return df, 0
    mask = df["patient_id"].astype(str).str.startswith("odc-")
    n = int(mask.sum())
    if n == 0:
        return df, 0
    if "controller" in df.columns:
        df.loc[mask, "controller"] = "AAPS"
    # NOTE: Do NOT change lineage. These ODC patients have zero oref1
    # markers (no SMB, no dynamic ISF) -> 'oref0 (legacy)' is the
    # algorithm-correct label even though the platform is AAPS.
    return df, n


def main() -> None:
    for fname in TARGETS:
        p = EXP_DIR / fname
        if not p.exists():
            print(f"SKIP {fname} (missing)")
            continue
        df = pd.read_parquet(p)
        df, n = relabel(df)
        if n:
            df.to_parquet(p, index=False)
            print(f"RELABELED {fname}: {n} rows -> controller=AAPS")
        else:
            print(f"NOOP {fname}: no odc- rows touched")


if __name__ == "__main__":
    main()



def main() -> None:
    for fname in TARGETS:
        p = EXP_DIR / fname
        if not p.exists():
            print(f"SKIP {fname} (missing)")
            continue
        df = pd.read_parquet(p)
        df, n = relabel(df)
        if n:
            df.to_parquet(p, index=False)
            print(f"RELABELED {fname}: {n} rows -> AAPS / oref1 (modern)")
        else:
            print(f"NOOP {fname}: no odc- rows touched")


if __name__ == "__main__":
    main()
