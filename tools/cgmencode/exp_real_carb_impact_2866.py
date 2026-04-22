"""EXP-2866 — Impact of small-carb-event noise on basal extraction.

Sanity check on user concern: median carb event in the cohort is 15g
and 30% of events are <5g. Patients b (79% small) and odc-39819048
(83% small) have implausibly many "meals" per day. Question: does
treating <5g events as noise (not real meals) materially change the
EXP-2865 clean-fasting filter and the basal mismatch conclusion?

Method:
1. For each row, compute `time_since_real_carb_min` by ignoring
   carb events with `carbs < 5g`.
2. Re-run EXP-2865's clean-fasting + equilibrium filter using the
   stricter "real-carb" definition.
3. Per-patient: how many additional fasting rows? does the
   per-patient median basal mismatch change?
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
EXPDIR = REPO / "externals" / "experiments"
GRID = REPO / "externals" / "ns-parquet" / "training" / "grid.parquet"

REAL_CARB_THRESHOLD_G = 5.0
EQUILIBRIUM_ROC = 0.5
MIN_ROWS = 30


def main() -> None:
    df = pd.read_parquet(GRID, columns=[
        "patient_id", "time", "carbs", "cob",
        "time_since_carb_min", "time_since_bolus_min",
        "exercise_active", "override_active",
        "actual_basal_rate", "scheduled_basal_rate",
        "glucose_roc",
    ])

    # Recompute time_since_real_carb_min ignoring <5g events.
    df = df.sort_values(["patient_id", "time"]).reset_index(drop=True)
    df["is_real_carb"] = (df["carbs"].fillna(0) >= REAL_CARB_THRESHOLD_G)

    parts = []
    for pid, g in df.groupby("patient_id", sort=False):
        g = g.copy()
        g["t"] = pd.to_datetime(g["time"]).astype("int64") / 60_000_000_000  # minutes
        last_carb_t = np.where(g["is_real_carb"], g["t"], np.nan)
        # forward-fill last real-carb time, then minutes since.
        s = pd.Series(last_carb_t).ffill().to_numpy()
        g["time_since_real_carb_min"] = (g["t"].to_numpy() - s)
        parts.append(g.drop(columns=["t"]))
    df = pd.concat(parts, ignore_index=True)

    # Original clean-fasting (uses time_since_carb_min).
    orig = df[
        (df["cob"].fillna(0) == 0)
        & (df["time_since_carb_min"].fillna(1e9) >= 240)
        & (df["time_since_bolus_min"].fillna(1e9) >= 240)
        & (~df["exercise_active"].fillna(False).astype(bool))
        & (~df["override_active"].fillna(False).astype(bool))
        & df["actual_basal_rate"].notna()
        & df["scheduled_basal_rate"].notna()
        & (df["glucose_roc"].abs() <= EQUILIBRIUM_ROC)
    ]

    # Real-carb clean-fasting (uses time_since_real_carb_min, which can
    # legitimately be NaN at the head before any real carb event — keep
    # those rows as fasting).
    real = df[
        (df["cob"].fillna(0) == 0)
        & ((df["time_since_real_carb_min"].fillna(1e9) >= 240))
        & (df["time_since_bolus_min"].fillna(1e9) >= 240)
        & (~df["exercise_active"].fillna(False).astype(bool))
        & (~df["override_active"].fillna(False).astype(bool))
        & df["actual_basal_rate"].notna()
        & df["scheduled_basal_rate"].notna()
        & (df["glucose_roc"].abs() <= EQUILIBRIUM_ROC)
    ]

    per_p_orig = orig.groupby("patient_id").size().rename("n_orig")
    per_p_real = real.groupby("patient_id").size().rename("n_real")
    per_p = pd.concat([per_p_orig, per_p_real], axis=1).fillna(0).astype(int)
    per_p["delta"] = per_p["n_real"] - per_p["n_orig"]
    per_p["pct_delta"] = (per_p["delta"] / per_p["n_orig"].replace(0, np.nan) * 100).round(1)

    # Per-patient basal mismatch (single-pool, no TOD here for compactness).
    def _mismatch(grp):
        if len(grp) < MIN_ROWS:
            return np.nan
        med = float(grp["actual_basal_rate"].median())
        sched = float(grp["scheduled_basal_rate"].median())
        if sched <= 0:
            return np.nan
        return med / sched

    mult_orig = orig.groupby("patient_id").apply(_mismatch).rename("mult_orig")
    mult_real = real.groupby("patient_id").apply(_mismatch).rename("mult_real")
    per_p = per_p.join(mult_orig).join(mult_real)
    per_p["mult_change_pct"] = (
        (per_p["mult_real"] - per_p["mult_orig"]) / per_p["mult_orig"] * 100
    ).round(1)

    per_p = per_p.reset_index().sort_values("delta", ascending=False)
    per_p.to_parquet(EXPDIR / "exp-2866_real_carb_impact.parquet", index=False)

    summary = {
        "exp": "EXP-2866",
        "method": (
            f"Recomputed time_since_real_carb_min ignoring carb events "
            f"<{REAL_CARB_THRESHOLD_G}g. Compared EXP-2865 clean-fasting + "
            "equilibrium filter row counts and per-patient basal multiplier "
            "between original and real-carb-only definitions."
        ),
        "rows_clean_fasting_orig": int(len(orig)),
        "rows_clean_fasting_real_carb": int(len(real)),
        "delta_rows": int(len(real) - len(orig)),
        "pct_increase": float(round(100*(len(real)-len(orig))/max(len(orig),1), 1)),
        "n_patients": int(per_p.shape[0]),
        "n_patients_with_increase": int((per_p["delta"] > 0).sum()),
        "patient_b_n_orig": int(per_p[per_p["patient_id"]=="b"]["n_orig"].iloc[0])
            if "b" in per_p["patient_id"].values else None,
        "patient_b_n_real": int(per_p[per_p["patient_id"]=="b"]["n_real"].iloc[0])
            if "b" in per_p["patient_id"].values else None,
        "median_mult_change_pct": float(per_p["mult_change_pct"].median()) if per_p["mult_change_pct"].notna().any() else None,
        "max_mult_change_pct": float(per_p["mult_change_pct"].abs().max()) if per_p["mult_change_pct"].notna().any() else None,
    }
    (EXPDIR / "exp-2866_summary.json").write_text(json.dumps(summary, indent=2))

    print(json.dumps(summary, indent=2))
    print()
    print("Top 10 patients by row-count change:")
    print(per_p.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
