"""EXP-2888 - Hidden-leverage construct validation against outcomes.

Counter-causal guard:  EXP-2886 synthesized a composite
`hidden_leverage = stack_score * (1 - braking_ratio)` from three
orthogonal phenotype axes.  EXP-2887 rejected one mechanistic story
(HAAF mediation).  The remaining question is external / construct
validity:  does hidden_leverage predict the outcome variable
(severe_fraction) that motivated the construct in the first place?

Tests:
    1. Univariate Spearman: hidden_leverage -> severe_fraction
    2. Univariate Spearman: each component separately
    3. Multi-factor OLS: severe_fraction ~ stack + brake + CR
       (does the composite add explanatory power beyond components?)
    4. Archetype stratification: severe_fraction by archetype

This is a *construct validation* experiment, not a mechanism test.
Even if the lineage mechanism is unknown (EXP-2887), the composite
can be actionable if it identifies at-risk patients.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

OUT = Path("externals/experiments")
FIGS = Path("docs/60-research/figures")
FIGS.mkdir(parents=True, exist_ok=True)


def main() -> None:
    df = pd.read_parquet(OUT / "exp-2886_phenotype.parquet")
    n_all = len(df)

    # EXP-2886 severe_fraction comes from EXP-2878 which excludes patients
    # with zero severe events -> not quite true.  Drop any NaN.
    df = df.dropna(subset=["severe_fraction", "hidden_leverage",
                           "stack_score", "braking_ratio",
                           "counter_reg_intercept"]).copy()
    print(f"Patients with full data: {len(df)}/{n_all}")

    # ------------------------------------------------------------------
    # 1. Univariate correlations
    # ------------------------------------------------------------------
    def rho(a, b):
        r, p = stats.spearmanr(df[a], df[b])
        return {"var": a, "rho": float(r), "p": float(p), "n": len(df)}

    uni = [
        rho("hidden_leverage", "severe_fraction"),
        rho("stack_score", "severe_fraction"),
        rho("braking_ratio", "severe_fraction"),
        rho("counter_reg_intercept", "severe_fraction"),
        rho("hidden_leverage", "hypo_fraction"),
    ]
    for u in uni:
        print(f"  {u['var']:28s} vs outcome  rho={u['rho']:+.3f} p={u['p']:.3f}")

    # ------------------------------------------------------------------
    # 2. Multi-factor OLS  (does composite add over components?)
    # ------------------------------------------------------------------
    y = df["severe_fraction"].values
    X_parts = df[["stack_score", "braking_ratio",
                  "counter_reg_intercept"]].copy()
    X_parts = sm.add_constant(X_parts)
    m_parts = sm.OLS(y, X_parts).fit()

    X_comp = df[["hidden_leverage"]].copy()
    X_comp = sm.add_constant(X_comp)
    m_comp = sm.OLS(y, X_comp).fit()

    # Nested-model test: do the 3 components beat the single composite?
    # (they use more df, so need adj-r2 comparison, not F)
    parts_result = {
        "adj_r2": float(m_parts.rsquared_adj),
        "r2": float(m_parts.rsquared),
        "params": {k: float(v) for k, v in m_parts.params.items()},
        "pvalues": {k: float(v) for k, v in m_parts.pvalues.items()},
    }
    comp_result = {
        "adj_r2": float(m_comp.rsquared_adj),
        "r2": float(m_comp.rsquared),
        "params": {k: float(v) for k, v in m_comp.params.items()},
        "pvalues": {k: float(v) for k, v in m_comp.pvalues.items()},
    }
    print("\n3-component model:",
          f"adj_r2={parts_result['adj_r2']:.3f}")
    print("composite model:   ",
          f"adj_r2={comp_result['adj_r2']:.3f}")

    # ------------------------------------------------------------------
    # 3. Archetype stratification  (non-parametric)
    # ------------------------------------------------------------------
    arch_stats = (df.groupby("archetype")["severe_fraction"]
                    .agg(["mean", "median", "count"]).reset_index())
    print("\nSevere fraction by archetype:")
    print(arch_stats.to_string(index=False))

    # Kruskal across archetypes
    groups = [g["severe_fraction"].values
              for _, g in df.groupby("archetype") if len(g) >= 2]
    kw = None
    if len(groups) >= 2:
        kw_stat, kw_p = stats.kruskal(*groups)
        kw = {"H": float(kw_stat), "p": float(kw_p),
              "n_groups": len(groups)}
        print(f"Kruskal-Wallis across archetypes: H={kw_stat:.2f} "
              f"p={kw_p:.3f}")

    # ------------------------------------------------------------------
    # 4. Figures
    # ------------------------------------------------------------------
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))

    ax = axes[0]
    for arch, g in df.groupby("archetype"):
        ax.scatter(g["hidden_leverage"], g["severe_fraction"] * 100,
                   label=arch, s=60, alpha=0.75)
    ax.set_xlabel("hidden_leverage  (stack × (1 − brake))")
    ax.set_ylabel("severe hypo fraction  (%)")
    r, p = stats.spearmanr(df["hidden_leverage"], df["severe_fraction"])
    ax.set_title(f"Construct validation\nρ={r:+.3f}  p={p:.3f}  n={len(df)}")
    ax.legend(fontsize=7, loc="upper left")
    ax.grid(alpha=0.3)

    ax = axes[1]
    comps = ["stack_score", "braking_ratio", "counter_reg_intercept",
             "hidden_leverage"]
    rs = [stats.spearmanr(df[c], df["severe_fraction"])[0] for c in comps]
    ps = [stats.spearmanr(df[c], df["severe_fraction"])[1] for c in comps]
    xs = np.arange(len(comps))
    colors = ["steelblue" if p_ > 0.05 else "firebrick" for p_ in ps]
    ax.bar(xs, rs, color=colors)
    ax.axhline(0, color="k", lw=0.5)
    ax.set_xticks(xs)
    ax.set_xticklabels([c.replace("_", "\n") for c in comps],
                       fontsize=8)
    ax.set_ylabel("Spearman ρ with severe_fraction")
    ax.set_title("Component vs composite")
    for xi, (r_, p_) in enumerate(zip(rs, ps)):
        ax.text(xi, r_ + (0.02 if r_ >= 0 else -0.04),
                f"p={p_:.2f}", ha="center", fontsize=8)
    ax.grid(alpha=0.3, axis="y")

    ax = axes[2]
    arch_order = (df.groupby("archetype")["severe_fraction"]
                    .median().sort_values().index.tolist())
    data = [df[df["archetype"] == a]["severe_fraction"].values * 100
            for a in arch_order]
    ax.boxplot(data, labels=arch_order, showmeans=True)
    ax.set_xticklabels(arch_order, rotation=25, ha="right", fontsize=8)
    ax.set_ylabel("severe hypo fraction (%)")
    title = "Outcome by archetype"
    if kw is not None:
        title += f"\nKruskal p={kw['p']:.3f}"
    ax.set_title(title)
    ax.grid(alpha=0.3, axis="y")

    fig.tight_layout()
    fig_path = FIGS / "exp-2888_leverage_validation.png"
    fig.savefig(fig_path, dpi=130)
    plt.close(fig)

    # ------------------------------------------------------------------
    # 5. Save summary
    # ------------------------------------------------------------------
    summary = {
        "exp": "EXP-2888",
        "n_patients": int(len(df)),
        "univariate": uni,
        "three_component_model": parts_result,
        "composite_model": comp_result,
        "archetype_stats": arch_stats.to_dict(orient="records"),
        "archetype_kruskal": kw,
        "figure": str(fig_path),
    }
    (OUT / "exp-2888_leverage_validation_summary.json").write_text(
        json.dumps(summary, indent=2))
    df.to_parquet(OUT / "exp-2888_leverage_validation.parquet")
    print(f"\nWrote {fig_path}")
    print("Summary -> exp-2888_leverage_validation_summary.json")


if __name__ == "__main__":
    main()
