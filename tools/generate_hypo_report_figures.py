#!/usr/bin/env python3
"""Generate visualizations for the hypoglycemia draft report.

Usage:
    python tools/generate_hypo_report_figures.py

Output:
    docs/60-research/figures/hypo-fig{1..6}-*.png
"""
import os
import sys

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import numpy as np
except ImportError:
    print("ERROR: matplotlib and numpy are required. Install with:")
    print("  pip install matplotlib numpy")
    sys.exit(1)

OUTDIR = os.path.join(os.path.dirname(__file__), "..", "docs", "60-research", "figures")
os.makedirs(OUTDIR, exist_ok=True)


def fig1_fundamental_asymmetry():
    """HIGH vs HYPO prediction AUC and forecast accuracy by glucose range."""
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Panel A: AUC comparison
    horizons = ['2-hour', '6-hour', 'Overnight']
    high_auc = [0.907, 0.796, 0.805]
    hypo_auc = [0.860, 0.668, 0.690]
    x = np.arange(len(horizons))
    w = 0.35
    bars1 = axes[0].bar(x - w/2, high_auc, w, label='HIGH (>180)', color='#e74c3c', alpha=0.8)
    bars2 = axes[0].bar(x + w/2, hypo_auc, w, label='HYPO (<70)', color='#3498db', alpha=0.8)
    axes[0].axhline(y=0.80, color='green', linestyle='--', linewidth=1.5, label='Clinical threshold (0.80)')
    axes[0].set_ylabel('AUC-ROC', fontsize=12)
    axes[0].set_title('A) Prediction AUC: HIGH vs HYPO', fontsize=13, fontweight='bold')
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(horizons, fontsize=11)
    axes[0].set_ylim(0.5, 1.0)
    axes[0].legend(fontsize=9)
    for bar in bars1 + bars2:
        axes[0].text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.01,
                     f'{bar.get_height():.3f}', ha='center', va='bottom', fontsize=9)

    # Panel B: MAE and R² by glucose range
    ranges = ['In-range\n(80-120)', 'Below 80', 'Below 70\n(hypo)']
    mae_vals = [21.5, 26.6, 39.8]
    r2_vals = [0.281, 0.153, 0.153]
    color_mae = '#e67e22'
    color_r2 = '#2ecc71'
    x2 = np.arange(len(ranges))
    axes[1].bar(x2 - 0.18, mae_vals, 0.35, label='MAE (mg/dL)', color=color_mae, alpha=0.8)
    ax2b = axes[1].twinx()
    ax2b.bar(x2 + 0.18, r2_vals, 0.35, label='R²', color=color_r2, alpha=0.8)
    axes[1].set_ylabel('MAE (mg/dL)', color=color_mae, fontsize=12)
    ax2b.set_ylabel('R²', color=color_r2, fontsize=12)
    axes[1].set_title('B) Forecast Accuracy by Glucose Range', fontsize=13, fontweight='bold')
    axes[1].set_xticks(x2)
    axes[1].set_xticklabels(ranges, fontsize=10)
    axes[1].set_ylim(0, 50)
    ax2b.set_ylim(0, 0.5)
    lines1, labels1 = axes[1].get_legend_handles_labels()
    lines2, labels2 = ax2b.get_legend_handles_labels()
    axes[1].legend(lines1 + lines2, labels1 + labels2, loc='upper left', fontsize=9)

    plt.tight_layout()
    path = os.path.join(OUTDIR, 'hypo-fig1-fundamental-asymmetry.png')
    plt.savefig(path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"✅ {path}")


def fig2_anatomy_of_event():
    """Six-phase anatomy of a hypoglycemic event with counter-regulatory response."""
    fig, ax = plt.subplots(figsize=(14, 6))

    np.random.seed(42)
    t_pre = np.arange(-120, 0, 5)
    g_pre = 130 - 0.5 * np.abs(t_pre) + np.random.normal(0, 2, len(t_pre))
    t_entry = np.arange(0, 30, 5)
    g_entry = 70 - 3.5 * np.arange(len(t_entry)) + np.random.normal(0, 1.5, len(t_entry))
    t_nadir = np.arange(30, 50, 5)
    g_nadir = np.array([52, 48, 46, 49]) + np.random.normal(0, 1, 4)
    t_recov = np.arange(50, 100, 5)
    g_recov = 49 + 4.5 * np.arange(len(t_recov)) + np.random.normal(0, 2, len(t_recov))
    t_rebound = np.arange(100, 200, 5)
    g_rebound = 94 + 6 * np.arange(len(t_rebound)) - 0.25 * np.arange(len(t_rebound))**2 \
        + np.random.normal(0, 3, len(t_rebound))
    g_rebound = np.clip(g_rebound, 80, 220)

    t_all = np.concatenate([t_pre, t_entry, t_nadir, t_recov, t_rebound])
    g_all = np.concatenate([g_pre, g_entry, g_nadir, g_recov, g_rebound])

    ax.plot(t_all, g_all, 'k-', linewidth=2, zorder=5)
    ax.axhline(y=70, color='red', linestyle='--', linewidth=1.5, alpha=0.7, label='Level 1 Hypo (70 mg/dL)')
    ax.axhline(y=54, color='darkred', linestyle='--', linewidth=1.5, alpha=0.7,
               label='Level 2 Hypo (54 mg/dL)')
    ax.axhline(y=180, color='orange', linestyle='--', linewidth=1, alpha=0.5,
               label='Hyperglycemia (180 mg/dL)')

    ax.axvspan(-120, -30, alpha=0.08, color='green', label='Phase 1: Pre-event decline')
    ax.axvspan(-30, 0, alpha=0.12, color='yellow', label='Phase 2: Approaching threshold')
    ax.axvspan(0, 30, alpha=0.12, color='orange', label='Phase 3: Entry & descent')
    ax.axvspan(30, 50, alpha=0.15, color='red', label='Phase 4: Nadir')
    ax.axvspan(50, 100, alpha=0.12, color='purple', label='Phase 5: Counter-regulatory recovery')
    ax.axvspan(100, 200, alpha=0.08, color='blue', label='Phase 6: Potential rebound')

    ax.annotate('AID suspends\ninsulin here', xy=(-20, 80), fontsize=9, ha='center',
                arrowprops=dict(arrowstyle='->', color='gray'), xytext=(-50, 105))
    ax.annotate('Glucagon\nreleased', xy=(35, 48), fontsize=9, ha='center', color='purple',
                arrowprops=dict(arrowstyle='->', color='purple'), xytext=(10, 30))
    ax.annotate('Counter-regulatory\novershoot', xy=(140, 180), fontsize=9, ha='center',
                color='blue',
                arrowprops=dict(arrowstyle='->', color='blue'), xytext=(160, 210))
    ax.annotate('Nadir\n(deepest point)', xy=(40, 46), fontsize=9, ha='center', color='darkred',
                arrowprops=dict(arrowstyle='->', color='darkred'), xytext=(65, 30))

    ax.set_xlabel('Time relative to threshold crossing (minutes)', fontsize=12)
    ax.set_ylabel('Glucose (mg/dL)', fontsize=12)
    ax.set_title('Anatomy of a Hypoglycemic Event: Phases & Counter-Regulatory Response',
                 fontsize=14, fontweight='bold')
    ax.set_ylim(20, 230)
    ax.legend(loc='upper right', fontsize=7.5, ncol=2)

    plt.tight_layout()
    path = os.path.join(OUTDIR, 'hypo-fig2-anatomy-of-event.png')
    plt.savefig(path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"✅ {path}")


def fig3_patient_risk_landscape():
    """TIR-TBR paradox scatter and recovery phenotype clustering."""
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))

    patients = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k']
    tir = [55.8, 56.7, 61.6, 79.2, 65.4, 65.5, 75.2, 85.0, 59.9, 81.0, 95.1]
    tbr = [2.96, 1.04, 4.70, 0.75, 1.77, 3.03, 3.24, 5.87, 10.68, 1.11, 4.87]
    episodes = [137, 64, 229, 51, 97, 145, 199, 127, 341, 34, 224]
    sizes = [e / 3 for e in episodes]

    colors_risk = []
    for t in tbr:
        if t < 2:
            colors_risk.append('#2ecc71')
        elif t < 4:
            colors_risk.append('#f39c12')
        elif t < 8:
            colors_risk.append('#e74c3c')
        else:
            colors_risk.append('#8e44ad')

    axes[0].scatter(tir, tbr, s=sizes, c=colors_risk, alpha=0.8,
                    edgecolors='black', linewidth=0.5, zorder=5)
    for i, p in enumerate(patients):
        axes[0].annotate(p, (tir[i], tbr[i]), fontsize=10, fontweight='bold',
                         xytext=(5, 5), textcoords='offset points')
    axes[0].axhline(y=4, color='red', linestyle='--', alpha=0.6, label='ADA TBR limit (4%)')
    axes[0].axvline(x=70, color='green', linestyle='--', alpha=0.6, label='ADA TIR target (70%)')
    axes[0].fill_between([70, 100], 0, 4, alpha=0.1, color='green', label='Target zone')
    axes[0].set_xlabel('Time in Range (%)', fontsize=12)
    axes[0].set_ylabel('Time Below Range (%)', fontsize=12)
    axes[0].set_title('A) The TIR-TBR Paradox', fontsize=13, fontweight='bold')
    axes[0].legend(fontsize=8)
    axes[0].set_xlim(45, 100)
    axes[0].set_ylim(0, 12)

    # Panel B: Recovery phenotypes
    carb_treated = [0.7, 60.9, 0.4, 15.0, 10.0, 2.0, 5.0, 28.0, 4.4, 58.8, 3.0]
    recovery_time = [20, 15, 15, 15, 15, 15, 15, 15, 25, 15, 15]
    phenotype_colors = ['#e74c3c' if ct < 20 else '#2ecc71' for ct in carb_treated]
    axes[1].scatter(carb_treated, recovery_time, s=[e / 2 for e in episodes],
                    c=phenotype_colors, alpha=0.8, edgecolors='black', linewidth=0.5, zorder=5)
    for i, p in enumerate(patients):
        axes[1].annotate(p, (carb_treated[i], recovery_time[i]), fontsize=10, fontweight='bold',
                         xytext=(5, 2), textcoords='offset points')
    axes[1].axvline(x=20, color='gray', linestyle=':', alpha=0.6)
    axes[1].set_xlabel('% Episodes Carb-Treated', fontsize=12)
    axes[1].set_ylabel('Median Recovery Time (min)', fontsize=12)
    axes[1].set_title('B) Two Recovery Phenotypes', fontsize=13, fontweight='bold')
    axes[1].annotate('Passive reliers\n(wait for AID suspend)', xy=(5, 22), fontsize=10,
                     color='#e74c3c', fontweight='bold')
    axes[1].annotate('Active treaters\n(eat carbs)', xy=(45, 14), fontsize=10,
                     color='#2ecc71', fontweight='bold')

    plt.tight_layout()
    path = os.path.join(OUTDIR, 'hypo-fig3-patient-risk-landscape.png')
    plt.savefig(path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"✅ {path}")


def fig4_observable_vs_unobservable():
    """Observable vs unobservable factors for hypo prediction."""
    fig, ax = plt.subplots(figsize=(12, 6))

    categories = [
        'CGM glucose\nhistory', 'Insulin on\nBoard (IOB)', 'Carbs on\nBoard (COB)',
        'Basal rate\ndeviations', 'Supply/demand\nflux balance',
        'Counter-reg\nhormones', 'Exercise\n& activity', 'Stress &\ncortisol',
        'Meal\ncomposition', 'Gastric\nemptying rate',
    ]
    observable = [1, 1, 1, 1, 1, 0, 0, 0, 0, 0]
    importance = [0.495, 0.15, 0.12, 0.07, 0.10, 0.30, 0.15, 0.10, 0.08, 0.05]
    colors_obs = ['#27ae60' if o else '#c0392b' for o in observable]

    ax.barh(range(len(categories)), importance, color=colors_obs, alpha=0.8,
            edgecolor='black', linewidth=0.5)
    ax.set_yticks(range(len(categories)))
    ax.set_yticklabels(categories, fontsize=10)
    ax.set_xlabel('Estimated Importance for Hypo Prediction', fontsize=12)
    ax.set_title('What We Can Measure vs What Matters for Hypoglycemia',
                 fontsize=14, fontweight='bold')
    ax.axvline(x=0, color='black', linewidth=0.5)

    observed_patch = mpatches.Patch(color='#27ae60', alpha=0.8, label='Observable (in our data)')
    unobserved_patch = mpatches.Patch(color='#c0392b', alpha=0.8,
                                      label='Unobservable (not in CGM/pump data)')
    ax.legend(handles=[observed_patch, unobserved_patch], fontsize=10, loc='lower right')
    ax.invert_yaxis()

    plt.tight_layout()
    path = os.path.join(OUTDIR, 'hypo-fig4-observable-vs-unobservable.png')
    plt.savefig(path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"✅ {path}")


def fig5_nocturnal_timing():
    """Nocturnal clustering of hypoglycemic events."""
    fig, ax = plt.subplots(figsize=(10, 5))
    hours = list(range(24))
    # Distribution based on report data (peak at 0-3 AM)
    hypo_density = [0.12, 0.14, 0.11, 0.09, 0.06, 0.05, 0.03, 0.02, 0.02, 0.02,
                    0.02, 0.03, 0.04, 0.03, 0.03, 0.03, 0.02, 0.03, 0.03, 0.03,
                    0.02, 0.03, 0.05, 0.08]
    colors_hour = ['#2c3e50' if 22 <= h or h <= 6 else '#bdc3c7' for h in hours]
    ax.bar(hours, hypo_density, color=colors_hour, alpha=0.8, edgecolor='black', linewidth=0.3)
    ax.axvspan(22, 24, alpha=0.1, color='navy')
    ax.axvspan(0, 6, alpha=0.1, color='navy', label='Nocturnal window')
    ax.set_xlabel('Hour of Day', fontsize=12)
    ax.set_ylabel('Relative Hypo Frequency', fontsize=12)
    ax.set_title('Hypoglycemic Event Timing: Nocturnal Clustering', fontsize=13, fontweight='bold')
    ax.set_xticks(hours)
    ax.set_xticklabels([f'{h:02d}' for h in hours], fontsize=8)
    ax.annotate('Peak onset: 0:00-3:00 AM\n(post-dinner insulin tail)', xy=(1.5, 0.13),
                fontsize=10, ha='center', color='navy', fontweight='bold',
                arrowprops=dict(arrowstyle='->', color='navy'), xytext=(8, 0.15))
    ax.legend(fontsize=10)

    plt.tight_layout()
    path = os.path.join(OUTDIR, 'hypo-fig5-nocturnal-timing.png')
    plt.savefig(path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"✅ {path}")


def fig6_prediction_ceiling():
    """Nine approaches all converging at the same AUC ceiling."""
    fig, ax = plt.subplots(figsize=(10, 5))
    approaches = [
        'Baseline\n(no physics)', 'Physics\nfeatures', 'Focal\nloss', 'Near-hypo\nthreshold',
        'Glucose\nderivatives', 'CNN\narchitecture', 'Extended\ncontext (6h)',
        'Transformer', 'PK channel\nfeatures',
    ]
    aucs = [0.520, 0.696, 0.698, 0.702, 0.699, 0.690, 0.688, 0.692, 0.683]
    colors_bar = ['#95a5a6'] + ['#27ae60'] + ['#e74c3c'] * 7
    ax.bar(range(len(approaches)), aucs, color=colors_bar, alpha=0.8,
           edgecolor='black', linewidth=0.5)
    ax.axhline(y=0.69, color='red', linestyle='--', linewidth=1.5, alpha=0.7, label='Ceiling ≈ 0.69')
    ax.axhline(y=0.80, color='green', linestyle='--', linewidth=1.5, alpha=0.7,
               label='Clinical threshold (0.80)')
    ax.set_ylabel('Overnight HYPO AUC', fontsize=12)
    ax.set_title('The Robust Prediction Ceiling: 9 Approaches, Same Result',
                 fontsize=13, fontweight='bold')
    ax.set_xticks(range(len(approaches)))
    ax.set_xticklabels(approaches, fontsize=8)
    ax.set_ylim(0.4, 0.9)
    ax.legend(fontsize=10)
    for i, v in enumerate(aucs):
        ax.text(i, v + 0.01, f'{v:.3f}', ha='center', fontsize=8)

    plt.tight_layout()
    path = os.path.join(OUTDIR, 'hypo-fig6-prediction-ceiling.png')
    plt.savefig(path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"✅ {path}")


if __name__ == '__main__':
    fig1_fundamental_asymmetry()
    fig2_anatomy_of_event()
    fig3_patient_risk_landscape()
    fig4_observable_vs_unobservable()
    fig5_nocturnal_timing()
    fig6_prediction_ceiling()
    print(f"\n🎉 All 6 figures generated in {OUTDIR}")
