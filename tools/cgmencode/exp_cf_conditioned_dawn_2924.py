"""EXP-2924 - Guard #6 cf-conditioning on the fasted-dawn gap.

The 8x Loop vs oref1 fasted-dawn gap (EXP-2923) could in
principle be a patient-selection artefact: maybe oref1 patients
have lower cf_severe (lower load) than Loop patients in this
cohort. Guard #6 (cf-conditioning) requires that any cross-design
claim be tested after matching or stratifying on cf load.

Method:
  - Per patient, compute fasted-dawn frac_hyper (state==FASTED,
    hour in [2,3,4]) from EXP-2923's pipeline.
  - Join with cf_severe and lineage from exp-2891.
  - Stratify by cf_severe tertile (low / mid / high) and report
    Loop vs oref1 within each tertile.
  - If the gap survives within tertile, design effect is robust.
  - Bootstrap CI on the within-tertile gap (n=2-5).

Scope: design-level robustness check. Per binding scope.
"""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent.parent
SIMP = REPO / "externals" / "experiments" / "exp-2891_simpson_dose_response.parquet"
GRID = REPO / "externals" / "ns-parquet" / "training" / "grid.parquet"
OUT = REPO / "externals" / "experiments" / "exp-2924_summary.json"

RNG = np.random.default_rng(2924)
N_BOOT = 2000
HYPER = 250


def boot_ci(values: np.ndarray) -> tuple[float, float]:
    if len(values) < 2:
        v = float(values[0]) if len(values) == 1 else float("nan")
        return v, v
    samples = RNG.choice(values, size=(N_BOOT, len(values)), replace=True).mean(axis=1)
    return float(np.percentile(samples, 2.5)), float(np.percentile(samples, 97.5))


def main() -> None:
    simp = pd.read_parquet(SIMP, columns=["patient_id", "lineage", "cf_severe"])
    simp = simp[simp.lineage.isin(["Loop (iOS)", "oref1 (modern)", "oref0 (legacy)"])]

    g = pd.read_parquet(GRID, columns=["patient_id", "time", "glucose", "time_since_carb_min"])
    g = g[g.patient_id.isin(set(simp.patient_id))].dropna(subset=["glucose"])
    g["hour"] = g["time"].dt.hour
    g = g[(g.hour.isin([2, 3, 4])) & (g.time_since_carb_min >= 300)]
    fasted_dawn = g.groupby("patient_id").apply(
        lambda d: pd.Series({
            "n_cells": len(d),
            "frac_hyper": float((d.glucose > HYPER).mean()) if len(d) >= 6 else np.nan,
        })
    ).reset_index()
    fasted_dawn = fasted_dawn.dropna(subset=["frac_hyper"])
    df = fasted_dawn.merge(simp, on="patient_id")

    # cf tertiles overall
    df["cf_tertile"] = pd.qcut(df["cf_severe"], 3, labels=["low_cf", "mid_cf", "high_cf"])

    print("=== Patient table ===")
    print(df[["patient_id", "lineage", "cf_severe", "cf_tertile", "frac_hyper", "n_cells"]]
          .sort_values(["cf_tertile", "lineage", "cf_severe"]).to_string(index=False))

    cells = []
    for tert, sub in df.groupby("cf_tertile"):
        for lin in ["Loop (iOS)", "oref1 (modern)", "oref0 (legacy)"]:
            sub_lin = sub[sub.lineage == lin]
            if sub_lin.empty:
                continue
            v = sub_lin["frac_hyper"].values
            lo, hi = boot_ci(v)
            cells.append({
                "cf_tertile": str(tert), "lineage": lin, "n": int(len(v)),
                "mean_frac_hyper": float(v.mean()),
                "ci_lo": lo, "ci_hi": hi,
                "patient_ids": sub_lin.patient_id.tolist(),
            })
    cdf = pd.DataFrame(cells)
    print("\n=== Cell-level (cf_tertile x lineage) ===")
    print(cdf.to_string(index=False))

    # Pairwise within-tertile Loop vs oref1 gap
    print("\n=== Within-tertile Loop vs oref1 gap ===")
    pairs = []
    for tert in df.cf_tertile.unique():
        loop = cdf[(cdf.cf_tertile == str(tert)) & (cdf.lineage == "Loop (iOS)")]
        ore = cdf[(cdf.cf_tertile == str(tert)) & (cdf.lineage == "oref1 (modern)")]
        if loop.empty or ore.empty:
            continue
        gap = float(loop.iloc[0]["mean_frac_hyper"] - ore.iloc[0]["mean_frac_hyper"])
        loop_v = df[(df.cf_tertile == tert) & (df.lineage == "Loop (iOS)")]["frac_hyper"].values
        ore_v = df[(df.cf_tertile == tert) & (df.lineage == "oref1 (modern)")]["frac_hyper"].values
        if len(loop_v) >= 2 and len(ore_v) >= 2:
            boot_l = RNG.choice(loop_v, size=(N_BOOT, len(loop_v)), replace=True).mean(axis=1)
            boot_o = RNG.choice(ore_v, size=(N_BOOT, len(ore_v)), replace=True).mean(axis=1)
            gaps = boot_l - boot_o
            ci_lo, ci_hi = float(np.percentile(gaps, 2.5)), float(np.percentile(gaps, 97.5))
            sig = (ci_lo > 0) or (ci_hi < 0)
        else:
            ci_lo = ci_hi = float("nan")
            sig = None
        pairs.append({
            "cf_tertile": str(tert),
            "n_loop": int(len(loop_v)), "n_oref1": int(len(ore_v)),
            "gap_loop_minus_oref1": gap,
            "ci_lo": ci_lo, "ci_hi": ci_hi,
            "ci_excludes_zero": sig,
        })
        print(f"  {tert}: gap={gap*100:5.2f}pp  CI=[{ci_lo*100:.2f}, {ci_hi*100:.2f}]pp  "
              f"n_loop={len(loop_v)}, n_oref1={len(ore_v)}, sig={sig}")

    summary = {
        "scope": "Guard #6 cf-conditioning on the fasted-dawn 8x gap",
        "patient_table": df.to_dict(orient="records"),
        "cells": cdf.to_dict(orient="records"),
        "pairs": pairs,
    }
    OUT.write_text(json.dumps(summary, indent=2, default=str))
    print(f"\n[exp-2924] {OUT}")


if __name__ == "__main__":
    main()
