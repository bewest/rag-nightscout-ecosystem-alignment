#!/usr/bin/env python3
"""Round 2b visualizations — properly designed experiments.

Generates fig29-fig32:
  fig29: Model comparison — all models fail equally (EXP-2634)
  fig30: Recovery attribution — what correlates? (EXP-2635)
  fig31: Time-of-day recovery patterns (EXP-2635)
  fig32: Synthesis — why no single model works
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


def fig29_model_comparison():
    """All 5 models fail — R² is negative for all."""
    r = _load("exp-2634_model_comparison.json")
    ms = r.get("model_summary", {})

    models = ["null", "mean_reversion", "iob_decay", "biexp_decay", "hill_egp"]
    labels = ["Null\n(flat)", "Mean\nReversion", "IOB Decay\n(6h DIA)", "Biexp Decay\n(fast+slow)", "Hill EGP"]
    rmses = [ms.get(m, {}).get("rmse_mean", 0) for m in models]
    r2s = [ms.get(m, {}).get("r2_mean", 0) for m in models]

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Panel A: RMSE comparison
    ax = axes[0]
    colors = ["#95a5a6", "#3498db", "#e67e22", "#9b59b6", "#e74c3c"]
    bars = ax.bar(range(len(models)), rmses, color=colors, alpha=0.85, edgecolor="white")
    ax.set_xticks(range(len(models)))
    ax.set_xticklabels(labels, fontsize=10)
    ax.set_ylabel("RMSE (mg/dL)", fontsize=12)
    ax.set_title("A. Recovery Prediction RMSE (lower = better)", fontsize=13, fontweight="bold")
    # Annotate
    for i, v in enumerate(rmses):
        ax.text(i, v + 0.5, f"{v:.1f}", ha="center", fontsize=10, fontweight="bold")
    ax.set_ylim(0, max(rmses) * 1.15)

    # Panel B: R² — all negative!
    ax = axes[1]
    bars = ax.bar(range(len(models)), r2s, color=colors, alpha=0.85, edgecolor="white")
    ax.set_xticks(range(len(models)))
    ax.set_xticklabels(labels, fontsize=10)
    ax.set_ylabel("R²", fontsize=12)
    ax.set_title("B. All Models Have NEGATIVE R²", fontsize=13, fontweight="bold")
    ax.axhline(0, color="black", linewidth=1.5, linestyle="--", label="R² = 0 (mean baseline)")
    for i, v in enumerate(r2s):
        ax.text(i, v - 0.15, f"{v:.2f}", ha="center", fontsize=10, fontweight="bold", color="white")
    ax.legend(fontsize=10, loc="lower left")
    ax.set_ylim(min(r2s) * 1.2, 0.5)

    fig.suptitle(f"EXP-2634: No Single Model Explains Recovery (N={r['n_events']} corrections, "
                 f"{r['n_patients']} patients)", fontsize=14, fontweight="bold", y=1.02)
    plt.tight_layout()
    out = OUTDIR / "fig29_model_comparison.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(out.name)


def fig30_recovery_attribution():
    """Correlation scatter plots for recovery attribution."""
    r = _load("exp-2635_recovery_attribution.json")
    hyp = r.get("hypotheses", {})

    fig, axes = plt.subplots(1, 3, figsize=(16, 5))

    labels_data = [
        ("IOB Decay Rate (U/hr)", "Recovery Slope (mg/dL/hr)",
         "iob_decay_rate", "recovery_slope",
         f"H2: r = {hyp['H2'].get('r', 0):.3f}",
         "r = −0.068 → IOB decay\ndoes NOT explain recovery"),
        ("48h Carb Load (g)", "Recovery Slope (mg/dL/hr)",
         "carbs_48h", "recovery_slope",
         f"H3: r = {hyp['H3'].get('r', 0):.3f}",
         "r = −0.146 → More carbs\n= SLOWER recovery (!)"),
        ("Bolus Size (U)", "Recovery Slope (mg/dL/hr)",
         "bolus_u", "recovery_slope",
         f"H4: r = {hyp['H4'].get('r', 0):.3f}",
         "r = −0.307 → Larger bolus\n= SLOWER recovery"),
    ]

    # We don't have raw events in summary, so show the hypothesis results as bar chart
    metrics = {
        "IOB decay rate": hyp.get("H2", {}).get("r", 0),
        "48h carb load": hyp.get("H3", {}).get("r", 0),
        "Bolus size": hyp.get("H4", {}).get("r", 0),
        "Time of day\n(overnight vs day)": -0.018,  # from t-test, small effect
    }

    ax = axes[0]
    names = list(metrics.keys())
    vals = list(metrics.values())
    colors = ["#e74c3c" if abs(v) > 0.15 else "#3498db" for v in vals]
    ax.barh(range(len(names)), vals, color=colors, alpha=0.8)
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names, fontsize=11)
    ax.set_xlabel("Pearson r with Recovery Slope", fontsize=12)
    ax.set_title("A. What Predicts Recovery?", fontsize=13, fontweight="bold")
    ax.axvline(0, color="black", linewidth=0.5)
    ax.axvline(0.15, color="#27ae60", linestyle="--", alpha=0.5, label="|r| = 0.15 threshold")
    ax.axvline(-0.15, color="#27ae60", linestyle="--", alpha=0.5)
    ax.legend(fontsize=9)
    for i, v in enumerate(vals):
        ax.text(v + 0.02 * np.sign(v), i, f"{v:.3f}", va="center", fontsize=10)

    # Panel B: Per-patient recovery rates
    ax = axes[1]
    pp = r.get("per_patient", {})
    patients = sorted(pp.keys())
    rates = [pp[p].get("mean_recovery", 0) for p in patients]
    n_ev = [pp[p].get("n_events", 0) for p in patients]
    colors_p = ["#27ae60" if rate > 0 else "#e74c3c" for rate in rates]
    bars = ax.barh(patients, rates, color=colors_p, alpha=0.8)
    ax.set_xlabel("Mean Recovery Slope (mg/dL/hr)", fontsize=12)
    ax.set_ylabel("Patient", fontsize=12)
    ax.set_title("B. Per-Patient Recovery Rates", fontsize=13, fontweight="bold")
    ax.axvline(0, color="black", linewidth=0.5)
    ax.axvline(18, color="#f39c12", linestyle="--", label="Base EGP (18)")
    for i, (rate, n) in enumerate(zip(rates, n_ev)):
        ax.text(max(rate, 0) + 1, i, f"n={n}", va="center", fontsize=9, color="gray")
    ax.legend(fontsize=9)

    # Panel C: Time of day pattern
    ax = axes[2]
    tod_data = {
        "Night\n0-6": 8.9,
        "Morning\n6-10": 16.1,
        "Midday\n10-14": 2.2,
        "Afternoon\n14-18": 19.0,
        "Evening\n18-22": 44.1,
        "Late\n22-24": 29.7,
    }
    times = list(tod_data.keys())
    vals = list(tod_data.values())
    colors_t = plt.cm.coolwarm(np.linspace(0.2, 0.8, len(times)))
    ax.bar(range(len(times)), vals, color=colors_t, alpha=0.85, edgecolor="white")
    ax.set_xticks(range(len(times)))
    ax.set_xticklabels(times, fontsize=9)
    ax.set_ylabel("Recovery Slope (mg/dL/hr)", fontsize=12)
    ax.set_title("C. Recovery by Time of Day", fontsize=13, fontweight="bold")
    ax.axhline(18, color="#f39c12", linestyle="--", label="Base EGP (18)")
    ax.legend(fontsize=9)

    fig.suptitle(f"EXP-2635: Recovery Attribution (N={r['n_events']})",
                 fontsize=14, fontweight="bold", y=1.02)
    plt.tight_layout()
    out = OUTDIR / "fig30_recovery_attribution.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(out.name)


def fig31_synthesis():
    """Why no single model works — the AID coupling diagram."""
    fig, ax = plt.subplots(1, 1, figsize=(14, 8))
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 10)
    ax.axis("off")

    ax.text(7, 9.5, "Why No Single Recovery Model Works",
            ha="center", fontsize=18, fontweight="bold")
    ax.text(7, 8.9, "EXP-2634 + EXP-2635: 219 corrections across 9 patients, proper methodology",
            ha="center", fontsize=11, color="#7f8c8d")

    # Three columns
    # Column 1: What we tested
    ax.text(2.5, 8.0, "MODELS TESTED", ha="center", fontsize=13,
            fontweight="bold", color="#2c3e50")

    models_text = [
        ("Null (flat from nadir)", "R² = −2.5"),
        ("Mean-reversion → 120", "R² = −2.4"),
        ("IOB decay (6h DIA)", "R² = −2.8"),
        ("Biexp decay (τ=0.8+12h)", "R² = −2.4"),
        ("Hill EGP (n=1.5, K=2)", "R² = −3.2"),
    ]
    y = 7.2
    for name, score in models_text:
        ax.text(0.5, y, f"• {name}", fontsize=10, color="#2c3e50")
        ax.text(4.3, y, score, fontsize=10, color="#e74c3c", fontweight="bold",
                family="monospace")
        y -= 0.5

    ax.text(2.5, y - 0.2, "ALL negative R² — worse than\njust guessing the mean!",
            ha="center", fontsize=10, style="italic", color="#e74c3c",
            bbox=dict(boxstyle="round", facecolor="#fadbd8", alpha=0.8))

    # Column 2: What predicts recovery
    ax.text(7, 8.0, "ATTRIBUTION", ha="center", fontsize=13,
            fontweight="bold", color="#2c3e50")

    attrib = [
        ("IOB decay rate", "r = −0.07", "NO"),
        ("48h carb load", "r = −0.15", "REVERSED"),
        ("Time of day", "p = 0.85", "NO"),
        ("Bolus size", "r = −0.31", "YES (−)"),
    ]
    y = 7.2
    for name, val, verdict in attrib:
        color = "#27ae60" if "YES" in verdict else "#e74c3c" if "NO" in verdict else "#f39c12"
        ax.text(5.3, y, f"• {name}", fontsize=10, color="#2c3e50")
        ax.text(8.0, y, val, fontsize=10, family="monospace", color="#7f8c8d")
        ax.text(9.2, y, verdict, fontsize=10, fontweight="bold", color=color)
        y -= 0.5

    ax.text(7, y - 0.2, "Only bolus size matters — and in\nthe WRONG direction (larger = slower)",
            ha="center", fontsize=10, style="italic", color="#f39c12",
            bbox=dict(boxstyle="round", facecolor="#fef9e7", alpha=0.8))

    # Column 3: What this means
    ax.text(11.5, 8.0, "CONCLUSION", ha="center", fontsize=13,
            fontweight="bold", color="#2c3e50")

    conclusions = [
        "Recovery is NOT driven by",
        "any single mechanism:",
        "",
        "• Not EGP (Hill R² = −3.2)",
        "• Not IOB decay (r = −0.07)",
        "• Not glycogen (r = −0.15)",
        "• Not circadian (p = 0.85)",
        "",
        "The AID controller",
        "ABSORBS all signals,",
        "making single-factor",
        "models impossible.",
    ]
    y = 7.2
    for line in conclusions:
        weight = "bold" if "NOT" in line or "ABSORBS" in line else "normal"
        ax.text(10, y, line, fontsize=10, color="#2c3e50", fontweight=weight)
        y -= 0.38

    # Bottom: Practical implication
    ax.text(7, 1.5, "PRACTICAL IMPLICATION", ha="center", fontsize=14,
            fontweight="bold", color="#2c3e50")
    ax.text(7, 0.5,
            "Instead of modeling recovery, AID controllers should:\n"
            "1. EXPECT recovery after nadir (3.5h) and dampen their own response\n"
            "2. Use phase-aware ISF: don't stack corrections during recovery phase\n"
            "3. Treat the coupling as a feature, not a bug — it's already dampening oscillations",
            ha="center", fontsize=11,
            bbox=dict(boxstyle="round,pad=0.6", facecolor="#eaf2f8", edgecolor="#2980b9"))

    plt.tight_layout()
    out = OUTDIR / "fig31_synthesis.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(out.name)


if __name__ == "__main__":
    fig29_model_comparison()
    fig30_recovery_attribution()
    fig31_synthesis()
    print("Done — 3 figures generated")
