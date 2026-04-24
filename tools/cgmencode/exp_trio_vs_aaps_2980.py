"""EXP-2980 - Trio vs AAPS platform isolation within oref1 lineage.

Hypothesis: same algorithm (oref1) on different platforms (Trio
on iOS vs AAPS on Android) should produce the same SMB dosing
pattern.  Deviation isolates platform implementation differences
(BLE timing, profile sync, scheduler granularity).

This script first inspects the cohort lineage/controller columns
to identify Trio vs AAPS sub-cohorts.  If both are present,
compares em_rate, mean_emission, and outcome metrics at sustained-
high BG.  If only one is present, documents that honestly.

Scope: AID-author audience.
What this is NOT: per-patient therapy advice.
"""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent.parent
SIMP = REPO / "externals" / "experiments" / "exp-2891_simpson_dose_response.parquet"
GRID = REPO / "externals" / "ns-parquet" / "training" / "grid.parquet"
OUT = REPO / "externals" / "experiments" / "exp-2980_summary.json"

OREF0_PATS = {"odc-74077367", "odc-86025410", "odc-96254963"}

SUSTAIN_BG = 180.0
SUSTAIN_WIN = 12
PRE_NO_CARB = 24


def main():
    simp = pd.read_parquet(SIMP, columns=["patient_id", "lineage", "controller"]).drop_duplicates("patient_id")
    print("=== Cohort controller distribution ===")
    print(simp.controller.value_counts())
    print("\n=== oref1 lineage controllers ===")
    oref1_pats = simp[simp.lineage == "oref1 (modern)"]
    print(oref1_pats.to_string())

    controllers = sorted(set(oref1_pats.controller.dropna().unique()))
    print(f"\nDistinct controllers in oref1 lineage: {controllers}")

    if "AAPS" not in controllers and "AndroidAPS" not in controllers:
        verdict = (
            "MERGED-LABEL: All oref1-lineage patients in this cohort are "
            f"controller={controllers}.  No AAPS-on-Android patients are "
            "available, so Trio-vs-AAPS platform isolation cannot be "
            "performed within the existing dataset.  EXP-2972/2973 "
            "'oref1' findings are therefore Trio-specific and may not "
            "transfer to AAPS.  Future work: add AAPS-NS export to cohort."
        )
        print(f"\n>>> VERDICT: {verdict}")
        out = {
            "scope": "Trio vs AAPS platform isolation",
            "verdict": "MERGED_LABEL_CANNOT_SEPARATE",
            "controllers_present_in_oref1": controllers,
            "oref1_patient_controllers": oref1_pats.set_index("patient_id")["controller"].to_dict(),
            "note": verdict,
            "implication": (
                "Re-label EXP-2972/2973/2975/2978 'oref1' findings as "
                "'Trio (oref1 lineage)' to be precise; AAPS may share "
                "the algorithm but iOS/Android scheduler differences "
                "(BLE timing, doze mode, profile sync cadence) cannot "
                "be measured in this cohort."
            ),
        }
        OUT.write_text(json.dumps(out, indent=2, default=str))
        print(f"\n[exp-2980] {OUT}")
        return

    # Both present -- run sustained-high em_rate comparison
    cols = ["patient_id", "time", "glucose", "carbs", "bolus_smb"]
    g = pd.read_parquet(GRID, columns=cols)
    g = g[g.patient_id.isin(set(oref1_pats.patient_id))]
    pid_to_ctl = dict(zip(oref1_pats.patient_id, oref1_pats.controller))

    rows = []
    for pid, sub in g.groupby("patient_id"):
        ctl = pid_to_ctl[pid]
        sub = sub.sort_values("time").reset_index(drop=True)
        carbs = sub["carbs"].fillna(0).values
        carbs_pre = sub["carbs"].fillna(0).shift(1).rolling(PRE_NO_CARB, min_periods=1).sum().fillna(0).values
        bg = sub["glucose"].values
        smb = sub["bolus_smb"].fillna(0).values
        n = len(sub)
        bg_ok = (bg >= SUSTAIN_BG)
        sustained = pd.Series(bg_ok).rolling(SUSTAIN_WIN, min_periods=SUSTAIN_WIN).min().fillna(0).astype(bool).values
        n_cells = 0; n_fired = 0; sum_smb = 0.0
        for i in range(SUSTAIN_WIN, n):
            if sustained[i] and carbs_pre[i] == 0 and carbs[i] == 0:
                n_cells += 1
                if smb[i] > 0:
                    n_fired += 1; sum_smb += smb[i]
        em_rate = n_fired / n_cells if n_cells else 0.0
        mean_em = sum_smb / n_fired if n_fired else 0.0
        rows.append({"patient_id": pid, "controller": ctl,
                     "n_cells": n_cells, "n_fired": n_fired,
                     "em_rate": em_rate, "mean_em_U": mean_em})

    df = pd.DataFrame(rows)
    print("\n=== Per-patient sustained-high (no-carb) em_rate by controller ===")
    print(df.sort_values(["controller", "em_rate"]).to_string(index=False))
    out = {"scope": "Trio vs AAPS sustained-high em_rate",
           "controllers_present_in_oref1": controllers,
           "per_patient": df.to_dict(orient="records")}
    OUT.write_text(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
