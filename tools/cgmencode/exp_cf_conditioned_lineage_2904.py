"""EXP-2904: cf-conditioned lineage protection comparison.

EXP-2891 found a lineage effect on aid_protection_severe (permutation
p=0.018; ANCOVA Kruskal p=0.034). EXP-2902 revealed that 42% of the
cohort is in load_saturation regime (cf>=0.95), with Loop concentrated
there (5/7). This raises the concern that EXP-2891's lineage effect is
partly mediated by load-intensity self-selection.

This experiment re-tests the lineage effect with cf_severe added as a
covariate (or stratifier). If the effect SURVIVES cf-conditioning, it
is a robust lineage-mechanism signal. If it ATTENUATES, EXP-2891 was
partly conflating lineage capability with user behaviour.

Methods:
  1. ANCOVA-style: linear regression protection ~ lineage + cf_severe
     report partial-eta-squared and t-stats per lineage contrast
  2. Stratified: re-run Kruskal within each cf-stratum (>=0.95 vs <0.95)
  3. Permutation: shuffle lineage labels within cf-stratum, recompute
     within-stratum lineage spread

Output: summary JSON with raw and cf-adjusted contrasts.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

OUT = Path("externals/experiments")
EXP_ID = "exp-2904"

CF_HIGH = 0.95
RNG = np.random.default_rng(2904)


def fit_ancova(df: pd.DataFrame) -> dict:
    """Linear regression protection ~ lineage_dummies + cf_severe."""
    lineages = sorted(df["lineage"].unique())
    base = lineages[0]
    X_cols = ["intercept", "cf_severe"] + [f"lin__{l}" for l in lineages[1:]]
    X = np.zeros((len(df), len(X_cols)))
    X[:, 0] = 1.0
    X[:, 1] = df["cf_severe"].values
    for i, l in enumerate(lineages[1:]):
        X[:, 2 + i] = (df["lineage"].values == l).astype(float)
    y = df["aid_protection_severe"].values
    beta, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
    yhat = X @ beta
    resid = y - yhat
    rss = float(np.sum(resid ** 2))
    tss = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - rss / tss
    n = len(df)
    p = X.shape[1]
    sigma2 = rss / (n - p)
    cov = sigma2 * np.linalg.inv(X.T @ X)
    se = np.sqrt(np.diag(cov))
    tstats = beta / se
    return {
        "base_lineage": base,
        "coefficients": dict(zip(X_cols, beta.tolist())),
        "se": dict(zip(X_cols, se.tolist())),
        "tstats": dict(zip(X_cols, tstats.tolist())),
        "r2": r2,
        "n": n,
        "df_resid": n - p,
    }


def kruskal_by_lineage(df: pd.DataFrame) -> dict:
    groups = [g["aid_protection_severe"].values for _, g in df.groupby("lineage")]
    if len(groups) < 2 or any(len(g) < 2 for g in groups):
        return {"H": None, "p": None, "n": int(len(df)), "note": "insufficient cells"}
    H, p = stats.kruskal(*groups)
    return {"H": float(H), "p": float(p), "n": int(len(df))}


def stratified_perm(df: pd.DataFrame, n_perm: int = 5000) -> dict:
    """Permute lineage labels within each cf-stratum, compare observed lineage
    median spread to null distribution."""
    df = df.copy()
    df["cf_stratum"] = np.where(df["cf_severe"] >= CF_HIGH, "high", "low")

    def median_spread(d: pd.DataFrame) -> float:
        med = d.groupby("lineage")["aid_protection_severe"].median()
        return float(med.max() - med.min())

    obs = median_spread(df)
    strata_indices = {
        s: df.index[df["cf_stratum"] == s].to_numpy()
        for s in df["cf_stratum"].unique()
    }
    null = np.empty(n_perm)
    for i in range(n_perm):
        d = df.copy()
        for stratum, idx in strata_indices.items():
            shuffled = RNG.permutation(d.loc[idx, "lineage"].to_numpy())
            d.loc[idx, "lineage"] = shuffled
        null[i] = median_spread(d)
    p = float(np.mean(null >= obs))
    return {"observed_spread": obs, "perm_p": p, "n_perm": n_perm}


def main() -> None:
    df = pd.read_parquet(OUT / "exp-2891_simpson_dose_response.parquet")
    df = df[df["lineage"] != "unknown"].copy()

    summary = {
        "exp": EXP_ID,
        "n_total": int(len(df)),
        "lineage_counts": df["lineage"].value_counts().to_dict(),
    }

    # 1. Raw Kruskal (baseline reproduction)
    summary["raw_kruskal"] = kruskal_by_lineage(df)

    # 2. ANCOVA with cf
    summary["ancova"] = fit_ancova(df)

    # 3. Stratified Kruskal
    high_cf = df[df["cf_severe"] >= CF_HIGH]
    low_cf = df[df["cf_severe"] < CF_HIGH]
    summary["high_cf_kruskal"] = kruskal_by_lineage(high_cf)
    summary["low_cf_kruskal"] = kruskal_by_lineage(low_cf)
    summary["high_cf_n"] = int(len(high_cf))
    summary["low_cf_n"] = int(len(low_cf))

    # 4. Stratified permutation (within-cf-stratum)
    summary["stratified_perm"] = stratified_perm(df)

    # 5. Lineage medians within each stratum
    summary["lineage_medians_by_stratum"] = (
        df.assign(cf_stratum=np.where(df["cf_severe"] >= CF_HIGH, "high", "low"))
          .groupby(["cf_stratum", "lineage"])["aid_protection_severe"]
          .agg(["count", "median", "std"])
          .reset_index()
          .to_dict(orient="records")
    )

    (OUT / f"{EXP_ID}_summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(f"[{EXP_ID}] n={summary['n_total']}")
    print(f"  raw kruskal: H={summary['raw_kruskal']['H']:.3f}  p={summary['raw_kruskal']['p']:.4f}")
    print(f"  high-cf only kruskal (n={summary['high_cf_n']}): "
          f"{summary['high_cf_kruskal']}")
    print(f"  low-cf only kruskal (n={summary['low_cf_n']}): "
          f"{summary['low_cf_kruskal']}")
    print(f"  ANCOVA r2={summary['ancova']['r2']:.3f}")
    print(f"  ANCOVA t-stats: {summary['ancova']['tstats']}")
    print(f"  stratified perm: observed_spread={summary['stratified_perm']['observed_spread']:.3f}  "
          f"p={summary['stratified_perm']['perm_p']:.4f}")
    print()
    print("  Lineage medians by cf stratum:")
    for r in summary["lineage_medians_by_stratum"]:
        print(f"    cf={r['cf_stratum']:5s}  {r['lineage']:15s}  "
              f"n={int(r['count']):2d}  med={r['median']:.3f}  std={r['std']:.3f}"
              if not np.isnan(r['std']) else
              f"    cf={r['cf_stratum']:5s}  {r['lineage']:15s}  "
              f"n={int(r['count']):2d}  med={r['median']:.3f}  std=  n/a")


if __name__ == "__main__":
    main()
