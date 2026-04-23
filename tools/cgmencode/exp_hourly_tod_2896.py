"""EXP-2896: hourly resolution of TOD x lineage protection.

Refines EXP-2895's 4-bin TOD into 24 hourly bins. Identifies the exact
hour(s) where oref0/oref1 night-degradation begins and ends. Useful
for overnight-basal recommendations and for setting per-hour thresholds
in the audition matrix.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

EXP_ID = "exp-2896"
OUT_DIR = Path("externals/experiments")
EVENTS = Path("externals/experiments/exp-2881_evening_drivers.parquet")
LIN = Path("externals/experiments/exp-2891_simpson_dose_response.parquet")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ev = pd.read_parquet(EVENTS)
    lin = pd.read_parquet(LIN)[["patient_id", "lineage"]]
    df = ev.merge(lin, on="patient_id", how="inner")
    df["severe"] = (df["bg_nadir"] < 54).astype(int)

    by_hr = (
        df.groupby(["lineage", "nadir_hour"])
        .agg(n=("severe", "size"), severe_rate=("severe", "mean"))
        .reset_index()
    )
    # Pivot for readability
    pivot = by_hr.pivot(index="nadir_hour", columns="lineage",
                        values="severe_rate")
    counts = by_hr.pivot(index="nadir_hour", columns="lineage", values="n")

    by_hr.to_parquet(OUT_DIR / f"{EXP_ID}_hourly.parquet", index=False)

    # Per-lineage daytime (8-22) vs nighttime (22-8) excess
    daynight = {}
    for lin_name, sub in df.groupby("lineage"):
        if lin_name == "unknown":
            continue
        night_mask = (sub["nadir_hour"] >= 22) | (sub["nadir_hour"] < 8)
        day_mask = (sub["nadir_hour"] >= 8) & (sub["nadir_hour"] < 22)
        n_rate = float(sub.loc[night_mask, "severe"].mean())
        d_rate = float(sub.loc[day_mask, "severe"].mean())
        n_n = int(night_mask.sum())
        n_d = int(day_mask.sum())
        # Worst hour
        worst = (
            sub.groupby("nadir_hour")["severe"].agg(["mean", "size"])
            .query("size >= 5")
            .sort_values("mean", ascending=False)
            .head(3)
        )
        daynight[lin_name] = {
            "night_rate": n_rate,
            "day_rate": d_rate,
            "excess": n_rate - d_rate,
            "n_night": n_n,
            "n_day": n_d,
            "top3_worst_hours": worst.reset_index().to_dict("records"),
        }

    summary = {
        "exp_id": EXP_ID,
        "title": "Hourly TOD x lineage severe-hypo rates",
        "n_events": int(df.shape[0]),
        "lineage_daynight": daynight,
        "method": (
            "Day window 08:00-22:00, night 22:00-08:00. Worst hours "
            "filtered to bins with >=5 events."
        ),
    }
    out_json = OUT_DIR / f"{EXP_ID}_summary.json"
    out_json.write_text(json.dumps(summary, indent=2, default=str))

    print(json.dumps(summary, indent=2, default=str))
    print("\nHourly severe-rate matrix (rows=hour, cols=lineage):")
    print(pivot.round(3).to_string())
    print("\nEvent counts:")
    print(counts.to_string())


if __name__ == "__main__":
    main()
