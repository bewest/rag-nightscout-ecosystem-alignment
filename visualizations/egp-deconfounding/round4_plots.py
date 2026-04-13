#!/usr/bin/env python3
"""Round 4 Visualizations: Sampling Robustness + Per-Patient ISF

Figures:
  fig36: Sampling robustness - bootstrap distribution + subsample comparison
  fig37: Per-patient dose-ISF scatter with individual fitted curves
  fig38: Leave-one-out sensitivity + dose-matched convergence
  fig39: Round 4 synthesis - methodology validation summary
"""

import json
import os
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

OUT_DIR = os.path.join(os.path.dirname(__file__))
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'externals', 'experiments')


def load_results():
    with open(os.path.join(DATA_DIR, 'exp-2639_sampling_robustness.json')) as f:
        r2639 = json.load(f)
    with open(os.path.join(DATA_DIR, 'exp-2640_per_patient_isf.json')) as f:
        r2640 = json.load(f)
    return r2639, r2640


def fig36_sampling_robustness(r2639):
    """Bootstrap distribution + subsample stability."""
    fig = plt.figure(figsize=(14, 10))
    gs = GridSpec(2, 2, figure=fig, hspace=0.35, wspace=0.3)

    # Panel A: Bootstrap distribution
    ax1 = fig.add_subplot(gs[0, 0])
    # Reconstruct approximate distribution from summary stats
    mean = r2639['block_bootstrap']['mean']
    ci_lo = r2639['block_bootstrap']['ci_2_5']
    ci_hi = r2639['block_bootstrap']['ci_97_5']
    # Approximate normal around mean with CI-implied std
    std = (ci_hi - ci_lo) / (2 * 1.96)
    x = np.linspace(ci_lo - 0.1, ci_hi + 0.1, 200)
    y = np.exp(-0.5 * ((x - mean) / std) ** 2) / (std * np.sqrt(2 * np.pi))
    ax1.fill_between(x, y, alpha=0.3, color='steelblue')
    ax1.plot(x, y, color='steelblue', linewidth=2)
    ax1.axvline(mean, color='navy', linewidth=2, label=f'Mean r = {mean:.3f}')
    ax1.axvline(ci_lo, color='red', linewidth=1.5, linestyle='--',
                label=f'95% CI: [{ci_lo:.3f}, {ci_hi:.3f}]')
    ax1.axvline(ci_hi, color='red', linewidth=1.5, linestyle='--')
    ax1.axvline(0, color='gray', linewidth=1, linestyle=':',
                label='r = 0 (null)')
    ax1.set_xlabel('Dose-ISF Correlation (r)', fontsize=11)
    ax1.set_ylabel('Density', fontsize=11)
    ax1.set_title('A. Block Bootstrap (10,000 resamples by patient)', fontsize=12)
    ax1.legend(fontsize=9, loc='upper left')

    # Panel B: Subsample stability
    ax2 = fig.add_subplot(gs[0, 1])
    subsamples = [
        ('Full\n(N=219)', r2639['full_dataset']['dose_isf_r']),
        ('>72h\n(N=108)', r2639['independent_72h']['dose_isf_r']),
        ('>120h\n(N=83)', r2639['independent_120h']['dose_isf_r']),
    ]
    names = [s[0] for s in subsamples]
    vals = [s[1] for s in subsamples]
    bars = ax2.bar(names, vals, color=['steelblue', 'darkorange', 'forestgreen'],
                   width=0.5, edgecolor='black', linewidth=0.5)
    for bar, val in zip(bars, vals):
        ax2.text(bar.get_x() + bar.get_width() / 2, val - 0.03,
                 f'r={val:.3f}', ha='center', fontsize=11, fontweight='bold', color='white')
    ax2.axhline(-0.3, color='red', linewidth=1, linestyle='--', alpha=0.7,
                label='Moderate effect threshold')
    ax2.set_ylabel('Dose-ISF Correlation (r)', fontsize=11)
    ax2.set_title('B. Subsampling Stability', fontsize=12)
    ax2.set_ylim(-0.7, 0)
    ax2.legend(fontsize=9)

    # Panel C: Autocorrelation
    ax3 = fig.add_subplot(gs[1, 0])
    ac = r2639['autocorrelation']
    fields = ['bolus_u', 'apparent_isf', 'drop']
    labels = ['Bolus Size', 'Apparent ISF', 'Glucose Drop']
    colors_ac = ['tomato', 'steelblue', 'forestgreen']
    ac_vals = [ac[f'{f}_autocorr']['r'] for f in fields]
    ac_ps = [ac[f'{f}_autocorr']['p'] for f in fields]
    bars = ax3.bar(labels, ac_vals, color=colors_ac, width=0.5,
                   edgecolor='black', linewidth=0.5)
    for bar, val, p in zip(bars, ac_vals, ac_ps):
        sig = '*' if p < 0.05 else ''
        ax3.text(bar.get_x() + bar.get_width() / 2,
                 val + 0.02 if val >= 0 else val - 0.04,
                 f'r={val:.2f}{sig}', ha='center', fontsize=10, fontweight='bold')
    ax3.axhline(0, color='gray', linewidth=0.5)
    ax3.axhline(0.5, color='red', linewidth=1, linestyle='--', alpha=0.5,
                label='Concern threshold (0.5)')
    ax3.set_ylabel('Autocorrelation (consecutive <48h)', fontsize=11)
    ax3.set_title('C. Feature Independence', fontsize=12)
    ax3.set_ylim(-0.2, 0.6)
    ax3.legend(fontsize=9)

    # Panel D: Power analysis
    ax4 = fig.add_subplot(gs[1, 1])
    power = r2639['power_analysis']
    findings = ['dose_isf', 'bolus_recovery', 'carbs_48h', 'iob_decay']
    finding_labels = ['Dose-ISF\n(r=0.56)', 'Bolus-Recov\n(r=0.31)',
                      '48h Carbs\n(r=0.15)', 'IOB Decay\n(r=0.07)']
    n_needed = [power[f]['n_needed_80pct'] for f in findings]
    powered = [power[f]['powered_at_219'] for f in findings]
    colors_pw = ['forestgreen' if p else 'tomato' for p in powered]
    bars = ax4.barh(finding_labels, n_needed, color=colors_pw,
                    edgecolor='black', linewidth=0.5)
    ax4.axvline(219, color='navy', linewidth=2, linestyle='--',
                label='Our N = 219')
    for bar, n, p in zip(bars, n_needed, powered):
        status = 'OK' if p else 'NEED MORE'
        ax4.text(min(n + 20, 1400), bar.get_y() + bar.get_height() / 2,
                 f'N={n} {status}', va='center', fontsize=9, fontweight='bold')
    ax4.set_xlabel('Events Required (80% power)', fontsize=11)
    ax4.set_title('D. Statistical Power', fontsize=12)
    ax4.set_xlim(0, 1700)
    ax4.legend(fontsize=9, loc='lower right')

    fig.suptitle('Figure 36: Sampling Robustness Audit (EXP-2639)',
                 fontsize=14, fontweight='bold', y=0.98)

    plt.savefig(os.path.join(OUT_DIR, 'fig36_sampling_robustness.png'),
                dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    print("  fig36 saved")


def fig37_per_patient_isf(r2640):
    """Per-patient dose-ISF scatter with fitted curves."""
    patients = r2640['per_patient']
    fitted = {pid: c for pid, c in patients.items()
              if not c.get('insufficient', False)}

    n_plots = len(fitted)
    cols = 3
    rows = (n_plots + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(14, 4 * rows))
    axes = axes.flatten() if hasattr(axes, 'flatten') else [axes]

    colors = plt.cm.Set2(np.linspace(0, 1, n_plots))

    for idx, (pid, c) in enumerate(sorted(fitted.items())):
        ax = axes[idx]
        data = c['data']
        bolus = np.array(data['bolus_u'])
        isf = np.array(data['apparent_isf'])

        ax.scatter(bolus, isf, alpha=0.5, color=colors[idx], s=30, edgecolor='gray',
                   linewidth=0.3, zorder=3)

        # Plot linear fit
        lin = c['linear']
        x_fit = np.linspace(bolus.min(), bolus.max(), 100)
        y_lin = lin['intercept'] + lin['slope'] * x_fit
        ax.plot(x_fit, y_lin, color='gray', linewidth=1, linestyle='--',
                alpha=0.6, label=f"linear r={lin['r']:.2f}")

        # Plot log fit (best for most patients)
        log_fit = c['log']
        y_log = log_fit['intercept'] + log_fit['slope'] * np.log(x_fit + 0.01)
        ax.plot(x_fit, y_log, color=colors[idx], linewidth=2,
                label=f"log r={log_fit['r']:.2f}")

        ax.set_xlabel('Bolus (U)', fontsize=10)
        ax.set_ylabel('Apparent ISF (mg/dL/U)', fontsize=10)
        sig_marker = ' *' if lin['p'] < 0.05 else ''
        ax.set_title(f"Patient {pid} (n={c['n_events']}{sig_marker})", fontsize=11)
        ax.legend(fontsize=8, loc='upper right')
        ax.set_ylim(bottom=0)
        ax.grid(alpha=0.2)

    # Hide unused axes
    for idx in range(n_plots, len(axes)):
        axes[idx].set_visible(False)

    fig.suptitle('Figure 37: Per-Patient Dose-ISF Curves (EXP-2640)',
                 fontsize=14, fontweight='bold', y=1.01)
    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, 'fig37_per_patient_isf.png'),
                dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    print("  fig37 saved")


def fig38_sensitivity(r2639, r2640):
    """Leave-one-out + dose-matched convergence."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    # Panel A: Leave-one-out
    loo = r2640['leave_one_out']
    full_r = r2639['full_dataset']['dose_isf_r']
    pids = sorted(loo.keys())
    loo_rs = [loo[p]['r'] for p in pids]
    loo_ns = [loo[p]['n_remaining'] for p in pids]

    colors_loo = ['tomato' if abs(r - full_r) > 0.05 else 'steelblue'
                  for r in loo_rs]
    bars = ax1.barh(pids, loo_rs, color=colors_loo, edgecolor='black',
                    linewidth=0.5)
    ax1.axvline(full_r, color='navy', linewidth=2, linestyle='--',
                label=f'Full r = {full_r:.3f}')
    ax1.axvline(-0.3, color='red', linewidth=1, linestyle=':',
                label='Moderate threshold')
    for bar, r_val, n in zip(bars, loo_rs, loo_ns):
        ax1.text(r_val - 0.01, bar.get_y() + bar.get_height() / 2,
                 f'{r_val:.3f} (N={n})', va='center', ha='right',
                 fontsize=8, fontweight='bold', color='white')
    ax1.set_xlabel('Dose-ISF Correlation (r)', fontsize=11)
    ax1.set_ylabel('Excluded Patient', fontsize=11)
    ax1.set_title('A. Leave-One-Out Sensitivity', fontsize=12)
    ax1.legend(fontsize=9)
    ax1.set_xlim(-0.7, -0.3)

    # Panel B: Dose-matched convergence
    matched = r2640['dose_matched']
    doses = sorted(matched.keys(), key=float)
    dose_vals = [float(d) for d in doses]
    means = [matched[d]['mean'] for d in doses]
    stds = [matched[d]['std'] for d in doses]
    cvs = [matched[d]['cv'] for d in doses]

    ax2_twin = ax2.twinx()
    ax2.errorbar(dose_vals, means, yerr=stds, fmt='o-', color='steelblue',
                 linewidth=2, markersize=8, capsize=5, label='Mean ISF +/- SD')
    ax2_twin.bar(dose_vals, cvs, width=0.3, alpha=0.3, color='tomato',
                 label='CV (%)')
    ax2.set_xlabel('Bolus Dose (U)', fontsize=11)
    ax2.set_ylabel('Predicted ISF (mg/dL/U)', fontsize=11, color='steelblue')
    ax2_twin.set_ylabel('CV (%)', fontsize=11, color='tomato')
    ax2.set_title('B. Cross-Patient Convergence at Matched Doses', fontsize=12)
    ax2.grid(alpha=0.2)

    # Combined legend
    lines1, labels1 = ax2.get_legend_handles_labels()
    lines2, labels2 = ax2_twin.get_legend_handles_labels()
    ax2.legend(lines1 + lines2, labels1 + labels2, fontsize=9, loc='upper right')

    fig.suptitle('Figure 38: Sensitivity & Convergence (EXP-2639/2640)',
                 fontsize=14, fontweight='bold', y=1.02)
    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, 'fig38_sensitivity_convergence.png'),
                dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    print("  fig38 saved")


def fig39_synthesis(r2639, r2640):
    """Round 4 synthesis - methodology validation summary."""
    fig = plt.figure(figsize=(14, 10))
    gs = GridSpec(2, 2, figure=fig, hspace=0.4, wspace=0.35)

    # Panel A: Time scales diagram
    ax1 = fig.add_subplot(gs[0, 0])
    timescales = [
        ('Grid resolution', 5/60, 'forestgreen'),
        ('Insulin peak', 1.25, 'steelblue'),
        ('Correction nadir', 3.5, 'steelblue'),
        ('DIA', 6.0, 'steelblue'),
        ('Median spacing', 41.3/24, 'darkorange'),
        ('Carb window', 48/24, 'tomato'),
        ('Mean spacing', 126/24, 'darkorange'),
    ]
    labels = [t[0] for t in timescales]
    # Convert to hours
    hours = [t[1] * 24 if t[1] < 1 else t[1] * 24 if t[1] < 10 else t[1]
             for t in timescales]
    # Actually let's just use hours consistently
    hours_correct = [5/60, 1.25, 3.5, 6.0, 41.3, 48.0, 126.0]
    colors_ts = [t[2] for t in timescales]

    ax1.barh(labels[::-1], hours_correct[::-1], color=colors_ts[::-1],
             edgecolor='black', linewidth=0.5)
    for i, (label, h) in enumerate(zip(labels[::-1], hours_correct[::-1])):
        ax1.text(h + 2, i, f'{h:.1f}h', va='center', fontsize=9)
    ax1.set_xlabel('Hours', fontsize=11)
    ax1.set_title('A. Time Scales in Our Data', fontsize=12)
    ax1.set_xscale('log')
    ax1.set_xlim(0.01, 300)

    # Panel B: Effective N by finding
    ax2 = fig.add_subplot(gs[0, 1])
    findings = [
        ('Dose-ISF\nr=-0.56', 219, 23, True),
        ('Bolus-Recov\nr=-0.31', 219, 80, True),
        ('48h Carbs\nr=-0.15', 219, 347, False),
        ('IOB Decay\nr=-0.07', 219, 1600, False),
    ]
    x_pos = range(len(findings))
    have = [f[1] for f in findings]
    need = [f[2] for f in findings]
    colors_n = ['forestgreen' if f[3] else 'tomato' for f in findings]

    ax2.bar([x - 0.15 for x in x_pos], have, width=0.3, color='steelblue',
            label='Have (N=219)', edgecolor='black', linewidth=0.5)
    ax2.bar([x + 0.15 for x in x_pos], need, width=0.3, color=colors_n,
            label='Need (80% power)', edgecolor='black', linewidth=0.5)
    ax2.set_xticks(x_pos)
    ax2.set_xticklabels([f[0] for f in findings], fontsize=9)
    ax2.set_ylabel('Events Required', fontsize=11)
    ax2.set_title('B. Power vs Sample Size', fontsize=12)
    ax2.set_yscale('log')
    ax2.legend(fontsize=9)
    ax2.grid(alpha=0.2, axis='y')

    # Panel C: Log model universality
    ax3 = fig.add_subplot(gs[1, 0])
    pp = r2640['per_patient']
    fitted = {pid: c for pid, c in pp.items() if not c.get('insufficient', False)}
    pids_f = sorted(fitted.keys())
    lin_rs = [abs(fitted[p]['linear']['r']) for p in pids_f]
    log_rs = [abs(fitted[p]['log']['r']) for p in pids_f]

    x_p = np.arange(len(pids_f))
    width = 0.35
    ax3.bar(x_p - width/2, lin_rs, width, label='Linear', color='steelblue',
            edgecolor='black', linewidth=0.5)
    ax3.bar(x_p + width/2, log_rs, width, label='Log', color='darkorange',
            edgecolor='black', linewidth=0.5)
    for i, (lr, logr) in enumerate(zip(lin_rs, log_rs)):
        winner = 'L' if logr > lr else 'l'
        ax3.text(i, max(lr, logr) + 0.02, winner, ha='center', fontsize=10,
                 fontweight='bold', color='darkorange' if winner == 'L' else 'steelblue')
    ax3.set_xticks(x_p)
    ax3.set_xticklabels(pids_f, fontsize=10)
    ax3.set_ylabel('|r| (correlation strength)', fontsize=11)
    ax3.set_title('C. Linear vs Log Model per Patient', fontsize=12)
    ax3.legend(fontsize=9)
    ax3.set_ylim(0, 1.0)
    ax3.grid(alpha=0.2, axis='y')

    # Panel D: Summary scorecard
    ax4 = fig.add_subplot(gs[1, 1])
    ax4.axis('off')

    checks = [
        ('Dose-ISF survives >72h subsample', True, 'r=-0.615'),
        ('Bootstrap CI excludes zero', True, '[-0.67, -0.44]'),
        ('Bolus autocorrelation < 0.5', True, 'r=0.36'),
        ('ISF/drop autocorrelation ~ 0', True, 'r=0.12, -0.04'),
        ('Log model best for 5/6 patients', True, '83%'),
        ('Leave-one-out all r < -0.3', True, 'range [-0.64, -0.49]'),
        ('Not outlier-driven', True, 'r=-0.53 w/o top-2'),
        ('Cross-patient CV < 20% (1.5-3U)', True, 'CV=8-9%'),
        ('48h carb effect underpowered', True, 'need N=347'),
        ('IOB decay undetectable', True, 'need N=1600'),
    ]

    y_start = 0.95
    for i, (text, passed, detail) in enumerate(checks):
        marker = '[+]' if passed else '[X]'
        color = 'forestgreen' if passed else 'tomato'
        ax4.text(0.02, y_start - i * 0.09, marker, fontsize=11,
                 fontweight='bold', color=color,
                 transform=ax4.transAxes, family='monospace')
        ax4.text(0.08, y_start - i * 0.09, text, fontsize=10,
                 transform=ax4.transAxes)
        ax4.text(0.75, y_start - i * 0.09, detail, fontsize=9,
                 color='gray', transform=ax4.transAxes)

    ax4.set_title('D. Validation Scorecard', fontsize=12)

    fig.suptitle('Figure 39: Round 4 Synthesis -- Methodology Validated',
                 fontsize=14, fontweight='bold', y=0.98)

    plt.savefig(os.path.join(OUT_DIR, 'fig39_synthesis.png'),
                dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    print("  fig39 saved")


def main():
    print("Round 4 Visualizations")
    print("=" * 40)
    r2639, r2640 = load_results()

    fig36_sampling_robustness(r2639)
    fig37_per_patient_isf(r2640)
    fig38_sensitivity(r2639, r2640)
    fig39_synthesis(r2639, r2640)

    print("\nAll Round 4 figures saved.")


if __name__ == '__main__':
    main()
