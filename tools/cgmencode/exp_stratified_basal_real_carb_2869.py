"""EXP-2869: Re-run EXP-2865 stratified basal extraction using
`time_since_real_carb_min` (resets only on carbs >= 5g) instead of
`time_since_carb_min`. Per EXP-2868, the headline cohort basal
multiplier shifts from ~0.07 to ~0.13 when noise-carb events are
excluded. This updates the audition artifact consumed by
BasalMismatchFactsLoader.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from tools.cgmencode.production.meal_filter import (
    REAL_CARB_EVENT_THRESHOLD_G,
)

GRID = REPO / "externals" / "ns-parquet" / "training" / "grid.parquet"
OUT = REPO / "externals" / "experiments"

EQUILIBRIUM_ROC = 0.5
MIN_ROWS_PER_TOD = 30
N_BOOT = 300
MISMATCH_THRESHOLD = 0.5   # P(actual/scheduled > this) --> high confidence
RNG_SEED = 2869


def _block(h: int) -> str:
    if 6 <= h < 12:
        return "morning"
    if 12 <= h < 18:
        return "afternoon"
    if 18 <= h < 24:
        return "evening"
    return "night"


def main() -> None:
    rng = np.random.default_rng(RNG_SEED)
    df = pd.read_parquet(GRID, columns=[
        "patient_id", "time", "glucose", "cob", "carbs",
        "time_since_carb_min", "time_since_bolus_min",
        "exercise_active", "override_active",
        "actual_basal_rate", "scheduled_basal_rate",
        "glucose_roc",
    ])
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.sort_values(["patient_id", "time"]).reset_index(drop=True)

    # Build time_since_real_carb_min (resets only on carbs >= threshold)
    real_event = df["carbs"].fillna(0) >= REAL_CARB_EVENT_THRESHOLD_G
    last_real_time = df["time"].where(real_event).groupby(df["patient_id"]).ffill()
    df["time_since_real_carb_min"] = (
        (df["time"] - last_real_time).dt.total_seconds() / 60.0
    )

    df = df[
        (df["cob"].fillna(0) == 0)
        & (df["time_since_real_carb_min"].fillna(1e9) >= 240)
        & (df["time_since_bolus_min"].fillna(1e9) >= 240)
        & (~df["exercise_active"].fillna(False).astype(bool))
        & (~df["override_active"].fillna(False).astype(bool))
        & df["actual_basal_rate"].notna()
        & df["scheduled_basal_rate"].notna()
        & (df["scheduled_basal_rate"] > 0)
    ]
    df = df[df["glucose_roc"].abs() <= EQUILIBRIUM_ROC]
    df["hour"] = df["time"].dt.hour
    df["tod"] = df["hour"].apply(_block)

    rows = []
    for (pid, tod), g in df.groupby(["patient_id", "tod"]):
        if len(g) < MIN_ROWS_PER_TOD:
            continue
        actual = g["actual_basal_rate"].to_numpy()
        scheduled = float(g["scheduled_basal_rate"].median())
        if scheduled <= 0:
            continue
        mults = actual / scheduled
        # bootstrap median multiplier and P(scheduled >> actual)
        idx = rng.integers(0, len(mults), size=(N_BOOT, len(mults)))
        boot_meds = np.median(mults[idx], axis=1)
        p_mismatch = float((boot_meds < MISMATCH_THRESHOLD).mean())
        rows.append({
            "patient_id": pid,
            "tod": tod,
            "n_rows": len(g),
            "median_actual_mult": float(np.median(mults)),
            "boot_med_lo": float(np.quantile(boot_meds, 0.025)),
            "boot_med_hi": float(np.quantile(boot_meds, 0.975)),
            "p_scheduled_gt_actual": p_mismatch,
            "high_mismatch": p_mismatch >= 0.9,
        })

    tod_df = pd.DataFrame(rows)
    tod_df.to_parquet(OUT / "exp-2869_per_patient_tod_basal.parquet", index=False)

    per_pat = (
        tod_df.groupby("patient_id")
        .agg(
            n_tod=("tod", "size"),
            any_high_mismatch=("high_mismatch", "sum"),
            max_mismatch_p=("p_scheduled_gt_actual", "max"),
            median_recommended_mult=("median_actual_mult", "median"),
            spread_recommended_mult=(
                "median_actual_mult",
                lambda s: float(s.max() - s.min()),
            ),
        )
        .reset_index()
    )
    per_pat.to_parquet(OUT / "exp-2869_per_patient_summary.parquet", index=False)

    summary = {
        "exp": "EXP-2869",
        "method": (
            "EXP-2865 re-run with time_since_real_carb_min (>=5g reset) "
            "replacing time_since_carb_min. Fasting+equilibrium filter, "
            "TOD stratification, bootstrap N=300."
        ),
        "n_patient_tod_buckets": len(tod_df),
        "n_patients": int(per_pat["patient_id"].nunique()),
        "n_high_mismatch_buckets": int(tod_df["high_mismatch"].sum()),
        "pct_high_mismatch": float(tod_df["high_mismatch"].mean()),
        "cohort_median_multiplier": float(per_pat["median_recommended_mult"].median()),
        "cohort_median_max_p": float(per_pat["max_mismatch_p"].median()),
    }
    with open(OUT / "exp-2869_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
