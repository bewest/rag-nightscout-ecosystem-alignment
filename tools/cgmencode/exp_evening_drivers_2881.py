"""EXP-2881 — Characterize evening hypo drivers.

EXP-2880 found evening (18-24 UTC) descent is fastest (-0.77 mg/dL/min).
Hypothesis: evening hypos are driven by bolus stacking (multiple
dinner-time/post-dinner corrections + extended-effect residuals).

Tests:
  1. Time since last bolus at nadir — evening should be shorter
  2. 4-hour cumulative bolus pre-nadir — evening should be larger
  3. IOB at start of descent window — evening should be higher
  4. Scheduled basal rate — evening basal may be similar across TOD,
     so a basal-profile mis-tune hypothesis is ruled out/in

Approach: re-detect events, enrich with 4h bolus cumulative and
time_since_bolus features, compare across TOD with Mann-Whitney.

Output: exp-2881_evening_drivers.parquet + summary + figure.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.cgmencode.exp_counter_regulation_2875 import (  # noqa: E402
    detect_hypo_recovery_events,
)

GRID = ROOT / "externals/ns-parquet/training/grid.parquet"
OUT = ROOT / "externals/experiments/exp-2881_evening_drivers.parquet"
OUT_SUMMARY = ROOT / "externals/experiments/exp-2881_evening_drivers_summary.json"
OUT_FIG = ROOT / "docs/60-research/figures/exp-2881_evening_drivers.png"

TOD_BINS = [
    ("night", 0, 6),
    ("morning", 6, 12),
    ("afternoon", 12, 18),
    ("evening", 18, 24),
]
PRE_WINDOW_MIN = 60
BOLUS_WINDOW_MIN = 240  # 4h cumulative


def classify_tod(hour: int) -> str:
    for name, lo, hi in TOD_BINS:
        if lo <= hour < hi:
            return name
    return "unknown"


def enrich(g_pat: pd.DataFrame, ev: dict) -> dict | None:
    nadir = ev["nadir_idx"]
    n = len(g_pat)
    cells_back = PRE_WINDOW_MIN // 5
    bolus_cells = BOLUS_WINDOW_MIN // 5

    start = nadir - cells_back
    if start < 0:
        return None
    bolus_start = max(0, nadir - bolus_cells)

    bg_nadir = float(g_pat["glucose"].iloc[nadir])
    bg_start = float(g_pat["glucose"].iloc[start])
    if np.isnan(bg_nadir) or np.isnan(bg_start):
        return None

    pre_slice = g_pat.iloc[start:nadir + 1]
    if pre_slice["carbs"].fillna(0).sum() > 0:
        return None

    # 4h bolus cumulative
    bolus_4h = float(
        g_pat["bolus"].iloc[bolus_start:nadir + 1].fillna(0).sum()
    )
    # time since last bolus
    bolus_series = g_pat["bolus"].iloc[:nadir + 1].fillna(0)
    nonzero_idx = np.where(bolus_series.values > 0)[0]
    if len(nonzero_idx):
        last_bolus_idx = nonzero_idx[-1]
        time_since_bolus = (nadir - last_bolus_idx) * 5.0  # minutes
        last_bolus_size = float(bolus_series.iloc[last_bolus_idx])
    else:
        time_since_bolus = float("nan")
        last_bolus_size = 0.0

    iob_start = float(pre_slice["iob"].iloc[0])
    iob_nadir = float(pre_slice["iob"].iloc[-1])
    sched_basal = float(pre_slice["scheduled_basal_rate"].mean())
    actual_basal = float(pre_slice["actual_basal_rate"].mean())

    descent_slope = (bg_nadir - bg_start) / PRE_WINDOW_MIN

    nadir_time = g_pat["time"].iloc[nadir]
    hour = int(nadir_time.hour)

    return {
        "bg_start": bg_start,
        "bg_nadir": bg_nadir,
        "descent_slope": descent_slope,
        "bolus_4h": bolus_4h,
        "time_since_bolus_min": time_since_bolus,
        "last_bolus_size": last_bolus_size,
        "iob_start": iob_start,
        "iob_nadir": iob_nadir,
        "sched_basal": sched_basal,
        "actual_basal": actual_basal,
        "nadir_hour": hour,
        "tod": classify_tod(hour),
    }


def main() -> None:
    print("Loading grid...")
    grid = pd.read_parquet(GRID)
    grid["time"] = pd.to_datetime(grid["time"], utc=True)

    rows = []
    for pid in grid.patient_id.unique():
        g_pat = grid[grid.patient_id == pid].sort_values("time").reset_index(drop=True).copy()
        for ev in detect_hypo_recovery_events(g_pat):
            r = enrich(g_pat, ev)
            if r is None:
                continue
            r["patient_id"] = pid
            rows.append(r)
    df = pd.DataFrame(rows)
    print(f"  events={len(df)}")

    ev_2875 = pd.read_parquet(
        ROOT / "externals/experiments/exp-2875_counter_regulation_events.parquet"
    )
    pat_ctrl = ev_2875.drop_duplicates("patient_id").set_index("patient_id").controller
    df["controller"] = df.patient_id.map(pat_ctrl)

    df.to_parquet(OUT)

    features = [
        "bolus_4h", "time_since_bolus_min", "last_bolus_size",
        "iob_start", "iob_nadir", "sched_basal", "descent_slope",
    ]

    summary = {"exp_id": "2881", "n_events": int(len(df)), "per_tod": {}}
    for name, _, _ in TOD_BINS:
        sub = df[df.tod == name]
        summary["per_tod"][name] = {
            "n": int(len(sub)),
            **{f"{f}_median": float(sub[f].median()) for f in features},
            **{f"{f}_mean": float(sub[f].mean()) for f in features},
        }

    # Print table
    print("\nPer-TOD medians:")
    header = f"{'feat':20s}" + "".join(f"{n:>12s}" for n, _, _ in TOD_BINS)
    print(header)
    for f in features:
        line = f"{f:20s}"
        for name, _, _ in TOD_BINS:
            v = summary["per_tod"][name][f"{f}_median"]
            line += f"{v:>12.3f}"
        print(line)

    # Evening vs other Mann-Whitney tests
    evening_mask = df.tod == "evening"
    summary["evening_vs_rest"] = {}
    for f in features:
        ev_vals = df.loc[evening_mask, f].dropna().values
        rest_vals = df.loc[~evening_mask, f].dropna().values
        if len(ev_vals) < 10 or len(rest_vals) < 10:
            continue
        u, p = stats.mannwhitneyu(ev_vals, rest_vals, alternative="two-sided")
        diff_median = float(np.median(ev_vals) - np.median(rest_vals))
        summary["evening_vs_rest"][f] = {
            "evening_median": float(np.median(ev_vals)),
            "rest_median": float(np.median(rest_vals)),
            "diff_median": diff_median,
            "mannwhitney_u": float(u),
            "mannwhitney_p": float(p),
        }

    print("\nEvening vs rest (two-sided Mann-Whitney):")
    for f, r in summary["evening_vs_rest"].items():
        print(
            f"  {f:22s} ev={r['evening_median']:+.3f} "
            f"rest={r['rest_median']:+.3f} diff={r['diff_median']:+.3f} "
            f"p={r['mannwhitney_p']:.2g}"
        )

    # Figure: 4-panel boxplots of key features by TOD
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    axes = axes.flatten()
    panel_specs = [
        ("bolus_4h", "4h cumulative bolus (U)"),
        ("time_since_bolus_min", "Time since last bolus (min)"),
        ("iob_start", "IOB at descent start (U)"),
        ("descent_slope", "Descent slope (mg/dL/min)"),
    ]
    tod_names = [n for n, _, _ in TOD_BINS]
    colors = ["#1f3b5f", "#d99133", "#3d8a5f", "#6d3d8f"]
    for ax, (f, label) in zip(axes, panel_specs):
        data = [df[df.tod == n][f].dropna().values for n in tod_names]
        bp = ax.boxplot(
            data, labels=tod_names, showfliers=False, patch_artist=True
        )
        for patch, c in zip(bp["boxes"], colors):
            patch.set_facecolor(c)
            patch.set_alpha(0.6)
        ax.set_ylabel(label)
        ax.grid(axis="y", alpha=0.3)
        if f in summary["evening_vs_rest"]:
            p = summary["evening_vs_rest"][f]["mannwhitney_p"]
            ax.set_title(f"{label}  (evening vs rest p={p:.2g})", fontsize=10)

    fig.suptitle(
        "EXP-2881 — Evening Hypo Drivers: Bolus Stacking vs Basal",
        fontsize=13,
    )
    fig.tight_layout()
    OUT_FIG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_FIG, dpi=110)
    plt.close(fig)

    # Verdict: evening bolus stacking = higher bolus_4h AND/OR shorter time_since_bolus
    # AND/OR higher iob_start, all in evening vs rest
    b4 = summary["evening_vs_rest"].get("bolus_4h", {})
    tsb = summary["evening_vs_rest"].get("time_since_bolus_min", {})
    iob = summary["evening_vs_rest"].get("iob_start", {})
    sched = summary["evening_vs_rest"].get("sched_basal", {})

    bolus_stacking_evidence = 0
    notes = []
    if b4 and b4["diff_median"] > 0.2 and b4["mannwhitney_p"] < 0.05:
        bolus_stacking_evidence += 1
        notes.append(
            f"4h bolus higher in evening (+{b4['diff_median']:.2f}U, p={b4['mannwhitney_p']:.2g})"
        )
    if tsb and tsb["diff_median"] < -15 and tsb["mannwhitney_p"] < 0.05:
        bolus_stacking_evidence += 1
        notes.append(
            f"Time-since-bolus shorter in evening ({tsb['diff_median']:+.0f} min, p={tsb['mannwhitney_p']:.2g})"
        )
    if iob and iob["diff_median"] > 0.1 and iob["mannwhitney_p"] < 0.05:
        bolus_stacking_evidence += 1
        notes.append(
            f"IOB higher at evening descent start (+{iob['diff_median']:.2f}U, p={iob['mannwhitney_p']:.2g})"
        )

    basal_mistune = False
    if sched and abs(sched["diff_median"]) > 0.05 and sched["mannwhitney_p"] < 0.01:
        basal_mistune = True
        notes.append(
            f"Scheduled basal also differs (diff={sched['diff_median']:+.3f}U/h, p={sched['mannwhitney_p']:.2g})"
        )

    if bolus_stacking_evidence >= 2 and not basal_mistune:
        verdict = (
            f"EVENING HYPOS ARE BOLUS-STACKING — {bolus_stacking_evidence}/3 "
            f"stacking features significantly elevated in evening vs rest. "
            f"Basal profile is similar across TOD. Actionable: reduce "
            f"dinner/post-dinner bolus aggression or enforce min-time-"
            f"between-boluses guard.\n\nEvidence: " + "; ".join(notes)
        )
    elif bolus_stacking_evidence >= 2 and basal_mistune:
        verdict = (
            f"EVENING HYPOS ARE MIXED — {bolus_stacking_evidence}/3 bolus "
            "stacking features elevated AND evening basal differs. Both "
            "levers contribute.\n\n" + "; ".join(notes)
        )
    elif basal_mistune and bolus_stacking_evidence < 2:
        verdict = (
            "EVENING HYPOS ARE BASAL-DRIVEN — insufficient bolus-stacking "
            f"signal, but basal differs across TOD ({sched['diff_median']:+.3f}). "
            "Actionable: review evening basal profile."
        )
    else:
        verdict = (
            f"EVENING HYPOS NOT CLEARLY EXPLAINED — bolus-stacking evidence "
            f"{bolus_stacking_evidence}/3, basal mistune {basal_mistune}. "
            "Other factors (delayed meals, exercise, sensor artifacts?) may "
            "contribute."
        )

    summary["verdict"] = verdict
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2))
    print(f"\nVerdict: {verdict}")


if __name__ == "__main__":
    main()
