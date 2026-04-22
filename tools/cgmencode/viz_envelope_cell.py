"""Envelope vs cell-level reconciliation visualizations."""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

VIZ = Path("visualizations/envelope-vs-cell-level")
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
    print("Generating envelope vs cell-level visualizations...")
    make_placeholder("fig01_envelope_summary.png", "Envelope-level analysis")
    make_placeholder("fig02_cell_resolution.png", "Cell-level decomposition")
    print("✓ All visualizations generated")
