"""EXP-2898: counter-regulation intercept by lineage.

Joins EXP-2875 per-patient counter-reg intercept with EXP-2891 lineage.

Hypothesis: oref1 SMB capability could over-correct after rebound,
producing higher counter_reg_intercept variance or lower mean intercept
(faster correction = faster recovery, but possibly stacking).

Test: compare intercept distribution by lineage. Look at:
  - Mean / median intercept (recovery rise rate, mg/dL/min)
  - Variance / IQR (consistency)
  - Correlation with frac_smb (EXP-2893) — does more SMB correlate
    with smaller (less over-shoot) or larger (faster recovery) intercept?
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

OUT = Path("externals/experiments")
EXP_ID = "exp-2898"


def main() -> None:
    p = pd.read_parquet(OUT / "exp-2875_per_patient.parquet")
    lin = pd.read_parquet(OUT / "exp-2891_simpson_dose_response.parquet")[
        ["patient_id", "lineage", "tercile"]
    ]
    smb = pd.read_parquet(OUT / "exp-2893_hyper_channels.parquet")[
        ["patient_id", "frac_smb", "frac_user", "frac_excess_basal"]
    ]
    df = p.merge(lin, on="patient_id", how="left").merge(smb, on="patient_id", how="left")

    by_lineage = (
        df.dropna(subset=["lineage"])
        .groupby("lineage")
        .agg(
            n=("intercept", "size"),
            median_intercept=("intercept", "median"),
            mean_intercept=("intercept", "mean"),
            iqr_intercept=("intercept", lambda s: float(s.quantile(0.75) - s.quantile(0.25))),
            median_frac_smb=("frac_smb", "median"),
        )
        .reset_index()
    )

    # Kruskal-Wallis across lineages
    groups = [
        sub["intercept"].dropna().values
        for _, sub in df.dropna(subset=["lineage"]).groupby("lineage")
    ]
    if len(groups) >= 2:
        kruskal = stats.kruskal(*groups)
        kruskal_out = {"H": float(kruskal.statistic), "p": float(kruskal.pvalue)}
    else:
        kruskal_out = None

    # Spearman: intercept vs frac_smb
    sub = df.dropna(subset=["intercept", "frac_smb"])
    if len(sub) >= 3:
        rho, p_rho = stats.spearmanr(sub["intercept"], sub["frac_smb"])
        smb_corr = {
            "rho": float(rho),
            "p": float(p_rho),
            "n": int(len(sub)),
        }
    else:
        smb_corr = None

    summary = {
        "exp_id": EXP_ID,
        "title": "Counter-regulation intercept by lineage",
        "n_patients": int(df["patient_id"].nunique()),
        "by_lineage": by_lineage.to_dict("records"),
        "kruskal_intercept_across_lineage": kruskal_out,
        "intercept_vs_frac_smb": smb_corr,
        "interpretation": (
            "If lineage Kruskal p<0.05, recovery rate differs across "
            "algorithm families. Spearman vs frac_smb tells whether "
            "SMB delivery accelerates (positive rho) or moderates "
            "(negative rho) post-nadir recovery."
        ),
    }
    out = OUT / f"{EXP_ID}_summary.json"
    out.write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
