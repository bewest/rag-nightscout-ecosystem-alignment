"""EXP-2911 — cf-conditioned setting-independence (axis 2 re-grade).

EXP-2891 found three distinct lineage signatures across aggressiveness
terciles:
  oref1: 0.63 -> 0.72 (setting-INDEPENDENT)
  Loop:  0.49 -> 0.58 (modest dose-response)
  oref0: 0.13 -> 0.72 (HUGE dose-response)

Default Guard #6 requires cf-conditioning. This experiment fits within
each lineage:
   protection_severe ~ tercile + cf_severe (per-patient cell-level)
and reports the partial-tercile effect after controlling for cf.

If oref0's dose-response shrinks under cf-conditioning, the original
finding was confounded by aggressive users sitting in load_saturation;
if it persists, oref0 conservative users are genuinely under-defended
by the algorithm itself.
"""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

REPO = Path(__file__).resolve().parent.parent.parent
SRC = REPO / "externals" / "experiments" / "exp-2891_simpson_dose_response.parquet"
SUMMARY = REPO / "externals" / "experiments" / "exp-2911_summary.json"

TERCILE_ORDER = {"conservative": 0, "moderate": 1, "aggressive": 2}


def main():
    df = pd.read_parquet(SRC)
    df = df[df["lineage"] != "unknown"].copy()
    df["tercile_num"] = df["tercile"].map(TERCILE_ORDER)
    df = df.dropna(subset=["aid_protection_severe", "cf_severe", "tercile_num", "lineage"])

    out = {"by_lineage": {}}
    for lineage in df["lineage"].unique():
        sub = df[df["lineage"] == lineage].copy()
        if len(sub) < 3:
            out["by_lineage"][lineage] = {"n": int(len(sub)), "skipped": "n<3"}
            continue

        # Marginal: protection ~ tercile_num
        if sub["tercile_num"].nunique() >= 2:
            r_marg, p_marg = stats.spearmanr(sub["tercile_num"], sub["aid_protection_severe"])
        else:
            r_marg, p_marg = (np.nan, np.nan)

        # Cf-conditioned: residualize protection on cf, then correlate residual with tercile
        x = sub["cf_severe"].values
        y = sub["aid_protection_severe"].values
        # OLS linear regression: y ~ a + b*cf
        if np.std(x) > 1e-9:
            slope, intercept, *_ = stats.linregress(x, y)
            y_resid = y - (intercept + slope * x)
        else:
            y_resid = y - np.mean(y)
        if sub["tercile_num"].nunique() >= 2:
            r_cf, p_cf = stats.spearmanr(sub["tercile_num"], y_resid)
        else:
            r_cf, p_cf = (np.nan, np.nan)

        # Per-tercile means (raw + residualized)
        per_tier = {}
        for tier_name, tier_num in TERCILE_ORDER.items():
            mask = sub["tercile_num"] == tier_num
            if mask.sum() == 0:
                continue
            per_tier[tier_name] = {
                "n": int(mask.sum()),
                "mean_protection": float(sub.loc[mask, "aid_protection_severe"].mean()),
                "mean_cf": float(sub.loc[mask, "cf_severe"].mean()),
                "mean_protection_cf_resid": float(np.mean(y_resid[mask.values])),
            }

        out["by_lineage"][lineage] = {
            "n": int(len(sub)),
            "marginal_rho": float(r_marg) if not np.isnan(r_marg) else None,
            "marginal_p": float(p_marg) if not np.isnan(p_marg) else None,
            "cf_resid_rho": float(r_cf) if not np.isnan(r_cf) else None,
            "cf_resid_p": float(p_cf) if not np.isnan(p_cf) else None,
            "per_tier": per_tier,
        }

    SUMMARY.write_text(json.dumps(out, indent=2))
    print(f"[exp-2911] {SUMMARY}")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
