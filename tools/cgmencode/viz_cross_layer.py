"""Visualizations for cross-layer interactions (EXP-2830, 2831, 2832).

Generates 3-panel dashboard for cross-layer-interactions-report-2026-04-22.md:
1. Formulation constant findings
2. Correction decomposition  
3. Inverse EGP validation

Output: visualizations/cross-layer-interactions/fig{01-03}_*.png
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

EXP = Path("externals/experiments")
VIZ = Path("visualizations/cross-layer-interactions")
VIZ.mkdir(parents=True, exist_ok=True)


def load_json(filename: str):
    """Load experiment JSON data."""
    path = EXP / filename
    if not path.exists():
        print(f"WARNING: {filename} not found at {path}")
        return {}
    with open(path) as f:
        return json.load(f)


def viz_formulation_constant():
    """Fig 1: Formulation constant findings."""
    data = load_json("exp-2830_formulation_constant.json")
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle("EXP-2830: Formulation Constant", fontsize=14, fontweight='bold')
    
    # Panel 1: Per-patient estimates
    if 'per_patient' in data:
        patients = list(data['per_patient'].keys())
        constants = []
        for p in patients:
            c = data['per_patient'][p].get('formulation_constant', 0)
            constants.append(c)
        
        if constants:
            ax1.hist(constants, bins=8, color='#3498db', alpha=0.7, edgecolor='black')
            ax1.axvline(np.mean(constants), color='red', linestyle='--', 
                       linewidth=2, label=f"Mean: {np.mean(constants):.3f}")
            ax1.set_xlabel("Formulation constant (1/mg/dL)")
            ax1.set_ylabel("Number of patients")
            ax1.set_title("Distribution across cohort")
            ax1.legend()
    
    # Panel 2: Summary vs theory
    if 'summary' in data:
        summary = data['summary']
        empirical = summary.get('mean_formulation_constant', 0)
        theoretical = summary.get('theoretical_constant', 0)
        
        categories = ['Empirical', 'Theoretical']
        values = [empirical, theoretical]
        colors = ['#3498db', '#95a5a6']
        
        ax2.bar(categories, values, color=colors, alpha=0.7, edgecolor='black')
        ax2.set_ylabel("Constant value (1/mg/dL)")
        ax2.set_title("Empirical vs Theoretical")
        for i, v in enumerate(values):
            ax2.text(i, v + 0.0001, f'{v:.6f}', ha='center', fontweight='bold')
    
    plt.tight_layout()
    plt.savefig(VIZ / "fig01_formulation_constant.png", dpi=150, bbox_inches='tight')
    plt.close()
    print(f"✓ Generated fig01_formulation_constant.png")


def viz_correction_decomposition():
    """Fig 2: Correction decomposition."""
    data = load_json("exp-2830_formulation_constant.json")
    
    fig, ax = plt.subplots(figsize=(10, 6))
    fig.suptitle("Correction Event Decomposition", fontsize=14, fontweight='bold')
    
    if 'correction_components' in data:
        components = data['correction_components']
        comp_names = list(components.keys())
        comp_values = list(components.values())
        
        colors_comp = ['#2ecc71', '#3498db', '#f39c12', '#e74c3c'][:len(comp_names)]
        wedges, texts, autotexts = ax.pie(comp_values, labels=comp_names, autopct='%1.1f%%',
                                           colors=colors_comp, startangle=90)
        
        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_fontweight('bold')
            autotext.set_fontsize(10)
    else:
        ax.text(0.5, 0.5, "Decomposition data pending", ha='center', va='center',
               transform=ax.transAxes, fontsize=12, color='gray')
    
    plt.tight_layout()
    plt.savefig(VIZ / "fig02_correction_decomposition.png", dpi=150, bbox_inches='tight')
    plt.close()
    print(f"✓ Generated fig02_correction_decomposition.png")


def viz_inverse_egp():
    """Fig 3: Inverse EGP validation."""
    data = load_json("exp-2832_inverse_egp.json")
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle("EXP-2832: Inverse EGP Validation", fontsize=14, fontweight='bold')
    
    # Panel 1: Forward vs inverse correlation
    if 'comparison' in data:
        comp = data['comparison']
        methods = ['Forward\nsubtraction', 'Inverse\nformulation']
        correlations = [comp.get('forward_r', 0), comp.get('inverse_r', 0)]
        colors_comp = ['#3498db', '#9b59b6']
        
        ax1.bar(methods, correlations, color=colors_comp, alpha=0.7, edgecolor='black')
        ax1.set_ylabel("Correlation with demand (r)")
        ax1.set_title("EGP Extraction Method Comparison")
        ax1.set_ylim([0, 1])
        for i, (method, corr) in enumerate(zip(methods, correlations)):
            ax1.text(i, corr + 0.02, f'{corr:.3f}', ha='center', fontweight='bold')
    
    # Panel 2: Per-patient scatter
    if 'per_patient' in data:
        patients_data = data['per_patient']
        forward_vals = []
        inverse_vals = []
        
        for p in patients_data.values():
            if 'forward_egp' in p and 'inverse_egp' in p:
                forward_vals.append(p['forward_egp'])
                inverse_vals.append(p['inverse_egp'])
        
        if forward_vals and inverse_vals:
            ax2.scatter(forward_vals, inverse_vals, alpha=0.6, s=100, color='#16a085')
            
            # Perfect agreement line
            lim = [min(forward_vals + inverse_vals), max(forward_vals + inverse_vals)]
            ax2.plot(lim, lim, 'r--', alpha=0.5, label='Perfect agreement')
            
            ax2.set_xlabel("Forward subtraction (mg/dL/min)")
            ax2.set_ylabel("Inverse formulation (mg/dL/min)")
            ax2.set_title("Per-patient correlation")
            ax2.legend()
    
    plt.tight_layout()
    plt.savefig(VIZ / "fig03_inverse_egp.png", dpi=150, bbox_inches='tight')
    plt.close()
    print(f"✓ Generated fig03_inverse_egp.png")


if __name__ == "__main__":
    print("Generating cross-layer interactions visualizations...")
    viz_formulation_constant()
    viz_correction_decomposition()
    viz_inverse_egp()
    print("✓ All visualizations generated")
