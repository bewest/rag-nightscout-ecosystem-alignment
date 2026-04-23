"""EXP-2897: hourly counterfactual replay by lineage.

Extends EXP-2889 mechanism to per-hour cells. For each (lineage, hour)
cell, computes:

  obs_severe = P(observed nadir < 54)
  cf_severe  = P(replay nadir < 54)  using basal-deficit -> extra-drop
  protection = cf_severe - obs_severe

Question: at the worst observed hours per lineage (EXP-2896), is the
AID actually preventing more events (high protection at those hours),
or is it absent (low protection AND high cf_severe)?

The contrast is diagnostic:
- HIGH cf_severe AND HIGH protection -> AID is doing heavy lifting at
  this hour; physiology is genuinely difficult.
- HIGH cf_severe AND LOW protection -> AID is failing at this hour
  (algorithm gap).
- LOW cf_severe AND HIGH obs_severe -> something other than basal
  inertia is driving the night problem (rare; likely sensor or rebound).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

EXP_ID = "exp-2897"
OUT = Path("externals/experiments")
ISF_POP = 50.0


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    ev = pd.read_parquet(OUT / "exp-2881_evening_drivers.parquet")
    lin = pd.read_parquet(OUT / "exp-2891_simpson_dose_response.parquet")[
        ["patient_id", "lineage"]
    ]
    df = ev.merge(lin, on="patient_id", how="inner")
    df = df[(df["descent_slope"] < -0.05) & (df["bg_nadir"] < df["bg_start"])].copy()

    df["duration_min"] = (
        (df["bg_start"] - df["bg_nadir"]) / (-df["descent_slope"])
    ).clip(lower=5, upper=240)
    df["basal_deficit_uh"] = (
        (df["sched_basal"] - df["actual_basal"]).clip(lower=0)
    )
    df["extra_insulin_u"] = df["basal_deficit_uh"] * df["duration_min"] / 60.0
    df["extra_drop_mgdl"] = df["extra_insulin_u"] * ISF_POP
    df["cf_nadir"] = df["bg_nadir"] - df["extra_drop_mgdl"]
    df["obs_severe"] = (df["bg_nadir"] < 54).astype(int)
    df["cf_severe"] = (df["cf_nadir"] < 54).astype(int)

    cells = (
        df.groupby(["lineage", "nadir_hour"])
        .agg(
            n=("obs_severe", "size"),
            obs=("obs_severe", "mean"),
            cf=("cf_severe", "mean"),
            mean_deficit=("basal_deficit_uh", "mean"),
        )
        .reset_index()
    )
    cells["protection"] = cells["cf"] - cells["obs"]
    cells.to_parquet(OUT / f"{EXP_ID}_hourly_cf.parquet", index=False)

    # Worst-hour diagnostic per lineage
    diag = {}
    for lname in ["Loop (iOS)", "oref0 (legacy)", "oref1 (modern)"]:
        sub = cells[(cells["lineage"] == lname) & (cells["n"] >= 8)]
        if sub.empty:
            continue
        worst_obs = sub.sort_values("obs", ascending=False).head(3)
        diag[lname] = {
            "worst_obs_hours": worst_obs[
                ["nadir_hour", "n", "obs", "cf", "protection"]
            ].to_dict("records"),
            "median_protection": float(sub["protection"].median()),
            "median_cf": float(sub["cf"].median()),
            "median_obs": float(sub["obs"].median()),
        }

    summary = {
        "exp_id": EXP_ID,
        "title": "Hourly counterfactual protection by lineage",
        "n_events": int(df.shape[0]),
        "isf_pop": ISF_POP,
        "diagnostic_per_lineage": diag,
        "interpretation": (
            "Per worst hour: HIGH cf + HIGH protection => physiology "
            "load (AID earning its keep). HIGH cf + LOW protection "
            "=> algorithm gap at that hour."
        ),
    }
    out = OUT / f"{EXP_ID}_summary.json"
    out.write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
