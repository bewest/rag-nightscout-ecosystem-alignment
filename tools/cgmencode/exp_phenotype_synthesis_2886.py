"""EXP-2886 — Three-dimensional phenotype synthesis.

Integrates three independent per-patient signals:

  1. Insulin-input behavior (EXP-2882 stack_score): how much the
     patient stacks boluses in evening vs rest.
  2. AID response (EXP-2885 braking_ratio): how aggressively the
     algorithm defends against descending BG.
  3. Physiological defense (EXP-2875 counter_reg_intercept +
     EXP-2877 beta_nadir): how well the body counter-regulates at
     hypo nadir.

Per-patient 3D coordinates enable:
  - Archetype classification (stacker/braker/defender, etc.)
  - Hidden-leverage detection (aggressive stacker + strong braking
    = closed-loop-dependent safety)
  - Orthogonality audit (are any two dimensions redundant?)
  - Controller-lineage contextualization (oref0 vs oref1 vs Loop)
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]

STACK_PATH = ROOT / "externals/experiments/exp-2882_stacker_phenotype.parquet"
BRAKE_PATH = ROOT / "externals/experiments/exp-2885_simpson_braking.parquet"
CR_PATH = ROOT / "externals/experiments/exp-2877_hypo_severity_per_patient.parquet"
HAAF_PATH = ROOT / "externals/experiments/exp-2878_haaf.parquet"
OUT = ROOT / "externals/experiments/exp-2886_phenotype.parquet"
OUT_SUMMARY = ROOT / "externals/experiments/exp-2886_phenotype_summary.json"
OUT_FIG = ROOT / "docs/60-research/figures/exp-2886_phenotype.png"


def lineage(ctrl: str) -> str:
    if ctrl == "OpenAPS":
        return "oref0 (legacy)"
    if ctrl in ("Trio", "AAPS"):
        return "oref1 (modern)"
    if ctrl == "Loop":
        return "Loop (iOS)"
    return "unknown"


def main() -> None:
    stack = pd.read_parquet(STACK_PATH)
    if stack.index.name == "patient_id":
        stack = stack.reset_index()
    print(f"stack rows: {len(stack)}")

    brake = pd.read_parquet(BRAKE_PATH)
    # Collapse per-patient braking (mean across TOD)
    brake_pp = (
        brake.groupby(["patient_id", "controller"])
        .agg(
            braking_ratio=("mean_ratio", "mean"),
            suspension_rate=("suspension_rate", "mean"),
        )
        .reset_index()
    )
    print(f"brake_pp: {len(brake_pp)}")

    # Counter-reg
    try:
        cr = pd.read_parquet(CR_PATH)
        if cr.index.name == "patient_id":
            cr = cr.reset_index()
        # EXP-2877 schema: median_beta + intercept
        cr_cols = {"patient_id"}
        if "median_beta" in cr.columns:
            cr_cols.add("median_beta")
        if "intercept" in cr.columns:
            cr_cols.add("intercept")
        if "counter_reg_intercept" in cr.columns:
            cr_cols.add("counter_reg_intercept")
        cr = cr[list(cr_cols)]
    except Exception as e:
        print(f"no CR file: {e}")
        cr = pd.DataFrame({"patient_id": []})

    # HAAF exposure
    try:
        haaf = pd.read_parquet(HAAF_PATH)
        if haaf.index.name == "patient_id":
            haaf = haaf.reset_index()
        haaf = haaf[["patient_id", "hypo_fraction", "severe_fraction"]]
    except Exception as e:
        print(f"no HAAF file: {e}")
        haaf = pd.DataFrame({"patient_id": []})

    # Merge
    df = stack[["patient_id", "controller", "stack_score",
                "delta_bolus4h", "delta_iob_start",
                "counter_reg_intercept"]].copy()
    df = df.merge(brake_pp[["patient_id", "braking_ratio",
                            "suspension_rate"]],
                  on="patient_id", how="left")
    if len(haaf):
        df = df.merge(haaf, on="patient_id", how="left")

    df["lineage"] = df["controller"].apply(lineage)

    # Hidden-leverage metric:
    # patients with aggressive stacking AND strong braking are
    # AID-dependent; if braking fails, they have far too much insulin.
    # Normalize: 1 - braking_ratio ≈ fraction of scheduled basal cut.
    df["hidden_leverage"] = df["stack_score"] * (1 - df["braking_ratio"])

    print("\nPer-lineage summary:")
    print(df.groupby("lineage").agg(
        n=("patient_id", "size"),
        stack=("stack_score", "mean"),
        brake_ratio=("braking_ratio", "mean"),
        susp_rate=("suspension_rate", "mean"),
        cr_intercept=("counter_reg_intercept", "mean"),
        hidden_lev=("hidden_leverage", "mean"),
    ).round(3).to_string())

    # Orthogonality matrix: spearman correlations among 3 signals
    dims = [
        ("stack_score", "stacking"),
        ("braking_ratio", "braking"),
        ("counter_reg_intercept", "counter_reg"),
    ]
    orth = {}
    for i, (a, an) in enumerate(dims):
        for b, bn in dims[i + 1:]:
            sub = df[[a, b]].dropna()
            if len(sub) >= 5:
                rho, p = stats.spearmanr(sub[a], sub[b])
                orth[f"{an}_vs_{bn}"] = {
                    "n": int(len(sub)),
                    "rho": float(rho),
                    "p": float(p),
                }

    print("\nOrthogonality (Spearman):")
    for k, v in orth.items():
        print(f"  {k:30s} n={v['n']}  rho={v['rho']:+.3f}  p={v['p']:.3f}")

    # Archetype classification
    def classify(row) -> str:
        stack = row.get("stack_score", np.nan)
        brake_r = row.get("braking_ratio", np.nan)
        cr = row.get("counter_reg_intercept", np.nan)
        if pd.isna(stack) or pd.isna(brake_r):
            return "insufficient_data"
        stacker = stack >= 0.6
        strong_brake = brake_r <= 0.10
        weak_brake = brake_r >= 0.30
        weak_cr = (not pd.isna(cr)) and cr < 1.0

        if stacker and strong_brake:
            return "hidden_leverage"
        if stacker and weak_brake:
            return "exposed_stacker"
        if stacker and weak_cr:
            return "stacker_weak_defense"
        if stacker:
            return "stacker_balanced"
        if strong_brake and weak_cr:
            return "algorithm_dependent"
        if weak_brake:
            return "lax_braking"
        if weak_cr:
            return "weak_defender"
        return "well_defended"

    df["archetype"] = df.apply(classify, axis=1)
    print("\nArchetype counts:")
    print(df.archetype.value_counts().to_string())

    print("\nArchetype × lineage:")
    print(pd.crosstab(df.archetype, df.lineage).to_string())

    df.to_parquet(OUT, index=False)

    # Figure: 2x2 panel
    fig, axes = plt.subplots(2, 2, figsize=(14, 11))

    lineage_colors = {
        "Loop (iOS)": "#1f77b4",
        "oref1 (modern)": "#ff7f0e",
        "oref0 (legacy)": "#2ca02c",
    }

    # Panel 1: stacking vs braking
    for lin, sub in df.groupby("lineage"):
        axes[0, 0].scatter(
            sub.stack_score, sub.braking_ratio,
            c=lineage_colors.get(lin, "gray"),
            label=f"{lin} (n={len(sub)})",
            s=80, edgecolor="black", alpha=0.8,
        )
    axes[0, 0].axvline(0.6, color="red", linestyle=":", lw=0.7,
                       label="stacker threshold")
    axes[0, 0].axhline(0.10, color="blue", linestyle=":", lw=0.7,
                       label="strong-brake threshold")
    axes[0, 0].set_xlabel("stack_score (EXP-2882)")
    axes[0, 0].set_ylabel("braking_ratio (EXP-2885)")
    axes[0, 0].set_title(
        "Stacking × Braking\n(upper-right = hidden-leverage risk)")
    axes[0, 0].legend(fontsize=8, loc="upper right")
    axes[0, 0].grid(alpha=0.3)

    # Panel 2: counter-reg vs hidden leverage
    for lin, sub in df.groupby("lineage"):
        axes[0, 1].scatter(
            sub.counter_reg_intercept, sub.hidden_leverage,
            c=lineage_colors.get(lin, "gray"),
            label=lin, s=80, edgecolor="black", alpha=0.8,
        )
    axes[0, 1].set_xlabel("counter_reg_intercept (EXP-2875)")
    axes[0, 1].set_ylabel("hidden_leverage = stack × (1 − braking_ratio)")
    axes[0, 1].set_title(
        "Physiological defense × algorithmic dependence")
    axes[0, 1].legend(fontsize=8)
    axes[0, 1].grid(alpha=0.3)

    # Panel 3: lineage means bar
    lineage_order = ["Loop (iOS)", "oref1 (modern)", "oref0 (legacy)"]
    metrics = [
        ("stack_score", "stack"),
        ("braking_ratio", "brake_ratio"),
        ("suspension_rate", "susp_rate"),
        ("counter_reg_intercept", "cr_int"),
    ]
    x_pos = np.arange(len(lineage_order))
    w = 0.2
    for i, (col, lab) in enumerate(metrics):
        vals = [df[df.lineage == lin][col].mean() for lin in lineage_order]
        axes[1, 0].bar(x_pos + (i - 1.5) * w, vals, w, label=lab)
    axes[1, 0].set_xticks(x_pos)
    axes[1, 0].set_xticklabels(lineage_order, rotation=15, fontsize=8)
    axes[1, 0].set_title("Per-lineage mean phenotype profiles")
    axes[1, 0].legend(fontsize=8)
    axes[1, 0].grid(axis="y", alpha=0.3)

    # Panel 4: archetype distribution
    arch_counts = pd.crosstab(df.archetype, df.lineage).reindex(
        columns=lineage_order, fill_value=0
    )
    arch_counts.plot(
        kind="barh", stacked=True, ax=axes[1, 1],
        color=[lineage_colors[l] for l in lineage_order],
    )
    axes[1, 1].set_title("Archetype distribution by lineage")
    axes[1, 1].set_xlabel("patients")
    axes[1, 1].legend(fontsize=8)
    axes[1, 1].grid(axis="x", alpha=0.3)

    fig.suptitle(
        "EXP-2886 — Three-dimensional phenotype synthesis "
        "(stacking × braking × counter-regulation)",
        fontsize=13,
    )
    fig.tight_layout()
    OUT_FIG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_FIG, dpi=110)
    plt.close(fig)

    summary = {
        "exp_id": "2886",
        "n_patients": int(len(df)),
        "lineage_means": df.groupby("lineage").agg(
            n=("patient_id", "size"),
            stack=("stack_score", "mean"),
            brake_ratio=("braking_ratio", "mean"),
            susp_rate=("suspension_rate", "mean"),
            cr_intercept=("counter_reg_intercept", "mean"),
            hidden_lev=("hidden_leverage", "mean"),
        ).round(4).to_dict(orient="index"),
        "orthogonality": orth,
        "archetype_counts": df.archetype.value_counts().to_dict(),
        "archetype_by_lineage": pd.crosstab(
            df.archetype, df.lineage
        ).to_dict(orient="index"),
    }

    # Find hidden-leverage candidates
    hl = df.nlargest(5, "hidden_leverage")[
        ["patient_id", "controller", "stack_score", "braking_ratio",
         "hidden_leverage", "counter_reg_intercept"]
    ]
    summary["top_hidden_leverage"] = hl.to_dict(orient="records")
    print("\nTop hidden-leverage candidates:")
    print(hl.round(3).to_string(index=False))

    summary["verdict"] = (
        "Three-dimensional phenotype orthogonality: " +
        "; ".join(
            f"{k} rho={v['rho']:+.2f} p={v['p']:.2f}"
            for k, v in orth.items()
        ) +
        f". Hidden-leverage archetype n={df[df.archetype == 'hidden_leverage'].shape[0]}."
    )
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2, default=str))
    print(f"\nVerdict: {summary['verdict']}")


if __name__ == "__main__":
    main()
