"""Visualizations for metabolic state & EGP integration (EXP-2810, 2811, 2820, 2821).

Generates 4-panel dashboard for state-and-egp-integration-report-2026-04-22.md:
1. State clustering analysis
2. EGP audit and reconciliation  
3. Transition matrices and persistence
4. ISF decoupling by state

Output: visualizations/state-and-egp-integration/fig{01-04}_*.png
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd

EXP = Path("externals/experiments")
VIZ = Path("visualizations/state-and-egp-integration")
VIZ.mkdir(parents=True, exist_ok=True)


def load_json(filename: str):
    """Load experiment JSON data."""
    path = EXP / filename
    if not path.exists():
        print(f"WARNING: {filename} not found at {path}")
        return {}
    with open(path) as f:
        return json.load(f)


def viz_state_clustering():
    """Fig 1: State clustering analysis."""
    data = load_json("exp-2810_state_clustering.json")
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle("EXP-2810: State Clustering (KMeans, k=2)", fontsize=14, fontweight='bold')
    
    # Panel 1: State distribution
    if 'summary' in data:
        states = data['summary'].get('state_distribution', {})
        state_names = ['WELL_CONTROLLED', 'MODERATE/HIGH']
        counts = [states.get('0', 0), states.get('1', 0)]
        colors = ['#2ecc71', '#e74c3c']
        ax1.bar(state_names, counts, color=colors, alpha=0.7, edgecolor='black')
        ax1.set_ylabel("Number of 48h windows")
        ax1.set_title("State Distribution (n=3,981 windows, 28 patients)")
        for i, (name, count) in enumerate(zip(state_names, counts)):
            ax1.text(i, count + 50, f"{count}\n({count/sum(counts)*100:.1f}%)", 
                    ha='center', fontweight='bold')
    
    # Panel 2: Silhouette score
    if 'silhouette_scores' in data:
        k_values = sorted(data['silhouette_scores'].keys(), key=lambda x: int(x))
        scores = [data['silhouette_scores'][k] for k in k_values]
        ax2.plot(k_values, scores, 'o-', linewidth=2, markersize=8, color='#3498db')
        ax2.axvline(x=2, color='red', linestyle='--', alpha=0.5, label='Optimal k=2')
        ax2.set_xlabel("Number of clusters (k)")
        ax2.set_ylabel("Silhouette score")
        ax2.set_title("Clustering quality across k")
        ax2.grid(True, alpha=0.3)
        ax2.legend()
    
    plt.tight_layout()
    plt.savefig(VIZ / "fig01_state_clustering.png", dpi=150, bbox_inches='tight')
    plt.close()
    print(f"✓ Generated fig01_state_clustering.png")


def viz_egp_audit():
    """Fig 2: EGP audit and reconciliation."""
    data = load_json("exp-2820_egp_audit.json")
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle("EXP-2820: Canonical EGP Audit", fontsize=14, fontweight='bold')
    
    # Panel 1: EGP distribution
    if 'per_patient' in data:
        patients = list(data['per_patient'].keys())[:11]  # 11 orig patients
        egp_vals = []
        for p in patients:
            if p in data['per_patient']:
                egp = data['per_patient'][p].get('median_egp_mg_dl_min', 0)
                egp_vals.append(egp)
        
        if egp_vals:
            ax1.hist(egp_vals, bins=8, color='#9b59b6', alpha=0.7, edgecolor='black')
            ax1.axvline(np.median(egp_vals), color='red', linestyle='--', 
                       linewidth=2, label=f"Median: {np.median(egp_vals):.2f}")
            ax1.set_xlabel("Median EGP (mg/dL/min)")
            ax1.set_ylabel("Number of patients")
            ax1.set_title(f"EGP Distribution (n={len(patients)} patients)")
            ax1.legend()
    
    # Panel 2: EGP vs reference
    if 'summary' in data:
        refs = ['canonical_median_mg_dl_min', 'uva_padova_reference_mg_dl_min']
        ref_vals = []
        ref_labels = ['AID-mediated\nEGP', 'Reference\n(UVA/Padova)']
        for ref in refs:
            val = data['summary'].get(ref, 0)
            ref_vals.append(val)
        
        if ref_vals and any(ref_vals):
            colors_ref = ['#3498db', '#95a5a6']
            ax2.bar(ref_labels, ref_vals, color=colors_ref, alpha=0.7, edgecolor='black')
            ax2.set_ylabel("EGP (mg/dL/hr)")
            ax2.set_title("EGP: AID-Controlled vs Reference")
            for i, val in enumerate(ref_vals):
                ax2.text(i, val + 0.5, f"{val:.1f}", ha='center', fontweight='bold')
    
    plt.tight_layout()
    plt.savefig(VIZ / "fig02_egp_audit.png", dpi=150, bbox_inches='tight')
    plt.close()
    print(f"✓ Generated fig02_egp_audit.png")


def viz_transitions():
    """Fig 3: Transition matrices and persistence."""
    data = load_json("exp-2812_state_transition_audition.json")
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle("EXP-2812: State Transitions", fontsize=14, fontweight='bold')
    
    # Panel 1: Transition matrix
    if 'transition_matrix' in data:
        trans = data['transition_matrix']
        # Ensure it's 2x2
        trans_arr = np.array([[trans.get('0_to_0', 0), trans.get('0_to_1', 0)],
                              [trans.get('1_to_0', 0), trans.get('1_to_1', 0)]])
        # Normalize rows to probabilities
        trans_prob = trans_arr / trans_arr.sum(axis=1, keepdims=True)
        
        im = ax1.imshow(trans_prob, cmap='RdYlGn', vmin=0, vmax=1, aspect='auto')
        ax1.set_xticks([0, 1])
        ax1.set_yticks([0, 1])
        ax1.set_xticklabels(['S0→S0', 'S0→S1'])
        ax1.set_yticklabels(['S0', 'S1'])
        ax1.set_ylabel("Current state")
        ax1.set_title("Transition Probabilities")
        
        # Add values
        for i in range(2):
            for j in range(2):
                text = ax1.text(j, i, f'{trans_prob[i, j]:.1%}',
                              ha="center", va="center", color="black", fontweight='bold')
        plt.colorbar(im, ax=ax1)
    
    # Panel 2: Persistence
    if 'summary' in data:
        persist = data['summary'].get('day_to_day_persistence_pct', 0)
        ax2.bar(['Day-to-day\npersistence'], [persist], color='#16a085', 
               alpha=0.7, edgecolor='black', width=0.5)
        ax2.set_ylim([0, 100])
        ax2.set_ylabel("Persistence (%)")
        ax2.set_title("State Persistence (48h→next 48h)")
        ax2.text(0, persist + 2, f"{persist:.1f}%", ha='center', 
                fontweight='bold', fontsize=12)
    
    plt.tight_layout()
    plt.savefig(VIZ / "fig03_transitions.png", dpi=150, bbox_inches='tight')
    plt.close()
    print(f"✓ Generated fig03_transitions.png")


def viz_isf_decoupling():
    """Fig 4: ISF decoupling by state."""
    data = load_json("exp-2811_state_decoupling.json")
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle("EXP-2811: ISF↔Basal Coupling by State", fontsize=14, fontweight='bold')
    
    # Panel 1: ISF correlation by state
    if 'per_state' in data:
        states_info = data['per_state']
        state_names = []
        correlations = []
        for state_key in sorted(states_info.keys()):
            state_data = states_info[state_key]
            r = state_data.get('isf_basal_correlation', 0)
            state_names.append(f"State {state_key}")
            correlations.append(r)
        
        if correlations:
            colors_corr = ['#2ecc71' if abs(c) < 0.1 else '#f39c12' for c in correlations]
            ax1.bar(state_names, correlations, color=colors_corr, alpha=0.7, edgecolor='black')
            ax1.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
            ax1.set_ylabel("Correlation coefficient (ρ)")
            ax1.set_title("ISF↔Basal Coupling")
            ax1.set_ylim([-1, 1])
            for i, (name, corr) in enumerate(zip(state_names, correlations)):
                ax1.text(i, corr + 0.05 if corr > 0 else corr - 0.05, 
                        f'{corr:.3f}', ha='center', fontweight='bold')
    
    # Panel 2: Basal drift by state
    if 'per_state' in data:
        states_info = data['per_state']
        state_names2 = []
        basal_drifts = []
        for state_key in sorted(states_info.keys()):
            state_data = states_info[state_key]
            drift = state_data.get('mean_basal_drift_mg_dl_hr', 0)
            state_names2.append(f"State {state_key}")
            basal_drifts.append(drift)
        
        if basal_drifts:
            colors_drift = ['#2ecc71' if drift < 0.5 else '#e74c3c' for drift in basal_drifts]
            ax2.bar(state_names2, basal_drifts, color=colors_drift, alpha=0.7, edgecolor='black')
            ax2.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
            ax2.set_ylabel("Mean basal drift (mg/dL/hr)")
            ax2.set_title("Basal Compensation by State")
            for i, (name, drift) in enumerate(zip(state_names2, basal_drifts)):
                ax2.text(i, drift + 0.05 if drift > 0 else drift - 0.05, 
                        f'{drift:.2f}', ha='center', fontweight='bold')
    
    plt.tight_layout()
    plt.savefig(VIZ / "fig04_isf_decoupling.png", dpi=150, bbox_inches='tight')
    plt.close()
    print(f"✓ Generated fig04_isf_decoupling.png")


if __name__ == "__main__":
    print("Generating state & EGP integration visualizations...")
    viz_state_clustering()
    viz_egp_audit()
    viz_transitions()
    viz_isf_decoupling()
    print("✓ All visualizations generated")
