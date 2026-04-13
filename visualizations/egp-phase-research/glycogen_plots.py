#!/usr/bin/env python3
"""Visualization for EXP-2628: Glycogen State Detection."""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

VIZ_DIR = Path("visualizations/egp-phase-research")
RESULTS = Path("externals/experiments/exp-2628_glycogen_state_detection.json")


def main():
    with open(RESULTS) as f:
        r = json.load(f)

    ps = r["pooled_summary"]
    states = ["low", "nominal", "high"]
    colors = {"low": "#3498db", "nominal": "#95a5a6", "high": "#e74c3c"}
    labels = {"low": "Low\n(depleted)", "nominal": "Nominal", "high": "High\n(replete)"}

    fig, axes = plt.subplots(2, 2, figsize=(13, 10))

    # Panel 1: Overnight drift by state
    ax = axes[0, 0]
    drifts = [ps[s]["drift_mean"] for s in states]
    drift_err = [ps[s]["drift_std"] / np.sqrt(ps[s]["n_days"]) for s in states]
    bars = ax.bar(range(3), drifts, yerr=drift_err, capsize=5,
                  color=[colors[s] for s in states], edgecolor='k', linewidth=0.8)
    ax.axhline(0, color='k', linewidth=0.5)
    ax.set_xticks(range(3))
    ax.set_xticklabels([labels[s] for s in states])
    ax.set_ylabel('Overnight Drift (mg/dL/hr)')
    ax.set_title('Glycogen State → Overnight Drift\n(p=0.001, Δ=9.7 mg/dL/hr)')
    ax.grid(axis='y', alpha=0.3)
    for i, (d, s) in enumerate(zip(drifts, states)):
        ax.annotate(f'{d:+.1f}', xy=(i, d + (2 if d >= 0 else -3)),
                    ha='center', fontsize=10, fontweight='bold')
    ax.annotate('← Rising\n(EGP > basal)', xy=(2.7, max(drifts) - 1),
                fontsize=7, ha='right', color='gray')
    ax.annotate('← Falling\n(EGP < basal)', xy=(2.7, min(drifts) + 1),
                fontsize=7, ha='right', color='gray')

    # Panel 2: Mean glucose and TIR by state
    ax = axes[0, 1]
    mg = [ps[s]["mean_glucose"] for s in states]
    tir = [ps[s]["tir"] for s in states]
    x = np.arange(3)
    w = 0.35
    ax2 = ax.twinx()
    ax.bar(x - w/2, mg, w, color=[colors[s] for s in states],
           edgecolor='k', linewidth=0.8, alpha=0.7, label='Mean Glucose')
    ax2.bar(x + w/2, tir, w, color=[colors[s] for s in states],
            edgecolor='k', linewidth=0.8, alpha=0.4, hatch='//', label='TIR %')
    ax.set_xticks(x)
    ax.set_xticklabels([labels[s] for s in states])
    ax.set_ylabel('Mean Glucose (mg/dL)')
    ax2.set_ylabel('TIR (%)')
    ax.set_title('Glycogen State → Glycemic Outcomes\n(r=0.302, p<0.001)')
    ax.legend(loc='upper left', fontsize=7)
    ax2.legend(loc='upper right', fontsize=7)
    ax.grid(axis='y', alpha=0.2)

    # Panel 3: Per-patient drift deltas
    ax = axes[1, 0]
    pp = r["per_patient"]
    patients_with_delta = [(pid, p["drift_delta_high_minus_low"])
                           for pid, p in sorted(pp.items())
                           if p.get("drift_delta_high_minus_low") is not None]
    if patients_with_delta:
        pids = [p[0] for p in patients_with_delta]
        deltas = [p[1] for p in patients_with_delta]
        bar_colors = ['#e74c3c' if abs(d) > 10 else '#f39c12' if abs(d) > 5 else '#27ae60'
                      for d in deltas]
        ax.barh(range(len(pids)), deltas, color=bar_colors, edgecolor='k', linewidth=0.5)
        ax.set_yticks(range(len(pids)))
        ax.set_yticklabels(pids)
        ax.axvline(0, color='k', linewidth=0.5)
        ax.set_xlabel('Drift Δ: high - low glycogen (mg/dL/hr)')
        ax.set_title('Per-Patient Glycogen Impact on Drift')
        ax.grid(axis='x', alpha=0.3)
        for i, d in enumerate(deltas):
            ax.annotate(f'{d:+.1f}', xy=(d + (1 if d >= 0 else -1), i),
                        va='center', fontsize=8, fontweight='bold')

    # Panel 4: Settings recommendations
    ax = axes[1, 1]
    ax.axis('off')
    text = (
        "GLYCOGEN-AWARE SETTINGS\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Detection: 48h cumulative carbs\n"
        "  → per-patient terciles\n\n"
        "LOW glycogen (depleted):\n"
        "  • Overnight drift: +6.0 mg/dL/hr\n"
        "  • EGP > basal → glucose rises\n"
        "  • Mean glucose: 146 mg/dL (best)\n"
        "  • TIR: 70.4% (best)\n"
        "  ⟹ Current basal is ADEQUATE\n\n"
        "HIGH glycogen (replete):\n"
        "  • Overnight drift: -3.8 mg/dL/hr\n"
        "  • More EGP → pushes glucose up\n"
        "  • But insulin also higher\n"
        "  • Mean glucose: 154 mg/dL\n"
        "  • TIR: 67.7%\n"
        "  ⟹ May need +0.25 U/hr basal\n\n"
        "Swing: 9.7 mg/dL/hr ≈ 39% of\n"
        "mean basal rate equivalent"
    )
    ax.text(0.05, 0.95, text, transform=ax.transAxes, fontsize=9,
            verticalalignment='top', fontfamily='monospace',
            bbox=dict(boxstyle='round', facecolor='#f0f0f0', alpha=0.8))

    fig.suptitle('EXP-2628: Glycogen State Detection from 48h Carb History',
                 fontsize=14, fontweight='bold')
    fig.tight_layout()
    fig.savefig(VIZ_DIR / "fig14_glycogen_state_detection.png", dpi=150)
    plt.close(fig)
    print("  Saved fig14_glycogen_state_detection.png")


if __name__ == "__main__":
    main()
