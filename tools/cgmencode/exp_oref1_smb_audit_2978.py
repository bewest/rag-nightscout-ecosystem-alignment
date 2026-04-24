"""EXP-2978 - Per-patient oref1 enableSMB_always audit.

EXP-2972 noted oref1 patients showed em_rate around 0.080 in the
70-100 sweet spot, but at sustained-high BG (>=180 for 60 min)
the cohort-level em_rate jumped to ~0.16, with one anomalous
low-firer.  This script:
  1. Computes per-patient em_rate at BG >= 180 sustained 60 min
     (no-carb).
  2. Identifies the outlier(s) (em_rate << median).
  3. Cross-references SMB:total_dose ratio + total dose proxies
     for outlier vs cohort.

Likely cause: outlier patients have `enableSMB_always` off in
their AAPS/Trio profile -- SMB only fires on rising/PP, not
on sustained-high alone.

Source code references for AID authors:
  * AndroidAPS: plugins/aps/.../DetermineBasalSMB.kt:66-103
    -- enable_smb gate (any of enableSMB_always, enableSMB_with_COB,
    enableSMB_with_temptarget, enableSMB_after_carbs, ...)
  * Trio: FreeAPS/Sources/APS/OpenAPS/  (mirrors oref1)

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
OUT = REPO / "externals" / "experiments" / "exp-2978_summary.json"

LOOP_AB_OFF = {"a", "f"}
LOOP_AB_ON = {"c", "d", "e", "g", "i"}
OREF0_PATS = {"odc-74077367", "odc-86025410", "odc-96254963"}

SUSTAIN_BG = 180.0
SUSTAIN_WIN = 12  # 60 min preceding cells must all be >= 180
PRE_NO_CARB = 24  # 120 min


def design_of(pid, lin):
    if pid in OREF0_PATS:
        return "oref0"
    if lin == "oref1 (modern)":
        return "oref1"
    if pid in LOOP_AB_ON:
        return "Loop_AB_ON"
    if pid in LOOP_AB_OFF:
        return "Loop_AB_OFF"
    return None


def main():
    simp = pd.read_parquet(SIMP, columns=["patient_id", "lineage"]).drop_duplicates("patient_id")
    pid_to_lin = dict(zip(simp.patient_id, simp.lineage))

    cols = ["patient_id", "time", "glucose", "carbs", "bolus", "bolus_smb"]
    g = pd.read_parquet(GRID, columns=cols)
    g = g[g.patient_id.isin(set(simp.patient_id))].dropna(subset=["glucose"])
    g = g.sort_values(["patient_id", "time"]).reset_index(drop=True)

    rows = []
    for pid, sub in g.groupby("patient_id"):
        d = design_of(pid, pid_to_lin.get(pid, ""))
        if d != "oref1":
            continue
        sub = sub.sort_values("time").reset_index(drop=True)
        carbs = sub["carbs"].fillna(0).values
        carbs_pre = sub["carbs"].fillna(0).shift(1).rolling(PRE_NO_CARB, min_periods=1).sum().fillna(0).values
        bg = sub["glucose"].values
        smb = sub["bolus_smb"].fillna(0).values
        bol = sub["bolus"].fillna(0).values
        n = len(sub)

        # Cell qualifies if BG[i-SUSTAIN_WIN..i] all >= SUSTAIN_BG and no recent carbs
        bg_ok = (bg >= SUSTAIN_BG)
        sustained = pd.Series(bg_ok).rolling(SUSTAIN_WIN, min_periods=SUSTAIN_WIN).min().fillna(0).astype(bool).values
        n_cells = 0; n_fired = 0; sum_smb = 0.0
        for i in range(SUSTAIN_WIN, n):
            if not sustained[i]:
                continue
            if not (carbs_pre[i] == 0 and carbs[i] == 0):
                continue
            n_cells += 1
            if smb[i] > 0:
                n_fired += 1
                sum_smb += smb[i]

        # Patient-wide totals (no-carb cells only) for ratio context
        nc_mask = (carbs_pre == 0) & (carbs == 0)
        total_smb = float(smb[nc_mask].sum())
        total_bol = float(bol[nc_mask].sum())
        smb_ratio = total_smb / total_bol if total_bol > 0 else float("nan")

        em_rate = n_fired / n_cells if n_cells else 0.0
        rows.append({"patient_id": pid, "n_sustained_cells": n_cells,
                     "n_fired": n_fired, "em_rate": em_rate,
                     "sum_smb_in_sustained_U": sum_smb,
                     "no_carb_total_smb_U": total_smb,
                     "no_carb_total_bolus_U": total_bol,
                     "smb_to_bolus_ratio": smb_ratio})

    df = pd.DataFrame(rows).sort_values("em_rate")
    print(f"oref1 patients analyzed: {len(df)}")
    print("\n=== Per-patient sustained-high em_rate (BG>=180 for 60min, no-carb) ===")
    print(df.to_string(index=False))

    if len(df) >= 3:
        med = float(df["em_rate"].median())
        mad = float(np.median(np.abs(df["em_rate"] - med)))
        thr = max(med - 3 * mad, med * 0.25)
        outliers = df[df["em_rate"] < thr]
        print(f"\nMedian em_rate={med:.4f}  MAD={mad:.4f}  outlier_threshold<{thr:.4f}")
        print("Outlier(s):")
        print(outliers.to_string(index=False) if len(outliers) else "  (none below threshold)")
    else:
        outliers = df.iloc[:0]

    out = {
        "scope": "Per-patient oref1 sustained-high em_rate audit",
        "sustain_band_lo": SUSTAIN_BG,
        "sustain_minutes": SUSTAIN_WIN * 5,
        "per_patient": df.to_dict(orient="records"),
        "outliers": outliers.to_dict(orient="records"),
        "code_refs": [
            "externals/AndroidAPS/plugins/aps/src/main/kotlin/.../DetermineBasalSMB.kt:66-103 enable_smb gate",
            "externals/AndroidAPS/core/data/.../SMBDefaults.kt enableSMB_always default",
        ],
    }
    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n[exp-2978] {OUT}")


if __name__ == "__main__":
    main()
