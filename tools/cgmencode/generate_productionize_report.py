#!/usr/bin/env python3
"""Generate visualizations for the autoproductionize summary report.

Reads experiment results from externals/experiments/ and produces
figures summarizing what each production module does and why.
"""

import json
import glob
import sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
EXPERIMENTS = ROOT / 'externals' / 'experiments'
VIS_DIR = ROOT / 'visualizations' / 'autoproductionize-summary'

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
except ImportError:
    print("matplotlib required: pip install matplotlib")
    sys.exit(1)

plt.rcParams.update({
    'figure.figsize': (10, 6),
    'font.size': 11,
    'axes.titlesize': 13,
    'axes.labelsize': 11,
})

PATIENTS = list('abcdefghijk')


def load_exp(pattern):
    files = sorted(glob.glob(str(EXPERIMENTS / pattern)))
    if not files:
        return None
    return json.load(open(files[0]))


# ── Figure 1: Fidelity vs ADA Grade Comparison ─────────────────────────

def fig1_fidelity_vs_ada():
    """Side-by-side comparison of ADA grading vs Fidelity grading."""
    combined = load_exp('exp-1531_fidelity_combined.json')
    if not combined:
        print("SKIP fig1: no exp-1531 data")
        return
    data = combined.get('1531', combined)
    pop = data.get('population', {})
    per_patient = data.get('per_patient', {})

    ada_grades = []
    fid_grades = []
    rmse_vals = []
    tir_vals = []
    names = []
    for pid in PATIENTS:
        if pid not in per_patient:
            continue
        p = per_patient[pid]
        fid = p.get('fidelity', p)
        ada = p.get('ada', p)
        ada_grades.append(ada.get('grade', 'C'))
        fid_grades.append(fid.get('fidelity_grade', fid.get('grade', 'Acceptable')))
        rmse_vals.append(fid.get('rmse', 10))
        tir_vals.append(ada.get('tir', 50))
        names.append(pid)

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # ADA grade distribution
    ada_map = {'A': 0, 'B': 1, 'C': 2, 'D': 3}
    fid_map = {'Excellent': 0, 'Good': 1, 'Acceptable': 2, 'Poor': 3}
    ada_colors = {'A': '#2ecc71', 'B': '#f1c40f', 'C': '#e67e22', 'D': '#e74c3c'}
    fid_colors = {'Excellent': '#2ecc71', 'Good': '#3498db', 'Acceptable': '#f1c40f', 'Poor': '#e74c3c'}

    x = np.arange(len(names))
    ada_nums = [ada_map.get(g, 2) for g in ada_grades]
    fid_nums = [fid_map.get(g, 2) for g in fid_grades]

    bars1 = axes[0].bar(x - 0.2, [4 - v for v in ada_nums], 0.35,
                        color=[ada_colors.get(g, '#999') for g in ada_grades],
                        label='ADA Grade', edgecolor='white')
    bars2 = axes[0].bar(x + 0.2, [4 - v for v in fid_nums], 0.35,
                        color=[fid_colors.get(g, '#999') for g in fid_grades],
                        label='Fidelity Grade', edgecolor='white', hatch='//')
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(names, fontweight='bold')
    axes[0].set_ylabel('Grade Quality →')
    axes[0].set_yticks([1, 2, 3, 4])
    axes[0].set_yticklabels(['D/Poor', 'C/Accept.', 'B/Good', 'A/Excell.'])
    axes[0].set_title('ADA vs Fidelity Grade by Patient')
    axes[0].legend(loc='lower right')

    # Concordance scatter
    agree = sum(1 for a, f in zip(ada_nums, fid_nums) if a == f)
    total = len(ada_nums)
    concordance = agree / total * 100 if total else 0

    axes[1].scatter(tir_vals, rmse_vals, c=[fid_colors.get(g, '#999') for g in fid_grades],
                    s=120, edgecolors='black', linewidth=1, zorder=5)
    for i, pid in enumerate(names):
        axes[1].annotate(pid, (tir_vals[i], rmse_vals[i]), fontweight='bold',
                         ha='center', va='bottom', fontsize=9)
    axes[1].set_xlabel('Time in Range (%) — ADA metric')
    axes[1].set_ylabel('RMSE (mg/dL/5min) — Fidelity metric')
    axes[1].set_title(f'TIR vs RMSE (concordance: {concordance:.0f}%)')
    axes[1].axhline(y=6, color='green', linestyle='--', alpha=0.5, label='Excellent threshold')
    axes[1].axhline(y=9, color='blue', linestyle='--', alpha=0.5, label='Good threshold')
    axes[1].axhline(y=11, color='orange', linestyle='--', alpha=0.5, label='Acceptable threshold')
    axes[1].legend(fontsize=8)
    axes[1].invert_yaxis()

    plt.tight_layout()
    plt.savefig(VIS_DIR / 'fig1_fidelity_vs_ada.png', dpi=150)
    plt.close()
    print("  fig1_fidelity_vs_ada.png")


# ── Figure 2: Harmonic vs Sinusoidal Circadian ──────────────────────────

def fig2_harmonic_circadian():
    """4-harmonic vs sinusoidal R² comparison."""
    sin_data = load_exp('exp-1631_temporal.json')
    harm_data = load_exp('exp-1632_temporal.json')
    if not sin_data or not harm_data:
        print("SKIP fig2: no temporal data")
        return

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    # R² comparison
    sin_r2 = [sin_data['patients'][p]['r2'] for p in PATIENTS if p in sin_data['patients']]
    harm_r2 = [harm_data['patients'][p]['r2_full'] for p in PATIENTS if p in harm_data['patients']]
    pids = [p for p in PATIENTS if p in sin_data['patients'] and p in harm_data['patients']]
    x = np.arange(len(pids))

    axes[0].bar(x - 0.2, sin_r2[:len(pids)], 0.35, color='#e74c3c', label='Sinusoidal (1 harmonic)', alpha=0.8)
    axes[0].bar(x + 0.2, harm_r2[:len(pids)], 0.35, color='#2ecc71', label='4-Harmonic', alpha=0.8)
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(pids, fontweight='bold')
    axes[0].set_ylabel('R²')
    axes[0].set_title('Circadian Model Fit: Sinusoidal vs 4-Harmonic')
    axes[0].legend()
    axes[0].set_ylim(0, 1.05)
    axes[0].axhline(y=np.mean(sin_r2[:len(pids)]), color='#e74c3c', linestyle='--', alpha=0.5)
    axes[0].axhline(y=np.mean(harm_r2[:len(pids)]), color='#2ecc71', linestyle='--', alpha=0.5)

    # Example patient hourly means with both fits
    pid = 'a'
    if pid in sin_data['patients'] and 'hourly_means' in sin_data['patients'][pid]:
        hourly = sin_data['patients'][pid]['hourly_means']
        hours = np.arange(24)
        means = [hourly.get(str(h), 0) for h in hours]
        axes[1].plot(hours, means, 'ko-', markersize=4, label='Observed hourly mean', zorder=5)

        # Sinusoidal fit
        amp = sin_data['patients'][pid]['amplitude']
        phase = sin_data['patients'][pid]['phase_hours']
        baseline = sin_data['patients'][pid]['baseline']
        t = np.linspace(0, 24, 200)
        sin_fit = baseline + amp * np.sin(2 * np.pi * (t - phase) / 24)
        axes[1].plot(t, sin_fit, 'r-', linewidth=2, alpha=0.7,
                     label=f'Sinusoidal (R²={sin_data["patients"][pid]["r2"]:.3f})')

        # 4-harmonic — use cumulative R² to show improvement
        if pid in harm_data['patients'] and 'harmonic_r2' in harm_data['patients'][pid]:
            hr2 = harm_data['patients'][pid]['harmonic_r2']
            axes[1].axhline(y=harm_data['patients'][pid]['r2_full'],
                            color='g', linestyle=':', alpha=0.5)
            axes[1].text(22, harm_data['patients'][pid]['r2_full'] + 2,
                         f'4-Harmonic R²={harm_data["patients"][pid]["r2_full"]:.3f}',
                         color='green', fontsize=9)

        axes[1].set_xlabel('Hour of Day')
        axes[1].set_ylabel('Mean Glucose (mg/dL)')
        axes[1].set_title(f'Patient {pid}: Circadian Fit Comparison')
        axes[1].legend(fontsize=9)
        axes[1].set_xlim(0, 23)

    plt.tight_layout()
    plt.savefig(VIS_DIR / 'fig2_harmonic_circadian.png', dpi=150)
    plt.close()
    print("  fig2_harmonic_circadian.png")


# ── Figure 3: AID-Aware ISF ─────────────────────────────────────────────

def fig3_isf_aid():
    """AID loop feedback and ISF correction."""
    isf_data = load_exp('exp-1603_isf_aid.json')
    if not isf_data:
        print("SKIP fig3: no isf data")
        return

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    # AID feedback: damped vs boosted corrections
    pids = [p for p in PATIENTS if p in isf_data['patients']]
    n_damped = [isf_data['patients'][p].get('n_damped', 0) for p in pids]
    n_boosted = [isf_data['patients'][p].get('n_boosted', 0) for p in pids]
    n_neutral = [isf_data['patients'][p].get('n_neutral', 0) for p in pids]
    x = np.arange(len(pids))

    axes[0].bar(x, n_damped, 0.5, color='#e74c3c', label='Damped by AID', alpha=0.8)
    axes[0].bar(x, n_neutral, 0.5, bottom=n_damped, color='#95a5a6', label='Neutral', alpha=0.8)
    axes[0].bar(x, n_boosted, 0.5,
                bottom=[d + n for d, n in zip(n_damped, n_neutral)],
                color='#2ecc71', label='Boosted by AID', alpha=0.8)
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(pids, fontweight='bold')
    axes[0].set_ylabel('Number of Corrections')
    axes[0].set_title('AID Loop Feedback During Corrections')
    axes[0].legend(fontsize=9)

    # ISF comparison: damped vs boosted median
    damped_isf = []
    boosted_isf = []
    labels = []
    for p in pids:
        d = isf_data['patients'][p]
        di = d.get('damped_isf_median')
        bi = d.get('boosted_isf_median')
        if di is not None and bi is not None:
            damped_isf.append(di)
            boosted_isf.append(bi)
            labels.append(p)

    if damped_isf:
        x2 = np.arange(len(labels))
        axes[1].bar(x2 - 0.2, damped_isf, 0.35, color='#e74c3c', label='ISF (damped windows)', alpha=0.8)
        axes[1].bar(x2 + 0.2, boosted_isf, 0.35, color='#2ecc71', label='ISF (boosted windows)', alpha=0.8)
        axes[1].set_xticks(x2)
        axes[1].set_xticklabels(labels, fontweight='bold')
        axes[1].set_ylabel('ISF (mg/dL per unit)')
        axes[1].set_title('ISF Varies by AID State')
        axes[1].legend(fontsize=9)
    else:
        axes[1].text(0.5, 0.5, 'Insufficient data\nfor ISF comparison',
                     ha='center', va='center', transform=axes[1].transAxes)
        axes[1].set_title('ISF by AID State')

    plt.tight_layout()
    plt.savefig(VIS_DIR / 'fig3_isf_aid_feedback.png', dpi=150)
    plt.close()
    print("  fig3_isf_aid_feedback.png")


# ── Figure 4: Alert Filtering ───────────────────────────────────────────

def fig4_alerts():
    """Multi-feature alert scoring AUC and burst dedup impact."""
    alert_data = load_exp('exp-1613_alert_filtering.json')
    if not alert_data:
        print("SKIP fig4: no alert data")
        return

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    pids = [p for p in PATIENTS if p in alert_data['patients']]
    aucs = [alert_data['patients'][p].get('auc', 0) for p in pids]
    ppvs = [alert_data['patients'][p].get('ppv', 0) for p in pids]
    alerts_day = [alert_data['patients'][p].get('alerts_per_day', 0) for p in pids]

    # AUC comparison
    x = np.arange(len(pids))
    colors = ['#2ecc71' if a > 0.85 else '#f1c40f' if a > 0.75 else '#e74c3c' for a in aucs]
    axes[0].bar(x, aucs, color=colors, edgecolor='white')
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(pids, fontweight='bold')
    axes[0].set_ylabel('AUC')
    axes[0].set_title(f'Multi-Feature Alert Scoring (mean AUC={np.mean(aucs):.3f})')
    axes[0].axhline(y=0.9, color='green', linestyle='--', alpha=0.4, label='AUC=0.90')
    axes[0].set_ylim(0.5, 1.0)
    axes[0].legend(fontsize=9)

    # Alerts/day vs PPV tradeoff
    sc = axes[1].scatter(alerts_day, ppvs, c=aucs, cmap='RdYlGn', s=120,
                         edgecolors='black', linewidth=1, vmin=0.7, vmax=1.0, zorder=5)
    for i, pid in enumerate(pids):
        axes[1].annotate(pid, (alerts_day[i], ppvs[i]), fontweight='bold',
                         ha='center', va='bottom', fontsize=9)
    axes[1].set_xlabel('Alerts per Day')
    axes[1].set_ylabel('PPV (Precision)')
    axes[1].set_title('Alert Volume vs Precision Tradeoff')
    plt.colorbar(sc, ax=axes[1], label='AUC')

    plt.tight_layout()
    plt.savefig(VIS_DIR / 'fig4_alert_filtering.png', dpi=150)
    plt.close()
    print("  fig4_alert_filtering.png")


# ── Figure 5: Confidence Grades ──────────────────────────────────────────

def fig5_confidence():
    """Recommendation confidence grade distribution."""
    conf_data = load_exp('exp-1625_confidence.json')
    if not conf_data:
        print("SKIP fig5: no confidence data")
        return

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    pids = [p for p in PATIENTS if p in conf_data['patients']]
    isf_changes = []
    cr_changes = []
    isf_labels = []
    for p in pids:
        d = conf_data['patients'][p]
        scenarios = d.get('scenarios', {})
        point = scenarios.get('point', {})
        low = scenarios.get('isf_low_cr_low', {})
        high = scenarios.get('isf_high_cr_high', scenarios.get('isf_hi_cr_hi', {}))
        if point and low and high:
            isf_range = abs(high.get('isf_rec', 0) - low.get('isf_rec', 0))
            cr_range = abs(high.get('cr_rec', 0) - low.get('cr_rec', 0))
            base_isf = point.get('isf_rec', 1)
            base_cr = point.get('cr_rec', 1)
            isf_ci = isf_range / max(abs(base_isf), 0.01) * 100
            cr_ci = cr_range / max(abs(base_cr), 0.01) * 100
            isf_changes.append(isf_ci)
            cr_changes.append(cr_ci)
            isf_labels.append(p)

    if isf_changes:
        x = np.arange(len(isf_labels))
        # ISF CI width
        isf_colors = ['#2ecc71' if v <= 30 else '#3498db' if v <= 46 else '#f1c40f' if v <= 60 else '#e74c3c'
                       for v in isf_changes]
        axes[0].bar(x, isf_changes, color=isf_colors, edgecolor='white')
        axes[0].set_xticks(x)
        axes[0].set_xticklabels(isf_labels, fontweight='bold')
        axes[0].set_ylabel('CI Width (%)')
        axes[0].set_title('ISF Recommendation Confidence')
        axes[0].axhline(y=30, color='green', linestyle='--', alpha=0.4, label='Grade A')
        axes[0].axhline(y=46, color='blue', linestyle='--', alpha=0.4, label='Grade B')
        axes[0].axhline(y=60, color='orange', linestyle='--', alpha=0.4, label='Grade C')
        axes[0].legend(fontsize=8)

        # CR CI width
        cr_colors = ['#2ecc71' if v <= 5 else '#3498db' if v <= 10 else '#f1c40f' if v <= 15 else '#e74c3c'
                      for v in cr_changes]
        axes[1].bar(x, cr_changes, color=cr_colors, edgecolor='white')
        axes[1].set_xticks(x)
        axes[1].set_xticklabels(isf_labels, fontweight='bold')
        axes[1].set_ylabel('CI Width (%)')
        axes[1].set_title('CR Recommendation Confidence')
        axes[1].axhline(y=5, color='green', linestyle='--', alpha=0.4, label='Grade A')
        axes[1].axhline(y=10, color='blue', linestyle='--', alpha=0.4, label='Grade B')
        axes[1].axhline(y=15, color='orange', linestyle='--', alpha=0.4, label='Grade C')
        axes[1].legend(fontsize=8)

    plt.tight_layout()
    plt.savefig(VIS_DIR / 'fig5_confidence_grades.png', dpi=150)
    plt.close()
    print("  fig5_confidence_grades.png")


# ── Figure 6: Meal Archetypes ────────────────────────────────────────────

def fig6_meals():
    """Meal archetype distribution and CR effectiveness."""
    meal_data = load_exp('exp-1593_meal_clustering.json')
    if not meal_data:
        print("SKIP fig6: no meal data")
        return

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    cluster_cr = meal_data.get('cluster_cr', {})

    # Archetype distribution
    labels_arch = []
    announced = []
    unannounced = []
    excursions = []
    for cid, info in sorted(cluster_cr.items()):
        label = info.get('label', f'cluster_{cid}')
        labels_arch.append(label.replace('_', '\n'))
        announced.append(info.get('n_announced', 0))
        unannounced.append(info.get('n_unannounced', 0))
        excursions.append(info.get('announced_mean_excursion') or 0)

    if labels_arch:
        x = np.arange(len(labels_arch))
        axes[0].bar(x - 0.2, announced, 0.35, color='#3498db', label='Announced', alpha=0.8)
        axes[0].bar(x + 0.2, unannounced, 0.35, color='#e67e22', label='Unannounced (UAM)', alpha=0.8)
        axes[0].set_xticks(x)
        axes[0].set_xticklabels(labels_arch, fontweight='bold')
        axes[0].set_ylabel('Number of Meals')
        axes[0].set_title('Meal Archetype Distribution')
        axes[0].legend()

        # Excursion comparison
        axes[1].bar(x, excursions, color=['#2ecc71', '#e74c3c'][:len(x)], alpha=0.8, edgecolor='white')
        axes[1].set_xticks(x)
        axes[1].set_xticklabels(labels_arch, fontweight='bold')
        axes[1].set_ylabel('Mean Excursion (mg/dL)')
        axes[1].set_title('Excursion by Archetype')
        axes[1].axhline(y=60, color='red', linestyle='--', alpha=0.5, label='Archetype threshold')
        axes[1].legend()

    plt.tight_layout()
    plt.savefig(VIS_DIR / 'fig6_meal_archetypes.png', dpi=150)
    plt.close()
    print("  fig6_meal_archetypes.png")


# ── Figure 7: Production Module Overview ─────────────────────────────────

def fig7_overview():
    """Visual summary of production modules and technique type."""
    fig, ax = plt.subplots(figsize=(12, 7))

    modules = [
        ('P1: Fidelity Grade', 'Analytical', 'RMSE+CE replaces ADA', '#3498db'),
        ('P2: 4-Harmonic Circadian', 'Analytical', 'R² 0.515→0.959', '#3498db'),
        ('P3: AID-Aware ISF', 'Analytical', 'Exp decay τ grid search', '#3498db'),
        ('P4: Alert Burst Dedup', 'ML (LR)', 'AUC=0.90, 93% dedup', '#e74c3c'),
        ('P5: Confidence Grade', 'Statistical', 'Bootstrap CI → A-D', '#f1c40f'),
        ('P6: Meal Archetypes', 'Analytical', 'Timing-weighted CR', '#3498db'),
    ]

    y_positions = np.arange(len(modules))[::-1]
    tech_colors = {'Analytical': '#3498db', 'ML (LR)': '#e74c3c', 'Statistical': '#f1c40f'}

    for i, (name, tech, detail, color) in enumerate(modules):
        y = y_positions[i]
        ax.barh(y, 1.0, 0.6, color=tech_colors[tech], alpha=0.8, edgecolor='white')
        ax.text(0.02, y, name, va='center', ha='left', fontweight='bold', fontsize=12, color='white')
        ax.text(1.05, y + 0.15, tech, va='center', ha='left', fontsize=10,
                color=tech_colors[tech], fontweight='bold')
        ax.text(1.05, y - 0.15, detail, va='center', ha='left', fontsize=9, color='#555')

    ax.set_xlim(-0.1, 2.5)
    ax.set_yticks([])
    ax.set_xticks([])
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['bottom'].set_visible(False)
    ax.spines['left'].set_visible(False)
    ax.set_title('Production Pipeline Modules — Technique Overview', fontsize=14, fontweight='bold')

    # Legend
    patches = [mpatches.Patch(color='#3498db', label='Analytical (5/6)'),
               mpatches.Patch(color='#e74c3c', label='ML — Logistic Regression (1/6)'),
               mpatches.Patch(color='#f1c40f', label='Statistical (1/6)')]
    ax.legend(handles=patches, loc='lower right', fontsize=10)

    plt.tight_layout()
    plt.savefig(VIS_DIR / 'fig7_module_overview.png', dpi=150)
    plt.close()
    print("  fig7_module_overview.png")


if __name__ == '__main__':
    VIS_DIR.mkdir(parents=True, exist_ok=True)
    print("Generating autoproductionize summary figures...")
    fig1_fidelity_vs_ada()
    fig2_harmonic_circadian()
    fig3_isf_aid()
    fig4_alerts()
    fig5_confidence()
    fig6_meals()
    fig7_overview()
    print(f"Done. Figures saved to {VIS_DIR}")
