#!/usr/bin/env python3
"""Round 2 visualizations for EGP calibration experiments.

Generates figures 25-28:
  fig25: Per-patient phase separation (EXP-2631)
  fig26: Controller gain patterns (EXP-2632)
  fig27: EGP prediction failure analysis (EXP-2633)
  fig28: Coupling proof — why naive EGP hurts
"""
import json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXPDIR = ROOT / "externals" / "experiments"
OUTDIR = Path(__file__).parent


def _load(name):
    with open(EXPDIR / name) as f:
        return json.load(f)


def fig25_phase_separation():
    """Per-patient phase slopes showing EGP variation."""
    r = _load("exp-2631_phase_resolved.json")
    pp = r["per_patient"]

    patients = sorted(pp.keys())
    p1 = [pp[p].get("p1_mean", 0) for p in patients]
    p3 = [pp[p].get("p3_mean", 0) for p in patients]
    n_events = [pp[p].get("n_events", 0) for p in patients]

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Panel A: Phase slopes by patient
    ax = axes[0]
    x = np.arange(len(patients))
    w = 0.35
    bars1 = ax.bar(x - w / 2, p1, w, label="Phase 1 (Demand)", color="#e74c3c", alpha=0.8)
    bars3 = ax.bar(x + w / 2, p3, w, label="Phase 3 (Recovery)", color="#27ae60", alpha=0.8)
    ax.axhline(18, color="#f39c12", linestyle="--", linewidth=2, label="Base EGP (18 mg/dL/hr)")
    ax.axhline(0, color="black", linewidth=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels(patients, fontsize=12)
    ax.set_xlabel("Patient", fontsize=12)
    ax.set_ylabel("Slope (mg/dL/hr)", fontsize=12)
    ax.set_title("A. Phase Slopes per Patient", fontsize=13, fontweight="bold")
    ax.legend(fontsize=9)

    # Annotate event counts
    for i, n in enumerate(n_events):
        ax.annotate(f"n={n}", (i, max(p1[i], p3[i]) + 2), ha="center", fontsize=8, color="gray")

    # Panel B: Recovery rate distribution
    ax = axes[1]
    all_p3 = []
    for p in patients:
        slopes = pp[p].get("p3_recovery_slopes", [])
        all_p3.extend(slopes)
    if all_p3:
        ax.hist(all_p3, bins=50, range=(-50, 80), color="#27ae60", alpha=0.7, edgecolor="white")
        ax.axvline(18, color="#f39c12", linestyle="--", linewidth=2, label=f"Base EGP = 18")
        ax.axvline(np.median(all_p3), color="#2980b9", linestyle="-", linewidth=2,
                   label=f"Median = {np.median(all_p3):.1f}")
        ax.set_xlabel("Phase 3 Recovery Slope (mg/dL/hr)", fontsize=12)
        ax.set_ylabel("Count", fontsize=12)
        ax.set_title("B. Recovery Rate Distribution (all events)", fontsize=13, fontweight="bold")
        ax.legend(fontsize=10)

    plt.tight_layout()
    out = OUTDIR / "fig25_phase_separation.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(out.name)


def fig26_controller_gain():
    """Controller modulation patterns around corrections."""
    r = _load("exp-2632_controller_gain.json")
    wm = r.get("window_modulation", {})
    pp = r.get("per_patient", {})

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Panel A: Modulation ratio by window
    ax = axes[0]
    windows = ["pre_1h", "post_0_1h", "post_1_2h", "post_2_4h", "post_4_6h"]
    labels = ["-1→0h", "0→1h", "1→2h", "2→4h", "4→6h"]
    means = [wm.get(w, {}).get("mean_ratio", 0) for w in windows]
    stds = [wm.get(w, {}).get("std", 0) for w in windows]

    colors = ["#e74c3c"] + ["#3498db"] * 4
    bars = ax.bar(range(len(windows)), means, yerr=stds, color=colors, alpha=0.8,
                  edgecolor="white", capsize=4)
    ax.axhline(1.0, color="#2c3e50", linestyle="--", linewidth=1.5, label="Scheduled rate")
    ax.set_xticks(range(len(windows)))
    ax.set_xticklabels(labels, fontsize=11)
    ax.set_xlabel("Time Window (relative to correction)", fontsize=12)
    ax.set_ylabel("Enacted / Scheduled Ratio", fontsize=12)
    ax.set_title("A. AID Basal Modulation Around Corrections", fontsize=13, fontweight="bold")
    ax.legend(fontsize=10)

    # Panel B: Aggressiveness by patient
    ax = axes[1]
    patients = sorted(pp.keys())
    agg = [pp[p].get("aggressiveness", 0) for p in patients]
    colors_p = ["#e74c3c" if a > 1.5 else "#3498db" for a in agg]
    ax.barh(patients, agg, color=colors_p, alpha=0.8, edgecolor="white")
    ax.set_xlabel("Aggressiveness (mean |enacted/scheduled - 1|)", fontsize=12)
    ax.set_ylabel("Patient", fontsize=12)
    ax.set_title("B. Controller Aggressiveness per Patient", fontsize=13, fontweight="bold")
    ax.axvline(1.0, color="#e74c3c", linestyle="--", alpha=0.5, label="High threshold")
    ax.legend(fontsize=10)

    plt.tight_layout()
    out = OUTDIR / "fig26_controller_gain.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(out.name)


def fig27_prediction_failure():
    """EGP prediction gets progressively worse — proof of coupling."""
    r = _load("exp-2633_egp_prediction.json")
    ws = r.get("window_summary", {})
    pp = r.get("per_patient", {})

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Panel A: MAE by window — standard vs EGP
    ax = axes[0]
    windows = ["1-2h", "2-3h", "3-4h", "4-5h", "5-6h"]
    std_mae = [ws.get(w, {}).get("standard", 0) for w in windows]
    egp_mae = [ws.get(w, {}).get("egp", 0) for w in windows]

    x = np.arange(len(windows))
    w_bar = 0.35
    ax.bar(x - w_bar / 2, std_mae, w_bar, label="Standard (no EGP)", color="#3498db", alpha=0.8)
    ax.bar(x + w_bar / 2, egp_mae, w_bar, label="+ Naive EGP", color="#e74c3c", alpha=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(windows, fontsize=11)
    ax.set_xlabel("Time Window Post-Correction", fontsize=12)
    ax.set_ylabel("MAE (mg/dL)", fontsize=12)
    ax.set_title("A. Adding EGP Makes Predictions WORSE", fontsize=13, fontweight="bold")
    ax.legend(fontsize=10)

    # Add improvement % labels
    for i, w_name in enumerate(windows):
        imp = ws.get(w_name, {}).get("improvement", 0) * 100
        y_pos = max(std_mae[i], egp_mae[i]) + 2
        ax.annotate(f"{imp:+.0f}%", (i + w_bar / 2, y_pos), ha="center", fontsize=9,
                    color="#e74c3c", fontweight="bold")

    # Panel B: Recovery rate vs improvement — negative correlation!
    ax = axes[1]
    patients = sorted(pp.keys())
    rec_rates = [pp[p].get("recovery_rate", 0) for p in patients]
    improvements = [pp[p].get("improvement_3-6h", 0) * 100 for p in patients]

    ax.scatter(rec_rates, improvements, s=100, c="#8e44ad", alpha=0.8, edgecolors="white", zorder=3)
    for i, pid in enumerate(patients):
        ax.annotate(pid, (rec_rates[i], improvements[i]), textcoords="offset points",
                    xytext=(8, 5), fontsize=10)

    # Trend line
    if len(rec_rates) > 2:
        from scipy import stats
        slope, intercept, r_val, p_val, se = stats.linregress(rec_rates, improvements)
        x_line = np.linspace(min(rec_rates), max(rec_rates), 50)
        ax.plot(x_line, slope * x_line + intercept, "--", color="#e74c3c", alpha=0.7,
                label=f"r = {r_val:.2f}")

    ax.axhline(0, color="black", linewidth=0.5, linestyle="-")
    ax.set_xlabel("Calibrated Recovery Rate (mg/dL/hr)", fontsize=12)
    ax.set_ylabel("MAE Improvement (%)", fontsize=12)
    ax.set_title("B. Higher EGP → Worse Prediction (Coupling!)", fontsize=13, fontweight="bold")
    ax.legend(fontsize=10)

    plt.tight_layout()
    out = OUTDIR / "fig27_prediction_failure.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(out.name)


def fig28_coupling_proof():
    """Synthesis: why naive EGP fails — the coupling diagram."""
    fig, ax = plt.subplots(1, 1, figsize=(12, 7))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.axis("off")

    # Title
    ax.text(5, 9.5, "The Coupling Problem: Why Naive EGP Addition Fails",
            ha="center", fontsize=16, fontweight="bold")

    # Left: Naive model
    ax.text(2.5, 8.5, "Naive Model (WRONG)", ha="center", fontsize=13,
            fontweight="bold", color="#e74c3c")
    ax.text(2.5, 7.8, "Glucose = Insulin Effect + EGP", ha="center", fontsize=11,
            family="monospace", bbox=dict(boxstyle="round", facecolor="#fadbd8"))
    ax.text(2.5, 7.1, "Assumes forces are\nINDEPENDENT & ADDITIVE", ha="center",
            fontsize=10, style="italic", color="#7f8c8d")

    # Right: Coupled model
    ax.text(7.5, 8.5, "Coupled Model (CORRECT)", ha="center", fontsize=13,
            fontweight="bold", color="#27ae60")
    ax.text(7.5, 7.8, "Glucose = f(Insulin, EGP, AID)", ha="center", fontsize=11,
            family="monospace", bbox=dict(boxstyle="round", facecolor="#d5f5e3"))
    ax.text(7.5, 7.1, "Forces OPPOSE each other\nthrough feedback loop", ha="center",
            fontsize=10, style="italic", color="#7f8c8d")

    # Center evidence box
    evidence = [
        "EVIDENCE FROM 7,652 CORRECTIONS",
        "━" * 40,
        "• EGP + AID + Counter-reg = 34 mg/dL/hr",
        "• Actual recovery = 4.1 mg/dL/hr",
        "• Coupling suppresses 88% of raw forces",
        "",
        "• Naive EGP addition: MAE WORSE by 17.5%",
        "• Gets worse over time: -3% at 1h → -23% at 5h",
        "• Higher EGP rate → WORSE prediction (r = -0.41)",
        "",
        "• Per-patient EGP varies 14×: 1.6 → 22.0 mg/dL/hr",
        "• Yet variation doesn't help — it HURTS",
    ]
    y = 5.8
    for line in evidence:
        fontsize = 12 if line.startswith("EVIDENCE") else 10
        weight = "bold" if line.startswith("EVIDENCE") or line.startswith("━") else "normal"
        color = "#2c3e50" if "•" in line else "#7f8c8d"
        if "WORSE" in line or "HURTS" in line:
            color = "#e74c3c"
        ax.text(5, y, line, ha="center", fontsize=fontsize, fontweight=weight,
                color=color, family="monospace")
        y -= 0.38

    # Bottom: Implication
    ax.text(5, 1.2, "IMPLICATION", ha="center", fontsize=13, fontweight="bold",
            color="#2c3e50")
    ax.text(5, 0.6, "EGP modeling requires CO-MODELING the AID controller response.\n"
                     "The controller is not a passive observer — it actively opposes EGP recovery.",
            ha="center", fontsize=11, style="italic",
            bbox=dict(boxstyle="round,pad=0.5", facecolor="#f0f0f0", edgecolor="#2c3e50"))

    plt.tight_layout()
    out = OUTDIR / "fig28_coupling_proof.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(out.name)


if __name__ == "__main__":
    fig25_phase_separation()
    fig26_controller_gain()
    fig27_prediction_failure()
    fig28_coupling_proof()
    print("Done — 4 figures generated")
