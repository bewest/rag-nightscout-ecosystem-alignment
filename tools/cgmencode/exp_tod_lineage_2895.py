"""EXP-2895: TOD × lineage protection.

Hypothesis: does oref1's setting-independence (EXP-2891) extend to
time-of-day? Or does AID-protection degrade at certain hours for
specific lineages?

Method:
- Use EXP-2881 descent events (3,912 events with tod + controller).
- Join lineage from EXP-2891 patient table (controller -> lineage).
- For each (lineage, tod) cell, compute:
    obs_severe  = mean(bg_nadir < 54)
    cf_severe   = mean(cf_replay < 54)  -- approximated via EXP-2889
                  formula since we don't have per-event cf here.
                  Use bg_nadir + extra_drop_proxy. SIMPLER: use
                  observed severe rate by cell as the outcome and
                  ask: does the conditional severe rate vary by
                  (lineage, tod) more than (lineage) alone?
- Stratified analysis: severe rate by tod within lineage; chi-sq
  for tod-effect within each lineage.

Output: parquet of cell-level rates + per-lineage chi-sq + summary.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

EXP_ID = "exp-2895"
OUT_DIR = Path("externals/experiments")
EVENTS_PATH = Path("externals/experiments/exp-2881_evening_drivers.parquet")
LINEAGE_PATH = Path("externals/experiments/exp-2891_simpson_dose_response.parquet")

LINEAGE_BY_CONTROLLER = {
    "Loop": "Loop",
    "Trio": "oref1 (modern)",
    "OpenAPS": None,  # mixed oref0/oref1 — resolve via patient table
}


def load_events() -> pd.DataFrame:
    ev = pd.read_parquet(EVENTS_PATH)
    lin = pd.read_parquet(LINEAGE_PATH)[["patient_id", "lineage", "tercile"]]
    merged = ev.merge(lin, on="patient_id", how="inner")
    return merged


def severe_by_cell(df: pd.DataFrame) -> pd.DataFrame:
    df = df.assign(severe=(df["bg_nadir"] < 54).astype(int))
    grp = (
        df.groupby(["lineage", "tod"])
        .agg(n=("severe", "size"), severe_rate=("severe", "mean"),
             nadir_med=("bg_nadir", "median"))
        .reset_index()
    )
    return grp


def chi_sq_within_lineage(df: pd.DataFrame) -> dict:
    out = {}
    for lin, sub in df.groupby("lineage"):
        sub = sub.assign(severe=(sub["bg_nadir"] < 54).astype(int))
        ct = pd.crosstab(sub["tod"], sub["severe"])
        if ct.shape[0] >= 2 and ct.shape[1] == 2 and ct.values.min() >= 1:
            chi2, p, dof, _ = stats.chi2_contingency(ct.values)
            out[lin] = {
                "chi2": float(chi2),
                "p": float(p),
                "dof": int(dof),
                "n_events": int(sub.shape[0]),
                "tod_range_severe_rate": float(
                    sub.groupby("tod")["severe"].mean().max()
                    - sub.groupby("tod")["severe"].mean().min()
                ),
            }
    return out


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = load_events()
    cells = severe_by_cell(df)
    cells.to_parquet(OUT_DIR / f"{EXP_ID}_tod_lineage.parquet", index=False)
    chi = chi_sq_within_lineage(df)

    lineage_overall = (
        df.assign(severe=(df["bg_nadir"] < 54).astype(int))
        .groupby("lineage")["severe"].agg(["mean", "size"]).reset_index()
        .rename(columns={"mean": "severe_rate", "size": "n_events"})
    )

    summary = {
        "exp_id": EXP_ID,
        "title": "TOD x lineage severe-hypo rate",
        "n_events": int(df.shape[0]),
        "n_patients": int(df["patient_id"].nunique()),
        "lineage_overall": lineage_overall.to_dict(orient="records"),
        "tod_within_lineage_chi2": chi,
        "interpretation": (
            "If chi2 p<0.05 within a lineage, severe-hypo rate "
            "varies materially across hours of day for that lineage. "
            "If oref1 shows the smallest tod_range, the EXP-2891 "
            "setting-independence claim extends to hour-of-day. "
            "Large tod_range for Loop/oref0 indicates dawn or "
            "evening protection-degradation by lineage."
        ),
    }

    out_json = OUT_DIR / f"{EXP_ID}_summary.json"
    out_json.write_text(json.dumps(summary, indent=2, default=str))

    print(f"Wrote {out_json}")
    print(json.dumps(summary, indent=2, default=str))
    print("\nCell rates:")
    print(cells.to_string(index=False))


if __name__ == "__main__":
    main()
