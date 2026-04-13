#!/usr/bin/env python3
"""Generate Phase 3 visualizations (Figures 27-29).

fig27: Sticky hyper episodes — wall detection rates
fig28: Patience mode — delayed hypo reduction
fig29: Extended prediction — 3-phase vs linear RMSE at each horizon
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

VIZ_DIR = Path(__file__).resolve().parent
EXP_DIR = Path("externals/experiments")


def fig27_sticky_hyper_wall():
    """Wall detection and episode statistics."""
    data = json.loads((EXP_DIR / "exp-2660_sticky_hyper.json").read_text())

    patients, n_eps, wall_pcts, hypo_pcts = [], [], [], []
    for pid, p in data.items():
        patients.append(pid)
        n_eps.append(p["n_episodes"])
        wall_pcts.append(p["wall_detected_pct"])
        hypo_pcts.append(p["delayed_hypo_pct"])

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Panel A: Wall detection vs delayed hypo rate
    ax = axes[0]
    sizes = [max(30, n * 2) for n in n_eps]
    ax.scatter(wall_pcts, hypo_pcts, s=sizes, c="#e17055", alpha=0.7, edgecolors="black")
    for i, pid in enumerate(patients):
        label = pid.replace("odc-", "o-")
        ax.annotate(label, (wall_pcts[i], hypo_pcts[i]),
                    fontsize=7, ha="left", va="bottom", xytext=(3, 3),
                    textcoords="offset points")

    ax.set_xlabel("Wall Detection Rate (%)")
    ax.set_ylabel("Delayed Hypo Rate (%)")
    ax.set_title("A: Wall Detection vs Delayed Hypo Rate\n"
                 "Higher wall detection → more insulin wasted → more delayed hypos")
    ax.grid(alpha=0.3)

    # Panel B: Episode counts with wall breakdown
    ax = axes[1]
    x = np.arange(len(patients))
    wall_counts = [int(p["wall_count"]) for p in data.values()]
    non_wall = [n - w for n, w in zip(n_eps, wall_counts)]
    ax.bar(x, non_wall, label="Non-wall", color="#74b9ff", alpha=0.7)
    ax.bar(x, wall_counts, bottom=non_wall, label="Wall detected", color="#d63031", alpha=0.7)
    ax.set_xticks(x)
    ax.set_xticklabels(patients, rotation=45, ha="right", fontsize=7)
    ax.set_ylabel("Number of Episodes")
    ax.set_title("B: Sticky Hyper Episodes\n"
                 "Red = controller pushing against SC ceiling")
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.3)

    fig.suptitle("EXP-2660: Sticky Hyper Detection & Suppression Wall", fontsize=11, y=1.02)
    fig.tight_layout()
    fig.savefig(VIZ_DIR / "fig27_sticky_hyper.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("  fig27 saved")


def fig28_patience_mode():
    """Patience mode simulation — hypo reduction potential."""
    data = json.loads((EXP_DIR / "exp-2660_sticky_hyper.json").read_text())

    patients, orig_hypo, patience_hypo, excess_insulin = [], [], [], []
    for pid, p in data.items():
        sim = p.get("patience_simulation", {})
        if sim.get("wall_count", 0) == 0:
            continue
        patients.append(pid)
        orig_hypo.append(sim.get("wall_hypo_rate", 0) * 100)
        patience_hypo.append(sim.get("patience_hypo_rate", 0) * 100)
        excess_insulin.append(sim.get("mean_excess_insulin", 0))

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Panel A: Hypo rate reduction
    ax = axes[0]
    x = np.arange(len(patients))
    width = 0.35
    ax.bar(x - width/2, orig_hypo, width, label="Current (aggressive)", color="#d63031", alpha=0.7)
    ax.bar(x + width/2, patience_hypo, width, label="Patience mode", color="#27ae60", alpha=0.7)
    ax.set_xticks(x)
    ax.set_xticklabels(patients, rotation=45, ha="right", fontsize=7)
    ax.set_ylabel("Delayed Hypo Rate (%)")
    ax.set_title("A: Delayed Hypo Rate — Current vs Patience Mode\n"
                 "Patience mode (cap IOB at 1.5×) eliminates delayed hypos")
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.3)

    # Panel B: Excess insulin wasted
    ax = axes[1]
    colors = ["#d63031" if e > 15 else "#e17055" if e > 10 else "#fdcb6e"
              for e in excess_insulin]
    ax.bar(range(len(patients)), excess_insulin, color=colors)
    ax.set_xticks(range(len(patients)))
    ax.set_xticklabels(patients, rotation=45, ha="right", fontsize=7)
    ax.set_ylabel("Excess Insulin (U·h)")
    ax.set_title("B: Mean Excess Insulin per Wall Episode\n"
                 "Insulin wasted pushing against the SC suppression ceiling")
    ax.grid(axis="y", alpha=0.3)

    fig.suptitle("EXP-2660: Patience Mode Simulation", fontsize=11, y=1.02)
    fig.tight_layout()
    fig.savefig(VIZ_DIR / "fig28_patience_mode.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("  fig28 saved")


def fig29_extended_prediction():
    """3-phase vs linear prediction RMSE at each horizon."""
    data = json.loads((EXP_DIR / "exp-2658_extended_horizon.json").read_text())

    horizons = ["2h", "4h", "6h", "8h"]
    h_vals = [2, 4, 6, 8]

    fig, ax = plt.subplots(figsize=(10, 6))
    cmap = plt.cm.tab10

    for idx, (pid, p) in enumerate(data.items()):
        rmse = p.get("rmse", {})
        linear_vals, phase3_vals = [], []
        avail_h = []
        for h in horizons:
            if h in rmse:
                linear_vals.append(rmse[h]["linear"])
                phase3_vals.append(rmse[h]["3phase"])
                avail_h.append(h_vals[horizons.index(h)])

        if len(avail_h) >= 2:
            label = pid.replace("odc-", "o-")
            ax.plot(avail_h, linear_vals, "o-", color=cmap(idx), alpha=0.5, markersize=4)
            ax.plot(avail_h, phase3_vals, "s--", color=cmap(idx), alpha=0.5, markersize=4,
                    label=label)

    # Add reference lines
    ax.axhline(y=100, color="gray", linestyle=":", alpha=0.3, label="100 mg/dL RMSE")

    ax.set_xlabel("Prediction Horizon (hours)")
    ax.set_ylabel("RMSE (mg/dL)")
    ax.set_title("EXP-2658: 3-Phase (dashed) vs Linear (solid) Prediction\n"
                 "3-Phase is WORSE: additive EGP doesn't work in coupled AID systems\n"
                 "The AID controller compensates for EGP recovery in real-time")
    ax.legend(fontsize=7, ncol=3, loc="upper left")
    ax.set_xticks(h_vals)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(VIZ_DIR / "fig29_extended_prediction.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("  fig29 saved")


if __name__ == "__main__":
    print("Generating Phase 3 visualizations...")
    fig27_sticky_hyper_wall()
    fig28_patience_mode()
    fig29_extended_prediction()
    print("Done!")
