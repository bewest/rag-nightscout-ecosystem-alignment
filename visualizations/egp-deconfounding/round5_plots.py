#!/usr/bin/env python3
"""Round 5 Visualizations: Forward Sim + Retrospective Audit

Figures:
  fig40: Model comparison — MAE/bias/R² across 6 ISF models
  fig41: Predicted vs actual drop scatter for best and worst models
  fig42: Retrospective audit — outcome classification + dose ratios
  fig43: Round 5 synthesis — descriptive vs prescriptive insight
"""

import json
import os
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

OUT_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'externals', 'experiments')


def load_results():
    with open(os.path.join(DATA_DIR, 'exp-2641_forward_sim_log_isf.json')) as f:
        r2641 = json.load(f)
    with open(os.path.join(DATA_DIR, 'exp-2642_retrospective_audit.json')) as f:
        r2642 = json.load(f)
    return r2641, r2642


def fig40_model_comparison(r2641):
    """Bar chart comparing 6 models on MAE, bias, R²."""
    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(16, 5))

    models = r2641['models']
    order = ['A_fixed_isf', 'D_linear_ratio', 'E_iob_weighted',
             'B_pop_log_isf', 'F_iob_log', 'C_patient_log_isf']
    labels = [models[k]['label'] for k in order if k in models]
    maes = [models[k]['mae'] for k in order if k in models]
    biases = [models[k]['bias'] for k in order if k in models]
    r2s = [models[k]['r_squared'] for k in order if k in models]

    # Wrap labels
    labels_wrapped = [l.replace(' ', '\n', 1) for l in labels]

    # MAE
    colors_mae = ['tomato' if m > 80 else 'goldenrod' if m > 70
                  else 'forestgreen' for m in maes]
    bars = ax1.bar(range(len(labels)), maes, color=colors_mae,
                   edgecolor='black', linewidth=0.5)
    for bar, val in zip(bars, maes):
        ax1.text(bar.get_x() + bar.get_width() / 2, val + 1,
                 f'{val:.0f}', ha='center', fontsize=9, fontweight='bold')
    ax1.set_xticks(range(len(labels)))
    ax1.set_xticklabels(labels_wrapped, fontsize=8)
    ax1.set_ylabel('MAE (mg/dL)', fontsize=11)
    ax1.set_title('A. Mean Absolute Error', fontsize=12)
    ax1.axhline(84.4, color='gray', linewidth=0.5, linestyle='--', alpha=0.5)
    ax1.set_ylim(0, max(maes) * 1.15)

    # Bias
    colors_bias = ['tomato' if abs(b) > 50 else 'goldenrod' if abs(b) > 20
                   else 'forestgreen' for b in biases]
    bars = ax2.bar(range(len(labels)), biases, color=colors_bias,
                   edgecolor='black', linewidth=0.5)
    for bar, val in zip(bars, biases):
        y_pos = val + 3 if val >= 0 else val - 8
        ax2.text(bar.get_x() + bar.get_width() / 2, y_pos,
                 f'{val:+.0f}', ha='center', fontsize=9, fontweight='bold')
    ax2.set_xticks(range(len(labels)))
    ax2.set_xticklabels(labels_wrapped, fontsize=8)
    ax2.set_ylabel('Bias (mg/dL)', fontsize=11)
    ax2.set_title('B. Prediction Bias', fontsize=12)
    ax2.axhline(0, color='black', linewidth=1)

    # R²
    colors_r2 = ['forestgreen' if r > -0.3 else 'goldenrod' if r > -1.0
                 else 'tomato' for r in r2s]
    bars = ax3.bar(range(len(labels)), r2s, color=colors_r2,
                   edgecolor='black', linewidth=0.5)
    for bar, val in zip(bars, r2s):
        y_pos = val - 0.1 if val < 0 else val + 0.03
        ax3.text(bar.get_x() + bar.get_width() / 2, y_pos,
                 f'{val:.2f}', ha='center', fontsize=9, fontweight='bold')
    ax3.set_xticks(range(len(labels)))
    ax3.set_xticklabels(labels_wrapped, fontsize=8)
    ax3.set_ylabel('R-squared', fontsize=11)
    ax3.set_title('C. Explained Variance', fontsize=12)
    ax3.axhline(0, color='black', linewidth=1, linestyle='--')

    fig.suptitle('Figure 40: Forward Sim Model Comparison (EXP-2641)',
                 fontsize=14, fontweight='bold', y=1.02)
    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, 'fig40_model_comparison.png'),
                dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    print("  fig40 saved")


def fig41_scatter(r2641):
    """Predicted vs actual scatter for best (per-patient log) and worst (fixed)."""
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    preds = r2641['predictions']

    plot_models = [
        ('A_fixed_isf', 'Fixed ISF (baseline)', 'tomato'),
        ('C_patient_log_isf', 'Per-patient log-ISF (best)', 'forestgreen'),
        ('E_iob_weighted', 'IOB-weighted fixed', 'steelblue'),
    ]

    for ax, (key, label, color) in zip(axes, plot_models):
        if key not in preds:
            continue
        actual = np.array(preds[key]['actual'])
        predicted = np.array(preds[key]['predicted'])
        model = r2641['models'][key]

        ax.scatter(actual, predicted, alpha=0.3, s=20, color=color,
                   edgecolor='gray', linewidth=0.3)

        # Perfect prediction line
        lim = max(actual.max(), predicted.max()) * 1.05
        ax.plot([0, lim], [0, lim], 'k--', linewidth=1, alpha=0.5,
                label='Perfect prediction')

        # Regression line
        slope, intercept = np.polyfit(actual, predicted, 1)
        x_fit = np.linspace(0, lim, 100)
        ax.plot(x_fit, slope * x_fit + intercept, color=color, linewidth=2,
                label=f'Fit: y={slope:.2f}x+{intercept:.0f}')

        ax.set_xlabel('Actual Drop (mg/dL)', fontsize=10)
        ax.set_ylabel('Predicted Drop (mg/dL)', fontsize=10)
        ax.set_title(f'{label}\nMAE={model["mae"]:.0f}, R²={model["r_squared"]:.2f}',
                     fontsize=11)
        ax.legend(fontsize=8, loc='upper left')
        ax.set_xlim(0, lim)
        ax.set_ylim(0, lim)
        ax.set_aspect('equal')
        ax.grid(alpha=0.2)

    fig.suptitle('Figure 41: Predicted vs Actual Glucose Drop (EXP-2641)',
                 fontsize=14, fontweight='bold', y=1.02)
    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, 'fig41_scatter_comparison.png'),
                dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    print("  fig41 saved")


def fig42_audit(r2642):
    """Retrospective audit outcomes + dose ratios."""
    fig = plt.figure(figsize=(14, 10))
    gs = GridSpec(2, 2, figure=fig, hspace=0.35, wspace=0.3)

    audits = r2642['audits']

    # Panel A: Outcome distribution
    ax1 = fig.add_subplot(gs[0, 0])
    outcomes = r2642['outcomes']
    categories = ['appropriate', 'under_correction', 'over_correction', 'hypo']
    cat_labels = ['Appropriate\n(target +/- margin)', 'Under-correction\n(>target+40)',
                  'Over-correction\n(<target-20)', 'Hypo\n(<70 mg/dL)']
    cat_colors = ['forestgreen', 'goldenrod', 'tomato', 'darkred']
    counts = [outcomes.get(c, 0) for c in categories]

    bars = ax1.bar(range(4), counts, color=cat_colors, edgecolor='black', linewidth=0.5)
    for bar, cnt, total in zip(bars, counts, [len(audits)] * 4):
        ax1.text(bar.get_x() + bar.get_width() / 2, cnt + 2,
                 f'{cnt}\n({cnt/total*100:.0f}%)', ha='center', fontsize=10,
                 fontweight='bold')
    ax1.set_xticks(range(4))
    ax1.set_xticklabels(cat_labels, fontsize=9)
    ax1.set_ylabel('Number of Corrections', fontsize=11)
    ax1.set_title('A. Correction Outcome Classification', fontsize=12)

    # Panel B: Outcome by dose bin
    ax2 = fig.add_subplot(gs[0, 1])
    dose_bins = [(0, 1.0, '<1U'), (1.0, 2.0, '1-2U'),
                 (2.0, 3.0, '2-3U'), (3.0, 100, '>=3U')]
    x = np.arange(len(dose_bins))
    width = 0.2
    for i, (cat, color) in enumerate(zip(categories, cat_colors)):
        rates = []
        for lo, hi, _ in dose_bins:
            bin_events = [a for a in audits if lo <= a['bolus_u'] < hi]
            n_cat = sum(1 for a in bin_events if a['outcome'] == cat)
            rates.append(n_cat / len(bin_events) * 100 if bin_events else 0)
        ax2.bar(x + i * width, rates, width, label=cat.replace('_', ' ').title(),
                color=color, edgecolor='black', linewidth=0.3)

    ax2.set_xticks(x + 1.5 * width)
    ax2.set_xticklabels([d[2] for d in dose_bins], fontsize=10)
    ax2.set_ylabel('% of Corrections', fontsize=11)
    ax2.set_title('B. Outcomes by Dose Bin', fontsize=12)
    ax2.legend(fontsize=8, loc='upper right')

    # Panel C: Excess drop vs bolus size
    ax3 = fig.add_subplot(gs[1, 0])
    boluses = np.array([a['bolus_u'] for a in audits])
    excess = np.array([a['excess_drop'] for a in audits])
    outcome_colors = {'appropriate': 'forestgreen', 'under_correction': 'goldenrod',
                      'over_correction': 'tomato', 'hypo': 'darkred'}
    for cat in categories:
        mask = np.array([a['outcome'] == cat for a in audits])
        if mask.sum() > 0:
            ax3.scatter(boluses[mask], excess[mask], alpha=0.5, s=25,
                        color=outcome_colors[cat], label=cat.replace('_', ' ').title(),
                        edgecolor='gray', linewidth=0.3)
    ax3.axhline(0, color='black', linewidth=1, linestyle='--', alpha=0.5)
    ax3.set_xlabel('Bolus Size (U)', fontsize=11)
    ax3.set_ylabel('Excess Drop (mg/dL)', fontsize=11)
    ax3.set_title('C. Excess Drop vs Dose', fontsize=12)
    ax3.legend(fontsize=8)
    ax3.grid(alpha=0.2)

    # Panel D: Dose ratio distributions
    ax4 = fig.add_subplot(gs[1, 1])
    for key, label, color in [
        ('dose_ratio_fixed', 'Fixed ISF', 'tomato'),
        ('dose_ratio_patient_log', 'Patient log-ISF', 'forestgreen'),
    ]:
        ratios = [a[key] for a in audits if a[key] is not None]
        # Clip for visualization
        ratios_clipped = np.clip(ratios, 0, 5)
        ax4.hist(ratios_clipped, bins=30, alpha=0.4, color=color,
                 label=f'{label} (med={np.median(ratios):.2f})',
                 edgecolor='black', linewidth=0.3)
    ax4.axvline(1.0, color='black', linewidth=2, linestyle='--',
                label='Perfect dose (ratio=1.0)')
    ax4.axvspan(0.75, 1.25, alpha=0.1, color='green', label='+/- 25% zone')
    ax4.set_xlabel('Recommended / Optimal Dose Ratio', fontsize=11)
    ax4.set_ylabel('Count', fontsize=11)
    ax4.set_title('D. Dose Recommendation Accuracy', fontsize=12)
    ax4.legend(fontsize=8)
    ax4.set_xlim(0, 5)

    fig.suptitle('Figure 42: Retrospective Correction Audit (EXP-2642)',
                 fontsize=14, fontweight='bold', y=0.98)
    plt.savefig(os.path.join(OUT_DIR, 'fig42_retrospective_audit.png'),
                dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    print("  fig42 saved")


def fig43_synthesis(r2641, r2642):
    """Synthesis: descriptive vs prescriptive insight."""
    fig = plt.figure(figsize=(14, 10))
    gs = GridSpec(2, 2, figure=fig, hspace=0.4, wspace=0.35)

    # Panel A: The gap between description and prescription
    ax1 = fig.add_subplot(gs[0, 0])
    # Show that the same model that DESCRIBES well (low bias)
    # PRESCRIBES badly (high dose ratio)
    models_desc = r2641['models']
    model_keys = ['A_fixed_isf', 'B_pop_log_isf', 'C_patient_log_isf',
                  'E_iob_weighted']
    desc_bias = [abs(models_desc[k]['bias']) for k in model_keys]
    # Approximate prescription accuracy from audit
    desc_labels = ['Fixed\nISF', 'Pop\nlog-ISF', 'Patient\nlog-ISF', 'IOB\nweighted']

    ax1.bar(range(4), desc_bias, color='steelblue', edgecolor='black', linewidth=0.5)
    for i, val in enumerate(desc_bias):
        ax1.text(i, val + 2, f'{val:.0f}', ha='center', fontsize=10, fontweight='bold')
    ax1.set_xticks(range(4))
    ax1.set_xticklabels(desc_labels, fontsize=9)
    ax1.set_ylabel('|Bias| in Drop Prediction (mg/dL)', fontsize=10)
    ax1.set_title('A. Descriptive Accuracy\n(lower = better predictor)', fontsize=11)
    ax1.grid(alpha=0.2, axis='y')

    # Panel B: The prescription problem
    ax2 = fig.add_subplot(gs[0, 1])
    audits = r2642['audits']
    # For fixed and patient-log, show dose ratio distributions
    fixed_ratios = [a['dose_ratio_fixed'] for a in audits if a['dose_ratio_fixed'] is not None]
    log_ratios = [a['dose_ratio_patient_log'] for a in audits
                  if a['dose_ratio_patient_log'] is not None]

    fixed_within = np.mean(np.abs(np.array(fixed_ratios) - 1.0) < 0.25) * 100
    log_within = np.mean(np.abs(np.array(log_ratios) - 1.0) < 0.25) * 100

    ax2.bar([0, 1], [fixed_within, log_within],
            color=['tomato', 'forestgreen'], edgecolor='black', linewidth=0.5,
            width=0.5)
    ax2.text(0, fixed_within + 1, f'{fixed_within:.0f}%', ha='center',
             fontsize=12, fontweight='bold')
    ax2.text(1, log_within + 1, f'{log_within:.0f}%', ha='center',
             fontsize=12, fontweight='bold')
    ax2.set_xticks([0, 1])
    ax2.set_xticklabels(['Fixed ISF', 'Patient log-ISF'], fontsize=10)
    ax2.set_ylabel('% Within +/-25% of Optimal Dose', fontsize=10)
    ax2.set_title('B. Prescriptive Accuracy\n(higher = better dose calculator)', fontsize=11)
    ax2.set_ylim(0, 50)
    ax2.grid(alpha=0.2, axis='y')

    # Panel C: Why the paradox exists - AID closed loop diagram
    ax3 = fig.add_subplot(gs[1, 0])
    ax3.axis('off')

    # Text-based diagram
    diagram = """
    THE CLOSED-LOOP PARADOX

    When we OBSERVE corrections:
    
      Bolus --> [Patient] --> Glucose Drop
                   ^                |
                   |    [AID Controller]
                   |        |
                   +-- Basal Withdrawal --+
    
    Apparent ISF = Drop / Dose
    (includes BOTH bolus AND controller effects)
    
    When we try to USE apparent ISF for dosing:
    
      Log-ISF(dose) x dose = predicted drop
      
    But changing the dose CHANGES the controller
    response, invalidating the ISF we measured!
    
    => Descriptive ISF != Prescriptive ISF
    """
    ax3.text(0.05, 0.95, diagram, transform=ax3.transAxes, fontsize=9,
             family='monospace', va='top',
             bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))
    ax3.set_title('C. The Closed-Loop Paradox', fontsize=11)

    # Panel D: Summary scorecard
    ax4 = fig.add_subplot(gs[1, 1])
    ax4.axis('off')

    findings = [
        ('DESCRIPTIVE FINDINGS (EXP-2641)', None, 'navy'),
        ('Per-patient log-ISF best predictor', True, None),
        ('  MAE: 84 -> 59 mg/dL (30% improvement)', True, None),
        ('  Bias: +35 -> -3 mg/dL (near-zero)', True, None),
        ('  All models R-squared < 0 (high variance)', False, None),
        ('', None, None),
        ('PRESCRIPTIVE FINDINGS (EXP-2642)', None, 'navy'),
        ('  34 hypo events (16% of corrections)', False, None),
        ('  Log-ISF prevents 29% of over-corrections', False, None),
        ('  Fixed ISF actually closer to optimal dosing', True, None),
        ('  No model within +/-25% for >25% of events', False, None),
        ('', None, None),
        ('KEY INSIGHT', None, 'darkred'),
        ('  Apparent ISF is an EMERGENT property', None, 'black'),
        ('  of the closed-loop system, not a', None, 'black'),
        ('  parameter that can be used for dosing.', None, 'black'),
    ]

    y = 0.97
    for text, passed, header_color in findings:
        if not text:
            y -= 0.02
            continue
        if header_color:
            ax4.text(0.02, y, text, transform=ax4.transAxes, fontsize=10,
                     fontweight='bold', color=header_color)
        else:
            marker = '[+]' if passed else '[X]' if passed is not None else '   '
            color = 'forestgreen' if passed else 'tomato' if passed is not None else 'black'
            ax4.text(0.02, y, marker, transform=ax4.transAxes, fontsize=9,
                     fontweight='bold', color=color, family='monospace')
            ax4.text(0.08, y, text, transform=ax4.transAxes, fontsize=9)
        y -= 0.055

    ax4.set_title('D. Round 5 Scorecard', fontsize=11)

    fig.suptitle('Figure 43: The Descriptive-Prescriptive Paradox',
                 fontsize=14, fontweight='bold', y=0.98)
    plt.savefig(os.path.join(OUT_DIR, 'fig43_synthesis.png'),
                dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    print("  fig43 saved")


def main():
    print("Round 5 Visualizations")
    print("=" * 40)
    r2641, r2642 = load_results()

    fig40_model_comparison(r2641)
    fig41_scatter(r2641)
    fig42_audit(r2642)
    fig43_synthesis(r2641, r2642)

    print("\nAll Round 5 figures saved.")


if __name__ == '__main__':
    main()
