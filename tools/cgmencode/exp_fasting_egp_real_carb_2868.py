"""EXP-2868: Do EGP / fasting-window findings change when we gate carb
events to real carb events (>=5g) instead of any non-zero carb?

Prior EGP experiments (EXP-2739/2740/2757/2758) and the stratified
basal experiment (EXP-2865) all declare "fasting equilibrium" using
`time_since_carb_min >= 240`. But `time_since_carb_min` is reset by
ANY carb event, including the 30% of <5g events that EXP-2866
identified as treat-of-low / detector noise.

For messy-log patients (EXP-2866: patient `b` 79% <5g, 38/day),
noise-carb events never let `time_since_carb_min` grow to 240 min.
Those patients may have been entirely excluded from EGP/basal
findings — a coverage gap, not a value bias.

This experiment:
    1. Recompute `time_since_real_carb_min` where resets happen only
       on events with carbs >= REAL_CARB_EVENT_THRESHOLD_G (5 g).
    2. Apply the EXP-2865 fasting+equilibrium filter under both
       definitions. Compare row counts and patient coverage.
    3. For each patient, compute median net glucose drift
       (mg/dL / 5min) in fasting equilibrium — the "ISF-independent
       EGP" proxy from EXP-2758. Compare naive vs real-carb gating.
    4. Check whether `b` and `odc-39819048` gain fasting coverage.
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
OUT.mkdir(parents=True, exist_ok=True)


def _build_real_tsc(g: pd.DataFrame) -> pd.Series:
    """Per-patient: time_since_real_carb_min (resets only on carbs >= 5g)."""
    g = g.sort_values(["patient_id", "time"]).reset_index(drop=True)
    # event_time marks rows with a real-carb event
    real_event = g["carbs"] >= REAL_CARB_EVENT_THRESHOLD_G
    # last real carb time per row via forward-fill
    last_real_time = g["time"].where(real_event).groupby(g["patient_id"]).ffill()
    delta = (g["time"] - last_real_time).dt.total_seconds() / 60.0
    return delta


def main() -> None:
    g = pd.read_parquet(GRID)
    g["time"] = pd.to_datetime(g["time"], utc=True)
    g["time_since_real_carb_min"] = _build_real_tsc(g)

    # common filters
    base = (
        (g["cob"].fillna(0) == 0)
        & (g["time_since_bolus_min"].fillna(0) >= 240)
        & (g["exercise_active"].fillna(False) == False)
        & (g["override_active"].fillna(False) == False)
        & g["glucose_roc"].notna()
        & g["actual_basal_rate"].notna()
        & g["scheduled_basal_rate"].notna()
        & (g["scheduled_basal_rate"] > 0)
    )
    # equilibrium
    equil = base & (g["glucose_roc"].abs() <= 0.5)

    naive_fasting = equil & (g["time_since_carb_min"].fillna(0) >= 240)
    real_fasting = equil & (g["time_since_real_carb_min"].fillna(0) >= 240)

    def summarize(mask: pd.Series, label: str) -> dict:
        sub = g.loc[mask].copy()
        per_pat = (
            sub.groupby("patient_id")
            .agg(
                n_rows=("glucose", "size"),
                median_drift=("glucose_roc", "median"),
                median_basal_mult=(
                    "actual_basal_rate",
                    lambda s: float(
                        (s / g.loc[s.index, "scheduled_basal_rate"]).median()
                    ),
                ),
            )
            .reset_index()
        )
        return {
            "label": label,
            "n_rows": int(mask.sum()),
            "n_patients": int(sub["patient_id"].nunique()),
            "cohort_median_drift_mg_dl_per_5min": float(per_pat["median_drift"].median())
            if len(per_pat)
            else None,
            "cohort_iqr_drift": [
                float(per_pat["median_drift"].quantile(0.25))
                if len(per_pat)
                else None,
                float(per_pat["median_drift"].quantile(0.75))
                if len(per_pat)
                else None,
            ],
            "cohort_median_basal_mult": float(per_pat["median_basal_mult"].median())
            if len(per_pat)
            else None,
            "patients_covered": sorted(per_pat["patient_id"].tolist()),
            "_per_patient": per_pat,
        }

    naive = summarize(naive_fasting, "naive (any carb reset)")
    real = summarize(real_fasting, "real (>=5g reset only)")

    covered_naive = set(naive["patients_covered"])
    covered_real = set(real["patients_covered"])
    newly_covered = sorted(covered_real - covered_naive)
    lost = sorted(covered_naive - covered_real)

    # per-patient delta for patients present in both
    merged = naive["_per_patient"].merge(
        real["_per_patient"], on="patient_id", suffixes=("_naive", "_real")
    )
    merged["drift_delta"] = merged["median_drift_real"] - merged["median_drift_naive"]
    merged["basal_mult_delta"] = (
        merged["median_basal_mult_real"] - merged["median_basal_mult_naive"]
    )
    merged["row_ratio"] = merged["n_rows_real"] / merged["n_rows_naive"].clip(lower=1)

    summary = {
        "exp": "EXP-2868",
        "method": (
            "Redefine time_since_real_carb_min to reset only on carbs>="
            f"{REAL_CARB_EVENT_THRESHOLD_G}g. Apply EXP-2865 fasting+"
            "equilibrium filter. Compare cohort EGP-proxy (median drift) "
            "and basal multiplier under naive vs real-carb gating."
        ),
        "naive": {k: v for k, v in naive.items() if k != "_per_patient"},
        "real": {k: v for k, v in real.items() if k != "_per_patient"},
        "coverage": {
            "newly_covered_patients": newly_covered,
            "lost_patients": lost,
            "n_both": len(merged),
        },
        "per_patient_delta": {
            "median_drift_delta_mg_dl_per_5min": float(merged["drift_delta"].median())
            if len(merged)
            else None,
            "max_abs_drift_delta": float(merged["drift_delta"].abs().max())
            if len(merged)
            else None,
            "median_basal_mult_delta": float(merged["basal_mult_delta"].median())
            if len(merged)
            else None,
            "median_row_ratio_real_over_naive": float(merged["row_ratio"].median())
            if len(merged)
            else None,
        },
        "messy_log_patients_check": {
            "b_in_naive": "b" in covered_naive,
            "b_in_real": "b" in covered_real,
            "odc-39819048_in_naive": "odc-39819048" in covered_naive,
            "odc-39819048_in_real": "odc-39819048" in covered_real,
        },
    }

    merged.to_parquet(OUT / "exp-2868_fasting_compare.parquet", index=False)
    with open(OUT / "exp-2868_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
