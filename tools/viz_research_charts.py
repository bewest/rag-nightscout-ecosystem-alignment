#!/usr/bin/env python3
"""Research visualization charts for CGM prediction experiments.

Generates 10 publication-quality charts from experiment JSON files,
saved to the visualizations/ directory.
"""
import json
import glob as globmod
import os
import pathlib
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import TwoSlopeNorm
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "visualizations"

# ---------------------------------------------------------------------------
# Consistent style configuration
# ---------------------------------------------------------------------------
STYLE = 'seaborn-v0_8-whitegrid'
DPI = 150
SINGLE_FIG = (12, 7)
DUAL_FIG = (16, 7)
TITLE_SIZE = 14
LABEL_SIZE = 12
ANNOT_SIZE = 10
GRID_ALPHA = 0.3

# Colorblind-friendly palette (tab10 first 11)
PAT_COLORS = plt.cm.tab10(np.linspace(0, 1, 10)).tolist()
PAT_COLORS.append(plt.cm.Set2(0.0))  # 11th distinct colour

VERSION_COLORS = {'v0': '#d62728', 'v1': '#ff7f0e', 'v2': '#2ca02c'}


def _apply_style():
    plt.style.use(STYLE)
    plt.rcParams.update({
        'figure.dpi': DPI,
        'axes.titlesize': TITLE_SIZE,
        'axes.labelsize': LABEL_SIZE,
        'xtick.labelsize': 10,
        'ytick.labelsize': 10,
        'grid.alpha': GRID_ALPHA,
        'legend.fontsize': 10,
    })


def load_experiment(pattern: str) -> dict:
    """Load an experiment JSON file matching a glob pattern from the repo root."""
    matches = sorted(ROOT.glob(pattern))
    if not matches:
        raise FileNotFoundError(f"No file matching {pattern} in {ROOT}")
    with open(matches[0]) as f:
        return json.load(f)


# ===================================================================
# Chart 1 – R² Improvement Waterfall (grouped bar)
# ===================================================================
def chart_r2_waterfall():
    _apply_style()
    data = load_experiment("exp-700*.json")
    patients = data["per_patient"]

    # Sort by final R² (v2)
    patients.sort(key=lambda p: p["r2_v2_cleaned_dawn"])

    names = [p["patient"] for p in patients]
    v0 = [p["r2_v0_baseline"] for p in patients]
    v1 = [p["r2_v1_spike_cleaned"] for p in patients]
    v2 = [p["r2_v2_cleaned_dawn"] for p in patients]

    means = [data["mean_r2_v0"], data["mean_r2_v1"], data["mean_r2_v2"]]

    x = np.arange(len(names))
    w = 0.25

    fig, ax = plt.subplots(figsize=SINGLE_FIG)
    ax.bar(x - w, v0, w, label=f'v0 baseline (mean {means[0]:.3f})',
           color=VERSION_COLORS['v0'], edgecolor='white', linewidth=0.5)
    ax.bar(x, v1, w, label=f'v1 spike-cleaned (mean {means[1]:.3f})',
           color=VERSION_COLORS['v1'], edgecolor='white', linewidth=0.5)
    ax.bar(x + w, v2, w, label=f'v2 cleaned+dawn (mean {means[2]:.3f})',
           color=VERSION_COLORS['v2'], edgecolor='white', linewidth=0.5)

    for i, m in enumerate(means):
        style = ['--', '-.', '-'][i]
        color = [VERSION_COLORS['v0'], VERSION_COLORS['v1'], VERSION_COLORS['v2']][i]
        ax.axhline(m, ls=style, color=color, alpha=0.5, linewidth=1)

    ax.set_xticks(x)
    ax.set_xticklabels(names)
    ax.set_xlabel("Patient (sorted by final R²)")
    ax.set_ylabel("R² Score")
    ax.set_title("Model Improvement Across 11 Patients")
    ax.legend(loc='upper left', framealpha=0.9)
    ax.set_ylim(0, 0.85)
    fig.tight_layout()
    fig.savefig(OUT / "r2_improvement_waterfall.png", dpi=DPI)
    plt.close(fig)
    print("  ✓ r2_improvement_waterfall.png")


# ===================================================================
# Chart 2 – Clinical Dashboard Heatmap
# ===================================================================
def chart_clinical_dashboard():
    _apply_style()
    data = load_experiment("exp-688*.json")
    dash = data["dashboard"]

    columns = ['tir', 'tbr', 'tar', 'cv', 'gmi', 'risk_score', 'model_r2']
    col_labels = ['TIR %', 'TBR %', 'TAR %', 'CV %', 'GMI %', 'Risk Score', 'Model R²']
    # For normalisation: direction where higher = better (+1) or worse (-1)
    col_direction = [1, -1, -1, -1, -1, -1, 1]

    # Sort by grade (A<B<C<D) then by TIR descending within grade
    grade_order = {'A': 0, 'B': 1, 'C': 2, 'D': 3}
    dash.sort(key=lambda p: (grade_order.get(p['grade'], 9), -p['tir']))

    names = [p['patient'] for p in dash]
    grades = [p['grade'] for p in dash]
    raw = np.array([[p[c] for c in columns] for p in dash])

    # Normalise each column to 0-1 then flip direction so 1 = good
    norm = np.zeros_like(raw)
    for j in range(raw.shape[1]):
        col = raw[:, j]
        mn, mx = col.min(), col.max()
        if mx - mn > 0:
            norm[:, j] = (col - mn) / (mx - mn)
        else:
            norm[:, j] = 0.5
        if col_direction[j] == -1:
            norm[:, j] = 1.0 - norm[:, j]

    fig, ax = plt.subplots(figsize=(14, 7))
    # Green=good (1), Red=bad (0)
    cmap = plt.cm.RdYlGn
    im = ax.imshow(norm, cmap=cmap, aspect='auto', vmin=0, vmax=1)

    ax.set_xticks(np.arange(len(col_labels)))
    ax.set_xticklabels(col_labels, rotation=30, ha='right')
    ax.set_yticks(np.arange(len(names)))
    ax.set_yticklabels([f"[{g}] {n}" for g, n in zip(grades, names)])

    # Annotate cells with raw values
    for i in range(raw.shape[0]):
        for j in range(raw.shape[1]):
            val = raw[i, j]
            txt = f"{val:.1f}" if val >= 1 else f"{val:.3f}"
            text_color = 'white' if norm[i, j] < 0.35 or norm[i, j] > 0.85 else 'black'
            ax.text(j, i, txt, ha='center', va='center',
                    fontsize=9, color=text_color, fontweight='bold')

    ax.set_title("Cross-Patient Clinical Dashboard")
    cbar = fig.colorbar(im, ax=ax, shrink=0.8, pad=0.02)
    cbar.set_label("Normalised quality (green = better)")
    fig.tight_layout()
    fig.savefig(OUT / "clinical_dashboard_heatmap.png", dpi=DPI)
    plt.close(fig)
    print("  ✓ clinical_dashboard_heatmap.png")


# ===================================================================
# Chart 3 – Control Quality Paradox Scatter
# ===================================================================
def chart_tir_vs_r2():
    _apply_style()
    data700 = load_experiment("exp-700*.json")
    data688 = load_experiment("exp-688*.json")
    tir_map = {p['patient']: p['tir'] for p in data688['dashboard']}

    patients = data700['per_patient']
    names = [p['patient'] for p in patients]
    tir = np.array([tir_map[n] for n in names])
    r2 = np.array([p['r2_v2_cleaned_dawn'] for p in patients])

    # Regression
    m, b = np.polyfit(tir, r2, 1)
    corr = np.corrcoef(tir, r2)[0, 1]
    x_fit = np.linspace(tir.min() - 2, tir.max() + 2, 100)
    y_fit = m * x_fit + b

    fig, ax = plt.subplots(figsize=SINGLE_FIG)
    for idx, (xi, yi, nm) in enumerate(zip(tir, r2, names)):
        ax.scatter(xi, yi, s=120, color=PAT_COLORS[idx % len(PAT_COLORS)],
                   edgecolors='black', linewidth=0.5, zorder=5)
        offset = (5, 5) if nm not in ('k', 'i') else (8, -12)
        ax.annotate(nm, (xi, yi), textcoords="offset points",
                    xytext=offset, fontsize=ANNOT_SIZE, fontweight='bold')

    ax.plot(x_fit, y_fit, '--', color='gray', alpha=0.7,
            label=f'r = {corr:.3f}')

    # Annotate extremes
    ax.annotate("k: TIR 95.1%, R²=0.241\n(best control, hardest to predict)",
                xy=(95.1, 0.241), xytext=(80, 0.15),
                arrowprops=dict(arrowstyle='->', color='red'),
                fontsize=ANNOT_SIZE, color='red', fontweight='bold')
    ax.annotate("i: R²=0.735\n(most predictable)",
                xy=(59.9, 0.735), xytext=(62, 0.78),
                arrowprops=dict(arrowstyle='->', color='blue'),
                fontsize=ANNOT_SIZE, color='blue', fontweight='bold')

    # Explanatory box
    props = dict(boxstyle='round,pad=0.5', facecolor='lightyellow',
                 edgecolor='orange', alpha=0.9)
    ax.text(0.98, 0.02,
            "Tight control creates narrow BG band\n→ less predictable signal",
            transform=ax.transAxes, fontsize=ANNOT_SIZE,
            verticalalignment='bottom', horizontalalignment='right',
            bbox=props)

    ax.set_xlabel("Time in Range (TIR %)")
    ax.set_ylabel("Model R² (v2 cleaned+dawn)")
    ax.set_title("Control Quality Paradox: Well-Controlled Patients Are Harder to Predict")
    ax.legend(loc='upper right')
    fig.tight_layout()
    fig.savefig(OUT / "tir_vs_r2_paradox.png", dpi=DPI)
    plt.close(fig)
    print("  ✓ tir_vs_r2_paradox.png")


# ===================================================================
# Chart 4 – Minimal Data Learning Curve
# ===================================================================
def chart_minimal_data():
    _apply_style()
    data = load_experiment("exp-699*.json")
    mean_r2 = data["mean_r2_by_days"]
    days_keys = sorted(mean_r2.keys(), key=lambda k: int(k))
    days = np.array([int(k) for k in days_keys])
    mean_vals = np.array([mean_r2[k] for k in days_keys])

    fig, ax = plt.subplots(figsize=SINGLE_FIG)

    # Per-patient thin lines
    for idx, p in enumerate(data["per_patient"]):
        pdays = sorted(p["r2_by_days"].keys(), key=lambda k: int(k))
        pd = [int(k) for k in pdays]
        pv = [p["r2_by_days"][k] for k in pdays]
        ax.plot(pd, pv, '-', color=PAT_COLORS[idx % len(PAT_COLORS)],
                alpha=0.35, linewidth=1, label=p["patient"] if idx < 11 else None)

    # Mean bold line
    ax.plot(days, mean_vals, 'k-o', linewidth=3, markersize=8,
            label='Mean R²', zorder=10)

    # "3 days = 94% of 30-day" annotation
    r2_3 = mean_r2["3"]
    r2_30 = mean_r2["30"]
    pct = r2_3 / r2_30 * 100
    ax.annotate(f"3 days → {r2_3:.3f}\n= {pct:.0f}% of 30-day ({r2_30:.3f})",
                xy=(3, r2_3), xytext=(6, r2_3 - 0.06),
                arrowprops=dict(arrowstyle='->', color='darkorange', lw=1.5),
                fontsize=ANNOT_SIZE, fontweight='bold', color='darkorange',
                bbox=dict(boxstyle='round,pad=0.3', fc='lightyellow',
                          ec='orange', alpha=0.9))

    # Diminishing returns shading
    ax.axvspan(3, 30, alpha=0.06, color='green')
    ax.text(12, mean_vals.min() - 0.02, "Diminishing returns zone",
            fontsize=9, color='green', alpha=0.7, ha='center')

    ax.set_xscale('log')
    ax.set_xticks(days)
    ax.set_xticklabels([str(d) for d in days])
    ax.set_xlabel("Days of Training Data (log scale)")
    ax.set_ylabel("R² Score")
    ax.set_title("Minimal Data Learning Curve: How Much Data Is Enough?")
    ax.legend(loc='lower right', ncol=3, fontsize=8, framealpha=0.9)
    fig.tight_layout()
    fig.savefig(OUT / "minimal_data_learning_curve.png", dpi=DPI)
    plt.close(fig)
    print("  ✓ minimal_data_learning_curve.png")


# ===================================================================
# Chart 5 – Longitudinal Stability (dual panel)
# ===================================================================
def chart_longitudinal_stability():
    _apply_style()
    data = load_experiment("exp-698*.json")
    patients = data["per_patient"]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=DUAL_FIG, sharey=True)

    canonical_days = np.array([30, 60, 90, 120, 150])

    for panel, key, ax, title in [
        (0, 'raw_decay', ax1, 'Raw Model Decay'),
        (1, 'clean_decay', ax2, 'Cleaned Model Stability'),
    ]:
        # Collect per-patient values, using NaN for missing days
        grid = np.full((len(patients), len(canonical_days)), np.nan)
        for idx, p in enumerate(patients):
            decay = p[key]
            for j, day in enumerate(canonical_days):
                val = decay.get(str(day))
                if val is not None:
                    grid[idx, j] = val
            # Plot individual trace (only available points)
            mask = ~np.isnan(grid[idx])
            ax.plot(canonical_days[mask], grid[idx][mask], '-',
                    color=PAT_COLORS[idx % len(PAT_COLORS)],
                    alpha=0.35, linewidth=1)

        # Bold mean line (nanmean handles gaps)
        mean_v = np.nanmean(grid, axis=0)
        ax.plot(canonical_days, mean_v, 'k-o', linewidth=3, markersize=6,
                label='Mean', zorder=10)
        ax.set_xlabel("Days Since Training")
        ax.set_title(title)
        ax.legend(loc='lower left')
        ax.set_xticks(canonical_days)

    ax1.set_ylabel("R² Score")
    fig.suptitle("Longitudinal Model Stability: Raw vs Cleaned", fontsize=TITLE_SIZE)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(OUT / "longitudinal_stability.png", dpi=DPI)
    plt.close(fig)
    print("  ✓ longitudinal_stability.png")


# ===================================================================
# Chart 6 – Prediction Interval Calibration
# ===================================================================
def chart_pi_calibration():
    _apply_style()
    data = load_experiment("exp-700*.json")
    patients = data["per_patient"]

    names = [p["patient"] for p in patients]
    cov = np.array([p["pi_coverage"] for p in patients])
    wid = np.array([p["pi_width"] for p in patients])
    mean_cov = data["mean_coverage"]

    fig, ax = plt.subplots(figsize=SINGLE_FIG)
    for idx, (w, c, n) in enumerate(zip(wid, cov, names)):
        ax.scatter(w, c, s=140, color=PAT_COLORS[idx % len(PAT_COLORS)],
                   edgecolors='black', linewidth=0.5, zorder=5, label=n)
        ax.annotate(n, (w, c), textcoords="offset points",
                    xytext=(6, 4), fontsize=ANNOT_SIZE, fontweight='bold')

    ax.axhline(90.0, ls='--', color='red', alpha=0.7, linewidth=1.5,
               label='90% target')
    ax.axhline(mean_cov, ls=':', color='blue', alpha=0.6, linewidth=1.5,
               label=f'Mean coverage {mean_cov:.1f}%')

    ax.set_xlabel("Prediction Interval Width (mg/dL)")
    ax.set_ylabel("PI Coverage (%)")
    ax.set_title("Prediction Interval Calibration: 90% Target")
    ax.legend(loc='lower right', ncol=3, fontsize=8, framealpha=0.9)
    ax.set_ylim(88, 96)
    fig.tight_layout()
    fig.savefig(OUT / "prediction_interval_calibration.png", dpi=DPI)
    plt.close(fig)
    print("  ✓ prediction_interval_calibration.png")


# ===================================================================
# Chart 7 – Horizon MAE Curve
# ===================================================================
def chart_horizon_mae():
    _apply_style()

    # Direct multi-horizon data
    h_short = np.array([30, 60, 120])
    mae_short = np.array([13.3, 17.2, 22.1])
    h_long = np.array([180, 240, 360])
    mae_long = np.array([25.1, 27.0, 28.9])

    # AR comparison
    h_ar = np.array([120, 180, 240, 360])
    direct_mae = np.array([23.9, 25.6, 26.7, 29.6])
    ar_mae = np.array([22.3, 26.2, 26.0, 29.3])

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=DUAL_FIG)

    # Left panel: model handoff
    ax1.plot(h_short, mae_short, 'o-', color='#1f77b4', linewidth=2.5,
             markersize=8, label='Short w48', zorder=5)
    ax1.plot(h_long, mae_long, 's-', color='#d62728', linewidth=2.5,
             markersize=8, label='Long w96', zorder=5)

    # Crossover region
    ax1.axvspan(120, 180, alpha=0.1, color='purple')
    ax1.annotate("Model\nhandoff", xy=(150, 23.5), fontsize=ANNOT_SIZE,
                 ha='center', color='purple', fontweight='bold')

    # Clinical annotations
    annotations = {30: "Immediate\ndosing", 60: "Meal\ntiming",
                   120: "Exercise\nplanning", 360: "Overnight\nforecast"}
    for h, label in annotations.items():
        mae_at = dict(zip(list(h_short) + list(h_long),
                          list(mae_short) + list(mae_long))).get(h, 27)
        ax1.annotate(label, xy=(h, mae_at), xytext=(h, mae_at + 2.5),
                     fontsize=8, ha='center', color='gray',
                     arrowprops=dict(arrowstyle='->', color='gray', lw=0.8))

    ax1.set_xlabel("Prediction Horizon (minutes)")
    ax1.set_ylabel("MAE (mg/dL)")
    ax1.set_title("Multi-Horizon Forecast Performance")
    ax1.legend(loc='upper left')

    # Right panel: direct vs AR
    ax2.plot(h_ar, direct_mae, 'o-', color='#1f77b4', linewidth=2,
             label='Direct forecast')
    ax2.plot(h_ar, ar_mae, 's--', color='#ff7f0e', linewidth=2,
             label='Autoregressive rollout')
    ax2.set_xlabel("Prediction Horizon (minutes)")
    ax2.set_ylabel("MAE (mg/dL)")
    ax2.set_title("Direct vs Autoregressive Comparison")
    ax2.legend(loc='upper left')

    fig.suptitle("Horizon MAE Analysis", fontsize=TITLE_SIZE)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(OUT / "horizon_mae_curve.png", dpi=DPI)
    plt.close(fig)
    print("  ✓ horizon_mae_curve.png")


# ===================================================================
# Chart 8 – Feature Ablation 2h vs 12h (diverging bar)
# ===================================================================
def chart_feature_ablation():
    _apply_style()

    channels = ['glucose', 'iob', 'cob', 'basal_rate', 'bolus',
                'carbs', 'time_sin', 'time_cos']
    sil_2h = np.array([-0.045, 0.090, 0.178, -0.004, 0.120,
                        0.090, 0.112, 0.120])
    sil_12h = np.array([-0.584, -0.564, -0.456, -0.296, 0.224,
                         -0.604, -0.526, -0.201])

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=DUAL_FIG, sharey=True)

    y = np.arange(len(channels))

    for ax, vals, title, scale_label in [
        (ax1, sil_2h, "2-hour window", "ΔSilhouette (2h)"),
        (ax2, sil_12h, "12-hour window", "ΔSilhouette (12h)"),
    ]:
        colors = ['#d62728' if v < 0 else '#2ca02c' for v in vals]
        ax.barh(y, vals, color=colors, edgecolor='white', height=0.6)
        ax.axvline(0, color='black', linewidth=0.8)
        ax.set_yticks(y)
        ax.set_yticklabels(channels)
        ax.set_xlabel(scale_label)
        ax.set_title(title)

        # Value labels
        for i, v in enumerate(vals):
            ha = 'left' if v >= 0 else 'right'
            offset = 0.01 if v >= 0 else -0.01
            ax.text(v + offset, i, f"{v:+.3f}", va='center', ha=ha,
                    fontsize=9, fontweight='bold')

    # Legend
    red_patch = mpatches.Patch(color='#d62728',
                               label='Negative = feature important (removal hurts)')
    green_patch = mpatches.Patch(color='#2ca02c',
                                 label='Positive = feature is noise (removal helps)')
    ax2.legend(handles=[red_patch, green_patch], loc='lower right',
               fontsize=8, framealpha=0.9)

    # Sensitivity annotation
    mean_abs_2h = np.mean(np.abs(sil_2h))
    mean_abs_12h = np.mean(np.abs(sil_12h))
    ratio = mean_abs_12h / mean_abs_2h if mean_abs_2h > 0 else 0
    fig.text(0.5, 0.01,
             f"Mean |ΔSilhouette|: 2h={mean_abs_2h:.3f}, 12h={mean_abs_12h:.3f}"
             f"  →  {ratio:.1f}× more sensitive at 12h",
             ha='center', fontsize=ANNOT_SIZE, fontweight='bold',
             color='purple')

    fig.suptitle("Feature Importance: Scale-Dependent Sensitivity",
                 fontsize=TITLE_SIZE)
    fig.tight_layout(rect=[0, 0.04, 1, 0.95])
    fig.savefig(OUT / "feature_ablation_comparison.png", dpi=DPI)
    plt.close(fig)
    print("  ✓ feature_ablation_comparison.png")


# ===================================================================
# Chart 9 – Window Size U-Curve
# ===================================================================
def chart_window_ucurve():
    _apply_style()

    windows = np.array([12, 24, 48, 72, 96, 144])
    labels = ["1h", "2h", "4h", "6h", "8h", "12h"]
    sils = np.array([-0.346, -0.367, -0.537, -0.544, -0.642, -0.339])

    # Add 7-day point
    windows_ext = np.append(windows, 2016)  # 7 days * 288 5-min samples ... using raw steps
    labels_ext = labels + ["7d"]
    sils_ext = np.append(sils, -0.301)

    fig, ax = plt.subplots(figsize=SINGLE_FIG)

    ax.plot(windows_ext, sils_ext, 'o-', color='#1f77b4', linewidth=2,
            markersize=10, zorder=5)

    # Highlight 12h optimal
    idx_12h = 5
    ax.scatter([windows[idx_12h]], [sils[idx_12h]], s=250, marker='*',
               color='gold', edgecolors='black', linewidth=1, zorder=10)
    ax.annotate("12h optimal", xy=(windows[idx_12h], sils[idx_12h]),
                xytext=(windows[idx_12h] + 20, sils[idx_12h] + 0.03),
                fontsize=ANNOT_SIZE, fontweight='bold', color='goldenrod',
                arrowprops=dict(arrowstyle='->', color='goldenrod'))

    # DIA confusion valley (4-8h = windows 48-96)
    ax.axvspan(48, 96, alpha=0.15, color='red')
    ax.text(72, sils.min() - 0.03, "Insulin DIA\nconfusion valley\n(4–8h)",
            ha='center', fontsize=9, color='red', fontweight='bold')

    # 7-day star
    ax.scatter([2016], [-0.301], s=250, marker='*', color='limegreen',
               edgecolors='black', linewidth=1, zorder=10)
    ax.annotate("7-day\n(best)", xy=(2016, -0.301),
                xytext=(2016, -0.26),
                fontsize=ANNOT_SIZE, fontweight='bold', color='green',
                ha='center')

    ax.set_xticks(windows_ext)
    ax.set_xticklabels(labels_ext)
    ax.set_xlabel("Window Size")
    ax.set_ylabel("Silhouette Score (higher = better clustering)")
    ax.set_title("Window Size vs Clustering Quality: U-Curve Pattern")

    fig.tight_layout()
    fig.savefig(OUT / "window_silhouette_ucurve.png", dpi=DPI)
    plt.close(fig)
    print("  ✓ window_silhouette_ucurve.png")


# ===================================================================
# Chart 10 – Basal Assessment
# ===================================================================
def chart_basal_assessment():
    _apply_style()
    data = load_experiment("exp-693*.json")
    dist = data["assessment_distribution"]
    patients = data["per_patient"]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=DUAL_FIG)

    # Left: Pie chart
    pie_labels = []
    pie_sizes = []
    pie_colors = []
    color_map = {
        'basal_too_high': ('#d62728', 'Too High'),
        'basal_slightly_high': ('#ff7f0e', 'Slightly High'),
        'basal_appropriate': ('#2ca02c', 'Appropriate'),
        'basal_too_low': ('#1f77b4', 'Too Low'),
    }
    for key, (color, label) in color_map.items():
        if key in dist:
            pie_labels.append(f"{label} ({dist[key]})")
            pie_sizes.append(dist[key])
            pie_colors.append(color)

    wedges, texts, autotexts = ax1.pie(
        pie_sizes, labels=pie_labels, colors=pie_colors,
        autopct='%1.0f%%', startangle=90, textprops={'fontsize': 10})
    for at in autotexts:
        at.set_fontweight('bold')
    ax1.set_title("Basal Rate Assessment Distribution")
    ax1.text(0, -1.3, f"Mean overnight TIR: {data['mean_overnight_tir']:.1f}%",
             ha='center', fontsize=ANNOT_SIZE, fontweight='bold')

    # Right: Per-patient overnight TIR coloured by assessment
    assessment_color = {
        'too_high': '#d62728',
        'slightly_high': '#ff7f0e',
        'appropriate': '#2ca02c',
        'too_low': '#1f77b4',
    }
    # Sort by overnight_tir
    patients.sort(key=lambda p: p['overnight_tir'])
    names = [p['patient'] for p in patients]
    tir_vals = [p['overnight_tir'] for p in patients]
    bar_colors = [assessment_color.get(p['assessment'], 'gray') for p in patients]

    y = np.arange(len(names))
    ax2.barh(y, tir_vals, color=bar_colors, edgecolor='white', height=0.7)
    ax2.set_yticks(y)
    ax2.set_yticklabels(names)
    ax2.set_xlabel("Overnight TIR (%)")
    ax2.set_title("Overnight TIR by Patient")
    ax2.axvline(70, ls='--', color='green', alpha=0.6, label='70% target')
    ax2.legend(loc='lower right')

    # Value labels
    for i, v in enumerate(tir_vals):
        ax2.text(v + 0.5, i, f"{v:.1f}%", va='center', fontsize=9)

    # Assessment legend
    handles = [mpatches.Patch(color=c, label=l)
               for l, c in [('Too High', '#d62728'),
                             ('Slightly High', '#ff7f0e'),
                             ('Appropriate', '#2ca02c'),
                             ('Too Low', '#1f77b4')]]
    ax2.legend(handles=handles, loc='lower right', fontsize=8, framealpha=0.9)

    fig.suptitle("Basal Rate Assessment (EXP-693)", fontsize=TITLE_SIZE)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(OUT / "basal_assessment.png", dpi=DPI)
    plt.close(fig)
    print("  ✓ basal_assessment.png")


# ===================================================================
# Main entry point
# ===================================================================
ALL_CHARTS = [
    ("R² Improvement Waterfall", chart_r2_waterfall),
    ("Clinical Dashboard Heatmap", chart_clinical_dashboard),
    ("TIR vs R² Paradox", chart_tir_vs_r2),
    ("Minimal Data Learning Curve", chart_minimal_data),
    ("Longitudinal Stability", chart_longitudinal_stability),
    ("Prediction Interval Calibration", chart_pi_calibration),
    ("Horizon MAE Curve", chart_horizon_mae),
    ("Feature Ablation Comparison", chart_feature_ablation),
    ("Window Silhouette U-Curve", chart_window_ucurve),
    ("Basal Assessment", chart_basal_assessment),
]


def main():
    OUT.mkdir(exist_ok=True)
    print(f"Generating {len(ALL_CHARTS)} charts → {OUT}/")
    for name, fn in ALL_CHARTS:
        try:
            fn()
        except Exception as exc:
            print(f"  ✗ {name}: {exc}")
            raise
    print(f"\nAll {len(ALL_CHARTS)} charts saved to {OUT}")


if __name__ == "__main__":
    main()
