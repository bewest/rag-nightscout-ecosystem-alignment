#!/usr/bin/env python3
"""Round 1 visualizations for EGP Phase Separation Research.

Generates publication-ready figures from EXP-2621 and EXP-2622 results.
Output: visualizations/egp-phase-research/*.png
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

PATIENTS = ["a", "b", "c", "d", "e", "f", "g", "i", "k"]


def load_results():
    with open(RESULTS_DIR / "exp-2621_residual_census.json") as f:
        r2621 = json.load(f)
    with open(RESULTS_DIR / "exp-2622_egp_trajectory.json") as f:
        r2622 = json.load(f)
    return r2621, r2622


def fig1_meal_census_by_block(r2621):
    """Bar chart: detected meals/day by time-of-day block per patient."""
    fig, ax = plt.subplots(figsize=(12, 6))

    blocks = ["overnight", "breakfast", "midday", "afternoon", "dinner", "evening"]
    colors = ["#2c3e50", "#e67e22", "#f1c40f", "#27ae60", "#e74c3c", "#8e44ad"]

    # Filter patients with data
    pids = []
    block_data = {b: [] for b in blocks}
    for pid in PATIENTS:
        if pid not in r2621["per_patient"]:
            continue
        p = r2621["per_patient"][pid]
        census = p["census"]
        if census["total_events"] == 0:
            continue
        pids.append(pid)
        for b in blocks:
            block_data[b].append(census["per_block"].get(b, {}).get("per_day", 0.0))

    if not pids:
        return

    x = np.arange(len(pids))
    width = 0.12
    for i, b in enumerate(blocks):
        offset = (i - len(blocks) / 2 + 0.5) * width
        ax.bar(x + offset, block_data[b], width, label=b.capitalize(), color=colors[i])

    ax.set_xlabel("Patient")
    ax.set_ylabel("Detected Events / Day")
    ax.set_title("EXP-2621: Residual Event Census by Time-of-Day Block")
    ax.set_xticks(x)
    ax.set_xticklabels(pids)
    ax.legend(ncol=3, fontsize=8)
    ax.grid(axis="y", alpha=0.3)

    fig.tight_layout()
    fig.savefig(VIZ_DIR / "fig1_meal_census_by_block.png", dpi=150)
    plt.close(fig)
    print(f"  Saved fig1_meal_census_by_block.png")


def fig2_spectral_bands(r2621):
    """Stacked bar: spectral power distribution across patients."""
    fig, ax = plt.subplots(figsize=(10, 5))

    bands = ["ultra_low", "egp_low", "meal", "high_freq"]
    labels = ["Ultra-low (>24h)", "EGP (8-24h)", "Meal (3-8h)", "High-freq (<3h)"]
    colors = ["#1abc9c", "#3498db", "#e67e22", "#95a5a6"]

    pids = []
    band_vals = {b: [] for b in bands}
    for pid in PATIENTS:
        if pid not in r2621["per_patient"]:
            continue
        p = r2621["per_patient"][pid]
        sp = p.get("spectral_bands", {})
        if not sp:
            continue
        pids.append(pid)
        for b in bands:
            band_vals[b].append(sp.get(b, 0.0))

    if not pids:
        return

    x = np.arange(len(pids))
    bottom = np.zeros(len(pids))
    for i, b in enumerate(bands):
        vals = np.array(band_vals[b])
        ax.bar(x, vals, bottom=bottom, label=labels[i], color=colors[i])
        bottom += vals

    ax.set_xlabel("Patient")
    ax.set_ylabel("Fraction of Residual Variance")
    ax.set_title("EXP-2621: Spectral Power Distribution of Metabolic Residual")
    ax.set_xticks(x)
    ax.set_xticklabels(pids)
    ax.legend(fontsize=8)
    ax.set_ylim(0, 1.05)
    ax.axhline(y=0.2, color="red", linestyle="--", alpha=0.5, label="20% threshold")
    ax.grid(axis="y", alpha=0.3)

    fig.tight_layout()
    fig.savefig(VIZ_DIR / "fig2_spectral_bands.png", dpi=150)
    plt.close(fig)
    print(f"  Saved fig2_spectral_bands.png")


def fig3_glycogen_vs_drift(r2622):
    """Scatter: glycogen proxy vs overnight drift (pooled)."""
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    pooled = r2622.get("pooled_windows", [])
    if not pooled:
        print("  SKIP fig3: no pooled windows")
        return

    glycogen = [w["glycogen_proxy"] for w in pooled]
    drift = [w["drift_rate"] for w in pooled]
    carbs_24 = [w["carbs_24h"] for w in pooled]
    carbs_48 = [w["carbs_48h"] for w in pooled]
    pids = [w["patient_id"] for w in pooled]
    unique_pids = sorted(set(pids))
    cmap = plt.cm.tab10
    pid_colors = {p: cmap(i / max(len(unique_pids), 1)) for i, p in enumerate(unique_pids)}
    c = [pid_colors[p] for p in pids]

    pool_stats = r2622.get("pooled", {})

    # Panel 1: 24h carbs vs drift
    ax = axes[0]
    ax.scatter(carbs_24, drift, c=c, alpha=0.6, edgecolor="k", linewidth=0.3, s=30)
    if len(carbs_24) > 2:
        m, b = np.polyfit(carbs_24, drift, 1)
        xs = np.linspace(min(carbs_24), max(carbs_24), 50)
        ax.plot(xs, m * xs + b, "r--", alpha=0.7)
    ax.set_xlabel("Prior-24h Carbs (g)")
    ax.set_ylabel("Overnight Drift (mg/dL/hr)")
    r_val = pool_stats.get("r_carbs24", 0)
    ax.set_title(f"24h Carbs → Drift (r={r_val:.3f})")
    ax.grid(alpha=0.3)

    # Panel 2: 48h carbs vs drift
    ax = axes[1]
    ax.scatter(carbs_48, drift, c=c, alpha=0.6, edgecolor="k", linewidth=0.3, s=30)
    if len(carbs_48) > 2:
        m, b = np.polyfit(carbs_48, drift, 1)
        xs = np.linspace(min(carbs_48), max(carbs_48), 50)
        ax.plot(xs, m * xs + b, "r--", alpha=0.7)
    ax.set_xlabel("Prior-48h Carbs (g)")
    r_val = pool_stats.get("r_carbs48", 0)
    ax.set_title(f"48h Carbs → Drift (r={r_val:.3f})")
    ax.grid(alpha=0.3)

    # Panel 3: glycogen proxy vs drift
    ax = axes[2]
    ax.scatter(glycogen, drift, c=c, alpha=0.6, edgecolor="k", linewidth=0.3, s=30)
    if len(glycogen) > 2:
        m, b = np.polyfit(glycogen, drift, 1)
        xs = np.linspace(min(glycogen), max(glycogen), 50)
        ax.plot(xs, m * xs + b, "r--", alpha=0.7)
    ax.set_xlabel("Glycogen Proxy (a.u.)")
    r_val = pool_stats.get("r_glycogen", 0)
    ax.set_title(f"Glycogen → Drift (r={r_val:.3f})")
    ax.grid(alpha=0.3)

    # Legend
    for pid in unique_pids:
        axes[2].scatter([], [], c=[pid_colors[pid]], label=f"Patient {pid}", s=30)
    axes[2].legend(fontsize=7, loc="upper right")

    fig.suptitle("EXP-2622: Prior Carb Load → Overnight Glucose Drift", fontsize=13)
    fig.tight_layout()
    fig.savefig(VIZ_DIR / "fig3_glycogen_vs_drift.png", dpi=150)
    plt.close(fig)
    print(f"  Saved fig3_glycogen_vs_drift.png")


def fig4_unannounced_vs_spectral(r2621):
    """Scatter: unannounced meal fraction vs EGP-band spectral power."""
    fig, ax = plt.subplots(figsize=(7, 5))

    pids, unanno, egp_band = [], [], []
    for pid in PATIENTS:
        if pid not in r2621["per_patient"]:
            continue
        p = r2621["per_patient"][pid]
        census = p["census"]
        if census["total_events"] == 0:
            continue
        pids.append(pid)
        unanno.append(census["unannounced_pct"])
        egp_band.append(p["spectral_bands"]["egp_low"])

    if len(pids) < 3:
        return

    ax.scatter(unanno, egp_band, s=80, c="#3498db", edgecolor="k", zorder=5)
    for i, pid in enumerate(pids):
        ax.annotate(f"  {pid}", (unanno[i], egp_band[i]), fontsize=9)

    # Trend line
    m, b = np.polyfit(unanno, egp_band, 1)
    xs = np.linspace(min(unanno), max(unanno), 50)
    ax.plot(xs, m * xs + b, "r--", alpha=0.5)

    rho = r2621.get("hypothesis_results", {}).get("h3_spearman_rho", 0)
    p_val = r2621.get("hypothesis_results", {}).get("h3_p_value", 1)
    ax.set_xlabel("Unannounced Meal Fraction (%)")
    ax.set_ylabel("EGP-Band Spectral Power (fraction)")
    ax.set_title(f"Unannounced Events vs EGP Spectral Power (ρ={rho:.2f}, p={p_val:.3f})")
    ax.grid(alpha=0.3)

    fig.tight_layout()
    fig.savefig(VIZ_DIR / "fig4_unannounced_vs_spectral.png", dpi=150)
    plt.close(fig)
    print(f"  Saved fig4_unannounced_vs_spectral.png")


if __name__ == "__main__":
    print("Generating Round 1 visualizations...")
    r2621, r2622 = load_results()
    fig1_meal_census_by_block(r2621)
    fig2_spectral_bands(r2621)
    fig3_glycogen_vs_drift(r2622)
    fig4_unannounced_vs_spectral(r2621)
    print("Done.")
