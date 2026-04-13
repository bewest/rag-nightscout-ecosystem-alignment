#!/usr/bin/env python3
"""Generate Phase 1 visualizations (Figures 19-22).

fig19: Basal recommendation — scheduled vs recommended (midnight/dawn)
fig20: Two-phase ISF decomposition — demand vs apparent per patient
fig21: ISF inflation ratio distribution
fig22: Circadian ISF profiles — 4h blocks per patient
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

VIZ_DIR = Path(__file__).resolve().parent
EXP_DIR = Path("externals/experiments")


def fig19_basal_recommendations():
    """Scheduled vs recommended basal for midnight and dawn blocks."""
    data = json.loads((EXP_DIR / "exp-2650_basal_recommendation.json").read_text())

    patients = []
    sched, mid_rec, dawn_rec = [], [], []
    for pid, p in data.items():
        patients.append(pid)
        sched.append(p["scheduled_basal"])
        mid = p.get("midnight")
        dawn = p.get("dawn")
        mid_rec.append(mid["recommended_basal"] if mid else np.nan)
        dawn_rec.append(dawn["recommended_basal"] if dawn else np.nan)

    x = np.arange(len(patients))
    width = 0.25

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.bar(x - width, sched, width, label="Scheduled", color="#888", alpha=0.7)
    bars_mid = ax.bar(x, [v if not np.isnan(v) else 0 for v in mid_rec],
                      width, label="Midnight (00-04h)", color="#d63031")
    bars_dawn = ax.bar(x + width, [v if not np.isnan(v) else 0 for v in dawn_rec],
                       width, label="Dawn (04-08h)", color="#0984e3")

    # Mark missing blocks
    for i, v in enumerate(mid_rec):
        if np.isnan(v):
            ax.text(x[i], 0.02, "–", ha="center", fontsize=8, color="#d63031")
    for i, v in enumerate(dawn_rec):
        if np.isnan(v):
            ax.text(x[i] + width, 0.02, "–", ha="center", fontsize=8, color="#0984e3")

    ax.set_xlabel("Patient")
    ax.set_ylabel("Basal Rate (U/hr)")
    ax.set_title("EXP-2650: IOB-Corrected Basal Recommendations\n"
                 "Overnight drift→0 when IOB→0 (EGP-matching basal)")
    ax.set_xticks(x)
    ax.set_xticklabels(patients, rotation=45, ha="right")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(VIZ_DIR / "fig19_basal_recommendations.png", dpi=150)
    plt.close(fig)
    print("  fig19 saved")


def fig20_isf_decomposition():
    """Demand vs apparent ISF per patient."""
    data = json.loads((EXP_DIR / "exp-2651_two_phase_isf.json").read_text())

    patients, sched_isf, demand_isf, apparent_isf = [], [], [], []
    for pid, p in data.items():
        d_isf = p.get("demand_isf")
        if d_isf is not None and d_isf > 0:
            patients.append(pid)
            sched_isf.append(p["scheduled_isf"])
            demand_isf.append(d_isf)
            apparent_isf.append(p["apparent_isf"])

    x = np.arange(len(patients))
    width = 0.25

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.bar(x - width, demand_isf, width, label="Demand ISF (0-2h)", color="#e17055")
    ax.bar(x, sched_isf, width, label="Scheduled ISF", color="#888", alpha=0.7)
    ax.bar(x + width, apparent_isf, width, label="Apparent ISF (to nadir)", color="#0984e3")

    ax.set_xlabel("Patient")
    ax.set_ylabel("ISF (mg/dL per U)")
    ax.set_title("EXP-2651: Two-Phase ISF Decomposition\n"
                 "Demand (insulin-only) vs Apparent (includes EGP + AID compensation)")
    ax.set_xticks(x)
    ax.set_xticklabels(patients, rotation=45, ha="right")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(VIZ_DIR / "fig20_isf_decomposition.png", dpi=150)
    plt.close(fig)
    print("  fig20 saved")


def fig21_inflation_ratio():
    """ISF inflation ratio (apparent / demand) distribution."""
    data = json.loads((EXP_DIR / "exp-2651_two_phase_isf.json").read_text())

    patients, ratios = [], []
    for pid, p in data.items():
        r = p.get("inflation_ratio")
        if r is not None and not np.isnan(r) and r > 0:
            patients.append(pid)
            ratios.append(r)

    fig, ax = plt.subplots(figsize=(10, 5))
    colors = ["#d63031" if r > 3.0 else "#e17055" if r > 2.0 else "#0984e3"
              for r in ratios]
    ax.bar(patients, ratios, color=colors)
    ax.axhline(y=1.0, color="black", linestyle="--", alpha=0.3, label="No inflation")
    ax.axhline(y=2.0, color="orange", linestyle="--", alpha=0.5, label="2× threshold")

    ax.set_xlabel("Patient")
    ax.set_ylabel("Inflation Ratio (apparent / demand)")
    ax.set_title("EXP-2651: ISF Inflation Ratio\n"
                 "How much EGP recovery + AID compensation inflates measured ISF")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(VIZ_DIR / "fig21_isf_inflation.png", dpi=150)
    plt.close(fig)
    print("  fig21 saved")


def fig22_circadian_isf():
    """Circadian ISF profiles — 6 blocks per patient."""
    data = json.loads((EXP_DIR / "exp-2652_circadian_profiling.json").read_text())

    blocks = ["00-04", "04-08", "08-12", "12-16", "16-20", "20-24"]
    fig, axes = plt.subplots(3, 4, figsize=(16, 10), sharey=False)
    axes = axes.flatten()

    plotted = 0
    for pid, p in data.items():
        if plotted >= 12:
            break
        ax = axes[plotted]
        vals = []
        counts = []
        for b in blocks:
            bdata = p.get("blocks", {}).get(b, {})
            v = bdata.get("isf")
            n = bdata.get("n", 0)
            vals.append(v if v is not None else np.nan)
            counts.append(n)

        colors = ["#e17055" if n < 5 else "#0984e3" for n in counts]
        ax.bar(range(len(blocks)), vals, color=colors)
        sched = p.get("scheduled_isf", p.get("global_isf"))
        if sched:
            ax.axhline(y=sched, color="red", linestyle="--", alpha=0.5, linewidth=1)
        variation = p.get("isf_variation", 0)
        ax.set_title(f"{pid} ({variation:.1f}×)", fontsize=9)
        ax.set_xticks(range(len(blocks)))
        ax.set_xticklabels(blocks, fontsize=7, rotation=45)
        if plotted % 4 == 0:
            ax.set_ylabel("ISF (mg/dL/U)")
        plotted += 1

    for i in range(plotted, len(axes)):
        axes[i].set_visible(False)

    fig.suptitle("EXP-2652: Circadian ISF Profiles by 4h Blocks\n"
                 "Orange = <5 events (low confidence), red line = scheduled ISF",
                 fontsize=11)
    fig.tight_layout()
    fig.savefig(VIZ_DIR / "fig22_circadian_isf.png", dpi=150)
    plt.close(fig)
    print("  fig22 saved")


if __name__ == "__main__":
    print("Generating Phase 1 visualizations...")
    fig19_basal_recommendations()
    fig20_isf_decomposition()
    fig21_inflation_ratio()
    fig22_circadian_isf()
    print("Done!")
