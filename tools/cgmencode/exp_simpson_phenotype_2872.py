"""EXP-2872 — Simpson's paradox test on EXP-2870 phenotype → TIR.

EXP-2870 found stream_A_dominant patients have median TIR 82% vs
stream_B_normal 67%, AND that all stream_A_dominant patients are
Trio/OpenAPS while all stream_B_normal Loop. EXP-2871 confirmed
controller is causally implicated.

Question: is the phenotype→TIR association explained ENTIRELY by
controller (Simpson's paradox), or does it hold WITHIN each
controller cohort?

Specifically:
  - WITHIN Loop: only stream_B_normal observed (no within-cohort
    variation). Cannot test, but the absence of variation is itself
    informative.
  - WITHIN Trio: 5 stream_A_dominant + 2 stream_B_early + 1
    stream_B_normal. Test: does the TIR ranking hold?
  - WITHIN OpenAPS: 2 stream_A_dominant + 1 stream_B_early + 2
    stream_B_normal. Test: does the TIR ranking hold?
  - ACROSS controllers AT MATCHED phenotype: 1 Trio + 2 OpenAPS in
    stream_B_normal — do they have low TIR like the 6 Loop ones?
    1 Loop in stream_B_normal vs 5 Trio in stream_A_dominant — TIR
    gap exists?

Outputs:
  externals/experiments/exp-2872_simpson_check.json
  docs/60-research/figures/exp-2872_simpson_paradox.png
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

EXP = Path("externals/experiments")
FIG = Path("docs/60-research/figures")


def main() -> None:
    pdf = pd.read_parquet(EXP / "exp-2870_per_patient_crossover.parquet")
    if "controller" not in pdf.columns:
        # merge from EXP-2812
        tx = pd.read_parquet(EXP / "exp-2812_pre_post_transitions.parquet",
                             columns=["patient_id", "controller"])
        pdf = pdf.merge(tx.drop_duplicates("patient_id"),
                        on="patient_id", how="left")
    print(f"Loaded {len(pdf)} patients with phenotype + TIR + controller")

    # ---- Pooled (Simpson's paradox numerator) ----
    pooled = (pdf.groupby("phenotype")["tir"]
              .agg(["count", "median", "mean", "std"])
              .reset_index())
    print("\nPOOLED phenotype × TIR:")
    print(pooled.to_string(index=False))

    # ---- Within controller (Simpson's paradox denominator) ----
    within = (pdf.groupby(["controller", "phenotype"])["tir"]
              .agg(["count", "median", "mean"])
              .reset_index()
              .sort_values(["controller", "phenotype"]))
    print("\nWITHIN controller × phenotype × TIR:")
    print(within.to_string(index=False))

    # ---- Cross-controller AT MATCHED phenotype ----
    matched = (pdf.groupby(["phenotype", "controller"])["tir"]
               .agg(["count", "median"])
               .reset_index()
               .pivot(index="phenotype", columns="controller", values="median"))
    print("\nMATCHED phenotype × controller (median TIR):")
    print(matched.to_string())

    # ---- Spearman within each controller ----
    pheno_rank = {
        "stream_A_dominant": 0,
        "stream_B_late": 1,
        "stream_B_normal": 2,
        "stream_B_early": 3,
        "ambiguous": np.nan,
    }
    pdf["pheno_rank"] = pdf["phenotype"].map(pheno_rank)

    within_corr = {}
    for ctl, sub in pdf.groupby("controller"):
        s = sub.dropna(subset=["pheno_rank", "tir"])
        if len(s) >= 3 and s["pheno_rank"].nunique() >= 2:
            rho = s[["pheno_rank", "tir"]].corr(method="spearman").iloc[0, 1]
            within_corr[ctl] = {"n": int(len(s)),
                                "n_phenotypes": int(s["pheno_rank"].nunique()),
                                "spearman_rho": float(rho)}
        else:
            within_corr[ctl] = {"n": int(len(s)),
                                "n_phenotypes": int(s["pheno_rank"].nunique()),
                                "spearman_rho": None,
                                "note": "insufficient variation within cohort"}

    pooled_s = pdf.dropna(subset=["pheno_rank", "tir"])
    pooled_rho = (pooled_s[["pheno_rank", "tir"]].corr(method="spearman").iloc[0, 1]
                  if len(pooled_s) >= 3 else None)

    print("\nSpearman ρ(phenotype_rank, TIR):")
    print(f"  POOLED: {pooled_rho}")
    for ctl, d in within_corr.items():
        print(f"  {ctl}: {d}")

    # ---- Simpson interpretation ----
    # Test 1: Is the POOLED association strong? (|ρ| > 0.3)
    pooled_strong = abs(pooled_rho) > 0.3 if pooled_rho is not None else False
    # Test 2: Does any within-controller association FLIP sign vs pooled?
    flips = []
    for ctl, d in within_corr.items():
        if d["spearman_rho"] is None or pooled_rho is None:
            continue
        if (d["spearman_rho"] > 0) != (pooled_rho > 0):
            flips.append(ctl)
    # Test 3: Do within-controller associations DISSOLVE (|ρ| < 0.2)?
    dissolved = [
        ctl for ctl, d in within_corr.items()
        if d["spearman_rho"] is not None and abs(d["spearman_rho"]) < 0.2
    ]

    summary = {
        "experiment": "EXP-2872",
        "title": "Simpson's paradox test on EXP-2870 phenotype → TIR",
        "n_patients": int(len(pdf)),
        "pooled_phenotype_tir": pooled.to_dict(orient="records"),
        "within_controller": {
            ctl: sub.to_dict(orient="records")
            for ctl, sub in within.groupby("controller")
        },
        "matched_pivot": matched.fillna(np.nan).to_dict(orient="index"),
        "spearman": {
            "pooled_rho": pooled_rho,
            "within_controller": within_corr,
        },
        "checks": {
            "PASS_pooled_signal_present": pooled_strong,
            "PASS_simpson_paradox_detected": len(flips) > 0,
            "PASS_associations_dissolve_within": len(dissolved) >= 1,
        },
    }
    summary["checks_passed"] = sum(summary["checks"].values())

    interp_lines = []
    interp_lines.append(
        f"Pooled Spearman ρ(phenotype_rank, TIR) = {pooled_rho:.2f}."
        if pooled_rho is not None else
        "Pooled Spearman could not be computed."
    )
    if flips:
        interp_lines.append(
            f"SIMPSON'S PARADOX DETECTED: within {flips} the association "
            "FLIPS sign vs the pooled estimate. Pooled effect is an "
            "aggregation artifact."
        )
    elif dissolved:
        interp_lines.append(
            f"Within {dissolved} the association DISSOLVES (|ρ|<0.2). "
            "Pooled effect is largely driven by the controller "
            "confound, not the phenotype itself."
        )
    else:
        interp_lines.append(
            "No Simpson's paradox: within-controller associations point "
            "in the same direction as the pooled estimate. Phenotype "
            "carries TIR signal independently of controller."
        )
    # Loop-specific note
    loop_phenotypes = pdf.loc[pdf["controller"] == "Loop", "phenotype"].unique()
    if len(loop_phenotypes) <= 1:
        interp_lines.append(
            f"NOTE: Loop cohort has zero phenotype variation "
            f"(all {len(loop_phenotypes)} unique = {list(loop_phenotypes)}). "
            "Cannot test phenotype→TIR within Loop. Loop low TIR "
            "(67%) may reflect either the phenotype OR the controller; "
            "the design cannot distinguish in this cohort."
        )
    summary["interpretation"] = interp_lines

    (EXP / "exp-2872_simpson_check.json").write_text(
        json.dumps(summary, indent=2, default=str)
    )

    # ---- Figure ----
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    fig.suptitle("EXP-2872 — Simpson's paradox test on EXP-2870 phenotype → TIR",
                 fontsize=11)

    ax = axes[0]
    pheno_order = ["stream_A_dominant", "stream_B_late",
                   "stream_B_normal", "stream_B_early"]
    pheno_present = [p for p in pheno_order if p in pdf["phenotype"].values]
    # Pooled box
    data = [pdf.loc[pdf["phenotype"] == p, "tir"].dropna().values
            for p in pheno_present]
    bp = ax.boxplot(data, positions=range(len(pheno_present)),
                    showmeans=True, widths=0.5)
    ax.set_xticks(range(len(pheno_present)))
    ax.set_xticklabels(pheno_present, rotation=15)
    ax.set_ylabel("TIR (70-180)")
    ax.set_title(f"POOLED (n={len(pdf)})\nρ={pooled_rho:.2f}"
                 if pooled_rho is not None else "POOLED")
    ax.grid(alpha=0.3)

    ax = axes[1]
    colors = {"Loop": "#1f77b4", "Trio": "#d62728", "OpenAPS": "#2ca02c"}
    for ctl, sub in pdf.dropna(subset=["controller"]).groupby("controller"):
        s = sub.dropna(subset=["tir", "pheno_rank"])
        if s.empty:
            continue
        ax.scatter(s["pheno_rank"], s["tir"],
                   c=colors.get(ctl, "gray"), label=f"{ctl} (n={len(s)})",
                   s=80, alpha=0.7)
    ax.set_xticks([0, 1, 2, 3])
    ax.set_xticklabels(["A_dom", "B_late", "B_normal", "B_early"])
    ax.set_xlabel("Phenotype")
    ax.set_ylabel("TIR (70-180)")
    rho_txt = "; ".join(
        f"{c}:ρ={d['spearman_rho']:.2f}" if d["spearman_rho"] is not None
        else f"{c}:n/a"
        for c, d in within_corr.items()
    )
    ax.set_title(f"WITHIN controller\n{rho_txt}", fontsize=9)
    ax.legend()
    ax.grid(alpha=0.3)

    plt.tight_layout()
    FIG.mkdir(parents=True, exist_ok=True)
    plt.savefig(FIG / "exp-2872_simpson_paradox.png", dpi=120)
    plt.close()

    print(f"\nChecks passed: {summary['checks_passed']}/3")
    for line in interp_lines:
        print(f"  - {line}")


if __name__ == "__main__":
    main()
