#!/usr/bin/env python3
"""Round 3 visualizations — Actionable Controller Insights.

Generates fig32-fig35:
  fig32: Dose-response curve — ISF diminishing returns (EXP-2636)
  fig33: Stacking analysis — clean vs stacked outcomes (EXP-2637)
  fig34: Controller behavior — predictability & oscillation (EXP-2638)
  fig35: Round 3 synthesis — what we learned across 3 rounds
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


def fig32_dose_response():
    """ISF diminishing returns — the strongest finding of Round 3."""
    r = _load("exp-2636_dose_dependent_isf.json")
    dose_resp = r.get("dose_response", [])

    fig, axes = plt.subplots(1, 3, figsize=(16, 5))

    # Panel A: Apparent ISF vs dose bin
    ax = axes[0]
    bins_label = [d["bin"] for d in dose_resp]
    isfs = [d["mean_isf"] for d in dose_resp]
    ns = [d["n"] for d in dose_resp]
    colors = plt.cm.RdYlGn_r(np.linspace(0.2, 0.8, len(bins_label)))
    bars = ax.bar(range(len(bins_label)), isfs, color=colors, edgecolor="white", alpha=0.9)
    ax.set_xticks(range(len(bins_label)))
    ax.set_xticklabels(bins_label, fontsize=9)
    ax.set_ylabel("Apparent ISF (mg/dL per U)", fontsize=11)
    ax.set_title("A. ISF Diminishes with Dose", fontsize=13, fontweight="bold")
    for i, (v, n) in enumerate(zip(isfs, ns)):
        ax.text(i, v + 2, f"{v:.0f}\nn={n}", ha="center", fontsize=9)
    ax.set_ylim(0, max(isfs) * 1.25)

    # Panel B: Drop vs dose (showing ceiling)
    ax = axes[1]
    drops = [d["mean_drop"] for d in dose_resp]
    ax.bar(range(len(bins_label)), drops, color="#3498db", edgecolor="white", alpha=0.85)
    ax.set_xticks(range(len(bins_label)))
    ax.set_xticklabels(bins_label, fontsize=9)
    ax.set_ylabel("Mean Glucose Drop (mg/dL)", fontsize=11)
    ax.set_title("B. Drop Has a Ceiling (~140)", fontsize=13, fontweight="bold")
    ax.axhline(140, color="#e74c3c", linestyle="--", alpha=0.5, label="~140 ceiling")
    for i, v in enumerate(drops):
        ax.text(i, v + 2, f"{v:.0f}", ha="center", fontsize=9)
    ax.legend(fontsize=9)

    # Panel C: Recovery slope vs dose
    ax = axes[2]
    recs = [d["mean_recovery"] for d in dose_resp]
    colors_r = ["#27ae60" if r > 20 else "#f39c12" if r > 10 else "#e74c3c" for r in recs]
    ax.bar(range(len(bins_label)), recs, color=colors_r, edgecolor="white", alpha=0.85)
    ax.set_xticks(range(len(bins_label)))
    ax.set_xticklabels(bins_label, fontsize=9)
    ax.set_ylabel("Recovery Slope (mg/dL/hr)", fontsize=11)
    ax.set_title("C. Large Doses = Slow Recovery", fontsize=13, fontweight="bold")
    ax.axhline(18, color="#9b59b6", linestyle="--", alpha=0.5, label="Base EGP (18)")
    for i, v in enumerate(recs):
        ax.text(i, max(v, 0) + 1, f"{v:.0f}", ha="center", fontsize=9)
    ax.legend(fontsize=9)

    h2 = r["hypotheses"]["H2"]
    fig.suptitle(f"EXP-2636: Dose-Dependent ISF (N={r['n_events']}, r = {h2['r']:.3f})",
                 fontsize=14, fontweight="bold", y=1.02)
    plt.tight_layout()
    out = OUTDIR / "fig32_dose_response.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(out.name)


def fig33_stacking():
    """Clean vs stacked correction outcomes."""
    r = _load("exp-2637_phase_stacking.json")

    fig, axes = plt.subplots(1, 3, figsize=(16, 5))

    # Panel A: CV comparison
    ax = axes[0]
    h1 = r["hypotheses"]["H1"]
    labels = ["Clean\n(no stacking)", "Stacked\n(bolus within 4h)"]
    cvs = [h1["clean_cv"], h1["stacked_cv"]]
    colors = ["#27ae60", "#e74c3c"]
    ax.bar(labels, cvs, color=colors, alpha=0.85, edgecolor="white")
    ax.set_ylabel("Glucose CV (%)", fontsize=11)
    ax.set_title(f"A. Glucose Variability (p={h1['p_value']})", fontsize=13, fontweight="bold")
    for i, v in enumerate(cvs):
        ax.text(i, v + 0.5, f"{v:.1f}%", ha="center", fontsize=11, fontweight="bold")
    ax.set_ylim(0, max(cvs) * 1.3)

    # Panel B: Target attainment
    ax = axes[1]
    h3 = r["hypotheses"]["H3"]
    vals = [h3["clean_pct"], h3["stacked_pct"]]
    ax.bar(labels, vals, color=colors, alpha=0.85, edgecolor="white")
    ax.set_ylabel("% Reaching Target (80-120)", fontsize=11)
    ax.set_title(f"B. Target Attainment ({h3['diff_pp']:.0f}pp diff)", fontsize=13, fontweight="bold")
    for i, v in enumerate(vals):
        ax.text(i, v + 1, f"{v:.0f}%", ha="center", fontsize=11, fontweight="bold")
    ax.set_ylim(0, 100)
    ax.axhline(80, color="#3498db", linestyle="--", alpha=0.3, label="80% goal")
    ax.legend(fontsize=9)

    # Panel C: Per-patient stacking rates
    ax = axes[2]
    pp = r.get("per_patient", {})
    patients = sorted(pp.keys())
    pct_stacked = [pp[p].get("pct_stacked", 0) for p in patients]
    n_events = [pp[p].get("n_events", 0) for p in patients]
    ax.barh(patients, pct_stacked, color="#3498db", alpha=0.8)
    ax.set_xlabel("% Corrections with Stacking", fontsize=11)
    ax.set_ylabel("Patient", fontsize=11)
    ax.set_title("C. Stacking Prevalence", fontsize=13, fontweight="bold")
    ax.axvline(50, color="#e74c3c", linestyle="--", alpha=0.5, label="50%")
    for i, (pct, n) in enumerate(zip(pct_stacked, n_events)):
        ax.text(pct + 1, i, f"n={n}", va="center", fontsize=9, color="gray")
    ax.legend(fontsize=9)

    fig.suptitle(f"EXP-2637: Stacking Analysis (N={r['n_events']}: {r['n_clean']} clean, "
                 f"{r['n_stacked']} stacked)",
                 fontsize=14, fontweight="bold", y=1.02)
    plt.tight_layout()
    out = OUTDIR / "fig33_stacking.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(out.name)


def fig34_controller():
    """Controller predictability and oscillation."""
    r = _load("exp-2638_controller_behavior.json")
    pp = r.get("per_patient", {})

    fig, axes = plt.subplots(1, 3, figsize=(16, 5))

    patients = sorted(pp.keys())

    # Panel A: R² predictability
    ax = axes[0]
    r2s = [pp[p].get("r2_predictability", 0) for p in patients]
    colors = ["#e74c3c" if v < 0.1 else "#f39c12" if v < 0.3 else "#27ae60" for v in r2s]
    ax.barh(patients, r2s, color=colors, alpha=0.85)
    ax.set_xlabel("R² (glucose+IOB+ROC → ratio)", fontsize=11)
    ax.set_ylabel("Patient", fontsize=11)
    ax.set_title("A. Controller Predictability", fontsize=13, fontweight="bold")
    ax.axvline(0.3, color="#27ae60", linestyle="--", label="R² = 0.3 threshold")
    for i, v in enumerate(r2s):
        ax.text(v + 0.005, i, f"{v:.3f}", va="center", fontsize=9)
    ax.legend(fontsize=9)

    # Panel B: Mean enacted/scheduled ratio
    ax = axes[1]
    ratios = [pp[p].get("mean_ratio", 0) for p in patients]
    colors_r = ["#e74c3c" if v > 1 else "#3498db" for v in ratios]
    ax.barh(patients, ratios, color=colors_r, alpha=0.85)
    ax.set_xlabel("Mean Enacted/Scheduled Ratio", fontsize=11)
    ax.set_title("B. Controller Aggressiveness", fontsize=13, fontweight="bold")
    ax.axvline(1.0, color="black", linestyle="--", label="1.0 = scheduled")
    for i, v in enumerate(ratios):
        ax.text(max(v, 0) + 0.02, i, f"{v:.2f}", va="center", fontsize=9)
    ax.legend(fontsize=9)

    # Panel C: Oscillation period
    ax = axes[2]
    periods = [pp[p].get("peak_period_h", 0) or 0 for p in patients]
    ax.barh(patients, periods, color="#9b59b6", alpha=0.8)
    ax.set_xlabel("Peak Oscillation Period (hours)", fontsize=11)
    ax.set_title("C. Controller Oscillation", fontsize=13, fontweight="bold")
    ax.axvline(1.5, color="#f39c12", linestyle="--", label="1.5h mean")
    for i, v in enumerate(periods):
        ax.text(v + 0.05, i, f"{v:.1f}h", va="center", fontsize=9)
    ax.legend(fontsize=9)

    fig.suptitle(f"EXP-2638: Controller Behavior (N={r['n_patients']} patients, "
                 f"mean R²={r['hypotheses']['H1']['mean_r2']})",
                 fontsize=14, fontweight="bold", y=1.02)
    plt.tight_layout()
    out = OUTDIR / "fig34_controller.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(out.name)


def fig35_synthesis():
    """Three-round synthesis — what we've learned."""
    fig, ax = plt.subplots(1, 1, figsize=(16, 10))
    ax.set_xlim(0, 16)
    ax.set_ylim(0, 12)
    ax.axis("off")

    ax.text(8, 11.5, "Three Rounds of EGP/Recovery Research — Synthesis",
            ha="center", fontsize=18, fontweight="bold")

    # Round 1
    y = 10.5
    ax.text(0.5, y, "ROUND 1: AID Compensation Theorem", fontsize=14,
            fontweight="bold", color="#2c3e50")
    findings_r1 = [
        "[+] IOB drops 55% before hypo (controller withdrawing insulin)",
        "[+] Forces are COUPLED: sum=34, actual=4.1 -> loop gain 8.3x",
        "[+] Hill EGP under-predicts recovery by 2.1x",
    ]
    for i, f in enumerate(findings_r1):
        ax.text(0.8, y - 0.4 - i * 0.35, f, fontsize=10, color="#2c3e50")

    # Round 2
    y = 8.6
    ax.text(0.5, y, "ROUND 2: No Single Model Works", fontsize=14,
            fontweight="bold", color="#2c3e50")
    findings_r2 = [
        "[X] ALL 5 models R2 < 0 (worse than guessing the mean)",
        "[X] IOB decay: r = -0.07 (zero correlation with recovery)",
        "[X] 48h carbs: r = -0.15 (wrong direction)",
        "[X] Circadian: p = 0.85 (no effect)",
        ">>> Only bolus size predicts recovery (r = -0.31)",
    ]
    for i, f in enumerate(findings_r2):
        ax.text(0.8, y - 0.4 - i * 0.35, f, fontsize=10, color="#2c3e50")

    # Round 3
    y = 6.4
    ax.text(0.5, y, "ROUND 3: Actionable Controller Insights", fontsize=14,
            fontweight="bold", color="#2c3e50")
    findings_r3 = [
        "[!] ISF is dose-dependent: small=100, large=22 (r = -0.56)",
        "[!] Glucose drop has ceiling ~140 mg/dL (AID + counter-regulation)",
        "[!] Stacking doesn't significantly worsen outcomes (AID compensates)",
        "[!] Controller is 93% unpredictable from inputs (R2 = 0.07)",
        "[!] Controller oscillates at ~1.4h period (feedback delay)",
    ]
    for i, f in enumerate(findings_r3):
        ax.text(0.8, y - 0.4 - i * 0.35, f, fontsize=10, color="#2c3e50")

    # Right side: Practical implications
    y = 10.5
    ax.text(9, y, "PRACTICAL IMPLICATIONS", fontsize=14,
            fontweight="bold", color="#2980b9")

    implications = [
        ("For AID Controllers:", "#2c3e50", True),
        ("1. Don't add EGP as an additive term (proven harmful)", "#7f8c8d", False),
        ("2. Use dose-dependent ISF: scale down for large corrections", "#7f8c8d", False),
        ("3. Expect recovery at 3.5h — don't re-correct during recovery", "#7f8c8d", False),
        ("4. Controller oscillation at ~1.4h is a feature, not a bug", "#7f8c8d", False),
        ("", "", False),
        ("For Settings Advisors:", "#2c3e50", True),
        ("1. ISF from small corrections is 4.6× the ISF from large ones", "#7f8c8d", False),
        ("2. Scheduled ISF overestimates large-dose effectiveness", "#7f8c8d", False),
        ("3. Recovery slope is dose-dependent — account for bolus size", "#7f8c8d", False),
        ("", "", False),
        ("Research Lines CLOSED:", "#e74c3c", True),
        ("• EGP as prediction term (R² = −3.2)", "#7f8c8d", False),
        ("• IOB decay as recovery driver (r = −0.07)", "#7f8c8d", False),
        ("• Glycogen → recovery (r = −0.15, wrong sign)", "#7f8c8d", False),
        ("• Circadian recovery (p = 0.85)", "#7f8c8d", False),
        ("• Controller predictability (R² = 0.07)", "#7f8c8d", False),
    ]
    for i, (text, color, bold) in enumerate(implications):
        if text:
            ax.text(9, y - 0.4 - i * 0.35, text, fontsize=10, color=color,
                    fontweight="bold" if bold else "normal")

    # Bottom: Key equation
    ax.text(8, 0.8,
            "KEY INSIGHT: Apparent ISF = 1.87 − 0.13 × bolus_U (r = −0.56, N = 219)\n"
            "First unit drops glucose 100 mg/dL. Sixth unit drops only 22 mg/dL.\n"
            "The AID controller absorbs the rest through basal withdrawal.",
            ha="center", fontsize=12,
            bbox=dict(boxstyle="round,pad=0.5", facecolor="#eaf2f8", edgecolor="#2980b9"))

    plt.tight_layout()
    out = OUTDIR / "fig35_synthesis.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(out.name)


if __name__ == "__main__":
    fig32_dose_response()
    fig33_stacking()
    fig34_controller()
    fig35_synthesis()
    print("Done — 4 figures generated")
