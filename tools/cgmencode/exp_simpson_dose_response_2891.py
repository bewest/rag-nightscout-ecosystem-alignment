"""EXP-2891 - Simpson-stratified AID protection by lineage x aggressiveness.

The user's long-standing concern applied to counterfactual outcomes:
oref1 patients show the strongest AID protection magnitude per
EXP-2889 (and strongest braking per EXP-2885).  Is this a LINEAGE
effect, or are oref1 users simply more aggressive setters whose
settings force the controller to brake harder?

Method:
  1. Compute per-patient aggressiveness:
        aggr = rank(mean_sched_basal_event) + rank(mean_bolus_4h)
     (same formulation as EXP-2885)
  2. Split into terciles within the whole cohort
  3. Cross with lineage (Loop / oref1 / oref0)
  4. For each cell, compute mean aid_protection_severe and
     mean counterfactual_severe
  5. Test: does lineage effect survive WITHIN aggressiveness tercile?
  6. Permutation test: shuffle lineage labels, recompute lineage
     effect size, see where observed falls.

If lineage effect vanishes within tercile → finding was Simpson
(aggressiveness was confounding lineage).  If lineage effect survives
→ genuine controller-family signature.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

OUT = Path("externals/experiments")
FIGS = Path("docs/60-research/figures")
RNG = np.random.default_rng(2891)


def main() -> None:
    ev = pd.read_parquet(OUT / "exp-2881_evening_drivers.parquet")
    protect = pd.read_parquet(OUT / "exp-2889_counterfactual_replay.parquet")

    aggr = (ev.groupby("patient_id")
              .agg(mean_sched_basal=("sched_basal", "mean"),
                   mean_bolus4h=("bolus_4h", "mean"),
                   n_events=("bg_start", "size"))
              .reset_index())
    aggr["r_basal"] = aggr["mean_sched_basal"].rank()
    aggr["r_bolus"] = aggr["mean_bolus4h"].rank()
    aggr["aggressiveness"] = aggr["r_basal"] + aggr["r_bolus"]
    aggr["tercile"] = pd.qcut(aggr["aggressiveness"], 3,
                              labels=["conservative", "moderate",
                                      "aggressive"])

    merged = protect.merge(
        aggr[["patient_id", "aggressiveness", "tercile",
              "mean_sched_basal", "mean_bolus4h"]],
        on="patient_id", how="left")
    merged = merged.dropna(subset=["lineage", "aid_protection_severe",
                                   "tercile"])
    print(f"n={len(merged)} patients with full data")
    print("lineage distribution:",
          merged["lineage"].value_counts().to_dict())
    print("tercile distribution:",
          merged["tercile"].value_counts().to_dict())

    # ------------------------------------------------------------------
    # Pooled (Simpson-vulnerable) lineage effect
    # ------------------------------------------------------------------
    pooled = (merged.groupby("lineage")
                    .agg(n=("patient_id", "size"),
                         protection=("aid_protection_severe", "mean"),
                         cf_severe=("cf_severe", "mean"),
                         obs_severe=("obs_severe", "mean"),
                         mean_aggr=("aggressiveness", "mean"))
                    .reset_index())
    print("\nPooled by lineage:")
    print(pooled.to_string(index=False))

    # ------------------------------------------------------------------
    # Lineage x aggressiveness cells
    # ------------------------------------------------------------------
    cells = (merged.groupby(["lineage", "tercile"], observed=True)
                   .agg(n=("patient_id", "size"),
                        protection=("aid_protection_severe", "mean"),
                        cf_severe=("cf_severe", "mean"),
                        obs_severe=("obs_severe", "mean"))
                   .reset_index())
    print("\nLineage x aggressiveness tercile:")
    print(cells.to_string(index=False))

    # ------------------------------------------------------------------
    # Test 1: does lineage rank-order of protection survive within
    # tercile?
    # ------------------------------------------------------------------
    within_tercile_tests = []
    for terc in ["conservative", "moderate", "aggressive"]:
        sub = merged[merged["tercile"] == terc]
        lineages = sub["lineage"].unique()
        if len(lineages) < 2:
            continue
        groups = [sub[sub["lineage"] == ln]["aid_protection_severe"].values
                  for ln in lineages]
        # Skip if any group too small for meaningful test
        if min(len(g) for g in groups) < 2:
            within_tercile_tests.append({
                "tercile": terc, "kruskal_H": None, "p": None,
                "lineage_n": {ln: int(len(g)) for ln, g in
                              zip(lineages, groups)},
                "note": "underpowered (some lineage n<2)",
            })
            continue
        h, p = stats.kruskal(*groups)
        within_tercile_tests.append({
            "tercile": terc,
            "kruskal_H": float(h), "p": float(p),
            "lineage_n": {ln: int(len(g)) for ln, g in
                          zip(lineages, groups)},
            "lineage_means": {ln: float(np.mean(g)) for ln, g in
                              zip(lineages, groups)},
        })
        print(f"  within {terc}: Kruskal H={h:.2f} p={p:.3f} "
              f"ns={dict((ln, len(g)) for ln, g in zip(lineages, groups))}")

    # ------------------------------------------------------------------
    # Test 2: permutation test on lineage effect size
    # (max lineage mean − min lineage mean)
    # ------------------------------------------------------------------
    def lineage_range(df):
        means = df.groupby("lineage")["aid_protection_severe"].mean()
        return float(means.max() - means.min())

    observed_range = lineage_range(merged)
    perms = []
    for _ in range(5000):
        shuffled = merged.copy()
        shuffled["lineage"] = RNG.permutation(shuffled["lineage"].values)
        perms.append(lineage_range(shuffled))
    perms = np.array(perms)
    p_perm = float((perms >= observed_range).mean())
    print(f"\nPermutation test of lineage effect size (range of means):")
    print(f"  observed = {observed_range:.3f}")
    print(f"  p_perm   = {p_perm:.4f}  (n=5000)")

    # ------------------------------------------------------------------
    # Test 3: ANCOVA-style - aggressiveness-adjusted lineage effect
    # via simple residualisation
    # ------------------------------------------------------------------
    import statsmodels.api as sm
    # Model protection = f(aggressiveness) + lineage residual
    X = sm.add_constant(merged[["aggressiveness"]])
    y = merged["aid_protection_severe"].values
    fit = sm.OLS(y, X).fit()
    merged["protection_resid"] = y - fit.predict(X)
    resid_by_lin = (merged.groupby("lineage")["protection_resid"]
                          .agg(["mean", "count"]).reset_index())
    print("\nAggressiveness-adjusted protection residuals:")
    print(resid_by_lin.to_string(index=False))

    groups = [merged[merged["lineage"] == ln]["protection_resid"].values
              for ln in merged["lineage"].unique()]
    h_r, p_r = stats.kruskal(*groups)
    print(f"  Kruskal on residuals: H={h_r:.2f} p={p_r:.3f}")

    # ------------------------------------------------------------------
    # Figure
    # ------------------------------------------------------------------
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))

    ax = axes[0]
    pivot = (cells.pivot(index="tercile", columns="lineage",
                         values="protection")
                  .reindex(["conservative", "moderate", "aggressive"]))
    pivot.plot(kind="bar", ax=ax, width=0.8)
    ax.set_ylabel("mean AID protection_severe")
    ax.set_title("Lineage x aggressiveness (Simpson check)")
    ax.set_xticklabels(pivot.index, rotation=0, fontsize=9)
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3, axis="y")

    ax = axes[1]
    ax.hist(perms, bins=50, color="steelblue", alpha=0.8,
            label="permutations (H0)")
    ax.axvline(observed_range, color="firebrick", ls="--",
               label=f"observed={observed_range:.2f}")
    ax.set_xlabel("max - min lineage mean of AID protection")
    ax.set_ylabel("count")
    ax.set_title(f"Permutation test  p={p_perm:.3f}")
    ax.legend(fontsize=8)

    ax = axes[2]
    for ln, g in merged.groupby("lineage"):
        ax.scatter(g["aggressiveness"], g["aid_protection_severe"] * 100,
                   label=ln, s=60, alpha=0.8)
    ax.set_xlabel("aggressiveness rank sum")
    ax.set_ylabel("AID protection severe (%)")
    ax.set_title("Dose-response (points per patient)")
    ax.legend(fontsize=7)
    ax.grid(alpha=0.3)

    fig.tight_layout()
    fig_path = FIGS / "exp-2891_simpson_dose_response.png"
    fig.savefig(fig_path, dpi=130)
    plt.close(fig)

    summary = {
        "exp": "EXP-2891",
        "n_patients": int(len(merged)),
        "pooled_by_lineage": pooled.to_dict(orient="records"),
        "cells": cells.to_dict(orient="records"),
        "within_tercile_tests": within_tercile_tests,
        "permutation_test": {
            "observed_range": observed_range,
            "p_perm": p_perm,
            "n_perms": 5000,
        },
        "ancova_residuals": {
            "lineage_means": resid_by_lin.to_dict(orient="records"),
            "kruskal_H": float(h_r),
            "kruskal_p": float(p_r),
        },
        "figure": str(fig_path),
    }
    (OUT / "exp-2891_simpson_dose_response_summary.json").write_text(
        json.dumps(summary, indent=2, default=str))
    merged.to_parquet(OUT / "exp-2891_simpson_dose_response.parquet")
    print(f"\nWrote {fig_path}")


if __name__ == "__main__":
    main()
