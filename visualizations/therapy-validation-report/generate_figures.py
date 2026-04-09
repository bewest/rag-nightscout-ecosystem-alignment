#!/usr/bin/env python3
"""
Therapy Settings Validation Report — Figures
=============================================

Generates publication-quality visualizations for the therapy settings
validation report. Reads real experiment data from externals/experiments/.

Figures:
  fig01 — Cohort dashboard: grade distribution + TIR/CV/TBR heatmap
  fig02 — Basal: overnight drift per patient (train vs verify)
  fig03 — ISF: response curve fit quality + ratio distribution
  fig04 — CR: post-meal excursion distribution + CR impact sizing
  fig05 — Holdout stability: train vs verify grade/score scatter
  fig06 — Flag agreement: stacked bar of flag reproducibility
  fig07 — Recommendation consistency: Jaccard similarity per patient
  fig08 — Minimum data sensitivity: grade agreement vs data fraction
  fig09 — Safety: hypo episodes + TBR by patient
  fig10 — Evidence synthesis: key metrics summary dashboard

Usage:
    PYTHONPATH=tools python visualizations/therapy-validation-report/generate_figures.py
"""

import json
import os
import sys
from collections import defaultdict
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'externals', 'experiments')
DPI = 150
np.random.seed(42)

# ── Color palette (colorblind-friendly) ──────────────────────────────
C_BLUE    = '#5B8DEF'
C_ORANGE  = '#F5A623'
C_GREEN   = '#7ED321'
C_RED     = '#D0021B'
C_PURPLE  = '#9013FE'
C_TEAL    = '#50E3C2'
C_GRAY    = '#9B9B9B'
C_BG      = '#FAFAFA'
C_DARK    = '#2C3E50'

GRADE_COLORS = {'A': '#2ECC71', 'B': '#3498DB', 'C': '#F39C12', 'D': '#E74C3C'}
SAFETY_COLORS = {'low': '#2ECC71', 'moderate': '#F39C12', 'high': '#E67E22', 'critical': '#E74C3C'}


def _load(fname):
    """Load experiment JSON."""
    path = os.path.join(DATA_DIR, fname)
    if not os.path.exists(path):
        print(f'  Warning: {fname} not found, using placeholder data')
        return None
    with open(path) as f:
        return json.load(f)


def _savefig(fig, name):
    """Save figure to output directory."""
    path = os.path.join(OUT_DIR, name)
    fig.savefig(path, dpi=DPI, bbox_inches='tight', facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f'  → {name}')


# ═════════════════════════════════════════════════════════════════════════
# Figure 1: Cohort Dashboard
# ═════════════════════════════════════════════════════════════════════════

def fig01_cohort_dashboard():
    """Grade distribution + per-patient TIR/CV/TBR heatmap."""
    data = _load('exp-1521_therapy.json')
    if data is None:
        return

    patients = sorted(data['per_patient'], key=lambda p: p['v10_score'], reverse=True)
    pids = [p['patient'] for p in patients]

    fig = plt.figure(figsize=(16, 8), facecolor=C_BG)
    gs = GridSpec(2, 3, figure=fig, hspace=0.35, wspace=0.3)

    # Panel A: Grade distribution pie
    ax = fig.add_subplot(gs[0, 0])
    ax.set_facecolor(C_BG)
    grades = data['grade_distribution']
    grade_order = ['A', 'B', 'C', 'D']
    sizes = [grades.get(g, 0) for g in grade_order]
    colors = [GRADE_COLORS[g] for g in grade_order]
    labels = [f'Grade {g}\n(n={grades.get(g, 0)})' for g in grade_order]
    wedges, texts, autotexts = ax.pie(
        sizes, labels=labels, colors=colors, autopct='%1.0f%%',
        startangle=90, pctdistance=0.75)
    for t in autotexts:
        t.set_fontsize(9)
        t.set_fontweight('bold')
    ax.set_title('Grade Distribution (v10)', fontsize=12, fontweight='bold')

    # Panel B: v10 score bar chart
    ax = fig.add_subplot(gs[0, 1:])
    ax.set_facecolor(C_BG)
    scores = [p['v10_score'] for p in patients]
    bar_colors = [GRADE_COLORS[p['grade']] for p in patients]
    bars = ax.bar(range(len(pids)), scores, color=bar_colors, edgecolor='white', linewidth=0.5)
    ax.set_xticks(range(len(pids)))
    ax.set_xticklabels(pids, fontsize=10)
    ax.set_ylabel('v10 Composite Score', fontsize=11)
    ax.set_title('Per-Patient v10 Score (higher = better)', fontsize=12, fontweight='bold')
    ax.axhline(y=80, color=GRADE_COLORS['A'], linestyle='--', alpha=0.5, label='A threshold')
    ax.axhline(y=65, color=GRADE_COLORS['B'], linestyle='--', alpha=0.5, label='B threshold')
    ax.axhline(y=50, color=GRADE_COLORS['C'], linestyle='--', alpha=0.5, label='C threshold')
    ax.legend(fontsize=8, loc='upper right')
    ax.set_ylim(0, 100)
    for bar, score in zip(bars, scores):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
                f'{score:.0f}', ha='center', va='bottom', fontsize=8, fontweight='bold')

    # Panel C: TIR / CV / TBR heatmap
    ax = fig.add_subplot(gs[1, :])
    ax.set_facecolor(C_BG)
    metrics = ['tir', 'cv', 'overnight_drift', 'max_excursion']
    metric_labels = ['TIR %', 'CV %', 'Overnight Drift\n(mg/dL/h)', 'Post-meal P90\n(mg/dL)']
    targets = [70, 36, 5.0, 70.0]  # ADA targets/thresholds

    matrix = np.zeros((len(metrics), len(pids)))
    for j, p in enumerate(patients):
        for i, m in enumerate(metrics):
            matrix[i, j] = p[m]

    # Normalize each row for coloring
    im = ax.imshow(matrix, aspect='auto', cmap='RdYlGn')
    ax.set_xticks(range(len(pids)))
    ax.set_xticklabels(pids, fontsize=10)
    ax.set_yticks(range(len(metrics)))
    ax.set_yticklabels(metric_labels, fontsize=10)
    ax.set_title('Key Metrics Heatmap', fontsize=12, fontweight='bold')

    # Add text annotations
    for i in range(len(metrics)):
        for j in range(len(pids)):
            val = matrix[i, j]
            fmt = '.0f' if val > 10 else '.1f'
            color = 'white' if abs(val) > np.mean(matrix[i, :]) else 'black'
            ax.text(j, i, f'{val:{fmt}}', ha='center', va='center',
                    fontsize=8, fontweight='bold', color=color)

    fig.suptitle('EXP-1521: Therapy Assessment Cohort Dashboard (n=11)',
                 fontsize=14, fontweight='bold', y=1.02)
    _savefig(fig, 'fig01_cohort_dashboard.png')


# ═════════════════════════════════════════════════════════════════════════
# Figure 2: Basal Assessment — Overnight Drift
# ═════════════════════════════════════════════════════════════════════════

def fig02_basal_drift():
    """Overnight drift analysis: full data + train/verify comparison."""
    data_1521 = _load('exp-1521_therapy.json')
    data_1524 = _load('exp-1524_therapy.json')
    data_1331 = _load('exp-1331_therapy.json')

    fig, axes = plt.subplots(1, 3, figsize=(18, 6), facecolor=C_BG)

    # Panel A: Overnight drift bar (EXP-1331 basal ground truth)
    ax = axes[0]
    ax.set_facecolor(C_BG)
    if data_1331:
        pp = sorted(data_1331['per_patient'], key=lambda p: p['drift_mg_per_hour'])
        pids = [p['patient'] for p in pp]
        drifts = [p['drift_mg_per_hour'] for p in pp]
        colors = [C_GREEN if p['archetype'] == 'well-calibrated' else
                  C_ORANGE if p['archetype'] == 'needs-tuning' else C_RED
                  for p in pp]
        ax.barh(range(len(pids)), drifts, color=colors, edgecolor='white')
        ax.set_yticks(range(len(pids)))
        ax.set_yticklabels(pids, fontsize=10)
        ax.axvline(x=0, color=C_DARK, linewidth=1)
        ax.axvline(x=5, color=C_RED, linestyle='--', alpha=0.5, label='Flag threshold')
        ax.axvline(x=-5, color=C_RED, linestyle='--', alpha=0.5)
        ax.set_xlabel('Overnight Drift (mg/dL/h)', fontsize=11)
        ax.set_title('EXP-1331: Basal Ground Truth\n(drift direction)', fontsize=11, fontweight='bold')
        legend_elements = [
            mpatches.Patch(color=C_GREEN, label='Well-calibrated'),
            mpatches.Patch(color=C_ORANGE, label='Needs tuning'),
            mpatches.Patch(color=C_RED, label='Miscalibrated'),
        ]
        ax.legend(handles=legend_elements, fontsize=8, loc='lower right')

    # Panel B: Production pipeline drift (EXP-1521)
    ax = axes[1]
    ax.set_facecolor(C_BG)
    if data_1521:
        pp = sorted(data_1521['per_patient'], key=lambda p: p['overnight_drift'])
        pids = [p['patient'] for p in pp]
        drifts = [p['overnight_drift'] for p in pp]
        flagged = [p['basal_flag'] for p in pp]
        colors = [C_RED if f else C_GREEN for f in flagged]
        ax.barh(range(len(pids)), drifts, color=colors, edgecolor='white')
        ax.set_yticks(range(len(pids)))
        ax.set_yticklabels(pids, fontsize=10)
        ax.axvline(x=5, color=C_RED, linestyle='--', alpha=0.5, label='±5 flag threshold')
        ax.axvline(x=-5, color=C_RED, linestyle='--', alpha=0.5)
        ax.set_xlabel('Overnight Drift (mg/dL/h)', fontsize=11)
        ax.set_title('EXP-1521: Production Pipeline\nOvernight Drift', fontsize=11, fontweight='bold')
        legend_elements = [
            mpatches.Patch(color=C_RED, label='Basal flagged'),
            mpatches.Patch(color=C_GREEN, label='Basal OK'),
        ]
        ax.legend(handles=legend_elements, fontsize=8)

    # Panel C: Train vs Verify drift (EXP-1524)
    ax = axes[2]
    ax.set_facecolor(C_BG)
    if data_1524:
        pp = data_1524['per_patient']
        for p in pp:
            color = C_GREEN if p['flag_agrees'] else C_RED
            ax.scatter(p['train_drift'], p['verify_drift'],
                      color=color, s=100, edgecolors=C_DARK, linewidths=0.5, zorder=5)
            ax.annotate(p['patient'], (p['train_drift'], p['verify_drift']),
                       fontsize=8, ha='left', va='bottom')
        lim = max(abs(ax.get_xlim()[0]), abs(ax.get_xlim()[1]),
                  abs(ax.get_ylim()[0]), abs(ax.get_ylim()[1])) + 2
        ax.plot([-lim, lim], [-lim, lim], 'k--', alpha=0.3, label='Perfect agreement')
        ax.set_xlim(-lim, lim)
        ax.set_ylim(-lim, lim)
        ax.set_xlabel('Training Drift (mg/dL/h)', fontsize=11)
        ax.set_ylabel('Verification Drift (mg/dL/h)', fontsize=11)
        corr = data_1524.get('drift_correlation', 0)
        ax.set_title(f'EXP-1524: Drift Reproducibility\n(r={corr:.2f})',
                    fontsize=11, fontweight='bold')
        legend_elements = [
            mpatches.Patch(color=C_GREEN, label='Flag agrees'),
            mpatches.Patch(color=C_RED, label='Flag disagrees'),
        ]
        ax.legend(handles=legend_elements, fontsize=8)

    fig.suptitle('Basal Rate Assessment: Overnight Drift Analysis',
                 fontsize=14, fontweight='bold', y=1.02)
    _savefig(fig, 'fig02_basal_drift.png')


# ═════════════════════════════════════════════════════════════════════════
# Figure 3: ISF Response Curve Validation
# ═════════════════════════════════════════════════════════════════════════

def fig03_isf_validation():
    """ISF response curve quality + ratio distribution."""
    data_1301 = _load('exp-1301_therapy.json')
    data_1309 = _load('exp-1309_therapy.json')
    data_1525 = _load('exp-1525_therapy.json')

    fig, axes = plt.subplots(1, 3, figsize=(18, 6), facecolor=C_BG)

    # Panel A: ISF curve fit R² per patient (EXP-1301)
    ax = axes[0]
    ax.set_facecolor(C_BG)
    if data_1301:
        pp = sorted(data_1301['per_patient'], key=lambda p: p['mean_fit_r2'], reverse=True)
        pids = [p['patient'] for p in pp]
        r2s = [p['mean_fit_r2'] for p in pp]
        n_corr = [p['n_corrections'] for p in pp]
        colors = [C_GREEN if r > 0.75 else C_ORANGE if r > 0.5 else C_RED for r in r2s]
        bars = ax.bar(range(len(pids)), r2s, color=colors, edgecolor='white')
        ax.set_xticks(range(len(pids)))
        ax.set_xticklabels(pids, fontsize=10)
        ax.set_ylabel('R² (curve fit)', fontsize=11)
        ax.set_ylim(0, 1.0)
        ax.axhline(y=0.75, color=C_DARK, linestyle='--', alpha=0.3, label='Good fit')
        ax.set_title(f'EXP-1301: ISF Response Curve R²\n(mean={np.mean(r2s):.3f})',
                    fontsize=11, fontweight='bold')
        for bar, n in zip(bars, n_corr):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
                    f'n={n}', ha='center', va='bottom', fontsize=7)
        ax.legend(fontsize=8)

    # Panel B: ISF curve/profile ratio (EXP-1301)
    ax = axes[1]
    ax.set_facecolor(C_BG)
    if data_1301:
        pp = data_1301['per_patient']
        ratios = [p['curve_vs_profile_ratio'] for p in pp]
        pids = [p['patient'] for p in pp]
        colors = [C_RED if abs(r - 1) > 1.5 else C_ORANGE if abs(r - 1) > 0.5 else C_GREEN
                  for r in ratios]
        ax.bar(range(len(pids)), ratios, color=colors, edgecolor='white')
        ax.set_xticks(range(len(pids)))
        ax.set_xticklabels(pids, fontsize=10)
        ax.set_ylabel('Effective / Profile ISF Ratio', fontsize=11)
        ax.axhline(y=1.0, color=C_DARK, linewidth=2, label='Perfect match')
        ax.set_title(f'EXP-1301: ISF Mismatch Ratio\n(1.0 = profile correct)',
                    fontsize=11, fontweight='bold')
        ax.legend(fontsize=8)

    # Panel C: UAM augmentation R² improvement (EXP-1309)
    ax = axes[2]
    ax.set_facecolor(C_BG)
    if data_1309:
        pp = sorted(data_1309['per_patient'], key=lambda p: p['r2_improvement'], reverse=True)
        pids = [p['patient'] for p in pp]
        baseline = [p['r2_baseline'] for p in pp]
        augmented = [p['r2_augmented'] for p in pp]

        x = np.arange(len(pids))
        w = 0.35
        ax.bar(x - w/2, baseline, w, color=C_GRAY, label='Baseline R²', edgecolor='white')
        ax.bar(x + w/2, augmented, w, color=C_BLUE, label='UAM-augmented R²', edgecolor='white')
        ax.set_xticks(x)
        ax.set_xticklabels(pids, fontsize=10)
        ax.set_ylabel('R² (conservation model)', fontsize=11)
        ax.axhline(y=0, color=C_DARK, linewidth=0.5)
        improvement = data_1309.get('mean_r2_improvement', 0)
        ax.set_title(f'EXP-1309: UAM Augmentation\n(mean Δ={improvement:+.3f})',
                    fontsize=11, fontweight='bold')
        ax.legend(fontsize=8)

    fig.suptitle('ISF Validation: Response Curves & Conservation Model',
                 fontsize=14, fontweight='bold', y=1.02)
    _savefig(fig, 'fig03_isf_validation.png')


# ═════════════════════════════════════════════════════════════════════════
# Figure 4: CR / Carb Estimation Validation
# ═════════════════════════════════════════════════════════════════════════

def fig04_cr_validation():
    """Post-meal excursion + carb estimation method comparison."""
    data_1341 = _load('exp-1341_carb_survey.json')
    data_1521 = _load('exp-1521_therapy.json')
    data_1451 = _load('exp-1451_therapy.json')

    fig, axes = plt.subplots(1, 3, figsize=(18, 6), facecolor=C_BG)

    # Panel A: Post-meal excursion P90 per patient
    ax = axes[0]
    ax.set_facecolor(C_BG)
    if data_1521:
        pp = sorted(data_1521['per_patient'], key=lambda p: p['max_excursion'], reverse=True)
        pids = [p['patient'] for p in pp]
        exc = [p['max_excursion'] for p in pp]
        flagged = [p['cr_flag'] for p in pp]
        colors = [C_RED if f else C_GREEN for f in flagged]
        bars = ax.barh(range(len(pids)), exc, color=colors, edgecolor='white')
        ax.set_yticks(range(len(pids)))
        ax.set_yticklabels(pids, fontsize=10)
        ax.axvline(x=70, color=C_RED, linestyle='--', alpha=0.5, label='CR flag threshold')
        ax.set_xlabel('Post-meal Excursion P90 (mg/dL)', fontsize=11)
        ax.set_title('EXP-1521: Post-meal Excursion\n(CR adequacy signal)', fontsize=11, fontweight='bold')
        legend_elements = [
            mpatches.Patch(color=C_RED, label='CR flagged'),
            mpatches.Patch(color=C_GREEN, label='CR adequate'),
        ]
        ax.legend(handles=legend_elements, fontsize=8)

    # Panel B: Carb estimation method comparison (EXP-1341)
    ax = axes[1]
    ax.set_facecolor(C_BG)
    if data_1341:
        pop = data_1341['population']
        methods = ['physics', 'oref0', 'excursion', 'loop_irc']
        method_labels = ['Physics\nresidual', 'oref0\ndeviation', 'Glucose\nexcursion', 'Loop\nIRC']
        method_colors = [C_BLUE, C_ORANGE, C_GREEN, C_RED]
        medians = []
        for m in methods:
            if m in pop:
                medians.append(pop[m]['all']['median'])
            else:
                medians.append(0)

        bars = ax.bar(range(len(methods)), medians, color=method_colors, edgecolor='white')
        ax.set_xticks(range(len(methods)))
        ax.set_xticklabels(method_labels, fontsize=9)
        ax.set_ylabel('Median Estimated Carbs (g)', fontsize=11)
        ax.set_title(f'EXP-1341: Carb Estimation Methods\n(n={data_1341["n_meals"]:,} meals)',
                    fontsize=11, fontweight='bold')
        for bar, med in zip(bars, medians):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                    f'{med:.1f}g', ha='center', va='bottom', fontsize=9, fontweight='bold')

    # Panel C: CR impact sizing with CIs (EXP-1451)
    ax = axes[2]
    ax.set_facecolor(C_BG)
    if data_1451:
        pp = data_1451.get('per_patient', [])
        if pp:
            pp_sorted = sorted(pp, key=lambda p: p.get('cr_tir_delta', p.get('excursion_tir_gap', 0)), reverse=True)
            pids = [p.get('pid', p.get('patient', '?')) for p in pp_sorted]
            deltas = [p.get('cr_tir_delta', p.get('excursion_tir_gap', 0)) for p in pp_sorted]
            colors = [C_RED if d > 15 else C_ORANGE if d > 5 else C_GREEN for d in deltas]
            ax.barh(range(len(pids)), deltas, color=colors, edgecolor='white')
            ax.set_yticks(range(len(pids)))
            ax.set_yticklabels(pids, fontsize=10)
            ax.set_xlabel('TIR Gap (high vs low excursion windows) %', fontsize=10)
            ax.set_title('EXP-1451: CR Impact Sizing\n(TIR improvement potential)',
                        fontsize=11, fontweight='bold')

    fig.suptitle('Carb Ratio Validation: Excursion Analysis & Impact Sizing',
                 fontsize=14, fontweight='bold', y=1.02)
    _savefig(fig, 'fig04_cr_validation.png')


# ═════════════════════════════════════════════════════════════════════════
# Figure 5: Holdout Stability — Train vs Verify
# ═════════════════════════════════════════════════════════════════════════

def fig05_holdout_stability():
    """Train vs verify: score scatter + grade stability."""
    data_1522 = _load('exp-1522_therapy.json')
    if data_1522 is None:
        return

    fig, axes = plt.subplots(1, 2, figsize=(14, 6), facecolor=C_BG)

    # Panel A: Score scatter (train vs verify)
    ax = axes[0]
    ax.set_facecolor(C_BG)
    pp = data_1522['per_patient']
    for p in pp:
        color = C_GREEN if p['grade_stable'] else C_RED
        ax.scatter(p['train_score'], p['verify_score'],
                  color=color, s=120, edgecolors=C_DARK, linewidths=0.5, zorder=5)
        ax.annotate(p['patient'], (p['train_score'], p['verify_score']),
                   fontsize=9, ha='left', va='bottom', fontweight='bold')

    ax.plot([0, 100], [0, 100], 'k--', alpha=0.3, label='Perfect agreement')
    ax.set_xlabel('Training v10 Score', fontsize=12)
    ax.set_ylabel('Verification v10 Score', fontsize=12)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    agreement = data_1522.get('grade_agreement', 0)
    ax.set_title(f'v10 Score: Train vs Verify\n(grade agreement={agreement:.0f}%)',
                fontsize=12, fontweight='bold')
    legend_elements = [
        mpatches.Patch(color=C_GREEN, label='Same grade'),
        mpatches.Patch(color=C_RED, label='Grade changed'),
    ]
    ax.legend(handles=legend_elements, fontsize=9)

    # Panel B: Score delta distribution
    ax = axes[1]
    ax.set_facecolor(C_BG)
    deltas = [p['score_delta'] for p in pp]
    pids = [p['patient'] for p in pp]
    colors = [C_GREEN if abs(d) < 10 else C_ORANGE if abs(d) < 20 else C_RED for d in deltas]

    pp_sorted = sorted(zip(pids, deltas, colors), key=lambda x: x[1])
    pids_s = [x[0] for x in pp_sorted]
    deltas_s = [x[1] for x in pp_sorted]
    colors_s = [x[2] for x in pp_sorted]

    ax.barh(range(len(pids_s)), deltas_s, color=colors_s, edgecolor='white')
    ax.set_yticks(range(len(pids_s)))
    ax.set_yticklabels(pids_s, fontsize=10)
    ax.axvline(x=0, color=C_DARK, linewidth=1)
    ax.set_xlabel('Score Delta (verify − train)', fontsize=11)
    mean_delta = data_1522.get('mean_score_delta', 0)
    std_delta = data_1522.get('score_delta_std', 0)
    ax.set_title(f'v10 Score Shift\n(mean={mean_delta:+.1f}, σ={std_delta:.1f})',
                fontsize=12, fontweight='bold')

    fig.suptitle('EXP-1522: Holdout Validation — Training vs Verification Stability',
                 fontsize=14, fontweight='bold', y=1.02)
    _savefig(fig, 'fig05_holdout_stability.png')


# ═════════════════════════════════════════════════════════════════════════
# Figure 6: Flag Agreement
# ═════════════════════════════════════════════════════════════════════════

def fig06_flag_agreement():
    """Stacked bar of flag reproducibility across splits."""
    data_1523 = _load('exp-1523_therapy.json')
    if data_1523 is None:
        return

    fig, axes = plt.subplots(1, 2, figsize=(14, 6), facecolor=C_BG)

    # Panel A: Flag agreement rates
    ax = axes[0]
    ax.set_facecolor(C_BG)
    rates = data_1523.get('flag_agreement_rates', {})
    flag_names = ['basal_flag', 'cr_flag', 'cv_flag', 'tbr_flag']
    flag_labels = ['Basal\n(drift)', 'CR\n(excursion)', 'CV\n(variability)', 'TBR\n(hypo)']
    flag_colors = [C_BLUE, C_ORANGE, C_PURPLE, C_RED]

    values = [rates.get(f, 0) for f in flag_names]
    bars = ax.bar(range(len(flag_names)), values, color=flag_colors, edgecolor='white')
    ax.set_xticks(range(len(flag_names)))
    ax.set_xticklabels(flag_labels, fontsize=10)
    ax.set_ylabel('Agreement Rate (%)', fontsize=11)
    ax.set_ylim(0, 105)
    overall = data_1523.get('overall_agreement', 0)
    ax.axhline(y=overall, color=C_DARK, linestyle='--', alpha=0.5,
              label=f'Overall: {overall:.0f}%')
    ax.set_title('Flag Agreement: Train vs Verify', fontsize=12, fontweight='bold')
    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
                f'{val:.0f}%', ha='center', va='bottom', fontsize=10, fontweight='bold')
    ax.legend(fontsize=9)

    # Panel B: Per-patient agreement heatmap
    ax = axes[1]
    ax.set_facecolor(C_BG)
    pp = data_1523['per_patient']
    pids = [p['patient'] for p in pp]
    matrix = np.zeros((len(flag_names), len(pids)))
    for j, p in enumerate(pp):
        for i, f in enumerate(flag_names):
            matrix[i, j] = 1.0 if p.get(f'{f}_stable', False) else 0.0

    im = ax.imshow(matrix, aspect='auto', cmap='RdYlGn', vmin=0, vmax=1)
    ax.set_xticks(range(len(pids)))
    ax.set_xticklabels(pids, fontsize=10)
    ax.set_yticks(range(len(flag_names)))
    ax.set_yticklabels([l.replace('\n', ' ') for l in flag_labels], fontsize=10)
    ax.set_title('Per-Patient Flag Stability', fontsize=12, fontweight='bold')

    for i in range(len(flag_names)):
        for j in range(len(pids)):
            symbol = '✓' if matrix[i, j] == 1.0 else '✗'
            color = C_DARK if matrix[i, j] == 1.0 else 'white'
            ax.text(j, i, symbol, ha='center', va='center',
                    fontsize=12, fontweight='bold', color=color)

    fig.suptitle('EXP-1523: Detection Flag Reproducibility',
                 fontsize=14, fontweight='bold', y=1.02)
    _savefig(fig, 'fig06_flag_agreement.png')


# ═════════════════════════════════════════════════════════════════════════
# Figure 7: Recommendation Consistency
# ═════════════════════════════════════════════════════════════════════════

def fig07_recommendation_consistency():
    """Jaccard similarity of recommendations per patient."""
    data_1527 = _load('exp-1527_therapy.json')
    if data_1527 is None:
        return

    fig, axes = plt.subplots(1, 2, figsize=(14, 6), facecolor=C_BG)

    pp = data_1527['per_patient']

    # Panel A: Jaccard similarity bar chart
    ax = axes[0]
    ax.set_facecolor(C_BG)
    pp_sorted = sorted(pp, key=lambda p: p['jaccard_similarity'], reverse=True)
    pids = [p['patient'] for p in pp_sorted]
    jaccards = [p['jaccard_similarity'] for p in pp_sorted]
    colors = [C_GREEN if j >= 0.8 else C_ORANGE if j >= 0.5 else C_RED for j in jaccards]

    bars = ax.bar(range(len(pids)), jaccards, color=colors, edgecolor='white')
    ax.set_xticks(range(len(pids)))
    ax.set_xticklabels(pids, fontsize=10)
    ax.set_ylabel('Jaccard Similarity', fontsize=11)
    ax.set_ylim(0, 1.1)
    mean_j = data_1527.get('mean_jaccard', 0)
    ax.axhline(y=mean_j, color=C_DARK, linestyle='--', alpha=0.5,
              label=f'Mean: {mean_j:.2f}')
    ax.set_title('Recommendation Consistency\n(train vs verify)', fontsize=12, fontweight='bold')
    for bar, j in zip(bars, jaccards):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
                f'{j:.2f}', ha='center', va='bottom', fontsize=9, fontweight='bold')
    ax.legend(fontsize=9)

    # Panel B: Recommendation set comparison
    ax = axes[1]
    ax.set_facecolor(C_BG)
    ax.set_xlim(0, 10)
    ax.set_ylim(-0.5, len(pp) - 0.5)
    ax.set_yticks(range(len(pp)))
    ax.set_yticklabels([p['patient'] for p in pp], fontsize=10)
    ax.set_xlabel('Recommendations', fontsize=11)
    ax.set_title('Shared vs Unique Recommendations', fontsize=12, fontweight='bold')

    for i, p in enumerate(pp):
        n_shared = p['n_shared']
        n_train_only = p['n_train'] - n_shared
        n_verify_only = p['n_verify'] - n_shared
        ax.barh(i, n_shared, color=C_GREEN, edgecolor='white', label='Shared' if i == 0 else '')
        ax.barh(i, n_train_only, left=n_shared, color=C_BLUE, edgecolor='white',
               label='Train only' if i == 0 else '')
        ax.barh(i, n_verify_only, left=n_shared + n_train_only, color=C_ORANGE,
               edgecolor='white', label='Verify only' if i == 0 else '')

    ax.legend(fontsize=9, loc='lower right')

    fig.suptitle('EXP-1527: Recommendation Reproducibility',
                 fontsize=14, fontweight='bold', y=1.02)
    _savefig(fig, 'fig07_recommendation_consistency.png')


# ═════════════════════════════════════════════════════════════════════════
# Figure 8: Minimum Data Sensitivity
# ═════════════════════════════════════════════════════════════════════════

def fig08_minimum_data():
    """Grade agreement vs data fraction learning curve."""
    data_1528 = _load('exp-1528_therapy.json')
    if data_1528 is None:
        return

    fig, axes = plt.subplots(1, 2, figsize=(14, 6), facecolor=C_BG)

    fracs = data_1528['per_fraction']

    # Panel A: Grade agreement curve
    ax = axes[0]
    ax.set_facecolor(C_BG)
    days = [f['n_days_approx'] for f in fracs]
    agreement = [f['grade_agreement_pct'] for f in fracs]
    ax.plot(days, agreement, 'o-', color=C_BLUE, linewidth=2, markersize=10, zorder=5)
    ax.fill_between(days, agreement, alpha=0.1, color=C_BLUE)
    ax.set_xlabel('Days of Data', fontsize=12)
    ax.set_ylabel('Grade Agreement with Full Data (%)', fontsize=11)
    ax.set_ylim(0, 105)
    ax.axhline(y=90, color=C_GREEN, linestyle='--', alpha=0.5, label='90% threshold')
    ax.set_title('Grade Stability vs Data Volume', fontsize=12, fontweight='bold')
    ax.legend(fontsize=9)
    for d, a in zip(days, agreement):
        ax.annotate(f'{a:.0f}%', (d, a), textcoords='offset points',
                   xytext=(0, 10), ha='center', fontsize=9, fontweight='bold')

    # Panel B: Score delta vs data fraction
    ax = axes[1]
    ax.set_facecolor(C_BG)
    score_deltas = [f['mean_score_delta'] for f in fracs]
    score_stds = [f['score_delta_std'] for f in fracs]
    ax.errorbar(days, score_deltas, yerr=score_stds, fmt='o-', color=C_ORANGE,
               linewidth=2, markersize=10, capsize=5, zorder=5)
    ax.axhline(y=0, color=C_DARK, linewidth=1)
    ax.set_xlabel('Days of Data', fontsize=12)
    ax.set_ylabel('Score Delta vs Full Data', fontsize=11)
    ax.set_title('Score Bias vs Data Volume', fontsize=12, fontweight='bold')
    for d, s in zip(days, score_deltas):
        ax.annotate(f'{s:+.1f}', (d, s), textcoords='offset points',
                   xytext=(0, 12), ha='center', fontsize=9, fontweight='bold')

    fig.suptitle('EXP-1528: Minimum Data Requirements for Reliable Assessment',
                 fontsize=14, fontweight='bold', y=1.02)
    _savefig(fig, 'fig08_minimum_data.png')


# ═════════════════════════════════════════════════════════════════════════
# Figure 9: Safety — Hypo Episodes & TBR
# ═════════════════════════════════════════════════════════════════════════

def fig09_safety():
    """Hypo episode analysis + TBR by patient."""
    data_1521 = _load('exp-1521_therapy.json')
    data_1501 = _load('exp-1501_therapy.json')
    if data_1521 is None:
        return

    fig, axes = plt.subplots(1, 3, figsize=(18, 6), facecolor=C_BG)

    # Panel A: TBR per patient
    ax = axes[0]
    ax.set_facecolor(C_BG)
    pp = sorted(data_1521['per_patient'],
                key=lambda p: p.get('tbr_total', 0),
                reverse=True)
    pids = [p['patient'] for p in pp]
    tbr_vals = [p.get('tbr_total', 0) for p in pp]
    flagged = [p.get('tbr_flag', False) for p in pp]
    colors = [C_RED if f else C_GREEN for f in flagged]
    bars = ax.bar(range(len(pids)), tbr_vals, color=colors, edgecolor='white')
    ax.axhline(y=4, color=C_DARK, linestyle='--', alpha=0.5, label='ADA 4% target')
    ax.set_xticks(range(len(pids)))
    ax.set_xticklabels(pids, fontsize=10)
    ax.set_ylabel('Time Below Range (%)', fontsize=11)
    ax.set_title('TBR by Patient', fontsize=11, fontweight='bold')
    for bar, v in zip(bars, tbr_vals):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.2,
                f'{v:.1f}%', ha='center', va='bottom', fontsize=8, fontweight='bold')
    legend_elements = [
        mpatches.Patch(color=C_RED, label='TBR flagged'),
        mpatches.Patch(color=C_GREEN, label='TBR OK'),
    ]
    ax.legend(handles=legend_elements, fontsize=8)

    # Panel B: Hypo episodes count per patient
    ax = axes[1]
    ax.set_facecolor(C_BG)
    pp2 = sorted(data_1521['per_patient'],
                 key=lambda p: p.get('n_hypo', 0),
                 reverse=True)
    pids2 = [p['patient'] for p in pp2]
    n_hypos = [p.get('n_hypo', 0) for p in pp2]
    colors = [C_RED if n > 10 else C_ORANGE if n > 3 else C_GREEN for n in n_hypos]
    bars = ax.bar(range(len(pids2)), n_hypos, color=colors, edgecolor='white')
    ax.set_xticks(range(len(pids2)))
    ax.set_xticklabels(pids2, fontsize=10)
    ax.set_ylabel('Hypo Episodes', fontsize=11)
    ax.set_title('Hypoglycemia Frequency', fontsize=11, fontweight='bold')
    for bar, n in zip(bars, n_hypos):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3,
                f'{n}', ha='center', va='bottom', fontsize=8, fontweight='bold')

    # Panel C: Safety tier distribution
    ax = axes[2]
    ax.set_facecolor(C_BG)
    tiers = defaultdict(int)
    for p in data_1521['per_patient']:
        tiers[p['safety_tier']] += 1
    tier_order = ['low', 'moderate', 'high', 'critical']
    tier_labels = ['Low', 'Moderate', 'High', 'Critical']
    tier_sizes = [tiers.get(t, 0) for t in tier_order]
    tier_colors = [SAFETY_COLORS.get(t, C_GRAY) for t in tier_order]
    wedges, texts, autotexts = ax.pie(
        tier_sizes, labels=[f'{l}\n(n={s})' for l, s in zip(tier_labels, tier_sizes)],
        colors=tier_colors, autopct='%1.0f%%', startangle=90, pctdistance=0.75)
    for t in autotexts:
        t.set_fontsize(9)
        t.set_fontweight('bold')
    ax.set_title('Safety Tier Distribution', fontsize=11, fontweight='bold')

    fig.suptitle('Safety Analysis: Hypoglycemia & Time Below Range',
                 fontsize=14, fontweight='bold', y=1.02)
    _savefig(fig, 'fig09_safety.png')


# ═════════════════════════════════════════════════════════════════════════
# Figure 10: Evidence Synthesis Dashboard
# ═════════════════════════════════════════════════════════════════════════

def fig10_evidence_synthesis():
    """Key metrics summary across all validation experiments."""
    # Load all available results
    exp_data = {}
    for eid in [1521, 1522, 1523, 1524, 1525, 1526, 1527, 1528]:
        d = _load(f'exp-{eid}_therapy.json')
        if d:
            exp_data[eid] = d

    # Also load prior experiments
    for eid, fname in [(1301, 'exp-1301_therapy.json'),
                       (1309, 'exp-1309_therapy.json'),
                       (1320, 'exp-1320_therapy.json'),
                       (1331, 'exp-1331_therapy.json'),
                       (1334, 'exp-1334_therapy.json'),
                       (1341, 'exp-1341_carb_survey.json'),
                       (1510, 'exp-1510_therapy.json')]:
        d = _load(fname)
        if d:
            exp_data[eid] = d

    fig = plt.figure(figsize=(16, 10), facecolor=C_BG)
    gs = GridSpec(3, 4, figure=fig, hspace=0.4, wspace=0.35)

    # Metric cards
    metrics = [
        ('ISF Curve R²', exp_data.get(1301, {}).get('mean_fit_r2',
          np.mean([p.get('mean_fit_r2',0) for p in exp_data.get(1301,{}).get('per_patient',[])]
          ) if exp_data.get(1301,{}).get('per_patient') else 0), 0.805, 'higher=better'),
        ('DIA Median (h)', exp_data.get(1334, {}).get('population_dia_median', 0), 6.0, 'vs 5h profile'),
        ('UAM Δ R²', exp_data.get(1309, {}).get('mean_r2_improvement', 0), 0.859, 'augmentation'),
        ('UAM Transfer', exp_data.get(1320, {}).get('universal_pct_improved', 0), 100, '% improved'),
        ('Meals Analyzed', exp_data.get(1341, {}).get('n_meals', 0), 12060, 'EXP-1341'),
        ('UAM %', exp_data.get(1341, {}).get('pct_uam', 0), 76.5, 'unannounced'),
        ('Grade Stability',
         exp_data.get(1522, {}).get('grade_agreement', 0),
         90.9, 'train vs verify %'),
        ('Flag Agreement',
         exp_data.get(1523, {}).get('overall_agreement', 0), 77.3, 'holdout %'),
        ('Drift Corr.',
         exp_data.get(1524, {}).get('drift_correlation', 0), 0.825, 'basal r'),
        ('Rec. Jaccard',
         exp_data.get(1527, {}).get('mean_jaccard', 0), 0.49, 'consistency'),
        ('Bootstrap Stab.',
         exp_data.get(1510, {}).get('summary', {}).get('mean_grade_stability', 0), 94.5, '% (n=1000)'),
        ('Rec. Consist.',
         exp_data.get(1510, {}).get('summary', {}).get('mean_rec_consistency', 0), 81.2, '% bootstrap'),
    ]

    for idx, (label, value, reference, note) in enumerate(metrics):
        row = idx // 4
        col = idx % 4
        ax = fig.add_subplot(gs[row, col])
        ax.set_facecolor(C_BG)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis('off')

        # Card background
        rect = plt.Rectangle((0.05, 0.05), 0.9, 0.9, fill=True,
                             facecolor='white', edgecolor=C_DARK, linewidth=1,
                             transform=ax.transAxes, zorder=0)
        ax.add_patch(rect)

        # Value
        if isinstance(value, float):
            if value > 100:
                val_str = f'{value:,.0f}'
            elif value > 10:
                val_str = f'{value:.1f}'
            else:
                val_str = f'{value:.3f}'
        else:
            val_str = f'{value:,}'

        ax.text(0.5, 0.65, val_str, transform=ax.transAxes, ha='center', va='center',
               fontsize=20, fontweight='bold', color=C_DARK)
        ax.text(0.5, 0.35, label, transform=ax.transAxes, ha='center', va='center',
               fontsize=10, fontweight='bold', color=C_DARK)
        ax.text(0.5, 0.18, note, transform=ax.transAxes, ha='center', va='center',
               fontsize=8, color=C_GRAY, style='italic')

    fig.suptitle('Evidence Synthesis: Therapy Settings Validation (230+ Experiments)',
                 fontsize=15, fontweight='bold', y=0.98)
    _savefig(fig, 'fig10_evidence_synthesis.png')


# ═════════════════════════════════════════════════════════════════════════
# Main
# ═════════════════════════════════════════════════════════════════════════

FIGURES = [
    ('fig01', fig01_cohort_dashboard),
    ('fig02', fig02_basal_drift),
    ('fig03', fig03_isf_validation),
    ('fig04', fig04_cr_validation),
    ('fig05', fig05_holdout_stability),
    ('fig06', fig06_flag_agreement),
    ('fig07', fig07_recommendation_consistency),
    ('fig08', fig08_minimum_data),
    ('fig09', fig09_safety),
    ('fig10', fig10_evidence_synthesis),
]


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Generate therapy validation figures')
    parser.add_argument('--only', nargs='*', help='Generate specific figures (e.g., fig01 fig05)')
    args = parser.parse_args()

    print(f'Generating figures in {OUT_DIR}')
    print(f'Reading data from {DATA_DIR}')
    print()

    for name, fn in FIGURES:
        if args.only and name not in args.only:
            continue
        print(f'Generating {name}...')
        try:
            fn()
        except Exception as e:
            print(f'  ERROR: {e}')
            import traceback
            traceback.print_exc()

    print('\nDone!')


if __name__ == '__main__':
    main()
