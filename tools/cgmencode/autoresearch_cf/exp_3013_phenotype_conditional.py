"""EXP-3013: Phenotype-conditional analysis of per-patient (T*, M*) recommendations.

Joins EXP-3012's per-patient recommendation table with the EXP-2886/2995
phenotype axes (braking_ratio, stack_score, hidden_leverage, algorithm_mode)
and tests whether the per-patient unrealised benefit / optimal lever is
predictable from phenotype.

Hypothesis: high-stack-score patients should have the largest unrealised
benefit (more SMBs delivered late = more headroom for the cf-replay).

Outputs
  externals/experiments/exp-3013_phenotype_conditional.parquet
  externals/experiments/exp-3013_summary.json
  docs/60-research/figures/exp-3013_phenotype_scatter.png
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[3]
EXT = ROOT / "externals" / "experiments"
DOCS_FIG = ROOT / "docs" / "60-research" / "figures"
DOCS_FIG.mkdir(parents=True, exist_ok=True)

REC = EXT / "exp-3012_per_patient.parquet"
PHENO_2886 = EXT / "exp-2886_phenotype.parquet"
PHENO_2995 = EXT / "exp-2995_phenotype_x_algorithm_mode.parquet"

OUT_PARQUET = EXT / "exp-3013_phenotype_conditional.parquet"
OUT_JSON = EXT / "exp-3013_summary.json"
OUT_FIG = DOCS_FIG / "exp-3013_phenotype_scatter.png"


def main() -> None:
    rec = pd.read_parquet(REC)
    ph = pd.read_parquet(PHENO_2886)
    ph2 = pd.read_parquet(PHENO_2995)[["patient_id", "tercile", "aggressiveness"]]

    df = rec.merge(
        ph[["patient_id", "stack_score", "braking_ratio", "hidden_leverage",
            "algorithm_mode", "archetype", "hypo_fraction"]],
        on="patient_id", how="inner",
    ).merge(ph2, on="patient_id", how="left")

    print(f"[EXP-3013] joined {len(df)} / {len(rec)} patients with phenotype")

    df["abs_benefit"] = -df["rec_delta_over_pp"]

    # Spearman correlations: phenotype axis vs (benefit, T*, M*).
    targets = {
        "abs_benefit (overshoot reduction, pp)": "abs_benefit",
        "rec_T_min (min earlier)": "rec_T_min",
        "rec_M_mult (magnitude multiplier)": "rec_M_mult",
        "rec_delta_hypo_pp": "rec_delta_hypo_pp",
    }
    axes = ["stack_score", "braking_ratio", "hidden_leverage", "hypo_fraction"]

    rows = []
    for tgt_name, tgt in targets.items():
        for ax in axes:
            sub = df[[ax, tgt]].dropna()
            if len(sub) < 5:
                continue
            rho, p = spearmanr(sub[ax], sub[tgt])
            rows.append({
                "phenotype_axis": ax,
                "target": tgt,
                "n": int(len(sub)),
                "spearman_rho": float(rho),
                "p_value": float(p),
            })
    corr = pd.DataFrame(rows)

    print("\n=== Spearman correlations (phenotype × recommendation) ===")
    for tgt_name, tgt in targets.items():
        print(f"\n  Target: {tgt_name}")
        sub = corr[corr["target"] == tgt].sort_values("spearman_rho", key=abs, ascending=False)
        for _, r in sub.iterrows():
            sig = "**" if r["p_value"] < 0.05 else ("*" if r["p_value"] < 0.10 else "")
            print(f"    {r['phenotype_axis']:>20}  rho={r['spearman_rho']:+.3f}  p={r['p_value']:.3f}  n={r['n']}  {sig}")

    # Stratify by algorithm_mode.
    print("\n=== Stratified by algorithm_mode ===")
    grp = df.groupby("algorithm_mode").agg(
        n=("patient_id", "count"),
        mean_benefit=("abs_benefit", "mean"),
        std_benefit=("abs_benefit", "std"),
        mean_T=("rec_T_min", "mean"),
        mean_M=("rec_M_mult", "mean"),
        mean_stack=("stack_score", "mean"),
        mean_braking=("braking_ratio", "mean"),
    ).round(3)
    print(grp.to_string())

    # Stratify by archetype.
    print("\n=== Stratified by archetype ===")
    grp_arch = df.groupby("archetype").agg(
        n=("patient_id", "count"),
        mean_benefit=("abs_benefit", "mean"),
        mean_T=("rec_T_min", "mean"),
        mean_M=("rec_M_mult", "mean"),
    ).round(3)
    print(grp_arch.to_string())

    # Visualisation: 4-panel scatter of phenotype axes vs benefit.
    fig, axes_p = plt.subplots(2, 2, figsize=(11, 9))
    color_map = {
        "Loop-AB-ON": "tab:blue", "Loop-AB-OFF": "tab:cyan",
        "Trio-oref1": "tab:red",
        "AAPS-oref0": "tab:green", "AAPS-oref1": "tab:olive",
        "unknown": "tab:gray",
    }
    df["color"] = df["algorithm_mode"].map(color_map).fillna("tab:gray")

    for ax_obj, ax_name in zip(axes_p.flat, axes):
        ax_obj.scatter(df[ax_name], df["abs_benefit"], c=df["color"], s=70, alpha=0.85, edgecolor="k")
        sub = df[[ax_name, "abs_benefit"]].dropna()
        if len(sub) >= 5:
            rho, p = spearmanr(sub[ax_name], sub["abs_benefit"])
            ax_obj.set_title(f"{ax_name}  (Spearman ρ={rho:+.2f}, p={p:.2f})")
        else:
            ax_obj.set_title(ax_name)
        ax_obj.set_xlabel(ax_name)
        ax_obj.set_ylabel("overshoot reduction (pp)")
        ax_obj.grid(alpha=0.3)
    handles = [plt.Line2D([0], [0], marker='o', linestyle='', color=c, label=k,
                          markeredgecolor='k') for k, c in color_map.items()
               if k in df["algorithm_mode"].unique()]
    fig.legend(handles=handles, loc="lower center", ncol=len(handles), bbox_to_anchor=(0.5, -0.02))
    fig.suptitle("EXP-3013: Phenotype axes vs cf-replay unrealised benefit (n=24 patients)")
    fig.tight_layout(rect=[0, 0.03, 1, 0.97])
    fig.savefig(OUT_FIG, dpi=130, bbox_inches="tight")
    print(f"\n  → {OUT_FIG}")

    df.drop(columns=["color"]).to_parquet(OUT_PARQUET, index=False)

    summary = {
        "exp_id": "EXP-3013",
        "n_joined": int(len(df)),
        "spearman_correlations": corr.to_dict(orient="records"),
        "by_algorithm_mode": grp.reset_index().to_dict(orient="records"),
        "by_archetype": grp_arch.reset_index().to_dict(orient="records"),
    }
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str))
    print(f"  → {OUT_JSON}")


if __name__ == "__main__":
    main()
