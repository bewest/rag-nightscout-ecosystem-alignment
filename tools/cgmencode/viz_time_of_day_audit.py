"""Time-of-day profile audit refinement (V8: pairs with EXP-2780).

For each patient with significant S0/S1 basal coupling, decompose the
basal shift by hour-of-day window (dawn 4-9, midday 10-15,
evening 18-23, overnight 0-3 + 24). Charts:

  - Per-patient time-of-day audit (3-panel)
  - Cohort time-of-day heatmap (rows=patients, cols=hours, color=Δbasal%)

Charter: Stream B; profile-vs-actual gap; no biology numbers.
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

WINDOWS = {
    "overnight (0-3)": list(range(0, 4)),
    "dawn (4-9)":      list(range(4, 10)),
    "midday (10-15)":  list(range(10, 16)),
    "evening (16-23)": list(range(16, 24)),
}


def main():
    g = pd.read_parquet("externals/ns-parquet/training/grid.parquet")
    g["time"] = pd.to_datetime(g["time"], utc=True)
    g["hour"] = g["time"].dt.hour

    sa = pd.read_parquet(EXP / "exp-2810_state_assignments.parquet")
    sa["time"] = pd.to_datetime(sa["time"], utc=True)

    pheno = pd.read_parquet(EXP / "exp-2844_phenotype_table.parquet")
    pids = pheno["patient_id"].unique()
    g = g[g["patient_id"].isin(pids)].copy()
    sa = sa[sa["patient_id"].isin(pids)].copy()

    # Bind state to each cell
    g_sorted = g.sort_values("time").reset_index(drop=True)
    sa_sorted = sa.sort_values("time").reset_index(drop=True)
    merged = pd.merge_asof(
        g_sorted, sa_sorted[["patient_id", "time", "state"]],
        on="time", by="patient_id",
        direction="backward", tolerance=pd.Timedelta("2D"),
    ).dropna(subset=["state"])
    merged["state"] = merged["state"].astype(int)

    # Per (patient, hour, state): mean actual & scheduled basal
    g_agg = merged.groupby(["patient_id", "hour", "state"]).agg(
        actual=("actual_basal_rate", "mean"),
        sched=("scheduled_basal_rate", "mean"),
        n=("actual_basal_rate", "size"),
    ).reset_index()

    # Pivot S0/S1 to compute hourly delta basal %
    s0 = g_agg[g_agg["state"] == 0].set_index(["patient_id", "hour"])
    s1 = g_agg[g_agg["state"] == 1].set_index(["patient_id", "hour"])
    common = s0.index.intersection(s1.index)
    hourly = pd.DataFrame({
        "patient_id": [k[0] for k in common],
        "hour": [k[1] for k in common],
        "actual_s0": s0.loc[common, "actual"].values,
        "actual_s1": s1.loc[common, "actual"].values,
        "sched_s0":  s0.loc[common, "sched"].values,
    })
    hourly["delta_pct"] = (
        100.0 * (hourly["actual_s1"] - hourly["actual_s0"])
        / np.maximum(hourly["sched_s0"], 0.01)
    )

    # Cohort heatmap: rows=patients (sorted by phenotype), cols=hours
    pat_order = pheno.sort_values(
        ["phenotype", "actual_basal_shift_pct"]
    )["patient_id"].tolist()
    pivot = hourly.pivot_table(
        index="patient_id", columns="hour", values="delta_pct"
    ).reindex(pat_order)
    # Clip extreme outliers for visualization
    vmax = float(np.nanpercentile(np.abs(pivot.values), 95))
    vmax = min(vmax, 80)

    fig, ax = plt.subplots(figsize=(13, max(5, 0.35 * len(pat_order))))
    im = ax.imshow(
        pivot.values, cmap="RdBu_r", aspect="auto",
        vmin=-vmax, vmax=vmax,
    )
    ax.set_xticks(range(24))
    ax.set_xticklabels(range(24))
    ax.set_yticks(range(len(pivot.index)))
    yticklabels = []
    for pid in pivot.index:
        ph = pheno.loc[pheno["patient_id"] == pid, "phenotype"].iloc[0]
        ctrl = pheno.loc[pheno["patient_id"] == pid, "controller"].iloc[0]
        yticklabels.append(f"{pid} [{ctrl}/{ph}]")
    ax.set_yticklabels(yticklabels, fontsize=8)
    ax.set_xlabel("Hour of day (UTC)")
    ax.set_title(
        "Time-of-day basal shift heatmap (S1 − S0, % of scheduled)\n"
        "Stream B; red=S1 cuts basal; blue=S1 raises basal; "
        "rows sorted by phenotype",
        fontsize=11,
    )
    fig.colorbar(im, ax=ax, label="Δ basal % of scheduled")
    # Window separators
    for h in [4, 10, 16, 24]:
        ax.axvline(h - 0.5, color="black", lw=0.4, alpha=0.5)
    plt.tight_layout()
    out_heat = FIG / "tod_basal_heatmap_cohort.png"
    plt.savefig(out_heat, dpi=120, bbox_inches="tight")
    plt.close()
    print(f"Wrote {out_heat}")

    # Window-aggregated summary per phenotype
    def assign_window(h):
        for w, hours in WINDOWS.items():
            if h in hours:
                return w
        return None

    hourly["window"] = hourly["hour"].apply(assign_window)
    hourly = hourly.merge(
        pheno[["patient_id", "controller", "phenotype"]], on="patient_id"
    )
    summary = hourly.groupby(["phenotype", "window"]).agg(
        median_delta_pct=("delta_pct", "median"),
        n=("delta_pct", "size"),
    ).reset_index()
    summary.to_parquet(EXP / "exp-2845c_tod_summary.parquet", index=False)
    print("\nWindow-aggregated medians:")
    print(summary.to_string(index=False))

    # Window panel: bar chart per phenotype
    fig2, axes = plt.subplots(1, 3, figsize=(13, 5), sharey=True)
    for ax, ph in zip(axes, ["down_shift", "flat", "up_shift"]):
        sub = summary[summary["phenotype"] == ph]
        order = list(WINDOWS.keys())
        sub = sub.set_index("window").reindex(order).reset_index()
        bars = ax.bar(
            sub["window"], sub["median_delta_pct"],
            color={"down_shift": "#d62728", "flat": "#888888",
                   "up_shift": "#1f77b4"}.get(ph, "k"),
            alpha=0.8,
        )
        ax.axhline(0, color="k", lw=0.6)
        ax.set_title(f"{ph} (n_pts={hourly[hourly['phenotype']==ph]['patient_id'].nunique()})")
        ax.set_xticks(range(len(order)))
        ax.set_xticklabels(order, rotation=30, ha="right", fontsize=8)
        for bar, v in zip(bars, sub["median_delta_pct"].values):
            if not np.isnan(v):
                ax.text(bar.get_x() + bar.get_width()/2, v,
                        f"{v:+.0f}%", ha="center",
                        va="bottom" if v >= 0 else "top", fontsize=8)
    axes[0].set_ylabel("Median Δ basal % of scheduled")
    fig2.suptitle(
        "Time-of-day basal shift by phenotype (median across patients)\n"
        "Stream B; positive = S1 raises basal, negative = S1 cuts",
        fontsize=11,
    )
    plt.tight_layout(rect=(0, 0, 1, 0.94))
    out_panel = FIG / "tod_basal_panel_by_phenotype.png"
    plt.savefig(out_panel, dpi=120, bbox_inches="tight")
    plt.close()
    print(f"Wrote {out_panel}")


if __name__ == "__main__":
    main()
