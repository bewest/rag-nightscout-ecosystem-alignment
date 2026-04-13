#!/usr/bin/env python3
"""Generate Phase 2 visualizations (Figures 24-27).

fig24: CR adequacy — 5h residuals per patient
fig25: SC suppression ceiling — actual vs linear predicted drop rate
fig26: Per-patient suppression ceiling distribution
fig27: Dual-ISF safety/efficacy tradeoff
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

VIZ_DIR = Path(__file__).resolve().parent
EXP_DIR = Path("externals/experiments")


def fig24_cr_adequacy():
    """5h post-meal residuals showing CR adequacy."""
    data = json.loads((EXP_DIR / "exp-2654_cr_adequacy.json").read_text())

    patients, residuals, pct_adequate, cr_change = [], [], [], []
    for pid, p in data.items():
        patients.append(pid)
        residuals.append(p["mean_residual_5h"])
        pct_adequate.append(p["pct_adequate"] * 100)
        cr_change.append(p.get("cr_change_pct", 0))

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Panel A: Residuals
    ax = axes[0]
    colors = ["#d63031" if r > 20 else "#27ae60" if abs(r) <= 20 else "#0984e3"
              for r in residuals]
    ax.bar(range(len(patients)), residuals, color=colors)
    ax.axhline(y=0, color="black", linestyle="-", alpha=0.3)
    ax.axhline(y=20, color="orange", linestyle="--", alpha=0.5, label="+20 threshold")
    ax.axhline(y=-20, color="orange", linestyle="--", alpha=0.5, label="-20 threshold")
    ax.set_xticks(range(len(patients)))
    ax.set_xticklabels(patients, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("Mean 5h Residual (mg/dL)")
    ax.set_title("A: Post-Meal Glucose Residual at 5h\n"
                 "Red = under-dosed (glucose high), Blue = over-dosed")
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.3)

    # Panel B: CR change recommendation
    ax = axes[1]
    colors = ["#d63031" if c < -20 else "#e17055" if c < 0 else "#27ae60"
              for c in cr_change]
    ax.bar(range(len(patients)), cr_change, color=colors)
    ax.axhline(y=0, color="black", linestyle="-", alpha=0.3)
    ax.set_xticks(range(len(patients)))
    ax.set_xticklabels(patients, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("CR Change (%)")
    ax.set_title("B: Recommended CR Adjustment\n"
                 "Negative = decrease CR (more insulin per carb)")
    ax.grid(axis="y", alpha=0.3)

    fig.suptitle("EXP-2654: Carb Ratio Adequacy Analysis", fontsize=11, y=1.02)
    fig.tight_layout()
    fig.savefig(VIZ_DIR / "fig24_cr_adequacy.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("  fig24 saved")


def fig25_sc_ceiling():
    """Actual vs linear predicted glucose drop rate at high IOB."""
    data = json.loads((EXP_DIR / "exp-2656_sc_ceiling.json").read_text())

    patients = []
    actual, predicted, fitted_ceiling = [], [], []
    for pid, p in data.items():
        patients.append(pid)
        actual.append(p["mean_actual_rate"])
        predicted.append(p["mean_linear_predicted"])
        fitted_ceiling.append(p["fitted_ceiling"] * 100)

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Panel A: Actual vs predicted
    ax = axes[0]
    x = np.arange(len(patients))
    width = 0.35
    ax.bar(x - width/2, predicted, width, label="Linear prediction", color="#d63031", alpha=0.7)
    ax.bar(x + width/2, actual, width, label="Actual rate", color="#0984e3", alpha=0.7)
    ax.axhline(y=0, color="black", linestyle="-", alpha=0.3)
    ax.set_xticks(x)
    ax.set_xticklabels(patients, rotation=45, ha="right", fontsize=7)
    ax.set_ylabel("Glucose Rate (mg/dL/hr)")
    ax.set_title("A: Linear Model vs Reality at High IOB\n"
                 "Linear predicts -30 to -93; actual is -25 to +15")
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.3)

    # Panel B: Fitted suppression ceiling
    ax = axes[1]
    colors = ["#d63031" if c < 35 else "#e17055" if c < 50 else "#27ae60"
              for c in fitted_ceiling]
    ax.bar(range(len(patients)), fitted_ceiling, color=colors)
    ax.axhline(y=65, color="green", linestyle="--", alpha=0.5, label="cgmsim-lib 65%")
    ax.axhline(y=30, color="red", linestyle="--", alpha=0.5, label="Population floor 30%")
    ax.set_xticks(range(len(patients)))
    ax.set_xticklabels(patients, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("Fitted Suppression Ceiling (%)")
    ax.set_title("B: Per-Patient SC Suppression Ceiling\n"
                 "Most patients: 30% (far below cgmsim-lib's 65%)")
    ax.set_ylim(0, 80)
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.3)

    fig.suptitle("EXP-2656: SC Insulin Suppression Ceiling", fontsize=11, y=1.02)
    fig.tight_layout()
    fig.savefig(VIZ_DIR / "fig25_sc_ceiling.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("  fig25 saved")


def fig26_dual_isf_safety():
    """Dual-ISF dosing: TIR change vs hypo increase per patient."""
    data = json.loads((EXP_DIR / "exp-2661_dual_isf.json").read_text())

    patients, tir_delta, hypo_delta, infl = [], [], [], []
    for pid, p in data.items():
        patients.append(pid)
        tir_delta.append(p["tir_improvement"] * 100)
        hypo_delta.append(p["hypo_increase"] * 100)
        infl.append(p["inflation_ratio"])

    fig, ax = plt.subplots(figsize=(10, 6))
    sizes = [max(30, i * 30) for i in infl]
    colors = ["#27ae60" if t > 0 and h < 5 else "#d63031"
              for t, h in zip(tir_delta, hypo_delta)]
    ax.scatter(hypo_delta, tir_delta, s=sizes, c=colors, alpha=0.7, edgecolors="black")
    for i, pid in enumerate(patients):
        ax.annotate(pid, (hypo_delta[i], tir_delta[i]),
                    fontsize=7, ha="left", va="bottom", xytext=(4, 4),
                    textcoords="offset points")

    ax.axhline(y=0, color="black", linestyle="-", alpha=0.3)
    ax.axvline(x=5, color="red", linestyle="--", alpha=0.5, label="5pp hypo threshold")
    ax.axvline(x=0, color="black", linestyle="-", alpha=0.3)

    # Shade danger zone
    ax.axvspan(5, max(hypo_delta) + 5, alpha=0.05, color="red")

    ax.set_xlabel("Hypo Rate Increase (pp)")
    ax.set_ylabel("TIR Improvement (pp)")
    ax.set_title("EXP-2661: Dual-ISF Dosing Safety/Efficacy\n"
                 "Naive demand-ISF dosing: catastrophic hypo increase, no TIR gain\n"
                 "Circle size = inflation ratio")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(VIZ_DIR / "fig26_dual_isf_safety.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("  fig26 saved")


if __name__ == "__main__":
    print("Generating Phase 2 visualizations...")
    fig24_cr_adequacy()
    fig25_sc_ceiling()
    fig26_dual_isf_safety()
    print("Done!")
