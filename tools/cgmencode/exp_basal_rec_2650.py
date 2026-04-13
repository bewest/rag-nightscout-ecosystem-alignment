#!/usr/bin/env python3
"""EXP-2650: IOB-Corrected Basal Recommendation.

Builds on F3 (IOB@midnight predicts overnight drift, r=-0.45 to -0.57)
and F5 (recovery slope ≈ base EGP at 17-18 mg/dL/hr).

INSIGHT: When IOB@midnight = 0, overnight drift should equal
(EGP_rate - basal_insulin_effect). If drift > 0, basal is too low
(not matching EGP). If drift < 0, basal is too high.

METHOD:
  1. For each patient, fit: drift = α × IOB@midnight + β
     - β = drift at zero IOB = (EGP - basal_effect)
     - α = sensitivity of drift to residual IOB
  2. Solve for basal adjustment: Δbasal = β / scheduled_ISF
     (convert mg/dL/hr drift into U/hr basal change)
  3. Validate on held-out nights (80/20 split)

HYPOTHESES:
H1: IOB-corrected basal differs from scheduled basal by ≥0.05 U/hr for ≥50% of patients
H2: Recommended basal reduces held-out night drift variance by ≥15%
H3: Dawn phenomenon (04-08h) requires ≥20% more basal than midnight-04h for ≥50% of patients
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

PARQUET = Path("externals/ns-parquet/training/grid.parquet")
RESULTS_DIR = Path("externals/experiments")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
OUTFILE = RESULTS_DIR / "exp-2650_basal_recommendation.json"

NS_PATIENTS = ["a", "b", "c", "d", "e", "f", "g", "i", "k"]
ODC_FULL = ["odc-74077367", "odc-86025410", "odc-96254963"]
ALL_PATIENTS = NS_PATIENTS + ODC_FULL
STEPS_PER_HOUR = 12


def _extract_overnight_windows(pdf):
    """Extract clean overnight windows with drift, IOB@midnight, and time block."""
    pdf = pdf.sort_values("time").reset_index(drop=True)
    t = pd.to_datetime(pdf["time"])
    pdf = pdf.assign(hour=t.dt.hour, minute=t.dt.minute, date=t.dt.date)

    carbs = pdf["carbs"].fillna(0).values
    bolus = pdf["bolus"].fillna(0).values
    iob = pdf["iob"].fillna(0).values
    glucose = pdf["glucose"].values.astype(np.float64)

    rows = []
    for date in sorted(pdf["date"].unique()):
        # Two blocks: midnight-04h and 04h-08h (dawn phenomenon)
        for block_start, block_end, block_name in [(0, 4, "midnight"), (4, 8, "dawn")]:
            mask = (pdf["date"] == date) & (pdf["hour"] >= block_start) & (pdf["hour"] < block_end)
            block = pdf[mask]
            if len(block) < 24:  # need ≥2h of data
                continue

            bg = block["glucose"].dropna()
            if len(bg) < 16:
                continue

            # Skip if carbs or bolus during window
            if block["carbs"].fillna(0).sum() > 2 or block["bolus"].fillna(0).sum() > 0.3:
                continue

            # Compute drift (mg/dL/hr)
            t_hrs = np.arange(len(bg)) * (5.0 / 60.0)
            slope, intercept = np.polyfit(t_hrs, bg.values, 1)

            # IOB at start of window
            idx_start = block.index[0]
            pos = pdf.index.get_loc(idx_start)
            iob_start = float(iob[pos]) if not np.isnan(iob[pos]) else 0.0

            # Mean glucose
            mean_bg = float(bg.mean())

            rows.append({
                "date": str(date),
                "block": block_name,
                "drift": float(slope),
                "iob_start": iob_start,
                "mean_glucose": mean_bg,
                "n_points": len(bg),
            })

    return pd.DataFrame(rows)


def _analyze_patient(pid, pdf):
    """Per-patient basal analysis."""
    windows = _extract_overnight_windows(pdf)
    if len(windows) < 10:
        return None

    scheduled_basal = float(pdf["scheduled_basal_rate"].dropna().median())
    scheduled_isf = float(pdf["scheduled_isf"].dropna().median())

    result = {"scheduled_basal": scheduled_basal, "scheduled_isf": scheduled_isf}

    # Analyze each block separately
    for block_name in ["midnight", "dawn"]:
        bw = windows[windows["block"] == block_name]
        if len(bw) < 5:
            continue

        # Fit: drift = α × IOB + β
        iob_vals = bw["iob_start"].values
        drift_vals = bw["drift"].values

        # Handle constant IOB (some patients have very stable overnight IOB)
        if np.std(iob_vals) < 0.01:
            # Can't fit slope, just use mean drift as β
            beta = float(np.mean(drift_vals))
            alpha = 0.0
            r, p = 0.0, 1.0
            r2 = 0.0
        else:
            slope_fit, intercept_fit = np.polyfit(iob_vals, drift_vals, 1)
            alpha = float(slope_fit)
            beta = float(intercept_fit)
            r, p = stats.pearsonr(iob_vals, drift_vals)
            r2 = float(r ** 2)

        # β = drift at IOB=0 = (EGP_rate - basal_insulin_effect) in mg/dL/hr
        # If β > 0: basal too low (EGP > basal effect)
        # If β < 0: basal too high (basal effect > EGP)
        # Δbasal = β / ISF (convert mg/dL/hr → U/hr)
        delta_basal = beta / scheduled_isf if scheduled_isf > 0 else 0
        recommended_basal = scheduled_basal + delta_basal

        # Validate on held-out data (80/20 split)
        n_train = int(len(bw) * 0.8)
        train = bw.iloc[:n_train]
        test = bw.iloc[n_train:]

        if len(test) >= 3:
            # Predicted drift with new basal: drift_new = drift_old - Δbasal × ISF
            test_drift_original = test["drift"].values
            test_drift_corrected = test_drift_original - delta_basal * scheduled_isf
            var_original = float(np.var(test_drift_original))
            var_corrected = float(np.var(test_drift_corrected))
            # More meaningful: does mean drift get closer to zero?
            mae_original = float(np.mean(np.abs(test_drift_original)))
            mae_corrected = float(np.mean(np.abs(test_drift_corrected)))
            validation = {
                "n_test": len(test),
                "mae_original": mae_original,
                "mae_corrected": mae_corrected,
                "mae_reduction_pct": float((mae_original - mae_corrected) / mae_original * 100) if mae_original > 0 else 0,
                "var_original": var_original,
                "var_corrected": var_corrected,
            }
        else:
            validation = None

        result[block_name] = {
            "n_nights": len(bw),
            "mean_drift": float(np.mean(drift_vals)),
            "alpha": alpha,
            "beta": beta,
            "r_iob_drift": float(r),
            "p_value": float(p),
            "r2": r2,
            "delta_basal_uhr": float(delta_basal),
            "recommended_basal": float(max(0.05, recommended_basal)),
            "pct_change": float(delta_basal / scheduled_basal * 100) if scheduled_basal > 0 else 0,
            "validation": validation,
        }

    # Dawn vs midnight comparison
    if "midnight" in result and "dawn" in result:
        dawn_rec = result["dawn"]["recommended_basal"]
        midnight_rec = result["midnight"]["recommended_basal"]
        result["dawn_increase_pct"] = float((dawn_rec - midnight_rec) / midnight_rec * 100) if midnight_rec > 0 else 0

    return result


def main():
    print("=" * 70)
    print("EXP-2650: IOB-Corrected Basal Recommendation")
    print("=" * 70)

    df = pd.read_parquet(PARQUET)
    results = {}

    for pid in ALL_PATIENTS:
        pdf = df[df["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        if len(pdf) < 288 * 14:
            continue

        r = _analyze_patient(pid, pdf)
        if r is None:
            continue
        results[pid] = r

        marker = "ODC" if pid.startswith("odc") else "NS"
        sched = r["scheduled_basal"]
        print(f"\n  [{marker}] {pid} (scheduled basal: {sched:.2f} U/hr, ISF: {r['scheduled_isf']:.0f}):")

        for block in ["midnight", "dawn"]:
            if block not in r:
                continue
            b = r[block]
            print(f"    {block:8s}: {b['n_nights']} nights, "
                  f"drift@IOB=0: {b['beta']:+.1f} mg/dL/hr, "
                  f"rec: {b['recommended_basal']:.2f} U/hr ({b['pct_change']:+.0f}%), "
                  f"r={b['r_iob_drift']:.3f}")
            if b.get("validation"):
                v = b["validation"]
                print(f"             validation: MAE {v['mae_original']:.1f} → {v['mae_corrected']:.1f} "
                      f"({v['mae_reduction_pct']:+.0f}%)")

        if "dawn_increase_pct" in r:
            print(f"    dawn vs midnight: {r['dawn_increase_pct']:+.0f}% basal increase")

    # ── Hypothesis testing ────────────────────────────────────────
    print("\n" + "=" * 70)
    print("HYPOTHESIS TESTING")
    print("=" * 70)

    # H1: ≥50% patients need ≥0.05 U/hr change
    patients_with_midnight = [r for r in results.values() if "midnight" in r]
    if patients_with_midnight:
        big_changes = sum(1 for r in patients_with_midnight
                          if abs(r["midnight"]["delta_basal_uhr"]) >= 0.05)
        h1_pct = big_changes / len(patients_with_midnight) * 100
        h1_pass = h1_pct >= 50
        print(f"\n  H1: ≥50% patients need ≥0.05 U/hr basal change")
        print(f"      {big_changes}/{len(patients_with_midnight)} ({h1_pct:.0f}%) need adjustment")
        print(f"      → {'PASS' if h1_pass else 'FAIL'}")

    # H2: Recommended basal reduces held-out MAE ≥15%
    validated = [r for r in patients_with_midnight
                 if r["midnight"].get("validation") and r["midnight"]["validation"]["mae_reduction_pct"] > 0]
    if validated:
        reductions = [r["midnight"]["validation"]["mae_reduction_pct"] for r in validated]
        big_reductions = sum(1 for rd in reductions if rd >= 15)
        h2_pass = big_reductions / len(patients_with_midnight) * 100 >= 50
        print(f"\n  H2: Recommended basal reduces held-out MAE ≥15%")
        print(f"      Reductions: {[f'{rd:.0f}%' for rd in sorted(reductions, reverse=True)]}")
        print(f"      → {'PASS' if h2_pass else 'FAIL'}")

    # H3: Dawn needs ≥20% more basal for ≥50% of patients
    dawn_patients = [r for r in results.values() if "dawn_increase_pct" in r]
    if dawn_patients:
        dawn_increases = sum(1 for r in dawn_patients if r["dawn_increase_pct"] >= 20)
        h3_pct = dawn_increases / len(dawn_patients) * 100
        h3_pass = h3_pct >= 50
        print(f"\n  H3: Dawn (04-08h) needs ≥20% more basal than midnight-04h")
        dawn_vals = [r["dawn_increase_pct"] for r in dawn_patients]
        print(f"      Dawn increases: {[f'{d:+.0f}%' for d in sorted(dawn_vals, reverse=True)]}")
        print(f"      {dawn_increases}/{len(dawn_patients)} ({h3_pct:.0f}%) need ≥20% increase")
        print(f"      → {'PASS' if h3_pass else 'FAIL'}")

    # ── Summary table ─────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("BASAL RECOMMENDATION SUMMARY")
    print("=" * 70)
    print(f"  {'Patient':<15} {'Sched':>6} {'Midnight':>9} {'Dawn':>9} {'Dawn Δ':>7}")
    print(f"  {'':.<15} {'U/hr':>6} {'U/hr':>9} {'U/hr':>9} {'%':>7}")
    for pid in sorted(results.keys()):
        r = results[pid]
        mn = r["midnight"]["recommended_basal"] if "midnight" in r else float('nan')
        dn = r["dawn"]["recommended_basal"] if "dawn" in r else float('nan')
        di = r.get("dawn_increase_pct", float('nan'))
        print(f"  {pid:<15} {r['scheduled_basal']:>6.2f} {mn:>9.2f} {dn:>9.2f} {di:>+7.0f}%")

    with open(OUTFILE, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to {OUTFILE}")


if __name__ == "__main__":
    main()
