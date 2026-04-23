"""EXP-2916 — Algorithm-migration counterfactual delta.

For each patient, estimate the expected change in protection if their
load (cf_severe) and behaviour (tercile) were defended by a different
algorithm lineage.

Method:
  1. Build cell-mean protection table (lineage × tercile) from
     EXP-2891 cohort.
  2. For each patient, look up their (tercile, cf-stratum) cell mean
     under each lineage other than their own.
  3. Δ = (alternative_cell_mean) − (own_cell_mean)
  4. Translate into expected severe-rate change:
        Δ_obs_severe = (own_protection − alt_protection) × cf_severe
     (positive = migration LOSES protection; negative = migration GAINS)

Caveats:
  - Only uses verified Guard-#6 axes (1 mean protection, 6 hourly via
    cf-stratification). Assumes within-tercile homogeneity.
  - n=1-4 per cell — point estimates only. Bootstrapped SE deferred.
  - Does NOT model migration cost (config burden, hardware swap, etc).
"""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent.parent
SRC = REPO / "externals" / "experiments" / "exp-2891_simpson_dose_response.parquet"
SUMMARY = REPO / "externals" / "experiments" / "exp-2916_summary.json"
OUT_PARQUET = REPO / "externals" / "experiments" / "exp-2916_migration_delta.parquet"


def main() -> None:
    df = pd.read_parquet(SRC)
    df = df[df["lineage"] != "unknown"].copy()

    # Cell means (lineage × tercile)
    cell_means = (
        df.groupby(["lineage", "tercile"])
        .agg(cell_mean_protection=("aid_protection_severe", "mean"),
             cell_n=("patient_id", "size"))
        .reset_index()
    )

    rows = []
    for _, p in df.iterrows():
        own_lineage = p["lineage"]
        own_protection = p["aid_protection_severe"]
        cf = p["cf_severe"]
        tier = p["tercile"]

        for alt_lineage in df["lineage"].unique():
            if alt_lineage == own_lineage:
                continue
            alt_cell = cell_means[
                (cell_means["lineage"] == alt_lineage) & (cell_means["tercile"] == tier)
            ]
            if alt_cell.empty:
                continue
            alt_mean = float(alt_cell["cell_mean_protection"].iloc[0])
            alt_n = int(alt_cell["cell_n"].iloc[0])

            # Predicted obs_severe rate under each
            #   own_obs_severe = (1 - own_protection) * cf
            #   alt_obs_severe = (1 - alt_mean)       * cf
            # Migration BENEFIT (drop in severe rate) = own - alt
            #   = (alt_mean - own_protection) * cf
            # Positive => migration reduces severe events (good)
            delta_obs_severe = (alt_mean - own_protection) * cf
            rows.append({
                "patient_id": p["patient_id"],
                "own_lineage": own_lineage,
                "own_tercile": tier,
                "own_cf_severe": cf,
                "own_protection": own_protection,
                "alt_lineage": alt_lineage,
                "alt_cell_mean_protection": alt_mean,
                "alt_cell_n": alt_n,
                "delta_protection_if_migrate": alt_mean - own_protection,
                "expected_severe_rate_drop": delta_obs_severe,
                "recommend_migrate": delta_obs_severe > 0.05,
            })

    out = pd.DataFrame(rows)
    out.to_parquet(OUT_PARQUET, index=False)

    # Summary: best alternative per patient (largest expected drop in obs severe)
    best_recs = []
    for pid, g in out.groupby("patient_id"):
        best = g.sort_values("expected_severe_rate_drop", ascending=False).iloc[0]
        best_recs.append({
            "patient_id": pid,
            "own_lineage": best["own_lineage"],
            "own_tercile": best["own_tercile"],
            "own_protection": float(best["own_protection"]),
            "best_alt_lineage": best["alt_lineage"],
            "expected_severe_rate_drop": float(best["expected_severe_rate_drop"]),
            "recommend_migrate": bool(best["recommend_migrate"]),
        })
    best_df = pd.DataFrame(best_recs).sort_values("expected_severe_rate_drop", ascending=False)

    summary = {
        "n_patients": int(out["patient_id"].nunique()),
        "n_recommended_migrate": int(best_df["recommend_migrate"].sum()),
        "by_own_lineage": {
            ln: {
                "n": int((best_df["own_lineage"] == ln).sum()),
                "recommend_migrate": int(((best_df["own_lineage"] == ln) & best_df["recommend_migrate"]).sum()),
                "mean_expected_drop": float(best_df.loc[best_df["own_lineage"] == ln, "expected_severe_rate_drop"].mean()),
            }
            for ln in best_df["own_lineage"].unique()
        },
        "top10_recommended": best_df.head(10).to_dict(orient="records"),
        "bottom5_anti_recommend": best_df.tail(5).to_dict(orient="records"),
        "cell_means": cell_means.to_dict(orient="records"),
    }

    SUMMARY.write_text(json.dumps(summary, indent=2, default=str))
    print(f"[exp-2916] {SUMMARY}")
    print(json.dumps({k: v for k, v in summary.items() if k != "top10_recommended"}, indent=2, default=str))
    print("\nTop 5 recommendations:")
    print(best_df.head(5).to_string())


if __name__ == "__main__":
    main()
