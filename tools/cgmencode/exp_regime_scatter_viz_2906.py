"""EXP-2906 — regime scatter visualization.

Renders a 2-D scatter of cf_severe (x) vs aid_protection_severe (y)
with regime polygons (EXP-2902) and lineage markers, one annotation
per patient. Saves PNG to docs/visualizations/.
"""
from __future__ import annotations
import json
from pathlib import Path

import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

REPO = Path(__file__).resolve().parent.parent.parent
SRC = REPO / "externals" / "experiments" / "exp-2891_simpson_dose_response.parquet"
OUT_DIR = REPO / "docs" / "visualizations"
OUT_DIR.mkdir(parents=True, exist_ok=True)
PNG = OUT_DIR / "exp-2906-regime-scatter.png"
SUMMARY = REPO / "externals" / "experiments" / "exp-2906_summary.json"

# Regime cutoffs (must match EXP-2902 classify logic)
CF_HIGH = 0.95
PROT_HIGH = 0.65
PROT_LOW = 0.35


def regime(cf: float, p: float) -> str:
    if cf >= CF_HIGH and p < PROT_HIGH:
        return "load_saturation"
    if p < PROT_LOW:
        return "mechanism_gap"
    if p >= PROT_HIGH and cf < CF_HIGH:
        return "defended"
    if p >= PROT_HIGH and cf >= CF_HIGH:
        return "over_performer_at_load"
    return "moderate"


REGIME_COLOR = {
    "load_saturation": "#fde68a",
    "moderate": "#bfdbfe",
    "over_performer_at_load": "#bbf7d0",
    "defended": "#e5e7eb",
    "mechanism_gap": "#fecaca",
}

LINEAGE_MARKER = {
    "Loop (iOS)": ("o", "#1f77b4"),
    "oref1 (modern)": ("s", "#2ca02c"),
    "oref0 (legacy)": ("^", "#d62728"),
}


def main():
    df = pd.read_parquet(SRC)
    df = df[df["lineage"] != "unknown"].copy()
    df = df.dropna(subset=["cf_severe", "aid_protection_severe", "lineage"]).copy()
    df["regime"] = [regime(c, p) for c, p in zip(df["cf_severe"], df["aid_protection_severe"])]

    fig, ax = plt.subplots(figsize=(11, 7.5))

    # Regime polygons (background)
    polygons = [
        ("load_saturation", CF_HIGH, -0.05, 1.05 - CF_HIGH, PROT_HIGH + 0.05),
        ("over_performer_at_load", CF_HIGH, PROT_HIGH, 1.05 - CF_HIGH, 1.05 - PROT_HIGH),
        ("mechanism_gap", -0.05, -0.05, CF_HIGH + 0.05, PROT_LOW + 0.05),
        ("moderate", -0.05, PROT_LOW, CF_HIGH + 0.05, PROT_HIGH - PROT_LOW),
        ("defended", -0.05, PROT_HIGH, CF_HIGH + 0.05, 1.05 - PROT_HIGH),
    ]
    for name, x, y, w, h in polygons:
        rect = mpatches.Rectangle(
            (x, y), w, h, facecolor=REGIME_COLOR[name], edgecolor="none", alpha=0.55, zorder=0
        )
        ax.add_patch(rect)
        ax.text(
            x + w / 2,
            y + h - 0.025,
            name.replace("_", " "),
            ha="center",
            va="top",
            fontsize=9,
            color="#333",
            fontweight="bold",
            alpha=0.85,
        )

    # Cutoff lines
    ax.axvline(CF_HIGH, color="#888", lw=0.8, ls="--", zorder=1)
    ax.axhline(PROT_HIGH, color="#888", lw=0.8, ls="--", zorder=1)
    ax.axhline(PROT_LOW, color="#888", lw=0.8, ls="--", zorder=1)

    # Patient markers
    for lineage, (mk, col) in LINEAGE_MARKER.items():
        sub = df[df["lineage"] == lineage]
        ax.scatter(
            sub["cf_severe"],
            sub["aid_protection_severe"],
            marker=mk,
            color=col,
            edgecolor="black",
            linewidth=0.6,
            s=110,
            label=f"{lineage} (n={len(sub)})",
            zorder=3,
        )
        for _, row in sub.iterrows():
            ax.annotate(
                str(row["patient_id"])[:14],
                (row["cf_severe"], row["aid_protection_severe"]),
                fontsize=7,
                xytext=(4, 4),
                textcoords="offset points",
                color="#222",
                zorder=4,
            )

    ax.set_xlim(-0.05, 1.05)
    ax.set_ylim(-0.05, 1.05)
    ax.set_xlabel("Counterfactual severe rate (cf_severe) — load intensity")
    ax.set_ylabel("AID protection (1 - obs_severe / cf_severe)")
    ax.set_title("EXP-2906 — Cohort regime scatter (n={}; lineage × regime)".format(len(df)))
    ax.legend(loc="lower left", framealpha=0.95)
    ax.grid(True, alpha=0.25, zorder=2)

    plt.tight_layout()
    fig.savefig(PNG, dpi=140)
    plt.close(fig)

    counts = df["regime"].value_counts().to_dict()
    by_lineage = {
        l: df[df["lineage"] == l]["regime"].value_counts().to_dict() for l in df["lineage"].unique()
    }
    SUMMARY.write_text(
        json.dumps(
            {"png": str(PNG.relative_to(REPO)), "n": int(len(df)), "regime_counts": counts, "by_lineage": by_lineage},
            indent=2,
        )
    )
    print(f"[exp-2906] wrote {PNG}")
    print(f"  regime counts: {counts}")
    print(f"  by lineage: {json.dumps(by_lineage, indent=2)}")


if __name__ == "__main__":
    main()
