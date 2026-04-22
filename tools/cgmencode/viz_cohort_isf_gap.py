"""Cohort ISF-gap chart: distribution of correction-ISF gap (EXP-2847)
stratified by phenotype and controller. Charter V8 — every research
line gets a paired chart."""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

EXP = Path("externals/experiments")
FIG = Path("docs/60-research/figures")


def main() -> None:
    ev = pd.read_parquet(EXP / "exp-2847_correction_events.parquet")
    pheno = pd.read_parquet(EXP / "exp-2844_phenotype_table.parquet")

    # Per-event gap %
    ev = ev.dropna(subset=["obs_isf", "sched_isf"])
    ev = ev[(ev["sched_isf"] > 0) & np.isfinite(ev["obs_isf"])]
    ev["gap_pct"] = 100 * (ev["obs_isf"] - ev["sched_isf"]) / ev["sched_isf"]
    ev["gap_pct"] = ev["gap_pct"].clip(-150, 300)

    # Per-patient median gap
    per = (
        ev.groupby("patient_id")
        .agg(n=("gap_pct", "size"),
             gap_median=("gap_pct", "median"))
        .reset_index()
    )
    per = per[per["n"] >= 3]
    per = per.merge(
        pheno[["patient_id", "controller", "phenotype",
               "median_recovery_fraction"]],
        on="patient_id", how="left",
    )
    per["flag_b"] = (
        (per["phenotype"] == "flat")
        & (per["median_recovery_fraction"].fillna(1.0) < 0.4)
    )

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    fig.suptitle(
        "EXP-2847 cohort overlay — correction-ISF gap by phenotype + controller\n"
        "Charter V3 percentile bands; V4 'you are here' for patient b; "
        "V8 paired chart for the audition line",
        fontsize=11,
    )

    # Left: per-patient median gap by phenotype
    ax = axes[0]
    order = ["down_shift", "flat", "up_shift"]
    color_map = {"down_shift": "#1f77b4", "flat": "#888888",
                 "up_shift": "#d62728"}
    for i, ph in enumerate(order):
        sub = per[per["phenotype"] == ph]
        if sub.empty:
            continue
        x = np.full(len(sub), i) + np.random.uniform(-0.12, 0.12, len(sub))
        sizes = np.where(sub["flag_b"], 280, 80)
        edge = np.where(sub["flag_b"], "black", "white")
        ax.scatter(x, sub["gap_median"], s=sizes, c=color_map[ph],
                   alpha=0.75, edgecolor=edge, linewidth=1.2)
        # 25-75 band
        if len(sub) >= 3:
            q25, q75 = np.percentile(sub["gap_median"], [25, 75])
            ax.fill_between([i - 0.3, i + 0.3], q25, q75,
                            color=color_map[ph], alpha=0.12)
    ax.axhline(0, color="k", lw=0.6)
    ax.set_xticks(range(len(order)))
    ax.set_xticklabels(order)
    ax.set_ylabel("Median ISF gap (%): observed − scheduled")
    ax.set_title("Per-phenotype distribution; black-edge = patient b (only triple-flag)")

    # Right: same, by controller
    ax = axes[1]
    ctrls = sorted(per["controller"].dropna().unique())
    cmap = {"Loop": "#1f77b4", "Trio": "#2ca02c",
            "OpenAPS": "#ff7f0e", "AAPS": "#9467bd"}
    for i, c in enumerate(ctrls):
        sub = per[per["controller"] == c]
        if sub.empty:
            continue
        x = np.full(len(sub), i) + np.random.uniform(-0.12, 0.12, len(sub))
        sizes = np.where(sub["flag_b"], 280, 80)
        edge = np.where(sub["flag_b"], "black", "white")
        ax.scatter(x, sub["gap_median"], s=sizes,
                   c=cmap.get(c, "#777777"),
                   alpha=0.75, edgecolor=edge, linewidth=1.2)
        if len(sub) >= 3:
            q25, q75 = np.percentile(sub["gap_median"], [25, 75])
            ax.fill_between([i - 0.3, i + 0.3], q25, q75,
                            color=cmap.get(c, "#777777"), alpha=0.12)
    ax.axhline(0, color="k", lw=0.6)
    ax.set_xticks(range(len(ctrls)))
    ax.set_xticklabels(ctrls)
    ax.set_ylabel("Median ISF gap (%): observed − scheduled")
    ax.set_title("Per-controller distribution; cohort centers near +30 (over-correction)")

    plt.tight_layout(rect=(0, 0, 1, 0.93))
    out = FIG / "exp-2847_cohort_isf_gap.png"
    plt.savefig(out, dpi=120, bbox_inches="tight")
    plt.close()
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
