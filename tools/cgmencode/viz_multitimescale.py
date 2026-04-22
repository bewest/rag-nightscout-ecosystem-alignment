"""Generic multi-timescale supply-demand visualizations."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

EXP = Path("externals/experiments")
VIZ = Path("visualizations/multitimescale-supply-demand")
VIZ.mkdir(parents=True, exist_ok=True)


def load_json(filename: str):
    path = EXP / filename
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def make_placeholder(fig_name, exp_id, title):
    """Generate placeholder visualization."""
    fig, ax = plt.subplots(figsize=(10, 6))
    fig.suptitle(f"{exp_id}: {title}", fontsize=14, fontweight='bold')
    ax.text(0.5, 0.5, f"Visualization for {exp_id}\n(data pending)",
           ha='center', va='center', transform=ax.transAxes,
           fontsize=12, color='gray', style='italic')
    ax.axis('off')
    plt.tight_layout()
    plt.savefig(VIZ / fig_name, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"✓ Generated {fig_name}")


if __name__ == "__main__":
    print("Generating multitimescale supply-demand visualizations...")
    make_placeholder("fig01_supply_profiles.png", "EXP-2833-2835", "Supply profiles")
    make_placeholder("fig02_demand_evolution.png", "EXP-2836-2838", "Demand evolution")
    make_placeholder("fig03_balance_audit.png", "EXP-2839", "Supply-demand balance")
    print("✓ All visualizations generated")
