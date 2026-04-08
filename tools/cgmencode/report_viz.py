#!/usr/bin/env python3
"""
report_viz.py — Shared visualization functions for research reports.

Provides reusable figure generators that work with experiment JSON data
and continuous_pk physics models. Designed to be imported by per-report
figure scripts or used standalone.

Usage:
    from tools.cgmencode.report_viz import (
        plot_r2_waterfall,
        plot_horizon_routing_heatmap,
        plot_aid_loop_behavior,
        plot_patient_heterogeneity,
        plot_residual_ceiling,
    )
"""

import json
from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

# Style defaults
COLORS = {
    'primary': '#2563eb',
    'secondary': '#7c3aed',
    'accent': '#059669',
    'warning': '#d97706',
    'danger': '#dc2626',
    'neutral': '#6b7280',
    'bg_light': '#f8fafc',
    'grid': '#e2e8f0',
}

PATIENT_COLORS = {
    'a': '#e11d48', 'b': '#be123c', 'c': '#f59e0b', 'd': '#059669',
    'e': '#0284c7', 'f': '#7c3aed', 'g': '#c026d3', 'h': '#dc2626',
    'i': '#0d9488', 'j': '#ea580c', 'k': '#4f46e5',
}


def _setup_style(ax, title, xlabel, ylabel):
    """Apply consistent styling to axes."""
    ax.set_title(title, fontsize=13, fontweight='bold', pad=12)
    ax.set_xlabel(xlabel, fontsize=10)
    ax.set_ylabel(ylabel, fontsize=10)
    ax.grid(True, alpha=0.3, color=COLORS['grid'])
    ax.set_facecolor(COLORS['bg_light'])


def plot_r2_waterfall(stages: dict, per_patient: Optional[dict] = None,
                      output_path: Optional[str] = None):
    """
    Waterfall chart showing R² progression through pipeline stages.

    Parameters
    ----------
    stages : dict
        OrderedDict-like of {stage_name: r2_value}, e.g.
        {'Raw CGM baseline': 0.304, 'Spike cleaning': 0.461, ...}
    per_patient : dict, optional
        {patient_id: {stage_name: r2}} for background scatter
    output_path : str, optional
        Save path. If None, plt.show().
    """
    fig, ax = plt.subplots(figsize=(12, 6))

    names = list(stages.keys())
    values = list(stages.values())
    n = len(names)

    # Compute incremental deltas
    deltas = [values[0]] + [values[i] - values[i-1] for i in range(1, n)]

    # Draw waterfall bars
    cumulative = 0
    bar_bottoms = []
    bar_heights = []
    bar_colors = []

    for i, (name, delta) in enumerate(zip(names, deltas)):
        if i == 0:
            bar_bottoms.append(0)
            bar_heights.append(delta)
            bar_colors.append(COLORS['neutral'])
        else:
            bar_bottoms.append(cumulative)
            bar_heights.append(delta)
            bar_colors.append(COLORS['accent'] if delta > 0.01 else COLORS['warning'])
        cumulative += delta

    bars = ax.bar(range(n), bar_heights, bottom=bar_bottoms, color=bar_colors,
                  edgecolor='white', linewidth=1.5, width=0.6, zorder=3)

    # Connector lines between bars
    for i in range(n - 1):
        top = bar_bottoms[i] + bar_heights[i]
        ax.plot([i + 0.3, i + 0.7], [top, top], color='#94a3b8',
                linewidth=1, linestyle='--', zorder=2)

    # Value labels
    for i, (bar, val, delta) in enumerate(zip(bars, values, deltas)):
        y_top = bar_bottoms[i] + bar_heights[i]
        ax.text(i, y_top + 0.012, f'R²={val:.3f}',
                ha='center', va='bottom', fontsize=9, fontweight='bold')
        if i > 0 and delta > 0.005:
            ax.text(i, bar_bottoms[i] + delta / 2,
                    f'+{delta:.3f}', ha='center', va='center',
                    fontsize=8, color='white', fontweight='bold')

    # Per-patient scatter overlay
    if per_patient:
        for pid, patient_stages in per_patient.items():
            patient_vals = [patient_stages.get(name, np.nan) for name in names]
            jitter = (hash(pid) % 7 - 3) * 0.04
            ax.scatter([i + jitter for i in range(n)], patient_vals,
                       s=18, alpha=0.5, color=PATIENT_COLORS.get(pid, '#999'),
                       zorder=4, label=pid if pid == 'a' else None)

    ax.set_xticks(range(n))
    ax.set_xticklabels(names, rotation=20, ha='right', fontsize=9)
    _setup_style(ax, 'R² Progression Through Pipeline Stages',
                 '', 'R² (60-min glucose prediction)')
    ax.set_ylim(0, max(values) + 0.1)

    fig.tight_layout()
    if output_path:
        fig.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close(fig)
    return fig


def plot_horizon_routing_heatmap(window_data: dict,
                                 output_path: Optional[str] = None):
    """
    Heatmap showing MAE across window sizes × forecast horizons.
    Highlights the optimal window for each horizon.

    Parameters
    ----------
    window_data : dict
        {window_name: {horizon_name: mean_mae}}, e.g.
        {'w48': {'h30': 11.1, 'h60': 14.2, ...}, ...}
    """
    windows = list(window_data.keys())
    # Collect all horizons across windows
    all_horizons = sorted(set(h for wd in window_data.values() for h in wd.keys()),
                          key=lambda h: int(h[1:]))

    # Build matrix
    matrix = np.full((len(windows), len(all_horizons)), np.nan)
    for i, w in enumerate(windows):
        for j, h in enumerate(all_horizons):
            if h in window_data[w]:
                matrix[i, j] = window_data[w][h]

    fig, ax = plt.subplots(figsize=(14, 5))

    # Custom colormap: green (good) → yellow → red (bad)
    im = ax.imshow(matrix, cmap='RdYlGn_r', aspect='auto',
                   vmin=8, vmax=35)

    # Find best window per horizon
    best_per_horizon = {}
    for j, h in enumerate(all_horizons):
        col = matrix[:, j]
        valid = ~np.isnan(col)
        if valid.any():
            best_idx = np.nanargmin(col)
            best_per_horizon[j] = best_idx

    # Annotate cells
    for i in range(len(windows)):
        for j in range(len(all_horizons)):
            val = matrix[i, j]
            if np.isnan(val):
                ax.text(j, i, '—', ha='center', va='center',
                        fontsize=8, color='#94a3b8')
            else:
                is_best = best_per_horizon.get(j) == i
                weight = 'bold' if is_best else 'normal'
                color = 'white' if val > 25 else 'black'
                ax.text(j, i, f'{val:.1f}', ha='center', va='center',
                        fontsize=9, fontweight=weight, color=color)
                if is_best:
                    rect = plt.Rectangle((j - 0.45, i - 0.45), 0.9, 0.9,
                                         linewidth=2.5, edgecolor=COLORS['primary'],
                                         facecolor='none', zorder=5)
                    ax.add_patch(rect)

    ax.set_xticks(range(len(all_horizons)))
    ax.set_xticklabels([f'{h}\n({int(h[1:])}min)' for h in all_horizons], fontsize=8)
    ax.set_yticks(range(len(windows)))
    yticklabels = []
    win_context = {'w48': '2h', 'w72': '3h', 'w96': '4h', 'w144': '6h'}
    for w in windows:
        ctx = win_context.get(w, '')
        yticklabels.append(f'{w} ({ctx})' if ctx else w)
    ax.set_yticklabels(yticklabels, fontsize=10)

    cbar = fig.colorbar(im, ax=ax, shrink=0.8, pad=0.02)
    cbar.set_label('MAE (mg/dL)', fontsize=9)

    _setup_style(ax, 'Forecast Error by Window Size × Horizon (■ = best)',
                 'Forecast Horizon', 'Window Size (history length)')
    ax.grid(False)

    fig.tight_layout()
    if output_path:
        fig.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close(fig)
    return fig


def plot_aid_loop_behavior(loop_data: list,
                           output_path: Optional[str] = None):
    """
    Stacked bar chart showing AID loop action distribution per patient,
    plus glucose drift during stable windows.

    Parameters
    ----------
    loop_data : list of dict
        Each dict has: patient, pct_suspended, pct_high_temp, pct_nominal,
                       drift (mg/dL/hr), assessment
    """
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.5),
                                    gridspec_kw={'width_ratios': [3, 2]})

    patients = [d['patient'] for d in loop_data]
    n = len(patients)
    x = np.arange(n)

    suspended = [d['pct_suspended'] * 100 for d in loop_data]
    nominal = [d['pct_nominal'] * 100 for d in loop_data]
    high_temp = [d['pct_high_temp'] * 100 for d in loop_data]

    ax1.bar(x, suspended, label='Suspended', color='#93c5fd', edgecolor='white', width=0.7)
    ax1.bar(x, nominal, bottom=suspended, label='Nominal (scheduled)',
            color=COLORS['accent'], edgecolor='white', width=0.7)
    bottoms = [s + n for s, n in zip(suspended, nominal)]
    ax1.bar(x, high_temp, bottom=bottoms, label='High temp',
            color=COLORS['warning'], edgecolor='white', width=0.7)

    ax1.set_xticks(x)
    ax1.set_xticklabels([f'Patient {p}' for p in patients], rotation=45, ha='right', fontsize=9)
    ax1.set_ylim(0, 105)
    ax1.legend(loc='upper right', fontsize=8, framealpha=0.9)
    _setup_style(ax1, 'AID Loop Action Distribution',
                 '', '% of Time')

    # Right panel: glucose drift during stable windows
    drifts = []
    drift_patients = []
    colors = []
    for d in loop_data:
        drift = d.get('drift')
        if drift is not None:
            drifts.append(drift)
            drift_patients.append(d['patient'])
            colors.append(COLORS['danger'] if drift < 0 else COLORS['primary'])

    y_pos = np.arange(len(drift_patients))
    ax2.barh(y_pos, drifts, color=colors, height=0.6, edgecolor='white')
    ax2.axvline(0, color='black', linewidth=0.8)
    ax2.set_yticks(y_pos)
    ax2.set_yticklabels([f'Patient {p}' for p in drift_patients], fontsize=9)

    # Annotate assessments
    for i, (drift, d_patient) in enumerate(zip(drifts, drift_patients)):
        label = 'high' if drift < 0 else 'low'
        offset = -1 if drift < 0 else 1
        ax2.text(drift + offset, i, f'{drift:+.1f}',
                 ha='left' if drift > 0 else 'right',
                 va='center', fontsize=8, fontweight='bold')

    _setup_style(ax2, 'Glucose Drift in Stable Windows\n(Basal Assessment)',
                 'Drift (mg/dL/hr)', '')

    # Add annotation about the key finding
    ax2.annotate('8/10 patients: basal too high\n(glucose drops when loop is idle)',
                 xy=(0.02, 0.02), xycoords='axes fraction',
                 fontsize=8, fontstyle='italic', color=COLORS['danger'],
                 bbox=dict(boxstyle='round,pad=0.3', facecolor='#fef2f2',
                           edgecolor=COLORS['danger'], alpha=0.8))

    fig.tight_layout()
    if output_path:
        fig.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close(fig)
    return fig


def plot_patient_heterogeneity(patient_data: list,
                               output_path: Optional[str] = None):
    """
    Scatter plot of ISF vs MAE per patient, plus per-patient bar chart.

    Parameters
    ----------
    patient_data : list of dict
        Each dict has: patient, isf, h60_mae, h120_mae, missing_rate, mean_bg
    """
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.5),
                                    gridspec_kw={'width_ratios': [1, 1]})

    patients = [d['patient'] for d in patient_data]
    isfs = [d['isf'] for d in patient_data]
    h60s = [d['h60_mae'] for d in patient_data]
    h120s = [d['h120_mae'] for d in patient_data]
    missing = [d['missing_rate'] for d in patient_data]

    # Left: ISF vs h60 MAE scatter
    sizes = [max(40, m * 800) for m in missing]  # size by missing rate
    scatter = ax1.scatter(isfs, h60s, s=sizes, alpha=0.7, zorder=4,
                          c=[PATIENT_COLORS.get(p, '#999') for p in patients],
                          edgecolors='white', linewidth=1.5)

    for d in patient_data:
        offset_x = 2
        offset_y = 0.5
        if d['patient'] == 'h':
            offset_y = -1.5
        ax1.annotate(f'{d["patient"]}', (d['isf'], d['h60_mae']),
                     xytext=(offset_x, offset_y), textcoords='offset points',
                     fontsize=9, fontweight='bold')

    # Trend line
    z = np.polyfit(isfs, h60s, 1)
    x_line = np.linspace(min(isfs) - 5, max(isfs) + 5, 50)
    ax1.plot(x_line, np.polyval(z, x_line), '--', color=COLORS['neutral'],
             alpha=0.6, linewidth=1.5)

    r_val = np.corrcoef(isfs, h60s)[0, 1]
    ax1.text(0.05, 0.95, f'r = {r_val:.2f}', transform=ax1.transAxes,
             fontsize=10, fontweight='bold', va='top',
             bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))

    # Highlight patient h
    h_idx = patients.index('h')
    ax1.annotate(f'64% missing\ndata',
                 (isfs[h_idx], h60s[h_idx]),
                 xytext=(15, -25), textcoords='offset points',
                 fontsize=8, color=COLORS['danger'],
                 arrowprops=dict(arrowstyle='->', color=COLORS['danger'],
                                 lw=1.5))

    _setup_style(ax1, 'ISF vs Forecast Error (bubble = missing rate)',
                 'ISF (mg/dL per unit)', 'h60 MAE (mg/dL)')

    # Right: grouped bar chart h60 vs h120 per patient
    x = np.arange(len(patients))
    width = 0.35
    ax2.bar(x - width/2, h60s, width, label='h60 (1hr)',
            color=COLORS['primary'], edgecolor='white', alpha=0.8)
    ax2.bar(x + width/2, h120s, width, label='h120 (2hr)',
            color=COLORS['secondary'], edgecolor='white', alpha=0.8)

    ax2.set_xticks(x)
    ax2.set_xticklabels([f'{p}' for p in patients], fontsize=10, fontweight='bold')
    ax2.legend(fontsize=9, loc='upper left')

    # Annotate range
    best_h60 = min(h60s)
    worst_h60 = max(h60s)
    ax2.annotate(f'{worst_h60/best_h60:.1f}× range',
                 xy=(0.95, 0.95), xycoords='axes fraction',
                 fontsize=9, fontweight='bold', ha='right', va='top',
                 bbox=dict(boxstyle='round', facecolor='#eff6ff', alpha=0.9))

    _setup_style(ax2, 'Per-Patient Forecast Error',
                 'Patient', 'MAE (mg/dL)')

    fig.tight_layout()
    if output_path:
        fig.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close(fig)
    return fig


def plot_residual_ceiling(stages_data: dict,
                          output_path: Optional[str] = None):
    """
    Horizontal bar chart showing R² SOTA progression with annotated ceiling.

    Parameters
    ----------
    stages_data : dict with keys:
        milestones: list of (label, r2_value)
        ceiling: float (oracle ceiling)
        annotations: list of (label, value, note)
    """
    fig, ax = plt.subplots(figsize=(12, 6))

    milestones = stages_data['milestones']
    ceiling = stages_data['ceiling']

    labels = [m[0] for m in milestones]
    values = [m[1] for m in milestones]
    n = len(labels)

    y_pos = np.arange(n)
    colors = []
    for v in values:
        if v < 0.3:
            colors.append('#fca5a5')
        elif v < 0.5:
            colors.append('#fcd34d')
        else:
            colors.append(COLORS['accent'])

    bars = ax.barh(y_pos, values, color=colors, height=0.5,
                   edgecolor='white', linewidth=1.5, zorder=3)

    # Ceiling line
    ax.axvline(ceiling, color=COLORS['danger'], linewidth=2, linestyle='--',
               zorder=4, label=f'Oracle ceiling (R²={ceiling:.3f})')

    # Annotations on bars
    for i, (label, val) in enumerate(milestones):
        pct = val / ceiling * 100
        ax.text(val + 0.008, i, f'R²={val:.3f} ({pct:.0f}%)',
                va='center', fontsize=9, fontweight='bold')

    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlim(0, ceiling + 0.18)
    ax.legend(loc='lower right', fontsize=9, framealpha=0.9)
    ax.invert_yaxis()

    _setup_style(ax, 'R² SOTA Progression Toward Oracle Ceiling',
                 'R² (60-min glucose prediction)', '')

    # Dead-end zone annotation
    ax.axvspan(ceiling, ceiling + 0.18, alpha=0.08, color=COLORS['danger'], zorder=1)
    ax.text(ceiling + 0.06, 1.0,
            'Beyond ceiling:\nnew data sources\nrequired',
            fontsize=8, fontstyle='italic', color=COLORS['danger'],
            va='center', ha='center')

    fig.tight_layout()
    if output_path:
        fig.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close(fig)
    return fig
