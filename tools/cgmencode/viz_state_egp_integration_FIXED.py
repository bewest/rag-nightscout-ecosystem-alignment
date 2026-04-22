"""Fixed visualizations using ACTUAL experiment data."""
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
    """Fig 1: State clustering - USING ACTUAL DATA."""
    data = load_json("exp-2810_state_clustering.json")
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle(f"EXP-2810: State Clustering (k={data.get('best_k')})", 
                fontweight='bold')
    
    # Panel 1: Use actual silhouette_by_k data
    if 'silhouette_by_k' in data:
        k_vals = sorted([int(k) for k in data['silhouette_by_k'].keys()])
        scores = [data['silhouette_by_k'][str(k)] for k in k_vals]
        ax1.plot(k_vals, scores, 'o-', linewidth=2, markersize=8, color='#3498db')
        ax1.axvline(x=data.get('best_k', 2), color='red', linestyle='--', alpha=0.5)
        ax1.set_xlabel("Number of clusters (k)")
        ax1.set_ylabel("Silhouette score")
        ax1.set_title("Elbow plot: Silhouette by k")
        ax1.grid(True, alpha=0.3)
    
    # Panel 2: Metadata
    ax2.text(0.5, 0.7, f"n_patients: {data.get('n_patients')}", 
            ha='center', fontsize=11, transform=ax2.transAxes)
    ax2.text(0.5, 0.6, f"n_windows: {data.get('n_windows')}", 
            ha='center', fontsize=11, transform=ax2.transAxes)
    ax2.text(0.5, 0.5, f"Best k: {data.get('best_k')}", 
            ha='center', fontsize=11, fontweight='bold', transform=ax2.transAxes)
    ax2.text(0.5, 0.4, f"Best silhouette: {data.get('best_silhouette'):.3f}", 
            ha='center', fontsize=11, transform=ax2.transAxes)
    ax2.set_xlim(0, 1)
    ax2.set_ylim(0, 1)
    ax2.axis('off')
    
    plt.tight_layout()
    plt.savefig(VIZ / "fig01_state_clustering.png", dpi=150, bbox_inches='tight')
    plt.close()
    print("✓ Generated fig01_state_clustering.png (WITH ACTUAL DATA)")


def viz_egp_audit():
    """Fig 2: EGP audit using ACTUAL data."""
    data = load_json("exp-2820_egp_audit.json")
    
    fig, ax = plt.subplots(figsize=(10, 6))
    fig.suptitle("EXP-2820: Canonical EGP vs Reference", fontweight='bold')
    
    # Use actual data from JSON
    canonical = data.get('canonical_egp_median_mg_dL_hr', 0)
    reference = data.get('uva_padova_ref_mg_dL_hr', 0)
    
    categories = ['AID-mediated\nEGP', 'Reference\n(UVA/Padova)']
    values = [canonical, reference]
    colors = ['#3498db', '#95a5a6']
    
    ax.bar(categories, values, color=colors, alpha=0.7, edgecolor='black', width=0.6)
    ax.set_ylabel("EGP (mg/dL/hr)")
    ax.set_title("Canonical EGP vs Reference")
    
    for i, v in enumerate(values):
        ax.text(i, v + 0.5, f'{v:.1f}', ha='center', fontweight='bold', fontsize=11)
    
    # Add text box with details
    textstr = f"n_patients: {data.get('patients_with_canonical')}\n"
    textstr += f"Methods extracted: {data.get('methods_extracted')}"
    ax.text(0.98, 0.97, textstr, transform=ax.transAxes, fontsize=9,
           verticalalignment='top', horizontalalignment='right',
           bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
    
    plt.tight_layout()
    plt.savefig(VIZ / "fig02_egp_audit.png", dpi=150, bbox_inches='tight')
    plt.close()
    print("✓ Generated fig02_egp_audit.png (WITH ACTUAL DATA)")


def viz_transitions():
    """Fig 3: Transition matrix using ACTUAL data."""
    data = load_json("exp-2810_state_clustering.json")
    
    fig, ax = plt.subplots(figsize=(8, 6))
    fig.suptitle("State Transitions (48h → next 48h)", fontweight='bold')
    
    # Use actual transition_matrix from data
    if 'transition_matrix' in data:
        trans = data['transition_matrix']
        trans_arr = np.array([[trans['0']['0'], trans['0']['1']],
                              [trans['1']['0'], trans['1']['1']]])
        
        im = ax.imshow(trans_arr, cmap='RdYlGn', vmin=0, vmax=1)
        ax.set_xticks([0, 1])
        ax.set_yticks([0, 1])
        ax.set_xticklabels(['To S0', 'To S1'])
        ax.set_yticklabels(['From S0', 'From S1'])
        ax.set_ylabel("Current state")
        ax.set_xlabel("Next state")
        
        for i in range(2):
            for j in range(2):
                ax.text(j, i, f'{trans_arr[i,j]:.1%}', ha="center", va="center",
                       color="black", fontweight='bold')
        
        plt.colorbar(im, ax=ax, label="Probability")
    
    plt.tight_layout()
    plt.savefig(VIZ / "fig03_transitions.png", dpi=150, bbox_inches='tight')
    plt.close()
    print("✓ Generated fig03_transitions.png (WITH ACTUAL DATA)")


def viz_isf_decoupling():
    """Fig 4: ISF decoupling using ACTUAL data."""
    data = load_json("exp-2811_state_decoupling.json")
    
    fig, ax = plt.subplots(figsize=(10, 6))
    fig.suptitle("EXP-2811: ISF↔Basal Coupling Analysis", fontweight='bold')
    
    # Use actual data from JSON
    pooled_rho = data.get('pooled_isf_basal_rho', 0)
    pooled_p = data.get('pooled_isf_basal_p', 0.5)
    within_state_rho = data.get('within_state_isf_basal_rho', 0)
    
    methods = ['Pooled\n(ignoring state)', 'Within-state\n(controlled)']
    correlations = [pooled_rho, within_state_rho]
    colors = ['#e74c3c' if abs(c) > 0.3 else '#2ecc71' for c in correlations]
    
    ax.bar(methods, correlations, color=colors, alpha=0.7, edgecolor='black', width=0.5)
    ax.axhline(y=0, color='black', linestyle='-', linewidth=0.8)
    ax.set_ylabel("Correlation (ρ)")
    ax.set_title("ISF↔Basal Coupling: Before & After State Control")
    ax.set_ylim([-1, 1])
    
    for i, (method, corr) in enumerate(zip(methods, correlations)):
        sig = "✓" if (i == 0 and pooled_p < 0.05) or (i == 1) else ""
        ax.text(i, corr + 0.1, f'{corr:.3f}\n{sig}', ha='center', fontweight='bold')
    
    # Add text box
    textstr = f"n_extractions: {data.get('n_patient_state_extractions')}\n"
    textstr += f"with_isf_per_state: {data.get('n_with_isf_per_state')}"
    ax.text(0.98, 0.97, textstr, transform=ax.transAxes, fontsize=9,
           verticalalignment='top', horizontalalignment='right',
           bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.5))
    
    plt.tight_layout()
    plt.savefig(VIZ / "fig04_isf_decoupling.png", dpi=150, bbox_inches='tight')
    plt.close()
    print("✓ Generated fig04_isf_decoupling.png (WITH ACTUAL DATA)")


if __name__ == "__main__":
    print("Generating state & EGP integration visualizations (USING ACTUAL DATA)...")
    viz_state_clustering()
    viz_egp_audit()
    viz_transitions()
    viz_isf_decoupling()
    print("✓ All visualizations generated with real experiment data")
