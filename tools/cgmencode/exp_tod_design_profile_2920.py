"""EXP-2920 - Time-of-day x design severe-event profile.

Scientific characterization of WHEN each AID design's residual
severe-event burden lands. Per-hour-of-day, compute fraction of
cells with glucose<54 (severe hypo) and glucose>250 (severe hyper),
stratified by lineage. Per-patient first, then patient-mean within
lineage (avoids the patient-volume Simpson trap).

Scope: design-level scientific characterization for AID-author
audience. NOT therapy advice. Per binding scope statement
(docs/60-research/exp-2916-design-gap-2026-04-23.md).

Outputs:
  - exp-2920_summary.json: lineage x hour means + bootstrap CI
  - exp-2920_hourly.parquet: per-patient hourly fractions
  - exp-2920-tod-profile.png: small-multiples plot
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
SIMP = REPO / "externals" / "experiments" / "exp-2891_simpson_dose_response.parquet"
GRID = REPO / "externals" / "ns-parquet" / "training" / "grid.parquet"
OUT_J = REPO / "externals" / "experiments" / "exp-2920_summary.json"
OUT_P = REPO / "externals" / "experiments" / "exp-2920_hourly.parquet"
PNG = REPO / "docs" / "visualizations" / "exp-2920-tod-profile.png"
PNG.parent.mkdir(parents=True, exist_ok=True)

RNG = np.random.default_rng(2920)
N_BOOT = 2000
HYPO = 54
HYPER = 250

LINEAGE_ORDER = ["Loop (iOS)", "oref0 (legacy)", "oref1 (modern)"]
LINEAGE_COLOR = {"Loop (iOS)": "#1f77b4", "oref0 (legacy)": "#d62728", "oref1 (modern)": "#2ca02c"}


def per_patient_hourly(g: pd.DataFrame) -> pd.DataFrame:
    g = g.dropna(subset=["glucose"]).copy()
    g["hour"] = g["time"].dt.hour
    rows = []
    for (pid, hr), sub in g.groupby(["patient_id", "hour"]):
        n = len(sub)
        if n < 12:
            continue
        rows.append({
            "patient_id": pid,
            "hour": int(hr),
            "n_cells": n,
            "frac_hypo": float((sub["glucose"] < HYPO).mean()),
            "frac_hyper": float((sub["glucose"] > HYPER).mean()),
            "mean_glucose": float(sub["glucose"].mean()),
        })
    return pd.DataFrame(rows)


def boot_ci(values: np.ndarray, n_boot: int = N_BOOT) -> tuple[float, float]:
    if len(values) < 2:
        v = float(values[0]) if len(values) == 1 else float("nan")
        return v, v
    samples = RNG.choice(values, size=(n_boot, len(values)), replace=True).mean(axis=1)
    return float(np.percentile(samples, 2.5)), float(np.percentile(samples, 97.5))


def main() -> None:
    print("[exp-2920] loading lineage labels")
    simp = pd.read_parquet(SIMP, columns=["patient_id", "lineage", "tercile"])
    simp = simp[simp["lineage"].isin(LINEAGE_ORDER)]

    print("[exp-2920] loading grid (this is large)")
    grid = pd.read_parquet(GRID, columns=["patient_id", "time", "glucose"])
    grid = grid[grid["patient_id"].isin(set(simp["patient_id"]))]
    print(f"[exp-2920] grid rows after lineage filter: {len(grid):,}")

    hourly = per_patient_hourly(grid)
    hourly = hourly.merge(simp, on="patient_id", how="left")
    hourly.to_parquet(OUT_P)

    cells = []
    for lineage in LINEAGE_ORDER:
        for hr in range(24):
            sub = hourly[(hourly["lineage"] == lineage) & (hourly["hour"] == hr)]
            n_pat = sub["patient_id"].nunique()
            if n_pat == 0:
                continue
            patient_means_hypo = sub.groupby("patient_id")["frac_hypo"].mean().values
            patient_means_hyper = sub.groupby("patient_id")["frac_hyper"].mean().values
            lo_h, hi_h = boot_ci(patient_means_hypo)
            lo_y, hi_y = boot_ci(patient_means_hyper)
            cells.append({
                "lineage": lineage,
                "hour": hr,
                "n_patients": int(n_pat),
                "mean_frac_hypo": float(patient_means_hypo.mean()),
                "ci_lo_hypo": lo_h, "ci_hi_hypo": hi_h,
                "mean_frac_hyper": float(patient_means_hyper.mean()),
                "ci_lo_hyper": lo_y, "ci_hi_hyper": hi_y,
            })
    cells_df = pd.DataFrame(cells)

    summary = {
        "scope": "design-level time-of-day severe-event profile; AID-author audience; not therapy advice",
        "n_patients_total": int(hourly["patient_id"].nunique()),
        "n_patients_per_lineage": hourly.groupby("lineage")["patient_id"].nunique().to_dict(),
        "hourly_cells": cells_df.to_dict(orient="records"),
    }
    OUT_J.write_text(json.dumps(summary, indent=2, default=str))
    print(f"[exp-2920] {OUT_J}")

    # Render: 2x1 small multiples
    fig, (ax_hypo, ax_hyper) = plt.subplots(2, 1, figsize=(11, 7), sharex=True)
    for lineage in LINEAGE_ORDER:
        sub = cells_df[cells_df["lineage"] == lineage].sort_values("hour")
        if sub.empty:
            continue
        c = LINEAGE_COLOR[lineage]
        n_pat = sub["n_patients"].iloc[0]
        ax_hypo.plot(sub["hour"], sub["mean_frac_hypo"] * 100, "o-", color=c,
                     label=f"{lineage} (n={n_pat})")
        ax_hypo.fill_between(sub["hour"], sub["ci_lo_hypo"] * 100, sub["ci_hi_hypo"] * 100,
                             color=c, alpha=0.15)
        ax_hyper.plot(sub["hour"], sub["mean_frac_hyper"] * 100, "o-", color=c,
                      label=f"{lineage} (n={n_pat})")
        ax_hyper.fill_between(sub["hour"], sub["ci_lo_hyper"] * 100, sub["ci_hi_hyper"] * 100,
                              color=c, alpha=0.15)

    ax_hypo.set_ylabel("% of 5-min cells with glucose < 54")
    ax_hypo.set_title("Severe hypoglycemia by hour-of-day (patient-mean within design)\n95% bootstrap CI; AID-author scope")
    ax_hypo.legend(loc="upper right", fontsize=9)
    ax_hypo.grid(alpha=0.3)
    ax_hyper.set_ylabel("% of 5-min cells with glucose > 250")
    ax_hyper.set_xlabel("Hour of day (local)")
    ax_hyper.set_title("Severe hyperglycemia by hour-of-day")
    ax_hyper.legend(loc="upper right", fontsize=9)
    ax_hyper.grid(alpha=0.3)
    ax_hyper.set_xticks(range(0, 24, 2))
    plt.tight_layout()
    plt.savefig(PNG, dpi=150)
    print(f"[exp-2920] {PNG}")

    # Brief headline
    print("\nPeak hypo hour by design:")
    for lineage in LINEAGE_ORDER:
        sub = cells_df[cells_df["lineage"] == lineage]
        if sub.empty:
            continue
        peak = sub.loc[sub["mean_frac_hypo"].idxmax()]
        print(f"  {lineage}: hour {int(peak['hour']):02d}  ({peak['mean_frac_hypo']*100:.2f}%)")
    print("\nPeak hyper hour by design:")
    for lineage in LINEAGE_ORDER:
        sub = cells_df[cells_df["lineage"] == lineage]
        if sub.empty:
            continue
        peak = sub.loc[sub["mean_frac_hyper"].idxmax()]
        print(f"  {lineage}: hour {int(peak['hour']):02d}  ({peak['mean_frac_hyper']*100:.2f}%)")


if __name__ == "__main__":
    main()
