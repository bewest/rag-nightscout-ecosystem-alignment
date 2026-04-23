"""EXP-2909 — hourly cf-stratified replay.

Combines EXP-2896 (hourly resolution) with EXP-2907 (cf-conditioning).
For each lineage × hour-of-day cell, restricts to high-cf events
(cf_severe >= 0.95) and computes observed severe rate. This tests
whether oref1's 03:00 spike and oref0's 00-06 night-long peak survive
load matching at hourly resolution.

Outputs heatmap PNG + summary JSON.
"""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO = Path(__file__).resolve().parent.parent.parent
SRC = REPO / "externals" / "experiments" / "exp-2889_event_replay.parquet"
LINEAGE_SRC = REPO / "externals" / "experiments" / "exp-2891_simpson_dose_response.parquet"
OUT_DIR = REPO / "docs" / "visualizations"
OUT_DIR.mkdir(parents=True, exist_ok=True)
SUMMARY = REPO / "externals" / "experiments" / "exp-2909_summary.json"
PNG = OUT_DIR / "exp-2909-hourly-cf-stratified.png"

CF_HIGH = 0.95
MIN_N = 5  # cell minimum to plot


def main() -> None:
    df = pd.read_parquet(SRC)
    lineage_map = pd.read_parquet(LINEAGE_SRC)[["patient_id", "lineage"]]
    df = df.merge(lineage_map, on="patient_id", how="left")
    df = df[df["lineage"].notna() & (df["lineage"] != "unknown")].copy()
    df["is_high_cf"] = df["cf_severe"] >= CF_HIGH
    df["hour"] = df["nadir_hour"].astype(int)

    # Marginal per-lineage hourly severe rate (no stratification)
    marg = (
        df.groupby(["lineage", "hour"])
        .agg(n=("obs_severe", "size"), severe_rate=("obs_severe", "mean"))
        .reset_index()
    )

    # Stratified: cf_high only
    strat = (
        df[df["is_high_cf"]]
        .groupby(["lineage", "hour"])
        .agg(n=("obs_severe", "size"), severe_rate=("obs_severe", "mean"))
        .reset_index()
    )

    lineages = ["Loop (iOS)", "oref1 (modern)", "oref0 (legacy)"]
    hours = list(range(24))

    def to_grid(d: pd.DataFrame) -> np.ndarray:
        g = np.full((len(lineages), 24), np.nan)
        for _, row in d.iterrows():
            if row["lineage"] in lineages and row["n"] >= MIN_N:
                i = lineages.index(row["lineage"])
                g[i, int(row["hour"])] = row["severe_rate"]
        return g

    marg_grid = to_grid(marg)
    strat_grid = to_grid(strat)
    delta = strat_grid - marg_grid

    # Plot 3-panel heatmap
    fig, axes = plt.subplots(3, 1, figsize=(13, 8), sharex=True)
    titles = [
        "Marginal hourly severe rate (no cf stratification)",
        "High-cf stratum (cf_severe >= 0.95) hourly severe rate",
        "Δ (high-cf − marginal) — positive = night degradation worsens at load ceiling",
    ]
    grids = [marg_grid, strat_grid, delta]
    cmaps = ["YlOrRd", "YlOrRd", "RdBu_r"]
    vmins = [0, 0, -0.3]
    vmaxs = [1.0, 1.0, 0.3]

    for ax, g, title, cmap, vmin, vmax in zip(axes, grids, titles, cmaps, vmins, vmaxs):
        im = ax.imshow(g, aspect="auto", cmap=cmap, vmin=vmin, vmax=vmax)
        ax.set_yticks(range(len(lineages)))
        ax.set_yticklabels(lineages, fontsize=9)
        ax.set_xticks(range(24))
        ax.set_xticklabels([f"{h:02d}" for h in range(24)], fontsize=8)
        ax.set_title(title, fontsize=10)
        plt.colorbar(im, ax=ax, fraction=0.018, pad=0.01)
        for i in range(len(lineages)):
            for j in range(24):
                v = g[i, j]
                if not np.isnan(v):
                    ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=6, color="black")
    axes[-1].set_xlabel("Hour of nadir (local)")
    plt.tight_layout()
    fig.savefig(PNG, dpi=140)
    plt.close(fig)

    # Numeric summary: peak hours per lineage per stratum
    summary = {"cf_high_threshold": CF_HIGH, "min_n_per_cell": MIN_N, "lineages": {}}
    for i, lineage in enumerate(lineages):
        m_hours = [(h, marg_grid[i, h]) for h in range(24) if not np.isnan(marg_grid[i, h])]
        s_hours = [(h, strat_grid[i, h]) for h in range(24) if not np.isnan(strat_grid[i, h])]
        m_hours_sorted = sorted(m_hours, key=lambda x: -x[1])[:3]
        s_hours_sorted = sorted(s_hours, key=lambda x: -x[1])[:3]
        summary["lineages"][lineage] = {
            "marginal_top3_hours": [{"hour": h, "rate": float(r)} for h, r in m_hours_sorted],
            "high_cf_top3_hours": [{"hour": h, "rate": float(r)} for h, r in s_hours_sorted],
            "marginal_n_cells": len(m_hours),
            "high_cf_n_cells": len(s_hours),
        }

    SUMMARY.write_text(json.dumps(summary, indent=2))
    print(f"[exp-2909] wrote {PNG}")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
