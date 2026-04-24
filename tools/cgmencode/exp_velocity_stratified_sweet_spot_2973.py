"""EXP-2973 - Stratify the 70-100 no-carb sweet spot by velocity sign.

Within 70-100 mg/dL no-carb cells, partition by 30-min BG velocity:
  rising:  vel > +0.5 mg/dL/min
  stable:  -0.5 <= vel <= +0.5
  falling: vel < -0.5
For each (design, stratum), report:
  emission_rate, mean_emission, mean SMB per cell.
And the SMB-on-velocity slope WITHIN each stratum (pooled).

Hypothesis: Loop_AB_ON > oref1 advantage concentrates in `rising`,
where SMB triggers should fire most aggressively.

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
OUT = REPO / "externals" / "experiments" / "exp-2973_summary.json"

LOOP_AB_OFF = {"a", "f"}
LOOP_AB_ON = {"c", "d", "e", "g", "i"}
OREF0_PATS = {"odc-74077367", "odc-86025410", "odc-96254963"}

BAND_LO, BAND_HI = 70.0, 100.0
PRE_NO_CARB = 24  # 120 min
VEL_WIN = 6
INS_WIN = 12


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


def stratum(vel):
    if vel > 0.5:
        return "rising"
    if vel < -0.5:
        return "falling"
    return "stable"


def main():
    simp = pd.read_parquet(SIMP, columns=["patient_id", "lineage"]).drop_duplicates("patient_id")
    pid_to_lin = dict(zip(simp.patient_id, simp.lineage))

    cols = ["patient_id", "time", "glucose", "carbs", "bolus_smb"]
    g = pd.read_parquet(GRID, columns=cols)
    g = g[g.patient_id.isin(set(simp.patient_id))].dropna(subset=["glucose"])
    g = g.sort_values(["patient_id", "time"]).reset_index(drop=True)

    rows = []
    for pid, sub in g.groupby("patient_id"):
        d = design_of(pid, pid_to_lin.get(pid, ""))
        if d is None:
            continue
        sub = sub.sort_values("time").reset_index(drop=True)
        carbs = sub["carbs"].fillna(0).values
        carbs_pre = sub["carbs"].fillna(0).shift(1).rolling(PRE_NO_CARB, min_periods=1).sum().fillna(0).values
        bg = sub["glucose"].values
        smb = sub["bolus_smb"].fillna(0).values
        n = len(sub)
        for i in range(0, n - INS_WIN):
            if np.isnan(bg[i]):
                continue
            if not (BAND_LO <= bg[i] < BAND_HI):
                continue
            if not (carbs_pre[i] == 0 and carbs[i] == 0):
                continue
            j = i + VEL_WIN
            ys = bg[i:j + 1]
            if np.any(np.isnan(ys)):
                continue
            xs = np.arange(VEL_WIN + 1) * 5.0
            xm = xs.mean(); ym = ys.mean()
            denom = float(np.sum((xs - xm) ** 2))
            if denom <= 0:
                continue
            vel = float(np.sum((xs - xm) * (ys - ym)) / denom)
            rows.append({"patient_id": pid, "design": d, "vel_30": vel,
                         "stratum": stratum(vel),
                         "smb_cell": float(smb[i]),
                         "fired": int(smb[i] > 0),
                         "ins_60_smb": float(smb[i:i + INS_WIN].sum())})

    df = pd.DataFrame(rows)
    print(f"Total cells (with valid 30-min vel): {len(df):,}")

    from scipy import stats

    cells = []
    print("\n=== 70-100 no-carb stratified by 30-min velocity ===")
    print(f"{'design':>12} {'stratum':>8} {'n':>7} {'em_rate':>8} {'mean_em':>9} "
          f"{'mean_total':>11} {'slope':>9}")
    for d in ["Loop_AB_ON", "oref1", "Loop_AB_OFF", "oref0"]:
        for st in ["rising", "stable", "falling"]:
            sub = df[(df.design == d) & (df.stratum == st)]
            n = len(sub)
            if n < 30:
                continue
            n_fired = int(sub["fired"].sum())
            em = n_fired / n
            mean_em = float(sub.loc[sub.fired == 1, "smb_cell"].mean()) if n_fired else 0.0
            mean_total = float(sub["smb_cell"].mean())
            try:
                sl, _, _, p, se = stats.linregress(sub["vel_30"], sub["ins_60_smb"])
                slope = float(sl); slope_p = float(p); se = float(se)
            except Exception:
                slope = float("nan"); slope_p = float("nan"); se = float("nan")
            print(f"{d:>12} {st:>8} {n:>7} {em:>8.4f} {mean_em:>9.4f} "
                  f"{mean_total:>11.5f} {slope:>+9.4f}")
            cells.append({"design": d, "stratum": st, "n_cells": n,
                          "n_fired": n_fired, "emission_rate": em,
                          "mean_emission_U": mean_em,
                          "mean_smb_per_cell_U": mean_total,
                          "smb_slope": slope, "smb_slope_se": se,
                          "smb_slope_p": slope_p})

    print("\n=== Loop_AB_ON / oref1 emission_rate ratio per stratum ===")
    ratios = {}
    for st in ["rising", "stable", "falling"]:
        l = next((c for c in cells if c["design"] == "Loop_AB_ON" and c["stratum"] == st), None)
        o = next((c for c in cells if c["design"] == "oref1" and c["stratum"] == st), None)
        if l and o and o["emission_rate"] > 0:
            r = l["emission_rate"] / o["emission_rate"]
            print(f"  {st}: Loop em={l['emission_rate']:.4f} oref1 em={o['emission_rate']:.4f} ratio={r:.2f}x")
            ratios[st] = {"loop_em": l["emission_rate"], "oref1_em": o["emission_rate"], "ratio": r}

    out = {
        "scope": "Velocity-stratified 70-100 no-carb sweet spot",
        "band": [BAND_LO, BAND_HI],
        "strata": ["rising>0.5", "-0.5<=stable<=+0.5", "falling<-0.5 mg/dL/min"],
        "by_design_stratum": cells,
        "loop_vs_oref1_em_ratio": ratios,
    }
    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n[exp-2973] {OUT}")


if __name__ == "__main__":
    main()
