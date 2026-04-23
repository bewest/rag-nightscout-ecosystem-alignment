"""EXP-2925 - Hypoglycemia symmetry analog of EXP-2920/2922/2924.

Symmetric question: does the midnight HYPO signature (oref0
peak at 00:00, EXP-2920) also survive Guard #6 cf-conditioning,
and does oref1 trade hypo for hyper protection?

Method:
  - Per patient, severe hypo overnight rate: mean(glucose<54)
    over hours [0,1,2] (when most basal-driven), all states.
  - Stratify by cf_severe tertile.
  - Per (cf_tertile, lineage) cell + bootstrap CI.
  - Also: per-patient daily totals: %TBR (BG<70) and %TAR (BG>180)
    to test the "trade hypo for hyper" hypothesis at full-day
    aggregation.

Scope: design-feature characterisation. AID-author audience.
"""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent.parent
SIMP = REPO / "externals" / "experiments" / "exp-2891_simpson_dose_response.parquet"
GRID = REPO / "externals" / "ns-parquet" / "training" / "grid.parquet"
OUT = REPO / "externals" / "experiments" / "exp-2925_summary.json"

RNG = np.random.default_rng(2925)
N_BOOT = 2000
SEVERE_HYPO = 54
TBR = 70
TAR = 180


def boot_ci(values: np.ndarray) -> tuple[float, float]:
    if len(values) < 2:
        v = float(values[0]) if len(values) == 1 else float("nan")
        return v, v
    samples = RNG.choice(values, size=(N_BOOT, len(values)), replace=True).mean(axis=1)
    return float(np.percentile(samples, 2.5)), float(np.percentile(samples, 97.5))


def main() -> None:
    simp = pd.read_parquet(SIMP, columns=["patient_id", "lineage", "cf_severe"])
    simp = simp[simp.lineage.isin(["Loop (iOS)", "oref1 (modern)", "oref0 (legacy)"])]

    g = pd.read_parquet(GRID, columns=["patient_id", "time", "glucose"])
    g = g[g.patient_id.isin(set(simp.patient_id))].dropna(subset=["glucose"])
    g["hour"] = g["time"].dt.hour

    # Overnight severe hypo (hours 0,1,2)
    overnight = g[g.hour.isin([0, 1, 2])]
    onp = overnight.groupby("patient_id").apply(
        lambda d: pd.Series({
            "n_cells_overnight": len(d),
            "frac_severe_hypo_overnight": float((d.glucose < SEVERE_HYPO).mean()) if len(d) >= 12 else np.nan,
        })
    ).reset_index()
    # Full-day TBR/TAR
    daily = g.groupby("patient_id").apply(
        lambda d: pd.Series({
            "tbr_pct": float((d.glucose < TBR).mean()) * 100,
            "tar_pct": float((d.glucose > TAR).mean()) * 100,
            "tir_pct": float(((d.glucose >= TBR) & (d.glucose <= TAR)).mean()) * 100,
        })
    ).reset_index()
    df = onp.merge(daily, on="patient_id").merge(simp, on="patient_id").dropna()
    df["cf_tertile"] = pd.qcut(df["cf_severe"], 3, labels=["low_cf", "mid_cf", "high_cf"])

    print("=== Patient table ===")
    print(df[["patient_id", "lineage", "cf_severe", "cf_tertile",
              "frac_severe_hypo_overnight", "tbr_pct", "tar_pct", "tir_pct"]]
          .sort_values(["lineage", "cf_severe"]).to_string(index=False))

    # Cell summaries
    cells_hypo = []
    cells_tbr = []
    cells_tar = []
    cells_tir = []
    for tert, sub in df.groupby("cf_tertile"):
        for lin in ["Loop (iOS)", "oref1 (modern)", "oref0 (legacy)"]:
            sub_lin = sub[sub.lineage == lin]
            if sub_lin.empty:
                continue
            for col, store in [("frac_severe_hypo_overnight", cells_hypo),
                               ("tbr_pct", cells_tbr),
                               ("tar_pct", cells_tar),
                               ("tir_pct", cells_tir)]:
                v = sub_lin[col].values
                lo, hi = boot_ci(v)
                store.append({"cf_tertile": str(tert), "lineage": lin, "n": int(len(v)),
                              "mean": float(v.mean()), "ci_lo": lo, "ci_hi": hi})

    print("\n=== Overnight severe hypo (BG<54, hr 0-2) by cell ===")
    for r in cells_hypo:
        print(f"  {r['cf_tertile']} {r['lineage']:18s} n={r['n']}: "
              f"{r['mean']*100:5.2f}%  CI=[{r['ci_lo']*100:.2f}, {r['ci_hi']*100:.2f}]")

    print("\n=== Full-day TBR (BG<70) ===")
    for r in cells_tbr:
        print(f"  {r['cf_tertile']} {r['lineage']:18s} n={r['n']}: "
              f"{r['mean']:5.2f}%  CI=[{r['ci_lo']:.2f}, {r['ci_hi']:.2f}]")

    print("\n=== Full-day TAR (BG>180) ===")
    for r in cells_tar:
        print(f"  {r['cf_tertile']} {r['lineage']:18s} n={r['n']}: "
              f"{r['mean']:5.2f}%  CI=[{r['ci_lo']:.2f}, {r['ci_hi']:.2f}]")

    print("\n=== Full-day TIR (70-180) ===")
    for r in cells_tir:
        print(f"  {r['cf_tertile']} {r['lineage']:18s} n={r['n']}: "
              f"{r['mean']:5.2f}%  CI=[{r['ci_lo']:.2f}, {r['ci_hi']:.2f}]")

    # Lineage-level pooled (no tertile)
    print("\n=== Lineage pooled (across tertiles) ===")
    pooled = df.groupby("lineage").agg(
        n=("patient_id", "nunique"),
        overnight_hypo=("frac_severe_hypo_overnight", "mean"),
        tbr=("tbr_pct", "mean"),
        tar=("tar_pct", "mean"),
        tir=("tir_pct", "mean"),
    ).round(3)
    print(pooled.to_string())

    summary = {
        "scope": "Hypo symmetry: overnight severe hypo + daily TBR/TAR/TIR by lineage x cf",
        "patient_table": df.to_dict(orient="records"),
        "cells_overnight_hypo": cells_hypo,
        "cells_tbr": cells_tbr,
        "cells_tar": cells_tar,
        "cells_tir": cells_tir,
        "pooled": pooled.reset_index().to_dict(orient="records"),
    }
    OUT.write_text(json.dumps(summary, indent=2, default=str))
    print(f"\n[exp-2925] {OUT}")


if __name__ == "__main__":
    main()
