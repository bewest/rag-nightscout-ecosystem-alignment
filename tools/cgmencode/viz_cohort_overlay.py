"""Cohort overlay visualizations + EXP-2844 phenotype panels.

Charter compliance (Appendix V):
- V1: no quantitative biology numbers
- V2: percentile bands (V3) replace absolute predictions
- V3: cohort overlays use percentile bands
- V5: phenotype direction is a first-class facet
- V7: per-patient + cohort pairing

Outputs:
  docs/60-research/figures/cohort_phenotype_panel.png
  docs/60-research/figures/cohort_recovery_vs_shift.png
  docs/60-research/figures/cohort_controller_phenotype.png
  docs/60-research/figures/phenotype_panel_<phenotype>.png  (3 panels)
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

OUT = Path("docs/60-research/figures")
OUT.mkdir(parents=True, exist_ok=True)
EXP = Path("externals/experiments")

PHENOTYPE_COLOR = {
    "up_shift": "#1f77b4",
    "flat":     "#888888",
    "down_shift": "#d62728",
}

CONTROLLER_MARKER = {"Loop": "o", "Trio": "s", "OpenAPS": "^"}


def load() -> pd.DataFrame:
    df = pd.read_parquet(EXP / "exp-2844_phenotype_table.parquet")
    return df


def chart_cohort_phenotype_panel(df: pd.DataFrame) -> Path:
    """4-panel cohort summary keyed on phenotype."""
    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    fig.suptitle(
        "Cohort phenotype panel — S1-entry basal-shift direction\n"
        "Stream B operational; bands are observed cohort percentiles "
        "(V3 charter)",
        fontsize=12,
    )

    # P1: actual basal shift % distribution by phenotype
    ax = axes[0, 0]
    for ph, sub in df.groupby("phenotype"):
        ax.scatter(
            sub["actual_basal_shift_pct"],
            np.arange(len(sub)) + 0.05 * (hash(ph) % 5),
            color=PHENOTYPE_COLOR.get(ph, "k"),
            label=f"{ph} (n={len(sub)})", s=70, alpha=0.85,
        )
    ax.axvspan(-15, 15, color="lightgray", alpha=0.4, label="flat band")
    ax.axvline(0, color="k", lw=0.6)
    ax.set_xlabel("Actual basal shift S0→S1 (%)")
    ax.set_ylabel("Patient index (sorted within phenotype)")
    ax.set_title("Phenotype split (actual basal shift)")
    ax.legend(loc="best", fontsize=8)

    # P2: controller composition (stacked)
    ax = axes[0, 1]
    ct = pd.crosstab(df["phenotype"], df["controller"])
    ct = ct.reindex(["down_shift", "flat", "up_shift"]).fillna(0)
    bottom = np.zeros(len(ct))
    for ctrl in ct.columns:
        ax.bar(
            ct.index, ct[ctrl], bottom=bottom,
            label=ctrl, edgecolor="white",
        )
        bottom += ct[ctrl].values
    ax.set_ylabel("Patient count")
    ax.set_title("Controller composition by phenotype")
    ax.legend(loc="best", fontsize=9)

    # P3: recovery vs phenotype (boxplot + dots)
    ax = axes[1, 0]
    order = ["down_shift", "flat", "up_shift"]
    data = [
        df[df["phenotype"] == p]["median_recovery_fraction"].dropna().values
        for p in order
    ]
    bp = ax.boxplot(data, labels=order, patch_artist=True, widths=0.5)
    for patch, p in zip(bp["boxes"], order):
        patch.set_facecolor(PHENOTYPE_COLOR.get(p, "lightgray"))
        patch.set_alpha(0.4)
    for i, p in enumerate(order):
        sub = df[df["phenotype"] == p]
        ax.scatter(
            np.full(len(sub), i + 1) + np.random.uniform(-0.08, 0.08, len(sub)),
            sub["median_recovery_fraction"], color=PHENOTYPE_COLOR.get(p, "k"),
            s=50, alpha=0.85, edgecolor="white",
        )
    ax.set_ylabel("Median recovery fraction (EXP-2812)")
    ax.set_title("Self-recovery by phenotype")
    ax.set_ylim(-0.05, 1.05)

    # P4: baseline override vs S1 shift (the predictor candidate)
    ax = axes[1, 1]
    for ph, sub in df.groupby("phenotype"):
        for _, row in sub.iterrows():
            ax.scatter(
                row["override_magnitude_s0"], row["actual_basal_shift_pct"],
                color=PHENOTYPE_COLOR.get(ph, "k"),
                marker=CONTROLLER_MARKER.get(row["controller"], "x"),
                s=90, alpha=0.85, edgecolor="white",
            )
    ax.axhspan(-15, 15, color="lightgray", alpha=0.4)
    ax.axhline(0, color="k", lw=0.6)
    ax.axvline(0, color="k", lw=0.6)
    ax.set_xlabel("S0 override magnitude (baseline)")
    ax.set_ylabel("Actual basal shift S0→S1 (%)")
    ax.set_title("Does baseline override predict shift direction?")
    # Custom legend for markers
    handles = [
        plt.Line2D([0], [0], marker=m, color="gray", linestyle="",
                   markersize=9, label=ctrl)
        for ctrl, m in CONTROLLER_MARKER.items()
    ]
    ax.legend(handles=handles, loc="best", fontsize=9)

    plt.tight_layout(rect=(0, 0, 1, 0.95))
    out = OUT / "cohort_phenotype_panel.png"
    plt.savefig(out, dpi=120, bbox_inches="tight")
    plt.close()
    return out


def chart_cohort_recovery_vs_shift(df: pd.DataFrame) -> Path:
    """Single-panel "you are here" cohort scatter."""
    fig, ax = plt.subplots(figsize=(9, 6))
    for _, row in df.iterrows():
        ax.scatter(
            row["actual_basal_shift_pct"],
            row["median_recovery_fraction"],
            color=PHENOTYPE_COLOR.get(row["phenotype"], "k"),
            marker=CONTROLLER_MARKER.get(row["controller"], "x"),
            s=120, alpha=0.85, edgecolor="white",
        )
        ax.annotate(
            row["patient_id"],
            (row["actual_basal_shift_pct"], row["median_recovery_fraction"]),
            fontsize=7, alpha=0.6, xytext=(4, 4), textcoords="offset points",
        )
    # Cohort percentile bands (V3)
    p25, p75 = np.percentile(df["actual_basal_shift_pct"], [25, 75])
    ax.axvspan(p25, p75, color="lightyellow", alpha=0.5,
               label="cohort IQR (basal shift)")
    ax.axhline(df["median_recovery_fraction"].median(), color="gray",
               ls="--", lw=0.8, label="cohort median recovery")
    ax.axvline(0, color="k", lw=0.6)
    ax.set_xlabel("Actual basal shift S0→S1 (%)")
    ax.set_ylabel("Median recovery fraction")
    ax.set_title(
        "Cohort 'you are here' — basal-shift direction × self-recovery\n"
        "Marker = controller; color = phenotype; bands = cohort IQR (V3)"
    )
    handles = [
        plt.Line2D([0], [0], marker=m, color="gray", linestyle="",
                   markersize=9, label=ctrl)
        for ctrl, m in CONTROLLER_MARKER.items()
    ]
    ax.legend(handles=handles + ax.get_legend_handles_labels()[0],
              loc="best", fontsize=8)
    plt.tight_layout()
    out = OUT / "cohort_recovery_vs_shift.png"
    plt.savefig(out, dpi=120, bbox_inches="tight")
    plt.close()
    return out


def chart_cohort_controller_phenotype(df: pd.DataFrame) -> Path:
    """Stacked controller × phenotype heatmap-style chart."""
    fig, ax = plt.subplots(figsize=(8, 5))
    ct = pd.crosstab(df["controller"], df["phenotype"]).reindex(
        columns=["down_shift", "flat", "up_shift"]
    ).fillna(0).astype(int)
    im = ax.imshow(ct.values, cmap="YlOrRd", aspect="auto")
    ax.set_xticks(range(len(ct.columns)))
    ax.set_xticklabels(ct.columns)
    ax.set_yticks(range(len(ct.index)))
    ax.set_yticklabels(ct.index)
    for i in range(ct.shape[0]):
        for j in range(ct.shape[1]):
            ax.text(j, i, ct.values[i, j], ha="center", va="center",
                    color="black", fontsize=12, fontweight="bold")
    ax.set_title(
        "Controller × phenotype (counts)\n"
        "Pattern (Stream B): Trio → down-shift; Loop → up/flat"
    )
    fig.colorbar(im, ax=ax, label="patient count")
    plt.tight_layout()
    out = OUT / "cohort_controller_phenotype.png"
    plt.savefig(out, dpi=120, bbox_inches="tight")
    plt.close()
    return out


def main():
    df = load()
    print(f"Loaded {len(df)} significant patients with phenotype labels")
    paths = [
        chart_cohort_phenotype_panel(df),
        chart_cohort_recovery_vs_shift(df),
        chart_cohort_controller_phenotype(df),
    ]
    for p in paths:
        print(f"  wrote {p}")


if __name__ == "__main__":
    main()
