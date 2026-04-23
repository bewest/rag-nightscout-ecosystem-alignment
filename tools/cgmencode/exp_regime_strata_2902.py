"""EXP-2902: cohort stratification in (protection, cf) space.

Validates the EXP-2897/load-saturation diagnosis at cohort scale.

Each patient occupies a point in (aid_protection_severe, cf_severe).
The decomposition observed = (1-protection) * cf has two extreme regimes:

  - Mechanism-gap regime: protection low, cf moderate
    -> remediation: algorithm migration / mechanism upgrade
  - Load-saturation regime: protection moderate, cf at ceiling (~1.0)
    -> remediation: settings de-aggression
  - Defended regime: protection high, cf moderate
    -> no action; reference for cell peers
  - Over-performer regime: protection high, cf high
    -> capture as best-practice; verify not measurement artifact

Adds a 4-class regime label to each patient's row from EXP-2891.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path("externals/experiments")
EXP_ID = "exp-2902"

PROT_HIGH = 0.65
PROT_LOW = 0.35
CF_HIGH = 0.95


def classify(row) -> str:
    p = row["aid_protection_severe"]
    cf = row["cf_severe"]
    if cf >= CF_HIGH and p < PROT_HIGH:
        return "load_saturation"
    if p < PROT_LOW:
        return "mechanism_gap"
    if p >= PROT_HIGH and cf < CF_HIGH:
        return "defended"
    if p >= PROT_HIGH and cf >= CF_HIGH:
        return "over_performer_at_load"
    return "moderate"


def main() -> None:
    df = pd.read_parquet(OUT / "exp-2891_simpson_dose_response.parquet")
    df = df[df["lineage"] != "unknown"].copy()
    df["regime"] = df.apply(classify, axis=1)
    df["observed_severe_check"] = (1.0 - df["aid_protection_severe"]) * df["cf_severe"]

    # Cohort breakdown
    summary = {
        "exp": EXP_ID,
        "thresholds": {
            "PROT_HIGH": PROT_HIGH,
            "PROT_LOW": PROT_LOW,
            "CF_HIGH": CF_HIGH,
        },
        "n_total": int(len(df)),
        "regime_counts": df["regime"].value_counts().to_dict(),
        "regime_by_lineage": (
            df.groupby(["lineage", "regime"]).size().unstack(fill_value=0).to_dict(orient="index")
        ),
    }

    # Per-regime patient lists
    regime_members = {
        regime: df[df["regime"] == regime][
            ["patient_id", "lineage", "tercile", "aid_protection_severe",
             "cf_severe", "obs_severe"]
        ].to_dict(orient="records")
        for regime in df["regime"].unique()
    }
    summary["members"] = regime_members

    out_path = OUT / f"{EXP_ID}_regimes.parquet"
    df[[
        "patient_id", "lineage", "tercile", "aid_protection_severe",
        "cf_severe", "obs_severe", "regime",
    ]].to_parquet(out_path, index=False)

    (OUT / f"{EXP_ID}_summary.json").write_text(json.dumps(summary, indent=2, default=str))

    print(f"[{EXP_ID}] wrote {out_path} (n={len(df)})")
    print(f"  regimes: {summary['regime_counts']}")
    print()
    for regime, members in regime_members.items():
        print(f"  {regime} (n={len(members)}):")
        for m in members:
            print(f"    {m['patient_id']:30s} {m['lineage']:15s} {m['tercile']:14s} "
                  f"prot={m['aid_protection_severe']:.2f}  cf={m['cf_severe']:.2f}  "
                  f"obs={m['obs_severe']:.2f}")


if __name__ == "__main__":
    main()
