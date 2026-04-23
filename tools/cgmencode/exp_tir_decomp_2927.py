"""EXP-2927 - Decompose oref1's TIR advantage: fasted vs post-prandial.

oref1 outperforms Loop on TIR by 12-19 pp (EXP-2925). Two
candidate mechanisms:
  (A) Better EGP handling - shows up in fasted cells
  (B) Better carb handling - shows up in post-prandial cells

Decomposition: per-patient TIR within state, then design-gap
within (cf_tertile, state). Bootstrap CIs.

Scope: design-feature attribution. AID-author audience.
"""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent.parent
SIMP = REPO / "externals" / "experiments" / "exp-2891_simpson_dose_response.parquet"
GRID = REPO / "externals" / "ns-parquet" / "training" / "grid.parquet"
OUT = REPO / "externals" / "experiments" / "exp-2927_summary.json"

RNG = np.random.default_rng(2927)
N_BOOT = 2000
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

    g = pd.read_parquet(GRID, columns=["patient_id", "time", "glucose", "time_since_carb_min"])
    g = g[g.patient_id.isin(set(simp.patient_id))].dropna(subset=["glucose"])
    g["state"] = np.where(g.time_since_carb_min >= 300, "FASTED",
                          np.where(g.time_since_carb_min <= 180, "PP", "MID"))
    g = g[g.state != "MID"]

    rows = []
    for (pid, st), sub in g.groupby(["patient_id", "state"]):
        if len(sub) < 100:
            continue
        rows.append({
            "patient_id": pid, "state": st, "n_cells": len(sub),
            "tir": float(((sub.glucose >= TBR) & (sub.glucose <= TAR)).mean()) * 100,
            "tar": float((sub.glucose > TAR).mean()) * 100,
            "tbr": float((sub.glucose < TBR).mean()) * 100,
        })
    pat = pd.DataFrame(rows).merge(simp, on="patient_id")
    pat["cf_tertile"] = pd.qcut(pat["cf_severe"], 3, labels=["low_cf", "mid_cf", "high_cf"])

    print("=== Per-state TIR by lineage (pooled across cf) ===")
    pooled = pat.groupby(["lineage", "state"]).agg(
        n=("patient_id", "nunique"),
        tir=("tir", "mean"),
        tar=("tar", "mean"),
        tbr=("tbr", "mean"),
    ).round(2)
    print(pooled.to_string())

    # Loop vs oref1 gap per state x cf
    print("\n=== Loop vs oref1 TIR gap by (cf_tertile, state) ===")
    pairs = []
    for tert in ["low_cf", "mid_cf", "high_cf"]:
        for st in ["FASTED", "PP"]:
            loop_v = pat[(pat.cf_tertile == tert) & (pat.state == st) & (pat.lineage == "Loop (iOS)")]["tir"].values
            ore_v = pat[(pat.cf_tertile == tert) & (pat.state == st) & (pat.lineage == "oref1 (modern)")]["tir"].values
            if len(loop_v) == 0 or len(ore_v) == 0:
                continue
            gap = float(ore_v.mean() - loop_v.mean())
            if len(loop_v) >= 2 and len(ore_v) >= 2:
                bl = RNG.choice(loop_v, size=(N_BOOT, len(loop_v)), replace=True).mean(axis=1)
                bo = RNG.choice(ore_v, size=(N_BOOT, len(ore_v)), replace=True).mean(axis=1)
                gaps = bo - bl
                ci_lo, ci_hi = float(np.percentile(gaps, 2.5)), float(np.percentile(gaps, 97.5))
                sig = (ci_lo > 0) or (ci_hi < 0)
            else:
                ci_lo = ci_hi = float("nan"); sig = None
            pairs.append({"cf_tertile": tert, "state": st,
                          "n_loop": int(len(loop_v)), "n_oref1": int(len(ore_v)),
                          "tir_gap_oref1_minus_loop_pp": gap,
                          "ci_lo": ci_lo, "ci_hi": ci_hi, "sig": sig})
            print(f"  {tert} {st:7s}: oref1-Loop = {gap:+5.2f}pp  CI=[{ci_lo:+.2f}, {ci_hi:+.2f}]  "
                  f"n={len(loop_v)},{len(ore_v)} sig={sig}")

    summary = {
        "scope": "Decompose oref1 TIR advantage: fasted (EGP) vs PP (carbs)",
        "patient_table": pat.to_dict(orient="records"),
        "pooled_state_lineage": pooled.reset_index().to_dict(orient="records"),
        "pairs_loop_vs_oref1": pairs,
    }
    OUT.write_text(json.dumps(summary, indent=2, default=str))
    print(f"\n[exp-2927] {OUT}")


if __name__ == "__main__":
    main()
