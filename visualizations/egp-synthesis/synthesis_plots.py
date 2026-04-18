#!/usr/bin/env python3
"""Generate synthesis report figures from EGP experiment results.

Figures for the EGP Research Synthesis Report (2026-04-18).
All data from externals/experiments/exp-26XX_*.json.
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

VIZ_DIR = Path(__file__).resolve().parent
EXP_DIR = Path("externals/experiments")

# Consistent style
COLORS = {
    "demand": "#2980b9",
    "supply": "#e74c3c",
    "transition": "#f39c12",
    "good": "#27ae60",
    "bad": "#e74c3c",
    "neutral": "#7f8c8d",
    "accent": "#8e44ad",
    "highlight": "#f1c40f",
}

plt.rcParams.update({
    "font.size": 10,
    "axes.titlesize": 12,
    "axes.labelsize": 10,
    "figure.dpi": 150,
    "savefig.bbox": "tight",
    "savefig.dpi": 150,
})


def fig1_three_phase_correction():
    """Fig 1: Three-phase correction trajectory showing 3.5h nadir vs 1.25h insulin peak."""
    d = json.load(open(EXP_DIR / "exp-2624_correction_egp_recovery.json"))
    per_patient = d["per_patient"]

    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))

    # Panel A: Schematic of three-phase model
    ax = axes[0]
    t = np.linspace(0, 8, 200)
    # Insulin activity (exponential model, peak=1.25h, DIA=6h)
    tp, td = 1.25, 6.0
    tau = tp * (1 - tp / td) / (1 - 2 * tp / td)
    ia = (t / tp) * np.exp(1 - t / tp)
    ia = ia / ia.max()

    # Glucose trajectory (demand phase → nadir at 3.5h → recovery)
    glucose = np.piecewise(t,
        [t < 2.0, (t >= 2.0) & (t < 3.5), t >= 3.5],
        [lambda x: 220 - 30 * x,
         lambda x: 160 - 20 * (x - 2.0),
         lambda x: 130 + 17 * (x - 3.5)])

    # EGP suppression (delayed, nadir at 3.5h)
    egp = np.piecewise(t,
        [t < 1.0, (t >= 1.0) & (t < 3.5), t >= 3.5],
        [lambda x: 18.0,
         lambda x: 18.0 - 12.0 * (x - 1.0) / 2.5,
         lambda x: 6.0 + 12.0 * (1 - np.exp(-(x - 3.5) / 2.0))])

    ax2 = ax.twinx()
    ax.plot(t, glucose, color=COLORS["demand"], linewidth=2.5, label="Glucose")
    ax.axvline(3.5, color=COLORS["supply"], linestyle="--", alpha=0.7, label="Nadir (3.5h)")
    ax.axvline(1.25, color=COLORS["neutral"], linestyle=":", alpha=0.7, label="Insulin peak (1.25h)")
    ax2.plot(t, ia * 100, color=COLORS["neutral"], linewidth=1.5, alpha=0.6, label="Insulin activity")
    ax2.plot(t, egp / 18 * 100, color=COLORS["supply"], linewidth=1.5, alpha=0.6, label="EGP (% baseline)")

    # Phase annotations
    ax.axvspan(0, 2.0, alpha=0.08, color=COLORS["demand"])
    ax.axvspan(2.0, 3.5, alpha=0.08, color=COLORS["transition"])
    ax.axvspan(3.5, 8, alpha=0.08, color=COLORS["supply"])
    ax.text(1.0, 230, "DEMAND\nPhase", ha="center", fontsize=8, color=COLORS["demand"], fontweight="bold")
    ax.text(2.75, 230, "TRANS.", ha="center", fontsize=8, color=COLORS["transition"], fontweight="bold")
    ax.text(5.5, 230, "SUPPLY (EGP Recovery)\nPhase", ha="center", fontsize=8, color=COLORS["supply"], fontweight="bold")

    # Phase lag arrow
    ax.annotate("", xy=(3.5, 135), xytext=(1.25, 135),
                arrowprops=dict(arrowstyle="<->", color="black", lw=1.5))
    ax.text(2.375, 138, "2.25h phase lag", ha="center", fontsize=8, fontweight="bold")

    ax.set_xlabel("Hours post-correction")
    ax.set_ylabel("Glucose (mg/dL)")
    ax2.set_ylabel("% of maximum", color=COLORS["neutral"])
    ax.set_title("A: Three-Phase Correction Model")
    ax.set_xlim(0, 8)
    ax.set_ylim(110, 240)
    ax.legend(loc="upper right", fontsize=7)
    ax2.legend(loc="center right", fontsize=7)

    # Panel B: Per-patient nadir timing
    ax = axes[1]
    patients = sorted(per_patient.keys())
    nadirs = [per_patient[p]["nadir_median_hours"] for p in patients]
    n_events = [per_patient[p]["n_events"] for p in patients]
    colors = [COLORS["supply"] if n > 3.0 else COLORS["demand"] for n in nadirs]

    bars = ax.bar(range(len(patients)), nadirs, color=colors, edgecolor="black", linewidth=0.5)
    ax.axhline(1.25, color=COLORS["neutral"], linestyle=":", linewidth=1.5, label="Insulin peak (1.25h)")
    ax.axhline(d["pooled"]["nadir_median_hours"], color=COLORS["supply"], linestyle="--",
               linewidth=1.5, label=f'Population median ({d["pooled"]["nadir_median_hours"]:.1f}h)')

    for i, (p, n, nd) in enumerate(zip(patients, n_events, nadirs)):
        ax.text(i, nd + 0.08, f"n={n}", ha="center", fontsize=6, color=COLORS["neutral"])

    ax.set_xticks(range(len(patients)))
    ax.set_xticklabels(patients, fontsize=8)
    ax.set_ylabel("Nadir time (hours)")
    ax.set_xlabel("Patient")
    ax.set_title("B: Per-Patient Correction Nadir Timing")
    ax.legend(fontsize=8)
    ax.set_ylim(0, 5.5)

    fig.suptitle("Figure 1: Glucose Nadir at 3.5h — The EGP Phase Lag", fontsize=13, fontweight="bold")
    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig1_three_phase_correction.png")
    plt.close()
    print("  ✓ fig1_three_phase_correction.png")


def fig2_dose_dependent_isf():
    """Fig 2: ISF compression across dose bins + log model."""
    d = json.load(open(EXP_DIR / "exp-2636_dose_dependent_isf.json"))
    bins_data = d["dose_response"]

    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))

    # Panel A: ISF by dose bin
    ax = axes[0]
    labels = [b["bin"] for b in bins_data]
    isfs = [b["mean_isf"] for b in bins_data]
    ns = [b["n"] for b in bins_data]
    drops = [b["mean_drop"] for b in bins_data]

    bar_colors = plt.cm.RdYlGn_r(np.linspace(0.2, 0.8, len(labels)))
    bars = ax.bar(range(len(labels)), isfs, color=bar_colors, edgecolor="black", linewidth=0.5)

    for i, (n, isf) in enumerate(zip(ns, isfs)):
        ax.text(i, isf + 2, f"n={n}", ha="center", fontsize=7, color=COLORS["neutral"])

    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=8, rotation=15)
    ax.set_ylabel("Apparent ISF (mg/dL/U)")
    ax.set_xlabel("Dose bin")
    ax.set_title("A: ISF Compression by Dose Size")

    # Compression ratio annotation
    if len(isfs) >= 2:
        ratio = isfs[0] / isfs[-1] if isfs[-1] > 0 else 0
        ax.annotate(f"{ratio:.1f}× compression",
                    xy=(len(labels) - 1, isfs[-1]), xytext=(len(labels) - 2, isfs[0] * 0.7),
                    arrowprops=dict(arrowstyle="->", color="black"),
                    fontsize=10, fontweight="bold", color=COLORS["bad"])

    # Panel B: Per-patient log-ISF model
    ax = axes[1]
    pp_raw = json.load(open(EXP_DIR / "exp-2640_per_patient_isf.json"))
    pp = pp_raw.get("per_patient", pp_raw)
    patients_pp = sorted([k for k in pp.keys() if not k.startswith("_") and isinstance(pp[k], dict)])

    for i, pid in enumerate(patients_pp):
        p = pp[pid]
        data = p.get("data", {})
        if "bolus_u" in data and "apparent_isf" in data:
            doses = data["bolus_u"]
            isf_vals = data["apparent_isf"]
            ax.scatter(doses, isf_vals, s=15, alpha=0.4, label=pid if i < 6 else None)

    # Overlay log model
    x_model = np.linspace(0.3, 5.0, 100)
    y_model = 50 - 28 * np.log(x_model)
    y_model = np.clip(y_model, 0, 200)
    ax.plot(x_model, y_model, "k--", linewidth=2, label="ISF ≈ 50 − 28·ln(dose)")

    ax.set_xlabel("Correction dose (U)")
    ax.set_ylabel("Apparent ISF (mg/dL/U)")
    ax.set_title("B: Logarithmic Dose-Response Model")
    ax.legend(fontsize=7, ncol=2)
    ax.set_xlim(0, 5)
    ax.set_ylim(0, 160)

    fig.suptitle("Figure 2: Dose-Dependent ISF — 4.6× Compression (r = −0.56)", fontsize=13, fontweight="bold")
    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig2_dose_dependent_isf.png")
    plt.close()
    print("  ✓ fig2_dose_dependent_isf.png")


def fig3_sc_ceiling():
    """Fig 3: SC suppression ceiling by patient."""
    d = json.load(open(EXP_DIR / "exp-2656_sc_ceiling.json"))
    patients = sorted(d.keys())

    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))

    # Panel A: Ceiling values
    ax = axes[0]
    ratios = [d[p]["actual_to_predicted_ratio"] for p in patients]
    ceilings = [min(r, 1.0) * 100 for r in ratios]  # as percentage
    n_events = [d[p]["n_high_iob"] for p in patients]

    colors = [COLORS["good"] if c > 45 else COLORS["bad"] if c < 35 else COLORS["transition"]
              for c in ceilings]
    bars = ax.bar(range(len(patients)), ceilings, color=colors, edgecolor="black", linewidth=0.5)
    ax.axhline(30, color=COLORS["bad"], linestyle="--", linewidth=1.5, label="Population median (~30%)")
    ax.axhline(65, color=COLORS["neutral"], linestyle=":", linewidth=1, label="cgmsim-lib assumption (65%)")

    for i, (p, n, c) in enumerate(zip(patients, n_events, ceilings)):
        ax.text(i, c + 1.5, f"n={n}", ha="center", fontsize=7, color=COLORS["neutral"])

    ax.set_xticks(range(len(patients)))
    ax.set_xticklabels(patients, fontsize=9)
    ax.set_ylabel("EGP Suppression (% of baseline)")
    ax.set_xlabel("Patient")
    ax.set_title("A: SC Insulin Suppression Ceiling")
    ax.legend(fontsize=8)
    ax.set_ylim(0, 80)

    # Panel B: Linear vs ceiling RMSE comparison
    ax = axes[1]
    linear_rmse = [d[p]["linear_rmse"] for p in patients]
    ceiling_rmse = [d[p]["ceiling_65_rmse"] for p in patients]

    x_pos = np.arange(len(patients))
    w = 0.35
    ax.bar(x_pos - w / 2, linear_rmse, w, label="Linear model", color=COLORS["demand"], alpha=0.8)
    ax.bar(x_pos + w / 2, ceiling_rmse, w, label="Ceiling model (65%)", color=COLORS["supply"], alpha=0.8)

    ax.set_xticks(x_pos)
    ax.set_xticklabels(patients, fontsize=9)
    ax.set_ylabel("RMSE (mg/dL/hr)")
    ax.set_xlabel("Patient")
    ax.set_title("B: Linear vs Ceiling Model Fit")
    ax.legend(fontsize=8)

    fig.suptitle("Figure 3: SC Insulin Can Suppress at Most ~30% of Hepatic EGP", fontsize=13, fontweight="bold")
    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig3_sc_ceiling.png")
    plt.close()
    print("  ✓ fig3_sc_ceiling.png")


def fig4_aid_compensation():
    """Fig 4: AID compensation cascade — reverse causation."""
    d = json.load(open(EXP_DIR / "exp-2629_aid_compensation_cascade.json"))
    pooled = d["pooled"]
    per_patient = d["per_patient"]

    fig, axes = plt.subplots(1, 3, figsize=(16, 5))

    # Panel A: IOB drop before hypo
    ax = axes[0]
    patients = sorted(per_patient.keys())
    iob_drops = [per_patient[p].get("mean_iob_drop_pct", 0) for p in patients]
    n_episodes = [per_patient[p].get("n_low_episodes", 0) for p in patients]

    colors = [COLORS["bad"] if d > 50 else COLORS["transition"] for d in iob_drops]
    ax.barh(range(len(patients)), iob_drops, color=colors, edgecolor="black", linewidth=0.5)
    ax.axvline(pooled["median_iob_drop_pct"], color="black", linestyle="--",
               label=f'Median: {pooled["median_iob_drop_pct"]:.0f}%')

    for i, (p, n) in enumerate(zip(patients, n_episodes)):
        ax.text(max(iob_drops) + 2, i, f"n={n}", va="center", fontsize=7)

    ax.set_yticks(range(len(patients)))
    ax.set_yticklabels(patients, fontsize=9)
    ax.set_xlabel("IOB Drop Before Hypo (%)")
    ax.set_title("A: IOB Drops 55% BEFORE\nGlucose Crosses 70 mg/dL")
    ax.legend(fontsize=8)

    # Panel B: Causal diagram
    ax = axes[1]
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.set_aspect("equal")
    ax.axis("off")

    # Wrong model (crossed out)
    ax.text(5, 9.2, "NAIVE (WRONG) MODEL", ha="center", fontsize=10, fontweight="bold", color=COLORS["bad"])
    ax.annotate("", xy=(7, 8), xytext=(3, 8),
                arrowprops=dict(arrowstyle="->", color=COLORS["bad"], lw=2))
    ax.text(2, 8.2, "High IOB", ha="center", fontsize=9)
    ax.text(8, 8.2, "Recovery", ha="center", fontsize=9)
    ax.plot([3, 7], [8.5, 7.5], color=COLORS["bad"], linewidth=3)  # strikethrough

    # True model
    ax.text(5, 6.2, "TRUE MODEL", ha="center", fontsize=10, fontweight="bold", color=COLORS["good"])
    ax.text(5, 5.2, "Glucose ↓", ha="center", fontsize=11, fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.3", facecolor=COLORS["highlight"], alpha=0.5))
    ax.annotate("", xy=(2, 3.5), xytext=(4, 4.7),
                arrowprops=dict(arrowstyle="->", color=COLORS["good"], lw=2))
    ax.annotate("", xy=(8, 3.5), xytext=(6, 4.7),
                arrowprops=dict(arrowstyle="->", color=COLORS["good"], lw=2))
    ax.text(2, 3.0, "AID withdraws\ninsulin → IOB ↓", ha="center", fontsize=9,
            bbox=dict(boxstyle="round,pad=0.3", facecolor="#dfe6e9", alpha=0.7))
    ax.text(8, 3.0, "Glucose\nrecovers", ha="center", fontsize=9,
            bbox=dict(boxstyle="round,pad=0.3", facecolor="#dfe6e9", alpha=0.7))
    ax.text(5, 1.2, "Both are EFFECTS of falling glucose,\nnot cause → effect",
            ha="center", fontsize=9, style="italic", color=COLORS["neutral"])

    ax.set_title("B: Reverse Causation via Feedback")

    # Panel C: Hill under-prediction
    ax = axes[2]
    hill_ratio = pooled.get("hill_ratio_median", 2.09)
    categories = ["Hill EGP\nPrediction", "Actual\nRecovery", "Excess\n(Counter-reg +\nAID withdrawal)"]
    vals = [1.0, hill_ratio, hill_ratio - 1.0]
    colors_c = [COLORS["demand"], COLORS["supply"], COLORS["transition"]]

    bars = ax.bar(range(len(categories)), vals, color=colors_c, edgecolor="black", linewidth=0.5)
    ax.text(1, hill_ratio + 0.1, f"{hill_ratio:.1f}×", ha="center", fontsize=12, fontweight="bold")
    ax.set_xticks(range(len(categories)))
    ax.set_xticklabels(categories, fontsize=9)
    ax.set_ylabel("Recovery Rate (normalized)")
    ax.set_title("C: Hill EGP Under-Predicts\nRecovery by 2.1×")

    fig.suptitle("Figure 4: AID Compensation Cascade — Reverse Causation in Closed-Loop Data",
                 fontsize=13, fontweight="bold")
    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig4_aid_compensation.png")
    plt.close()
    print("  ✓ fig4_aid_compensation.png")


def fig5_model_comparison():
    """Fig 5: All recovery models have negative R²."""
    d = json.load(open(EXP_DIR / "exp-2634_model_comparison.json"))
    ms = d["model_summary"]

    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))

    # Panel A: R² comparison
    ax = axes[0]
    models = list(ms.keys())
    r2s = [ms[m]["r2_mean"] for m in models]
    r2_stds = [ms[m]["r2_std"] for m in models]
    rmses = [ms[m]["rmse_mean"] for m in models]

    model_labels = {
        "null": "Null\n(stay at nadir)",
        "mean_reversion": "Mean\nReversion",
        "iob_decay": "IOB\nDecay",
        "biexp_decay": "Biexp\nDecay",
        "hill_egp": "Hill EGP\n(WORST)",
    }
    labels = [model_labels.get(m, m) for m in models]
    colors = [COLORS["bad"] if m == "hill_egp" else COLORS["transition"] for m in models]

    bars = ax.bar(range(len(models)), r2s, color=colors, edgecolor="black", linewidth=0.5,
                  yerr=r2_stds, capsize=4)
    ax.axhline(0, color="black", linewidth=2, label="R² = 0 (mean predictor)")
    ax.set_xticks(range(len(models)))
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("R² (mean across patients)")
    ax.set_title("A: All Models Have NEGATIVE R²\n(worse than predicting the mean)")
    ax.legend(fontsize=8)

    for i, r2 in enumerate(r2s):
        ax.text(i, r2 - 0.3, f"{r2:.2f}", ha="center", fontsize=9, fontweight="bold", color="white")

    # Panel B: The prescriptive paradox
    d2 = json.load(open(EXP_DIR / "exp-2641_forward_sim_log_isf.json"))
    models_2641 = d2["models"]

    ax = axes[1]
    model_keys = list(models_2641.keys())
    biases = [models_2641[m]["bias"] for m in model_keys]
    r2s_2 = [models_2641[m]["r_squared"] for m in model_keys]

    model_labels_2 = {
        "A_fixed_isf": "Fixed ISF",
        "B_pop_log_isf": "Pop. Log-ISF",
        "C_patient_log_isf": "Patient\nLog-ISF",
        "D_linear_ratio": "Linear Ratio",
        "E_iob_weighted": "IOB-Weighted",
        "F_iob_log": "IOB+Log",
    }
    labels_2 = [model_labels_2.get(m, m) for m in model_keys]

    # Color by paradox: best descriptor (C) is worst prescriber
    colors_2 = []
    for m in model_keys:
        if m == "C_patient_log_isf":
            colors_2.append(COLORS["accent"])
        elif m == "A_fixed_isf":
            colors_2.append(COLORS["good"])
        else:
            colors_2.append(COLORS["neutral"])

    scatter = ax.scatter(biases, r2s_2, s=120, c=colors_2, edgecolors="black", linewidth=0.5, zorder=5)
    for i, (m, b, r2) in enumerate(zip(model_keys, biases, r2s_2)):
        ax.annotate(labels_2[i], (b, r2), fontsize=7, ha="center",
                    xytext=(0, 12), textcoords="offset points")

    ax.axhline(0, color="black", linestyle="-", alpha=0.3)
    ax.axvline(0, color="black", linestyle="-", alpha=0.3)
    ax.set_xlabel("Descriptive Bias (mg/dL)\n← undershoot | overshoot →")
    ax.set_ylabel("Prescriptive R²")
    ax.set_title("B: Prescriptive Paradox\nBest descriptor (bias≈0) has worst R²")

    # Highlight the paradox
    c_idx = model_keys.index("C_patient_log_isf") if "C_patient_log_isf" in model_keys else None
    if c_idx is not None:
        ax.annotate("PARADOX: Best descriptor\n= worst prescriber (2.3× overdose)",
                    xy=(biases[c_idx], r2s_2[c_idx]),
                    xytext=(biases[c_idx] + 30, r2s_2[c_idx] - 0.5),
                    arrowprops=dict(arrowstyle="->", color=COLORS["accent"], lw=1.5),
                    fontsize=8, fontweight="bold", color=COLORS["accent"])

    fig.suptitle("Figure 5: No Recovery Model Works — And the Best Descriptor Is the Worst Prescriber",
                 fontsize=13, fontweight="bold")
    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig5_models_and_paradox.png")
    plt.close()
    print("  ✓ fig5_models_and_paradox.png")


def fig6_two_phase_isf():
    """Fig 6: Demand-ISF vs Apparent-ISF — the 2-10× gap."""
    d = json.load(open(EXP_DIR / "exp-2651_two_phase_isf.json"))
    patients = sorted([k for k in d.keys() if not k.startswith("_")])

    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))

    # Panel A: ISF comparison
    ax = axes[0]
    demand_isfs = [d[p]["demand_isf"] for p in patients]
    apparent_isfs = [d[p]["apparent_isf"] for p in patients]
    scheduled_isfs = [d[p]["scheduled_isf"] for p in patients]
    inflation = [d[p]["inflation_ratio"] for p in patients]

    x = np.arange(len(patients))
    w = 0.25
    ax.bar(x - w, demand_isfs, w, label="Demand ISF (0–2h)", color=COLORS["demand"], edgecolor="black", linewidth=0.5)
    ax.bar(x, apparent_isfs, w, label="Apparent ISF (full drop)", color=COLORS["supply"], edgecolor="black", linewidth=0.5)
    ax.bar(x + w, scheduled_isfs, w, label="Scheduled ISF (profile)", color=COLORS["neutral"], edgecolor="black", linewidth=0.5)

    for i, inf in enumerate(inflation):
        ax.text(i, max(demand_isfs[i], apparent_isfs[i], scheduled_isfs[i]) + 5,
                f"{inf:.1f}×", ha="center", fontsize=7, fontweight="bold", color=COLORS["accent"])

    ax.set_xticks(x)
    ax.set_xticklabels(patients, fontsize=8)
    ax.set_ylabel("ISF (mg/dL/U)")
    ax.set_xlabel("Patient")
    ax.set_title("A: Three ISF Values Per Patient")
    ax.legend(fontsize=7)

    # Panel B: Inflation ratio distribution
    ax = axes[1]
    ax.bar(range(len(patients)), inflation, color=[
        COLORS["bad"] if i > 2.0 else COLORS["transition"] if i > 1.5 else COLORS["good"]
        for i in inflation
    ], edgecolor="black", linewidth=0.5)
    ax.axhline(1.0, color="black", linestyle="-", linewidth=1.5, label="No inflation (1.0×)")
    ax.axhline(np.median(inflation), color=COLORS["accent"], linestyle="--",
               label=f"Median: {np.median(inflation):.1f}×")

    ax.set_xticks(range(len(patients)))
    ax.set_xticklabels(patients, fontsize=8)
    ax.set_ylabel("Inflation Ratio (apparent / demand)")
    ax.set_xlabel("Patient")
    ax.set_title("B: Apparent ISF Inflated 2–10× Over Demand-Phase ISF")
    ax.legend(fontsize=8)

    fig.suptitle("Figure 6: Two-Phase ISF — Demand (0–2h) vs Apparent (Full Correction)",
                 fontsize=13, fontweight="bold")
    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig6_two_phase_isf.png")
    plt.close()
    print("  ✓ fig6_two_phase_isf.png")


def fig7_nyquist_multiscale():
    """Fig 7: Nyquist-correct multi-scale R² contributions."""
    d = json.load(open(EXP_DIR / "exp-2653_nyquist_multiscale.json"))
    pooled = d.get("_pooled", {})
    patients = sorted([k for k in d.keys() if not k.startswith("_")])

    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))

    # Panel A: R² by feature for pooled data
    ax = axes[0]
    features = ["iob_alone_r2", "carbs_24h_r2", "carbs_48h_r2", "demand_r2", "supply_r2", "net_energy_r2"]
    feature_labels = ["IOB alone", "24h carbs", "48h carbs", "Demand\n(IOB+carbs)", "Supply\n(EGP proxy)", "Net energy"]
    pooled_r2 = [pooled.get(f, 0) for f in features]

    colors_f = [COLORS["demand"], COLORS["transition"], COLORS["supply"],
                COLORS["demand"], COLORS["supply"], COLORS["accent"]]
    ax.bar(range(len(features)), pooled_r2, color=colors_f, edgecolor="black", linewidth=0.5)
    for i, r2 in enumerate(pooled_r2):
        ax.text(i, r2 + 0.005, f"{r2:.3f}", ha="center", fontsize=8, fontweight="bold")

    ax.set_xticks(range(len(features)))
    ax.set_xticklabels(feature_labels, fontsize=8)
    ax.set_ylabel("R² (overnight drift prediction)")
    ax.set_title("A: Pooled Feature Contributions\n87% of overnight drift is UNMEASURED")
    ax.set_ylim(0, max(pooled_r2) * 1.5 if max(pooled_r2) > 0 else 0.2)

    # Panel B: Per-patient IOB R² (demand/supply ratio varies 157×)
    ax = axes[1]
    iob_r2 = [d[p].get("iob_alone_r2", 0) for p in patients]
    supply_r2 = [d[p].get("supply_r2", 0) for p in patients]

    x = np.arange(len(patients))
    w = 0.35
    ax.bar(x - w / 2, iob_r2, w, label="Demand (IOB)", color=COLORS["demand"], edgecolor="black", linewidth=0.5)
    ax.bar(x + w / 2, supply_r2, w, label="Supply (EGP)", color=COLORS["supply"], edgecolor="black", linewidth=0.5)

    ax.set_xticks(x)
    ax.set_xticklabels(patients, fontsize=8)
    ax.set_ylabel("R²")
    ax.set_xlabel("Patient")
    ax.set_title("B: Demand vs Supply — 157× Variation Across Patients")
    ax.legend(fontsize=8)

    fig.suptitle("Figure 7: Nyquist Multi-Scale Analysis — Most Overnight Drift Is Unmeasured",
                 fontsize=13, fontweight="bold")
    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig7_nyquist_multiscale.png")
    plt.close()
    print("  ✓ fig7_nyquist_multiscale.png")


def fig8_basal_overnight_drift():
    """Fig 8: Basal optimization — overnight drift phenotypes and IOB-correction."""
    d = json.load(open(EXP_DIR / "exp-2650_basal_recommendation.json"))
    patients = sorted(d.keys())

    fig, axes = plt.subplots(1, 3, figsize=(16, 5))

    # Filter to patients with midnight data
    patients_mid = [p for p in patients if "midnight" in d[p]]
    patients_dawn = [p for p in patients if "dawn" in d[p]]

    # Panel A: Overnight drift per patient (midnight block)
    ax = axes[0]
    drifts = [d[p]["midnight"]["mean_drift"] for p in patients_mid]
    colors = [COLORS["bad"] if dr > 3 else COLORS["good"] if abs(dr) <= 3 else COLORS["demand"]
              for dr in drifts]

    bars = ax.barh(range(len(patients_mid)), drifts, color=colors, edgecolor="black", linewidth=0.5)
    ax.axvline(0, color="black", linewidth=1)
    ax.axvline(3, color=COLORS["bad"], linestyle="--", alpha=0.5, label="Under-basaled threshold")
    ax.axvline(-3, color=COLORS["demand"], linestyle="--", alpha=0.5, label="Over-basaled threshold")

    ax.set_yticks(range(len(patients_mid)))
    ax.set_yticklabels(patients_mid, fontsize=9)
    ax.set_xlabel("Mean overnight drift (mg/dL/hr)")
    ax.set_title("A: Overnight Glucose Drift\n(00:00–04:00)")
    ax.legend(fontsize=7)

    # Panel B: IOB-drift correlation
    ax = axes[1]
    r_vals = [d[p]["midnight"]["r_iob_drift"] for p in patients_mid]
    p_vals = [d[p]["midnight"]["p_value"] for p in patients_mid]
    colors_sig = [COLORS["good"] if pv < 0.05 else COLORS["neutral"] for pv in p_vals]

    ax.barh(range(len(patients_mid)), r_vals, color=colors_sig, edgecolor="black", linewidth=0.5)
    ax.axvline(0, color="black", linewidth=1)

    for i, (r, p_val) in enumerate(zip(r_vals, p_vals)):
        sig = "**" if p_val < 0.01 else "*" if p_val < 0.05 else ""
        ax.text(r + 0.02 if r >= 0 else r - 0.06, i, sig, va="center", fontsize=10, fontweight="bold")

    ax.set_yticks(range(len(patients_mid)))
    ax.set_yticklabels(patients_mid, fontsize=9)
    ax.set_xlabel("r (IOB@midnight vs drift)")
    ax.set_title("B: IOB Predicts Drift\n(* p<0.05, ** p<0.01)")
    sig_patch = mpatches.Patch(color=COLORS["good"], label="Significant (p<0.05)")
    ns_patch = mpatches.Patch(color=COLORS["neutral"], label="Not significant")
    ax.legend(handles=[sig_patch, ns_patch], fontsize=7)

    # Panel C: Dawn phenomenon
    ax = axes[2]
    dawn_pcts = []
    for p in patients:
        dawn = d[p].get("dawn_increase_pct", 0)
        dawn_pcts.append(dawn if dawn else 0)

    colors_dawn = [COLORS["bad"] if dp > 20 else COLORS["transition"] if dp > 0 else COLORS["good"]
                   for dp in dawn_pcts]
    ax.barh(range(len(patients)), dawn_pcts, color=colors_dawn, edgecolor="black", linewidth=0.5)
    ax.axvline(20, color=COLORS["bad"], linestyle="--", alpha=0.5, label="Dawn threshold (20%)")
    ax.axvline(0, color="black", linewidth=1)

    ax.set_yticks(range(len(patients)))
    ax.set_yticklabels(patients, fontsize=9)
    ax.set_xlabel("Dawn basal increase needed (%)")
    ax.set_title("C: Dawn Phenomenon\n(04:00–08:00 vs midnight)")
    ax.legend(fontsize=7)

    fig.suptitle("Figure 8: Basal Optimization — Overnight Drift, IOB Correction & Dawn Phenomenon",
                 fontsize=13, fontweight="bold")
    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig8_basal_overnight_drift.png")
    plt.close()
    print("  ✓ fig8_basal_overnight_drift.png")


if __name__ == "__main__":
    print("Generating EGP Research Synthesis figures...\n")
    fig1_three_phase_correction()
    fig2_dose_dependent_isf()
    fig3_sc_ceiling()
    fig4_aid_compensation()
    fig5_model_comparison()
    fig6_two_phase_isf()
    fig7_nyquist_multiscale()
    fig8_basal_overnight_drift()
    print(f"\nDone! 8 figures saved to {VIZ_DIR}/")
