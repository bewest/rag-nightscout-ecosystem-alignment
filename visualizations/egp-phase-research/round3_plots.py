#!/usr/bin/env python3
"""Round 3 visualizations for EGP Phase Separation Research.

Figures from EXP-2625 (per-patient EGP-aware settings).
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

RESULTS_DIR = Path("externals/experiments")
VIZ_DIR = Path("visualizations/egp-phase-research")
VIZ_DIR.mkdir(parents=True, exist_ok=True)


def load_results():
    with open(RESULTS_DIR / "exp-2625_egp_aware_settings.json") as f:
        return json.load(f)


def fig7_per_patient_egp_profiles(r):
    """Per-patient EGP metabolic profile: recovery, nadir, phase lag."""
    profiles = r["patient_profiles"]
    if not profiles:
        return

    pids = [p["patient"] for p in profiles]
    n = len(pids)
    x = np.arange(n)

    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    # Panel 1: Recovery slope (EGP rate proxy)
    ax = axes[0]
    recovery = [p["recovery_slope"] for p in profiles]
    colors = ["#e74c3c" if r > 20 else "#27ae60" if r < 10 else "#f39c12" for r in recovery]
    ax.bar(x, recovery, color=colors, edgecolor="k", linewidth=0.5)
    ax.axhline(y=18, color="blue", linestyle="--", alpha=0.6, label="Base EGP (18 mg/dL/hr)")
    ax.set_xlabel("Patient")
    ax.set_ylabel("Recovery Slope (mg/dL/hr)")
    ax.set_title("Post-Correction EGP Recovery Rate")
    ax.set_xticks(x)
    ax.set_xticklabels(pids)
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    # Annotate assessments
    for i, p in enumerate(profiles):
        label = "LOW?" if p["basal_assessment"] == "POSSIBLY_LOW" else "OK"
        color = "red" if label == "LOW?" else "green"
        ax.annotate(label, (i, recovery[i] + 1), ha="center", fontsize=7,
                    color=color, fontweight="bold")

    # Panel 2: Nadir timing with phase lag
    ax = axes[1]
    nadirs = [p["nadir_hours"] for p in profiles]
    lags = [p["phase_lag"] for p in profiles]
    ax.bar(x, nadirs, color="#3498db", edgecolor="k", linewidth=0.5, label="Nadir timing")
    ax.axhline(y=1.25, color="orange", linestyle=":", linewidth=2,
               label="Insulin peak (1.25h)")
    ax.set_xlabel("Patient")
    ax.set_ylabel("Time to Nadir (hours)")
    ax.set_title("Individual EGP Phase Lag")
    ax.set_xticks(x)
    ax.set_xticklabels(pids)
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    # Annotate phase lag
    for i, lag in enumerate(lags):
        ax.annotate(f"+{lag:.1f}h", (i, nadirs[i] + 0.1), ha="center", fontsize=7,
                    color="#8e44ad", fontweight="bold")

    # Panel 3: ISF inflation
    ax = axes[2]
    apparent = [p["apparent_isf"] for p in profiles]
    corrected = [p["corrected_isf"] if p["corrected_isf"] else p["apparent_isf"]
                 for p in profiles]
    inflation = [p["isf_inflation_pct"] if p["isf_inflation_pct"] else 0
                 for p in profiles]
    w = 0.35
    ax.bar(x - w / 2, apparent, w, label="Apparent ISF", color="#e74c3c", alpha=0.8)
    ax.bar(x + w / 2, corrected, w, label="EGP-Corrected ISF", color="#3498db", alpha=0.8)
    ax.set_xlabel("Patient")
    ax.set_ylabel("ISF (mg/dL per U)")
    ax.set_title("ISF: Apparent vs EGP-Corrected")
    ax.set_xticks(x)
    ax.set_xticklabels(pids)
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    # Annotate inflation %
    for i, inf in enumerate(inflation):
        if abs(inf) >= 15:
            ax.annotate(f"+{inf:.0f}%", (i, max(apparent[i], corrected[i]) + 1),
                        ha="center", fontsize=7, color="red", fontweight="bold")

    fig.suptitle("EXP-2625: Per-Patient EGP Metabolic Profiles", fontsize=13)
    fig.tight_layout()
    fig.savefig(VIZ_DIR / "fig7_per_patient_egp_profiles.png", dpi=150)
    plt.close(fig)
    print("  Saved fig7_per_patient_egp_profiles.png")


def fig8_circadian_egp(r):
    """Circadian EGP recovery: day vs night per patient."""
    per_patient = r.get("per_patient", {})
    patients_with_circadian = []
    for pid, data in per_patient.items():
        if isinstance(data, dict) and "circadian" in data and data["circadian"]:
            patients_with_circadian.append((pid, data["circadian"]))

    if len(patients_with_circadian) < 2:
        print("  SKIP fig8: not enough circadian data")
        return

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    pids = [p[0] for p in patients_with_circadian]
    day_rec = [p[1]["day_recovery_median"] for p in patients_with_circadian]
    night_rec = [p[1]["night_recovery_median"] for p in patients_with_circadian]
    dawn = [p[1]["dawn_effect"] for p in patients_with_circadian]
    n = len(pids)
    x = np.arange(n)

    # Panel 1: Day vs Night recovery
    ax = axes[0]
    w = 0.35
    ax.bar(x - w / 2, day_rec, w, label="Day (06-22h)", color="#f39c12")
    ax.bar(x + w / 2, night_rec, w, label="Night (22-06h)", color="#2c3e50")
    ax.axhline(y=0, color="k", linewidth=0.5)
    ax.set_xlabel("Patient")
    ax.set_ylabel("Recovery Slope (mg/dL/hr)")
    ax.set_title("EGP Recovery: Day vs Night")
    ax.set_xticks(x)
    ax.set_xticklabels(pids)
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.3)

    # Panel 2: Dawn effect
    ax = axes[1]
    colors = ["#e74c3c" if d > 5 else "#3498db" if d < -5 else "#95a5a6" for d in dawn]
    ax.bar(x, dawn, color=colors, edgecolor="k", linewidth=0.5)
    ax.axhline(y=0, color="k", linewidth=0.5)
    ax.set_xlabel("Patient")
    ax.set_ylabel("Night - Day Recovery (mg/dL/hr)")
    ax.set_title("Dawn Effect: Night EGP Excess")
    ax.set_xticks(x)
    ax.set_xticklabels(pids)
    ax.grid(axis="y", alpha=0.3)
    for i, d in enumerate(dawn):
        label = "Dawn↑" if d > 5 else "Night↓" if d < -5 else "~equal"
        ax.annotate(label, (i, d + (2 if d > 0 else -4)), ha="center",
                    fontsize=7, fontweight="bold")

    fig.suptitle("EXP-2625: Circadian EGP Variation", fontsize=13)
    fig.tight_layout()
    fig.savefig(VIZ_DIR / "fig8_circadian_egp.png", dpi=150)
    plt.close(fig)
    print("  Saved fig8_circadian_egp.png")


def fig9_basal_vs_egp(r):
    """Basal demand rate vs EGP recovery — the matching condition."""
    profiles = r["patient_profiles"]
    per_patient = r.get("per_patient", {})
    if not profiles:
        return

    fig, ax = plt.subplots(1, 1, figsize=(8, 6))

    for p in profiles:
        pid = p["patient"]
        data = per_patient.get(pid, {})
        if "basal_analysis" not in data:
            continue

        basal_demand = data["basal_analysis"]["basal_demand_rate_mgdl_hr"]
        recovery = p["recovery_slope"]
        assessment = p["basal_assessment"]

        color = {"POSSIBLY_LOW": "#e74c3c", "ADEQUATE": "#27ae60",
                 "POSSIBLY_HIGH": "#3498db"}.get(assessment, "#999")
        marker = "^" if assessment == "POSSIBLY_LOW" else "v" if assessment == "POSSIBLY_HIGH" else "o"

        ax.scatter(basal_demand, recovery, c=color, marker=marker, s=120,
                   edgecolor="k", linewidth=0.8, zorder=5)
        ax.annotate(pid, (basal_demand, recovery), xytext=(5, 5),
                    textcoords="offset points", fontsize=9, fontweight="bold")

    # Identity line (equilibrium)
    lims = ax.get_xlim()
    max_val = max(ax.get_xlim()[1], ax.get_ylim()[1])
    ax.plot([0, max_val], [0, max_val], "k--", alpha=0.3, label="Equilibrium (EGP=Demand)")
    ax.axhline(y=18, color="blue", linestyle=":", alpha=0.4, label="Base EGP (~18 mg/dL/hr)")

    ax.set_xlabel("Basal Demand Rate (basal × ISF, mg/dL/hr)")
    ax.set_ylabel("Post-Correction Recovery (mg/dL/hr)")
    ax.set_title("EGP Recovery vs Basal Demand Rate\n(Points above line → basal may be insufficient)")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)

    # Legend for assessment
    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], marker="^", color="w", markerfacecolor="#e74c3c",
               markersize=10, label="Possibly Low"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#27ae60",
               markersize=10, label="Adequate"),
    ]
    ax.legend(handles=legend_elements + ax.get_legend().legend_handles,
              fontsize=8, loc="upper left")

    fig.tight_layout()
    fig.savefig(VIZ_DIR / "fig9_basal_vs_egp.png", dpi=150)
    plt.close(fig)
    print("  Saved fig9_basal_vs_egp.png")


if __name__ == "__main__":
    print("Generating Round 3 visualizations...")
    r = load_results()
    fig7_per_patient_egp_profiles(r)
    fig8_circadian_egp(r)
    fig9_basal_vs_egp(r)
    print("Done.")
