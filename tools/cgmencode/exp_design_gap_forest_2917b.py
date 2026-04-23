"""EXP-2917b — Forest plot of design-cell protection CIs and pairwise gaps.

Renders two panels:
  (top)    Cell-level mean protection with 95% bootstrap CIs, by
           lineage × tercile. n=1 cells shown as point markers
           with an explicit "n=1" annotation (no CI bar).
  (bottom) Pairwise design-gap CIs (A - B). Pairs that involve an
           n=1 cell are drawn in grey with a hash mark to flag
           degenerate variance.

Outputs PNG to docs/visualizations/exp-2917-design-gap-forest.png.
"""
from __future__ import annotations
from pathlib import Path

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO = Path(__file__).resolve().parent.parent.parent
SRC = REPO / "externals" / "experiments" / "exp-2917_design_cell_cis.parquet"
OUT = REPO / "docs" / "visualizations" / "exp-2917-design-gap-forest.png"
OUT.parent.mkdir(parents=True, exist_ok=True)

LINEAGE_COLOR = {
    "Loop (iOS)": "#1f77b4",
    "oref0 (legacy)": "#d62728",
    "oref1 (modern)": "#2ca02c",
}
TERCILE_ORDER = ["conservative", "moderate", "aggressive"]


def main() -> None:
    import json
    summary = json.loads((REPO / "externals" / "experiments" / "exp-2917_summary.json").read_text())
    cells = pd.DataFrame(summary["cell_cis"])
    pairs = pd.DataFrame(summary["pairwise_design_gaps"])

    fig, (ax_cells, ax_pairs) = plt.subplots(2, 1, figsize=(10, 9), gridspec_kw={"height_ratios": [1, 1.2]})

    # ---- Top: cell-level forest --------------------------------------------
    cells = cells.copy()
    cells["tier_idx"] = cells["tercile"].map({t: i for i, t in enumerate(TERCILE_ORDER)})
    cells = cells.sort_values(["tier_idx", "lineage"]).reset_index(drop=True)
    y = list(range(len(cells)))
    for i, row in cells.iterrows():
        c = LINEAGE_COLOR.get(row["lineage"], "grey")
        if row["ci_possible"]:
            ax_cells.errorbar(
                row["mean_protection"], i,
                xerr=[[row["mean_protection"] - row["ci95_lo"]], [row["ci95_hi"] - row["mean_protection"]]],
                fmt="o", color=c, ecolor=c, capsize=4, markersize=7,
            )
        else:
            ax_cells.plot(row["mean_protection"], i, marker="D", color=c, markersize=8, mfc="white", mew=1.5)
            ax_cells.annotate(" n=1", (row["mean_protection"], i), va="center", fontsize=8, color="dimgrey")

    ax_cells.set_yticks(y)
    ax_cells.set_yticklabels([f"{r['lineage']}  /  {r['tercile']}  (n={int(r['n'])})" for _, r in cells.iterrows()], fontsize=9)
    ax_cells.invert_yaxis()
    ax_cells.set_xlabel("Mean AID protection (severe)")
    ax_cells.set_xlim(0.0, 1.0)
    ax_cells.axvline(0.5, color="lightgrey", linestyle="--", linewidth=0.8)
    ax_cells.set_title("Design-cell protection means with 95% bootstrap CI\n(diamond = n=1, no CI possible)", fontsize=11)
    ax_cells.grid(axis="x", alpha=0.3)

    # ---- Bottom: pairwise gap forest ---------------------------------------
    pairs = pairs.copy()
    pairs["abs_gap"] = pairs["gap_mean"].abs()
    pairs = pairs.sort_values("abs_gap", ascending=True).reset_index(drop=True)
    y2 = list(range(len(pairs)))
    for i, row in pairs.iterrows():
        n1_pair = (row["n_a"] == 1) or (row["n_b"] == 1)
        color = "grey" if n1_pair else ("#2ca02c" if row["ci_excludes_zero"] else "dimgrey")
        ax_pairs.errorbar(
            row["gap_mean"], i,
            xerr=[[row["gap_mean"] - row["gap_ci_lo"]], [row["gap_ci_hi"] - row["gap_mean"]]],
            fmt="s" if n1_pair else "o",
            color=color, ecolor=color, capsize=4, markersize=7, alpha=0.95,
        )
        if n1_pair:
            ax_pairs.annotate(" †", (row["gap_ci_hi"], i), va="center", fontsize=10, color="dimgrey")

    ax_pairs.axvline(0.0, color="black", linewidth=0.8)
    ax_pairs.set_yticks(y2)
    ax_pairs.set_yticklabels(
        [f"{r['tercile']}: {r['design_a']} − {r['design_b']}  (n={int(r['n_a'])},{int(r['n_b'])})" for _, r in pairs.iterrows()],
        fontsize=9,
    )
    ax_pairs.invert_yaxis()
    ax_pairs.set_xlabel("Pairwise protection gap (A − B)")
    ax_pairs.set_title("Pairwise design-gap CIs (95%)\ngreen = both n≥2 and CI excludes zero; † = degenerate (n=1)", fontsize=11)
    ax_pairs.grid(axis="x", alpha=0.3)

    plt.tight_layout()
    plt.savefig(OUT, dpi=150)
    print(f"[exp-2917b] {OUT}")


if __name__ == "__main__":
    main()
