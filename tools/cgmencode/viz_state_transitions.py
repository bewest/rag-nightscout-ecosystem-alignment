"""State transition audition visualizations using ACTUAL experiment data."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

EXP = Path("externals/experiments")
VIZ = Path("visualizations/state-transition-audition")
VIZ.mkdir(parents=True, exist_ok=True)


def load_json(filename: str):
    path = EXP / filename
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def viz_transitions():
    """Fig 1: Transition matrix from EXP-2812."""
    data = load_json("exp-2812_state_transition_audition.json")
    
    fig, ax = plt.subplots(figsize=(8, 6))
    fig.suptitle("EXP-2812: State Transitions (Stream B)", fontweight='bold', fontsize=13)
    
    # Use actual transition data from JSON
    trans_breakdown = data.get('transition_breakdown', {})
    if trans_breakdown:
        # Extract counts
        s0_to_s0 = trans_breakdown.get('0->0', 0)
        s0_to_s1 = trans_breakdown.get('0->1', 0)
        s1_to_s0 = trans_breakdown.get('1->0', 0)
        s1_to_s1 = trans_breakdown.get('1->1', 0)
        
        trans_arr = np.array([[s0_to_s0, s0_to_s1], [s1_to_s0, s1_to_s1]], dtype=float)
        trans_prob = trans_arr / trans_arr.sum(axis=1, keepdims=True)
        
        im = ax.imshow(trans_prob, cmap='RdYlGn', vmin=0, vmax=1, aspect='auto')
        ax.set_xticks([0, 1])
        ax.set_yticks([0, 1])
        ax.set_xticklabels(['→ S0', '→ S1'], fontsize=10)
        ax.set_yticklabels(['S0', 'S1'], fontsize=10)
        ax.set_ylabel("Current state", fontsize=11)
        ax.set_xlabel("Next state", fontsize=11)
        
        for i in range(2):
            for j in range(2):
                ax.text(j, i, f'{trans_prob[i,j]:.1%}\n(n={int(trans_arr[i,j])})',
                       ha="center", va="center", color="black", fontweight='bold', fontsize=9)
        
        plt.colorbar(im, ax=ax, label="Probability")
    
    plt.tight_layout()
    plt.savefig(VIZ / "fig01_transitions.png", dpi=150, bbox_inches='tight')
    plt.close()
    print("✓ Generated fig01_transitions.png")


def viz_persistence():
    """Fig 2: Persistence analysis from EXP-2812."""
    data = load_json("exp-2812_state_transition_audition.json")
    
    fig, ax = plt.subplots(figsize=(10, 6))
    fig.suptitle("State Persistence (Day-to-day)", fontweight='bold', fontsize=13)
    
    # Calculate persistence: % that stay in same state
    trans_breakdown = data.get('transition_breakdown', {})
    if trans_breakdown:
        s0_to_s0 = trans_breakdown.get('0->0', 0)
        s0_to_s1 = trans_breakdown.get('0->1', 0)
        s1_to_s0 = trans_breakdown.get('1->0', 0)
        s1_to_s1 = trans_breakdown.get('1->1', 0)
        
        persist_s0 = 100 * s0_to_s0 / (s0_to_s0 + s0_to_s1) if (s0_to_s0 + s0_to_s1) > 0 else 0
        persist_s1 = 100 * s1_to_s1 / (s1_to_s0 + s1_to_s1) if (s1_to_s0 + s1_to_s1) > 0 else 0
        
        states = ['S0\n(well-ctrl)', 'S1\n(mod/high)']
        persistence = [persist_s0, persist_s1]
        colors = ['#2ecc71', '#e74c3c']
        
        bars = ax.bar(states, persistence, color=colors, alpha=0.7, edgecolor='black', width=0.5)
        ax.set_ylabel("Persistence (%)", fontsize=11)
        ax.set_title("% of state transitions that repeat next day", fontsize=11)
        ax.set_ylim([0, 100])
        
        for bar, val in zip(bars, persistence):
            ax.text(bar.get_x() + bar.get_width()/2., val + 2,
                   f'{val:.1f}%', ha='center', fontweight='bold', fontsize=11)
    
    plt.tight_layout()
    plt.savefig(VIZ / "fig02_persistence.png", dpi=150, bbox_inches='tight')
    plt.close()
    print("✓ Generated fig02_persistence.png")


def viz_audition():
    """Fig 3: Audition results from EXP-2812."""
    data = load_json("exp-2812_state_transition_audition.json")
    
    fig, ax = plt.subplots(figsize=(10, 6))
    fig.suptitle("EXP-2812: Transition Audition Results", fontweight='bold', fontsize=13)
    
    ax.axis('off')
    
    summary_text = f"""
    Experiment Summary
    ═══════════════════════════════════════
    
    Dataset
    ───────────────────────────────────────
    Patients: {data.get('n_patients')}
    State transitions analyzed: {data.get('n_transitions_total'):,}
    Pre-post records: {data.get('n_pre_post_records'):,}
    
    Results
    ───────────────────────────────────────
    Transitions to S0→S1: {data.get('n_s0_to_s1_patients')} patients
    
    Stream Verdict
    ───────────────────────────────────────
    Conflation Risk: {data.get('conflation_risk')}
    Verdict: Stream B operational
             (settings/operational question)
    """
    
    ax.text(0.05, 0.95, summary_text, fontsize=10, verticalalignment='top',
           family='monospace', transform=ax.transAxes,
           bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.5))
    
    plt.tight_layout()
    plt.savefig(VIZ / "fig03_audition.png", dpi=150, bbox_inches='tight')
    plt.close()
    print("✓ Generated fig03_audition.png")


if __name__ == "__main__":
    print("Generating state transition audition visualizations...")
    viz_transitions()
    viz_persistence()
    viz_audition()
    print("✓ All visualizations generated")
