#!/usr/bin/env python3
"""Generate capstone visualization (Figure 30).

fig30: Patience mode full-history simulation — safety/efficacy summary
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

VIZ_DIR = Path(__file__).resolve().parent
EXP_DIR = Path("externals/experiments")


def fig30_patience_mode_summary():
    """Full-history patience mode simulation results."""
    data = json.loads((EXP_DIR / "exp-2662_patience_mode.json").read_text())

    patients, hypo_delta, hyper_delta, tir_delta, smb_pct = [], [], [], [], []
    for pid, p in data.items():
        patients.append(pid)
        hypo_delta.append(p["hypo_delta_pp"])
        hyper_delta.append(p["hyper_delta_pp"])
        tir_delta.append(p["tir_delta_pp"])
        smb_pct.append(p["smb_prevented_pct"])

    fig, axes = plt.subplots(1, 3, figsize=(16, 5))

    # Panel A: Hypo vs Hyper tradeoff
    ax = axes[0]
    colors = ["#27ae60" if h < 0 and hp < 3 else "#e17055" if hp >= 3 else "#74b9ff"
              for h, hp in zip(hypo_delta, hyper_delta)]
    sizes = [max(30, s * 2) for s in smb_pct]
    ax.scatter(hyper_delta, hypo_delta, s=sizes, c=colors, alpha=0.7, edgecolors="black")
    for i, pid in enumerate(patients):
        label = pid.replace("odc-", "o-")
        ax.annotate(label, (hyper_delta[i], hypo_delta[i]),
                    fontsize=6, ha="left", va="bottom", xytext=(3, 3),
                    textcoords="offset points")
    ax.axhline(y=0, color="black", linestyle="-", alpha=0.3)
    ax.axvline(x=0, color="black", linestyle="-", alpha=0.3)
    ax.set_xlabel("ΔHyper (pp)")
    ax.set_ylabel("ΔHypo (pp)")
    ax.set_title("A: Safety Tradeoff\n"
                 "Below zero = fewer hypos; right = more hypers\n"
                 "Circle size = % SMBs saved")
    ax.grid(alpha=0.3)

    # Panel B: TIR change
    ax = axes[1]
    bar_colors = ["#27ae60" if t >= 0 else "#e17055" for t in tir_delta]
    ax.bar(range(len(patients)), tir_delta, color=bar_colors)
    ax.axhline(y=0, color="black", linestyle="-", alpha=0.3)
    ax.set_xticks(range(len(patients)))
    ax.set_xticklabels(patients, rotation=45, ha="right", fontsize=7)
    ax.set_ylabel("ΔTIR (pp)")
    ax.set_title("B: Net TIR Impact\n"
                 "Roughly neutral: -1.1 to +0.2pp")
    ax.grid(axis="y", alpha=0.3)

    # Panel C: Insulin saved
    ax = axes[2]
    bar_colors = ["#0984e3" if s > 0 else "#dfe6e9" for s in smb_pct]
    ax.bar(range(len(patients)), smb_pct, color=bar_colors)
    ax.set_xticks(range(len(patients)))
    ax.set_xticklabels(patients, rotation=45, ha="right", fontsize=7)
    ax.set_ylabel("SMBs Prevented (%)")
    ax.set_title("C: Insulin Saved\n"
                 "34-82% of SMBs are wall-pushing waste")
    ax.grid(axis="y", alpha=0.3)

    fig.suptitle("EXP-2662: Patience Mode — Full-History Simulation\n"
                 "Safe (max +2.1pp hyper), reduces hypos 0.1-2.0pp, saves 34-82% SMBs",
                 fontsize=11, y=1.05)
    fig.tight_layout()
    fig.savefig(VIZ_DIR / "fig30_patience_mode.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("  fig30 saved")


if __name__ == "__main__":
    print("Generating capstone visualization...")
    fig30_patience_mode_summary()
    print("Done!")
