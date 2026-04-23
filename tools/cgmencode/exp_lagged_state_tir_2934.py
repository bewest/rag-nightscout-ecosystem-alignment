"""EXP-2934 - Day-level TIR decomposed by lagged-BG state (Guard #8 audit).

EXP-2925 showed oref1 Pareto-dominates Loop on day-level TIR
(82.6% vs 66.1%). EXP-2933 introduced Guard #8 - condition on
state-at-event-onset before scoring within-window outcomes.

Apply Guard #8 retroactively to day-level TIR: stratify cells by
1-hour-prior BG tertile and recompute TIR within strata. If gap
collapses within strata, the day-level advantage is in-band
momentum (autoregressive state). If gap holds within strata,
the controller is actively pulling back from excursions.

Method per patient:
  1. For each 5-min cell, compute lag_60_bg = BG at t - 60 min.
  2. Bin lag_60_bg into global tertiles.
  3. Compute TIR within (patient, lag_bin).
  4. Per (design, lag_bin) average + bootstrap CI on gap.

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
OUT = REPO / "externals" / "experiments" / "exp-2934_summary.json"

RNG = np.random.default_rng(2934)
N_BOOT = 2000
TBR = 70
TAR = 180

LOOP_AB_OFF = {"a", "f"}
LOOP_AB_ON = {"c", "d", "e", "g", "i"}


def boot_mean_ci(values: np.ndarray) -> tuple[float, float]:
    if len(values) < 2:
        v = float(values[0]) if len(values) == 1 else float("nan")
        return v, v
    samples = RNG.choice(values, size=(N_BOOT, len(values)), replace=True).mean(axis=1)
    return float(np.percentile(samples, 2.5)), float(np.percentile(samples, 97.5))


def main() -> None:
    simp = pd.read_parquet(SIMP, columns=["patient_id", "lineage"]).drop_duplicates("patient_id")
    simp = simp[simp.lineage.isin(["Loop (iOS)", "oref1 (modern)"])]

    g = pd.read_parquet(GRID, columns=["patient_id", "time", "glucose"])
    g = g[g.patient_id.isin(set(simp.patient_id))].sort_values(["patient_id", "time"]).reset_index(drop=True)
    g = g.dropna(subset=["glucose"])

    # Compute lag_60_bg per patient (12 cells = 60 min on 5-min grid)
    g["lag_60_bg"] = g.groupby("patient_id")["glucose"].shift(12)
    g = g.dropna(subset=["lag_60_bg"])
    print(f"Cells with lag_60_bg: {len(g):,}")

    # Global tertile cutpoints on lag_60_bg
    cuts = np.percentile(g["lag_60_bg"], [33.33, 66.67])
    print(f"lag_60_bg tertile cutpoints: low<={cuts[0]:.0f}, mid<={cuts[1]:.0f}, high>{cuts[1]:.0f}")
    g["lag_bin"] = pd.cut(g["lag_60_bg"], bins=[-np.inf, cuts[0], cuts[1], np.inf],
                          labels=["low_lag", "mid_lag", "high_lag"])

    # Per (patient, lag_bin) TIR/TAR/TBR
    rows = []
    for (pid, lb), sub in g.groupby(["patient_id", "lag_bin"], observed=True):
        if len(sub) < 100:
            continue
        rows.append({
            "patient_id": pid, "lag_bin": str(lb), "n_cells": len(sub),
            "tir": float(((sub.glucose >= TBR) & (sub.glucose <= TAR)).mean()) * 100,
            "tar": float((sub.glucose > TAR).mean()) * 100,
            "tbr": float((sub.glucose < TBR).mean()) * 100,
            "mean_bg": float(sub.glucose.mean()),
        })
    pat = pd.DataFrame(rows).merge(simp, on="patient_id")

    def design(row):
        if row["lineage"] == "oref1 (modern)":
            return "oref1"
        if row["patient_id"] in LOOP_AB_ON:
            return "Loop_AB_ON"
        if row["patient_id"] in LOOP_AB_OFF:
            return "Loop_AB_OFF"
        return None

    pat["design"] = pat.apply(design, axis=1)
    pat = pat.dropna(subset=["design"])

    # Distribution of cells across lag_bins by design (the confound)
    print("\n=== Cell distribution across lag_bin (% of design's cells) ===")
    g_with_design = g.merge(simp, on="patient_id")
    g_with_design["design"] = g_with_design.apply(design, axis=1)
    g_with_design = g_with_design.dropna(subset=["design"])
    dist = (g_with_design.groupby(["design", "lag_bin"], observed=True).size()
            / g_with_design.groupby("design").size() * 100).unstack(fill_value=0).round(1)
    print(dist)

    print("\n=== TIR by (design, lag_bin) — mean of per-patient ===")
    summary = pat.groupby(["design", "lag_bin"]).agg(
        n_pat=("patient_id", "nunique"),
        tir=("tir", "mean"),
        tar=("tar", "mean"),
        tbr=("tbr", "mean"),
        mean_bg=("mean_bg", "mean"),
    ).round(2)
    print(summary.to_string())

    print("\n=== Within-lag-bin TIR gap (oref1 - design, pp) ===")
    pairs = []
    for lb in ["low_lag", "mid_lag", "high_lag"]:
        oref_v = pat[(pat.design == "oref1") & (pat.lag_bin == lb)]["tir"].values
        for d in ["Loop_AB_OFF", "Loop_AB_ON"]:
            cmp_v = pat[(pat.design == d) & (pat.lag_bin == lb)]["tir"].values
            if len(oref_v) == 0 or len(cmp_v) == 0:
                continue
            gap = float(oref_v.mean() - cmp_v.mean())
            if len(oref_v) >= 2 and len(cmp_v) >= 2:
                br = RNG.choice(oref_v, size=(N_BOOT, len(oref_v)), replace=True).mean(axis=1)
                bc = RNG.choice(cmp_v, size=(N_BOOT, len(cmp_v)), replace=True).mean(axis=1)
                ds = br - bc
                ci_lo, ci_hi = float(np.percentile(ds, 2.5)), float(np.percentile(ds, 97.5))
                sig = (ci_lo > 0) or (ci_hi < 0)
            else:
                ci_lo = ci_hi = float("nan"); sig = None
            pairs.append({"lag_bin": lb, "design": d,
                          "n_oref1": int(len(oref_v)), "n_design": int(len(cmp_v)),
                          "tir_gap_oref1_minus_design_pp": gap,
                          "ci_lo": ci_lo, "ci_hi": ci_hi, "sig": sig})
            tag = "*" if sig else " "
            print(f"  {lb:8s} vs {d:12s}: gap = {gap:+6.2f}pp  CI[{ci_lo:+.2f},{ci_hi:+.2f}] {tag}")

    # Marginal day-level TIR for reference
    print("\n=== Marginal day-level TIR (no conditioning) ===")
    marg = pat.groupby(["patient_id", "design"]).apply(
        lambda d: pd.Series({
            "tir_marginal": (d["tir"] * d["n_cells"]).sum() / d["n_cells"].sum()
        })
    ).reset_index()
    marg_design = marg.groupby("design")["tir_marginal"].mean().round(2)
    print(marg_design)

    out = {
        "scope": "Day-level TIR decomposed by lag_60_bg tertile (Guard #8 audit)",
        "n_cells": int(len(g)),
        "lag_cutpoints": [float(cuts[0]), float(cuts[1])],
        "cell_distribution_by_design": dist.to_dict(),
        "tir_by_design_lag": summary.reset_index().to_dict(orient="records"),
        "within_lag_pairs": pairs,
        "marginal_tir_by_design": marg_design.to_dict(),
    }
    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n[exp-2934] {OUT}")


if __name__ == "__main__":
    main()
