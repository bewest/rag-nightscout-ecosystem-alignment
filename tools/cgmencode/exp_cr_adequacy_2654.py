#!/usr/bin/env python3
"""EXP-2654: CR Adequacy via Post-Meal Trajectory.

MOTIVATION: EXP-2650 addressed basal, EXP-2651 addressed ISF.
This completes the settings trifecta with Carb Ratio (CR) analysis.

If CR is correct, glucose should return to pre-meal baseline by ~5h
(DIA=6h, carb absorption ~3-4h). If glucose remains elevated,
CR is too high (under-dosed). If glucose drops below, CR too low.

METHOD:
  1. Detect announced meals: carbs ≥ 10g with bolus within ±30min
  2. Record pre-meal glucose (30min mean before meal)
  3. Track 5h trajectory → compute glucose delta (post - pre)
  4. CR adequacy score: delta / pre_glucose → % residual
  5. Recommend CR adjustment: new_CR = old_CR × (1 - residual/target_drop)
  6. Nyquist-aware: include 48h metabolic context as covariate

HYPOTHESES:
  H1: ≥50% of patients have mean |residual| ≥ 20 mg/dL (CR is wrong)
  H2: Residual correlates with meal size (r > 0.2) — large meals more off
  H3: 48h carb history predicts residual direction (r > 0.15)
  H4: Per-patient CR adjustment varies ≥30% across patients
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PARQUET = Path("externals/ns-parquet/training/grid.parquet")
RESULTS_DIR = Path("externals/experiments")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
OUTFILE = RESULTS_DIR / "exp-2654_cr_adequacy.json"

NS_PATIENTS = ["a", "b", "c", "d", "e", "f", "g", "i", "k"]
ODC_FULL = ["odc-74077367", "odc-86025410", "odc-96254963"]
ALL_PATIENTS = NS_PATIENTS + ODC_FULL
STEPS_PER_HOUR = 12


def _extract_meals(pdf, min_carbs=10, bolus_window_min=30, obs_hours=5):
    """Extract announced meals with pre/post glucose trajectories."""
    pdf = pdf.sort_values("time").reset_index(drop=True)

    glucose = pdf["glucose"].values.astype(np.float64)
    carbs = pdf["carbs"].fillna(0).values.astype(np.float64)
    bolus = pdf["bolus"].fillna(0).values.astype(np.float64)
    iob = pdf["iob"].fillna(0).values.astype(np.float64)
    sched_cr = pdf["scheduled_cr"].fillna(0).values.astype(np.float64)

    bolus_window = int(bolus_window_min / 5)  # steps
    pre_window = int(0.5 * STEPS_PER_HOUR)  # 30min before
    post_window = int(obs_hours * STEPS_PER_HOUR)  # 5h after
    lookback_48h = int(48 * STEPS_PER_HOUR)

    meals = []
    i = pre_window
    while i < len(pdf) - post_window:
        if carbs[i] < min_carbs:
            i += 1
            continue

        meal_carbs = float(carbs[i])

        # Check for bolus within ±bolus_window
        bolus_start = max(0, i - bolus_window)
        bolus_end = min(len(pdf), i + bolus_window + 1)
        meal_bolus = float(np.nansum(bolus[bolus_start:bolus_end]))
        if meal_bolus < 0.3:
            i += STEPS_PER_HOUR  # skip 1h
            continue

        # Pre-meal glucose (30min mean)
        pre_bg = glucose[i - pre_window:i]
        valid_pre = pre_bg[~np.isnan(pre_bg)]
        if len(valid_pre) < 3:
            i += STEPS_PER_HOUR
            continue
        pre_glucose = float(np.mean(valid_pre))

        # Post-meal trajectory
        post_bg = glucose[i:i + post_window + 1]
        valid_post = ~np.isnan(post_bg)
        if np.sum(valid_post) < post_window * 0.5:
            i += STEPS_PER_HOUR
            continue

        # Glucose at various timepoints
        def _bg_at(hours):
            idx = int(hours * STEPS_PER_HOUR)
            window = post_bg[max(0, idx-3):idx+4]
            valid = window[~np.isnan(window)]
            return float(np.mean(valid)) if len(valid) >= 2 else np.nan

        bg_1h = _bg_at(1)
        bg_2h = _bg_at(2)
        bg_3h = _bg_at(3)
        bg_5h = _bg_at(5)

        # Peak glucose
        smoothed = pd.Series(post_bg).rolling(6, min_periods=3, center=True).mean().values
        peak_idx = np.nanargmax(smoothed[:int(3 * STEPS_PER_HOUR)])
        peak_glucose = float(np.nanmax(smoothed[:int(3 * STEPS_PER_HOUR)]))
        peak_time_h = float(peak_idx / STEPS_PER_HOUR)

        # Residual at 5h (key CR metric)
        residual_5h = bg_5h - pre_glucose if not np.isnan(bg_5h) else np.nan

        # IOB at meal time
        iob_at_meal = float(iob[i])

        # CR at meal time
        cr = float(sched_cr[i]) if sched_cr[i] > 0 else np.nan

        # Expected dose for these carbs
        expected_dose = meal_carbs / cr if cr > 0 and not np.isnan(cr) else np.nan
        dose_ratio = meal_bolus / expected_dose if expected_dose > 0 else np.nan

        # 48h carb history
        lookback_start = max(0, i - lookback_48h)
        carbs_48h = float(np.nansum(carbs[lookback_start:i]))

        meals.append({
            "idx": int(i),
            "carbs": meal_carbs,
            "bolus": meal_bolus,
            "pre_glucose": pre_glucose,
            "peak_glucose": peak_glucose,
            "peak_time_h": peak_time_h,
            "bg_1h": bg_1h,
            "bg_2h": bg_2h,
            "bg_3h": bg_3h,
            "bg_5h": bg_5h,
            "residual_5h": residual_5h,
            "iob_at_meal": iob_at_meal,
            "scheduled_cr": cr,
            "dose_ratio": dose_ratio,
            "carbs_48h": carbs_48h,
        })

        # Skip ahead to avoid double-counting (min 2h between meals)
        i += 2 * STEPS_PER_HOUR

    return pd.DataFrame(meals)


def _analyze_patient(pid, pdf):
    """Per-patient CR adequacy analysis."""
    meals = _extract_meals(pdf)
    if len(meals) < 5:
        return None

    # Filter to meals with valid 5h residual
    valid = meals.dropna(subset=["residual_5h", "scheduled_cr"])
    if len(valid) < 5:
        return None

    residuals = valid["residual_5h"].values
    mean_residual = float(np.mean(residuals))
    median_residual = float(np.median(residuals))
    std_residual = float(np.std(residuals))

    # CR adequacy: residual > 0 → under-dosed (CR too high)
    pct_high = float(np.mean(residuals > 20))
    pct_low = float(np.mean(residuals < -20))
    pct_adequate = float(np.mean(np.abs(residuals) <= 20))

    # Recommended CR adjustment
    sched_cr = float(valid["scheduled_cr"].median())
    # If mean residual > 0, we need more insulin → lower CR
    # adjustment factor: how much to multiply CR by
    # Simple model: residual = (actual_carbs / actual_dose - ideal_cr) * dose
    # We approximate: new_cr = old_cr * pre_glucose / (pre_glucose + mean_residual)
    mean_pre = float(valid["pre_glucose"].mean())
    if mean_pre > 0:
        # More intuitive: if 5h glucose is 30 mg/dL above pre, and ISF=50,
        # that's 0.6U under-dosed. For 40g meal → CR should be 40/(bolus+0.6)
        sched_isf = float(pdf["scheduled_isf"].dropna().median())
        dose_correction = mean_residual / sched_isf if sched_isf > 0 else 0
        mean_bolus = float(valid["bolus"].mean())
        mean_carbs = float(valid["carbs"].mean())
        if mean_bolus > 0 and mean_carbs > 0:
            recommended_cr = mean_carbs / (mean_bolus + dose_correction)
            cr_change_pct = (recommended_cr / sched_cr - 1) * 100
        else:
            recommended_cr = np.nan
            cr_change_pct = np.nan
    else:
        recommended_cr = np.nan
        cr_change_pct = np.nan

    # Correlation: residual vs meal size
    r_carbs, p_carbs = stats.pearsonr(valid["carbs"].values, residuals)

    # Correlation: residual vs 48h carb history
    r_48h, p_48h = stats.pearsonr(valid["carbs_48h"].values, residuals)

    # Correlation: residual vs dose ratio
    dr = valid["dose_ratio"].dropna()
    if len(dr) >= 5:
        r_dose, p_dose = stats.pearsonr(dr.values,
                                         residuals[valid["dose_ratio"].notna()])
    else:
        r_dose, p_dose = np.nan, np.nan

    return {
        "n_meals": len(valid),
        "mean_carbs": float(valid["carbs"].mean()),
        "mean_bolus": float(valid["bolus"].mean()),
        "scheduled_cr": sched_cr,
        "mean_pre_glucose": mean_pre,
        "mean_peak": float(valid["peak_glucose"].mean()),
        "mean_peak_time_h": float(valid["peak_time_h"].mean()),
        "mean_residual_5h": mean_residual,
        "median_residual_5h": median_residual,
        "std_residual_5h": std_residual,
        "pct_high_5h": pct_high,
        "pct_low_5h": pct_low,
        "pct_adequate": pct_adequate,
        "recommended_cr": float(recommended_cr) if not np.isnan(recommended_cr) else None,
        "cr_change_pct": float(cr_change_pct) if not np.isnan(cr_change_pct) else None,
        "r_carbs_residual": float(r_carbs),
        "p_carbs_residual": float(p_carbs),
        "r_48h_residual": float(r_48h),
        "p_48h_residual": float(p_48h),
        "r_doseratio_residual": float(r_dose) if not np.isnan(r_dose) else None,
    }


def main():
    print("=" * 70)
    print("EXP-2654: CR Adequacy via Post-Meal Trajectory")
    print("=" * 70)

    df_all = pd.read_parquet(PARQUET)
    results = {}

    for pid in ALL_PATIENTS:
        pdf = df_all[df_all["patient_id"] == pid].copy()
        if len(pdf) < 200:
            continue

        r = _analyze_patient(pid, pdf)
        if r is None:
            print(f"\n  {pid}: insufficient announced meals")
            continue

        prefix = "[ODC]" if pid.startswith("odc") else "[NS] "
        print(f"\n  {prefix} {pid} ({r['n_meals']} meals, CR={r['scheduled_cr']:.0f}):")
        print(f"    Mean meal: {r['mean_carbs']:.0f}g → {r['mean_bolus']:.1f}U")
        print(f"    Pre: {r['mean_pre_glucose']:.0f}, Peak: {r['mean_peak']:.0f} "
              f"(+{r['mean_peak'] - r['mean_pre_glucose']:.0f}) at {r['mean_peak_time_h']:.1f}h")
        print(f"    5h residual: {r['mean_residual_5h']:+.0f} ± {r['std_residual_5h']:.0f} mg/dL "
              f"(adequate: {r['pct_adequate']*100:.0f}%, high: {r['pct_high_5h']*100:.0f}%, "
              f"low: {r['pct_low_5h']*100:.0f}%)")
        if r['recommended_cr'] is not None:
            print(f"    Recommended CR: {r['recommended_cr']:.1f} ({r['cr_change_pct']:+.0f}%)")
        print(f"    r(carbs→resid)={r['r_carbs_residual']:+.2f}, "
              f"r(48h→resid)={r['r_48h_residual']:+.2f}")

        results[pid] = r

    # === Hypothesis testing ===
    print("\n" + "=" * 70)
    print("HYPOTHESIS TESTING")
    print("=" * 70)

    # H1: ≥50% have |mean residual| ≥ 20
    bad_cr = sum(1 for r in results.values() if abs(r["mean_residual_5h"]) >= 20)
    total = len(results)
    print(f"\n  H1: ≥50% have |mean residual| ≥ 20 mg/dL")
    print(f"      {bad_cr}/{total} ({bad_cr/total*100:.0f}%)")
    residuals_str = [f'{r["mean_residual_5h"]:+.0f}' for r in results.values()]
    print(f"      Residuals: {residuals_str}")
    h1 = bad_cr >= total / 2
    print(f"      → {'PASS' if h1 else 'FAIL'}")

    # H2: Residual correlates with meal size (r > 0.2)
    sig_corr = sum(1 for r in results.values() if abs(r["r_carbs_residual"]) > 0.2)
    print(f"\n  H2: |r(carbs→residual)| > 0.2 for ≥50%")
    print(f"      {sig_corr}/{total}")
    corrs_str = [f'{r["r_carbs_residual"]:+.2f}' for r in results.values()]
    print(f"      Correlations: {corrs_str}")
    h2 = sig_corr >= total / 2
    print(f"      → {'PASS' if h2 else 'FAIL'}")

    # H3: 48h carbs predict residual direction
    sig_48h = sum(1 for r in results.values() if abs(r["r_48h_residual"]) > 0.15)
    print(f"\n  H3: |r(48h→residual)| > 0.15 for ≥50%")
    print(f"      {sig_48h}/{total}")
    corrs_48h_str = [f'{r["r_48h_residual"]:+.2f}' for r in results.values()]
    print(f"      Correlations: {corrs_48h_str}")
    h3 = sig_48h >= total / 2
    print(f"      → {'PASS' if h3 else 'FAIL'}")

    # H4: CR adjustment varies ≥30% across patients
    changes = [r["cr_change_pct"] for r in results.values()
               if r.get("cr_change_pct") is not None]
    if changes:
        cr_range = max(changes) - min(changes)
        print(f"\n  H4: CR adjustment range ≥ 30%")
        print(f"      Range: {cr_range:.0f}% ({min(changes):+.0f}% to {max(changes):+.0f}%)")
        h4 = cr_range >= 30
        print(f"      → {'PASS' if h4 else 'FAIL'}")

    Path(OUTFILE).write_text(json.dumps(results, indent=2, default=str))
    print(f"\nResults saved to {OUTFILE}")


if __name__ == "__main__":
    main()
