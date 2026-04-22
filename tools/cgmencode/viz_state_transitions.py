"""Visualizations for state transitions & audition (EXP-2812, 2823).

Generates 3-panel dashboard for state-transition-audition-report-2026-04-22.md:
1. Transition matrices 
2. Recovery curves
3. Wear sensitivity

Output: visualizations/state-transition-audition/fig{01-03}_*.png
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

EXP = Path("externals/experiments")
VIZ = Path("visualizations/state-transition-audition")
VIZ.mkdir(parents=True, exist_ok=True)


def load_json(filename: str):
    """Load experiment JSON data."""
    path = EXP / filename
    if not path.exists():
        print(f"WARNING: {filename} not found at {path}")
        return {}
    with open(path) as f:
        return json.load(f)


def viz_transitions_matrix():
    """Fig 1: Transition matrices."""
    data = load_json("exp-2812_state_transition_audition.json")
    
    fig, ax = plt.subplots(figsize=(8, 6))
    fig.suptitle("EXP-2812: State Transitions", fontsize=14, fontweight='bold')
    
    if 'transition_matrix' in data:
        trans = data['transition_matrix']
        trans_arr = np.array([[trans.get('0_to_0', 0), trans.get('0_to_1', 0)],
                              [trans.get('1_to_0', 0), trans.get('1_to_1', 0)]])
        trans_prob = trans_arr / trans_arr.sum(axis=1, keepdims=True)
        
        im = ax.imshow(trans_prob, cmap='RdYlGn', vmin=0, vmax=1)
        ax.set_xticks([0, 1])
        ax.set_yticks([0, 1])
        ax.set_xticklabels(['To S0', 'To S1'])
        ax.set_yticklabels(['From S0', 'From S1'])
        ax.set_ylabel("Current state")
        ax.set_xlabel("Next state")
        ax.set_title("Transition Probabilities (48h windows)")
        
        for i in range(2):
            for j in range(2):
                text = ax.text(j, i, f'{trans_prob[i, j]:.1%}\n(n={int(trans_arr[i, j])})',
                              ha="center", va="center", color="black", fontweight='bold')
        
        cbar = plt.colorbar(im, ax=ax)
        cbar.set_label("Probability", rotation=270, labelpad=20)
    
    plt.tight_layout()
    plt.savefig(VIZ / "fig01_transitions_matrix.png", dpi=150, bbox_inches='tight')
    plt.close()
    print(f"✓ Generated fig01_transitions_matrix.png")


def viz_recovery_curves():
    """Fig 2: Recovery curves."""
    data = load_json("exp-2812_state_transition_audition.json")
    
    fig, ax = plt.subplots(figsize=(10, 6))
    fig.suptitle("State Transition Recovery Profile", fontsize=14, fontweight='bold')
    
    if 'recovery_curves' in data:
        curves = data['recovery_curves']
        for i, (trans_type, curve) in enumerate(curves.items()):
            if isinstance(curve, dict):
                times = sorted(curve.keys())
                values = [curve[t] for t in times]
                ax.plot(times, values, 'o-', label=trans_type, linewidth=2, markersize=6)
        
        ax.set_xlabel("Hours post-transition")
        ax.set_ylabel("% in target (70-180 mg/dL)")
        ax.set_title("Recovery Trajectory by Transition Type")
        ax.legend()
        ax.grid(True, alpha=0.3)
    else:
        # Placeholder if data not available
        ax.text(0.5, 0.5, "Recovery curve data pending", ha='center', va='center',
               transform=ax.transAxes, fontsize=12, color='gray')
    
    plt.tight_layout()
    plt.savefig(VIZ / "fig02_recovery_curves.png", dpi=150, bbox_inches='tight')
    plt.close()
    print(f"✓ Generated fig02_recovery_curves.png")


def viz_wear_sensitivity():
    """Fig 3: Wear sensitivity."""
    data = load_json("exp-2823_egp_state_interaction.json")
    
    fig, ax = plt.subplots(figsize=(10, 6))
    fig.suptitle("EXP-2823: Sensor Wear Impact on State Transitions", 
                fontsize=14, fontweight='bold')
    
    if 'wear_impact' in data:
        wear_data = data['wear_impact']
        age_bins = sorted(wear_data.keys())
        
        persistence = []
        for age in age_bins:
            persist = wear_data[age].get('day_to_day_persistence', 0)
            persistence.append(persist)
        
        colors_wear = ['#2ecc71' if p > 0.7 else '#f39c12' if p > 0.5 else '#e74c3c' 
                      for p in persistence]
        ax.bar(range(len(age_bins)), persistence, color=colors_wear, alpha=0.7, 
              edgecolor='black')
        ax.set_xticks(range(len(age_bins)))
        ax.set_xticklabels([f"Day {b}" for b in age_bins])
        ax.set_ylabel("State Persistence (%)")
        ax.set_xlabel("Sensor age (days)")
        ax.set_ylim([0, 100])
        ax.axhline(y=84.7, color='red', linestyle='--', alpha=0.5, 
                  label='Overall mean (84.7%)')
        ax.legend()
    else:
        # Placeholder
        ax.text(0.5, 0.5, "Wear sensitivity data pending", ha='center', va='center',
               transform=ax.transAxes, fontsize=12, color='gray')
    
    plt.tight_layout()
    plt.savefig(VIZ / "fig03_wear_sensitivity.png", dpi=150, bbox_inches='tight')
    plt.close()
    print(f"✓ Generated fig03_wear_sensitivity.png")


if __name__ == "__main__":
    print("Generating state transition audition visualizations...")
    viz_transitions_matrix()
    viz_recovery_curves()
    viz_wear_sensitivity()
    print("✓ All visualizations generated")
