#!/usr/bin/env python3
"""Round 2 visualizations for EGP Phase Separation Research.

Figures from EXP-2623 (meal masking) and EXP-2624 (correction recovery).
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
    with open(RESULTS_DIR / "exp-2623_post_meal_egp.json") as f:
        r2623 = json.load(f)
    with open(RESULTS_DIR / "exp-2624_correction_egp_recovery.json") as f:
        r2624 = json.load(f)
    return r2623, r2624


def fig5_egp_enrichment(r2623):
    """Before/after EGP-band power with meal masking."""
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    pids = r2623["patients"]
    full = [r2623["per_patient"][p]["full_spectrum"]["egp_low"] for p in pids]
    masked = [r2623["per_patient"][p]["masked_spectrum"]["egp_low"] for p in pids]
    ratios = [r2623["per_patient"][p]["egp_enrichment_ratio"] for p in pids]

    # Panel 1: Before/after bar chart
    ax = axes[0]
    x = np.arange(len(pids))
    w = 0.35
    ax.bar(x - w / 2, [f * 100 for f in full], w, label="Full residual", color="#3498db")
    ax.bar(x + w / 2, [m * 100 for m in masked], w, label="Meals masked", color="#e74c3c")
    ax.set_xlabel("Patient")
    ax.set_ylabel("EGP-Band Power (%)")
    ax.set_title("EGP Spectral Power: Full vs Meal-Masked Residual")
    ax.set_xticks(x)
    ax.set_xticklabels(pids)
    ax.legend()
    ax.grid(axis="y", alpha=0.3)

    # Panel 2: Enrichment ratio
    ax = axes[1]
    colors = ["#27ae60" if r >= 2.0 else "#95a5a6" for r in ratios]
    ax.bar(x, ratios, color=colors, edgecolor="k", linewidth=0.5)
    ax.axhline(y=2.0, color="red", linestyle="--", alpha=0.7, label="2× threshold")
    ax.set_xlabel("Patient")
    ax.set_ylabel("EGP Enrichment Ratio (×)")
    ax.set_title("EGP-Band Enrichment After Meal Masking")
    ax.set_xticks(x)
    ax.set_xticklabels(pids)
    ax.legend()
    ax.grid(axis="y", alpha=0.3)

    fig.suptitle("EXP-2623: Meal Masking Reveals Hidden EGP Signal", fontsize=13)
    fig.tight_layout()
    fig.savefig(VIZ_DIR / "fig5_egp_enrichment.png", dpi=150)
    plt.close(fig)
    print("  Saved fig5_egp_enrichment.png")


def fig6_correction_recovery(r2624):
    """Nadir timing and recovery slope distributions."""
    events = r2624.get("pooled_events", [])
    if not events:
        print("  SKIP fig6: no events")
        return

    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    nadir_hrs = [e["nadir_hours"] for e in events]
    recovery = [e["recovery_slope_mgdl_hr"] for e in events]
    pre_bg = [e["pre_bg"] for e in events]
    drops = [e["drop_mgdl"] for e in events]

    pids = sorted(set(e.get("timestamp", "")[:10] for e in events))
    # Color by patient using parent results
    per_patient = r2624.get("per_patient", {})
    pid_list = list(per_patient.keys())
    cmap = plt.cm.tab10
    # Reconstruct per-event patient from counts
    event_pids = []
    for pid in pid_list:
        n = per_patient[pid]["n_events"]
        event_pids.extend([pid] * n)
    pid_colors = {p: cmap(i / max(len(pid_list), 1)) for i, p in enumerate(pid_list)}

    # Panel 1: Nadir timing histogram
    ax = axes[0]
    ax.hist(nadir_hrs, bins=20, color="#3498db", edgecolor="k", alpha=0.7)
    ax.axvline(x=np.median(nadir_hrs), color="red", linestyle="--", label=f"Median={np.median(nadir_hrs):.1f}h")
    ax.axvline(x=1.25, color="orange", linestyle=":", label="Insulin peak (1.25h)")
    ax.set_xlabel("Time to Nadir (hours)")
    ax.set_ylabel("Count")
    ax.set_title("Glucose Nadir Timing Post-Correction")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)

    # Panel 2: Recovery slope histogram
    ax = axes[1]
    ax.hist(recovery, bins=30, color="#e74c3c", edgecolor="k", alpha=0.7)
    ax.axvline(x=np.median(recovery), color="red", linestyle="--",
               label=f"Median={np.median(recovery):.0f}")
    ax.axvline(x=18, color="green", linestyle=":", label="Base EGP (18 mg/dL/hr)")
    ax.set_xlabel("Recovery Slope (mg/dL/hr)")
    ax.set_ylabel("Count")
    ax.set_title("Post-Nadir Recovery Rate")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)

    # Panel 3: Pre-BG vs recovery slope
    ax = axes[2]
    if len(event_pids) == len(pre_bg):
        c = [pid_colors.get(p, "#999999") for p in event_pids]
    else:
        c = "#3498db"
    ax.scatter(pre_bg, recovery, c=c, alpha=0.5, edgecolor="k", linewidth=0.3, s=25)
    if len(pre_bg) > 2:
        m, b = np.polyfit(pre_bg, recovery, 1)
        xs = np.linspace(min(pre_bg), max(pre_bg), 50)
        ax.plot(xs, m * xs + b, "r--", alpha=0.7)
    r_val = r2624.get("pooled", {}).get("r_prebg_recovery", 0)
    ax.set_xlabel("Pre-Correction BG (mg/dL)")
    ax.set_ylabel("Recovery Slope (mg/dL/hr)")
    ax.set_title(f"Pre-BG → Recovery (r={r_val:.2f})")
    ax.grid(alpha=0.3)
    if len(event_pids) == len(pre_bg):
        for pid in pid_list:
            ax.scatter([], [], c=[pid_colors[pid]], label=f"Pt {pid}", s=25)
        ax.legend(fontsize=7, loc="upper right")

    fig.suptitle("EXP-2624: Post-Correction EGP Recovery Dynamics", fontsize=13)
    fig.tight_layout()
    fig.savefig(VIZ_DIR / "fig6_correction_recovery.png", dpi=150)
    plt.close(fig)
    print("  Saved fig6_correction_recovery.png")


if __name__ == "__main__":
    print("Generating Round 2 visualizations...")
    r2623, r2624 = load_results()
    fig5_egp_enrichment(r2623)
    fig6_correction_recovery(r2624)
    print("Done.")
