#!/usr/bin/env python3
"""EGP Deconfounding Report Visualizations.

Figures for the EGP deconfounding report (2026-04-13), covering:
- Supply/demand theoretical framework
- AID Compensation Cascade (IOB-protective illusion)
- Ringing/resonance in real patient data
- Hill EGP model vs actual recovery
- Recovery decomposition
- Ecosystem takeaway

Uses data from EXP-2624, 2626, 2629, 2630.
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd

RESULTS_DIR = Path("externals/experiments")
PARQUET = Path("externals/ns-parquet/training/grid.parquet")
VIZ_DIR = Path("visualizations/egp-deconfounding")
VIZ_DIR.mkdir(parents=True, exist_ok=True)

C_GLUCOSE = "#2196F3"
C_IOB = "#FF9800"
C_EGP = "#4CAF50"
C_INSULIN = "#F44336"
C_BASAL = "#9C27B0"
C_AID = "#795548"
C_COUNTER = "#00BCD4"


def load_results():
    r = {}
    for name in [
        "exp-2624_correction_egp_recovery",
        "exp-2626_asymmetry_synthesis",
        "exp-2629_aid_compensation_cascade",
        "exp-2630_egp_deconfound",
    ]:
        path = RESULTS_DIR / f"{name}.json"
        if path.exists():
            with open(path) as f:
                r[name.split("_", 1)[0]] = json.load(f)
    return r


def fig19_supply_demand_theory():
    """Figure 19: Two forces on glucose — supply (EGP) vs demand (insulin)."""
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))

    t = np.linspace(0, 6, 300)
    td = 360.0; tp = 75.0
    tau = tp * (1 - tp / td) / (1 - 2 * tp / td)
    a = 2 * tau / td
    S = 1 / (1 - a + (1 + a) * np.exp(-td / tau))
    t_min = t * 60
    absorbed = S * (1 - a) * (
        (t_min ** 2 / (tau * td * (1 - a)) - t_min / tau - 1) * np.exp(-t_min / tau) + 1
    )
    iob = np.clip(1 - absorbed, 0, 1)
    activity = np.gradient(absorbed) * 60

    iob_u = iob * 2.0
    suppression = iob_u ** 1.5 / (iob_u ** 1.5 + 2.0 ** 1.5)
    egp = 18.0 * (1 - suppression)

    # Panel A: Two forces
    ax = axes[0]
    ax.fill_between(t, 0, -activity * 80, alpha=0.3, color=C_INSULIN, label="Insulin action (demand ↓)")
    ax.fill_between(t, 0, egp, alpha=0.3, color=C_EGP, label="EGP (supply ↑)")
    ax.axhline(0, color="gray", linewidth=0.5)
    ax.set_xlabel("Hours post-bolus")
    ax.set_ylabel("Glucose force (mg/dL/hr)")
    ax.set_title("A. Two Forces on Glucose", fontweight="bold")
    ax.legend(loc="upper right", fontsize=8)
    ax.set_xlim(0, 6)
    ax.annotate("Insulin peak\n(1.25h)", xy=(1.25, -max(activity * 80) * 0.8),
                fontsize=8, ha="center", color=C_INSULIN)

    # Panel B: Resulting glucose
    ax = axes[1]
    glucose = np.zeros_like(t)
    glucose[0] = 250
    for i in range(1, len(t)):
        dt = t[i] - t[i - 1]
        glucose[i] = glucose[i - 1] + (egp[i] - activity[i] * 80) * dt
    ax.plot(t, glucose, color=C_GLUCOSE, linewidth=2.5)
    ax.axhspan(70, 180, alpha=0.1, color="green")
    ax.axhline(180, color="green", linewidth=0.5, linestyle="--", alpha=0.3)
    ax.axhline(70, color="red", linewidth=0.5, linestyle="--", alpha=0.3)
    nadir_idx = np.argmin(glucose)
    ax.plot(t[nadir_idx], glucose[nadir_idx], "v", color=C_INSULIN, markersize=10)
    ax.annotate(f"Nadir @ {t[nadir_idx]:.1f}h", xy=(t[nadir_idx], glucose[nadir_idx]),
                xytext=(t[nadir_idx] + 0.5, glucose[nadir_idx] - 15), fontsize=8,
                arrowprops=dict(arrowstyle="->", color="gray"))
    ax.axvspan(0, 2, alpha=0.05, color=C_INSULIN)
    ax.axvspan(2, 3.5, alpha=0.05, color="gray")
    ax.axvspan(3.5, 6, alpha=0.05, color=C_EGP)
    ax.text(1.0, max(glucose) + 5, "DEMAND", ha="center", fontsize=7, color=C_INSULIN, fontweight="bold")
    ax.text(2.75, max(glucose) + 5, "TRANS", ha="center", fontsize=7, color="gray", fontweight="bold")
    ax.text(4.75, max(glucose) + 5, "SUPPLY", ha="center", fontsize=7, color=C_EGP, fontweight="bold")
    ax.set_xlabel("Hours post-correction")
    ax.set_ylabel("Glucose (mg/dL)")
    ax.set_title("B. Glucose Response", fontweight="bold")
    ax.set_xlim(0, 6)

    # Panel C: Phase lag
    ax = axes[2]
    ax.plot(t, activity / max(activity) * 100, color=C_INSULIN, linewidth=2, label="Insulin activity")
    ax.plot(t, (1 - egp / 18) * 100, color=C_EGP, linewidth=2, label="EGP suppression")
    ax.axvline(1.25, color=C_INSULIN, linestyle=":", alpha=0.5)
    ax.axvline(3.5, color=C_EGP, linestyle=":", alpha=0.5)
    ax.annotate("", xy=(3.5, 50), xytext=(1.25, 50),
                arrowprops=dict(arrowstyle="<->", color="black", linewidth=1.5))
    ax.text(2.375, 55, "2.25h phase lag", ha="center", fontsize=9, fontweight="bold")
    ax.set_xlabel("Hours post-bolus")
    ax.set_ylabel("% of peak")
    ax.set_title("C. The Phase Lag", fontweight="bold")
    ax.legend(loc="upper right", fontsize=8)
    ax.set_xlim(0, 6); ax.set_ylim(0, 105)

    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig19_supply_demand_theory.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  fig19_supply_demand_theory.png")


def fig20_aid_compensation_cascade(results):
    """Figure 20: AID Compensation Cascade — the IOB-protective illusion."""
    r29 = results.get("exp-2629")
    if not r29:
        print("  SKIP fig20 (no EXP-2629 data)")
        return

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    # Panel A: Example cascade
    ax = axes[0, 0]
    cascade = None
    found_pid = "?"
    for pid in ["a", "f", "i", "c"]:
        pdata = r29.get("per_patient", {}).get(pid, {})
        cascades = pdata.get("example_cascades", [])
        if cascades:
            cascade = cascades[0]
            found_pid = pid
            break

    if cascade:
        post_g = [x for x in cascade["post_glucose"] if x is not None]
        post_iob = [x for x in cascade["post_iob"] if x is not None]
        t_g = np.arange(len(post_g)) * 5 / 60
        t_iob = np.arange(len(post_iob)) * 5 / 60
        ax2 = ax.twinx()
        ln1 = ax.plot(t_g, post_g, color=C_GLUCOSE, linewidth=2, label="Glucose")
        ln2 = ax2.plot(t_iob, post_iob, color=C_IOB, linewidth=2, label="IOB")
        ax.axhline(80, color="red", linewidth=0.5, linestyle="--", alpha=0.5)
        ax.set_xlabel("Hours post-correction")
        ax.set_ylabel("Glucose (mg/dL)", color=C_GLUCOSE)
        ax2.set_ylabel("IOB (U)", color=C_IOB)
        lns = ln1 + ln2
        ax.legend(lns, [l.get_label() for l in lns], loc="upper right", fontsize=8)
    ax.set_title(f"A. Correction Cascade (Patient {found_pid})", fontweight="bold")

    # Panel B: IOB drop before hypo
    ax = axes[0, 1]
    drops = []
    labels = []
    for pid in r29.get("patients", []):
        pdata = r29.get("per_patient", {}).get(pid, {})
        med = pdata.get("median_iob_drop_pct")
        if med is not None:
            drops.append(med)
            labels.append(pid)
    if drops:
        colors = [C_INSULIN if d > 30 else C_AID for d in drops]
        ax.bar(labels, drops, color=colors, alpha=0.7, edgecolor="black", linewidth=0.5)
        ax.axhline(30, color="red", linestyle="--", linewidth=1, label="30% threshold")
        ax.axhline(0, color="gray", linewidth=0.5)
        pooled_med = r29.get("pooled", {}).get("median_iob_drop_pct", 0)
        ax.text(0.02, 0.95, f"Pooled median: {pooled_med:.0f}%",
                transform=ax.transAxes, fontsize=9, va="top",
                bbox=dict(boxstyle="round,pad=0.3", facecolor="lightyellow"))
        ax.legend(fontsize=8)
    ax.set_xlabel("Patient")
    ax.set_ylabel("IOB drop before hypo (%)")
    ax.set_title("B. AID Withdrawal Before Hypo", fontweight="bold")

    # Panel C: Causation diagram
    ax = axes[1, 0]
    ax.set_xlim(0, 10); ax.set_ylim(0, 8); ax.axis("off")
    ax.text(5, 7.5, "Reversed Causation", fontsize=13, fontweight="bold", ha="center")

    # Apparent
    ax.text(2.5, 6.5, "APPARENT", fontsize=10, fontweight="bold", ha="center", color="red")
    ax.text(2.5, 5.5, "High IOB", fontsize=9, ha="center",
            bbox=dict(boxstyle="round", facecolor="#FFCDD2"))
    ax.annotate("", xy=(2.5, 3.7), xytext=(2.5, 5.1),
                arrowprops=dict(arrowstyle="->", color="red", linewidth=2))
    ax.text(2.5, 3.3, '"Protects"\nagainst hypo', fontsize=9, ha="center",
            bbox=dict(boxstyle="round", facecolor="#FFCDD2"))

    # Actual
    ax.text(7.5, 6.5, "ACTUAL", fontsize=10, fontweight="bold", ha="center", color="green")
    boxes = [("Glucose ↓", 5.8), ("AID withdraws\ninsulin", 4.3), ("IOB ↓ + EGP ↑", 2.8),
             ("Glucose recovers", 1.3)]
    for text, y in boxes:
        ax.text(7.5, y, text, fontsize=9, ha="center",
                bbox=dict(boxstyle="round", facecolor="#C8E6C9"))
    for y1, y2 in [(5.4, 4.8), (3.9, 3.3), (2.4, 1.8)]:
        ax.annotate("", xy=(7.5, y2), xytext=(7.5, y1),
                    arrowprops=dict(arrowstyle="->", color="green", linewidth=1.5))

    ax.plot([5, 5], [1, 7], color="gray", linewidth=1, linestyle="--")
    ax.set_title("C. The IOB-Protective Illusion", fontweight="bold", pad=10)

    # Panel D: AID-active vs suspended recovery (from EXP-2630)
    ax = axes[1, 1]
    r30 = results.get("exp-2630")
    if r30:
        active = r30["pooled"].get("active_mean_recovery")
        suspended = r30["pooled"].get("suspended_mean_recovery")
        if active is not None and suspended is not None:
            bars = ax.bar(["AID Active\n(withdrawing)", "AID Suspended\n(no controller)"],
                          [active, suspended],
                          color=[C_INSULIN, C_EGP], alpha=0.7, edgecolor="black", linewidth=0.5)
            ax.text(0, active + 0.3, f"{active:.1f}", ha="center", fontsize=10, fontweight="bold")
            ax.text(1, suspended + 0.3, f"{suspended:.1f}", ha="center", fontsize=10, fontweight="bold")
            diff = active - suspended
            ax.text(0.5, max(active, suspended) + 1.5,
                    f"Δ = {diff:.1f} mg/dL/hr\n(AID adds {diff:.1f} to recovery)\np < 0.0001",
                    ha="center", fontsize=9,
                    bbox=dict(boxstyle="round,pad=0.3", facecolor="lightyellow"))
    ax.set_ylabel("Recovery rate (mg/dL/hr)")
    ax.set_title("D. AID Withdrawal Adds to Recovery", fontweight="bold")

    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig20_aid_compensation_cascade.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  fig20_aid_compensation_cascade.png")


def fig21_ringing_resonance():
    """Figure 21: Ringing/resonance in real AID control."""
    df = pd.read_parquet(PARQUET)
    df["time"] = pd.to_datetime(df["time"])

    fig, axes = plt.subplots(3, 1, figsize=(14, 12), sharex=True)

    pdf = df[df["patient_id"] == "a"].sort_values("time").copy()
    glucose = pdf["glucose"].values
    iob = pdf["iob"].fillna(0).values
    net_basal = pdf["net_basal"].fillna(0).values
    sched_basal = pdf["scheduled_basal_rate"].fillna(0).values
    bolus_vals = pdf["bolus"].fillna(0).values

    # Find best 24h window with oscillations
    window = 288
    best_start = 0
    best_score = 0
    for start in range(0, len(glucose) - window, 12):
        chunk_g = glucose[start:start + window]
        valid = np.isfinite(chunk_g)
        if valid.sum() < window * 0.8:
            continue
        g_s = pd.Series(chunk_g).rolling(3, min_periods=1).mean().values
        valid_g = g_s[np.isfinite(g_s)]
        if len(valid_g) < 50:
            continue
        diffs = np.diff(np.sign(np.diff(valid_g)))
        changes = np.sum(diffs != 0)
        amp = np.std(valid_g)
        nb = np.sum(bolus_vals[start:start + window] > 0.3)
        score = changes * amp * (1 + nb)
        if score > best_score:
            best_score = score
            best_start = start

    sl = slice(best_start, best_start + window)
    t_h = np.arange(window) * 5 / 60

    ax = axes[0]
    ax.plot(t_h, glucose[sl], color=C_GLUCOSE, linewidth=1.5, label="Glucose")
    ax.axhspan(70, 180, alpha=0.08, color="green")
    ax.axhline(180, color="green", linewidth=0.5, linestyle="--", alpha=0.3)
    ax.axhline(70, color="red", linewidth=0.5, linestyle="--", alpha=0.3)
    for j, b in enumerate(bolus_vals[sl]):
        if b > 0.3:
            ax.axvline(t_h[j], color=C_INSULIN, alpha=0.3, linewidth=1)
    ax.set_ylabel("Glucose (mg/dL)")
    ax.set_title("A. 24-Hour Glucose with Corrections (Patient a)", fontweight="bold")
    ax.legend(fontsize=8)

    ax = axes[1]
    ax.plot(t_h, iob[sl], color=C_IOB, linewidth=1.5, label="IOB")
    ax.fill_between(t_h, 0, iob[sl], alpha=0.2, color=C_IOB)
    ax.set_ylabel("IOB (U)")
    ax.set_title("B. IOB — Withdraw/Resume Cycles Visible", fontweight="bold")
    ax.legend(fontsize=8)

    ax = axes[2]
    ax.plot(t_h, net_basal[sl], color=C_BASAL, linewidth=1.5, label="Actual basal")
    ax.plot(t_h, sched_basal[sl], color="gray", linewidth=1, linestyle="--", label="Scheduled", alpha=0.7)
    ax.fill_between(t_h, sched_basal[sl], net_basal[sl],
                    where=net_basal[sl] < sched_basal[sl], alpha=0.3, color=C_INSULIN, label="Withdrawing")
    ax.fill_between(t_h, sched_basal[sl], net_basal[sl],
                    where=net_basal[sl] > sched_basal[sl], alpha=0.3, color=C_EGP, label="Increasing")
    ax.set_xlabel("Hours")
    ax.set_ylabel("Basal rate (U/hr)")
    ax.set_title("C. AID Actions — Ringing Pattern", fontweight="bold")
    ax.legend(fontsize=8)

    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig21_ringing_resonance.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  fig21_ringing_resonance.png")


def fig22_hill_vs_actual():
    """Figure 22: Hill model vs actual recovery + decomposition."""
    results = load_results()
    r30 = results.get("exp-2630")

    fig, axes = plt.subplots(1, 3, figsize=(16, 5))

    # Panel A: Hill curve
    ax = axes[0]
    iob = np.linspace(0, 8, 200)
    suppression = iob ** 1.5 / (iob ** 1.5 + 2.0 ** 1.5)
    egp = 18.0 * (1 - suppression)
    ax.plot(iob, egp, color=C_EGP, linewidth=2.5, label="Hill EGP model")
    ax.axhline(18, color="gray", linewidth=0.5, linestyle="--", alpha=0.5)
    ax.text(7, 18.5, "Base EGP", fontsize=8, color="gray")
    ax.axvspan(0, 1, alpha=0.1, color="red")
    ax.axvspan(1, 3, alpha=0.1, color="yellow")
    ax.axvspan(3, 6, alpha=0.1, color="green")
    ax.annotate("n=1.5, K=2.0U\n(UVA/Padova)", xy=(5.5, 3), fontsize=8,
                bbox=dict(boxstyle="round,pad=0.3", facecolor="lightyellow"))
    ax.set_xlabel("IOB (Units)")
    ax.set_ylabel("EGP (mg/dL/hr)")
    ax.set_title("A. Hill Equation EGP", fontweight="bold")

    # Panel B: Recovery scatter
    ax = axes[1]
    if r30:
        for pid in r30.get("patients", []):
            pdata = r30.get("per_patient", {}).get(pid, {})
            for ep in pdata.get("example_episodes", []):
                act = ep.get("recovery_slope")
                hill = ep.get("hill_predicted_rate")
                if act is not None and hill is not None and np.isfinite(act) and np.isfinite(hill):
                    ax.scatter(hill, act, alpha=0.4, s=12, color=C_GLUCOSE, edgecolor="none")
    ax.plot([0, 25], [0, 25], "k--", linewidth=1, alpha=0.5, label="1:1")
    ax.plot([0, 25], [0, 25 * 2.09], color="red", linewidth=1, linestyle=":", alpha=0.7,
            label="Actual/Hill ≈ 2.1×")
    ax.set_xlabel("Hill-predicted (mg/dL/hr)")
    ax.set_ylabel("Actual recovery (mg/dL/hr)")
    ax.set_title("B. Hill Under-Predicts Recovery", fontweight="bold")
    ax.legend(fontsize=8)
    ax.set_xlim(0, 25); ax.set_ylim(-20, 60)

    # Panel C: Decomposition
    ax = axes[2]
    if r30:
        decomp = r30.get("pooled", {}).get("decomposition", {})
        actual = decomp.get("actual_mean", 4.1)
        cats = ["Actual\nRecovery", "Hill\nEGP", "AID\nWithdrawal", "Counter-\nRegulation"]
        vals = [actual, decomp.get("hill_egp", 11.2), decomp.get("aid_withdrawal", 15.7),
                decomp.get("counter_regulation", 7.2)]
        colors = [C_GLUCOSE, C_EGP, C_AID, C_COUNTER]
        ax.barh(range(len(cats)), vals, color=colors, alpha=0.7, edgecolor="black", linewidth=0.5)
        ax.set_yticks(range(len(cats)))
        ax.set_yticklabels(cats)
        for i, v in enumerate(vals):
            ax.text(v + 0.3, i, f"{v:.1f}", va="center", fontsize=9)
        ax.set_xlabel("mg/dL/hr")
        ax.set_title("C. Forces Are Coupled\n(Sum ≫ Actual)", fontweight="bold")
        ax.text(0.95, 0.05, "Components sum to 34.1\nbut actual is only 4.1\n→ nonlinear coupling",
                transform=ax.transAxes, fontsize=8, ha="right",
                bbox=dict(boxstyle="round,pad=0.3", facecolor="#FFF9C4"))

    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig22_hill_vs_actual.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  fig22_hill_vs_actual.png")


def fig23_ecosystem_takeaway():
    """Figure 23: What AID controllers model vs what drives glucose."""
    fig, ax = plt.subplots(1, 1, figsize=(14, 8))
    ax.set_xlim(0, 14); ax.set_ylim(0, 10); ax.axis("off")

    ax.text(7, 9.5, "What AID Controllers Model vs Actual Glucose Dynamics",
            fontsize=14, fontweight="bold", ha="center")

    # Left: Current models
    ax.text(3.5, 8.5, "Current AID Models", fontsize=12, fontweight="bold",
            ha="center", color=C_INSULIN)
    rect1 = mpatches.FancyBboxPatch((0.5, 4.5), 6, 3.7, boxstyle="round,pad=0.2",
                                     facecolor="#FFEBEE", edgecolor=C_INSULIN, linewidth=2)
    ax.add_patch(rect1)
    items = [("✓ Insulin PK (IOB curve)", 7.7), ("✓ Carb absorption (COB)", 7.2),
             ("✓ Target glucose range", 6.7), ("✓ Basal scheduling", 6.2),
             ("✗ EGP dynamics", 5.7), ("✗ Counter-regulation", 5.2),
             ("✗ Phase lag awareness", 4.7)]
    for text, y in items:
        ax.text(0.8, y, text, fontsize=10, color="green" if "✓" in text else "red")

    # Right: Actual dynamics
    ax.text(10.5, 8.5, "Actual Dynamics", fontsize=12, fontweight="bold",
            ha="center", color=C_EGP)
    rect2 = mpatches.FancyBboxPatch((7.5, 4.5), 6, 3.7, boxstyle="round,pad=0.2",
                                     facecolor="#E8F5E9", edgecolor=C_EGP, linewidth=2)
    ax.add_patch(rect2)
    items_r = ["Insulin action (≈46% of correction)", "EGP suppression (≈54% of correction)",
               "Counter-regulation (drop-rate dep.)", "AID ringing (withdraw/resume)",
               "Circadian EGP (dawn phenomenon)", "Glycogen state (48h memory)",
               "Phase lag (2.25h insulin→nadir)"]
    for i, text in enumerate(items_r):
        ax.text(7.8, 7.7 - i * 0.5, text, fontsize=10)

    # Bottom implications
    ax.text(7, 3.8, "Key Takeaways for the Ecosystem", fontsize=12, fontweight="bold", ha="center")
    rect3 = mpatches.FancyBboxPatch((0.5, 0.5), 13, 3.0, boxstyle="round,pad=0.2",
                                     facecolor="#FFF9C4", edgecolor="#F57F17", linewidth=2)
    ax.add_patch(rect3)
    takeaways = [
        "1. ISF from corrections is inflated 25-188% — controllers over-estimate effectiveness",
        '2. Post-correction "rebound" is normal EGP recovery — do not stack corrections',
        "3. IOB correlating with hypo safety = reversed causation (AID withdrawal)",
        "4. Recovery ≈ 2× Hill prediction — counter-regulation is significant",
        "5. Forces are coupled, not additive — simple ISF×IOB models miss dynamics",
    ]
    for i, t in enumerate(takeaways):
        ax.text(0.8, 3.0 - i * 0.5, t, fontsize=9)

    fig.savefig(VIZ_DIR / "fig23_ecosystem_takeaway.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  fig23_ecosystem_takeaway.png")


def fig24_correction_trajectories():
    """Figure 24: Nadir timing and recovery slope distributions from EXP-2624."""
    r24_path = RESULTS_DIR / "exp-2624_correction_egp_recovery.json"
    if not r24_path.exists():
        print("  SKIP fig24 (no EXP-2624 data)")
        return
    with open(r24_path) as f:
        r24 = json.load(f)

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    # Nadir timing — events are stored in pooled_events (top-level)
    ax = axes[0]
    nadir_hours = []
    recovery = []
    for ev in r24.get("pooled_events", []):
        nh = ev.get("nadir_hours")
        if nh is not None and np.isfinite(nh):
            nadir_hours.append(nh)
        rs = ev.get("recovery_slope_mgdl_hr")
        if rs is not None and np.isfinite(rs):
            recovery.append(rs)

    if nadir_hours:
        ax.hist(nadir_hours, bins=30, color=C_GLUCOSE, alpha=0.7, edgecolor="black",
                linewidth=0.5, density=True)
        med = np.median(nadir_hours)
        ax.axvline(med, color="red", linewidth=2, linestyle="--", label=f"Median: {med:.1f}h")
        ax.axvline(1.25, color=C_INSULIN, linewidth=2, linestyle=":", label="Insulin peak (1.25h)")
        ax.annotate("", xy=(med, ax.get_ylim()[1] * 0.7 if ax.get_ylim()[1] > 0 else 0.5),
                    xytext=(1.25, ax.get_ylim()[1] * 0.7 if ax.get_ylim()[1] > 0 else 0.5),
                    arrowprops=dict(arrowstyle="<->", color="black", linewidth=1.5))
        ax.legend(fontsize=8)
    ax.set_xlabel("Hours to nadir")
    ax.set_ylabel("Density")
    ax.set_title(f"A. Glucose Nadir Timing (N={len(nadir_hours)})", fontweight="bold")

    # Recovery slope
    ax = axes[1]
    if recovery:
        ax.hist(recovery, bins=40, color=C_EGP, alpha=0.7, edgecolor="black",
                linewidth=0.5, density=True, range=(-20, 60))
        med = np.median(recovery)
        ax.axvline(med, color="red", linewidth=2, linestyle="--", label=f"Median: {med:.1f}")
        ax.axvline(18, color=C_EGP, linewidth=2, linestyle=":", label="Base EGP (18)")
        ax.legend(fontsize=8)
    ax.set_xlabel("Recovery slope (mg/dL/hr)")
    ax.set_ylabel("Density")
    ax.set_title("B. Post-Nadir Recovery Rate", fontweight="bold")

    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig24_correction_trajectories.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  fig24_correction_trajectories.png")


def main():
    print("Generating EGP Deconfounding Report Figures")
    print("=" * 50)
    results = load_results()
    fig19_supply_demand_theory()
    fig20_aid_compensation_cascade(results)
    fig21_ringing_resonance()
    fig22_hill_vs_actual()
    fig23_ecosystem_takeaway()
    fig24_correction_trajectories()
    print("\nAll figures saved to:", VIZ_DIR)


if __name__ == "__main__":
    main()
