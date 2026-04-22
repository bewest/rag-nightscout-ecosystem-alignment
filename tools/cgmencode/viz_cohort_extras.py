"""Recovery-by-controller and site-age cohort heatmap visualizations.

Two paired charts:
  - viz_recovery_by_controller: stratified recovery distributions
  - viz_site_age_cohort: per-patient×age heatmap of basal demand

Charter Appendix V (V1, V3, V5, V7).
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

EXP = Path("externals/experiments")
FIG = Path("docs/60-research/figures")

CTRL_COLOR = {"Loop": "#1f77b4", "Trio": "#d62728", "OpenAPS": "#2ca02c"}


def chart_recovery_by_controller():
    """Stratified recovery distribution from EXP-2812 transitions."""
    rec = pd.read_parquet(EXP / "exp-2812_pre_post_transitions.parquet")
    print(f"transitions: {len(rec)}; cols: {list(rec.columns)[:8]}")

    # Identify the recovery column
    rec_col = next(
        (c for c in rec.columns
         if "recovery" in c.lower() and "fraction" in c.lower()),
        None,
    )
    if rec_col is None:
        rec_col = "recovery_fraction"
    if rec_col not in rec.columns:
        # fall back to triage flags table aggregates
        rec = pd.read_parquet(EXP / "exp-2812_triage_flags.parquet")
        rec_col = "median_recovery_fraction"

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    fig.suptitle(
        "Recovery from S0→S1 transitions, stratified by controller "
        "(EXP-2812)\nStream B; cohort percentile bands (V3); marker overlay",
        fontsize=11,
    )

    # P1: violin + scatter
    ax = axes[0]
    controllers = ["Loop", "OpenAPS", "Trio"]
    data = []
    for ctrl in controllers:
        sub = rec[rec["controller"] == ctrl][rec_col].dropna()
        data.append(sub.values if len(sub) > 0 else np.array([0.0]))

    parts = ax.violinplot(data, positions=range(len(controllers)),
                          widths=0.7, showmedians=True)
    for pc, ctrl in zip(parts["bodies"], controllers):
        pc.set_facecolor(CTRL_COLOR.get(ctrl, "k"))
        pc.set_alpha(0.45)
    for i, vals in enumerate(data):
        ax.scatter(np.full(len(vals), i) + np.random.uniform(-0.15, 0.15, len(vals)),
                   vals, s=40, alpha=0.7,
                   color=CTRL_COLOR.get(controllers[i], "k"),
                   edgecolor="white")
    ax.set_xticks(range(len(controllers)))
    ax.set_xticklabels([f"{c}\n(n={len(d)})" for c, d in zip(controllers, data)])
    ax.set_ylabel("Recovery fraction")
    ax.set_title("Distribution by controller")
    ax.axhline(0.4, color="orange", lw=0.8, ls="--", label="triage threshold")
    ax.legend(loc="best", fontsize=8)

    # P2: ECDF
    ax = axes[1]
    for ctrl in controllers:
        sub = sorted(rec[rec["controller"] == ctrl][rec_col].dropna().values)
        if len(sub) == 0:
            continue
        x = np.array(sub)
        y = np.arange(1, len(x) + 1) / len(x)
        ax.step(x, y, where="post",
                color=CTRL_COLOR.get(ctrl, "k"), linewidth=2,
                label=f"{ctrl} (n={len(x)})")
    ax.axvline(0.4, color="orange", lw=0.8, ls="--")
    ax.set_xlabel("Recovery fraction")
    ax.set_ylabel("Cumulative share of patients/transitions")
    ax.set_title("ECDF — controllers diverge at low recovery")
    ax.legend(loc="best", fontsize=8)
    ax.grid(alpha=0.3)

    plt.tight_layout(rect=(0, 0, 1, 0.94))
    out = FIG / "cohort_recovery_by_controller.png"
    plt.savefig(out, dpi=120, bbox_inches="tight")
    plt.close()
    print(f"Wrote {out}")


def chart_site_age_cohort():
    """Cannula-age cohort heatmap (rows=patients, cols=age hours)."""
    g = pd.read_parquet("externals/ns-parquet/training/grid.parquet")
    g = g.dropna(subset=["cage_hours"])
    g = g[(g["cage_hours"] >= 0) & (g["cage_hours"] <= 72)]
    g["age_bin"] = (g["cage_hours"] // 4 * 4).astype(int)  # 4-hour bins

    sa = pd.read_parquet(EXP / "exp-2810_state_assignments.parquet")
    ctrl_map = sa.drop_duplicates("patient_id").set_index("patient_id")["controller"]
    g["controller"] = g["patient_id"].map(ctrl_map)
    g = g.dropna(subset=["controller"])

    # Two metrics: mean glucose and basal demand ratio (actual/scheduled)
    g["basal_demand"] = g["actual_basal_rate"] / np.maximum(g["scheduled_basal_rate"], 0.01)

    grid_glucose = g.groupby(["patient_id", "age_bin"])["glucose"].mean().reset_index()
    pivot_glu = grid_glucose.pivot(index="patient_id", columns="age_bin", values="glucose")

    grid_demand = g.groupby(["patient_id", "age_bin"])["basal_demand"].mean().reset_index()
    pivot_dem = grid_demand.pivot(index="patient_id", columns="age_bin", values="basal_demand")

    # Sort patients by controller, then by overall basal demand trend
    pat_ctrl = g.drop_duplicates("patient_id").set_index("patient_id")["controller"]
    pat_order = pivot_glu.index.tolist()
    pat_order = sorted(pat_order, key=lambda p: (pat_ctrl[p], -pivot_glu.loc[p].mean()))
    pivot_glu = pivot_glu.reindex(pat_order)
    pivot_dem = pivot_dem.reindex(pat_order)

    fig, axes = plt.subplots(1, 2, figsize=(15, max(6, 0.32 * len(pat_order))))
    fig.suptitle(
        "Site-age cohort heatmap (cannula age 0-72h, 4h bins)\n"
        "Stream B; rows = patients sorted by controller; "
        "left: mean BG, right: actual/scheduled basal demand ratio",
        fontsize=11,
    )

    # Mean BG heatmap
    ax = axes[0]
    im0 = ax.imshow(pivot_glu.values, cmap="RdYlGn_r", aspect="auto",
                    vmin=100, vmax=220)
    ax.set_xticks(range(len(pivot_glu.columns)))
    ax.set_xticklabels([f"{c}h" for c in pivot_glu.columns], fontsize=7)
    ax.set_yticks(range(len(pivot_glu.index)))
    yticklabels = [f"{p} [{pat_ctrl[p][0]}]" for p in pivot_glu.index]
    ax.set_yticklabels(yticklabels, fontsize=7)
    ax.set_title("Mean glucose by site age")
    fig.colorbar(im0, ax=ax, label="mg/dL")

    # Basal demand ratio heatmap
    ax = axes[1]
    im1 = ax.imshow(pivot_dem.values, cmap="RdBu_r", aspect="auto",
                    vmin=0.5, vmax=1.5)
    ax.set_xticks(range(len(pivot_dem.columns)))
    ax.set_xticklabels([f"{c}h" for c in pivot_dem.columns], fontsize=7)
    ax.set_yticks(range(len(pivot_dem.index)))
    ax.set_yticklabels(yticklabels, fontsize=7)
    ax.set_title("Basal demand ratio (actual / scheduled)")
    fig.colorbar(im1, ax=ax, label="ratio (1.0 = profile)")

    plt.tight_layout(rect=(0, 0, 1, 0.95))
    out = FIG / "cohort_site_age_heatmap.png"
    plt.savefig(out, dpi=120, bbox_inches="tight")
    plt.close()
    print(f"Wrote {out}")


def main():
    chart_recovery_by_controller()
    chart_site_age_cohort()


if __name__ == "__main__":
    main()
