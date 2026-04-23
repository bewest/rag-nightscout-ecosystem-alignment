"""EXP-2912 — cf-conditioned counter-reg moderation (axis 7 re-grade).

EXP-2898 found Kruskal p=0.037 across lineages on counter-reg
intercept, with rho(frac_smb, intercept) = -0.43 — interpreted as
"rapid recovery is a LAGGING indicator of upstream AID failure".

Default Guard #6 requires cf-conditioning. This experiment fits per-
patient:
  intercept ~ lineage + cf_severe
where cf_severe is taken from EXP-2891 per-patient summary as the
load-intensity proxy.

If oref0's elevated intercept is mediated by upstream load-saturated
events (high cf), the lineage effect should attenuate strongly under
cf-conditioning. If it persists, oref0 patients have rapid recovery
independent of load.
"""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

REPO = Path(__file__).resolve().parent.parent.parent
CR = REPO / "externals" / "experiments" / "exp-2875_per_patient.parquet"
LIN = REPO / "externals" / "experiments" / "exp-2891_simpson_dose_response.parquet"
SUMMARY = REPO / "externals" / "experiments" / "exp-2912_summary.json"


def main() -> None:
    cr = pd.read_parquet(CR)[["patient_id", "intercept", "median_rise_rate", "n_events"]]
    lin = pd.read_parquet(LIN)[["patient_id", "lineage", "cf_severe", "aid_protection_severe"]]
    df = cr.merge(lin, on="patient_id", how="inner")
    df = df[df["lineage"].notna() & (df["lineage"] != "unknown")].copy()

    out: dict = {"n_total": int(len(df))}

    # Per-lineage counts and means
    by_lineage = (
        df.groupby("lineage")
        .agg(
            n=("patient_id", "size"),
            mean_intercept=("intercept", "mean"),
            mean_cf=("cf_severe", "mean"),
            mean_protection=("aid_protection_severe", "mean"),
        )
        .reset_index()
    )
    out["by_lineage"] = by_lineage.to_dict(orient="records")

    # Marginal Kruskal-Wallis on intercept by lineage
    groups = [g["intercept"].values for _, g in df.groupby("lineage")]
    if len(groups) >= 2 and all(len(g) >= 2 for g in groups):
        kw_stat, kw_p = stats.kruskal(*groups)
        out["kruskal_marginal"] = {"H": float(kw_stat), "p": float(kw_p)}

    # Cf-conditioned: residualize intercept on cf_severe, then Kruskal residuals
    if df["cf_severe"].std() > 1e-9:
        slope, intercept_lin, *_ = stats.linregress(df["cf_severe"].values, df["intercept"].values)
        df["intercept_cf_resid"] = df["intercept"] - (intercept_lin + slope * df["cf_severe"])
    else:
        df["intercept_cf_resid"] = df["intercept"] - df["intercept"].mean()

    cf_resid_groups = [g["intercept_cf_resid"].values for _, g in df.groupby("lineage")]
    if len(cf_resid_groups) >= 2 and all(len(g) >= 2 for g in cf_resid_groups):
        kw_resid_stat, kw_resid_p = stats.kruskal(*cf_resid_groups)
        out["kruskal_cf_residualized"] = {"H": float(kw_resid_stat), "p": float(kw_resid_p)}

    # Per-lineage residual mean (signed direction of the lineage effect)
    by_lineage_resid = (
        df.groupby("lineage")
        .agg(
            mean_intercept_cf_resid=("intercept_cf_resid", "mean"),
            std_intercept_cf_resid=("intercept_cf_resid", "std"),
        )
        .reset_index()
    )
    out["by_lineage_residual"] = by_lineage_resid.to_dict(orient="records")

    # Bonus: rho(cf, intercept) per lineage
    out["rho_cf_intercept_per_lineage"] = {}
    for lineage in df["lineage"].unique():
        sub = df[df["lineage"] == lineage]
        if len(sub) >= 3 and sub["cf_severe"].std() > 1e-9:
            r, p = stats.spearmanr(sub["cf_severe"], sub["intercept"])
            out["rho_cf_intercept_per_lineage"][lineage] = {"n": int(len(sub)), "rho": float(r), "p": float(p)}

    # Bonus: rho(protection, intercept) — does upstream-failure correlate
    # with downstream rebound?
    out["rho_protection_intercept_per_lineage"] = {}
    for lineage in df["lineage"].unique():
        sub = df[df["lineage"] == lineage]
        if len(sub) >= 3:
            r, p = stats.spearmanr(sub["aid_protection_severe"], sub["intercept"])
            out["rho_protection_intercept_per_lineage"][lineage] = {"n": int(len(sub)), "rho": float(r), "p": float(p)}

    SUMMARY.write_text(json.dumps(out, indent=2, default=str))
    print(f"[exp-2912] {SUMMARY}")
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
