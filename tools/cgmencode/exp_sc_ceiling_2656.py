#!/usr/bin/env python3
"""EXP-2656: SC Insulin Suppression Ceiling Test.

MOTIVATION: cgmsim-lib's liver.ts models max SC suppression at 65% — SC insulin
can never fully suppress hepatic EGP because it doesn't reach the portal vein
(only IV insulin can). This has implications:
  - At high IOB, EGP still produces ~35% of basal glucose output
  - "Sticky hypers" may be partly explained by this ceiling
  - Current AID controllers assume linear IOB→glucose, missing the ceiling

From EXP-2629: 37% of sticky hyper time has glucose rising despite high IOB.
From EXP-2651: ISF inflated 2-10× (EGP recovery fills in the gap).

METHOD:
  1. For each patient, find high-IOB periods (IOB > 2× median)
  2. Compute actual glucose change rate during these periods
  3. Compare against predictions from:
     a) Linear model: expected_drop = IOB × ISF / DIA (standard AID)
     b) Ceiling model: expected_drop = min(IOB × ISF / DIA, 0.65 × EGP_base)
  4. Test: does the ceiling model predict the "plateau" better?
  5. Estimate per-patient suppression ceiling

HYPOTHESES:
  H1: At high IOB (>2× median), glucose drops SLOWER than linear model predicts
      (measured slope / predicted slope < 0.8 for ≥60% of patients)
  H2: The 65% ceiling model fits high-IOB segments better than linear (lower RMSE)
  H3: Per-patient suppression ceiling varies ≥20% (range 50-80%)
  H4: Sticky hyper rate correlates with distance from suppression ceiling (r > 0.3)
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats, optimize

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PARQUET = Path("externals/ns-parquet/training/grid.parquet")
RESULTS_DIR = Path("externals/experiments")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
OUTFILE = RESULTS_DIR / "exp-2656_sc_ceiling.json"

NS_PATIENTS = ["a", "b", "c", "d", "e", "f", "g", "i", "k"]
ODC_FULL = ["odc-74077367", "odc-86025410", "odc-96254963"]
ALL_PATIENTS = NS_PATIENTS + ODC_FULL
STEPS_PER_HOUR = 12
DIA_HOURS = 6.0

# Hill equation parameters from metabolic_engine.py
HILL_N = 1.5
HILL_K = 2.0
BASE_EGP = 18.0  # mg/dL/hr (1.5 mg/dL/5min × 12)


def _hill_suppression(iob, hill_k=HILL_K, hill_n=HILL_N, max_supp=0.65):
    """EGP suppression via Hill equation with SC ceiling.

    Returns fraction of EGP suppressed (0 to max_supp).
    """
    iob_abs = np.abs(iob)
    suppression = iob_abs**hill_n / (iob_abs**hill_n + hill_k**hill_n)
    return np.minimum(suppression, max_supp)


def _analyze_patient(pid, pdf):
    """Per-patient SC ceiling analysis."""
    pdf = pdf.sort_values("time").reset_index(drop=True)

    glucose = pdf["glucose"].values.astype(np.float64)
    iob = pdf["iob"].fillna(0).values.astype(np.float64)
    glucose_roc = pdf["glucose_roc"].fillna(0).values.astype(np.float64)
    sched_isf = float(pdf["scheduled_isf"].dropna().median())
    sched_basal = float(pdf["scheduled_basal_rate"].dropna().median())

    # Identify high-IOB segments (IOB > 2× median of non-zero IOB)
    iob_nonzero = iob[iob > 0.1]
    if len(iob_nonzero) < 100:
        return None
    iob_median = float(np.median(iob_nonzero))
    high_iob_threshold = 2 * iob_median

    # Find segments where IOB is high
    high_mask = iob > high_iob_threshold
    n_high = int(np.sum(high_mask))
    if n_high < 50:
        return None

    # Get glucose ROC during high-IOB periods
    high_iob_vals = iob[high_mask]
    high_glucose_roc_vals = glucose_roc[high_mask]
    high_glucose_vals = glucose[high_mask]

    # Filter out NaN glucose_roc
    valid = ~np.isnan(high_glucose_roc_vals) & ~np.isnan(high_glucose_vals)
    if np.sum(valid) < 30:
        return None

    high_iob_v = high_iob_vals[valid]
    high_roc_v = high_glucose_roc_vals[valid]
    high_bg_v = high_glucose_vals[valid]

    # === Linear model prediction ===
    # Expected glucose drop rate = -IOB × ISF / DIA (simplified)
    linear_predicted = -high_iob_v * sched_isf / DIA_HOURS
    actual_rate = high_roc_v * STEPS_PER_HOUR  # Convert from per-5min to per-hour

    # Ratio: actual/predicted (< 1 means glucose drops slower than expected)
    # Filter out near-zero predictions
    sig_pred = np.abs(linear_predicted) > 1.0
    if np.sum(sig_pred) < 20:
        return None
    ratio = actual_rate[sig_pred] / linear_predicted[sig_pred]
    mean_ratio = float(np.median(ratio))

    # === Ceiling model prediction ===
    # EGP contribution: EGP_base × (1 - suppression)
    # Net glucose rate = -insulin_effect + egp_residual
    suppression_65 = _hill_suppression(high_iob_v, max_supp=0.65)
    egp_residual_65 = BASE_EGP * (1 - suppression_65)
    ceiling_predicted = linear_predicted + egp_residual_65

    # RMSE comparison
    linear_rmse = float(np.sqrt(np.mean((actual_rate - linear_predicted)**2)))
    ceiling_rmse = float(np.sqrt(np.mean((actual_rate - ceiling_predicted)**2)))

    # === Fit per-patient suppression ceiling ===
    def _ceiling_residual(params, iob_vals, actual_vals):
        max_supp, base_egp = params
        supp = _hill_suppression(iob_vals, max_supp=max_supp)
        egp_resid = base_egp * (1 - supp)
        predicted = -iob_vals * sched_isf / DIA_HOURS + egp_resid
        return np.sum((actual_vals - predicted)**2)

    try:
        result = optimize.minimize(
            _ceiling_residual, x0=[0.65, BASE_EGP],
            args=(high_iob_v, actual_rate),
            bounds=[(0.3, 1.0), (5.0, 60.0)],
            method="L-BFGS-B"
        )
        fitted_ceiling = float(result.x[0])
        fitted_base_egp = float(result.x[1])
        fitted_rmse = float(np.sqrt(result.fun / len(high_iob_v)))
    except Exception:
        fitted_ceiling = np.nan
        fitted_base_egp = np.nan
        fitted_rmse = np.nan

    # === Sticky hyper analysis ===
    # High IOB + glucose > 180 + rising
    sticky_mask = (high_bg_v > 180) & (high_roc_v > 0)
    n_sticky = int(np.sum(sticky_mask))
    pct_sticky = float(n_sticky / len(high_bg_v)) if len(high_bg_v) > 0 else 0

    # Mean IOB during sticky hypers
    mean_iob_sticky = float(np.mean(high_iob_v[sticky_mask])) if n_sticky > 0 else np.nan
    mean_iob_all_high = float(np.mean(high_iob_v))

    return {
        "n_high_iob": int(np.sum(valid)),
        "iob_median": iob_median,
        "high_iob_threshold": high_iob_threshold,
        "scheduled_isf": sched_isf,
        "scheduled_basal": sched_basal,
        # Linear model
        "mean_actual_rate": float(np.mean(actual_rate)),
        "mean_linear_predicted": float(np.mean(linear_predicted)),
        "actual_to_predicted_ratio": mean_ratio,
        "linear_rmse": linear_rmse,
        # Ceiling model (65%)
        "ceiling_65_rmse": ceiling_rmse,
        "ceiling_improvement_pct": float((1 - ceiling_rmse / linear_rmse) * 100)
            if linear_rmse > 0 else 0,
        # Fitted ceiling
        "fitted_ceiling": fitted_ceiling,
        "fitted_base_egp": fitted_base_egp,
        "fitted_rmse": fitted_rmse,
        # Sticky hypers
        "n_sticky_hypers": n_sticky,
        "pct_sticky": pct_sticky,
        "mean_iob_sticky": mean_iob_sticky,
        "mean_iob_all_high": mean_iob_all_high,
    }


def main():
    print("=" * 70)
    print("EXP-2656: SC Insulin Suppression Ceiling Test")
    print("=" * 70)

    df_all = pd.read_parquet(PARQUET)
    results = {}

    for pid in ALL_PATIENTS:
        pdf = df_all[df_all["patient_id"] == pid].copy()
        if len(pdf) < 200:
            continue

        r = _analyze_patient(pid, pdf)
        if r is None:
            print(f"\n  {pid}: insufficient high-IOB data")
            continue

        prefix = "[ODC]" if pid.startswith("odc") else "[NS] "
        print(f"\n  {prefix} {pid} (N={r['n_high_iob']} high-IOB periods, "
              f"threshold={r['high_iob_threshold']:.1f}U):")
        print(f"    Actual rate: {r['mean_actual_rate']:+.1f} mg/dL/hr, "
              f"Linear predicted: {r['mean_linear_predicted']:+.1f}")
        print(f"    Actual/predicted ratio: {r['actual_to_predicted_ratio']:.2f} "
              f"({'slower' if r['actual_to_predicted_ratio'] > -0.5 else 'faster'} than expected)")
        print(f"    RMSE: linear={r['linear_rmse']:.1f}, "
              f"ceiling-65%={r['ceiling_65_rmse']:.1f} "
              f"({r['ceiling_improvement_pct']:+.1f}%)")
        print(f"    Fitted ceiling: {r['fitted_ceiling']*100:.0f}%, "
              f"base EGP: {r['fitted_base_egp']:.0f} mg/dL/hr")
        print(f"    Sticky hypers: {r['pct_sticky']*100:.0f}% of high-IOB time, "
              f"N={r['n_sticky_hypers']}")

        results[pid] = r

    # === Hypothesis testing ===
    print("\n" + "=" * 70)
    print("HYPOTHESIS TESTING")
    print("=" * 70)

    # H1: Glucose drops slower than linear for ≥60%
    slow = sum(1 for r in results.values()
               if r["actual_to_predicted_ratio"] > -0.5)
    # Actually, the ratio is actual/predicted. If predicted is -40 and actual is -20,
    # ratio = -20/-40 = 0.5 (drops at 50% of expected rate).
    # "Slower than expected" means |actual| < |predicted|, i.e., ratio < 1 (for negative values)
    # But the ratio can be positive if actual rate is positive (glucose rising despite high IOB)
    slower = sum(1 for r in results.values()
                 if abs(r["mean_actual_rate"]) < abs(r["mean_linear_predicted"]) * 0.8)
    total = len(results)
    print(f"\n  H1: Glucose drops ≥20% slower than linear at high IOB")
    print(f"      {slower}/{total} ({slower/total*100:.0f}%)")
    ratios_str = [f'{r["actual_to_predicted_ratio"]:.2f}' for r in results.values()]
    print(f"      Ratios: {ratios_str}")
    h1 = slower >= total * 0.6
    print(f"      → {'PASS' if h1 else 'FAIL'}")

    # H2: Ceiling model fits better
    better_ceiling = sum(1 for r in results.values()
                         if r["ceiling_65_rmse"] < r["linear_rmse"])
    print(f"\n  H2: 65% ceiling model RMSE < linear")
    print(f"      {better_ceiling}/{total}")
    improvements = [f'{r["ceiling_improvement_pct"]:+.1f}%' for r in results.values()]
    print(f"      Improvements: {improvements}")
    h2 = better_ceiling > total / 2
    print(f"      → {'PASS' if h2 else 'FAIL'}")

    # H3: Per-patient ceiling varies ≥20%
    ceilings = [r["fitted_ceiling"] for r in results.values()
                if not np.isnan(r["fitted_ceiling"])]
    if ceilings:
        ceil_range = max(ceilings) - min(ceilings)
        print(f"\n  H3: Suppression ceiling range ≥ 0.20")
        print(f"      Range: {ceil_range:.2f} ({min(ceilings)*100:.0f}% – {max(ceilings)*100:.0f}%)")
        ceilings_str = [f'{c*100:.0f}%' for c in sorted(ceilings)]
        print(f"      Per-patient: {ceilings_str}")
        h3 = ceil_range >= 0.20
        print(f"      → {'PASS' if h3 else 'FAIL'}")

    # H4: Sticky hyper rate correlates with ceiling
    if len(ceilings) >= 5:
        pct_sticky = [r["pct_sticky"] for r in results.values()
                      if not np.isnan(r["fitted_ceiling"])]
        r_corr, p_corr = stats.pearsonr(ceilings, pct_sticky)
        print(f"\n  H4: Sticky hyper rate correlates with suppression ceiling")
        print(f"      r = {r_corr:+.3f}, p = {p_corr:.3f}")
        h4 = abs(r_corr) > 0.3
        print(f"      → {'PASS' if h4 else 'FAIL'}")

    Path(OUTFILE).write_text(json.dumps(results, indent=2, default=str))
    print(f"\nResults saved to {OUTFILE}")


if __name__ == "__main__":
    main()
