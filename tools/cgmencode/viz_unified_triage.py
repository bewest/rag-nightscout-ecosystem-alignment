"""Cross-tab flat-phenotype patients with EXP-2812 + EXP-2831 triage flags.

Output: docs/60-research/figures/triage_unified_table.png
        externals/experiments/exp-2845b_unified_triage.parquet

Charter: Stream B operational; cross-references existing flag tables.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

EXP = Path("externals/experiments")
FIG = Path("docs/60-research/figures")


def main():
    pheno = pd.read_parquet(EXP / "exp-2844_phenotype_table.parquet")
    rec = pd.read_parquet(EXP / "exp-2812_triage_flags.parquet")
    wear = pd.read_parquet(EXP / "exp-2831_triage_flags.parquet")

    df = pheno[["patient_id", "controller", "phenotype",
                "actual_basal_shift_pct", "median_recovery_fraction"]].merge(
        rec[["patient_id", "n_transitions", "median_post_pct_high"]],
        on="patient_id", how="left",
    ).merge(
        wear[["patient_id", "delta_pct", "flag_site_change"]],
        on="patient_id", how="left",
    )
    df.rename(columns={"delta_pct": "wear_delta_pct"}, inplace=True)

    # Flag columns
    df["flag_recovery_low"] = df["median_recovery_fraction"] < 0.40
    df["flag_post_high"] = df["median_post_pct_high"] > 30
    df["flag_wear"] = df["flag_site_change"].fillna(False).astype(bool)
    df["flag_count"] = (
        df["flag_recovery_low"].astype(int)
        + df["flag_post_high"].astype(int)
        + df["flag_wear"].astype(int)
    )

    # Sort: most flags first; within phenotype
    df = df.sort_values(
        ["flag_count", "phenotype", "patient_id"],
        ascending=[False, True, True],
    ).reset_index(drop=True)

    out_parq = EXP / "exp-2845b_unified_triage.parquet"
    df.to_parquet(out_parq, index=False)
    print(df.to_string(index=False))

    # Render as a chart-table image
    fig, ax = plt.subplots(figsize=(13, max(4, 0.45 * len(df))))
    ax.axis("off")
    cols = [
        "patient_id", "controller", "phenotype",
        "actual_basal_shift_pct", "median_recovery_fraction",
        "median_post_pct_high", "wear_delta_pct",
        "flag_recovery_low", "flag_post_high", "flag_wear", "flag_count",
    ]
    cell_text = []
    cell_colors = []
    for _, row in df.iterrows():
        text_row = []
        color_row = []
        for c in cols:
            v = row.get(c, "")
            if isinstance(v, float):
                text_row.append(f"{v:.2f}" if not np.isnan(v) else "—")
            elif isinstance(v, (bool, np.bool_)):
                text_row.append("✓" if v else "")
            else:
                text_row.append(str(v))
            # Color cells
            if c == "phenotype":
                color_row.append(
                    {"up_shift": "#cce5ff", "flat": "#eeeeee",
                     "down_shift": "#ffcccc"}.get(v, "white")
                )
            elif c.startswith("flag_") and c != "flag_count" and bool(v):
                color_row.append("#ffe0a3")
            elif c == "flag_count" and isinstance(v, (int, np.integer)) and v >= 2:
                color_row.append("#ff9999")
            elif c == "flag_count" and isinstance(v, (int, np.integer)) and v == 1:
                color_row.append("#ffe0a3")
            else:
                color_row.append("white")
        cell_text.append(text_row)
        cell_colors.append(color_row)

    table = ax.table(
        cellText=cell_text, colLabels=cols, cellColours=cell_colors,
        loc="center", cellLoc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8)
    table.scale(1.0, 1.4)
    ax.set_title(
        "Unified triage table — phenotype × recovery × wear (EXP-2812 + 2831 + 2844)\n"
        "Stream B; flags from existing experiments; sorted by flag count",
        fontsize=11, pad=18,
    )
    out_fig = FIG / "triage_unified_table.png"
    plt.savefig(out_fig, dpi=120, bbox_inches="tight")
    plt.close()
    print(f"\nWrote {out_fig}")


if __name__ == "__main__":
    main()
