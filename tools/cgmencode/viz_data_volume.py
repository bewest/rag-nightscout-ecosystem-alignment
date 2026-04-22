"""Data volume and triage synthesis visualizations."""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

VIZ = Path("visualizations/data-volume-and-triage")
VIZ.mkdir(parents=True, exist_ok=True)


def make_placeholder(fig_name, title):
    """Generate placeholder visualization."""
    fig, ax = plt.subplots(figsize=(10, 6))
    fig.suptitle(title, fontsize=14, fontweight='bold')
    ax.text(0.5, 0.5, f"Visualization: {title}\n(data pending)",
           ha='center', va='center', transform=ax.transAxes,
           fontsize=12, color='gray', style='italic')
    ax.axis('off')
    plt.tight_layout()
    plt.savefig(VIZ / fig_name, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"✓ Generated {fig_name}")


if __name__ == "__main__":
    print("Generating data volume and triage visualizations...")
    make_placeholder("fig01_volume_analysis.png", "Data volume metrics")
    make_placeholder("fig02_triage_flowchart.png", "Triage decision flow")
    make_placeholder("fig03_synthesis_results.png", "Synthesis outcomes")
    print("✓ All visualizations generated")
