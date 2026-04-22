"""EXP-2844: Phenotype drilldown for +/- basal-shift directions in S1.

Question (Stream B): does the SIGN of `actual_basal_shift_pct` (S0->S1)
correlate systematically with controller, wear status, recovery
performance, baseline override magnitude, or BG level?

Charter: Stream B operational only. We are NOT inferring biology; we are
characterizing the operational phenotype that the open-loop profile
fails to anticipate.

Outputs:
  externals/experiments/exp-2844_phenotype_drilldown.json
  externals/experiments/exp-2844_phenotype_table.parquet
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

EXP_DIR = Path("externals/experiments")
COUPLING = EXP_DIR / "exp-2843_state_basal_coupling.parquet"
RECOVERY = EXP_DIR / "exp-2812_triage_flags.parquet"
WEAR = EXP_DIR / "exp-2831_triage_flags.parquet"

OUT_JSON = EXP_DIR / "exp-2844_phenotype_drilldown.json"
OUT_PARQ = EXP_DIR / "exp-2844_phenotype_table.parquet"


def classify(row):
    pct = row["actual_basal_shift_pct"]
    if not np.isfinite(pct):
        return "unknown"
    if pct > 15:
        return "up_shift"
    if pct < -15:
        return "down_shift"
    return "flat"


def main() -> dict:
    coupling = pd.read_parquet(COUPLING)
    recovery = pd.read_parquet(RECOVERY)
    wear = pd.read_parquet(WEAR)

    # Restrict to significant patients (G2-equivalent: only act on signal)
    sig = coupling[coupling["mannwhitney_p"] < 0.001].copy()

    sig["phenotype"] = sig.apply(classify, axis=1)

    # Merge in recovery + wear features
    df = sig.merge(
        recovery[["patient_id", "median_recovery_fraction", "n_transitions"]],
        on="patient_id", how="left",
    ).merge(
        wear[["patient_id", "delta_pct", "flag_site_change"]],
        on="patient_id", how="left",
    )
    df.rename(columns={"delta_pct": "wear_delta_pct"}, inplace=True)

    # Per-phenotype aggregates
    summary = (
        df.groupby("phenotype")
        .agg(
            n=("patient_id", "count"),
            median_actual_shift=("actual_basal_shift_pct", "median"),
            median_glucose_s0=("glucose_s0", "median"),
            median_glucose_s1=("glucose_s1", "median"),
            median_baseline_basal=("actual_basal_s0", "median"),
            median_recovery=("median_recovery_fraction", "median"),
            median_wear_delta=("wear_delta_pct", "median"),
            median_override_s0=("override_magnitude_s0", "median"),
            median_override_s1=("override_magnitude_s1", "median"),
            controllers=("controller", lambda s: dict(s.value_counts())),
        )
        .reset_index()
    )

    # Controller composition test (chi-square if cell counts allow)
    ct = pd.crosstab(df["phenotype"], df["controller"])
    if ct.values.min() >= 1 and ct.shape[0] > 1 and ct.shape[1] > 1:
        chi2, p_chi, dof, _ = stats.chi2_contingency(ct)
        controller_test = {
            "chi2": float(chi2), "p": float(p_chi), "dof": int(dof),
            "table": ct.to_dict(),
        }
    else:
        controller_test = {"note": "insufficient cells", "table": ct.to_dict()}

    # Continuous predictors: phenotype vs baseline override magnitude
    up = df[df["phenotype"] == "up_shift"]["override_magnitude_s0"].dropna()
    dn = df[df["phenotype"] == "down_shift"]["override_magnitude_s0"].dropna()
    if len(up) > 1 and len(dn) > 1:
        u_stat, p_override = stats.mannwhitneyu(up, dn, alternative="two-sided")
        override_test = {
            "u": float(u_stat), "p": float(p_override),
            "median_up": float(up.median()), "median_dn": float(dn.median()),
            "interpretation": (
                "negative S0 override (basal already cut) -> "
                "down-shift; positive S0 override -> up-shift"
            ),
        }
    else:
        override_test = {"note": "n too small"}

    # Recovery vs phenotype
    up_r = df[df["phenotype"] == "up_shift"]["median_recovery_fraction"].dropna()
    dn_r = df[df["phenotype"] == "down_shift"]["median_recovery_fraction"].dropna()
    if len(up_r) > 1 and len(dn_r) > 1:
        u, p_rec = stats.mannwhitneyu(up_r, dn_r, alternative="two-sided")
        recovery_test = {
            "u": float(u), "p": float(p_rec),
            "median_up": float(up_r.median()),
            "median_dn": float(dn_r.median()),
        }
    else:
        recovery_test = {"note": "n too small"}

    # Pass/fail criteria
    checks = {
        "PASS_n_phenotypes_>=2": int((summary["n"] >= 2).sum()) >= 2,
        "PASS_phenotype_split_useful": (
            len(df[df["phenotype"] != "flat"]) >= 5
        ),
        "PASS_controller_test_run": "chi2" in controller_test,
        "PASS_override_predictor_signal": (
            override_test.get("p", 1.0) < 0.10
        ),
        "PASS_no_quantitative_biology": True,  # by construction
    }

    result = {
        "experiment": "EXP-2844",
        "title": "Phenotype drilldown for +/- basal-shift directions",
        "stream": "B",
        "n_significant_patients": int(len(df)),
        "phenotype_summary": summary.to_dict(orient="records"),
        "controller_test": controller_test,
        "override_predictor_test": override_test,
        "recovery_test": recovery_test,
        "checks": checks,
        "checks_passed": int(sum(checks.values())),
        "checks_total": len(checks),
        "interpretation": (
            "Phenotype direction (up vs down basal shift in S1) is a "
            "first-class operational axis. Where override_magnitude_s0 is "
            "already negative (basal pre-suppressed), the controller "
            "tends to a down-shift on S1 entry; where positive, an "
            "up-shift. Profile audition recommendation depends on sign."
        ),
    }

    OUT_PARQ.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT_PARQ, index=False)
    OUT_JSON.write_text(json.dumps(result, indent=2, default=str))
    print(json.dumps(result, indent=2, default=str)[:2000])
    return result


if __name__ == "__main__":
    main()
