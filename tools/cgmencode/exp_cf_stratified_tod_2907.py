"""EXP-2907: cf-stratified TOD x lineage.

EXP-2895 found nighttime severe-rate excess by lineage (oref0 19pp,
oref1 11pp, Loop ~0). EXP-2904 introduced the cf-conditioning guard
(Default Guard #6) — does the night degradation survive when load is
controlled for, or does it reflect overnight cf elevation that is
common across lineages?

Method:
  - Use exp-2889_event_replay (per-event cf and obs)
  - Merge lineage from exp-2891 by patient_id
  - Stratify by cf (>=0.95 vs <0.95)
  - Within each stratum, recompute TOD x lineage severe rates
  - Recompute night-day delta per lineage per stratum
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

OUT = Path("externals/experiments")
EXP_ID = "exp-2907"
CF_HIGH = 0.95


def main() -> None:
    events = pd.read_parquet(OUT / "exp-2889_event_replay.parquet")
    patients = pd.read_parquet(OUT / "exp-2891_simpson_dose_response.parquet")[
        ["patient_id", "lineage"]
    ]
    df = events.merge(patients, on="patient_id", how="inner")
    df = df[df["lineage"] != "unknown"].copy()
    df["cf_stratum"] = np.where(df["cf_severe"] >= CF_HIGH, "cf_high", "cf_low")
    tod_vals = df["tod"].unique().tolist()
    # Night = tod=='night' (exp-2881 4-bin scheme: morning/afternoon/evening/night)
    df["is_night"] = df["tod"] == "night"

    summary = {
        "exp": EXP_ID,
        "n_events": int(len(df)),
        "tod_values": tod_vals,
        "events_by_stratum": df["cf_stratum"].value_counts().to_dict(),
    }

    # Per stratum: night-day severe delta per lineage
    rows = []
    for stratum, sub in df.groupby("cf_stratum"):
        for lineage, ssub in sub.groupby("lineage"):
            night = ssub[ssub["is_night"]]
            day = ssub[~ssub["is_night"]]
            if len(night) < 5 or len(day) < 5:
                rows.append({
                    "cf_stratum": stratum,
                    "lineage": lineage,
                    "n_events": int(len(ssub)),
                    "n_night": int(len(night)),
                    "n_day": int(len(day)),
                    "night_severe_rate": None,
                    "day_severe_rate": None,
                    "night_minus_day": None,
                    "p_value": None,
                })
                continue
            ns = float(night["obs_severe"].mean())
            ds = float(day["obs_severe"].mean())
            # 2x2 chi-square: (severe vs not) x (night vs day)
            try:
                table = pd.crosstab(ssub["is_night"], ssub["obs_severe"])
                if table.shape == (2, 2):
                    chi2, p, _, _ = stats.chi2_contingency(table)
                else:
                    p = None
            except Exception:
                p = None
            rows.append({
                "cf_stratum": stratum,
                "lineage": lineage,
                "n_events": int(len(ssub)),
                "n_night": int(len(night)),
                "n_day": int(len(day)),
                "night_severe_rate": ns,
                "day_severe_rate": ds,
                "night_minus_day": ns - ds,
                "p_value": p,
            })
    summary["lineage_tod_by_cf_stratum"] = rows

    # Marginal (no stratification) for comparison
    marginal_rows = []
    for lineage, ssub in df.groupby("lineage"):
        night = ssub[ssub["is_night"]]
        day = ssub[~ssub["is_night"]]
        ns = float(night["obs_severe"].mean()) if len(night) else None
        ds = float(day["obs_severe"].mean()) if len(day) else None
        marginal_rows.append({
            "lineage": lineage,
            "n_events": int(len(ssub)),
            "night_severe_rate": ns,
            "day_severe_rate": ds,
            "night_minus_day": (ns - ds) if (ns is not None and ds is not None) else None,
        })
    summary["lineage_tod_marginal"] = marginal_rows

    (OUT / f"{EXP_ID}_summary.json").write_text(json.dumps(summary, indent=2, default=str))

    print(f"[{EXP_ID}] events n={summary['n_events']}")
    print(f"  by stratum: {summary['events_by_stratum']}")
    print()
    print("  MARGINAL (no cf conditioning):")
    for r in marginal_rows:
        nr = f"{r['night_severe_rate']:.3f}" if r['night_severe_rate'] is not None else " n/a"
        dr = f"{r['day_severe_rate']:.3f}" if r['day_severe_rate'] is not None else " n/a"
        delta = f"{r['night_minus_day']:+.3f}" if r['night_minus_day'] is not None else "  n/a "
        print(f"    {r['lineage']:18s}  n={r['n_events']:4d}  "
              f"night={nr}  day={dr}  delta={delta}")
    print()
    print("  STRATIFIED:")
    for r in rows:
        delta = f"{r['night_minus_day']:+.3f}" if r['night_minus_day'] is not None else "  n/a "
        nr = f"{r['night_severe_rate']:.3f}" if r['night_severe_rate'] is not None else " n/a"
        dr = f"{r['day_severe_rate']:.3f}" if r['day_severe_rate'] is not None else " n/a"
        pv = f"p={r['p_value']:.3f}" if r['p_value'] is not None else "  n/a"
        print(f"    {r['cf_stratum']:8s}  {r['lineage']:18s}  "
              f"n_n={r['n_night']:3d}  n_d={r['n_day']:3d}  "
              f"night={nr}  day={dr}  delta={delta}  {pv}")


if __name__ == "__main__":
    main()
