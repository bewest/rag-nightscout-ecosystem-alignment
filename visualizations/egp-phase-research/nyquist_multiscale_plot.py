#!/usr/bin/env python3
"""Generate EXP-2653 Nyquist multi-scale visualization (Figure 23).

fig23: Demand vs Supply R² per patient, showing the balance point.
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

VIZ_DIR = Path(__file__).resolve().parent
EXP_DIR = Path("externals/experiments")


def fig23_demand_supply_balance():
    """Scatter of demand R² vs supply R², with combined R² as size."""
    data = json.loads((EXP_DIR / "exp-2653_nyquist_multiscale.json").read_text())

    patients, demand_r2, supply_r2, combined_r2, n_nights = [], [], [], [], []
    for pid, p in data.items():
        if pid.startswith("_"):
            continue
        dr = p.get("demand_r2", 0)
        sr = p.get("supply_r2")
        cr = p.get("combined_r2")
        if sr is None or cr is None:
            continue
        patients.append(pid)
        demand_r2.append(dr)
        supply_r2.append(sr)
        combined_r2.append(cr)
        n_nights.append(p.get("n_nights", 10))

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    # Panel A: Demand vs Supply R²
    ax = axes[0]
    sizes = [max(20, n * 3) for n in n_nights]
    colors = ["#d63031" if d > s else "#0984e3" for d, s in zip(demand_r2, supply_r2)]
    ax.scatter(demand_r2, supply_r2, s=sizes, c=colors, alpha=0.7, edgecolors="black")
    for i, pid in enumerate(patients):
        ax.annotate(pid, (demand_r2[i], supply_r2[i]),
                    fontsize=7, ha="left", va="bottom", xytext=(4, 4),
                    textcoords="offset points")
    lim = max(max(demand_r2), max(supply_r2)) * 1.1
    ax.plot([0, lim], [0, lim], "k--", alpha=0.3, label="Equal balance")
    ax.set_xlabel("Demand R² (IOB + insulin history)")
    ax.set_ylabel("Supply R² (carbs + metabolic state)")
    ax.set_title("A: Supply vs Demand Predictive Power\n"
                 "Red = demand-dominated, Blue = supply-dominated")
    ax.legend()
    ax.grid(alpha=0.3)

    # Panel B: Stacked bar of R² components
    ax = axes[1]
    x = np.arange(len(patients))
    width = 0.6

    # Split combined into demand-alone + supply-increment
    demand_only = [min(d, c) for d, c in zip(demand_r2, combined_r2)]
    supply_incr = [max(0, c - d) for d, c in zip(demand_r2, combined_r2)]
    unexplained = [max(0, 1 - c) for c in combined_r2]

    ax.bar(x, demand_only, width, label="Demand (insulin)", color="#d63031", alpha=0.7)
    ax.bar(x, supply_incr, width, bottom=demand_only,
           label="Supply increment (metabolic)", color="#0984e3", alpha=0.7)
    ax.bar(x, unexplained, width,
           bottom=[d + s for d, s in zip(demand_only, supply_incr)],
           label="Unexplained", color="#dfe6e9", alpha=0.5)

    ax.set_xlabel("Patient")
    ax.set_ylabel("Variance Explained")
    ax.set_title("B: Overnight Drift Variance Decomposition\n"
                 "8h window, 12h insulin + 48h metabolic lookback")
    ax.set_xticks(x)
    ax.set_xticklabels(patients, rotation=45, ha="right", fontsize=8)
    ax.set_ylim(0, 1.05)
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.3)

    fig.suptitle("EXP-2653: Nyquist-Aware Multi-Scale Analysis\n"
                 "Mean combined R² = 0.133 — 87% of drift is unmeasured 'metabolic weather'",
                 fontsize=11, y=1.02)
    fig.tight_layout()
    fig.savefig(VIZ_DIR / "fig23_nyquist_multiscale.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("  fig23 saved")


if __name__ == "__main__":
    print("Generating EXP-2653 visualizations...")
    fig23_demand_supply_balance()
    print("Done!")
