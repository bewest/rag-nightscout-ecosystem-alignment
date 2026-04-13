#!/usr/bin/env python3
"""Visualizations for EXP-2629: Hill Fitting, ODC Validation, Sticky Hypers.

Figures:
 fig15: Per-patient Hill curves (fitted vs population)
 fig16: ODC validation — overnight drift vs IOB@midnight
 fig17: Sticky hyper EGP signature (IOB vs glucose roc)
 fig18: Cross-population Hill K distribution
"""

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

RESULTS = Path("externals/experiments/exp-2629_hill_fitting.json")
OUTDIR = Path("visualizations/egp-phase-research")
OUTDIR.mkdir(parents=True, exist_ok=True)


def _load():
    with open(RESULTS) as f:
        return json.load(f)


def fig15_hill_curves(data):
    """Per-patient Hill suppression curves vs population."""
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    fig.suptitle("Fig 15: Per-Patient Hill Suppression Curves vs Population",
                 fontsize=14, fontweight="bold")

    iob_range = np.linspace(0, 12, 200)

    # Population curve
    pop_n, pop_k = 1.5, 2.0
    pop_supp = iob_range ** pop_n / (iob_range ** pop_n + pop_k ** pop_n)

    fits = data.get("hill_fits", {})
    fitted = {k: v for k, v in fits.items() if "error" not in v}

    # Top-left: All patient curves
    ax = axes[0, 0]
    ax.plot(iob_range, pop_supp * 100, "k--", linewidth=3, label="Population", alpha=0.8)
    ns_patients = {k: v for k, v in fitted.items() if not k.startswith("odc")}
    odc_patients = {k: v for k, v in fitted.items() if k.startswith("odc")}
    for pid, f in ns_patients.items():
        n, k = f["hill_n"], f["hill_k"]
        supp = iob_range ** n / (iob_range ** n + k ** n)
        ax.plot(iob_range, supp * 100, "-", alpha=0.6, label=f"NS-{pid}")
    for pid, f in odc_patients.items():
        n, k = f["hill_n"], f["hill_k"]
        supp = iob_range ** n / (iob_range ** n + k ** n)
        ax.plot(iob_range, supp * 100, "--", alpha=0.6, label=pid[:10])
    ax.set_xlabel("IOB (U)")
    ax.set_ylabel("EGP Suppression (%)")
    ax.set_title("All Patients")
    ax.legend(fontsize=7, ncol=2)
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 100)
    ax.grid(True, alpha=0.3)

    # Top-right: Hill K distribution
    ax = axes[0, 1]
    ns_ks = [f["hill_k"] for k, f in fitted.items() if not k.startswith("odc")]
    odc_ks = [f["hill_k"] for k, f in fitted.items() if k.startswith("odc")]
    all_ks = ns_ks + odc_ks
    labels = ([k for k in fitted if not k.startswith("odc")] +
              [k[:10] for k in fitted if k.startswith("odc")])
    colors = (["steelblue"] * len(ns_ks) + ["coral"] * len(odc_ks))
    bars = ax.barh(range(len(all_ks)), all_ks, color=colors)
    ax.set_yticks(range(len(all_ks)))
    ax.set_yticklabels(labels, fontsize=8)
    ax.axvline(pop_k, color="black", linestyle="--", label=f"Pop K={pop_k}")
    ax.set_xlabel("Hill K (U)")
    ax.set_title("Half-Max IOB by Patient")
    ax.legend()
    ax.grid(True, alpha=0.3, axis="x")

    # Bottom-left: Hill n distribution
    ax = axes[1, 0]
    ns_ns = [f["hill_n"] for k, f in fitted.items() if not k.startswith("odc")]
    odc_ns = [f["hill_n"] for k, f in fitted.items() if k.startswith("odc")]
    all_ns = ns_ns + odc_ns
    ax.barh(range(len(all_ns)), all_ns, color=colors)
    ax.set_yticks(range(len(all_ns)))
    ax.set_yticklabels(labels, fontsize=8)
    ax.axvline(pop_n, color="black", linestyle="--", label=f"Pop n={pop_n}")
    ax.set_xlabel("Hill Coefficient (n)")
    ax.set_title("Cooperativity by Patient")
    ax.legend()
    ax.grid(True, alpha=0.3, axis="x")

    # Bottom-right: R² and RMSE improvement
    ax = axes[1, 1]
    r2s = [f["r2"] for f in fitted.values()]
    imprs = [f["rmse_improvement_pct"] for f in fitted.values()]
    ax.scatter(r2s, imprs, c=colors, s=100, edgecolors="black", zorder=5)
    for i, lbl in enumerate(labels):
        ax.annotate(lbl, (r2s[i], imprs[i]), fontsize=7,
                    xytext=(5, 5), textcoords="offset points")
    ax.set_xlabel("R² (fit quality)")
    ax.set_ylabel("RMSE Improvement vs Population (%)")
    ax.set_title("Fit Quality (Low R² = noisy data)")
    ax.axhline(0, color="gray", linestyle="--", alpha=0.5)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(OUTDIR / "fig15_hill_curves.png", dpi=150)
    plt.close()
    print("  ✓ fig15_hill_curves.png")


def fig16_odc_validation(data):
    """ODC validation — overnight drift correlations."""
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    fig.suptitle("Fig 16: ODC Validation — IOB@Midnight Predicts Overnight Drift",
                 fontsize=14, fontweight="bold")

    drift = data.get("drift_validation", {})

    # Left: bar chart of correlations
    ax = axes[0]
    patients = sorted(drift.keys())
    iob_rs = [drift[p]["r_iob_drift"] if not np.isnan(drift[p].get("r_iob_drift", np.nan)) else 0
              for p in patients]
    carb_rs = [drift[p]["r_carbs_drift"] for p in patients]
    x = np.arange(len(patients))
    w = 0.35
    colors_iob = ["coral" if p.startswith("odc") else "steelblue" for p in patients]
    colors_carb = ["lightsalmon" if p.startswith("odc") else "lightsteelblue" for p in patients]
    ax.bar(x - w / 2, [abs(r) for r in iob_rs], w, color=colors_iob, label="IOB@midnight")
    ax.bar(x + w / 2, [abs(r) for r in carb_rs], w, color=colors_carb, label="48h carbs")
    ax.set_xticks(x)
    ax.set_xticklabels([p[:10] for p in patients], fontsize=8, rotation=45, ha="right")
    ax.set_ylabel("|r|")
    ax.set_title("Drift Predictor: IOB vs Carbs")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3, axis="y")

    # Middle: nights available
    ax = axes[1]
    nights = [drift[p]["n_nights"] for p in patients]
    ax.bar(x, nights, color=colors_iob)
    ax.set_xticks(x)
    ax.set_xticklabels([p[:10] for p in patients], fontsize=8, rotation=45, ha="right")
    ax.set_ylabel("Clean Fasting Nights")
    ax.set_title("Data Availability")
    ax.grid(True, alpha=0.3, axis="y")

    # Right: drift distributions
    ax = axes[2]
    drifts = [drift[p]["drift_mean"] for p in patients]
    stds = [drift[p]["drift_std"] for p in patients]
    ax.barh(x, drifts, xerr=stds, color=colors_iob, capsize=3)
    ax.set_yticks(x)
    ax.set_yticklabels([p[:10] for p in patients], fontsize=8)
    ax.axvline(0, color="gray", linestyle="--", alpha=0.5)
    ax.set_xlabel("Overnight Drift (mg/dL/hr)")
    ax.set_title("Mean ± SD Drift")
    ax.grid(True, alpha=0.3, axis="x")

    plt.tight_layout()
    plt.savefig(OUTDIR / "fig16_odc_validation.png", dpi=150)
    plt.close()
    print("  ✓ fig16_odc_validation.png")


def fig17_sticky_hypers(data):
    """Sticky hyper analysis: IOB ratio vs glucose behavior."""
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    fig.suptitle("Fig 17: Sticky Hypers — High IOB But Glucose Won't Drop",
                 fontsize=14, fontweight="bold")

    sticky = data.get("sticky_hypers", {})
    if not sticky:
        return

    patients = sorted(sticky.keys())
    n = len(patients)
    x = np.arange(n)
    colors = ["coral" if p.startswith("odc") else "steelblue" for p in patients]

    # Left: IOB ratio (sticky vs normal)
    ax = axes[0]
    ratios = [sticky[p]["sticky_iob_mean"] / max(sticky[p]["normal_iob_mean"], 0.01)
              for p in patients]
    ax.bar(x, ratios, color=colors)
    ax.set_xticks(x)
    ax.set_xticklabels([p[:10] for p in patients], fontsize=7, rotation=45, ha="right")
    ax.set_ylabel("IOB Ratio (sticky / normal)")
    ax.set_title("IOB During Sticky Hypers")
    ax.axhline(1, color="gray", linestyle="--", alpha=0.5, label="Normal IOB")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3, axis="y")

    # Middle: glucose rate during sticky hypers
    ax = axes[1]
    rocs = [sticky[p]["sticky_roc_mean"] for p in patients]
    pct_rising = [sticky[p]["pct_positive_roc"] for p in patients]
    bars = ax.bar(x, rocs, color=colors)
    for i, bar in enumerate(bars):
        ax.annotate(f"{pct_rising[i]:.0f}%↑", (x[i], max(rocs[i], 0) + 0.3),
                    fontsize=7, ha="center")
    ax.set_xticks(x)
    ax.set_xticklabels([p[:10] for p in patients], fontsize=7, rotation=45, ha="right")
    ax.set_ylabel("Glucose ROC (mg/dL/hr)")
    ax.set_title("Glucose Slope During Sticky Hypers")
    ax.axhline(0, color="red", linestyle="--", alpha=0.5, label="Zero slope")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3, axis="y")

    # Right: episode counts
    ax = axes[2]
    eps = [sticky[p]["n_episodes"] for p in patients]
    ax.bar(x, eps, color=colors)
    ax.set_xticks(x)
    ax.set_xticklabels([p[:10] for p in patients], fontsize=7, rotation=45, ha="right")
    ax.set_ylabel("# Episodes (>180 for ≥3h)")
    ax.set_title("Sticky Hyper Frequency")
    ax.grid(True, alpha=0.3, axis="y")

    plt.tight_layout()
    plt.savefig(OUTDIR / "fig17_sticky_hypers.png", dpi=150)
    plt.close()
    print("  ✓ fig17_sticky_hypers.png")


def fig18_hill_distribution(data):
    """Hill parameter distribution — population heterogeneity."""
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    fig.suptitle("Fig 18: Per-Patient EGP Diversity — Implications for Tuning",
                 fontsize=14, fontweight="bold")

    fits = data.get("hill_fits", {})
    fitted = {k: v for k, v in fits.items() if "error" not in v}
    if not fitted:
        return

    colors = ["coral" if k.startswith("odc") else "steelblue" for k in fitted]
    labels = [k[:10] for k in fitted]

    # Left: base_egp scatter vs basal implied
    ax = axes[0]
    egps = [v["base_egp_hr"] for v in fitted.values()]
    ks = [v["hill_k"] for v in fitted.values()]
    ax.scatter(ks, egps, c=colors, s=100, edgecolors="black", zorder=5)
    for i, lbl in enumerate(labels):
        ax.annotate(lbl, (ks[i], egps[i]), fontsize=7,
                    xytext=(5, 5), textcoords="offset points")
    ax.axhline(18, color="gray", linestyle="--", alpha=0.5, label="Pop EGP=18")
    ax.axvline(2, color="gray", linestyle=":", alpha=0.5, label="Pop K=2")
    ax.set_xlabel("Hill K (U) — insulin needed for 50% suppression")
    ax.set_ylabel("Base EGP (mg/dL/hr)")
    ax.set_title("EGP Rate vs Suppression Threshold")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    # Middle: suppression at 2U per patient
    ax = axes[1]
    supp_2u = []
    for f in fitted.values():
        s = 2.0 ** f["hill_n"] / (2.0 ** f["hill_n"] + f["hill_k"] ** f["hill_n"])
        supp_2u.append(s * 100)
    sorted_idx = np.argsort(supp_2u)
    ax.barh(range(len(supp_2u)),
            [supp_2u[i] for i in sorted_idx],
            color=[colors[i] for i in sorted_idx])
    ax.set_yticks(range(len(supp_2u)))
    ax.set_yticklabels([labels[i] for i in sorted_idx], fontsize=8)
    ax.axvline(50, color="black", linestyle="--", label="Pop 50%")
    ax.set_xlabel("EGP Suppression at 2U IOB (%)")
    ax.set_title("How Much EGP Is Suppressed\nat Typical Correction IOB")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3, axis="x")

    # Right: implications summary
    ax = axes[2]
    implications = []
    for pid, f in fitted.items():
        supp_pop = 2.0 ** 1.5 / (2.0 ** 1.5 + 2.0 ** 1.5)
        supp_pers = 2.0 ** f["hill_n"] / (2.0 ** f["hill_n"] + f["hill_k"] ** f["hill_n"])
        if supp_pers < supp_pop - 0.1:
            implications.append("Low suppress\n(need more insulin)")
        elif supp_pers > supp_pop + 0.1:
            implications.append("High suppress\n(insulin effective)")
        else:
            implications.append("Normal\nsuppression")

    cats = {"Low suppress\n(need more insulin)": 0,
            "Normal\nsuppression": 0,
            "High suppress\n(insulin effective)": 0}
    for imp in implications:
        cats[imp] += 1
    cat_colors = ["#e74c3c", "#f39c12", "#27ae60"]
    ax.pie(cats.values(), labels=cats.keys(), colors=cat_colors,
           autopct="%1.0f%%", startangle=90, textprops={"fontsize": 9})
    ax.set_title("EGP Suppression Categories")

    plt.tight_layout()
    plt.savefig(OUTDIR / "fig18_hill_distribution.png", dpi=150)
    plt.close()
    print("  ✓ fig18_hill_distribution.png")


def main():
    data = _load()
    print("Generating EXP-2629 visualizations...")
    fig15_hill_curves(data)
    fig16_odc_validation(data)
    fig17_sticky_hypers(data)
    fig18_hill_distribution(data)
    print("Done!")


if __name__ == "__main__":
    main()
