#!/usr/bin/env python3
"""Generate synthesis visualizations (fig37-43) for the Comprehensive Meal Data Science Synthesis report."""

import json
import sys
from pathlib import Path
import numpy as np

RESULTS_DIR = Path('externals/experiments')
VIZ_DIR = Path('visualizations/natural-experiments')
VIZ_DIR.mkdir(parents=True, exist_ok=True)


def load_json(name):
    with open(str(RESULTS_DIR / name)) as f:
        return json.load(f)


def generate_synthesis_visualizations():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyArrowPatch
    import matplotlib.patches as mpatches

    # Load all needed data
    d1551 = load_json('exp-1551_natural_experiments.json')
    d1559 = load_json('exp-1559_natural_experiments.json')
    d1561 = load_json('exp-1561_natural_experiments.json')
    d1569 = load_json('exp-1569_natural_experiments.json')
    d1571 = load_json('exp-1571_natural_experiments.json')

    # ================================================================
    # fig37: The Meal Counting Problem (Takeaway 1)
    # ================================================================
    fig, axes = plt.subplots(1, 3, figsize=(18, 5.5))
    fig.suptitle('Takeaway 1: Meal Count Is a Definition, Not a Fact', fontsize=14, fontweight='bold')

    # A) Bar chart of detection methods
    methods = ['Census\n(≥5g, 30m)', 'Medium\n(≥5g, 90m)', 'Therapy\n(≥18g, 90m)', 'UAM-inclusive\n(all excursions)']
    counts = [4072, 3272, 2619, 12060]
    colors = ['#3498db', '#2ecc71', '#e67e22', '#e74c3c']
    bars = axes[0].bar(methods, counts, color=colors, edgecolor='black', linewidth=0.5)
    for bar, cnt in zip(bars, counts):
        axes[0].text(bar.get_x() + bar.get_width()/2, bar.get_height() + 200,
                    f'{cnt:,}', ha='center', va='bottom', fontsize=10, fontweight='bold')
    axes[0].set_ylabel('Total Meals Detected')
    axes[0].set_title('A) Detection Method → Meal Count')
    axes[0].set_ylim(0, 14000)
    axes[0].grid(axis='y', alpha=0.3)

    # B) Quality vs quantity trade-off
    cfgs = ['A (≥5g/30m)', 'B (≥5g/90m)', 'C (≥18g/90m)']
    qualities = [0.923, 0.973, 0.979]
    mpds = [2.2, 1.8, 1.4]
    ax_q = axes[1]
    ax_m = ax_q.twinx()
    x = np.arange(len(cfgs))
    w = 0.35
    b1 = ax_q.bar(x - w/2, qualities, w, color='#2ecc71', alpha=0.8, label='Quality Score')
    b2 = ax_m.bar(x + w/2, mpds, w, color='#3498db', alpha=0.8, label='Meals/Day')
    ax_q.set_ylabel('Quality Score', color='#2ecc71')
    ax_m.set_ylabel('Meals per Day', color='#3498db')
    ax_q.set_ylim(0.9, 1.0)
    ax_m.set_ylim(0, 3)
    ax_q.set_xticks(x)
    ax_q.set_xticklabels(cfgs, fontsize=9)
    ax_q.set_title('B) Quality vs Quantity Trade-off')
    lines1, labels1 = ax_q.get_legend_handles_labels()
    lines2, labels2 = ax_m.get_legend_handles_labels()
    ax_q.legend(lines1 + lines2, labels1 + labels2, fontsize=8, loc='lower left')

    # C) 72-config landscape (meals/day vs regularity)
    grid = d1569['grid_summary']
    valid = [g for g in grid if g['n_meals'] > 0 and not (isinstance(g['mean_patient_std'], float) and np.isnan(g['mean_patient_std']))]
    mpd_vals = [g['meals_per_day'] for g in valid]
    std_vals = [g['mean_patient_std'] for g in valid]
    mc_vals = [g['min_carb_g'] for g in valid]
    sc = axes[2].scatter(mpd_vals, std_vals, c=mc_vals, cmap='RdYlGn_r', s=50, edgecolors='black',
                        linewidths=0.3, alpha=0.8)
    # Mark the knee
    knee = d1569['hypothesis_tests'].get('H2_knee_config', {})
    if knee:
        axes[2].scatter([knee['meals_per_day']], [knee['mean_patient_std']],
                       s=200, marker='*', c='red', zorder=5, edgecolors='black', linewidths=1)
        axes[2].annotate(f"Knee\n{knee['min_carb_g']}g/{knee['hysteresis_min']}m",
                        (knee['meals_per_day'], knee['mean_patient_std']),
                        textcoords='offset points', xytext=(15, 10), fontsize=8,
                        arrowprops=dict(arrowstyle='->', color='red'))
    plt.colorbar(sc, ax=axes[2], label='Min Carb (g)')
    axes[2].set_xlabel('Meals per Day')
    axes[2].set_ylabel('Mean Patient Std (h)')
    axes[2].set_title('C) 72-Config Parameter Space')
    axes[2].grid(alpha=0.3)

    plt.tight_layout(rect=[0, 0, 1, 0.93])
    plt.savefig(str(VIZ_DIR / 'fig37_synthesis_meal_counting.png'), dpi=150)
    plt.close()
    print("  ✓ fig37_synthesis_meal_counting.png")

    # ================================================================
    # fig38: ISF Normalization Re-Ranking (Takeaway 2)
    # ================================================================
    fig, axes = plt.subplots(1, 3, figsize=(18, 5.5))
    fig.suptitle('Takeaway 2: ISF Normalization Reveals Hidden Metabolic Burden', fontsize=14, fontweight='bold')

    pp = d1561['per_patient_isf']
    pats = sorted(pp.keys())
    isf_vals = [pp[p]['isf_mgdl'] for p in pats]
    raw_exc = [pp[p]['mean_raw_excursion'] for p in pats]
    isf_norm = [pp[p]['mean_isf_norm_excursion'] for p in pats]
    spectral = [pp[p]['mean_spectral_power'] / 1e6 for p in pats]

    # A) Bump chart: raw rank → ISF-norm rank
    raw_rank = np.argsort(np.argsort([-v for v in raw_exc]))  # descending
    norm_rank = np.argsort(np.argsort([-v for v in isf_norm]))  # descending

    tier_colors_map = {}
    if 'per_patient' in d1571:
        for p, t in d1571['per_patient'].items():
            tier_colors_map[p] = {'robust': '#2ecc71', 'moderate': '#f39c12', 'sensitive': '#e74c3c'}.get(t['tier'], 'gray')

    for i, p in enumerate(pats):
        color = tier_colors_map.get(p, 'steelblue')
        axes[0].plot([0, 1], [raw_rank[i] + 1, norm_rank[i] + 1], 'o-', color=color, linewidth=2, markersize=8)
        axes[0].text(-0.08, raw_rank[i] + 1, f'{p} ({raw_exc[i]:.0f})', ha='right', va='center', fontsize=8, color=color)
        axes[0].text(1.08, norm_rank[i] + 1, f'{p} ({isf_norm[i]:.2f})', ha='left', va='center', fontsize=8, color=color)

    axes[0].set_xlim(-0.3, 1.3)
    axes[0].set_ylim(0.3, len(pats) + 0.7)
    axes[0].invert_yaxis()
    axes[0].set_xticks([0, 1])
    axes[0].set_xticklabels(['Raw Excursion\n(mg/dL)', 'ISF-Normalized\n(correction-eq)'], fontsize=10)
    axes[0].set_ylabel('Rank (1 = highest)')
    axes[0].set_title('A) Rank Change: Raw → ISF-Normalized')
    axes[0].grid(axis='y', alpha=0.2)
    axes[0].set_yticks([])

    # B) ISF variation across patients
    sort_idx = np.argsort(isf_vals)
    sorted_pats = [pats[i] for i in sort_idx]
    sorted_isf = [isf_vals[i] for i in sort_idx]
    bar_colors = [tier_colors_map.get(p, 'steelblue') for p in sorted_pats]
    axes[1].barh(sorted_pats, sorted_isf, color=bar_colors, edgecolor='black', linewidth=0.5)
    axes[1].set_xlabel('Profile ISF (mg/dL per Unit)')
    axes[1].set_title(f'B) 4.5× ISF Variation Across Patients\n(range: {min(isf_vals):.0f}–{max(isf_vals):.0f} mg/dL/U)')
    axes[1].grid(axis='x', alpha=0.3)
    for i, (p, v) in enumerate(zip(sorted_pats, sorted_isf)):
        axes[1].text(v + 1, i, f'{v:.0f}', va='center', fontsize=8)

    # C) ISF-norm thresholds
    thresh_colors = []
    for v in isf_norm:
        if v < 1.0:
            thresh_colors.append('#2ecc71')
        elif v < 2.0:
            thresh_colors.append('#f39c12')
        else:
            thresh_colors.append('#e74c3c')
    sort_idx2 = np.argsort(isf_norm)
    sorted_pats2 = [pats[i] for i in sort_idx2]
    sorted_norm2 = [isf_norm[i] for i in sort_idx2]
    sorted_colors2 = [thresh_colors[i] for i in sort_idx2]
    axes[2].barh(sorted_pats2, sorted_norm2, color=sorted_colors2, edgecolor='black', linewidth=0.5)
    axes[2].axvline(1.0, color='orange', ls='--', alpha=0.7, label='<1.0: Well-managed')
    axes[2].axvline(2.0, color='red', ls='--', alpha=0.7, label='>2.0: Expensive')
    axes[2].set_xlabel('ISF-Normalized Excursion (correction-equivalents)')
    axes[2].set_title('C) Metabolic Burden Thresholds')
    axes[2].legend(fontsize=7, loc='lower right')
    axes[2].grid(axis='x', alpha=0.3)

    plt.tight_layout(rect=[0, 0, 1, 0.93])
    plt.savefig(str(VIZ_DIR / 'fig38_synthesis_isf_normalization.png'), dpi=150)
    plt.close()
    print("  ✓ fig38_synthesis_isf_normalization.png")

    # ================================================================
    # fig39: 2D Meal Quality Framework (Takeaway 3)
    # ================================================================
    fig, axes = plt.subplots(1, 2, figsize=(16, 6.5))
    fig.suptitle('Takeaway 3: Spectral Power × Excursion = 2D Meal Quality Framework', fontsize=14, fontweight='bold')

    # A) Per-patient scatter: ISF-norm excursion vs spectral power
    for i, p in enumerate(pats):
        color = tier_colors_map.get(p, 'steelblue')
        axes[0].scatter(isf_norm[i], spectral[i], s=100, c=color, edgecolors='black',
                       linewidths=0.5, zorder=3)
        axes[0].annotate(p, (isf_norm[i], spectral[i]), fontsize=9,
                        textcoords='offset points', xytext=(6, 4), fontweight='bold')

    # Quadrant lines and labels
    axes[0].axvline(1.5, color='gray', ls=':', alpha=0.4)
    axes[0].axhline(5.0, color='gray', ls=':', alpha=0.4)
    axes[0].text(0.5, 22, 'Well-Managed\n(low exc, high AID)', ha='center', fontsize=8, color='green', alpha=0.7,
                bbox=dict(boxstyle='round,pad=0.3', facecolor='lightgreen', alpha=0.3))
    axes[0].text(4.0, 22, 'AID Working Hard\nbut Still High', ha='center', fontsize=8, color='orange', alpha=0.7,
                bbox=dict(boxstyle='round,pad=0.3', facecolor='lightyellow', alpha=0.3))
    axes[0].text(0.5, 1.0, 'Low Excursion\nLow AID Activity', ha='center', fontsize=8, color='blue', alpha=0.7,
                bbox=dict(boxstyle='round,pad=0.3', facecolor='lightblue', alpha=0.3))
    axes[0].text(4.0, 1.0, 'Undertreated\n✗ Worst outcome', ha='center', fontsize=8, color='red', alpha=0.7,
                bbox=dict(boxstyle='round,pad=0.3', facecolor='lightyellow', alpha=0.3))

    corr = d1561['correlations']['isf_norm_vs_spectral_power']
    axes[0].set_xlabel('ISF-Normalized Excursion (correction-equivalents)')
    axes[0].set_ylabel('Spectral Power (×10⁶)')
    axes[0].set_title(f'A) Orthogonal Dimensions (r = {corr:.3f})')
    axes[0].grid(alpha=0.3)

    # B) Carb range: spectral power super-linear scaling
    carb_ranges = d1561['by_carb_range']
    range_labels = ['10–19g', '20–29g', '30–49g', '≥50g']
    range_keys = ['10-19g', '20-29g', '30-49g', '≥50g']

    exc_means = [carb_ranges[k]['raw_excursion_mean'] for k in range_keys]
    isf_means = [carb_ranges[k]['isf_norm_mean'] for k in range_keys]
    sp_means = [carb_ranges[k]['spectral_power_mean'] / 1e6 for k in range_keys]
    n_meals = [carb_ranges[k]['n'] for k in range_keys]

    x = np.arange(len(range_labels))
    w = 0.25

    ax_left = axes[1]
    ax_right = ax_left.twinx()

    b1 = ax_left.bar(x - w, exc_means, w, color='#3498db', alpha=0.8, label='Raw Excursion (mg/dL)')
    b2 = ax_left.bar(x, [v * 40 for v in isf_means], w, color='#e67e22', alpha=0.8, label='ISF-Norm (×40 scale)')
    b3 = ax_right.bar(x + w, sp_means, w, color='#e74c3c', alpha=0.8, label='Spectral Power (×10⁶)')

    ax_left.set_xticks(x)
    ax_left.set_xticklabels([f'{l}\n(n={n})' for l, n in zip(range_labels, n_meals)], fontsize=9)
    ax_left.set_ylabel('Excursion / ISF-Norm (scaled)')
    ax_right.set_ylabel('Spectral Power (×10⁶)', color='#e74c3c')
    ax_left.set_title('B) Super-Linear Spectral Scaling with Carb Size')

    lines1, labels1 = ax_left.get_legend_handles_labels()
    lines2, labels2 = ax_right.get_legend_handles_labels()
    ax_left.legend(lines1 + lines2, labels1 + labels2, fontsize=7, loc='upper left')

    # Add scaling annotations
    ratio = sp_means[-1] / sp_means[0] if sp_means[0] > 0 else 0
    ax_right.annotate(f'{ratio:.0f}× scaling', xy=(3, sp_means[-1]),
                     xytext=(2.2, sp_means[-1] * 0.85), fontsize=9, color='red',
                     arrowprops=dict(arrowstyle='->', color='red'))

    plt.tight_layout(rect=[0, 0, 1, 0.93])
    plt.savefig(str(VIZ_DIR / 'fig39_synthesis_2d_quality.png'), dpi=150)
    plt.close()
    print("  ✓ fig39_synthesis_2d_quality.png")

    # ================================================================
    # fig40: Carb Algorithm Disagreement (Takeaway 4)
    # ================================================================
    fig, axes = plt.subplots(1, 2, figsize=(15, 6))
    fig.suptitle('Takeaway 4: Four Algorithms, Four Different Realities', fontsize=14, fontweight='bold')

    # A) Algorithm comparison
    algos = ['Physics\nResidual', 'oref0\nDeviation', 'Glucose\nExcursion', 'Loop\nIRC']
    medians = [22.6, 21.8, 7.8, 5.6]
    correlations = [0.093, 0.368, 0.263, 0.334]
    algo_colors = ['#9b59b6', '#e74c3c', '#3498db', '#2ecc71']

    ax_med = axes[0]
    ax_corr = ax_med.twinx()
    x = np.arange(len(algos))
    w = 0.35
    b1 = ax_med.bar(x - w/2, medians, w, color=algo_colors, alpha=0.8, edgecolor='black', linewidth=0.5)
    b2 = ax_corr.bar(x + w/2, correlations, w, color=algo_colors, alpha=0.4, edgecolor='black',
                     linewidth=0.5, hatch='//')
    ax_med.axhline(30.0, color='gray', ls='--', alpha=0.5, label='Entered carbs median (30g)')
    ax_med.set_ylabel('Median Estimate (g)')
    ax_corr.set_ylabel('Correlation with Entered (r)')
    ax_med.set_xticks(x)
    ax_med.set_xticklabels(algos)
    ax_med.set_title('A) Median Estimates & Correlations')
    ax_med.set_ylim(0, 35)
    ax_corr.set_ylim(0, 0.5)

    # Add value labels
    for i, (m, c) in enumerate(zip(medians, correlations)):
        ax_med.text(i - w/2, m + 0.5, f'{m}g', ha='center', va='bottom', fontsize=9, fontweight='bold')
        ax_corr.text(i + w/2, c + 0.01, f'r={c:.3f}', ha='center', va='bottom', fontsize=8)

    legend_elements = [mpatches.Patch(facecolor='gray', alpha=0.8, label='Median estimate (g)'),
                      mpatches.Patch(facecolor='gray', alpha=0.4, hatch='//', label='Correlation (r)'),
                      plt.Line2D([0], [0], color='gray', ls='--', label='Entered carbs (30g)')]
    ax_med.legend(handles=legend_elements, fontsize=8, loc='upper right')

    # B) The 4x gap visualization
    uam_estimates = {'Physics': 23.6, 'oref0': 19.9, 'Excursion': 7.2, 'Loop IRC': 5.2}
    ann_estimates = {'Physics': 19.5, 'oref0': 27.9, 'Excursion': 10.0, 'Loop IRC': 8.0}

    x2 = np.arange(4)
    w2 = 0.35
    axes[1].bar(x2 - w2/2, list(ann_estimates.values()), w2, color='#3498db', alpha=0.8,
               label='Announced', edgecolor='black', linewidth=0.5)
    axes[1].bar(x2 + w2/2, list(uam_estimates.values()), w2, color='#e74c3c', alpha=0.8,
               label='Unannounced (76.5%)', edgecolor='black', linewidth=0.5)
    axes[1].set_xticks(x2)
    axes[1].set_xticklabels(list(uam_estimates.keys()))
    axes[1].set_ylabel('Median Carb Estimate (g)')
    axes[1].set_title('B) Announced vs Unannounced Estimates\n(76.5% of meals are UAM)')

    # Annotate the 4x gap
    axes[1].annotate('', xy=(3, 5.2), xytext=(1, 19.9),
                    arrowprops=dict(arrowstyle='<->', color='red', lw=2))
    axes[1].text(2.0, 14, '~4× gap\n(explains AID\nbehavior differences)', ha='center',
                fontsize=9, color='red', fontweight='bold',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='lightyellow', alpha=0.8))
    axes[1].legend(fontsize=9)
    axes[1].grid(axis='y', alpha=0.3)

    plt.tight_layout(rect=[0, 0, 1, 0.93])
    plt.savefig(str(VIZ_DIR / 'fig40_synthesis_carb_algorithms.png'), dpi=150)
    plt.close()
    print("  ✓ fig40_synthesis_carb_algorithms.png")

    # ================================================================
    # fig41: UAM Dominance + Bolus Timing (Takeaway 5)
    # ================================================================
    fig, axes = plt.subplots(1, 3, figsize=(18, 5.5))
    fig.suptitle('Takeaway 5: 76.5% Unannounced — Timing Beats Accuracy', fontsize=14, fontweight='bold')

    # A) Pie chart: announced vs unannounced
    sizes = [23.5, 76.5]
    labels_pie = ['Announced\n(23.5%)', 'Unannounced\nUAM (76.5%)']
    explode = (0, 0.05)
    wedges, texts, autotexts = axes[0].pie(sizes, explode=explode, labels=labels_pie,
                                           colors=['#3498db', '#e74c3c'], autopct='',
                                           startangle=90, textprops={'fontsize': 11})
    axes[0].set_title('A) Meal Announcement Status\n(n=12,060 meals)')

    # B) Announced vs Unannounced metabolic comparison
    ann_data = d1561['announcement_comparison']
    metrics = ['Raw Excursion\n(mg/dL)', 'ISF-Normalized\n(corr-eq)', 'Spectral Power\n(×10⁶)']
    ann_vals = [ann_data['announced']['mean_raw_excursion'],
                ann_data['announced']['mean_isf_norm_excursion'],
                ann_data['announced']['mean_spectral_power'] / 1e6]
    uam_vals = [ann_data['unannounced']['mean_raw_excursion'],
                ann_data['unannounced']['mean_isf_norm_excursion'],
                ann_data['unannounced']['mean_spectral_power'] / 1e6]

    x3 = np.arange(3)
    w3 = 0.35
    axes[1].bar(x3 - w3/2, ann_vals, w3, color='#3498db', alpha=0.8, label=f'Announced (n={ann_data["announced"]["n"]})')
    axes[1].bar(x3 + w3/2, uam_vals, w3, color='#e74c3c', alpha=0.8, label=f'Unannounced (n={ann_data["unannounced"]["n"]})')
    axes[1].set_xticks(x3)
    axes[1].set_xticklabels(metrics, fontsize=9)
    axes[1].set_title('B) The Paradox: Higher Raw, Lower ISF-Norm')
    axes[1].legend(fontsize=8)
    axes[1].grid(axis='y', alpha=0.3)

    # Annotate paradox arrows
    axes[1].annotate('+30%', xy=(0 + w3/2, uam_vals[0]), xytext=(0.3, uam_vals[0] + 10),
                    fontsize=9, color='red', fontweight='bold', arrowprops=dict(arrowstyle='->', color='red'))
    axes[1].annotate('−15%', xy=(1 + w3/2, uam_vals[1]), xytext=(1.3, uam_vals[1] + 0.3),
                    fontsize=9, color='green', fontweight='bold', arrowprops=dict(arrowstyle='->', color='green'))

    # C) Bolus timing vs dose (from EXP-1591-1598 findings)
    r2_labels = ['Bolus\nTiming', 'Bolus\nDose']
    r2_vals = [8.9, 0.8]
    bar_colors3 = ['#e74c3c', '#95a5a6']
    axes[2].bar(r2_labels, r2_vals, color=bar_colors3, edgecolor='black', linewidth=0.5, width=0.5)
    for i, (l, v) in enumerate(zip(r2_labels, r2_vals)):
        axes[2].text(i, v + 0.3, f'R²={v}%', ha='center', fontsize=11, fontweight='bold')

    # Add the 11x annotation
    axes[2].annotate('', xy=(0, 8.9), xytext=(1, 0.8),
                    arrowprops=dict(arrowstyle='<->', color='darkred', lw=2.5))
    axes[2].text(0.5, 5.5, '11×\nmore\nvariance', ha='center', fontsize=12, fontweight='bold',
                color='darkred', bbox=dict(boxstyle='round,pad=0.3', facecolor='lightyellow', alpha=0.8))
    axes[2].set_ylabel('Variance Explained (R²%)')
    axes[2].set_title('C) What Explains Excursion?\n(Timing >> Dose)')
    axes[2].set_ylim(0, 12)
    axes[2].grid(axis='y', alpha=0.3)

    plt.tight_layout(rect=[0, 0, 1, 0.93])
    plt.savefig(str(VIZ_DIR / 'fig41_synthesis_uam_timing.png'), dpi=150)
    plt.close()
    print("  ✓ fig41_synthesis_uam_timing.png")

    # ================================================================
    # fig42: Robustness Archetypes Summary (Takeaway 6)
    # ================================================================
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    fig.suptitle('Takeaway 6: 45% Robust, 36% Need Personalization — n_peaks Is the Triage Tool',
                fontsize=14, fontweight='bold')

    traits = d1571['per_patient']
    pats_sorted = sorted(traits.keys(), key=lambda p: traits[p]['sigma_sigma'])
    tier_colors = {'robust': '#2ecc71', 'moderate': '#f39c12', 'sensitive': '#e74c3c'}

    # A) σσ distribution with annotations
    ss_vals = [traits[p]['sigma_sigma'] for p in pats_sorted]
    colors_ss = [tier_colors[traits[p]['tier']] for p in pats_sorted]
    axes[0].barh(pats_sorted, ss_vals, color=colors_ss, edgecolor='black', linewidth=0.5)
    axes[0].axvline(0.6, color='orange', ls='--', alpha=0.7)
    axes[0].axvline(1.0, color='red', ls='--', alpha=0.7)

    # Tier labels
    axes[0].text(0.3, 7.5, 'ROBUST\n45%', fontsize=10, color='green', fontweight='bold', ha='center')
    axes[0].text(0.8, 7.5, 'MOD\n18%', fontsize=9, color='orange', fontweight='bold', ha='center')
    axes[0].text(1.6, 7.5, 'SENSITIVE\n36%', fontsize=10, color='red', fontweight='bold', ha='center')

    axes[0].set_xlabel('σσ (lower = more robust)')
    axes[0].set_title('A) Robustness Distribution')
    axes[0].grid(axis='x', alpha=0.3)

    # B) σσ vs n_peaks (THE key finding)
    for p in pats_sorted:
        t = traits[p]
        axes[1].scatter(t['n_peaks'], t['sigma_sigma'], s=120, c=tier_colors[t['tier']],
                       edgecolors='black', linewidths=0.7, zorder=3)
        axes[1].annotate(p, (t['n_peaks'], t['sigma_sigma']), fontsize=10,
                        fontweight='bold', textcoords='offset points', xytext=(6, 4))

    # Regression line
    peaks = [traits[p]['n_peaks'] for p in pats_sorted]
    sigmas = [traits[p]['sigma_sigma'] for p in pats_sorted]
    if len(set(peaks)) > 1:
        z = np.polyfit(peaks, sigmas, 1)
        xfit = np.linspace(0, max(peaks) + 0.5, 50)
        axes[1].plot(xfit, np.polyval(z, xfit), 'k--', alpha=0.4, linewidth=1.5)

    corr_data = d1571.get('correlations_with_sigma_sigma', {}).get('n_peaks', {})
    rho = corr_data.get('spearman_rho', -0.851)
    pval = corr_data.get('p_value', 0.0009)
    axes[1].set_xlabel('Number of Personal Meal Peaks')
    axes[1].set_ylabel('σσ (Robustness)')
    axes[1].set_title(f'B) THE Key Predictor\n(ρ = {rho:.3f}, p = {pval:.4f})')
    axes[1].grid(alpha=0.3)

    # Add interpretation box
    axes[1].text(3.5, 2.0, '3+ peaks = robust\n(redundancy creates\nresilience)', fontsize=9,
                ha='center', color='green', fontweight='bold',
                bbox=dict(boxstyle='round,pad=0.4', facecolor='lightgreen', alpha=0.4))
    axes[1].text(0.5, 0.5, '0–1 peaks = sensitive\n(single point of failure)', fontsize=9,
                ha='center', color='red', fontweight='bold',
                bbox=dict(boxstyle='round,pad=0.4', facecolor='lightyellow', alpha=0.4))

    # C) Clinical decision tree
    axes[2].set_xlim(0, 10)
    axes[2].set_ylim(0, 10)
    axes[2].axis('off')
    axes[2].set_title('C) Clinical Triage Decision Tree')

    # Root
    axes[2].text(5, 9.2, 'Count meal peaks', fontsize=11, ha='center', fontweight='bold',
                bbox=dict(boxstyle='round,pad=0.4', facecolor='lightblue', alpha=0.8))

    # Left branch: 3+ peaks
    axes[2].annotate('', xy=(2.5, 7.5), xytext=(4.2, 8.6),
                    arrowprops=dict(arrowstyle='->', lw=2, color='green'))
    axes[2].text(2.5, 7.3, '≥ 3 peaks', fontsize=10, ha='center', color='green', fontweight='bold')
    axes[2].text(2.5, 6.2, 'ROBUST (45%)\n─────────\n• Any config works\n• Focus on metabolic\n  analysis instead\n• Universal thresholds\n  are sufficient',
                fontsize=8, ha='center', va='top',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='#d5f5e3', alpha=0.8))

    # Middle branch: 2 peaks
    axes[2].annotate('', xy=(5, 7.5), xytext=(5, 8.6),
                    arrowprops=dict(arrowstyle='->', lw=2, color='orange'))
    axes[2].text(5, 7.3, '2 peaks', fontsize=10, ha='center', color='orange', fontweight='bold')
    axes[2].text(5, 6.2, 'MODERATE (18%)\n─────────\n• Monitor for\n  config sensitivity\n• May need light\n  tuning',
                fontsize=8, ha='center', va='top',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='#fef9e7', alpha=0.8))

    # Right branch: 0-1 peaks
    axes[2].annotate('', xy=(7.5, 7.5), xytext=(5.8, 8.6),
                    arrowprops=dict(arrowstyle='->', lw=2, color='red'))
    axes[2].text(7.5, 7.3, '0–1 peaks', fontsize=10, ha='center', color='red', fontweight='bold')
    axes[2].text(7.5, 6.2, 'SENSITIVE (36%)\n─────────\n• Per-patient config\n  optimization needed\n• Regularity swings\n  5+ hours by config\n• Reactive detection\n  only (no time-of-day)',
                fontsize=8, ha='center', va='top',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='#fdedec', alpha=0.8))

    plt.tight_layout(rect=[0, 0, 1, 0.92])
    plt.savefig(str(VIZ_DIR / 'fig42_synthesis_robustness.png'), dpi=150)
    plt.close()
    print("  ✓ fig42_synthesis_robustness.png")

    # ================================================================
    # fig43: The Detection-Sensitivity-Insight Trade-off (Takeaway 7 + Cross-cutting)
    # ================================================================
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    fig.suptitle('Takeaway 7: The AID Loop Is Signal — Decode It, Don\'t Remove It',
                fontsize=14, fontweight='bold')

    # A) AID distortion summary
    distortions = {
        'Excursion\nreduction': 30,
        'ISF inflation\n(effective/profile)': 36,
        'Carb estimate\n4× gap': 75,
        'Basal override\n(% non-scheduled)': 65,
        'Peak shift\n(minutes)': 15,
    }
    labels_d = list(distortions.keys())
    vals_d = list(distortions.values())
    colors_d = ['#3498db', '#e67e22', '#e74c3c', '#9b59b6', '#2ecc71']
    axes[0].barh(labels_d, vals_d, color=colors_d, edgecolor='black', linewidth=0.5)
    for i, v in enumerate(vals_d):
        axes[0].text(v + 1, i, f'{v}%', va='center', fontsize=10, fontweight='bold')
    axes[0].set_xlabel('Magnitude (%)')
    axes[0].set_title('A) How AID Distorts Meal Signals')
    axes[0].grid(axis='x', alpha=0.3)
    axes[0].set_xlim(0, 90)

    # B) The detection-sensitivity-insight trade-off curve
    valid_sorted = sorted([g for g in grid if g['n_meals'] > 0 and
                          not (isinstance(g['mean_patient_std'], float) and np.isnan(g['mean_patient_std']))],
                         key=lambda g: g['meals_per_day'])
    mpd_curve = [g['meals_per_day'] for g in valid_sorted]
    std_curve = [g['mean_patient_std'] for g in valid_sorted]
    isf_curve = [g.get('mean_isf_norm', 0) for g in valid_sorted]

    ax_std = axes[1]
    ax_isf = ax_std.twinx()
    ax_std.plot(mpd_curve, std_curve, 'o-', color='#3498db', markersize=3, alpha=0.6, label='Regularity (std, h)')
    ax_isf.plot(mpd_curve, isf_curve, 's-', color='#e74c3c', markersize=3, alpha=0.6, label='ISF-Norm Excursion')

    # Knee marker
    if knee:
        ax_std.axvline(knee['meals_per_day'], color='green', ls='--', alpha=0.5)
        ax_std.text(knee['meals_per_day'] + 0.05, max(std_curve) * 0.95, f"Knee\n{knee['meals_per_day']} mpd",
                   fontsize=8, color='green')

    ax_std.set_xlabel('Meals per Day')
    ax_std.set_ylabel('Regularity (Weighted Std, h)', color='#3498db')
    ax_isf.set_ylabel('ISF-Norm Excursion', color='#e74c3c')
    ax_std.set_title('B) The Trade-off Curve')
    lines_a, labels_a = ax_std.get_legend_handles_labels()
    lines_b, labels_b = ax_isf.get_legend_handles_labels()
    ax_std.legend(lines_a + lines_b, labels_a + labels_b, fontsize=8, loc='upper right')
    ax_std.grid(alpha=0.3)

    # C) Personalization gradient (from universal to personal)
    axes[2].set_xlim(0, 10)
    axes[2].set_ylim(0, 10)
    axes[2].axis('off')
    axes[2].set_title('C) The Personalization Gradient')

    levels = [
        (8.5, 'Universal', 'UAM threshold = 1.0 mg/dL/5min\n100% cross-patient transfer', '#2ecc71'),
        (7.0, 'Universal', 'Knee config: 5g/150min\n~80% performance', '#27ae60'),
        (5.5, 'Population', '2 meal clusters (controlled/high)\nARI=0.976 across patients', '#f1c40f'),
        (4.0, 'Per-Tier', 'n_peaks → robust/moderate/sensitive\nTier-specific recommendations', '#e67e22'),
        (2.5, 'Per-Patient', 'ISF normalization thresholds\nResponse-curve ISF (R²=0.805)', '#e74c3c'),
        (1.0, 'Fully Personal', 'Optimal detection config\n(sensitive patients only, 36%)', '#c0392b'),
    ]

    # Draw gradient background
    from matplotlib.patches import Rectangle
    for i, (y, level, desc, color) in enumerate(levels):
        rect = Rectangle((0.3, y - 0.55), 9.4, 1.0, facecolor=color, alpha=0.15, edgecolor=color, linewidth=1)
        axes[2].add_patch(rect)
        axes[2].text(1.0, y, level, fontsize=10, fontweight='bold', va='center', color=color)
        axes[2].text(3.5, y, desc, fontsize=8, va='center', color='black')

    # Arrow on right side
    axes[2].annotate('', xy=(9.5, 1.0), xytext=(9.5, 8.5),
                    arrowprops=dict(arrowstyle='<->', lw=2, color='gray'))
    axes[2].text(9.7, 4.8, 'More\npersonal', fontsize=8, ha='left', rotation=90, va='center', color='gray')

    plt.tight_layout(rect=[0, 0, 1, 0.92])
    plt.savefig(str(VIZ_DIR / 'fig43_synthesis_aid_signal.png'), dpi=150)
    plt.close()
    print("  ✓ fig43_synthesis_aid_signal.png")

    print("\n  All synthesis visualizations complete!")


if __name__ == '__main__':
    generate_synthesis_visualizations()
