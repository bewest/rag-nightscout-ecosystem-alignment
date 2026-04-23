"""EXP-2913 - HAAF-adjacent blunting investigation.

Context: EXP-2912 found rho(cf_severe, counter_reg_intercept) is
NEGATIVE in Loop (-0.56) and oref1 (-0.20). Patients with higher
chronic hypo load have LOWER counter-reg intercept (slower bg
recovery from nadir). Candidate biological explanation: HAAF
(hypoglycemia-associated autonomic failure / counter-reg blunting
from chronic exposure). Candidate methodological alternative:
selection / measurement artifact.

Method:
  1. Per patient, compute hypo exposure metrics from EXP-2891:
     - cf_severe (load proxy, used in 2912)
     - aid_protection_severe (lower => more uncovered hypo events)
     - cf_severe * (1 - protection) = obs_severe rate (TRUE
       chronic exposure: counterfactual load AFTER AID coverage)
  2. Per patient, EXP-2875 has counter_reg intercept and
     median_rise_rate.
  3. Test rho(true_exposure, intercept) per lineage. Compare to
     rho(cf, intercept) from 2912 - if HAAF, true_exposure should
     correlate MORE strongly than cf (because cf is potential
     load, true_exposure is actual experienced hypo).
  4. Bootstrap CIs (1000 resamples) per lineage.
  5. Stratify by controller for Simpson check.

Limitations:
  - HAAF requires longitudinal data; we have cross-sectional only.
    A negative cross-sectional rho is consistent with HAAF but does
    not establish causation.
  - n_per_lineage is small (3-9). Wide CIs expected.
  - obs_severe rate is itself protected by AID, so chronic exposure
    is bounded; ceiling effects likely.

Output:
  per-lineage rho, bootstrap CI, comparison table, plot data.
"""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent.parent
SIMPSON = REPO / "externals" / "experiments" / "exp-2891_simpson_dose_response.parquet"
COUNTER = REPO / "externals" / "experiments" / "exp-2875_per_patient.parquet"
SUMMARY = REPO / "externals" / "experiments" / "exp-2913_summary.json"
OUT_PARQUET = REPO / "externals" / "experiments" / "exp-2913_haaf_blunting.parquet"

RNG = np.random.default_rng(42)
N_BOOT = 1000


def boot_rho(x: np.ndarray, y: np.ndarray, n: int = N_BOOT) -> tuple[float, float, float]:
    if len(x) < 4:
        return (float("nan"), float("nan"), float("nan"))
    rhos = []
    idx = np.arange(len(x))
    for _ in range(n):
        s = RNG.choice(idx, size=len(idx), replace=True)
        if len(np.unique(x[s])) < 2 or len(np.unique(y[s])) < 2:
            continue
        rhos.append(float(np.corrcoef(x[s], y[s])[0, 1]))
    if not rhos:
        return (float("nan"), float("nan"), float("nan"))
    return (
        float(np.median(rhos)),
        float(np.percentile(rhos, 2.5)),
        float(np.percentile(rhos, 97.5)),
    )


def main() -> None:
    sd = pd.read_parquet(SIMPSON)
    cr = pd.read_parquet(COUNTER)
    df = sd.merge(
        cr[["patient_id", "intercept", "median_rise_rate", "n_events"]],
        on="patient_id", how="inner",
    )
    df = df[df["lineage"] != "unknown"].copy()
    df["true_exposure_rate"] = df["cf_severe"] * (1 - df["aid_protection_severe"])

    df.to_parquet(OUT_PARQUET, index=False)

    metrics = []
    for ln, g in df.groupby("lineage"):
        n = len(g)
        for x_name in ("cf_severe", "true_exposure_rate", "aid_protection_severe"):
            x = g[x_name].astype(float).values
            for y_name in ("intercept", "median_rise_rate"):
                y = g[y_name].astype(float).values
                rho_pt = float(np.corrcoef(x, y)[0, 1]) if n >= 3 else float("nan")
                rho_med, lo, hi = boot_rho(x, y)
                metrics.append({
                    "lineage": ln,
                    "n_patients": int(n),
                    "x": x_name,
                    "y": y_name,
                    "rho_point": rho_pt,
                    "rho_boot_median": rho_med,
                    "ci95_lo": lo,
                    "ci95_hi": hi,
                    "ci_excludes_zero": (
                        bool(lo > 0 or hi < 0) if not (np.isnan(lo) or np.isnan(hi)) else False
                    ),
                })

    metrics_df = pd.DataFrame(metrics)

    # HAAF interpretation table: focus on (x=true_exposure, y=intercept)
    haaf_rows = metrics_df[
        (metrics_df["x"] == "true_exposure_rate") & (metrics_df["y"] == "intercept")
    ]
    cf_rows = metrics_df[
        (metrics_df["x"] == "cf_severe") & (metrics_df["y"] == "intercept")
    ]

    # Compare rho_cf vs rho_true_exposure per lineage
    comparison = []
    for ln in df["lineage"].unique():
        cf_r = cf_rows[cf_rows["lineage"] == ln].iloc[0]
        te_r = haaf_rows[haaf_rows["lineage"] == ln].iloc[0]
        delta = float(te_r["rho_point"] - cf_r["rho_point"])
        comparison.append({
            "lineage": ln,
            "n": int(cf_r["n_patients"]),
            "rho(cf, intercept)": float(cf_r["rho_point"]),
            "rho(true_exposure, intercept)": float(te_r["rho_point"]),
            "delta_strength": delta,
            "haaf_signal": (
                "STRONGER under true_exposure" if abs(te_r["rho_point"]) > abs(cf_r["rho_point"]) + 0.05
                else "WEAKER under true_exposure" if abs(te_r["rho_point"]) < abs(cf_r["rho_point"]) - 0.05
                else "similar"
            ),
        })

    summary = {
        "scope": (
            "Cross-sectional HAAF-adjacent blunting investigation. "
            "Negative rho(exposure, intercept) is CONSISTENT WITH but "
            "does not ESTABLISH HAAF without longitudinal data."
        ),
        "all_metrics": metrics_df.to_dict(orient="records"),
        "haaf_comparison_per_lineage": comparison,
        "n_patients_total": int(df["patient_id"].nunique()),
    }

    SUMMARY.write_text(json.dumps(summary, indent=2, default=str))
    print(f"[exp-2913] {SUMMARY}")
    print("\nHAAF comparison (rho with counter_reg intercept):")
    print(pd.DataFrame(comparison).to_string(index=False))
    print("\nFull metrics with bootstrap CIs:")
    print(metrics_df[
        metrics_df["y"] == "intercept"
    ].sort_values(["lineage", "x"]).to_string(index=False))


if __name__ == "__main__":
    main()
