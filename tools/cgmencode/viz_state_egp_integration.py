"""Visualizations for metabolic state & EGP integration using ACTUAL experiment data."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

EXP = Path("externals/experiments")
VIZ = Path("visualizations/state-and-egp-integration")
VIZ.mkdir(parents=True, exist_ok=True)


def load_json(filename: str):
    path = EXP / filename
    if not path.exists():
        print(f"WARNING: {filename} not found")
        return {}
    with open(path) as f:
        return json.load(f)


def viz_state_clustering():
    """Fig 1: State clustering analysis from EXP-2810."""
    data = load_json("exp-2810_state_clustering.json")
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle(f"EXP-2810: State Clustering (KMeans, k={data.get('best_k')})", 
                fontweight='bold', fontsize=13)
    
    # Panel 1: Silhouette scores by k
    if 'silhouette_by_k' in data:
        k_vals = sorted([int(k) for k in data['silhouette_by_k'].keys()])
        scores = [data['silhouette_by_k'][str(k)] for k in k_vals]
        ax1.plot(k_vals, scores, 'o-', linewidth=2, markersize=8, color='#3498db')
        ax1.axvline(x=data.get('best_k', 2), color='red', linestyle='--', alpha=0.7, label='Optimal')
        ax1.set_xlabel("Number of clusters (k)", fontsize=11)
        ax1.set_ylabel("Silhouette score", fontsize=11)
        ax1.set_title("Elbow plot", fontsize=11)
        ax1.grid(True, alpha=0.3)
        ax1.legend()
    
    # Panel 2: Metadata summary
    ax2.axis('off')
    summary_text = f"""
    Clustering Results
    ────────────────────
    Optimal k: {data.get('best_k')}
    Best silhouette: {data.get('best_silhouette'):.3f}
    
    Dataset
    ────────────────────
    Patients: {data.get('n_patients')}
    48h windows: {data.get('n_windows'):,}
    Window size: {data.get('window_hours')}h
    Step: {data.get('step_hours')}h
    """
    ax2.text(0.1, 0.5, summary_text, fontsize=10, verticalalignment='center',
            family='monospace', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.3))
    
    plt.tight_layout()
    plt.savefig(VIZ / "fig01_state_clustering.png", dpi=150, bbox_inches='tight')
    plt.close()
    print("✓ Generated fig01_state_clustering.png")


def viz_egp_audit():
    """Fig 2: EGP audit and reconciliation from EXP-2820."""
    data = load_json("exp-2820_egp_audit.json")
    
    fig, ax = plt.subplots(figsize=(10, 6))
    fig.suptitle("EXP-2820: Canonical EGP vs Reference", fontweight='bold', fontsize=13)
    
    canonical = data.get('canonical_egp_median_mg_dL_hr', 0)
    reference = data.get('uva_padova_ref_mg_dL_hr', 0)
    
    categories = ['AID-mediated\nEGP', 'UVA/Padova\nReference']
    values = [canonical, reference]
    colors = ['#3498db', '#95a5a6']
    
    bars = ax.bar(categories, values, color=colors, alpha=0.7, edgecolor='black', width=0.6)
    ax.set_ylabel("EGP (mg/dL/hr)", fontsize=11)
    ax.set_title("EGP: AID-Controlled vs Physiological Reference", fontsize=11)
    
    for i, (bar, v) in enumerate(zip(bars, values)):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height + 0.3,
               f'{v:.1f}', ha='center', va='bottom', fontweight='bold', fontsize=11)
    
    # Annotation
    if reference > 0 and canonical > 0:
        reduction = 100 * (1 - canonical/reference)
        ax.text(0.98, 0.97, f'AID reduces EGP\nby {reduction:.0f}%',
               transform=ax.transAxes, fontsize=10, verticalalignment='top',
               horizontalalignment='right', bbox=dict(boxstyle='round', 
               facecolor='lightblue', alpha=0.6))
    
    ax.set_ylim([0, max(values) * 1.2])
    plt.tight_layout()
    plt.savefig(VIZ / "fig02_egp_audit.png", dpi=150, bbox_inches='tight')
    plt.close()
    print("✓ Generated fig02_egp_audit.png")


def viz_transitions():
    """Fig 3: Transition matrices from EXP-2810."""
    data = load_json("exp-2810_state_clustering.json")
    
    fig, ax = plt.subplots(figsize=(8, 6))
    fig.suptitle("State Transitions (48h → next 48h)", fontweight='bold', fontsize=13)
    
    if 'transition_matrix' in data:
        trans = data['transition_matrix']
        trans_arr = np.array([[float(trans['0']['0']), float(trans['0']['1'])],
                              [float(trans['1']['0']), float(trans['1']['1'])]])
        
        im = ax.imshow(trans_arr, cmap='RdYlGn', vmin=0, vmax=1, aspect='auto')
        ax.set_xticks([0, 1])
        ax.set_yticks([0, 1])
        ax.set_xticklabels(['→ S0\n(well-ctrl)', '→ S1\n(mod/high)'], fontsize=10)
        ax.set_yticklabels(['S0\n(well-ctrl)', 'S1\n(mod/high)'], fontsize=10)
        ax.set_ylabel("Current state", fontsize=11)
        ax.set_xlabel("Next state", fontsize=11)
        
        for i in range(2):
            for j in range(2):
                ax.text(j, i, f'{trans_arr[i,j]:.1%}', ha="center", va="center",
                       color="black", fontweight='bold', fontsize=12)
        
        cbar = plt.colorbar(im, ax=ax, label="Persistence")
        cbar.set_label("Transition Probability", fontsize=10)
    
    plt.tight_layout()
    plt.savefig(VIZ / "fig03_transitions.png", dpi=150, bbox_inches='tight')
    plt.close()
    print("✓ Generated fig03_transitions.png")


def viz_isf_decoupling():
    """Fig 4: ISF decoupling by state from EXP-2811."""
    data = load_json("exp-2811_state_decoupling.json")
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle("EXP-2811: ISF↔Basal Coupling (State-Controlled)", fontweight='bold', fontsize=13)
    
    # Panel 1: Pooled vs within-state correlation
    pooled_rho = data.get('pooled_isf_basal_rho', 0)
    
    # Extract within-state correlations
    within_state = data.get('within_state_isf_basal_rho', {})
    s0_rho = within_state.get('0', {}).get('rho', 0) if isinstance(within_state.get('0'), dict) else 0
    s1_rho = within_state.get('1', {}).get('rho', 0) if isinstance(within_state.get('1'), dict) else 0
    
    methods = ['Pooled\n(biased)', 'State 0\n(well-ctrl)', 'State 1\n(mod/high)']
    correlations = [pooled_rho, s0_rho, s1_rho]
    colors = ['#e74c3c', '#2ecc71', '#2ecc71']  # Red for confounded, green for decoupled
    
    bars = ax1.bar(methods, correlations, color=colors, alpha=0.7, edgecolor='black')
    ax1.axhline(y=0, color='black', linestyle='-', linewidth=0.8)
    ax1.axhline(y=0.3, color='orange', linestyle=':', alpha=0.5, label='|ρ|=0.3 threshold')
    ax1.axhline(y=-0.3, color='orange', linestyle=':', alpha=0.5)
    ax1.set_ylabel("Correlation (ρ)", fontsize=11)
    ax1.set_title("ISF↔Basal Coupling: Before & After State Control", fontsize=11)
    ax1.set_ylim([-0.6, 0.6])
    ax1.legend()
    
    for bar, corr in zip(bars, correlations):
        height = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2., height + (0.02 if height > 0 else -0.05),
                f'{corr:.3f}', ha='center', va='bottom' if height > 0 else 'top', 
                fontweight='bold', fontsize=10)
    
    # Panel 2: Pass/fail criteria
    criteria = data.get('criteria', {})
    pass_count = data.get('n_pass', 0)
    
    ax2.axis('off')
    criteria_text = f"""
    Decoupling Criteria (Results)
    ─────────────────────────────────
    P1: ≥10 patients/state    {'✓' if criteria.get('P1_extraction_ge_10_patients_one_state') else '✗'}
    P2: Within-state decouples {'✓' if criteria.get('P2_within_state_decouples') else '✗'}
    P3: |ρ| < 0.3 in ≥1 state  {'✓' if criteria.get('P3_at_least_one_state_rho_lt_0.3') else '✗'}
    P4: ISF varies ≥5 patients {'✓' if criteria.get('P4_isf_varies_ge_5_patients') else '✗'}
    P5: Basal varies ≥5 patients {'✓' if criteria.get('P5_basal_varies_ge_5_patients') else '✗'}
    
    RESULT: {pass_count} / 5 criteria pass
    """
    ax2.text(0.05, 0.95, criteria_text, fontsize=9, verticalalignment='top',
            family='monospace', transform=ax2.transAxes,
            bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.5))
    
    plt.tight_layout()
    plt.savefig(VIZ / "fig04_isf_decoupling.png", dpi=150, bbox_inches='tight')
    plt.close()
    print("✓ Generated fig04_isf_decoupling.png")


if __name__ == "__main__":
    print("Generating state & EGP integration visualizations (using ACTUAL experiment data)...")
    viz_state_clustering()
    viz_egp_audit()
    viz_transitions()
    viz_isf_decoupling()
    print("✓ All visualizations generated with real data")
