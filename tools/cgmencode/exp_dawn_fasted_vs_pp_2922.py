"""EXP-2922 - Loop dawn-hyper post-prandial vs basal-fasted decomposition.

Tests whether Loop's 03:00 dawn-hyperglycemia signature
(EXP-2920/2921) is genuine EGP-driven (present in fasted cells)
or carry-over from late-evening meals.

Method:
  - Per Loop patient, classify each cell as:
      FASTED:        time_since_carb_min >= 300 (>5h since carbs)
      POST_PRANDIAL: time_since_carb_min <= 180 (<=3h)
      MID:           180-300 (excluded)
  - Per (patient, hour, state), compute frac_hyper = mean(glucose>250).
  - Patient-mean within (autobolus, hour, state) before pooling.
  - Compare 03:00-04:00 fasted vs post-prandial.

Scope: design-feature characterisation. AID-author audience.
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
OUT_J = REPO / "externals" / "experiments" / "exp-2922_summary.json"
PNG = REPO / "docs" / "visualizations" / "exp-2922-dawn-fasted-vs-pp.png"

RNG = np.random.default_rng(2922)
N_BOOT = 2000
HYPER = 250
HYPO = 54
LOOP_AUTOBOLUS_OFF = {"a", "f"}
LOOP_AUTOBOLUS_ON = {"c", "d", "e", "g", "i"}


def boot_ci(values: np.ndarray) -> tuple[float, float]:
    if len(values) < 2:
        v = float(values[0]) if len(values) == 1 else float("nan")
        return v, v
    samples = RNG.choice(values, size=(N_BOOT, len(values)), replace=True).mean(axis=1)
    return float(np.percentile(samples, 2.5)), float(np.percentile(samples, 97.5))


def main() -> None:
    print("[exp-2922] loading lineage")
    simp = pd.read_parquet(SIMP, columns=["patient_id", "lineage"])
    loop_pids = set(simp[simp["lineage"] == "Loop (iOS)"]["patient_id"])

    print("[exp-2922] loading grid (Loop only)")
    grid = pd.read_parquet(GRID, columns=["patient_id", "time", "glucose", "time_since_carb_min"])
    grid = grid[grid["patient_id"].isin(loop_pids)].dropna(subset=["glucose"])

    grid["hour"] = grid["time"].dt.hour
    grid["state"] = np.where(
        grid["time_since_carb_min"] >= 300, "FASTED",
        np.where(grid["time_since_carb_min"] <= 180, "POST_PRANDIAL", "MID")
    )
    grid = grid[grid["state"] != "MID"]

    rows = []
    for (pid, hr, st), sub in grid.groupby(["patient_id", "hour", "state"]):
        if len(sub) < 6:
            continue
        rows.append({
            "patient_id": pid, "hour": int(hr), "state": st,
            "n_cells": len(sub),
            "frac_hyper": float((sub["glucose"] > HYPER).mean()),
            "frac_hypo": float((sub["glucose"] < HYPO).mean()),
        })
    pat = pd.DataFrame(rows)
    pat["autobolus"] = pat["patient_id"].map(
        lambda p: "ON" if p in LOOP_AUTOBOLUS_ON else ("OFF" if p in LOOP_AUTOBOLUS_OFF else None)
    )
    pat = pat.dropna(subset=["autobolus"])

    cells = []
    for ab in ["OFF", "ON"]:
        for st in ["FASTED", "POST_PRANDIAL"]:
            for hr in range(24):
                sub = pat[(pat["autobolus"] == ab) & (pat["state"] == st) & (pat["hour"] == hr)]
                n_pat = sub["patient_id"].nunique()
                if n_pat == 0:
                    continue
                pm_y = sub.groupby("patient_id")["frac_hyper"].mean().values
                lo, hi = boot_ci(pm_y)
                cells.append({
                    "autobolus": ab, "state": st, "hour": hr, "n_patients": int(n_pat),
                    "mean_frac_hyper": float(pm_y.mean()),
                    "ci_lo": lo, "ci_hi": hi,
                })
    df = pd.DataFrame(cells)

    summary = {
        "scope": "Loop dawn-hyper decomposition (fasted vs post-prandial); AID-author scope",
        "hourly_cells": df.to_dict(orient="records"),
    }
    OUT_J.write_text(json.dumps(summary, indent=2, default=str))

    # Headline at 03:00-04:00
    print("\n=== Loop 03:00-04:00 hyper by state x autobolus ===")
    for ab in ["OFF", "ON"]:
        for st in ["FASTED", "POST_PRANDIAL"]:
            sub = df[(df["autobolus"] == ab) & (df["state"] == st) & (df["hour"].isin([3, 4]))]
            if sub.empty:
                continue
            print(f"  autobolus {ab} / {st}: hr3 hyper={sub[sub.hour==3]['mean_frac_hyper'].mean()*100:.2f}%, "
                  f"hr4 hyper={sub[sub.hour==4]['mean_frac_hyper'].mean()*100:.2f}%, "
                  f"n_patients={sub['n_patients'].max()}")

    # 4-line plot
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), sharey=True)
    state_color = {"FASTED": "#7f7f7f", "POST_PRANDIAL": "#ff7f0e"}
    for ax, ab in zip(axes, ["OFF", "ON"]):
        for st in ["FASTED", "POST_PRANDIAL"]:
            sub = df[(df["autobolus"] == ab) & (df["state"] == st)].sort_values("hour")
            if sub.empty:
                continue
            n = sub["n_patients"].iloc[0]
            ax.plot(sub["hour"], sub["mean_frac_hyper"] * 100, "o-",
                    color=state_color[st], label=f"{st} (n={n})")
            ax.fill_between(sub["hour"], sub["ci_lo"] * 100, sub["ci_hi"] * 100,
                            color=state_color[st], alpha=0.15)
        ax.set_title(f"Loop autobolus {ab}")
        ax.set_xlabel("Hour of day")
        ax.set_xticks(range(0, 24, 3))
        ax.grid(alpha=0.3); ax.legend()
    axes[0].set_ylabel("% cells > 250 mg/dL")
    fig.suptitle("Loop dawn-hyper decomposed: fasted (>5h since carbs) vs post-prandial (<=3h)\n"
                 "95% bootstrap CI; AID-author scope", fontsize=11)
    plt.tight_layout()
    plt.savefig(PNG, dpi=150)
    print(f"[exp-2922] {PNG}")


if __name__ == "__main__":
    main()
