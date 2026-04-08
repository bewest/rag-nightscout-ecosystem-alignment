#!/usr/bin/env python3
"""
Carb Estimation Survey (EXP-1341) — Figures
============================================

Generates visualizations from the corrected EXP-1341 results.
Reads actual experiment data from externals/experiments/ JSON files.

Figures:
  fig1 — 4-method distribution comparison (violin + box)
  fig2 — Correlation scatter: each method vs entered carbs
  fig3 — Per-patient oref0 vs physics comparison
  fig4 — Summary dashboard: hierarchy, ratios, correlations
"""

import json
import os
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'externals', 'experiments')
DPI = 150
np.random.seed(42)

# ── Color palette ────────────────────────────────────────────────────
C_PHYSICS   = '#5B8DEF'  # blue
C_OREF0     = '#F5A623'  # orange
C_EXCURSION = '#7ED321'  # green
C_LOOP_IRC  = '#D0021B'  # red
C_ENTERED   = '#9B9B9B'  # gray
C_BG        = '#FAFAFA'

METHOD_COLORS = {
    'physics': C_PHYSICS,
    'oref0': C_OREF0,
    'excursion_est': C_EXCURSION,
    'loop_irc': C_LOOP_IRC,
}
METHOD_LABELS = {
    'physics': 'Physics residual',
    'oref0': 'oref0 deviation',
    'excursion_est': 'Glucose excursion',
    'loop_irc': 'Loop IRC',
}
METHOD_ORDER = ['physics', 'oref0', 'excursion_est', 'loop_irc']


def load_data():
    """Load experiment results."""
    with open(os.path.join(DATA_DIR, 'exp-1341_carb_survey.json')) as f:
        summary = json.load(f)
    with open(os.path.join(DATA_DIR, 'exp-1341_carb_survey_detail.json')) as f:
        detail = json.load(f)
    return summary, detail['meals']


def fig1_method_distributions(meals):
    """Violin + box plots comparing all 4 methods."""
    fig, axes = plt.subplots(1, 2, figsize=(14, 5), facecolor=C_BG)
    fig.suptitle('Carb Estimation: 4-Method Distribution Comparison',
                 fontsize=14, fontweight='bold', y=0.98)

    # Left: All meals
    ax = axes[0]
    ax.set_facecolor(C_BG)
    data_all = []
    labels = []
    colors = []
    for method in METHOD_ORDER:
        vals = [m[method] for m in meals
                if m[method] is not None and not np.isnan(float(m[method]))]
        vals = np.clip(vals, 0, 100)  # clip for display
        data_all.append(vals)
        labels.append(METHOD_LABELS[method])
        colors.append(METHOD_COLORS[method])

    vp = ax.violinplot(data_all, positions=range(len(data_all)),
                       showmedians=False, showextrema=False)
    for i, body in enumerate(vp['bodies']):
        body.set_facecolor(colors[i])
        body.set_alpha(0.3)

    bp = ax.boxplot(data_all, positions=range(len(data_all)),
                    widths=0.15, patch_artist=True,
                    medianprops=dict(color='black', linewidth=2),
                    flierprops=dict(marker='.', markersize=2, alpha=0.3))
    for i, patch in enumerate(bp['boxes']):
        patch.set_facecolor(colors[i])
        patch.set_alpha(0.7)

    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=9, rotation=15, ha='right')
    ax.set_ylabel('Estimated carbs (g)')
    ax.set_title(f'All meals (n={len(meals):,})', fontsize=11)
    ax.set_ylim(-2, 100)
    ax.axhline(y=0, color='gray', linewidth=0.5, linestyle='-')

    # Right: Announced vs UAM for oref0 (the best calibrated method)
    ax = axes[1]
    ax.set_facecolor(C_BG)
    ann_meals = [m for m in meals if m['announced']]
    uam_meals = [m for m in meals if not m['announced']]

    data_split = []
    split_labels = []
    split_colors = []
    for method in METHOD_ORDER:
        ann_vals = [m[method] for m in ann_meals
                    if m[method] is not None and not np.isnan(float(m[method]))]
        uam_vals = [m[method] for m in uam_meals
                    if m[method] is not None and not np.isnan(float(m[method]))]
        data_split.extend([np.clip(ann_vals, 0, 100),
                           np.clip(uam_vals, 0, 100)])
        split_labels.extend([f'{METHOD_LABELS[method]}\nAnn.', f'\nUAM'])
        split_colors.extend([METHOD_COLORS[method], METHOD_COLORS[method]])

    positions = []
    pos = 0
    for i in range(4):
        positions.extend([pos, pos + 0.8])
        pos += 2.2

    bp2 = ax.boxplot(data_split, positions=positions,
                     widths=0.55, patch_artist=True,
                     medianprops=dict(color='black', linewidth=2),
                     flierprops=dict(marker='.', markersize=1, alpha=0.2))
    for i, patch in enumerate(bp2['boxes']):
        c = split_colors[i]
        patch.set_facecolor(c)
        patch.set_alpha(0.8 if i % 2 == 0 else 0.4)

    ax.set_xticks(positions)
    ax.set_xticklabels(split_labels, fontsize=7)
    ax.set_ylabel('Estimated carbs (g)')
    ax.set_title(f'Announced (n={len(ann_meals):,}) vs UAM (n={len(uam_meals):,})',
                 fontsize=11)
    ax.set_ylim(-2, 100)

    plt.tight_layout()
    path = os.path.join(OUT_DIR, 'fig1_method_distributions.png')
    fig.savefig(path, dpi=DPI, bbox_inches='tight', facecolor=C_BG)
    plt.close(fig)
    print(f'  Saved {path}')


def fig2_correlation_scatter(meals):
    """Scatter plots: each method vs entered carbs (announced only)."""
    fig, axes = plt.subplots(1, 4, figsize=(16, 4), facecolor=C_BG)
    fig.suptitle('Method Estimates vs Entered Carbs (announced meals)',
                 fontsize=13, fontweight='bold', y=1.02)

    ann_meals = [m for m in meals
                 if m['announced'] and m['entered_carbs'] > 0]

    for i, method in enumerate(METHOD_ORDER):
        ax = axes[i]
        ax.set_facecolor(C_BG)

        pairs = [(float(m[method]), float(m['entered_carbs']))
                 for m in ann_meals
                 if m[method] is not None and not np.isnan(float(m[method]))]
        if not pairs:
            continue

        est = np.array([p[0] for p in pairs])
        ent = np.array([p[1] for p in pairs])

        ax.scatter(ent, est, alpha=0.08, s=8,
                   color=METHOD_COLORS[method], edgecolors='none')

        # Correlation and trend line
        corr = np.corrcoef(est, ent)[0, 1]
        ratio = np.median(est) / np.median(ent)

        # Fit line
        z = np.polyfit(ent, est, 1)
        x_line = np.linspace(0, max(ent), 100)
        ax.plot(x_line, np.polyval(z, x_line),
                color=METHOD_COLORS[method], linewidth=2, alpha=0.8)

        # 1:1 reference
        ax.plot([0, 120], [0, 120], 'k--', alpha=0.3, linewidth=1)

        ax.set_xlim(0, 120)
        ax.set_ylim(0, 120)
        ax.set_xlabel('Entered carbs (g)')
        if i == 0:
            ax.set_ylabel('Estimated carbs (g)')
        ax.set_title(f'{METHOD_LABELS[method]}\nr={corr:.3f}, ratio={ratio:.2f}×',
                     fontsize=10)
        ax.set_aspect('equal')

    plt.tight_layout()
    path = os.path.join(OUT_DIR, 'fig2_correlation_scatter.png')
    fig.savefig(path, dpi=DPI, bbox_inches='tight', facecolor=C_BG)
    plt.close(fig)
    print(f'  Saved {path}')


def fig3_per_patient_comparison(summary):
    """Per-patient bar chart: oref0 vs physics vs entered."""
    per_patient = summary['per_patient']
    patients = [p['patient'] for p in per_patient]
    n = len(patients)

    fig, axes = plt.subplots(2, 1, figsize=(12, 8), facecolor=C_BG)
    fig.suptitle('Per-Patient Carb Estimation Comparison',
                 fontsize=14, fontweight='bold')

    # Top: medians by method
    ax = axes[0]
    ax.set_facecolor(C_BG)
    x = np.arange(n)
    width = 0.18

    for j, method in enumerate(METHOD_ORDER):
        key = f'{method}_stats' if method != 'excursion' else 'excursion_stats'
        vals = [p.get(key, {}).get('median', 0) for p in per_patient]
        ax.bar(x + (j - 1.5) * width, vals, width,
               color=METHOD_COLORS[method],
               label=METHOD_LABELS[method], alpha=0.8)

    # Entered carbs
    entered = [p.get('entered_stats', {}).get('median', 0) for p in per_patient]
    ax.scatter(x, entered, color=C_ENTERED, marker='D', s=60,
               zorder=5, label='Entered (median)', edgecolors='black', linewidths=0.5)

    ax.set_xticks(x)
    ax.set_xticklabels(patients)
    ax.set_ylabel('Median carb estimate (g)')
    ax.set_title('Method medians vs entered carbs per patient')
    ax.legend(fontsize=8, ncol=3, loc='upper left')
    ax.set_ylim(0, 90)

    # Bottom: UAM% and meals/day
    ax2 = axes[1]
    ax2.set_facecolor(C_BG)
    uam_pct = [p['pct_uam'] for p in per_patient]
    meals_per_day = [p['meals_per_day'] for p in per_patient]
    n_days = [p['n_days'] for p in per_patient]

    bars = ax2.bar(x - 0.15, uam_pct, 0.3, color='#FF6B6B', alpha=0.7,
                   label='UAM %')
    ax2.set_ylabel('UAM %', color='#FF6B6B')
    ax2.set_ylim(0, 105)

    ax3 = ax2.twinx()
    ax3.bar(x + 0.15, meals_per_day, 0.3, color='#4ECDC4', alpha=0.7,
            label='Meals/day')
    ax3.set_ylabel('Meals/day', color='#4ECDC4')

    # Mark short-data patients
    for i, nd in enumerate(n_days):
        if nd < 170:
            ax2.annotate(f'{nd:.0f}d', (x[i], uam_pct[i] + 2),
                         ha='center', fontsize=7, color='red')

    ax2.set_xticks(x)
    ax2.set_xticklabels(patients)
    ax2.set_title('UAM prevalence and meal detection rate')

    lines1, labels1 = ax2.get_legend_handles_labels()
    lines2, labels2 = ax3.get_legend_handles_labels()
    ax2.legend(lines1 + lines2, labels1 + labels2, fontsize=8, loc='upper right')

    plt.tight_layout()
    path = os.path.join(OUT_DIR, 'fig3_per_patient_comparison.png')
    fig.savefig(path, dpi=DPI, bbox_inches='tight', facecolor=C_BG)
    plt.close(fig)
    print(f'  Saved {path}')


def fig4_summary_dashboard(summary, meals):
    """Summary dashboard with key metrics."""
    fig = plt.figure(figsize=(14, 7), facecolor=C_BG)
    gs = fig.add_gridspec(2, 3, hspace=0.35, wspace=0.3)
    fig.suptitle('EXP-1341: Multi-Algorithm Carb Estimation Survey — Summary',
                 fontsize=14, fontweight='bold')

    pop = summary['population']

    # ── Panel 1: Method hierarchy (horizontal bar) ──────────────────
    ax1 = fig.add_subplot(gs[0, 0])
    ax1.set_facecolor(C_BG)
    methods = METHOD_ORDER
    medians = [pop[m.replace('_est', '')]['all']['median'] for m in methods]
    y_pos = np.arange(len(methods))

    ax1.barh(y_pos, medians,
             color=[METHOD_COLORS[m] for m in methods], alpha=0.8, height=0.6)
    ax1.set_yticks(y_pos)
    ax1.set_yticklabels([METHOD_LABELS[m] for m in methods], fontsize=9)
    ax1.set_xlabel('Median estimate (g)')
    ax1.set_title('Method Hierarchy', fontsize=11, fontweight='bold')
    ax1.axvline(x=pop['entered']['median'], color=C_ENTERED, linestyle='--',
                linewidth=2, label=f"Entered ({pop['entered']['median']}g)")
    ax1.legend(fontsize=8)
    for i, v in enumerate(medians):
        ax1.text(v + 0.5, i, f'{v}g', va='center', fontsize=9, fontweight='bold')

    # ── Panel 2: Correlation ranking ────────────────────────────────
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.set_facecolor(C_BG)

    ann_meals = [m for m in meals if m['announced'] and m['entered_carbs'] > 0]
    corrs = {}
    for method in methods:
        pairs = [(float(m[method]), float(m['entered_carbs']))
                 for m in ann_meals
                 if m[method] is not None and not np.isnan(float(m[method]))]
        if len(pairs) > 10:
            est = np.array([p[0] for p in pairs])
            ent = np.array([p[1] for p in pairs])
            corrs[method] = float(np.corrcoef(est, ent)[0, 1])

    sorted_methods = sorted(corrs.keys(), key=lambda m: corrs[m], reverse=True)
    y_pos = np.arange(len(sorted_methods))
    ax2.barh(y_pos, [corrs[m] for m in sorted_methods],
             color=[METHOD_COLORS[m] for m in sorted_methods], alpha=0.8, height=0.6)
    ax2.set_yticks(y_pos)
    ax2.set_yticklabels([METHOD_LABELS[m] for m in sorted_methods], fontsize=9)
    ax2.set_xlabel('Correlation (r)')
    ax2.set_title('Correlation with Entered Carbs', fontsize=11, fontweight='bold')
    ax2.set_xlim(0, 0.45)
    for i, m in enumerate(sorted_methods):
        ax2.text(corrs[m] + 0.005, i, f'r={corrs[m]:.3f}', va='center',
                 fontsize=9, fontweight='bold')

    # ── Panel 3: Ratio vs entered ───────────────────────────────────
    ax3 = fig.add_subplot(gs[0, 2])
    ax3.set_facecolor(C_BG)
    ratios = {}
    for method in methods:
        ann_key = method.replace('_est', '')
        ann_med = pop[ann_key]['announced']['median']
        ent_med = pop['entered']['median']
        ratios[method] = ann_med / ent_med

    sorted_by_ratio = sorted(ratios.keys(),
                             key=lambda m: abs(1 - ratios[m]))
    y_pos = np.arange(len(sorted_by_ratio))
    ratio_vals = [ratios[m] for m in sorted_by_ratio]
    ax3.barh(y_pos, ratio_vals,
             color=[METHOD_COLORS[m] for m in sorted_by_ratio], alpha=0.8, height=0.6)
    ax3.set_yticks(y_pos)
    ax3.set_yticklabels([METHOD_LABELS[m] for m in sorted_by_ratio], fontsize=9)
    ax3.set_xlabel('Ratio (method / entered)')
    ax3.set_title('Calibration (1.0 = perfect)', fontsize=11, fontweight='bold')
    ax3.axvline(x=1.0, color='black', linestyle='--', linewidth=1.5, alpha=0.5)
    ax3.set_xlim(0, 1.2)
    for i, v in enumerate(ratio_vals):
        ax3.text(v + 0.01, i, f'{v:.2f}×', va='center', fontsize=9, fontweight='bold')

    # ── Panel 4: UAM vs Announced split ─────────────────────────────
    ax4 = fig.add_subplot(gs[1, 0])
    ax4.set_facecolor(C_BG)
    x = np.arange(len(methods))
    width = 0.35
    ann_meds = [pop[m.replace('_est', '')]['announced']['median'] for m in methods]
    uam_meds = [pop[m.replace('_est', '')]['uam']['median'] for m in methods]

    ax4.bar(x - width/2, ann_meds, width, color=[METHOD_COLORS[m] for m in methods],
            alpha=0.9, label='Announced')
    ax4.bar(x + width/2, uam_meds, width, color=[METHOD_COLORS[m] for m in methods],
            alpha=0.4, label='UAM')

    ax4.set_xticks(x)
    ax4.set_xticklabels([METHOD_LABELS[m].split()[0] for m in methods], fontsize=9)
    ax4.set_ylabel('Median (g)')
    ax4.set_title('Announced vs UAM', fontsize=11, fontweight='bold')
    ax4.legend(fontsize=8)

    # ── Panel 5: By meal window ─────────────────────────────────────
    ax5 = fig.add_subplot(gs[1, 1])
    ax5.set_facecolor(C_BG)
    windows = ['breakfast', 'lunch', 'dinner', 'snack']
    window_labels = ['Breakfast', 'Lunch', 'Dinner', 'Snack']
    x = np.arange(len(windows))
    width = 0.18

    for j, method in enumerate(methods):
        vals = []
        for w in windows:
            w_meals = [m for m in meals if m['window'] == w]
            w_vals = [float(m[method]) for m in w_meals
                      if m[method] is not None and not np.isnan(float(m[method]))]
            vals.append(np.median(w_vals) if w_vals else 0)
        ax5.bar(x + (j - 1.5) * width, vals, width,
                color=METHOD_COLORS[method], alpha=0.8,
                label=METHOD_LABELS[method])

    ax5.set_xticks(x)
    ax5.set_xticklabels(window_labels, fontsize=9)
    ax5.set_ylabel('Median (g)')
    ax5.set_title('By Meal Window', fontsize=11, fontweight='bold')
    ax5.legend(fontsize=7, ncol=2)

    # ── Panel 6: Key findings text ──────────────────────────────────
    ax6 = fig.add_subplot(gs[1, 2])
    ax6.set_facecolor(C_BG)
    ax6.axis('off')

    n_total = summary['n_meals']
    pct_uam = summary['pct_uam']

    findings = (
        f"Key Findings\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• {n_total:,} meals, {pct_uam}% UAM\n"
        f"• oref0 best correlation (r=0.368)\n"
        f"  & closest to entered (0.93×)\n"
        f"• Physics most aggressive (22.6g)\n"
        f"  but lowest correlation (r=0.093)\n"
        f"• Loop IRC most conservative (5.6g)\n"
        f"  but 2nd best correlation (r=0.334)\n"
        f"• ~4× gap: oref0 vs Loop IRC\n"
        f"  explains Loop's slow UAM response\n"
        f"• Entered carbs ≠ ground truth\n"
        f"  (r < 0.37 for all methods)"
    )
    ax6.text(0.05, 0.95, findings, transform=ax6.transAxes,
             fontsize=9, verticalalignment='top', fontfamily='monospace',
             bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

    path = os.path.join(OUT_DIR, 'fig4_summary_dashboard.png')
    fig.savefig(path, dpi=DPI, bbox_inches='tight', facecolor=C_BG)
    plt.close(fig)
    print(f'  Saved {path}')


if __name__ == '__main__':
    print('Loading EXP-1341 data...')
    summary, meals = load_data()
    print(f'  {len(meals):,} meals loaded')

    print('Generating figures...')
    fig1_method_distributions(meals)
    fig2_correlation_scatter(meals)
    fig3_per_patient_comparison(summary)
    fig4_summary_dashboard(summary, meals)
    print('Done.')
