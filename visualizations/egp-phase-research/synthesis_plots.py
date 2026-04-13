#!/usr/bin/env python3
"""Synthesis visualizations: Supply/Demand Asymmetry in Diabetes Data.

Comprehensive figures showing the fundamental asymmetry between insulin
demand and EGP supply, with practical implications for AID controllers
and settings recommendations.
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

RESULTS_DIR = Path("externals/experiments")
VIZ_DIR = Path("visualizations/egp-phase-research")
VIZ_DIR.mkdir(parents=True, exist_ok=True)


def load_all():
    results = {}
    for name in ["exp-2624_correction_egp_recovery",
                 "exp-2625_egp_aware_settings",
                 "exp-2626_asymmetry_synthesis"]:
        with open(RESULTS_DIR / f"{name}.json") as f:
            results[name] = json.load(f)
    return results


def fig10_three_phase_correction(r26):
    """The three-phase correction model: demand → transition → recovery."""
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    # Panel 1: Idealized correction timeline with phases
    ax = axes[0]
    t = np.linspace(0, 6, 300)

    # Simulated glucose trajectory after correction bolus
    # Phase 1: Demand (0-2h) — fast drop driven by insulin
    # Phase 2: Transition (2-3.5h) — EGP suppressed, insulin waning
    # Phase 3: Recovery (3.5-6h) — EGP reasserting
    pre_bg = 250
    nadir_bg = 130
    recovery_rate = 17  # mg/dL/hr

    glucose = np.zeros_like(t)
    for i, ti in enumerate(t):
        if ti <= 2.0:
            # Demand phase: ~46% of drop
            frac = ti / 2.0
            glucose[i] = pre_bg - (pre_bg - nadir_bg) * 0.46 * frac
        elif ti <= 3.5:
            # Transition phase: remaining 54% of drop
            bg_at_2h = pre_bg - (pre_bg - nadir_bg) * 0.46
            frac = (ti - 2.0) / 1.5
            glucose[i] = bg_at_2h - (bg_at_2h - nadir_bg) * frac
        else:
            # Recovery phase: EGP reasserts
            glucose[i] = nadir_bg + recovery_rate * (ti - 3.5)

    ax.plot(t, glucose, 'k-', linewidth=2.5, zorder=5)

    # Phase shading
    ax.axvspan(0, 2.0, alpha=0.15, color='#e74c3c', label='Phase 1: Demand')
    ax.axvspan(2.0, 3.5, alpha=0.15, color='#f39c12', label='Phase 2: EGP Suppressed')
    ax.axvspan(3.5, 6.0, alpha=0.15, color='#27ae60', label='Phase 3: EGP Recovery')

    # Annotations
    ax.axhline(y=nadir_bg, color='gray', linestyle=':', alpha=0.5)
    ax.axvline(x=1.25, color='#e74c3c', linestyle='--', alpha=0.6, linewidth=1.5)
    ax.axvline(x=3.5, color='#f39c12', linestyle='--', alpha=0.6, linewidth=1.5)

    ax.annotate('Insulin Peak\n(1.25h)', xy=(1.25, 220), fontsize=8,
                ha='center', color='#e74c3c', fontweight='bold')
    ax.annotate('Glucose Nadir\n(3.5h)', xy=(3.5, nadir_bg - 8),
                fontsize=8, ha='center', color='#f39c12', fontweight='bold')
    ax.annotate(f'EGP Recovery\n+{recovery_rate} mg/dL/hr',
                xy=(4.5, nadir_bg + 20), fontsize=8, ha='center',
                color='#27ae60', fontweight='bold')

    # What controllers predict (wrong)
    controller_glucose = np.zeros_like(t)
    for i, ti in enumerate(t):
        if ti <= 1.5:
            controller_glucose[i] = pre_bg - (pre_bg - nadir_bg) * (ti / 1.5) * 0.7
        elif ti <= 3.0:
            controller_glucose[i] = pre_bg - (pre_bg - nadir_bg) * 0.7 - \
                (pre_bg - nadir_bg) * 0.3 * ((ti - 1.5) / 1.5)
        else:
            controller_glucose[i] = nadir_bg  # Controllers expect flat
    ax.plot(t, controller_glucose, 'r:', linewidth=1.5, alpha=0.6,
            label='Controller prediction (no EGP)')

    ax.annotate('2.25h\nphase lag', xy=(2.375, 185), fontsize=9,
                ha='center', fontweight='bold', color='#8e44ad',
                bbox=dict(boxstyle='round', facecolor='#f0e6ff', alpha=0.8))

    ax.set_xlabel('Time After Correction Bolus (hours)', fontsize=11)
    ax.set_ylabel('Glucose (mg/dL)', fontsize=11)
    ax.set_title('Three-Phase Correction Model', fontsize=12)
    ax.legend(loc='upper right', fontsize=8)
    ax.set_xlim(0, 6)
    ax.set_ylim(100, 270)
    ax.grid(alpha=0.2)

    # Panel 2: Phase contribution bar chart
    ax = axes[1]
    # Population data from EXP-2626
    pop = r26.get("population_asymmetry", {})
    med_demand = pop.get("demand_rate_median", 24)
    med_supply = pop.get("supply_rate_median", 17)
    egp_frac = pop.get("egp_suppression_frac_median", 0.54)

    categories = ['Demand\nPhase\n(0-2h)', 'EGP\nSuppressed\n(2h-nadir)', 'Recovery\n(post-nadir)']
    values = [med_demand, (med_demand + med_supply) / 2, med_supply]
    colors = ['#e74c3c', '#f39c12', '#27ae60']

    bars = ax.bar(range(3), values, color=colors, edgecolor='k', linewidth=0.8)

    ax.set_ylabel('Rate (mg/dL/hr)', fontsize=11)
    ax.set_title('Phase Rates (Population Median)', fontsize=12)
    ax.set_xticks(range(3))
    ax.set_xticklabels(categories, fontsize=9)
    ax.grid(axis='y', alpha=0.3)

    # Annotate with key stats
    ax.annotate(f'Demand: {med_demand:.0f}\nmg/dL/hr',
                xy=(0, med_demand + 1), ha='center', fontsize=8, fontweight='bold')
    ax.annotate(f'Recovery: {med_supply:.0f}\nmg/dL/hr',
                xy=(2, med_supply + 1), ha='center', fontsize=8, fontweight='bold')

    # Inset: pie chart of drop contribution
    ax_inset = ax.inset_axes([0.55, 0.55, 0.4, 0.4])
    ax_inset.pie([1 - egp_frac, egp_frac],
                 labels=[f'Demand\n{(1-egp_frac)*100:.0f}%',
                         f'EGP Supp.\n{egp_frac*100:.0f}%'],
                 colors=['#e74c3c', '#f39c12'], textprops={'fontsize': 7},
                 startangle=90, wedgeprops={'edgecolor': 'k', 'linewidth': 0.5})
    ax_inset.set_title('Drop Attribution', fontsize=8)

    fig.suptitle('Supply/Demand Asymmetry in Glucose Corrections', fontsize=14)
    fig.tight_layout()
    fig.savefig(VIZ_DIR / "fig10_three_phase_correction.png", dpi=150)
    plt.close(fig)
    print("  Saved fig10_three_phase_correction.png")


def fig11_isf_decomposition(r26):
    """Per-patient ISF: scheduled vs apparent vs demand-phase vs EGP-corrected."""
    recs = r26.get("recommendations", [])
    if not recs:
        return

    fig, ax = plt.subplots(1, 1, figsize=(12, 6))

    pids = [r["patient"] for r in recs]
    n = len(pids)
    x = np.arange(n)
    w = 0.2

    scheduled = [r["scheduled"]["isf"] for r in recs]
    apparent = [r["recommendations"]["isf"]["apparent_isf_from_corrections"] for r in recs]
    corrected = [r["recommendations"]["isf"].get("egp_corrected_isf", r["scheduled"]["isf"])
                 for r in recs]
    demand_phase = [r["asymmetry"].get("demand_phase_isf") or r["scheduled"]["isf"]
                    for r in recs]

    ax.bar(x - 1.5 * w, scheduled, w, label='Scheduled ISF', color='#95a5a6',
           edgecolor='k', linewidth=0.5)
    ax.bar(x - 0.5 * w, apparent, w, label='Apparent (from corrections)',
           color='#e74c3c', edgecolor='k', linewidth=0.5)
    ax.bar(x + 0.5 * w, corrected, w, label='EGP-Corrected ISF',
           color='#3498db', edgecolor='k', linewidth=0.5)
    ax.bar(x + 1.5 * w, demand_phase, w, label='Demand-Phase ISF (0-2h)',
           color='#f39c12', edgecolor='k', linewidth=0.5)

    ax.set_xlabel('Patient', fontsize=11)
    ax.set_ylabel('ISF (mg/dL per Unit)', fontsize=11)
    ax.set_title('ISF Decomposition: Why One Number Is Not Enough', fontsize=13)
    ax.set_xticks(x)
    ax.set_xticklabels(pids, fontsize=11)
    ax.legend(fontsize=8, loc='upper right')
    ax.grid(axis='y', alpha=0.3)

    # Annotate inflation %
    for i, r in enumerate(recs):
        infl = r["recommendations"]["isf"].get("inflation_pct")
        if infl is not None and abs(infl) >= 15:
            y_max = max(scheduled[i], apparent[i], corrected[i], demand_phase[i])
            ax.annotate(f'+{infl:.0f}%\ninflation',
                        xy=(i, y_max + 3), ha='center', fontsize=7,
                        color='red', fontweight='bold')

    fig.tight_layout()
    fig.savefig(VIZ_DIR / "fig11_isf_decomposition.png", dpi=150)
    plt.close(fig)
    print("  Saved fig11_isf_decomposition.png")


def fig12_settings_recommendations(r26):
    """Concrete per-patient settings recommendations with TIR context."""
    recs = r26.get("recommendations", [])
    if not recs:
        return

    fig, axes = plt.subplots(1, 3, figsize=(16, 5))

    pids = [r["patient"] for r in recs]
    n = len(pids)
    x = np.arange(n)

    # Panel 1: Basal current vs recommended
    ax = axes[0]
    current = [r["scheduled"]["basal"] for r in recs]
    suggested = [r["recommendations"]["basal"]["suggested_basal"] for r in recs]
    w = 0.35
    ax.bar(x - w / 2, current, w, label='Current', color='#95a5a6', edgecolor='k')
    ax.bar(x + w / 2, suggested, w, label='EGP-Adjusted', color='#3498db', edgecolor='k')
    ax.set_ylabel('Basal Rate (U/hr)')
    ax.set_title('Basal Rate: Current vs EGP-Adjusted')
    ax.set_xticks(x)
    ax.set_xticklabels(pids)
    ax.legend(fontsize=8)
    ax.grid(axis='y', alpha=0.3)
    for i, r in enumerate(recs):
        direction = r["recommendations"]["basal"]["direction"]
        marker = '↑' if 'increase' in direction else '→' if direction == 'maintain' else '↓'
        ax.annotate(marker, xy=(i + w / 2, suggested[i] + 0.03),
                    ha='center', fontsize=12, fontweight='bold',
                    color='red' if '↑' in marker else 'green')

    # Panel 2: TIR with TAR/TBR breakdown
    ax = axes[1]
    tir = [r["outcomes"]["tir"] for r in recs]
    tar = [r["outcomes"]["tar"] for r in recs]
    tbr = [r["outcomes"]["tbr"] for r in recs]

    ax.bar(x, tbr, label='<70 (TBR)', color='#e74c3c', edgecolor='k', linewidth=0.5)
    ax.bar(x, tir, bottom=tbr, label='70-180 (TIR)', color='#27ae60',
           edgecolor='k', linewidth=0.5)
    ax.bar(x, tar, bottom=[t + r for t, r in zip(tbr, tir)], label='>180 (TAR)',
           color='#f39c12', edgecolor='k', linewidth=0.5)
    ax.axhline(y=70, color='green', linestyle='--', alpha=0.3)
    ax.set_ylabel('Time (%)')
    ax.set_title('Current Glycemic Outcomes')
    ax.set_xticks(x)
    ax.set_xticklabels(pids)
    ax.legend(fontsize=7)
    ax.set_ylim(0, 105)
    ax.grid(axis='y', alpha=0.2)
    for i in range(n):
        ax.annotate(f'{tir[i]:.0f}%', xy=(i, tbr[i] + tir[i] / 2),
                    ha='center', va='center', fontsize=8, fontweight='bold', color='white')

    # Panel 3: Recovery slope → EGP assessment
    ax = axes[2]
    recovery = [r["egp"]["recovery_slope"] for r in recs]
    colors_r = ['#e74c3c' if rv > 20 else '#27ae60' if rv < 10 else '#f39c12'
                for rv in recovery]
    bars = ax.barh(x, recovery, color=colors_r, edgecolor='k', linewidth=0.5)
    ax.axvline(x=18, color='blue', linestyle=':', alpha=0.5, label='Base EGP (18)')
    ax.axvline(x=0, color='k', linewidth=0.5)
    ax.set_xlabel('Recovery Slope (mg/dL/hr)')
    ax.set_title('EGP Recovery Rate')
    ax.set_yticks(x)
    ax.set_yticklabels(pids)
    ax.legend(fontsize=8)
    ax.grid(axis='x', alpha=0.3)
    for i, r in enumerate(recs):
        assess = r["recommendations"]["basal"]["direction"]
        label = {'increase': 'Basal↑', 'slight_increase': 'Basal↑?',
                 'maintain': 'OK', 'decrease': 'Basal↓'}.get(assess, '?')
        ax.annotate(label, xy=(recovery[i] + 1, i), va='center', fontsize=8,
                    fontweight='bold', color='red' if '↑' in label else 'green')

    fig.suptitle('EXP-2626: Per-Patient Settings Impact from EGP Analysis', fontsize=14)
    fig.tight_layout()
    fig.savefig(VIZ_DIR / "fig12_settings_recommendations.png", dpi=150)
    plt.close(fig)
    print("  Saved fig12_settings_recommendations.png")


def fig13_controller_error(r24):
    """Show where AID controllers get it wrong: prediction vs reality."""
    events = r24.get("pooled_events", [])
    if not events:
        return

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    nadir_hrs = [e["nadir_hours"] for e in events]
    drops = [e["drop_mgdl"] for e in events]
    recovery = [e["recovery_slope_mgdl_hr"] for e in events]

    # Panel 1: Nadir timing distribution with controller assumption
    ax = axes[0]
    ax.hist(nadir_hrs, bins=20, color='#3498db', edgecolor='k', alpha=0.7,
            density=True, label='Observed nadir timing')

    # Controller assumption: insulin peak ≈ 1.25h, expected nadir ~2h
    ax.axvline(x=1.25, color='red', linewidth=2, linestyle='--',
               label='Insulin PK peak (1.25h)')
    ax.axvline(x=np.median(nadir_hrs), color='#27ae60', linewidth=2,
               linestyle='-', label=f'Actual median nadir ({np.median(nadir_hrs):.1f}h)')

    # Shade the "error zone" — where controllers are wrong
    ax.axvspan(1.25, np.median(nadir_hrs), alpha=0.15, color='red')
    ax.annotate('Controller\nblind spot\n(2.25h)',
                xy=((1.25 + np.median(nadir_hrs)) / 2, ax.get_ylim()[1] * 0.7),
                ha='center', fontsize=9, fontweight='bold', color='#e74c3c',
                bbox=dict(boxstyle='round', facecolor='#ffe6e6', alpha=0.8))

    ax.set_xlabel('Time to Glucose Nadir (hours)', fontsize=11)
    ax.set_ylabel('Density', fontsize=11)
    ax.set_title('When Does Glucose Actually Bottom Out?', fontsize=12)
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)

    # Panel 2: Recovery slope distribution — the "rebound" that isn't
    ax = axes[1]
    pos = [r for r in recovery if r > 0]
    neg = [r for r in recovery if r <= 0]

    ax.hist(pos, bins=20, color='#27ae60', edgecolor='k', alpha=0.7,
            label=f'EGP recovery ({len(pos)/len(recovery):.0%})')
    if neg:
        ax.hist(neg, bins=10, color='#e74c3c', edgecolor='k', alpha=0.7,
                label=f'Continued drop ({len(neg)/len(recovery):.0%})')

    ax.axvline(x=18, color='blue', linestyle=':', linewidth=1.5,
               label='Base EGP rate (18 mg/dL/hr)')
    ax.axvline(x=np.median(recovery), color='#27ae60', linestyle='-',
               linewidth=2, label=f'Median ({np.median(recovery):.0f} mg/dL/hr)')

    ax.set_xlabel('Post-Nadir Recovery Rate (mg/dL/hr)', fontsize=11)
    ax.set_ylabel('Count', fontsize=11)
    ax.set_title('"Rebounds" Are EGP Recovery', fontsize=12)
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)

    fig.suptitle('What AID Controllers Miss: The EGP Phase Lag', fontsize=14)
    fig.tight_layout()
    fig.savefig(VIZ_DIR / "fig13_controller_error.png", dpi=150)
    plt.close(fig)
    print("  Saved fig13_controller_error.png")


if __name__ == "__main__":
    print("Generating synthesis visualizations...")
    r = load_all()
    fig10_three_phase_correction(r["exp-2626_asymmetry_synthesis"])
    fig11_isf_decomposition(r["exp-2626_asymmetry_synthesis"])
    fig12_settings_recommendations(r["exp-2626_asymmetry_synthesis"])
    fig13_controller_error(r["exp-2624_correction_egp_recovery"])
    print("Done.")
